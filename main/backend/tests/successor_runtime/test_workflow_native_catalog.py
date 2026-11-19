"""Installed operation and workflow runtime contracts."""

from __future__ import annotations

import dataclasses
from typing import cast

import pytest
from functorial_kit.contributions import contribution_failures
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import BindingAccepted, BindingRejected

from app.successor_runtime.capabilities import (
    workflow_native_contribution as workflow_runtime_module,
)
from app.successor_runtime.capabilities.workflow_native_contribution import (
    advance_workflow_execution_context,
    build_workflow_runtime_definition,
    build_workflow_runtime_program,
    validate_workflow_context_bound_inputs,
)
from app.composition.installed_operation import (
    Dispatch,
    InstalledOperationContext,
    installed_operation_catalog,
    installed_operation_contribution_catalog,
    installed_operation_for_ref,
    validate_installed_operation,
    url_installed_operations,
    workflow_installed_operation_catalog,
    workflow_installed_operations,
)


def test_installed_url_catalog_resolves_both_legacy_and_current_exact_refs() -> None:
    from app.successor_runtime.capabilities import acquisition_url as url

    legacy, readback_legacy, current = url.build_url_single_url_contracts()
    assert tuple(
        item.definition.contract.ref for item in url_installed_operations
    ) == (legacy.ref, readback_legacy.ref, current.ref)
    assert (
        installed_operation_for_ref(installed_operation_catalog, legacy.ref)
        is url_installed_operations[0]
    )
    assert (
        installed_operation_for_ref(installed_operation_catalog, readback_legacy.ref)
        is url_installed_operations[1]
    )
    assert (
        installed_operation_for_ref(installed_operation_catalog, current.ref)
        is url_installed_operations[2]
    )
    drifted = dataclasses.replace(current.ref, contract_digest="0" * 64)
    with pytest.raises(ValueError, match="operation ref drift"):
        installed_operation_for_ref(installed_operation_catalog, drifted)


def test_historical_url_installations_are_exact_readers_without_effect_handlers() -> None:
    from app.successor_runtime.capabilities import acquisition_url as url

    legacy, readback_legacy, current = url.build_url_single_url_contracts()
    for installed, contract in zip(
        url_installed_operations[:2],
        (legacy, readback_legacy),
        strict=True,
    ):
        assert installed.definition.input_codec.contract_ref == contract.ref
        assert installed.definition.input_codec.codec_version == "1"
        assert installed.definition.output_codec.contract_ref == contract.ref
        assert installed.definition.output_codec.codec_version == "1"
        result = installed.assemble(cast(InstalledOperationContext, object()))
        assert isinstance(result, Failure)
        assert result.code == "HISTORICAL_OPERATION_READ_ONLY"

    current_installed = url_installed_operations[2]
    assert current_installed.definition.contract.ref == current.ref
    assert current_installed.definition.input_codec.codec_version == "2"
    assert current_installed.definition.output_codec.codec_version == "2"


def test_workflow_native_catalog_is_the_effective_project_projection() -> None:
    from contributions.project_catalog import project_contribution_catalog

    definition = build_workflow_runtime_definition()
    assert tuple(
        (
            native.definition.source.node_type,
            native.definition.contract,
            native.definition.profiles,
        )
        for native in workflow_installed_operations
    ) == tuple(
        (item.node_type, item.contract, item.profiles) for item in definition.operations
    )
    assert all(
        native.definition.source is item
        for native, item in zip(
            workflow_installed_operation_catalog(definition),
            definition.operations,
            strict=True,
        )
    )
    assert installed_operation_contribution_catalog == tuple(
        native.projection for native in installed_operation_catalog
    )
    assert all(
        native.projection in project_contribution_catalog
        for native in workflow_installed_operations
    )
    operation = definition.operations[0]
    drifted = dataclasses.replace(operation.contract.ref, contract_digest="0" * 64)
    with pytest.raises(ValueError, match="operation ref drift"):
        installed_operation_for_ref(workflow_installed_operations, drifted)


