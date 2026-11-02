"""Model A (OpenAI Responses API) against a mocked HTTP layer: the studio pre-fill and the
whole-bill read_bill; retries, 429 waits, budget refusals, usage records. The openai SDK is
built on httpx2, so an httpx2.MockTransport stands in for the network."""

import io
import json
from decimal import Decimal

import httpx2
import pytest
from PIL import Image

from billx.core.schema import UsageRecord
from billx.reader.providers import openai_reader
from billx.reader.providers.base import (
    BudgetExceeded,
    Page,
    ProviderError,
    make_model_a,
    make_prefill_provider,
)
from billx.reader.providers.openai_reader import OpenAIReader, parse_values
from billx.reader.providers.usage import cost

FIELDS = [
    {"path": "utility", "type": "text"},
    {"path": "energy.kwh", "type": "number", "unit": "kWh"},
    {"path": "totals.net_payable", "type": "number", "unit": "INR"},
]
FAKE_KEY = "sk-test-not-a-real-key-123"  # secrets-check: allow (a fake key)
SHA = "ab" * 32
PAGES = [Page("image/png", b"\x89PNG synthetic")]


def _ok(text: str, input_tokens=1000, output_tokens=200):
    return httpx2.Response(
        200,
        json={
            "id": "resp_1",
            "object": "response",
            "created_at": 0,
            "model": "gpt-6.1-sol",
            "status": "completed",
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "output": [
                {
                    "type": "message",
                    "id": "msg_1",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": text, "annotations": []}],
                }
            ],
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        },
    )


def _rate_limited():
    return httpx2.Response(429, json={"error": {"message": "slow down", "type": "rate_limit"}})


ANSWER = json.dumps(
    {"utility": "SYNTHETIC POWER DISCOM", "energy.kwh": "1,234.50", "totals.net_payable": None}
)


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(openai_reader, "_sleep", calls.append)
    return calls


def _reader(tmp_path, responses):
    requests = []

    def handler(request):
        requests.append(request)
        return responses[min(len(requests), len(responses)) - 1]

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    reader = OpenAIReader(
        "openai:gpt-6.1-sol", FAKE_KEY, usage_log=tmp_path / "usage.jsonl", http_client=client
    )
    return reader, requests


def _usage(tmp_path):
    return [json.loads(x) for x in (tmp_path / "usage.jsonl").read_text().splitlines()]


def test_success_returns_printed_strings_and_records_usage_without_values(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [_ok(ANSWER)])
    values = reader.prefill(PAGES, FIELDS, bill_kind="electricity", bill_id=SHA)
    assert values == {"utility": "SYNTHETIC POWER DISCOM", "energy.kwh": "1,234.50"}
    assert sleeps == [] and len(requests) == 1

    body = json.loads(requests[0].content)
    assert body["model"] == "gpt-6.1-sol"
    assert body["text"] == {"format": {"type": "json_object"}}
    assert body["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,")
    assert "energy.kwh: number, kWh" in body["input"][0]["content"][0]["text"]

    (record,) = _usage(tmp_path)
    assert record["status"] == "ok" and record["attempts"] == 1
    assert record["bill_id"] == SHA and record["model"] == "openai:gpt-6.1-sol"
    assert record["prompt"] == "prefill_v1"
    assert record["input_tokens"] == 1000 and record["output_tokens"] == 200
    assert record["cost_usd"] == str(cost("openai:gpt-6.1-sol", 1000, 200))
    assert isinstance(record["cost_estimate_usd"], str)
    assert record["prices_placeholder"] is True
    log_text = (tmp_path / "usage.jsonl").read_text()
    for secret in ("1,234.50", "SYNTHETIC POWER DISCOM", FAKE_KEY):
        assert secret not in log_text


def test_429_waits_60_seconds_then_retries(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [_rate_limited(), _ok(ANSWER)])
    values = reader.prefill(PAGES, FIELDS, bill_kind="electricity", bill_id=SHA)
    assert values["energy.kwh"] == "1,234.50"
    assert sleeps == [60] and len(requests) == 2
    assert _usage(tmp_path)[0]["attempts"] == 2


