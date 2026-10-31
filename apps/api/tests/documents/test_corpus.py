import json
from pathlib import Path

from ergplan.db.base import session_scope
from ergplan.documents import corpus, service
from tests.fixtures.pdfgen import make_pdf


def test_page_hints_from_notes() -> None:
    e = corpus.load_index()[0]
    assert e.state == "UP" and e.commission == "UPERC"
    assert e.page_hints["schedule"] == [352, 400]
    assert e.provenance_url and e.provenance_url.startswith("https://www.uperc.org/")


def test_register_corpus_reports_missing_and_registers_present(tmp_path: Path) -> None:
    (tmp_path / "UP").mkdir()
    (tmp_path / "UP" / "a.pdf").write_bytes(make_pdf([["a"], ["b"]]))
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "path": "UP/a.pdf",
                        "state": "UP",
                        "commission": "UPERC",
                        "title": "A",
                        "order_date": "2026-07-02",
                        "provenance_url": "https://example.org/a.pdf",
                        "notes": ["Rate schedule: Annexure-I, PDF pages 1-2."],
                    },
                    {"path": "UP/missing.pdf", "state": "UP", "commission": "UPERC", "title": "B"},
                ]
            }
        )
    )
    r = corpus.register_corpus(tmp_path, index=index)
    assert len(r["registered"]) == 1 and r["missing"] == ["UP/missing.pdf"]
    with session_scope() as s:
        doc = service.get(s, r["registered"][0]["id"])
        assert doc.url_public == "https://example.org/a.pdf"
        assert doc.page_hints == {"schedule": [1, 2]}
    again = corpus.register_corpus(tmp_path, index=index)
    assert len(again["existing"]) == 1 and not again["registered"]