def test_workflow_runtime_resource_profiles_use_installable_classes() -> None:
    from app.successor_runtime.runtime.resources import ResourceClass

    expected = {
        "vector_search": ResourceClass.NETWORK_IO,
        "llm_call": ResourceClass.NETWORK_IO,
        "join": ResourceClass.CPU_LIGHT,
    }
    definition = build_workflow_runtime_definition()
    assert {operation.node_type for operation in definition.operations} == set(expected)
    for operation in definition.operations:
        resource_classes = operation.profiles.resource.resource_classes
        assert len(resource_classes) == 1
        assert ResourceClass(resource_classes[0]) is expected[operation.node_type]
        assert operation.profiles.effect.network_required is (
            expected[operation.node_type] is ResourceClass.NETWORK_IO
        )

def test_runtime_program_uses_real_profiles_exact_bytes_and_unique_occurrences() -> None:
    definition = build_workflow_runtime_definition()
    runtime = build_workflow_runtime_program(
        workflow_id="graph-1",
        nodes=(
            {
                "node_id": "search",
                "node_type": "vector_search",
                "params": {"top_k": 3},
                "depends_on": [],
            },
            {
                "node_id": "draft",
                "node_type": "llm_call",
                "params": {"prompt": "$node.search"},
                "depends_on": ["search"],
            },
            {
                "node_id": "combine",
                "node_type": "join",
                "params": {},
                "depends_on": ["search", "draft"],
            },
        ),
        topo_order=("search", "draft", "combine"),
        inputs={"query": "water"},
        program_id="workflow:graph-1:run-1",
        project_key="project-1",
        project_registry_revision=7,
        project_scope_digest="a" * 64,
        incarnation="incarnation-1",
        trace_id="trace-1",
    )

    assert runtime.program.contract_version == "mrw.workflow.runtime.program.v1"
    assert runtime.operation_ids == (
        "workflow-node:0:search",
        "workflow-node:1:draft",
        "workflow-node:2:combine",
    )
    assert len(set(ref.content_digest for ref, _ in runtime.values)) == 3
    assert all(ref.byte_size == len(exact) for ref, exact in runtime.values)
    assert all(
        operation.contract.semantic_profile_ref == operation.profiles.semantic.ref
        and operation.contract.effect_profile_ref == operation.profiles.effect.ref
        and operation.contract.resource_profile_ref == operation.profiles.resource.ref
        and operation.contract.failure_profile_ref == operation.profiles.failure.ref
        and operation.contract.authority_profile_ref == operation.profiles.authority.ref
        and operation.contract.interpreter_compatibility_ref
        == operation.profiles.interpreter.ref
        for operation in definition.operations
    )

    first_operation = definition.operation_for_node_type("vector_search")
    first_ref, first_exact = runtime.values[0]
    first_context = first_operation.context_codec.decode_payload(
        __import__("json").loads(first_exact)
    )
    validate_workflow_context_bound_inputs(
        first_context,
        ((first_ref, first_exact),),
        operation=first_operation,
    )
    advanced = advance_workflow_execution_context(
        first_context,
        node_id="search",
        result={"items": ["a"]},
    )
    second_operation = definition.operation_for_node_type("llm_call")
    second_ref, second_exact = runtime.values[1]
    validate_workflow_context_bound_inputs(
        advanced,
        ((second_ref, second_exact),),
        operation=second_operation,
    )
    assert advanced.cursor == 1
    assert advanced.results == {"search": {"items": ["a"]}}

