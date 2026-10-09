from __future__ import annotations

import logging
import re
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, NoReturn

from functorial_kit import Failure
from starlette.requests import Request

from mrw_functorial_kit.core.application_failure_semantics import project_operation_failures

from ...settings.config import get_effective_project_key_enforcement_mode, settings

_PROJECT_KEY_VAR: ContextVar[str | None] = ContextVar("project_key", default=None)
_SCHEMA_VAR: ContextVar[str | None] = ContextVar("project_schema", default=None)


logger = logging.getLogger(__name__)


_PROJECT_FAILURE_WITNESS = "test:test_w01_project_identity_failures"
_PROJECT_FAILURE_CONTEXT_KEYS = frozenset(
    {
        "boundary_class",
        "failure_family",
        "operation",
        "owner",
        "public_exception",
        "public_message",
        "site",
        "witness",
    }
)


def project_failure(
    code: str,
    message: str,
    *,
    operation: str,
    site: str,
    public_exception: str,
    **details: Any,
) -> Failure:
    """Construct a closed project-operation failure before the ABI lift."""

    context: dict[str, Any] = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": project_operation_failures.name,
        "operation": operation,
        "owner": site,
        "public_exception": public_exception,
        "public_message": message,
        "site": site,
        "witness": _PROJECT_FAILURE_WITNESS,
    }
    context.update(details)
    return project_operation_failures.fail(code, message, context)


def raise_project_failure(
    failure: Failure,
    exception_type: type[Exception] = ValueError,
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    """Restore the established public exception at one explicit boundary."""

    context = failure.context or {}
    if (
        not project_operation_failures.matches(failure)
        or _PROJECT_FAILURE_CONTEXT_KEYS - set(context)
        or context.get("public_exception") != exception_type.__name__
    ):
        # kit:boundary owner=projects.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w01_project_context_and_workflow_lifts_preserve_public_messages
        raise TypeError("project operation failure lift context is incomplete")
    message = str(context["public_message"])
    if cause is None:
        # kit:boundary owner=projects.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=project.operation.failure witness=test:test_w01_project_context_and_workflow_lifts_preserve_public_messages
        raise exception_type(message)
    # kit:boundary owner=projects.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=project.operation.failure witness=test:test_w01_project_context_and_workflow_lifts_preserve_public_messages
    raise exception_type(message) from cause


_project_failure = project_failure
_raise_project_failure = raise_project_failure


def resolve_request_project_context(
    request: Request,
    *,
    fallback: Callable[[], str],
    explicit_project_key: str | None = None,
    use_resolved_fallback: bool = False,
    endpoint_payload: bool = False,
) -> tuple[str, str, bool]:
    """Read request scope once, preserving the endpoint's declared fallback."""
    explicit = str(explicit_project_key or "").strip()
    if explicit:
        return explicit, "endpoint_payload", False
    resolved_source = str(getattr(request.state, "project_key_source", "") or "")
    resolved = str(getattr(request.state, "project_key_resolved", "") or "").strip()
    if resolved and resolved_source in {"header", "query"}:
        return resolved, resolved_source, False
    for request_source, value in (
        ("header", request.headers.get("X-Project-Key")),
        ("query", request.query_params.get("project_key")),
    ):
        key = str(value or "").strip()
        if key:
            return key, request_source, False
    if use_resolved_fallback and resolved and resolved_source == "fallback":
        return resolved, "fallback", True
    if endpoint_payload:
        return "", "endpoint_payload", False
    return fallback(), "fallback", True


def normalize_project_key(project_key: str) -> str:
    key = project_key.strip().lower()
    key = re.sub(r"[^a-z0-9_]+", "_", key)
    key = re.sub(r"_+", "_", key).strip("_")
    return key or settings.active_project_key or "default"


PG_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


def _sanitize_schema_prefix(raw: str | None, *, fallback: str = "project_") -> str:
    s = (raw or fallback).strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s)
    if not s or not re.match(r"^[a-z_].*", s):
        s = fallback
    if not s.endswith("_"):
        s = f"{s}_"
    return s[:63]


def is_allowed_project_schema(schema_name: str) -> bool:
    schema = (schema_name or "").strip()
    if schema == "public":
        return True
    prefix = _sanitize_schema_prefix(settings.project_schema_prefix or "project_")
    if not schema.startswith(prefix):
        return False
    suffix = schema[len(prefix) :]
    normalized_suffix = normalize_project_key(suffix)
    return bool(suffix) and schema == f"{prefix}{normalized_suffix}"


def project_schema_name(project_key: str) -> str:
    normalized = normalize_project_key(project_key)
    # Reserve "public" as a meta-layer key (not a tenant schema).
    # Aggregation should be handled explicitly via aggregator schema/endpoints.
    if normalized == "public":
        return "public"
    safe_prefix = _sanitize_schema_prefix(settings.project_schema_prefix or "project_")
    full = f"{safe_prefix}{normalized}"
    if not PG_IDENTIFIER_RE.match(full):
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
    mode = get_effective_project_key_enforcement_mode()
    fallback = settings.active_project_key
    if mode == "require":
        _raise_project_failure(
            _project_failure(
                "project_key_required",
                "project key required but missing (enforcement=require)",
                operation="current_project_key",
                site="app.services.projects.context.current_project_key",
                public_exception="RuntimeError",
            ),
            RuntimeError,
        )
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
    normalized = normalize_project_key(raw)
    if normalized == "public":
        mode = get_effective_project_key_enforcement_mode()
        msg = "attempt to bind_project to reserved key public is not allowed"
        if mode == "require":
            _raise_project_failure(
                _project_failure(
                    "project_binding_conflict",
                    msg,
                    operation="bind_project",
                    site="app.services.projects.context.bind_project",
                    public_exception="ValueError",
                    project_key=raw,
                )
            )
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
def bind_resolved_project(project_key: str, resolved_schema: str):
    """Bind the exact server-resolved identity for an installed runtime kernel."""
    token_key = _PROJECT_KEY_VAR.set(project_key)
    token_schema = _SCHEMA_VAR.set(resolved_schema)
    try:
        yield
    finally:
        _SCHEMA_VAR.reset(token_schema)
        _PROJECT_KEY_VAR.reset(token_key)


@contextmanager
def bind_schema(schema_name: str):
    mode = str(getattr(settings, "project_key_enforcement_mode", "warn")).lower()
    if not is_allowed_project_schema(schema_name):
        msg = f"disallowed schema binding: {schema_name!r}"
        if mode == "require":
            _raise_project_failure(
                _project_failure(
                    "schema_binding_conflict",
                    msg,
                    operation="bind_schema",
                    site="app.services.projects.context.bind_schema",
                    public_exception="ValueError",
                    schema_name=schema_name,
                )
            )
        logger.warning(msg)
        # In warn mode, normalize to closest safe schema when possible
        if schema_name and schema_name != "public":
            # try to extract suffix and rebuild
            prefix = _sanitize_schema_prefix(settings.project_schema_prefix or "project_")
            suffix = schema_name[len(prefix) :] if schema_name.startswith(prefix) else schema_name
            schema_name = f"{prefix}{normalize_project_key(suffix)}"
    token_schema = _SCHEMA_VAR.set(schema_name)
    try:
        yield
    finally:
        _SCHEMA_VAR.reset(token_schema)
