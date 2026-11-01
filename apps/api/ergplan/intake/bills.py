"""Bills: hand the file to billx, store its result, and decide which values ergPLAN may use.

Invariant 7: billx is the only reader. A bill is usable when billx accepted it (`accepted: true`)
or when the client has confirmed, one click per field, every value ergPLAN takes from it that billx
did not verify (`bill_confirmations`). A confirmation may also correct a value; the corrected value
is what ergPLAN uses, and its source_ref says who confirmed it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.settings import get_settings
from ..core.sourced import RefKind, SourceRef
from ..db.models import Bill, BillConfirmation
from . import bill_fields
from .billx_client import BillxClient

# What intake takes from a bill; each must be verified by billx or confirmed by the client.
# `energy` stands for energy.kwh or energy.kvah (one is enough).
REQUIRED = ("period.bill_month", "energy", "demand.max_kva", "demand.contract_kva", "tariff.category")
OPTIONAL = (
    "energy.power_factor",
    "totals.current_charges",
    "consumer.account_number",
    "consumer.name",
    "utility.name",
    "energy.billed_units",
)


class BillNotFound(LookupError):
    pass


class UnknownField(ValueError):
    pass


@dataclass
class FieldReview:
    path: str
    value: str | None
    unit: str | None
    verification: str | None
    page: int | None
    required: bool
    confirmed: bool
    needs_confirmation: bool

    def as_json(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _confirmations(session: Session, bill_id: str) -> dict[str, BillConfirmation]:
    out: dict[str, BillConfirmation] = {}
    for c in session.scalars(
        select(BillConfirmation).where(BillConfirmation.bill_id == bill_id).order_by(BillConfirmation.at)
    ):
        out[c.path] = c  # the latest confirmation of a path wins
    return out


def _bill_facts(bill: Bill) -> bill_fields.BillFacts:
    bills = bill_fields.from_result(bill.billx_result)
    match = [b for b in bills if b.index == bill.bill_index]
    if not match:
        raise BillNotFound(f"bill index {bill.bill_index} not in the stored billx result")
    return match[0]


def _paths(f: bill_fields.BillFacts) -> list[str]:
    paths = [
        "period.bill_month",
        "energy.kwh",
        "energy.kvah",
        "demand.max_kva",
        "demand.contract_kva",
        "tariff.category",
        *OPTIONAL,
    ]
    paths += [f"energy.tod.{i}.kwh" for i in range(len(f.tod))]
    return list(dict.fromkeys(paths))


def _tod_field(f: bill_fields.BillFacts, path: str) -> bill_fields.FieldValue:
    i = int(path.split(".")[2])
    row = f.tod[i]
    return bill_fields.FieldValue(
        path,
        None if row["kwh"] is None else str(row["kwh"]),
        row.get("unit") or "kWh",
        row.get("verification"),
        row.get("page"),
    )


def _field(f: bill_fields.BillFacts, path: str) -> bill_fields.FieldValue | None:
    if path.startswith("energy.tod."):
        return _tod_field(f, path)
    return f.fields.get(path)


def review(session: Session, bill: Bill) -> list[FieldReview]:
    """Every value intake takes from this bill, whether billx verified it, and whether it still
    needs the client's confirmation before the bill can be used."""
    f = _bill_facts(bill)
    conf = _confirmations(session, bill.id)
    has_kwh = (
        f.fields.get("energy.kwh") and f.fields["energy.kwh"].value is not None
    ) or "energy.kwh" in conf
    kwh_ok = "energy.kwh" in conf or bool(f.fields.get("energy.kwh") and f.fields["energy.kwh"].trusted)
    kvah_ok = "energy.kvah" in conf or bool(f.fields.get("energy.kvah") and f.fields["energy.kvah"].trusted)
    billed = f.fields.get("energy.billed_units")
    priced_in_kvah = (billed is not None and billed.value is not None and billed.unit == "kVAh") or any(
        (row.get("unit") or "") == "kVAh" for row in f.tod
    )
    # the month's energy is needed once: kWh where printed, else kVAh; a bill priced in kVAh whose
    # kVAh is verified and whose kWh only one reader read needs no confirmation of the kWh
    use_kvah = not has_kwh or (priced_in_kvah and kvah_ok and not kwh_ok)
    energy_path = "energy.kvah" if use_kvah else "energy.kwh"
    out = []
    for p in _paths(f):
        fv = _field(f, p)
        c = conf.get(p)
        required = p in REQUIRED or p == energy_path or p.startswith("energy.tod.")
        trusted = bool(fv and fv.trusted)
        value = c.value if c else (None if fv is None or fv.value is None else str(fv.value))
        out.append(
            FieldReview(
                path=p,
                value=value,
                unit=fv.unit if fv else None,
                verification=("confirmed" if c else fv.verification if fv else None),
                page=fv.page if fv else None,
                required=required,
                confirmed=c is not None,
                needs_confirmation=required and not bill.accepted and not trusted and c is None,
            )
        )
    return out


