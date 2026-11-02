"""billx.reader.ingest: rendered pages, genuine text layers, photos, limits and errors."""

import hashlib
from decimal import Decimal

import pytest
from _synth import build_set, entries
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas

from billx.reader.ingest import (
    MAX_BYTES,
    MAX_PAGES,
    Document,
    PasswordRequired,
    TooLarge,
    UnsupportedType,
    load,
    sniff_media_type,
)
from billx.reader.read.words import group_lines, line_text


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    return build_set(tmp_path_factory)


def _pdf(path, pages=1, text="Hello bill 123", encrypt=None, image=None, render_mode=None):
    c = canvas.Canvas(str(path), pagesize=A4, encrypt=encrypt, invariant=1)
    for _ in range(pages):
        if image is not None:
            c.drawImage(image, 0, 0, width=A4[0], height=A4[1])
        t = c.beginText(72, 700)
        if render_mode is not None:
            t.setTextRenderMode(render_mode)
        t.textLine(text)
        c.drawText(t)
        c.showPage()
    c.save()
    return path


def _image_file(tmp_path, name, fmt, size=(40, 20), frames=1, exif_orientation=None):
    img = Image.new("RGB", size, "white")
    kw = {}
    if frames > 1:
        kw = {"save_all": True, "append_images": [Image.new("RGB", size, "black")] * (frames - 1)}
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        kw["exif"] = exif.tobytes()
    path = tmp_path / name
    img.save(path, fmt, **kw)
    return path


def test_synthetic_digital_pdfs_have_a_text_layer_and_scans_do_not(out):
    digital = entries(out, "digital_pdf")
    scans = entries(out, "scan_pdf")
    assert len(digital) == 11 and len(scans) == 4
    for e in digital:
        doc = load(out / e["file"])
        assert doc.media_type == "application/pdf" and doc.page_count == 1
        assert (
            doc.sha256 == e["sha256"] == hashlib.sha256((out / e["file"]).read_bytes()).hexdigest()
        )
        page = doc.pages[0]
        assert page.text_words and page.image.size == (page.width, page.height)
        # A4 (most layouts) or A5 (the receipt) at 200 dpi: the A-series ratio either way
        assert page.width in (1654, 1166) and abs(page.height / page.width - 1.414) < 0.01
        for w in page.text_words:
            for v in (w.x0, w.y0, w.x1, w.y1):
                assert isinstance(v, Decimal) and Decimal(0) <= v <= Decimal(1)
                assert v == v.quantize(Decimal("0.0001"))
            assert w.x0 < w.x1 and w.y0 < w.y1 and w.page == 0 and w.confidence is None
    for e in scans:
        doc = load(out / e["file"])
        assert doc.page_count == 1 and doc.pages[0].text_words is None
        assert not doc.has_text_layer()


def test_text_layer_words_follow_the_page(out):
    e = next(e for e in entries(out, "digital_pdf") if e["file"].startswith("avvnl"))
    doc = load(out / e["file"])
    lines = [line_text(line) for line in group_lines(doc.pages[0].text_words)]
    assert lines[0] == "AJMER VIDYUT VITRAN NIGAM LIMITED (AVVNL)"
    assert any(line.startswith("KNO ") for line in lines)
    kno = next(w for w in doc.pages[0].text_words if w.text == "KNO")
    assert kno.y0 < Decimal("0.15") and kno.x0 < Decimal("0.12")


def test_photos_load_as_images_without_text(out):
    for e in entries(out, "photo_jpeg")[:3]:
        doc = load(out / e["file"])
        assert doc.media_type == "image/jpeg" and doc.page_count == 1
        assert doc.pages[0].text_words is None and doc.pages[0].image.mode == "RGB"
    data = (out / entries(out, "photo_jpeg")[0]["file"]).read_bytes()
    assert load(data).media_type == "image/jpeg"  # bytes identify themselves


def test_password_protected_pdf(tmp_path):
    path = _pdf(tmp_path / "locked.pdf", encrypt=StandardEncryption("secret"))
    with pytest.raises(PasswordRequired):
        load(path)
    doc = load(path, password="secret")
    assert doc.page_count == 1 and doc.pages[0].text_words


def test_hidden_ocr_layer_is_not_a_text_layer(tmp_path):
    scan = _image_file(tmp_path, "scan.png", "PNG", size=(200, 280))
    covered = load(_pdf(tmp_path / "covered.pdf", image=str(scan)))
    assert covered.pages[0].text_words is None
    invisible = load(_pdf(tmp_path / "invisible.pdf", render_mode=3))
    assert invisible.pages[0].text_words is None
    plain = load(_pdf(tmp_path / "plain.pdf"))
    assert [w.text for w in plain.pages[0].text_words] == ["Hello", "bill", "123"]


def test_tiff_frames_and_exif_rotation(tmp_path):
    tiff = load(_image_file(tmp_path, "two.tiff", "TIFF", frames=2))
    assert tiff.media_type == "image/tiff" and [p.index for p in tiff.pages] == [0, 1]
    rotated = load(_image_file(tmp_path, "rot.jpg", "JPEG", size=(40, 20), exif_orientation=6))
    assert (rotated.pages[0].width, rotated.pages[0].height) == (20, 40)
    png = load(_image_file(tmp_path, "p.png", "PNG"))
    assert png.media_type == "image/png"
    webp = load(_image_file(tmp_path, "w.webp", "WEBP"))
    assert webp.media_type == "image/webp" and webp.page_count == 1


def test_limits(tmp_path):
    assert MAX_BYTES == 25 * 1024 * 1024 and MAX_PAGES == 30
    many = _pdf(tmp_path / "many.pdf", pages=31)
    with pytest.raises(TooLarge):
        load(many)
    assert load(many, max_pages=31).page_count == 31
    with pytest.raises(TooLarge):
        load(many.read_bytes(), "application/pdf", max_bytes=100)
    with pytest.raises(TooLarge):
        load(_image_file(tmp_path, "many.tiff", "TIFF", frames=3), max_pages=2)


def test_unsupported_types():
    with pytest.raises(UnsupportedType, match="HEIC"):
        load(b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32, "photo.heic")
    with pytest.raises(UnsupportedType):
        load(b"<html><body>not a bill</body></html>", "text/html")
    with pytest.raises(UnsupportedType):
        load(b"%PDF-1.4 garbage", "x.pdf")
    with pytest.raises(UnsupportedType):
        load(b"\x89PNG\r\n\x1a\n not really", "x.png")


def test_sniff_media_type():
    assert sniff_media_type(b"%PDF-1.7") == "application/pdf"
    assert sniff_media_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert (
        sniff_media_type(b"II*\x00") == "image/tiff"
        and sniff_media_type(b"MM\x00*") == "image/tiff"
    )
    assert sniff_media_type(b"????", "scan.TIF") == "image/tiff"
    assert sniff_media_type(b"????", "image/png") == "image/png"
    assert sniff_media_type(b"????", "x.bmp") is None and sniff_media_type(b"????") is None


def test_document_shape():
    doc = Document(sha256="0" * 64, media_type="application/pdf")
    assert doc.page_count == 0 and not doc.has_text_layer()
