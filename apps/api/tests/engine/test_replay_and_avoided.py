"""Replay grouping and statuses on billx-shaped bills (synthetic, built here), the gap registry,
and the avoided-cost waterfall."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from ergplan.core.settings import REPO_ROOT
from ergplan.core.sourced import RefKind
from ergplan.core.units import Unit
from ergplan.engine import avoided_cost, replay
from ergplan.engine.gaps import GAPS

from .helpers import restore_committed, rules, sv


@pytest.fixture
def committed() -> None:
    restore_committed()


def _el(
    i: int,
    label: str,
    amount: str,
    code: str = "other",
    kind: str = "item",
    qty: str | None = None,
    rate: str | None = None,
    stage: str = "current",
) -> dict[str, Any]:
    return {
        "index": i,
        "label": label,
        "code": code,
        "kind": kind,
        "stage": stage,
        "quantity": qty,
        "rate": rate,
        "amount": {"value": amount},
    }


def msedcl_bill(peak_rate: str = "2.11") -> dict[str, Any]:
    """An April 2026 MSEDCL HT I(A) bill shaped like billx's output for the real one."""
    return {
        "index": 0,
        "flags": [],
        "fields": {
            "energy": {
                "billed_units": {"value": "1452509", "unit": "kVAh"},
                "kvah": {"value": "1452509"},
                "kwh": {"value": "1446902"},
                "power_factor": {"value": "0.996"},
            },
            "demand": {"max_kva": {"value": "2157", "page": 2}, "contract_kva": {"value": "2200"}},
            "period": {"from": {"value": "2026-03-31"}, "to": {"value": "2026-04-30"}},
            "totals": {"current_charges": {"value": "14577144.52"}},
        },
        "elements": [
            _el(0, "TOD TARIFF EC", str(Decimal("-629561.54") + Decimal("419028") * Decimal(peak_rate))),
            _el(1, "ELECTRICITY DUTY", "1186395.02", "electricity_duty"),
            _el(2, "CHARGES FOR EXCESS DEMAND", "0", "excess_demand_penalty"),
            _el(3, "TOTAL CURRENT BILL AS PER TARIFF", "14577144.52", kind="subtotal"),
            _el(4, "DEMAND CHARGES", "1402050", "demand_charge", rate="650"),
            _el(5, "WHEELING CHARGE @", "1176532.29", "wheeling_charge"),
            _el(6, "ENERGY CHARGES", "12259175.96", "energy_charge"),
            _el(7, "FAC @", "726254.5", "fppca"),
            _el(8, "TEXTILE SUBSIDY", "2916170", "subsidy"),
            _el(9, "PAYABLE BEFORE DUE DATE", "11938720"),
            _el(10, "PRINCIPAL ARREARS", "-241383.41", "arrears", stage="arrear"),
            _el(11, "A", "0", "other_rebate", kind="info", qty="357651", rate="0"),
            _el(12, "B", "0", "other_rebate", kind="info", qty="178545", rate="0"),
            _el(13, "C", "-629561.54", "other_rebate", kind="info", qty="497284", rate="-1.266"),
            _el(14, "D", "884149.08", "other_rebate", kind="info", qty="419028", rate=peak_rate),
        ],
    }


def test_replay_matches_and_explains(committed: None) -> None:
    r = rules("msedcl", "HT I(A)", "22", date(2026, 4, 30))
    rep = replay.replay("b1", msedcl_bill(), {}, date(2026, 4, 30), r.schedule, r.tod, sv("2200", Unit.KVA))
    g = {ln.group: ln for ln in rep.lines}
    assert g["demand"].status == "match" and g["wheeling"].status == "match"
    assert g["energy"].status == "match" and g["energy"].billed == Decimal("12513763.50")
    assert g["fppca"].status == "explained" and g["fppca"].gap == "fppca_monthly"
    assert g["electricity_duty"].status == "explained"
    assert g["state_subsidy"].billed == Decimal("-2916170")  # a credit
    assert "other:PAYABLE BEFORE DUE DATE" not in g and "arrears" not in str(g)  # totals and arrears left out
    assert rep.status == "explained"
    assert g["energy"].computed is not None
    assert {ref.kind for ref in g["energy"].computed.source_refs} >= {RefKind.ORDER, RefKind.BILL}


def test_replay_flags_a_wrong_rule(committed: None) -> None:
    # had the bill charged the peak at +20% (1.688/kVAh) the approved +25% would not agree
    r = rules("msedcl", "HT I(A)", "22", date(2026, 4, 30))
    rep = replay.replay(
        "b1", msedcl_bill("1.688"), {}, date(2026, 4, 30), r.schedule, r.tod, sv("2200", Unit.KVA)
    )
    energy = next(ln for ln in rep.lines if ln.group == "energy")
    assert energy.status == "unexplained" and rep.status == "unexplained"
    assert any("+20.0%" in n for n in rep.notes)


