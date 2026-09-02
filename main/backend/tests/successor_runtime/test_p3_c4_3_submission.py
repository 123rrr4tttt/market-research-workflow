"""C4.3 durable submission contracts, codec/program/interpreter, repository tests."""

from __future__ import annotations

import hashlib

import pytest

from app.successor_runtime.capabilities import agent_batch_c4 as c4
from app.successor_runtime.capabilities.agent_batch_c4 import (
    AgentBatchSubmission,
    AgentBatchSubmissionItem,
    build_agent_batch_submission_digest,
)
from app.successor_runtime.substrate.postgres.agent_batch_c4 import (
    C4SubmissionConflict,
    C4SubmissionNotFound,
    InMemoryC4SubmissionRepository,
)
from app.successor_runtime.substrate.postgres.idempotency import (
    IdempotencyBinding,
)

from .p3_c4_fixture import (
    PROJECT_KEY,
    REGISTRY_REVISION,
    RESOLVED_SCHEMA,
    SCOPE_DIGEST,
    SCOPE_INCARNATION,
)


def _submission(**overrides: object) -> AgentBatchSubmission:
    values = {
        "schema_version": "mrw.successor.agent-batch.c4-3.payload.v1",
        "operation_kind": "agent_batch.submit.v1",
        "submission_id": "sub:c4-3:001",
        "project_key": PROJECT_KEY,
        "resolved_schema": RESOLVED_SCHEMA,
        "registry_revision": REGISTRY_REVISION,
        "scope_incarnation": SCOPE_INCARNATION,
        "scope_digest": SCOPE_DIGEST,
        "capability_id": c4.SUBMISSION_OWNER,
        "logical_request_id": "request:c4-3:001",
        "request_digest": "",
        "jobs": (
            AgentBatchSubmissionItem(
                job_id="job:1",
                channel="search.market",
                query_terms=("机器人",),
                lane="main",
            ),
        ),
        "authority_snapshot_ref": "authority:snapshot:001",
        "resource_request_ref": "resource:request:001",
    }
    values.update(overrides)
    values["request_digest"] = values["request_digest"] or "0" * 64
    return AgentBatchSubmission(**values)


def _binding(**overrides: object) -> IdempotencyBinding:
    submission = _submission()
    values = {
        "idempotency_id": "idem:c4-3:001",
        "capability_id": c4.SUBMISSION_OWNER,
        "logical_request_id": "request:c4-3:001",
        "operation_kind": c4.SUBMISSION_KIND,
        "request_digest": build_agent_batch_submission_digest(submission),
        "run_id": "run:c4-3:001",
    }
    values.update(overrides)
    return IdempotencyBinding(**values)


def test_submission_contract_binds_scope_digest_and_request_digest() -> None:
    submission = _submission()
    assert submission.submission_digest
    assert submission.scope_digest == SCOPE_DIGEST
    assert submission.project_key == PROJECT_KEY
    assert submission.capability_id == c4.SUBMISSION_OWNER
    digest = build_agent_batch_submission_digest(submission)
    assert digest
    assert len(digest) == 64


def test_in_memory_repository_replays_exact_digest_and_conflicts_on_drift() -> None:
    repo = InMemoryC4SubmissionRepository()
    binding = _binding()
    reserved, state = repo.reserve(binding)
    assert state == "STARTED"
    assert reserved.request_digest == binding.request_digest

    replay, replay_state = repo.reserve(binding)
    assert replay.request_digest == binding.request_digest
    assert replay_state == "STARTED"

    drift = _binding(request_digest="1" * 64)
    with pytest.raises(C4SubmissionConflict):
        repo.reserve(drift)


def test_in_memory_repository_records_terminal_state_and_typed_receipt() -> None:
    repo = InMemoryC4SubmissionRepository()
    binding = _binding()
    repo.reserve(binding)
    updated = repo.record_terminal(
        capability_id=binding.capability_id,
        logical_request_id=binding.logical_request_id,
        acceptance_state="ACCEPTED",
        receipt_ref="receipt:c4-3:001",
    )
    assert updated.state == "TERMINAL"
    assert updated.terminal_observation_ref == "receipt:c4-3:001"
    acceptance_state, receipt_ref = repo.receipt(
        capability_id=binding.capability_id,
        logical_request_id=binding.logical_request_id,
    )
    assert acceptance_state == "ACCEPTED"
    assert receipt_ref == "receipt:c4-3:001"
    loaded = repo.load(
        capability_id=binding.capability_id,
        logical_request_id=binding.logical_request_id,
    )
    assert loaded.state == "TERMINAL"


