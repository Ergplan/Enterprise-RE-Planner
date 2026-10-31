from ergplan.regreader.grounding import numbers_in, quote_on_page, ungrounded_numbers

PAGE = """BASE RATE
Demand Charges Rs. 300.00 / kVA /
month
Rs. 290.00 / kVA /
month
Energy Charges Rs. 7.10 / kVAh Rs. 6.80 / kVAh Rs. 6.40 / kVAh Rs. 6.10 / kVAh
19:00 hrs – 02:00 hrs (+) 15%"""


def test_quote_whole_and_fragments() -> None:
    assert quote_on_page("Energy Charges Rs. 7.10 / kVAh Rs. 6.80 / kVAh", PAGE)
    assert quote_on_page(
        "BASE RATE ... Demand Charges Rs. 300.00 / kVA / ... Energy Charges Rs. 7.10 / kVAh", PAGE
    )
    assert quote_on_page("19:00 hrs - 02:00 hrs (+) 15%", PAGE)  # en dash vs hyphen
    assert not quote_on_page("Energy Charges Rs. 7.20 / kVAh", PAGE)
    assert not quote_on_page("BASE ... RATE", PAGE)  # fragments too short
    assert not quote_on_page("short", PAGE)


def test_numbers_must_be_printed() -> None:
    body = {
        "demand_charge": {"value": "300", "basis": "inr_per_kva_month"},
        "energy_charge": {"base": "7.10"},
    }
    assert ungrounded_numbers(body, [PAGE]) == []
    assert ungrounded_numbers({"energy_charge": {"base": "7.15"}}, [PAGE]) == ["7.15"]
    assert numbers_in({"a": ["1", {"b": "2.5 kV"}], "c": 3, "category": "HV-2"}) == ["1", "3"]
