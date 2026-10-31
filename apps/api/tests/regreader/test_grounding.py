from ergplan.regreader.grounding import numbers_in, quote_on_page, semantic_numbers, ungrounded_numbers

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


def test_semantic_zero_and_waiver() -> None:
    page = "the Commission hereby approves the additional surcharge as zero. Wheeling shall not be payable if ..."
    assert ungrounded_numbers(semantic_numbers({"value": "0"}, [page]), [page]) == []
    assert ungrounded_numbers(
        semantic_numbers({"value": "0"}, ["approved as 1.20"]), ["approved as 1.20"]
    ) == ["0"]
    body = {"value": "1.03", "exemptions": [{"condition": "other", "waived_pct": "100"}]}
    assert ungrounded_numbers(semantic_numbers(body, [page + " 1.03"]), [page + " 1.03"]) == []
    assert ungrounded_numbers(semantic_numbers({"value": "0.00"}, ["value 5"]), ["value 5"]) == ["0.00"]


def test_ocr_interleaved_columns() -> None:
    page = "Renewable Banking of energy subject to a | Carry forward on monthly basis Energy maximum ceiling of 25% of | subject to the ceiling"
    assert quote_on_page("Banking of energy subject to a maximum ceiling of 25% of", page, ocr=True)
    assert not quote_on_page("Banking of energy subject to a maximum ceiling of 25% of", page, ocr=False)
    assert not quote_on_page("Banking of energy subject to a maximum ceiling of 35% of", page, ocr=True)


def test_negative_values_are_checked_by_magnitude() -> None:
    assert ungrounded_numbers({"rate_delta": "-15"}, ["07:00 hrs - 16:00 hrs (-) 15%"]) == []
    assert (
        ungrounded_numbers({"rate_delta": "-16"}, ["07:00 hrs - 16:00 hrs (-) 15%"]) == []
    )  # 16 is on the page
    assert ungrounded_numbers({"rate_delta": "-17"}, ["07:00 hrs - 16:00 hrs (-) 15%"]) == ["-17"]
