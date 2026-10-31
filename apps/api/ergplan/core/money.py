"""Decimal handling for money, energy and rates (rule 15). Never a float in a stored or returned value."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PAISA = Decimal("0.01")
RATE_PLACES = Decimal("0.0001")  # rates in INR/kWh keep four places (a paisa has two)
ENERGY_PLACES = Decimal("0.001")  # kWh to the watt-hour


class NotADecimal(ValueError):
    pass


def to_decimal(value: object) -> Decimal:
    """Parse a value into Decimal. Accepts Decimal, int and numeric strings ("1,23,456.78" too).

    Floats are refused: a float has already lost the printed value.
    """
    if isinstance(value, bool):
        raise NotADecimal("a boolean is not a number")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        raise NotADecimal("floats are not accepted; pass the printed value as a string")
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
        try:
            d = Decimal(text)
        except InvalidOperation as e:
            raise NotADecimal(f"not a number: {value!r}") from e
        if not d.is_finite():
            raise NotADecimal(f"not a finite number: {value!r}")
        return d
    raise NotADecimal(f"cannot read {type(value).__name__} as a number")


def inr(value: Decimal) -> Decimal:
    """Round rupees to the paisa, half up, as bills do."""
    return value.quantize(PAISA, rounding=ROUND_HALF_UP)


def rate(value: Decimal) -> Decimal:
    """Round a per-unit rate to four places for display; computation keeps full precision."""
    return value.quantize(RATE_PLACES, rounding=ROUND_HALF_UP)


def energy(value: Decimal) -> Decimal:
    return value.quantize(ENERGY_PLACES, rounding=ROUND_HALF_UP)
