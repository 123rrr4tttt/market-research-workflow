#!/usr/bin/env python3
"""Check Single URL First Ingest Allocation external-blocker reduction."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
SCRIPT_DIR = BACKEND_ROOT / "scripts"
for path in (BACKEND_ROOT, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.services.ingest.canary_handoff import CANARY_HANDOFF_CONTRACT_VERSION  # noqa: E402
from app.services.ingest.canary_handoff_live import run_repo_local_production_like_handoff_canary  # noqa: E402
from app.services.ingest.canary_metrics import build_configured_provider_canary_boundary  # noqa: E402
from app.services.ingest.canary_strict_promotion import (  # noqa: E402
    OPS_PROMOTION_EVIDENCE_INVALID_BLOCKER,
    OPS_PROMOTION_BLOCKERS,
    OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION,
    PRODUCTION_24H_EVIDENCE_INVALID_BLOCKER,
    PRODUCTION_24H_BLOCKERS,
    PRODUCTION_24H_METRICS_CONTRACT_VERSION,
    build_strict_promotion_readiness,
    validate_strict_promotion_readiness,
)
from check_ingest_canary_24h_metrics_artifact import build_24h_metrics_artifact  # noqa: E402
from check_llm_crawler_high_js_replay_readiness import build_check as build_high_js_replay_check  # noqa: E402
from check_single_url_official_api_provider_maturity import (  # noqa: E402
    PROVIDER_CREDENTIALS_BEYOND_CROSSREF_BLOCKER,
    PROVIDER_CREDENTIALS_CONFIGURED_ONLY_STATUS,
    build_report as build_official_api_report,
)


CONTRACT_VERSION = "single_url.external_blocker_closure.v1"
TOPIC_SLUG = "2026-03-02-single-url-first-ingest-allocation-plan"
TOPIC_DIR = Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED") / TOPIC_SLUG
EVIDENCE_DOC = TOPIC_DIR / "13_wave57-single-url-external-blocker-closure-2026-05-24.md"
DEFAULT_RUN_DIR = Path(
    "development/latest-dev-docs/automation-runs/"
    "single-url-first-ingest-allocation-external-blocker-closure/2026-05-24"
)
DEFAULT_PUBLIC_REPLAY_ARTIFACT = DEFAULT_RUN_DIR / "high_js_public_replay.json"

LiveCanaryRunner = Callable[..., dict[str, Any]]
OfficialApiReportBuilder = Callable[..., dict[str, Any]]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _token_check(path: Path, tokens: tuple[str, ...]) -> dict[str, Any]:
    full_path = REPO_ROOT / path
    exists = full_path.is_file()
    text = _read_text(full_path) if exists else ""
    missing = [token for token in tokens if token not in text]
    return {
        "path": str(path),
        "exists": exists,
        "tokens_checked": list(tokens),
        "missing_tokens": missing,
        "passed": bool(exists and not missing),
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _read_json_artifact(path: Path | None) -> tuple[dict[str, Any] | None, str | None, str | None]:
    if path is None:
        return None, None, None
    full_path = _resolve_path(path)
    try:
        payload = json.loads(full_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, str(full_path), f"{exc.__class__.__name__}: {exc}"
    if not isinstance(payload, dict):
        return None, str(full_path), "artifact JSON must be an object"
    return payload, str(full_path), None


def _configured_provider_live_evidence_from_canary(live_result: Mapping[str, Any]) -> dict[str, Any]:
    evidence = _mapping(live_result.get("evidence"))
    validation = _mapping(live_result.get("validation"))
    validation_checks = _mapping(evidence.get("validation_checks"))
    handoff = _mapping(live_result.get("validated_handoff"))
    frontdoor = _mapping(handoff.get("frontdoor_run"))
    live_passed = (
        live_result.get("status") == "passed"
        and validation.get("passed") is True
        and evidence.get("live_canary_validated") is True
    )
    return {
        "demo_proj_live_canary_validated": live_passed,
        "single_url_frontdoor_run_completed": validation_checks.get("api_runtime_validated") is True,
        "configured_services_used": validation_checks.get("db_readback_validated") is True,
        "canary_handoff_readback_present": bool(handoff),
        "configured_provider": {
            "provider_key": "source_library_frontdoor",
            "config_state": "configured" if live_passed else "failed",
            "runtime": "repo_local_api_db_runtime",
            "live_probe_status": "passed" if live_passed else "failed",
        },
        "frontdoor_run": {
            "project_key": frontdoor.get("project_key") or live_result.get("project_key"),
            "entrypoint": frontdoor.get("entrypoint"),
            "source_mode": frontdoor.get("source_mode"),
            "source_url": frontdoor.get("source_url") or evidence.get("accepted_url"),
        },
        "handoff_readback": handoff,
        "closure_claim": False,
    }


def _public_replay_reduced(public_replay_check: Mapping[str, Any]) -> bool:
    closure = _mapping(public_replay_check.get("closure"))
    return bool(
        closure.get("real_public_high_js_replay_complete") is True
        or closure.get("accessible_public_high_js_replay_complete") is True
    )


def _provider_boundary_reduced(official_api_report: Mapping[str, Any], *, require_live_crossref: bool) -> bool:
    live = _mapping(official_api_report.get("live_crossref"))
    return bool(
        official_api_report.get("status") == "passed"
        and (not require_live_crossref or live.get("status") == "passed")
    )


def _provider_credentials_satisfied(official_api_report: Mapping[str, Any]) -> bool:
    maturity = _mapping(official_api_report.get("non_arxiv_provider_maturity"))
    return maturity.get("provider_credentials_beyond_crossref_satisfied") is True


def _remaining_external_blockers(
    *,
    public_replay_check: Mapping[str, Any],
    strict_promotion_report: Mapping[str, Any],
    official_api_report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    closure = _mapping(public_replay_check.get("closure"))
    for item in closure.get("remaining_external_blockers") or []:
        if isinstance(item, Mapping):
            blockers.append(
                {
                    "id": f"public_high_js_{item.get('target_id') or 'unknown'}",
                    "classification": item.get("classification") or "external_public_runtime",
                    "detail": item.get("reason"),
                }
            )
    remaining_ids = {
        str(item.get("id") or "")
        for item in strict_promotion_report.get("remaining_external_blockers") or []
        if isinstance(item, Mapping)
    }
    for blocker_id in (*PRODUCTION_24H_BLOCKERS, PRODUCTION_24H_EVIDENCE_INVALID_BLOCKER):
        if blocker_id in remaining_ids:
            blockers.append(
                {
                    "id": blocker_id,
                    "classification": "external_live_operational",
                    "detail": (
                        "Production 24h metrics artifact is present but invalid."
                        if blocker_id == PRODUCTION_24H_EVIDENCE_INVALID_BLOCKER
                        else "Production 24h metrics require production live-window readback, not a repo-local fixture."
                    ),
                }
            )
    for blocker_id in (*OPS_PROMOTION_BLOCKERS, OPS_PROMOTION_EVIDENCE_INVALID_BLOCKER):
        if blocker_id in remaining_ids:
            blockers.append(
                {
                    "id": blocker_id,
                    "classification": "external_live_operational",
                    "detail": (
                        "Operations promotion artifact is present but invalid."
                        if blocker_id == OPS_PROMOTION_EVIDENCE_INVALID_BLOCKER
                        else "All-project strict-gate promotion remains operations-owned."
                    ),
                }
            )
    if not _provider_credentials_satisfied(official_api_report):
        provider_boundary = _mapping(
            _mapping(official_api_report.get("non_arxiv_provider_maturity")).get("provider_credentials_boundary")
        )
        configured_only = provider_boundary.get("status") == PROVIDER_CREDENTIALS_CONFIGURED_ONLY_STATUS
        blockers.append(
            {
                "id": PROVIDER_CREDENTIALS_BEYOND_CROSSREF_BLOCKER,
                "classification": "external_provider_account",
                "detail": (
                    "Credentialed provider presence is recorded as configured_only, but live provider-specific quota validation is not authorized or passed."
                    if configured_only
                    else "Only public arXiv/Crossref official APIs are validated; credentialed provider quota beyond Crossref is not configured in repo."
                ),
            }
        )
    return blockers


def build_check(
    *,
    public_replay_artifact: Path | str | None = None,
    project_key: str | None = "single_url_wave57_canary",
    allow_live_crossref: bool = False,
    require_live_crossref: bool = False,
    production_metrics_artifact_path: Path | None = None,
    ops_promotion_artifact_path: Path | None = None,
    provider_credentials_artifact_path: Path | None = None,
    claim_closure: bool = False,
    live_canary_runner: LiveCanaryRunner = run_repo_local_production_like_handoff_canary,
    official_api_report_builder: OfficialApiReportBuilder = build_official_api_report,
) -> dict[str, Any]:
    public_artifact = Path(public_replay_artifact or DEFAULT_PUBLIC_REPLAY_ARTIFACT)
    public_replay_check = build_high_js_replay_check(REPO_ROOT, public_artifact)

    live_result = live_canary_runner(project_key=project_key)
    live_evidence = _mapping(live_result.get("evidence"))
    resolved_project_key = str(live_result.get("project_key") or project_key or "demo_proj")
    configured_provider_evidence = _configured_provider_live_evidence_from_canary(live_result)
    configured_provider_boundary = build_configured_provider_canary_boundary(
        live_canary_evidence=configured_provider_evidence,
        project_key=resolved_project_key,
    )

    deterministic_metrics_artifact = build_24h_metrics_artifact(project_key=resolved_project_key)
    production_metrics_artifact, production_metrics_path, production_metrics_error = _read_json_artifact(
        production_metrics_artifact_path
    )
    ops_promotion_evidence, ops_promotion_path, ops_promotion_error = _read_json_artifact(
        ops_promotion_artifact_path
    )
    metrics_artifact = production_metrics_artifact or deterministic_metrics_artifact
    if production_metrics_artifact_path is not None and production_metrics_artifact is None:
        metrics_artifact = {"_artifact_load_error": production_metrics_error, "contract_version": None}
    if ops_promotion_artifact_path is not None and ops_promotion_evidence is None:
        ops_promotion_evidence = {"_artifact_load_error": ops_promotion_error, "contract_version": None}
    strict_readiness = build_strict_promotion_readiness(
        project_key=resolved_project_key,
        live_canary_evidence=live_evidence,
        metrics_artifact=metrics_artifact,
        ops_promotion_evidence=ops_promotion_evidence,
        closure_claim=claim_closure,
    )
    strict_report = strict_readiness.to_dict()
    strict_validation_errors = validate_strict_promotion_readiness(strict_report)
    official_api_report = official_api_report_builder(
        allow_live_crossref=allow_live_crossref or require_live_crossref,
        require_live_crossref=require_live_crossref,
        provider_credentials_artifact=provider_credentials_artifact_path,
    )

    token_results = [
        _token_check(
            Path("main/backend/app/services/ingest/canary_metrics.py"),
            (
                "_SINGLE_URL_FRONTDOOR_ENTRYPOINTS",
                "ingest.url.single",
                "frontdoor_entrypoint_is_single_url_frontdoor",
            ),
        ),
        _token_check(
            Path("main/backend/scripts/check_single_url_external_blocker_closure.py"),
            (
                "single_url.external_blocker_closure.v1",
                "build_high_js_replay_check",
                "run_repo_local_production_like_handoff_canary",
                "PROVIDER_CREDENTIALS_BEYOND_CROSSREF_BLOCKER",
                "--production-metrics-artifact",
                "--ops-promotion-artifact",
                "--provider-credentials-artifact",
                "--claim-closure",
            ),
        ),
        _token_check(
            EVIDENCE_DOC,
            (
                "Wave57 Single URL External Blocker Closure",
                "single_url_external_blocker_repo_public_reduced",
                "accessible_public_high_js_replay_complete_external_targets_blocked",
                "repo_local_configured_canary_validated=true",
                "production_24h_metrics_satisfied=false",
                "provider_credentials_beyond_crossref_open=true",
                "closure_claim=false",
            ),
        ),
    ]

    public_replay_reduced = _public_replay_reduced(public_replay_check)
    configured_boundary_validation = _mapping(configured_provider_boundary.get("validation"))
    provider_boundary_reduced = _provider_boundary_reduced(
        official_api_report,
        require_live_crossref=require_live_crossref,
    )
    remaining_blockers = _remaining_external_blockers(
        public_replay_check=public_replay_check,
        strict_promotion_report=strict_report,
        official_api_report=official_api_report,
    )
    public_replay_full_closure = _mapping(public_replay_check.get("closure")).get("full_closure_allowed") is True
    provider_credentials_closed = _provider_credentials_satisfied(official_api_report)
    provider_credentials_boundary = _mapping(
        _mapping(official_api_report.get("non_arxiv_provider_maturity")).get("provider_credentials_boundary")
    )
    provider_credentials_boundary_status = provider_credentials_boundary.get("status")
    remaining_ids = {
        item.get("id")
        for item in remaining_blockers
        if isinstance(item, Mapping)
    }
    production_blockers = set(PRODUCTION_24H_BLOCKERS) | {PRODUCTION_24H_EVIDENCE_INVALID_BLOCKER}
    ops_blockers = set(OPS_PROMOTION_BLOCKERS) | {OPS_PROMOTION_EVIDENCE_INVALID_BLOCKER}
    can_be_closed = bool(
        public_replay_full_closure
        and configured_boundary_validation.get("passed") is True
        and strict_report.get("production_24h_metrics_satisfied") is True
        and strict_report.get("strict_gate_promotion_satisfied") is True
        and provider_boundary_reduced
        and provider_credentials_closed
        and not remaining_blockers
        and not strict_validation_errors
    )
    closure_claim = bool(claim_closure and can_be_closed)
    provider_credentials_blocker_present = any(
        item.get("id") == PROVIDER_CREDENTIALS_BEYOND_CROSSREF_BLOCKER
        for item in remaining_blockers
    )
    provider_credentials_gate_passed = (
        provider_credentials_closed
        if provider_credentials_artifact_path is not None
        else provider_credentials_blocker_present
    )
    if (
        provider_credentials_artifact_path is not None
        and provider_credentials_boundary_status == PROVIDER_CREDENTIALS_CONFIGURED_ONLY_STATUS
        and provider_credentials_blocker_present
        and not closure_claim
    ):
        provider_credentials_gate_passed = True
    runtime_results = [
        {
            "name": "public_browser_runtime_replay_reduced",
            "passed": public_replay_check.get("validation", {}).get("readiness_checks_passed") is True
            and public_replay_check.get("validation", {}).get("public_network_attempted") is True
            and public_replay_reduced,
            "evidence": {
                "status": public_replay_check.get("status"),
                "claim": _mapping(public_replay_check.get("closure")).get("claim"),
                "public_network_attempted": public_replay_check.get("validation", {}).get("public_network_attempted"),
                "remaining_external_blockers": _mapping(public_replay_check.get("closure")).get("remaining_external_blockers"),
            },
        },
        {
            "name": "repo_local_configured_canary_validated",
            "passed": live_result.get("status") == "passed"
            and configured_boundary_validation.get("passed") is True,
            "evidence": {
                "live_result_status": live_result.get("status"),
                "configured_provider_boundary_status": configured_provider_boundary.get("status"),
                "frontdoor_run": configured_provider_boundary.get("frontdoor_run"),
                "cleanup": live_result.get("cleanup"),
            },
        },
        {
            "name": "repo_local_24h_metric_shape_validated_production_open",
            "passed": (
                strict_report.get("repo_local_metric_24h_shape_validated") is True
                and (
                    (
                        production_metrics_artifact_path is None
                        and strict_report.get("production_24h_metrics_satisfied") is False
                        and bool(production_blockers.intersection(remaining_ids))
                    )
                    or (
                        production_metrics_artifact_path is not None
                        and strict_report.get("production_24h_metrics_satisfied") is True
                    )
                )
            ),
            "evidence": {
                "status": strict_report.get("status"),
                "artifact_supplied": production_metrics_artifact_path is not None,
                "source_path": production_metrics_path,
                "load_error": production_metrics_error,
                "repo_local_metric_24h_shape_validated": strict_report.get("repo_local_metric_24h_shape_validated"),
                "production_24h_metrics_satisfied": strict_report.get("production_24h_metrics_satisfied"),
                "remaining_production_blockers": sorted(production_blockers.intersection(remaining_ids)),
                "required_contract_version": PRODUCTION_24H_METRICS_CONTRACT_VERSION,
            },
        },
        {
            "name": "ops_strict_gate_promotion_evidence_gate",
            "passed": (
                strict_report.get("strict_gate_promotion_satisfied") is True
                if ops_promotion_artifact_path is not None
                else bool(ops_blockers.intersection(remaining_ids))
            ),
            "evidence": {
                "artifact_supplied": ops_promotion_artifact_path is not None,
                "source_path": ops_promotion_path,
                "load_error": ops_promotion_error,
                "strict_gate_promotion_satisfied": strict_report.get("strict_gate_promotion_satisfied"),
                "remaining_ops_blockers": sorted(ops_blockers.intersection(remaining_ids)),
                "required_contract_version": OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION,
            },
        },
        {
            "name": "crossref_public_official_api_boundary_reduced",
            "passed": provider_boundary_reduced,
            "evidence": {
                "status": official_api_report.get("status"),
                "live_crossref_status": _mapping(official_api_report.get("live_crossref")).get("status"),
                "remaining_provider_catalog_boundary": _mapping(
                    official_api_report.get("non_arxiv_provider_maturity")
                ).get("remaining_provider_catalog_boundary"),
            },
        },
        {
            "name": "provider_credentials_beyond_crossref_evidence_gate",
            "passed": provider_credentials_gate_passed,
            "evidence": {
                "artifact_supplied": provider_credentials_artifact_path is not None,
                "blocker_id": PROVIDER_CREDENTIALS_BEYOND_CROSSREF_BLOCKER,
                "provider_credentials_boundary_status": provider_credentials_boundary_status,
                "provider_credentials_beyond_crossref_satisfied": provider_credentials_closed,
                "closure_claim": closure_claim,
            },
        },
        {
            "name": "closure_decision_consistent",
            "passed": (
                (
                    claim_closure
                    and can_be_closed
                    and closure_claim
                    and not remaining_blockers
                )
                or (
                    not claim_closure
                    and can_be_closed
                    and closure_claim is False
                    and not remaining_blockers
                )
                or (
                    not can_be_closed
                    and closure_claim is False
                    and bool(remaining_blockers)
                )
            ),
            "evidence": {
                "closure_requested": claim_closure,
                "can_be_closed": can_be_closed,
                "closure_claim": closure_claim,
                "remaining_external_blocker_count": len(remaining_blockers),
            },
        },
    ]
    passed = (
        not strict_validation_errors
        and all(item["passed"] for item in token_results)
        and all(item["passed"] for item in runtime_results)
    )
    closure_status = "closed" if closure_claim else ("ready_for_closure" if can_be_closed else "external_blocked")
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if passed else "failed",
        "topic_slug": TOPIC_SLUG,
        "evidence_doc": str(EVIDENCE_DOC),
        "public_replay_artifact": str(public_artifact),
        "decision_marker": "single_url_external_blocker_repo_public_reduced",
        "closure_decision": {
            "status": closure_status,
            "can_be_closed": can_be_closed,
            "closure_claim": closure_claim,
            "repo_public_boundaries_reduced": {
                "public_browser_runtime_replay": public_replay_reduced,
                "repo_local_configured_canary": configured_boundary_validation.get("passed") is True,
                "repo_local_24h_metric_shape": strict_report.get("repo_local_metric_24h_shape_validated") is True,
                "crossref_public_official_api": provider_boundary_reduced,
                "provider_credentials_beyond_crossref": provider_credentials_closed,
            },
            "remaining_external_blockers": remaining_blockers,
        },
        "token_results": token_results,
        "runtime_results": runtime_results,
        "strict_validation_errors": strict_validation_errors,
        "public_replay_check": public_replay_check,
        "configured_provider_boundary": configured_provider_boundary,
        "strict_promotion_readiness": strict_report,
        "official_api_provider_maturity": official_api_report,
        "evidence_inputs": {
            "production_metrics_artifact_path": production_metrics_path,
            "production_metrics_artifact_error": production_metrics_error,
            "ops_promotion_artifact_path": ops_promotion_path,
            "ops_promotion_artifact_error": ops_promotion_error,
            "provider_credentials_artifact_path": str(_resolve_path(provider_credentials_artifact_path))
            if provider_credentials_artifact_path is not None
            else None,
        },
        "live_canary_result": {
            "contract_version": live_result.get("contract_version"),
            "status": live_result.get("status"),
            "project_key": live_result.get("project_key"),
            "validation": live_result.get("validation"),
            "cleanup": live_result.get("cleanup"),
            "evidence": live_result.get("evidence"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Single URL external blocker closure status")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    parser.add_argument("--output", type=Path, default=None, help="write full check output JSON")
    parser.add_argument("--public-replay-artifact", type=Path, default=None)
    parser.add_argument("--project-key", default="single_url_wave57_canary")
    parser.add_argument("--allow-live-crossref", action="store_true")
    parser.add_argument("--require-live-crossref", action="store_true")
    parser.add_argument("--production-metrics-artifact", type=Path, default=None)
    parser.add_argument("--ops-promotion-artifact", type=Path, default=None)
    parser.add_argument("--provider-credentials-artifact", type=Path, default=None)
    parser.add_argument("--claim-closure", action="store_true")
    args = parser.parse_args(argv)

    result = build_check(
        public_replay_artifact=args.public_replay_artifact,
        project_key=args.project_key,
        allow_live_crossref=args.allow_live_crossref,
        require_live_crossref=args.require_live_crossref,
        production_metrics_artifact_path=args.production_metrics_artifact,
        ops_promotion_artifact_path=args.ops_promotion_artifact,
        provider_credentials_artifact_path=args.provider_credentials_artifact,
        claim_closure=args.claim_closure,
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        closure = result["closure_decision"]
        public_status = result["public_replay_check"].get("status")
        print(
            f"{result['status'].upper()} {CONTRACT_VERSION} "
            f"closure_status={closure['status']} can_be_closed={str(closure['can_be_closed']).lower()} "
            f"public_replay={public_status} "
            f"repo_local_configured_canary={str(closure['repo_public_boundaries_reduced']['repo_local_configured_canary']).lower()} "
            f"production_24h_metrics={str(result['strict_promotion_readiness']['production_24h_metrics_satisfied']).lower()} "
            f"closure_claim={str(closure['closure_claim']).lower()}"
        )
        if result["status"] != "passed":
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
