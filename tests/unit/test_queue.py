"""The bounded in-process queue (Stage 2.2): concurrency, the limit, failures without
values, thread safety, recovery. Temp folders only; no network."""

import logging
import threading
import time
from datetime import UTC, datetime

import pytest

from billx.platform.store.files import FileStore
from billx.platform.store.jobs import JobStore
from billx.platform.store.queue import JobFailure, Queue, QueueFull

PLANTED = "SYN-PLANTED-9876543"  # a value-like string that must never reach store or log


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "data", clock=lambda: datetime.now(UTC))


@pytest.fixture
def files(tmp_path):
    return FileStore(tmp_path / "data")


def submit_new(store, queue, request_id, **over):
    job, _ = store.create(
        request_id=request_id,
        product="esgos",
        sha256=f"{abs(hash(request_id)) % 10**12:012d}".ljust(64, "0"),
        media_type="application/pdf",
        size=10,
        kind="bill",
        options={"allow_cloud_model": False},
    )
    queue.submit(job)
    return job


def wait_until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("timed out")
        time.sleep(0.01)


def test_four_jobs_run_at_once(store, files):
    barrier = threading.Barrier(4, timeout=10)
    seen = []
    lock = threading.Lock()
    live = 0
    peak = 0

    def process(job):
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        barrier.wait()  # all four must be inside at the same moment
        time.sleep(0.05)
        files.write_result(job.job_id, "{}")
        store.mark_done(job.job_id, files.result_path(job.job_id))
        with lock:
            live -= 1
            seen.append(job.job_id)

    queue = Queue(store, process, max_jobs=4, queue_limit=32)
    queue.start()
    try:
        jobs = [submit_new(store, queue, f"r{i}") for i in range(4)]
        wait_until(lambda: store.count("done") == 4)
    finally:
        queue.stop(timeout=5)
    assert peak == 4 and set(seen) == {j.job_id for j in jobs}
    for job in jobs:
        after = store.get(job.job_id)
        assert after.status == "done" and after.attempts == 1
        assert after.started_at and after.finished_at and after.result_path
    assert queue.depth() == 0 and queue.running() == 0


def test_queue_bounds_at_queue_limit_with_retry_after(store):
    release = threading.Event()

    def process(job):
        release.wait(10)
        store.mark_done(job.job_id, "r")

    queue = Queue(store, process, max_jobs=1, queue_limit=2)
    queue.start()
    try:
        running = submit_new(store, queue, "running")
        wait_until(lambda: queue.running() == 1)
        submit_new(store, queue, "wait-1")
        submit_new(store, queue, "wait-2")
        assert queue.depth() == 2
        extra, _ = store.create(
            request_id="extra",
            product="esgos",
            sha256="f" * 64,
            media_type="image/png",
            size=1,
            kind="bill",
            options={},
        )
        with pytest.raises(QueueFull) as info:
            queue.submit(extra)
        assert info.value.depth == 2
        assert isinstance(info.value.retry_after_seconds, int)
        assert info.value.retry_after_seconds >= 5
        # With no history the estimate is (2 + 1) jobs x 30 s default over 1 worker.
        assert info.value.retry_after_seconds == 90
        assert queue.depth() == 2 and store.get(extra.job_id).status == "queued"
        release.set()
        wait_until(lambda: store.count("done") == 3)
        assert store.get(running.job_id).status == "done"
    finally:
        release.set()
        queue.stop(timeout=5)


def test_retry_after_uses_the_median_job_time_and_floors_at_5(store):
    def process(job):
        time.sleep(0.01)
        store.mark_done(job.job_id, "r")

    queue = Queue(store, process, max_jobs=4, queue_limit=0)
    queue.start()
    try:
        queue._durations_ms.extend([10, 20, 15])
        assert queue._retry_after(0) == 5
        queue._durations_ms.clear()
        queue._durations_ms.extend([40_000, 60_000, 50_000])
        assert queue._retry_after(7) == 100  # 8 jobs x 50 s / 4 workers
        with pytest.raises(QueueFull) as info:
            submit_new(store, queue, "any")
        assert info.value.retry_after_seconds == 13  # 1 x 50 / 4 -> ceil
    finally:
        queue.stop(timeout=5)


