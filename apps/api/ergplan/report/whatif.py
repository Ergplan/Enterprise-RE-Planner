"""What-if on a settled plan (Stage 7): change a price, a capacity, the contract demand, switch a
source off, or take the rules in force on another date; the sizes of the plan's run are held (with
the change), the year is dispatched and settled hourly (a fast preview) and the judge settles it
again. The answer is one sentence built from the returned numbers — no model composes it."""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..core.settings import get_settings
from ..db.models import Run, RunResult, Scenario
from ..engine import landed_cost
from ..optimizer import model as om
from ..optimizer.highs_solve import solve
from ..optimizer.resettle import resettle
from ..optimizer.scenarios import ScenarioSpec
from ..platform import runs as svc
from ..rulebook.repository import Reader


class WhatIf(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prices: dict[str, Decimal] = Field(default_factory=dict)  # source kind → INR/kWh
    capacities_mw: dict[str, Decimal] = Field(default_factory=dict)  # source kind → MW
    contract_demand_kva: Decimal | None = Field(default=None, gt=0)
    off: list[str] = Field(default_factory=list)  # source kinds switched off
    as_of: date | None = None  # the rules in force on this date

    def describe(self) -> str:
        parts = [f"{_label(k)} at ₹{v}/kWh" for k, v in self.prices.items()]
        parts += [f"{_label(k)} at {v} MW" for k, v in self.capacities_mw.items()]
        if self.contract_demand_kva:
            parts.append(f"contract demand {self.contract_demand_kva} kVA")
        parts += [f"no {_label(k)}" for k in self.off]
        if self.as_of:
            parts.append(f"the rules in force on {self.as_of:%d %b %Y}")
        return ", ".join(parts) or "no change"


def _label(kind: str) -> str:
    spec = landed_cost.SOURCE_BY_ID.get(kind)
    return spec.label[0].lower() + spec.label[1:] if spec else kind.replace("_", " ")


class WhatIfFailed(RuntimeError):
    pass


def _crore(v: Decimal) -> str:
    return f"₹{(v / Decimal(10_000_000)).quantize(Decimal('0.01'))} crore"


def evaluate(s: Session, run: Run, w: WhatIf) -> dict[str, Any]:
    rr = s.get(RunResult, run.id)
    sc = s.get(Scenario, run.scenario_id)
    if rr is None or sc is None or run.status != "done":
        raise WhatIfFailed("the plan has no settled run to change")
    spec = ScenarioSpec.model_validate(run.spec)
    cands = []
    for c in spec.candidates:
        if c.kind in w.off:
            continue
        upd: dict[str, Any] = {}
        if c.kind in w.prices:
            upd["price_inr_per_kwh"] = w.prices[c.kind]
        cands.append(c.model_copy(update=upd))
    if not cands:
        raise WhatIfFailed("every source is switched off")
    spec = spec.model_copy(update={"candidates": cands, "resolution_min": 60, "as_of": w.as_of or spec.as_of})
    a = svc.assemble(s, sc, spec, Reader())
    sizes = {z["kind"]: z for z in rr.summary["sizes"]}
    cap: dict[str, float] = {}
    bkw: dict[str, float] = {}
    bkwh: dict[str, float] = {}
    for m in a.cands:
        z = sizes.get(m.spec.kind)
        kw = float(Decimal(z["kw"]["value"])) if z else 0.0
        if m.spec.kind in w.capacities_mw:
            new_kw = float(w.capacities_mw[m.spec.kind] * 1000)
            if m.spec.kind == "btm_bess" and kw > 0 and z and z.get("kwh"):
                bkwh[m.cid] = float(Decimal(z["kwh"]["value"])) * new_kw / kw
            elif m.spec.kind == "btm_bess":
                bkwh[m.cid] = new_kw * 2
            kw = new_kw
        if m.spec.kind == "btm_bess":
            bkw[m.cid] = kw
            bkwh.setdefault(m.cid, float(Decimal(z["kwh"]["value"])) if z and z.get("kwh") else 0.0)
        else:
            cap[m.cid] = kw
    cd = float(w.contract_demand_kva) if w.contract_demand_kva else a.problem.grid.cd_kva
    p = a.problem
    # the capacities are the plan's (or the changed ones): widen bounds so the fixed values are feasible
    cands_fixed = [
        dataclasses.replace(c, min_kw=0.0, max_kw=max(c.max_kw, cap.get(c.id, 0.0))) for c in p.candidates
    ]
    bats = [
        dataclasses.replace(
            b, min_kw=0.0, max_kw=max(b.max_kw, bkw.get(b.id, 0.0)), min_hours=0.0, max_hours=1e6
        )
        for b in p.batteries
    ]
    p = dataclasses.replace(
        p, candidates=cands_fixed, batteries=bats, fixed=om.Fixed(cap, bkw, bkwh, cd), limits=[]
    )
    st = get_settings()
    sol = solve(p, st.ergplan_optimizer_time_limit_s, st.ergplan_optimizer_mip_gap)
    rs = resettle(p, sol, st.ergplan_resettle_tolerance_kwh)
    if not rs.agrees:
        raise WhatIfFailed("the changed plan could not be settled within tolerance; it is not shown")
    summary = svc.summarise(a, sol, rs)
    base_saving = Decimal(rr.summary["annual"]["saving"]["value"])
    saving = Decimal(summary["annual"]["saving"]["value"])
    sentence = (
        f"With {w.describe()}, the plan saves {_crore(saving)} a year, "
        f"against {_crore(base_saving)} in the plan as settled (this check is hourly)."
        if saving >= 0
        else f"With {w.describe()}, the plan costs {_crore(-saving)} a year more than the grid alone."
    )
    return {
        "change": w.model_dump(mode="json"),
        "described": w.describe(),
        "annual": summary["annual"],
        "sizes": summary["sizes"],
        "settlement": summary["settlement"],
        "sentence": sentence,
        "resolution_min": 60,
        "base_saving": rr.summary["annual"]["saving"],
    }
