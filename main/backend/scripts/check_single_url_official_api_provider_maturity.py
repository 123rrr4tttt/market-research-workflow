#!/usr/bin/env python3
"""Check single-URL non-arXiv official API provider maturity evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.resource_pool.site_search_policy import resolve_site_search_policy  # noqa: E402
from app.services.source_library.adapters import official_access as official_access_module  # noqa: E402
from app.services.source_library.adapters.official_access import handle_official_access_api  # noqa: E402


CONTRACT_VERSION = "single_url.official_api_provider_maturity.v1"
PROVIDER_CREDENTIALS_EVIDENCE_CONTRACT_VERSION = "single_url.provider_credentials_quota_evidence.v1"
PROVIDER_CREDENTIALS_BEYOND_CROSSREF_BLOCKER = "provider_credentials_quota_beyond_public_crossref_not_validated"
TOPIC_SLUG = "2026-03-02-single-url-first-ingest-allocation-plan"
TOPIC_DIR = Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED") / TOPIC_SLUG
WAVE56_DOC = TOPIC_DIR / "12_wave56-crossref-official-api-provider-maturity-2026-05-23.md"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _token_check(path: Path, tokens: tuple[str, ...]) -> dict[str, Any]:
    exists = path.is_file()
    text = _read_text(path) if exists else ""
    missing = [token for token in tokens if token not in text]
    try:
        rel_path = str(path.relative_to(REPO_ROOT))
    except ValueError:
        rel_path = str(path)
    return {
        "path": rel_path,
        "exists": exists,
        "tokens_checked": list(tokens),
        "missing_tokens": missing,
        "passed": exists and not missing,
    }


def _fixture_crossref_payload() -> dict[str, Any]:
    return {
        "message": {
            "total-results": 2,
            "items": [
                {
                    "DOI": "10.5555/single-url-crossref-1",
                    "URL": "https://doi.org/10.5555/single-url-crossref-1",
                    "title": ["Single URL Robotics Market Evidence"],
                    "publisher": "Fixture Publisher",
                    "type": "journal-article",
                },
                {
                    "DOI": "10.5555/single-url-crossref-2",
                    "title": ["Single URL Automation Evidence"],
                    "publisher": "Fixture Publisher",
                    "type": "proceedings-article",
                },
            ],
        }
    }


def _run_fixture_probe() -> dict[str, Any]:
    official_access_module._CROSSREF_RESULT_CACHE.clear()
    with patch("app.services.source_library.adapters.official_access.default_http_client.get_json") as get_json:
        get_json.return_value = _fixture_crossref_payload()
        result = handle_official_access_api(
            {
                "provider_key": "crossref",
                "query_terms": ["single url robotics market"],
                "max_results": 5,
            },
            project_key="demo_proj",
        )
        call_count = get_json.call_count
    return {
        "result": result,
        "http_call_count": call_count,
    }


def _run_live_probe() -> dict[str, Any]:
    try:
        result = handle_official_access_api(
            {
                "provider_key": "crossref",
                "query_terms": ["robotics market adoption"],
                "max_results": 3,
                "probe_timeout": 10.0,
            },
            project_key="demo_proj",
        )
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "error": str(exc), "result": {}}
    candidates = list(result.get("candidates") or []) if isinstance(result, Mapping) else []
    diagnostics = result.get("diagnostics") if isinstance(result, Mapping) else {}
    passed = bool(candidates) and isinstance(diagnostics, Mapping) and diagnostics.get("provider_key") == "crossref"
    return {
        "status": "passed" if passed else "failed",
        "candidate_count": len(candidates),
        "sample_candidates": candidates[:3],
        "diagnostics": dict(diagnostics or {}) if isinstance(diagnostics, Mapping) else {},
        "errors": list(result.get("errors") or []) if isinstance(result, Mapping) else [],
        "result": result,
    }


def _read_json_artifact(path: Path | None) -> tuple[dict[str, Any] | None, str | None, str | None]:
    if path is None:
        return None, None, None
    full_path = path if path.is_absolute() else REPO_ROOT / path
    try:
        payload = json.loads(full_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, str(full_path), f"{exc.__class__.__name__}: {exc}"
    if not isinstance(payload, dict):
        return None, str(full_path), "artifact JSON must be an object"
    return payload, str(full_path), None


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _provider_credentials_boundary(
    evidence: Mapping[str, Any] | None,
    *,
    source_path: str | None = None,
    load_error: str | None = None,
) -> dict[str, Any]:
    payload = evidence if isinstance(evidence, Mapping) else {}
    providers = payload.get("providers") if isinstance(payload.get("providers"), list) else []
    provider_results: list[dict[str, Any]] = []
    for item in providers:
        if not isinstance(item, Mapping):
            provider_results.append(
                {
                    "provider_key": None,
                    "status": "invalid",
                    "failed_checks": ["provider_entry_must_be_object"],
                }
            )
            continue
        checks = {
            "provider_key_present": bool(_clean_text(item.get("provider_key"))),
            "credential_state_configured": _clean_text(item.get("credential_state")).lower()
            in {"configured", "available", "valid"},
            "quota_status_healthy": _clean_text(item.get("quota_status")).lower()
            in {"within_quota", "healthy", "available"},
            "live_probe_status_passed": _clean_text(item.get("live_probe_status")).lower()
            in {"passed", "validated", "ok"},
            "provider_specific_quota_validated": item.get("provider_specific_quota_validated") is True,
            "credential_material_not_logged": item.get("credential_material_logged") is False,
        }
        failed = [name for name, passed in checks.items() if not passed]
        provider_results.append(
            {
                "provider_key": item.get("provider_key"),
                "status": "validated" if not failed else "failed_evidence",
                "checks": checks,
                "failed_checks": failed,
                "quota_status": item.get("quota_status"),
                "live_probe_status": item.get("live_probe_status"),
            }
        )

    checks = {
        "artifact_loaded": load_error is None,
        "contract_version": payload.get("contract_version") == PROVIDER_CREDENTIALS_EVIDENCE_CONTRACT_VERSION,
        "evidence_scope": payload.get("evidence_scope") == "provider_credentials_quota",
        "providers_present": bool(providers),
        "all_provider_entries_validated": bool(provider_results)
        and all(result.get("status") == "validated" for result in provider_results),
        "generated_by_present": bool(_clean_text(payload.get("generated_by"))),
        "generated_at_present": bool(_clean_text(payload.get("generated_at"))),
        "credential_material_not_logged": payload.get("credential_material_logged") is False,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    validated = bool(payload) and not failed_checks
    return {
        "contract_version": PROVIDER_CREDENTIALS_EVIDENCE_CONTRACT_VERSION,
        "status": "validated" if validated else ("failed_evidence" if payload or load_error else "missing_evidence"),
        "validated": validated,
        "source_path": source_path,
        "load_error": load_error,
        "checks": checks,
        "failed_checks": failed_checks,
        "provider_results": provider_results,
        "credentialed_provider_count": sum(1 for result in provider_results if result.get("status") == "validated"),
    }


def _fixture_runtime_results(fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = fixture.get("result") if isinstance(fixture.get("result"), Mapping) else {}
    diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), Mapping) else {}
    records = result.get("candidate_records") if isinstance(result.get("candidate_records"), list) else []
    policy = resolve_site_search_policy("https://crossref.org/search?q=robotics")
    return [
        {
            "name": "crossref_policy_is_api_preferred",
            "passed": policy.category == "api_preferred" and policy.provider_key == "crossref",
            "evidence": {
                "category": policy.category,
                "provider_key": policy.provider_key,
                "implementation_hint": policy.implementation_hint,
            },
        },
        {
            "name": "crossref_official_api_fixture_returns_candidates",
            "passed": len(result.get("candidates") or []) >= 2
            and fixture.get("http_call_count") == 1
            and diagnostics.get("provider_key") == "crossref",
            "evidence": {
                "candidate_count": len(result.get("candidates") or []),
                "http_call_count": fixture.get("http_call_count"),
                "provider_key": diagnostics.get("provider_key"),
            },
        },
        {
            "name": "crossref_provider_is_public_no_credential_boundary",
            "passed": diagnostics.get("credential_required") is False
            and diagnostics.get("public_api") is True
            and diagnostics.get("endpoint") == "https://api.crossref.org/works",
            "evidence": {
                "endpoint": diagnostics.get("endpoint"),
                "credential_required": diagnostics.get("credential_required"),
                "public_api": diagnostics.get("public_api"),
            },
        },
        {
            "name": "crossref_candidate_records_preserve_title_and_doi",
            "passed": bool(records)
            and all(isinstance(record, Mapping) and record.get("url") for record in records)
            and any(isinstance(record, Mapping) and record.get("doi") for record in records),
            "evidence": {
                "record_count": len(records),
                "sample_record": records[0] if records else {},
            },
        },
    ]


def build_report(
    *,
    allow_live_crossref: bool = False,
    require_live_crossref: bool = False,
    provider_credentials_artifact: Path | None = None,
    provider_credentials_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    token_results = [
        _token_check(
            REPO_ROOT / "main/backend/app/services/source_library/adapters/official_access.py",
            (
                "_run_crossref_works_probe",
                "crossref_works_api",
                "https://api.crossref.org/works",
                "credential_required",
                "_CROSSREF_RESULT_CACHE",
            ),
        ),
        _token_check(
            REPO_ROOT / "main/backend/app/services/resource_pool/site_search_policy.py",
            (
                "crossref.org",
                "provider_key=\"crossref\"",
                "Prefer official Crossref works API search",
            ),
        ),
        _token_check(
            REPO_ROOT / "main/backend/tests/unit/test_source_library_official_access_adapter_unittest.py",
            (
                "test_crossref_official_api_returns_doi_candidate_urls",
                "test_crossref_official_api_reuses_cached_candidates",
                "test_crossref_official_api_reports_transport_failure",
            ),
        ),
        _token_check(
            REPO_ROOT / WAVE56_DOC,
            (
                "Wave56 Crossref Official API Provider Maturity",
                "single_url_non_arxiv_official_api_provider_reduced",
                "crossref_works_api",
                "closure_claim=false",
            ),
        ),
    ]
    fixture = _run_fixture_probe()
    runtime_results = _fixture_runtime_results(fixture)
    live_crossref = {"status": "not_requested"}
    if allow_live_crossref:
        live_crossref = _run_live_probe()
        runtime_results.append(
            {
                "name": "crossref_public_api_live_probe",
                "passed": live_crossref.get("status") == "passed",
                "evidence": {
                    "candidate_count": live_crossref.get("candidate_count"),
                    "sample_candidates": live_crossref.get("sample_candidates", []),
                    "errors": live_crossref.get("errors", []),
                },
            }
        )
    live_required_failed = require_live_crossref and live_crossref.get("status") != "passed"
    loaded_provider_evidence, provider_evidence_path, provider_evidence_error = _read_json_artifact(
        provider_credentials_artifact
    )
    credentials_boundary = _provider_credentials_boundary(
        provider_credentials_evidence or loaded_provider_evidence,
        source_path=provider_evidence_path,
        load_error=provider_evidence_error,
    )
    provider_credentials_satisfied = credentials_boundary.get("validated") is True
    provider_artifact_supplied = provider_credentials_artifact is not None or provider_credentials_evidence is not None
    provider_artifact_failed = provider_artifact_supplied and not provider_credentials_satisfied
    passed = (
        all(item["passed"] for item in token_results)
        and all(item["passed"] for item in runtime_results)
        and not live_required_failed
        and not provider_artifact_failed
    )
    remaining_provider_boundary = [
        "public browser/runtime replay remains external to this gate",
        "configured demo_proj canary and production 24h readback remain external/live",
    ]
    if not provider_credentials_satisfied:
        remaining_provider_boundary.insert(
            0,
            "provider-specific credentials and quota behavior beyond public Crossref remain external",
        )
    return {
        "contract_version": CONTRACT_VERSION,
        "topic_slug": TOPIC_SLUG,
        "status": "passed" if passed else "failed",
        "decision_marker": "single_url_non_arxiv_official_api_provider_reduced",
        "closure_claim": False,
        "non_arxiv_provider_maturity": {
            "closed_provider": "crossref",
            "provider_scope": "public Crossref works API",
            "credential_required": False,
            "provider_credentials_beyond_crossref_satisfied": provider_credentials_satisfied,
            "provider_credentials_blocker_id": PROVIDER_CREDENTIALS_BEYOND_CROSSREF_BLOCKER,
            "provider_credentials_boundary": credentials_boundary,
            "remaining_provider_catalog_boundary": remaining_provider_boundary,
        },
        "token_results": token_results,
        "runtime_results": runtime_results,
        "fixture_probe": fixture,
        "live_crossref": live_crossref,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check single-URL non-arXiv official API provider maturity")
    parser.add_argument("--json", action="store_true", help="print JSON report")
    parser.add_argument("--allow-live-crossref", action="store_true", help="run a live public Crossref API probe")
    parser.add_argument("--require-live-crossref", action="store_true", help="fail unless live Crossref probe passes")
    parser.add_argument("--provider-credentials-artifact", type=Path, default=None)
    parser.add_argument("--write-report", type=Path, default=None, help="write JSON report to this path")
    args = parser.parse_args(argv)

    report = build_report(
        allow_live_crossref=args.allow_live_crossref or args.require_live_crossref,
        require_live_crossref=args.require_live_crossref,
        provider_credentials_artifact=args.provider_credentials_artifact,
    )
    if args.write_report is not None:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        live_status = report["live_crossref"]["status"]
        print(
            f"{report['status'].upper()} {CONTRACT_VERSION} "
            f"crossref_fixture={'passed' if all(item['passed'] for item in report['runtime_results'] if item['name'] != 'crossref_public_api_live_probe') else 'failed'} "
            f"live_crossref={live_status} closure_claim=false"
        )
        if report["status"] != "passed":
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
