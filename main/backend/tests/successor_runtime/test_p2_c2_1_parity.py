"""P2 C2.1 legacy/successor parity, exact binding and rollback observations."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.successor_migration.legacy_source_library import (
    LegacySourceLibraryC2_1Adapter,
    build_legacy_source_library_c2_1_binding,
    build_successor_source_library_c2_1_binding,
)
from app.successor_runtime.capabilities.source_library_c2_1 import (
    AuthenticatedProjectScope,
    RejectedResolution,
    ResolvedResolution,
    SourceResolutionObservation,
    build_channel_catalog_snapshot,
    build_source_library_c2_1_bundle,
    build_source_library_c2_1_catalog,
    build_source_library_c2_1_registry,
    deployment_catalog_digest,
    observations_equal,
    payload_from_dicts,
    project_scope_digest,
    source_item_definition_content_digest,
)
from app.successor_runtime.capabilities.source_library_c2_1_interpreters import (
    InterpreterFailure,
    ResolutionBindingMismatch,
    SourceLibraryC2_1SuccessorInterpreter,
    require_exact_resolution_binding,
    resolve_source_execution_request,
)
from app.successor_runtime.capabilities.source_library_c2_1_program import (
    build_source_library_c2_1_program,
    compile_source_library_c2_1_program,
)

PROJECT_KEY = "demo_proj"
REGISTRY_REVISION = 5
RESOLVED_SCHEMA = "mrw_p_demo_proj"
SCOPE_INCARNATION = "scope-inc-5"
SCOPE_DIGEST = project_scope_digest(
    PROJECT_KEY, RESOLVED_SCHEMA, REGISTRY_REVISION, SCOPE_INCARNATION
)
ITEM_REVISION = 3
ITEM_INCARNATION = "item-inc-3"
DEPLOYMENT_CATALOG_DIGEST = deployment_catalog_digest()


def _bundle():
    return build_source_library_c2_1_bundle()


def _catalog():
    return build_source_library_c2_1_catalog(_bundle())


def _registry():
    return build_source_library_c2_1_registry(_bundle())


def _channels():
    return [
        {
            "channel_key": "handler.cluster",
            "provider_type": "native",
            "enabled": True,
        },
        {
            "channel_key": "generic_web.search_template",
            "provider": "generic_web",
            "provider_type": "native",
            "enabled": True,
        },
        {
            "channel_key": "crawler.demo_proj",
            "provider_type": "scrapy",
            "enabled": True,
        },
        {"channel_key": "market.default", "provider_type": "native", "enabled": True},
    ]


def _item(**overrides):
    values = {
        "item_key": "handler.cluster.news",
        "channel_key": "handler.cluster",
        "enabled": True,
        "params": {"keywords": ["robotics"], "limit": 9},
        "extra": {
            "stable_handler_cluster": True,
            "expected_entry_type": "search_template",
        },
        "revision": ITEM_REVISION,
        "incarnation": ITEM_INCARNATION,
    }
    values.update(overrides)
    values.setdefault("content_digest", source_item_definition_content_digest(values))
    return values


def _payload(**overrides):
    values = {
        "project_key": PROJECT_KEY,
        "registry_revision": REGISTRY_REVISION,
        "resolved_schema": RESOLVED_SCHEMA,
        "scope_incarnation": SCOPE_INCARNATION,
        "scope_digest": SCOPE_DIGEST,
        "channels": _channels(),
        "item": _item(),
        "params": {
            "query_terms": ["x"],
            "site_entries": ["https://example.com/search?q={{q}}"],
        },
    }
    values.update(overrides)
    if "item" in overrides:
        values["item"] = _item(**overrides["item"])
    return payload_from_dicts(**values)


def _program(payload, program_id="c2-1.parity.program"):
    return build_source_library_c2_1_program(
        payload=payload,
        catalog=_catalog(),
        program_id=program_id,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )


def _plan(program):
    return compile_source_library_c2_1_program(
        program, _catalog(), operation_contracts=_registry()
    )


def _bindings():
    bundle = _bundle()
    legacy = build_legacy_source_library_c2_1_binding(
        contract_digest=bundle.operation.ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    successor = build_successor_source_library_c2_1_binding(
        contract_digest=bundle.operation.ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    return legacy, successor


def _closure(payload):
    program = _program(payload)
    plan = _plan(program)
    ref = program.root.operation.contract_ref
    payload_ref = program.root.operation.payload_ref
    return program, plan, ref, payload_ref


def _run_successor(payload, program, plan, ref, payload_ref, binding):
    return SourceLibraryC2_1SuccessorInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=payload.project_scope,
        catalog=_catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=binding,
    )


def _run_legacy(payload, program, plan, ref, payload_ref, binding):
    return LegacySourceLibraryC2_1Adapter().resolve(
        payload=payload,
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        project_scope=payload.project_scope,
        catalog=_catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=binding,
    )


def test_legacy_trace_replay_is_deterministic() -> None:
    payload = _payload()
    adapter = LegacySourceLibraryC2_1Adapter()
    first = adapter._trace(payload, trace_id="trace-1")
    second = adapter._trace(payload, trace_id="trace-2")
    assert first.normalized_params == second.normalized_params
    assert first.source_mode == second.source_mode
    assert first.taxonomy == second.taxonomy
    assert first.warnings == second.warnings
    assert first.protocol == second.protocol
    assert first.trace_digest != second.trace_digest
    assert adapter.resolves == 0  # trace never dispatches effects


@pytest.mark.parametrize(
    "item,params",
    [
        (
            _item(extra={"stable_handler_cluster": True}),
            {
                "site_entries": ["https://example.com/search"],
                "source_mode": "site_search",
            },
        ),
        (
            _item(item_key="report.urls", channel_key="market.default"),
            {"urls": ["https://example.com/a"], "source_mode": "site_search"},
        ),
        (
            _item(item_key="crawler.item", channel_key="crawler.demo_proj"),
            {},
        ),
        (
            _item(
                item_key="generic_web.internal",
                channel_key="generic_web.search_template",
                item_type="service_aggregated",
                managed_by="system",
            ),
            {"query_terms": ["robotics"]},
        ),
    ],
)
def test_same_program_legacy_successor_parity(item, params) -> None:
    payload = _payload(item=item, params=params)
    program, plan, ref, payload_ref = _closure(payload)
    legacy_binding, successor_binding = _bindings()

    successor = _run_successor(
        payload, program, plan, ref, payload_ref, successor_binding
    )
    legacy = _run_legacy(payload, program, plan, ref, payload_ref, legacy_binding)
    assert not isinstance(successor, InterpreterFailure)
    assert not isinstance(legacy, InterpreterFailure)
    successor_value = successor.value
    legacy_value = legacy.value
    assert isinstance(successor_value, ResolvedResolution)
    assert isinstance(legacy_value, ResolvedResolution)
    assert successor_value.request == legacy_value.request
    assert successor_value.observation_digest == legacy_value.observation_digest
    assert [
        (warning.code, warning.ordered_payload)
        for warning in successor_value.request.warnings
    ] == [
        (warning.code, warning.ordered_payload)
        for warning in legacy_value.request.warnings
    ]


def test_payload_mutation_rejects_exact_binding() -> None:
    original = _payload()
    program, plan, ref, payload_ref = _closure(original)
    mutated = replace(
        original,
        item=replace(original.item, item_key="mutated.item", content_digest=""),
        payload_digest="",
    )
    _, successor_binding = _bindings()
    with pytest.raises(ResolutionBindingMismatch, match="payload ref content digest"):
        require_exact_resolution_binding(
            program=program,
            plan=plan,
            contract_ref=ref,
            payload_ref=payload_ref,
            payload=mutated,
            project_scope=original.project_scope,
            catalog=_catalog(),
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            binding=successor_binding,
        )
    failure = _run_successor(
        mutated, program, plan, ref, payload_ref, successor_binding
    )
    assert isinstance(failure, InterpreterFailure)
    assert failure.code == "ASSIGNMENT_BINDING_MISMATCH"


def test_catalog_drift_rejects() -> None:
    original = _payload()
    program, plan, ref, payload_ref = _closure(original)
    drifted = replace(
        original,
        catalog=build_channel_catalog_snapshot(
            revision=original.catalog.revision + 1,
            incarnation=original.catalog.incarnation,
            entries=original.catalog.entries,
        ),
        payload_digest="",
    )
    legacy_binding, _ = _bindings()
    with pytest.raises(ResolutionBindingMismatch, match="program metadata/catalog"):
        require_exact_resolution_binding(
            program=program,
            plan=plan,
            contract_ref=ref,
            payload_ref=payload_ref,
            payload=drifted,
            project_scope=original.project_scope,
            catalog=_catalog(),
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            binding=legacy_binding,
        )


def test_project_scope_drift_rejects() -> None:
    payload = _payload()
    program, plan, ref, payload_ref = _closure(payload)
    _, successor_binding = _bindings()
    drifted_scope = AuthenticatedProjectScope(
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=RESOLVED_SCHEMA,
        incarnation="scope-inc-drift",
        scope_digest="",
    )
    with pytest.raises(ResolutionBindingMismatch, match="scope digest"):
        require_exact_resolution_binding(
            program=program,
            plan=plan,
            contract_ref=ref,
            payload_ref=payload_ref,
            payload=payload,
            project_scope=drifted_scope,
            catalog=_catalog(),
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            binding=successor_binding,
        )


def test_project_scope_incarnation_drift_rejects_aba() -> None:
    original = _payload()
    program, plan, ref, payload_ref = _closure(original)
    _, successor_binding = _bindings()
    swapped = replace(
        original,
        project_scope=AuthenticatedProjectScope(
            project_key=PROJECT_KEY,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=RESOLVED_SCHEMA,
            incarnation="scope-inc-swap",
            scope_digest="",
        ),
        payload_digest="",
    )
    with pytest.raises(ResolutionBindingMismatch, match="scope incarnation"):
        require_exact_resolution_binding(
            program=program,
            plan=plan,
            contract_ref=ref,
            payload_ref=payload_ref,
            payload=swapped,
            project_scope=swapped.project_scope,
            catalog=_catalog(),
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            binding=successor_binding,
        )


def test_forged_plan_digest_is_rejected() -> None:
    payload = _payload()
    program, plan, ref, payload_ref = _closure(payload)
    _, successor_binding = _bindings()
    forged = replace(plan, plan_digest="0" * 64)
    with pytest.raises(ResolutionBindingMismatch, match="plan digest forged"):
        require_exact_resolution_binding(
            program=program,
            plan=forged,
            contract_ref=ref,
            payload_ref=payload_ref,
            payload=payload,
            project_scope=payload.project_scope,
            catalog=_catalog(),
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            binding=successor_binding,
        )
    failure = _run_successor(
        payload, program, forged, ref, payload_ref, successor_binding
    )
    assert isinstance(failure, InterpreterFailure)
    assert failure.code == "ASSIGNMENT_BINDING_MISMATCH"


def test_deployment_catalog_digest_swap_is_rejected() -> None:
    payload = _payload()
    program, plan, ref, payload_ref = _closure(payload)
    legacy_binding, successor_binding = _bindings()
    assert DEPLOYMENT_CATALOG_DIGEST != _catalog().catalog_digest
    swapped = "2" * 64
    with pytest.raises(
        ResolutionBindingMismatch, match="binding/deployment catalog digest"
    ):
        require_exact_resolution_binding(
            program=program,
            plan=plan,
            contract_ref=ref,
            payload_ref=payload_ref,
            payload=payload,
            project_scope=payload.project_scope,
            catalog=_catalog(),
            deployment_catalog_digest=swapped,
            binding=successor_binding,
        )
    failure = SourceLibraryC2_1SuccessorInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=payload.project_scope,
        catalog=_catalog(),
        deployment_catalog_digest=swapped,
        binding=successor_binding,
    )
    assert isinstance(failure, InterpreterFailure)
    assert failure.code == "ASSIGNMENT_BINDING_MISMATCH"
    legacy_failure = LegacySourceLibraryC2_1Adapter().resolve(
        payload=payload,
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        project_scope=payload.project_scope,
        catalog=_catalog(),
        deployment_catalog_digest=swapped,
        binding=legacy_binding,
    )
    assert isinstance(legacy_failure, InterpreterFailure)
    assert legacy_failure.code == "ASSIGNMENT_BINDING_MISMATCH"


def test_legacy_unbound_resolve_is_rejected() -> None:
    payload = _payload()
    adapter = LegacySourceLibraryC2_1Adapter()
    with pytest.raises(TypeError):
        adapter.resolve(payload=payload)  # type: ignore[call-arg]


def test_exact_bindings_are_distinct_and_cross_rejected() -> None:
    from app.successor_migration.legacy_source_library import bindings_are_distinct

    legacy_binding, successor_binding = _bindings()
    assert bindings_are_distinct(legacy_binding, successor_binding)
    assert (
        legacy_binding.operation_contract_digest
        == successor_binding.operation_contract_digest
    )

    payload = _payload()
    program, plan, ref, payload_ref = _closure(payload)
    legacy_with_successor_binding = _run_legacy(
        payload, program, plan, ref, payload_ref, successor_binding
    )
    assert isinstance(legacy_with_successor_binding, InterpreterFailure)
    assert legacy_with_successor_binding.code == "ASSIGNMENT_BINDING_MISMATCH"
    successor_with_legacy_binding = _run_successor(
        payload, program, plan, ref, payload_ref, legacy_binding
    )
    assert isinstance(successor_with_legacy_binding, InterpreterFailure)
    assert successor_with_legacy_binding.code == "ASSIGNMENT_BINDING_MISMATCH"


def test_rollback_changes_future_selection_without_downstream_replay() -> None:
    payload = _payload()
    program, plan, ref, payload_ref = _closure(payload)
    legacy_binding, successor_binding = _bindings()
    downstream_calls: list[str] = []

    def downstream_effect(label: str) -> None:
        downstream_calls.append(label)

    journal: list[str] = []
    first = _run_successor(payload, program, plan, ref, payload_ref, successor_binding)
    assert not isinstance(first, InterpreterFailure)
    journal.append(first.value.observation_digest)
    downstream_effect("successor")

    future_selection = "legacy"
    if future_selection == "legacy":
        rollback = _run_legacy(payload, program, plan, ref, payload_ref, legacy_binding)
    else:
        rollback = first
    assert not isinstance(rollback, InterpreterFailure)

    assert downstream_calls == ["successor"]
    assert journal == [first.value.observation_digest]
    assert rollback.value.observation_digest == first.value.observation_digest
    assert rollback.value.request == first.value.request


def test_generic_web_direct_rejection_is_parity() -> None:
    item = _item(
        item_key="generic_web.demo",
        channel_key="generic_web.search_template",
        item_type="user_defined",
        managed_by="user",
    )
    payload = _payload(item=item, params={"query_terms": ["robotics"]})
    program, plan, ref, payload_ref = _closure(payload)
    legacy_binding, successor_binding = _bindings()
    successor = _run_successor(
        payload, program, plan, ref, payload_ref, successor_binding
    )
    legacy = _run_legacy(payload, program, plan, ref, payload_ref, legacy_binding)
    assert isinstance(successor.value, RejectedResolution)
    assert isinstance(legacy.value, RejectedResolution)
    assert successor.value.rejection == legacy.value.rejection


def test_generic_web_raw_flag_never_authorizes_parity() -> None:
    item = _item(
        item_key="generic_web.demo.flag",
        channel_key="generic_web.search_template",
        item_type="user_defined",
        managed_by="user",
    )
    payload = _payload(
        item=item,
        params={"query_terms": ["robotics"], "_allow_internal_generic_web": True},
    )
    program, plan, ref, payload_ref = _closure(payload)
    legacy_binding, successor_binding = _bindings()
    successor = _run_successor(
        payload, program, plan, ref, payload_ref, successor_binding
    )
    legacy = _run_legacy(payload, program, plan, ref, payload_ref, legacy_binding)
    assert isinstance(successor.value, RejectedResolution)
    assert isinstance(legacy.value, RejectedResolution)
    assert successor.value.rejection == legacy.value.rejection
    assert successor.value.rejection.code == "FORBIDDEN_INTERNAL_ADAPTER"


def test_observation_equality_requires_exact_profile_and_identities() -> None:
    payload = _payload()
    resolved = resolve_source_execution_request(payload)
    assert isinstance(resolved, ResolvedResolution)
    request = resolved.request
    kwargs = {
        "project_scope": request.project_scope,
        "item_revision": request.item_revision,
        "item_incarnation": request.item_incarnation,
        "item_content_digest": request.item_content_digest,
        "catalog_revision": request.catalog_revision,
        "catalog_incarnation": request.catalog_incarnation,
        "catalog_digest": request.catalog_digest,
        "normalized_params": request.params,
        "source_mode": request.source_mode,
        "taxonomy": request.taxonomy,
        "warnings": request.warnings,
        "protocol": request.protocol,
        "observation_digest": "",
    }
    observation = SourceResolutionObservation(
        observation_profile="mrw.successor.source-library.c2-1.observation.v1",
        **kwargs,
    )
    relabeled = SourceResolutionObservation(
        observation_profile="other.profile.ref",
        **kwargs,
    )
    assert not observations_equal(observation, relabeled)

    changed_protocol = replace(
        request.protocol, candidate_urls=("https://example.com/changed",)
    )
    different_protocol = SourceResolutionObservation(
        observation_profile=observation.observation_profile,
        **{**kwargs, "protocol": changed_protocol},
    )
    assert not observations_equal(observation, different_protocol)

    changed_item = replace(request, item_incarnation="item-inc-swap")
    different_item = SourceResolutionObservation(
        observation_profile=observation.observation_profile,
        **{
            **kwargs,
            "item_revision": changed_item.item_revision,
            "item_incarnation": changed_item.item_incarnation,
            "item_content_digest": changed_item.item_content_digest,
        },
    )
    assert not observations_equal(observation, different_item)
    assert observations_equal(observation, observation)