def outstanding(session: Session, bill: Bill) -> list[str]:
    return [r.path for r in review(session, bill) if r.needs_confirmation]


def store_file(data: bytes) -> str:
    sha = hashlib.sha256(data).hexdigest()
    d = get_settings().bill_files_dir
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{sha}.pdf"
    if not p.exists():
        p.write_bytes(data)
    return sha


def page_png(sha: str, page: int, scale: float = 2.0) -> bytes:
    """A page (1-based) of a stored bill file rendered for display, cached beside the file. This
    draws the page; it reads nothing from it (invariant 7)."""
    import io

    import pypdfium2 as pdfium

    d = get_settings().bill_files_dir
    cached = d / "pages" / f"{sha}-{page}.png"
    if cached.exists():
        return cached.read_bytes()
    src = d / f"{sha}.pdf"
    if not src.exists():
        raise FileNotFoundError(sha)
    pdf = pdfium.PdfDocument(str(src))
    try:
        if page < 1 or page > len(pdf):
            raise IndexError(page)
        image = pdf[page - 1].render(scale=scale).to_pil()
        # a scan's page can be very large: the view needs about 1,600 px on the long side
        longest = max(image.size)
        if longest > 1800:
            image = image.resize((image.width * 1800 // longest, image.height * 1800 // longest))
        buf = io.BytesIO()
        image.save(buf, format="PNG", optimize=True)
    finally:
        pdf.close()
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(buf.getvalue())
    return buf.getvalue()


UNREADABLE = "unreadable"


def _retry(session: Session, rows: list[Bill]) -> bool:
    if not all(b.status == UNREADABLE for b in rows):
        return False
    ids = [b.id for b in rows]
    return not session.scalar(select(BillConfirmation.id).where(BillConfirmation.bill_id.in_(ids)).limit(1))


def ingest(
    session: Session,
    data: bytes,
    filename: str,
    client: BillxClient | None = None,
    connection_id: str | None = None,
    uploaded_by: str | None = None,
) -> list[Bill]:
    """Read a bill file through billx (or reuse the stored result for the same file) and store one
    row per bill in it. Each uploader gets their own rows; billx reads a file once."""
    sha = store_file(data)
    q = select(Bill).where(Bill.file_sha256 == sha)
    mine = list(
        session.scalars(
            q.where(
                Bill.uploaded_by.is_(None) if uploaded_by is None else Bill.uploaded_by == uploaded_by
            ).order_by(Bill.bill_index)
        )
    )
    if mine and _retry(session, mine):
        # every bill in the stored reading was unreadable and nobody confirmed anything on it: billx
        # may read it now (a model key added, a profile fixed), so the file is read again
        for b in mine:
            session.delete(b)
        session.flush()
        mine = []
    if mine:
        for b in mine:
            if connection_id and b.connection_id is None:
                b.connection_id = connection_id
        return mine
    earlier = session.scalars(
        q.where(Bill.status != UNREADABLE).order_by(Bill.created_at)
    ).first()  # an unreadable reading is never reused for another uploader
    result = (
        earlier.billx_result
        if earlier is not None
        else (client or BillxClient()).read(data, filename, account_ref=connection_id)
    )
    return store_result(session, sha, filename, result, connection_id, uploaded_by)


def reusable(session: Session, sha: str, uploaded_by: str | None) -> tuple[list[Bill], dict[str, Any] | None]:
    """This uploader's stored bills of the file (when billx's reading of them still stands), and
    any other uploader's stored reading of the same file billx need not read again."""
    q = select(Bill).where(Bill.file_sha256 == sha)
    mine = list(
        session.scalars(
            q.where(
                Bill.uploaded_by.is_(None) if uploaded_by is None else Bill.uploaded_by == uploaded_by
            ).order_by(Bill.bill_index)
        )
    )
    if mine and _retry(session, mine):
        for b in mine:
            session.delete(b)
        session.flush()
        mine = []
    # the latest reading stands: a file read again after billx improved is not read the old way
    latest = session.scalars(q.where(Bill.status != UNREADABLE).order_by(Bill.created_at.desc())).first()
    return mine, (latest.billx_result if latest is not None else None)


def store_result(
    session: Session,
    sha: str,
    filename: str,
    result: dict[str, Any],
    connection_id: str | None,
    uploaded_by: str | None,
) -> list[Bill]:
    """One `bills` row per bill in billx's result for the file."""
    rows = []
    for f in bill_fields.from_result(result):
        b = Bill(
            connection_id=connection_id,
            file_sha256=sha,
            filename=filename,
            billx_job_id=str(result.get("job_id") or "") or None,
            bill_index=f.index,
            bill_month=f.bill_month,
            status=f.status,
            accepted=f.accepted,
            accepted_by=f.accepted_by or ("engine" if f.accepted else None),
            billx_result=result,
            uploaded_by=uploaded_by,
        )
        session.add(b)
        rows.append(b)
    session.flush()
    return rows


def confirm(session: Session, bill_id: str, path: str, value: str | None, actor: str) -> Bill:
    bill = session.get(Bill, bill_id)
    if bill is None:
        raise BillNotFound(bill_id)
    if path not in {r.path for r in review(session, bill)}:
        raise UnknownField(path)
    session.add(BillConfirmation(bill_id=bill_id, path=path, value=value, confirmed_by=actor))
    session.flush()
    if path == "period.bill_month" and value:
        bill.bill_month = bill_fields.parse_month(value) or bill.bill_month
    if not bill.accepted and not outstanding(session, bill):
        bill.accepted = True
        bill.accepted_by = "bill_confirmations"
    return bill


def accept(session: Session, bill_id: str, actor: str) -> Bill:
    """The client checked the values ergPLAN takes against the bill and accepts it: each required
    value that billx verified (or that was corrected) is confirmed in their name, one recorded
    confirmation per value (invariant 7). Values still outstanding must be confirmed first."""
    bill = session.get(Bill, bill_id)
    if bill is None:
        raise BillNotFound(bill_id)
    if bill.accepted:
        return bill
    rows = review(session, bill)
    missing = [r.path for r in rows if r.needs_confirmation]
    if missing:
        raise ValueError("confirm these values first: " + ", ".join(missing))
    for r in rows:
        if r.required and r.value is not None and not r.confirmed:
            session.add(BillConfirmation(bill_id=bill_id, path=r.path, value=r.value, confirmed_by=actor))
    session.flush()
    bill.accepted = True
    bill.accepted_by = "bill_confirmations"
    return bill


@dataclass(frozen=True)
class BillValue:
    value: str | None
    unit: str | None
    ref: SourceRef

    @property
    def dec(self) -> Decimal | None:
        return bill_fields.to_dec(self.value)


def values(session: Session, bill: Bill) -> dict[str, BillValue]:
    """The values intake may use from an accepted bill, each with its bill source_ref."""
    if not bill.accepted:
        raise ValueError("bill is not accepted: confirm its outstanding fields first")
    conf = _confirmations(session, bill.id)
    out = {}
    for r in review(session, bill):
        if r.value is None:
            continue
        c = conf.get(r.path)
        if c is None and not r.required and r.verification not in ("verified", None):
            # an optional value billx did not verify (a power factor read two ways) and nobody
            # confirmed is left out: the bill's acceptance covers what was checked, not this
            continue
        note = f"confirmed by {c.confirmed_by}" if c else f"billx: {r.verification or 'accepted bill'}"
        out[r.path] = BillValue(
            r.value,
            r.unit,
            SourceRef(kind=RefKind.BILL, bill_id=bill.id, field_path=r.path, page=r.page, note=note),
        )
    return out


def tod_slots(bill: Bill) -> list[str | None]:
    return [row["slot"] for row in _bill_facts(bill).tod]


def profile_id(bill: Bill) -> str | None:
    return _bill_facts(bill).profile_id
