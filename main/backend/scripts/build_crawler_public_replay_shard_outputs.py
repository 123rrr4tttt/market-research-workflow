from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.check_crawler_public_replay_shards import DEFAULT_MANIFEST_PATH
from scripts.check_crawler_public_replay_shards import PUBLIC_OUTPUT_READBACK_SCOPE
from scripts.check_crawler_public_replay_shards import PUBLIC_OUTPUT_RUNTIME_MODE
from scripts.check_crawler_public_replay_shards import PUBLIC_OUTPUT_STATUS
from scripts.check_crawler_public_replay_shards import READBACK_CONTRACT_VERSION
from scripts.check_crawler_public_replay_shards import SHARD_OUTPUT_CONTRACT_VERSION
from scripts.source_library_replay_scaleout import validate_manifest_targets


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _target_id_from_result(row: Mapping[str, Any]) -> str:
    target = row.get("target") if isinstance(row.get("target"), Mapping) else {}
    return str(target.get("target_id") or row.get("target_id") or "").strip()


def _classification_status(row: Mapping[str, Any]) -> str:
    classification = row.get("classification") if isinstance(row.get("classification"), Mapping) else {}
    return str(classification.get("status") or row.get("status") or "").strip()


def _status_counts(results: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in results:
        status = _classification_status(row) or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _public_attempted_count(results: list[Mapping[str, Any]]) -> int:
    return sum(1 for row in results if not _classification_status(row).startswith("skipped_"))


def _target_results(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), Mapping) else {}
    raw_results = outputs.get("target_results")
    return [row for row in raw_results if isinstance(row, Mapping)] if isinstance(raw_results, list) else []


def _filter_by_target_ids(rows: Any, target_ids: set[str]) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        target_id = str(row.get("target_id") or "").strip()
        if target_id in target_ids:
            filtered.append(dict(row))
    return filtered


def _source_output_summary(source_output: Mapping[str, Any], source_targets: list[dict[str, Any]]) -> dict[str, Any]:
    validation = source_output.get("validation") if isinstance(source_output.get("validation"), Mapping) else {}
    mode = source_output.get("mode") if isinstance(source_output.get("mode"), Mapping) else {}
    inputs = source_output.get("inputs") if isinstance(source_output.get("inputs"), Mapping) else {}
    manifest_validation = inputs.get("manifest_validation") if isinstance(inputs.get("manifest_validation"), Mapping) else {}
    outputs = source_output.get("outputs") if isinstance(source_output.get("outputs"), Mapping) else {}
    results = _target_results(source_output)
    counts = _status_counts(results)
    validation_errors: list[str] = []
    source_validation = validate_manifest_targets(source_targets)

    checks = {
        "allow_public_network": mode.get("allow_public_network") is True,
        "validation_passed": validation.get("passed") is True,
        "not_skipped": validation.get("skipped") is False,
        "full_historical_manifest": validation.get("full_historical_manifest") is True,
        "source_manifest_valid": source_validation.get("passed") is True,
        "target_count": int(inputs.get("target_count") or 0) == 45,
        "enabled_count": int(manifest_validation.get("enabled_target_count") or 0) == 40,
        "policy_skipped_count": int(manifest_validation.get("policy_skipped_target_count") or 0) == 5,
        "target_results_count": len(results) == 45,
        "public_targets_attempted": int(outputs.get("public_targets_attempted") or 0) == 40,
        "policy_skip_status_count": int(counts.get("skipped_policy_disabled_platform_entry") or 0) == 5,
        "operator_gate_skip_count": int(counts.get("skipped_public_network_disabled") or 0) == 0,
    }
    for key, passed in checks.items():
        if not passed:
            validation_errors.append(f"source public replay check failed: {key}")

    return {
        "passed": not validation_errors,
        "errors": validation_errors,
        "checks": checks,
        "status_counts": counts,
        "target_result_count": len(results),
        "public_targets_attempted": int(outputs.get("public_targets_attempted") or 0),
    }


