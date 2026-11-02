"""The `docling` reader (method `layout`): Docling's page layout and table structure.

Docling (run as a docling-serve container, `BILLX_DOCLING_URL`) converts the file once: text
blocks and tables with every cell's row, column, span and box, read by its own OCR on a scan
(RapidOCR) or from the text layer of a digital PDF. This reader turns that into a
`ReaderOutput` the consensus step consumes like any other:

- **fields** by the label rule over Docling's words (text blocks and table cells, each with
  its box), the same rule the local readers use;
- **meter rows** from the tables themselves: a row whose first cell names a time-of-day slot
  (or the total) gives that slot's consumption, open-access and net units from the columns
  whose headings say so; a slot-wise reading table (slots as columns, one table per read
  date) gives each slot's present and past readings;
- **printed lines** from tables with an amount column, and from label-amount pairs.

It finds a field by table position rather than by the label next to it, but it is a local
reader all the same (method `layout`): it never verifies a value with the text layer or
local OCR (proof rule 2 and 3), only with a model reader. Every reading carries its page and
the box of the cell it came from.

Docling is optional: without `BILLX_DOCLING_URL`, or when the service fails, the reader is
absent and the bill is read as before. Logs carry the file hash and counts only.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from billx.core.settings import setting
from billx.reader.read.consensus import RawRead, ReaderOutput
from billx.reader.read.label import LOAD_LABEL, guaranteed_scalar_fields, read_labels, sane
from billx.reader.read.words import WordBox, detach_colons, frac, region_of, split_phrase

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 900
OPTIONS = {
    "to_formats": "json",
    "do_ocr": "true",
    "ocr_engine": "rapidocr",
    "table_mode": "accurate",
    "images_scale": "2",
    "image_export_mode": "placeholder",
}


# the service -----------------------------------------------------------------------------


def configured() -> bool:
    return bool(setting("BILLX_DOCLING_URL"))


def convert(path: Path, *, scanned: bool) -> dict | None:
    """Docling's document (DoclingDocument JSON) for the file, or None when Docling is not
    configured or the call fails. A scan is OCR'd on every page (`force_ocr`); a digital PDF
    keeps its text layer."""
    import httpx

    url = setting("BILLX_DOCLING_URL")
    if not url:
        return None
    timeout = float(setting("BILLX_DOCLING_TIMEOUT", str(DEFAULT_TIMEOUT_S)) or DEFAULT_TIMEOUT_S)
    data = {**OPTIONS, "force_ocr": "true" if scanned else "false"}
    try:
        with open(path, "rb") as f:
            response = httpx.post(
                url.rstrip("/") + "/v1/convert/file",
                data=data,
                files={"files": (path.name, f, "application/octet-stream")},
                timeout=timeout,
            )
        response.raise_for_status()
        body = response.json()
    except Exception as e:  # noqa: BLE001 - Docling is an extra reader; its failure is logged
        log.warning("docling failed: %s", type(e).__name__)
        return None
    if body.get("status") not in ("success", "partial_success"):
        log.warning("docling status %s", body.get("status"))
        return None
    document = (body.get("document") or {}).get("json_content")
    return document if isinstance(document, dict) else None


# geometry --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    text: str
    row: int
    col: int
    row_end: int
    col_end: int
    header: bool
    page: int  # 0-based, as every reader's pages
    box: tuple[Decimal, Decimal, Decimal, Decimal] | None  # fractions, top left origin

    def words(self) -> list[WordBox]:
        if self.box is None or not self.text.strip():
            return []
        return split_phrase(self.text, self.page, *self.box)

    def raw(self) -> RawRead:
        words = self.words()
        return RawRead(self.text.strip(), self.page, region_of(words) if words else None)


@dataclass
class Table:
    page: int
    top: Decimal
    cells: list[Cell]
    num_rows: int
    num_cols: int
    title: str | None = None  # the section heading printed just above the table

    def grid(self) -> list[list[Cell | None]]:
        grid: list[list[Cell | None]] = [[None] * self.num_cols for _ in range(self.num_rows)]
        for c in self.cells:
            for r in range(c.row, min(c.row_end, self.num_rows)):
                for k in range(c.col, min(c.col_end, self.num_cols)):
                    grid[r][k] = c
        return grid

    def header_rows(self) -> int:
        n = 0
        for r, row in enumerate(self.grid()):
            if row and all(c is None or c.header for c in row) and any(c for c in row):
                n = r + 1
            else:
                break
        return n

    def column_heading(self, col: int) -> str:
        """Every header cell above a column, outermost first, distinct texts only."""
        parts: list[str] = []
        grid = self.grid()
        for r in range(self.header_rows()):
            c = grid[r][col]
            if c is not None and c.text.strip() and c.text.strip() not in parts:
                parts.append(c.text.strip())
        return " - ".join(parts)


def _box(bbox: dict, size: dict) -> tuple[Decimal, Decimal, Decimal, Decimal] | None:
    try:
        width, height = float(size["width"]), float(size["height"])
        left, right = float(bbox["l"]), float(bbox["r"])
        top, bottom = float(bbox["t"]), float(bbox["b"])
    except (KeyError, TypeError, ValueError):
        return None
    if bbox.get("coord_origin", "TOPLEFT") == "BOTTOMLEFT":
        top, bottom = height - top, height - bottom
    if top > bottom:
        top, bottom = bottom, top
    return frac(left, width), frac(top, height), frac(right, width), frac(bottom, height)


def _pages(document: dict) -> dict[int, dict]:
    return {int(k): v.get("size", {}) for k, v in (document.get("pages") or {}).items()}


def texts(document: dict, pages: set[int]) -> list[tuple[int, Decimal, str, Any]]:
    """(page 0-based, top, text, box) of every text block on the given pages."""
    sizes = _pages(document)
    out = []
    for t in document.get("texts") or []:
        for prov in t.get("prov") or []:
            page = int(prov.get("page_no", 0)) - 1
            if page not in pages:
                continue
            box = _box(prov.get("bbox") or {}, sizes.get(page + 1, {}))
            if box is not None and (t.get("text") or "").strip():
                out.append((page, box[1], t["text"], box))
    return out


def tables(document: dict, pages: set[int]) -> list[Table]:
    sizes = _pages(document)
    heads = [(p, top, text) for p, top, text, _ in texts(document, pages)]
    out = []
    for t in document.get("tables") or []:
        prov = (t.get("prov") or [{}])[0]
        page = int(prov.get("page_no", 0)) - 1
        if page not in pages:
            continue
        size = sizes.get(page + 1, {})
        tbox = _box(prov.get("bbox") or {}, size)
        data = t.get("data") or {}
        cells = []
        for c in data.get("table_cells") or []:
            cells.append(
                Cell(
                    text=str(c.get("text") or ""),
                    row=int(c.get("start_row_offset_idx", 0)),
                    col=int(c.get("start_col_offset_idx", 0)),
                    row_end=int(c.get("end_row_offset_idx", 1)),
                    col_end=int(c.get("end_col_offset_idx", 1)),
                    header=bool(c.get("column_header")),
                    page=page,
                    box=_box(c.get("bbox") or {}, size) if c.get("bbox") else None,
                )
            )
        top = tbox[1] if tbox else Decimal(0)
        above = [(t_top, text) for p, t_top, text in heads if p == page and t_top < top]
        title = max(above)[1] if above else None
        rows, cols = int(data.get("num_rows", 0)), int(data.get("num_cols", 0))
        out.append(Table(page, top, cells, rows, cols, title))
    return out


def words(document: dict, pages: set[int]) -> list[WordBox]:
    """Docling's words: every text block and every table cell, each split into words."""
    out: list[WordBox] = []
    for page, _, text, box in texts(document, pages):
        out.extend(split_phrase(text, page, *box))
    for table in tables(document, pages):
        for c in table.cells:
            out.extend(c.words())
    return detach_colons(out)


