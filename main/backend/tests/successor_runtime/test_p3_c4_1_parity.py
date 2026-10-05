"""Current-native C4.1/C4.2 Program/Plan interpreter and binding witnesses."""

from __future__ import annotations

from dataclasses import dataclass
import dataclasses

from app.successor_runtime.capabilities.batch_task_interpreters import (
    BatchTaskPlanSuccessorInterpreter,
    BatchTaskRetrySuccessorInterpreter,
    InterpreterFailure,
    InterpreterSuccess,
    build_successor_agent_batch_c4_plan_binding,
    build_successor_agent_batch_c4_retry_binding,
)

from .p3_c4_fixture import (
    DEPLOYMENT_CATALOG_DIGEST,
    SCOPE_DIGEST,
    catalog,
    plan_payload,
    plan_program_and_plan,
    retry_payload,
    retry_program_and_plan,
)


@dataclass(frozen=True, slots=True)
class _Scope:
    project_key: str
    registry_revision: int
    incarnation: str
    resolved_schema: str
    scope_digest: str


def _scope_view(payload):
    return _Scope(
        project_key=payload.project_key,
        registry_revision=payload.registry_revision,
        incarnation=payload.scope_incarnation,
        resolved_schema=payload.resolved_schema,
        scope_digest=payload.scope_digest,
    )


def _plan_binding(contract_digest: str):
    return build_successor_agent_batch_c4_plan_binding(
        contract_digest=contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )


def _retry_binding(contract_digest: str):
    return build_successor_agent_batch_c4_retry_binding(
        contract_digest=contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )


def _plan_arguments(payload):
    program, plan, ref, payload_ref = plan_program_and_plan(payload)
    return {
        "program": program,
        "plan": plan,
        "contract_ref": ref,
        "payload_ref": payload_ref,
        "payload": payload,
        "project_scope": _scope_view(payload),
        "catalog": catalog(),
        "deployment_catalog_digest": DEPLOYMENT_CATALOG_DIGEST,
        "binding": _plan_binding(ref.contract_digest),
    }


def _retry_arguments(payload):
    program, plan, ref, payload_ref = retry_program_and_plan(payload)
    return {
        "program": program,
        "plan": plan,
        "contract_ref": ref,
        "payload_ref": payload_ref,
        "payload": payload,
        "project_scope": _scope_view(payload),
        "catalog": catalog(),
        "deployment_catalog_digest": DEPLOYMENT_CATALOG_DIGEST,
        "binding": _retry_binding(ref.contract_digest),
    }


def test_native_plan_interpreter_binds_and_projects_exact_order() -> None:
    outcome = BatchTaskPlanSuccessorInterpreter().interpret(**_plan_arguments(plan_payload()))

    assert isinstance(outcome, InterpreterSuccess)
    assert outcome.disposition == "SUCCEEDED"
    assert [task.channel for task in outcome.value.tasks] == [
        "search.market",
        "source_library",
        "source_library",
    ]
    assert outcome.value.result_digest == (
        "f58ec2a42edf50edc2729fda8a9de06529e8973ed28762ace97af5407aaefa5a"
    )


def test_native_plan_rejects_swapped_binding_and_mutated_plan() -> None:
    arguments = _plan_arguments(plan_payload())
    retry_binding = _retry_binding(arguments["contract_ref"].contract_digest)
    swapped = BatchTaskPlanSuccessorInterpreter().interpret(
        **{**arguments, "binding": retry_binding}
    )
    mutated_plan = dataclasses.replace(arguments["plan"], plan_digest="0" * 64)
    mutated = BatchTaskPlanSuccessorInterpreter().interpret(
        **{**arguments, "plan": mutated_plan}
    )

    assert isinstance(swapped, InterpreterFailure)
    assert swapped.code == "ASSIGNMENT_BINDING_MISMATCH"
    assert isinstance(mutated, InterpreterFailure)
    assert mutated.code == "ASSIGNMENT_BINDING_MISMATCH"


def test_native_retry_interpreter_binds_exact_attempt() -> None:
    outcome = BatchTaskRetrySuccessorInterpreter().interpret(
        **_retry_arguments(retry_payload())
    )

    assert isinstance(outcome, InterpreterSuccess)
    assert outcome.value.kind == "RETRY_SCHEDULED"
    assert outcome.value.attempt_intent is not None
    assert outcome.value.attempt_intent.attempt_intent_digest == (
        "f81b9c70f5beb632cb5c56551d3bdabc8b42e1b4955a06a2840709e6de4077b0"
    )


def test_native_retry_rejects_swapped_binding() -> None:
    arguments = _retry_arguments(retry_payload())
    plan_binding = _plan_binding(arguments["contract_ref"].contract_digest)
    outcome = BatchTaskRetrySuccessorInterpreter().interpret(
        **{**arguments, "binding": plan_binding}
    )

    assert isinstance(outcome, InterpreterFailure)
    assert outcome.code == "ASSIGNMENT_BINDING_MISMATCH"
