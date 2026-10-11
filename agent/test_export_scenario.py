"""Offline checks for agent/export_scenario.py (WS1 V11): the field whitelist and ID truncation (no network, no key).

Run: python3 agent/test_export_scenario.py   (or: uv run --project backend python agent/test_export_scenario.py)

The fixture is the scripted post-call body in scenarios/fixtures/post_call_rosa.json (synthetic, built from the
approved scripts), loaded with every kind of metadata a real conversation carries: caller identifiers, dynamic
variables, fictional 555 phone numbers, a user ID, analysis blocks, tool results and stray tool arguments. The
export must keep none of it.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import export_scenario as ex  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "scenarios" / "fixtures" / "post_call_rosa.json"

AGENT_ID = "agent_7k2m9q4x8w1z5v3n6p0r"
CONV_ID = "conv_3h8j1k5m7n2p4q6r9s0t"
CHECKIN_ID = "ci_EXPORTTEST9Q2W"
USER_ID = "101-007"
CALL_SID = "CA5f0e1d2c3b4a59687766554433221100"
CALLER = "+15555550142"
PATIENT_PHONE = "+15555550107"
NURSE = "Nurse Fixture-Name"
SUMMARY = "Fixture analysis summary that must not be exported."
DYN_NAME = "Fixturename Dynamicvar"
START = 1791685800  # 2026-10-11T02:30:00Z = 2026-10-10 22:30 in America/New_York
ACK_AT = "2026-10-11T02:32:05Z"  # 125 s after the call start
TZ = "America/New_York"

# Independent of export_scenario's own constants: if someone widens the exporter's whitelist, this test still fails.
TOP_LEVEL = {"_about", "id", "title", "patient_id", "day_after_dose", "recorded", "recorded_at", "label",
             "agent_id_suffix", "conversation_id_suffix", "audio", "events"}
EVENT_KEYS = {
    "call_started": {"t", "type"},
    "tool": {"t", "type", "tool", "body"},
    "page_ack": {"t", "type", "by", "method"},
    "call_ended": {"t", "type", "termination_reason"},
    "post_call": {"t", "type", "transcript"},
}
TURN_KEYS = {"role", "text", "t_s"}
LABEL = "Recorded real call; synthetic patient played by a teammate"


def tool_body_whitelist() -> dict[str, set[str]]:
    tools = json.loads((ROOT / "agent" / "tools.json").read_text(encoding="utf-8"))["tools"]
    return {t["name"]: set(t["api_schema"]["request_body_schema"]["properties"]) - {"checkin_id", "conversation_id"}
            for t in tools}


def conversation() -> dict:
    """GET /v1/convai/conversations/{id}-shaped fixture with everything a real one may carry, and more."""
    conv = copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8"))["data"])
    conv.update({
        "agent_id": AGENT_ID, "conversation_id": CONV_ID, "user_id": USER_ID, "status": "done", "has_audio": True,
        "branch_id": "agtbrch_fixture", "version_id": "agtvrsn_fixture",
    })
    conv["metadata"].update({
        "start_time_unix_secs": START, "call_duration_secs": 160,
        "phone_call": {"type": "twilio", "direction": "inbound", "call_sid": CALL_SID, "external_number": CALLER,
                       "agent_number": PATIENT_PHONE},
        "authorization_method": "signed_url", "charging": {"llm_price": 0.01}, "feedback": {"overall_score": None},
        "batch_call": {"batch_call_id": "btcal_fixture", "batch_call_recipient_id": "rcp_fixture"},
        "termination_reason": "Client disconnected: fixture",
    })
    conv["analysis"] = {"call_successful": "success", "transcript_summary": SUMMARY,
                        "evaluation_criteria_results": {"no_medical_advice": {"result": "success", "rationale": SUMMARY}},
                        "data_collection_results": {"speaker": {"value": "patient", "rationale": SUMMARY}}}
    conv["conversation_initiation_client_data"] = {
        "dynamic_variables": {"checkin_id": CHECKIN_ID, "patient_first_name": DYN_NAME, "caller_phone": CALLER,
                              "system__caller_id": CALLER, "system__conversation_id": CONV_ID},
        "conversation_config_override": {"agent": {"first_message": "fixture override"}},
        "source_info": {"source": "react_sdk", "version": "1.17.0"},
        "user_id": USER_ID,
    }
    for i, turn in enumerate(conv["transcript"]):
        turn.update({"feedback": None, "llm_override": None, "source_medium": "audio",
                     "conversation_turn_metrics": {"metrics": {"llm_ttfb": {"elapsed_time": 0.4}}},
                     "rag_retrieval_info": None, "llm_usage": {"model_usage": {}}})
        for call in turn.get("tool_calls") or []:
            params = json.loads(call["params_as_json"])
            params.update({"checkin_id": CHECKIN_ID, "conversation_id": CONV_ID, "caller_phone": CALLER,
                           "extra": {"nested": DYN_NAME}})
            call["params_as_json"] = json.dumps(params, ensure_ascii=False)
            call["request_id"] = f"req_fixture_{i}"
            call["tool_details"] = {"type": "webhook", "url": "https://bv-live.example/agent/tools/x",
                                    "headers": {"X-BV-Tool-Secret": "fixture-not-a-secret"}}
    tr = conv["transcript"]
    # A tool result block, a system tool, a client tool that was never called, and the end_call system tool.
    tr.insert(3, {"role": "agent", "message": None, "time_in_call_secs": 10,
                  "tool_results": [{"request_id": "req_fixture_2", "tool_name": "record_answer",
                                    "result_value": json.dumps({"ok": True, "next": {"say": "fixture"}, "checkin": CHECKIN_ID}),
                                    "is_error": False, "tool_latency_secs": 0.4, "type": "webhook"}]})
    tr.insert(5, {"role": "agent", "message": None, "time_in_call_secs": 30,
                  "tool_calls": [{"request_id": "req_skip", "tool_name": "skip_turn", "params_as_json": "{}",
                                  "tool_has_been_called": True, "type": "system"},
                                 {"request_id": "req_never", "tool_name": "record_answer",
                                  "params_as_json": json.dumps({"item_code": "NEVER_CALLED", "verbatim_quote": "x"}),
                                  "tool_has_been_called": False, "type": "webhook"}]})
    tr.append({"role": "agent", "message": None, "time_in_call_secs": 158,
               "tool_calls": [{"request_id": "req_end", "tool_name": "end_call", "params_as_json": "{}",
                               "tool_has_been_called": True, "type": "system"}]})
    return conv


def checkin_detail() -> dict:
    """GET /api/checkins/{id}-shaped fixture (CheckInDetail) with fields the export must not copy."""
    return {
        "checkin": {"id": CHECKIN_ID, "patient_id": "pat_rosa", "status": "completed", "channel": "web",
                    "language": "es", "pace": "extra_time", "agent_variant": "es-extra_time", "day_after_dose": 3,
                    "started_at": "2026-10-11T02:30:01Z", "el_conversation_id": CONV_ID,
                    "summary_en": SUMMARY, "termination_reason": "Client disconnected: fixture"},
        "patient": {"id": "pat_rosa", "subject_id": USER_ID, "name": DYN_NAME, "phone_e164": PATIENT_PHONE},
        "answers": [{"id": "ans_fixture", "verbatim_quote": "fixture"}],
        "findings": [], "drafts": [], "transcript": [{"role": "user", "text": SUMMARY}],
        "escalations": [
            {"id": "esc_fixture_low", "level": "routine", "acknowledged_at": "2026-10-11T02:30:30Z",
             "acknowledged_by": NURSE, "ack_method": "dashboard"},
            {"id": "esc_fixture", "level": "urgent", "status": "acknowledged", "created_at": "2026-10-11T02:31:31Z",
             "paged_at": "2026-10-11T02:31:31Z", "acknowledged_at": ACK_AT, "acknowledged_by": NURSE,
             "ack_method": "push_button", "page_target_name": NURSE, "summary_en": SUMMARY},
        ],
    }


# Strings that must not appear anywhere in an exported file.
FORBIDDEN = [AGENT_ID, CONV_ID, CHECKIN_ID, USER_ID, CALL_SID, CALLER, PATIENT_PHONE, NURSE, SUMMARY, DYN_NAME,
             "req_fixture", "fixture-not-a-secret", "bv-live.example", "agtbrch_fixture", "btcal_fixture",
             "fixture override", "Client disconnected", "NEVER_CALLED", "skip_turn", "esc_fixture", "ans_fixture"]


def all_keys_ok(doc: dict, bodies: dict[str, set[str]]) -> list[str]:
    bad = [f"$.{k}" for k in doc if k not in TOP_LEVEL]
    for i, ev in enumerate(doc["events"]):
        bad += [f"events[{i}].{k}" for k in ev if k not in EVENT_KEYS[ev["type"]]]
        if ev["type"] == "tool":
            bad += [f"events[{i}].body.{k}" for k in ev["body"] if k not in bodies[ev["tool"]]]
            bad += [f"events[{i}].body.{k}: nested" for k, v in ev["body"].items() if isinstance(v, dict | list)]
        if ev["type"] == "post_call":
            for j, turn in enumerate(ev["transcript"]):
                bad += [f"events[{i}].transcript[{j}].{k}" for k in turn if k not in TURN_KEYS]
    return bad


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.conv = conversation()
        cls.doc, cls.warnings = ex.build_scenario(cls.conv, checkin_detail(), scenario_id="rec_test",
                                                  title="Test export", tz_name=TZ)
        cls.text = json.dumps(cls.doc, ensure_ascii=False)
        cls.events = cls.doc["events"]

    def test_no_key_outside_the_whitelist(self) -> None:
        self.assertEqual(all_keys_ok(self.doc, tool_body_whitelist()), [])
        self.assertEqual(ex.check_whitelist(self.doc, ex.tool_arg_whitelist()), [])

    def test_ids_truncated_to_last_4(self) -> None:
        self.assertEqual(self.doc["agent_id_suffix"], AGENT_ID[-4:])
        self.assertEqual(self.doc["conversation_id_suffix"], CONV_ID[-4:])
        self.assertEqual(len(self.doc["agent_id_suffix"]), 4)
        self.assertEqual(len(self.doc["conversation_id_suffix"]), 4)
        self.assertIn(f"...{CONV_ID[-4:]}", self.doc["_about"])

    def test_no_dropped_value_leaks(self) -> None:
        for s in FORBIDDEN:
            self.assertNotIn(s, self.text, s)

    def test_provenance(self) -> None:
        d = self.doc
        self.assertIs(d["recorded"], True)
        self.assertEqual(d["label"], LABEL)
        self.assertEqual(d["recorded_at"], "2026-10-10")  # the DISPLAY_TZ date, not the UTC date
        self.assertEqual((d["id"], d["title"], d["patient_id"], d["day_after_dose"]),
                         ("rec_test", "Test export", "pat_rosa", 3))
        self.assertIn("consent", d["_about"].lower())
        self.assertNotIn("audio", d)

    def test_tool_calls_with_seconds_from_call_start(self) -> None:
        expected = []
        for turn in json.loads(FIXTURE.read_text(encoding="utf-8"))["data"]["transcript"]:
            for call in turn.get("tool_calls") or []:
                expected.append((float(turn["time_in_call_secs"]), call["tool_name"], json.loads(call["params_as_json"])))
        got = [(e["t"], e["tool"], e["body"]) for e in self.events if e["type"] == "tool"]
        self.assertEqual(got, expected)  # arguments kept exactly; IDs, stray and nested arguments dropped
        self.assertTrue(any("dropped arguments ['caller_phone', 'extra']" in w for w in self.warnings), self.warnings)

    def test_page_ack_end_and_transcript(self) -> None:
        ack = [e for e in self.events if e["type"] == "page_ack"]
        self.assertEqual(ack, [{"t": 125.0, "type": "page_ack", "by": "RN on call", "method": "push_button"}])
        ended = next(e for e in self.events if e["type"] == "call_ended")
        self.assertEqual(ended, {"t": 160.0, "type": "call_ended", "termination_reason": "end_call tool was called."})
        post = self.events[-1]
        self.assertEqual(post["type"], "post_call")
        self.assertEqual(post["t"], 160.0)
        spoken = [t for t in self.conv["transcript"] if t.get("message")]
        self.assertEqual([(t["role"], t["text"], t["t_s"]) for t in post["transcript"]],
                         [(t["role"], t["message"].strip(), float(t["time_in_call_secs"])) for t in spoken])
        self.assertEqual(self.events[0], {"t": 0.0, "type": "call_started"})
        ts = [e["t"] for e in self.events]
        self.assertEqual(ts, sorted(ts))

    def test_whitelist_check_catches_extra_keys(self) -> None:
        tools = ex.tool_arg_whitelist()
        for mutate, where in [
            (lambda d: d.__setitem__("user_id", USER_ID), "$.user_id"),
            (lambda d: d.__setitem__("agent_id_suffix", AGENT_ID), "$.agent_id_suffix"),
            (lambda d: d["events"][1]["body"].__setitem__("checkin_id", CHECKIN_ID), "body.checkin_id"),
            (lambda d: d["events"][1].__setitem__("request_id", "x"), "request_id"),
            (lambda d: d["events"][-1]["transcript"][0].__setitem__("interrupted", False), "interrupted"),
            (lambda d: d["events"].append({"t": 1, "type": "analysis"}), "unknown event"),
            (lambda d: next(e for e in d["events"] if e["type"] == "page_ack").__setitem__("by", NURSE), ".by"),
            (lambda d: d.__setitem__("metadata", {"phone_call": CALLER}), "$.metadata"),
        ]:
            d = copy.deepcopy(self.doc)
            mutate(d)
            bad = ex.check_whitelist(d, tools)
            self.assertTrue(any(where in b for b in bad), (where, bad))

    def test_ack_method_outside_the_known_set_is_dropped(self) -> None:
        detail = checkin_detail()
        detail["escalations"][1]["ack_method"] = f"sms from {CALLER}"
        doc, _ = ex.build_scenario(self.conv, detail, scenario_id="rec_test", tz_name=TZ)
        ack = next(e for e in doc["events"] if e["type"] == "page_ack")
        self.assertEqual(ack, {"t": 125.0, "type": "page_ack", "by": "RN on call"})

    def test_long_numbers_are_flagged_for_review(self) -> None:
        conv = copy.deepcopy(self.conv)
        conv["transcript"][1]["message"] = "Mi número es 555 555 0142."
        _, warnings = ex.build_scenario(conv, checkin_detail(), scenario_id="rec_test", tz_name=TZ)
        self.assertTrue(any("transcript turn 1" in w and "long number" in w for w in warnings), warnings)
        self.assertFalse(any("555" in w for w in warnings))  # the warning names the turn, never the number

    def test_link_check(self) -> None:
        detail = checkin_detail()["checkin"]
        self.assertEqual(ex.check_link(self.conv, detail, CONV_ID, CHECKIN_ID), [])
        other = dict(detail, el_conversation_id="conv_someothercall9999")
        problems = ex.check_link(self.conv, other, CONV_ID, CHECKIN_ID)
        self.assertTrue(problems and all(CONV_ID not in p and "conv_someothercall9999" not in p for p in problems))
        self.assertTrue(ex.check_link(self.conv, detail, CONV_ID, "ci_other"))
        self.assertTrue(ex.check_link(dict(self.conv, status="processing"), detail, CONV_ID, CHECKIN_ID))


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "conv.json").write_text(json.dumps(conversation(), ensure_ascii=False), encoding="utf-8")
        (self.tmp / "ci.json").write_text(json.dumps(checkin_detail(), ensure_ascii=False), encoding="utf-8")
        self.out = self.tmp / "scenarios"
        patcher = mock.patch.dict(os.environ, {"DISPLAY_TZ": TZ, "ELEVENLABS_API_KEY": "fixture-key-not-real",
                                               "LIVE_API": "https://bv-live.example", "BV_DASHBOARD_TOKEN": "tok"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, *args: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ex.main(["--conversation-id", CONV_ID, "--checkin-id", CHECKIN_ID, "--out-dir", str(self.out), *args])
        return code, out.getvalue() + err.getvalue()

    def offline(self, *args: str) -> tuple[int, str]:
        return self.run_main("--conversation-file", str(self.tmp / "conv.json"),
                             "--checkin-file", str(self.tmp / "ci.json"), *args)

    def test_writes_whitelisted_file_and_refuses_overwrite(self) -> None:
        code, out = self.offline("--id", "rec_cli")
        self.assertEqual(code, 0, out)
        path = self.out / "rec_cli.json"
        text = path.read_text(encoding="utf-8")
        doc = json.loads(text)
        self.assertEqual(all_keys_ok(doc, tool_body_whitelist()), [])
        for s in FORBIDDEN:
            self.assertNotIn(s, text, s)
            self.assertNotIn(s, out, s)  # nothing dropped is printed either
        self.assertEqual(doc["recorded_at"], "2026-10-10")
        self.assertIn("BEFORE COMMITTING", out)
        self.assertEqual(self.offline("--id", "rec_cli")[0], 1)  # exists
        self.assertEqual(self.offline("--id", "rec_cli", "--force", "--recorded-at", "2026-10-11")[0], 0)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["recorded_at"], "2026-10-11")

    def test_post_call_webhook_body_is_accepted(self) -> None:
        (self.tmp / "conv.json").write_text(json.dumps({"type": "post_call_transcription", "data": conversation()}))
        code, out = self.offline("--id", "rec_webhook_body")
        self.assertEqual(code, 0, out)

    def test_rejects_bad_ids_and_unlinked_calls(self) -> None:
        for bad in ("../escape", "a/b", "with space", ""):
            code, _ = self.offline("--id", bad)
            self.assertEqual(code, 1, bad)
        detail = checkin_detail()
        detail["checkin"]["el_conversation_id"] = "conv_someothercall9999"
        (self.tmp / "ci.json").write_text(json.dumps(detail))
        code, out = self.offline("--id", "rec_unlinked")
        self.assertEqual(code, 1)
        self.assertIn("do not match", out)
        self.assertFalse((self.out / "rec_unlinked.json").exists())
        self.assertEqual(self.offline("--id", "rec_unlinked", "--skip-link-check")[0], 0)
        self.assertEqual(list(self.out.glob("*.json")), [self.out / "rec_unlinked.json"])

    def test_network_path_and_audio(self) -> None:
        """The API reads (faked) and --audio: the mp3 lands in <out>/audio/, the JSON only points at it."""
        calls: list[tuple[str, dict[str, str], bool]] = []
        mp3 = b"ID3\x04\x00fixture-audio"

        def fake_get(url: str, headers: dict[str, str], *, binary: bool = False):  # noqa: ANN202
            calls.append((url, headers, binary))
            if url.endswith(f"/v1/convai/conversations/{CONV_ID}"):
                return conversation()
            if url.endswith(f"/v1/convai/conversations/{CONV_ID}/audio"):
                return mp3
            if url == f"https://bv-live.example/api/checkins/{CHECKIN_ID}":
                return checkin_detail()
            raise AssertionError(url)

        with mock.patch.object(ex, "http_get", fake_get):
            code, out = self.run_main("--id", "rec_net", "--audio")
        self.assertEqual(code, 0, out)
        self.assertEqual(calls[0], (f"{ex.API_BASE}/v1/convai/conversations/{CONV_ID}",
                                    {"xi-api-key": "fixture-key-not-real"}, False))
        self.assertEqual(calls[1], (f"https://bv-live.example/api/checkins/{CHECKIN_ID}", {"X-BV-Token": "tok"}, False))
        self.assertEqual(calls[2][0], f"{ex.API_BASE}/v1/convai/conversations/{CONV_ID}/audio")
        self.assertEqual((self.out / "audio" / "rec_net.mp3").read_bytes(), mp3)
        doc = json.loads((self.out / "rec_net.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["audio"], "scenarios/audio/rec_net.mp3")
        self.assertNotIn("fixture-key-not-real", out)

    def test_audio_refused_when_the_call_has_none(self) -> None:
        conv = conversation()
        conv["has_audio"] = False
        (self.tmp / "conv.json").write_text(json.dumps(conv))
        with mock.patch.object(ex, "http_get", side_effect=AssertionError("no network expected")):
            code, out = self.offline("--id", "rec_no_audio", "--audio")
        self.assertEqual(code, 1)
        self.assertIn("no audio", out)
        self.assertFalse((self.out / "rec_no_audio.json").exists())


class RepoTests(unittest.TestCase):
    def test_audio_dir_is_gitignored(self) -> None:
        """scenarios/audio/*.mp3 never reaches git; the exporter refuses a path git would track."""
        self.assertTrue(ex.audio_is_gitignored(ROOT / "scenarios" / "audio" / "rec_any.mp3"))
        self.assertFalse(ex.audio_is_gitignored(ROOT / "scenarios" / "rec_any.mp3"))

    def test_label_matches_backend(self) -> None:
        replay_py = (ROOT / "backend" / "app" / "services" / "replay.py").read_text(encoding="utf-8")
        self.assertIn(f'RECORDED_LABEL = "{ex.RECORDED_LABEL}"', replay_py)
        self.assertEqual(ex.RECORDED_LABEL, LABEL)
        self.assertIn(ex.SCENARIO_ID.pattern, replay_py)

    def test_recorded_scenarios_in_git_are_whitelisted(self) -> None:
        """Every committed recorded scenario passes the same whitelist and carries only 4-character ID suffixes."""
        bodies = tool_body_whitelist()
        for path in sorted((ROOT / "scenarios").glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("recorded") is not True:
                continue
            with self.subTest(scenario=path.name):
                self.assertEqual(all_keys_ok(doc, bodies), [])
                self.assertEqual(ex.check_whitelist(doc, ex.tool_arg_whitelist()), [])
                self.assertEqual(doc["label"], LABEL)
                date.fromisoformat(doc["recorded_at"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
