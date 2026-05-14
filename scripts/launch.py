#!/usr/bin/env python3
"""Cross-platform GUI launcher for Market Research Workflow."""

from __future__ import annotations

import os
import platform
import re
import json
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk


ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / "main" / "backend" / ".env"
ENV_EXAMPLE_PATH = ROOT_DIR / "main" / "backend" / ".env.example"


SETTINGS = [
    {
        "key": "OPENAI_API_KEY",
        "label": "OpenAI API Key",
        "secret": True,
        "url": "https://platform.openai.com/api-keys",
        "hint": "LLM, embeddings, extraction",
    },
    {
        "key": "OPENAI_API_BASE",
        "label": "OpenAI API Base",
        "secret": False,
        "url": "https://platform.openai.com/docs",
        "hint": "OpenAI-compatible endpoint",
    },
    {
        "key": "AZURE_API_KEY",
        "label": "Azure OpenAI Key",
        "secret": True,
        "url": "https://portal.azure.com/",
        "hint": "Azure OpenAI",
    },
    {
        "key": "AZURE_API_BASE",
        "label": "Azure OpenAI Endpoint",
        "secret": False,
        "url": "https://portal.azure.com/",
        "hint": "Azure OpenAI endpoint",
    },
    {
        "key": "OLLAMA_BASE_URL",
        "label": "Ollama Base URL",
        "secret": False,
        "url": "https://ollama.com/download",
        "hint": "Local LLM",
    },
    {
        "key": "SERPER_API_KEY",
        "label": "Serper Key",
        "secret": True,
        "url": "https://serper.dev/api-key",
        "hint": "External web search",
    },
    {
        "key": "GOOGLE_SEARCH_API_KEY",
        "label": "Google Search API Key",
        "secret": True,
        "url": "https://console.cloud.google.com/apis/credentials",
        "hint": "Google Custom Search",
    },
    {
        "key": "GOOGLE_SEARCH_CSE_ID",
        "label": "Google Search CSE ID",
        "secret": False,
        "url": "https://programmablesearchengine.google.com/controlpanel/all",
        "hint": "Google Custom Search engine",
    },
    {
        "key": "SERPAPI_KEY",
        "label": "SerpApi Key",
        "secret": True,
        "url": "https://serpapi.com/manage-api-key",
        "hint": "External web search",
    },
    {
        "key": "SERPSTACK_KEY",
        "label": "Serpstack Key",
        "secret": True,
        "url": "https://serpstack.com/dashboard",
        "hint": "External web search",
    },
    {
        "key": "BING_SEARCH_KEY",
        "label": "Bing Search Key",
        "secret": True,
        "url": "https://portal.azure.com/#view/Microsoft_Azure_ProjectOxford/CognitiveServicesHub/~/BingSearch",
        "hint": "Bing web search",
    },
    {
        "key": "AZURE_SEARCH_ENDPOINT",
        "label": "Azure Search Endpoint",
        "secret": False,
        "url": "https://portal.azure.com/",
        "hint": "Azure AI Search",
    },
    {
        "key": "AZURE_SEARCH_KEY",
        "label": "Azure Search Key",
        "secret": True,
        "url": "https://portal.azure.com/",
        "hint": "Azure AI Search",
    },
    {
        "key": "SEARXNG_BASE_URL",
        "label": "SearXNG Base URL",
        "secret": False,
        "url": "http://127.0.0.1:8088",
        "hint": "Optional local metasearch",
    },
    {
        "key": "YACY_BASE_URL",
        "label": "YaCy Base URL",
        "secret": False,
        "url": "http://127.0.0.1:8090",
        "hint": "Optional local corpus search",
    },
    {
        "key": "LEGISCAN_API_KEY",
        "label": "LegiScan Key",
        "secret": True,
        "url": "https://legiscan.com/legiscan",
        "hint": "Policy data ingestion",
    },
    {
        "key": "TWITTER_BEARER_TOKEN",
        "label": "Twitter Bearer Token",
        "secret": True,
        "url": "https://developer.x.com/en/portal/dashboard",
        "hint": "Twitter/X ingestion",
    },
]

STARTUP_ENHANCEMENTS = [
    {
        "key": "searxng",
        "flag": "--with-searxng",
        "label": "SearXNG",
        "hint": "Optional external metasearch provider on :8088",
    },
    {
        "key": "yacy",
        "flag": "--with-yacy",
        "label": "YaCy",
        "hint": "Optional local/search-corpus provider on :8090",
    },
    {
        "key": "lancedb",
        "flag": "--with-lancedb",
        "label": "LanceDB",
        "hint": "Optional local index adapter dependency",
    },
]


