"""Request/response models for every endpoint in docs/03-api-contracts.md (they define /openapi.json)."""

from datetime import date, datetime
from enum import IntEnum
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class SiteSignalHealth(BaseModel):
    """`health.site_signal` (docs/03 §6.7). `available` is true only when MONITORING_OUT/signal_run.json exists and
    loads; `sap_tag_commit` and `generated_at` then come from its `run` object, otherwise they are null."""

    available: bool
    sap_tag_commit: str | None
    generated_at: str | None
    data_origin: Literal["SIMULATED"]


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
    site_signal: SiteSignalHealth


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
    """`GET /api/demo/scenarios` item (docs/03 §6.2). A scripted scenario is always labeled "Scripted";
    `audio_url` is set only when `scenarios/audio/<id>.mp3` exists on the server (audio is never in git)."""

    id: str
    title: str
    duration_s: float
    patient_id: str
    recorded: bool
    recorded_at: date | None
    label: str
    audio_url: str | None


class ReplaySpeed(IntEnum):
    """`POST /api/demo/replay/{id}?speed=`: playback multiplier (2 = twice real time); anything else is 422."""

    X1 = 1
    X2 = 2
    X4 = 4


class ReplayOut(BaseModel):
    checkin_id: str


# ---- real-voice evidence (docs/03 §6.11) -----------------------------------------------------------------


class VoiceCheckCall(BaseModel):
    """One real browser call against the deployed live backend (V10). Unknown keys in the file pass through."""

    model_config = ConfigDict(extra="allow")
    variant: str | None = None
    conversation_id: str | None = None
    checkin_id: str | None = None
    scenario: str | None = None
    disclosure_first_turn: bool | None = None
    red_flag_expected: bool | None = None
    paged: bool | None = None
    utterance_to_page_s: float | None = None
    page_to_ack_s: float | None = None
    grade: int | None = None
    rule_id: str | None = None


class VoiceChecksOut(BaseModel):
    """`GET /api/eval/voice-checks`: `eval/results/voice_checks.json` plus `data_origin: "MEASURED"`. Served with
    exclude_unset, so the body is the file as written (never pooled with text-mode evaluation results)."""

    model_config = ConfigDict(extra="allow")
    run_at: str | None = None
    backend: str | None = None
    agent_llm: str | None = None
    data_origin: Literal["MEASURED"]
    calls: list[VoiceCheckCall] = Field(default_factory=list)


# ---- Site Signal (docs/03 §5.1-5.3, docs/02 § Site Signal) ------------------------------------------------
#
# File-backed shapes of the committed study in MONITORING_OUT (`monitoring/out/*.json`, written by
# `make site-signal`) and the read payloads built from them. `services/site_signal.py` validates every file
# against these models; any error is 503 `site_signal_unavailable` (REQ-025). Typed shapes ignore unknown keys,
# so nothing beyond the contract (a planted label, say) reaches a payload by accident; the validation summary
# and the equity file are pass-through files and keep every key.

DataOrigin = Literal["SIMULATED", "MEASURED", "MIXED"]
SignalTier = Literal["watch", "look", "none", "not_computed"]  # no tier means "clean"; none renders green
NotComputedReason = Literal[
    "error", "integrated_mode", "low_coverage", "insufficient_patients", "insufficient_episodes",
    "study_below_min_sites",
]
EpisodeStatus = Literal["paged", "pending", "not_evaluated", "matched", "unmatched"]  # docs/11 §6.4 precedence
QuoteSource = Literal["live_call", "replay", "synthetic"]
SubjectLanguage = Literal["en", "es"]
SubjectPace = Literal["standard", "extra_time"]
AnswerKeyLabel = Literal[
    "gross_under", "under_50", "under_25", "language_gap", "decoy_healthy_casemix", "honest_low_diligence",
    "low_coverage", "small_site", "honest",
]
COMMITTED_RUN_ID = "sr_committed"  # the committed study: a reserved literal, never a database row


class _SignalShape(BaseModel):
    model_config = ConfigDict(extra="ignore")


class TierThresholds(_SignalShape):
    """Look and Watch thresholds of one indicator, from `monitoring/out/thresholds.json`; null = never assigned."""

    look: float | None
    watch: float | None


class RunThresholds(_SignalShape):
    discordance: TierThresholds
    rate_kri: TierThresholds
    simaerep_classic: TierThresholds


class ThresholdsFile(RunThresholds):
    """`monitoring/out/thresholds.json` (bvsignal.calibrate): the only source of tier thresholds (REQ-023)."""

    sap_tag_commit: str
    eval_seed: int
    expected_false_look_flags_per_study: float


class RunDesign(_SignalShape):
    n_sites: int
    window_weeks: int
    data_cut_date: date
    patients_per_site: list[int]


