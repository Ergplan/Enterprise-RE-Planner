"""Stage 1 "done when", end to end on the synthetic set through read_file.

- every clean digital electricity PDF passes with no model call (text layer + OCR agree);
- a scan is refused honestly without a model (model_not_allowed / no_model_configured) and
  passes with mocked Model A and Model B;
- every planted misread is caught by the check that declares it;
- non-bills are refused with their type named; nothing is misread as an electricity bill.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from billx.core.normalize import normalise
from billx.platform.api.examples import ReplayModel
from billx.platform.synth.cli import build
from billx.reader.pipeline import read_file

ROOT = Path(__file__).resolve().parents[2]
FIELD_TYPES = {
    f["path"]: f["type"]
    for kind in ("electricity", "gas")
    for f in __import__("yaml").safe_load((ROOT / "config/guaranteed_fields.yaml").read_text())[
        kind
    ]
}


@pytest.fixture(scope="module")
def synth(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("synth")
    build(out, 1)
    return out


def _truth(path: Path) -> dict:
    return json.loads(path.with_suffix(".truth.json").read_text())


def _electricity_digital(synth: Path) -> list[Path]:
    return sorted(p for p in synth.glob("*.digital.pdf") if p.name.startswith(("avvnl", "pvvnl")))


@pytest.mark.ocr
def test_a_scan_is_refused_honestly_without_a_model(synth):
    scan = next(p for p in sorted(synth.glob("avvnl*.scan.pdf")))
    bill = read_file(scan, allow_cloud_model=False).bills[0]
    assert bill.status == "model_not_allowed" and bill.route == "none"
    assert bill.unread_reason == "model_not_allowed" and not bill.passed
    # a refused bill still says which discom and layout it came from
    assert bill.utility.id == "avvnl" and bill.profile.status == "draft"
    bill = read_file(scan, allow_cloud_model=True, max_cost_usd=Decimal("1")).bills[0]
    assert bill.status == "unreadable" and "no_model_configured" in bill.notes


@pytest.mark.ocr
def test_a_digital_bill_without_a_model_is_refused_but_keeps_its_reading(synth):
    """Proof rule 2: the text layer and OCR find fields by the same label rule, so their
    agreement verifies nothing; the bill is refused and still carries what was read."""
    path = _electricity_digital(synth)[0]
    bill = read_file(path).bills[0]
    assert bill.status == "model_not_allowed" and not bill.passed
    assert bill.data is not None and bill.checks
    assert all(v.verification != "verified" for v in bill.fields)


@pytest.mark.ocr
def test_every_digital_electricity_bill_passes_with_one_model_family(synth):
    files = _electricity_digital(synth)
    assert len(files) == 4
    for path in files:
        truth = _truth(path)
        a, b = ReplayModel.pair([path])
        env = read_file(
            path, allow_cloud_model=True, max_cost_usd=Decimal("1"), model_a=a, model_b=b
        )
        bill = env.bills[0]
        failed = [c.id for c in bill.checks if c.status == "fail"]
        assert bill.status == "passed", (path.name, bill.review_reasons, failed)
        assert bill.accepted and bill.accepted_by == "engine" and bill.flags == ()
        for v in bill.fields:
            expected = truth["fields"].get(v.path)
            if expected is None:
                continue
            assert v.verification == "verified", (path.name, v.path, v.readings)
            want = normalise(expected, FIELD_TYPES[v.path])
            if v.path == "utility.name":
                assert want in v.value, (path.name, v.path)  # the name as printed holds the code
            else:
                assert v.value == want, (path.name, v.path)
        assert "G09" in {c.id for c in bill.checks if c.status == "pass"}
        assert bill.data is not None and len(bill.data.line_items) >= len(truth["charges"])
        assert all(
            e.formula_recheck.status == "match" for e in bill.elements if e.quantity and e.rate
        )


@pytest.mark.ocr
def test_a_scan_passes_with_two_model_families(synth):
    scan = next(p for p in sorted(synth.glob("avvnl*.scan.pdf")))
    truth = _truth(scan)
    a, b = ReplayModel.pair([scan])
    env = read_file(scan, allow_cloud_model=True, max_cost_usd=Decimal("1"), model_a=a, model_b=b)
    bill = env.bills[0]
    assert bill.status == "passed", (
        bill.review_reasons,
        [c.id for c in bill.checks if c.status == "fail"],
    )
    assert bill.route == "cloud_model" and len(env.usage) >= 1 and a.calls == 1
    for v in bill.fields:
        if truth["fields"].get(v.path) is not None:
            assert v.verification == "verified" and "model_a" in v.readers, v.path


@pytest.mark.ocr
def test_every_planted_misread_is_caught(synth):
    planted = sorted(synth.glob("*.planted-*.pdf"))
    assert planted, "billx synth writes planted bills"
    missed = []
    for path in planted:
        info = _truth(path)["planted"]
        bill = read_file(path).bills[0]
        statuses = {c.id: c.status for c in bill.checks}
        if statuses.get(info["check"]) != "fail":
            missed.append((path.name, info["check"], statuses.get(info["check"])))
            continue
        # verified inputs + failed equation = the bill itself is wrong: passes with the flag
        assert f"printed_inconsistency:{info['check']}" in bill.flags or not bill.passed, path.name
    assert missed == []


@pytest.mark.ocr
def test_non_bills_are_refused_with_their_type_named(synth):
    expected = {
        "water-municipal-synth-v1": "water_bill",
        "telecom-fictional-synth-v1": "telecom_bill",
        "invoice-supplies-synth-v1": "other_invoice",
        "receipt-store-synth-v1": "not_a_bill",
        "letter-synth-v1": "not_a_bill",
    }
    for layout, doc_type in expected.items():
        path = synth / f"{layout}.digital.pdf"
        bill = read_file(path).bills[0]
        assert bill.status == "not_a_bill" and bill.unread_reason == "not_a_bill", layout
        assert bill.document_type == doc_type, layout
        assert bill.route == "none" and not bill.passed


@pytest.mark.ocr
def test_a_gas_bill_is_read_as_gas_never_as_not_a_bill(synth):
    for path in sorted(synth.glob("gas-*.digital.pdf")):
        bill = read_file(path).bills[0]
        assert bill.document_type == "gas_bill" and bill.bill_type == "gas", path.name
        assert bill.status != "not_a_bill"


@pytest.mark.ocr
def test_an_unclear_gate_asks_model_a_when_cloud_is_allowed(synth):
    """A low-resolution photo gives the local gate too little; with cloud use allowed, Model A
    confirms the type and the bill is read; without it, the file is refused as unclear."""
    photo = next(p for p in sorted(synth.glob("pvvnl*01.photo-lowres.jpg")))
    refused = read_file(photo, allow_cloud_model=False).bills[0]
    assert refused.status == "not_a_bill" and "type_unclear" in refused.notes
    a, b = ReplayModel.pair([photo])
    bill = read_file(
        photo, allow_cloud_model=True, max_cost_usd=Decimal("1"), model_a=a, model_b=b
    ).bills[0]
    assert bill.document_type == "electricity_bill" and bill.status != "not_a_bill"
    assert a.calls == 1 and "model_a" in bill.routes_used
