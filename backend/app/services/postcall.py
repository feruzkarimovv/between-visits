"""Post-call pipeline (docs/01 Flow B): transcript → quote timing → extraction → safety net → translations
→ drafts with evidence. Idempotent per check-in. Fails safe: if the safety net can't run, a human is paged.
"""

import logging
import re
import unicodedata
from typing import Any

from sqlmodel import Session, select

from app import content
from app.audit import write_audit
from app.models import CheckIn, CheckInPlan, Escalation, Finding, Patient
from app.services import clinical, drafts, escalation, gemini, rules
from app.timeutil import utcnow

log = logging.getLogger("bv.postcall")


def turns_from_elevenlabs(data: dict[str, Any], default_lang: str) -> list[dict[str, Any]]:
    lang = (data.get("metadata") or {}).get("main_language") or default_lang
    out: list[dict[str, Any]] = []
    for t in data.get("transcript") or []:
        msg = t.get("message")
        if not msg:
            continue
        out.append({"i": len(out), "role": "agent" if t.get("role") == "agent" else "user", "text": msg,
                    "t_s": t.get("time_in_call_secs"), "lang": lang})
    return out


def _words(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.findall(r"[a-z0-9]+", s)


def match_turn(quote: str, turns: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Best user turn for a quote: containment first, then word overlap."""
    qw = _words(quote)
    if not qw:
        return None
    best, best_score = None, 0.0
    for t in turns:
        if t["role"] != "user":
            continue
        tw = _words(t["text"])
        if not tw:
            continue
        joined_q, joined_t = " ".join(qw), " ".join(tw)
        if joined_q in joined_t or joined_t in joined_q:
            score = 1.0 + min(len(qw), len(tw)) / max(len(qw), len(tw))
        else:
            score = len(set(qw) & set(tw)) / max(len(set(qw)), 1)
        if score > best_score:
            best, best_score = t, score
    return best if best_score >= 0.5 else None


def _med_key(name: str) -> set[str]:
    return {w for w in _words(name) if len(w) > 3} - {"from", "pharmacy", "started", "yesterday", "name", "given", "farmacia"}


def run(session: Session, checkin: CheckIn, turns: list[dict[str, Any]] | None = None) -> dict[str, int]:
    """Run the pipeline on the check-in's stored transcript. Returns counts for logging/tests."""
    patient = session.get(Patient, checkin.patient_id)
    assert patient is not None
    turns = turns if turns is not None else list(checkin.transcript or [])
    lang = checkin.language
    counts = {"drafts": 0, "safety_net_escalations": 0}

    # 1. time-stamp live answers and draft evidence by matching quotes to transcript turns
    answers = clinical.answers_for(session, checkin.id)
    for a in answers:
        t = match_turn(a.verbatim_quote, turns)
        if t and a.t_s is None:
            a.t_s = t["t_s"]
            session.add(a)
    for d in drafts.drafts_for(session, checkin.id):
        new_ev = []
        for ev in d.evidence or []:
            t = match_turn(ev.get("quote", ""), turns)
            if t and ev.get("t_s") is None:
                ev = {**ev, "t_s": t["t_s"], "turn_index": t["i"]}
            new_ev.append(ev)
        d.evidence = new_ev
        session.add(d)

    # 2. extraction and safety net (Gemini or fake)
    try:
        extraction = gemini.extract(turns, lang)
    except Exception as e:  # noqa: BLE001
        log.error("extraction_failed checkin_id=%s error=%r", checkin.id, e)
        extraction = {"symptoms": [], "medications": [], "questions": [], "care_visits": []}
        write_audit(session, actor="system", role="system", action="postcall.extraction_failed", entity_type="CheckIn",
                    entity_id=checkin.id, note=repr(e)[:500], checkin_id=checkin.id)
    try:
        hits = gemini.safety_net(turns, lang)
    except Exception as e:  # noqa: BLE001  fail safe: a human reviews the transcript
        log.error("safety_net_failed checkin_id=%s error=%r", checkin.id, e)
        hits = []
        esc = escalation.create_callback(session, checkin, patient, "post_call_safety_net",
                                         "Automated post-call safety review failed; review the transcript now.", actor="system")
        esc.level = "urgent"
        session.flush()
        escalation.page(session, esc, patient)
        counts["safety_net_escalations"] += 1

    # 3. safety net: every red flag mentioned but not escalated gets escalated now
    plan_row = session.get(CheckInPlan, checkin.plan_id)
    plan_flags = list(plan_row.red_flag_ids) if plan_row else None
    known = clinical.all_escalated_flag_ids(session, checkin.id)
    missed = [h for h in hits if h["red_flag_id"] not in known and (plan_flags is None or h["red_flag_id"] in plan_flags)]
    if missed:
        rf_hits = [rules.RedFlagHit(h["red_flag_id"], content.red_flag(h["red_flag_id"])["level"], "report", {}) for h in missed]
        outcome, esc = escalation.escalate_flags(session, checkin, patient, rf_hits, "post_call_safety_net", actor="system")
        if esc is not None and outcome != "none":
            counts["safety_net_escalations"] += 1
            log.warning("safety_net_escalation checkin_id=%s flags=%s outcome=%s", checkin.id,
                        [h["red_flag_id"] for h in missed], outcome)

    # 4. translations for non-English quotes (stored separately, labeled)
    quotes: set[str] = set()
    if lang != "en":
        quotes |= {a.verbatim_quote for a in answers if a.verbatim_quote}
        for d in drafts.drafts_for(session, checkin.id):
            quotes |= {ev.get("quote", "") for ev in d.evidence or [] if ev.get("quote")}
        for key in ("symptoms", "medications", "questions", "care_visits"):
            quotes |= {x["quote"] for x in extraction.get(key, []) if x.get("quote")}
    qlist = sorted(q for q in quotes if q.strip())
    try:
        tr = {q: t for q, t in zip(qlist, gemini.translate(qlist, lang), strict=False) if t} if qlist else {}
    except Exception as e:  # noqa: BLE001
        log.error("translation_failed checkin_id=%s error=%r", checkin.id, e)
        tr = {}

    def ev_for(quote: str, source: str, t: dict[str, Any] | None = None) -> dict[str, Any]:
        t = t or match_turn(quote, turns)
        return drafts.evidence(quote, lang, source, t_s=t["t_s"] if t else None, turn_index=t["i"] if t else None,
                               translation_en=tr.get(quote) if lang != "en" else None)

    # backfill translations on live drafts
    for d in drafts.drafts_for(session, checkin.id):
        d.evidence = [{**ev, "translation_en": tr.get(ev.get("quote", "")),
                       "translation_label": drafts.TRANSLATION_LABEL if tr.get(ev.get("quote", "")) else None}
                      if lang != "en" else ev for ev in d.evidence or []]
        session.add(d)

    # 5. AE drafts: one per finding term (live) + extraction-only terms
    existing_ae = {d.payload.get("term") for d in drafts.drafts_for(session, checkin.id, "AE")}
    findings = session.exec(select(Finding).where(Finding.checkin_id == checkin.id)).all()
    escs = session.exec(select(Escalation).where(Escalation.checkin_id == checkin.id)).all()
    by_id = {a.id: a for a in clinical.answers_for(session, checkin.id)}
    for f in findings:
        if f.term in existing_ae:
            continue
        fa = [by_id[i] for i in f.answer_ids if i in by_id]
        linked = next((e.id for e in escs if set(e.red_flag_ids or []) & set(f.red_flag_ids or [])), None)
        en_quotes = [tr.get(a.verbatim_quote, a.verbatim_quote) if lang != "en" else a.verbatim_quote for a in fa]
        payload = {
            "term": f.term, "verbatim_en": "; ".join(q for q in en_quotes if q), "onset_date": None, "ongoing": True,
            "provisional_grade": f.provisional_grade, "grade_basis": f.grade_basis, "rule_id": f.rule_id,
            "rule_text": f.rule_text,
            "answers": [{"item_code": a.item_code, "option_code": a.option_code, "numeric_value": a.numeric_value} for a in fa],
            "escalation_id": linked, "reporter": fa[0].reporter if fa else "patient",
        }
        ev = [{**ev_for(a.verbatim_quote, "live_tool"), "t_s": a.t_s if a.t_s is not None else ev_for(a.verbatim_quote, "live_tool")["t_s"]}
              for a in fa if a.verbatim_quote]
        drafts.create_draft(session, checkin, "AE", payload, ev, actor="system")
        existing_ae.add(f.term)
        counts["drafts"] += 1
    for s in extraction.get("symptoms", []):
        term = s["term"] if isinstance(s["term"], str) else s["term"].value
        if term in existing_ae:
            continue
        linked = next((e.id for e in escs if e.level in ("urgent", "emergency")), None) if term == "Chest pain" else None
        payload = {"term": term, "verbatim_en": s.get("verbatim_en") or tr.get(s["quote"], s["quote"]), "onset_date": None,
                   "ongoing": True, "provisional_grade": None, "grade_basis": "needs_clinician", "rule_id": None,
                   "rule_text": None, "answers": [], "escalation_id": linked,
                   "reporter": "caregiver" if checkin.speaker == "caregiver" else "patient"}
        t = next((x for x in turns if x["i"] == s.get("turn_index")), None)
        drafts.create_draft(session, checkin, "AE", payload, [ev_for(s["quote"], "post_call_extraction", t)], actor="system")
        existing_ae.add(term)
        counts["drafts"] += 1

    # 6. CM drafts: merge extraction into live ones, add the rest
    live_cms = drafts.drafts_for(session, checkin.id, "CM")
    for m in extraction.get("medications", []):
        key = _med_key(m["name"])
        match = next((d for d in live_cms if key & _med_key(d.payload.get("medication_name", "") + " " + d.payload.get("as_reported_en", ""))), None)
        info = {"otc": True if re.search(r"pharmacy|farmacia|over the counter", m["quote"].lower()) else None,
                "indication_en": m.get("indication_en"), "start_date": None}
        if match:
            match.payload = {**match.payload, "as_reported_en": match.payload.get("as_reported_en") or match.payload.get("medication_name"),
                             "medication_name": m["name"],
                             **{k: v for k, v in info.items() if v is not None and not match.payload.get(k)}}
            session.add(match)
            continue
        t = next((x for x in turns if x["i"] == m.get("turn_index")), None)
        d = drafts.create_draft(session, checkin, "CM", {"medication_name": m["name"], "dose_text": None, **info},
                                [ev_for(m["quote"], "post_call_extraction", t)], actor="system")
        live_cms.append(d)
        counts["drafts"] += 1

    # 7. nurse tasks for questions and care visits not already captured live
    tasks = drafts.drafts_for(session, checkin.id, "NURSE_TASK")
    task_quotes = {ev.get("quote") for d in tasks for ev in d.evidence or []}
    for q in extraction.get("questions", []):
        if q["quote"] in task_quotes or any(match_turn(q["quote"], [{"i": 0, "role": "user", "text": tq or "", "t_s": 0}]) for tq in task_quotes):
            continue
        t = next((x for x in turns if x["i"] == q.get("turn_index")), None)
        drafts.create_draft(session, checkin, "NURSE_TASK", {"category": "medical_question", "text_en": q["text_en"]},
                            [ev_for(q["quote"], "post_call_extraction", t)], actor="system")
        counts["drafts"] += 1
    if extraction.get("care_visits") and not any(d.payload.get("category") == "care_visit" for d in tasks):
        cv = extraction["care_visits"][0]
        t = next((x for x in turns if x["i"] == cv.get("turn_index")), None)
        drafts.create_draft(session, checkin, "NURSE_TASK", {"category": "care_visit", "text_en": cv["description_en"]},
                            [ev_for(cv["quote"], "post_call_extraction", t)], actor="system")
        counts["drafts"] += 1

    checkin.postcall_status = "done"
    session.add(checkin)
    write_audit(session, actor="system", role="system", action="postcall.processed", entity_type="CheckIn",
                entity_id=checkin.id, after=counts, checkin_id=checkin.id)
    log.info("postcall_done checkin_id=%s %s", checkin.id, counts)
    return counts


def apply_call_metadata(checkin: CheckIn, data: dict[str, Any], turns: list[dict[str, Any]]) -> None:
    meta = data.get("metadata") or {}
    analysis = data.get("analysis") or {}
    if not isinstance(meta, dict):
        meta = {}
    checkin.transcript = turns
    checkin.duration_s = meta.get("call_duration_secs")
    checkin.termination_reason = meta.get("termination_reason")
    checkin.summary_en = analysis.get("transcript_summary")
    checkin.analysis = {
        "evaluation_criteria_results": analysis.get("evaluation_criteria_results"),
        "data_collection_results": analysis.get("data_collection_results"),
        "call_successful": analysis.get("call_successful"),
    }
    phone = meta.get("phone_call") or {}  # null on browser calls
    if phone.get("call_sid"):
        checkin.twilio_call_sid = checkin.twilio_call_sid or phone["call_sid"]
    now = utcnow()
    checkin.ended_at = checkin.ended_at or now
    if checkin.started_at is None and meta.get("start_time_unix_secs"):
        from datetime import UTC, datetime

        checkin.started_at = datetime.fromtimestamp(meta["start_time_unix_secs"], UTC)
    if checkin.status not in ("cancelled",):
        checkin.status = "completed"
    checkin.postcall_status = "processing"
