#!/usr/bin/env python3
"""Wave20 deterministic review-batch 4 gate for source-library review closure."""

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

from app.services.source_library.relevance_review import CONTRACT_VERSION as REVIEW_QUEUE_CONTRACT_VERSION  # noqa: E402
from app.services.source_library.relevance_review import (  # noqa: E402
    TAXONOMY_REVIEW_READINESS_CONTRACT_VERSION,
)
from app.services.source_library.relevance_review import build_relevance_review_queue  # noqa: E402
from scripts.check_source_library_relevance_review_queue import (  # noqa: E402
    build_check as build_relevance_review_queue_check,
)
from scripts.check_source_library_review_closure_batch import (  # noqa: E402
    CONTRACT_VERSION as WAVE16_REVIEW_BATCH_CONTRACT_VERSION,
)
from scripts.check_source_library_review_closure_batch import (  # noqa: E402
    build_check as build_wave16_review_batch_check,
)
from scripts.check_source_library_review_closure_batch2 import (  # noqa: E402
    CONTRACT_VERSION as WAVE18_REVIEW_BATCH_CONTRACT_VERSION,
)
from scripts.check_source_library_review_closure_batch2 import (  # noqa: E402
    build_check as build_wave18_review_batch_check,
)
from scripts.check_source_library_review_closure_batch3 import (  # noqa: E402
    CONTRACT_VERSION as WAVE19_REVIEW_BATCH_CONTRACT_VERSION,
)
from scripts.check_source_library_review_closure_batch3 import (  # noqa: E402
    build_check as build_wave19_review_batch_check,
)
from scripts.check_source_library_search_governance import (  # noqa: E402
    CONTRACT_VERSION as SEARCH_GOVERNANCE_CONTRACT_VERSION,
)
from scripts.check_source_library_search_governance import (  # noqa: E402
    build_check as build_search_governance_check,
)
from scripts.check_source_library_taxonomy_review_readiness import (  # noqa: E402
    build_check as build_taxonomy_review_readiness_check,
)


CONTRACT_VERSION = "source_library.review_closure_batch4.v1"
RUN_DIR = Path("development/latest-dev-docs/automation-runs/source-library-review-closure-batch4/2026-05-22")
DEFAULT_ARTIFACT_PATH = RUN_DIR / "review_batch4.json"
WAVE16_ARTIFACT_PATH = Path(
    "development/latest-dev-docs/automation-runs/source-library-review-closure-batch/2026-05-22/review_batch.json"
)
WAVE18_ARTIFACT_PATH = Path(
    "development/latest-dev-docs/automation-runs/source-library-review-closure-batch2/2026-05-22/review_batch2.json"
)
WAVE19_ARTIFACT_PATH = Path(
    "development/latest-dev-docs/automation-runs/source-library-review-closure-batch3/2026-05-22/review_batch3.json"
)
CURRENT_DEV_ROOT = Path("development/latest-dev-docs/development-plans/CURRENT_DEV")
ARCHIVE_EXTERNAL_BLOCKED_ROOT = Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED")


def _evidence_doc_candidates(topic_dir: str, filename: str) -> tuple[Path, Path]:
    return (
        ARCHIVE_EXTERNAL_BLOCKED_ROOT / topic_dir / filename,
        CURRENT_DEV_ROOT / topic_dir / filename,
    )

EVIDENCE_DOCS = {
    "three_lane": _evidence_doc_candidates(
        "2026-03-11-source-library-three-lane-architecture",
        "13_wave20-review-closure-batch4-2026-05-22.md",
    ),
    "search_chain": _evidence_doc_candidates(
        "2026-03-14-search-chain-source-library-mounting-audit",
        "09_wave20-review-closure-batch4-2026-05-22.md",
    ),
    "adapter_capability": _evidence_doc_candidates(
        "2026-03-14-source-library-adapter-capability-remediation",
        "19_wave20-review-closure-batch4-2026-05-22.md",
    ),
    "minimal_migration": _evidence_doc_candidates(
        "2026-03-25-source-library-ingest-minimal-migration",
        "16_wave20-review-closure-batch4-2026-05-22.md",
    ),
}

FORBIDDEN_SHARED_INDEXES = {
    "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md",
    "development/latest-dev-docs/development-plans/INDEX.md",
    "development/latest-dev-docs/README.md",
    "development/latest-dev-docs/MERGED_OVERVIEW.md",
}

