#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.agent_core.external_provider_live_readback import (
    build_agent_core_external_provider_live_readback_evidence,
    validate_agent_core_external_provider_live_readback_evidence,
)


def build_contract_snapshot(
    *,
    allow_external_network: bool = False,
    timeout_ms: int = 20_000,
    model: str | None = None,
) -> dict[str, Any]:
    return build_agent_core_external_provider_live_readback_evidence(
        allow_external_network=allow_external_network,
        timeout_ms=timeout_ms,
        model=model,
    )


def validate_contract_snapshot(snapshot: dict[str, Any]) -> list[str]:
    return validate_agent_core_external_provider_live_readback_evidence(snapshot)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the selected AgentCore external provider live readback gate.")
    parser.add_argument("--json", action="store_true", help="Print the full live readback evidence as JSON.")
    parser.add_argument("--write-report", type=Path, default=None, help="Write the live readback evidence to a JSON file.")
    parser.add_argument(
        "--allow-external-network",
        action="store_true",
        help="Allow a bounded real selected-provider call. Without this flag, the gate records a blocked evidence state.",
    )
    parser.add_argument("--require-closed", action="store_true", help="Return non-zero unless the selected provider live gate closes.")
    parser.add_argument("--timeout-ms", type=int, default=20_000, help="Total timeout budget recorded for the live probe.")
    parser.add_argument("--model", default=None, help="Optional model override for the selected provider.")
    args = parser.parse_args(argv)

    snapshot = build_contract_snapshot(
        allow_external_network=args.allow_external_network,
        timeout_ms=args.timeout_ms,
        model=args.model,
    )
    errors = validate_contract_snapshot(snapshot)
    closed = snapshot.get("closed") is True
    status = "failed" if errors or (args.require_closed and not closed) else "ok"
    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(
            json.dumps(
                {
                    "status": status,
                    "errors": errors,
                    "closed": closed,
                    "contract": snapshot,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    elif errors or (args.require_closed and not closed):
        print(
            json.dumps(
                {
                    "status": status,
                    "errors": errors,
                    "closed": closed,
                    "remaining_blockers": snapshot.get("remaining_blockers") or [],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    else:
        print(
            "OK agent_core_external_provider_live_readback=validated "
            f"closed={str(closed).lower()} "
            f"provider={snapshot.get('provider')} "
            f"model={snapshot.get('model_id')} "
            f"external_model_calls={snapshot.get('external_model_calls')} "
            f"latency_status={snapshot.get('latency_status')} "
            f"remaining_blockers={len(snapshot.get('remaining_blockers') or [])}"
        )
    return 1 if status != "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
