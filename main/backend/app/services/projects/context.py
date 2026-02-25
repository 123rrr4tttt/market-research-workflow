from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import re

from ...settings.config import settings


_PROJECT_KEY_VAR: ContextVar[str | None] = ContextVar("project_key", default=None)
_SCHEMA_VAR: ContextVar[str | None] = ContextVar("project_schema", default=None)


def _normalize_project_key(project_key: str) -> str:
    key = project_key.strip().lower()
    key = re.sub(r"[^a-z0-9_]+", "_", key)
    key = re.sub(r"_+", "_", key).strip("_")
    return key or settings.active_project_key or "default"


def project_schema_name(project_key: str) -> str:
    normalized = _normalize_project_key(project_key)
    # Reserve "public" as a meta-layer key (not a tenant schema).
    # Aggregation should be handled explicitly via aggregator schema/endpoints.
    if normalized == "public":
        return "public"
    return f"{settings.project_schema_prefix}{normalized}"


def current_project_key() -> str:
    key = _PROJECT_KEY_VAR.get()
    if key:
        return key
    return settings.active_project_key


def current_project_schema() -> str:
    schema = _SCHEMA_VAR.get()
    if schema:
        return schema
    return project_schema_name(current_project_key())


@contextmanager
def bind_project(project_key: str):
    token_key = _PROJECT_KEY_VAR.set(_normalize_project_key(project_key))
    token_schema = _SCHEMA_VAR.set(project_schema_name(project_key))
    try:
        yield
    finally:
        _SCHEMA_VAR.reset(token_schema)
        _PROJECT_KEY_VAR.reset(token_key)


@contextmanager
def bind_schema(schema_name: str):
    token_schema = _SCHEMA_VAR.set(schema_name)
    try:
        yield
    finally:
        _SCHEMA_VAR.reset(token_schema)
