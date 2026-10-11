#!/usr/bin/env python3
"""Create or update the Between Visits ElevenLabs agents and tools (config as code).

Run from the repo root:

    uv run --project backend python agent/sync_agent.py [--dry-run] [--only VARIANT]
                                                        [--setup-webhook] [--inbound VARIANT]
    uv run --project backend python agent/sync_agent.py --snapshot [--llm-note TEXT]

What it does (exact API fields: docs/04-voice-agent.md):
  1. renders the system prompt from agent/prompt.md (${RED_FLAG_LIST} from data/red_flags.json);
  2. finds or creates the workspace secret `bv_tool_secret` (= TOOL_SHARED_SECRET);
  3. upserts the five webhook tools in agent/tools.json by name;
  4. upserts the four agent variants (agent/agent.template.json + agent/variants.json) by name,
     always sending the full config;
  5. writes agent/agents.lock.json {"en-standard": "agent_...", ...}.
  --setup-webhook  also creates/attaches the HMAC post-call workspace webhook.
  --inbound V      also points the inbound-init webhook and the imported phone number at variant V.
  --dry-run        prints everything that would be sent; no network, no API key needed.
  --snapshot       read-only (GET only, no other step runs): reads each deployed variant back by the IDs
                   in agent/agents.lock.json (or AGENTS_LOCK_JSON) and writes agent/deployed_snapshot.json
                   (docs/02): captured_at; per variant agent_id_suffix (last 4 characters), llm,
                   backup_llms, tts_model, prompt_sha256, tools_sha256, config_sha256. The hashes cover
                   only the keys the sync sends, read back, with IDs, URLs and secret references removed
                   (see normalized()); agent/check_config_hash.py recomputes them offline from git.

All `${...}` placeholders are filled here at sync time; all `{{...}}` are ElevenLabs runtime
dynamic variables and are left untouched. No clinical wording lives in this file: every
spoken or clinical string is read from data/.

Dependencies: httpx + stdlib (python-dotenv is used if importable, else a tiny .env parser).
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / "agent"
DATA_DIR = ROOT / "data"
LOCK_PATH = AGENT_DIR / "agents.lock.json"
SNAPSHOT_PATH = AGENT_DIR / "deployed_snapshot.json"
LATEST_EVAL_PATH = ROOT / "eval" / "results" / "latest.json"

API_BASE = "https://api.elevenlabs.io"
AGENT_NAME_PREFIX = "between-visits-"
AGENT_SEARCH = "between-visits"
SECRET_NAME = "bv_tool_secret"
WEBHOOK_NAME = "between-visits"
WEBHOOK_EVENTS = ["transcript", "call_initiation_failure", "audio"]
SKIP_TURN_WAIT_SECS = 20
INBOUND_FLAG = "enable_conversation_initiation_client_data_from_webhook"

PLACEHOLDER = re.compile(r"\$\{([A-Z0-9_]+)\}")
# `{name}` (single braces) in data/scripts.json -> ElevenLabs `{{name}}`; leaves `{{name}}` alone.
SINGLE_BRACE_VAR = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")


class SyncError(Exception):
    """A configuration or data problem; message is shown to the user."""


class ApiError(SyncError):
    def __init__(self, method: str, path: str, status: int, body: str) -> None:
        super().__init__(f"ElevenLabs API error: {method} {path} -> HTTP {status}\n{body}")
        self.status = status


# ---------------------------------------------------------------- env and files


def load_env() -> None:
    """Load <repo>/.env into os.environ without overriding variables already set."""
    path = ROOT / ".env"
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]

        load_dotenv(path, override=False)
        return
    except ImportError:
        pass
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value[:1] in ("'", '"') and value.count(value[0]) >= 2:
            value = value[1 : value.index(value[0], 1)]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        os.environ.setdefault(key, value)


def env(name: str) -> str:
    return os.environ.get(name, "").strip()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise SyncError(f"missing file: {path.relative_to(ROOT)}") from e
    except json.JSONDecodeError as e:
        raise SyncError(f"invalid JSON in {path.relative_to(ROOT)}: {e}") from e


# ---------------------------------------------------------------- rendering


def render(node: Any, values: dict[str, Any]) -> Any:
    """Fill ${NAME} placeholders by walking parsed JSON and drop keys starting with `_`.

    A string that is exactly "${NAME}" is replaced by the typed value (list, object, number...).
    Placeholders embedded in a longer string are substituted as text (scalars only).
    Substituted values are not re-scanned.
    """
    if isinstance(node, dict):
        return {k: render(v, values) for k, v in node.items() if not k.startswith("_")}
    if isinstance(node, list):
        return [render(v, values) for v in node]
    if isinstance(node, str):
        whole = PLACEHOLDER.fullmatch(node)
        if whole:
            return copy.deepcopy(_lookup(whole.group(1), values))

        def sub(m: re.Match[str]) -> str:
            value = _lookup(m.group(1), values)
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise SyncError(
                    f"placeholder ${{{m.group(1)}}} is embedded in a string but its value is not a scalar"
                )
            return str(value)

        return PLACEHOLDER.sub(sub, node)
    return node


def _lookup(name: str, values: dict[str, Any]) -> Any:
    if name not in values:
        raise SyncError(f"no value for placeholder ${{{name}}}")
    return values[name]


def find_leftover_placeholders(node: Any, path: str = "$") -> list[str]:
    if isinstance(node, dict):
        return [p for k, v in node.items() for p in find_leftover_placeholders(v, f"{path}.{k}")]
    if isinstance(node, list):
        return [p for i, v in enumerate(node) for p in find_leftover_placeholders(v, f"{path}[{i}]")]
    if isinstance(node, str) and "${" in node:
        return [path]
    return []


def to_runtime_vars(text: str) -> str:
    """data/scripts.json uses {x}; ElevenLabs dynamic variables are {{x}}."""
    return SINGLE_BRACE_VAR.sub(r"{{\1}}", text)


class Sources:
    """Everything read from agent/ and data/."""

    def __init__(self) -> None:
        self.prompt_md = (AGENT_DIR / "prompt.md").read_text(encoding="utf-8")
        self.tools = read_json(AGENT_DIR / "tools.json")
        self.template = read_json(AGENT_DIR / "agent.template.json")
        self.variants = read_json(AGENT_DIR / "variants.json")
        self.scripts = read_json(DATA_DIR / "scripts.json")
        self.red_flags = read_json(DATA_DIR / "red_flags.json")
        self.plan = read_json(DATA_DIR / "plan.json")
        self.study = read_json(DATA_DIR / "study.json")

    def red_flag_ids(self) -> list[str]:
        ids = list(self.plan.get("red_flag_ids") or [])
        known = {f["id"] for f in self.red_flags["red_flags"]}
        missing = [i for i in ids if i not in known]
        if not ids:
            raise SyncError("data/plan.json has no red_flag_ids")
        if missing:
            raise SyncError(f"data/plan.json red_flag_ids not in data/red_flags.json: {missing}")
        return ids

    def red_flag_list(self) -> str:
        by_id = {f["id"]: f for f in self.red_flags["red_flags"]}
        lines = []
        for rf_id in self.red_flag_ids():
            flag = by_id[rf_id]
            examples = [*flag.get("examples_en", []), *flag.get("examples_es", [])]
            line = f"- {rf_id}: {flag['agent_description']}"
            if examples:
                line += " (examples: " + ", ".join(json.dumps(e, ensure_ascii=False) for e in examples) + ")"
            lines.append(line)
        return "\n".join(lines)

    def system_prompt(self) -> str:
        if "${RED_FLAG_LIST}" not in self.prompt_md:
            raise SyncError("agent/prompt.md has no ${RED_FLAG_LIST} placeholder")
        prompt = self.prompt_md.replace("${RED_FLAG_LIST}", self.red_flag_list()).strip() + "\n"
        leftover = PLACEHOLDER.findall(prompt)
        if leftover:
            raise SyncError(f"agent/prompt.md has unknown sync-time placeholders: {leftover}")
        return prompt

    def tool_configs(self, public_base_url: str, secret_id: str) -> list[dict[str, Any]]:
        values = {
            "PUBLIC_BASE_URL": public_base_url,
            "TOOL_SECRET_ID": secret_id,
            "RED_FLAG_IDS": self.red_flag_ids(),
        }
        return [render(t, values) for t in self.tools["tools"]]

    def line(self, key: str, lang: str) -> str:
        try:
            return self.scripts["lines"][key][lang]
        except KeyError as e:
            raise SyncError(f"data/scripts.json lines.{key}.{lang} is missing") from e

    def agent_config(
        self,
        variant: str,
        *,
        tool_ids: list[str],
        voice_id: str,
        inbound: bool | None,
    ) -> dict[str, Any]:
        """inbound: True = this variant takes inbound calls, False = explicitly not, None = leave unset."""
        spec = self.variants["variants"][variant]
        lang, pace = spec["language"], spec["pace"]
        pace_cfg = self.variants["pace_settings"][pace]
        values: dict[str, Any] = {
            "VARIANT": variant,
            "LANGUAGE": lang,
            "FIRST_MESSAGE": to_runtime_vars(self.line("first_message", lang)),
            "VOICEMAIL_MESSAGE": to_runtime_vars(self.line("voicemail", lang)),
            "PACE_INSTRUCTIONS_SAMPLE": self.scripts["pace_instructions"][pace],
            "LANGUAGE_NAME_SAMPLE": self.scripts["language_names"][lang]["en"],
            "STUDY_TEAM_NAME_SAMPLE": self.study["study_team_name"][lang],
            "PROMPT": self.system_prompt(),
            "LLM": (llm := env("ELEVENLABS_LLM") or self.variants["llm"]),
            "TOOL_IDS": list(tool_ids),
            "BACKUP_LLM_ORDER": list(self.variants["backup_llm_order_claude"] if llm.startswith("claude")
                                     else self.variants["backup_llm_order"]),
            "TTS_MODEL_ID": env(f"ELEVENLABS_TTS_MODEL_{lang.upper()}") or self.variants["tts_model_by_language"][lang],
            "VOICE_ID": voice_id,
            "TTS_SPEED": float(pace_cfg["tts_speed"]),
            "TURN": pace_cfg["turn"],
            "MAX_DURATION_SECONDS": int(pace_cfg["max_duration_seconds"]),
        }
        cfg = render(self.template, values)
        prompt = cfg["conversation_config"]["agent"]["prompt"]
        if pace_cfg.get("skip_turn"):
            prompt["built_in_tools"]["skip_turn"] = {
                "type": "system",
                "name": "skip_turn",
                "description": "",
                "params": {"system_tool_type": "skip_turn", "wait_timeout_secs": SKIP_TURN_WAIT_SECS},
            }
        if inbound is True:
            cfg["platform_settings"]["overrides"] = {
                INBOUND_FLAG: True,
                "conversation_config_override": {"agent": {"first_message": True}},
            }
        elif inbound is False:
            cfg["platform_settings"]["overrides"] = {INBOUND_FLAG: False}
        leftover = find_leftover_placeholders(cfg)
        if leftover:
            raise SyncError(f"{variant}: unfilled ${{...}} placeholders at {leftover}")
        return cfg


# ---------------------------------------------------------------- API client


class ElevenLabs:
    def __init__(self, api_key: str) -> None:
        import httpx

        self._http = httpx.Client(base_url=API_BASE, headers={"xi-api-key": api_key}, timeout=30.0)

    def request(
        self, method: str, path: str, *, body: Any = None, params: dict[str, Any] | None = None
    ) -> Any:
        try:
            r = self._http.request(method, path, json=body, params=params)
        except Exception as e:  # network errors
            raise SyncError(f"network error on {method} {path}: {e}") from e
        if r.status_code >= 400:
            raise ApiError(method, path, r.status_code, r.text)
        if not r.content:
            return {}
        try:
            return r.json()
        except ValueError:
            return {}

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params=params or None)

    def post(self, path: str, body: Any) -> Any:
        return self.request("POST", path, body=body)

    def patch(self, path: str, body: Any) -> Any:
        return self.request("PATCH", path, body=body)


def ensure_secret(api: ElevenLabs, value: str) -> str:
    secrets = api.get("/v1/convai/secrets").get("secrets", [])
    matches = [s for s in secrets if s.get("name") == SECRET_NAME]
    if len(matches) > 1:
        print(f"  warning: {len(matches)} secrets named {SECRET_NAME}; using the first")
    if matches:
        secret_id = matches[0]["secret_id"]
        try:
            api.patch(
                f"/v1/convai/secrets/{secret_id}", {"type": "update", "name": SECRET_NAME, "value": value}
            )
            print(f"  secret {SECRET_NAME}: updated value ({secret_id})")
        except ApiError as e:
            if e.status not in (400, 404, 405, 422):
                raise
            print(
                f"  secret {SECRET_NAME}: reusing {secret_id} (value update not accepted, HTTP {e.status}).\n"
                "    If TOOL_SHARED_SECRET changed, update the secret in the ElevenLabs dashboard."
            )
        return secret_id
    created = api.post("/v1/convai/secrets", {"type": "new", "name": SECRET_NAME, "value": value})
    secret_id = created["secret_id"]
    print(f"  secret {SECRET_NAME}: created ({secret_id})")
    return secret_id


def upsert_tools(api: ElevenLabs, configs: list[dict[str, Any]]) -> dict[str, str]:
    existing: dict[str, list[str]] = {}
    for t in api.get("/v1/convai/tools").get("tools", []):
        name = (t.get("tool_config") or {}).get("name") or t.get("name")
        if name:
            existing.setdefault(name, []).append(t["id"])
    ids: dict[str, str] = {}
    for cfg in configs:
        name = cfg["name"]
        found = existing.get(name, [])
        if len(found) > 1:
            print(f"  warning: {len(found)} tools named {name} ({', '.join(found)}); updating the first")
        if found:
            api.patch(f"/v1/convai/tools/{found[0]}", {"tool_config": cfg})
            ids[name] = found[0]
            print(f"  tool {name}: updated ({found[0]})")
        else:
            ids[name] = api.post("/v1/convai/tools", {"tool_config": cfg})["id"]
            print(f"  tool {name}: created ({ids[name]})")
    return ids


def list_agents(api: ElevenLabs) -> dict[str, list[str]]:
    by_name: dict[str, list[str]] = {}
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"search": AGENT_SEARCH, "page_size": 100}
        if cursor:
            params["cursor"] = cursor
        page = api.get("/v1/convai/agents", **params)
        for a in page.get("agents", []):
            by_name.setdefault(a.get("name", ""), []).append(a["agent_id"])
        cursor = page.get("next_cursor")
        if not page.get("has_more") or not cursor:
            return by_name


def current_inbound_variant(api: ElevenLabs, agent_ids: dict[str, str]) -> str | None:
    """The variant whose live agent already accepts the inbound-init webhook (kept on plain syncs)."""
    for variant, agent_id in agent_ids.items():
        agent = api.get(f"/v1/convai/agents/{agent_id}")
        overrides = (agent.get("platform_settings") or {}).get("overrides") or {}
        if overrides.get(INBOUND_FLAG):
            return variant
    return None


def patch_settings(api: ElevenLabs, key: str, value: dict[str, Any]) -> None:
    """PATCH one key of /v1/convai/settings; restore the other key we manage if the PATCH wiped it."""
    managed = ("webhooks", "conversation_initiation_client_data_webhook")
    before = api.get("/v1/convai/settings")
    api.patch("/v1/convai/settings", {key: value})
    after = api.get("/v1/convai/settings")
    lost = {k: before[k] for k in managed if k != key and before.get(k) and not after.get(k)}
    if lost:
        print(f"  note: PATCH /v1/convai/settings cleared {list(lost)}; restoring")
        api.patch("/v1/convai/settings", {key: value, **lost})


def setup_webhook(api: ElevenLabs, public_base_url: str) -> None:
    url = f"{public_base_url}/webhooks/elevenlabs/post-call"
    hooks = api.get("/v1/workspace/webhooks").get("webhooks", [])
    match = next((h for h in hooks if h.get("name") == WEBHOOK_NAME), None)
    if match:
        webhook_id = match["webhook_id"]
        print(
            f"  webhook {WEBHOOK_NAME}: reusing {webhook_id}. Its signing secret is only shown at creation;\n"
            "    if ELEVENLABS_WEBHOOK_SECRET is lost, delete the webhook in the dashboard and rerun --setup-webhook."
        )
        if match.get("webhook_url") and match["webhook_url"] != url:
            print(
                f"  warning: existing webhook points at {match['webhook_url']}, not {url}.\n"
                "    Update it in the dashboard (or delete it and rerun --setup-webhook)."
            )
    else:
        created = api.post(
            "/v1/workspace/webhooks",
            {"settings": {"auth_type": "hmac", "name": WEBHOOK_NAME, "webhook_url": url}},
        )
        webhook_id = created["webhook_id"]
        print(f"  webhook {WEBHOOK_NAME}: created ({webhook_id}) -> {url}")
        print("\n  Put this in .env (shown only once):\n")
        print(f"    ELEVENLABS_WEBHOOK_SECRET={created.get('webhook_secret', '<missing in response>')}\n")
    api.patch(
        f"/v1/workspace/webhooks/{webhook_id}",
        {"is_disabled": False, "name": WEBHOOK_NAME, "retry_enabled": True},
    )
    print("  webhook: enabled, retries on")
    patch_settings(api, "webhooks", webhook_settings(webhook_id))
    print(f"  webhook: attached workspace-wide for {WEBHOOK_EVENTS}")


def webhook_settings(webhook_id: str) -> dict[str, Any]:
    return {"post_call_webhook_id": webhook_id, "events": WEBHOOK_EVENTS, "transcript_format": "json"}


def inbound_settings(public_base_url: str, secret_id: str) -> dict[str, Any]:
    return {
        "url": f"{public_base_url}/webhooks/elevenlabs/inbound-init",
        "request_headers": {"X-BV-Tool-Secret": {"secret_id": secret_id}},
    }


# ---------------------------------------------------------------- deployed snapshot (V9)
#
# A hash must be equal for the config the sync renders and for the same config read back right after
# the sync. Read back (GET /v1/convai/agents/{id}, GET /v1/convai/tools/{id}, checked Oct 11 2026) the API
#   - adds many server fields (metadata, widget, turn_model, inline `prompt.tools`, per-tool defaults...),
#   - returns integral numbers as floats (temperature 0 -> 0.0, turn_timeout 8 -> 8.0),
#   - returns real tool, voice, agent and secret IDs and the tools' PUBLIC_BASE_URL webhook URLs,
#   - keeps key and list order (lists are not reordered).
# normalized() therefore: keeps only the keys the sync sends (project()), removes the deployment-specific
# fields below, turns integral floats into ints, and hashes canonical JSON (sorted keys).

# Fields the sync fills with deployment-specific IDs, URLs or secret references, removed at any depth when
# the value is a string, a list of strings or null (a tool's body-schema property that happens to be called
# `url` is an object and is kept). Secret values themselves are never part of an agent or tool config.
DEPLOYMENT_KEYS = frozenset({"agent_id", "tool_ids", "voice_id", "secret_id", "url"})
# Inbound-call wiring: set per deployment by --inbound (and kept by later plain syncs), not by the template.
DEPLOYMENT_PATHS = frozenset({("platform_settings", "overrides")})
AGENT_ID_SUFFIX_CHARS = 4
DRY_RUN_BASE = "https://PUBLIC_BASE_URL.invalid"
DRY_RUN_SECRET_ID = "<secret_id of bv_tool_secret>"


def _dig(node: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _is_deployment_value(value: Any) -> bool:
    if value is None or isinstance(value, str):
        return True
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def strip_deployment_fields(node: Any, path: tuple[str, ...] = ()) -> Any:
    """Remove IDs, URLs and secret references (DEPLOYMENT_KEYS) and DEPLOYMENT_PATHS."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            sub = (*path, key)
            if sub in DEPLOYMENT_PATHS or (key in DEPLOYMENT_KEYS and _is_deployment_value(value)):
                continue
            out[key] = strip_deployment_fields(value, sub)
        return out
    if isinstance(node, list):
        return [strip_deployment_fields(v, path) for v in node]
    return node


