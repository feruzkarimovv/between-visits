"""Interview engine: the backend owns the question order (docs/03 § "The interview engine").

The agent only reports what it heard; this module records answers, runs the rules after every answer,
escalates (paging before returning), and decides the next approved `say`.

interview_state = {"queue": [upcoming codes], "current": code, "asked": [codes asked so far],
                   "escalated": bool, "closed": bool, "intro_done": bool, "reported_flags": [ids]}
"""

import logging
import secrets
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from app import content
from app.audit import write_audit
from app.ids import new_id
from app.models import Answer, CheckIn, CheckInPlan, Patient, Study
from app.services import clinical, drafts, escalation
from app.timeutil import utcnow

log = logging.getLogger("bv.interview")

FLOW_TAIL = ["MEDS_NEW", "CARE_VISIT", "ANYTHING_ELSE"]


@dataclass
class Next:
    action: str  # ask | close
    item_code: str | None
    say: str


@dataclass
class ToolResult:
    ok: bool
    next: Next
    escalated: bool = False
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def envelope(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok, "next": asdict(self.next), "escalated": self.escalated}
        if self.error:
            out["error"] = self.error
        return out


class Ctx:
    """Everything a tool call needs about one check-in."""

    def __init__(self, session: Session, checkin: CheckIn):
        self.session = session
        self.checkin = checkin
        patient = session.get(Patient, checkin.patient_id)
        if patient is None:
            raise ValueError(f"patient {checkin.patient_id} missing")
        self.patient = patient
        self.plan = session.get(CheckInPlan, checkin.plan_id)
        self.study = session.get(Study, checkin.study_id)
        self.lang = checkin.language
        if not checkin.interview_state:
            start(checkin, self.plan)
        self.state: dict[str, Any] = checkin.interview_state

    @property
    def plan_flags(self) -> list[str]:
        return list(self.plan.red_flag_ids) if self.plan else [r["id"] for r in content.red_flags()]

    def vars(self) -> dict[str, str]:
        team = (self.study.study_team_name if self.study else {}) or content.study_doc()["study_team_name"]
        return {
            "study_team_name": team.get(self.lang) or team.get("en", ""),
            "patient_first_name": self.patient.first_name,
            "caregiver_name": self.patient.caregiver_name or ("un cuidador" if self.lang == "es" else "a caregiver"),
        }

    def save(self) -> None:
        self.checkin.interview_state = self.state
        flag_modified(self.checkin, "interview_state")
        self.session.add(self.checkin)

    def script(self, key: str) -> str:
        return content.script(key, self.lang, **self.vars())

    def question(self, code: str) -> str:
        if code == "CALL_CONSENT" and self.checkin.speaker == "caregiver":
            return self.script("caregiver_allowed")
        return content.question_say(code, self.lang, self.checkin.pace, **self.vars())


# ---- state helpers ------------------------------------------------------------------------------------


def initial_state(plan: CheckInPlan | None) -> dict[str, Any]:
    items = list(plan.items) if plan else list(content.plan_doc()["items"])
    return {
        "queue": ["CALL_CONSENT", *items, *FLOW_TAIL],
        "current": "IDENTITY",
        "asked": [],
        "escalated": False,
        "closed": False,
        "intro_done": False,
        "reported_flags": [],
    }


def start(checkin: CheckIn, plan: CheckInPlan | None) -> None:
    checkin.interview_state = initial_state(plan)
    flag_modified(checkin, "interview_state")


def _kind(code: str) -> str:
    return content.item(code).get("kind", "symptom") if content.has_item(code) else "flow"


def _drop_symptoms(state: dict[str, Any]) -> None:
    state["queue"] = [c for c in state["queue"] if _kind(c) not in ("symptom", "followup")]


def _advance(ctx: Ctx) -> str | None:
    """Move to the next queued item; returns it (or None when the queue is empty)."""
    st = ctx.state
    cur = st.get("current")
    if cur and cur not in st["asked"]:
        st["asked"].append(cur)
    st["current"] = st["queue"].pop(0) if st["queue"] else None
    return st["current"]


def _closing(ctx: Ctx) -> str:
    return ctx.script("closing_after_escalation" if ctx.state.get("escalated") else "closing")


def _close(ctx: Ctx, say: str) -> Next:
    st = ctx.state
    cur = st.get("current")
    if cur and cur not in st["asked"]:
        st["asked"].append(cur)
    st["current"] = None
    st["closed"] = True
    return Next("close", None, say)


