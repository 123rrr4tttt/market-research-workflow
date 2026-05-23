#!/usr/bin/env python3
"""Wave27 structured/consumer closure decision gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(BACKEND_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT / "scripts"))

from app.services.document_queries import (  # noqa: E402
    DOCUMENT_QUERY_CONTRACT_VERSION,
    build_document_query,
    build_document_query_statement,
    build_search_endpoint_document_query_envelope,
    build_structured_data_search_document_query_envelope,
    compile_document_query_statement,
    validate_document_query_result_envelope,
)
from check_admin_dashboard_consumer_boundary import build_check as build_admin_dashboard_check  # noqa: E402
from check_consumer_side_facade_contract import build_check as build_consumer_side_check  # noqa: E402
from check_consumer_sql_predicate_facade import build_check as build_consumer_sql_check  # noqa: E402
from check_policy_state_document_query_boundary import build_check as build_policy_state_check  # noqa: E402
from check_prompt_time_density_consumer_boundary import build_check as build_prompt_time_density_check  # noqa: E402
from check_structured_sql_helper_migration import build_check as build_structured_sql_check  # noqa: E402


CONTRACT_VERSION = "wave27.structured_consumer_closure.v1"
STRUCTURED_TOPIC_ID = "2026-03-12-data-structured-service-modularization"
CONSUMER_TOPIC_ID = "2026-03-14-consumer-side-modularization"
LIVE_EVIDENCE_CONTRACT_VERSION = "wave45.structured_consumer_live_api_evidence.v1"

SEARCH_API_PATH = "main/backend/app/api/search.py"
STRUCTURED_SEARCH_SERVICE_PATH = "main/backend/app/services/agent_runtime/structured_data_search.py"
DOCUMENT_QUERY_BUILDER_EXPECTED_EXPORTS = (
    "build_document_query_statement",
    "compile_document_query_statement",
    "apply_document_query_to_statement",
    "document_query_to_statement",
)


def _repo_root() -> Path:
    return REPO_ROOT


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _marker_gaps(root: Path, rel_path: str, markers: tuple[str, ...]) -> list[str]:
    path = root / rel_path
    if not path.is_file():
        return list(markers)
    text = _read_text(path)
    return [marker for marker in markers if marker not in text]


def _gate(name: str, *, topic_id: str, result: dict[str, Any], passed: bool | None = None) -> dict[str, Any]:
    validation = result.get("validation") if isinstance(result, dict) else {}
    gate_passed = bool(validation.get("passed")) if passed is None else bool(passed)
    return {
        "name": name,
        "topic_id": topic_id,
        "contract_version": result.get("contract_version"),
        "status": result.get("status"),
        "passed": gate_passed,
        "problem_count": validation.get("problem_count"),
        "summary": validation,
    }


def _build_endpoint_projection_gate(root: Path) -> dict[str, Any]:
    search_envelope = build_search_endpoint_document_query_envelope(
        query=" robotics policy ",
        state="CA",
        modality="text",
        rank="hybrid",
        top_k=3,
        project_key="demo_proj",
        used_backends=("opensearch_lexical", "qdrant_vector"),
        results=[
            {
                "id": "doc-1",
                "document_id": 1,
                "title": "Robotics policy note",
                "summary": "Evidence for robotics policy pilots.",
                "url": "https://example.org/robotics-policy",
                "score": 0.82,
                "backend": "opensearch_lexical",
            }
        ],
    )
    structured_envelope = build_structured_data_search_document_query_envelope(
        project_key="demo_proj",
        query="robotics",
        datasets_requested=("documents", "market_stats"),
        limit=8,
        query_mode="search",
        total_matches=1,
        total_stored_rows=3,
        fallback_used=False,
        items=[
            {
                "dataset": "documents",
                "record_id": "doc-7",
                "title": "Robot local note",
                "summary": "stored robot evidence",
                "source_uri": "https://example.org/robot",
            }
        ],
    )
    validate_document_query_result_envelope(search_envelope)
    validate_document_query_result_envelope(structured_envelope)

    search_data = search_envelope["data"]
    structured_data = structured_envelope["data"]
    search_marker_gaps = _marker_gaps(
        root,
        SEARCH_API_PATH,
        (
            "build_search_endpoint_document_query_envelope",
            "document_query_contract_version",
            "document_query_results",
            "document_query_pagination",
            "document_query_meta",
        ),
    )
    structured_marker_gaps = _marker_gaps(
        root,
        STRUCTURED_SEARCH_SERVICE_PATH,
        (
            "build_structured_data_search_document_query_envelope",
            "document_query_contract_version",
            "document_query_results",
            "document_query_pagination",
            "document_query_meta",
        ),
    )
    problems: list[str] = []
    if search_data["contract_version"] != DOCUMENT_QUERY_CONTRACT_VERSION:
        problems.append("api.search projection contract version mismatch")
    if search_data["query"]["consumer"] != "api.search":
        problems.append("api.search projection consumer mismatch")
    if structured_data["query"]["consumer"] != "project.structured_data.search":
        problems.append("structured-data projection consumer mismatch")
    if search_marker_gaps:
        problems.append(f"api.search marker gaps: {search_marker_gaps}")
    if structured_marker_gaps:
        problems.append(f"structured-data search marker gaps: {structured_marker_gaps}")

    return {
        "contract_version": "wave27.endpoint_projection_gate.v1",
        "topic_id": STRUCTURED_TOPIC_ID,
        "status": "passed" if not problems else "failed",
        "validation": {
            "passed": not problems,
            "problem_count": len(problems),
            "problems": problems,
            "covered_endpoints": [
                "/api/v1/search",
                "project.structured_data.search",
            ],
            "api_search_marker_gaps": search_marker_gaps,
            "structured_search_marker_gaps": structured_marker_gaps,
        },
    }


def _document_query_statement_builder_status(root: Path) -> dict[str, Any]:
    query_dir = root / "main" / "backend" / "app" / "services" / "document_queries"
    exports = _read_text(query_dir / "__init__.py") if (query_dir / "__init__.py").is_file() else ""
    candidates: list[dict[str, Any]] = []
    for path in sorted(query_dir.glob("*.py")):
        text = _read_text(path)
        matched = [token for token in DOCUMENT_QUERY_BUILDER_EXPECTED_EXPORTS if token in text]
        if matched:
            candidates.append({"path": str(path.relative_to(root)), "matched_tokens": matched})
    exported = [token for token in DOCUMENT_QUERY_BUILDER_EXPECTED_EXPORTS if token in exports]
    compile_gaps: list[str] = []
    compiled_sql = ""
    if exported and candidates:
        try:
            sample_query = build_document_query(
                "robotics policy",
                project_key="demo_proj",
                consumer="wave27.structured_closure",
                sources=("document",),
                filters=(
                    {"field": "state", "op": "eq", "value": "CA"},
                    {"field": "doc_type", "op": "in", "value": ["policy", "news"]},
                    {"field": "extracted_data.policy.policy_type", "op": "contains", "value": "grant"},
                ),
                sort=({"field": "published_at", "direction": "desc"},),
                limit=7,
                offset=3,
            )
            statement = build_document_query_statement(sample_query)
            compiled_sql = compile_document_query_statement(statement)
            required_fragments = (
                "FROM documents",
                "documents.state = 'CA'",
                "documents.doc_type IN ('policy', 'news')",
                "project_key",
                "policy_type",
                "ORDER BY documents.publish_date DESC NULLS LAST",
                "LIMIT 7 OFFSET 3",
            )
            compile_gaps = [fragment for fragment in required_fragments if fragment not in compiled_sql]
        except Exception as exc:  # pragma: no cover - surfaced in checker output.
            compile_gaps = [f"{type(exc).__name__}: {exc}"]
    covered = bool(exported and candidates and not compile_gaps)
    return {
        "boundary_id": "generic_document_query_db_statement_builder",
        "expected_exports": list(DOCUMENT_QUERY_BUILDER_EXPECTED_EXPORTS),
        "exported_tokens": exported,
        "candidate_definitions": candidates,
        "compiled_sql_sample": compiled_sql,
        "compile_gaps": compile_gaps,
        "exists": covered,
        "status": "covered" if covered else "missing_repo_local_builder",
    }


def _load_live_evidence(path: Path | str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    evidence_path = Path(path)
    if not evidence_path.is_file():
        return {
            "status": "failed",
            "path": str(evidence_path),
            "problems": ["live evidence file is missing"],
        }
    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "failed",
            "path": str(evidence_path),
            "problems": [f"invalid live evidence JSON: {exc}"],
        }
    if not isinstance(data, dict):
        return {
            "status": "failed",
            "path": str(evidence_path),
            "problems": ["live evidence root must be an object"],
        }
    data["path"] = str(evidence_path)
    return data


def _live_evidence_status(evidence: dict[str, Any] | None) -> dict[str, Any]:
    required_flags = (
        "live_db_api_smoke_validated",
        "structured_query_endpoint_validated",
        "statement_builder_live_db_execution_validated",
        "search_consumer_validated",
        "admin_dashboard_consumer_validated",
        "policy_consumer_validated",
        "prompt_time_density_consumer_validated",
    )
    if evidence is None:
        return {
            "status": "not_provided",
            "validated": False,
            "problems": ["live evidence was not provided"],
            "required_flags": list(required_flags),
        }
    problems = list(evidence.get("problems") or [])
    if evidence.get("contract_version") != LIVE_EVIDENCE_CONTRACT_VERSION:
        problems.append("contract_version mismatch")
    if evidence.get("status") != "passed":
        problems.append("status must be passed")
    for flag in required_flags:
        if evidence.get(flag) is not True:
            problems.append(f"{flag} must be true")
    endpoints = evidence.get("endpoints")
    if not isinstance(endpoints, list) or len(endpoints) < 6:
        problems.append("endpoints must contain at least six live API checks")
    else:
        for index, endpoint in enumerate(endpoints):
            if not isinstance(endpoint, dict):
                problems.append(f"endpoints[{index}] must be an object")
                continue
            if int(endpoint.get("http_status") or 0) != 200:
                problems.append(f"endpoints[{index}] http_status must be 200")
            if endpoint.get("validated") is not True:
                problems.append(f"endpoints[{index}] validated must be true")
    statement_builder = evidence.get("live_db_statement_builder")
    if not isinstance(statement_builder, dict):
        problems.append("live_db_statement_builder must be an object")
    else:
        if statement_builder.get("status") != "passed":
            problems.append("live_db_statement_builder.status must be passed")
        if int(statement_builder.get("row_count") or 0) <= 0:
            problems.append("live_db_statement_builder.row_count must be positive")
        fragments = statement_builder.get("compiled_sql_contains")
        if not isinstance(fragments, dict) or not all(bool(value) for value in fragments.values()):
            problems.append("live_db_statement_builder.compiled_sql_contains must all be true")
    return {
        "status": "validated" if not problems else "failed",
        "validated": not problems,
        "path": evidence.get("path"),
        "project_key": evidence.get("project_key"),
        "endpoint_count": len(endpoints) if isinstance(endpoints, list) else 0,
        "problems": problems,
        "required_flags": list(required_flags),
    }


def build_check(
    repo_root: Path | str | None = None,
    *,
    live_evidence_path: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root is not None else _repo_root().resolve()

    structured_sql = build_structured_sql_check(root)
    consumer_side = build_consumer_side_check(root)
    consumer_sql = build_consumer_sql_check(root)
    admin_dashboard = build_admin_dashboard_check(root)
    policy_state = build_policy_state_check(root)
    prompt_time_density = build_prompt_time_density_check(root)
    endpoint_projection = _build_endpoint_projection_gate(root)
    builder_status = _document_query_statement_builder_status(root)
    live_evidence = _load_live_evidence(live_evidence_path)
    live_evidence_status = _live_evidence_status(live_evidence)

    gates = [
        _gate("structured_sql_helper_migration", topic_id=STRUCTURED_TOPIC_ID, result=structured_sql),
        _gate(
            "structured_endpoint_projection",
            topic_id=STRUCTURED_TOPIC_ID,
            result=endpoint_projection,
        ),
        _gate("consumer_side_facade_contract", topic_id=CONSUMER_TOPIC_ID, result=consumer_side),
        _gate("consumer_sql_predicate_facade", topic_id=CONSUMER_TOPIC_ID, result=consumer_sql),
        _gate("admin_dashboard_consumer_boundary", topic_id=CONSUMER_TOPIC_ID, result=admin_dashboard),
        _gate("policy_state_document_query_boundary", topic_id=CONSUMER_TOPIC_ID, result=policy_state),
        _gate("prompt_time_density_consumer_boundary", topic_id=CONSUMER_TOPIC_ID, result=prompt_time_density),
    ]

    repo_local_blockers: list[dict[str, Any]] = []
    for gate in gates:
        if not gate["passed"]:
            repo_local_blockers.append(
                {
                    "id": f"{gate['name']}_failed",
                    "kind": "repo_local_gate_failure",
                    "topic_id": gate["topic_id"],
                    "detail": gate["summary"],
                }
            )

    if builder_status["status"] != "covered":
        repo_local_blockers.append(
            {
                "id": "generic_document_query_db_statement_builder_missing",
                "kind": "repo_local_db_builder_gap",
                "topic_id": STRUCTURED_TOPIC_ID,
                "detail": (
                    "No exported DocumentQuery-to-SQLAlchemy statement builder was found under "
                    "main/backend/app/services/document_queries. Existing endpoint/predicate helpers are covered, "
                    "but the generic DB statement-builder scope remains repo-local if it is still required."
                ),
                "builder_status": builder_status,
            }
        )

    external_blockers = []
    if not live_evidence_status["validated"]:
        external_blockers.append(
            {
                "id": "live_db_api_smoke_not_run",
                "kind": "external_runtime_validation",
                "topic_ids": [STRUCTURED_TOPIC_ID, CONSUMER_TOPIC_ID],
                "detail": (
                    "Focused gates are deterministic and do not start a live tenant DB/API stack; live DB/API smoke "
                    "remains a separate external-runtime validation condition."
                ),
                "live_evidence_status": live_evidence_status,
            }
        )
    structured_repo_local_blockers = [
        blocker for blocker in repo_local_blockers if blocker.get("topic_id") == STRUCTURED_TOPIC_ID
    ]
    consumer_repo_local_blockers = [
        blocker for blocker in repo_local_blockers if blocker.get("topic_id") == CONSUMER_TOPIC_ID
    ]
    structured_archive_eligible = not structured_repo_local_blockers
    consumer_archive_eligible = not consumer_repo_local_blockers
    validation_passed = all(gate["passed"] for gate in gates)
    closure_ready = validation_passed and not repo_local_blockers and not external_blockers

    return {
        "contract_version": CONTRACT_VERSION,
        "topic_ids": [STRUCTURED_TOPIC_ID, CONSUMER_TOPIC_ID],
        "status": "passed" if validation_passed else "failed",
        "decision": {
            "status": "closed" if closure_ready else "external_blocked_candidate",
            "archive_eligible": structured_archive_eligible and consumer_archive_eligible,
            "repo_local_blocker_count": len(repo_local_blockers),
            "external_blocker_count": len(external_blockers),
            "recommendation": (
                "move structured service modularization and consumer-side modularization to ARCHIVE_CLOSED"
                if closure_ready
                else "move structured service modularization to ARCHIVE_EXTERNAL_BLOCKED when the supervisor performs the next CURRENT_DEV status migration"
            ),
            "topics": {
                STRUCTURED_TOPIC_ID: {
                    "status": (
                        "closed"
                        if closure_ready and structured_archive_eligible
                        else "external_blocked_candidate"
                        if structured_archive_eligible
                        else "retained_partial"
                    ),
                    "archive_eligible": structured_archive_eligible,
                    "repo_local_blocker_count": len(structured_repo_local_blockers),
                    "external_blocker_ids": [item["id"] for item in external_blockers],
                },
                CONSUMER_TOPIC_ID: {
                    "status": (
                        "closed"
                        if closure_ready and consumer_archive_eligible
                        else "external_blocked_candidate"
                        if consumer_archive_eligible
                        else "retained_partial"
                    ),
                    "archive_eligible": consumer_archive_eligible,
                    "repo_local_blocker_count": len(consumer_repo_local_blockers),
                    "external_blocker_ids": [item["id"] for item in external_blockers],
                },
            },
        },
        "gates": gates,
        "repo_local_blockers": repo_local_blockers,
        "external_blockers": external_blockers,
        "validation": {
            "passed": validation_passed,
            "gate_count": len(gates),
            "passed_gate_count": sum(1 for gate in gates if gate["passed"]),
            "document_query_statement_builder": builder_status,
            "live_evidence": live_evidence_status,
            "closure_ready": closure_ready,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave27 structured/consumer closure decision.")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--live-evidence-json", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build_check(live_evidence_path=args.live_evidence_json)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
