"""The element catalogue and code_for (build prompt 5.7)."""

from __future__ import annotations

from billx.reader.identify.profiles import Discom, ProfileVersion, common, profiles
from billx.reader.normalize.codes import OTHER, catalogue, code_for


def test_catalogue_is_the_closed_list_of_5_7():
    codes = catalogue()
    assert codes[0] == "energy_charge" and codes[-1] == OTHER
    assert {
        "fppca",
        "electricity_duty",
        "cess",
        "tod_rebate",
        "tod_surcharge",
        "meter_rent",
        "gas_charge",
        "vat",
    } <= set(codes)
    assert len(codes) == len(set(codes))


def test_every_label_map_code_is_in_the_catalogue():
    codes = set(catalogue())
    for entry in common()["label_map"]:
        assert entry["code"] in codes, entry
    p = profiles()
    for discom in p.discoms.values():
        for entry in discom.label_map:
            assert entry["code"] in codes, (discom.id, entry)
    for versions in p.versions.values():
        for v in versions:
            for entry in v.label_map:
                assert entry["code"] in codes, (v.id, entry)


def test_code_for_common_labels():
    assert code_for(None, "Energy Charges") == "energy_charge"
    assert code_for("A", "TOD Surcharge (Peak Hours)") == "tod_surcharge"
    assert code_for(None, "TOD Rebate (Off Peak Hours)") == "tod_rebate"
    assert code_for(None, "Fixed Charges (on Billing Demand)") == "demand_charge"
    assert code_for(None, "Fuel Surcharge") == "fppca"
    assert code_for(None, "FPPCA") == "fppca"
    assert code_for(None, "Electricity Duty") == "electricity_duty"
    assert code_for(None, "Water Conservation Cess") == "cess"
    assert code_for(None, "Meter Rent") == "meter_rent"
    assert code_for(None, "VAT @ 5%") == "vat"
    assert code_for(None, "Transportation Charges") == "transport"
    assert code_for(None, "Something Unknown") == OTHER
    assert code_for("Arrears", "Previous dues") == "arrears"


def test_version_then_discom_then_common():
    discom = Discom(
        id="x",
        name="x",
        state=None,
        bill_type="electricity",
        match=(),
        extends=None,
        label_map=({"pattern": "special", "code": "cess"},),
        path=profiles().root,
    )
    version = ProfileVersion(
        discom=discom,
        version="v",
        effective_from="2025-01",
        status="draft",
        label_map=(
            {"pattern": "special", "code": "fppca"},
            {"pattern": "bogus", "code": "not_a_code"},
        ),
    )
    assert code_for(None, "Special levy", version) == "fppca"
    assert (
        code_for(
            None,
            "Special levy",
            ProfileVersion(discom=discom, version="v", effective_from="2025-01", status="draft"),
        )
        == "cess"
    )
    assert code_for(None, "Special levy") == OTHER
    assert (
        code_for(None, "bogus", version) == OTHER
    )  # a code outside the catalogue is never returned


def test_synthetic_truth_codes_agree_with_code_for():
    from _checks_support import electricity_truths, gas_truths

    for truth in electricity_truths() + gas_truths():
        for c in truth["charges"]:
            assert code_for(None, c["label"]) == c["code"], c["label"]
