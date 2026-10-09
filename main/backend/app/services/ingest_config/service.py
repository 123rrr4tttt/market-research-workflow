"""Ingest config service: get/upsert project ingest configs."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ...models.base import SessionLocal
from ...models.entities import IngestConfig
from ..projects import bind_schema

logger = logging.getLogger(__name__)


def _model_value(row: object, field: str) -> object:
    return getattr(row, field, None)


def _datetime_text(value: object) -> str | None:
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat()) if callable(isoformat) else None


def _config_view(cfg: object) -> dict[str, object]:
    return {
        "project_key": _model_value(cfg, "project_key"),
        "config_key": _model_value(cfg, "config_key"),
        "config_type": _model_value(cfg, "config_type"),
        "payload": _model_value(cfg, "payload"),
        "created_at": _datetime_text(_model_value(cfg, "created_at")),
        "updated_at": _datetime_text(_model_value(cfg, "updated_at")),
    }


def get_config(project_key: str, config_key: str) -> dict[str, object] | None:
    """Get ingest config by project_key + config_key. Returns payload dict if found, else None."""
    try:
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
                return _config_view(cfg)
    except SQLAlchemyError as exc:
        logger.warning(
            "ingest_config_read_degraded project_key=%s config_key=%s error=%s",
            project_key,
            config_key,
            exc.__class__.__name__,
        )
        return None


def upsert_config(
    project_key: str,
    config_key: str,
    config_type: str,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
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
                cfg = IngestConfig()
                setattr(cfg, "project_key", project_key)
                setattr(cfg, "config_key", config_key)
                setattr(cfg, "config_type", config_type)
                setattr(cfg, "payload", payload)
                session.add(cfg)
            else:
                setattr(cfg, "config_type", config_type)
                setattr(cfg, "payload", payload)
            session.commit()
            session.refresh(cfg)
    return _config_view(cfg)
