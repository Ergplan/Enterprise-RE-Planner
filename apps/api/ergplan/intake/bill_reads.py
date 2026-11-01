"""Reading a bill file in the background: the upload returns at once with a `bill_reads` row,
the worker hands the file to billx and polls it (Docling and two model readers take minutes), and
the bills billx returns become `bills` rows. The page shows the file's pages meanwhile and opens
the reading view when billx is done.

Invariant 7: billx reads the file; this module stores the file, counts its pages (to draw them)
and waits.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.settings import get_settings
from ..db.base import session_scope
from ..db.models import Bill, BillRead
from . import bills as bill_store
from .billx_client import BillxClient, BillxError

log = logging.getLogger("ergplan.bill_reads")


def page_count(sha: str) -> int:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(get_settings().bill_files_dir / f"{sha}.pdf"))
    try:
        return len(pdf)
    finally:
        pdf.close()


def queue(
    session: Session,
    data: bytes,
    filename: str,
    connection_id: str | None = None,
    uploaded_by: str | None = None,
) -> BillRead:
    """Store the file and queue its reading. A file billx already read (for this uploader, or
    for anyone, while that reading stands) is done at once from the stored reading."""
    sha = bill_store.store_file(data)
    try:
        pages = page_count(sha)
    except Exception as e:
        raise ValueError("the file could not be opened as a PDF") from e
    read = BillRead(
        file_sha256=sha,
        filename=filename,
        pages=pages,
        connection_id=connection_id,
        uploaded_by=uploaded_by,
        status="queued",
    )
    session.add(read)
    mine, stored = bill_store.reusable(session, sha, uploaded_by)
    if mine or stored is not None:
        rows = mine or bill_store.store_result(
            session, sha, filename, stored or {}, connection_id, uploaded_by
        )
        for b in rows:
            if connection_id and b.connection_id is None:
                b.connection_id = connection_id
        read.status = "done"
        read.bill_ids = [b.id for b in rows]
        read.finished_at = datetime.now(UTC)
    session.flush()
    return read


def claim_next() -> str | None:
    """The oldest queued read, marked `reading` (one worker takes each)."""
    with session_scope(actor="worker") as s:
        read = s.scalars(
            select(BillRead)
            .where(BillRead.status == "queued")
            .order_by(BillRead.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if read is None:
            return None
        read.status = "reading"
        read.started_at = datetime.now(UTC)
        return read.id


def execute(read_id: str, client: BillxClient | None = None) -> str:
    """Hand the file to billx, wait for its result, store the bills. Returns the final status."""
    with session_scope(actor="worker") as s:
        read = s.get(BillRead, read_id)
        if read is None:
            return "missing"
        sha, filename = read.file_sha256, read.filename or "bill.pdf"
    data = (get_settings().bill_files_dir / f"{sha}.pdf").read_bytes()
    try:
        result = (client or BillxClient()).read(data, filename)
    except BillxError as e:
        with session_scope(actor="worker") as s:
            read = s.get(BillRead, read_id)
            if read is not None:
                read.status = "failed"
                read.error = str(e)[:500]
                read.finished_at = datetime.now(UTC)
        log.info("bill read %s failed: %s", read_id, type(e).__name__)
        return "failed"
    with session_scope(actor="worker") as s:
        read = s.get(BillRead, read_id)
        if read is None:
            return "missing"
        rows = bill_store.store_result(s, sha, filename, result, read.connection_id, read.uploaded_by)
        read.bill_ids = [b.id for b in rows]
        _retire(s, read.replaces)
        read.billx_job_id = str(result.get("job_id") or "") or None
        read.status = "done"
        read.finished_at = datetime.now(UTC)
    log.info("bill read %s done: %d bills", read_id, len(rows))
    return "done"


def _retire(session: Session, bill_ids: list[str]) -> None:
    """The bills a new reading replaces are removed, unless they were accepted (a plan may cite
    them) or someone confirmed a value on them (a person's confirmation is never thrown away);
    those stay beside the new reading."""
    from ..db.models import BillConfirmation

    for bid in bill_ids:
        b = session.get(Bill, bid)
        if b is None or b.accepted:
            continue
        confirmed = session.scalars(
            select(BillConfirmation.id).where(BillConfirmation.bill_id == bid).limit(1)
        ).first()
        if confirmed is None:
            session.delete(b)


def reread(session: Session, bill: Bill, by: str | None) -> BillRead:
    """Read a stored file again (after billx improved): a new reading of the same file whose
    bills replace this file's bills for the same uploader when it is done."""
    siblings = list(
        session.scalars(
            select(Bill).where(
                Bill.file_sha256 == bill.file_sha256,
                Bill.uploaded_by.is_(None)
                if bill.uploaded_by is None
                else Bill.uploaded_by == bill.uploaded_by,
            )
        )
    )
    read = BillRead(
        file_sha256=bill.file_sha256,
        filename=bill.filename,
        pages=page_count(bill.file_sha256),
        connection_id=bill.connection_id,
        uploaded_by=bill.uploaded_by or by,
        status="queued",
        replaces=[b.id for b in siblings],
    )
    session.add(read)
    session.flush()
    return read


def requeue_stale() -> int:
    """Reads left `reading` by a worker that stopped are read again."""
    with session_scope(actor="worker") as s:
        stale = list(s.scalars(select(BillRead).where(BillRead.status == "reading")))
        for r in stale:
            r.status = "queued"
        return len(stale)


def drain(client: BillxClient | None = None) -> int:
    n = 0
    while (read_id := claim_next()) is not None:
        execute(read_id, client)
        n += 1
    return n


def bills_of(session: Session, read: BillRead) -> list[Bill]:
    if not read.bill_ids:
        return []
    rows = {b.id: b for b in session.scalars(select(Bill).where(Bill.id.in_(read.bill_ids)))}
    return [rows[i] for i in read.bill_ids if i in rows]
