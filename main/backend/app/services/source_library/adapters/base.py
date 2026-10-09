"""Base protocol for channel handlers."""

from __future__ import annotations

from typing import Any, Protocol


class ChannelHandlerProtocol(Protocol):
    """Protocol for channel handlers: (params, project_key) -> dict."""

    def __call__(self, params: dict[object, object], project_key: str | None) -> dict[str, Any]:
        ...
