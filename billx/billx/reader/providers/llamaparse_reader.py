"""The `llamaparse` reader (family `llamaindex`): LlamaParse's extraction (LlamaExtract v2).

The bill's own pages are sent as one PDF to LlamaIndex's cloud with a JSON schema of the
guaranteed fields, the meter rows and the printed lines, every value a string as printed, and
the transcription rules as the system prompt (`prompts/llamaparse_extract_v1.md`). LlamaExtract
parses the pages itself and finds every value by its meaning, so it is a model reader of its
own family: it verifies a value with a local reader or with a model of another family, never
alone. Its citations give each field's page and box, which the other model readers lack.

Like the other model readers it runs only when the caller allows cloud models, makes no
request when its worst-case cost is above what is left of the budget, retries a 429 or a
connection error within bounds, and writes one usage record per call (credits converted to US
dollars at the configured rate). Nothing here logs a value or the key.
"""

from __future__ import annotations

import io
import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from billx.core.schema import Region
from billx.reader.providers.base import (
    LINE_KEYS,
    METER_KEYS,
    BaseReader,
    BillKind,
    BudgetExceeded,
    ModelReading,
    Page,
    ProviderError,
    parse_items,
    parse_lines,
    render_prompt,
)
from billx.reader.providers.usage import record_usage
from billx.reader.read.words import frac

log = logging.getLogger(__name__)

PROMPT = "llamaparse_extract_v1"
DEFAULT_BASE_URL = "https://api.cloud.llamaindex.ai"
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}

_sleep = time.sleep  # tests replace this


def _wait(seconds: float) -> None:
    _sleep(seconds)


class _Retryable(Exception):
    pass


class _RateLimited(_Retryable):
    pass


class _Failed(Exception):
    pass


class LlamaUnauthorized(_Failed):
    """401 or 403: the key is not accepted (wrong key, or another region's)."""


class LlamaRequestRefused(_Failed):
    """Any other 4xx: the request was refused (its body is not logged)."""


