"""billx.reader.read.label: the label rule on the synthetic text layers and on hand-built lines."""

from decimal import Decimal

import pytest
from _synth import build_set, entries, truth

from billx.core.normalize import normalise
from billx.reader.ingest import load
from billx.reader.read.consensus import RawRead
from billx.reader.read.label import (
    common_labels,
    guaranteed_scalar_fields,
    label_match,
    read_labels,
    sane,
)
from billx.reader.read.words import WordBox

D = Decimal
ELECTRICITY_PATHS = [
    "consumer.account_number",
    "period.from",
    "period.to",
    "period.bill_month",
    "period.due_date",
    "period.bill_date",
    "demand.max_kva",
    "demand.contract_kva",
    "totals.current_charges",
    "totals.arrears",
    "totals.net_payable",
    "tariff.category",
    "utility.name",
]
GAS_PATHS = [
    "consumer.customer_id",
    "period.from",
    "period.to",
    "readings.previous",
    "readings.current",
    "volume.scm",
    "gas.gcv_kcal_per_scm",
    "energy.mmbtu",
    "totals.amount",
]


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    return build_set(tmp_path_factory)


def _types(kind):
    return {f.path: f.field_type for f in guaranteed_scalar_fields(kind)}


def _check(found, t, kind, paths):
    types = _types(kind)
    bad = {}
    for path in paths:
        got = found.get(path)
        want = normalise(t["fields"][path], types[path])
        have = normalise(got.raw, types[path]) if got else None
        if path == "utility.name" and have and want and want in have:
            continue  # the whole printed line carries the short code the truth holds
        if got is None or have != want:
            bad[path] = (got.raw if got else None, t["fields"][path])
    assert not bad, (t["file"], bad)


def test_electricity_digital_pdfs(out):
    bills = entries(out, "digital_pdf", "electricity_bill")
    assert len(bills) == 4
    for e in bills:
        t = truth(out, e)
        found = read_labels(load(out / e["file"]).pages[0].text_words, "electricity")
        paths = ELECTRICITY_PATHS + (["meter.number"] if e["file"].startswith("pvvnl") else [])
        _check(found, t, "electricity", paths)
        for raw in found.values():
            assert raw.page == 0 and raw.region is not None and raw.region.w > 0
        assert "charges.energy" not in found and "charges.demand" not in found


def test_gas_digital_pdf(out):
    e = next(e for e in entries(out, "digital_pdf", "gas_bill") if "citygas" in e["file"])
    found = read_labels(load(out / e["file"]).pages[0].text_words, "gas")
    _check(found, truth(out, e), "gas", GAS_PATHS)


# hand-built layouts ---------------------------------------------------------------------


def row(y, *cells, page=0, h="0.01"):
    """Words from (x, text) cells on one line; a cell's words sit 0.004 apart."""
    words = []
    for x, text in cells:
        x = D(x)
        for part in text.split():
            w = D(len(part)) * D("0.008")
            words.append(WordBox(part, page, x, D(y), x + w, D(y) + D(h)))
            x += w + D("0.004")
    return words


def test_label_match_strips_colon_and_unit():
    pats = common_labels()["readings.previous"]
    assert label_match(row(0, ("0", "Previous Reading (SCM) 796830.78")), pats) == 3
    assert label_match(row(0, ("0", "Previous Reading : 1")), pats) == 3
    assert label_match(row(0, ("0", "Not a label")), pats) == 0
    assert (
        label_match(
            common_labels() and row(0, ("0", "Tariff Cd : HV-2")),
            common_labels()["tariff.category"],
        )
        == 3
    )


def test_value_below_in_a_grid_and_never_a_neighbouring_label():
    words = row("0.10", ("0.05", "KNO"), ("0.30", "A/c No"), ("0.55", "Billing Month"))
    words += row("0.115", ("0.05", "994927801935"), ("0.30", "SYN/1/2"), ("0.55", "APR-2025"))
    words += row(
        "0.14", ("0.05", "Reading Date (Past)"), ("0.55", "Net Payable (A+B)"), ("0.85", "1,234.50")
    )
    words += row("0.155", ("0.05", "01-04-2025"))
    found = read_labels(words, "electricity")
    assert found["consumer.account_number"].raw == "994927801935"
    assert found["period.bill_month"].raw == "APR-2025"
    assert found["period.from"].raw == "01-04-2025"
    assert found["totals.net_payable"].raw == "1,234.50"
    assert found["consumer.account_number"].region.x == D("0.05")


def test_colon_lines_and_right_aligned_totals():
    words = row("0.10", ("0.05", "AC-No : 9912345678"), ("0.50", "Contracted Demand (KVA) : 5000"))
    words += row("0.12", ("0.05", "Bill Month : 09/2026"), ("0.50", "Recorded MD (KVA) : 3250.00"))
    words += row("0.14", ("0.05", "Reading Period : 01-AUG-2026 to 31-AUG-2026"))
    words += row("0.16", ("0.05", "NET PAYABLE"), ("0.70", "2,43,58,156.60"))
    words += row("0.18", ("0.05", "NOTICE: the net payable 99 is due"))
    found = read_labels(words, "electricity")
    assert found["consumer.account_number"].raw == "9912345678"
    assert found["demand.contract_kva"].raw == "5000"
    assert found["demand.max_kva"].raw == "3250.00"
    assert found["period.bill_month"].raw == "09/2026"
    assert found["period.from"].raw == "01-AUG-2026" and found["period.to"].raw == "31-AUG-2026"
    assert found["totals.net_payable"].raw == "2,43,58,156.60"


