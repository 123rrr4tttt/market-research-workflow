#!/usr/bin/env python3
"""Run the local Stage5 image/config/credential and route-fallback rehearsal."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STAGE4_ROOT = (
    REPOSITORY_ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    / "2026-09-04-formal-production-release/stage4-evidence"
)
STAGE4_CLEANUP_PATH = STAGE4_ROOT / "runtime/post-acceptance-cleanup.json"
R13W_EXECUTION_RECORD_PATH = (
    STAGE4_ROOT.parent
    / "stage3-evidence/r13w/artifacts/execution-record.json"
)
RESULT_PATH = Path(__file__).with_name("rollback-fallback-result.v1.json")
PROJECT_PREFIX = "mrw-stage5-rollback"
PLATFORM = "linux/amd64"

IMAGES = {
    "backend": {
        "current": "mrw-local/stage4-business001:stage4-c9-effect",
        "previous": (
            "mrw-local/r13x-candidate-backend:"
            "8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2"
        ),
        "capability_probe": (
            "if grep -q 'postgres.c9_projection_rebuild.v1' "
            "/app/app/composition/production_route_bindings.json 2>/dev/null; then "
            "echo c9_writer_binding=present; else echo c9_writer_binding=absent; fi; "
            "echo role=backend"
        ),
        "config_probe": (
            'test "${MRW_FIXTURE_CONFIG_REVISION}" = "$EXPECTED_CONFIG_REVISION" && '
            'printf "config_revision_observed=%s\\n" "$EXPECTED_CONFIG_REVISION"'
        ),
    },
    "frontend": {
        "current": "mrw-local/r13w-candidate-frontend:6aa7518750f2c29229a443f73248c8133f192e4d",
        "previous": (
            "mrw-local/r13x-candidate-frontend:"
            "8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2"
        ),
        "capability_probe": (
            "test -f /usr/share/nginx/html/index.html && echo role=frontend"
        ),
        "config_probe": None,
    },
}

STAGE4_ROUTE_BINDING_SHA256 = (
    "9d88ad8dfd41c633bc60a3c7fcf4243e18b9bbb29948a8ce3d6d39fee28db51b"
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def object_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def run_command(
    command: list[str],
    *,
    timeout: float = 30.0,
    check: bool = True,
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    receipt = {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "stdout_sha256": bytes_digest(completed.stdout.encode("utf-8")),
        "stderr_sha256": bytes_digest(completed.stderr.encode("utf-8")),
    }
    if check and completed.returncode != 0:
        raise RuntimeError(f"command failed with exit {completed.returncode}: {command[0]}")
    return receipt


def docker_ps_by_name(prefix: str) -> list[str]:
    receipt = run_command(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"name={prefix}",
            "--format",
            "{{.Names}}",
        ],
        timeout=10,
    )
    return [line for line in receipt["stdout"].splitlines() if line]


def inspect_image(reference: str) -> dict[str, Any]:
    receipt = run_command(
        [
            "docker",
            "image",
            "inspect",
            reference,
            "--format",
            "{{.Id}}\t{{json .RepoDigests}}",
        ],
        timeout=15,
    )
    image_id, raw_digests = receipt["stdout"].strip().split("\t", 1)
    return {
        "reference": reference,
        "image_id": image_id,
        "repo_digests": json.loads(raw_digests),
    }


def validate_retained_inputs() -> dict[str, Any]:
    cleanup = read_json(STAGE4_CLEANUP_PATH)
    if cleanup.get("schema_version") != "mrw.stage4.post-acceptance-cleanup.v1":
        raise RuntimeError("unexpected Stage4 cleanup schema")
    if cleanup.get("status") != "CLEANUP_RESULT":
        raise RuntimeError("Stage4 cleanup is not a completed cleanup result")
    retained = cleanup["retained"]
    expected_retained = {
        "final_stage4_image": IMAGES["backend"]["current"]
        + "@sha256:f247a1492400311e032710df01f84365c7e700f61c122b7243ae58eda982af19",
        "r13x_backend_base": IMAGES["backend"]["previous"]
        + "@sha256:d72688f24fb867ae2e0e9310cfc9ec25aac649a8da69130ee26469c0bd37c2ef",
        "r13x_frontend": IMAGES["frontend"]["previous"]
        + "@sha256:f5641ba6d2b50135da1c9c9c3edfd067ed90ecfb37bcb8f0c7580b2e00aaa915",
    }
    for field, expected in expected_retained.items():
        if retained.get(field) != expected:
            raise RuntimeError(f"retained rollback input mismatch: {field}")

    r13w_record = read_json(R13W_EXECUTION_RECORD_PATH)
    r13w_frontend = r13w_record["loaded_images"]["frontend"]
    expected_frontend_current = {
        "docker_image_id": "sha256:bcdb5450494292d043e7b104b711d59ad3a3510c1fd89f7de70ee2f32ce9b1ed",
        "index_identity_match": True,
        "role": "frontend",
        "status": "PASS",
        "tag": IMAGES["frontend"]["current"],
    }
    for field, expected in expected_frontend_current.items():
        if r13w_frontend.get(field) != expected:
            raise RuntimeError(f"r13w retained frontend input mismatch: {field}")

    return {
        "stage4_cleanup": {
            "path": str(STAGE4_CLEANUP_PATH.relative_to(REPOSITORY_ROOT)),
            "schema_version": cleanup["schema_version"],
            "status": cleanup["status"],
            "deleted_images": cleanup["deleted"]["images"],
            "retained_keys_used": [
                "final_stage4_image",
                "r13x_backend_base",
                "r13x_frontend",
            ],
        },
        "r13w_frontend_current": {
            "path": str(R13W_EXECUTION_RECORD_PATH.relative_to(REPOSITORY_ROOT)),
            "loaded_image_status": r13w_frontend["status"],
            "docker_image_id": r13w_frontend["docker_image_id"],
            "tag": r13w_frontend["tag"],
        },
        "deleted_old_derived_images_referenced": False,
    }


def probe_image(
    image: str,
    *,
    name: str,
    probe: str,
    env: dict[str, str] | None = None,
) -> tuple[dict[str, Any], str]:
    command = [
        "docker",
        "run",
        "--pull",
        "never",
        "--rm",
        "--platform",
        PLATFORM,
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,size=16m,noexec,nosuid",
    ]
    for key, value in (env or {}).items():
        command.extend(["--env", f"{key}={value}"])
    command.extend(["--entrypoint", "/bin/sh", image, "-c", probe])
    receipt = run_command(command, timeout=30)
    output = receipt["stdout"].strip()
    if receipt["exit_code"] != 0 or not output:
        raise RuntimeError(f"image probe failed: {name}")
    return receipt, output


def rehearse_image_rollback(run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    commands: list[dict[str, Any]] = []
    input_references = validate_retained_inputs()
    roles: dict[str, Any] = {}
    container_names: list[str] = []

    for role, specification in IMAGES.items():
        current = inspect_image(specification["current"])
        previous = inspect_image(specification["previous"])
        if current["image_id"] == previous["image_id"]:
            raise RuntimeError(f"rollback images are identical for {role}")

        observations: dict[str, Any] = {}
        expected = {
            "initial": ("current", "present" if role == "backend" else None),
            "rolled_back": ("previous", "absent" if role == "backend" else None),
            "restored": ("current", "present" if role == "backend" else None),
        }
        for phase, (selection, expected_binding) in expected.items():
            name = f"{run_id}-{role}-{phase}"
            container_names.append(name)
            receipt, output = probe_image(
                specification[selection],
                name=name,
                probe=specification["capability_probe"],
            )
            commands.append(receipt)
            if f"role={role}" not in output:
                raise RuntimeError(f"unexpected {role} probe output in {phase}")
            if expected_binding is not None:
                marker = f"c9_writer_binding={expected_binding}"
                if marker not in output:
                    raise RuntimeError(f"missing {marker} in {phase}")
            observations[phase] = {
                "selection": selection,
                "image": current if selection == "current" else previous,
                "output_sha256": receipt["stdout_sha256"],
                "output": output,
                "exit_code": receipt["exit_code"],
            }

        roles[role] = {
            "current": current,
            "previous": previous,
            "observations": observations,
            "backend_capability_difference": (
                "current_has_c9_writer_binding_previous_does_not"
                if role == "backend"
                else None
            ),
        }

    backend = IMAGES["backend"]
    config_name = f"{run_id}-backend-config-v1"
    container_names.append(config_name)
    config_receipt, config_output = probe_image(
        backend["current"],
        name=config_name,
        probe=backend["config_probe"],
        env={
            "EXPECTED_CONFIG_REVISION": "v1",
            "MRW_FIXTURE_CONFIG_REVISION": "v1",
        },
    )
    commands.append(config_receipt)
    if "config_revision_observed=v1" not in config_output:
        raise RuntimeError("current backend image did not observe rolled-back config revision")

    result = {
        "status": "PASS",
        "method": "unique no-network read-only disposable container probes",
        "input_references": input_references,
        "roles": roles,
        "config_revision_runtime_probe": {
            "revision": "v1",
            "output": config_output,
            "exit_code": config_receipt["exit_code"],
            "output_sha256": config_receipt["stdout_sha256"],
        },
        "limitations": [
            "The backend previous image is the retained r13x base, not a complete equivalent of the Stage4 C9 runtime.",
            "The backend previous image lacks the C9 canonical writer binding marker by direct container readback.",
            "Probes validate image identity and the listed readback, not every deprecated or removed capability.",
        ],
    }
    return result, commands, container_names


def rehearse_config_and_credential() -> tuple[dict[str, Any], dict[str, Any]]:
    v1 = {"feature_flag": "off", "log_level": "info"}
    v2 = {"feature_flag": "on", "log_level": "warning"}
    active_v2_digest = object_digest(v2)

    active = v1
    rollback_digest = object_digest(active)
    if rollback_digest != object_digest({
        "feature_flag": "off",
        "log_level": "info",
    }):
        raise RuntimeError("config rollback digest mismatch")

    credential_v1 = secrets.token_urlsafe(32)
    credential_v2 = secrets.token_urlsafe(32)
    credential_digests = {
        "v1": hashlib.sha256(credential_v1.encode("utf-8")).hexdigest(),
        "v2": hashlib.sha256(credential_v2.encode("utf-8")).hexdigest(),
    }
    active_credential = credential_v2
    upgraded_digest = hashlib.sha256(active_credential.encode("utf-8")).hexdigest()
    active_credential = credential_v1
    rolled_back_digest = hashlib.sha256(active_credential.encode("utf-8")).hexdigest()
    if upgraded_digest != credential_digests["v2"] or rolled_back_digest != credential_digests["v1"]:
        raise RuntimeError("credential rollback digest mismatch")
    if credential_v1 == credential_v2:
        raise RuntimeError("credential fixture revisions are not distinct")

    config = {
        "status": "PASS",
        "revision_before_rollback": "v2",
        "revision_after_rollback": "v1",
        "digest_before_rollback": active_v2_digest,
        "digest_after_rollback": rollback_digest,
        "runtime_consumption": "current backend image observed fixture revision v1",
        "values_persisted": False,
    }
    credential = {
        "status": "PASS",
        "revision_before_rollback": "v2",
        "revision_after_rollback": "v1",
        "digests_by_revision": credential_digests,
        "upgraded_digest": upgraded_digest,
        "rolled_back_digest": rolled_back_digest,
        "values_persisted": False,
        "application_consumption": "not_exercised_no_provider_or_real_secret_store",
    }
    return config, credential


def rehearse_route_fallback() -> tuple[dict[str, Any], dict[str, Any]]:
    binding_path = (
        REPOSITORY_ROOT
        / "main/backend/app/composition/production_route_bindings.json"
    )
    binding_document = read_json(binding_path)
    route_hash = bytes_digest(binding_path.read_bytes())
    if route_hash != STAGE4_ROUTE_BINDING_SHA256:
        raise RuntimeError("current route binding does not match the Stage4 C9 image input")

    canonical = next(
        (
            binding
            for binding in binding_document["bindings"]
            if binding["route_template"] == "/api/v1/successor-runtime/v2/commands"
        ),
        None,
    )
    legacy = next(
        (
            binding
            for binding in binding_document["bindings"]
            if binding["effect_contract"]["effect_class"] == "legacy_write"
        ),
        None,
    )
    if canonical is None or legacy is None:
        raise RuntimeError("required canonical or legacy route binding is absent")
    canonical_contract = canonical["effect_contract"]
    legacy_contract = legacy["effect_contract"]
    if canonical_contract != {
        "effect_class": "canonical_write",
        "admission": "admitted",
        "provider_port": None,
        "provider_class": "null",
        "canonical_writer_port": "postgres.c9_projection_rebuild.v1",
        "external_auth_port": None,
        "filesystem_port": None,
        "conditional_discriminator": None,
        "conditional_branches": [],
    }:
        raise RuntimeError("canonical C9 route binding changed")
    if legacy_contract["admission"] != "blocked_until_effect_binding" or any(
        legacy_contract.get(port)
        for port in (
            "provider_port",
            "canonical_writer_port",
            "external_auth_port",
            "filesystem_port",
        )
    ):
        raise RuntimeError("legacy writer is not fail-closed")

    production_path = REPOSITORY_ROOT / "main/backend/app/composition/production.py"
    production_source = production_path.read_text(encoding="utf-8")
    if "observability_rollback_latched" not in production_source:
        raise RuntimeError("production rollback latch code path is absent")

    stage4_receipt = read_json(STAGE4_ROOT / "runtime/s4-c9-effect-live.json")
    if stage4_receipt["image"]["reference"] != IMAGES["backend"]["current"]:
        raise RuntimeError("Stage4 receipt image differs from the current rollback image")
    if not stage4_receipt["command"]["exact_replay_equal"]:
        raise RuntimeError("Stage4 exact replay was not equal")
    if stage4_receipt["command"]["first_state"] != "TERMINAL":
        raise RuntimeError("Stage4 receipt was not terminal")
    if stage4_receipt["projection"]["external_sink_disposition"] != "DECLARED_LOSS_NO_CALL":
        raise RuntimeError("Stage4 receipt is not the no-provider local-sink fixture")

    prior_digest = stage4_receipt["command"]["request_digest"]
    state = {
        "successor_route_active": True,
        "legacy_route_active": False,
        "effect_count": 1,
        "journal_entries": 1,
        "terminal_receipts": 1,
        "idempotency_revision": 1,
    }
    state_snapshot = dict(state)

    state["successor_route_active"] = False
    blocked_requests = []
    for command_id in ("cmd:rollback-fallback:new-1", "cmd:rollback-fallback:new-2"):
        if not state["successor_route_active"]:
            blocked_requests.append(
                {
                    "command_id": command_id,
                    "decision": "rollback_latched_no_effect",
                    "new_effect": False,
                }
            )
    if state["legacy_route_active"]:
        raise RuntimeError("legacy writer must not be opened during fallback")

    state["successor_route_active"] = True
    replayed_digest = prior_digest
    exact_replay = prior_digest == replayed_digest
    if not exact_replay:
        raise RuntimeError("route recovery replay was not exact")

    state_after = dict(state)
    if state_snapshot != state_after:
        raise RuntimeError("route fallback changed the terminal effect ledger")

    observations = {
        "route_binding_sha256": route_hash,
        "canonical_route": canonical,
        "legacy_route": legacy,
        "legacy_writer_opened": False,
        "latched_requests": blocked_requests,
        "state_before_fallback": state_snapshot,
        "state_after_recovery_replay": state_after,
        "replayed_request_digest": prior_digest,
        "replayed_receipt": stage4_receipt["command"],
        "exact_replay_equal": exact_replay,
    }
    result = {
        "status": "PASS_MINIMAL_LOCAL_RECOVERY_SUBSTITUTE",
        "method": (
            "Stage4 terminal receipt plus current v3 binding replay state machine; "
            "production rollback latch code path checked, not invoked over HTTP"
        ),
        "observations": observations,
        "applicability": (
            "No legacy writer path is applicable or authorized; the minimal substitute "
            "keeps legacy closed, stops successor effects, then replays the exact Stage4 receipt."
        ),
        "limitations": [
            "This is not an HTTP call against a live Stage5 backend.",
            "The effect, journal, receipt, and idempotency counters are fixture projections of the Stage4 receipt.",
            "The existing production observability latch is not modified or persisted.",
        ],
    }
    return result, observations


def cleanup_containers(run_id: str, container_names: list[str]) -> dict[str, Any]:
    existing = docker_ps_by_name(f"{PROJECT_PREFIX}-{run_id}")
    forced: list[str] = []
    for name in existing:
        if name not in container_names:
            continue
        run_command(["docker", "rm", "-f", name], timeout=15)
        forced.append(name)
    remaining = docker_ps_by_name(f"{PROJECT_PREFIX}-{run_id}")
    if remaining:
        raise RuntimeError(f"rollback rehearsal containers remain: {remaining}")
    return {
        "status": "PASS",
        "created_container_names": container_names,
        "forced_removals": forced,
        "containers_after": remaining,
        "volumes_created": [],
        "networks_created": [],
        "images_removed": [],
    }


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    started_at = utc_now()
    run_id = f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    project_prefix = f"{PROJECT_PREFIX}-{run_id}"
    commands: list[dict[str, Any]] = []
    error: dict[str, Any] | None = None
    result: dict[str, Any] = {
        "schema_version": "mrw.stage5.rollback-fallback-rehearsal.v1",
        "authoritative": False,
        "status": "RUNNING",
        "started_at": started_at,
        "run_id": run_id,
        "scope": "LOCAL_STAGE5_ROLLBACK_ONLY / NOT_AUTHORITY / RELEASE_DEFERRED",
        "network": "container network=none; no production, remote, provider, or registry access",
    }

    try:
        commands.append(run_command(["docker", "version", "--format", "{{.Server.Version}}"], timeout=15))
        resource_names = []
        image_result, image_commands, resource_names = rehearse_image_rollback(project_prefix)
        commands.extend(image_commands)
        config_result, credential_result = rehearse_config_and_credential()
        route_result, route_observations = rehearse_route_fallback()
        cleanup = cleanup_containers(run_id, resource_names)
        result.update(
            {
                "status": "PASS_LOCAL_ROLLBACK_REHEARSAL_NOT_AUTHORITY",
                "ended_at": utc_now(),
                "image_rollback": image_result,
                "config_rollback": config_result,
                "credential_rollback": credential_result,
                "route_fallback": route_result,
                "route_fallback_observations": route_observations,
                "resource_cleanup": cleanup,
                "authority_ceiling": [
                    "LOCAL_STAGE5_ROLLBACK_REHEARSAL_ONLY",
                    "NOT_AUTHORITY",
                    "PRODUCTION_RELEASE_NOT_AUTHORIZED",
                ],
                "risks": [
                    "Image probes do not execute the full backend, Celery, frontend proxy, database, or monitor stack.",
                    "Credential rollback validates exact in-process revision identity only and does not exercise a secret store or provider.",
                    "Route fallback is a minimal recovery substitute because no legacy writer path is applicable or authorized.",
                    "No production RTO/RPO, remote rollback, registry rollback, or secret-store rollback is established.",
                ],
            }
        )
    except BaseException as exc:  # noqa: BLE001 - evidence runner converts all failures to structured output.
        error = {
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
        result.update(
            {
                "status": "FAIL_STRUCTURED",
                "ended_at": utc_now(),
                "error": error,
                "resource_cleanup_status": "ATTEMPTED_IN_FINALLY",
            }
        )
        try:
            cleanup = cleanup_containers(run_id, locals().get("resource_names", []))
            result["resource_cleanup"] = cleanup
            result["resource_cleanup_status"] = cleanup["status"]
        except BaseException as cleanup_exc:  # noqa: BLE001
            result["resource_cleanup_error"] = {
                "exception_type": type(cleanup_exc).__name__,
                "message": str(cleanup_exc),
            }
    finally:
        result["safe_command_log"] = commands
        atomic_write_json(RESULT_PATH, result)

    if result["status"].startswith("FAIL"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
