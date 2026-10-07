"""Family-local Program builders for the C4 agent-batch atoms.

The C4.1 batch-plan and C4.2 retry-reducer atoms compile through the shared
Program AST/compiler as single-Atom programs with exact content-addressed
payload ValueRefs.  The C4.1 ordered traversal is additionally compiled as a
shared ``TraverseOrdered(STATIC_SHAPE)`` Program whose metadata binds the exact
``traversal_shape_digest`` and ``traversal_element_count`` for the payload's
ordered task sequence.

The C4.3 submit atom is contract/submission-repository only: durable
submission uses the shared STARTED/TERMINAL idempotency repository, and the
family-specific acceptance status stays in the typed receipt, so no C4-owned
DB enum exists.
"""

from __future__ import annotations

import dataclasses
from typing import Annotated, Any

from functorial_kit import Failure

from app.successor_runtime.capabilities import batch_task as batch_task, batch_business
from app.successor_runtime.capabilities.checksum import (
    CanonicalJsonArray,
    CanonicalJsonValue,
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.language.algebra import (
    AlgebraRef,
    ObjectType,
    OperationSpec,
    ValueRef,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    OperationContractResolver,
)
from app.successor_runtime.language.plan import traversal_shape_digest
from app.successor_runtime.language.program import (
    ProgramNode,
    ProgramSpec,
    atom_node,
    then_node,
    sequence_object_type,
    traverse_ordered_node,
    zip_ordered_node,
)
from app.successor_runtime.language.transforms import MergeRef, TransformRegistry
__all__ = [
    "build_batch_task_plan_program",
    "build_batch_task_plan_traversal_program",
    "build_batch_task_retry_program",
    "build_batch_task_single_dispatch_program",
    "build_batch_task_submission_program",
    "build_ordered_dispatch_merge_registry",
    "build_batch_business_program",
    "compile_batch_task_program",
    "exact_contract_ref",
    "payload_value_ref",
    "traversal_shape_binding",
]


def exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
    *,
    kind: str,
) -> OperationContractRef:
    result = try_exact_contract_ref(catalog, kind=kind)
    if isinstance(result, Failure):
        batch_task._raise_contract_failure(result)
    return result


def try_exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
    *,
    kind: str,
) -> OperationContractRef | Failure:
    ref = catalog.lookup(kind)
    if ref is None:
        return batch_task._failure(
            "catalog_contract_invalid",
            f"contract {kind} missing from catalog {catalog.catalog_id}",
            site="program/exact_contract_ref",
        )
    return ref


def payload_value_ref(
    payload: Any,
    *,
    program_id: str,
    project_key: str,
    object_type: Any,
    codec_id: str,
    value_suffix: str,
) -> ValueRef:
    """Build the exact content-addressed ValueRef for one C4 payload."""

    result = try_payload_value_ref(
        payload,
        program_id=program_id,
        project_key=project_key,
        object_type=object_type,
        codec_id=codec_id,
        value_suffix=value_suffix,
    )
    if isinstance(result, Failure):
        batch_task._raise_contract_failure(result)
    return result


def try_payload_value_ref(
    payload: Any,
    *,
    program_id: str,
    project_key: str,
    object_type: Any,
    codec_id: str,
    value_suffix: str,
) -> ValueRef | Failure:
    failure = _payload_value_ref_failure(payload, project_key=project_key)
    if failure is not None:
        return failure
    plain = dataclasses.asdict(payload)
    exact_text = canonical_json(plain)
    exact_bytes = exact_text.encode("utf-8")
    content_digest_hex = sha256_hex(exact_bytes)
    payload_digest = str(getattr(payload, "payload_digest", "") or "")
    digest_failure = batch_task._hex64_failure(payload_digest, "payload payload_digest")
    if digest_failure is not None:
        return digest_failure
    value_id = f"{program_id}:payload:{value_suffix}"
    provenance_digest = content_digest(
        {
            "schema": "mrw.batch.payload-provenance.v2",
            "program_id": program_id,
            "project_key": project_key,
            "resolved_schema": getattr(payload, "resolved_schema", ""),
            "project_scope_incarnation": getattr(payload, "scope_incarnation", ""),
            "project_scope_digest": getattr(payload, "scope_digest", ""),
            "payload_digest": payload_digest,
            "content_digest": content_digest_hex,
        }
    )
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=object_type,
        codec_id=codec_id,
        content_digest=content_digest_hex,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact_bytes),
        provenance_digest=provenance_digest,
    )