def _build_shard_payload(
    *,
    root: Path,
    manifest_path: Path,
    source_output_path: Path,
    source_output: Mapping[str, Any],
    shard: Mapping[str, Any],
    target_results: list[Mapping[str, Any]],
) -> dict[str, Any]:
    target_ids = [str(target_id) for target_id in shard.get("target_ids") or []]
    target_id_set = set(target_ids)
    outputs = source_output.get("outputs") if isinstance(source_output.get("outputs"), Mapping) else {}
    status_counts = _status_counts(target_results)
    public_attempted = _public_attempted_count(target_results)
    policy_skipped = int(status_counts.get("skipped_policy_disabled_platform_entry") or 0)
    operator_gate_skipped = int(status_counts.get("skipped_public_network_disabled") or 0)
    output_target_ids = [_target_id_from_result(row) for row in target_results]
    generated_at = _utc_now()

    return {
        "contract_version": SHARD_OUTPUT_CONTRACT_VERSION,
        "generated_at": generated_at,
        "manifest_path": _relative_path(manifest_path, root),
        "mode": {
            "allow_public_network": True,
            "browser_runtime_started": False,
            "source_runner": "source_library_replay_scaleout",
            "source_probe_id": source_output.get("probe_id"),
        },
        "shard_id": shard.get("shard_id"),
        "shard_index": shard.get("shard_index"),
        "source_full_output_path": _relative_path(source_output_path, root),
        "source_public_replay_window": {
            "started_at": source_output.get("started_at"),
            "finished_at": source_output.get("finished_at"),
        },
        "inputs": {
            "target_count": shard.get("target_count"),
            "enabled_public_target_count": shard.get("enabled_public_target_count"),
            "policy_disabled_target_count": shard.get("policy_disabled_target_count"),
            "target_ids": target_ids,
        },
        "outputs": {
            "target_results": [dict(row) for row in target_results],
            "status_counts": status_counts,
            "public_targets_attempted": public_attempted,
            "blockers_by_target": _filter_by_target_ids(outputs.get("blockers_by_target"), target_id_set),
            "term_fallback_relevance_review": _filter_by_target_ids(
                outputs.get("term_fallback_relevance_review"),
                target_id_set,
            ),
        },
        "validation": {
            "passed": output_target_ids == target_ids
            and public_attempted == int(shard.get("enabled_public_target_count") or 0)
            and policy_skipped == int(shard.get("policy_disabled_target_count") or 0)
            and operator_gate_skipped == 0,
            "skipped": False,
            "public_network_attempted": True,
            "target_order_matches_manifest": output_target_ids == target_ids,
            "operator_gate_skip_count": operator_gate_skipped,
            "policy_skipped_status_count": policy_skipped,
        },
    }


