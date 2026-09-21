#!/usr/bin/env python3
"""Generate the Contract 12 deterministic backend failure inventory.

The generator is intentionally stdlib-only and side-effect free apart from the
requested output file.  Classification is provisional: it records the first
bounded cause and the input path which a later disposition must resolve.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from typing import Any


CONTRACT_SHA256 = "c11c96a68284085dfb2548cd9ce19062de22b5d4bbf5af9d2c2863a16dcf03f2"
CONTRACT_REL = "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/12_stage1-residual-disposition-return-contract.v1.md"
DEFAULT_JUNIT = Path("/private/tmp/mrw-stage12-v5-backend-final.4e2HdA/backend-unit-final.xml")
DEFAULT_LOG = Path("/private/tmp/mrw-stage12-v5-backend-final.4e2HdA/backend-unit-final.log")
DEFAULT_OUTPUT = Path(__file__).with_name("backend_failure_inventory.v1.json")
AUTHORITY_CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)
CATEGORIES = ("missing_evidence", "stale_expected_semantics", "source_defect", "test_fixture_defect")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _nodeid(classname: str, name: str) -> str:
    # pytest's JUnit classname is module-qualified in this run.  Keep the
    # exact emitted identity; parametrized names remain part of ``name``.
    return f"{classname}::{name}"


def parse_failures(junit: Path) -> list[dict[str, Any]]:
    root = ET.parse(junit).getroot()
    rows: list[dict[str, Any]] = []
    for testcase in root.iter("testcase"):
        failure = testcase.find("failure")
        if failure is None:
            continue
        text = failure.text or ""
        compact = " ".join(line.strip() for line in text.splitlines() if line.strip())
        rows.append(
            {
                "nodeid": _nodeid(testcase.attrib.get("classname", ""), testcase.attrib.get("name", "")),
                "classname": testcase.attrib.get("classname", ""),
                "name": testcase.attrib.get("name", ""),
                "failure_message": failure.attrib.get("message", ""),
                "failure_excerpt": compact[:600],
                "failure_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
    return rows


def _rule(nodeid: str) -> dict[str, Any]:
    """Return one provisional disposition for a nodeid.

    Rules are ordered from direct implementation defects to missing/default
    fixture inputs.  Every rule names one owner and one primary input path.
    """
    def row(category: str, group: str, path: str, owner: str, cause: str, refs: list[str], status: str) -> dict[str, Any]:
        return {
            "category": category,
            "cause_group": group,
            "primary_input_path": path,
            "owner": owner,
            "primary_cause": cause,
            "referenced_paths": refs,
            "evidence_status": status,
        }

    test_path = nodeid.split(".", 3)[0:]
    del test_path
    if "test_collect_runtime_process_fallback_unittest" in nodeid:
        return row("source_defect", "process-fallback-overlay", "main/backend/app/api/process.py", "main/backend/app/api/process.py", "direct-call process projection loses the db-job fallback task id", ["main/backend/app/api/process.py", "main/backend/tests/unit/test_collect_runtime_process_fallback_unittest.py"], "present_but_behavior_mismatch")
    if "test_graph_typed_writing_consumer_status_boundary" in nodeid:
        return row("stale_expected_semantics", "graph-typed-writing-current-authority", "docs/development/development-plans/ARCHIVE_CLOSED", "main/backend/scripts/check_graph_typed_writing_consumer_status_boundary.py", "test expects the later closed-authority projection while canonical closure/decision inputs are absent", ["main/backend/scripts/check_graph_typed_writing_consumer_status_boundary.py", "docs/development/development-plans/ARCHIVE_CLOSED"], "present_but_semantics_unresolved")
    if "test_ingest_canary_closure_readiness" in nodeid:
        return row("missing_evidence", "ingest-canary-authority-docs", "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED", "main/backend/scripts/check_ingest_canary_closure_readiness.py", "current Wave 51/56/57 authority documents or index rows are unavailable", ["main/backend/scripts/check_ingest_canary_closure_readiness.py", "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED"], "missing")
    if "test_build_crawler_public_replay_shard_outputs" in nodeid or "test_crawler_public_replay_shards" in nodeid:
        return row("test_fixture_defect", "crawler-public-replay-shards", "development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/shard_manifest.json", "main/backend/tests/unit/test_crawler_public_replay_shards_unittest.py", "default shard manifest/readback fixture is absent from the dirty checkout", ["development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/shard_manifest.json", "development/latest-dev-docs/automation-runs/crawler-public-replay-shards/2026-05-22/shard_readback.json"], "missing")
    if "test_crawler_public_replay_gate" in nodeid:
        return row("missing_evidence", "crawler-public-replay-gate", "development/latest-dev-docs/automation-runs/crawler-public-replay-gate/2026-05-22/manifest.json", "main/backend/scripts/check_crawler_public_replay_gate.py", "A5 gate manifest required by the checker is unavailable", ["development/latest-dev-docs/automation-runs/crawler-public-replay-gate/2026-05-22/manifest.json", "main/backend/scripts/check_crawler_public_replay_gate.py"], "missing")
    if "test_crawler_source_expansion_closure_check" in nodeid:
        return row("missing_evidence", "crawler-source-expansion-closure", "development/latest-dev-docs/automation-runs/crawler-source-expansion-wave8-a7-validation-pack/2026-05-22/crawler_source_expansion_closure_check.json", "main/backend/scripts/check_crawler_source_expansion_closure.py", "closure checker cannot close A4/A5/A7 without the recorded probe and replay evidence", ["main/backend/scripts/check_crawler_source_expansion_closure.py", "development/latest-dev-docs/automation-runs/source-library-real-probes/2026-05-22/README.md", "development/latest-dev-docs/automation-runs/source-library-live-probes/2026-05-22/README.md"], "missing")
    if "test_llm_crawler_replay_fixture" in nodeid:
        return row("test_fixture_defect", "llm-crawler-browser-fixture", "development/latest-dev-docs/automation-runs/llm-crawler-browser-replay-fixture/2026-05-22/replay.fixture.json", "main/backend/tests/unit/test_llm_crawler_replay_fixture_check_unittest.py", "default browser replay fixture was deleted or is unavailable", ["development/latest-dev-docs/automation-runs/llm-crawler-browser-replay-fixture/2026-05-22/replay.fixture.json", "main/backend/tests/unit/test_llm_crawler_replay_fixture_check_unittest.py"], "missing")
    if "test_llm_crawler_replay_manifest" in nodeid:
        return row("test_fixture_defect", "llm-crawler-public-manifest", "development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-22/manifest.json", "main/backend/tests/unit/test_llm_crawler_replay_manifest_check_unittest.py", "default opt-in manifest fixture was deleted or is unavailable", ["development/latest-dev-docs/automation-runs/llm-crawler-high-js-public-replay/2026-05-22/manifest.json", "main/backend/tests/unit/test_llm_crawler_replay_manifest_check_unittest.py"], "missing")
    if "test_open_search_runtime_boundary" in nodeid and "skip_live_probe" in nodeid:
        return row("stale_expected_semantics", "open-search-auto-route-exclusion", "development/latest-dev-docs/automation-runs/search-provider-trace-artifacts/2026-05-22/search_provider_trace_contract.json", "main/backend/scripts/check_open_search_runtime_boundary.py", "trace contract does not declare local open-search providers excluded from provider=auto", ["development/latest-dev-docs/automation-runs/search-provider-trace-artifacts/2026-05-22/search_provider_trace_contract.json", "main/backend/scripts/check_open_search_runtime_boundary.py"], "present_but_semantics_unresolved")
    if "test_open_search" in nodeid:
        return row("missing_evidence", "wave12-open-search-readiness", "development/latest-dev-docs/automation-runs/wave12-provider-readiness/2026-05-22/provider_readiness_summary.json", "main/backend/scripts/check_open_search_health_artifact.py", "Wave12 provider readiness input is unavailable to health/readback builders", ["development/latest-dev-docs/automation-runs/wave12-provider-readiness/2026-05-22/provider_readiness_summary.json", "main/backend/scripts/check_open_search_health_artifact.py"], "missing")
    if "test_source_library_public_replay_a5_gate" in nodeid:
        return row("missing_evidence", "source-library-a5-replay", "development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/input.json", "main/backend/scripts/check_source_library_public_replay_a5_gate.py", "A5 replay input and live-probe readback are unavailable", ["development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/input.json", "development/latest-dev-docs/automation-runs/source-library-live-probes/2026-05-22/README.md"], "missing")
    if "test_source_library_review_closure_batch" in nodeid:
        batch = re.search(r"batch(2|3|4)?", nodeid)
        suffix = batch.group(1) if batch and batch.group(1) else ""
        name = f"review_batch{suffix}.json" if suffix else "review_batch.json"
        path = f"development/latest-dev-docs/automation-runs/source-library-review-closure-batch{suffix}/2026-05-22/{name}"
        return row("test_fixture_defect", f"source-library-review-{suffix or '1'}", path, f"main/backend/tests/unit/test_source_library_review_closure_batch{suffix}_unittest.py" if suffix else "main/backend/tests/unit/test_source_library_review_closure_batch_unittest.py", "deterministic review-batch artifact is absent, so fixture closure cannot be read back", [path], "missing")
    if "test_source_library_search_governance_check" in nodeid:
        return row("source_defect", "source-library-governance-anchor", "main/backend/app/services/source_library/resolver.py", "main/backend/scripts/check_source_library_search_governance.py", "resolver static governance anchor is absent while the governance checker still requires it", ["main/backend/app/services/source_library/resolver.py", "main/backend/scripts/check_source_library_search_governance.py"], "present_but_behavior_mismatch")
    if "test_wave10_vectorization_quality_gate" in nodeid:
        return row("missing_evidence", "wave10-vector-quality", "development/latest-dev-docs/automation-runs/wave10-vectorization-quality-gate/2026-05-22/contract_summary.json", "ops/search-lab/scripts/wave10_vectorization_quality_gate.py", "Wave10 deterministic gate output is unavailable", ["development/latest-dev-docs/automation-runs/wave10-vectorization-quality-gate/2026-05-22/contract_summary.json", "ops/search-lab/scripts/wave10_vectorization_quality_gate.py"], "missing")
    if "test_wave12_provider_readiness_gate" in nodeid:
        return row("missing_evidence", "wave12-provider-readiness", "development/latest-dev-docs/automation-runs/wave12-provider-readiness/2026-05-22/provider_readiness_summary.json", "ops/search-lab/scripts/wave12_provider_readiness_gate.py", "Wave12 readiness artifact is unavailable", ["development/latest-dev-docs/automation-runs/wave12-provider-readiness/2026-05-22/provider_readiness_summary.json", "ops/search-lab/scripts/wave12_provider_readiness_gate.py"], "missing")
    if "test_wave14_vectorization_provider_capability" in nodeid:
        return row("missing_evidence", "wave14-provider-capability", "development/latest-dev-docs/automation-runs/wave14-vectorization-provider-capability/2026-05-22", "main/backend/scripts/check_wave14_vectorization_provider_capability.py", "Wave14 depends on unavailable Wave10/Wave12 provider inputs", ["development/latest-dev-docs/automation-runs/wave14-vectorization-provider-capability/2026-05-22", "development/latest-dev-docs/automation-runs/wave10-vectorization-quality-gate/2026-05-22/contract_summary.json", "development/latest-dev-docs/automation-runs/wave12-provider-readiness/2026-05-22/provider_readiness_summary.json"], "missing")
    if "test_wave18_vectorization_hybrid_readback" in nodeid:
        return row("missing_evidence", "wave18-hybrid-readback", "development/latest-dev-docs/automation-runs/wave18-vectorization-hybrid-readback/2026-05-22/hybrid_readback_contract.json", "ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py", "hybrid readback artifact is unavailable", ["development/latest-dev-docs/automation-runs/wave18-vectorization-hybrid-readback/2026-05-22/hybrid_readback_contract.json"], "missing")
    if "test_wave19_vectorization_provider_manifest" in nodeid:
        return row("missing_evidence", "wave19-provider-manifest", "development/latest-dev-docs/automation-runs/wave19-vectorization-provider-manifest/2026-05-22/provider_manifest_readback.json", "ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py", "provider manifest readback is unavailable", ["development/latest-dev-docs/automation-runs/wave19-vectorization-provider-manifest/2026-05-22/provider_manifest_readback.json", "development/latest-dev-docs/automation-runs/wave18-vectorization-hybrid-readback/2026-05-22/hybrid_readback_contract.json"], "missing")
    if "test_wave27_vectorization_closure_gate" in nodeid or "test_wave29_oss_node_vector_manifest_replay" in nodeid:
        return row("missing_evidence", "wave27-29-provider-manifest", "development/latest-dev-docs/automation-runs/wave19-vectorization-provider-manifest/2026-05-22/provider_manifest_readback.json", "ops/search-lab/scripts/wave27_vectorization_closure_gate.py", "closure/replay gate cannot consume the missing provider manifest", ["development/latest-dev-docs/automation-runs/wave19-vectorization-provider-manifest/2026-05-22/provider_manifest_readback.json", "development/latest-dev-docs/automation-runs/wave29-oss-node-vector-manifest-replay/2026-05-23"], "missing")
    if "test_wave55_oss_node_search_quality_gate" in nodeid:
        return row("missing_evidence", "wave55-oss-search-quality", "development/latest-dev-docs/automation-runs/wave55-oss-node-search-quality-gate/2026-05-23", "ops/search-lab/scripts/wave55_oss_node_search_quality_gate.py", "Wave55 quality inputs/readback are unavailable", ["development/latest-dev-docs/automation-runs/wave55-oss-node-search-quality-gate/2026-05-23", "development/latest-dev-docs/automation-runs/search-provider-trace-artifacts/2026-05-22/search_provider_trace_contract.json"], "missing")
    if "test_wave57_oss_node_public_corpus" in nodeid:
        return row("missing_evidence", "wave57-public-corpus", "development/latest-dev-docs/automation-runs/wave57-oss-node-public-corpus-semantic-relevance-gate/2026-05-23", "ops/search-lab/scripts/wave57_oss_node_public_corpus_semantic_relevance_gate.py", "Wave57 public-corpus semantic gate input is unavailable", ["development/latest-dev-docs/automation-runs/wave57-oss-node-public-corpus-semantic-relevance-gate/2026-05-23", "development/latest-dev-docs/automation-runs/wave55-oss-node-search-quality-gate/2026-05-23"], "missing")
    if "test_wave57_production_vector_quality_gate" in nodeid:
        return row("missing_evidence", "wave57-production-vector", "development/latest-dev-docs/automation-runs/wave57-production-vector-quality-gate/2026-05-23", "ops/search-lab/scripts/wave57_production_vector_quality_gate.py", "production-like vector quality inputs and optional vector-store readback are unavailable", ["development/latest-dev-docs/automation-runs/wave57-production-vector-quality-gate/2026-05-23", "development/latest-dev-docs/automation-runs/wave56-semantic-relevance-gate/2026-05-23"], "missing")
    if "test_wave8_search_vectorization_contract" in nodeid:
        return row("missing_evidence", "wave8-search-vectorization", "development/latest-dev-docs/automation-runs/search-provider-container-replay/2026-05-22/provider_trace_replay_summary.json", "ops/search-lab/scripts/wave8_search_vectorization_contract.py", "Wave8 recorded provider/container replay evidence is unavailable", ["development/latest-dev-docs/automation-runs/search-provider-container-replay/2026-05-22/provider_trace_replay_summary.json", "development/latest-dev-docs/automation-runs/wave10-vectorization-quality-gate/2026-05-22/contract_summary.json"], "missing")
    # Remaining crawler gate failures are default fixture/evidence reads.
    return row("missing_evidence", "unclassified-backend-failure", "unknown", "stage1-successor-evidence/residual-disposition-v1/inventory", "no classification rule matched the JUnit nodeid", [], "unclassified")


def build_inventory(junit: Path, log: Path) -> dict[str, Any]:
    failures = parse_failures(junit)
    records: list[dict[str, Any]] = []
    groups: dict[str, dict[str, Any]] = {}
    for failure in failures:
        disposition = _rule(failure["nodeid"])
        record = {**failure, **disposition, "authority_ceiling": AUTHORITY_CEILING}
        records.append(record)
        key = disposition["primary_input_path"]
        group = groups.setdefault(key, {"primary_input_path": key, "nodeids": [], "category": disposition["category"], "owner": disposition["owner"]})
        group["nodeids"].append(failure["nodeid"])
    for group in groups.values():
        group["nodeids"].sort()
    records.sort(key=lambda row: row["nodeid"])
    categories = {category: sum(row["category"] == category for row in records) for category in CATEGORIES}
    payload: dict[str, Any] = {
        "schema_version": "mrw.stage1.residual-disposition.backend-failure-inventory.v1",
        "contract_12": {"path": CONTRACT_REL, "sha256": CONTRACT_SHA256},
        "source_execution": {
            "junit_path": str(junit),
            "junit_sha256": sha256_file(junit),
            "log_path": str(log),
            "log_sha256": sha256_file(log),
        },
        "authority_ceiling": AUTHORITY_CEILING,
        "failure_count": len(records),
        "category_counts": categories,
        "groups": sorted(groups.values(), key=lambda group: group["primary_input_path"]),
        "failures": records,
    }
    payload["inventory_sha256"] = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return payload


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    without_digest = dict(payload)
    without_digest.pop("inventory_sha256", None)
    return (json.dumps(without_digest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, default=DEFAULT_JUNIT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    payload = build_inventory(args.junit, args.log)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "failure_count": payload["failure_count"], "inventory_sha256": payload["inventory_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
