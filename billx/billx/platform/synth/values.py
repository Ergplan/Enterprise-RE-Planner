"""Known values for synthetic documents: Decimal throughout, every total built from its parts.

Each generator returns a plain dict holding the values (Decimal, str, None) and, beside each
value, the string the layout prints for it, so the renderer and the truth file cannot drift.
All names, numbers and addresses are invented.
"""

import calendar
import random
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
FIELDS_YAML = Path(__file__).resolve().parents[3] / "config" / "guaranteed_fields.yaml"
CONSUMERS = [
    "Synthetic Test Industries Pvt Ltd",
    "Imaginary Alloys Ltd",
    "Placeholder Textile Mills Ltd",
    "Fictional Cement Works Pvt Ltd",
    "Sample Polymers Pvt Ltd",
    "Dummy Steel Rolling Mills",
]
TOWNS = ["Synthnagar", "Testpur", "Mockabad", "Fakegarh"]
# The synthetic layouts' tariff rates, fixed so their draft profiles (profiles/avvnl and
# profiles/pvvnl, versions avvnl-ht-synth-v1 and pvvnl-hv2-synth-v1) can carry the same
# numbers as `params` and T01 to T05 run end to end. FPPCA stays random: it is notice-based.
AVVNL_RATES = {"energy_charge": Decimal("7.30"), "demand_charge": Decimal("330.00")}  # /kVAh, /kVA
PVVNL_RATES = {"demand_charge": Decimal("300.00"), "energy_charge": Decimal("7.10")}  # /kVA, /kVAh


def field_paths(kind: str) -> list[str]:
    """Scalar guaranteed-field paths (contract 1.0 section 6 plus 6.4) for `electricity` or
    `gas`; the arrays (readings[], energy.tod[], charges.by_code[]) are in the truth file's
    `tod` and `charges` instead."""
    return list(field_types(kind))


def field_types(kind: str) -> dict[str, str]:
    """Scalar guaranteed-field path -> its type (number, date, month, identifier, text)."""
    fields = yaml.safe_load(FIELDS_YAML.read_text())[kind]
    return {f["path"]: f["type"] for f in fields if f["type"] != "array"}


def money(d: Decimal) -> Decimal:
    return d.quantize(CENT, ROUND_HALF_UP)


def plain(d: Decimal) -> str:
    """The number exactly as held, no grouping: 26949346.81."""
    return f"{d:f}"


def western(d: Decimal) -> str:
    return f"{d:,f}"


def indian(d: Decimal) -> str:
    """Indian digit grouping: 2,69,49,346.81."""
    sign = "-" if d < 0 else ""
    whole, dot, frac = f"{abs(d):f}".partition(".")
    if len(whole) > 3:
        head, groups = whole[:-3], [whole[-3:]]
        while head:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join(groups)
    return sign + whole + dot + frac


def dmy(d: date, sep: str = "-") -> str:
    return d.strftime(f"%d{sep}%m{sep}%Y")


def dmon(d: date) -> str:
    return f"{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}"


def month_name_year(d: date) -> str:
    """The AVVNL layout's bill month: MAR-2025."""
    return f"{MONTHS[d.month - 1]}-{d.year}"


def month_slash_year(d: date) -> str:
    """The PVVNL layout's bill month: 03/2025."""
    return f"{d.month:02d}/{d.year}"


def rnd(rng: random.Random, lo, hi, places: int = 0) -> Decimal:
    """A uniform Decimal in [lo, hi] with exactly `places` decimals."""
    scale = 10**places
    return Decimal(rng.randint(int(Decimal(lo) * scale), int(Decimal(hi) * scale))).scaleb(-places)


def digits(rng: random.Random, n: int) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(n))


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def month_period(rng: random.Random) -> tuple[date, date]:
    """A whole calendar month between Jan 2025 and Aug 2026."""
    first = add_months(date(2025, 1, 1), rng.randint(0, 19))
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def line(label, code, unit, qty, rate, fq=plain, fr=plain, fa=plain) -> dict:
    """One printed charge line; amount = quantity x rate rounded half-up to paise."""
    amount = money(qty * rate)
    return {
        "label": label,
        "code": code,
        "unit": unit,
        "quantity": qty,
        "rate": rate,
        "amount": amount,
        "printed": {"quantity": fq(qty), "rate": fr(rate), "amount": fa(amount)},
    }


