#!/usr/bin/env python3
"""ST06: cut over scheduler strategy to time-window density (with 72h rollback window)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TARGET_STRATEGY = "time_window_density"
DEFAULT_STRATEGY = "legacy"
ROLLBACK_WINDOW_HOURS = 72


def _load_json(path: Path, default_obj: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default_obj)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid JSON object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Switch scheduler default strategy to time_window_density")
    parser.add_argument(
        "--config",
        default="main/backend/scripts/artifacts/st06_scheduler_runtime_config.json",
        help="Runtime scheduler config JSON",
    )
    parser.add_argument(
        "--rollout-state",
        default="main/backend/scripts/artifacts/st06_scheduler_rollout_state.json",
        help="Rollout state JSON",
    )
    parser.add_argument("--operator", default="st06")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    state_path = Path(args.rollout_state).resolve()

    config = _load_json(config_path, {"scheduler_strategy": DEFAULT_STRATEGY})
    previous = str(config.get("scheduler_strategy") or DEFAULT_STRATEGY)

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=ROLLBACK_WINDOW_HOURS)
    new_config = dict(config)
    new_config["scheduler_strategy"] = TARGET_STRATEGY
    new_config["st06_last_cutover_at"] = now.isoformat()

    state = {
        "status": "cutover_done",
        "operator": args.operator,
        "previous_strategy": previous,
        "current_strategy": TARGET_STRATEGY,
        "cutover_at": now.isoformat(),
        "rollback_deadline": deadline.isoformat(),
        "rollback_window_hours": ROLLBACK_WINDOW_HOURS,
    }

    if not args.dry_run:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(new_config, ensure_ascii=False, indent=2), encoding="utf-8")
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "mode": "dry_run" if args.dry_run else "apply",
                "config_path": str(config_path),
                "rollout_state_path": str(state_path),
                "previous_strategy": previous,
                "current_strategy": TARGET_STRATEGY,
                "cutover_at": state["cutover_at"],
                "rollback_deadline": state["rollback_deadline"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
