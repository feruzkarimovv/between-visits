"""Offline checks for agent/sync_agent.py rendering and the deployed-config snapshot (no network, no API key).

Run: python3 agent/test_sync_agent.py   (or: uv run --project backend python agent/test_sync_agent.py)
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_config_hash as chk  # noqa: E402
import sync_agent as sa  # noqa: E402

BASE = "https://example.ngrok-free.app"


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.src = sa.Sources()
        cls.tools = cls.src.tool_configs(BASE, "sec_test")
        cls.tool_ids = [f"tool_{t['name']}" for t in cls.tools]
        cls.agents = {
            v: cls.src.agent_config(
                v, tool_ids=cls.tool_ids, voice_id="voice_test", inbound=(v == "es-extra_time")
            )
            for v in cls.src.variants["variants"]
        }

    def test_four_variants(self) -> None:
        self.assertEqual(
            sorted(self.agents), ["en-extra_time", "en-standard", "es-extra_time", "es-standard"]
        )

    def test_no_sync_placeholders_left(self) -> None:
        blob = json.dumps([self.tools, self.agents], ensure_ascii=False)
        self.assertNotIn("${", blob)
        self.assertNotIn('"_about"', blob)

    def test_tools(self) -> None:
        self.assertEqual(len(self.tools), 5)
        for t in self.tools:
            self.assertTrue(t["api_schema"]["url"].startswith(f"{BASE}/agent/tools/"))
            self.assertEqual(
                t["api_schema"]["request_headers"]["X-BV-Tool-Secret"], {"secret_id": "sec_test"}
            )
            self.assertEqual(t["tool_error_handling_mode"], "passthrough")
        rf = next(t for t in self.tools if t["name"] == "report_red_flag")
        enum = rf["api_schema"]["request_body_schema"]["properties"]["red_flag_id"]["enum"]
        self.assertEqual(enum, self.src.plan["red_flag_ids"])

    def test_agent_types_and_runtime_vars(self) -> None:
        for v, cfg in self.agents.items():
            agent = cfg["conversation_config"]["agent"]
            prompt = agent["prompt"]
            self.assertEqual(cfg["name"], f"between-visits-{v}")
            self.assertEqual(prompt["tool_ids"], self.tool_ids)
            self.assertIsInstance(prompt["backup_llm_config"]["order"], list)
            self.assertIsInstance(cfg["conversation_config"]["turn"], dict)
            self.assertIsInstance(cfg["conversation_config"]["tts"]["speed"], float)
            self.assertIsInstance(cfg["conversation_config"]["conversation"]["max_duration_seconds"], int)
            self.assertTrue(cfg["conversation_config"]["tts"]["model_id"])
            self.assertIn("{{patient_first_name}}", agent["first_message"])
            self.assertIn("{{study_team_name}}", agent["first_message"])
            self.assertNotRegex(agent["first_message"], r"(?<!\{)\{[a-z_]+\}(?!\})")
            vm = prompt["built_in_tools"]["voicemail_detection"]["params"]["voicemail_message"]
            self.assertIn("{{patient_first_name}}", vm)
            for var in ("patient_first_name", "pace_instructions", "language_name", "caregiver_name"):
                self.assertIn("{{" + var + "}}", prompt["prompt"])
            for rf_id in self.src.plan["red_flag_ids"]:
                self.assertIn(f"- {rf_id}: ", prompt["prompt"])
            self.assertIn("end_call", prompt["built_in_tools"])
            self.assertEqual("skip_turn" in prompt["built_in_tools"], v.endswith("extra_time"))

    def test_inbound_overrides(self) -> None:
        ov = self.agents["es-extra_time"]["platform_settings"]["overrides"]
        self.assertTrue(ov[sa.INBOUND_FLAG])
        self.assertTrue(ov["conversation_config_override"]["agent"]["first_message"])
        self.assertFalse(self.agents["en-standard"]["platform_settings"]["overrides"][sa.INBOUND_FLAG])
        none = self.src.agent_config("en-standard", tool_ids=[], voice_id="v", inbound=None)
        self.assertNotIn("overrides", none["platform_settings"])

    def test_render_typed_and_embedded(self) -> None:
        out = sa.render({"a": "${X}", "b": "pre ${Y} post", "_c": 1}, {"X": [1, 2], "Y": 3})
        self.assertEqual(out, {"a": [1, 2], "b": "pre 3 post"})
        with self.assertRaises(sa.SyncError):
            sa.render("pre ${X}", {"X": [1]})
        with self.assertRaises(sa.SyncError):
            sa.render("${MISSING}", {})

    def test_runtime_vars(self) -> None:
        self.assertEqual(sa.to_runtime_vars("Hi {a}, {{b}}"), "Hi {{a}}, {{b}}")


# ---------------------------------------------------------------- deployed snapshot (V9), offline

ROOT = Path(__file__).resolve().parent.parent
LIVE_BASE = "https://bv-live-api.example.invalid"
SECRET_ID = "secFAKE0secret0id0000"
VOICE_ID = "voiceFAKE0000000000000"


def _floats(node: object) -> object:
    """The API reads integral numbers back as floats (temperature 0 -> 0.0, turn_timeout 8 -> 8.0)."""
    if isinstance(node, dict):
        return {k: _floats(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_floats(v) for v in node]
    if isinstance(node, int) and not isinstance(node, bool):
        return float(node)
    return node


class FakeApi:
    """Read-only ElevenLabs stand-in that returns the read-back shape seen on Oct 11 2026: server-added
    fields, integral numbers as floats, real-looking IDs, tool URLs and secret IDs. It has no post/patch:
    a write would raise AttributeError."""

    def __init__(self, src: sa.Sources, *, inbound_variant: str | None = "es-extra_time") -> None:
        self.calls: list[str] = []
        sent_tools = src.tool_configs(LIVE_BASE, SECRET_ID)
        self.tool_ids = {t["name"]: f"tool_{i:02d}FAKE0000000000000000" for i, t in enumerate(sent_tools)}
        self.tools: dict[str, dict] = {}
        for t in sent_tools:
            cfg = _floats(copy.deepcopy(t))
            cfg.update({"execution_mode": "immediate", "assignments": [], "tool_call_sound": None})
            cfg["api_schema"].update({"content_type": "application/json", "query_params_schema": None})
            for prop in cfg["api_schema"]["request_body_schema"]["properties"].values():
                prop.update({"is_system_provided": False, "constant_value": "", "enum": prop.get("enum")})
            tid = self.tool_ids[t["name"]]
            self.tools[tid] = {"id": tid, "tool_config": cfg, "usage_stats": {"total_calls": 3}}
        self.agent_ids: dict[str, str] = {}
        self.agents: dict[str, dict] = {}
        for i, variant in enumerate(src.variants["variants"]):
            agent_id = f"agent_{i}FAKE00000000000000000000x{i}y{i}"
            self.agent_ids[variant] = agent_id
            inbound = None if inbound_variant is None else variant == inbound_variant
            sent = src.agent_config(
                variant, tool_ids=list(self.tool_ids.values()), voice_id=VOICE_ID, inbound=inbound
            )
            back = _floats(copy.deepcopy(sent))
            back.update({"agent_id": agent_id, "metadata": {"created_at_unix_secs": 1791669527}, "version_id": None})
            cc = back["conversation_config"]
            cc["tts"].update({"optimize_streaming_latency": 3, "agent_output_audio_format": "pcm_16000"})
            cc["turn"].update({"turn_model": "turn_v3", "soft_timeout_config": {"timeout_seconds": -1.0}})
            cc["vad"] = {"background_voice_detection": False}
            prompt = cc["agent"]["prompt"]
            prompt.update({"reasoning_effort": None, "max_tokens": -1, "mcp_server_ids": []})
            prompt["tools"] = [self.tools[tid]["tool_config"] for tid in prompt["tool_ids"]]
            for tool in prompt["built_in_tools"].values():
                tool.update({"response_timeout_secs": 20, "disable_interruptions": False})
            prompt["built_in_tools"]["transfer_to_number"] = None
            for c in back["platform_settings"]["evaluation"]["criteria"]:
                c.update({"scope": "conversation", "llm": None})
            back["platform_settings"]["widget"] = {"variant": "full", "bg_color": "#ffffff"}
            back["platform_settings"].setdefault("overrides", {})["enable_conversation_overrides"] = True
            self.agents[agent_id] = back

    def get(self, path: str, **params: object) -> dict:
        self.calls.append(path)
        kind, _, item = path.removeprefix("/v1/convai/").partition("/")
        store = {"agents": self.agents, "tools": self.tools}[kind]
        return copy.deepcopy(store[item])

    def back(self, variant: str) -> dict:
        return self.agents[self.agent_ids[variant]]


class SnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        saved = {k: os.environ.pop(k) for k in (*chk.OVERRIDE_ENV, "AGENTS_LOCK_JSON") if k in os.environ}
        self.addCleanup(os.environ.update, saved)
        self.src = sa.Sources()
        self.api = FakeApi(self.src)
        self.rendered = chk.rendered_fingerprints(self.src)
        self.evaluated = sa.evaluated_agent_llm()

    def snap(self, **kw: object) -> dict:
        snap, _ = sa.take_snapshot(self.api, self.src, self.api.agent_ids, captured_at="2026-10-11T07:00:00Z", **kw)
        return snap

    def test_shape_matches_docs_02(self) -> None:
        snap = self.snap()
        self.assertEqual(list(snap), ["captured_at", "variants"])
        self.assertEqual(list(snap["variants"]), list(self.src.variants["variants"]))
        for variant, entry in snap["variants"].items():
            self.assertEqual(
                list(entry),
                ["agent_id_suffix", "llm", "backup_llms", "tts_model", "prompt_sha256", "tools_sha256", "config_sha256"],
            )
            self.assertEqual(entry["agent_id_suffix"], self.api.agent_ids[variant][-4:])
            for field in chk.HASH_FIELDS:
                self.assertRegex(entry[field], r"^[0-9a-f]{64}$")
        self.assertEqual(
            snap["variants"]["es-standard"]["tts_model"], self.src.variants["tts_model_by_language"]["es"]
        )
        self.assertEqual(self.snap(llm_note="differs from evaluated model: test")["llm_note"],
                         "differs from evaluated model: test")

    def test_read_only_get_calls(self) -> None:
        self.snap()
        self.assertTrue(self.api.calls)
        self.assertTrue(all(c.startswith(("/v1/convai/agents/", "/v1/convai/tools/")) for c in self.api.calls))
        self.assertEqual(len([c for c in self.api.calls if "/tools/" in c]), 5)  # tools read once, cached
        self.assertFalse(hasattr(sa.ReadOnlyApi(None), "patch"))  # type: ignore[arg-type]

    def test_no_ids_urls_or_secrets_in_snapshot(self) -> None:
        blob = json.dumps(self.snap(), ensure_ascii=False)
        for value in [*self.api.agent_ids.values(), *self.api.tool_ids.values(), VOICE_ID, SECRET_ID, LIVE_BASE]:
            self.assertNotIn(value, blob)
            self.assertNotIn(value[:12], blob)
        self.assertNotIn("://", blob)

    def test_hashes_match_rendering_right_after_a_sync(self) -> None:
        snap = self.snap()
        for variant, want in self.rendered.items():
            self.assertEqual({k: snap["variants"][variant][k] for k in want}, want, variant)
        rows, problems = chk.compare(snap, self.rendered, self.evaluated)
        self.assertEqual(problems, [])
        self.assertEqual(len(rows), 1 + len(self.rendered))

    def test_inbound_wiring_does_not_change_hashes(self) -> None:
        without = sa.take_snapshot(FakeApi(self.src, inbound_variant=None), self.src, self.api.agent_ids)[0]
        with_inbound = self.snap()
        for variant in self.rendered:
            self.assertEqual(without["variants"][variant]["config_sha256"],
                             with_inbound["variants"][variant]["config_sha256"])

    def test_prompt_drift_is_reported(self) -> None:
        self.api.back("es-standard")["conversation_config"]["agent"]["prompt"]["prompt"] += "\nextra line"
        snap = self.snap()
        _, problems = chk.compare(snap, self.rendered, self.evaluated)
        self.assertEqual(
            sorted(p.split(" differs")[0] for p in problems),
            ["es-standard: config_sha256", "es-standard: prompt_sha256"],
        )

    def test_tool_drift_is_reported(self) -> None:
        tid = self.api.tool_ids["report_red_flag"]
        self.api.tools[tid]["tool_config"]["description"] += " (edited in the dashboard)"
        _, problems = chk.compare(self.snap(), self.rendered, self.evaluated)
        self.assertEqual(len(problems), 4)
        self.assertTrue(all(": tools_sha256 differs" in p for p in problems))

    def test_turn_setting_drift_is_reported(self) -> None:
        self.api.back("en-extra_time")["conversation_config"]["turn"]["turn_timeout"] = 9.0
        _, problems = chk.compare(self.snap(), self.rendered, self.evaluated)
        self.assertEqual(problems, [p for p in problems if p.startswith("en-extra_time: config_sha256 differs")])
        self.assertEqual(len(problems), 1)

    def test_llm_drift_needs_llm_note(self) -> None:
        for variant in self.rendered:
            self.api.back(variant)["conversation_config"]["agent"]["prompt"]["llm"] = "gemini-3.5-flash"
        snap = self.snap()
        self.assertEqual({e["llm"] for e in snap["variants"].values()}, {"gemini-3.5-flash"})
        _, problems = chk.compare(snap, self.rendered, self.evaluated)
        joined = "\n".join(problems)
        self.assertIn("en-standard: llm differs", joined)
        self.assertIn("en-standard: config_sha256 differs", joined)
        self.assertIn("is not the evaluated model", joined)
        self.assertEqual(len(chk.llm_problems(snap, self.evaluated)), 4)
        noted = self.snap(llm_note="differs from evaluated model: test")
        self.assertEqual(chk.llm_problems(noted, self.evaluated), [])
        self.assertEqual(len(chk.llm_problems(self.snap(), None)), 4)  # no evaluated model and no note

    def test_server_only_fields_do_not_matter(self) -> None:
        back = self.api.back("en-standard")
        back["conversation_config"]["tts"]["optimize_streaming_latency"] = 4
        back["platform_settings"]["widget"]["bg_color"] = "#000000"
        back["conversation_config"]["agent"]["prompt"]["tools"] = []
        _, problems = chk.compare(self.snap(), self.rendered, self.evaluated)
        self.assertEqual(problems, [])

    def test_unread_keys_are_warned(self) -> None:
        del self.api.back("en-standard")["conversation_config"]["agent"]["disable_first_message_interruptions"]
        snap, warnings = sa.take_snapshot(self.api, self.src, self.api.agent_ids)
        self.assertIn(
            "en-standard: sent but not read back: $.conversation_config.agent.disable_first_message_interruptions",
            warnings,
        )
        _, problems = chk.compare(snap, self.rendered, self.evaluated)
        self.assertEqual([p.split(" differs")[0] for p in problems], ["en-standard: config_sha256"])

    def test_missing_variant_and_long_suffix(self) -> None:
        snap = self.snap()
        del snap["variants"]["es-extra_time"]
        snap["variants"]["en-standard"]["agent_id_suffix"] = self.api.agent_ids["en-standard"]
        _, problems = chk.compare(snap, self.rendered, self.evaluated)
        self.assertIn("es-extra_time: missing from the snapshot", problems)
        self.assertIn("en-standard: agent_id_suffix must be the last 4 characters only", problems)

    def test_missing_agent_id_is_an_error(self) -> None:
        ids = dict(self.api.agent_ids)
        del ids["es-standard"]
        with self.assertRaises(sa.SyncError):
            sa.take_snapshot(self.api, self.src, ids)

    def test_dry_run_parity(self) -> None:
        """check_config_hash hashes exactly what `sync_agent.py --dry-run` prints."""
        args = argparse.Namespace(inbound=None, setup_webhook=False)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sa.dry_run(args, self.src, list(self.src.variants["variants"]))
        sections = out.getvalue().split("\n## ")
        tools = self._dry_run_tools(sections[1])
        self.assertEqual(len(tools), 5)
        agents = {s.split()[1]: json.loads(s.split("\n", 1)[1]) for s in sections[2:] if s.startswith("Agent ")}
        self.assertEqual(list(agents), list(self.rendered))
        for variant, cfg in agents.items():
            self.assertEqual(sa.config_fingerprint(cfg, tools), self.rendered[variant])

    @staticmethod
    def _dry_run_tools(section: str) -> list[dict]:
        body = section.split("\n", 1)[1]
        decoder, pos, tools = json.JSONDecoder(), 0, []
        while pos < len(body.rstrip()):
            obj, end = decoder.raw_decode(body, pos)
            tools.append(obj["tool_config"])
            pos = end + 1
        return tools


class NormalizationTests(unittest.TestCase):
    def test_canonical_numbers(self) -> None:
        self.assertEqual(sa.canonical_numbers({"a": 0.0, "b": 8.0, "c": 0.85, "d": True, "e": [1.0, 2]}),
                         {"a": 0, "b": 8, "c": 0.85, "d": True, "e": [1, 2]})
        self.assertIs(sa.canonical_numbers(True), True)
        self.assertEqual(sa.sha256_json({"t": 0}), sa.sha256_json(sa.canonical_numbers({"t": 0.0})))

    def test_strip_deployment_fields(self) -> None:
        cfg = {
            "conversation_config": {"tts": {"voice_id": "v", "model_id": "m"},
                                    "agent": {"prompt": {"tool_ids": ["a", "b"], "llm": "x"}}},
            "platform_settings": {"overrides": {"x": True}, "auth": {"enable_auth": True}},
            "api_schema": {"url": "https://h/agent/tools/x",
                           "request_headers": {"X-BV-Tool-Secret": {"secret_id": "s"}},
                           "request_body_schema": {"properties": {"url": {"type": "string"},
                                                                  "checkin_id": {"dynamic_variable": "checkin_id"}}}},
            "dynamic_variable_placeholders": {"checkin_id": "ci_test"},
        }
        self.assertEqual(sa.strip_deployment_fields(cfg), {
            "conversation_config": {"tts": {"model_id": "m"}, "agent": {"prompt": {"llm": "x"}}},
            "platform_settings": {"auth": {"enable_auth": True}},
            "api_schema": {"request_headers": {"X-BV-Tool-Secret": {}},
                           "request_body_schema": {"properties": {"url": {"type": "string"},
                                                                  "checkin_id": {"dynamic_variable": "checkin_id"}}}},
            "dynamic_variable_placeholders": {"checkin_id": "ci_test"},
        })

    def test_project_keeps_only_sent_keys(self) -> None:
        sent = {"a": 1, "b": {"c": [1, 2], "d": [{"e": 1}]}, "missing": 1}
        back = {"a": 1.0, "extra": 1, "b": {"c": [1, 2, 3], "d": [{"e": 1, "server": 2}], "x": None}}
        self.assertEqual(sa.project(sent, back), {"a": 1.0, "b": {"c": [1, 2, 3], "d": [{"e": 1}]}})
        self.assertEqual(sa.unread_keys(sent, back), ["$.missing"])

    def test_key_order_does_not_matter(self) -> None:
        self.assertEqual(sa.sha256_json({"a": 1, "b": {"c": 2, "d": 3}}),
                         sa.sha256_json({"b": {"d": 3, "c": 2}, "a": 1}))


class LockAndCheckMainTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        saved = {k: os.environ.pop(k) for k in (*chk.OVERRIDE_ENV, "AGENTS_LOCK_JSON") if k in os.environ}
        self.addCleanup(os.environ.update, saved)

    def run_check(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = chk.main(list(argv))
        return code, out.getvalue()

    def test_agent_ids_from_lock_file_or_env(self) -> None:
        lock = self.tmp / "agents.lock.json"
        lock.write_text('{"en-standard": "agent_lockfile"}')
        self.assertEqual(sa.read_agent_ids(lock), {"en-standard": "agent_lockfile"})
        absent = self.tmp / "absent.json"
        with self.assertRaisesRegex(sa.SyncError, "AGENTS_LOCK_JSON is empty"):
            sa.read_agent_ids(absent)
        os.environ["AGENTS_LOCK_JSON"] = '{"en-standard": "agent_fromenv"}'
        self.assertEqual(sa.read_agent_ids(absent), {"en-standard": "agent_fromenv"})
        os.environ["AGENTS_LOCK_JSON"] = "{not json agent_secretish"
        with self.assertRaises(sa.SyncError) as ctx:
            sa.read_agent_ids(absent)
        self.assertNotIn("agent_secretish", str(ctx.exception))
        del os.environ["AGENTS_LOCK_JSON"]

    def test_no_snapshot_exits_1(self) -> None:
        code, out = self.run_check("--snapshot", str(self.tmp / "deployed_snapshot.json"))
        self.assertEqual(code, 1)
        self.assertIn("no deployed snapshot yet: run make sync-agent ARGS=--snapshot", out)

    def test_check_passes_then_fails_with_readable_diff(self) -> None:
        src = sa.Sources()
        api = FakeApi(src)
        snap, _ = sa.take_snapshot(api, src, api.agent_ids)
        path = self.tmp / "deployed_snapshot.json"
        path.write_text(json.dumps(snap))
        os.environ["ELEVENLABS_LLM"] = "some-other-model"  # ignored: the check uses the committed config
        code, out = self.run_check("--snapshot", str(path))
        self.assertEqual(code, 0, out)
        self.assertIn("OK: the deployed config of all 4 variants matches the repo.", out)
        self.assertIn("ignoring ELEVENLABS_LLM", out)
        self.assertEqual(os.environ["ELEVENLABS_LLM"], "some-other-model")  # restored after rendering
        snap["variants"]["es-extra_time"]["tts_model"] = "eleven_flash_v2"
        snap["variants"]["es-extra_time"]["config_sha256"] = "0" * 64
        path.write_text(json.dumps(snap))
        code, out = self.run_check("--snapshot", str(path))
        self.assertEqual(code, 1)
        self.assertIn("es-extra_time: config_sha256 differs", out)
        self.assertIn('es-extra_time: tts_model differs: rendered "eleven_flash_v2_5", deployed "eleven_flash_v2"', out)
        self.assertIn("make sync-agent ARGS=--snapshot", out)
        path.write_text("[]")
        self.assertEqual(self.run_check("--snapshot", str(path))[0], 1)

    def test_pin_is_consistent(self) -> None:
        """variants.json llm = evaluated model = config.py default = .env.example (WS1 V9)."""
        pinned = sa.read_json(sa.AGENT_DIR / "variants.json")["llm"]
        self.assertEqual(pinned, sa.evaluated_agent_llm())
        config_py = (ROOT / "backend" / "app" / "config.py").read_text(encoding="utf-8")
        self.assertIn(f'elevenlabs_llm: str = "{pinned}"', config_py)
        env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn(f"\nELEVENLABS_LLM={pinned} ", env_example)
        rendered = sa.Sources().agent_config("en-standard", tool_ids=[], voice_id="v", inbound=None)
        prompt = rendered["conversation_config"]["agent"]["prompt"]
        self.assertEqual(prompt["llm"], pinned)
        self.assertEqual(prompt["backup_llm_config"]["order"], sa.read_json(sa.AGENT_DIR / "variants.json")["backup_llm_order_claude"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
