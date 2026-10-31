"""Normative generation profiles (packages/profiles/cuf): a year of 15-minute kW for a source of a
given capacity, scaled to the curve's annual CUF. Assumptions until the developer's profile exists."""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..core.settings import REPO_ROOT

CUF_DIR = REPO_ROOT / "packages" / "profiles" / "cuf"


class CurveNotFound(LookupError):
    pass


@lru_cache
def curve(curve_id: str, root: Path = CUF_DIR) -> dict[str, Any]:
    p = root / f"{curve_id}.yaml"
    if not p.exists():
        raise CurveNotFound(curve_id)
    return dict(yaml.safe_load(p.read_text()))


def curve_for(source: str, state: str) -> list[str]:
    """Curve ids for a source in a state (hybrid = solar + wind, equal energy)."""
    st = state.lower()
    if source == "hybrid":
        return [f"solar_{st}", f"wind_{st}"]
    return [f"{source}_{st}"]


def profile(curve_ids: list[str], capacity_kw: Decimal, year_start: date) -> tuple[list[Decimal], Decimal]:
    """15-minute kW for a year from `year_start` and the blended annual CUF (percent)."""
    days = []
    d = year_start
    for _ in range(12):
        n = calendar.monthrange(d.year, d.month)[1]
        days += [d.month] * n
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    total = [Decimal(0)] * (len(days) * 96)
    cufs = []
    for cid in curve_ids:
        c = curve(cid)
        monthly = {int(k): Decimal(str(v)) for k, v in c["monthly"].items()}
        hourly = {int(k): Decimal(str(v)) for k, v in c["hourly"].items()}
        raw = [monthly[m] * hourly.get(b // 4, Decimal(0)) for m in days for b in range(96)]
        target = capacity_kw * Decimal(8760) * Decimal(str(c["annual_cuf_pct"])) / 100
        scale = target / (sum(raw, Decimal(0)) / 4) if sum(raw, Decimal(0)) else Decimal(0)
        share = Decimal(1) / len(curve_ids)
        for i, v in enumerate(raw):
            total[i] += min(v * scale, capacity_kw) * share
        cufs.append(Decimal(str(c["annual_cuf_pct"])))
    return total, sum(cufs, Decimal(0)) / len(cufs)
