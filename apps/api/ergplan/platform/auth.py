"""Who is calling, and may they (Stage 8; rule 12).

Production (`ERGPLAN_ENV` other than `dev`): identity is a session cookie set by the email magic link
(`ergplan_session`, HttpOnly; only its SHA-256 is stored). Development keeps the two headers
X-Ergplan-Actor / X-Ergplan-Role for tests and local work, and ignores them in production.

The guard (an app-wide dependency) applies the access policy by route: a few routes are public (the
shared plan, the regulation documents, sign-in, health); every other route needs a signed-in user; a
client may reach only the connections, sites, bills, scenarios and runs of clients they created.
Analysts reach everything. Endpoints that need the analyst role say so with `Depends(analyst)`."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.settings import get_settings
from ..db.base import session_scope
from ..db.models import AuthSession, Bill, Client, Connection, Run, Scenario, Site, User

COOKIE = "ergplan_session"
ANONYMOUS = "anonymous"

# Route templates open without signing in (production).
PUBLIC = {
    "/health",
    "/auth/request",
    "/auth/verify",
    "/auth/login",
    "/auth/me",
    "/auth/logout",
    "/p/{token}",
    "/p/{token}/pdf",
    "/p/{token}/whatif",
    "/p/{token}/explain",
    "/documents",
    "/documents/{document_id}",
    "/documents/{document_id}/meta",
    "/documents/{document_id}/pages/{page}.png",
    "/documents/{document_id}/pages/{page}/text",
    "/prices/vintages/{vintage_id}",
    "/intake/shapes",
    "/voice/session",
    "/voice/tool",
    "/voice/tools",
    "/chat",
}


@dataclass(frozen=True)
class Caller:
    actor: str
    role: str

    @property
    def signed_in(self) -> bool:
        return self.actor != ANONYMOUS


def production() -> bool:
    return get_settings().ergplan_env != "dev"


def sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _from_session(token: str | None) -> Caller | None:
    if not token:
        return None
    with session_scope() as s:
        row = s.get(AuthSession, sha(token))
        if row is None or row.revoked_at is not None or row.expires_at < datetime.now(UTC):
            return None
        user = s.get(User, row.email)
        return Caller(actor=row.email, role=user.role if user else "client")


def caller(
    request: Request,
    x_ergplan_actor: Annotated[str | None, Header()] = None,
    x_ergplan_role: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Caller:
    bearer = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None
    found = _from_session(request.cookies.get(COOKIE) or bearer)
    if found is not None:
        return found
    if production():
        return Caller(actor=ANONYMOUS, role="client")
    return Caller(
        actor=(x_ergplan_actor or ANONYMOUS).strip()[:128], role=(x_ergplan_role or "client").strip()
    )


def analyst(c: Annotated[Caller, Depends(caller)]) -> Caller:
    if c.role != "analyst" or c.actor == ANONYMOUS:
        raise HTTPException(403, "analyst role required")
    return c


def role_for(email: str) -> str:
    st = get_settings()
    listed = {e.strip().lower() for e in st.ergplan_analyst_emails.split(",") if e.strip()}
    domain = st.ergplan_analyst_domain.strip().lower()
    e = email.lower()
    return "analyst" if e in listed or (domain and e.endswith("@" + domain)) else "client"


# ---------------------------------------------------------------- the guard


def owner_of(s: Session, kind: str, ident: str) -> str | None:
    """The email that owns a resource (the creator of its client; a bill's uploader), or None."""
    conn: Connection | None = None
    if kind == "connection_id":
        conn = s.get(Connection, ident)
    elif kind == "site_id":
        site = s.get(Site, ident)
        if site is None:
            return None
        cl = s.get(Client, site.client_id)
        return cl.created_by if cl else None
    elif kind == "bill_id":
        bill = s.get(Bill, ident)
        if bill is None:
            return None
        if bill.uploaded_by:
            return bill.uploaded_by
        conn = s.get(Connection, bill.connection_id) if bill.connection_id else None
    elif kind == "scenario_id":
        sc = s.get(Scenario, ident)
        conn = s.get(Connection, sc.connection_id) if sc else None
    elif kind == "run_id":
        run = s.get(Run, ident)
        sc = s.get(Scenario, run.scenario_id) if run else None
        conn = s.get(Connection, sc.connection_id) if sc else None
    if conn is None:
        return None
    site = s.get(Site, conn.site_id)
    cl = s.get(Client, site.client_id) if site else None
    return cl.created_by if cl else None


def may_reach(s: Session, who: Caller, kind: str, ident: str) -> bool:
    if who.role == "analyst" and who.signed_in:
        return True
    owner = owner_of(s, kind, ident)
    return owner is None or owner == who.actor  # unknown ids fall through to the route's own 404


OWNED = ("connection_id", "site_id", "bill_id", "scenario_id", "run_id")


def guard(request: Request, who: Annotated[Caller, Depends(caller)]) -> None:
    """App-wide: sign-in and ownership in production; development is open (headers are trusted)."""
    if not production():
        return
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    if path in PUBLIC or path.startswith(("/docs", "/openapi", "/redoc")):
        return
    if not who.signed_in:
        raise HTTPException(401, "sign in first")
    params = request.path_params
    with session_scope() as s:
        for kind in OWNED:
            if kind in params and not may_reach(s, who, kind, str(params[kind])):
                raise HTTPException(403, "this belongs to another client")


def owned_bills(s: Session, who: Caller, ids: list[str]) -> None:
    """For routes that take bill ids in the body."""
    if not production():
        return
    for i in ids:
        if not may_reach(s, who, "bill_id", i):
            raise HTTPException(403, "this belongs to another client")


def owned_connection(s: Session, who: Caller, connection_id: str | None) -> None:
    if production() and connection_id and not may_reach(s, who, "connection_id", connection_id):
        raise HTTPException(403, "this belongs to another client")
