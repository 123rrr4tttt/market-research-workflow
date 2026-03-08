from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(slots=True)
class ChannelRecord:
    channel_key: str
    name: str
    kind: str
    provider: str
    provider_type: str
    provider_config: Dict[str, Any]
    execution_policy: Dict[str, Any]
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


@dataclass(slots=True)
class FrontDoorExecutionProtocol:
    item_key: str
    item_channel_key: str
    project_key: str | None
    front_door_owner: str
    execution_mode: str
    write_mode: str
    route_decision: str
    query_terms: list[str]
    site_entries: list[str]
    candidate_urls: list[str]
    expected_entry_type: str | None
    write_to_pool: bool
    auto_ingest: bool
    ingest_limit: int
    force_single_url_flow: bool
    prefer_crawler_first: bool
    search_parallelism: int
    routing_parallelism: int
