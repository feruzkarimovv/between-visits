"""SQLModel tables, exactly as docs/02-data-model.md (plus a few bookkeeping columns noted inline).

JSON columns are plain SQLAlchemy JSON: always reassign (or flag_modified) after mutating them in place.
Timestamps are stored as UTC and always come back timezone-aware.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, TypeDecorator
from sqlmodel import Field, SQLModel

from app.timeutil import ensure_utc, utcnow


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):  # noqa: ANN001
        value = ensure_utc(value)
        return value.replace(tzinfo=None) if value else None

    def process_result_value(self, value: datetime | None, dialect):  # noqa: ANN001
        return ensure_utc(value)


def dt_col(nullable: bool = True) -> Any:
    return Column(UTCDateTime(), nullable=nullable)


def json_col() -> Any:
    return Column(JSON, nullable=True)


class Study(SQLModel, table=True):
    id: str = Field(primary_key=True)
    nct_id: str
    title_short: str
    drug_class: str
    masking: str
    site_id: str
    site_name: str
    study_team_name: dict[str, str] = Field(default_factory=dict, sa_column=json_col())
    active_plan_id: str | None = None
    sponsor_study_number: str | None = None


class CheckInPlan(SQLModel, table=True):
    id: str = Field(primary_key=True)
    study_id: str = Field(index=True)
    version: int = 1
    status: str = "draft"  # draft | approved | superseded
    items: list[str] = Field(default_factory=list, sa_column=json_col())
    red_flag_ids: list[str] = Field(default_factory=list, sa_column=json_col())
    schedule_days_after_dose: list[int] = Field(default_factory=list, sa_column=json_col())
    source: str = "seed"  # seed | protocol_pdf
    source_citations: list[dict[str, Any]] = Field(default_factory=list, sa_column=json_col())
    approved_by: str | None = None
    approved_at: datetime | None = Field(default=None, sa_column=dt_col())


class Patient(SQLModel, table=True):
    id: str = Field(primary_key=True)
    study_id: str = Field(index=True)
    subject_id: str = Field(index=True)
    first_name: str
    last_name: str
    age: int
    sex: str
    language: str  # en | es
    pace: str  # standard | extra_time
    hearing: str = "typical"
    caregiver_name: str | None = None
    caregiver_relation: str | None = None
    caregiver_may_answer: bool = False
    phone_e164: str = ""
    dose_dates: list[str] = Field(default_factory=list, sa_column=json_col())  # ISO dates
    baseline: dict[str, Any] = Field(default_factory=dict, sa_column=json_col())
    notes: str = ""


class CheckIn(SQLModel, table=True):
    id: str = Field(primary_key=True)
    patient_id: str = Field(index=True)
    study_id: str
    plan_id: str
    day_after_dose: int | None = None
    scheduled_for: datetime | None = Field(default=None, sa_column=dt_col())
    channel: str = "phone"  # phone | phone_inbound | web | replay
    language: str = "en"
    pace: str = "standard"
    agent_variant: str = ""
    el_agent_id: str | None = None
    el_conversation_id: str | None = Field(default=None, index=True)
    twilio_call_sid: str | None = None
    status: str = "scheduled"  # scheduled|dialing|in_progress|completed|no_answer|failed|cancelled
    speaker: str | None = None  # patient | caregiver
    caregiver_relation: str | None = None
    interview_state: dict[str, Any] = Field(default_factory=dict, sa_column=json_col())
    transcript: list[dict[str, Any]] = Field(default_factory=list, sa_column=json_col())
    summary_en: str | None = None
    analysis: dict[str, Any] | None = Field(default=None, sa_column=json_col())  # ElevenLabs extra signals
    postcall_status: str | None = None  # None | processing | done | failed (bookkeeping)
    started_at: datetime | None = Field(default=None, sa_column=dt_col())
    ended_at: datetime | None = Field(default=None, sa_column=dt_col())
    duration_s: int | None = None
    termination_reason: str | None = None
    created_at: datetime = Field(default_factory=utcnow, sa_column=dt_col(False))


class Answer(SQLModel, table=True):
    id: str = Field(primary_key=True)
    checkin_id: str = Field(index=True)
    item_code: str
    term: str | None = None
    attribute: str
    option_code: str | None = None
    numeric_value: float | None = None
    unit: str | None = None
    reporter: str = "patient"
    verbatim_quote: str = ""
    quote_lang: str = "en"
    t_s: float | None = None
    source: str = "live_tool"  # live_tool | post_call_extraction | replay
    created_at: datetime = Field(default_factory=utcnow, sa_column=dt_col(False))


class Finding(SQLModel, table=True):
    id: str = Field(primary_key=True)
    checkin_id: str = Field(index=True)
    term: str
    provisional_grade: int | None = None
    grade_basis: str = "needs_clinician"  # rule | needs_clinician
    rule_id: str | None = None
    rule_text: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict, sa_column=json_col())
    red_flag_ids: list[str] = Field(default_factory=list, sa_column=json_col())
    escalation_level: str = "none"
    answer_ids: list[str] = Field(default_factory=list, sa_column=json_col())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=dt_col(False))


class Escalation(SQLModel, table=True):
    id: str = Field(primary_key=True)
    checkin_id: str = Field(index=True)
    patient_id: str = Field(index=True)
    level: str  # emergency | urgent | callback
    red_flag_ids: list[str] = Field(default_factory=list, sa_column=json_col())
    reason: str  # live_rule | agent_report | post_call_safety_net | patient_request | medical_question
    summary_en: str = ""
    patient_language: str = "en"
    status: str = "open"  # open | acknowledged | resolved
    created_at: datetime = Field(default_factory=utcnow, sa_column=dt_col(False))
    paged_at: datetime | None = Field(default=None, sa_column=dt_col())
    last_paged_at: datetime | None = Field(default=None, sa_column=dt_col())  # bookkeeping for re-page
    page_channel: str | None = None
    page_target_name: str | None = None
    page_ref: str | None = None
    ack_token: str = ""
    repage_count: int = 0
    backup_paged_at: datetime | None = Field(default=None, sa_column=dt_col())
    acknowledged_at: datetime | None = Field(default=None, sa_column=dt_col())
    acknowledged_by: str | None = None
    ack_method: str | None = None  # push_button | phone_keypress | dashboard
    resolved_at: datetime | None = Field(default=None, sa_column=dt_col())
    resolution_note: str | None = None


class DraftEntry(SQLModel, table=True):
    id: str = Field(primary_key=True)
    checkin_id: str = Field(index=True)
    patient_id: str = Field(index=True)
    kind: str  # AE | CM | NURSE_TASK
    status: str = "draft"  # draft | confirmed | rejected
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=json_col())
    evidence: list[dict[str, Any]] = Field(default_factory=list, sa_column=json_col())
    reviewed_by: str | None = None
    reviewed_at: datetime | None = Field(default=None, sa_column=dt_col())
    review_note: str | None = None
    investigator: dict[str, Any] | None = Field(default=None, sa_column=json_col())
    created_at: datetime = Field(default_factory=utcnow, sa_column=dt_col(False))


class SAEReport(SQLModel, table=True):
    id: str = Field(primary_key=True)
    draft_entry_id: str = Field(index=True)
    patient_id: str
    checkin_id: str
    status: str = "draft"  # draft | signed | sent
    aware_at: datetime = Field(sa_column=dt_col(False))
    due_at: datetime = Field(sa_column=dt_col(False))
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=json_col())
    narrative_ai_draft: str = ""
    narrative_final: str | None = None
    signed_by: str | None = None
    signed_at: datetime | None = Field(default=None, sa_column=dt_col())
    sent_at: datetime | None = Field(default=None, sa_column=dt_col())
    sponsor_received_at: datetime | None = Field(default=None, sa_column=dt_col())
    created_at: datetime = Field(default_factory=utcnow, sa_column=dt_col(False))


class AuditEvent(SQLModel, table=True):
    id: str = Field(primary_key=True)
    ts: datetime = Field(default_factory=utcnow, sa_column=dt_col(False))
    actor: str
    role: str
    action: str
    entity_type: str
    entity_id: str = Field(index=True)
    checkin_id: str | None = Field(default=None, index=True)  # convenience filter
    before: dict[str, Any] | None = Field(default=None, sa_column=json_col())
    after: dict[str, Any] | None = Field(default=None, sa_column=json_col())
    note: str | None = None


def parse_date(s: str) -> date:
    return date.fromisoformat(s)
