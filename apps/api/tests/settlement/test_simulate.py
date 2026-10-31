"""Settlement simulator: the hand-worked cases (tests/settlement/cases, mirrored in packages/rulebooks/golden),
and properties on generated years (energy balance in every block, bank never negative, deposits =
withdrawals + lapse over the run)."""

from __future__ import annotations

import random
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from ergplan.core.settings import REPO_ROOT
from ergplan.core.sourced import RefKind, SourcedValue, SourceRef
from ergplan.core.units import Unit
from ergplan.rulebook.models import RuleView
from ergplan.settlement.simulate import Bank, Block, SourceIn, simulate, statement

CASES = Path(__file__).parent / "cases"
STATES = REPO_ROOT / "packages" / "rulebooks" / "states"
GOLDEN = REPO_ROOT / "packages" / "rulebooks" / "golden"
D = Decimal


def _rule(spec: dict[str, Any]) -> RuleView:
    if "body" in spec:
        return RuleView(
            id="inline",
            family="settlement",
            version_id="v",
            jurisdiction_id="X",
            scope={},
            body=spec["body"],
            source_ref={"kind": "assumption", "note": "synthetic rule"},
        )
    d = yaml.safe_load((STATES / spec["file"]).read_text())
    row = d["rows"][spec["row"]]
    return RuleView(
        id=f"{d['jurisdiction']}-{spec['row']}",
        family="settlement",
        version_id="v",
        jurisdiction_id=d["jurisdiction"],
        scope=row["scope"],
        body=row["body"],
        source_ref=row["source_ref"],
        field_refs=row.get("field_refs") or {},
    )


def _blocks(rows: list[dict[str, Any]]) -> list[Block]:
    out = []
    for r in rows:
        y, m = (int(x) for x in str(r["month"]).split("-"))
        out.append(
            Block(
                month=date(y, m, 1),
                slot=str(r["slot"]),
                load_kwh=D(str(r["load"])),
                supply_kwh={k: D(str(v)) for k, v in (r.get("supply") or {}).items()},
                classes=frozenset(r.get("classes") or []),
                hour=int(r.get("hour", 0)),
            )
        )
    return out


def _all_cases() -> list[tuple[str, dict[str, Any], dict[str, Any], list[dict[str, Any]]]]:
    out = []
    for f in sorted(CASES.glob("*.yaml")):
        d = yaml.safe_load(f.read_text())
        for c in d["cases"]:
            out.append(
                (f"{f.stem}: {c['name']}", c.get("rule") or d["rule"], c, c.get("sources") or d["sources"])
            )
    return out


