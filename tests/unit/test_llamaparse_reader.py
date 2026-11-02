"""The `llamaparse` reader (LlamaExtract v2) against a mocked LlamaIndex API: request shape,
polling, parsing with citations, budget, failures. No value or key is real."""

from __future__ import annotations

import io
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from PIL import Image

from billx.core.proof import ReadingView, decide
from billx.reader.providers import llamaparse_reader as lp
from billx.reader.providers.base import BudgetExceeded, Page, ProviderError

FAKE_KEY = "llx-test-key-not-real"
FIELDS = [
    {"path": "energy.kvah", "type": "number", "unit": "kVAh", "description": "total kVAh"},
    {"path": "tariff.category", "type": "text", "unit": None, "description": "tariff category"},
    {"path": "totals.net_payable", "type": "number", "unit": "INR", "description": "net payable"},
]
RESULT = {
    "fields": {
        "energy": {"kvah": "12,500"},
        "tariff": {"category": "HV-1"},
        "totals": {"net_payable": 98765.4},
    },
    "meters": [
        {
            "register": "kVAh",
            "tod_slot": "TOD-1 (05 to 11)",
            "consumption": "5,000",
            "open_access": "1,000.5",
            "net": "3,999.5",
        }
    ],
    "lines": [{"label": "Energy Charges", "amount": "54,321.00", "kind": "item"}],
}
META = {
    "fields": {
        "tariff": {
            "category": {
                "citation": [
                    {
                        "page": 2,
                        "matching_text": "HV-1",
                        "bounding_boxes": [{"x": 100, "y": 200, "w": 50, "h": 10}],
                        "page_dimensions": {"width": 1000, "height": 1400},
                    }
                ]
            }
        }
    }
}


def _page() -> Page:
    buf = io.BytesIO()
    Image.new("RGB", (60, 80), "white").save(buf, format="PNG")
    return Page("image/png", buf.getvalue())


def _reader(tmp_path: Path, handler) -> lp.LlamaParseReader:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    lp._sleep = lambda s: None
    return lp.LlamaParseReader(FAKE_KEY, usage_log=tmp_path / "usage.jsonl", client=client)


