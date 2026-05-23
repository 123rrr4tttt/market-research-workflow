from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .vector_contracts import (
    SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
    build_retrieval_run_record,
    validate_retrieval_run_record,
)


SEARCH_RETRIEVAL_RUN_READBACK_CONTRACT_VERSION = "search_retrieval_run_readback.v1"
RETRIEVAL_RUNS_BRANCHES_HITS_BLOCKER = "retrieval_runs_branches_hits_persistence_not_implemented"


def default_search_retrieval_runs_path() -> Path:
    configured = os.getenv("SEARCH_RETRIEVAL_RUNS_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path(tempfile.gettempdir()) / "market-research-workflow" / "search_retrieval_runs.jsonl"


def write_search_retrieval_run_record(path: Path | str, record: Mapping[str, Any]) -> dict[str, Any]:
    validate_retrieval_run_record(record)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "contract_version": SEARCH_RETRIEVAL_RUN_READBACK_CONTRACT_VERSION,
        "status": "written",
        "storage_kind": "local_jsonl",
        "path": str(destination),
        "run_id": record.get("run_id"),
        "retrieval_run_contract_version": SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
    }


def read_search_retrieval_run_record(path: Path | str, run_id: str) -> dict[str, Any]:
    source = Path(path)
    target_run_id = str(run_id or "").strip()
    if not target_run_id:
        raise ValueError("run_id is required for search retrieval run readback")
    if not source.exists():
        raise FileNotFoundError(f"search retrieval run store missing: {source}")

    matched: dict[str, Any] | None = None
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid search retrieval run JSONL at line {line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"search retrieval run JSONL line {line_number} must be an object")
            if str(row.get("run_id") or "") == target_run_id:
                matched = row

    if matched is None:
        raise KeyError(f"search retrieval run not found: {target_run_id}")
    validate_retrieval_run_record(matched)
    return matched


def persist_search_retrieval_run_record(
    record: Mapping[str, Any],
    *,
    path: Path | str | None = None,
) -> dict[str, Any]:
    destination = Path(path) if path is not None else default_search_retrieval_runs_path()
    write_result = write_search_retrieval_run_record(destination, record)
    readback = read_search_retrieval_run_record(destination, str(record.get("run_id") or ""))
    return {
        "contract_version": SEARCH_RETRIEVAL_RUN_READBACK_CONTRACT_VERSION,
        "status": "passed",
        "write_performed": True,
        "readback_performed": True,
        "readback_available": True,
        "storage_kind": write_result["storage_kind"],
        "path": write_result["path"],
        "run_id": record.get("run_id"),
        "retrieval_run_id": record.get("retrieval_run_id") or record.get("run_id"),
        "branch_count": len(list(readback.get("retrieval_branches") or [])),
        "hit_count": len(list(readback.get("retrieval_hits") or [])),
        "closed_repo_local_blockers": [RETRIEVAL_RUNS_BRANCHES_HITS_BLOCKER],
        "remaining_repo_local_blockers": [],
    }


def run_search_retrieval_run_readback_gate(
    *,
    query: str,
    query_group_id: str,
    evidence_hits: list[Mapping[str, Any]],
    path: Path | str,
    project_key: str | None = None,
    rank_mode: str = "hybrid",
    state: str | None = None,
    modality: str = "any",
    top_k: int | None = None,
    retrieval_family: str = "main_search",
) -> dict[str, Any]:
    record = build_retrieval_run_record(
        query=query,
        query_group_id=query_group_id,
        evidence_hits=evidence_hits,
        project_key=project_key,
        rank_mode=rank_mode,
        state=state,
        modality=modality,
        top_k=top_k,
        retrieval_family=retrieval_family,
    )
    persistence = persist_search_retrieval_run_record(record, path=path)
    readback = read_search_retrieval_run_record(path, str(record["run_id"]))
    return {
        "contract_version": SEARCH_RETRIEVAL_RUN_READBACK_CONTRACT_VERSION,
        "status": "passed",
        "write_performed": True,
        "readback_performed": True,
        "record_path": str(Path(path)),
        "run_id": record["run_id"],
        "query_group_id": query_group_id,
        "retrieval_run_contract_version": SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
        "closed_repo_local_blockers": [RETRIEVAL_RUNS_BRANCHES_HITS_BLOCKER],
        "remaining_repo_local_blockers": [],
        "persistence": persistence,
        "readback_record": readback,
    }


__all__ = [
    "RETRIEVAL_RUNS_BRANCHES_HITS_BLOCKER",
    "SEARCH_RETRIEVAL_RUN_READBACK_CONTRACT_VERSION",
    "default_search_retrieval_runs_path",
    "persist_search_retrieval_run_record",
    "read_search_retrieval_run_record",
    "run_search_retrieval_run_readback_gate",
    "write_search_retrieval_run_record",
]
