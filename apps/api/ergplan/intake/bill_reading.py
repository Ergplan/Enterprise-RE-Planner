"""The reading view of one bill: every value billx read, where it is printed (page and box), which
readers read what, the bill's own checks, and the values RE planning takes from it.

Invariant 7: billx read the bill; this module only arranges billx's stored result for display and
for the hand-off to planning. Nothing here reads a PDF. Each figure carries a `bill` source_ref to
the bill page it was read from (invariant 1).
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.sourced import RefKind, SourcedValue, SourceRef, derive
from ..core.units import Unit
from ..db.models import Bill
from . import bills as bill_store
from . import defaults
from .recognise import Recognition, discom_of, recognise

LABELS: dict[str, str] = {
    "utility.name": "DISCOM",
    "consumer.name": "Consumer name",
    "consumer.account_number": "Account number",
    "meter.number": "Meter number",
    "connection.tariff_category": "Tariff category (connection)",
    "tariff.category": "Tariff category",
    "period.bill_month": "Bill month",
    "period.bill_date": "Bill date",
    "period.due_date": "Due date",
    "period.from": "Period from",
    "period.to": "Period to",
    "energy.kwh": "Energy (kWh)",
    "energy.kvah": "Energy (kVAh)",
    "energy.billed_units": "Billed units",
    "energy.power_factor": "Power factor",
    "demand.max_kva": "Recorded maximum demand",
    "demand.contract_kva": "Contract demand",
    "charges.energy": "Energy charges",
    "charges.demand": "Demand charges",
    "open_access.re_kwh": "Open access (RE)",
    "open_access.non_re_kwh": "Open access (other)",
    "open_access.banked_kwh": "Banked energy drawn",
    "green_tariff.kwh": "Green tariff units",
    "net_metering.import_kwh": "Net metering import",
    "net_metering.export_kwh": "Net metering export",
    "totals.current_charges": "Current charges",
    "totals.arrears": "Arrears",
    "totals.due_date_rebate": "Due-date rebate",
    "totals.net_payable": "Net payable",
}
ORDER = list(LABELS)

READER_NAMES = {
    "text_layer": "PDF text",
    "local_ocr": "Local OCR",
    "docling": "Docling",
    "model_a": "Model A",
    "model_b": "Model B",
    "llamaparse": "LlamaParse",
    "human": "You",
}


class Box(BaseModel):
    """Fractions of the page from the top left (strings, as billx returns them)."""

    x: str
    y: str
    w: str
    h: str


class ReaderReading(BaseModel):
    reader: str
    reader_name: str
    printed: str | None
    value: str | None
    page: int | None
    box: Box | None


class ReadValue(BaseModel):
    """One value as billx read it, where it is printed and who read it."""

    path: str
    label: str
    value: str | None
    unit: str | None
    printed: str | None
    page: int | None
    box: Box | None
    verification: str | None
    readers: list[str]
    readings: list[ReaderReading]
    source_ref: SourceRef | None
    needs_confirmation: bool = False
    confirmed: bool = False
    confirmable: bool = False  # the client may confirm or correct it (POST /bills/{id}/confirm)


class TodRow(BaseModel):
    slot: str
    start: str | None  # "05:00"
    end: str | None
    unit: str
    consumption: ReadValue | None
    open_access: ReadValue | None
    net: ReadValue | None


class ChargeRow(BaseModel):
    label: str
    code: str | None
    group: str | None
    kind: str | None
    stage: str | None
    tod_slot: str | None
    quantity: str | None
    rate: str | None
    amount: ReadValue
    recheck: str | None  # match | differs | not_computable


class CheckRow(BaseModel):
    id: str
    description: str | None
    status: str
    expected: str | None
    actual: str | None


class BillReading(BaseModel):
    bill_id: str
    filename: str | None
    file_url: str
    pages: list[int]
    page_url: str  # with {page} for the 1-based page number
    status: str
    accepted: bool
    discom: str | None
    profile_status: str | None
    readers_used: list[str]
    fields: list[ReadValue]
    tod: list[TodRow]
    charges: list[ChargeRow]
    checks: list[CheckRow]
    review_reasons: list[str]
    outstanding: list[str]
    cost_usd: str | None = Field(default=None, description="what billx spent on model readers")


# ---------------------------------------------------------------- slot hours

_HOURS = re.compile(
    r"(\d{1,2})(?:[:.](\d{2}))?\s*(?:hrs?|h)?\s*(?:-|–|to)\s*(\d{1,2})(?:[:.](\d{2}))?",
    re.IGNORECASE,
)


def slot_label(slot: str) -> str:
    """A slot's label for display: 'Tod-1(05 To 11)' (billx's key, title-cased) → 'TOD-1 (05 to 11)'."""
    s = re.sub(r"^\s*tod\b", "TOD", slot.strip(), flags=re.IGNORECASE)
    s = re.sub(r"\s*\(\s*", " (", s)
    s = re.sub(r"\b[Tt][Oo]\b", "to", s)
    return re.sub(r"\s+", " ", s).strip()


def slot_hours(slot: str | None) -> tuple[str, str] | None:
    """The hours a ToD slot's label prints: 'TOD-1 (05 to 11)', 'Peak 17:00-23:00', '05.00 to 10.00
    hrs' → ('05:00', '11:00'). None when the label prints no hours."""
    if not slot:
        return None
    for m in _HOURS.finditer(slot):
        h1, m1, h2, m2 = int(m.group(1)), m.group(2) or "00", int(m.group(3)), m.group(4) or "00"
        if h1 > 24 or h2 > 24 or int(m1) > 59 or int(m2) > 59:
            continue
        if m.group(2) is None and m.group(4) is None and not re.search(r"\(|to|-", m.group(0), re.I):
            continue
        a = f"{h1 % 24:02d}:{m1}"
        b = f"{h2 % 24:02d}:{m2}"
        if a != b:
            return a, b
    return None


