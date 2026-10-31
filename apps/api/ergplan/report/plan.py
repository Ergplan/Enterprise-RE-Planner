"""The live plan (Stage 7): one page of a site's plan — the facts, today's cost, the settled scenarios,
the recommended one, what can be edited, and the documents every number cites. The same data serves
the client view, the jouleWise view (analysts: every assumption, rule version, run pin and margin)
and the PDF."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Client as ClientRow
from ..db.models import (
    Connection,
    LoadProfile,
    RulebookVersion,
    Run,
    RunResult,
    Scenario,
    Site,
    SourceDocument,
)


class PlanNotFound(LookupError):
    pass


def _walk_refs(x: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(x, dict):
        if "source_refs" in x and isinstance(x["source_refs"], list):
            out.extend(r for r in x["source_refs"] if isinstance(r, dict))
        for v in x.values():
            _walk_refs(v, out)
    elif isinstance(x, list):
        for v in x:
            _walk_refs(v, out)


def _latest_done(s: Session, scenario_id: str) -> tuple[Run, RunResult] | None:
    run = s.scalars(
        select(Run)
        .where(Run.scenario_id == scenario_id, Run.status == "done", Run.replay_of.is_(None))
        .order_by(Run.created_at.desc())
    ).first()
    if run is None:
        return None
    rr = s.get(RunResult, run.id)
    return (run, rr) if rr is not None else None


def build(s: Session, connection_id: str, analyst: bool = False) -> dict[str, Any]:
    conn = s.get(Connection, connection_id)
    if conn is None:
        raise PlanNotFound(connection_id)
    site = s.get(Site, conn.site_id)
    assert site is not None
    client = s.get(ClientRow, site.client_id)
    lp = s.scalars(
        select(LoadProfile).where(LoadProfile.connection_id == conn.id).order_by(LoadProfile.version.desc())
    ).first()
    scenarios = []
    pending = 0
    for sc in s.scalars(
        select(Scenario).where(Scenario.connection_id == conn.id).order_by(Scenario.created_at)
    ):
        got = _latest_done(s, sc.id)
        open_runs = s.scalars(
            select(Run).where(Run.scenario_id == sc.id, Run.status.in_(("queued", "running")))
        ).first()
        pending += 1 if open_runs is not None else 0
        if got is None:
            continue
        run, rr = got
        item: dict[str, Any] = {
            "scenario_id": sc.id,
            "name": sc.name,
            "run_id": run.id,
            "resolution_min": run.resolution_min,
            "finished_at": run.finished_at,
            "summary": rr.summary,
        }
        if analyst:
            versions = (run.pins or {}).get("rulebook_versions") or []
            item["analyst"] = {
                "pins": run.pins,
                "solver": run.solver,
                "resettle": rr.resettle,
                "spec": run.spec,
                "cost_lines_before": rr.summary.get("lines_before"),
                "cost_lines_after": rr.summary.get("lines_after"),
                "rule_versions": [
                    {
                        "id": v.id,
                        "family": v.family,
                        "jurisdiction": v.jurisdiction_id,
                        "version": v.version,
                        "status": v.status,
                        "title": v.title,
                        "approved_by": v.approved_by,
                    }
                    for v in s.scalars(select(RulebookVersion).where(RulebookVersion.id.in_(versions)))
                ],
            }
        scenarios.append(item)
    best = max(scenarios, key=lambda x: Decimal(x["summary"]["annual"]["saving"]["value"]), default=None)
    refs: list[dict[str, Any]] = []
    _walk_refs([x["summary"] for x in scenarios], refs)
    doc_pages: dict[str, set[int]] = {}
    assumptions: dict[str, dict[str, Any]] = {}
    for r in refs:
        if r.get("document_id"):
            doc_pages.setdefault(r["document_id"], set())
            if r.get("page"):
                doc_pages[r["document_id"]].add(int(r["page"]))
        if r.get("kind") == "assumption" and r.get("note"):
            assumptions.setdefault(r["note"], r)
    rows = {d.id: d for d in s.scalars(select(SourceDocument).where(SourceDocument.id.in_(list(doc_pages))))}
    documents = [
        {
            "id": did,
            "title": rows[did].title if did in rows else f"Document {did[:8]} (not in this library)",
            "regulator": rows[did].regulator if did in rows else None,
            "url_public": rows[did].url_public if did in rows else None,
            "url": f"/documents/{did}",
            "pages": sorted(pages),
        }
        for did, pages in doc_pages.items()
    ]
    editable = []
    if best is not None:
        for z in best["summary"]["sizes"]:
            for slot_lines in list(z.get("waterfall", {}).values())[:1]:
                if slot_lines and slot_lines[0].get("label") == "PPA tariff":
                    editable.append(
                        {
                            "tool": "set_price",
                            "source": z["kind"],
                            "label": f"{z['label']}: PPA tariff",
                            "value": slot_lines[0],
                        }
                    )
        editable.append(
            {
                "tool": "set_contract_demand",
                "source": None,
                "label": "Contract demand",
                "value": best["summary"]["contract_demand_kva"],
            }
        )
    return {
        "connection_id": conn.id,
        "client": client.name if client else "",
        "site": site.name,
        "state": site.state,
        "discom": conn.discom_id,
        "category": conn.tariff_category,
        "voltage_kv": str(conn.voltage_kv) if conn.voltage_kv is not None else None,
        "profile": f"v{lp.version} ({lp.provenance})" if lp else None,
        "scenarios": scenarios,
        "recommended": best["scenario_id"] if best else None,
        "pending_runs": pending,
        "documents": sorted(documents, key=lambda d: d["title"]),
        "assumptions": [{"note": k, "ref": v} for k, v in assumptions.items()],
        "editable": editable,
    }