def _payload_value_ref_failure(payload: Any, *, project_key: str) -> Failure | None:
    if getattr(payload, "project_key", None) != project_key:
        return batch_task._failure(
            "scope_contract_invalid",
            "payload project scope drift",
            site="program/payload_value_ref/project_key",
        )
    return None


def _batch_task_program_scope_failure(
    payload: Any,
    *,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> Failure | None:
    if getattr(payload, "project_key", None) != project_key:
        return batch_task._failure(
            "scope_contract_invalid",
            "payload project_key does not match Program project_key",
            site="program/scope/project_key",
        )
    if getattr(payload, "registry_revision", None) != project_registry_revision:
        return batch_task._failure(
            "scope_contract_invalid",
            "payload registry revision does not match Program registry revision",
            site="program/scope/registry_revision",
        )
    if getattr(payload, "scope_digest", None) != project_scope_digest:
        return batch_task._failure(
            "scope_contract_invalid",
            "payload scope digest does not match Program scope digest",
            site="program/scope/scope_digest",
        )
    return None


def _traversal_program_payload_failure(
    payloads: tuple[Any, ...] | list[Any],
) -> Failure | None:
    if not payloads:
        return batch_task._failure(
            "schema_contract_invalid",
            "traversal program requires at least one payload",
            site="program/traversal/payloads",
        )
    return None


def _build_batch_task_program(
    *,
    payload: Any,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    kind: str,
    operation_id: str,
    semantic_identity: str,
    observation_profile: str,
    owner: str,
    input_type: Any,
    output_type: Any,
    object_type: Any,
    codec_id: str,
    value_suffix: str,
) -> ProgramSpec:
    failure = _batch_task_program_scope_failure(
        payload,
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
    )
    if failure is not None:
        batch_task._raise_contract_failure(failure)
    ref = exact_contract_ref(catalog, kind=kind)
    value_ref = payload_value_ref(
        payload,
        program_id=program_id,
        project_key=project_key,
        object_type=object_type,
        codec_id=codec_id,
        value_suffix=value_suffix,
    )
    operation = OperationSpec(
        operation_id=operation_id,
        contract_ref=ref,
        input_refs=(value_ref,),
        payload_ref=value_ref,
        allowed_overrides=freeze_json_object({}),
    )
    root = atom_node(
        operation,
        input_type=input_type,
        output_type=output_type,
    )
    metadata = freeze_json_object(
        {
            "schema": "mrw.batch.program-metadata.v2",
            "operation_kind": kind,
            "project_registry_revision": project_registry_revision,
            "resolved_schema": getattr(payload, "resolved_schema", ""),
            "project_scope_incarnation": getattr(payload, "scope_incarnation", ""),
            "project_scope_digest": project_scope_digest,
            "payload_value_id": value_ref.value_id,
            "payload_storage_ref": value_ref.storage_ref,
            "payload_content_digest": value_ref.content_digest,
            "payload_provenance_digest": value_ref.provenance_digest,
            "canonical_owner": owner,
        }
    )
    return ProgramSpec(
        program_id=program_id,
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity=semantic_identity,
        input_type=root.input_type,
        output_type=root.output_type,
        root=root,
        algebra_refs=(
            AlgebraRef(
                algebra_id="mrw.successor.language.algebra",
                algebra_version="1",
            ),
        ),
        transform_refs=(),
        observation_profile=observation_profile,
        metadata=metadata,
        program_digest="",
    ).with_digest()


def build_batch_task_plan_program(
    *,
    payload: batch_task.BatchPlanPayload,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> Annotated[  # NonAuthoritative
    ProgramSpec,
    "kit:prepared-command effect_boundary=successor_program_interpreter "
    "witness=test:test_w05_agent_batch_authority_metadata",
]:
    """Compilable single-Atom Program for the C4.1 ordered batch plan."""

    return _build_batch_task_program(
        payload=payload,
        catalog=catalog,
        program_id=program_id,
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        kind=batch_task.BATCH_PLAN_KIND,
        operation_id=batch_task.BATCH_PLAN_OPERATION_ID,
        semantic_identity=batch_task.BATCH_PLAN_SEMANTIC_IDENTITY,
        observation_profile=batch_task.BATCH_PLAN_OBSERVATION_PROFILE,
        owner=batch_task.BATCH_TASK_OWNER,
        input_type=batch_task.BATCH_PLAN_PAYLOAD_TYPE,
        output_type=batch_task.BATCH_PLAN_RESULT_TYPE,
        object_type=batch_task.BATCH_PLAN_PAYLOAD_TYPE,
        codec_id=batch_task.BATCH_PLAN_PAYLOAD_CODEC_ID,
        value_suffix="task-plan",
    )


def build_batch_task_retry_program(
    *,
    payload: batch_task.RetryReducerInput,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> Annotated[  # NonAuthoritative
    ProgramSpec,
    "kit:prepared-command effect_boundary=successor_program_interpreter "
    "witness=test:test_w05_agent_batch_authority_metadata",
]:
    """Compilable single-Atom Program for the C4.2 retry reducer."""

    return _build_batch_task_program(
        payload=payload,
        catalog=catalog,
        program_id=program_id,
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        kind=batch_task.RETRY_REDUCE_KIND,
        operation_id=batch_task.RETRY_REDUCE_OPERATION_ID,
        semantic_identity=batch_task.RETRY_REDUCE_SEMANTIC_IDENTITY,
        observation_profile=batch_task.RETRY_REDUCE_OBSERVATION_PROFILE,
        owner=batch_task.BATCH_TASK_OWNER,
        input_type=batch_task.RETRY_REDUCER_PAYLOAD_TYPE,
        output_type=batch_task.RETRY_TRANSITION_TYPE,
        object_type=batch_task.RETRY_REDUCER_PAYLOAD_TYPE,
        codec_id=batch_task.RETRY_REDUCER_PAYLOAD_CODEC_ID,
        value_suffix="retry-action",
    )


def compile_batch_task_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_contracts: OperationContractResolver,
) -> Any:
    """Compile a C4 Program through the shared compiler."""

    return compile_program(
        program,
        catalog,
        operation_contracts=operation_contracts,
    )


def traversal_shape_binding(
    payloads: tuple[batch_task.BatchPlanPayload, ...] | list[batch_task.BatchPlanPayload],
) -> dict[str, object]:
    """Exact STATIC_SHAPE binding via the shared ``language.plan`` digest.

    The shape is computed over the actual TraverseOrdered input sequence,
    which is the ordered ``BatchPlanPayload`` sequence, using the shared
    ``traversal_shape_digest``/``traversal_element_digests`` identities.
    """

    return {
        "traversal_shape_digest": traversal_shape_digest(
            tuple(dataclasses.asdict(payload) for payload in payloads)
        ),
        "traversal_element_count": len(payloads),
    }


def build_batch_task_plan_traversal_program(
    *,
    payloads: tuple[batch_task.BatchPlanPayload, ...] | list[batch_task.BatchPlanPayload],
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> Annotated[  # NonAuthoritative
    ProgramSpec,
    "kit:prepared-command effect_boundary=successor_program_interpreter "
    "witness=test:test_w05_agent_batch_authority_metadata",
]:
    """Build the C4.1 ordered traversal Program over batch-plan payloads.

    The root is ``TraverseOrdered(STATIC_SHAPE)`` whose input is the ordered
    ``BatchPlanPayload`` sequence.  Exact shape digest and element count come
    from the shared ``language.plan.traversal_shape_digest`` and are bound in
    Program metadata; the shared compiler realizes the traversal as a pure
    ordered materialization step.
    """

    failure = _traversal_program_payload_failure(payloads)
    if failure is not None:
        batch_task._raise_contract_failure(failure)
    payload = payloads[0]
    atom = build_batch_task_plan_program(
        payload=payload,
        catalog=catalog,
        program_id=program_id,
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
    )
    binding = traversal_shape_binding(payloads)
    metadata_values = {key: value for key, value in dict(atom.metadata).items()}
    metadata_values.update(binding)
    root = traverse_ordered_node(
        element_program=atom.root,
        traversal_policy="STATIC_SHAPE",
    )
    return ProgramSpec(
        program_id=program_id + ":traverse-static",
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity="batch.task.build-plan-traverse-static",
        input_type=root.input_type,
        output_type=root.output_type,
        root=root,
        algebra_refs=atom.algebra_refs,
        transform_refs=(),
        observation_profile=batch_task.BATCH_PLAN_OBSERVATION_PROFILE,
        metadata=freeze_json_object(metadata_values),
        program_digest="",
    ).with_digest()


def build_batch_task_submission_program(
    *,
    payload: batch_task.AgentBatchSubmission,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> Annotated[  # NonAuthoritative
    ProgramSpec,
    "kit:prepared-command effect_boundary=successor_program_interpreter "
    "witness=test:test_w05_agent_batch_authority_metadata",
]:
    """Compilable single-Atom Program for the C4.3 submission atom."""

    return _build_batch_task_program(
        payload=payload,
        catalog=catalog,
        program_id=program_id,
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        kind=batch_task.SUBMISSION_KIND,
        operation_id=batch_task.SUBMISSION_OPERATION_ID,
        semantic_identity=batch_task.SUBMISSION_SEMANTIC_IDENTITY,
        observation_profile=batch_task.SUBMISSION_OBSERVATION_PROFILE,
        owner=batch_task.SUBMISSION_OWNER,
        input_type=batch_task.SUBMISSION_TYPE,
        output_type=batch_task.SUBMISSION_RECEIPT_TYPE,
        object_type=batch_task.SUBMISSION_TYPE,
        codec_id=batch_task.SUBMISSION_PAYLOAD_CODEC_ID,
        value_suffix="task-submission",
    )


def build_batch_task_single_dispatch_program(
    *,
    payload: batch_task.BatchTaskSingleDispatchPayload,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> Annotated[  # NonAuthoritative
    ProgramSpec,
    "kit:prepared-command effect_boundary=successor_program_interpreter "
    "witness=test:test_w05_agent_batch_authority_metadata",
]:
    """Compilable single-Atom Program for the independent single-item dispatch."""

    return _build_batch_task_program(
        payload=payload,
        catalog=catalog,
        program_id=program_id,
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        kind=batch_task.DISPATCH_SINGLE_KIND,
        operation_id=batch_task.DISPATCH_SINGLE_OPERATION_ID,
        semantic_identity=batch_task.DISPATCH_SINGLE_SEMANTIC_IDENTITY,
        observation_profile=batch_task.DISPATCH_SINGLE_OBSERVATION_PROFILE,
        owner=batch_task.DISPATCH_SINGLE_OWNER,
        input_type=batch_task.DISPATCH_SINGLE_PAYLOAD_TYPE,
        output_type=batch_task.DISPATCH_SINGLE_ACK_TYPE,
        object_type=batch_task.DISPATCH_SINGLE_PAYLOAD_TYPE,
        codec_id=batch_task.DISPATCH_SINGLE_PAYLOAD_CODEC_ID,
        value_suffix="single-dispatch",
    )


def _collect_pair_dispatch_acks(
    left: CanonicalJsonValue,
    right: CanonicalJsonValue,
) -> CanonicalJsonArray:
    """Ordered first pair merge: two ACK payloads become one sequence."""

    return [left, right]


def _collect_append_dispatch_ack(
    left: CanonicalJsonArray,
    right: CanonicalJsonValue,
) -> CanonicalJsonArray:
    """Ordered append merge: one ACK is appended after the prior sequence."""

    return [*left, right]


def _ordered_dispatch_sequence_type() -> ObjectType:
    ack = batch_task.DISPATCH_SINGLE_ACK_TYPE
    return ObjectType(
        type_id=f"sequence:{ack.type_id}",
        schema_version="1",
        codec_id="mrw.successor.sequence_codec.v1",
        canonical_codec_version="1",
    )


def _register_ordered_dispatch_merges(
    registry: TransformRegistry,
    *,
    element_type: ObjectType = batch_task.DISPATCH_SINGLE_ACK_TYPE,
    name: str = "mrw.batch.ordered_dispatch",
    sequence_type: ObjectType | None = None,
) -> tuple[MergeRef, MergeRef]:
    ack = element_type
    seq = sequence_type or _ordered_dispatch_sequence_type()
    pair_ref = registry.register_merge(
        name=f"{name}.collect_pair",
        version="1.0.0",
        left_type=ack,
        right_type=ack,
        output_type=seq,
        func=_collect_pair_dispatch_acks,
    )
    append_ref = registry.register_merge(
        name=f"{name}.collect_append",
        version="1.0.0",
        left_type=seq,
        right_type=ack,
        output_type=seq,
        func=_collect_append_dispatch_ack,
    )
    return pair_ref, append_ref


def build_ordered_dispatch_merge_registry() -> Annotated[TransformRegistry, 'kit:non-authoritative derived_as=program fact_source=ordered_batch_dispatch_and_business_contracts witness=test:test_post_waits_for_real_business_outputs_in_input_order']:
    """Rebuild the shared ordered-dispatch merge registry for worker composition."""

    registry = TransformRegistry(
        registry_id="mrw.batch.ordered-dispatch.merge.v1",
        registry_version="1",
    )
    _register_ordered_dispatch_merges(registry)
    _register_ordered_dispatch_merges(
        registry, element_type=batch_business.BUSINESS_WAIT_RESULT_TYPE,
        name="mrw.batch.ordered_business.v2",
        sequence_type=sequence_object_type(batch_business.BUSINESS_WAIT_RESULT_TYPE, version="2"),
    )
    return registry


def build_batch_business_program(
    *, payloads: tuple[batch_task.BatchTaskSingleDispatchPayload, ...],
    catalog: OperationContractCatalogSnapshot, program_id: str,
    project_key: str, project_registry_revision: int, project_scope_digest: str,
) -> Annotated[ProgramSpec, 'kit:non-authoritative derived_as=program fact_source=ordered_batch_dispatch_and_business_contracts witness=test:test_post_waits_for_real_business_outputs_in_input_order']:
    """Ordered item dispatch followed by the actual business terminal readback."""
    if not payloads:
        batch_task._raise_contract_failure(batch_task._failure(
            "schema_contract_invalid", "business program requires at least one payload",
            site="program/business/payloads",
        ))
    wait = exact_contract_ref(catalog, kind=batch_business.BUSINESS_WAIT_KIND)
    roots: list[ProgramNode] = []
    for index, payload in enumerate(payloads):
        item = build_batch_task_single_dispatch_program(
            payload=payload, catalog=catalog, program_id=f"{program_id}:{index}",
            project_key=project_key, project_registry_revision=project_registry_revision,
            project_scope_digest=project_scope_digest,
        )
        from app.successor_runtime.language.program import program_atoms
        dispatch = program_atoms(item.root)[0]
        dispatch = dataclasses.replace(dispatch, operation=dataclasses.replace(
            dispatch.operation, operation_id=f"{batch_task.DISPATCH_SINGLE_OPERATION_ID}:{payload.dispatch_id}",
        ))
        # The immutable request qualifies this occurrence; Then supplies the
        # actual ACK as semantic input through the existing typed data edge.
        waiter = atom_node(OperationSpec(
            operation_id=f"{batch_business.BUSINESS_WAIT_KIND}:{payload.dispatch_id}",
            contract_ref=wait, input_refs=(dispatch.operation.payload_ref,),
            payload_ref=dispatch.operation.payload_ref, allowed_overrides=freeze_json_object({}),
        ), input_type=batch_task.DISPATCH_SINGLE_ACK_TYPE,
            output_type=batch_business.BUSINESS_WAIT_RESULT_TYPE)
        roots.append(then_node(dispatch, waiter))
    seq = sequence_object_type(batch_business.BUSINESS_WAIT_RESULT_TYPE, version="2")
    registry = TransformRegistry()
    pair, append = _register_ordered_dispatch_merges(
        registry, element_type=batch_business.BUSINESS_WAIT_RESULT_TYPE,
        name="mrw.batch.ordered_business.v2", sequence_type=seq,
    )
    root = roots[0]
    for index, next_item in enumerate(roots[1:], start=1):
        root = zip_ordered_node(left=root, right=next_item,
                                merge_ref=pair if index == 1 else append, output_type=seq)
    return dataclasses.replace(
        item, program_id=program_id, semantic_identity="batch.task.business-ordered.v2",
        root=root, input_type=root.input_type, output_type=root.output_type,
        metadata=freeze_json_object({"schema": "mrw.batch.business-program.v2",
                                     "ordered_element_count": len(payloads)}),
        program_digest="",
    ).with_digest()
