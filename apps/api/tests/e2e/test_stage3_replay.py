"""Stage 3 replay of real bills: billx's stored results for the real bills in data/bills (gitignored;
read once through billx and cached under data/bills/billx-results/) replayed against the approved
rulebooks. Every line must match within ₹1 or be explained by a named gap; for bills inside the
approved tariffs' period, demand and energy (with ToD) must match the bill outright.

The supply voltage is not printed on these bills; the replay uses the band whose printed rates the
bills carry (UP 11–66 kV: Rs 290/kVA and 6.80/kVAh; MSEDCL HT: 22 kV), as a client would confirm."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from ergplan.core.settings import REPO_ROOT
from ergplan.core.sourced import RefKind, SourcedValue, SourceRef
from ergplan.core.units import Unit
from ergplan.engine import replay as rp
from ergplan.intake import bill_fields, defaults

from ..engine.helpers import restore_committed, rules

RESULTS = REPO_ROOT / "data" / "bills" / "billx-results"
VOLTAGE = {"UP": "33", "MH": "22"}
# bills whose period falls inside the approved FY 2026-27 tariffs: demand and energy must match
COMPUTED = {
    "NPCL July - Aug Plant.pdf",
    "July 2026.pdf",
    "August-2026.pdf",
    "bill_500_251019006990_202604.pdf",
}


def _cases() -> list[tuple[str, dict[str, Any]]]:
    out = []
    for p in sorted(RESULTS.glob("*.json")) if RESULTS.exists() else []:
        d = json.loads(p.read_text())
        for b in d["result"].get("bills", []):
            if defaults.discom_from_profile((b.get("profile") or {}).get("id")):
                out.append((d["filename"], b))
    return out


CASES = _cases()
pytestmark = pytest.mark.skipif(
    len(CASES) < 10, reason="fewer than ten cached real bills in data/bills/billx-results"
)


@pytest.fixture
def committed() -> None:  # function scope: the suite truncates tables after each test
    restore_committed()


def _when(f: bill_fields.BillFacts) -> date:
    to = f.text("period.to")
    if to and len(to) >= 10:
        return date.fromisoformat(to[:10])
    assert f.bill_month is not None
    return f.bill_month


@pytest.mark.parametrize(("filename", "bill"), CASES, ids=[c[0] for c in CASES])
def test_real_bill_replays(filename: str, bill: dict[str, Any], committed: None) -> None:
    f = bill_fields.facts(bill)
    discom = defaults.discom_from_profile(f.profile_id)
    assert discom
    state = defaults.state_of(discom) or ""
    cat = defaults.category_from_printed(state, f.text("tariff.category"))
    assert cat is not None, f.text("tariff.category")
    when = _when(f)
    r = rules(discom, cat.value, VOLTAGE[state], when)
    cd = f.num("demand.contract_kva")
    cdv = (
        SourcedValue(
            value=cd,
            unit=Unit.KVA,
            source_refs=(SourceRef(kind=RefKind.BILL, bill_id="b", field_path="demand.contract_kva"),),
        )
        if cd
        else None
    )
    rep = rp.replay("b", bill, {}, when, r.schedule, r.tod, cdv)
    bad = [(ln.group, str(ln.difference), ln.explanation) for ln in rep.lines if ln.status == "unexplained"]
    assert rep.status in ("match", "explained"), bad
    assert not bad
    if filename in COMPUTED:
        groups = {ln.group: ln for ln in rep.lines}
        assert groups["demand"].status in ("match", "explained") and groups["demand"].computed is not None
        assert groups["energy"].status == "match", (groups["energy"].billed, groups["energy"].computed)
        for ln in rep.lines:
            if ln.computed is not None:
                assert all(
                    ref.kind in (RefKind.ORDER, RefKind.BILL, RefKind.REGULATION)
                    for ref in ln.computed.source_refs
                )


def test_at_least_ten_real_bills_and_four_inside_the_approved_tariffs() -> None:
    names = {c[0] for c in CASES}
    assert len(CASES) >= 10
    assert len(names & COMPUTED) >= 3
