"""Reconciling a client's own working with the plan's chain, and closing the differences.

A working (spreadsheet, CSV, PDF or text) is stored with its text by page. A figure of it is set
against one link of the chain as a working line: the figure as written, its scale and unit, and the
words on that page it stands in. The API checks those words are on the page and the figure is in
them (the same grounding the regulation reader passes), converts it to the link's unit and computes
the difference itself. Whoever transcribes (the audit assistant or a person) decides no number.

A difference is closed by its kind:
- the client's own figure (a PPA price, a capacity, the open-access arrangement) becomes the plan's
  input, marked as stated by the client and citing the working, in a scenario "(your figures)",
  which is run again;
- a regulatory figure (a charge, a loss, a banking charge, an exemption) becomes a proposal against
  the approved rule for an analyst: accepting it makes a new draft rulebook version through
  rulebook.service, citing the regulation's page the analyst gives, which then needs the usual
  approval with golden tests (invariants 2 and 3). Nothing here writes to `rules`;
- anything else is computed by the plan (energy settled, money for the year): the line stays a
  difference to explain, or the client accepts the plan's figure."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.settings import get_settings
from ..core.units import IncompatibleUnits, Unit, convert
from ..db.models import Rule, RulebookVersion, RuleProposal, Scenario, SourceDocument, Working, WorkingLine
from ..documents import service as documents
from ..optimizer.scenarios import ScenarioSpec
from ..platform import runs as svc
from ..regreader.grounding import quote_on_page
from ..rulebook import service as rulebook_service  # the single writer of rules (invariant 3)
from . import chain as chain_data

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGE_CHARS = 60_000
SCALES = {
    "units": Decimal(1),
    "thousand": Decimal(1_000),
    "lakh": Decimal(100_000),
    "million": Decimal(1_000_000),
    "crore": Decimal(10_000_000),
}
REGULATORY = {"charge", "loss", "capacity", "drawal", "exemption", "banking"}
YOUR_FIGURES = " (your figures)"
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


class AuditError(ValueError):
    """A request the audit cannot carry out, in words the client can act on."""


# ---------------------------------------------------------------- reading a working


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return format(Decimal(str(v)).normalize(), "f")
    return str(v).strip()


def read_working(filename: str, data: bytes) -> list[dict[str, Any]]:
    """The text of a working by page: a sheet of a workbook, a page of a PDF, a whole CSV or text."""
    if len(data) > MAX_BYTES:
        raise AuditError("a working may be at most 10 MB")
    ext = Path(filename).suffix.lower()
    pages: list[dict[str, Any]] = []
    if ext in (".xlsx", ".xlsm"):
        import openpyxl

        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        except Exception as e:  # a corrupt or password-protected workbook
            raise AuditError(f"the workbook could not be opened ({type(e).__name__})") from e
        for i, ws in enumerate(wb.worksheets, start=1):
            lines = []
            for row in ws.iter_rows(values_only=True):
                cells = [_cell(v) for v in row]
                if any(cells):
                    lines.append(" | ".join(c for c in cells if c))
            pages.append({"page": i, "name": ws.title, "text": "\n".join(lines)[:MAX_PAGE_CHARS]})
    elif ext == ".csv":
        text = data.decode("utf-8-sig", errors="replace")
        rows = [" | ".join(c.strip() for c in r if c.strip()) for r in csv.reader(io.StringIO(text))]
        pages.append({"page": 1, "name": filename, "text": "\n".join(r for r in rows if r)[:MAX_PAGE_CHARS]})
    elif ext == ".pdf":
        import pdfplumber

        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for i, p in enumerate(pdf.pages, start=1):
                    pages.append(
                        {"page": i, "name": f"page {i}", "text": (p.extract_text() or "")[:MAX_PAGE_CHARS]}
                    )
        except Exception as e:
            raise AuditError(f"the PDF could not be read ({type(e).__name__})") from e
    elif ext in (".txt", ".md", ""):
        pages.append(
            {"page": 1, "name": filename, "text": data.decode("utf-8", errors="replace")[:MAX_PAGE_CHARS]}
        )
    else:
        raise AuditError("a working may be a spreadsheet (.xlsx), a CSV, a PDF or a text file")
    if not any(p["text"].strip() for p in pages):
        raise AuditError("no text could be read from this working (a scanned PDF needs its figures typed)")
    return pages


def workings_dir() -> Path:
    d = get_settings().ergplan_data_dir / "workings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def store_working(
    s: Session,
    connection_id: str,
    filename: str,
    content_type: str,
    data: bytes,
    actor: str,
    scenario_id: str | None = None,
) -> Working:
    pages = read_working(filename, data)
    sha = hashlib.sha256(data).hexdigest()
    path = workings_dir() / f"{sha}{Path(filename).suffix.lower()}"
    if not path.exists():
        path.write_bytes(data)
    try:
        _, run, _ = chain_data.latest_run(s, connection_id, scenario_id)
        run_id, scenario_id = run.id, run.scenario_id
    except chain_data.ChainNotFound:
        run_id = None
    w = Working(
        connection_id=connection_id,
        scenario_id=scenario_id,
        run_id=run_id,
        filename=Path(filename).name[:200],
        sha256=sha,
        content_type=content_type[:128],
        path=str(path),
        pages=pages,
        uploaded_by=actor,
    )
    s.add(w)
    s.flush()
    return w


# ---------------------------------------------------------------- lines


class LineIn(BaseModel):
    """One figure of a working, as written, with the words it stands in."""

    chain_key: str | None = Field(default=None, max_length=128)  # None: a figure the chain has no link for
    compare: Literal["value", "rate"] = "value"
    label: str = Field(min_length=1, max_length=300)
    value: str = Field(min_length=1, max_length=40)  # as written: "3.20", "1,23,456"
    scale: Literal["units", "thousand", "lakh", "million", "crore"] = "units"
    unit: str = Field(min_length=1, max_length=32)
    page: int = Field(ge=1)
    quote: str = Field(min_length=3, max_length=400)


def _number(text: str) -> Decimal:
    try:
        return Decimal(text.replace(",", "").replace("₹", "").strip())
    except InvalidOperation as e:
        raise AuditError(f"'{text}' is not a number") from e


def _in_quote(value: Decimal, quote: str) -> bool:
    for m in _NUMBER.findall(quote):
        try:
            if Decimal(m.replace(",", "")) == value:
                return True
        except InvalidOperation:
            continue
    return False


def _tolerance(ours: Decimal, unit: str) -> Decimal:
    floor = {
        Unit.INR_PER_KWH.value: Decimal("0.005"),
        Unit.PERCENT.value: Decimal("0.01"),
        Unit.INR.value: Decimal(1),
        Unit.KWH.value: Decimal(1),
    }.get(unit, Decimal("0.001"))
    return max(abs(ours) * Decimal("0.005"), floor)


def compare_line(line: WorkingLine, step: chain_data.ChainStep | None) -> None:
    """Theirs in our unit, ours, and whether they agree. Computed here, never by the assistant."""
    raw = line.value * SCALES[line.scale]
    if step is None:
        line.theirs, line.ours, line.ours_unit = raw, None, None
        line.status = "unmatched"
        return
    target = step.rate if line.compare == "rate" else step.value
    if target is None:
        raise AuditError(f"the link '{step.label}' has no rate to compare with; compare its value")
    try:
        theirs = convert(raw, line.unit, target.unit)
    except (IncompatibleUnits, ValueError) as e:
        raise AuditError(f"{line.unit} cannot be compared with {target.unit} ('{step.label}')") from e
    line.theirs, line.ours, line.ours_unit = theirs, target.value, str(target.unit)
    line.status = (
        "matches" if abs(theirs - target.value) <= _tolerance(target.value, str(target.unit)) else "differs"
    )


def record_line(
    s: Session, working: Working, chain: chain_data.Chain, body: LineIn, actor: str
) -> WorkingLine:
    """Ground the figure in the working, then compare it with the chain's link."""
    page = next((p for p in working.pages if p["page"] == body.page), None)
    if page is None:
        raise AuditError(f"the working has no page {body.page}")
    if not quote_on_page(body.quote, page["text"]):
        raise AuditError(f"the words '{body.quote[:80]}' are not on page {body.page} of {working.filename}")
    value = _number(body.value)
    if not _in_quote(value, body.quote):
        raise AuditError(f"{body.value} is not among the figures in the words quoted")
    try:
        Unit(body.unit)
    except ValueError as e:
        raise AuditError(f"unknown unit {body.unit}; use one of {', '.join(u.value for u in Unit)}") from e
    steps = chain_data.steps_by_key(chain)
    step = steps.get(body.chain_key) if body.chain_key else None
    if body.chain_key and step is None:
        raise AuditError(f"the chain has no link {body.chain_key}")
    line = WorkingLine(
        working_id=working.id,
        chain_key=body.chain_key,
        compare=body.compare,
        label=body.label,
        value=value,
        scale=body.scale,
        unit=body.unit,
        page=body.page,
        quote=body.quote,
        created_by=actor,
    )
    compare_line(line, step)
    s.add(line)
    s.flush()
    return line


