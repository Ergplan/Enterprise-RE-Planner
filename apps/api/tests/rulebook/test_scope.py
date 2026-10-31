from datetime import date

from ergplan.rulebook.scope import matches, norm_code


def test_norm_code() -> None:
    assert norm_code("HV-2") == norm_code("hv 2") == norm_code("HV – 2") == "HV2"
    assert norm_code("HT-I (A)") == "HTIA"


def test_bands_inclusive_and_exclusive() -> None:
    at11 = {"voltage_kv": {"min": 11, "max": 11}}
    above11 = {"voltage_kv": {"min": 11, "min_exclusive": True}}
    assert matches(at11, {"voltage_kv": 11}) and not matches(at11, {"voltage_kv": 33})
    assert matches(above11, {"voltage_kv": 33}) and not matches(above11, {"voltage_kv": 11})


def test_strict_when_context_lacks_a_constrained_field() -> None:
    assert not matches({"voltage_kv": {"min": 11}}, {"category": "HV-2"})
    assert matches({}, {})


def test_sources_lists_months_and_dates() -> None:
    assert matches({"source": ["any_re"]}, {"source": "wind"})
    assert not matches({"source": ["any_re"]}, {"source": "thermal"})
    assert matches({"source": ["any"]}, {"source": "thermal"})
    assert matches({"connection": ["ists"]}, {"connection": "ists"})
    assert not matches({"connection": ["ists"]}, {"connection": "intra_state"})
    assert matches({"months": [4, 5, 6]}, {"month": 5}) and not matches({"months": [4]}, {"month": 5})
    band = {"commissioned": {"from": "2025-07-01", "to": "2026-06-30"}}
    assert matches(band, {"commissioned": date(2025, 12, 1)}) and not matches(
        band, {"commissioned": "2026-07-01"}
    )


def test_unknown_scope_key_never_matches() -> None:
    assert not matches({"planet": ["mars"]}, {"planet": "mars"})
