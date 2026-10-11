// In-memory fixture "backend" used when NEXT_PUBLIC_USE_FIXTURES=1.
// Implements the endpoints of docs/03-api-contracts.md § 1 closely enough to
// click through the whole demo (calls progress in real time, mutations stick
// until the page is reloaded).

import type { DemoIdentity } from "@/lib/role";
import type {
  Answer,
  AuditEvent,
  CheckIn,
  CheckInDetail,
  CheckInStatus,
  CreateCheckInRequest,
  CreateCheckInResponse,
  DraftEntry,
  Escalation,
  Finding,
  InvestigatorRequest,
  PatientDetail,
  PatientRef,
  PatientSummary,
  SAEReport,
  SponsorInboxItem,
  TodayRow,
} from "@/lib/types";
import {
  DAY,
  EVAL_LATEST,
  HEALTH,
  HOUR,
  MIN,
  PAST_CHECKINS,
  PATIENTS,
  SCENARIOS,
  SEED_AUDIT,
  STUDY,
  STUDY_TEAM_NAME,
  TIMELINES,
  VALIDATION,
  dateAt,
  fixtureChain,
  isoAt,
  walterSae,
  type FixturePatient,
} from "./base";
import { PLAN } from "./plan-data";
import { englishScript, noAnswerScript, rosaScript, type SimScript } from "./scripts";

/** Fixture calls run faster than real time so the demo flow is quick to click through. */
const SPEED = 2;

export interface FixtureResponse {
  status: number;
  body: unknown;
}

interface Sim {
  id: string;
  patient: FixturePatient;
  channel: CheckIn["channel"];
  dayAfterDose: number;
  createdMs: number;
  /** null until the call actually starts (web calls wait for web-started). */
  startMs: number | null;
  script: SimScript;
  applied: number;
  checkin: CheckIn;
  answers: Answer[];
  findings: Finding[];
  transcript: CheckInDetail["transcript"];
  escalationId: string | null;
}

interface Db {
  sims: Sim[];
  escalations: Escalation[];
  drafts: DraftEntry[];
  saes: SAEReport[];
  audit: AuditEvent[];
  seq: number;
}

// Initialized at the bottom of the module (after every const it depends on).
let db!: Db;

function freshDb(): Db {
  const d: Db = { sims: [], escalations: [], drafts: [], saes: [walterSae()], audit: [...SEED_AUDIT], seq: 0 };
  db = d;
  // Walter's resolved escalation + confirmed serious AE from two days ago
  d.escalations.push({
    id: "esc_walter_d1",
    checkin_id: "ci_walter_d1",
    patient_id: "pat_walter",
    level: "urgent",
    status: "resolved",
    red_flag_ids: ["RF_BREATHING"],
    reason: "live_rule",
    summary_en: "Subject 101-004 reports shortness of breath at rest. Caregiver (son) answering.",
    patient_language: "en",
    created_at: isoAt(-2 * DAY),
    paged_at: isoAt(-2 * DAY),
    seconds_open: 38,
    page_channel: "ntfy",
    page_target_name: "RN on call",
    repage_count: 0,
    backup_paged_at: null,
    red_flag_labels: redFlagLabels(["RF_BREATHING"]),
    seconds_to_ack: 38,
    acknowledged_at: isoAt(-2 * DAY + 38),
    acknowledged_by: "RN on call",
    ack_method: "push_button",
    resolved_at: isoAt(-2 * DAY + 40 * MIN),
    resolution_note: "Nurse called back; family taking him to the ED.",
    patient: patientRef(byId("pat_walter")),
  });
  d.drafts.push({
    id: "dr_walter_ae1",
    checkin_id: "ci_walter_d1",
    patient_id: "pat_walter",
    kind: "AE",
    status: "confirmed",
    payload: {
      term: "Dyspnea",
      verbatim_en: "Short of breath sitting still",
      onset_date: dateAt(-2),
      ongoing: true,
      provisional_grade: 3,
      grade_basis: "rule",
      rule_id: "CTCAE5_DYSPNEA_G3",
      rule_text: "Shortness of breath at rest; limiting self care ADL",
      answers: [{ item_code: "SOB_EXERTION", option_code: "at_rest" }],
      escalation_id: "esc_walter_d1",
    },
    evidence: [
      { quote: "He gets out of breath just sitting in his chair.", quote_lang: "en", translation_en: null, translation_label: null, t_s: 141.5, turn_index: 22, source: "live_tool" },
    ],
    reviewed_by: "Jess Kim",
    reviewed_at: isoAt(-2 * DAY + 2 * HOUR),
    review_note: null,
    investigator: { is_serious: true, seriousness_criteria: ["hospitalization"], relatedness: "possibly_related", signed_by: "Dr. Patel", signed_at: isoAt(-2 * DAY + 2.5 * HOUR) },
    sae_report_id: "sae_walter",
    created_at: isoAt(-2 * DAY + 10 * MIN),
    patient: patientRef(byId("pat_walter")),
    origin: "between_visits",
  });
  // Today: Rosa's completed urgent call, James's completed call with a question, Ana no answer
  createSim(byId("pat_rosa"), "phone", Date.now() - 32 * MIN * 1000, "ci_rosa_d3");
  createSim(byId("pat_james"), "phone", Date.now() - 95 * MIN * 1000, "ci_james_d1", true);
  createSim(byId("pat_ana"), "phone", Date.now() - 50 * MIN * 1000, "ci_ana_d7");
  tick();
  return d;
}

