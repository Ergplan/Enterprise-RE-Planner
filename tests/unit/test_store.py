"""The embedded store (Stage 2.2): the SQLite job store, the file store, the sweeper and
the settings. Temp folders only; no network."""

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from billx.platform.store import Settings
from billx.platform.store.files import BadJobId, FileStore
from billx.platform.store.jobs import Job, JobStore, RequestIdConflict, UnknownJob, new_job_id
from billx.platform.store.sweeper import Sweeper

OPTIONS = {"allow_cloud_model": True, "max_cost_usd": "0.25", "hints": {"utility_id": "syn"}}


class Clock:
    """A settable UTC clock for the store."""

    def __init__(self, start: datetime | None = None):
        self.now = start or datetime(2026, 10, 7, 10, 15, 2, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    return JobStore(tmp_path / "data", clock=clock)


@pytest.fixture
def files(tmp_path):
    return FileStore(tmp_path / "data")


def make(store: JobStore, request_id="req-1", sha256="a" * 64, **over):
    args = dict(
        request_id=request_id,
        product="esgos",
        sha256=sha256,
        media_type="application/pdf",
        size=1234,
        kind="bill",
        options=OPTIONS,
    )
    args.update(over)
    return store.create(**args)


# -- job ids -------------------------------------------------------------------------------


def test_job_ids_are_uuid7_and_time_ordered():
    first = new_job_id()
    time.sleep(0.002)
    second = new_job_id()
    assert first[14] == "7" and first[19] in "89ab"
    assert first < second
    assert len({new_job_id() for _ in range(200)}) == 200


# -- create / get / idempotency ------------------------------------------------------------


def test_create_and_get(store):
    job, created = make(store)
    assert created and job.status == "queued" and job.attempts == 0
    assert job.submitted_at == "2026-10-07T10:15:02Z"
    assert job.started_at is None and job.finished_at is None and job.result_path is None
    got = store.get(job.job_id)
    assert got == job
    assert got.options == OPTIONS and got.size == 1234 and got.kind == "bill"
    assert store.get("0000") is None
    assert store.count() == 1 and store.count("queued") == 1 and store.count("done") == 0


def test_same_request_id_same_file_returns_the_same_job(store):
    job, created = make(store)
    again, created_again = make(store)
    assert created and not created_again
    assert again.job_id == job.job_id and store.count() == 1


def test_same_request_id_different_file_conflicts(store):
    job, _ = make(store)
    with pytest.raises(RequestIdConflict) as info:
        make(store, sha256="b" * 64)
    assert info.value.request_id == "req-1" and info.value.job_id == job.job_id
    assert store.count() == 1
    # The store is still usable afterwards (the transaction was released).
    other, created = make(store, request_id="req-2", sha256="b" * 64)
    assert created and other.job_id != job.job_id


def test_create_refuses_floats_and_keeps_decimals_as_strings(store):
    with pytest.raises(TypeError):
        make(store, options={"max_cost_usd": 0.25})
    with pytest.raises(TypeError):
        make(store, options={"hints": {"x": [1, 2.5]}})
    job, _ = make(store, options={"max_cost_usd": Decimal("0.25")})
    assert store.get(job.job_id).options == {"max_cost_usd": "0.25"}
    with pytest.raises(ValueError):
        make(store, request_id="r2", kind="other")
    with pytest.raises(TypeError):
        make(store, request_id="r3", size=12.0)


def test_nothing_stored_is_a_float(store):
    job, _ = make(store, options={"max_cost_usd": Decimal("1.50"), "n": 3})
    for f in fields(Job):
        assert not isinstance(getattr(job, f.name), float), f.name
    with sqlite3.connect(store.path) as conn:
        row = conn.execute("SELECT * FROM jobs").fetchone()
        types = {
            typeof
            for (typeof,) in conn.execute(
                "SELECT typeof(size) FROM jobs UNION SELECT typeof(attempts) FROM jobs"
            )
        }
    assert all(not isinstance(v, float) for v in row)
    assert types == {"integer"}


# -- status transitions ----------------------------------------------------------------------


def test_status_transitions_stamp_times(store, clock):
    job, _ = make(store)
    clock.advance(seconds=3)
    reading = store.mark_reading(job.job_id)
    assert reading.status == "reading" and reading.attempts == 1
    assert reading.started_at == "2026-10-07T10:15:05Z" and reading.finished_at is None
    clock.advance(seconds=19)
    done = store.mark_done(job.job_id, "/data/jobs/x/result.json")
    assert done.status == "done" and done.finished_at == "2026-10-07T10:15:24Z"
    assert done.result_path == "/data/jobs/x/result.json" and done.error_code is None
    assert store.get(job.job_id) == done

    failed = store.mark_failed(job.job_id, "internal", "ValueError")
    assert failed.status == "failed" and failed.error_code == "internal"
    assert failed.error_message == "ValueError" and failed.result_path is None
    assert store.count("failed") == 1 and store.count("done") == 0

    for call in (
        lambda: store.mark_reading("nope"),
        lambda: store.mark_done("nope", "r"),
        lambda: store.mark_failed("nope", "internal", "X"),
    ):
        with pytest.raises(UnknownJob):
            call()


def test_delete_removes_row_and_folder(store, files):
    job, _ = make(store)
    files.put(job.job_id, b"%PDF-1.4 synthetic", ".pdf")
    files.write_result(job.job_id, "{}")
    assert files.folder(job.job_id).is_dir()
    assert files.delete(job.job_id) and store.delete(job.job_id)
    assert not files.folder(job.job_id).exists() and store.get(job.job_id) is None
    assert not files.delete(job.job_id) and not store.delete(job.job_id)
    assert files.jobs_dir.is_dir()


# -- retention --------------------------------------------------------------------------------


def test_older_than_and_the_sweeper_delete_exactly_the_old_jobs(store, files, clock, caplog):
    old, _ = make(store, request_id="old")
    files.put(old.job_id, b"old", ".pdf")
    store.mark_reading(old.job_id)
    store.mark_done(old.job_id, files.write_result(old.job_id, "{}"))
    clock.advance(hours=23, minutes=59)
    edge, _ = make(store, request_id="edge")
    files.put(edge.job_id, b"edge", ".png")
    clock.advance(minutes=2)  # old is 24h01m old, edge 2 minutes old
    fresh, _ = make(store, request_id="fresh")
    files.put(fresh.job_id, b"fresh", ".jpg")

    assert [j.job_id for j in store.older_than(24)] == [old.job_id]
    assert {j.job_id for j in store.older_than(0)} == {old.job_id, edge.job_id}
    with pytest.raises(TypeError):
        store.older_than(1.5)

    sweeper = Sweeper(store, files, retention_hours=24)
    with caplog.at_level(logging.INFO, logger="billx.platform.store.sweeper"):
        assert sweeper.run_once() == 1
    assert store.get(old.job_id) is None and not files.folder(old.job_id).exists()
    assert store.get(edge.job_id) and files.folder(edge.job_id).is_dir()
    assert store.get(fresh.job_id) and files.folder(fresh.job_id).is_dir()
    assert sweeper.run_once() == 0
    assert "1 expired job(s)" in caplog.text
    assert old.job_id not in caplog.text  # counts only


def test_sweeper_removes_orphan_folders_past_retention(store, files):
    orphan = new_job_id()
    files.put(orphan, b"x", ".pdf")
    young = new_job_id()
    files.put(young, b"y", ".pdf")
    stale = int(time.time()) - 25 * 3600
    os.utime(files.folder(orphan), (stale, stale))
    assert Sweeper(store, files, retention_hours=24).run_once() == 1
    assert not files.folder(orphan).exists() and files.folder(young).is_dir()


def test_sweeper_thread_runs_and_stops(store, files, clock):
    job, _ = make(store)
    clock.advance(hours=25)
    sweeper = Sweeper(store, files, retention_hours=24, interval_seconds=1)
    sweeper.start()
    deadline = time.monotonic() + 5
    while store.get(job.job_id) is not None and time.monotonic() < deadline:
        time.sleep(0.02)
    sweeper.stop(timeout=5)
    assert store.get(job.job_id) is None
    with pytest.raises(ValueError):
        Sweeper(store, files, retention_hours=-1)


# -- restart -------------------------------------------------------------------------------------


def test_requeue_stale_after_a_simulated_crash(tmp_path, clock):
    root = tmp_path / "data"
    first = JobStore(root, clock=clock)
    reading, _ = make(first, request_id="a")
    first.mark_reading(reading.job_id)
    queued, _ = make(first, request_id="b")
    done, _ = make(first, request_id="c")
    first.mark_reading(done.job_id)
    first.mark_done(done.job_id, "r.json")
    failed, _ = make(first, request_id="d")
    first.mark_reading(failed.job_id)
    first.mark_failed(failed.job_id, "internal", "RuntimeError")
    del first  # the process dies here; a new one opens the same file

    second = JobStore(root, clock=clock)
    back = second.requeue_stale()
    assert [j.job_id for j in back] == [reading.job_id, queued.job_id]
    assert all(j.status == "queued" and j.started_at is None for j in back)
    assert second.get(reading.job_id).attempts == 1  # the first attempt stays counted
    assert second.get(done.job_id).status == "done"
    assert second.get(failed.job_id).status == "failed"
    assert second.requeue_stale() == back


# -- threads -----------------------------------------------------------------------------------


def test_store_is_safe_from_several_threads(store):
    errors: list[BaseException] = []

    def work(n: int) -> None:
        try:
            for i in range(25):
                job, created = make(store, request_id=f"t{n}-{i}", sha256=f"{n:02d}{i:02d}" * 16)
                assert created
                store.mark_reading(job.job_id)
                store.mark_done(job.job_id, "r")
                assert store.get(job.job_id).status == "done"
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert errors == []
    assert store.count("done") == 200


# -- file store --------------------------------------------------------------------------------


def test_file_store_layout_and_results(files):
    job_id = new_job_id()
    path = files.put(job_id, b"%PDF-1.4", ".pdf")
    assert path == files.jobs_dir / job_id / "input.pdf" and path.read_bytes() == b"%PDF-1.4"
    assert files.input_path(job_id) == path
    assert files.read_result(job_id) is None
    out = files.write_result(job_id, json.dumps({"ok": True}))
    assert out == files.result_path(job_id) == files.jobs_dir / job_id / "result.json"
    assert files.read_result(job_id) == '{"ok": true}'
    assert not list(files.jobs_dir.joinpath(job_id).glob("*.tmp"))
    assert files.job_ids() == [job_id]
    with pytest.raises(FileNotFoundError):
        files.input_path(new_job_id())
    files.append_feedback(job_id, {"path": "energy.kwh", "right": False, "v": Decimal("1.5")})
    files.append_feedback(job_id, {"path": "totals.net_payable", "right": True})
    lines = (files.folder(job_id) / "feedback.jsonl").read_text().splitlines()
    assert [json.loads(line) for line in lines] == [
        {"path": "energy.kwh", "right": False, "v": "1.5"},
        {"path": "totals.net_payable", "right": True},
    ]
    with pytest.raises(TypeError):
        files.append_feedback(job_id, {"x": 1.5})
    assert len(lines) == 2
    assert files.delete(job_id) and not (files.jobs_dir / job_id).exists()
    with pytest.raises(ValueError):
        files.put(job_id, b"x", "../x")
    with pytest.raises(ValueError):
        files.put(job_id, b"x", "pdf")


@pytest.mark.parametrize(
    "bad",
    ["../x", "..", "/etc", "a/b", "A1B2", "x" * 65, "", "0199b6c2-5f1e-7a3c/../..", "jobs\\x"],
)
def test_file_store_refuses_path_traversal(files, tmp_path, bad):
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    for call in (
        lambda: files.put(bad, b"x", ".pdf"),
        lambda: files.result_path(bad),
        lambda: files.write_result(bad, "{}"),
        lambda: files.read_result(bad),
        lambda: files.delete(bad),
        lambda: files.input_path(bad),
        lambda: files.append_feedback(bad, {}),
    ):
        with pytest.raises(BadJobId):
            call()
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before


def test_file_store_never_follows_a_link_out_of_jobs(files, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("x")
    link = files.jobs_dir / "abcdef"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(BadJobId):
        files.delete("abcdef")
    assert (outside / "keep").exists()


# -- settings ----------------------------------------------------------------------------------


def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BILLX_DATA_DIR", str(tmp_path / "d"))
    s = Settings.from_env()
    assert s.data_dir == tmp_path / "d"
    assert (s.max_jobs, s.queue_limit, s.retention_hours) == (4, 32, 24)
    assert s.sweep_interval_seconds == 600
    monkeypatch.setenv("BILLX_MAX_JOBS", "2")
    monkeypatch.setenv("BILLX_QUEUE_LIMIT", "10")
    monkeypatch.setenv("BILLX_RETENTION_HOURS", "6")
    s = Settings.from_env()
    assert (s.max_jobs, s.queue_limit, s.retention_hours) == (2, 10, 6)
    monkeypatch.setenv("BILLX_MAX_JOBS", "0")
    assert Settings.from_env().max_jobs == 1
    monkeypatch.setenv("BILLX_MAX_JOBS", "8")
    assert Settings.from_env().max_jobs == 8
    monkeypatch.setenv("BILLX_MAX_JOBS", "many")
    with pytest.raises(ValueError):
        Settings.from_env()
