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
    build_search_endpoint_document_query_envelope,
    validate_document_query_result_envelope,
)


API_SEARCH_PATH = REPO_ROOT / "main" / "backend" / "app" / "api" / "search.py"
REQUIRED_API_MARKERS = (
    "build_search_endpoint_document_query_envelope",
    "document_query_contract_version",
    "document_query_results",
    "document_query_pagination",
    "document_query_meta",
)


def _api_marker_gaps() -> list[str]:
    text = API_SEARCH_PATH.read_text(encoding="utf-8")
    return [marker for marker in REQUIRED_API_MARKERS if marker not in text]


def main() -> int:
    envelope = build_search_endpoint_document_query_envelope(
        query=" robotics   policy ",
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
    validate_document_query_result_envelope(envelope)
    data = envelope["data"]
    query = data["query"]
    gaps = _api_marker_gaps()
    checks = {
        "contract_version": data["contract_version"],
        "consumer": query["consumer"],
        "project_key": query["project_key"],
        "state_filter": query["filters"][0] if query["filters"] else None,
        "result_count": data["pagination"]["result_count"],
        "result_source_type": data["results"][0]["source_type"] if data["results"] else None,
        "api_marker_gaps": gaps,
    }
    passed = (
        checks["contract_version"] == DOCUMENT_QUERY_CONTRACT_VERSION
        and checks["consumer"] == "api.search"
        and checks["project_key"] == "demo_proj"
        and checks["state_filter"] == {"field": "state", "op": "eq", "value": "CA"}
        and checks["result_count"] == 1
        and checks["result_source_type"] == "document"
        and not gaps
    )
    print(json.dumps({"status": "pass" if passed else "fail", "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
