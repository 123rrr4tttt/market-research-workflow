"""Ingest config service: get/upsert project ingest configs."""

from .service import get_config, upsert_config

__all__ = ["get_config", "upsert_config"]
