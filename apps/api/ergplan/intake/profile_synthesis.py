"""A year of 15-minute demand from monthly bills.

For each month with a bill, starting from the site's industry shape (packages/profiles/shapes):
  1. weekly shape → the month's days, with declared shutdown days at the shape's base level;
  2. energy: scale every ToD window so its energy equals the bill's ToD energy (or the whole month
     to the month's energy when the bill prints no ToD split) — exact;
  3. peak: stretch each window's deviations from its own mean by one factor k (which keeps every
     window's energy unchanged) so the month's highest block equals recorded MD × power factor.
     k is found by bisection; if the shape cannot reach the target without negative load, the
     closest feasible profile is kept and the shortfall is recorded.
Months without a bill take the mean daily energy of the billed months, flagged `extrapolated`.

All checks the profile must pass (monthly kWh, ToD split within 0.1 %, max = MD) are returned in
`method` with their achieved values, so a reviewer sees how close each month came.
Floats are used inside the arithmetic; the stored series is Decimal kW to the watt.
"""

from __future__ import annotations

import calendar
import zlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ..core.settings import REPO_ROOT

SHAPES_DIR = REPO_ROOT / "packages" / "profiles" / "shapes"
BLOCKS_PER_DAY = 96
HOURS_PER_BLOCK = 0.25


class ShapeNotFound(LookupError):
    pass


@dataclass(frozen=True)
class TodWindow:
    start: str  # "19:00"
    end: str  # "02:00" (wraps past midnight when end <= start)
    kwh: Decimal


@dataclass(frozen=True)
class MonthInput:
    month: date  # first of the month
    kwh: Decimal
    max_kva: Decimal | None = None
    power_factor: Decimal | None = None
    tod: tuple[TodWindow, ...] = ()
    shutdown_days: tuple[int, ...] = ()  # day numbers in the month


@dataclass
class Profile:
    year_start: date
    kw: np.ndarray  # one value per 15-minute block
    method: dict[str, Any] = field(default_factory=dict)
    month_targets: list[tuple[int, int, Decimal]] = field(default_factory=list)  # (start, end, kWh)

    def as_decimals(self) -> list[Decimal]:
        """kW to the watt, with each month's rounding residue put back one watt at a time on blocks
        nearest the month's median (never its peak), so stored monthly energy equals the bill exactly."""
        out = [Decimal(f"{v:.3f}") for v in self.kw]
        step = Decimal("0.001")
        for a, b, kwh in self.month_targets:
            residue = kwh - sum(out[a:b], Decimal(0)) * Decimal("0.25")
            n = int((residue * 4 / step).to_integral_value())
            if n == 0:
                continue
            seg = self.kw[a:b]
            peak = float(seg.max())
            order = np.argsort(np.abs(seg - float(np.median(seg))), kind="stable")
            room = int(abs(n)) // len(seg) + 2  # watts a block may move
            picks = [
                a + int(i) for i in order if seg[i] < peak - 0.001 * room - 0.001 and seg[i] > 0.001 * room
            ]
            picks = picks or [a + int(i) for i in order]
            for j in range(abs(n)):
                out[picks[j % len(picks)]] += step if n > 0 else -step
        return out


def _block(t: str) -> int:
    h, m = (int(x) for x in t.split(":"))
    return (h * 60 + m) // 15


def shape_ids() -> list[str]:
    return sorted(p.stem for p in SHAPES_DIR.glob("*.yaml"))