# ---------------------------------------------------------------- building


def _box(region: Any) -> Box | None:
    if not isinstance(region, dict):
        return None
    try:
        return Box(**{k: str(region[k]) for k in ("x", "y", "w", "h")})
    except KeyError:
        return None


def _bill_dict(bill: Bill) -> dict[str, Any]:
    for b in (bill.billx_result or {}).get("bills", []):
        if int(b.get("index", 0)) == bill.bill_index:
            return dict(b)
    raise bill_store.BillNotFound(f"bill index {bill.bill_index} not in the stored billx result")


def read_value(bill: Bill, path: str, node: Any, label: str | None = None) -> ReadValue | None:
    """A billx field object as a ReadValue, or None when the node is not a field object."""
    if not isinstance(node, dict) or "value" not in node:
        return None
    value = node.get("value")
    page = node.get("page") if isinstance(node.get("page"), int) else None
    readings = []
    for r in node.get("readings") or []:
        if not isinstance(r, dict):
            continue
        reader = str(r.get("reader") or "")
        readings.append(
            ReaderReading(
                reader=reader,
                reader_name=READER_NAMES.get(reader, reader),
                printed=None if r.get("printed") is None else str(r.get("printed")),
                value=None if r.get("value") is None else str(r.get("value")),
                page=r.get("page") if isinstance(r.get("page"), int) else None,
                box=_box(r.get("region")),
            )
        )
    ref = (
        SourceRef(kind=RefKind.BILL, bill_id=bill.id, field_path=path, page=page)
        if value is not None
        else None
    )
    return ReadValue(
        path=path,
        label=label or LABELS.get(path, path),
        value=None if value is None else str(value),
        unit=node.get("unit"),
        printed=node.get("printed"),
        page=page,
        box=_box(node.get("region")),
        verification=node.get("verification"),
        readers=[str(x) for x in node.get("readers") or []],
        readings=readings,
        source_ref=ref,
    )