def flat_line(label, code, amount, fa=plain) -> dict:
    """A printed line with an amount only (a tax at a percentage, an adjustment)."""
    return {
        "label": label,
        "code": code,
        "unit": None,
        "quantity": None,
        "rate": None,
        "amount": amount,
        "printed": {"quantity": None, "rate": None, "amount": fa(amount)},
    }


def total(lines: list[dict]) -> Decimal:
    return sum((x["amount"] for x in lines), ZERO)


def _row(slot, past, diff, mf, fc) -> dict:
    row = {
        "slot": slot,
        "present": past + diff,
        "past": past,
        "difference": diff,
        "mf": mf,
        "consumption": diff * mf,
    }
    row["printed"] = {
        k: (fc if k == "consumption" else plain)(v) for k, v in row.items() if k != "slot"
    }
    return row


def registers(rng, slots, mf, lo, hi, fc) -> dict:
    """kWh and kVAh registers by TOD slot plus the total register; slot kVAh >= slot kWh."""
    out = {"kwh": [], "kvah": []}
    for name in slots:
        d_kwh = rnd(rng, lo, hi, 2)
        d_kvah = (d_kwh / rnd(rng, "0.900", "0.995", 3)).quantize(CENT, ROUND_CEILING)
        out["kwh"].append(_row(name, rnd(rng, 1000, 60000, 2), d_kwh, mf, fc))
        out["kvah"].append(_row(name, rnd(rng, 1000, 60000, 2), d_kvah, mf, fc))
    for reg in ("kwh", "kvah"):
        diff = sum((r["difference"] for r in out[reg]), ZERO)
        out[f"{reg}_total"] = _row("Total", rnd(rng, 100000, 900000, 2), diff, mf, fc)
    return out


def _consumption(tod, reg, slots) -> Decimal:
    return sum((r["consumption"] for r in tod[reg] if r["slot"] in slots), ZERO)


def _demand(rng, kwh):
    """Contract demand sized to the energy, recorded MD 60-105% of it, billing at 75% floor."""
    cd = max(Decimal(500), (kwh / Decimal(396) / 50).to_integral_value() * 50)
    md = (cd * rnd(rng, "0.60", "1.05", 2)).quantize(CENT)
    cd75 = (cd * Decimal("0.75")).quantize(CENT)
    return cd, md, cd75, max(md, cd75)


def _electricity(
    layout: str, rng, n: int, given: dict, tod: dict, lines: list, fmt: dict, facts: dict
) -> dict:
    """Totals and energy from their parts; `given` holds the printed identifiers, dates, demand
    on the contract's paths; `facts` holds printed items that are not guaranteed fields
    (the bill number), each as {name: (value, printed)}.

    `fmt` maps a field path to the function that prints it on this layout (default str).
    """
    current = total(lines)
    arrears = rnd(rng, 10000, 900000, 2) if n % 2 else ZERO
    by_code = {x["code"]: x["amount"] for x in lines}
    computed = {
        "energy.kwh": tod["kwh_total"]["consumption"],
        "energy.kvah": tod["kvah_total"]["consumption"],
        "charges.energy": by_code.get("energy_charge"),
        "charges.demand": by_code.get("demand_charge"),
        "totals.net_payable": current + arrears,
        "totals.current_charges": current,
        "totals.arrears": arrears,
    }
    values = {path: {**given, **computed}.get(path) for path in field_paths("electricity")}
    assert set(given) | set(computed) <= set(values), "synth out of step with the field list"
    fields, printed = {}, {}
    for path, v in values.items():
        if isinstance(v, date):
            fields[path] = v.isoformat()[:7] if path == "period.bill_month" else v.isoformat()
        else:
            fields[path] = v
        if v is not None:
            printed[path] = fmt[path](v) if path in fmt else str(v)
    return {
        "document_type": "electricity_bill",
        "layout": layout,
        "fields": fields,
        "printed": printed,
        "values": values,
        "tod": tod,
        "charges": lines,
        "facts": _facts(**facts),
    }


