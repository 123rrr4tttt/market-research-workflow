from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.check_source_library_public_replay_a5_gate import build_check as build_a5_gate_check
from scripts.source_library_replay_scaleout import DEFAULT_HISTORICAL_TARGETS
from scripts.source_library_replay_scaleout import validate_manifest_targets


CONTRACT_VERSION = "crawler_source_expansion.public_replay_gate.v1"
MANIFEST_CONTRACT_VERSION = "crawler_source_expansion.public_replay_gate_manifest.v1"
DEFAULT_MANIFEST_PATH = Path(
    "development/latest-dev-docs/automation-runs/"
    "crawler-public-replay-gate/2026-05-22/manifest.json"
)

EXPECTED_COUNTS = {
    "historical_target_count": 45,
    "enabled_public_target_count": 40,
    "policy_disabled_target_count": 5,
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_path(root: Path, path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else root / path


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _load_json(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    if not path.is_file():
        errors.append(f"missing {label}: {_relative_path(path, _repo_root())}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"invalid {label}: {_relative_path(path, _repo_root())}: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"{label} must be a JSON object: {_relative_path(path, _repo_root())}")
        return {}
    return payload


def _require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def _status_counts(payload: dict[str, Any]) -> dict[str, int]:
    raw_counts = ((payload.get("outputs") or {}).get("status_counts") or {})
    if not isinstance(raw_counts, dict):
        return {}
    counts: dict[str, int] = {}
    for key, value in raw_counts.items():
        try:
            counts[str(key)] = int(value)
        except (TypeError, ValueError):
            counts[str(key)] = 0
    return counts


def _target_ids_from_targets(raw_targets: Any) -> set[str]:
    if not isinstance(raw_targets, list):
        return set()
    return {
        str(target.get("target_id") or "").strip()
        for target in raw_targets
        if isinstance(target, dict) and str(target.get("target_id") or "").strip()
    }


def _expected_target_ids() -> set[str]:
    return {
        str(target.get("target_id") or "").strip()
        for target in DEFAULT_HISTORICAL_TARGETS
        if str(target.get("target_id") or "").strip()
    }


def _validate_expected_counts(counts: dict[str, Any], errors: list[str], label: str) -> dict[str, int]:
    resolved = {
        "historical_target_count": int(counts.get("historical_target_count") or 0),
        "enabled_public_target_count": int(counts.get("enabled_public_target_count") or 0),
        "policy_disabled_target_count": int(counts.get("policy_disabled_target_count") or 0),
    }
    for key, expected in EXPECTED_COUNTS.items():
        _require(resolved[key] == expected, errors, f"{label}.{key} must be {expected}")
    return resolved


def _manifest_summary(manifest: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    _require(
        manifest.get("contract_version") == MANIFEST_CONTRACT_VERSION,
        errors,
        f"manifest contract_version must be {MANIFEST_CONTRACT_VERSION}",
    )
    required_artifacts = manifest.get("required_artifacts")
    _require(isinstance(required_artifacts, dict), errors, "manifest.required_artifacts must be an object")
    expected_counts = _validate_expected_counts(
        manifest.get("expected_counts") if isinstance(manifest.get("expected_counts"), dict) else {},
        errors,
        "manifest.expected_counts",
    )
    closure_policy = manifest.get("closure_policy") if isinstance(manifest.get("closure_policy"), dict) else {}
    _require(
        closure_policy.get("live_public_replay_default_status") == "not_closed_missing_real_evidence",
        errors,
        "manifest must default live public replay to not_closed_missing_real_evidence",
    )
    return {
        "contract_version": str(manifest.get("contract_version") or ""),
        "expected_counts": expected_counts,
        "required_artifact_keys": (
            sorted((required_artifacts or {}).keys()) if isinstance(required_artifacts, dict) else []
        ),
        "live_public_replay_default_status": str(closure_policy.get("live_public_replay_default_status") or ""),
    }


def _artifact_paths(root: Path, manifest: dict[str, Any], errors: list[str]) -> dict[str, Path]:
    required = manifest.get("required_artifacts")
    if not isinstance(required, dict):
        return {}
    required_keys = {
        "source_replay_manifest",
        "deterministic_replay_output",
        "stored_a5_gate_output",
        "stored_closure_output",
        "live_public_output",
    }
    paths: dict[str, Path] = {}
    for key in sorted(required_keys):
        value = required.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"manifest.required_artifacts.{key} must be a path string")
            continue
        paths[key] = _resolve_path(root, value)
    return paths


def _source_replay_manifest_summary(payload: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    targets = payload.get("targets")
    if not isinstance(targets, list):
        errors.append("source replay manifest must contain targets list")
        targets = []
    artifact_ids = _target_ids_from_targets(targets)
    expected_ids = _expected_target_ids()
    enabled_count = sum(1 for target in targets if isinstance(target, dict) and bool(target.get("enabled", True)))
    policy_disabled_count = sum(
        1 for target in targets if isinstance(target, dict) and bool(target.get("skip_public_execution"))
    )
    validation = validate_manifest_targets([dict(target) for target in targets if isinstance(target, dict)])

    _require(bool(validation.get("passed")), errors, "source replay manifest target validation must pass")
    _require(len(targets) == 45, errors, "source replay manifest must contain 45 historical targets")
    _require(artifact_ids == expected_ids, errors, "source replay manifest target_id set must match embedded snapshot")
    _require(enabled_count == 40, errors, "source replay manifest must contain 40 enabled public targets")
    _require(policy_disabled_count == 5, errors, "source replay manifest must contain 5 policy-disabled targets")

    return {
        "target_count": len(targets),
        "enabled_public_target_count": enabled_count,
        "policy_disabled_target_count": policy_disabled_count,
        "target_ids_match_embedded_snapshot": artifact_ids == expected_ids,
        "validation_passed": bool(validation.get("passed")),
    }


def _deterministic_replay_summary(payload: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    manifest_validation = (
        inputs.get("manifest_validation") if isinstance(inputs.get("manifest_validation"), dict) else {}
    )
    counts = _status_counts(payload)

    _require(bool(validation.get("passed")), errors, "deterministic replay output validation.passed must be true")
    _require(bool(validation.get("skipped")), errors, "deterministic replay output must stay skipped")
    _require(
        bool(validation.get("full_historical_manifest")),
        errors,
        "deterministic replay output must cover the full manifest",
    )
    _require(
        not bool((payload.get("mode") or {}).get("allow_public_network")),
        errors,
        "deterministic replay must not allow public network",
    )
    _require(int(inputs.get("target_count") or 0) == 45, errors, "deterministic replay output must record 45 targets")
    _require(
        int(manifest_validation.get("enabled_target_count") or 0) == 40,
        errors,
        "deterministic replay output must record 40 enabled targets",
    )
    _require(
        int(manifest_validation.get("policy_skipped_target_count") or 0) == 5,
        errors,
        "deterministic replay output must record 5 policy-disabled targets",
    )
    _require(
        counts == {"skipped_public_network_disabled": 45},
        errors,
        "deterministic replay output must skip all 45 targets",
    )
    _require(
        int(outputs.get("public_targets_attempted") or 0) == 0,
        errors,
        "deterministic replay must attempt 0 public targets",
    )

    return {
        "validation_passed": bool(validation.get("passed")),
        "skipped": bool(validation.get("skipped")),
        "full_historical_manifest": bool(validation.get("full_historical_manifest")),
        "allow_public_network": bool((payload.get("mode") or {}).get("allow_public_network")),
        "status_counts": counts,
        "public_targets_attempted": int(outputs.get("public_targets_attempted") or 0),
    }


def _stored_a5_gate_summary(payload: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    external_blocker = payload.get("external_blocker") if isinstance(payload.get("external_blocker"), dict) else {}
    a5_gate = payload.get("a5_gate") if isinstance(payload.get("a5_gate"), dict) else {}
    embedded_manifest = a5_gate.get("embedded_manifest") if isinstance(a5_gate.get("embedded_manifest"), dict) else {}

    _require(
        payload.get("contract_version") == "source_library.public_replay_a5_gate.v1",
        errors,
        "stored A5 gate contract version mismatch",
    )
    _require(bool(validation.get("passed")), errors, "stored A5 gate validation must pass")
    _require(
        not bool(validation.get("public_network_attempted")),
        errors,
        "stored A5 gate must not attempt public network",
    )
    _require(
        payload.get("a5_status") == "deterministic_replay_gate_closed_external_public_replay_blocked",
        errors,
        "stored A5 gate must preserve external public replay blocker status",
    )
    _require(
        external_blocker.get("blocker_type") == "external_public_network_or_site_stability",
        errors,
        "stored A5 gate must record external_public_network_or_site_stability",
    )
    _require(
        int(embedded_manifest.get("target_count") or 0) == 45,
        errors,
        "stored A5 gate must record 45 embedded targets",
    )

    return {
        "validation_passed": bool(validation.get("passed")),
        "a5_status": str(payload.get("a5_status") or ""),
        "public_network_attempted": bool(validation.get("public_network_attempted")),
        "external_blocker_type": str(external_blocker.get("blocker_type") or ""),
        "target_count": int(embedded_manifest.get("target_count") or 0),
    }


def _fresh_a5_gate_summary(payload: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    external_blocker = payload.get("external_blocker") if isinstance(payload.get("external_blocker"), dict) else {}
    _require(bool(validation.get("passed")), errors, "fresh A5 gate validation must pass")
    _require(
        not bool(validation.get("public_network_attempted")),
        errors,
        "fresh A5 gate must not attempt public network",
    )
    return {
        "validation_passed": bool(validation.get("passed")),
        "a5_status": str(payload.get("a5_status") or ""),
        "public_network_attempted": bool(validation.get("public_network_attempted")),
        "external_blocker_status": str(external_blocker.get("status") or ""),
        "external_blocker_type": external_blocker.get("blocker_type"),
    }


def _closure_summary(payload: dict[str, Any], errors: list[str], label: str) -> dict[str, Any]:
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
    task_statuses = {
        str(task.get("task_id") or ""): str(task.get("status") or "")
        for task in tasks
        if isinstance(task, dict)
    }
    _require(bool(validation.get("passed")), errors, f"{label} closure validation must pass")
    _require(
        payload.get("overall_status") == "external_blocked",
        errors,
        f"{label} closure must remain external_blocked",
    )
    _require(task_statuses.get("A5") == "blocked_external", errors, f"{label} closure must keep A5 blocked_external")
    return {
        "validation_passed": bool(validation.get("passed")),
        "overall_status": str(payload.get("overall_status") or ""),
        "a5_status": task_statuses.get("A5", ""),
        "task_statuses": task_statuses,
    }


def _public_target_summary(payload: dict[str, Any]) -> dict[str, int]:
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    target_results = outputs.get("target_results") if isinstance(outputs.get("target_results"), list) else []
    status_counts = _status_counts(payload)
    return {
        "target_result_count": len(target_results),
        "public_targets_attempted": int(outputs.get("public_targets_attempted") or 0),
        "policy_skipped_status_count": int(status_counts.get("skipped_policy_disabled_platform_entry") or 0),
        "operator_gate_skip_count": int(status_counts.get("skipped_public_network_disabled") or 0),
    }


def _live_public_replay_summary(path: Path, errors: list[str]) -> dict[str, Any]:
    if not path.is_file():
        return {
            "status": "not_closed_missing_real_evidence",
            "closure_claim": "not_closed",
            "evidence_present": False,
            "path": str(path),
            "required_future_artifact": (
                "Store output.public.json from an opt-in 45-site public replay before revisiting closure."
            ),
        }

    payload = _load_json(path, errors, "live public replay output")
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    manifest_validation = (
        inputs.get("manifest_validation") if isinstance(inputs.get("manifest_validation"), dict) else {}
    )
    mode = payload.get("mode") if isinstance(payload.get("mode"), dict) else {}
    target_summary = _public_target_summary(payload)
    status_counts = _status_counts(payload)
    before_error_count = len(errors)

    _require(
        bool(mode.get("allow_public_network")),
        errors,
        "live public replay evidence must record allow_public_network=true",
    )
    _require(bool(validation.get("passed")), errors, "live public replay evidence validation.passed must be true")
    _require(not bool(validation.get("skipped")), errors, "live public replay evidence must not be skipped")
    _require(
        bool(validation.get("full_historical_manifest")),
        errors,
        "live public replay evidence must cover the full historical manifest",
    )
    _require(int(inputs.get("target_count") or 0) == 45, errors, "live public replay evidence must record 45 targets")
    _require(
        int(manifest_validation.get("enabled_target_count") or 0) == 40,
        errors,
        "live public replay evidence must record 40 enabled targets",
    )
    _require(
        int(manifest_validation.get("policy_skipped_target_count") or 0) == 5,
        errors,
        "live public replay evidence must record 5 policy-disabled targets",
    )
    _require(
        target_summary["target_result_count"] == 45,
        errors,
        "live public replay evidence must include 45 target results",
    )
    _require(
        target_summary["public_targets_attempted"] == 40,
        errors,
        "live public replay evidence must attempt 40 enabled targets",
    )
    _require(
        target_summary["policy_skipped_status_count"] == 5,
        errors,
        "live public replay evidence must keep 5 platform/API entries policy-skipped",
    )
    _require(
        target_summary["operator_gate_skip_count"] == 0,
        errors,
        "live public replay evidence must not contain operator-gate public-network skips",
    )

    valid_public_artifact = len(errors) == before_error_count
    return {
        "status": (
            "real_evidence_present_review_required" if valid_public_artifact else "invalid_public_replay_evidence"
        ),
        "closure_claim": "review_required" if valid_public_artifact else "not_closed",
        "evidence_present": True,
        "path": str(path),
        "allow_public_network": bool(mode.get("allow_public_network")),
        "validation_passed": bool(validation.get("passed")),
        "live_evidence_sufficient": bool(validation.get("live_evidence_sufficient")),
        "status_counts": status_counts,
        **target_summary,
    }


def build_check(
    repo_root: Path | str | None = None,
    manifest_path: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    manifest_file = _resolve_path(root, manifest_path or DEFAULT_MANIFEST_PATH)
    errors: list[str] = []

    embedded_validation = validate_manifest_targets([dict(target) for target in DEFAULT_HISTORICAL_TARGETS])
    _require(bool(embedded_validation.get("passed")), errors, "embedded 45-site target snapshot must validate")

    manifest = _load_json(manifest_file, errors, "crawler public replay gate manifest")
    manifest_info = _manifest_summary(manifest, errors) if manifest else {}
    paths = _artifact_paths(root, manifest, errors) if manifest else {}

    source_manifest = (
        _load_json(paths["source_replay_manifest"], errors, "source replay manifest")
        if "source_replay_manifest" in paths
        else {}
    )
    deterministic_output = (
        _load_json(paths["deterministic_replay_output"], errors, "deterministic replay output")
        if "deterministic_replay_output" in paths
        else {}
    )
    stored_a5_output = (
        _load_json(paths["stored_a5_gate_output"], errors, "stored A5 gate output")
        if "stored_a5_gate_output" in paths
        else {}
    )
    stored_closure_output = (
        _load_json(paths["stored_closure_output"], errors, "stored crawler closure output")
        if "stored_closure_output" in paths
        else {}
    )

    source_manifest_summary = _source_replay_manifest_summary(source_manifest, errors) if source_manifest else {}
    deterministic_summary = _deterministic_replay_summary(deterministic_output, errors) if deterministic_output else {}
    stored_a5_summary = _stored_a5_gate_summary(stored_a5_output, errors) if stored_a5_output else {}
    stored_closure_summary = _closure_summary(stored_closure_output, errors, "stored") if stored_closure_output else {}

    fresh_a5 = build_a5_gate_check(root)
    fresh_a5_summary = _fresh_a5_gate_summary(fresh_a5, errors)

    live_public_output_path = paths.get("live_public_output", root / "missing-output.public.json")
    live_public_replay = _live_public_replay_summary(live_public_output_path, errors)

    public_closed = live_public_replay.get("status") == "real_evidence_present_review_required"
    overall_status = (
        "deterministic_artifacts_valid_live_public_replay_evidence_present_review_required"
        if public_closed
        else "deterministic_artifacts_valid_live_public_replay_not_closed"
    )

    result = {
        "contract_version": CONTRACT_VERSION,
        "repo_root": str(root),
        "manifest_path": _relative_path(manifest_file, root),
        "manifest": manifest_info,
        "deterministic_artifacts": {
            "embedded_manifest": embedded_validation,
            "source_replay_manifest": source_manifest_summary,
            "deterministic_replay_output": deterministic_summary,
            "stored_a5_gate_output": stored_a5_summary,
            "fresh_a5_gate_check": fresh_a5_summary,
            "stored_closure_output": stored_closure_summary,
        },
        "live_public_replay": live_public_replay,
        "overall_status": overall_status,
        "validation": {
            "passed": not errors,
            "errors": errors,
            "public_network_attempted": False,
            "shared_indexes_edited": False,
        },
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check crawler public replay gate artifacts without public network access."
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build_check(repo_root=args.repo_root, manifest_path=args.manifest)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
