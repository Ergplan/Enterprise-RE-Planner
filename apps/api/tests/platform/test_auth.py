"""Stage 8 sign-in and access, in production mode: email link → session cookie; development headers
are ignored; signed-out callers reach only the public routes; a client reaches only what they created;
analysts reach everything; the shared plan opens logged out; security headers."""

from __future__ import annotations

import smtplib
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ergplan.core.settings import get_settings
from ergplan.db.base import session_scope
from ergplan.db.models import AuthSession, LoginToken, User
from ergplan.intake import bills as bill_store
from ergplan.platform import mail
from ergplan.platform.app import app
from tests.engine.helpers import restore_committed
from tests.intake.helpers import FakeBillx
from tests.platform.test_api_runs import msedcl_5mw


@pytest.fixture
def prod(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    monkeypatch.setattr(get_settings(), "ergplan_env", "prod")
    monkeypatch.setattr(get_settings(), "ergplan_smtp_url", "smtp://mail.test:587")
    sent: list[tuple[str, str]] = []

    def fake_send(to: str, subject: str, body: str) -> bool:
        sent.append((to, body))
        return True

    monkeypatch.setattr(mail, "send", fake_send)
    return sent


def sign_in(email: str, sent: list[tuple[str, str]]) -> TestClient:
    c = TestClient(app, base_url="https://testserver")
    r = c.post("/auth/request", json={"email": email})
    assert r.status_code == 200 and r.json() == {"sent": True, "dev_link": None}
    token = sent[-1][1].split("token=")[1].split("&")[0].split()[0]
    v = c.post("/auth/verify", json={"token": token})
    assert v.status_code == 200, v.text
    assert "ergplan_session" in c.cookies
    assert c.post("/auth/verify", json={"token": token}).status_code == 401  # one use only
    return c


def test_sign_in_roles_and_logout(prod: list[tuple[str, str]]) -> None:
    a = sign_in("Priya@joulewise.in", prod)
    assert a.get("/auth/me").json() == {
        "email": "priya@joulewise.in",
        "role": "analyst",
        "signed_in": True,
        "required": True,
        "has_password": False,
    }
    c = sign_in("ops@acme.in", prod)
    assert c.get("/auth/me").json()["role"] == "client"
    private = c.get("/rulebooks/versions")  # any signed-in route
    assert private.status_code == 200
    assert private.headers["x-content-type-options"] == "nosniff"
    assert "max-age" in private.headers["strict-transport-security"]
    old_cookie = c.cookies["ergplan_session"]
    bearer = TestClient(app, base_url="https://testserver")  # a non-browser client: same token as a bearer
    me = bearer.get("/auth/me", headers={"Authorization": f"Bearer {old_cookie}"}).json()
    assert me["signed_in"] is True and me["email"] == "ops@acme.in"
    out = c.post("/auth/logout")
    assert out.json()["signed_in"] is False
    assert (
        'ergplan_session=""' in out.headers["set-cookie"] or "max-age=0" in out.headers["set-cookie"].lower()
    )
    with session_scope() as s:
        rows = s.query(AuthSession).filter(AuthSession.email == "ops@acme.in").all()
        assert rows and all(r.revoked_at is not None for r in rows)  # revoked in the database
    assert c.get("/auth/me").json()["signed_in"] is False
    replay = TestClient(app, base_url="https://testserver", cookies={"ergplan_session": old_cookie})
    assert replay.get("/rulebooks/versions").status_code == 401  # the session is revoked, not just forgotten


def test_expired_link_is_refused(prod: list[tuple[str, str]]) -> None:
    c = TestClient(app, base_url="https://testserver")
    c.post("/auth/request", json={"email": "late@acme.in"})
    token = prod[-1][1].split("token=")[1].split("&")[0]
    with session_scope() as s:
        for t in s.query(LoginToken).all():
            t.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    assert c.post("/auth/verify", json={"token": token}).status_code == 401


def test_development_headers_are_ignored_in_production(prod: list[tuple[str, str]]) -> None:
    c = TestClient(app, base_url="https://testserver")
    fake = {"X-Ergplan-Actor": "intruder@x.in", "X-Ergplan-Role": "analyst"}
    assert c.get("/auth/me", headers=fake).json()["signed_in"] is False
    assert c.get("/rulebooks/versions", headers=fake).status_code == 401
    assert c.get("/health").status_code == 200 and c.get("/documents").status_code == 200
    r = c.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and "strict-transport-security" in r.headers


def test_a_client_reaches_only_their_own_sites(
    prod: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    restore_committed()
    fake = FakeBillx()
    monkeypatch.setattr(bill_store, "BillxClient", fake.client)
    owner = sign_in("owner@acme.in", prod)
    other = sign_in("someone@else.in", prod)
    analyst = sign_in("ana@joulewise.in", prod)
    pdf = fake.register("b", msedcl_5mw())
    assert (
        TestClient(app, base_url="https://testserver")
        .post("/bills", files={"file": ("b.pdf", pdf, "application/pdf")})
        .status_code
        == 401
    )
    [bill] = owner.post("/bills", files={"file": ("b.pdf", pdf, "application/pdf")}).json()
    # the same file from someone else: their own bill row, billx not called again
    calls = fake.calls
    [theirs] = other.post("/bills", files={"file": ("b.pdf", pdf, "application/pdf")}).json()
    assert theirs["id"] != bill["id"] and fake.calls == calls
    assert other.get(f"/bills/{bill['id']}").status_code == 403
    assert other.post("/intake/from-bills", json={"bill_ids": [bill["id"]]}).status_code == 403
    si = owner.post("/intake/from-bills", json={"bill_ids": [bill["id"]]}).json()
    out = owner.post("/sites", json={"intake": si}).json()
    conn, site = out["connection_id"], out["site_id"]
    for path in (
        f"/connections/{conn}",
        f"/connections/{conn}/profile",
        f"/sites/{site}/scenarios",
        f"/connections/{conn}/plan",
    ):
        assert owner.get(path).status_code == 200, path
        assert other.get(path).status_code == 403, path
        assert analyst.get(path).status_code == 200, path
    tok = owner.post(f"/connections/{conn}/share").json()["token"]
    assert other.post(f"/connections/{conn}/share").status_code == 403
    anon = TestClient(app, base_url="https://testserver")
    d: dict[str, Any] = anon.get(f"/p/{tok}").json()  # the shared plan opens logged out
    assert d["connection_id"] == conn
    assert anon.get(f"/p/{tok}", params={"view": "analyst"}).status_code == 403
    assert anon.post("/voice/session", json={"mode": "intake"}).status_code == 401
    assert (
        anon.post(
            "/chat", json={"mode": "intake", "messages": [{"role": "user", "content": "hi"}]}
        ).status_code
        == 401
    )


def test_production_without_mail_refuses_to_issue_a_link(prod: list[tuple[str, str]]) -> None:
    get_settings().ergplan_smtp_url = ""  # restored by the fixture's monkeypatch
    with session_scope() as s:
        before = s.query(LoginToken).count()
    r = TestClient(app).post("/auth/request", json={"email": "someone@acme.in"})
    assert r.status_code == 503 and "ERGPLAN_SMTP_URL" in r.json()["detail"]
    assert not prod
    with session_scope() as s:
        assert s.query(LoginToken).count() == before


def test_development_link_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ergplan_env", "dev")
    monkeypatch.setattr(get_settings(), "ergplan_smtp_url", "")
    c = TestClient(app)
    r = c.post("/auth/request", json={"email": "dev@acme.in"})
    assert r.status_code == 200 and r.json()["sent"] is False
    assert "/login/verify?token=" in (r.json()["dev_link"] or "")
    me = c.get("/auth/me", headers={"X-Ergplan-Actor": "a@joulewise.in", "X-Ergplan-Role": "analyst"}).json()
    assert me["signed_in"] is True and me["role"] == "analyst" and me["required"] is False


def test_a_refusing_mail_server_is_reported(
    prod: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(to: str, subject: str, body: str) -> bool:
        raise smtplib.SMTPRecipientsRefused({to: (550, b"no")})

    monkeypatch.setattr(mail, "send", refuse)
    r = TestClient(app).post("/auth/request", json={"email": "x@acme.in"})
    assert r.status_code == 502


def test_plain_http_public_url_is_warned_in_production(
    prod: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    from ergplan.platform.app import create_app

    monkeypatch.setattr(get_settings(), "ergplan_public_url", "http://plan.example.in")
    monkeypatch.setattr(
        logging.getLogger("ergplan.app"), "disabled", False
    )  # alembic's fileConfig in conftest
    with caplog.at_level("WARNING", logger="ergplan.app"):
        create_app()
    assert "not https" in caplog.text


def test_operator_issues_a_link_and_cookie_follows_the_scheme(
    prod: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from ergplan.platform import signin

    monkeypatch.setattr(get_settings(), "ergplan_public_url", "http://192.168.1.73")  # a LAN server
    assert signin.main(["Ravi@Joulewise.in"]) == 0
    link = capsys.readouterr().out.strip()
    assert link.startswith("http://192.168.1.73/login/verify?token=")
    c = TestClient(app, base_url="http://testserver")
    v = c.post("/auth/verify", json={"token": link.split("token=")[1].split("&")[0]})
    assert v.status_code == 200 and v.json()["role"] == "analyst"
    assert "secure" not in v.headers["set-cookie"].lower()  # http: a Secure cookie would never come back
    assert c.get("/rulebooks/versions").status_code == 200
    with pytest.raises(SystemExit):
        signin.main(["not-an-email"])


def test_every_public_template_is_a_real_route() -> None:
    from ergplan.platform.auth import PUBLIC

    paths = set(app.openapi()["paths"])  # routers are included lazily; the schema lists every route
    assert paths >= PUBLIC, sorted(PUBLIC - paths)


def test_password_sign_in_set_change_and_analyst_adds_a_person(prod: list[tuple[str, str]]) -> None:
    from ergplan.platform.routers import auth as auth_routes

    auth_routes._failures.clear()
    c = sign_in("owner@joulewise.in", prod)  # first time: the emailed or operator link
    assert c.get("/auth/me").json()["has_password"] is False
    assert c.post("/auth/password", json={"password": "short"}).status_code == 422
    assert c.post("/auth/password", json={"password": "green-power-2026"}).json()["has_password"] is True
    # changing it needs the current password
    assert c.post("/auth/password", json={"password": "another-pass-1"}).status_code == 403
    assert (
        c.post(
            "/auth/password", json={"password": "another-pass-1", "current": "green-power-2026"}
        ).status_code
        == 200
    )
    c.post("/auth/logout")
    fresh = TestClient(app, base_url="https://testserver")
    assert (
        fresh.post("/auth/login", json={"email": "Owner@joulewise.in", "password": "nope-nope"}).status_code
        == 401
    )
    ok = fresh.post("/auth/login", json={"email": "owner@joulewise.in", "password": "another-pass-1"})
    assert ok.status_code == 200 and ok.json()["role"] == "analyst" and "ergplan_session" in fresh.cookies
    assert fresh.get("/rulebooks/versions").status_code == 200
    # an analyst adds a client with a first password; a client cannot add people
    added = fresh.post("/auth/users", json={"email": "plant@acme.in", "password": "first-pass-9"})
    assert added.status_code == 201 and added.json() == {"email": "plant@acme.in", "role": "client"}
    cl = TestClient(app, base_url="https://testserver")
    assert (
        cl.post("/auth/login", json={"email": "plant@acme.in", "password": "first-pass-9"}).json()["role"]
        == "client"
    )
    assert cl.post("/auth/users", json={"email": "x@acme.in", "password": "whatever-1"}).status_code == 403
    with session_scope() as s:
        u = s.get(User, "plant@acme.in")
        assert u is not None and u.password_hash and "first-pass-9" not in u.password_hash


def test_wrong_passwords_are_throttled(prod: list[tuple[str, str]]) -> None:
    from ergplan.platform.routers import auth as auth_routes

    auth_routes._failures.clear()
    c = TestClient(app, base_url="https://testserver")
    codes = [
        c.post("/auth/login", json={"email": "who@acme.in", "password": f"guess-{i}"}).status_code
        for i in range(11)
    ]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    auth_routes._failures.clear()


def test_password_hashes_are_salted_and_checked_in_constant_time() -> None:
    from ergplan.platform.passwords import hash_password, verify_password

    a, b = hash_password("same-password"), hash_password("same-password")
    assert a != b and a.startswith("scrypt$")
    assert verify_password("same-password", a) and not verify_password("other", a)
    assert not verify_password("x", None) and not verify_password("x", "garbage")
