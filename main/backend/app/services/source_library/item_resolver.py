from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any, Callable, Dict, Literal, NotRequired, TypeGuard, TypedDict

from .types import (
    FrontDoorExecutionProtocol,
    resolve_source_library_item_markers,
)

SourceMode = Literal["protocol_search", "provider_harvest", "site_search", "url_execution"]


class ExecutionPayload(TypedDict):
    item_key: str
    channel_key: str | None
    params: dict[object, object]
    result: dict[str, object]
    orchestrator: NotRequired[dict[str, str]]


@dataclass(frozen=True)
class ExecutionRequest:
    source_mode: SourceMode
    item_key: str
    item_channel_key: str
    project_key: str | None
    params: dict[object, object]
    protocol: FrontDoorExecutionProtocol
    warnings: list[str] = field(default_factory=list[str])
    taxonomy: Dict[str, Any] = field(default_factory=dict[str, Any])

    def attach_result(self, payload: ExecutionPayload) -> ExecutionPayload:
        payload["result"].setdefault("execution_request", execution_request_to_dict(self))
        return payload

    def complete(
        self, result: Mapping[str, object], *, channel_key: str | None,
        params: dict[object, object] | None = None,
    ) -> ExecutionPayload:
        return self.attach_result({
            "item_key": self.item_key,
            "channel_key": channel_key,
            "params": self.params if params is None else params,
            "result": result if isinstance(result, dict) else dict(result),
        })


def terminal_output_params(params: Mapping[object, object]) -> dict[object, object]:
    return {
        **params,
        "_source_library_execution_layer": "terminal_output_only",
        "_source_library_terminal_output_only": True,
        "source_library_execution_layer": "terminal_output_only",
        "source_library_terminal_output_only": True,
    }


def execution_request_to_dict(request: ExecutionRequest) -> Dict[str, Any]:
    return {
        "source_mode": request.source_mode,
        "item_key": request.item_key,
        "item_channel_key": request.item_channel_key,
        "project_key": request.project_key,
        "params": dict(request.params),
        "warnings": list(request.warnings),
        "taxonomy": dict(request.taxonomy),
    }