# meter rows ------------------------------------------------------------------------------

_SLOT = re.compile(
    r"(?i)^\s*(?:t[o0]{1,2}d?|tz|zone|slot)\s*[-·.:]?\s*\d"
    r"|^\s*(?:peak|off[- ]?peak|normal|night|morning|evening|day)\b"
)
_TOTAL = re.compile(r"(?i)^\s*(?:grand\s+)?total\b")
_REGISTER = re.compile(r"(?i)\b(kvah|kwh|kvarh)\b")
_MONTH = re.compile(
    r"(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/ ']?(\d{2,4})\b"
)
_NUMBER = re.compile(r"^-?[\d,]+(?:\.\d+)?$")
_READ_DATE = re.compile(r"(?i)read\s*date\s*[:\-]?\s*(\S+)")


def slot_label(text: str) -> str:
    """A slot's label as a key: OCR's look-alikes of TOD ("T00", "TOO", "T0D") and the
    middle dot read for a hyphen are put right; the label is a key, never a value."""
    s = re.sub(r"(?i)^\s*t[o0][o0d]\b", "TOD", text.strip())
    s = re.sub(r"(?i)^\s*t[o0]{2}(?=\s*[-·.]?\s*\d)", "TOD", s)
    s = s.replace("·", "-").replace("[", "(").replace("]", ")")
    s = re.sub(r"(?i)^TOD\s*[-.]?\s*(\d)", r"TOD-\1", s)
    return re.sub(r"\s+", " ", s).strip()


