#!/usr/bin/env python3
"""Validate backend Alembic migration graph without requiring a live database."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Annotated, Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VERSIONS_DIR = REPO_ROOT / "main" / "backend" / "migrations" / "versions"


def _literal_assignment(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        try:
            return ast.literal_eval(node.value)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"{name} must be a literal") from exc
    return None


def _normalize_down_revision(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _read_revision(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    revision = _literal_assignment(tree, "revision")
    if not revision:
        raise ValueError("missing revision")
    down_revision = _normalize_down_revision(_literal_assignment(tree, "down_revision"))
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "revision": str(revision),
        "down_revision": down_revision,
        "text": text,
    }


def _walk_ancestors(revision: str, parent_map: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    stack = [revision]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(parent_map.get(current, []))
    return seen


def build_report(versions_dir: Path, *, required_tables: list[str]) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=preflight "
    "fact_source=alembic_migration_source_files "
    "witness=test:test_w11_non_authoritative_metadata",
]:
    problems: list[str] = []
    records: list[dict[str, Any]] = []
    for path in sorted(versions_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        try:
            records.append(_read_revision(path))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{path.relative_to(REPO_ROOT)}: {exc}")

    revisions = [record["revision"] for record in records]
    revision_counts = Counter(revisions)
    duplicates = sorted(revision for revision, count in revision_counts.items() if count > 1)
    for revision in duplicates:
        problems.append(f"duplicate revision: {revision}")

    known = set(revisions)
    parent_map = {record["revision"]: list(record["down_revision"]) for record in records}
    child_map: dict[str, list[str]] = defaultdict(list)
    roots: list[str] = []
    for record in records:
        parents = list(record["down_revision"])
        if not parents:
            roots.append(record["revision"])
        for parent in parents:
            if parent not in known:
                problems.append(f"{record['revision']} references missing down_revision {parent}")
            child_map[parent].append(record["revision"])

    heads = sorted(revision for revision in known if not child_map.get(revision))

    for record in records:
        ancestors = _walk_ancestors(record["revision"], parent_map)
        if any(parent == record["revision"] for parent in parent_map.get(record["revision"], [])):
            problems.append(f"{record['revision']} references itself as down_revision")
        if len(ancestors) != len(set(ancestors)):
            problems.append(f"{record['revision']} has duplicate ancestors")

    table_hits: dict[str, list[str]] = {}
    for table in required_tables:
        hits = [record["path"] for record in records if table in record["text"]]
        table_hits[table] = hits
        if not hits:
            problems.append(f"required table not mentioned by any migration: {table}")

    return {
        "status": "passed" if not problems else "failed",
        "versions_dir": str(versions_dir.relative_to(REPO_ROOT)),
        "revision_count": len(records),
        "roots": sorted(roots),
        "heads": heads,
        "duplicate_revisions": duplicates,
        "required_table_hits": table_hits,
        "latest_head": heads[0] if len(heads) == 1 else None,
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions-dir", type=Path, default=DEFAULT_VERSIONS_DIR)
    parser.add_argument("--expect-single-head", action="store_true")
    parser.add_argument("--expect-head", default="")
    parser.add_argument("--require-table", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(args.versions_dir, required_tables=list(args.require_table or []))
    problems = list(report["problems"])
    heads = list(report["heads"])
    if args.expect_single_head and len(heads) != 1:
        problems.append(f"expected one migration head, found {len(heads)}: {heads}")
    if args.expect_head and args.expect_head not in heads:
        problems.append(f"expected head {args.expect_head}, found {heads}")
    report["problems"] = problems
    report["status"] = "passed" if not problems else "failed"

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    elif problems:
        for problem in problems:
            print(f"FAIL backend_migration_graph: {problem}", file=sys.stderr)
    else:
        print(
            "OK backend_migration_graph=passed "
            f"revisions={report['revision_count']} heads={','.join(heads)}"
        )
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