def canonical_numbers(node: Any) -> Any:
    """Integral floats become ints (the API reads 0 back as 0.0); bools stay bools."""
    if isinstance(node, dict):
        return {k: canonical_numbers(v) for k, v in node.items()}
    if isinstance(node, list):
        return [canonical_numbers(v) for v in node]
    if isinstance(node, float) and node.is_integer():
        return int(node)
    return node


def project(sent: Any, back: Any) -> Any:
    """The read-back restricted to the keys the sync sends: server-added fields are dropped.

    Lists of the same length are projected element by element; anything else is kept as read back,
    so a changed value, type or list length still changes the hash.
    """
    if isinstance(sent, dict) and isinstance(back, dict):
        return {k: project(v, back[k]) for k, v in sent.items() if k in back}
    if isinstance(sent, list) and isinstance(back, list) and len(sent) == len(back):
        return [project(s, b) for s, b in zip(sent, back, strict=True)]
    return back


def unread_keys(sent: Any, back: Any, path: str = "$") -> list[str]:
    """Paths the sync sends that the API did not read back (an ignored or renamed field)."""
    if isinstance(sent, dict) and isinstance(back, dict):
        out = []
        for key, value in sent.items():
            if key not in back:
                out.append(f"{path}.{key}")
            else:
                out.extend(unread_keys(value, back[key], f"{path}.{key}"))
        return out
    if isinstance(sent, list) and isinstance(back, list) and len(sent) == len(back):
        return [p for i, (s, b) in enumerate(zip(sent, back, strict=True)) for p in unread_keys(s, b, f"{path}[{i}]")]
    return []


