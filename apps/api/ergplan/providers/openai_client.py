"""The one place ergPLAN calls a model (rule 9). Typed input and output, a versioned prompt loaded
from providers/prompts/<name>_v<n>.md, bounded retries, and one model_calls row per call (written
in its own transaction so a failed call is still accounted for)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from ..core.settings import get_settings
from ..db.base import session_scope
from ..db.models import ModelCall

PROMPTS = Path(__file__).parent / "prompts"
RETRIES = 3


class ProviderError(RuntimeError):
    pass


class NoModelConfigured(ProviderError):
    pass


@dataclass(frozen=True)
class CallResult:
    data: dict[str, Any]
    call_id: str
    model: str
    prompt: str
    tokens_in: int
    tokens_out: int


def load_prompt(name: str, version: int) -> str:
    p = PROMPTS / f"{name}_v{version}.md"
    if not p.exists():
        raise ProviderError(f"prompt {p.name} not found")
    return p.read_text()


@lru_cache
def _prices() -> dict[str, dict[str, float]]:
    return dict(yaml.safe_load((Path(__file__).parent / "prices.yaml").read_text()))


def price_known(model: str) -> bool:
    return bool(_prices().get(model) or _prices().get(model.rsplit("-", 1)[0]))


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> Decimal:
    p = _prices().get(model) or _prices().get(model.rsplit("-", 1)[0])
    if not p:
        return Decimal("0")
    return (Decimal(str(p["input"])) * tokens_in + Decimal(str(p["output"])) * tokens_out) / Decimal(
        1_000_000
    )


@lru_cache
def _client() -> OpenAI:
    key = get_settings().openai_api_key
    if not key:
        raise NoModelConfigured("OPENAI_API_KEY is not set")
    return OpenAI(api_key=key, max_retries=0, timeout=180)


def _log(row: ModelCall) -> str:
    with session_scope(actor="providers") as s:
        s.add(row)
        s.flush()
        return row.id


def call_json(
    *,
    prompt_name: str,
    prompt_version: int,
    purpose: str,
    user: str,
    model: str | None = None,
    reasoning_effort: str | None = "low",
    ref_type: str | None = None,
    ref_id: str | None = None,
) -> CallResult:
    """System prompt from the versioned file, user content as given, a JSON object back."""
    system = load_prompt(prompt_name, prompt_version)
    model = model or get_settings().openai_model_regreader
    started = datetime.now(UTC)
    last_error = ""
    for attempt in range(RETRIES):
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            }
            if reasoning_effort and model.startswith("gpt-5"):
                kwargs["reasoning_effort"] = reasoning_effort
            r = _client().chat.completions.create(**kwargs)
            tin, tout = r.usage.prompt_tokens if r.usage else 0, r.usage.completion_tokens if r.usage else 0
            text = r.choices[0].message.content or ""
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                _log(
                    ModelCall(
                        provider="openai",
                        model=model,
                        prompt_name=prompt_name,
                        prompt_version=prompt_version,
                        purpose=purpose,
                        tokens_in=tin,
                        tokens_out=tout,
                        cost_usd=cost_usd(model, tin, tout),
                        status="unparseable",
                        ref_type=ref_type,
                        ref_id=ref_id,
                        started_at=started,
                        ended_at=datetime.now(UTC),
                    )
                )
                raise ProviderError("model returned text that is not JSON") from None
            call_id = _log(
                ModelCall(
                    provider="openai",
                    model=model,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                    purpose=purpose,
                    tokens_in=tin,
                    tokens_out=tout,
                    cost_usd=cost_usd(model, tin, tout),
                    status="ok",
                    error=None if price_known(model) else "price unknown: cost recorded as 0",
                    ref_type=ref_type,
                    ref_id=ref_id,
                    started_at=started,
                    ended_at=datetime.now(UTC),
                )
            )
            return CallResult(
                data=data,
                call_id=call_id,
                model=model,
                prompt=f"{prompt_name}_v{prompt_version}",
                tokens_in=tin,
                tokens_out=tout,
            )
        except (RateLimitError, APIConnectionError) as e:
            last_error = type(e).__name__
            time.sleep(min(30, 5 * (attempt + 1)))
        except APIStatusError as e:
            last_error = f"{type(e).__name__} {e.status_code}"
            if e.status_code < 500:
                break
            time.sleep(5 * (attempt + 1))
    _log(
        ModelCall(
            provider="openai",
            model=model,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            purpose=purpose,
            status="failed",
            error=last_error,
            ref_type=ref_type,
            ref_id=ref_id,
            started_at=started,
            ended_at=datetime.now(UTC),
        )
    )
    raise ProviderError(f"model call failed: {last_error}")


# ---------------------------------------------------------------- Stage 7: voice and chat

REALTIME_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"


@dataclass(frozen=True)
class RealtimeSecret:
    value: str
    expires_at: int
    model: str
    call_id: str


def realtime_secret(
    *,
    prompt_name: str,
    prompt_version: int,
    tools: list[dict[str, Any]],
    purpose: str,
    voice: str = "marin",
    transport: Any = None,
) -> RealtimeSecret:
    """Mint an ephemeral Realtime client secret for the browser's WebRTC session. The session's
    instructions are the versioned prompt; its tools are ergPLAN's typed tools (executed by the API).
    The key never leaves the server."""
    import httpx

    key = get_settings().openai_api_key
    if not key:
        raise NoModelConfigured("OPENAI_API_KEY is not set")
    model = get_settings().openai_realtime_model
    body = {
        "session": {
            "type": "realtime",
            "model": model,
            "instructions": load_prompt(prompt_name, prompt_version),
            "tools": tools,
            "tool_choice": "auto",
            "audio": {
                "input": {"transcription": {"model": "gpt-4o-mini-transcribe"}},
                "output": {"voice": voice},
            },
        }
    }
    started = datetime.now(UTC)
    status, error = "ok", None
    try:
        with httpx.Client(transport=transport, timeout=30) as c:
            r = c.post(REALTIME_SECRETS_URL, json=body, headers={"Authorization": f"Bearer {key}"})
        if r.status_code >= 400:
            status, error = "failed", f"HTTP {r.status_code}"
            raise ProviderError(f"realtime session refused: HTTP {r.status_code}")
        d = r.json()
        value = d.get("value") or (d.get("client_secret") or {}).get("value")
        if not value:
            status, error = "failed", "no client secret in the response"
            raise ProviderError("realtime session: no client secret returned")
        expires = int(d.get("expires_at") or (d.get("client_secret") or {}).get("expires_at") or 0)
    except httpx.HTTPError as e:
        status, error = "failed", type(e).__name__
        raise ProviderError(f"realtime session failed: {type(e).__name__}") from e
    finally:
        call_id = _log(
            ModelCall(
                provider="openai",
                model=model,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                purpose=purpose,
                status=status,
                error=error or "session minted; audio usage is billed by OpenAI per session",
                started_at=started,
                ended_at=datetime.now(UTC),
            )
        )
    return RealtimeSecret(value=value, expires_at=expires, model=model, call_id=call_id)


@dataclass(frozen=True)
class ChatTurn:
    text: str | None
    tool_calls: list[dict[str, Any]]  # [{id, name, arguments (dict)}]
    tokens_in: int
    tokens_out: int


def chat_with_tools(
    *,
    prompt_name: str,
    prompt_version: int,
    purpose: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str | None = None,
) -> ChatTurn:
    """One chat turn that may ask for tools (OpenAI function calling). The caller executes the tools
    and calls again with their outputs; the model never computes a number itself (prompt)."""
    system = load_prompt(prompt_name, prompt_version)
    model = model or get_settings().openai_model_explain
    started = datetime.now(UTC)
    fn_tools = [
        {"type": "function", "function": {k: t[k] for k in ("name", "description", "parameters")}}
        for t in tools
    ]
    last_error = ""
    for attempt in range(RETRIES):
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": [{"role": "system", "content": system}, *messages],
                "tools": fn_tools,
            }
            if model.startswith("gpt-5"):
                kwargs["reasoning_effort"] = "low"
            r = _client().chat.completions.create(**kwargs)
            tin, tout = r.usage.prompt_tokens if r.usage else 0, r.usage.completion_tokens if r.usage else 0
            msg = r.choices[0].message
            calls = []
            for tc in msg.tool_calls or []:
                fn = getattr(tc, "function", None)
                if fn is None:
                    continue
                try:
                    args = json.loads(fn.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                calls.append({"id": tc.id, "name": fn.name, "arguments": args})
            _log(
                ModelCall(
                    provider="openai",
                    model=model,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                    purpose=purpose,
                    tokens_in=tin,
                    tokens_out=tout,
                    cost_usd=cost_usd(model, tin, tout),
                    status="ok",
                    started_at=started,
                    ended_at=datetime.now(UTC),
                )
            )
            return ChatTurn(text=msg.content, tool_calls=calls, tokens_in=tin, tokens_out=tout)
        except (RateLimitError, APIConnectionError) as e:
            last_error = type(e).__name__
            time.sleep(min(30, 5 * (attempt + 1)))
        except APIStatusError as e:
            last_error = f"{type(e).__name__} {e.status_code}"
            if e.status_code < 500:
                break
            time.sleep(5 * (attempt + 1))
    _log(
        ModelCall(
            provider="openai",
            model=model,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            purpose=purpose,
            status="failed",
            error=last_error,
            started_at=started,
            ended_at=datetime.now(UTC),
        )
    )
    raise ProviderError(f"chat failed: {last_error}")
