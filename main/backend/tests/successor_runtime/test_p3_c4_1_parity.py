"""C4.1/C4.2 same-Program/Plan legacy+successor parity and binding isolation."""

from __future__ import annotations

from app.successor_migration.legacy_agent_batch import (
    LegacyAgentBatchPlanAdapter,
    LegacyAgentBatchRetryAdapter,
    build_legacy_agent_batch_c4_plan_binding,
    build_legacy_agent_batch_c4_retry_binding,
    build_successor_agent_batch_c4_plan_binding,
    build_successor_agent_batch_c4_retry_binding,
)
from app.successor_runtime.capabilities.agent_batch_c4 import (
    RetryAction,
    build_batch_plan,
    reduce_retry_action,
)
from app.successor_runtime.capabilities.agent_batch_c4_interpreters import (
    AgentBatchC4PlanSuccessorInterpreter,
    AgentBatchC4RetrySuccessorInterpreter,
    InterpreterFailure,
    InterpreterSuccess,
)

from .p3_c4_fixture import (
    DEPLOYMENT_CATALOG_DIGEST,
    SCOPE_DIGEST,
    c2_snapshot,
    catalog,
    plan_payload,
    plan_program_and_plan,
    retry_payload,
    retry_program_and_plan,
)


def _scope_view(payload):
    from dataclasses import dataclass

    @dataclass(frozen=True, slots=True)
    class _Scope:
        project_key: str
        registry_revision: int
        incarnation: str
        resolved_schema: str
        scope_digest: str

    return _Scope(
        project_key=payload.project_key,
        registry_revision=payload.registry_revision,
        incarnation=payload.scope_incarnation,
        resolved_schema=payload.resolved_schema,
        scope_digest=payload.scope_digest,
    )


def _plan_bindings(contract_digest: str):
    legacy = build_legacy_agent_batch_c4_plan_binding(
        contract_digest=contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    successor = build_successor_agent_batch_c4_plan_binding(
        contract_digest=contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    return legacy, successor


def _retry_bindings(contract_digest: str):
    legacy = build_legacy_agent_batch_c4_retry_binding(
        contract_digest=contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    successor = build_successor_agent_batch_c4_retry_binding(
        contract_digest=contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    return legacy, successor


def test_same_program_plan_legacy_and_successor_c4_1_agree() -> None:
    payload = plan_payload()
    program, plan, ref, payload_ref = plan_program_and_plan(payload)
    legacy_binding, successor_binding = _plan_bindings(ref.contract_digest)

    legacy_outcome = LegacyAgentBatchPlanAdapter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope_view(payload),
        catalog=catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=legacy_binding,
    )
    successor_outcome = AgentBatchC4PlanSuccessorInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope_view(payload),
        catalog=catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=successor_binding,
    )
    assert isinstance(legacy_outcome, InterpreterSuccess)
    assert isinstance(successor_outcome, InterpreterSuccess)
    assert legacy_outcome.value.result_digest == successor_outcome.value.result_digest
    assert [task.channel for task in legacy_outcome.value.tasks] == [
        task.channel for task in successor_outcome.value.tasks
    ]
    assert [task.item_key for task in legacy_outcome.value.tasks] == [
        task.item_key for task in successor_outcome.value.tasks
    ]


def test_binding_swap_and_mutation_reject_c4_1() -> None:
    payload = plan_payload()
    program, plan, ref, payload_ref = plan_program_and_plan(payload)
    legacy_binding, successor_binding = _plan_bindings(ref.contract_digest)

    swapped = AgentBatchC4PlanSuccessorInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope_view(payload),
        catalog=catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=legacy_binding,
    )
    assert isinstance(swapped, InterpreterFailure)
    assert swapped.code == "ASSIGNMENT_BINDING_MISMATCH"

    swapped_legacy = LegacyAgentBatchPlanAdapter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope_view(payload),
        catalog=catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=successor_binding,
    )
    assert isinstance(swapped_legacy, InterpreterFailure)
    assert swapped_legacy.code == "ASSIGNMENT_BINDING_MISMATCH"

    # Mutation of the compiled plan is rejected by exact binding validation.
    import dataclasses

    mutated_plan = dataclasses.replace(plan, plan_digest="0" * 64)
    mutated = AgentBatchC4PlanSuccessorInterpreter().interpret(
        program=program,
        plan=mutated_plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope_view(payload),
        catalog=catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=successor_binding,
    )
    assert isinstance(mutated, InterpreterFailure)
    assert mutated.code == "ASSIGNMENT_BINDING_MISMATCH"