def _register_of(text: str) -> str | None:
    m = _REGISTER.search(text)
    return {"kvah": "kVAh", "kwh": "kWh", "kvarh": "kVArh"}[m.group(1).lower()] if m else None


def _month_of(text: str) -> tuple[int, int] | None:
    m = _MONTH.search(text)
    if not m:
        return None
    months = "jan feb mar apr may jun jul aug sep oct nov dec".split()
    year = int(m.group(2))
    return (year + 2000 if year < 100 else year, months.index(m.group(1).lower()[:3]) + 1)


def _role(heading: str) -> str | None:
    h = heading.lower()
    if re.search(r"billable|net\s*(?:billed|units)|distribution\s*licensee", h):
        return "net"
    if re.search(r"final\s*adjust", h):
        return "open_access:3"
    if re.search(r"actual\s*adjusted|adjusted\s*oa", h):
        return "open_access:2"
    if re.search(r"(?:units\s*to\s*be\s*adjusted|open\s*access.*adjust|adjust.*open\s*access)", h):
        if "extra" not in h:
            return "open_access:1"
    if re.search(r"consumption|units\s*consumed", h) and "available" not in h:
        return "consumption"
    return None


_FIGURE = re.compile(r"^-?[\d,]+(?:[.\s]\d+)?$")


def _number(cell: Cell | None) -> str | None:
    """The cell's text when it is a figure as printed (OCR may have read a decimal point as a
    space: the text is kept as read, and consensus decides)."""
    if cell is None:
        return None
    text = cell.text.strip()
    return text if _FIGURE.match(text) else None


def _figure(cell: Cell | None) -> RawRead | None:
    """A figure cell as a RawRead (its text, page and box), or None."""
    return cell.raw() if cell is not None and _number(cell) is not None else None


def slot_rows(table: Table) -> list[dict]:
    """Meter rows from a table whose rows are slots: consumption, open access and net units
    from the columns whose headings name them. Where two consumption columns name months
    (the open-access month and the consumption month), the one of the net column's month
    is the bill's; failing that, the later month."""
    heads = table.header_rows()
    if heads == 0:
        return []
    grid = table.grid()
    headings = {c: table.column_heading(c) for c in range(table.num_cols)}
    register = next(
        (r for r in (_register_of(h) for h in headings.values()) if r), None
    ) or _register_of(table.title or "")
    roles: dict[int, str] = {}
    for col, h in headings.items():
        role = _role(h)
        if role:
            roles[col] = role
    if "net" not in roles.values() and not any(r == "consumption" for r in roles.values()):
        return []
    net_month = next((_month_of(headings[c]) for c, r in roles.items() if r == "net"), None)
    consumption_cols = [c for c, r in roles.items() if r == "consumption"]
    if len(consumption_cols) > 1:
        dated = [(c, _month_of(headings[c])) for c in consumption_cols]
        pick = next((c for c, m in dated if m and m == net_month), None)
        if pick is None:
            known = [(m, c) for c, m in dated if m]
            pick = max(known)[1] if known else consumption_cols[-1]
        for c in consumption_cols:
            if c != pick:
                roles.pop(c)
    oa_cols = sorted((r, c) for c, r in roles.items() if r.startswith("open_access"))
    for _, c in oa_cols[:-1]:
        roles.pop(c)
    rows = []
    labels = [
        (grid[r][0].text.strip() if grid[r][0] is not None and not grid[r][0].header else "")
        for r in range(heads, table.num_rows)
    ]
    slots = _infer_slots(labels)
    for r in range(heads, table.num_rows):
        slot = slots[r - heads]
        if slot is None:
            continue
        row: dict[str, Any] = {
            "register": register or "kWh",
            "tod_slot": slot,
            "page": table.page,
            "region": None,
        }
        boxes = []
        for col, role in roles.items():
            cell = grid[r][col]
            value = _number(cell)
            if value is None or cell is None:
                continue
            row[role.split(":")[0]] = value
            row.setdefault("_cells", {})[role.split(":")[0]] = cell.raw()
            boxes.extend(cell.words())
        if len(row) > 4:
            row["region"] = region_of(boxes) if boxes else None
            rows.append(row)
    return rows


