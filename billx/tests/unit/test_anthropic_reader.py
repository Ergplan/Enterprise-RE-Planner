"""Model B (Anthropic Messages API) against a mocked HTTP layer: the page-plus-bands request,
no other reader's value in any request, budget refusals, 429 waits, usage records.

The anthropic SDK (1.x) is built on httpx2; its client takes `http_client`, so every test
hands it an httpx2.MockTransport whose handler raises on any request it did not expect.
Nothing here can reach the network.
"""

from __future__ import annotations

import io
import json
from decimal import Decimal

import httpx2
import pytest
from PIL import Image

from billx.core.schema import UsageRecord
from billx.reader.providers import anthropic_reader
from billx.reader.providers.anthropic_reader import AnthropicReader, line_lines
from billx.reader.providers.base import BudgetExceeded, Page, ProviderError
from billx.reader.providers.usage import cost

SPEC = "anthropic:claude-sonnet-5-5"
FAKE_KEY = "sk-ant-test-not-a-real-key-123"  # secrets-check: allow (a fake key)
SHA = "cd" * 32
FIELDS = [
    {"path": "utility.name", "type": "text"},
    {"path": "energy.kwh", "type": "number", "unit": "kWh"},
    {"path": "totals.net_payable", "type": "number", "unit": "INR"},
]
#: A value another reader might hold for these fields and lines. It must never reach a
#: request to Model B (5.1: never shown another reader's values).
PLANTED = "9,87,65,432.10"


@pytest.fixture(autouse=True)
def no_model_b_env(monkeypatch):
    for name in ("BILLX_ANTHROPIC_API_KEY", "BILLX_MODEL_B"):
        monkeypatch.delenv(name, raising=False)


def png(width: int = 60, height: int = 90) -> Page:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (255, 255, 255)).save(buf, format="PNG")
    return Page("image/png", buf.getvalue())


PAGES = [png()]


def _ok(text: str, input_tokens: int = 3000, output_tokens: int = 150) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-5-5",
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        },
    )


def _error(status: int, kind: str) -> httpx2.Response:
    return httpx2.Response(
        status, json={"type": "error", "error": {"type": kind, "message": "synthetic"}}
    )


FIELDS_ANSWER = json.dumps(
    {
        "utility.name": "SYNTHETIC POWER DISCOM",
        "energy.kwh": 1234567,  # a JSON number: kept as its literal text
        "totals.net_payable": "2,43,58,156.60",
        "unknown.path": "dropped",
    }
)
LINES_ANSWER = json.dumps(
    {
        "lines": [
            {
                "group": "Energy Charges",
                "label": "Energy Charge",
                "quantity": "24,69,000",
                "rate": 6.5,
                "unit": "kWh",
                "amount": "1,60,48,500.00",
            },
            {
                "group": None,
                "label": "Not on the page",
                "quantity": None,
                "rate": None,
                "unit": None,
                "amount": None,
            },
        ]
    }
)


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(anthropic_reader, "_sleep", calls.append)
    return calls


def _reader(tmp_path, responses: list[httpx2.Response]):
    """A reader whose transport answers the scripted responses in order and raises on any
    request beyond them (no test may fall through to the network)."""
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) > len(responses):
            raise AssertionError("unexpected HTTP request")
        return responses[len(requests) - 1]

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    reader = AnthropicReader(SPEC, FAKE_KEY, usage_log=tmp_path / "usage.jsonl", http_client=client)
    return reader, requests


def _usage(tmp_path):
    return [json.loads(x) for x in (tmp_path / "usage.jsonl").read_text().splitlines()]


def _body(request) -> dict:
    return json.loads(request.content)


def _image_blocks(body: dict) -> list[dict]:
    return [b for b in body["messages"][0]["content"] if b["type"] == "image"]


def _decoded_sizes(body: dict) -> list[tuple[int, int]]:
    import base64

    sizes = []
    for block in _image_blocks(body):
        img = Image.open(io.BytesIO(base64.b64decode(block["source"]["data"])))
        sizes.append(img.size)
    return sizes


