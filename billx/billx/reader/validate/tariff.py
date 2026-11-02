"""Layer 4, the tariff checks T01 to T05 (Developer Guide section 6): the printed rates
against the version's `params`. Always warnings, never failures (build prompt 5.4): a T
warning that holds across many bills usually means a new tariff order, not a misread. Skip
when the version has no param for the comparison or the bill does not print the input.

Params the checks look for (each with its unit and source in `params_notes`):

    energy_rate_kvah / energy_rate_kwh     T01, by the energy line's unit
    tod_surcharge_rate / tod_rebate_rate   T01, the TOD lines
    demand_rate_kva                        T02, demand charge = billing demand x rate
    ed_rate_kvah / ed_rate_kwh / ed_pct    T03, electricity duty by unit or per cent
    <word>_cess_rate, cess_rate, cess_pct  T03, a cess line whose label contains <word>
    pf_incentive_min_pf, pf_penalty_max_pf T04, the PF band
    fixed_rate_kva / fixed_charge          T05, fixed or minimum charge per kVA or flat
"""

from __future__ import annotations

import re
from decimal import Decimal

from billx.core.schema import Bill, CheckResult, LineItem
from billx.reader.validate.registry import (
    ONE,
    CheckContext,
    check,
    line_path,
    paths_for,
    result,
    skip,
    within,
)

RATE_TOL = Decimal("0.0001")
_FIXED = re.compile(r"fixed|minimum", re.IGNORECASE)
_DEMAND = re.compile(r"demand", re.IGNORECASE)
_SURCHARGE = re.compile(r"surcharge", re.IGNORECASE)
_REBATE = re.compile(r"rebate", re.IGNORECASE)


def _lines(bill: Bill, code: str) -> list[tuple[int, LineItem]]:
    return [(i, x) for i, x in enumerate(bill.line_items) if x.code == code and x.kind == "item"]


def _rate_param(params: dict[str, Decimal], base: str, x: LineItem) -> tuple[str, Decimal] | None:
    unit = (x.unit or "").lower()
    if x.rate_unit and "%" in x.rate_unit:
        names = [f"{base}_pct"]
    elif unit in ("kvah", "kwh", "kva", "kw"):
        names = [f"{base}_rate_{unit}", f"{base}_rate"]
    else:
        names = [f"{base}_rate"]
    for name in names:
        if name in params:
            return name, params[name]
    return None


def _compare_rates(
    check_id: str, bill: Bill, pairs: list[tuple[int, LineItem, str, Decimal]]
) -> CheckResult:
    if not pairs:
        return skip(check_id, "no line with a printed rate matches a param")
    bad = [
        (i, x, n, p) for i, x, n, p in pairs if x.rate is None or not within(x.rate, p, RATE_TOL)
    ]
    i, x, name, p = bad[0] if bad else pairs[-1]
    return result(
        check_id,
        "warn" if bad else "pass",
        expected=p,
        actual=x.rate,
        tolerance=RATE_TOL,
        paths=paths_for(bill, *(line_path(j, "rate") for j, _, _, _ in pairs)),
        note=(
            f"differs_from:{name};lines:{len(bad)}"
            if bad
            else f"params:{','.join(n for _, _, n, _ in pairs)}"
        ),
    )


@check(
    "T01",
    "each printed energy and TOD rate equals the version's param",
    detects=(
        "a printed energy, TOD surcharge or TOD rebate rate that differs from the param by 0.0001"
    ),
    severity="warn",
)
def t01(bill: Bill, ctx: CheckContext) -> CheckResult:
    params = ctx.params()
    pairs = []
    for code, base in (
        ("energy_charge", "energy"),
        ("tod_surcharge", "tod_surcharge"),
        ("tod_rebate", "tod_rebate"),
    ):
        for i, x in _lines(bill, code):
            if x.rate is None:
                continue
            found = _rate_param(params, base, x)
            if found:
                pairs.append((i, x, found[0], found[1]))
    return _compare_rates("T01", bill, pairs)


