"""SiteIntake: everything the engines will read about a client's site, filled by any door — bills,
the typed form, or (Stage 7) the voice tools, which reuse these schemas.

Every field is a `Fact`: a value, its provenance (`bill`, `client_stated`, `assumption`) and a
SourceRef. Defaults come from `defaults.py` and are recorded as assumptions; values from bills
carry `bill` refs naming the bill and the billx path. `build()` persists client, site, connection,
assets and the synthesised load profile.
"""

from __future__ import annotations

import calendar
import re
from datetime import date
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.sourced import RefKind, SourceRef
from ..db.models import Asset, Bill, Client, Connection, LoadProfile, Site
from . import bills as bill_store
from . import defaults
from .bill_fields import parse_month
from .profile_synthesis import MonthInput, ShapeNotFound, TodWindow, encode, shape, shape_ids, synthesise_year

T = TypeVar("T")
Provenance = Literal["bill", "client_stated", "assumption"]
_KIND_OF = {"bill": RefKind.BILL, "client_stated": RefKind.CLIENT_STATED, "assumption": RefKind.ASSUMPTION}


class Fact(BaseModel, Generic[T]):  # noqa: UP046 (pydantic generic model)
    """One input value with where it came from. A typed value needs no ref (client_stated is made);
    an assumption needs a note; a bill value needs a bill ref."""

    model_config = ConfigDict(extra="forbid")

    value: T
    provenance: Provenance = "client_stated"
    ref: SourceRef | None = None

    @model_validator(mode="after")
    def _ref_matches_provenance(self) -> Fact[T]:
        if self.ref is None:
            if self.provenance != "client_stated":
                raise ValueError(f"a {self.provenance} value needs its source_ref")
            self.ref = SourceRef(kind=RefKind.CLIENT_STATED)
        if self.ref.kind != _KIND_OF[self.provenance]:
            raise ValueError(f"provenance {self.provenance} with a {self.ref.kind} ref")
        return self


def stated(v: Any) -> Fact[Any]:
    return Fact(value=v)


def assumed(a: defaults.Assumed) -> Fact[Any]:
    return Fact(value=a.value, provenance="assumption", ref=a.ref)


def from_bill(v: bill_store.BillValue, value: Any) -> Fact[Any]:
    return Fact(value=value, provenance="bill", ref=v.ref)


_HHMM = re.compile(r"^([01]\d|2[0-4]):[0-5]\d$")


class TodEnergy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str
    end: str
    energy: Fact[Decimal]
    slot: str | None = None  # the bill's slot name, when the window came from a bill

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        if not _HHMM.match(v) or (v.startswith("24") and v != "24:00") or int(v[3:]) % 15:
            raise ValueError("a time is HH:MM on a quarter hour, 00:00–24:00")
        return v


class MonthFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: date
    energy: Fact[Decimal]
    energy_unit: Literal["kWh", "kVAh"] = "kWh"
    tod: list[TodEnergy] = Field(default_factory=list)
    max_kva: Fact[Decimal] | None = None
    power_factor: Fact[Decimal] | None = None
    bill_inr: Fact[Decimal] | None = None
    bill_id: str | None = None
    shutdown_days: list[int] = Field(default_factory=list)
    unmapped_tod_slots: list[str] = Field(default_factory=list)

    @field_validator("month")
    @classmethod
    def _first_of_month(cls, v: date) -> date:
        return v.replace(day=1)

    @model_validator(mode="after")
    def _checks(self) -> MonthFacts:
        if self.energy.value <= 0:
            raise ValueError("monthly energy must be positive")
        if self.max_kva is not None and self.max_kva.value <= 0:
            raise ValueError("maximum demand must be positive")
        if self.power_factor is not None and not (Decimal("0.3") <= self.power_factor.value <= Decimal("1")):
            raise ValueError("power factor must be between 0.3 and 1")
        n = calendar.monthrange(self.month.year, self.month.month)[1]
        if any(not 1 <= d <= n for d in self.shutdown_days):
            raise ValueError(f"shutdown days must be within 1–{n}")
        if self.tod:
            tod_sum = sum((t.energy.value for t in self.tod), Decimal(0))
            if tod_sum > self.energy.value * Decimal("1.001"):
                raise ValueError("the ToD split adds up to more than the month's energy")
        return self


