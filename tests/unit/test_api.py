"""The HTTP API against contract 1.0 (esgos-1.0 mode) and 1.1 (esgos-1.1 mode), with the
engine stubbed: every call, every error code of contract section 8, idempotency, kind
text, the wait option, and the no-values-in-logs rule (invariant 9)."""

from __future__ import annotations

import json
import logging
import threading
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from billx.core.normalize import normalise
from billx.core.schema import (
    BillResult,
    Envelope,
    FileInfo,
    PageText,
    Reading,
    Region,
    TextEnvelope,
    Word,
    make_value,
)
from billx.platform.api.app import ApiSettings, create_app
from billx.reader.pipeline import ReadError

TOKEN = "test-token-0123456789"
PLANTED = "7,77,777.77"  # a distinctive value that must never appear in a log or metric


def _value(path, raw, ft="number", unit=None):
    rs = tuple(
        Reading(reader=r, method=m, family=fam, raw=raw, normalised=normalise(raw, ft), page=0)
        for r, m, fam in (("text_layer", "text_layer", None), ("model_a", "vision", "openai"))
    )
    return make_value(path, ft, rs, unit=unit)


def _envelope(sha="cd" * 32, passed=True):
    bill = BillResult(
        index=0,
        pages=(1,),
        bill_type="electricity",
        document_type="electricity_bill",
        route="template",
        fields=(
            _value("consumer.account_number", "994927801935", "identifier"),
            _value("totals.net_payable", PLANTED, unit="INR"),
        ),
        passed=passed,
        status="passed" if passed else "needs_review",
        review_reasons=() if passed else ("insufficient_arithmetic",),
        accepted=passed,
        accepted_by="engine" if passed else None,
    )
    return Envelope(
        contract_version="1.1",
        file=FileInfo(sha256=sha, pages=1, media_type="application/pdf"),
        bills=(bill,),
        seconds=Decimal("0.5"),
    )


class FakeEngine:
    def __init__(self):
        self.calls = []
        self.fail_with: str | None = None
        self.block = threading.Event()
        self.block.set()

    def read_file(self, path, **kw):
        self.block.wait(5)
        self.calls.append((Path(path).name, kw))
        if self.fail_with:
            raise ReadError(self.fail_with, self.fail_with)
        return _envelope()

    def read_text_file(self, path):
        page = PageText(
            page=1,
            text="SYNTHETIC TEXT",
            words=(
                Word(
                    text="SYNTHETIC",
                    region=Region(
                        x=Decimal("0.1"), y=Decimal("0.1"), w=Decimal("0.2"), h=Decimal("0.02")
                    ),
                ),
            ),
        )
        return TextEnvelope(
            contract_version="1.0",
            file=FileInfo(sha256="ef" * 32, pages=1, media_type="application/pdf"),
            pages=(page,),
            seconds=Decimal("0.1"),
        )


@pytest.fixture
def api(tmp_path):
    def make(mode="esgos-1.1", **overrides):
        engine = FakeEngine()
        settings = ApiSettings(mode=mode, token=TOKEN, data_dir=tmp_path / mode, **overrides)
        app = create_app(
            settings,
            read_file=engine.read_file,
            read_text_file=engine.read_text_file,
            providers=lambda: (None, None),
        )
        client = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})
        client.__enter__()
        return client, engine

    made = []

    def factory(*a, **kw):
        c, e = make(*a, **kw)
        made.append(c)
        return c, e

    yield factory
    for c in made:
        c.__exit__(None, None, None)


def _pdf_bytes(n=1):
    return b"%PDF-1.4 synthetic " + bytes(n)


def _submit(client, options: dict, data=None, name="bill.pdf", content_type="application/pdf"):
    return client.post(
        "/v1/jobs",
        files={"file": (name, data or _pdf_bytes(), content_type)},
        data={"options": json.dumps(options)},
    )


