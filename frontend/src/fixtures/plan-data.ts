// Snapshot of GET /api/plan/active (built by the backend from data/plan.json,
// data/symptom_items.json and data/red_flags.json). Fixture mode only.
import type { Plan } from "@/lib/types";

export const PLAN: Plan = {
  "id": "plan_v1",
  "version": 1,
  "status": "approved",
  "approved_by": "Jess Kim (research coordinator, demo)",
  "approved_at": "2026-10-10T20:00:00Z",
  "schedule_days_after_dose": [
    1,
    3,
    7
  ],
  "items": [
    {
      "item_code": "DIARRHEA_FREQ",
      "term": "Diarrhea",
      "attribute": "frequency",
      "kind": "symptom",
      "text": {
        "en": "In the past 7 days, how often have you had loose or watery bowel movements?",
        "es": "En los últimos 7 días, ¿con qué frecuencia ha tenido diarrea, es decir, evacuaciones sueltas o aguadas?"
      },
      "options_say": {
        "en": "Would you say never, rarely, sometimes, often, or almost all the time?",
        "es": "¿Diría que nunca, rara vez, a veces, a menudo o casi todo el tiempo?"
      },
      "source": "study_team",
      "followups": [
        "DIARRHEA_STOOLS_PER_DAY",
        "DIARRHEA_BASELINE",
        "STOOL_BLOOD"
      ]
    },
    {
      "item_code": "DIARRHEA_STOOLS_PER_DAY",
      "term": "Diarrhea",
      "attribute": "count",
      "kind": "followup",
      "text": {
        "en": "On your worst day, about how many bowel movements did you have?",
        "es": "En su peor día, ¿cuántas veces fue al baño a evacuar, más o menos?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": []
    },
    {
      "item_code": "DIARRHEA_BASELINE",
      "term": "Diarrhea",
      "attribute": "count",
      "kind": "followup",
      "text": {
        "en": "Before your study treatment, how many bowel movements did you usually have in a day?",
        "es": "Antes de su tratamiento del estudio, ¿cuántas veces al día solía evacuar?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": []
    },
    {
      "item_code": "STOOL_BLOOD",
      "term": "Diarrhea",
      "attribute": "yes_no",
      "kind": "followup",
      "text": {
        "en": "Have you seen any blood or mucus in your stool, or stool that looks black like tar?",
        "es": "¿Ha visto sangre o mucosidad en sus heces, o heces negras como el alquitrán?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": []
    },
    {
      "item_code": "NAUSEA_FREQ",
      "term": "Nausea",
      "attribute": "frequency",
      "kind": "symptom",
      "text": {
        "en": "In the past 7 days, how often have you felt sick to your stomach, as if you might throw up?",
        "es": "En los últimos 7 días, ¿con qué frecuencia ha tenido náuseas, como si fuera a vomitar?"
      },
      "options_say": {
        "en": "Would you say never, rarely, sometimes, often, or almost all the time?",
        "es": "¿Diría que nunca, rara vez, a veces, a menudo o casi todo el tiempo?"
      },
      "source": "study_team",
      "followups": []
    },
    {
      "item_code": "VOMITING_FREQ",
      "term": "Vomiting",
      "attribute": "frequency",
      "kind": "symptom",
      "text": {
        "en": "In the past 7 days, how often have you thrown up?",
        "es": "En los últimos 7 días, ¿con qué frecuencia ha vomitado?"
      },
      "options_say": {
        "en": "Would you say never, rarely, sometimes, often, or almost all the time?",
        "es": "¿Diría que nunca, rara vez, a veces, a menudo o casi todo el tiempo?"
      },
      "source": "study_team",
      "followups": [
        "FLUIDS_KEPT_DOWN"
      ]
    },
    {
      "item_code": "FLUIDS_KEPT_DOWN",
      "term": "Vomiting",
      "attribute": "yes_no",
      "kind": "followup",
      "text": {
        "en": "In the last 24 hours, have you been able to keep liquids down?",
        "es": "En las últimas 24 horas, ¿ha podido tomar líquidos sin vomitarlos?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": []
    },
    {
      "item_code": "FEVER_CHILLS",
      "term": "Fever",
      "attribute": "yes_no",
      "kind": "symptom",
      "text": {
        "en": "In the past 7 days, have you had a fever, chills, or shaking?",
        "es": "En los últimos 7 días, ¿ha tenido fiebre, escalofríos o temblores?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": [
        "TEMP_HIGHEST"
      ]
    },
    {
      "item_code": "TEMP_HIGHEST",
      "term": "Fever",
      "attribute": "temperature",
      "kind": "followup",
      "text": {
        "en": "Did you take your temperature? If you did, what was the highest reading?",
        "es": "¿Se tomó la temperatura? Si lo hizo, ¿cuál fue la más alta?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": []
    },
    {
      "item_code": "SOB_SEV",
      "term": "Dyspnea",
      "attribute": "severity",
      "kind": "symptom",
      "text": {
        "en": "In the past 7 days, how much shortness of breath have you had?",
        "es": "En los últimos 7 días, ¿qué tanta falta de aire ha tenido?"
      },
      "options_say": {
        "en": "Would you say none, mild, moderate, severe, or very severe?",
        "es": "¿Diría que nada, leve, moderada, fuerte o muy fuerte?"
      },
      "source": "study_team",
      "followups": [
        "SOB_EXERTION"
      ]
    },
    {
      "item_code": "SOB_EXERTION",
      "term": "Dyspnea",
      "attribute": "severity",
      "kind": "followup",
      "text": {
        "en": "When does it happen? Only with hard activity like climbing stairs, also with light activity like walking around the house or getting dressed, or even when you are resting?",
        "es": "¿Cuándo le pasa? ¿Solo con actividad fuerte, como subir escaleras; también con actividad ligera, como caminar por la casa o vestirse; o incluso cuando está descansando?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": []
    },
    {
      "item_code": "DIZZINESS_SEV",
      "term": "Dizziness",
      "attribute": "severity",
      "kind": "symptom",
      "text": {
        "en": "In the past 7 days, how much dizziness have you had?",
        "es": "En los últimos 7 días, ¿qué tan fuerte ha sido el mareo?"
      },
      "options_say": {
        "en": "Would you say none, mild, moderate, severe, or very severe?",
        "es": "¿Diría que nada, leve, moderado, fuerte o muy fuerte?"
      },
      "source": "study_team",
      "followups": [
        "DIZZY_ON_STANDING"
      ]
    },
    {
      "item_code": "DIZZY_ON_STANDING",
      "term": "Dizziness",
      "attribute": "yes_no",
      "kind": "followup",
      "text": {
        "en": "Do you feel dizzy or lightheaded when you stand up?",
        "es": "¿Se marea al ponerse de pie?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": []
    },
    {
      "item_code": "FATIGUE_SEV",
      "term": "Fatigue",
      "attribute": "severity",
      "kind": "symptom",
      "text": {
        "en": "In the past 7 days, how much tiredness or lack of energy have you had?",
        "es": "En los últimos 7 días, ¿qué tan fuerte ha sido el cansancio o la falta de energía?"
      },
      "options_say": {
        "en": "Would you say none, mild, moderate, severe, or very severe?",
        "es": "¿Diría que nada, leve, moderado, fuerte o muy fuerte?"
      },
      "source": "study_team",
      "followups": [
        "FATIGUE_REST_HELPS"
      ]
    },
    {
      "item_code": "FATIGUE_REST_HELPS",
      "term": "Fatigue",
      "attribute": "yes_no",
      "kind": "followup",
      "text": {
        "en": "Does resting make the tiredness better?",
        "es": "¿El cansancio mejora cuando descansa?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": []
    },
    {
      "item_code": "RASH_ANY",
      "term": "Rash maculo-papular",
      "attribute": "yes_no",
      "kind": "symptom",
      "text": {
        "en": "In the past 7 days, have you had a new skin rash?",
        "es": "En los últimos 7 días, ¿le ha salido algún sarpullido o erupción nueva en la piel?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": [
        "SKIN_BLISTER"
      ]
    },
    {
      "item_code": "SKIN_BLISTER",
      "term": "Rash maculo-papular",
      "attribute": "yes_no",
      "kind": "followup",
      "text": {
        "en": "Is your skin blistering or peeling anywhere, or do you have painful sores in your mouth?",
        "es": "¿Tiene ampollas o la piel pelándose en alguna parte, o llagas dolorosas en la boca?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": []
    },
    {
      "item_code": "NEURO_CHANGE",
      "term": "Confusion",
      "attribute": "yes_no",
      "kind": "symptom",
      "text": {
        "en": "Have you or your family noticed any new confusion, trouble finding words, or unusual sleepiness?",
        "es": "¿Usted o su familia han notado confusión nueva, dificultad para encontrar las palabras o sueño fuera de lo normal?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": []
    },
    {
      "item_code": "MEDS_NEW",
      "term": null,
      "attribute": "yes_no",
      "kind": "flow",
      "text": {
        "en": "Since your last study visit, have you started, stopped, or changed any medicines, including ones from the pharmacy or vitamins?",
        "es": "Desde su última visita del estudio, ¿ha empezado, dejado o cambiado algún medicamento, incluidos los de la farmacia o vitaminas?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": [
        "MEDS_DETAIL"
      ]
    },
    {
      "item_code": "MEDS_DETAIL",
      "term": null,
      "attribute": "free_text",
      "kind": "flow",
      "text": {
        "en": "Which medicine was it, and when did you start or change it?",
        "es": "¿Qué medicamento fue y cuándo lo empezó o lo cambió?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": []
    },
    {
      "item_code": "CARE_VISIT",
      "term": null,
      "attribute": "yes_no",
      "kind": "flow",
      "text": {
        "en": "Since your last study visit, have you gone to an emergency room, urgent care, or another doctor?",
        "es": "Desde su última visita del estudio, ¿ha ido a una sala de emergencias, a una clínica de urgencias o a otro médico?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": [
        "CARE_VISIT_DETAIL"
      ]
    },
    {
      "item_code": "CARE_VISIT_DETAIL",
      "term": null,
      "attribute": "free_text",
      "kind": "flow",
      "text": {
        "en": "Where did you go, and what was it for?",
        "es": "¿A dónde fue y por qué motivo?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": []
    },
    {
      "item_code": "ANYTHING_ELSE",
      "term": null,
      "attribute": "yes_no",
      "kind": "flow",
      "text": {
        "en": "Is there anything else you would like the nurse to know?",
        "es": "¿Hay algo más que le gustaría que supiera la enfermera?"
      },
      "options_say": null,
      "source": "study_team",
      "followups": []
    }
  ],
  "red_flags": [
    {
      "id": "RF_FEVER",
      "level": "urgent",
      "label_en": "Temperature 38.0 °C (100.4 °F) or higher",
      "rule_based": true
    },
    {
      "id": "RF_DIARRHEA_SEVERE",
      "level": "urgent",
      "label_en": "7 or more stools a day above usual, blood or mucus in stool, black stool, or severe belly pain",
      "rule_based": true
    },
    {
      "id": "RF_DEHYDRATION",
      "level": "urgent",
      "label_en": "Dizzy on standing with diarrhea or vomiting, or can't keep liquids down",
      "rule_based": true
    },
    {
      "id": "RF_BREATHING",
      "level": "urgent",
      "label_en": "Short of breath at rest, severe shortness of breath, or new cough with shortness of breath",
      "rule_based": true
    },
    {
      "id": "RF_BREATHING_SEVERE",
      "level": "emergency",
      "label_en": "Struggling to breathe right now",
      "rule_based": false
    },
    {
      "id": "RF_CHEST_PAIN",
      "level": "emergency",
      "label_en": "Chest pain, pressure or tightness",
      "rule_based": false
    },
    {
      "id": "RF_NEURO",
      "level": "urgent",
      "label_en": "New confusion, trouble speaking, unusual sleepiness, new tremor or balance problems, severe headache",
      "rule_based": true
    },
    {
      "id": "RF_SEIZURE_FAINT",
      "level": "emergency",
      "label_en": "Seizure, fainting, or can't be woken",
      "rule_based": false
    },
    {
      "id": "RF_SKIN_SEVERE",
      "level": "urgent",
      "label_en": "Blistering or peeling skin, or painful sores in the mouth, nose, throat or genitals",
      "rule_based": true
    },
    {
      "id": "RF_LIVER_KIDNEY",
      "level": "urgent",
      "label_en": "Yellow skin or eyes, very dark urine, or much less urine than usual",
      "rule_based": false
    },
    {
      "id": "RF_HEART",
      "level": "urgent",
      "label_en": "New fast, pounding or irregular heartbeat",
      "rule_based": false
    },
    {
      "id": "RF_BLEEDING",
      "level": "urgent",
      "label_en": "Vomiting blood or bleeding that won't stop",
      "rule_based": false
    },
    {
      "id": "RF_SELF_HARM",
      "level": "emergency",
      "label_en": "Thoughts of self-harm or not wanting to live",
      "rule_based": false
    }
  ],
  "source": "seed",
  "source_citations": []
};

export const PLAN_ITEMS = PLAN.items;
export const PLAN_RED_FLAGS = PLAN.red_flags;
