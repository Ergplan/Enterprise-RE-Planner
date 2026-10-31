"""Avoided cost (Stage 3). Pure: what one more or one fewer kWh from the grid costs in each
15-minute block, and the fixed-side terms of the bill, from approved rules and the load profile.

Under the retail tariffs ergPLAN covers, the marginal rate depends only on the month (season, ToD
rows) and the time of day, so the 35,040 block rates are exactly a month × 96-block matrix. Each
cell is built from rate cards (month × ToD slot) whose components are SourcedValues citing the rule
rows; components the rulebook does not hold (FPPCA, duty when not in the row) are left out and
named as gaps rather than estimated (rule 13).
"""

from __future__ import annotations

import calendar
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..core.money import inr
from ..core.sourced import SourcedValue, derive
from ..core.units import Unit
from ..rulebook.models import RuleView
from .tariff_eval import RATE_OF_BASIS, slot_adjustment_pct, slot_of

HUNDRED = Decimal(100)


@dataclass(frozen=True)
class RateCard:
    month: date
    slot: str | None
    components: list[SourcedValue]  # energy, ToD, wheeling, duty … in the billing unit
    kvah_factor: SourcedValue | None  # kVAh per kWh when the schedule bills kVAh
    rate_inr_per_kwh: SourcedValue  # the marginal avoided cost of one kWh in this month and slot


@dataclass
class Waterfall:
    year_start: date
    matrix: list[list[Decimal]]  # 12 months × 96 blocks, INR/kWh
    cards: list[RateCard]
    annual: list[SourcedValue]  # fixed-side and energy totals for the year
    gaps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    cell_cards: list[list[int]] = field(default_factory=list)  # index into `cards` per cell, −1 when none


@dataclass(frozen=True)
class MonthRules:
    schedule: RuleView | None
    tod: RuleView | None


def _rate(row: RuleView, pointer: str, unit: Unit, label: str) -> SourcedValue | None:
    raw = row.get(pointer)
    if raw in (None, ""):
        return None
    return SourcedValue(value=Decimal(str(raw)), unit=unit, source_refs=(row.ref(pointer),), label=label)


def rate_card(
    month: date, rules: MonthRules, slot_index: int | None, kvah_factor: SourcedValue | None
) -> RateCard | None:
    s = rules.schedule
    if s is None:
        return None
    basis = str(s.body.get("billing_basis", "kwh"))
    unit = RATE_OF_BASIS[basis]
    base = _rate(s, "/energy_charge/base", unit, "Energy charge")
    if base is None:
        return None
    comps = [base]
    slot_name = None
    energy_rate = base.value
    if rules.tod is not None and slot_index is not None:
        slot = rules.tod.body["slots"][slot_index]
        slot_name = str(slot["name"])
        pct = slot_adjustment_pct(slot)
        if pct != 0:
            key = "surcharge_pct" if pct > 0 else "rebate_pct"
            p = _rate(rules.tod, f"/slots/{slot_index}/{key}", Unit.PERCENT, f"ToD {slot_name}")
            assert p is not None
            comps.append(derive(base.value * pct / HUNDRED, unit, [base, p], label=f"ToD {slot_name}"))
            energy_rate += base.value * pct / HUNDRED
        elif slot.get("rate_delta_inr_per_kwh"):
            d = _rate(rules.tod, f"/slots/{slot_index}/rate_delta_inr_per_kwh", unit, f"ToD {slot_name}")
            assert d is not None
            comps.append(d)
            energy_rate += d.value
    for pointer, label in (("/retail_wheeling_charge", "Wheeling charge"), ("/fppca_inr_per_unit", "FPPCA")):
        r = _rate(s, pointer, unit, label)
        if r is not None:
            comps.append(r)
    ed_pct = _rate(s, "/electricity_duty/pct", Unit.PERCENT, "Electricity duty")
    if ed_pct is not None:
        comps.append(
            derive(energy_rate * ed_pct.value / HUNDRED, unit, [*comps[:2], ed_pct], label="Electricity duty")
        )
    ed_unit = _rate(s, "/electricity_duty/inr_per_unit", unit, "Electricity duty")
    if ed_unit is not None:
        comps.append(ed_unit)
    per_unit = sum((c.value for c in comps), Decimal(0))
    inputs = list(comps)
    if basis == "kvah":
        if kvah_factor is None:
            raise ValueError("a kVAh schedule needs the kVAh-per-kWh factor")
        per_unit = per_unit * kvah_factor.value
        inputs.append(kvah_factor)
    total = derive(
        per_unit, Unit.INR_PER_KWH, inputs, label=f"Avoided cost{f' · {slot_name}' if slot_name else ''}"
    )
    return RateCard(month, slot_name, comps, kvah_factor if basis == "kvah" else None, total)