def test_replay_without_a_schedule_is_the_tariff_period_gap() -> None:
    rep = replay.replay("b1", msedcl_bill(), {}, date(2025, 4, 30), None, None, None)
    assert rep.status == "explained" and {ln.gap for ln in rep.lines} == {"tariff_period"}


def test_demand_proration_is_recognised(committed: None) -> None:
    r = rules("npcl", "HV-2", "33", date(2026, 8, 19))
    bill = {
        "index": 0,
        "flags": [],
        "fields": {
            "energy": {"billed_units": {"value": "1000", "unit": "kVAh"}},
            "demand": {"max_kva": {"value": "3999.6"}},
            "period": {"from": {"value": "2026-07-19"}, "to": {"value": "2026-08-19"}},
        },
        "elements": [
            _el(0, "BILLABLE DEMAND", "1330027.4"),
            _el(1, "ENERGY CHARGES", "7100", "energy_charge"),
        ],
    }
    rep = replay.replay("b", bill, {}, date(2026, 8, 19), r.schedule, r.tod, sv("6000", Unit.KVA))
    demand = next(ln for ln in rep.lines if ln.group == "demand")
    assert demand.status == "explained" and demand.gap == "demand_proration"  # 1,305,000 × 31/(365/12)


def test_confirmed_values_override_billx(committed: None) -> None:
    r = rules("msedcl", "HT I(A)", "22", date(2026, 4, 30))
    rep = replay.replay(
        "b1",
        msedcl_bill(),
        {"demand.max_kva": "2190"},
        date(2026, 4, 30),
        r.schedule,
        r.tod,
        sv("2180", Unit.KVA),
    )
    demand = next(ln for ln in rep.lines if ln.group == "demand")
    assert demand.computed is not None and demand.computed.value == Decimal("1423500.00")  # 650 × 2190
    assert demand.status == "unexplained"  # the bill charged 2157 kVA


def test_every_gap_is_listed_in_known_gaps() -> None:
    text = (REPO_ROOT / "docs" / "known-gaps.md").read_text()
    missing = [g for g in GAPS if f"`{g}`" not in text]
    assert not missing


def test_avoided_cost_matrix_cards_and_annual(committed: None) -> None:
    month_rules = lambda on: rules("msedcl", "HT I(A)", "22", on)  # noqa: E731
    kw = [Decimal("1000")] * (365 * 96)
    wf = avoided_cost.build(
        date(2026, 4, 1),
        kw,
        month_rules,
        sv("1.0039", Unit.RATIO),
        sv("8760000", Unit.KWH),
        sv("2200", Unit.KVA),
        sv("0.996", Unit.RATIO),
    )
    assert len(wf.matrix) == 12 and all(len(r) == 96 for r in wf.matrix)
    # April, 10:00 (solar): (8.44 − 15% + 0.81 wheeling) × 1.0039 kVAh/kWh
    assert wf.matrix[0][40] == (Decimal("8.44") * Decimal("0.85") + Decimal("0.81")) * Decimal("1.0039")
    # April, 20:00 (peak +25%)
    assert wf.matrix[0][80] == (Decimal("8.44") * Decimal("1.25") + Decimal("0.81")) * Decimal("1.0039")
    # December, 10:00 (solar −25%)
    assert wf.matrix[8][40] == (Decimal("8.44") * Decimal("0.75") + Decimal("0.81")) * Decimal("1.0039")
    card = next(c for c in wf.cards if c.slot == "peak")
    assert any(ref.page == 565 for ref in card.rate_inr_per_kwh.source_refs)
    labels = [a.label for a in wf.annual]
    assert labels[0] == "Energy at avoided rates (year)" and "Demand charges (year)" in labels
    demand_year = next(a for a in wf.annual if a.label == "Demand charges (year)")
    month = (Decimal("1000") / Decimal("0.996") * 650).quantize(Decimal("0.01"))
    assert demand_year.value == month * 12
    assert set(wf.gaps) == {"fppca_monthly", "electricity_duty"}


def test_avoided_cost_without_rules_is_zero_and_says_so() -> None:
    wf = avoided_cost.build(
        date(2026, 4, 1),
        [Decimal("1")] * (365 * 96),
        lambda on: avoided_cost.MonthRules(None, None),
        None,
        sv("1", Unit.KWH),
        None,
        None,
    )
    assert all(v == 0 for row in wf.matrix for v in row)
    assert len(wf.notes) == 12
