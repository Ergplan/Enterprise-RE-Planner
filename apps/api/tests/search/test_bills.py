"""Bill search (Haystack BM25 over stored readings) and analytics (figures with bill refs), through
the API on synthetic readings: who sees what, what matches, and the monthly series."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ergplan.intake import bills as bill_store
from ergplan.platform.app import app
from tests.intake.helpers import FakeBillx
from tests.platform.test_api_bill_reading import oa_result

client = TestClient(app)
AN = {"X-Ergplan-Actor": "analyst@joulewise.in", "X-Ergplan-Role": "analyst"}


def _as(email: str) -> dict[str, str]:
    return {"X-Ergplan-Actor": email, "X-Ergplan-Role": "client"}


@pytest.fixture
def billx(monkeypatch: pytest.MonkeyPatch) -> FakeBillx:
    fake = FakeBillx()
    monkeypatch.setattr(bill_store, "BillxClient", fake.client)
    return fake


def _upload(fake: FakeBillx, tag: str, res: dict[str, Any], who: dict[str, str]) -> list[dict[str, Any]]:
    data = fake.register(tag, res)
    r = client.post("/bills", files={"file": (f"{tag}.pdf", data, "application/pdf")}, headers=who)
    assert r.status_code == 201, r.text
    return list(r.json())


def test_search_finds_a_bill_by_its_slots_and_checks_and_never_another_clients(billx: FakeBillx) -> None:
    alice = _as("alice@plant.in")
    res = oa_result()
    res["bills"][0]["checks"] = [{"id": "G09", "status": "fail", "description": "net payable"}]
    mine = _upload(billx, "s-alice", res, alice)
    other = copy.deepcopy(oa_result())
    other["bills"][0]["fields"]["consumer"]["name"]["value"] = "ZEBRA TEXTILES"
    _upload(billx, "s-bob", other, _as("bob@other.in"))
    r = client.get("/bill-search", params={"q": "TOD-3 17 to 23"}, headers=alice)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["searched"] == 2  # alice's file holds two bills; bob's are not searched
    assert {h["bill_id"] for h in out["hits"]} <= {b["id"] for b in mine}
    assert any("TOD-3" in ln for h in out["hits"] for ln in h["lines"])
    assert out["hits"][0]["reading_url"].startswith("/plan/intake/bill/")
    fails = client.get("/bill-search", params={"q": "G09 fails"}, headers=alice).json()
    assert fails["hits"] and fails["hits"][0]["bill_id"] == mine[0]["id"]
    zebra = client.get("/bill-search", params={"q": "zebra"}, headers=alice).json()
    assert zebra["hits"] == []
    assert client.get("/bill-search", params={"q": "zebra"}, headers=AN).json()["hits"]
    assert client.get("/bill-search", params={"q": ""}, headers=alice).status_code == 422


def test_analytics_give_each_month_with_its_slots_and_open_access_share(billx: FakeBillx) -> None:
    carol = _as("carol@plant.in")
    _upload(billx, "a-carol", oa_result(), carol)
    r = client.get("/bill-analytics", headers=carol)
    assert r.status_code == 200, r.text
    [acct] = r.json()["accounts"]
    months = [m["month"] for m in acct["months"]]
    assert months == sorted(months) and len(months) == 2
    m = acct["months"][-1]
    assert m["unit"] == "kVAh" and len(m["slots"]) == 4
    assert m["open_access"]["value"] == "3600.5"
    assert m["slots"][0]["consumption"]["source_refs"][0]["kind"] == "bill"
    assert m["max_kva"]["unit"] == "kVA"