// ------------------------------------------------------------------ helpers

function byId(id: string): FixturePatient {
  const p = PATIENTS.find((x) => x.id === id);
  if (!p) throw new Error(`unknown fixture patient ${id}`);
  return p;
}

function redFlagLabels(ids: string[]): string[] {
  return ids.map((id) => PLAN.red_flags.find((r) => r.id === id)?.label_en ?? id);
}

function patientRef(p: FixturePatient): PatientRef {
  return {
    id: p.id,
    subject_id: p.subject_id,
    first_name: p.first_name,
    last_name: p.last_name,
    language: p.language,
    pace: p.pace,
    caregiver_name: p.caregiver_name,
  };
}

function nextId(prefix: string): string {
  db.seq += 1;
  return `${prefix}_fx${db.seq.toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

function audit(
  identity: DemoIdentity | { user: string; role: string },
  action: string,
  entity_type: string,
  entity_id: string,
  before: unknown,
  after: unknown,
  note: string | null = null,
): void {
  db.audit.unshift({
    id: nextId("aud"),
    ts: new Date().toISOString(),
    actor: identity.user,
    role: identity.role,
    action,
    entity_type,
    entity_id,
    checkin_id: entity_type === "CheckIn" ? entity_id : null,
    before: (before ?? null) as AuditEvent["before"],
    after: (after ?? null) as AuditEvent["after"],
    note,
    ...fixtureChain(Math.max(0, ...db.audit.map((a) => a.seq)) + 1),
  });
}

const SYSTEM = { user: "system", role: "system" };
const AGENT = { user: "agent", role: "agent" };

function err(status: number, code: string, message: string): FixtureResponse {
  return { status, body: { error: { code, message } } };
}

function ok(body: unknown, status = 200): FixtureResponse {
  return { status, body: structuredClone(body) };
}

// ------------------------------------------------------------------ simulation

function createSim(
  patient: FixturePatient,
  channel: CheckIn["channel"],
  createdMs: number,
  id?: string,
  withQuestion = false,
): Sim {
  const script =
    id === "ci_ana_d7"
      ? noAnswerScript(patient.language)
      : patient.language === "es"
        ? rosaScript(patient.first_name)
        : englishScript(patient.first_name, withQuestion);
  const simId = id ?? nextId("ci");
  const sim: Sim = {
    id: simId,
    patient,
    channel,
    dayAfterDose: patient.next_due?.day_after_dose ?? 1,
    createdMs,
    startMs: channel === "web" ? null : createdMs,
    script,
    applied: 0,
    checkin: {
      id: simId,
      patient_id: patient.id,
      status: "dialing",
      channel,
      language: patient.language,
      pace: patient.pace,
      agent_variant: `${patient.language}-${patient.pace}`,
      day_after_dose: patient.next_due?.day_after_dose ?? 1,
      scheduled_for: new Date(createdMs).toISOString(),
      speaker: null,
      started_at: null,
      ended_at: null,
      duration_s: null,
      termination_reason: null,
      el_conversation_id: channel === "web" ? `conv_${simId}` : null,
      summary_en: null,
      postcall_status: null,
      created_at: new Date(createdMs).toISOString(),
      interview_state: { current: "IDENTITY", asked: [], queue: [], escalated: false, closed: false },
    },
    answers: [],
    findings: [],
    transcript: [],
    escalationId: null,
  };
  db.sims.unshift(sim);
  return sim;
}

function atIso(sim: Sim, t: number): string {
  return new Date((sim.startMs ?? Date.now()) + (t * 1000) / SPEED).toISOString();
}

function tick(): void {
  const now = Date.now();
  for (const sim of db.sims) {
    if (sim.startMs === null) continue;
    if (sim.checkin.status === "cancelled") continue;
    const elapsed = ((now - sim.startMs) / 1000) * SPEED;
    const events = sim.script.events;
    while (sim.applied < events.length && events[sim.applied].t <= elapsed) {
      applyEvent(sim, events[sim.applied]);
      sim.applied += 1;
    }
  }
}

function applyEvent(sim: Sim, e: SimScript["events"][number]): void {
  const ci = sim.checkin;
  const state = ci.interview_state;
  switch (e.type) {
    case "start":
      ci.status = "in_progress";
      ci.started_at = atIso(sim, e.t);
      ci.speaker = "patient";
      return;
    case "answer": {
      const a = e.answer;
      const existing = sim.answers.findIndex((x) => x.item_code === a.item_code);
      const ans: Answer = {
        id: `ans_${sim.id}_${a.item_code.toLowerCase()}`,
        item_code: a.item_code,
        term: a.term ?? null,
        attribute: a.attribute ?? "",
        option_code: a.option_code ?? null,
        numeric_value: a.numeric_value ?? null,
        unit: a.unit ?? null,
        verbatim_quote: a.verbatim_quote,
        quote_lang: sim.script.lang,
        reporter: "patient",
        source: sim.channel === "replay" ? "replay" : "live_tool",
        t_s: null,
        created_at: atIso(sim, e.t),
      };
      if (existing >= 0) sim.answers[existing] = ans;
      else sim.answers.push(ans);
      state.asked = [...state.asked, a.item_code];
      state.current = e.next;
      ci.interview_state = state;
      audit(AGENT, "answer.recorded", "Answer", ans.id, null, { item_code: ans.item_code, option_code: ans.option_code, numeric_value: ans.numeric_value });
      return;
    }
    case "finding": {
      const idx = sim.findings.findIndex((f) => f.term === e.finding.term);
      const f: Finding = {
        ...e.finding,
        id: `fnd_${sim.id}_${e.finding.term.toLowerCase()}`,
        answer_ids: sim.answers.filter((x) => x.term === e.finding.term).map((x) => x.id),
      };
      const before = idx >= 0 ? sim.findings[idx] : null;
      if (idx >= 0) sim.findings[idx] = f;
      else sim.findings.push(f);
      audit(SYSTEM, "finding.updated", "Finding", f.id, before ? { provisional_grade: before.provisional_grade } : null, { provisional_grade: f.provisional_grade, rule_id: f.rule_id });
      return;
    }
    case "escalate": {
      const open = db.escalations.find((x) => x.checkin_id === sim.id && x.status !== "resolved" && x.level === e.level);
      if (open) {
        open.red_flag_ids = [...open.red_flag_ids, ...e.red_flag_ids];
        open.red_flag_labels = redFlagLabels(open.red_flag_ids);
        audit(SYSTEM, "escalation.flag_added", "Escalation", open.id, null, { red_flag_ids: open.red_flag_ids });
        return;
      }
      const esc: Escalation = {
        id: `esc_${sim.id.replace(/^ci_/, "")}`,
        checkin_id: sim.id,
        patient_id: sim.patient.id,
        level: e.level,
        status: "open",
        red_flag_ids: e.red_flag_ids,
        reason: e.reason,
        summary_en: e.summary_en,
        patient_language: sim.patient.language,
        created_at: atIso(sim, e.t),
        paged_at: e.paged ? atIso(sim, e.t) : null,
        seconds_open: 0,
        page_channel: e.paged ? "ntfy" : null,
        page_target_name: e.paged ? "RN on call" : null,
        repage_count: 0,
        backup_paged_at: null,
        red_flag_labels: redFlagLabels(e.red_flag_ids),
        seconds_to_ack: null,
        acknowledged_at: null,
        acknowledged_by: null,
        ack_method: null,
        resolved_at: null,
        resolution_note: null,
        patient: patientRef(sim.patient),
      };
      db.escalations.unshift(esc);
      sim.escalationId = esc.id;
      if (e.level !== "callback") state.escalated = true;
      ci.interview_state = state;
      audit(SYSTEM, e.paged ? "escalation.paged" : "escalation.created", "Escalation", esc.id, null, { level: esc.level, red_flag_ids: esc.red_flag_ids });
      return;
    }
    case "ack": {
      const esc = db.escalations.find((x) => x.id === sim.escalationId);
      if (esc && esc.status === "open") {
        esc.status = "acknowledged";
        esc.acknowledged_at = atIso(sim, e.t);
        esc.acknowledged_by = e.by;
        esc.ack_method = e.method;
        audit({ user: e.by, role: "nurse" }, "escalation.acknowledged", "Escalation", esc.id, { status: "open" }, { status: "acknowledged", ack_method: e.method });
      }
      return;
    }
    case "end":
      ci.status = e.status;
      ci.ended_at = atIso(sim, e.t);
      ci.duration_s = e.status === "completed" ? Math.round(e.t) : null;
      ci.termination_reason = e.status === "completed" ? "end_call tool was called." : "no-answer";
      if (e.status === "completed") ci.postcall_status = "processing";
      state.closed = true;
      ci.interview_state = state;
      audit(SYSTEM, `checkin.${e.status}`, "CheckIn", sim.id, null, { status: e.status });
      return;
    case "post_call": {
      sim.transcript = sim.script.transcript;
      ci.summary_en = sim.script.summary_en;
      ci.postcall_status = "done";
      for (const a of sim.answers) {
        const turn = sim.transcript.find((t) => t.role === "user" && t.text === a.verbatim_quote);
        if (turn) a.t_s = turn.t_s ?? null;
      }
      for (const seed of sim.script.drafts) {
        const draft = seed.build({ checkinId: sim.id, patientId: sim.patient.id, escalationId: sim.escalationId });
        draft.created_at = atIso(sim, e.t);
        draft.patient = patientRef(sim.patient);
        db.drafts.unshift(draft);
        audit(SYSTEM, "draft.created", "DraftEntry", draft.id, null, { kind: draft.kind, status: "draft" });
      }
      return;
    }
  }
}

function secondsOpen(esc: Escalation): number {
  const start = Date.parse(esc.paged_at ?? esc.created_at ?? new Date().toISOString());
  const end = esc.acknowledged_at ? Date.parse(esc.acknowledged_at) : Date.now();
  return Math.max(0, Math.round((end - start) / 1000));
}

function withSecondsOpen(esc: Escalation): Escalation {
  const s = secondsOpen(esc);
  return { ...esc, seconds_open: s, seconds_to_ack: esc.acknowledged_at ? s : null };
}

function simDetail(sim: Sim): CheckInDetail {
  return {
    checkin: sim.checkin,
    patient: patientRef(sim.patient),
    answers: sim.answers,
    findings: sim.findings,
    escalations: db.escalations.filter((e) => e.checkin_id === sim.id).map(withSecondsOpen),
    drafts: db.drafts.filter((d) => d.checkin_id === sim.id),
    transcript: sim.transcript,
    current_question:
      LIVE_STATUSES.includes(sim.checkin.status) && sim.checkin.interview_state.current
        ? (PLAN.items.find((i) => i.item_code === sim.checkin.interview_state.current)?.text[sim.script.lang] ?? null)
        : null,
  };
}

const LIVE_STATUSES: CheckInStatus[] = ["dialing", "in_progress"];

function patientSummary(p: FixturePatient): PatientSummary {
  const latest = db.sims.find((s) => s.patient.id === p.id);
  const pastLatest = PAST_CHECKINS[p.id]?.[0];
  return {
    id: p.id,
    subject_id: p.subject_id,
    first_name: p.first_name,
    last_name: p.last_name,
    age: p.age,
    language: p.language,
    pace: p.pace,
    hearing: p.hearing,
    caregiver_name: p.caregiver_name,
    caregiver_relation: p.caregiver_relation,
    next_due: p.next_due,
    last_checkin_status: latest?.checkin.status ?? pastLatest?.status ?? null,
    sex: p.sex,
    caregiver_may_answer: p.caregiver_may_answer,
    open_escalations: db.escalations.filter((e) => e.patient_id === p.id && e.status === "open").length,
  };
}

function patientDetail(p: FixturePatient): PatientDetail {
  return {
    ...patientSummary(p),
    phone_on_file: false,
    baseline: p.baseline,
    notes: p.notes,
    dose_dates: p.dose_offsets_days.map((d) => dateAt(d)),
    checkins: [...db.sims.filter((s) => s.patient.id === p.id).map((s) => s.checkin), ...(PAST_CHECKINS[p.id] ?? [])],
    timeline: TIMELINES[p.id] ?? [],
  };
}

function todayRows(): TodayRow[] {
  const today = dateAt(0);
  return PATIENTS.filter((p) => p.next_due?.date === today).map((p) => {
    const sim = db.sims.find((s) => s.patient.id === p.id);
    const patient = patientSummary(p);
    return {
      id: sim?.id ?? null,
      status: sim?.checkin.status ?? ("due" as const),
      channel: sim?.channel ?? null,
      day_after_dose: sim?.dayAfterDose ?? p.next_due?.day_after_dose ?? 1,
      started_at: sim?.checkin.started_at ?? null,
      patient,
      open_escalations: patient.open_escalations,
    };
  });
}


function saeView(s: SAEReport): SAEReport {
  const end = s.sponsor_received_at ? Date.parse(s.sponsor_received_at) : Date.now();
  return { ...s, seconds_until_due: Math.round((Date.parse(s.due_at) - end) / 1000) };
}

function inboxItem(s: SAEReport): SponsorInboxItem {
  const draft = db.drafts.find((d) => d.id === s.draft_entry_id);
  return {
    sae_id: s.id,
    received_at: s.sponsor_received_at ?? "",
    due_at: s.due_at,
    on_time: !!s.sponsor_received_at && Date.parse(s.sponsor_received_at) <= Date.parse(s.due_at),
    study: s.payload.study.nct_id,
    site: s.payload.study.site_id,
    subject_id: s.payload.patient.subject_id,
    event_term: s.payload.reaction.term,
    seriousness_criteria: s.payload.seriousness,
    provisional_grade: s.payload.reaction.provisional_ctcae_grade,
    relatedness: s.payload.causality.result ?? draft?.investigator?.relatedness ?? null,
    valid_case_checks: {
      identifiable_patient: !!s.payload.patient.subject_id,
      identifiable_reporter: !!s.payload.reporter.name,
      suspect_product: !!s.payload.suspect_product.description,
      adverse_event: !!s.payload.reaction.term,
    },
    narrative: s.narrative_final ?? s.narrative_ai_draft,
    seconds_before_deadline: s.sponsor_received_at ? Math.round((Date.parse(s.due_at) - Date.parse(s.sponsor_received_at)) / 1000) : 0,
    report: { ...s.payload },
  };
}

function createSae(draft: DraftEntry & { kind: "AE" }, identity: DemoIdentity, req: InvestigatorRequest): SAEReport {
  const p = byId(draft.patient_id);
  const esc = db.escalations.find((e) => e.id === draft.payload.escalation_id);
  const aware = esc?.acknowledged_at ?? draft.reviewed_at ?? new Date().toISOString();
  const due = new Date(Date.parse(aware) + DAY * 1000).toISOString();
  const cms = db.drafts.filter((d) => d.checkin_id === draft.checkin_id && d.kind === "CM");
  const lastDose = p.dose_offsets_days.length ? dateAt(Math.max(...p.dose_offsets_days)) : null;
  const narrative = `Subject ${p.subject_id}, a ${p.age}-year-old ${p.sex === "F" ? "woman" : "man"} receiving the study drug (anti-PD-1 monoclonal antibody), reported ${draft.payload.verbatim_en.toLowerCase()} during a scheduled automated check-in ${draft.payload.onset_date ? `(onset ${draft.payload.onset_date})` : ""}, ${p.next_due?.day_after_dose ?? 3} days after the most recent dose. Provisional CTCAE v5.0 grade ${draft.payload.provisional_grade ?? "not assigned"} (rule-based, clinician to confirm). The on-call nurse was paged and acknowledged. Seriousness: ${req.seriousness_criteria.join(", ").replaceAll("_", " ") || "none"}. ${cms.length ? `Concomitant: ${cms.map((c) => (c.kind === "CM" ? c.payload.medication_name : "")).join(", ")}.` : ""} Outcome: not recovered at time of report.`;
  const sae: SAEReport = {
    id: nextId("sae"),
    draft_entry_id: draft.id,
    patient_id: p.id,
    checkin_id: draft.checkin_id,
    status: "draft",
    aware_at: aware,
    due_at: due,
    seconds_until_due: 0,
    payload: {
      report_type: "initial",
      date_of_report: dateAt(0),
      study: { nct_id: STUDY.nct_id, site_id: STUDY.site_id, sponsor_study_number: "R2810-ONC-1540" },
      patient: { subject_id: p.subject_id, initials: `${p.first_name[0]}.${p.last_name[0]}.`, age: p.age, sex: p.sex, country: "US" },
      reaction: {
        term: draft.payload.term,
        onset_date: draft.payload.onset_date,
        provisional_ctcae_grade: draft.payload.provisional_grade,
        ctcae_version: "5.0",
        description: draft.payload.verbatim_en,
        outcome: "not_recovered",
      },
      seriousness: req.seriousness_criteria,
      suspect_product: { description: "Study drug (anti-PD-1 monoclonal antibody)", route: "intravenous", last_dose_date: lastDose },
      concomitant: cms.flatMap((c) => (c.kind === "CM" ? [{ medication: c.payload.medication_name, start_date: c.payload.start_date, otc: c.payload.otc }] : [])),
      causality: { assessed_by: `${identity.user} (investigator)`, result: req.relatedness },
      reporter: { name: identity.user, role: "investigator", site: STUDY.site_name },
      aware_at: aware,
      due_at: due,
      narrative_ai_draft_used: true,
    },
    narrative_ai_draft: narrative.replace(/\s+/g, " ").trim(),
    narrative_final: null,
    signed_by: null,
    signed_at: null,
    sent_at: null,
    sponsor_received_at: null,
    created_at: new Date().toISOString(),
    patient: patientRef(p),
  };
  db.saes.unshift(sae);
  audit(SYSTEM, "sae.created", "SAEReport", sae.id, null, { due_at: due });
  return sae;
}

// ------------------------------------------------------------------ router

type Handler = (
  m: RegExpMatchArray,
  q: URLSearchParams,
  body: unknown,
  identity: DemoIdentity,
) => FixtureResponse;

const routes: { method: string; re: RegExp; h: Handler }[] = [];
function route(method: string, pattern: string, h: Handler): void {
  routes.push({ method, re: new RegExp(`^${pattern}$`), h });
}

function obj(body: unknown): Record<string, unknown> {
  return body && typeof body === "object" ? (body as Record<string, unknown>) : {};
}

route("GET", "/api/health", () => ok({ ...HEALTH, demo_mode: false }));
route("GET", "/api/study", () => ok(STUDY));
route("GET", "/api/plan/active", () => ok(PLAN));
route("GET", "/api/patients", () => ok(PATIENTS.map(patientSummary)));
route("GET", "/api/patients/([^/]+)", (m) => {
  const p = PATIENTS.find((x) => x.id === m[1]);
  return p ? ok(patientDetail(p)) : err(404, "patient_not_found", "Patient not found");
});
route("GET", "/api/checkins", (_m, q) => {
  const date = q.get("date") ?? dateAt(0);
  return ok(date === dateAt(0) ? todayRows() : []);
});
route("POST", "/api/patients/([^/]+)/checkins", (m, _q, body, identity) => {
  const p = PATIENTS.find((x) => x.id === m[1]);
  if (!p) return err(404, "patient_not_found", "Patient not found");
  const live = db.sims.find((s) => s.patient.id === p.id && ["dialing", "in_progress"].includes(s.checkin.status));
  if (live) return err(409, "checkin_in_progress", `${p.subject_id} already has a live check-in.`);
  const req = obj(body) as Partial<CreateCheckInRequest>;
  const channel = req.channel === "web" ? "web" : "phone";
  const sim = createSim(p, channel, Date.now());
  if (req.day_after_dose) sim.dayAfterDose = req.day_after_dose;
  audit(identity, "checkin.created", "CheckIn", sim.id, null, { channel });
  const res: CreateCheckInResponse = { checkin: structuredClone(sim.checkin), web_session: null };
  if (channel === "web") {
    res.web_session = {
      agent_id: `agent_${p.language}_${p.pace}_fixture`,
      conversation_token: "fixture-token",
      conversation_id: `conv_${sim.id}`,
      dynamic_variables: {
        checkin_id: sim.id,
        patient_first_name: p.first_name,
        study_team_name: STUDY_TEAM_NAME[p.language],
        language_name: p.language === "es" ? "Spanish" : "English",
        pace_instructions: p.pace === "extra_time" ? "extra time" : "standard",
        caregiver_name: p.caregiver_name ?? "",
      },
      user_id: p.subject_id,
    };
  }
  return ok(res, 201);
});
route("POST", "/api/checkins/([^/]+)/web-started", (m) => {
  const sim = db.sims.find((s) => s.id === m[1]);
  if (!sim) return err(404, "checkin_not_found", "Check-in not found");
  if (sim.startMs === null) sim.startMs = Date.now();
  return ok({ ok: true });
});
route("POST", "/api/checkins/([^/]+)/cancel", (m, _q, _b, identity) => {
  const sim = db.sims.find((s) => s.id === m[1]);
  if (!sim) return err(404, "checkin_not_found", "Check-in not found");
  const before = sim.checkin.status;
  sim.checkin.status = "cancelled";
  audit(identity, "checkin.cancelled", "CheckIn", sim.id, { status: before }, { status: "cancelled" });
  return ok(sim.checkin);
});
route("GET", "/api/checkins/([^/]+)", (m) => {
  const sim = db.sims.find((s) => s.id === m[1]);
  if (sim) return ok(simDetail(sim));
  // older check-ins (patient history) have no answers/transcript in fixtures
  for (const [pid, list] of Object.entries(PAST_CHECKINS)) {
    const c = list.find((x) => x.id === m[1]);
    if (c) {
      const detail: CheckInDetail = {
        checkin: { ...c, summary_en: "Earlier check-in (fixture data: details not loaded)." },
        patient: patientRef(byId(pid)),
        answers: [],
        findings: [],
        escalations: db.escalations.filter((e) => e.checkin_id === c.id).map(withSecondsOpen),
        drafts: db.drafts.filter((d) => d.checkin_id === c.id),
        transcript: [],
        current_question: null,
      };
      return ok(detail);
    }
  }
  return err(404, "checkin_not_found", "Check-in not found");
});

route("GET", "/api/escalations", (_m, q) => {
  const status = q.get("status");
  const ci = q.get("checkin_id");
  return ok(db.escalations.filter((e) => (!status || e.status === status) && (!ci || e.checkin_id === ci)).map(withSecondsOpen));
});
route("POST", "/api/escalations/([^/]+)/ack", (m, _q, _b, identity) => {
  const e = db.escalations.find((x) => x.id === m[1]);
  if (!e) return err(404, "escalation_not_found", "Escalation not found");
  if (e.status === "open") {
    e.status = "acknowledged";
    e.acknowledged_at = new Date().toISOString();
    e.acknowledged_by = identity.user;
    e.ack_method = "dashboard";
    audit(identity, "escalation.acknowledged", "Escalation", e.id, { status: "open" }, { status: "acknowledged", ack_method: "dashboard" });
  }
  return ok(withSecondsOpen(e));
});
route("POST", "/api/escalations/([^/]+)/resolve", (m, _q, body, identity) => {
  const e = db.escalations.find((x) => x.id === m[1]);
  if (!e) return err(404, "escalation_not_found", "Escalation not found");
  const note = String(obj(body).note ?? "");
  const before = e.status;
  if (!e.acknowledged_at) {
    e.acknowledged_at = new Date().toISOString();
    e.acknowledged_by = identity.user;
    e.ack_method = "dashboard";
  }
  e.status = "resolved";
  e.resolved_at = new Date().toISOString();
  e.resolution_note = note || null;
  audit(identity, "escalation.resolved", "Escalation", e.id, { status: before }, { status: "resolved" }, note || null);
  return ok(withSecondsOpen(e));
});

route("GET", "/api/drafts", (_m, q) => {
  const status = q.get("status");
  const kind = q.get("kind");
  const ci = q.get("checkin_id");
  const pid = q.get("patient_id");
  return ok(
    db.drafts.filter(
      (d) => (!status || d.status === status) && (!kind || d.kind === kind) && (!ci || d.checkin_id === ci) && (!pid || d.patient_id === pid),
    ),
  );
});
route("PATCH", "/api/drafts/([^/]+)", (m, _q, body, identity) => {
  const d = db.drafts.find((x) => x.id === m[1]);
  if (!d) return err(404, "draft_not_found", "Draft not found");
  if (d.status !== "draft") return err(409, "not_editable", "Only drafts can be edited.");
  const b = obj(body);
  const before = structuredClone(d.payload);
  Object.assign(d.payload, obj(b.payload));
  audit(identity, "draft.edited", "DraftEntry", d.id, before, d.payload, typeof b.note === "string" ? b.note : null);
  return ok(d);
});
route("POST", "/api/drafts/([^/]+)/confirm", (m, _q, body, identity) => {
  const d = db.drafts.find((x) => x.id === m[1]);
  if (!d) return err(404, "draft_not_found", "Draft not found");
  if (d.status !== "draft") return err(409, "not_draft", "Draft was already reviewed.");
  d.status = "confirmed";
  d.reviewed_by = identity.user;
  d.reviewed_at = new Date().toISOString();
  const note = obj(body).note;
  d.review_note = typeof note === "string" ? note : null;
  audit(identity, "draft.confirmed", "DraftEntry", d.id, { status: "draft" }, { status: "confirmed" });
  return ok(d);
});
route("POST", "/api/drafts/([^/]+)/reject", (m, _q, body, identity) => {
  const d = db.drafts.find((x) => x.id === m[1]);
  if (!d) return err(404, "draft_not_found", "Draft not found");
  const reason = obj(body).reason;
  if (typeof reason !== "string" || !reason.trim()) return err(422, "reason_required", "A reason is required to reject a draft.");
  d.status = "rejected";
  d.reviewed_by = identity.user;
  d.reviewed_at = new Date().toISOString();
  d.review_note = reason;
  audit(identity, "draft.rejected", "DraftEntry", d.id, { status: "draft" }, { status: "rejected" }, reason);
  return ok(d);
});
route("POST", "/api/drafts/([^/]+)/investigator", (m, _q, body, identity) => {
  if (identity.role !== "investigator") return err(403, "wrong_role", "Only the investigator can assess seriousness and sign.");
  const d = db.drafts.find((x) => x.id === m[1]);
  if (!d) return err(404, "draft_not_found", "Draft not found");
  if (d.kind !== "AE" || d.status !== "confirmed") return err(409, "not_confirmed_ae", "Draft must be a confirmed AE.");
  const req = obj(body) as unknown as InvestigatorRequest;
  const before = d.investigator ?? null;
  d.investigator = {
    is_serious: !!req.is_serious,
    seriousness_criteria: req.seriousness_criteria ?? [],
    relatedness: req.relatedness ?? null,
    signed_by: req.sign ? identity.user : null,
    signed_at: req.sign ? new Date().toISOString() : null,
  };
  audit(identity, "draft.investigator_signed", "DraftEntry", d.id, before, d.investigator);
  let sae: SAEReport | undefined;
  if (req.is_serious && !d.sae_report_id) {
    sae = createSae(d, identity, req);
    d.sae_report_id = sae.id;
  }
  return ok({ draft: d, ...(sae ? { sae_report: { id: sae.id, status: sae.status, aware_at: sae.aware_at, due_at: sae.due_at } } : {}) });
});

route("GET", "/api/sae", () => ok(db.saes.map(saeView)));
route("GET", "/api/sae/([^/]+)", (m) => {
  const s = db.saes.find((x) => x.id === m[1]);
  return s ? ok(saeView(s)) : err(404, "sae_not_found", "Report not found");
});
route("PATCH", "/api/sae/([^/]+)", (m, _q, body, identity) => {
  if (identity.role !== "investigator") return err(403, "wrong_role", "Only the investigator can edit the report.");
  const s = db.saes.find((x) => x.id === m[1]);
  if (!s) return err(404, "sae_not_found", "Report not found");
  if (s.status === "sent") return err(409, "already_sent", "Report was already sent.");
  const b = obj(body);
  const before = { narrative_final: s.narrative_final };
  if (typeof b.narrative_final === "string") s.narrative_final = b.narrative_final;
  if (b.payload && typeof b.payload === "object") Object.assign(s.payload, b.payload);
  audit(identity, "sae.edited", "SAEReport", s.id, before, { narrative_final: s.narrative_final });
  return ok(saeView(s));
});
route("POST", "/api/sae/([^/]+)/sign", (m, _q, _b, identity) => {
  if (identity.role !== "investigator") return err(403, "wrong_role", "Only the investigator can sign.");
  const s = db.saes.find((x) => x.id === m[1]);
  if (!s) return err(404, "sae_not_found", "Report not found");
  s.status = "signed";
  s.signed_by = identity.user;
  s.signed_at = new Date().toISOString();
  if (!s.narrative_final) s.narrative_final = s.narrative_ai_draft;
  audit(identity, "sae.signed", "SAEReport", s.id, { status: "draft" }, { status: "signed" });
  return ok(saeView(s));
});
route("POST", "/api/sae/([^/]+)/send", (m, _q, _b, identity) => {
  const s = db.saes.find((x) => x.id === m[1]);
  if (!s) return err(404, "sae_not_found", "Report not found");
  if (s.status !== "signed") return err(409, "not_signed", "The investigator must sign before sending.");
  const now = new Date().toISOString();
  s.status = "sent";
  s.sent_at = now;
  s.sponsor_received_at = now;
  s.payload.narrative = s.narrative_final ?? s.narrative_ai_draft;
  audit(identity, "sae.sent", "SAEReport", s.id, { status: "signed" }, { status: "sent" });
  return ok(saeView(s));
});
route("GET", "/api/sponsor/inbox", () => ok(db.saes.filter((s) => s.status === "sent").map(inboxItem)));

route("GET", "/api/audit", (_m, q) => {
  const entity = q.get("entity_id");
  const limit = Number(q.get("limit") ?? 200);
  return ok(db.audit.filter((a) => !entity || a.entity_id === entity).slice(0, limit));
});
route("GET", "/api/eval/latest", () => ok(EVAL_LATEST));
route("GET", "/api/validation/latest", () => ok(VALIDATION));

route("GET", "/api/demo/scenarios", () => ok(SCENARIOS));
route("POST", "/api/demo/replay/([^/]+)", (m, _q, _b, identity) => {
  if (m[1] !== "rosa_es_urgent") return err(404, "scenario_not_found", "Scenario not found");
  const p = byId("pat_rosa");
  const live = db.sims.find((s) => s.patient.id === p.id && ["dialing", "in_progress"].includes(s.checkin.status));
  if (live) return err(409, "checkin_in_progress", `${p.subject_id} already has a live check-in.`);
  const sim = createSim(p, "replay", Date.now());
  audit(identity, "demo.replay_started", "CheckIn", sim.id, null, { scenario: m[1] });
  return ok({ checkin_id: sim.id });
});
route("POST", "/api/demo/reset", () => {
  freshDb();
  return ok({ ok: true });
});

freshDb();

export function handleFixture(method: string, path: string, body: unknown, identity: DemoIdentity): FixtureResponse {
  tick();
  const url = new URL(path, "http://fixture.local");
  for (const r of routes) {
    if (r.method !== method) continue;
    const m = url.pathname.match(r.re);
    if (m) {
      try {
        return r.h(m, url.searchParams, body, identity);
      } catch (e) {
        return err(500, "fixture_error", e instanceof Error ? e.message : "Fixture error");
      }
    }
  }
  return err(404, "not_found", `No fixture for ${method} ${url.pathname}`);
}
