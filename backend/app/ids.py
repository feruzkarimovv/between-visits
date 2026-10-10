"""Prefixed random IDs: pat_, ci_, ans_, fnd_, esc_, dr_, sae_, aud_ + 10 base32 chars."""

import secrets

_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def new_id(prefix: str) -> str:
    return f"{prefix}_" + "".join(secrets.choice(_ALPHABET) for _ in range(10))
