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

from app.successor_runtime.capabilities import batch_task as batch_task
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.language.algebra import (
    AlgebraRef,
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
    ProgramSpec,
    atom_node,
    traverse_ordered_node,
)
__all__ = [
    "build_batch_task_plan_program",
    "build_batch_task_plan_traversal_program",
    "build_batch_task_retry_program",
    "build_batch_task_submission_program",
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
