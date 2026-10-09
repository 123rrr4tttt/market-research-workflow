"""Capture config: which job_types to capture URLs for."""

from __future__ import annotations

from typing import TypedDict, TypeGuard

from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import ResourcePoolCaptureConfig
from ..projects import bind_schema


class CaptureConfig(TypedDict):
    job_types: list[str]
    scope: str
    enabled: bool


class StoredCaptureConfig(CaptureConfig):
    project_key: str


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _job_types(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if _is_object_list(value) else []


def _scope(value: object) -> str:
    return value if type(value) is str and value else "project"


def _enabled(value: object) -> bool:
    return value if type(value) is bool else False


def get_capture_config(project_key: str) -> CaptureConfig:
    """Get capture config for project. Returns {job_types, scope, enabled}."""
    with bind_schema("public"):
        with SessionLocal() as session:
            row = session.execute(
                select(ResourcePoolCaptureConfig).where(
                    ResourcePoolCaptureConfig.project_key == project_key
                )
            ).scalar_one_or_none()
            if row is None:
                return {"job_types": [], "scope": "project", "enabled": False}
            return {
                "job_types": _job_types(row.job_types),
                "scope": _scope(row.scope),
                "enabled": _enabled(row.enabled),
            }


def upsert_capture_config(
    project_key: str,
    *,
    job_types: list[str],
    scope: str = "project",
    enabled: bool = True,
) -> StoredCaptureConfig:
    """Upsert capture config for project."""
    with bind_schema("public"):
        with SessionLocal() as session:
            row = session.execute(
                select(ResourcePoolCaptureConfig).where(
                    ResourcePoolCaptureConfig.project_key == project_key
                )
            ).scalar_one_or_none()
            if row is None:
                cfg = ResourcePoolCaptureConfig(
                    project_key=project_key,
                    scope=scope,
                    job_types=job_types,
                    enabled=enabled,
                )
                session.add(cfg)
            else:
                row.job_types = job_types
                row.scope = scope
                row.enabled = enabled
            session.commit()
    return {"project_key": project_key, "job_types": job_types, "scope": scope, "enabled": enabled}