@check(
    "T02",
    "demand charge = billing demand x the version's demand rate",
    detects=(
        "Rs 1 in the demand charge against billing demand x demand_rate_kva, or a differing "
        "printed rate"
    ),
    severity="warn",
)
def t02(bill: Bill, ctx: CheckContext) -> CheckResult:
    params = ctx.params()
    if "demand_rate_kva" not in params:
        return skip("T02", "no demand_rate_kva param")
    lines = [
        (i, x)
        for i, x in _lines(bill, "demand_charge")
        if _DEMAND.search(x.label) and not _FIXED.search(x.label)
    ]
    if not lines:
        return skip("T02", "no demand charge line")
    i, x = lines[0]
    billing = bill.demand.billing_kva if bill.demand.billing_kva is not None else x.quantity
    if billing is None:
        return skip("T02", "billing demand not printed")
    rate = params["demand_rate_kva"]
    expected = billing * rate
    ok = within(x.amount, expected, ONE) and (x.rate is None or within(x.rate, rate, RATE_TOL))
    return result(
        "T02",
        "pass" if ok else "warn",
        expected=expected,
        actual=x.amount,
        tolerance=ONE,
        paths=paths_for(bill, line_path(i), line_path(i, "rate"), "demand.billing_kva"),
    )


@check(
    "T03",
    "electricity duty and cess rates equal the version's params",
    detects="a printed duty or cess rate that differs from its param by 0.0001",
    severity="warn",
)
def t03(bill: Bill, ctx: CheckContext) -> CheckResult:
    params = ctx.params()
    pairs = []
    for i, x in _lines(bill, "electricity_duty"):
        if x.rate is None:
            continue
        found = _rate_param(params, "ed", x)
        if found:
            pairs.append((i, x, found[0], found[1]))
    cess_params = {n: v for n, v in params.items() if n.endswith("cess_rate") or n == "cess_pct"}
    for i, x in _lines(bill, "cess"):
        if x.rate is None:
            continue
        label = x.label.lower()
        for name, value in cess_params.items():
            word = name[: -len("_cess_rate")] if name.endswith("_cess_rate") else ""
            if name in ("cess_rate", "cess_pct") or (word and word in label):
                pairs.append((i, x, name, value))
                break
    return _compare_rates("T03", bill, pairs)


@check(
    "T04",
    "the PF incentive or penalty falls in the version's band for the printed power factor",
    detects=(
        "a PF incentive line with PF below pf_incentive_min_pf, or a penalty line with PF "
        "above pf_penalty_max_pf"
    ),
    severity="warn",
)
def t04(bill: Bill, ctx: CheckContext) -> CheckResult:
    params = ctx.params()
    pf = bill.energy.power_factor
    if pf is None or not ({"pf_incentive_min_pf", "pf_penalty_max_pf"} & set(params)):
        return skip("T04", "power factor or PF band params not printed")
    problems = []
    paths = ["energy.power_factor"]
    for i, _ in _lines(bill, "pf_incentive"):
        paths.append(line_path(i))
        if "pf_incentive_min_pf" in params and pf < params["pf_incentive_min_pf"]:
            problems.append("incentive_below_band")
    for i, _ in _lines(bill, "pf_penalty"):
        paths.append(line_path(i))
        if "pf_penalty_max_pf" in params and pf > params["pf_penalty_max_pf"]:
            problems.append("penalty_above_band")
    return result(
        "T04",
        "warn" if problems else "pass",
        actual=pf,
        paths=paths_for(bill, *paths),
        note=",".join(problems) or None,
    )


@check(
    "T05",
    "the fixed or minimum charge equals the version's rate or amount",
    detects=(
        "a printed fixed-charge rate differing from fixed_rate_kva by 0.0001, or a flat fixed "
        "charge differing from fixed_charge by Rs 1"
    ),
    severity="warn",
)
def t05(bill: Bill, ctx: CheckContext) -> CheckResult:
    params = ctx.params()
    lines = [
        (i, x)
        for i, x in enumerate(bill.line_items)
        if x.kind == "item"
        and (x.code == "fixed_charge" or (x.code == "demand_charge" and _FIXED.search(x.label)))
    ]
    if not lines:
        return skip("T05", "no fixed or minimum charge line")
    i, x = lines[0]
    if "fixed_rate_kva" in params and x.rate is not None:
        rate = params["fixed_rate_kva"]
        return result(
            "T05",
            "pass" if within(x.rate, rate, RATE_TOL) else "warn",
            expected=rate,
            actual=x.rate,
            tolerance=RATE_TOL,
            paths=paths_for(bill, line_path(i, "rate")),
        )
    if "fixed_charge" in params:
        flat = params["fixed_charge"]
        return result(
            "T05",
            "pass" if within(x.amount, flat, ONE) else "warn",
            expected=flat,
            actual=x.amount,
            tolerance=ONE,
            paths=paths_for(bill, line_path(i)),
        )
    return skip("T05", "no fixed_rate_kva or fixed_charge param")


__all__ = ["RATE_TOL"]
