#!/usr/bin/env python3
"""Run the bounded Stage 5 database recovery and migration-failure drill."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any


OUT = Path(__file__).resolve().parent
WORKSPACE = Path("/Users/wangyiliang/market-research-workflow")
STAGE4 = (
    WORKSPACE
    / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/stage4-evidence"
)
CANDIDATE = Path(
    "/Users/wangyiliang/.codex/release-rehearsals/"
    "mrw-stage2-20260912-v4-r13x/candidate"
)
COMPOSE_FILE = CANDIDATE / "main/ops/docker-compose.production.yml"
OVERRIDE = OUT / "compose.recovery.yml"
SNAPSHOT = STAGE4 / "runtime/synthetic-production-like.snapshot.dump"
SEED = STAGE4 / "runtime/seed-c9-effect.py"
PROJECT = "mrw-stage5-recovery"
PORT = 18152
PROJECT_KEY = "stage5_recovery_20260913"
PROJECT_SCHEMA = "project_stage5_recovery_20260913"
INCARNATION = "incarnation:stage5-recovery:v1"
SOURCE_DB = "mrw_stage5_recovery"
RESTORE_DB = "mrw_stage5_restore"
MIGRATION_DB = "mrw_stage5_migration_probe"
BACKEND_IMAGE = "mrw-local/stage4-business001:stage4-c9-effect"
BACKEND_IMAGE_ID = "sha256:f247a1492400311e032710df01f84365c7e700f61c122b7243ae58eda982af19"
DB_IMAGE = "ankane/pgvector:latest"
DB_IMAGE_ID = "sha256:956744bd14e9cbdf639c61c2a2a7c7c2c48a9c8cdd42f7de4ac034f4e96b90f8"
ES_IMAGE = "docker.elastic.co/elasticsearch/elasticsearch:8.15.3"
ES_IMAGE_ID = "sha256:01c1732062b4a846c5ca687b0094b89bad0bfed00c6d71626db32fb8f3131a78"
REDIS_IMAGE = "redis:7.4"
REDIS_IMAGE_ID = "sha256:71da9275c5f3fcb97d0fa0c8c5b36cc995327265420f17a04bfd544f458059f7"
MIGRATION_IMAGE = "mrw-local/r13x-candidate-migration-runner:8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2"
MIGRATION_IMAGE_ID = "sha256:3b409669bb8248f738c1133f9458d73725951140c0eae938064d469045960509"
HEAD = "20260905_000001"
PARENT = "20260830_000001"
COMMAND_ID = "cmd:stage5:recovery:c9"
APPROVAL_ID = "approval:stage5:recovery:c9"
PROJECTION_ID = "projection.c9-movement-closure.v1"
SOURCE_IDENTITY = {
    "projector_id": "projector:c9-movement-closure",
    "projector_version": "1",
    "source_kind": "successor_values",
    "source_ref": f"project:{PROJECT_KEY}:semantic-sources",
    "source_incarnation": INCARNATION,
}


def read_provider_env() -> dict[str, str]:
    selected = {"LLM_PROVIDER", "OPENAI_API_KEY", "OPENAI_API_BASE"}
    values: dict[str, str] = {}
    path = WORKSPACE / "main/backend/.env"
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() not in selected:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    if not values.get("OPENAI_API_KEY"):
        raise RuntimeError("task provider credential is absent; external calls remain forbidden")
    values.setdefault("LLM_PROVIDER", "openai")
    values.setdefault("OPENAI_API_BASE", "https://api.openai.com/v1")
    return values


PROVIDER_ENV = read_provider_env()
POSTGRES_PASSWORD = secrets.token_hex(18)
TASK_AUTH_TOKEN = secrets.token_hex(24)
METRICS_TOKEN = secrets.token_hex(24)
SECRET_VALUES = (
    POSTGRES_PASSWORD,
    TASK_AUTH_TOKEN,
    METRICS_TOKEN,
    PROVIDER_ENV["OPENAI_API_KEY"],
)
RUN_ENV = dict(os.environ)
RUN_ENV.update(
    {
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": POSTGRES_PASSWORD,
        "POSTGRES_DB": SOURCE_DB,
        "DATABASE_URL": (
            "postgresql+psycopg2://postgres:"
            f"{POSTGRES_PASSWORD}@db:5432/{SOURCE_DB}"
        ),
        "ELASTIC_PASSWORD": "stage5-" + secrets.token_hex(14),
        "ES_URL": "http://elastic:ignored-by-override@es:9200",
        "ES_JAVA_OPTS": "-Xms512m -Xmx512m",
        "REDIS_PASSWORD": "stage5-" + secrets.token_hex(18),
        "REDIS_URL": "redis://:ignored-by-override@redis:6379/0",
        "FRONTEND_PUBLIC_PORT": "127.0.0.1:15152",
        "RELEASE_BUILD_COMMIT": "8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2",
        "RELEASE_BUILD_TREE": "ce7c67c831b51f9d64b4c2f1a470a724a50b19df",
        "RELEASE_BUILD_DIGEST": "sha256:dd4b1f3b512da6d013feb7f5925f343e5a639263b037d5a81445bfa2f8c93c0b",
        "CODEX_OAUTH_COOKIE_SECURE": "true",
        "PRODUCTION_ALLOWED_HOSTS": "127.0.0.1,localhost,backend",
        "PRODUCTION_ALLOWED_ORIGINS": "https://127.0.0.1:18152,https://localhost:18152",
        "PRODUCTION_TRUSTED_ACTOR_SOURCES": "authenticated_codex_token",
        "PRODUCTION_TRUSTED_AUTH_MODES": "codex_auth_token",
        "PRODUCTION_REQUIRE_TLS": "true",
        "PRODUCTION_ALLOWED_METHODS": "GET,POST,PUT,PATCH,DELETE",
        "PRODUCTION_ALLOWED_CONTENT_TYPES": "application/json",
        "PRODUCTION_MAX_BODY_BYTES": "1048576",
        "PRODUCTION_HTTP_RATE_MAX_REQUESTS": "120",
        "PRODUCTION_HTTP_RATE_WINDOW_SECONDS": "60",
        "PRODUCTION_PROVIDER_IDS": "openai",
        "PRODUCTION_PROVIDER_RATE_MAX_REQUESTS": "4",
        "PRODUCTION_PROVIDER_RATE_WINDOW_SECONDS": "60",
        "PRODUCTION_PROVIDER_MAX_PAYLOAD_BYTES": "131072",
        "PRODUCTION_PROVIDER_CATALOG_BINDING": "registered-provider-catalog.v1",
        "PRODUCTION_RATE_AUTHORITY_BINDING": "atomic-redis-rate-observations.v1",
        "PRODUCTION_CANONICAL_WRITER_BINDING": " ",
        "PRODUCTION_CANONICAL_WRITER_OWNER": " ",
        "PRODUCTION_PROJECT_KEYS": PROJECT_KEY,
        "PRODUCTION_OBSERVABILITY_RUNTIME_ID": "mrw-stage5-recovery",
        "PRODUCTION_CANARY_ROUTE_ENABLED": "false",
        "PRODUCTION_DOMAIN_REJECTION_TRIGGER_RATIO": "0.10",
        "PRODUCTION_DOMAIN_REJECTION_RECOVER_RATIO": "0.05",
        "PRODUCTION_ROUTE_ERROR_TRIGGER_RATIO": "0.05",
        "PRODUCTION_ROUTE_ERROR_RECOVER_RATIO": "0.01",
        "PRODUCTION_RELEASE_ERROR_TRIGGER_RATIO": "0.05",
        "PRODUCTION_RELEASE_ERROR_RECOVER_RATIO": "0.01",
        "BACKEND_IMAGE_DIGEST": BACKEND_IMAGE,
        "DB_IMAGE_DIGEST": DB_IMAGE,
        "ES_IMAGE_DIGEST": ES_IMAGE,
        "REDIS_IMAGE_DIGEST": REDIS_IMAGE,
        "FRONTEND_IMAGE_DIGEST": "mrw-local/r13x-candidate-frontend:8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2",
        "RUN_MIGRATIONS_BACKEND": "false",
        "RUN_MIGRATIONS_WORKER": "false",
        "CODEX_AUTH_TOKENS": TASK_AUTH_TOKEN,
        "PRODUCTION_METRICS_TOKEN": METRICS_TOKEN,
        "OPENAI_API_KEY": PROVIDER_ENV["OPENAI_API_KEY"],
        "OPENAI_API_BASE": PROVIDER_ENV["OPENAI_API_BASE"],
        "LLM_PROVIDER": PROVIDER_ENV["LLM_PROVIDER"],
    }
)
COMPOSE = [
    "docker", "compose", "-p", PROJECT,
    "-f", str(COMPOSE_FILE), "-f", str(OVERRIDE),
]


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def scrub(text: str) -> str:
    redacted = text
    for value in SECRET_VALUES:
        redacted = redacted.replace(value, "<redacted>")
    return redacted


def scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, list):
        return [scrub_value(item) for item in value]
    if isinstance(value, dict):
        return {key: scrub_value(item) for key, item in value.items()}
    return value


def write_json(name: str, payload: dict[str, Any]) -> None:
    payload.setdefault("authoritative", False)
    (OUT / name).write_text(
        json.dumps(scrub_value(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run(
    name: str,
    command: list[str],
    *,
    check: bool = True,
    timeout: int = 420,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    started = utc_now()
    started_monotonic = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=str(CANDIDATE),
        env=RUN_ENV,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    elapsed_ms = int((time.monotonic() - started_monotonic) * 1000)
    (OUT / f"{name}.log").write_text(
        "\n".join(
            [
                f"START_UTC={started}",
                f"END_UTC={utc_now()}",
                f"ELAPSED_MS={elapsed_ms}",
                f"COMMAND={scrub(shlex.join(command))}",
                f"EXIT_CODE={completed.returncode}",
                "OUTPUT_BEGIN",
                scrub(completed.stdout or ""),
                "OUTPUT_END",
                "",
            ]
        ),
        encoding="utf-8",
    )
    if check and completed.returncode != 0:
        raise RuntimeError(f"{name} failed with exit {completed.returncode}")
    return completed


def compose_args(*args: str) -> list[str]:
    return COMPOSE + list(args)


def project_resources() -> dict[str, list[str]]:
    label = f"label=com.docker.compose.project={PROJECT}"

    def lines(args: list[str]) -> list[str]:
        completed = subprocess.run(
            args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
        )
        return sorted(line for line in completed.stdout.splitlines() if line.strip())

    return {
        "containers": lines(["docker", "ps", "-a", "--filter", label, "--format", "{{.Names}}"]),
        "networks": lines(["docker", "network", "ls", "--filter", label, "--format", "{{.Name}}"]),
        "volumes": lines(["docker", "volume", "ls", "--filter", label, "--format", "{{.Name}}"]),
    }


def image_identity(reference: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["docker", "image", "inspect", reference],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    raw = json.loads(completed.stdout)[0]
    return {
        "reference": reference,
        "id": raw.get("Id"),
        "platform": f"{raw.get('Os')}/{raw.get('Architecture')}",
    }


def last_json(name: str) -> dict[str, Any]:
    raw = (OUT / f"{name}.log").read_text(encoding="utf-8")
    block = raw.split("OUTPUT_BEGIN\n", 1)[1].split("\nOUTPUT_END", 1)[0]
    return json.loads(block.strip().splitlines()[-1])


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(encoded)


def psql(name: str, service: str, database: str, sql: str) -> str:
    completed = run(
        name,
        compose_args(
            "exec", "-T", service, "psql", "-U", "postgres", "-d", database,
            "-v", "ON_ERROR_STOP=1", "-At", "-c", sql,
        ),
    )
    return completed.stdout.strip()


def state_query(database: str, schema: str = PROJECT_SCHEMA) -> str:
    return f"""
