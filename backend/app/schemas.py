"""Request/response models for every endpoint in docs/03-api-contracts.md (they define /openapi.json)."""

from datetime import date, datetime
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

# ---- demo identity (docs/03 §5.1, §6.1) ----------------------------------------------------------------

# `X-BV-Role` values. A missing or unknown header means DEFAULT_ROLE; a role-restricted route answers any other
# role with 403 `wrong_role` (`require_role` in app/routers/api.py). The role is written to AuditEvent.role.
Role = Literal["coordinator", "investigator", "sponsor", "cra"]
ROLES: tuple[Role, ...] = get_args(Role)
DEFAULT_ROLE: Role = "coordinator"

# ---- agent tools ---------------------------------------------------------------------------------------


class ToolBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    checkin_id: str | None = None
    conversation_id: str | None = None


class RecordAnswerIn(ToolBase):
    item_code: str | None = None
    option_code: str | None = None
    numeric_value: float | None = None
    unit: str | None = None
    verbatim_quote: str = ""


class ReportRedFlagIn(ToolBase):
    red_flag_id: str
    verbatim_quote: str = ""
    language: str | None = None


class RecordMedicationIn(ToolBase):
    description: str
    verbatim_quote: str = ""
    language: str | None = None


class RequestHumanIn(ToolBase):
    reason: str = "other"
    verbatim_quote: str = ""
    language: str | None = None


class SetSpeakerIn(ToolBase):
    speaker: Literal["patient", "caregiver"]
    relation: str | None = None


class NextStep(BaseModel):
    action: Literal["ask", "close"]
    item_code: str | None = None
    say: str


class ToolEnvelope(BaseModel):
    ok: bool
    next: NextStep
    escalated: bool = False
    error: str | None = None


# ---- shared out models ---------------------------------------------------------------------------------


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorOut(BaseModel):
    error: ErrorBody


class Health(BaseModel):
    ok: bool
    demo_mode: bool
    version: str
    commit: str
    app_env: str
    pager_channel: str
    phone_calls_enabled: bool = False
    browser_calls_enabled: bool = False
    phone_calls_note: str | None = None
    browser_calls_note: str | None = None


class StudyOut(BaseModel):
    id: str
    nct_id: str
    title_short: str
    drug_class: str
    masking: str
    site_id: str
    site_name: str
    active_plan_id: str | None


class PlanItemOut(BaseModel):
    item_code: str
    term: str | None
    attribute: str
    kind: str
    text: dict[str, str]
    options_say: dict[str, str] | None = None
    source: str
    followups: list[str] = []


class PlanRedFlagOut(BaseModel):
    id: str
    level: str
    label_en: str
    rule_based: bool


class PlanOut(BaseModel):
    id: str
    version: int
    status: str
    approved_by: str | None
    approved_at: datetime | None
    schedule_days_after_dose: list[int]
    items: list[PlanItemOut]
    red_flags: list[PlanRedFlagOut]
    source: str
    source_citations: list[dict[str, Any]]


class NextDue(BaseModel):
    day_after_dose: int
    date: date


class PatientSummary(BaseModel):
    id: str
    subject_id: str
    first_name: str
    last_name: str
    age: int
    sex: str
    language: str
    pace: str
    hearing: str
    caregiver_name: str | None
    caregiver_relation: str | None
    caregiver_may_answer: bool = False
    next_due: NextDue | None = None
    last_checkin_status: str | None = None
    open_escalations: int = 0


class PatientBrief(BaseModel):
    id: str
    subject_id: str
    first_name: str
    last_name: str | None = None
    language: str
    pace: str
    caregiver_name: str | None = None


class InterviewStateOut(BaseModel):
    current: str | None = None
    asked: list[str] = []
    queue: list[str] = []
    escalated: bool = False
    closed: bool = False


class CheckInOut(BaseModel):
    id: str
    patient_id: str
    status: str
    channel: str
    language: str
    pace: str
    agent_variant: str
    day_after_dose: int | None
    scheduled_for: datetime | None
    speaker: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_s: int | None
    termination_reason: str | None
    el_conversation_id: str | None
    summary_en: str | None
    postcall_status: str | None
    created_at: datetime
    interview_state: InterviewStateOut


class AnswerOut(BaseModel):
    id: str
    item_code: str
    term: str | None
    attribute: str
    option_code: str | None
    numeric_value: float | None
    unit: str | None
    verbatim_quote: str
    quote_lang: str
    reporter: str
    source: str
    t_s: float | None
    created_at: datetime


class FindingOut(BaseModel):
    id: str
    term: str
    provisional_grade: int | None
    grade_basis: str
    rule_id: str | None
    rule_text: str | None
    inputs: dict[str, Any]
    red_flag_ids: list[str]
    escalation_level: str
    answer_ids: list[str]


class EscalationOut(BaseModel):
    id: str
    checkin_id: str
    patient_id: str
    level: str
    status: str
    reason: str
    red_flag_ids: list[str]
    red_flag_labels: list[str] = []
    summary_en: str
    patient_language: str
    created_at: datetime
    paged_at: datetime | None
    page_channel: str | None
    page_target_name: str | None
    repage_count: int
    backup_paged_at: datetime | None
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    ack_method: str | None
    resolved_at: datetime | None
    resolution_note: str | None
    seconds_open: int
    seconds_to_ack: int | None = None
    patient: PatientBrief | None = None