def test_two_column_table_takes_the_far_right_identifier():
    words = row("0.10", ("0.05", "Customer ID"), ("0.40", "SYNCG25192002"))
    words += row("0.125", ("0.05", "Customer Name"), ("0.40", "Someone"))
    found = read_labels(words, "gas")
    assert found["consumer.customer_id"].raw == "SYNCG25192002"
    # an identifier without a digit is never taken, so the label below is not a value
    only_labels = row("0.10", ("0.05", "Customer ID")) + row("0.125", ("0.05", "Customer Name"))
    assert "consumer.customer_id" not in read_labels(only_labels, "gas")


def test_utility_name_is_the_whole_printed_line():
    words = row("0.05", ("0.2", "AJMER VIDYUT VITRAN NIGAM LIMITED (AVVNL)"))
    assert read_labels(words, "electricity")["utility.name"].raw == (
        "AJMER VIDYUT VITRAN NIGAM LIMITED (AVVNL)"
    )
    words = row("0.05", ("0.2", "Some Vidyut Vitran Nigam"))
    assert read_labels(words, "electricity")["utility.name"].raw == "Some Vidyut Vitran Nigam"
    assert "utility.name" not in read_labels(row("0.05", ("0.2", "Synthetic City Gas Ltd")), "gas")


def test_meter_rows_never_feed_the_label_rule():
    words = row(
        "0.10",
        ("0.05", "KWH TOTAL"),
        ("0.3", "861911.27"),
        ("0.4", "861801.68"),
        ("0.5", "109.59"),
        ("0.6", "18000"),
        ("0.7", "1972620.00"),
    )
    assert "energy.kwh" not in read_labels(words, "electricity")
    words = row("0.10", ("0.05", "Total Units"), ("0.3", "1972620.00"))
    assert read_labels(words, "electricity")["energy.kwh"].raw == "1972620.00"


def test_first_label_in_reading_order_wins_and_labels_only_at_segment_start():
    words = row("0.10", ("0.05", "Due Date : 01-01-2026"), ("0.5", "Pay By : 02-02-2026"))
    assert read_labels(words, "electricity")["period.due_date"].raw == "01-01-2026"
    words = row("0.10", ("0.05", "Please pay the Net Payable amount 100.00"))
    assert "totals.net_payable" not in read_labels(words, "electricity")


def test_utility_name_leaves_out_a_box_on_the_same_line():
    words = row("0.05", ("0.10", "CHIMANCHAL VIDYUT VITRAN NIGAM LIMITED"), ("0.80", "1912"))
    assert read_labels(words, "electricity")["utility.name"].raw == (
        "CHIMANCHAL VIDYUT VITRAN NIGAM LIMITED"
    )


def test_a_neighbouring_label_is_never_taken_as_a_value():
    words = row("0.10", ("0.05", "Tariff Category"), ("0.30", "CONNECTED LOAD(KW)"))
    assert "connection.tariff_category" not in read_labels(words, "electricity")
    words = row("0.10", ("0.05", "Consumer Name"), ("0.30", "ADDRESS"))
    assert "consumer.name" not in read_labels(words, "electricity")
    words = row("0.10", ("0.05", "Account No."), ("0.30", "STANDARDSUPPLYVOLTAGE(KV)11.00"))
    assert "consumer.account_number" not in read_labels(words, "electricity")
    words = row("0.10", ("0.05", "Account No."), ("0.30", "900012002400"))
    assert read_labels(words, "electricity")["consumer.account_number"].raw == "900012002400"


def test_the_rest_of_a_longer_label_and_a_row_of_dates_are_never_a_name():
    # "Consumer Name" with "& Address." printed close after it: one label, not label and value
    words = row("0.10", ("0.05", "Consumer Name"), ("0.17", "& Address."))
    words += row("0.115", ("0.05", "19-05-2026 P 1.0 SIX M/S"))
    assert "consumer.name" not in read_labels(words, "electricity")
    words = row("0.10", ("0.05", "Consumer Name"), ("0.17", "& Address."))
    words += row("0.115", ("0.05", "M/S SYNTH WORKS LTD"))
    assert read_labels(words, "electricity")["consumer.name"].raw == "M/S SYNTH WORKS LTD"


