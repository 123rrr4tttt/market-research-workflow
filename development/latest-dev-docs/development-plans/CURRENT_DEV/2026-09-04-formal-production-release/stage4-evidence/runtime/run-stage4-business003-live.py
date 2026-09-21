#!/usr/bin/env python3
"""Close S4-BUSINESS-003 against the task-owned Stage 4 Compose runtime."""

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
LIVE_OVERRIDE = OUT / "compose.business003.override.yml"
SNAPSHOT = OUT / "synthetic-production-like.snapshot.dump"
DERIVED_IMAGE = "mrw-local/stage4-business003:f0e694fa35a8227e"
PROJECT_KEY = "stage4_s4_20260913"
PROJECT_SCHEMA = "project_stage4_s4_20260913"
REGISTRY_REVISION = 1
INCARNATION = "incarnation:stage4-tls-probe:v1"
PROJECTION_ID = "projection:stage4-business003:v1"
PROJECTOR_ID = "projector:stage4-business003"
PROJECTOR_VERSION = "1"
SOURCE_KIND = "successor_values"
SOURCE_REF = f"project:{PROJECT_KEY}:semantic-sources"

spec = importlib.util.spec_from_file_location("stage4_runtime_base", BASE_SCRIPT)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load Stage 4 runtime helper")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
runtime.BACKEND = DERIVED_IMAGE
runtime.RUN_ENV["BACKEND_IMAGE_DIGEST"] = DERIVED_IMAGE
runtime.COMPOSE_BASE += ["-f", str(LIVE_OVERRIDE)]


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def request(body: dict[str, Any], *, project_header: str) -> tuple[int, dict[str, Any]]:
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    probe_code = f'''
import json
import os
import urllib.error
import urllib.request

body = {encoded!r}.encode()
request = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/successor-runtime/v2/queries",
    data=body,
    method="POST",
    headers={{
        "Authorization": "Bearer " + os.environ["CODEX_AUTH_TOKENS"],
        "Content-Type": "application/json",
        "X-Project-Key": {project_header!r},
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
    completed = subprocess.run(
        runtime.COMPOSE_BASE + ["exec", "-T", "backend", "python", "-c", probe_code],
        cwd=str(runtime.CANDIDATE),
        env=runtime.RUN_ENV,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("container-loopback HTTP probe failed")
    wrapped = json.loads(completed.stdout.strip().splitlines()[-1])
    return int(wrapped["http_status"]), wrapped["payload"]


def main() -> int:
    started_at = utc_now()
    before = runtime.project_resources()
    image = runtime.image_identity(DERIVED_IMAGE)
    base = runtime.image_identity(runtime.BASE_BACKEND)
    result: dict[str, Any] = {
        "authoritative": False,
        "schema_version": "mrw.stage4.business003-live-readback.v1",
        "status": "FAIL",
        "started_at": started_at,
        "frozen_r13x_modified": False,
        "provider_calls": 0,
        "command_writes": 0,
        "migration_matrix_rerun": False,
        "snapshot_reused": SNAPSHOT.name,
        "compose_project": runtime.PROJECT,
        "images": {
            "r13x_base": {"reference": runtime.BASE_BACKEND, "image_id": base["id"]},
            "backend_and_celery": {"reference": DERIVED_IMAGE, "image_id": image["id"]},
        },
        "project_resources_before": before,
    }
    started = False
    error: str | None = None
    try:
        if any(before.values()):
            raise RuntimeError(f"task project collision: {before}")
        if not SNAPSHOT.is_file() or SNAPSHOT.stat().st_size == 0:
            raise RuntimeError("bound synthetic snapshot is unavailable")
        if image["platform"] != "linux/amd64":
            raise RuntimeError("derived backend architecture mismatch")

        runtime.run(
            "60-business003-foundation-up",
            runtime.COMPOSE_BASE
            + ["up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "180", "db", "es", "redis"],
            timeout=300,
        )
        started = True
        db_container = runtime.run(
            "61-business003-db-container", runtime.COMPOSE_BASE + ["ps", "-q", "db"]
        ).stdout.strip()
        runtime.run(
            "62-business003-snapshot-copy",
            ["docker", "cp", str(SNAPSHOT), f"{db_container}:/tmp/mrw-stage4-synthetic.dump"],
        )
        runtime.run(
            "63-business003-snapshot-restore",
            ["docker", "exec", db_container, "pg_restore", "-U", "postgres", "-d", "mrw_stage4", "--exit-on-error", "/tmp/mrw-stage4-synthetic.dump"],
            timeout=300,
        )
        runtime.run(
            "64-business003-services-up",
            runtime.COMPOSE_BASE
            + ["up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "300", "backend", "celery-worker"],
            timeout=420,
        )

        fixture_code = f'''
