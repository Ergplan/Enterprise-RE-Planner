"""Profile synthesis properties (Stage 2): monthly kWh exact, ToD split within 0.1 %, maximum equals
MD × PF, weekly offs and shutdowns honoured, every shape usable."""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from ergplan.intake.profile_synthesis import (
    MonthInput,
    ShapeNotFound,
    TodWindow,
    decode,
    encode,
    shape,
    shape_ids,
    synthesise_year,
    working_days,
)


def _month_slice(kw: np.ndarray, year_start: date, month: date) -> np.ndarray:
    i = 0
    y, m = year_start.year, year_start.month
    while (y, m) != (month.year, month.month):
        i += calendar.monthrange(y, m)[1] * 96
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return kw[i : i + calendar.monthrange(month.year, month.month)[1] * 96]


def _window(n_days: int, a: int, b: int) -> np.ndarray:
    day = np.zeros(96, dtype=bool)
    if a < b:
        day[a:b] = True
    else:
        day[a:] = True
        day[:b] = True
    return np.tile(day, n_days)


MAY = MonthInput(
    month=date(2026, 5, 1),
    kwh=Decimal("812000"),
    max_kva=Decimal("1900"),
    power_factor=Decimal("0.98"),
    tod=(TodWindow("19:00", "02:00", Decimal("230000")), TodWindow("07:00", "16:00", Decimal("320000"))),
)
JUNE = MonthInput(
    month=date(2026, 6, 1), kwh=Decimal("790000"), max_kva=Decimal("1850"), power_factor=Decimal("0.97")
)


def test_eight_shapes_ship_and_build_a_week() -> None:
    assert shape_ids() == sorted(
        [
            "continuous_process",
            "two_shift",
            "single_shift",
            "cold_storage",
            "textile_spinning",
            "steel_induction",
            "pharma_formulation",
            "food_processing",
        ]
    )
    for sid in shape_ids():
        week, d = shape(sid)
        assert week.shape == (7, 96)
        assert week.max() <= 100 and week.min() >= 0
        assert d["note"]


def test_unknown_shape() -> None:
    with pytest.raises(ShapeNotFound):
        shape("nope")


@pytest.mark.parametrize("sid", ["two_shift", "steel_induction", "single_shift", "food_processing"])
def test_month_energy_tod_and_peak(sid: str) -> None:
    p = synthesise_year([MAY, JUNE], sid)
    assert len(p.kw) == 365 * 96
    may = _month_slice(p.kw, p.year_start, MAY.month)
    assert abs(may.sum() * 0.25 - 812000) < 0.01
    for w, (a, b) in zip(MAY.tod, [(76, 8), (28, 64)], strict=True):
        got = may[_window(31, a, b)].sum() * 0.25
        assert abs(got - float(w.kwh)) / float(w.kwh) < 0.001
    assert abs(may.max() - 1900 * 0.98) < 0.01
    june = _month_slice(p.kw, p.year_start, JUNE.month)
    assert abs(june.sum() * 0.25 - 790000) < 0.01
    assert abs(june.max() - 1850 * 0.97) < 0.01
    assert p.kw.min() >= 0


def test_months_without_bills_are_extrapolated_and_flagged() -> None:
    p = synthesise_year([MAY, JUNE], "two_shift")
    reports = p.method["months"]
    assert len(reports) == 12
    assert [r["month"] for r in reports][:3] == ["2026-04-01", "2026-05-01", "2026-06-01"]
    assert sum(1 for r in reports if r.get("extrapolated")) == 10
    assert reports[1]["from_bill_month"] == "2026-05-01"


def test_same_calendar_month_of_another_year_is_used() -> None:
    p = synthesise_year(
        [MonthInput(month=date(2025, 5, 1), kwh=Decimal("500000"))], "two_shift", year_start=date(2026, 4, 1)
    )
    assert p.method["months"][1]["from_bill_month"] == "2025-05-01"


def test_weekly_off_and_shutdown_days_sit_at_base() -> None:
    m = MonthInput(month=date(2026, 5, 1), kwh=Decimal("300000"), shutdown_days=(5,))
    p = synthesise_year([m], "continuous_process", weekly_off=(6,))
    may = _month_slice(p.kw, p.year_start, m.month).reshape(31, 96)
    sundays = [d - 1 for d in range(1, 32) if date(2026, 5, d).weekday() == 6]
    for d in [*sundays, 4]:
        assert np.allclose(may[d], may[d][0])  # a flat base day
    assert may[0].max() > may[sundays[0]].max()  # working day above the off day


def test_shape_too_flat_for_the_peak_is_flagged_not_negative() -> None:
    p = synthesise_year(
        [MonthInput(month=date(2026, 5, 1), kwh=Decimal("800000"), max_kva=Decimal("2600"))],
        "continuous_process",
    )
    rep = p.method["months"][1]
    assert p.kw.min() >= 0
    assert rep.get("peak_shortfall_kw", 0) > 0 or abs(rep["max_kw"] - 2600) < 0.01


def test_kwh_without_md_keeps_the_shape() -> None:
    p = synthesise_year([MonthInput(month=date(2026, 5, 1), kwh=Decimal("400000"))], "two_shift")
    assert "max_kw" not in p.method["months"][1]


def test_working_days() -> None:
    assert working_days("two_shift") == [0, 1, 2, 3, 4, 5]
    assert working_days("continuous_process") == [0, 1, 2, 3, 4, 5, 6]


def test_encode_round_trip() -> None:
    vals = [Decimal("1.250"), Decimal("0.000"), Decimal("1234.567")]
    assert decode(encode(vals)) == vals


def test_needs_a_month() -> None:
    with pytest.raises(ValueError):
        synthesise_year([], "two_shift")


def test_stored_decimals_keep_monthly_energy_exact_and_the_peak() -> None:
    p = synthesise_year(
        [MAY, JUNE, MonthInput(month=date(2026, 7, 1), kwh=Decimal("1972620.37"), max_kva=Decimal("3250"))],
        "continuous_process",
    )
    vals = p.as_decimals()
    for a, b, kwh in p.month_targets:
        assert sum(vals[a:b], Decimal(0)) * Decimal("0.25") == kwh
    may = vals[p.month_targets[1][0] : p.month_targets[1][1]]
    assert max(may) == Decimal("1862.000")
