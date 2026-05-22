#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.agent_core.tool_calling_quality import (
    build_agent_core_tool_calling_quality_contract,
    validate_agent_core_tool_calling_quality_contract,
)


def build_contract_snapshot() -> dict[str, Any]:
    return build_agent_core_tool_calling_quality_contract()


def validate_contract_snapshot(snapshot: dict[str, Any]) -> list[str]:
    return validate_agent_core_tool_calling_quality_contract(snapshot)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate deterministic AgentCore tool-calling quality.")
    parser.add_argument("--json", action="store_true", help="Print the full tool-calling quality contract as JSON.")
    parser.add_argument("--write-report", type=Path, default=None, help="Write the quality contract to a JSON file.")
    args = parser.parse_args(argv)

    snapshot = build_contract_snapshot()
    errors = validate_contract_snapshot(snapshot)
    status = "failed" if errors or snapshot.get("status") != "passed" else "ok"
    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(
            json.dumps(
                {
                    "status": status,
                    "errors": errors,
                    "contract": snapshot,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    elif errors:
        print(json.dumps({"status": status, "errors": errors}, ensure_ascii=False, sort_keys=True))
    else:
        gap = snapshot.get("external_provider_live_gap") if isinstance(snapshot.get("external_provider_live_gap"), dict) else {}
        print(
            "OK agent_core_tool_calling_quality=passed "
            f"deterministic_tool_calling_ready={str(snapshot.get('deterministic_tool_calling_ready')).lower()} "
            f"external_provider_live_gap={gap.get('state')} "
            f"providers={len(snapshot.get('provider_tool_call_contracts') or [])} "
            f"live_model_calls={(snapshot.get('quality_gate') or {}).get('live_model_calls')}"
        )
    return 1 if status != "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