def normalized(cfg: Any) -> Any:
    return canonical_numbers(strip_deployment_fields(cfg))


def sha256_json(node: Any) -> str:
    blob = json.dumps(node, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def config_fingerprint(agent_cfg: dict[str, Any], tool_cfgs: list[dict[str, Any]]) -> dict[str, Any]:
    """The snapshot fields of one variant, from a config as rendered or as read back (projected).

    prompt_sha256: the system prompt text. tools_sha256: the agent's tool configs, normalized and sorted
    by name. config_sha256: the whole agent config the sync sends (prompt, llm, voice settings, turn,
    evaluation...), normalized.
    """
    prompt = _dig(agent_cfg, "conversation_config", "agent", "prompt") or {}
    tools = sorted((normalized(t) for t in tool_cfgs), key=lambda t: str(t.get("name", "")))
    return {
        "llm": prompt.get("llm"),
        "backup_llms": list(_dig(prompt, "backup_llm_config", "order") or []),
        "tts_model": _dig(agent_cfg, "conversation_config", "tts", "model_id"),
        "prompt_sha256": sha256_text(prompt.get("prompt") or ""),
        "tools_sha256": sha256_json(tools),
        "config_sha256": sha256_json(normalized(agent_cfg)),
    }


def render_dry_run(
    sources: Sources, variants: list[str], *, inbound_variant: str | None = None
) -> tuple[str, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """What --dry-run prints (and check_config_hash.py hashes): placeholders for every ID it can't know."""
    base = (env("PUBLIC_BASE_URL") or DRY_RUN_BASE).rstrip("/")
    tools = sources.tool_configs(base, DRY_RUN_SECRET_ID)
    for t in tools:
        leftover = find_leftover_placeholders(t)
        if leftover:
            raise SyncError(f"tool {t['name']}: unfilled placeholders at {leftover}")
    tool_ids = [f"<tool_id:{t['name']}>" for t in tools]
    agents = {}
    for variant in variants:
        voice_env = sources.variants["variants"][variant]["voice_env"]
        voice_id = env(voice_env) or f"<{voice_env}>"
        inbound = None if not inbound_variant else variant == inbound_variant
        agents[variant] = sources.agent_config(variant, tool_ids=tool_ids, voice_id=voice_id, inbound=inbound)
    return base, tools, agents


def read_agent_ids(lock_path: Path = LOCK_PATH) -> dict[str, str]:
    """Agent IDs from agent/agents.lock.json, else from AGENTS_LOCK_JSON (cloud deploys, docs/03 §6.9)."""
    if lock_path.exists():
        origin = "agent/agents.lock.json"
        raw = lock_path.read_text(encoding="utf-8")
    else:
        origin = "AGENTS_LOCK_JSON"
        raw = env("AGENTS_LOCK_JSON")
        if not raw:
            raise SyncError(
                "no agent IDs: agent/agents.lock.json is absent and AGENTS_LOCK_JSON is empty "
                "(run `make sync-agent` first)"
            )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise SyncError(f"{origin} is not valid JSON") from None  # never echo its content
    if not isinstance(data, dict) or not all(isinstance(v, str) and v for v in data.values()):
        raise SyncError(f'{origin} must be a JSON object {{"<variant>": "<agent_id>", ...}}')
    return data


def evaluated_agent_llm(path: Path = LATEST_EVAL_PATH) -> str | None:
    """`model.agent` of the last text-mode evaluation (eval/results/latest.json), if any."""
    try:
        model = json.loads(path.read_text(encoding="utf-8")).get("model") or {}
    except (OSError, ValueError, AttributeError):
        return None
    agent = model.get("agent") if isinstance(model, dict) else None
    return agent if isinstance(agent, str) and agent else None


class ReadOnlyApi:
    """GET only: --snapshot can never write to ElevenLabs."""

    def __init__(self, api: ElevenLabs) -> None:
        self._api = api

    def get(self, path: str, **params: Any) -> Any:
        return self._api.get(path, **params)


def take_snapshot(
    api: Any,
    sources: Sources,
    agent_ids: dict[str, str],
    *,
    captured_at: str | None = None,
    llm_note: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Read every variant (and its tools) back and fingerprint it. Returns (snapshot, warnings).

    `api` needs only `.get(path)`. The projection key set is the --dry-run rendering, so the hashes are
    comparable with check_config_hash.py, which hashes that rendering directly.
    """
    variants = list(sources.variants["variants"])
    missing = [v for v in variants if not agent_ids.get(v)]
    if missing:
        raise SyncError(f"no agent ID for {missing} (run `make sync-agent` first)")
    _, sent_tools, sent_agents = render_dry_run(sources, variants)
    sent_tool_by_name = {t["name"]: t for t in sent_tools}
    tools_read: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    entries: dict[str, dict[str, Any]] = {}
    for variant in variants:
        agent_id = agent_ids[variant]
        suffix = agent_id[-AGENT_ID_SUFFIX_CHARS:]
        try:
            back = api.get(f"/v1/convai/agents/{agent_id}")
        except ApiError as e:
            raise SyncError(
                f"{variant}: GET agent ...{suffix} failed (HTTP {e.status}); run `make sync-agent` first"
            ) from None
        sent = sent_agents[variant]
        warnings += [f"{variant}: sent but not read back: {p}" for p in unread_keys(sent, back)]
        back_tools = []
        for tool_id in _dig(back, "conversation_config", "agent", "prompt", "tool_ids") or []:
            if tool_id not in tools_read:
                tool = (api.get(f"/v1/convai/tools/{tool_id}") or {}).get("tool_config") or {}
                name = tool.get("name")
                ref = sent_tool_by_name.get(name)
                if ref is None:
                    warnings.append(f"{variant}: uses a tool that is not in agent/tools.json: {name!r}")
                    tools_read[tool_id] = tool
                else:
                    warnings += [f"tool {name}: sent but not read back: {p}" for p in unread_keys(ref, tool)]
                    tools_read[tool_id] = project(ref, tool)
            back_tools.append(tools_read[tool_id])
        entries[variant] = {"agent_id_suffix": suffix, **config_fingerprint(project(sent, back), back_tools)}
    snapshot: dict[str, Any] = {
        "captured_at": captured_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    if llm_note:
        snapshot["llm_note"] = llm_note
    snapshot["variants"] = entries
    return snapshot, warnings


def snapshot(args: argparse.Namespace, sources: Sources) -> None:
    if not env("ELEVENLABS_API_KEY"):
        raise SyncError("environment not ready:\n  - ELEVENLABS_API_KEY is empty\n(see .env.example)")
    agent_ids = read_agent_ids()
    print("Snapshot (read-only: GET requests only)")
    snap, warnings = take_snapshot(
        ReadOnlyApi(ElevenLabs(env("ELEVENLABS_API_KEY"))), sources, agent_ids, llm_note=args.llm_note
    )
    for w in warnings:
        print(f"  warning: {w}")
    for variant, e in snap["variants"].items():
        print(
            f"  {variant}: agent ...{e['agent_id_suffix']}  llm {e['llm']}  backups {e['backup_llms']}  "
            f"tts {e['tts_model']}  config {e['config_sha256'][:12]}"
        )
    deployed = sorted({str(e["llm"]) for e in snap["variants"].values()})
    evaluated = evaluated_agent_llm()
    if deployed != [evaluated] and not args.llm_note:
        print(
            f"  warning: deployed llm {deployed} is not the evaluated model {evaluated!r} "
            "(eval/results/latest.json model.agent).\n"
            "    check_config_hash.py fails until you pin the evaluated model, or rerun with\n"
            "    --llm-note 'differs from evaluated model: <why>' and start a re-evaluation (WS1 V9)."
        )
    SNAPSHOT_PATH.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {SNAPSHOT_PATH.relative_to(ROOT)}; check it with: python3 agent/check_config_hash.py")


# ---------------------------------------------------------------- main flow


def validate_env(args: argparse.Namespace, sources: Sources, variants: list[str]) -> list[str]:
    errors = []
    if not env("ELEVENLABS_API_KEY"):
        errors.append("ELEVENLABS_API_KEY is empty")
    url = env("PUBLIC_BASE_URL")
    if not url:
        errors.append("PUBLIC_BASE_URL is empty (run `make tunnel` and set it to the https tunnel URL)")
    elif not url.startswith("https://"):
        errors.append(f"PUBLIC_BASE_URL must start with https:// (got {url!r})")
    elif "your-name" in url:
        errors.append(f"PUBLIC_BASE_URL is still the .env.example value ({url!r})")
    secret = env("TOOL_SHARED_SECRET")
    if not secret:
        errors.append("TOOL_SHARED_SECRET is empty")
    elif secret.startswith("change-me"):
        errors.append("TOOL_SHARED_SECRET is still the .env.example value; set a long random string")
    for var in sorted({sources.variants["variants"][v]["voice_env"] for v in variants}):
        if not env(var):
            errors.append(f"{var} is empty (pick a voice in ElevenLabs and put its voice ID in .env)")
    if args.inbound and not env("ELEVENLABS_PHONE_NUMBER_ID"):
        errors.append("--inbound needs ELEVENLABS_PHONE_NUMBER_ID (import the Twilio number first)")
    return errors


def dry_run(args: argparse.Namespace, sources: Sources, variants: list[str]) -> None:
    base, tools, agents = render_dry_run(sources, variants, inbound_variant=args.inbound)
    secret_id = DRY_RUN_SECRET_ID
    print("# DRY RUN: nothing is sent. PUBLIC_BASE_URL =", base)
    print("\n## Tools (POST/PATCH /v1/convai/tools body)")
    for t in tools:
        print(json.dumps({"tool_config": t}, ensure_ascii=False, indent=2))
    for variant, cfg in agents.items():
        print(
            f"\n## Agent {variant} (POST /v1/convai/agents/create or PATCH /v1/convai/agents/{{agent_id}} body)"
        )
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
    if args.setup_webhook:
        print("\n## --setup-webhook")
        print(
            "POST /v1/workspace/webhooks",
            json.dumps(
                {
                    "settings": {
                        "auth_type": "hmac",
                        "name": WEBHOOK_NAME,
                        "webhook_url": f"{base}/webhooks/elevenlabs/post-call",
                    }
                }
            ),
        )
        print(
            "PATCH /v1/workspace/webhooks/{id}",
            json.dumps({"is_disabled": False, "name": WEBHOOK_NAME, "retry_enabled": True}),
        )
        print("PATCH /v1/convai/settings", json.dumps({"webhooks": webhook_settings("<webhook_id>")}))
    if args.inbound:
        print(f"\n## --inbound {args.inbound}")
        print(
            "PATCH /v1/convai/settings",
            json.dumps({"conversation_initiation_client_data_webhook": inbound_settings(base, secret_id)}),
        )
        phone = env("ELEVENLABS_PHONE_NUMBER_ID") or "<ELEVENLABS_PHONE_NUMBER_ID>"
        print(
            f"PATCH /v1/convai/phone-numbers/{phone}", json.dumps({"agent_id": f"<agent_id:{args.inbound}>"})
        )


def sync(args: argparse.Namespace, sources: Sources, variants: list[str]) -> None:
    errors = validate_env(args, sources, variants)
    if errors:
        raise SyncError("environment not ready:\n  - " + "\n  - ".join(errors) + "\n(see .env.example)")
    base = env("PUBLIC_BASE_URL").rstrip("/")
    api = ElevenLabs(env("ELEVENLABS_API_KEY"))

    print("Secret")
    secret_id = ensure_secret(api, env("TOOL_SHARED_SECRET"))

    print("Tools")
    tool_ids_by_name = upsert_tools(api, sources.tool_configs(base, secret_id))
    tool_ids = [tool_ids_by_name[t["name"]] for t in sources.tools["tools"]]

    print("Agents")
    existing = list_agents(api)
    existing_ids = {
        v: existing[AGENT_NAME_PREFIX + v][0] for v in variants if existing.get(AGENT_NAME_PREFIX + v)
    }
    inbound_variant = args.inbound
    if not inbound_variant:
        inbound_variant = current_inbound_variant(api, existing_ids)
        if inbound_variant:
            print(f"  keeping inbound-call settings on {inbound_variant} (set earlier with --inbound)")
    lock: dict[str, str] = read_json(LOCK_PATH) if LOCK_PATH.exists() else {}
    for variant in variants:
        spec = sources.variants["variants"][variant]
        inbound = (variant == inbound_variant) if inbound_variant else None
        cfg = sources.agent_config(
            variant, tool_ids=tool_ids, voice_id=env(spec["voice_env"]), inbound=inbound
        )
        name = cfg["name"]
        found = existing.get(name, [])
        if len(found) > 1:
            print(
                f"  warning: {len(found)} agents named {name} ({', '.join(found)}); updating the first. "
                "Delete the extras in the dashboard."
            )
        if found:
            api.patch(f"/v1/convai/agents/{found[0]}", cfg)
            lock[variant] = found[0]
            print(f"  agent {name}: updated ({found[0]})")
        else:
            lock[variant] = api.post("/v1/convai/agents/create", cfg)["agent_id"]
            print(f"  agent {name}: created ({lock[variant]})")
    ordered = {v: lock[v] for v in sources.variants["variants"] if v in lock}
    LOCK_PATH.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {LOCK_PATH.relative_to(ROOT)}")

    if args.setup_webhook:
        print("Post-call webhook")
        setup_webhook(api, base)

    if args.inbound:
        print(f"Inbound fallback -> {args.inbound}")
        patch_settings(api, "conversation_initiation_client_data_webhook", inbound_settings(base, secret_id))
        print(f"  inbound-init webhook: {base}/webhooks/elevenlabs/inbound-init")
        phone_id = env("ELEVENLABS_PHONE_NUMBER_ID")
        api.patch(f"/v1/convai/phone-numbers/{phone_id}", {"agent_id": lock[args.inbound]})
        print(f"  phone number {phone_id} -> {args.inbound} ({lock[args.inbound]})")
        print("  Test with one real inbound call (dashboard Preview does not call the inbound webhook).")

    print("Done. Next: make sync-agent ARGS=--snapshot, then commit agent/deployed_snapshot.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync the Between Visits ElevenLabs agents and tools.")
    parser.add_argument(
        "--dry-run", action="store_true", help="print rendered configs; no network, no API key"
    )
    parser.add_argument("--only", metavar="VARIANT", help="sync just this variant (tools are always synced)")
    parser.add_argument(
        "--setup-webhook", action="store_true", help="create/attach the HMAC post-call webhook"
    )
    parser.add_argument(
        "--inbound", metavar="VARIANT", help="point the inbound webhook and phone number at VARIANT"
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="read-only: read the deployed variants back and write agent/deployed_snapshot.json",
    )
    parser.add_argument(
        "--llm-note",
        metavar="TEXT",
        help="with --snapshot: why the deployed llm differs from the evaluated model (recorded as llm_note)",
    )
    args = parser.parse_args(argv)
    if args.snapshot and (args.dry_run or args.only or args.setup_webhook or args.inbound):
        parser.error("--snapshot runs alone (read-only); run the sync first, then --snapshot")
    if args.llm_note is not None and not args.snapshot:
        parser.error("--llm-note only applies to --snapshot")

    load_env()
    try:
        sources = Sources()
        all_variants = list(sources.variants["variants"])
        for flag in ("only", "inbound"):
            value = getattr(args, flag)
            if value and value not in all_variants:
                parser.error(f"--{flag} must be one of {all_variants}")
        if args.only and args.inbound and args.only != args.inbound:
            parser.error("--inbound must name the same variant as --only (or drop --only)")
        variants = [args.only] if args.only else all_variants
        if args.snapshot:
            snapshot(args, sources)
        elif args.dry_run:
            dry_run(args, sources, variants)
        else:
            sync(args, sources, variants)
    except ApiError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1
    except SyncError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
