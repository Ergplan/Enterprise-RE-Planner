"""A site described by typing, for a consumer who has no bills at hand (or none accepted yet): the
factory, its connection and its consumption as a year's units or month by month. Everything typed is
`client_stated`; what ergPLAN fills in (months spread from a year's units, a power factor) is an
`assumption` with its note, so the plan shows it as an editable chip and never as a sourced fact."""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import defaults
from .profile_synthesis import working_days
from .site_intake import AssetIn, Fact, MonthFacts, Shift, SiteIntake


class TypedMonth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: date
    kwh: Decimal = Field(gt=0)
    max_kva: Decimal | None = Field(default=None, gt=0)
    bill_inr: Decimal | None = Field(default=None, ge=0)


class TypedIn(BaseModel):
    """What the Evaluate page asks when there are no bills."""

    model_config = ConfigDict(extra="forbid")

    client_name: str = Field(min_length=1, max_length=200)
    site_name: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=2, max_length=8)
    discom: str = Field(min_length=2, max_length=32)
    category: str = Field(min_length=1, max_length=64)
    voltage_kv: Decimal = Field(gt=0)
    contract_demand_kva: Decimal = Field(gt=0)
    consumer_number: str | None = Field(default=None, max_length=64)
    rate_block: str | None = Field(default=None, max_length=32)
    industry_shape: str = Field(min_length=1, max_length=32)
    weekly_off: list[int] | None = None
    shifts: list[Shift] | None = None
    land_acres: Decimal | None = Field(default=None, ge=0)
    roof_sqm: Decimal | None = Field(default=None, ge=0)
    open_access: str | None = None
    annual_kwh: Decimal | None = Field(default=None, gt=0)
    months: list[TypedMonth] | None = Field(default=None, min_length=1, max_length=12)
    max_demand_kva: Decimal | None = Field(default=None, gt=0)
    power_factor: Decimal | None = Field(default=None, ge=Decimal("0.3"), le=1)
    year_end: date | None = None  # the last of the twelve months a year's units are spread over
    assets: list[AssetIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_consumption(self) -> TypedIn:
        if (self.annual_kwh is None) == (self.months is None):
            raise ValueError("give the year's units (annual_kwh) or the months, not both")
        return self


def _twelve_months_to(end: date) -> list[date]:
    first = end.replace(day=1)
    out = [first]
    for _ in range(11):
        y, m = (first.year, first.month - 1) if first.month > 1 else (first.year - 1, 12)
        first = date(y, m, 1)
        out.append(first)
    return sorted(out)


def _working_days_in(month: date, off: set[int]) -> int:
    n = calendar.monthrange(month.year, month.month)[1]
    return sum(1 for d in range(1, n + 1) if date(month.year, month.month, d).weekday() not in off)


def spread(annual_kwh: Decimal, months: list[date], off: set[int]) -> dict[date, Decimal]:
    """A year's units spread over twelve months in proportion to each month's working days (the
    plant runs on its working days; a 31-day month with more of them uses more)."""
    weights = {
        m: Decimal(_working_days_in(m, off) or calendar.monthrange(m.year, m.month)[1]) for m in months
    }
    total = sum(weights.values(), Decimal(0))
    out = {m: (annual_kwh * w / total).quantize(Decimal("0.001")) for m, w in weights.items()}
    # the rounding difference lands on the last month, so the months add up to the year exactly
    last = months[-1]
    out[last] += annual_kwh - sum(out.values(), Decimal(0))
    return out


def build(body: TypedIn, today: date | None = None) -> SiteIntake:
    """The SiteIntake the typed facts describe (validated as any intake: a known DISCOM in its state,
    a known industry shape, positive figures)."""
    today = today or date.today()
    off_days = body.weekly_off
    off_ref = None
    if off_days is None:
        assumed = defaults.weekly_off(body.industry_shape)
        off_days, off_ref = list(assumed.value), assumed.ref
    off = set(off_days)
    pf_fact: Fact[Decimal] | None = None
    if body.power_factor is not None:
        pf_fact = Fact(value=body.power_factor)
    else:
        a = defaults.power_factor()
        pf_fact = Fact(value=a.value, provenance="assumption", ref=a.ref)
    months: list[MonthFacts] = []
    if body.annual_kwh is not None:
        end = body.year_end or _previous_month(today)
        keys = _twelve_months_to(end)
        per = spread(body.annual_kwh, keys, off)
        note = (
            f"the year's {body.annual_kwh:,.0f} kWh spread over the twelve months to {end:%b %Y} in "
            "proportion to each month's working days; replace with the bills' figures when you have them"
        )
        for m in keys:
            months.append(
                MonthFacts(
                    month=m,
                    energy=Fact(value=per[m], provenance="assumption", ref=defaults.assumption(note)),
                    max_kva=_demand_fact(body, m),
                    power_factor=pf_fact,
                )
            )
    else:
        for tm in body.months or []:
            months.append(
                MonthFacts(
                    month=tm.month,
                    energy=Fact(value=tm.kwh),
                    max_kva=Fact(value=tm.max_kva)
                    if tm.max_kva is not None
                    else _demand_fact(body, tm.month),
                    power_factor=pf_fact,
                    bill_inr=Fact(value=tm.bill_inr) if tm.bill_inr is not None else None,
                )
            )

    def f(v: Any) -> Any:
        return Fact(value=v)

    return SiteIntake(
        client_name=f(body.client_name),
        site_name=f(body.site_name),
        state=f(body.state),
        discom=f(body.discom),
        category=f(body.category),
        voltage_kv=f(body.voltage_kv),
        contract_demand_kva=f(body.contract_demand_kva),
        consumer_number=f(body.consumer_number) if body.consumer_number else None,
        rate_block=_rate_block(body),
        industry_shape=f(body.industry_shape),
        weekly_off=(
            Fact(value=off_days, provenance="assumption", ref=off_ref) if off_ref is not None else f(off_days)
        ),
        shifts=f(body.shifts) if body.shifts else None,
        land_acres=f(body.land_acres) if body.land_acres is not None else None,
        roof_sqm=f(body.roof_sqm) if body.roof_sqm is not None else None,
        open_access=f(body.open_access) if body.open_access else None,
        months=months,
        assets=body.assets,
    )


def _rate_block(body: TypedIn) -> Fact[str] | None:
    """The schedule's supply area (UP splits urban and rural): as typed, else the state's usual one."""
    if body.rate_block:
        return Fact(value=body.rate_block)
    a = defaults.rate_block(body.state)
    return Fact(value=a.value, provenance="assumption", ref=a.ref) if a is not None else None


def _demand_fact(body: TypedIn, month: date) -> Fact[Decimal] | None:
    if body.max_demand_kva is not None:
        return Fact(
            value=body.max_demand_kva,
            provenance="assumption",
            ref=defaults.assumption(
                f"the recorded demand of {body.max_demand_kva} kVA stated for the year, "
                f"taken for {month:%b %Y}"
            ),
        )
    return None


def _previous_month(today: date) -> date:
    return date(today.year, today.month - 1, 1) if today.month > 1 else date(today.year - 1, 12, 1)


def default_weekly_off(shape_id: str) -> list[int]:
    """The shape's non-working days (what the form shows before the client changes it)."""
    return sorted(set(range(7)) - set(working_days(shape_id)))
