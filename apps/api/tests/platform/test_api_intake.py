"""Every Stage 2 endpoint: bills (upload, read, file, confirm), shapes, from-bills, sites,
connections, profiles (summary, CSV, measured upload), prices (upload, overlap, vintages, coverage)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ergplan.intake import bills as bill_store
from ergplan.platform.app import app
from tests.intake.helpers import FakeBillx, result, with_month
from tests.intake.test_iex_loader import DAM, RTM

client = TestClient(app)
AN = {"X-Ergplan-Actor": "analyst@joulewise.in", "X-Ergplan-Role": "analyst"}
CL = {"X-Ergplan-Actor": "client@acme.in", "X-Ergplan-Role": "client"}


@pytest.fixture
def billx(monkeypatch: pytest.MonkeyPatch) -> FakeBillx:
    fake = FakeBillx()
    monkeypatch.setattr(bill_store, "BillxClient", fake.client)
    return fake


def _upload(fake: FakeBillx, tag: str, res: dict[str, Any], **form: str) -> list[dict[str, Any]]:
    data = fake.register(tag, res)
    r = client.post("/bills", files={"file": (f"{tag}.pdf", data, "application/pdf")}, data=form)
    assert r.status_code == 201, r.text
    return list(r.json())


def test_bill_upload_read_file_and_confirm(billx: FakeBillx) -> None:
    [b] = _upload(billx, "nr", result("pvvnl_needs_review"))
    assert b["status"] == "needs_review" and not b["accepted"] and b["discom"] == "pvvnl"
    assert b["outstanding"] == ["energy.kwh", "demand.max_kva", "energy.tod.0.kwh"]
    assert "disputed:energy.kwh" in b["review_reasons"]
    assert client.get(f"/bills/{b['id']}").json()["id"] == b["id"]
    f = client.get(b["file_url"])
    assert f.status_code == 200 and f.headers["content-type"] == "application/pdf"
    for path, value in [
        ("energy.kwh", "1972620"),
        ("demand.max_kva", "3250"),
        ("energy.tod.0.kwh", "725220"),
    ]:
        r = client.post(f"/bills/{b['id']}/confirm", json={"path": path, "value": value}, headers=CL)
        assert r.status_code == 200
    out = r.json()
    assert out["accepted"] and out["accepted_by"] == "bill_confirmations" and out["outstanding"] == []
    km = next(x for x in out["fields"] if x["path"] == "demand.max_kva")
    assert km["confirmed"] and km["verification"] == "confirmed"
    assert client.post(f"/bills/{b['id']}/confirm", json={"path": "x.y", "value": "1"}).status_code == 422
    assert client.post("/bills/missing/confirm", json={"path": "energy.kwh", "value": "1"}).status_code == 404
    assert client.get("/bills/missing").status_code == 404
    assert client.get("/bills/missing/file").status_code == 404


def test_bill_upload_errors(billx: FakeBillx) -> None:
    r = client.post("/bills", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert r.status_code == 415
    r = client.post(
        "/bills",
        files={"file": ("x.pdf", billx.register("q", result("pvvnl_passed")), "application/pdf")},
        data={"connection_id": "missing"},
    )
    assert r.status_code == 404
    billx.down = True
    r = client.post(
        "/bills", files={"file": ("y.pdf", billx.register("down", result("pvvnl_passed")), "application/pdf")}
    )
    assert r.status_code == 503


def test_billx_refusal_is_502(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from ergplan.intake.billx_client import BillxClient

    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"job_id": "j", "status": "failed", "error": {"message": "unreadable"}}
        )

    monkeypatch.setattr(
        bill_store,
        "BillxClient",
        lambda: BillxClient(base_url="http://b", token="t", transport=httpx.MockTransport(refuse)),
    )
    data = FakeBillx().register("fail", result("pvvnl_passed"))
    assert client.post("/bills", files={"file": ("f.pdf", data, "application/pdf")}).status_code == 502


def test_shapes() -> None:
    shapes = {s["id"]: s for s in client.get("/intake/shapes").json()}
    assert len(shapes) == 8 and shapes["two_shift"]["working_days"] == [0, 1, 2, 3, 4, 5]


def test_from_bills_site_connection_profile(billx: FakeBillx) -> None:
    ids = [
        _upload(billx, f"m{m}", with_month(result("pvvnl_passed"), f"2026-{m:02d}"))[0]["id"] for m in (8, 9)
    ]
    r = client.post(
        "/intake/from-bills", json={"bill_ids": ids, "overrides": {"voltage_kv": "33", "site_name": "Unit 2"}}
    )
    assert r.status_code == 200, r.text
    si = r.json()
    assert si["voltage_kv"] == {
        "value": "33",
        "provenance": "client_stated",
        "ref": {"kind": "client_stated"},
    } or (si["voltage_kv"]["value"] == "33" and si["voltage_kv"]["provenance"] == "client_stated")
    assert si["category"]["provenance"] == "assumption" and si["months"][1]["energy"]["provenance"] == "bill"
    assert client.post("/intake/from-bills", json={"bill_ids": ["missing"]}).status_code == 404
    [nr] = _upload(billx, "nr2", result("pvvnl_needs_review"))
    assert client.post("/intake/from-bills", json={"bill_ids": [nr["id"]]}).status_code == 422

    built = client.post("/sites", json={"intake": si}, headers=CL)
    assert built.status_code == 201, built.text
    out = built.json()
    conn = client.get(f"/connections/{out['connection_id']}").json()
    assert conn["discom_id"] == "pvvnl" and conn["voltage_kv"] == "33.000" and conn["connection_kind"] == "ht"
    assert conn["site"]["name"] == "Unit 2" and len(conn["bills"]) == 2 and len(conn["profiles"]) == 1
    prof = client.get(f"/connections/{out['connection_id']}/profile").json()
    assert prof["provenance"] == "synthesised" and len(prof["months"]) == 12 and len(prof["week_kw"]) == 672
    sep = next(m for m in prof["months"] if m["month"] == "2026-09-01")
    assert sep["energy_kwh"]["value"] == "1972620.000" and sep["energy_kwh"]["unit"] == "kWh"
    assert sep["energy_kwh"]["source_refs"][0]["kind"] == "bill"
    assert sep["max_kw"]["value"] == "3250.000"
    apr = next(m for m in prof["months"] if m["month"] == "2026-04-01")
    assert apr["extrapolated"] and apr["energy_kwh"]["source_refs"][0]["kind"] == "assumption"
    csv = client.get(f"/connections/{out['connection_id']}/profile.csv")
    assert csv.status_code == 200 and csv.text.count("\n") == 365 * 96 + 1
    assert (
        client.get(f"/connections/{out['connection_id']}/profile", params={"version": 9}).status_code == 404
    )
    back = client.get(f"/connections/{out['connection_id']}/intake").json()
    assert back["voltage_kv"]["value"] == "33" and len(back["months"]) == 2
    back["industry_shape"] = {"value": "continuous_process"}
    rebuilt = client.post("/sites", json={"intake": back, "connection_id": out["connection_id"]})
    assert rebuilt.status_code == 201 and rebuilt.json()["load_profile_version"] == 2
    assert client.get("/connections/missing/intake").status_code == 404
    assert client.get("/connections/missing").status_code == 404
    assert client.get("/connections/missing/profile").status_code == 404
    bad = dict(si, state={"value": "MH"})
    assert client.post("/sites", json={"intake": bad}).status_code == 422
    assert client.post("/sites", json={"intake": si, "connection_id": "missing"}).status_code == 404


def test_measured_upload(billx: FakeBillx) -> None:
    ids = [_upload(billx, "m9", with_month(result("pvvnl_passed"), "2026-09"))[0]["id"]]
    si = client.post("/intake/from-bills", json={"bill_ids": ids}).json()
    cid = client.post("/sites", json={"intake": si}).json()["connection_id"]
    start = datetime(2026, 4, 1)
    rows = ["timestamp,kW"] + [
        f"{start + timedelta(minutes=15 * i):%Y-%m-%d %H:%M},{1000 + i % 7}" for i in range(365 * 96)
    ]
    r = client.post(
        f"/connections/{cid}/profile/measured",
        files={"file": ("meter.csv", ("\n".join(rows)).encode(), "text/csv")},
    )
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["provenance"] == "measured" and p["version"] == 2
    assert p["months"][0]["energy_kwh"]["source_refs"][0]["kind"] == "measured"
    bad = client.post(
        f"/connections/{cid}/profile/measured", files={"file": ("m.csv", b"a,b\n1,2\n", "text/csv")}
    )
    assert bad.status_code == 422
    assert (
        client.post(
            "/connections/missing/profile/measured",
            files={"file": ("meter.csv", ("\n".join(rows)).encode(), "text/csv")},
        ).status_code
        == 404
    )


def test_prices_endpoints() -> None:
    files = {"file": ("rtm.csv", RTM.encode(), "text/csv")}
    assert client.post("/prices", files=files).status_code == 403
    assert client.post("/prices", files=files, headers=CL).status_code == 403
    r = client.post("/prices", files=files, headers=AN)
    assert r.status_code == 201, r.text
    v1 = r.json()["vintage"]
    assert v1["segment"] == "rtm" and v1["rows"] == 3 and r.json()["missing_blocks"] == 189
    changed = {"file": ("rtm2.csv", RTM.replace("799.45", "805").encode(), "text/csv")}
    clash = client.post("/prices", files=changed, headers=AN)
    assert clash.status_code == 409 and clash.json()["detail"]["vintage_ids"] == [v1["id"]]
    rep = client.post("/prices", files=changed, data={"replace": "true"}, headers=AN)
    assert rep.status_code == 201
    dam = client.post(
        "/prices", files={"file": ("x.csv", DAM.encode(), "text/csv")}, data={"segment": "dam"}, headers=AN
    )
    assert dam.status_code == 201 and dam.json()["conflicts"] == 1
    bad = client.post("/prices", files={"file": ("x.csv", b"a\n1\n", "text/csv")}, headers=AN)
    assert bad.status_code == 422
    vs = client.get("/prices/vintages").json()
    assert {v["segment"] for v in vs} == {"rtm", "dam"}
    assert next(v for v in vs if v["id"] == v1["id"])["superseded_by"] == rep.json()["vintage"]["id"]
    assert len(client.get("/prices/vintages", params={"segment": "dam"}).json()) == 1
    cov = client.get("/prices/coverage", params={"segment": "rtm"}).json()
    assert [c["blocks"] for c in cov] == [2, 1]
    assert len(client.get("/prices/coverage").json()) == 3


def test_kvah_month_carries_the_conversion_assumption() -> None:
    si = {
        "client_name": {"value": "Acme"},
        "site_name": {"value": "P"},
        "state": {"value": "MH"},
        "discom": {"value": "msedcl"},
        "category": {"value": "HT I(A)"},
        "voltage_kv": {"value": "22"},
        "contract_demand_kva": {"value": "2200"},
        "industry_shape": {"value": "two_shift"},
        "weekly_off": {"value": [6]},
        "months": [{"month": "2026-04-01", "energy": {"value": "1000000"}, "energy_unit": "kVAh"}],
    }
    cid = client.post("/sites", json={"intake": si}).json()["connection_id"]
    apr = client.get(f"/connections/{cid}/profile").json()["months"][0]
    assert apr["energy_kwh"]["value"] == "950000.000"
    notes = [r.get("note") or "" for r in apr["energy_kwh"]["source_refs"]]
    assert any("0.95 (assumed)" in n for n in notes)
