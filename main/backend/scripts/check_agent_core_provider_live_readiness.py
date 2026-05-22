#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.agent_core.provider_readiness import (
    build_agent_core_provider_live_readiness_contract,
    validate_agent_core_provider_live_readiness_contract,
)


def build_contract_snapshot(*, enable_live_probes: bool = False) -> dict[str, Any]:
    return build_agent_core_provider_live_readiness_contract(enable_live_probes=enable_live_probes)


def validate_contract_snapshot(snapshot: dict[str, Any]) -> list[str]:
    return validate_agent_core_provider_live_readiness_contract(snapshot)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the AgentCore provider live-readiness boundary.")
    parser.add_argument("--json", action="store_true", help="Print the full readiness contract as JSON.")
    parser.add_argument("--write-report", type=Path, default=None, help="Write the readiness contract to a JSON file.")
    parser.add_argument(
        "--enable-live-probes",
        action="store_true",
        help="Reserve flag for future bounded live probes; current contract records the gap without external model calls.",
    )
    args = parser.parse_args(argv)

    snapshot = build_contract_snapshot(enable_live_probes=args.enable_live_probes)
    errors = validate_contract_snapshot(snapshot)
    status = "failed" if errors or snapshot.get("status") != "passed" else "ok"
    report_path = args.write_report
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
        selected = snapshot.get("configured_provider", {}).get("llm_provider")
        selected_live = next(
            (
                row.get("live_probe_status")
                for row in snapshot.get("live_availability", {}).get("providers", [])
                if isinstance(row, dict) and row.get("selected")
            ),
            "unknown",
        )
        print(
            "OK agent_core_provider_live_readiness=passed "
            f"readiness_state={snapshot.get('readiness_state')} "
            f"selected_provider={selected} "
            f"selected_live={selected_live} "
            f"local_fixtures={len(snapshot.get('local_fixture_readiness') or [])} "
            f"unsupported_claims={len(snapshot.get('unsupported_closure_claims') or [])}"
        )
    return 1 if status != "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