class SignalRunMeta(_SignalShape):
    """`run` of `GET /api/sites`: the committed study's metadata. Thresholds and the expected number of false
    Look flags are served from thresholds.json (docs/03 §5.1)."""

    id: Literal["sr_committed"]
    data_origin: Literal["SIMULATED"]
    sap_tag_commit: str
    eval_seed: int
    generated_at: str
    code_commit: str
    design: RunDesign
    thresholds: RunThresholds
    expected_false_look_flags_per_study: float
    phi: float | None
    tau2: float | None
    n_computed_sites: int
    study_not_computed_reason: NotComputedReason | None


class SignalRunMetaFile(SignalRunMeta):
    """`run` as written in signal_run.json. A copy of the thresholds there must agree with thresholds.json."""

    thresholds: RunThresholds | None = None  # type: ignore[assignment]
    expected_false_look_flags_per_study: float | None = None  # type: ignore[assignment]


class SiteCard(_SignalShape):
    """`Site` (docs/02): fictional site metadata. `data_origin` is MIXED on the site 101 card with live episodes."""

    site_id: str
    name: str
    region: str
    n_patients: int
    spanish_share: float
    extra_time_share: float
    call_completion: float
    is_live_site: bool
    data_origin: DataOrigin


class SiteFile(SiteCard):
    data_origin: Literal["SIMULATED"]  # type: ignore[assignment]


class RateKriComparator(_SignalShape):
    z_adj: float | None
    tier: SignalTier


class SimaerepComparator(_SignalShape):
    prob: float | None
    p_value: float | None
    tier: SignalTier


class SignalComparators(_SignalShape):
    rate_kri: RateKriComparator
    simaerep_classic: SimaerepComparator


class SiteSignalRow(_SignalShape):
    """`SiteSignalRow` (docs/02): one site of the committed run. The statistic is always SIMULATED.

    REQ-025: `not_computed` always carries a reason and no rank; a computed tier has no reason and a rank."""

    site_id: str
    n_patients: int
    n_episodes_evaluable: int
    n_pending: int
    n_paged: int
    call_completion: float
    O: int | None  # noqa: E741  (docs/02 field name: matched evaluable non-paged episodes, a count)
    E: float | None
    V: float | None
    oe_ratio: float | None
    z_raw: float | None
    z_adj: float | None
    tier: SignalTier
    not_computed_reason: NotComputedReason | None
    comparators: SignalComparators
    rank: int | None
    data_origin: Literal["SIMULATED"]

    @model_validator(mode="after")
    def _tier_has_reason(self) -> "SiteSignalRow":
        not_computed = self.tier == "not_computed"
        if not_computed != (self.not_computed_reason is not None):
            raise ValueError(f"site {self.site_id}: tier {self.tier!r} with reason {self.not_computed_reason!r}")
        if not_computed != (self.rank is None):
            raise ValueError(f"site {self.site_id}: tier {self.tier!r} with rank {self.rank!r}")
        return self


class SiteRowOut(_SignalShape):
    """One `GET /api/sites` row: the `Site` and `SiteSignalRow` fields merged, plus `open_queries`."""

    site_id: str
    name: str
    region: str
    n_patients: int
    spanish_share: float
    extra_time_share: float
    call_completion: float
    is_live_site: bool
    n_episodes_evaluable: int
    n_pending: int
    n_paged: int
    O: int | None  # noqa: E741
    E: float | None
    V: float | None
    oe_ratio: float | None
    z_raw: float | None
    z_adj: float | None
    tier: SignalTier
    not_computed_reason: NotComputedReason | None
    comparators: SignalComparators
    rank: int | None
    open_queries: int
    data_origin: Literal["SIMULATED"]


class FunnelPoint(_SignalShape):
    site_id: str
    E: float
    oe_ratio: float
    tier: SignalTier


class FunnelLimit(_SignalShape):
    E: float
    look_lower: float | None
    watch_lower: float | None


class Funnel(_SignalShape):
    points: list[FunnelPoint]
    limits: list[FunnelLimit]


class SignalRunFile(_SignalShape):
    """`monitoring/out/signal_run.json`: `{run, sites, rows, funnel}`."""

    run: SignalRunMetaFile
    sites: list[SiteFile]
    rows: list[SiteSignalRow]
    funnel: Funnel


class SignalLabels(BaseModel):
    """`data/signal_rules.json` `labels` with the `en` strings flattened (docs/03 §5.1). Keys WS4 adds pass through."""

    model_config = ConfigDict(extra="allow")
    watch: str
    look: str
    none: str
    not_computed: str
    footer: str
    footer_expected_false_look: str
    reasons: dict[str, str]
    answer_key: dict[str, str]


class SitesOut(BaseModel):
    """`GET /api/sites`: computed sites first by `rank`, then not-computed sites by `site_id`."""

    run: SignalRunMeta
    labels: SignalLabels
    funnel: Funnel
    sites: list[SiteRowOut]


class EpisodeEvidence(_SignalShape):
    """Verbatim quote in the original language. Every translation is an AI translation (REQ-026)."""

    quote: str
    quote_lang: str
    translation_en: str | None
    translation_is_ai: bool
    t_s: float | None
    source: QuoteSource
    checkin_id: str | None

    @model_validator(mode="after")
    def _translation_labeled(self) -> "EpisodeEvidence":
        if self.translation_en is not None and not self.translation_is_ai:
            raise ValueError("a translation must carry translation_is_ai: true")
        return self


