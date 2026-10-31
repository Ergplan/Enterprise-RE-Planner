from decimal import Decimal

import pytest

from ergplan.core.money import NotADecimal, inr, to_decimal
from ergplan.core.units import IncompatibleUnits, Unit, convert, kwh_from_kw_block


def test_convert_same_dimension() -> None:
    assert convert(Decimal("4500"), Unit.INR_PER_MWH, Unit.INR_PER_KWH) == Decimal("4.5000")
    assert convert(Decimal("710"), Unit.PAISE_PER_KWH, Unit.INR_PER_KWH) == Decimal("7.10")
    assert convert(Decimal("2.5"), Unit.MW, Unit.KW) == Decimal("2500.0")
    assert convert(Decimal("8"), Unit.PERCENT, Unit.RATIO) == Decimal("0.08")
    assert convert(Decimal("3"), "INR/kWh", "INR/kWh") == Decimal("3")


def test_convert_across_dimensions_refuses() -> None:
    with pytest.raises(IncompatibleUnits):
        convert(Decimal("1"), Unit.INR_PER_MW_MONTH, Unit.INR_PER_KWH)


def test_block_energy() -> None:
    assert kwh_from_kw_block(Decimal("1000")) == Decimal("250")


@pytest.mark.parametrize(
    "raw,expected", [("1,23,456.78", "123456.78"), ("₹ 7.10", "7.10"), ("Rs. 450", "450"), (5, "5")]
)
def test_to_decimal_reads_printed_forms(raw: object, expected: str) -> None:
    assert to_decimal(raw) == Decimal(expected)


@pytest.mark.parametrize("bad", [1.5, True, "abc", "NaN", None])
def test_to_decimal_refuses(bad: object) -> None:
    with pytest.raises(NotADecimal):
        to_decimal(bad)


def test_inr_rounds_half_up_to_paisa() -> None:
    assert inr(Decimal("10.005")) == Decimal("10.01")
