// Time-based check-in simulations for fixture mode. Each script is a list of
// events at call-time offsets (seconds); the fixture server applies them as the
// wall clock advances, so the live page behaves like a real call.

import type {
  Answer,
  AnswerSource,
  DraftEntry,
  EscalationLevel,
  EscalationReason,
  Evidence,
  Finding,
  Lang,
  TranscriptTurn,
} from "@/lib/types";
import { PLAN_ITEMS } from "./plan-data";
import { ROSA_TRANSCRIPT } from "./rosa-transcript";
import { dateAt } from "./base";

export type SimAnswer = Pick<Answer, "item_code" | "verbatim_quote"> &
  Partial<Pick<Answer, "term" | "attribute" | "option_code" | "numeric_value" | "unit">> & {
    turn?: number;
  };

export type SimEvent =
  | { t: number; type: "start" }
  | { t: number; type: "answer"; answer: SimAnswer; next: string | null }
  | { t: number; type: "finding"; finding: SimFinding }
  | {
      t: number;
      type: "escalate";
      level: EscalationLevel;
      red_flag_ids: string[];
      reason: EscalationReason;
      summary_en: string;
      paged: boolean;
    }
  | { t: number; type: "ack"; by: string; method: "push_button" | "phone_keypress" }
  | { t: number; type: "end"; status: "completed" | "no_answer" }
  | { t: number; type: "post_call" };

/** Finding as authored in a script; the fixture server adds id and answer_ids. */
export type SimFinding = Omit<Finding, "id" | "answer_ids">;

export interface DraftSeed {
  key: string;
  build: (ctx: { checkinId: string; patientId: string; escalationId: string | null }) => DraftEntry;
}

export interface SimScript {
  lang: Lang;
  events: SimEvent[];
  transcript: TranscriptTurn[];
  summary_en: string;
  drafts: DraftSeed[];
}

const AI_LABEL = "AI translation, verify";

function ev(
  quote: string,
  quote_lang: Lang,
  translation_en: string | null,
  t_s: number,
  turn_index: number,
  source: AnswerSource = "live_tool",
): Evidence {
  return {
    quote,
    quote_lang,
    translation_en,
    translation_label: translation_en ? AI_LABEL : null,
    t_s,
    turn_index,
    source,
  };
}

function draftBase(ctx: { checkinId: string; patientId: string }, key: string) {
  return {
    id: `dr_${ctx.checkinId.replace(/^ci_/, "")}_${key}`,
    checkin_id: ctx.checkinId,
    patient_id: ctx.patientId,
    status: "draft" as const,
    reviewed_by: null,
    reviewed_at: null,
    review_note: null,
    investigator: null,
    sae_report_id: null,
    created_at: new Date().toISOString(),
    origin: "between_visits" as const,
  };
}

// ------------------------------------------------------------------ Rosa (es)

const DIARRHEA_G3: SimFinding = {
  term: "Diarrhea",
  provisional_grade: 3,
  grade_basis: "rule",
  rule_id: "CTCAE5_DIARRHEA_G3",
  rule_text:
    "Increase of >=7 stools per day over baseline; hospitalization indicated; severe increase in ostomy output compared to baseline; limiting self care ADL",
  inputs: { stools_over_baseline: 7, stools_per_day: 8, baseline: 1 },
  red_flag_ids: ["RF_DIARRHEA_SEVERE"],
  escalation_level: "urgent",
};