def _walk(tree: Any, path: str) -> Any:
    node = tree
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _tod(bill: Bill, fields: dict[str, Any]) -> list[TodRow]:
    rows = []
    for i, item in enumerate(_walk(fields, "energy.tod") or []):
        if not isinstance(item, dict):
            continue
        slot_node = item.get("slot")
        slot = slot_label(str(slot_node.get("value") if isinstance(slot_node, dict) else slot_node or ""))
        kwh = read_value(bill, f"energy.tod.{i}.kwh", item.get("kwh"), f"{slot} · kWh")
        kvah = read_value(bill, f"energy.tod.{i}.kvah", item.get("kvah"), f"{slot} · kVAh")
        consumption = kwh if kwh is not None and kwh.value is not None else kvah
        unit = "kWh" if consumption is kwh and kwh is not None and kwh.value is not None else "kVAh"
        hours = slot_hours(slot)
        rows.append(
            TodRow(
                slot=slot,
                start=hours[0] if hours else None,
                end=hours[1] if hours else None,
                unit=unit,
                consumption=consumption,
                open_access=read_value(
                    bill, f"energy.tod.{i}.open_access", item.get("open_access"), f"{slot} · open access"
                ),
                net=read_value(bill, f"energy.tod.{i}.net", item.get("net"), f"{slot} · billed"),
            )
        )
    return rows


def _charges(bill: Bill, elements: list[Any]) -> list[ChargeRow]:
    out = []
    for e in elements:
        if not isinstance(e, dict):
            continue
        amount = read_value(bill, f"elements[{e.get('index')}].amount", e.get("amount"), e.get("label"))
        if amount is None:
            continue
        recheck = (
            (e.get("formula_recheck") or {}).get("status")
            if isinstance(e.get("formula_recheck"), dict)
            else None
        )
        out.append(
            ChargeRow(
                label=str(e.get("label") or ""),
                code=e.get("code"),
                group=e.get("group"),
                kind=e.get("kind"),
                stage=e.get("stage"),
                tod_slot=e.get("tod_slot"),
                quantity=e.get("quantity"),
                rate=e.get("rate"),
                amount=amount,
                recheck=recheck,
            )
        )
    return out


def _cost(result: dict[str, Any]) -> str | None:
    total = Decimal(0)
    seen = False
    for u in result.get("usage") or []:
        if isinstance(u, dict) and u.get("cost_usd") is not None:
            try:
                total += Decimal(str(u["cost_usd"]))
                seen = True
            except ArithmeticError:
                continue
    return format(total, "f") if seen else None


def build(session: Session, bill: Bill) -> BillReading:
    b = _bill_dict(bill)
    fields = b.get("fields") or {}
    review = {r.path: r for r in bill_store.review(session, bill)}
    values: list[ReadValue] = []
    for path in ORDER:
        rv = read_value(bill, path, _walk(fields, path))
        if rv is None or (rv.value is None and path not in review):
            continue
        r = review.get(path)
        if r is not None:
            rv.confirmable = True
            rv.needs_confirmation = r.needs_confirmation
            rv.confirmed = r.confirmed
            if r.confirmed:
                rv.value = r.value
                rv.verification = "confirmed"
        values.append(rv)
    tod = _tod(bill, fields)
    for row in tod:
        for cell in (row.consumption, row.open_access, row.net):
            if cell is None:
                continue
            r = review.get(cell.path) or review.get(re.sub(r"\.kvah$", ".kwh", cell.path))
            if r is not None and cell is row.consumption:
                cell.path = r.path  # confirmations of a slot's consumption use the review's path
                cell.confirmable = True
                cell.needs_confirmation = r.needs_confirmation
                cell.confirmed = r.confirmed
                if r.confirmed:
                    cell.value = r.value
                    cell.verification = "confirmed"
    pages = [int(p) for p in b.get("pages") or []]
    return BillReading(
        bill_id=bill.id,
        filename=bill.filename,
        file_url=f"/bills/{bill.id}/file",
        pages=pages,
        page_url=f"/bills/{bill.id}/pages/{{page}}.png",
        status=bill.status,
        accepted=bill.accepted,
        discom=discom_of(bill).discom,
        profile_status=(b.get("profile") or {}).get("status"),
        readers_used=[str(r) for r in b.get("routes_used") or []],
        fields=values,
        tod=tod,
        charges=_charges(bill, list(b.get("elements") or [])),
        checks=[
            CheckRow(
                id=str(c.get("id")),
                description=c.get("description"),
                status=str(c.get("status")),
                expected=None if c.get("expected") is None else str(c.get("expected")),
                actual=None if c.get("actual") is None else str(c.get("actual")),
            )
            for c in b.get("checks") or []
            if isinstance(c, dict)
        ],
        review_reasons=[str(x) for x in b.get("review_reasons") or []],
        outstanding=[p for p, r in review.items() if r.needs_confirmation],
        cost_usd=_cost(bill.billx_result or {}),
    )