ASSET_KINDS = ("rooftop_pv", "captive_thermal", "waste_heat", "bess", "dg")


class CaptiveThermal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fuel: str
    gcv_kcal_per_kg: Decimal | None = None
    heat_rate_kcal_per_kwh: Decimal | None = None
    capacity_mw: Decimal = Field(gt=0)
    technical_minimum_pct: Decimal = Field(ge=0, le=100)
    ramp_up_mw_per_block: Decimal | None = Field(default=None, gt=0)
    ramp_down_mw_per_block: Decimal | None = Field(default=None, gt=0)
    min_up_blocks: int | None = Field(default=None, ge=0)
    min_down_blocks: int | None = Field(default=None, ge=0)
    variable_cost_inr_per_kwh: Decimal | None = Field(default=None, ge=0)
    fuel_price_inr_per_tonne: Decimal | None = Field(default=None, ge=0)
    aux_consumption_pct: Decimal = Field(default=Decimal("8"), ge=0, le=30)
    must_run: bool = False

    @model_validator(mode="after")
    def _cost(self) -> CaptiveThermal:
        if self.variable_cost_inr_per_kwh is None and not (
            self.fuel_price_inr_per_tonne is not None and self.gcv_kcal_per_kg and self.heat_rate_kcal_per_kwh
        ):
            raise ValueError("give variable_cost_inr_per_kwh, or fuel_price with gcv and heat_rate")
        return self


class RooftopPv(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capacity_kwp: Decimal = Field(gt=0)
    metering: Literal["net", "gross", "behind_the_meter"] = "behind_the_meter"
    commissioned: date | None = None


class WasteHeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capacity_mw: Decimal = Field(gt=0)
    availability_pct: Decimal = Field(default=Decimal("90"), ge=0, le=100)


class Bess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    power_mw: Decimal = Field(gt=0)
    energy_mwh: Decimal = Field(gt=0)
    round_trip_efficiency_pct: Decimal = Field(default=Decimal("88"), gt=0, le=100)


class DieselGenerator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capacity_kva: Decimal = Field(gt=0)
    cost_inr_per_kwh: Decimal | None = Field(default=None, ge=0)


ASSET_MODELS: dict[str, type[BaseModel]] = {
    "rooftop_pv": RooftopPv,
    "captive_thermal": CaptiveThermal,
    "waste_heat": WasteHeat,
    "bess": Bess,
    "dg": DieselGenerator,
}


class AssetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["rooftop_pv", "captive_thermal", "waste_heat", "bess", "dg"]
    params: dict[str, Any]
    provenance: Provenance = "client_stated"

    @model_validator(mode="after")
    def _params_valid(self) -> AssetIn:
        self.params = (
            ASSET_MODELS[self.kind].model_validate(self.params).model_dump(mode="json", exclude_none=True)
        )
        return self


class Shift(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str
    end: str
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5])