# read_fields -------------------------------------------------------------------------------


def test_read_fields_returns_printed_strings_and_a_usage_record(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [_ok(FIELDS_ANSWER)])
    reading = reader.read_fields(
        PAGES, bill_kind="electricity", fields=FIELDS, bill_id=SHA, max_cost_usd=Decimal("1")
    )
    assert reading.fields == {
        "utility.name": "SYNTHETIC POWER DISCOM",
        "energy.kwh": "1234567",
        "totals.net_payable": "2,43,58,156.60",
    }
    assert all(isinstance(v, str) for v in reading.fields.values())
    assert reading.meters == [] and reading.lines == []
    assert reading.reader_name == "model_b" and reading.family == "anthropic"
    assert reading.model_id == "claude-sonnet-5-5" and reading.prompt_version == "read_fields_v4"
    assert reading.usage == [
        UsageRecord(
            provider="anthropic",
            model=SPEC,
            purpose="read_fields",
            input_tokens=3000,
            output_tokens=150,
            cost_usd=cost(SPEC, 3000, 150),
        )
    ]
    assert sleeps == [] and len(requests) == 1

    out = reading.to_output()
    assert out.reader == "model_b" and out.method == "vision" and out.family == "anthropic"
    assert out.fields["totals.net_payable"].raw == "2,43,58,156.60"

    (record,) = _usage(tmp_path)
    assert record["status"] == "ok" and record["attempts"] == 1
    assert record["purpose"] == "read_fields" and record["prompt"] == "read_fields_v4"
    assert record["pages"] == 1 and record["images"] == 4
    assert record["input_tokens"] == 3000 and record["output_tokens"] == 150
    assert record["cost_usd"] == str(cost(SPEC, 3000, 150))
    assert record["fields_returned"] == 3
    log_text = (tmp_path / "usage.jsonl").read_text()
    for secret in ("2,43,58,156.60", "SYNTHETIC POWER DISCOM", "1234567", FAKE_KEY):
        assert secret not in log_text


def test_read_fields_request_has_the_page_and_three_bands_per_page(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [_ok(FIELDS_ANSWER)])
    pages = [png(60, 90), png(80, 120)]
    reader.read_fields(
        pages, bill_kind="electricity", fields=FIELDS, bill_id=SHA, max_cost_usd=Decimal("1")
    )
    body = _body(requests[0])
    assert body["model"] == "claude-sonnet-5-5"
    assert body["max_tokens"] == reader.max_output_tokens
    assert "temperature" not in body  # none configured for this model id
    assert requests[0].headers["x-api-key"] == FAKE_KEY  # to the SDK only, never logged
    assert len(_image_blocks(body)) == 4 * len(pages)
    assert {b["source"]["media_type"] for b in _image_blocks(body)} == {"image/png"}
    sizes = _decoded_sizes(body)
    assert sizes[0] == (60, 90) and sizes[4] == (80, 120)  # the whole pages
    for page_w, page_h, start in ((60, 90, 1), (80, 120, 5)):
        band_sizes = sizes[start : start + 3]
        assert all(w == page_w for w, _ in band_sizes)
        third = page_h / 3
        assert all(third <= h <= third * 1.15 + 1 for _, h in band_sizes)
    # the prompt is the last block, and lists paths and types only
    last = body["messages"][0]["content"][-1]
    assert last["type"] == "text"
    assert "energy.kwh: number, kWh" in last["text"]
    assert "totals.net_payable: number, INR" in last["text"]