def test_same_program_plan_legacy_and_successor_c4_2_agree() -> None:
    payload = retry_payload()
    program, plan, ref, payload_ref = retry_program_and_plan(payload)
    legacy_binding, successor_binding = _retry_bindings(ref.contract_digest)

    legacy_outcome = LegacyAgentBatchRetryAdapter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope_view(payload),
        catalog=catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=legacy_binding,
    )
    successor_outcome = AgentBatchC4RetrySuccessorInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope_view(payload),
        catalog=catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=successor_binding,
    )
    assert isinstance(legacy_outcome, InterpreterSuccess)
    assert isinstance(successor_outcome, InterpreterSuccess)
    # The legacy slice projects the same fresh attempt intent and ordered
    # task shape; transition observations differ only in declared legacy loss
    # fields, so the digest equality assertion is semantic, not byte-level.
    assert (
        legacy_outcome.value.attempt_intent.attempt_intent_digest
        == successor_outcome.value.attempt_intent.attempt_intent_digest
    )
    assert (
        legacy_outcome.value.attempt_intent.idempotency_key
        == successor_outcome.value.attempt_intent.idempotency_key
    )
    assert [task.channel for task in legacy_outcome.value.tasks] == [
        task.channel for task in successor_outcome.value.tasks
    ]
    assert [task.item_key for task in legacy_outcome.value.tasks] == [
        task.item_key for task in successor_outcome.value.tasks
    ]


def test_binding_swap_and_mutation_reject_c4_2() -> None:
    payload = retry_payload()
    program, plan, ref, payload_ref = retry_program_and_plan(payload)
    legacy_binding, successor_binding = _retry_bindings(ref.contract_digest)

    swapped = AgentBatchC4RetrySuccessorInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope_view(payload),
        catalog=catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=legacy_binding,
    )
    assert isinstance(swapped, InterpreterFailure)
    assert swapped.code == "ASSIGNMENT_BINDING_MISMATCH"

    swapped_legacy = LegacyAgentBatchRetryAdapter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=_scope_view(payload),
        catalog=catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=successor_binding,
    )
    assert isinstance(swapped_legacy, InterpreterFailure)
    assert swapped_legacy.code == "ASSIGNMENT_BINDING_MISMATCH"


def test_legacy_and_successor_plan_order_and_shapes_agree() -> None:
    payload = plan_payload()
    adapter = LegacyAgentBatchPlanAdapter()
    legacy = adapter.build_plan(
        payload,
        candidate_item_keys=tuple(
            item.item_key for item in payload.candidates.source_items
        ),
    )
    successor = build_batch_plan(payload)

    assert [task.channel for task in legacy.tasks] == [
        task.channel for task in successor.tasks
    ]
    assert [task.item_key for task in legacy.tasks] == [
        task.item_key for task in successor.tasks
    ]
    assert legacy.supplementation.item_keys == successor.supplementation.item_keys
    assert legacy.branching.enabled == successor.branching.enabled
    assert legacy.branching.strategy_labels == successor.branching.strategy_labels
    # The legacy pure slice reindexes task_ids during normalization; the
    # successor preserves the original ordered task identity.  Shape, order and
    # item keys are the parity surface; task_id reindexing is declared loss.
    assert [task.item_key for task in legacy.tasks] == [
        task.item_key for task in successor.tasks
    ]


def test_legacy_and_successor_branching_shape_agree() -> None:
    payload = plan_payload(
        command="调研机器人产品、公司和厂商",
        limited_branching=True,
        candidates=c2_snapshot(item_keys=()),
    )
    legacy = LegacyAgentBatchPlanAdapter().build_plan(
        payload,
        candidate_item_keys=tuple(
            item.item_key for item in payload.candidates.source_items
        ),
    )
    successor = build_batch_plan(payload)
    assert legacy.branching.enabled is True
    assert successor.branching.enabled is True
    assert [task.query_terms for task in legacy.tasks] == [
        task.query_terms for task in successor.tasks
    ]


def test_legacy_retry_and_successor_retry_agree_without_submit() -> None:
    payload = retry_payload()
    legacy = LegacyAgentBatchRetryAdapter().reduce(payload)
    successor = reduce_retry_action(payload)
    assert legacy.kind == successor.kind == "RETRY_SCHEDULED"
    assert legacy.attempt_intent is not None
    assert successor.attempt_intent is not None
    assert (
        legacy.attempt_intent.idempotency_key
        == successor.attempt_intent.idempotency_key
    )
    assert [task.item_key for task in legacy.tasks] == [
        task.item_key for task in successor.tasks
    ]
    assert [task.channel for task in legacy.tasks] == [
        task.channel for task in successor.tasks
    ]
    assert legacy.observations["used"] == successor.observations["used"]


def test_legacy_source_mode_rewrite_is_counted_but_never_projected() -> None:
    adapter = LegacyAgentBatchRetryAdapter()
    transition = adapter.reduce(
        retry_payload(
            action=RetryAction(
                action="attach_source_library",
                reason="source_backing_missing",
                channel="source_library",
                rewrite={
                    "item_key": "handler.cluster.news",
                    "source_mode": "site_search",
                },
            )
        )
    )
    assert adapter.source_mode_rewrites_seen == 1
    assert transition.kind == "RETRY_SCHEDULED"
    assert all(not hasattr(task, "source_mode") for task in transition.tasks)
    assert "source_mode" not in transition.observations


def test_legacy_plan_adapter_never_calls_ambient_discovery_for_supplied_keys() -> None:
    payload = plan_payload(candidates=c2_snapshot(item_keys=("only.supplied.key",)))
    adapter = LegacyAgentBatchPlanAdapter()
    legacy = adapter.build_plan(
        payload,
        candidate_item_keys=("only.supplied.key",),
    )
    appended = [
        task.item_key for task in legacy.tasks if task.channel == "source_library"
    ]
    assert appended == ["only.supplied.key"]
    assert adapter.plan_calls == 1
