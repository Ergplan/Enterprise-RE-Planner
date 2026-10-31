from typing import Any

import pytest
from fastapi.testclient import TestClient

from ergplan.platform.app import app
from ergplan.providers.openai_client import CallResult
from ergplan.regreader import direct
from tests.fixtures.pdfgen import make_pdf
from tests.regreader.test_tariff_oder import NETWORK, TARIFF
from tests.rulebook.helpers import GOLDEN, ROWS

pytestmark = pytest.mark.usefixtures("jurisdictions")
client = TestClient(app)
AN = {"X-Ergplan-Actor": "analyst@joulewise.in", "X-Ergplan-Role": "analyst"}


def _golden_files(tmp_path, monkeypatch) -> None:
    import yaml

    from ergplan.rulebook import golden

    d = tmp_path / "golden" / "up"
    d.mkdir(parents=True)
    (d / "npcl-tariff_schedule.yaml").write_text(
        yaml.safe_dump({"jurisdiction": "npcl", "family": "tariff_schedule", "tests": GOLDEN})
    )
    monkeypatch.setattr(golden, "golden_dir", lambda: tmp_path / "golden")


def test_jurisdictions_and_families() -> None:
    js = {j["id"]: j for j in client.get("/rulebooks/jurisdictions").json()}
    assert js["pvvnl"]["parent_id"] == "uppcl" and js["npcl"]["state_code"] == "UP"
    assert "tariff_schedule" in client.get("/rulebooks/families").json()


def test_writes_need_an_analyst() -> None:
    body = {
        "family": "tariff_schedule",
        "jurisdiction_id": "npcl",
        "effective_from": "2026-07-09",
        "rows": ROWS,
    }
    assert client.post("/rulebooks/versions", json=body).status_code == 403
    assert (
        client.post(
            "/rulebooks/versions", json=body, headers={"X-Ergplan-Actor": "c", "X-Ergplan-Role": "client"}
        ).status_code
        == 403
    )


def test_propose_edit_golden_approve_flow(tmp_path, monkeypatch) -> None:
    _golden_files(tmp_path, monkeypatch)
    body = {
        "family": "tariff_schedule",
        "jurisdiction_id": "npcl",
        "effective_from": "2026-07-09",
        "title": "NPCL",
        "rows": ROWS,
    }
    r = client.post("/rulebooks/versions", json=body, headers=AN)
    assert r.status_code == 201, r.text
    vid, rows = r.json()["version"]["id"], r.json()["rows"]
    bad = client.put(
        f"/rulebooks/versions/{vid}/rows/{rows[0]['id']}",
        json={**ROWS[0], "body": {"category": "HV-2"}},
        headers=AN,
    )
    assert bad.status_code == 422 and "errors" in bad.json()["detail"]
    g = client.post(f"/rulebooks/versions/{vid}/golden", headers=AN).json()
    assert g["version"]["golden_status"] == "green" and all(t["passed"] for t in g["golden"])
    a = client.post(f"/rulebooks/versions/{vid}/approve", headers=AN)
    assert a.status_code == 200 and a.json()["version"]["status"] == "approved"
    assert (
        client.put(f"/rulebooks/versions/{vid}/rows/{rows[0]['id']}", json=ROWS[0], headers=AN).status_code
        == 409
    )
    dup = client.post(f"/rulebooks/versions/{vid}/duplicate", headers=AN).json()
    assert dup["version"]["status"] == "draft" and dup["version"]["version"] == 2
    assert (
        client.delete(
            f"/rulebooks/versions/{dup['version']['id']}/rows/{dup['rows'][0]['id']}", headers=AN
        ).json()["version"]["rows"]
        == 1
    )
    assert client.post(f"/rulebooks/versions/{dup['version']['id']}/approve", headers=AN).status_code == 409
    assert (
        client.post(f"/rulebooks/versions/{dup['version']['id']}/reject", headers=AN).json()["version"][
            "status"
        ]
        == "rejected"
    )
    listed = client.get("/rulebooks/versions?jurisdiction=npcl").json()
    assert [v["status"] for v in listed] == ["rejected", "approved"]
    assert client.get("/rulebooks/versions/nope").status_code == 404