def test_429_retries_are_bounded_with_backoff(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [_rate_limited()])
    with pytest.raises(ProviderError) as exc:
        reader.prefill(PAGES, FIELDS, bill_kind="electricity", bill_id=SHA)
    assert len(requests) == 3  # max_attempts in config/providers.yaml
    assert sleeps == [60, 120]
    assert "RateLimitError" in str(exc.value) and FAKE_KEY not in str(exc.value)
    (record,) = _usage(tmp_path)
    assert record["status"] == "failed" and record["attempts"] == 3
    assert record["error"] == "RateLimitError"


def test_429_for_an_empty_account_is_not_retried(tmp_path, sleeps):
    """Waiting does not refill credit: fail at once instead of holding the studio 3 minutes."""
    no_credit = httpx2.Response(
        429,
        json={
            "error": {
                "message": "You have no credits remaining.",
                "type": "insufficient_quota",
                "code": "credit_balance_exhausted",
            }
        },
    )
    reader, requests = _reader(tmp_path, [no_credit])
    with pytest.raises(ProviderError):
        reader.prefill(PAGES, FIELDS, bill_kind="electricity", bill_id=SHA)
    assert len(requests) == 1 and sleeps == []


def test_server_error_retries_with_the_short_wait(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [httpx2.Response(500, json={}), _ok(ANSWER)])
    reader.prefill(PAGES, FIELDS, bill_kind="electricity", bill_id=SHA)
    assert sleeps == [5] and len(requests) == 2


def test_client_error_is_not_retried(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [httpx2.Response(400, json={"error": {"message": "x"}})])
    with pytest.raises(ProviderError):
        reader.prefill(PAGES, FIELDS, bill_kind="electricity", bill_id=SHA)
    assert len(requests) == 1 and sleeps == []
    assert _usage(tmp_path)[0]["error"] == "BadRequestError"


def test_estimate_above_the_ceiling_makes_no_call(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [_ok(ANSWER)])
    reader.cfg["max_cost_usd_per_call"] = "0.000001"
    with pytest.raises(ProviderError):
        reader.prefill(PAGES, FIELDS, bill_kind="electricity", bill_id=SHA)
    assert requests == []
    assert _usage(tmp_path)[0]["status"] == "refused_over_ceiling"


def test_unparseable_answer_fails_without_echoing_it(tmp_path, sleeps):
    reader, _ = _reader(tmp_path, [_ok("the total is 1,234.50")])
    with pytest.raises(ProviderError) as exc:
        reader.prefill(PAGES, FIELDS, bill_kind="electricity", bill_id=SHA)
    assert "1,234.50" not in str(exc.value)
    assert _usage(tmp_path)[0]["status"] == "unparseable"


def test_json_numbers_keep_their_printed_text_never_float():
    text = '{"energy.kwh": 1234.50, "totals.net_payable": 980, "utility": null, "x": "1"}'
    assert parse_values(text, FIELDS) == {"energy.kwh": "1234.50", "totals.net_payable": "980"}


def test_provider_needs_a_key(tmp_path, monkeypatch):
    assert make_prefill_provider(tmp_path / "usage.jsonl") is None
    monkeypatch.setenv("BILLX_OPENAI_API_KEY", FAKE_KEY)
    assert isinstance(make_prefill_provider(tmp_path / "usage.jsonl"), OpenAIReader)
    monkeypatch.setenv("BILLX_MODEL_A", "anthropic:some-model")
    assert make_prefill_provider(tmp_path / "usage.jsonl") is None  # Stage 0: OpenAI only


def test_key_is_read_from_the_env_file(tmp_path, monkeypatch):
    env = tmp_path / "test.env"
    env.write_text(f"# synthetic\nBILLX_OPENAI_API_KEY={FAKE_KEY}\n")
    monkeypatch.setenv("BILLX_ENV_FILE", str(env))
    reader = make_prefill_provider(tmp_path / "usage.jsonl")
    assert reader is not None and reader.model_spec == "openai:gpt-6.1-sol"


# read_bill (Stage 1.2): the whole bill as a ModelReading ------------------------------------

