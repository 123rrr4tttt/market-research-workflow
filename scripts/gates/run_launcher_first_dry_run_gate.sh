#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-$(pwd)}"
OUT_PATH="${2:-${TARGET_DIR}/artifacts/gates/launcher_first/launcher-first-dry-run.json}"

mkdir -p "$(dirname "$OUT_PATH")"

python3 - "$TARGET_DIR" "$OUT_PATH" <<'PY'
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()


def read_rel(path: str) -> str:
    target = root / path
    if not target.exists():
        return ""
    return target.read_text(encoding="utf-8")


def has_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)


files = {
    "platform_macos": "scripts/platform-macos.sh",
    "docker_launcher_ui": "scripts/docker-launcher-ui.sh",
    "docker_app_control": "scripts/docker-app-control.sh",
    "launch_py": "scripts/launch.py",
    "build_macos_launcher": "scripts/build-macos-launcher.sh",
    "compose": "main/ops/docker-compose.yml",
    "swift_launcher": "tools/macos/Launcher.swift",
}
contents = {key: read_rel(path) for key, path in files.items()}

checks = [
    {
        "name": "platform_macos_routes_docker_start_to_launcher_ui",
        "passed": has_all(contents["platform_macos"], ["docker-start)", "DOCKER_LAUNCHER_SCRIPT", 'exec "${DOCKER_LAUNCHER_SCRIPT}"']),
        "evidence": files["platform_macos"],
    },
    {
        "name": "platform_macos_exposes_docker_status",
        "passed": has_all(contents["platform_macos"], ["docker-status)", "DOCKER_APP_CONTROL_SCRIPT", 'exec "${DOCKER_APP_CONTROL_SCRIPT}" status']),
        "evidence": files["platform_macos"],
    },
    {
        "name": "launcher_ui_starts_only_launcher_services",
        "passed": has_all(contents["docker_launcher_ui"], ["launcher-agent launcher-ui", "--profile modern-ui", "wait_for_launcher", "LAUNCHER_URL"]),
        "evidence": files["docker_launcher_ui"],
    },
    {
        "name": "docker_status_is_read_only_ps",
        "passed": has_all(contents["docker_app_control"], ["status)", "docker compose", "ps --status running --services"]),
        "evidence": files["docker_app_control"],
    },
    {
        "name": "gui_launcher_exposes_docker_launcher_action",
        "passed": has_all(contents["launch_py"], ['self.run_action("docker-start")', 'self.run_action("docker-status")', 'action == "docker-start"']),
        "evidence": files["launch_py"],
    },
    {
        "name": "compose_defines_launcher_services",
        "passed": has_all(contents["compose"], ["launcher-ui:", "launcher-agent:", "5176:80", "127.0.0.1:8787:8787", "profiles:", "- modern-ui"]),
        "evidence": files["compose"],
    },
    {
        "name": "macos_swift_launcher_build_entry_exists",
        "passed": has_all(contents["build_macos_launcher"], ["tools/macos/Launcher.swift", "swiftc", "Market Research Workflow.app"])
        and bool(contents["swift_launcher"]),
        "evidence": f"{files['build_macos_launcher']} + {files['swift_launcher']}",
    },
]

try:
    git_head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
except Exception:
    git_head = None

status = "passed" if all(item["passed"] for item in checks) else "failed"
artifact = {
    "status": status,
    "gate": "launcher_first_dry_run",
    "dry_run": True,
    "destructive_actions": [],
    "checks": checks,
    "runtime_fingerprint": {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "python_version": platform.python_version(),
        "git_head": git_head,
    },
}
out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"[launcher-first-dry-run] status={status} artifact={out}")
if status != "passed":
    raise SystemExit(1)
PY