def refresh_lines(s: Session, connection_id: str, chain: chain_data.Chain) -> int:
    """After a new run, compare every line that is still open against the new chain."""
    steps = chain_data.steps_by_key(chain)
    n = 0
    for line in s.scalars(
        select(WorkingLine)
        .join(Working, Working.id == WorkingLine.working_id)
        .where(
            Working.connection_id == connection_id, WorkingLine.status.in_(("matches", "differs", "stated"))
        )
    ):
        try:
            compare_line(line, steps.get(line.chain_key) if line.chain_key else None)
        except AuditError:
            continue
        line.updated_at = datetime.now(UTC)
        n += 1
    return n


def citation(line: WorkingLine, working: Working) -> str:
    page = next((p for p in working.pages if p["page"] == line.page), {"name": f"page {line.page}"})
    return f"your working {working.filename}, {page['name']}: '{line.quote[:160]}'"


def what_kind(step: chain_data.ChainStep) -> Literal["yours", "regulatory", "computed"]:
    if step.editable or step.key.endswith(".energy.capacity"):
        return "yours"
    if step.kind in REGULATORY and step.rule_id and step.pointer:
        return "regulatory"
    return "computed"


def _line(s: Session, line_id: str, connection_id: str) -> tuple[WorkingLine, Working]:
    line = s.get(WorkingLine, line_id)
    w = s.get(Working, line.working_id) if line else None
    if line is None or w is None or w.connection_id != connection_id:
        raise AuditError("no such line in this connection's workings")
    return line, w