def _ask_current(ctx: Ctx, prefix: str | None = None) -> Next:
    """Say the current question (with intro on the first plan item), or close if nothing is left."""
    st = ctx.state
    code = st.get("current")
    if code is None:
        closing = _closing(ctx)
        return _close(ctx, f"{prefix} {closing}" if prefix else closing)
    parts = [prefix] if prefix else []
    plan_items = list(ctx.plan.items) if ctx.plan else []
    if code in plan_items and not st.get("intro_done"):
        st["intro_done"] = True
        parts.append(ctx.script("intro_questions"))
    parts.append(ctx.question(code))
    return Next("ask", code, " ".join(parts))


def _next_after_answer(ctx: Ctx, prefix: str | None = None) -> Next:
    _advance(ctx)
    return _ask_current(ctx, prefix)


def _reask(ctx: Ctx, code: str, error: str) -> ToolResult:
    phrase = content.options_phrase(code, ctx.lang)
    if phrase and error == "invalid_option":
        say = content.script("reask_options", ctx.lang, options=phrase)
    else:
        say = f"{ctx.script('reask_current')} {ctx.question(code)}"
    return ToolResult(False, Next("ask", code, say), bool(ctx.state.get("escalated")), error)


# ---- escalation glue ----------------------------------------------------------------------------------


def _escalation_say(ctx: Ctx, outcome: str, esc_level: str, flag_ids: list[str]) -> str | None:
    """Approved line for a new/raised/added escalation (None when nothing new happened)."""
    if outcome == "none":
        return None
    if outcome == "added":
        return ctx.script("added_to_page")
    for fid in flag_ids:  # a flag-specific script (e.g. crisis line) wins
        if content.has_red_flag(fid) and content.red_flag(fid).get("say_script"):
            return ctx.script(content.red_flag(fid)["say_script"])
    key = content.level_say_script(esc_level) or "urgent_line"
    return ctx.script(key)


def _run_rules(ctx: Ctx, reason: str = "live_rule") -> tuple[str, str, list[str]]:
    """Recompute findings and escalate any new red flags. Returns (outcome, level, new_flag_ids)."""
    clinical.recompute_findings(ctx.session, ctx.checkin, ctx.patient, ctx.plan_flags)
    hits = clinical.current_hits(ctx.session, ctx.checkin, ctx.patient, ctx.plan_flags)
    known = clinical.all_escalated_flag_ids(ctx.session, ctx.checkin.id)
    new_ids = [h.id for h in hits if h.id not in known and h.level in escalation.PAGED_LEVELS]
    outcome, esc = escalation.escalate_flags(ctx.session, ctx.checkin, ctx.patient, hits, reason)
    if outcome != "none" and esc is not None:
        ctx.state["escalated"] = True
        # findings may now link to the escalation level
        clinical.recompute_findings(ctx.session, ctx.checkin, ctx.patient, ctx.plan_flags)
        return outcome, esc.level, new_ids
    return "none", "none", []


def _respond_to_escalation(ctx: Ctx, outcome: str, level: str, new_ids: list[str], repeat_current: bool) -> Next:
    """Build `next` after an escalation outcome. Emergency closes; urgent drops remaining symptom items.

    repeat_current=False: the current item was just answered, so move on.
    repeat_current=True: the current item is still unanswered (red flag reported mid-question, or a
    correction to an earlier item); re-ask it, unless it is a symptom item that the urgent page drops."""
    line = _escalation_say(ctx, outcome, level, new_ids)
    if outcome in ("new", "raised") and level == "emergency":
        return _close(ctx, f"{line} {ctx.script('closing_after_escalation')}")
    if outcome in ("new", "raised"):
        _drop_symptoms(ctx.state)
        cur = ctx.state.get("current")
        if repeat_current and cur and _kind(cur) in ("symptom", "followup"):
            ctx.state["current"] = None  # dropped, never answered
            return _next_after_answer(ctx, line)
    if repeat_current:
        return _ask_current(ctx, line)
    return _next_after_answer(ctx, line)


# ---- tools --------------------------------------------------------------------------------------------


def _closed_result(ctx: Ctx) -> ToolResult:
    return ToolResult(True, Next("close", None, _closing(ctx)), bool(ctx.state.get("escalated")))


