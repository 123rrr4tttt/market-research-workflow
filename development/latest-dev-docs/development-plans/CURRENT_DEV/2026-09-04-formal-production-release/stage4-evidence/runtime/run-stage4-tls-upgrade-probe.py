#!/usr/bin/env python3
"""Run bounded local TLS/trusted-proxy and representative pre-head upgrade probes."""

from __future__ import annotations

import hashlib
import importlib.util
import ipaddress
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


OUT = Path(__file__).resolve().parent
BASE_SCRIPT = OUT / "run-stage4-runtime.py"
TLS_OVERRIDE = OUT / "compose.tls-probe.override.yml"
TLS_NGINX = OUT / "tls-edge.nginx.conf"
SNAPSHOT = OUT / "synthetic-production-like.snapshot.dump"
TLS_SUBNET = ipaddress.ip_network("172.30.44.0/28")
TLS_EDGE_IP = "172.30.44.10"
TLS_PORT = 15442
PROBE_DATABASE = "mrw_stage4_upgrade_probe"
PRE_HEAD = "20260830_000001"
EXPECTED_HEAD = "20260905_000001"
LEGACY_ID = "stage4-upgrade-offset-001"
LEGACY_DIGEST = "a" * 64

spec = importlib.util.spec_from_file_location("stage4_runtime_base", BASE_SCRIPT)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load Stage 4 runtime helper")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def compose_tls() -> list[str]:
    return runtime.COMPOSE_BASE + ["-f", str(TLS_OVERRIDE)]


def tls_run(
    name: str,
    args: list[str],
    *,
    check: bool = True,
    timeout: int = 600,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return runtime.run(
        name,
        compose_tls() + args,
        check=check,
        timeout=timeout,
        input_text=input_text,
    )


def parse_marked_http(raw: str) -> tuple[str, dict[str, str]]:
    marker = "\nSTAGE4_HTTP_CODE="
    if marker not in raw:
        raise RuntimeError("curl output is missing Stage 4 status markers")
    body, marked = raw.rsplit(marker, 1)
    lines = marked.splitlines()
    values = {"http_code": lines[0].strip()}
    for line in lines[1:]:
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.removeprefix("STAGE4_").lower()] = value.strip()
    return body, values


def response_reason_code(payload: dict[str, Any]) -> str:
    detail = payload.get("detail") or {}
    top_error = payload.get("error") or {}
    nested_error = detail.get("error") or {} if isinstance(detail, dict) else {}
    candidates = [
        detail.get("reason_code") if isinstance(detail, dict) else None,
        (detail.get("details") or {}).get("reason_code") if isinstance(detail, dict) else None,
        (top_error.get("details") or {}).get("reason_code") if isinstance(top_error, dict) else None,
        (nested_error.get("details") or {}).get("reason_code") if isinstance(nested_error, dict) else None,
    ]
    return next((str(value) for value in candidates if value), "")


def request_config(*, include_spoofed_proto: bool, request_id: str) -> str:
    lines = [
        f'header = "Authorization: Bearer {runtime.TASK_AUTH_TOKEN}"',
        'header = "X-Project-Key: stage4_s4_20260913"',
        f'header = "X-Request-Id: {request_id}"',
    ]
    if include_spoofed_proto:
        lines.append('header = "X-Forwarded-Proto: http"')
    return "\n".join(lines) + "\n"


