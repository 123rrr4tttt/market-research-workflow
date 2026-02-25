from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    NOT_FOUND = "NOT_FOUND"
    CONFIG_ERROR = "CONFIG_ERROR"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    PARSE_ERROR = "PARSE_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def map_exception_to_error(exc: Exception) -> tuple[ErrorCode, str, dict[str, Any] | None]:
    msg = str(exc) or exc.__class__.__name__
    lower = msg.lower()
    if "not found" in lower or "不存在" in msg:
        return ErrorCode.NOT_FOUND, msg, None
    if "rate limit" in lower or "429" in lower or "限流" in msg:
        return ErrorCode.RATE_LIMITED, msg, None
    if "json" in lower or "parse" in lower or "解析" in msg:
        return ErrorCode.PARSE_ERROR, msg, None
    if "api key" in lower or "配置" in msg or "missing" in lower:
        return ErrorCode.CONFIG_ERROR, msg, None
    if "http" in lower or "upstream" in lower or "timeout" in lower:
        return ErrorCode.UPSTREAM_ERROR, msg, None
    return ErrorCode.INTERNAL_ERROR, msg, {"exception_type": exc.__class__.__name__}
