#!/usr/bin/env python3
"""Check current graph/typed/writing/consumer closure authority.

Wave27 external-blocked decisions remain useful history, but the current
authority is the later Wave45/46/54 closure record in canonical
``docs/development`` ARCHIVE_CLOSED directories.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]

CONTRACT_VERSION = "graph_typed_writing_consumer.status_boundary.v2"
CANONICAL_ROOT = Path("docs/development/development-plans/ARCHIVE_CLOSED")
CLOSED_INDEX = CANONICAL_ROOT / "INDEX.md"
TARGET_STATUS = "closed"

TOPICS: tuple[dict[str, Any], ...] = (
    {
        "id": "2026-03-07-graph-editing-and-reporting",
        "label": "graph_editing_and_reporting",
        "closure_wave": 46,
        "closure_doc": "12_wave46-manual-live-audit-closure-2026-05-23.md",
        "historical_decision": "11_wave27-external-blocked-decision-2026-05-23.md",
        "required_closure_tokens": (
            "Status: `closed`",
            "closure_claim=true",
            "live_tenant_db_audit_open=false",
        ),
    },
    {
        "id": "2026-03-07-typed-knowledge-organization",
        "label": "typed_knowledge_organization",
        "closure_wave": 54,
        "closure_doc": "07_wave54-typed-writing-live-closure-2026-05-23.md",
        "historical_decision": "10_wave27-external-blocked-decision-2026-05-23.md",
        "required_closure_tokens": (
            "status: `closed`",
            "archive: `ARCHIVE_CLOSED`",
            "closure_claim_allowed: true",
            "remaining_live_gaps empty",
        ),
    },
    {
        "id": "2026-03-07-writing-workbench-evolution",
        "label": "writing_workbench_evolution",
        "closure_wave": 54,
        "closure_doc": "08_wave54-typed-writing-live-closure-2026-05-23.md",
        "historical_decision": "11_wave27-external-blocked-decision-2026-05-23.md",
        "required_closure_tokens": (
            "status: `closed`",
            "archive: `ARCHIVE_CLOSED`",
            "closure_claim_allowed: true",
            "remaining_live_gaps empty",
        ),
    },
    {
        "id": "2026-03-14-consumer-side-modularization",
        "label": "consumer_side_modularization",
        "closure_wave": 45,
        "closure_doc": "09_wave45-manual-live-api-closure-2026-05-23.md",
        "historical_decision": "08_wave27-external-blocked-decision-2026-05-23.md",
        "required_closure_tokens": (
            "Status: `closed`",
            "status=passed",
            "decision.status=closed",
            "external_blocker_count=0",
        ),
    },
)

HISTORICAL_STATUS_RE = re.compile(r"external[_ -]?blocked|closure_claim(?:_allowed)?[=:]false", re.IGNORECASE)


def _read_text(root: Path, rel_path: Path) -> str:
    try:
        return (root / rel_path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _topic_result(root: Path, closed_index_text: str, topic: Mapping[str, Any]) -> dict[str, Any]:
    topic_dir = CANONICAL_ROOT / str(topic["id"])
    topic_index = topic_dir / "INDEX.md"
    closure_doc = topic_dir / str(topic["closure_doc"])
    historical_doc = topic_dir / str(topic["historical_decision"])
    topic_index_text = _read_text(root, topic_index)
    closure_text = _read_text(root, closure_doc)
    historical_text = _read_text(root, historical_doc)
    required_tokens = list(topic["required_closure_tokens"])
    missing_tokens = [token for token in required_tokens if token not in closure_text]
    closed_index_row = next((line for line in closed_index_text.splitlines() if str(topic["id"]) in line), "")
    return {
        "topic_id": topic["id"],
        "label": topic["label"],
        "canonical_status": TARGET_STATUS if not missing_tokens and (root / closure_doc).is_file() else "missing",
        "closure_wave": topic["closure_wave"],
        "canonical_directory": topic_dir.as_posix(),
        "canonical_directory_exists": (root / topic_dir).is_dir(),
        "canonical_closure_doc": closure_doc.as_posix(),
        "canonical_closure_doc_exists": (root / closure_doc).is_file(),
        "required_closure_tokens": required_tokens,
        "missing_closure_tokens": missing_tokens,
        "topic_index": topic_index.as_posix(),
        "topic_index_has_current_authority": (
            TARGET_STATUS in topic_index_text.lower()
            and str(topic["closure_doc"]) in topic_index_text
            and "canonical" in topic_index_text.lower()
        ),
        "closed_index_row": closed_index_row,
        "closed_index_points_to_closure": str(topic["closure_doc"]) in closed_index_row,
        "historical_wave27": {
            "path": historical_doc.as_posix(),
            "exists": (root / historical_doc).is_file(),
            "classification": "historical_pre_closure_snapshot",
            "contains_pre_closure_status": bool(HISTORICAL_STATUS_RE.search(historical_text)),
            "is_current_authority": False,
        },
    }


def build_check(repo_root: Path | str = REPO_ROOT) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=docs/development/development-plans/ARCHIVE_CLOSED/topic_INDEX+closure_doc "
    "witness=test:test_c13_cli_graph_workflow_metadata_preserves_abi",
]:
    root = Path(repo_root).resolve()
    closed_index_text = _read_text(root, CLOSED_INDEX)
    topics = [_topic_result(root, closed_index_text, topic) for topic in TOPICS]
    report: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "scope": "graph_typed_writing_consumer_canonical_closure_authority",
        "status": "passed",
        "authority": {
            "root": CANONICAL_ROOT.as_posix(),
            "index": CLOSED_INDEX.as_posix(),
            "status": TARGET_STATUS,
            "historical_wave27_is_current_authority": False,
        },
        "topics": topics,
        "history_semantics": {
            "classification": "pre_closure_snapshots",
            "current_authority": "topic INDEX.md plus Wave45/46/54 closure document",
            "deleted_json_or_jsonl_used_as_evidence": False,
        },
    }
    failures = validate_report(report)
    report["validation"] = {"passed": not failures, "failures": failures}
    report["status"] = "passed" if not failures else "failed"
    return report


def validate_report(report: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if report.get("contract_version") != CONTRACT_VERSION:
        failures.append("contract_version_mismatch")
    authority = report.get("authority") if isinstance(report.get("authority"), Mapping) else {}
    if authority.get("root") != CANONICAL_ROOT.as_posix():
        failures.append("canonical_authority_root_mismatch")
    if authority.get("historical_wave27_is_current_authority") is not False:
        failures.append("wave27_history_must_not_be_current_authority")
    topics = report.get("topics") if isinstance(report.get("topics"), list) else []
    if len(topics) != len(TOPICS):
        failures.append(f"expected_{len(TOPICS)}_topics")
    for topic in topics:
        if not isinstance(topic, Mapping):
            failures.append("topic_result_must_be_object")
            continue
        topic_id = topic.get("topic_id", "<missing>")
        if topic.get("canonical_status") != TARGET_STATUS:
            failures.append(f"canonical_closure_missing:{topic_id}")
        if topic.get("canonical_directory_exists") is not True:
            failures.append(f"canonical_directory_missing:{topic_id}")
        if topic.get("canonical_closure_doc_exists") is not True:
            failures.append(f"canonical_closure_doc_missing:{topic_id}")
        if topic.get("missing_closure_tokens") != []:
            failures.append(f"canonical_closure_tokens_missing:{topic_id}")
        if topic.get("topic_index_has_current_authority") is not True:
            failures.append(f"topic_index_authority_missing:{topic_id}")
        if topic.get("closed_index_points_to_closure") is not True:
            failures.append(f"closed_index_closure_link_missing:{topic_id}")
        history = topic.get("historical_wave27") if isinstance(topic.get("historical_wave27"), Mapping) else {}
        if history.get("is_current_authority") is not False:
            failures.append(f"historical_decision_promoted_to_current:{topic_id}")
    history_semantics = report.get("history_semantics") or {}
    if history_semantics.get("deleted_json_or_jsonl_used_as_evidence") is not False:
        failures.append("deleted_runtime_evidence_must_not_be_used")
    return failures


def _print_text(report: Mapping[str, Any]) -> None:
    print(f"{str(report.get('status')).upper()} {CONTRACT_VERSION}")
    for topic in report.get("topics") or []:
        print(f"{topic['topic_id']}={topic['canonical_status']} wave={topic['closure_wave']}")
    for failure in report.get("validation", {}).get("failures") or []:
        print(f"- {failure}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check canonical graph/typed/writing/consumer closure authority.")
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    report = build_check(args.root)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(report)
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