def _valid(code: str, option_code: str | None, numeric_value: float | None, unit: str | None) -> tuple[bool, str | None]:
    """Validate an answer against the item's scale. Returns (ok, normalized unit)."""
    sc = content.item(code)["scale"]
    if sc == "free_text":
        return True, None
    opts = content.item_options(code)
    if content.is_numeric(code):
        if option_code in opts:
            return True, None
        if numeric_value is None:
            return False, None
        units = content.item_units(code)
        if unit not in units:
            if sc == "temperature":
                unit = "fahrenheit" if numeric_value > 45 else "celsius"
            else:
                unit = units[0] if units else None
        return True, unit
    return option_code in opts, None


def record_answer(
    session: Session,
    checkin: CheckIn,
    *,
    item_code: str | None,
    option_code: str | None,
    numeric_value: float | None,
    unit: str | None,
    verbatim_quote: str,
    source: str = "live_tool",
) -> ToolResult:
    ctx = Ctx(session, checkin)
    st = ctx.state
    if st.get("closed"):
        return _closed_result(ctx)
    code = item_code or st.get("current")
    if not code or not content.has_item(code) or (code != st.get("current") and code not in st["asked"]):
        cur = st.get("current")
        if cur is None:
            return _closed_result(ctx)
        res = _reask(ctx, cur, "unexpected_item")
        ctx.save()
        return res
    if option_code == "":
        option_code = None
    ok, norm_unit = _valid(code, option_code, numeric_value, unit)
    if not ok:
        res = _reask(ctx, code, "invalid_option")
        ctx.save()
        return res
    is_correction = code != st.get("current")

    _upsert_answer(ctx, code, option_code, numeric_value if option_code is None else None, norm_unit, verbatim_quote, source)
    _mark_in_progress(ctx)

    # flow items
    if code == "IDENTITY":
        if option_code == "no":
            nxt = _close(ctx, ctx.script("wrong_person_close"))
            return _finish(ctx, nxt)
        if option_code != "yes":
            return _finish(ctx, _reask(ctx, code, "unclear").next, ok=False, error="unclear")
        if ctx.checkin.speaker is None:
            ctx.checkin.speaker = "patient"
        return _finish(ctx, _next_after_answer(ctx))
    if code == "CALL_CONSENT":
        if option_code in ("no", "later"):
            escalation.create_callback(
                session, ctx.checkin, ctx.patient, "patient_request", "Patient asked to be called back later."
            )
            return _finish(ctx, _close(ctx, ctx.script("consent_later")))
        if option_code != "yes":
            return _finish(ctx, _reask(ctx, code, "unclear").next, ok=False, error="unclear")
        return _finish(ctx, _next_after_answer(ctx))
    if code == "MEDS_DETAIL":
        drafts.medication(session, ctx.checkin, verbatim_quote, verbatim_quote, ctx.lang, _src(source))
    elif code == "CARE_VISIT" and option_code == "yes" and not is_correction:
        escalation.create_callback(
            session, ctx.checkin, ctx.patient, "care_visit", "Reports an ER, urgent care or other doctor visit."
        )
        drafts.nurse_task(session, ctx.checkin, "care_visit", "Reports an ER, urgent care or other doctor visit.",
                          verbatim_quote, ctx.lang, _src(source))
    elif code == "CARE_VISIT_DETAIL":
        _append_to_task(ctx, "care_visit", verbatim_quote, source)
    elif code == "ANYTHING_ELSE" and option_code != "no" and verbatim_quote.strip() and not is_correction:
        drafts.nurse_task(session, ctx.checkin, "anything_else", verbatim_quote, verbatim_quote, ctx.lang, _src(source))

    _insert_followups(ctx, code, option_code)

    # rules after every answer
    outcome, level, new_ids = "none", "none", []
    if content.term_of(code):
        try:
            outcome, level, new_ids = _run_rules(ctx)
        except Exception as e:  # noqa: BLE001  fail safe: a rules failure on a symptom answer escalates
            log.exception("rules_failed checkin_id=%s item=%s", ctx.checkin.id, code)
            outcome, level, new_ids = _fail_safe_escalation(ctx, repr(e))
    if outcome != "none":
        return _finish(ctx, _respond_to_escalation(ctx, outcome, level, new_ids, repeat_current=is_correction))
    if is_correction:
        return _finish(ctx, _ask_current(ctx))
    return _finish(ctx, _next_after_answer(ctx))


def _src(source: str) -> str:
    return "replay" if source == "replay" else source