def avvnl(rng: random.Random, n: int) -> dict:
    """AVVNL-style HT large-industrial bill: calendar-month period, bill month the same month."""
    start, end = month_period(rng)
    issue = end + timedelta(days=rng.randint(3, 8))
    due = issue + timedelta(days=15)
    mf = Decimal(rng.choice([500, 1000, 2000]))
    slots = ["Normal", "Morning Peak", "Evening Peak", "Off Peak"]
    tod = registers(rng, slots, mf, Decimal(150000) / mf, Decimal(700000) / mf, indian)
    kvah = tod["kvah_total"]["consumption"]
    cd, md, cd75, billing = _demand(rng, tod["kwh_total"]["consumption"])
    peak = _consumption(tod, "kvah", {"Morning Peak", "Evening Peak"})
    off = _consumption(tod, "kvah", {"Off Peak"})
    f = {"fq": indian, "fr": plain, "fa": indian}
    lines = [
        line("Energy Charges", "energy_charge", "kVAh", kvah, AVVNL_RATES["energy_charge"], **f),
        line(
            "Fixed Charges (on Billing Demand)",
            "demand_charge",
            "kVA",
            billing,
            AVVNL_RATES["demand_charge"],
            **f,
        ),
        line("TOD Surcharge (Peak Hours)", "tod_surcharge", "kVAh", peak, Decimal("0.73"), **f),
        line("TOD Rebate (Off Peak Hours)", "tod_rebate", "kVAh", off, Decimal("-0.73"), **f),
        line("Fuel Surcharge", "fppca", "kVAh", kvah, rnd(rng, "0.20", "0.70", 2), **f),
        line("Electricity Duty", "electricity_duty", "kVAh", kvah, Decimal("0.40"), **f),
        line("Water Conservation Cess", "cess", "kVAh", kvah, Decimal("0.10"), **f),
        line("Urban Cess", "cess", "kVAh", kvah, Decimal("0.15"), **f),
        line("Meter Rent", "meter_rent", "month", Decimal(1), Decimal("1500.00"), **f),
    ]
    category = rng.choice(["HT-5", "HT-4"])
    given = {
        "utility.name": "AVVNL",
        "consumer.account_number": "99" + digits(rng, 10),
        "period.from": start,
        "period.to": end,
        "period.bill_date": issue,
        "period.bill_month": start,
        "demand.max_kva": md,
        "demand.contract_kva": cd,
        "consumer.name": rng.choice(CONSUMERS),
        "period.due_date": due,
        "connection.tariff_category": category,
        "tariff.category": category,
    }
    fmt = {
        "period.from": dmy,
        "period.to": dmy,
        "period.bill_date": dmy,
        "period.due_date": dmy,
        "period.bill_month": month_name_year,
        "energy.kwh": indian,
        "energy.kvah": indian,
        "demand.max_kva": plain,
        "demand.contract_kva": plain,
        "charges.energy": indian,
        "charges.demand": indian,
        "totals.net_payable": indian,
        "totals.current_charges": indian,
        "totals.arrears": indian,
    }
    bill_number = "SYN" + digits(rng, 9)
    facts = {"bill_number": (bill_number, bill_number)}
    bill = _electricity("avvnl-ht-synth-v1", rng, n, given, tod, lines, fmt, facts)
    town = rng.choice(TOWNS)
    bill["header"] = {
        "A/c No": "SYN/" + digits(rng, 4) + "/" + digits(rng, 3),
        "Area Code": "A" + digits(rng, 3),
        "Feeder Code": "FDR-SYN-" + digits(rng, 2),
        "Voltage of Supply": rng.choice(["11 KV", "33 KV", "132 KV"]),
        "Metering side": "HT",
        "Sanction Load": plain(cd * Decimal("0.9")) + " KW",
        "75% of CD": plain(cd75),
        "Billing Demand (KVA)": plain(billing),
        "Address": f"Plot {rng.randint(1, 99)}, Synthetic Industrial Area, {town} - "
        f"999{digits(rng, 3)}",
        "GSTIN": "08SYNTH" + digits(rng, 4) + "T1ZX",
    }
    return bill


