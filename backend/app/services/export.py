"""SDTM-style exports of confirmed drafts (docs/05 § 8). MedDRA/WHODrug columns are left empty on purpose.

The header row is line 1 (a standard CSV reader takes line 1 as the header); the note about the file travels in
the `X-BV-Note` response header instead (docs/03 §6.5, CAPA-001).
"""

import csv
import io
from typing import Any, Final

from sqlmodel import Session, select

from app import content
from app.models import CheckIn, DraftEntry, Patient, SAEReport, Study
from app.timeutil import local_date

# Every exported row is a confirmed Between Visits draft. Sponsor-defined column (SUPPAE QNAM ORIGIN in a real
# submission); Site Signal excludes rows with this origin from matching (REQ-024).
ORIGIN: Final = "between_visits"
AE_COLUMNS = ["STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM", "AEDECOD", "AEBODSYS", "AETOXGR", "AESER",
              "AESDTH", "AESLIFE", "AESHOSP", "AESDISAB", "AESCONG", "AESMIE", "AEREL", "AEOUT", "AESTDTC", "AEENDTC",
              "ORIGIN"]
CM_COLUMNS = ["STUDYID", "DOMAIN", "USUBJID", "CMSEQ", "CMTRT", "CMDECOD", "CMINDC", "CMDOSE", "CMDOSU", "CMDOSFRQ",
              "CMROUTE", "CMSTDTC", "CMENDTC"]
REL = {"not_related": "NOT RELATED", "unlikely_related": "UNLIKELY RELATED", "possibly_related": "POSSIBLY RELATED",
       "probably_related": "PROBABLY RELATED", "related": "RELATED"}
OUT = {"recovered": "RECOVERED/RESOLVED", "recovering": "RECOVERING/RESOLVING", "not_recovered": "NOT RECOVERED/NOT RESOLVED",
       "recovered_with_sequelae": "RECOVERED/RESOLVED WITH SEQUELAE", "fatal": "FATAL", "unknown": "UNKNOWN"}
CRIT = {"AESDTH": "death", "AESLIFE": "life_threatening", "AESHOSP": "hospitalization", "AESDISAB": "disability",
        "AESCONG": "congenital_anomaly", "AESMIE": "important_medical_event"}
CM_NOTE = "synthetic data; CMDECOD empty: WHODrug coding is licensed and done downstream"


def ae_note() -> str:
    """`X-BV-Note` for ae.csv (docs/03 §6.5)."""
    return (f"CTCAE v{content.ctcae_version()}; synthetic data; AEDECOD/AEBODSYS coded downstream by licensed sponsor; "
            "ORIGIN is a sponsor-defined column")


def outcome_of(payload: dict[str, Any] | None) -> str:
    """Outcome key of an AE draft, shared by ae.csv `AEOUT` and the SAE report's `reaction.outcome` (docs/03 §6.5).

    A known `outcome` key wins; otherwise an ongoing event is `not_recovered` and anything else is `unknown`.
    """
    pay = payload or {}
    key = pay.get("outcome")
    if isinstance(key, str) and key in OUT:
        return key
    return "not_recovered" if pay.get("ongoing") is True else "unknown"


def _yn(v: bool) -> str:
    return "Y" if v else "N"


def _confirmed(session: Session, kind: str) -> list[tuple[DraftEntry, Patient, CheckIn]]:
    rows = session.exec(
        select(DraftEntry).where(DraftEntry.kind == kind, DraftEntry.status == "confirmed").order_by(DraftEntry.created_at)  # type: ignore[arg-type]
    ).all()
    out = []
    for d in rows:
        p, c = session.get(Patient, d.patient_id), session.get(CheckIn, d.checkin_id)
        if p and c:
            out.append((d, p, c))
    return out


def _studyid(session: Session) -> str:
    s = session.exec(select(Study)).first()
    return s.nct_id if s else ""


def ae_csv(session: Session) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=AE_COLUMNS)
    w.writeheader()
    sid = _studyid(session)
    seq: dict[str, int] = {}
    for d, p, c in _confirmed(session, "AE"):
        seq[p.id] = seq.get(p.id, 0) + 1
        pay, inv = d.payload or {}, d.investigator or {}
        crit = set(inv.get("seriousness_criteria", []))
        grade = pay.get("provisional_grade")
        row: dict[str, Any] = {
            "STUDYID": sid, "DOMAIN": "AE", "USUBJID": f"{sid}-{p.subject_id}", "AESEQ": seq[p.id], "AESPID": c.id,
            "AETERM": pay.get("term", ""), "AEDECOD": "", "AEBODSYS": "", "AETOXGR": str(grade) if grade else "",
            "AESER": _yn(bool(inv.get("is_serious"))) if inv else "",
            "AEREL": REL.get(inv.get("relatedness", ""), ""), "AEOUT": OUT[outcome_of(pay)],
            "AESTDTC": pay.get("onset_date") or local_date(c.started_at or c.created_at).isoformat(), "AEENDTC": "",
            "ORIGIN": ORIGIN,
        }
        for col, key in CRIT.items():
            row[col] = _yn(key in crit) if inv else ""
        w.writerow(row)
    return buf.getvalue()


def cm_csv(session: Session) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CM_COLUMNS)
    w.writeheader()
    sid = _studyid(session)
    seq: dict[str, int] = {}
    for d, p, _c in _confirmed(session, "CM"):
        seq[p.id] = seq.get(p.id, 0) + 1
        pay = d.payload or {}
        w.writerow({
            "STUDYID": sid, "DOMAIN": "CM", "USUBJID": f"{sid}-{p.subject_id}", "CMSEQ": seq[p.id],
            "CMTRT": pay.get("medication_name", ""), "CMDECOD": "", "CMINDC": pay.get("indication_en") or "",
            "CMDOSE": "", "CMDOSU": "", "CMDOSFRQ": "", "CMROUTE": pay.get("route", "UNKNOWN") or "UNKNOWN",
            "CMSTDTC": pay.get("start_date") or "", "CMENDTC": "",
        })
    return buf.getvalue()


def sae_json(r: SAEReport) -> dict[str, Any]:
    return {**r.payload, "narrative": r.narrative_final or r.payload.get("narrative"), "status": r.status,
            "sae_id": r.id}
