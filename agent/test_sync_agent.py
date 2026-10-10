"""Offline checks for agent/sync_agent.py rendering (no network, no API key).

Run: python3 agent/test_sync_agent.py   (or: uv run --project backend python agent/test_sync_agent.py)
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
