"""The reading pipeline (build prompt 5.0 to 5.7): one file in, an Envelope out.

ingest → document-type gate → discom and version → readers (text layer, local OCR, Model A,
Model B on disagreement) → consensus → the transcription (`data`) → checks → formula recheck
and elements → the pass rule. Every step that produces a value goes through decide(); every
step that logs, logs ids and counts only.

The CLI, the API and the evaluation all call `read_file`; nothing else reads a bill.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from billx.core.schema import (
    ArrayValue,
    BillResult,
    BillType,
    CheckResult,
    DocumentType,
    Element,
    Envelope,
    FileInfo,
    FormulaRecheck,
    PageText,
    Profile,
    TextEnvelope,
    UsageRecord,
    Utility,
    Value,
    Word,
    make_value,
    with_checks,
)
from billx.reader.identify.gate import classify
from billx.reader.normalize.fields import (
    bill_from_values,
    either_required,
    required_paths,
    scalar_specs,
)
from billx.reader.read.consensus import (
    FieldSpec,
    ReaderOutput,
    consensus_fields,
    item_value,
    match_items,
)
from billx.reader.validate.passrule import verdict

log = logging.getLogger(__name__)

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".heic": "image/heic",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

METER_FIELDS = (
    "present",
    "past",
    "difference",
    "multiplying_factor",
    "consumption",
    "open_access",
    "net",
)
LINE_FIELDS = ("quantity", "rate", "amount")


@dataclass
class Options:
    allow_cloud_model: bool = False
    max_cost_usd: Decimal = Decimal("0")
    contract: str = "1.1"
    hints: dict[str, str] = field(default_factory=dict)


class ReadError(Exception):
    """A file-level refusal the API maps to an error code (unsupported type, too large)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def media_type_of(path: Path) -> str:
    try:
        return MEDIA_TYPES[path.suffix.lower()]
    except KeyError:
        raise ReadError("unsupported_type", f"{path.suffix} is not a supported file type") from None


# ---------------------------------------------------------------------------------------


def read_file(
    path: Path,
    *,
    allow_cloud_model: bool = False,
    max_cost_usd: Decimal = Decimal("0"),
    model_a=None,
    model_b=None,
    contract: str = "1.1",
    hints: dict[str, str] | None = None,
    model_c=None,
) -> Envelope:
    """Read one file. `model_a` and `model_b` are provider objects (or None when no key is
    configured); they are called only when `allow_cloud_model` is true and within budget.
    `model_c` is a whole-bill reader of a third family (LlamaParse), read beside Model A."""
    from billx.reader.ingest import PasswordRequired, TooLarge, load

    started = time.monotonic()
    media_type = media_type_of(path)
    sha = sha256_of(path)
    options = Options(allow_cloud_model, max_cost_usd, contract, hints or {})
    usage: list[UsageRecord] = []
    try:
        document = load(path, media_type)
    except PasswordRequired:
        bill = _refused(0, (1,), "unreadable", ("password_required",), None)
        return _envelope(contract, sha, 1, media_type, [bill], usage, started)
    except TooLarge as exc:
        raise ReadError("too_large", str(exc)) from None

    document.docling_job = _start_docling(path, document)
    groups = _bill_page_groups(document)  # local OCR runs while Docling converts
    bills = []
    for index, pages in enumerate(groups):
        part = document if len(pages) == document.page_count else _pages_of(document, pages)
        bill = _read_bill(part, pages, options, model_a, model_b, usage, sha, model_c)
        bills.append(bill.model_copy(update={"index": index}))
    log.info(
        "read sha=%s pages=%d bills=%d status=%s",
        sha[:12],
        document.page_count,
        len(bills),
        ",".join(b.status for b in bills),
    )
    return _envelope(contract, sha, document.page_count, media_type, bills, usage, started)


def _start_docling(path: Path, document):
    """Docling's conversion of the file, started in the background when Docling is configured
    (it is a separate service, so the local readers run meanwhile); None otherwise."""
    from concurrent.futures import ThreadPoolExecutor

    from billx.reader.read import docling

    if not docling.configured() or document.media_type != "application/pdf":
        return None
    pool = ThreadPoolExecutor(max_workers=1)
    job = pool.submit(docling.convert, path, scanned=not document.has_text_layer())
    pool.shutdown(wait=False)
    return job


