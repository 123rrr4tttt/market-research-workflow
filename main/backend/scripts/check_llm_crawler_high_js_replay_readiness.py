from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ingest import url_pool as url_pool_module
from scripts.check_crawler_provider_handoff_contract import build_check as build_provider_handoff_check


CONTRACT_VERSION = "llm_crawler.high_js_replay_readiness.v1"
PUBLIC_REPLAY_CONTRACT_VERSION = "llm_crawler.high_js_public_replay.v1"
TOPIC_DIR = Path(
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
    "2026-03-08-llm-crawler-unified-frontdoor"
)
WAVE13_DOC = TOPIC_DIR / "06_wave13-high-js-public-replay-readiness-2026-05-22.md"
DEFAULT_PUBLIC_ARTIFACT = Path(
    "development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/"
    "2026-05-22/output.public.json"
)

PROTECTED_SHARED_INDEXES = [
    "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md",
    "development/latest-dev-docs/development-plans/INDEX.md",
    "development/latest-dev-docs/README.md",
    "development/latest-dev-docs/MERGED_OVERVIEW.md",
]

DEFAULT_HIGH_JS_TARGETS = [
    {
        "target_id": "x_search_robotics",
        "url": "https://x.com/search?q=robotics",
        "expected_domain": "x.com",
        "public_replay_role": "public_high_js_probe",
        "external_blocker_accept_statuses": ["auth_or_anti_bot_blocked"],
    },
    {
        "target_id": "instagram_tag_robotics",
        "url": "https://www.instagram.com/explore/tags/robotics/",
        "expected_domain": "instagram.com",
        "public_replay_role": "public_high_js_probe",
        "external_blocker_accept_statuses": ["auth_or_anti_bot_blocked"],
    },
    {
        "target_id": "youtube_search_robotics",
        "url": "https://www.youtube.com/results?search_query=robotics",
        "expected_domain": "youtube.com",
        "public_replay_role": "public_high_js_probe",
        "external_blocker_accept_statuses": ["auth_or_anti_bot_blocked"],
    },
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def _load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"invalid public replay artifact json: {path}: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"public replay artifact must be a JSON object: {path}")
        return {}
    return payload


def _target_profile_summary(target: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    target_id = str(target.get("target_id") or "").strip()
    url = str(target.get("url") or "").strip()
    expected_domain = str(target.get("expected_domain") or "").strip()
    profile = url_pool_module._frontdoor_route_profile_for_url(url)
    router_contract = profile.get("router_contract") if isinstance(profile.get("router_contract"), dict) else {}
    fallback_boundary = (
        router_contract.get("fallback_boundary") if isinstance(router_contract.get("fallback_boundary"), dict) else {}
    )

    _require(profile.get("contract_version") == "ingest.frontdoor_route_profile.v1", errors, f"{target_id}: route profile contract drifted")
    _require(profile.get("domain") == expected_domain, errors, f"{target_id}: expected domain {expected_domain!r}")
    _require(profile.get("route_hint") == "crawler_browse", errors, f"{target_id}: route_hint must be crawler_browse")
    _require(profile.get("fetch_strategy") == "browser_render", errors, f"{target_id}: fetch_strategy must be browser_render")
    _require(bool(profile.get("high_js")), errors, f"{target_id}: high_js must be true")
    _require(bool(profile.get("render_required")), errors, f"{target_id}: render_required must be true")
    _require(router_contract.get("contract_version") == "ingest.frontdoor_fetch_router.v1", errors, f"{target_id}: router contract missing")
    _require(router_contract.get("router_state") == "needs_browser", errors, f"{target_id}: router_state must be needs_browser")
    _require(router_contract.get("reason_code") == "needs_browser_runtime", errors, f"{target_id}: reason_code must be needs_browser_runtime")
    _require(bool(fallback_boundary.get("browser_fetch_required")), errors, f"{target_id}: browser fetch must be required")
    _require(bool(fallback_boundary.get("crawler_provider_allowed")), errors, f"{target_id}: crawler provider must be allowed")
    _require(
        fallback_boundary.get("http_fetch_fallback_allowed") is False,
        errors,
        f"{target_id}: http fallback must stay disabled for high-JS routes",
    )
    _require(
        fallback_boundary.get("public_browser_replay_performed") is False,
        errors,
        f"{target_id}: deterministic route profile must not claim public browser replay",
    )

    return {
        "target_id": target_id,
        "url": url,
        "domain": profile.get("domain"),
        "route_hint": profile.get("route_hint"),
        "fetch_strategy": profile.get("fetch_strategy"),
        "high_js": bool(profile.get("high_js")),
        "render_required": bool(profile.get("render_required")),
        "router_contract": {
            "contract_version": router_contract.get("contract_version"),
            "router_state": router_contract.get("router_state"),
            "dashboard_status": router_contract.get("dashboard_status"),
            "reason_code": router_contract.get("reason_code"),
            "public_browser_replay_performed": fallback_boundary.get("public_browser_replay_performed"),
            "http_fetch_fallback_allowed": fallback_boundary.get("http_fetch_fallback_allowed"),
            "browser_fetch_required": fallback_boundary.get("browser_fetch_required"),
            "crawler_provider_allowed": fallback_boundary.get("crawler_provider_allowed"),
        },
    }


def _provider_handoff_summary(errors: list[str]) -> dict[str, Any]:
    result = build_provider_handoff_check()
    assertions = result.get("assertions") if isinstance(result.get("assertions"), dict) else {}
    _require(result.get("status") == "passed", errors, "crawler provider handoff checker must pass")
    _require(
        all(bool(value) for value in assertions.values()),
        errors,
        "crawler provider handoff assertions must all pass",
    )
    return {
        "contract_version": result.get("contract_version"),
        "status": result.get("status"),
        "assertions": assertions,
        "fixture_target": "https://x.com/search?q=robotics",
        "public_network_attempted": False,
    }


def _resolve_public_artifact_path(root: Path, public_artifact: Path | str | None) -> Path:
    raw = Path(public_artifact) if public_artifact is not None else DEFAULT_PUBLIC_ARTIFACT
    return raw if raw.is_absolute() else root / raw


def _target_results_successful(payload: dict[str, Any]) -> bool:
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    target_results = outputs.get("target_results")
    if not isinstance(target_results, list) or not target_results:
        return False
    for item in target_results:
        if not isinstance(item, dict):
            return False
        if str(item.get("status") or "").strip().lower() != "success":
            return False
        if item.get("browser_rendered") is not True:
            return False
    return True


def _result_by_target_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    target_results = outputs.get("target_results")
    if not isinstance(target_results, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in target_results:
        if isinstance(item, dict):
            target_id = str(item.get("target_id") or "").strip()
            if target_id:
                result[target_id] = item
    return result


def _target_result_successful(item: dict[str, Any] | None) -> bool:
    if not isinstance(item, dict):
        return False
    return str(item.get("status") or "").strip().lower() == "success" and item.get("browser_rendered") is True


def _external_gate_result_proven(target: dict[str, Any], item: dict[str, Any] | None) -> bool:
    if not isinstance(item, dict):
        return False
    allowed_statuses = {
        str(status).strip().lower()
        for status in target.get("external_blocker_accept_statuses", [])
        if str(status).strip()
    }
    status = str(item.get("status") or "").strip().lower()
    markers = item.get("markers") if isinstance(item.get("markers"), dict) else {}
    auth_or_anti_bot_marker = bool(markers.get("contains_login") or markers.get("contains_captcha"))
    return bool(
        status in allowed_statuses
        and item.get("browser_rendered") is True
        and item.get("public_network_attempted") is True
        and auth_or_anti_bot_marker
    )


def _public_artifact_summary(root: Path, public_artifact: Path | str | None, errors: list[str]) -> dict[str, Any]:
    artifact_path = _resolve_public_artifact_path(root, public_artifact)
    relative_path = str(artifact_path.relative_to(root)) if artifact_path.is_relative_to(root) else str(artifact_path)
    if not artifact_path.is_file():
        return {
            "status": "absent_blocked",
            "path": relative_path,
            "contract_version": PUBLIC_REPLAY_CONTRACT_VERSION,
            "public_network_attempted": False,
            "real_public_high_js_replay_proven": False,
            "full_closure_allowed": False,
            "blocker_type": "external_public_high_js_replay_not_proven",
            "reason": (
                "No real public high-JS replay artifact is present. Deterministic route and handoff fixtures "
                "are readiness evidence only."
            ),
        }

    payload = _load_json(artifact_path, errors)
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    attempted = int(outputs.get("public_targets_attempted") or 0)
    target_count = int(inputs.get("target_count") or 0)
    success_count = int(outputs.get("high_js_success_count") or 0)
    explicit_proof = validation.get("real_public_high_js_replay_proven") is True
    public_network_attempted = validation.get("public_network_attempted") is True
    sufficient_targets = target_count >= len(DEFAULT_HIGH_JS_TARGETS) and attempted >= target_count
    all_targets_successful = success_count >= target_count and _target_results_successful(payload)
    contract_version_ok = payload.get("contract_version") == PUBLIC_REPLAY_CONTRACT_VERSION
    by_target_id = _result_by_target_id(payload)
    public_probe_targets = list(DEFAULT_HIGH_JS_TARGETS)
    successful_accessible_targets = [
        target
        for target in public_probe_targets
        if _target_result_successful(by_target_id.get(str(target.get("target_id") or "")))
    ]
    gate_blocked_targets = [
        target
        for target in public_probe_targets
        if not _target_result_successful(by_target_id.get(str(target.get("target_id") or "")))
        and _external_gate_result_proven(target, by_target_id.get(str(target.get("target_id") or "")))
    ]
    all_probe_targets_accounted_for = len(successful_accessible_targets) + len(gate_blocked_targets) == len(public_probe_targets)
    accessible_targets_successful = bool(successful_accessible_targets) and all_probe_targets_accounted_for
    external_gate_blockers_proven = bool(gate_blocked_targets) and all_probe_targets_accounted_for
    accessible_replay_proven = bool(
        contract_version_ok
        and public_network_attempted
        and sufficient_targets
        and accessible_targets_successful
    )
    proven = bool(
        contract_version_ok
        and explicit_proof
        and public_network_attempted
        and sufficient_targets
        and all_targets_successful
    )
    remaining_external_blockers = []
    for target in gate_blocked_targets:
        target_id = str(target.get("target_id") or "")
        item = by_target_id.get(target_id, {})
        remaining_external_blockers.append(
            {
                "target_id": target_id,
                "url": target.get("url"),
                "status": item.get("status"),
                "reason": item.get("reason"),
                "markers": item.get("markers") if isinstance(item.get("markers"), dict) else {},
                "classification": "intrinsic_external_auth_or_anti_bot_gate",
            }
        )

    if not proven and not (accessible_replay_proven and external_gate_blockers_proven):
        errors.append(
            "public replay artifact is present but does not prove real public high-JS replay completion"
        )

    return {
        "status": (
            "proven"
            if proven
            else (
                "accessible_replay_proven_external_targets_blocked"
                if accessible_replay_proven and external_gate_blockers_proven
                else "present_not_proven"
            )
        ),
        "path": relative_path,
        "contract_version": payload.get("contract_version"),
        "public_network_attempted": public_network_attempted,
        "real_public_high_js_replay_proven": proven,
        "accessible_public_high_js_replay_proven": accessible_replay_proven,
        "external_gate_blockers_proven": external_gate_blockers_proven,
        "full_closure_allowed": proven,
        "target_count": target_count,
        "public_targets_attempted": attempted,
        "high_js_success_count": success_count,
        "public_high_js_probe_target_ids": [target["target_id"] for target in public_probe_targets],
        "successful_accessible_target_ids": [target["target_id"] for target in successful_accessible_targets],
        "external_gate_target_ids": [target["target_id"] for target in gate_blocked_targets],
        "remaining_external_blockers": remaining_external_blockers,
        "blocker_type": (
            None
            if proven
            else (
                "intrinsic_external_auth_or_anti_bot_gate"
                if accessible_replay_proven and external_gate_blockers_proven
                else "public_artifact_present_but_not_proven"
            )
        ),
        "requirements": {
            "contract_version_ok": contract_version_ok,
            "explicit_proof": explicit_proof,
            "public_network_attempted": public_network_attempted,
            "sufficient_targets": sufficient_targets,
            "all_targets_successful": all_targets_successful,
            "all_probe_targets_accounted_for": all_probe_targets_accounted_for,
            "accessible_targets_successful": accessible_targets_successful,
            "external_gate_blockers_proven": external_gate_blockers_proven,
        },
    }


def build_check(
    repo_root: Path | str | None = None,
    public_artifact: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    errors: list[str] = []

    target_profiles = [_target_profile_summary(target, errors) for target in DEFAULT_HIGH_JS_TARGETS]
    provider_handoff = _provider_handoff_summary(errors)
    public_replay = _public_artifact_summary(root, public_artifact, errors)

    deterministic_fixture_ready = not errors or (
        len(errors) == 1
        and errors[0] == "public replay artifact is present but does not prove real public high-JS replay completion"
    )
    public_proven = bool(public_replay.get("real_public_high_js_replay_proven"))
    accessible_public_proven = bool(public_replay.get("accessible_public_high_js_replay_proven"))
    external_gate_blockers_proven = bool(public_replay.get("external_gate_blockers_proven"))
    full_closure_allowed = bool(deterministic_fixture_ready and public_proven)

    if errors and public_replay.get("status") == "present_not_proven":
        status = "public_replay_artifact_not_proven"
    elif errors:
        status = "failed"
    elif full_closure_allowed:
        status = "real_public_high_js_replay_proven"
    elif deterministic_fixture_ready and accessible_public_proven and external_gate_blockers_proven:
        status = "accessible_public_high_js_replay_proven_external_targets_blocked"
    else:
        status = "fixture_ready_real_public_replay_blocked"

    return {
        "contract_version": CONTRACT_VERSION,
        "repo_root": str(root),
        "status": status,
        "scope": "llm_crawler_unified_frontdoor_high_js_public_replay_boundary",
        "evidence_doc": str(WAVE13_DOC),
        "deterministic_fixture": {
            "ready": deterministic_fixture_ready,
            "target_count": len(target_profiles),
            "target_profiles": target_profiles,
            "provider_handoff": provider_handoff,
        },
        "public_high_js_replay": public_replay,
        "closure": {
            "deterministic_fixture_ready": deterministic_fixture_ready,
            "real_public_high_js_replay_complete": public_proven,
            "accessible_public_high_js_replay_complete": accessible_public_proven,
            "remaining_external_blockers": list(public_replay.get("remaining_external_blockers") or []),
            "full_closure_allowed": full_closure_allowed,
            "claim": (
                "real_public_high_js_replay_complete"
                if full_closure_allowed
                else (
                    "accessible_public_high_js_replay_complete_external_targets_blocked"
                    if accessible_public_proven and external_gate_blockers_proven
                    else "deterministic_fixture_ready_not_public_high_js_replay_complete"
                )
            ),
        },
        "validation": {
            "passed": status
            in {
                "fixture_ready_real_public_replay_blocked",
                "accessible_public_high_js_replay_proven_external_targets_blocked",
                "real_public_high_js_replay_proven",
            },
            "errors": errors,
            "public_network_attempted": bool(public_replay.get("public_network_attempted")),
            "shared_indexes_edited": False,
            "protected_shared_indexes": list(PROTECTED_SHARED_INDEXES),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check LLM crawler high-JS deterministic readiness and public replay proof boundary."
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--public-artifact", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build_check(args.repo_root, args.public_artifact)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
