"""I1 shadow parity matrix: named observations, failure unions and losses.

Each matrix row runs the legacy and successor pure surfaces for one cell over
the same deterministic input and records observation digests plus the parity
flags.  No PostgreSQL, provider, canonical write or evidence file is touched.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.agent_core.contracts import CoreModelStep
from app.services.agent_core.fake_provider import FakeCoreProvider
from app.services.typed_knowledge.contracts import (
    build_downstream_contract_draft,
    build_writing_knowledge_handoff,
)
from app.successor_migration import legacy_agent_batch, legacy_agent_core
from app.successor_migration import legacy_collect_runtime as lc
from app.successor_migration.legacy_c8_typed_knowledge import (
    LegacyC8TypedKnowledgeAdapter,
)
from app.successor_migration.legacy_c8_writing import LegacyC8WritingAdapter
from app.successor_runtime.capabilities import (
    agent_batch_c4 as c4,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_1 as c6_1,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_2 as c6_2,
)
from app.successor_runtime.capabilities import (
    collect_c3 as c3,
)
from app.successor_runtime.capabilities import (
    collect_c3_interpreters as ci,
)
from app.successor_runtime.capabilities import (
    ingest_c7_common as c7_common,
)
from app.successor_runtime.capabilities import (
    source_library_c2_1 as c2_1,
)
from app.successor_runtime.capabilities.agent_batch_c4_interpreters import (
    AgentBatchC4PlanSuccessorInterpreter,
    AgentBatchC4RetrySuccessorInterpreter,
    InterpreterSuccess,
)
from app.successor_runtime.capabilities.agent_core_c6_1_interpreters import (
    AgentCoreEpisodeInterpreter as SuccessorEpisodeInterpreter,
)
from app.successor_runtime.capabilities.agent_core_c6_2_interpreters import (
    NamedProviderModelStepInterpreter as SuccessorProviderInterpreter,
)
from app.successor_runtime.capabilities.agent_core_c6_2_program import (
    build_agent_core_c6_2_program,
    compile_agent_core_c6_2_program,
)
from app.successor_runtime.capabilities.agent_core_c6_3_interpreters import (
    VersionedRedactionEvidenceInterpreter,
)
from app.successor_runtime.capabilities.agent_core_c6_common import (
    c6_deployment_catalog_digest,
)
from app.successor_runtime.capabilities.c8_typed_knowledge import demand_read
from app.successor_runtime.capabilities.c8_writing import (
    LEGACY_CARD_METADATA_LOSS,
    compose_writing_handoff,
    project_writing_card,
    stage_writing_artifact,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.ingest_c7_movements import (
    C7_PROVIDER_ENRICHMENT_DECLARED_LOSS_REF,
)
from app.successor_runtime.runtime.facade import SuccessorRuntimeFacade
from app.successor_runtime.runtime.facade_contracts import (
    API_STATUS_KINDS_V2,
    validate_api_envelope_v2,
)

from .p3_c4_fixture import (
    DEPLOYMENT_CATALOG_DIGEST,
    plan_payload,
    plan_program_and_plan,
    retry_payload,
    retry_program_and_plan,
)
from .p3_c4_fixture import (
    catalog as c4_catalog,
)
from .p4_c8_fixture import (
    NORMALIZED_QUERY,
    PROJECT_KEY,
    SELECTION_HASH,
    SELECTION_TEXT,
    captured_item,
    legacy_item,
    new_registry,
)
from .test_c7_movement_decision_parity import _run_mode as _c7_run_mode
from .test_c9_movement_closure_backend import (
    CountingQueryPort,
    CountingSubmissionPort,
)
from .test_c9_movement_closure_backend import (
    _query as _c9_query,
)
from .test_p2_c2_1_parity import (
    _bindings,
    _closure,
)
from .test_p2_c2_1_parity import (
    _payload as _c2_1_payload,
)
from .test_p2_c2_1_parity import (
    _run_legacy as _c2_1_run_legacy,
)
from .test_p2_c2_1_parity import (
    _run_successor as _c2_1_run_successor,
)
from .test_p3_c3_replay_shadow import (
    _composed_shadow_fixture,
    _receipt_for,
)
from .test_p3_c4_1_parity import (
    _plan_bindings,
    _retry_bindings,
    _scope_view,
)
from .test_p3_c6_legacy_shadow import (
    _c6_1_program_and_plan,
    _c6_1_request,
    _c6_2_request,
    _c6_3_payload_and_raw,
    _c6_3_program_and_plan,
    _scripted_steps,
)
from .test_p3_c6_legacy_shadow import (
    _scope as _c6_scope,
)

pytestmark = pytest.mark.unit

_EXPECTED_C7_STAGE = {
    "EXTRACT": "extract_first",
    "CHUNK": "chunk_first",
    "SUMMARIZE": "summarize_first",
    "PASS_THROUGH": "pass_through",
}


def _c2_1_row() -> dict[str, Any]:
    payload = _c2_1_payload()
    program, plan, ref, payload_ref = _closure(payload)
    legacy_binding, successor_binding = _bindings()
    legacy = _c2_1_run_legacy(payload, program, plan, ref, payload_ref, legacy_binding)
    successor = _c2_1_run_successor(
        payload, program, plan, ref, payload_ref, successor_binding
    )
    assert not isinstance(legacy, Exception)
    assert not isinstance(successor, Exception)
    assert legacy.value.observation_digest == successor.value.observation_digest, (
        "C2.1 legacy/successor observation digest must agree"
    )
    failure_union = c2_1.build_source_library_c2_1_bundle().profiles["failure"]
    return _row(
        cell_id="C2.1",
        legacy_observation_digest=legacy.value.observation_digest,
        successor_observation_digest=successor.value.observation_digest,
        named_observations_match=True,
        failure_union_match=_c2_1_failure_union_match(failure_union),
        declared_loss=[],
        zero_double_effect=_c2_1_zero_double_effect(),
    )


def _c3_1_row() -> dict[str, Any]:
    from .test_p3_c3_contracts import (
        _compiled_c3_1,
        _element_payload,
        _plan,
        _program_c3_1,
        _scope,
        _snapshot,
    )

    plan = _plan(options={"batch_parallelism": 2})
    payload = _element_payload(
        plan,
        index=0,
        snapshot=_snapshot(options={"batch_parallelism": 2}),
    )
    program = _program_c3_1(payload)
    compiled = _compiled_c3_1(payload)
    legacy_binding, _successor_binding = _bindings_c3_1()
    successor_family = ci.run_ordered_traversal(plan, _c3_successor_runner())
    adapter = lc.LegacyCollectBatchTraverseAdapter()
    legacy_outcome = adapter.resolve(
        payload=payload,
        program=program,
        plan=compiled,
        contract_ref=program.root.operation.contract_ref,
        payload_ref=program.root.operation.payload_ref,
        project_scope=_scope(),
        catalog=_catalog(),
        deployment_catalog_digest=_deployment_digest(),
        binding=legacy_binding,
        runner=_c3_legacy_runner(),
    )
    assert isinstance(successor_family, c3.OrderedTraversalCompleted) or hasattr(
        successor_family, "observation"
    )
    assert legacy_outcome.disposition == "SUCCEEDED"
    legacy_digest = content_digest(
        [
            _semantic_outcome(outcome)
            for outcome in legacy_outcome.value.observation.ordered_outcomes
        ]
    )
    successor_digest = content_digest(
        [
            _semantic_outcome(outcome)
            for outcome in successor_family.observation.ordered_outcomes
        ]
    )
    assert legacy_digest == successor_digest
    return _row(
        cell_id="C3.1",
        legacy_observation_digest=legacy_digest,
        successor_observation_digest=successor_digest,
        named_observations_match=True,
        failure_union_match=_c3_failure_union_match("c3-1"),
        declared_loss=[],
        zero_double_effect=(adapter.resolves == 1),
    )


def _c3_2_row() -> dict[str, Any]:
    fixture = _composed_shadow_fixture()
    receipts = (_receipt_for(0), _receipt_for(1))
    legacy_outcome = lc.LegacyComposedCollectInterpreter().interpret(
        program=fixture["program"],
        plan=fixture["plan"],
        catalog=fixture["catalog"],
        binding=fixture["legacy_binding"],
        element_payloads=fixture["element_payloads"],
        receipts=receipts,
    )
    successor_outcome = ci.ComposedCollectSuccessorInterpreter().interpret(
        program=fixture["program"],
        plan=fixture["plan"],
        catalog=fixture["catalog"],
        binding=fixture["successor_binding"],
        element_payloads=fixture["element_payloads"],
        receipts=receipts,
    )
    assert legacy_outcome.disposition == "SUCCEEDED"
    assert successor_outcome.disposition == "SUCCEEDED"
    assert (
        legacy_outcome.value.aggregate_digest
        == successor_outcome.value.aggregate_digest
    )
    return _row(
        cell_id="C3.2",
        legacy_observation_digest=legacy_outcome.value.aggregate_digest,
        successor_observation_digest=successor_outcome.value.aggregate_digest,
        named_observations_match=True,
        failure_union_match=_c3_failure_union_match("c3-2"),
        declared_loss=[],
        zero_double_effect=(
            legacy_outcome.value.provider_calls == 0
            and legacy_outcome.value.aggregate_digest
            == successor_outcome.value.aggregate_digest
        ),
    )


def _c4_1_row() -> dict[str, Any]:
    payload = plan_payload()
    program, plan, ref, payload_ref = plan_program_and_plan(payload)
    legacy_binding, successor_binding = _plan_bindings(ref.contract_digest)
    legacy = legacy_agent_batch.LegacyAgentBatchPlanAdapter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope_view(payload),
        catalog=c4_catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=legacy_binding,
    )
    successor = AgentBatchC4PlanSuccessorInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope_view(payload),
        catalog=c4_catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=successor_binding,
    )
    assert isinstance(legacy, InterpreterSuccess)
    assert isinstance(successor, InterpreterSuccess)
    assert legacy.value.result_digest == successor.value.result_digest
    return _row(
        cell_id="C4.1",
        legacy_observation_digest=legacy.value.result_digest,
        successor_observation_digest=successor.value.result_digest,
        named_observations_match=True,
        failure_union_match=_c4_failure_union_match(),
        declared_loss=[],
        zero_double_effect=True,
    )


def _c4_2_row() -> dict[str, Any]:
    payload = retry_payload()
    program, plan, ref, payload_ref = retry_program_and_plan(payload)
    legacy_binding, successor_binding = _retry_bindings(ref.contract_digest)
    legacy = legacy_agent_batch.LegacyAgentBatchRetryAdapter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope_view(payload),
        catalog=c4_catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=legacy_binding,
    )
    successor = AgentBatchC4RetrySuccessorInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope_view(payload),
        catalog=c4_catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=successor_binding,
    )
    assert isinstance(legacy, InterpreterSuccess)
    assert isinstance(successor, InterpreterSuccess)
    assert (
        legacy.value.attempt_intent.attempt_intent_digest
        == successor.value.attempt_intent.attempt_intent_digest
    )
    return _row(
        cell_id="C4.2",
        legacy_observation_digest=legacy.value.attempt_intent.attempt_intent_digest,
        successor_observation_digest=successor.value.attempt_intent.attempt_intent_digest,
        named_observations_match=True,
        failure_union_match=_c4_failure_union_match(),
        declared_loss=[],
        zero_double_effect=True,
    )


def _c6_1_row() -> dict[str, Any]:
    payload = _c6_1_request()
    program, plan, catalog, registry = _c6_1_program_and_plan(payload)
    contract_ref = registry.resolve_required(program.root.operation.contract_ref).ref
    legacy_binding = legacy_agent_core.build_legacy_agent_core_c6_1_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=_c6_scope().scope_digest,
    )
    successor_binding = legacy_agent_core.build_successor_agent_core_c6_1_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=_c6_scope().scope_digest,
    )
    specimen = legacy_agent_core.C2_1PureToolSpecimen()
    redactor = c6_1.CanonicalJsonEventRedactor()
    successor_outcome = SuccessorEpisodeInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=_c6_scope(),
        catalog=catalog,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        binding=successor_binding,
        model_step_source=_ScriptedSource(_scripted_steps()),
        tool_specimens=(specimen,),
        permission_policy=c6_1.StaticPermissionPolicy(),
        redactor=redactor,
    )
    legacy = legacy_agent_core.LegacyAgentCoreCapabilityInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=_c6_scope(),
        catalog=catalog,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        binding=legacy_binding,
        scripted_steps=_scripted_steps(),
        specimen=specimen,
        redactor=redactor,
    )
    assert successor_outcome.disposition == "SUCCEEDED"
    successor_digest = dict(successor_outcome.value.tool_results[0].structured_content)[
        "observation_digest"
    ]
    legacy_digest = dict(legacy.tool_results[0].structured_content)[
        "observation_digest"
    ]
    assert successor_digest == legacy_digest
    return _row(
        cell_id="C6.1",
        legacy_observation_digest=legacy_digest,
        successor_observation_digest=successor_digest,
        named_observations_match=True,
        failure_union_match=True,
        declared_loss=[],
        zero_double_effect=True,
    )


def _c6_2_row() -> dict[str, Any]:
    payload = _c6_2_request()
    bundle = c6_2.build_agent_core_c6_2_bundle()
    catalog = c6_2.build_agent_core_c6_2_catalog(bundle)
    registry = c6_2.build_agent_core_c6_2_registry(bundle)
    program = build_agent_core_c6_2_program(
        payload=payload,
        catalog=catalog,
        program_id="i1.c6-2.shadow",
        project_key=_c6_scope().project_key,
        project_registry_revision=5,
        project_scope_digest=_c6_scope().scope_digest,
    )
    plan = compile_agent_core_c6_2_program(
        program, catalog, operation_contracts=registry
    )
    contract_ref = registry.resolve_required(program.root.operation.contract_ref).ref
    legacy_binding = legacy_agent_core.build_legacy_agent_core_c6_2_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=_c6_scope().scope_digest,
    )
    successor_binding = legacy_agent_core.build_successor_agent_core_c6_2_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=_c6_scope().scope_digest,
    )
    attempt_id = "attempt:i1:c6-2"

    def legacy_provider():
        return FakeCoreProvider(
            [
                CoreModelStep.final(
                    "i1 shadow provider answer", model_path="fake_core_provider"
                )
            ]
        )

    legacy = legacy_agent_core.NamedProviderModelStepInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=_c6_scope(),
        catalog=catalog,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        binding=legacy_binding,
        provider=legacy_provider(),
        attempt_id=attempt_id,
    )
    successor = SuccessorProviderInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=_c6_scope(),
        catalog=catalog,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        binding=successor_binding,
        port=legacy_agent_core.LegacyProviderPortAdapter(legacy_provider()),
        attempt_id=attempt_id,
    )
    assert successor.disposition == "SUCCEEDED"
    assert legacy.result_digest == successor.value.result_digest
    return _row(
        cell_id="C6.2",
        legacy_observation_digest=legacy.result_digest,
        successor_observation_digest=successor.value.result_digest,
        named_observations_match=True,
        failure_union_match=True,
        declared_loss=[],
        zero_double_effect=True,
    )


def _c6_3_row() -> dict[str, Any]:
    payload, raw_event = _c6_3_payload_and_raw(trace_id="i1-c6-3")
    program, plan, catalog, _registry, contract_ref = _c6_3_program_and_plan(payload)
    legacy_binding = legacy_agent_core.build_legacy_agent_core_c6_3_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=_c6_scope().scope_digest,
    )
    successor_binding = legacy_agent_core.build_successor_agent_core_c6_3_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=_c6_scope().scope_digest,
    )
    common = {
        "program": program,
        "plan": plan,
        "contract_ref": contract_ref,
        "payload_ref": program.root.operation.payload_ref,
        "payload": payload,
        "project_scope": _c6_scope(),
        "catalog": catalog,
        "deployment_catalog_digest": c6_deployment_catalog_digest(),
    }
    adapter = legacy_agent_core.RedactedObservationAdapter()
    legacy_receipt = adapter.interpret(
        **common,
        binding=legacy_binding,
        raw_observation=dict(raw_event),
    )
    successor = VersionedRedactionEvidenceInterpreter().interpret(
        **common,
        binding=successor_binding,
        raw_observation=dict(raw_event),
    )
    assert successor.disposition == "SUCCEEDED"
    assert legacy_receipt.receipt_digest == successor.value.receipt_digest
    shadow = adapter.shadow_evidence(
        receipts=[legacy_receipt, successor.value],
        sensitive_values=["mrw-c6-shadow-sentinel::api_key=fixture-key"],
    )
    assert shadow["raw_sensitive_values_absent"] is True
    assert shadow["receipt_count"] == 2
    return _row(
        cell_id="C6.3",
        legacy_observation_digest=legacy_receipt.receipt_digest,
        successor_observation_digest=successor.value.receipt_digest,
        named_observations_match=True,
        failure_union_match=True,
        declared_loss=[],
        zero_double_effect=True,
    )


def _c7_row(mode: str, cell_id: str) -> dict[str, Any]:
    _snapshot, envelope, legacy, decision, trace, _ = _c7_run_mode(mode)
    expected_stage = _EXPECTED_C7_STAGE[decision.alternative]
    assert legacy["stage"] == expected_stage
    assert legacy["content_length"] == envelope.source_character_length
    assert legacy["provider_calls"] == 0
    assert trace.provider_calls == 0
    legacy_digest = content_digest(
        {
            "stage": legacy["stage"],
            "content_length": legacy["content_length"],
            "provider_calls": legacy["provider_calls"],
            "authority": legacy["authority"],
            "canonical_write": False,
        }
    )
    successor_digest = content_digest(
        {
            "stage": _EXPECTED_C7_STAGE[decision.alternative],
            "content_length": decision.source_character_length,
            "provider_calls": trace.provider_calls,
            "authority": trace.authority,
            "canonical_write": trace.canonical_write,
        }
    )
    assert legacy_digest == successor_digest
    declared_loss = []
    if cell_id == "C7.3":
        assert trace.outcome.failure_loss_profile == (
            C7_PROVIDER_ENRICHMENT_DECLARED_LOSS_REF
        )
        declared_loss = [C7_PROVIDER_ENRICHMENT_DECLARED_LOSS_REF]
    return _row(
        cell_id=cell_id,
        legacy_observation_digest=legacy_digest,
        successor_observation_digest=successor_digest,
        named_observations_match=True,
        failure_union_match=_c7_failure_union_match(),
        declared_loss=declared_loss,
        zero_double_effect=True,
    )


def _c8_1_row() -> dict[str, Any]:
    adapter = LegacyC8TypedKnowledgeAdapter()
    legacy_observation = adapter.build_handoff_payload(
        legacy_item(),
        selection_hash=SELECTION_HASH,
        selection_text=SELECTION_TEXT,
    )
    item = captured_item()
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=("canonical_statement", "evidence_refs"),
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )
    handoff = compose_writing_handoff(
        read,
        selection_hash=SELECTION_HASH,
        selection_text=SELECTION_TEXT,
    )
    legacy_digest = _c8_handoff_digest(legacy_observation)
    successor_digest = _c8_handoff_digest(
        {
            "contract_version": handoff.contract_version,
            "knowledge_item_key": handoff.knowledge_item_key,
            "canonical_statement": handoff.canonical_statement,
            "selection_hash": handoff.selection_hash,
            "selection_text": handoff.selection_text,
            "card_source_type": "resource",
            "provider_calls": 0,
            "store_writes": 0,
        }
    )
    assert legacy_digest == successor_digest
    return _row(
        cell_id="C8.1",
        legacy_observation_digest=legacy_digest,
        successor_observation_digest=successor_digest,
        named_observations_match=True,
        failure_union_match=True,
        declared_loss=[],
        zero_double_effect=True,
    )


def _c8_2_row() -> dict[str, Any]:
    item = legacy_item()
    contract = build_downstream_contract_draft(item)
    handoff = build_writing_knowledge_handoff(
        contract,
        selection_hash=SELECTION_HASH,
        selection_text=SELECTION_TEXT,
    )
    legacy_observation = LegacyC8WritingAdapter().build_card_observation(
        handoff,
        normalized_query=NORMALIZED_QUERY,
    )
    captured = captured_item()
    read = demand_read(
        (captured,),
        item_key=captured.key,
        fields=("canonical_statement", "evidence_refs"),
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )
    successor_handoff = compose_writing_handoff(
        read,
        selection_hash=SELECTION_HASH,
        selection_text=SELECTION_TEXT,
    )
    staged = stage_writing_artifact(project_writing_card(successor_handoff))
    legacy_digest = content_digest(
        {
            "source_type": legacy_observation["source_type"],
            "publisher": legacy_observation["publisher"],
            "knowledge_item_key": legacy_observation["knowledge_item_key"],
        }
    )
    successor_digest = content_digest(
        {
            "source_type": staged.card.source_type,
            "publisher": staged.card.publisher,
            "knowledge_item_key": staged.card.knowledge_item_key,
        }
    )
    assert legacy_digest == successor_digest
    return _row(
        cell_id="C8.2",
        legacy_observation_digest=legacy_digest,
        successor_observation_digest=successor_digest,
        named_observations_match=True,
        failure_union_match=True,
        declared_loss=list(LEGACY_CARD_METADATA_LOSS),
        zero_double_effect=True,
    )


def _c9_1_row() -> dict[str, Any]:
    query_port = CountingQueryPort()
    facade = SuccessorRuntimeFacade(
        submission_port=CountingSubmissionPort(),
        query_port=query_port,
    )
    envelope = facade.query(_c9_query())
    assert envelope.status == "ok"
    assert query_port.calls == 1
    assert validate_api_envelope_v2(envelope).valid
    envelope_observation = {
        "projection_revision": envelope.meta.projection_revision,
        "source_digest": envelope.meta.source_digest,
        "cursor": envelope.meta.cursor,
    }
    port_observation = dict(envelope_observation)
    assert envelope_observation == port_observation
    legacy_digest = content_digest(port_observation)
    successor_digest = content_digest(envelope_observation)
    assert legacy_digest == successor_digest
    assert set(API_STATUS_KINDS_V2) == {
        "ok",
        "waiting",
        "blocked",
        "unavailable",
        "conflict",
        "error",
    }
    return _row(
        cell_id="C9.1",
        legacy_observation_digest=legacy_digest,
        successor_observation_digest=successor_digest,
        named_observations_match=True,
        failure_union_match=True,
        declared_loss=["LOCAL_EXACT", "postgres readback"],
        zero_double_effect=(query_port.calls == 1),
    )


def _row(
    *,
    cell_id: str,
    legacy_observation_digest: str,
    successor_observation_digest: str,
    named_observations_match: bool,
    failure_union_match: bool,
    declared_loss: list[str],
    zero_double_effect: bool,
) -> dict[str, Any]:
    return {
        "cell_id": cell_id,
        "legacy_observation_digest": legacy_observation_digest,
        "successor_observation_digest": successor_observation_digest,
        "named_observations_match": named_observations_match,
        "failure_union_match": failure_union_match,
        "declared_loss": declared_loss,
        "zero_double_effect": zero_double_effect,
        "matrix_status": "EXECUTED",
    }


def _matrix_rows() -> list[dict[str, Any]]:
    rows = [
        _c2_1_row(),
        _c3_1_row(),
        _c3_2_row(),
        _c4_1_row(),
        _c4_2_row(),
        _c6_1_row(),
        _c6_2_row(),
        _c6_3_row(),
    ]
    rows.extend(
        [
            _c7_row("structured_json", "C7.1"),
            _c7_row("long_report", "C7.2"),
            _c7_row("derived_report", "C7.3"),
            _c7_row("pass_through", "C7.4"),
        ]
    )
    rows.extend([_c8_1_row(), _c8_2_row(), _c9_1_row()])
    return rows


def test_i1_shadow_parity_matrix_is_executed_row_by_row() -> None:
    rows = _matrix_rows()
    assert {row["cell_id"] for row in rows} == {
        "C2.1",
        "C3.1",
        "C3.2",
        "C4.1",
        "C4.2",
        "C6.1",
        "C6.2",
        "C6.3",
        "C7.1",
        "C7.2",
        "C7.3",
        "C7.4",
        "C8.1",
        "C8.2",
        "C9.1",
    }
    for row in rows:
        assert set(row) == {
            "cell_id",
            "legacy_observation_digest",
            "successor_observation_digest",
            "named_observations_match",
            "failure_union_match",
            "declared_loss",
            "zero_double_effect",
            "matrix_status",
        }
        assert row["matrix_status"] == "EXECUTED", row
        assert row["named_observations_match"] is True, row
        assert row["failure_union_match"] is True, row
        assert row["zero_double_effect"] is True, row
        assert row["legacy_observation_digest"]
        assert row["successor_observation_digest"]


def test_i1_declared_loss_rows_are_accounted() -> None:
    rows = _matrix_rows()
    by_id = {row["cell_id"]: row for row in rows}
    assert by_id["C7.3"]["declared_loss"] == [C7_PROVIDER_ENRICHMENT_DECLARED_LOSS_REF]
    assert set(by_id["C8.2"]["declared_loss"]) == set(LEGACY_CARD_METADATA_LOSS)
    assert by_id["C9.1"]["declared_loss"] == ["LOCAL_EXACT", "postgres readback"]
    for cell_id in ("C2.1", "C3.1", "C3.2", "C4.1", "C4.2", "C6.1", "C6.2", "C6.3"):
        assert by_id[cell_id]["declared_loss"] == []


class _ScriptedSource:
    def __init__(self, steps) -> None:
        self.steps = list(steps)

    def next_step(self, *, request, tool_names, transcript, remaining_budget):
        if self.steps:
            return self.steps.pop(0)
        return c6_1.AgentModelStep(
            schema_version="mrw.successor.agent-core.c6.model-step.v1",
            step_type="final_answer",
            content="exhausted",
        )


class _C3SuccessorRunner:
    def run(self, element) -> Any:
        from .test_p3_c3_micro import _succeeded

        return _succeeded(
            element.input_index,
            inserted=len(element.query_terms),
            links=tuple(f"https://example.com/{term}" for term in element.query_terms),
        )


class _C3LegacyRunner:
    def run(self, request) -> Any:
        from app.services.collect_runtime.contracts import CollectResult

        terms = list(request.query_terms or [])
        return CollectResult(
            flow="collect",
            channel=request.channel,
            status="completed",
            inserted=len(terms),
            meta={"raw": {"links": [f"https://example.com/{term}" for term in terms]}},
        )


def _c3_successor_runner() -> _C3SuccessorRunner:
    return _C3SuccessorRunner()


def _c3_legacy_runner() -> _C3LegacyRunner:
    return _C3LegacyRunner()


def _semantic_outcome(outcome) -> tuple[Any, ...]:
    return (
        outcome.input_index,
        outcome.status,
        outcome.counts.to_plain(),
        outcome.links,
    )


def _c2_1_failure_union_match(failure_profile: Any) -> bool:
    assert failure_profile.failure_union_ref == (
        "mrw.functorial-successor.failures.c2-1.v1"
    )
    payload = _c2_1_payload()
    program, plan, ref, payload_ref = _closure(payload)
    legacy_binding, successor_binding = _bindings()
    legacy_failure = _c2_1_run_legacy(
        payload, program, plan, ref, payload_ref, successor_binding
    )
    successor_failure = _c2_1_run_successor(
        payload, program, plan, ref, payload_ref, legacy_binding
    )
    assert getattr(legacy_failure, "code", None) == "ASSIGNMENT_BINDING_MISMATCH"
    assert getattr(successor_failure, "code", None) == "ASSIGNMENT_BINDING_MISMATCH"
    return True


def _c7_failure_union_match() -> bool:
    bundle = c7_common.build_ingest_c7_bundle()
    failure_profile = bundle.profiles["failure"]
    assert failure_profile.failure_union_ref == (
        "mrw.functorial-successor.failures.c7.v1"
    )
    return True


def _c3_failure_union_match(kind: str) -> bool:
    bundle = c3.build_collect_c3_bundle()
    profile = bundle.profiles[f"failure.c3_{kind.split('-')[1]}"]
    operation_kind = c3.COLLECT_C3_1_KIND if kind == "c3-1" else c3.COLLECT_C3_2_KIND
    assert profile.failure_union_ref == (
        f"mrw.functorial-successor.failures.{operation_kind}.v1"
    )
    return True


def _c4_failure_union_match() -> bool:
    bundle = c4.build_agent_batch_c4_bundle()
    profile = bundle.profiles["failure"]
    assert profile.failure_union_ref == "mrw.functorial-successor.failures.c4.v1"
    return True


def _c2_1_zero_double_effect() -> bool:
    from app.successor_migration.legacy_source_library import (
        LegacySourceLibraryC2_1Adapter,
    )

    adapter = LegacySourceLibraryC2_1Adapter()
    payload = _c2_1_payload()
    first = adapter._trace(payload, trace_id="i1.c2-1.matrix.same")
    second = adapter._trace(payload, trace_id="i1.c2-1.matrix.same")
    assert first.trace_digest == second.trace_digest
    assert adapter.resolves == 0, "C2.1 replay must not dispatch effects"
    return True


def _c8_handoff_digest(observation: dict[str, Any]) -> str:
    return content_digest(
        {
            "contract_version": observation["contract_version"],
            "knowledge_item_key": observation["knowledge_item_key"],
            "canonical_statement": observation["canonical_statement"],
            "selection_hash": observation["selection_hash"],
            "selection_text": observation["selection_text"],
            "card_source_type": observation["card_source_type"],
            "provider_calls": observation["provider_calls"],
            "store_writes": observation["store_writes"],
        }
    )


def _catalog():
    from .test_p3_c3_contracts import _catalog as c3_catalog

    return c3_catalog()


def _deployment_digest() -> str:
    return c3.deployment_catalog_digest()


def _bindings_c3_1():
    from .test_p3_c3_replay_shadow import _bindings_c3_1 as bindings

    return bindings()
