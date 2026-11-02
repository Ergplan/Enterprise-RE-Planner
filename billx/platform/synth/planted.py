"""Planted misreads and reader-misread fixtures (build prompt sections 2, 5.4 and 10).

A **planted misread** is a variant of a clean synthetic bill whose page shows ONE printed
value changed by one digit, at a position the declared check can catch, while the truth
file keeps the clean bill's values and records what was planted. The renderers read the
`printed` strings of the bill dict, so a variant is rendered from a deep copy of the dict
with that one string altered; nothing else on the page moves. The clean bill passes; the
planted one must make its declared check report `fail` (the evaluation counts it caught
or missed).

A **reader-misread fixture** lists, for every scalar guaranteed field a clean electricity
bill prints, one plausible misread string (a digit changed, a digit group dropped, or an
OCR-confusable character) whose normalised value differs from the truth, so the evaluation
can simulate a reader disagreement without rendering anything.

Everything here is deterministic for a bill dict (and, for the fixtures, a seeded rng).
"""

from __future__ import annotations

import copy
import random
from collections.abc import Callable, Iterator
from decimal import Decimal

from billx.core.normalize import normalise
from billx.platform.synth.values import add_months, field_types, month_name_year, month_slash_year

KIND = "printed_inconsistency"
MONTH_FORMAT = {"avvnl-ht-synth-v1": month_name_year, "pvvnl-hv2-synth-v1": month_slash_year}
CONFUSABLE = {
    "O": "0",
    "0": "O",
    "I": "1",
    "1": "I",
    "l": "1",
    "S": "5",
    "5": "S",
    "B": "8",
    "8": "B",
    "Z": "2",
    "2": "Z",
    "G": "6",
    "6": "G",
}


# digit arithmetic on printed strings --------------------------------------------------------


def _value(printed: str) -> Decimal:
    return Decimal(printed.replace(",", ""))


def _digit_positions(printed: str) -> list[int]:
    return [i for i, ch in enumerate(printed) if ch.isdigit()]


def _leading(printed: str) -> int:
    """Index of the leading significant digit (the first non-zero digit, else the first)."""
    positions = _digit_positions(printed)
    return next((i for i in positions if printed[i] != "0"), positions[0])


def _replace(printed: str, index: int, digit: int) -> str:
    return printed[:index] + str(digit) + printed[index + 1 :]


def change_leading_digit(printed: str) -> str:
    """The leading significant digit raised by one (lowered for a 9): the largest one-digit
    change, which every equality check's `detects:` covers."""
    i = _leading(printed)
    d = int(printed[i])
    return _replace(printed, i, d + 1 if d < 9 else d - 1)


def candidates(printed: str) -> Iterator[str]:
    """Every one-digit replacement of `printed`, positions left to right, each position
    trying the nearest digits first; the leading digit is never made 0 (that would read as
    a dropped digit) except as the very last resort."""
    lead = _leading(printed)
    last_resort = None
    for i in _digit_positions(printed):
        d = int(printed[i])
        for step in range(1, 10):
            for r in (d - step, d + step):
                if not 0 <= r <= 9 or r == d:
                    continue
                if i == lead and r == 0:
                    last_resort = _replace(printed, i, r)
                    continue
                yield _replace(printed, i, r)
    if last_resort is not None:
        yield last_resort


def smallest_change_of_at_least(printed: str, fraction: Decimal) -> str:
    """The one-digit change of `printed` with the smallest relative difference that is still
    at least `fraction` of the value (GG03 wants about one per cent)."""
    original = _value(printed)
    best, best_rel = None, None
    for c in candidates(printed):
        rel = abs(_value(c) - original) / original
        if rel >= fraction and (best_rel is None or rel < best_rel):
            best, best_rel = c, rel
    if best is None:
        raise ValueError("no one-digit change reaches the fraction")
    return best


# the planted variants ------------------------------------------------------------------------


def _record(path: str, check: str, original: str, planted: str, **extra) -> dict:
    return {
        "path": path,
        "check": check,
        "original_printed": original,
        "planted_printed": planted,
        "kind": KIND,
        **extra,
    }


def _plant(container: dict, key: str, path: str, check: str, planted: str) -> dict:
    original = container[key]
    if planted == original:
        raise ValueError(f"{check}: the planted string equals the printed one")
    container[key] = planted
    return _record(path, check, original, planted)