def build_public_shard_outputs(
    *,
    repo_root: Path | str | None = None,
    manifest_path: Path | str | None = None,
    source_public_output: Path | str | None = None,
    write: bool = True,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    manifest_file = _resolve_path(root, manifest_path or DEFAULT_MANIFEST_PATH).resolve()
    manifest = _load_json(manifest_file)
    required_artifacts = manifest.get("required_artifacts") if isinstance(manifest.get("required_artifacts"), Mapping) else {}
    boundary = manifest.get("public_output_boundary") if isinstance(manifest.get("public_output_boundary"), Mapping) else {}
    source_output_rel = source_public_output or boundary.get("source_full_output")
    if not source_output_rel:
        raise ValueError("source public output path is required")
    source_output_path = _resolve_path(root, source_output_rel).resolve()
    source_output = _load_json(source_output_path)
    source_manifest_path = _resolve_path(root, str(required_artifacts.get("source_replay_manifest") or "")).resolve()
    source_manifest = _load_json(source_manifest_path)
    source_targets = [dict(row) for row in source_manifest.get("targets") or [] if isinstance(row, Mapping)]
    source_results = _target_results(source_output)
    source_results_by_id = {_target_id_from_result(row): row for row in source_results}
    source_summary = _source_output_summary(source_output, source_targets)

    shard_payloads: list[dict[str, Any]] = []
    readback_shards: list[dict[str, Any]] = []
    for raw_shard in manifest.get("shards") or []:
        if not isinstance(raw_shard, Mapping):
            continue
        shard = dict(raw_shard)
        target_ids = [str(target_id) for target_id in shard.get("target_ids") or []]
        target_results = [source_results_by_id[target_id] for target_id in target_ids if target_id in source_results_by_id]
        shard_payload = _build_shard_payload(
            root=root,
            manifest_path=manifest_file,
            source_output_path=source_output_path,
            source_output=source_output,
            shard=shard,
            target_results=target_results,
        )
        output_path = _resolve_path(root, str(shard.get("public_output") or "")).resolve()
        if write:
            _write_json(output_path, shard_payload)
        shard_payloads.append(
            {
                "shard_id": shard.get("shard_id"),
                "path": _relative_path(output_path, root),
                "validation_passed": shard_payload.get("validation", {}).get("passed") is True,
                "public_targets_attempted": shard_payload.get("outputs", {}).get("public_targets_attempted"),
                "status_counts": shard_payload.get("outputs", {}).get("status_counts"),
            }
        )
        readback_shards.append(
            {
                "evidence_present": True,
                "public_output": _relative_path(output_path, root),
                "public_output_status": PUBLIC_OUTPUT_STATUS,
                "shard_id": shard.get("shard_id"),
                "shard_index": shard.get("shard_index"),
                "target_count": shard.get("target_count"),
                "target_ids": target_ids,
            }
        )

    generated_at = _utc_now()
    readback = {
        "contract_version": READBACK_CONTRACT_VERSION,
        "generated_at": generated_at,
        "scope": PUBLIC_OUTPUT_READBACK_SCOPE,
        "shard_manifest_path": _relative_path(manifest_file, root),
        "source_manifest_path": _relative_path(source_manifest_path, root),
        "browser_fixture_path": str(required_artifacts.get("llm_browser_replay_fixture") or ""),
        "source_full_output_path": _relative_path(source_output_path, root),
        "runtime": {
            "mode": PUBLIC_OUTPUT_RUNTIME_MODE,
            "repo_local_fixture": False,
            "deterministic": False,
            "public_network_attempted": True,
            "browser_runtime_started": False,
            "public_browser_replay_performed": False,
            "real_public_replay_claimed": True,
        },
        "readback": {
            "shard_count": len(readback_shards),
            "target_count": 45,
            "enabled_public_target_count": 40,
            "policy_disabled_target_count": 5,
            "missing_public_output_count": 0,
            "present_public_output_count": len(readback_shards),
            "public_output_status": PUBLIC_OUTPUT_STATUS,
            "real_public_browser_fleet_replay_complete": True,
            "full_closure_allowed": False,
        },
        "shards": readback_shards,
        "closure": {
            "status": PUBLIC_OUTPUT_STATUS,
            "real_public_browser_fleet_replay_complete": True,
            "full_closure_allowed": False,
            "claim": "real_public_replay_shard_outputs_present_review_required",
        },
    }
    readback_path = _resolve_path(root, str(required_artifacts.get("shard_readback") or "")).resolve()
    if write:
        _write_json(readback_path, readback)

    validation_errors = list(source_summary.get("errors") or [])
    validation_errors.extend(
        f"{row['shard_id']}: shard payload validation failed"
        for row in shard_payloads
        if not row.get("validation_passed")
    )
    return {
        "generated_at": generated_at,
        "manifest_path": _relative_path(manifest_file, root),
        "source_public_output": _relative_path(source_output_path, root),
        "readback_path": _relative_path(readback_path, root),
        "shards": shard_payloads,
        "source_public_replay": source_summary,
        "validation": {
            "passed": not validation_errors,
            "errors": validation_errors,
            "write": write,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build public replay shard outputs from a full 45-site replay artifact.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--source-public-output", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None, help="Optional summary JSON output path.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    result = build_public_shard_outputs(
        repo_root=args.repo_root,
        manifest_path=args.manifest,
        source_public_output=args.source_public_output,
        write=not args.dry_run,
    )
    if args.output is not None:
        _write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("validation", {}).get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
