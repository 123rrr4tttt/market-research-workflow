from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ingest import url_pool as url_pool_module
from scripts.check_llm_crawler_high_js_replay_readiness import CONTRACT_VERSION as READINESS_CONTRACT_VERSION
from scripts.check_llm_crawler_high_js_replay_readiness import DEFAULT_HIGH_JS_TARGETS
from scripts.check_llm_crawler_high_js_replay_readiness import PROTECTED_SHARED_INDEXES
from scripts.check_llm_crawler_high_js_replay_readiness import PUBLIC_REPLAY_CONTRACT_VERSION


CONTRACT_VERSION = "llm_crawler.replay_manifest.check.v1"
MANIFEST_CONTRACT_VERSION = "llm_crawler.high_js_replay_manifest.v1"
OPT_IN_CONTRACT_VERSION = "llm_crawler.high_js_public_replay.opt_in_request.v1"
DEFAULT_MANIFEST_PATH = Path(
    "development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/"
    "2026-05-22/manifest.json"
)

TOPIC_DIR = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-03-08-llm-crawler-unified-frontdoor"
)
WAVE13_DOC = TOPIC_DIR / "06_wave13-high-js-public-replay-readiness-2026-05-22.md"
WAVE15_DOC = TOPIC_DIR / "07_wave15-high-js-replay-manifest-2026-05-22.md"

REQUIRED_ARTIFACT_KEYS = {
    "manifest",
    "readiness_checker",
    "provider_handoff_checker",
    "frontdoor_router_contract",
    "url_pool_route_profiles",
    "wave13_readiness_doc",
    "wave15_manifest_evidence_doc",
    "live_public_output",
}
OPTIONAL_ABSENT_ARTIFACT_KEYS = {"live_public_output"}

REQUIRED_TRUE_FIELDS = [
    "allow_public_network",
    "allow_browser_runtime",
    "allow_high_js_targets",
    "acknowledge_external_site_terms",
    "acknowledge_rate_limits",
    "acknowledge_no_shared_index_edits",
]
REQUIRED_STRING_FIELDS = [
    "operator",
    "run_id",
    "requested_at",
    "browser_runtime",
    "evidence_output",
    "output_contract_version",
]
REQUIRED_LIST_FIELDS = ["target_ids"]