_NUMBERED = re.compile(r"(?i)^TOD-(\d)")


def _infer_slots(labels: list[str]) -> list[str | None]:
    """Each row's slot from its first cell. A row whose label OCR could not read, lying
    between numbered slot rows ("TOD-1", ?, "TOD-3") or right after the last one before the
    total, is the next number in the sequence when its text is empty or holds that digit.
    The slot is the row's key, never a value: a wrong guess leaves the row's figures
    unmatched with the other readers' rows (unverified), it never verifies them."""
    out: list[str | None] = []
    for label in labels:
        if _TOTAL.match(label):
            out.append("Total")
        elif _SLOT.match(label):
            out.append(slot_label(label))
        else:
            out.append(None)
    for _ in range(len(out)):  # until nothing more can be inferred
        if not _infer_once(out, labels):
            break
    return out


def _infer_once(out: list[str | None], labels: list[str]) -> bool:
    changed = False
    for i, slot in enumerate(out):
        if slot is not None:
            continue
        prev = out[i - 1] if i > 0 else None
        nxt = out[i + 1] if i + 1 < len(out) else None
        m_prev = _NUMBERED.match(prev or "")
        m_next = _NUMBERED.match(nxt or "")
        n = None
        if m_prev:
            n = int(m_prev.group(1)) + 1
        elif m_next:
            n = int(m_next.group(1)) - 1
        if n is None or n < 1:
            continue
        if m_prev and m_next and int(m_next.group(1)) != n + 1:
            continue
        if not m_next and nxt not in ("Total", None):
            continue
        text = labels[i]
        if text == "" or str(n) in re.sub(r"\(.*", "", text):
            out[i] = f"TOD-{n}"
            changed = True
    return changed


def canonical_slots(rows: list[dict]) -> list[dict]:
    """A numbered slot printed with its hours in one table and without them in another
    ("TOD-1" and "TOD-1 (05 to 11)") is one slot: every row takes the fullest label."""
    fullest: dict[str, str] = {}
    for row in rows:
        m = _NUMBERED.match(row.get("tod_slot") or "")
        if m and len(row["tod_slot"]) > len(fullest.get(m.group(1), "")):
            fullest[m.group(1)] = row["tod_slot"]
    for row in rows:
        m = _NUMBERED.match(row.get("tod_slot") or "")
        if m:
            row["tod_slot"] = fullest[m.group(1)]
    return rows


def reading_rows(tables_: list[Table]) -> list[dict]:
    """Present and past readings from slot-wise reading tables (one per read date, slots as
    columns, a register as each row's label): the latest read date is the present reading,
    the one before it the past reading."""
    by_date: list[tuple[str, dict[tuple[str, str], Cell]]] = []
    for table in tables_:
        m = _READ_DATE.search(table.title or "")
        if not m:
            continue
        from billx.core.normalize import normalise_date

        date = normalise_date(m.group(1))
        if not date:
            continue
        grid = table.grid()
        values: dict[tuple[str, str], Cell] = {}
        slots: dict[int, str] = {}
        for row in grid:
            labels = [(i, c) for i, c in enumerate(row) if c is not None]
            if not labels:
                continue
            first = labels[0][1].text.strip()
            if re.match(r"(?i)time\s*slots?", first):
                slots = {
                    i: slot_label(c.text)
                    for i, c in labels[1:]
                    if _SLOT.match(c.text) or _TOTAL.match(c.text)
                }
                continue
            register = _register_of(first)
            if register is None or not slots or re.search(r"(?i)winter", first):
                continue
            for i, slot in slots.items():
                cell = row[i] if i < len(row) else None
                if _number(cell) is not None and cell is not None:
                    values[(register, "Total" if _TOTAL.match(slot) else slot)] = cell
        if values:
            by_date.append((date, values))
    if len(by_date) < 2:
        return []
    by_date.sort()
    (_, past), (_, present) = by_date[-2], by_date[-1]
    rows = []
    for key, cell in present.items():
        prev = past.get(key)
        rows.append(
            {
                "register": key[0],
                "tod_slot": key[1],
                "present": cell.text.strip(),
                "past": prev.text.strip() if prev else None,
                "page": cell.page,
                "region": region_of(cell.words() + (prev.words() if prev else [])) or None,
                "_cells": {"present": cell.raw(), **({"past": prev.raw()} if prev else {})},
            }
        )
    return rows


