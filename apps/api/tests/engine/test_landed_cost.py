"""Landed cost: each component and exemption with hand-computed expectations, the six-consumer
spreadsheets (tests/fixtures/landed_cost_<state>.csv), and LCOE / LCOS."""

from __future__ import annotations

import csv
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from ergplan.core.sourced import RefKind
from ergplan.core.units import Unit
from ergplan.db.base import session_scope
from ergplan.engine import landed_cost as lc
from ergplan.engine import lcoe
from ergplan.rulebook import repository, service
from ergplan.rulebook.models import RuleView

from .helpers import restore_committed, sv

FIX = Path(__file__).resolve().parents[1] / "fixtures"
CATEGORY = {"pvvnl": "HV-2", "npcl": "HV-2", "msedcl": "HT I(A)"}


@pytest.fixture
def committed() -> None:
    restore_committed()


def _rows(discom: str) -> tuple[list[RuleView], list[RuleView]]:
    with session_scope() as s:
        chain = service.jurisdiction_chain(s, discom)
        return (
            repository.approved_rules(s, "oa_charge", chain, date(2026, 11, 1)),
            repository.approved_rules(s, "settlement", chain, date(2026, 11, 1)),
        )


def _ctx(discom: str, kv: int) -> dict[str, object]:
    return {"category": CATEGORY[discom], "voltage_kv": Decimal(kv), "month": 11, "rate_block": "urban"}


