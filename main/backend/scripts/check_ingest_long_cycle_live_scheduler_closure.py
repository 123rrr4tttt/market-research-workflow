#!/usr/bin/env python3
"""Wave55 live closure gate for ingest long-cycle scheduler/queue/worker readback."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ingest.long_cycle_live_runtime import run_long_cycle_live_scheduler_closure_probe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute and validate a bounded live long-cycle scheduler closure run"
    )
    parser.add_argument("--project-key", default="demo_proj")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    payload = run_long_cycle_live_scheduler_closure_probe(project_key=args.project_key)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.format == "text":
        print(f"status={payload['status']}")
        print(f"contract_version={payload['contract_version']}")
        print(f"closure_claim={str(payload['closure_claim']).lower()}")
        print(f"readiness_state={payload['readiness_state']}")
        print(f"failures={','.join(payload['failures']) if payload['failures'] else '-'}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
