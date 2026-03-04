#!/usr/bin/env python3
"""ST06: rollback scheduler strategy from time-window density within 72h window."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_STRATEGY = "legacy"
TARGET_STRATEGY = "time_window_density"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid JSON object: {path}")
    return payload


def _to_dt(text: str | None) -> datetime | None:
    if not text:
        return None
    raw = text.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Rollback scheduler default strategy to previous value")
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
    parser.add_argument("--force", action="store_true", help="Allow rollback after deadline")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    state_path = Path(args.rollout_state).resolve()

    if not config_path.exists() or not state_path.exists():
        raise SystemExit("Config/state file is missing, cannot rollback")

    config = _load_json(config_path)
    state = _load_json(state_path)

    previous = str(state.get("previous_strategy") or DEFAULT_STRATEGY)
    current = str(config.get("scheduler_strategy") or DEFAULT_STRATEGY)
    deadline = _to_dt(str(state.get("rollback_deadline") or ""))
    now = datetime.now(timezone.utc)

    in_window = bool(deadline and now <= deadline)
    if not in_window and not args.force:
        raise SystemExit(
            f"Rollback window expired at {state.get('rollback_deadline')}, use --force to override"
        )

    if current != TARGET_STRATEGY:
        raise SystemExit(f"Current strategy is {current!r}, expected {TARGET_STRATEGY!r} before rollback")

    new_config = dict(config)
    new_config["scheduler_strategy"] = previous
    new_config["st06_last_rollback_at"] = now.isoformat()

    new_state = dict(state)
    new_state["status"] = "rollback_done"
    new_state["rolled_back_at"] = now.isoformat()
    new_state["rolled_back_by"] = args.operator
    new_state["window_check"] = "in_window" if in_window else "force_override"
    new_state["current_strategy"] = previous

    if not args.dry_run:
        config_path.write_text(json.dumps(new_config, ensure_ascii=False, indent=2), encoding="utf-8")
        state_path.write_text(json.dumps(new_state, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "mode": "dry_run" if args.dry_run else "apply",
                "config_path": str(config_path),
                "rollout_state_path": str(state_path),
                "rolled_back_to": previous,
                "window_check": new_state["window_check"],
                "rolled_back_at": new_state["rolled_back_at"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
