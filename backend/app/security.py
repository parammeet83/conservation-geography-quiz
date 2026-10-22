"""Anonymous attempt access tokens.

A high-entropy token is returned once when an attempt is created. Only its
SHA-256 hash is stored. Clients send the raw token in an
``Authorization: Bearer <token>`` header; it never appears in URLs or logs.
"""

import hashlib
import hmac
import secrets


def new_access_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), stored_hash)