export function rosaScript(firstName: string): SimScript {
  const transcript = ROSA_TRANSCRIPT.map((t) => ({
    ...t,
    text: t.text.replaceAll("Rosa", firstName),
  }));
  return {
    lang: "es",
    transcript,
    summary_en:
      "Check-in completed in Spanish at extra-time pace. Patient reported diarrhea almost all the time, 8 stools on the worst day versus a usual 1, and dizziness on standing this morning. Urgent page sent and acknowledged. Took over-the-counter loperamide yesterday. No care visits.",
    events: [
      { t: 0, type: "start" },
      { t: 9, type: "answer", answer: { item_code: "IDENTITY", option_code: "yes", verbatim_quote: "Sí, soy yo.", turn: 1 }, next: "CALL_CONSENT" },
      { t: 21.5, type: "answer", answer: { item_code: "CALL_CONSENT", option_code: "yes", verbatim_quote: "Sí, está bien.", turn: 3 }, next: "DIARRHEA_FREQ" },
      { t: 63.5, type: "answer", answer: { item_code: "DIARRHEA_FREQ", term: "Diarrhea", attribute: "frequency", option_code: "almost_always", verbatim_quote: "Casi todo el tiempo, la verdad.", turn: 7 }, next: "DIARRHEA_STOOLS_PER_DAY" },
      {
        t: 63.5,
        type: "finding",
        finding: { term: "Diarrhea", provisional_grade: null, grade_basis: "needs_clinician", rule_id: null, rule_text: null, inputs: { frequency: "almost_always" }, red_flag_ids: [], escalation_level: "none" },
      },
      { t: 89.5, type: "answer", answer: { item_code: "DIARRHEA_STOOLS_PER_DAY", term: "Diarrhea", attribute: "count", numeric_value: 8, unit: "per_day", verbatim_quote: "Como siete u ocho veces... normalmente voy una.", turn: 11 }, next: "MEDS_NEW" },
      { t: 89.5, type: "finding", finding: DIARRHEA_G3 },
      {
        t: 89.5,
        type: "escalate",
        level: "urgent",
        red_flag_ids: ["RF_DIARRHEA_SEVERE"],
        reason: "live_rule",
        summary_en: "Subject 101-007 reports 7 stools a day above baseline. Prefers Spanish, use interpreter line.",
        paged: true,
      },
      {
        t: 104.5,
        type: "finding",
        finding: { term: "Dizziness", provisional_grade: null, grade_basis: "needs_clinician", rule_id: null, rule_text: null, inputs: { dizzy_on_standing: "reported" }, red_flag_ids: ["RF_DEHYDRATION"], escalation_level: "urgent" },
      },
      {
        t: 104.5,
        type: "escalate",
        level: "urgent",
        red_flag_ids: ["RF_DEHYDRATION"],
        reason: "agent_report",
        summary_en: "",
        paged: false,
      },
      { t: 113, type: "ack", by: "RN on call", method: "push_button" },
      { t: 118.5, type: "answer", answer: { item_code: "MEDS_NEW", attribute: "yes_no", option_code: "yes", verbatim_quote: "Sí, ayer tomé Imodium de la farmacia.", turn: 17 }, next: "MEDS_DETAIL" },
      { t: 130.5, type: "answer", answer: { item_code: "MEDS_DETAIL", attribute: "free_text", verbatim_quote: "El Imodium, lo empecé ayer.", turn: 19 }, next: "CARE_VISIT" },
      { t: 142.5, type: "answer", answer: { item_code: "CARE_VISIT", attribute: "yes_no", option_code: "no", verbatim_quote: "No.", turn: 21 }, next: "ANYTHING_ELSE" },
      { t: 152.5, type: "answer", answer: { item_code: "ANYTHING_ELSE", attribute: "yes_no", option_code: "no", verbatim_quote: "No, nada más. Gracias.", turn: 23 }, next: null },
      { t: 162, type: "end", status: "completed" },
      { t: 170, type: "post_call" },
    ],
    drafts: [
      {
        key: "ae_diarrhea",
        build: (ctx) => ({
          ...draftBase(ctx, "ae_diarrhea"),
          kind: "AE",
          payload: {
            term: "Diarrhea",
            verbatim_en: "7 to 8 loose stools a day, usually 1",
            onset_date: dateAt(-2),
            ongoing: true,
            provisional_grade: 3,
            grade_basis: "rule",
            rule_id: DIARRHEA_G3.rule_id,
            rule_text: DIARRHEA_G3.rule_text,
            answers: [
              { item_code: "DIARRHEA_FREQ", option_code: "almost_always" },
              { item_code: "DIARRHEA_STOOLS_PER_DAY", numeric_value: 8 },
            ],
            escalation_id: ctx.escalationId,
          },
          evidence: [
            ev("Casi todo el tiempo, la verdad.", "es", "Almost all the time, honestly.", 55, 7),
            ev("Como siete u ocho veces... normalmente voy una.", "es", "Like seven or eight times... normally I go once.", 80, 11),
          ],
        }),
      },
      {
        key: "ae_dizziness",
        build: (ctx) => ({
          ...draftBase(ctx, "ae_dizziness"),
          kind: "AE",
          payload: {
            term: "Dizziness",
            verbatim_en: "Dizzy when standing up this morning",
            onset_date: dateAt(0),
            ongoing: true,
            provisional_grade: null,
            grade_basis: "needs_clinician",
            rule_id: null,
            rule_text: null,
            answers: [],
            escalation_id: ctx.escalationId,
          },
          evidence: [ev("Ay... y esta mañana me mareé al levantarme.", "es", "Oh... and this morning I got dizzy when I stood up.", 104, 15)],
        }),
      },
      {
        key: "cm_loperamide",
        build: (ctx) => ({
          ...draftBase(ctx, "cm_loperamide"),
          kind: "CM",
          payload: {
            medication_name: "loperamide (Imodium)",
            otc: true,
            indication_en: "diarrhea",
            start_date: dateAt(-1),
            dose_text: null,
          },
          evidence: [
            ev("El Imodium, lo empecé ayer.", "es", "The Imodium, I started it yesterday.", 130, 19),
            ev("Sí, ayer tomé Imodium de la farmacia.", "es", "Yes, yesterday I took Imodium from the pharmacy.", 118, 17, "post_call_extraction"),
          ],
        }),
      },
    ],
  };
}

