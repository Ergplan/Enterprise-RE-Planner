"""The audit chat: the assistant reads the client's working against the chain and calls typed tools;
the API runs them (grounding, comparison, overrides, proposals) and the assistant reads back what the
tools said. The model never decides a number (invariant 4): it transcribes figures with their words,
and every check and difference is computed in report.audit."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import AuditMessage, Working, WorkingLine
from ..providers import openai_client
from . import audit
from . import chain as chain_data

PROMPT = ("audit", 1)
MAX_ROUNDS = 5
HISTORY = 30
PAGE_CHARS = 12_000
CONTEXT_CHARS = 60_000

_LINE = {
    "type": "object",
    "properties": {
        "chain_key": {"type": ["string", "null"]},
        "compare": {"type": "string", "enum": ["value", "rate"]},
        "label": {"type": "string"},
        "value": {"type": "string", "description": "the figure exactly as written"},
        "scale": {"type": "string", "enum": list(audit.SCALES)},
        "unit": {"type": "string"},
        "page": {"type": "integer"},
        "quote": {"type": "string", "description": "verbatim words of that page containing the figure"},
    },
    "required": ["chain_key", "compare", "label", "value", "scale", "unit", "page", "quote"],
}
TOOLS: list[dict[str, Any]] = [
    {
        "name": "record_lines",
        "description": "Set figures of a working against links of the chain; the API checks the quote "
        "is on the page and computes each difference.",
        "parameters": {
            "type": "object",
            "properties": {
                "working_id": {"type": "string"},
                "lines": {"type": "array", "items": _LINE, "maxItems": 40},
            },
            "required": ["working_id", "lines"],
        },
    },
    {
        "name": "use_my_figure",
        "description": "Make a recorded line's figure (the client's own price or capacity) the plan's "
        "input in the scenario '(your figures)' and run the plan again.",
        "parameters": {
            "type": "object",
            "properties": {"line_id": {"type": "string"}},
            "required": ["line_id"],
        },
    },
    {
        "name": "set_ownership",
        "description": "Set a source's open-access arrangement in the scenario '(your figures)' and run "
        "the plan again.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string"},
                "ownership": {"type": "string", "enum": ["captive", "group_captive", "third_party"]},
            },
            "required": ["source_id", "ownership"],
        },
    },
    {
        "name": "propose_rule_change",
        "description": "Send a regulatory rate the working states differently (a recorded line compared "
        "by rate) to a jouleWise analyst as a proposed rule change.",
        "parameters": {
            "type": "object",
            "properties": {
                "line_id": {"type": "string"},
                "reason": {"type": "string", "description": "why, in the client's words"},
            },
            "required": ["line_id", "reason"],
        },
    },
    {
        "name": "accept_our_figure",
        "description": "The client accepts the plan's figure for a recorded line.",
        "parameters": {
            "type": "object",
            "properties": {"line_id": {"type": "string"}, "note": {"type": "string"}},
            "required": ["line_id"],
        },
    },
]


def _n(d: Decimal | None) -> str:
    return "—" if d is None else format(d.normalize(), "f")


def _step_line(st: chain_data.ChainStep) -> str:
    rate = f"; rate {_n(st.rate.value)} {st.rate.unit}" if st.rate else ""
    kind = audit.what_kind(st)
    return f"- {st.key} [{kind}] {st.label}: {_n(st.value.value)} {st.value.unit}{rate}"


def chain_text(chain: chain_data.Chain) -> str:
    out = [
        f"Plan: scenario '{chain.scenario}' ({chain.scenario_id}), {chain.discom.upper()}, {chain.state}. "
        f"Settlement rule: {chain.settlement_rule or 'none approved'}."
    ]
    for src in chain.sources:
        out.append(f"\nSource {src.id} — {src.label} ({src.ownership or 'own plant'}), slot {src.slot}:")
        out += [_step_line(st) for st in src.landed]
        if src.landed_total is not None:
            out.append(
                f"- {src.id}.landed [computed] landed cost at the meter: {_n(src.landed_total.value)} INR/kWh"
            )
        out += [_step_line(st) for st in src.energy]
        out += [f"  gap: {g}" for g in src.gaps.values()]
    out.append("\nSite energy and money for the year:")
    out += [_step_line(st) for st in [*chain.energy, *chain.money]]
    return "\n".join(out)


def line_text(line: WorkingLine) -> str:
    diff = (
        f", difference {_n(line.theirs - line.ours)} {line.ours_unit}"
        if line.theirs is not None and line.ours is not None
        else ""
    )
    return (
        f"line {line.id}: '{line.label}' {line.chain_key or '(no link)'} by {line.compare}: theirs "
        f"{_n(line.theirs)}, ours {_n(line.ours)} {line.ours_unit or ''}{diff} — {line.status}"
    )


def context(s: Session, connection_id: str, chain: chain_data.Chain) -> str:
    parts = ["THE CHAIN\n" + chain_text(chain)]
    used = len(parts[0])
    for w in s.scalars(
        select(Working).where(Working.connection_id == connection_id).order_by(Working.created_at)
    ):
        head = f"\nWORKING {w.id}: {w.filename}"
        pages = []
        for p in w.pages:
            text = str(p["text"])[:PAGE_CHARS]
            if used + len(text) > CONTEXT_CHARS:
                pages.append(f"[page {p['page']} ({p['name']}) not shown: too long]")
                continue
            used += len(text)
            pages.append(f"--- page {p['page']} ({p['name']}) ---\n{text}")
        lines = s.scalars(
            select(WorkingLine).where(WorkingLine.working_id == w.id).order_by(WorkingLine.created_at)
        )
        recorded = [line_text(x) for x in lines]
        parts.append("\n".join([head, *pages, "Recorded lines:", *(recorded or ["(none yet)"])]))
    return "\n".join(parts)


@dataclass
class ToolResult:
    say: str
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)


def run_tool(
    s: Session, connection_id: str, chain: chain_data.Chain, name: str, args: dict[str, Any], actor: str
) -> ToolResult:
    try:
        if name == "record_lines":
            w = s.get(Working, str(args.get("working_id")))
            if w is None or w.connection_id != connection_id:
                return ToolResult("No such working for this connection.", False)
            said, ids = [], []
            for raw in args.get("lines") or []:
                try:
                    line = audit.record_line(s, w, chain, audit.LineIn.model_validate(raw), actor)
                except (audit.AuditError, ValidationError) as e:
                    label = raw.get("label") if isinstance(raw, dict) else raw
                    said.append(f"'{label}': refused — {str(e).splitlines()[0]}")
                    continue
                ids.append(line.id)
                said.append(line_text(line))
            return ToolResult("\n".join(said) or "No lines given.", bool(ids), {"line_ids": ids})
        if name == "use_my_figure":
            sc, run_id = audit.use_their_figure(s, connection_id, chain, str(args.get("line_id")), actor)
            return ToolResult(
                f"The figure is now the plan's input in '{sc.name}'; the plan is being run again (run "
                f"{run_id}). The chain refreshes when it is settled.",
                True,
                {"scenario_id": sc.id, "run_id": run_id},
            )
        if name == "set_ownership":
            sc, run_id = audit.set_ownership(
                s, connection_id, chain, str(args.get("source_id")), str(args.get("ownership")), actor
            )
            return ToolResult(
                f"The arrangement is set in '{sc.name}'; the plan is being run again (run {run_id}).",
                True,
                {"scenario_id": sc.id, "run_id": run_id},
            )
        if name == "propose_rule_change":
            p = audit.propose_rule_change(
                s, connection_id, chain, str(args.get("line_id")), str(args.get("reason") or ""), actor
            )
            return ToolResult(
                f"Proposed to a jouleWise analyst: {p.rule_label or p.family} {p.pointer} from "
                f"{_n(p.current)} to {_n(p.proposed)} {p.unit}. The plan changes only if the analyst "
                "accepts it and the changed rule is approved.",
                True,
                {"proposal_id": p.id},
            )
        if name == "accept_our_figure":
            line = audit.accept_ours(s, connection_id, str(args.get("line_id")), args.get("note"))
            return ToolResult(f"Noted: the plan's figure stands for '{line.label}'.", True)
    except audit.AuditError as e:
        return ToolResult(str(e), False)
    return ToolResult(f"Unknown tool {name}.", False)


def _history(s: Session, connection_id: str) -> list[dict[str, Any]]:
    rows = list(
        s.scalars(
            select(AuditMessage)
            .where(AuditMessage.connection_id == connection_id, AuditMessage.role.in_(("user", "assistant")))
            .order_by(AuditMessage.created_at.desc())
            .limit(HISTORY)
        )
    )
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def converse(
    s: Session, connection_id: str, scenario_id: str | None, message: str, actor: str
) -> tuple[str, list[dict[str, Any]]]:
    """One user message: the assistant's reply and what its tools did. Every turn is kept."""
    chain = chain_data.build(s, connection_id, scenario_id)
    msgs: list[dict[str, Any]] = [
        {"role": "user", "content": context(s, connection_id, chain)},
        {"role": "assistant", "content": "I have the chain and the workings."},
        *_history(s, connection_id),
        {"role": "user", "content": message},
    ]
    s.add(AuditMessage(connection_id=connection_id, role="user", content=message, actor=actor))
    results: list[dict[str, Any]] = []
    reply = ""
    for _ in range(MAX_ROUNDS):
        turn = openai_client.chat_with_tools(
            prompt_name=PROMPT[0], prompt_version=PROMPT[1], purpose="audit_chat", messages=msgs, tools=TOOLS
        )
        if not turn.tool_calls:
            reply = turn.text or ""
            break
        msgs.append(
            {
                "role": "assistant",
                "content": turn.text or "",
                "tool_calls": [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], default=str)},
                    }
                    for c in turn.tool_calls
                ],
            }
        )
        for c in turn.tool_calls:
            out = run_tool(s, connection_id, chain, c["name"], c["arguments"], actor)
            s.flush()
            results.append({"name": c["name"], "say": out.say, "ok": out.ok, **out.data})
            s.add(
                AuditMessage(
                    connection_id=connection_id,
                    role="action",
                    content=out.say,
                    data={"tool": c["name"], "ok": out.ok, **out.data},
                    actor=actor,
                )
            )
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": out.say})
    else:
        reply = results[-1]["say"] if results else ""
    s.add(AuditMessage(connection_id=connection_id, role="assistant", content=reply, actor="audit assistant"))
    return reply, results
