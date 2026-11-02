"""Digital PDFs for the non-electricity documents the document-type gate must recognise."""

from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from billx.platform.synth.electricity import GRID, STYLES, footer
from billx.platform.synth.values import plain


def _kv(pairs: list[tuple[str, str]], cols: int) -> Table:
    rows = [sum((list(p) for p in pairs[i : i + cols]), []) for i in range(0, len(pairs), cols)]
    rows[-1] += ["", ""] * (cols - len(rows[-1]) // 2)
    t = Table(rows)
    t.setStyle(TableStyle(GRID[1:] + [("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold")]))
    return t


def _charges(
    doc: dict, total_label: str, total_printed: str, unit_col: str = "Unit", width: float = 180 * mm
) -> Table:
    rows = [["Particulars", unit_col, "Quantity", "Rate", "Amount"]]
    for x in doc["charges"]:
        q = x["printed"]
        rows.append(
            [x["label"], x["unit"] or "", q["quantity"] or "", q["rate"] or "", q["amount"]]
        )
    rows.append([total_label, "", "", "", total_printed])
    t = Table(rows, colWidths=[width * f for f in (0.38, 0.11, 0.17, 0.14, 0.20)])
    t.setStyle(
        TableStyle(
            GRID
            + [
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ]
        )
    )
    return t


def _build(path, story, title, pagesize=A4) -> None:
    doc = SimpleDocTemplate(
        str(path),
        pagesize=pagesize,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        invariant=1,
        title=title,
        author="billx synth",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def _p(text: str, style: str = "Normal") -> Paragraph:
    return Paragraph(text, STYLES[style])


def gas_pdf(doc: dict, path) -> None:
    v, p = doc["values"], doc["printed"]
    if doc["layout"].startswith("gas-citygas"):
        story = [
            _p(f"<b>{p['utility.name']}</b>", "Title"),
            _p("Piped Natural Gas - Industrial Gas Bill"),
            Spacer(1, 4 * mm),
            _kv(
                [
                    ("Customer ID", p["consumer.customer_id"]),
                    ("Bill No", doc["bill_no"]),
                    ("Customer Name", doc["consumer"]),
                    ("Billing Period", f"{p['period.from']} to {p['period.to']}"),
                    ("Previous Reading (SCM)", p["readings.previous"]),
                    ("Present Reading (SCM)", p["readings.current"]),
                    ("Gas Consumed (SCM)", p["volume.scm"]),
                    ("GCV (kcal/SCM)", p["gas.gcv_kcal_per_scm"]),
                    ("Energy (MMBtu)", p["energy.mmbtu"]),
                ],
                2,
            ),
            Spacer(1, 4 * mm),
            _charges(doc, "Total Amount Payable (Rs.)", p["totals.amount"]),
        ]
    else:
        story = [
            _p(f"<b>{v['utility.name']}</b>", "Title"),
            _p("<b>GAS SALES INVOICE</b>", "Heading3"),
            _kv(
                [
                    ("Customer Code", p["consumer.customer_id"]),
                    ("Invoice No", doc["bill_no"]),
                    ("Buyer", doc["consumer"]),
                    ("Supply From", p["period.from"]),
                    ("Supply To", p["period.to"]),
                    ("Quantity (SCM)", p["volume.scm"]),
                    ("Avg GCV (kcal/SCM)", p["gas.gcv_kcal_per_scm"]),
                    ("Quantity (MMBtu)", p["energy.mmbtu"]),
                    ("Meter Index", f"{p['readings.previous']} / {p['readings.current']}"),
                ],
                3,
            ),
            Spacer(1, 4 * mm),
            _charges(doc, "Invoice Total (INR)", p["totals.amount"]),
            Spacer(1, 3 * mm),
            _p("Energy (MMBtu) = SCM x GCV / 252000. Payment within 10 days of invoice."),
        ]
    _build(path, story, "Synthetic gas bill")


def water_pdf(doc: dict, path) -> None:
    f, r = doc["facts"], doc["readings"]
    story = [
        _p(f"<b>{f['supplier']['printed']}</b>", "Title"),
        _p("Water and Sewerage Bill"),
        Spacer(1, 4 * mm),
        _kv(
            [
                ("Consumer No", doc["account"]),
                ("Name", doc["consumer"]),
                ("From", f["period_start"]["printed"]),
                ("To", f["period_end"]["printed"]),
                ("Previous Reading (kL)", plain(r["previous"])),
                ("Present Reading (kL)", plain(r["present"])),
                ("Consumption (kL)", f["consumption_kl"]["printed"]),
            ],
            2,
        ),
        Spacer(1, 4 * mm),
        _charges(doc, "Amount Payable (Rs.)", f["amount"]["printed"]),
    ]
    _build(path, story, "Synthetic water bill")


def telecom_pdf(doc: dict, path) -> None:
    f = doc["facts"]
    story = [
        _p(f"<b>{f['supplier']['printed']}</b>", "Title"),
        _p("Postpaid Business Services - Monthly Statement"),
        Spacer(1, 4 * mm),
        _kv(
            [
                ("Account No", doc["account"]),
                ("Customer", doc["consumer"]),
                ("Bill Period", f"{f['period_start']['printed']} - {f['period_end']['printed']}"),
                ("Plan", "Business Plan 999"),
            ],
            2,
        ),
        Spacer(1, 4 * mm),
        _charges(doc, "Total Due (Rs.)", f["amount"]["printed"], unit_col="Per"),
    ]
    _build(path, story, "Synthetic telecom bill")


def receipt_pdf(doc: dict, path) -> None:
    f = doc["facts"]
    story = [
        _p(f"<b>{f['supplier']['printed']}</b>", "Heading2"),
        _p(f"PAYMENT RECEIPT &nbsp; No. {doc['receipt_no']} &nbsp; Date: {f['date']['printed']}"),
        Spacer(1, 3 * mm),
        _charges(doc, "Total Paid (Cash)", f["amount"]["printed"], unit_col="Per", width=118 * mm),
        Spacer(1, 3 * mm),
        _p("Received with thanks. Goods once sold will not be taken back."),
    ]
    _build(path, story, "Synthetic receipt", pagesize=A5)


def invoice_pdf(doc: dict, path) -> None:
    f = doc["facts"]
    story = [
        _p(f"<b>{f['supplier']['printed']}</b>", "Title"),
        _p("<b>TAX INVOICE</b>", "Heading3"),
        _kv(
            [
                ("Invoice No", doc["invoice_no"]),
                ("Date", f["date"]["printed"]),
                ("Bill To", doc["consumer"]),
            ],
            2,
        ),
        Spacer(1, 4 * mm),
        _charges(doc, "Invoice Total (Rs.)", f["amount"]["printed"]),
    ]
    _build(path, story, "Synthetic tax invoice")


def letter_pdf(doc: dict, path) -> None:
    f = doc["facts"]
    sender = f["sender"]["printed"]
    body = [
        f"<b>{sender}</b><br/>Plot 7, Synthetic Industrial Area, {doc['town']}",
        f"Date: {f['date']['printed']}",
        "To<br/>The Manager<br/>Imaginary Cooperative Bank, Main Branch",
        "<b>Subject: Request to update our correspondence address</b>",
        "Dear Sir or Madam,",
        "We request you to update the correspondence address on our current account to the "
        "address given above with effect from next month. A copy of the board resolution is "
        "enclosed for your records.",
        "Kindly acknowledge receipt of this letter.",
        f"Yours faithfully,<br/>for {sender}<br/><br/>Authorised Signatory",
    ]
    story = []
    for b in body:
        story += [_p(b), Spacer(1, 4 * mm)]
    _build(path, story, "Synthetic letter")
