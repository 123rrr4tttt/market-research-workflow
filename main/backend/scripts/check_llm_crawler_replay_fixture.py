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
from scripts.check_llm_crawler_replay_manifest import DEFAULT_MANIFEST_PATH
from scripts.check_llm_crawler_replay_manifest import MANIFEST_CONTRACT_VERSION
from scripts.check_llm_crawler_replay_manifest import build_check as build_manifest_check


CONTRACT_VERSION = "llm_crawler.replay_fixture.check.v1"
FIXTURE_CONTRACT_VERSION = "llm_crawler.browser_replay_fixture.v1"
DECISION_CONTRACT_VERSION = "llm_crawler.browser_replay_decision.v1"
DEFAULT_FIXTURE_PATH = Path(
    "development/latest-dev-docs/automation-runs/llm-crawler-browser-replay-fixture/"
    "2026-05-22/replay.fixture.json"
)

TOPIC_DIR = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-03-08-llm-crawler-unified-frontdoor"
)
WAVE18_DOC = TOPIC_DIR / "08_wave18-browser-replay-fixture-readback-2026-05-22.md"

REQUIRED_RUNTIME_FLAGS = {
    "repo_local_fixture": True,
    "deterministic": True,
    "public_network_attempted": False,
    "browser_runtime_started": False,
    "public_browser_replay_performed": False,
    "real_public_replay_claimed": False,
}

REQUIRED_MANIFEST_SHAPE = {
    "high_js": True,
    "public_site": True,
    "render_required": True,
    "route_hint": "crawler_browse",
    "fetch_strategy": "browser_render",
    "public_replay_opt_in_required": True,
    "http_fetch_fallback_allowed": False,
}

REQUIRED_DECISION_PATH = {
    "route_hint": "crawler_browse",
    "fetch_strategy": "browser_render",
    "router_state": "needs_browser",
    "reason_code": "needs_browser_runtime",
    "browser_fetch_required": True,
    "http_fetch_fallback_allowed": False,
    "public_browser_replay_performed": False,
}


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


def _manifest_targets_by_id(manifest: Mapping[str, Any], errors: list[str]) -> dict[str, dict[str, Any]]:
    target_set = manifest.get("target_set") if isinstance(manifest.get("target_set"), Mapping) else {}
    targets = target_set.get("targets") if isinstance(target_set.get("targets"), list) else []
    result: dict[str, dict[str, Any]] = {}
    _require(target_set.get("target_kind") == "high_js_public_replay", errors, "manifest target_kind mismatch")
    _require(isinstance(targets, list) and bool(targets), errors, "manifest target_set.targets must be a non-empty list")
    for raw_target in targets:
        if not isinstance(raw_target, Mapping):
            errors.append("manifest target must be an object")
            continue
        target = dict(raw_target)
        target_id = str(target.get("target_id") or "").strip()
        _require(bool(target_id), errors, "manifest target_id is required")
        if target_id:
            result[target_id] = target
    _require(target_set.get("target_count") == len(result), errors, "manifest target_count must match unique targets")
    return result


