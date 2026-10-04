"""P3 C2.2 typed contract, profile, planner, program and binding tests."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.successor_runtime.capabilities import source_library_c2_1 as c21
from app.successor_runtime.capabilities import source_library_c2_1_program as c21p
from app.successor_runtime.capabilities import source_library_c2_2 as c22
from app.successor_runtime.capabilities import source_library_c2_2_interpreters as c22i
from app.successor_runtime.capabilities import source_library_c2_2_program as c22p
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.source_library_c2_1 import (
    source_item_definition_content_digest,
)
from app.successor_runtime.capabilities.source_library_c2_1_interpreters import (
    resolve_source_execution_request,
)
from app.successor_runtime.language.program import (
    decode_program_spec,
    encode_program_spec,
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


def _resolve(item: dict[str, Any], params: dict[str, Any]) -> tuple[Any, Any]:
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
    return payload, resolved


def _planning_payload(
    payload: Any,
    resolved: c21.ResolvedResolution,
) -> c22.SourceModePlanningPayload:
    request = resolved.request
    return c22.SourceModePlanningPayload(
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


def _bundle() -> c22.SourceLibraryC2_2CapabilityBundle:
    return c22.build_source_library_c2_2_bundle()


def _catalog() -> Any:
    return c22.build_source_library_c2_2_catalog(_bundle())


def _registry() -> Any:
    return c22.build_source_library_c2_2_registry(_bundle())


def test_c2_2_bundle_registers_four_exact_operations() -> None:
    bundle = _bundle()
    catalog = _catalog()
    registry = _registry()
    kinds = tuple(operation.ref.kind for operation in bundle.operations)
    assert kinds == (
        "source_library.protocol_search.v1",
        "source_library.provider_harvest.v1",
        "source_library.site_search.v1",
        "source_library.url_execution.v1",
    )
    for operation in bundle.operations:
        assert operation.owner_capability_id == "source_library.c2_2.v1"
        assert operation.ref.contract_version == "1.0.0"
        assert catalog.lookup(operation.ref.kind) == operation.ref
        assert registry.resolve_required(operation.ref).ref == operation.ref
    assert bundle.profiles["effect"].execution_class == "PURE_TRANSFORM"
    assert bundle.profiles["effect"].network_required is False
    assert bundle.profiles["authority"].canonical_owner == "source_library.c2_2.v1"
    assert "RESOURCE_CEILING_EXCEEDED" in bundle.profiles["failure"].typed_failures


@pytest.mark.parametrize(
    ("item", "params", "expected_mode", "expected_tasks"),
    [
        (
            {
                "item_key": "market.2",
                "channel_key": "market.default",
                "enabled": True,
                "params": {},
                "extra": {},
                "revision": 3,
                "incarnation": "item-inc-3",
            },
            {"query_terms": ["robotics"]},
            "protocol_search",
            1,
        ),
        (
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
            "provider_harvest",
            1,
        ),
        (
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
            "site_search",
            1,
        ),
        (
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
            "url_execution",
            2,
        ),
    ],
)
def test_four_planners_produce_exact_ordered_mode_plans(
    item: dict[str, Any],
    params: dict[str, Any],
    expected_mode: str,
    expected_tasks: int,
) -> None:
    payload, resolved = _resolve(item, params)
    planning = _planning_payload(payload, resolved)
    c22i.require_exact_planning_binding(planning)
    result = c22i.plan_source_mode(planning)
    assert isinstance(result, c22.PlannedPlanning)
    assert result.plan.mode == expected_mode
    assert len(result.plan.ordered_tasks) == expected_tasks
    assert result.plan.execution_request_digest == planning.execution_request_digest
    assert result.plan.catalog_digest == planning.catalog.digest
    assert result.plan.ordered_fold_policy.fold_kind == (
        "ordered_source_collection_fold.v1"
    )
    if expected_mode in {"provider_harvest", "url_execution"}:
        assert result.plan.terminal_profile.collect_only
    else:
        assert not result.plan.terminal_profile.collect_only
    assert all(task.effect_request.request_digest for task in result.plan.ordered_tasks)


def test_site_search_forces_handler_cluster_and_credentials_are_opaque() -> None:
    payload, resolved = _resolve(
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
    planning = _planning_payload(payload, resolved)
    result = c22i.plan_source_mode(planning)
    assert isinstance(result, c22.PlannedPlanning)
    for task in result.plan.ordered_tasks:
        assert task.effect_request.channel_key == "handler.cluster"
        assert task.effect_request.credential_refs
        for ref in task.effect_request.credential_refs:
            assert ref.ref.startswith("credential:/")
            assert ref.ref == ref.ref.strip()
            assert ref.schema_version == (
                "mrw.successor.source-library.c2-3.credential-ref.v1"
            )


def test_url_execution_preserves_input_order() -> None:
    payload, resolved = _resolve(
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
    planning = _planning_payload(payload, resolved)
    result = c22i.plan_source_mode(planning)
    assert isinstance(result, c22.PlannedPlanning)
    urls = [
        dict(task.effect_request.effect_payload).get("url")
        for task in result.plan.ordered_tasks
    ]
    assert urls == ["https://a.example/x", "https://b.example/y"]
    assert [task.order_index for task in result.plan.ordered_tasks] == [0, 1]


def test_generic_web_direct_execution_is_rejected() -> None:
    payload, resolved = _resolve(
        {
            "item_key": "market.2",
            "channel_key": "market.default",
            "enabled": True,
            "params": {},
            "extra": {},
            "revision": 3,
            "incarnation": "item-inc-3",
        },
        {"query_terms": ["robotics"]},
    )
    # C2.1 rejects generic-web direct execution, so derive a protocol-search
    # request and rebind its channel to generic_web to test the planner gate.
    request = dataclasses.replace(
        resolved.request,
        item_key="generic.1",
        item_channel_key="generic_web.search_template",
    )
    planning = c22.SourceModePlanningPayload(
        schema_version=c22.SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA,
        operation_kind=c22.SOURCE_LIBRARY_C2_2_PROTOCOL_SEARCH_KIND,
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
    assert isinstance(result, c22.RejectedPlanning)
    assert result.code == "FORBIDDEN_INTERNAL_ADAPTER"


def test_url_execution_rebinds_generic_web_and_is_rejected() -> None:
    payload, resolved = _resolve(
        {
            "item_key": "market.2",
            "channel_key": "market.default",
            "enabled": True,
            "params": {},
            "extra": {},
            "revision": 3,
            "incarnation": "item-inc-3",
        },
        {"urls": ["https://a.example/x"]},
    )
    request = dataclasses.replace(
        resolved.request,
        item_key="generic.1",
        item_channel_key="generic_web.search_template",
    )
    planning = c22.SourceModePlanningPayload(
        schema_version=c22.SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA,
        operation_kind=c22.SOURCE_LIBRARY_C2_2_URL_EXECUTION_KIND,
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
    assert isinstance(result, c22.RejectedPlanning)
    assert result.code == "FORBIDDEN_INTERNAL_ADAPTER"


def test_resource_ceiling_rejects_excessive_url_plan() -> None:
    urls = [f"https://example.com/{index}" for index in range(c22.C2_2_MAX_URLS + 1)]
    payload, resolved = _resolve(
        {
            "item_key": "market.1",
            "channel_key": "market.default",
            "enabled": True,
            "params": {},
            "extra": {},
            "revision": 3,
            "incarnation": "item-inc-3",
        },
        {"urls": ["https://example.com/0", "https://example.com/1"]},
    )
    request = dataclasses.replace(
        resolved.request,
        params=c21.NormalizedParamsSnapshot(urls=tuple(urls)),
    )
    planning = _planning_payload(
        payload, dataclasses.replace(resolved, request=request)
    )
    result = c22i.plan_source_mode(planning)
    assert isinstance(result, c22.RejectedPlanning)
    assert result.code == "RESOURCE_CEILING_EXCEEDED"


def test_program_compiles_one_effect_step_and_roundtrips() -> None:
    payload, resolved = _resolve(
        {
            "item_key": "market.2",
            "channel_key": "market.default",
            "enabled": True,
            "params": {},
            "extra": {},
            "revision": 3,
            "incarnation": "item-inc-3",
        },
        {"query_terms": ["robotics"]},
    )
    planning = _planning_payload(payload, resolved)
    program = c22p.build_source_library_c2_2_program(
        payload=planning,
        catalog=_catalog(),
        program_id="p3-c2-2.contracts.program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = c22p.compile_source_library_c2_2_program(
        program, _catalog(), operation_contracts=_registry()
    )
    decoded = decode_program_spec(encode_program_spec(program))
    assert decoded.program_digest == program.program_digest
    effect_steps = [
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    ]
    assert len(effect_steps) == 1
    ref = c22p.planning_payload_value_ref(
        planning,
        program_id="p3-c2-2.contracts.program",
        project_key=PROJECT_KEY,
    )
    metadata = dict(program.metadata)
    assert ref.content_digest == metadata["payload_content_digest"]
    assert ref.provenance_digest == metadata["payload_provenance_digest"]


def test_c2_1_to_c2_2_materialization_is_exact() -> None:
    payload, resolved = _resolve(
        {
            "item_key": "market.2",
            "channel_key": "market.default",
            "enabled": True,
            "params": {},
            "extra": {},
            "revision": 3,
            "incarnation": "item-inc-3",
        },
        {"query_terms": ["robotics"]},
    )
    planning = _planning_payload(payload, resolved)
    c2_1_bundle = c21.build_source_library_c2_1_bundle()
    c2_1_catalog = c21.build_source_library_c2_1_catalog(c2_1_bundle)
    c2_1_registry = c21.build_source_library_c2_1_registry(c2_1_bundle)
    c2_1_program = c21p.build_source_library_c2_1_program(
        payload=payload,
        catalog=c2_1_catalog,
        program_id="p3-c2-2.chain.c2-1",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    c2_1_plan = c21p.compile_source_library_c2_1_program(
        c2_1_program, c2_1_catalog, operation_contracts=c2_1_registry
    )
    c2_1_value_ref = c21p.payload_value_ref(
        payload,
        program_id="p3-c2-2.chain.c2-1",
        project_key=PROJECT_KEY,
    )
    successor_program = c22p.build_source_library_c2_2_program(
        payload=planning,
        catalog=_catalog(),
        program_id="p3-c2-2.chain.c2-2",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    materialization = c22p.build_c2_1_to_c2_2_materialization(
        materialization_id="materialization:p3-c2-2.chain",
        predecessor_run_id="run:p3-c2-2.chain",
        predecessor_step_id="step:p3-c2-2.chain",
        predecessor_plan_digest=c2_1_plan.plan_digest,
        source_value_ref=c2_1_value_ref,
        authority_digest=c22i.successor_planning_interpreter_profile_digest(),
        idempotency_key="idem:p3-c2-2.chain",
        successor_program=successor_program,
    )
    assert materialization.predecessor_plan_digest == c2_1_plan.plan_digest
    assert materialization.successor_program_digest == successor_program.program_digest
    assert materialization.source_value_ref.content_digest == (
        c2_1_value_ref.content_digest
    )


def test_mixed_program_plan_binding_fails_closed() -> None:
    payload, resolved = _resolve(
        {
            "item_key": "market.2",
            "channel_key": "market.default",
            "enabled": True,
            "params": {},
            "extra": {},
            "revision": 3,
            "incarnation": "item-inc-3",
        },
        {"query_terms": ["robotics"]},
    )
    planning = _planning_payload(payload, resolved)
    program_a = c22p.build_source_library_c2_2_program(
        payload=planning,
        catalog=_catalog(),
        program_id="p3-mixed-program-a",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    program_b = c22p.build_source_library_c2_2_program(
        payload=planning,
        catalog=_catalog(),
        program_id="p3-mixed-program-b",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan_a = c22p.compile_source_library_c2_2_program(
        program_a, _catalog(), operation_contracts=_registry()
    )
    plan_b = c22p.compile_source_library_c2_2_program(
        program_b, _catalog(), operation_contracts=_registry()
    )
    assert program_a.program_digest != program_b.program_digest
    assert plan_a.plan_digest != plan_b.plan_digest
    # Both pairs are individually valid.
    c22i.require_exact_planning_binding(planning, program=program_a, plan=plan_a)
    c22i.require_exact_planning_binding(planning, program=program_b, plan=plan_b)
    # Mixed Program A + Plan B must fail closed before any effect.
    with pytest.raises(c22i.PlanningBindingMismatch):
        c22i.require_exact_planning_binding(planning, program=program_a, plan=plan_b)
    outcome = c22i.SourceLibraryC2_2SuccessorInterpreter().interpret(
        planning,
        program=program_a,
        plan=plan_b,
        contract_ref=_catalog().lookup(planning.operation_kind),
        payload_ref=c22p.planning_payload_value_ref(
            planning, program_id="p3-mixed-program-a", project_key=PROJECT_KEY
        ),
        project_scope=planning.project_scope,
        catalog=_catalog(),
        deployment_catalog_digest=content_digest({"deployment": "c2-2"}),
        binding=None,
    )
    assert isinstance(outcome, c22i.InterpreterFailure)
    assert outcome.code == "ASSIGNMENT_BINDING_MISMATCH"


def test_planning_binding_mismatch_fails_closed() -> None:
    payload, resolved = _resolve(
        {
            "item_key": "market.2",
            "channel_key": "market.default",
            "enabled": True,
            "params": {},
            "extra": {},
            "revision": 3,
            "incarnation": "item-inc-3",
        },
        {"query_terms": ["robotics"]},
    )
    planning = _planning_payload(payload, resolved)
    wrong_mode = dataclasses.replace(
        planning,
        operation_kind=c22.SOURCE_LIBRARY_C2_2_SITE_SEARCH_KIND,
        payload_digest="",
    )
    with pytest.raises(c22i.PlanningBindingMismatch):
        c22i.require_exact_planning_binding(wrong_mode)
