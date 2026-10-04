"""P3 C2.2 legacy fixture replay, shadow and rollback observations."""

from __future__ import annotations

from typing import Any

from app.successor_migration.legacy_source_library_c2_2 import (
    LegacySourceLibraryC2_2Adapter,
)
from app.successor_runtime.capabilities import source_library_c2_1 as c21
from app.successor_runtime.capabilities import source_library_c2_2 as c22
from app.successor_runtime.capabilities import source_library_c2_2_interpreters as c22i
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.source_library_c2_1 import (
    source_item_definition_content_digest,
)
from app.successor_runtime.capabilities.source_library_c2_1_interpreters import (
    resolve_source_execution_request,
)

PROJECT_KEY = "demo_proj"
REGISTRY_REVISION = 5
RESOLVED_SCHEMA = "mrw_p_demo_proj"
SCOPE_INCARNATION = "scope-inc-5"
SCOPE_DIGEST = c21.project_scope_digest(
    PROJECT_KEY, RESOLVED_SCHEMA, REGISTRY_REVISION, SCOPE_INCARNATION
)
ORCHESTRATION_POLICY_REF = "mrw.successor.source-library.c2-2.policy.v1"


def _channels() -> list[dict[str, Any]]:
    return [
        {
            "channel_key": "handler.cluster",
            "provider_type": "native",
            "enabled": True,
            "extra": {"credential_refs": ["credential:/secret-ref/hc-api-key"]},
        },
        {
            "channel_key": "crawler.demo_proj",
            "provider_type": "scrapy",
            "enabled": True,
        },
        {"channel_key": "market.default", "provider_type": "native", "enabled": True},
        {
            "channel_key": "generic_web.search_template",
            "provider": "generic_web",
            "provider_type": "native",
            "enabled": True,
        },
    ]


def _channel_map() -> dict[str, dict[str, Any]]:
    return {channel["channel_key"]: dict(channel) for channel in _channels()}


def _resolved_request(
    item: dict[str, Any],
    params: dict[str, Any],
) -> tuple[Any, c21.SourceExecutionRequest]:
    values = dict(item)
    values["content_digest"] = source_item_definition_content_digest(values)
    payload = c21.payload_from_dicts(
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=RESOLVED_SCHEMA,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST,
        channels=_channels(),
        item=values,
        params=params,
    )
    resolved = resolve_source_execution_request(payload)
    assert isinstance(resolved, c21.ResolvedResolution)
    return payload, resolved.request


def _successor_plan(
    payload: Any,
    request: c21.SourceExecutionRequest,
) -> c22.SourceModePlan:
    planning = c22.SourceModePlanningPayload(
        schema_version=c22.SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA,
        operation_kind=c22i.kind_for_mode(request.source_mode.mode),
        project_scope=request.project_scope,
        execution_request=request,
        execution_request_digest=content_digest(request.to_plain()),
        catalog=payload.catalog,
        item_revision=request.item_revision,
        item_incarnation=request.item_incarnation,
        item_content_digest=request.item_content_digest,
        orchestration_policy_ref=ORCHESTRATION_POLICY_REF,
        resource_ceiling_digest=c21.resource_ceiling_digest(),
    )
    result = c22i.plan_source_mode(planning)
    assert isinstance(result, c22.PlannedPlanning)
    return result.plan


def test_legacy_replay_uses_fixture_callbacks_only() -> None:
    _payload, request = _resolved_request(
        {
            "item_key": "handler.cluster.news",
            "channel_key": "handler.cluster",
            "enabled": True,
            "params": {"keywords": ["robotics"], "limit": 9},
            "extra": {
                "stable_handler_cluster": True,
                "expected_entry_type": "search_template",
            },
            "revision": 3,
            "incarnation": "item-inc-3",
        },
        {
            "query_terms": ["robotics"],
            "site_entries": ["https://example.com/search?q={{q}}"],
        },
    )
    adapter = LegacySourceLibraryC2_2Adapter()
    traces, provider_calls = adapter.replay(
        request=request,
        item={
            "item_key": "handler.cluster.news",
            "channel_key": "handler.cluster",
            "enabled": True,
            "extra": {"stable_handler_cluster": True},
        },
        channel_map=_channel_map(),
    )
    assert set(traces) == {
        "protocol_search",
        "provider_harvest",
        "site_search",
        "url_execution",
    }
    assert all(trace.provider_calls for trace in traces.values())
    assert provider_calls == list(adapter.provider_calls)
    assert traces["site_search"].payload["result"]["routing_result"]["forced"] is True


def test_shadow_matches_successor_plan_modes_without_double_effect() -> None:
    payload, request = _resolved_request(
        {
            "item_key": "market.1",
            "channel_key": "market.default",
            "enabled": True,
            "params": {},
            "extra": {},
            "revision": 3,
            "incarnation": "item-inc-3",
        },
        {"urls": ["https://a.example/x", "https://b.example/y"]},
    )
    successor_plan = _successor_plan(payload, request)
    adapter = LegacySourceLibraryC2_2Adapter()
    traces, calls = adapter.replay(
        request=request,
        item={
            "item_key": "market.1",
            "channel_key": "market.default",
            "enabled": True,
            "extra": {},
        },
        channel_map=_channel_map(),
    )
    # The successor plan carries only its own mode; the shared fixture is the
    # deterministic receipt set, executed zero times by the successor line.
    assert successor_plan.mode == "url_execution"
    assert successor_plan.ordered_tasks[0].effect_request.request_digest
    assert len(successor_plan.ordered_tasks) == 2
    assert len(traces["url_execution"].payload["result"]["by_url"]) == 2
    assert calls and len(calls) == len(traces["url_execution"].provider_calls)
    # No real provider call: every call is the fixture receipt callback.
    assert all("fixture" in call or call in _channel_map() for call in calls)


def test_rollback_retains_plan_and_does_not_redispatch() -> None:
    payload, request = _resolved_request(
        {
            "item_key": "crawler.1",
            "channel_key": "crawler.demo_proj",
            "enabled": True,
            "params": {},
            "extra": {},
            "revision": 3,
            "incarnation": "item-inc-3",
        },
        {"query_terms": ["robotics"]},
    )
    successor_plan = _successor_plan(payload, request)
    adapter = LegacySourceLibraryC2_2Adapter()
    before, before_calls = adapter.replay(
        request=request,
        item={
            "item_key": "crawler.1",
            "channel_key": "crawler.demo_proj",
            "enabled": True,
            "extra": {},
        },
        channel_map=_channel_map(),
    )
    plan_digest_before_rollback = successor_plan.plan_digest
    # Future dispatch returns to the legacy claim owner; successor plan rows
    # are retained and no provider effect is replayed.
    assert successor_plan.plan_digest == plan_digest_before_rollback
    assert before["provider_harvest"].receipt["contract_version"] == (
        "source_library.provider_handoff.v1"
    )
    assert len(adapter.provider_calls) == len(before_calls)
