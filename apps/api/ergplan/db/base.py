"""Engine and sessions. A write session names its actor: `SET LOCAL ergplan.actor` is what the
audit triggers read (invariant 3); a session without one cannot write audited tables."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..core.settings import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or get_settings().database_url, pool_pre_ping=True, future=True)


def _factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(
    actor: str | None = None, role: str | None = None, engine: Engine | None = None
) -> Iterator[Session]:
    """A transaction. `actor` (an email or a service name) and `role` are set for the triggers."""
    s = _factory(engine or get_engine())()
    try:
        if actor:
            s.execute(text("select set_config('ergplan.actor', :a, true)"), {"a": actor})
        if role:
            s.execute(text("select set_config('ergplan.role', :r, true)"), {"r": role})
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