def _layout_reading(document, bill_type):
    """The docling reader's output for this bill's pages, waiting for the conversion if it is
    still running; None when Docling is off or failed."""
    from billx.reader.read.docling import read_docling

    if document.docling is None and document.docling_job is not None:
        document.docling = document.docling_job.result()
    if document.docling is None:
        return None
    return read_docling(document.docling, {p.index for p in document.pages}, bill_type)


def _bill_page_groups(document) -> list[tuple[int, ...]]:
    """The file's pages grouped into bills (5.0 page sorting) from each page's local text: the
    genuine text layer where a page has one, else local OCR (read once and kept on the page)."""
    from billx.reader.identify.split import group_pages
    from billx.reader.read.local import page_texts

    if document.page_count < 2:
        return [tuple(range(1, document.page_count + 1))]
    texts = page_texts(document, "text_layer" if document.has_text_layer() else "local_ocr")
    if len(texts) != document.page_count:
        return [tuple(range(1, document.page_count + 1))]
    return group_pages(texts)


def _pages_of(document, pages: tuple[int, ...]):
    """A document holding only the given pages (1-based), each keeping its own page number."""
    import dataclasses

    return dataclasses.replace(document, pages=[document.pages[p - 1] for p in pages])


def read_text_file(path: Path) -> TextEnvelope:
    """A `kind: "text"` job (contract 5.3): every page's text and words with regions, from
    the genuine text layer when there is one, else local OCR. The gate does not run and
    nothing is extracted."""
    from billx.reader.ingest import PasswordRequired, TooLarge, load
    from billx.reader.read.local import page_words
    from billx.reader.read.words import group_lines, line_text, region_of

    started = time.monotonic()
    media_type = media_type_of(path)
    sha = sha256_of(path)
    try:
        document = load(path, media_type)
    except PasswordRequired:
        raise ReadError("unreadable", "password_required") from None
    except TooLarge as exc:
        raise ReadError("too_large", str(exc)) from None
    words_by_page = page_words(document, "text_layer") or page_words(document, "local_ocr") or []
    pages = []
    for i, words in enumerate(words_by_page):
        lines = group_lines(words)
        text = "\n".join(line_text(line) for line in lines)
        pages.append(
            PageText(
                page=i + 1,
                text=text,
                words=tuple(Word(text=w.text, region=region_of([w])) for w in words),
            )
        )
    return TextEnvelope(
        contract_version="1.0",
        file=FileInfo(sha256=sha, pages=document.page_count, media_type=media_type),
        pages=tuple(pages),
        seconds=Decimal(str(round(time.monotonic() - started, 3))),
    )


def _envelope(contract, sha, page_count, media_type, bills, usage, started) -> Envelope:
    return Envelope(
        contract_version=contract,
        file=FileInfo(sha256=sha, pages=page_count, media_type=media_type),
        bills=tuple(bills),
        usage=tuple(usage),
        seconds=Decimal(str(round(time.monotonic() - started, 3))),
    )


def _refused(
    index,
    pages,
    reason,
    notes,
    document_type,
    bill_type=None,
    utility=None,
    profile=None,
    fields=(),
    arrays=(),
) -> BillResult:
    """A refusal. A bill refused after reading still carries every field as read, with its
    evidence and verification (5.2), so a person or product can see what was found."""
    status = {
        "not_a_bill": "not_a_bill",
        "unreadable": "unreadable",
        "model_not_allowed": "model_not_allowed",
        "budget_exceeded": "budget_exceeded",
    }[reason]
    return BillResult(
        index=index,
        pages=tuple(pages),
        bill_type=bill_type,
        document_type=document_type or "not_a_bill",
        utility=utility or Utility(),
        profile=profile or Profile(),
        fields=tuple(fields),
        arrays=tuple(arrays),
        route="none",
        passed=False,
        status=status,  # type: ignore[arg-type]
        unread_reason=reason,
        notes=tuple(notes),
        accepted=False,
    )


# ---------------------------------------------------------------------------------------