def _plant_leading(container: dict, key: str, path: str, check: str) -> dict:
    return _plant(container, key, path, check, change_leading_digit(container[key]))


def _tod(b: dict, reg: str, i: int) -> tuple[dict, str]:
    return b["tod"][reg][i]["printed"], f"tod.{reg}[{i}]"


def _charge(b: dict, code: str) -> tuple[dict, str]:
    i = next(i for i, x in enumerate(b["charges"]) if x["code"] == code)
    return b["charges"][i]["printed"], f"charges[{i}]"


def _g02(b: dict) -> dict:
    """A TOD row's present reading in its leading digit: present - past != difference."""
    row, path = _tod(b, "kwh", 0)
    return _plant_leading(row, "present", f"{path}.present", "G02")


def _g03(b: dict) -> dict:
    """One slot's consumption in its leading digit: difference x MF != consumption."""
    row, path = _tod(b, "kwh", 1)
    return _plant_leading(row, "consumption", f"{path}.consumption", "G03")


def _g05(b: dict) -> dict:
    """One charge line's amount in its leading digit: quantity x rate != amount."""
    line, path = _charge(b, "energy_charge")
    return _plant_leading(line, "amount", f"{path}.amount", "G05")


def _g07(b: dict) -> dict:
    """Current charges in the leading digit, far more than the one-rupee tolerance."""
    return _plant_leading(b["printed"], "totals.current_charges", "totals.current_charges", "G07")


def _g09(b: dict) -> dict:
    """Net payable in the leading digit: current + arrears != net payable."""
    return _plant_leading(b["printed"], "totals.net_payable", "totals.net_payable", "G09")


def _g15(b: dict) -> dict:
    """One kVAh slot's consumption changed while the total register stays: the slots no longer
    add up to the total (G03 trips on the same row; G15 is the declared check)."""
    row, path = _tod(b, "kvah", 0)
    return _plant_leading(row, "consumption", f"{path}.consumption", "G15")


def _g16(b: dict) -> dict:
    """The gross kVAh total printed below the gross kWh total by more than G16's tolerance
    (max(1, 0.006 x MF)): the first one-digit change of the kVAh total that gets there."""
    kvah, kwh = b["tod"]["kvah_total"], b["tod"]["kwh_total"]
    tolerance = max(Decimal(1), Decimal("0.006") * kvah["mf"])
    limit = kwh["consumption"] - 2 * tolerance
    printed = kvah["printed"]["consumption"]
    planted = next(c for c in candidates(printed) if _value(c) < limit)
    return _plant(kvah["printed"], "consumption", "tod.kvah_total.consumption", "G16", planted)


def _g18(b: dict) -> dict:
    """The bill month printed three months after the reading period ends (the default
    `bill_month_offset` allows 0 to 1)."""
    planted = MONTH_FORMAT[b["layout"]](add_months(b["values"]["period.to"], 3))
    return _plant(b["printed"], "period.bill_month", "period.bill_month", "G18", planted)


def _g19(b: dict) -> dict:
    """The two reading dates swapped: the period now ends before it starts. Two printed
    strings move, which the record says with `swapped_with`."""
    p = b["printed"]
    start, end = p["period.from"], p["period.to"]
    p["period.from"], p["period.to"] = end, start
    return _record("period.from", "G19", start, end, swapped_with="period.to")


def _g20(b: dict) -> dict:
    """A non-credit line (electricity duty) printed with a minus and no credit marker."""
    line, path = _charge(b, "electricity_duty")
    return _plant(line, "amount", f"{path}.amount", "G20", "-" + line["amount"])


def _gg02(b: dict) -> dict:
    """The present reading in its leading digit: (current - previous) != volume."""
    return _plant_leading(b["printed"], "readings.current", "readings.current", "GG02")


def _gg03(b: dict) -> dict:
    """MMBtu changed by about one per cent (the smallest one-digit change of at least 1%;
    GG03 allows 0.5%)."""
    planted = smallest_change_of_at_least(b["printed"]["energy.mmbtu"], Decimal("0.01"))
    return _plant(b["printed"], "energy.mmbtu", "energy.mmbtu", "GG03", planted)


