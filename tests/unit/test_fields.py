"""The field map: contract paths to the transcription and the required-field lists."""

from decimal import Decimal

from billx.core.normalize import normalise
from billx.core.schema import Reading, make_value
from billx.reader.normalize.fields import (
    bill_from_values,
    either_required,
    required_paths,
    scalar_specs,
)


def _v(path, raw, ft="number", unit=None):
    rs = tuple(
        Reading(reader=r, method=m, family=fam, raw=raw, normalised=normalise(raw, ft), page=0)
        for r, m, fam in (("text_layer", "text_layer", None), ("model_a", "vision", "openai"))
    )
    return make_value(path, ft, rs, unit=unit)


def test_required_lists_follow_the_contract():
    assert required_paths("electricity") == [
        "consumer.account_number",
        "period.from",
        "period.to",
        "period.bill_month",
        "energy.kwh",
        "totals.net_payable",
    ]
    assert either_required("electricity") == {"energy.kwh": "energy.kvah"}
    assert either_required("gas") == {"volume.scm": "energy.mmbtu", "energy.mmbtu": "volume.scm"}
    assert {f["path"] for f in scalar_specs("electricity", "1.0")}.isdisjoint(
        {"consumer.name", "tariff.category", "totals.arrears"}
    )
    assert "consumer.name" in {f["path"] for f in scalar_specs("electricity", "1.1")}


def test_bill_from_values_fills_the_schema_through_the_field_map():
    values = [
        _v("consumer.account_number", "99 4927 801935", "identifier"),
        _v("period.from", "01-04-2025", "date"),
        _v("period.bill_month", "APR-2025", "month"),
        _v("totals.net_payable", "2,43,58,156.60", unit="INR"),
        _v("demand.contract_kva", "6250", unit="kVA"),
        _v("energy.kwh", "24,77,850.00", unit="kWh"),
    ]
    meters = [
        {
            "register": "kWh",
            "tod_slot": "Normal",
            "present": _v("readings[0].current", "56545.82"),
            "past": _v("readings[0].previous", "56082.94"),
            "difference": _v("x", "462.88"),
            "multiplying_factor": _v("y", "1000"),
            "consumption": _v("z", "4,62,880.00"),
        }
    ]
    lines = [
        {
            "label": "Energy Charges",
            "quantity": _v("a", "26,60,310.00"),
            "rate": _v("b", "7.30"),
            "amount": _v("c", "1,94,20,263.00"),
            "unit": "kVAh",
            "code": "energy_charge",
            "kind": "item",
            "stage": "current",
        }
    ]
    bill = bill_from_values("electricity", values, meters, lines)
    assert bill.consumer.account_number == "994927801935"
    assert bill.period.reading_from == "2025-04-01" and bill.period.bill_month == "2025-04"
    assert bill.totals.net_payable == Decimal("24358156.6")
    assert bill.connection.contract_demand_kva == Decimal("6250")
    assert bill.energy.gross_kwh == Decimal("2477850")
    m = bill.meters[0]
    assert (m.quantity, m.tod_slot, m.present, m.gross_units) == (
        "kWh",
        "Normal",
        Decimal("56545.82"),
        Decimal("462880"),
    )
    li = bill.line_items[0]
    assert (li.code, li.quantity, li.rate, li.amount) == (
        "energy_charge",
        Decimal("2660310"),
        Decimal("7.3"),
        Decimal("19420263"),
    )


def test_an_unverified_value_still_lands_in_data_but_a_missing_one_does_not():
    r = Reading(reader="local_ocr", method="ocr", raw="1,000", normalised="1000", page=0)
    single = make_value("totals.net_payable", "number", (r,), unit="INR")
    none = make_value("totals.current_charges", "number", (), unit="INR")
    bill = bill_from_values("electricity", [single, none], [], [])
    assert bill.totals.net_payable == Decimal("1000") and bill.totals.current_charges is None