def merge_meter_rows(rows: list[dict]) -> list[dict]:
    """One row per register and slot: the reading-table and consumption-table rows of a slot
    become one (each figure from where it is printed)."""
    merged: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for row in rows:
        key = (row["register"], (row.get("tod_slot") or "").upper())
        if key not in merged:
            merged[key] = {}
            order.append(key)
        target = merged[key]
        for k, v in row.items():
            if k == "_cells":
                cells = target.setdefault("_cells", {})
                for name, cell in v.items():
                    cells.setdefault(name, cell)  # the cell of the figure the row keeps
            elif v is not None and target.get(k) is None:
                target[k] = v
    return [merged[k] for k in order]


def _with_cells(row: dict) -> dict:
    """A meter row as consensus takes it: each figure the RawRead of its cell (page and box)
    where the cell is known, else its text; the private `_cells` dropped."""
    cells = row.get("_cells") or {}
    return {
        k: (cells[k] if k in cells and cells[k].raw == v else v)
        for k, v in row.items()
        if not k.startswith("_")
    }


# printed lines ---------------------------------------------------------------------------


def table_lines(table: Table) -> list[dict]:
    """Printed lines with an amount: a table with an "amount" column gives one line per row
    (its label, quantity, rate and amount columns by heading, within the heading's block);
    any other table gives a line for each label cell followed by a number."""
    grid = table.grid()
    heads = table.header_rows()
    headings = {c: table.column_heading(c).lower() for c in range(table.num_cols)}
    lines = []
    amount_cols = [c for c, h in headings.items() if re.search(r"\bamount\b", h)]
    used: set[int] = set()
    for a in amount_cols:
        block = headings[a].split(" - ")[0]
        cols = [c for c, h in headings.items() if h.split(" - ")[0] == block]
        label_col = min(cols)
        qty = next((c for c in cols if re.search(r"\bunits?\b|quantity|qty", headings[c])), None)
        rate = next((c for c in cols if re.search(r"\brate\b", headings[c])), None)
        used.update(cols)
        for r in range(heads, table.num_rows):
            label_cell, amount_cell = grid[r][label_col], grid[r][a]
            if label_cell is None or _number(amount_cell) is None or amount_cell is None:
                continue
            label = label_cell.text.strip()
            if not label or _NUMBER.match(label.replace(" ", "")):
                continue
            line = {
                "group": block or table.title,
                "label": label,
                "quantity": _figure(grid[r][qty]) if qty is not None else None,
                "rate": _figure(grid[r][rate]) if rate is not None else None,
                "amount": amount_cell.raw(),
                "tod_slot": slot_label(label) if _SLOT.match(label) else None,
                "page": table.page,
                "region": region_of(label_cell.words() + amount_cell.words()) or None,
            }
            lines.append(line)
    for r in range(heads, table.num_rows):
        row = grid[r]
        k = 0
        while k < table.num_cols - 1:
            if k in used:
                k += 1
                continue
            cell, nxt = row[k], row[k + 1]
            if (
                cell is not None
                and nxt is not None
                and nxt is not cell
                and (k + 1) not in used
                and cell.text.strip()
                and not _number(cell)
                and _number(nxt) is not None
            ):
                group = headings.get(k, "").split(" - ")[0] or table.title
                lines.append(
                    {
                        "group": group,
                        "label": cell.text.strip(),
                        "quantity": None,
                        "rate": None,
                        "amount": nxt.raw(),
                        "tod_slot": None,
                        "page": table.page,
                        "region": region_of(cell.words() + nxt.words()) or None,
                    }
                )
                k += 2
                continue
            k += 1
    return lines


# key-value pairs in tables -----------------------------------------------------------------


