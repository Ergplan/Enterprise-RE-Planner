"""`bill_from_truth`: the engine's transcription (`billx.core.schema.Bill`) built from a
synthetic truth file, exactly as a perfect reader would transcribe the page. Scaffolding for
the planted-misread tests (invariant 10) and the evaluation: the truth's strings become
Decimals, its TOD registers become meter rows, its charges become line items, and nothing is
computed that the layout does not print.
"""

from __future__ import annotations

import re
from decimal import Decimal

from billx.core.schema import (
    Bill,
    Connection,
    Consumer,
    Demand,
    Discom,
    Energy,
    Gas,
    LineItem,
    MeterRow,
    Period,
    TodSlot,
    Totals,
)

_BILLING_DEMAND = re.compile(r"bill(ing|able) demand", re.IGNORECASE)
_MINIMUM = re.compile(r"^75% of CD$", re.IGNORECASE)


def _d(s: str | None) -> Decimal | None:
    if s is None or s == "":
        return None
    return Decimal(str(s))


def _header_decimal(header: dict | None, pattern: re.Pattern) -> Decimal | None:
    for key, value in (header or {}).items():
        if pattern.search(key):
            m = re.search(r"-?\d+(\.\d+)?", str(value).replace(",", ""))
            return Decimal(m.group(0)) if m else None
    return None


def _meters(tod: dict) -> tuple[MeterRow, ...]:
    rows: list[MeterRow] = []
    for reg, quantity in (("kwh", "kWh"), ("kvah", "kVAh")):
        slots = tod.get(reg) or []
        total = tod.get(f"{reg}_total")
        for r in slots:
            rows.append(_row(quantity, r, r["slot"]))
        if total:
            rows.append(_row(quantity, total, None))
    return tuple(rows)


def _row(quantity: str, r: dict, slot: str | None) -> MeterRow:
    label = f"{quantity} {slot}" if slot else f"{quantity} Total"
    return MeterRow(
        label=label,
        quantity=quantity,  # type: ignore[arg-type]
        tod_slot=slot,
        present=_d(r.get("present")),
        past=_d(r.get("past")),
        difference=_d(r.get("difference")),
        multiplying_factor=_d(r.get("mf")),
        multiplying_factor_printed=str(r["mf"]) if r.get("mf") is not None else None,
        gross_units=_d(r.get("consumption")),
    )


def _lines(charges: list[dict], start: int = 0) -> list[LineItem]:
    out = []
    for i, c in enumerate(charges, start):
        amount = _d(c["amount"])
        assert amount is not None
        out.append(
            LineItem(
                index=i,
                label=str(c["label"]),
                kind="item",
                stage="current",
                quantity=_d(c.get("quantity")),
                rate=_d(c.get("rate")),
                unit=c.get("unit"),
                amount=amount,
                code=c.get("code"),
            )
        )
    return out


def _tod_slots(tod: dict) -> tuple[TodSlot, ...]:
    kwh = {r["slot"]: _d(r["consumption"]) for r in tod.get("kwh") or []}
    kvah = {r["slot"]: _d(r["consumption"]) for r in tod.get("kvah") or []}
    return tuple(TodSlot(slot=s, kwh=kwh.get(s), kvah=kvah.get(s)) for s in kwh)


def _electricity(truth: dict) -> Bill:
    f = truth["fields"]
    tod = truth.get("tod") or {}
    header = truth.get("header") or {}
    facts = truth.get("facts") or {}
    lines = _lines(truth.get("charges") or [])
    arrears = _d(f.get("totals.arrears"))
    if arrears is not None and arrears != 0:
        lines.append(
            LineItem(
                index=len(lines),
                label="Arrears",
                kind="item",
                stage="arrear",
                amount=arrears,
                code="arrears",
            )
        )
    bill_number = (
        facts.get("bill_number", {}).get("value")
        if isinstance(facts.get("bill_number"), dict)
        else None
    )
    return Bill(
        bill_type="electricity",
        discom=Discom(name_as_printed=f.get("utility.name")),
        consumer=Consumer(
            name=f.get("consumer.name"), account_number=f.get("consumer.account_number")
        ),
        connection=Connection(
            tariff_code=f.get("connection.tariff_category"),
            tariff_category=f.get("tariff.category"),
            meter_number=f.get("meter.number"),
            contract_demand_kva=_d(f.get("demand.contract_kva")),
            minimum_billable_kva=_header_decimal(header, _MINIMUM),
        ),
        period=Period(
            bill_month=f.get("period.bill_month"),
            bill_number=bill_number,
            bill_date=f.get("period.bill_date"),
            due_date=f.get("period.due_date"),
            reading_from=f.get("period.from"),
            reading_to=f.get("period.to"),
        ),
        meters=_meters(tod),
        demand=Demand(
            recorded_kva=_d(f.get("demand.max_kva")),
            billing_kva=_header_decimal(header, _BILLING_DEMAND),
        ),
        energy=Energy(
            gross_kwh=_d(f.get("energy.kwh")),
            gross_kvah=_d(f.get("energy.kvah")),
            power_factor=_d(f.get("energy.power_factor")),
            net_metering_import_kwh=_d(f.get("net_metering.import_kwh")),
            net_metering_export_kwh=_d(f.get("net_metering.export_kwh")),
            open_access_re_kwh=_d(f.get("open_access.re_kwh")),
            open_access_non_re_kwh=_d(f.get("open_access.non_re_kwh")),
            open_access_banked_kwh=_d(f.get("open_access.banked_kwh")),
            green_tariff_kwh=_d(f.get("green_tariff.kwh")),
            tod=_tod_slots(tod),
        ),
        line_items=tuple(lines),
        totals=Totals(
            current_charges=_d(f.get("totals.current_charges")),
            arrears_total=arrears,
            net_payable=_d(f.get("totals.net_payable")),
        ),
    )


def _gas(truth: dict) -> Bill:
    f = truth["fields"]
    return Bill(
        bill_type="gas",
        discom=Discom(name_as_printed=f.get("utility.name")),
        consumer=Consumer(name=truth.get("consumer")),
        connection=Connection(meter_number=f.get("meter.number")),
        period=Period(
            bill_number=truth.get("bill_no"),
            reading_from=f.get("period.from"),
            reading_to=f.get("period.to"),
        ),
        gas=Gas(
            customer_id=f.get("consumer.customer_id"),
            volume_scm=_d(f.get("volume.scm")),
            gcv_kcal_per_scm=_d(f.get("gas.gcv_kcal_per_scm")),
            energy_mmbtu=_d(f.get("energy.mmbtu")),
            reading_previous=_d(f.get("readings.previous")),
            reading_current=_d(f.get("readings.current")),
        ),
        line_items=tuple(_lines(truth.get("charges") or [])),
        totals=Totals(net_payable=_d(f.get("totals.amount"))),
    )


def bill_from_truth(truth: dict) -> Bill:
    """The Bill a perfect transcription of this synthetic document would give."""
    kind = truth.get("document_type")
    if kind == "electricity_bill":
        return _electricity(truth)
    if kind == "gas_bill":
        return _gas(truth)
    raise ValueError(f"not an electricity or gas bill truth: {kind}")


__all__ = ["bill_from_truth"]
