"""Voice tools: schemas, intake setters (a voice-only intake equals the typed one), errors, and the
Realtime session minted with the transport mocked (no network); one real call marked external."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import httpx
import pytest

from ergplan.core.settings import get_settings
from ergplan.intake.site_intake import Fact, MonthFacts, SiteIntake
from ergplan.providers import openai_client
from ergplan.voice import tools as vt

TYPED = SiteIntake(
    client_name=Fact(value="Acme Castings"),
    site_name=Fact(value="Greater Noida"),
    state=Fact(value="UP"),
    discom=Fact(value="npcl"),
    category=Fact(value="HV-2"),
    voltage_kv=Fact(value=Decimal("33")),
    contract_demand_kva=Fact(value=Decimal("5000")),
    industry_shape=Fact(value="steel_induction"),
    weekly_off=Fact(value=[6]),
    roof_sqm=Fact(value=Decimal("12000")),
    months=[
        MonthFacts(
            month="2026-07-01", energy=Fact(value=Decimal("1950000")), max_kva=Fact(value=Decimal("4100"))
        ),
        MonthFacts(
            month="2026-08-01", energy=Fact(value=Decimal("2010000")), max_kva=Fact(value=Decimal("4200"))
        ),
    ],
)

SPOKEN = [
    ("set_client_name", {"value": "Acme Castings"}),
    ("set_site_name", {"value": "Greater Noida"}),
    ("set_discom", {"value": "NPCL"}),
    ("set_category", {"value": "HV-2"}),
    ("set_voltage_kv", {"value": "33"}),
    ("set_contract_demand_kva", {"value": 5000}),
    ("set_industry_shape", {"value": "steel_induction"}),
    ("set_weekly_off", {"days": [6]}),
    ("set_roof_sqm", {"value": 12000}),
    ("set_month", {"month": "2026-08", "energy_kwh": 2010000, "max_kva": 4200}),
    ("set_month", {"month": "2026-06", "energy_kwh": 1, "max_kva": 1}),
    ("remove_month", {"month": "2026-06"}),
    ("set_month", {"month": "2026-07", "energy_kwh": "1950000", "max_kva": "4100"}),
]


def test_tool_schemas_are_json_schema_functions() -> None:
    for mode in ("intake", "plan"):
        for spec in vt.specs(mode):
            assert spec["type"] == "function" and spec["parameters"]["type"] == "object"
            json.dumps(spec)
    names = {s["name"] for s in vt.specs("intake")}
    assert {"set_discom", "set_month", "check_intake"} <= names
    assert {"set_price", "toggle_source", "set_rules_date"} == {s["name"] for s in vt.specs("plan")} - {
        "set_capacity",
        "set_contract_demand",
        "reset_whatif",
    }


def test_voice_only_intake_equals_the_typed_form() -> None:
    state: dict[str, Any] = {}
    for name, args in SPOKEN:
        state, say, mode = vt.apply(name, args, state)
        assert mode == "intake" and say
    _, say, _ = vt.apply("check_intake", {}, state)
    assert say == "The site description is complete."
    spoken = SiteIntake.model_validate(state)
    assert spoken.model_dump(mode="json") == TYPED.model_dump(mode="json")


def test_tools_refuse_what_does_not_fit() -> None:
    with pytest.raises(vt.ToolError, match="DISCOM"):
        vt.apply("set_discom", {"value": "tata"}, {})
    with pytest.raises(vt.ToolError):
        vt.apply("set_contract_demand_kva", {"value": -5}, {})
    with pytest.raises(vt.ToolError, match="no tool"):
        vt.apply("compute_saving", {}, {})
    _, say, _ = vt.apply("check_intake", {}, {})
    assert say.startswith("Still needed: client name")


def test_plan_tools_accumulate_a_what_if() -> None:
    s, _, mode = vt.apply("set_price", {"source": "oa_solar_intra", "inr_per_kwh": "3.4"}, {})
    s, _, _ = vt.apply("toggle_source", {"source": "btm_bess", "on": False}, s)
    s, _, _ = vt.apply("set_contract_demand", {"value": 4500}, s)
    assert mode == "plan" and s["whatif"] == {
        "prices": {"oa_solar_intra": "3.4"},
        "off": ["btm_bess"],
        "contract_demand_kva": "4500",
    }
    s, _, _ = vt.apply("reset_whatif", {}, s)
    assert s["whatif"] == {}


def test_realtime_session_minted_with_the_transport_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-not-a-key")
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"value": "ek_test", "expires_at": 1793500000})

    sec = openai_client.realtime_secret(
        prompt_name="voice",
        prompt_version=1,
        tools=vt.specs("intake"),
        purpose="voice_intake",
        transport=httpx.MockTransport(handler),
    )
    assert sec.value == "ek_test" and seen["url"].endswith("/v1/realtime/client_secrets")
    sess = seen["body"]["session"]
    assert sess["model"] == get_settings().openai_realtime_model
    assert "never compute" in sess["instructions"] and len(sess["tools"]) == len(vt.specs("intake"))
    assert seen["auth"] == "Bearer sk-test-not-a-key"


@pytest.mark.external
def test_realtime_session_real_call() -> None:
    sec = openai_client.realtime_secret(
        prompt_name="voice", prompt_version=1, tools=vt.specs("intake"), purpose="voice_intake"
    )
    assert sec.value.startswith("ek_")