def _read_bill(
    document, pages, options: Options, model_a, model_b, usage, sha, model_c=None
) -> BillResult:
    from billx.reader.read.local import page_texts, read_local

    # 1. local readers
    text_layer = read_local(document, "text_layer", "electricity")
    local_ocr = read_local(document, "local_ocr", "electricity")
    texts = page_texts(document, "text_layer" if text_layer else "local_ocr")
    joined = "\n".join(texts)

    # 2. the document-type gate on local signals; when they are unclear and the caller allows
    # cloud use, Model A confirms (5.0): a poor photo is read as the likeliest bill type and
    # counts as a bill only when the model returns its required fields
    gate = classify(joined)
    doc_type: DocumentType = gate.document_type
    confirm_with_model = False
    if gate.unclear:
        if not (options.allow_cloud_model and model_a is not None):
            return _refused(0, pages, "not_a_bill", ("type_unclear",), "not_a_bill")
        doc_type = (
            "gas_bill"
            if gate.scores.get("gas_bill", 0) > gate.scores.get("electricity_bill", 0)
            else "electricity_bill"
        )
        confirm_with_model = True
    if doc_type == "gas_bill":
        bill_type: BillType = "gas"
    elif doc_type == "electricity_bill":
        bill_type = "electricity"
    else:
        return _refused(0, pages, "not_a_bill", (f"document_type:{doc_type}",), doc_type)
    if bill_type == "gas":
        # the gas label rule needs the gas field list; re-read locally for gas
        text_layer = read_local(document, "text_layer", "gas")
        local_ocr = read_local(document, "local_ocr", "gas")

    outputs: list[ReaderOutput] = [o for o in (text_layer, local_ocr) if o is not None]
    routes_used = [o.reader for o in outputs]
    # every guaranteed field is read whatever the contract: 1.0 only renders its subset, and
    # the checks need the 6.4 fields (current charges, arrears) to tie the net payable
    specs = [
        FieldSpec(f["path"], f["type"], f.get("unit"), bool(f.get("required")))
        for f in scalar_specs(bill_type, "1.1")
    ]

    # 3. the discom and its version
    utility, profile, version = _identify(joined, outputs, specs)

    # 4. model readers, when allowed, configured and affordable
    model_outputs, refusal = _model_readings(
        document, outputs, specs, bill_type, options, model_a, model_b, usage, sha, version, model_c
    )
    # Docling's layout reading joins after the model readers ran (its conversion overlaps them);
    # it sits with the local readers, before the models, as every reader keeps its place
    layout = _layout_reading(document, bill_type)
    if layout is not None:
        local_count = len(outputs)
        outputs.insert(local_count, layout)
        routes_used.insert(local_count, layout.reader)
    outputs.extend(model_outputs)
    routes_used.extend(o.reader for o in model_outputs)
    if model_outputs:
        # identify again with what the readers verified: a scan's printed name may be cut or
        # unreadable to local OCR, and the bill month picks the version
        named = consensus_fields(outputs, [s for s in specs if s.path == "utility.name"])
        # profile.id is None exactly when the local text named no discom (_identify returned an
        # empty Profile above); only then may an unverified model-read name pick one
        found = _identify(
            identity_text(joined, named[0] if named else None, profile.id), outputs, specs
        )
        if found[0].id is not None:
            utility, profile, version = found
    if confirm_with_model:
        model_a_out = next((o for o in model_outputs if o.reader == "model_a"), None)
        required = required_paths(bill_type)
        found = model_a_out is not None and any(p in model_a_out.fields for p in required)
        if not found:
            return _refused(
                0, pages, "not_a_bill", ("type_unclear", "model_found_no_bill"), "not_a_bill"
            )
        doc_type = "electricity_bill" if bill_type == "electricity" else "gas_bill"

    # 5. consensus: scalar fields, then arrays
    values = _printed_units(consensus_fields(outputs, specs), version, joined)
    meters, meter_values = _array_values(outputs, "meters", ("register", "tod_slot"), METER_FIELDS)
    lines, line_values = _array_values(outputs, "lines", ("label",), LINE_FIELDS)
    # 6. codes on every line, then the fields the layouts print only inside tables
    from billx.reader.normalize.codes import code_for

    for ln in lines:
        ln["code"] = code_for(ln.get("group"), ln.get("label") or "", version)
        ln["kind"] = ln.get("kind") or "item"
        ln["stage"] = ln.get("stage") or "current"
        if ln["code"] == "arrears" and ln["kind"] == "subtotal":
            # the printed arrears line is the arrear-stage amount itself (G08, G09)
            ln["kind"], ln["stage"] = "item", "arrear"
    values = _derive_from_arrays(values, meters, lines, bill_type, specs)

    # 7. the transcription
    data = bill_from_values(bill_type, values, meters, lines)

    # 7. checks, with unverified inputs marked and arithmetic added to the Values
    layout_version = _for_layout(version, joined)
    checks = _run_checks(data, layout_version, values, meters, lines)
    values = _add_arithmetic(values, checks)

    # 8. elements with the formula recheck
    elements = _elements(data, lines, layout_version)

    if refusal is not None and not _all_required_verified(values, bill_type):
        # a model was needed and could not run: refused, but with everything that was read
        # and every check that ran on it, so a person sees what the local readers found
        arrays = (("readings[]", tuple(meter_values)), ("elements[]", tuple(line_values)))
        refused = _refused(
            0, pages, refusal[0], refusal[1], doc_type, bill_type, utility, profile, values, arrays
        )
        return refused.model_copy(
            update={
                "data": data,
                "checks": tuple(checks),
                "elements": tuple(elements),
                "routes_used": tuple(dict.fromkeys(routes_used)),
            }
        )

    # 9. the pass rule
    required = required_paths(bill_type)
    if options.contract == "1.0" and bill_type == "electricity":
        either = {}
    else:
        either = either_required(bill_type)
    energy_paths = (
        ("energy.kwh", "energy.kvah")
        if bill_type == "electricity"
        else ("volume.scm", "energy.mmbtu")
    )
    money_path = "totals.net_payable" if bill_type == "electricity" else "totals.amount"
    v = verdict(
        values,
        checks,
        required=required,
        energy_paths=energy_paths,
        money_path=money_path,
        either_required=either,
    )

    route = "cloud_model" if any(o.reader.startswith("model") for o in outputs) else "template"
    arrays = (
        ("readings[]", tuple(meter_values)),
        ("elements[]", tuple(line_values)),
    )
    # 1.0 has no review_reasons or flags: they travel in notes; 1.1 carries them as fields
    notes = list(v.review_reasons) + list(v.flags) if options.contract == "1.0" else []
    return BillResult(
        index=0,
        pages=tuple(pages),
        bill_type=bill_type,
        document_type=doc_type,
        utility=utility,
        profile=profile,
        route=route,
        routes_used=tuple(dict.fromkeys(routes_used)),
        fields=tuple(values),
        arrays=arrays,
        data=data,
        checks=tuple(checks),
        elements=tuple(elements),
        passed=v.passed,
        status=v.status,  # type: ignore[arg-type]
        review_reasons=v.review_reasons,
        flags=v.flags,
        unread_reason=None,
        notes=tuple(notes),
        accepted=v.accepted,
        accepted_by=v.accepted_by,  # type: ignore[arg-type]
    )


