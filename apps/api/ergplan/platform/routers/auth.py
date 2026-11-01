"""Sign-in (Stage 8). By email and password (POST /auth/login), or by a one-time email link
(POST /auth/request sends it, 15 minutes; POST /auth/verify turns it into a session). Either way the
session is a cookie (30 days, HttpOnly, Secure on https). A signed-in person sets or changes their
password with POST /auth/password; an analyst adds a person with a first password (POST /auth/users)."""

from __future__ import annotations

import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from ...core.settings import get_settings
from ...db.base import session_scope
from ...db.models import AuthSession, LoginToken, User
from .. import mail
from ..auth import COOKIE, Caller, analyst, caller, production, role_for, sha
from ..passwords import MIN_LENGTH, hash_password, verify_password

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
    has_password: bool = False


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(pattern=r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$")
    password: str = Field(min_length=1, max_length=200)


class PasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=MIN_LENGTH, max_length=200)
    current: str | None = Field(default=None, max_length=200)


class UserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(pattern=r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$")
    password: str = Field(min_length=MIN_LENGTH, max_length=200)


class UserOut(BaseModel):
    email: str
    role: str


# failed password attempts per email in this process: more than FAIL_LIMIT in FAIL_WINDOW is refused
FAIL_LIMIT = 10
FAIL_WINDOW = timedelta(minutes=15)
_failures: dict[str, list[datetime]] = {}


def _start_session(s: Any, user: User, response: Response, now: datetime) -> MeOut:
    user.last_login_at = now
    s.flush()
    cookie = secrets.token_urlsafe(32)
    s.add(
        AuthSession(token_sha256=sha(cookie), email=user.email, expires_at=now + timedelta(days=SESSION_DAYS))
    )
    response.set_cookie(
        COOKIE,
        cookie,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        secure=secure_cookie(),
        samesite="lax",
        path="/",
    )
    return MeOut(email=user.email, role=user.role, signed_in=True, has_password=bool(user.password_hash))


def secure_cookie() -> bool:
    """Secure whenever the site is served over https (a LAN server on plain http cannot set one)."""
    return get_settings().ergplan_public_url.startswith("https://")


def issue_link(email: str, next_path: str = "/plan/intake", actor: str | None = None) -> str:
    """A one-time sign-in link for an email (15 minutes); only its SHA-256 is stored. Used by
    /auth/request and by the server operator's `python -m ergplan.platform.signin`."""
    email = email.strip().lower()
    token = secrets.token_urlsafe(32)
    with session_scope(actor=actor or email) as s:
        s.add(
            LoginToken(
                token_sha256=sha(token),
                email=email,
                expires_at=datetime.now(UTC) + timedelta(minutes=LINK_MINUTES),
            )
        )
    return f"{get_settings().ergplan_public_url.rstrip('/')}/login/verify?token={token}&next={next_path}"


@router.post("/request", response_model=RequestOut)
def request_link(body: RequestIn) -> RequestOut:
    email = body.email.strip().lower()
    if production() and not get_settings().ergplan_smtp_url:
        # no way to deliver the link: say so rather than claim it was sent
        raise HTTPException(
            503, "sign-in mail is not set up on this server (ERGPLAN_SMTP_URL); ask jouleWise for a link"
        )
    link = issue_link(email, body.next)
    try:
        sent = mail.send(
            email,
            "Your ergPLAN sign-in link",
            f"Open this link to sign in to ergPLAN (it works once, for {LINK_MINUTES} minutes):\n\n{link}\n\n"
            "If you did not ask for it, ignore this message.\n\njouleWise",
        )
    except (OSError, smtplib.SMTPException) as e:  # the mail server refused or could not be reached
        raise HTTPException(502, "the sign-in mail could not be sent; try again shortly") from e
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
        return _start_session(s, user, response, now)


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, response: Response) -> MeOut:
    now = datetime.now(UTC)
    email = body.email.strip().lower()
    recent = [t for t in _failures.get(email, []) if now - t < FAIL_WINDOW]
    if len(recent) >= FAIL_LIMIT:
        raise HTTPException(429, "too many wrong passwords; wait 15 minutes or ask for a sign-in link")
    with session_scope(actor="auth") as s:
        user = s.get(User, email)
        if user is None or not verify_password(body.password, user.password_hash):
            _failures[email] = [*recent, now]
            raise HTTPException(401, "that email and password do not match")
        _failures.pop(email, None)
        return _start_session(s, user, response, now)


@router.post("/password", response_model=MeOut)
def set_password(body: PasswordIn, who: Annotated[Caller, Depends(caller)]) -> MeOut:
    """Set or change the signed-in person's password (the current one is needed to change it)."""
    if not who.signed_in:
        raise HTTPException(401, "sign in first")
    with session_scope(actor=who.actor) as s:
        user = s.get(User, who.actor)
        if user is None:  # development headers: a person not yet in users
            user = User(email=who.actor, role=role_for(who.actor))
            s.add(user)
        if user.password_hash and not verify_password(body.current or "", user.password_hash):
            raise HTTPException(403, "the current password is not right")
        user.password_hash = hash_password(body.password)
        return MeOut(email=user.email, role=user.role, signed_in=True, has_password=True)


@router.post("/users", response_model=UserOut, status_code=201)
def add_user(body: UserIn, who: Annotated[Caller, Depends(analyst)]) -> UserOut:
    """An analyst adds a person (or resets their password) and tells them the first password."""
    email = body.email.strip().lower()
    with session_scope(actor=who.actor) as s:
        user = s.get(User, email)
        if user is None:
            user = User(email=email, role=role_for(email))
            s.add(user)
        user.password_hash = hash_password(body.password)
        return UserOut(email=user.email, role=user.role)


@router.get("/me", response_model=MeOut)
def me(who: Annotated[Caller, Depends(caller)]) -> MeOut:
    has = False
    if who.signed_in:
        with session_scope() as s:
            u = s.get(User, who.actor)
            has = bool(u and u.password_hash)
    return MeOut(
        email=who.actor if who.signed_in else None,
        role=who.role,
        signed_in=who.signed_in,
        required=production(),
        has_password=has,
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
