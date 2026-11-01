"""Tariff evaluator, one test per line type, with expectations computed by hand from the approved
UPERC and MERC schedules (pages cited in the rulebooks) and checked against real bills."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from ergplan.core.sourced import RefKind
from ergplan.core.units import Unit
from ergplan.engine.tariff_eval import BasisMismatch, MonthQuantities, evaluate, slot_of
from ergplan.rulebook.models import RuleView

from .helpers import restore_committed, rules, schedule, sv

pytestmark = pytest.mark.usefixtures("committed")


@pytest.fixture
def committed() -> None:
    restore_committed()


def _amount(tb, code: str) -> Decimal:  # type: ignore[no-untyped-def]
    return sum((ln.amount.value for ln in tb.lines if ln.code == code), Decimal(0))


def test_msedcl_ht1a_demand_energy_tod_wheeling_match_the_april_2026_bill() -> None:
    # MERC Case 75/2025 p. 100: HT I(A) 650 Rs/kVA/month, 8.44 Rs/kVAh, wheeling 0.81 Rs/kVAh below 66 kV;
    # ToD p. 77 with the peak +25% of the MYT order's note (p. 565). The real bill (Apr 2026): MD 2157 kVA,
    # 1,452,509 kVAh; zones A 357,651 + B 178,545 (normal), C 497,284 (solar), D 419,028 (peak).
    r = rules("msedcl", "HT I(A)", "22", date(2026, 4, 30))
    q = MonthQuantities(
        month=date(2026, 4, 1),
        units=sv("1452509", Unit.KVAH),
        max_kva=sv("2157", Unit.KVA),
        contract_kva=sv("2200", Unit.KVA),
        by_slot={
            "normal": sv("536196", Unit.KVAH),
            "solar": sv("497284", Unit.KVAH),
            "peak": sv("419028", Unit.KVAH),
        },
    )
    tb = evaluate(schedule(r), r.tod, q)
    assert _amount(tb, "demand_charge") == Decimal("1402050.00")  # 650 × 2157
    assert _amount(tb, "energy_charge") == Decimal("12259175.96")  # 8.44 × 1,452,509
    assert _amount(tb, "tod_adjustment") == Decimal(
        "254587.54"
    )  # −15% × 8.44 × 497,284 + 25% × 8.44 × 419,028
    assert _amount(tb, "wheeling_charge") == Decimal("1176532.29")  # 0.81 × 1,452,509
    demand = next(ln for ln in tb.lines if ln.code == "demand_charge")
    assert demand.rate is not None and demand.rate.source_refs[0].page == 100
    tod = next(ln for ln in tb.lines if ln.code == "tod_adjustment" and ln.slot == "peak")
    assert any(ref.page == 565 for ref in tod.amount.source_refs)  # the +25% note
    assert "fppca_monthly" in tb.gaps and "electricity_duty" in tb.gaps


def test_up_billable_demand_floor_and_excess_demand() -> None:
    # UPERC NPCL order p. 387 (290 Rs/kVA/month above 11 kV), p. 354 (billable demand ≥ 75% of contract),
    # p. 355 (excess at 200% of the normal rate in addition).
    r = rules("npcl", "HV-2", "33", date(2026, 8, 15))
    low = evaluate(
        schedule(r),
        r.tod,
        MonthQuantities(
            month=date(2026, 8, 1),
            units=sv("100000", Unit.KVAH),
            max_kva=sv("3120", Unit.KVA),
            contract_kva=sv("6000", Unit.KVA),
        ),
    )
    assert _amount(low, "demand_charge") == Decimal("1305000.00")  # 290 × 4500
    assert _amount(low, "excess_demand_penalty") == 0
    high = evaluate(
        schedule(r),
        r.tod,
        MonthQuantities(
            month=date(2026, 8, 1),
            units=sv("100000", Unit.KVAH),
            max_kva=sv("6500", Unit.KVA),
            contract_kva=sv("6000", Unit.KVA),
        ),
    )
    assert _amount(high, "demand_charge") == Decimal("1885000.00")  # 290 × 6500
    assert _amount(high, "excess_demand_penalty") == Decimal("290000.00")  # 500 × 290 × 2
    floor = next(ln for ln in low.lines if ln.code == "demand_charge").quantity
    assert floor is not None and floor.value == Decimal("4500")
    assert {ref.page for ref in floor.source_refs if ref.kind == RefKind.ORDER} == {354}


def test_up_energy_by_tod_slot_matches_the_npcl_july_bill() -> None:
    # NPCL Jul–Aug 2026: TOD1 841,920 kVAh at 5.78 (−15%), TOD3 653,640 at 7.82 (+15%), TOD2/TOD4 at 6.80.
    r = rules("npcl", "HV-2", "33", date(2026, 8, 19))
    assert r.tod is not None
    names = {str(s["name"]) for s in r.tod.body["slots"]}
    rebate = next(
        n
        for n in names
        if r.tod.body["slots"][[str(s["name"]) for s in r.tod.body["slots"]].index(n)].get("rebate_pct")
    )
    surcharge = next(
        n
        for n in names
        if r.tod.body["slots"][[str(s["name"]) for s in r.tod.body["slots"]].index(n)].get("surcharge_pct")
    )
    normal = sorted(names - {rebate, surcharge})[0]
    q = MonthQuantities(
        month=date(2026, 8, 1),
        units=sv("2253840", Unit.KVAH),
        max_kva=sv("3999.6", Unit.KVA),
        contract_kva=sv("6000", Unit.KVA),
        by_slot={
            rebate: sv("841920", Unit.KVAH),
            normal: sv("758280", Unit.KVAH),
            surcharge: sv("653640", Unit.KVAH),
        },
    )
    tb = evaluate(schedule(r), r.tod, q)
    energy = _amount(tb, "energy_charge") + _amount(tb, "tod_adjustment")
    assert energy == Decimal("15134066.40")  # the bill's four energy lines


def test_no_split_records_the_tod_gap() -> None:
    r = rules("npcl", "HV-2", "11", date(2026, 8, 15))
    tb = evaluate(schedule(r), r.tod, MonthQuantities(month=date(2026, 8, 1), units=sv("1000", Unit.KVAH)))
    assert _amount(tb, "energy_charge") == Decimal("7100.00")  # 7.10 Rs/kVAh up to 11 kV
    assert "tod_split_unknown" in tb.gaps
    assert tb.total.value == Decimal("7100.00")


def test_basis_mismatch_is_refused() -> None:
    r = rules("npcl", "HV-2", "11", date(2026, 8, 15))
    with pytest.raises(BasisMismatch):
        evaluate(schedule(r), r.tod, MonthQuantities(month=date(2026, 8, 1), units=sv("1000", Unit.KWH)))


def _row(body: dict, field_refs: dict | None = None) -> RuleView:  # type: ignore[type-arg]
    ref = {"kind": "order", "document_id": "d", "page": 1, "quote": "q"}
    return RuleView(
        id="r",
        family="tariff_schedule",
        version_id="v",
        jurisdiction_id="x",
        scope={},
        body=body,
        source_ref=ref,
        field_refs=field_refs or {},
    )


def test_optional_lines_pf_lf_duty_fppca_minimum_taxes_rebate() -> None:
    body = {
        "category": "X",
        "billing_basis": "kwh",
        "demand_charge": {"value": "100", "basis": "inr_per_kva_month"},
        "energy_charge": {"base": "5"},
        "fppca_inr_per_unit": "0.5",
        "electricity_duty": {"pct": "10"},
        "pf_incentive": [{"pf_min": 0.95, "pf_max": 1.0, "pct": "1"}],
        "lf_incentive": [{"lf_min_pct": 75, "lf_max_pct": 100, "rebate_inr_per_unit": "0.25"}],
        "minimum_charge": {"inr_per_kva_month": "1000"},
        "taxes_pct": "2",
        "prompt_payment_rebate_pct": "1",
    }
    q = MonthQuantities(
        month=date(2026, 5, 1),
        units=sv("1000", Unit.KWH),
        max_kva=sv("10", Unit.KVA),
        contract_kva=sv("10", Unit.KVA),
        power_factor=sv("0.98", Unit.RATIO),
        load_factor_pct=sv("80", Unit.PERCENT),
    )
    tb = evaluate(_row(body), None, q)
    got = {ln.code: ln.amount.value for ln in tb.lines}
    assert got["demand_charge"] == Decimal("1000.00")
    assert got["energy_charge"] == Decimal("5000.00")
    assert got["fppca"] == Decimal("500.00")
    assert got["pf_adjustment"] == Decimal("-50.00")  # 1% incentive on 5,000 of energy
    assert got["load_factor_rebate"] == Decimal("-250.00")
    assert got["electricity_duty"] == Decimal("500.00")  # 10% of energy
    assert got["minimum_charge"] == Decimal("3300.00")  # 10 kVA × 1000 = 10,000 floor − 6,700
    assert got["taxes"] == Decimal("200.00")  # 2% of 10,000
    assert got["prompt_payment_rebate"] == Decimal("-102.00")  # 1% of 10,200
    assert tb.total.value == Decimal("10098.00")
    assert tb.gaps == []


def test_slot_of_wraps_midnight() -> None:
    tod = _row(
        {
            "slots": [
                {"name": "night", "start": "22:00", "end": "06:00"},
                {"name": "day", "start": "06:00", "end": "22:00"},
            ]
        }
    )
    assert slot_of(tod, 5, 23 * 60)["name"] == "night"  # type: ignore[index]
    assert slot_of(tod, 5, 2 * 60)["name"] == "night"  # type: ignore[index]
    assert slot_of(tod, 5, 12 * 60)["name"] == "day"  # type: ignore[index]


def _gerc_htp1() -> tuple[RuleView, RuleView]:
    """GERC HTP-I for MGVCL FY 2026-27 (PDF pages 173-175), as rule rows."""
    ref = {"kind": "order", "document_id": "g", "page": 173, "quote": "q"}
    sch = RuleView(
        id="s",
        family="tariff_schedule",
        version_id="v",
        jurisdiction_id="mgvcl",
        scope={},
        source_ref=ref,
        body={
            "category": "HTP-I",
            "billing_basis": "kwh",
            "demand_charge": {
                "value": "475",
                "basis": "inr_per_kva_month_billing_demand",
                "slabs": [
                    {"up_to_kva": "500", "value": "150"},
                    {"up_to_kva": "1000", "value": "260"},
                    {"value": "475"},
                ],
                "billing_demand_rule": {
                    "min_pct_of_contract_demand": "85",
                    "min_kva": "100",
                    "excess_demand_rate": "555",
                },
            },
            "energy_charge": {
                "base": "4.00",
                "by_billing_demand": [
                    {"above_kva": "500", "base": "4.20"},
                    {"above_kva": "2500", "base": "4.30"},
                ],
                "rebate_pct": "1",
            },
        },
    )
    tod = RuleView(
        id="t",
        family="tod_slots",
        version_id="v",
        jurisdiction_id="mgvcl",
        scope={},
        source_ref=ref,
        body={
            "slots": [
                {
                    "name": "peak",
                    "start": "07:00",
                    "end": "11:00",
                    "rate_delta_inr_per_kwh": "0.45",
                    "rate_delta_by_billing_demand": [{"above_kva": "500", "rate_delta_inr_per_kwh": "0.85"}],
                },
                {"name": "day", "start": "11:00", "end": "17:00", "rate_delta_inr_per_kwh": "-0.60"},
                {"name": "normal", "start": "17:00", "end": "07:00"},
            ]
        },
    )
    return sch, tod


def test_gerc_demand_slabs_billing_floor_energy_band_tod_band_and_rebate() -> None:
    sch, tod = _gerc_htp1()
    q = MonthQuantities(
        month=date(2026, 5, 1),
        units=sv("1000000", Unit.KWH),
        by_slot={
            "peak": sv("200000", Unit.KWH),
            "day": sv("300000", Unit.KWH),
            "normal": sv("500000", Unit.KWH),
        },
        max_kva=sv("1500", Unit.KVA),
        contract_kva=sv("2000", Unit.KVA),
    )
    tb = evaluate(sch, tod, q)
    # billing demand = max(1500, 85% of 2000) = 1700: 500 × 150 + 500 × 260 + 700 × 475
    assert _amount(tb, "demand_charge") == Decimal("537500.00")
    energy = [ln for ln in tb.lines if ln.code == "energy_charge" and ln.slot]
    assert {ln.rate.value for ln in energy if ln.rate} == {Decimal("4.20")}  # 500 < 1700 ≤ 2500 kVA
    tod_lines = {ln.slot: ln.amount.value for ln in tb.lines if ln.code == "tod_adjustment"}
    assert tod_lines["peak"] == Decimal("170000.00")  # 0.85 above 500 kVA
    assert tod_lines["day"] == Decimal("-180000.00")
    rebate = next(ln for ln in tb.lines if ln.label == "Rebate on energy charges")
    assert rebate.amount.value == Decimal("-42000.00")  # 1 % of 4.20 × 1,000,000


def test_gerc_excess_over_contract_and_least_billing_demand() -> None:
    sch, _ = _gerc_htp1()
    over = evaluate(
        sch,
        None,
        MonthQuantities(
            month=date(2026, 5, 1),
            units=sv("100000", Unit.KWH),
            max_kva=sv("1000", Unit.KVA),
            contract_kva=sv("800", Unit.KVA),
        ),
    )
    assert _amount(over, "demand_charge") == Decimal("153000.00")  # 500 × 150 + 300 × 260 (up to contract)
    assert _amount(over, "excess_demand_penalty") == Decimal("111000.00")  # 200 × 555
    small = evaluate(
        sch,
        None,
        MonthQuantities(
            month=date(2026, 5, 1),
            units=sv("5000", Unit.KWH),
            max_kva=sv("40", Unit.KVA),
            contract_kva=sv("100", Unit.KVA),
        ),
    )
    assert _amount(small, "demand_charge") == Decimal("15000.00")  # one hundred kVA × 150
    assert next(ln for ln in small.lines if ln.code == "energy_charge" and ln.rate).rate.value == Decimal(
        "4.00"
    )
