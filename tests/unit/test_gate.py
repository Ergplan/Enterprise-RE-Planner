"""The document-type gate (5.0) on the synthetic set's text layers: every synthetic document
gets its type from local signals alone; nothing is misread as an electricity bill."""

import pypdfium2 as pdfium
import pytest

from billx.platform.synth.cli import build
from billx.reader.identify.gate import classify

EXPECTED = {
    "avvnl-ht-synth-v1": "electricity_bill",
    "pvvnl-hv2-synth-v1": "electricity_bill",
    "gas-citygas-synth-v1": "gas_bill",
    "gas-gridsales-synth-v1": "gas_bill",
    "water-municipal-synth-v1": "water_bill",
    "telecom-fictional-synth-v1": "telecom_bill",
    "invoice-supplies-synth-v1": "other_invoice",
    "receipt-store-synth-v1": "not_a_bill",
    "letter-synth-v1": "not_a_bill",
}


@pytest.fixture(scope="module")
def digital(tmp_path_factory):
    out = tmp_path_factory.mktemp("synth")
    build(out, 1)
    found = {}
    for pdf in sorted(out.glob("*.digital.pdf")):
        doc = pdfium.PdfDocument(str(pdf))
        try:
            text = " ".join(p.get_textpage().get_text_range() for p in doc)
        finally:
            doc.close()
        layout = pdf.name.split(".")[0].rsplit("_", 1)[0]
        found.setdefault(layout, []).append(text)
    return found


def test_every_synthetic_document_is_typed_from_local_signals(digital):
    assert set(digital) == set(EXPECTED)
    for layout, texts in digital.items():
        for text in texts:
            v = classify(text)
            assert (v.document_type, v.unclear) == (EXPECTED[layout], False), (layout, v.scores)


def test_an_empty_page_is_unclear_never_a_bill():
    v = classify("")
    assert v.document_type == "not_a_bill" and v.unclear


def test_a_gas_bill_is_never_an_electricity_bill():
    v = classify("Synthetic City Gas Ltd  Gas Consumed (SCM) 12,345  GCV (kcal/SCM) 9100")
    assert v.document_type == "gas_bill"
