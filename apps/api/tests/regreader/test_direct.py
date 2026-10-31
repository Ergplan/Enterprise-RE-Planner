"""The direct reader with the model call stubbed: grounding and schema decide what is accepted."""

from typing import Any

import pytest

from ergplan.db.base import session_scope
from ergplan.documents import service as documents
from ergplan.providers.openai_client import CallResult
from ergplan.regreader import direct
from tests.fixtures.pdfgen import make_pdf

PAGES = [
    ["RATE SCHEDULE HV - 2"],
    ["For supply up to 11 kV", "Demand Charges Rs. 300.00 / kVA / month", "Energy Charges Rs. 7.10 / kVAh"],
]


def _doc() -> str:
    with session_scope(actor="t") as s:
        d, _ = documents.register(
            s,
            make_pdf(PAGES),
            documents.DocumentMeta(title="Order", regulator="UPERC", jurisdiction="UP"),
            "t",
        )
        return d.id


def _row(energy: str, quote: str, page: int = 2) -> dict[str, Any]:
    return {
        "label": "HV-2 up to 11 kV",
        "scope": {"category": ["HV-2"], "voltage_kv": {"max": 11}},
        "page": page,
        "quote": quote,
        "body": {
            "category": "HV-2",
            "billing_basis": "kvah",
            "demand_charge": {"value": "300.00", "basis": "inr_per_kva_month"},
            "energy_charge": {"base": energy},
        },
    }


def test_reader_accepts_grounded_rows_and_rejects_the_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = _doc()
    rows = [
        _row("7.10", "Demand Charges Rs. 300.00 / kVA / month ... Energy Charges Rs. 7.10 / kVAh"),
        _row("7.15", "Energy Charges Rs. 7.10 / kVAh"),  # number not printed
        _row("7.10", "Energy Charges Rs. 9.99 / kVAh"),  # quote not on page
        _row("7.10", "Energy Charges Rs. 7.10 / kVAh", page=7),  # page not read
        {**_row("7.10", "Energy Charges Rs. 7.10 / kVAh"), "body": {"category": "HV-2"}},  # schema
    ]

    def fake_call(**kw: Any) -> CallResult:
        assert (
            kw["prompt_name"] == "regreader_tariff_schedule" and kw["prompt_version"] == direct.PROMPT_VERSION
        )
        assert "=== PDF page 2 ===" in kw["user"]
        return CallResult(
            data={"rows": rows, "not_found": ["rural"], "notes": "n"},
            call_id="call-1",
            model="gpt-5.1",
            prompt="regreader_tariff_schedule_v2",
            tokens_in=10,
            tokens_out=5,
        )

    monkeypatch.setattr(direct, "call_json", fake_call)
    with session_scope() as s:
        r = direct.read(s, document_id=doc, family="tariff_schedule", jurisdiction_id="npcl", pages=[1, 2])
    assert len(r.accepted) == 1
    acc = r.accepted[0]
    assert acc["source_ref"] == {
        "kind": "order",
        "document_id": doc,
        "page": 2,
        "quote": "Demand Charges Rs. 300.00 / kVA / month ... Energy Charges Rs. 7.10 / kVAh",
    }
    assert acc["review"]["call_id"] == "call-1"
    reasons = [" ".join(x.reasons) for x in r.rejected]
    assert "numbers not printed" in reasons[0] and "7.15" in reasons[0]
    assert "quote not found" in reasons[1]
    assert "was not among the pages read" in reasons[2]
    assert "schema" in reasons[3]
    assert r.not_found == ["rural"]


def test_prompts_exist_for_every_family() -> None:
    from ergplan.providers.openai_client import load_prompt
    from ergplan.rulebook.schemas import FAMILIES

    for fam in FAMILIES:
        assert "Family: " + fam in load_prompt(f"regreader_{fam}", direct.PROMPT_VERSION)