def identity_text(joined: str, name, profile_id: str | None) -> str:
    """The text the discom is identified from after the models read: the local text and the
    utility's name when verified. When the local text named no discom (a scan, or a name the
    text layer garbles), the name one model read is used too: it picks which profile's labels and
    checks apply, never a value, and a wrong profile shows as failing checks, not as a verified
    value."""
    value = getattr(name, "value", None)
    if not value:
        return joined
    if getattr(name, "verification", None) == "verified" or profile_id is None:
        return joined + "\n" + str(value)
    return joined


def _identify(text: str, outputs, specs) -> tuple[Utility, Profile, object | None]:
    from billx.reader.identify.profiles import match_discom, profiles, select_version

    discom_id = match_discom(text)
    name_value = consensus_fields(outputs, [s for s in specs if s.path == "utility.name"])
    name = name_value[0].value if name_value and name_value[0].value else None
    if discom_id is None:
        return Utility(id=None, name_as_printed=name, state=None), Profile(), None
    discom = profiles().discoms[discom_id]
    month_value = consensus_fields(outputs, [s for s in specs if s.path == "period.bill_month"])
    month = month_value[0].value if month_value and month_value[0].value else None
    try:
        version = select_version(discom_id, month)
    except Exception:  # a discom with no versions yet: read by the generic ladder
        version = None
    status = version.status if version is not None else "none"
    return (
        Utility(id=discom.id, name_as_printed=name, state=discom.state),
        Profile(id=discom.id, version=version.version if version else None, status=status),
        version,
    )