# ---------------------------------------------------------------- closing: the client's own figures


def _your_scenario(s: Session, base: Scenario, actor: str) -> Scenario:
    if base.name.endswith(YOUR_FIGURES):
        return base
    sc = Scenario(
        site_id=base.site_id,
        connection_id=base.connection_id,
        name=f"{base.name}{YOUR_FIGURES}",
        spec=dict(base.spec),
        created_by=actor,
    )
    s.add(sc)
    s.flush()
    return sc


def use_their_figure(
    s: Session, connection_id: str, chain: chain_data.Chain, line_id: str, actor: str
) -> tuple[Scenario, str]:
    """The client's price or capacity becomes the plan's input (client_stated, citing the working),
    in the scenario '(your figures)', and a run of it is queued. Returns the scenario and run id."""
    line, w = _line(s, line_id, connection_id)
    step = chain_data.steps_by_key(chain).get(line.chain_key or "")
    if step is None or what_kind(step) != "yours":
        raise AuditError(
            "only your own figures (a price or a capacity) change the plan's inputs; a regulatory "
            "figure is proposed to an analyst, and a computed one follows from the inputs"
        )
    if line.theirs is None:
        raise AuditError("this line has no figure to use")
    source_id = step.key.split(".", 1)[0]
    src = next((x for x in chain.sources if x.id == source_id), None)
    if src is None:
        raise AuditError(f"no source {source_id} in this plan")
    base = s.get(Scenario, chain.scenario_id)
    assert base is not None
    sc = _your_scenario(s, base, actor)
    spec = ScenarioSpec.model_validate(sc.spec)
    stated = citation(line, w)[:300]
    cands = []
    found = False
    for c in spec.candidates:
        if c.kind == src.kind:
            found = True
            if step.kind == "price":
                c = c.model_copy(update={"price_inr_per_kwh": line.theirs, "stated_in": stated})
            else:  # a capacity: fix the source at the stated size
                mw = (
                    convert(line.theirs, step.value.unit, Unit.MW)
                    if step.value.unit != Unit.MW
                    else line.theirs
                )
                c = c.model_copy(update={"min_mw": mw, "max_mw": mw, "stated_in": stated})
        cands.append(c)
    if not found:
        raise AuditError(f"the scenario has no {src.label}")
    sc.spec = spec.model_copy(update={"candidates": cands}).model_dump(mode="json")
    run = svc.create_run(s, sc, actor)
    line.status, line.updated_at = "stated", datetime.now(UTC)
    line.note = f"used as the plan's input in '{sc.name}'"
    return sc, run.id


