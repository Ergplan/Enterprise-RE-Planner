"""Model A (family `openai`) through the OpenAI Responses API with JSON-object output.

Two calls: `prefill` (the studio's pre-fill of the guaranteed fields, Stage 0) and
`read_bill` (5.3 step 3: the whole bill, guaranteed fields, meter rows and every printed
line with an amount, as `ModelReading`). Both transcribe only (rule 6): every value is the
string printed on the page, numbers kept as literal text.

Every call: a worst-case cost estimate first (refused above the caller's budget or the
per-call ceiling without any request), a timeout, bounded retries (on HTTP 429 wait
`rate_limit_wait_seconds`, then back off), and one usage record after it, written whether
the call succeeded or not. Nothing here logs or raises a bill value or the key.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import openai

from billx.reader.providers.base import (
    METER_KEYS,
    BaseReader,
    BillKind,
    ModelReading,
    Page,
    ProviderError,
    parse_fields,
    parse_items,
    parse_lines,
    parse_notes,
    render_prompt,
)
from billx.reader.providers.images import downscale
from billx.reader.providers.usage import cost, estimate_tokens, record_usage

log = logging.getLogger(__name__)

_sleep = time.sleep  # tests replace this; nothing else does


def _wait(seconds: float) -> None:
    _sleep(seconds)


class OpenAIReader(BaseReader):
    family = "openai"
    reader_name = "model_a"
    provider_name = "openai"
    prompt_version = "prefill_v1"  # the studio pre-fill's prompt (Provider protocol)
    read_bill_prompt = "read_bill_v5"
    retryable = (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError)
    rate_limited = openai.RateLimitError
    sdk_error = openai.OpenAIError

    def __init__(self, model_spec: str, api_key: str, *, usage_log: Path, http_client=None):
        super().__init__(model_spec, usage_log=usage_log)
        self._client = openai.OpenAI(
            api_key=api_key,
            max_retries=0,  # retries are ours, so a 429 waits as rule 14 says
            timeout=self.cfg["timeout_seconds"],
            http_client=http_client,
        )

    # request building ---------------------------------------------------------------------

    def _request(self, prompt: str, pages: list[Page]) -> dict[str, Any]:
        """The Responses API request: the prompt, then every page (downscaled to the config's
        longest side) as a data URL, JSON-object output, the configured temperature if any."""
        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        for p in pages:
            page = downscale(p, self.max_image_edge_px)
            data = base64.b64encode(page.data).decode("ascii")
            content.append({"type": "input_image", "image_url": f"data:{page.mime};base64,{data}"})
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": self.max_output_tokens,
            "text": {"format": {"type": "json_object"}},
        }
        temperature = self.temperature()
        if temperature is not None:
            kwargs["temperature"] = temperature
        return kwargs

    def _create(self, kwargs: dict[str, Any]):
        return self._client.responses.create(**kwargs)

    # the studio pre-fill (Stage 0) --------------------------------------------------------

    def prefill(
        self, pages: list[Page], fields: list[dict], *, bill_kind: str, bill_id: str
    ) -> dict[str, str]:
        """The guaranteed fields as printed strings for the studio's pre-fill. Bounded by the
        per-call ceiling only (the studio has no per-bill budget)."""
        prompt = render_prompt(self.prompt_version, fields, bill_kind)
        estimate = cost(
            self.model_spec, estimate_tokens(prompt, len(pages)), self.max_output_tokens
        )
        record = self._skeleton(
            purpose="studio_prefill",
            prompt_version=self.prompt_version,
            bill_id=bill_id,
            pages=len(pages),
            images=len(pages),
        )
        record["cost_estimate_usd"] = str(estimate)
        if estimate > Decimal(str(self.cfg["max_cost_usd_per_call"])):
            record_usage(self.usage_log, {**record, "status": "refused_over_ceiling"})
            raise ProviderError(
                f"bill {bill_id[:12]}: estimate above the per-call ceiling",
                (self._usage_record(record),),
            )
        kwargs = self._request(prompt, pages)
        response = self._call(record, bill_id, lambda: self._create(kwargs), _wait)
        if response.usage is not None:
            self._account(record, response.usage.input_tokens, response.usage.output_tokens)
        try:
            values = parse_values(response.output_text, fields)
        except ValueError:
            record_usage(self.usage_log, {**record, "status": "unparseable"})
            raise ProviderError(
                f"bill {bill_id[:12]}: model answer was not a JSON object",
                (self._usage_record(record),),
            ) from None
        record_usage(self.usage_log, {**record, "status": "ok", "fields_returned": len(values)})
        log.info("prefill bill=%s fields=%d", bill_id[:12], len(values))
        return values

    # the whole-bill reading (5.3 step 3) --------------------------------------------------

    def read_bill(
        self,
        pages: list[Page],
        *,
        bill_kind: BillKind,
        fields: list[dict],
        bill_id: str,
        max_cost_usd: Decimal,
        hints: tuple[str, ...] = (),
    ) -> ModelReading:
        """The whole bill in one call: the guaranteed `fields` (path, type, unit; never a
        value), every meter-table row and every printed line with an amount, each value as
        printed. `hints` are the profile's layout notes. Raises BudgetExceeded (no request)
        when the worst-case cost is above `max_cost_usd`, ProviderError on failure or a
        non-JSON answer; the usage record travels on the exception."""
        prompt = render_prompt(self.read_bill_prompt, fields, bill_kind, hints)
        record = self._plan(
            purpose="read_bill",
            prompt_version=self.read_bill_prompt,
            bill_id=bill_id,
            prompt=prompt,
            images=len(pages),
            pages=len(pages),
            max_cost_usd=max_cost_usd,
        )
        kwargs = self._request(prompt, pages)
        response = self._call(record, bill_id, lambda: self._create(kwargs), _wait)
        if response.usage is not None:
            self._account(record, response.usage.input_tokens, response.usage.output_tokens)

        def parse(obj: Any) -> ModelReading:
            if not isinstance(obj, dict):
                raise ValueError("not an object")
            reading = self._reading(self.read_bill_prompt)
            reading.fields = parse_fields(obj.get("fields", {}), fields)
            reading.meters = parse_items(obj.get("meters"), METER_KEYS, required=("register",))
            reading.lines = parse_lines(obj.get("lines"))
            reading.extraction_notes = parse_notes(obj.get("extraction_notes"))
            return reading

        return self._finish(record, bill_id, response.output_text, parse)


def parse_values(text: str, fields: list[dict]) -> dict[str, str]:
    """Keep known paths with non-empty printed strings. A JSON number is kept as its literal
    text (never parsed to float); null, booleans and unknown keys are dropped."""
    raw = json.loads(text, parse_float=str, parse_int=str)
    return parse_fields(raw, fields)
