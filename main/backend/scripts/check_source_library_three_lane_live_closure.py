#!/usr/bin/env python3
"""Wave55 live evidence gate for source-library three-lane closure."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.resource_pool.url_utils import domain_from_url  # noqa: E402
from app.services.source_library.adapters.external_project import handle_external_project_manifest  # noqa: E402
from app.services.source_library.external_project import EXTERNAL_PROJECT_CHANNEL_KEY  # noqa: E402
from app.services.source_library.external_project import EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION  # noqa: E402
from app.services.source_library.external_project import EXTERNAL_PROJECT_MANIFEST_KEY  # noqa: E402
from app.services.source_library.relevance_review import CONTRACT_VERSION as REVIEW_QUEUE_CONTRACT_VERSION  # noqa: E402
from app.services.source_library.relevance_review import TAXONOMY_REVIEW_READINESS_CONTRACT_VERSION  # noqa: E402
from app.services.source_library.relevance_review import build_relevance_review_queue  # noqa: E402
from app.services.source_library.relevance_review import build_taxonomy_review_readiness  # noqa: E402
from scripts.source_library_public_live_probes import DEFAULT_TARGETS  # noqa: E402
from scripts.source_library_public_live_probes import run_probe  # noqa: E402


CONTRACT_VERSION = "source_library.three_lane_live_closure.v1"
DEFAULT_RUN_DIR = Path("development/latest-dev-docs/automation-runs/wave55-source-library-three-lane-live-closure/2026-05-23")
DEFAULT_ARTIFACT_PATH = DEFAULT_RUN_DIR / "closure.json"
TOPIC_DOC_DIR = Path(
    "docs/development/development-plans/ARCHIVE_CLOSED/"
    "2026-03-11-source-library-three-lane-architecture"
)
ARTICLE_EXTRACTOR_ITEM_KEY = "external.three_lane.live_article_extractor"
HUMAN_REVIEW_REQUIRED_FIELDS = ("queue_id", "reviewed_by", "reviewed_at", "decision", "state")
HUMAN_REVIEW_COMPLETED_STATE = "completed"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_json(path: Path | None) -> Any:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_targets(path: Path | None) -> list[dict[str, Any]]:
    payload = _load_json(path)
    if payload is None:
        return [dict(row) for row in DEFAULT_TARGETS]
    raw_targets = payload.get("targets") if isinstance(payload, dict) else payload
    if not isinstance(raw_targets, list):
        raise ValueError("--target-file must contain a list or an object with targets")
    return [dict(row) for row in raw_targets if isinstance(row, dict)]


def _load_human_review_evidence(path: Path | None) -> list[dict[str, Any]]:
    payload = _load_json(path)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError("--human-review-evidence must contain a JSON array")
    return [dict(row) for row in payload if isinstance(row, dict)]


def _repo_output_path(repo_root: Path | None, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (repo_root.resolve() if repo_root else REPO_ROOT) / path


def _candidate_rows_from_probe(probe: dict[str, Any], *, max_candidates: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in ((probe.get("outputs") or {}).get("target_results") or []):
        if not isinstance(result, dict):
            continue
        target = result.get("target") if isinstance(result.get("target"), dict) else {}
        classification = result.get("classification") if isinstance(result.get("classification"), dict) else {}
        adapter_result = result.get("adapter_result") if isinstance(result.get("adapter_result"), dict) else {}
        status = str(classification.get("status") or "")
        if not status.startswith("candidate_ready"):
            continue
        used_term_fallback = bool(adapter_result.get("used_term_fallback") or status == "candidate_ready_with_term_fallback")
        target_id = str(target.get("target_id") or "").strip()
        template = str(target.get("template") or "").strip()
        query_terms = [str(term).strip() for term in target.get("query_terms") or [] if str(term).strip()]
        search_urls = [str(url).strip() for url in adapter_result.get("search_urls") or [] if str(url).strip()]
        diagnostics = adapter_result.get("diagnostics") if isinstance(adapter_result.get("diagnostics"), dict) else {}
        for candidate in adapter_result.get("candidates") or []:
            url = str(candidate or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            rows.append(
                {
                    "url": url,
                    "domain": str(domain_from_url(url) or "").strip().lower() or None,
                    "target_id": target_id,
                    "source_status": status,
                    "query_terms": query_terms,
                    "site_entry_url": search_urls[0] if search_urls else template,
                    "entry_domain": str(result.get("entry_domain") or domain_from_url(template) or "").strip().lower()
                    or None,
                    "used_term_fallback": used_term_fallback,
                    "candidate_quality": "low" if used_term_fallback else "medium",
                    "matched_by": "none" if used_term_fallback else "live_public_probe",
                    "adapter_capability_status": "review" if used_term_fallback else "allow",
                    "adapter_capability_reason": "term_fallback_candidates" if used_term_fallback else None,
                    "parser_profile_resolved": diagnostics.get("parser_profile_resolved"),
                }
            )
    if len(rows) <= max_candidates:
        return rows
    extraction_ready = [row for row in rows if not row.get("used_term_fallback")]
    review_required = [row for row in rows if row.get("used_term_fallback")]
    if not extraction_ready:
        return review_required[:max_candidates]
    if not review_required:
        return extraction_ready[:max_candidates]
    extraction_slots = max(1, max_candidates - 1)
    selected = extraction_ready[:extraction_slots] + review_required[: max_candidates - extraction_slots]
    return selected[:max_candidates]


def _article_extractor_item() -> dict[str, Any]:
    manifest = {
        "contract_version": EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION,
        "item_key": ARTICLE_EXTRACTOR_ITEM_KEY,
        "display_name": "Three-Lane Live Article Extractor",
        "project_link": "https://example.com/source-library-three-lane-live",
        "source_kind": "article_extraction_stack",
        "source_scope": "source_library_three_lane_live_closure",
        "capabilities": {
            "candidate_urls": False,
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
        "normalization": {
            "record_kind": "document_candidate",
            "frontdoor_strategy": "records_allow_extract",
        },
        "limits": {
            "default_max_items": 4,
            "max_items_cap": 8,
            "request_timeout_ms": 8000,
        },
        "refresh_policy": {
            "manifest_ttl_minutes": 60,
            "probe_ttl_minutes": 1440,
        },
        "provenance": {
            "discovered_by": "wave55_three_lane_live_closure",
            "source_refs": [TOPIC_DOC_DIR.as_posix()],
        },
    }
    return {
        "item_key": ARTICLE_EXTRACTOR_ITEM_KEY,
        "name": "Three-Lane Live Article Extractor",
        "channel_key": EXTERNAL_PROJECT_CHANNEL_KEY,
        "item_type": "service_aggregated",
        "managed_by": "system",
        "enabled": True,
        "params": {},
        "extra": {EXTERNAL_PROJECT_MANIFEST_KEY: manifest},
    }


def _run_article_extraction(candidate_rows: list[dict[str, Any]], *, allow_public_network: bool) -> dict[str, Any]:
    urls = [str(row.get("url") or "").strip() for row in candidate_rows if str(row.get("url") or "").strip()]
    if not urls:
        return {
            "attempted": False,
            "skipped": True,
            "skip_reason": "no_live_candidate_urls",
            "status": "skipped",
            "record_count": 0,
            "article_body_extracted_count": 0,
            "state_counts": {},
            "records": [],
            "errors": [],
        }
    if not allow_public_network:
        return {
            "attempted": False,
            "skipped": True,
            "skip_reason": "public_network_disabled_for_article_extraction",
            "status": "skipped",
            "candidate_url_count": len(urls),
            "record_count": 0,
            "article_body_extracted_count": 0,
            "state_counts": {},
            "records": [],
            "errors": [],
        }

    result = handle_external_project_manifest(
        {
            "_source_library_item": _article_extractor_item(),
            "urls": urls,
            "max_items": len(urls),
        },
        project_key="demo_proj",
    )
    return _summarize_article_extraction(result, urls=urls)


def _summarize_article_extraction(result: dict[str, Any], *, urls: list[str]) -> dict[str, Any]:
    records = [record for record in result.get("records") or [] if isinstance(record, dict)]
    record_rows: list[dict[str, Any]] = []
    state_counts: Counter[str] = Counter()
    for record in records:
        meta = record.get("record_meta") if isinstance(record.get("record_meta"), dict) else {}
        extraction = meta.get("article_extraction") if isinstance(meta.get("article_extraction"), dict) else {}
        state = str(extraction.get("state") or "missing_article_extraction_meta").strip()
        state_counts[state] += 1
        record_rows.append(
            {
                "url": str(record.get("url") or "").strip(),
                "title": str(record.get("title") or "").strip() or None,
                "state": state,
                "extractor": extraction.get("extractor"),
                "confidence": extraction.get("confidence"),
                "content_chars": int(extraction.get("content_chars") or len(str(record.get("content_text") or ""))),
                "has_content_text": bool(str(record.get("content_text") or "").strip()),
            }
        )
    extracted_count = int(state_counts.get("article_body_extracted", 0))
    return {
        "attempted": True,
        "skipped": False,
        "status": str(result.get("status") or "unknown"),
        "candidate_url_count": len(urls),
        "record_count": len(records),
        "article_body_extracted_count": extracted_count,
        "state_counts": dict(sorted(state_counts.items())),
        "provider_binding": ((result.get("runtime_diagnostics") or {}).get("provider_binding") or result.get("provider_binding")),
        "diagnostics": (result.get("runtime_diagnostics") or {}).get("diagnostics") or {},
        "records": record_rows,
        "errors": list(result.get("errors") or []),
        "validation": {
            "provider_article_extraction_complete": extracted_count > 0,
            "all_candidates_materialized": len(records) == len(urls),
        },
    }


def _build_live_review_queue(candidate_rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [str(row.get("url") or "").strip() for row in candidate_rows if str(row.get("url") or "").strip()]
    candidate_refs: dict[str, dict[str, Any]] = {}
    runtime_diagnostics: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for row in candidate_rows:
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        used_term_fallback = bool(row.get("used_term_fallback"))
        site_entry_url = str(row.get("site_entry_url") or "").strip()
        candidate_refs[url] = {
            "site_entry_url": site_entry_url,
            "entry_type": "search_template",
            "domain": row.get("domain"),
            "entry_domain": row.get("entry_domain"),
            "candidate_source": f"wave55_live_probe:{row.get('target_id')}",
            "site_policy": "keep",
            "search_service": "generic_web.search_template",
            "matched_by": row.get("matched_by"),
            "route_kind": "article",
            "candidate_quality": row.get("candidate_quality"),
            "usable_for_search": not used_term_fallback,
            "adapter_capability_status": row.get("adapter_capability_status"),
            "adapter_capability_reason": row.get("adapter_capability_reason"),
            "parser_profile_resolved": row.get("parser_profile_resolved"),
            "candidate_review_state": "relevance_review" if used_term_fallback else "candidate_ready",
            "relevance_review_required": used_term_fallback,
        }
        runtime_diagnostics.append(
            {
                "site_url": site_entry_url,
                "domain": row.get("entry_domain"),
                "site_policy": "keep",
                "search_service": "generic_web.search_template",
                "adapter_capability_status": row.get("adapter_capability_status"),
                "adapter_capability_reason": row.get("adapter_capability_reason"),
                "parser_profile_resolved": row.get("parser_profile_resolved"),
                "relevance_review_required": used_term_fallback,
                "relevance_review_reason": "term_fallback_candidates" if used_term_fallback else "",
            }
        )
        if used_term_fallback:
            errors.append(
                {
                    "site_url": site_entry_url,
                    "error": "url_term_filter_empty_fallback_used",
                    "search_service_used": "generic_web.search_template",
                }
            )
    return build_relevance_review_queue(
        project_key="demo_proj",
        item_key="handler.cluster.search_template.wave55_live",
        query_terms=sorted({term for row in candidate_rows for term in row.get("query_terms") or []}),
        candidates=candidates,
        candidate_refs=candidate_refs,
        runtime_diagnostics=runtime_diagnostics,
        errors=errors,
        source_surface="wave55_source_library_three_lane_live_closure",
    )


def _human_review_blocker(
    *,
    review_queue: dict[str, Any],
    readiness: dict[str, Any],
    human_review_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    review = readiness.get("review_queue") if isinstance(readiness.get("review_queue"), dict) else {}
    human_review = readiness.get("human_review") if isinstance(readiness.get("human_review"), dict) else {}
    queue_ids = [str(row).strip() for row in review.get("queue_ids") or [] if str(row).strip()]
    missing_queue_ids = [
        str(row).strip() for row in human_review.get("missing_queue_ids") or [] if str(row).strip()
    ]
    completed = bool(human_review.get("completed"))
    if completed:
        status = "closed_by_explicit_human_review_evidence"
        blocker_type = None
    elif human_review_evidence:
        status = "human_review_evidence_incomplete_or_invalid"
        blocker_type = "explicit_human_review_evidence_required_for_all_queue_ids"
    elif queue_ids:
        status = "human_review_evidence_missing"
        blocker_type = "explicit_human_review_evidence_required"
    else:
        status = "review_queue_not_ready"
        blocker_type = "review_queue_not_ready"

    review_entries: list[dict[str, Any]] = []
    for entry in review_queue.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        fields = entry.get("reviewer_fields") if isinstance(entry.get("reviewer_fields"), dict) else {}
        review_entries.append(
            {
                "queue_id": entry.get("queue_id"),
                "url": fields.get("url"),
                "domain": fields.get("domain"),
                "query_terms": fields.get("query_terms") or [],
                "reason_codes": list(entry.get("reason_codes") or []),
                "reviewer_ready": bool(entry.get("reviewer_ready")),
                "reviewer_fields_missing": list(entry.get("reviewer_fields_missing") or []),
                "required_evidence": {
                    "queue_id": entry.get("queue_id"),
                    "reviewed_by": "<human-or-approved-reviewer-id>",
                    "reviewed_at": "<RFC3339 timestamp>",
                    "decision": "<accept|reject|defer plus reviewer rationale>",
                    "state": HUMAN_REVIEW_COMPLETED_STATE,
                },
            }
        )

    return {
        "contract_version": "source_library.three_lane_human_review_blocker.v1",
        "status": status,
        "blocker_type": blocker_type,
        "closure_allowed": completed,
        "evidence_supplied": bool(human_review_evidence),
        "required_fields": list(HUMAN_REVIEW_REQUIRED_FIELDS),
        "completed_state": HUMAN_REVIEW_COMPLETED_STATE,
        "queue_ids": queue_ids,
        "missing_queue_ids": missing_queue_ids,
        "completed_queue_ids": list(human_review.get("completed_queue_ids") or []),
        "invalid_evidence": list(human_review.get("invalid_evidence") or []),
        "review_packet": review_entries,
        "non_closure_rule": (
            "Do not claim human review closure unless explicit evidence covers every queue id "
            "with queue_id, reviewed_by, reviewed_at, decision, and state=completed."
        ),
    }


def _taxonomy_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "live_source_collection_site_search",
            "item_key": "handler.cluster.search_template.wave55_live",
            "item_channel_key": "handler.cluster",
            "source_mode": "site_search",
            "taxonomy": {
                "channel_family": "generic_web",
                "item_type": "service_aggregated",
                "managed_by": "system",
                "expected_entry_type": "search_template",
                "internal_adapter_only": True,
                "site_search_authoritative": True,
            },
        },
        {
            "case_id": "provider_article_extraction",
            "item_key": ARTICLE_EXTRACTOR_ITEM_KEY,
            "item_channel_key": EXTERNAL_PROJECT_CHANNEL_KEY,
            "source_mode": "provider_harvest",
            "taxonomy": {
                "channel_family": "external_project",
                "item_type": "service_aggregated",
                "managed_by": "system",
                "expected_entry_type": "article_extractor",
                "internal_adapter_only": False,
                "site_search_authoritative": False,
            },
        },
        {
            "case_id": "human_review_candidate_readback",
            "item_key": "handler.cluster.search_template.wave55_live",
            "item_channel_key": "handler.cluster",
            "source_mode": "url_execution",
            "taxonomy": {
                "channel_family": "review_queue",
                "item_type": "service_aggregated",
                "managed_by": "system",
                "expected_entry_type": "review_candidate",
                "internal_adapter_only": False,
                "site_search_authoritative": False,
            },
        },
    ]


def build_contract(
    repo_root: Path | str | None = None,
    *,
    targets: list[dict[str, Any]] | None = None,
    live_probe_payload: dict[str, Any] | None = None,
    allow_public_network: bool = False,
    probe_timeout: float = 6.0,
    max_targets: int | None = None,
    max_candidates: int = 4,
    human_review_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    root = root.resolve()
    started_at = _utc_now()
    errors: list[str] = []

    if live_probe_payload is None:
        probe = run_probe(
            targets=targets,
            allow_public_network=allow_public_network,
            project_key="demo_proj",
            probe_timeout=probe_timeout,
            max_targets=max_targets,
        )
    else:
        probe = dict(live_probe_payload)

    candidate_rows = _candidate_rows_from_probe(probe, max_candidates=max_candidates)
    article_extraction = _run_article_extraction(candidate_rows, allow_public_network=allow_public_network)
    review_queue = _build_live_review_queue(candidate_rows)
    readiness = build_taxonomy_review_readiness(
        taxonomy_cases=_taxonomy_cases(),
        review_queue=review_queue,
        human_review_evidence=human_review_evidence or [],
        source_surface="check_source_library_three_lane_live_closure",
    )
    human_review_blocker = _human_review_blocker(
        review_queue=review_queue,
        readiness=readiness,
        human_review_evidence=human_review_evidence or [],
    )

    probe_validation = probe.get("validation") if isinstance(probe.get("validation"), dict) else {}
    live_source_collection_complete = (
        bool(probe_validation.get("passed"))
        and not bool(probe_validation.get("skipped"))
        and bool(probe_validation.get("live_evidence_sufficient"))
        and bool(candidate_rows)
    )
    provider_article_extraction_complete = bool(
        (article_extraction.get("validation") or {}).get("provider_article_extraction_complete")
    )
    human_review_completed = bool(readiness["readiness"]["human_review_completed"])

    if allow_public_network and not live_source_collection_complete:
        errors.append("public live source collection did not produce candidate-ready evidence")
    if live_source_collection_complete and not provider_article_extraction_complete:
        errors.append("provider article extraction did not extract any article body from live candidates")

    closure_state = (
        "live_collection_article_extraction_human_review_complete"
        if live_source_collection_complete and provider_article_extraction_complete and human_review_completed
        else "live_collection_article_extraction_ready_human_review_open"
        if live_source_collection_complete and provider_article_extraction_complete
        else "live_collection_ready_article_extraction_open"
        if live_source_collection_complete
        else "live_evidence_open"
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "repo_root": str(root),
        "started_at": started_at,
        "finished_at": _utc_now(),
        "scope": {
            "topic_doc_dir": TOPIC_DOC_DIR.as_posix(),
            "public_network_required_for_live_evidence": True,
            "public_network_attempted": bool(allow_public_network),
            "shared_indexes_edited": False,
            "global_manifest_indexes_edited": False,
        },
        "live_source_collection": {
            "probe_contract": probe.get("probe_id"),
            "status_counts": (probe.get("outputs") or {}).get("status_counts") or {},
            "candidate_ready_targets": (probe.get("outputs") or {}).get("candidate_ready_targets") or [],
            "candidate_count": len(candidate_rows),
            "candidate_rows": candidate_rows,
            "complete": live_source_collection_complete,
            "validation": probe_validation,
        },
        "provider_article_extraction": {
            **article_extraction,
            "complete": provider_article_extraction_complete,
        },
        "human_review_readback": {
            "review_queue_contract": REVIEW_QUEUE_CONTRACT_VERSION,
            "taxonomy_review_contract": TAXONOMY_REVIEW_READINESS_CONTRACT_VERSION,
            "review_queue": review_queue,
            "readiness": readiness,
            "blocker": human_review_blocker,
            "complete": human_review_completed,
            "evidence_supplied": bool(human_review_evidence),
        },
        "closure_state": closure_state,
        "non_closure_markers": {
            "claims_live_source_collection_complete": live_source_collection_complete,
            "claims_provider_article_extraction_complete": provider_article_extraction_complete,
            "claims_human_review_complete": human_review_completed,
            "claims_human_relevance_review_complete": human_review_completed,
            "shared_indexes_edited": False,
        },
        "validation": {
            "passed": not errors,
            "errors": errors,
            "warnings": [
                "public live evidence is environment-dependent; rerun before promotion or archive migration",
                "human review completion is only claimed when explicit evidence covers every live review queue id",
            ],
            "strict_live_runtime_complete": live_source_collection_complete and provider_article_extraction_complete,
            "human_review_completed": human_review_completed,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Wave55 live source-library three-lane closure evidence gate.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--target-file", type=Path, default=None)
    parser.add_argument("--live-probe-input", type=Path, default=None)
    parser.add_argument("--human-review-evidence", type=Path, default=None)
    parser.add_argument(
        "--human-review-blocker-output",
        type=Path,
        default=None,
        help="Write a focused human-review blocker/readback artifact for the live review queue.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_ARTIFACT_PATH)
    parser.add_argument("--probe-timeout", type=float, default=6.0)
    parser.add_argument("--max-targets", type=int, default=None)
    parser.add_argument("--max-candidates", type=int, default=4)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero unless live collection and article extraction both complete.")
    parser.add_argument(
        "--require-human-review-complete",
        action="store_true",
        help="Exit non-zero unless explicit human-review evidence closes every queue id.",
    )
    args = parser.parse_args(argv)

    targets = _load_targets(args.target_file)
    live_probe_payload = _load_json(args.live_probe_input)
    human_review_evidence = _load_human_review_evidence(args.human_review_evidence)
    result = build_contract(
        args.repo_root,
        targets=targets,
        live_probe_payload=live_probe_payload,
        allow_public_network=args.allow_public_network,
        probe_timeout=args.probe_timeout,
        max_targets=args.max_targets,
        max_candidates=args.max_candidates,
        human_review_evidence=human_review_evidence,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        output_path = _repo_output_path(args.repo_root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    if args.human_review_blocker_output is not None:
        blocker_output_path = _repo_output_path(args.repo_root, args.human_review_blocker_output)
        blocker_output_path.parent.mkdir(parents=True, exist_ok=True)
        blocker_output_path.write_text(
            json.dumps(
                result["human_review_readback"]["blocker"],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    if not result["validation"]["passed"]:
        return 1
    if args.strict and not result["validation"]["strict_live_runtime_complete"]:
        return 2
    if args.require_human_review_complete and not result["validation"]["human_review_completed"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
