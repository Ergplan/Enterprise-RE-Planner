"""billx.reader.read.local: the two local readers over the synthetic set; OCR agreement."""

import sys
from decimal import Decimal

import pytest
from _synth import build_set, entries, truth

from billx.core.normalize import normalise
from billx.reader import ocr
from billx.reader.ingest import load
from billx.reader.read.consensus import RawRead, ReaderOutput
from billx.reader.read.label import guaranteed_scalar_fields
from billx.reader.read.local import page_texts, read_local

AGREE_ON = [
    "consumer.account_number",
    "period.bill_month",
    "totals.net_payable",
    "energy.kwh",
    "energy.kvah",
]


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    return build_set(tmp_path_factory)


def _types(kind):
    return {f.path: f.field_type for f in guaranteed_scalar_fields(kind)}


def test_text_layer_reader_on_every_digital_bill(out):
    for e in entries(out, "digital_pdf", "electricity_bill"):
        t = truth(out, e)
        doc = load(out / e["file"])
        r = read_local(doc, "text_layer", "electricity")
        assert isinstance(r, ReaderOutput)
        assert (r.reader, r.method, r.family, r.model_id) == (
            "text_layer",
            "text_layer",
            None,
            None,
        )
        assert all(isinstance(v, RawRead) for v in r.fields.values())
        types = _types("electricity")
        for path in ("energy.kwh", "energy.kvah", "totals.net_payable", "consumer.account_number"):
            assert normalise(r.fields[path].raw, types[path]) == normalise(
                t["fields"][path], types[path]
            )
        assert len(r.meters) == 2 * (len(t["tod"]["kwh"]) + 1)
        assert len([x for x in r.lines if x["kind"] == "item"]) == len(t["charges"])
        assert all(x["page"] == 0 for x in r.lines + r.meters)


def test_text_layer_reader_is_none_without_a_genuine_layer(out):
    e = entries(out, "scan_pdf")[0]
    doc = load(out / e["file"])
    assert read_local(doc, "text_layer", "electricity") is None
    assert page_texts(doc, "text_layer") == []
    assert (
        read_local(load(out / entries(out, "photo_jpeg")[0]["file"]), "text_layer", "electricity")
        is None
    )


def test_page_texts_for_the_gate(out):
    e = next(e for e in entries(out, "digital_pdf") if e["file"].startswith("pvvnl"))
    texts = page_texts(load(out / e["file"]), "text_layer")
    assert len(texts) == 1 and texts[0].startswith("PASCHIMANCHAL VIDYUT VITRAN NIGAM LTD. (PVVNL)")
    assert "KVAH TOTAL" in texts[0] and "NET PAYABLE" in texts[0]


def test_gas_text_layer(out):
    e = next(e for e in entries(out, "digital_pdf", "gas_bill") if "citygas" in e["file"])
    r = read_local(load(out / e["file"]), "text_layer", "gas")
    assert "energy.kwh" not in r.fields and r.meters == []
    assert (
        normalise(r.fields["totals.amount"].raw, "number")
        == truth(out, e)["fields"]["totals.amount"]
    )


# local OCR ------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ocr_outputs(out):
    """Text-layer and OCR outputs for the four electricity digital PDFs (OCR runs once)."""
    pairs = []
    for e in entries(out, "digital_pdf", "electricity_bill"):
        doc = load(out / e["file"])
        text = read_local(doc, "text_layer", "electricity")
        local = read_local(doc, "local_ocr", "electricity")
        pairs.append((e["file"], text, local))
    return pairs


@pytest.mark.ocr
def test_ocr_is_available():
    assert ocr.available()


@pytest.mark.ocr
def test_ocr_agrees_with_the_text_layer_on_most_bills(ocr_outputs):
    types = _types("electricity")
    header = f"{'bill':32} " + " ".join(f"{p.split('.')[-1]:>16}" for p in AGREE_ON)
    table = [header]
    agreeing = 0
    for name, text, local in ocr_outputs:
        assert local is not None and local.reader == "local_ocr" and local.method == "ocr"
        cells, all_agree = [], True
        for path in AGREE_ON:
            a = normalise(text.fields[path].raw, types[path]) if path in text.fields else None
            b = normalise(local.fields[path].raw, types[path]) if path in local.fields else None
            ok = a is not None and a == b
            all_agree &= ok
            cells.append(f"{'agree' if ok else ('missing' if b is None else 'differs'):>16}")
        agreeing += all_agree
        table.append(f"{name:32} " + " ".join(cells))
    table.append(f"bills agreeing on every field: {agreeing} of {len(ocr_outputs)}")
    print("\nOCR agreement with the text layer\n" + "\n".join(table))
    assert agreeing >= 3, "\n".join(table)


@pytest.mark.ocr
def test_ocr_words_carry_confidence_and_fractions(ocr_outputs, out):
    e = entries(out, "digital_pdf", "electricity_bill")[0]
    doc = load(out / e["file"])
    texts = page_texts(doc, "local_ocr")  # OCR runs here once and is kept on the page
    assert len(texts) == 1 and "VIDYUT" in texts[0]
    words = doc.pages[0].ocr_words
    assert words and all(isinstance(w.confidence, Decimal) for w in words)
    assert all(Decimal(0) <= w.x0 < w.x1 <= Decimal(1) for w in words)
    assert page_texts(doc, "local_ocr") == texts  # cached, not re-run


@pytest.mark.ocr
def test_ocr_reads_a_scan(out):
    e = next(e for e in entries(out, "scan_pdf") if e["file"].startswith("avvnl"))
    t = truth(out, e)
    r = read_local(load(out / e["file"]), "local_ocr", "electricity")
    assert r is not None and r.reader == "local_ocr"
    assert (
        normalise(r.fields["consumer.account_number"].raw, "identifier")
        == t["fields"]["consumer.account_number"]
    )
    assert len(r.meters) >= 8 and any(x["kind"] == "subtotal" for x in r.lines)


@pytest.mark.ocr
def test_rapidocr_fallback_when_paddle_cannot_import(out, monkeypatch):
    e = entries(out, "digital_pdf", "electricity_bill")[0]
    page = load(out / e["file"]).pages[0]
    crop = page.image.crop((100, 220, 700, 300))  # the KNO cell and its value
    monkeypatch.setitem(sys.modules, "paddleocr", None)
    monkeypatch.setattr(ocr, "_engine", None)
    words = ocr.read_words(crop, 0)
    assert ocr.engine_name() == "rapidocr"
    texts = [w.text for w in words]
    assert "KNO" in texts and truth(out, e)["printed"]["consumer.account_number"] in texts
