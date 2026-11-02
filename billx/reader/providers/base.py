"""The provider interface: what a model reader is given and what it returns.

A provider transcribes; it returns each field as the string printed on the bill (or leaves
the field out when not printed). It never calculates (rule 6). This package is the only
code that imports a model SDK (rule 9).

Every model call goes through `BaseReader`: a worst-case cost estimate compared with the
caller's remaining `max_cost_usd` and the per-call ceiling before the call (invariant 8; a
refusal makes no HTTP request and still writes a usage record), a timeout, bounded retries
(rule 14: on a 429 wait `rate_limit_wait_seconds`, then back off), and one usage record
after, whether the call succeeded or not. JSON numbers in a model's answer are kept as the
literal text the model wrote (`parse_int=str`, `parse_float=str`): a value is never a float
(invariant 4). Nothing here logs or raises a bill value or a key (invariant 9).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol

from billx.core.schema import Region, UsageRecord
from billx.core.settings import data_dir, load_config, setting
from billx.reader.providers.usage import (
    cost,
    estimate_tokens,
    prices_are_placeholder,
    record_usage,
)
from billx.reader.read.consensus import RawRead, ReaderOutput

log = logging.getLogger(__name__)

ReaderName = Literal["model_a", "model_b"]
BillKind = Literal["electricity", "gas"]

METER_KEYS = (
    "register",
    "tod_slot",
    "present",
    "past",
    "difference",
    "multiplying_factor",
    "consumption",
    "open_access",
    "net",
)
LINE_KEYS = ("group", "label", "kind", "stage", "quantity", "rate", "unit", "amount", "detail_of")
LINE_KINDS = {"item", "subtotal", "info"}
LINE_STAGES = {"current", "arrear", "adjustment"}


@dataclass(frozen=True)
class Page:
    mime: str  # image/png or image/jpeg
    data: bytes


class ProviderError(Exception):
    """A failed or refused model call. Its message carries ids and error classes only, never
    values. `usage` holds the call's usage record (zero tokens when no request was made) so
    the caller can still account for it in the result's `usage` (invariant 8)."""

    def __init__(self, message: str, usage: tuple[UsageRecord, ...] = ()):
        super().__init__(message)
        self.usage = usage


class BudgetExceeded(ProviderError):
    """The call's worst-case cost is above what is left of the caller's `max_cost_usd`; no
    request was made (5.3 step 7: the bill ends `budget_exceeded`)."""


class Provider(Protocol):
    model_spec: str  # e.g. "openai:gpt-6.1-sol"
    prompt_version: str  # e.g. "prefill_v1"

    def prefill(
        self, pages: list[Page], fields: list[dict], *, bill_kind: str, bill_id: str
    ) -> dict[str, str]: ...


@dataclass
class ModelReading:
    """One model reader's transcription of a bill, every value the printed string (never a
    number), ready for consensus through `to_output()`.

    `fields` maps a guaranteed-field path to the text printed for it (paths the bill does not
    print are absent). `meters` has one dict per meter-table row (keys `METER_KEYS`) and
    `lines` one per printed line with an amount (keys `LINE_KEYS`; `label` and `amount` are
    always present, the rest may be None). `usage` is the call's usage record.
    """

    reader_name: ReaderName
    family: str
    model_spec: str
    model_id: str
    prompt_version: str
    fields: dict[str, str] = field(default_factory=dict)
    meters: list[dict[str, str | None]] = field(default_factory=list)
    lines: list[dict[str, str | None]] = field(default_factory=list)
    extraction_notes: list[str] = field(default_factory=list)
    usage: list[UsageRecord] = field(default_factory=list)
    # a reader that cites where it read a field (LlamaParse): path -> (page 0-based, region)
    citations: dict[str, tuple[int | None, Region | None]] = field(default_factory=dict)

    def to_output(self) -> ReaderOutput:
        """The reading as consensus consumes it: every field a RawRead of the printed text,
        meters and lines as dicts of raw strings. The model does not say which page a value
        is on, so pages and regions are None, except where the reader cited them."""
        return ReaderOutput(
            reader=self.reader_name,
            method="vision",
            family=self.family,
            model_id=self.model_id,
            prompt_version=self.prompt_version,
            fields={
                path: RawRead(raw, *self.citations.get(path, (None, None)))
                for path, raw in self.fields.items()
            },
            meters=[dict(m) for m in self.meters],
            lines=[dict(ln) for ln in self.lines],
        )


