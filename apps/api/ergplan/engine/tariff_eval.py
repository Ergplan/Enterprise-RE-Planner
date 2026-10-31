"""Evaluate an approved retail tariff for one month of a connection (Stage 3). Pure: rule rows and
quantities in, cited lines out. No database, no network, no model.

Every line is a SourcedValue in INR whose refs are the rule fields it used (the row's field_refs or
its source_ref) and the quantities it multiplied (bill fields, profile, statements). What the
schedule row does not state is not invented: the evaluator records the named gap (engine/gaps.py)
and leaves the line out, so a client never sees an unsourced number (rule 13).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..core.money import inr
from ..core.sourced import RefKind, SourcedValue, SourceRef, derive
from ..core.units import Unit
from ..rulebook.models import RuleView

UNIT_OF_BASIS = {"kwh": Unit.KWH, "kvah": Unit.KVAH}
RATE_OF_BASIS = {"kwh": Unit.INR_PER_KWH, "kvah": Unit.INR_PER_KVAH}
HUNDRED = Decimal(100)


class BasisMismatch(ValueError):
    pass


@dataclass(frozen=True)
class MonthQuantities:
    month: date
    units: SourcedValue  # the month's billed units in the schedule's basis (kWh or kVAh)
    by_slot: Mapping[str, SourcedValue] = field(default_factory=dict)  # ToD slot name → units
    max_kva: SourcedValue | None = None
    contract_kva: SourcedValue | None = None
    power_factor: SourcedValue | None = None
    load_factor_pct: SourcedValue | None = None


@dataclass(frozen=True)
class Line:
    # demand_charge | excess_demand_penalty | energy_charge | tod_adjustment | wheeling_charge | fppca |
    # electricity_duty | pf_adjustment | load_factor_rebate | minimum_charge | taxes | prompt_payment_rebate
    code: str
    label: str
    amount: SourcedValue
    quantity: SourcedValue | None = None
    rate: SourcedValue | None = None
    slot: str | None = None


@dataclass
class TariffBill:
    month: date
    schedule_id: str
    tod_id: str | None
    lines: list[Line]
    gaps: list[str]
    notes: list[str]

    @property
    def total(self) -> SourcedValue:
        if not self.lines:
            raise ValueError("no lines")
        return derive(
            inr(sum((ln.amount.value for ln in self.lines), Decimal(0))),
            Unit.INR,
            [ln.amount for ln in self.lines],
            label="Total",
        )

    def sum(self, *codes: str) -> Decimal:
        return sum((ln.amount.value for ln in self.lines if ln.code in codes), Decimal(0))


def _rate(row: RuleView, pointer: str, unit: Unit, label: str) -> SourcedValue | None:
    raw = row.get(pointer)
    if raw is None or raw == "":
        return None
    return SourcedValue(value=Decimal(str(raw)), unit=unit, source_refs=(row.ref(pointer),), label=label)


def _amount(value: Decimal, inputs: list[SourcedValue], label: str) -> SourcedValue:
    return derive(inr(value), Unit.INR, inputs, label=label)


def slot_of(tod: RuleView, month: int, minute_of_day: int) -> dict[str, object] | None:
    """The ToD slot covering a time of day in a month (slots may wrap past midnight)."""
    for s in tod.body.get("slots", []):
        if s.get("months") and month not in s["months"]:
            continue
        a = _minutes(str(s["start"]))
        b = _minutes(str(s["end"]))
        inside = a <= minute_of_day < b if a < b else (minute_of_day >= a or minute_of_day < b)
        if inside:
            return dict(s)
    return None


def _minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def slot_adjustment_pct(slot: Mapping[str, object]) -> Decimal:
    """Surcharge as +pct, rebate as −pct (both printed as positive numbers)."""
    if slot.get("surcharge_pct") not in (None, ""):
        return Decimal(str(slot["surcharge_pct"]))
    if slot.get("rebate_pct") not in (None, ""):
        return -Decimal(str(slot["rebate_pct"]))
    return Decimal(0)


def evaluate(schedule: RuleView, tod: RuleView | None, q: MonthQuantities) -> TariffBill:
    body = schedule.body
    basis = str(body.get("billing_basis", "kwh"))
    if q.units.unit != UNIT_OF_BASIS[basis]:
        raise BasisMismatch(f"the schedule bills in {basis}; quantities are in {q.units.unit}")
    lines: list[Line] = []
    gaps: list[str] = []
    notes: list[str] = []
    rate_unit = RATE_OF_BASIS[basis]

    # Demand
    dc = _rate(schedule, "/demand_charge/value", Unit.INR_PER_KVA_MONTH, "Demand charge")
    if dc is not None:
        recorded = q.max_kva
        cd = q.contract_kva
        floor_pct = schedule.get("/demand_charge/billing_demand_rule/min_pct_of_contract_demand")
        if recorded is None and cd is not None:
            billing = cd
            notes.append("recorded demand not given: demand charge on contract demand")
        elif recorded is None:
            billing = None
        elif floor_pct is not None and cd is not None:
            fp = _rate(
                schedule,
                "/demand_charge/billing_demand_rule/min_pct_of_contract_demand",
                Unit.PERCENT,
                "Billing-demand floor",
            )
            assert fp is not None
            floor = cd.value * fp.value / HUNDRED
            billing = derive(max(recorded.value, floor), Unit.KVA, [recorded, cd, fp], label="Billing demand")
        else:
            billing = recorded
            if cd is not None and recorded.value < cd.value:
                gaps.append("billing_demand_rule")
                notes.append(
                    "the schedule row states no billing-demand floor: demand charge on recorded demand"
                )
        if billing is not None:
            # Demand charge on the whole billing demand; demand above contract is charged again at
            # the stated multiple of the demand rate (UPERC general provisions 7(ii)(b): "200% of the
            # normal rate apart from the normal fixed / demand charges"; MERC: 150% additionally).
            lines.append(
                Line(
                    "demand_charge",
                    "Demand charge",
                    _amount(billing.value * dc.value, [billing, dc], "Demand charge"),
                    quantity=billing,
                    rate=dc,
                )
            )
            mult = schedule.get("/demand_charge/billing_demand_rule/excess_demand_penalty_multiplier")
            if mult is not None and cd is not None and recorded is not None and recorded.value > cd.value:
                m = _rate(
                    schedule,
                    "/demand_charge/billing_demand_rule/excess_demand_penalty_multiplier",
                    Unit.RATIO,
                    "Excess-demand multiple",
                )
                assert m is not None
                excess = derive(
                    recorded.value - cd.value, Unit.KVA, [recorded, cd], label="Demand above contract"
                )
                lines.append(
                    Line(
                        "excess_demand_penalty",
                        "Excess demand",
                        _amount(excess.value * dc.value * m.value, [excess, dc, m], "Excess demand"),
                        quantity=excess,
                        rate=dc,
                    )
                )

    # Energy and ToD
    base = _rate(schedule, "/energy_charge/base", rate_unit, "Energy charge")
    energy_total = Decimal(0)
    if base is not None:
        slots = list(tod.body.get("slots", [])) if tod is not None else []
        slots = [s for s in slots if not s.get("months") or q.month.month in s["months"]]
        adjusting = [s for s in slots if slot_adjustment_pct(s) != 0 or s.get("rate_delta_inr_per_kwh")]
        if slots and q.by_slot:
            covered = Decimal(0)
            for i, s in enumerate(slots):
                name = str(s["name"])
                units = q.by_slot.get(name)
                if units is None:
                    continue
                covered += units.value
                e = units.value * base.value
                energy_total += e
                lines.append(
                    Line(
                        "energy_charge",
                        f"Energy · {name}",
                        _amount(e, [units, base], f"Energy · {name}"),
                        quantity=units,
                        rate=base,
                        slot=name,
                    )
                )
                pct = slot_adjustment_pct(s)
                assert tod is not None
                if pct != 0:
                    key = "surcharge_pct" if pct > 0 else "rebate_pct"
                    p = _rate(tod, f"/slots/{i}/{key}", Unit.PERCENT, f"ToD {name}")
                    assert p is not None
                    adj = units.value * base.value * pct / HUNDRED
                    energy_total += adj
                    lines.append(
                        Line(
                            "tod_adjustment",
                            f"ToD {'surcharge' if pct > 0 else 'rebate'} · {name}",
                            _amount(adj, [units, base, p], f"ToD · {name}"),
                            quantity=units,
                            rate=p,
                            slot=name,
                        )
                    )
                elif s.get("rate_delta_inr_per_kwh"):
                    d = _rate(tod, f"/slots/{i}/rate_delta_inr_per_kwh", rate_unit, f"ToD {name}")
                    assert d is not None
                    adj = units.value * d.value
                    energy_total += adj
                    lines.append(
                        Line(
                            "tod_adjustment",
                            f"ToD · {name}",
                            _amount(adj, [units, d], f"ToD · {name}"),
                            quantity=units,
                            rate=d,
                            slot=name,
                        )
                    )
            rest = q.units.value - covered
            if rest > Decimal("0.5"):
                ru = derive(
                    rest, q.units.unit, [q.units, *q.by_slot.values()], label="Units outside the ToD slots"
                )
                e = rest * base.value
                energy_total += e
                lines.append(
                    Line(
                        "energy_charge",
                        "Energy · other hours",
                        _amount(e, [ru, base], "Energy"),
                        quantity=ru,
                        rate=base,
                    )
                )
        else:
            e = q.units.value * base.value
            energy_total += e
            lines.append(
                Line(
                    "energy_charge",
                    "Energy charge",
                    _amount(e, [q.units, base], "Energy charge"),
                    quantity=q.units,
                    rate=base,
                )
            )
            if adjusting:
                gaps.append("tod_split_unknown")
    energy_charges = [ln.amount for ln in lines if ln.code in ("energy_charge", "tod_adjustment")]

    # Per-unit additions
    for pointer, code, label, gap in (
        ("/retail_wheeling_charge", "wheeling_charge", "Wheeling charge", None),
        ("/fppca_inr_per_unit", "fppca", "Fuel and power purchase adjustment", "fppca_monthly"),
    ):
        r = _rate(schedule, pointer, rate_unit, label)
        if r is not None:
            lines.append(
                Line(
                    code,
                    label,
                    _amount(q.units.value * r.value, [q.units, r], label),
                    quantity=q.units,
                    rate=r,
                )
            )
        elif gap:
            gaps.append(gap)

    # Power factor (on energy charges)
    bands = body.get("pf_incentive") or []
    if bands and q.power_factor is not None and energy_charges:
        for i, b in enumerate(bands):
            if Decimal(str(b["pf_min"])) <= q.power_factor.value <= Decimal(str(b["pf_max"])):
                p = _rate(schedule, f"/pf_incentive/{i}/pct", Unit.PERCENT, "Power-factor incentive")
                assert p is not None
                amt = -energy_total * p.value / HUNDRED  # + incentive reduces the bill
                lines.append(
                    Line(
                        "pf_adjustment",
                        "Power-factor incentive" if p.value > 0 else "Power-factor penalty",
                        _amount(amt, [q.power_factor, p, *energy_charges], "PF"),
                        rate=p,
                    )
                )
                break

    # Load factor
    lf = body.get("lf_incentive") or []
    if lf and q.load_factor_pct is not None:
        for i, b in enumerate(lf):
            if Decimal(str(b["lf_min_pct"])) <= q.load_factor_pct.value <= Decimal(str(b["lf_max_pct"])):
                r = _rate(schedule, f"/lf_incentive/{i}/rebate_inr_per_unit", rate_unit, "Load-factor rebate")
                assert r is not None
                lines.append(
                    Line(
                        "load_factor_rebate",
                        "Load-factor incentive",
                        _amount(-q.units.value * r.value, [q.units, q.load_factor_pct, r], "LF"),
                        quantity=q.units,
                        rate=r,
                    )
                )
                break
    elif not lf:
        gaps.append("load_factor_incentive")

    # Electricity duty
    ed_pct = _rate(schedule, "/electricity_duty/pct", Unit.PERCENT, "Electricity duty")
    ed_unit = _rate(schedule, "/electricity_duty/inr_per_unit", rate_unit, "Electricity duty")
    if ed_pct is not None and energy_charges:
        lines.append(
            Line(
                "electricity_duty",
                "Electricity duty",
                _amount(energy_total * ed_pct.value / HUNDRED, [ed_pct, *energy_charges], "ED"),
                rate=ed_pct,
            )
        )
    elif ed_unit is not None:
        lines.append(
            Line(
                "electricity_duty",
                "Electricity duty",
                _amount(q.units.value * ed_unit.value, [q.units, ed_unit], "ED"),
                quantity=q.units,
                rate=ed_unit,
            )
        )
    else:
        gaps.append("electricity_duty")

    # Minimum charge
    mc = _rate(schedule, "/minimum_charge/inr_per_kva_month", Unit.INR_PER_KVA_MONTH, "Minimum charge")
    if mc is not None and q.contract_kva is not None and lines:
        floor = q.contract_kva.value * mc.value
        sub = sum((ln.amount.value for ln in lines), Decimal(0))
        if sub < floor:
            lines.append(
                Line(
                    "minimum_charge",
                    "Minimum charge top-up",
                    _amount(
                        floor - sub, [q.contract_kva, mc, *[ln.amount for ln in lines]], "Minimum charge"
                    ),
                    rate=mc,
                )
            )

    # Taxes and prompt payment
    tx = _rate(schedule, "/taxes_pct", Unit.PERCENT, "Taxes")
    if tx is not None and lines:
        sub = sum((ln.amount.value for ln in lines), Decimal(0))
        lines.append(
            Line(
                "taxes",
                "Taxes",
                _amount(sub * tx.value / HUNDRED, [tx, *[ln.amount for ln in lines]], "Taxes"),
                rate=tx,
            )
        )
    pp = _rate(schedule, "/prompt_payment_rebate_pct", Unit.PERCENT, "Prompt-payment rebate")
    if pp is not None and lines:
        sub = sum((ln.amount.value for ln in lines), Decimal(0))
        lines.append(
            Line(
                "prompt_payment_rebate",
                "Prompt-payment rebate",
                _amount(-sub * pp.value / HUNDRED, [pp, *[ln.amount for ln in lines]], "PPR"),
                rate=pp,
            )
        )
    else:
        gaps.append("prompt_payment_rebate")
    return TariffBill(q.month, schedule.id, tod.id if tod else None, lines, list(dict.fromkeys(gaps)), notes)


def assumed_quantity(value: Decimal, unit: Unit, note: str) -> SourcedValue:
    return SourcedValue(value=value, unit=unit, source_refs=(SourceRef(kind=RefKind.ASSUMPTION, note=note),))
