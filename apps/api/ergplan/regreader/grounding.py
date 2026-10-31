"""The deterministic checks every proposed rule row passes before it can become a draft:
the quote is on the cited page, and every number in the body is printed on a cited page.
No model is involved here; this is what makes a model's transcription reviewable."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])")
_WHOLE_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def normalise(text: str) -> str:
    """Case-folded, NFKC, dashes and quotes unified, all whitespace runs to one space."""
    t = unicodedata.normalize("NFKC", text).replace("￾", "").replace("­", "")
    t = re.sub(r"[‐-―−]", "-", t)
    t = re.sub(r"[‘’´`]", "'", t)
    t = re.sub(r"[“”]", '"', t)
    t = re.sub(r"[|¦]", " ", t)  # OCR'd tables carry column bars the printed text does not
    return re.sub(r"\s+", " ", t).strip().casefold()


def _nospace(text: str) -> str:
    return re.sub(r"\s+", "", text)


_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…)\s*")


def _fragment_on_page(fragment: str, page: str) -> bool:
    q = normalise(fragment)
    return q in page or _nospace(q) in _nospace(page)


def _words_in_order(quote: str, page: str) -> bool:
    """OCR of a multi-column table interleaves the columns' words. Each column keeps its own order,
    so a quote from one column appears as its words in order with other words between them. Accept
    that when the words span at most 4 x their count + 20 words of the page."""
    q = re.findall(r"[\w.%/-]+", quote)
    w = re.findall(r"[\w.%/-]+", page)
    if len(q) < 4:
        return False
    limit = 4 * len(q) + 20
    for start in (i for i, x in enumerate(w) if x == q[0]):
        j, k = start, 0
        while j < len(w) and k < len(q) and j - start <= limit:
            if w[j] == q[k]:
                k += 1
            j += 1
        if k == len(q):
            return True
    return False


def quote_on_page(quote: str, page_text: str, ocr: bool = False) -> bool:
    """The quote is on the page. A table row whose cells the text layer splits across lines may be
    quoted as fragments joined by '...' or '…': every fragment must then be verbatim on the page,
    none shorter than 4 characters, and at least one 12 characters or longer."""
    p = normalise(page_text)
    fragments = [f for f in _ELLIPSIS.split(quote) if f.strip()]
    if not fragments:
        return False

    def found(f: str) -> bool:
        return _fragment_on_page(f, p) or (ocr and _words_in_order(normalise(f), p))

    if len(fragments) == 1:
        return len(normalise(fragments[0])) >= 8 and found(fragments[0])
    if any(len(normalise(f)) < 4 for f in fragments) or max(len(normalise(f)) for f in fragments) < 12:
        return False
    return all(found(f) for f in fragments)


def numbers_in(value: Any) -> list[str]:
    """Every value in a body that is a number or a wholly numeric string (codes such as 'HV-2' and
    labels are identifiers, not values), recursively."""
    out: list[str] = []
    if isinstance(value, dict):
        for v in value.values():
            out += numbers_in(v)
    elif isinstance(value, list):
        for v in value:
            out += numbers_in(v)
    elif isinstance(value, bool) or value is None:
        pass
    elif isinstance(value, (int, float)):
        out.append(str(value))
    elif isinstance(value, str) and _WHOLE_NUM.fullmatch(value.strip()):
        out.append(value.strip())
    return out


def _forms(n: str) -> set[str]:
    """'300' is printed as '300', '300.00' or '300.0'; '1,23,456' as itself or '123456'."""
    plain = n.replace(",", "").lstrip("-+")  # signs are printed as words or brackets: compare magnitudes
    forms = {n, plain}
    if "." in plain:
        whole, frac = plain.split(".", 1)
        stripped = frac.rstrip("0")
        forms.add(whole if not stripped else f"{whole}.{stripped}")
    else:
        forms |= {f"{plain}.0", f"{plain}.00"}
    return forms


def printed_numbers(texts: Iterable[str]) -> set[str]:
    found: set[str] = set()
    for t in texts:
        for m in _NUM.finditer(unicodedata.normalize("NFKC", t)):
            found |= _forms(m.group(0))
    return found


def ungrounded_numbers(body: dict[str, Any], page_texts: Iterable[str]) -> list[str]:
    """Numbers in the body that are printed on none of the given pages (time bands like 19:00
    count as printed when the hour is)."""
    printed = printed_numbers(page_texts)
    missing = []
    for n in numbers_in(body):
        if not (_forms(n) & printed):
            missing.append(n)
    return sorted(set(missing))


_ZERO_WORDS = re.compile(r"\b(zero|nil)\b", re.I)
_WAIVED_WORDS = re.compile(
    r"not\s+be\s+payable|shall\s+not\s+be\s+(levied|payable|applicable)|not\s+required\s+to\s+pay|exempt|waive",
    re.I,
)


def semantic_numbers(body: dict[str, Any], page_texts: Iterable[str]) -> dict[str, Any]:
    """A copy of the body without the numbers that stand for printed words: a value of 0 where the
    page says 'zero' or 'nil', and an exemption's waived_pct of 100 where the page says the charge
    is not payable, exempt or waived. Everything else must still be printed as a number."""
    text = " ".join(page_texts)
    out = dict(body)
    if "value" in out and str(out["value"]).strip() in {"0", "0.0", "0.00"} and _ZERO_WORDS.search(text):
        out.pop("value")
    if isinstance(out.get("exemptions"), list) and _WAIVED_WORDS.search(text):
        out["exemptions"] = [
            {
                k: v
                for k, v in e.items()
                if not (k == "waived_pct" and str(v).strip() in {"100", "100.0", "100.00"})
            }
            if isinstance(e, dict)
            else e
            for e in out["exemptions"]
        ]
    return out