# prompts ----------------------------------------------------------------------------------

_PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


def field_lines(fields: list[dict], describe: bool = False) -> str:
    """The field list as every prompt shows it: path, type and unit, and with `describe` the
    field's meaning from config/guaranteed_fields.yaml; never a value."""
    lines = []
    for f in fields:
        unit = f", {f['unit']}" if f.get("unit") else ""
        meaning = f": {f['description']}" if describe and f.get("description") else ""
        lines.append(f"- {f['path']}: {f['type']}{unit}{meaning}")
    return "\n".join(lines)


def render_template(version: str, **slots: str) -> str:
    """The versioned prompt file with its `{{SLOT}}` markers filled in. Prompt files are never
    edited in place; a change is a new version (rule 9)."""
    text = (_PROMPTS / f"{version}.md").read_text(encoding="utf-8")
    for name, value in slots.items():
        text = text.replace("{{" + name + "}}", value)
    return text


def render_prompt(
    version: str, fields: list[dict], bill_kind: str, hints: tuple[str, ...] = ()
) -> str:
    """A field-list prompt (prefill, read_bill, read_fields) for `bill_kind`. `hints` are the
    profile version's `prompt_hints`: layout notes, never a value from another reader."""
    hint_text = "\n".join(f"- {h}" for h in hints) if hints else "- (none)"
    return render_template(
        version,
        BILL_KIND=bill_kind,
        FIELDS=field_lines(fields),
        FIELDS_DESCRIBED=field_lines(fields, describe=True),
        HINTS=hint_text,
    )


# parsing ----------------------------------------------------------------------------------


def _text(value: Any) -> str | None:
    """A non-empty JSON string, stripped; anything else (null, boolean, object, list) is
    "not printed". Numbers arrive as strings already (see `load_json`)."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def load_json(text: str) -> Any:
    """The model's answer as JSON with numbers kept as their literal text. A code fence
    around the object is tolerated; anything else that is not JSON raises ValueError."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else ""
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    try:
        return json.loads(s, parse_float=str, parse_int=str)
    except json.JSONDecodeError as e:
        raise ValueError("not JSON") from e


def parse_fields(obj: Any, fields: list[dict]) -> dict[str, str]:
    """Known paths with non-empty printed strings; unknown keys, null and booleans dropped."""
    if not isinstance(obj, dict):
        raise ValueError("not an object")
    paths = {f["path"] for f in fields}
    out = {}
    for key, value in obj.items():
        if key in paths and (text := _text(value)) is not None:
            out[key] = text
    return out


def parse_items(
    items: Any, keys: tuple[str, ...], required: tuple[str, ...] = ()
) -> list[dict[str, str | None]]:
    """A list of row objects reduced to `keys` (missing keys None); a row that is not an
    object or lacks a `required` key is dropped."""
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = {k: _text(item.get(k)) for k in keys}
        if any(row[k] is None for k in required):
            continue
        out.append(row)
    return out


def parse_lines(items: Any) -> list[dict[str, str | None]]:
    """Printed lines: `label` and `amount` required; `kind` and `stage` kept only when they
    are one of the schema's words (anything else becomes None for the integrator to default)."""
    rows = parse_items(items, LINE_KEYS, required=("label", "amount"))
    for row in rows:
        for key, allowed in (("kind", LINE_KINDS), ("stage", LINE_STAGES)):
            word = (row[key] or "").lower()
            row[key] = word if word in allowed else None
        if row.get("detail_of"):
            row["kind"] = "info"  # a line that itemises another is never added in a second time
    return rows


