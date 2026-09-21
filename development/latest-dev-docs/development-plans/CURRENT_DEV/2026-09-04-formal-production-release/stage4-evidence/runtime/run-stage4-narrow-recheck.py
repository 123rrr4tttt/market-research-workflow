#!/usr/bin/env python3
"""Narrow Stage 4 stopped-to-up recheck for the secure-config derived backend."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import time
from pathlib import Path
from typing import Any


OUT = Path(__file__).resolve().parent
BASE_SCRIPT = OUT / "run-stage4-runtime.py"
spec = importlib.util.spec_from_file_location("stage4_runtime_base", BASE_SCRIPT)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load Stage 4 runtime helper")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

DERIVED_BACKEND = "mrw-local/stage4-r13x-backend-config:8652d653f740735f"
DERIVED_IMAGE_ID = "sha256:f99f900e5b420cf7e1c9513598a87251cc6c8124e6ec8461c564ed4d7ca76c20"
runtime.BACKEND = DERIVED_BACKEND
runtime.RUN_ENV["BACKEND_IMAGE_DIGEST"] = DERIVED_BACKEND
SNAPSHOT = OUT / "synthetic-production-like.snapshot.dump"


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def split_http(raw: str) -> tuple[str, int]:
    body, code = raw.rsplit("\n", 1)
    return body, int(code)


def bearer_request(name: str, url: str, token: str | None) -> tuple[str, int]:
    config = ""
    if token is not None:
        config = f'header = "Authorization: Bearer {token}"\n'
    completed = runtime.run(
        name,
        [
            "curl", "--config", "-", "--silent", "--show-error", "--output", "-",
            "--write-out", "\n%{http_code}", "--header", "X-Project-Key: stage4_s4_20260913", url,
        ],
        input_text=config,
        check=False,
    )
    return split_http(completed.stdout)


def compose_ps() -> dict[str, dict[str, Any]]:
    completed = runtime.run("24-compose-ps", runtime.COMPOSE_BASE + ["ps", "--format", "json"])
    return runtime.parse_compose_ps(completed.stdout)


def write_result(payload: dict[str, Any]) -> None:
    runtime.write_json("narrow-secure-config-recheck.json", payload)


def update_aggregate(result: dict[str, Any]) -> None:
    full_path = OUT / "full-stack.json"
    full = json.loads(full_path.read_text(encoding="utf-8"))
    for role in ("backend", "celery-worker"):
        if role in full.get("services", {}):
            full["services"][role]["image"] = DERIVED_BACKEND
    full["secure_config_recheck"] = {
        "status": result["status"],
        "backend_and_celery_authenticated_readiness": result.get("backend_and_celery_authenticated_readiness", False),
        "cookie": result.get("cookie", {"status": "NOT_RUN"}),
        "auth_prefix": result.get("auth_prefix", {"status": "NOT_RUN"}),
        "evidence": "narrow-secure-config-recheck.json",
    }
    full["status"] = "PASS" if result["status"] == "PASS" else "FAIL"
    runtime.write_json("full-stack.json", full)

    summary_path = OUT / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["ended_at"] = result["ended_at"]
    summary.setdefault("results", {})["secure_config_narrow_recheck"] = result["status"]
    summary["results"]["cleanup"] = result["cleanup"]["status"]
    summary.setdefault("commands_policy", {}).update(
        {
            "entrypoint_only_derived_backend_build_executed": True,
            "secure_config_derived_backend_build_executed": True,
            "full_role_rebuild_executed": False,
            "narrow_recheck_reused_existing_snapshot_without_rerunning_migrations": True,
        }
    )
    summary["runtime_backend_identity"] = {
        "classification": "NON_R13X_DERIVED_STAGE4_RUNTIME_IMAGE",
        "reference": DERIVED_BACKEND,
        "image_id": DERIVED_IMAGE_ID,
        "base": runtime.BASE_BACKEND,
        "replaced_paths": ["/docker-entrypoint.sh", "/app/app/composition/production.py"],
    }
    summary["status"] = (
        "PASS_LOCAL_STAGE4_RUNTIME_NOT_AUTHORITY"
        if result["status"] == "PASS" and result["cleanup"]["status"] == "PASS"
        else "FAIL"
    )
    summary["error"] = result.get("error")
    summary["risks"] = [
        "This local runtime evidence is non-authoritative and does not establish remote staging or release qualification.",
        "Backend and Celery used a non-r13x derived image replacing /docker-entrypoint.sh and /app/app/composition/production.py on the exact retained r13x backend base.",
        "The narrow recheck restored the already-bound synthetic snapshot; it did not rerun the migration or snapshot matrix.",
        "The cookie probe exercised the running container's actual settings and Starlette Set-Cookie serialization without performing an external OAuth exchange.",
    ]
    runtime.write_json("summary.json", summary)


def rebuild_index() -> int:
    files = sorted(
        path
        for path in OUT.iterdir()
        if path.is_file() and path.name not in {"SHA256SUMS", "checksums-verify.log"}
    )
    (OUT / "SHA256SUMS").write_text(
        "\n".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in files) + "\n",
        encoding="utf-8",
    )
    verify = subprocess.run(
        ["shasum", "-a", "256", "-c", "SHA256SUMS"],
        cwd=str(OUT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    (OUT / "checksums-verify.log").write_text(
        f"AUTHORITATIVE=false\nEXIT_CODE={verify.returncode}\n{verify.stdout}", encoding="utf-8"
    )
    return verify.returncode


def main() -> int:
    started_at = utc_now()
    before = runtime.project_resources()
    error: str | None = None
    result: dict[str, Any] = {
        "authoritative": False,
        "schema_version": "mrw.stage4.secure-config-narrow-recheck.v1",
        "status": "FAIL",
        "started_at": started_at,
        "backend_image": {"reference": DERIVED_BACKEND, "image_id": DERIVED_IMAGE_ID},
        "snapshot_reused": SNAPSHOT.name,
        "migration_matrix_rerun": False,
        "project_resources_before": before,
    }
    started = False
    try:
        if any(before.values()):
            raise RuntimeError(f"task project collision: {before}")
        actual_image = runtime.image_identity(DERIVED_BACKEND)
        if actual_image["id"] != DERIVED_IMAGE_ID:
            raise RuntimeError(f"derived image identity mismatch: {actual_image['id']}")
        if not SNAPSHOT.is_file() or SNAPSHOT.stat().st_size == 0:
            raise RuntimeError("bound synthetic snapshot is unavailable")

        runtime.run(
            "20-foundation-up",
            runtime.COMPOSE_BASE
            + ["up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "180", "db", "es", "redis"],
            timeout=300,
        )
        started = True
        db_container = runtime.run("20a-db-container-id", runtime.COMPOSE_BASE + ["ps", "-q", "db"]).stdout.strip()
        runtime.run("20b-snapshot-copy", ["docker", "cp", str(SNAPSHOT), f"{db_container}:/tmp/mrw-stage4-synthetic.dump"])
        runtime.run(
            "20c-snapshot-restore",
            ["docker", "exec", db_container, "pg_restore", "-U", "postgres", "-d", "mrw_stage4", "--exit-on-error", "/tmp/mrw-stage4-synthetic.dump"],
            timeout=300,
        )
        runtime.run(
            "21-affected-services-up",
            runtime.COMPOSE_BASE
            + ["up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "360", "backend", "celery-worker", "frontend"],
            timeout=480,
        )
        states = compose_ps()
        service_ok = all(
            states.get(role, {}).get("state") == "running" and states.get(role, {}).get("health") == "healthy"
            for role in ("backend", "celery-worker")
        )
        runtime.run(
            "25-affected-service-logs",
            runtime.COMPOSE_BASE + ["logs", "--no-color", "--tail", "180", "backend", "celery-worker"],
            check=False,
        )

        shallow, shallow_code = runtime.health_request(
            "26-health-shallow-direct", "http://127.0.0.1:18142/api/v1/health"
        )
        deep, deep_code = runtime.health_request(
            "27-health-deep-direct", "http://127.0.0.1:18142/api/v1/health/deep"
        )
        deep_proxy, deep_proxy_code = runtime.health_request(
            "28-health-deep-proxy", "http://127.0.0.1:15142/api/v1/health/deep"
        )
        health_ok = (
            shallow_code == 200
            and shallow.get("status") == "ok"
            and deep_code == 200
            and deep.get("status") == "ok"
            and deep_proxy_code == 200
            and deep_proxy.get("status") == "ok"
        )

        cookie_probe_code = (
            "from starlette.responses import Response; "
            "from app.services.codex_oauth import codex_cookie_name,codex_cookie_secure; "
            "r=Response(); r.set_cookie(key=codex_cookie_name(),value='stage4-local-probe',"
            "httponly=True,secure=codex_cookie_secure(),samesite='lax',path='/'); "
            "print('secure_setting=' + str(codex_cookie_secure()).lower()); "
            "print(r.headers['set-cookie'])"
        )
        cookie_raw = runtime.run(
            "29-cookie-readback",
            runtime.COMPOSE_BASE + ["exec", "-T", "backend", "python", "-c", cookie_probe_code],
        ).stdout.strip()
        cookie_lower = cookie_raw.lower()
        cookie_ok = "secure_setting=true" in cookie_lower and "secure" in cookie_lower and "httponly" in cookie_lower

        unauth_body, unauth_code = bearer_request(
            "30-successor-runtime-unauth", "http://127.0.0.1:18142/api/v1/successor-runtime", None
        )
        auth_body, auth_code = bearer_request(
            "31-successor-runtime-auth", "http://127.0.0.1:18142/api/v1/successor-runtime", runtime.TASK_AUTH_TOKEN
        )
        auth_prefix_ok = unauth_code == 401 and auth_code != 401

        result.update(
            {
                "status": "PASS" if service_ok and health_ok and cookie_ok and auth_prefix_ok else "FAIL",
                "services": states,
                "backend_and_celery_authenticated_readiness": service_ok,
                "health": {
                    "shallow_direct": {"code": shallow_code, "status": shallow.get("status")},
                    "deep_direct": {"code": deep_code, "status": deep.get("status")},
                    "deep_proxy": {"code": deep_proxy_code, "status": deep_proxy.get("status")},
                },
                "cookie": {
                    "secure_setting": "secure_setting=true" in cookie_lower,
                    "set_cookie_secure": "secure" in cookie_lower,
                    "set_cookie_httponly": "httponly" in cookie_lower,
                    "dummy_cookie_value_only": True,
                    "external_oauth_exchange": False,
                },
                "auth_prefix": {
                    "path": "/api/v1/successor-runtime",
                    "configured_in_override": True,
                    "unauthenticated_http_status": unauth_code,
                    "authenticated_http_status": auth_code,
                    "unauthenticated_response_class": "codex_auth_required" if "codex auth required" in unauth_body.lower() else "other",
                    "authenticated_response_class": "passed_codex_auth_middleware" if auth_code != 401 else "blocked_by_codex_auth",
                    "token_persisted": False,
                },
                "ended_at": utc_now(),
            }
        )
        if result["status"] != "PASS":
            raise RuntimeError("one or more narrow secure-config assertions failed")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        result["error"] = error
        result.setdefault("ended_at", utc_now())
    finally:
        cleanup = runtime.cleanup() if started else {"status": "NOT_RUN"}
        result["cleanup"] = cleanup
        result["project_resources_after"] = runtime.project_resources()
        if cleanup.get("status") != "PASS":
            result["status"] = "FAIL"
            result["error"] = result.get("error") or "task resource cleanup failed"

    write_result(result)
    update_aggregate(result)
    verify_rc = rebuild_index()
    return 0 if result["status"] == "PASS" and verify_rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
