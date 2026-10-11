"""V10: GET /api/eval/voice-checks serves eval/results/voice_checks.json as written, so planned calls stay pending
placeholders and are never turned into results (docs/03 §6.11)."""

import json
from pathlib import Path

from app.config import ROOT
from app.routers import api
from tests.conftest import COORD

VOICE_CHECKS = ROOT / "eval" / "results" / "voice_checks.json"
# Everything a call measures; null on a pending row (= agent/voice_check.py MEASURED_KEYS).
MEASURED_KEYS = ("conversation_id", "checkin_id", "started_at", "disclosure_first_turn", "paged", "page_level",
                 "red_flag_ids", "utterance_to_page_s", "page_to_ack_s", "term", "grade", "rule_id")


def _pending(scenario: str, variant: str, red_flag_expected: bool) -> dict:
    return {"variant": variant, "scenario": scenario, "status": "pending", "red_flag_expected": red_flag_expected,
            **dict.fromkeys(MEASURED_KEYS),
            "expected": {"patient_id": "pat_james", "term": "Diarrhea", "grade": 2, "rule_id": "CTCAE5_DIARRHEA_G2",
                         "paged": False, "red_flag_ids": []}}


def test_committed_file_is_served_as_written(client) -> None:
    assert api.ROOT == ROOT
    doc = json.loads(VOICE_CHECKS.read_text(encoding="utf-8"))
    r = client.get("/api/eval/voice-checks", headers=COORD)
    assert r.status_code == 200
    assert r.json() == {**doc, "data_origin": "MEASURED"}
    for row in r.json()["calls"]:
        if row.get("status") == "pending":
            assert all(row[k] is None for k in MEASURED_KEYS)


def test_pending_rows_stay_placeholders(client, monkeypatch, tmp_path: Path) -> None:
    doc = {"_about": "test", "run_at": None, "backend": "pending", "agent_llm": "test-model",
           "calls": [_pending("james_g2_diarrhea", "en-standard", False),
                     _pending("rosa_g3_diarrhea", "es-extra_time", True)]}
    (tmp_path / "eval" / "results").mkdir(parents=True)
    (tmp_path / "eval" / "results" / "voice_checks.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(api, "ROOT", tmp_path)
    body = client.get("/api/eval/voice-checks", headers=COORD).json()
    assert body == {**doc, "data_origin": "MEASURED"}
    assert body["run_at"] is None and body["backend"] == "pending"
    for row in body["calls"]:
        assert row["status"] == "pending"
        assert all(row[k] is None for k in MEASURED_KEYS)  # no default, no value is filled in by the route
