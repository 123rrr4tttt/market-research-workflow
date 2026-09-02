"""C4 quality-promotion readback runtime handler.

The handler is the S2 ALL-SM-013 runtime binding: it invokes the successor
quality-promotion port on explicit typed evidence during a C4 handler
execution and returns the deterministic readback digest.  Promotion
decisions remain readback-only; no provider, rollout, store or canonical
effect is ever started by this module.
"""

from __future__ import annotations

from typing import Any

from app.successor_runtime.capabilities.quality_promotion_port import (
    QualityGateEvidence,
    evaluate_quality_promotion_gate,
)
from app.successor_runtime.runtime.assignments import (
    RuntimeAssignment,
    require_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)


class C4QualityPromotionRuntimeHandler(RuntimeHandler):
    """Execute the quality gate and return its deterministic readback."""

    def __init__(
        self,
        *,
        evidence: QualityGateEvidence,
        handler_binding_digest: str,
        interpreter_profile_digest: str,
        operation_contract_digest: str,
        deployment_catalog_digest: str,
    ) -> None:
        if not isinstance(evidence, QualityGateEvidence):
            raise TypeError("C4 quality promotion evidence must be typed")
        require_digest(handler_binding_digest, "C4 quality handler binding digest")
        require_digest(
            interpreter_profile_digest,
            "C4 quality interpreter profile digest",
        )
        require_digest(
            operation_contract_digest,
            "C4 quality operation contract digest",
        )
        require_digest(
            deployment_catalog_digest,
            "C4 quality deployment catalog digest",
        )
        self.evidence = evidence
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.operation_contract_digest = operation_contract_digest
        self.deployment_catalog_digest = deployment_catalog_digest
        self.gate_calls = 0
        self.last_result: Any = None

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
            raise DefiniteInterpreterFailure("EXACT_C4_QUALITY_HANDLER_BINDING_DRIFT")
        if assignment.deployment_catalog_digest != self.deployment_catalog_digest:
            raise DefiniteInterpreterFailure(
                "EXACT_C4_QUALITY_DEPLOYMENT_CATALOG_DRIFT"
            )
        result = evaluate_quality_promotion_gate(self.evidence)
        self.gate_calls += 1
        self.last_result = result
        readback_digest = result.readback.readback_digest
        if not readback_digest:
            raise DefiniteInterpreterFailure(
                "C4_QUALITY_PROMOTION_READBACK_DIGEST_MISSING"
            )
        return InterpreterOutcome.succeeded(
            readback_digest,
            receipt_ref=(
                "receipt:quality-promotion:" + result.promotion.decision.decision_id
            ),
        )


__all__ = ["C4QualityPromotionRuntimeHandler"]