def _runtime_summary(fixture: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    runtime = fixture.get("runtime") if isinstance(fixture.get("runtime"), Mapping) else {}
    _require(isinstance(fixture.get("runtime"), Mapping), errors, "fixture.runtime must be an object")
    for key, expected in REQUIRED_RUNTIME_FLAGS.items():
        _require(runtime.get(key) is expected, errors, f"fixture.runtime.{key} must be {expected!r}")
    _require(
        runtime.get("mode") == "repo_local_browser_replay_fixture",
        errors,
        "fixture.runtime.mode must be repo_local_browser_replay_fixture",
    )
    return {key: runtime.get(key) for key in ["mode", *REQUIRED_RUNTIME_FLAGS.keys()]}


def _manifest_readback_summary(
    *,
    fixture: Mapping[str, Any],
    manifest_path: Path,
    manifest_targets: Mapping[str, Mapping[str, Any]],
    root: Path,
    errors: list[str],
) -> dict[str, Any]:
    readback = fixture.get("manifest_readback") if isinstance(fixture.get("manifest_readback"), Mapping) else {}
    manifest_target_ids = sorted(manifest_targets)
    readback_target_ids = sorted(_as_string_list(readback.get("target_ids")))

    _require(isinstance(fixture.get("manifest_readback"), Mapping), errors, "fixture.manifest_readback must be an object")
    _require(readback.get("manifest_contract_version") == MANIFEST_CONTRACT_VERSION, errors, "manifest_readback contract mismatch")
    _require(
        readback.get("manifest_path") == _relative_path(manifest_path, root),
        errors,
        "manifest_readback.manifest_path must point to the checked manifest",
    )
    _require(readback.get("target_count") == len(manifest_targets), errors, "manifest_readback.target_count mismatch")
    _require(readback_target_ids == manifest_target_ids, errors, "manifest_readback.target_ids mismatch")
    _require(
        readback.get("shape_checked") == sorted(REQUIRED_MANIFEST_SHAPE),
        errors,
        "manifest_readback.shape_checked must list the required manifest target shape",
    )

    return {
        "manifest_path": readback.get("manifest_path"),
        "manifest_contract_version": readback.get("manifest_contract_version"),
        "target_count": readback.get("target_count"),
        "target_ids": readback_target_ids,
        "shape_checked": readback.get("shape_checked"),
    }


def _decision_contract_summary(fixture: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    decision = (
        fixture.get("browser_decision_path")
        if isinstance(fixture.get("browser_decision_path"), Mapping)
        else {}
    )
    _require(isinstance(fixture.get("browser_decision_path"), Mapping), errors, "browser_decision_path must be an object")
    _require(
        decision.get("contract_version") == DECISION_CONTRACT_VERSION,
        errors,
        "browser_decision_path contract mismatch",
    )
    for key, expected in REQUIRED_DECISION_PATH.items():
        _require(decision.get(key) == expected, errors, f"browser_decision_path.{key} must be {expected!r}")
    return {
        "contract_version": decision.get("contract_version"),
        **{key: decision.get(key) for key in REQUIRED_DECISION_PATH},
    }


def _target_summary(
    *,
    fixture: Mapping[str, Any],
    manifest_targets: Mapping[str, Mapping[str, Any]],
    errors: list[str],
) -> dict[str, Any]:
    raw_results = fixture.get("target_results")
    results = raw_results if isinstance(raw_results, list) else []
    seen_ids: set[str] = set()
    target_summaries: list[dict[str, Any]] = []
    _require(isinstance(raw_results, list) and bool(raw_results), errors, "fixture.target_results must be a non-empty list")

    for raw_result in results:
        result = raw_result if isinstance(raw_result, Mapping) else {}
        target_id = str(result.get("target_id") or "").strip()
        seen_ids.add(target_id)
        manifest_target = manifest_targets.get(target_id)
        if manifest_target is None:
            errors.append(f"unexpected fixture target_id: {target_id!r}")
            continue

        url = str(result.get("url") or "").strip()
        expected_domain = str(result.get("expected_domain") or "").strip()
        manifest_shape = result.get("manifest_shape") if isinstance(result.get("manifest_shape"), Mapping) else {}
        fixture_decision = (
            result.get("frontdoor_decision")
            if isinstance(result.get("frontdoor_decision"), Mapping)
            else {}
        )
        fixture_replay = result.get("fixture_replay") if isinstance(result.get("fixture_replay"), Mapping) else {}
        profile = url_pool_module._frontdoor_route_profile_for_url(url)
        router_contract = profile.get("router_contract") if isinstance(profile.get("router_contract"), Mapping) else {}
        fallback = (
            router_contract.get("fallback_boundary")
            if isinstance(router_contract.get("fallback_boundary"), Mapping)
            else {}
        )

        _require(url == manifest_target.get("url"), errors, f"{target_id}: url must match manifest")
        _require(expected_domain == manifest_target.get("expected_domain"), errors, f"{target_id}: expected_domain must match manifest")
        for key, expected in REQUIRED_MANIFEST_SHAPE.items():
            _require(manifest_target.get(key) == expected, errors, f"{target_id}: manifest {key} must be {expected!r}")
            _require(manifest_shape.get(key) == expected, errors, f"{target_id}: fixture manifest_shape.{key} must be {expected!r}")

        actual_decision = {
            "route_profile_contract_version": profile.get("contract_version"),
            "router_contract_version": router_contract.get("contract_version"),
            "domain": profile.get("domain"),
            "route_hint": profile.get("route_hint"),
            "fetch_strategy": profile.get("fetch_strategy"),
            "high_js": profile.get("high_js") is True,
            "render_required": profile.get("render_required") is True,
            "router_state": router_contract.get("router_state"),
            "reason_code": router_contract.get("reason_code"),
            "browser_fetch_required": fallback.get("browser_fetch_required"),
            "crawler_provider_allowed": fallback.get("crawler_provider_allowed"),
            "http_fetch_fallback_allowed": fallback.get("http_fetch_fallback_allowed"),
            "public_browser_replay_performed": fallback.get("public_browser_replay_performed"),
        }
        for key, actual in actual_decision.items():
            _require(fixture_decision.get(key) == actual, errors, f"{target_id}: frontdoor_decision.{key} drifted")
        for key, expected in REQUIRED_DECISION_PATH.items():
            _require(actual_decision.get(key) == expected, errors, f"{target_id}: route decision {key} must be {expected!r}")

        _require(
            fixture_replay.get("status") == "decision_path_replayed",
            errors,
            f"{target_id}: fixture_replay.status must be decision_path_replayed",
        )
        _require(
            fixture_replay.get("browser_render_decision_proven") is True,
            errors,
            f"{target_id}: browser_render_decision_proven must be true",
        )
        _require(
            fixture_replay.get("repo_local_snapshot_present") is True,
            errors,
            f"{target_id}: repo_local_snapshot_present must be true",
        )
        _require(
            fixture_replay.get("public_network_attempted") is False,
            errors,
            f"{target_id}: public_network_attempted must be false",
        )
        _require(
            fixture_replay.get("browser_runtime_started") is False,
            errors,
            f"{target_id}: browser_runtime_started must be false",
        )
        _require(
            fixture_replay.get("real_public_replay_claimed") is False,
            errors,
            f"{target_id}: real_public_replay_claimed must be false",
        )

        target_summaries.append(
            {
                "target_id": target_id,
                "url": url,
                "expected_domain": expected_domain,
                "route_hint": actual_decision["route_hint"],
                "fetch_strategy": actual_decision["fetch_strategy"],
                "router_state": actual_decision["router_state"],
                "reason_code": actual_decision["reason_code"],
                "browser_render_decision_proven": fixture_replay.get("browser_render_decision_proven") is True,
                "public_network_attempted": fixture_replay.get("public_network_attempted") is True,
            }
        )

    missing_ids = sorted(set(manifest_targets) - seen_ids)
    extra_ids = sorted(seen_ids - set(manifest_targets))
    _require(not missing_ids, errors, f"fixture.target_results missing target_ids: {missing_ids}")
    _require(not extra_ids, errors, f"fixture.target_results has unexpected target_ids: {extra_ids}")
    return {
        "target_count": len(target_summaries),
        "manifest_target_ids": sorted(manifest_targets),
        "fixture_target_ids": sorted(seen_ids),
        "targets": target_summaries,
    }


def build_check(
    repo_root: Path | str | None = None,
    manifest_path: Path | str | None = None,
    fixture_path: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    manifest_rel = Path(manifest_path) if manifest_path is not None else DEFAULT_MANIFEST_PATH
    fixture_rel = Path(fixture_path) if fixture_path is not None else DEFAULT_FIXTURE_PATH
    manifest_abs = _resolve_path(root, manifest_rel).resolve()
    fixture_abs = _resolve_path(root, fixture_rel).resolve()
    errors: list[str] = []

    manifest_check = build_manifest_check(root, manifest_rel)
    _require(manifest_check.get("validation", {}).get("passed") is True, errors, "manifest readback checker must pass")
    _require(
        manifest_check.get("closure", {}).get("real_public_high_js_replay_complete") is False,
        errors,
        "manifest checker must not claim real public replay completion",
    )

    manifest = _load_json_file(manifest_abs, errors, "replay manifest")
    fixture = _load_json_file(fixture_abs, errors, "browser replay fixture")
    _require(fixture.get("contract_version") == FIXTURE_CONTRACT_VERSION, errors, "fixture contract_version mismatch")
    _require(
        fixture.get("scope") == "llm_crawler_high_js_browser_replay_manifest_readback",
        errors,
        "fixture.scope mismatch",
    )

    manifest_targets = _manifest_targets_by_id(manifest, errors)
    runtime = _runtime_summary(fixture, errors)
    manifest_readback = _manifest_readback_summary(
        fixture=fixture,
        manifest_path=manifest_abs,
        manifest_targets=manifest_targets,
        root=root,
        errors=errors,
    )
    browser_decision_path = _decision_contract_summary(fixture, errors)
    targets = _target_summary(fixture=fixture, manifest_targets=manifest_targets, errors=errors)

    validation_passed = not errors
    status = "fixture_replay_passed_public_replay_not_closed" if validation_passed else "failed"
    return {
        "contract_version": CONTRACT_VERSION,
        "fixture_contract_version": FIXTURE_CONTRACT_VERSION,
        "repo_root": str(root),
        "manifest_path": _relative_path(manifest_abs, root),
        "fixture_path": _relative_path(fixture_abs, root),
        "status": status,
        "scope": "llm_crawler_unified_frontdoor_browser_replay_fixture",
        "evidence_doc": str(WAVE18_DOC),
        "manifest_gate": {
            "contract_version": manifest_check.get("contract_version"),
            "status": manifest_check.get("status"),
            "passed": bool(manifest_check.get("validation", {}).get("passed")),
            "real_public_high_js_replay_complete": bool(
                manifest_check.get("closure", {}).get("real_public_high_js_replay_complete")
            ),
        },
        "runtime": runtime,
        "manifest_readback": manifest_readback,
        "browser_decision_path": browser_decision_path,
        "target_results": targets,
        "closure": {
            "manifest_readback_valid": validation_passed,
            "browser_high_js_decision_path_valid": validation_passed,
            "repo_local_fixture_replay_complete": validation_passed,
            "real_public_high_js_replay_complete": False,
            "full_closure_allowed": False,
            "claim": (
                "repo_local_browser_replay_fixture_passed_real_public_replay_not_closed"
                if validation_passed
                else "repo_local_browser_replay_fixture_failed"
            ),
        },
        "validation": {
            "passed": validation_passed,
            "errors": errors,
            "public_network_attempted": False,
            "browser_runtime_started": False,
            "shared_indexes_edited": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate repo-local LLM crawler high-JS browser replay fixture and manifest readback."
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build_check(args.repo_root, args.manifest, args.fixture)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