// ------------------------------------------------------------------ simple EN

function itemText(code: string): string {
  return PLAN_ITEMS.find((i) => i.item_code === code)?.text.en ?? code;
}

interface EnStep {
  code: string;
  term?: string;
  attribute: string;
  option?: string;
  quote: string;
}

export function englishScript(firstName: string, withQuestion: boolean): SimScript {
  const steps: EnStep[] = [
    { code: "DIARRHEA_FREQ", term: "Diarrhea", attribute: "frequency", option: "never", quote: "Never." },
    { code: "NAUSEA_FREQ", term: "Nausea", attribute: "frequency", option: "rarely", quote: "Rarely, maybe once after dinner." },
    { code: "VOMITING_FREQ", term: "Vomiting", attribute: "frequency", option: "never", quote: "No, never." },
    { code: "FEVER_CHILLS", term: "Fever", attribute: "presence", option: "no", quote: "No fever." },
    { code: "SOB_SEV", term: "Dyspnea", attribute: "severity", option: "none", quote: "None." },
    { code: "DIZZINESS_SEV", term: "Dizziness", attribute: "severity", option: "none", quote: "None." },
    { code: "FATIGUE_SEV", term: "Fatigue", attribute: "severity", option: "mild", quote: "Mild, I get tired in the afternoon." },
    { code: "FATIGUE_REST_HELPS", term: "Fatigue", attribute: "yes_no", option: "yes", quote: "Yes, a nap helps." },
    { code: "RASH_ANY", term: "Rash maculo-papular", attribute: "presence", option: "no", quote: "No." },
    { code: "NEURO_CHANGE", term: "Confusion", attribute: "presence", option: "no", quote: "No." },
    { code: "MEDS_NEW", attribute: "yes_no", option: "no", quote: "No changes." },
    { code: "CARE_VISIT", attribute: "yes_no", option: "no", quote: "No." },
    withQuestion
      ? { code: "ANYTHING_ELSE", attribute: "yes_no", option: "yes", quote: "Should I stop my blood pressure pills?" }
      : { code: "ANYTHING_ELSE", attribute: "yes_no", option: "no", quote: "No, that's all." },
  ];

  const events: SimEvent[] = [{ t: 0, type: "start" }];
  const transcript: TranscriptTurn[] = [];
  let t = 6;
  let i = 0;
  const say = (role: "agent" | "user", text: string) => {
    transcript.push({ i: i++, role, text, t_s: t, lang: "en" });
  };
  say("agent", `[Approved first message: AI disclosure, offer of a human] May I speak with ${firstName}?`);
  t += 4;
  say("user", "Yes, this is me.");
  events.push({ t, type: "answer", answer: { item_code: "IDENTITY", option_code: "yes", verbatim_quote: "Yes, this is me.", turn: i - 1 }, next: "CALL_CONSENT" });
  t += 4;
  say("agent", "[Approved consent question]");
  t += 4;
  say("user", "Sure, go ahead.");
  events.push({ t, type: "answer", answer: { item_code: "CALL_CONSENT", option_code: "yes", verbatim_quote: "Sure, go ahead.", turn: i - 1 }, next: steps[0].code });

  steps.forEach((s, idx) => {
    t += 3;
    say("agent", s.code === "FATIGUE_REST_HELPS" ? "Does resting make the tiredness better?" : itemText(s.code));
    t += 5;
    say("user", s.quote);
    events.push({
      t,
      type: "answer",
      answer: { item_code: s.code, term: s.term ?? null, attribute: s.attribute, option_code: s.option ?? null, verbatim_quote: s.quote, turn: i - 1 },
      next: steps[idx + 1]?.code ?? null,
    });
    if (s.code === "NAUSEA_FREQ") {
      events.push({ t, type: "finding", finding: { term: "Nausea", provisional_grade: null, grade_basis: "needs_clinician", rule_id: null, rule_text: null, inputs: { frequency: "rarely" }, red_flag_ids: [], escalation_level: "none" } });
    }
    if (s.code === "FATIGUE_REST_HELPS") {
      events.push({ t, type: "finding", finding: { term: "Fatigue", provisional_grade: 1, grade_basis: "rule", rule_id: "CTCAE5_FATIGUE_G1", rule_text: "Fatigue relieved by rest", inputs: { severity: "mild", rest_helps: "yes" }, red_flag_ids: [], escalation_level: "none" } });
    }
    if (s.code === "ANYTHING_ELSE" && withQuestion) {
      t += 2;
      say("agent", "[Approved deferral line: that's a question for your nurse]");
      events.push({ t, type: "escalate", level: "callback", red_flag_ids: [], reason: "medical_question", summary_en: "Subject asked a medication question for the nurse.", paged: false });
    }
  });
  t += 3;
  say("agent", "[Approved closing line]");
  t += 3;
  events.push({ t, type: "end", status: "completed" });
  events.push({ t: t + 6, type: "post_call" });

  const quoteTurn = (q: string) => transcript.find((x) => x.text === q);
  const drafts: DraftSeed[] = [
    {
      key: "ae_fatigue",
      build: (ctx) => ({
        ...draftBase(ctx, "ae_fatigue"),
        kind: "AE",
        payload: {
          term: "Fatigue",
          verbatim_en: "Mild tiredness in the afternoon; a nap helps",
          onset_date: null,
          ongoing: true,
          provisional_grade: 1,
          grade_basis: "rule",
          rule_id: "CTCAE5_FATIGUE_G1",
          rule_text: "Fatigue relieved by rest",
          answers: [
            { item_code: "FATIGUE_SEV", option_code: "mild" },
            { item_code: "FATIGUE_REST_HELPS", option_code: "yes" },
          ],
          escalation_id: null,
        },
        evidence: ["Mild, I get tired in the afternoon.", "Yes, a nap helps."].map((q) => {
          const turn = quoteTurn(q);
          return ev(q, "en", null, turn?.t_s ?? 0, turn?.i ?? 0);
        }),
      }),
    },
    {
      key: "ae_nausea",
      build: (ctx) => {
        const q = "Rarely, maybe once after dinner.";
        const turn = quoteTurn(q);
        return {
          ...draftBase(ctx, "ae_nausea"),
          kind: "AE",
          payload: {
            term: "Nausea",
            verbatim_en: q,
            onset_date: null,
            ongoing: true,
            provisional_grade: null,
            grade_basis: "needs_clinician",
            rule_id: null,
            rule_text: null,
            answers: [{ item_code: "NAUSEA_FREQ", option_code: "rarely" }],
            escalation_id: null,
          },
          evidence: [ev(q, "en", null, turn?.t_s ?? 0, turn?.i ?? 0, "post_call_extraction")],
        };
      },
    },
  ];
  if (withQuestion) {
    drafts.push({
      key: "task_question",
      build: (ctx) => {
        const q = "Should I stop my blood pressure pills?";
        const turn = quoteTurn(q);
        return {
          ...draftBase(ctx, "task_question"),
          kind: "NURSE_TASK",
          payload: { category: "medical_question", text_en: q },
          evidence: [ev(q, "en", null, turn?.t_s ?? 0, turn?.i ?? 0)],
        };
      },
    });
  }

  return {
    lang: "en",
    events,
    transcript,
    summary_en: withQuestion
      ? "Check-in completed in English. Rare nausea and mild fatigue relieved by rest. Patient asked a medication question; nurse task created."
      : "Check-in completed in English. Rare nausea and mild fatigue relieved by rest. No red flags.",
    drafts,
  };
}

export function noAnswerScript(lang: Lang): SimScript {
  return {
    lang,
    events: [{ t: 45, type: "end", status: "no_answer" }],
    transcript: [],
    summary_en: "",
    drafts: [],
  };
}
