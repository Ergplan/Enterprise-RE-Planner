"""Landed cost at the meter for every source (Stage 4). Pure: approved rule rows, prices and
scenario inputs in; a waterfall of SourcedValues (INR per kWh consumed) out.

Order and meaning of the lines (master prompt Stage 4):
1. generation price P — PPA tariff (scenario), IEX MCP (price series), LCOE/LCOS, thermal variable cost;
2. per-kWh charges levied on injection (STU transmission, wheeling, ISTS) and the loss gross-up of
   P and those charges: (P + charges) × (1/Π(1 − loss) − 1) over the loss stages the power crosses;
3. capacity charges (INR/MW/month) over the month's scheduled energy (capacity × CUF × hours);
4. per-kWh charges at drawal: CSS, additional surcharge, duty on OA, DSM, standby/grid support, and
   the banking charge on the full injected quantity, labelled as the upper bound (Stage 5 settles
   the banked quantity);
5. the ISTS waiver by commissioning date, on ISTS charges and losses;
6. exemptions by scope (captive, group captive, GEOA, voltage, RE waivers with sunset), each a line
   citing its rule row.
A component the rulebook does not hold is a named gap; nothing is estimated (rule 13).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from ..core.sourced import SourcedValue, derive
from ..core.units import Unit
from ..rulebook.models import RuleView
from ..rulebook.scope import matches

HUNDRED = Decimal(100)
HOURS_IN_MONTH = Decimal(8760) / 12  # 730, for INR/MW/month over scheduled energy
DAYS_IN_MONTH = Decimal(365) / 12  # INR/MW/day → INR/MW/month


@dataclass(frozen=True)
class SourceSpec:
    id: str
    label: str
    connection: str  # ists | intra_state | behind_meter | discom
    source: str  # scope source: solar | wind | hybrid | bess | pumped_storage | iex | thermal
    price_kind: str  # ppa | iex | lcoe | lcos | thermal | grid | green_tariff
    iex_segment: str | None = None
    open_access: bool = True


SOURCES: list[SourceSpec] = [
    SourceSpec("discom_grid", "DISCOM grid supply", "discom", "any", "grid", open_access=False),
    SourceSpec(
        "discom_green_tariff", "DISCOM green tariff", "discom", "any", "green_tariff", open_access=False
    ),
    SourceSpec(
        "rooftop_pv", "Rooftop solar (behind the meter)", "behind_meter", "solar", "lcoe", open_access=False
    ),
    SourceSpec("btm_bess", "Battery behind the meter", "behind_meter", "bess", "lcos", open_access=False),
    SourceSpec("oa_solar_intra", "Open-access solar, intra-state", "intra_state", "solar", "ppa"),
    SourceSpec("oa_wind_intra", "Open-access wind, intra-state", "intra_state", "wind", "ppa"),
    SourceSpec("oa_hybrid_intra", "Open-access hybrid, intra-state", "intra_state", "hybrid", "ppa"),
    SourceSpec("oa_solar_ists", "Open-access solar, ISTS", "ists", "solar", "ppa"),
    SourceSpec("oa_wind_ists", "Open-access wind, ISTS", "ists", "wind", "ppa"),
    SourceSpec("oa_hybrid_ists", "Open-access hybrid, ISTS", "ists", "hybrid", "ppa"),
    SourceSpec("oa_bess", "Open-access storage", "intra_state", "bess", "ppa"),
    SourceSpec("pumped_storage", "Pumped storage (ISTS)", "ists", "pumped_storage", "ppa"),
    SourceSpec("iex_dam", "IEX day-ahead (DAM)", "ists", "iex", "iex", "dam"),
    SourceSpec("iex_rtm", "IEX real-time (RTM)", "ists", "iex", "iex", "rtm"),
    SourceSpec("iex_gdam", "IEX green day-ahead (GDAM)", "ists", "iex", "iex", "gdam"),
    SourceSpec("iex_gtam", "IEX green term-ahead (G-TAM)", "ists", "iex", "iex", "gtam"),
    SourceSpec("iex_tam", "IEX term-ahead (TAM)", "ists", "iex", "iex", "tam"),
    SourceSpec("iex_hpdam", "IEX high-price day-ahead (HP-DAM)", "ists", "iex", "iex", "hpdam"),
    SourceSpec(
        "captive_thermal", "Captive thermal plant", "behind_meter", "thermal", "thermal", open_access=False
    ),
    SourceSpec("group_captive", "Group captive solar, intra-state", "intra_state", "solar", "ppa"),
]
SOURCE_BY_ID = {s.id: s for s in SOURCES}

INJECTION_COMPONENTS = ("ists_transmission", "stu_transmission", "wheeling")
LOSS_COMPONENTS = ("ists_losses", "stu_losses", "wheeling_losses")
DRAWAL_COMPONENTS = (
    "cross_subsidy_surcharge",
    "additional_surcharge",
    "electricity_duty_oa",
    "dsm_passthrough",
    "standby_charge",
    "grid_support_charge",
    "exchange_fee",
    "trading_margin",
)
CAPACITY_BASES = ("inr_per_mw_month", "inr_per_kw_month", "inr_per_mw_day")
ISTS_COMPONENTS = ("ists_transmission", "ists_losses")


@dataclass(frozen=True)
class Scenario:
    """What the client is weighing for one source. Every value is cited (client_stated or assumption)."""

    price: SourcedValue  # INR/kWh at the generator bus (or the bus price for IEX, avoided cost for the grid)
    ownership: str = "third_party"  # captive | group_captive | third_party | discom
    commissioned: date | None = None
    capacity_mw: SourcedValue | None = None
    cuf_pct: SourcedValue | None = None
    on: date = date(2026, 11, 1)
    geoa: bool = False  # Green Energy Open Access consumer keeping its contract demand
    extra: tuple[
        SourcedValue, ...
    ] = ()  # source-specific additions (group-captive equity cost, charging energy)


@dataclass
class Waterfall:
    source: str
    label: str
    lines: list[SourcedValue]
    total: SourcedValue
    gaps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    rules_used: list[str] = field(default_factory=list)
    delivered: SourcedValue | None = None  # share of injected energy that reaches the meter (after losses)

    def coefficient(self) -> tuple[Decimal, Decimal]:
        """total = a × P + b: the price multiplier and the price-independent rest (for block series)."""
        return self._a, self.total.value - self._a * self.lines[0].value

    _a: Decimal = Decimal(1)


def _val(row: RuleView, ctx: dict[str, Any]) -> tuple[Decimal | None, str]:
    """The row's value for this connection (value_by_voltage keyed by kV when tabulated)."""
    body = row.body
    vbv = body.get("value_by_voltage") or {}
    if vbv and ctx.get("voltage_kv") is not None:
        kv = Decimal(str(ctx["voltage_kv"]))
        keys = sorted(vbv, key=lambda k: Decimal(k))
        pick = next((k for k in keys if kv <= Decimal(k)), keys[-1])
        return Decimal(str(vbv[pick])), f"/value_by_voltage/{pick}"
    if body.get("value") in (None, ""):
        return None, "/value"
    return Decimal(str(body["value"])), "/value"