BILL_FIELDS = [
    {"path": "consumer.account_number", "type": "identifier"},
    {"path": "energy.kwh", "type": "number", "unit": "kWh"},
    {"path": "totals.net_payable", "type": "number", "unit": "INR"},
]
BILL_ANSWER = json.dumps(
    {
        "fields": {
            "consumer.account_number": "1234567890",
            "energy.kwh": 2469000,  # a JSON number: kept as its literal text
            "totals.net_payable": "2,43,58,156.60",
            "period.from": "01-04-2026",  # not asked for: dropped
        },
        "meters": [
            {
                "register": "kWh",
                "tod_slot": None,
                "present": "12345.6",
                "past": "11111.1",
                "difference": "1234.5",
                "multiplying_factor": 2000,
                "consumption": "24,69,000",
            },
            {"present": "no register: dropped"},
        ],
        "lines": [
            {
                "group": "Energy Charges",
                "label": "Energy Charge",
                "kind": "item",
                "stage": "current",
                "quantity": "24,69,000",
                "rate": "6.50",
                "unit": "kWh",
                "amount": "1,60,48,500.00",
            },
            {
                "group": "Totals",
                "label": "Net Payable",
                "kind": "subtotal",
                "stage": "current",
                "quantity": None,
                "rate": None,
                "unit": None,
                "amount": "2,43,58,156.60",
            },
            {"group": "Totals", "label": "Previous bill", "kind": "info", "amount": None},
        ],
        "extraction_notes": ["a stamp covers part of the due date"],
    }
)


def _png(width: int = 60, height: int = 90) -> Page:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (255, 255, 255)).save(buf, format="PNG")
    return Page("image/png", buf.getvalue())


def _strict_reader(tmp_path, responses):
    """Like _reader, but a request beyond the scripted responses raises."""
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) > len(responses):
            raise AssertionError("unexpected HTTP request")
        return responses[len(requests) - 1]

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    reader = OpenAIReader(
        "openai:gpt-6.1-sol", FAKE_KEY, usage_log=tmp_path / "usage.jsonl", http_client=client
    )
    return reader, requests


def _read_bill(reader, pages=None, budget="1"):
    return reader.read_bill(
        pages or [_png()],
        bill_kind="electricity",
        fields=BILL_FIELDS,
        bill_id=SHA,
        max_cost_usd=Decimal(budget),
    )


def test_read_bill_parses_fields_meters_lines_with_numbers_as_text(tmp_path, sleeps):
    reader, requests = _strict_reader(tmp_path, [_ok(BILL_ANSWER, 5000, 900)])
    reading = _read_bill(reader)
    assert reading.reader_name == "model_a" and reading.family == "openai"
    assert reading.model_id == "gpt-6.1-sol" and reading.prompt_version == "read_bill_v5"
    assert reading.fields == {
        "consumer.account_number": "1234567890",
        "energy.kwh": "2469000",
        "totals.net_payable": "2,43,58,156.60",
    }
    assert reading.meters == [
        {
            "register": "kWh",
            "tod_slot": None,
            "present": "12345.6",
            "past": "11111.1",
            "difference": "1234.5",
            "multiplying_factor": "2000",
            "consumption": "24,69,000",
            "open_access": None,
            "net": None,
        }
    ]
    assert [ln["label"] for ln in reading.lines] == ["Energy Charge", "Net Payable"]
    assert reading.lines[0]["rate"] == "6.50" and reading.lines[1]["kind"] == "subtotal"
    assert reading.extraction_notes == ["a stamp covers part of the due date"]
    assert reading.usage == [
        UsageRecord(
            provider="openai",
            model="openai:gpt-6.1-sol",
            purpose="read_bill",
            input_tokens=5000,
            output_tokens=900,
            cost_usd=cost("openai:gpt-6.1-sol", 5000, 900),
        )
    ]

    def walk(x):
        if isinstance(x, dict):
            return all(walk(v) for v in x.values())
        if isinstance(x, list):
            return all(walk(v) for v in x)
        return not isinstance(x, float)

    assert walk(reading.fields) and walk(reading.meters) and walk(reading.lines)

    out = reading.to_output()
    assert out.reader == "model_a" and out.method == "vision" and out.family == "openai"
    assert out.fields["totals.net_payable"].raw == "2,43,58,156.60"
    assert out.fields["energy.kwh"].page is None
    assert (
        out.meters[0]["consumption"] == "24,69,000" and out.lines[1]["amount"] == "2,43,58,156.60"
    )

    body = json.loads(requests[0].content)
    assert body["text"] == {"format": {"type": "json_object"}}
    assert body["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,")
    prompt = body["input"][0]["content"][0]["text"]
    assert "- totals.net_payable: number, INR" in prompt and '"lines"' in prompt
    assert "2,43,58,156.60" in prompt  # the example of a grouped figure in the prompt text

    (record,) = _usage(tmp_path)
    assert record["status"] == "ok" and record["purpose"] == "read_bill"
    assert record["prompt"] == "read_bill_v5" and record["images"] == 1
    assert record["fields_returned"] == 3 and record["meters_returned"] == 1
    assert record["lines_returned"] == 2
    log_text = (tmp_path / "usage.jsonl").read_text()
    for secret in ("1234567890", "2469000", "24,69,000", "1,60,48,500.00", FAKE_KEY):
        assert secret not in log_text


