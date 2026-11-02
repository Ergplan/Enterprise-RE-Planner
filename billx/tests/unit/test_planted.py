"""Planted misreads: one printed value changed on the page, the truth unchanged beside it, every
check in the planted table covered, and reader-misread fixtures that really disagree."""

import json
import random
import re
from decimal import Decimal
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from billx.core.normalize import normalise
from billx.platform.synth import planted
from billx.platform.synth.cli import build
from billx.platform.synth.values import avvnl, field_types, gas, letter

ELECTRICITY_CHECKS = {"G02", "G03", "G05", "G07", "G09", "G15", "G16", "G18", "G19", "G20"}
GAS_CHECKS = {"GG02", "GG03", "GG04", "GG05"}


def _no_float(s):
    raise AssertionError(f"float in JSON: {s}")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(), parse_float=_no_float)


def _text(pdf: Path) -> str:
    doc = pdfium.PdfDocument(str(pdf))
    try:
        return re.sub(r"\s+", " ", " ".join(p.get_textpage().get_text_range() for p in doc))
    finally:
        doc.close()


@pytest.fixture(scope="module")
def out(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("planted")
    build(d, 1)
    return d


@pytest.fixture(scope="module")
def entries(out) -> list[dict]:
    return _load(out / "manifest.json")["files"]


@pytest.fixture(scope="module")
def planted_truths(out, entries) -> list[dict]:
    return [_load(out / e["truth"]) for e in entries if e["planted"]]


def _clean_truth(out: Path, t: dict) -> dict:
    return _load(out / t["derived_from"].replace(".pdf", ".truth.json"))


def test_every_planted_file_lists_exactly_one_planted_item(entries, planted_truths):
    assert len(planted_truths) == 48
    for e, t in zip([e for e in entries if e["planted"]], planted_truths, strict=True):
        p = t["planted"]
        assert isinstance(p, dict)
        assert set(p) >= {"path", "check", "original_printed", "planted_printed", "kind"}
        assert p["kind"] == "printed_inconsistency"
        assert p["check"] == e["check"]
        assert e["file"].endswith(f".planted-{p['check']}.pdf")
        assert e["input_kind"] == "digital_pdf" and e["variant"] == f"planted-{p['check']}"
        assert p["original_printed"] != p["planted_printed"]
        assert t["file"] == e["file"]


def test_the_truth_keeps_the_clean_bills_values(out, planted_truths):
    for t in planted_truths:
        clean = _clean_truth(out, t)
        assert t["fields"] == clean["fields"]
        assert t["printed"] == clean["printed"]
        assert t["charges"] == clean["charges"]
        assert t.get("tod") == clean.get("tod")
        assert t["document_type"] == clean["document_type"]


def test_the_page_shows_the_planted_string_and_not_the_original(out, planted_truths):
    for t in planted_truths:
        p = t["planted"]
        text, clean_text = _text(out / t["file"]), _text(out / t["derived_from"])
        assert text != clean_text, t["file"]
        assert p["planted_printed"] in text, t["file"]
        if p["check"] == "G19":
            start, end = p["original_printed"], p["planted_printed"]
            if t["layout"].startswith("avvnl"):
                assert f"Reading Date (Present) {start}" in text
                assert f"Reading Date (Past) {end}" in text
            else:
                assert f"Reading Period : {end} to {start}" in text
        elif p["original_printed"] in p["planted_printed"]:  # G20: "-" prefixed
            assert p["check"] == "G20"
            assert text.count(p["original_printed"]) == clean_text.count(p["original_printed"])
            assert text.count(p["planted_printed"]) == clean_text.count(p["planted_printed"]) + 1
        else:
            # exactly one occurrence replaced: the same string may legitimately be printed
            # elsewhere (a register total is also a charge line's quantity)
            assert text.count(p["original_printed"]) == clean_text.count(p["original_printed"]) - 1
            assert text.count(p["planted_printed"]) == clean_text.count(p["planted_printed"]) + 1
            # the change is one digit at one position (the planted string is as long)
            assert len(p["planted_printed"]) == len(p["original_printed"])
            diff = [
                i
                for i, (a, b) in enumerate(
                    zip(p["original_printed"], p["planted_printed"], strict=True)
                )
                if a != b
            ]
            if p["check"] != "G18":
                assert len(diff) == 1 and p["original_printed"][diff[0]].isdigit(), t["file"]


def test_every_check_has_a_planted_file(planted_truths):
    by_type: dict[str, set[str]] = {}
    for t in planted_truths:
        by_type.setdefault(t["document_type"], set()).add(t["planted"]["check"])
    assert by_type["electricity_bill"] == ELECTRICITY_CHECKS
    assert by_type["gas_bill"] == GAS_CHECKS
    per_layout: dict[str, int] = {}
    for t in planted_truths:
        per_layout[t["layout"]] = per_layout.get(t["layout"], 0) + 1
    assert per_layout == {
        "avvnl-ht-synth-v1": 20,
        "pvvnl-hv2-synth-v1": 20,
        "gas-citygas-synth-v1": 4,
        "gas-gridsales-synth-v1": 4,
    }


def test_planted_values_sit_where_the_check_looks(out, planted_truths):
    for t in planted_truths:
        p, c = t["planted"], t["planted"]["check"]
        if c in ("G02", "G03", "G15", "G16"):
            assert p["path"].startswith("tod.")
        if c in ("G05", "G20", "GG04"):
            assert re.fullmatch(r"charges\[\d+\]\.amount", p["path"])
        if c == "G16":
            kwh = Decimal(t["tod"]["kwh_total"]["consumption"])
            assert Decimal(p["planted_printed"].replace(",", "")) < kwh
        if c == "G18":
            assert normalise(p["original_printed"], "month") == t["fields"]["period.bill_month"]
            y0, m0 = map(int, t["fields"]["period.to"].split("-")[:2])
            y1, m1 = map(int, normalise(p["planted_printed"], "month").split("-"))
            assert (y1 * 12 + m1) - (y0 * 12 + m0) == 3  # three months after the period
        if c == "G20":
            line = t["charges"][int(p["path"][8:].split("]")[0])]
            assert line["code"] == "electricity_duty" and Decimal(line["amount"]) > 0
            assert p["planted_printed"] == "-" + p["original_printed"]
        if c == "GG03":
            a, b = Decimal(p["original_printed"]), Decimal(p["planted_printed"])
            assert abs(b - a) / a >= Decimal("0.01")
        if c in ("G07", "G09", "GG05", "GG02"):
            a = Decimal(p["original_printed"].replace(",", ""))
            b = Decimal(p["planted_printed"].replace(",", ""))
            assert abs(a - b) > 1


def test_same_seed_same_planted_bytes(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    build(a, 5), build(b, 5)
    ma, mb = _load(a / "manifest.json"), _load(b / "manifest.json")
    assert ma == mb
    for e in ma["files"]:
        if e["planted"]:
            assert (a / e["file"]).read_bytes() == (b / e["file"]).read_bytes()
            assert (a / e["truth"]).read_text() == (b / e["truth"]).read_text()
        if "misreads" in e:
            assert (a / e["misreads"]).read_text() == (b / e["misreads"]).read_text()


def test_misread_fixtures_disagree_with_the_truth(out, entries):
    fixtures = [(e, _load(out / e["misreads"])) for e in entries if "misreads" in e]
    assert len(fixtures) == 4
    types = field_types("electricity")
    for e, fx in fixtures:
        truth = _load(out / e["truth"])
        assert fx["file"] == e["file"] and fx["truth"] == e["truth"]
        assert set(fx["misreads"]) == set(truth["printed"])
        for path, m in fx["misreads"].items():
            assert m["printed"] == truth["printed"][path]
            assert m["kind"] in ("digit_changed", "group_dropped", "character_confused")
            got, want = normalise(m["misread"], types[path]), normalise(m["printed"], types[path])
            assert got is not None and want is not None and got != want, (e["file"], path)
            if m["kind"] == "digit_changed":
                assert len(m["misread"]) == len(m["printed"])
            if m["kind"] == "group_dropped":
                assert m["misread"].count(",") == m["printed"].count(",") - 1


def test_digit_helpers():
    assert planted.change_leading_digit("2,52,30,114.71") == "3,52,30,114.71"
    assert planted.change_leading_digit("9123.00") == "8123.00"
    assert planted.change_leading_digit("0.73") == "0.83"
    first = list(planted.candidates("2,60,310.00"))[:4]
    assert first == ["1,60,310.00", "3,60,310.00", "4,60,310.00", "5,60,310.00"]
    assert "0,60,310.00" == list(planted.candidates("2,60,310.00"))[-1]
    got = planted.smallest_change_of_at_least("5083.077", Decimal("0.01"))
    assert got == "5023.077"  # 60 / 5083 = 1.2%, the smallest one-digit change over 1%
    with pytest.raises(ValueError):
        planted.smallest_change_of_at_least("1", Decimal("100"))


def test_variants_leave_the_clean_dict_untouched():
    bill = avvnl(random.Random("x"), 1)
    before = json.dumps(bill, default=str, sort_keys=True)
    got = list(planted.variants(bill))
    assert [c for c, _, _ in got] == sorted(ELECTRICITY_CHECKS, key=lambda c: int(c[1:]))
    assert json.dumps(bill, default=str, sort_keys=True) == before
    assert len(list(planted.variants(gas(random.Random("y"), "a")))) == 4
    assert list(planted.variants(letter(random.Random("z")))) == []
