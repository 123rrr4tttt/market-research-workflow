#!/usr/bin/env python3
"""Offline gate for the source-library relevance-review queue contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.source_library.relevance_review import CONTRACT_VERSION  # noqa: E402
from app.services.source_library.relevance_review import annotate_records_with_relevance_review_queue  # noqa: E402
from app.services.source_library.relevance_review import build_relevance_review_queue  # noqa: E402


CURRENT_DEV_ROOT = Path("development/latest-dev-docs/development-plans/CURRENT_DEV")
ARCHIVE_EXTERNAL_BLOCKED_ROOT = Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED")
ARCHIVE_CLOSED_ROOT = Path("docs/development/development-plans/ARCHIVE_CLOSED")


def _evidence_doc_candidates(topic_dir: str, filename: str) -> tuple[Path, ...]:
    return (
        ARCHIVE_CLOSED_ROOT / topic_dir / filename,
        ARCHIVE_EXTERNAL_BLOCKED_ROOT / topic_dir / filename,
        CURRENT_DEV_ROOT / topic_dir / filename,
    )


EVIDENCE_DOCS = [
    _evidence_doc_candidates(
        "2026-03-11-source-library-three-lane-architecture",
        "08_wave12-relevance-review-queue-contract-2026-05-22.md",
    ),
    _evidence_doc_candidates(
        "2026-03-14-search-chain-source-library-mounting-audit",
        "04_wave12-relevance-review-queue-contract-2026-05-22.md",
    ),
    _evidence_doc_candidates(
        "2026-03-14-source-library-adapter-capability-remediation",
        "14_wave12-relevance-review-queue-contract-2026-05-22.md",
    ),
    _evidence_doc_candidates(
        "2026-03-25-source-library-ingest-minimal-migration",
        "12_wave12-relevance-review-queue-contract-2026-05-22.md",
    ),
]
FORBIDDEN_SHARED_INDEXES = {
    "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md",
    "development/latest-dev-docs/development-plans/INDEX.md",
    "development/latest-dev-docs/README.md",
    "development/latest-dev-docs/MERGED_OVERVIEW.md",
}


def _read(root: Path, relative: Path | str) -> str:
    path = root / relative
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _resolve_existing_relative(root: Path, candidates: tuple[Path, ...]) -> Path:
    for relative in candidates:
        if (root / relative).is_file():
            return relative
    return candidates[0]


def _require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def _fixture_queue() -> dict[str, Any]:
    return build_relevance_review_queue(
        project_key="demo_proj",
        item_key="handler.cluster.search_template",
        query_terms=["robotics funding"],
        candidates=[
            "https://example.com/posts/robotics-review",
            "https://safe.example/posts/high-confidence",
        ],
        candidate_refs={
            "https://example.com/posts/robotics-review": {
                "site_entry_url": "https://example.com/search?q={{q}}",
                "entry_type": "search_template",
                "domain": "example.com",
                "entry_domain": "example.com",
                "candidate_source": "search_template",
                "site_policy": "keep",
                "search_service": "basic",
                "matched_by": "none",
                "route_kind": "page",
                "candidate_quality": "low",
                "usable_for_search": False,
                "adapter_capability_status": "review",
                "adapter_capability_reason": "low_confidence_anchor_only_profile",
                "parser_profile_resolved": "fallback_anchor_only",
                "candidate_review_state": "relevance_review",
                "relevance_review_required": True,
            },
            "https://safe.example/posts/high-confidence": {
                "site_entry_url": "https://safe.example/search?q={{q}}",
                "entry_type": "search_template",
                "domain": "safe.example",
                "entry_domain": "safe.example",
                "candidate_source": "search_template",
                "site_policy": "keep",
                "search_service": "basic",
                "matched_by": "title",
                "route_kind": "article",
                "candidate_quality": "high",
                "usable_for_search": True,
                "adapter_capability_status": "allow",
                "parser_profile_resolved": "site_adaptive",
                "relevance_review_required": False,
            },
        },
        runtime_diagnostics=[
            {
                "site_url": "https://example.com/search?q={{q}}",
                "domain": "example.com",
                "site_policy": "keep",
                "search_service": "basic",
                "adapter_capability_status": "review",
                "adapter_capability_reason": "low_confidence_anchor_only_profile",
                "parser_profile_resolved": "fallback_anchor_only",
                "relevance_review_required": True,
                "relevance_review_reason": "term_fallback_candidates",
            }
        ],
        errors=[
            {
                "site_url": "https://example.com/search?q={{q}}",
                "error": "url_term_filter_empty_fallback_used",
                "search_service_used": "basic",
            }
        ],
        source_surface="checker.fixture",
    )


def _build_fixture_check(errors: list[str]) -> dict[str, Any]:
    queue = _fixture_queue()
    repeat = _fixture_queue()
    entries = queue.get("entries") or []
    entry = entries[0] if entries else {}
    reason_codes = set(entry.get("reason_codes") or [])
    fail_closed = entry.get("fail_closed") if isinstance(entry.get("fail_closed"), dict) else {}
    gaps = entry.get("gap_markers") if isinstance(entry.get("gap_markers"), dict) else {}

    _require(queue.get("contract_version") == CONTRACT_VERSION, errors, "queue contract version mismatch")
    _require(queue.get("queue_state") == "ready_for_review", errors, "fixture queue must be ready_for_review")
    _require(queue.get("summary", {}).get("queued_count") == 1, errors, "fixture must queue exactly one candidate")
    _require(
        entry.get("queue_id") == ((repeat.get("entries") or [{}])[0]).get("queue_id"),
        errors,
        "queue id must be deterministic",
    )
    for code in {
        "fallback_anchor_only_profile",
        "term_fallback_candidates",
        "low_confidence_candidate",
        "adapter_capability_review",
    }:
        _require(code in reason_codes, errors, f"fixture missing reason code {code}")
    _require(entry.get("reviewer_ready") is True, errors, "review entry must be reviewer-ready")
    _require(fail_closed.get("auto_accept_allowed") is False, errors, "auto accept must fail closed")
    _require(fail_closed.get("auto_ingest_allowed") is False, errors, "auto ingest must fail closed")
    _require(gaps.get("human_relevance_review_completed") is False, errors, "human review must remain open")
    _require(gaps.get("live_public_replay_completed") is False, errors, "live replay must remain open")

    records = annotate_records_with_relevance_review_queue(
        [
            {
                "record_id": "candidate:0:https://example.com/posts/robotics-review",
                "url": "https://example.com/posts/robotics-review",
                "record_meta": {"artifact_ref": {"local_path": "/tmp/demo.pdf"}},
            }
        ],
        queue,
    )
    review_meta = records[0]["record_meta"].get("source_library_relevance_review")
    _require(records[0]["record_meta"]["artifact_ref"]["local_path"] == "/tmp/demo.pdf", errors, "annotation must preserve record_meta")
    _require(isinstance(review_meta, dict), errors, "record annotation missing review metadata")
    _require((review_meta or {}).get("review_completed") is False, errors, "record annotation must not claim review completion")

    return {
        "queue": queue,
        "deterministic_queue_id": entry.get("queue_id"),
        "annotated_record_review": review_meta,
    }


def _build_static_integration_check(root: Path, errors: list[str]) -> dict[str, Any]:
    checks = {
        "unified_search_emits_queue": "relevance_review_queue=relevance_review_queue" in _read(
            root,
            "main/backend/app/services/resource_pool/unified_search.py",
        ),
        "resolver_propagates_queue": '"relevance_review_queue": relevance_review_queue' in _read(
            root,
            "main/backend/app/services/source_library/resolver.py",
        ),
        "handler_adapter_propagates_queue": '"relevance_review_queue": relevance_review_queue' in _read(
            root,
            "main/backend/app/services/source_library/adapters/handler_cluster.py",
        ),
    }
    for key, value in checks.items():
        _require(value, errors, f"static integration missing: {key}")
    return checks


def _build_doc_check(root: Path, errors: list[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for candidates in EVIDENCE_DOCS:
        relative = _resolve_existing_relative(root, candidates)
        text = _read(root, relative)
        exists = bool(text)
        has_queue = "source_library.relevance_review_queue.v1" in text
        has_non_closure = "claims_human_relevance_review_complete=false" in text and "claims_live_public_replay_complete=false" in text
        rows.append(
            {
                "path": relative.as_posix(),
                "candidate_paths": [path.as_posix() for path in candidates],
                "exists": exists,
                "contract_mentioned": has_queue,
                "non_closure_markers_present": has_non_closure,
            }
        )
        _require(exists, errors, f"missing topic evidence doc: {relative.as_posix()}")
        _require(has_queue, errors, f"evidence doc missing contract marker: {relative.as_posix()}")
        _require(has_non_closure, errors, f"evidence doc missing non-closure markers: {relative.as_posix()}")
    return {"docs": rows, "forbidden_shared_indexes": sorted(FORBIDDEN_SHARED_INDEXES)}


def build_check(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    root = root.resolve()
    errors: list[str] = []
    fixture = _build_fixture_check(errors)
    static = _build_static_integration_check(root, errors)
    docs = _build_doc_check(root, errors)
    return {
        "contract_version": CONTRACT_VERSION,
        "repo_root": str(root),
        "fixture": fixture,
        "static_integration": static,
        "evidence_docs": docs,
        "governance_scope": {
            "public_network_required": False,
            "claims_human_relevance_review_complete": False,
            "claims_live_public_replay_complete": False,
            "shared_indexes_edited": False,
        },
        "validation": {
            "passed": not errors,
            "errors": errors,
            "public_network_attempted": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check source-library relevance-review queue contract.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build_check(args.repo_root)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
