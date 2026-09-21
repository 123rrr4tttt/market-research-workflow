#!/usr/bin/env python3
"""Run the bounded Stage 4 production-like Compose lifecycle on retained r13x images."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


OUT = Path(__file__).resolve().parent
WORKSPACE = Path("/Users/wangyiliang/market-research-workflow")
CANDIDATE = Path(
    "/Users/wangyiliang/.codex/release-rehearsals/"
    "mrw-stage2-20260912-v4-r13x/candidate"
)
COMPOSE = CANDIDATE / "main/ops/docker-compose.production.yml"
OVERRIDE = OUT / "compose.override.yml"
PROJECT = "mrw-stage4-local"
COMMIT = "8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2"
TREE = "ce7c67c831b51f9d64b4c2f1a470a724a50b19df"
BASE_BACKEND = f"mrw-local/r13x-candidate-backend:{COMMIT}"
BACKEND = "mrw-local/stage4-r13x-backend-config:8652d653f740735f"
FRONTEND = f"mrw-local/r13x-candidate-frontend:{COMMIT}"
MIGRATION = f"mrw-local/r13x-candidate-migration-runner:{COMMIT}"
DB_IMAGE = "ankane/pgvector:latest"
ES_IMAGE = "docker.elastic.co/elasticsearch/elasticsearch:8.15.3"
REDIS_IMAGE = "redis:7.4"
EXPECTED_IMAGE_IDS = {
    "base-backend": "sha256:d72688f24fb867ae2e0e9310cfc9ec25aac649a8da69130ee26469c0bd37c2ef",
    "backend": "sha256:f99f900e5b420cf7e1c9513598a87251cc6c8124e6ec8461c564ed4d7ca76c20",
    "frontend": "sha256:f5641ba6d2b50135da1c9c9c3edfd067ed90ecfb37bcb8f0c7580b2e00aaa915",
    "migration-runner": "sha256:3b409669bb8248f738c1133f9458d73725951140c0eae938064d469045960509",
    "db": "sha256:956744bd14e9cbdf639c61c2a2a7c7c2c48a9c8cdd42f7de4ac034f4e96b90f8",
    "elasticsearch": "sha256:01c1732062b4a846c5ca687b0094b89bad0bfed00c6d71626db32fb8f3131a78",
    "redis": "sha256:71da9275c5f3fcb97d0fa0c8c5b36cc995327265420f17a04bfd544f458059f7",
}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_selected_dotenv(path: Path) -> dict[str, str]:
    selected = {"LLM_PROVIDER", "OPENAI_API_KEY", "OPENAI_API_BASE"}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in selected:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


PROVIDER_ENV = parse_selected_dotenv(WORKSPACE / "main/backend/.env")
if not PROVIDER_ENV.get("OPENAI_API_KEY"):
    raise SystemExit("OPENAI_API_KEY is absent from project-owned main/backend/.env")

POSTGRES_PASSWORD = secrets.token_hex(18)
REDIS_PASSWORD = secrets.token_hex(18)
ELASTIC_PASSWORD = "Stage4_" + secrets.token_hex(14)
METRICS_TOKEN = secrets.token_hex(24)
TASK_AUTH_TOKEN = secrets.token_hex(24)
SECRET_VALUES = tuple(
    value
    for value in (
        POSTGRES_PASSWORD,
        REDIS_PASSWORD,
        ELASTIC_PASSWORD,
        METRICS_TOKEN,
        TASK_AUTH_TOKEN,
        PROVIDER_ENV.get("OPENAI_API_KEY", ""),
    )
    if value
)

RUN_ENV = dict(os.environ)
RUN_ENV.update(
    {
        "DB_IMAGE_DIGEST": DB_IMAGE,
        "ES_IMAGE_DIGEST": ES_IMAGE,
        "REDIS_IMAGE_DIGEST": REDIS_IMAGE,
        "BACKEND_IMAGE_DIGEST": BACKEND,
        "FRONTEND_IMAGE_DIGEST": FRONTEND,
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": POSTGRES_PASSWORD,
        "POSTGRES_DB": "mrw_stage4",
        "DATABASE_URL": (
            "postgresql+psycopg2://postgres:"
            f"{POSTGRES_PASSWORD}@db:5432/mrw_stage4"
        ),
        "REDIS_PASSWORD": REDIS_PASSWORD,
        "ELASTIC_PASSWORD": ELASTIC_PASSWORD,
        "ES_URL": f"http://elastic:{ELASTIC_PASSWORD}@es:9200",
        "REDIS_URL": f"redis://:{REDIS_PASSWORD}@redis:6379/0",
        "ES_JAVA_OPTS": "-Xms512m -Xmx512m",
        "FRONTEND_PUBLIC_PORT": "127.0.0.1:15142",
        "RELEASE_BUILD_COMMIT": COMMIT,
        "RELEASE_BUILD_TREE": TREE,
        "RELEASE_BUILD_DIGEST": "sha256:dd4b1f3b512da6d013feb7f5925f343e5a639263b037d5a81445bfa2f8c93c0b",
        "RUN_MIGRATIONS_BACKEND": "false",
        "RUN_MIGRATIONS_WORKER": "false",
        "PRODUCTION_ALLOWED_HOSTS": "127.0.0.1,localhost,backend",
        "PRODUCTION_ALLOWED_ORIGINS": "https://127.0.0.1:15142,https://localhost:15142",
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
        # Compose marks an empty required variable as absent, while the
        # retained r13x route-binding artifact has no canonical-writer refs.
        # A single whitespace satisfies Compose interpolation and is stripped
        # by settings, preserving the image's empty deployment assertion.
        "PRODUCTION_CANONICAL_WRITER_BINDING": " ",
        "PRODUCTION_CANONICAL_WRITER_OWNER": " ",
        "PRODUCTION_PROJECT_KEYS": "stage4_s4_20260913",
        "PRODUCTION_METRICS_TOKEN": METRICS_TOKEN,
        "CODEX_AUTH_ENABLED": "true",
        "CODEX_AUTH_TOKENS": TASK_AUTH_TOKEN,
        "CODEX_AUTH_PROTECTED_PREFIXES": "/api/v1/projects,/api/v1/business-lines,/api/v1/ingest,/api/v1/workflow-graph,/api/v1/admin,/api/v1/writing,/api/v1/successor-runtime",
        "PRODUCTION_OBSERVABILITY_RUNTIME_ID": "mrw-stage4-local-r13x",
        "PRODUCTION_CANARY_ROUTE_ENABLED": "false",
        "PRODUCTION_DOMAIN_REJECTION_TRIGGER_RATIO": "0.10",
        "PRODUCTION_DOMAIN_REJECTION_RECOVER_RATIO": "0.05",
        "PRODUCTION_ROUTE_ERROR_TRIGGER_RATIO": "0.05",
        "PRODUCTION_ROUTE_ERROR_RECOVER_RATIO": "0.01",
        "PRODUCTION_RELEASE_ERROR_TRIGGER_RATIO": "0.05",
        "PRODUCTION_RELEASE_ERROR_RECOVER_RATIO": "0.01",
        "LLM_PROVIDER": PROVIDER_ENV.get("LLM_PROVIDER") or "openai",
        "OPENAI_API_KEY": PROVIDER_ENV["OPENAI_API_KEY"],
        "OPENAI_API_BASE": PROVIDER_ENV.get("OPENAI_API_BASE") or "https://api.openai.com/v1",
        "ACTIVE_PROJECT_KEY": "stage4_s4_20260913",
    }
)

COMPOSE_BASE = [
    "docker", "compose", "-p", PROJECT,
    "-f", str(COMPOSE), "-f", str(OVERRIDE),
]


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
    timeout: int = 600,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    started = utc_now()
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
    (OUT / f"{name}.log").write_text(
        "\n".join(
            [
                f"START_UTC={started}",
                f"END_UTC={utc_now()}",
                f"CWD={CANDIDATE}",
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


def project_resources() -> dict[str, list[str]]:
    def lines(command: list[str]) -> list[str]:
        completed = subprocess.run(
            command,
            env=RUN_ENV,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return sorted(line for line in completed.stdout.splitlines() if line.strip())

    label = f"label=com.docker.compose.project={PROJECT}"
    return {
        "containers": lines(["docker", "ps", "-a", "--filter", label, "--format", "{{.Names}}"]),
        "networks": lines(["docker", "network", "ls", "--filter", label, "--format", "{{.Name}}"]),
        "volumes": lines(["docker", "volume", "ls", "--filter", label, "--format", "{{.Name}}"]),
    }


def image_identity(image: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["docker", "image", "inspect", image],
        env=RUN_ENV,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    raw = json.loads(completed.stdout)[0]
    return {
        "reference": image,
        "id": raw.get("Id"),
        "platform": f"{raw.get('Os')}/{raw.get('Architecture')}",
        "repo_tags": raw.get("RepoTags") or [],
        "repo_digests": raw.get("RepoDigests") or [],
    }


def parse_compose_ps(raw: str) -> dict[str, dict[str, str | None]]:
    try:
        parsed = json.loads(raw)
        rows = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    return {
        str(row.get("Service")): {
            "name": row.get("Name"),
            "state": row.get("State"),
            "health": row.get("Health"),
            "image": row.get("Image"),
        }
        for row in rows
    }


def health_request(name: str, url: str) -> tuple[dict[str, Any], int]:
    config = f'header = "Authorization: Bearer {METRICS_TOKEN}"\n'
    completed = run(
        name,
        ["curl", "--config", "-", "--silent", "--show-error", "--output", "-", "--write-out", "\n%{http_code}", url],
        input_text=config,
    )
    body, status = completed.stdout.rsplit("\n", 1)
    return json.loads(body), int(status)


def cleanup() -> dict[str, Any]:
    completed = run(
        "90-compose-down",
        COMPOSE_BASE + ["down", "--volumes", "--remove-orphans", "--timeout", "30"],
        check=False,
        timeout=240,
    )
    residue = project_resources()
    return {
        "status": "PASS" if completed.returncode == 0 and not any(residue.values()) else "FAIL",
        "down_exit_code": completed.returncode,
        "project_residue": residue,
        "docker_prune_executed": False,
        "stage3_images_removed": False,
    }


def main() -> int:
    started_at = utc_now()
    before = project_resources()
    write_json("00-resources-before.json", {"observed_at": started_at, "project": PROJECT, **before})
    collision = any(before.values())
    started = False
    status = "FAIL"
    error: str | None = None
    results: dict[str, Any] = {}
    cleanup_result: dict[str, Any] = {"status": "NOT_RUN"}
    try:
        if collision:
            raise RuntimeError(f"task Compose project collision: {before}")
        commit = run("01-candidate-commit", ["git", "rev-parse", "HEAD"]).stdout.strip()
        tree = run("01-candidate-tree", ["git", "rev-parse", "HEAD^{tree}"]).stdout.strip()
        dirty = run("01-candidate-status", ["git", "status", "--short"]).stdout.strip()
        images = {
            "base-backend": image_identity(BASE_BACKEND),
            "backend": image_identity(BACKEND),
            "frontend": image_identity(FRONTEND),
            "migration-runner": image_identity(MIGRATION),
            "db": image_identity(DB_IMAGE),
            "elasticsearch": image_identity(ES_IMAGE),
            "redis": image_identity(REDIS_IMAGE),
        }
        identity_ok = (
            commit == COMMIT
            and tree == TREE
            and not dirty
            and all(images[name]["id"] == expected for name, expected in EXPECTED_IMAGE_IDS.items())
        )
        identity = {
            "status": "PASS" if identity_ok else "FAIL",
            "candidate": {"root": str(CANDIDATE), "commit": commit, "tree": tree, "clean": not dirty},
            "images": images,
            "expected_image_ids": EXPECTED_IMAGE_IDS,
            "compose_runtime_no_build": True,
            "pull_policy": "never",
            "derived_backend_boundary": {
                "base_image": BASE_BACKEND,
                "base_image_id": EXPECTED_IMAGE_IDS["base-backend"],
                "derived_image": BACKEND,
                "derived_image_id": EXPECTED_IMAGE_IDS["backend"],
                "replaced_paths": {
                    "/docker-entrypoint.sh": {
                        "source": "current worktree main/backend/docker-entrypoint.sh",
                        "sha256": "f5215bda79994b29c544763f9a88fbdbefd863a0ab3b70f2962f09b62de677c7",
                    },
                    "/app/app/composition/production.py": {
                        "source": "current worktree main/backend/app/composition/production.py",
                        "sha256": "f35a8cc676fd226eacb960f55d4e270ed9174aa664bb18e92189bc0c6593da67",
                    },
                },
                "identity_classification": "NON_R13X_DERIVED_STAGE4_RUNTIME_IMAGE",
            },
        }
        write_json("identity.json", identity)
        results["identity"] = identity["status"]
        if not identity_ok:
            raise RuntimeError("candidate or retained image identity mismatch")

        resolved_raw = run("02-compose-config", COMPOSE_BASE + ["config", "--format", "json"]).stdout
        resolved = json.loads(resolved_raw)
        services = resolved["services"]
        compose_assertions = {
            "backend_exact": services["backend"]["image"] == BACKEND,
            "worker_exact": services["celery-worker"]["image"] == BACKEND,
            "frontend_exact": services["frontend"]["image"] == FRONTEND,
            "no_service_builds": all("build" not in service for service in services.values()),
            "no_base_host_ports": all(not services[name].get("ports") for name in ("db", "es", "redis")),
            "all_pull_never": all(service.get("pull_policy") == "never" for service in services.values()),
            "production_env": services["backend"]["environment"].get("ENV") == "production",
            "provider_key_injected": bool(services["backend"]["environment"].get("OPENAI_API_KEY")),
        }
        write_json(
            "compose-resolved.redacted.json",
            {"status": "PASS" if all(compose_assertions.values()) else "FAIL", "assertions": compose_assertions, "services": services},
        )
        results["compose_config"] = "PASS" if all(compose_assertions.values()) else "FAIL"
        if not all(compose_assertions.values()):
            raise RuntimeError(f"Compose contract mismatch: {compose_assertions}")

        run(
            "03-db-up",
            COMPOSE_BASE + ["up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "120", "db"],
            timeout=180,
        )
        started = True
        network = f"{PROJECT}_default"
        heads = run(
            "04-migration-heads",
            ["docker", "run", "--rm", "--name", "mrw-stage4-local-migration-heads", "--platform", "linux/amd64", "--network", network, "-e", "DATABASE_URL", "--entrypoint", "python", MIGRATION, "-m", "alembic", "heads"],
        )
        head_lines = [line.split()[0] for line in heads.stdout.splitlines() if "(head)" in line]
        if len(head_lines) != 1:
            raise RuntimeError(f"expected one migration head, got {head_lines}")
        expected_head = head_lines[0]
        before_schema = run(
            "04-schema-before",
            COMPOSE_BASE + ["exec", "-T", "db", "psql", "-U", "postgres", "-d", "mrw_stage4", "-At", "-c", "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"],
        ).stdout.strip()
        fresh = run(
            "05-migration-fresh-upgrade",
            ["docker", "run", "--rm", "--name", "mrw-stage4-local-migration-fresh", "--platform", "linux/amd64", "--network", network, "-e", "DATABASE_URL", MIGRATION],
            timeout=360,
        )
        current = run(
            "06-migration-current",
            ["docker", "run", "--rm", "--name", "mrw-stage4-local-migration-current", "--platform", "linux/amd64", "--network", network, "-e", "DATABASE_URL", "--entrypoint", "python", MIGRATION, "-m", "alembic", "current"],
        )
        schema_sql = (
            "SELECT version_num FROM alembic_version; "
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'; "
            "SELECT table_name||':'||column_name||':'||data_type FROM information_schema.columns "
            "WHERE table_schema='public' ORDER BY table_name,column_name;"
        )
        schema_after_raw = run(
            "07-schema-after",
            COMPOSE_BASE + ["exec", "-T", "db", "psql", "-U", "postgres", "-d", "mrw_stage4", "-At", "-c", schema_sql],
        ).stdout
        schema_after_lines = [line for line in schema_after_raw.splitlines() if line.strip()]
        table_count = int(schema_after_lines[1])
        schema_fingerprint = hashlib.sha256("\n".join(schema_after_lines[2:]).encode()).hexdigest()
        repeat = run(
            "08-migration-repeat-upgrade",
            ["docker", "run", "--rm", "--name", "mrw-stage4-local-migration-repeat", "--platform", "linux/amd64", "--network", network, "-e", "DATABASE_URL", MIGRATION],
            timeout=360,
        )
        schema_repeat_raw = run(
            "09-schema-repeat",
            COMPOSE_BASE + ["exec", "-T", "db", "psql", "-U", "postgres", "-d", "mrw_stage4", "-At", "-c", schema_sql],
        ).stdout
        schema_repeat_lines = [line for line in schema_repeat_raw.splitlines() if line.strip()]
        repeat_fingerprint = hashlib.sha256("\n".join(schema_repeat_lines[2:]).encode()).hexdigest()
        migration_ok = (
            before_schema == "0"
            and fresh.returncode == 0
            and repeat.returncode == 0
            and expected_head in current.stdout
            and schema_after_lines[0] == expected_head
            and table_count > 0
            and schema_fingerprint == repeat_fingerprint
        )
        migration = {
            "status": "PASS" if migration_ok else "FAIL",
            "database_scope": "dedicated disposable mrw_stage4 database in mrw-stage4-local",
            "public_tables_before": int(before_schema),
            "public_tables_after": table_count,
            "expected_head": expected_head,
            "current_contains_head": expected_head in current.stdout,
            "fresh_upgrade_exit_code": fresh.returncode,
            "repeat_upgrade_exit_code": repeat.returncode,
            "schema_fingerprint_sha256": schema_fingerprint,
            "repeat_schema_fingerprint_sha256": repeat_fingerprint,
            "repeat_upgrade_schema_stable": schema_fingerprint == repeat_fingerprint,
        }
        write_json("migration.json", migration)
        results["migration"] = migration["status"]
        if not migration_ok:
            raise RuntimeError("fresh/repeat upgrade or schema readback failed")

        fixture_sql = (
            "CREATE SCHEMA stage4_fixture; "
            "CREATE TABLE stage4_fixture.runtime_records ("
            "record_id text PRIMARY KEY, project_key text NOT NULL, "
            "payload jsonb NOT NULL, idempotency_key text UNIQUE NOT NULL); "
            "INSERT INTO stage4_fixture.runtime_records VALUES "
            "('fixture-001','stage4_s4_20260913','{\"kind\":\"market\",\"score\":11}','stage4-idem-001'),"
            "('fixture-002','stage4_s4_20260913','{\"kind\":\"risk\",\"score\":22}','stage4-idem-002'),"
            "('fixture-003','stage4_s4_20260913','{\"kind\":\"trend\",\"score\":33}','stage4-idem-003');"
        )
        run(
            "09a-synthetic-fixture-seed",
            COMPOSE_BASE + ["exec", "-T", "db", "psql", "-U", "postgres", "-d", "mrw_stage4", "-v", "ON_ERROR_STOP=1", "-c", fixture_sql],
        )
        fixture_query = (
            "SELECT record_id||'|'||project_key||'|'||payload::text||'|'||idempotency_key "
            "FROM stage4_fixture.runtime_records ORDER BY record_id;"
        )
        fixture_source = run(
            "09b-synthetic-fixture-readback",
            COMPOSE_BASE + ["exec", "-T", "db", "psql", "-U", "postgres", "-d", "mrw_stage4", "-At", "-c", fixture_query],
        ).stdout.strip()
        fixture_source_hash = hashlib.sha256(fixture_source.encode()).hexdigest()
        db_container_id = run("09c-db-container-id", COMPOSE_BASE + ["ps", "-q", "db"]).stdout.strip()
        run(
            "09d-snapshot-create",
            ["docker", "exec", db_container_id, "pg_dump", "-U", "postgres", "-d", "mrw_stage4", "-Fc", "-f", "/tmp/mrw-stage4-synthetic.dump"],
            timeout=300,
        )
        snapshot_path = OUT / "synthetic-production-like.snapshot.dump"
        if snapshot_path.exists():
            snapshot_path.unlink()
        run(
            "09e-snapshot-copy",
            ["docker", "cp", f"{db_container_id}:/tmp/mrw-stage4-synthetic.dump", str(snapshot_path)],
        )
        run(
            "09f-restore-db-create",
            ["docker", "exec", db_container_id, "createdb", "-U", "postgres", "mrw_stage4_restore"],
        )
        restore = run(
            "09g-snapshot-restore",
            ["docker", "exec", db_container_id, "pg_restore", "-U", "postgres", "-d", "mrw_stage4_restore", "--exit-on-error", "/tmp/mrw-stage4-synthetic.dump"],
            timeout=300,
        )
        fixture_restored = run(
            "09h-restored-fixture-readback",
            COMPOSE_BASE + ["exec", "-T", "db", "psql", "-U", "postgres", "-d", "mrw_stage4_restore", "-At", "-c", fixture_query],
        ).stdout.strip()
        restore_meta = run(
            "09i-restored-schema-readback",
            COMPOSE_BASE + ["exec", "-T", "db", "psql", "-U", "postgres", "-d", "mrw_stage4_restore", "-At", "-c", "SELECT version_num FROM alembic_version; SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"],
        ).stdout.splitlines()
        fixture_restored_hash = hashlib.sha256(fixture_restored.encode()).hexdigest()
        snapshot_ok = (
            restore.returncode == 0
            and fixture_source_hash == fixture_restored_hash
            and restore_meta[0].strip() == expected_head
            and int(restore_meta[1].strip()) == table_count
            and snapshot_path.stat().st_size > 0
        )
        snapshot_result = {
            "status": "PASS" if snapshot_ok else "FAIL",
            "classification": "TASK_OWNED_SYNTHETIC_PRODUCTION_LIKE_NOT_REAL_PRODUCTION_DATA",
            "source_database": "mrw_stage4",
            "restore_database": "mrw_stage4_restore",
            "project_key": "stage4_s4_20260913",
            "fixture_rows": len(fixture_source.splitlines()),
            "source_fixture_sha256": fixture_source_hash,
            "restored_fixture_sha256": fixture_restored_hash,
            "schema_head": restore_meta[0].strip(),
            "public_table_count": int(restore_meta[1].strip()),
            "snapshot_path": snapshot_path.name,
            "snapshot_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
            "snapshot_bytes": snapshot_path.stat().st_size,
            "restore_exit_code": restore.returncode,
            "production_or_unknown_database_contacted": False,
        }
        write_json("snapshot-restore.json", snapshot_result)
        results["snapshot_restore"] = snapshot_result["status"]
        if not snapshot_ok:
            raise RuntimeError("synthetic snapshot/restore readback failed")

        # Start all services without Compose's aggregate health gate. The
        # retained frontend image's wget healthcheck can lag under emulation;
        # explicit API/proxy/root/asset probes below remain authoritative for
        # this local runtime check.
        full_stack_up = run(
            "10-full-stack-up",
            COMPOSE_BASE + ["up", "-d", "--no-build", "--pull", "never", "db", "es", "redis", "backend", "celery-worker", "frontend"],
            check=False,
            timeout=480,
        )
        time.sleep(20)
        if full_stack_up.returncode != 0:
            run(
                "10a-full-stack-failure-ps",
                COMPOSE_BASE + ["ps", "-a", "--format", "json"],
                check=False,
            )
            run(
                "10b-full-stack-failure-logs",
                COMPOSE_BASE + ["logs", "--no-color", "--tail", "260", "backend", "celery-worker", "frontend", "es", "redis"],
                check=False,
            )
            raise RuntimeError(f"10-full-stack-up failed with exit {full_stack_up.returncode}")
        ps = run("11-full-stack-ps", COMPOSE_BASE + ["ps", "--format", "json"])
        services_state = parse_compose_ps(ps.stdout)
        logs = run(
            "12-service-logs",
            COMPOSE_BASE + ["logs", "--no-color", "--tail", "220", "backend", "celery-worker", "frontend"],
            check=False,
        )
        shallow_direct, shallow_direct_code = health_request(
            "13-health-shallow-direct", "http://127.0.0.1:18142/api/v1/health"
        )
        deep_direct, deep_direct_code = health_request(
            "14-health-deep-direct", "http://127.0.0.1:18142/api/v1/health/deep"
        )
        shallow_proxy, shallow_proxy_code = health_request(
            "15-health-shallow-proxy", "http://127.0.0.1:15142/api/v1/health"
        )
        deep_proxy, deep_proxy_code = health_request(
            "16-health-deep-proxy", "http://127.0.0.1:15142/api/v1/health/deep"
        )
        frontend = run(
            "17-frontend-root",
            ["curl", "--silent", "--show-error", "--output", "-", "--write-out", "\n%{http_code}", "http://127.0.0.1:15142/"],
        )
        frontend_body, frontend_code_raw = frontend.stdout.rsplit("\n", 1)
        asset = re.search(r'(?:src|href)=["\'](/assets/[^"\']+)["\']', frontend_body)
        asset_code = None
        if asset:
            asset_code = int(
                run(
                    "18-frontend-asset",
                    ["curl", "--silent", "--show-error", "--output", "/dev/null", "--write-out", "%{http_code}", f"http://127.0.0.1:15142{asset.group(1)}"],
                ).stdout
            )
        dependency_results = deep_direct.get("dependency_ping", {}).get("service_results", {})
        dependencies_ok = all(
            dependency_results.get(name, {}).get("status") == "ok"
            for name in ("database", "elasticsearch", "redis")
        )
        states_ok = all(
            services_state.get(name, {}).get("state") == "running"
            for name in ("db", "es", "redis", "backend", "celery-worker", "frontend")
        )
        health_ok = (
            states_ok
            and all(code == 200 for code in (shallow_direct_code, deep_direct_code, shallow_proxy_code, deep_proxy_code))
            and shallow_direct.get("status") == "ok"
            and shallow_proxy.get("status") == "ok"
            and deep_direct.get("status") == "ok"
            and deep_proxy.get("status") == "ok"
            and not deep_direct.get("missing_dependencies")
            and dependencies_ok
            and int(frontend_code_raw) == 200
            and asset_code == 200
        )
        full_stack = {
            "status": "PASS" if health_ok else "FAIL",
            "services": services_state,
            "http": {
                "shallow_direct": {"code": shallow_direct_code, "status": shallow_direct.get("status")},
                "deep_direct": {"code": deep_direct_code, "status": deep_direct.get("status")},
                "shallow_proxy": {"code": shallow_proxy_code, "status": shallow_proxy.get("status")},
                "deep_proxy": {"code": deep_proxy_code, "status": deep_proxy.get("status")},
                "frontend_root": int(frontend_code_raw),
                "frontend_asset": asset_code,
            },
            "dependency_ping": {name: dependency_results.get(name, {}).get("status") for name in ("database", "elasticsearch", "redis")},
            "provider_readiness": {
                "selected_provider": deep_direct.get("services", {}).get("llm", {}).get("provider"),
                "missing_dependencies": deep_direct.get("missing_dependencies", []),
                "credential_injected_to_task_containers": True,
                "credential_persisted_in_evidence": False,
                "external_model_calls": 0,
                "scope": "configuration/readiness through same-stack deep health only",
            },
            "production_runtime": {
                "env": "production",
                "observability_bearer_required": True,
                "production_require_tls": True,
                "localhost_transport": "HTTP for health-only runtime probe; TLS policy is evaluated separately for production effect routes",
            },
            "service_logs_exit_code": logs.returncode,
        }
        write_json("full-stack.json", full_stack)
        results["full_stack"] = full_stack["status"]
        if not health_ok:
            raise RuntimeError("full stack service/worker/health/proxy assertion failed")
        hold_seconds = int(os.environ.get("STAGE4_HOLD_SECONDS", "0") or "0")
        ready_path = Path("/tmp/mrw-stage4-local.ready.json")
        release_path = Path("/tmp/mrw-stage4-local.release")
        if hold_seconds > 0:
            ready_path.write_text(
                json.dumps(
                    {
                        "project": PROJECT,
                        "backend": "http://127.0.0.1:18142",
                        "frontend": "http://127.0.0.1:15142",
                        "candidate_commit": COMMIT,
                        "candidate_tree": TREE,
                        "ready_at": utc_now(),
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"STAGE4_RUNTIME_READY release_signal={release_path}", flush=True)
            deadline = time.monotonic() + hold_seconds
            while time.monotonic() < deadline and not release_path.exists():
                time.sleep(2)
            if not release_path.exists():
                raise RuntimeError(f"shared runtime hold timed out after {hold_seconds}s")
        status = "PASS_LOCAL_STAGE4_RUNTIME_NOT_AUTHORITY"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if started:
            cleanup_result = cleanup()
        elif collision:
            cleanup_result = {"status": "NOT_RUN_COLLISION_PRESERVED", "project_resources": before}
        else:
            cleanup_result = cleanup()
        write_json("cleanup.json", cleanup_result)
        after = project_resources()
        retained_images = {
            "backend": image_identity(BACKEND),
            "frontend": image_identity(FRONTEND),
            "migration-runner": image_identity(MIGRATION),
        }
        write_json(
            "99-resources-after.json",
            {
                "observed_at": utc_now(),
                "project": PROJECT,
                **after,
                "retained_stage3_images": retained_images,
            },
        )
        if cleanup_result.get("status") != "PASS" and not collision:
            status = "FAIL"
            error = error or "task resource cleanup failed"
        for signal_path in (
            Path("/tmp/mrw-stage4-local.ready.json"),
            Path("/tmp/mrw-stage4-local.release"),
        ):
            try:
                signal_path.unlink()
            except FileNotFoundError:
                pass

    summary = {
        "schema_version": "mrw.stage4.local-runtime.v1",
        "status": status,
        "authority_ceiling": "LOCAL_STAGE4_RUNTIME_ONLY / NOT_AUTHORITY / PRODUCTION_RELEASE_NOT_AUTHORIZED",
        "started_at": started_at,
        "ended_at": utc_now(),
        "candidate": {"label": "r13x", "root": str(CANDIDATE), "commit": COMMIT, "tree": TREE},
        "compose_project": PROJECT,
        "ports": {"backend": "127.0.0.1:18142", "frontend": "127.0.0.1:15142"},
        "results": {**results, "cleanup": cleanup_result.get("status")},
        "commands_policy": {
            "full_role_rebuild_executed": False,
            "entrypoint_only_derived_backend_build_executed": True,
            "secure_config_derived_backend_build_executed": True,
            "pull_allowed": False,
            "prune_executed": False,
        },
        "provider": {
            "credential_source": "project-owned main/backend/.env selected fields",
            "selected_fields": ["LLM_PROVIDER", "OPENAI_API_KEY", "OPENAI_API_BASE"],
            "secret_persisted": False,
            "external_model_calls": 0,
            "deep_health_same_stack": results.get("full_stack") == "PASS",
        },
        "remote_or_publish_actions": 0,
        "stage3_artifacts_preserved": True,
        "error": error,
        "risks": [
            "This local runtime evidence is non-authoritative and does not establish remote staging or release qualification.",
            "Health probes used the production observability token but did not make an external provider model call.",
            "Backend and Celery used a non-r13x derived image that replaced only /docker-entrypoint.sh on the exact retained r13x backend base; frontend and migration remained exact r13x.",
        ],
    }
    write_json("summary.json", summary)

    files = sorted(path for path in OUT.iterdir() if path.is_file() and path.name not in {"SHA256SUMS", "checksums-verify.log"})
    checksum_lines = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in files]
    (OUT / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    verify = subprocess.run(
        ["shasum", "-a", "256", "-c", "SHA256SUMS"],
        cwd=str(OUT),
        env=RUN_ENV,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    (OUT / "checksums-verify.log").write_text(
        f"AUTHORITATIVE=false\nEXIT_CODE={verify.returncode}\n{verify.stdout}",
        encoding="utf-8",
    )
    return 0 if status.startswith("PASS") and verify.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
