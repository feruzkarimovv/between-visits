// Short UI labels for enum codes. These are navigation labels for staff, not
// clinical wording: the questions themselves always come from data/ via the API.

import type {
  AckMethod,
  AnswerSource,
  Channel,
  EscalationReason,
  Relatedness,
  SeriousnessCriterion,
} from "./types";
import { humanize } from "./format";

const ITEM_LABELS: Record<string, string> = {
  IDENTITY: "Identity check",
  CALL_CONSENT: "Consent to the call",
  DIARRHEA_FREQ: "Diarrhea · how often",
  DIARRHEA_STOOLS_PER_DAY: "Diarrhea · stools on worst day",
  DIARRHEA_BASELINE: "Diarrhea · usual stools per day",
  STOOL_BLOOD: "Diarrhea · blood or black stool",
  NAUSEA_FREQ: "Nausea · how often",
  VOMITING_FREQ: "Vomiting · how often",
  FLUIDS_KEPT_DOWN: "Vomiting · keeps liquids down",
  FEVER_CHILLS: "Fever or chills",
  TEMP_HIGHEST: "Fever · highest temperature",
  SOB_SEV: "Shortness of breath · severity",
  SOB_EXERTION: "Shortness of breath · when",
  DIZZINESS_SEV: "Dizziness · severity",
  DIZZY_ON_STANDING: "Dizziness · on standing",
  FATIGUE_SEV: "Fatigue · severity",
  FATIGUE_REST_HELPS: "Fatigue · rest helps",
  RASH_ANY: "New rash",
  SKIN_BLISTER: "Rash · blistering or mouth sores",
  NEURO_CHANGE: "Confusion or sleepiness",
  MEDS_NEW: "Medication changes",
  MEDS_DETAIL: "Medication details",
  CARE_VISIT: "ER, urgent care or other doctor",
  CARE_VISIT_DETAIL: "Care visit details",
  ANYTHING_ELSE: "Anything else for the nurse",
};

export function itemLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return ITEM_LABELS[code] ?? humanize(code);
}

const UNIT_LABELS: Record<string, string> = {
  per_day: "per day",
  celsius: "°C",
  fahrenheit: "°F",
};

export function valueLabel(a: {
  option_code?: string | null;
  numeric_value?: number | null;
  unit?: string | null;
}): string {
  if (a.numeric_value !== null && a.numeric_value !== undefined) {
    const unit = a.unit ? UNIT_LABELS[a.unit] ?? a.unit : "";
    return `${a.numeric_value}${unit.startsWith("°") ? "" : " "}${unit}`.trim();
  }
  if (a.option_code) return humanize(a.option_code);
  return "Free text";
}

export const SERIOUSNESS_LABELS: Record<SeriousnessCriterion, string> = {
  death: "Results in death",
  life_threatening: "Life-threatening",
  hospitalization: "Requires or prolongs hospitalization",
  disability: "Persistent or significant disability",
  congenital_anomaly: "Congenital anomaly / birth defect",
  important_medical_event: "Important medical event",
};

export const SERIOUSNESS_ORDER: SeriousnessCriterion[] = [
  "death",
  "life_threatening",
  "hospitalization",
  "disability",
  "congenital_anomaly",
  "important_medical_event",
];

export const RELATEDNESS_LABELS: Record<Relatedness, string> = {
  not_related: "Not related",
  unlikely_related: "Unlikely related",
  possibly_related: "Possibly related",
  probably_related: "Probably related",
  related: "Related",
};

export const RELATEDNESS_ORDER: Relatedness[] = [
  "not_related",
  "unlikely_related",
  "possibly_related",
  "probably_related",
  "related",
];

export const ACK_METHOD_LABELS: Record<AckMethod, string> = {
  push_button: "push button",
  phone_keypress: "phone keypress",
  dashboard: "dashboard",
};

export const REASON_LABELS: Record<EscalationReason, string> = {
  live_rule: "Rule fired during call",
  agent_report: "Reported during call",
  post_call_safety_net: "Found after the call",
  patient_request: "Patient asked for a person",
  medical_question: "Medical question",
  care_visit: "ER, urgent care or other doctor visit",
};

export const NURSE_TASK_LABELS: Record<string, string> = {
  medical_question: "Medical question for the nurse",
  wants_person: "Asked for a person",
  distress: "Distress",
  other: "Other",
  care_visit: "Care visit to follow up",
  anything_else: "Something else for the nurse",
};

export const CHANNEL_LABELS: Record<Channel, string> = {
  phone: "Phone (outbound)",
  phone_inbound: "Phone (call-in)",
  web: "Browser call",
  replay: "Replay",
};

export const SOURCE_LABELS: Record<AnswerSource, string> = {
  live_tool: "Recorded during the call",
  post_call_extraction: "Found after the call",
  replay: "Replay",
};

export const PAGE_CHANNEL_LABELS: Record<string, string> = {
  ntfy: "push",
  twilio_voice: "phone call",
  console: "console (demo)",
};