def _wait_done(client, job_id, tries=50):
    for _ in range(tries):
        r = client.get(f"/v1/jobs/{job_id}")
        if r.json()["status"] in ("done", "failed"):
            return r.json()
        threading.Event().wait(0.05)
    raise AssertionError("job did not finish")


BASE = {"request_id": "file_1", "product": "esgos", "allow_cloud_model": False}


def test_health_and_auth(api):
    client, _ = api()
    r = client.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["contract_version"] == "1.1"
    assert body["schema_version"] == "2.0" and body["cloud_model"] == "not_configured"
    assert set(body) == {
        "status",
        "engine_version",
        "contract_version",
        "schema_version",
        "profiles_version",
        "ocr",
        "cloud_model",
    }
    bare = TestClient(client.app)
    r = bare.get("/v1/health")
    assert r.status_code == 401 and r.json() == {
        "error": {"code": "unauthorised", "message": "missing or wrong token"}
    }
    r = bare.get("/v1/health", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_a_job_runs_end_to_end_in_1_0_mode(api):
    client, engine = api("esgos-1.0")
    r = _submit(client, BASE, name="x.pdf")
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    assert r.json() == {"job_id": job_id, "status": "queued"}
    assert r.headers["X-Request-Id"]
    body = _wait_done(client, job_id)
    assert body["status"] == "done" and body["error"] is None and body["request_id"] == "file_1"
    result = body["result"]
    assert result["contract_version"] == "1.0"
    bill = result["bills"][0]
    assert "status" not in bill and "flags" not in bill  # no 1.1 additions in 1.0
    assert bill["fields"]["totals"]["net_payable"]["value"] == "777777.77"
    assert (
        engine.calls[0][1]["contract"] == "1.0" and engine.calls[0][1]["allow_cloud_model"] is False
    )


def test_1_1_mode_adds_status_and_accepted(api):
    client, _ = api()
    job_id = _submit(client, BASE).json()["job_id"]
    bill = _wait_done(client, job_id)["result"]["bills"][0]
    assert (
        bill["status"] == "passed" and bill["accepted"] is True and bill["accepted_by"] == "engine"
    )
    assert bill["fields"]["totals"]["net_payable"]["verification"] == "verified"


def test_1_1_option_in_1_0_mode_is_bad_request(api):
    client, _ = api("esgos-1.0")
    r = _submit(client, {**BASE, "wait": True})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"


def test_option_errors(api):
    client, _ = api()
    r = _submit(client, {"product": "esgos", "allow_cloud_model": False})
    assert (r.status_code, r.json()["error"]["code"]) == (400, "bad_request")
    r = _submit(client, {**BASE, "allow_cloud_model": True})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "invalid_options")
    r = _submit(client, {**BASE, "kind": "picture"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "invalid_options")
    r = client.post(
        "/v1/jobs", files={"file": ("x.pdf", b"x", "application/pdf")}, data={"options": "not json"}
    )
    assert r.status_code == 400


def test_unsupported_type_and_too_large(api):
    client, _ = api()
    r = _submit(client, BASE, data=b"<html>", name="bill.html", content_type="text/html")
    assert (r.status_code, r.json()["error"]["code"]) == (415, "unsupported_type")
    r = _submit(client, BASE, data=b"x" * (25 * 1024 * 1024 + 1))
    assert (r.status_code, r.json()["error"]["code"]) == (413, "too_large")


def test_request_id_is_idempotent_and_conflicts_on_a_different_file(api):
    client, engine = api()
    first = _submit(client, BASE).json()["job_id"]
    again = _submit(client, BASE)
    assert again.status_code == 202 and again.json()["job_id"] == first
    other = _submit(client, BASE, data=_pdf_bytes(2))
    assert (other.status_code, other.json()["error"]["code"]) == (409, "conflict")
    _wait_done(client, first)
    assert len(engine.calls) == 1


def test_get_unknown_delete_and_feedback(api):
    client, _ = api()
    assert client.get("/v1/jobs/nope").status_code == 404
    job_id = _submit(client, BASE).json()["job_id"]
    _wait_done(client, job_id)
    r = client.post(
        "/v1/feedback",
        json={
            "job_id": job_id,
            "file_sha256": "cd" * 32,
            "bill_index": 0,
            "corrections": [
                {"path": "energy.kwh", "engine_value": "12400", "final_value": "12460"}
            ],
        },
    )
    assert r.status_code == 202
    assert client.delete(f"/v1/jobs/{job_id}").status_code == 204
    assert client.get(f"/v1/jobs/{job_id}").status_code == 404
    assert client.delete(f"/v1/jobs/{job_id}").status_code == 404


def test_a_failed_read_is_a_failed_job_with_the_code(api):
    client, engine = api()
    engine.fail_with = "unsupported_type"
    job_id = _submit(client, BASE).json()["job_id"]
    body = _wait_done(client, job_id)
    assert (
        body["status"] == "failed"
        and body["error"]["code"] == "unsupported_type"
        and body["result"] is None
    )


def test_kind_text_returns_pages_and_words(api):
    client, _ = api()
    job_id = _submit(client, {**BASE, "kind": "text"}).json()["job_id"]
    result = _wait_done(client, job_id)["result"]
    assert "bills" not in result and result["pages"][0]["text"] == "SYNTHETIC TEXT"
    assert result["pages"][0]["words"][0]["region"]["x"] == "0.1"


def test_wait_returns_the_result_when_the_job_finishes_in_time(api):
    client, _ = api()
    r = _submit(client, {**BASE, "wait": True})
    assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["result"]["bills"]


def test_queue_full_is_429_with_retry_after(api):
    client, engine = api(max_jobs=1, queue_limit=1)
    engine.block.clear()
    ids = []
    try:
        for i in range(2):
            r = _submit(client, {**BASE, "request_id": f"f{i}"})
            assert r.status_code == 202, r.text
            ids.append(r.json()["job_id"])
        r = _submit(client, {**BASE, "request_id": "f_over"})
        assert r.status_code == 429 and r.json()["error"]["code"] == "busy"
        assert int(r.headers["Retry-After"]) >= 5
    finally:
        engine.block.set()
    for job_id in ids:
        _wait_done(client, job_id)


def test_metrics_carry_counts_only(api):
    client, _ = api()
    job_id = _submit(client, BASE).json()["job_id"]
    _wait_done(client, job_id)
    r = client.get("/metrics")
    assert r.status_code == 200 and "billx_jobs_total" in r.text
    assert PLANTED not in r.text and "777777" not in r.text


def test_no_value_in_logs_metrics_or_errors(api, caplog):
    caplog.set_level(logging.DEBUG)
    client, engine = api()
    job_id = _submit(client, BASE).json()["job_id"]
    _wait_done(client, job_id)
    engine.fail_with = "unreadable"
    failed = _submit(client, {**BASE, "request_id": "f2"}).json()["job_id"]
    body = _wait_done(client, failed)
    client.get("/v1/jobs/nope")
    haystack = caplog.text + client.get("/metrics").text + json.dumps(body["error"])
    for needle in (PLANTED, "777777", "994927801935"):
        assert needle not in haystack


def test_request_id_header_is_echoed_and_trace_logged(api, caplog):
    caplog.set_level(logging.INFO)
    client, _ = api()
    r = client.get(
        "/v1/health",
        headers={
            "X-Request-Id": "req-abc",
            "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
        },
    )
    assert r.headers["X-Request-Id"] == "req-abc"
    assert "request_id=req-abc" in caplog.text and "0af7651916cd43dd8448eb211c80319c" in caplog.text


def test_health_in_1_0_mode_reports_contract_1_0(api):
    client, _ = api("esgos-1.0")
    assert client.get("/v1/health").json()["contract_version"] == "1.0"
