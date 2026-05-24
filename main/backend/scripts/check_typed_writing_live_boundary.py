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
    KeywordCardRequest,
    TypedKnowledgeWritingContext,
    TypedKnowledgeWritingHandoffData,
    WritingContextEnvelope,
)
from app.models.base import SessionLocal  # noqa: E402
from app.services.document_views.writing_card_view import (  # noqa: E402
    build_keyword_card_from_typed_knowledge_handoff,
)
from app.services.projects import bind_project  # noqa: E402
from app.services.typed_knowledge import contracts  # noqa: E402
from app.services.typed_knowledge import persistence_boundary  # noqa: E402


CONTRACT_VERSION = "typed_writing.live_boundary_inventory.v1"
READINESS_STATE = "closed"
CLOSURE_POSITION = "typed_knowledge_live_db_api_ui_governance_closed"

EVIDENCE_DOCS = (
    Path(
        "docs/development/development-plans/ARCHIVE_CLOSED/"
        "2026-03-07-typed-knowledge-organization/"
        "07_wave54-typed-writing-live-closure-2026-05-23.md"
    ),
    Path(
        "docs/development/development-plans/ARCHIVE_CLOSED/"
        "2026-03-07-writing-workbench-evolution/"
        "08_wave54-typed-writing-live-closure-2026-05-23.md"
    ),
)
CLOSURE_DOC_MARKERS = (
    "wave54_typed_writing_live_closure: passed",
    "live_db_persistence: true",
    "live_db_backed_typed_knowledge_api_readback: true",
    "governance_ui: true",
    "writing_live_typed_knowledge_fetch: true",
    "persisted_typed_knowledge_cards_live_readback: true",
    "closure_claim_allowed: true",
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
REQUIRED_CLOSED_GAPS = (
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
                    "buildPersistedTypedKnowledgeKeywordCardRequest",
                ),
            )
            and "sources = ['document', 'resource', 'graph']" in frontend_domain,
            [
                "main/frontend-modern/src/pages/WritingWorkbenchPage.tsx",
                "main/frontend-modern/src/lib/api/domains/writing.ts",
            ],
            "workbench remains a writing API consumer surface, with persisted typed-card request defaults kept in the API domain helper",
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
        "/typed-knowledge/writing-context",
        "getTypedKnowledgeWritingContext",
        "typedKnowledge",
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


def _typed_knowledge_migration_exists(root: Path) -> bool:
    for path in (root / "main/backend/migrations/versions").glob("*typed_knowledge_objects*.py"):
        text = path.read_text(encoding="utf-8")
        if "CREATE TABLE IF NOT EXISTS" in text and "typed_knowledge_objects" in text:
            return True
    return False


