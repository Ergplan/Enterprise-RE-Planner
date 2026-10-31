"""Units as regulations print them, and the one place conversions happen (rule 15).

Conversions that need an energy or time quantity (INR/MW/month → INR/kWh) are not unit
conversions; they live in the engine, which knows the scheduled energy.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum


class Unit(StrEnum):
    INR = "INR"
    INR_PER_KWH = "INR/kWh"
    INR_PER_KVAH = "INR/kVAh"
    INR_PER_MWH = "INR/MWh"
    INR_PER_KVA_MONTH = "INR/kVA/month"
    INR_PER_KW_MONTH = "INR/kW/month"
    INR_PER_MW_MONTH = "INR/MW/month"
    INR_PER_MW_DAY = "INR/MW/day"
    INR_PER_YEAR = "INR/year"
    PAISE_PER_KWH = "paise/kWh"
    PERCENT = "percent"
    KWH = "kWh"
    KVAH = "kVAh"
    MWH = "MWh"
    KW = "kW"
    KVA = "kVA"
    MW = "MW"
    KV = "kV"
    HOURS = "hours"
    RATIO = "ratio"
    COUNT = "count"
    YEARS = "years"
    TCO2 = "tCO2"
    TCO2_PER_MWH = "tCO2/MWh"


class IncompatibleUnits(ValueError):
    pass


# factor such that value_in_to = value_in_from * factor
_FACTORS: dict[tuple[Unit, Unit], Decimal] = {
    (Unit.INR_PER_MWH, Unit.INR_PER_KWH): Decimal("0.001"),
    (Unit.INR_PER_KWH, Unit.INR_PER_MWH): Decimal("1000"),
    (Unit.PAISE_PER_KWH, Unit.INR_PER_KWH): Decimal("0.01"),
    (Unit.INR_PER_KWH, Unit.PAISE_PER_KWH): Decimal("100"),
    (Unit.MWH, Unit.KWH): Decimal("1000"),
    (Unit.KWH, Unit.MWH): Decimal("0.001"),
    (Unit.MW, Unit.KW): Decimal("1000"),
    (Unit.KW, Unit.MW): Decimal("0.001"),
    (Unit.INR_PER_MW_MONTH, Unit.INR_PER_KW_MONTH): Decimal("0.001"),
    (Unit.INR_PER_KW_MONTH, Unit.INR_PER_MW_MONTH): Decimal("1000"),
    (Unit.PERCENT, Unit.RATIO): Decimal("0.01"),
    (Unit.RATIO, Unit.PERCENT): Decimal("100"),
}


def convert(value: Decimal, from_unit: Unit | str, to_unit: Unit | str) -> Decimal:
    """Convert between units of the same dimension. Raises IncompatibleUnits otherwise."""
    f, t = Unit(from_unit), Unit(to_unit)
    if f == t:
        return value
    try:
        return value * _FACTORS[(f, t)]
    except KeyError as e:
        raise IncompatibleUnits(f"cannot convert {f} to {t} without a quantity") from e


def blocks_per_day(minutes: int = 15) -> int:
    return 24 * 60 // minutes


def kwh_from_kw_block(kw: Decimal, minutes: int = 15) -> Decimal:
    """Energy in a block from average power: kW × hours."""
    return kw * Decimal(minutes) / Decimal(60)
