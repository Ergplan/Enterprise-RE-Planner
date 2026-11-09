"""The Evaluate page's API: the DISCOMs a client can pick with their categories and what is sourced;
a site described by typing (no bills); the caller's evaluations; what the year costs today; the
lifecycle view in a run's summary; the whole year's dispatch as a file."""

from __future__ import annotations

import csv
import io
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from ergplan.intake import typed
from ergplan.platform.app import app
from tests.engine.helpers import restore_committed
from tests.platform.test_api_plan import _truncate
from tests.platform.test_api_runs import AN, CL

client = TestClient(app)


def test_the_discoms_a_client_can_pick() -> None:
    restore_committed()
    r = client.get("/intake/discoms", headers=CL)
    assert r.status_code == 200, r.text
    by = {d["id"]: d for d in r.json()}
    npcl, msedcl, hpsebl = by["npcl"], by["msedcl"], by["hpsebl"]
    assert npcl["state"] == "UP" and npcl["state_name"] == "Uttar Pradesh" and npcl["ready"]
    codes = {c["code"] for c in npcl["categories"]}
    assert "HV-2" in codes
    hv2 = next(c for c in npcl["categories"] if c["code"] == "HV-2" and c["voltage_max_kv"] == "11")
    assert hv2["rate_block"] == "Urban Schedule" and hv2["usual_voltage_kv"] == "11"
    assert msedcl["sourced"]["tariff_schedule"] and msedcl["sourced"]["settlement"]
    assert not hpsebl["ready"] and hpsebl["categories"] == [] and hpsebl["state"] == "HP"
    assert [d["state"] for d in r.json()] == sorted(d["state"] for d in r.json())


def test_a_typed_site_spreads_the_year_by_working_days() -> None:
    body = {
        "client_name": "Acme Forgings",
        "site_name": "Greater Noida",
        "state": "UP",
        "discom": "npcl",
        "category": "HV-2",
        "voltage_kv": "11",
        "contract_demand_kva": "2500",
        "industry_shape": "two_shift",
        "annual_kwh": "9600000",
        "max_demand_kva": "2300",
        "year_end": "2026-09-01",
        "roof_sqm": "8000",
    }
    r = client.post("/intake/typed", json=body, headers=CL)
    assert r.status_code == 200, r.text
    it = r.json()
    months = it["months"]
    assert len(months) == 12 and months[0]["month"] == "2025-10-01" and months[-1]["month"] == "2026-09-01"
    assert sum(Decimal(m["energy"]["value"]) for m in months) == Decimal("9600000")
    assert all(
        m["energy"]["provenance"] == "assumption" and "working days" in m["energy"]["ref"]["note"]
        for m in months
    )
    # a month with more working days gets more
    by = {m["month"]: Decimal(m["energy"]["value"]) for m in months}
    assert by["2026-03-01"] > by["2026-02-01"]
    assert months[0]["max_kva"]["value"] == "2300" and months[0]["max_kva"]["provenance"] == "assumption"
    assert months[0]["power_factor"]["provenance"] == "assumption"
    assert it["weekly_off"]["provenance"] == "assumption" and it["roof_sqm"]["value"] == "8000"
    assert it["client_name"]["provenance"] == "client_stated"
    # the months given are taken as typed
    r2 = client.post(
        "/intake/typed",
        json={
            **{k: v for k, v in body.items() if k not in ("annual_kwh", "year_end", "max_demand_kva")},
            "months": [{"month": "2026-06-01", "kwh": "800000", "max_kva": "2200"}],
            "power_factor": "0.97",
        },
        headers=CL,
    )
    assert r2.status_code == 200, r2.text
    m = r2.json()["months"][0]
    assert m["energy"]["provenance"] == "client_stated" and m["power_factor"]["value"] == "0.97"
    # refused: both or neither; an unknown DISCOM
    assert (
        client.post(
            "/intake/typed", json={**body, "months": [{"month": "2026-06-01", "kwh": "1"}]}
        ).status_code
        == 422
    )
    assert client.post("/intake/typed", json={**body, "discom": "nobody"}).status_code == 422
    assert typed.default_weekly_off("two_shift") == [6]


