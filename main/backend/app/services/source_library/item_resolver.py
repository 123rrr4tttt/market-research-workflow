from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Literal

from .types import FrontDoorExecutionProtocol

SourceMode = Literal["protocol_search", "provider_harvest", "site_search", "url_execution"]
ItemType = Literal["user_defined", "service_aggregated"]
ManagedBy = Literal["user", "system"]


@dataclass(frozen=True)
class ExecutionRequest:
    source_mode: SourceMode
    item_key: str
    item_channel_key: str
    project_key: str | None
    params: Dict[str, Any]
    protocol: FrontDoorExecutionProtocol
    warnings: list[str] = field(default_factory=list)


def execution_request_to_dict(request: ExecutionRequest) -> Dict[str, Any]:
    return {
        "source_mode": request.source_mode,
        "item_key": request.item_key,
        "item_channel_key": request.item_channel_key,
        "project_key": request.project_key,
        "params": dict(request.params),
        "warnings": list(request.warnings),
    }


def normalize_item_taxonomy(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    extra = _as_dict(out.get("extra"))
    item_type = _resolve_item_type({**out, "extra": extra})
    managed_by = _resolve_managed_by({**out, "extra": extra}, item_type)
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
        params: Dict[str, Any],
        project_key: str | None,
        channel_map: Dict[str, Dict[str, Any]],
        build_frontdoor_protocol: Callable[..., FrontDoorExecutionProtocol],
        is_handler_cluster_item: Callable[[Dict[str, Any] | None], bool],
        has_site_entries: Callable[[Dict[str, Any] | None], bool],
    ) -> ExecutionRequest:
        item_key = str(item.get("item_key") or "").strip() or "_anonymous"
        item_channel_key = str(item.get("channel_key") or "").strip()
        channel = channel_map.get(item_channel_key) or {}
        provider = str(channel.get("provider") or "").strip().lower()
        provider_type = str(channel.get("provider_type") or "").strip().lower()
        protocol = build_frontdoor_protocol(item=item, params=params, project_key=project_key)
        warnings: list[str] = []

        source_mode: SourceMode = "protocol_search"
        if protocol.candidate_urls:
            source_mode = "url_execution"
        elif is_handler_cluster_item(item) or has_site_entries(params):
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

        if source_mode == "site_search" and item_channel_key.lower() != "handler.cluster":
            warnings.append(f"site_search_forced_handler_cluster:{item_channel_key or '<empty>'}")

        if provider == "generic_web" or item_channel_key.lower().startswith("generic_web."):
            warnings.append("generic_web_internal_adapter_detected")
            if source_mode != "url_execution" and protocol.candidate_urls:
                source_mode = "url_execution"
                warnings.append("generic_web_mode_coerced:url_execution")

        return ExecutionRequest(
            source_mode=source_mode,
            item_key=item_key,
            item_channel_key=item_channel_key,
            project_key=str(project_key or "").strip() or None,
            params=params,
            protocol=protocol,
            warnings=warnings,
        )


def _resolve_item_type(payload: Dict[str, Any]) -> ItemType:
    explicit = str(payload.get("item_type") or "").strip().lower()
    if explicit in {"user_defined", "service_aggregated"}:
        return explicit  # type: ignore[return-value]

    extra = _as_dict(payload.get("extra"))
    from_extra = str(extra.get("item_type") or "").strip().lower()
    if from_extra in {"user_defined", "service_aggregated"}:
        return from_extra  # type: ignore[return-value]

    channel_key = str(payload.get("channel_key") or "").strip().lower()
    item_key = str(payload.get("item_key") or "").strip().lower()
    if (
        channel_key == "handler.cluster"
        or channel_key.startswith("crawler.")
        or item_key.startswith("handler.cluster.")
        or item_key == "url_pool.default"
        or bool(extra.get("stable_handler_cluster"))
        or str(extra.get("creation_handler") or "").strip().lower().startswith("handler.")
        or str(extra.get("crawler_provider") or "").strip()
    ):
        return "service_aggregated"
    return "user_defined"


def _resolve_managed_by(payload: Dict[str, Any], item_type: ItemType) -> ManagedBy:
    explicit = str(payload.get("managed_by") or "").strip().lower()
    if explicit in {"user", "system"}:
        return explicit  # type: ignore[return-value]

    extra = _as_dict(payload.get("extra"))
    from_extra = str(extra.get("managed_by") or "").strip().lower()
    if from_extra in {"user", "system"}:
        return from_extra  # type: ignore[return-value]

    return "system" if item_type == "service_aggregated" else "user"


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}
