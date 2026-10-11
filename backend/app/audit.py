"""Append-only audit log with a hash chain (docs/03 §6.6, REQ-019). No code path updates or deletes AuditEvent rows.

`write_audit` stages an event in the caller's session, as before. The chain fields are assigned when that session
flushes the event, which is the moment the row is written:

- `seq` = max + 1, `prev_hash` = the head event's `hash` (64 zeros for `seq` 1),
  `hash` = sha256(prev_hash + canonical JSON), the canonical form being exactly `canonical()` below.
- Before reading the head, the writing connection takes the SQLite write lock (`BEGIN IMMEDIATE`, the lock the
  flush would take a moment later anyway), so no other connection can append between the read and the insert.
  Nothing is locked or written earlier than without the chain.
- One process-wide lock covers the head read and the insert. It is never held while waiting for the database,
  and a writer that cannot get it within `LOCK_WAIT_S` goes ahead without it.
- The insert runs on the session's own connection, so the event commits or rolls back with the caller's change.
  A `seq` collision (unique constraint) is retried with a fresh head, never raised.
- Rule 5: chain assignment never fails or delays a safety-path write. Any unexpected error is logged at ERROR
  with the full event (`audit_chain_failed`) and swallowed; the caller's own write still commits.

`verify_chain` walks the chain in `seq` order and reports the first event that no longer matches. The chain is
tamper-evident inside the database only: the head hash is not anchored externally.
"""

import hashlib
import json
import logging
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from sqlalchemy import String, event, select, type_coerce
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession
from sqlmodel import Session

from app.ids import new_id
from app.models import AuditEvent
from app.timeutil import ensure_utc

log = logging.getLogger("bv.audit")

ZERO_HASH = "0" * 64
# The fields the hash covers, in the order of docs/03 §6.6 (the JSON itself is key-sorted).
HASHED_FIELDS = ("id", "seq", "ts", "actor", "role", "action", "entity_type", "entity_id", "checkin_id",
                 "before", "after", "note")
LOCK_WAIT_S = 1.0
MAX_ATTEMPTS = 20

_CHAIN_LOCK = threading.Lock()
_ORDER_KEY = "bv_audit_order"  # session.info: events in write_audit call order


def _jsonable(v: Any) -> Any:
    return json.loads(json.dumps(v, default=str)) if v is not None else None


def ts_utc_str(ts: datetime) -> str:
    """`ts` as hashed: UTC with microseconds and a Z (naive values are taken as UTC)."""
    return ensure_utc(ts).strftime("%Y-%m-%dT%H:%M:%S.%fZ")  # type: ignore[union-attr]


def canonical(fields: Mapping[str, Any]) -> str:
    """The canonical JSON of one event, exactly as docs/03 §6.6."""
    doc = {k: fields[k] for k in HASHED_FIELDS}
    doc["ts"] = ts_utc_str(doc["ts"])
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def chain_hash(prev_hash: str, fields: Mapping[str, Any]) -> str:
    """Lowercase hex sha256(prev_hash + canonical JSON)."""
    return hashlib.sha256((prev_hash + canonical(fields)).encode("utf-8")).hexdigest()


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
    """Stage an audit event in the caller's session; it is chained and written when the session flushes."""
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
    session.info.setdefault(_ORDER_KEY, []).append(ev)
    return ev


# ---- chain assignment (runs inside the caller's flush) -------------------------------------------------


@event.listens_for(OrmSession, "before_flush")
def _chain_staged_events(session: OrmSession, flush_context: Any, instances: Any) -> None:
    """Take every new AuditEvent out of the ORM flush and append it to the chain on the session's connection."""
    staged = [o for o in session.new if isinstance(o, AuditEvent)]
    order = session.info.pop(_ORDER_KEY, [])
    if not staged:
        return
    rank = {id(o): i for i, o in enumerate(order)}
    staged.sort(key=lambda o: rank.get(id(o), len(rank)))  # stable: write_audit order, then any direct adds
    for o in staged:
        session.expunge(o)
    done = 0
    try:
        conn = session.connection()
        locked = _hold_write_lock(conn)
        for o in staged:
            _append(conn, o, locked)
            done += 1
    except Exception:  # noqa: BLE001  rule 5: never fail the caller's write because of the chain
        for o in staged[done:]:
            log.exception("audit_chain_failed event=%s", json.dumps(_event_fields(o), default=str, ensure_ascii=False))


@event.listens_for(OrmSession, "after_soft_rollback")
def _drop_staged_order(session: OrmSession, previous_transaction: Any) -> None:
    # A rollback expunges the staged events themselves; forget their order too.
    session.info.pop(_ORDER_KEY, None)


def _event_fields(o: AuditEvent) -> dict[str, Any]:
    return {k: getattr(o, k) for k in HASHED_FIELDS}


