"""The two local readers (build prompt 5.1): `text_layer` over a genuine PDF text layer and
`local_ocr` over the rendered pages, both through the same label rule and row rules, each
producing a `ReaderOutput` the consensus step consumes. Neither sees a model value or the
other's regions.
"""

from __future__ import annotations

import logging
from typing import Literal

from billx.reader.ingest import Document
from billx.reader.read.consensus import RawRead, ReaderOutput
from billx.reader.read.label import read_labels
from billx.reader.read.rows import extract_lines, extract_meters
from billx.reader.read.words import WordBox, group_lines, line_text

log = logging.getLogger(__name__)
LocalReader = Literal["text_layer", "local_ocr"]
METHOD = {"text_layer": "text_layer", "local_ocr": "ocr"}
REGISTER_TOTALS = {"energy.kwh": "kWh", "energy.kvah": "kVAh"}


def page_words(document: Document, reader: LocalReader) -> list[list[WordBox]] | None:
    """Per page, the reader's words. None for `text_layer` when no page has a genuine text
    layer (a page without one contributes no words). OCR runs once per page and is kept on
    the page."""
    if reader == "text_layer":
        if not document.has_text_layer():
            return None
        return [list(p.text_words or []) for p in document.pages]
    from billx.reader import ocr

    out = []
    for page in document.pages:
        if page.ocr_words is None:
            page.ocr_words = ocr.read_words(page.image, page.index)
        out.append(list(page.ocr_words))
    return out


def page_texts(document: Document, reader: LocalReader) -> list[str]:
    """Each page's words in reading order joined by spaces (for the document-type gate); an
    empty list when the reader has nothing for this document."""
    pages = page_words(document, reader)
    if pages is None:
        return []
    return [" ".join(line_text(line) for line in group_lines(words)) for words in pages]


def read_local(document: Document, reader: LocalReader, bill_kind: str) -> ReaderOutput | None:
    """One reader's output for the whole document: guaranteed fields by the label rule, meter
    rows and printed lines. None when the reader has no words for this document."""
    pages = page_words(document, reader)
    if pages is None:
        return None
    words = [w for page in pages for w in page]
    out = ReaderOutput(reader=reader, method=METHOD[reader])
    out.fields = read_labels(words, bill_kind)
    out.meters = extract_meters(words)
    out.lines = extract_lines(words)
    for path, register in REGISTER_TOTALS.items():
        if path not in out.fields and bill_kind == "electricity":
            total = _register_total(out.meters, register)
            if total:
                out.fields[path] = total
    log.info(
        "%s read %s: %d fields, %d meter rows, %d lines",
        reader,
        document.sha256[:12],
        len(out.fields),
        len(out.meters),
        len(out.lines),
    )
    return out


def _register_total(meters: list[dict], register: str) -> RawRead | None:
    """`energy.kwh` / `energy.kvah` when no label names them: the printed consumption of the
    register's "Total" meter row (the register total printed on the bill, not a sum)."""
    for row in meters:
        if row["register"] == register and row["tod_slot"] == "Total":
            return RawRead(str(row["consumption"]), row["page"], row["region"])  # type: ignore[arg-type]
    return None