class EvidenceOut(BaseModel):
    quote: str
    quote_lang: str
    translation_en: str | None = None
    translation_label: str | None = None
    t_s: float | None = None
    turn_index: int | None = None
    source: str


class DraftOut(BaseModel):
    id: str
    checkin_id: str
    patient_id: str
    kind: str
    status: str
    payload: dict[str, Any]
    evidence: list[EvidenceOut]
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str | None
    investigator: dict[str, Any] | None
    created_at: datetime
    sae_report_id: str | None = None
    patient: PatientBrief | None = None
    origin: Literal["between_visits"] = "between_visits"  # computed, not stored (docs/03 §6.5)


class TranscriptTurn(BaseModel):
    i: int
    role: str
    text: str
    t_s: float | None = None
    lang: str | None = None


class CheckInDetail(BaseModel):
    checkin: CheckInOut
    patient: PatientBrief
    answers: list[AnswerOut]
    findings: list[FindingOut]
    escalations: list[EscalationOut]
    drafts: list[DraftOut]
    transcript: list[TranscriptTurn]
    current_question: str | None = None


class TimelinePoint(BaseModel):
    checkin_id: str
    date: date
    provisional_grade: int | None
    answer: str | None


class TermTimeline(BaseModel):
    term: str
    points: list[TimelinePoint]


class PatientDetail(PatientSummary):
    phone_on_file: bool
    baseline: dict[str, Any]
    notes: str
    dose_dates: list[date]
    checkins: list[CheckInOut]
    timeline: list[TermTimeline]


class CheckInListItem(BaseModel):
    """A check-in scheduled or run on the date, or a patient due that day without one (status `due`)."""

    id: str | None
    status: str
    channel: str | None
    day_after_dose: int | None
    started_at: datetime | None = None
    patient: PatientSummary
    open_escalations: int = 0


class CreateCheckInIn(BaseModel):
    channel: Literal["phone", "web"] = "phone"
    day_after_dose: int | None = None


class WebSession(BaseModel):
    agent_id: str
    conversation_token: str
    conversation_id: str | None
    dynamic_variables: dict[str, str]
    user_id: str


class CreateCheckInOut(BaseModel):
    checkin: CheckInOut
    web_session: WebSession | None = None


class WebStartedIn(BaseModel):
    conversation_id: str | None = None


class OkOut(BaseModel):
    ok: bool = True


class ResolveIn(BaseModel):
    note: str | None = None


class DraftPatchIn(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class ConfirmIn(BaseModel):
    note: str | None = None


class RejectIn(BaseModel):
    reason: str


SeriousnessCriterion = Literal[
    "death", "life_threatening", "hospitalization", "disability", "congenital_anomaly", "important_medical_event"
]
Relatedness = Literal["not_related", "unlikely_related", "possibly_related", "probably_related", "related"]


class InvestigatorIn(BaseModel):
    is_serious: bool
    seriousness_criteria: list[SeriousnessCriterion] = []
    relatedness: Relatedness
    sign: bool = True


class SAEOut(BaseModel):
    id: str
    draft_entry_id: str
    patient_id: str
    checkin_id: str
    status: str
    aware_at: datetime
    due_at: datetime
    seconds_until_due: int
    payload: dict[str, Any]
    narrative_ai_draft: str
    narrative_final: str | None
    signed_by: str | None
    signed_at: datetime | None
    sent_at: datetime | None
    sponsor_received_at: datetime | None
    created_at: datetime
    patient: PatientBrief | None = None


class InvestigatorOut(BaseModel):
    draft: DraftOut
    sae_report: SAEOut | None = None


class SAEPatchIn(BaseModel):
    narrative_final: str | None = None
    payload: dict[str, Any] | None = None


class ValidCaseChecks(BaseModel):
    identifiable_patient: bool
    identifiable_reporter: bool
    suspect_product: bool
    adverse_event: bool


class SponsorInboxItem(BaseModel):
    sae_id: str
    received_at: datetime
    due_at: datetime
    on_time: bool
    seconds_before_deadline: int
    study: str
    site: str
    subject_id: str
    event_term: str
    seriousness_criteria: list[str]
    provisional_grade: int | None
    relatedness: str | None
    valid_case_checks: ValidCaseChecks
    narrative: str
    report: dict[str, Any]


class AuditOut(BaseModel):
    id: str
    ts: datetime
    actor: str
    role: str
    action: str
    entity_type: str
    entity_id: str
    checkin_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    note: str | None
    seq: int
    prev_hash: str
    hash: str


class AuditVerifyOut(BaseModel):
    """`GET /api/audit/verify` (docs/03 §6.6): always 200; a broken chain is ok:false."""

    ok: bool
    n_events: int
    head_hash: str
    first_bad_id: str | None
    first_bad_seq: int | None


class ScenarioOut(BaseModel):
    id: str
    title: str
    duration_s: float
    patient_id: str


class ReplayOut(BaseModel):
    checkin_id: str