def _fail_safe_escalation(ctx: Ctx, err: str) -> tuple[str, str, list[str]]:
    esc = escalation.Escalation(
        id=new_id("esc"), checkin_id=ctx.checkin.id, patient_id=ctx.patient.id, level="urgent",
        red_flag_ids=[], reason="live_rule", summary_en="Rules engine error on a symptom answer; please review.",
        patient_language=ctx.lang, ack_token=secrets.token_urlsafe(24),
    )
    ctx.session.add(esc)
    ctx.session.flush()
    escalation.page(ctx.session, esc, ctx.patient)
    ctx.state["escalated"] = True
    return "new", "urgent", []


def _finish(ctx: Ctx, nxt: Next, ok: bool = True, error: str | None = None) -> ToolResult:
    ctx.save()
    return ToolResult(ok, nxt, bool(ctx.state.get("escalated")), error)


def _mark_in_progress(ctx: Ctx) -> None:
    c = ctx.checkin
    if c.status in ("scheduled", "dialing"):
        c.status = "in_progress"
        c.started_at = c.started_at or utcnow()


def _upsert_answer(
    ctx: Ctx, code: str, option_code: str | None, numeric_value: float | None, unit: str | None, quote: str, source: str
) -> Answer:
    s = ctx.session
    existing = s.exec(select(Answer).where(Answer.checkin_id == ctx.checkin.id, Answer.item_code == code)).first()
    reporter = "caregiver" if ctx.checkin.speaker == "caregiver" else "patient"
    if existing:
        before = {"option_code": existing.option_code, "numeric_value": existing.numeric_value, "unit": existing.unit,
                  "verbatim_quote": existing.verbatim_quote}
        existing.option_code, existing.numeric_value, existing.unit = option_code, numeric_value, unit
        existing.verbatim_quote, existing.reporter, existing.created_at = quote, reporter, utcnow()
        s.add(existing)
        write_audit(s, actor="agent", role="agent", action="answer.corrected", entity_type="Answer",
                    entity_id=existing.id, before=before,
                    after={"option_code": option_code, "numeric_value": numeric_value, "unit": unit,
                           "verbatim_quote": quote}, checkin_id=ctx.checkin.id)
        log.info("answer_corrected checkin_id=%s item=%s", ctx.checkin.id, code)
        s.flush()
        return existing
    a = Answer(
        id=new_id("ans"), checkin_id=ctx.checkin.id, item_code=code, term=content.term_of(code),
        attribute=content.attribute_of(code), option_code=option_code, numeric_value=numeric_value, unit=unit,
        reporter=reporter, verbatim_quote=quote, quote_lang=ctx.lang,
        source="replay" if source == "replay" else source,
    )
    s.add(a)
    write_audit(s, actor="agent", role="agent", action="answer.recorded", entity_type="Answer", entity_id=a.id,
                after={"item_code": code, "option_code": option_code, "numeric_value": numeric_value, "unit": unit},
                checkin_id=ctx.checkin.id)
    s.flush()
    return a


def _insert_followups(ctx: Ctx, code: str, option_code: str | None) -> None:
    st = ctx.state
    to_insert: list[str] = []
    for f in content.item(code).get("followups", []):
        if option_code not in f["when"]["in"]:
            continue
        if f.get("only_if") == "baseline_stools_missing" and (ctx.patient.baseline or {}).get("stools_per_day") is not None:
            continue
        fc = f["item"]
        if fc in st["asked"] or fc in st["queue"] or fc == st.get("current"):
            continue
        to_insert.append(fc)
    st["queue"] = to_insert + st["queue"]


def _append_to_task(ctx: Ctx, category: str, quote: str, source: str) -> None:
    for d in reversed(drafts.drafts_for(ctx.session, ctx.checkin.id, "NURSE_TASK")):
        if d.payload.get("category") == category:
            d.evidence = [*d.evidence, drafts.evidence(quote, ctx.lang, _src(source))]
            d.payload = {**d.payload, "detail": quote}
            ctx.session.add(d)
            return
    drafts.nurse_task(ctx.session, ctx.checkin, category, quote, quote, ctx.lang, _src(source))