def _model_readings(
    document,
    outputs,
    specs,
    bill_type,
    options,
    model_a,
    model_b,
    usage,
    sha,
    version=None,
    model_c=None,
):
    """Model A reads the whole bill when allowed; Model B reads the fields that are still
    unverified or disputed after Model A. Returns the outputs and, when a model was needed
    but could not run, the refusal (reason, notes)."""
    from billx.reader.providers.base import BudgetExceeded, Page, ProviderError

    needs_model = not _all_required_verified(consensus_fields(outputs, specs), bill_type)
    if not needs_model:
        return [], None
    if not options.allow_cloud_model:
        return [], ("model_not_allowed", ())
    if model_a is None and model_b is None and model_c is None:
        return [], ("unreadable", ("no_model_configured",))

    pages = [Page("image/png", _png(p.image)) for p in document.pages]
    meanings = {f["path"]: f.get("description") for f in scalar_specs(bill_type, "1.1")}
    fields = [
        {"path": s.path, "type": s.field_type, "unit": s.unit, "description": meanings.get(s.path)}
        for s in specs
    ]
    hints = tuple(getattr(version, "prompt_hints", ()) or ())
    out: list[ReaderOutput] = []
    # the budget is the file's: what earlier bills of the same file spent counts too
    spent = sum((u.cost_usd for u in usage), Decimal(0))
    third = _start_third_reader(
        model_c, model_a, pages, document, fields, bill_type, sha, hints, options, spent
    )
    for reader in (model_a, model_b):
        if reader is None:
            continue
        if reader is model_b and third is not None:
            # the third reader read beside Model A; Model B reads what is still unsettled
            # after both
            reading = _finish_third_reader(third, model_c, sha)
            third = None
            if reading is not None:
                usage.extend(reading.usage)
                spent += sum((u.cost_usd for u in reading.usage), Decimal(0))
                out.append(reading.to_output())
        remaining = options.max_cost_usd - spent
        try:
            if reader.reader_name == "model_a":
                reading = reader.read_bill(
                    pages,
                    bill_kind=bill_type,
                    fields=fields,
                    bill_id=sha,
                    max_cost_usd=remaining,
                    hints=hints,
                )
            else:
                still = [
                    f
                    for f in fields
                    if not _settled(consensus_fields(outputs + out, specs), f["path"])
                ]
                if not still:
                    break
                reading = reader.read_fields(
                    pages,
                    bill_kind=bill_type,
                    fields=still,
                    bill_id=sha,
                    max_cost_usd=remaining,
                    hints=hints,
                )
        except BudgetExceeded:
            return out, ("budget_exceeded", ())
        except ProviderError as exc:
            log.warning("model call failed sha=%s reader=%s: %s", sha[:12], reader.reader_name, exc)
            continue
        usage.extend(reading.usage)
        spent += sum((u.cost_usd for u in reading.usage), Decimal(0))
        out.append(reading.to_output())
    if third is not None:
        reading = _finish_third_reader(third, model_c, sha)
        if reading is not None:
            usage.extend(reading.usage)
            out.append(reading.to_output())
    return out, None


def _start_third_reader(
    model_c, model_a, pages, document, fields, bill_type, sha, hints, options, spent
):
    """The whole-bill reader of a third family (LlamaParse), started on a thread beside
    Model A. Its budget is what is left after Model A's worst case, so the two together
    never exceed the caller's budget."""
    from concurrent.futures import ThreadPoolExecutor

    if model_c is None:
        return None
    reserve = Decimal(0)
    if model_a is not None and hasattr(model_a, "read_bill_prompt"):
        from billx.reader.providers.base import render_prompt
        from billx.reader.providers.usage import cost, estimate_tokens

        try:
            prompt = render_prompt(model_a.read_bill_prompt, fields, bill_type, hints)
            reserve = cost(
                model_a.model_spec,
                estimate_tokens(prompt, len(pages)),
                model_a.max_output_tokens,
            )
        except (KeyError, TypeError, ValueError):
            reserve = Decimal(0)
    budget = options.max_cost_usd - spent - reserve
    numbers = tuple(p.index for p in document.pages)
    pool = ThreadPoolExecutor(max_workers=1)
    job = pool.submit(
        model_c.read_bill,
        pages,
        bill_kind=bill_type,
        fields=fields,
        bill_id=sha,
        max_cost_usd=budget,
        hints=hints,
        page_numbers=numbers,
    )
    pool.shutdown(wait=False)
    return job


