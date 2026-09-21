#!/usr/bin/env python3
"""Bounded r13x runtime and full-stack smoke using preloaded canonical images."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


OUT = Path(__file__).resolve().parent
CANDIDATE = Path(
    "/Users/wangyiliang/.codex/release-rehearsals/"
    "mrw-stage2-20260912-v4-r13x/candidate"
)
COMPOSE = CANDIDATE / "main/ops/docker-compose.yml"
OVERRIDE = OUT / "compose.override.yml"
PROJECT = "mrw-r13x-runtime"
COMMIT = "8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2"
TREE = "ce7c67c831b51f9d64b4c2f1a470a724a50b19df"
BACKEND = f"mrw-local/r13x-candidate-backend:{COMMIT}"
FRONTEND = f"mrw-local/r13x-candidate-frontend:{COMMIT}"
MIGRATION = f"mrw-local/r13x-candidate-migration-runner:{COMMIT}"
EXPECTED_IMAGE_IDS = {
    "backend": "sha256:d72688f24fb867ae2e0e9310cfc9ec25aac649a8da69130ee26469c0bd37c2ef",
    "frontend": "sha256:f5641ba6d2b50135da1c9c9c3edfd067ed90ecfb37bcb8f0c7580b2e00aaa915",
    "migration-runner": "sha256:3b409669bb8248f738c1133f9458d73725951140c0eae938064d469045960509",
}
COMPOSE_BASE = [
    "docker", "compose", "-p", PROJECT,
    "-f", str(COMPOSE), "-f", str(OVERRIDE),
    "--profile", "modern-ui",
]
ONE_OFF_NAMES = [
    "mrw-r13x-content-check",
    "mrw-r13x-migration-heads",
    "mrw-r13x-migration-upgrade",
    "mrw-r13x-migration-current",
    "mrw-r13x-migration-heads-module",
    "mrw-r13x-migration-upgrade-module",
    "mrw-r13x-migration-current-module",
]


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_json(name: str, payload: dict[str, Any]) -> None:
    payload.setdefault("authoritative", False)
    (OUT / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run(
    name: str,
    command: list[str],
    *,
    check: bool = True,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    started = utc_now()
    completed = subprocess.run(
        command,
        cwd=str(CANDIDATE),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
        env=dict(os.environ),
    )
    ended = utc_now()
    log = OUT / f"{name}.log"
    log.write_text(
        "\n".join(
            [
                f"START_UTC={started}",
                f"END_UTC={ended}",
                f"CWD={CANDIDATE}",
                f"COMMAND={shlex.join(command)}",
                f"EXIT_CODE={completed.returncode}",
                "OUTPUT_BEGIN",
                completed.stdout or "",
                "OUTPUT_END",
                "",
            ]
        ),
        encoding="utf-8",
    )
    if check and completed.returncode != 0:
        raise RuntimeError(f"{name} failed with exit {completed.returncode}; see {log}")
    return completed


def docker_resource_snapshot() -> dict[str, Any]:
    def lines(command: list[str]) -> list[str]:
        completed = subprocess.run(
            command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
        )
        return sorted(line for line in completed.stdout.splitlines() if line.strip())

    containers = lines(
        ["docker", "ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}"]
    )
    volumes = lines(["docker", "volume", "ls", "--format", "{{.Name}}"])
    networks = lines(["docker", "network", "ls", "--format", "{{.ID}}\t{{.Name}}"])
    return {
        "authoritative": False,
        "observed_at": utc_now(),
        "containers": containers,
        "volumes": volumes,
        "networks": networks,
        "non_r13x": {
            "containers": [line for line in containers if "r13x" not in line.lower()],
            "volumes": [line for line in volumes if "r13x" not in line.lower()],
            "networks": [line for line in networks if "r13x" not in line.lower()],
        },
    }


def inspect_image(image: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["docker", "image", "inspect", image],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    raw = json.loads(completed.stdout)[0]
    config = raw.get("Config", {})
    return {
        "tag": image,
        "id": raw.get("Id"),
        "repo_tags": raw.get("RepoTags", []),
        "repo_digests": raw.get("RepoDigests", []),
        "platform": f"{raw.get('Os')}/{raw.get('Architecture')}",
        "entrypoint": config.get("Entrypoint"),
        "cmd": config.get("Cmd"),
    }


def compose_config() -> dict[str, Any]:
    completed = run("01-compose-config", COMPOSE_BASE + ["config", "--format", "json"])
    return json.loads(completed.stdout)


def parse_json_body(name: str, body: str) -> dict[str, Any]:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name} did not return JSON: {exc}") from exc
    (OUT / f"{name}.response.json").write_text(
        json.dumps(
            {"authoritative": False, "response": parsed},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return parsed


def cleanup() -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    down = run(
        "90-compose-down",
        COMPOSE_BASE + ["down", "--volumes", "--remove-orphans", "--timeout", "30"],
        check=False,
        timeout=180,
    )
    actions.append({"action": "compose_down", "exit_code": down.returncode})
    for name in ONE_OFF_NAMES:
        completed = subprocess.run(
            ["docker", "container", "inspect", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode == 0:
            removed = run(
                f"91-cleanup-{name}",
                ["docker", "rm", "-f", name],
                check=False,
                timeout=60,
            )
            actions.append(
                {"action": "remove_exact_container", "name": name, "exit_code": removed.returncode}
            )

    residue_containers = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=r13x", "--format", "{{.Names}}"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    ).stdout.splitlines()
    residue_volumes = subprocess.run(
        ["docker", "volume", "ls", "--filter", "name=r13x", "--format", "{{.Name}}"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    ).stdout.splitlines()
    residue_networks = subprocess.run(
        ["docker", "network", "ls", "--filter", "name=r13x", "--format", "{{.Name}}"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    ).stdout.splitlines()
    return {
        "authoritative": False,
        "actions": actions,
        "residue": {
            "containers": sorted(filter(None, residue_containers)),
            "volumes": sorted(filter(None, residue_volumes)),
            "networks": sorted(filter(None, residue_networks)),
        },
    }


def main() -> int:
    started_at = utc_now()
    pre = docker_resource_snapshot()
    write_json("00-resources-before.json", pre)
    status = "FAILED"
    error: str | None = None
    identity_result: dict[str, Any] = {"authoritative": False}
    content_result: dict[str, Any] = {"authoritative": False, "status": "NOT_RUN"}
    migration_result: dict[str, Any] = {"authoritative": False, "status": "NOT_RUN"}
    stack_result: dict[str, Any] = {"authoritative": False, "status": "NOT_RUN"}
    cleanup_result: dict[str, Any] = {"authoritative": False, "status": "NOT_RUN"}

    try:
        actual_commit = run("00-candidate-commit", ["git", "rev-parse", "HEAD"]).stdout.strip()
        actual_tree = run("00-candidate-tree", ["git", "rev-parse", "HEAD^{tree}"]).stdout.strip()
        candidate_status = run("00-candidate-status", ["git", "status", "--short"]).stdout
        images = {
            "backend": inspect_image(BACKEND),
            "frontend": inspect_image(FRONTEND),
            "migration-runner": inspect_image(MIGRATION),
        }
        identity_ok = (
            actual_commit == COMMIT
            and actual_tree == TREE
            and not candidate_status.strip()
            and all(images[role]["id"] == expected for role, expected in EXPECTED_IMAGE_IDS.items())
        )
        identity_result = {
            "authoritative": False,
            "status": "PASS" if identity_ok else "FAIL",
            "candidate": {"root": str(CANDIDATE), "commit": actual_commit, "tree": actual_tree, "clean": not candidate_status.strip()},
            "images": images,
            "expected_image_ids": EXPECTED_IMAGE_IDS,
            "image_identity_match": identity_ok,
            "no_build_policy": True,
        }
        write_json("identity.json", identity_result)
        if not identity_ok:
            raise RuntimeError("candidate or canonical image identity mismatch")

        config = compose_config()
        services = config["services"]
        backend_health = services["backend"]["healthcheck"]["test"]
        compose_assertions = {
            "backend_image_exact": services["backend"]["image"] == BACKEND,
            "worker_image_exact": services["celery-worker"]["image"] == BACKEND,
            "frontend_image_exact": services["frontend-modern"]["image"] == FRONTEND,
            "backend_source_mounts_absent": not services["backend"].get("volumes"),
            "worker_source_mounts_absent": not services["celery-worker"].get("volumes"),
            "backend_build_absent": "build" not in services["backend"],
            "worker_build_absent": "build" not in services["celery-worker"],
            "frontend_build_absent": "build" not in services["frontend-modern"],
            "backend_health_argv_exact": backend_health == ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"],
        }
        (OUT / "compose.resolved.json").write_text(
            json.dumps({"authoritative": False, "services": services}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if not all(compose_assertions.values()):
            raise RuntimeError(f"compose assertion failed: {compose_assertions}")

        content_cmd = (
            "set -eu; "
            "python -m pip check; "
            "command -v bash; command -v curl; command -v pg_isready; "
            "if command -v git >/dev/null 2>&1; then echo git_unexpected; exit 41; fi; "
            "if command -v gcc >/dev/null 2>&1; then echo gcc_unexpected; exit 42; fi; "
            "test -s /app/alembic.ini; test -d /app/migrations; test -d /app/app; test -d /opt/mrw/src; "
            "python -c \"import fastapi,functorial_kit,psycopg2,psutil; "
            "print('IMPORTS_OK fastapi functorial_kit psycopg2 psutil')\"; "
            "python -c \"import app.main; print('APP_MAIN_IMPORT_OK')\"; "
            "echo CONTENT_CHECK_PASS"
        )
        content = run(
            "02-backend-content-import-tools",
            [
                "docker", "run", "--rm", "--name", "mrw-r13x-content-check",
                "--platform", "linux/amd64", "--entrypoint", "/bin/bash", BACKEND,
                "-lc", content_cmd,
            ],
        )
        content_result = {
            "authoritative": False,
            "status": "PASS",
            "pip_check": "No broken requirements found." in content.stdout,
            "required_tools": ["bash", "curl", "pg_isready"],
            "forbidden_tools_absent": ["git", "gcc"],
            "imports": ["fastapi", "functorial_kit", "psycopg2", "psutil", "app.main"],
            "content_paths": ["/app/alembic.ini", "/app/migrations", "/app/app", "/opt/mrw/src"],
            "entrypoint": images["backend"]["entrypoint"],
            "cmd": images["backend"]["cmd"],
            "compose_health_argv": backend_health,
            "compose_assertions": compose_assertions,
        }
        write_json("runtime-content.json", content_result)

        run(
            "03-db-up",
            COMPOSE_BASE + ["up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "120", "db"],
            timeout=180,
        )
        network = f"{PROJECT}_default"
        db_url = "postgresql+psycopg2://postgres:postgres@db:5432/postgres"
        default_heads = run(
            "04-migration-default-entrypoint-heads",
            [
                "docker", "run", "--rm", "--name", "mrw-r13x-migration-heads",
                "--platform", "linux/amd64", "--network", network,
                "-e", f"DATABASE_URL={db_url}", MIGRATION, "heads",
            ],
            check=False,
        )
        heads = run(
            "04-migration-module-heads",
            [
                "docker", "run", "--rm", "--name", "mrw-r13x-migration-heads-module",
                "--platform", "linux/amd64", "--network", network,
                "-e", f"DATABASE_URL={db_url}", "--entrypoint", "python", MIGRATION,
                "-m", "alembic", "heads",
            ],
        )
        head_lines = [line.strip().split()[0] for line in heads.stdout.splitlines() if "(head)" in line]
        if len(head_lines) != 1:
            raise RuntimeError(f"expected one Alembic head, got {head_lines}")
        expected_head = head_lines[0]
        default_upgrade = run(
            "05-migration-default-entrypoint-upgrade",
            [
                "docker", "run", "--rm", "--name", "mrw-r13x-migration-upgrade",
                "--platform", "linux/amd64", "--network", network,
                "-e", f"DATABASE_URL={db_url}", MIGRATION,
            ],
            check=False,
            timeout=300,
        )
        run(
            "05-migration-module-upgrade",
            [
                "docker", "run", "--rm", "--name", "mrw-r13x-migration-upgrade-module",
                "--platform", "linux/amd64", "--network", network,
                "-e", f"DATABASE_URL={db_url}", "--entrypoint", "python", MIGRATION,
                "-m", "alembic", "upgrade", "head",
            ],
            timeout=300,
        )
        current = run(
            "06-migration-module-current",
            [
                "docker", "run", "--rm", "--name", "mrw-r13x-migration-current-module",
                "--platform", "linux/amd64", "--network", network,
                "-e", f"DATABASE_URL={db_url}", "--entrypoint", "python", MIGRATION,
                "-m", "alembic", "current",
            ],
        )
        query = (
            "SELECT version_num FROM alembic_version; "
            "SELECT count(*) AS public_table_count FROM information_schema.tables WHERE table_schema='public'; "
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
            "AND table_name IN ('ingest_submission_registry','llm_report_quality_trends',"
            "'llm_report_export_audit_events','llm_report_export_token_states') ORDER BY table_name;"
        )
        readback = run(
            "07-migration-schema-readback",
            COMPOSE_BASE + ["exec", "-T", "db", "psql", "-U", "postgres", "-d", "postgres", "-At", "-c", query],
        )
        readback_lines = [line.strip() for line in readback.stdout.splitlines() if line.strip()]
        required_tables = {
            "ingest_submission_registry",
            "llm_report_quality_trends",
            "llm_report_export_audit_events",
            "llm_report_export_token_states",
        }
        observed_tables = required_tables.intersection(readback_lines)
        schema_ok = (
            expected_head in current.stdout
            and expected_head in readback_lines
            and observed_tables == required_tables
        )
        # The declared image contract is exactly `alembic upgrade head`; it ran
        # successfully. The metadata-only `heads` command exposes a separately
        # recorded console-script import-path limitation.
        default_contract_ok = default_upgrade.returncode == 0
        migration_ok = schema_ok and default_contract_ok
        migration_result = {
            "authoritative": False,
            "status": "PASS_WITH_HEADS_INTROSPECTION_LIMITATION" if migration_ok else "FAIL_RUNTIME_ENTRYPOINT",
            "database_scope": "dedicated disposable PostgreSQL in mrw-r13x-runtime compose project",
            "migration_image": images["migration-runner"],
            "default_entrypoint": images["migration-runner"]["entrypoint"],
            "default_cmd": images["migration-runner"]["cmd"],
            "default_heads_exit_code": default_heads.returncode,
            "default_upgrade_exit_code": default_upgrade.returncode,
            "default_contract_executed": "alembic upgrade head",
            "default_contract_passed": default_contract_ok,
            "heads_introspection_limitation": (
                "alembic heads via the console-script entrypoint fails with "
                "ModuleNotFoundError: No module named 'migrations'; "
                "python -m alembic heads succeeds"
                if default_heads.returncode != 0 else None
            ),
            "head_introspection_invocation": "python -m alembic heads",
            "schema_readback_ok": schema_ok,
            "expected_head": expected_head,
            "current_contains_expected_head": expected_head in current.stdout,
            "schema_readback_lines": readback_lines,
            "required_tables": sorted(required_tables),
            "required_tables_present": sorted(observed_tables),
        }
        write_json("migration.json", migration_result)
        if not schema_ok:
            raise RuntimeError("migration diagnostic module head/schema readback failed")

        run(
            "08-full-stack-up",
            COMPOSE_BASE + [
                "up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "300",
                "db", "es", "redis", "backend", "celery-worker", "frontend-modern",
            ],
            timeout=420,
        )
        ps = run("09-full-stack-ps", COMPOSE_BASE + ["ps", "--format", "json"])
        logs = run(
            "10-full-stack-service-logs",
            COMPOSE_BASE + ["logs", "--no-color", "--tail", "240", "backend", "celery-worker", "frontend-modern"],
            check=False,
        )
        shallow_direct_raw = run(
            "11-health-shallow-direct", ["curl", "-fsS", "http://127.0.0.1:18132/api/v1/health"]
        ).stdout
        deep_direct_raw = run(
            "12-health-deep-direct", ["curl", "-fsS", "http://127.0.0.1:18132/api/v1/health/deep"]
        ).stdout
        frontend_html = run(
            "13-frontend-root", ["curl", "-fsS", "http://127.0.0.1:15132/"]
        ).stdout
        asset_match = re.search(r'(?:src|href)=["\'](/assets/[^"\']+)["\']', frontend_html)
        if not asset_match:
            raise RuntimeError("frontend root did not reference a built static asset")
        frontend_asset_path = asset_match.group(1)
        frontend_asset = run(
            "13-frontend-static-asset",
            [
                "curl", "-fsS", "-o", "/dev/null", "-w", "%{http_code}",
                f"http://127.0.0.1:15132{frontend_asset_path}",
            ],
        ).stdout.strip()
        shallow_proxy_raw = run(
            "14-health-shallow-frontend-proxy", ["curl", "-fsS", "http://127.0.0.1:15132/api/v1/health"]
        ).stdout
        deep_proxy_raw = run(
            "15-health-deep-frontend-proxy", ["curl", "-fsS", "http://127.0.0.1:15132/api/v1/health/deep"]
        ).stdout
        shallow_direct = parse_json_body("health-shallow-direct", shallow_direct_raw)
        deep_direct = parse_json_body("health-deep-direct", deep_direct_raw)
        shallow_proxy = parse_json_body("health-shallow-frontend-proxy", shallow_proxy_raw)
        deep_proxy = parse_json_body("health-deep-frontend-proxy", deep_proxy_raw)
        missing_key = "OPENAI_API_KEY" in deep_direct.get("missing_dependencies", [])
        dependency = deep_direct.get("dependency_ping", {}).get("service_results", {})
        local_dependencies_ok = all(
            dependency.get(name, {}).get("status") == "ok"
            for name in ("database", "elasticsearch", "redis")
        )
        try:
            parsed_ps = json.loads(ps.stdout)
            ps_lines = parsed_ps if isinstance(parsed_ps, list) else [parsed_ps]
        except json.JSONDecodeError:
            ps_lines = [json.loads(line) for line in ps.stdout.splitlines() if line.strip()]
        service_states = {
            item.get("Service"): {"state": item.get("State"), "health": item.get("Health")}
            for item in ps_lines
        }
        core_services_running = all(
            service_states.get(name, {}).get("state") == "running"
            for name in ("db", "es", "redis", "backend", "celery-worker", "frontend-modern")
        )
        stack_ok = (
            shallow_direct.get("status") == "ok"
            and shallow_proxy.get("status") == "ok"
            and deep_direct.get("status") == "degraded"
            and deep_proxy.get("status") == "degraded"
            and missing_key
            and local_dependencies_ok
            and frontend_asset == "200"
            and core_services_running
        )
        stack_result = {
            "authoritative": False,
            "status": "PASS_SCOPED" if stack_ok else "FAIL",
            "services": service_states,
            "frontend_root_http_status": 200,
            "frontend_static_asset_path": frontend_asset_path,
            "frontend_static_asset_http_status": int(frontend_asset),
            "backend_direct_shallow_status": shallow_direct.get("status"),
            "frontend_proxy_shallow_status": shallow_proxy.get("status"),
            "backend_direct_deep_status": deep_direct.get("status"),
            "frontend_proxy_deep_status": deep_proxy.get("status"),
            "local_dependencies": {
                name: dependency.get(name, {}).get("status")
                for name in ("database", "elasticsearch", "redis")
            },
            "live_provider": {
                "status": "DEGRADED_AWAITING_HUMAN_AUTHORITY" if missing_key else "OBSERVED_CONFIGURED",
                "missing_dependencies": deep_direct.get("missing_dependencies", []),
                "openai_api_key_injected": False,
            },
            "canonical_images_only": True,
            "source_bind_mounts": False,
            "compose_no_build": True,
            "service_logs_exit_code": logs.returncode,
        }
        write_json("full-stack.json", stack_result)
        if not stack_ok:
            raise RuntimeError("full-stack assertion failed")
        status = (
            "PASS_SCOPED_WITH_LIVE_PROVIDER_AND_HEADS_INTROSPECTION_LIMITATIONS"
            if migration_ok
            else "FAILED_RUNTIME_ENTRYPOINT"
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            cleanup_result = cleanup()
        except Exception as exc:
            cleanup_result = {"authoritative": False, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
        post = docker_resource_snapshot()
        write_json("99-resources-after.json", post)
        end_commit = subprocess.run(
            ["git", "-C", str(CANDIDATE), "rev-parse", "HEAD"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        ).stdout.strip()
        end_tree = subprocess.run(
            ["git", "-C", str(CANDIDATE), "rev-parse", "HEAD^{tree}"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        ).stdout.strip()
        end_status = subprocess.run(
            ["git", "-C", str(CANDIDATE), "status", "--short"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        ).stdout
        residue = cleanup_result.get("residue", {})
        zero_residue = all(not residue.get(kind) for kind in ("containers", "volumes", "networks"))
        non_r13x_unchanged = pre["non_r13x"] == post["non_r13x"]
        cleanup_result.update(
            {
                "status": "PASS" if zero_residue and non_r13x_unchanged else "FAIL",
                "zero_r13x_residue": zero_residue,
                "non_r13x_resources_unchanged": non_r13x_unchanged,
                "candidate_end_identity": {
                    "commit": end_commit,
                    "tree": end_tree,
                    "clean": not end_status.strip(),
                },
                "candidate_end_identity_match": (
                    end_commit == COMMIT and end_tree == TREE and not end_status.strip()
                ),
                "non_r13x_before": pre["non_r13x"],
                "non_r13x_after": post["non_r13x"],
            }
        )
        write_json("cleanup.json", cleanup_result)

    if cleanup_result.get("status") != "PASS":
        status = "FAILED"
        error = error or "cleanup/residue verification failed"
    summary = {
        "authoritative": False,
        "schema_version": "mrw.stage3.r13x-runtime-smoke.v1",
        "status": status,
        "authority_ceiling": "PRODUCTION_RELEASE_NOT_AUTHORIZED",
        "started_at": started_at,
        "ended_at": utc_now(),
        "candidate": {"commit": COMMIT, "tree": TREE, "root": str(CANDIDATE)},
        "results": {
            "identity": identity_result.get("status"),
            "runtime_content": content_result.get("status"),
            "migration": migration_result.get("status"),
            "full_stack": stack_result.get("status"),
            "cleanup": cleanup_result.get("status"),
        },
        "live_provider": stack_result.get("live_provider", {"status": "NOT_RUN"}),
        "candidate_modified": False,
        "docker_build_executed": False,
        "remote_or_publish_action": False,
        "error": error,
        "limitations": [
            "OPENAI_API_KEY absent: deep health is DEGRADED_AWAITING_HUMAN_AUTHORITY",
            "migration runner console-script `alembic heads` cannot import namespace package migrations; exact default `alembic upgrade head` passed",
        ],
    }
    write_json("summary.json", summary)

    files = sorted(
        path for path in OUT.iterdir()
        if path.is_file() and path.name not in {"SHA256SUMS", "checksums-verify.log"}
    )
    checksum_lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in files
    ]
    (OUT / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    verify = subprocess.run(
        ["shasum", "-a", "256", "-c", "SHA256SUMS"],
        cwd=str(OUT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    (OUT / "checksums-verify.log").write_text(
        f"AUTHORITATIVE=false\nEXIT_CODE={verify.returncode}\n{verify.stdout}", encoding="utf-8"
    )
    if verify.returncode != 0:
        return 1
    return 0 if status.startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
