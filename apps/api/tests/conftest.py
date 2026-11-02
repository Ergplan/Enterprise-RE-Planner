"""Test settings: the ergplan_test database and a temporary data folder, set before any import
of ergplan so the cached settings and engine pick them up."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://ergplan:ergplan@localhost:5432/ergplan_test")
os.environ["ERGPLAN_DATA_DIR"] = tempfile.mkdtemp(prefix="ergplan-test-")

from sqlalchemy import text

from ergplan.db.base import get_engine

APP_TABLES = [
    "rule_proposals",
    "audit_messages",
    "working_lines",
    "workings",
    "auth_sessions",
    "login_tokens",
    "users",
    "explanations",
    "share_links",
    "run_results",
    "runs",
    "scenarios",
    "bill_confirmations",
    "load_profiles",
    "assets",
    "bills",
    "connections",
    "sites",
    "clients",
    "price_series",
    "price_vintages",
    "model_calls",
    "source_documents",
    "rule_test_runs",
    "rule_tests",
    "rules",
    "rulebook_versions",
    "audit_log",
    "jurisdictions",
]


@pytest.fixture(scope="session", autouse=True)
def migrated() -> None:
    """Bring the test database to head once per session, so a fresh checkout's tests just run."""
    from pathlib import Path

    from alembic.config import Config

    from alembic import command

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    cfg.cmd_opts = type("o", (), {"x": [f"url={os.environ['DATABASE_URL']}"]})()  # type: ignore[assignment]
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def clean_db() -> Iterator[None]:
    yield
    eng = get_engine()
    with eng.begin() as c:
        existing = {
            r[0] for r in c.execute(text("select tablename from pg_tables where schemaname='public'"))
        }
        tables = [t for t in APP_TABLES if t in existing]
        if tables:
            c.execute(text("truncate " + ", ".join(tables) + " cascade"))


@pytest.fixture
def jurisdictions() -> None:
    from ergplan.db.base import session_scope
    from ergplan.rulebook import service

    with session_scope(actor="test") as s:
        service.sync_jurisdictions(s)
