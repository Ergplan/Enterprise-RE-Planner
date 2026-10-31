"""Who is calling. Until Stage 8 (rule 12) identity is two development headers, X-Ergplan-Actor
and X-Ergplan-Role, defaulting to an anonymous client. Analyst endpoints require role analyst.
Stage 8 replaces this module with magic-link sessions; the dependency names stay."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException


@dataclass(frozen=True)
class Caller:
    actor: str
    role: str


def caller(
    x_ergplan_actor: Annotated[str | None, Header()] = None,
    x_ergplan_role: Annotated[str | None, Header()] = None,
) -> Caller:
    return Caller(
        actor=(x_ergplan_actor or "anonymous").strip()[:128], role=(x_ergplan_role or "client").strip()
    )


def analyst(c: Annotated[Caller, Depends(caller)]) -> Caller:
    if c.role != "analyst" or c.actor == "anonymous":
        raise HTTPException(403, "analyst role required")
    return c
