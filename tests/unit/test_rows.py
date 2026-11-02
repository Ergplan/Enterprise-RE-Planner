"""billx.reader.read.rows: charge lines and meter rows on the synthetic text layers."""

from decimal import Decimal

import pytest
from _synth import build_set, entries, truth

from billx.reader.ingest import load
from billx.reader.read.rows import extract_lines, extract_meters, is_meter_row, money_like
from billx.reader.read.words import WordBox

D = Decimal


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    return build_set(tmp_path_factory)


def _words(out, e):
    return load(out / e["file"]).pages[0].text_words


def test_every_charge_line_and_the_three_totals(out):
    for e in entries(out, "digital_pdf", "electricity_bill"):
        t = truth(out, e)
        lines = extract_lines(_words(out, e))
        items = {row["label"]: row for row in lines if row["kind"] == "item"}
        for charge in t["charges"]:
            row = items[charge["label"]]
            printed = charge["printed"]
            assert (row["quantity"], row["rate"], row["amount"]) == (
                printed["quantity"],
                printed["rate"],
                printed["amount"],
            ), (e["file"], charge["label"])
            assert row["page"] == 0 and row["region"].w > 0
        assert len(items) == len(t["charges"])
        subtotals = [row for row in lines if row["kind"] == "subtotal"]
        amounts = [row["amount"] for row in subtotals]
        p = t["printed"]
        assert amounts == [
            p["totals.current_charges"],
            p["totals.arrears"],
            p["totals.net_payable"],
        ]
        assert all(row["quantity"] is None and row["rate"] is None for row in subtotals)
        if e["file"].startswith("avvnl"):
            assert all(items[c["label"]]["unit"] == c["unit"] for c in t["charges"])
            assert [r["label"] for r in lines if r["kind"] == "info"] == [
                "Recorded MD (KVA)",
                "Billing Demand (KVA)",
            ]


def test_every_tod_row_as_a_meter_row(out):
    for e in entries(out, "digital_pdf", "electricity_bill"):
        t = truth(out, e)
        rows = extract_meters(_words(out, e))
        by_key = {(r["register"], r["tod_slot"]): r for r in rows}
        for reg, name in (("kwh", "kWh"), ("kvah", "kVAh")):
            for r in t["tod"][reg] + [t["tod"][f"{reg}_total"]]:
                got = by_key[(name, r["slot"])]
                q = r["printed"]
                assert (
                    got["present"],
                    got["past"],
                    got["difference"],
                    got["multiplying_factor"],
                    got["consumption"],
                ) == (q["present"], q["past"], q["difference"], q["mf"], q["consumption"]), (
                    e["file"],
                    name,
                    r["slot"],
                )
                assert got["page"] == 0 and got["region"].h > 0
        assert len(rows) == len(by_key) == 2 * (len(t["tod"]["kwh"]) + 1)


def test_gas_lines(out):
    e = next(e for e in entries(out, "digital_pdf", "gas_bill") if "citygas" in e["file"])
    t = truth(out, e)
    words = _words(out, e)
    lines = extract_lines(words)
    assert [(r["label"], r["kind"]) for r in lines] == [
        ("Gas Charges", "item"),
        ("Transportation Charges", "item"),
        ("VAT @ 5%", "item"),
        ("Total Amount Payable (Rs.)", "subtotal"),
    ]
    assert [r["amount"] for r in lines[:3]] == [c["printed"]["amount"] for c in t["charges"]]
    assert lines[0]["unit"] == "SCM" and lines[2]["quantity"] is None
    assert extract_meters(words) == []


# hand-built lines -----------------------------------------------------------------------


def row(y, *cells):
    words = []
    for x, text in cells:
        x = D(x)
        for part in text.split():
            w = D(len(part)) * D("0.008")
            words.append(WordBox(part, 0, x, D(y), x + w, D(y) + D("0.01")))
            x += w + D("0.004")
    return words


def test_money_like():
    assert money_like("1,500.00") and money_like("-5,61,632.80") and money_like("1087500.00")
    assert money_like("2,660") and not money_like("6250") and not money_like("7.3")
    assert not money_like("09/2026") and not money_like("(Rs.)")


def test_row_shapes():
    one = extract_lines(row("0.1", ("0.05", "Late Payment Surcharge"), ("0.8", "250.00")))
    assert one == [
        {
            "label": "Late Payment Surcharge",
            "quantity": None,
            "rate": None,
            "amount": "250.00",
            "unit": None,
            "kind": "item",
            "page": 0,
            "region": one[0]["region"],
        }
    ]
    two = extract_lines(row("0.1", ("0.05", "Meter Rent"), ("0.5", "2"), ("0.8", "3,000.00")))[0]
    assert (two["quantity"], two["rate"], two["amount"]) == ("2", None, "3,000.00")
    three = extract_lines(row("0.1", ("0.05", "9 Meter Rent month 1 1500.00 1,500.00")))[0]
    assert three["label"] == "Meter Rent" and three["unit"] == "month"
    assert (three["quantity"], three["rate"], three["amount"]) == ("1", "1500.00", "1,500.00")


def test_rows_that_do_not_qualify():
    header = row("0.1", ("0.05", "Particulars"), ("0.5", "Quantity"), ("0.8", "Amount (Rs.)"))
    assert extract_lines(header) == []
    kv = row("0.1", ("0.05", "Recorded MD (KVA) : 3250.00"))
    assert extract_lines(kv) == []
    kv2 = row("0.1", ("0.05", "Previous Reading (SCM) 796830.78 Present Reading (SCM) 944013.99"))
    assert extract_lines(kv2) == []
    meter = row("0.1", ("0.05", "kWh Normal 56545.82 56082.94 462.88 1000 4,62,880.00"))
    assert extract_lines(meter) == [] and is_meter_row(meter)
    assert extract_lines(row("0.1", ("0.8", "1,500.00"))) == []  # an amount with no label


def test_meter_register_from_heading_and_total_slot():
    words = row("0.10", ("0.05", "KWH"))
    words += row("0.12", ("0.05", "Normal 56545.82 56082.94 462.88 1000 462880.00"))
    words += row("0.14", ("0.05", "KWH TOTAL 56545.82 56082.94 462.88 1000 462880.00"))
    words += row("0.16", ("0.05", "KVAH"))
    words += row("0.18", ("0.05", "TOD-1 1.00 0.50 0.50 1 0.50"))
    rows = extract_meters(words)
    assert [(r["register"], r["tod_slot"]) for r in rows] == [
        ("kWh", "Normal"),
        ("kWh", "Total"),
        ("kVAh", "TOD-1"),
    ]
    assert rows[0]["multiplying_factor"] == "1000" and rows[0]["consumption"] == "462880.00"
    # five numbers with no register anywhere above are not a meter row
    assert extract_meters(row("0.1", ("0.05", "X 1 2 3 4 5.00"))) == []