import hashlib
import json
import os
import sqlalchemy as sa
from sqlalchemy import MetaData, delete, insert, text
from app.models.base import engine
from app.services.request_identity import actor_id_from_secret
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.runtime.authority_grants import AuthorityOperationScope
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES, project_tables
from app.successor_runtime.substrate.postgres.projection_offsets import ProjectionOffsetKey, ProjectionOffsetRepository
from app.successor_runtime.substrate.postgres.session import compute_scope_digest
from app.successor_runtime.substrate.postgres.values import ValueRepository

project_key = {PROJECT_KEY!r}
resolved_schema = {PROJECT_SCHEMA!r}
registry_revision = {REGISTRY_REVISION}
incarnation = {INCARNATION!r}
projector_id = {PROJECTOR_ID!r}
projector_version = {PROJECTOR_VERSION!r}
source_kind = {SOURCE_KIND!r}
source_ref = {SOURCE_REF!r}
scope_digest = compute_scope_digest(project_key, resolved_schema, registry_revision, incarnation)
actor_id = actor_id_from_secret("codex_auth_token", os.environ["CODEX_AUTH_TOKENS"])
scope = RuntimeScope(ProjectScopeRef(project_key, resolved_schema, registry_revision, incarnation, scope_digest), actor_id)
operation_scope = AuthorityOperationScope.from_content(
    operation_kinds=("successor-runtime.run_query",),
    project_scope_digest=scope_digest,
).model_dump(mode="json")
source_digest = hashlib.sha256(canonical_bytes({{"source_ref": source_ref, "revision": 7}})).hexdigest()
key = ProjectionOffsetKey(projector_id, projector_version, source_kind, source_ref, incarnation)

