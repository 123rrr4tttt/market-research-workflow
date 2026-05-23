#!/usr/bin/env python3
"""Wave16 deterministic review-batch gate for source-library review/taxonomy closure."""

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
from scripts.check_source_library_relevance_review_queue import (  # noqa: E402
    build_check as build_relevance_review_queue_check,
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


CONTRACT_VERSION = "source_library.review_closure_batch.v1"
RUN_DIR = Path("development/latest-dev-docs/automation-runs/source-library-review-closure-batch/2026-05-22")
DEFAULT_ARTIFACT_PATH = RUN_DIR / "review_batch.json"
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
        "10_wave16-review-closure-batch-2026-05-22.md",
    ),
    "search_chain": _evidence_doc_candidates(
        "2026-03-14-search-chain-source-library-mounting-audit",
        "06_wave16-review-closure-batch-2026-05-22.md",
    ),
    "adapter_capability": _evidence_doc_candidates(
        "2026-03-14-source-library-adapter-capability-remediation",
        "16_wave16-review-closure-batch-2026-05-22.md",
    ),
    "minimal_migration": _evidence_doc_candidates(
        "2026-03-25-source-library-ingest-minimal-migration",
        "13_wave16-review-closure-batch-2026-05-22.md",
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
    "deterministic_batch_closed=true",
    "claims_human_relevance_review_complete=false",
    "claims_live_public_replay_complete=false",
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


def _batch_decision(entry: dict[str, Any]) -> dict[str, Any]:
    reviewer_fields = entry.get("reviewer_fields") if isinstance(entry.get("reviewer_fields"), dict) else {}
    return {
        "queue_id": entry.get("queue_id"),
        "url": reviewer_fields.get("url"),
        "domain": reviewer_fields.get("domain"),
        "source_library_item_key": reviewer_fields.get("source_library_item_key"),
        "decision": "reject_low_confidence_fixture_candidate",
        "decision_basis": [
            "fallback_anchor_only_profile",
            "term_fallback_candidates",
            "low_confidence_candidate",
            "adapter_capability_review",
        ],
        "review_scope": "deterministic_fixture_batch_only",
        "effect": {
            "auto_accept_allowed": False,
            "auto_ingest_allowed": False,
            "closed_for_fixture_batch": True,
            "human_relevance_review_completed": False,
            "live_public_replay_completed": False,
        },
    }


def build_expected_artifact(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    root = root.resolve()

    relevance = build_relevance_review_queue_check(root)
    taxonomy = build_taxonomy_review_readiness_check(root)
    search_governance = build_search_governance_check(root)
    queue = relevance.get("fixture", {}).get("queue") if isinstance(relevance.get("fixture"), dict) else {}
    entries = [entry for entry in queue.get("entries") or [] if isinstance(entry, dict)] if isinstance(queue, dict) else []
    decisions = [_batch_decision(entry) for entry in entries]
    queue_ids = [str(row.get("queue_id")) for row in decisions if row.get("queue_id")]

    return {
        "contract_version": CONTRACT_VERSION,
        "batch_id": "wave16-source-library-review-closure-batch-2026-05-22",
        "artifact_kind": "deterministic_fixture_review_batch",
        "scope": {
            "source": "Wave12 review queue + Wave14 taxonomy readiness + Search Governance no-network gate",
            "fixture_only": True,
            "public_network_required": False,
            "public_network_attempted": False,
            "applies_to_full_current_dev_review": False,
        },
        "input_contracts": {
            "review_queue": {
                "contract_version": REVIEW_QUEUE_CONTRACT_VERSION,
                "validation_passed": _validation_passed(relevance),
                "queue_state": queue.get("queue_state") if isinstance(queue, dict) else None,
                "queued_count": queue.get("summary", {}).get("queued_count") if isinstance(queue.get("summary"), dict) else None,
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
        },
        "review_batch": {
            "state": "closed_for_deterministic_fixture_batch",
            "deterministic_batch_closed": True,
            "closed_queue_ids": sorted(queue_ids),
            "decision_count": len(decisions),
            "decisions": decisions,
        },
        "topic_coverage": {
            topic: {"wave16_evidence_doc": _resolve_existing_relative(root, paths).as_posix()}
            for topic, paths in sorted(EVIDENCE_DOCS.items())
        },
        "non_closure_markers": {
            "claims_human_relevance_review_complete": False,
            "claims_live_public_replay_complete": False,
            "claims_full_45_site_public_replay": False,
            "claims_current_dev_topic_archived": False,
            "shared_indexes_edited": False,
        },
        "remaining_boundaries": [
            "Full human relevance review for live Current Dev candidates remains open.",
            "Opt-in 45-site public replay remains open and environment-dependent.",
            "Integration branch must update shared indexes after worker merge.",
        ],
    }


def _compare_artifact(expected: dict[str, Any], actual: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    actual_batch = actual.get("review_batch") if isinstance(actual.get("review_batch"), dict) else {}
    actual_non_closure = (
        actual.get("non_closure_markers") if isinstance(actual.get("non_closure_markers"), dict) else {}
    )
    actual_scope = actual.get("scope") if isinstance(actual.get("scope"), dict) else {}
    expected_batch = expected["review_batch"]

    _require(actual.get("contract_version") == CONTRACT_VERSION, errors, "artifact contract version mismatch")
    _require(actual.get("batch_id") == expected.get("batch_id"), errors, "artifact batch_id mismatch")
    _require(
        actual_scope.get("fixture_only") is True and actual_scope.get("public_network_attempted") is False,
        errors,
        "artifact scope must be fixture-only and no-network",
    )
    _require(
        actual_batch.get("state") == expected_batch.get("state"),
        errors,
        "artifact review batch state mismatch",
    )
    _require(
        actual_batch.get("deterministic_batch_closed") is True,
        errors,
        "artifact must close the deterministic fixture batch",
    )
    _require(
        actual_batch.get("closed_queue_ids") == expected_batch.get("closed_queue_ids"),
        errors,
        "artifact closed queue ids do not match generated queue",
    )
    _require(
        actual_batch.get("decision_count") == expected_batch.get("decision_count"),
        errors,
        "artifact decision count mismatch",
    )
    _require(
        actual_batch.get("decisions") == expected_batch.get("decisions"),
        errors,
        "artifact decisions do not match generated fixture decisions",
    )
    for key in (
        "claims_human_relevance_review_complete",
        "claims_live_public_replay_complete",
        "claims_full_45_site_public_replay",
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
        _require(bool(text), errors, f"missing Wave16 topic evidence doc: {relative.as_posix()}")
        _require(
            not missing_markers,
            errors,
            f"Wave16 topic evidence doc missing markers: {relative.as_posix()}: {missing_markers}",
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
        _require(bool(row.get("validation_passed")), errors, f"upstream check failed: {name}")

    actual_artifact = _load_json(artifact)
    _require(bool(actual_artifact), errors, f"missing or invalid review batch artifact: {artifact}")
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
            "deterministic_batch_closed": True,
            "claims_human_relevance_review_complete": False,
            "claims_live_public_replay_complete": False,
            "claims_full_45_site_public_replay": False,
            "shared_indexes_edited": False,
        },
        "validation": {
            "passed": not errors,
            "errors": errors,
            "public_network_attempted": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave16 source-library deterministic review closure batch.")
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
