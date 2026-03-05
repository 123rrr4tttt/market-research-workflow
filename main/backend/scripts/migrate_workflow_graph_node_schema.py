#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_io_item(item: Any, *, for_input: bool) -> dict[str, Any]:
    row = _as_dict(item)
    out: dict[str, Any] = {
        "name": str(row.get("name") or row.get("key") or "").strip(),
        "value_type": str(row.get("value_type") or row.get("type") or "string"),
    }
    if for_input:
        out["source"] = str(row.get("source") or "input")
        if row.get("from_node"):
            out["from_node"] = row.get("from_node")
        if row.get("from_key"):
            out["from_key"] = row.get("from_key")
        if row.get("expr"):
            out["expr"] = row.get("expr")
    if "required" in row:
        out["required"] = bool(row.get("required"))
    if row.get("default_value") not in (None, ""):
        out["default_value"] = row.get("default_value")
    return out


def migrate_dsl(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    nodes = _as_list(out.get("nodes"))
    migrated_nodes: list[dict[str, Any]] = []
    for item in nodes:
        node = _as_dict(item)
        node_out = dict(node)
        config = _as_dict(node_out.get("config"))

        old_inputs = _as_list(config.get("inputs"))
        old_outputs = _as_list(config.get("outputs"))
        new_inputs = _as_list(config.get("input_vars")) or old_inputs
        new_outputs = _as_list(config.get("output_vars")) or old_outputs

        if new_inputs:
            config["input_vars"] = [_normalize_io_item(x, for_input=True) for x in new_inputs]
        if new_outputs:
            config["output_vars"] = [_normalize_io_item(x, for_input=False) for x in new_outputs]

        config.pop("inputs", None)
        config.pop("outputs", None)
        node_out["config"] = config
        migrated_nodes.append(node_out)
    out["nodes"] = migrated_nodes
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate workflow graph DSL node config to v2 IO schema.")
    parser.add_argument("--input", required=True, help="input JSON file path")
    parser.add_argument("--output", required=False, help="output JSON file path")
    parser.add_argument("--dry-run", action="store_true", help="print migration summary only")
    args = parser.parse_args()

    input_path = Path(args.input)
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    migrated = migrate_dsl(_as_dict(raw))

    if args.dry_run:
        print(json.dumps({"input": str(input_path), "nodes": len(_as_list(migrated.get("nodes"))), "dry_run": True}, ensure_ascii=False))
        return 0

    output_path = Path(args.output) if args.output else input_path.with_suffix(".migrated.json")
    output_path.write_text(json.dumps(migrated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"input": str(input_path), "output": str(output_path), "nodes": len(_as_list(migrated.get("nodes")))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
