#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-$(pwd)}"
OUT_PATH="${2:-${TARGET_DIR}/artifacts/gates/launcher_first/launcher-first-dry-run.json}"

mkdir -p "$(dirname "$OUT_PATH")"

python3 - "$TARGET_DIR" "$OUT_PATH" <<'PY'
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_files(base: Path) -> dict[str, str]:
    return {
        path.relative_to(base).as_posix(): sha256_file(path)
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def run_prepare_failure_fixture(kind: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix=f"mrw-launcher-prepare-{kind}-") as raw:
        fixture = Path(raw)
        candidate = fixture / "candidate"
        dependency_source = fixture / "dependency-source"
        copied = (
            Path("scripts/local-deploy.sh"),
            Path("main/backend/start-local.sh"),
            Path("main/backend/requirements.txt"),
            Path("main/frontend-modern/package-lock.json"),
            Path("main/ops/codex-webui/pnpm-lock.yaml"),
        )
        for relative in copied:
            target = candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, target)
        for relative in copied[2:]:
            target = dependency_source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, target)

        source_backend = dependency_source / "main/backend/.venv311"
        source_frontend = dependency_source / "main/frontend-modern/node_modules"
        source_webui = dependency_source / "main/ops/codex-webui/node_modules"
        for dependency_dir in (source_backend, source_frontend, source_webui):
            dependency_dir.mkdir(parents=True)
            (dependency_dir / "source-sentinel").write_text(kind + "\n", encoding="utf-8")
        requirements_hash = sha256_file(candidate / "main/backend/requirements.txt")
        (source_backend / ".requirements.sha256").write_text(requirements_hash + "\n", encoding="utf-8")

        candidate_backend = candidate / "main/backend/.venv311"
        candidate_frontend = candidate / "main/frontend-modern/node_modules"
        candidate_webui = candidate / "main/ops/codex-webui/node_modules"
        conflict_sentinel = candidate_backend / "candidate-sentinel"
        fake_ln_log = fixture / "fake-ln.log"
        env = os.environ.copy()
        env["MRW_DEPENDENCY_SOURCE_ROOT"] = str(dependency_source)

        if kind == "existing-conflict":
            candidate_backend.mkdir()
            conflict_sentinel.write_text("preserve\n", encoding="utf-8")
        elif kind == "link-failure":
            fake_bin = fixture / "fake-bin"
            fake_bin.mkdir()
            fake_ln = fake_bin / "ln"
            fake_ln.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$*" >> "$MRW_FAKE_LN_LOG"\nexit 73\n',
                encoding="utf-8",
            )
            fake_ln.chmod(0o755)
            env["MRW_FAKE_LN_LOG"] = str(fake_ln_log)
            env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        else:
            raise ValueError(f"unknown prepare fixture: {kind}")

        source_before = snapshot_files(dependency_source)
        result = subprocess.run(
            [str(candidate / "scripts/local-deploy.sh"), "prepare"],
            cwd=candidate,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        source_after = snapshot_files(dependency_source)
        later_dependencies_absent = not candidate_frontend.exists() and not candidate_webui.exists()
        if kind == "existing-conflict":
            branch_witness = (
                conflict_sentinel.read_text(encoding="utf-8") == "preserve\n"
                and candidate_backend.resolve() != source_backend.resolve()
            )
        else:
            branch_witness = (
                fake_ln_log.is_file()
                and fake_ln_log.read_text(encoding="utf-8").startswith("-s ")
                and not candidate_backend.exists()
                and "✅ 复用 backend venv" not in stdout
            )
        return {
            "kind": kind,
            "command": "scripts/local-deploy.sh prepare",
            "returncode": result.returncode,
            "passed": (
                result.returncode != 0
                and branch_witness
                and later_dependencies_absent
                and source_before == source_after
            ),
            "branch_witness": branch_witness,
            "later_dependencies_absent": later_dependencies_absent,
            "dependency_source_unchanged": source_before == source_after,
        }


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
    "stop_local": "main/backend/stop-local.sh",
    "webui_start": "main/ops/codex-webui/start.sh",
}
contents = {key: read_rel(path) for key, path in files.items()}
prepare_function = ""
if "prepare_dependencies_only() {" in contents["start_local"]:
    prepare_function = contents["start_local"].split("prepare_dependencies_only() {", 1)[1].split("\n}", 1)[0]

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
        "name": "local_python_prefers_backend_runtime_venv",
        "passed": (
            contents["local_deploy"].index('.venv311/bin/python')
            < contents["local_deploy"].index("/Users/wangyiliang/.local/bin/python3.11")
        ),
        "evidence": files["local_deploy"],
    },
    {
        "name": "local_start_defaults_to_existing_runtime",
        "passed": has_all(
            contents["start_local"],
            ["PROVISION=0", "--provision", "ensure_runtime_dependencies_ready || exit 1"],
        )
        and 'if [ "$PROVISION" = "1" ]; then\n    ensure_db_migrated_and_seeded' in contents["start_local"],
        "evidence": files["start_local"],
    },
    {
        "name": "local_dependency_prepare_is_explicit_and_exits_before_runtime",
        "passed": has_all(
            contents["local_deploy"] + contents["start_local"],
            [
                "prepare)",
                "--prepare-dependencies",
                "PREPARE_DEPENDENCIES=0",
                "prepare_dependencies_only",
            ],
        )
        and contents["start_local"].index('if [ "$PREPARE_DEPENDENCIES" = "1" ]; then\n    prepare_dependencies_only')
        < contents["start_local"].index('if [ ! -f ".env" ]; then'),
        "evidence": f"{files['local_deploy']} + {files['start_local']}",
    },
    {
        "name": "local_dependency_prepare_is_lock_bound_and_side_effect_bounded",
        "passed": has_all(
            prepare_function,
            ["npm ci", "pnpm install --frozen-lockfile", "verify_candidate_source_imports"],
        )
        and all(
            forbidden not in prepare_function
            for forbidden in (
                "ensure_db_migrated_and_seeded",
                "docker compose",
                "compose up",
                "brew install",
                "source \".env\"",
                "uvicorn app.main:app",
            )
        ),
        "evidence": files["start_local"],
    },
    {
        "name": "fresh_root_dependency_reuse_keeps_candidate_source_authority",
        "passed": has_all(
            contents["start_local"],
            [
                "MRW_DEPENDENCY_SOURCE_ROOT",
                'cmp -s "$REQ_FILE"',
                'cmp -s "$FRONTEND_DIR/package-lock.json"',
                'cmp -s "$WEBUI_DIR/pnpm-lock.yaml"',
                '"app": root / "main" / "backend" / "app" / "__init__.py"',
                '"mrw_functorial_kit": root / "src" / "mrw_functorial_kit" / "__init__.py"',
                'export PYTHONPATH="$SCRIPT_DIR:$REPO_DIR/src:$REPO_DIR"',
                "backend runtime must be Python 3.11",
                "当前根已有不同依赖目录（$label）",
            ],
        ),
        "evidence": files["start_local"],
    },
    {
        "name": "local_frontend_defaults_to_built_preview",
        "passed": has_all(
            contents["start_local"] + contents["local_service_control"],
            [
                'FRONTEND_MODE="${FRONTEND_MODE:-preview}"',
                'FRONTEND_MODE="preview"',
                'npm run "$FRONTEND_MODE"',
                "dist/index.html",
                "--strictPort",
            ],
        )
        and "npm run dev --" not in contents["start_local"] + contents["local_service_control"],
        "evidence": f"{files['start_local']} + {files['local_service_control']}",
    },
    {
        "name": "local_stop_is_launchd_and_path_aware",
        "passed": has_all(
            contents["stop_local"] + contents["local_service_control"],
            [
                "com.mrw.successor-backend",
                "stop_owned_port_listener",
                "pid_cwd",
                "terminate_pid_gracefully",
            ],
        )
        and "lsof -ti:8000 | xargs kill -9" not in contents["stop_local"] + contents["local_service_control"],
        "evidence": f"{files['stop_local']} + {files['local_service_control']}",
    },
    {
        "name": "fresh_root_direct_control_requires_launchd_opt_in",
        "passed": has_all(
            contents["local_deploy"] + contents["local_service_control"],
            [
                'FRONTEND_USE_LAUNCHD="${FRONTEND_USE_LAUNCHD:-0}"',
                'WORKER_USE_LAUNCHD="${WORKER_USE_LAUNCHD:-0}"',
                'BACKEND_USE_LAUNCHD="${BACKEND_USE_LAUNCHD:-0}"',
                'exec "${LOCAL_SERVICE_CONTROL_SCRIPT}" local-stop',
                "stop_owned_port_listener 8000 \"$BACKEND_DIR\"",
            ],
        ),
        "evidence": f"{files['local_deploy']} + {files['local_service_control']}",
    },
    {
        "name": "webui_start_rejects_foreign_port_owner",
        "passed": has_all(
            contents["webui_start"],
            [
                "webui_port_has_foreign_owner",
                "port $PORT is owned by another process",
                "webui_launchd_has_foreign_owner",
                "launchd label $LABEL belongs to another source root",
            ],
        )
        and "launchctl print \"$DOMAIN/$LABEL\" 2>&1 | tail" not in contents["webui_start"],
        "evidence": files["webui_start"],
    },
    {
        "name": "webui_skill_source_is_current_candidate_root",
        "passed": has_all(
            contents["webui_start"],
            [
                'candidate_skill_root = (Path(root).parents[1] / "backend" / "skills").resolve()',
                "skill_source_root != candidate_skill_root",
                '"MRW_SKILL_SOURCE_ROOT": str(skill_source_root)',
            ],
        )
        and 'host_environment.get("MRW_SKILL_SOURCE_ROOT")' not in contents["webui_start"],
        "evidence": files["webui_start"],
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

prepare_failure_evidence = [
    run_prepare_failure_fixture("existing-conflict"),
    run_prepare_failure_fixture("link-failure"),
]
checks.extend(
    {
        "name": f"local_dependency_prepare_propagates_{item['kind']}",
        "passed": item["passed"],
        "evidence": "temporary fixed-root scripts/local-deploy.sh prepare fixture",
    }
    for item in prepare_failure_evidence
)

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
    "functional_evidence": {"dependency_prepare_failures": prepare_failure_evidence},
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
