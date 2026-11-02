"""The audit screen's data: the chain from the generator's price to the saving, read from a settled
plan; its links add up to what the plan shows, and every link carries its sources."""

from __future__ import annotations

import copy
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ergplan.db.base import session_scope
from ergplan.db.models import RunResult
from ergplan.platform.app import app
from ergplan.report import chain as chain_data
from tests.platform.test_api_plan import _truncate
from tests.platform.test_api_runs import AN, CL, make_site, msedcl_5mw

client = TestClient(app)
REGULATORY = {"charge", "loss", "capacity", "drawal", "exemption", "banking"}


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
        yield {"site": site, "conn": conn}
    finally:
        mp.undo()
        _truncate()


@pytest.fixture(autouse=True)
def clean_db() -> None:  # the module's site is shared by its tests
    return None


def _chain(conn: str, **params: str) -> dict[str, Any]:
    r = client.get(f"/connections/{conn}/chain", params=params, headers=CL)
    assert r.status_code == 200, r.text
    return dict(r.json())


def _d(v: dict[str, Any]) -> Decimal:
    return Decimal(v["value"])


def test_the_chain_adds_up_to_the_plan(plan: dict[str, str]) -> None:
    c = _chain(plan["conn"])
    shown = client.get(f"/connections/{plan['conn']}/plan", headers=CL).json()
    assert c["scenario_id"] == shown["recommended"]
    assert c["discom"] == "msedcl" and c["state"] == "MH"
    oa = [s for s in c["sources"] if s["landed"]]
    assert oa, "an open-access source with its landed cost"
    for s in oa:
        assert s["landed"][0]["kind"] == "price" and s["landed"][0]["editable"] == "price_inr_per_kwh"
        total = sum((_d(st["value"]) for st in s["landed"]), Decimal(0))
        assert total == _d(s["landed_total"]) == _d(s["landed"][-1]["running"])
        for st in s["landed"]:
            assert st["value"]["source_refs"], st["key"]
            if st["kind"] in REGULATORY:
                assert st["rule_id"] and st["pointer"] and st["rate"], st["key"]
        assert len({st["key"] for st in s["landed"]}) == len(s["landed"])  # keys are unique
    money = {m["key"]: _d(m["value"]) for m in c["money"]}
    before = sum((v for k, v in money.items() if k.startswith("money.before.")), Decimal(0))
    after = sum((v for k, v in money.items() if k.startswith("money.after.")), Decimal(0))
    assert abs(before - money["money.before"]) <= Decimal("0.05")
    assert abs(after - money["money.after"]) <= Decimal("0.05")
    assert money["money.saving"] == money["money.before"] - money["money.after"]
    energy = {e["key"]: _d(e["value"]) for e in c["energy"]}
    assert energy["energy.consumption"] >= energy["energy.grid"]
    assert c["settlement_rule"] and c["settlement_ref"]["kind"] in ("regulation", "order")


def test_a_named_scenario_and_the_misses(plan: dict[str, str]) -> None:
    shown = client.get(f"/connections/{plan['conn']}/plan", headers=CL).json()
    other = next(s for s in shown["scenarios"] if s["scenario_id"] != shown["recommended"])
    assert _chain(plan["conn"], scenario_id=other["scenario_id"])["scenario_id"] == other["scenario_id"]
    assert client.get("/connections/missing/chain", headers=CL).status_code == 404
    r = client.get(f"/connections/{plan['conn']}/chain", params={"scenario_id": "nope"}, headers=CL)
    assert r.status_code == 404


def test_a_run_from_before_the_chain_shows_its_waterfall(plan: dict[str, str]) -> None:
    c = _chain(plan["conn"])
    with session_scope(actor="t") as s:
        rr = s.get(RunResult, c["run_id"])
        assert rr is not None
        kept = copy.deepcopy(rr.summary)
        old = copy.deepcopy(rr.summary)
        for z in old["sizes"]:
            z.pop("chain", None)
        rr.summary = old
    try:
        with session_scope(actor="t") as s:
            built = chain_data.build(s, plan["conn"], c["scenario_id"])
        for src, new in zip(built.sources, c["sources"], strict=True):
            # the waterfall's lines may group what the chain splits; the landed cost is the same
            if new["landed_total"] is not None:
                assert src.landed_total is not None
                assert src.landed_total.value == Decimal(new["landed_total"]["value"])
            assert all(st.rate is None for st in src.landed)
    finally:
        with session_scope(actor="t") as s:
            rr = s.get(RunResult, c["run_id"])
            assert rr is not None
            rr.summary = kept


# ---------------------------------------------------------------- workings, lines and closing