@pytest.mark.parametrize(("name", "rule", "case", "sources"), _all_cases(), ids=[c[0] for c in _all_cases()])
def test_case(name: str, rule: dict[str, Any], case: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    srcs = [
        SourceIn(
            id=s["id"], category=s.get("category", "captive_generation"), surplus=s.get("surplus", "bank")
        )
        for s in sources
    ]
    res = simulate(_blocks(case["blocks"]), srcs, _rule(rule))
    e = case["expect"]
    got = {
        "grid": res.total(res.grid_kwh),
        "withdrawn": res.total(res.withdrawn_kwh),
        "banked": sum((res.total(v) for v in res.deposit_kwh.values()), D(0)),
        "charge": sum((res.total(v) for v in res.charge_kwh.values()), D(0)),
        "lapsed": sum((x["kwh"] for x in res.lapsed), D(0)),
        "unbanked": sum((res.total(v) for v in res.unbanked_kwh.values()), D(0)),
    }
    for k in ("grid", "withdrawn", "banked", "charge", "lapsed", "unbanked"):
        if k in e:
            assert got[k] == D(str(e[k])), (k, got)
    for sid, v in (e.get("setoff") or {}).items():
        assert res.total(res.setoff_kwh[sid]) == D(str(v))


@pytest.mark.parametrize("state", ["up", "mh"])
def test_cases_are_mirrored_in_the_golden_folder(state: str) -> None:
    assert (GOLDEN / state / "settlement-cases.yaml").read_text() == (CASES / f"{state}.yaml").read_text()


def _random_year(seed: int, months: int = 3) -> list[Block]:
    rnd = random.Random(seed)
    out = []
    for m in range(months):
        mo = date(2026 + (3 + m) // 12, (3 + m) % 12 + 1, 1)
        for b in range(96 * 3):
            slot = "peak" if 68 <= b % 96 < 88 else ("solar" if 36 <= b % 96 < 68 else "normal")
            out.append(
                Block(
                    month=mo,
                    slot=slot,
                    classes=frozenset({"peak" if slot == "peak" else "off_peak"}),
                    load_kwh=D(rnd.randint(0, 400)) / 4,
                    supply_kwh={
                        "pv": D(rnd.randint(0, 800)) / 4 if slot == "solar" else D(0),
                        "wind": D(rnd.randint(0, 200)) / 4,
                    },
                    hour=(m * 96 * 3 + b) // 4,
                )
            )
    return out


@pytest.mark.parametrize(
    "rule",
    [
        {"file": "up/settlement/UP-v1.yaml", "row": 0},
        {"file": "mh/settlement/msedcl-v2.yaml", "row": 0},
        {
            "body": {
                "granularity": "hourly",
                "banking": {
                    "allowed": True,
                    "buckets": "pooled",
                    "period": "monthly",
                    "carry_over": True,
                    "charge": {"kind": "in_kind_percent", "value": "5"},
                },
            }
        },
        {"body": {"granularity": "monthly_aggregate", "banking": {"allowed": False}}},
    ],
    ids=["up", "msedcl", "hourly", "monthly"],
)
@pytest.mark.parametrize("seed", [1, 2])
def test_properties(rule: dict[str, Any], seed: int) -> None:
    blocks = _random_year(seed)
    srcs = [SourceIn("pv"), SourceIn("wind", category="bilateral")]
    res = simulate(blocks, srcs, _rule(rule))
    tol = D("1e-9")
    for i, b in enumerate(blocks):
        setoff = sum((res.setoff_kwh[s.id][i] for s in srcs), D(0))
        assert (
            abs(b.load_kwh - (setoff + res.withdrawn_kwh[i] + res.grid_kwh[i])) < tol
        )  # every block balances
        for s in srcs:
            used = (
                res.setoff_at_source_kwh[s.id][i]
                + res.deposit_kwh[s.id][i]
                + res.charge_kwh[s.id][i]
                + res.unbanked_kwh[s.id][i]
            )
            assert abs(b.supply_kwh[s.id] - used) < tol
        assert res.grid_kwh[i] >= -tol and res.withdrawn_kwh[i] >= -tol
    deposits = sum((res.total(v) for v in res.deposit_kwh.values()), D(0))
    lapsed = sum((x["kwh"] for x in res.lapsed), D(0))
    assert abs(deposits - (res.total(res.withdrawn_kwh) + lapsed)) < tol  # nothing left after the last period
    assert all(x["kwh"] >= 0 for x in res.balances)


def test_bank_never_goes_negative() -> None:
    bank = Bank(
        _rule({"body": {"granularity": "block_15min", "banking": {"allowed": True, "buckets": "pooled"}}})
    )
    bank.deposit("pool", D(10), 0)
    assert bank.withdraw(["pool"], D(25)) == D(10)
    assert bank.balance() == {}


def test_statement_lines_cite_the_rule() -> None:
    rule = _rule({"file": "up/settlement/UP-v1.yaml", "row": 0})
    res = simulate(
        _blocks(
            [{"month": "2026-04", "slot": "d", "classes": ["off_peak"], "load": 10, "supply": {"pv": 30}}]
        ),
        [SourceIn("pv")],
        rule,
    )
    ref = SourcedValue(
        value=D(10), unit=Unit.KWH, source_refs=(SourceRef(kind=RefKind.DERIVED, note="profile"),)
    )
    lines = statement(
        res,
        rule,
        ref,
        {"pv": ref},
        lapse_price=SourcedValue(
            value=D("1"),
            unit=Unit.INR_PER_KWH,
            source_refs=(SourceRef(kind=RefKind.ASSUMPTION, note="APPC"),),
        ),
    )
    by = {str(x.label): x for x in lines}
    assert by["Consumption"].value == 10 and by["Set off from pv"].value == 10
    assert by["Banking charge in kind"].value == D("1.6") and by["Lapsed"].value == D("18.4")
    assert by["Paid for lapsed energy"].value == D("18.4") and by["Paid for lapsed energy"].unit == Unit.INR
    assert any(r.kind == RefKind.REGULATION and r.page for r in by["Lapsed"].source_refs)
