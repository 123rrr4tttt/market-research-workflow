"""Native C1 catalog derives projections and bindings from one authored source."""

from __future__ import annotations

import dataclasses

import pytest
from functorial_kit.contributions import contribution_failures

from app.successor_runtime.capabilities import (
    workflow_native_contribution as workflow_runtime_module,
)
from app.successor_runtime.capabilities.workflow_legacy_dsl import (
    HISTORICAL_C1_DSL_RECEIPT_SCHEMA,
    WORKFLOW_DSL_RECEIPT_SCHEMA,
    WORKFLOW_OPERATION_CATALOG_ID,
    read_workflow_compile_artifact,
    replay_workflow_compile_artifact,
    parse_and_validate_workflow_dsl,
)
from app.successor_runtime.capabilities.workflow_native_contribution import (
    ASSEMBLY_CELL_IDS,
    WORKFLOW_NATIVE_RULE_ID,
    WORKFLOW_NATIVE_VERIFICATION_INPUTS,
    WorkflowAssemblyContext,
    WorkflowNativeSource,
    DEFAULT_WORKFLOW_NATIVE_SOURCE,
    WORKFLOW_DEFINITION_FAILURES,
    compile_workflow_native_contribution,
    advance_workflow_execution_context,
    build_workflow_runtime_definition,
    build_workflow_runtime_program,
    validate_workflow_context_bound_inputs,
)
from functorial_kit.contribution_verification import VerificationChanges
from functorial_kit.core.failure import Failure

from mrw_functorial_kit.contributions import workflow as c1_catalog_module

EXPECTED_WORKFLOW_PROGRAM_DIGEST = (
    "9d59c7f244312015cf98e28519ead5b5048446cf6f2314f89ea65cff4bac06f0"
)
EXPECTED_WORKFLOW_PLAN_DIGEST = (
    "598448169562000b641cf18418011feb93c4559674359ee2968bd2dd0cc977d6"
)
EXPECTED_WORKFLOW_CATALOG_DIGEST = (
    "355c3dc24b7857b3f5ee5c1d03870c47ea3d3c1cfc2e7452c958713d995b91b1"
)
EXPECTED_WORKFLOW_CELL_BINDING_DIGESTS = (
    "e82cd08ee2a9a31e000fe0d3b07e5abe925a764a1116dc62048c40df7cdb0967",
    "1439af714e90de1f79e89ee5ed4c61ede5ff5ffede57381dca2aceb4d70b1ec0",
    "f15a42c0ce59a5c9b1ac47b431194e06dc39de43b41ae4071455159fa0b27a42",
)


def _inert_context() -> WorkflowAssemblyContext:
    from app.successor_runtime.assembly.base import local_assembly_scope_digest

    return WorkflowAssemblyContext(project_scope_digest=local_assembly_scope_digest())


def _compile(source: WorkflowNativeSource):
    native = compile_workflow_native_contribution(source)
    assert not isinstance(native, Failure)
    return native


def test_default_source_compiles_once_and_projects_dsl_authorities() -> None:
    native = c1_catalog_module.workflow_native_contribution
    objects = native.projection.objects
    capabilities = [obj.id for obj in objects if obj.kind == "Capability"]
    assert capabilities == [
        "workflow.vector_search.v1",
        "workflow.llm_call.v1",
        "workflow.join.v1",
    ]
    assert native.projection.id == DEFAULT_WORKFLOW_NATIVE_SOURCE.contribution_id
    assert native.projection.id == "mrw.workflow.definition.native.v2"
    assert native.projection.owner == "workflow.definition.v2"
    assert {obj.owner for obj in objects} == {"workflow.definition.v2"}
    assert native.projection.failures == (
        WORKFLOW_DEFINITION_FAILURES,
        contribution_failures,
    )
    assert WORKFLOW_DEFINITION_FAILURES.name == "workflow.definition.failure"
    assert all(not code.startswith("C1_") for code in WORKFLOW_DEFINITION_FAILURES.codes)
    assert native.verification is not None
    assert native.verification.rule_id == WORKFLOW_NATIVE_RULE_ID
    assert WORKFLOW_NATIVE_RULE_ID == "mrw.workflow.definition.native-rule.v2"
    assert native.verification.inputs == WORKFLOW_NATIVE_VERIFICATION_INPUTS
    assert all(".c1." not in item for item in WORKFLOW_NATIVE_VERIFICATION_INPUTS)
    assert native.verification.complete is True
    assert DEFAULT_WORKFLOW_NATIVE_SOURCE.family_id == "mrw.workflow"
    assert ASSEMBLY_CELL_IDS == (
        "workflow.definition.compile.v2",
        "workflow.runtime.observe.v2",
        "workflow.state.restore.v2",
    )
    assert tuple(cell.cell_id for cell in DEFAULT_WORKFLOW_NATIVE_SOURCE.cells) == ASSEMBLY_CELL_IDS
    runtime_identity_values = (
        DEFAULT_WORKFLOW_NATIVE_SOURCE.interpreter_profile_id,
        DEFAULT_WORKFLOW_NATIVE_SOURCE.deployment_catalog_preimage,
        DEFAULT_WORKFLOW_NATIVE_SOURCE.authority_requirement_preimage,
        *(cell.digest_preimage for cell in DEFAULT_WORKFLOW_NATIVE_SOURCE.cells),
        *(cell.recovery_binding_ref for cell in DEFAULT_WORKFLOW_NATIVE_SOURCE.cells),
        *(cell.kernel_id or "workflow.definition.compile.handler.v2" for cell in DEFAULT_WORKFLOW_NATIVE_SOURCE.cells),
    )
    assert all("successor" not in value and ".c1" not in value for value in runtime_identity_values)


