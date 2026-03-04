from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import logging
import re

from ...settings.config import settings


_PROJECT_KEY_VAR: ContextVar[str | None] = ContextVar("project_key", default=None)
_SCHEMA_VAR: ContextVar[str | None] = ContextVar("project_schema", default=None)


logger = logging.getLogger(__name__)


def _normalize_project_key(project_key: str) -> str:
    key = project_key.strip().lower()
    key = re.sub(r"[^a-z0-9_]+", "_", key)
    key = re.sub(r"_+", "_", key).strip("_")
    return key or settings.active_project_key or "default"


_PG_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


def _sanitize_identifier(raw: str, *, fallback: str) -> str:
    s = (raw or "").strip()
    if not s:
        return fallback
    # Normalize to lower-case for consistency with _normalize_project_key output
    s = re.sub(r"[^a-z0-9_]+", "_", s.lower())
    s = re.sub(r"_+", "_", s).strip("_")
    # Ensure first char is alpha/underscore per PG rules by prefixing underscore if needed
    if not s or not re.match(r"^[a-z_].*", s):
        s = f"_{s}" if s else fallback
    # Truncate to 63 chars (PG identifier limit)
    return s[:63]


def _is_allowed_schema(schema_name: str) -> bool:
    schema = (schema_name or "").strip()
    if schema == "public":
        return True
    prefix = _sanitize_identifier(settings.project_schema_prefix or "project_", fallback="project_")
    if not schema.startswith(prefix):
        return False
    suffix = schema[len(prefix) :]
    normalized_suffix = _normalize_project_key(suffix)
    return bool(suffix) and schema == f"{prefix}{normalized_suffix}"


def project_schema_name(project_key: str) -> str:
    normalized = _normalize_project_key(project_key)
    # Reserve "public" as a meta-layer key (not a tenant schema).
    # Aggregation should be handled explicitly via aggregator schema/endpoints.
    if normalized == "public":
        return "public"
    safe_prefix = _sanitize_identifier(settings.project_schema_prefix or "project_", fallback="project_")
    full = f"{safe_prefix}{normalized}"
    if not _PG_IDENT_RE.match(full):
        # As a last resort, compress invalid characters and trim to 63 chars.
        compact = re.sub(r"[^a-z0-9_]+", "_", full.lower())
        compact = re.sub(r"_+", "_", compact).strip("_")[:63]
        logger.warning("project_schema_name adjusted to safe identifier: %r -> %r", full, compact)
        return compact or "public"
    return full


def current_project_key() -> str:
    key = _PROJECT_KEY_VAR.get()
    if key:
        return key
    # No explicit context; enforce per mode.
    mode = str(getattr(settings, "project_key_enforcement_mode", "warn")).lower()
    fallback = settings.active_project_key
    if mode == "require":
        raise RuntimeError("project key required but missing (enforcement=require)")
    logger.warning(
        "project key missing; fallback to active_project_key=%r (mode=%s)",
        fallback,
        mode,
    )
    return fallback


def current_project_schema() -> str:
    schema = _SCHEMA_VAR.get()
    if schema:
        return schema
    return project_schema_name(current_project_key())


@contextmanager
def bind_project(project_key: str):
    raw = str(project_key or "").strip()
    normalized = _normalize_project_key(raw)
    if normalized == "public":
        mode = str(getattr(settings, "project_key_enforcement_mode", "warn")).lower()
        msg = "attempt to bind_project to reserved key public is not allowed"
        if mode == "require":
            raise ValueError(msg)
        logger.warning(msg)
        # fallback to active project in warn mode
        normalized = settings.active_project_key
    token_key = _PROJECT_KEY_VAR.set(normalized)
    token_schema = _SCHEMA_VAR.set(project_schema_name(normalized))
    try:
        yield
    finally:
        _SCHEMA_VAR.reset(token_schema)
        _PROJECT_KEY_VAR.reset(token_key)


@contextmanager
def bind_schema(schema_name: str):
    mode = str(getattr(settings, "project_key_enforcement_mode", "warn")).lower()
    if not _is_allowed_schema(schema_name):
        msg = f"disallowed schema binding: {schema_name!r}"
        if mode == "require":
            raise ValueError(msg)
        logger.warning(msg)
        # In warn mode, normalize to closest safe schema when possible
        if schema_name and schema_name != "public":
            # try to extract suffix and rebuild
            prefix = _sanitize_identifier(settings.project_schema_prefix or "project_", fallback="project_")
            suffix = schema_name[len(prefix) :] if schema_name.startswith(prefix) else schema_name
            schema_name = f"{prefix}{_normalize_project_key(suffix)}"
    token_schema = _SCHEMA_VAR.set(schema_name)
    try:
        yield
    finally:
        _SCHEMA_VAR.reset(token_schema)
