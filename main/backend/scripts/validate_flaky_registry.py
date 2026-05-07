#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_OWNER_KEYS = ("service_owner", "data_owner", "alert_owner")


def load_registry(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_entries(data: object) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("entries"), list):
            return [item for item in data["entries"] if isinstance(item, dict)]
        return [data]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    registry_path = Path(args.registry)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["## Flaky Registry Validation", ""]
    if not registry_path.exists():
        lines.extend(
            [
                "- status: missing-registry",
                f"- registry: `{registry_path}`",
            ]
        )
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    try:
        entries = iter_entries(load_registry(registry_path))
    except Exception as exc:
        lines.extend(
            [
                "- status: invalid-json",
                f"- error: `{exc}`",
            ]
        )
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    missing = []
    for index, entry in enumerate(entries):
        entry_name = entry.get("name") or entry.get("nodeid") or f"entry-{index}"
        absent = [key for key in REQUIRED_OWNER_KEYS if not entry.get(key)]
        if absent:
            missing.append((entry_name, absent))

    lines.append(f"- registry_entries: `{len(entries)}`")
    if missing:
        lines.append(f"- status: `fail` ({len(missing)} ownership gap(s))")
        lines.append("")
        lines.append("### Missing ownership")
        lines.extend([f"- `{name}`: missing {', '.join(keys)}" for name, keys in missing[:20]])
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    lines.append("- status: `pass`")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