class SiteEpisode(_SignalShape):
    """`Episode` (docs/02): `ep_{site}_{n}` from episodes.json (SIMULATED), or `ep_live_{checkin_id}_{term}` built
    at request time for the live site (MEASURED)."""

    episode_id: str
    site_id: str
    subject_id: str
    language: SubjectLanguage
    pace: SubjectPace
    term: str
    grade: int
    kind: Literal["new", "worsened"]
    episode_date: date
    checkin_ids: list[str]
    status: EpisodeStatus
    paged_level: Literal["urgent", "emergency"] | None
    matched_site_ae_id: str | None
    evidence: EpisodeEvidence
    data_origin: Literal["SIMULATED", "MEASURED"]

    @model_validator(mode="after")
    def _status_consistent(self) -> "SiteEpisode":
        if (self.status == "paged") != (self.paged_level is not None):
            raise ValueError(f"{self.episode_id}: status {self.status!r} with paged_level {self.paged_level!r}")
        if self.status == "matched" and self.matched_site_ae_id is None:
            raise ValueError(f"{self.episode_id}: matched without matched_site_ae_id")
        if self.status == "unmatched" and self.matched_site_ae_id is not None:
            raise ValueError(f"{self.episode_id}: unmatched with matched_site_ae_id")
        return self


class SiteAERow(_SignalShape):
    """`SiteAE` (docs/02): one row of the simulated site AE log."""

    site_ae_id: str
    site_id: str
    subject_id: str
    usubjid: str
    aeseq: int
    aeterm: str
    aetoxgr: str
    aestdtc: date
    entered_on: date
    origin: Literal["site", "between_visits"]
    symptomatic: bool
    data_origin: Literal["SIMULATED"]


class StratumCount(BaseModel):
    evaluable: int
    matched: int


class SiteStrata(BaseModel):
    """Episodes in the O/E set (evaluable and not paged: status matched or unmatched) by language and by pace."""

    language: dict[str, StratumCount]
    pace: dict[str, StratumCount]


class PagedStratum(BaseModel):
    n: int
    matched: int


class SiteDetailOut(BaseModel):
    """`GET /api/sites/{site_id}`. MEASURED live episodes come first and never enter `signal`, `strata` or
    `paged_stratum`. `queries` stays empty until the site query flow (B18)."""

    site: SiteCard
    signal: SiteSignalRow
    episodes: list[SiteEpisode]
    strata: SiteStrata | None
    paged_stratum: PagedStratum | None
    queries: list[dict[str, Any]]


class AnswerKeyEntry(_SignalShape):
    site_id: str
    label: AnswerKeyLabel
    f: float | None


class ConfusionCounts(_SignalShape):
    tp: int
    fp: int
    fn: int
    tn: int


class TierConfusion(_SignalShape):
    watch: ConfusionCounts
    look: ConfusionCounts


class AnswerKeyFile(_SignalShape):
    """`monitoring/out/answer_key.json`: the planted truth and the confusion counts `run.py` wrote (the backend
    counts nothing)."""

    data_origin: Literal["SIMULATED"] = "SIMULATED"
    answer_key: list[AnswerKeyEntry]
    confusion: dict[str, TierConfusion]


class AnswerKeyOut(BaseModel):
    run_id: Literal["sr_committed"]
    data_origin: Literal["SIMULATED"]
    answer_key: list[AnswerKeyEntry]
    confusion: dict[str, TierConfusion]


class EquityOut(BaseModel):
    """`GET /api/site-signal/equity`: `monitoring/out/equity.json` (docs/11 §14). Nested blocks pass through."""

    model_config = ConfigDict(extra="allow")
    data_origin: Literal["SIMULATED"] = "SIMULATED"
    language: dict[str, Any]
    pace: dict[str, Any]
    single_language_counterfactual: list[dict[str, Any]]
    note: str | None = None


class SiteSignalValidationOut(BaseModel):
    """`GET /api/site-signal/validation`: `validation/site_signal/summary.json` verbatim plus `data_origin`.
    Typed top-level keys from docs/11 §12.9; nested blocks pass through as dicts."""

    model_config = ConfigDict(extra="allow")
    sap_tag_commit: str
    eval_seed: int
    beacon_round: int | None
    code_commit: str
    generated_at: str
    numpy_version: str
    scipy_version: str
    data_origin: Literal["SIMULATED"] = "SIMULATED"
    design: dict[str, Any]
    null: dict[str, Any]
    power: list[dict[str, Any]]
    full_mix: dict[str, Any]
    head_to_head: dict[str, Any]
    failure_case: dict[str, Any]
    sensitivity: list[dict[str, Any]]
    eval_study: dict[str, Any]
    simaerep_fixture: dict[str, Any]
    quick_hashes: dict[str, Any]
