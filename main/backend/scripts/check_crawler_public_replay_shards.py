from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.check_crawler_public_replay_gate import build_check as build_public_gate_check
from scripts.check_llm_crawler_replay_fixture import build_check as build_browser_fixture_check
from scripts.source_library_replay_scaleout import DEFAULT_HISTORICAL_TARGETS
from scripts.source_library_replay_scaleout import validate_manifest_targets


CONTRACT_VERSION = "crawler_source_expansion.public_replay_shards.check.v1"
MANIFEST_CONTRACT_VERSION = "crawler_source_expansion.public_replay_shards_manifest.v1"
READBACK_CONTRACT_VERSION = "crawler_source_expansion.public_replay_shards_readback.v1"
SHARD_OUTPUT_CONTRACT_VERSION = "crawler_source_expansion.public_replay_shard_output.v1"

DEFAULT_MANIFEST_PATH = Path(
    "development/latest-dev-docs/automation-runs/"
    "crawler-public-replay-shards/2026-05-22/shard_manifest.json"
)
DEFAULT_READBACK_PATH = Path(
    "development/latest-dev-docs/automation-runs/"
    "crawler-public-replay-shards/2026-05-22/shard_readback.json"
)

CRAWLER_TOPIC_DOC = Path(
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
    "2026-03-07-crawler-source-expansion/2026-05-22-wave19-public-replay-shards.md"
)
LLM_TOPIC_DOC = Path(
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
    "2026-03-08-llm-crawler-unified-frontdoor/09_wave19-public-replay-shards-readback-2026-05-22.md"
)

EXPECTED_COUNTS = {
    "historical_target_count": 45,
    "enabled_public_target_count": 40,
    "policy_disabled_target_count": 5,
}
REQUIRED_ARTIFACT_KEYS = {
    "source_replay_manifest",
    "crawler_public_replay_gate_manifest",
    "llm_high_js_replay_manifest",
    "llm_browser_replay_fixture",
    "shard_readback",
}
OPTIONAL_ARTIFACT_KEYS: set[str] = set()
MISSING_OUTPUT_RUNTIME_FLAGS = {
    "repo_local_fixture": True,
    "deterministic": True,
    "public_network_attempted": False,
    "browser_runtime_started": False,
    "public_browser_replay_performed": False,
    "real_public_replay_claimed": False,
}
PUBLIC_OUTPUT_RUNTIME_FLAGS = {
    "repo_local_fixture": False,
    "deterministic": False,
    "public_network_attempted": True,
    "browser_runtime_started": False,
    "public_browser_replay_performed": False,
    "real_public_replay_claimed": True,
}
MISSING_OUTPUT_READBACK_SCOPE = "crawler_public_replay_shards_missing_output_readback"
PUBLIC_OUTPUT_READBACK_SCOPE = "crawler_public_replay_shards_public_output_readback"
MISSING_OUTPUT_RUNTIME_MODE = "repo_local_public_replay_shard_readback"
PUBLIC_OUTPUT_RUNTIME_MODE = "public_replay_shard_output_readback"
PUBLIC_OUTPUT_STATUS = "real_evidence_present_review_required"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _load_json_file(path: Path, errors: list[str], label: str) -> dict[str, Any]:
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


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _expected_targets() -> list[dict[str, Any]]:
    return [dict(target) for target in DEFAULT_HISTORICAL_TARGETS]


def _expected_target_ids() -> list[str]:
    return [str(target["target_id"]) for target in _expected_targets()]


def _chunks(values: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _target_counts(targets: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "target_count": len(targets),
        "enabled_public_target_count": sum(1 for target in targets if bool(target.get("enabled", True))),
        "policy_disabled_target_count": sum(1 for target in targets if bool(target.get("skip_public_execution"))),
    }


def _target_id_from_result(row: Mapping[str, Any]) -> str:
    target = row.get("target") if isinstance(row.get("target"), Mapping) else {}
    return str(target.get("target_id") or row.get("target_id") or "").strip()


def _classification_status(row: Mapping[str, Any]) -> str:
    classification = row.get("classification") if isinstance(row.get("classification"), Mapping) else {}
    return str(classification.get("status") or row.get("status") or "").strip()


def _status_counts_from_results(results: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in results:
        status = _classification_status(row) or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _status_counts_from_payload(payload: Mapping[str, Any]) -> dict[str, int]:
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), Mapping) else {}
    raw_counts = outputs.get("status_counts") if isinstance(outputs.get("status_counts"), Mapping) else {}
    counts: dict[str, int] = {}
    for key, value in raw_counts.items():
        try:
            counts[str(key)] = int(value)
        except (TypeError, ValueError):
            counts[str(key)] = 0
    return counts


def _target_results_from_payload(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), Mapping) else {}
    raw_results = outputs.get("target_results")
    return [row for row in raw_results if isinstance(row, Mapping)] if isinstance(raw_results, list) else []


