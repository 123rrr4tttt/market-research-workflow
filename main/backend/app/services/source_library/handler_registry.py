"""Channel handler registry: register and resolve builtin handlers by (provider, kind)."""

from __future__ import annotations

from typing import Any, Callable

ChannelHandler = Callable[[dict[object, object], str | None], dict[str, Any]]
ChannelKey = tuple[str, str]

_HANDLERS: dict[ChannelKey, ChannelHandler] = {}


def register(provider: str, kind: str, handler: ChannelHandler) -> None:
    """Register a builtin handler for (provider, kind)."""
    key = (provider.strip().lower(), kind.strip().lower())
    _HANDLERS[key] = handler


def get(provider: str, kind: str) -> ChannelHandler | None:
    """Return builtin handler for (provider, kind), or None if not registered."""
    key = (provider.strip().lower(), kind.strip().lower())
    return _HANDLERS.get(key)