def _gg04(b: dict) -> dict:
    """The gas charge line's amount in its leading digit: quantity x rate != amount."""
    line, path = _charge(b, "gas_charge")
    return _plant_leading(line, "amount", f"{path}.amount", "GG04")


def _gg05(b: dict) -> dict:
    """The total in its leading digit: items + taxes != total."""
    return _plant_leading(b["printed"], "totals.amount", "totals.amount", "GG05")


ELECTRICITY: dict[str, Callable[[dict], dict]] = {
    "G02": _g02,
    "G03": _g03,
    "G05": _g05,
    "G07": _g07,
    "G09": _g09,
    "G15": _g15,
    "G16": _g16,
    "G18": _g18,
    "G19": _g19,
    "G20": _g20,
}
GAS: dict[str, Callable[[dict], dict]] = {
    "GG02": _gg02,
    "GG03": _gg03,
    "GG04": _gg04,
    "GG05": _gg05,
}
BY_TYPE = {"electricity_bill": ELECTRICITY, "gas_bill": GAS}


def variants(bill: dict) -> Iterator[tuple[str, dict, dict]]:
    """For a clean electricity or gas bill dict: (check id, the altered copy to render, the
    `planted` record for the truth file), one per check in the order of the tables above.
    Other document types yield nothing."""
    for check, plant in BY_TYPE.get(bill["document_type"], {}).items():
        altered = copy.deepcopy(bill)
        record = plant(altered)
        assert record["check"] == check
        yield check, altered, record


# reader-misread fixtures ----------------------------------------------------------------------


def _misread_number(printed: str, rng: random.Random) -> tuple[str, str]:
    groups = printed.split(",")
    if len(groups) >= 3 and rng.random() < 0.5:
        drop = rng.randrange(1, len(groups) - 1)  # an inner group, so the shape stays plausible
        return ",".join(groups[:drop] + groups[drop + 1 :]), "group_dropped"
    return _misread_digit(printed, rng), "digit_changed"


def _misread_digit(printed: str, rng: random.Random) -> str:
    positions = _digit_positions(printed)
    i = rng.choice(positions)
    d = int(printed[i])
    r = rng.choice([x for x in range(10) if x != d])
    return _replace(printed, i, r)


def _misread_text(printed: str, rng: random.Random) -> tuple[str, str]:
    if any(ch.isdigit() for ch in printed):
        return _misread_digit(printed, rng), "digit_changed"
    indexes = [i for i, ch in enumerate(printed) if ch in CONFUSABLE]
    if indexes:
        i = rng.choice(indexes)
        return printed[:i] + CONFUSABLE[printed[i]] + printed[i + 1 :], "character_confused"
    letters = [i for i, ch in enumerate(printed) if ch.isalpha()]
    i = rng.choice(letters)
    ch = printed[i]
    swap = chr(ord(ch) + 1) if ch.lower() != "z" else chr(ord(ch) - 1)
    return printed[:i] + swap + printed[i + 1 :], "character_confused"


def misread(printed: str, field_type: str, rng: random.Random) -> tuple[str, str]:
    """One plausible misread of `printed` for a field of `field_type` whose normalised value
    is readable and differs from the printed one, and the kind of misread it is."""
    truth = normalise(printed, field_type)
    for _ in range(100):
        if field_type == "number":
            got, kind = _misread_number(printed, rng)
        elif field_type in ("date", "month", "identifier"):
            got, kind = _misread_digit(printed, rng), "digit_changed"
        else:
            got, kind = _misread_text(printed, rng)
        norm = normalise(got, field_type)
        if norm is not None and norm != truth:
            return got, kind
    raise ValueError("no plausible misread found")


def misreads(bill: dict, rng: random.Random) -> dict[str, dict]:
    """{field path: {printed, misread, kind}} for every scalar guaranteed field the bill
    prints; `rng` makes the choice of digit or group repeatable."""
    kind = {"electricity_bill": "electricity", "gas_bill": "gas"}[bill["document_type"]]
    types = field_types(kind)
    out = {}
    for path, printed in bill["printed"].items():
        got, how = misread(printed, types[path], rng)
        out[path] = {"printed": printed, "misread": got, "kind": how}
    return out