def _hold_write_lock(conn: Connection) -> bool:
    """SQLite: make sure this connection holds the write lock (True), so the head cannot move before the insert.

    A connection already inside a write transaction holds it. Otherwise `BEGIN IMMEDIATE` takes it now, waiting
    (busy_timeout) exactly as the flush's first INSERT would. Other databases, or any error: False (the insert
    then runs outside the process-wide lock and a collision is retried)."""
    if conn.dialect.name != "sqlite":
        return False
    try:
        raw = conn.connection.dbapi_connection
        if raw is None:
            return False
        if not raw.in_transaction:  # type: ignore[attr-defined]
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("audit_chain_write_lock_unavailable error=%r", e)
        return False


@contextmanager
def _chain_lock() -> Iterator[None]:
    got = _CHAIN_LOCK.acquire(timeout=LOCK_WAIT_S)
    if not got:
        log.warning("audit_chain_lock_wait_exceeded wait_s=%s; appending without the process lock", LOCK_WAIT_S)
    try:
        yield
    finally:
        if got:
            _CHAIN_LOCK.release()


def _head(conn: Connection) -> tuple[int, str]:
    """(max seq, its hash), or (0, 64 zeros) for an empty log."""
    t = AuditEvent.__table__  # type: ignore[attr-defined]
    row = conn.execute(select(t.c.seq, t.c.hash).order_by(t.c.seq.desc()).limit(1)).first()
    if row is None:
        return 0, ZERO_HASH
    if isinstance(row.seq, int):
        return row.seq, str(row.hash)
    # A row edited outside the app to a non-integer seq sorts last in SQLite: keep appending after the
    # highest integer seq (verify reports the break).
    rows = [r for r in conn.execute(select(t.c.seq, t.c.hash)).all() if isinstance(r.seq, int)]
    best = max(rows, key=lambda r: r.seq, default=None)
    return (best.seq, str(best.hash)) if best else (0, ZERO_HASH)


def _insert(conn: Connection, o: AuditEvent) -> bool:
    """Insert one chained event. False on a unique-constraint collision (statement rolled back, transaction kept)."""
    t = AuditEvent.__table__  # type: ignore[attr-defined]
    try:
        conn.execute(t.insert().values({c.name: getattr(o, c.name) for c in t.columns}))
    except IntegrityError:
        return False
    return True


def _append(conn: Connection, o: AuditEvent, locked: bool) -> None:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        with _chain_lock():
            seq, prev = _head(conn)
            o.seq, o.prev_hash = seq + 1, prev
            o.hash = chain_hash(prev, _event_fields(o))
            inserted = _insert(conn, o) if locked else None
        if inserted is None:  # no write lock: insert outside the process lock
            inserted = _insert(conn, o)
        if inserted:
            return
        log.warning("audit_chain_seq_collision event_id=%s seq=%s attempt=%d; retrying", o.id, o.seq, attempt)
    raise RuntimeError(f"audit chain: no free seq after {MAX_ATTEMPTS} attempts")


# ---- verification ------------------------------------------------------------------------------------------


def _decode(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Raw stored values -> the values that were hashed. Raises on anything malformed."""
    out = dict(raw)
    ts = raw["ts"]
    out["ts"] = ensure_utc(ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts)))
    for k in ("before", "after"):
        v = raw[k]
        out[k] = json.loads(v) if isinstance(v, str | bytes) else v
    return out


def verify_chain(session: Session) -> dict[str, Any]:
    """Walk the chain in `seq` order: contiguous `seq` from 1, each `prev_hash` equal to the previous `hash`, and
    each `hash` recomputing. Returns {ok, n_events, head_hash, first_bad_id, first_bad_seq}; never raises on a
    modified row (a broken chain is ok:false). Values are read as stored, so a malformed edit is reported too."""
    session.flush()  # chain anything this session has staged
    t = AuditEvent.__table__  # type: ignore[attr-defined]
    cols = [type_coerce(t.c[k], String).label(k) if k in ("ts", "before", "after") else t.c[k]
            for k in (*HASHED_FIELDS, "prev_hash", "hash")]
    rows = session.connection().execute(select(*cols).order_by(t.c.seq)).mappings().all()
    prev, first_bad = ZERO_HASH, None
    for expected_seq, r in enumerate(rows, start=1):
        try:
            good = (r["seq"] == expected_seq and r["prev_hash"] == prev
                    and r["hash"] == chain_hash(prev, _decode(r)))
        except Exception:  # noqa: BLE001  malformed stored value
            good = False
        if not good:
            first_bad = r
            break
        prev = r["hash"]
    out = {
        "ok": first_bad is None,
        "n_events": len(rows),
        "head_hash": str(rows[-1]["hash"]) if rows else ZERO_HASH,
        "first_bad_id": first_bad["id"] if first_bad is not None else None,
        "first_bad_seq": first_bad["seq"] if first_bad is not None and isinstance(first_bad["seq"], int) else None,
    }
    if first_bad is not None:
        log.warning("audit_chain_broken n_events=%d first_bad_id=%s first_bad_seq=%s",
                    out["n_events"], out["first_bad_id"], out["first_bad_seq"])
    return out