def table_fields(tables_: list[Table], bill_kind: str) -> dict[str, RawRead]:
    """Guaranteed fields printed as a label cell with its value in the next cell of the same
    table row ("Tariff Type | HV-2"). A table states which value belongs to which label, so
    these readings replace the free label rule's for the same field; the first pair in page
    order wins."""
    from billx.reader.read.label import common_labels, guaranteed_scalar_fields, is_typed

    labels = common_labels()
    types = {f.path: f.field_type for f in guaranteed_scalar_fields(bill_kind)}
    found: dict[str, RawRead] = {}
    every = [p for pats in labels.values() for p in pats]

    def is_label(text: str) -> bool:
        t = _label_text(text)
        return any(p.fullmatch(t) for p in every)

    def is_value(text: str) -> bool:
        return any(is_typed(text.strip(), t) for t in ("number", "date"))

    for table in sorted(tables_, key=lambda t: (t.page, t.top)):
        for row in table.grid():
            distinct = list(dict.fromkeys(c for c in row if c is not None))
            if sum(1 for c in distinct if is_label(c.text)) >= 2 and not any(
                is_value(c.text) for c in distinct
            ):
                continue  # a row of column headings: their values are in the row below
            for k in range(len(row) - 1):
                cell, nxt = row[k], row[k + 1]
                if cell is None or nxt is None or nxt is cell or not nxt.text.strip():
                    continue
                # a column heading is not the label of the heading beside it, except for a
                # figure printed in a heading row ("Sanctioned Load (KVA) | 5000")
                heading = cell.header or nxt.header
                label = _label_text(cell.text)
                for path, patterns in labels.items():
                    if path in found or path not in types or path == "utility.name":
                        continue
                    if not any(p.fullmatch(label) for p in patterns):
                        continue
                    value = nxt.text.strip()
                    if is_label(value) or value == cell.text.strip():
                        continue
                    if _series(row, k + 1, types[path]):
                        continue  # a history row ("Bill Month | 202512 | 202511 | ..."), not a pair
                    if path == "demand.contract_kva" and LOAD_LABEL.search(label):
                        figure = _kva_figure(value)
                        if figure is not None:
                            raw = nxt.raw()
                            found[path] = RawRead(figure, raw.page, raw.region)
                        continue  # a load is a demand in kVA only
                    if heading and types[path] not in ("number", "date", "month"):
                        # a heading row may print an identifier beside its label ("K No: |
                        # 900000000001"); never a text value
                        if not (types[path] == "identifier" and _mostly_digits(value)):
                            continue
                    if is_typed(value, types[path]):
                        found[path] = nxt.raw()
    # a label printed as a column heading with its value in the row below ("Tariff Code" over
    # "8000"): taken only when no row pair gave the field, and only when the cell below is
    # not itself a label
    for table in sorted(tables_, key=lambda t: (t.page, t.top)):
        grid = table.grid()
        for r in range(len(grid) - 1):
            for k, cell in enumerate(grid[r]):
                below = grid[r + 1][k] if k < len(grid[r + 1]) else None
                if cell is None or below is None or below is cell or not below.text.strip():
                    continue
                label = _label_text(cell.text)
                value = below.text.strip()
                if is_label(value):
                    continue
                for path, patterns in labels.items():
                    if path in found or path not in types or path == "utility.name":
                        continue
                    kind = types[path]
                    typed = kind in ("number", "date", "month")
                    # a typed figure may sit under a cell that joins two headings ("Reading
                    # Date Bill Issue Date"): the heading that ends the cell is its own
                    names = _tails(label) if typed else [label]
                    if not any(p.fullmatch(n) for n in names for p in patterns):
                        continue
                    if path == "demand.contract_kva" and LOAD_LABEL.search(label):
                        figure = _kva_figure(value)
                        if figure is not None:
                            raw = below.raw()
                            found[path] = RawRead(figure, raw.page, raw.region)
                        continue  # a load is a demand in kVA only
                    if kind == "text" and _HONORIFIC.fullmatch(value):
                        continue  # "M/S" with the name cut off is no name
                    parts = value.split()
                    if is_typed(value, kind):
                        found[path] = below.raw()
                    elif (
                        kind == "number"
                        and len(parts) == 2
                        and all(is_typed(x, kind) for x in parts)
                        and not any(p.fullmatch(label) for p in patterns)
                    ):
                        # two headings joined over two figures joined ("Load Factor
                        # Cont.Demand (KVA)" over "40.10 2500.00"): the heading that ends the
                        # cell has the figure that ends it
                        raw = below.raw()
                        found[path] = RawRead(parts[1], raw.page, raw.region)
                    elif kind == "month" and is_typed(value.split()[0], kind):
                        # a month printed first in a cell joined with its neighbour
                        # ("202601 SYNTH CO ..."); the region is the cell's
                        raw = below.raw()
                        found[path] = RawRead(value.split()[0], raw.page, raw.region)
    return found