@lru_cache
def shape(shape_id: str, shapes_dir: Path = SHAPES_DIR) -> tuple[np.ndarray, dict[str, Any]]:
    """The weekly shape: 7 × 96 levels (percent of peak) and its definition."""
    p = shapes_dir / f"{shape_id}.yaml"
    if not p.exists():
        raise ShapeNotFound(shape_id)
    d = yaml.safe_load(p.read_text())
    week = np.full((7, BLOCKS_PER_DAY), float(d["base"]))
    ramp = max(0, int(d.get("ramp_minutes", 0)) // 15)
    for w in d.get("working", []):
        a, b = _block(w["start"]), _block(w["end"]) if w["end"] != "24:00" else BLOCKS_PER_DAY
        for day in w["days"]:
            for i in range(a, b):
                level = float(w["level"])
                if ramp:
                    edge = min(i - a + 1, b - i)
                    if edge <= ramp:
                        level = float(d["base"]) + (level - float(d["base"])) * edge / (ramp + 1)
                week[day, i] = max(week[day, i], level)
    for dip in d.get("dips", []):
        a, b = _block(dip["start"]), _block(dip["end"])
        for day in dip["days"]:
            week[day, a:b] = np.minimum(week[day, a:b], float(dip["level"]))
    return week, d


def _window_mask(n_days: int, start: str, end: str) -> np.ndarray:
    a, b = _block(start), _block(end) if end != "24:00" else BLOCKS_PER_DAY
    day = np.zeros(BLOCKS_PER_DAY, dtype=bool)
    if a < b:
        day[a:b] = True
    else:  # wraps past midnight
        day[a:] = True
        day[:b] = True
    return np.tile(day, n_days)


def _month_base(
    month: date,
    week: np.ndarray,
    base_level: float,
    shutdown: tuple[int, ...],
    weekly_off: tuple[int, ...] = (),
) -> np.ndarray:
    n = calendar.monthrange(month.year, month.month)[1]
    days = []
    for d in range(1, n + 1):
        wd = date(month.year, month.month, d).weekday()
        off = d in shutdown or wd in weekly_off
        days.append(np.full(BLOCKS_PER_DAY, base_level) if off else week[wd])
    return np.concatenate(days)


def working_days(shape_id: str) -> list[int]:
    """Weekdays on which the shape has working hours (0=Mon … 6=Sun)."""
    _, d = shape(shape_id)
    return sorted({int(x) for w in d.get("working", []) for x in w["days"]})


def _windows(m: MonthInput, n_days: int) -> list[tuple[np.ndarray, float]]:
    """Disjoint masks covering the month with their target energy (kWh)."""
    total = float(m.kwh)
    if not m.tod:
        return [(np.ones(n_days * BLOCKS_PER_DAY, dtype=bool), total)]
    masks, covered = [], np.zeros(n_days * BLOCKS_PER_DAY, dtype=bool)
    for w in m.tod:
        mask = _window_mask(n_days, w.start, w.end) & ~covered
        covered |= mask
        masks.append((mask, float(w.kwh)))
    if not covered.all():  # hours the bill's slots do not name carry the remainder
        masks.append((~covered, max(0.0, total - sum(e for _, e in masks))))
    return masks


def synthesise_month(
    m: MonthInput, week: np.ndarray, base_level: float, weekly_off: tuple[int, ...] = ()
) -> tuple[np.ndarray, dict[str, Any]]:
    n = calendar.monthrange(m.month.year, m.month.month)[1]
    x = _month_base(m.month, week, base_level, m.shutdown_days, weekly_off).astype(float)
    windows = _windows(m, n)
    # 1. energy per window, exact
    for mask, e in windows:
        s = x[mask].sum() * HOURS_PER_BLOCK
        x[mask] = x[mask] * (e / s) if s > 0 else e / (mask.sum() * HOURS_PER_BLOCK)
    report: dict[str, Any] = {"month": m.month.isoformat(), "kwh_target": str(m.kwh)}
    # 2. peak = MD × PF, keeping each window's energy
    if m.max_kva is not None:
        pf = float(m.power_factor) if m.power_factor else 1.0
        target = float(m.max_kva) * pf
        means = np.zeros_like(x)
        for mask, _ in windows:
            means[mask] = x[mask].mean()
        dev = x - means

        def peak(k: float) -> float:
            return float((means + k * dev).max())

        lo, hi = 0.0, 1.0
        if dev.max() <= 1e-12:
            k = 1.0
        else:
            while peak(hi) < target and hi < 1e6:
                hi *= 2
            for _ in range(80):
                mid = (lo + hi) / 2
                (lo, hi) = (mid, hi) if peak(mid) < target else (lo, mid)
            k = (lo + hi) / 2
        y = means + k * dev
        method = "linear"
        if y.min() < 0:
            # A linear stretch this large would need negative load (a flat-topped shape). Stretch only
            # while the lowest block stays above half the shape's lowest load (a plant does not drop
            # to zero to make its peak), then place the rest of the month's maximum demand
            # as one 15-minute peak at the shape's busiest block, taking the energy it adds evenly
            # (pro rata) from the rest of that block's window so every window's energy is unchanged.
            method = "linear+peak_block"
            neg = dev < 0
            floor = 0.5 * float(x.min())
            k = max(1.0, float(np.min((means[neg] - floor) / -dev[neg]))) if neg.any() else 1.0
            y = np.maximum(means + k * dev, 0.0)
            idx = int(np.argmax(y))
            if y[idx] < target:
                mask = next(mk for mk, _ in windows if mk[idx])
                others = mask.copy()
                others[idx] = False
                extra = (target - y[idx]) * HOURS_PER_BLOCK
                pool = y[others].sum() * HOURS_PER_BLOCK
                if pool > extra:
                    y[others] = y[others] * (1 - extra / pool)
                    y[idx] = target
                else:
                    report["peak_shortfall_kw"] = round(target - float(y.max()), 3)
        x = y
        report.update(
            {
                "max_kw_target": round(target, 3),
                "max_kw": round(float(x.max()), 3),
                "peak_method": method,
                "stretch": round(k, 6),
            }
        )
    report["kwh"] = round(float(x.sum() * HOURS_PER_BLOCK), 3)
    if m.tod:
        report["tod"] = [
            {
                "window": f"{w.start}-{w.end}",
                "kwh_target": str(w.kwh),
                "kwh": round(float(x[_window_mask(n, w.start, w.end)].sum() * HOURS_PER_BLOCK), 3),
            }
            for w in m.tod
        ]
    return x, report


def synthesise_year(
    months: list[MonthInput], shape_id: str, year_start: date | None = None, weekly_off: tuple[int, ...] = ()
) -> Profile:
    """Twelve months from `year_start` (default: the first billed month's April-to-March year)."""
    if not months:
        raise ValueError("at least one month of bills is needed")
    week, d = shape(shape_id)
    base_level = float(d["base"])
    by_month = {m.month: m for m in months}
    first = min(by_month)
    start = year_start or date(first.year if first.month >= 4 else first.year - 1, 4, 1)
    daily = [float(m.kwh) / calendar.monthrange(m.month.year, m.month.month)[1] for m in months]
    mean_daily = sum(daily) / len(daily)
    parts, reports, targets = [], [], []
    offset = 0
    for i in range(12):
        y, mo = start.year + (start.month - 1 + i) // 12, (start.month - 1 + i) % 12 + 1
        month = date(y, mo, 1)
        m = by_month.get(month)
        if m is None:
            # same calendar month in another year counts as that month's bill
            m = next((v for k, v in by_month.items() if k.month == mo), None)
        if m is None:
            n = calendar.monthrange(y, mo)[1]
            mi = MonthInput(month=month, kwh=Decimal(str(round(mean_daily * n, 3))))
            x, rep = synthesise_month(mi, week, base_level, weekly_off)
            rep["extrapolated"] = True
        else:
            x, rep = synthesise_month(
                MonthInput(
                    month=month,
                    kwh=m.kwh,
                    max_kva=m.max_kva,
                    power_factor=m.power_factor,
                    tod=m.tod,
                    shutdown_days=m.shutdown_days,
                ),
                week,
                base_level,
                weekly_off,
            )
            rep["from_bill_month"] = m.month.isoformat()
        parts.append(x)
        reports.append(rep)
        targets.append((offset, offset + len(x), Decimal(rep["kwh_target"])))
        offset += len(x)
    kw = np.concatenate(parts)
    return Profile(
        year_start=start,
        kw=kw,
        month_targets=targets,
        method={
            "shape": shape_id,
            "weekly_off": list(weekly_off),
            "shape_note": d.get("note"),
            "months": reports,
            "algorithm": "profile_synthesis v1 (window energy exact, peak by deviation stretch)",
        },
    )


def encode(values: list[Decimal]) -> bytes:
    return zlib.compress("\n".join(format(v, "f") for v in values).encode())


def decode(blob: bytes) -> list[Decimal]:
    return [Decimal(s) for s in zlib.decompress(blob).decode().split("\n") if s]


def year_days(start: date) -> list[date]:
    out, d = [], start
    end = date(start.year + 1, start.month, start.day)
    while d < end:
        out.append(d)
        d += timedelta(days=1)
    return out