def occupied_networks() -> list[str]:
    listing = subprocess.run(
        ["docker", "network", "ls", "-q"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    ids = [line.strip() for line in listing.stdout.splitlines() if line.strip()]
    if not ids:
        return []
    inspected = subprocess.run(
        ["docker", "network", "inspect", *ids],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    values: list[str] = []
    for network in json.loads(inspected.stdout):
        for config in (network.get("IPAM") or {}).get("Config") or []:
            subnet = str(config.get("Subnet") or "").strip()
            if subnet:
                values.append(subnet)
    return sorted(set(values))


def ensure_probe_subnet_available() -> list[str]:
    observed = occupied_networks()
    overlaps = []
    for raw in observed:
        try:
            candidate = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            continue
        if candidate.version == TLS_SUBNET.version and candidate.overlaps(TLS_SUBNET):
            overlaps.append(raw)
    if overlaps:
        raise RuntimeError(f"task TLS subnet overlaps existing Docker networks: {overlaps}")
    return observed


def migration_command(name: str, database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    network = f"{runtime.PROJECT}_default"
    return runtime.run(
        name,
        [
            "docker",
            "run",
            "--rm",
            "--name",
            f"mrw-stage4-local-{name}",
            "--platform",
            "linux/amd64",
            "--network",
            network,
            "-e",
            f"DATABASE_URL={database_url}",
            "--entrypoint",
            "python",
            runtime.MIGRATION,
            "-m",
            "alembic",
            *args,
        ],
        timeout=360,
    )


def psql(name: str, database: str, sql: str) -> str:
    return tls_run(
        name,
        [
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "postgres",
            "-d",
            database,
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            "-c",
            sql,
        ],
    ).stdout.strip()


def log_output(name: str) -> str:
    raw = (OUT / f"{name}.log").read_text(encoding="utf-8")
    match = re.search(r"OUTPUT_BEGIN\n(.*)\nOUTPUT_END\n?$", raw, flags=re.DOTALL)
    if match is None:
        raise RuntimeError(f"{name}.log has no parseable output block")
    return match.group(1).strip()


def reused_upgrade_result() -> dict[str, Any]:
    before_revision = log_output("45a-upgrade-pre-head-current")
    before_row = log_output("45c-upgrade-legacy-row-before")
    to_head = log_output("46-upgrade-pre-head-to-head")
    current = log_output("46a-upgrade-current")
    after_revision = log_output("46b-upgrade-head-readback")
    after_row = log_output("46c-upgrade-legacy-row-after")
    schema_readback = log_output("46d-upgrade-schema-readback")
    database_absent = log_output("47a-upgrade-probe-db-absence") == "0"
    expected_before = f"{LEGACY_ID}|stage4_upgrade_probe|stage4-projector|v0|7|{LEGACY_DIGEST}|cursor:7|3"
    expected_after = expected_before + f"|LEGACY_OFFSET|projection-offset:{LEGACY_ID}|legacy:{LEGACY_DIGEST}|0"
    ok = (
        before_revision == PRE_HEAD
        and after_revision == EXPECTED_HEAD
        and EXPECTED_HEAD in current
        and before_row == expected_before
        and after_row == expected_after
        and schema_readback.splitlines()[0] == "runtime_run_projections"
        and "20260831_000002" in to_head
        and "20260525_000001" in to_head
        and EXPECTED_HEAD in to_head
        and database_absent
    )
    if not ok:
        raise RuntimeError("retained representative upgrade evidence failed deterministic readback")
    return {
        "status": "PASS",
        "from_revision": PRE_HEAD,
        "to_revision": EXPECTED_HEAD,
        "legacy_row_backfill": "PASS",
        "legacy_row_preserved": True,
        "sibling_branch_completed": True,
        "probe_database_removed": True,
        "reused_from_prior_attempt": True,
        "evidence_logs": [
            "45-upgrade-to-pre-head.log",
            "45a-upgrade-pre-head-current.log",
            "45c-upgrade-legacy-row-before.log",
            "46-upgrade-pre-head-to-head.log",
            "46a-upgrade-current.log",
            "46b-upgrade-head-readback.log",
            "46c-upgrade-legacy-row-after.log",
            "46d-upgrade-schema-readback.log",
            "47-upgrade-probe-db-drop.log",
            "47a-upgrade-probe-db-absence.log",
        ],
    }


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
        f"AUTHORITATIVE=false\nEXIT_CODE={verify.returncode}\n{verify.stdout}",
        encoding="utf-8",
    )
    return verify.returncode


def finalize_existing_evidence() -> int:
    resources = runtime.project_resources()
    graph_report = json.loads(log_output("32-migration-graph-check"))
    handshake = log_output("42-tls-handshake")
    tls_body, tls_meta = parse_marked_http(log_output("43-tls-trusted-proxy-request"))
    tls_payload = json.loads(tls_body)
    spoof_body, spoof_meta = parse_marked_http(log_output("48-untrusted-forwarded-proto-request"))
    spoof_payload = json.loads(spoof_body)
    reason_code = response_reason_code(spoof_payload)
    edge_ip = log_output("40-tls-edge-ip")
    trusted_ip = log_output("41-backend-forwarded-allow-ips")
    upgrade = reused_upgrade_result()
    tls_ok = (
        "CONNECTION ESTABLISHED" in handshake
        and "Protocol version: TLSv1.3" in handshake
        and "Verification: OK" in handshake
        and tls_meta.get("http_code") == "200"
        and tls_meta.get("ssl_verify") == "0"
        and tls_meta.get("remote_ip") in {"127.0.0.1", "::1"}
        and isinstance(tls_payload, dict)
        and edge_ip == TLS_EDGE_IP
        and trusted_ip == TLS_EDGE_IP
        and spoof_meta.get("http_code") == "403"
        and reason_code == "tls_denied"
    )
    cleanup_ok = not any(resources.values()) and "EXIT_CODE=0" in (OUT / "49-tls-compose-down.log").read_text(encoding="utf-8")
    result: dict[str, Any] = {
        "authoritative": False,
        "schema_version": "mrw.stage4.tls-upgrade-probe.v1",
        "status": "PASS" if tls_ok and cleanup_ok else "FAIL",
        "started_at": "2026-09-13T06:27:09Z",
        "ended_at": utc_now(),
        "authority_ceiling": "LOCAL_STAGE4_RUNTIME_ONLY / NOT_AUTHORITY / PRODUCTION_RELEASE_NOT_AUTHORIZED",
        "candidate": {"commit": runtime.COMMIT, "tree": runtime.TREE},
        "runtime_images": {
            "backend": runtime.BACKEND,
            "migration": runtime.MIGRATION,
            "tls_edge": runtime.FRONTEND,
        },
        "migration_graph": {
            "status": "PASS" if graph_report.get("status") == "passed" else "FAIL",
            "revision_count": graph_report.get("revision_count"),
            "roots": graph_report.get("roots"),
            "heads": graph_report.get("heads"),
            "checker": "32-migration-graph-check.log",
        },
        "tls": {
            "status": "PASS" if tls_ok else "FAIL",
            "handshake": "PASS" if "Verification: OK" in handshake else "FAIL",
            "protocol": "TLSv1.3" if "Protocol version: TLSv1.3" in handshake else "UNEXPECTED",
            "certificate_trust": "PASS" if tls_meta.get("ssl_verify") == "0" else "FAIL",
            "ephemeral_private_key_persisted": False,
            "trusted_proxy_ip": TLS_EDGE_IP,
            "trusted_proxy_path": "PASS" if tls_meta.get("http_code") == "200" else "FAIL",
            "incoming_proto_header_overridden_by_edge": True,
            "https_request_status": int(tls_meta.get("http_code") or 0),
            "tls_http_version": tls_meta.get("http_version"),
            "untrusted_host_spoof_status": int(spoof_meta.get("http_code") or 0),
            "untrusted_host_spoof_reason_code": reason_code,
            "observability_rollback_latched_seen_in_negative_response": reason_code == "observability_rollback_latched",
            "public_certificate_or_dns_verified": False,
            "evidence_logs": [
                "40-tls-edge-ip.log",
                "41-backend-forwarded-allow-ips.log",
                "41a-tls-scope-fixture.log",
                "42-tls-handshake.log",
                "43-tls-trusted-proxy-request.log",
                "48-untrusted-forwarded-proto-request.log",
            ],
        },
        "upgrade": {
            **upgrade,
            "baseline_classification": "CONSTRUCTED_REPRESENTATIVE_NOT_ACTUAL_PRODUCTION_PREDECESSOR",
            "all_historical_versions_covered": False,
        },
        "cleanup": {
            "status": "PASS" if cleanup_ok else "FAIL",
            "compose_down_exit_code": 0 if "EXIT_CODE=0" in (OUT / "49-tls-compose-down.log").read_text(encoding="utf-8") else 1,
            "project_residue": resources,
            "docker_prune_executed": False,
        },
        "project_resources_after": resources,
        "matrix_scope": {
            "fresh_migration_rerun": False,
            "snapshot_matrix_rerun": False,
            "restore_matrix_rerun": False,
            "full_stack_rerun": False,
            "upgrade_runtime_rerun_during_tls_correction": False,
        },
    }
    runtime.write_json("tls-upgrade-probe.json", result)
    if result["status"] == "PASS":
        update_aggregates(result)
    verify_rc = rebuild_index()
    return 0 if result["status"] == "PASS" and verify_rc == 0 else 1


def update_aggregates(result: dict[str, Any]) -> None:
    full_path = OUT / "full-stack.json"
    full = json.loads(full_path.read_text(encoding="utf-8"))
    full.setdefault("production_runtime", {}).update(
        {
            "local_tls_handshake_verified": result["tls"]["status"] == "PASS",
            "trusted_proxy_path_verified": result["tls"]["trusted_proxy_path"] == "PASS",
            "tls_evidence": "tls-upgrade-probe.json",
            "tls_scope": "task-local self-signed CA and fixed single-IP Docker proxy only",
        }
    )
    full["representative_pre_head_upgrade"] = {
        "status": result["upgrade"]["status"],
        "from_revision": PRE_HEAD,
        "to_revision": EXPECTED_HEAD,
        "legacy_row_backfill": result["upgrade"]["legacy_row_backfill"],
        "evidence": "tls-upgrade-probe.json",
        "classification": "CONSTRUCTED_REPRESENTATIVE_BASELINE_NOT_ACTUAL_PRODUCTION_PREDECESSOR",
    }
    runtime.write_json("full-stack.json", full)

    summary_path = OUT / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["ended_at"] = result["ended_at"]
    summary.setdefault("results", {})["tls_trusted_proxy_probe"] = result["tls"]["status"]
    summary["results"]["representative_pre_head_upgrade"] = result["upgrade"]["status"]
    summary["results"]["cleanup"] = result["cleanup"]["status"]
    summary.setdefault("commands_policy", {})["fresh_snapshot_restore_matrix_rerun_for_tls_upgrade_probe"] = False
    additions = [
        "The TLS probe used a task-local self-signed CA and one fixed trusted Docker proxy IP; it does not establish public certificate, DNS, or remote ingress readiness.",
        "The pre-head upgrade probe used a constructed 20260830_000001 baseline with one legacy row; it is not evidence for every historical version or an actual production predecessor.",
    ]
    risks = summary.setdefault("risks", [])
    for item in additions:
        if item not in risks:
            risks.append(item)
    runtime.write_json("summary.json", summary)


def main() -> int:
    started_at = utc_now()
    before = runtime.project_resources()
    result: dict[str, Any] = {
        "authoritative": False,
        "schema_version": "mrw.stage4.tls-upgrade-probe.v1",
        "status": "FAIL",
        "started_at": started_at,
        "authority_ceiling": "LOCAL_STAGE4_RUNTIME_ONLY / NOT_AUTHORITY / PRODUCTION_RELEASE_NOT_AUTHORIZED",
        "candidate": {"commit": runtime.COMMIT, "tree": runtime.TREE},
        "runtime_images": {
            "backend": runtime.BACKEND,
            "migration": runtime.MIGRATION,
            "tls_edge": runtime.FRONTEND,
        },
        "project_resources_before": before,
        "matrix_scope": {
            "fresh_migration_rerun": False,
            "snapshot_matrix_rerun": False,
            "restore_matrix_rerun": False,
            "full_stack_rerun": False,
        },
    }
    started = False
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    try:
        if any(before.values()):
            raise RuntimeError(f"task project collision: {before}")
        observed_subnets = ensure_probe_subnet_available()
        if not SNAPSHOT.is_file() or SNAPSHOT.stat().st_size == 0:
            raise RuntimeError("bound synthetic snapshot is unavailable")

        graph = runtime.run(
            "32-migration-graph-check",
            [
                str(runtime.WORKSPACE / ".venv/bin/python"),
                str(runtime.CANDIDATE / "scripts/check_backend_migration_graph.py"),
                "--expect-single-head",
                "--expect-head",
                EXPECTED_HEAD,
                "--json",
            ],
        )
        graph_report = json.loads(graph.stdout)
        if graph_report.get("status") != "passed" or graph_report.get("revision_count") != 36:
            raise RuntimeError("r13x migration graph check did not match the expected single-head graph")

        temp_dir = tempfile.TemporaryDirectory(prefix=".stage4-tls-probe-", dir=str(OUT))
        temp_root = Path(temp_dir.name)
        cert_path = temp_root / "tls.crt"
        key_path = temp_root / "tls.key"
        runtime.run(
            "33-tls-certificate-generate",
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-sha256",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
                "-keyout",
                str(key_path),
                "-out",
                str(cert_path),
            ],
        )
        os.chmod(key_path, 0o600)
        runtime.RUN_ENV.update(
            {
                "STAGE4_TLS_CERT_PATH": str(cert_path),
                "STAGE4_TLS_KEY_PATH": str(key_path),
                "STAGE4_TLS_NGINX_PATH": str(TLS_NGINX),
            }
        )
        resolved = json.loads(tls_run("34-tls-compose-config", ["config", "--format", "json"]).stdout)
        edge = resolved["services"]["tls-edge"]
        backend = resolved["services"]["backend"]
        compose_ok = (
            edge.get("image") == runtime.FRONTEND
            and edge.get("pull_policy") == "never"
            and backend.get("environment", {}).get("FORWARDED_ALLOW_IPS") == TLS_EDGE_IP
        )
        if not compose_ok:
            raise RuntimeError("TLS proxy Compose binding mismatch")

        tls_run(
            "35-tls-foundation-up",
            ["up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "180", "db", "es", "redis"],
            timeout=300,
        )
        started = True
        db_container = tls_run("36-tls-db-container-id", ["ps", "-q", "db"]).stdout.strip()
        runtime.run("37-tls-snapshot-copy", ["docker", "cp", str(SNAPSHOT), f"{db_container}:/tmp/mrw-stage4-synthetic.dump"])
        runtime.run(
            "38-tls-snapshot-restore",
            ["docker", "exec", db_container, "pg_restore", "-U", "postgres", "-d", "mrw_stage4", "--exit-on-error", "/tmp/mrw-stage4-synthetic.dump"],
            timeout=300,
        )
        tls_run(
            "39-tls-services-up",
            ["up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "240", "backend", "tls-edge"],
            timeout=360,
        )

        edge_ip = runtime.run(
            "40-tls-edge-ip",
            ["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", f"{runtime.PROJECT}-tls-edge-1"],
        ).stdout.strip()
        trusted_ip = tls_run(
            "41-backend-forwarded-allow-ips",
            ["exec", "-T", "backend", "sh", "-c", "printf '%s\\n' \"$FORWARDED_ALLOW_IPS\""],
        ).stdout.strip()
        if edge_ip != TLS_EDGE_IP or trusted_ip != TLS_EDGE_IP:
            raise RuntimeError(f"trusted proxy identity mismatch edge={edge_ip} backend={trusted_ip}")

        scope_fixture_code = """
import hashlib
import json
import os
from sqlalchemy import text
from app.models.base import engine
from app.services.request_identity import actor_id_from_secret
from app.successor_runtime.substrate.postgres.session import compute_scope_digest
from app.successor_runtime.runtime.authority_grants import AuthorityOperationScope

project_key = "stage4_s4_20260913"
resolved_schema = "project_stage4_s4_20260913"
registry_revision = 1
incarnation = "incarnation:stage4-tls-probe:v1"
scope_digest = compute_scope_digest(project_key, resolved_schema, registry_revision, incarnation)
actor_id = actor_id_from_secret("codex_auth_token", os.environ["CODEX_AUTH_TOKENS"])
operation_scope = AuthorityOperationScope.from_content(
    operation_kinds=("projects.list_projects",),
    project_scope_digest=scope_digest,
).model_dump(mode="json")
with engine.begin() as connection:
    connection.execute(text('''
        INSERT INTO public.project_scope_registry
            (project_key, registry_revision, resolved_schema, scope_digest, incarnation, state, updated_by, approval_ref)
        VALUES (:project_key, :registry_revision, :resolved_schema, :scope_digest, :incarnation, 'ACTIVE', 'stage4-tls-probe', 'stage4-tls-probe')
        ON CONFLICT (project_key, registry_revision) DO UPDATE SET
            resolved_schema=EXCLUDED.resolved_schema,
            scope_digest=EXCLUDED.scope_digest,
            incarnation=EXCLUDED.incarnation,
            state='ACTIVE',
            updated_by=EXCLUDED.updated_by,
            approval_ref=EXCLUDED.approval_ref
    '''), locals())
    connection.execute(text('''
        INSERT INTO public.runtime_capability_authority
            (project_key, capability_id, mode, authority_epoch, successor_claim_enabled, legacy_claim_enabled,
             allowlist_digest, config_digest, effective_at, updated_by, approval_ref, rollback_target_ref, revision)
        VALUES (:project_key, '', 'on', 1, true, false, :allowlist_digest, :config_digest,
                now(), 'stage4-tls-probe', 'stage4-tls-probe', 'stage4-tls-probe', 0)
        ON CONFLICT (project_key, capability_id) DO UPDATE SET
            mode='on', authority_epoch=1, successor_claim_enabled=true, legacy_claim_enabled=false,
            effective_at=now(), updated_by='stage4-tls-probe'
    '''), {
        "project_key": project_key,
        "allowlist_digest": hashlib.sha256(b"stage4-tls-allowlist").hexdigest(),
        "config_digest": hashlib.sha256(b"stage4-tls-config").hexdigest(),
    })
    connection.execute(text('''
        INSERT INTO public.runtime_authority_grants
            (grant_id, project_key, actor_id, capability_id, operation_scope_json,
             resource_ceiling_json, grant_epoch, expires_at, revoked_at, revision)
        VALUES ('stage4-tls-api-invoke', :project_key, :actor_id, '', CAST(:operation_scope AS jsonb),
                '{}'::jsonb, 1, NULL, NULL, 0)
        ON CONFLICT (project_key, grant_id) DO UPDATE SET
            actor_id=EXCLUDED.actor_id,
            operation_scope_json=EXCLUDED.operation_scope_json,
            revoked_at=NULL,
            revision=runtime_authority_grants.revision + 1
    '''), {
        "project_key": project_key,
        "actor_id": actor_id,
        "operation_scope": json.dumps(operation_scope, sort_keys=True),
    })
print("scope_fixture=ready")
print("project_scope_digest=" + scope_digest)
print("actor_identity_sha256=" + hashlib.sha256(actor_id.encode()).hexdigest())
"""
        scope_fixture = tls_run(
            "41a-tls-scope-fixture",
            ["exec", "-T", "backend", "python", "-c", scope_fixture_code],
        )
        if "scope_fixture=ready" not in scope_fixture.stdout:
            raise RuntimeError("task-local TLS project scope fixture was not installed")

        deadline = time.monotonic() + 60
        while True:
            ready = subprocess.run(
                ["curl", "--noproxy", "*", "--cacert", str(cert_path), "--silent", "--show-error", "--output", "/dev/null", "https://localhost:15442/ready"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(f"TLS edge readiness timed out: {ready.stderr.strip()}")
            time.sleep(2)

        handshake = runtime.run(
            "42-tls-handshake",
            ["openssl", "s_client", "-connect", "127.0.0.1:15442", "-servername", "localhost", "-CAfile", str(cert_path), "-verify_return_error", "-brief"],
            input_text="",
            timeout=30,
        )
        tls_response = runtime.run(
            "43-tls-trusted-proxy-request",
            [
                "curl",
                "--config",
                "-",
                "--noproxy",
                "*",
                "--cacert",
                str(cert_path),
                "--silent",
                "--show-error",
                "--output",
                "-",
                "--write-out",
                "\\nSTAGE4_HTTP_CODE=%{http_code}\\nSTAGE4_SSL_VERIFY=%{ssl_verify_result}\\nSTAGE4_REMOTE_IP=%{remote_ip}\\nSTAGE4_HTTP_VERSION=%{http_version}\\n",
                "https://localhost:15442/api/v1/projects",
            ],
            input_text=request_config(
                include_spoofed_proto=True,
                request_id="stage4-tls-trusted-proxy-probe",
            ),
        )
        tls_body, tls_meta = parse_marked_http(tls_response.stdout)
        tls_payload = json.loads(tls_body)
        tls_positive_ok = (
            tls_meta.get("http_code") == "200"
            and tls_meta.get("ssl_verify") == "0"
            and tls_meta.get("remote_ip") in {"127.0.0.1", "::1"}
            and isinstance(tls_payload, dict)
        )
        if not tls_positive_ok:
            reason = response_reason_code(tls_payload)
            raise RuntimeError(
                f"trusted TLS proxy request was not admitted: http={tls_meta.get('http_code')} reason={reason}"
            )

        reuse_upgrade = os.environ.get("STAGE4_REUSE_UPGRADE_EVIDENCE") == "1"
        expected_before = f"{LEGACY_ID}|stage4_upgrade_probe|stage4-projector|v0|7|{LEGACY_DIGEST}|cursor:7|3"
        expected_after = expected_before + f"|LEGACY_OFFSET|projection-offset:{LEGACY_ID}|legacy:{LEGACY_DIGEST}|0"
        if reuse_upgrade:
            reused_upgrade = reused_upgrade_result()
            before_row = log_output("45c-upgrade-legacy-row-before")
            after_row = log_output("46c-upgrade-legacy-row-after")
            schema_readback = log_output("46d-upgrade-schema-readback")
            to_head_output = log_output("46-upgrade-pre-head-to-head")
            database_absent = reused_upgrade["probe_database_removed"]
        else:
            tls_run("44-upgrade-probe-db-create", ["exec", "-T", "db", "createdb", "-U", "postgres", PROBE_DATABASE])
            probe_url = runtime.RUN_ENV["DATABASE_URL"].rsplit("/", 1)[0] + f"/{PROBE_DATABASE}"
            pre_upgrade = migration_command("45-upgrade-to-pre-head", probe_url, "upgrade", PRE_HEAD)
            before_revision = psql("45a-upgrade-pre-head-current", PROBE_DATABASE, "SELECT version_num FROM alembic_version ORDER BY version_num;")
            legacy_insert_sql = (
                "INSERT INTO public.runtime_projection_offsets "
                "(projection_offset_id,project_key,projector_id,projector_version,source_revision,source_digest,offset_ref,revision) VALUES "
                f"('{LEGACY_ID}','stage4_upgrade_probe','stage4-projector','v0',7,'{LEGACY_DIGEST}','cursor:7',3);"
            )
            psql("45b-upgrade-legacy-row-insert", PROBE_DATABASE, legacy_insert_sql)
            before_row = psql(
                "45c-upgrade-legacy-row-before",
                PROBE_DATABASE,
                "SELECT projection_offset_id||'|'||project_key||'|'||projector_id||'|'||projector_version||'|'||source_revision||'|'||source_digest||'|'||offset_ref||'|'||revision FROM public.runtime_projection_offsets WHERE projection_offset_id='stage4-upgrade-offset-001';",
            )
            to_head = migration_command("46-upgrade-pre-head-to-head", probe_url, "upgrade", "head")
            current = migration_command("46a-upgrade-current", probe_url, "current")
            after_revision = psql("46b-upgrade-head-readback", PROBE_DATABASE, "SELECT version_num FROM alembic_version ORDER BY version_num;")
            after_row = psql(
                "46c-upgrade-legacy-row-after",
                PROBE_DATABASE,
                "SELECT projection_offset_id||'|'||project_key||'|'||projector_id||'|'||projector_version||'|'||source_revision||'|'||source_digest||'|'||offset_ref||'|'||revision||'|'||source_kind||'|'||source_ref||'|'||source_incarnation||'|'||projection_generation FROM public.runtime_projection_offsets WHERE projection_offset_id='stage4-upgrade-offset-001';",
            )
            schema_readback = psql(
                "46d-upgrade-schema-readback",
                PROBE_DATABASE,
                "SELECT to_regclass('public.runtime_run_projections'); SELECT column_name||'|'||is_nullable||'|'||coalesce(column_default,'') FROM information_schema.columns WHERE table_schema='public' AND table_name='runtime_projection_offsets' AND column_name IN ('source_kind','source_ref','source_incarnation','projection_generation') ORDER BY column_name;",
            )
            to_head_output = to_head.stdout
            upgrade_ok = (
                pre_upgrade.returncode == 0
                and to_head.returncode == 0
                and before_revision == PRE_HEAD
                and after_revision == EXPECTED_HEAD
                and EXPECTED_HEAD in current.stdout
                and before_row == expected_before
                and after_row == expected_after
                and schema_readback.splitlines()[0] == "runtime_run_projections"
                and "20260831_000002" in to_head_output
                and "20260525_000001" in to_head_output
                and EXPECTED_HEAD in to_head_output
            )
            if not upgrade_ok:
                raise RuntimeError("representative pre-head upgrade/backfill assertions failed")
            tls_run("47-upgrade-probe-db-drop", ["exec", "-T", "db", "dropdb", "-U", "postgres", PROBE_DATABASE])
            database_absent = psql("47a-upgrade-probe-db-absence", "postgres", f"SELECT count(*) FROM pg_database WHERE datname='{PROBE_DATABASE}';") == "0"
            if not database_absent:
                raise RuntimeError("upgrade probe database was not removed")

        spoofed = runtime.run(
            "48-untrusted-forwarded-proto-request",
            [
                "curl",
                "--config",
                "-",
                "--noproxy",
                "*",
                "--silent",
                "--show-error",
                "--output",
                "-",
                "--write-out",
                "\\nSTAGE4_HTTP_CODE=%{http_code}\\n",
                "--header",
                "X-Forwarded-Proto: https",
                "http://127.0.0.1:18142/api/v1/projects",
            ],
            input_text=request_config(
                include_spoofed_proto=False,
                request_id="stage4-untrusted-forwarded-proto-probe",
            ),
            check=False,
        )
        spoof_body, spoof_meta = parse_marked_http(spoofed.stdout)
        spoof_payload = json.loads(spoof_body)
        detail = spoof_payload.get("detail") or {}
        nested_error = detail.get("error") if isinstance(detail, dict) else None
        nested_details = nested_error.get("details") if isinstance(nested_error, dict) else None
        reason_code = str(
            (detail.get("reason_code") if isinstance(detail, dict) else None)
            or (nested_details.get("reason_code") if isinstance(nested_details, dict) else None)
            or ""
        )
        untrusted_rejected = spoof_meta.get("http_code") == "403" and reason_code == "tls_denied"
        if not untrusted_rejected:
            raise RuntimeError("untrusted forwarded-proto spoof was not denied by the TLS policy")

        runtime.run("48a-tls-probe-service-logs", compose_tls() + ["logs", "--no-color", "--tail", "160", "backend", "tls-edge"], check=False)
        cert_fingerprint = hashlib.sha256(cert_path.read_bytes()).hexdigest()
        result.update(
            {
                "status": "PASS",
                "migration_graph": {
                    "status": "PASS",
                    "revision_count": graph_report["revision_count"],
                    "roots": graph_report["roots"],
                    "heads": graph_report["heads"],
                    "checker": "32-migration-graph-check.log",
                },
                "tls": {
                    "status": "PASS" if tls_positive_ok and untrusted_rejected else "FAIL",
                    "handshake_exit_code": handshake.returncode,
                    "certificate_trust": "PASS" if tls_meta.get("ssl_verify") == "0" else "FAIL",
                    "ephemeral_certificate_sha256": cert_fingerprint,
                    "ephemeral_private_key_persisted": False,
                    "trusted_proxy_ip": TLS_EDGE_IP,
                    "trusted_proxy_path": "PASS" if tls_positive_ok else "FAIL",
                    "incoming_proto_header_overridden_by_edge": True,
                    "https_request_status": int(tls_meta["http_code"]),
                    "tls_http_version": tls_meta.get("http_version"),
                    "untrusted_host_spoof_status": int(spoof_meta["http_code"]),
                    "untrusted_host_spoof_reason_code": reason_code,
                    "public_certificate_or_dns_verified": False,
                },
                "upgrade": {
                    "status": "PASS",
                    "from_revision": PRE_HEAD,
                    "to_revision": EXPECTED_HEAD,
                    "baseline_classification": "CONSTRUCTED_REPRESENTATIVE_NOT_ACTUAL_PRODUCTION_PREDECESSOR",
                    "legacy_row_backfill": "PASS",
                    "legacy_fields_preserved": before_row == expected_before and after_row.startswith(expected_before + "|"),
                    "new_projection_table_present": schema_readback.splitlines()[0] == "runtime_run_projections",
                    "sibling_branch_applied": "20260525_000001" in to_head_output,
                    "probe_database_removed": database_absent,
                    "reused_from_prior_attempt": reuse_upgrade,
                    "all_historical_versions_covered": False,
                },
                "docker_subnets_observed_before": observed_subnets,
                "ended_at": utc_now(),
            }
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result.setdefault("ended_at", utc_now())
    finally:
        if started:
            cleanup_run = tls_run(
                "49-tls-compose-down",
                ["down", "--volumes", "--remove-orphans", "--timeout", "30"],
                check=False,
                timeout=240,
            )
            residue = runtime.project_resources()
            cleanup = {
                "status": "PASS" if cleanup_run.returncode == 0 and not any(residue.values()) else "FAIL",
                "down_exit_code": cleanup_run.returncode,
                "project_residue": residue,
                "docker_prune_executed": False,
            }
        elif any(before.values()):
            cleanup = {"status": "NOT_RUN_COLLISION_PRESERVED", "project_residue": before}
        else:
            cleanup = {"status": "NOT_NEEDED", "project_residue": runtime.project_resources()}
        if temp_dir is not None:
            temp_dir.cleanup()
        result["cleanup"] = cleanup
        result["project_resources_after"] = runtime.project_resources()
        result["ended_at"] = utc_now()
        if cleanup.get("status") not in {"PASS", "NOT_NEEDED"}:
            result["status"] = "FAIL"
            result["error"] = result.get("error") or "task resource cleanup failed"

    runtime.write_json("tls-upgrade-probe.json", result)
    if result.get("status") == "PASS" and result.get("tls", {}).get("status") == "PASS" and result.get("upgrade", {}).get("status") == "PASS":
        update_aggregates(result)
    verify_rc = rebuild_index()
    return 0 if result.get("status") == "PASS" and verify_rc == 0 else 1


if __name__ == "__main__":
    if os.environ.get("STAGE4_FINALIZE_EXISTING_EVIDENCE") == "1":
        raise SystemExit(finalize_existing_evidence())
    raise SystemExit(main())
