from __future__ import annotations

from typing import Any

from .errors import ErrorCode
from .responses import ApiMetaModel, fail, ok


def success_response(
    data: Any = None,
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Transitional helper. New code should prefer contracts.responses.ok().
    return ok(data, meta=ApiMetaModel(**(meta or {})))


def error_response(
    code: ErrorCode,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Transitional helper. New code should prefer contracts.responses.fail().
    return fail(
        code,
        message,
        details=details,
        meta=ApiMetaModel(**(meta or {})),
    )
