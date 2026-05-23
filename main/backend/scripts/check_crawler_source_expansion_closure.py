from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.check_crawler_public_replay_gate import build_check as build_public_replay_gate_check
from scripts.check_source_library_public_replay_a5_gate import build_check as build_a5_gate_check


CONTRACT_VERSION = "crawler_source_expansion.closure_check.v1"
TOPIC_DIR = Path(
    "docs/development/development-plans/ARCHIVE_CLOSED/"
    "2026-03-07-crawler-source-expansion"
)
WAVE6_DOC = TOPIC_DIR / "2026-05-22-wave6-closure-gap-and-min-plan.md"
WAVE7_POLICY_MATRIX_DOC = TOPIC_DIR / "2026-05-22-wave7-crawler-policy-matrix.md"
WAVE7_A5_DOC = TOPIC_DIR / "2026-05-22-wave7-a5-public-replay-evidence.md"
WAVE8_A7_DOC = TOPIC_DIR / "2026-05-22-wave8-a7-validation-pack.md"
WAVE13_PUBLIC_REPLAY_DOC = TOPIC_DIR / "2026-05-22-wave13-worker7-crawler-public-replay-gate.md"
WAVE47_PUBLIC_REPLAY_CLOSURE_DOC = TOPIC_DIR / "10_wave47-manual-public-replay-closure-2026-05-23.md"
WAVE8_A7_RUN_DIR = Path(
    "development/latest-dev-docs/automation-runs/"
    "crawler-source-expansion-wave8-a7-validation-pack/2026-05-22"
)
WAVE13_PUBLIC_REPLAY_RUN_DIR = Path(
    "development/latest-dev-docs/automation-runs/"
    "crawler-public-replay-gate/2026-05-22"
)

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
    "wave7_policy_matrix_doc": Anchor(
        WAVE7_POLICY_MATRIX_DOC,
        ("source_policy_action", "`allow`", "`downgrade`", "`block`", "Executable Check"),
    ),
    "wave7_a5_public_replay_doc": Anchor(
        WAVE7_A5_DOC,
        ("A5 Gate Decision", "Deterministic Gate", "External Blocker"),
    ),
    "wave8_a7_validation_pack_doc": Anchor(
        WAVE8_A7_DOC,
        ("A7 Validation Pack", "External Blocker Boundary", "Repeatable Commands", "Overall Status"),
    ),
    "wave13_public_replay_doc": Anchor(
        WAVE13_PUBLIC_REPLAY_DOC,
        ("Wave13 Worker 7 Crawler Public Replay Gate", "Live 45-site public replay remains not closed"),
    ),
    "wave47_manual_public_replay_closure_doc": Anchor(
        WAVE47_PUBLIC_REPLAY_CLOSURE_DOC,
        (
            "Wave47 Manual Public Replay Closure",
            "A5 status: `closed`",
            "real_evidence_present_review_required",
            "closure decision: `closed`",
        ),
    ),
    "wave8_a7_validation_pack_run": Anchor(
        WAVE8_A7_RUN_DIR / "README.md",
        ("Wave8-1 A7 Validation Pack", "A5 remains `blocked_external`", "`external_blocked`"),
    ),
    "wave13_public_replay_run": Anchor(
        WAVE13_PUBLIC_REPLAY_RUN_DIR / "README.md",
        ("Crawler Public Replay Gate", "not_closed_missing_real_evidence", "public network attempted by checker"),
    ),
    "wave13_public_replay_manifest": Anchor(
        WAVE13_PUBLIC_REPLAY_RUN_DIR / "manifest.json",
        ("crawler_source_expansion.public_replay_gate_manifest.v1", "live_public_output"),
    ),
    "wave13_public_replay_check_output": Anchor(
        WAVE13_PUBLIC_REPLAY_RUN_DIR / "crawler_public_replay_gate_check.json",
        ("crawler_source_expansion.public_replay_gate.v1", "not_closed_missing_real_evidence"),
    ),
    "wave8_a7_closure_check_output": Anchor(
        WAVE8_A7_RUN_DIR / "crawler_source_expansion_closure_check.json",
        ("crawler_source_expansion.closure_check.v1",),
    ),
    "wave8_a7_a5_gate_output": Anchor(
        WAVE8_A7_RUN_DIR / "a5_public_replay_gate_check.json",
        (
            "source_library.public_replay_a5_gate.v1",
            "deterministic_replay_gate_closed_external_public_replay_blocked",
            "external_public_network_or_site_stability",
        ),
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
    "source_candidate_trust": Anchor(
        Path("main/backend/app/services/source_library/source_candidate_trust.py"),
        (
            "SOURCE_POLICY_ACTIONS",
            "source_policy_action",
            "source_policy_reason",
            "duplicate_candidate_url",
        ),
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
    "source_policy_matrix_check_script": Anchor(
        Path("main/backend/scripts/check_crawler_policy_matrix.py"),
        ("POLICY_ACTIONS", "source_policy_action", "policy_matrix_doc"),
    ),
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
    "crawler_public_replay_gate_script": Anchor(
        Path("main/backend/scripts/check_crawler_public_replay_gate.py"),
        ("CONTRACT_VERSION", "def build_check", "not_closed_missing_real_evidence"),
    ),
    "source_replay_scaleout_evidence": Anchor(
        Path("development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/README.md"),
        ("45-site", "output.public.json", "Closed for crawler source expansion"),
    ),
    "source_replay_scaleout_public_output": Anchor(
        Path("development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/output.public.json"),
        (
            "allow_public_network",
            "public_targets_attempted",
            "skipped_policy_disabled_platform_entry",
            "candidate_ready_with_term_fallback",
        ),
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
    "crawler_provider_handoff_evidence": Anchor(
        Path("development/latest-dev-docs/automation-runs/crawler-provider-handoff/2026-05-22/README.md"),
        ("Provider Handoff Contract", "High-JS/browser handoff", "source_library.provider_handoff.v1"),
    ),
    "crawler_provider_handoff_script": Anchor(
        Path("main/backend/scripts/check_crawler_provider_handoff_contract.py"),
        ("CONTRACT_VERSION", "PROVIDER_HANDOFF_CONTRACT_VERSION", "def build_check"),
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
        ("authority_output", "frontdoor_ingress", "preserves_provider_handoff_contract"),
    ),
    "test_provider_handoff": Anchor(
        Path("main/backend/tests/unit/test_source_library_resolver_unittest.py"),
        ("high_js_browser_route_hands_off_to_crawler_provider_with_trace", "source_library.provider_handoff.v1"),
    ),
    "test_crawler_bridge": Anchor(
        Path("main/backend/tests/unit/test_crawler_management_bridge_unittest.py"),
        ("submit_crawler_job", "poll_crawler_job"),
    ),
    "test_clue_chain_source_expansion": Anchor(
        Path("main/backend/tests/unit/test_clue_chain_source_library_expansion_unittest.py"),
        ("fixture_required", "network_fetch_performed"),
    ),
    "test_policy_matrix_check": Anchor(
        Path("main/backend/tests/unit/test_crawler_policy_matrix_check_unittest.py"),
        ("test_policy_matrix_binds_all_actions_to_existing_anchors", "test_policy_matrix_keeps_shared_navigation_out_of_scope"),
    ),
    "test_source_candidate_trust": Anchor(
        Path("main/backend/tests/unit/test_source_candidate_trust_unittest.py"),
        ("source_policy_action", "test_plan_marks_medium_trust_candidates_as_downgraded_review_path"),
    ),
    "test_source_library_public_replay_a5_gate": Anchor(
        Path("main/backend/tests/unit/test_source_library_public_replay_a5_gate_unittest.py"),
        ("full_public_replay_reviewed_closed", "review_required_not_full_closure"),
    ),
    "test_crawler_public_replay_gate": Anchor(
        Path("main/backend/tests/unit/test_crawler_public_replay_gate_unittest.py"),
        (
            "test_gate_validates_deterministic_artifacts_and_detects_real_public_replay",
            "real_evidence_present_review_required",
        ),
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


def _overall_status(tasks: list[dict[str, Any]]) -> str:
    blockers = [task for task in tasks if task["status"] != "closed"]
    if not blockers:
        return "closed"
    if all(task["status"] == "blocked_external" for task in blockers):
        return "external_blocked"
    if any(task["status"] == "blocked_external" for task in blockers):
        return "partial"
    return "not_closed"


def build_check(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    anchor_results = {key: _anchor_result(root, key, anchor) for key, anchor in ANCHORS.items()}
    a5_gate = build_a5_gate_check(root)
    public_replay_gate = build_public_replay_gate_check(root)

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
        "wave7_policy_matrix_doc",
        "source_candidate_trust",
        "quality_meaningful_gate",
        "quality_llm_validator",
        "quality_discovery_store",
        "source_policy_matrix_check_script",
        "source_real_probe_evidence",
        "source_live_probe_evidence",
        "test_policy_matrix_check",
        "test_source_candidate_trust",
    ]
    a5_keys = [
        "source_replay_script",
        "source_public_live_probe_script",
        "source_public_replay_a5_gate_script",
        "crawler_public_replay_gate_script",
        "source_replay_scaleout_evidence",
        "source_replay_scaleout_public_output",
        "source_live_probe_evidence",
        "wave7_a5_public_replay_doc",
        "wave13_public_replay_doc",
        "wave47_manual_public_replay_closure_doc",
        "wave13_public_replay_run",
        "wave13_public_replay_manifest",
        "wave13_public_replay_check_output",
        "test_source_library_public_replay_a5_gate",
        "test_crawler_public_replay_gate",
    ]
    a6_keys = [
        "collect_source_library_adapter",
        "collect_runtime_contracts",
        "source_library_resolver",
        "ingest_frontdoor_evidence",
        "crawler_provider_handoff_evidence",
        "crawler_provider_handoff_script",
        "test_collect_adapter",
        "test_provider_handoff",
    ]
    a7_keys = [
        "wave6_closure_doc",
        "wave8_a7_validation_pack_doc",
        "wave8_a7_validation_pack_run",
        "wave8_a7_closure_check_output",
        "wave8_a7_a5_gate_output",
        "test_clue_chain_source_expansion",
        "clue_chain_source_expansion",
        "test_source_library_public_replay_a5_gate",
    ]
    a5_anchors_pass = _passed(anchor_results, a5_keys)
    a5_gate_closed = (
        a5_gate.get("a5_status") == "full_public_replay_reviewed_closed"
        and bool((a5_gate.get("validation") or {}).get("passed"))
        and (a5_gate.get("external_blocker") or {}).get("status") == "resolved"
    )
    public_replay_ready = (
        bool((public_replay_gate.get("validation") or {}).get("passed"))
        and public_replay_gate.get("overall_status")
        == "deterministic_artifacts_valid_live_public_replay_evidence_present_review_required"
        and (public_replay_gate.get("live_public_replay") or {}).get("status")
        == "real_evidence_present_review_required"
    )
    a5_status = "closed" if a5_anchors_pass and a5_gate_closed and public_replay_ready else (
        "blocked_external" if a5_anchors_pass else "needs_update"
    )

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
            "closed" if _passed(anchor_results, a4_keys) else "needs_update",
            a4_keys,
            anchor_results,
            "The Wave7 policy matrix binds allow/downgrade/block to source_candidate_trust, resolver metadata, probe evidence, and downstream gates.",
            "" if _passed(anchor_results, a4_keys) else "Refresh the A4 policy matrix or its executable coverage check.",
        ),
        _task(
            "A5",
            "Define directed-source onboarding strategy",
            a5_status,
            a5_keys,
            anchor_results,
            (
                "The 45-site historical manifest, no-network replay gate, public-live fixture, opt-in full public replay, "
                "A5 checker, Wave13 public replay gate, and Wave47 manual review are represented."
            ),
            "" if a5_status == "closed" else (
                "Full 45-site public replay or its manual review is still missing; term-fallback rows stay review evidence, not clean closure."
            ),
        ),
        _task(
            "A6",
            "Freeze minimum source-to-ingest handoff contract",
            "closed" if _passed(anchor_results, a6_keys) else "needs_update",
            a6_keys,
            anchor_results,
            "Source-library terminal/authority output, frontdoor ingress, provider-specific crawler dispatch, and high-JS/browser route handoff now have focused contract coverage.",
            "" if _passed(anchor_results, a6_keys) else "Provider-specific crawler or high-JS/browser handoff evidence is missing.",
        ),
        _task(
            "A7",
            "Validation pack and documentation closure",
            "closed" if _passed(anchor_results, a7_keys) else "needs_update",
            a7_keys,
            anchor_results,
            "Wave8 stores a repeatable validation pack tying the closure checker, A5 external-blocker gate, clue-chain fixture replay, and no-shared-index boundary together.",
            "" if _passed(anchor_results, a7_keys) else "Refresh the Wave8 validation pack artifacts before downgrading the overall topic state.",
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
    errors.extend(f"a5_gate: {message}" for message in (a5_gate.get("validation") or {}).get("errors", []))
    errors.extend(
        f"public_replay_gate: {message}" for message in (public_replay_gate.get("validation") or {}).get("errors", [])
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "repo_root": str(root),
        "topic_dir": str(TOPIC_DIR),
        "overall_status": _overall_status(tasks),
        "doc_drift": {
            "status": "historical_snapshot_superseded",
            "reason": "The 2026-03-07 tasklist still records the initial pending plan, but Wave47 public replay evidence and review now supersede the former A5 external blocker.",
        },
        "tasks": tasks,
        "a5_gate": {
            "status": a5_gate.get("a5_status"),
            "external_blocker": a5_gate.get("external_blocker"),
            "full_public_replay": a5_gate.get("full_public_replay"),
            "closure_review": a5_gate.get("closure_review"),
        },
        "public_replay_gate": {
            "overall_status": public_replay_gate.get("overall_status"),
            "live_public_replay": public_replay_gate.get("live_public_replay"),
        },
        "minimum_development_plan": [
            "Keep A1-A4, A6, and A7 as evidence-closed through their existing code, fixture, and checker anchors.",
            "Treat A5 as closed only while the Wave47 opt-in public replay artifact and manual review note remain present.",
            "Keep term-fallback rows as relevance-review evidence rather than promoting them to clean source corpus rows.",
            "Keep public transport, anti-bot, and empty-source outcomes classified in output.public.json instead of hiding them.",
            "Keep shared navigation synced through the archive-closed target root.",
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