# ---------------------------------------------------------------- the hand-off to planning


class PlanValue(BaseModel):
    """A value planning takes from the bill: the SourcedValue (invariant 1) and how billx
    verified it, so the screen can say which still needs the client's eye."""

    key: str
    label: str
    value: SourcedValue = Field(json_schema_extra={"owner": "bills.billx_result", "ref_kinds": ["bill"]})
    verification: str | None


class PlanSlot(BaseModel):
    slot: str
    start: str | None
    end: str | None
    consumption: PlanValue | None
    open_access: PlanValue | None
    billed: PlanValue | None
    rate: PlanValue | None
    share_of_consumption: PlanValue | None


class PlanInputs(BaseModel):
    bill_id: str
    bill_month: str | None
    discom: str | None
    tariff_category: str | None  # as printed on the bill
    category_code: str | None = None  # the order's category the printed text maps to (None: unknown)
    category_note: str | None = None  # how it was read
    accepted: bool
    energy_unit: str
    facts: list[PlanValue]
    slots: list[PlanSlot]
    derived: list[PlanValue]
    notes: list[str]
    recognition: Recognition


_UNITS = {
    "kWh": Unit.KWH,
    "kVAh": Unit.KVAH,
    "kVA": Unit.KVA,
    "INR": Unit.INR,
}


def _sv(rv: ReadValue | None, unit: Unit, key: str, label: str) -> PlanValue | None:
    if rv is None or rv.value is None or rv.source_ref is None:
        return None
    try:
        value = Decimal(str(rv.value).replace(",", ""))
    except ArithmeticError:
        return None
    return PlanValue(
        key=key,
        label=label,
        value=SourcedValue(value=value, unit=unit, source_refs=(rv.source_ref,), label=label),
        verification=rv.verification,
    )


def _slot_number(text: str | None) -> str | None:
    m = re.search(r"(?i)\bt\s*o\s*d\s*[-·.]?\s*(\d)", text or "")
    return m.group(1) if m else None