def test_no_other_readers_value_reaches_model_b(tmp_path, sleeps):
    """The field dicts may come from a result that already holds readings; whatever else is
    in them, only path, type and unit are rendered. Same for the lines' figures."""
    reader, requests = _reader(tmp_path, [_ok(FIELDS_ANSWER), _ok(LINES_ANSWER)])
    fields = [
        {**f, "value": PLANTED, "printed": PLANTED, "readings": [{"raw": PLANTED}]} for f in FIELDS
    ]
    reader.read_fields(
        PAGES, bill_kind="electricity", fields=fields, bill_id=SHA, max_cost_usd=Decimal("1")
    )
    lines = [
        {
            "group": "Energy Charges",
            "label": "Energy Charge",
            "quantity": PLANTED,
            "rate": PLANTED,
            "amount": PLANTED,
            "kind": "item",
        }
    ]
    reader.read_lines(PAGES, lines=lines, bill_id=SHA, max_cost_usd=Decimal("1"))
    for request in requests:
        assert PLANTED not in request.content.decode("utf-8")
    assert line_lines(lines) == "- Energy Charges | Energy Charge"


def test_budget_refusal_makes_no_request_and_records_it(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [])
    with pytest.raises(BudgetExceeded) as exc:
        reader.read_fields(
            PAGES,
            bill_kind="electricity",
            fields=FIELDS,
            bill_id=SHA,
            max_cost_usd=Decimal("0.000001"),
        )
    assert requests == [] and sleeps == []
    (record,) = _usage(tmp_path)
    assert record["status"] == "refused" and record["reason"] == "budget"
    assert record["attempts"] == 0 and record["cost_usd"] == "0"
    assert Decimal(record["cost_estimate_usd"]) > Decimal("0.000001")
    assert exc.value.usage == (
        UsageRecord(
            provider="anthropic",
            model=SPEC,
            purpose="read_fields",
            input_tokens=0,
            output_tokens=0,
            cost_usd=Decimal(0),
        ),
    )


def test_estimate_counts_four_images_per_page(tmp_path, sleeps):
    """The worst case assumes every image costs `tokens_per_image`: a budget that affords one
    image per page does not afford the page plus its bands."""
    reader, requests = _reader(tmp_path, [])
    one_image = cost(SPEC, 1600, reader.max_output_tokens)
    with pytest.raises(BudgetExceeded):
        reader.read_fields(
            PAGES, bill_kind="electricity", fields=FIELDS, bill_id=SHA, max_cost_usd=one_image
        )
    assert requests == []


def test_429_waits_the_configured_time_then_retries_once(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [_error(429, "rate_limit_error"), _ok(FIELDS_ANSWER)])
    reading = reader.read_fields(
        PAGES, bill_kind="electricity", fields=FIELDS, bill_id=SHA, max_cost_usd=Decimal("1")
    )
    assert reading.fields["energy.kwh"] == "1234567"
    assert sleeps == [reader.cfg["rate_limit_wait_seconds"]] == [60]
    assert len(requests) == 2
    (record,) = _usage(tmp_path)
    assert record["status"] == "ok" and record["attempts"] == 2


def test_429_retries_are_bounded_with_backoff(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [_error(429, "rate_limit_error")] * 3)
    with pytest.raises(ProviderError) as exc:
        reader.read_fields(
            PAGES, bill_kind="electricity", fields=FIELDS, bill_id=SHA, max_cost_usd=Decimal("1")
        )
    assert len(requests) == 3 and sleeps == [60, 120]
    assert "RateLimitError" in str(exc.value) and FAKE_KEY not in str(exc.value)
    (record,) = _usage(tmp_path)
    assert record["status"] == "failed" and record["error"] == "RateLimitError"
    assert exc.value.usage[0].input_tokens == 0


def test_overloaded_and_server_errors_retry_with_the_short_wait(tmp_path, sleeps):
    reader, requests = _reader(
        tmp_path,
        [_error(529, "overloaded_error"), _error(500, "api_error"), _ok(FIELDS_ANSWER)],
    )
    reader.read_fields(
        PAGES, bill_kind="electricity", fields=FIELDS, bill_id=SHA, max_cost_usd=Decimal("1")
    )
    assert sleeps == [5, 10] and len(requests) == 3


