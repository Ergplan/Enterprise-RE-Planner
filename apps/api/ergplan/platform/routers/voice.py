"""Voice and text chat (Stage 7). The browser opens a WebRTC session to OpenAI Realtime with an
ephemeral secret minted here; when the model calls a tool, the browser posts it to /voice/tool and
sends the result back. Text chat runs the same tools server-side. The tools set intake fields or run
a what-if; the model only takes inputs and reads results back (prompt voice_v1)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ...db.base import session_scope
from ...providers import openai_client
from ...report import share
from ...report.whatif import WhatIf, WhatIfFailed, evaluate
from ...voice import tools as vt
from ..auth import Caller, caller
from .plan import recommended_run

router = APIRouter(tags=["voice"])
PROMPT = ("voice", 1)
MAX_ROUNDS = 4


class SessionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["intake", "plan"]
    token: str | None = None  # the share token, for plan mode


class SessionOut(BaseModel):
    client_secret: str
    expires_at: int
    model: str
    tools: list[dict[str, Any]]


class ToolIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["intake", "plan"]
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    token: str | None = None


class ToolOut(BaseModel):
    state: dict[str, Any]
    say: str
    ok: bool


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["intake", "plan"]
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=40)
    state: dict[str, Any] = Field(default_factory=dict)
    token: str | None = None


class ChatOut(BaseModel):
    reply: str
    state: dict[str, Any]
    tool_results: list[dict[str, Any]]


def _plan_token(token: str | None) -> str:
    if not token:
        raise HTTPException(422, "plan mode needs the plan's share token")
    with session_scope() as s:
        try:
            return share.resolve(s, token).connection_id
        except share.LinkNotFound as e:
            raise HTTPException(404, "this link does not exist or was withdrawn") from e


def run_tool(mode: str, name: str, args: dict[str, Any], state: dict[str, Any], token: str | None) -> ToolOut:
    try:
        new, say, tmode = vt.apply(name, args, state)
    except vt.ToolError as e:
        return ToolOut(state=state, say=str(e), ok=False)
    if tmode != mode:
        return ToolOut(state=state, say=f"{name} is not available now.", ok=False)
    if tmode == "plan":
        cid = _plan_token(token)
        w = new.get("whatif") or {}
        try:
            change = WhatIf.model_validate(
                {
                    **w,
                    "prices": {k: Decimal(v) for k, v in (w.get("prices") or {}).items()},
                    "capacities_mw": {k: Decimal(v) for k, v in (w.get("capacities_mw") or {}).items()},
                }
            )
        except ValueError as e:
            return ToolOut(state=state, say=f"That change does not fit: {e}", ok=False)
        with session_scope() as s:
            run = recommended_run(s, cid)
            try:
                out = evaluate(s, run, change)
            except WhatIfFailed as e:
                return ToolOut(state=new, say=str(e), ok=False)
        new["last_result"] = {"sentence": out["sentence"], "annual": out["annual"]}
        say = out["sentence"]
    return ToolOut(state=new, say=say, ok=True)


@router.post("/voice/session", response_model=SessionOut)
def voice_session(body: SessionIn, who: Annotated[Caller, Depends(caller)]) -> SessionOut:
    if body.mode == "plan":
        _plan_token(body.token)
    specs = vt.specs(body.mode)
    try:
        sec = openai_client.realtime_secret(
            prompt_name=PROMPT[0], prompt_version=PROMPT[1], tools=specs, purpose=f"voice_{body.mode}"
        )
    except openai_client.NoModelConfigured as e:
        raise HTTPException(503, "voice is not configured on this server") from e
    except openai_client.ProviderError as e:
        raise HTTPException(502, str(e)) from e
    return SessionOut(client_secret=sec.value, expires_at=sec.expires_at, model=sec.model, tools=specs)


@router.post("/voice/tool", response_model=ToolOut)
def voice_tool(body: ToolIn) -> ToolOut:
    return run_tool(body.mode, body.name, body.arguments, body.state, body.token)


@router.get("/voice/tools")
def voice_tools(mode: Literal["intake", "plan"]) -> list[dict[str, Any]]:
    return vt.specs(mode)


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    """Text chat with the same tools: the model asks for tools, the API runs them, the model reads back."""
    if body.mode == "plan":
        _plan_token(body.token)
    msgs: list[dict[str, Any]] = [
        {"role": m.get("role", "user"), "content": str(m.get("content", ""))}
        for m in body.messages
        if m.get("role") in ("user", "assistant")
    ]
    state = body.state
    results: list[dict[str, Any]] = []
    specs = vt.specs(body.mode)
    for _ in range(MAX_ROUNDS):
        try:
            turn = openai_client.chat_with_tools(
                prompt_name=PROMPT[0],
                prompt_version=PROMPT[1],
                purpose=f"chat_{body.mode}",
                messages=msgs,
                tools=specs,
            )
        except openai_client.NoModelConfigured as e:
            raise HTTPException(503, "chat is not configured on this server") from e
        except openai_client.ProviderError as e:
            raise HTTPException(502, str(e)) from e
        if not turn.tool_calls:
            return ChatOut(reply=turn.text or "", state=state, tool_results=results)
        msgs.append(
            {
                "role": "assistant",
                "content": turn.text or "",
                "tool_calls": [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {"name": c["name"], "arguments": _json(c["arguments"])},
                    }
                    for c in turn.tool_calls
                ],
            }
        )
        for c in turn.tool_calls:
            out = run_tool(body.mode, c["name"], c["arguments"], state, body.token)
            state = out.state
            results.append({"name": c["name"], "arguments": c["arguments"], "say": out.say, "ok": out.ok})
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": out.say})
    return ChatOut(reply=results[-1]["say"] if results else "", state=state, tool_results=results)


def _json(x: Any) -> str:
    import json

    return json.dumps(x, default=str)
