"""Share links (rule 12 until Stage 8): an unguessable token opens a site's live plan without login."""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Connection, ShareLink


class LinkNotFound(LookupError):
    pass


def create(s: Session, connection_id: str, actor: str) -> ShareLink:
    if s.get(Connection, connection_id) is None:
        raise LinkNotFound(connection_id)
    existing = s.scalars(
        select(ShareLink).where(ShareLink.connection_id == connection_id, ShareLink.revoked_at.is_(None))
    ).first()
    if existing is not None:
        return existing
    link = ShareLink(token=secrets.token_urlsafe(24), connection_id=connection_id, created_by=actor)
    s.add(link)
    s.flush()
    return link


def resolve(s: Session, token: str) -> ShareLink:
    link = s.get(ShareLink, token)
    if link is None or link.revoked_at is not None:
        raise LinkNotFound(token)
    return link