def build(
    year_start: date,
    kw: Sequence[Decimal],
    rules_for: Callable[[date], MonthRules],
    kvah_factor: SourcedValue | None,
    profile_ref: SourcedValue,
    contract_kva: SourcedValue | None,
    power_factor: SourcedValue | None,
) -> Waterfall:
    """The year from `year_start`: rate matrix, rate cards, and annual lines (energy at the
    avoided rates, demand charges at the profile's monthly peaks)."""
    matrix: list[list[Decimal]] = []
    cell_cards: list[list[int]] = []
    cards: list[RateCard] = []
    annual: list[SourcedValue] = []
    gaps: list[str] = []
    notes: list[str] = []
    i = 0
    energy_cost = Decimal(0)
    energy_inputs: list[SourcedValue] = [profile_ref]
    demand_lines: list[SourcedValue] = []
    for m in range(12):
        y, mo = year_start.year + (year_start.month - 1 + m) // 12, (year_start.month - 1 + m) % 12 + 1
        first = date(y, mo, 1)
        n = calendar.monthrange(y, mo)[1] * 96
        rules = rules_for(first)
        row: list[Decimal] = []
        idx_row: list[int] = []
        by_slot: dict[int | None, RateCard | None] = {}
        for b in range(96):
            idx = None
            if rules.tod is not None:
                s = slot_of(rules.tod, mo, b * 15)
                idx = rules.tod.body["slots"].index(s) if s is not None else None
            if idx not in by_slot:
                by_slot[idx] = rate_card(first, rules, idx, kvah_factor)
                if by_slot[idx] is not None:
                    cards.append(by_slot[idx])  # type: ignore[arg-type]
            card = by_slot[idx]
            row.append(card.rate_inr_per_kwh.value if card else Decimal(0))
            idx_row.append(next((j for j in range(len(cards) - 1, -1, -1) if cards[j] is card), -1))
        if rules.schedule is None:
            notes.append(
                f"{first:%b %Y}: no approved tariff schedule; avoided cost not computed for this month"
            )
        matrix.append(row)
        cell_cards.append(idx_row)
        seg = kw[i : i + n]
        for k, v in enumerate(seg):
            energy_cost += v * Decimal("0.25") * row[k % 96]
        for c in by_slot.values():
            if c is not None and c.rate_inr_per_kwh not in energy_inputs:
                energy_inputs.append(c.rate_inr_per_kwh)
        # demand charge at this month's billing demand (profile peak in kVA, floor from the row)
        if rules.schedule is not None and seg:
            dc = _rate(rules.schedule, "/demand_charge/value", Unit.INR_PER_KVA_MONTH, "Demand charge")
            if dc is not None and power_factor is not None:
                peak_kva = max(seg) / power_factor.value
                floor = rules.schedule.get("/demand_charge/billing_demand_rule/min_pct_of_contract_demand")
                billing = peak_kva
                inputs = [profile_ref, power_factor, dc]
                if floor is not None and contract_kva is not None:
                    fp = _rate(
                        rules.schedule,
                        "/demand_charge/billing_demand_rule/min_pct_of_contract_demand",
                        Unit.PERCENT,
                        "Billing-demand floor",
                    )
                    assert fp is not None
                    billing = max(peak_kva, contract_kva.value * fp.value / HUNDRED)
                    inputs += [contract_kva, fp]
                demand_lines.append(
                    derive(inr(billing * dc.value), Unit.INR, inputs, label=f"Demand charge · {first:%b %Y}")
                )
        i += n
    annual.append(derive(inr(energy_cost), Unit.INR, energy_inputs, label="Energy at avoided rates (year)"))
    if demand_lines:
        annual.append(
            derive(
                inr(sum((d.value for d in demand_lines), Decimal(0))),
                Unit.INR,
                demand_lines,
                label="Demand charges (year)",
            )
        )
        annual.extend(demand_lines)
    for gap in ("fppca_monthly", "electricity_duty"):
        sched_rows = [rules_for(date(year_start.year, year_start.month, 1)).schedule]
        if gap == "fppca_monthly" and not any(s and s.get("/fppca_inr_per_unit") for s in sched_rows):
            gaps.append(gap)
        if gap == "electricity_duty" and not any(
            s and (s.get("/electricity_duty/pct") or s.get("/electricity_duty/inr_per_unit"))
            for s in sched_rows
        ):
            gaps.append(gap)
    return Waterfall(year_start, matrix, cards, annual, gaps, notes, cell_cards)
