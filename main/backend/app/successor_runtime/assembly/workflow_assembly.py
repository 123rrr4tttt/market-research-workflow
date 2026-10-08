"""Workflow family assembly: durable runtime handler only."""

from __future__ import annotations

from functools import partial

from app.successor_runtime.capabilities.workflow_native_contribution import (
    WORKFLOW_RUNTIME_CONTEXT_TYPE,
    WORKFLOW_RUNTIME_OWNER,
    WorkflowExecutionContext,
    WorkflowRuntimeOperationDefinition,
    validate_workflow_context_bound_inputs,
)
from app.successor_runtime.runtime.assignments import InterpreterBinding
from app.successor_runtime.runtime.node import DefiniteInterpreterFailure
from app.successor_runtime.runtime.ports import ProjectScopeRef
from app.successor_runtime.substrate.postgres.batch_task_submission_handler import (
    PersistentOperationHandler,
)
from app.successor_runtime.substrate.postgres.node_adapter import UowFactory


def assemble_workflow_runtime_handler(
    *,
    operation: WorkflowRuntimeOperationDefinition,
    uow_factory: UowFactory,
    binding: InterpreterBinding,
    project_key: str,
    resolved_schema: str,
) -> PersistentOperationHandler[WorkflowExecutionContext, WorkflowExecutionContext]:
    """Bind durable node execution; observe/restore wiring stays handler-free."""
    contract, profiles, codec = operation.contract, operation.profiles, operation.context_codec
    if any((
        contract.input_type != WORKFLOW_RUNTIME_CONTEXT_TYPE,
        contract.output_type != WORKFLOW_RUNTIME_CONTEXT_TYPE,
        codec.payload_type_id != WORKFLOW_RUNTIME_CONTEXT_TYPE.type_id,
        codec.contract_ref != contract.ref,
        contract.authority_profile_ref != profiles.authority.ref,
        (contract.owner_capability_id, profiles.authority.canonical_owner) != (WORKFLOW_RUNTIME_OWNER,) * 2,
    )):
        raise ValueError("workflow runtime operation binding drift")
    from app.services.projects.context import bind_resolved_project
    from app.services.workflow_graph.runtime import (
        WorkflowNodeSettledFailure,
        invoke_workflow_runtime_node,
    )

    def check_scope(context: WorkflowExecutionContext, project: ProjectScopeRef, capability_id: str) -> None:
        if (context.project_key, project.project_key, project.resolved_schema, capability_id) != (
            project_key,
            project_key,
            resolved_schema,
            contract.owner_capability_id,
        ):
            raise ValueError("workflow context crosses the installed project scope")

    def invoke(context: WorkflowExecutionContext) -> WorkflowExecutionContext:
        with bind_resolved_project(project_key, resolved_schema):
            try:
                return invoke_workflow_runtime_node(context)
            except WorkflowNodeSettledFailure as exc:
                raise DefiniteInterpreterFailure(exc.failure_code) from exc

    return PersistentOperationHandler(
        uow_factory=uow_factory,
        binding=binding,
        contract=contract,
        input_codec=codec,
        output_codec=codec,
        invoke=invoke,
        validate_input=check_scope,
        validate_bound_inputs=partial(validate_workflow_context_bound_inputs, operation=operation),
    )


__all__ = ["assemble_workflow_runtime_handler"]
