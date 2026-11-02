"""The document-type gate (build prompt 5.0): what a page group is, from local signals only.

Every page's words are scored against the `document_signals` patterns in
profiles/_common.yaml; the type with the highest weighted score wins, and a score below
`min_score` is `type_unclear` (reported as `not_a_bill` with that note unless a model is
allowed to confirm; the pipeline decides that). Nothing here reads a value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from billx.core.schema import DocumentType

_COMMON = Path(__file__).resolve().parents[3] / "profiles" / "_common.yaml"

TYPES: tuple[DocumentType, ...] = (
    "electricity_bill",
    "gas_bill",
    "water_bill",
    "telecom_bill",
    "other_invoice",
    "not_a_bill",
)


@dataclass(frozen=True)
class Verdict:
    document_type: DocumentType
    score: int
    scores: dict[str, int]
    unclear: bool  # best score below the floor: `type_unclear`


@lru_cache(maxsize=1)
def _signals() -> tuple[int, dict[str, list[tuple[re.Pattern[str], int]]]]:
    cfg = yaml.safe_load(_COMMON.read_text(encoding="utf-8"))["document_signals"]
    compiled = {
        t: [(re.compile(s["pattern"], re.I), int(s["weight"])) for s in cfg.get(t, [])]
        for t in TYPES
    }
    return int(cfg["min_score"]), compiled


def classify(text: str) -> Verdict:
    """The type of one page (or page group) from its text."""
    floor, signals = _signals()
    scores: dict[str, int] = {}
    for doc_type, patterns in signals.items():
        scores[doc_type] = sum(w for pat, w in patterns if pat.search(text))
    best = max(TYPES, key=lambda t: (scores[t], -TYPES.index(t)))
    score = scores[best]
    if score < floor:
        return Verdict("not_a_bill", score, scores, unclear=True)
    return Verdict(best, score, scores, unclear=False)


def classify_pages(page_texts: list[str]) -> list[Verdict]:
    return [classify(t) for t in page_texts]
