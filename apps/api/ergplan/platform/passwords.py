"""Password hashing for email + password sign-in: scrypt from the standard library, a random salt per
password, compared in constant time. Only the hash is stored (users.password_hash)."""

from __future__ import annotations

import hashlib
import hmac
import secrets

N, R, P = 2**14, 8, 1
MIN_LENGTH = 8


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    return f"scrypt${N}${R}${P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(digest) // 2
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got.hex(), digest)