REQUIRED_REAL_EVIDENCE = [
    "contract_version=llm_crawler.high_js_public_replay.v1",
    "operator_opt_in.contract_version=llm_crawler.high_js_public_replay.opt_in_request.v1",
    "operator_opt_in.allow_public_network=true",
    "operator_opt_in.allow_browser_runtime=true",
    "operator_opt_in.allow_high_js_targets=true",
    "validation.real_public_high_js_replay_proven=true",
    "validation.public_network_attempted=true",
    "inputs.target_count=3",
    "outputs.public_targets_attempted=3",
    "outputs.high_js_success_count=3",
    "outputs.target_results[].status=success",
    "outputs.target_results[].browser_rendered=true",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _load_json_file(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    if not path.is_file():
        errors.append(f"missing {label}: {path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"invalid {label}: {path}: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"{label} must be a JSON object: {path}")
        return {}
    return payload


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _expected_targets_by_id() -> dict[str, dict[str, str]]:
    return {str(target["target_id"]): dict(target) for target in DEFAULT_HIGH_JS_TARGETS}


def _artifact_summary(root: Path, manifest_path: Path, manifest: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    raw_artifacts = manifest.get("required_artifacts")
    _require(isinstance(raw_artifacts, dict), errors, "manifest.required_artifacts must be an object")
    artifacts = raw_artifacts if isinstance(raw_artifacts, dict) else {}
    artifact_keys = set(artifacts)
    missing_keys = sorted(REQUIRED_ARTIFACT_KEYS - artifact_keys)
    extra_keys = sorted(artifact_keys - REQUIRED_ARTIFACT_KEYS)
    _require(not missing_keys, errors, f"manifest.required_artifacts missing keys: {missing_keys}")
    _require(not extra_keys, errors, f"manifest.required_artifacts has unexpected keys: {extra_keys}")

    present: dict[str, bool] = {}
    paths: dict[str, str] = {}
    for key in sorted(REQUIRED_ARTIFACT_KEYS):
        value = artifacts.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"manifest.required_artifacts.{key} must be a path string")
            continue
        resolved = _resolve_path(root, value)
        paths[key] = _relative_path(resolved, root)
        exists = resolved.is_file()
        present[key] = exists
        if key not in OPTIONAL_ABSENT_ARTIFACT_KEYS:
            _require(exists, errors, f"manifest.required_artifacts.{key} does not exist: {paths[key]}")

    declared_manifest = artifacts.get("manifest")
    if isinstance(declared_manifest, str) and declared_manifest.strip():
        declared_manifest_path = _resolve_path(root, declared_manifest).resolve()
        _require(
            declared_manifest_path == manifest_path.resolve(),
            errors,
            "manifest.required_artifacts.manifest must point to the checked manifest",
        )

    return {
        "required_keys": sorted(REQUIRED_ARTIFACT_KEYS),
        "present": present,
        "paths": paths,
        "live_public_output_present": bool(present.get("live_public_output")),
    }


def _target_summary(manifest: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    target_set = manifest.get("target_set") if isinstance(manifest.get("target_set"), dict) else {}
    targets = target_set.get("targets") if isinstance(target_set.get("targets"), list) else []
    expected_by_id = _expected_targets_by_id()
    seen_ids: set[str] = set()
    target_results: list[dict[str, Any]] = []

    _require(target_set.get("target_kind") == "high_js_public_replay", errors, "target_set.target_kind mismatch")
    _require(target_set.get("target_count") == len(expected_by_id), errors, "target_set.target_count mismatch")
    _require(isinstance(target_set.get("targets"), list), errors, "target_set.targets must be a list")
    _require(len(targets) == len(expected_by_id), errors, "target_set.targets must match the default high-JS target count")

    for raw_target in targets:
        target = raw_target if isinstance(raw_target, dict) else {}
        target_id = str(target.get("target_id") or "").strip()
        seen_ids.add(target_id)
        expected = expected_by_id.get(target_id)
        if expected is None:
            errors.append(f"unexpected high-JS target_id in manifest: {target_id!r}")
            continue

        url = str(target.get("url") or "").strip()
        expected_domain = str(target.get("expected_domain") or "").strip()
        profile = url_pool_module._frontdoor_route_profile_for_url(url)
        router_contract = profile.get("router_contract") if isinstance(profile.get("router_contract"), dict) else {}
        fallback = (
            router_contract.get("fallback_boundary")
            if isinstance(router_contract.get("fallback_boundary"), dict)
            else {}
        )

        _require(url == expected["url"], errors, f"{target_id}: url must match Wave13 readiness target")
        _require(
            expected_domain == expected["expected_domain"],
            errors,
            f"{target_id}: expected_domain must match Wave13 readiness target",
        )
        _require(target.get("high_js") is True, errors, f"{target_id}: high_js must be true")
        _require(target.get("public_site") is True, errors, f"{target_id}: public_site must be true")
        _require(target.get("render_required") is True, errors, f"{target_id}: render_required must be true")
        _require(target.get("public_replay_opt_in_required") is True, errors, f"{target_id}: opt-in must be required")
        _require(target.get("route_hint") == "crawler_browse", errors, f"{target_id}: route_hint must be crawler_browse")
        _require(
            target.get("fetch_strategy") == "browser_render",
            errors,
            f"{target_id}: fetch_strategy must be browser_render",
        )
        _require(
            target.get("http_fetch_fallback_allowed") is False,
            errors,
            f"{target_id}: http_fetch_fallback_allowed must be false",
        )
        _require(profile.get("domain") == expected_domain, errors, f"{target_id}: route profile domain mismatch")
        _require(profile.get("high_js") is True, errors, f"{target_id}: route profile high_js drifted")
        _require(profile.get("render_required") is True, errors, f"{target_id}: route profile render_required drifted")
        _require(
            profile.get("fetch_strategy") == "browser_render",
            errors,
            f"{target_id}: route profile fetch_strategy drifted",
        )
        _require(
            router_contract.get("router_state") == "needs_browser",
            errors,
            f"{target_id}: router_state must remain needs_browser",
        )
        _require(
            fallback.get("http_fetch_fallback_allowed") is False,
            errors,
            f"{target_id}: router fallback must not allow HTTP fallback",
        )
        _require(
            fallback.get("public_browser_replay_performed") is False,
            errors,
            f"{target_id}: deterministic route profile must not claim public browser replay",
        )
        target_results.append(
            {
                "target_id": target_id,
                "url": url,
                "expected_domain": expected_domain,
                "route_hint": target.get("route_hint"),
                "fetch_strategy": target.get("fetch_strategy"),
                "high_js": target.get("high_js") is True,
                "public_replay_opt_in_required": target.get("public_replay_opt_in_required") is True,
                "router_state": router_contract.get("router_state"),
                "public_browser_replay_performed": fallback.get("public_browser_replay_performed"),
            }
        )

    missing_ids = sorted(set(expected_by_id) - seen_ids)
    extra_ids = sorted(seen_ids - set(expected_by_id))
    _require(not missing_ids, errors, f"target_set.targets missing target_ids: {missing_ids}")
    _require(not extra_ids, errors, f"target_set.targets has unexpected target_ids: {extra_ids}")

    return {
        "target_kind": str(target_set.get("target_kind") or ""),
        "target_count": int(target_set.get("target_count") or 0),
        "expected_target_ids": sorted(expected_by_id),
        "manifest_target_ids": sorted(seen_ids),
        "targets": target_results,
    }


def _execution_policy_summary(manifest: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    policy = manifest.get("execution_policy") if isinstance(manifest.get("execution_policy"), dict) else {}
    expected = {
        "deterministic_gate_allowed_without_network": True,
        "default_public_network_allowed": False,
        "default_browser_runtime_allowed": False,
        "real_public_replay_requires_explicit_opt_in": True,
        "live_public_replay_default_status": "not_closed_missing_real_evidence",
        "closure_without_real_public_evidence_allowed": False,
        "http_fetch_fallback_allowed_for_high_js": False,
    }
    _require(isinstance(manifest.get("execution_policy"), dict), errors, "manifest.execution_policy must be an object")
    for key, value in expected.items():
        _require(policy.get(key) == value, errors, f"execution_policy.{key} must be {value!r}")
    return {key: policy.get(key) for key in expected}


def _opt_in_schema_summary(manifest: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    schema = manifest.get("operator_opt_in_schema") if isinstance(manifest.get("operator_opt_in_schema"), dict) else {}
    true_fields = _as_string_list(schema.get("required_true_fields"))
    string_fields = _as_string_list(schema.get("required_string_fields"))
    list_fields = _as_string_list(schema.get("required_list_fields"))

    _require(isinstance(manifest.get("operator_opt_in_schema"), dict), errors, "operator_opt_in_schema must be an object")
    _require(schema.get("contract_version") == OPT_IN_CONTRACT_VERSION, errors, "operator_opt_in_schema contract mismatch")
    _require(set(true_fields) == set(REQUIRED_TRUE_FIELDS), errors, "operator_opt_in_schema.required_true_fields mismatch")
    _require(
        set(string_fields) == set(REQUIRED_STRING_FIELDS),
        errors,
        "operator_opt_in_schema.required_string_fields mismatch",
    )
    _require(set(list_fields) == set(REQUIRED_LIST_FIELDS), errors, "operator_opt_in_schema.required_list_fields mismatch")
    _require(
        schema.get("target_ids_must_match_manifest") is True,
        errors,
        "operator_opt_in_schema.target_ids_must_match_manifest must be true",
    )
    _require(
        schema.get("evidence_output_contract_version") == PUBLIC_REPLAY_CONTRACT_VERSION,
        errors,
        "operator_opt_in_schema.evidence_output_contract_version mismatch",
    )
    return {
        "contract_version": str(schema.get("contract_version") or ""),
        "required_true_fields": true_fields,
        "required_string_fields": string_fields,
        "required_list_fields": list_fields,
        "target_ids_must_match_manifest": schema.get("target_ids_must_match_manifest") is True,
        "evidence_output_contract_version": str(schema.get("evidence_output_contract_version") or ""),
    }


def _real_evidence_summary(manifest: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    raw = _as_string_list(manifest.get("real_evidence_requires"))
    missing = [item for item in REQUIRED_REAL_EVIDENCE if item not in raw]
    _require(not missing, errors, f"real_evidence_requires missing entries: {missing}")
    return {
        "required_entries": REQUIRED_REAL_EVIDENCE,
        "manifest_entries": raw,
        "complete": not missing,
    }


def _protected_indexes_summary(manifest: Mapping[str, Any], errors: list[str]) -> list[str]:
    raw = _as_string_list(manifest.get("protected_shared_indexes"))
    _require(
        set(raw) == set(PROTECTED_SHARED_INDEXES),
        errors,
        "protected_shared_indexes must match the Wave13/Wave15 protected shared indexes",
    )
    return raw


def _opt_in_request_payload(
    root: Path,
    opt_in_request: Mapping[str, Any] | str | Path | None,
    errors: list[str],
) -> dict[str, Any] | None:
    if opt_in_request is None:
        return None
    if isinstance(opt_in_request, Mapping):
        return dict(opt_in_request)
    return _load_json_file(_resolve_path(root, opt_in_request), errors, "operator opt-in request")


def _opt_in_request_summary(
    root: Path,
    manifest: Mapping[str, Any],
    target_summary: Mapping[str, Any],
    opt_in_request: Mapping[str, Any] | str | Path | None,
    errors: list[str],
) -> dict[str, Any]:
    payload = _opt_in_request_payload(root, opt_in_request, errors)
    if payload is None:
        return {
            "status": "not_provided",
            "valid": False,
            "public_replay_execution_allowed": False,
            "public_network_attempted": False,
        }

    schema = manifest.get("operator_opt_in_schema") if isinstance(manifest.get("operator_opt_in_schema"), dict) else {}
    artifacts = manifest.get("required_artifacts") if isinstance(manifest.get("required_artifacts"), dict) else {}
    expected_target_ids = set(target_summary.get("expected_target_ids") or [])
    request_target_ids = set(_as_string_list(payload.get("target_ids")))

    request_errors: list[str] = []
    _require(payload.get("contract_version") == schema.get("contract_version"), request_errors, "opt-in contract_version mismatch")
    for field in _as_string_list(schema.get("required_true_fields")):
        _require(payload.get(field) is True, request_errors, f"opt-in field {field} must be true")
    for field in _as_string_list(schema.get("required_string_fields")):
        _require(
            isinstance(payload.get(field), str) and bool(str(payload.get(field) or "").strip()),
            request_errors,
            f"opt-in field {field} must be a non-empty string",
        )
    for field in _as_string_list(schema.get("required_list_fields")):
        _require(_as_string_list(payload.get(field)) == list(payload.get(field) or []), request_errors, f"opt-in field {field} must be a string list")
    _require(
        request_target_ids == expected_target_ids,
        request_errors,
        "opt-in target_ids must match the high-JS replay manifest targets",
    )
    _require(
        payload.get("evidence_output") == artifacts.get("live_public_output"),
        request_errors,
        "opt-in evidence_output must match manifest.required_artifacts.live_public_output",
    )
    _require(
        payload.get("output_contract_version") == PUBLIC_REPLAY_CONTRACT_VERSION,
        request_errors,
        "opt-in output_contract_version mismatch",
    )

    errors.extend(request_errors)
    valid = not request_errors
    return {
        "status": "valid_ready_for_public_replay" if valid else "invalid",
        "valid": valid,
        "public_replay_execution_allowed": valid,
        "public_network_attempted": False,
        "target_ids": sorted(request_target_ids),
        "errors": request_errors,
    }


def build_check(
    repo_root: Path | str | None = None,
    manifest_path: Path | str | None = None,
    opt_in_request: Mapping[str, Any] | str | Path | None = None,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    manifest_rel = Path(manifest_path) if manifest_path is not None else DEFAULT_MANIFEST_PATH
    manifest_abs = manifest_rel if manifest_rel.is_absolute() else root / manifest_rel
    manifest_abs = manifest_abs.resolve()
    errors: list[str] = []

    manifest = _load_json_file(manifest_abs, errors, "replay manifest")
    _require(
        manifest.get("contract_version") == MANIFEST_CONTRACT_VERSION,
        errors,
        f"manifest contract_version must be {MANIFEST_CONTRACT_VERSION}",
    )
    _require(isinstance(manifest.get("scope"), str) and bool(manifest.get("scope", "").strip()), errors, "manifest.scope is required")
    _require(
        manifest.get("readiness_contract_version") == READINESS_CONTRACT_VERSION,
        errors,
        "manifest.readiness_contract_version mismatch",
    )
    _require(
        manifest.get("public_replay_contract_version") == PUBLIC_REPLAY_CONTRACT_VERSION,
        errors,
        "manifest.public_replay_contract_version mismatch",
    )

    artifacts = _artifact_summary(root, manifest_abs, manifest, errors)
    targets = _target_summary(manifest, errors)
    execution_policy = _execution_policy_summary(manifest, errors)
    opt_in_schema = _opt_in_schema_summary(manifest, errors)
    real_evidence = _real_evidence_summary(manifest, errors)
    protected_indexes = _protected_indexes_summary(manifest, errors)
    opt_in = _opt_in_request_summary(root, manifest, targets, opt_in_request, errors)

    validation_passed = not errors
    live_output_present = bool(artifacts.get("live_public_output_present"))
    status = "manifest_valid_real_public_replay_not_closed"
    if opt_in.get("valid"):
        status = "manifest_valid_opt_in_request_valid"
    if not validation_passed:
        status = "failed"

    return {
        "contract_version": CONTRACT_VERSION,
        "manifest_contract_version": MANIFEST_CONTRACT_VERSION,
        "repo_root": str(root),
        "manifest_path": _relative_path(manifest_abs, root),
        "status": status,
        "scope": "llm_crawler_high_js_public_replay_manifest_boundary",
        "artifacts": artifacts,
        "target_set": targets,
        "execution_policy": execution_policy,
        "operator_opt_in_schema": opt_in_schema,
        "operator_opt_in_request": opt_in,
        "real_evidence_requires": real_evidence,
        "closure": {
            "manifest_valid": validation_passed,
            "operator_opt_in_valid": bool(opt_in.get("valid")),
            "real_public_high_js_replay_complete": False,
            "live_public_output_present": live_output_present,
            "full_closure_allowed": False,
            "claim": (
                "operator_opt_in_ready_but_real_public_replay_not_executed"
                if opt_in.get("valid")
                else "manifest_schema_valid_not_public_high_js_replay_complete"
            ),
        },
        "validation": {
            "passed": validation_passed,
            "errors": errors,
            "public_network_attempted": False,
            "browser_runtime_started": False,
            "shared_indexes_edited": False,
            "protected_shared_indexes": protected_indexes,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the LLM crawler high-JS public replay manifest and explicit opt-in schema."
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--opt-in-request", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build_check(args.repo_root, args.manifest, args.opt_in_request)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
