#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if sys.version_info < (3, 10):
    candidates = (
        os.environ.get("PYTHON311"),
        shutil.which("python3.11"),
        "/Users/wangyiliang/.local/bin/python3.11",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and Path(candidate) != Path(sys.executable):
            os.execv(candidate, [candidate, *sys.argv])

sys.path.insert(0, str(BACKEND_ROOT))

from app.contracts.schemas.writing import (  # noqa: E402
    TypedKnowledgeWritingContext,
    TypedKnowledgeWritingHandoffData,
    WritingContextEnvelope,
)
from app.services.document_views.writing_card_view import (  # noqa: E402
    build_keyword_card_from_typed_knowledge_handoff,
)
from app.services.typed_knowledge import contracts  # noqa: E402
from app.services.typed_knowledge import persistence_boundary  # noqa: E402


CONTRACT_VERSION = "typed_writing.live_boundary_inventory.v1"
READINESS_STATE = "partial"
CLOSURE_POSITION = "typed_knowledge_public_route_contract_available_live_db_ui_not_closed"

EVIDENCE_DOCS = (
    Path(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-03-07-typed-knowledge-organization/"
        "04_wave10-worker7-writing-context-envelope-evidence-2026-05-22.md"
    ),
    Path(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-03-07-typed-knowledge-organization/"
        "05_wave12-worker7-persistence-api-boundary-evidence-2026-05-22.md"
    ),
    Path(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-03-07-writing-workbench-evolution/"
        "05_wave10-worker7-typed-knowledge-context-consumer-evidence-2026-05-22.md"
    ),
    Path(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-03-07-writing-workbench-evolution/"
        "06_wave12-worker7-typed-knowledge-persistence-boundary-evidence-2026-05-22.md"
    ),
    Path(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-03-07-typed-knowledge-organization/"
        "06_wave15-typed-writing-live-boundary-2026-05-22.md"
    ),
    Path(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-03-07-writing-workbench-evolution/"
        "07_wave15-typed-writing-live-boundary-2026-05-22.md"
    ),
)
WAVE10_DOC_MARKERS = (
    "Scope:",
    "Landed Slice",
    "Still partial",
)
LIVE_BOUNDARY_DOC_MARKERS = (
    "live_db_persistence: false",
    "public_api_route: false",
    "governance_ui: false",
    "remaining_live_gaps",
)
WAVE15_DOC_MARKERS = (
    "wave15_live_boundary_inventory: passed",
    "deterministic_persistence_api_boundary: covered",
    "closure_claim_allowed: false",
)

SOURCE_FILES = {
    "typed_contracts": Path("main/backend/app/services/typed_knowledge/contracts.py"),
    "typed_persistence_boundary": Path("main/backend/app/services/typed_knowledge/persistence_boundary.py"),
    "typed_api": Path("main/backend/app/api/typed_knowledge.py"),
    "api_init": Path("main/backend/app/api/__init__.py"),
    "writing_schema": Path("main/backend/app/contracts/schemas/writing.py"),
    "writing_api": Path("main/backend/app/api/writing.py"),
    "writing_keyword_service": Path("main/backend/app/services/writing/keyword_card_service.py"),
    "writing_card_view": Path("main/backend/app/services/document_views/writing_card_view.py"),
    "frontend_writing_domain": Path("main/frontend-modern/src/lib/api/domains/writing.ts"),
    "frontend_writing_workbench": Path("main/frontend-modern/src/pages/WritingWorkbenchPage.tsx"),
}

REQUIRED_DETERMINISTIC_COVERAGE = (
    "typed_knowledge_object_identity",
    "typed_knowledge_status_data_error_meta_envelope",
    "in_memory_repository_readback",
    "writing_handoff_reference_preservation",
    "typed_knowledge_public_api_route_contract",
    "writing_context_envelope_schema_parity",
    "writing_keyword_card_resource_consumer",
    "writing_api_contract_surface",
    "frontend_api_type_parity",
    "frontend_workbench_consumer_surface",
)
REQUIRED_OPEN_GAPS = (
    "live_db_persistence_not_implemented",
    "live_db_backed_typed_knowledge_api_readback_not_verified",
    "governance_ui_not_implemented",
    "migration_and_backfill_not_executed",
    "writing_live_typed_knowledge_fetch_not_available",
    "writing_ui_governance_mutation_not_available",
    "persisted_typed_knowledge_cards_live_readback_not_verified",
)


def _read_text(root: Path, rel_path: Path) -> str:
    path = root / rel_path
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _source_inventory(root: Path) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "path": rel_path.as_posix(),
            "exists": (root / rel_path).is_file(),
            "text": _read_text(root, rel_path),
        }
        for name, rel_path in SOURCE_FILES.items()
    }


