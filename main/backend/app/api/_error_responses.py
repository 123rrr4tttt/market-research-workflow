"""Shared HTTP projection for an existing contracts error envelope."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi.responses import JSONResponse

from ..contracts import ErrorCode, error_response


def error_json_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    *,
    details: Mapping[str, object] | None = None,
    meta: Mapping[str, object] | None = None,
) -> JSONResponse:
    """Project a contracts envelope to HTTP without changing its semantics."""
    payload = error_response(
        code,
        message,
        details=None if details is None else dict(details),
        meta=None if meta is None else dict(meta),
    )
    payload["detail"] = {"error": payload["error"], "message": message}
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={"X-Error-Code": code.value},
    )


__all__ = ["error_json_response"]
