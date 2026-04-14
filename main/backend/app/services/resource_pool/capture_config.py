"""Capture config: which job_types to capture URLs for."""

from __future__ import annotations

from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import ResourcePoolCaptureConfig
from ..projects import bind_schema


def get_capture_config(project_key: str) -> dict:
    """Get capture config for project. Returns {job_types, scope, enabled}."""
    with bind_schema("public"):
        with SessionLocal() as session:
            row = session.execute(
                select(ResourcePoolCaptureConfig).where(
                    ResourcePoolCaptureConfig.project_key == project_key
                )
            ).scalar_one_or_none()
            if not row:
                return {"job_types": [], "scope": "project", "enabled": False}
            (cfg,) = row
            return {
                "job_types": cfg.job_types or [],
                "scope": cfg.scope or "project",
                "enabled": bool(cfg.enabled),
            }


def upsert_capture_config(
    project_key: str,
    *,
    job_types: list[str],
    scope: str = "project",
    enabled: bool = True,
) -> dict:
    """Upsert capture config for project."""
    with bind_schema("public"):
        with SessionLocal() as session:
            row = session.execute(
                select(ResourcePoolCaptureConfig).where(
                    ResourcePoolCaptureConfig.project_key == project_key
                )
            ).scalar_one_or_none()
            if not row:
                cfg = ResourcePoolCaptureConfig(
                    project_key=project_key,
                    scope=scope,
                    job_types=job_types,
                    enabled=enabled,
                )
                session.add(cfg)
            else:
                (cfg,) = row
                cfg.job_types = job_types
                cfg.scope = scope
                cfg.enabled = enabled
            session.commit()
    return {"project_key": project_key, "job_types": job_types, "scope": scope, "enabled": enabled}