def normalize_item_taxonomy(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    extra = _as_dict(out.get("extra"))
    item_type, managed_by = resolve_source_library_item_markers(
        item_type=out.get("item_type"),
        managed_by=out.get("managed_by"),
        item_key=out.get("item_key"),
        channel_key=out.get("channel_key"),
        extra=extra,
    )
    out["item_type"] = item_type
    out["managed_by"] = managed_by
    extra.setdefault("item_type", item_type)
    extra.setdefault("managed_by", managed_by)
    out["extra"] = extra
    return out


class ItemResolver:
    @staticmethod
    def resolve(
        *,
        item: Dict[str, Any],
        params: dict[object, object],
        project_key: str | None,
        channel_map: Dict[str, Dict[str, Any]],
        build_frontdoor_protocol: Callable[..., FrontDoorExecutionProtocol],
        is_handler_cluster_item: Callable[[Dict[str, Any] | None], bool],
        has_site_entries: Callable[[Mapping[object, object] | None], bool],
    ) -> ExecutionRequest:
        item_key = str(item.get("item_key") or "").strip() or "_anonymous"
        item_channel_key = str(item.get("channel_key") or "").strip()
        channel = channel_map.get(item_channel_key) or {}
        provider = str(channel.get("provider") or "").strip().lower()
        provider_type = str(channel.get("provider_type") or "").strip().lower()
        item_extra = _as_dict(item.get("extra"))
        normalized_item = normalize_item_taxonomy(item)
        channel_family = _resolve_channel_family(
            item_channel_key=item_channel_key,
            provider=provider,
            provider_type=provider_type,
        )
        expected_entry_type = str(
            params.get("expected_entry_type")
            or item_extra.get("expected_entry_type")
            or _as_dict(item.get("params")).get("expected_entry_type")
            or ""
        ).strip().lower()
        site_search_authoritative = _is_site_search_authoritative(
            item=item,
            params=params,
            item_channel_key=item_channel_key,
            channel_family=channel_family,
            expected_entry_type=expected_entry_type,
            is_handler_cluster_item=is_handler_cluster_item,
            has_site_entries=has_site_entries,
        )
        protocol = build_frontdoor_protocol(item=item, params=params, project_key=project_key)
        warnings: list[str] = []

        source_mode: SourceMode = "protocol_search"
        if protocol.candidate_urls:
            source_mode = "url_execution"
        elif site_search_authoritative:
            source_mode = "site_search"
        elif provider_type in {"scrapy", "crawlee", "meltano"} or item_channel_key.lower().startswith("crawler."):
            source_mode = "provider_harvest"

        explicit_mode = str(params.get("source_mode") or "").strip().lower()
        if explicit_mode:
            allowed_modes = {"protocol_search", "provider_harvest", "site_search", "url_execution"}
            if explicit_mode in allowed_modes:
                source_mode = explicit_mode  # type: ignore[assignment]
            else:
                warnings.append(f"invalid_source_mode_ignored:{explicit_mode}")

        if protocol.candidate_urls and source_mode != "url_execution":
            warnings.append(f"source_mode_overridden_by_urls:{source_mode}->url_execution")
            source_mode = "url_execution"

        if site_search_authoritative and source_mode not in {"site_search", "url_execution"}:
            warnings.append(f"source_mode_coerced_by_site_search_taxonomy:{source_mode}->site_search")
            source_mode = "site_search"

        if source_mode == "site_search" and item_channel_key.lower() != "handler.cluster":
            warnings.append(f"site_search_forced_handler_cluster:{item_channel_key or '<empty>'}")

        if channel_family == "generic_web":
            warnings.append("generic_web_internal_adapter_detected")
            if source_mode not in {"site_search", "url_execution"}:
                warnings.append(f"generic_web_mode_coerced:{source_mode}->site_search")
                source_mode = "site_search"

        taxonomy = {
            "channel_family": channel_family,
            "item_type": normalized_item.get("item_type"),
            "managed_by": normalized_item.get("managed_by"),
            "expected_entry_type": expected_entry_type or None,
            "internal_adapter_only": channel_family == "generic_web",
            "site_search_authoritative": site_search_authoritative,
        }

        return ExecutionRequest(
            source_mode=source_mode,
            item_key=item_key,
            item_channel_key=item_channel_key,
            project_key=str(project_key or "").strip() or None,
            params=params,
            protocol=protocol,
            warnings=warnings,
            taxonomy=taxonomy,
        )


def _resolve_channel_family(*, item_channel_key: str, provider: str, provider_type: str) -> str:
    channel_key = str(item_channel_key or "").strip().lower()
    if channel_key == "handler.cluster":
        return "handler_cluster"
    if channel_key.startswith("generic_web.") or provider == "generic_web":
        return "generic_web"
    if channel_key.startswith("crawler.") or provider_type in {"scrapy", "crawlee", "meltano"}:
        return "crawler_provider"
    if channel_key == "url_pool":
        return "url_pool"
    return provider or "single_channel"


def _is_site_search_authoritative(
    *,
    item: Dict[str, Any],
    params: Mapping[object, object],
    item_channel_key: str,
    channel_family: str,
    expected_entry_type: str,
    is_handler_cluster_item: Callable[[Dict[str, Any] | None], bool],
    has_site_entries: Callable[[Mapping[object, object] | None], bool],
) -> bool:
    if channel_family in {"handler_cluster", "generic_web"}:
        return True
    if is_handler_cluster_item(item):
        return True
    if has_site_entries(params):
        return True
    if expected_entry_type:
        return True
    return False


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def channel_default_params(value: object) -> dict[object, object]:
    if not _is_object_mapping(value):
        # kit:boundary owner=source_library.item_resolver.channel_defaults class=PROGRAMMER_DEFECT failure_family=none witness=test:test_run_item_payload_preserves_opaque_mapping_defaults_and_override
        raise TypeError("source channel default_params must be a mapping with string keys")
    return dict(value)


def item_mapping_fields(value: object) -> dict[object, object]:
    return dict(value) if _is_object_dict(value) else {}


def _as_dict(value: object) -> Dict[str, Any]:
    if _is_object_dict(value):
        return {str(key): item for key, item in value.items()}
    return {}