def test_a_typed_site_is_saved_costed_and_listed() -> None:
    _truncate()
    restore_committed()
    it = client.post(
        "/intake/typed",
        json={
            "client_name": "Acme Forgings",
            "site_name": "Greater Noida",
            "state": "UP",
            "discom": "npcl",
            "category": "HV-2",
            "voltage_kv": "11",
            "contract_demand_kva": "2500",
            "industry_shape": "two_shift",
            "annual_kwh": "9600000",
            "max_demand_kva": "2300",
        },
        headers=CL,
    ).json()
    r = client.post("/sites", json={"intake": it}, headers=CL)
    assert r.status_code == 201, r.text
    conn = r.json()["connection_id"]
    today = client.get(f"/connections/{conn}/today", headers=CL)
    assert today.status_code == 200, today.text
    t = today.json()
    assert t["source"] == "tariff" and Decimal(t["annual"]["value"]) > 0 and Decimal(t["kwh"]["value"]) > 0
    assert Decimal(t["energy"]["value"]) + Decimal(t["demand"]["value"]) == Decimal(t["annual"]["value"])
    assert Decimal("5") < Decimal(t["average_inr_per_kwh"]["value"]) < Decimal("15")
    # invariant 1: every figure cites the tariff pages and the profile's provenance
    assert any(r["kind"] == "order" and r.get("page") for r in t["annual"]["source_refs"])
    assert {r["kind"] for r in t["average_inr_per_kwh"]["source_refs"]} >= {"order", "derived"}
    mine = client.get("/connections", headers=CL)
    assert mine.status_code == 200
    [row] = [x for x in mine.json() if x["connection_id"] == conn]
    assert row["client"] == "Acme Forgings" and row["discom"] == "npcl" and row["bills"] == 0
    assert row["profile_provenance"] == "synthesised" and row["latest_run"] is None
    # another client does not see it; an analyst does
    other = {"X-Ergplan-Actor": "someone@else.in", "X-Ergplan-Role": "client"}
    assert conn not in {x["connection_id"] for x in client.get("/connections", headers=other).json()}
    assert conn in {x["connection_id"] for x in client.get("/connections", headers=AN).json()}
    # the lifecycle view and the dispatch file, on an hourly run of a small mix
    run = client.post(
        f"/connections/{conn}/mix",
        params={"wait": "true"},
        json={
            "sources": [
                {"kind": "rooftop_pv"},
                {"kind": "oa_solar_intra", "ownership": "captive", "max_mw": "3"},
            ],
            "resolution_min": 60,
            "finance": {"analysis_years": 20, "tariff_escalation_pct": "4"},
        },
        headers=CL,
    )
    assert run.status_code == 202, run.text
    out = client.get(f"/runs/{run.json()['run_id']}", headers=CL).json()
    assert out["status"] == "done"
    lc = out["summary"]["lifecycle"]
    assert lc["analysis_years"]["value"] == "20" and len(lc["years"]) == 20
    assert lc["assumptions"]["tariff_escalation_pct"]["value"] == "4"
    assert lc["assumptions"]["tariff_escalation_pct"]["source_refs"][0]["kind"] == "client_stated"
    assert lc["assumptions"]["discount_pct"]["source_refs"][0]["kind"] == "assumption"
    y1 = lc["years"][0]
    assert Decimal(y1["bau"]) == Decimal(out["summary"]["annual"]["before"]["value"])
    # year one of the plan is the settled year's lines: the grid's and the contracted energy as settled,
    # the owned plant's annualised line replaced by its capital at year 0 and its O&M
    an = client.get(f"/runs/{run.json()['run_id']}", headers=AN).json()["analyst"]
    la = {k: Decimal(v) for k, v in an["lines_after"].items()}
    assert Decimal(y1["grid"]) == sum(v for k, v in la.items() if ":" not in k).quantize(Decimal("0.01"))
    assert Decimal(y1["contracted"]) == sum(v for k, v in la.items() if k.startswith("energy:")).quantize(
        Decimal("0.01")
    )
    fixed = sum(v for k, v in la.items() if k.startswith("fixed:"))
    assert Decimal(out["summary"]["annual"]["after"]["value"]) == sum(la.values(), Decimal(0))
    assert (fixed > 0) == (Decimal(lc["capex"]["value"]) > 0)
    assert Decimal(lc["npv"]["value"]) != 0 and lc["npv"]["source_refs"]
    if Decimal(lc["capex"]["value"]) > 0:
        assert Decimal(y1["om"]) > 0 and lc["irr_pct"] is not None
    listed = next(x for x in client.get("/connections", headers=CL).json() if x["connection_id"] == conn)
    assert listed["latest_run"]["status"] == "done" and listed["latest_run"]["scenario"] == "Your mix"
    assert Decimal(listed["latest_run"]["saving"]["value"]) == Decimal(
        out["summary"]["annual"]["saving"]["value"]
    )
    # the shared plan carries the same report: the lifecycle and the months of the recommended run
    token = client.post(f"/connections/{conn}/share", headers=CL).json()["token"]
    shared = client.get(f"/p/{token}").json()
    [sc] = shared["scenarios"]
    assert sc["summary"]["lifecycle"]["years"][-1]["year"] == 20 and len(sc["summary"]["monthly"]) == 12
    assert sc["summary"]["lifecycle"]["npv"] == lc["npv"]
    f = client.get(f"/runs/{run.json()['run_id']}/dispatch.csv", headers=CL)
    assert f.status_code == 200 and f.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(f.text)))
    assert rows[0][:2] == ["time", "slot"] and len(rows) == 8761
    assert rows[1][0].startswith(out["summary"]["year_start"][:4]) if "year_start" in out["summary"] else True
    # invariant 2 for the new client endpoints: a draft with an absurd energy charge changes nothing
    discoms_before = client.get("/intake/discoms", headers=CL).json()
    _absurd_draft("npcl")
    assert client.get(f"/connections/{conn}/today", headers=CL).json() == t
    assert client.get("/intake/discoms", headers=CL).json() == discoms_before
    _truncate()


def _absurd_draft(discom: str) -> None:
    import copy

    from sqlalchemy import select

    from ergplan.db.base import session_scope
    from ergplan.db.models import Rule, RulebookVersion
    from ergplan.rulebook import service

    with session_scope(actor="analyst@joulewise.in", role="analyst") as s:
        v = s.scalars(
            select(RulebookVersion).where(
                RulebookVersion.family == "tariff_schedule",
                RulebookVersion.jurisdiction_id == discom,
                RulebookVersion.status == "approved",
            )
        ).first()
        assert v is not None
        draft = service.duplicate(s, v.id, actor="analyst@joulewise.in")
        rows = []
        for r in s.scalars(select(Rule).where(Rule.rulebook_version_id == draft.id).order_by(Rule.position)):
            body = copy.deepcopy(r.body)
            if "energy_charge" in body:
                body["energy_charge"]["base"] = "999.99"
            rows.append({"scope": r.scope, "body": body, "source_ref": r.source_ref, "label": r.label})
        service.revise(s, draft.id, rows)


@pytest.mark.parametrize("path", ["/connections/missing/today", "/runs/missing/dispatch.csv"])
def test_misses(path: str) -> None:
    assert client.get(path, headers=AN).status_code == 404