def _r4(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _cases() -> list[dict[str, str]]:
    out = []
    for p in sorted(FIX.glob("landed_cost_*.csv")):
        lines = [ln for ln in p.read_text().splitlines() if not ln.startswith("#")]
        out += list(csv.DictReader(lines))
    return out


@pytest.mark.parametrize("row", _cases(), ids=lambda r: r["consumer"])
def test_spreadsheet_consumers(row: dict[str, str], committed: None) -> None:
    oa, _ = _rows(row["discom"])
    spec = lc.SOURCE_BY_ID[row["source"]]
    wf = lc.evaluate(
        spec,
        _ctx(row["discom"], int(row["voltage_kv"])),
        lc.Scenario(price=sv(row["price"], Unit.INR_PER_KWH), ownership=row["ownership"]),
        oa,
    )
    assert _r4(wf.total.value) == Decimal(row["landed"]), [(x.label, x.value) for x in wf.lines]
    labels = {str(x.label): x.value for x in wf.lines}
    if row["css"] and Decimal(row["css"]) > 0:
        assert any("CSS" in k and _r4(v) == Decimal(row["css"]) for k, v in labels.items())
    for x in wf.lines[1:]:  # every line but the stated price cites a stored document page
        assert any(
            r.kind in (RefKind.ORDER, RefKind.REGULATION) and r.url and "#page=" in r.url
            for r in x.source_refs
        ), x.label


def test_loss_gross_up_and_injection_charges(committed: None) -> None:
    oa, _ = _rows("npcl")
    wf = lc.evaluate(
        lc.SOURCE_BY_ID["oa_solar_intra"],
        _ctx("npcl", 33),
        lc.Scenario(price=sv("3.10", Unit.INR_PER_KWH)),
        oa,
    )
    by = {str(x.label): x.value for x in wf.lines}
    stu = next(v for k, v in by.items() if "intra-state transmission charge" in k)
    wheel = next(v for k, v in by.items() if k.startswith("Average wheeling"))
    assert (stu, wheel) == (Decimal("0.3075"), Decimal("1.03"))
    losses = next(v for k, v in by.items() if k.startswith("Losses"))
    assert _r4(losses) == _r4((Decimal("3.10") + stu + wheel) * (1 / (1 - Decimal("0.0318")) - 1))
    assert "oa_losses" in wf.gaps  # NPCL publishes no OA distribution loss in the corpus
    a, b = wf.coefficient()
    assert _r4(a * Decimal("3.10") + b) == _r4(wf.total.value)


def test_captive_css_exemption_cites_the_regulation(committed: None) -> None:
    oa, _ = _rows("pvvnl")
    wf = lc.evaluate(
        lc.SOURCE_BY_ID["oa_solar_intra"],
        _ctx("pvvnl", 33),
        lc.Scenario(price=sv("3.10", Unit.INR_PER_KWH), ownership="captive"),
        oa,
    )
    ex = next(x for x in wf.lines if "exemption" in str(x.label))
    assert ex.value == Decimal("-0.49")
    assert any(r.page == 13 and r.kind == RefKind.REGULATION for r in ex.source_refs)


def test_banking_charge_upper_bound_for_captive(committed: None) -> None:
    oa, st = _rows("pvvnl")
    ctx = {**_ctx("pvvnl", 33), "connection": "intra_state", "source": "solar", "ownership": "captive"}
    from ergplan.rulebook.scope import matches

    settlement = next(r for r in st if matches(r.scope, ctx))
    wf = lc.evaluate(
        lc.SOURCE_BY_ID["oa_solar_intra"],
        _ctx("pvvnl", 33),
        lc.Scenario(price=sv("3.10", Unit.INR_PER_KWH), ownership="captive"),
        oa,
        (),
        settlement,
    )
    bank = next(x for x in wf.lines if "Banking" in str(x.label))
    before = sum((x.value for x in wf.lines[: wf.lines.index(bank)]), Decimal(0))
    assert _r4(bank.value) == _r4(before * (1 / Decimal("0.92") - 1))  # 8% in kind (CRE Reg. 12)
    assert any("upper bound" in n or "banked quantity" in n for n in wf.notes)


def test_ists_source_records_cerc_gaps(committed: None) -> None:
    oa, _ = _rows("pvvnl")
    wf = lc.evaluate(
        lc.SOURCE_BY_ID["oa_solar_ists"],
        _ctx("pvvnl", 33),
        lc.Scenario(price=sv("2.70", Unit.INR_PER_KWH)),
        oa,
    )
    assert {"ists_charges", "ists_waiver"} <= set(wf.gaps)
    assert any(
        "inter-state transmission loss" in str(x.label) for x in wf.lines if str(x.label).startswith("Losses")
    )


def _waiver_row() -> RuleView:
    ref = {"kind": "order", "document_id": "d", "page": 3, "quote": "q"}
    return RuleView(
        id="w",
        family="ists_waiver",
        version_id="v",
        jurisdiction_id="CERC",
        scope={},
        source_ref=ref,
        body={
            "applies_to": ["solar"],
            "bands": [
                {
                    "commissioned_from": "2023-07-01",
                    "commissioned_to": "2025-06-30",
                    "charges_waived_pct": "100",
                    "losses_waived_pct": "100",
                    "years": 25,
                }
            ],
        },
    )


def test_ists_waiver_and_capacity_charges() -> None:
    ref = {"kind": "order", "document_id": "d", "page": 9, "quote": "q"}
    rows = [
        RuleView(
            id="c",
            family="oa_charge",
            version_id="v",
            jurisdiction_id="CERC",
            scope={"connection": ["ists"]},
            source_ref=ref,
            body={"component": "ists_transmission", "basis": "inr_per_mw_month", "value": "300000"},
        ),
        RuleView(
            id="l",
            family="oa_charge",
            version_id="v",
            jurisdiction_id="CERC",
            scope={"connection": ["ists"]},
            source_ref=ref,
            body={"component": "ists_losses", "basis": "percent_in_kind", "value": "3"},
        ),
    ]
    sc = lc.Scenario(
        price=sv("2.70", Unit.INR_PER_KWH),
        capacity_mw=sv("10", Unit.MW),
        cuf_pct=sv("25", Unit.PERCENT),
        commissioned=date(2024, 1, 1),
        on=date(2026, 11, 1),
    )
    wf = lc.evaluate(lc.SOURCE_BY_ID["oa_solar_ists"], {"voltage_kv": Decimal(33)}, sc, rows, [_waiver_row()])
    cap = next(x for x in wf.lines if "scheduled energy" in str(x.label))
    assert cap.value == 0  # 100% waived for a 2024 plant
    assert not any(str(x.label).startswith("Losses") and x.value > 0 for x in wf.lines)
    late = lc.evaluate(
        lc.SOURCE_BY_ID["oa_solar_ists"],
        {"voltage_kv": Decimal(33)},
        lc.Scenario(
            price=sc.price,
            capacity_mw=sc.capacity_mw,
            cuf_pct=sc.cuf_pct,
            commissioned=date(2026, 1, 1),
            on=date(2026, 11, 1),
        ),
        rows,
        [_waiver_row()],
    )
    cap2 = next(x for x in late.lines if "scheduled energy" in str(x.label))
    # 3,00,000 INR/MW/month × 10 MW over 10,000 kW × 730 h × 25% = 1.6438 INR/kWh
    assert _r4(cap2.value) == Decimal("1.6438")


def test_exemption_conditions_and_sunset() -> None:
    ref = {"kind": "order", "document_id": "d", "page": 1, "quote": "q"}
    row = RuleView(
        id="x",
        family="oa_charge",
        version_id="v",
        jurisdiction_id="X",
        scope={},
        source_ref=ref,
        body={
            "component": "wheeling",
            "basis": "inr_per_kwh",
            "value": "1",
            "exemptions": [
                {"condition": "consumer_voltage_at_or_above_kv", "param": "66", "waived_pct": "100"},
                {"condition": "re_source_waiver", "waived_pct": "50", "sunset": "2026-03-31"},
                {"condition": "other", "waived_pct": "100", "note": "not applied automatically"},
            ],
        },
    )
    p = sv("3", Unit.INR_PER_KWH)
    hv = lc.evaluate(
        lc.SOURCE_BY_ID["oa_solar_intra"], {"voltage_kv": Decimal(132)}, lc.Scenario(price=p), [row]
    )
    assert sum((x.value for x in hv.lines[1:]), Decimal(0)) == 0  # wheeling 1 − 100%
    lv = lc.evaluate(
        lc.SOURCE_BY_ID["oa_solar_intra"], {"voltage_kv": Decimal(11)}, lc.Scenario(price=p), [row]
    )
    assert (
        sum((x.value for x in lv.lines[1:]), Decimal(0)) == 1
    )  # the RE waiver has sunset; `other` is not applied
    before = lc.evaluate(
        lc.SOURCE_BY_ID["oa_solar_intra"],
        {"voltage_kv": Decimal(11)},
        lc.Scenario(price=p, on=date(2026, 1, 1)),
        [row],
    )
    assert sum((x.value for x in before.lines[1:]), Decimal(0)) == Decimal("0.5")


def test_behind_the_meter_sources_add_only_their_own_lines() -> None:
    v = lcoe.lcoe(lcoe.default_rooftop())
    wf = lc.evaluate(lc.SOURCE_BY_ID["rooftop_pv"], {}, lc.Scenario(price=v), [])
    assert wf.total.value == v.value and wf.gaps == []


def test_lcoe_and_lcos_hand_computed() -> None:
    g = lcoe.default_rooftop()
    r, n = Decimal("0.10"), 25
    crf = r * (1 + r) ** n / ((1 + r) ** n - 1)
    avg = sum((Decimal("0.995") ** y for y in range(n)), Decimal(0)) / n
    expect = (Decimal(40000) * crf + Decimal(600)) / (Decimal(8760) * Decimal("0.17") * avg)
    got = lcoe.lcoe(g)
    assert _r4(got.value) == _r4(expect)
    assert all(ref.kind in (RefKind.ASSUMPTION, RefKind.DERIVED) for ref in got.source_refs)
    s = lcoe.default_bess()
    crf12 = r * (1 + r) ** 12 / ((1 + r) ** 12 - 1)
    assert _r4(lcoe.lcos(s).value) == _r4(
        (Decimal(12000) * crf12 + Decimal(240)) / (Decimal(330) * Decimal("0.9"))
    )
