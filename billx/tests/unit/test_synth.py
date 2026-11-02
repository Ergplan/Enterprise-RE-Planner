"""`billx synth`: determinism, exact arithmetic in every truth file, text layers, scans, photos."""

import json
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageChops

from billx.cli import main
from billx.platform.synth.cli import build
from billx.platform.synth.values import AVVNL_RATES, PVVNL_RATES, field_paths, indian

CENT = Decimal("0.01")
EXPECTED_TYPES = {
    "avvnl-ht-synth-v1": "electricity_bill",
    "pvvnl-hv2-synth-v1": "electricity_bill",
    "gas-citygas-synth-v1": "gas_bill",
    "gas-gridsales-synth-v1": "gas_bill",
    "water-municipal-synth-v1": "water_bill",
    "telecom-fictional-synth-v1": "telecom_bill",
    "invoice-supplies-synth-v1": "other_invoice",
    "receipt-store-synth-v1": "not_a_bill",
    "letter-synth-v1": "not_a_bill",
}


def _no_float(s):
    raise AssertionError(f"float in truth JSON: {s}")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(), parse_float=_no_float)


@pytest.fixture(scope="module")
def out(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("synth")
    build(d, 1)
    return d


@pytest.fixture(scope="module")
def truths(out) -> list[dict]:
    return [_load(out / e["truth"]) for e in _load(out / "manifest.json")["files"]]


def _text(pdf: Path) -> str:
    doc = pdfium.PdfDocument(str(pdf))
    try:
        return " ".join(page.get_textpage().get_text_range() for page in doc)
    finally:
        doc.close()


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s)


def _d(s: str) -> Decimal:
    return Decimal(s)


def test_indian_grouping():
    assert indian(Decimal("26949346.81")) == "2,69,49,346.81"
    assert indian(Decimal("-561632.80")) == "-5,61,632.80"
    assert indian(Decimal("999.50")) == "999.50"
    assert indian(Decimal("1000")) == "1,000"


def test_cli_writes_manifest(tmp_path):
    assert main(["synth", "--out", str(tmp_path), "--seed", "3"]) == 0
    files = _load(tmp_path / "manifest.json")["files"]
    listed = {e["file"] for e in files} | {e["truth"] for e in files} | {"manifest.json"}
    listed |= {e["misreads"] for e in files if "misreads" in e}
    assert listed == {p.name for p in tmp_path.iterdir()}
    assert all(e["truth"] == e["file"].rsplit(".", 1)[0] + ".truth.json" for e in files)
    assert sum(e["planted"] for e in files) == 48
    assert {e["file"] for e in files if "misreads" in e} == {
        e["file"]
        for e in files
        if e["document_type"] == "electricity_bill" and e["variant"] == "clean"
    }


def test_cli_without_planted(tmp_path):
    assert main(["synth", "--out", str(tmp_path), "--seed", "3", "--no-planted"]) == 0
    files = _load(tmp_path / "manifest.json")["files"]
    assert not any(e["planted"] for e in files) and not any("misreads" in e for e in files)
    assert not list(tmp_path.glob("*planted*")) and not list(tmp_path.glob("*misreads*"))