def test_regreader_direct_creates_a_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = make_pdf(
        [
            [
                "For supply up to 11 kV",
                "Demand Charges Rs. 300.00 / kVA / month",
                "Energy Charges Rs. 7.10 / kVAh",
            ]
        ]
    )
    d = client.post(
        "/documents",
        files={"file": ("o.pdf", pdf, "application/pdf")},
        data={"title": "Order", "jurisdiction": "UP"},
    ).json()
    row = {
        "label": "HV-2",
        "scope": {"category": ["HV-2"], "voltage_kv": {"max": 11}},
        "page": 1,
        "quote": "Demand Charges Rs. 300.00 / kVA / month",
        "body": {
            "category": "HV-2",
            "billing_basis": "kvah",
            "demand_charge": {"value": "300.00", "basis": "inr_per_kva_month"},
            "energy_charge": {"base": "7.10"},
        },
    }

    def fake(**kw: Any) -> CallResult:
        return CallResult(data={"rows": [row]}, call_id="c", model="m", prompt="p", tokens_in=1, tokens_out=1)

    monkeypatch.setattr(direct, "call_json", fake)
    r = client.post(
        "/regreader/direct",
        headers=AN,
        json={
            "document_id": d["id"],
            "family": "tariff_schedule",
            "jurisdiction_id": "npcl",
            "pages": [1],
            "effective_from": "2026-07-09",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["accepted"] == 1 and r.json()["version_id"]
    v = client.get(f"/rulebooks/versions/{r.json()['version_id']}").json()
    assert v["version"]["origin"] == "regreader_direct" and v["rows"][0]["source_ref"]["page"] == 1
    assert client.get(f"/regreader/locate/{d['id']}?topic=rate_schedule").status_code == 200
    assert (
        client.post(
            "/regreader/direct",
            headers=AN,
            json={
                "document_id": d["id"],
                "family": "tariff_schedule",
                "jurisdiction_id": "npcl",
                "pages": [],
            },
        ).status_code
        == 422
    )


def test_tariff_oder_import_from_explorer_json() -> None:
    pdf = make_pdf([["x"]])
    d = client.post(
        "/documents", files={"file": ("n.pdf", pdf, "application/pdf")}, data={"title": "NPCL"}
    ).json()
    r = client.post(
        "/regreader/tariff-oder",
        headers=AN,
        json={
            "document_id": d["id"],
            "jurisdiction_id": "npcl",
            "tariff": TARIFF,
            "network": NETWORK,
            "effective_from": "2026-07-09",
        },
    )
    assert r.status_code == 201, r.text
    fams = {x["family"]: x for x in r.json()}
    assert (
        fams["tariff_schedule"]["accepted"] == 1
        and fams["tod_slots"]["accepted"] == 1
        and fams["oa_charge"]["accepted"] == 1
    )
    assert fams["unmapped"]["rejected"][0]["reasons"] == ["value_state cross_reference"]
    assert (
        client.post(
            "/regreader/tariff-oder", headers=AN, json={"document_id": d["id"], "jurisdiction_id": "npcl"}
        ).status_code
        == 422
    )


def test_families_and_locate_errors() -> None:
    fams = client.get("/rulebooks/families").json()
    assert set(fams) >= {"tariff_schedule", "tod_slots", "oa_charge", "settlement"}
    assert "energy_charge" in fams["tariff_schedule"]["properties"]["body"]["properties"]
    assert client.get("/regreader/locate/nope?topic=banking").status_code == 404
    pdf = make_pdf(
        [["intro"], ["Banking of energy shall be allowed. Banking charges 8%"], ["Banked energy lapses"]]
    )
    d = client.post(
        "/documents", files={"file": ("b.pdf", pdf, "application/pdf")}, data={"title": "Banking"}
    ).json()
    hits = client.get(f"/regreader/locate/{d['id']}?topic=banking").json()["pages"]
    assert [h["page"] for h in hits] == [2, 3]