def _sv(row: RuleView, pointer: str, value: Decimal, unit: Unit, label: str) -> SourcedValue:
    return SourcedValue(value=value, unit=unit, source_refs=(row.ref(pointer),), label=label)


def _exemption_applies(ex: dict[str, Any], ctx: dict[str, Any], sc: Scenario) -> bool:
    cond = ex["condition"]
    if ex.get("sunset") and date.fromisoformat(str(ex["sunset"])) < sc.on:
        return False
    if cond == "captive_26_51":
        return sc.ownership == "captive"
    if cond == "group_captive":
        return sc.ownership == "group_captive"
    if cond == "geoa_contract_demand_not_reduced":
        return sc.geoa
    if cond == "behind_meter":
        return ctx.get("connection") == "behind_meter"
    if cond == "re_source_waiver":
        return ctx.get("source") in ("solar", "wind", "hybrid", "bess", "pumped_storage")
    if cond == "consumer_voltage_at_or_above_kv":
        return ex.get("param") is not None and Decimal(str(ctx.get("voltage_kv", 0))) >= Decimal(
            str(ex["param"])
        )
    if cond == "commissioned_in_band" and sc.commissioned and ex.get("param"):
        a, _, b = str(ex["param"]).partition("..")
        return (not a or sc.commissioned >= date.fromisoformat(a)) and (
            not b or sc.commissioned <= date.fromisoformat(b)
        )
    return False  # `other`: shown with the row, applied only by an analyst's explicit scope


def _ists_waiver(
    rows: Sequence[RuleView], ctx: dict[str, Any], sc: Scenario
) -> tuple[RuleView, int, dict[str, Any]] | None:
    if sc.commissioned is None:
        return None
    for r in rows:
        if ctx.get("source") not in r.body.get("applies_to", []):
            continue
        for i, b in enumerate(r.body.get("bands", [])):
            lo = date.fromisoformat(str(b["commissioned_from"]))
            hi = date.fromisoformat(str(b["commissioned_to"])) if b.get("commissioned_to") else None
            if sc.commissioned >= lo and (hi is None or sc.commissioned <= hi):
                expires = date(sc.commissioned.year + int(b["years"]), sc.commissioned.month, 1)
                if sc.on < expires:
                    return r, i, b
    return None