def _has_all(text: str, markers: tuple[str, ...]) -> bool:
    return all(marker in text for marker in markers)


def _coverage_row(code: str, passed: bool, evidence: list[str], detail: str) -> dict[str, Any]:
    return {
        "code": code,
        "passed": bool(passed),
        "evidence": evidence,
        "detail": detail,
    }


def _build_handoff() -> contracts.WritingKnowledgeHandoff:
    item = contracts.KnowledgeItem(
        key="ki:robotics-policy",
        project_key="demo_proj",
        canonical_statement="Humanoid robotics investment is shifting toward industrial pilots.",
        primary_type_node_key="type:market_signal",
        evidence_refs=("doc:robotics:42",),
        topic_cluster_keys=("topic:robotics",),
        booklet_keys=("booklet:q2-review",),
        review_state=contracts.REVIEW_STATE_HUMAN_CONFIRMED,
        quality_grade=contracts.QUALITY_GRADE_GOLD,
        locale="en",
    )
    return contracts.build_writing_knowledge_handoff(
        contracts.build_downstream_contract_draft(item),
        selection_hash="selection:robotics",
        selection_text="robotics investment",
    )


def _deterministic_coverage(root: Path, sources: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    envelope = persistence_boundary.build_sample_boundary_envelope()
    persistence_boundary.validate_persistence_api_envelope(envelope)
    route_envelope = persistence_boundary.build_public_api_route_contract_envelope()
    persistence_boundary.validate_public_api_route_contract_envelope(route_envelope)

    records = envelope["data"]["records"]
    writes = envelope["data"]["writes"]
    record_types = {record["object_type"] for record in records}
    item_record = next(record for record in records if record["object_type"] == "knowledge_item")
    writing_refs = envelope["data"]["writing_handoff_refs"]
    readiness = envelope["meta"]["readiness"]
    route_meta = route_envelope["meta"]

    handoff = _build_handoff()
    typed_context = contracts.build_writing_knowledge_context_envelope((handoff,))
    writing_context = WritingContextEnvelope(typed_knowledge_context=typed_context)
    parsed_handoffs = contracts.parse_writing_knowledge_context_envelope(
        writing_context.model_dump()["typed_knowledge_context"]
    )
    card = build_keyword_card_from_typed_knowledge_handoff(parsed_handoffs[0], normalized_query="robotics investment")

    writing_api = str(sources["writing_api"]["text"])
    typed_api = str(sources["typed_api"]["text"])
    api_init = str(sources["api_init"]["text"])
    writing_schema = str(sources["writing_schema"]["text"])
    keyword_service = str(sources["writing_keyword_service"]["text"])
    frontend_domain = str(sources["frontend_writing_domain"]["text"])
    frontend_workbench = str(sources["frontend_writing_workbench"]["text"])

    return [
        _coverage_row(
            "typed_knowledge_object_identity",
            record_types == {"type_node", "knowledge_item", "topic_cluster", "booklet"}
            and item_record["identity_ref"] == "demo_proj:knowledge_item:ki:robotics-policy",
            ["main/backend/app/services/typed_knowledge/persistence_boundary.py"],
            "four typed-knowledge object roles retain project-scoped identity refs",
        ),
        _coverage_row(
            "typed_knowledge_status_data_error_meta_envelope",
            envelope["status"] == "ok"
            and set(("status", "data", "error", "meta")).issubset(envelope)
            and envelope["meta"]["contract_readiness"] == "ready",
            ["main/backend/app/services/typed_knowledge/persistence_boundary.py"],
            "persistence/API boundary uses the project API envelope shape",
        ),
        _coverage_row(
            "in_memory_repository_readback",
            envelope["data"]["repository"]["persistence_mode"] == "in_memory_contract"
            and readiness["repository_contract"] is True
            and all(write["live_db_write"] is False for write in writes),
            ["main/backend/app/services/typed_knowledge/persistence_boundary.py"],
            "repository readback is deterministic and does not claim a live DB write",
        ),
        _coverage_row(
            "writing_handoff_reference_preservation",
            len(writing_refs) == 1
            and writing_refs[0]["consumer"] == "writing.keyword_card"
            and writing_refs[0]["card_source_type"] == "resource",
            ["main/backend/app/services/typed_knowledge/persistence_boundary.py"],
            "knowledge-item persistence records preserve the writing keyword-card handoff reference",
        ),
        _coverage_row(
            "typed_knowledge_public_api_route_contract",
            route_envelope["data"]["route"]["path"] == persistence_boundary.PUBLIC_API_ROUTE_PATH
            and route_meta["readiness"]["public_api_route"] is True
            and route_meta["readiness"]["live_db_persistence"] is False
            and "public_typed_knowledge_api_route_not_implemented" not in route_meta["remaining_live_gaps"]
            and "get_typed_knowledge_persistence_boundary" in typed_api
            and "typed_knowledge_router" in api_init,
            [
                "main/backend/app/api/typed_knowledge.py",
                "main/backend/app/api/__init__.py",
                "main/backend/app/services/typed_knowledge/persistence_boundary.py",
            ],
            "typed-knowledge now exposes a public contract route without claiming live DB persistence",
        ),
        _coverage_row(
            "writing_context_envelope_schema_parity",
            TypedKnowledgeWritingHandoffData.model_fields["contract_version"].default
            == contracts.WRITING_KNOWLEDGE_HANDOFF_CONTRACT_VERSION
            and TypedKnowledgeWritingContext.model_fields["contract_version"].default
            == contracts.WRITING_KNOWLEDGE_CONTEXT_ENVELOPE_VERSION
            and "class WritingContextEnvelope" in writing_schema
            and "typed_knowledge_context" in writing_schema,
            ["main/backend/app/contracts/schemas/writing.py"],
            "backend writing schema exposes typed-knowledge handoff/context fields",
        ),
        _coverage_row(
            "writing_keyword_card_resource_consumer",
            len(parsed_handoffs) == 1
            and card.source_type == "resource"
            and card.publisher == "typed_knowledge"
            and "parse_writing_knowledge_context_envelope" in keyword_service
            and "typed_knowledge_boundary_rule" in keyword_service,
            [
                "main/backend/app/services/writing/keyword_card_service.py",
                "main/backend/app/services/document_views/writing_card_view.py",
            ],
            "writing consumes typed knowledge as resource cards only",
        ),
        _coverage_row(
            "writing_api_contract_surface",
            _has_all(
                writing_api,
                (
                    '"/documents"',
                    '"/keyword-cards"',
                    '"/llm-actions"',
                    '"/export/markdown"',
                    "response_model=ApiEnvelope[KeywordCardListResponse]",
                ),
            ),
            ["main/backend/app/api/writing.py"],
            "writing workbench API routes remain typed through the existing writing envelope",
        ),
        _coverage_row(
            "frontend_api_type_parity",
            _has_all(
                frontend_domain,
                (
                    "export type TypedKnowledgeWritingHandoff",
                    "export type TypedKnowledgeWritingContext",
                    "typed_knowledge_context?: TypedKnowledgeWritingContext | null",
                    "context_boundary: Record<string, unknown>",
                    "dependency_gate: Record<string, unknown>",
                ),
            ),
            ["main/frontend-modern/src/lib/api/domains/writing.ts"],
            "frontend API domain sees the backend typed-knowledge context and boundary fields",
        ),
        _coverage_row(
            "frontend_workbench_consumer_surface",
            _has_all(
                frontend_workbench,
                (
                    "getWritingKeywordCards",
                    "WritingWorkbenchPage",
                    "sources: ['document', 'resource', 'graph']",
                ),
            ),
            ["main/frontend-modern/src/pages/WritingWorkbenchPage.tsx"],
            "workbench remains a writing API consumer surface, not typed-knowledge governance UI",
        ),
    ]


def _public_typed_knowledge_api_exists(root: Path) -> bool:
    api_dir = root / "main/backend/app/api"
    if not api_dir.is_dir():
        return False
    for path in api_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "typed_knowledge" in text or "typed-knowledge" in text:
            return True
    return False


def _writing_live_typed_knowledge_fetch_exists(sources: Mapping[str, Mapping[str, Any]]) -> bool:
    writing_api = str(sources["writing_api"]["text"])
    frontend_domain = str(sources["frontend_writing_domain"]["text"])
    frontend_workbench = str(sources["frontend_writing_workbench"]["text"])
    route_markers = (
        "/typed-knowledge/persistence-boundary",
        "getTypedKnowledge",
        "fetchTypedKnowledge",
        "typedKnowledgeApi",
    )
    return any(marker in writing_api or marker in frontend_domain or marker in frontend_workbench for marker in route_markers)


def _typed_knowledge_db_model_exists(root: Path) -> bool:
    model_dir = root / "main/backend/app/models"
    if not model_dir.is_dir():
        return False
    for path in model_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "__tablename__" in text and "typed_knowledge" in text:
            return True
    return False


def _live_boundaries(root: Path, sources: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    envelope = persistence_boundary.build_sample_boundary_envelope()
    route_envelope = persistence_boundary.build_public_api_route_contract_envelope()
    readiness = envelope["meta"]["readiness"]
    remaining = set(envelope["meta"]["remaining_live_gaps"])
    route_remaining = set(route_envelope["meta"]["remaining_live_gaps"])
    frontend_workbench = str(sources["frontend_writing_workbench"]["text"])

    return [
        {
            "code": "live_db_persistence_not_implemented",
            "area": "typed_knowledge.live_db",
            "closed": bool(readiness.get("live_db_persistence")) and _typed_knowledge_db_model_exists(root),
            "evidence": ["main/backend/app/services/typed_knowledge/persistence_boundary.py"],
            "gap_recorded": "live_db_persistence_not_implemented" in remaining,
            "required_to_close": "add live typed-knowledge DB model/table, migration, write/readback smoke, and rollout evidence",
        },
        {
            "code": "live_db_backed_typed_knowledge_api_readback_not_verified",
            "area": "typed_knowledge.live_db_backed_api",
            "closed": bool(readiness.get("live_db_persistence"))
            and _typed_knowledge_db_model_exists(root)
            and _public_typed_knowledge_api_exists(root),
            "evidence": ["main/backend/app/api/typed_knowledge.py"],
            "gap_recorded": "live_db_backed_typed_knowledge_readback_not_verified" in route_remaining,
            "required_to_close": "back the typed-knowledge route with live DB persistence and durable readback evidence",
        },
        {
            "code": "governance_ui_not_implemented",
            "area": "typed_knowledge.governance_ui",
            "closed": bool(readiness.get("governance_ui"))
            and ("typedKnowledge" in frontend_workbench or "typed_knowledge_governance" in frontend_workbench),
            "evidence": ["main/frontend-modern/src/pages/WritingWorkbenchPage.tsx"],
            "gap_recorded": "governance_ui_not_implemented" in remaining,
            "required_to_close": "add typed-knowledge governance UI with human acceptance and state mutation contract",
        },
        {
            "code": "migration_and_backfill_not_executed",
            "area": "typed_knowledge.migration_backfill",
            "closed": False,
            "evidence": ["main/backend/app/services/typed_knowledge/persistence_boundary.py"],
            "gap_recorded": "migration_and_backfill_not_executed" in remaining,
            "required_to_close": "run migration/backfill against a live DB and preserve evidence",
        },
        {
            "code": "writing_live_typed_knowledge_fetch_not_available",
            "area": "writing.public_typed_knowledge_fetch",
            "closed": _writing_live_typed_knowledge_fetch_exists(sources),
            "evidence": ["main/backend/app/api/writing.py", "main/frontend-modern/src/lib/api/domains/writing.ts"],
            "gap_recorded": True,
            "required_to_close": "wire writing workbench to a live typed-knowledge fetch API instead of envelope-only context injection",
        },
        {
            "code": "writing_ui_governance_mutation_not_available",
            "area": "writing.ui_governance_mutation",
            "closed": False,
            "evidence": ["main/frontend-modern/src/pages/WritingWorkbenchPage.tsx"],
            "gap_recorded": True,
            "required_to_close": "add explicit governance mutation controls and API contract, not just resource-card consumption",
        },
        {
            "code": "persisted_typed_knowledge_cards_live_readback_not_verified",
            "area": "writing.live_db_card_survival",
            "closed": False,
            "evidence": ["main/backend/tests/unit/test_writing_keyword_card_service_unittest.py"],
            "gap_recorded": True,
            "required_to_close": "prove typed-knowledge cards survive process restart through live DB/API readback",
        },
    ]


def _evidence_docs(root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for rel_path in EVIDENCE_DOCS:
        path = root / rel_path
        text = _read_text(root, rel_path)
        markers = list(WAVE10_DOC_MARKERS if "wave10" in rel_path.name else LIVE_BOUNDARY_DOC_MARKERS)
        if "wave15" in rel_path.name:
            markers.extend(WAVE15_DOC_MARKERS)
        docs.append(
            {
                "path": rel_path.as_posix(),
                "exists": path.is_file(),
                "required_markers": markers,
                "missing_markers": [marker for marker in markers if marker not in text],
            }
        )
    return docs


def build_inventory(root: Path = REPO_ROOT) -> dict[str, Any]:
    root = root.resolve()
    sources = _source_inventory(root)
    deterministic_coverage = _deterministic_coverage(root, sources)
    live_boundaries = _live_boundaries(root, sources)
    evidence_docs = _evidence_docs(root)
    failures = validate_inventory(
        {
            "contract_version": CONTRACT_VERSION,
            "deterministic_coverage": deterministic_coverage,
            "live_boundaries": live_boundaries,
            "evidence_docs": evidence_docs,
            "closure_claim_allowed": False,
            "readiness_state": READINESS_STATE,
        }
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "scope": "typed_knowledge_to_writing_workbench_live_boundary",
        "status": "passed" if not failures else "failed",
        "readiness_state": READINESS_STATE,
        "closure_position": CLOSURE_POSITION,
        "closure_claim_allowed": False,
        "deterministic_coverage": deterministic_coverage,
        "live_boundaries": live_boundaries,
        "remaining_live_gaps": [row["code"] for row in live_boundaries if not row["closed"]],
        "unsupported_closure_claims": [
            {
                "code": "typed_writing_live_boundary_closed",
                "reason": "live DB/API/UI evidence is intentionally absent in this Wave15 boundary inventory",
            }
        ],
        "source_inventory": [
            {"name": name, "path": row["path"], "exists": row["exists"]}
            for name, row in sources.items()
        ],
        "evidence_docs": evidence_docs,
        "failures": failures,
    }


def validate_inventory(inventory: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if inventory.get("contract_version") != CONTRACT_VERSION:
        failures.append("contract_version_mismatch")
    if inventory.get("readiness_state") != READINESS_STATE:
        failures.append("readiness_state_must_remain_partial")
    if inventory.get("closure_claim_allowed") is not False:
        failures.append("closure_claim_allowed_must_remain_false")

    coverage_by_code = {
        str(row.get("code")): row
        for row in inventory.get("deterministic_coverage", [])
        if isinstance(row, Mapping)
    }
    for code in REQUIRED_DETERMINISTIC_COVERAGE:
        row = coverage_by_code.get(code)
        if row is None:
            failures.append(f"missing_deterministic_coverage:{code}")
        elif row.get("passed") is not True:
            failures.append(f"deterministic_coverage_failed:{code}")

    live_by_code = {
        str(row.get("code")): row
        for row in inventory.get("live_boundaries", [])
        if isinstance(row, Mapping)
    }
    for code in REQUIRED_OPEN_GAPS:
        row = live_by_code.get(code)
        if row is None:
            failures.append(f"missing_live_boundary_gap:{code}")
            continue
        if row.get("closed") is not False:
            failures.append(f"live_boundary_overclaimed:{code}")
        if row.get("gap_recorded") is not True:
            failures.append(f"live_boundary_gap_not_recorded:{code}")

    for doc in inventory.get("evidence_docs", []):
        if not isinstance(doc, Mapping):
            failures.append("invalid_evidence_doc_entry")
            continue
        if doc.get("exists") is not True:
            failures.append(f"missing_evidence_doc:{doc.get('path')}")
        for marker in doc.get("missing_markers") or []:
            failures.append(f"evidence_doc_missing_marker:{doc.get('path')}:{marker}")

    return failures


def _print_text(inventory: Mapping[str, Any]) -> None:
    print(
        "OK typed_writing_live_boundary=passed"
        if inventory["status"] == "passed"
        else "FAIL typed_writing_live_boundary=failed"
    )
    print(f"contract_version={inventory['contract_version']}")
    print(f"readiness_state={inventory['readiness_state']}")
    print(f"closure_claim_allowed={str(inventory['closure_claim_allowed']).lower()}")
    print("deterministic_coverage:")
    for row in inventory["deterministic_coverage"]:
        print(f"- {row['code']}: {'passed' if row['passed'] else 'failed'}")
    print("remaining_live_gaps:")
    for gap in inventory["remaining_live_gaps"]:
        print(f"- {gap}")
    if inventory["failures"]:
        print("failures:")
        for failure in inventory["failures"]:
            print(f"- {failure}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check typed-knowledge/writing live boundary inventory.")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root")
    args = parser.parse_args()

    inventory = build_inventory(Path(args.root))
    if args.format == "json":
        print(json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(inventory)
    return 0 if inventory["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
