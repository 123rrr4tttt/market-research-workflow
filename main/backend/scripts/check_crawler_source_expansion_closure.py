from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "crawler_source_expansion.closure_check.v1"
TOPIC_DIR = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-03-07-crawler-source-expansion"
)
WAVE6_DOC = TOPIC_DIR / "2026-05-22-wave6-closure-gap-and-min-plan.md"
WAVE7_A5_DOC = TOPIC_DIR / "2026-05-22-wave7-a5-public-replay-evidence.md"

PROTECTED_SHARED_INDEXES = [
    "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md",
    "development/latest-dev-docs/development-plans/INDEX.md",
    "development/latest-dev-docs/README.md",
    "development/latest-dev-docs/MERGED_OVERVIEW.md",
]


@dataclass(frozen=True)
class Anchor:
    path: Path
    tokens: tuple[str, ...] = ()


ANCHORS: dict[str, Anchor] = {
    "topic_plan": Anchor(TOPIC_DIR / "01_crawler-source-expansion-plan-2026-03-07.md"),
    "topic_tasklist": Anchor(TOPIC_DIR / "02_atomic-tasklist-crawler-source-expansion-2026-03-07.md"),
    "wave6_closure_doc": Anchor(WAVE6_DOC, ("Closure Decision", "Minimum Development Plan")),
    "wave7_a5_public_replay_doc": Anchor(
        WAVE7_A5_DOC,
        ("A5 Gate Decision", "Deterministic Gate", "External Blocker"),
    ),
    "crawler_api": Anchor(Path("main/backend/app/api/crawler.py")),
    "source_library_api": Anchor(Path("main/backend/app/api/source_library.py")),
    "source_library_types": Anchor(
        Path("main/backend/app/services/source_library/types.py"),
        (
            "class SourceTier",
            "class SourceOnboardingPriority",
            "def derive_source_tiering",
            "def default_source_layer_boundary",
            "class FrontDoorExecutionProtocol",
        ),
    ),
    "collect_runtime_contracts": Anchor(
        Path("main/backend/app/services/collect_runtime/contracts.py"),
        ("class CollectRequest", "class CollectResult"),
    ),
    "crawler_dispatch_contracts": Anchor(
        Path("main/backend/app/services/crawlers/base.py"),
        ("class CrawlerDispatchRequest", "class CrawlerDispatchResult"),
    ),
    "source_library_resolver": Anchor(
        Path("main/backend/app/services/source_library/resolver.py"),
        ("source_tier", "onboarding_priority", "middle_layer_protocol"),
    ),
    "source_library_runner": Anchor(
        Path("main/backend/app/services/source_library/runner.py"),
        ("source_tiering", "layer_boundary", "provider_dispatch"),
    ),
    "collect_source_library_adapter": Anchor(
        Path("main/backend/app/services/collect_runtime/adapters/source_library.py"),
        ("def to_source_library_response", "def build_source_library_authority_output"),
    ),
    "crawler_bridge": Anchor(
        Path("main/backend/app/services/crawlers/bridge.py"),
        ("def submit_crawler_job", "def poll_crawler_job"),
    ),
    "clue_chain_source_expansion": Anchor(
        Path("main/backend/app/services/clue_chains/source_library_expansion.py"),
        ("def expand_source_library_hop", "replay_manifest", "network_fetch_performed"),
    ),
    "quality_meaningful_gate": Anchor(Path("main/backend/app/services/ingest/meaningful_gate.py")),
    "quality_llm_validator": Anchor(Path("main/backend/app/services/resource_pool/llm_validator.py")),
    "quality_discovery_store": Anchor(Path("main/backend/app/services/discovery/store.py")),
    "source_replay_script": Anchor(
        Path("main/backend/scripts/source_library_replay_scaleout.py"),
        ("DEFAULT_HISTORICAL_TARGETS", "def validate_manifest_targets", "def run_replay"),
    ),
    "source_real_probe_script": Anchor(
        Path("main/backend/scripts/source_library_real_probes.py"),
        ("def run_probe", "site_entry_discovery", "transport_resilience"),
    ),
    "source_public_live_probe_script": Anchor(
        Path("main/backend/scripts/source_library_public_live_probes.py"),
        ("def run_probe", "live_evidence_sufficient", "allow_public_network"),
    ),
    "source_public_replay_a5_gate_script": Anchor(
        Path("main/backend/scripts/check_source_library_public_replay_a5_gate.py"),
        ("CONTRACT_VERSION", "def build_check", "external_public_network_or_site_stability"),
    ),
    "source_replay_scaleout_evidence": Anchor(
        Path("development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/README.md"),
        ("45-site", "not closed"),
    ),
    "source_real_probe_evidence": Anchor(
        Path("development/latest-dev-docs/automation-runs/source-library-real-probes/2026-05-22/README.md"),
        ("Deterministic local", "Dirty-source shortlist"),
    ),
    "source_live_probe_evidence": Anchor(
        Path("development/latest-dev-docs/automation-runs/source-library-live-probes/2026-05-22/README.md"),
        ("candidate_ready", "relevance_review"),
    ),
    "ingest_frontdoor_evidence": Anchor(
        Path("development/latest-dev-docs/automation-runs/ingest-frontdoor-closure/2026-05-22/README.md"),
        ("source_library.resolver.run_item_with_url_routing", "partial"),
    ),
    "test_source_tiering": Anchor(
        Path("main/backend/tests/unit/test_source_library_resolver_unittest.py"),
        ("attaches_source_tiering_contract", "injects_channel_source_tiering_into_protocol"),
    ),
    "test_runner_boundary": Anchor(
        Path("main/backend/tests/unit/test_source_library_runner_gray_rollout_unittest.py"),
        ("source_tiering", "layer_boundary"),
    ),
    "test_collect_adapter": Anchor(
        Path("main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py"),
        ("authority_output", "frontdoor_ingress"),
    ),
    "test_crawler_bridge": Anchor(
        Path("main/backend/tests/unit/test_crawler_management_bridge_unittest.py"),
        ("submit_crawler_job", "poll_crawler_job"),
    ),
    "test_clue_chain_source_expansion": Anchor(
        Path("main/backend/tests/unit/test_clue_chain_source_library_expansion_unittest.py"),
        ("fixture_required", "network_fetch_performed"),
    ),
    "test_source_library_public_replay_a5_gate": Anchor(
        Path("main/backend/tests/unit/test_source_library_public_replay_a5_gate_unittest.py"),
        ("deterministic_replay_gate_closed_external_public_replay_blocked", "review_required_not_full_closure"),
    ),
}


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
    missing_tokens: list[str] = []
    if exists and anchor.tokens:
        text = _read_text(path)
        missing_tokens = [token for token in anchor.tokens if token not in text]
    return {
        "key": key,
        "path": str(anchor.path),
        "exists": exists,
        "tokens_checked": list(anchor.tokens),
        "missing_tokens": missing_tokens,
        "passed": exists and not missing_tokens,
    }


