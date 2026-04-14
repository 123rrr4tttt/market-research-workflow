#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_items(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return [x for x in data["items"] if isinstance(x, dict)]
        if isinstance(payload.get("items"), list):
            return [x for x in payload["items"] if isinstance(x, dict)]
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    raise ValueError(f"unsupported snapshot format: {path}")


def _key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("source_domain") or ""),
            str(row.get("prompt_group_id") or ""),
            str(row.get("bucket_time") or ""),
        ]
    )


def _f(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare API snapshot and UI snapshot for prompt-time-density.")
    parser.add_argument("--api", required=True, help="Path to API snapshot JSON.")
    parser.add_argument("--ui", required=True, help="Path to UI snapshot JSON.")
    parser.add_argument("--tolerance", type=float, default=1e-6, help="Allowed numeric diff tolerance.")
    parser.add_argument("--output", default=".artifacts/prompt_time_density_diff_report.md")
    args = parser.parse_args()

    api_items = _load_items(Path(args.api))
    ui_items = _load_items(Path(args.ui))

    api_map = {_key(x): x for x in api_items}
    ui_map = {_key(x): x for x in ui_items}
    keys = sorted(set(api_map) | set(ui_map))

    missing_in_ui: list[str] = []
    missing_in_api: list[str] = []
    metric_diffs: list[dict[str, Any]] = []
    metrics = ["density", "norm_density", "dup_ratio", "effective_new_docs"]

    for k in keys:
        a = api_map.get(k)
        u = ui_map.get(k)
        if a is None:
            missing_in_api.append(k)
            continue
        if u is None:
            missing_in_ui.append(k)
            continue
        for m in metrics:
            d = abs(_f(a.get(m)) - _f(u.get(m)))
            if d > args.tolerance:
                metric_diffs.append(
                    {
                        "key": k,
                        "metric": m,
                        "api_value": a.get(m),
                        "ui_value": u.get(m),
                        "abs_diff": d,
                    }
                )

    status = "PASS" if not missing_in_ui and not missing_in_api and not metric_diffs else "FAIL"
    lines: list[str] = []
    lines.append("# Prompt-Time-Density API/UI Reconciliation Report")
    lines.append("")
    lines.append(f"- status: `{status}`")
    lines.append(f"- total_api_items: `{len(api_items)}`")
    lines.append(f"- total_ui_items: `{len(ui_items)}`")
    lines.append(f"- tolerance: `{args.tolerance}`")
    lines.append(f"- missing_in_ui: `{len(missing_in_ui)}`")
    lines.append(f"- missing_in_api: `{len(missing_in_api)}`")
    lines.append(f"- metric_diffs: `{len(metric_diffs)}`")
    lines.append("")

    if missing_in_ui:
        lines.append("## Missing In UI")
        lines.extend([f"- `{x}`" for x in missing_in_ui[:50]])
        lines.append("")
    if missing_in_api:
        lines.append("## Missing In API")
        lines.extend([f"- `{x}`" for x in missing_in_api[:50]])
        lines.append("")
    if metric_diffs:
        lines.append("## Metric Diffs")
        for row in metric_diffs[:100]:
            lines.append(
                f"- `{row['key']}` `{row['metric']}` api={row['api_value']} ui={row['ui_value']} abs_diff={row['abs_diff']}"
            )
        lines.append("")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": status, "output": str(out_path), "metric_diffs": len(metric_diffs)}))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

