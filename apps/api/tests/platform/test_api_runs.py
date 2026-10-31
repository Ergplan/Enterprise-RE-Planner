"""Scenarios and runs: create, run (hourly here; the 15-minute sites are in tests/optimizer/test_sites.py),
read as analyst and client, dispatch, replay identity (invariant 5), failed re-settlement hidden from
clients (invariant 6), drafts invisible to runs (invariant 2), audit of every write to runs."""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from ergplan.core.settings import get_settings
from ergplan.db.base import session_scope
from ergplan.db.models import AuditLog, Connection, Rule, RulebookVersion
from ergplan.intake import bills as bill_store
from ergplan.platform.app import app
from ergplan.rulebook import service
from tests.engine.helpers import restore_committed
from tests.intake.helpers import FakeBillx, result
from tests.platform.test_api_cost import msedcl_result

client = TestClient(app)
AN = {"X-Ergplan-Actor": "analyst@joulewise.in", "X-Ergplan-Role": "analyst"}
CL = {"X-Ergplan-Actor": "client@acme.in", "X-Ergplan-Role": "client"}


def _v(value: str, unit: str | None = None) -> dict[str, Any]:
    return {"value": value, "unit": unit, "verification": "verified", "page": 1, "proof": ["consensus"]}


def msedcl_5mw() -> dict[str, Any]:
    """The synthetic MSEDCL bill scaled to a 5 MVA plant (3.3 GWh a month, 4.9 MVA recorded)."""
    r = copy.deepcopy(msedcl_result())
    f = r["bills"][0]["fields"]
    f["energy"]["kwh"] = _v("3300000", "kWh")
    f["energy"]["kvah"] = _v("3313000", "kVAh")
    f["demand"]["max_kva"] = _v("4900", "kVA")
    f["demand"]["contract_kva"] = _v("5000", "kVA")
    return r


def make_site(
    monkeypatch: pytest.MonkeyPatch, res: dict[str, Any], overrides: dict[str, str]
) -> tuple[str, str]:
    restore_committed()
    fake = FakeBillx()
    monkeypatch.setattr(bill_store, "BillxClient", fake.client)
    [bill] = client.post(
        "/bills", files={"file": ("b.pdf", fake.register("b", res), "application/pdf")}
    ).json()
    for path in bill["outstanding"]:
        value = next(f["value"] for f in bill["fields"] if f["path"] == path)
        bill = client.post(f"/bills/{bill['id']}/confirm", json={"path": path, "value": value}).json()
    si = client.post("/intake/from-bills", json={"bill_ids": [bill["id"]], "overrides": overrides}).json()
    out = client.post("/sites", json={"intake": si})
    assert out.status_code == 201, out.text
    return str(out.json()["site_id"]), str(out.json()["connection_id"])


