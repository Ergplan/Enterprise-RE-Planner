"""The embedded job store (build prompt Stage 2.2): one SQLite file, `<root>/jobs.sqlite`.

A row per job, its validated options kept as JSON for the worker and never logged (invariant
9). Everything the store writes is text or an integer: timestamps are UTC ISO 8601 strings,
sizes and attempts are integers, a `Decimal` inside the options is stored as its string
(invariant 4; no float is ever stored).

Thread safety: every public method takes the store's lock and opens its own connection, so
the API's request threads, the queue's workers and the sweeper can share one `JobStore`.
`create` runs its request_id check and insert in one `BEGIN IMMEDIATE` transaction, so the
idempotency rule of contract 1.0 section 4.2 (same request_id and file: the same job; a
different file: 409) also holds across processes sharing the file.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from billx.platform.store._json import dumps_exact

Status = Literal["queued", "reading", "done", "failed"]
Kind = Literal["bill", "text"]

STATUSES: tuple[str, ...] = ("queued", "reading", "done", "failed")
KINDS: tuple[str, ...] = ("bill", "text")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id        TEXT PRIMARY KEY,
    request_id    TEXT NOT NULL UNIQUE,
    product       TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    media_type    TEXT NOT NULL,
    size          INTEGER NOT NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('bill', 'text')),
    options_json  TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('queued', 'reading', 'done', 'failed')),
    submitted_at  TEXT NOT NULL,
    started_at    TEXT,
    finished_at   TEXT,
    error_code    TEXT,
    error_message TEXT,
    result_path   TEXT,
    attempts      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS jobs_submitted_at ON jobs (submitted_at);
"""

_COLUMNS = (
    "job_id",
    "request_id",
    "product",
    "sha256",
    "media_type",
    "size",
    "kind",
    "options_json",
    "status",
    "submitted_at",
    "started_at",
    "finished_at",
    "error_code",
    "error_message",
    "result_path",
    "attempts",
)
_SELECT = f"SELECT {', '.join(_COLUMNS)} FROM jobs"


class StoreError(Exception):
    """Base of the store's own errors."""


class RequestIdConflict(StoreError):
    """The request_id already names a job for a different file (the API answers 409)."""

    def __init__(self, request_id: str, job_id: str):
        super().__init__(f"request_id already used for job {job_id}")
        self.request_id = request_id
        self.job_id = job_id


class UnknownJob(StoreError):
    """A status change was asked for a job_id the store does not hold."""

    def __init__(self, job_id: str):
        super().__init__(f"unknown job {job_id}")
        self.job_id = job_id


@dataclass(frozen=True)
class Job:
    """One row of the store. `options` is the validated options object as the API gave it
    (a `Decimal` comes back as its string); it must never be logged."""

    job_id: str
    request_id: str
    product: str
    sha256: str
    media_type: str
    size: int
    kind: str
    options: dict
    status: str
    submitted_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    result_path: str | None = None
    attempts: int = 0

    @classmethod
    def _from_row(cls, row: sqlite3.Row | tuple) -> Job:
        values = dict(zip(_COLUMNS, row, strict=True))
        values["options"] = json.loads(values.pop("options_json"))
        return cls(**values)


def utc_now() -> datetime:
    """The store's default clock: an aware UTC datetime."""
    return datetime.now(UTC)


def format_time(moment: datetime) -> str:
    """`2026-10-07T10:15:02Z`, the contract's form (section 3: UTC, ISO 8601)."""
    if moment.tzinfo is None:
        raise ValueError("naive datetime")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_job_id() -> str:
    """A UUID version 7 string: 48 bits of Unix milliseconds, then random bits, so ids sort by
    submission time and never collide in practice."""
    ms = time.time_ns() // 1_000_000
    rand = secrets.randbits(74)
    rand_a, rand_b = rand >> 62, rand & ((1 << 62) - 1)
    value = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return str(uuid.UUID(int=value))


