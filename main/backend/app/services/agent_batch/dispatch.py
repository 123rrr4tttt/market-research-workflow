"""Shared successor fixed-N dispatch submission and ordered ACK readback."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, TypeVar

from datetime import datetime
import json

from app.composition.production import submit_installed_program, read_installed_program, read_installed_program_outputs
from app.successor_runtime.substrate.postgres.runtime_journal import ExactBindingConflict
from app.models.base import engine
from app.successor_runtime.capabilities import batch_task, batch_business
from app.successor_runtime.capabilities.catalog import build_operation_catalog
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.capabilities.batch_task_program import (
    build_batch_business_program,
)
from app.successor_runtime.capabilities.checksum import CanonicalJsonObject, canonical_json
from app.successor_runtime.capabilities.codecs import PayloadCodec
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.program import program_atoms
from app.successor_runtime.research.object_types import ObjectType


T = TypeVar("T")


def build_dispatch_submission_inputs(
    *,
    payloads: tuple[batch_task.BatchTaskSingleDispatchPayload, ...],
    program_id: str,
    incarnation: str,
) -> Annotated[tuple[Any, Any, Any, tuple[tuple[Any, bytes], ...], dict[str, tuple[int, str]]], 'kit:non-authoritative derived_as=program fact_source=typed_batch_payloads_and_runtime_scope witness=test:test_post_waits_for_real_business_outputs_in_input_order']:
    """Pure fixed-N dispatch Program/Plan/value/binding lowering."""

    contract = batch_task.build_batch_task_single_dispatch_contract()
    contracts = (contract, batch_business.build_batch_business_wait_contract())
    catalog = build_operation_catalog(contracts, catalog_id="batch.business-ordered.v2", catalog_version="2")
    registry = OperationContractRegistry(catalog, contracts)
    first = payloads[0]
    program = build_batch_business_program(
        payloads=payloads, catalog=catalog, program_id=program_id,
        project_key=first.project_key, project_registry_revision=first.registry_revision,
        project_scope_digest=first.scope_digest,
    )
    plan = compile_program(program, catalog, operation_contracts=registry)
    steps = tuple(step for step in plan.ordered_steps if step.step_kind == "EFFECT")
    atom_by_operation_id = {
        atom.operation.operation_id: atom.operation.payload_ref
        for atom in program_atoms(program.root)
    }
    canonical_bindings = {step.step_id: (0, incarnation) for step in steps}
    payload_bytes = {
        f"{batch_task.DISPATCH_SINGLE_OPERATION_ID}:{payload.dispatch_id}": canonical_json(payload).encode()
        for payload in payloads
    }
    values = tuple(
        (atom_by_operation_id[step.operation_id], payload_bytes[step.operation_id])
        for step in steps
        if step.operation_id in payload_bytes
    )
    return catalog, registry, program, values, canonical_bindings


def submit_dispatch_run(
    *,
    run_id: str,
    payloads: tuple[batch_task.BatchTaskSingleDispatchPayload, ...],
    project_key: str,
    actor_id: str,
    queue: str,
    idempotency_key: str | None,
    now: datetime,
) -> tuple[str, tuple[str, ...]]:
    """Submit one fixed-N dispatch Program and dispatch its persisted work items."""

    logical_request_id = str(idempotency_key or payloads[0].dispatch_id)
    idempotency_id = f"idem-{run_id}"
    incarnation = "dispatch-incarnation"
    trace_id = payloads[0].trace_id or f"trace-{run_id}"
    catalog, registry, program, values, canonical_bindings = build_dispatch_submission_inputs(
        payloads=payloads, program_id=f"program:{run_id}",
        incarnation=incarnation,
    )
    run, work_item_ids = submit_installed_program(
        engine=engine, project_key=project_key, actor_id=actor_id, program=program,
        operation_catalog=catalog, operation_contracts=registry, values=values,
        idempotency_id=idempotency_id, identity_capability_id=payloads[0].capability_id,
        logical_request_id=logical_request_id,
        identity_operation_kind=payloads[0].operation_kind, run_id=run_id,
        incarnation=incarnation, canonical_bindings=canonical_bindings,
        approvals_by_step={}, trace_id=trace_id, now=now, queue=queue,
    )
    return str(run["run_id"]), work_item_ids


def load_dispatch_run(
    *,
    run_id: str,
    project_key: str,
    actor_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], tuple[Mapping[str, object], ...]]:
    """Project ordered item facts from the original Plan and exact typed outputs."""

    run, steps, events = read_installed_program(
        engine=engine, project_key=project_key, actor_id=actor_id, run_id=run_id,
    )
    outputs = {step_id: (ref, exact) for step_id, ref, exact in read_installed_program_outputs(
        engine=engine, project_key=project_key, actor_id=actor_id, run_id=run_id,
    )}
    wait_steps = {str(step["operation_id"]).removeprefix(batch_business.BUSINESS_WAIT_KIND + ":"): step
                  for step in steps if step["operation_kind"] == batch_business.BUSINESS_WAIT_KIND}
    dispatch_contract = batch_task.build_batch_task_single_dispatch_contract()
    wait_contract = batch_business.build_batch_business_wait_contract()
    ack_codec = batch_task.build_batch_task_single_dispatch_ack_codec(dispatch_contract.ref)
    result_codec = batch_business.build_batch_business_wait_result_codec(wait_contract.ref)

    def decode(
        step: Mapping[str, object],
        object_type: ObjectType,
        codec: PayloadCodec[T],
    ) -> T | None:
        value = outputs.get(str(step["step_id"]))
        if value is None:
            return None
        ref, exact = value
        if ref.object_type != object_type or ref.codec_id != codec.codec_id:
            # kit:boundary owner=batch.business class=SHELL_BOUNDARY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_batch_readback_rejects_codec_and_ack_identity_drift
            raise ExactBindingConflict("batch result codec differs from the exact operation")
        decoded: CanonicalJsonObject = json.loads(exact)
        return codec.decode_payload(decoded)

    items: list[dict[str, Any]] = []
    for step in steps:
        if step["operation_kind"] != batch_task.DISPATCH_SINGLE_KIND:
            continue
        item_id = str(step["operation_id"]).removeprefix(batch_task.DISPATCH_SINGLE_OPERATION_ID + ":")
        waiter = wait_steps.get(item_id)
        ack = decode(step, batch_task.DISPATCH_SINGLE_ACK_TYPE, ack_codec)
        result = decode(waiter, batch_business.BUSINESS_WAIT_RESULT_TYPE, result_codec) if waiter else None
        if result is not None and (ack is None or result.task_id != ack.celery_task_id):
            # kit:boundary owner=batch.business class=SHELL_BOUNDARY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_batch_readback_rejects_codec_and_ack_identity_drift
            raise ExactBindingConflict("business result does not bind its dispatch ACK")
        observed = waiter if waiter and (ack or waiter["state"] != "PENDING") else step
        state = str(observed["state"])
        if result is not None:
            status = "succeeded"
        elif state in {"FAILED", "CANCELLED", "SUPERSEDED"}:
            status = {"FAILED": "failed", "CANCELLED": "cancelled", "SUPERSEDED": "superseded"}[state]
        elif state == "RECONCILING":
            status = "unknown"
        elif ack:
            status = "waiting" if waiter else "submitted"
        elif state in {"PENDING", "READY", "AWAITING_APPROVAL"}:
            status = "queued"
        else:
            status = "running"
        items.append({"item_id": item_id, "status": status,
                      "runtime_state": state, "task_id": ack.celery_task_id if ack else None,
                      "dispatch_ack": ack_codec.encode_payload(ack) if ack else None,
                      "business_terminal": bool(waiter) and status in {"succeeded", "failed", "cancelled", "superseded"},
                      "output": result.output if result else None,
                      "error": {"failure_digest": observed["failure_digest"]} if observed.get("failure_digest") else None,
                      "input": {"run_id": run_id}})
    return {**run, "business_program": bool(wait_steps)}, items, events


__all__ = [
    "build_dispatch_submission_inputs",
    "load_dispatch_run",
    "submit_dispatch_run",
]