@pytest.fixture
def mh_site(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    return make_site(monkeypatch, msedcl_5mw(), {})


@pytest.fixture
def up_site(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    return make_site(monkeypatch, result("pvvnl_passed"), {"voltage_kv": "33"})


SPEC = {
    "candidates": [
        {"kind": "oa_hybrid_intra", "ownership": "third_party", "max_mw": "8"},
        {"kind": "btm_bess"},
    ],
    "as_of": "2026-06-01",
    "resolution_min": 60,
    "sensitivities": [{"kind": "price", "candidate": "oa_hybrid_intra", "pct": ["-10", "10"]}],
}


def _scenario(site: str, conn: str, spec: dict[str, Any] = SPEC, name: str = "Hybrid and battery") -> str:
    r = client.post(
        f"/sites/{site}/scenarios", json={"connection_id": conn, "name": name, "spec": spec}, headers=AN
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def test_scenario_validation_and_roles(mh_site: tuple[str, str]) -> None:
    site, conn = mh_site
    body = {"connection_id": conn, "name": "x", "spec": SPEC}
    assert client.post(f"/sites/{site}/scenarios", json=body, headers=CL).status_code == 403
    assert client.post("/sites/missing/scenarios", json=body, headers=AN).status_code == 404
    bad = {**body, "connection_id": "nope"}
    assert client.post(f"/sites/{site}/scenarios", json=bad, headers=AN).status_code == 422
    bad2 = {**body, "spec": {"candidates": [{"kind": "discom_grid"}]}}
    assert client.post(f"/sites/{site}/scenarios", json=bad2, headers=AN).status_code == 422
    assert client.post("/scenarios/missing/run", headers=AN).status_code == 404
    assert client.get("/runs/missing").status_code == 404


def test_run_replay_dispatch_and_audit(mh_site: tuple[str, str]) -> None:
    site, conn = mh_site
    sid = _scenario(site, conn)
    r = client.post(f"/scenarios/{sid}/run", params={"wait": "true"}, headers=AN)
    assert r.status_code == 202, r.text
    run = r.json()
    assert run["status"] == "done", run["error"]
    assert run["analyst"]["resettle"]["agrees"] is True
    pins = run["pins"]
    assert pins["rulebook_versions"] and pins["load_profile_id"] and pins["solver"].startswith("highspy")
    s = run["summary"]
    sizes = {x["kind"]: x for x in s["sizes"]}
    assert Decimal(sizes["oa_hybrid_intra"]["kw"]["value"]) > 0
    # every client-facing number carries refs; the hybrid's capacity cites an order page
    assert all(
        x["source_refs"] for x in (s["annual"]["after"], s["annual"]["saving"], s["contract_demand_kva"])
    )
    assert any(ref.get("page") for ref in s["annual"]["after"]["source_refs"])
    assert Decimal(s["annual"]["before"]["value"]) - Decimal(s["annual"]["after"]["value"]) == Decimal(
        s["annual"]["saving"]["value"]
    )
    assert s["emissions"]["factor"]["source_refs"][0]["kind"] == "assumption"
    assert [x["label"] for x in s["sensitivities"]] == [
        "oa_hybrid_intra price -10% (sizes held)",
        "oa_hybrid_intra price +10% (sizes held)",
    ]
    assert s["provenance"]["load_profile"].endswith("(synthesised)")

    # every SourcedValue anywhere in the summary carries at least one ref (invariant 1)
    def walk(x: Any) -> int:
        if isinstance(x, dict):
            if "value" in x and "unit" in x and "source_refs" in x:
                assert x["source_refs"], x
                return 1
            return sum(walk(v) for v in x.values())
        if isinstance(x, list):
            return sum(walk(v) for v in x)
        return 0

    assert walk(s) > 20
    # client view: same summary, no analyst block
    c = client.get(f"/runs/{run['id']}", headers=CL).json()
    assert c["analyst"] is None and c["summary"]["annual"] == s["annual"]
    # dispatch: the peak week by default
    d = client.get(f"/runs/{run['id']}/dispatch", headers=CL).json()
    assert d["minutes"] == 60 and len(d["times"]) == 7 * 24 and "grid" in d["series"]
    assert d["series"]["grid"][0]["source_refs"][0]["kind"] == "derived"
    # replay from the pins: identical to the paisa
    rp = client.post(f"/runs/{run['id']}/replay", params={"wait": "true"}, headers=AN).json()
    assert rp["status"] == "done" and rp["identical_to_original"] is True
    assert rp["summary"] == run["summary"]
    # scenario list shows the latest original run
    [sc] = client.get(f"/sites/{site}/scenarios", headers=CL).json()
    assert sc["latest_run"]["id"] == run["id"]
    with session_scope() as db:
        acts = db.execute(
            select(AuditLog.action, AuditLog.actor).where(
                AuditLog.table_name == "runs", AuditLog.row_id == run["id"]
            )
        ).all()
        assert ("INSERT", "analyst@joulewise.in") in acts and ("UPDATE", "worker@ergplan") in acts
        with pytest.raises(Exception, match=r"no ergplan\.actor"):
            db.execute(text("update runs set status = 'failed' where id = :i"), {"i": run["id"]})


def test_failed_resettlement_is_hidden_from_clients(
    mh_site: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    site, conn = mh_site
    sid = _scenario(site, conn)
    monkeypatch.setattr(get_settings(), "ergplan_resettle_tolerance_kwh", Decimal("-1"))
    run = client.post(f"/scenarios/{sid}/run", params={"wait": "true"}, headers=AN).json()
    assert run["status"] == "failed_resettle" and "re-settlement differs" in run["error"]
    assert client.get(f"/runs/{run['id']}", headers=CL).status_code == 404
    assert client.get(f"/runs/{run['id']}/dispatch", headers=CL).status_code == 404
    [sc] = client.get(f"/sites/{site}/scenarios", headers=CL).json()
    assert sc["latest_run"] is None
    assert client.get(f"/runs/{run['id']}", headers=AN).json()["summary"] is not None


def test_an_absurd_draft_does_not_change_a_run(mh_site: tuple[str, str]) -> None:
    """Invariant 2 for runs: a draft tariff with an absurd energy charge changes nothing."""
    site, conn = mh_site
    sid = _scenario(site, conn)
    before = client.post(f"/scenarios/{sid}/run", params={"wait": "true"}, headers=AN).json()
    with session_scope(actor="analyst@joulewise.in", role="analyst") as s:
        v = s.scalars(
            select(RulebookVersion).where(
                RulebookVersion.family == "tariff_schedule",
                RulebookVersion.jurisdiction_id == "msedcl",
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
    after = client.post(f"/scenarios/{sid}/run", params={"wait": "true"}, headers=AN).json()
    assert after["summary"] == before["summary"]


def test_up_site_runs_with_banking(up_site: tuple[str, str]) -> None:
    site, conn = up_site
    with session_scope() as s:
        c = s.get(Connection, conn)
        assert c is not None and c.discom_id == "pvvnl"
    spec = {
        "candidates": [{"kind": "oa_solar_intra", "ownership": "captive", "max_mw": "10"}],
        "resolution_min": 60,
        "as_of": "2026-09-01",
    }
    sid = _scenario(site, conn, spec, "Captive solar")
    run = client.post(f"/scenarios/{sid}/run", params={"wait": "true"}, headers=AN).json()
    assert run["status"] == "done", run["error"]
    s = run["summary"]
    assert "Renewable captive" in (s["settlement"]["rule"] or "")
    assert run["analyst"]["resettle"]["max_diff_kwh"] == "0.000"


def test_pinned_rules_never_return_a_draft(mh_site: tuple[str, str]) -> None:
    """Replay reads pinned versions only if they are approved or superseded, never a draft."""
    from datetime import date

    from ergplan.rulebook import repository

    with session_scope(actor="analyst@joulewise.in", role="analyst") as s:
        v = s.scalars(
            select(RulebookVersion).where(
                RulebookVersion.family == "tariff_schedule", RulebookVersion.jurisdiction_id == "msedcl"
            )
        ).first()
        assert v is not None
        draft = service.duplicate(s, v.id, actor="analyst@joulewise.in")
        on = date(2026, 6, 1)
        got = repository.pinned_rules(s, "tariff_schedule", ["msedcl"], on, [draft.id, v.id])
        assert got and {r.version_id for r in got} == {v.id}
        reader = repository.Reader()
        assert all(r.version_id != draft.id for r in reader(s, "tariff_schedule", ["msedcl"], on))
