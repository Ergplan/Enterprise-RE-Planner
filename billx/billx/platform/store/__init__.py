"""The embedded store behind the API (build prompt Stage 2.2): the SQLite job store, a
folder per job, the bounded in-process queue and the 24-hour sweeper, all under
`BILLX_DATA_DIR` (the embedded image mounts `/data` there).

Settings (rule 12: nothing environment-specific in code) come from the environment or the
env file through `billx.core.settings.setting`:

- `BILLX_DATA_DIR`: the root (default `~/billx-data`).
- `BILLX_MAX_JOBS`: jobs run at once (default 4, the contract's figure; the image may ship
  a smaller default where memory needs it, build prompt Stage 2.5: four jobs are still
  accepted at once, the rest wait in the queue).
- `BILLX_QUEUE_LIMIT`: jobs that may wait before 429 (default 32).
- `BILLX_RETENTION_HOURS`: how long a job's file and result may live (default 24).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from billx.core.settings import data_dir, setting
from billx.platform.store.files import BadJobId, FileStore
from billx.platform.store.jobs import (
    Job,
    JobStore,
    RequestIdConflict,
    StoreError,
    UnknownJob,
    format_time,
    new_job_id,
)
from billx.platform.store.queue import JobFailure, Queue, QueueFull
from billx.platform.store.sweeper import Sweeper

DEFAULT_MAX_JOBS = 4
DEFAULT_QUEUE_LIMIT = 32
DEFAULT_RETENTION_HOURS = 24
SWEEP_INTERVAL_SECONDS = 600


def _int_setting(name: str, default: int, *, minimum: int) -> int:
    raw = setting(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    return max(minimum, value)


@dataclass(frozen=True)
class Settings:
    """The store's configuration, read once at start."""

    data_dir: Path
    max_jobs: int = DEFAULT_MAX_JOBS
    queue_limit: int = DEFAULT_QUEUE_LIMIT
    retention_hours: int = DEFAULT_RETENTION_HOURS
    sweep_interval_seconds: int = SWEEP_INTERVAL_SECONDS

    @classmethod
    def from_env(cls) -> Settings:
        """From `BILLX_DATA_DIR`, `BILLX_MAX_JOBS` (at least 1), `BILLX_QUEUE_LIMIT` and
        `BILLX_RETENTION_HOURS`."""
        return cls(
            data_dir=data_dir(),
            max_jobs=_int_setting("BILLX_MAX_JOBS", DEFAULT_MAX_JOBS, minimum=1),
            queue_limit=_int_setting("BILLX_QUEUE_LIMIT", DEFAULT_QUEUE_LIMIT, minimum=0),
            retention_hours=_int_setting(
                "BILLX_RETENTION_HOURS", DEFAULT_RETENTION_HOURS, minimum=0
            ),
        )


__all__ = [
    "DEFAULT_MAX_JOBS",
    "DEFAULT_QUEUE_LIMIT",
    "DEFAULT_RETENTION_HOURS",
    "SWEEP_INTERVAL_SECONDS",
    "BadJobId",
    "FileStore",
    "Job",
    "JobFailure",
    "JobStore",
    "Queue",
    "QueueFull",
    "RequestIdConflict",
    "Settings",
    "StoreError",
    "Sweeper",
    "UnknownJob",
    "format_time",
    "new_job_id",
]