def test_failure_stores_the_class_name_only(store, caplog):
    class SyntheticReadError(RuntimeError):
        pass

    def process(job):
        raise SyntheticReadError(f"could not read net payable {PLANTED}")

    queue = Queue(store, process, max_jobs=4, queue_limit=4)
    with caplog.at_level(logging.DEBUG):
        queue.start()
        try:
            job = submit_new(store, queue, "boom")
            wait_until(lambda: store.get(job.job_id).status == "failed")
        finally:
            queue.stop(timeout=5)
    after = store.get(job.job_id)
    assert after.error_code == "internal" and after.error_message == "SyntheticReadError"
    assert after.result_path is None and after.finished_at
    assert PLANTED not in (after.error_message or "") and PLANTED not in caplog.text
    assert "net payable" not in caplog.text
    assert f"job {job.job_id} failed: SyntheticReadError" in caplog.text


def test_job_failure_names_its_code_and_unmarked_jobs_fail(store):
    def process(job):
        if job.request_id == "budget":
            raise JobFailure("budget_exceeded")
        return None  # forgot to mark done

    queue = Queue(store, process, max_jobs=2, queue_limit=4)
    queue.start()
    try:
        a = submit_new(store, queue, "budget")
        b = submit_new(store, queue, "forgot")
        wait_until(lambda: store.count("failed") == 2)
    finally:
        queue.stop(timeout=5)
    assert store.get(a.job_id).error_code == "budget_exceeded"
    assert store.get(a.job_id).error_message == "JobFailure"
    assert store.get(b.job_id).error_message == "ResultNotRecorded"


def test_submit_from_several_threads(store):
    def process(job):
        store.mark_done(job.job_id, "r")

    queue = Queue(store, process, max_jobs=4, queue_limit=1000)
    queue.start()
    errors = []

    def submitter(n):
        try:
            for i in range(20):
                submit_new(store, queue, f"t{n}-{i}")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    try:
        threads = [threading.Thread(target=submitter, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert errors == []
        wait_until(lambda: store.count("done") == 160, timeout=30)
    finally:
        queue.stop(timeout=5)
    assert queue.depth() == 0 and queue.running() == 0


def test_recover_requeues_jobs_from_a_crashed_process(tmp_path):
    root = tmp_path / "data"
    first = JobStore(root)
    stale, _ = first.create(
        request_id="stale",
        product="esgos",
        sha256="1" * 64,
        media_type="application/pdf",
        size=1,
        kind="bill",
        options={},
    )
    first.mark_reading(stale.job_id)
    del first

    second = JobStore(root)
    done = []

    def process(job):
        second.mark_done(job.job_id, "r")
        done.append(job.job_id)

    queue = Queue(second, process, max_jobs=4, queue_limit=0)
    assert queue.recover() == 1
    queue.start()
    try:
        wait_until(lambda: second.get(stale.job_id).status == "done")
    finally:
        queue.stop(timeout=5)
    assert done == [stale.job_id] and second.get(stale.job_id).attempts == 2


def test_stop_leaves_waiting_jobs_queued_for_the_next_start(store):
    release = threading.Event()

    def process(job):
        release.wait(10)
        store.mark_done(job.job_id, "r")

    queue = Queue(store, process, max_jobs=1, queue_limit=5)
    queue.start()
    submit_new(store, queue, "running")
    wait_until(lambda: queue.running() == 1)
    waiting = submit_new(store, queue, "waiting")
    release.set()
    queue.stop(timeout=5)
    # The worker drains what it can before stopping; whatever is left is still queued.
    status = store.get(waiting.job_id).status
    assert status in {"queued", "done"}
    assert queue.running() == 0
    with pytest.raises(ValueError):
        Queue(store, process, max_jobs=0)
