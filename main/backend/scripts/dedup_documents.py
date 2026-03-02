#!/usr/bin/env python3
"""
Document dedup tool (safe two-step):

1) Dry-run:
   python scripts/dedup_documents.py --project demo_proj

2) Apply:
   python scripts/dedup_documents.py --project demo_proj --apply
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from sqlalchemy import text

project_root = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(project_root))

from app.models.base import engine


def _schema_from_project(project_key: str) -> str:
    key = str(project_key or "").strip()
    if not key:
        raise ValueError("project key is required")
    if key.startswith("project_"):
        return key
    return f"project_{key}"


def _normalize_title(title: str) -> str:
    return " ".join(str(title or "").strip().lower().split())


def _canonical_uri(uri: str) -> str:
    raw = str(uri or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    host = str(parsed.netloc or "").strip().lower()
    if not host:
        return ""
    scheme = str(parsed.scheme or "https").strip().lower()
    path = unquote(str(parsed.path or "")).rstrip("/")
    return f"{scheme}://{host}{path}"


def _dedup_plan_for_schema(schema: str) -> dict[str, Any]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT id, title, uri, created_at
                FROM "{schema}".documents
                ORDER BY created_at DESC, id DESC
                """
            )
        ).fetchall()

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        row_id = int(row[0])
        title = str(row[1] or "")
        uri = str(row[2] or "")
        created_at = str(row[3]) if row[3] is not None else None
        title_norm = _normalize_title(title)
        canonical = _canonical_uri(uri)
        if not title_norm or not canonical:
            continue
        groups[(title_norm, canonical)].append(
            {
                "id": row_id,
                "title": title,
                "uri": uri,
                "created_at": created_at,
            }
        )

    duplicate_groups: list[dict[str, Any]] = []
    delete_ids: list[int] = []
    for (title_norm, canonical), items in groups.items():
        if len(items) <= 1:
            continue
        keep = items[0]
        to_delete = items[1:]
        delete_ids.extend([int(x["id"]) for x in to_delete])
        duplicate_groups.append(
            {
                "title_norm": title_norm[:180],
                "canonical_uri": canonical,
                "keep_id": int(keep["id"]),
                "delete_ids": [int(x["id"]) for x in to_delete],
            }
        )

    return {
        "schema": schema,
        "total_docs": len(rows),
        "duplicate_group_count": len(duplicate_groups),
        "delete_count": len(delete_ids),
        "delete_ids": sorted(set(delete_ids)),
        "duplicate_groups": duplicate_groups,
    }


def _apply_delete(schema: str, delete_ids: list[int]) -> int:
    if not delete_ids:
        return 0
    with engine.begin() as conn:
        conn.execute(
            text(f'DELETE FROM "{schema}".documents WHERE id = ANY(:ids)'),
            {"ids": delete_ids},
        )
    return len(delete_ids)


def run(project_key: str, *, apply: bool, sample_limit: int) -> int:
    schema = _schema_from_project(project_key)
    plan = _dedup_plan_for_schema(schema)

    print(f"[dedup] project={project_key} schema={schema}")
    print(
        f"[dedup] total_docs={plan['total_docs']} duplicate_groups={plan['duplicate_group_count']} "
        f"delete_count={plan['delete_count']}"
    )
    if plan["duplicate_group_count"] > 0:
        print(f"[dedup] sample_top_{sample_limit}:")
        for g in plan["duplicate_groups"][: max(1, int(sample_limit))]:
            print(
                f"  keep_id={g['keep_id']} delete_ids={g['delete_ids']} "
                f"title_norm={g['title_norm']!r} canonical_uri={g['canonical_uri']!r}"
            )

    if not apply:
        print("[dedup] dry-run mode, no rows deleted")
        return int(plan["delete_count"])

    deleted = _apply_delete(schema, list(plan["delete_ids"]))
    print(f"[dedup] apply deleted={deleted}")
    return int(deleted)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deduplicate documents by title + canonical URI")
    parser.add_argument("--project", default="demo_proj", help="Project key, e.g. demo_proj/default")
    parser.add_argument("--apply", action="store_true", help="Actually delete duplicate rows")
    parser.add_argument("--sample-limit", type=int, default=10, help="Dry-run sample group count")
    parser.add_argument("--json", action="store_true", help="Output final summary as JSON")
    args = parser.parse_args()

    deleted_or_planned = run(
        str(args.project),
        apply=bool(args.apply),
        sample_limit=max(1, int(args.sample_limit)),
    )
    if bool(args.json):
        print(json.dumps({"project": str(args.project), "count": int(deleted_or_planned), "apply": bool(args.apply)}))


if __name__ == "__main__":
    main()