def test_acceptance_status_stays_in_typed_receipt_not_db_enum() -> None:
    assert c4.C4AcceptanceState.__args__ == (
        "ACCEPTED",
        "PARTIALLY_ACCEPTED",
        "REJECTED",
        "CONFLICT",
    )
    assert "STARTED" not in c4.C4AcceptanceState.__args__
    assert "TERMINAL" not in c4.C4AcceptanceState.__args__
    # Generic idempotency root stays STARTED/TERMINAL/SUPERSEDED.
    binding = _binding()
    assert binding.state == "STARTED"
    terminal = IdempotencyBinding(
        idempotency_id="idem:c4-3:002",
        capability_id=c4.SUBMISSION_OWNER,
        logical_request_id="request:c4-3:002",
        operation_kind=c4.SUBMISSION_KIND,
        request_digest=hashlib.sha256(b"x").hexdigest(),
        run_id="run:c4-3:002",
        state="TERMINAL",
        terminal_observation_ref="receipt:c4-3:002",
    )
    assert terminal.state == "TERMINAL"


def test_submission_payload_codec_restores_nested_typed_jobs() -> None:
    from app.successor_migration.legacy_agent_batch import (
        build_successor_agent_batch_c4_submission_binding,
    )
    from app.successor_runtime.capabilities import agent_batch_c4 as c4
    from app.successor_runtime.capabilities.agent_batch_c4_interpreters import (
        AgentBatchC4SubmissionSuccessorInterpreter,
        InterpreterSuccess,
    )
    from app.successor_runtime.capabilities.agent_batch_c4_program import (
        build_agent_batch_c4_3_program,
        compile_agent_batch_c4_program,
    )

    from .p3_c4_fixture import (
        DEPLOYMENT_CATALOG_DIGEST,
        catalog,
        registry,
    )

    submission = _submission()
    codec = c4.build_agent_batch_c4_bundle().codec_by_kind(c4.SUBMISSION_KIND)
    encoded = codec.encode_payload(submission)
    decoded = codec.decode_payload(encoded)
    assert decoded.submission_id == submission.submission_id
    assert decoded.logical_request_id == submission.logical_request_id
    assert decoded.jobs
    assert all(isinstance(job, c4.AgentBatchSubmissionItem) for job in decoded.jobs)
    assert decoded.jobs[0].job_id == "job:1"
    assert decoded.jobs[0].query_terms == ("机器人",)

    program = build_agent_batch_c4_3_program(
        payload=submission,
        catalog=catalog(),
        program_id="program:p3-c4-3-unit",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_agent_batch_c4_program(
        program,
        catalog(),
        operation_contracts=registry(),
    )
    effect_steps = [
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    ]
    assert len(effect_steps) == 1
    ref = program.root.operation.contract_ref
    binding = build_successor_agent_batch_c4_submission_binding(
        contract_digest=ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    from dataclasses import dataclass

    @dataclass(frozen=True, slots=True)
    class _Scope:
        project_key: str
        registry_revision: int
        incarnation: str
        resolved_schema: str
        scope_digest: str

    scope = _Scope(
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        incarnation=SCOPE_INCARNATION,
        resolved_schema=RESOLVED_SCHEMA,
        scope_digest=SCOPE_DIGEST,
    )
    outcome = AgentBatchC4SubmissionSuccessorInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=program.root.operation.payload_ref,
        payload=submission,
        project_scope=scope,
        catalog=catalog(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=binding,
    )
    assert isinstance(outcome, InterpreterSuccess)
    assert outcome.value.state == "ACCEPTED"
    assert outcome.value.accepted_items == ("job:1",)
    assert outcome.value.receipt_digest


def test_in_memory_record_terminal_cannot_terminate_another_capability() -> None:
    repo = InMemoryC4SubmissionRepository()
    first = _binding(
        idempotency_id="idem:c4-3:cap-a",
        capability_id="capability.a",
        logical_request_id="request:shared",
        operation_kind="agent_batch.submit.v1",
        request_digest=hashlib.sha256(b"shared-a").hexdigest(),
        run_id="run:a",
    )
    second = _binding(
        idempotency_id="idem:c4-3:cap-b",
        capability_id="capability.b",
        logical_request_id="request:shared",
        operation_kind="agent_batch.submit.v1",
        request_digest=hashlib.sha256(b"shared-b").hexdigest(),
        run_id="run:b",
    )
    repo.reserve(first)
    repo.reserve(second)
    terminated = repo.record_terminal(
        capability_id="capability.a",
        logical_request_id="request:shared",
        acceptance_state="ACCEPTED",
        receipt_ref="receipt:a",
    )
    assert terminated.capability_id == "capability.a"
    assert terminated.state == "TERMINAL"
    # Cross-capability binding with the same logical request id stays STARTED.
    assert (
        repo.load(
            capability_id="capability.b", logical_request_id="request:shared"
        ).state
        == "STARTED"
    )
    with pytest.raises(C4SubmissionNotFound):
        repo.receipt(capability_id="capability.b", logical_request_id="request:shared")
