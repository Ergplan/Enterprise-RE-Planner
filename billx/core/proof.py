"""The verification rule (build prompt 5.2): `decide` is the only code that turns evidence
into a verification, and the only code that says which value a field carries.

It lives in core because the core schema's model validator calls it, and core imports
nothing from the engines (section 9); `billx.reader.validate.proof` re-exports it so the
prompt's path resolves. The one-rule test asserts that no other module assigns a
verification.

Readings are compared on their normalised strings. Two readings are independent when
their readers differ in method, or both are vision models of different families; a reader
never counts as agreeing with itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PROOF_RULE_VERSION = "3"  # 2: two local readers never verify each other; 3: docling, llamaparse

Reader = Literal["text_layer", "local_ocr", "docling", "model_a", "model_b", "llamaparse", "human"]
Method = Literal["text_layer", "ocr", "layout", "vision", "human"]
Verification = Literal["unverified", "verified", "disputed", "confirmed"]
ProofLevel = Literal["exact", "consensus", "arithmetic", "confirmed", "single"]
Source = Literal["template", "ocr", "model"]

_SOURCE_OF: dict[str, Source] = {
    "text_layer": "ocr",
    "local_ocr": "ocr",
    "docling": "ocr",
    "model_a": "model",
    "llamaparse": "model",
    "model_b": "model",
    "human": "model",  # never returned: a confirmed value's source is the reading it confirms
}
_SOURCE_ORDER = {"template": 0, "ocr": 1, "model": 2}


@dataclass(frozen=True)
class ReadingView:
    """What decide needs to know about one reading (the schema's Reading provides it)."""

    reader: str
    method: str
    family: str | None
    normalised: str | None  # None: the reader produced text it could not normalise
    exact: bool = False  # a genuine text-layer reading inside an anchored region (deferred)
    confirmed_by: str | None = None


@dataclass(frozen=True)
class Decision:
    verification: Verification
    value: str | None  # the normalised value the field carries
    proof: tuple[ProofLevel, ...]
    readers: tuple[str, ...]  # the readers that agree with `value`
    source: Source | None


LOCAL_METHODS = frozenset({"text_layer", "ocr", "layout"})


def independent(a: ReadingView, b: ReadingView) -> bool:
    """Two readings are independent when they could not share a mistake: they differ in how
    they FIND the field, not only in how they read its characters. The PDF text layer and
    local OCR read characters independently but find a field by the same label rule, so on
    a layout where that rule picks a neighbouring label they agree on the same wrong text
    (seen on real bills, 23 Oct 2026). Two local readers are therefore never independent of
    each other; a local reader and a model are; two models are when their families differ."""
    if a.reader == b.reader:
        return False
    if a.method in LOCAL_METHODS and b.method in LOCAL_METHODS:
        return False
    if a.method != b.method:
        return True
    if a.method == "vision":
        return a.family is not None and b.family is not None and a.family != b.family
    return False


def decide(
    readings: tuple[ReadingView, ...], passing_equality_checks: tuple[str, ...] = ()
) -> Decision:
    """The rule of 5.2, applied to a field's evidence.

    - a named person's confirmation: `confirmed`, with the confirmed value;
    - two independent readings with the same normalised value: `verified` (consensus);
    - an exact reading, with arithmetic for a number (the caller passes the passing
      equality checks it took part in): `verified`;
    - readings that exist but never agree: `disputed`;
    - one reading: `unverified`;
    - no reading: `unverified` with no value.
    """
    confirmed = [r for r in readings if r.reader == "human" and r.confirmed_by]
    if confirmed:
        c = confirmed[-1]
        agreeing = [
            r.reader for r in readings if r.normalised == c.normalised and r.reader != "human"
        ]
        return Decision(
            "confirmed", c.normalised, ("confirmed",), ("human", *agreeing), _source(agreeing)
        )

    machine = [r for r in readings if r.reader != "human"]
    if not machine:
        return Decision("unverified", None, (), (), None)

    # Consensus: the first pair of independent readings (in reading order) that agree.
    for i, a in enumerate(machine):
        if a.normalised is None:
            continue
        for b in machine[i + 1 :]:
            if b.normalised == a.normalised and independent(a, b):
                agreeing = tuple(r.reader for r in machine if r.normalised == a.normalised)
                proof: tuple[ProofLevel, ...] = ("consensus",)
                if passing_equality_checks:
                    proof += ("arithmetic",)
                return Decision("verified", a.normalised, proof, agreeing, _source(agreeing))

    # Exact text-layer reading (anchored; deferred, so `exact` is never set in this build).
    for r in machine:
        if r.exact and r.normalised is not None and passing_equality_checks:
            return Decision(
                "verified", r.normalised, ("exact", "arithmetic"), (r.reader,), _source([r.reader])
            )

    readable = [r for r in machine if r.normalised is not None]
    first = machine[0]
    value = (
        first.normalised
        if first.normalised is not None
        else (readable[0].normalised if readable else None)
    )
    agreeing = tuple(r.reader for r in machine if r.normalised == value and value is not None)
    distinct = {r.normalised for r in readable}
    if len(readable) >= 2 and len(distinct) >= 2:
        return Decision("disputed", value, ("single",), agreeing, _source(agreeing))
    return Decision(
        "unverified", value, ("single",) if value is not None else (), agreeing, _source(agreeing)
    )


def _source(readers) -> Source | None:
    sources = [_SOURCE_OF[r] for r in readers if r in _SOURCE_OF and r != "human"]
    if not sources:
        return None
    return min(sources, key=lambda s: _SOURCE_ORDER[s])
