import pytest

from ergplan.regreader.voltage import band_key, parse_band


@pytest.mark.parametrize(
    "text,band",
    [
        ("For supply up to 11 kV", {"max": 11}),
        ("For supply at 11kV", {"min": 11, "max": 11}),
        ("For supply above 11 kV and up to 66 kV", {"min": 11, "min_exclusive": True, "max": 66}),
        ("For supply above 132 kV", {"min": 132, "min_exclusive": True}),
        ("11 kV & above", {"min": 11}),
        ("33 kV", {"min": 33, "max": 33}),
        ("no voltage here", None),
    ],
)
def test_parse_band(text: str, band: dict | None) -> None:
    assert parse_band(text) == band


def test_band_key() -> None:
    assert band_key({"min": 11, "max": 11}) == "11"
    assert band_key({"min": 132, "min_exclusive": True}) == "132"
    assert band_key(None) is None