def evaluate(
    spec: SourceSpec,
    ctx: dict[str, Any],
    sc: Scenario,
    oa_rows: Sequence[RuleView],
    ists_waivers: Sequence[RuleView] = (),
    settlement: RuleView | None = None,
) -> Waterfall:
    """One source's landed cost per kWh at the meter. `ctx` is the connection's scope context with
    `connection`, `source` and `ownership` set for this source; `oa_rows` are the approved oa_charge
    rows of the connection's jurisdiction chain (nearest first)."""
    ctx = {**ctx, "connection": spec.connection, "source": spec.source, "ownership": sc.ownership}
    if sc.capacity_mw is not None:
        ctx["capacity_mw"] = sc.capacity_mw.value
    if sc.commissioned is not None:
        ctx["commissioned"] = sc.commissioned
    lines: list[SourcedValue] = [sc.price]
    gaps: list[str] = []
    notes: list[str] = []
    used: list[str] = []
    a = Decimal(1)
    if not spec.open_access:
        lines.extend(sc.extra)
        total = derive(
            sum((x.value for x in lines), Decimal(0)), Unit.INR_PER_KWH, lines, label="Landed cost"
        )
        return Waterfall(spec.id, spec.label, lines, total, gaps, notes, used)

    applicable = [r for r in oa_rows if matches(r.scope, ctx)]
    by_comp: dict[str, RuleView] = {}
    for row in applicable:  # nearest jurisdiction first; the first row of a component wins
        by_comp.setdefault(str(row.body["component"]), row)
    waiver = _ists_waiver(ists_waivers, ctx, sc) if spec.connection == "ists" else None
    if spec.connection == "ists" and not ists_waivers:
        gaps.append("ists_waiver")

    # 2. injection charges and losses
    injection: list[SourcedValue] = []
    for comp in INJECTION_COMPONENTS:
        r: RuleView | None = by_comp.get(comp)
        if r is None:
            if comp == "ists_transmission" and spec.connection == "ists":
                gaps.append("ists_charges")
            elif comp == "wheeling" and spec.connection in ("intra_state", "ists"):
                gaps.append("oa_wheeling")
            continue
        if str(r.body["basis"]) in CAPACITY_BASES:
            continue
        v, ptr = _val(r, ctx)
        if v is None:
            continue
        line = _sv(r, ptr, v, Unit.INR_PER_KWH, str(r.label or comp))
        injection.append(line)
        lines.append(line)
        used.append(r.id)
        ex_lines, ex_used = _exemptions(r, line, ctx, sc)
        lines.extend(ex_lines)
        injection.extend(ex_lines)
        used.extend(ex_used)
    keep = Decimal(1)
    loss_inputs: list[SourcedValue] = []
    for comp in LOSS_COMPONENTS:
        r = by_comp.get(comp)
        if r is None:
            if comp in ("stu_losses", "wheeling_losses") and spec.connection in ("intra_state", "ists"):
                gaps.append("oa_losses")
            continue
        v, ptr = _val(r, ctx)
        if v is None:
            continue
        loss = _sv(r, ptr, v, Unit.PERCENT, str(r.label or comp))
        if comp == "ists_losses" and waiver is not None:
            wr, wi, wb = waiver
            w = _sv(
                wr,
                f"/bands/{wi}/losses_waived_pct",
                Decimal(str(wb["losses_waived_pct"])),
                Unit.PERCENT,
                "ISTS loss waiver",
            )
            loss = derive(
                v * (1 - w.value / HUNDRED), Unit.PERCENT, [loss, w], label=f"{r.label} after waiver"
            )
            used.append(wr.id)
        keep *= 1 - loss.value / HUNDRED
        loss_inputs.append(loss)
        used.append(r.id)
    delivered = (
        derive(keep, Unit.RATIO, loss_inputs, label="Delivered share after losses") if loss_inputs else None
    )
    if loss_inputs:
        base = sum((x.value for x in [sc.price, *injection]), Decimal(0))
        gross = 1 / keep - 1
        a = 1 / keep
        lines.append(
            derive(
                base * gross,
                Unit.INR_PER_KWH,
                [sc.price, *injection, *loss_inputs],
                label=f"Losses ({', '.join(str(x.label) for x in loss_inputs)})",
            )
        )

    # 3. capacity charges over scheduled energy
    for comp, r in by_comp.items():
        if str(r.body["basis"]) not in CAPACITY_BASES:
            continue
        if sc.capacity_mw is None or sc.cuf_pct is None:
            gaps.append("scheduled_energy")
            continue
        v, ptr = _val(r, ctx)
        if v is None:
            continue
        rate = _sv(r, ptr, v, Unit.INR_PER_MW_MONTH, str(r.label or comp))
        per_mw_month = (
            v
            * {
                "inr_per_mw_month": Decimal(1),
                "inr_per_kw_month": Decimal(1000),
                "inr_per_mw_day": DAYS_IN_MONTH,
            }[str(r.body["basis"])]
        )
        kwh = sc.capacity_mw.value * 1000 * HOURS_IN_MONTH * sc.cuf_pct.value / HUNDRED
        line = derive(
            per_mw_month * sc.capacity_mw.value / kwh,
            Unit.INR_PER_KWH,
            [rate, sc.capacity_mw, sc.cuf_pct],
            label=f"{r.label or comp} over scheduled energy",
        )
        if comp in ISTS_COMPONENTS and waiver is not None:
            line = _waive(line, waiver, "charges_waived_pct", used)
        lines.append(line)
        used.append(r.id)

    # 4. drawal charges
    for comp in DRAWAL_COMPONENTS:
        r = by_comp.get(comp)
        if r is None:
            if comp == "cross_subsidy_surcharge":
                gaps.append("oa_css")
            elif comp == "additional_surcharge":
                gaps.append("oa_additional_surcharge")
            elif comp == "electricity_duty_oa":
                gaps.append("electricity_duty")
            elif comp == "exchange_fee" and spec.price_kind == "iex":
                gaps.append("iex_fees")
            continue
        basis = str(r.body["basis"])
        if basis in CAPACITY_BASES:
            continue
        v, ptr = _val(r, ctx)
        if v is None:
            continue
        if basis == "percent_of_price":
            line = derive(
                sc.price.value * v / HUNDRED,
                Unit.INR_PER_KWH,
                [sc.price, _sv(r, ptr, v, Unit.PERCENT, str(r.label))],
                label=str(r.label or comp),
            )
            a += v / HUNDRED
        else:
            line = _sv(r, ptr, v, Unit.INR_PER_KWH, str(r.label or comp))
        lines.append(line)
        used.append(r.id)
        ex_lines, ex_used = _exemptions(r, line, ctx, sc)
        lines.extend(ex_lines)
        used.extend(ex_used)
    if settlement is not None and sc.ownership in ("captive", "group_captive", "third_party"):
        ch = (settlement.body.get("banking") or {}).get("charge") or {}
        if ch.get("kind") == "in_kind_percent" and ch.get("value") not in (None, ""):
            c = _sv(
                settlement, "/banking/charge/value", Decimal(str(ch["value"])), Unit.PERCENT, "Banking charge"
            )
            so_far = sum((x.value for x in lines), Decimal(0))
            lines.append(
                derive(
                    so_far * (1 / (1 - c.value / HUNDRED) - 1),
                    Unit.INR_PER_KWH,
                    [*lines, c],
                    label="Banking charge, upper bound (all energy banked)",
                )
            )
            a *= 1 / (1 - c.value / HUNDRED)
            notes.append(
                "the banking charge is shown as if every unit were banked; the settlement simulator "
                "(Stage 5) decides the banked quantity"
            )
            used.append(settlement.id)
    lines.extend(sc.extra)
    total = derive(
        sum((x.value for x in lines), Decimal(0)), Unit.INR_PER_KWH, lines, label="Landed cost at the meter"
    )
    wf = Waterfall(
        spec.id, spec.label, lines, total, list(dict.fromkeys(gaps)), notes, list(dict.fromkeys(used))
    )
    wf._a = a
    wf.delivered = delivered
    return wf