def _public_attempted_count(results: list[Mapping[str, Any]]) -> int:
    return sum(1 for row in results if not _classification_status(row).startswith("skipped_"))


def _validate_expected_counts(raw_counts: Any, errors: list[str], label: str) -> dict[str, int]:
    counts = raw_counts if isinstance(raw_counts, Mapping) else {}
    resolved = {
        "historical_target_count": int(counts.get("historical_target_count") or 0),
        "enabled_public_target_count": int(counts.get("enabled_public_target_count") or 0),
        "policy_disabled_target_count": int(counts.get("policy_disabled_target_count") or 0),
    }
    for key, expected in EXPECTED_COUNTS.items():
        _require(resolved[key] == expected, errors, f"{label}.{key} must be {expected}")
    return resolved


def _artifact_paths(
    root: Path,
    manifest_path: Path,
    manifest: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Path]:
    artifacts = manifest.get("required_artifacts") if isinstance(manifest.get("required_artifacts"), Mapping) else {}
    _require(isinstance(manifest.get("required_artifacts"), Mapping), errors, "manifest.required_artifacts must be an object")
    keys = set(artifacts)
    missing = sorted(REQUIRED_ARTIFACT_KEYS - keys)
    extra = sorted(keys - REQUIRED_ARTIFACT_KEYS - OPTIONAL_ARTIFACT_KEYS)
    _require(not missing, errors, f"manifest.required_artifacts missing keys: {missing}")
    _require(not extra, errors, f"manifest.required_artifacts has unexpected keys: {extra}")

    paths: dict[str, Path] = {}
    for key in sorted(REQUIRED_ARTIFACT_KEYS | OPTIONAL_ARTIFACT_KEYS):
        value = artifacts.get(key)
        if not isinstance(value, str) or not value.strip():
            if key in REQUIRED_ARTIFACT_KEYS:
                errors.append(f"manifest.required_artifacts.{key} must be a path string")
            continue
        resolved = _resolve_path(root, value).resolve()
        paths[key] = resolved
        if key not in OPTIONAL_ARTIFACT_KEYS:
            _require(
                resolved.is_file(),
                errors,
                f"manifest.required_artifacts.{key} does not exist: {_relative_path(resolved, root)}",
            )

    _require(manifest_path.is_file(), errors, "manifest path must be readable")
    return paths


