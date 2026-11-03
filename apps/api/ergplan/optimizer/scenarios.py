"""Scenarios (Stage 6): what an analyst asks the optimizer to size, and the money arithmetic on a
re-settled result (saving, simple payback, IRR, sensitivities). Pure."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SIZEABLE = (
    "oa_solar_intra",
    "oa_wind_intra",
    "oa_hybrid_intra",
    "oa_solar_ists",
    "oa_wind_ists",
    "oa_hybrid_ists",
    "group_captive",
    "rooftop_pv",
    "btm_bess",
    "iex_dam",
    "iex_rtm",
    "iex_gdam",
    "iex_gtam",
    "iex_tam",
    "iex_hpdam",
)


class CandidateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[SIZEABLE]  # type: ignore[valid-type]
    ownership: Literal["captive", "group_captive", "third_party"] | None = None
    price_inr_per_kwh: Decimal | None = Field(default=None, ge=0)  # the client's quote; else an assumption
    max_mw: Decimal | None = Field(default=None, gt=0)  # the most the client would take (or the exchange cap)
    min_mw: Decimal = Field(default=Decimal(0), ge=0)
    commissioned: date | None = None
    # where the client stated the price or capacity (their working's page and words), for its ref
    stated_in: str | None = Field(default=None, max_length=300)


class ContractDemandSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_kva: Decimal = Field(default=Decimal(50), gt=0)
    min_kva: Decimal | None = None
    max_kva: Decimal | None = None
    change_inr_per_kva_year: Decimal = Decimal(0)


class Sensitivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["price", "grid_rate"]
    candidate: str | None = None  # for kind price: a candidate kind
    pct: list[Decimal] = Field(
        default_factory=lambda: [Decimal(-10), Decimal(10)], min_length=1, max_length=6
    )


class ScenarioSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateSpec] = Field(min_length=1, max_length=8)
    as_of: date | None = None
    resolution_min: Literal[15, 60] = 15
    contract_demand: ContractDemandSpec | None = None  # None: keep today's contract demand
    lapse_price_inr_per_kwh: Decimal | None = Field(default=None, ge=0)
    grid_factor_t_per_mwh: Decimal | None = Field(default=None, gt=0)
    sensitivities: list[Sensitivity] = Field(default_factory=list, max_length=6)


def irr(cash: list[Decimal], lo: Decimal = Decimal("-0.99"), hi: Decimal = Decimal(10)) -> Decimal | None:
    """Internal rate of return of yearly cash flows (year 0 first), by bisection to 0.01%."""

    def npv(r: Decimal) -> Decimal:
        return sum((c / (1 + r) ** i for i, c in enumerate(cash)), Decimal(0))

    if not cash or npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
        if hi - lo < Decimal("0.00001"):
            break
    return ((lo + hi) / 2 * 100).quantize(Decimal("0.01"))


def payback_years(capex: Decimal, yearly_cash: Decimal) -> Decimal | None:
    if capex <= 0 or yearly_cash <= 0:
        return None
    return (capex / yearly_cash).quantize(Decimal("0.01"))


def reprice(lines: dict[str, Decimal], line: str, pct: Decimal) -> Decimal:
    """The year's total cost with one cost line scaled by pct (energy quantities held)."""
    return sum(lines.values(), Decimal(0)) + lines.get(line, Decimal(0)) * pct / 100


def standard(as_of: date, resolution_min: int = 15) -> list[tuple[str, ScenarioSpec]]:
    """The three scenarios a client gets without an analyst: captive solar; third-party hybrid with a
    battery; rooftop, captive solar and a battery."""
    base: dict[str, object] = {"as_of": as_of, "resolution_min": resolution_min}
    return [
        (
            "Captive solar",
            ScenarioSpec.model_validate(
                {
                    **base,
                    "candidates": [{"kind": "oa_solar_intra", "ownership": "captive"}],
                    "sensitivities": [{"kind": "price", "candidate": "oa_solar_intra"}],
                }
            ),
        ),
        (
            "Hybrid + battery",
            ScenarioSpec.model_validate(
                {
                    **base,
                    "candidates": [
                        {"kind": "oa_hybrid_intra", "ownership": "third_party"},
                        {"kind": "btm_bess"},
                    ],
                    "sensitivities": [{"kind": "price", "candidate": "oa_hybrid_intra"}],
                }
            ),
        ),
        (
            "Rooftop + solar + battery",
            ScenarioSpec.model_validate(
                {
                    **base,
                    "candidates": [
                        {"kind": "rooftop_pv"},
                        {"kind": "oa_solar_intra", "ownership": "captive"},
                        {"kind": "btm_bess"},
                    ],
                    "sensitivities": [{"kind": "grid_rate", "pct": ["-5", "5"]}],
                }
            ),
        ),
    ]
