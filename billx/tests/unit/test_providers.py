"""The providers package apart from the HTTP calls: ModelReading and to_output(), the JSON
parsing that keeps numbers as text, the page bands and downscaling, the prompt files, the
factories (None without a key), and the config entries the readers depend on."""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from billx.core.schema import UsageRecord
from billx.core.settings import load_config
from billx.reader.providers import images
from billx.reader.providers.anthropic_reader import AnthropicReader
from billx.reader.providers.base import (
    LINE_KEYS,
    METER_KEYS,
    ModelReading,
    Page,
    load_json,
    make_model_a,
    make_model_b,
    make_prefill_provider,
    model_a_spec,
    model_b_spec,
    parse_fields,
    parse_items,
    parse_lines,
    parse_notes,
    render_prompt,
    render_template,
)
from billx.reader.providers.openai_reader import OpenAIReader
from billx.reader.providers.usage import cost
from billx.reader.read.consensus import RawRead, ReaderOutput

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "billx" / "reader" / "prompts"
FAKE_KEY = "sk-test-not-a-real-key-123"  # secrets-check: allow (a fake key)
FIELDS = [
    {"path": "energy.kwh", "type": "number", "unit": "kWh"},
    {"path": "totals.net_payable", "type": "number", "unit": "INR"},
]


@pytest.fixture(autouse=True)
def no_model_env(monkeypatch):
    for name in ("BILLX_ANTHROPIC_API_KEY", "BILLX_MODEL_B"):
        monkeypatch.delenv(name, raising=False)


def png(width: int, height: int) -> Page:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (255, 255, 255)).save(buf, format="PNG")
    return Page("image/png", buf.getvalue())


def jpeg(width: int, height: int) -> Page:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (255, 255, 255)).save(buf, format="JPEG")
    return Page("image/jpeg", buf.getvalue())


def _size(page: Page) -> tuple[int, int]:
    return Image.open(io.BytesIO(page.data)).size


# ModelReading ------------------------------------------------------------------------------


def test_to_output_is_a_reader_output_of_raw_reads():
    reading = ModelReading(
        reader_name="model_a",
        family="openai",
        model_spec="openai:gpt-6.1-sol",
        model_id="gpt-6.1-sol",
        prompt_version="read_bill_v1",
        fields={"totals.net_payable": "2,43,58,156.60", "energy.kwh": "24,69,000"},
        meters=[dict.fromkeys(METER_KEYS) | {"register": "kWh", "present": "12,345.6"}],
        lines=[dict.fromkeys(LINE_KEYS) | {"label": "Energy Charge", "amount": "1,60,48,500.00"}],
        extraction_notes=["faint print"],
        usage=[
            UsageRecord(
                provider="openai",
                model="openai:gpt-6.1-sol",
                purpose="read_bill",
                input_tokens=1,
                output_tokens=1,
                cost_usd=Decimal("0.000025"),
            )
        ],
    )
    out = reading.to_output()
    assert isinstance(out, ReaderOutput)
    assert out.reader == "model_a" and out.method == "vision" and out.family == "openai"
    assert out.model_id == "gpt-6.1-sol" and out.prompt_version == "read_bill_v1"
    assert out.fields == {
        "totals.net_payable": RawRead("2,43,58,156.60"),
        "energy.kwh": RawRead("24,69,000"),
    }
    assert out.meters[0]["present"] == "12,345.6" and out.meters[0]["past"] is None
    assert out.lines[0]["amount"] == "1,60,48,500.00"
    assert out.meters[0] is not reading.meters[0]  # copies: consensus may not alter the reading


# parsing -----------------------------------------------------------------------------------


def test_json_numbers_stay_literal_text():
    obj = load_json('{"a": 1234.50, "b": 980, "c": -0.10, "d": 1e3}')
    assert obj == {"a": "1234.50", "b": "980", "c": "-0.10", "d": "1e3"}
    assert not any(isinstance(v, float) for v in obj.values())