class LlamaParseReader(BaseReader):
    family = "llamaindex"
    reader_name = "llamaparse"  # type: ignore[assignment]
    provider_name = "llamaindex"
    prompt_version = PROMPT
    reads_whole_bill = True  # it reads fields, meters and lines whatever is still unsettled
    retryable = (_Retryable,)
    rate_limited = _RateLimited
    sdk_error = _Failed

    def __init__(
        self,
        api_key: str,
        *,
        usage_log: Path,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.Client | None = None,
    ):
        super().__init__("llamaindex:extract-agentic", usage_log=usage_log)
        self.llama = dict(self.cfg.get("llamaparse") or {})
        self.tier = str(self.llama.get("tier", "agentic"))
        self.model_spec = f"llamaindex:extract-{self.tier}"
        self.model_id = f"extract-{self.tier}"
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=float(self.cfg["timeout_seconds"]))

    # cost -------------------------------------------------------------------------------

    def _usd_per_credit(self) -> Decimal:
        return Decimal(str(self.llama.get("usd_per_credit", "0.00125")))

    def worst_case_usd(self, pages: int) -> Decimal:
        credits = Decimal(str(self.llama.get("worst_case_credits_per_page", "60"))) * pages
        return (credits * self._usd_per_credit()).quantize(Decimal("0.000001"))

    # http -------------------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}", "Accept": "application/json"}

    def _send(self, method: str, path: str, **kwargs) -> dict:
        try:
            r = self._client.request(method, self._base + path, headers=self._headers(), **kwargs)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            raise _Retryable(type(e).__name__) from None
        if r.status_code == 429:
            raise _RateLimited("429")
        if r.status_code >= 500:
            raise _Retryable(str(r.status_code))
        if r.status_code in (401, 403):
            raise LlamaUnauthorized(str(r.status_code))
        if r.status_code >= 400:
            raise LlamaRequestRefused(str(r.status_code))
        try:
            body = r.json()
        except ValueError:
            raise _Failed("not json") from None
        if not isinstance(body, dict):
            raise _Failed("not an object")
        return body

    # the reading ------------------------------------------------------------------------

    def read_fields(
        self,
        pages: list[Page],
        *,
        bill_kind: BillKind,
        fields: list[dict],
        bill_id: str,
        max_cost_usd: Decimal,
        hints: tuple[str, ...] = (),
        page_numbers: tuple[int, ...] | None = None,
    ) -> ModelReading:
        """The whole bill (fields, meters, lines), whichever fields the pipeline still needs:
        LlamaExtract reads the document once, so asking for fewer fields saves nothing and
        would leave the meter rows to one reader."""
        return self.read_bill(
            pages,
            bill_kind=bill_kind,
            fields=fields,
            bill_id=bill_id,
            max_cost_usd=max_cost_usd,
            hints=hints,
            page_numbers=page_numbers,
        )

    def read_bill(
        self,
        pages: list[Page],
        *,
        bill_kind: BillKind,
        fields: list[dict],
        bill_id: str,
        max_cost_usd: Decimal,
        hints: tuple[str, ...] = (),
        page_numbers: tuple[int, ...] | None = None,
    ) -> ModelReading:
        """`page_numbers` are the pages' own numbers (0-based) in the file, so citations name
        the right page of a multi-bill file."""
        prompt = render_prompt(PROMPT, fields, bill_kind, hints)
        estimate = self.worst_case_usd(len(pages))
        record = self._skeleton(
            purpose="read_bill",
            prompt_version=PROMPT,
            bill_id=bill_id,
            pages=len(pages),
            images=len(pages),
        )
        record["cost_estimate_usd"] = str(estimate)
        record["max_cost_usd"] = str(max_cost_usd)
        if estimate > max_cost_usd:
            record_usage(self.usage_log, {**record, "status": "refused", "reason": "budget"})
            raise BudgetExceeded(
                f"bill {bill_id[:12]}: llamaparse estimate above the remaining budget",
                (self._usage_record(record),),
            )
        if estimate > Decimal(str(self.cfg["max_cost_usd_per_call"])):
            record_usage(self.usage_log, {**record, "status": "refused", "reason": "ceiling"})
            raise ProviderError(
                f"bill {bill_id[:12]}: llamaparse estimate above the per-call ceiling",
                (self._usage_record(record),),
            )
        pdf = pages_pdf(pages, self.max_image_edge_px)
        configuration = {
            "tier": self.tier,
            "version": str(self.llama.get("version", "latest")),
            "extraction_target": "per_doc",
            "data_schema": data_schema(fields),
            "cite_sources": True,
            "confidence_scores": False,
            "system_prompt": prompt,
        }

        def run() -> dict:
            upload = self._send(
                "POST",
                "/api/v1/beta/files",
                files={"file": (f"{bill_id[:12]}.pdf", pdf, "application/pdf")},
                data={"purpose": "extract"},
            )
            file_id = upload.get("id")
            if not file_id:
                raise _Failed("no file id")
            job = self._send(
                "POST",
                "/api/v2/extract",
                json={"file_input": file_id, "configuration": configuration},
            )
            job_id = job.get("id")
            if not job_id:
                raise _Failed("no job id")
            return self._poll(str(job_id))

        body = self._call(record, bill_id, run, _wait)
        credits = _credits(body.get("usage"))
        record["credits"] = str(credits)
        record["cost_usd"] = str((credits * self._usd_per_credit()).quantize(Decimal("0.000001")))
        status = body.get("status")
        if status != "COMPLETED":
            record_usage(self.usage_log, {**record, "status": "failed", "error": str(status)})
            raise ProviderError(
                f"bill {bill_id[:12]}: llamaparse job ended {status}",
                (self._usage_record(record),),
            )
        result = body.get("extract_result")
        metadata = ((body.get("extract_metadata") or {}).get("field_metadata") or {}).get(
            "document_metadata"
        ) or {}

        def parse(obj: Any) -> ModelReading:
            if not isinstance(obj, dict):
                raise ValueError("not an object")
            reading = self._reading(PROMPT)
            reading.fields = flatten_fields(obj.get("fields"), fields)
            reading.meters = parse_items(obj.get("meters"), METER_KEYS, required=("register",))
            reading.lines = parse_lines(obj.get("lines"))
            reading.citations = citations(metadata.get("fields"), fields, page_numbers)
            return reading

        return self._finish(record, bill_id, result, parse)

    def _poll(self, job_id: str) -> dict:
        deadline = time.monotonic() + float(self.cfg["timeout_seconds"])
        every = float(self.llama.get("poll_seconds", 3))
        while True:
            body = self._send(
                "GET",
                f"/api/v2/extract/{job_id}",
                params=[("expand", "extract_metadata"), ("expand", "usage")],
            )
            if str(body.get("status")) in TERMINAL:
                return body
            if time.monotonic() > deadline:
                raise _Retryable("poll timeout")
            _wait(every)

    def _finish(self, record, bill_id, result, parse):  # type: ignore[override]
        """As the base class, from an already-decoded JSON object."""
        try:
            reading = parse(result)
        except ValueError:
            record_usage(self.usage_log, {**record, "status": "unparseable"})
            raise ProviderError(
                f"bill {bill_id[:12]}: llamaparse answer was not the expected JSON",
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
            "llamaparse bill=%s fields=%d meters=%d lines=%d",
            bill_id[:12],
            len(reading.fields),
            len(reading.meters),
            len(reading.lines),
        )
        return reading


