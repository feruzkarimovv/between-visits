"""B13 (docs/03 §6.6): the audit log is a hash chain and GET /api/audit/verify names the first modified event.

Also covers the safety constraint: chain assignment never fails or delays the caller's write (rule 5), a seq
collision is retried rather than raised, and concurrent writers still produce one contiguous chain.
"""

import hashlib
import json
import logging
import threading
from datetime import UTC

import pytest
from sqlalchemy import text
from sqlmodel import Session, select

from app import audit
from app import db as db_module
from app.audit import ZERO_HASH, verify_chain, write_audit
from app.models import AuditEvent, Patient
from app.services import replay
from tests.conftest import COORD

pytestmark = pytest.mark.req("REQ-019")


def _write(session: Session, n: int, start: int = 0) -> list[str]:
    ids = []
    for i in range(start, start + n):
        ev = write_audit(
            session, actor="Jess Kim", role="coordinator", action="draft.edited", entity_type="DraftEntry",
            entity_id=f"dr_chain{i}", before={"payload": {"onset_date": None, "n": i}},
            after={"payload": {"onset_date": "2026-10-08", "quote": "dolor de estómago", "x": 0.1}},
            note=f"edit {i}", checkin_id="ci_chain",
        )
        ids.append(ev.id)
    session.commit()
    return ids


def _rows(session: Session) -> list[AuditEvent]:
    session.expire_all()
    return list(session.exec(select(AuditEvent).order_by(AuditEvent.seq)).all())  # type: ignore[arg-type]