def test_non_default_source_updates_projection_without_duplicating_authority() -> None:
    changed = dataclasses.replace(
        DEFAULT_WORKFLOW_NATIVE_SOURCE,
        contribution_id="test.mrw.c1.native.alt.v1",
        owner="test.c1.owner",
        rollback_refs=("test/rollback/c1-alt.json",),
    )
    native = _compile(changed)
    assert native.projection.id == changed.contribution_id
    assert native.projection.owner == changed.owner
    assert native.verification is not None
    assert (
        native.verification.checks[0].witness.id
        == f"test_workflow_native_definition_law:{changed.contribution_id}"
    )
    binding = native.assemble(_inert_context())
    assert not isinstance(binding, Failure)
    assert binding.receipt is native.definition.receipt
    assert binding.receipt.ok
    assert binding.receipt.catalog_digest == native.definition.catalog.catalog_digest
    assert binding.rollback_binding_refs_by_cell == (
        changed.rollback_refs,
        ("development/latest-dev-docs/development-plans/CURRENT_DEV/"
         "2026-08-30-functorial-successor-migration/evidence/p5-c1-slices/C1SliceA.v1.json",
         "development/latest-dev-docs/development-plans/CURRENT_DEV/"
         "2026-08-30-functorial-successor-migration/evidence/p5-c1-slices/C1SliceB.v1.json",
         "development/latest-dev-docs/development-plans/CURRENT_DEV/"
         "2026-08-30-functorial-successor-migration/evidence/p5-c1-slices/C1SliceC.v1.json",
         "main/backend/app/services/workflow_graph/runtime.py"),
        ("development/latest-dev-docs/development-plans/CURRENT_DEV/"
         "2026-08-30-functorial-successor-migration/evidence/p5-c1-slices/C1SliceA.v1.json",
         "development/latest-dev-docs/development-plans/CURRENT_DEV/"
         "2026-08-30-functorial-successor-migration/evidence/p5-c1-slices/C1SliceB.v1.json",
         "development/latest-dev-docs/development-plans/CURRENT_DEV/"
         "2026-08-30-functorial-successor-migration/evidence/p5-c1-slices/C1SliceC.v1.json",
         "main/backend/app/services/workflow_graph/runtime.py"),
    )


def test_default_catalog_law_and_verification_plan_are_inert_until_run() -> None:
    catalog = c1_catalog_module.workflow_native_catalog
    assert [native.definition.contribution_id for native in catalog] == [
        DEFAULT_WORKFLOW_NATIVE_SOURCE.contribution_id
    ]
    plan = c1_catalog_module.workflow_verification_plan_for()
    assert plan.selection.contribution_ids == (
        DEFAULT_WORKFLOW_NATIVE_SOURCE.contribution_id,
    )
    for witness in c1_catalog_module.workflow_verification_law_witnesses:
        witness.run()
    c1_catalog_module.workflow_law_witnesses[0].run()