WORKING = """Item,Value,Unit
PPA tariff (Rs/kWh),3.20,Rs/kWh
Cross subsidy surcharge,2.50,Rs/kWh
Electricity duty on open access,0.10,Rs/kWh
"""
PRICE = "oa_hybrid_intra.price.price"
CSS = "oa_hybrid_intra.drawal.cross_subsidy_surcharge"


def _base(conn: str) -> str:
    shown = client.get(f"/connections/{conn}/plan", headers=CL).json()
    return str(shown["recommended"])


def _upload(conn: str, name: str = "our-working.csv", data: str = WORKING) -> dict[str, Any]:
    r = client.post(
        f"/connections/{conn}/workings",
        files={"file": (name, data.encode(), "text/csv")},
        headers=CL,
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


def _line(working: str, scenario: str, **kw: Any) -> Any:
    return client.post(f"/workings/{working}/lines", params={"scenario_id": scenario}, json=kw, headers=CL)


def test_a_working_is_grounded_compared_and_closed_by_kind(plan: dict[str, str]) -> None:
    conn, base = plan["conn"], _base(plan["conn"])
    w = _upload(conn)
    assert w["pages"] == [{"page": 1, "name": "our-working.csv"}]
    price = _line(
        w["id"],
        base,
        chain_key=PRICE,
        label="PPA tariff",
        value="3.20",
        unit="INR/kWh",
        page=1,
        quote="PPA tariff (Rs/kWh) | 3.20",
    )
    assert price.status_code == 201, price.text
    p = price.json()
    assert (p["status"], Decimal(p["theirs"]), Decimal(p["ours"]), p["kind"]) == (
        "differs",
        Decimal("3.2"),
        Decimal("3.5"),
        "yours",
    )
    assert Decimal(p["difference"]) == Decimal("-0.3")
    css = _line(
        w["id"],
        base,
        chain_key=CSS,
        compare="rate",
        label="CSS",
        value="2.50",
        unit="INR/kWh",
        page=1,
        quote="Cross subsidy surcharge | 2.50",
    ).json()
    assert (css["status"], css["kind"]) == ("differs", "regulatory")
    duty = _line(
        w["id"],
        base,
        chain_key=None,
        label="Electricity duty on OA",
        value="0.10",
        unit="INR/kWh",
        page=1,
        quote="Electricity duty on open access | 0.10",
    ).json()
    assert duty["status"] == "unmatched" and duty["ours"] is None
    # what the API refuses: words not on the page, a figure not in the words, units that do not compare
    for kw, words in (
        ({"quote": "PPA tariff | 2.90", "value": "2.90"}, "not on page 1"),
        ({"quote": "PPA tariff (Rs/kWh) | 3.20", "value": "9.99"}, "not among the figures"),
        ({"quote": "PPA tariff (Rs/kWh) | 3.20", "value": "3.20", "unit": "kWh"}, "cannot be compared"),
        ({"quote": "PPA tariff (Rs/kWh) | 3.20", "value": "3.20", "page": 4}, "no page 4"),
    ):
        args = {"chain_key": PRICE, "label": "x", "value": "3.20", "unit": "INR/kWh", "page": 1, **kw}
        r = _line(w["id"], base, **args)
        assert r.status_code == 422 and words in r.json()["detail"], (kw, r.text)
    # each difference is closed by its kind
    assert (
        client.post(f"/working-lines/{css['id']}/use", params={"scenario_id": base}, headers=CL).status_code
        == 422
    )
    r = client.post(
        f"/working-lines/{p['id']}/propose", json={"reason": "ours", "scenario_id": base}, headers=CL
    )
    assert r.status_code == 422
    use = client.post(f"/working-lines/{p['id']}/use", params={"scenario_id": base}, headers=CL)
    assert use.status_code == 202, use.text
    rerun = use.json()
    assert rerun["scenario"].endswith("(your figures)") and rerun["status"] == "queued"
    from ergplan.platform import runs as svc

    assert svc.execute(rerun["run_id"]) == "done"
    mine = _chain(conn, scenario_id=rerun["scenario_id"])
    first = next(s for s in mine["sources"] if s["id"] == "oa_hybrid_intra")["landed"][0]
    assert Decimal(first["value"]["value"]) == Decimal("3.2")
    ref = first["value"]["source_refs"][0]
    assert ref["kind"] == "client_stated" and "our-working.csv" in ref["note"]
    audit = client.get(f"/connections/{conn}/audit", params={"scenario_id": rerun["scenario_id"]}, headers=CL)
    lines = {x["id"]: x for x in audit.json()["workings"][0]["lines"]}
    assert lines[p["id"]]["status"] == "stated"
    refreshed = client.post(
        f"/connections/{conn}/audit/refresh", params={"scenario_id": rerun["scenario_id"]}, headers=CL
    )
    assert refreshed.json()["compared"] >= 1
    after = client.get(f"/connections/{conn}/audit", params={"scenario_id": rerun["scenario_id"]}, headers=CL)
    now = {x["id"]: x for x in after.json()["workings"][0]["lines"]}[p["id"]]
    assert now["status"] == "matches" and Decimal(now["ours"]) == Decimal("3.2")
    assert client.get(f"/workings/{w['id']}/file", headers=CL).content == WORKING.encode()


def test_a_regulatory_difference_goes_to_an_analyst_and_never_to_the_client_plan(
    plan: dict[str, str],
) -> None:
    from ergplan.db.models import Rule, RulebookVersion
    from ergplan.documents import service as documents
    from tests.fixtures.pdfgen import make_pdf

    conn, base = plan["conn"], _base(plan["conn"])
    before = _chain(conn, scenario_id=base)
    w = _upload(conn, "css.csv")
    css = _line(
        w["id"],
        base,
        chain_key=CSS,
        compare="rate",
        label="CSS",
        value="2.50",
        unit="INR/kWh",
        page=1,
        quote="Cross subsidy surcharge | 2.50",
    ).json()
    r = client.post(
        f"/working-lines/{css['id']}/propose",
        json={"reason": "the 2025 order", "scenario_id": base},
        headers=CL,
    )
    assert r.status_code == 201, r.text
    prop = r.json()
    assert (Decimal(prop["current"]), Decimal(prop["proposed"]), prop["unit"]) == (
        Decimal("2.11"),
        Decimal("2.5"),
        "INR/kWh",
    )
    assert "css.csv" in prop["reason"] and prop["status"] == "open"
    assert client.get("/rule-proposals", headers=CL).status_code == 403
    assert [x["id"] for x in client.get("/rule-proposals", headers=AN).json()] == [prop["id"]]
    assert client.post(f"/rule-proposals/{prop['id']}/accept", json={}, headers=CL).status_code in (403, 422)
    with session_scope(actor="t") as s:
        doc, _ = documents.register(
            s,
            make_pdf([["Cross Subsidy Surcharge for HT Industry: Rs. 2.50 / kWh"]]),
            documents.DocumentMeta(title="CSS order", regulator="MERC", jurisdiction="MH"),
            "t",
        )
        doc_id = doc.id
    bad = client.post(
        f"/rule-proposals/{prop['id']}/accept",
        json={"document_id": doc_id, "page": 1, "quote": "Cross Subsidy Surcharge is Rs. 2.50"},
        headers=AN,
    )
    assert bad.status_code == 422 and "not on page 1" in bad.json()["detail"]
    ok = client.post(
        f"/rule-proposals/{prop['id']}/accept",
        json={
            "document_id": doc_id,
            "page": 1,
            "quote": "Cross Subsidy Surcharge for HT Industry: Rs. 2.50 / kWh",
        },
        headers=AN,
    )
    assert ok.status_code == 200, ok.text
    done = ok.json()
    assert done["status"] == "accepted" and done["decided_by"] == "analyst@joulewise.in"
    with session_scope(actor="t") as s:
        v = s.get(RulebookVersion, done["draft_version_id"])
        assert v is not None and v.status == "draft"
        row = next(
            r
            for r in s.query(Rule).filter(Rule.rulebook_version_id == v.id)
            if r.field_refs and prop["pointer"] in r.field_refs
        )
        assert row.field_refs[prop["pointer"]]["document_id"] == doc_id
        assert row.review["proposal"] == prop["id"]
    # invariant 2: the draft does not reach the client's plan
    again = _chain(conn, scenario_id=base)
    assert [st["value"]["value"] for s in again["sources"] for st in s["landed"]] == [
        st["value"]["value"] for s in before["sources"] for st in s["landed"]
    ]
    # a second proposal, rejected
    css2 = _line(
        w["id"],
        base,
        chain_key=CSS,
        compare="rate",
        label="CSS",
        value="2.50",
        unit="INR/kWh",
        page=1,
        quote="Cross subsidy surcharge | 2.50",
    ).json()
    p2 = client.post(
        f"/working-lines/{css2['id']}/propose", json={"reason": "again", "scenario_id": base}, headers=CL
    ).json()
    rej = client.post(
        f"/rule-proposals/{p2['id']}/reject", json={"note": "the order of 2024 governs"}, headers=AN
    )
    assert rej.status_code == 200 and rej.json()["status"] == "rejected"
    lines = {
        x["id"]: x
        for x in client.get(f"/connections/{conn}/audit", headers=CL).json()["workings"][-1]["lines"]
    }
    assert lines[css["id"]]["status"] == "rule_changed" and lines[css2["id"]]["status"] == "rejected"
    ours = client.post(f"/working-lines/{css2['id']}/accept-ours", json={"note": "fine"}, headers=CL)
    assert ours.json()["status"] == "ours_accepted"


def test_the_audit_assistant_transcribes_and_the_api_compares(
    plan: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from ergplan.providers import openai_client

    conn, base = plan["conn"], _base(plan["conn"])
    w = _upload(conn, "chat.csv")
    seen: list[list[dict[str, Any]]] = []
    turns = [
        openai_client.ChatTurn(
            text=None,
            tool_calls=[
                {
                    "id": "c1",
                    "name": "record_lines",
                    "arguments": {
                        "working_id": w["id"],
                        "lines": [
                            {
                                "chain_key": PRICE,
                                "compare": "value",
                                "label": "PPA tariff",
                                "value": "3.20",
                                "scale": "units",
                                "unit": "INR/kWh",
                                "page": 1,
                                "quote": "PPA tariff (Rs/kWh) | 3.20",
                            },
                            {
                                "chain_key": PRICE,
                                "compare": "value",
                                "label": "made up",
                                "value": "2.00",
                                "scale": "units",
                                "unit": "INR/kWh",
                                "page": 1,
                                "quote": "PPA tariff 2.00",
                            },
                        ],
                    },
                }
            ],
            tokens_in=1,
            tokens_out=1,
        ),
        openai_client.ChatTurn(
            text="Your PPA price differs from the plan's.", tool_calls=[], tokens_in=1, tokens_out=1
        ),
    ]

    def fake(**kw: Any) -> openai_client.ChatTurn:
        seen.append(kw["messages"])
        assert kw["prompt_name"] == "audit" and kw["prompt_version"] == 1
        return turns.pop(0)

    monkeypatch.setattr(openai_client, "chat_with_tools", fake)
    r = client.post(
        f"/connections/{conn}/audit/chat",
        json={"message": "check my working", "scenario_id": base},
        headers=CL,
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["reply"] == "Your PPA price differs from the plan's."
    [res] = out["tool_results"]
    assert res["ok"] and len(res["line_ids"]) == 1 and "refused" in res["say"]
    assert "THE CHAIN" in seen[0][0]["content"] and "chat.csv" in seen[0][0]["content"]
    assert PRICE in seen[0][0]["content"]
    roles = [m["role"] for m in client.get(f"/connections/{conn}/audit", headers=CL).json()["messages"]]
    assert roles[-3:] == ["user", "action", "assistant"]
    bad = client.post(
        f"/connections/{conn}/workings", files={"file": ("x.exe", b"MZ", "application/x")}, headers=CL
    )
    assert bad.status_code == 422


def test_the_arrangement_is_the_clients_to_state(plan: dict[str, str]) -> None:
    conn, base = plan["conn"], _base(plan["conn"])
    r = client.post(
        f"/connections/{conn}/ownership",
        json={"source_id": "oa_hybrid_intra", "ownership": "captive", "scenario_id": base},
        headers=CL,
    )
    assert r.status_code == 202, r.text
    with session_scope(actor="t") as s:
        from ergplan.db.models import Scenario

        sc = s.get(Scenario, r.json()["scenario_id"])
        assert sc is not None and sc.name.endswith("(your figures)")
        assert {c["ownership"] for c in sc.spec["candidates"] if c["kind"] == "oa_hybrid_intra"} == {
            "captive"
        }
    bad = client.post(
        f"/connections/{conn}/ownership",
        json={"source_id": "nope", "ownership": "captive", "scenario_id": base},
        headers=CL,
    )
    assert bad.status_code == 422 and "no source nope" in bad.json()["detail"]


def test_an_accepted_value_is_a_decimal_string_never_a_float() -> None:
    from ergplan.report.audit import AuditError, _set_pointer

    body: dict[str, Any] = {"charge": {"value": "2.11"}, "n": 3, "f": 0.5, "rows": [{"v": "1"}]}
    assert _set_pointer(body, "/charge/value", Decimal("2.500000")) == "2.11"
    assert body["charge"]["value"] == "2.5"
    _set_pointer(body, "/n", Decimal("4"))
    _set_pointer(body, "/rows/0/v", Decimal("1.25"))
    assert body["n"] == 4 and body["rows"][0]["v"] == "1.25"
    with pytest.raises(AuditError):
        _set_pointer(body, "/f", Decimal("0.75"))


def test_the_assistant_reads_at_most_six_decimals() -> None:
    from ergplan.report.audit_chat import _n

    assert _n(Decimal("0.1425219376161950010328444532")) == "0.142522"
    assert _n(Decimal("3.10")) == "3.1" and _n(Decimal("100")) == "100" and _n(None) == "—"
