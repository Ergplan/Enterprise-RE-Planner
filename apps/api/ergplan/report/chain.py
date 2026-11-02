"""The chain from the generator to the saving, for one settled run, link by link, as the audit screen
shows it (and as a client's own working is reconciled against it):

1. per source, the landed cost per kWh at the meter: the price, each charge on injection, each loss
   stage (the energy lost, paid for), capacity charges over scheduled energy, each charge at drawal,
   each exemption, the banking charge; a running total to the landed cost;
2. per source, the energy: capacity, energy at the meter, set off against consumption, banked,
   not banked; for the site, consumption, set off, withdrawn from the bank, lapsed, drawn from the grid;
3. the money for the year: the grid bill today line by line, the bill with the plan line by line
   (grid energy and demand, each source's energy, own plant's fixed cost), and the saving.

Read from the run's stored summary only (the numbers are the plan's; nothing is recomputed), so the
chain always agrees with what the plan shows. Every value carries its source_refs (invariant 1)."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.sourced import SourcedValue, SourceRef, derive
from ..core.units import Unit
from ..db.models import Connection, Run, RunResult, Scenario, Site
from ..engine.gaps import GAPS

EXTRA: dict[str, Any] = {
    "owner": "run_results.summary",
    "ref_kinds": [
        "order",
        "regulation",
        "derived",
        "assumption",
        "client_stated",
        "bill",
        "market",
        "measured",
    ],
}


def _o() -> Any:
    return Field(default=None, json_schema_extra=EXTRA)


def _f() -> Any:
    return Field(json_schema_extra=EXTRA)


class ChainStep(BaseModel):
    """One link. `key` is stable across runs of the scenario, so a client's figure for the link
    stays attached to it when the plan is run again."""

    key: str
    # price | charge | loss | capacity | drawal | exemption | banking | extra | energy | money | total
    kind: str
    label: str
    rate: SourcedValue | None = _o()  # as the rule states it: INR/kWh, percent, INR/MW/month
    value: SourcedValue = _f()  # its effect: INR/kWh (landed), kWh (energy) or INR (money)
    running: SourcedValue | None = _o()  # the landed cost so far
    rule_id: str | None = None
    pointer: str | None = None  # the rule row's field (JSON pointer) the rate comes from
    editable: str | None = None  # a client's own figure (price, capacity…): the scenario field it changes


class SourceChain(BaseModel):
    id: str
    kind: str
    label: str
    ownership: str | None
    capacity: SourcedValue | None = _o()
    slot: str | None  # the time-of-day slot shown (the landed cost of a PPA is the same in every slot)
    slots_differ: bool
    landed: list[ChainStep]
    landed_total: SourcedValue | None = _o()
    energy: list[ChainStep]
    gaps: dict[str, str]


class Chain(BaseModel):
    connection_id: str
    site: str
    state: str | None
    discom: str
    scenario_id: str
    scenario: str
    run_id: str
    finished_at: datetime | None
    settlement_rule: str | None
    settlement_ref: SourceRef | None
    sources: list[SourceChain]
    energy: list[ChainStep]
    money: list[ChainStep]
    saving: SourcedValue = _f()
    notes: list[str]


class ChainNotFound(LookupError):
    pass


def _sv(x: Any) -> SourcedValue | None:
    return SourcedValue.model_validate(x) if isinstance(x, dict) and x.get("source_refs") else None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "line"


MONEY_LABEL = {
    "grid_energy": "Grid energy",
    "demand": "Demand charges",
    "excess_demand": "Excess demand penalty",
}


def latest_run(
    s: Session, connection_id: str, scenario_id: str | None = None
) -> tuple[Scenario, Run, RunResult]:
    """The run the chain is read from: the scenario's latest settled run, or, when no scenario is
    named, the connection's best (the largest saving), as the plan recommends."""
    conn = s.get(Connection, connection_id)
    if conn is None:
        raise ChainNotFound(connection_id)
    q = select(Scenario).where(Scenario.connection_id == conn.id)
    if scenario_id:
        q = q.where(Scenario.id == scenario_id)
    best: tuple[Scenario, Run, RunResult] | None = None
    for sc in s.scalars(q):
        run = s.scalars(
            select(Run)
            .where(Run.scenario_id == sc.id, Run.status == "done", Run.replay_of.is_(None))
            .order_by(Run.created_at.desc())
        ).first()
        rr = s.get(RunResult, run.id) if run else None
        if run is None or rr is None:
            continue
        if best is None or Decimal(rr.summary["annual"]["saving"]["value"]) > Decimal(
            best[2].summary["annual"]["saving"]["value"]
        ):
            best = (sc, run, rr)
    if best is None:
        raise ChainNotFound("no settled run for this connection")
    return best