def set_ownership(
    s: Session, connection_id: str, chain: chain_data.Chain, source_id: str, ownership: str, actor: str
) -> tuple[Scenario, str]:
    if ownership not in ("captive", "group_captive", "third_party"):
        raise AuditError("ownership is captive, group_captive or third_party")
    src = next((x for x in chain.sources if x.id == source_id), None)
    if src is None:
        raise AuditError(f"no source {source_id} in this plan")
    base = s.get(Scenario, chain.scenario_id)
    assert base is not None
    sc = _your_scenario(s, base, actor)
    spec = ScenarioSpec.model_validate(sc.spec)
    cands = [
        c.model_copy(update={"ownership": ownership}) if c.kind == src.kind else c for c in spec.candidates
    ]
    sc.spec = spec.model_copy(update={"candidates": cands}).model_dump(mode="json")
    return sc, svc.create_run(s, sc, actor).id


def accept_ours(s: Session, connection_id: str, line_id: str, note: str | None) -> WorkingLine:
    line, _ = _line(s, line_id, connection_id)
    line.status, line.updated_at = "ours_accepted", datetime.now(UTC)
    line.note = (note or "the plan's figure accepted")[:500]
    return line


# ---------------------------------------------------------------- closing: regulatory figures


def propose_rule_change(
    s: Session, connection_id: str, chain: chain_data.Chain, line_id: str, reason: str, actor: str
) -> RuleProposal:
    """A rate the working states differently from the approved rule, for an analyst to decide."""
    line, w = _line(s, line_id, connection_id)
    step = chain_data.steps_by_key(chain).get(line.chain_key or "")
    if step is None or what_kind(step) != "regulatory":
        raise AuditError(
            "only a regulatory link (a charge, loss, exemption or banking charge) has a rule to change"
        )
    if line.compare != "rate" or line.theirs is None or step.rate is None:
        raise AuditError("set the working's rate (not its per-kWh effect) against the link first")
    if line.status == "matches":
        raise AuditError("the working agrees with the rule; there is nothing to propose")
    rule = s.get(Rule, step.rule_id)
    v = s.get(RulebookVersion, rule.rulebook_version_id) if rule else None
    if rule is None or v is None:
        raise AuditError("the rule behind this link is no longer stored")
    open_one = s.scalars(
        select(RuleProposal).where(RuleProposal.working_line_id == line.id, RuleProposal.status == "open")
    ).first()
    if open_one:
        return open_one
    p = RuleProposal(
        connection_id=connection_id,
        working_line_id=line.id,
        rule_id=rule.id,
        family=v.family,
        jurisdiction_id=v.jurisdiction_id,
        rule_label=rule.label,
        pointer=step.pointer or "",
        current=step.rate.value,
        proposed=line.theirs,
        unit=str(step.rate.unit),
        reason=f"{reason[:800]} (from {citation(line, w)})",
        proposed_by=actor,
    )
    s.add(p)
    line.status, line.updated_at = "proposed", datetime.now(UTC)
    s.flush()
    return p


