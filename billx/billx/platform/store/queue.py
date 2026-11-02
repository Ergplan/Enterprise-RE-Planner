"""The in-process bounded queue (build prompt Stage 2.2): `max_jobs` worker threads take
queued jobs in submission order; beyond `queue_limit` waiting jobs `submit` raises
`QueueFull`, which carries the `Retry-After` estimate the API returns with 429 (contract
1.0 section 8).

A worker marks the job `reading`, calls `process(job)` (the API's function, which runs the
pipeline, writes the result through the `FileStore` and marks the job `done`), and on any
exception marks the job `failed` with the exception's class name only: a message could
carry a value from the bill, and neither the store nor the log may hold one (invariant 9).
Logs carry job ids, counts and timings only.
"""

from __future__ import annotations

import logging
import queue
import statistics
import threading
import time
from collections import deque
from collections.abc import Callable

from billx.platform.store.jobs import Job, JobStore, UnknownJob

log = logging.getLogger(__name__)

_STOP = object()
MIN_RETRY_AFTER_SECONDS = 5
DEFAULT_JOB_SECONDS = 30


class QueueFull(Exception):
    """More than `queue_limit` jobs are waiting. `retry_after_seconds` (an int, at least 5)
    estimates when a slot will be free from the queue depth and the median job time."""

    def __init__(self, depth: int, retry_after_seconds: int):
        super().__init__(f"queue full: {depth} waiting, retry after {retry_after_seconds}s")
        self.depth = depth
        self.retry_after_seconds = retry_after_seconds


class JobFailure(Exception):
    """A `process` function may raise this to name the failure's error code (default
    `internal`). As with any exception, only the class name is stored, never the message."""

    code = "internal"

    def __init__(self, code: str = "internal"):
        super().__init__(code)
        self.code = code


class Queue:
    """A bounded queue of jobs with a pool of worker threads."""

    def __init__(
        self,
        store: JobStore,
        process: Callable[[Job], None],
        *,
        max_jobs: int = 4,
        queue_limit: int = 32,
        default_job_seconds: int = DEFAULT_JOB_SECONDS,
    ):
        if max_jobs < 1:
            raise ValueError("max_jobs must be at least 1")
        if queue_limit < 0:
            raise ValueError("queue_limit must be at least 0")
        self.store = store
        self.process = process
        self.max_jobs = max_jobs
        self.queue_limit = queue_limit
        self.default_job_seconds = default_job_seconds
        self._queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._running = 0
        self._durations_ms: deque[int] = deque(maxlen=64)
        self._threads: list[threading.Thread] = []
        self._started = False

    # -- lifecycle -------------------------------------------------------------------------

    def start(self) -> None:
        """Start the worker threads (daemon, so they never block process exit)."""
        with self._lock:
            if self._started:
                return
            self._started = True
            for i in range(self.max_jobs):
                t = threading.Thread(target=self._worker, name=f"billx-job-{i}", daemon=True)
                t.start()
                self._threads.append(t)
        log.info("queue started: workers=%d queue_limit=%d", self.max_jobs, self.queue_limit)

    def stop(self, timeout: int | None = None) -> None:
        """Ask every worker to finish its current job and stop; wait up to `timeout`
        seconds in all. Jobs still waiting stay `queued` in the store for the next start."""
        with self._lock:
            if not self._started:
                return
            threads, self._threads = self._threads, []
            self._started = False
        for _ in threads:
            self._queue.put(_STOP)
        deadline = None if timeout is None else time.monotonic() + timeout
        for t in threads:
            t.join(None if deadline is None else max(0, deadline - time.monotonic()))
        log.info("queue stopped: still_waiting=%d", self.depth())

    def recover(self) -> int:
        """On start: put back every job the store still holds as `queued` or `reading`
        (left by a crash), ignoring the limit so none is lost. Returns how many."""
        jobs = self.store.requeue_stale()
        for job in jobs:
            self._queue.put(job)
        if jobs:
            log.info("queue recovered %d job(s) from the store", len(jobs))
        return len(jobs)

    # -- submission ------------------------------------------------------------------------

    def submit(self, job: Job) -> None:
        """Queue a job the store already holds; raises `QueueFull` when `queue_limit` jobs
        are already waiting."""
        with self._lock:
            depth = self._queue.qsize()
            if depth >= self.queue_limit:
                raise QueueFull(depth, self._retry_after(depth))
            self._queue.put(job)

    def depth(self) -> int:
        """Jobs waiting for a worker (not counting those running)."""
        return self._queue.qsize()

    def running(self) -> int:
        """Jobs a worker is processing now."""
        with self._lock:
            return self._running

    def _retry_after(self, depth: int) -> int:
        """Seconds until a slot is likely free: (waiting + 1) jobs ahead, each taking the
        median recent time, over `max_jobs` workers; integer arithmetic, at least 5."""
        if self._durations_ms:
            median_ms = int(statistics.median_low(self._durations_ms))
        else:
            median_ms = self.default_job_seconds * 1000
        total_ms = (depth + 1) * median_ms
        seconds = -(-total_ms // (self.max_jobs * 1000))  # ceiling division
        return max(MIN_RETRY_AFTER_SECONDS, seconds)

    # -- workers ---------------------------------------------------------------------------

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            self._run(item)

    def _run(self, job: Job) -> None:
        job_id = job.job_id
        try:
            self.store.mark_reading(job_id)
        except UnknownJob:
            log.info("job %s was deleted before it started", job_id)
            return
        with self._lock:
            self._running += 1
        started = time.monotonic_ns()
        try:
            self.process(job)
        except Exception as exc:  # noqa: BLE001 - every failure is recorded the same way
            name = type(exc).__name__
            code = exc.code if isinstance(exc, JobFailure) else "internal"
            log.error("job %s failed: %s (%s)", job_id, name, code)
            self._mark_failed(job_id, code, name)
        else:
            after = self.store.get(job_id)
            if after is not None and after.status == "reading":
                log.error("job %s: process returned without marking the job done", job_id)
                self._mark_failed(job_id, "internal", "ResultNotRecorded")
        finally:
            elapsed_ms = (time.monotonic_ns() - started) // 1_000_000
            with self._lock:
                self._running -= 1
                self._durations_ms.append(int(elapsed_ms))
            log.info("job %s finished in %d ms", job_id, elapsed_ms)

    def _mark_failed(self, job_id: str, code: str, name: str) -> None:
        try:
            self.store.mark_failed(job_id, code, name)
        except UnknownJob:
            log.info("job %s was deleted while running", job_id)


__all__ = ["DEFAULT_JOB_SECONDS", "MIN_RETRY_AFTER_SECONDS", "JobFailure", "Queue", "QueueFull"]