with engine.begin() as connection:
    connection.execute(delete(PUBLIC_TABLES["runtime_projection_offsets"]).where(PUBLIC_TABLES["runtime_projection_offsets"].c.project_key == project_key))
    connection.execute(delete(PUBLIC_TABLES["runtime_authority_grants"]).where(PUBLIC_TABLES["runtime_authority_grants"].c.project_key == project_key))
    connection.execute(delete(PUBLIC_TABLES["runtime_capability_authority"]).where(PUBLIC_TABLES["runtime_capability_authority"].c.project_key == project_key))
    connection.execute(delete(PUBLIC_TABLES["project_scope_registry"]).where(PUBLIC_TABLES["project_scope_registry"].c.project_key == project_key))
    connection.execute(text(f'DROP SCHEMA IF EXISTS "{{resolved_schema}}" CASCADE'))
    connection.execute(text(f'CREATE SCHEMA "{{resolved_schema}}"'))
    metadata = MetaData(schema=resolved_schema)
    tables = project_tables(metadata, resolved_schema)
    metadata.create_all(connection)
    connection.execute(insert(PUBLIC_TABLES["project_scope_registry"]).values(
        project_key=project_key, registry_revision=registry_revision, resolved_schema=resolved_schema,
        scope_digest=scope_digest, incarnation=incarnation, state="ACTIVE", updated_by="stage4-business003-live",
        approval_ref="stage4-business003-live",
    ))
    connection.execute(insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
        project_key=project_key, capability_id="", mode="on", authority_epoch=1,
        successor_claim_enabled=True, legacy_claim_enabled=False,
        allowlist_digest=hashlib.sha256(b"stage4-business003-allowlist").hexdigest(),
        config_digest=hashlib.sha256(b"stage4-business003-config").hexdigest(),
        effective_at=sa.func.now(), updated_by="stage4-business003-live",
        approval_ref="stage4-business003-live", rollback_target_ref="stage4-business003-live", revision=0,
    ))
    connection.execute(insert(PUBLIC_TABLES["runtime_authority_grants"]).values(
        grant_id="stage4-business003-api-invoke", project_key=project_key, actor_id=actor_id,
        capability_id="", operation_scope_json=operation_scope, resource_ceiling_json={{}},
        credential_ref=None, grant_epoch=1, expires_at=None, revoked_at=None, revision=0,
    ))
    sinks = {{
        "agent_session": "AgentSessionLocalProjection.v1",
        "graph": "GraphLocalProjection.v1",
        "search": "SearchLocalProjection.v1",
    }}
    for sink, object_type in sinks.items():
        provenance = {{
            "projector_id": projector_id, "projector_version": projector_version,
            "source_kind": source_kind, "source_ref": source_ref,
            "source_incarnation": incarnation, "projection_generation": 1, "sink": sink,
        }}
        content = {{"schema_version": "mrw.stage4.business003-candidate.v1", "payload": {{"sink": sink, "marker": "task-local"}}}}
        content_digest = hashlib.sha256(canonical_bytes(content)).hexdigest()
        provenance_digest = hashlib.sha256(canonical_bytes(provenance)).hexdigest()
        ValueRepository(connection, tables).put_exact(
            scope, value_id=f"stage4-business003-{{sink}}", object_type=object_type,
            codec_id="codec:stage4-business003:v1", content=content, expected_digest=content_digest,
            provenance_digest=provenance_digest, expected_revision=0,
            expected_incarnation=f"stage4-business003-{{sink}}:v1", source_ref=source_ref,
            provenance=provenance,
        )
    ProjectionOffsetRepository(connection, scope).create(
        projection_offset_id="stage4-business003-offset", key=key,
        projection_generation=1, source_revision=7, source_digest=source_digest,
        offset_ref="cursor:stage4-business003:7",
    )