def _landed(sid: str, size: dict[str, Any]) -> tuple[list[ChainStep], str | None, bool, SourcedValue | None]:
    chains: dict[str, list[dict[str, Any]]] = size.get("chain") or {}
    waterfalls: dict[str, list[dict[str, Any]]] = size.get("waterfall") or {}
    slots = list(chains or waterfalls)
    if not slots:
        return [], None, False, None
    slot = slots[0]
    steps: list[ChainStep] = []
    seen: dict[str, int] = {}
    running: SourcedValue | None = None

    def add(
        kind: str,
        component: str,
        label: str,
        value: SourcedValue,
        rate: SourcedValue | None,
        rule_id: str | None,
        pointer: str | None,
    ) -> None:
        nonlocal running
        base = f"{sid}.{kind}.{component}"
        n = seen.get(base, 0)
        seen[base] = n + 1
        running = (
            value
            if running is None
            else derive(
                running.value + value.value, Unit.INR_PER_KWH, [running, value], label="Landed cost so far"
            )
        )
        steps.append(
            ChainStep(
                key=base if n == 0 else f"{base}.{n + 1}",
                kind=kind,
                label=label,
                rate=rate,
                value=value,
                running=running,
                rule_id=rule_id,
                pointer=pointer,
                editable="price_inr_per_kwh" if kind == "price" else None,
            )
        )

    if chains:
        for st in chains[slot]:
            value = _sv(st["per_kwh"])
            assert value is not None
            add(
                st["kind"],
                st["component"],
                st["label"],
                value,
                _sv(st.get("rate")),
                st.get("rule_id"),
                st.get("pointer"),
            )
        differ = any(
            [x["per_kwh"]["value"] for x in chains[o]] != [x["per_kwh"]["value"] for x in chains[slot]]
            for o in slots[1:]
        )
    else:  # a run made before the chain was stored: its waterfall lines, without their rates
        for i, raw in enumerate(waterfalls[slot]):
            value = _sv(raw)
            assert value is not None
            label = str(value.label or f"line {i + 1}")
            kind = "price" if i == 0 else "loss" if label.lower().startswith("losses") else "charge"
            add(kind, _slug(label), label, value, None, None, None)
        differ = any(
            [x["value"] for x in waterfalls[o]] != [x["value"] for x in waterfalls[slot]] for o in slots[1:]
        )
    total = (
        derive(running.value, Unit.INR_PER_KWH, [running], label="Landed cost at the meter")
        if running is not None
        else None
    )
    return steps, slot, differ, total


def _energy_step(key: str, label: str, x: Any, kind: str = "energy") -> ChainStep | None:
    v = _sv(x)
    return ChainStep(key=key, kind=kind, label=label, value=v) if v is not None else None


