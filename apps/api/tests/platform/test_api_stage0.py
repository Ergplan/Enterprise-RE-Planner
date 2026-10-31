from fastapi.testclient import TestClient

from ergplan.platform.app import app
from tests.fixtures.pdfgen import make_pdf

client = TestClient(app)
PDF = make_pdf([["one"], ["two"], ["three: Banking charges 8 percent"]])


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["migration"]


def _upload() -> dict:
    r = client.post(
        "/documents",
        files={"file": ("order.pdf", PDF, "application/pdf")},
        data={"title": "Banking rule", "regulator": "UPERC", "jurisdiction": "UP"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_upload_list_open_page_and_text() -> None:
    d = _upload()
    assert d["pages"] == 3 and d["url"] == f"/documents/{d['id']}"
    assert any(x["id"] == d["id"] for x in client.get("/documents?jurisdiction=UP").json())
    pdf = client.get(f"/documents/{d['id']}")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"].startswith("inline")
    img = client.get(f"/documents/{d['id']}/pages/3.png")
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")
    assert "Banking charges" in client.get(f"/documents/{d['id']}/pages/3/text").json()["text"]
    assert client.get(f"/documents/{d['id']}/meta").json()["regulator"] == "UPERC"


def test_errors() -> None:
    d = _upload()
    assert client.get("/documents/nope").status_code == 404
    assert client.get(f"/documents/{d['id']}/pages/9.png").status_code == 404
    bad = client.post(
        "/documents", files={"file": ("x.pdf", b"not a pdf", "application/pdf")}, data={"title": "x"}
    )
    assert bad.status_code == 422
