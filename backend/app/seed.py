"""`python -m app.seed`: drop and recreate the database, load data/*.json (+ data/patients.local.json).

Dose dates are computed from `dose_offsets_days` relative to today (DISPLAY_TZ), so someone is always due.
Real phone numbers come only from data/patients.local.json (gitignored).
"""

import json
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Session

from app import content
from app.config import DATA_DIR, get_settings
from app.db import create_all, drop_all, get_engine
from app.ids import new_id
from app.models import CheckIn, CheckInPlan, Patient, Study
from app.timeutil import utcnow

log = logging.getLogger("bv.seed")


def today_local() -> date:
    return datetime.now(ZoneInfo(get_settings().display_tz)).date()


def _local_overrides() -> dict:
    p = DATA_DIR / "patients.local.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def due_day(dose_dates: list[str], schedule: list[int], on: date) -> int | None:
    for d in dose_dates:
        delta = (on - date.fromisoformat(d)).days
        if delta in schedule:
            return delta
    return None


def variant_for(language: str, pace: str) -> str:
    return f"{language}-{pace}"


def seed(session: Session) -> dict[str, int]:
    content.reload()
    sd = content.study_doc()
    pd = content.plan_doc()
    study = Study(
        id=sd["id"], nct_id=sd["nct_id"], title_short=sd["title_short"], drug_class=sd["drug_class"],
        masking=sd["masking"], site_id=sd["site_id"], site_name=sd["site_name"],
        study_team_name=sd["study_team_name"], active_plan_id=sd["active_plan_id"],
        sponsor_study_number=sd.get("sponsor_study_number"),
    )
    session.add(study)
    plan = CheckInPlan(
        id=pd["id"], study_id=pd["study_id"], version=pd["version"], status=pd["status"], items=pd["items"],
        red_flag_ids=pd["red_flag_ids"], schedule_days_after_dose=pd["schedule_days_after_dose"],
        source=pd["source"], source_citations=pd["source_citations"], approved_by=pd.get("approved_by"),
        approved_at=datetime.fromisoformat(pd["approved_at"].replace("Z", "+00:00")) if pd.get("approved_at") else None,
    )
    session.add(plan)
    local = _local_overrides()
    today = today_local()
    n_checkins = 0
    patients = content.patients_doc()["patients"]
    for p in patients:
        over = local.get(p["id"], {})
        dose_dates = [(today + timedelta(days=o)).isoformat() for o in p["dose_offsets_days"]]
        pat = Patient(
            id=p["id"], study_id=study.id, subject_id=p["subject_id"], first_name=p["first_name"],
            last_name=p["last_name"], age=p["age"], sex=p["sex"], language=p["language"], pace=p["pace"],
            hearing=p.get("hearing", "typical"), caregiver_name=p.get("caregiver_name"),
            caregiver_relation=p.get("caregiver_relation"), caregiver_may_answer=p.get("caregiver_may_answer", False),
            phone_e164=over.get("phone_e164", p["phone_e164"]), dose_dates=dose_dates,
            baseline=p.get("baseline", {}), notes=p.get("notes", ""),
        )
        session.add(pat)
        day = due_day(dose_dates, plan.schedule_days_after_dose, today)
        if day is not None:
            session.add(
                CheckIn(
                    id=new_id("ci"), patient_id=pat.id, study_id=study.id, plan_id=plan.id, day_after_dose=day,
                    scheduled_for=utcnow(), channel="phone", language=pat.language, pace=pat.pace,
                    agent_variant=variant_for(pat.language, pat.pace), status="scheduled",
                )
            )
            n_checkins += 1
    session.commit()
    return {"patients": len(patients), "checkins_due_today": n_checkins, "local_overrides": len(local)}


def reset_and_seed() -> dict[str, int]:
    drop_all()
    create_all()
    with Session(get_engine()) as s:
        return seed(s)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(reset_and_seed()))