def build(s: Session, connection_id: str, scenario_id: str | None = None) -> Chain:
    sc, run, rr = latest_run(s, connection_id, scenario_id)
    sm = rr.summary
    conn = s.get(Connection, connection_id)
    assert conn is not None
    site = s.get(Site, conn.site_id)
    annual = sm["annual"]
    before_ref = _sv(annual["before"])
    after_ref = _sv(annual["after"])
    assert before_ref is not None and after_ref is not None
    sources: list[SourceChain] = []
    for z in sm["sizes"]:
        sid = str(z["id"])
        landed, slot, differ, total = _landed(sid, z)
        energy = [
            st
            for st in (
                _energy_step(f"{sid}.energy.capacity", "Capacity", z.get("kw")),
                _energy_step(
                    f"{sid}.energy.delivered_share",
                    "Share of energy reaching the meter",
                    z.get("delivered_share"),
                ),
                _energy_step(
                    f"{sid}.energy.delivered", "Energy at the meter, for the year", z.get("delivered_kwh")
                ),
                _energy_step(f"{sid}.energy.setoff", "Set off against consumption", z.get("setoff_kwh")),
                _energy_step(
                    f"{sid}.energy.banked", "Banked (after the charge in kind)", z.get("banked_kwh")
                ),
                _energy_step(f"{sid}.energy.unbanked", "Surplus not banked", z.get("unbanked_kwh")),
                _energy_step(f"{sid}.energy.storage", "Battery energy", z.get("kwh")),
                _energy_step(f"{sid}.money.energy_cost", "Cost for the year", z.get("energy_cost"), "money"),
            )
            if st is not None
        ]
        sources.append(
            SourceChain(
                id=sid,
                kind=str(z["kind"]),
                label=str(z["label"]),
                ownership=z.get("ownership"),
                capacity=_sv(z.get("kw")),
                slot=slot,
                slots_differ=differ,
                landed=landed,
                landed_total=total,
                energy=energy,
                gaps={g: GAPS.get(g, g) for g in z.get("gaps") or []},
            )
        )
    st = sm.get("settlement") or {}
    load = _sv(st.get("load_kwh"))
    site_energy = [
        x
        for x in (
            ChainStep(key="energy.consumption", kind="energy", label="Consumption for the year", value=load)
            if load is not None
            else None,
            _energy_step("energy.withdrawn", "Withdrawn from the bank", st.get("withdrawn_kwh")),
            _energy_step("energy.lapsed", "Lapsed (banked, never drawn)", st.get("lapsed_kwh")),
            _energy_step("energy.grid", "Drawn from the DISCOM with the plan", st.get("grid_kwh")),
        )
        if x is not None
    ]
    money: list[ChainStep] = []
    for key, amount in (sm.get("lines_before") or {}).items():
        money.append(
            ChainStep(
                key=f"money.before.{key}",
                kind="money",
                label=f"Today: {MONEY_LABEL.get(key, key.replace('_', ' '))}",
                value=derive(Decimal(amount), Unit.INR, [before_ref], label=MONEY_LABEL.get(key, key)),
            )
        )
    money.append(
        ChainStep(key="money.before", kind="total", label="Grid cost today, for the year", value=before_ref)
    )
    names = {str(z["id"]): str(z["label"]) for z in sm["sizes"]}
    for key, amount in (sm.get("lines_after") or {}).items():
        head, _, cid = key.partition(":")
        if cid:
            what = {"energy": "energy", "fixed": "plant (capital recovery and O&M)"}.get(head, head)
            label = f"With the plan: {names.get(cid, cid)}, {what}"
        else:
            label = f"With the plan: {MONEY_LABEL.get(key, key.replace('_', ' '))}"
        money.append(
            ChainStep(
                key=f"money.after.{key.replace(':', '.')}",
                kind="money",
                label=label,
                value=derive(Decimal(amount), Unit.INR, [after_ref], label=label),
            )
        )
    money.append(
        ChainStep(key="money.after", kind="total", label="Cost with the plan, for the year", value=after_ref)
    )
    saving = _sv(annual["saving"])
    assert saving is not None
    money.append(ChainStep(key="money.saving", kind="total", label="Saving for the year", value=saving))
    lb, la = sm.get("lines_before") or {}, sm.get("lines_after") or {}
    grid_kwh = _sv(st.get("grid_kwh"))
    if load is not None and grid_kwh is not None and "grid_energy" in lb and "grid_energy" in la:
        displaced = load.value - grid_kwh.value
        if displaced > 0:
            money.append(
                ChainStep(
                    key="money.avoided_rate",
                    kind="money",
                    label="Grid energy cost avoided, per kWh displaced",
                    value=derive(
                        ((Decimal(lb["grid_energy"]) - Decimal(la["grid_energy"])) / displaced).quantize(
                            Decimal("0.0001")
                        ),
                        Unit.INR_PER_KWH,
                        [before_ref, after_ref, load, grid_kwh],
                        label="Grid energy cost avoided per kWh",
                    ),
                )
            )
    rule_ref = st.get("rule_ref")
    return Chain(
        connection_id=connection_id,
        site=site.name if site else "",
        state=site.state if site else None,
        discom=conn.discom_id,
        scenario_id=sc.id,
        scenario=sc.name,
        run_id=run.id,
        finished_at=run.finished_at,
        settlement_rule=st.get("rule"),
        settlement_ref=SourceRef.model_validate(rule_ref) if isinstance(rule_ref, dict) else None,
        sources=sources,
        energy=site_energy,
        money=money,
        saving=saving,
        notes=[str(n) for n in sm.get("notes") or []],
    )


def steps_by_key(chain: Chain) -> dict[str, ChainStep]:
    out: dict[str, ChainStep] = {}
    for src in chain.sources:
        for st in [*src.landed, *src.energy]:
            out[st.key] = st
        if src.landed_total is not None:
            out[f"{src.id}.landed"] = ChainStep(
                key=f"{src.id}.landed",
                kind="total",
                label=f"{src.label}: landed cost at the meter",
                value=src.landed_total,
            )
    for st in [*chain.energy, *chain.money]:
        out[st.key] = st
    return out