def test_client_error_is_not_retried(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [_error(400, "invalid_request_error")])
    with pytest.raises(ProviderError):
        reader.read_fields(
            PAGES, bill_kind="electricity", fields=FIELDS, bill_id=SHA, max_cost_usd=Decimal("1")
        )
    assert len(requests) == 1 and sleeps == []
    assert _usage(tmp_path)[0]["error"] == "BadRequestError"


def test_non_json_answer_is_a_provider_error_with_a_usage_record(tmp_path, sleeps):
    reader, _ = _reader(tmp_path, [_ok("The net payable is 2,43,58,156.60")])
    with pytest.raises(ProviderError) as exc:
        reader.read_fields(
            PAGES, bill_kind="electricity", fields=FIELDS, bill_id=SHA, max_cost_usd=Decimal("1")
        )
    assert "2,43,58,156.60" not in str(exc.value)
    (record,) = _usage(tmp_path)
    assert record["status"] == "unparseable" and record["input_tokens"] == 3000
    assert exc.value.usage[0].input_tokens == 3000


def test_fenced_json_is_accepted(tmp_path, sleeps):
    reader, _ = _reader(tmp_path, [_ok("```json\n" + FIELDS_ANSWER + "\n```")])
    reading = reader.read_fields(
        PAGES, bill_kind="electricity", fields=FIELDS, bill_id=SHA, max_cost_usd=Decimal("1")
    )
    assert reading.fields["totals.net_payable"] == "2,43,58,156.60"


def test_configured_temperature_is_sent_and_pages_are_downscaled(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [_ok(FIELDS_ANSWER)])
    reader.cfg["temperature"] = {SPEC: 0}
    reader.cfg["max_image_edge_px"] = 100
    reader.read_fields(
        [png(300, 60)],
        bill_kind="electricity",
        fields=FIELDS,
        bill_id=SHA,
        max_cost_usd=Decimal("1"),
    )
    body = _body(requests[0])
    assert body["temperature"] == 0
    assert _decoded_sizes(body)[0] == (100, 20)


def test_undecodable_page_is_refused_before_any_request(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [])
    with pytest.raises(ProviderError) as exc:
        reader.read_fields(
            [Page("image/png", b"not an image")],
            bill_kind="electricity",
            fields=FIELDS,
            bill_id=SHA,
            max_cost_usd=Decimal("1"),
        )
    assert requests == [] and "not a decodable image" in str(exc.value)
    assert not (tmp_path / "usage.jsonl").exists()  # no call was planned


# read_lines --------------------------------------------------------------------------------


def test_read_lines_returns_the_found_lines_figures_as_printed(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [_ok(LINES_ANSWER)])
    lines = [
        {"group": "Energy Charges", "label": "Energy Charge"},
        {"group": None, "label": "Not on the page"},
    ]
    reading = reader.read_lines(PAGES, lines=lines, bill_id=SHA, max_cost_usd=Decimal("1"))
    assert reading.prompt_version == "read_lines_v1" and reading.fields == {}
    assert reading.lines == [
        {
            "group": "Energy Charges",
            "label": "Energy Charge",
            "quantity": "24,69,000",
            "rate": "6.5",
            "unit": "kWh",
            "amount": "1,60,48,500.00",
        }
    ]
    body = _body(requests[0])
    assert len(_image_blocks(body)) == 4
    prompt = body["messages"][0]["content"][-1]["text"]
    assert "- Energy Charges | Energy Charge" in prompt
    assert "- (no heading) | Not on the page" in prompt
    out = reading.to_output()
    assert out.lines[0]["amount"] == "1,60,48,500.00" and out.fields == {}
    (record,) = _usage(tmp_path)
    assert record["purpose"] == "read_lines" and record["lines_returned"] == 1


def test_read_lines_budget_refusal(tmp_path, sleeps):
    reader, requests = _reader(tmp_path, [])
    with pytest.raises(BudgetExceeded):
        reader.read_lines(
            PAGES, lines=[{"label": "Energy Charge"}], bill_id=SHA, max_cost_usd=Decimal("0")
        )
    assert requests == []
    assert _usage(tmp_path)[0]["purpose"] == "read_lines"
