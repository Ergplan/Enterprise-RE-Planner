"""Identifiers: UUID4 strings for rows, URL-safe random tokens for share links."""

from __future__ import annotations

import secrets
import uuid


def new_id() -> str:
    return str(uuid.uuid4())


DOCUMENT_NAMESPACE = uuid.UUID("6f1b2a0e-5d6c-4c2b-9a51-6a2f1d3e0b77")


def document_id(sha256: str) -> str:
    """A document's id is derived from its bytes, so the same PDF has the same id on every machine
    and a citation committed to git resolves after any database rebuild."""
    return str(uuid.uuid5(DOCUMENT_NAMESPACE, sha256.lower()))


def share_token() -> str:
    return secrets.token_urlsafe(24)