def _source_manifest_summary(source_manifest: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    raw_targets = source_manifest.get("targets")
    targets = [dict(target) for target in raw_targets] if isinstance(raw_targets, list) else []
    validation = validate_manifest_targets(targets)
    target_ids = [str(target.get("target_id") or "").strip() for target in targets]
    expected_ids = _expected_target_ids()
    counts = _target_counts(targets)

    _require(isinstance(raw_targets, list), errors, "source replay manifest must contain targets list")
    _require(bool(validation.get("passed")), errors, "source replay manifest target validation must pass")
    _require(target_ids == expected_ids, errors, "source replay manifest target order must match embedded 45-site snapshot")
    _require(counts["target_count"] == 45, errors, "source replay manifest must contain 45 targets")
    _require(counts["enabled_public_target_count"] == 40, errors, "source replay manifest must contain 40 enabled targets")
    _require(counts["policy_disabled_target_count"] == 5, errors, "source replay manifest must contain 5 policy-disabled targets")

    return {
        **counts,
        "validation_passed": bool(validation.get("passed")),
        "target_order_matches_embedded_snapshot": target_ids == expected_ids,
        "target_ids": target_ids,
    }


def _expected_shards(shard_size: int) -> list[dict[str, Any]]:
    expected_targets = _expected_targets()
    shards: list[dict[str, Any]] = []
    for index, chunk in enumerate(_chunks(expected_targets, shard_size), start=1):
        counts = _target_counts(chunk)
        shards.append(
            {
                "shard_id": f"crawler_public_replay_shard_{index:02d}",
                "shard_index": index,
                **counts,
                "target_ids": [str(target["target_id"]) for target in chunk],
            }
        )
    return shards


def _shard_policy_summary(manifest: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    policy = manifest.get("shard_policy") if isinstance(manifest.get("shard_policy"), Mapping) else {}
    expected = {
        "strategy": "source_manifest_order_chunks",
        "preserve_source_manifest_order": True,
        "shard_count": 5,
        "shard_size": 9,
        "public_output_contract_version": SHARD_OUTPUT_CONTRACT_VERSION,
        "missing_public_output_status": "external_blocked",
        "closure_without_all_shard_outputs_allowed": False,
        "browser_replay_fixture_required": True,
    }
    _require(isinstance(manifest.get("shard_policy"), Mapping), errors, "manifest.shard_policy must be an object")
    for key, value in expected.items():
        _require(policy.get(key) == value, errors, f"manifest.shard_policy.{key} must be {value!r}")
    return {key: policy.get(key) for key in expected}


def _manifest_shard_summary(root: Path, manifest: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    raw_shards = manifest.get("shards")
    shards = raw_shards if isinstance(raw_shards, list) else []
    policy = manifest.get("shard_policy") if isinstance(manifest.get("shard_policy"), Mapping) else {}
    shard_size = int(policy.get("shard_size") or 0)
    expected_shards = _expected_shards(shard_size if shard_size else 9)
    expected_by_id = {shard["shard_id"]: shard for shard in expected_shards}
    seen_shard_ids: set[str] = set()
    seen_targets: list[str] = []
    output_paths: list[str] = []
    shard_summaries: list[dict[str, Any]] = []

    _require(isinstance(raw_shards, list), errors, "manifest.shards must be a list")
    _require(len(shards) == len(expected_shards), errors, "manifest.shards must contain 5 shards")

    for raw_shard in shards:
        shard = raw_shard if isinstance(raw_shard, Mapping) else {}
        shard_id = str(shard.get("shard_id") or "").strip()
        seen_shard_ids.add(shard_id)
        expected = expected_by_id.get(shard_id)
        if expected is None:
            errors.append(f"unexpected shard_id in manifest: {shard_id!r}")
            continue

        target_ids = _as_string_list(shard.get("target_ids"))
        seen_targets.extend(target_ids)
        public_output = str(shard.get("public_output") or "").strip()
        resolved_public_output = _resolve_path(root, public_output).resolve() if public_output else root
        output_paths.append(_relative_path(resolved_public_output, root))

        _require(shard.get("shard_index") == expected["shard_index"], errors, f"{shard_id}: shard_index mismatch")
        _require(shard.get("target_count") == expected["target_count"], errors, f"{shard_id}: target_count mismatch")
        _require(
            shard.get("enabled_public_target_count") == expected["enabled_public_target_count"],
            errors,
            f"{shard_id}: enabled_public_target_count mismatch",
        )
        _require(
            shard.get("policy_disabled_target_count") == expected["policy_disabled_target_count"],
            errors,
            f"{shard_id}: policy_disabled_target_count mismatch",
        )
        _require(target_ids == expected["target_ids"], errors, f"{shard_id}: target_ids must match source manifest order chunk")
        _require(bool(public_output), errors, f"{shard_id}: public_output must be a path string")
        _require(
            shard.get("expected_missing_output_status") == "external_blocked",
            errors,
            f"{shard_id}: expected_missing_output_status must be external_blocked",
        )

        shard_summaries.append(
            {
                "shard_id": shard_id,
                "shard_index": shard.get("shard_index"),
                "target_count": shard.get("target_count"),
                "enabled_public_target_count": shard.get("enabled_public_target_count"),
                "policy_disabled_target_count": shard.get("policy_disabled_target_count"),
                "target_ids": target_ids,
                "public_output": _relative_path(resolved_public_output, root),
                "public_output_present": resolved_public_output.is_file(),
                "public_output_status": PUBLIC_OUTPUT_STATUS if resolved_public_output.is_file() else "external_blocked",
            }
        )

    expected_target_ids = [target_id for shard in expected_shards for target_id in shard["target_ids"]]
    missing_shards = sorted(set(expected_by_id) - seen_shard_ids)
    extra_shards = sorted(seen_shard_ids - set(expected_by_id))
    _require(not missing_shards, errors, f"manifest.shards missing shard_ids: {missing_shards}")
    _require(not extra_shards, errors, f"manifest.shards has unexpected shard_ids: {extra_shards}")
    _require(seen_targets == expected_target_ids, errors, "manifest shard target_ids must cover the embedded 45-site snapshot once in order")
    _require(len(set(seen_targets)) == len(seen_targets), errors, "manifest shard target_ids must be unique")
    _require(len(set(output_paths)) == len(output_paths), errors, "manifest shard public_output paths must be unique")

    return {
        "shard_count": len(shard_summaries),
        "target_count": len(seen_targets),
        "enabled_public_target_count": sum(int(shard.get("enabled_public_target_count") or 0) for shard in shard_summaries),
        "policy_disabled_target_count": sum(int(shard.get("policy_disabled_target_count") or 0) for shard in shard_summaries),
        "expected_shard_ids": sorted(expected_by_id),
        "manifest_shard_ids": sorted(seen_shard_ids),
        "missing_public_output_count": sum(1 for shard in shard_summaries if not shard["public_output_present"]),
        "present_public_output_count": sum(1 for shard in shard_summaries if shard["public_output_present"]),
        "shards": shard_summaries,
    }


def _public_output_boundary_summary(root: Path, manifest: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    boundary = manifest.get("public_output_boundary") if isinstance(manifest.get("public_output_boundary"), Mapping) else {}
    _require(isinstance(manifest.get("public_output_boundary"), Mapping), errors, "manifest.public_output_boundary must be an object")
    source_full_output = str(boundary.get("source_full_output") or "").strip()
    source_full_path = _resolve_path(root, source_full_output).resolve() if source_full_output else root
    _require(bool(source_full_output), errors, "manifest.public_output_boundary.source_full_output must be a path string")
    _require(
        boundary.get("real_public_browser_fleet_replay_status") == "external_blocked",
        errors,
        "manifest.public_output_boundary.real_public_browser_fleet_replay_status must be external_blocked",
    )
    _require(
        boundary.get("full_closure_allowed") is False,
        errors,
        "manifest.public_output_boundary.full_closure_allowed must be false",
    )
    required_future_evidence = _as_string_list(boundary.get("required_future_evidence"))
    _require(
        {
            "opt-in 45-site public replay output",
            "per-shard public browser/fetch output JSON",
            "40 enabled public targets attempted",
            "5 policy-disabled platform/API targets skipped",
        }.issubset(set(required_future_evidence)),
        errors,
        "manifest.public_output_boundary.required_future_evidence is incomplete",
    )
    return {
        "source_full_output": _relative_path(source_full_path, root),
        "source_full_output_present": source_full_path.is_file(),
        "real_public_browser_fleet_replay_status": boundary.get("real_public_browser_fleet_replay_status"),
        "full_closure_allowed": boundary.get("full_closure_allowed") is True,
        "required_future_evidence": required_future_evidence,
    }


def _readback_runtime_summary(
    readback: Mapping[str, Any],
    errors: list[str],
    *,
    public_output_mode: bool,
) -> dict[str, Any]:
    runtime = readback.get("runtime") if isinstance(readback.get("runtime"), Mapping) else {}
    _require(isinstance(readback.get("runtime"), Mapping), errors, "readback.runtime must be an object")
    expected_flags = PUBLIC_OUTPUT_RUNTIME_FLAGS if public_output_mode else MISSING_OUTPUT_RUNTIME_FLAGS
    expected_mode = PUBLIC_OUTPUT_RUNTIME_MODE if public_output_mode else MISSING_OUTPUT_RUNTIME_MODE
    for key, expected in expected_flags.items():
        _require(runtime.get(key) is expected, errors, f"readback.runtime.{key} must be {expected!r}")
    _require(
        runtime.get("mode") == expected_mode,
        errors,
        f"readback.runtime.mode must be {expected_mode}",
    )
    return {"mode": runtime.get("mode"), **{key: runtime.get(key) for key in expected_flags}}


def _validate_public_shard_output(
    *,
    root: Path,
    public_output_path: Path,
    manifest_shard: Mapping[str, Any],
    source_full_output: str,
    errors: list[str],
) -> dict[str, Any]:
    shard_id = str(manifest_shard.get("shard_id") or "").strip()
    payload = _load_json_file(public_output_path, errors, f"{shard_id} public shard output")
    if not payload:
        return {}

    validation = payload.get("validation") if isinstance(payload.get("validation"), Mapping) else {}
    mode = payload.get("mode") if isinstance(payload.get("mode"), Mapping) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), Mapping) else {}
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), Mapping) else {}
    target_results = _target_results_from_payload(payload)
    result_target_ids = [_target_id_from_result(row) for row in target_results]
    expected_target_ids = list(manifest_shard.get("target_ids") or [])
    status_counts = _status_counts_from_payload(payload)
    computed_status_counts = _status_counts_from_results(target_results)
    public_attempted = int(outputs.get("public_targets_attempted") or _public_attempted_count(target_results))
    policy_skipped = int(status_counts.get("skipped_policy_disabled_platform_entry") or 0)
    operator_gate_skipped = int(status_counts.get("skipped_public_network_disabled") or 0)

    _require(payload.get("contract_version") == SHARD_OUTPUT_CONTRACT_VERSION, errors, f"{shard_id}: shard output contract mismatch")
    _require(payload.get("shard_id") == shard_id, errors, f"{shard_id}: shard output shard_id mismatch")
    _require(payload.get("shard_index") == manifest_shard.get("shard_index"), errors, f"{shard_id}: shard output shard_index mismatch")
    _require(payload.get("source_full_output_path") == source_full_output, errors, f"{shard_id}: source_full_output_path mismatch")
    _require(bool(mode.get("allow_public_network")), errors, f"{shard_id}: shard output must record allow_public_network=true")
    _require(bool(validation.get("passed")), errors, f"{shard_id}: shard output validation.passed must be true")
    _require(validation.get("skipped") is False, errors, f"{shard_id}: shard output validation.skipped must be false")
    _require(
        validation.get("public_network_attempted") is True,
        errors,
        f"{shard_id}: shard output validation.public_network_attempted must be true",
    )
    _require(
        validation.get("target_order_matches_manifest") is True,
        errors,
        f"{shard_id}: shard output target_order_matches_manifest must be true",
    )
    _require(inputs.get("target_count") == manifest_shard.get("target_count"), errors, f"{shard_id}: shard output target_count mismatch")
    _require(
        inputs.get("enabled_public_target_count") == manifest_shard.get("enabled_public_target_count"),
        errors,
        f"{shard_id}: shard output enabled_public_target_count mismatch",
    )
    _require(
        inputs.get("policy_disabled_target_count") == manifest_shard.get("policy_disabled_target_count"),
        errors,
        f"{shard_id}: shard output policy_disabled_target_count mismatch",
    )
    _require(result_target_ids == expected_target_ids, errors, f"{shard_id}: shard output target_results order mismatch")
    _require(status_counts == computed_status_counts, errors, f"{shard_id}: shard output status_counts mismatch target_results")
    _require(
        public_attempted == int(manifest_shard.get("enabled_public_target_count") or 0),
        errors,
        f"{shard_id}: shard output must attempt every enabled public target",
    )
    _require(
        policy_skipped == int(manifest_shard.get("policy_disabled_target_count") or 0),
        errors,
        f"{shard_id}: shard output policy-disabled skip count mismatch",
    )
    _require(operator_gate_skipped == 0, errors, f"{shard_id}: shard output must not contain operator-gate skips")

    return {
        "contract_version": payload.get("contract_version"),
        "source_full_output_path": payload.get("source_full_output_path"),
        "allow_public_network": bool(mode.get("allow_public_network")),
        "validation_passed": bool(validation.get("passed")),
        "target_count": len(target_results),
        "public_targets_attempted": public_attempted,
        "policy_skipped_status_count": policy_skipped,
        "operator_gate_skip_count": operator_gate_skipped,
        "status_counts": status_counts,
    }