def test_workflow_runtime_validation_uses_typed_failure_lift() -> None:
    failure = workflow_runtime_module._workflow_runtime_failure(
        workflow_runtime_module.WORKFLOW_PROGRAM_PLAN_BINDING_INVALID,
        "workflow runtime test rejection",
        site="test_workflow_runtime_validation",
    )
    assert failure.family == "workflow.definition.failure"
    assert failure.code == "WORKFLOW_PROGRAM_PLAN_BINDING_INVALID"
    assert failure.context is not None
    assert failure.context["public_exception"] == "ValueError"

    with pytest.raises(ValueError, match="^workflow runtime test rejection$"):
        workflow_runtime_module._raise_workflow_runtime_failure(failure)
    malformed_failure = contribution_failures.fail(
        "CONTRIBUTION_INVALID",
        "not a workflow runtime failure",
        {},
    )
    with pytest.raises(TypeError, match="workflow runtime failure lift context is incomplete"):
        workflow_runtime_module._raise_workflow_runtime_failure(malformed_failure)

    definition = build_workflow_runtime_definition()
    with pytest.raises(ValueError, match="unsupported workflow runtime node type"):
        definition.operation_for_node_type("unsupported")
    kinds = dict(workflow_runtime_module.WORKFLOW_RUNTIME_NODE_KINDS)
    for invalid in (
        {"join": kinds["join"]},
        {**kinds, "join": kinds["llm_call"]},
        {**kinds, "join": ""},
        {**kinds, "unsupported": "workflow.runtime.unsupported.v1"},
    ):
        with pytest.raises(ValueError, match="operation kinds are invalid"):
            build_workflow_runtime_definition(invalid)
    operation = definition.operation_for_node_type("join")
    for invalid_ref in (
        dataclasses.replace(operation.contract.ref, contract_version="wrong"),
        dataclasses.replace(operation.contract.ref, contract_digest="0" * 64),
    ):
        with pytest.raises(ValueError, match="operation ref drift"):
            definition.operation_for_ref(invalid_ref)
    with pytest.raises(TypeError, match="workflow runtime context JSON shape is invalid"):
        definition.operations[0].context_codec.decode_payload({})

