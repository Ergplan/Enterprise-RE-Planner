"""Contract 1.0's wire shape exactly in esgos-1.0 mode; the 6.5 additions only in 1.1."""

from decimal import Decimal

from billx.core.normalize import normalise
from billx.core.schema import (
    ArrayValue,
    BillResult,
    CheckResult,
    Envelope,
    FileInfo,
    Profile,
    Reading,
    Utility,
    make_value,
)
from billx.platform.api.render import (
    CONTRACT_1_0_BILL_KEYS,
    CONTRACT_1_0_FIELD_KEYS,
    render_envelope,
)


def _v(path, raw, ft="number", unit=None, readers=("text_layer", "model_a")):
    methods = {"text_layer": "text_layer", "local_ocr": "ocr", "model_a": "vision"}
    rs = tuple(
        Reading(
            reader=r,
            method=methods[r],
            family="openai" if r == "model_a" else None,
            raw=raw,
            normalised=normalise(raw, ft),
            page=0,
        )
        for r in readers
    )
    return make_value(path, ft, rs, unit=unit)


def _bill(flags=(), passed=True):
    fields = (
        _v("utility.name", "AVVNL", "text"),
        _v("consumer.account_number", "994927801935", "identifier"),
        _v("period.from", "01-04-2025", "date"),
        _v("period.to", "30-04-2025", "date"),
        _v("period.bill_month", "APR-2025", "month"),
        _v("energy.kwh", "24,77,850.00", unit="kWh"),
        _v("totals.net_payable", "2,43,58,156.60", unit="INR"),
        _v("consumer.name", "Dummy Steel Rolling Mills", "text"),
        _v("totals.current_charges", "2,41,01,777.50", unit="INR"),
    )
    readings = (
        ArrayValue(
            key="KWH | NORMAL",
            fields=(
                _v("readings[0].present", "56545.82"),
                _v("readings[0].past", "56082.94"),
                _v("readings[0].multiplying_factor", "1000"),
                _v("readings[0].consumption", "4,62,880.00"),
            ),
        ),
    )
    return BillResult(
        index=0,
        pages=(1,),
        bill_type="electricity",
        document_type="electricity_bill",
        utility=Utility(id="avvnl", name_as_printed="AVVNL", state="Rajasthan"),
        profile=Profile(id="avvnl", version="2025-01", status="draft"),
        route="template",
        routes_used=("text_layer", "local_ocr"),
        fields=fields,
        arrays=(("readings[]", readings),),
        checks=(
            CheckResult(
                id="G09",
                description="net payable adds up",
                status="pass",
                detects="x",
                expected="24358156.6",
                actual="24358156.6",
                tolerance="1",
                paths=("totals.net_payable",),
                proves=("totals.net_payable",),
                equality=True,
            ),
        ),
        passed=passed,
        status="passed" if passed else "needs_review",
        flags=tuple(flags),
        accepted=passed,
        accepted_by="engine" if passed else None,
    )


def _env(bill):
    return Envelope(
        contract_version="1.1",
        file=FileInfo(sha256="ab" * 32, pages=1, media_type="application/pdf"),
        bills=(bill,),
        seconds=Decimal("12.5"),
    )


def test_1_0_has_exactly_the_contract_keys_and_no_additions():
    out = render_envelope(_env(_bill()), "esgos-1.0")
    assert out["contract_version"] == "1.0" and out["schema_version"] == "2.0"
    assert set(out) == {
        "contract_version",
        "engine_version",
        "schema_version",
        "file",
        "bills",
        "usage",
        "seconds",
    }
    bill = out["bills"][0]
    assert set(bill) == CONTRACT_1_0_BILL_KEYS
    acct = bill["fields"]["consumer"]["account_number"]
    assert set(acct) == CONTRACT_1_0_FIELD_KEYS
    assert acct["value"] == "994927801935" and acct["page"] == 1 and acct["source"] == "ocr"
    assert bill["fields"]["totals"]["net_payable"]["value"] == "24358156.6"
    assert bill["fields"]["totals"]["net_payable"]["unit"] == "INR"
    # 6.4 additions are not in 1.0
    assert "name" not in bill["fields"]["consumer"]
    assert "current_charges" not in bill["fields"]["totals"]
    # every 1.0 path is present, null where not printed
    assert bill["fields"]["meter"]["number"]["value"] is None
    assert bill["fields"]["readings"][0]["current"]["value"] == "56545.82"
    assert bill["fields"]["readings"][0]["tod_slot"] == "Normal"
    assert bill["fields"]["energy"]["tod"][0]["kwh"]["value"] == "462880"
    assert bill["profile"] == {"id": "avvnl", "version": "2025-01", "status": "draft"}
    assert bill["checks"][0]["id"] == "G09" and bill["passed"] is True
    assert out["seconds"] == "12.5"


def test_1_1_adds_the_optional_fields_only():
    out = render_envelope(_env(_bill()), "esgos-1.1")
    bill = out["bills"][0]
    assert CONTRACT_1_0_BILL_KEYS <= set(bill)
    assert {
        "status",
        "review_reasons",
        "flags",
        "accepted",
        "accepted_by",
        "proof_rule_version",
        "routes_used",
        "document_type",
        "audit_status",
        "elements",
        "tariff_recheck",
        "insights",
    } <= set(bill)
    assert bill["status"] == "passed" and bill["accepted"] and bill["accepted_by"] == "engine"
    assert bill["audit_status"] == "not_audited"
    acct = bill["fields"]["consumer"]["account_number"]
    assert acct["verification"] == "verified" and acct["proof"] == ["consensus"]
    assert acct["readers"] == ["text_layer", "model_a"]
    assert bill["fields"]["consumer"]["name"]["value"] == "DUMMY STEEL ROLLING MILLS"
    assert bill["fields"]["totals"]["current_charges"]["value"] == "24101777.5"


def test_a_printed_inconsistency_passes_in_1_1_and_fails_in_1_0_with_a_note():
    bill = _bill(flags=("printed_inconsistency:G05",))
    v11 = render_envelope(_env(bill), "esgos-1.1")["bills"][0]
    assert v11["passed"] is True and v11["flags"] == ["printed_inconsistency:G05"]
    v10 = render_envelope(_env(bill), "esgos-1.0")["bills"][0]
    assert v10["passed"] is False and "printed_inconsistency:G05" in v10["notes"]
    assert "flags" not in v10


def test_no_float_in_the_rendered_json():
    def walk(x):
        if isinstance(x, float):
            raise AssertionError("float in rendered result")
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        if isinstance(x, list):
            for v in x:
                walk(v)

    walk(render_envelope(_env(_bill()), "esgos-1.1"))
