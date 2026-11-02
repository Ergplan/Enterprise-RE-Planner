"""The `docling` reader: Docling's tables turned into fields, meter rows and lines.

The documents here are hand-built DoclingDocument JSON with synthetic figures, in the shape
docling-serve returns (pages with sizes, texts with provenance, tables with cells)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from billx.core.proof import ReadingView, decide
from billx.reader.read import docling

W, H = 1000.0, 1400.0


def _cell(text, r, c, *, rs=1, cs=1, header=False, y=None):
    top = 100 + r * 30 if y is None else y
    return {
        "bbox": {
            "l": 50 + c * 90,
            "t": top,
            "r": 130 + c * 90,
            "b": top + 20,
            "coord_origin": "TOPLEFT",
        },
        "row_span": rs,
        "col_span": cs,
        "start_row_offset_idx": r,
        "end_row_offset_idx": r + rs,
        "start_col_offset_idx": c,
        "end_col_offset_idx": c + cs,
        "text": text,
        "column_header": header,
    }


def _table(page, top, rows, cols, cells):
    return {
        "prov": [
            {
                "page_no": page,
                "bbox": {
                    "l": 40,
                    "t": H - top,
                    "r": 960,
                    "b": H - top - 300,
                    "coord_origin": "BOTTOMLEFT",
                },
            }
        ],
        "data": {"num_rows": rows, "num_cols": cols, "table_cells": cells},
    }


def _text(page, top, text):
    return {
        "text": text,
        "label": "section_header",
        "prov": [
            {
                "page_no": page,
                "bbox": {
                    "l": 40,
                    "t": H - top,
                    "r": 600,
                    "b": H - top - 20,
                    "coord_origin": "BOTTOMLEFT",
                },
            }
        ],
    }


def _oa_table(page=1, top=90):
    cells = [
        _cell("Units", 0, 0, rs=2, header=True),
        _cell("MONTHLY CONSUMPTION", 0, 1, cs=2, header=True),
        _cell("(Jan-2026) [KVAH]", 1, 1, header=True),
        _cell("(Feb-2026) [KVAH]", 1, 2, header=True),
        _cell("ADJUSTABLE OPEN ACCESS UNITS (KVAH)", 0, 3, cs=2, header=True),
        _cell("Open Access units to be Adjusted", 1, 3, header=True),
        _cell("Final Adjustable Units", 1, 4, header=True),
        _cell("BILLABLE CONSUMPTION [Feb-2026 KVAH]", 0, 5, rs=2, header=True),
        # TOD-1's label could not be read: inferred from TOD-2 below it
        _cell("1000", 2, 1),
        _cell("1100", 2, 2),
        _cell("300.5", 2, 3),
        _cell("300.500", 2, 4),
        _cell("799.500", 2, 5),
        _cell("T00 2 (11 to 17)", 3, 0),
        _cell("2000", 3, 1),
        _cell("2100", 3, 2),
        _cell("100", 3, 3),
        _cell("100.000", 3, 4),
        _cell("2000.000", 3, 5),
        _cell("Total", 4, 0),
        _cell("3000", 4, 1),
        _cell("3200", 4, 2),
        _cell("400.5", 4, 3),
        _cell("400.500", 4, 4),
        _cell("2799.500", 4, 5),
    ]
    return _table(page, top, 5, 6, cells)


def _reading_table(page, top, a, b):
    cells = [
        _cell("Time Slots", 0, 0, y=top + 10),
        _cell("TOD-1 (05 to 11)", 0, 1, y=top + 10),
        _cell("TOD-2 (11 to 17)", 0, 2, y=top + 10),
        _cell("Total", 0, 3, y=top + 10),
        _cell("KVAH Summer", 1, 0, y=top + 40),
        _cell(a, 1, 1, y=top + 40),
        _cell(b, 1, 2, y=top + 40),
        _cell("9.000", 1, 3, y=top + 40),
    ]
    return _table(page, top, 2, 4, cells)


def _connection_table(page=1, top=600):
    cells = [
        _cell("Category", 0, 0, header=True, y=top + 10),
        _cell("Amount (Rs.)", 0, 1, header=True, y=top + 10),
        _cell("Sanctioned Load (KVA)", 0, 2, header=True, y=top + 10),
        _cell("5000", 0, 3, header=True, y=top + 10),
        _cell("Prev. Arrear", 1, 0, y=top + 40),
        _cell("0.00", 1, 1, y=top + 40),
        _cell("Tariff Type", 1, 2, y=top + 40),
        _cell("HV-1", 1, 3, y=top + 40),
    ]
    return _table(page, top, 2, 4, cells)


def _document():
    return {
        "pages": {
            "1": {"size": {"width": W, "height": H}},
            "2": {"size": {"width": W, "height": H}},
        },
        "texts": [
            _text(2, 80, "Read Date : 01-Jan-26"),
            _text(2, 380, "Read Date : 01-Feb-26"),
        ],
        "tables": [
            _oa_table(),
            _connection_table(),
            _reading_table(2, 100, "1.000", "2.000"),
            _reading_table(2, 400, "1.500", "2.500"),
        ],
    }


def _raw(row, *names):
    return tuple(row[n].raw if hasattr(row[n], "raw") else row[n] for n in names)


def test_slot_rows_take_the_consumption_month_and_the_final_adjusted_units():
    out = docling.read_docling(_document(), {0, 1}, "electricity")
    rows = {m["tod_slot"]: m for m in out.meters if m.get("consumption")}
    assert set(rows) == {"TOD-1 (05 to 11)", "TOD-2 (11 to 17)", "Total"}
    one = rows["TOD-1 (05 to 11)"]  # the label inferred, then given the hours printed elsewhere
    assert _raw(one, "consumption", "open_access", "net") == ("1100", "300.500", "799.500")
    two = rows["TOD-2 (11 to 17)"]
    assert _raw(two, "consumption", "open_access", "net") == ("2100", "100.000", "2000.000")
    assert one["net"].region is not None and one["net"].page == 0  # each cell's own box
    assert all(m["register"] == "kVAh" for m in out.meters)


def test_reading_tables_give_present_and_past_readings_by_read_date():
    out = docling.read_docling(_document(), {0, 1}, "electricity")
    rows = {m["tod_slot"]: m for m in out.meters}
    assert _raw(rows["TOD-1 (05 to 11)"], "present", "past") == ("1.500", "1.000")
    assert _raw(rows["TOD-2 (11 to 17)"], "present") == ("2.500",)


def test_label_value_pairs_in_tables_but_never_a_heading_beside_a_heading():
    out = docling.read_docling(_document(), {0, 1}, "electricity")
    assert out.fields["tariff.category"].raw == "HV-1"  # not "Amount (Rs.)" beside "Category"
    assert out.fields["demand.contract_kva"].raw == "5000"  # a figure in a heading row
    assert out.fields["tariff.category"].page == 0
    assert out.fields["tariff.category"].region is not None


def test_only_the_bills_own_pages_are_read():
    out = docling.read_docling(_document(), {1}, "electricity")
    assert "tariff.category" not in out.fields
    assert not any(m.get("consumption") for m in out.meters)


def test_slot_labels_put_ocr_look_alikes_right():
    assert docling.slot_label("T00 2 (11 to 17)") == "TOD-2 (11 to 17)"
    assert docling.slot_label("TOD·3 [17 to 23)") == "TOD-3 (17 to 23)"
    assert docling.slot_label("TOD 4") == "TOD-4"


def test_an_unreadable_label_is_inferred_only_from_its_neighbours():
    assert docling._infer_slots(["", "TOD-2", "TOD-3"]) == ["TOD-1", "TOD-2", "TOD-3"]
    assert docling._infer_slots(["TOD-1", "x 7 y", "TOD-3"]) == ["TOD-1", None, "TOD-3"]
    assert docling._infer_slots(["Mobile", "Meter"]) == [None, None]


def test_lines_from_an_amount_column_carry_quantity_rate_and_slot():
    cells = [
        _cell("EC Calculation", 0, 0, cs=4, header=True),
        _cell("Slab", 1, 0, header=True),
        _cell("Units", 1, 1, header=True),
        _cell("Rate", 1, 2, header=True),
        _cell("Amount", 1, 3, header=True),
        _cell("TOD-1", 2, 0),
        _cell("100.5", 2, 1),
        _cell("6.800", 2, 2),
        _cell("683.40", 2, 3),
    ]
    doc = {
        "pages": {"1": {"size": {"width": W, "height": H}}},
        "texts": [],
        "tables": [_table(1, 90, 3, 4, cells)],
    }
    out = docling.read_docling(doc, {0}, "electricity")
    line = next(ln for ln in out.lines if ln["label"] == "TOD-1")
    assert line["amount"].region is not None and line["amount"].page == 0
    assert (line["quantity"].raw, line["rate"].raw, line["amount"].raw, line["tod_slot"]) == (
        "100.5",
        "6.800",
        "683.40",
        "TOD-1",
    )


def test_a_layout_reading_verifies_only_with_a_model():
    def view(reader, method, family=None):
        return ReadingView(reader, method, family, "4275")

    assert (
        decide((view("docling", "layout"), view("local_ocr", "ocr"))).verification == "unverified"
    )
    assert decide((view("docling", "layout"), view("text_layer", "text_layer"))).verification == (
        "unverified"
    )
    got = decide((view("docling", "layout"), view("model_a", "vision", "openai")))
    assert got.verification == "verified" and got.readers == ("docling", "model_a")


def test_convert_is_off_without_a_url_and_returns_the_json_content(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "bill.pdf"
    pdf.write_bytes(b"%PDF-1.4 synthetic")
    monkeypatch.delenv("BILLX_DOCLING_URL", raising=False)
    monkeypatch.setenv("BILLX_ENV_FILE", str(tmp_path / "none.env"))
    assert docling.convert(pdf, scanned=True) is None
    monkeypatch.setenv("BILLX_DOCLING_URL", "http://docling.test:5001")
    sent = {}

    def fake_post(url, data, files, timeout):
        sent.update(url=url, data=data)
        return httpx.Response(
            200,
            json={"status": "success", "document": {"json_content": _document()}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    got = docling.convert(pdf, scanned=True)
    assert got is not None and len(got["tables"]) == 4
    assert sent["url"] == "http://docling.test:5001/v1/convert/file"
    assert sent["data"]["force_ocr"] == "true" and sent["data"]["ocr_engine"] == "rapidocr"
    assert docling.convert(pdf, scanned=False) is not None and sent["data"]["force_ocr"] == "false"


def test_a_failing_service_is_no_reading(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "bill.pdf"
    pdf.write_bytes(b"%PDF-1.4 synthetic")
    monkeypatch.setenv("BILLX_DOCLING_URL", "http://docling.test:5001")

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    assert docling.convert(pdf, scanned=True) is None


@pytest.mark.ocr
def test_the_pipeline_adds_the_docling_reader_when_configured(monkeypatch, tmp_path: Path):
    from billx.platform.synth.cli import build
    from billx.reader.pipeline import read_file

    out = tmp_path / "synth"
    build(out, 1)
    path = sorted(p for p in out.glob("pvvnl*.digital.pdf"))[0]
    monkeypatch.setattr(docling, "configured", lambda: True)
    monkeypatch.setattr(docling, "convert", lambda p, scanned: _document())
    bill = read_file(path).bills[0]
    assert "docling" in bill.routes_used


def test_register_totals_give_energy_and_billed_units_with_their_cells():
    out = docling.read_docling(_document(), {0, 1}, "electricity")
    assert out.fields["energy.kvah"].raw == "3200" and out.fields["energy.kvah"].region is not None
    assert out.fields["energy.billed_units"].raw == "2799.500"


def test_a_slot_keeps_the_cell_of_the_figure_it_keeps():
    rows = docling.merge_meter_rows(
        [
            {
                "register": "kVAh",
                "tod_slot": "TOD-1",
                "consumption": "5",
                "_cells": {"consumption": "a"},
            },
            {
                "register": "kVAh",
                "tod_slot": "TOD-1",
                "consumption": "5.000",
                "_cells": {"consumption": "b"},
            },
        ]
    )
    assert rows[0]["consumption"] == "5" and rows[0]["_cells"]["consumption"] == "a"


def _column_bill():
    """A bill printed as columns of headings over values (AVVNL's layout), in one grid with
    the meter table inside it and a twelve-month history below. Synthetic figures."""
    rows = [
        ["K No: No:", "900000000001", "Acc No:", "123", "GSTIN:", "08AAAAA0000A1Z5"],
        [
            "Billing Month",
            "Tariff Code",
            "Area code",
            "Reading Date Bill Issue Date",
            "Due Date",
            "Consumer Name & Address.",
        ],
        ["202601 SYNTH CO", "7000", "R 1", "10-01-2026", "20-01-2026", "M/S"],
        ["Voltage", "Load Factor Cont.Demand (KVA)", "", "", "", ""],
        ["11000", "40.10 2500.00", "", "", "", ""],
        ["Meter No.", "Nature Of Meter", "Present Reading", "Last Reading", "MF", "Consumption"],
        ["11 1", "KWH", "200.5000", "100.5000", "10.0000", "1000.0000"],
        ["11 2", "KVAH", "210.0000", "105.0000", "10.0000", "1050.0000"],
        ["11 3", "KVA", "4.5000", "0.0000", "10.0000", "45.0000"],
    ]
    cells = [_cell(t, r, c) for r, row in enumerate(rows) for c, t in enumerate(row)]
    history = [
        _cell("Bill Month", 0, 0, y=900),
        _cell("202512", 0, 1, y=900),
        _cell("202511", 0, 2, y=900),
        _cell("202510", 0, 3, y=900),
        _cell("Units", 1, 0, y=930),
        _cell("900", 1, 1, y=930),
        _cell("950", 1, 2, y=930),
        _cell("990", 1, 3, y=930),
    ]
    return {
        "pages": {"1": {"size": {"width": W, "height": H}}},
        "texts": [],
        "tables": [_table(1, 90, len(rows), 6, cells), _table(1, 890, 2, 4, history)],
    }


def test_a_column_layout_reads_values_under_their_headings_and_not_the_history():
    out = docling.read_docling(_column_bill(), {0}, "electricity")
    got = {k: v.raw for k, v in out.fields.items()}
    assert got["consumer.account_number"] == "900000000001"  # "K No: No:" is "K No"
    assert got["period.bill_month"] == "202601"  # first in its cell, not the history's 202512
    assert got["period.bill_date"] == "10-01-2026"  # under the heading that ends its cell
    assert got["period.due_date"] == "20-01-2026"
    assert got["tariff.category"] == "7000"
    assert got["demand.contract_kva"] == "2500.00"  # the figure under the heading that ends
    assert "consumer.name" not in got  # "& Address." and "M/S" are not a name


def test_register_rows_inside_a_larger_grid_give_readings_and_totals():
    out = docling.read_docling(_column_bill(), {0}, "electricity")
    rows = {m["register"]: m for m in out.meters}
    assert _raw(rows["kWh"], "present", "past", "multiplying_factor", "consumption") == (
        "200.5000",
        "100.5000",
        "10.0000",
        "1000.0000",
    )
    assert rows["kWh"].get("tod_slot") is None
    assert out.fields["energy.kwh"].raw == "1000.0000"
    assert out.fields["energy.kvah"].raw == "1050.0000"
    assert out.fields["demand.max_kva"].raw == "45.0000"
    assert out.fields["energy.kwh"].region is not None


def test_a_register_printed_on_several_meters_names_no_total():
    rows = [
        {"register": "kWh", "tod_slot": None, "consumption": "1"},
        {"register": "kWh", "tod_slot": None, "consumption": "2"},
    ]
    assert "energy.kwh" not in docling.register_totals(rows)


def test_a_meter_table_with_stacked_headings_slots_and_units_in_cells():
    """The UPPCL layout: "Previous" and "Current" over "Date" and "/Read" columns, registers
    with their slot in one cell, consumption printed with its unit. Synthetic figures."""
    cells = [
        _cell("Previous", 0, 3, cs=2, header=True),
        _cell("Current", 0, 5, cs=2, header=True),
        _cell("Meter Number", 1, 0, header=True),
        _cell("Type Energy", 1, 1, header=True),
        _cell("Demand Recorded", 1, 2, header=True),
        _cell("Date", 1, 3, header=True),
        _cell("/Read", 1, 4, header=True),
        _cell("Date", 1, 5, header=True),
        _cell("/Read", 1, 6, header=True),
        _cell("Diff.", 1, 7, header=True),
        _cell("M.F.", 1, 8, header=True),
        _cell("Meter Units", 1, 9, header=True),
    ]
    A, B = "01-APR-26", "01-MAY-26"
    rows = [
        ("KVA", "6.00", "", "", "", "", "", "10", "60.0 KVA"),
        ("KVAH TOD-1 05-11", "", A, "100", B, "150", "50", "10", "KVAH 500"),
        ("KVAH TOD-2 11-17", "", A, "200", B, "230", "30", "10", "KVAH 300"),
        ("KWH", "", A, "1000", B, "1075", "75", "10", "750 KWH"),
    ]
    for r, values in enumerate(rows, start=2):
        cells.append(_cell("X1", r, 0))
        cells += [_cell(v, r, c) for c, v in enumerate(values, start=1) if v]
    doc = {
        "pages": {"1": {"size": {"width": W, "height": H}}},
        "texts": [],
        "tables": [_table(1, 90, 6, 10, cells)],
    }
    out = docling.read_docling(doc, {0}, "electricity")
    rows_ = {(m["register"], m.get("tod_slot")): m for m in out.meters}
    one = rows_[("kVAh", "TOD-1 05-11")]
    assert _raw(one, "past", "present", "difference", "multiplying_factor", "consumption") == (
        "100",
        "150",
        "50",
        "10",
        "500",
    )
    assert one["consumption"].region is not None
    assert out.fields["energy.kwh"].raw == "750"
    assert out.fields["demand.max_kva"].raw == "60.0"
    assert "energy.kvah" not in out.fields  # slots, but no printed total


def test_a_load_in_a_table_is_the_contract_demand_only_in_kva():
    cells = [_cell("Sanction Load", 0, 0), _cell("600 kVA", 0, 1)]
    cells += [_cell("Sanctioned Load", 1, 0), _cell("15", 1, 1)]
    doc = {"pages": {"1": {"size": {"width": W, "height": H}}}, "texts": []}
    doc["tables"] = [_table(1, 90, 2, 2, cells[:2])]
    assert docling.read_docling(doc, {0}, "electricity").fields["demand.contract_kva"].raw == "600"
    doc["tables"] = [_table(1, 90, 2, 2, cells[2:])]
    assert "demand.contract_kva" not in docling.read_docling(doc, {0}, "electricity").fields