def _passed(anchor_results: dict[str, dict[str, Any]], keys: list[str]) -> bool:
    return all(bool(anchor_results[key]["passed"]) for key in keys)


def _task(
    task_id: str,
    title: str,
    status: str,
    anchor_keys: list[str],
    anchor_results: dict[str, dict[str, Any]],
    evidence: str,
    gap: str,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "title": title,
        "status": status,
        "anchors": [anchor_results[key] for key in anchor_keys],
        "evidence": evidence,
        "gap": gap,
    }


def build_check(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    anchor_results = {key: _anchor_result(root, key, anchor) for key, anchor in ANCHORS.items()}

    a1_keys = [
        "topic_plan",
        "topic_tasklist",
        "crawler_api",
        "source_library_api",
        "source_library_types",
        "collect_runtime_contracts",
        "crawler_dispatch_contracts",
    ]
    a2_keys = ["source_library_types", "source_library_resolver", "test_source_tiering"]
    a3_keys = [
        "source_library_types",
        "collect_runtime_contracts",
        "crawler_dispatch_contracts",
        "source_library_runner",
        "crawler_bridge",
        "test_runner_boundary",
        "test_crawler_bridge",
    ]
    a4_keys = [
        "quality_meaningful_gate",
        "quality_llm_validator",
        "quality_discovery_store",
        "source_real_probe_evidence",
        "source_live_probe_evidence",
    ]
    a5_keys = [
        "source_replay_script",
        "source_public_live_probe_script",
        "source_public_replay_a5_gate_script",
        "source_replay_scaleout_evidence",
        "source_live_probe_evidence",
        "wave7_a5_public_replay_doc",
        "test_source_library_public_replay_a5_gate",
    ]
    a6_keys = [
        "collect_source_library_adapter",
        "collect_runtime_contracts",
        "source_library_resolver",
        "ingest_frontdoor_evidence",
        "test_collect_adapter",
    ]
    a7_keys = ["wave6_closure_doc", "test_clue_chain_source_expansion", "clue_chain_source_expansion"]

    tasks = [
        _task(
            "A1",
            "Verify baseline inventory and layer map",
            "closed" if _passed(anchor_results, a1_keys) else "needs_update",
            a1_keys,
            anchor_results,
            "The original code anchors still exist and include source_library, collect_runtime, crawler dispatch, and APIs.",
            "" if _passed(anchor_results, a1_keys) else "Refresh the baseline inventory before using downstream task statuses.",
        ),
        _task(
            "A2",
            "Freeze source tiering and priority model",
            "closed" if _passed(anchor_results, a2_keys) else "needs_update",
            a2_keys,
            anchor_results,
            "SourceTier, onboarding priority, resolver propagation, and unit assertions are present.",
            "" if _passed(anchor_results, a2_keys) else "Tiering code or assertions are missing.",
        ),
        _task(
            "A3",
            "Freeze layer responsibilities and onboarding boundary",
            "closed" if _passed(anchor_results, a3_keys) else "needs_update",
            a3_keys,
            anchor_results,
            "Layer boundary metadata and crawler bridge tests now cover source catalog, runtime, and provider dispatch.",
            "" if _passed(anchor_results, a3_keys) else "Boundary code or tests are missing.",
        ),
        _task(
            "A4",
            "Define minimum quality, dedupe, and stability rules",
            "needs_update" if _passed(anchor_results, a4_keys) else "not_closed",
            a4_keys,
            anchor_results,
            "Quality anchors and probe evidence exist, including local fixture and public live probe artifacts.",
            "The plan still needs a final source-layer allow/downgrade/block matrix tied to enforcement points.",
        ),
        _task(
            "A5",
            "Define directed-source onboarding strategy",
            "blocked_external" if _passed(anchor_results, a5_keys) else "needs_update",
            a5_keys,
            anchor_results,
            "The 45-site historical manifest, no-network replay gate, public-live fixture, A5 checker, and term-fallback relevance-review test are represented.",
            "Full 45-site public replay remains an external public-network/site-stability blocker; term-fallback rows stay review evidence, not clean closure.",
        ),
        _task(
            "A6",
            "Freeze minimum source-to-ingest handoff contract",
            "needs_update" if _passed(anchor_results, a6_keys) else "not_closed",
            a6_keys,
            anchor_results,
            "Source-library terminal/authority output and frontdoor ingress mapping exist with focused unit coverage.",
            "Provider-specific crawler and high-JS/browser handoff closure remains broader than this evidence.",
        ),
        _task(
            "A7",
            "Validation pack and documentation closure",
            "not_closed" if _passed(anchor_results, a7_keys) else "needs_update",
            a7_keys,
            anchor_results,
            "A Wave6 closure-gap document and fixture-replay clue-chain assertions provide a repeatable status baseline.",
            "Do not move the topic or edit shared indexes until A4-A6 blockers close.",
        ),
    ]

    errors = [
        f"{result['key']}: missing {result['path']}"
        for result in anchor_results.values()
        if not result["exists"] and result["key"] != "wave6_closure_doc"
    ]
    errors.extend(
        f"{result['key']}: missing tokens {result['missing_tokens']}"
        for result in anchor_results.values()
        if result["exists"] and result["missing_tokens"]
    )
    if not anchor_results["wave6_closure_doc"]["exists"]:
        errors.append("wave6_closure_doc: missing Wave6 closure-gap document")

    blockers = [task for task in tasks if task["status"] != "closed"]
    return {
        "contract_version": CONTRACT_VERSION,
        "repo_root": str(root),
        "topic_dir": str(TOPIC_DIR),
        "overall_status": "not_closed" if blockers else "closed",
        "doc_drift": {
            "status": "outdated_snapshot",
            "reason": "The 2026-03-07 tasklist still marks A1-A7 pending, while A1-A3 now have code/test evidence.",
        },
        "tasks": tasks,
        "minimum_development_plan": [
            "Keep A1-A3 as evidence-closed and update only topic-local documentation until integration.",
            "Close A4 by pinning a source-layer allow/downgrade/block matrix to existing resolver/probe enforcement points.",
            "Treat A5 as deterministic-gate sealed but externally blocked until an opt-in 45-site public replay can be rerun and stored.",
            "Close A6 after crawler/provider-specific handoff cases are covered by focused source_library/ingest tests.",
            "Update shared navigation only in a later integration lane.",
        ],
        "protected_shared_indexes": PROTECTED_SHARED_INDEXES,
        "validation": {
            "passed": not errors,
            "errors": errors,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check crawler source expansion closure evidence.")
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