def test_code_fences_are_tolerated_and_prose_is_not():
    assert load_json('```json\n{"a": "1"}\n```') == {"a": "1"}
    assert load_json('```\n{"a": "1"}```') == {"a": "1"}
    with pytest.raises(ValueError):
        load_json("the total is 1,234.50")
    with pytest.raises(ValueError):
        load_json("")


def test_parse_fields_keeps_known_non_empty_strings_only():
    obj = {"energy.kwh": "  24,69,000 ", "totals.net_payable": None, "x": "1", "y": True}
    assert parse_fields(obj, FIELDS + [{"path": "y", "type": "text"}]) == {
        "energy.kwh": "24,69,000"
    }
    with pytest.raises(ValueError):
        parse_fields(["not", "an", "object"], FIELDS)


def test_parse_items_fills_missing_keys_and_drops_bad_rows():
    rows = parse_items(
        [
            {"register": "kWh", "present": "1", "extra": "dropped"},
            {"present": "2"},  # no register
            "not a row",
            {"register": "kVAh", "present": {"nested": "x"}},
        ],
        METER_KEYS,
        required=("register",),
    )
    assert rows == [
        dict.fromkeys(METER_KEYS) | {"register": "kWh", "present": "1"},
        dict.fromkeys(METER_KEYS) | {"register": "kVAh"},
    ]
    assert parse_items({"not": "a list"}, METER_KEYS) == []


def test_parse_lines_requires_label_and_amount_and_normalises_kind_and_stage():
    rows = parse_lines(
        [
            {"label": "Energy Charge", "amount": "1.00", "kind": "Item", "stage": "CURRENT"},
            {"label": "Total", "amount": "1.00", "kind": "grand total", "stage": "later"},
            {"label": "No amount", "amount": None},
            {"amount": "5.00"},
        ]
    )
    assert [r["label"] for r in rows] == ["Energy Charge", "Total"]
    assert rows[0]["kind"] == "item" and rows[0]["stage"] == "current"
    assert rows[1]["kind"] is None and rows[1]["stage"] is None
    assert set(rows[0]) == set(LINE_KEYS)


def test_parse_notes_keeps_strings_only():
    assert parse_notes(["faint print", "", None, 3]) == ["faint print"]
    assert parse_notes("not a list") == []


# images ------------------------------------------------------------------------------------


def test_three_bands_cover_the_page_and_overlap_their_neighbours():
    boxes = images.band_boxes(900)
    assert len(boxes) == 3
    assert boxes[0][0] == 0 and boxes[-1][1] == 900
    for (_, bottom), (top, _) in zip(boxes, boxes[1:], strict=False):
        overlap = bottom - top
        assert abs(overlap - 900 / 3 * images.BAND_OVERLAP) <= 1
    assert all(bottom - top >= 300 for top, bottom in boxes)


def test_bands_are_crops_of_the_page_in_its_own_format():
    page = png(60, 90)
    out = images.bands(page, 0)
    assert [b.position for b in out] == ["top", "middle", "bottom"]
    assert all(b.page_index == 0 and b.page.mime == "image/png" for b in out)
    assert all(_size(b.page)[0] == 60 for b in out)
    assert sum(_size(b.page)[1] for b in out) > 90  # the overlap
    jpg = images.bands(jpeg(60, 90), 1)
    assert all(b.page.mime == "image/jpeg" for b in jpg)
    with pytest.raises(ValueError):
        images.bands(Page("image/png", b"not an image"), 0)


def test_downscale_only_beyond_the_longest_side():
    small = png(50, 40)
    assert images.downscale(small, 2000) is small
    assert _size(images.downscale(png(300, 60), 100)) == (100, 20)
    assert _size(images.downscale(png(60, 300), 100)) == (20, 100)
    assert images.downscale(jpeg(300, 60), 100).mime == "image/jpeg"
    raw = Page("image/png", b"not an image")
    assert images.downscale(raw, 100) is raw


