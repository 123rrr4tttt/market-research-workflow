"""Independent single-item dispatch witness: contract, program, codec, ACK."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.successor_runtime.capabilities import batch_task as c4
from app.successor_runtime.capabilities.batch_task_interpreters import (
    DispatchSingleBindingMismatch,
    build_successor_agent_batch_c4_dispatch_binding,
    require_exact_dispatch_single_binding,
)
from app.successor_runtime.capabilities.batch_task_program import (
    build_batch_task_single_dispatch_program,
    compile_batch_task_program,
)
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.plan import ExecutionPlan
from app.successor_runtime.language.program import ProgramSpec

from .p3_c4_fixture import (
    ordered_dispatch_program,
    DEPLOYMENT_CATALOG_DIGEST,
    PROGRAM_ID,
    PROJECT_KEY,
    REGISTRY_REVISION,
    RESOLVED_SCHEMA,
    SCOPE_DIGEST,
    SCOPE_INCARNATION,
)


def _dispatch_payload(
    *,
    dispatch_id: str = "dispatch:batch-task:001",
    item: c4.AgentBatchSubmissionItem | None = None,
    payload_digest: str = "",
    scope_digest: str = SCOPE_DIGEST,
) -> c4.BatchTaskSingleDispatchPayload:
    return c4.BatchTaskSingleDispatchPayload(
        schema_version=c4.DISPATCH_SINGLE_PAYLOAD_SCHEMA,
        operation_kind=c4.DISPATCH_SINGLE_KIND,
        dispatch_id=dispatch_id,
        project_key=PROJECT_KEY,
        resolved_schema=RESOLVED_SCHEMA,
        registry_revision=REGISTRY_REVISION,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=scope_digest,
        capability_id=c4.BATCH_TASK_OWNER,
        item=item
        or c4.AgentBatchSubmissionItem(
            job_id="job:1",
            channel="search.market",
            query_terms=("机器人",),
        ),
        lane="main",
        queue="celery",
        payload_digest=payload_digest,
    )


def _compile(
    payload: c4.BatchTaskSingleDispatchPayload,
) -> tuple[ProgramSpec, ExecutionPlan, OperationContractCatalogSnapshot]:
    catalog = c4.build_batch_task_single_dispatch_catalog()
    registry = c4.build_batch_task_single_dispatch_registry()
    program = build_batch_task_single_dispatch_program(
        payload=payload,
        catalog=catalog,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_batch_task_program(
        program, catalog, operation_contracts=registry
    )
    return program, plan, catalog


def test_dispatch_single_contract_has_exact_installed_endpoints() -> None:
    contract = c4.build_batch_task_single_dispatch_contract()
    assert contract.ref.kind == c4.DISPATCH_SINGLE_KIND
    assert contract.input_type.type_id == c4.DISPATCH_SINGLE_PAYLOAD_TYPE.type_id
    assert contract.output_type.type_id == c4.DISPATCH_SINGLE_ACK_TYPE.type_id

    assert contract.owner_capability_id == c4.DISPATCH_SINGLE_OWNER


def test_dispatch_single_profiles_are_real_semantics() -> None:
    profiles = c4.build_batch_task_single_dispatch_profiles()
    assert profiles.effect.execution_class == "EFFECTFUL"
    assert profiles.effect.network_required is True
    assert profiles.effect.external_visibility == "INTERNAL_ONLY"
    assert profiles.effect.irreversible is False
    assert profiles.effect.human_approval_required is False
    assert profiles.resource.resource_classes == ("NETWORK_IO",)
    assert profiles.failure.retryable is False
    assert profiles.failure.retryable_failure_kinds == ()
    assert profiles.failure.unknown_outcome_supported is True
    assert profiles.failure.readback_or_compensation == "readback"


def test_dispatch_single_program_compiles_to_one_effect_step() -> None:
    payload = _dispatch_payload()
    program, plan, _ = _compile(payload)
    effect_steps = [
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    ]
    assert len(effect_steps) == 1
    assert effect_steps[0].operation_contract_ref.kind == c4.DISPATCH_SINGLE_KIND
    assert program.root.operation.payload_ref.content_digest


def test_ordered_dispatch_program_compiles_to_distinct_effect_steps() -> None:
    payload_a = _dispatch_payload()
    payload_b = _dispatch_payload(dispatch_id="dispatch:batch-task:002")
    catalog = c4.build_batch_task_single_dispatch_catalog()
    program = ordered_dispatch_program(
        payloads=[payload_a, payload_b],
        catalog=catalog,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_batch_task_program(program, catalog, operation_contracts=c4.build_batch_task_single_dispatch_registry())
    effect_steps = [
        step for step in plan.ordered_steps if step.step_kind == "EFFECT"
    ]
    assert len(effect_steps) == 2
    operation_ids = {step.operation_id for step in effect_steps}
    assert operation_ids == {
        f"{c4.DISPATCH_SINGLE_OPERATION_ID}:{payload_a.dispatch_id}",
        f"{c4.DISPATCH_SINGLE_OPERATION_ID}:{payload_b.dispatch_id}",
    }
    metadata = dict(program.metadata)
    assert metadata["ordered_element_count"] == 2


def test_dispatch_single_payload_codec_roundtrip_restores_item() -> None:
    contract = c4.build_batch_task_single_dispatch_contract()
    codec = c4.build_batch_task_single_dispatch_payload_codec(contract.ref)
    payload = _dispatch_payload()
    decoded = codec.decode_payload(codec.encode_payload(payload))
    assert decoded.dispatch_id == payload.dispatch_id
    assert isinstance(decoded.item, c4.AgentBatchSubmissionItem)
    assert decoded.item.job_id == "job:1"
    assert decoded.item.query_terms == ("机器人",)
    assert decoded.runtime_readback == {}


def test_dispatch_single_ack_codec_roundtrip_flat() -> None:
    contract = c4.build_batch_task_single_dispatch_contract()
    codec = c4.build_batch_task_single_dispatch_ack_codec(contract.ref)
    ack = c4.BatchTaskSingleDispatchAck(
        schema_version=c4.DISPATCH_SINGLE_ACK_SCHEMA,
        operation_kind=c4.DISPATCH_SINGLE_KIND,
        dispatch_id="dispatch:batch-task:001",
        channel="search.market",
        celery_task_id="celery-task-real",
        lane="main",
        queue="celery",
    )
    decoded = codec.decode_payload(codec.encode_payload(ack))
    assert decoded.dispatch_id == ack.dispatch_id
    assert decoded.celery_task_id == ack.celery_task_id
    assert decoded.queue == ack.queue
    assert decoded.ack_digest == ack.ack_digest


def test_dispatch_single_ack_requires_celery_task_id() -> None:
    with pytest.raises(ValueError, match="celery task identity"):
        c4.BatchTaskSingleDispatchAck(
            schema_version=c4.DISPATCH_SINGLE_ACK_SCHEMA,
            operation_kind=c4.DISPATCH_SINGLE_KIND,
            dispatch_id="dispatch:batch-task:001",
            channel="search.market",
            celery_task_id="",
            lane="main",
            queue="celery",
        )


def test_dispatch_single_ack_is_not_business_terminal() -> None:
    ack = c4.BatchTaskSingleDispatchAck(
        schema_version=c4.DISPATCH_SINGLE_ACK_SCHEMA,
        operation_kind=c4.DISPATCH_SINGLE_KIND,
        dispatch_id="dispatch:batch-task:001",
        channel="search.market",
        celery_task_id="celery-task-real",
        lane="main",
        queue="celery",
    )
    assert ack.celery_task_id == "celery-task-real"
    assert ack.ack_digest
    assert not hasattr(ack, "state")


def test_dispatch_single_ack_rejects_forged_digest() -> None:
    with pytest.raises(ValueError, match="does not match content"):
        c4.BatchTaskSingleDispatchAck(
            schema_version=c4.DISPATCH_SINGLE_ACK_SCHEMA,
            operation_kind=c4.DISPATCH_SINGLE_KIND,
            dispatch_id="dispatch:batch-task:001",
            channel="search.market",
            celery_task_id="celery-task-real",
            lane="main",
            queue="celery",
            ack_digest="0" * 64,
        )


def test_dispatch_task_id_is_server_derived_and_deterministic() -> None:
    task_id = c4.derive_dispatch_task_id(
        project_scope_digest=SCOPE_DIGEST,
        capability_id=c4.BATCH_TASK_OWNER,
        dispatch_id="dispatch:batch-task:001",
    )
    assert len(task_id) == 64
    assert (
        task_id
        == c4.derive_dispatch_task_id(
            project_scope_digest=SCOPE_DIGEST,
            capability_id=c4.BATCH_TASK_OWNER,
            dispatch_id="dispatch:batch-task:001",
        )
    )
    assert (
        task_id
        != c4.derive_dispatch_task_id(
            project_scope_digest=SCOPE_DIGEST,
            capability_id=c4.BATCH_TASK_OWNER,
            dispatch_id="dispatch:batch-task:002",
        )
    )


def test_dispatch_run_id_is_derived_from_scope_actor_and_logical_request() -> None:
    run_id = c4.derive_dispatch_run_id(
        project_scope_digest=SCOPE_DIGEST,
        actor_id="actor:1",
        logical_request_id="request-1",
    )
    assert len(run_id) == 64
    assert (
        run_id
        == c4.derive_dispatch_run_id(
            project_scope_digest=SCOPE_DIGEST,
            actor_id="actor:1",
            logical_request_id="request-1",
        )
    )
    assert (
        run_id
        != c4.derive_dispatch_run_id(
            project_scope_digest=SCOPE_DIGEST,
            actor_id="actor:1",
            logical_request_id="request-2",
        )
    )
    assert (
        run_id
        != c4.derive_dispatch_run_id(
            project_scope_digest=SCOPE_DIGEST,
            actor_id="actor:2",
            logical_request_id="request-1",
        )
    )


def test_dispatch_single_payload_rejects_unsupported_channel() -> None:
    with pytest.raises(ValueError, match="unsupported dispatch item channel"):
        _dispatch_payload(
            item=c4.AgentBatchSubmissionItem(job_id="job:1", channel="unknown"),
        )


def test_dispatch_single_payload_rejects_forged_digest() -> None:
    with pytest.raises(ValueError, match="does not match content"):
        _dispatch_payload(payload_digest="0" * 64)


def test_dispatch_single_validate_exact_binding_accepts_and_rejects_drift() -> None:
    payload = _dispatch_payload()
    program, plan, catalog = _compile(payload)
    ref = program.root.operation.contract_ref
    binding = build_successor_agent_batch_c4_dispatch_binding(
        contract_digest=ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )

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
    accepted = require_exact_dispatch_single_binding(
        program=program,
        plan=plan,
        contract_ref=ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=scope,
        catalog=catalog,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=binding,
    )
    assert accepted["program_digest"] == program.program_digest

    drifted_binding = build_successor_agent_batch_c4_dispatch_binding(
        contract_digest=ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest="f" * 64,
    )
    with pytest.raises(DispatchSingleBindingMismatch):
        require_exact_dispatch_single_binding(
            program=program,
            plan=plan,
            contract_ref=ref,
            payload_ref=program.root.operation.payload_ref,
            payload=payload,
            project_scope=scope,
            catalog=catalog,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            binding=drifted_binding,
        )


def test_operation_profiles_reject_caller_supplied_digest() -> None:
    from app.successor_runtime.capabilities.profiles import build_operation_profiles
    with pytest.raises(ValueError, match="digest is derived"):
        build_operation_profiles(identity="invalid", semantic={"profile_digest": "forged"},
            effect={}, resource={}, failure={}, authority={}, interpreter={}, observation={})
