"""Append-only audit log. No code path updates or deletes AuditEvent rows."""

import json
import logging
from typing import Any

from sqlmodel import Session

from app.ids import new_id
from app.models import AuditEvent

log = logging.getLogger("bv.audit")


def _jsonable(v: Any) -> Any:
    return json.loads(json.dumps(v, default=str)) if v is not None else None


def write_audit(
    session: Session,
    *,
    actor: str,
    role: str,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    note: str | None = None,
    checkin_id: str | None = None,
) -> AuditEvent:
    ev = AuditEvent(
        id=new_id("aud"),
        actor=actor or "unknown",
        role=role or "unknown",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        checkin_id=checkin_id,
        before=_jsonable(before),
        after=_jsonable(after),
        note=note,
    )
    session.add(ev)
    return ev
