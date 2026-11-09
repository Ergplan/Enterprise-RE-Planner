"""Levelised cost of energy (generation you own) and of storage (Stage 4). Pure.

Every input is a SourcedValue; the defaults are ergPLAN's normative assumptions (kind `assumption`,
editable chips), and the result carries the refs of every input it used.

LCOE = (capex × CRF + annual O&M) / average annual energy over the life (degradation applied)
LCOS = (capex × CRF + annual O&M) / annual energy discharged — the storage adder per kWh out,
       before the cost of the energy charged (the landed cost adds that, divided by round-trip
       efficiency)
CRF  = r (1 + r)^n / ((1 + r)^n − 1)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.sourced import RefKind, SourcedValue, SourceRef, derive
from ..core.units import Unit

HOURS = Decimal(8760)


def assumed(value: str, unit: Unit, note: str, label: str) -> SourcedValue:
    return SourcedValue(
        value=Decimal(value),
        unit=unit,
        label=label,
        source_refs=(SourceRef(kind=RefKind.ASSUMPTION, note=note),),
    )


def crf(rate_pct: SourcedValue, years: SourcedValue) -> SourcedValue:
    r = rate_pct.value / 100
    if years.value != years.value.to_integral_value() or years.value < 1:
        raise ValueError("economic life must be a whole number of years")
    n = int(years.value)
    f = (1 + r) ** n
    return derive(r * f / (f - 1), Unit.RATIO, [rate_pct, years], label="Capital recovery factor")


@dataclass(frozen=True)
class GenerationCost:
    capex_inr_per_kw: SourcedValue
    om_pct_of_capex: SourcedValue
    cuf_pct: SourcedValue
    degradation_pct: SourcedValue
    life_years: SourcedValue
    discount_pct: SourcedValue


@dataclass(frozen=True)
class StorageCost:
    capex_inr_per_kwh: SourcedValue
    om_pct_of_capex: SourcedValue
    cycles_per_year: SourcedValue
    depth_pct: SourcedValue
    life_years: SourcedValue
    discount_pct: SourcedValue
    round_trip_pct: SourcedValue


def default_rooftop() -> GenerationCost:
    return GenerationCost(
        capex_inr_per_kw=assumed(
            "40000", Unit.INR, "rooftop PV EPC for C&I in India, 2026, per kWp (DC)", "Capex"
        ),
        om_pct_of_capex=assumed("1.5", Unit.PERCENT, "annual O&M as % of capex", "O&M"),
        cuf_pct=assumed("17", Unit.PERCENT, "rooftop PV capacity utilisation, north and west India", "CUF"),
        degradation_pct=assumed("0.5", Unit.PERCENT, "module degradation per year", "Degradation"),
        life_years=assumed("25", Unit.COUNT, "economic life", "Life"),
        discount_pct=assumed("10", Unit.PERCENT, "pre-tax cost of capital", "Discount rate"),
    )


def default_bess() -> StorageCost:
    return StorageCost(
        capex_inr_per_kwh=assumed(
            "12000", Unit.INR, "4-hour LFP BESS incl. PCS and EPC, 2026, per kWh", "Capex"
        ),
        om_pct_of_capex=assumed("2", Unit.PERCENT, "annual O&M as % of capex", "O&M"),
        cycles_per_year=assumed("330", Unit.COUNT, "one cycle a day, 330 days", "Cycles"),
        depth_pct=assumed("90", Unit.PERCENT, "usable depth of discharge", "Depth of discharge"),
        life_years=assumed("12", Unit.COUNT, "economic life", "Life"),
        discount_pct=assumed("10", Unit.PERCENT, "pre-tax cost of capital", "Discount rate"),
        round_trip_pct=assumed("88", Unit.PERCENT, "AC round-trip efficiency", "Round-trip efficiency"),
    )


def lcoe(g: GenerationCost) -> SourcedValue:
    f = crf(g.discount_pct, g.life_years)
    n = int(g.life_years.value)
    d = g.degradation_pct.value / 100
    avg_factor = sum(((1 - d) ** y for y in range(n)), Decimal(0)) / n
    energy_per_kw = HOURS * g.cuf_pct.value / 100 * avg_factor
    annual = g.capex_inr_per_kw.value * f.value + g.capex_inr_per_kw.value * g.om_pct_of_capex.value / 100
    return derive(
        annual / energy_per_kw,
        Unit.INR_PER_KWH,
        [g.capex_inr_per_kw, g.om_pct_of_capex, g.cuf_pct, g.degradation_pct, f],
        label="LCOE",
    )


def lcos(s: StorageCost) -> SourcedValue:
    f = crf(s.discount_pct, s.life_years)
    out_per_kwh = s.cycles_per_year.value * s.depth_pct.value / 100
    annual = s.capex_inr_per_kwh.value * f.value + s.capex_inr_per_kwh.value * s.om_pct_of_capex.value / 100
    return derive(
        annual / out_per_kwh,
        Unit.INR_PER_KWH,
        [s.capex_inr_per_kwh, s.om_pct_of_capex, s.cycles_per_year, s.depth_pct, f],
        label="LCOS",
    )


def default_finance() -> dict[str, SourcedValue]:
    """The lifecycle view's assumptions when the client states none (engine.lifecycle)."""
    return {
        "analysis_years": assumed(
            "25", Unit.COUNT, "analysis period, the life of a solar plant", "Analysis period"
        ),
        "discount_pct": assumed("10", Unit.PERCENT, "pre-tax cost of capital", "Discount rate"),
        "tariff_escalation_pct": assumed(
            "3",
            Unit.PERCENT,
            "DISCOM tariff growth per year (the last decade's average)",
            "Tariff escalation",
        ),
        "ppa_escalation_pct": assumed(
            "0",
            Unit.PERCENT,
            "open-access and exchange prices held flat (a PPA is usually fixed)",
            "PPA escalation",
        ),
        "om_escalation_pct": assumed(
            "4", Unit.PERCENT, "O&M cost growth per year (inflation)", "O&M escalation"
        ),
    }
