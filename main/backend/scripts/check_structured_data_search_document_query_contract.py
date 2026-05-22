#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.document_queries import (  # noqa: E402
    DOCUMENT_QUERY_CONTRACT_VERSION,
    build_structured_data_search_document_query_envelope,
    validate_document_query_result_envelope,
)


SERVICE_PATH = REPO_ROOT / "main" / "backend" / "app" / "services" / "agent_runtime" / "structured_data_search.py"
REQUIRED_SERVICE_MARKERS = (
    "build_structured_data_search_document_query_envelope",
    "document_query_contract_version",
    "document_query_results",
    "document_query_pagination",
    "document_query_meta",
)


def _service_marker_gaps() -> list[str]:
    text = SERVICE_PATH.read_text(encoding="utf-8")
    return [marker for marker in REQUIRED_SERVICE_MARKERS if marker not in text]


def main() -> int:
    envelope = build_structured_data_search_document_query_envelope(
        project_key="demo_proj",
        query=" robotics ",
        datasets_requested=("documents", "market_stats"),
        limit=999,
        query_mode="search",
        total_matches=3,
        total_stored_rows=9,
        fallback_used=False,
        items=[
            {
                "dataset": "documents",
                "record_id": "doc-1",
                "title": "Robotics local note",
                "summary": "Stored robotics evidence.",
                "source_uri": "https://example.org/robotics",
                "fields": {"source_name": "fixture"},
            }
        ],
    )
    validate_document_query_result_envelope(envelope)
    data = envelope["data"]
    query = data["query"]
    result = data["results"][0] if data["results"] else {}
    gaps = _service_marker_gaps()
    checks = {
        "contract_version": data["contract_version"],
        "consumer": query["consumer"],
        "project_key": query["project_key"],
        "dataset_filter": query["filters"][0] if query["filters"] else None,
        "limit": query["limit"],
        "result_count": data["pagination"]["result_count"],
        "pagination_total": data["pagination"]["total"],
        "result_source_type": result.get("source_type"),
        "result_backend": result.get("backend"),
        "meta_source": envelope["meta"].get("source"),
        "meta_total_stored_rows": envelope["meta"].get("total_stored_rows"),
        "service_marker_gaps": gaps,
    }
    passed = (
        checks["contract_version"] == DOCUMENT_QUERY_CONTRACT_VERSION
        and checks["consumer"] == "project.structured_data.search"
        and checks["project_key"] == "demo_proj"
        and checks["dataset_filter"] == {"field": "dataset", "op": "in", "value": ["documents", "market_stats"]}
        and checks["limit"] == 100
        and checks["result_count"] == 1
        and checks["pagination_total"] == 3
        and checks["result_source_type"] == "structured_record"
        and checks["result_backend"] == "documents"
        and checks["meta_source"] == "agent_runtime.structured_data_search"
        and checks["meta_total_stored_rows"] == 9
        and not gaps
    )
    print(json.dumps({"status": "pass" if passed else "fail", "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