# schema and parsing ------------------------------------------------------------------------


def _nest(paths: list[tuple[str, str]]) -> dict:
    """{"energy.kwh": description} as nested JSON-schema objects of strings."""
    root: dict[str, Any] = {"type": "object", "properties": {}}
    for path, description in paths:
        node = root
        parts = path.split(".")
        for part in parts[:-1]:
            node = node["properties"].setdefault(part, {"type": "object", "properties": {}})
        node["properties"][parts[-1]] = {"type": "string", "description": description}
    return root


def data_schema(fields: list[dict]) -> dict:
    """The JSON schema LlamaExtract fills: fields as nested objects of strings, meter rows and
    printed lines as arrays of objects of strings."""
    described = [
        (
            f["path"],
            (f.get("description") or f["path"]) + (f" ({f['unit']})" if f.get("unit") else ""),
        )
        for f in fields
    ]
    row = {"type": "object", "properties": {k: {"type": "string"} for k in METER_KEYS}}
    line = {"type": "object", "properties": {k: {"type": "string"} for k in LINE_KEYS}}
    return {
        "type": "object",
        "properties": {
            "fields": _nest(described),
            "meters": {"type": "array", "items": row},
            "lines": {"type": "array", "items": line},
        },
    }


def flatten_fields(obj: Any, fields: list[dict]) -> dict[str, str]:
    """The nested `fields` object back to {path: printed text}, known paths only."""
    out: dict[str, str] = {}
    if not isinstance(obj, dict):
        return out
    for f in fields:
        node: Any = obj
        for part in f["path"].split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if isinstance(node, (int, float)) and not isinstance(node, bool):
            node = str(node)
        if isinstance(node, str) and node.strip():
            out[f["path"]] = node.strip()
    return out


def citations(
    meta: Any, fields: list[dict], page_numbers: tuple[int, ...] | None
) -> dict[str, tuple[int | None, Region | None]]:
    """Each field's (page, region) from LlamaExtract's first citation: the page in the file
    (0-based) and the box as fractions of the page."""
    out: dict[str, tuple[int | None, Region | None]] = {}
    if not isinstance(meta, dict):
        return out
    for f in fields:
        node: Any = meta
        for part in f["path"].split("."):
            node = node.get(part) if isinstance(node, dict) else None
        cites = node.get("citation") if isinstance(node, dict) else None
        if not isinstance(cites, list) or not cites or not isinstance(cites[0], dict):
            continue
        c = cites[0]
        page = c.get("page")
        index = None
        if isinstance(page, int) and page >= 1:
            index = (
                page_numbers[page - 1] if page_numbers and page <= len(page_numbers) else page - 1
            )
        out[f["path"]] = (index, _region(c))
    return out


def _region(citation: dict) -> Region | None:
    boxes = citation.get("bounding_boxes") or []
    dims = citation.get("page_dimensions") or {}
    try:
        width, height = float(dims["width"]), float(dims["height"])
        box = boxes[0]
        x, y, w, h = (float(box[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    if max(x + w, y + h) <= 1.0001:  # already fractions
        width = height = 1.0
    return Region(x=frac(x, width), y=frac(y, height), w=frac(w, width), h=frac(h, height))


def _credits(usage: Any) -> Decimal:
    if not isinstance(usage, dict):
        return Decimal(0)
    for key in ("credits", "total_credits"):
        value = usage.get(key)
        if value is not None:
            try:
                return Decimal(str(value))
            except ArithmeticError:
                return Decimal(0)
    return Decimal(0)


def pages_pdf(pages: list[Page], max_edge: int) -> bytes:
    """The bill's page images as one PDF (only this bill's pages leave the machine)."""
    from PIL import Image

    from billx.reader.providers.images import downscale

    images = []
    for p in pages:
        small = downscale(p, max_edge)
        images.append(Image.open(io.BytesIO(small.data)).convert("RGB"))
    buf = io.BytesIO()
    images[0].save(buf, format="PDF", save_all=True, append_images=images[1:], resolution=150)
    return buf.getvalue()


def make_llamaparse(usage_log: Path | None = None) -> LlamaParseReader | None:
    """The LlamaParse reader from `LLAMA_CLOUD_API_KEY` (and `BILLX_LLAMA_BASE_URL` for
    another region), or None when no key is configured. The key is handed to the client
    and held nowhere else."""
    from billx.core.settings import setting
    from billx.reader.providers.base import default_usage_log

    key = setting("LLAMA_CLOUD_API_KEY")
    if not key:
        return None
    return LlamaParseReader(
        key,
        usage_log=usage_log or default_usage_log(),
        base_url=setting("BILLX_LLAMA_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL,
    )