def test_same_seed_same_output_other_seed_other_values(tmp_path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    build(a, 7), build(b, 7), build(c, 8)
    ma, mb = _load(a / "manifest.json"), _load(b / "manifest.json")
    assert ma == mb  # every file byte-identical, by sha256
    for e in ma["files"]:
        assert (a / e["truth"]).read_text() == (b / e["truth"]).read_text()
        if e["input_kind"] == "digital_pdf":
            assert _text(a / e["file"]) == _text(b / e["file"])
    first = ma["files"][0]["truth"]
    assert _load(a / first)["fields"] != _load(c / first)["fields"]


def test_no_float_anywhere(out):
    for path in out.glob("*.json"):
        _load(path)  # raises on any float literal


def test_fields_follow_the_contract_list(truths):
    for t in truths:
        kind = {"electricity_bill": "electricity", "gas_bill": "gas"}.get(t["document_type"])
        assert list(t["fields"]) == (field_paths(kind) if kind else [])


def test_document_types(out, truths):
    assert {t["layout"] for t in truths} == set(EXPECTED_TYPES)
    for t in truths:
        assert t["document_type"] == EXPECTED_TYPES[t["layout"]]
    kinds = {(t["document_type"], t["input_kind"]) for t in truths}
    assert ("gas_bill", "photo_jpeg") in kinds and ("not_a_bill", "photo_jpeg") in kinds


def test_charge_lines(truths):
    for t in truths:
        for x in t["charges"]:
            if x["quantity"] is not None:
                product = (_d(x["quantity"]) * _d(x["rate"])).quantize(CENT, ROUND_HALF_UP)
                assert product == _d(x["amount"]), (t["file"], x["label"])
            assert _d(x["printed"]["amount"].replace(",", "")) == _d(x["amount"])
        total = sum((_d(x["amount"]) for x in t["charges"]), Decimal(0))
        if t["document_type"] == "electricity_bill":
            assert total == _d(t["fields"]["totals.current_charges"])
        elif t["document_type"] == "gas_bill":
            assert total == _d(t["fields"]["totals.amount"])
        elif t["charges"]:
            assert total == _d(t["facts"]["amount"]["value"])


def test_electricity_arithmetic(truths):
    bills = [t for t in truths if t["document_type"] == "electricity_bill"]
    assert len(bills) == 28 + 40  # 4 bills x (digital, scan, 5 photos) + 4 x 10 planted
    for t in bills:
        f, tod = t["fields"], t["tod"]
        for reg in ("kwh", "kvah"):
            for r in tod[reg] + [tod[f"{reg}_total"]]:
                assert _d(r["present"]) - _d(r["past"]) == _d(r["difference"])
                assert _d(r["difference"]) * _d(r["mf"]) == _d(r["consumption"])
                for k, printed in r["printed"].items():
                    assert _d(printed.replace(",", "")) == _d(r[k])
            for k in ("difference", "consumption"):
                slots = sum((_d(r[k]) for r in tod[reg]), Decimal(0))
                assert slots == _d(tod[f"{reg}_total"][k])
        for kwh, kvah in zip(tod["kwh"], tod["kvah"], strict=True):
            assert kwh["slot"] == kvah["slot"] and _d(kvah["consumption"]) >= _d(kwh["consumption"])
        assert _d(f["energy.kwh"]) == _d(tod["kwh_total"]["consumption"])
        assert _d(f["energy.kvah"]) == _d(tod["kvah_total"]["consumption"])
        assert _d(f["energy.kvah"]) >= _d(f["energy.kwh"])
        net = _d(f["totals.current_charges"]) + _d(f["totals.arrears"])
        assert net == _d(f["totals.net_payable"])
        demand = next(x for x in t["charges"] if x["code"] == "demand_charge")
        floor = (_d(f["demand.contract_kva"]) * Decimal("0.75")).quantize(CENT)
        assert _d(demand["quantity"]) == max(_d(f["demand.max_kva"]), floor)
        start, end = date.fromisoformat(f["period.from"]), date.fromisoformat(f["period.to"])
        assert start < end
        y, m = map(int, f["period.bill_month"].split("-"))
        months = (y * 12 + m) - (end.year * 12 + end.month)
        assert (y, m) >= (start.year, start.month) and months <= 1
        assert date.fromisoformat(f["period.due_date"]) > end


def test_tariff_rates_are_the_profiles_params(truths):
    """The energy and demand rates are fixed so the draft profiles can carry them as params
    (T01 to T05); FPPCA stays random because it is notice-based."""
    assert AVVNL_RATES == {"energy_charge": Decimal("7.30"), "demand_charge": Decimal("330.00")}
    assert PVVNL_RATES == {"demand_charge": Decimal("300.00"), "energy_charge": Decimal("7.10")}
    fppca = set()
    for t in (t for t in truths if t["document_type"] == "electricity_bill"):
        rates = {x["code"]: _d(x["rate"]) for x in t["charges"] if x["code"] != "cess"}
        expected = AVVNL_RATES if t["layout"].startswith("avvnl") else PVVNL_RATES
        for code, rate in expected.items():
            assert rates[code] == rate, (t["file"], code)
        fppca.add(rates["fppca"])
    assert len(fppca) > 1


def test_gas_arithmetic(truths):
    for t in (t for t in truths if t["document_type"] == "gas_bill"):
        f, r = t["fields"], t["readings"]
        assert _d(r["present"]) - _d(r["previous"]) == _d(f["volume.scm"])
        assert _d(f["readings.current"]) - _d(f["readings.previous"]) == _d(f["volume.scm"])
        mmbtu = _d(f["volume.scm"]) * _d(f["gas.gcv_kcal_per_scm"]) / Decimal(252000)
        assert mmbtu.quantize(Decimal("0.001"), ROUND_HALF_UP) == _d(f["energy.mmbtu"])
        assert date.fromisoformat(f["period.from"]) < date.fromisoformat(f["period.to"])


def test_printed_numbers_equal_values(truths):
    for t in truths:
        for path, printed in t["printed"].items():
            value = t["fields"][path]
            if re.fullmatch(r"-?[\d,]+(\.\d+)?", printed) and re.fullmatch(r"-?\d+(\.\d+)?", value):
                assert _d(printed.replace(",", "")) == _d(value), (t["file"], path)


def test_digital_text_layer_has_every_printed_value(out, truths):
    digital = [t for t in truths if t["input_kind"] == "digital_pdf" and "planted" not in t]
    assert len(digital) == 11
    for t in digital:
        text = _squash(_text(out / t["file"]))
        wanted = list(t["printed"].values())
        wanted += [v for x in t["charges"] for v in x["printed"].values() if v is not None]
        wanted += [x["label"] for x in t["charges"]]
        for reg in ("kwh", "kvah", "kwh_total", "kvah_total"):
            rows = t.get("tod", {}).get(reg, [])
            for r in rows if isinstance(rows, list) else [rows]:
                wanted += list(r["printed"].values())
        wanted += [f["printed"] for f in t.get("facts", {}).values()]
        missing = [w for w in wanted if _squash(w) not in text]
        assert not missing, (t["file"], missing)


def test_scans_have_no_text_layer(out, truths):
    scans = [t for t in truths if t["input_kind"] == "scan_pdf"]
    assert len(scans) == 4
    for t in scans:
        assert _text(out / t["file"]).strip() == ""
        assert len(pdfium.PdfDocument(str(out / t["file"]))) == 1


def test_photo_variants_exist_and_differ(out, truths):
    photos = [t for t in truths if t["input_kind"] == "photo_jpeg"]
    by_source: dict[str, list[dict]] = {}
    for t in photos:
        by_source.setdefault(t["derived_from"], []).append(t)
    electricity = [s for s in by_source if s.startswith(("avvnl", "pvvnl"))]
    assert len(electricity) == 4
    for source in electricity:
        group = by_source[source]
        assert sorted(t["variant"] for t in group) == sorted(
            ["rotation", "perspective", "blur", "glare", "lowres"]
        )
        images = {t["variant"]: Image.open(out / t["file"]).convert("RGB") for t in group}
        assert images["lowres"].width < images["blur"].width // 2
        assert images["rotation"].size != images["blur"].size
        names = sorted(images)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                ia, ib = images[a], images[b]
                if ia.size == ib.size:
                    assert ImageChops.difference(ia, ib).getbbox() is not None, (a, b)
        for t in group:
            assert t["fields"] == _load(out / source.replace(".pdf", ".truth.json"))["fields"]
