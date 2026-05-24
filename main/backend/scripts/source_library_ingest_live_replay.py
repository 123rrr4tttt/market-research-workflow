#!/usr/bin/env python3
"""Live replay gate for source-library ingest external-project migration.

The default mode is skip-safe. Pass --allow-public-network to exercise the
existing external-project adapter against bounded public targets.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.collect_runtime.adapters.source_library import to_source_library_response
from app.services.collect_runtime.contracts import CollectResult
from app.services.source_library.adapters.external_project import handle_external_project_manifest
from app.services.source_library.external_project import (
    EXTERNAL_PROJECT_CHANNEL_KEY,
    EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION,
    EXTERNAL_PROJECT_MANIFEST_KEY,
)


CONTRACT_VERSION = "source-library-ingest-live-replay.v1"
DEFAULT_ARTICLE_URLS = ["https://peps.python.org/pep-0008/"]
DEFAULT_EXTERNAL_PROJECT_API_URL = "https://api.github.com/repos/python/cpython"
DEFAULT_EXTERNAL_PROJECT_LINK = "https://github.com/python/cpython"
DEFAULT_MIN_ARTICLE_CONTENT_CHARS = 1000

ExternalProjectRunner = Callable[[dict[str, Any], dict[str, Any], str], dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _article_manifest(*, timeout_ms: int) -> dict[str, Any]:
    return {
        "contract_version": EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION,
        "item_key": "external.live.article_extraction.pep8",
        "display_name": "Live Article Extraction PEP 8",
        "project_link": "https://peps.python.org/pep-0008/",
        "source_kind": "article_extraction_stack",
        "source_scope": "technical_article",
        "capabilities": {
            "candidate_urls": True,
            "article_metadata": True,
            "article_body": True,
            "pdf_artifact": False,
        },
        "accepted_inputs": {
            "query_terms": False,
            "urls": True,
            "domains": False,
            "date_range": False,
            "max_items": True,
        },
        "execution_mode": "article_extractor",
        "runner_ref": "article-extractor://trafilatura-or-heuristic",
        "runtime_config": {
            "parser": "heuristic.main_content.v1",
        },
        "normalization": {
            "record_kind": "document_candidate",
            "frontdoor_strategy": "records_allow_extract",
        },
        "limits": {
            "default_max_items": 1,
            "max_items_cap": 5,
            "request_timeout_ms": timeout_ms,
        },
        "refresh_policy": {
            "manifest_ttl_minutes": 60,
            "probe_ttl_minutes": 1440,
        },
        "provenance": {
            "discovered_by": "wave55_live_replay",
            "source_refs": ["https://peps.python.org/pep-0008/"],
        },
    }


def _external_project_api_manifest(*, timeout_ms: int) -> dict[str, Any]:
    return {
        "contract_version": EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION,
        "item_key": "external.live.github.cpython",
        "display_name": "Live GitHub CPython API",
        "project_link": DEFAULT_EXTERNAL_PROJECT_LINK,
        "source_kind": "api_provider",
        "source_scope": "software_project_metadata",
        "capabilities": {
            "candidate_urls": True,
            "article_metadata": True,
            "article_body": False,
            "pdf_artifact": False,
        },
        "accepted_inputs": {
            "query_terms": False,
            "urls": False,
            "domains": False,
            "date_range": False,
            "max_items": True,
        },
        "execution_mode": "http_api",
        "runner_ref": DEFAULT_EXTERNAL_PROJECT_API_URL,
        "runtime_config": {
            "method": "GET",
            "headers": {"Accept": "application/vnd.github+json"},
            "record_mapping": {
                "url": "html_url",
                "title": "full_name",
                "summary": "description",
                "published_at": "pushed_at",
                "language": "language",
            },
        },
        "normalization": {
            "record_kind": "article_metadata",
            "frontdoor_strategy": "records_only_defer",
        },
        "limits": {
            "default_max_items": 1,
            "max_items_cap": 1,
            "request_timeout_ms": timeout_ms,
        },
        "refresh_policy": {
            "manifest_ttl_minutes": 60,
            "probe_ttl_minutes": 1440,
        },
        "provenance": {
            "discovered_by": "wave55_live_replay",
            "source_refs": [DEFAULT_EXTERNAL_PROJECT_LINK],
        },
    }


def _external_item(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_key": manifest["item_key"],
        "name": manifest["display_name"],
        "channel_key": EXTERNAL_PROJECT_CHANNEL_KEY,
        "item_type": "user_defined",
        "managed_by": "user",
        "enabled": True,
        "params": {},
        "extra": {EXTERNAL_PROJECT_MANIFEST_KEY: manifest},
    }


def _default_runner(item: dict[str, Any], params: dict[str, Any], project_key: str) -> dict[str, Any]:
    return handle_external_project_manifest({"_source_library_item": item, **params}, project_key=project_key)


def _frontdoor_response(
    *,
    item: dict[str, Any],
    params: dict[str, Any],
    result: dict[str, Any],
    project_key: str,
) -> dict[str, Any]:
    legacy_result = {
        **item,
        "project_key": project_key,
        "params": params,
        "result": result,
    }
    return to_source_library_response(CollectResult(channel="source_library", meta={"raw": legacy_result}))


def _run_case(
    *,
    case_id: str,
    item: dict[str, Any],
    params: dict[str, Any],
    project_key: str,
    runner: ExternalProjectRunner,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    try:
        result = runner(item, params, project_key)
        response = _frontdoor_response(item=item, params=params, result=result, project_key=project_key)
        return {
            "case_id": case_id,
            "status": "completed",
            "elapsed_ms": int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
            "runner_result": _summarize_runner_result(result),
            "frontdoor": _summarize_frontdoor_response(response),
        }
    except Exception as exc:  # noqa: BLE001 - live replay must preserve external/runtime blockers.
        return {
            "case_id": case_id,
            "status": "failed",
            "elapsed_ms": int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
            "error": str(exc),
            "exception_type": exc.__class__.__name__,
        }


def _summarize_runner_result(result: dict[str, Any]) -> dict[str, Any]:
    records = [dict(row) for row in result.get("records") or [] if isinstance(row, dict)]
    diagnostics = result.get("runtime_diagnostics") if isinstance(result.get("runtime_diagnostics"), dict) else {}
    nested_diagnostics = diagnostics.get("diagnostics") if isinstance(diagnostics.get("diagnostics"), dict) else {}
    provider_binding = result.get("provider_binding") if isinstance(result.get("provider_binding"), dict) else {}
    fallback_states = [
        {
            "url": str(row.get("url") or ""),
            "state": str(row.get("state") or ""),
            "extractor": str(row.get("extractor") or ""),
            "confidence": str(row.get("confidence") or ""),
            "content_chars": int(row.get("content_chars") or 0),
        }
        for row in nested_diagnostics.get("fallback_states") or []
        if isinstance(row, dict)
    ]
    return {
        "status": result.get("status"),
        "provider": result.get("provider"),
        "execution_mode": result.get("execution_mode"),
        "provider_key": provider_binding.get("provider_key"),
        "record_count": len(records),
        "error_count": len(result.get("errors") or []),
        "errors": list(result.get("errors") or [])[:5],
        "record_refs": [
            {
                "url": str(record.get("url") or ""),
                "title": str(record.get("title") or ""),
                "summary_chars": len(str(record.get("summary") or "")),
                "content_chars": len(str(record.get("content_text") or "")),
            }
            for record in records[:5]
        ],
        "article_extraction": {
            "fallback_states": fallback_states,
            "article_body_extracted": int(nested_diagnostics.get("article_body_extracted") or 0),
            "target_urls": list(nested_diagnostics.get("target_urls") or []),
            "parser_capability": dict(nested_diagnostics.get("parser_capability") or {}),
        },
        "http_api": {
            "endpoint": nested_diagnostics.get("endpoint"),
            "method": nested_diagnostics.get("method"),
            "records_total": nested_diagnostics.get("records_total"),
        },
    }


def _summarize_frontdoor_response(response: dict[str, Any]) -> dict[str, Any]:
    authority = response.get("authority_output") if isinstance(response.get("authority_output"), dict) else {}
    summary = authority.get("summary") if isinstance(authority.get("summary"), dict) else {}
    record_stats = summary.get("record_stats") if isinstance(summary.get("record_stats"), dict) else {}
    handoff = summary.get("handoff") if isinstance(summary.get("handoff"), dict) else {}
    frontdoor = response.get("frontdoor_ingress") if isinstance(response.get("frontdoor_ingress"), dict) else {}
    source_ref = frontdoor.get("source_ref") if isinstance(frontdoor.get("source_ref"), dict) else {}
    return {
        "terminal_status": summary.get("status"),
        "source_kind": source_ref.get("source_kind"),
        "execution_mode": source_ref.get("execution_mode"),
        "record_stats": {
            "fetched": int(record_stats.get("fetched") or 0),
            "normalized": int(record_stats.get("normalized") or 0),
            "dropped": int(record_stats.get("dropped") or 0),
            "errors": int(record_stats.get("errors") or 0),
        },
        "handoff": {
            "admission": handoff.get("admission"),
            "run_extraction": bool(handoff.get("run_extraction")),
            "run_writer": bool(handoff.get("run_writer")),
        },
    }


def _validate_live_outputs(
    *,
    article_case: dict[str, Any] | None,
    external_case: dict[str, Any] | None,
    min_article_content_chars: int,
    skipped: bool,
) -> dict[str, Any]:
    if skipped:
        return {
            "passed": True,
            "skipped": True,
            "live_evidence_sufficient": False,
            "live_article_extraction_stack_replay_closed": False,
            "live_external_project_replay_closed": False,
            "errors": [],
            "warnings": ["public network replay skipped by operator gate"],
        }

    errors: list[str] = []
    warnings = ["live replay is environment-dependent; rerun before using it as fresh closure evidence"]
    article_closed = False
    external_closed = False

    if not article_case or article_case.get("status") != "completed":
        errors.append(f"article_extraction_stack: {article_case.get('error') if article_case else 'not run'}")
    else:
        runner_result = article_case.get("runner_result") if isinstance(article_case.get("runner_result"), dict) else {}
        extraction = runner_result.get("article_extraction") if isinstance(runner_result.get("article_extraction"), dict) else {}
        content_chars = [
            int(row.get("content_chars") or 0)
            for row in extraction.get("fallback_states") or []
            if isinstance(row, dict) and row.get("state") == "article_body_extracted"
        ]
        normalized = int((((article_case.get("frontdoor") or {}).get("record_stats") or {}).get("normalized")) or 0)
        article_closed = (
            runner_result.get("status") == "ok"
            and int(extraction.get("article_body_extracted") or 0) >= 1
            and bool(content_chars)
            and max(content_chars) >= min_article_content_chars
            and normalized >= 1
        )
        if not article_closed:
            errors.append(
                "article_extraction_stack: no live extracted article body met "
                f"min_article_content_chars={min_article_content_chars}"
            )

    if not external_case or external_case.get("status") != "completed":
        errors.append(f"external_project_replay: {external_case.get('error') if external_case else 'not run'}")
    else:
        runner_result = external_case.get("runner_result") if isinstance(external_case.get("runner_result"), dict) else {}
        normalized = int((((external_case.get("frontdoor") or {}).get("record_stats") or {}).get("normalized")) or 0)
        external_closed = (
            runner_result.get("status") == "ok"
            and runner_result.get("execution_mode") == "http_api"
            and int(runner_result.get("record_count") or 0) >= 1
            and normalized >= 1
        )
        if not external_closed:
            errors.append("external_project_replay: live http_api adapter did not produce a normalized record")

    return {
        "passed": not errors,
        "skipped": False,
        "live_evidence_sufficient": bool(article_closed and external_closed),
        "live_article_extraction_stack_replay_closed": article_closed,
        "live_external_project_replay_closed": external_closed,
        "errors": errors,
        "warnings": warnings,
    }


def run_replay(
    *,
    allow_public_network: bool = False,
    project_key: str = "demo_proj",
    article_urls: list[str] | None = None,
    timeout_ms: int = 10000,
    min_article_content_chars: int = DEFAULT_MIN_ARTICLE_CONTENT_CHARS,
    runner: ExternalProjectRunner | None = None,
) -> dict[str, Any]:
    started_at = _utc_now()
    env_value = os.environ.get("SOURCE_LIBRARY_INGEST_LIVE_REPLAY", "")
    resolved_article_urls = [str(url).strip() for url in (article_urls or DEFAULT_ARTICLE_URLS) if str(url).strip()]
    resolved_runner = runner or _default_runner

    if not allow_public_network:
        result = {
            "contract_version": CONTRACT_VERSION,
            "replay_id": "source_library_ingest_live_replay_2026_05_23",
            "started_at": started_at,
            "finished_at": _utc_now(),
            "mode": {
                "allow_public_network": False,
                "skip_safe": True,
                "public_network_env": env_value,
            },
            "inputs": {
                "project_key": project_key,
                "article_urls": resolved_article_urls,
                "external_project_api_url": DEFAULT_EXTERNAL_PROJECT_API_URL,
                "external_project_link": DEFAULT_EXTERNAL_PROJECT_LINK,
                "timeout_ms": timeout_ms,
                "min_article_content_chars": min_article_content_chars,
            },
            "outputs": {
                "article_extraction_stack": {"status": "skipped_public_network_disabled"},
                "external_project_replay": {"status": "skipped_public_network_disabled"},
            },
        }
        result["validation"] = _validate_live_outputs(
            article_case=None,
            external_case=None,
            min_article_content_chars=min_article_content_chars,
            skipped=True,
        )
        return result

    article_item = _external_item(_article_manifest(timeout_ms=timeout_ms))
    external_item = _external_item(_external_project_api_manifest(timeout_ms=timeout_ms))
    article_case = _run_case(
        case_id="live_article_extraction_stack",
        item=article_item,
        params={"urls": resolved_article_urls, "max_items": len(resolved_article_urls) or 1},
        project_key=project_key,
        runner=resolved_runner,
    )
    external_case = _run_case(
        case_id="live_external_project_http_api",
        item=external_item,
        params={"max_items": 1},
        project_key=project_key,
        runner=resolved_runner,
    )
    result = {
        "contract_version": CONTRACT_VERSION,
        "replay_id": "source_library_ingest_live_replay_2026_05_23",
        "started_at": started_at,
        "finished_at": _utc_now(),
        "mode": {
            "allow_public_network": True,
            "skip_safe": True,
            "public_network_env": env_value,
        },
        "inputs": {
            "project_key": project_key,
            "article_urls": resolved_article_urls,
            "external_project_api_url": DEFAULT_EXTERNAL_PROJECT_API_URL,
            "external_project_link": DEFAULT_EXTERNAL_PROJECT_LINK,
            "timeout_ms": timeout_ms,
            "min_article_content_chars": min_article_content_chars,
        },
        "outputs": {
            "article_extraction_stack": article_case,
            "external_project_replay": external_case,
        },
    }
    result["validation"] = _validate_live_outputs(
        article_case=article_case,
        external_case=external_case,
        min_article_content_chars=min_article_content_chars,
        skipped=False,
    )
    return result


def _build_log_lines(result: dict[str, Any]) -> list[str]:
    validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
    lines = [
        f"contract_version={result.get('contract_version')}",
        f"replay_id={result.get('replay_id')}",
        f"started_at={result.get('started_at')}",
        f"finished_at={result.get('finished_at')}",
        f"allow_public_network={result.get('mode', {}).get('allow_public_network')}",
        f"live_article_extraction_stack_replay_closed={validation.get('live_article_extraction_stack_replay_closed')}",
        f"live_external_project_replay_closed={validation.get('live_external_project_replay_closed')}",
        f"live_evidence_sufficient={validation.get('live_evidence_sufficient')}",
    ]
    for name in ("article_extraction_stack", "external_project_replay"):
        case = (result.get("outputs") or {}).get(name) if isinstance(result.get("outputs"), dict) else {}
        runner_result = case.get("runner_result") if isinstance(case, dict) and isinstance(case.get("runner_result"), dict) else {}
        frontdoor = case.get("frontdoor") if isinstance(case, dict) and isinstance(case.get("frontdoor"), dict) else {}
        record_stats = frontdoor.get("record_stats") if isinstance(frontdoor.get("record_stats"), dict) else {}
        lines.append(
            "{name} status={status} runner_status={runner_status} records={records} normalized={normalized} errors={errors}".format(
                name=name,
                status=case.get("status") if isinstance(case, dict) else None,
                runner_status=runner_result.get("status"),
                records=runner_result.get("record_count"),
                normalized=record_stats.get("normalized"),
                errors=runner_result.get("error_count"),
            )
        )
    for error in validation.get("errors") or []:
        lines.append(f"error={error}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run source-library ingest live replay for article extraction and external-project adapter boundaries.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON replay output path.")
    parser.add_argument("--log-output", type=Path, default=None, help="Optional plain-text replay log path.")
    parser.add_argument("--project-key", default="demo_proj")
    parser.add_argument("--article-url", action="append", default=None, help="Article URL to fetch; may be repeated.")
    parser.add_argument("--timeout-ms", type=int, default=10000)
    parser.add_argument("--min-article-content-chars", type=int, default=DEFAULT_MIN_ARTICLE_CONTENT_CHARS)
    parser.add_argument("--allow-public-network", action="store_true", help="Actually contact bounded public live targets.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when live replay is skipped or insufficient.")
    args = parser.parse_args(argv)

    env_allows_public = os.environ.get("SOURCE_LIBRARY_INGEST_LIVE_REPLAY", "").strip().lower() in {"1", "true", "yes"}
    result = run_replay(
        allow_public_network=bool(args.allow_public_network or env_allows_public),
        project_key=args.project_key,
        article_urls=args.article_url,
        timeout_ms=args.timeout_ms,
        min_article_content_chars=args.min_article_content_chars,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    if args.log_output:
        args.log_output.parent.mkdir(parents=True, exist_ok=True)
        args.log_output.write_text("\n".join(_build_log_lines(result)) + "\n", encoding="utf-8")
    print(payload)

    validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
    if not validation.get("passed"):
        return 1
    if args.strict and not validation.get("live_evidence_sufficient"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