def _happy(requests: list[httpx.Request], polls: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/beta/files":
            return httpx.Response(200, json={"id": "dfl-1"})
        if request.url.path == "/api/v2/extract" and request.method == "POST":
            return httpx.Response(200, json={"id": "job-1", "status": "PENDING"})
        if request.url.path == "/api/v2/extract/job-1":
            status = polls.pop(0) if polls else "COMPLETED"
            body = {"id": "job-1", "status": status}
            if status == "COMPLETED":
                body.update(
                    extract_result=RESULT,
                    extract_metadata={"field_metadata": {"document_metadata": META}},
                    usage={"credits": 150},
                )
            return httpx.Response(200, json=body)
        return httpx.Response(404)

    return handler


def test_reads_fields_meters_lines_with_citations(tmp_path):
    requests: list[httpx.Request] = []
    reader = _reader(tmp_path, _happy(requests, ["RUNNING"]))
    reading = reader.read_bill(
        [_page(), _page()],
        bill_kind="electricity",
        fields=FIELDS,
        bill_id="a" * 64,
        max_cost_usd=Decimal("1"),
        page_numbers=(2, 3),
    )
    assert reading.fields == {
        "energy.kvah": "12,500",
        "tariff.category": "HV-1",
        "totals.net_payable": "98765.4",
    }
    assert reading.meters[0]["open_access"] == "1,000.5" and reading.meters[0]["net"] == "3,999.5"
    assert reading.lines[0]["label"] == "Energy Charges"
    out = reading.to_output()
    assert out.reader == "llamaparse" and out.method == "vision" and out.family == "llamaindex"
    cited = out.fields["tariff.category"]
    assert cited.page == 3  # page 2 of the uploaded bill is page 3 (0-based) of the file
    assert cited.region is not None and str(cited.region.x) == "0.1000"
    assert reading.usage[0].cost_usd == Decimal("0.150000")  # 150 credits at the config rate
    # the request: the key only in the header, the schema and prompt in the configuration
    upload, create = requests[0], requests[1]
    assert upload.headers["authorization"] == f"Bearer {FAKE_KEY}"
    body = json.loads(create.content)
    cfg = body["configuration"]
    assert body["file_input"] == "dfl-1" and cfg["cite_sources"] is True
    assert cfg["data_schema"]["properties"]["fields"]["properties"]["energy"]["properties"]["kvah"]
    assert "Transcribe only" in cfg["system_prompt"]
    record = json.loads((tmp_path / "usage.jsonl").read_text().splitlines()[-1])
    assert record["status"] == "ok" and FAKE_KEY not in json.dumps(record)
    assert "12,500" not in json.dumps(record)


def test_no_request_above_the_budget(tmp_path):
    requests: list[httpx.Request] = []
    reader = _reader(tmp_path, _happy(requests, []))
    with pytest.raises(BudgetExceeded):
        reader.read_bill(
            [_page()],
            bill_kind="electricity",
            fields=FIELDS,
            bill_id="b" * 64,
            max_cost_usd=Decimal("0.01"),
        )
    assert requests == []


def test_a_failed_job_is_a_provider_error(tmp_path):
    def handler(request):
        if request.url.path == "/api/v1/beta/files":
            return httpx.Response(200, json={"id": "dfl-1"})
        if request.method == "POST":
            return httpx.Response(200, json={"id": "job-1"})
        return httpx.Response(200, json={"status": "FAILED", "error_message": "x"})

    reader = _reader(tmp_path, handler)
    with pytest.raises(ProviderError):
        reader.read_bill(
            [_page()],
            bill_kind="electricity",
            fields=FIELDS,
            bill_id="c" * 64,
            max_cost_usd=Decimal("1"),
        )


def test_a_rate_limit_is_retried(tmp_path):
    calls = {"n": 0}
    happy = _happy([], [])

    def handler(request):
        if request.url.path == "/api/v1/beta/files" and calls["n"] == 0:
            calls["n"] += 1
            return httpx.Response(429)
        return happy(request)

    reader = _reader(tmp_path, handler)
    reading = reader.read_bill(
        [_page()],
        bill_kind="electricity",
        fields=FIELDS,
        bill_id="d" * 64,
        max_cost_usd=Decimal("1"),
    )
    assert reading.fields["tariff.category"] == "HV-1"


def test_an_unauthorised_key_fails_at_once(tmp_path):
    reader = _reader(tmp_path, lambda r: httpx.Response(401))
    with pytest.raises(ProviderError):
        reader.read_bill(
            [_page()],
            bill_kind="electricity",
            fields=FIELDS,
            bill_id="e" * 64,
            max_cost_usd=Decimal("1"),
        )


def test_llamaparse_and_model_a_are_independent_but_never_alone():
    def view(reader, method, family):
        return ReadingView(reader, method, family, "4275")

    both = decide((view("model_a", "vision", "openai"), view("llamaparse", "vision", "llamaindex")))
    assert both.verification == "verified"
    alone = decide((view("llamaparse", "vision", "llamaindex"),))
    assert alone.verification == "unverified"


def test_no_key_no_reader(monkeypatch, tmp_path):
    monkeypatch.delenv("LLAMA_CLOUD_API_KEY", raising=False)
    monkeypatch.setenv("BILLX_ENV_FILE", str(tmp_path / "none.env"))
    assert lp.make_llamaparse() is None


@pytest.mark.ocr
def test_a_scan_passes_with_model_a_and_llamaparse_read_side_by_side(tmp_path):
    """Without Model B, LlamaParse (a third family, read beside Model A) is the second model
    reading that verifies a scan."""
    from billx.platform.api.examples import ReplayModel
    from billx.platform.synth.cli import build
    from billx.reader.pipeline import read_file

    out = tmp_path / "synth"
    build(out, 1)
    scan = sorted(out.glob("avvnl*.scan.pdf"))[0]
    a, _ = ReplayModel.pair([scan])

    class ReplayLlama(ReplayModel):
        def read_bill(self, pages, *, page_numbers=None, **kw):
            assert page_numbers == tuple(range(len(pages)))
            return super().read_bill(pages, **kw)

    c = ReplayLlama("llamaparse", "llamaindex", a.truths)
    env = read_file(scan, allow_cloud_model=True, max_cost_usd=Decimal("1"), model_a=a, model_c=c)
    bill = env.bills[0]
    assert bill.status == "passed", bill.review_reasons
    assert a.calls == 1 and c.calls == 1
    net = next(v for v in bill.fields if v.path == "totals.net_payable")
    assert net.verification == "verified" and "llamaparse" in net.readers
    assert sum(u.cost_usd for u in env.usage) == Decimal("0.02")


def test_an_unaccepted_key_is_named_in_the_usage_record(tmp_path):
    reader = _reader(tmp_path, lambda r: httpx.Response(401))
    with pytest.raises(ProviderError) as err:
        reader.read_bill(
            [_page()],
            bill_kind="electricity",
            fields=FIELDS,
            bill_id="f" * 64,
            max_cost_usd=Decimal("1"),
        )
    assert "LlamaUnauthorized" in str(err.value)
    record = json.loads((tmp_path / "usage.jsonl").read_text().splitlines()[-1])
    assert record["status"] == "failed" and record["error"] == "LlamaUnauthorized"