def test_runtime_handler_assembly_rejects_drift_without_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    from importlib import import_module
    from types import SimpleNamespace
    from typing import cast

    from sqlalchemy.engine import Engine

    from app.successor_runtime.assembly.base import runtime_binding
    from app.successor_runtime.assembly.workflow_assembly import assemble_workflow_runtime_handler
    from app.successor_runtime.capabilities.batch_business import BrokerBusinessReadback
    from app.successor_runtime.capabilities.codecs import dataclass_codec
    from app.successor_runtime.research.object_types import ObjectType
    from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
    from app.successor_runtime.substrate.postgres.runtime_activation import (
        ActivationCatalogEntry,
    )

    workflow_kernel = import_module("app.services.workflow_graph.runtime")
    node_adapter = import_module(
        "app.successor_runtime.substrate.postgres.node_adapter"
    )
    definition = build_workflow_runtime_definition()
    operation = definition.operation_for_node_type("join")
    other = definition.operation_for_node_type("llm_call")
    contract, profiles, codec = operation.contract, operation.profiles, operation.context_codec
    binding = runtime_binding(
        operation_contract_digest=contract.ref.contract_digest,
        interpreter_profile_digest=profiles.interpreter.ref.profile_digest,
        deployment_catalog_digest="a" * 64, project_scope_digest="b" * 64, resource_policy_epoch=1,
        authority_requirement_digest=profiles.authority.ref.profile_digest, runtime_protocol_version="1",
    )
    calls: list[object] = []
    monkeypatch.setattr(workflow_kernel, "invoke_workflow_runtime_node", lambda value: calls.append(value))

    def assemble_with(
        candidate: workflow_runtime_module.WorkflowRuntimeOperationDefinition,
        operation_binding,
    ):
        return assemble_workflow_runtime_handler(
            operation=candidate, uow_factory=lambda: (_ for _ in ()).throw(AssertionError("UoW opened")),
            binding=operation_binding, project_key="project-1", resolved_schema="project_1",
            bind_project_scope=import_module("app.services.projects.context").bind_resolved_project,
            invoke_runtime_node=workflow_kernel.invoke_workflow_runtime_node,
            settled_failure_type=workflow_kernel.WorkflowNodeSettledFailure,
        )

    def assemble(candidate):
        return assemble_with(candidate, binding)

    join_native = installed_operation_for_ref(
        workflow_installed_operation_catalog(definition), contract.ref,
    )
    assert join_native is not None
    monkeypatch.setattr(
        node_adapter,
        "runtime_uow_factory",
        lambda _engine: lambda: (_ for _ in ()).throw(AssertionError("UoW opened")),
    )
    scope = RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key="project-1",
            resolved_schema="project_1",
            project_registry_revision=1,
            incarnation="test",
            scope_digest="b" * 64,
        ),
        actor_id="actor-1",
    )
    factory_handler = join_native.assemble((
        cast(Engine, object()),
        scope,
        cast(ActivationCatalogEntry, SimpleNamespace(interpreter_binding=binding)),
        cast(Dispatch, lambda _payload: None),
        cast(BrokerBusinessReadback, object()),
    ))
    assert not isinstance(factory_handler, Failure)
    assert factory_handler.contract == contract
    assert calls == []
    accepted = validate_installed_operation(join_native.definition, factory_handler)
    assert isinstance(accepted, BindingAccepted)
    other_binding = runtime_binding(
        operation_contract_digest=other.contract.ref.contract_digest,
        interpreter_profile_digest=other.profiles.interpreter.ref.profile_digest,
        deployment_catalog_digest="a" * 64, project_scope_digest="b" * 64, resource_policy_epoch=1,
        authority_requirement_digest=other.profiles.authority.ref.profile_digest, runtime_protocol_version="1",
    )
    cross_definition = validate_installed_operation(
        join_native.definition, assemble_with(other, other_binding),
    )
    assert isinstance(cross_definition, BindingRejected)
    wrong_profile_binding = runtime_binding(
        operation_contract_digest=contract.ref.contract_digest,
        interpreter_profile_digest=other.profiles.interpreter.ref.profile_digest,
        deployment_catalog_digest="a" * 64, project_scope_digest="b" * 64, resource_policy_epoch=1,
        authority_requirement_digest=profiles.authority.ref.profile_digest, runtime_protocol_version="1",
    )
    wrong_profile = validate_installed_operation(
        join_native.definition, assemble_with(operation, wrong_profile_binding),
    )
    assert isinstance(wrong_profile, BindingRejected)
    wrong_authority_binding = runtime_binding(
        operation_contract_digest=contract.ref.contract_digest,
        interpreter_profile_digest=profiles.interpreter.ref.profile_digest,
        deployment_catalog_digest="a" * 64, project_scope_digest="b" * 64, resource_policy_epoch=1,
        authority_requirement_digest="0" * 64, runtime_protocol_version="1",
    )
    wrong_authority = validate_installed_operation(
        join_native.definition, assemble_with(operation, wrong_authority_binding),
    )
    assert isinstance(wrong_authority, BindingRejected)
    equivalent_codec = dataclasses.replace(codec)
    assert equivalent_codec == codec and equivalent_codec is not codec
    codec_identity_drift = validate_installed_operation(
        join_native.definition,
        assemble(dataclasses.replace(operation, context_codec=equivalent_codec)),
    )
    assert isinstance(codec_identity_drift, BindingRejected)
    wrong_type = ObjectType("WrongWorkflowContext.v1", codec_id=codec.codec_id)

    def rebound_operation(
        *, input_type: ObjectType = contract.input_type,
        output_type: ObjectType = contract.output_type,
        owner: str = contract.owner_capability_id,
    ) -> workflow_runtime_module.WorkflowRuntimeOperationDefinition:
        rebound = profiles.contract(
            kind=contract.ref.kind, contract_version=contract.ref.contract_version,
            input_type=input_type, output_type=output_type,
            return_contract_ref=contract.return_contract_ref,
            allowed_override_schema_ref=contract.allowed_override_schema_ref,
            owner_capability_id=owner,
        )
        return dataclasses.replace(
            operation, contract=rebound,
            context_codec=dataclasses.replace(codec, contract_ref=rebound.ref),
        )

    wrong_codec = dataclass_codec(
        codec_id=codec.codec_id, codec_version=codec.codec_version, contract_ref=contract.ref,
        payload_type_id=wrong_type.type_id, dto_cls=workflow_runtime_module.WorkflowExecutionContext)
    invalid_operations = (
        rebound_operation(input_type=wrong_type),
        rebound_operation(output_type=wrong_type),
        dataclasses.replace(operation, context_codec=wrong_codec),
        dataclasses.replace(operation, context_codec=other.context_codec),
        rebound_operation(owner="wrong.workflow.owner"),
        dataclasses.replace(operation, profiles=dataclasses.replace(profiles, authority=other.profiles.authority)),
    )
    for invalid in invalid_operations:
        with pytest.raises(ValueError, match="operation binding drift"):
            assemble(invalid)