REQUIRED_DOC_MARKERS = (
    CONTRACT_VERSION,
    DEFAULT_ARTIFACT_PATH.as_posix(),
    "deterministic_batch4_closed=true",
    "claims_human_review_complete=false",
    "claims_human_relevance_review_complete=false",
    "claims_public_replay_complete=false",
    "claims_live_public_replay_complete=false",
    "claims_live_source_collection_complete=false",
    "claims_live_ingest_migration_complete=false",
    "shared_indexes_edited=false",
)


def _require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def _read_text(root: Path, relative: Path | str) -> str:
    path = root / relative
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _resolve_existing_relative(root: Path, candidates: tuple[Path, ...]) -> Path:
    for relative in candidates:
        if (root / relative).is_file():
            return relative
    return candidates[0]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _validation_passed(payload: dict[str, Any]) -> bool:
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    return bool(validation.get("passed"))


def _public_network_attempted(payload: dict[str, Any]) -> bool:
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    return bool(validation.get("public_network_attempted"))


def _batch4_fixture_queue() -> dict[str, Any]:
    return build_relevance_review_queue(
        project_key="demo_proj",
        item_key="handler.cluster.search_template.batch4",
        query_terms=["humanoid robotics source-library review", "public procurement commercialization"],
        candidates=[
            "https://lane.example/posts/source-routing-cross-lane-note",
            "https://mounting.example/source/mounted-search-taxonomy",
            "https://adapter.example/reports/parser-capability-fallback",
            "https://migration.example/external-project/canary-url",
        ],
        candidate_refs={
            "https://lane.example/posts/source-routing-cross-lane-note": {
                "site_entry_url": "https://lane.example/search?q={{q}}",
                "entry_type": "search_template",
                "domain": "lane.example",
                "entry_domain": "lane.example",
                "candidate_source": "three_lane_dispatch_fixture",
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
            "https://mounting.example/source/mounted-search-taxonomy": {
                "site_entry_url": "https://mounting.example/search?q={{q}}",
                "entry_type": "search_template",
                "domain": "mounting.example",
                "entry_domain": "mounting.example",
                "candidate_source": "mounted_search_chain",
                "site_policy": "keep",
                "search_service": "basic",
                "matched_by": "site_policy",
                "route_kind": "directory",
                "candidate_quality": "medium",
                "usable_for_search": True,
                "adapter_capability_status": "allow",
                "parser_profile_resolved": "site_adaptive",
                "candidate_review_state": "relevance_review",
                "relevance_review_required": True,
            },
            "https://adapter.example/reports/parser-capability-fallback": {
                "site_entry_url": "https://adapter.example/search?q={{q}}",
                "entry_type": "search_template",
                "domain": "adapter.example",
                "entry_domain": "adapter.example",
                "candidate_source": "adapter_capability_probe",
                "site_policy": "keep",
                "search_service": "basic",
                "matched_by": "none",
                "route_kind": "article",
                "candidate_quality": "unknown",
                "usable_for_search": False,
                "adapter_capability_status": "review",
                "adapter_capability_reason": "low_confidence_anchor_only_profile",
                "parser_profile_resolved": "fallback_anchor_only",
                "candidate_review_state": "relevance_review",
                "relevance_review_required": True,
            },
            "https://migration.example/external-project/canary-url": {
                "site_entry_url": "https://migration.example/source?q={{q}}",
                "entry_type": "external_project_url_pool",
                "domain": "migration.example",
                "entry_domain": "migration.example",
                "candidate_source": "external_project_url_pool",
                "site_policy": "keep",
                "search_service": "url_pool",
                "matched_by": "none",
                "route_kind": "article",
                "candidate_quality": "low",
                "usable_for_search": False,
                "adapter_capability_status": "review",
                "adapter_capability_reason": "low_confidence_anchor_only_profile",
                "parser_profile_resolved": "fallback_anchor_only",
                "candidate_review_state": "relevance_review",
                "relevance_review_required": True,
            },
        },
        runtime_diagnostics=[
            {
                "site_url": "https://lane.example/search?q={{q}}",
                "domain": "lane.example",
                "site_policy": "keep",
                "search_service": "basic",
                "adapter_capability_status": "review",
                "adapter_capability_reason": "low_confidence_anchor_only_profile",
                "parser_profile_resolved": "fallback_anchor_only",
                "relevance_review_required": True,
                "relevance_review_reason": "term_fallback_candidates",
            },
            {
                "site_url": "https://mounting.example/search?q={{q}}",
                "domain": "mounting.example",
                "site_policy": "keep",
                "search_service": "basic",
                "adapter_capability_status": "allow",
                "parser_profile_resolved": "site_adaptive",
                "relevance_review_required": True,
                "relevance_review_reason": "mounted_search_chain_sample_requires_review",
            },
            {
                "site_url": "https://adapter.example/search?q={{q}}",
                "domain": "adapter.example",
                "site_policy": "keep",
                "search_service": "basic",
                "adapter_capability_status": "review",
                "adapter_capability_reason": "low_confidence_anchor_only_profile",
                "parser_profile_resolved": "fallback_anchor_only",
                "relevance_review_required": True,
                "relevance_review_reason": "adapter_capability_fixture_requires_review",
            },
            {
                "site_url": "https://migration.example/source?q={{q}}",
                "domain": "migration.example",
                "site_policy": "keep",
                "search_service": "url_pool",
                "adapter_capability_status": "review",
                "adapter_capability_reason": "low_confidence_anchor_only_profile",
                "parser_profile_resolved": "fallback_anchor_only",
                "relevance_review_required": True,
                "relevance_review_reason": "term_fallback_migration_candidate",
            },
        ],
        errors=[
            {
                "site_url": "https://lane.example/search?q={{q}}",
                "error": "url_term_filter_empty_fallback_used",
                "search_service_used": "basic",
            },
            {
                "site_url": "https://migration.example/source?q={{q}}",
                "error": "url_term_filter_empty_fallback_used",
                "search_service_used": "url_pool",
            },
        ],
        source_surface="checker.fixture.batch4",
    )


def _batch4_decision(entry: dict[str, Any]) -> dict[str, Any]:
    reviewer_fields = entry.get("reviewer_fields") if isinstance(entry.get("reviewer_fields"), dict) else {}
    reason_codes = [str(code) for code in entry.get("reason_codes") or []]
    decision = "reject_low_confidence_fixture_candidate"
    if reason_codes == ["source_marked_review_required"]:
        decision = "defer_source_marked_candidate_pending_human_review"

    return {
        "queue_id": entry.get("queue_id"),
        "url": reviewer_fields.get("url"),
        "domain": reviewer_fields.get("domain"),
        "source_library_item_key": reviewer_fields.get("source_library_item_key"),
        "candidate_source": reviewer_fields.get("candidate_source"),
        "decision": decision,
        "decision_basis": reason_codes,
        "review_scope": "deterministic_fixture_batch4_only",
        "effect": {
            "auto_accept_allowed": False,
            "auto_ingest_allowed": False,
            "closed_for_fixture_batch": True,
            "human_review_completed": False,
            "public_replay_completed": False,
            "live_source_collection_completed": False,
            "live_ingest_migration_completed": False,
        },
    }


def _remaining_gaps() -> dict[str, dict[str, str]]:
    return {
        "human_review": {
            "status": "open",
            "completion_claim": "not_claimed",
            "reason": "Batch4 fixture decisions are generated; live Current Dev human review evidence is absent.",
        },
        "public_replay": {
            "status": "open",
            "completion_claim": "not_claimed",
            "reason": "The checker is no-network and does not execute the opt-in public replay lane.",
        },
        "live_source_collection": {
            "status": "open",
            "completion_claim": "not_claimed",
            "reason": "Batch4 records source-collection review gaps without running live source collection.",
        },
        "live_ingest_migration": {
            "status": "open",
            "completion_claim": "not_claimed",
            "reason": "The fixture does not run live ingest canaries, external-project replay, or tenant DB writes.",
        },
    }


def build_expected_artifact(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    root = root.resolve()

    relevance = build_relevance_review_queue_check(root)
    taxonomy = build_taxonomy_review_readiness_check(root)
    search_governance = build_search_governance_check(root)
    wave16 = build_wave16_review_batch_check(root)
    wave18 = build_wave18_review_batch_check(root)
    wave19 = build_wave19_review_batch_check(root)
    batch4_queue = _batch4_fixture_queue()
    entries = [entry for entry in batch4_queue.get("entries") or [] if isinstance(entry, dict)]
    decisions = [_batch4_decision(entry) for entry in entries]
    queue_ids = [str(row.get("queue_id")) for row in decisions if row.get("queue_id")]

    wave16_artifact_check = wave16.get("artifact_check") if isinstance(wave16.get("artifact_check"), dict) else {}
    wave18_artifact_check = wave18.get("artifact_check") if isinstance(wave18.get("artifact_check"), dict) else {}
    wave19_artifact_check = wave19.get("artifact_check") if isinstance(wave19.get("artifact_check"), dict) else {}
    return {
        "contract_version": CONTRACT_VERSION,
        "batch_id": "wave20-source-library-review-closure-batch4-2026-05-22",
        "artifact_kind": "deterministic_fixture_review_batch4",
        "scope": {
            "source": (
                "Wave12 review queue + Wave14 taxonomy readiness + Wave16/Wave18/Wave19 deterministic batches "
                "+ batch4 cross-topic fixture queue"
            ),
            "fixture_only": True,
            "public_network_required": False,
            "public_network_attempted": False,
            "applies_to_full_current_dev_review": False,
            "applies_to_live_source_collection": False,
            "applies_to_live_ingest_migration": False,
        },
        "input_contracts": {
            "review_queue": {
                "contract_version": REVIEW_QUEUE_CONTRACT_VERSION,
                "validation_passed": _validation_passed(relevance),
                "queue_state": relevance.get("fixture", {}).get("queue", {}).get("queue_state")
                if isinstance(relevance.get("fixture"), dict)
                else None,
                "queued_count": relevance.get("fixture", {}).get("queue", {}).get("summary", {}).get("queued_count")
                if isinstance(relevance.get("fixture"), dict)
                else None,
            },
            "taxonomy_review_readiness": {
                "contract_version": TAXONOMY_REVIEW_READINESS_CONTRACT_VERSION,
                "validation_passed": _validation_passed(taxonomy),
                "taxonomy_readiness": taxonomy.get("governance_scope", {}).get("taxonomy_readiness"),
                "review_queue_ready": taxonomy.get("governance_scope", {}).get("review_queue_ready"),
                "human_review_completed": taxonomy.get("governance_scope", {}).get("human_review_completed"),
            },
            "search_chain_governance": {
                "contract_version": SEARCH_GOVERNANCE_CONTRACT_VERSION,
                "validation_passed": _validation_passed(search_governance),
                "public_network_attempted": _public_network_attempted(search_governance),
                "claims_full_45_site_public_replay": search_governance.get("governance_scope", {}).get(
                    "claims_full_45_site_public_replay"
                ),
                "claims_human_relevance_review_complete": search_governance.get("governance_scope", {}).get(
                    "claims_human_relevance_review_complete"
                ),
            },
            "wave16_review_batch": {
                "contract_version": WAVE16_REVIEW_BATCH_CONTRACT_VERSION,
                "validation_passed": _validation_passed(wave16),
                "artifact_path": WAVE16_ARTIFACT_PATH.as_posix(),
                "batch_state": wave16_artifact_check.get("batch_state"),
                "decision_count": wave16_artifact_check.get("decision_count"),
            },
            "wave18_review_batch": {
                "contract_version": WAVE18_REVIEW_BATCH_CONTRACT_VERSION,
                "validation_passed": _validation_passed(wave18),
                "artifact_path": WAVE18_ARTIFACT_PATH.as_posix(),
                "batch_state": wave18_artifact_check.get("batch_state"),
                "decision_count": wave18_artifact_check.get("decision_count"),
            },
            "wave19_review_batch": {
                "contract_version": WAVE19_REVIEW_BATCH_CONTRACT_VERSION,
                "validation_passed": _validation_passed(wave19),
                "artifact_path": WAVE19_ARTIFACT_PATH.as_posix(),
                "batch_state": wave19_artifact_check.get("batch_state"),
                "decision_count": wave19_artifact_check.get("decision_count"),
            },
            "batch4_fixture_queue": {
                "contract_version": REVIEW_QUEUE_CONTRACT_VERSION,
                "queue_state": batch4_queue.get("queue_state"),
                "queued_count": batch4_queue.get("summary", {}).get("queued_count"),
                "queue_ids": sorted(queue_ids),
            },
        },
        "review_batch": {
            "state": "closed_for_fourth_deterministic_fixture_batch",
            "deterministic_batch4_closed": True,
            "closed_queue_ids": sorted(queue_ids),
            "decision_count": len(decisions),
            "decisions": decisions,
            "previous_batch_dependencies": [
                {
                    "contract_version": WAVE16_REVIEW_BATCH_CONTRACT_VERSION,
                    "artifact_path": WAVE16_ARTIFACT_PATH.as_posix(),
                    "validation_passed": _validation_passed(wave16),
                },
                {
                    "contract_version": WAVE18_REVIEW_BATCH_CONTRACT_VERSION,
                    "artifact_path": WAVE18_ARTIFACT_PATH.as_posix(),
                    "validation_passed": _validation_passed(wave18),
                },
                {
                    "contract_version": WAVE19_REVIEW_BATCH_CONTRACT_VERSION,
                    "artifact_path": WAVE19_ARTIFACT_PATH.as_posix(),
                    "validation_passed": _validation_passed(wave19),
                },
            ],
        },
        "topic_coverage": {
            topic: {"wave20_evidence_doc": _resolve_existing_relative(root, paths).as_posix()}
            for topic, paths in sorted(EVIDENCE_DOCS.items())
        },
        "remaining_gaps": _remaining_gaps(),
        "non_closure_markers": {
            "claims_human_review_complete": False,
            "claims_human_relevance_review_complete": False,
            "claims_public_replay_complete": False,
            "claims_live_public_replay_complete": False,
            "claims_full_45_site_public_replay": False,
            "claims_live_source_collection_complete": False,
            "claims_live_ingest_migration_complete": False,
            "claims_current_dev_topic_archived": False,
            "shared_indexes_edited": False,
        },
        "remaining_boundaries": [
            "Human review remains open until live Current Dev candidate evidence is supplied.",
            "Public replay remains open until the opt-in public replay lane is executed.",
            "Live source collection remains open until live collection artifacts are produced.",
            "Live ingest migration remains open until live canary/external-project replay evidence is produced.",
            "Integration branch must update shared indexes after worker merge.",
        ],
    }


def _compare_artifact(expected: dict[str, Any], actual: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    actual_batch = actual.get("review_batch") if isinstance(actual.get("review_batch"), dict) else {}
    actual_non_closure = (
        actual.get("non_closure_markers") if isinstance(actual.get("non_closure_markers"), dict) else {}
    )
    actual_scope = actual.get("scope") if isinstance(actual.get("scope"), dict) else {}
    actual_gaps = actual.get("remaining_gaps") if isinstance(actual.get("remaining_gaps"), dict) else {}
    expected_batch = expected["review_batch"]

    _require(actual.get("contract_version") == CONTRACT_VERSION, errors, "artifact contract version mismatch")
    _require(actual.get("batch_id") == expected.get("batch_id"), errors, "artifact batch_id mismatch")
    _require(
        actual_scope.get("fixture_only") is True and actual_scope.get("public_network_attempted") is False,
        errors,
        "artifact scope must be fixture-only and no-network",
    )
    _require(
        actual_scope.get("applies_to_live_source_collection") is False,
        errors,
        "artifact must not claim live source collection applicability",
    )
    _require(
        actual_scope.get("applies_to_live_ingest_migration") is False,
        errors,
        "artifact must not claim live ingest migration applicability",
    )
    _require(
        actual_batch.get("state") == expected_batch.get("state"),
        errors,
        "artifact review batch state mismatch",
    )
    _require(
        actual_batch.get("deterministic_batch4_closed") is True,
        errors,
        "artifact must close the fourth deterministic fixture batch",
    )
    _require(
        actual_batch.get("closed_queue_ids") == expected_batch.get("closed_queue_ids"),
        errors,
        "artifact closed queue ids do not match generated batch4 queue",
    )
    _require(
        actual_batch.get("decision_count") == expected_batch.get("decision_count"),
        errors,
        "artifact decision count mismatch",
    )
    _require(
        actual_batch.get("decisions") == expected_batch.get("decisions"),
        errors,
        "artifact decisions do not match generated batch4 fixture decisions",
    )
    for key in ("human_review", "public_replay", "live_source_collection", "live_ingest_migration"):
        gap = actual_gaps.get(key) if isinstance(actual_gaps.get(key), dict) else {}
        _require(gap.get("status") == "open", errors, f"remaining gap must stay open: {key}")
        _require(gap.get("completion_claim") == "not_claimed", errors, f"remaining gap must not claim closure: {key}")
    for key in (
        "claims_human_review_complete",
        "claims_human_relevance_review_complete",
        "claims_public_replay_complete",
        "claims_live_public_replay_complete",
        "claims_full_45_site_public_replay",
        "claims_live_source_collection_complete",
        "claims_live_ingest_migration_complete",
        "claims_current_dev_topic_archived",
        "shared_indexes_edited",
    ):
        _require(actual_non_closure.get(key) is False, errors, f"artifact non-closure marker must be false: {key}")
    return {
        "path": DEFAULT_ARTIFACT_PATH.as_posix(),
        "exists": bool(actual),
        "contract_version": actual.get("contract_version"),
        "batch_state": actual_batch.get("state"),
        "closed_queue_ids": actual_batch.get("closed_queue_ids") or [],
        "decision_count": actual_batch.get("decision_count"),
        "remaining_gap_keys": sorted(actual_gaps),
    }


def _build_doc_check(root: Path, errors: list[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for topic, candidates in sorted(EVIDENCE_DOCS.items()):
        relative = _resolve_existing_relative(root, candidates)
        text = _read_text(root, relative)
        missing_markers = [marker for marker in REQUIRED_DOC_MARKERS if marker not in text]
        rows.append(
            {
                "topic": topic,
                "path": relative.as_posix(),
                "candidate_paths": [path.as_posix() for path in candidates],
                "exists": bool(text),
                "missing_markers": missing_markers,
            }
        )
        _require(bool(text), errors, f"missing Wave20 topic evidence doc: {relative.as_posix()}")
        _require(
            not missing_markers,
            errors,
            f"Wave20 topic evidence doc missing markers: {relative.as_posix()}: {missing_markers}",
        )
    return {
        "docs": rows,
        "forbidden_shared_indexes": sorted(FORBIDDEN_SHARED_INDEXES),
    }


def build_check(
    repo_root: Path | str | None = None,
    *,
    artifact_path: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    root = root.resolve()
    artifact = (root / Path(artifact_path or DEFAULT_ARTIFACT_PATH)).resolve()
    errors: list[str] = []

    expected_artifact = build_expected_artifact(root)
    upstream_checks = expected_artifact["input_contracts"]
    for name, row in upstream_checks.items():
        if isinstance(row, dict) and "validation_passed" in row:
            _require(bool(row.get("validation_passed")), errors, f"upstream check failed: {name}")
    _require(
        upstream_checks["batch4_fixture_queue"].get("queued_count") == 4,
        errors,
        "batch4 fixture queue must contain four review candidates",
    )

    actual_artifact = _load_json(artifact)
    _require(bool(actual_artifact), errors, f"missing or invalid review batch4 artifact: {artifact}")
    artifact_check = _compare_artifact(expected_artifact, actual_artifact, errors)
    docs = _build_doc_check(root, errors)

    return {
        "contract_version": CONTRACT_VERSION,
        "repo_root": str(root),
        "expected_artifact": expected_artifact,
        "artifact_check": artifact_check,
        "topic_evidence": docs,
        "governance_scope": {
            "public_network_required": False,
            "public_network_attempted": False,
            "deterministic_batch4_closed": True,
            "claims_human_review_complete": False,
            "claims_human_relevance_review_complete": False,
            "claims_public_replay_complete": False,
            "claims_live_public_replay_complete": False,
            "claims_live_source_collection_complete": False,
            "claims_live_ingest_migration_complete": False,
            "shared_indexes_edited": False,
        },
        "validation": {
            "passed": not errors,
            "errors": errors,
            "public_network_attempted": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave20 source-library deterministic review closure batch 4.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT_PATH)
    parser.add_argument("--write-artifact", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    root = Path(args.repo_root) if args.repo_root is not None else REPO_ROOT
    root = root.resolve()
    artifact_path = (root / args.artifact).resolve()
    if args.write_artifact:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(build_expected_artifact(root), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    result = build_check(root, artifact_path=artifact_path)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        output_path = (root / args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
