"""The plan over its analysis period (25 years by default): year-by-year cash flows, their present
value, the lifecycle cost today and with the plan, NPV, payback and IRR.

The optimizer sizes one representative year (hourly or 15-minute). This module projects that year
forward the way REopt and the tariff regulators' own models do: the grid tariff escalates at one rate,
contracted power (PPA, exchange) at another, O&M at a third; owned plant is paid for up front and
replaced when its life ends inside the period; generation degrades so a little more is bought from
the grid each year; every year is discounted at the cost of capital. Pure arithmetic in Decimal; the
inputs arrive as SourcedValues and every output carries them (invariant 1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..core.sourced import SourcedValue, derive
from ..core.units import Unit

ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)


@dataclass(frozen=True)
class Asset:
    """Owned plant in the plan (rooftop solar, a battery): its capital cost, O&M, life and how its
    output falls with age. `displaced_inr` is the grid cost its year-1 output avoids: as the plant
    degrades, that much more is bought from the grid."""

    cid: str
    label: str
    capex: SourcedValue  # INR, the whole plant
    om_pct: SourcedValue  # percent of capex per year
    life_years: SourcedValue  # count
    degradation_pct: SourcedValue  # percent per year (0 for a battery: it is replaced instead)
    displaced_inr: Decimal = ZERO


@dataclass(frozen=True)
class Inputs:
    analysis_years: SourcedValue
    discount_pct: SourcedValue
    tariff_escalation_pct: SourcedValue
    ppa_escalation_pct: SourcedValue
    om_escalation_pct: SourcedValue


@dataclass(frozen=True)
class Year:
    year: int  # 1..N (0 is the investment)
    bau: Decimal  # the grid bill without the plan
    grid: Decimal  # with the plan: what is still bought from the DISCOM
    contracted: Decimal  # PPA and exchange energy
    om: Decimal
    capex: Decimal  # replacements inside the period (year 0 holds the first purchase)
    saving: Decimal  # bau − (grid + contracted + om)
    cash: Decimal  # saving − capex
    cumulative: Decimal
    discount: Decimal  # 1 / (1 + r)^year
    pv_cash: Decimal


@dataclass(frozen=True)
class Lifecycle:
    inputs: Inputs
    years: list[Year]
    capex0: Decimal
    pv_bau: Decimal
    pv_plan: Decimal  # grid + contracted + om + capex (year 0 and replacements), discounted
    npv: Decimal  # pv_bau − pv_plan
    nominal_saving: Decimal  # Σ saving − Σ capex, undiscounted
    simple_payback_years: Decimal | None
    discounted_payback_years: Decimal | None
    irr_pct: Decimal | None
    notes: list[str] = field(default_factory=list)


def _esc(pct: Decimal, year: int) -> Decimal:
    return (ONE + pct / HUNDRED) ** (year - 1)


def project(
    before_lines: dict[str, Decimal],
    after_lines: dict[str, Decimal],
    assets: list[Asset],
    fin: Inputs,
) -> Lifecycle:
    """Year 1 is the optimizer's settled year. `after_lines` holds the plan's grid lines (`demand`,
    `grid_energy`, `excess_demand`), each contracted source's `energy:<cid>` and each owned asset's
    annualised `fixed:<cid>`; the fixed lines are replaced here by capital at year 0 (and at each
    replacement) plus O&M, which is what the cash flows are."""
    n = int(fin.analysis_years.value)
    r = fin.discount_pct.value / HUNDRED
    bau1 = sum(before_lines.values(), ZERO)
    grid1 = sum((v for k, v in after_lines.items() if ":" not in k), ZERO)
    contracted1 = sum((v for k, v in after_lines.items() if k.startswith("energy:")), ZERO)
    capex0 = sum((a.capex.value for a in assets), ZERO)
    om1 = sum((a.capex.value * a.om_pct.value / HUNDRED for a in assets), ZERO)
    years: list[Year] = []
    cumulative = -capex0
    pv_bau = ZERO
    pv_plan = capex0  # paid at year 0, discount factor 1; replacements are discounted in their year
    savings: list[Decimal] = []  # full precision; the Year rows are quantized for display only
    cashes: list[Decimal] = []
    discounts: list[Decimal] = []
    notes: list[str] = []
    replaced: set[str] = set()
    if any(a.degradation_pct.value > 0 and a.displaced_inr > 0 for a in assets):
        notes.append(
            "the output lost to degradation is bought back from the grid at the year's average energy "
            "rate (assumption)"
        )
    for y in range(1, n + 1):
        te, pe, oe = (
            fin.tariff_escalation_pct.value,
            fin.ppa_escalation_pct.value,
            fin.om_escalation_pct.value,
        )
        bau = bau1 * _esc(te, y)
        lost = ZERO  # grid cost that returns as owned plant degrades
        capex_y = ZERO
        for a in assets:
            d = a.degradation_pct.value / HUNDRED
            life = int(a.life_years.value)
            age = (y - 1) % life if life > 0 else y - 1
            if d > 0:
                lost += a.displaced_inr * (ONE - (ONE - d) ** age) * _esc(te, y)
            if life > 0 and y > life and (y - 1) % life == 0:
                capex_y += a.capex.value
                if a.cid not in replaced:
                    replaced.add(a.cid)
                    notes.append(
                        f"{a.label}: replaced in year {y} at today's capital cost (its life is {life} years)"
                    )
        grid = grid1 * _esc(te, y) + lost
        contracted = contracted1 * _esc(pe, y)
        om = om1 * _esc(oe, y)
        saving = bau - (grid + contracted + om)
        cash = saving - capex_y
        cumulative += cash
        disc = ONE / (ONE + r) ** y
        pv_bau += bau * disc
        pv_plan += (grid + contracted + om + capex_y) * disc
        savings.append(saving)
        cashes.append(cash)
        discounts.append(disc)
        years.append(
            Year(
                year=y,
                bau=_q(bau),
                grid=_q(grid),
                contracted=_q(contracted),
                om=_q(om),
                capex=_q(capex_y),
                saving=_q(saving),
                cash=_q(cash),
                cumulative=_q(cumulative),
                discount=disc.quantize(Decimal("0.000001")),
                pv_cash=_q(cash * disc),
            )
        )
    # every total from the full-precision series; quantized once, here, for the report
    nominal = cumulative  # Σ cash − capex0: the last cumulative
    return Lifecycle(
        inputs=fin,
        years=years,
        capex0=_q(capex0),
        pv_bau=_q(pv_bau),
        pv_plan=_q(pv_plan),
        npv=_q(pv_bau - pv_plan),
        nominal_saving=_q(nominal),
        # payback on the operating saving (replacements are in the IRR and NPV, not the payback)
        simple_payback_years=_payback(capex0, savings),
        discounted_payback_years=_payback(capex0, [sv * d for sv, d in zip(savings, discounts, strict=True)]),
        irr_pct=_irr([-capex0, *cashes]) if capex0 > 0 else None,
        notes=notes,
    )


def _q(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"))


def _payback(capex: Decimal, cash: list[Decimal]) -> Decimal | None:
    """Years until the cumulative cash flow recovers the investment, interpolated within the year."""
    if capex <= 0:
        return None
    cum = -capex
    for i, c in enumerate(cash):
        if cum + c >= 0:
            if c <= 0:
                return None
            return (Decimal(i) + (-cum) / c).quantize(Decimal("0.1"))
        cum += c
    return None


def _irr(cash: list[Decimal]) -> Decimal | None:
    from ..optimizer.scenarios import irr  # the bisection the plan already uses

    return irr(cash)


def to_json(lc: Lifecycle, inputs: list[SourcedValue]) -> dict[str, object]:
    """The lifecycle for the run summary: totals as SourcedValues carrying every input, the years as
    plain decimals (strings), the assumptions by name."""
    fin = lc.inputs
    all_inputs = [
        *inputs,
        fin.analysis_years,
        fin.discount_pct,
        fin.tariff_escalation_pct,
        fin.ppa_escalation_pct,
        fin.om_escalation_pct,
    ]

    def sv(v: Decimal | None, unit: Unit, label: str) -> dict[str, object] | None:
        if v is None:
            return None
        return derive(v, unit, all_inputs, label=label).model_dump(mode="json")

    return {
        "analysis_years": fin.analysis_years.model_dump(mode="json"),
        "assumptions": {
            "discount_pct": fin.discount_pct.model_dump(mode="json"),
            "tariff_escalation_pct": fin.tariff_escalation_pct.model_dump(mode="json"),
            "ppa_escalation_pct": fin.ppa_escalation_pct.model_dump(mode="json"),
            "om_escalation_pct": fin.om_escalation_pct.model_dump(mode="json"),
        },
        "capex": sv(lc.capex0, Unit.INR, "Capital cost, year 0"),
        "pv_bau": sv(lc.pv_bau, Unit.INR, "Lifecycle cost today (present value)"),
        "pv_plan": sv(lc.pv_plan, Unit.INR, "Lifecycle cost with the plan (present value)"),
        "npv": sv(lc.npv, Unit.INR, "Net present value of the plan"),
        "nominal_saving": sv(lc.nominal_saving, Unit.INR, "Saving over the period, undiscounted"),
        "simple_payback_years": sv(lc.simple_payback_years, Unit.YEARS, "Simple payback"),
        "discounted_payback_years": sv(lc.discounted_payback_years, Unit.YEARS, "Discounted payback"),
        "irr_pct": sv(lc.irr_pct, Unit.PERCENT, "IRR on the capital"),
        "years": [
            {
                "year": y.year,
                "bau": str(y.bau),
                "grid": str(y.grid),
                "contracted": str(y.contracted),
                "om": str(y.om),
                "capex": str(y.capex),
                "saving": str(y.saving),
                "cash": str(y.cash),
                "cumulative": str(y.cumulative),
                "pv_cash": str(y.pv_cash),
            }
            for y in lc.years
        ],
        "notes": lc.notes,
    }
