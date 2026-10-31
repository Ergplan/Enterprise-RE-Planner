"""Identifiers: UUID4 strings for rows, URL-safe random tokens for share links."""

from __future__ import annotations

import secrets
import uuid


def new_id() -> str:
    return str(uuid.uuid4())


def share_token() -> str:
    return secrets.token_urlsafe(24)