def _readback_summary(
    *,
    root: Path,
    manifest_path: Path,
    readback_path: Path,
    manifest_shards: Mapping[str, Any],
    public_output_boundary: Mapping[str, Any],
    readback: Mapping[str, Any],
    artifacts: Mapping[str, Path],
    errors: list[str],
) -> dict[str, Any]:
    _require(readback.get("contract_version") == READBACK_CONTRACT_VERSION, errors, "readback contract_version mismatch")
    readback_scope = str(readback.get("scope") or "").strip()
    public_output_mode = readback_scope == PUBLIC_OUTPUT_READBACK_SCOPE
    _require(
        readback_scope in {MISSING_OUTPUT_READBACK_SCOPE, PUBLIC_OUTPUT_READBACK_SCOPE},
        errors,
        "readback.scope mismatch",
    )
    _require(
        readback.get("shard_manifest_path") == _relative_path(manifest_path, root),
        errors,
        "readback.shard_manifest_path must point to the checked manifest",
    )
    source_manifest_path = artifacts.get("source_replay_manifest", root)
    browser_fixture_path = artifacts.get("llm_browser_replay_fixture", root)
    _require(
        readback.get("source_manifest_path") == _relative_path(source_manifest_path, root),
        errors,
        "readback.source_manifest_path mismatch",
    )
    _require(
        readback.get("browser_fixture_path") == _relative_path(browser_fixture_path, root),
        errors,
        "readback.browser_fixture_path mismatch",
    )

    runtime = _readback_runtime_summary(readback, errors, public_output_mode=public_output_mode)
    readback_counts = readback.get("readback") if isinstance(readback.get("readback"), Mapping) else {}
    _require(isinstance(readback.get("readback"), Mapping), errors, "readback.readback must be an object")
    _require(readback_counts.get("shard_count") == manifest_shards.get("shard_count"), errors, "readback.shard_count mismatch")
    _require(readback_counts.get("target_count") == 45, errors, "readback.target_count must be 45")
    _require(readback_counts.get("enabled_public_target_count") == 40, errors, "readback enabled_public_target_count must be 40")
    _require(readback_counts.get("policy_disabled_target_count") == 5, errors, "readback policy_disabled_target_count must be 5")
    _require(
        readback_counts.get("missing_public_output_count") == manifest_shards.get("missing_public_output_count"),
        errors,
        "readback missing_public_output_count mismatch",
    )
    if public_output_mode:
        _require(readback_counts.get("present_public_output_count") == manifest_shards.get("present_public_output_count"), errors, "readback present_public_output_count mismatch")
        _require(readback_counts.get("missing_public_output_count") == 0, errors, "readback missing_public_output_count must be 0")
        _require(
            readback_counts.get("public_output_status") == PUBLIC_OUTPUT_STATUS,
            errors,
            f"readback public_output_status must be {PUBLIC_OUTPUT_STATUS}",
        )
        _require(
            readback_counts.get("real_public_browser_fleet_replay_complete") is True,
            errors,
            "readback real_public_browser_fleet_replay_complete must be true",
        )
    else:
        _require(
            readback_counts.get("missing_public_output_status") == "external_blocked",
            errors,
            "readback missing_public_output_status must be external_blocked",
        )
        _require(
            readback_counts.get("real_public_browser_fleet_replay_complete") is False,
            errors,
            "readback real_public_browser_fleet_replay_complete must be false",
        )
    _require(readback_counts.get("full_closure_allowed") is False, errors, "readback full_closure_allowed must be false")

    manifest_shards_by_id = {
        str(shard.get("shard_id") or ""): shard
        for shard in manifest_shards.get("shards", [])
        if isinstance(shard, Mapping)
    }
    raw_shards = readback.get("shards")
    shards = raw_shards if isinstance(raw_shards, list) else []
    _require(isinstance(raw_shards, list), errors, "readback.shards must be a list")
    shard_summaries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    public_output_summaries: dict[str, dict[str, Any]] = {}
    source_full_output = str(public_output_boundary.get("source_full_output") or "").strip()
    for raw_shard in shards:
        shard = raw_shard if isinstance(raw_shard, Mapping) else {}
        shard_id = str(shard.get("shard_id") or "").strip()
        seen_ids.add(shard_id)
        manifest_shard = manifest_shards_by_id.get(shard_id)
        if manifest_shard is None:
            errors.append(f"unexpected readback shard_id: {shard_id!r}")
            continue
        expected_public_output = str(manifest_shard.get("public_output") or "")
        public_output = str(shard.get("public_output") or "").strip()
        public_output_path = _resolve_path(root, public_output).resolve() if public_output else root
        _require(shard.get("shard_index") == manifest_shard.get("shard_index"), errors, f"{shard_id}: readback shard_index mismatch")
        _require(shard.get("target_count") == manifest_shard.get("target_count"), errors, f"{shard_id}: readback target_count mismatch")
        _require(
            _as_string_list(shard.get("target_ids")) == manifest_shard.get("target_ids"),
            errors,
            f"{shard_id}: readback target_ids mismatch",
        )
        _require(public_output == expected_public_output, errors, f"{shard_id}: readback public_output mismatch")
        if public_output_mode:
            _require(shard.get("evidence_present") is True, errors, f"{shard_id}: evidence_present must be true")
            _require(
                shard.get("public_output_status") == PUBLIC_OUTPUT_STATUS,
                errors,
                f"{shard_id}: public_output_status must be {PUBLIC_OUTPUT_STATUS}",
            )
            _require(public_output_path.is_file(), errors, f"{shard_id}: public output must be present")
            if public_output_path.is_file():
                public_output_summaries[shard_id] = _validate_public_shard_output(
                    root=root,
                    public_output_path=public_output_path,
                    manifest_shard=manifest_shard,
                    source_full_output=source_full_output,
                    errors=errors,
                )
        else:
            _require(shard.get("evidence_present") is False, errors, f"{shard_id}: evidence_present must be false")
            _require(shard.get("public_output_status") == "external_blocked", errors, f"{shard_id}: public_output_status must be external_blocked")
            _require(not public_output_path.is_file(), errors, f"{shard_id}: public output must remain absent for external_blocked readback")
        shard_summaries.append(
            {
                "shard_id": shard_id,
                "shard_index": shard.get("shard_index"),
                "target_count": shard.get("target_count"),
                "public_output": _relative_path(public_output_path, root),
                "evidence_present": shard.get("evidence_present") is True,
                "public_output_status": shard.get("public_output_status"),
                "public_output_summary": public_output_summaries.get(shard_id, {}),
            }
        )

    missing_ids = sorted(set(manifest_shards_by_id) - seen_ids)
    extra_ids = sorted(seen_ids - set(manifest_shards_by_id))
    _require(not missing_ids, errors, f"readback.shards missing shard_ids: {missing_ids}")
    _require(not extra_ids, errors, f"readback.shards has unexpected shard_ids: {extra_ids}")

    closure = readback.get("closure") if isinstance(readback.get("closure"), Mapping) else {}
    _require(isinstance(readback.get("closure"), Mapping), errors, "readback.closure must be an object")
    if public_output_mode:
        _require(closure.get("status") == PUBLIC_OUTPUT_STATUS, errors, f"readback.closure.status must be {PUBLIC_OUTPUT_STATUS}")
        _require(
            closure.get("real_public_browser_fleet_replay_complete") is True,
            errors,
            "readback.closure.real_public_browser_fleet_replay_complete must be true",
        )
    else:
        _require(closure.get("status") == "external_blocked", errors, "readback.closure.status must be external_blocked")
        _require(
            closure.get("real_public_browser_fleet_replay_complete") is False,
            errors,
            "readback.closure.real_public_browser_fleet_replay_complete must be false",
        )
    _require(closure.get("full_closure_allowed") is False, errors, "readback.closure.full_closure_allowed must be false")

    return {
        "readback_path": _relative_path(readback_path, root),
        "scope": readback_scope,
        "runtime": runtime,
        "counts": {
            "shard_count": readback_counts.get("shard_count"),
            "target_count": readback_counts.get("target_count"),
            "enabled_public_target_count": readback_counts.get("enabled_public_target_count"),
            "policy_disabled_target_count": readback_counts.get("policy_disabled_target_count"),
            "missing_public_output_count": readback_counts.get("missing_public_output_count"),
            "missing_public_output_status": readback_counts.get("missing_public_output_status"),
            "present_public_output_count": readback_counts.get("present_public_output_count"),
            "public_output_status": readback_counts.get("public_output_status"),
        },
        "shards": shard_summaries,
        "closure": {
            "status": closure.get("status"),
            "real_public_browser_fleet_replay_complete": closure.get("real_public_browser_fleet_replay_complete") is True,
            "full_closure_allowed": closure.get("full_closure_allowed") is True,
            "claim": closure.get("claim"),
        },
    }


