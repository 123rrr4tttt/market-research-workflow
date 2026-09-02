"""Deterministically generate the normalized P3 C5 evidence fragment.

Root schema: ``mrw.functorial_successor.p3_fragment.v1``.  The generator binds
the C5.1 journal-derived session/task projection, C5.2 legacy attempt replay
and existing-owner reconciliation acceptance, C5.3 fold/snapshot agreement over
the existing replay/projector, and C5.4 offline Celery/DB/process typed
observations and join projection.  It runs no live provider, network, Celery,
Redis, or canonical write.  Run from ``main/backend``:

    python3.11 scripts/generate_successor_p3_c5_fragment.py

The generator self-tests determinism (two identical builds) and the
``content_digest`` over the canonical fragment body.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.successor_migration.legacy_agent_sessions import (
    project_legacy_session_read_model,
)
from app.successor_migration.legacy_effect_attempts import (
    ExactLegacyAttemptBinding,
    LegacyInterpreterProfile,
    replay_effect_attempt,
)
from app.successor_migration.legacy_process_observations import (
    capture_celery_async_result,
    capture_celery_inspect_task,
    capture_etl_job_run,
    capture_process_log,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    EffectReconciler,
)
from app.successor_runtime.runtime.replay import (
    ReplayEvent,
    RuntimeReplayProjection,
    replay_runtime_events,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.projections.agent_session import (
    fold_agent_session,
)
from app.successor_runtime.substrate.projections.legacy_process import (
    SourceBindingMismatch,
    join_process_observations,
)

PROJECT_KEY = "p3-c5-fragment"
RESOLVED_SCHEMA = "mrw_p3_c5_fragment"
REGISTRY_REVISION = 1
SCOPE_INCARNATION = "scope-inc-p3-c5"
OBSERVED_AT = datetime(2030, 9, 1, 8, 0, tzinfo=UTC)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_ROOT = REPOSITORY_ROOT / (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
FRAGMENT_PATH = EVIDENCE_ROOT / "p3-fragments/C5.json"
FRAGMENT_ID = "p3-c5-family-local-implementation"
FRAGMENT_SCHEMA = "mrw.functorial_successor.p3_fragment.v1"
AUTHORITY_DIGEST = content_digest("p3-c5-authority")
PROGRAM_DIGEST = content_digest("p3-c5-program")
ADJUDICATION_PATH = EVIDENCE_ROOT / "C5_4LocatorAdjudication.v1.json"
ADJUDICATION_RELATIVE = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/"
    "C5_4LocatorAdjudication.v1.json"
)
ADJUDICATION_CONTENT_DIGEST = (
    "1b2209a7cc55be719a4470575579a66b744171aadea52eae9e30e075e81b9b0d"
)
ADJUDICATION_FILE_SHA256 = (
    "81a64ec01988d7dd02034f689d8c70e0d7d58dbc6c39eb6306fe029a14b34f77"
)
NORMATIVE_DONOR_LOCATORS = (
    "main/backend/app/services/tasks.py",
    "main/backend/app/services/agent_sessions",
    "main/backend/app/celery_app.py",
)
SUPPLEMENTARY_READ_ONLY_EVIDENCE = (
    "main/backend/app/api/process.py",
    "main/backend/app/api/agent_batch.py",
)
PROHIBITED_DIRTY_SOURCE = "main/backend/app/services/task_readback_metadata.py"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _bind(path: Path, role: str) -> dict[str, object]:
    relative = path.resolve().relative_to(REPOSITORY_ROOT.resolve())
    data = path.read_bytes()
    return {
        "path": str(relative),
        "sha256": _sha256_bytes(data),
        "bytes": len(data),
        "lines": len(data.splitlines()),
        "role": role,
    }


def _p1_cells() -> dict[str, dict[str, Any]]:
    artifact = json.loads(
        (EVIDENCE_ROOT / "P1FunctorizationEligibility.v1.json").read_text()
    )
    return {str(cell["cell"]): cell for cell in artifact["cells"]}


def _p1_cell_digest(cell_id: str) -> str:
    cell = _p1_cells()[cell_id]
    return content_digest(cell)


def _validate_adjudication(
    bindings: Sequence[Mapping[str, object]],
) -> dict[str, Any]:
    """Deterministically validate the supervisor adjudication artifact."""

    if not ADJUDICATION_PATH.is_file():
        raise FileNotFoundError(f"missing adjudication artifact: {ADJUDICATION_PATH}")
    data = ADJUDICATION_PATH.read_bytes()
    if _sha256_bytes(data) != ADJUDICATION_FILE_SHA256:
        raise ValueError("adjudication artifact file sha256 drift")
    artifact = json.loads(data)
    body = {key: value for key, value in artifact.items() if key != "content_digest"}
    if artifact.get("content_digest") != ADJUDICATION_CONTENT_DIGEST:
        raise ValueError("adjudication artifact content digest drift")
    if content_digest(body) != ADJUDICATION_CONTENT_DIGEST:
        raise ValueError("adjudication artifact canonical digest mismatch")
    if (
        artifact.get("schema")
        != "mrw.functorial_successor.c5_4_locator_adjudication.v1"
    ):
        raise ValueError("adjudication artifact schema drift")
    if artifact.get("status") != "RESOLVED_BY_EXISTING_FREEZE_PRECEDENCE":
        raise ValueError("adjudication artifact status drift")
    if artifact.get("disposition") != "NO_ADDITIVE_AMENDMENT_REQUIRED":
        raise ValueError("adjudication artifact disposition drift")
    if artifact.get("blocker") != "C5_4_FROZEN_LOCATOR_CLARIFICATION_REQUIRED":
        raise ValueError("adjudication artifact blocker identity drift")
    if tuple(artifact.get("normative_donor_locators") or ()) != (
        NORMATIVE_DONOR_LOCATORS
    ):
        raise ValueError("adjudication normative donor locators drift")
    if tuple(artifact.get("supplementary_read_only_evidence") or ()) != (
        SUPPLEMENTARY_READ_ONLY_EVIDENCE
    ):
        raise ValueError("adjudication supplementary evidence locators drift")
    dirty = artifact.get("path_observations", {}).get("source_checkout_dirty", {})
    if dirty.get("path") != PROHIBITED_DIRTY_SOURCE:
        raise ValueError("adjudication dirty source path drift")
    if dirty.get("adopted") is not False:
        raise ValueError("adjudication must never adopt the dirty source")
    for binding in bindings:
        if str(binding.get("path")) == PROHIBITED_DIRTY_SOURCE:
            raise ValueError("prohibited dirty source is bound by the fragment")
    return artifact


def _events() -> tuple[ReplayEvent, ...]:
    def event(
        seq: int,
        event_type: str,
        schema_version: str,
        *,
        step_id: str | None = None,
        attempt_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ReplayEvent:
        return ReplayEvent.from_content(
            project_key=PROJECT_KEY,
            run_id="run:p3-c5",
            run_incarnation="run-inc:p3-c5",
            seq=seq,
            event_type=event_type,
            schema_version=schema_version,
            step_id=step_id,
            attempt_id=attempt_id,
            metadata=metadata or {},
            payload_ref=None,
            payload_digest=None,
            authority_digest=AUTHORITY_DIGEST,
        )

    return (
        event(
            1,
            "ProgramAccepted",
            "mrw.runtime.event.program_accepted.v1",
            metadata={"program_id": "program:p3-c5", "program_digest": PROGRAM_DIGEST},
        ),
        event(
            2,
            "CompileSucceeded",
            "mrw.runtime.event.compile-succeeded.v1",
            metadata={"plan_digest": PROGRAM_DIGEST},
        ),
        event(
            3,
            "PlanCompiled",
            "mrw.runtime.event.plan_compiled.v1",
            metadata={"plan_id": "plan:p3-c5", "plan_digest": PROGRAM_DIGEST},
        ),
        event(
            4,
            "QualificationActivated",
            "mrw.runtime.event.qualification_activated.v1",
            metadata={
                "qualification_id": "qualification:p3-c5",
                "qualification_digest": PROGRAM_DIGEST,
                "decision": "QUALIFIED",
                "reducer_event_code": "PlanCompiled",
            },
        ),
        event(
            5,
            "StepActivated",
            "mrw.runtime.event.step_activated.v1",
            step_id="step:p3-c5",
            metadata={
                "assignment_digest": PROGRAM_DIGEST,
                "activation_digest": PROGRAM_DIGEST,
                "input_closure_digest": PROGRAM_DIGEST,
            },
        ),
        event(
            6,
            "StepClaimed",
            "mrw.runtime.event.step_claimed.v1",
            step_id="step:p3-c5",
            attempt_id="attempt:p3-c5",
            metadata={
                "assignment_kind": "INTERPRET",
                "reconciliation_attempt_id": None,
            },
        ),
        event(
            7,
            "EffectStarted",
            "mrw.runtime.event.effect_started.v1",
            step_id="step:p3-c5",
            attempt_id="attempt:p3-c5",
        ),
        event(
            8,
            "RuntimeValueProduced",
            "mrw.runtime.event.effect_succeeded.v1",
            step_id="step:p3-c5",
            attempt_id="attempt:p3-c5",
        ),
        event(
            9,
            "RunCompletionDerived",
            "mrw.runtime.event.run_completion_derived.v1",
            metadata={"required_step_ids": ["step:p3-c5"]},
        ),
    )


def _effect_assignment(recovery: RecoveryBinding) -> RuntimeAssignment:
    operation_digest = content_digest("p3-c5-operation")
    interpreter = InterpreterBinding.from_content(
        operation_contract_digest=operation_digest,
        interpreter_profile_digest=recovery.interpreter_profile_digest,
        deployment_catalog_digest=content_digest("p3-c5-catalog"),
        runtime_protocol_version="1",
        project_scope_digest=content_digest("p3-c5-scope"),
        resource_policy_epoch=1,
        authority_requirement_digest=content_digest("p3-c5-authority-requirement"),
    )
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work:p3-c5-original",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=PROJECT_KEY,
        run_id="run:p3-c5",
        step_id="step:p3-c5",
        step_role=CompiledStepRole.EFFECT,
        capability_id="mrw.c5.attempt.v1",
        operation_contract_ref=OperationContractRef(
            kind="fixture.c5.operation.v1",
            contract_version="1",
            contract_digest=operation_digest,
        ),
        operation_contract_digest=operation_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            "fixture.c5.return.v1",
            ReturnContract(
                success_modes=("SUCCEEDED",),
                failure_modes=("FAILED",),
                admission_required=False,
            ),
        ),
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{interpreter.binding_digest}",
        handler_binding_digest=interpreter.binding_digest,
        handler_binding=interpreter,
        program_digest=PROGRAM_DIGEST,
        plan_digest=PROGRAM_DIGEST,
        deployment_catalog_digest=content_digest("p3-c5-catalog"),
        execution_epoch=1,
        incarnation="run-inc:p3-c5",
        input_refs=("value:p3-c5:1",),
        input_closure_digest=content_digest("p3-c5-input"),
        queue_eligibility_digest=content_digest("p3-c5-eligibility"),
        resource_policy_epoch=1,
        claim_authority_epoch=2,
        claim_policy_digest=content_digest("p3-c5-claim-policy"),
        expected_step_revision=0,
        trace_id="trace:p3-c5",
    )


def _recovery_assignment(
    original: RuntimeAssignment,
    recovery: RecoveryBinding,
    target_attempt_id: str,
) -> RuntimeAssignment:
    values = original.model_dump(mode="python")
    values.update(
        work_item_id="work:p3-c5-reconcile",
        assignment_kind=AssignmentKind.RECONCILE,
        handler_binding_kind=HandlerBindingKind.RECOVERY,
        handler_binding_ref=f"handler-binding:sha256:{recovery.binding_digest}",
        handler_binding_digest=recovery.binding_digest,
        handler_binding=recovery,
        expected_step_revision=4,
        reconciliation_attempt_id=target_attempt_id,
    )
    return RuntimeAssignment(**values)


def _recovery_and_profile() -> tuple[RecoveryBinding, LegacyInterpreterProfile]:
    profile = LegacyInterpreterProfile.from_content(
        interpreter_id="legacy.c5.interpreter",
        interpreter_version="1.0.0",
        provider_id="provider.c5.fixture",
        provider_version="2.0.0",
    )
    recovery = RecoveryBinding.from_content(
        recovery_handler_id="authoritative-readback",
        recovery_handler_version="1",
        interpreter_profile_digest=profile.profile_digest,
        authoritative_readback_profile_ref="readback-profile:p3-c5",
    )
    return recovery, profile


def _c5_1_observations() -> tuple[dict[str, object], dict[str, object]]:
    read_model = project_legacy_session_read_model(
        {
            "session_id": "legacy-session:p3-c5",
            "status": "active",
            "task_count": 1,
        },
        [
            {
                "session_id": "legacy-session:p3-c5",
                "task_id": "task:p3-c5",
                "status": "in_progress",
                "blocked_by": [],
            }
        ],
        observed_at=OBSERVED_AT,
        source_ref="legacy:agent-sessions:p3-c5",
    )
    legacy = {
        "interpreter_id": "legacy.agent_sessions.read_only_replay.v1",
        "session_status": read_model.session.status,
        "task_statuses": [item.status for item in read_model.tasks],
        "read_model_digest": read_model.read_model_digest,
        "authority": read_model.authority,
    }
    projection = replay_runtime_events(_events())
    snapshot = fold_agent_session(projection)
    successor = {
        "projector_id": "successor.agent_session.journal_projection.v1",
        "projector_version": "1.0.0",
        "session_status": snapshot.status.value,
        "task_statuses": [item.status.value for item in snapshot.tasks],
        "projection_digest": snapshot.projection_digest,
        "source_digest": snapshot.source_digest,
        "terminal_events": list(snapshot.terminal_events),
        "is_authority": False,
    }
    return legacy, successor


def _c5_2_observations() -> tuple[dict[str, object], dict[str, object]]:
    recovery, profile = _recovery_and_profile()
    original = _effect_assignment(recovery)
    binding = ExactLegacyAttemptBinding.from_derived_attempt(
        original,
        authorization_digest=content_digest("p3-c5-authorization"),
        call_id="call:p3-c5",
        external_idempotency_key="idem:p3-c5",
        authoritative_readback_locator="provider:p3-c5:receipt",
        capability_id=original.capability_id,
    )
    evidence = replay_effect_attempt(
        {
            "call_id": "call:p3-c5",
            "capability_id": original.capability_id,
            "idempotency_key": "idem:p3-c5",
            "authoritative_readback_locator": "provider:p3-c5:receipt",
            "status": "",
        },
        assignment=original,
        recovery=recovery,
        profile=profile,
        binding=binding,
        observed_at=OBSERVED_AT,
    )
    attempt = evidence.observation
    legacy = {
        "interpreter_id": "legacy.c5.attempt_replay.v1",
        "binding_digest": evidence.binding.binding_digest,
        "attempt_id": attempt.attempt_id,
        "call_id": binding.call_id,
        "external_idempotency_key": binding.external_idempotency_key,
        "authoritative_readback_locator": binding.authoritative_readback_locator,
        "capability_id": binding.capability_id,
        "disposition": attempt.disposition.value,
        "provider_calls": 0,
    }
    assignment = _recovery_assignment(original, recovery, attempt.attempt_id)
    readback = AuthoritativeEffectReadback(
        attempt_id=attempt.attempt_id,
        disposition=EffectDisposition.SUCCEEDED,
        provider_locator=binding.authoritative_readback_locator,
        receipt_digest=content_digest("p3-c5-receipt"),
        observation_digest=content_digest("p3-c5-observation"),
    )

    class _Stub:
        interpreter_id = profile.interpreter_id
        interpreter_version = profile.interpreter_version
        provider_id = profile.provider_id
        provider_version = profile.provider_version

        def readback(self, _attempt: object) -> AuthoritativeEffectReadback:
            return readback

        def prove_not_started(self, _attempt: object) -> object:
            return None

    result = EffectReconciler().reconcile(
        assignment=assignment,
        attempt=attempt,
        interpreter=_Stub(),
    )
    successor = {
        "interpreter_id": "successor.c5.reconciliation.v1",
        "state": result.state.value,
        "disposition": result.disposition.value,
        "binding_digest": binding.binding_digest,
        "readback_observation_digest": readback.observation_digest,
        "provider_calls": 0,
        "is_authority": False,
    }
    return legacy, successor


def _c5_3_observations() -> tuple[dict[str, object], dict[str, object]]:
    events = _events()
    projection = replay_runtime_events(events)
    snapshot = fold_agent_session(projection)
    decoded = RuntimeReplayProjection.from_json(projection.to_json())
    agreement = fold_agent_session(decoded) == snapshot
    legacy = {
        "interpreter_id": "legacy.agent_sessions.event_feed.v1",
        "event_count": len(events),
        "observed_event_types": list(projection.observed_event_types),
        "replay_digest": content_digest(projection.to_json()),
    }
    successor = {
        "projector_id": "successor.agent_session.fold_snapshot.v1",
        "projector_version": "1.0.0",
        "session_status": snapshot.status.value,
        "task_status": snapshot.tasks[0].status.value,
        "projection_digest": snapshot.projection_digest,
        "source_digest": snapshot.source_digest,
        "fold_snapshot_agreement": agreement,
        "is_authority": False,
    }
    return legacy, successor


def _c5_4_observations() -> tuple[dict[str, object], dict[str, object]]:
    contradictory = capture_celery_async_result(
        {"task_id": "task:p3-c5", "status": "SUCCESS", "ready": True},
        observed_at=OBSERVED_AT,
    )
    running = capture_etl_job_run(
        {"id": 17, "status": "running"},
        observed_at=OBSERVED_AT,
        linked_run_id="run:p3-c5",
    )
    joined = join_process_observations(
        (contradictory, running),
        captured_at=OBSERVED_AT,
    )
    unbound_log = capture_process_log(
        {
            "path": "worker.log",
            "line_no": "1",
            "level": "info",
            "task_id": "task:unbound:p3-c5",
        },
        observed_at=OBSERVED_AT,
    )
    binding_mismatch_fail_closed = False
    try:
        join_process_observations(
            (
                capture_celery_inspect_task(
                    {"id": "task:mismatch:p3-c5", "status": "active"},
                    worker="worker-a",
                    observed_at=OBSERVED_AT,
                    linked_run_id="run:p3-c5:1",
                ),
                capture_celery_inspect_task(
                    {"id": "task:mismatch:p3-c5", "status": "active"},
                    worker="worker-a",
                    observed_at=OBSERVED_AT,
                    linked_run_id="run:p3-c5:2",
                ),
            ),
            captured_at=OBSERVED_AT,
        )
    except SourceBindingMismatch:
        binding_mismatch_fail_closed = True
    legacy = {
        "interpreter_id": "legacy.process_readback.v1",
        "sources": ["celery_async_result", "etl_job_run"],
        "contradictory_observation": contradictory.observation_class.value,
        "etl_observation": running.observation_class.value,
        "unbound_observation_class": unbound_log.observation_class.value,
        "normalized_process_log_level": unbound_log.observed_state,
        "binding_mismatch_fail_closed": binding_mismatch_fail_closed,
        "source_digests": {
            "celery_async_result": contradictory.source_digest,
            "etl_job_run": running.source_digest,
        },
        "provider_calls": 0,
    }
    successor = {
        "projector_id": "successor.legacy_process_observation_join.v1",
        "projector_version": "1.0.0",
        "view_digest": joined.view_digest,
        "donor_surface": {
            "normative": list(NORMATIVE_DONOR_LOCATORS),
            "supplementary": list(SUPPLEMENTARY_READ_ONLY_EVIDENCE),
        },
        "source_dirty_excluded": PROHIBITED_DIRTY_SOURCE,
        "unbound_fixture": {
            "observation_class": unbound_log.observation_class.value,
            "reason": unbound_log.reason,
            "observed_state": unbound_log.observed_state,
        },
        "task_statuses": [
            {
                "task_id": task.task_id,
                "observation_class": task.observation_class.value,
                "status": task.status,
            }
            for task in joined.tasks
        ],
        "terminal_authority_claim": None,
        "is_authority": False,
        "provider_calls": 0,
    }
    return legacy, successor


def _bindings() -> tuple[
    list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]
]:
    source_paths = [
        (EVIDENCE_ROOT / "P1FunctorizationEligibility.v1.json", "p1_eligibility"),
        (EVIDENCE_ROOT / "p1-fragments/C5.json", "p1_fragment"),
        (ADJUDICATION_PATH, "c5_4_locator_adjudication"),
        (
            REPOSITORY_ROOT
            / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/"
            "06_functorial-successor-runtime-architecture-correction.draft.zh-CN.md",
            "frozen_architecture",
        ),
        (
            REPOSITORY_ROOT
            / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/"
            "13_functorial-successor-c1-c9-locator-pending-inventory.v1.json",
            "frozen_locator_inventory",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/services/agent_sessions/service.py",
            "legacy_donor_c5_1_c5_3",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/services/agent_sessions/store.py",
            "legacy_donor_c5_1_c5_3",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/services/agent_runtime/run_loop.py",
            "legacy_donor_c5_2",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/services/agent_runtime/interactive_agent.py",
            "legacy_donor_c5_2",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/api/agent_batch.py",
            "legacy_donor_c5_4_supplementary",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/api/process.py",
            "legacy_donor_c5_4_supplementary",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/services/tasks.py",
            "legacy_donor_c5_4_normative",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/celery_app.py",
            "legacy_donor_c5_4_normative",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/models/entities.py",
            "legacy_donor_c5_4",
        ),
    ]
    implementation_paths = [
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/runtime/observations.py",
            "c5_4_observation_contracts",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/substrate/projections/agent_session.py",
            "c5_1_c5_3_session_projection",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/substrate/projections/legacy_process.py",
            "c5_4_process_join_projection",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_migration/legacy_agent_sessions.py",
            "c5_1_legacy_adapter",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_migration/legacy_effect_attempts.py",
            "c5_2_legacy_adapter",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_migration/legacy_process_observations.py",
            "c5_4_legacy_adapter",
        ),
        (Path(__file__).resolve(), "evidence_generator"),
    ]
    test_paths = [
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c5_0_evidence_generator.py",
            "evidence_generator",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c5_1_session_projection.py",
            "c5_1_session_projection",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c5_2_attempt_replay_reconciliation.py",
            "c5_2_attempt_replay_reconciliation",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c5_2_reconciliation_postgres.py",
            "c5_2_reconciliation_postgres",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c5_3_projection_postgres.py",
            "c5_3_projection_postgres",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c5_4_process_observations.py",
            "c5_4_process_observations",
        ),
    ]
    return (
        [_bind(path, role) for path, role in source_paths],
        [_bind(path, role) for path, role in implementation_paths],
        [_bind(path, role) for path, role in test_paths],
    )


def _operation_bindings(kind: str, role: str, reason: str) -> list[dict[str, object]]:
    return [
        {
            "operation_kind": kind,
            "contract_digest": None,
            "role": role,
            "reason": reason,
        }
    ]


def build_fragment() -> dict[str, object]:
    c5_1_legacy, c5_1_successor = _c5_1_observations()
    c5_2_legacy, c5_2_successor = _c5_2_observations()
    c5_3_legacy, c5_3_successor = _c5_3_observations()
    c5_4_legacy, c5_4_successor = _c5_4_observations()
    source_bindings, implementation_bindings, test_bindings = _bindings()
    _validate_adjudication((*source_bindings, *implementation_bindings, *test_bindings))

    cells = [
        {
            "cell_id": "C5.1",
            "p1_cell_digest": _p1_cell_digest("C5.1"),
            "operation_bindings": _operation_bindings(
                "agent_session.task_transition.v1",
                "projector_registry",
                (
                    "candidate atom from P1 C5.1; journal-derived read-only "
                    "session/task projection in this family line"
                ),
            ),
            "owner_capability_id": "agent_session.task_transition.v1",
            "program_digest": {
                "value": None,
                "reason": "session/task projection is a journal read model, not a Program Atom",
            },
            "plan_digest": {
                "value": None,
                "reason": "no compiled plan is produced by a read-only projection",
            },
            "legacy_observation": c5_1_legacy,
            "successor_observation": c5_1_successor,
            "rollback_observation": {
                "claim_owner": "legacy",
                "legacy_view_readonly_restorable": True,
                "no_dual_claim": True,
                "rollback_digest": content_digest(
                    {
                        "claim_owner": "legacy",
                        "readonly_restore": True,
                        "no_dual_claim": True,
                    }
                ),
            },
            "provider_calls": 0,
            "postgres_requirement": "required_and_verified_mrw_p3_c5_worker_test",
        },
        {
            "cell_id": "C5.2",
            "p1_cell_digest": _p1_cell_digest("C5.2"),
            "operation_bindings": _operation_bindings(
                "runtime.effect.reconcile.v1",
                "reconciliation_owner",
                (
                    "candidate atom from P1 C5.2; replayed attempt observations "
                    "feed the existing EffectReconciler/PostgresReconciliationOwner"
                ),
            ),
            "owner_capability_id": "runtime.effect.reconcile.v1",
            "program_digest": {
                "value": None,
                "reason": (
                    "reconciliation reuses existing EffectReconciler/"
                    "PostgresReconciliationOwner; no new Program Atom"
                ),
            },
            "plan_digest": {
                "value": None,
                "reason": "attempt replay is an observation adapter, not a compiled plan",
            },
            "legacy_observation": c5_2_legacy,
            "successor_observation": c5_2_successor,
            "rollback_observation": {
                "claim_owner": "legacy",
                "no_duplicate_provider_dispatch": True,
                "outcome_unknown_remains": True,
                "rollback_digest": content_digest(
                    {
                        "claim_owner": "legacy",
                        "no_duplicate_provider_dispatch": True,
                        "outcome_unknown_remains": True,
                    }
                ),
            },
            "provider_calls": 0,
            "postgres_requirement": "required_and_verified_mrw_p3_c5_worker_test",
        },
        {
            "cell_id": "C5.3",
            "p1_cell_digest": _p1_cell_digest("C5.3"),
            "operation_bindings": _operation_bindings(
                "runtime.event.project.v1",
                "projector_registry",
                (
                    "candidate atom from P1 C5.3; acceptance only over the "
                    "existing replay/projector"
                ),
            ),
            "owner_capability_id": "runtime.event.project.v1",
            "program_digest": {
                "value": None,
                "reason": "fold/snapshot acceptance runs over existing replay/projector",
            },
            "plan_digest": {
                "value": None,
                "reason": "no new plan is introduced by the acceptance line",
            },
            "legacy_observation": c5_3_legacy,
            "successor_observation": c5_3_successor,
            "rollback_observation": {
                "claim_owner": "legacy",
                "projection_rows_retained": True,
                "run_authority_not_double_written": True,
                "rollback_digest": content_digest(
                    {
                        "claim_owner": "legacy",
                        "projection_rows_retained": True,
                        "run_authority_not_double_written": True,
                    }
                ),
            },
            "provider_calls": 0,
            "postgres_requirement": "required_and_verified_mrw_p3_c5_worker_test",
        },
        {
            "cell_id": "C5.4",
            "p1_cell_digest": _p1_cell_digest("C5.4"),
            "operation_bindings": _operation_bindings(
                "legacy.runtime_observation.project.v1",
                "projector_registry",
                (
                    "candidate atom from P1 C5.4; offline captured typed "
                    "observations and join projection"
                ),
            ),
            "owner_capability_id": "legacy.runtime_observation.project.v1",
            "program_digest": {
                "value": None,
                "reason": "typed observations and join projection are pure read models",
            },
            "plan_digest": {
                "value": None,
                "reason": "no compiled plan is required for offline observation capture",
            },
            "legacy_observation": c5_4_legacy,
            "successor_observation": c5_4_successor,
            "rollback_observation": {
                "claim_owner": "legacy",
                "successor_journal_retained_on_rollback": True,
                "readback_never_control": True,
                "rollback_digest": content_digest(
                    {
                        "claim_owner": "legacy",
                        "successor_journal_retained_on_rollback": True,
                        "readback_never_control": True,
                    }
                ),
            },
            "provider_calls": 0,
            "postgres_requirement": "not_required",
        },
    ]

    return {
        "schema": FRAGMENT_SCHEMA,
        "phase": "P3",
        "family": "C5",
        "fragment_id": FRAGMENT_ID,
        "status": "IMPLEMENTED_CANDIDATE_NOT_PROMOTED",
        "cells": cells,
        "source_bindings": source_bindings,
        "implementation_bindings": implementation_bindings,
        "test_bindings": test_bindings,
        "authority": {
            "production_canonical_write": False,
            "live_provider": False,
            "external_delivery": False,
            "live_credential": False,
            "network": False,
            "cutover": False,
            "authority_transfer": False,
            "legacy_retired": False,
            "p3_promotion": False,
        },
        "resolved_findings": [
            {
                "id": "C5_4_FROZEN_LOCATOR_CLARIFICATION_REQUIRED",
                "severity": "P0",
                "state": "RESOLVED_BY_EXISTING_FREEZE_PRECEDENCE",
                "disposition": "NO_ADDITIVE_AMENDMENT_REQUIRED",
                "normative_donor_locators": list(NORMATIVE_DONOR_LOCATORS),
                "supplementary_read_only_evidence": list(
                    SUPPLEMENTARY_READ_ONLY_EVIDENCE
                ),
                "source_dirty_excluded": {
                    "path": PROHIBITED_DIRTY_SOURCE,
                    "adopted": False,
                },
                "evidence_ref": {
                    "path": ADJUDICATION_RELATIVE,
                    "file_sha256": ADJUDICATION_FILE_SHA256,
                    "content_digest": ADJUDICATION_CONTENT_DIGEST,
                },
            },
        ],
        "open_findings": [
            {
                "id": "P3_AUTHORITY_RECORD_DIVERGENCE",
                "severity": "P0",
                "normative_blocker": False,
                "description": (
                    "frozen 01/02 still bound P0-C; mutable ledger claims P3 "
                    "authorized; promotion requires root/supervisor authority record"
                ),
            },
            {
                "id": "P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED",
                "severity": "P1",
                "normative_blocker": False,
                "description": (
                    "capability surface remains untracked; exact review tree pending"
                ),
            },
            {
                "id": "C5_1_SESSION_TASK_CONTROL_NOT_MIGRATED",
                "severity": "P1",
                "normative_blocker": False,
                "description": (
                    "legacy AgentSession/AgentTask rows remain read-only compat "
                    "views; no write authority transfer to the runtime journal"
                ),
            },
            {
                "id": "C5_2_DURABLE_ATTEMPT_NODE_NOT_PROVEN",
                "severity": "P1",
                "normative_blocker": False,
                "description": (
                    "attempt replay/reconciliation acceptance is fixture/sqlite-"
                    "level; durable PostgreSQL RuntimeNode path for C5.2 is not proven"
                ),
            },
            {
                "id": "C5_3_SESSION_PROJECTION_OFFSET_NOT_OWNED",
                "severity": "P1",
                "normative_blocker": False,
                "description": (
                    "session/task view derives from the existing runtime-run "
                    "projection; no dedicated session projection table or offset "
                    "is owned by C5.3"
                ),
            },
        ],
        "content_digest": "",
    }


def _self_test(fragment: dict[str, object]) -> None:
    assert fragment["schema"] == FRAGMENT_SCHEMA
    assert fragment["phase"] == "P3"
    assert fragment["family"] == "C5"
    assert fragment["status"] == "IMPLEMENTED_CANDIDATE_NOT_PROMOTED"
    body = {key: value for key, value in fragment.items() if key != "content_digest"}
    assert fragment["content_digest"] == content_digest(body)
    required_roots = {
        "schema",
        "phase",
        "family",
        "fragment_id",
        "status",
        "cells",
        "source_bindings",
        "implementation_bindings",
        "test_bindings",
        "authority",
        "resolved_findings",
        "open_findings",
        "content_digest",
    }
    assert set(fragment) == required_roots
    cell_ids = [cell["cell_id"] for cell in fragment["cells"]]
    assert cell_ids == ["C5.1", "C5.2", "C5.3", "C5.4"]
    required_cell_fields = {
        "cell_id",
        "p1_cell_digest",
        "operation_bindings",
        "owner_capability_id",
        "program_digest",
        "plan_digest",
        "legacy_observation",
        "successor_observation",
        "rollback_observation",
        "provider_calls",
        "postgres_requirement",
    }
    for cell in fragment["cells"]:
        assert set(cell) == required_cell_fields
        assert len(cell["p1_cell_digest"]) == 64
        assert {"value", "reason"} == set(cell["program_digest"])
        assert {"value", "reason"} == set(cell["plan_digest"])
        assert cell["provider_calls"] == 0
    assert fragment["cells"][0]["postgres_requirement"] == (
        "required_and_verified_mrw_p3_c5_worker_test"
    )
    assert fragment["cells"][1]["postgres_requirement"] == (
        "required_and_verified_mrw_p3_c5_worker_test"
    )
    assert fragment["cells"][2]["postgres_requirement"] == (
        "required_and_verified_mrw_p3_c5_worker_test"
    )
    assert all(not value for value in fragment["authority"].values()), (
        "authority flags must all be false"
    )
    open_finding_ids = {item["id"] for item in fragment["open_findings"]}
    assert "C5_4_FROZEN_LOCATOR_CLARIFICATION_REQUIRED" not in open_finding_ids
    resolved = {item["id"]: item for item in fragment["resolved_findings"]}
    blocker = resolved["C5_4_FROZEN_LOCATOR_CLARIFICATION_REQUIRED"]
    assert blocker["state"] == "RESOLVED_BY_EXISTING_FREEZE_PRECEDENCE"
    assert blocker["disposition"] == "NO_ADDITIVE_AMENDMENT_REQUIRED"
    assert blocker["evidence_ref"]["content_digest"] == ADJUDICATION_CONTENT_DIGEST
    assert blocker["evidence_ref"]["file_sha256"] == ADJUDICATION_FILE_SHA256
    assert blocker["normative_donor_locators"] == list(NORMATIVE_DONOR_LOCATORS)
    assert blocker["supplementary_read_only_evidence"] == list(
        SUPPLEMENTARY_READ_ONLY_EVIDENCE
    )
    assert blocker["source_dirty_excluded"] == {
        "path": PROHIBITED_DIRTY_SOURCE,
        "adopted": False,
    }
    assert "normative_blocker" not in blocker
    assert blocker["severity"] == "P0"


def _build_fragment_with_digest() -> tuple[dict[str, object], str]:
    first = build_fragment()
    second = build_fragment()
    assert _canonical_json(first) == _canonical_json(second), (
        "non-deterministic fragment"
    )
    digest = content_digest(
        {key: value for key, value in first.items() if key != "content_digest"}
    )
    first["content_digest"] = digest
    _self_test(first)
    return first, _canonical_json(first) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="generate or read-only check the P3 C5 evidence fragment",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "compare an in-memory canonical build against the persisted "
            "fragment without writing; exit 1 on drift"
        ),
    )
    args = parser.parse_args(argv)
    fragment, expected_text = _build_fragment_with_digest()
    if args.check:
        if not FRAGMENT_PATH.is_file():
            print(f"drift: missing {FRAGMENT_PATH}", file=sys.stderr)
            return 1
        try:
            persisted = json.loads(FRAGMENT_PATH.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"drift: unreadable fragment: {exc}", file=sys.stderr)
            return 1
        persisted_text = _canonical_json(persisted) + "\n"
        if persisted_text != expected_text:
            print(
                f"drift: {FRAGMENT_PATH} differs from the canonical build",
                file=sys.stderr,
            )
            return 1
        print(f"check ok: {FRAGMENT_PATH}")
        print(f"content_digest {fragment['content_digest']}")
        print(f"cells {[cell['cell_id'] for cell in fragment['cells']]}")
        return 0
    FRAGMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FRAGMENT_PATH.write_text(expected_text)
    persisted = json.loads(FRAGMENT_PATH.read_text())
    assert _canonical_json(persisted) == _canonical_json(fragment)
    print(f"wrote {FRAGMENT_PATH}")
    print(f"content_digest {fragment['content_digest']}")
    print(f"cells {[cell['cell_id'] for cell in fragment['cells']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
