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
    build_document_query,
    build_document_query_result_envelope,
    rows_for_document_views,
    validate_document_query_result_envelope,
)
from app.services.document_views import build_keyword_card_from_hybrid_row  # noqa: E402


def main() -> int:
    query = build_document_query(
        "robotics policy",
        consumer="checker.document_queries",
        sources=("document",),
        filters=({"field": "state", "op": "eq", "value": "CA"},),
        sort=({"field": "relevance", "direction": "desc"},),
        limit=3,
    )
    envelope = build_document_query_result_envelope(
        query,
        [
            {
                "id": "doc-1",
                "document_id": 1,
                "title": "Robotics policy note",
                "summary": "Evidence for robotics policy pilots.",
                "url": "https://example.org/robotics-policy",
                "score": 0.82,
                "backend": "deterministic_fixture",
            }
        ],
        source="deterministic_fixture",
        result_source_type="document",
    )
    validate_document_query_result_envelope(envelope)
    rows = rows_for_document_views(envelope)
    card = build_keyword_card_from_hybrid_row(rows[0], normalized_query=query.normalized_query)
    checks = {
        "contract_version": envelope["data"]["contract_version"],
        "query_id": envelope["data"]["query"]["query_id"],
        "result_count": envelope["data"]["pagination"]["result_count"],
        "view_card_source_type": card.source_type,
        "view_card_backend": card.extra.get("backend"),
    }
    passed = (
        checks["contract_version"] == DOCUMENT_QUERY_CONTRACT_VERSION
        and checks["result_count"] == 1
        and checks["view_card_source_type"] == "document"
        and checks["view_card_backend"] == "deterministic_fixture"
    )
    print(json.dumps({"status": "pass" if passed else "fail", "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