class JobStore:
    """Jobs in `<root>/jobs.sqlite`. `clock` returns the current aware UTC time; tests pass
    their own to age jobs."""

    def __init__(self, root: Path, *, clock: Callable[[], datetime] = utc_now):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "jobs.sqlite"
        self._clock = clock
        self._lock = threading.Lock()
        with self._lock, closing(self._connect()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _now(self) -> str:
        return format_time(self._clock())

    # -- creation and reading --------------------------------------------------------------

    def create(
        self,
        *,
        request_id: str,
        product: str,
        sha256: str,
        media_type: str,
        size: int,
        kind: str,
        options: dict,
    ) -> tuple[Job, bool]:
        """Insert a queued job and return `(job, True)`; for a request_id already held with
        the same sha256 return `(existing, False)`; with a different sha256 raise
        `RequestIdConflict`."""
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise TypeError("size must be a non-negative int")
        if not isinstance(options, dict):
            raise TypeError("options must be a dict")
        options_json = dumps_exact(options, "options")
        with self._lock, closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(f"{_SELECT} WHERE request_id = ?", (request_id,)).fetchone()
                if row is not None:
                    existing = Job._from_row(row)
                    if existing.sha256 != sha256:
                        raise RequestIdConflict(request_id, existing.job_id)
                    return existing, False
                job = Job(
                    job_id=new_job_id(),
                    request_id=request_id,
                    product=product,
                    sha256=sha256,
                    media_type=media_type,
                    size=size,
                    kind=kind,
                    options=json.loads(options_json),
                    status="queued",
                    submitted_at=self._now(),
                )
                conn.execute(
                    "INSERT INTO jobs (job_id, request_id, product, sha256, media_type, size,"
                    " kind, options_json, status, submitted_at, attempts)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                    (
                        job.job_id,
                        job.request_id,
                        job.product,
                        job.sha256,
                        job.media_type,
                        job.size,
                        job.kind,
                        options_json,
                        job.status,
                        job.submitted_at,
                    ),
                )
                return job, True
            finally:
                # Commits the insert, or releases the lock after a conflict or an early return.
                conn.execute("COMMIT")

    def get(self, job_id: str) -> Job | None:
        """The job, or None when the store does not hold it."""
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(f"{_SELECT} WHERE job_id = ?", (job_id,)).fetchone()
        return None if row is None else Job._from_row(row)

    def count(self, status: str | None = None) -> int:
        """How many jobs the store holds, in one status or in all."""
        with self._lock, closing(self._connect()) as conn:
            if status is None:
                return conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM jobs WHERE status = ?", (status,)).fetchone()[
                0
            ]

    def older_than(self, hours: int) -> list[Job]:
        """Every job submitted more than `hours` ago (whatever its status), oldest first."""
        if isinstance(hours, bool) or not isinstance(hours, int) or hours < 0:
            raise TypeError("hours must be a non-negative int")
        cutoff = format_time(self._clock() - timedelta(hours=hours))
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                f"{_SELECT} WHERE submitted_at < ? ORDER BY submitted_at, job_id", (cutoff,)
            ).fetchall()
        return [Job._from_row(r) for r in rows]

    # -- status transitions ----------------------------------------------------------------

    def _update(self, job_id: str, sql: str, params: tuple) -> Job:
        with self._lock, closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cur = conn.execute(f"UPDATE jobs SET {sql} WHERE job_id = ?", (*params, job_id))
                if cur.rowcount == 0:
                    raise UnknownJob(job_id)
                row = conn.execute(f"{_SELECT} WHERE job_id = ?", (job_id,)).fetchone()
            finally:
                conn.execute("COMMIT")
        return Job._from_row(row)

    def mark_reading(self, job_id: str) -> Job:
        """queued -> reading: stamps started_at and counts an attempt."""
        return self._update(
            job_id,
            "status = 'reading', started_at = ?, attempts = attempts + 1,"
            " finished_at = NULL, error_code = NULL, error_message = NULL",
            (self._now(),),
        )

    def mark_done(self, job_id: str, result_path: str | Path) -> Job:
        """reading -> done, with the path of the result file under the job folder."""
        return self._update(
            job_id,
            "status = 'done', finished_at = ?, result_path = ?,"
            " error_code = NULL, error_message = NULL",
            (self._now(), str(result_path)),
        )

    def mark_failed(self, job_id: str, code: str, message: str) -> Job:
        """reading -> failed. `message` is an identifier (an error class name, a check id),
        never a bill value."""
        return self._update(
            job_id,
            "status = 'failed', finished_at = ?, error_code = ?, error_message = ?,"
            " result_path = NULL",
            (self._now(), code, message),
        )

    def requeue_stale(self) -> list[Job]:
        """After a restart: every job left `reading` or `queued` by the previous process goes
        back to `queued` (its result, if any, was never recorded). Returns them oldest first
        for the queue to take."""
        with self._lock, closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "UPDATE jobs SET status = 'queued', started_at = NULL"
                    " WHERE status IN ('queued', 'reading')"
                )
                rows = conn.execute(
                    f"{_SELECT} WHERE status = 'queued' ORDER BY submitted_at, job_id"
                ).fetchall()
            finally:
                conn.execute("COMMIT")
        return [Job._from_row(r) for r in rows]

    def delete(self, job_id: str) -> bool:
        """Remove the row; True when it existed."""
        with self._lock, closing(self._connect()) as conn:
            cur = conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            return cur.rowcount > 0


__all__ = [
    "KINDS",
    "STATUSES",
    "Job",
    "JobStore",
    "RequestIdConflict",
    "StoreError",
    "UnknownJob",
    "format_time",
    "new_job_id",
    "utc_now",
]
