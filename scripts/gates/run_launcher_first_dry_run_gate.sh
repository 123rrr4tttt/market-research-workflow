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
    "launcher_agent": "main/ops/launcher-agent/launcher_agent.py",
    "launch_py": "scripts/launch.py",
    "build_macos_launcher": "scripts/build-macos-launcher.sh",
    "compose": "main/ops/docker-compose.yml",
    "launcher_nginx": "main/ops/launcher-ui/nginx.conf",
    "swift_launcher": "tools/macos/Launcher.swift",
    "local_deploy": "scripts/local-deploy.sh",
    "local_service_control": "scripts/local-service-control.sh",
    "start_local": "main/backend/start-local.sh",
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
        "name": "launcher_start_does_not_build_images_inline",
        "passed": '["up", "-d", "--no-build", *services]' in contents["launcher_agent"]
        and '["up", "-d", "--no-build", service]' in contents["launcher_agent"]
        and "COMPOSE_OPERATION_LOCK" in contents["launcher_agent"],
        "evidence": files["launcher_agent"],
    },
    {
        "name": "compose_dependencies_stay_container_internal",
        "passed": all(
            mapping not in contents["compose"]
            for mapping in ("127.0.0.1:5432:5432", "127.0.0.1:6379:6379", "127.0.0.1:9200:9200")
        ),
        "evidence": files["compose"],
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
        "passed": has_all(contents["compose"], ["launcher-ui:", "launcher-agent:", "5176:80", "profiles:", "- modern-ui"])
        and '127.0.0.1:8787:8787' not in contents["compose"]
        and "proxy_pass http://launcher-agent:8787/api/launcher/;" in contents["launcher_nginx"],
        "evidence": f"{files['compose']} + {files['launcher_nginx']}",
    },
    {
        "name": "macos_swift_launcher_build_entry_exists",
        "passed": has_all(contents["build_macos_launcher"], ["tools/macos/Launcher.swift", "swiftc", "Market Research Workflow.app"])
        and bool(contents["swift_launcher"]),
        "evidence": f"{files['build_macos_launcher']} + {files['swift_launcher']}",
    },
    {
        "name": "swift_monitor_preserves_cwd_and_separates_runtime_owners",
        "passed": has_all(
            contents["swift_launcher"],
            [
                "docker_services=$( (cd main/ops",
                "local_backend=",
                "docker_backend=",
                "docker_frontend=",
                "docker_worker=",
                "main/backend/.env",
            ],
        ),
        "evidence": files["swift_launcher"],
    },
    {
        "name": "swift_deep_health_requires_json_status_ok",
        "passed": has_all(
            contents["swift_launcher"],
            ['json.load(sys.stdin).get("status","")', '[ "$deep_status" = "ok" ]'],
        ),
        "evidence": files["swift_launcher"],
    },
    {
        "name": "swift_docker_stack_requires_three_core_services",
        "passed": has_all(
            contents["swift_launcher"],
            [
                "has_docker_service backend",
                "has_docker_service frontend-modern",
                "has_docker_service celery-worker",
                "dockerRunningCount >= 3",
            ],
        ),
        "evidence": files["swift_launcher"],
    },
    {
        "name": "swift_launcher_url_probes_5176",
        "passed": "curl -fsS --max-time 2 http://127.0.0.1:5176" in contents["swift_launcher"],
        "evidence": files["swift_launcher"],
    },
    {
        "name": "macos_settings_cover_current_external_service_contract",
        "passed": has_all(
            contents["swift_launcher"],
            [
                "AZURE_SEARCH_ENDPOINT",
                "AZURE_SEARCH_KEY",
                "launcherSettingsUpdates()",
            ],
        ),
        "evidence": files["swift_launcher"],
    },
    {
        "name": "local_backend_action_is_backend_only_and_non_destructive",
        "passed": has_all(
            contents["local_deploy"] + contents["start_local"] + contents["local_service_control"],
            [
                "--backend-only",
                "BACKEND_ONLY=1",
                "start --backend-only --no-local-worker --non-interactive",
            ],
        )
        and "start --force --no-local-worker" not in contents["local_service_control"],
        "evidence": f"{files['local_deploy']} + {files['start_local']} + {files['local_service_control']}",
    },
    {
        "name": "docker_launcher_help_and_build_are_guarded",
        "passed": has_all(
            contents["docker_launcher_ui"],
            ["-h|--help", "UP_BUILD_ARG=(--no-build)", '--project-name "$LAUNCHER_PROJECT_NAME" --profile modern-ui stop', 'up -d "${UP_BUILD_ARG[@]}"'],
        )
        and "--build launcher-agent launcher-ui" not in contents["docker_launcher_ui"],
        "evidence": files["docker_launcher_ui"],
    },
    {
        "name": "macos_launcher_build_is_staged_and_verified",
        "passed": has_all(
            contents["build_macos_launcher"],
            ["mktemp", "replace_app", "codesign --verify --deep --strict --verbose=2", "trap cleanup EXIT"],
        ),
        "evidence": files["build_macos_launcher"],
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
