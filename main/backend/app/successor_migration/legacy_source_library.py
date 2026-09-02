"""Sibling legacy adapter for the C2.1 source-library resolve atom.

This is the only file allowed to call the legacy pure helpers
``item_resolver.ItemResolver``, ``item_resolver.normalize_item_taxonomy``,
``resolver._normalize_search_params`` and ``resolver._build_frontdoor_protocol``.
It deliberately never calls ``run_item_payload`` or any ``_run_source_mode_*``
orchestrator: the adapter only replays the deterministic resolve front door and
then projects the legacy ``ExecutionRequest`` into the frozen successor
observation.

The adapter validates the exact Program/Plan/contract/payload/project/catalog
and its own InterpreterBinding before touching the legacy helpers, and it
exposes the two independent exact binding helpers used by the legacy and
successor interpreters.  No code in this module claims both bindings for one
logical run.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from app.services.source_library.item_resolver import (
    ItemResolver,
)
from app.services.source_library.item_resolver import (
    normalize_item_taxonomy as _legacy_normalize_item_taxonomy,
)
from app.services.source_library.resolver import (
    _build_frontdoor_protocol as _legacy_build_frontdoor_protocol,
)
from app.services.source_library.resolver import (
    _has_site_entries as _legacy_has_site_entries,
)
from app.services.source_library.resolver import (
    _is_handler_cluster_item as _legacy_is_handler_cluster_item,
)
from app.services.source_library.resolver import (
    _normalize_search_params as _legacy_normalize_search_params,
)
from app.services.source_library.types import FrontDoorExecutionProtocol
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.source_library_c2_1 import (
    SOURCE_RESOLUTION_OBSERVATION_PROFILE,
    FrontDoorConcurrencyPlan,
    FrontDoorConcurrencyStage,
    FrontDoorProtocol,
    NormalizedParamsSnapshot,
    RejectedResolution,
    ResolvedResolution,
    SourceExecutionRequest,
    SourceMode,
    SourceRejection,
    SourceResolutionObservation,
    SourceResolutionPayload,
    SourceTaxonomy,
    versioned_warning_from_legacy_string,
)
from app.successor_runtime.capabilities.source_library_c2_1_interpreters import (
    SOURCE_LIBRARY_C2_1_LEGACY_INTERPRETER_ID,
    InterpreterFailure,
    InterpreterSuccess,
    ResolutionBindingMismatch,
    authority_requirement_digest,
    legacy_interpreter_profile_digest,
    require_exact_resolution_binding,
    require_resource_ceiling,
    successor_interpreter_profile_digest,
)
from app.successor_runtime.runtime.assignments import InterpreterBinding

__all__ = [
    "LegacySourceLibraryC2_1Adapter",
    "bindings_are_distinct",
    "build_legacy_source_library_c2_1_binding",
    "build_successor_source_library_c2_1_binding",
]


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _thaw(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        if value and all(
            isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
            for item in value
        ):
            return {str(key): _thaw(item) for key, item in value}
        if not value:
            return {}
        return [_thaw(item) for item in value]
    if isinstance(value, list):
        return [_thaw(item) for item in value]
    return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _enrich_item_legacy_dict(payload: SourceResolutionPayload) -> dict[str, Any]:
    """Mirror ``resolver._enrich_item_with_channel_tiering`` in pure form."""

    enriched = {
        "item_key": payload.item.item_key,
        "channel_key": payload.item.channel_key,
        "enabled": payload.item.enabled,
        "item_type": payload.item.item_type,
        "managed_by": payload.item.managed_by,
        "params": _thaw(payload.item.params),
        "extra": _thaw(payload.item.extra),
    }
    channel_key = str(enriched["channel_key"] or "").strip()
    entry = payload.catalog.entry_by_key(channel_key)
    extra = enriched["extra"]
    if entry is not None:
        if not str(extra.get("source_tier") or "").strip():
            extra["source_tier"] = str(getattr(entry, "source_tier", "") or "").strip()
        if not str(extra.get("onboarding_priority") or "").strip():
            extra["onboarding_priority"] = str(
                getattr(entry, "onboarding_priority", "") or ""
            ).strip()
        entry_extra = _thaw(getattr(entry, "extra", None))
        source_tiering = entry_extra.get("source_tiering")
        if isinstance(source_tiering, dict) and not isinstance(
            extra.get("source_tiering"), dict
        ):
            extra["source_tiering"] = dict(source_tiering)
    enriched["extra"] = extra
    return enriched


def _concurrency_plan_from_legacy(
    value: dict[str, Any],
) -> FrontDoorConcurrencyPlan:
    def stage(raw: dict[str, Any]) -> FrontDoorConcurrencyStage:
        return FrontDoorConcurrencyStage(
            stage=str(raw.get("stage") or ""),
            tasks_total=int(raw.get("tasks_total") or 0),
            requested_parallelism=int(raw.get("requested_parallelism") or 1),
            parallelism=int(raw.get("parallelism") or 1),
            budget=int(raw.get("budget") or 1),
            fail_fast=bool(raw.get("fail_fast", False)),
            timeout_seconds=raw.get("timeout_seconds"),
        )

    return FrontDoorConcurrencyPlan(
        batch_size=int(value.get("batch_size") or 1),
        shared_budget=int(value.get("shared_budget") or 1),
        search=stage(dict(value.get("search") or {})),
        url=stage(dict(value.get("url") or {})),
    )


def frontdoor_protocol_from_legacy(
    protocol: FrontDoorExecutionProtocol,
) -> FrontDoorProtocol:
    return FrontDoorProtocol(
        item_key=protocol.item_key,
        item_channel_key=protocol.item_channel_key,
        project_key=protocol.project_key,
        front_door_owner=protocol.front_door_owner,
        execution_mode=protocol.execution_mode,
        write_mode=protocol.write_mode,
        route_decision=protocol.route_decision,
        query_terms=tuple(protocol.query_terms),
        site_entries=tuple(protocol.site_entries),
        candidate_urls=tuple(protocol.candidate_urls),
        expected_entry_type=protocol.expected_entry_type,
        write_to_pool=protocol.write_to_pool,
        auto_ingest=protocol.auto_ingest,
        ingest_limit=protocol.ingest_limit,
        force_url_routing_flow=protocol.force_url_routing_flow,
        prefer_crawler_first=protocol.prefer_crawler_first,
        search_parallelism=protocol.search_parallelism,
        routing_parallelism=protocol.routing_parallelism,
        concurrency_plan=_concurrency_plan_from_legacy(
            dict(protocol.concurrency_plan or {})
        ),
        source_tier=protocol.source_tier,
        onboarding_priority=protocol.onboarding_priority,
    )


def _canonical_request_from_legacy(
    legacy_request: Any,
    payload: SourceResolutionPayload,
) -> SourceExecutionRequest:
    taxonomy = legacy_request.taxonomy
    return SourceExecutionRequest(
        source_mode=SourceMode(legacy_request.source_mode),
        item_key=legacy_request.item_key,
        item_channel_key=legacy_request.item_channel_key,
        project_key=legacy_request.project_key,
        project_scope=payload.project_scope,
        item_revision=payload.item.revision,
        item_incarnation=payload.item.incarnation,
        item_content_digest=payload.item.content_digest,
        catalog_revision=payload.catalog.revision,
        catalog_incarnation=payload.catalog.incarnation,
        catalog_digest=payload.catalog.digest,
        params=NormalizedParamsSnapshot.from_dict(dict(legacy_request.params)),
        protocol=frontdoor_protocol_from_legacy(legacy_request.protocol),
        warnings=tuple(
            versioned_warning_from_legacy_string(warning)
            for warning in legacy_request.warnings
        ),
        taxonomy=SourceTaxonomy(
            channel_family=taxonomy["channel_family"],
            item_type=taxonomy["item_type"],
            managed_by=taxonomy["managed_by"],
            expected_entry_type=taxonomy["expected_entry_type"],
            internal_adapter_only=bool(taxonomy["internal_adapter_only"]),
            site_search_authoritative=bool(taxonomy["site_search_authoritative"]),
        ),
    )


def _observation_for_request(
    request: SourceExecutionRequest,
) -> SourceResolutionObservation:
    return SourceResolutionObservation(
        observation_profile=SOURCE_RESOLUTION_OBSERVATION_PROFILE,
        project_scope=request.project_scope,
        item_revision=request.item_revision,
        item_incarnation=request.item_incarnation,
        item_content_digest=request.item_content_digest,
        catalog_revision=request.catalog_revision,
        catalog_incarnation=request.catalog_incarnation,
        catalog_digest=request.catalog_digest,
        normalized_params=request.params,
        source_mode=request.source_mode,
        taxonomy=request.taxonomy,
        warnings=request.warnings,
        protocol=request.protocol,
        observation_digest="",
    )


@dataclass(frozen=True, slots=True)
class LegacyResolutionTrace:
    """Deterministic replay trace over the legacy pure resolve helpers."""

    trace_id: str
    normalized_params: dict[str, Any]
    source_mode: str
    taxonomy: dict[str, Any]
    warnings: list[str]
    protocol: dict[str, Any]
    trace_digest: str = ""

    def __post_init__(self) -> None:
        if not self.trace_id:
            raise ValueError("LegacyResolutionTrace.trace_id is required")
        if self.trace_digest == "":
            object.__setattr__(
                self,
                "trace_digest",
                content_digest(
                    {
                        "schema": "mrw.successor.source-library.c2-1.trace.v1",
                        "trace_id": self.trace_id,
                        "normalized_params": self.normalized_params,
                        "source_mode": self.source_mode,
                        "taxonomy": self.taxonomy,
                        "warnings": self.warnings,
                        "protocol": self.protocol,
                    }
                ),
            )


class LegacySourceLibraryC2_1Adapter:
    """Legacy sibling interpreter for the C2.1 resolve atom."""

    interpreter_id = SOURCE_LIBRARY_C2_1_LEGACY_INTERPRETER_ID

    def __init__(self) -> None:
        self.resolves = 0
        self.traces: list[LegacyResolutionTrace] = []

    def _resolve_legacy(
        self, payload: SourceResolutionPayload
    ) -> tuple[Any, dict[str, Any], dict[str, Any]]:
        item_key = str(payload.item.item_key or "").strip() or "_anonymous"
        item_channel_key = str(payload.item.channel_key or "").strip()
        item = _enrich_item_legacy_dict(payload)
        item = _legacy_normalize_item_taxonomy(item)
        merged = _deep_merge(_thaw(payload.item.params), _thaw(payload.params))
        normalized = _legacy_normalize_search_params(merged)

        item_type = str(item.get("item_type") or "").strip().lower()
        managed_by = str(item.get("managed_by") or "").strip().lower()
        generic_web_internal_item = (
            item_type == "service_aggregated" and managed_by == "system"
        )
        if (
            item_channel_key.lower().startswith("generic_web.")
            and not generic_web_internal_item
        ):
            raise _GenericWebDirectRejected(
                "generic_web.* direct item execution is disabled; "
                "use site_search(handler.cluster) entry"
            )

        if item_channel_key.lower() == "url_pool" or item_key.lower().startswith(
            "url_pool."
        ):
            allow_legacy_url_list = _as_bool(
                normalized.get("enable_legacy_url_list"), True
            )
            if not allow_legacy_url_list and isinstance(normalized.get("urls"), list):
                normalized = dict(normalized)
                normalized.pop("urls", None)
                normalized["legacy_url_list_frozen"] = True

        channel_map = {
            entry.channel_key: entry.to_plain_dict()
            for entry in payload.catalog.entries
        }
        legacy_request = ItemResolver.resolve(
            item=item,
            params=normalized,
            project_key=payload.project_scope.project_key,
            channel_map=channel_map,
            build_frontdoor_protocol=_legacy_build_frontdoor_protocol,
            is_handler_cluster_item=_legacy_is_handler_cluster_item,
            has_site_entries=_legacy_has_site_entries,
        )
        return legacy_request, item, normalized

    def resolve(
        self,
        payload: SourceResolutionPayload,
        *,
        program: Any,
        plan: Any,
        contract_ref: Any,
        payload_ref: Any,
        project_scope: Any,
        catalog: Any,
        deployment_catalog_digest: str,
        binding: Any,
        expected_interpreter_profile_digest: str | None = None,
    ):
        try:
            require_exact_resolution_binding(
                program=program,
                plan=plan,
                contract_ref=contract_ref,
                payload_ref=payload_ref,
                payload=payload,
                project_scope=project_scope,
                catalog=catalog,
                deployment_catalog_digest=deployment_catalog_digest,
                binding=binding,
                expected_interpreter_profile_digest=(
                    expected_interpreter_profile_digest
                    or legacy_interpreter_profile_digest()
                ),
            )
        except ResolutionBindingMismatch as exc:
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str(exc),
                retryable=False,
            )

        item_key = str(payload.item.item_key or "").strip() or "_anonymous"
        if not payload.item.enabled:
            return InterpreterSuccess(
                RejectedResolution(
                    SourceRejection(
                        code="DISABLED_ITEM",
                        version="1",
                        message=f"source item disabled: {item_key}",
                    )
                )
            )
        if (
            not item_key
            and not str(payload.item.channel_key or "").strip()
            and not _thaw(payload.item.params)
            and not _thaw(payload.params)
        ):
            return InterpreterSuccess(
                RejectedResolution(
                    SourceRejection(
                        code="INVALID_ITEM",
                        version="1",
                        message=("source item has no identity, channel or parameters"),
                    )
                )
            )
        ceiling_message = require_resource_ceiling(payload)
        if ceiling_message is not None:
            return InterpreterSuccess(
                RejectedResolution(
                    SourceRejection(
                        code="RESOURCE_CEILING_EXCEEDED",
                        version="1",
                        message=ceiling_message,
                    )
                )
            )

        try:
            legacy_request, _item, _normalized = self._resolve_legacy(payload)
        except _GenericWebDirectRejected as exc:
            return InterpreterSuccess(
                RejectedResolution(
                    SourceRejection(
                        code="FORBIDDEN_INTERNAL_ADAPTER",
                        version="1",
                        message=str(exc),
                    )
                )
            )

        self.resolves += 1
        request = _canonical_request_from_legacy(legacy_request, payload)
        observation = _observation_for_request(request)
        return InterpreterSuccess(
            ResolvedResolution(
                request=request,
                observation_digest=observation.observation_digest,
            )
        )

    def _trace(
        self,
        payload: SourceResolutionPayload,
        *,
        trace_id: str = "legacy.c2_1.trace",
    ) -> LegacyResolutionTrace:
        if not payload.item.enabled:
            raise ValueError("trace requires an enabled item")
        try:
            legacy_request, _item, normalized = self._resolve_legacy(payload)
        except _GenericWebDirectRejected as exc:
            raise ValueError(str(exc)) from exc
        trace = LegacyResolutionTrace(
            trace_id=trace_id,
            normalized_params=dict(normalized),
            source_mode=str(legacy_request.source_mode),
            taxonomy=dict(legacy_request.taxonomy),
            warnings=list(legacy_request.warnings),
            protocol=dataclasses.asdict(legacy_request.protocol),
            trace_digest="",
        )
        self.traces.append(trace)
        return trace


class _GenericWebDirectRejected(ValueError):
    """Internal marker for the frozen FORBIDDEN_INTERNAL_ADAPTER gate."""


def build_legacy_source_library_c2_1_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    """One exact legacy interpreter binding; never claims successor too."""

    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=legacy_interpreter_profile_digest(),
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest(),
    )


def build_successor_source_library_c2_1_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    """One exact successor interpreter binding; never claims legacy too."""

    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=successor_interpreter_profile_digest(),
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest(),
    )


def bindings_are_distinct(
    legacy: InterpreterBinding, successor: InterpreterBinding
) -> bool:
    return (
        legacy.interpreter_profile_digest != successor.interpreter_profile_digest
        and legacy.binding_digest != successor.binding_digest
    )