def _gate_summary(root: Path, gate_manifest_path: Path, errors: list[str]) -> dict[str, Any]:
    gate = build_public_gate_check(root, manifest_path=gate_manifest_path)
    validation = gate.get("validation") if isinstance(gate.get("validation"), Mapping) else {}
    live_public = gate.get("live_public_replay") if isinstance(gate.get("live_public_replay"), Mapping) else {}
    _require(validation.get("passed") is True, errors, "crawler public replay gate must pass")
    _require(validation.get("public_network_attempted") is False, errors, "crawler public replay gate must not attempt public network")
    allowed_overall_statuses = {
        "deterministic_artifacts_valid_live_public_replay_not_closed",
        "deterministic_artifacts_valid_live_public_replay_evidence_present_review_required",
    }
    allowed_live_statuses = {"not_closed_missing_real_evidence", PUBLIC_OUTPUT_STATUS}
    _require(
        gate.get("overall_status") in allowed_overall_statuses,
        errors,
        "crawler public replay gate status must be not_closed or evidence_present_review_required",
    )
    _require(
        live_public.get("status") in allowed_live_statuses,
        errors,
        "crawler public replay gate live status must be not_closed_missing_real_evidence or real_evidence_present_review_required",
    )
    return {
        "contract_version": gate.get("contract_version"),
        "passed": validation.get("passed") is True,
        "overall_status": gate.get("overall_status"),
        "live_public_replay_status": live_public.get("status"),
        "live_public_replay_evidence_present": live_public.get("evidence_present") is True,
        "public_network_attempted": validation.get("public_network_attempted") is True,
    }


