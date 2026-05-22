#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.agent_core.provider_trace import (
    build_agent_core_provider_trace_readback_contract,
    validate_agent_core_provider_trace_readback_contract,
)


def build_contract_snapshot() -> dict[str, Any]:
    return build_agent_core_provider_trace_readback_contract()


def validate_contract_snapshot(snapshot: dict[str, Any]) -> list[str]:
    return validate_agent_core_provider_trace_readback_contract(snapshot)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate deterministic AgentCore provider trace readback.")
    parser.add_argument("--json", action="store_true", help="Print the full provider trace contract as JSON.")
    parser.add_argument("--write-report", type=Path, default=None, help="Write the provider trace contract to a JSON file.")
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
        trace = snapshot.get("provider_trace") if isinstance(snapshot.get("provider_trace"), dict) else {}
        envelope = snapshot.get("status_data_error_meta_compatibility") if isinstance(snapshot.get("status_data_error_meta_compatibility"), dict) else {}
        print(
            "OK agent_core_provider_trace_readback=passed "
            f"provider={trace.get('provider_key')} "
            f"provider_calls={trace.get('call_count')} "
            f"status_data_error_meta={str(envelope.get('compatible')).lower()} "
            f"real_external_provider_call_open={str(snapshot.get('real_external_provider_call_open')).lower()} "
            f"external_model_calls={snapshot.get('external_model_calls')}"
        )
    return 1 if status != "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