print(json.dumps({{
    "scope_digest": scope_digest,
    "actor_identity_sha256": hashlib.sha256(actor_id.encode()).hexdigest(),
    "source_digest": source_digest,
    "candidate_count": 3,
}}, sort_keys=True))
'''
        fixture = runtime.run(
            "65-business003-scope-projection-seed",
            runtime.COMPOSE_BASE + ["exec", "-T", "backend", "python", "-c", fixture_code],
        )
        seeded = json.loads(fixture.stdout.strip().splitlines()[-1])

        body = {
            "query_id": "stage4-business003-query-001",
            "query_kind": "projection_snapshot",
            "project_locator": PROJECT_KEY,
            "trace_id": "stage4-business003-trace-001",
            "params": {
                "params_kind": "projection_snapshot",
                "projection_id": PROJECTION_ID,
                "projector_id": PROJECTOR_ID,
                "projector_version": PROJECTOR_VERSION,
                "source_kind": SOURCE_KIND,
                "source_ref": SOURCE_REF,
                "source_incarnation": INCARNATION,
            },
        }
        positive_code, positive = request(body, project_header=PROJECT_KEY)
        expected_scope = {
            "project_key": PROJECT_KEY,
            "resolved_schema": PROJECT_SCHEMA,
            "project_registry_revision": REGISTRY_REVISION,
            "incarnation": INCARNATION,
            "scope_digest": seeded["scope_digest"],
        }
        positive_meta = positive.get("meta") or {}
        positive_data = positive.get("data") or {}
        observed_scope = positive_meta.get("project_scope_ref")
        sinks = sorted(item.get("sink") for item in (positive_data.get("candidate_values") or []))
        result["observed_response_summary"] = {
            "http_status": positive_code,
            "envelope_status": positive.get("status"),
            "error_code": (positive.get("error") or {}).get("code"),
            "error_message": (positive.get("error") or {}).get("message"),
            "scope": observed_scope,
            "candidate_sinks": sinks,
        }
        positive_ok = (
            positive_code == 200
            and positive.get("status") == "ok"
            and positive.get("control_feedback") is False
            and observed_scope == expected_scope
            and sinks == ["agent_session", "graph", "search"]
            and positive_data.get("source_digest") == seeded["source_digest"]
        )

        foreign_body = dict(body)
        foreign_body.update({"query_id": "stage4-business003-foreign-001", "project_locator": "stage4_foreign_20260913"})
        foreign_code, foreign = request(foreign_body, project_header=PROJECT_KEY)
        foreign_error = foreign.get("error") or {}
        foreign_resolver_ok = (
            foreign_code == 200
            and foreign.get("status") == "error"
            and foreign_error.get("code") == "SCOPE_RESOLUTION_FAILED"
        )
        policy_code, policy_foreign = request(foreign_body, project_header="stage4_foreign_20260913")
        foreign_policy_ok = policy_code in {403, 503} and policy_foreign.get("status") == "error"

        if not (positive_ok and foreign_resolver_ok and foreign_policy_ok):
            raise RuntimeError(
                "live query closure failed: "
                f"positive={positive_code}/{positive.get('status')} "
                f"resolver={foreign_code}/{foreign.get('status')} "
                f"policy={policy_code}"
            )

        result.update(
            {
                "status": "PASS_LOCAL_STAGE4_BUSINESS003_NOT_AUTHORITY",
                "ended_at": utc_now(),
                "fixture": {
                    "project_scope_ref": expected_scope,
                    "actor_identity_sha256": seeded["actor_identity_sha256"],
                    "candidate_count": seeded["candidate_count"],
                    "projection_generation": 1,
                    "source_revision": 7,
                    "source_digest": seeded["source_digest"],
                },
                "request_summary": {
                    "method": "POST",
                    "route": "/api/v1/successor-runtime/v2/queries",
                    "query_kind": body["query_kind"],
                    "query_id": body["query_id"],
                    "body_sha256": hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                },
                "authenticated_projection_snapshot": {
                    "http_status": positive_code,
                    "envelope_status": positive["status"],
                    "scope_exact_match": True,
                    "control_feedback": positive["control_feedback"],
                    "candidate_sinks": sinks,
                    "projection_generation": positive["data"]["projection_generation"],
                    "offset_revision": positive["data"]["offset_revision"],
                    "cursor": positive["data"]["cursor"],
                },
                "foreign_tenant_rejection": {
                    "same_header_foreign_locator": {
                        "http_status": foreign_code,
                        "error_code": foreign_error.get("code"),
                        "rejected": foreign_resolver_ok,
                    },
                    "foreign_header_and_locator": {"http_status": policy_code, "rejected": foreign_policy_ok},
                },
                "reused_evidence": {
                    "snapshot": "snapshot-restore.json",
                    "tls_and_upgrade": "tls-upgrade-probe.json",
                    "migration_or_tls_matrix_rerun": False,
                },
            }
        )
    except Exception as exc:  # noqa: BLE001 - evidence must retain the failure
        error = str(exc)
        result["error"] = error
        result["ended_at"] = utc_now()
    finally:
        if started:
            runtime.run(
                "69-business003-cleanup",
                runtime.COMPOSE_BASE + ["down", "--volumes", "--remove-orphans", "--timeout", "30"],
                check=False,
                timeout=180,
            )
        after = runtime.project_resources()
        result["cleanup"] = {"status": "PASS" if not any(after.values()) else "FAIL", "resources_after": after}
        if result["cleanup"]["status"] != "PASS":
            result["status"] = "FAIL"
            result["error"] = result.get("error") or "task Compose resources remain after cleanup"
        runtime.write_json("s4-business-003-live-readback.json", result)
    return 0 if result["status"] == "PASS_LOCAL_STAGE4_BUSINESS003_NOT_AUTHORITY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
