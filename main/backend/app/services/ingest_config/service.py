"""Ingest config service: get/upsert project ingest configs."""

from __future__ import annotations

from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import IngestConfig
from ..projects import bind_schema


def get_config(project_key: str, config_key: str) -> dict | None:
    """Get ingest config by project_key + config_key. Returns payload dict if found, else None."""
    with bind_schema("public"):
        with SessionLocal() as session:
            cfg = session.execute(
                select(IngestConfig).where(
                    IngestConfig.project_key == project_key,
                    IngestConfig.config_key == config_key,
                )
            ).scalar_one_or_none()
            if not cfg:
                return None
            return {
                "project_key": cfg.project_key,
                "config_key": cfg.config_key,
                "config_type": cfg.config_type,
                "payload": cfg.payload,
                "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
                "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
            }


def upsert_config(
    project_key: str,
    config_key: str,
    config_type: str,
    payload: dict | None = None,
) -> dict:
    """Upsert ingest config. Returns the saved config dict."""
    with bind_schema("public"):
        with SessionLocal() as session:
            cfg = session.execute(
                select(IngestConfig).where(
                    IngestConfig.project_key == project_key,
                    IngestConfig.config_key == config_key,
                )
            ).scalar_one_or_none()
            if not cfg:
                cfg = IngestConfig(
                    project_key=project_key,
                    config_key=config_key,
                    config_type=config_type,
                    payload=payload,
                )
                session.add(cfg)
            else:
                cfg.config_type = config_type
                cfg.payload = payload
            session.commit()
            session.refresh(cfg)
    return {
        "project_key": cfg.project_key,
        "config_key": cfg.config_key,
        "config_type": cfg.config_type,
        "payload": cfg.payload,
        "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }
