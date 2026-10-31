import pytest

from ergplan.db.base import session_scope
from ergplan.documents import service
from tests.fixtures.pdfgen import make_pdf

PDF = make_pdf([["Cover page"], ["ANNEXURE-I RATE SCHEDULE"], ["HV-2 Energy Charge 7.10 per kVAh"]])


def test_register_dedupes_by_sha256() -> None:
    meta = service.DocumentMeta(title="Test order", regulator="UPERC", jurisdiction="UP")
    with session_scope(actor="test") as s:
        a, created_a = service.register(s, PDF, meta, uploaded_by="test")
        b, created_b = service.register(s, PDF, meta, uploaded_by="test")
    assert created_a and not created_b
    assert a.id == b.id and a.pages == 3
    assert service.path_for(a.file_sha256).exists()


def test_not_a_pdf_is_refused() -> None:
    with session_scope(actor="test") as s, pytest.raises(service.NotAPdf):
        service.register(s, b"hello", service.DocumentMeta(title="x"), uploaded_by="test")


def test_page_text_and_render() -> None:
    with session_scope(actor="test") as s:
        doc, _ = service.register(s, PDF, service.DocumentMeta(title="t"), uploaded_by="test")
        assert "7.10" in service.page_text(doc, 3)
        png = service.render_page_png(doc, 2)
        assert png.startswith(b"\x89PNG")
        with pytest.raises(service.PageOutOfRange):
            service.page_text(doc, 4)