def pvvnl(rng: random.Random, n: int) -> dict:
    """PVVNL-style HV-2 'bill cum notice': calendar-month period, bill month the next month."""
    start, end = month_period(rng)
    bill_date = end + timedelta(days=rng.randint(2, 6))
    due = bill_date + timedelta(days=15)
    ct, pt = rng.choice([(100, 5), (200, 5), (300, 5)]), rng.choice([(11000, 110), (33000, 110)])
    mf = Decimal(ct[0] // ct[1] * (pt[0] // pt[1]))
    slots = ["TOD-1", "TOD-2", "TOD-3"]
    tod = registers(rng, slots, mf, Decimal(200000) / mf, Decimal(900000) / mf, plain)
    kvah = tod["kvah_total"]["consumption"]
    cd, md, cd75, billing = _demand(rng, tod["kwh_total"]["consumption"])
    lines = [
        line("Demand Charge", "demand_charge", "kVA", billing, PVVNL_RATES["demand_charge"]),
        line("Energy Charge", "energy_charge", "kVAh", kvah, PVVNL_RATES["energy_charge"]),
        line(
            "TOD Surcharge (TOD-3)",
            "tod_surcharge",
            "kVAh",
            _consumption(tod, "kvah", {"TOD-3"}),
            Decimal("1.10"),
        ),
        line(
            "TOD Rebate (TOD-1)",
            "tod_rebate",
            "kVAh",
            _consumption(tod, "kvah", {"TOD-1"}),
            Decimal("-0.55"),
        ),
        line("FPPCA", "fppca", "kVAh", kvah, rnd(rng, "0.05", "0.40", 2)),
        line("Electricity Duty", "electricity_duty", "kVAh", kvah, Decimal("0.50")),
    ]
    given = {
        "utility.name": "PVVNL",
        "consumer.account_number": "99" + digits(rng, 8),
        "meter.number": "SYNM" + digits(rng, 7),
        "period.from": start,
        "period.to": end,
        "period.bill_date": bill_date,
        "period.bill_month": add_months(start, 1),
        "demand.max_kva": md,
        "demand.contract_kva": cd,
        "consumer.name": rng.choice(CONSUMERS),
        "period.due_date": due,
        "connection.tariff_category": "HV-2",
        "tariff.category": "HV-2",
    }
    fmt = {
        "period.from": dmon,
        "period.to": dmon,
        "period.bill_date": dmon,
        "period.due_date": dmon,
        "period.bill_month": month_slash_year,
        "energy.kwh": plain,
        "energy.kvah": plain,
        "demand.max_kva": plain,
        "demand.contract_kva": plain,
        "charges.energy": plain,
        "charges.demand": plain,
        "totals.net_payable": indian,
        "totals.current_charges": plain,
        "totals.arrears": plain,
    }
    bill_number = "SB" + digits(rng, 10)
    facts = {"bill_number": (bill_number, bill_number)}
    bill = _electricity("pvvnl-hv2-synth-v1", rng, n, given, tod, lines, fmt, facts)
    bill["header"] = {
        "Discont-Dt": dmon(due + timedelta(days=15)),
        "CT Ratio": f"{ct[0]}/{ct[1]}",
        "PT Ratio": f"{pt[0]}/{pt[1]}",
        "Sup. Volt (KV)": "11" if pt[0] == 11000 else "33",
        "Billable Demand (KVA) (75%)": plain(billing),
        "Division": f"Synthetic Test Division, {rng.choice(TOWNS)}",
        "Address": f"Khasra {rng.randint(1, 999)}, Mock Industrial Estate, {rng.choice(TOWNS)}",
    }
    return bill


def _doc(document_type, layout, fields=None, printed=None, charges=None, facts=None, **extra):
    return {
        "document_type": document_type,
        "layout": layout,
        "fields": fields or {},
        "printed": printed or {},
        "charges": charges or [],
        "facts": facts or {},
        **extra,
    }


def _facts(**kv) -> dict:
    """Printed facts outside the guaranteed-field list: {name: {value, printed}}."""
    return {k: {"value": v, "printed": p} for k, (v, p) in kv.items()}


def gas(rng: random.Random, style: str) -> dict:
    """Gas bill: SCM from readings, MMBtu = SCM x GCV / 252000 (3 dp), lines sum to the total.

    style "a" bills per SCM (city-gas layout); style "b" bills per MMBtu (gas-sales invoice).
    """
    start, end = month_period(rng)
    prev = rnd(rng, 10000, 900000, 2)
    scm = rnd(rng, 20000, 300000, 2)
    gcv = rnd(rng, 8400, 9800, 0)
    mmbtu = (scm * gcv / Decimal(252000)).quantize(Decimal("0.001"), ROUND_HALF_UP)
    if style == "a":
        utility, layout = "Synthetic City Gas Ltd", "gas-citygas-synth-v1"
        cust = "SYNCG" + digits(rng, 8)
        base = [
            line(
                "Gas Charges",
                "gas_charge",
                "SCM",
                scm,
                rnd(rng, "45.00", "62.00", 2),
                indian,
                plain,
                indian,
            ),
            line(
                "Transportation Charges",
                "transport",
                "SCM",
                scm,
                Decimal("1.25"),
                indian,
                plain,
                indian,
            ),
        ]
        vat = money(total(base) * Decimal("0.05"))
        charges = base + [flat_line("VAT @ 5%", "vat", vat, indian)]
        fmt_n, fmt_d = indian, dmy
    else:
        utility, layout = "Imaginary Gas Grid Corporation", "gas-gridsales-synth-v1"
        cust = "IGG/" + digits(rng, 6)
        base = [
            line("Gas Price", "gas_charge", "MMBtu", mmbtu, rnd(rng, "900.00", "1150.00", 2)),
            line("Pipeline Tariff", "transport", "MMBtu", mmbtu, Decimal("60.00")),
        ]
        vat = money(total(base) * Decimal("0.15"))
        charges = base + [flat_line("VAT @ 15%", "vat", vat)]
        fmt_n, fmt_d = plain, dmon
    amount = total(charges)
    given = {
        "utility.name": utility,
        "consumer.customer_id": cust,
        "meter.number": None,
        "period.from": start,
        "period.to": end,
        "readings.previous": prev,
        "readings.current": prev + scm,
        "volume.scm": scm,
        "gas.gcv_kcal_per_scm": gcv,
        "energy.mmbtu": mmbtu,
        "totals.amount": amount,
    }
    values = {path: given.get(path) for path in field_paths("gas")}
    assert set(given) == set(values), "synth out of step with the gas field list"
    fields = {k: v.isoformat() if isinstance(v, date) else v for k, v in values.items()}
    fmt = {
        "period.from": fmt_d,
        "period.to": fmt_d,
        "readings.previous": plain,
        "readings.current": plain,
        "volume.scm": fmt_n,
        "gas.gcv_kcal_per_scm": plain,
        "energy.mmbtu": plain,
        "totals.amount": fmt_n,
    }
    printed = {k: fmt[k](v) if k in fmt else str(v) for k, v in values.items() if v is not None}
    if style == "a":
        printed["utility.name"] = utility.upper()  # the city-gas header is in capitals
    readings = {"previous": prev, "present": prev + scm}
    return _doc(
        "gas_bill",
        layout,
        fields,
        printed,
        charges,
        values=values,
        readings=readings,
        bill_no=f"G{digits(rng, 9)}",
        consumer=rng.choice(CONSUMERS),
    )


def water(rng: random.Random) -> dict:
    start, end = month_period(rng)
    prev = rnd(rng, 1000, 50000, 0)
    kl = rnd(rng, 200, 5000, 0)
    charges = [
        line("Water Charges", "water_charge", "kL", kl, Decimal("32.50")),
        line("Sewerage Charges", "sewerage", "kL", kl, Decimal("9.75")),
        line("Meter Rent", "meter_rent", "month", Decimal(1), Decimal("150.00")),
    ]
    amount = total(charges)
    return _doc(
        "water_bill",
        "water-municipal-synth-v1",
        charges=charges,
        facts=_facts(
            supplier=("Synthetic Municipal Water Board",) * 2,
            consumption_kl=(kl, plain(kl)),
            amount=(amount, plain(amount)),
            period_start=(start.isoformat(), dmy(start)),
            period_end=(end.isoformat(), dmy(end)),
        ),
        readings={"previous": prev, "present": prev + kl},
        consumer=rng.choice(CONSUMERS),
        account="WB-" + digits(rng, 8),
    )


def telecom(rng: random.Random) -> dict:
    start, end = month_period(rng)
    base = [
        line(
            "Monthly Rental - Business Plan 999", "rental", "month", Decimal(1), Decimal("999.00")
        ),
        line("Data Add-on 50 GB", "data", "pack", Decimal(rng.randint(1, 4)), Decimal("199.00")),
        line("Leased Line Port", "port", "port", Decimal(rng.randint(1, 3)), Decimal("2500.00")),
    ]
    tax = money(total(base) * Decimal("0.09"))
    charges = base + [flat_line("CGST @ 9%", "cgst", tax), flat_line("SGST @ 9%", "sgst", tax)]
    amount = total(charges)
    return _doc(
        "telecom_bill",
        "telecom-fictional-synth-v1",
        charges=charges,
        facts=_facts(
            supplier=("Fictional Telecom Ltd",) * 2,
            amount=(amount, western(amount)),
            period_start=(start.isoformat(), dmy(start, "/")),
            period_end=(end.isoformat(), dmy(end, "/")),
        ),
        consumer=rng.choice(CONSUMERS),
        account="FT" + digits(rng, 10),
    )


def receipt(rng: random.Random) -> dict:
    items = [
        ("A4 Paper Ream", "320.00"),
        ("Ball Pens (box)", "150.00"),
        ("Stapler", "275.50"),
        ("Box File", "95.00"),
        ("Whiteboard Marker", "45.00"),
    ]
    charges = [
        line(name, "item", "nos", Decimal(rng.randint(1, 6)), Decimal(rate))
        for name, rate in rng.sample(items, 3)
    ]
    amount = total(charges)
    day = date(2026, 1, 1) + timedelta(days=rng.randint(0, 240))
    return _doc(
        "not_a_bill",
        "receipt-store-synth-v1",
        charges=charges,
        facts=_facts(
            supplier=("Synthetic Stationery Mart",) * 2,
            amount=(amount, plain(amount)),
            date=(day.isoformat(), dmy(day, "/")),
        ),
        receipt_no="R-" + digits(rng, 6),
    )


def invoice(rng: random.Random) -> dict:
    base = [
        line("Office Chair", "item", "nos", Decimal(rng.randint(2, 10)), Decimal("4250.00")),
        line("Filing Cabinet", "item", "nos", Decimal(rng.randint(1, 4)), Decimal("8900.00")),
    ]
    gst = money(total(base) * Decimal("0.18"))
    charges = base + [flat_line("IGST @ 18%", "igst", gst)]
    amount = total(charges)
    day = date(2026, 1, 1) + timedelta(days=rng.randint(0, 240))
    return _doc(
        "other_invoice",
        "invoice-supplies-synth-v1",
        charges=charges,
        facts=_facts(
            supplier=("Placeholder Office Supplies Pvt Ltd",) * 2,
            amount=(amount, indian(amount)),
            date=(day.isoformat(), dmy(day)),
        ),
        invoice_no="INV/" + digits(rng, 5),
        consumer=rng.choice(CONSUMERS),
    )


def letter(rng: random.Random) -> dict:
    day = date(2026, 1, 1) + timedelta(days=rng.randint(0, 240))
    sender = rng.choice(CONSUMERS)
    return _doc(
        "not_a_bill",
        "letter-synth-v1",
        facts=_facts(sender=(sender, sender), date=(day.isoformat(), dmon(day))),
        town=rng.choice(TOWNS),
    )