class SiteIntake(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_name: Fact[str]
    site_name: Fact[str]
    state: Fact[str]
    discom: Fact[str]
    category: Fact[str]
    voltage_kv: Fact[Decimal]
    contract_demand_kva: Fact[Decimal]
    consumer_number: Fact[str] | None = None
    rate_block: Fact[str] | None = None
    industry_shape: Fact[str]
    weekly_off: Fact[list[int]]
    shifts: Fact[list[Shift]] | None = None
    land_acres: Fact[Decimal] | None = None
    roof_sqm: Fact[Decimal] | None = None
    months: list[MonthFacts] = Field(min_length=1, max_length=12)
    assets: list[AssetIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> SiteIntake:
        st = defaults.state_of(self.discom.value)
        if st is None:
            raise ValueError(f"unknown DISCOM {self.discom.value!r}")
        if st != self.state.value:
            raise ValueError(f"{self.discom.value} is in {st}, not {self.state.value}")
        if self.voltage_kv.value <= 0 or self.contract_demand_kva.value <= 0:
            raise ValueError("voltage and contract demand must be positive")
        if self.industry_shape.value not in shape_ids():
            raise ValueError(
                f"unknown industry shape {self.industry_shape.value!r}; one of {', '.join(shape_ids())}"
            )
        if any(not 0 <= d <= 6 for d in self.weekly_off.value):
            raise ValueError("weekly off days are 0 (Mon) to 6 (Sun)")
        months = [m.month for m in self.months]
        if len(set(months)) != len(months):
            raise ValueError("each month may appear once")
        return self

    def warnings(self) -> list[str]:
        out = []
        cd = self.contract_demand_kva.value
        for m in self.months:
            if m.max_kva is not None and m.max_kva.value > cd * Decimal("1.2"):
                out.append(
                    f"{m.month:%b %Y}: recorded demand {m.max_kva.value} kVA exceeds "
                    f"contract demand {cd} kVA by more than 20%"
                )
            if m.unmapped_tod_slots:
                out.append(
                    f"{m.month:%b %Y}: the bill's ToD slots {', '.join(m.unmapped_tod_slots)} "
                    "do not name their hours; "
                    "the month's total is used — type the hours to use the split"
                )
        if len(self.months) < 12:
            out.append(f"{len(self.months)} of 12 months given; the other months are extrapolated from them")
        return out


# ---------------------------------------------------------------- filling from bills

_WINDOW = re.compile(r"(\d{1,2})[:.](\d{2})\s*(?:hrs?)?\s*(?:-|–|to)\s*(\d{1,2})[:.](\d{2})")


def window_of(slot: str | None) -> tuple[str, str] | None:
    """A bill ToD slot that prints its hours ('19:00-03:00', '05.00 to 10.00 hrs') → (start, end)."""
    if not slot:
        return None
    m = _WINDOW.search(slot)
    if not m:
        return None
    a, b = f"{int(m.group(1)):02d}:{m.group(2)}", f"{int(m.group(3)):02d}:{m.group(4)}"
    return (a, b) if _HHMM.match(a) and _HHMM.match(b) else None


def month_from_bill(session: Session, bill: Bill) -> MonthFacts:
    v = bill_store.values(session, bill)
    month = parse_month(v["period.bill_month"].value) if "period.bill_month" in v else bill.bill_month
    if month is None:
        raise ValueError(f"bill {bill.id} has no bill month")
    if "energy.kwh" in v and v["energy.kwh"].dec:
        energy, unit = from_bill(v["energy.kwh"], v["energy.kwh"].dec), "kWh"
    elif "energy.kvah" in v and v["energy.kvah"].dec:
        energy, unit = from_bill(v["energy.kvah"], v["energy.kvah"].dec), "kVAh"
    else:
        raise ValueError(f"bill {bill.id} has no energy")
    tod, unmapped = [], []
    for i, slot in enumerate(bill_store.tod_slots(bill)):
        bv = v.get(f"energy.tod.{i}.kwh")
        w = window_of(slot)
        if bv is None or bv.dec is None:
            continue
        if w is None:
            unmapped.append(slot or f"slot {i + 1}")
            continue
        tod.append(TodEnergy(start=w[0], end=w[1], energy=from_bill(bv, bv.dec), slot=slot))
    if unmapped:
        tod = []  # a partial split would mislead; the month's total is used until the client types the hours
    return MonthFacts(
        month=month,
        energy=energy,
        energy_unit=unit,
        tod=tod,
        bill_id=bill.id,
        unmapped_tod_slots=unmapped,
        max_kva=from_bill(v["demand.max_kva"], v["demand.max_kva"].dec) if "demand.max_kva" in v else None,
        power_factor=from_bill(v["energy.power_factor"], v["energy.power_factor"].dec)
        if "energy.power_factor" in v and v["energy.power_factor"].dec
        else None,
        bill_inr=from_bill(v["totals.current_charges"], v["totals.current_charges"].dec)
        if "totals.current_charges" in v and v["totals.current_charges"].dec
        else None,
    )


def from_bills(session: Session, bill_ids: list[str], overrides: dict[str, Any] | None = None) -> SiteIntake:
    """A SiteIntake prefilled from accepted bills of one connection; what no bill prints is a
    default (an assumption) or comes from `overrides` (the client's typed values)."""
    bills = [session.get(Bill, i) for i in bill_ids]
    if not bills or any(b is None for b in bills):
        raise bill_store.BillNotFound(", ".join(bill_ids))
    ready = [b for b in bills if b is not None]
    not_ready = [b.id for b in ready if not b.accepted]
    if not_ready:
        raise ValueError(f"bills not accepted yet (confirm their fields first): {', '.join(not_ready)}")
    latest = max(ready, key=lambda b: b.bill_month or date.min)
    v = bill_store.values(session, latest)
    o = dict(overrides or {})

    discom_id = defaults.discom_from_profile(bill_store.profile_id(latest))
    if "discom" in o:
        discom = stated(o.pop("discom"))
    elif discom_id:
        discom = Fact(
            value=discom_id,
            provenance="assumption",
            ref=defaults.assumption(f"DISCOM from billx's layout profile '{bill_store.profile_id(latest)}'"),
        )
    else:
        raise ValueError("billx did not recognise the DISCOM; say which DISCOM supplies the site")
    st = defaults.state_of(discom.value) or ""
    printed = v["tariff.category"].value if "tariff.category" in v else None
    if "category" in o:
        category = stated(o.pop("category"))
    else:
        mapped = defaults.category_from_printed(st, printed)
        if mapped is None:
            raise ValueError(
                f"the bill's category {printed!r} is not one ergPLAN knows for {st}; "
                "say which category applies"
            )
        category = assumed(mapped)
    voltage = (
        stated(Decimal(str(o.pop("voltage_kv"))))
        if "voltage_kv" in o
        else assumed(defaults.voltage_kv(category.value))
    )
    if "contract_demand_kva" in o:
        cd = stated(Decimal(str(o.pop("contract_demand_kva"))))
    elif "demand.contract_kva" in v and v["demand.contract_kva"].dec:
        cd = from_bill(v["demand.contract_kva"], v["demand.contract_kva"].dec)
    else:
        raise ValueError("contract demand is not on the bill; type it")
    shape_id = str(o.pop("industry_shape")) if "industry_shape" in o else None
    shape_fact = stated(shape_id) if shape_id else assumed(defaults.industry_shape())
    weekly_off = (
        stated(list(o.pop("weekly_off")))
        if "weekly_off" in o
        else assumed(defaults.weekly_off(shape_fact.value))
    )
    name = v["consumer.name"].value if "consumer.name" in v else None
    client_name = (
        stated(o.pop("client_name"))
        if "client_name" in o
        else (from_bill(v["consumer.name"], name) if name else stated("Unnamed client"))
    )
    months = {m.month: m for m in (month_from_bill(session, b) for b in ready)}
    data: dict[str, Any] = dict(
        client_name=client_name,
        site_name=stated(o.pop("site_name", None) or f"{discom.value.upper()} connection"),
        state=Fact(value=st, provenance="assumption", ref=defaults.assumption(f"state of {discom.value}")),
        discom=discom,
        category=category,
        voltage_kv=voltage,
        contract_demand_kva=cd,
        consumer_number=from_bill(v["consumer.account_number"], v["consumer.account_number"].value)
        if "consumer.account_number" in v
        else None,
        industry_shape=shape_fact,
        weekly_off=weekly_off,
        months=[months[k] for k in sorted(months)][-12:],
    )
    for k, val in o.items():
        data[k] = stated(val) if k in SiteIntake.model_fields and not isinstance(val, (dict, list)) else val
    return SiteIntake.model_validate(data)


# ---------------------------------------------------------------- persistence


def _prov(**facts: Fact[Any] | None) -> dict[str, Any]:
    return {
        k: {"provenance": f.provenance, "source_ref": f.ref.to_json() if f.ref else None}
        for k, f in facts.items()
        if f is not None
    }


def month_inputs(intake: SiteIntake) -> list[MonthInput]:
    out = []
    for m in intake.months:
        pf = m.power_factor.value if m.power_factor else None
        kwh = m.energy.value if m.energy_unit == "kWh" else m.energy.value * (pf or Decimal("0.95"))
        out.append(
            MonthInput(
                month=m.month,
                kwh=kwh,
                max_kva=m.max_kva.value if m.max_kva else None,
                power_factor=pf,
                tod=tuple(
                    TodWindow(
                        t.start,
                        t.end,
                        t.energy.value
                        if m.energy_unit == "kWh"
                        else t.energy.value * (pf or Decimal("0.95")),
                    )
                    for t in m.tod
                ),
                shutdown_days=tuple(m.shutdown_days),
            )
        )
    return out


def synthesise(session: Session, connection_id: str, intake: SiteIntake) -> LoadProfile:
    try:
        shape(intake.industry_shape.value)
    except ShapeNotFound as e:
        raise ValueError(f"unknown industry shape {e}") from e
    prof = synthesise_year(
        month_inputs(intake), intake.industry_shape.value, weekly_off=tuple(intake.weekly_off.value)
    )
    prof.method["inputs"] = {
        "industry_shape": _prov(f=intake.industry_shape)["f"],
        "weekly_off": _prov(f=intake.weekly_off)["f"],
        "months": [
            {
                "month": m.month.isoformat(),
                "bill_id": m.bill_id,
                "energy_unit": m.energy_unit,
                **_prov(energy=m.energy, max_kva=m.max_kva, power_factor=m.power_factor),
            }
            for m in intake.months
        ],
    }
    version = (
        session.scalar(
            select(func.max(LoadProfile.version)).where(LoadProfile.connection_id == connection_id)
        )
        or 0
    ) + 1
    lp = LoadProfile(
        connection_id=connection_id,
        version=version,
        provenance="synthesised",
        resolution_min=15,
        year_start=prof.year_start,
        blocks=len(prof.kw),
        series_kw=encode(prof.as_decimals()),
        method=prof.method,
    )
    session.add(lp)
    session.flush()
    return lp


def build(
    session: Session, intake: SiteIntake, actor: str, connection_id: str | None = None
) -> dict[str, Any]:
    """Persist the intake: client, site, connection (new or updated), assets, the bills' link to
    the connection, and a synthesised load profile. Returns the ids and warnings."""
    if connection_id:
        conn = session.get(Connection, connection_id)
        if conn is None:
            raise LookupError(connection_id)
        site = session.get(Site, conn.site_id)
        assert site is not None
        client = session.get(Client, site.client_id)
        assert client is not None
    else:
        client = Client(name=intake.client_name.value, created_by=actor)
        session.add(client)
        session.flush()
        site = Site(client_id=client.id, name=intake.site_name.value, state=intake.state.value)
        session.add(site)
        session.flush()
        conn = Connection(site_id=site.id, discom_id=intake.discom.value)
        session.add(conn)
    client.name = intake.client_name.value
    site.name, site.state = intake.site_name.value, intake.state.value
    site.industry_shape = intake.industry_shape.value
    site.weekly_off = list(intake.weekly_off.value)
    site.shift_hours = {"shifts": [s.model_dump() for s in intake.shifts.value]} if intake.shifts else {}
    site.land_acres = intake.land_acres.value if intake.land_acres else None
    site.roof_sqm = intake.roof_sqm.value if intake.roof_sqm else None
    site.provenance = _prov(
        client_name=intake.client_name,
        site_name=intake.site_name,
        state=intake.state,
        industry_shape=intake.industry_shape,
        weekly_off=intake.weekly_off,
        shifts=intake.shifts,
        land_acres=intake.land_acres,
        roof_sqm=intake.roof_sqm,
    )
    conn.discom_id = intake.discom.value
    conn.tariff_category = intake.category.value
    conn.voltage_kv = intake.voltage_kv.value
    conn.contract_demand_kva = intake.contract_demand_kva.value
    conn.connection_kind = defaults.connection_kind(intake.voltage_kv.value)
    conn.consumer_number = intake.consumer_number.value if intake.consumer_number else None
    conn.rate_block = intake.rate_block.value if intake.rate_block else None
    conn.provenance = _prov(
        discom=intake.discom,
        category=intake.category,
        voltage_kv=intake.voltage_kv,
        contract_demand_kva=intake.contract_demand_kva,
        consumer_number=intake.consumer_number,
        rate_block=intake.rate_block,
    )
    session.flush()
    for a in intake.assets:
        session.add(
            Asset(site_id=site.id, kind=a.kind, params=a.params, provenance={"provenance": a.provenance})
        )
    for m in intake.months:
        if m.bill_id:
            b = session.get(Bill, m.bill_id)
            if b is not None:
                b.connection_id = conn.id
    lp = synthesise(session, conn.id, intake)
    return {
        "client_id": client.id,
        "site_id": site.id,
        "connection_id": conn.id,
        "load_profile_id": lp.id,
        "load_profile_version": lp.version,
        "warnings": intake.warnings(),
    }