def _browser_fixture_gate_summary(
    root: Path,
    manifest_path: Path,
    fixture_path: Path,
    errors: list[str],
) -> dict[str, Any]:
    fixture = build_browser_fixture_check(root, manifest_path=manifest_path, fixture_path=fixture_path)
    validation = fixture.get("validation") if isinstance(fixture.get("validation"), Mapping) else {}
    closure = fixture.get("closure") if isinstance(fixture.get("closure"), Mapping) else {}
    _require(validation.get("passed") is True, errors, "LLM crawler browser replay fixture checker must pass")
    _require(validation.get("public_network_attempted") is False, errors, "browser fixture must not attempt public network")
    _require(validation.get("browser_runtime_started") is False, errors, "browser fixture must not start browser runtime")
    _require(
        closure.get("real_public_high_js_replay_complete") is False,
        errors,
        "browser fixture must not claim real public high-JS replay completion",
    )
    _require(closure.get("full_closure_allowed") is False, errors, "browser fixture must keep full closure disabled")
    return {
        "contract_version": fixture.get("contract_version"),
        "passed": validation.get("passed") is True,
        "status": fixture.get("status"),
        "real_public_high_js_replay_complete": closure.get("real_public_high_js_replay_complete") is True,
        "full_closure_allowed": closure.get("full_closure_allowed") is True,
        "public_network_attempted": validation.get("public_network_attempted") is True,
        "browser_runtime_started": validation.get("browser_runtime_started") is True,
    }


