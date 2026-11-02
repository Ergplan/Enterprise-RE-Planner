"""The retention sweeper (build prompt 6.2, Stage 2.2): every `interval_seconds` (600 by
default) it deletes every job, row and folder, submitted more than `retention_hours` (24)
ago, so no file or result outlives the contract's 24 hours. Folders with no row (left by
a crash between a folder delete and a row delete, or the reverse) go too once they are
older than the retention. It logs counts only.
"""

from __future__ import annotations

import logging
import threading
import time

from billx.platform.store.files import BadJobId, FileStore
from billx.platform.store.jobs import JobStore

log = logging.getLogger(__name__)


class Sweeper:
    """A daemon thread calling `run_once` every `interval_seconds`."""

    def __init__(
        self,
        store: JobStore,
        files: FileStore,
        *,
        retention_hours: int = 24,
        interval_seconds: int = 600,
    ):
        if isinstance(retention_hours, bool) or retention_hours < 0:
            raise ValueError("retention_hours must be a non-negative int")
        if interval_seconds < 1:
            raise ValueError("interval_seconds must be at least 1")
        self.store = store
        self.files = files
        self.retention_hours = retention_hours
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> int:
        """Delete every expired job; returns how many jobs (rows or orphan folders) went."""
        deleted = 0
        for job in self.store.older_than(self.retention_hours):
            try:
                self.files.delete(job.job_id)
            except BadJobId:
                log.error("job %s: folder name refused; row deleted only", job.job_id)
            self.store.delete(job.job_id)
            deleted += 1
        orphans = self._sweep_orphans()
        if deleted or orphans:
            log.info("sweeper deleted %d expired job(s), %d orphan folder(s)", deleted, orphans)
        return deleted + orphans

    def _sweep_orphans(self) -> int:
        cutoff = int(time.time()) - self.retention_hours * 3600
        gone = 0
        for job_id in self.files.job_ids():
            try:
                if self.files.folder_mtime(job_id) >= cutoff or self.store.get(job_id):
                    continue
                if self.files.delete(job_id):
                    gone += 1
            except (BadJobId, OSError):
                log.error("sweeper could not inspect one folder")
        return gone

    def start(self) -> None:
        """Start sweeping in the background (the first sweep runs at once)."""
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="billx-sweeper", daemon=True)
        self._thread.start()

    def stop(self, timeout: int | None = None) -> None:
        """Stop the thread; a sweep in progress finishes first."""
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001 - the sweeper must keep running
                log.error("sweep failed: %s", type(exc).__name__)
            self._stop.wait(self.interval_seconds)


__all__ = ["Sweeper"]
