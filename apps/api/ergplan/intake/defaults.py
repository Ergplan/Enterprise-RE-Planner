"""ergPLAN's normative defaults for what a bill does not print, each recorded as an assumption.

Every default returns the value and a SourceRef of kind `assumption` whose note says what was
assumed and why, so the client sees it as an editable chip (invariant 1), never as a fact.
Category mapping turns a printed tariff code into the order's category code; the mapping is
itself an assumption until the client or analyst confirms it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..core.sourced import RefKind, SourceRef

# DISCOM → state (mirrors packages/rulebooks/jurisdictions.yaml for the seeded states).
DISCOM_STATE = {
    "npcl": "UP",
    "pvvnl": "UP",
    "mvvnl": "UP",
    "puvvnl": "UP",
    "dvvnl": "UP",
    "kesco": "UP",
    "msedcl": "MH",
    "aeml": "MH",
    "tpcd": "MH",
    "best": "MH",
}

# billx profile ids that are not ergPLAN jurisdiction ids.
BILLX_PROFILE_ALIASES = {"uppcl": "pvvnl", "mahadiscom": "msedcl", "mseb": "msedcl"}

# Printed tariff codes → the order's category code, per state. Patterns run on the upper-cased text.
CATEGORY_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "UP": [
        (r"\bHV\s*[-–]?\s*2\b", "HV-2"),
        (r"\bHV\s*[-–]?\s*1\b", "HV-1"),
        (r"\bLMV\s*[-–]?\s*6\b", "LMV-6"),
    ],
    "MH": [
        (r"\bHT\s*[-–]?\s*(I|1)\s*[-–]?\s*\(?\s*A\s*\)?", "HT I(A)"),
        (r"\bHT\s*[-–]?\s*(II|2)\b", "HT II"),
        (r"\bHT\s*[-–]?\s*(I|1)\s*[-–]?\s*\(?\s*B\s*\)?", "HT I(B)"),
        (r"\bLT\s*[-–]?\s*V\b", "LT V"),
    ],
}

# The usual supply voltage of a category, offered as the default chip (most bills do not print it).
USUAL_VOLTAGE_KV = {
    "HV-2": Decimal("11"),
    "HV-1": Decimal("11"),
    "HT I(A)": Decimal("22"),
    "HT I(B)": Decimal("22"),
    "HT II": Decimal("22"),
    "LMV-6": Decimal("0.415"),
    "LT V": Decimal("0.415"),
}


@dataclass(frozen=True)
class Assumed:
    value: Any
    ref: SourceRef


def assumption(note: str) -> SourceRef:
    return SourceRef(kind=RefKind.ASSUMPTION, note=note[:500])


def discom_from_profile(profile_id: str | None) -> str | None:
    if not profile_id:
        return None
    pid = profile_id.lower().strip()
    pid = BILLX_PROFILE_ALIASES.get(pid, pid)
    return pid if pid in DISCOM_STATE else None


def state_of(discom: str) -> str | None:
    return DISCOM_STATE.get(discom)


def category_from_printed(state: str, printed: str | None) -> Assumed | None:
    if not printed:
        return None
    text = printed.upper()
    for pattern, code in CATEGORY_PATTERNS.get(state, []):
        if re.search(pattern, text):
            return Assumed(
                code, assumption(f"the bill prints category '{printed}', read as the order's {code}; confirm")
            )
    return None


def voltage_kv(category: str | None) -> Assumed:
    if category and category in USUAL_VOLTAGE_KV:
        v = USUAL_VOLTAGE_KV[category]
        return Assumed(
            v,
            assumption(
                f"supply voltage not on the bill; {v} kV is the usual voltage for {category}; confirm"
            ),
        )
    return Assumed(
        Decimal("11"),
        assumption("supply voltage not on the bill; 11 kV assumed (lowest HT voltage); confirm"),
    )


def connection_kind(voltage: Decimal) -> str:
    if voltage >= Decimal("66"):
        return "eht"
    return "ht" if voltage >= Decimal("3.3") else "lt"


def power_factor() -> Assumed:
    return Assumed(Decimal("0.95"), assumption("power factor not on the bill; 0.95 assumed"))


def industry_shape() -> Assumed:
    return Assumed(
        "two_shift", assumption("operating pattern not stated; two shifts, six days a week assumed")
    )


def weekly_off(shape_id: str) -> Assumed:
    from .profile_synthesis import working_days

    off = [d for d in range(7) if d not in working_days(shape_id)]
    names = ", ".join(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d] for d in off) or "none"
    return Assumed(off, assumption(f"weekly off not stated; {names} assumed from the {shape_id} pattern"))
