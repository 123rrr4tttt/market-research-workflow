"""Shared HTTP projection for an existing contracts error envelope."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from ..contracts import ErrorCode, error_response


def error_json_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> JSONResponse:
    """Project a contracts envelope to HTTP without changing its semantics."""
    payload = error_response(code, message, details=details, meta=meta)
    payload["detail"] = {"error": payload["error"], "message": message}
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={"X-Error-Code": code.value},
    )


__all__ = ["error_json_response"]
