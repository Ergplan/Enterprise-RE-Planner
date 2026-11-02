"""Model B (family `anthropic`) through the Anthropic Messages API with image blocks.

Model B is the independent second family (5.1): it reads the guaranteed fields from each
whole page plus three overlapping horizontal bands of it (`read_fields`, 5.3 step 5), and
re-reads named printed lines on request (`read_lines`, 5.3 step 6). It is never shown any
other reader's value: a prompt lists field paths and types, or line labels and section
headings, and nothing else. Callers pass line dicts that may carry other readers' figures;
only `label` and `group` ever reach the prompt.

Every call: a worst-case cost estimate first (refused above the caller's budget or the
per-call ceiling without any request), a timeout, bounded retries through the SDK client
with `max_retries=0` (on HTTP 429 wait `rate_limit_wait_seconds`, then back off), and one
usage record after it. Nothing here logs or raises a bill value or the key.
"""

from __future__ import annotations

import base64
import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import anthropic

from billx.reader.providers.base import (
    BaseReader,
    BillKind,
    ModelReading,
    Page,
    ProviderError,
    parse_fields,
    parse_items,
    render_prompt,
    render_template,
)
from billx.reader.providers.images import BAND_COUNT, bands, downscale

log = logging.getLogger(__name__)

_sleep = time.sleep  # tests replace this; nothing else does

#: The keys of a line that the re-read prompt may show: what the line is, never its figures.
LINE_PROMPT_KEYS = ("group", "label")
LINE_ANSWER_KEYS = ("group", "label", "quantity", "rate", "unit", "amount")


def _wait(seconds: float) -> None:
    _sleep(seconds)


def line_lines(lines: list[dict]) -> str:
    """The lines to re-read as the prompt shows them: `heading | label` per line, from
    `LINE_PROMPT_KEYS` only, so no quantity, rate or amount from any reader is ever sent."""
    out = []
    for ln in lines:
        group = ln.get("group") or "(no heading)"
        out.append(f"- {group} | {ln['label']}")
    return "\n".join(out)


class AnthropicReader(BaseReader):
    family = "anthropic"
    reader_name = "model_b"
    provider_name = "anthropic"
    read_fields_prompt = "read_fields_v4"
    read_lines_prompt = "read_lines_v1"
    retryable = (
        anthropic.RateLimitError,
        anthropic.APIConnectionError,
        anthropic.InternalServerError,
        anthropic.OverloadedError,
    )
    rate_limited = anthropic.RateLimitError
    sdk_error = anthropic.AnthropicError

    def __init__(self, model_spec: str, api_key: str, *, usage_log: Path, http_client=None):
        super().__init__(model_spec, usage_log=usage_log)
        self._client = anthropic.Anthropic(
            api_key=api_key,
            max_retries=0,  # retries are ours, so a 429 waits as rule 14 says
            timeout=self.cfg["timeout_seconds"],
            http_client=http_client,
        )

    # request building ---------------------------------------------------------------------

    @staticmethod
    def _image_block(page: Page) -> dict[str, Any]:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": page.mime,
                "data": base64.b64encode(page.data).decode("ascii"),
            },
        }

    def _images(self, pages: list[Page]) -> list[dict[str, Any]]:
        """For each page (downscaled to the config's longest side): the whole page, then its
        top, middle and bottom bands, each preceded by a one-line caption."""
        blocks: list[dict[str, Any]] = []
        for i, p in enumerate(pages):
            page = downscale(p, self.max_image_edge_px)
            blocks.append({"type": "text", "text": f"Page {i + 1}, whole page:"})
            blocks.append(self._image_block(page))
            for band in bands(page, i):
                blocks.append({"type": "text", "text": f"Page {i + 1}, {band.position} band:"})
                blocks.append(self._image_block(band.page))
        return blocks

    def _request(self, prompt: str, pages: list[Page]) -> dict[str, Any]:
        content = self._images(pages) + [{"type": "text", "text": prompt}]
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": self.max_output_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        temperature = self.temperature()
        if temperature is not None:
            # the SDK no longer has the parameter; a model configured with one gets it raw
            kwargs["extra_body"] = {"temperature": temperature}
        return kwargs

    def _create(self, kwargs: dict[str, Any]):
        return self._client.messages.create(**kwargs)

    @staticmethod
    def _answer_text(response: Any) -> str:
        return "".join(b.text for b in response.content if getattr(b, "type", "") == "text")

    def _read(
        self,
        pages: list[Page],
        *,
        purpose: str,
        prompt_version: str,
        prompt: str,
        bill_id: str,
        max_cost_usd: Decimal,
        parse,
    ) -> ModelReading:
        try:
            kwargs = self._request(prompt, pages)  # before the plan: no call, no record
        except ValueError:
            raise ProviderError(f"bill {bill_id[:12]}: a page is not a decodable image") from None
        record = self._plan(
            purpose=purpose,
            prompt_version=prompt_version,
            bill_id=bill_id,
            prompt=prompt,
            images=len(pages) * (1 + BAND_COUNT),
            pages=len(pages),
            max_cost_usd=max_cost_usd,
        )
        response = self._call(record, bill_id, lambda: self._create(kwargs), _wait)
        if response.usage is not None:
            self._account(record, response.usage.input_tokens, response.usage.output_tokens)
        return self._finish(record, bill_id, self._answer_text(response), parse)

    # the two readings ---------------------------------------------------------------------

    def read_fields(
        self,
        pages: list[Page],
        *,
        bill_kind: BillKind,
        fields: list[dict],
        bill_id: str,
        max_cost_usd: Decimal,
        hints: tuple[str, ...] = (),
    ) -> ModelReading:
        """The guaranteed `fields` (path, type, unit; never a value) from each page and its
        three bands, each value as printed. `hints` are the profile's layout notes. Raises
        BudgetExceeded (no request) when the worst-case cost is above `max_cost_usd`,
        ProviderError on failure or a non-JSON answer; the usage record travels on the
        exception."""
        prompt = render_prompt(self.read_fields_prompt, fields, bill_kind, hints)

        def parse(obj: Any) -> ModelReading:
            reading = self._reading(self.read_fields_prompt)
            reading.fields = parse_fields(obj, fields)
            return reading

        return self._read(
            pages,
            purpose="read_fields",
            prompt_version=self.read_fields_prompt,
            prompt=prompt,
            bill_id=bill_id,
            max_cost_usd=max_cost_usd,
            parse=parse,
        )

    def read_lines(
        self,
        pages: list[Page],
        *,
        lines: list[dict],
        bill_id: str,
        max_cost_usd: Decimal,
    ) -> ModelReading:
        """The quantity, rate, unit and amount printed on each of `lines`, found on the page
        by `label` and `group` (the only keys of a line that reach the prompt). The answer's
        lines carry those keys and the figures as printed; a line the model could not find
        has no amount and is dropped."""
        prompt = render_template(self.read_lines_prompt, LINES=line_lines(lines))

        def parse(obj: Any) -> ModelReading:
            if not isinstance(obj, dict):
                raise ValueError("not an object")
            reading = self._reading(self.read_lines_prompt)
            reading.lines = parse_items(
                obj.get("lines"), LINE_ANSWER_KEYS, required=("label", "amount")
            )
            return reading

        return self._read(
            pages,
            purpose="read_lines",
            prompt_version=self.read_lines_prompt,
            prompt=prompt,
            bill_id=bill_id,
            max_cost_usd=max_cost_usd,
            parse=parse,
        )
