"""Explanations (Stage 7): two to four plain sentences about a waterfall or a binding constraint,
drafted by the model through providers/ from the SourcedValues only (prompt explain_v1), cached by
input, and shown as "explanation" beside the sourced numbers — never instead of them."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from ..core.settings import get_settings
from ..db.models import Explanation
from ..providers import openai_client

PROMPT = ("explain", 1)


def _lines(values: list[dict[str, Any]], titles: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for v in values:
        refs = []
        for r in v.get("source_refs") or []:
            refs.append(
                {
                    k: x
                    for k, x in {
                        "kind": r.get("kind"),
                        "document": titles.get(r.get("document_id") or ""),
                        "page": r.get("page"),
                        "quote": (r.get("quote") or "")[:240] or None,
                        "note": r.get("note"),
                    }.items()
                    if x
                }
            )
        out.append(
            {"label": v.get("label"), "value": v.get("value"), "unit": v.get("unit"), "sources": refs[:4]}
        )
    return out


def explain(s: Session, title: str, values: list[dict[str, Any]], titles: dict[str, str]) -> dict[str, Any]:
    payload = json.dumps({"title": title, "lines": _lines(values, titles)}, sort_keys=True, default=str)
    key = hashlib.sha256(f"{PROMPT[0]}_v{PROMPT[1]}\n{payload}".encode()).hexdigest()
    hit = s.get(Explanation, key)
    if hit is not None:
        return {"text": hit.text, "prompt": hit.prompt, "cached": True}
    r = openai_client.call_json(
        prompt_name=PROMPT[0],
        prompt_version=PROMPT[1],
        purpose="explanation",
        user=payload,
        model=get_settings().openai_model_explain,
    )
    text = str(r.data.get("text") or "").strip()
    if not text:
        raise openai_client.ProviderError("the model returned no explanation")
    s.add(Explanation(key=key, prompt=r.prompt, text=text, model_call_id=r.call_id))
    s.flush()
    return {"text": text, "prompt": r.prompt, "cached": False}
