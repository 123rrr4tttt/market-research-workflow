from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select

from ..crawlers.scrapyd_runtime import ensure_scrapyd_ready
from ...models.base import SessionLocal
from ...models.entities import IngestChannel, SourceLibraryItem
from ..projects import bind_project


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _merge_unique_strings(*parts: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for value in part:
            key = str(value or "").strip()
            if not key:
                continue
            lowered = key.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            merged.append(key)
    return merged


def _normalize_allowlist(execution_policy: dict[str, Any], *, project_key: str, item_key: str) -> dict[str, Any]:
    policy = dict(execution_policy or {})
    gray = _as_dict(policy.get("gray_release"))
    allowlist = _as_dict(gray.get("allowlist"))
    projects = [str(x).strip() for x in _as_list(allowlist.get("projects")) if str(x or "").strip()]
    items = [str(x).strip() for x in _as_list(allowlist.get("items")) if str(x or "").strip()]
    allowlist["projects"] = _merge_unique_strings(projects, [project_key])
    allowlist["items"] = _merge_unique_strings(items, [item_key])
    gray["allowlist"] = allowlist
    policy["gray_release"] = gray
    return policy


def _resolve_scrapyd_endpoint(base_url: str | None) -> tuple[str, float]:
    configured = ensure_scrapyd_ready(base_url=base_url or os.getenv("SCRAPYD_BASE_URL"))
    timeout = float(os.getenv("SCRAPYD_TIMEOUT", "15.0"))
    return configured.rstrip("/"), timeout


def _load_egg_bytes(*, egg_file_path: str | None, egg_content_b64: str | None) -> bytes:
    if egg_content_b64:
        try:
            return base64.b64decode(egg_content_b64)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("egg_content_b64 is not valid base64 payload") from exc
    if egg_file_path:
        file_path = Path(str(egg_file_path)).expanduser().resolve()
        if not file_path.exists():
            raise ValueError(f"egg_file_path does not exist: {file_path}")
        return file_path.read_bytes()
    raise ValueError("either egg_file_path or egg_content_b64 is required for scrapy deploy")


def deploy_scrapy_project_version(
    *,
    project: str,
    version: str,
    egg_file_path: str | None = None,
    egg_content_b64: str | None = None,
    base_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scrapyd_base_url, timeout = _resolve_scrapyd_endpoint(base_url)
    project_name = str(project or "").strip()
    version_name = str(version or "").strip()
    if not project_name:
        raise ValueError("scrapy deploy requires non-empty project")
    if not version_name:
        raise ValueError("scrapy deploy requires non-empty version")

    egg_bytes = _load_egg_bytes(egg_file_path=egg_file_path, egg_content_b64=egg_content_b64)
    payload = {"project": project_name, "version": version_name}
    if metadata:
        payload["meta"] = json.dumps(dict(metadata), ensure_ascii=True)

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            f"{scrapyd_base_url}/addversion.json",
            data=payload,
            files={"egg": ("project.egg", egg_bytes, "application/octet-stream")},
        )
        resp.raise_for_status()
        body = resp.json()

    if not isinstance(body, dict):
        raise ValueError("invalid scrapyd addversion response")
    status = str(body.get("status") or "unknown").strip().lower()
    if status not in {"ok", "queued"}:
        raise ValueError(f"scrapyd addversion failed: {body}")
    return {
        "provider_type": "scrapy",
        "provider_status": status,
        "project": project_name,
        "version": version_name,
        "raw": {"addversion": body},
    }


def rollback_scrapy_project_version(
    *,
    project: str,
    version: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    scrapyd_base_url, timeout = _resolve_scrapyd_endpoint(base_url)
    project_name = str(project or "").strip()
    version_name = str(version or "").strip()
    if not project_name:
        raise ValueError("scrapy rollback requires non-empty project")
    if not version_name:
        raise ValueError("scrapy rollback requires non-empty version")

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            f"{scrapyd_base_url}/delversion.json",
            data={"project": project_name, "version": version_name},
        )
        resp.raise_for_status()
        body = resp.json()
    if not isinstance(body, dict):
        raise ValueError("invalid scrapyd delversion response")
    status = str(body.get("status") or "unknown").strip().lower()
    if status not in {"ok", "queued"}:
        raise ValueError(f"scrapyd delversion failed: {body}")
    return {
        "provider_type": "scrapy",
        "provider_status": status,
        "project": project_name,
        "version": version_name,
        "raw": {"delversion": body},
    }


def register_or_update_source_library_scrapy_binding(
    *,
    project_key: str,
    channel_key: str,
    item_key: str,
    spider: str,
    scrapy_project: str,
    channel_name: str | None = None,
    item_name: str | None = None,
    description: str | None = None,
    arguments: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    item_params_patch: dict[str, Any] | None = None,
    channel_extra_patch: dict[str, Any] | None = None,
    item_extra_patch: dict[str, Any] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    project_value = str(project_key or "").strip()
    channel_value = str(channel_key or "").strip()
    item_value = str(item_key or "").strip()
    spider_value = str(spider or "").strip()
    scrapy_project_value = str(scrapy_project or "").strip()
    if not project_value:
        raise ValueError("project_key is required")
    if not channel_value:
        raise ValueError("channel_key is required")
    if not item_value:
        raise ValueError("item_key is required")
    if not spider_value:
        raise ValueError("spider is required")
    if not scrapy_project_value:
        raise ValueError("scrapy_project is required")

    with bind_project(project_value):
        with SessionLocal() as session:
            channel_row = session.execute(
                select(IngestChannel).where(IngestChannel.channel_key == channel_value)
            ).scalar_one_or_none()
            if channel_row is None:
                channel_row = IngestChannel(channel_key=channel_value)
                session.add(channel_row)

            current_execution_policy = _as_dict(getattr(channel_row, "execution_policy", None))
            channel_row.name = str(channel_name or channel_value)
            channel_row.kind = str(getattr(channel_row, "kind", None) or "crawler")
            channel_row.provider = str(getattr(channel_row, "provider", None) or "crawler")
            channel_row.provider_type = "scrapy"
            channel_row.provider_config = {
                **_as_dict(getattr(channel_row, "provider_config", None)),
                "project": scrapy_project_value,
                "spider": spider_value,
            }
            channel_row.execution_policy = _normalize_allowlist(
                current_execution_policy,
                project_key=project_value,
                item_key=item_value,
            )
            channel_row.default_params = {
                **_as_dict(getattr(channel_row, "default_params", None)),
                "scrapy_project": scrapy_project_value,
                "project": scrapy_project_value,
                "spider": spider_value,
            }
            channel_row.param_schema = {
                **_as_dict(getattr(channel_row, "param_schema", None)),
                "required": _merge_unique_strings(
                    [str(x) for x in _as_list(_as_dict(getattr(channel_row, "param_schema", None)).get("required"))],
                    ["spider"],
                ),
            }
            if description is not None:
                channel_row.description = description
            if enabled is not None:
                channel_row.enabled = bool(enabled)
            channel_row.extra = {
                **_as_dict(getattr(channel_row, "extra", None)),
                **_as_dict(channel_extra_patch),
            }

            item_row = session.execute(
                select(SourceLibraryItem).where(SourceLibraryItem.item_key == item_value)
            ).scalar_one_or_none()
            if item_row is None:
                item_row = SourceLibraryItem(item_key=item_value)
                session.add(item_row)

            item_row.name = str(item_name or item_value)
            item_row.channel_key = channel_value
            if description is not None:
                item_row.description = description
            item_row.params = {
                **_as_dict(getattr(item_row, "params", None)),
                "scrapy_project": scrapy_project_value,
                "project": scrapy_project_value,
                "spider": spider_value,
                "arguments": _as_dict(arguments),
                "settings": _as_dict(settings),
                **_as_dict(item_params_patch),
            }
            item_row.tags = _merge_unique_strings(
                [str(x) for x in _as_list(getattr(item_row, "tags", None))],
                ["crawler", "scrapy"],
            )
            if enabled is not None:
                item_row.enabled = bool(enabled)
            item_row.extra = {
                **_as_dict(getattr(item_row, "extra", None)),
                **_as_dict(item_extra_patch),
            }

            session.commit()

    return {
        "project_key": project_value,
        "channel_key": channel_value,
        "item_key": item_value,
        "provider_type": "scrapy",
        "rollout_allowlist": {
            "projects": [project_value],
            "items": [item_value],
        },
        "channel_registered": True,
        "item_registered": True,
    }


def apply_source_library_native_rollback(
    *,
    project_key: str,
    channel_key: str,
    item_key: str | None = None,
    keep_item_enabled: bool = True,
) -> dict[str, Any]:
    project_value = str(project_key or "").strip()
    channel_value = str(channel_key or "").strip()
    if not project_value:
        raise ValueError("project_key is required")
    if not channel_value:
        raise ValueError("channel_key is required")

    row_exists = False
    item_updated = False
    with bind_project(project_value):
        with SessionLocal() as session:
            channel_row = session.execute(
                select(IngestChannel).where(IngestChannel.channel_key == channel_value)
            ).scalar_one_or_none()
            if channel_row is not None:
                row_exists = True
                channel_row.provider_type = "native"
                session.add(channel_row)

            item_value = str(item_key or "").strip()
            if item_value:
                item_row = session.execute(
                    select(SourceLibraryItem).where(SourceLibraryItem.item_key == item_value)
                ).scalar_one_or_none()
                if item_row is not None:
                    item_updated = True
                    if not keep_item_enabled:
                        item_row.enabled = False
                    session.add(item_row)

            session.commit()
    return {
        "project_key": project_value,
        "channel_key": channel_value,
        "item_key": str(item_key or "").strip() or None,
        "provider_type": "native",
        "channel_found": row_exists,
        "item_updated": item_updated,
    }