def _kva_figure(text: str) -> str | None:
    m = re.fullmatch(r"(?i)\s*([\d,]+(?:\.\d+)?)\s*kva\s*", text)
    return m.group(1) if m else None


_HONORIFIC = re.compile(r"(?i)\s*(m/?s\.?|mr\.?|mrs\.?|ms\.?|shri|smt\.?|sri)\s*")


def _series(row: list[Cell | None], start: int, kind: str) -> bool:
    """Whether the row prints three or more distinct values of one type from `start`: a
    month-by-month history, whose first value is not the bill's."""
    from billx.reader.read.label import is_typed

    if kind not in ("number", "date", "month"):
        return False
    distinct = list(dict.fromkeys(c for c in row[start:] if c is not None))
    run = 0
    for c in distinct:
        if not is_typed(c.text.strip(), kind):
            break
        run += 1
    return run >= 3


def _mostly_digits(text: str) -> bool:
    t = re.sub(r"[\s\-/]", "", text)
    return bool(t) and sum(ch.isdigit() for ch in t) * 2 > len(t)


def _label_text(text: str) -> str:
    """A cell's text as a label: no trailing colon, and no word repeated at its end ("K No:
    No:", a heading layout repeats)."""
    t = re.sub(r"\s*[:：]\s*$", "", text.strip())
    words = t.split()
    if len(words) >= 2 and words[-1].rstrip(":：") == words[-2].rstrip(":："):
        t = " ".join(words[:-1])
    return re.sub(r"\s*[:：]\s*$", "", t)


def _tails(label: str) -> list[str]:
    """The label and every run of two or more words that ends it."""
    words = label.split()
    return [label] + [" ".join(words[i:]) for i in range(1, len(words) - 1)]


_REGISTER_WORD = re.compile(r"(?i)^\s*(kwh|kvah|kva|kvarh|kw)\b\s*(.*?)\s*$")
_UNIT_WORD = re.compile(r"(?i)\b(kwh|kvah|kva|kvarh|kw)\b")
_READING_ROLES = (
    ("present", re.compile(r"(?i)present|current\W*read|curr\.?\s*rdng|new\s*read")),
    ("past", re.compile(r"(?i)last\s*read|previous|prev\.?\s*r|past|old\s*read")),
    ("difference", re.compile(r"(?i)difference|diff\b|advance")),
    ("multiplying_factor", re.compile(r"(?i)^\s*m\.?\s*f\.?\b|multiplying")),
    ("consumption", re.compile(r"(?i)^\s*consumption|units?\s*consumed|meter\s*units")),
)
_DATE_WORD = re.compile(r"(?i)\bdate\b")


def _roles_of(row: list[Cell | None]) -> dict[int, str]:
    roles: dict[int, str] = {}
    for col, c in enumerate(row):
        if c is None or _DATE_WORD.search(c.text):
            continue  # a reading's date column is not the reading
        for role, pattern in _READING_ROLES:
            if role not in roles.values() and pattern.search(c.text):
                roles[col] = role
                break
    return roles


def _stacked(upper: list[Cell | None], lower: list[Cell | None]) -> list[Cell | None]:
    """Two heading rows read as one, column by column ("Previous" over "/Read")."""
    out: list[Cell | None] = []
    for col, low in enumerate(lower):
        up = upper[col] if col < len(upper) else None
        if low is None or up is None or up is low:
            out.append(low if low is not None else up)
        else:
            out.append(dataclasses.replace(low, text=f"{up.text} {low.text}"))
    return out


def _register_cell(row: list[Cell | None]) -> tuple[str, str | None] | None:
    """The register a row reads and its slot: "KWH", or "KVAH TOD-1 05-11" (a slot of it)."""
    for c in row[:4]:
        if c is None:
            continue
        m = _REGISTER_WORD.match(c.text)
        if m:
            rest = m.group(2)
            return m.group(1), (slot_label(rest) if rest else None)
    return None


def _figure_in(cell: Cell | None) -> str | None:
    """A figure printed with its unit in the same cell ("750 KWH", "KVAH 500")."""
    if cell is None:
        return None
    text = _UNIT_WORD.sub("", cell.text).strip()
    return text if _FIGURE.match(text) else None


