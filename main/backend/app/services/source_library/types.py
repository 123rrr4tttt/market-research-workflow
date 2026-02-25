from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(slots=True)
class ChannelRecord:
    channel_key: str
    name: str
    kind: str
    provider: str
    description: str | None
    credential_refs: list[str]
    default_params: Dict[str, Any]
    param_schema: Dict[str, Any]
    extends_channel_key: str | None
    enabled: bool
    extra: Dict[str, Any]
    scope: str


@dataclass(slots=True)
class SourceItemRecord:
    item_key: str
    name: str
    channel_key: str
    description: str | None
    params: Dict[str, Any]
    tags: list[str]
    schedule: str | None
    extends_item_key: str | None
    enabled: bool
    extra: Dict[str, Any]
    scope: str