# prompts -----------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["read_bill_v1", "read_fields_v1"])
def test_field_prompts_list_paths_and_types_only(name):
    text = render_prompt(name, FIELDS, "electricity")
    assert "{{" not in text
    assert "- energy.kwh: number, kWh" in text
    assert "- totals.net_payable: number, INR" in text
    assert "electricity" in text
    assert "never" in text.lower() and "calculate" in text.lower()


def test_lines_prompt_has_the_lines_slot():
    text = render_template("read_lines_v1", LINES="- Energy Charges | Energy Charge")
    assert "{{" not in text and "- Energy Charges | Energy Charge" in text


def test_prompt_files_are_versioned_and_prefill_v1_is_untouched():
    names = {p.name for p in PROMPTS.glob("*.md")}
    assert {"prefill_v1.md", "read_bill_v1.md", "read_fields_v1.md", "read_lines_v1.md"} <= names
    prefill = (PROMPTS / "prefill_v1.md").read_text()
    assert "{{FIELDS}}" in prefill and "{{BILL_KIND}}" in prefill
    assert "band" not in prefill  # Stage 0's text, as it was


# factories and config ----------------------------------------------------------------------


def test_factories_return_none_without_keys(tmp_path):
    assert make_model_a() is None
    assert make_model_b() is None
    assert make_prefill_provider(tmp_path / "usage.jsonl") is None


def test_factories_build_the_readers_from_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("BILLX_OPENAI_API_KEY", FAKE_KEY)
    fake_b = "sk-ant-test-not-a-real-key"  # secrets-check: allow (a fake key)
    monkeypatch.setenv("BILLX_ANTHROPIC_API_KEY", fake_b)
    a = make_model_a(tmp_path / "a.jsonl")
    b = make_model_b(tmp_path / "b.jsonl")
    assert isinstance(a, OpenAIReader) and a.family == "openai" and a.reader_name == "model_a"
    assert isinstance(b, AnthropicReader) and b.family == "anthropic"
    assert b.reader_name == "model_b"
    assert a.model_spec == model_a_spec() and b.model_spec == model_b_spec()
    assert a.usage_log == tmp_path / "a.jsonl" and b.usage_log == tmp_path / "b.jsonl"
    # the default usage log lives under the data folder
    assert str(make_model_b().usage_log).startswith(str(tmp_path / "billx-data"))
    # a spec of the other family is not this reader
    monkeypatch.setenv("BILLX_MODEL_B", "openai:some-model")
    assert make_model_b() is None
    monkeypatch.setenv("BILLX_MODEL_A", "anthropic:some-model")
    assert make_model_a() is None


def test_configured_models_have_prices_and_the_image_limit_exists():
    for spec in (model_a_spec(), model_b_spec()):
        assert cost(spec, 1_000_000, 1_000_000) > 0
    providers = load_config("providers.yaml")
    assert int(providers["max_image_edge_px"]) >= 1000
    prices = load_config("prices.yaml")
    assert prices["placeholder"] is True  # still marked until the team confirms them


def test_hints_reach_the_prompt_and_an_empty_list_says_none():
    text = render_prompt("read_bill_v2", FIELDS, "electricity", ("The account number is the KNO.",))
    assert "- The account number is the KNO." in text and "{{HINTS}}" not in text
    assert "- (none)" in render_prompt("read_fields_v2", FIELDS, "electricity")


def test_v4_prompts_carry_each_fields_meaning_and_v3_does_not():
    fields = [
        {
            "path": "open_access.re_kwh",
            "type": "number",
            "unit": "kWh",
            "description": "renewable units set off against consumption",
        }
    ]
    v4 = render_prompt("read_bill_v4", fields, "electricity")
    assert "- open_access.re_kwh: number, kWh: renewable units set off" in v4
    v3 = render_prompt("read_bill_v3", fields, "electricity")
    assert "renewable units set off" not in v3 and "- open_access.re_kwh: number, kWh" in v3
    assert "renewable units set off" in render_prompt("read_fields_v4", fields, "electricity")
