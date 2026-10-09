from __future__ import annotations

import ast
import json
import time
from typing import TypeGuard
from urllib.parse import urljoin

import httpx

from ..ingest.raw_import import run_raw_import_materials
from ..projects.context import bind_project
from .base import CrawlerJsonObject, CrawlerJsonValue
from .providers.scrapy import finished_job_status
from .scrapyd_client import ScrapydClient
from .scrapyd_runtime import ensure_scrapyd_ready


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _json_value(value: object) -> CrawlerJsonValue:
    if _is_object_dict(value):
        return {str(key): _json_value(item) for key, item in value.items()}
    if _is_object_list(value):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _json_object(value: object) -> CrawlerJsonObject:
    normalized = _json_value(value)
    return normalized if isinstance(normalized, dict) else {}


def _job_rows(value: CrawlerJsonValue) -> list[CrawlerJsonObject]:
    if not isinstance(value, list):
        return []
    return [_json_object(item) for item in value if isinstance(item, dict)]


def _absolute_url(base_url: str, maybe_relative: str | None) -> str | None:
    raw = str(maybe_relative or "").strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://")):
        return raw
    return urljoin(base_url.rstrip("/") + "/", raw.lstrip("/"))


def _find_job_entry(
    listjobs: CrawlerJsonObject,
    job_id: str,
) -> tuple[str | None, CrawlerJsonObject | None]:
    for bucket in ("pending", "running", "finished"):
        for row in _job_rows(listjobs.get(bucket)):
            if str(row.get("id") or "").strip() == job_id:
                return bucket, row
    return None, None


def _parse_jsonl_items(text: str) -> list[CrawlerJsonObject]:
    out: list[CrawlerJsonObject] = []
    for line in str(text or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            value: CrawlerJsonValue = json.loads(raw)
        except Exception:
            continue
        if isinstance(value, dict):
            out.append(_json_object(value))
    return out


def _parse_log_items(text: str) -> list[CrawlerJsonObject]:
    out: list[CrawlerJsonObject] = []
    lines = str(text or "").splitlines()
    for idx, line in enumerate(lines):
        if "Scraped from" not in line:
            continue
        if idx + 1 >= len(lines):
            continue
        payload = lines[idx + 1].strip()
        if not (payload.startswith("{") and payload.endswith("}")):
            continue
        try:
            value: CrawlerJsonValue = ast.literal_eval(payload)
        except Exception:
            continue
        if isinstance(value, dict):
            out.append(_json_object(value))
    return out


def _normalize_raw_items_to_import_items(
    raw_items: list[CrawlerJsonObject],
    *,
    material_type: str,
) -> list[CrawlerJsonObject]:
    out: list[CrawlerJsonObject] = []
    for row in raw_items:
        text = ""
        for key in ("text", "content", "body", "summary", "snippet", "description"):
            value = str(row.get(key) or "").strip()
            if value:
                text = value
                break
        title = str(row.get("title") or row.get("name") or "").strip() or None
        uri = str(row.get("url") or row.get("uri") or "").strip() or None
        out.append(
            {
                "text": text,
                "title": title,
                "uri": uri,
                "material_type": material_type,
            }
        )
    return out


def ingest_scrapyd_job_output(
    *,
    project_key: str,
    scrapy_project: str,
    job_id: str,
    base_url: str | None = None,
    wait_timeout_seconds: float = 8.0,
    poll_interval_seconds: float = 0.8,
    source_name: str | None = None,
    material_type: str = "news",
    enable_extraction: bool = False,
    max_items: int = 100,
) -> CrawlerJsonObject:
    if not project_key:
        return {"status": "skipped", "reason": "missing_project_key"}
    if not scrapy_project:
        return {"status": "skipped", "reason": "missing_scrapy_project"}
    if not job_id:
        return {"status": "skipped", "reason": "missing_job_id"}

    resolved_base_url = ensure_scrapyd_ready(base_url=base_url)
    client = ScrapydClient(base_url=resolved_base_url)

    deadline = time.time() + max(1.0, float(wait_timeout_seconds))
    state: str | None = None
    job_entry: CrawlerJsonObject | None = None
    last_listjobs: CrawlerJsonObject = {}
    while time.time() <= deadline:
        last_listjobs = _json_object(client.list_jobs(project=scrapy_project))
        state, job_entry = _find_job_entry(last_listjobs, job_id)
        if state == "finished":
            break
        if state is None:
            time.sleep(max(0.1, float(poll_interval_seconds)))
            continue
        if state in {"pending", "running"}:
            time.sleep(max(0.1, float(poll_interval_seconds)))
            continue
        break

    if state != "finished" or not job_entry:
        return {
            "status": "pending",
            "state": state,
            "job_id": job_id,
            "scrapy_project": scrapy_project,
            "raw": {"listjobs": last_listjobs},
        }

    terminal_status = finished_job_status(job_entry)
    if terminal_status != "completed":
        return {
            "status": f"finished_{terminal_status}",
            "state": state,
            "job_id": job_id,
            "scrapy_project": scrapy_project,
            "raw_item_count": 0,
        }

    log_url = _absolute_url(resolved_base_url, str(job_entry.get("log_url") or ""))
    items_url = _absolute_url(resolved_base_url, str(job_entry.get("items_url") or ""))
    fetched_from = None
    raw_items: list[CrawlerJsonObject] = []
    with httpx.Client(timeout=15.0) as http:
        if items_url:
            try:
                response = http.get(items_url)
                response.raise_for_status()
                raw_items = _parse_jsonl_items(response.text)
                fetched_from = "items_url"
            except Exception:
                raw_items = []
        if not raw_items and log_url:
            try:
                response = http.get(log_url)
                response.raise_for_status()
                raw_items = _parse_log_items(response.text)
                fetched_from = "log_url"
            except Exception:
                raw_items = []

    if max_items > 0:
        raw_items = raw_items[: int(max_items)]
    import_items = _normalize_raw_items_to_import_items(
        raw_items,
        material_type=material_type,
    )
    if not import_items:
        return {
            "status": "finished_no_items",
            "state": state,
            "job_id": job_id,
            "scrapy_project": scrapy_project,
            "fetched_from": fetched_from,
            "log_url": log_url,
            "items_url": items_url,
            "raw_item_count": 0,
        }

    with bind_project(project_key):
        import_result = run_raw_import_materials(
            payload={
                "source_name": source_name or f"crawler.{scrapy_project}",
                "default_material_type": material_type,
                "enable_extraction": bool(enable_extraction),
                "items": import_items,
            },
            project_key=project_key,
        )
    return {
        "status": "ingested",
        "state": state,
        "job_id": job_id,
        "scrapy_project": scrapy_project,
        "fetched_from": fetched_from,
        "log_url": log_url,
        "items_url": items_url,
        "raw_item_count": len(raw_items),
        "import_result": _json_object(import_result),
    }


__all__ = ["ingest_scrapyd_job_output"]
