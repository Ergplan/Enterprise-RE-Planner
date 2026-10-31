"""Bill replay (Stage 3). Pure: rebuild a bill from the approved tariff on the bill's own
quantities and compare it, line group by line group, with what the DISCOM charged (billx's
elements and totals).

A group's status is `match` when computed and billed agree within ₹1, `explained` when the
difference is covered by a named gap (engine/gaps.py, listed in docs/known-gaps.md) or a billx
flag, otherwise `unexplained`. The bill's status is the worst of its groups (and of the total).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ..core.money import inr
from ..core.sourced import RefKind, SourcedValue, SourceRef
from ..core.units import Unit
from ..rulebook.models import RuleView
from . import gaps as G
from .tariff_eval import MonthQuantities, TariffBill, evaluate, slot_adjustment_pct

TOLERANCE = Decimal("1.00")
SUMMARY_LABELS = ("PAYABLE", "DUE DATE AMOUNT", "TOTAL", "NET PAY", "CURRENT BILL AMOUNT", "BILL AMOUNT")
CREDIT_CODES = {"prompt_payment_rebate", "load_factor_rebate", "subsidy", "other_rebate", "tds"}
GROUP_LABEL = {
    "demand": "Demand charge",
    "excess_demand": "Excess demand",
    "energy": "Energy and ToD",
    "wheeling": "Wheeling charge",
    "fppca": "Fuel and power purchase adjustment",
    "electricity_duty": "Electricity duty",
    "pf": "Power factor",
    "load_factor": "Load-factor incentive",
    "minimum": "Minimum charge",
    "taxes": "Taxes",
    "prompt_payment": "Prompt-payment rebate",
}
COMPUTED_GROUP = {
    "demand_charge": "demand",
    "excess_demand_penalty": "excess_demand",
    "energy_charge": "energy",
    "tod_adjustment": "energy",
    "wheeling_charge": "wheeling",
    "fppca": "fppca",
    "electricity_duty": "electricity_duty",
    "pf_adjustment": "pf",
    "load_factor_rebate": "load_factor",
    "minimum_charge": "minimum",
    "taxes": "taxes",
    "prompt_payment_rebate": "prompt_payment",
}
GROUP_GAP = {
    "fppca": "fppca_monthly",
    "electricity_duty": "electricity_duty",
    "load_factor": "load_factor_incentive",
    "prompt_payment": "prompt_payment_rebate",
    "demand": "billing_demand_rule",
    "energy": "tod_split_unknown",
}


def _dec(v: Any) -> Decimal | None:
    if isinstance(v, dict):
        v = v.get("value")
    if v is None or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v).replace(",", "").strip())
    except InvalidOperation:
        return None


@dataclass(frozen=True)
class BilledLine:
    index: int
    label: str
    code: str
    amount: Decimal  # signed: credits negative
    group: str
    gap: str | None


@dataclass
class ReplayLine:
    group: str
    label: str
    billed: Decimal | None
    computed: SourcedValue | None
    difference: Decimal
    status: str  # match | explained | unexplained | not_billed
    explanation: str
    gap: str | None = None
    billed_items: list[str] = field(default_factory=list)


@dataclass
class ReplayReport:
    bill_id: str
    month: date
    lines: list[ReplayLine]
    computed_total: SourcedValue | None
    billed_total: Decimal | None
    total_difference: Decimal
    status: str
    tariff: TariffBill | None
    notes: list[str]


# ---------------------------------------------------------------- billed side


def billed_lines(bill: Mapping[str, Any]) -> list[BilledLine]:
    """The bill's current-period charge lines from billx's elements (items, not subtotals or
    information lines; arrears and adjustments are reported but do not enter the replay)."""
    out = []
    for e in bill.get("elements") or []:
        if e.get("kind") != "item" or e.get("stage") != "current":
            continue
        amt = _dec(e.get("amount"))
        if amt is None:
            continue
        code = str(e.get("code") or "other")
        label = str(e.get("label") or "").strip()
        up = label.upper()
        if any(s in up for s in SUMMARY_LABELS):
            continue  # a printed total or a payable amount, not a charge
        if code in CREDIT_CODES:
            amt = -abs(amt)
        group, gap = _group_of(code, up)
        out.append(BilledLine(int(e.get("index", 0)), label, code, amt, group, gap))
    if not any(b.group == "energy" for b in out):
        # some layouts print energy only as ToD zone lines (quantity × rate) marked as information
        for e in bill.get("elements") or []:
            label = str(e.get("label") or "").strip()
            amt, q = _dec(e.get("amount")), _dec(e.get("quantity"))
            if e.get("stage") == "current" and label.upper().startswith("TOD") and amt is not None and q:
                out.append(BilledLine(int(e.get("index", 0)), label, "energy_charge", amt, "energy", None))
    return out


def _group_of(code: str, up: str) -> tuple[str, str | None]:
    if code == "excess_demand_penalty" or "EXCESS" in up:
        return "excess_demand", None
    if code == "demand_charge" or (
        code == "other" and ("DEMAND" in up or up.startswith("FC") or "FIXED CHARGE" in up)
    ):
        return "demand", None
    if code in ("energy_charge", "tod_surcharge", "tod_rebate") or (code == "other" and "TOD" in up):
        return "energy", None
    if code == "wheeling_charge":
        return "wheeling", None
    if code.startswith("minimum_charge"):
        return "minimum", None
    if code in ("pf_penalty", "pf_incentive"):
        return "pf", None
    if code == "fppca":
        return "fppca", G.CODE_GAPS["fppca"]
    if code == "electricity_duty":
        return "electricity_duty", G.CODE_GAPS["electricity_duty"]
    if code == "load_factor_rebate":
        return "load_factor", G.CODE_GAPS["load_factor_rebate"]
    if code == "prompt_payment_rebate":
        return "prompt_payment", G.CODE_GAPS["prompt_payment_rebate"]
    for needle, gap in G.LABEL_GAPS:
        if needle in up:
            group = "fppca" if gap == "fppca_monthly" else gap
            return group, gap
    if code in G.CODE_GAPS:
        return G.CODE_GAPS[code], G.CODE_GAPS[code]
    return f"other:{up or code}", "unmodelled_line"


# ---------------------------------------------------------------- quantities from the bill


def _ref(bill_id: str, path: str, page: Any = None, note: str | None = None) -> SourceRef:
    return SourceRef(
        kind=RefKind.BILL,
        bill_id=bill_id,
        field_path=path,
        page=page if isinstance(page, int) else None,
        note=note,
    )


def tod_units(
    bill: Mapping[str, Any], bill_id: str, base_rate: Decimal, tod: RuleView | None, month: int, unit: Unit
) -> tuple[dict[str, SourcedValue], list[str]]:
    """Energy by ToD slot from billx's elements (zone lines with quantity and rate), matched to the
    approved slots by the adjustment the bill applied. A zone whose adjustment no approved slot
    carries is put on the slot with the nearest adjustment and reported."""
    notes: list[str] = []
    if tod is None:
        return {}, notes
    slots = [s for s in tod.body.get("slots", []) if not s.get("months") or month in s["months"]]
    zones: dict[str, dict[str, Any]] = {}
    for e in bill.get("elements") or []:
        q, r = _dec(e.get("quantity")), _dec(e.get("rate"))
        label = str(e.get("label") or "").strip().upper()
        if q is None or r is None or q == 0 or e.get("stage") != "current":
            continue
        is_zone = label.startswith("TOD") or (len(label) == 1 and label.isalpha()) or e.get("tod_slot")
        if not is_zone:
            continue
        key = str(e.get("tod_slot") or label)
        z = zones.setdefault(key, {"units": Decimal(0), "rate": r, "idx": []})
        z["units"] += q
        z["idx"].append(int(e.get("index", 0)))
    if not zones or base_rate == 0:
        return {}, notes
    out: dict[str, SourcedValue] = {}
    for key, z in sorted(zones.items()):
        r = z["rate"]
        # a zone printed at its full rate (base × (1 + p)) or as the adjustment alone (base × p)
        pct = (r / base_rate - 1) * 100 if r > base_rate / 2 else r / base_rate * 100
        best = min(slots, key=lambda s: abs(slot_adjustment_pct(s) - pct)) if slots else None
        if best is None:
            continue
        if abs(slot_adjustment_pct(best) - pct) > Decimal("0.5"):
            notes.append(
                f"bill zone {key} is charged {pct:+.1f}% on energy; the approved ToD rule has "
                f"{slot_adjustment_pct(best):+.1f}% for {best['name']}"
            )
        name = str(best["name"])
        refs = tuple(_ref(bill_id, f"elements.{i}.quantity", note=f"zone {key}") for i in z["idx"])
        prev = out.get(name)
        total = z["units"] + (prev.value if prev else Decimal(0))
        out[name] = SourcedValue(
            value=total, unit=unit, source_refs=(*(prev.source_refs if prev else ()), *refs)
        )
    return out, notes


def quantities(
    bill: Mapping[str, Any],
    bill_id: str,
    confirmed: Mapping[str, str],
    basis: str,
    month: date,
    contract_kva: SourcedValue | None,
    tod: RuleView | None,
    base_rate: Decimal,
) -> tuple[MonthQuantities, list[str]]:
    f = bill.get("fields") or {}

    def field_(path: str) -> tuple[Decimal | None, int | None]:
        if path in confirmed:
            return _dec(confirmed[path]), None
        node: Any = f
        for p in path.split("."):
            node = node.get(p) if isinstance(node, dict) else None
        return (_dec(node), node.get("page") if isinstance(node, dict) else None)

    unit = Unit.KVAH if basis == "kvah" else Unit.KWH
    notes: list[str] = []
    path = None
    for cand in (("energy.billed_units",) if basis else ()) + (
        ("energy.kvah",) if basis == "kvah" else ("energy.kwh",)
    ):
        v, _ = field_(cand)
        bu = (
            ((f.get("energy") or {}).get("billed_units") or {}).get("unit")
            if cand == "energy.billed_units"
            else None
        )
        if v is not None and (cand != "energy.billed_units" or (bu or "").lower() == basis):
            path = cand
            break
    if path is None:
        raise ValueError(f"the bill gives no units in {basis}")
    units_v, page = field_(path)
    assert units_v is not None
    units = SourcedValue(value=units_v, unit=unit, source_refs=(_ref(bill_id, path, page),))
    md_v, md_p = field_("demand.max_kva")
    pf_v, pf_p = field_("energy.power_factor")
    by_slot, tnotes = tod_units(bill, bill_id, base_rate, tod, month.month, unit)
    notes += tnotes
    return MonthQuantities(
        month=month,
        units=units,
        by_slot=by_slot,
        max_kva=SourcedValue(value=md_v, unit=Unit.KVA, source_refs=(_ref(bill_id, "demand.max_kva", md_p),))
        if md_v is not None
        else None,
        contract_kva=contract_kva,
        power_factor=SourcedValue(
            value=pf_v, unit=Unit.RATIO, source_refs=(_ref(bill_id, "energy.power_factor", pf_p),)
        )
        if pf_v is not None
        else None,
    ), notes


# ---------------------------------------------------------------- comparison


def period_days(bill: Mapping[str, Any]) -> int | None:
    per = (bill.get("fields") or {}).get("period") or {}
    try:
        a = date.fromisoformat(str((per.get("from") or {}).get("value"))[:10])
        b = date.fromisoformat(str((per.get("to") or {}).get("value"))[:10])
    except ValueError:
        return None
    return (b - a).days if b > a else None


def printed_rate_notes(bill: Mapping[str, Any], schedule: RuleView) -> list[str]:
    """When the bill prints its demand rate and it differs from the approved row's, say so: it is
    usually the supply voltage (a different band of the schedule)."""
    dc = schedule.get("/demand_charge/value")
    out = []
    for e in bill.get("elements") or []:
        up = str(e.get("label") or "").upper()
        r = _dec(e.get("rate"))
        if r is None or dc is None or e.get("kind") != "item" or "EXCESS" in up:
            continue
        is_demand = e.get("code") == "demand_charge" or up.startswith("FC") or "FIXED CHARGE" in up
        if is_demand and r != Decimal(str(dc)):
            out.append(
                f"the bill charges demand at ₹{r}/kVA/month; the approved row for this connection "
                f"({schedule.label}) has ₹{dc}: check the supply voltage"
            )
    return out


def replay(
    bill_id: str,
    bill: Mapping[str, Any],
    confirmed: Mapping[str, str],
    month: date,
    schedule: RuleView | None,
    tod: RuleView | None,
    contract_kva: SourcedValue | None,
) -> ReplayReport:
    flags = [str(x) for x in bill.get("flags") or []]
    billed = billed_lines(bill)
    billed_total = _dec(((bill.get("fields") or {}).get("totals") or {}).get("current_charges"))
    if schedule is None:
        lines = [
            ReplayLine(
                b.group,
                b.label,
                b.amount,
                None,
                -b.amount,
                "explained",
                G.GAPS["tariff_period"],
                "tariff_period",
                [b.label],
            )
            for b in billed
        ]
        return ReplayReport(
            bill_id,
            month,
            lines,
            None,
            billed_total,
            -sum((b.amount for b in billed), Decimal(0)),
            "explained",
            None,
            ["no approved tariff schedule for this connection on the bill's date"],
        )
    basis = str(schedule.body.get("billing_basis", "kwh"))
    base = Decimal(str(schedule.get("/energy_charge/base") or 0))
    q, notes = quantities(bill, bill_id, confirmed, basis, month, contract_kva, tod, base)
    tb = evaluate(schedule, tod, q)
    notes = notes + tb.notes + printed_rate_notes(bill, schedule)

    groups: dict[str, dict[str, Any]] = {}
    for ln in tb.lines:
        g = groups.setdefault(COMPUTED_GROUP[ln.code], {"computed": [], "billed": [], "gap": None})
        g["computed"].append(ln.amount)
    for b in billed:
        g = groups.setdefault(b.group, {"computed": [], "billed": [], "gap": b.gap})
        g["billed"].append(b)
        g["gap"] = g["gap"] or b.gap
    out: list[ReplayLine] = []
    for name, g in groups.items():
        comp: list[SourcedValue] = g["computed"]
        bl: list[BilledLine] = g["billed"]
        computed = None
        if comp:
            from ..core.sourced import derive

            computed = derive(
                inr(sum((c.value for c in comp), Decimal(0))),
                Unit.INR,
                comp,
                label=GROUP_LABEL.get(name, name),
            )
        b_amt = sum((b.amount for b in bl), Decimal(0)) if bl else None
        diff = (computed.value if computed else Decimal(0)) - (b_amt or Decimal(0))
        gap = g["gap"] or (GROUP_GAP.get(name) if GROUP_GAP.get(name) in tb.gaps else None)
        if name == "demand" and computed is not None and b_amt and abs(diff) > TOLERANCE and not gap:
            days = period_days(bill)
            if days and abs(b_amt / computed.value - Decimal(days) * 12 / 365) < Decimal("0.0002"):
                gap = "demand_proration"
        if abs(diff) <= TOLERANCE:
            status, why = (
                ("match", "agrees with the bill within ₹1")
                if bl
                else ("match", "computed as zero; not billed")
            )
        elif gap:
            status, why = "explained", G.GAPS[gap]
        elif any(f.startswith("printed_inconsistency") for f in flags):
            status, why = "explained", f"billx flags the bill's own arithmetic: {', '.join(flags)}"
        else:
            status = "unexplained"
            why = "the bill differs from the approved tariff" + (f" ({'; '.join(notes)})" if notes else "")
        out.append(
            ReplayLine(
                name,
                GROUP_LABEL.get(name, name.split(":", 1)[-1].title()),
                b_amt,
                computed,
                diff,
                status if bl or computed else "not_billed",
                why,
                gap,
                [b.label for b in bl],
            )
        )
    order = list(GROUP_LABEL)
    out.sort(key=lambda r: (order.index(r.group) if r.group in order else len(order), r.group))
    computed_total = tb.total if tb.lines else None
    sum_billed = sum((b.amount for b in billed), Decimal(0))
    total_diff = (computed_total.value if computed_total else Decimal(0)) - sum_billed
    if billed_total is not None and abs(billed_total - sum_billed) > TOLERANCE:
        notes.append(
            f"billx's current charges (₹{billed_total:,.2f}) are a subtotal the bill prints; the replay "
            f"compares its {len(billed)} current lines (₹{sum_billed:,.2f}) one by one"
        )
    statuses = {r.status for r in out}
    status = (
        "unexplained" if "unexplained" in statuses else "explained" if "explained" in statuses else "match"
    )
    return ReplayReport(bill_id, month, out, computed_total, billed_total, total_diff, status, tb, notes)