def parse_notes(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [t for t in (_text(x) for x in items) if t is not None]


# the common call --------------------------------------------------------------------------

_NO_CREDIT = ("insufficient_quota", "credit_balance_exhausted", "billing_error")


def _out_of_credit(error: Exception) -> bool:
    """A rate-limit error that is really an empty account (OpenAI `insufficient_quota`)."""
    body = getattr(error, "body", None)
    kinds = {getattr(error, "code", None), getattr(error, "type", None)}
    if isinstance(body, dict):
        kinds |= {body.get("code"), body.get("type")}
        inner = body.get("error")
        if isinstance(inner, dict):
            kinds |= {inner.get("code"), inner.get("type")}
    return any(k in _NO_CREDIT for k in kinds if isinstance(k, str))


class BaseReader:
    """What the two model readers share: settings, the budget check, the retry loop and the
    usage record. A subclass sets `family`, `reader_name`, `provider_name` and the SDK's
    error classes, and builds the request."""

    family: str
    reader_name: ReaderName
    provider_name: str
    retryable: tuple[type[Exception], ...]
    rate_limited: type[Exception]
    sdk_error: type[Exception]

    def __init__(self, model_spec: str, *, usage_log: Path):
        self.model_spec = model_spec
        self.model_id = model_spec.partition(":")[2]
        self.usage_log = usage_log
        self.cfg = load_config("providers.yaml")

    @property
    def max_image_edge_px(self) -> int:
        return int(self.cfg.get("max_image_edge_px", 2000))

    @property
    def max_output_tokens(self) -> int:
        return int(self.cfg["max_output_tokens"])

    def temperature(self) -> float | None:
        """The configured temperature for this model id, or None when the model is called
        without one (invariant 6: 0 where the model accepts it; some reject the parameter)."""
        return (self.cfg.get("temperature") or {}).get(self.model_spec)

    def _usage_record(self, record: dict) -> UsageRecord:
        return UsageRecord(
            provider=self.provider_name,
            model=self.model_spec,
            purpose=record["purpose"],
            input_tokens=int(record["input_tokens"]),
            output_tokens=int(record["output_tokens"]),
            cost_usd=Decimal(record["cost_usd"]),
        )

    def _skeleton(
        self, *, purpose: str, prompt_version: str, bill_id: str, pages: int, images: int
    ) -> dict:
        return {
            "purpose": purpose,
            "bill_id": bill_id,
            "provider": self.provider_name,
            "model": self.model_spec,
            "prompt": prompt_version,
            "pages": pages,
            "images": images,
            "prices_placeholder": prices_are_placeholder(),
            "attempts": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": "0",
        }

    def _plan(
        self,
        *,
        purpose: str,
        prompt_version: str,
        bill_id: str,
        prompt: str,
        images: int,
        pages: int,
        max_cost_usd: Decimal,
    ) -> dict:
        """The usage-record skeleton for a call, after its worst-case cost (prompt tokens,
        every image, the full output allowance, at config prices) passed both limits. A call
        above the caller's budget raises BudgetExceeded, one above the per-call ceiling
        ProviderError; both write a `refused` record and make no request."""
        estimate = cost(self.model_spec, estimate_tokens(prompt, images), self.max_output_tokens)
        record = self._skeleton(
            purpose=purpose,
            prompt_version=prompt_version,
            bill_id=bill_id,
            pages=pages,
            images=images,
        )
        record["cost_estimate_usd"] = str(estimate)
        record["max_cost_usd"] = str(max_cost_usd)
        if estimate > max_cost_usd:
            record_usage(self.usage_log, {**record, "status": "refused", "reason": "budget"})
            raise BudgetExceeded(
                f"bill {bill_id[:12]}: {purpose} estimate above the remaining budget",
                (self._usage_record(record),),
            )
        if estimate > Decimal(str(self.cfg["max_cost_usd_per_call"])):
            record_usage(self.usage_log, {**record, "status": "refused", "reason": "ceiling"})
            raise ProviderError(
                f"bill {bill_id[:12]}: {purpose} estimate above the per-call ceiling",
                (self._usage_record(record),),
            )
        return record

    def _call(self, record: dict, bill_id: str, request: Callable[[], Any], sleep: Callable):
        """`request()` with bounded retries: a 429 waits `rate_limit_wait_seconds`, a timeout,
        connection error or 5xx `retry_wait_seconds`, each further wait multiplied by
        `backoff_factor`; any other SDK error, and a 429 that says the account has no credit
        left (waiting does not help), fails at once. A failure writes the usage record and
        raises ProviderError naming the error class only."""
        cfg = self.cfg
        max_attempts = int(cfg["max_attempts"])
        started = time.monotonic()
        response, error = None, None
        for attempt in range(1, max_attempts + 1):
            record["attempts"] = attempt
            try:
                response = request()
                break
            except self.retryable as e:
                error = e
                if attempt == max_attempts or _out_of_credit(e):
                    break
                base = (
                    cfg["rate_limit_wait_seconds"]
                    if isinstance(e, self.rate_limited)
                    else cfg["retry_wait_seconds"]
                )
                wait = base * cfg["backoff_factor"] ** (attempt - 1)
                log.warning(
                    "%s bill=%s attempt=%d %s; waiting %ss",
                    record["purpose"],
                    bill_id[:12],
                    attempt,
                    type(e).__name__,
                    wait,
                )
                sleep(wait)
            except self.sdk_error as e:
                error = e
                break
        record["duration_ms"] = int((time.monotonic() - started) * 1000)
        if response is None:
            name = type(error).__name__
            record_usage(self.usage_log, {**record, "status": "failed", "error": name})
            raise ProviderError(
                f"bill {bill_id[:12]}: {record['purpose']} failed after "
                f"{record['attempts']} attempts ({name})",
                (self._usage_record(record),),
            )
        return response

    def _account(self, record: dict, input_tokens: int | None, output_tokens: int | None) -> None:
        record["input_tokens"] = int(input_tokens or 0)
        record["output_tokens"] = int(output_tokens or 0)
        record["cost_usd"] = str(
            cost(self.model_spec, record["input_tokens"], record["output_tokens"])
        )

    def _finish(
        self, record: dict, bill_id: str, text: str, parse: Callable[[Any], ModelReading]
    ) -> ModelReading:
        """The answer parsed into a ModelReading, with the `ok` usage record attached; an
        answer that is not the expected JSON writes an `unparseable` record and raises
        without echoing it."""
        try:
            reading = parse(load_json(text))
        except ValueError:
            record_usage(self.usage_log, {**record, "status": "unparseable"})
            raise ProviderError(
                f"bill {bill_id[:12]}: {record['purpose']} answer was not the expected JSON",
                (self._usage_record(record),),
            ) from None
        reading.usage = [self._usage_record(record)]
        record_usage(
            self.usage_log,
            {
                **record,
                "status": "ok",
                "fields_returned": len(reading.fields),
                "meters_returned": len(reading.meters),
                "lines_returned": len(reading.lines),
            },
        )
        log.info(
            "%s bill=%s fields=%d meters=%d lines=%d",
            record["purpose"],
            bill_id[:12],
            len(reading.fields),
            len(reading.meters),
            len(reading.lines),
        )
        return reading

    def _reading(self, prompt_version: str) -> ModelReading:
        return ModelReading(
            reader_name=self.reader_name,
            family=self.family,
            model_spec=self.model_spec,
            model_id=self.model_id,
            prompt_version=prompt_version,
        )


# factories --------------------------------------------------------------------------------


def model_a_spec() -> str:
    return setting("BILLX_MODEL_A") or load_config("providers.yaml")["model_a"]


def model_b_spec() -> str:
    return setting("BILLX_MODEL_B") or load_config("providers.yaml")["model_b"]


def default_usage_log() -> Path:
    """Where the engine's own calls are recorded when no workspace log is given."""
    return data_dir() / "usage" / "providers.jsonl"


def make_prefill_provider(usage_log: Path) -> Provider | None:
    """Model A's provider for the studio pre-fill, or None when no key is configured (the
    studio then works with an empty pre-fill)."""
    return make_model_a(usage_log)


def make_model_a(usage_log: Path | None = None):
    """Model A (family `openai`) from `BILLX_MODEL_A` or `config/providers.yaml` and the key
    `BILLX_OPENAI_API_KEY`; None when the key is missing or the spec is not an OpenAI model.
    The key is handed to the SDK client and held nowhere else."""
    spec = model_a_spec()
    family, _, model_id = spec.partition(":")
    if family != "openai" or not model_id:
        return None
    key = setting("BILLX_OPENAI_API_KEY")
    if not key:
        return None
    from billx.reader.providers.openai_reader import OpenAIReader

    return OpenAIReader(spec, key, usage_log=usage_log or default_usage_log())


def make_model_b(usage_log: Path | None = None):
    """Model B (family `anthropic`) from `BILLX_MODEL_B` or `config/providers.yaml` and the
    key `BILLX_ANTHROPIC_API_KEY`; None when the key is missing or the spec is not an
    Anthropic model."""
    spec = model_b_spec()
    family, _, model_id = spec.partition(":")
    if family != "anthropic" or not model_id:
        return None
    key = setting("BILLX_ANTHROPIC_API_KEY")
    if not key:
        return None
    from billx.reader.providers.anthropic_reader import AnthropicReader

    return AnthropicReader(spec, key, usage_log=usage_log or default_usage_log())


def make_model_c(usage_log: Path | None = None):
    """The third, whole-bill reader (LlamaParse, family `llamaindex`) from
    `LLAMA_CLOUD_API_KEY`; None when the key is missing."""
    from billx.reader.providers.llamaparse_reader import make_llamaparse

    return make_llamaparse(usage_log)
