"""Family-local canary handler for the C4 agent-batch atoms.

The canary slice is a bounded local realization: it captures an exact fixture
closure (Program, Plan, contract, payload ref, payload, catalog, binding) and
runs the pure successor interpreters through the shared RuntimeHandler shape.
It never enables a live provider, never performs submission/Celery/network
work, never claims a real runtime work item, and does not touch shared
substrate idempotency tables.

C4.1 additionally compiles the shared TraverseOrdered STATIC_SHAPE shape with
exact metadata; C4.3 uses the shared STARTED/TERMINAL idempotency root.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.successor_runtime.capabilities.agent_batch_c4_interpreters import (
    AgentBatchC4PlanSuccessorInterpreter,
    AgentBatchC4RetrySuccessorInterpreter,
    InterpreterFailure,
)
from app.successor_runtime.runtime.assignments import RuntimeAssignment, require_digest
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)

__all__ = [
    "C4_1_BatchPlanRuntimeHandler",
    "C4_2_RetryRuntimeHandler",
]


@dataclass(frozen=True, slots=True)
class _ScopeView:
    project_key: str
    registry_revision: int
    incarnation: str
    resolved_schema: str
    scope_digest: str


class _C4RuntimeHandlerBase(RuntimeHandler):
    """Exact fixture-closure realization for one pure C4 atom."""

    interpreter = None
    drift_code = "EXACT_C4_HANDLER_BINDING_DRIFT"

    def __init__(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: Any,
        payload_ref: Any,
        payload: Any,
        catalog: Any,
        binding: Any,
        deployment_catalog_digest: str,
    ) -> None:
        require_digest(
            getattr(binding, "binding_digest", ""),
            "C4 handler binding digest",
        )
        require_digest(deployment_catalog_digest, "C4 deployment catalog digest")
        self.program = program
        self.plan = plan
        self.contract_ref = contract_ref
        self.payload_ref = payload_ref
        self.payload = payload
        self.catalog = catalog
        self.binding = binding
        self.deployment_catalog_digest = deployment_catalog_digest
        self.handler_binding_digest = binding.binding_digest
        self.interpreter_profile_digest = binding.interpreter_profile_digest
        self.operation_contract_digest = contract_ref.contract_digest
        self.provider_calls = 0

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        if claim.assignment_digest != assignment.assignment_digest:
            raise DefiniteInterpreterFailure("CLAIM_ASSIGNMENT_BINDING_DRIFT")
        if (
            assignment.handler_binding_digest != self.handler_binding_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
        ):
            raise DefiniteInterpreterFailure(self.drift_code)
        if assignment.deployment_catalog_digest != self.deployment_catalog_digest:
            raise DefiniteInterpreterFailure("EXACT_C4_DEPLOYMENT_CATALOG_DRIFT")
        self.provider_calls += 1
        outcome = self.interpreter.interpret(
            program=self.program,
            plan=self.plan,
            contract_ref=self.contract_ref,
            payload_ref=self.payload_ref,
            payload=self.payload,
            project_scope=_ScopeView(
                project_key=self.payload.project_key,
                registry_revision=self.payload.registry_revision,
                incarnation=self.payload.scope_incarnation,
                resolved_schema=self.payload.resolved_schema,
                scope_digest=self.payload.scope_digest,
            ),
            catalog=self.catalog,
            deployment_catalog_digest=self.deployment_catalog_digest,
            binding=self.binding,
        )
        if isinstance(outcome, InterpreterFailure):
            raise DefiniteInterpreterFailure(outcome.code)
        return InterpreterOutcome.succeeded(
            getattr(outcome.value, "result_digest", None)
            or getattr(outcome.value, "transition_digest", None)
        )


class C4_1_BatchPlanRuntimeHandler(_C4RuntimeHandlerBase):
    """Exact installed realization of the pure C4.1 batch-plan interpreter."""

    interpreter = AgentBatchC4PlanSuccessorInterpreter()
    drift_code = "EXACT_C4_1_HANDLER_BINDING_DRIFT"


class C4_2_RetryRuntimeHandler(_C4RuntimeHandlerBase):
    """Exact installed realization of the pure C4.2 retry reducer."""

    interpreter = AgentBatchC4RetrySuccessorInterpreter()
    drift_code = "EXACT_C4_2_HANDLER_BINDING_DRIFT"
