"""Base protocol for channel handlers."""

from __future__ import annotations

from typing import Any, Dict, Protocol


class ChannelHandlerProtocol(Protocol):
    """Protocol for channel handlers: (params, project_key) -> dict."""

    def __call__(self, params: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
        ...
