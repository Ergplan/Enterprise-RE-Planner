"""The evaluation report: Markdown for `docs/accuracy/<date>-<set>.md` and a JSON summary
beside it. Both hold counts, rates, case ids, field paths and check ids only; never a
value, a consumer, or a file name from a real set (golden cases are sha256 prefixes). A
real set is headed `unmeasured` until a held-out set exists (build prompt section 10).
Every number is a Decimal written as a string; no float is written.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from billx.platform.evals.metrics import GroupMetrics

if TYPE_CHECKING:
    from billx.platform.evals.runner import EvalResult


def _s(x) -> str:
    """A cell: Decimal as text, None as a dash."""
    if x is None:
        return "-"
    if isinstance(x, Decimal):
        return format(x, "f")
    return str(x)


def _pair(a, b) -> str:
    return f"{_s(a)} / {_s(b)}"


def _group_row(g: GroupMetrics) -> list[str]:
    layout, kind, route = g.key
    return [
        layout,
        kind,
        route,
        _s(g.n),
        _s(g.bills),
        _s(g.passed),
        _s(g.coverage),
        _s(g.silent_errors),
        _s(g.silent_error_bound),
        _s(g.correct_refusals),
        _s(g.false_refusals),
        _s(g.non_bills_read_as_bills),
        _s(g.needs_review),
        _s(g.declined),
        _s(g.errors),
        _s(g.formula_coverage),
        _pair(g.planted_caught, g.planted_missed),
        _pair(g.cost_median, g.cost_p95),
        _pair(g.seconds_median, g.seconds_p95),
    ]


GROUP_HEADER = [
    "layout",
    "input kind",
    "route",
    "n",
    "bills",
    "passed",
    "coverage",
    "silent errors",
    "bound 3/n",
    "correct refusals",
    "false refusals",
    "non-bills read as bills",
    "needs review",
    "declined",
    "errors",
    "formula coverage",
    "planted caught / missed",
    "cost USD median / p95",
    "seconds median / p95",
]


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def render_markdown(result: EvalResult) -> str:
    m = result.metrics
    t = m.total
    label = " (unmeasured)" if result.unmeasured else ""
    lines = [
        f"# billx eval: {result.set_name}{label}",
        "",
        f"- Date: {result.date}",
        f"- Engine version: {result.engine_version}",
        f"- Set: {result.set_kind}"
        + (
            "; **unmeasured**: real bills, no held-out set exists yet"
            if result.unmeasured
            else "; synthetic bills with known values, not a measure of real-bill accuracy"
        ),
        f"- Cloud model allowed: {'yes' if result.allow_cloud_model else 'no'}; "
        f"budget per bill: {_s(result.max_cost_usd)} USD",
        f"- Cases: {t.n} (bills {t.bills}, non-bills {t.non_bills}, planted {t.planted})",
        f"- Silent errors: {t.silent_errors} in {t.passed} passed bills"
        + (
            f" (true rate below {_s(t.silent_error_bound)} with 95% confidence)"
            if t.silent_error_bound is not None
            else ""
        ),
        f"- False refusals: {t.false_refusals}; correct refusals: {t.correct_refusals}; "
        f"non-bills read as bills: {t.non_bills_read_as_bills}",
        f"- Planted misreads: {t.planted_caught} caught, {t.planted_missed} missed",
        "",
        "## Per layout, input kind and route",
        "",
        *_table(GROUP_HEADER, [_group_row(g) for g in m.groups.values()] + [_group_row(t)]),
        "",
        "## Accuracy over attempted, per field, on passed bills",
        "",
    ]
    for g in list(m.groups.values()) + [t]:
        acc = g.field_accuracy()
        if not acc:
            continue
        lines += [f"### {' / '.join(g.key)} (passed {g.passed})", ""]
        lines += _table(
            ["field", "correct", "attempted", "accuracy"],
            [[p, _s(c), _s(n), _s(r)] for p, (c, n, r) in acc.items()],
        )
        lines.append("")
    lines += ["## Findings", ""]
    lines += _list("Silent errors (case, field)", [f"{i}: {p}" for i, p in t.silent_error_paths])
    lines += _list("False refusals (case)", t.false_refusal_ids)
    lines += _list("Non-bills read as bills (case)", t.non_bills_read_as_bills_ids)
    lines += _list(
        "Planted misreads missed (case, check)", [f"{i}: {c}" for i, c in t.planted_missed_ids]
    )
    lines += _list("Engine errors (case, class)", [f"{i}: {e}" for i, e in t.error_ids])
    return "\n".join(lines) + "\n"


def _list(title: str, items: list[str]) -> list[str]:
    if not items:
        return [f"- {title}: none"]
    return [f"- {title}:"] + [f"  - {x}" for x in items] + [""]


def _group_json(g: GroupMetrics) -> dict:
    return {
        "layout": g.key[0],
        "input_kind": g.key[1],
        "route": g.key[2],
        "n": g.n,
        "bills": g.bills,
        "non_bills": g.non_bills,
        "planted": g.planted,
        "passed": g.passed,
        "needs_review": g.needs_review,
        "declined": g.declined,
        "errors": g.errors,
        "coverage": _j(g.coverage),
        "silent_errors": g.silent_errors,
        "silent_error_paths": [{"case": i, "path": p} for i, p in g.silent_error_paths],
        "silent_error_bound": _j(g.silent_error_bound),
        "correct_refusals": g.correct_refusals,
        "false_refusals": g.false_refusals,
        "false_refusal_ids": list(g.false_refusal_ids),
        "non_bills_read_as_bills": g.non_bills_read_as_bills,
        "non_bills_read_as_bills_ids": list(g.non_bills_read_as_bills_ids),
        "field_accuracy": {
            p: {"correct": c, "attempted": n, "accuracy": _j(r)}
            for p, (c, n, r) in g.field_accuracy().items()
        },
        "elements": g.elements,
        "elements_computable": g.elements_computable,
        "formula_coverage": _j(g.formula_coverage),
        "planted_caught": g.planted_caught,
        "planted_missed": g.planted_missed,
        "planted_missed_ids": [{"case": i, "check": c} for i, c in g.planted_missed_ids],
        "error_ids": [{"case": i, "error": e} for i, e in g.error_ids],
        "cost_usd": {"median": _j(g.cost_median), "p95": _j(g.cost_p95)},
        "seconds": {"median": _j(g.seconds_median), "p95": _j(g.seconds_p95)},
    }


def _j(x: Decimal | None) -> str | None:
    return None if x is None else format(x, "f")


def summary(result: EvalResult) -> dict:
    """The JSON summary: the same counts as the Markdown, Decimals as strings."""
    m = result.metrics
    return {
        "set": result.set_name,
        "set_kind": result.set_kind,
        "unmeasured": result.unmeasured,
        "date": result.date,
        "engine_version": result.engine_version,
        "allow_cloud_model": result.allow_cloud_model,
        "max_cost_usd": _j(result.max_cost_usd),
        "total": _group_json(m.total),
        "groups": [_group_json(g) for g in m.groups.values()],
        "all_planted_caught": m.all_planted_caught,
    }


def write_report(result: EvalResult, path: Path) -> tuple[Path, Path]:
    """Write the Markdown report to `path` and the JSON summary beside it (`.json`)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(result), encoding="utf-8")
    json_path = path.with_suffix(".json")
    json_path.write_text(
        json.dumps(summary(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path, json_path
