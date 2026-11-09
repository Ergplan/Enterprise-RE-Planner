"""The voice's (and text chat's) tools. Voice is a mouth, not a mind: intake tools set `SiteIntake`
fields (Stage 2 schemas) one at a time on a draft the browser holds; plan tools add a change to the
what-if and run it (report.whatif). Every tool returns the new state and one sentence to read back,
built from the values it set or the numbers the engines returned."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..intake import defaults
from ..intake.profile_synthesis import shape_ids
from ..intake.site_intake import SiteIntake

SHAPES = tuple(shape_ids())


class ToolError(ValueError):
    pass


# ---------------------------------------------------------------- arguments


class _A(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Text(_A):
    value: str = Field(min_length=1, max_length=120)


STATES = tuple(sorted(set(defaults.DISCOM_STATE.values())))


class StateArg(_A):
    value: str = Field(description=f"state code, one of: {', '.join(STATES)}")


class Discom(_A):
    value: str = Field(
        description="DISCOM id, one of: "
        + ", ".join(sorted(defaults.DISCOM_STATE))
        + " (or its printed name)"
    )


class Num(_A):
    value: Decimal = Field(gt=0)


class Shape(_A):
    value: str = Field(description=f"one of: {', '.join(shape_ids())}")


class Days(_A):
    days: list[int] = Field(description="weekly off days, 0 = Monday … 6 = Sunday", max_length=7)


class Month(_A):
    month: str = Field(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")
    energy_kwh: Decimal = Field(gt=0)
    max_kva: Decimal | None = Field(default=None, gt=0)
    bill_inr: Decimal | None = Field(default=None, gt=0)


class MonthKey(_A):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")


class Empty(_A):
    pass


class Price(_A):
    source: str = Field(description="source kind, e.g. oa_solar_intra")
    inr_per_kwh: Decimal = Field(gt=0, lt=50)


class Capacity(_A):
    source: str
    mw: Decimal = Field(ge=0, lt=500)


class Toggle(_A):
    source: str
    on: bool


class RulesDate(_A):
    on: date


# ---------------------------------------------------------------- intake


def _fact(v: Any) -> dict[str, Any]:
    return {"value": v, "provenance": "client_stated"}


def _set(field: str, cast: Callable[[Any], Any] = lambda v: v) -> Callable[[dict[str, Any], Any], str]:
    def run(state: dict[str, Any], a: Any) -> str:
        state[field] = _fact(cast(a.value))
        return f"{field.replace('_', ' ').capitalize()} set to {a.value}."

    return run


def _state(state: dict[str, Any], a: StateArg) -> str:
    code = a.value.strip().upper()
    if code not in STATES:
        raise ToolError(f"the state must be one of {', '.join(STATES)}")
    state["state"] = _fact(code)
    return f"State set to {code}."


def _discom(state: dict[str, Any], a: Discom) -> str:
    d = a.value.strip().lower()
    if defaults.state_of(d) is None:
        d = defaults.discom_from_name(a.value) or d
    st = defaults.state_of(d)
    if st is None:
        raise ToolError(f"I don't know the DISCOM {a.value}")
    state["discom"] = _fact(d)
    state.setdefault("state", _fact(st))
    return f"DISCOM set to {d.upper()}."


def _shape(state: dict[str, Any], a: Shape) -> str:
    if a.value not in SHAPES:
        raise ToolError(f"the pattern must be one of {', '.join(SHAPES)}")
    state["industry_shape"] = _fact(a.value)
    return f"Operating pattern set to {a.value.replace('_', ' ')}."


def _days(state: dict[str, Any], a: Days) -> str:
    if any(not 0 <= d <= 6 for d in a.days):
        raise ToolError("days are 0 (Monday) to 6 (Sunday)")
    state["weekly_off"] = _fact(sorted(set(a.days)))
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return "Weekly off: " + (", ".join(names[d] for d in sorted(set(a.days))) or "none") + "."


def _month(state: dict[str, Any], a: Month) -> str:
    months = [m for m in state.get("months", []) if m["month"][:7] != a.month]
    m: dict[str, Any] = {"month": f"{a.month}-01", "energy": _fact(str(a.energy_kwh))}
    if a.max_kva is not None:
        m["max_kva"] = _fact(str(a.max_kva))
    if a.bill_inr is not None:
        m["bill_inr"] = _fact(str(a.bill_inr))
    months.append(m)
    state["months"] = sorted(months, key=lambda x: x["month"])
    extra = f", maximum demand {a.max_kva} kVA" if a.max_kva is not None else ""
    return f"{a.month}: {a.energy_kwh} kWh{extra}."


def _remove_month(state: dict[str, Any], a: MonthKey) -> str:
    state["months"] = [m for m in state.get("months", []) if m["month"][:7] != a.month]
    return f"{a.month} removed."


REQUIRED = (
    "client_name",
    "site_name",
    "state",
    "discom",
    "category",
    "voltage_kv",
    "contract_demand_kva",
    "industry_shape",
    "weekly_off",
)


def _check(state: dict[str, Any], a: Empty) -> str:
    missing = [f.replace("_", " ") for f in REQUIRED if f not in state]
    if not state.get("months"):
        missing.append("at least one month's units")
    if missing:
        return "Still needed: " + ", ".join(missing) + "."
    try:
        SiteIntake.model_validate(state)
    except ValidationError as e:
        first = e.errors()[0]
        return f"Something does not fit: {first['msg']}."
    return "The site description is complete."


# ---------------------------------------------------------------- plan (what-if)


def _wi(state: dict[str, Any]) -> dict[str, Any]:
    w: dict[str, Any] = state.setdefault("whatif", {})
    return w


def _price(state: dict[str, Any], a: Price) -> str:
    _wi(state).setdefault("prices", {})[a.source] = str(a.inr_per_kwh)
    return ""


def _capacity(state: dict[str, Any], a: Capacity) -> str:
    _wi(state).setdefault("capacities_mw", {})[a.source] = str(a.mw)
    return ""


def _cd(state: dict[str, Any], a: Num) -> str:
    _wi(state)["contract_demand_kva"] = str(a.value)
    return ""


def _toggle(state: dict[str, Any], a: Toggle) -> str:
    off = set(_wi(state).get("off", []))
    (off.discard if a.on else off.add)(a.source)
    _wi(state)["off"] = sorted(off)
    return ""


def _rules_date(state: dict[str, Any], a: RulesDate) -> str:
    _wi(state)["as_of"] = a.on.isoformat()
    return ""


def _reset(state: dict[str, Any], a: Empty) -> str:
    state["whatif"] = {}
    return ""


class Tool:
    def __init__(
        self, name: str, description: str, args: type[BaseModel], run: Callable[..., str], mode: str
    ):
        self.name, self.description, self.args, self.run, self.mode = name, description, args, run, mode

    def spec(self) -> dict[str, Any]:
        schema = self.args.model_json_schema()
        schema.pop("title", None)
        return {"type": "function", "name": self.name, "description": self.description, "parameters": schema}


TOOLS: list[Tool] = [
    Tool("set_client_name", "The client company's name", Text, _set("client_name"), "intake"),
    Tool("set_site_name", "The site's name or town", Text, _set("site_name"), "intake"),
    Tool("set_state", "The state the site is in (code)", StateArg, _state, "intake"),
    Tool("set_discom", "The distribution company", Discom, _discom, "intake"),
    Tool(
        "set_category",
        "The tariff category printed on the bill, e.g. HV-2 or HT I(A)",
        Text,
        _set("category"),
        "intake",
    ),
    Tool("set_voltage_kv", "Supply voltage in kV", Num, _set("voltage_kv", str), "intake"),
    Tool(
        "set_contract_demand_kva", "Contract demand in kVA", Num, _set("contract_demand_kva", str), "intake"
    ),
    Tool(
        "set_consumer_number",
        "The consumer or account number on the bill",
        Text,
        _set("consumer_number"),
        "intake",
    ),
    Tool("set_industry_shape", "How the plant runs across the day", Shape, _shape, "intake"),
    Tool("set_weekly_off", "Days the plant does not run", Days, _days, "intake"),
    Tool("set_roof_sqm", "Usable roof area in square metres", Num, _set("roof_sqm", str), "intake"),
    Tool("set_land_acres", "Free land in acres", Num, _set("land_acres", str), "intake"),
    Tool(
        "set_month",
        "One month's units (kWh) from a bill, with maximum demand and amount if known",
        Month,
        _month,
        "intake",
    ),
    Tool("remove_month", "Remove a month given by mistake", MonthKey, _remove_month, "intake"),
    Tool("check_intake", "What is still missing from the site description", Empty, _check, "intake"),
    Tool("set_price", "What-if: the price of a source in INR per kWh", Price, _price, "plan"),
    Tool("set_capacity", "What-if: the capacity of a source in MW", Capacity, _capacity, "plan"),
    Tool("set_contract_demand", "What-if: the contract demand in kVA", Num, _cd, "plan"),
    Tool("toggle_source", "What-if: switch a source of the plan on or off", Toggle, _toggle, "plan"),
    Tool(
        "set_rules_date",
        "What-if: use the tariff and open-access rules in force on a date",
        RulesDate,
        _rules_date,
        "plan",
    ),
    Tool("reset_whatif", "Undo every what-if change", Empty, _reset, "plan"),
]
BY_NAME = {t.name: t for t in TOOLS}


def specs(mode: str) -> list[dict[str, Any]]:
    return [t.spec() for t in TOOLS if t.mode == mode]


def apply(name: str, args: dict[str, Any], state: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    """Validate the arguments, apply the tool to a copy of the state: (state, sentence, mode)."""
    t = BY_NAME.get(name)
    if t is None:
        raise ToolError(f"no tool {name}")
    try:
        a = t.args.model_validate(args or {})
    except ValidationError as e:
        raise ToolError(f"{name}: {e.errors()[0]['msg']}") from e
    new = _copy(state)
    say = t.run(new, a)
    return new, say, t.mode


def _copy(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _copy(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_copy(v) for v in x]
    return x