def report_red_flag(session: Session, checkin: CheckIn, *, red_flag_id: str, verbatim_quote: str,
                    reason: str = "agent_report", source: str = "live_tool") -> ToolResult:
    """Never second-guessed: escalates at the flag's level even after the interview closed."""
    ctx = Ctx(session, checkin)
    st = ctx.state
    if red_flag_id not in st["reported_flags"]:
        st["reported_flags"].append(red_flag_id)
    write_audit(session, actor="agent", role="agent", action="red_flag.reported", entity_type="CheckIn",
                entity_id=checkin.id, after={"red_flag_id": red_flag_id, "verbatim_quote": verbatim_quote},
                checkin_id=checkin.id)
    _mark_in_progress(ctx)
    ctx.save()
    session.flush()
    outcome, level, new_ids = _run_rules(ctx, reason=reason)
    if st.get("closed"):
        return _finish(ctx, Next("close", None, _closing(ctx)))
    if outcome == "none":
        # already covered by an open page: acknowledge and continue
        if red_flag_id in clinical.all_escalated_flag_ids(session, checkin.id):
            return _finish(ctx, _ask_current(ctx, ctx.script("added_to_page")))
        return _finish(ctx, _ask_current(ctx))
    return _finish(ctx, _respond_to_escalation(ctx, outcome, level, new_ids, repeat_current=True))


def record_medication_change(session: Session, checkin: CheckIn, *, description: str, verbatim_quote: str,
                             source: str = "live_tool") -> ToolResult:
    ctx = Ctx(session, checkin)
    st = ctx.state
    drafts.medication(session, checkin, description, verbatim_quote, ctx.lang, _src(source))
    log.info("medication_recorded checkin_id=%s", checkin.id)
    if st.get("closed"):
        return _closed_result(ctx)
    if st.get("current") == "MEDS_DETAIL":
        return _finish(ctx, _next_after_answer(ctx))
    if st.get("current") == "MEDS_NEW":
        # the person described the medicine while answering MEDS_NEW: record yes and skip MEDS_DETAIL
        _upsert_answer(ctx, "MEDS_NEW", "yes", None, None, verbatim_quote, source)
        st["asked"].append("MEDS_DETAIL")
        return _finish(ctx, _next_after_answer(ctx))
    return _finish(ctx, _ask_current(ctx))


def request_human(session: Session, checkin: CheckIn, *, reason: str, verbatim_quote: str,
                  source: str = "live_tool") -> ToolResult:
    ctx = Ctx(session, checkin)
    st = ctx.state
    category = reason if reason in ("wants_person", "medical_question", "distress", "other") else "other"
    esc_reason = "medical_question" if category == "medical_question" else "patient_request"
    summary = {
        "medical_question": "Patient asked a medical question; nurse to call back.",
        "wants_person": "Patient asked to speak with a person.",
        "distress": "Patient sounded very distressed; asked for a person.",
        "other": "Patient needs a human follow-up.",
    }[category]
    escalation.create_callback(session, checkin, ctx.patient, esc_reason, summary)
    drafts.nurse_task(session, checkin, category, verbatim_quote, verbatim_quote, ctx.lang, _src(source))
    if st.get("closed"):
        return _closed_result(ctx)
    if category in ("wants_person", "distress"):
        return _finish(ctx, _close(ctx, ctx.script("wants_person_close")))
    return _finish(ctx, _ask_current(ctx, ctx.script("deferral_medical")))


def set_speaker(session: Session, checkin: CheckIn, *, speaker: str, relation: str | None) -> ToolResult:
    ctx = Ctx(session, checkin)
    st = ctx.state
    if st.get("closed"):
        return _closed_result(ctx)
    before = {"speaker": checkin.speaker}
    if speaker == "caregiver":
        if not ctx.patient.caregiver_may_answer:
            escalation.create_callback(session, checkin, ctx.patient, "patient_request",
                                       "Caregiver answered; caregiver proxy not permitted. Call back the patient.")
            checkin.speaker = "caregiver"
            return _finish(ctx, _close(ctx, ctx.script("caregiver_not_allowed")))
        checkin.speaker = "caregiver"
        checkin.caregiver_relation = relation or ctx.patient.caregiver_relation
    else:
        checkin.speaker = "patient"
    write_audit(session, actor="agent", role="agent", action="checkin.speaker_set", entity_type="CheckIn",
                entity_id=checkin.id, before=before, after={"speaker": checkin.speaker, "relation": relation},
                checkin_id=checkin.id)
    _mark_in_progress(ctx)
    if st.get("current") == "IDENTITY":
        return _finish(ctx, _next_after_answer(ctx))
    return _finish(ctx, _ask_current(ctx))


def current_say(session: Session, checkin: CheckIn) -> str | None:
    ctx = Ctx(session, checkin)
    cur = ctx.state.get("current")
    return ctx.question(cur) if cur else None
