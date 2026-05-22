from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "crawler_policy_matrix.v1"
TOPIC_DIR = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-03-07-crawler-source-expansion"
)
POLICY_MATRIX_DOC = TOPIC_DIR / "2026-05-22-wave7-crawler-policy-matrix.md"
POLICY_ACTIONS = ("allow", "downgrade", "block")


@dataclass(frozen=True)
class Anchor:
    path: Path
    tokens: tuple[str, ...]


ANCHORS: dict[str, Anchor] = {
    "policy_matrix_doc": Anchor(
        POLICY_MATRIX_DOC,
        (
            "source_policy_action",
            "`allow`",
            "`downgrade`",
            "`block`",
            "Resolver/probe binding",
            "Enforcement and downstream binding",
        ),
    ),
    "source_candidate_trust": Anchor(
        Path("main/backend/app/services/source_library/source_candidate_trust.py"),
        (
            "SOURCE_POLICY_ACTIONS",
            "source_policy_action",
            "source_policy_reason",
            "duplicate_candidate_url",
            "medium_trust_candidate_requires_review_before_bulk_ingest",
        ),
    ),
    "source_library_resolver": Anchor(
        Path("main/backend/app/services/source_library/resolver.py"),
        (
            "source_tier",
            "onboarding_priority",
            "middle_layer_protocol",
            "force_crawler_fallback_on_empty",
            "site_policy_breakdown",
        ),
    ),
    "ingest_meaningful_gate": Anchor(
        Path("main/backend/app/services/ingest/meaningful_gate.py"),
        (
            "class GateDecision",
            "def url_policy_check",
            "def content_quality_check",
            "def build_gateplus_snapshot",
        ),
    ),
    "resource_pool_llm_validator": Anchor(
        Path("main/backend/app/services/resource_pool/llm_validator.py"),
        (
            "validate_llm_recommendation",
            "_ALLOWED_ENTRY_TYPES",
            "_ALLOWED_CHANNEL_KEYS",
        ),
    ),
    "discovery_store": Anchor(
        Path("main/backend/app/services/discovery/store.py"),
        (
            "def _discovery_gate_check",
            "url_policy_check",
            "content_quality_check",
            "build_discovery_ingress_envelope",
            "run_postprocess_frontdoor",
            "def _sha256",
        ),
    ),
    "policy_matrix_test": Anchor(
        Path("main/backend/tests/unit/test_crawler_policy_matrix_check_unittest.py"),
        (
            "test_policy_matrix_binds_all_actions_to_existing_anchors",
            "test_policy_matrix_keeps_shared_navigation_out_of_scope",
        ),
    ),
    "source_candidate_trust_test": Anchor(
        Path("main/backend/tests/unit/test_source_candidate_trust_unittest.py"),
        (
            "source_policy_action",
            "test_plan_marks_medium_trust_candidates_as_downgraded_review_path",
        ),
    ),
}

PROTECTED_SHARED_INDEXES = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md",
    "development/latest-dev-docs/development-plans/INDEX.md",
    "development/latest-dev-docs/README.md",
    "development/latest-dev-docs/MERGED_OVERVIEW.md",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _anchor_result(root: Path, key: str, anchor: Anchor) -> dict[str, Any]:
    path = root / anchor.path
    exists = path.is_file()
    text = _read_text(path) if exists else ""
    missing_tokens = [token for token in anchor.tokens if token not in text]
    return {
        "key": key,
        "path": str(anchor.path),
        "exists": exists,
        "tokens_checked": list(anchor.tokens),
        "missing_tokens": missing_tokens,
        "passed": exists and not missing_tokens,
    }


def _doc_decision_coverage(root: Path) -> dict[str, Any]:
    path = root / POLICY_MATRIX_DOC
    text = _read_text(path) if path.is_file() else ""
    coverage: dict[str, bool] = {}
    for action in POLICY_ACTIONS:
        coverage[action] = (
            f"`{action}`" in text
            and f"source_policy_action={action}" in text
        )
    return {
        "policy_actions": list(POLICY_ACTIONS),
        "coverage": coverage,
        "passed": all(coverage.values()),
    }


def build_check(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    anchors = {key: _anchor_result(root, key, anchor) for key, anchor in ANCHORS.items()}
    doc_coverage = _doc_decision_coverage(root)

    errors: list[str] = []
    errors.extend(
        f"{result['key']}: missing {result['path']}"
        for result in anchors.values()
        if not result["exists"]
    )
    errors.extend(
        f"{result['key']}: missing tokens {result['missing_tokens']}"
        for result in anchors.values()
        if result["exists"] and result["missing_tokens"]
    )
    if not doc_coverage["passed"]:
        missing = [
            action
            for action, covered in dict(doc_coverage["coverage"]).items()
            if not covered
        ]
        errors.append(f"policy_matrix_doc: missing decision coverage {missing}")

    return {
        "contract_version": CONTRACT_VERSION,
        "repo_root": str(root),
        "topic_dir": str(TOPIC_DIR),
        "policy_matrix_doc": str(POLICY_MATRIX_DOC),
        "policy_actions": list(POLICY_ACTIONS),
        "anchors": anchors,
        "doc_decision_coverage": doc_coverage,
        "protected_shared_indexes": list(PROTECTED_SHARED_INDEXES),
        "validation": {
            "passed": not errors,
            "errors": errors,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check crawler source-layer policy matrix coverage.")
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
