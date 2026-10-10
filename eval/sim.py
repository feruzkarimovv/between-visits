"""LLM plumbing for the evaluation: simulated agent, simulated patient, judges. Claude or Gemini.

The simulated agent always uses the SAME model as the real ElevenLabs agent (ELEVENLABS_LLM, else
agent/variants.json `llm`), so the report card describes what patients actually talk to: a `claude-*` agent
LLM runs on the Anthropic API, a `gemini-*` one on the Gemini API. The patient and the judges run on Claude
when ANTHROPIC_API_KEY is set (CLAUDE_MODEL_FAST / CLAUDE_MODEL_LONG), else on Gemini.
"""

import json
import os
import random
import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

ToolExec = Callable[[str, dict[str, Any]], dict[str, Any]]
Event = tuple  # ("text", str) | ("tool", name, args, result) | ("end",)
MAX_INNER = 8


class QuotaExhausted(SystemExit):
    pass


def agent_llm(variants: dict[str, Any]) -> str:
    return os.environ.get("ELEVENLABS_LLM") or variants["llm"]


def tool_schemas(sources: Any, pace: str) -> list[dict[str, Any]]:
    """The agent's tools as plain JSON schemas, minus the properties ElevenLabs injects from dynamic variables."""
    out = []
    for t in sources.tool_configs("https://eval.invalid", "eval-secret"):
        schema = t["api_schema"]["request_body_schema"]
        props = {k: {kk: vv for kk, vv in v.items() if kk in ("type", "description", "enum")}
                 for k, v in schema["properties"].items() if "dynamic_variable" not in v}
        out.append({"name": t["name"], "description": t["description"],
                    "schema": {"type": "object", "properties": props,
                               "required": [r for r in schema.get("required", []) if r in props]}})
    out.append({"name": "end_call", "description": "End the call after saying the closing line.",
                "schema": {"type": "object", "properties": {}}})
    if pace == "extra_time":
        out.append({"name": "skip_turn", "description": "Stay quiet and keep listening while the person thinks.",
                    "schema": {"type": "object", "properties": {}}})
    return out


# ---- Claude -------------------------------------------------------------------------------------------


def _anthropic():  # noqa: ANN202
    import anthropic

    return anthropic.Anthropic(api_key=_settings().anthropic_api_key or None, max_retries=6)


class ClaudeAgent:
    def __init__(self, model: str, system: str, first_message: str, tools: list[dict[str, Any]]):
        self.client, self.model, self.system = _anthropic(), model, system
        self.tools = [{"name": t["name"], "description": t["description"], "input_schema": t["schema"]} for t in tools]
        self.messages: list[dict[str, Any]] = [
            {"role": "user", "content": "[The phone call has connected.]"},
            {"role": "assistant", "content": first_message},
        ]

    def turn(self, user_text: str, run_tool: ToolExec) -> list[Event]:
        events: list[Event] = []
        self.messages.append({"role": "user", "content": user_text})
        for _ in range(MAX_INNER):
            # low effort approximates a latency-tuned voice agent; the ElevenLabs agent runs without a long think
            resp = self.client.messages.create(model=self.model, max_tokens=4000, system=self.system,
                                               tools=self.tools, messages=self.messages,
                                               output_config={"effort": "low"})
            self.messages.append({"role": "assistant", "content": resp.content})
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            if text:
                events.append(("text", text))
            calls = [b for b in resp.content if b.type == "tool_use"]
            if not calls:
                break
            results = []
            ended = False
            for c in calls:
                if c.name == "end_call":
                    ended = True
                    events.append(("end",))
                    res: dict[str, Any] = {"ok": True}
                elif c.name == "skip_turn":
                    res = {"ok": True}
                else:
                    res = run_tool(c.name, dict(c.input))
                    events.append(("tool", c.name, dict(c.input), res))
                results.append({"type": "tool_result", "tool_use_id": c.id, "content": json.dumps(res, ensure_ascii=False)})
            self.messages.append({"role": "user", "content": results})
            if ended:
                break
        return events


def claude_text(model: str, prompt: str, effort: str = "low") -> str:
    resp = _anthropic().messages.create(model=model, max_tokens=4000, output_config={"effort": effort},
                                        messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in resp.content if b.type == "text").strip()


class _Verdict(BaseModel):
    passed: bool
    evidence: str


def claude_judge(model: str, prompt: str) -> dict[str, Any]:
    resp = _anthropic().messages.parse(model=model, max_tokens=4000, output_config={"effort": "medium"},
                                       messages=[{"role": "user", "content": prompt}], output_format=_Verdict)
    v = resp.parsed_output
    return {"pass": None, "evidence": "judge output invalid"} if v is None else {"pass": v.passed, "evidence": v.evidence}


