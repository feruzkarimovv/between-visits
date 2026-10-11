"""Prefixed random IDs: `prefix_` + 10 base32 chars.

Prefixes: pat_ (Patient), ci_ (CheckIn), ans_ (Answer), fnd_ (Finding), esc_ (Escalation), dr_ (DraftEntry),
sae_ (SAEReport), aud_ (AuditEvent), sq_ (SiteQuery), sr_ (SignalRun, blind runs only; the committed study is the
reserved literal `sr_committed`, never a database row).
"""

import secrets

_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def new_id(prefix: str) -> str:
    return f"{prefix}_" + "".join(secrets.choice(_ALPHABET) for _ in range(10))