def _contract_hash(prev_hash: str, r: AuditEvent) -> str:
    """docs/03 §6.6, written out here independently of app.audit."""
    canonical = json.dumps(
        {"id": r.id, "seq": r.seq, "ts": r.ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "actor": r.actor,
         "role": r.role, "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id,
         "checkin_id": r.checkin_id, "before": r.before, "after": r.after, "note": r.note},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


def _sql(session: Session, sql: str, **params) -> None:
    session.connection().execute(text(sql), params)
    session.commit()


def test_empty_log_is_ok_with_zero_head(client):
    assert client.get("/api/audit/verify").json() == {
        "ok": True, "n_events": 0, "head_hash": "0" * 64, "first_bad_id": None, "first_bad_seq": None,
    }


def test_five_events_form_a_verified_chain(client, session):
    ids = _write(session, 5)
    rows = _rows(session)
    assert [r.id for r in rows] == ids  # seq follows write_audit order inside one transaction
    assert [r.seq for r in rows] == [1, 2, 3, 4, 5]
    prev = ZERO_HASH
    for r in rows:
        assert r.prev_hash == prev
        assert r.hash == _contract_hash(prev, r) and len(r.hash) == 64 and r.hash == r.hash.lower()
        prev = r.hash

    v = client.get("/api/audit/verify").json()
    assert v == {"ok": True, "n_events": 5, "head_hash": rows[-1].hash, "first_bad_id": None, "first_bad_seq": None}

    listed = client.get("/api/audit").json()
    assert [a["seq"] for a in listed] == [5, 4, 3, 2, 1]  # seq descending
    assert listed[0]["hash"] == rows[-1].hash and listed[-1]["prev_hash"] == ZERO_HASH


def test_modified_note_is_reported(client, session):
    ids = _write(session, 5)
    _sql(session, "UPDATE auditevent SET note = :note WHERE id = :id", note="edited after the fact", id=ids[2])
    r = client.get("/api/audit/verify")
    assert r.status_code == 200
    v = r.json()
    assert v["ok"] is False and v["n_events"] == 5
    assert v["first_bad_id"] == ids[2] and v["first_bad_seq"] == 3
    assert v["head_hash"] == _rows(session)[-1].hash


@pytest.mark.parametrize(
    ("sql", "bad_index"),
    [
        ("DELETE FROM auditevent WHERE id = :id", 3),  # gap in seq: the next event is the first that no longer fits
        ("UPDATE auditevent SET \"after\" = '{\"payload\": ' WHERE id = :id", 2),  # malformed JSON: 200, not 500
        ("UPDATE auditevent SET prev_hash = :zero WHERE id = :id", 2),
        ("UPDATE auditevent SET actor = 'someone else' WHERE id = :id", 2),
        ("UPDATE auditevent SET ts = '2026-10-01 00:00:00.000000' WHERE id = :id", 2),
        ("UPDATE auditevent SET seq = 'x' WHERE id = :id", 3),  # a text seq sorts last; the gap it leaves is reported
    ],
    ids=["deleted_row", "malformed_json", "prev_hash", "actor", "ts", "non_integer_seq"],
)
def test_other_edits_are_reported(client, session, sql, bad_index):
    ids = _write(session, 5)
    _sql(session, sql, id=ids[2], zero=ZERO_HASH)
    v = client.get("/api/audit/verify").json()
    assert v["ok"] is False and v["first_bad_id"] == ids[bad_index]


def test_rewriting_one_hash_breaks_the_next_link(client, session):
    ids = _write(session, 5)
    _sql(session, "UPDATE auditevent SET note = 'changed' WHERE id = :id", id=ids[1])
    r = next(x for x in _rows(session) if x.id == ids[1])
    _sql(session, "UPDATE auditevent SET hash = :h WHERE id = :id", h=_contract_hash(r.prev_hash, r), id=ids[1])
    v = client.get("/api/audit/verify").json()
    assert v["ok"] is False and v["first_bad_id"] == ids[2] and v["first_bad_seq"] == 3


@pytest.mark.parametrize("role", [None, "coordinator", "investigator", "sponsor", "cra"])
def test_verify_is_open_to_every_role(client, role):
    headers = {"X-BV-User": "Role check", **({"X-BV-Role": role} if role else {})}
    r = client.get("/api/audit/verify", headers=headers)
    assert r.status_code == 200 and r.json()["ok"] is True


def test_staged_events_follow_the_callers_transaction(session):
    write_audit(session, actor="Jess Kim", role="coordinator", action="draft.edited", entity_type="DraftEntry",
                entity_id="dr_rolled_back")
    session.rollback()
    assert _rows(session) == []
    ids = _write(session, 2)
    # an audit-only transaction is written too, and staged events are visible to queries before the commit
    ev = write_audit(session, actor="system", role="system", action="checkin.started", entity_type="CheckIn",
                     entity_id="ci_chain")
    assert session.exec(select(AuditEvent).where(AuditEvent.id == ev.id)).one().seq == 3
    session.commit()
    assert [r.id for r in _rows(session)] == [*ids, ev.id]
    assert verify_chain(session)["ok"] is True


def test_seq_collision_is_retried_not_raised(session, monkeypatch, caplog):
    _write(session, 1)
    real_head, calls = audit._head, []

    def stale_head(conn):  # the first read misses the event above, as a concurrent writer would
        calls.append(1)
        return (0, ZERO_HASH) if len(calls) == 1 else real_head(conn)

    monkeypatch.setattr(audit, "_head", stale_head)
    pat = session.get(Patient, "pat_rosa")
    pat.notes = "changed together with the audit event"
    session.add(pat)
    ev = write_audit(session, actor="Jess Kim", role="coordinator", action="patient.edited", entity_type="Patient",
                     entity_id="pat_rosa")
    with caplog.at_level(logging.WARNING, logger="bv.audit"):
        session.commit()  # no exception
    assert len(calls) == 2 and "audit_chain_seq_collision" in caplog.text
    session.expire_all()
    assert session.get(Patient, "pat_rosa").notes == "changed together with the audit event"
    assert [(r.id, r.seq) for r in _rows(session)][-1] == (ev.id, 2)
    assert verify_chain(session)["ok"] is True


def test_chain_failure_never_fails_the_callers_write(session, monkeypatch, caplog):
    def broken_head(conn):
        raise RuntimeError("chain store unavailable")

    monkeypatch.setattr(audit, "_head", broken_head)
    pat = session.get(Patient, "pat_rosa")
    pat.notes = "safety-path write"
    session.add(pat)
    write_audit(session, actor="system", role="system", action="escalation.paged", entity_type="Escalation",
                entity_id="esc_chain", checkin_id="ci_chain")
    with caplog.at_level(logging.ERROR, logger="bv.audit"):
        session.commit()  # no exception: the caller's write commits
    session.expire_all()
    assert session.get(Patient, "pat_rosa").notes == "safety-path write"
    assert "audit_chain_failed" in caplog.text and "esc_chain" in caplog.text  # never silent


@pytest.mark.parametrize("write_lock", [True, False], ids=["write_lock", "collision_retry"])
def test_concurrent_writers_keep_one_contiguous_chain(tmp_path, monkeypatch, write_lock):
    """File database (WAL, real locking), several threads committing domain changes with audit events.

    collision_retry: without the up-front write lock, concurrent writers read the same head and collide on seq;
    each collision is retried with a fresh head and none reaches the caller."""
    if not write_lock:
        monkeypatch.setattr(audit, "_hold_write_lock", lambda conn: False)
    monkeypatch.setattr(db_module, "_engine", db_module._engine)  # restored after the test
    engine = db_module.configure_engine(f"sqlite:///{tmp_path / 'chain.db'}")
    db_module.create_all()
    with Session(engine) as s:
        for k in range(6):
            s.add(Patient(id=f"pat_t{k}", study_id="st", subject_id=f"t-{k}", first_name="T", last_name="T", age=60,
                          sex="F", language="en", pace="standard"))
        s.commit()

    errors: list[BaseException] = []
    barrier = threading.Barrier(6)

    def worker(k: int) -> None:
        try:
            barrier.wait()
            for j in range(12):
                with Session(engine) as s:
                    p = s.get(Patient, f"pat_t{k}")
                    p.notes = f"{k}-{j}"
                    s.add(p)
                    for m in range(2):
                        write_audit(s, actor=f"user{k}", role="coordinator", action="patient.edited",
                                    entity_type="Patient", entity_id=p.id, note=f"{j}.{m}")
                    s.commit()
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert errors == []
    with Session(engine) as s:
        rows = _rows(s)
        assert [r.seq for r in rows] == list(range(1, 6 * 12 * 2 + 1))
        assert verify_chain(s) == {"ok": True, "n_events": 144, "head_hash": rows[-1].hash,
                                   "first_bad_id": None, "first_bad_seq": None}
        for k in range(6):  # each transaction's two events are adjacent and in write order
            mine = [r for r in rows if r.actor == f"user{k}"]
            assert [r.note for r in mine] == [f"{j}.{m}" for j in range(12) for m in range(2)]
            assert all(b.seq == a.seq + 1 for a, b in zip(mine[::2], mine[1::2], strict=True))
    engine.dispose()


def test_replay_and_review_keep_the_chain_valid(client, session, fake_pager):
    """The acceptance path: replay rosa_es_urgent, confirm a draft, then verify."""
    cid = replay.start(session, "rosa_es_urgent", speed=10_000, run_async=False)
    draft = next(d for d in client.get("/api/drafts", params={"checkin_id": cid}).json() if d["kind"] == "AE")
    assert client.post(f"/api/drafts/{draft['id']}/confirm", json={}, headers=COORD).status_code == 200
    v = client.get("/api/audit/verify").json()
    assert v["ok"] is True and v["n_events"] > 10
    listed = client.get("/api/audit", params={"limit": 1000}).json()
    assert listed[0]["seq"] == v["n_events"] and listed[0]["hash"] == v["head_hash"]
    assert listed[0]["action"] == "draft.confirmed"
    assert sorted(a["seq"] for a in listed) == list(range(1, v["n_events"] + 1))