def test_read_bill_budget_refusal_makes_no_request(tmp_path, sleeps):
    reader, requests = _strict_reader(tmp_path, [])
    with pytest.raises(BudgetExceeded) as exc:
        _read_bill(reader, budget="0.000001")
    assert requests == [] and sleeps == []
    (record,) = _usage(tmp_path)
    assert record["status"] == "refused" and record["reason"] == "budget"
    assert record["max_cost_usd"] == "0.000001"
    assert exc.value.usage[0].cost_usd == Decimal(0) and exc.value.usage[0].purpose == "read_bill"


def test_read_bill_over_ceiling_is_a_provider_error_not_a_budget_refusal(tmp_path, sleeps):
    reader, requests = _strict_reader(tmp_path, [])
    reader.cfg["max_cost_usd_per_call"] = "0.000001"
    with pytest.raises(ProviderError) as exc:
        _read_bill(reader, budget="1")
    assert not isinstance(exc.value, BudgetExceeded)
    assert requests == [] and _usage(tmp_path)[0]["reason"] == "ceiling"


def test_read_bill_429_waits_then_retries_once(tmp_path, sleeps):
    reader, requests = _strict_reader(tmp_path, [_rate_limited(), _ok(BILL_ANSWER)])
    reading = _read_bill(reader)
    assert reading.fields["energy.kwh"] == "2469000"
    assert sleeps == [60] and len(requests) == 2
    assert _usage(tmp_path)[0]["attempts"] == 2


def test_read_bill_non_json_answer_fails_with_a_usage_record(tmp_path, sleeps):
    reader, _ = _strict_reader(tmp_path, [_ok("Net payable 2,43,58,156.60", 700, 20)])
    with pytest.raises(ProviderError) as exc:
        _read_bill(reader)
    assert "2,43,58,156.60" not in str(exc.value)
    (record,) = _usage(tmp_path)
    assert record["status"] == "unparseable" and record["input_tokens"] == 700
    assert exc.value.usage[0].output_tokens == 20


def test_read_bill_answer_that_is_a_list_is_unparseable(tmp_path, sleeps):
    reader, _ = _strict_reader(tmp_path, [_ok('[{"fields": {}}]')])
    with pytest.raises(ProviderError):
        _read_bill(reader)
    assert _usage(tmp_path)[0]["status"] == "unparseable"


def test_read_bill_downscales_pages_beyond_the_configured_edge(tmp_path, sleeps):
    import base64

    reader, requests = _strict_reader(tmp_path, [_ok(BILL_ANSWER)])
    reader.cfg["max_image_edge_px"] = 100
    _read_bill(reader, pages=[_png(300, 60)])
    url = json.loads(requests[0].content)["input"][0]["content"][1]["image_url"]
    data = base64.b64decode(url.split(",", 1)[1])
    assert Image.open(io.BytesIO(data)).size == (100, 20)


def test_factory_builds_model_a_with_a_key(tmp_path, monkeypatch):
    assert make_model_a(tmp_path / "usage.jsonl") is None
    monkeypatch.setenv("BILLX_OPENAI_API_KEY", FAKE_KEY)
    reader = make_model_a(tmp_path / "usage.jsonl")
    assert isinstance(reader, OpenAIReader) and reader.reader_name == "model_a"
