"""Supply-voltage phrases as tariff orders print them → scope voltage bands (kV)."""

from __future__ import annotations

import re
from typing import Any

_KV = r"(\d+(?:\.\d+)?)\s*k\s*v"


def parse_band(text: str | None) -> dict[str, Any] | None:
    """'up to 11 kV' → {max: 11}; 'at 11kV' / '11 kV' → {min: 11, max: 11};
    'above 11 kV and up to 66 kV' → {min: 11, min_exclusive: true, max: 66};
    'above 132 kV' → {min: 132, min_exclusive: true}; '11 kV & above' → {min: 11}.
    None when the text names no voltage."""
    if not text:
        return None
    t = text.lower().replace("–", "-")
    nums = [float(x) for x in re.findall(_KV, t)]
    if not nums:
        return None
    band: dict[str, Any] = {}

    def num(x: float) -> float | int:
        return int(x) if x == int(x) else x

    above = re.search(r"(above|more than|exceeding|beyond)\s*" + _KV, t)
    upto = re.search(r"(up\s*to|upto|below|not exceeding|less than)\s*(and including\s*)?" + _KV, t)
    and_above = re.search(_KV + r"\s*(&|and)\s*above", t)
    if above:
        band["min"] = num(float(above.group(2)))
        band["min_exclusive"] = True
    if and_above:
        band["min"] = num(float(and_above.group(1)))
    if upto:
        band["max"] = num(float(upto.group(3)))
        if upto.group(1).startswith(("below", "less")):
            band["max_exclusive"] = True
    if not band and len(nums) == 1:
        band = {"min": num(nums[0]), "max": num(nums[0])}
    return band or None


def band_key(band: dict[str, Any] | None) -> str | None:
    """A voltage key for value_by_voltage: the band's single or upper voltage ('11', '33')."""
    if not band:
        return None
    v = band.get("max", band.get("min"))
    return None if v is None else str(v)