def register_rows(table: Table) -> list[dict]:
    """Meter rows of a reading table whose rows are registers (KWH, KVAH, KVA), or slots of a
    register ("KVAH TOD-1 05-11"): present and past readings, difference, multiplying factor
    and consumption, by the headings of the nearest heading rows above (one row, or two read
    together: "Previous" over "/Read"); a meter table can sit inside a larger grid. A
    register's row without a slot is its total."""
    grid = table.grid()
    name = {"kwh": "kWh", "kvah": "kVAh", "kva": "kVA", "kvarh": "kVArh", "kw": "kW"}
    roles: dict[int, str] = {}
    above: list[Cell | None] | None = None
    rows = []
    for row in grid:
        found_register = _register_cell(row)
        if found_register is None:
            found = _roles_of(row)
            if above is not None:
                both = _roles_of(_stacked(above, row))
                if len(both) > len(found):
                    found = both
            if len(found) >= 2:
                roles = found
            above = row
            continue
        if len(roles) < 2:
            continue
        register, slot = found_register
        out: dict[str, Any] = {
            "register": name[register.lower()],
            "tod_slot": slot,
            "page": table.page,
            "region": None,
        }
        for col, role in roles.items():
            cell = row[col] if col < len(row) else None
            figure = _figure_in(cell)
            if figure is not None and cell is not None:
                raw = cell.raw()
                out[role] = figure
                out.setdefault("_cells", {})[role] = RawRead(figure, raw.page, raw.region)
        if len(out) > 5:
            rows.append(out)
    return rows


def _as_read(cell: RawRead | str) -> RawRead:
    return cell if isinstance(cell, RawRead) else RawRead(cell)


def register_totals(meters: list[dict]) -> dict[str, RawRead]:
    """`energy.kwh` / `energy.kvah` from a register's printed "Total" row (its consumption), and
    `energy.billed_units` from that row's billed (net) units, when the label rule found none:
    the bill prints them only inside its tables. A register printed once with no slots ("KWH
    | 200.50 | ... | 1000") is its own total, and a kVA register's consumption is the
    recorded demand; a register printed on several meters' rows names no single total."""
    out: dict[str, RawRead] = {}
    has_total = {r.get("register") for r in meters if (r.get("tod_slot") or "").upper() == "TOTAL"}
    whole: dict[str, list[dict]] = {}
    for row in meters:
        if row.get("tod_slot") is None and row.get("register"):
            whole.setdefault(row["register"], []).append(row)
    for row in meters:
        slot = (row.get("tod_slot") or "").upper()
        register = row.get("register") or ""
        if slot != "TOTAL" and not (
            slot == "" and register not in has_total and len(whole.get(register, [])) == 1
        ):
            continue
        consumption, net = row.get("consumption"), row.get("net")
        path = {"kWh": "energy.kwh", "kVAh": "energy.kvah", "kVA": "demand.max_kva"}.get(register)
        if path and consumption is not None:
            out.setdefault(path, _as_read(consumption))
        if net is not None:
            out.setdefault("energy.billed_units", _as_read(net))
    return out


# the reader ------------------------------------------------------------------------------


def read_docling(document: dict, pages: set[int], bill_kind: str) -> ReaderOutput | None:
    """The `docling` reader's output for the given pages (0-based) of a converted file."""
    found = tables(document, pages)
    page_words = words(document, pages)
    if not page_words:
        return None
    out = ReaderOutput(reader="docling", method="layout", family="docling")
    out.fields = {**read_labels(page_words, bill_kind), **table_fields(found, bill_kind)}
    if bill_kind == "electricity":
        rows = []
        for t in found:
            rows.extend(slot_rows(t))
            rows.extend(register_rows(t))
        rows.extend(reading_rows(found))
        rows = canonical_slots(rows)
        out.meters = [_with_cells(row) for row in merge_meter_rows(rows)]
        for path, value in register_totals(out.meters).items():
            out.fields.setdefault(path, value)
    types = {f.path: f.field_type for f in guaranteed_scalar_fields(bill_kind)}
    kept = {path: sane(path, types.get(path, "text"), read) for path, read in out.fields.items()}
    out.fields = {path: read for path, read in kept.items() if read is not None}
    lines = []
    for t in found:
        lines.extend(table_lines(t))
    out.lines = lines
    log.info(
        "docling read: %d fields, %d meter rows, %d lines",
        len(out.fields),
        len(out.meters),
        len(out.lines),
    )
    return out