@pytest.mark.parametrize(
    "path,kind,raw,expected",
    [
        ("consumer.account_number", "identifier", "MAR-2026", None),
        ("consumer.account_number", "identifier", "Legacy A/C No. 900012002423", "900012002423"),
        ("consumer.account_number", "identifier", "Date Z99-LL02-00001", "Z99-LL02-00001"),
        ("consumer.account_number", "identifier", "AEN Mobile 900000000001 No. 9000000002", None),
        ("consumer.account_number", "identifier", "1234 5678 9012", "1234 5678 9012"),
        ("tariff.category", "text", "Nature of Industry : MISCELLANEOUS (OTHERS)", None),
        ("tariff.category", "text", "CONSUMER)", None),
        ("tariff.category", "text", "HT-I A", "HT-I A"),
        ("utility.name", "text", "SYNTH LTD (SPL) GST: 1", "SYNTH LTD (SPL) GST: 1"),
        ("energy.power_factor", "number", "1234567.89", None),
        ("energy.power_factor", "number", "0.986", "0.986"),
        ("energy.power_factor", "number", "98.6", "98.6"),
        ("energy.power_factor", "number", "8", None),
        ("energy.power_factor", "number", "0.00", "0.00"),
    ],
)
def test_a_value_its_field_cannot_carry_is_no_reading(path, kind, raw, expected):
    got = sane(path, kind, RawRead(raw, 0, None))
    assert (got.raw if got else None) == expected


def test_footnote_numbers_and_figures_past_another_label_are_not_values():
    # a layout that numbers its labels: "Power Factor 8 :" has its value below the label
    words = row("0.10", ("0.05", "Power Factor 8 :"), ("0.50", "Payable by Due Date"))
    words += row("0.10", ("0.68", "Minimum Payable Amount 10"))
    words += row("0.115", ("0.05", "0.95"), ("0.50", "1,234.00"))
    found = read_labels(words, "electricity")
    assert found["energy.power_factor"].raw == "0.95"
    assert found["totals.net_payable"].raw == "1,234.00"


def test_labels_of_manual_and_scanned_bills():
    words = row("0.10", ("0.05", "DUEDATE 19.01.2026"))
    words += row("0.12", ("0.05", "DUEDATEAMOUNTRS. 1000.00"))
    words += row("0.14", ("0.05", "AFTERDUEDATEAMOUNTRS. 1010.00"))
    month_line = "Bill for the supply of Electrical Energy for the Month of May 2025"
    words += row("0.16", ("0.05", month_line))
    found = read_labels(words, "electricity")
    assert found["period.due_date"].raw == "19.01.2026"
    assert found["totals.net_payable"].raw == "1000.00"
    assert found["period.bill_month"].raw == "May 2025"
    words = row("0.10", ("0.05", "Payable After Due Date Amount Rs. 2.00"))
    words += row("0.12", ("0.05", "Payable before Due Date Amount Rs. 1.00"))
    assert read_labels(words, "electricity")["totals.net_payable"].raw == "1.00"


def test_a_label_heading_a_row_of_figures_has_no_single_value():
    words = row("0.10", ("0.05", "Total kWh Energy 9000.000 8000.000 1000.000 12.00000 12000.000"))
    words += row("0.115", ("0.05", "Normal hours(kVAh) 500.000 400.000 100.000 12.00000 1200.000"))
    words += row("0.30", ("0.05", "Total Amount Payable 5.51 6.07 7.68 8.91- 28.17"))
    found = read_labels(words, "electricity")
    assert "energy.kwh" not in found and "totals.net_payable" not in found


def test_a_formula_between_a_label_and_its_value_is_passed_over():
    words = row("0.10", ("0.05", "Current Bill Amount (Rs.) A + B+ C+ D - G - H + I 1,823,331.00"))
    assert read_labels(words, "electricity")["totals.current_charges"].raw == "1,823,331.00"


def test_a_rate_annotation_between_a_label_and_its_value_is_passed_over():
    words = row("0.10", ("0.05", "Excess Demand Charges"), ("0.40", "Due date rebate @1% 990.00"))
    assert read_labels(words, "electricity")["totals.due_date_rebate"].raw == "990.00"


def test_msedcl_style_labels():
    words = row("0.10", ("0.05", "Highest Recorded Demand 1633.25"))
    words += row("0.12", ("0.05", "Energy Charges KVAH Units : 1000000 8.00 80,00,000.00"))
    found = read_labels(words, "electricity")
    assert found["demand.max_kva"].raw == "1633.25"
    assert found["energy.kvah"].raw == "1000000"


def test_a_sanctioned_load_is_the_contract_demand_only_in_kva():
    words = row("0.10", ("0.05", "Sanction Load : 600 kVA"))
    assert read_labels(words, "electricity")["demand.contract_kva"].raw == "600"
    words = row("0.10", ("0.05", "Sanctioned Load : 15 kW"))
    assert "demand.contract_kva" not in read_labels(words, "electricity")


def test_billed_units_have_labels_of_their_own():
    words = row("0.10", ("0.05", "Net Billed Units : 300000"))
    assert read_labels(words, "electricity")["energy.billed_units"].raw == "300000"


def test_a_label_inside_a_sentence_takes_no_figure_from_below():
    words = row("0.10", ("0.05", "Net Billed Units are the units used for calculation"))
    words += row("0.115", ("0.05", "0.90 or above helps reduce losses"))
    assert "energy.billed_units" not in read_labels(words, "electricity")
