"""A survey of real, unconfirmed bills (build prompt Stage 3.1): how many were read end to
end, how many refused, how many need review and for which reasons, per discom and input
kind. The report holds counts, status codes, reason codes and check ids only: never a value,
a name, a file name or a page's text. Discoms come from the folder names the team used.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from billx.core.schema import ENGINE_VERSION
from billx.reader.normalize.fields import required_paths

log = logging.getLogger(__name__)

SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic"}


@dataclass
class Group:
    files: int = 0
    statuses: Counter = field(default_factory=Counter)
    reasons: Counter = field(default_factory=Counter)
    notes: Counter = field(default_factory=Counter)
    failed_checks: Counter = field(default_factory=Counter)
    document_types: Counter = field(default_factory=Counter)
    discom_matched: Counter = field(default_factory=Counter)
    errors: Counter = field(default_factory=Counter)
    seconds: list[Decimal] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)
    found: Counter = field(default_factory=Counter)  # required path -> files with a value
    verified: Counter = field(default_factory=Counter)  # required path -> files verified


def _input_kind(path: Path) -> str:
    if path.suffix.lower() != ".pdf":
        return "image"
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(str(path))
        try:
            for page in doc:
                if page.get_textpage().get_text_bounded().strip():
                    return "digital_pdf"
        finally:
            doc.close()
    except Exception:  # noqa: BLE001 - an unreadable PDF is reported by the reader
        return "pdf_unopened"
    return "scan_pdf"


def _code(reason: str) -> str:
    """A reason code without its path: `unverified:<path>` -> `unverified`."""
    return reason.split(":", 1)[0]


def survey(
    root: Path, read_file, *, allow_cloud_model: bool = False, max_cost_usd=Decimal(0)
) -> dict[str, Group]:
    groups: dict[str, Group] = defaultdict(Group)
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUFFIXES)
    for path in files:
        discom = (
            path.relative_to(root).parts[0] if len(path.relative_to(root).parts) > 1 else "unsorted"
        )
        kind = _input_kind(path)
        g = groups[f"{discom} / {kind}"]
        g.files += 1
        try:
            env = read_file(path, allow_cloud_model=allow_cloud_model, max_cost_usd=max_cost_usd)
        except Exception as exc:  # noqa: BLE001 - the class name is the finding
            g.errors[type(exc).__name__] += 1
            log.info("survey file=%d error=%s", g.files, type(exc).__name__)
            continue
        g.seconds.append(env.seconds)
        g.pages.append(env.file.pages)
        for bill in env.bills:
            g.statuses[bill.status] += 1
            g.document_types[bill.document_type] += 1
            g.discom_matched[bill.utility.id or "none"] += 1
            for r in bill.review_reasons:
                g.reasons[_code(r)] += 1
            for n in bill.notes:
                g.notes[_code(n)] += 1
            for c in bill.checks:
                if c.status == "fail":
                    g.failed_checks[c.id] += 1
            if bill.bill_type:
                for path in required_paths(bill.bill_type):
                    v = bill.field(path)
                    if v is not None and v.value is not None:
                        g.found[path] += 1
                        if v.verification in ("verified", "confirmed"):
                            g.verified[path] += 1
    return dict(groups)


def _median(values: list) -> str:
    if not values:
        return "-"
    ordered = sorted(values)
    return str(ordered[len(ordered) // 2])


def render(groups: dict[str, Group], root_label: str = "unconfirmed set") -> str:
    lines = [
        f"# Survey of the {root_label}",
        "",
        f"{datetime.now(UTC).date().isoformat()}, engine {ENGINE_VERSION}. Counts only: no value,",
        "name or file name appears here. Statuses are the engine's (contract 1.1); the",
        "`needs_review` reasons and failed checks are codes. Nothing here is an accuracy",
        "figure (**unmeasured**).",
        "",
        "| Discom / kind | files | statuses | reasons | failed checks | discom matched "
        "| required fields found (verified) | median s | median pages | errors |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    total = Group()
    for key in sorted(groups):
        g = groups[key]
        total.files += g.files
        total.statuses.update(g.statuses)
        total.reasons.update(g.reasons)
        total.failed_checks.update(g.failed_checks)
        total.errors.update(g.errors)
        total.seconds.extend(g.seconds)
        found = (
            ", ".join(
                f"{path.split('.')[-1]} {n} ({g.verified[path]})"
                for path, n in sorted(g.found.items())
            )
            or "-"
        )
        cells = [
            key,
            str(g.files),
            _fmt(g.statuses),
            _fmt(g.reasons),
            _fmt(g.failed_checks),
            _fmt(g.discom_matched),
            found,
            _median(g.seconds),
            _median(g.pages),
            _fmt(g.errors),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    cells = [
        "**all**",
        str(total.files),
        _fmt(total.statuses),
        _fmt(total.reasons),
        _fmt(total.failed_checks),
        "",
        "",
        _median(total.seconds),
        "",
        _fmt(total.errors),
    ]
    lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _fmt(counter: Counter) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(counter.items())) or "-"
