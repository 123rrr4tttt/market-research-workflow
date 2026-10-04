"""Task observation native catalog and offline family binding tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.successor_runtime.assembly.base import (
    ProjectorSourceKey,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.task_observation_assembly import (
    PROCESS_OBSERVATION_CELL_ID,
    RUN_OBSERVATION_CELL_ID,
    SESSION_OBSERVATION_CELL_ID,
    TASK_EFFECT_RECONCILE_CELL_ID,
    TASK_OBSERVATION_FAMILY_ID,
    ProcessLineEventReadbackRouteHandler,
    TaskEffectReconcileRouteHandler,
    build_task_observation_assembly,
)
from app.successor_runtime.runtime.task_observation_native_contribution import (
    ASSEMBLY_CELL_IDS,
    DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE,
    NON_DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE,
    TaskObservationAssemblyContext,
    TaskObservationAssemblyOptions,
    compile_task_observation_native_contribution,
)
from app.successor_runtime.runtime.process_observation import (
    try_join_process_observations,
)
from app.successor_runtime.runtime.reconciliation import EffectReconciler
from app.successor_runtime.substrate.projections.agent_session import (
    PostgresAgentSessionReadAdapter,
)
from app.successor_runtime.substrate.projections.legacy_process import (
    LINE_EVENT_READBACK_PROJECTOR_REF,
    project_line_event_readbacks,
)
from app.successor_runtime.substrate.projections.runtime_run import (
    PostgresRuntimeRunProjector,
)
from functorial_kit.contribution_verification import VerificationChanges
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import NativeContribution

from mrw_functorial_kit.contributions.task import (
    task_law_witnesses,
    task_native_catalog,
    task_verification_law_witnesses,
    task_verification_plan,
    task_verification_plan_for,
    task_verification_registration,
    contribution_catalog,
)
from mrw_functorial_kit.core.w07_semantics import runtime_failures

SOURCES = (
    DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE,
    NON_DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE,
)


def test_catalog_contains_default_and_non_default_sources_in_order() -> None:
    assert tuple(native.projection.id for native in task_native_catalog) == tuple(
        source.contribution_id for source in SOURCES
    )
    assert tuple(native.projection.owner for native in task_native_catalog) == (
        "task.observation.v2",
        "task.observation.v2",
    )
    assert tuple(item.id for item in contribution_catalog.contributions) == tuple(
        native.projection.id for native in task_native_catalog
    )
    assert all(
        native.projection.failures == (runtime_failures,)
        for native in task_native_catalog
    )


def test_default_source_declares_exact_task_observation_order_and_offline_authority_boundary() -> None:
    assert tuple((cell.cell_id, cell.role) for cell in DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.cells) == (
        (SESSION_OBSERVATION_CELL_ID, "session_observation_projection"),
        (TASK_EFFECT_RECONCILE_CELL_ID, "effect_reconciliation_readback"),
        (RUN_OBSERVATION_CELL_ID, "runtime_run_projection"),
        (PROCESS_OBSERVATION_CELL_ID, "process_observation_projection"),
    )
    assert ASSEMBLY_CELL_IDS == tuple(
        cell.cell_id for cell in DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.cells
    )
    assert TASK_OBSERVATION_FAMILY_ID == "task.observation.v1"
    assert DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.cells[1].authority_ref.endswith(":EffectReconciler")
    assert DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.cells[1].handler_ref.endswith(":AuthoritativeEffectReadback")
    assert DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.cells[3].authority_ref.endswith(
        ":try_join_process_observations"
    )
    assert DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.production_canonical_write is False
    assert DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.durable_evidence_authorized is False
    assert DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.registry_metadata_is_execution_evidence is False
    assert DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.projector_source_keys == ()


@pytest.mark.parametrize("witness", task_law_witnesses, ids=[witness.id for witness in task_law_witnesses])
def test_catalog_laws_are_inert_and_pass(witness) -> None:
    witness.run()


def test_verification_plan_derives_from_same_catalog_and_unknown_changes_expand() -> None:
    expected = tuple(native.projection.id for native in task_native_catalog)
    assert task_verification_plan.selection.contribution_ids == expected
    unknown = task_verification_plan_for(VerificationChanges(unknown=True))
    assert unknown.selection.mode == "full"
    assert "unknown_changes" in unknown.selection.reasons
    assert unknown.selection.contribution_ids == expected
    assert task_verification_registration is not None
    for witness in task_verification_law_witnesses:
        witness.run()


@pytest.mark.parametrize("source", SOURCES, ids=["default", "runtime-readback"])
def test_rule_binding_keeps_reconcile_readback_and_projector_separate(source) -> None:
    native = compile_task_observation_native_contribution(source)
    assert isinstance(native, NativeContribution)
    definition = native.definition
    assert definition.reconciler is EffectReconciler
    assert definition.session_projector is PostgresAgentSessionReadAdapter
    assert definition.runtime_projector is PostgresRuntimeRunProjector
    assert definition.process_observation_projector is try_join_process_observations
    rejected_projection = definition.process_observation_projector(
        (),
        captured_at=datetime(2030, 2, 2, 3, 4, tzinfo=UTC),
    )
    assert isinstance(rejected_projection, Failure)
    assert rejected_projection.code == "PROCESS_OBSERVATION_INVALID"
    assert definition.line_event_projector_ref == LINE_EVENT_READBACK_PROJECTOR_REF
    assert project_line_event_readbacks.__module__.endswith(
        "substrate.projections.legacy_process"
    )

    binding = native.assemble(
        TaskObservationAssemblyContext(
            project_scope_digest=local_assembly_scope_digest(),
            options=TaskObservationAssemblyOptions(),
        )
    )
    assert not isinstance(binding, Failure)
    assert tuple(cell.cell_id for cell in binding.family_assembly.cells) == (
        ASSEMBLY_CELL_IDS
    )
    assert binding.family_assembly.family_id == TASK_OBSERVATION_FAMILY_ID
    reconcile_handlers = [
        handler for handler in binding.family_assembly.handlers
        if isinstance(handler, TaskEffectReconcileRouteHandler)
    ]
    line_handlers = [
        handler for handler in binding.family_assembly.handlers
        if isinstance(handler, ProcessLineEventReadbackRouteHandler)
    ]
    assert len(reconcile_handlers) == 1
    assert len(line_handlers) == (1 if source.line_event_readback_records is not None else 0)
    if line_handlers:
        assert reconcile_handlers[0] is not line_handlers[0]
    registered = binding.family_assembly.projector_registry
    if source.projector_source_keys:
        assert registered is not None
        assert len(registered.projectors) == len(source.projector_source_keys)
    else:
        assert registered is None


def test_default_source_has_no_registry_and_non_default_registers_only_c5_3() -> None:
    default_binding = compile_task_observation_native_contribution(SOURCES[0]).assemble(
        TaskObservationAssemblyContext(
            project_scope_digest=local_assembly_scope_digest(),
            options=TaskObservationAssemblyOptions(),
        )
    )
    non_default_binding = compile_task_observation_native_contribution(SOURCES[1]).assemble(
        TaskObservationAssemblyContext(
            project_scope_digest=local_assembly_scope_digest(),
            options=TaskObservationAssemblyOptions(),
        )
    )
    assert not isinstance(default_binding, Failure)
    assert not isinstance(non_default_binding, Failure)
    assert default_binding.family_assembly.projector_registry is None
    assert len(non_default_binding.family_assembly.projector_registry.projectors) == 1


def test_assembly_consumes_only_current_family_keys_from_shared_source_map() -> None:
    foreign_key = ProjectorSourceKey(
        source_ref="run:foreign-family:001",
        source_incarnation="incarnation:foreign-family:001",
    )
    observed = build_task_observation_assembly(projector_source_keys={"knowledge.graph.v1": foreign_key})
    assert observed.projector_registry is None

    with pytest.raises(ValueError, match="historical C5 projector source keys"):
        build_task_observation_assembly(projector_source_keys={"C5.1": foreign_key})