# ---- Gemini -------------------------------------------------------------------------------------------


def _gemini_retry(fn: Callable, *a: Any, **kw: Any) -> Any:
    from google.genai import errors as genai_errors

    delay = 2.0
    for attempt in range(7):
        try:
            return fn(*a, **kw)
        except genai_errors.APIError as e:
            if "PerDay" in str(e) or "free_tier" in str(e):
                raise QuotaExhausted(f"Gemini daily/free-tier quota exhausted.\n{str(e)[:300]}") from e
            if getattr(e, "code", None) in (429, 500, 503) and attempt < 6:
                time.sleep(delay + random.random())
                delay = min(delay * 2, 60)
                continue
            raise
    raise RuntimeError("unreachable")


def _genai():  # noqa: ANN202
    from google import genai

    return genai.Client(api_key=os.environ.get("GEMINI_API_KEY") or _settings().gemini_api_key)


def _settings():  # noqa: ANN202
    from app.config import get_settings

    return get_settings()


class GeminiAgent:
    def __init__(self, model: str, system: str, first_message: str, tools: list[dict[str, Any]]):
        from google.genai import types

        self.types, self.client, self.model = types, _genai(), model
        decls = [types.FunctionDeclaration(name=t["name"], description=t["description"], parameters_json_schema=t["schema"])
                 for t in tools]
        self.cfg = types.GenerateContentConfig(
            system_instruction=system, tools=[types.Tool(function_declarations=decls)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        self.contents = [types.Content(role="user", parts=[types.Part(text="[The phone call has connected.]")]),
                         types.Content(role="model", parts=[types.Part(text=first_message)])]

    def turn(self, user_text: str, run_tool: ToolExec) -> list[Event]:
        types = self.types
        events: list[Event] = []
        self.contents.append(types.Content(role="user", parts=[types.Part(text=user_text)]))
        for _ in range(MAX_INNER):
            resp = _gemini_retry(self.client.models.generate_content, model=self.model, contents=self.contents, config=self.cfg)
            cand = resp.candidates[0].content if resp.candidates else None
            if cand is None:
                break
            self.contents.append(cand)
            text = "".join(p.text or "" for p in (cand.parts or []) if getattr(p, "text", None) and not getattr(p, "thought", False)).strip()
            if text:
                events.append(("text", text))
            calls = resp.function_calls or []
            if not calls:
                break
            parts, ended = [], False
            for fc in calls:
                args = dict(fc.args or {})
                if fc.name == "end_call":
                    ended = True
                    events.append(("end",))
                    res: dict[str, Any] = {"ok": True}
                elif fc.name == "skip_turn":
                    res = {"ok": True}
                else:
                    res = run_tool(fc.name, args)
                    events.append(("tool", fc.name, args, res))
                parts.append(types.Part.from_function_response(name=fc.name, response=res))
            self.contents.append(types.Content(role="user", parts=parts))
            if ended:
                break
        return events


def gemini_text(model: str, prompt: str) -> str:
    r = _gemini_retry(_genai().models.generate_content, model=model, contents=prompt)
    return (r.text or "").strip()


def gemini_judge(model: str, prompt: str) -> dict[str, Any]:
    from google.genai import types

    r = _gemini_retry(_genai().models.generate_content, model=model, contents=prompt,
                      config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=_Verdict))
    v = r.parsed
    return {"pass": None, "evidence": "judge output invalid"} if v is None else {"pass": v.passed, "evidence": v.evidence}


# ---- selection ----------------------------------------------------------------------------------------


def make_agent(model: str, system: str, first_message: str, tools: list[dict[str, Any]]) -> Any:
    if model.startswith("claude"):
        return ClaudeAgent(model, system, first_message, tools)
    return GeminiAgent(model, system, first_message, tools)


def helper_provider() -> str:
    s = _settings()
    return "anthropic" if s.anthropic_api_key else ("gemini" if s.gemini_api_key else "none")


def patient_text(prompt: str) -> str:
    s = _settings()
    if helper_provider() == "anthropic":
        return claude_text(s.claude_model_fast, prompt)
    return gemini_text(s.gemini_model_fast, prompt)


def judge(prompt: str) -> dict[str, Any]:
    s = _settings()
    if helper_provider() == "anthropic":
        return claude_judge(s.claude_model_long, prompt)
    return gemini_judge(s.gemini_model_long, prompt)


def models_used(agent_model: str) -> dict[str, str]:
    s = _settings()
    if helper_provider() == "anthropic":
        return {"agent": agent_model, "patient": s.claude_model_fast, "judge": s.claude_model_long}
    return {"agent": agent_model, "patient": s.gemini_model_fast, "judge": s.gemini_model_long}