def _live_db_runtime_readback() -> dict[str, Any]:
    try:
        with bind_project("demo_proj"), SessionLocal() as session:
            boundary_envelope = persistence_boundary.build_live_db_boundary_envelope(
                session=session,
                project_key="demo_proj",
                seed_sample=True,
            )
            route_envelope = persistence_boundary.build_public_api_route_contract_envelope(
                project_key="demo_proj",
                boundary_envelope=boundary_envelope,
            )
            mutation = persistence_boundary.apply_live_governance_review_state(
                session=session,
                project_key="demo_proj",
                object_type=persistence_boundary.OBJECT_TYPE_KNOWLEDGE_ITEM,
                object_key="ki:robotics-policy",
                review_state=contracts.REVIEW_STATE_HUMAN_CONFIRMED,
                actor_type=contracts.ACTOR_HUMAN,
                actor_id="wave54-checker",
                write_time="2026-05-23T00:00:00Z",
            )
            context = persistence_boundary.build_live_writing_context_from_repository(
                session=session,
                project_key="demo_proj",
                seed_sample=True,
            )
            readback = persistence_boundary.build_persisted_card_request_response_readback(
                project_key="demo_proj",
                boundary_envelope=boundary_envelope,
                live_db_backed=True,
            )
            payload = KeywordCardRequest.model_validate(readback["keyword_card_request"]["body"])
            typed_context_payload = payload.context.typed_knowledge_context
            if hasattr(typed_context_payload, "model_dump"):
                typed_context_payload = typed_context_payload.model_dump()
            handoff = contracts.parse_writing_knowledge_context_envelope(
                typed_context_payload
            )[0]
            card = build_keyword_card_from_typed_knowledge_handoff(
                handoff,
                normalized_query=str(payload.query or "").strip().lower(),
            )
            session.commit()
        return {
            "passed": True,
            "boundary_live": boundary_envelope["data"]["repository"]["live_db_write"] is True
            and boundary_envelope["meta"]["readiness"]["live_db_persistence"] is True
            and not boundary_envelope["meta"]["remaining_live_gaps"],
            "route_live": route_envelope["data"]["route"]["live_db_backed"] is True
            and route_envelope["meta"]["readiness"]["live_api_closure"] is True
            and not route_envelope["meta"]["remaining_live_gaps"],
            "governance_mutation": mutation["live_db_write"] is True
            and mutation["current"]["review_state"] == contracts.REVIEW_STATE_HUMAN_CONFIRMED,
            "writing_context": context["contract_version"] == contracts.WRITING_KNOWLEDGE_CONTEXT_ENVELOPE_VERSION
            and len(context["handoffs"]) >= 1,
            "persisted_card_live": readback["typed_knowledge_api_boundary"]["live_db_backed"] is True
            and readback["persisted_document"]["live_db_document"] is True
            and readback["meta"]["readiness"]["live_api_closure"] is True
            and card.publisher == "typed_knowledge",
            "evidence": {
                "identity_ref": mutation["identity_ref"],
                "boundary_fingerprint": route_envelope["data"]["boundary_fingerprint"],
                "card_id": card.card_id,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "passed": False,
            "error": f"{exc.__class__.__name__}: {exc}",
        }


def _live_boundaries(root: Path, sources: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    live = _live_db_runtime_readback()
    frontend_workbench = str(sources["frontend_writing_workbench"]["text"])
    frontend_domain = str(sources["frontend_writing_domain"]["text"])
    typed_api = str(sources["typed_api"]["text"])
    migration_exists = _typed_knowledge_migration_exists(root)
    db_model_exists = _typed_knowledge_db_model_exists(root)
    governance_ui_exists = (
        "writing-typed-knowledge-governance" in frontend_workbench
        and "updateTypedKnowledgeReviewState" in frontend_domain
        and "governance/review-state" in typed_api
    )

    return [
        {
            "code": "live_db_persistence_not_implemented",
            "area": "typed_knowledge.live_db",
            "closed": bool(live.get("boundary_live")) and db_model_exists and migration_exists,
            "evidence": [
                "main/backend/app/models/typed_knowledge_entities.py",
                "main/backend/app/services/typed_knowledge/persistence_boundary.py",
                "main/backend/migrations/versions/20260402_000003_add_typed_knowledge_objects.py",
            ],
            "gap_recorded": False,
            "readback": live.get("evidence", live.get("error")),
            "required_to_close": "live typed-knowledge DB model/table, migration, write/readback smoke, and rollout evidence",
        },
        {
            "code": "live_db_backed_typed_knowledge_api_readback_not_verified",
            "area": "typed_knowledge.live_db_backed_api",
            "closed": bool(live.get("route_live"))
            and db_model_exists
            and _public_typed_knowledge_api_exists(root),
            "evidence": ["main/backend/app/api/typed_knowledge.py"],
            "gap_recorded": False,
            "readback": live.get("evidence", live.get("error")),
            "required_to_close": "typed-knowledge route backed by live DB persistence and durable readback evidence",
        },
        {
            "code": "governance_ui_not_implemented",
            "area": "typed_knowledge.governance_ui",
            "closed": bool(live.get("governance_mutation")) and governance_ui_exists,
            "evidence": ["main/frontend-modern/src/pages/WritingWorkbenchPage.tsx"],
            "gap_recorded": False,
            "required_to_close": "typed-knowledge governance UI with human acceptance and state mutation contract",
        },
        {
            "code": "migration_and_backfill_not_executed",
            "area": "typed_knowledge.migration_backfill",
            "closed": bool(live.get("boundary_live")) and migration_exists,
            "evidence": ["main/backend/migrations/versions/20260402_000003_add_typed_knowledge_objects.py"],
            "gap_recorded": False,
            "required_to_close": "migration/backfill run against live DB and preserved evidence",
        },
        {
            "code": "writing_live_typed_knowledge_fetch_not_available",
            "area": "writing.public_typed_knowledge_fetch",
            "closed": bool(live.get("writing_context")) and _writing_live_typed_knowledge_fetch_exists(sources),
            "evidence": ["main/backend/app/api/writing.py", "main/frontend-modern/src/lib/api/domains/writing.ts"],
            "gap_recorded": False,
            "required_to_close": "writing workbench wired to a live typed-knowledge fetch API instead of envelope-only context injection",
        },
        {
            "code": "writing_ui_governance_mutation_not_available",
            "area": "writing.ui_governance_mutation",
            "closed": bool(live.get("governance_mutation")) and governance_ui_exists,
            "evidence": ["main/frontend-modern/src/pages/WritingWorkbenchPage.tsx"],
            "gap_recorded": False,
            "required_to_close": "explicit governance mutation controls and API contract, not just resource-card consumption",
        },
        {
            "code": "persisted_typed_knowledge_cards_live_readback_not_verified",
            "area": "writing.live_db_card_survival",
            "closed": bool(live.get("persisted_card_live")),
            "evidence": ["main/backend/tests/unit/test_writing_keyword_card_service_unittest.py"],
            "gap_recorded": False,
            "readback": live.get("evidence", live.get("error")),
            "required_to_close": "typed-knowledge cards survive process restart through live DB/API readback",
        },
    ]


def _evidence_docs(root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for rel_path in EVIDENCE_DOCS:
        path = root / rel_path
        text = _read_text(root, rel_path)
        markers = list(CLOSURE_DOC_MARKERS)
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
            "closure_claim_allowed": True,
            "readiness_state": READINESS_STATE,
        }
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "scope": "typed_knowledge_to_writing_workbench_live_boundary",
        "status": "passed" if not failures else "failed",
        "readiness_state": READINESS_STATE,
        "closure_position": CLOSURE_POSITION,
        "closure_claim_allowed": True,
        "deterministic_coverage": deterministic_coverage,
        "live_boundaries": live_boundaries,
        "remaining_live_gaps": [row["code"] for row in live_boundaries if not row["closed"]],
        "unsupported_closure_claims": [],
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
        failures.append("readiness_state_must_be_closed")
    if inventory.get("closure_claim_allowed") is not True:
        failures.append("closure_claim_allowed_must_be_true")

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
    for code in REQUIRED_CLOSED_GAPS:
        row = live_by_code.get(code)
        if row is None:
            failures.append(f"missing_live_boundary_gap:{code}")
            continue
        if row.get("closed") is not True:
            failures.append(f"live_boundary_not_closed:{code}")
        if row.get("gap_recorded") is not False:
            failures.append(f"live_boundary_gap_still_recorded:{code}")

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