def _waive(
    line: SourcedValue, waiver: tuple[RuleView, int, dict[str, Any]], key: str, used: list[str]
) -> SourcedValue:
    wr, wi, wb = waiver
    w = _sv(wr, f"/bands/{wi}/{key}", Decimal(str(wb[key])), Unit.PERCENT, "ISTS waiver")
    used.append(wr.id)
    return derive(
        line.value * (1 - w.value / HUNDRED), Unit.INR_PER_KWH, [line, w], label=f"{line.label} after waiver"
    )


def _exemptions(
    r: RuleView, line: SourcedValue, ctx: dict[str, Any], sc: Scenario
) -> tuple[list[SourcedValue], list[str]]:
    """Exemption lines (negative) for the row's exemptions that apply to this scenario, and the
    exemption fields used (rule id with the exemption's pointer)."""
    out: list[SourcedValue] = []
    used: list[str] = []
    for i, ex in enumerate(r.body.get("exemptions") or []):
        if ex.get("waived_pct") in (None, "") or not _exemption_applies(ex, ctx, sc):
            continue
        w = _sv(
            r,
            f"/exemptions/{i}/waived_pct",
            Decimal(str(ex["waived_pct"])),
            Unit.PERCENT,
            f"Exemption: {ex['condition'].replace('_', ' ')}",
        )
        out.append(
            derive(
                -line.value * w.value / HUNDRED,
                Unit.INR_PER_KWH,
                [line, w],
                label=f"{line.label} · exemption ({ex['condition'].replace('_', ' ')})",
            )
        )
        used.append(f"{r.id}#/exemptions/{i}")
    return out, used