SELECT json_build_object(
  'scope', (SELECT COALESCE(json_agg(x), '[]'::json) FROM (
      SELECT * FROM public.project_scope_registry WHERE project_key = '{PROJECT_KEY}' ORDER BY registry_revision
  ) AS x),
  'idempotency', (SELECT COALESCE(json_agg(x), '[]'::json) FROM (
      SELECT * FROM public.runtime_idempotency WHERE project_key = '{PROJECT_KEY}' ORDER BY idempotency_id
  ) AS x),
  'projection_offsets', (SELECT COALESCE(json_agg(x), '[]'::json) FROM (
      SELECT * FROM public.runtime_projection_offsets WHERE project_key = '{PROJECT_KEY}' ORDER BY projection_offset_id
  ) AS x),
  'events', (SELECT COALESCE(json_agg(x), '[]'::json) FROM (
      SELECT * FROM public.runtime_events WHERE project_key = '{PROJECT_KEY}' ORDER BY run_id, seq
  ) AS x),
  'steps', (SELECT COALESCE(json_agg(x), '[]'::json) FROM (
      SELECT * FROM public.runtime_steps WHERE project_key = '{PROJECT_KEY}' ORDER BY run_id, step_id
  ) AS x),
  'effect_attempts', (SELECT COALESCE(json_agg(x), '[]'::json) FROM (
      SELECT * FROM public.runtime_effect_attempts WHERE project_key = '{PROJECT_KEY}' ORDER BY attempt_id
  ) AS x),
  'receipts', (SELECT COALESCE(json_agg(x), '[]'::json) FROM (
      SELECT * FROM "{schema}".successor_receipts WHERE project_key = '{PROJECT_KEY}' ORDER BY receipt_id
  ) AS x),
  'values', (SELECT COALESCE(json_agg(x), '[]'::json) FROM (
      SELECT * FROM "{schema}".successor_values WHERE project_key = '{PROJECT_KEY}' ORDER BY value_id
  ) AS x)
);
"""


def capture_state(name: str, service: str, database: str) -> dict[str, Any]:
    raw = psql(name, service, database, state_query(database))
    if not raw:
        raise RuntimeError(f"{name} returned no state JSON")
    state = json.loads(raw)
    return {
        "digest": canonical_digest(state),
        "counts": {key: len(value) for key, value in state.items()},
        "rows": state,
    }


def invariant_summary(state: dict[str, Any]) -> dict[str, Any]:
    scope = state["rows"]["scope"]
    idempotency = state["rows"]["idempotency"]
    offsets = state["rows"]["projection_offsets"]
    receipts = state["rows"]["receipts"]
    receipt_contents = [row.get("receipt_json") or {} for row in receipts]
    return {
        "scope_rows": len(scope),
        "scope_digest": scope[0].get("scope_digest") if len(scope) == 1 else None,
        "idempotency_rows": len(idempotency),
        "idempotency_states": sorted({row.get("state") for row in idempotency}),
        "idempotency_request_digests": sorted({row.get("request_digest") for row in idempotency}),
        "projection_rows": len(offsets),
        "projection_generations": sorted({row.get("projection_generation") for row in offsets}),
        "receipt_rows": len(receipts),
        "receipt_states": sorted({row.get("state") for row in receipt_contents}),
        "receipt_command_ids": sorted({row.get("command_id") for row in receipt_contents}),
        "receipt_digest_unique": len({row.get("receipt_digest") for row in receipts}) == len(receipts),
    }


def http_probe(name: str, service: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    code = f'''
import json, os, urllib.error, urllib.request
body = {encoded!r}.encode()
request = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/successor-runtime/v2/commands",
    data=body,
    method="POST",
    headers={{
        "Authorization": "Bearer " + os.environ["CODEX_AUTH_TOKENS"],
        "Content-Type": "application/json",
        "X-Project-Key": "{PROJECT_KEY}",
        "X-Forwarded-Proto": "https",
    }},
)
try:
    response = urllib.request.urlopen(request, timeout=30)
    status = response.status
    raw = response.read().decode()
except urllib.error.HTTPError as exc:
    status = exc.code
    raw = exc.read().decode()
print(json.dumps({{"http_status": status, "payload": json.loads(raw)}}, sort_keys=True))
'''
    completed = run(
        name,
        compose_args("exec", "-T", service, "python", "-c", code),
    )
    wrapped = json.loads(completed.stdout.strip().splitlines()[-1])
    return int(wrapped["http_status"]), wrapped["payload"]


def effect_body(trace_id: str) -> dict[str, Any]:
    return {
        "command_id": COMMAND_ID,
        "command_kind": "rebuild_projection",
        "project_locator": PROJECT_KEY,
        "trace_id": trace_id,
        "payload": {
            "payload_kind": "rebuild_projection",
            "projection_id": PROJECTION_ID,
            "mode": "FULL",
        },
        "expected_base_token": f"generation:0|revision:0|incarnation:{INCARNATION}",
        "approval_locator": APPROVAL_ID,
    }


def response_summary(status: int, payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") or {}
    error = payload.get("error") or {}
    return {
        "http_status": status,
        "envelope_status": payload.get("status"),
        "error_code": error.get("code"),
        "receipt_state": data.get("state"),
        "request_digest": data.get("request_digest"),
        "effect_generation": (data.get("effect_result") or {}).get("generation"),
        "scope": (payload.get("meta") or {}).get("project_scope_ref"),
    }


def migration_database_url() -> str:
    return (
        "postgresql+psycopg2://postgres:"
        f"{POSTGRES_PASSWORD}@migration-db:5432/{MIGRATION_DB}"
    )


def alembic(name: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    network = f"{PROJECT}_default"
    return run(
        name,
        [
            "docker", "run", "--rm", "--name", f"{PROJECT}-{name}",
            "--platform", "linux/amd64", "--network", network,
            "-e", f"DATABASE_URL={migration_database_url()}",
            "--entrypoint", "python", MIGRATION_IMAGE,
            "-m", "alembic", *args,
        ],
        check=check,
    )


def cleanup() -> dict[str, Any]:
    completed = run(
        "90-compose-down",
        compose_args("down", "--volumes", "--remove-orphans", "--timeout", "30"),
        check=False,
        timeout=240,
    )
    residue = project_resources()
    return {
        "status": "PASS" if completed.returncode == 0 and not any(residue.values()) else "FAIL",
        "down_exit_code": completed.returncode,
        "project_residue": residue,
        "docker_prune_executed": False,
    }


def main() -> int:
    started_at = utc_now()
    before = project_resources()
    result: dict[str, Any] = {
        "schema_version": "mrw.stage5.backup-restore-migration-recovery.v1",
        "status": "FAIL",
        "started_at": started_at,
        "compose_project": PROJECT,
        "port": PORT,
        "project_key": PROJECT_KEY,
        "provider_calls": 0,
        "credentials_persisted": False,
        "project_resources_before": before,
        "input_retention": {
            "post_acceptance_cleanup": "stage4-evidence/runtime/post-acceptance-cleanup.json",
            "final_image_disposition": "retain_final_stage5_input",
        },
    }
    if any(before.values()):
        result["error"] = "Stage5 recovery Compose project collision"
        write_json("recovery-result.json", result)
        return 1
    started_services = False
    cleanup_result: dict[str, Any] = {"status": "NOT_RUN"}
    try:
        identities = {
            "backend": image_identity(BACKEND_IMAGE),
            "db": image_identity(DB_IMAGE),
            "elasticsearch": image_identity(ES_IMAGE),
            "redis": image_identity(REDIS_IMAGE),
            "migration": image_identity(MIGRATION_IMAGE),
        }
        expected = {
            "backend": BACKEND_IMAGE_ID,
            "db": DB_IMAGE_ID,
            "elasticsearch": ES_IMAGE_ID,
            "redis": REDIS_IMAGE_ID,
            "migration": MIGRATION_IMAGE_ID,
        }
        identities_ok = all(identities[name]["id"] == expected[name] for name in expected)
        result["image_identity"] = {"status": "PASS" if identities_ok else "FAIL", "images": identities}
        if not identities_ok or not SNAPSHOT.is_file() or not SEED.is_file():
            raise RuntimeError("retained recovery input identity or files failed")

        run(
            "01-dependencies-up",
            compose_args("up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "180",
                         "db", "es", "redis"),
            timeout=300,
        )
        started_services = True
        db_container = run("02-db-container", compose_args("ps", "-q", "db")).stdout.strip()
        run("03-snapshot-copy", ["docker", "cp", str(SNAPSHOT), f"{db_container}:/tmp/stage5-snapshot.dump"])
        restore_started = utc_now()
        restore_started_monotonic = time.monotonic()
        run(
            "04-snapshot-restore-primary",
            ["docker", "exec", db_container, "pg_restore", "-U", "postgres", "-d", SOURCE_DB,
             "--exit-on-error", "/tmp/stage5-snapshot.dump"],
            timeout=300,
        )
        run(
            "05-application-up",
            compose_args("up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "300",
                         "backend", "celery-worker"),
            timeout=420,
        )
        backend_container = run("06-backend-container", compose_args("ps", "-q", "backend")).stdout.strip()
        run(
            "07-seed-copy",
            ["docker", "cp", str(SEED), f"{backend_container}:/tmp/seed-c9-effect.py"],
        )
        seed = run(
            "08-seed-c9",
            compose_args("exec", "-T", "backend", "python", "/tmp/seed-c9-effect.py"),
        )
        seeded = last_json("08-seed-c9")
        first_started = utc_now()
        first_status, first = http_probe("09-c9-effect-first", "backend", effect_body("trace:stage5:recovery:first"))
        first_summary = response_summary(first_status, first)
        exact_ok = (
            first_status == 200
            and first.get("status") == "ok"
            and first_summary["receipt_state"] == "TERMINAL"
            and first_summary["effect_generation"] == 1
        )
        if not exact_ok:
            raise RuntimeError(f"first C9 effect failed: {first_summary}")

        source = capture_state("10-source-state", "db", SOURCE_DB)
        source_summary = invariant_summary(source)
        source_ok = (
            source_summary["scope_rows"] == 1
            and source_summary["scope_digest"] == seeded.get("scope_digest")
            and source_summary["idempotency_rows"] == 1
            and source_summary["idempotency_states"] == ["TERMINAL"]
            and source_summary["projection_generations"] == [1]
            and source_summary["receipt_rows"] == 1
            and source_summary["receipt_states"] == ["TERMINAL"]
            and source_summary["receipt_command_ids"] == [COMMAND_ID]
            and source_summary["receipt_digest_unique"]
        )
        if not source_ok:
            raise RuntimeError(f"source effect invariants failed: {source_summary}")

        replay_status, replay = http_probe("12-c9-effect-exact-replay", "backend", effect_body("trace:stage5:recovery:replay"))
        replay_summary = response_summary(replay_status, replay)
        after_source_replay = capture_state("13-source-state-after-replay", "db", SOURCE_DB)
        exact_replay_ok = (
            replay_status == 200
            and replay.get("status") == "ok"
            and replay.get("data") == first.get("data")
            and replay.get("meta") == first.get("meta")
            and after_source_replay["digest"] == source["digest"]
        )

        run("14-backup-pg-dump", ["docker", "exec", db_container, "pg_dump", "-U", "postgres", "-Fc", "-d", SOURCE_DB, "-f", "/tmp/stage5-task-data.dump"], timeout=300)
        run("15-backup-copy-out", ["docker", "cp", f"{db_container}:/tmp/stage5-task-data.dump", str(OUT / "stage5-task-data.dump")])
        backup_bytes = (OUT / "stage5-task-data.dump").read_bytes()
        backup_sha = sha256_bytes(backup_bytes)
        backup_completed = utc_now()
        run(
            "16-restore-instance-up",
            compose_args("up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "120", "restore-db"),
            timeout=180,
        )
        restore_db_container = run("17-restore-db-container", compose_args("ps", "-q", "restore-db")).stdout.strip()
        run("18-backup-copy-restore", ["docker", "cp", str(OUT / "stage5-task-data.dump"), f"{restore_db_container}:/tmp/task-data.dump"])
        run("19-backup-restore-independent", ["docker", "exec", restore_db_container, "pg_restore", "-U", "postgres", "-d", RESTORE_DB, "--exit-on-error", "/tmp/task-data.dump"], timeout=300)
        restored = capture_state("20-restored-state", "restore-db", RESTORE_DB)
        restored_summary = invariant_summary(restored)
        data_equal = restored["digest"] == source["digest"]
        run(
            "21-restore-backend-up",
            compose_args("up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "300", "restore-backend"),
            timeout=420,
        )
        restore_replay_status, restore_replay = http_probe("22-restored-exact-replay", "restore-backend", effect_body("trace:stage5:recovery:restored"))
        restore_replay_summary = response_summary(restore_replay_status, restore_replay)
        after_restore_replay = capture_state("23-restored-state-after-replay", "restore-db", RESTORE_DB)
        restore_replay_ok = (
            restore_replay_status == 200
            and restore_replay.get("status") == "ok"
            and restore_replay.get("data") == first.get("data")
            and restore_replay.get("meta") == first.get("meta")
            and after_restore_replay["digest"] == restored["digest"]
        )
        rto_ms = int((time.monotonic() - restore_started_monotonic) * 1000)
        restore_ok = data_equal and restored_summary == source_summary and restore_replay_ok
        if not restore_ok:
            raise RuntimeError(f"restore verification failed: equal={data_equal}, replay={restore_replay_summary}")

        run(
            "24-migration-probe-up",
            compose_args("up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "120", "migration-db"),
            timeout=180,
        )
        migration_container = run("25-migration-db-container", compose_args("ps", "-q", "migration-db")).stdout.strip()
        run("26-backup-copy-migration", ["docker", "cp", str(OUT / "stage5-task-data.dump"), f"{migration_container}:/tmp/task-data.dump"])
        run("27-migration-probe-restore", ["docker", "exec", migration_container, "pg_restore", "-U", "postgres", "-d", MIGRATION_DB, "--exit-on-error", "/tmp/task-data.dump"], timeout=300)
        migration_before = capture_state("28-migration-state-before", "migration-db", MIGRATION_DB)
        psql("29-migration-induce-version-drift", "migration-db", MIGRATION_DB,
             f"UPDATE public.alembic_version SET version_num = '{PARENT}';")
        failure_started_monotonic = time.monotonic()
        failure_started = utc_now()
        failure = alembic("30-migration-upgrade-expected-failure", "upgrade", "head", check=False)
        failure_text = (OUT / "30-migration-upgrade-expected-failure.log").read_text(encoding="utf-8")
        failure_is_collision = "source_kind" in failure_text and ("already exists" in failure_text or "duplicate column" in failure_text)
        if failure.returncode == 0 or not failure_is_collision:
            raise RuntimeError("expected migration metadata-drift failure did not occur")
        alembic("31-migration-forward-fix-stamp-head", "stamp", HEAD)
        recovery_upgrade = alembic("32-migration-upgrade-after-forward-fix", "upgrade", "head")
        current = alembic("33-migration-current", "current")
        migration_after = capture_state("34-migration-state-after", "migration-db", MIGRATION_DB)
        current_head = HEAD in current.stdout
        migration_preserved = migration_after["digest"] == migration_before["digest"]
        migration_recovery_ms = int((time.monotonic() - failure_started_monotonic) * 1000)
        migration_ok = current_head and migration_preserved
        if not migration_ok:
            raise RuntimeError("migration recovery did not preserve task data or reach head")

        result.update(
            {
                "status": "PASS_LOCAL_STAGE5_RECOVERY_NOT_AUTHORITY",
                "ended_at": utc_now(),
                "seed": {
                    "script": str(SEED.relative_to(WORKSPACE)),
                    "project_schema": seeded.get("resolved_schema"),
                    "scope_digest": seeded.get("scope_digest"),
                    "effect_request_digest": seeded.get("effect_request_digest"),
                    "actor_derived": seeded.get("actor_derived"),
                },
                "effect": {
                    "first": first_summary,
                    "exact_replay": replay_summary,
                    "exact_replay_equal": exact_replay_ok,
                    "source_rows_after_replay_unchanged": after_source_replay["digest"] == source["digest"],
                    "external_sinks": ["elasticsearch", "qdrant", "graph_provider"],
                    "external_sink_disposition": "DECLARED_LOSS_NO_CALL",
                },
                "backup": {
                    "format": "pg_dump/custom",
                    "bytes": len(backup_bytes),
                    "sha256": backup_sha,
                    "completed_at": backup_completed,
                    "command_exit_code": 0,
                },
                "restore": {
                    "independent_service": "restore-db",
                    "database": RESTORE_DB,
                    "state_equal": data_equal,
                    "source_digest": source["digest"],
                    "restored_digest": restored["digest"],
                    "source_counts": source["counts"],
                    "restored_counts": restored["counts"],
                    "invariants": restored_summary,
                    "restored_exact_replay": restore_replay_summary,
                    "restored_replay_rows_unchanged": after_restore_replay["digest"] == restored["digest"],
                    "restore_started_at": restore_started,
                    "rto_ms": rto_ms,
                    "rto_boundary": "restore instance start through restored exact replay and state comparison",
                    "observed_data_loss_rows": 0,
                    "rpo_note": "No source rows changed between source-state capture and backup; backup contains the complete captured effect.",
                },
                "migration_recovery": {
                    "independent_service": "migration-db",
                    "database": MIGRATION_DB,
                    "failure_mode": "CONTROLLED_ALEMBIC_VERSION_POINTER_DRIFT",
                    "parent_version": PARENT,
                    "expected_failure_exit_code": failure.returncode,
                    "observed_collision": failure_is_collision,
                    "failure_log": "30-migration-upgrade-expected-failure.log",
                    "forward_fix": f"alembic stamp {HEAD}",
                    "recovery_upgrade_exit_code": recovery_upgrade.returncode,
                    "current_head": current_head,
                    "state_digest_before": migration_before["digest"],
                    "state_digest_after": migration_after["digest"],
                    "task_data_preserved": migration_preserved,
                    "rto_ms": migration_recovery_ms,
                },
                "provider_calls": 0,
                "credentials_persisted": False,
            }
        )
    except Exception as exc:  # noqa: BLE001 - preserve failure evidence
        result["error"] = str(exc)
        result["ended_at"] = utc_now()
    finally:
        if started_services:
            cleanup_result = cleanup()
        result["cleanup"] = cleanup_result
        if result.get("cleanup", {}).get("status") != "PASS":
            result["status"] = "FAIL"
            result.setdefault("error", "Stage5 recovery Compose resources remain")
        write_json("recovery-result.json", result)
    return 0 if result.get("status") == "PASS_LOCAL_STAGE5_RECOVERY_NOT_AUTHORITY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