def build_check(
    repo_root: Path | str | None = None,
    manifest_path: Path | str | None = None,
    readback_path: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    manifest_rel = Path(manifest_path) if manifest_path is not None else DEFAULT_MANIFEST_PATH
    manifest_abs = _resolve_path(root, manifest_rel).resolve()
    errors: list[str] = []

    manifest = _load_json_file(manifest_abs, errors, "crawler public replay shard manifest")
    _require(
        manifest.get("contract_version") == MANIFEST_CONTRACT_VERSION,
        errors,
        f"manifest contract_version must be {MANIFEST_CONTRACT_VERSION}",
    )
    _require(isinstance(manifest.get("scope"), str) and bool(manifest.get("scope", "").strip()), errors, "manifest.scope is required")
    expected_counts = _validate_expected_counts(manifest.get("expected_counts"), errors, "manifest.expected_counts")
    artifacts = _artifact_paths(root, manifest_abs, manifest, errors)

    readback_rel = Path(readback_path) if readback_path is not None else artifacts.get("shard_readback", DEFAULT_READBACK_PATH)
    readback_abs = _resolve_path(root, readback_rel).resolve()
    if readback_path is not None:
        expected_readback = artifacts.get("shard_readback")
        if expected_readback is not None:
            _require(
                readback_abs == expected_readback,
                errors,
                "explicit readback_path must match manifest.required_artifacts.shard_readback",
            )
    readback = _load_json_file(readback_abs, errors, "crawler public replay shard readback")

    source_manifest_path = artifacts.get("source_replay_manifest", root / "missing-source-replay-manifest.json")
    source_manifest = _load_json_file(source_manifest_path, errors, "source replay manifest")
    source_manifest_summary = _source_manifest_summary(source_manifest, errors) if source_manifest else {}

    shard_policy = _shard_policy_summary(manifest, errors)
    manifest_shards = _manifest_shard_summary(root, manifest, errors)
    public_output_boundary = _public_output_boundary_summary(root, manifest, errors)
    readback_summary = (
        _readback_summary(
            root=root,
            manifest_path=manifest_abs,
            readback_path=readback_abs,
            manifest_shards=manifest_shards,
            public_output_boundary=public_output_boundary,
            readback=readback,
            artifacts=artifacts,
            errors=errors,
        )
        if readback
        else {}
    )

    gate_manifest_path = artifacts.get("crawler_public_replay_gate_manifest", root / "missing-gate-manifest.json")
    llm_manifest_path = artifacts.get("llm_high_js_replay_manifest", root / "missing-llm-manifest.json")
    browser_fixture_path = artifacts.get("llm_browser_replay_fixture", root / "missing-browser-fixture.json")
    crawler_gate = _gate_summary(root, gate_manifest_path, errors) if gate_manifest_path.is_file() else {}
    browser_gate = (
        _browser_fixture_gate_summary(root, llm_manifest_path, browser_fixture_path, errors)
        if llm_manifest_path.is_file() and browser_fixture_path.is_file()
        else {}
    )

    missing_output_count = int(manifest_shards.get("missing_public_output_count") or 0)
    present_output_count = int(manifest_shards.get("present_public_output_count") or 0)
    public_outputs_complete = bool(
        not errors
        and present_output_count == int(manifest_shards.get("shard_count") or 0)
        and readback_summary.get("closure", {}).get("real_public_browser_fleet_replay_complete") is True
    )
    validation_passed = not errors
    status = (
        "failed"
        if not validation_passed
        else "shard_outputs_present_review_required"
        if public_outputs_complete
        else "shard_manifest_valid_public_outputs_external_blocked"
    )
    overall_status = (
        "failed"
        if not validation_passed
        else "public_replay_shards_present_review_required"
        if public_outputs_complete
        else "external_blocked"
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "manifest_contract_version": MANIFEST_CONTRACT_VERSION,
        "readback_contract_version": READBACK_CONTRACT_VERSION,
        "repo_root": str(root),
        "manifest_path": _relative_path(manifest_abs, root),
        "readback_path": _relative_path(readback_abs, root),
        "status": status,
        "scope": "crawler_public_replay_shard_manifest_readback",
        "evidence_docs": {
            "crawler_source_expansion": str(CRAWLER_TOPIC_DOC),
            "llm_crawler_unified_frontdoor": str(LLM_TOPIC_DOC),
        },
        "expected_counts": expected_counts,
        "source_manifest": source_manifest_summary,
        "shard_policy": shard_policy,
        "shard_manifest": manifest_shards,
        "public_output_boundary": public_output_boundary,
        "shard_readback": readback_summary,
        "crawler_public_replay_gate": crawler_gate,
        "browser_replay_fixture_gate": browser_gate,
        "closure": {
            "shard_manifest_valid": validation_passed,
            "shard_readback_valid": validation_passed,
            "missing_public_outputs_external_blocked": missing_output_count == 5 and validation_passed,
            "public_shard_outputs_present": public_outputs_complete,
            "real_public_browser_fleet_replay_complete": public_outputs_complete,
            "full_closure_allowed": False,
            "overall_status": overall_status,
            "claim": (
                "real_public_replay_shard_outputs_present_review_required"
                if public_outputs_complete
                else "repo_local_shard_manifest_passed_missing_public_outputs_external_blocked"
                if validation_passed
                else "repo_local_shard_manifest_failed"
            ),
        },
        "validation": {
            "passed": validation_passed,
            "errors": errors,
            "public_network_attempted": bool(readback_summary.get("runtime", {}).get("public_network_attempted")),
            "browser_runtime_started": False,
            "shared_indexes_edited": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate crawler public replay shard manifest/readback without public network access."
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--readback", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build_check(args.repo_root, args.manifest, args.readback)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