def _finish_third_reader(job, model_c, sha):
    """The third reader's reading, or None when it could not run (its usage is kept by the
    provider's own record; a refused or failed extra reading never refuses the bill)."""
    from billx.reader.providers.base import ProviderError

    try:
        return job.result()
    except ProviderError as exc:
        log.warning("model call failed sha=%s reader=%s: %s", sha[:12], model_c.reader_name, exc)
        return None


def _printed_units(values: list[Value], version, text: str) -> list[Value]:
    """The unit each value is printed in, where the layout prints a field in another unit
    than the field list's (`printed_units` in the profile version): the figure stays as
    printed, never converted, and the value says its unit."""
    import re

    units = {}
    for entry in getattr(version, "printed_units", ()) or ():
        if re.search(str(entry["when"]), text, re.IGNORECASE):
            units.update({p: entry["unit"] for p in entry["paths"]})
    if not units:
        return values
    return [v.model_copy(update={"unit": units[v.path]}) if v.path in units else v for v in values]


def _for_layout(version, text: str):
    """The version as the checks see it: a version whose arithmetic belongs to one layout
    (`layout_match`) keeps its rules, params and template only for a bill of that layout.
    The synthetic AVVNL and PVVNL versions carry stand-in rates; a real bill of the same
    discom must never be checked against them."""
    import dataclasses
    import re

    if version is None or not getattr(version, "layout_match", None):
        return version
    if re.search(version.layout_match, text, re.IGNORECASE):
        return version
    return dataclasses.replace(version, rules=(), params={}, params_history=(), template=None)


def _png(image) -> bytes:
    import io

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _settled(values: list[Value], path: str) -> bool:
    """Whether a field needs no further reading: it is verified or confirmed. A field no
    reader found is NOT settled: a model may find what local OCR missed (an account number
    printed under a bilingual label, a period printed only in the meter table)."""
    v = next((x for x in values if x.path == path), None)
    return v is not None and v.value is not None and v.verification in ("verified", "confirmed")


def _all_required_verified(values: list[Value], bill_type: BillType) -> bool:
    by = {v.path: v for v in values}
    either = either_required(bill_type)
    for path in required_paths(bill_type):
        v = by.get(path)
        ok = v is not None and v.value is not None and v.verification in ("verified", "confirmed")
        if ok:
            continue
        alt = by.get(either.get(path, ""))
        if (
            alt is not None
            and alt.value is not None
            and alt.verification in ("verified", "confirmed")
        ):
            continue
        return False
    return True


def _array_values(outputs, kind, key_fields, value_fields):
    """Match the readers' array items and decide each numeric cell; returns the rows (with
    Values in the numeric cells) and the contract ArrayValues."""
    matched = match_items(outputs, kind, key_fields)
    # Model A's transcription is the fullest reading (5.3): when it read this table, its rows
    # are the bill's rows and another reader's rows only confirm them. A row no model saw is
    # an OCR fragment (a heading, a column title, two cells run together) and must not enter
    # the arithmetic. Without Model A, the local readers' rows are the bill's rows.
    model_a_read = any(
        o.reader == "model_a" and (o.meters if kind == "meters" else o.lines) for o in outputs
    )
    if model_a_read:
        matched = [
            (key, cells)
            for key, cells in matched
            if any(out.reader == "model_a" for reads in cells.values() for out, _ in reads)
        ]
    rows: list[dict] = []
    array_values: list[ArrayValue] = []
    prefix = "readings" if kind == "meters" else "elements"
    for i, (key, cells) in enumerate(matched):
        row: dict = {}
        parts = key.split(" | ")
        for k, part in zip(key_fields, parts, strict=False):
            row[k] = part.split(" #")[0] if part else None
        vals = []
        for name in value_fields:
            if name in cells:
                v = item_value(
                    f"{prefix}[{i}].{name}",
                    "number",
                    cells[name],
                    "INR" if name == "amount" else None,
                )
                row[name] = v
                vals.append(v)
        for name, readings in cells.items():
            if name not in value_fields and name not in row:
                raw = next((r for _, r in readings if r), None)
                row[name] = raw
        rows.append(row)
        array_values.append(ArrayValue(key=key, fields=tuple(vals)))
    return rows, array_values


