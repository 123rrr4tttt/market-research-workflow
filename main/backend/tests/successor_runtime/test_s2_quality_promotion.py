"""S2 C4 quality-promotion runtime handler wiring tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.successor_runtime.assembly.base import (
    C4AssemblyOptions,
    local_assembly_scope_digest,
    successor_binding,
)
from app.successor_runtime.assembly.c4_assembly import (
    _C4_DEPLOYMENT_CATALOG_DIGEST,
    _C4_QUALITY_PROMOTION_AUTHORITY_DIGEST,
    _C4_QUALITY_PROMOTION_INTERPRETER_DIGEST,
    _C4_QUALITY_PROMOTION_OPERATION_DIGEST,
    build_c4_assembly,
)
from app.successor_runtime.capabilities.quality_promotion_port import (
    BoundedRetryReadback,
    CriticScoreReadback,
    ExecutorHealthEvidence,
    FixtureQualityReadback,
    InputPromotionClaim,
    LiveProviderReplayReadback,
    LiveProviderRowEvidence,
    ProviderRolloutPolicyEvidence,
    QualityGateEvidence,
    RetryBoundaryObservation,
)
from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    NodeIdentity,
    RuntimeExecutionContext,
)
from app.successor_runtime.substrate.postgres.agent_batch_c4_quality_promotion_handler import (
    C4QualityPromotionRuntimeHandler,
)

pytestmark = pytest.mark.unit


def _fixture_quality_readback() -> FixtureQualityReadback:
    return FixtureQualityReadback(
        case_count=2,
        critic=CriticScoreReadback(
            case_id="robotics-source-gap",
            score=0.66,
            score_threshold=0.72,
            next_action="retry_with_precision_query",
            reason_codes=("entity_coverage_gap", "freshness_gap"),
        ),
        retry=BoundedRetryReadback(
            observations=(
                RetryBoundaryObservation(
                    case_id="robotics-source-gap",
                    expected_decision="retry_allowed",
                    decision="retry_allowed",
                    critic_score=0.66,
                    replay_score_is_observational=True,
                ),
                RetryBoundaryObservation(
                    case_id="robotics-sufficient-stop",
                    expected_decision="retry_blocked",
                    decision="retry_blocked",
                    critic_score=0.91,
                    replay_score_is_observational=True,
                ),
            ),
            enabled=True,
            retry_budget=1,
            max_retry_rounds=1,
        ),
        fixture_threshold_status="passed",
    )


def _executor_health() -> ExecutorHealthEvidence:
    return ExecutorHealthEvidence(
        worker_online=True,
        workers=("celery@successor",),
        inspect_performed=True,
        inspect_ok=True,
        broker_url_masked="redis://localhost:6379/0",
    )


def _provider_row(provider: str) -> LiveProviderRowEvidence:
    return LiveProviderRowEvidence(
        provider=provider,
        replay_status="passed",
        result_count=3,
        source_domains=("interestingengineering.com", "globenewswire.com"),
        relevance_score=0.82,
        freshness_score=0.84,
        duplicate_rate=0.0,
        timeout_rate=0.0,
        p95_latency_ms=980,
        review_sample_count=3,
        review_visible_sample_count=3,
        trace_success=True,
    )


def _full_closed_evidence() -> QualityGateEvidence:
    return QualityGateEvidence(
        fixture_replay=_fixture_quality_readback(),
        executor_health=_executor_health(),
        live_replay=LiveProviderReplayReadback(
            readback_artifact_ref="evidence/live-provider-quality-replay.v1.json",
            provider_rows=tuple(
                _provider_row(provider) for provider in ("searxng", "yacy", "web")
            ),
            operator_review_status="approved",
        ),
        rollout_policy=ProviderRolloutPolicyEvidence(
            approval_status="approved",
            approved_providers=("searxng", "yacy", "web"),
            rollback_criteria=("timeout_rate_above_10_percent",),
            monitoring_requirements=("daily_threshold_replay",),
            manual_review_artifact="evidence/provider-auto-review.md",
        ),
        input_promotion_claim=InputPromotionClaim(
            decision="promote_provider_auto",
            promotion_allowed=True,
            provider_auto_promotion_allowed=True,
        ),
    )


def _binding(handler: C4QualityPromotionRuntimeHandler) -> InterpreterBinding:
    binding = successor_binding(
        operation_contract_digest=handler.operation_contract_digest,
        interpreter_profile_digest=handler.interpreter_profile_digest,
        deployment_catalog_digest=handler.deployment_catalog_digest,
        project_scope_digest=local_assembly_scope_digest(),
        authority_requirement_digest=_C4_QUALITY_PROMOTION_AUTHORITY_DIGEST,
    )
    assert binding.binding_digest == handler.handler_binding_digest
    return binding


def _handler(evidence: QualityGateEvidence) -> C4QualityPromotionRuntimeHandler:
    return C4QualityPromotionRuntimeHandler(
        evidence=evidence,
        handler_binding_digest=successor_binding(
            operation_contract_digest=_C4_QUALITY_PROMOTION_OPERATION_DIGEST,
            interpreter_profile_digest=_C4_QUALITY_PROMOTION_INTERPRETER_DIGEST,
            deployment_catalog_digest=_C4_DEPLOYMENT_CATALOG_DIGEST,
            project_scope_digest=local_assembly_scope_digest(),
            authority_requirement_digest=_C4_QUALITY_PROMOTION_AUTHORITY_DIGEST,
        ).binding_digest,
        interpreter_profile_digest=_C4_QUALITY_PROMOTION_INTERPRETER_DIGEST,
        operation_contract_digest=_C4_QUALITY_PROMOTION_OPERATION_DIGEST,
        deployment_catalog_digest=_C4_DEPLOYMENT_CATALOG_DIGEST,
    )


def _assignment(
    handler: C4QualityPromotionRuntimeHandler,
    binding: InterpreterBinding,
) -> RuntimeAssignment:
    return RuntimeAssignment(
        runtime_protocol_version="mrw.runtime.protocol.v1",
        work_item_id="work:i1-c4-quality:001",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key="i1-local-c4",
        run_id="run:i1-c4-quality:001",
        step_id="step:c4-quality:gate",
        step_role=CompiledStepRole.EFFECT,
        capability_id="agent_batch.quality_promotion.v1",
        operation_contract_ref=OperationContractRef(
            kind="agent_batch.quality_promotion.v1",
            contract_version="1.0.0",
            contract_digest=handler.operation_contract_digest,
        ),
        operation_contract_digest=handler.operation_contract_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            "mrw.successor.agent-batch.quality-promotion.readback.v1",
            ReturnContract(
                success_modes=("SUCCEEDED",),
                failure_modes=("FAILED",),
                admission_required=False,
                wait_modes=(),
                cancel_modes=(),
            ),
        ),
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
        handler_binding=binding,
        program_digest=binding.binding_digest,
        deployment_catalog_digest=handler.deployment_catalog_digest,
        execution_epoch=1,
        incarnation="inc:i1-c4-quality:001",
        input_refs=(),
        queue_eligibility_digest="0" * 64,
        resource_policy_epoch=1,
        claim_authority_epoch=1,
        claim_policy_digest="0" * 64,
        expected_step_revision=0,
        trace_id="trace:i1-c4-quality:001",
    )


def _claim(
    handler: C4QualityPromotionRuntimeHandler,
    assignment: RuntimeAssignment,
) -> ClaimBinding:
    return ClaimBinding.bind(
        assignment,
        authorization_digest="0" * 64,
        lease_token="lease:i1-c4-quality",
        lease_expires_at=datetime(2026, 9, 2, 2, 0, tzinfo=UTC),
        node_id="node:i1-c4-quality",
        node_profile_digest="0" * 64,
        authority_digest="0" * 64,
        interpreter_profile_digest=handler.interpreter_profile_digest,
    )


def _context() -> RuntimeExecutionContext:
    return RuntimeExecutionContext(
        node=NodeIdentity(
            node_id="node:i1-c4-quality",
            incarnation="node-inc:i1-c4-quality",
            started_at=datetime(2026, 9, 2, 1, 0, tzinfo=UTC),
        ),
        observed_at=datetime(2026, 9, 2, 1, 0, tzinfo=UTC),
    )


def _execute(handler: C4QualityPromotionRuntimeHandler) -> object:
    binding = _binding(handler)
    assignment = _assignment(handler, binding)
    claim = _claim(handler, assignment)
    return handler.execute(assignment, claim, _context())


def test_c4_quality_handler_invokes_gate_without_authority_or_effects() -> None:
    handler = _handler(_full_closed_evidence())

    outcome = _execute(handler)

    assert handler.gate_calls == 1
    assert handler.last_result is not None
    result = handler.last_result
    assert result.status == "passed"
    assert result.promotion.decision.promotion_allowed is True
    assert result.readback.readback_matches_decision is True
    assert result.authority.authority_granted is False
    assert result.authority.provider_auto_promotion_authorized is False
    assert result.effect_counts.provider_calls == 0
    assert result.effect_counts.store_writes == 0
    assert result.effect_counts.canonical_writes == 0
    assert outcome.result_digest == result.readback.readback_digest


def test_missing_live_evidence_holds_and_rejects_input_promotion_claim() -> None:
    handler = _handler(
        QualityGateEvidence(
            fixture_replay=_fixture_quality_readback(),
            executor_health=_executor_health(),
            input_promotion_claim=InputPromotionClaim(
                decision="promote_provider_auto",
                promotion_allowed=True,
            ),
        )
    )

    _execute(handler)

    result = handler.last_result
    assert result.status == "passed"
    assert result.promotion.decision.promotion_allowed is False
    assert result.readback.input_promotion_claim_rejected is True
    assert result.readback.promotion_allowed is False


def test_health_anomaly_fails_closed() -> None:
    handler = _handler(
        QualityGateEvidence(
            fixture_replay=_fixture_quality_readback(),
            executor_health=ExecutorHealthEvidence(
                worker_online=False,
                workers=(),
                inspect_performed=True,
                inspect_ok=True,
            ),
            live_replay=LiveProviderReplayReadback(
                readback_artifact_ref="evidence/live-provider-quality-replay.v1.json",
                provider_rows=tuple(
                    _provider_row(provider) for provider in ("searxng", "yacy", "web")
                ),
                operator_review_status="approved",
            ),
            rollout_policy=ProviderRolloutPolicyEvidence(
                approval_status="approved",
                approved_providers=("searxng", "yacy", "web"),
                rollback_criteria=("timeout_rate_above_10_percent",),
                monitoring_requirements=("daily_threshold_replay",),
                manual_review_artifact="evidence/provider-auto-review.md",
            ),
        )
    )

    _execute(handler)

    result = handler.last_result
    assert result.health.passed is False
    assert "executor_health_no_online_worker" in result.health.failures
    assert result.promotion.decision.promotion_allowed is False
    assert result.effect_counts.provider_calls == 0


def test_c4_assembly_installs_quality_promotion_handler_with_evidence() -> None:
    assembly = build_c4_assembly(
        uow_factory=lambda: object(),  # type: ignore[arg-type]
        project_scope_digest=local_assembly_scope_digest(),
        options=C4AssemblyOptions(quality_evidence=_full_closed_evidence()),
    )
    quality_handlers = [
        handler
        for handler in assembly.handlers
        if isinstance(handler, C4QualityPromotionRuntimeHandler)
    ]
    assert len(quality_handlers) == 1
    assert "QUALITY_PROMOTION_HANDLER_INSTALLED_READBACK_ONLY" in (
        assembly.cell("C4.3").note
    )
    assert assembly.coverage() == {
        "C4.1": "FIXTURE_CLOSURE_REQUIRED",
        "C4.2": "FIXTURE_CLOSURE_REQUIRED",
        "C4.3": "INSTALLED",
    }