def ensure_env_file() -> None:
    if ENV_PATH.exists():
        return
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if ENV_EXAMPLE_PATH.exists():
        ENV_PATH.write_text(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        ENV_PATH.write_text("", encoding="utf-8")


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def read_env() -> tuple[list[str], dict[str, str]]:
    ensure_env_file()
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")
    for line in lines:
        match = pattern.match(line)
        if match:
            values[match.group(1)] = unquote(match.group(2))
    return lines, values


def write_env(updates: dict[str, str]) -> None:
    lines, _values = read_env()
    pattern = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*)$")
    seen: set[str] = set()
    next_lines: list[str] = []
    for line in lines:
        match = pattern.match(line)
        if not match:
            next_lines.append(line)
            continue
        prefix, key, sep, _old = match.groups()
        if key in updates:
            next_lines.append(f"{prefix}{key}{sep}{quote(updates[key])}")
            seen.add(key)
        else:
            next_lines.append(line)
    missing = [key for key in updates if key not in seen]
    if missing and next_lines and next_lines[-1].strip():
        next_lines.append("")
    for key in missing:
        next_lines.append(f"{key}={quote(updates[key])}")
    ENV_PATH.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")


def run_platform_action(action: str, *extra: str) -> subprocess.Popen:
    system = platform.system().lower()
    if system == "windows":
        script = ROOT_DIR / "scripts" / "platform-windows.ps1"
        command = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            action,
            *extra,
        ]
    elif system == "darwin":
        command = [str(ROOT_DIR / "scripts" / "platform-macos.sh"), action, *extra]
    else:
        command = [str(ROOT_DIR / "scripts" / "platform-linux.sh"), action, *extra]
    return subprocess.Popen(
        command,
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def url_reachable(url: str, timeout: float = 0.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except Exception:
        return False


def preferred_frontend_url() -> str:
    if url_reachable("http://localhost:5174"):
        return "http://localhost:5174"
    return "http://localhost:5173"


def open_codex_auth() -> None:
    message = start_codex_auth_flow()
    if message:
        messagebox.showinfo("Codex Auth", message)


def start_codex_auth_flow() -> str:
    write_env(
        {
            "CODEX_OAUTH_ENABLED": "true",
            "CODEX_OAUTH_REDIRECT_URI": "http://localhost:8000/api/v1/codex-auth/callback",
            "CODEX_OAUTH_FRONTEND_SUCCESS_URL": preferred_frontend_url(),
            "CODEX_OAUTH_FRONTEND_ERROR_URL": preferred_frontend_url(),
        }
    )
    request = urllib.request.Request(
        "http://localhost:8000/api/v1/codex-auth/cli/bootstrap",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return f"Backend is not ready for Codex auth bootstrap: {exc}"

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return "Codex auth bootstrap returned an invalid response"

    if data.get("authenticated"):
        webbrowser.open(preferred_frontend_url())
        return "Codex is already authenticated on this machine."

    device_url = data.get("device_url")
    if device_url:
        webbrowser.open(str(device_url))
        code = f"\nDevice code: {data.get('device_code')}" if data.get("device_code") else ""
        hint = f"\n{data.get('hint')}" if data.get("hint") else ""
        return f"Complete Codex device authentication in the opened browser.{code}{hint}"

    hint = data.get("hint") or "No device authentication URL was returned."
    return f"Codex CLI auth could not start.\n{hint}"


class LauncherApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Market Research Workflow")
        self.geometry("980x720")
        self.minsize(880, 620)
        self.env_values: dict[str, str] = {}
        self.entries: dict[str, ttk.Entry] = {}
        self.enhancement_vars: dict[str, tk.BooleanVar] = {}
        self.codex_oauth_var = tk.BooleanVar(value=True)
        self.secret_placeholders: dict[str, bool] = {}
        self._build()
        self.refresh_env()
        self.refresh_status()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self, padding=14)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Market Research Workflow", font=("Arial", 18, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=f"Repo: {ROOT_DIR}").grid(row=1, column=0, sticky="w")
        ttk.Button(header, text="Open Repo", command=lambda: webbrowser.open(ROOT_DIR.as_uri())).grid(row=0, column=1, padx=4)
        ttk.Button(header, text="API Docs", command=lambda: webbrowser.open("http://localhost:8000/docs")).grid(row=0, column=2, padx=4)
        ttk.Button(header, text="Local UI", command=lambda: webbrowser.open("http://localhost:5173")).grid(row=0, column=3, padx=4)
        ttk.Button(header, text="Docker UI", command=lambda: webbrowser.open("http://localhost:5174")).grid(row=0, column=4, padx=4)
        ttk.Button(header, text="Codex Auth", command=open_codex_auth).grid(row=0, column=5, padx=4)

        actions = ttk.LabelFrame(self, text="Startup", padding=12)
        actions.grid(row=1, column=0, sticky="ew", padx=14)
        for idx in range(8):
            actions.columnconfigure(idx, weight=1)
        ttk.Button(actions, text="Start Local", command=lambda: self.run_action("start", *self.selected_enhancement_args())).grid(row=0, column=0, sticky="ew", padx=3, pady=3)
        ttk.Button(actions, text="Stop Local", command=lambda: self.run_action("stop")).grid(row=0, column=1, sticky="ew", padx=3, pady=3)
        ttk.Button(actions, text="Docker Launcher", command=lambda: self.run_action("docker-start")).grid(row=0, column=2, sticky="ew", padx=3, pady=3)
        ttk.Button(actions, text="Stop Docker", command=lambda: self.run_action("docker-stop")).grid(row=0, column=3, sticky="ew", padx=3, pady=3)
        ttk.Button(actions, text="Status", command=lambda: self.run_action("status")).grid(row=0, column=4, sticky="ew", padx=3, pady=3)
        ttk.Button(actions, text="Docker Status", command=lambda: self.run_action("docker-status")).grid(row=0, column=5, sticky="ew", padx=3, pady=3)
        ttk.Button(actions, text="Doctor", command=self.run_doctor).grid(row=0, column=6, sticky="ew", padx=3, pady=3)
        ttk.Button(actions, text="Refresh", command=self.refresh_status).grid(row=0, column=7, sticky="ew", padx=3, pady=3)

        enhancements = ttk.LabelFrame(actions, text="Optional Startup Enhancements", padding=8)
        enhancements.grid(row=1, column=0, columnspan=8, sticky="ew", padx=3, pady=(8, 3))
        for idx, item in enumerate(STARTUP_ENHANCEMENTS):
            enhancements.columnconfigure(idx, weight=1)
            var = tk.BooleanVar(value=False)
            self.enhancement_vars[item["key"]] = var
            option = ttk.Frame(enhancements)
            option.grid(row=0, column=idx, sticky="ew", padx=6)
            ttk.Checkbutton(option, text=item["label"], variable=var).grid(row=0, column=0, sticky="w")
            ttk.Label(option, text=item["hint"]).grid(row=1, column=0, sticky="w")

        panes = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        panes.grid(row=2, column=0, sticky="nsew", padx=14, pady=10)

        settings_outer = ttk.Frame(panes)
        settings_outer.columnconfigure(0, weight=1)
        panes.add(settings_outer, weight=3)
        settings = ttk.LabelFrame(settings_outer, text="External Service Settings", padding=10)
        settings.grid(row=0, column=0, sticky="nsew")
        settings.columnconfigure(1, weight=1)

        for row, item in enumerate(SETTINGS):
            ttk.Label(settings, text=item["label"]).grid(row=row, column=0, sticky="w", padx=4, pady=3)
            entry = ttk.Entry(settings, show="*" if item["secret"] else "")
            entry.grid(row=row, column=1, sticky="ew", padx=4, pady=3)
            self.entries[item["key"]] = entry
            ttk.Label(settings, text=item["hint"]).grid(row=row, column=2, sticky="w", padx=4, pady=3)
            ttk.Button(settings, text="Open", command=lambda url=item["url"]: webbrowser.open(url)).grid(row=row, column=3, padx=4, pady=3)

        buttons = ttk.Frame(settings_outer, padding=(0, 8, 0, 0))
        buttons.grid(row=1, column=0, sticky="ew")
        ttk.Checkbutton(buttons, text="Enable Codex OAuth", variable=self.codex_oauth_var).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Codex Auth", command=self.open_codex_auth_from_settings).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Save Settings", command=self.save_settings).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Reload .env", command=self.refresh_env).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Open .env Folder", command=lambda: webbrowser.open(ENV_PATH.parent.as_uri())).pack(side=tk.LEFT, padx=4)

        output_frame = ttk.LabelFrame(panes, text="Output", padding=10)
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)
        panes.add(output_frame, weight=2)
        self.output = tk.Text(output_frame, height=20, wrap="word")
        self.output.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(output_frame, command=self.output.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.output.configure(yscrollcommand=scroll.set)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status_var, padding=(14, 0, 14, 10)).grid(row=3, column=0, sticky="ew")

    def append_output(self, text: str) -> None:
        self.output.insert(tk.END, text)
        self.output.see(tk.END)

    def refresh_env(self) -> None:
        _lines, self.env_values = read_env()
        for item in SETTINGS:
            key = item["key"]
            entry = self.entries[key]
            entry.delete(0, tk.END)
            value = self.env_values.get(key, "")
            if item["secret"] and value:
                entry.insert(0, "<configured>")
                self.secret_placeholders[key] = True
            else:
                entry.insert(0, value)
                self.secret_placeholders[key] = False
        self.codex_oauth_var.set(self.env_values.get("CODEX_OAUTH_ENABLED", "true").lower() != "false")
        self.status_var.set(f"Loaded {ENV_PATH}")

    def save_settings(self) -> None:
        updates: dict[str, str] = {}
        for item in SETTINGS:
            key = item["key"]
            value = self.entries[key].get().strip()
            if item["secret"] and self.secret_placeholders.get(key) and value == "<configured>":
                continue
            updates[key] = value
        updates["CODEX_OAUTH_ENABLED"] = "true" if self.codex_oauth_var.get() else "false"
        updates["CODEX_OAUTH_REDIRECT_URI"] = self.env_values.get("CODEX_OAUTH_REDIRECT_URI") or "http://localhost:8000/api/v1/codex-auth/callback"
        updates["CODEX_OAUTH_FRONTEND_SUCCESS_URL"] = preferred_frontend_url()
        updates["CODEX_OAUTH_FRONTEND_ERROR_URL"] = preferred_frontend_url()
        write_env(updates)
        self.refresh_env()
        self.append_output(f"Saved {len(updates)} settings to {ENV_PATH}\n")

    def open_codex_auth_from_settings(self) -> None:
        self.codex_oauth_var.set(True)
        self.save_settings()
        open_codex_auth()

    def selected_enhancement_args(self) -> tuple[str, ...]:
        flags: list[str] = []
        for item in STARTUP_ENHANCEMENTS:
            if self.enhancement_vars[item["key"]].get():
                flags.append(item["flag"])
        return tuple(flags)

    def run_action(self, action: str, *extra: str) -> None:
        self.append_output(f"\n$ {action} {' '.join(extra)}\n")
        self.status_var.set(f"Running {action}...")

        def worker() -> None:
            try:
                proc = run_platform_action(action, *extra)
                assert proc.stdout is not None
                for line in proc.stdout:
                    self.after(0, self.append_output, line)
                code = proc.wait()
                self.after(0, self.status_var.set, f"{action} exited with {code}")
                if code == 0 and action == "docker-start":
                    self.after(0, self.open_docker_launcher_when_ready)
            except Exception as exc:
                self.after(0, self.append_output, f"ERROR: {exc}\n")
                self.after(0, self.status_var.set, f"{action} failed")

        threading.Thread(target=worker, daemon=True).start()

    def open_docker_launcher_when_ready(self) -> None:
        def waiter() -> None:
            for _ in range(60):
                if url_reachable("http://127.0.0.1:5176", timeout=1.0):
                    webbrowser.open("http://127.0.0.1:5176")
                    self.after(0, self.append_output, "Opened Docker Launcher: http://127.0.0.1:5176\n")
                    return
                time.sleep(1)
            self.after(0, self.append_output, "Docker Launcher did not become reachable on :5176 within 60s\n")

        threading.Thread(target=waiter, daemon=True).start()

    def run_doctor(self) -> None:
        self.run_action("doctor")

    def refresh_status(self) -> None:
        self.run_action("config-status")


def main() -> int:
    try:
        app = LauncherApp()
    except tk.TclError as exc:
        print(f"Cannot open GUI window: {exc}", file=sys.stderr)
        print("Graphical settings require a desktop session with Tk support.", file=sys.stderr)
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
