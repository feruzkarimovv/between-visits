"""Offline checks for agent/voice_check.py (WS1 V10): the measurements, the pending-row fill, ID truncation and the
committed eval/results/voice_checks.json (no network, no key).

Run: python3 agent/test_voice_check.py   (or: uv run --project backend python agent/test_voice_check.py)

The conversation fixture is the scripted post-call body in scenarios/fixtures/post_call_rosa.json (synthetic, built
from the approved scripts) with tool results added; the check-in fixture is a GET /api/checkins/{id}-shaped body
with one urgent escalation. Times are invented test values, not measurements.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import voice_check as vc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "scenarios" / "fixtures" / "post_call_rosa.json"
COMMITTED = ROOT / "eval" / "results" / "voice_checks.json"
SNAPSHOT = json.loads((ROOT / "agent" / "deployed_snapshot.json").read_text(encoding="utf-8"))
SCRIPTS = json.loads((ROOT / "data" / "scripts.json").read_text(encoding="utf-8"))
STUDY = json.loads((ROOT / "data" / "study.json").read_text(encoding="utf-8"))

CONV_ID = "conv_3h8j1k5m7n2p4q6r9s0t"
OTHER_CONV = "conv_9z8y7x6w5v4u3t2s1r0q"
CHECKIN_ID = "ci_VOICETEST9Q2W"
AGENT_ID = "agent_7k2m9q4x8w1z5v3n6p" + SNAPSHOT["variants"]["es-extra_time"]["agent_id_suffix"]
API_KEY = "fixture-key-not-real"
TOKEN = "fixture-token-not-real"
START = 1791685800  # 2026-10-11T02:30:00Z
ESCALATING_T = 90  # the record_answer for the stool count (read-back confirmed at 89 s)
PLANNED = ("james_g2_diarrhea", "james_g3_diarrhea", "rosa_g3_diarrhea")  # the WS1 V10 table
FORBIDDEN = [CONV_ID, OTHER_CONV, CHECKIN_ID, AGENT_ID, API_KEY, TOKEN, "bv-live-api.onrender.com"]


def at(seconds: float) -> str:
    return datetime.fromtimestamp(START + seconds, tz=UTC).isoformat().replace("+00:00", "Z")


def rendered_first_message(lang: str, name: str) -> str:
    return (SCRIPTS["lines"]["first_message"][lang]
            .replace("{study_team_name}", STUDY["study_team_name"][lang]).replace("{patient_first_name}", name))


def conversation(*, tool_results: bool = True) -> dict:
    """GET /v1/convai/conversations/{id}-shaped: the scripted Rosa call plus request IDs and tool results whose
    `escalated` turns true at the stool-count answer (the backend envelope is sticky, docs/03 §2)."""
    conv = copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8"))["data"])
    conv.update({"agent_id": AGENT_ID, "conversation_id": CONV_ID, "status": "done"})
    conv["metadata"]["start_time_unix_secs"] = START
    conv["conversation_initiation_client_data"] = {"dynamic_variables": {"checkin_id": CHECKIN_ID}}
    for i, turn in enumerate(conv["transcript"]):
        for call in turn.get("tool_calls") or []:
            call["request_id"] = f"req_{i}"
            if tool_results:
                body = {"ok": True, "next": {"action": "ask"}, "escalated": turn["time_in_call_secs"] >= ESCALATING_T}
                turn.setdefault("tool_results", []).append(
                    {"request_id": f"req_{i}", "tool_name": call["tool_name"], "result_value": json.dumps(body)})
    return conv


def checkin_detail(*, paged_at: float | None = 91.5, ack_at: float | None = 125.0, grade: int = 3) -> dict:
    escalations = []
    if paged_at is not None:
        escalations.append({
            "id": "esc_fixture", "level": "urgent", "status": "acknowledged" if ack_at else "open",
            "red_flag_ids": ["RF_DIARRHEA_SEVERE", "RF_DEHYDRATION"], "created_at": at(paged_at - 0.2),
            "paged_at": at(paged_at), "acknowledged_at": at(ack_at) if ack_at is not None else None,
            "acknowledged_by": "Nurse Fixture-Name"})
    escalations.append({"id": "esc_cb", "level": "callback", "paged_at": None, "red_flag_ids": []})
    return {
        "checkin": {"id": CHECKIN_ID, "patient_id": "pat_rosa", "language": "es", "pace": "extra_time",
                    "agent_variant": "es-extra_time", "el_conversation_id": CONV_ID, "started_at": at(1)},
        "findings": [
            {"term": "Dizziness", "provisional_grade": None, "rule_id": None},
            {"term": "Diarrhea", "provisional_grade": grade, "rule_id": f"CTCAE5_DIARRHEA_G{grade}"},
        ],
        "escalations": escalations,
    }


def english_conversation(conv_id: str = OTHER_CONV) -> dict:
    """A short English call (James) with no page."""
    return {
        "conversation_id": conv_id, "agent_id": "agent_en_fixture" + SNAPSHOT["variants"]["en-standard"]["agent_id_suffix"],
        "status": "done",
        "metadata": {"start_time_unix_secs": START, "call_duration_secs": 60},
        "conversation_initiation_client_data": {"dynamic_variables": {"checkin_id": "ci_JAMESTEST0001"}},
        "transcript": [
            {"role": "agent", "message": rendered_first_message("en", "James"), "time_in_call_secs": 0},
            {"role": "user", "message": "Yes, this is James.", "time_in_call_secs": 7},
            {"role": "agent", "message": None, "time_in_call_secs": 8,
             "tool_calls": [{"request_id": "r1", "tool_name": "record_answer", "params_as_json": "{}"}],
             "tool_results": [{"request_id": "r1", "result_value": json.dumps({"ok": True, "escalated": False})}]},
        ],
    }


def english_detail(conv_id: str = OTHER_CONV) -> dict:
    return {
        "checkin": {"id": "ci_JAMESTEST0001", "patient_id": "pat_james", "language": "en", "pace": "standard",
                    "agent_variant": "en-standard", "el_conversation_id": conv_id, "started_at": at(0)},
        "findings": [{"term": "Diarrhea", "provisional_grade": 2, "rule_id": "CTCAE5_DIARRHEA_G2"}],
        "escalations": [],
    }


def pending_copy() -> dict:
    """The committed file with every row reset to a pending placeholder, so these tests hold after real calls."""
    doc = json.loads(COMMITTED.read_text(encoding="utf-8"))
    doc.update({"run_at": None, "backend": "pending"})
    seen: set[str] = set()
    calls = []
    for c in doc["calls"]:
        if c["scenario"] in seen:
            continue  # an appended repeat call
        seen.add(c["scenario"])
        calls.append(vc.ordered_row({**c, "status": "pending", **dict.fromkeys(vc.MEASURED_KEYS)}))
    doc["calls"] = calls
    return doc


class DisclosureTests(unittest.TestCase):
    def check(self, text: str, lang: str = "es") -> bool:
        conv = conversation()
        conv["transcript"][0]["message"] = text
        row, _, _ = vc.measure(conv, checkin_detail() if lang == "es" else english_detail())
        return row["disclosure_first_turn"]

    def test_scripted_first_turn_discloses(self) -> None:
        row, notes, _ = vc.measure(conversation(), checkin_detail())
        self.assertIs(row["disclosure_first_turn"], True)
        self.assertTrue(any("contains the approved es first message" in n for n in notes), notes)

    def test_every_language_matches_its_own_rendering(self) -> None:
        for lang in SCRIPTS["lines"]["first_message"]:
            with self.subTest(lang=lang):
                pattern = vc.disclosure_pattern(lang)
                self.assertTrue(pattern.search(vc.normalize(rendered_first_message(lang, "Ana María"))))

    def test_normalization_and_name_wildcard(self) -> None:
        en = rendered_first_message("en", "James")
        self.assertTrue(self.check(en, "en"))
        self.assertTrue(self.check("  " + en.upper().replace("I'M", "I’m").replace(" ", "\n ", 3), "en"))
        self.assertTrue(self.check(rendered_first_message("es", "Rosa Elena"), "es"))

    def test_wrong_or_partial_first_turn_does_not_disclose(self) -> None:
        es = rendered_first_message("es", "Rosa")
        self.assertFalse(self.check(es.replace("del equipo", "de el equipo")))  # the wording before D8
        human_offer = es.split(". ")[1]
        self.assertFalse(self.check(es.replace(human_offer, "Soy un asistente")))  # no offer of a human
        self.assertFalse(self.check(rendered_first_message("en", "Rosa"), "es"))  # the other language
        conv = conversation()
        conv["transcript"].insert(0, {"role": "agent", "message": "Hola.", "time_in_call_secs": 0})
        self.assertIs(vc.measure(conv, checkin_detail())[0]["disclosure_first_turn"], False)  # only in turn 2

    def test_no_agent_turn(self) -> None:
        conv = conversation()
        conv["transcript"] = [t for t in conv["transcript"] if t["role"] != "agent" or not t.get("message")]
        row, _, warnings = vc.measure(conv, checkin_detail())
        self.assertIs(row["disclosure_first_turn"], False)
        self.assertTrue(any("no agent turn" in w for w in warnings))


class MeasureTests(unittest.TestCase):
    def test_red_flag_call(self) -> None:
        row, notes, warnings = vc.measure(conversation(), checkin_detail(), term="Diarrhea")
        self.assertEqual(row, {
            "started_at": "2026-10-11T02:30:00Z", "disclosure_first_turn": True, "paged": True, "page_level": "urgent",
            "red_flag_ids": ["RF_DIARRHEA_SEVERE", "RF_DEHYDRATION"],
            "utterance_to_page_s": 2.5,  # page at 91.5 s - the read-back confirmation at 89 s
            "page_to_ack_s": 33.5,  # 125 - 91.5
            "term": "Diarrhea", "grade": 3, "rule_id": "CTCAE5_DIARRHEA_G3"})
        self.assertEqual(warnings, [])
        self.assertTrue(any("patient turn at 89.0 s" in n and "escalating tool call (90.0 s)" in n for n in notes))

    def test_trigger_is_the_turn_before_the_escalating_tool_call(self) -> None:
        # Page late, after the next patient turn (104 s): the trigger is still the turn before the escalating call.
        row, _, _ = vc.measure(conversation(), checkin_detail(paged_at=106.0))
        self.assertEqual(row["utterance_to_page_s"], 17.0)  # 106 - 89
        # Without tool results, the last patient turn before the page counts.
        row, notes, _ = vc.measure(conversation(tool_results=False), checkin_detail(paged_at=106.0))
        self.assertEqual(row["utterance_to_page_s"], 2.0)  # 106 - 104
        self.assertTrue(any("no tool result says escalated" in n for n in notes), notes)

    def test_unacknowledged_page(self) -> None:
        row, _, warnings = vc.measure(conversation(), checkin_detail(ack_at=None))
        self.assertIs(row["paged"], True)
        self.assertIsNone(row["page_to_ack_s"])
        self.assertTrue(any("not acknowledged" in w for w in warnings))

    def test_no_page(self) -> None:
        row, _, warnings = vc.measure(english_conversation(), english_detail(), term="Diarrhea")
        self.assertEqual(row, {
            "started_at": "2026-10-11T02:30:00Z", "disclosure_first_turn": True, "paged": False, "page_level": None,
            "red_flag_ids": [], "utterance_to_page_s": None, "page_to_ack_s": None,
            "term": "Diarrhea", "grade": 2, "rule_id": "CTCAE5_DIARRHEA_G2"})
        self.assertEqual(warnings, [])

    def test_failed_page_is_not_paged(self) -> None:
        detail = checkin_detail()
        detail["escalations"][0]["paged_at"] = None
        row, _, warnings = vc.measure(conversation(), detail)
        self.assertIs(row["paged"], False)
        self.assertTrue(any("no paged_at" in w for w in warnings))

    def test_negative_interval_is_not_written(self) -> None:
        row, _, warnings = vc.measure(conversation(), checkin_detail(paged_at=91.5, ack_at=80.0))
        self.assertIsNone(row["page_to_ack_s"])
        self.assertTrue(any("page_to_ack_s would be" in w for w in warnings))

    def test_pick_finding(self) -> None:
        findings = [{"term": "Fatigue", "provisional_grade": 1, "rule_id": "F1"},
                    {"term": "Diarrhea", "provisional_grade": None, "rule_id": None},
                    {"term": "Dyspnea", "provisional_grade": 3, "rule_id": "D3"}]
        self.assertEqual(vc.pick_finding(findings, None)["rule_id"], "D3")  # highest grade
        self.assertEqual(vc.pick_finding(findings, "diarrhea")["term"], "Diarrhea")  # the planned term, ungraded
        self.assertIsNone(vc.pick_finding(findings, "Fever"))
        self.assertIsNone(vc.pick_finding([{"term": "Rash", "provisional_grade": None}], None))

    def test_short_ids(self) -> None:
        self.assertEqual(vc.short_id(CONV_ID), "conv_...9s0t")
        self.assertEqual(vc.short_id(CHECKIN_ID), "ci_...9Q2W")
        self.assertEqual(vc.short_id("abcdef"), "...cdef")
        self.assertIsNone(vc.short_id(None))
        self.assertTrue(vc.is_short_id("conv_...9s0t") and vc.is_short_id("ci_...9Q2W"))
        self.assertFalse(vc.is_short_id(CONV_ID) or vc.is_short_id(None))


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.file = self.tmp / "voice_checks.json"
        self.file.write_text(json.dumps(pending_copy(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.write("conv.json", conversation())
        self.write("ci.json", checkin_detail())
        patcher = mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": API_KEY, "BV_DASHBOARD_TOKEN": TOKEN,
                                               "LIVE_API": "https://bv-live-api.onrender.com"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name: str, data: dict) -> None:
        (self.tmp / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def doc(self) -> dict:
        return json.loads(self.file.read_text(encoding="utf-8"))

    def run_main(self, *args: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = vc.main(["--file", str(self.file), *args])
        text = out.getvalue() + err.getvalue()
        for s in FORBIDDEN:
            self.assertNotIn(s, text, s)  # never a key, a token, a full ID or the live URL
        return code, text

    def offline(self, *args: str, scenario: str = "rosa_g3_diarrhea", checkin: str = CHECKIN_ID) -> tuple[int, str]:
        return self.run_main("--checkin-id", checkin, "--scenario", scenario, "--backend", "render-live",
                             "--conversation-file", str(self.tmp / "conv.json"),
                             "--checkin-file", str(self.tmp / "ci.json"), *args)

    def test_fills_the_pending_row_in_place(self) -> None:
        before = self.doc()
        code, out = self.offline()
        self.assertEqual(code, 0, out)
        self.assertIn("fills its pending row", out)
        self.assertIn("measured as planned", out)
        doc = self.doc()
        text = self.file.read_text(encoding="utf-8")
        for s in FORBIDDEN:
            self.assertNotIn(s, text, s)
        self.assertEqual(len(doc["calls"]), len(before["calls"]))  # filled, not appended
        idx = next(i for i, c in enumerate(before["calls"]) if c["scenario"] == "rosa_g3_diarrhea")
        row = doc["calls"][idx]
        self.assertEqual({k: row[k] for k in ("variant", "conversation_id", "checkin_id", "scenario", "status")},
                         {"variant": "es-extra_time", "conversation_id": "conv_...9s0t", "checkin_id": "ci_...9Q2W",
                          "scenario": "rosa_g3_diarrhea", "status": "logged"})
        self.assertEqual((row["paged"], row["utterance_to_page_s"], row["page_to_ack_s"], row["grade"]),
                         (True, 2.5, 33.5, 3))
        self.assertIs(row["red_flag_expected"], True)
        self.assertEqual(row["expected"], before["calls"][idx]["expected"])  # the plan is kept
        self.assertEqual(list(row)[:len(vc.ROW_KEYS)], list(vc.ROW_KEYS))
        for i, c in enumerate(doc["calls"]):
            if i != idx:
                self.assertEqual(c, before["calls"][i])  # the other planned rows stay pending
        self.assertEqual((doc["run_at"], doc["backend"], doc["agent_llm"]),
                         ("2026-10-11T02:30:00Z", "render-live", vc.snapshot_llm()))
        self.assertEqual(list(doc)[:5], ["_about", "run_at", "backend", "agent_llm", "calls"])

    def test_rerun_for_the_same_call_updates_its_row(self) -> None:
        self.write("ci.json", checkin_detail(ack_at=None))
        code, out = self.offline()
        self.assertEqual(code, 0, out)
        self.assertIn("not acknowledged", out)
        self.write("ci.json", checkin_detail())  # the nurse acknowledged afterwards
        code, out = self.offline()
        self.assertEqual(code, 0, out)
        self.assertIn("updates its logged row", out)
        rows = [c for c in self.doc()["calls"] if c["scenario"] == "rosa_g3_diarrhea"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["page_to_ack_s"], 33.5)

    def test_a_second_call_for_a_logged_scenario_needs_append(self) -> None:
        self.assertEqual(self.offline()[0], 0)
        conv, detail = conversation(), checkin_detail()
        conv["conversation_id"] = OTHER_CONV
        detail["checkin"]["el_conversation_id"] = OTHER_CONV
        self.write("conv.json", conv)
        self.write("ci.json", detail)
        n = len(self.doc()["calls"])
        code, out = self.offline()
        self.assertEqual(code, 1)
        self.assertIn("already logged", out)
        self.assertEqual(len(self.doc()["calls"]), n)
        code, out = self.offline("--append")
        self.assertEqual(code, 0, out)
        rows = [c for c in self.doc()["calls"] if c["scenario"] == "rosa_g3_diarrhea"]
        self.assertEqual([r["conversation_id"] for r in rows], ["conv_...9s0t", "conv_...1r0q"])
        self.assertEqual(rows[1]["expected"], rows[0]["expected"])

    def test_wrong_scenario_is_refused(self) -> None:
        before = self.file.read_text(encoding="utf-8")
        code, out = self.offline(scenario="james_g2_diarrhea")  # a Rosa es-extra_time call
        self.assertEqual(code, 1)
        self.assertIn("planned for en-standard", out)
        detail = checkin_detail()
        detail["checkin"]["patient_id"] = "pat_walter"
        self.write("ci.json", detail)
        code, out = self.offline()
        self.assertEqual(code, 1)
        self.assertIn("planned for pat_rosa", out)
        self.write("ci.json", checkin_detail())
        code, out = self.offline("--red-flag-expected", "no")
        self.assertIn("contradicts the planned row", out)
        self.assertEqual(code, 1)
        self.assertEqual(self.file.read_text(encoding="utf-8"), before)

    def test_unplanned_scenario_needs_red_flag_expected(self) -> None:
        code, out = self.offline(scenario="rosa_hero_call")
        self.assertEqual(code, 1)
        self.assertIn("--red-flag-expected", out)
        code, out = self.offline("--red-flag-expected", "yes", scenario="rosa_hero_call")
        self.assertEqual(code, 0, out)
        row = self.doc()["calls"][-1]
        self.assertEqual((row["scenario"], row["status"], row["red_flag_expected"]), ("rosa_hero_call", "logged", True))
        self.assertNotIn("expected", row)

    def test_unlinked_call_is_refused(self) -> None:
        detail = checkin_detail()
        detail["checkin"]["el_conversation_id"] = OTHER_CONV
        self.write("ci.json", detail)
        before = self.file.read_text(encoding="utf-8")
        code, out = self.offline("--conversation-id", CONV_ID)
        self.assertEqual(code, 1)
        self.assertIn("do not match", out)
        self.assertEqual(self.file.read_text(encoding="utf-8"), before)
        conv = conversation()
        conv["status"] = "processing"
        self.write("conv.json", conv)
        self.write("ci.json", checkin_detail())
        code, out = self.offline()
        self.assertEqual(code, 1)
        self.assertIn("not 'done'", out)

    def test_differences_from_the_plan_are_logged_as_measured(self) -> None:
        self.write("ci.json", checkin_detail(paged_at=None, grade=2))
        code, out = self.offline()
        self.assertEqual(code, 0, out)
        self.assertIn("DIFFERS from the plan", out)
        row = next(c for c in self.doc()["calls"] if c["scenario"] == "rosa_g3_diarrhea")
        self.assertEqual((row["status"], row["paged"], row["grade"], row["rule_id"]),
                         ("logged", False, 2, "CTCAE5_DIARRHEA_G2"))

    def test_dry_run_writes_nothing(self) -> None:
        before = self.file.read_text(encoding="utf-8")
        code, out = self.offline("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("dry run", out)
        self.assertIn('"conversation_id": "conv_...9s0t"', out)
        self.assertEqual(self.file.read_text(encoding="utf-8"), before)

    def test_network_path_and_backend(self) -> None:
        """The API reads (faked): the check-in first, then the conversation it names; headers carry the key/token."""
        calls: list[tuple[str, dict[str, str]]] = []
        james_conv, james_ci = "conv_jamesfixture00000001", "ci_JAMESTEST0001"

        def fake_get(url: str, headers: dict[str, str], what: str):  # noqa: ANN202
            calls.append((url, headers))
            if url == f"https://bv-live-api.onrender.com/api/checkins/{CHECKIN_ID}":
                return checkin_detail()
            if url == f"{vc.API_BASE}/v1/convai/conversations/{CONV_ID}":
                return conversation()
            if url == f"https://bv-live-api.onrender.com/api/checkins/{james_ci}":
                return english_detail(james_conv)
            if url == f"{vc.API_BASE}/v1/convai/conversations/{james_conv}":
                return english_conversation(james_conv)
            raise AssertionError(url)

        with mock.patch.object(vc, "http_get", fake_get):
            code, out = self.run_main("--checkin-id", CHECKIN_ID, "--scenario", "rosa_g3_diarrhea")
            self.assertEqual(code, 0, out)
            self.assertEqual(calls, [
                (f"https://bv-live-api.onrender.com/api/checkins/{CHECKIN_ID}", {"X-BV-Token": TOKEN}),
                (f"{vc.API_BASE}/v1/convai/conversations/{CONV_ID}", {"xi-api-key": API_KEY}),
            ])
            self.assertEqual(self.doc()["backend"], "render-live")  # from the onrender.com URL
            code, out = self.run_main("--checkin-id", james_ci, "--scenario", "james_g2_diarrhea", "--backend", "tunnel")
            self.assertEqual(code, 1)
            self.assertIn("one backend", out)
            code, out = self.run_main("--checkin-id", james_ci, "--scenario", "james_g2_diarrhea")
            self.assertEqual(code, 0, out)
        doc = self.doc()
        logged = [c for c in doc["calls"] if c["status"] == "logged"]
        self.assertEqual([c["scenario"] for c in logged], ["james_g2_diarrhea", "rosa_g3_diarrhea"])
        self.assertEqual(logged[0]["conversation_id"], "conv_...0001")

    def test_unknown_backend_url_needs_backend_flag(self) -> None:
        with mock.patch.dict(os.environ, {"LIVE_API": "https://api.example.test"}), \
                mock.patch.object(vc, "http_get", side_effect=[checkin_detail(), conversation()]):
            code, out = self.run_main("--checkin-id", CHECKIN_ID, "--scenario", "rosa_g3_diarrhea")
        self.assertEqual(code, 1)
        self.assertIn("--backend", out)

    def test_missing_snapshot_suffix_mismatch_warns(self) -> None:
        conv = conversation()
        conv["agent_id"] = "agent_someotheragent0000"
        self.write("conv.json", conv)
        code, out = self.offline()
        self.assertEqual(code, 0, out)
        self.assertIn("deployed_snapshot.json records", out)


def _ids(path: Path, key: str = "id") -> set[str]:
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if isinstance(node.get(key), str):
                found.add(node[key])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(json.loads(path.read_text(encoding="utf-8")))
    return found


class CommittedFileTests(unittest.TestCase):
    """eval/results/voice_checks.json in git: pending rows are placeholders with every measurement null; logged rows
    hold only truncated IDs; every plan names a real variant, patient, rule and red flag."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.doc = json.loads(COMMITTED.read_text(encoding="utf-8"))

    def test_header(self) -> None:
        d = self.doc
        self.assertEqual(list(d)[:5], ["_about", "run_at", "backend", "agent_llm", "calls"])
        self.assertEqual(d["agent_llm"], vc.snapshot_llm())
        self.assertIn(d["backend"], ("pending", *vc.BACKENDS))
        self.assertNotIn("data_origin", d)  # the route adds MEASURED
        logged = [c for c in d["calls"] if c["status"] == "logged"]
        if d["backend"] == "pending":
            self.assertEqual(logged, [])
            self.assertIsNone(d["run_at"])
        else:
            self.assertEqual(d["run_at"], min(c["started_at"] for c in logged))

    def test_planned_calls_present_once(self) -> None:
        scenarios = [c["scenario"] for c in self.doc["calls"]]
        self.assertLessEqual(set(PLANNED), set(scenarios))
        pending = [s for s, c in zip(scenarios, self.doc["calls"], strict=True) if c["status"] == "pending"]
        self.assertEqual(len(pending), len(set(pending)))  # one placeholder per planned call

    def test_rows(self) -> None:
        variants = set(json.loads((ROOT / "agent" / "variants.json").read_text(encoding="utf-8"))["variants"])
        patients = _ids(ROOT / "data" / "patients.json")
        rules = _ids(ROOT / "data" / "ctcae_rules.json")
        flags = _ids(ROOT / "data" / "red_flags.json")
        for row in self.doc["calls"]:
            with self.subTest(scenario=row.get("scenario")):
                self.assertIn(row["status"], ("pending", "logged"))
                self.assertIn(row["variant"], variants)
                self.assertIsInstance(row["red_flag_expected"], bool)
                if row["status"] == "pending":
                    self.assertEqual({k: row.get(k, None) for k in vc.MEASURED_KEYS},
                                     dict.fromkeys(vc.MEASURED_KEYS))  # placeholders, never results
                else:
                    self.assertTrue(vc.is_short_id(row["conversation_id"]), row["conversation_id"])
                    self.assertTrue(vc.is_short_id(row["checkin_id"]), row["checkin_id"])
                    self.assertIsInstance(row["disclosure_first_turn"], bool)
                    self.assertIsInstance(row["paged"], bool)
                exp = row.get("expected")
                if exp is not None:
                    self.assertIn(exp["patient_id"], patients)
                    self.assertIn(exp["rule_id"], rules)
                    self.assertTrue(set(exp["red_flag_ids"]) <= flags, exp["red_flag_ids"])
                    self.assertEqual(exp["paged"], row["red_flag_expected"])
                    self.assertEqual(exp["paged"], bool(exp["red_flag_ids"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