def test_unknown_changes_expand_verification_selection_to_full() -> None:
    plan = c1_catalog_module.workflow_verification_plan_for(VerificationChanges(unknown=True))
    assert plan.selection.mode == "full"
    assert "unknown_changes" in plan.selection.reasons
    assert plan.selection.contribution_ids == tuple(
        native.projection.id for native in c1_catalog_module.workflow_native_catalog
    )


def test_catalog_derives_the_existing_c1_operation_catalog_once() -> None:
    native = c1_catalog_module.workflow_native_contribution
    definition = native.definition
    assert definition.catalog.catalog_id == WORKFLOW_OPERATION_CATALOG_ID
    assert definition.receipt.schema == WORKFLOW_DSL_RECEIPT_SCHEMA
    assert definition.receipt.node_count == 3
    assert definition.receipt.edge_count == 2
    assert definition.receipt.topo_order == ("retrieve", "draft", "combine")
    assert definition.receipt.program_digest == EXPECTED_WORKFLOW_PROGRAM_DIGEST
    assert definition.receipt.plan_digest == EXPECTED_WORKFLOW_PLAN_DIGEST
    assert definition.receipt.catalog_digest == EXPECTED_WORKFLOW_CATALOG_DIGEST
    assert definition.catalog.catalog_digest == EXPECTED_WORKFLOW_CATALOG_DIGEST
    assert definition.receipt.provider_calls == 0
    assert definition.receipt.store_writes == 0
    assert definition.receipt.canonical_effect_calls == 0
    assert tuple(
        entry[0] for entry in definition.catalog.entries
    ) == (
        "workflow.vector_search.v1",
        "workflow.llm_call.v1",
        "workflow.join.v1",
    )


def test_failed_dsl_payload_is_rejected_at_lowering_without_speculative_adapter() -> None:
    source = dataclasses.replace(
        DEFAULT_WORKFLOW_NATIVE_SOURCE,
        contribution_id="test.mrw.c1.native.invalid.v1",
        dsl_payload={"version": "1.0", "options": {}, "nodes": [], "edges": []},
    )
    native = compile_workflow_native_contribution(source)
    assert isinstance(native, Failure)


def test_project_catalog_contains_the_workflow_business_catalog() -> None:
    from contributions.project_catalog import project_contribution_catalog

    assert tuple(c1_catalog_module.workflow_contribution_catalog) == tuple(
        item
        for item in project_contribution_catalog
        if item.id.startswith("mrw.workflow.")
    )


def test_changed_c1_rollback_reaches_installed_binding_and_validator() -> None:
    from dataclasses import replace as dc_replace

    from functorial_kit.native_contribution import BindingAccepted

    from app.successor_runtime.capabilities.workflow_native_contribution import (
        validate_workflow_native_binding,
    )

    changed = dataclasses.replace(
        DEFAULT_WORKFLOW_NATIVE_SOURCE,
        contribution_id="test.mrw.c1.native.rollback.v1",
        rollback_refs=("test/rollback/c1-changed.json",),
    )
    native = _compile(changed)
    binding = native.assemble(_inert_context())
    assert not isinstance(binding, Failure)
    assert tuple(
        cell.handler_binding_digest for cell in binding.family_assembly.cells
    ) == EXPECTED_WORKFLOW_CELL_BINDING_DIGESTS
    assert tuple(
        kernel.binding_digest for kernel in binding.family_assembly.kernel_wiring
    ) == EXPECTED_WORKFLOW_CELL_BINDING_DIGESTS[1:]
    installed_rollback = binding.family_assembly.rollback_bindings[0]
    assert installed_rollback.cell_id == ASSEMBLY_CELL_IDS[0]
    assert installed_rollback.binding_refs == changed.rollback_refs
    assert binding.rollback_binding_refs_by_cell[0] == changed.rollback_refs

    tampered_rollback = dc_replace(installed_rollback, binding_refs=("tampered.json",))
    tampered_assembly = dc_replace(
        binding.family_assembly,
        rollback_bindings=(tampered_rollback, *binding.family_assembly.rollback_bindings[1:]),
    )
    rejected = validate_workflow_native_binding(
        native.definition,
        dc_replace(binding, family_assembly=tampered_assembly),
    )
    assert not isinstance(rejected, BindingAccepted)
    assert any(
        issue.path == "$.binding.rollback_bindings.workflow.definition.compile.v2"
        for issue in rejected.issues
    )