def _derive_from_arrays(values, meters, lines, bill_type, specs):
    """Guaranteed fields the layouts print only inside a table: the energy totals from the
    register total rows, charges.energy and charges.demand from the coded lines. The
    derived Value carries the cell's own readings, so its verdict is still the rule's."""
    if bill_type != "electricity":
        return values
    by = {v.path: v for v in values}

    def replace(path, value: Value):
        nonlocal values
        values = [value if v.path == path else v for v in values]

    for register, path in (("KWH", "energy.kwh"), ("KVAH", "energy.kvah")):
        current = by.get(path)
        if current is not None and current.value is not None:
            continue
        for m in meters:
            if (m.get("register") or "").upper() == register and (
                m.get("tod_slot") or ""
            ).upper() == "TOTAL":
                cell = m.get("consumption")
                if isinstance(cell, Value):
                    unit = "kWh" if register == "KWH" else "kVAh"
                    replace(path, make_value(path, "number", cell.readings, unit=unit))
    for code, path in (("energy_charge", "charges.energy"), ("demand_charge", "charges.demand")):
        current = by.get(path)
        if current is None or current.value is not None:
            continue
        coded = [
            ln for ln in lines if ln.get("code") == code and isinstance(ln.get("amount"), Value)
        ]
        if len(coded) == 1:
            replace(path, make_value(path, "number", coded[0]["amount"].readings, unit="INR"))
    return values


def _run_checks(data, version, values, meters, lines) -> list[CheckResult]:
    from billx.reader.validate.formula import run_checks
    from billx.reader.validate.registry import CheckContext

    results = run_checks(data, CheckContext(version=version, bill_month=data.period.bill_month))
    unverified = _unverified_paths(values, meters, lines)
    out = []
    for c in results:
        bad = tuple(p for p in c.paths if p in unverified)
        out.append(c.model_copy(update={"unverified_inputs": bad}) if bad else c)
    return out


def _unverified_paths(values, meters, lines) -> set[str]:
    bad = {
        v.path
        for v in values
        if v.value is not None and v.verification not in ("verified", "confirmed")
    }
    for i, m in enumerate(meters):
        for name in METER_FIELDS:
            v = m.get(name)
            if (
                isinstance(v, Value)
                and v.value is not None
                and v.verification not in ("verified", "confirmed")
            ):
                schema_name = {
                    "consumption": "gross_units",
                    "open_access": "open_access_units",
                    "net": "net_units",
                }.get(name, name)
                bad.add(f"meters[{i}].{schema_name}")
    for i, ln in enumerate(lines):
        for name in LINE_FIELDS:
            v = ln.get(name)
            if (
                isinstance(v, Value)
                and v.value is not None
                and v.verification not in ("verified", "confirmed")
            ):
                bad.add(f"line_items[{i}].{name}")
    return bad


def _add_arithmetic(values: list[Value], checks: list[CheckResult]) -> list[Value]:
    proved: dict[str, list[str]] = {}
    for c in checks:
        if c.status == "pass" and c.equality:
            for p in c.proves:
                proved.setdefault(p, []).append(c.id)
    return [with_checks(v, tuple(proved[v.path])) if v.path in proved else v for v in values]


def _elements(data, lines, version) -> list[Element]:
    from billx.reader.validate.formula import recheck_element
    from billx.reader.validate.registry import CheckContext

    ctx = CheckContext(version=version)
    out = []
    items = {it.index: it for it in data.line_items}
    for i, ln in enumerate(lines):
        item = items.get(i)
        amount = ln.get("amount")
        if item is None or not isinstance(amount, Value):
            continue
        recheck = recheck_element(item, data, ctx)
        if not isinstance(recheck, FormulaRecheck):
            recheck = FormulaRecheck(status="not_computable", reason="no_recheck")
        out.append(
            Element(
                index=i,
                label=item.label,
                group=item.group,
                kind=item.kind,
                stage=item.stage,
                code=item.code or "other",
                quantity=str(item.quantity) if item.quantity is not None else None,
                rate=str(item.rate) if item.rate is not None else None,
                unit=item.unit,
                tod_slot=item.tod_slot,
                amount=amount,
                formula_recheck=recheck,
            )
        )
    return out
