#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.workflow_graph.observability import query_top_failure_reasons


REQUIRED_WORKFLOW_KEYS = {
    "contract_version",
    "taxonomy_version",
    "items",
    "total_reasons",
    "handoff_metrics",
    "backend_marker",
    "generated_at",
}


def _validate_items(items: object) -> None:
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("items entry must be an object")
        if not str(item.get("reason_code") or "").strip():
            raise ValueError("reason_code is required")


def main() -> int:
    workflow_payload = query_top_failure_reasons(limit=20)

    missing_workflow = sorted(REQUIRED_WORKFLOW_KEYS - set(workflow_payload.keys()))
    if missing_workflow:
        raise ValueError(f"workflow metrics missing keys: {missing_workflow}")

    _validate_items(workflow_payload.get("items"))

    print(
        json.dumps(
            {
                "status": "ok",
                "workflow_contract": workflow_payload.get("contract_version"),
                "workflow_reason_count": workflow_payload.get("total_reasons"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
