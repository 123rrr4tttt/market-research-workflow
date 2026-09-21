#!/usr/bin/env python3
"""Generate the Contract 13 claim-level evidence decision table.

This generator is intentionally non-operative: it classifies the frozen 30
missing-evidence nodeids and describes bounded future evidence work.  It does
not restore tracked-deleted files, run live probes, or create a new canonical
status.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent

CONTRACT_PATH = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/"
    "13_contract12-supervisor-review-and-return.v1.md"
)
INVENTORY_PATH = Path(
    "stage1-successor-evidence/residual-disposition-v1/inventory/"
    "backend_failure_inventory.root-input.v1.json"
)
CRAWLER_PROVENANCE_PATH = Path(
    "stage1-successor-evidence/residual-disposition-v1/missing-evidence/"
    "crawler-source/crawler-source-missing-evidence-provenance.v1.json"
)
VECTOR_PROVENANCE_PATH = Path(
    "stage1-successor-evidence/residual-disposition-v1/missing-evidence/"
    "opensearch-vector/opensearch-vector-missing-evidence-provenance.v1.json"
)

EXPECTED_INPUT_HASHES = {
    CONTRACT_PATH.as_posix(): "ac1629315b3ae91aa9de59b7ae87da04a5f10c54d643e406d8785a0783071717",
    INVENTORY_PATH.as_posix(): "4f01f15464582c7b465af79397e1297510ad95e9170d199564aea72a2c0e34d1",
    CRAWLER_PROVENANCE_PATH.as_posix(): "e30a797ff38ff3e43c9dd4459cbcdb306d9e44c6f630e2427a7f00429fe94453",
    VECTOR_PROVENANCE_PATH.as_posix(): "a2d74d92f6144dd8e913b7f286af4cff0d772715c14c024bfeec3d670dc4f435",
}

DECISIONS = {
    "ACTUAL_HISTORICAL_RECEIPT_REQUIRED",
    "FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE",
    "LIVE_OBSERVATION_REQUIRED",
}

GLOBAL_AUTHORITY_CEILING = (
    "STAGE1_UNACCEPTED; NOT_LIVE; NON_AUTHORITATIVE; "
    "PRODUCTION_RELEASE_NOT_AUTHORIZED; NO_DEPLOY_NO_CANARY_NO_CUTOVER_"
    "NO_AUTHORITY_TRANSFER_NO_PUSH_NO_REMOTE_MUTATION"
)


def _proposal(
    generators: list[str],
    allowed_inputs: list[dict[str, str]],
    artifact_name: str,
    ceiling: str,
) -> dict[str, Any]:
    return {
        "existing_generators": generators,
        "allowed_inputs": allowed_inputs,
        "expected_artifacts": [
            (
                "stage1-successor-evidence/contract13-bounded-corrections-v2/"
                f"claim-decisions/proposed-artifacts/{artifact_name}"
            )
        ],
        "status_authority_ceiling": ceiling,
        "write_boundary": (
            "Create a new bounded receipt only. Do not write any deleted 2026-05-22/23 "
            "automation-run path and do not update canonical topic status."
        ),
    }


REPO_CODE_INPUT = {
    "kind": "current_repo_code",
    "value": "Current checker/runtime source at the hashes captured in this table; no historical artifact substitution.",
}
NO_NETWORK_INPUT = {
    "kind": "execution_policy",
    "value": "no network, no container start, no production write, deterministic local fixtures only",
}


POLICIES: dict[str, dict[str, Any]] = {
    "crawler-public-replay-gate": {
        "claim_key": "crawler-public-replay-gate-recorded-run",
        "claim": "The recorded crawler public replay used the exact manifest and passed the reviewed real-public-replay gate.",
        "decision": "ACTUAL_HISTORICAL_RECEIPT_REQUIRED",
        "missing_specific_evidence": (
            "The historical manifest, public replay output/transcript, checker result, and review receipt bound to the same run identity."
        ),
        "recovery_authority_boundary": (
            "A designated historical-evidence custodian must verify the tracked historical objects and issue a new read-only receipt. "
            "This task may cite history-only identity but may not restore or copy the deleted files into their old paths."
        ),
    },
    "crawler-source-expansion-closure": {
        "claim_key": "crawler-source-expansion-recorded-closure",
        "claim": "The recorded crawler source-expansion closure mapped plan tasks to code/evidence and closed only after public-replay review.",
        "decision": "ACTUAL_HISTORICAL_RECEIPT_REQUIRED",
        "missing_specific_evidence": (
            "The historical closure decision, provider-handoff check, validation-pack output, and public-replay review references for one run lineage."
        ),
        "recovery_authority_boundary": (
            "Historical-object readback and semantic acceptance require supervisor/evidence-custodian authorization. "
            "No current closure status may be inferred from the HEAD blobs and no deleted package may be restored."
        ),
    },
    "ingest-canary-authority-docs": {
        "claim_key": "ingest-canary-current-authority-projection",
        "claim": "The current Wave51/56/57 authority documents and indexes preserve the three ingest-canary topic dispositions without treating Wave27 history as current authority.",
        "decision": "FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE",
        "fresh_proposal": _proposal(
            ["main/backend/scripts/check_ingest_canary_closure_readiness.py"],
            [
                REPO_CODE_INPUT,
                {
                    "kind": "canonical_current_documents",
                    "value": "Only the exact current authority/index documents listed in canonical_anchors.",
                },
                NO_NETWORK_INPUT,
            ],
            "ingest-canary-current-authority-readback.v2.json",
            "Current repo documentation/authority projection only; not a canary, runtime, deployment, or release receipt.",
        ),
    },
    "source-library-a5-replay": {
        "claim_key": "source-library-a5-recorded-public-replay",
        "claim": "The recorded A5 source-library public replay used the frozen input and received the recorded relevance review.",
        "decision": "ACTUAL_HISTORICAL_RECEIPT_REQUIRED",
        "missing_specific_evidence": (
            "The historical input, real/public probe or replay outputs and logs, A5 gate result, and human relevance-review receipt bound to one execution."
        ),
        "recovery_authority_boundary": (
            "Only an authorized historical evidence readback can establish the past run. A new public replay would be a new live observation, "
            "not a replacement for the historical claim; synthetic fixtures cannot close it."
        ),
    },
    "wave10-vector-quality": {
        "claim_key": "wave10-fresh-deterministic-vector-quality",
        "claim": "Current repo-local keyword/vector/hybrid runtime and deterministic benchmark behavior can be recomputed and aggregated without live-provider authority.",
        "decision": "FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE",
        "fresh_proposal": _proposal(
            [
                "ops/search-lab/scripts/search_provider_trace_contract.py",
                "ops/search-lab/scripts/local_index_lancedb_runtime_smoke.py",
                "ops/search-lab/scripts/local_index_lancedb_benchmark_quality.py",
                "ops/search-lab/scripts/wave10_vectorization_quality_gate.py",
            ],
            [
                REPO_CODE_INPUT,
                NO_NETWORK_INPUT,
                {
                    "kind": "fresh_chain_outputs",
                    "value": "Fresh outputs from the first three listed generators, all emitted to a new bounded evidence directory and explicitly injected into the aggregate checker.",
                },
            ],
            "wave10-vector-quality-fresh-local.v2.json",
            "Repo-local deterministic quality only; provider-live, production-semantic-quality, promotion and release claims remain forbidden.",
        ),
    },
    "wave12-open-search-readiness": {
        "claim_key": "wave12-current-open-search-runtime-readiness",
        "claim": "Current configured OpenSearch/SearXNG/YaCy endpoints have an observed runtime state distinguishable from configuration-only or connect-error state.",
        "decision": "LIVE_OBSERVATION_REQUIRED",
        "missing_specific_evidence": (
            "A fresh service-identity/config snapshot plus actual connection/query responses, timestamps, endpoint identity, failures, and an unsealed readback receipt."
        ),
        "rerun_authority_boundary": (
            "Requires explicit authorization to probe the named local services/containers and permission to record the responses. "
            "Do not start services, use network, or infer live state from mocks under this contract."
        ),
    },
    "wave12-provider-readiness": {
        "claim_key": "wave12-current-provider-readiness",
        "claim": "Current local-index modes and explicit SearXNG/YaCy provider routes have observed readiness while unsupported claims remain visible.",
        "decision": "LIVE_OBSERVATION_REQUIRED",
        "missing_specific_evidence": (
            "Fresh local-index mode probes and real explicit-provider responses with route/family/auto-inclusion trace, timestamp, environment identity, and unsupported-claim propagation."
        ),
        "rerun_authority_boundary": (
            "The existing Wave12 generator may be used only after live-probe authorization and after fresh non-live prerequisites are supplied. "
            "A --skip-live-probes output is useful but cannot satisfy this claim."
        ),
    },
    "wave14-provider-capability": {
        "claim_key": "wave14-fresh-local-provider-capability",
        "claim": "Current repo-controlled mode capability and the retained external-provider gap can be recomputed from fresh non-live evidence.",
        "decision": "FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE",
        "fresh_proposal": _proposal(
            [
                "main/backend/scripts/check_wave14_vectorization_provider_capability.py",
                "ops/search-lab/scripts/wave10_vectorization_quality_gate.py",
                "ops/search-lab/scripts/wave12_provider_readiness_gate.py",
            ],
            [
                REPO_CODE_INPUT,
                NO_NETWORK_INPUT,
                {
                    "kind": "fresh_prerequisites",
                    "value": "Fresh Wave10 deterministic output and fresh Wave12 --skip-live-probes output, injected by explicit path rather than written at deleted paths.",
                },
            ],
            "wave14-provider-capability-fresh-local.v2.json",
            "Local capability and explicit retained-gap report only; no external-provider/live-quality or closure authority.",
        ),
    },
    "wave18-hybrid-readback": {
        "claim_key": "wave18-fresh-deterministic-hybrid-readback",
        "claim": "Current repo-local deterministic adapter preserves keyword/vector/hybrid mode identity and readback without a live-provider closure claim.",
        "decision": "FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE",
        "fresh_proposal": _proposal(
            ["ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py"],
            [
                REPO_CODE_INPUT,
                NO_NETWORK_INPUT,
                {
                    "kind": "fresh_prerequisites",
                    "value": "Fresh non-live Wave8/Wave10/Wave12/Wave14 receipts, injected from a new bounded directory.",
                },
            ],
            "wave18-hybrid-readback-fresh-local.v2.json",
            "Deterministic adapter/readback behavior only; semantic quality, provider-live closure and production authority remain false.",
        ),
    },
    "wave19-provider-manifest": {
        "claim_key": "wave19-fresh-derived-provider-manifest",
        "claim": "A current non-live provider manifest can be deterministically derived from fresh Wave14 capability and Wave18 readback receipts.",
        "decision": "FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE",
        "fresh_proposal": _proposal(
            ["ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py"],
            [
                REPO_CODE_INPUT,
                NO_NETWORK_INPUT,
                {
                    "kind": "fresh_prerequisites",
                    "value": "Fresh Wave14 and Wave18 bounded receipts with explicit injected paths; no historical manifest reuse.",
                },
            ],
            "wave19-provider-manifest-fresh-local.v2.json",
            "Derived non-live manifest only; it must retain all external/live/semantic gaps and cannot authorize topic status changes.",
        ),
    },
    "wave27-29-provider-manifest": {
        "claim_key": "wave27-wave29-fresh-manifest-and-topic-readback",
        "claim": "Current canonical topic projections and a fresh non-live Wave19 manifest can be deterministically replayed without claiming live platform SLA.",
        "decision": "FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE",
        "fresh_proposal": _proposal(
            [
                "ops/search-lab/scripts/wave27_vectorization_closure_gate.py",
                "ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py",
            ],
            [
                REPO_CODE_INPUT,
                NO_NETWORK_INPUT,
                {
                    "kind": "fresh_prerequisite",
                    "value": "Fresh Wave19 non-live manifest passed by --provider-manifest; live API/UI bases must be empty.",
                },
                {
                    "kind": "canonical_topic_projection",
                    "value": "Only the exact relocated topic INDEX/decision documents listed in canonical_anchors; they are topic/status projections, not runtime receipts.",
                },
            ],
            "wave27-wave29-manifest-replay-fresh-local.v2.json",
            "Non-live manifest/topic readback only; platform SLA remains open and no new canonical status or migration is authorized.",
        ),
    },
    "wave27-29-provider-manifest-live": {
        "claim_key": "wave29-current-platform-api-ui-sla",
        "claim": "The current scheduler/tenant/API/UI platform condition has been observed live for the Wave29 OSS-node route.",
        "decision": "LIVE_OBSERVATION_REQUIRED",
        "missing_specific_evidence": (
            "A fresh Wave29 probe receipt with actual API and UI base identities, request/response timestamps, scheduler/tenant readback, failure details, and environment identity."
        ),
        "rerun_authority_boundary": (
            "Requires explicit permission to access the local API/UI runtime and record live responses. This contract neither starts those services nor authorizes a live probe."
        ),
    },
    "wave55-oss-search-quality": {
        "claim_key": "wave55-fresh-controlled-search-quality",
        "claim": "Current controlled repo-local open-search ranking and local embedding quality can be recomputed without network or live-container claims.",
        "decision": "FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE",
        "fresh_proposal": _proposal(
            [
                "ops/search-lab/scripts/search_provider_trace_contract.py",
                "ops/search-lab/scripts/wave55_live_embedding_provider_gate.py",
                "ops/search-lab/scripts/wave55_oss_node_search_quality_gate.py",
            ],
            [
                REPO_CODE_INPUT,
                NO_NETWORK_INPUT,
                {
                    "kind": "fresh_prerequisites",
                    "value": "Fresh deterministic explicit-route trace and Wave55 local embedding receipt, injected from a new bounded directory.",
                },
            ],
            "wave55-oss-search-quality-fresh-local.v2.json",
            "Controlled repo-local ranking only; live-container and production semantic quality remain unproven.",
        ),
    },
    "wave57-public-corpus": {
        "claim_key": "wave57-fresh-public-oss-corpus-relevance",
        "claim": "Current checked-in public OSS corpus excerpts can be deterministically ranked by the repo-local embedding route for the bounded OSS-node topic.",
        "decision": "FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE",
        "fresh_proposal": _proposal(
            [
                "ops/search-lab/scripts/wave55_live_embedding_provider_gate.py",
                "ops/search-lab/scripts/wave55_oss_node_search_quality_gate.py",
                "ops/search-lab/scripts/wave57_oss_node_public_corpus_semantic_relevance_gate.py",
            ],
            [
                REPO_CODE_INPUT,
                NO_NETWORK_INPUT,
                {"kind": "checked_in_corpus", "value": "reference-pool/oss/INDEX.md and the exact checked-in excerpts selected by the Wave57 generator"},
                {"kind": "fresh_prerequisite", "value": "Fresh bounded Wave55 deterministic quality receipt, not the deleted historical artifact."},
            ],
            "wave57-public-corpus-relevance-fresh-local.v2.json",
            "Bounded checked-in-corpus relevance only; no generic public-web, live provider, production traffic, or release authority.",
        ),
    },
    "wave57-production-vector": {
        "claim_key": "wave57-recorded-production-like-corpus-lineage",
        "claim": "The recorded Wave57 production-like vector replay used the historical corpus lineage and prerequisite Wave56/provider artifacts claimed by that run.",
        "decision": "ACTUAL_HISTORICAL_RECEIPT_REQUIRED",
        "missing_specific_evidence": (
            "The historical Wave56 gate, both recorded LanceDB JSONL corpora, four narrative inputs, and the Wave57 vector-store execution receipt bound to one corpus manifest."
        ),
        "recovery_authority_boundary": (
            "Historical corpus objects must be verified by an authorized evidence custodian. Rebuilding a different current corpus would be a successor experiment, "
            "not proof of the recorded claim; no deleted source may be restored by this task."
        ),
    },
    "wave8-search-vectorization": {
        "claim_key": "wave8-recorded-evidence-reuse",
        "claim": "The Wave8 aggregate reused the recorded provider trace, container replay, LanceDB runtime and benchmark evidence without claiming live services.",
        "decision": "ACTUAL_HISTORICAL_RECEIPT_REQUIRED",
        "missing_specific_evidence": (
            "The four historical source receipts and their aggregate Wave8 contract with matching run/object identities."
        ),
        "recovery_authority_boundary": (
            "Because the claim is explicitly about recorded reuse, fresh outputs cannot prove it. Authorized read-only historical verification is required; no old path restoration is allowed."
        ),
    },
}


CANONICAL_ANCHORS_BY_POLICY = {
    "ingest-canary-authority-docs": [
        ("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/INDEX.md", "7c9e761b9bcb6e314b7f2907a75adc5c2caf404fe4fa1ae2252e8474d1e525f6"),
        ("development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md", "0563941ec3ccd96a9d3cb133727f97d2de47d75ace7cf68bf86d9d4bd3dc31bc"),
        ("development/latest-dev-docs/development-plans/TARGET_TOPIC_ALLOWLIST.json", "ce35b86f548c64dd1d2dc8d84aad898b58245dcba737ce9dfb700b340681599b"),
        ("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-ingest-platformization-assessment/10_wave51-non-target-assessment-wrapper-reclassification-2026-05-23.md", "44f724b61793bb3b9fa4b4288887fc9860bbbbd1390bf753c6211b6a37ce7582"),
        ("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-meaningful-ingest-guardrails-plan/13_wave56-strict-promotion-final-gate-2026-05-24.md", "305b03d206308722bf316224c0a43b56883e3b6e0ae50cf4aca75191a4d277e6"),
        ("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-single-url-first-ingest-allocation-plan/13_wave57-single-url-external-blocker-closure-2026-05-24.md", "32f1f4e43b760852b578f2c498b386ed335c77efcd1d3b1201e999a758c42a44"),
    ],
    "wave27-29-provider-manifest": [
        ("docs/development/development-plans/ARCHIVE_CLOSED/2026-03-05-oss-node-platform-io-plan/INDEX.md", "b1377fd42a6b049428b941a60de7f3472ac4d451e3e8ad9e394d1c9ccb19b00d"),
        ("docs/development/development-plans/ARCHIVE_CLOSED/2026-03-05-oss-node-platform-io-plan/07_wave27-vectorization-closure-decision-2026-05-23.md", "3c5818809d0f512dd3b961f6b3477714c89ee6b5752df9a97f457b6bd953ccc8"),
        ("docs/development/development-plans/ARCHIVE_CLOSED/2026-03-05-oss-node-platform-io-plan/08_wave29-oss-node-vector-manifest-replay-2026-05-23.md", "9ff6233de1ff5313bbed3e86031e55a8c9e7544661c2e2029c365d037aa96e25"),
        ("docs/development/development-plans/ARCHIVE_CLOSED/2026-05-14-global-vectorization-general-foundation/INDEX.md", "09255aa414a279bf06ebadf46a36374e778e132f38c65803abdc21c6a4706c10"),
        ("docs/development/development-plans/ARCHIVE_CLOSED/2026-05-14-global-vectorization-general-foundation/09_wave27-vectorization-closure-decision-2026-05-23.md", "0a0117c5329dd7360a21eae4dab1beccfe86deb0e0f6f5e152c0cedfb7e2a613"),
    ],
    "wave55-oss-search-quality": [
        ("docs/development/development-plans/ARCHIVE_CLOSED/2026-03-05-oss-node-platform-io-plan/INDEX.md", "b1377fd42a6b049428b941a60de7f3472ac4d451e3e8ad9e394d1c9ccb19b00d"),
        ("docs/development/development-plans/ARCHIVE_CLOSED/2026-03-05-oss-node-platform-io-plan/10_wave55-oss-node-search-quality-gate-2026-05-23.md", "2bb3c453d321486040fe04c56dc60029de1f602810b2b7aa461516e1449ce20b"),
    ],
    "wave57-public-corpus": [
        ("docs/development/development-plans/ARCHIVE_CLOSED/2026-03-05-oss-node-platform-io-plan/INDEX.md", "b1377fd42a6b049428b941a60de7f3472ac4d451e3e8ad9e394d1c9ccb19b00d"),
        ("docs/development/development-plans/ARCHIVE_CLOSED/2026-03-05-oss-node-platform-io-plan/11_wave57-oss-node-public-corpus-semantic-relevance-2026-05-23.md", "9f7cea64c2392e92d3421347cde24cdf0454889ee99ebc093f787036e63fdebf"),
    ],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_name(nodeid: str) -> str:
    return nodeid.rsplit("::", 1)[-1]


def policy_key_for_failure(row: dict[str, Any]) -> str:
    if row["cause_group"] == "wave27-29-provider-manifest" and row["name"] == "test_live_platform_probe_can_close_scheduler_tenant_ui_condition":
        return "wave27-29-provider-manifest-live"
    return str(row["cause_group"])


def source_requirement(
    *, provenance_path: Path, provenance_sha256: str, entry: dict[str, Any]
) -> dict[str, Any]:
    historical = entry.get("available_historical_provenance") or entry.get("historical_provenance") or {}
    old_path = entry.get("old_path") or entry.get("path")
    return {
        "provenance_file": provenance_path.as_posix(),
        "provenance_file_sha256": provenance_sha256,
        "provenance_entry_id": entry.get("entry_id"),
        "missing_path": old_path,
        "required_factual_claim": entry.get("required_factual_claim"),
        "classification_at_source": entry.get("classification"),
        "historical_object": {
            key: historical[key]
            for key in (
                "source",
                "head_commit",
                "git_blob_oid",
                "git_object_sha1",
                "sha256",
                "bytes",
                "history_only",
                "usable_as_current_or_live_evidence",
                "content_read",
            )
            if key in historical
        },
    }


def relevant_requirements(
    nodeids: list[str], crawler: dict[str, Any], vector: dict[str, Any]
) -> list[dict[str, Any]]:
    names = {test_name(nodeid) for nodeid in nodeids}
    rows: list[dict[str, Any]] = []
    for entry in crawler["inventory"]["entries"]:
        dependent_names = {test_name(nodeid) for nodeid in entry.get("dependent_nodeids", [])}
        if names & dependent_names:
            rows.append(
                source_requirement(
                    provenance_path=CRAWLER_PROVENANCE_PATH,
                    provenance_sha256=EXPECTED_INPUT_HASHES[CRAWLER_PROVENANCE_PATH.as_posix()],
                    entry=entry,
                )
            )
    vector_nodeids = vector.get("nodeids", {})
    for entry in vector.get("missing_sources", []):
        dependent_names = {
            test_name(vector_nodeids[ref])
            for ref in entry.get("dependent_nodeid_refs", [])
            if ref in vector_nodeids
        }
        if names & dependent_names:
            rows.append(
                source_requirement(
                    provenance_path=VECTOR_PROVENANCE_PATH,
                    provenance_sha256=EXPECTED_INPUT_HASHES[VECTOR_PROVENANCE_PATH.as_posix()],
                    entry=entry,
                )
            )
    unique = {(row["provenance_file"], row.get("provenance_entry_id"), row["missing_path"]): row for row in rows}
    return [unique[key] for key in sorted(unique)]


def generator_refs(policy: dict[str, Any]) -> list[dict[str, str]]:
    proposal = policy.get("fresh_proposal") or {}
    refs = []
    for path_text in proposal.get("existing_generators", []):
        path = REPO_ROOT / path_text
        refs.append({"path": path_text, "sha256": sha256(path)})
    return refs


def canonical_anchors(policy_key: str) -> list[dict[str, str]]:
    return [
        {
            "path": path,
            "sha256": digest,
            "role": "existing canonical projection consumed read-only; not runtime evidence and not a new status",
        }
        for path, digest in CANONICAL_ANCHORS_BY_POLICY.get(policy_key, [])
    ]


def build_table() -> dict[str, Any]:
    for path_text, expected in EXPECTED_INPUT_HASHES.items():
        actual = sha256(REPO_ROOT / path_text)
        if actual != expected:
            raise RuntimeError(f"input hash mismatch: {path_text}: {actual} != {expected}")

    inventory = read_json(REPO_ROOT / INVENTORY_PATH)
    crawler = read_json(REPO_ROOT / CRAWLER_PROVENANCE_PATH)
    vector = read_json(REPO_ROOT / VECTOR_PROVENANCE_PATH)
    missing = [row for row in inventory["failures"] if row["category"] == "missing_evidence"]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in missing:
        groups[policy_key_for_failure(row)].append(row)

    claims = []
    for index, key in enumerate(sorted(groups), start=1):
        policy = POLICIES[key]
        nodeids = sorted(row["nodeid"] for row in groups[key])
        claim = {
            "claim_id": f"claim-{index:03d}",
            "claim_key": policy["claim_key"],
            "factual_claim": policy["claim"],
            "decision": policy["decision"],
            "dependent_nodeids": nodeids,
            "dependent_nodeid_count": len(nodeids),
            "source_cause_groups": sorted({row["cause_group"] for row in groups[key]}),
            "source_requirements": relevant_requirements(nodeids, crawler, vector),
            "canonical_anchors": canonical_anchors(key),
            "authority_ceiling": GLOBAL_AUTHORITY_CEILING,
        }
        if policy["decision"] == "FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE":
            claim["fresh_proposal"] = {
                **policy["fresh_proposal"],
                "existing_generator_refs": generator_refs(policy),
                "dependent_nodeids": nodeids,
            }
        elif policy["decision"] == "ACTUAL_HISTORICAL_RECEIPT_REQUIRED":
            claim["missing_specific_evidence"] = policy["missing_specific_evidence"]
            claim["recovery_authority_boundary"] = policy["recovery_authority_boundary"]
        else:
            claim["missing_specific_evidence"] = policy["missing_specific_evidence"]
            claim["rerun_authority_boundary"] = policy["rerun_authority_boundary"]
        claim_fingerprint_source = json.dumps(
            {"claim_key": claim["claim_key"], "decision": claim["decision"], "nodeids": nodeids},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        claim["claim_fingerprint_sha256"] = hashlib.sha256(claim_fingerprint_source).hexdigest()
        claims.append(claim)

    decision_counts = Counter(claim["decision"] for claim in claims)
    nodeid_decision_counts = Counter()
    for claim in claims:
        nodeid_decision_counts[claim["decision"]] += claim["dependent_nodeid_count"]
    return {
        "schema_version": "mrw.contract13.claim_decisions.v2",
        "record_id": "contract13-bounded-claim-decisions-2026-09-06",
        "status": "DECISION_TABLE_COMPLETE_ACCEPTANCE_NOT_CLAIMED",
        "authoritative": False,
        "execution_status": "NOT_LIVE",
        "closure_claim_allowed": False,
        "production_release_authorized": False,
        "contract_13": {"path": CONTRACT_PATH.as_posix(), "sha256": EXPECTED_INPUT_HASHES[CONTRACT_PATH.as_posix()]},
        "inputs": [
            {"path": path_text, "sha256": digest}
            for path_text, digest in sorted(EXPECTED_INPUT_HASHES.items())
        ],
        "classification_contract": {
            "allowed_decisions": sorted(DECISIONS),
            "mutually_exclusive": True,
            "synthetic_fixture_may_test_validator_behavior": True,
            "synthetic_fixture_may_close_factual_claim": False,
            "historical_blob_may_be_restored_or_substituted": False,
            "canonical_projection_may_create_new_status": False,
        },
        "summary": {
            "inventory_missing_evidence_nodeid_count": len(missing),
            "unique_claim_count": len(claims),
            "decision_claim_counts": dict(sorted(decision_counts.items())),
            "decision_nodeid_counts": dict(sorted(nodeid_decision_counts.items())),
            "nodeids_covered_exactly_once": True,
        },
        "claims": claims,
        "authority_ceiling": GLOBAL_AUTHORITY_CEILING,
    }


def render_markdown(table: dict[str, Any]) -> str:
    lines = [
        "# Contract 13 factual-evidence claim decisions v2",
        "",
        "Decision: `DECISION_TABLE_COMPLETE_ACCEPTANCE_NOT_CLAIMED`.",
        "",
        "This is a deduplicated routing table for the frozen 30 `missing_evidence` nodeids. "
        "It does not restore deleted evidence, perform live probes, create canonical status, or accept Stage 1.",
        "",
        "## Summary",
        "",
        f"- Unique claims: {table['summary']['unique_claim_count']}",
        f"- Nodeids covered exactly once: {table['summary']['inventory_missing_evidence_nodeid_count']}",
    ]
    for decision, count in table["summary"]["decision_nodeid_counts"].items():
        lines.append(f"- `{decision}`: {count} nodeids")
    lines.extend([
        "",
        "| Claim | Decision | Nodeids | Factual boundary |",
        "| --- | --- | ---: | --- |",
    ])
    for claim in table["claims"]:
        boundary = claim["factual_claim"].replace("|", "\\|")
        lines.append(
            f"| `{claim['claim_id']}` / `{claim['claim_key']}` | `{claim['decision']}` | "
            f"{claim['dependent_nodeid_count']} | {boundary} |"
        )
    lines.extend(["", "## Decision details", ""])
    for claim in table["claims"]:
        lines.extend([
            f"### {claim['claim_id']}: {claim['claim_key']}",
            "",
            claim["factual_claim"],
            "",
            f"Decision: `{claim['decision']}`.",
            "",
        ])
        if "fresh_proposal" in claim:
            proposal = claim["fresh_proposal"]
            lines.append("Existing generator chain:")
            lines.append("")
            lines.extend(f"- `{row['path']}` (`sha256:{row['sha256']}`)" for row in proposal["existing_generator_refs"])
            lines.extend(["", "Expected artifact:", ""])
            lines.extend(f"- `{path}`" for path in proposal["expected_artifacts"])
            lines.extend(["", f"Ceiling: {proposal['status_authority_ceiling']}", ""])
        else:
            lines.extend([
                f"Missing evidence: {claim['missing_specific_evidence']}",
                "",
                f"Authority boundary: {claim.get('recovery_authority_boundary') or claim.get('rerun_authority_boundary')}",
                "",
            ])
        lines.append("Dependent nodeids:")
        lines.append("")
        lines.extend(f"- `{nodeid}`" for nodeid in claim["dependent_nodeids"])
        if claim["canonical_anchors"]:
            lines.extend(["", "Read-only canonical anchors:", ""])
            lines.extend(f"- `{row['path']}` (`sha256:{row['sha256']}`)" for row in claim["canonical_anchors"])
        lines.append("")
    lines.extend([
        "## Hard ceilings",
        "",
        "Synthetic fixtures may test checker behavior but cannot close historical or live facts. "
        "History-only Git objects remain identity/provenance, not current authority. "
        "A fresh deterministic receipt is bounded to current repo-local behavior and cannot establish live provider, production, canary, cutover, or release authority.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    table = build_table()
    (OUT_DIR / "claim-decisions.v2.json").write_text(
        json.dumps(table, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "claim-decisions.v2.md").write_text(render_markdown(table), encoding="utf-8")
    print(json.dumps(table["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
