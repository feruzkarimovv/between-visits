#!/usr/bin/env python3
"""Create or update the Between Visits ElevenLabs agents and tools (config as code).

Run from the repo root:

    uv run --project backend python agent/sync_agent.py [--dry-run] [--only VARIANT]
                                                        [--setup-webhook] [--inbound VARIANT]

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

All `${...}` placeholders are filled here at sync time; all `{{...}}` are ElevenLabs runtime
dynamic variables and are left untouched. No clinical wording lives in this file: every
spoken or clinical string is read from data/.

Dependencies: httpx + stdlib (python-dotenv is used if importable, else a tiny .env parser).
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / "agent"
DATA_DIR = ROOT / "data"
LOCK_PATH = AGENT_DIR / "agents.lock.json"

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
            "LLM": env("ELEVENLABS_LLM") or self.variants["llm"],
            "TOOL_IDS": list(tool_ids),
            "BACKUP_LLM_ORDER": list(self.variants["backup_llm_order"]),
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
    base = (env("PUBLIC_BASE_URL") or "https://PUBLIC_BASE_URL.invalid").rstrip("/")
    secret_id = "<secret_id of bv_tool_secret>"
    tools = sources.tool_configs(base, secret_id)
    for t in tools:
        leftover = find_leftover_placeholders(t)
        if leftover:
            raise SyncError(f"tool {t['name']}: unfilled placeholders at {leftover}")
    tool_ids = [f"<tool_id:{t['name']}>" for t in tools]
    print("# DRY RUN: nothing is sent. PUBLIC_BASE_URL =", base)
    print("\n## Tools (POST/PATCH /v1/convai/tools body)")
    for t in tools:
        print(json.dumps({"tool_config": t}, ensure_ascii=False, indent=2))
    for variant in variants:
        voice_env = sources.variants["variants"][variant]["voice_env"]
        voice_id = env(voice_env) or f"<{voice_env}>"
        inbound = None if not args.inbound else variant == args.inbound
        cfg = sources.agent_config(variant, tool_ids=tool_ids, voice_id=voice_id, inbound=inbound)
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

    print("Done.")


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
    args = parser.parse_args(argv)

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
        if args.dry_run:
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
