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
    return re.sub(r"\s+", " ", t).strip().casefold()


def _nospace(text: str) -> str:
    return re.sub(r"\s+", "", text)


_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…)\s*")


def _fragment_on_page(fragment: str, page: str) -> bool:
    q = normalise(fragment)
    return q in page or _nospace(q) in _nospace(page)


def quote_on_page(quote: str, page_text: str) -> bool:
    """The quote is on the page. A table row whose cells the text layer splits across lines may be
    quoted as fragments joined by '...' or '…': every fragment must then be verbatim on the page,
    none shorter than 4 characters, and at least one 12 characters or longer."""
    p = normalise(page_text)
    fragments = [f for f in _ELLIPSIS.split(quote) if f.strip()]
    if not fragments:
        return False
    if len(fragments) == 1:
        return len(normalise(fragments[0])) >= 8 and _fragment_on_page(fragments[0], p)
    if any(len(normalise(f)) < 4 for f in fragments) or max(len(normalise(f)) for f in fragments) < 12:
        return False
    return all(_fragment_on_page(f, p) for f in fragments)


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
    plain = n.replace(",", "")
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