def test_historical_compile_read_and_replay_preserve_exact_bytes_and_hash() -> None:
    raw = (
        b'{"schema":"mrw.functorial-successor.c1.legacy-dsl-receipt.v1",'
        b'"program_digest":"historical-byte-identity"}'
    )
    read = read_workflow_compile_artifact(
        schema=HISTORICAL_C1_DSL_RECEIPT_SCHEMA,
        raw_bytes=raw,
    )
    assert read.identity.era == "historical_c1"
    assert read.raw_bytes is raw
    assert replay_workflow_compile_artifact(read) == raw
    assert read.sha256 == __import__("hashlib").sha256(raw).hexdigest()


def test_current_compile_write_and_unknown_versions_are_explicit() -> None:
    current = parse_and_validate_workflow_dsl(DEFAULT_WORKFLOW_NATIVE_SOURCE.dsl_payload)
    assert current.ok
    assert current.schema == WORKFLOW_DSL_RECEIPT_SCHEMA

    wrong_input = {
        **DEFAULT_WORKFLOW_NATIVE_SOURCE.dsl_payload,
        "version": "2.0",
    }
    rejected = parse_and_validate_workflow_dsl(wrong_input)
    assert not rejected.ok
    assert rejected.failure is not None
    assert rejected.failure.path == "version"
    assert "unsupported workflow definition version" in rejected.failure.message

    with __import__("pytest").raises(
        ValueError,
        match="unsupported workflow compile receipt schema",
    ):
        read_workflow_compile_artifact(
            schema="mrw.workflow.definition.compile.receipt.v999",
            raw_bytes=b"{}",
        )


def test_compile_replay_rejects_tampered_bytes() -> None:
    from dataclasses import replace

    original = read_workflow_compile_artifact(
        schema=HISTORICAL_C1_DSL_RECEIPT_SCHEMA,
        raw_bytes=b'{"historical":true}',
    )
    tampered = replace(original, raw_bytes=b'{"historical":false}')
    with __import__("pytest").raises(ValueError, match="hash mismatch"):
        replay_workflow_compile_artifact(tampered)


def test_v2_compile_read_preserves_bytes_after_typed_profile_upgrade() -> None:
    from app.successor_runtime.capabilities.workflow_legacy_dsl import (
        HISTORICAL_WORKFLOW_V2_RECEIPT_SCHEMA,
    )
    raw = b'{"schema":"mrw.workflow.definition.compile.receipt.v2", "original": true}'
    read = read_workflow_compile_artifact(
        schema=HISTORICAL_WORKFLOW_V2_RECEIPT_SCHEMA, raw_bytes=raw,
    )
    assert read.identity.era == "historical_v2"
    assert read.identity.program_schema.endswith(".v2")
    assert read.raw_bytes is raw
    assert replay_workflow_compile_artifact(read) == raw
    assert read.sha256 == __import__("hashlib").sha256(raw).hexdigest()


def test_current_profile_references_identify_versioned_opaque_descriptors() -> None:
    from app.successor_runtime.capabilities.workflow_legacy_dsl import build_workflow_operation_contracts
    from app.successor_runtime.capabilities.checksum import content_digest

    assert WORKFLOW_DSL_RECEIPT_SCHEMA.endswith(".v3")
    for contract in build_workflow_operation_contracts():
        assert contract.ref.contract_version == "2"
        for field in (
            "semantic_profile_ref", "effect_profile_ref", "resource_profile_ref",
            "failure_profile_ref", "authority_profile_ref",
            "interpreter_compatibility_ref", "observation_profile_ref",
        ):
            ref = getattr(contract, field)
            assert ref.profile_id.endswith(".reference-descriptor")
            assert ref.profile_version == "1"
            original = ref.profile_id.removesuffix(".reference-descriptor") + ".v1"
            assert ref.profile_digest == content_digest({
                "schema": "mrw.workflow.profile-reference-descriptor.v1",
                "referenced_profile": original,
            })


def test_compile_artifact_reader_rejects_non_bytes_at_runtime() -> None:
    with __import__("pytest").raises(TypeError, match="raw_bytes must be bytes"):
        read_workflow_compile_artifact(schema=WORKFLOW_DSL_RECEIPT_SCHEMA, raw_bytes="{}")


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
    with pytest.raises(TypeError, match="workflow runtime context JSON shape is invalid"):
        definition.operations[0].context_codec.decode_payload({})