def plan_inputs(session: Session, bill: Bill) -> PlanInputs:
    """What RE planning takes from this bill, each value with its bill source_ref: the slot table
    (consumption, open access set off, billed units, the slot's energy rate), the connection's
    demand, and the shares derived from them (each derived value carries its inputs' refs)."""
    r = build(session, bill)
    by_path = {v.path: v for v in r.fields}
    unit_name = r.tod[0].unit if r.tod else ("kWh" if by_path.get("energy.kwh") else "kVAh")
    eunit = _UNITS.get(unit_name, Unit.KWH)
    rate_unit = Unit.INR_PER_KVAH if eunit == Unit.KVAH else Unit.INR_PER_KWH
    facts: list[PlanValue] = []
    for path, unit, label in (
        ("demand.contract_kva", Unit.KVA, "Contract demand"),
        ("demand.max_kva", Unit.KVA, "Recorded maximum demand"),
        ("energy.kvah", Unit.KVAH, "Energy consumed (kVAh)"),
        ("energy.kwh", Unit.KWH, "Energy consumed (kWh)"),
        ("energy.billed_units", eunit, "Units billed by the DISCOM"),
        ("energy.power_factor", Unit.RATIO, "Power factor"),
        ("charges.energy", Unit.INR, "Energy charges"),
        ("totals.current_charges", Unit.INR, "Current charges"),
        ("totals.net_payable", Unit.INR, "Net payable"),
    ):
        pv = _sv(by_path.get(path), unit, path, label)
        if pv is not None:
            facts.append(pv)
    rates = {}
    for c in r.charges:
        n = _slot_number(c.tod_slot or c.label)
        if n and c.rate and c.code in (None, "energy_charge", "other") and n not in rates:
            rate_rv = c.amount.model_copy(
                update={"value": c.rate, "path": c.amount.path.replace(".amount", ".rate")}
            )
            rates[n] = rate_rv
    slots: list[PlanSlot] = []
    total = next((t for t in r.tod if t.slot.strip().lower() == "total"), None)
    for t in r.tod:
        if t is total:
            continue
        cons = _sv(t.consumption, eunit, f"{t.slot}.consumption", f"{t.slot}: consumed")
        oa = _sv(t.open_access, eunit, f"{t.slot}.open_access", f"{t.slot}: open access set off")
        net = _sv(t.net, eunit, f"{t.slot}.billed", f"{t.slot}: billed by the DISCOM")
        slot_rate = rates.get(_slot_number(t.slot) or "")
        rate = _sv(slot_rate, rate_unit, f"{t.slot}.rate", f"{t.slot}: energy rate")
        slots.append(
            PlanSlot(
                slot=t.slot,
                start=t.start,
                end=t.end,
                consumption=cons,
                open_access=oa,
                billed=net,
                rate=rate,
                share_of_consumption=None,
            )
        )
    derived: list[PlanValue] = []
    month_total = sum((s.consumption.value.value for s in slots if s.consumption), Decimal(0))
    if month_total > 0:
        for s in slots:
            if s.consumption is not None:
                share = (s.consumption.value.value / month_total * 100).quantize(Decimal("0.01"))
                s.share_of_consumption = PlanValue(
                    key=f"{s.slot}.share",
                    label=f"{s.slot}: share of the month",
                    value=derive(share, Unit.PERCENT, [s.consumption.value], label="share of consumption"),
                    verification=s.consumption.verification,
                )
    oa_total = [s.open_access.value for s in slots if s.open_access]
    cons_total = [s.consumption.value for s in slots if s.consumption]
    if oa_total and cons_total and month_total > 0:
        oa_sum = sum((v.value for v in oa_total), Decimal(0))
        derived.append(
            PlanValue(
                key="open_access_share",
                label="Share of consumption met by open access",
                value=derive(
                    (oa_sum / month_total * 100).quantize(Decimal("0.01")),
                    Unit.PERCENT,
                    [*oa_total, *cons_total],
                    label="open access share",
                ),
                verification=None,
            )
        )
    energy = next((f for f in facts if f.key == "charges.energy"), None)
    billed = next((f for f in facts if f.key == "energy.billed_units"), None)
    if energy and billed and billed.value.value > 0:
        derived.append(
            PlanValue(
                key="average_energy_rate",
                label="Average energy rate on billed units",
                value=derive(
                    (energy.value.value / billed.value.value).quantize(Decimal("0.0001")),
                    rate_unit,
                    [energy.value, billed.value],
                    label="average energy rate",
                ),
                verification=None,
            )
        )
    notes = []
    if any(s.start is None for s in slots):
        notes.append("Some slots print no hours; their energy is spread by your operating pattern.")
    if not bill.accepted:
        notes.append("Confirm the values marked for checking before this bill is used for planning.")
    month = by_path.get("period.bill_month")
    category = by_path.get("tariff.category") or by_path.get("connection.tariff_category")
    recognition = recognise(session, bill)
    mapped = (
        defaults.category_from_printed(recognition.state or "", str(category.value))
        if category is not None and category.value
        else None
    )
    return PlanInputs(
        bill_id=bill.id,
        bill_month=month.value if month else None,
        discom=r.discom,
        tariff_category=category.value if category else None,
        category_code=mapped.value if mapped is not None else None,
        category_note=mapped.ref.note if mapped is not None else None,
        accepted=bill.accepted,
        energy_unit=unit_name,
        facts=facts,
        slots=slots,
        derived=derived,
        notes=notes,
        recognition=recognition,
    )
