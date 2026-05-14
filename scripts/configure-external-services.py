#!/usr/bin/env python3
"""Configure external service keys for local MRW deployments.

This script intentionally writes only to main/backend/.env. It never prints
secret values and keeps unknown .env lines intact.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / "main" / "backend" / ".env"
ENV_EXAMPLE_PATH = ROOT_DIR / "main" / "backend" / ".env.example"


@dataclass(frozen=True)
class ServiceSetting:
    key: str
    label: str
    group: str
    required_for: str
    secret: bool = True
    default: str = ""


SETTINGS: list[ServiceSetting] = [
    ServiceSetting("OPENAI_API_KEY", "OpenAI API key", "LLM", "OpenAI chat, embeddings, extraction"),
    ServiceSetting("OPENAI_API_BASE", "OpenAI API base", "LLM", "OpenAI-compatible endpoint", secret=False, default="https://api.openai.com/v1"),
    ServiceSetting("AZURE_API_KEY", "Azure OpenAI API key", "LLM", "Azure OpenAI"),
    ServiceSetting("AZURE_API_BASE", "Azure OpenAI endpoint", "LLM", "Azure OpenAI", secret=False),
    ServiceSetting("AZURE_CHAT_DEPLOYMENT", "Azure chat deployment", "LLM", "Azure OpenAI chat", secret=False),
    ServiceSetting("AZURE_EMBEDDING_DEPLOYMENT", "Azure embedding deployment", "LLM", "Azure OpenAI embeddings", secret=False),
    ServiceSetting("OLLAMA_BASE_URL", "Ollama base URL", "LLM", "Local Ollama", secret=False, default="http://localhost:11434"),
    ServiceSetting("SERPER_API_KEY", "Serper API key", "Search", "Google-style web search"),
    ServiceSetting("GOOGLE_SEARCH_API_KEY", "Google Search API key", "Search", "Google Custom Search"),
    ServiceSetting("GOOGLE_SEARCH_CSE_ID", "Google Search CSE ID", "Search", "Google Custom Search", secret=False),
    ServiceSetting("SERPAPI_KEY", "SerpApi key", "Search", "SerpApi web search"),
    ServiceSetting("SERPSTACK_KEY", "Serpstack key", "Search", "Serpstack web search"),
    ServiceSetting("BING_SEARCH_KEY", "Bing Search key", "Search", "Bing web search"),
    ServiceSetting("AZURE_SEARCH_ENDPOINT", "Azure Search endpoint", "Search", "Azure AI Search", secret=False),
    ServiceSetting("AZURE_SEARCH_KEY", "Azure Search key", "Search", "Azure AI Search"),
    ServiceSetting("CODEX_OAUTH_ENABLED", "Codex OAuth enabled", "Codex Auth", "Browser-based Codex login", secret=False, default="false"),
    ServiceSetting("CODEX_OAUTH_REDIRECT_URI", "Codex OAuth redirect URI", "Codex Auth", "Backend OAuth callback", secret=False, default="http://localhost:8000/api/v1/codex-auth/callback"),
    ServiceSetting("CODEX_OAUTH_FRONTEND_SUCCESS_URL", "Codex OAuth success URL", "Codex Auth", "Frontend URL after login", secret=False, default="http://localhost:5173"),
    ServiceSetting("CODEX_OAUTH_FRONTEND_ERROR_URL", "Codex OAuth error URL", "Codex Auth", "Frontend URL after failed login", secret=False, default="http://localhost:5173"),
    ServiceSetting("SEARXNG_BASE_URL", "SearXNG base URL", "Search Enhancements", "Optional local metasearch", secret=False, default="http://127.0.0.1:8088"),
    ServiceSetting("SEARXNG_MAX_PAGES", "SearXNG max pages", "Search Enhancements", "Optional paged metasearch volume", secret=False, default="3"),
    ServiceSetting("YACY_BASE_URL", "YaCy base URL", "Search Enhancements", "Optional local corpus/search provider", secret=False, default="http://127.0.0.1:8090"),
    ServiceSetting("YACY_RESOURCE_MODE", "YaCy resource mode", "Search Enhancements", "local for corpus, global for web", secret=False, default="local"),
    ServiceSetting("LEGISCAN_API_KEY", "LegiScan API key", "Data", "Policy data ingestion"),
    ServiceSetting("TWITTER_BEARER_TOKEN", "Twitter bearer token", "Social", "Twitter/X ingestion"),
]


def ensure_env_file() -> None:
    if ENV_PATH.exists():
        return
    if ENV_EXAMPLE_PATH.exists():
        shutil.copyfile(ENV_EXAMPLE_PATH, ENV_PATH)
        print(f"created {ENV_PATH.relative_to(ROOT_DIR)} from .env.example")
        return
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_PATH.write_text("", encoding="utf-8")
    print(f"created empty {ENV_PATH.relative_to(ROOT_DIR)}")


def parse_env(path: Path) -> tuple[list[str], dict[str, str]]:
    if not path.exists():
        return [], {}
    lines = path.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")
    for line in lines:
        match = pattern.match(line)
        if not match:
            continue
        key, value = match.groups()
        values[key] = unquote_env_value(value.strip())
    return lines, values


def unquote_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def quote_env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def write_env_updates(updates: dict[str, str]) -> None:
    ensure_env_file()
    lines, _ = parse_env(ENV_PATH)
    seen: set[str] = set()
    pattern = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*)$")
    next_lines: list[str] = []
    for line in lines:
        match = pattern.match(line)
        if not match:
            next_lines.append(line)
            continue
        prefix, key, sep, _old_value = match.groups()
        if key in updates:
            next_lines.append(f"{prefix}{key}{sep}{quote_env_value(updates[key])}")
            seen.add(key)
        else:
            next_lines.append(line)
    missing = [setting.key for setting in SETTINGS if setting.key in updates and setting.key not in seen]
    if missing and next_lines and next_lines[-1].strip():
        next_lines.append("")
    for key in missing:
        next_lines.append(f"{key}={quote_env_value(updates[key])}")
    ENV_PATH.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")


def masked(value: str) -> str:
    if not value:
        return "missing"
    return "configured"


def collect_status() -> dict[str, str]:
    ensure_env_file()
    _, env_values = parse_env(ENV_PATH)
    merged = dict(env_values)
    for setting in SETTINGS:
        if os.environ.get(setting.key):
            merged[setting.key] = os.environ[setting.key]
    return {setting.key: merged.get(setting.key, "") for setting in SETTINGS}


def print_status() -> int:
    values = collect_status()
    groups: dict[str, list[ServiceSetting]] = {}
    for setting in SETTINGS:
        groups.setdefault(setting.group, []).append(setting)
    for group, settings in groups.items():
        print(f"\n[{group}]")
        for setting in settings:
            value = values.get(setting.key, "")
            state = "configured" if value else "missing"
            shown = masked(value) if setting.secret else (value or "missing")
            print(f"{setting.key:28} {state:10} {shown}")
    print(f"\n.env: {ENV_PATH}")
    return 0


def prompt_for_setting(setting: ServiceSetting, current: str) -> str | None:
    shown = masked(current) if setting.secret else (current or "")
    prompt = f"{setting.key} ({setting.label}, current: {shown or 'missing'}; blank keeps current): "
    if setting.secret:
        value = getpass.getpass(prompt)
    else:
        value = input(prompt)
    value = value.strip()
    if not value:
        return None
    return value


def run_wizard() -> int:
    ensure_env_file()
    _, values = parse_env(ENV_PATH)
    print("Configure external service keys. Blank input keeps the current value.")
    print(f"Writing to: {ENV_PATH}")
    updates: dict[str, str] = {}
    for setting in SETTINGS:
        current = os.environ.get(setting.key) or values.get(setting.key, "")
        value = prompt_for_setting(setting, current)
        if value is not None:
            updates[setting.key] = value
    if not updates:
        print("No changes.")
        return 0
    write_env_updates(updates)
    print(f"Saved {len(updates)} setting(s) to {ENV_PATH.relative_to(ROOT_DIR)}")
    return 0


def set_values(assignments: list[str]) -> int:
    updates: dict[str, str] = {}
    valid = {setting.key for setting in SETTINGS}
    for assignment in assignments:
        if "=" not in assignment:
            print(f"invalid assignment: {assignment}", file=sys.stderr)
            return 2
        key, value = assignment.split("=", 1)
        key = key.strip()
        if key not in valid:
            print(f"unsupported key: {key}", file=sys.stderr)
            return 2
        updates[key] = value.strip()
    write_env_updates(updates)
    print(f"Saved {len(updates)} setting(s) to {ENV_PATH.relative_to(ROOT_DIR)}")
    return 0


def probe_url(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= int(response.status) < 500
    except (OSError, urllib.error.URLError):
        return False


def run_doctor() -> int:
    values = collect_status()
    status = 0
    llm_ready = bool(values.get("OPENAI_API_KEY")) or bool(values.get("AZURE_API_KEY")) or probe_url(values.get("OLLAMA_BASE_URL") or "http://localhost:11434")
    search_ready = any(values.get(key) for key in ("SERPER_API_KEY", "GOOGLE_SEARCH_API_KEY", "SERPAPI_KEY", "SERPSTACK_KEY", "BING_SEARCH_KEY"))
    google_complete = bool(values.get("GOOGLE_SEARCH_API_KEY")) == bool(values.get("GOOGLE_SEARCH_CSE_ID"))

    print(f"env_file={ENV_PATH}")
    print(f"llm_ready={'yes' if llm_ready else 'no'}")
    print(f"search_ready={'yes' if search_ready else 'no'}")
    print(f"ollama_reachable={'yes' if probe_url(values.get('OLLAMA_BASE_URL') or 'http://localhost:11434') else 'no'}")
    print(f"google_search_pair={'ok' if google_complete else 'incomplete'}")

    if not llm_ready:
        print("warning: no OpenAI/Azure/Ollama LLM backend is configured", file=sys.stderr)
        status = 1
    if not search_ready:
        print("warning: no external web search provider key is configured", file=sys.stderr)
        status = 1
    if not google_complete:
        print("warning: GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CSE_ID should be configured together", file=sys.stderr)
        status = 1
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure local external service keys")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Show configured/missing settings without revealing secrets")
    subparsers.add_parser("wizard", help="Interactively update keys in main/backend/.env")
    subparsers.add_parser("doctor", help="Check high-level external service readiness")
    set_parser = subparsers.add_parser("set", help="Set one or more KEY=VALUE pairs")
    set_parser.add_argument("assignments", nargs="+")
    args = parser.parse_args()

    if args.command == "status":
        return print_status()
    if args.command == "wizard":
        return run_wizard()
    if args.command == "doctor":
        return run_doctor()
    if args.command == "set":
        return set_values(args.assignments)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