def _set_pointer(body: dict[str, Any], pointer: str, value: Decimal) -> Any:
    parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer.strip("/").split("/")]
    node: Any = body
    for p in parts[:-1]:
        node = node[int(p)] if isinstance(node, list) else node[p]
    last: Any = int(parts[-1]) if isinstance(node, list) else parts[-1]
    old = node[last]
    # keep the type the family schema gives the field (a string stays a string)
    if isinstance(old, str):
        new: Any = format(value.normalize(), "f")
    elif isinstance(old, int) and not isinstance(old, bool) and value == value.to_integral_value():
        new = int(value)
    else:  # never a float in a rule (rule 15): the analyst edits such a field in the rulebook editor
        raise AuditError(f"the field {pointer} is not a decimal value; change it in the rulebook editor")
    node[last] = new
    return old


def accept_proposal(
    s: Session,
    proposal_id: str,
    actor: str,
    document_id: str,
    page: int,
    quote: str,
    note: str | None = None,
) -> RuleProposal:
    """An analyst accepts: a new draft of the rule's rulebook with the field changed and cited to
    the regulation's page (the quote must be on it). The draft is approved like any other."""
    p = s.get(RuleProposal, proposal_id)
    if p is None or p.status != "open":
        raise AuditError("no open proposal with this id")
    doc = s.get(SourceDocument, document_id)
    if doc is None:
        raise AuditError("no stored document with this id; register the regulation first")
    try:
        text = documents.page_text(doc, page)
    except documents.PageOutOfRange as e:
        raise AuditError(str(e)) from e
    if not quote_on_page(quote, text, ocr=documents.page_is_ocr(doc, page)):
        raise AuditError(f"the quote is not on page {page} of {doc.title or doc.id}")
    if not _in_quote(p.proposed, quote) and not _in_quote(p.proposed.normalize(), quote):
        raise AuditError(f"the quote does not print {format(p.proposed.normalize(), 'f')}")
    rule = s.get(Rule, p.rule_id)
    assert rule is not None
    draft = rulebook_service.duplicate(
        s, rule.rulebook_version_id, actor, notes=f"proposal {p.id}: {p.rule_label or p.family} {p.pointer}"
    )
    row = s.scalars(
        select(Rule).where(Rule.rulebook_version_id == draft.id, Rule.position == rule.position)
    ).one()
    body = copy.deepcopy(row.body)
    _set_pointer(body, p.pointer, p.proposed)
    field_refs = dict(row.field_refs or {})
    field_refs[p.pointer] = {
        "kind": "regulation" if doc.document_kind == "regulation" else "order",
        "document_id": doc.id,
        "page": page,
        "quote": quote[:400],
    }
    rulebook_service.update_row(
        s,
        draft.id,
        row.id,
        {
            "label": row.label,
            "scope": row.scope,
            "body": body,
            "source_ref": row.source_ref,
            "field_refs": field_refs,
            "review": {"proposal": p.id, "note": (note or "")[:500]},
        },
    )
    p.status, p.decided_by, p.decided_at = "accepted", actor, datetime.now(UTC)
    p.decision_note, p.draft_version_id = note, draft.id
    line = s.get(WorkingLine, p.working_line_id) if p.working_line_id else None
    if line is not None:
        line.status, line.updated_at = "rule_changed", datetime.now(UTC)
        line.note = f"a draft rule change awaits approval (version {draft.version})"
    return p


def reject_proposal(s: Session, proposal_id: str, actor: str, note: str) -> RuleProposal:
    p = s.get(RuleProposal, proposal_id)
    if p is None or p.status != "open":
        raise AuditError("no open proposal with this id")
    p.status, p.decided_by, p.decided_at, p.decision_note = "rejected", actor, datetime.now(UTC), note[:800]
    line = s.get(WorkingLine, p.working_line_id) if p.working_line_id else None
    if line is not None:
        line.status, line.updated_at, line.note = (
            "rejected",
            datetime.now(UTC),
            f"the analyst kept the rule: {note[:300]}",
        )
    return p
