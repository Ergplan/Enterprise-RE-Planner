"""Sign-in by email link (Stage 8). POST /auth/request sends a one-time link (15 minutes);
POST /auth/verify turns it into a session cookie (30 days, HttpOnly, Secure in production)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from ...core.settings import get_settings
from ...db.base import session_scope
from ...db.models import AuthSession, LoginToken, User
from .. import mail
from ..auth import COOKIE, Caller, caller, production, role_for, sha

router = APIRouter(prefix="/auth", tags=["sign-in"])
LINK_MINUTES = 15
SESSION_DAYS = 30


class RequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(pattern=r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$")
    next: str = Field(default="/plan/intake", pattern=r"^/[^\s]{0,200}$")


class RequestOut(BaseModel):
    sent: bool
    dev_link: str | None = None  # development only, when no SMTP is configured


class VerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=200)


class MeOut(BaseModel):
    email: str | None
    role: str
    signed_in: bool
    required: bool = False  # production: sign-in needed outside the shared plan


@router.post("/request", response_model=RequestOut)
def request_link(body: RequestIn) -> RequestOut:
    email = body.email.strip().lower()
    token = secrets.token_urlsafe(32)
    with session_scope(actor=email) as s:
        s.add(
            LoginToken(
                token_sha256=sha(token),
                email=email,
                expires_at=datetime.now(UTC) + timedelta(minutes=LINK_MINUTES),
            )
        )
    link = f"{get_settings().ergplan_public_url.rstrip('/')}/login/verify?token={token}&next={body.next}"
    sent = mail.send(
        email,
        "Your ergPLAN sign-in link",
        f"Open this link to sign in to ergPLAN (it works once, for {LINK_MINUTES} minutes):\n\n{link}\n\n"
        "If you did not ask for it, ignore this message.\n\njouleWise",
    )
    return RequestOut(sent=sent, dev_link=None if sent or production() else link)


@router.post("/verify", response_model=MeOut)
def verify(body: VerifyIn, response: Response) -> MeOut:
    now = datetime.now(UTC)
    with session_scope(actor="auth") as s:
        t = s.get(LoginToken, sha(body.token))
        if t is None or t.used_at is not None or t.expires_at < now:
            raise HTTPException(401, "this link has expired or was used; ask for a new one")
        t.used_at = now
        user = s.get(User, t.email)
        if user is None:
            user = User(email=t.email, role=role_for(t.email))
            s.add(user)
        user.last_login_at = now
        s.flush()
        cookie = secrets.token_urlsafe(32)
        s.add(
            AuthSession(
                token_sha256=sha(cookie), email=user.email, expires_at=now + timedelta(days=SESSION_DAYS)
            )
        )
        role = user.role
        email = user.email
    response.set_cookie(
        COOKIE,
        cookie,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        secure=production(),
        samesite="lax",
        path="/",
    )
    return MeOut(email=email, role=role, signed_in=True)


@router.get("/me", response_model=MeOut)
def me(who: Annotated[Caller, Depends(caller)]) -> MeOut:
    return MeOut(
        email=who.actor if who.signed_in else None,
        role=who.role,
        signed_in=who.signed_in,
        required=production(),
    )


@router.post("/logout", response_model=MeOut)
def logout(response: Response, who: Annotated[Caller, Depends(caller)]) -> MeOut:
    if who.signed_in:
        with session_scope(actor=who.actor) as s:
            for row in s.query(AuthSession).filter(
                AuthSession.email == who.actor, AuthSession.revoked_at.is_(None)
            ):
                row.revoked_at = datetime.now(UTC)
    response.delete_cookie(COOKIE, path="/")
    return MeOut(email=None, role="client", signed_in=False)
