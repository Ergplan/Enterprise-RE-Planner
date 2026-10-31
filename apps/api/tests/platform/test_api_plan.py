"""Journey step 6 and the live plan: a client builds the standard plan with no analyst, shares it,
a logged-out visitor reads /p/{token}; the jouleWise view is refused to clients; what-if, PDF,
explanations (model mocked), voice session and tools, text chat with the same tools (model mocked)."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ergplan.db.base import session_scope
from ergplan.db.models import Explanation
from ergplan.platform.app import app
from ergplan.providers import openai_client
from ergplan.report import pdf as pdf_export
from tests.platform.test_api_runs import AN, CL, make_site, msedcl_5mw

client = TestClient(app)


def _truncate() -> None:
    from sqlalchemy import text

    from ergplan.db.base import get_engine
    from tests.conftest import APP_TABLES

    with get_engine().begin() as c:
        c.execute(text("truncate " + ", ".join(APP_TABLES) + " cascade"))


@pytest.fixture(scope="module")
def plan() -> Iterator[dict[str, str]]:
    _truncate()
    mp = pytest.MonkeyPatch()
    try:
        site, conn = make_site(mp, msedcl_5mw(), {})
        r = client.post(
            f"/connections/{conn}/plan",
            params={"wait": "true", "resolution_min": 60, "as_of": "2026-06-01"},
            headers=CL,
        )
        assert r.status_code == 202, r.text
        assert r.json()["created"] == 3 and len(r.json()["queued"]) == 3
        again = client.post(f"/connections/{conn}/plan", params={"resolution_min": 60}, headers=CL).json()
        assert again == {"created": 0, "queued": []}  # nothing duplicated
        tok = client.post(f"/connections/{conn}/share", headers=CL).json()
        yield {"site": site, "conn": conn, "token": tok["token"], "path": tok["path"]}
    finally:
        mp.undo()
        _truncate()


@pytest.fixture(autouse=True)
def clean_db() -> None:  # the module's site is shared by its tests
    return None


def test_logged_out_visitor_reads_the_plan(plan: dict[str, str]) -> None:
    d = client.get(plan["path"]).json()  # no headers at all
    assert d["token"] == plan["token"] and len(d["scenarios"]) == 3 and d["pending_runs"] == 0
    assert d["recommended"] in {s["scenario_id"] for s in d["scenarios"]}
    assert all(s.get("analyst") is None for s in d["scenarios"]) and d["analyst_view"] is False
    assert d["documents"] and all(
        doc["pages"] and doc["url"].startswith("/documents/") for doc in d["documents"]
    )
    assert any(e["tool"] == "set_price" for e in d["editable"])
    assert client.get("/p/not-a-token").status_code == 404
    own = client.get(f"/connections/{plan['conn']}/plan", headers=CL).json()  # step 6, before sharing
    assert own["token"] is None and own["recommended"] == d["recommended"]
    assert client.get("/connections/missing/plan").status_code == 404
    assert client.post("/connections/missing/plan").status_code == 404
    assert client.post("/connections/missing/share").status_code == 404
    assert client.post(f"/connections/{plan['conn']}/share", headers=CL).json()["token"] == plan["token"]


def test_jouleWise_view_is_for_analysts_only(plan: dict[str, str]) -> None:
    assert client.get(plan["path"], params={"view": "analyst"}).status_code == 403
    assert client.get(plan["path"], params={"view": "analyst"}, headers=CL).status_code == 403
    d = client.get(plan["path"], params={"view": "analyst"}, headers=AN).json()
    a = d["scenarios"][0]["analyst"]
    assert (
        d["analyst_view"]
        and a["pins"]["rulebook_versions"]
        and a["rule_versions"]
        and a["resettle"]["agrees"]
    )


def test_what_if_reads_back_one_sentence(plan: dict[str, str]) -> None:
    r = client.post(f"/p/{plan['token']}/whatif", json={"contract_demand_kva": "4500"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["sentence"].startswith("With contract demand 4500 kVA, the plan") and d["resolution_min"] == 60
    assert d["annual"]["saving"]["source_refs"]
    bad = client.post(
        f"/p/{plan['token']}/whatif",
        json={"off": ["oa_hybrid_intra", "btm_bess", "oa_solar_intra", "rooftop_pv"]},
    )
    assert bad.status_code == 422


def test_pdf_endpoint(plan: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_export, "export", lambda token: b"%PDF-1.7 " + token.encode() + b" " * 2000)
    r = client.get(f"/p/{plan['token']}/pdf")
    assert (
        r.status_code == 200
        and r.headers["content-type"] == "application/pdf"
        and r.content.startswith(b"%PDF")
    )

    def broken(token: str) -> bytes:
        raise pdf_export.PdfUnavailable("no Chromium")

    monkeypatch.setattr(pdf_export, "export", broken)
    assert client.get(f"/p/{plan['token']}/pdf").status_code == 503
    assert pdf_export.page_url("abc").endswith("/p/abc?print=1")


def test_explanation_is_drafted_once_and_cached(
    plan: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake(**kw: Any) -> openai_client.CallResult:
        calls.append(kw["user"])
        assert kw["prompt_name"] == "explain" and kw["prompt_version"] == 1
        return openai_client.CallResult(
            {"text": "The open-access price is the largest line."}, "c1", "m", "explain_v1", 1, 1
        )

    monkeypatch.setattr(openai_client, "call_json", fake)
    d = client.get(plan["path"]).json()
    sc = next(s for s in d["scenarios"] if s["summary"]["sizes"][0]["waterfall"])
    item = f"waterfall:{sc['summary']['sizes'][0]['id']}"
    r1 = client.post(
        f"/p/{plan['token']}/explain", json={"scenario_id": sc["scenario_id"], "item": item}
    ).json()
    r2 = client.post(
        f"/p/{plan['token']}/explain", json={"scenario_id": sc["scenario_id"], "item": item}
    ).json()
    assert (
        r1["kind"] == "explanation" and r1["values"] and not r1["cached"] and r2["cached"] and len(calls) == 1
    )
    assert '"value"' in calls[0] and "source" in calls[0]  # the model saw only sourced values
    with session_scope() as s:
        assert s.query(Explanation).count() == 1


def test_voice_session_and_plan_tool(plan: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(**kw: Any) -> openai_client.RealtimeSecret:
        assert kw["prompt_name"] == "voice" and any(t["name"] == "set_price" for t in kw["tools"])
        return openai_client.RealtimeSecret("ek_x", 1, "gpt-realtime", "c")

    monkeypatch.setattr(openai_client, "realtime_secret", fake)
    r = client.post("/voice/session", json={"mode": "plan", "token": plan["token"]}).json()
    assert r["client_secret"] == "ek_x" and r["tools"]
    assert client.post("/voice/session", json={"mode": "plan"}).status_code == 422
    assert {t["name"] for t in client.get("/voice/tools", params={"mode": "plan"}).json()} >= {"set_price"}
    t = client.post(
        "/voice/tool",
        json={
            "mode": "plan",
            "name": "set_contract_demand",
            "arguments": {"value": 4500},
            "token": plan["token"],
        },
    ).json()
    assert t["ok"] and t["say"].startswith("With contract demand 4500 kVA") and t["state"]["whatif"]
    wrong = client.post(
        "/voice/tool",
        json={"mode": "intake", "name": "set_price", "arguments": {"source": "x", "inr_per_kwh": 3}},
    ).json()
    assert not wrong["ok"]


def test_text_chat_shares_the_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    turns = iter(
        [
            openai_client.ChatTurn(
                None, [{"id": "1", "name": "set_contract_demand_kva", "arguments": {"value": 5000}}], 1, 1
            ),
            openai_client.ChatTurn("Contract demand set to 5000 kVA.", [], 1, 1),
        ]
    )
    seen: list[list[dict[str, Any]]] = []

    def fake(**kw: Any) -> openai_client.ChatTurn:
        seen.append(kw["messages"])
        return next(turns)

    monkeypatch.setattr(openai_client, "chat_with_tools", fake)
    r = client.post(
        "/chat", json={"mode": "intake", "messages": [{"role": "user", "content": "our CD is 5 MVA"}]}
    ).json()
    assert (
        r["reply"] == "Contract demand set to 5000 kVA."
        and r["state"]["contract_demand_kva"]["value"] == "5000"
    )
    assert seen[1][-1] == {"role": "tool", "tool_call_id": "1", "content": "Contract demand kva set to 5000."}
    assert Decimal(r["state"]["contract_demand_kva"]["value"]) == 5000
