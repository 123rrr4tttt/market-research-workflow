#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.models.base import SessionLocal  # noqa: E402
from app.models.entities import CrawlerProject  # noqa: E402
from app.services.crawlers_mgmt import register_or_update_source_library_scrapy_binding  # noqa: E402
from app.services.projects import bind_schema  # noqa: E402


@dataclass
class BindingPlan:
    crawler_project_id: int
    crawler_project_key: str
    scrapy_project: str
    spider: str
    channel_key: str
    item_key: str
    channel_name: str
    item_name: str
    description: str | None
    enabled: bool
    arguments: dict[str, Any]
    settings: dict[str, Any]
    item_params_patch: dict[str, Any]
    channel_extra_patch: dict[str, Any]
    item_extra_patch: dict[str, Any]


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalize_key(value: str | None, *, fallback: str) -> str:
    raw = str(value or "").strip()
    return raw or fallback


def _build_binding_plan(
    row: CrawlerProject,
    *,
    default_spider: str,
) -> BindingPlan:
    payload = _as_dict(row.import_payload)
    manifest = _as_dict(payload.get("manifest"))
    metadata = _as_dict(payload.get("metadata"))

    scrapy_project = _normalize_key(
        payload.get("scrapy_project") or manifest.get("scrapy_project"),
        fallback=row.project_key,
    )
    spider = _normalize_key(
        payload.get("spider") or manifest.get("spider"),
        fallback=default_spider,
    )
    channel_key = _normalize_key(payload.get("channel_key"), fallback=f"crawler.{row.project_key}")
    item_key = _normalize_key(payload.get("item_key"), fallback=f"crawler.{row.project_key}.default")
    channel_name = _normalize_key(payload.get("channel_name"), fallback=f"Crawler {row.name}")
    item_name = _normalize_key(payload.get("item_name"), fallback=f"{row.name} default")

    enabled_raw = payload.get("enable_now")
    enabled = bool(enabled_raw) if enabled_raw is not None else True
    description = row.description or payload.get("description")

    arguments = _as_dict(payload.get("arguments")) or _as_dict(manifest.get("arguments"))
    settings = _as_dict(payload.get("settings")) or _as_dict(manifest.get("settings"))

    item_params_patch = {
        "crawler_project_key": row.project_key,
        "crawler_project_id": int(row.id),
    }
    if row.current_version:
        item_params_patch["crawler_version"] = row.current_version

    channel_extra_patch = {
        "crawler_project_key": row.project_key,
        "crawler_project_id": int(row.id),
    }
    if row.source_uri:
        channel_extra_patch["source_uri"] = row.source_uri

    item_extra_patch = {
        "crawler_project_key": row.project_key,
        "crawler_project_id": int(row.id),
        "crawler_provider": row.provider,
    }
    if metadata:
        item_extra_patch["crawler_metadata"] = metadata

    return BindingPlan(
        crawler_project_id=int(row.id),
        crawler_project_key=row.project_key,
        scrapy_project=scrapy_project,
        spider=spider,
        channel_key=channel_key,
        item_key=item_key,
        channel_name=channel_name,
        item_name=item_name,
        description=description,
        enabled=enabled,
        arguments=arguments,
        settings=settings,
        item_params_patch=item_params_patch,
        channel_extra_patch=channel_extra_patch,
        item_extra_patch=item_extra_patch,
    )


def _load_crawler_projects(
    *,
    only_keys: set[str],
) -> list[CrawlerProject]:
    with bind_schema("public"):
        with SessionLocal() as session:
            rows = session.execute(select(CrawlerProject).order_by(CrawlerProject.id.asc())).scalars().all()
    if not only_keys:
        return rows
    return [row for row in rows if row.project_key in only_keys]


def run_backfill(
    *,
    target_project_key: str,
    default_spider: str,
    dry_run: bool,
    only_keys: set[str],
) -> dict[str, Any]:
    rows = _load_crawler_projects(only_keys=only_keys)
    summary: dict[str, Any] = {
        "target_project_key": target_project_key,
        "total_projects": len(rows),
        "processed": 0,
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "details": [],
    }

    for row in rows:
        provider = str(row.provider or "").strip().lower()
        if provider not in {"scrapy", "scrapyd"}:
            summary["skipped"] += 1
            summary["details"].append(
                {
                    "crawler_project_key": row.project_key,
                    "status": "skipped",
                    "reason": f"unsupported provider: {row.provider}",
                }
            )
            continue

        plan = _build_binding_plan(row, default_spider=default_spider)
        summary["processed"] += 1

        if dry_run:
            summary["success"] += 1
            summary["details"].append(
                {
                    "crawler_project_key": row.project_key,
                    "status": "dry_run",
                    "binding": asdict(plan),
                }
            )
            continue

        try:
            result = register_or_update_source_library_scrapy_binding(
                project_key=target_project_key,
                channel_key=plan.channel_key,
                item_key=plan.item_key,
                spider=plan.spider,
                scrapy_project=plan.scrapy_project,
                channel_name=plan.channel_name,
                item_name=plan.item_name,
                description=plan.description,
                arguments=plan.arguments,
                settings=plan.settings,
                item_params_patch=plan.item_params_patch,
                channel_extra_patch=plan.channel_extra_patch,
                item_extra_patch=plan.item_extra_patch,
                enabled=plan.enabled,
            )
            summary["success"] += 1
            summary["details"].append(
                {
                    "crawler_project_key": row.project_key,
                    "status": "ok",
                    "binding": {
                        "channel_key": plan.channel_key,
                        "item_key": plan.item_key,
                        "scrapy_project": plan.scrapy_project,
                        "spider": plan.spider,
                    },
                    "result": result,
                }
            )
        except Exception as exc:  # noqa: BLE001
            summary["failed"] += 1
            summary["details"].append(
                {
                    "crawler_project_key": row.project_key,
                    "status": "failed",
                    "error": str(exc),
                    "binding": {
                        "channel_key": plan.channel_key,
                        "item_key": plan.item_key,
                        "scrapy_project": plan.scrapy_project,
                        "spider": plan.spider,
                    },
                }
            )

    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill crawler projects into source_library scrapy bindings."
    )
    parser.add_argument(
        "--target-project-key",
        default=os.environ.get("TARGET_PROJECT_KEY", "demo_proj"),
        help="Target project_key where source_library bindings will be written. Default: demo_proj",
    )
    parser.add_argument(
        "--default-spider",
        default=os.environ.get("DEFAULT_SPIDER", "default"),
        help="Fallback spider when crawler import payload has no spider field. Default: default",
    )
    parser.add_argument(
        "--only-project-key",
        action="append",
        default=[],
        help="Optional filter; repeat to include multiple crawler project keys.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview binding plans without writing to DB.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    target_project_key = str(args.target_project_key or "").strip()
    default_spider = str(args.default_spider or "").strip()
    only_keys = {str(x).strip() for x in (args.only_project_key or []) if str(x).strip()}
    if not target_project_key:
        raise ValueError("target project key is required")
    if not default_spider:
        raise ValueError("default spider is required")

    summary = run_backfill(
        target_project_key=target_project_key,
        default_spider=default_spider,
        dry_run=bool(args.dry_run),
        only_keys=only_keys,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
