from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable, Mapping
import json
from typing import Literal, Protocol, TypeAlias, TypedDict

from mrw_functorial_kit.core.provider_port_failures import (
    CollectRuntimeFailureCode,
    CrawlerRuntimeFailureCode,
)

FLOW_COLLECT = "collect"
FLOW_SOURCE_COLLECT = "source_collect"
ALLOWED_COLLECT_FLOWS = {FLOW_COLLECT, FLOW_SOURCE_COLLECT}

CollectJsonValue: TypeAlias = (
    None | bool | int | float | str
    | list["CollectJsonValue"]
    | dict[str, "CollectJsonValue"]
)
CollectJsonObject: TypeAlias = dict[str, CollectJsonValue]
SourceLibraryCompatResponse: TypeAlias = dict[str, CollectJsonValue]

CollectStatus: TypeAlias = Literal[
    "completed",
    "accepted",
    "partial",
    "failed",
    "cancelled",
    "unknown",
]
CollectFailureFamily: TypeAlias = Literal["crawler.runtime.failure"]


def _empty_string_list() -> list[str]:
    return []


def _empty_collect_json_object() -> CollectJsonObject:
    return {}


def _empty_collect_failure_list() -> list[CollectFailure]:
    return []


@dataclass(slots=True)
class CollectRequest:
    contract_version: str = "collect.request.v1"
    flow: str = FLOW_COLLECT
    channel: str = ""
    project_key: str | None = None
    query_terms: list[str] = field(default_factory=_empty_string_list)
    urls: list[str] = field(default_factory=_empty_string_list)
    limit: int | None = None
    provider: str | None = None
    language: str | None = None
    scope: str | None = None
    item_key: str | None = None
    resource_id: str | None = None
    platforms: list[str] | None = None
    options: CollectJsonObject = field(default_factory=_empty_collect_json_object)
    source_context: CollectJsonObject = field(default_factory=_empty_collect_json_object)


class CollectFailure(TypedDict, total=False):
    code: (
        CollectRuntimeFailureCode
        | CrawlerRuntimeFailureCode
        | Literal["collect_effect_not_registered", "element_rejected", "runner_unavailable"]
    )
    family: CollectFailureFamily
    message: str
    context: Mapping[str, CollectJsonValue]
    query_terms: list[str] | tuple[str, ...]
    exception_type: str | None
    error_digest: str


@dataclass(slots=True)
class CollectResult:
    flow: str = FLOW_COLLECT
    channel: str = ""
    status: CollectStatus = "completed"
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[CollectFailure] = field(default_factory=_empty_collect_failure_list)
    items: list[CollectJsonObject] | None = None
    meta: CollectJsonObject = field(default_factory=_empty_collect_json_object)
    display_meta: CollectJsonObject = field(default_factory=_empty_collect_json_object)
    provider_job_id: str | None = None
    provider_type: str | None = None
    provider_status: str | None = None
    attempt_count: int | None = None


class CollectAdapter(Protocol):
    def run(self, request: CollectRequest) -> CollectResult:
        ...


CollectRunner: TypeAlias = Callable[[CollectRequest], CollectResult]
CollectEffectGateway: TypeAlias = Callable[[CollectRequest], CollectResult]


class SourceLibraryCompatProjector(Protocol):
    def __call__(self, result: CollectResult) -> SourceLibraryCompatResponse:
        ...


def source_library_compat_response(value: object) -> SourceLibraryCompatResponse:
    """Validate the adapter-owned projection at its single composition seam."""

    try:
        encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise TypeError("source-library compatibility response must be JSON") from exc
    decoded: CollectJsonValue = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise TypeError("source-library compatibility response must be a JSON object")
    return decoded
