"""Single-Atom Program builders for the C3 collect family.

The builder consumes the frozen operation catalog and shared Program AST
without modifying any shared root.  Payloads are exact-bound through
content/provenance digests that close over the project scope, request ref and
operation kind.

C3.1 declares an ordered batch traversal over finite elements, but the shared
compiler still rejects ``TraverseOrdered`` as draft-only.  This module never
fakes that compilation: ``compile_declared_traversal_program`` returns the
precise compiler blocker, and the successor family interpreter performs the
ordered traversal in-process only for bounded local fixtures and parity.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from app.successor_runtime.capabilities import collect_c3 as c3
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    require_hex64,
    sha256_hex,
)
from app.successor_runtime.language.algebra import (
    AlgebraRef,
    OperationSpec,
    ValueRef,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
)
from app.successor_runtime.language.compile import (
    TRAVERSAL_MATERIALIZER_TRANSFORM,
    TRAVERSAL_MATERIALIZER_VERSION,
    CompileFailure,
    compile_program,
)
from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    OperationContractResolver,
)
from app.successor_runtime.language.program import (
    ProgramSpec,
    atom_node,
    identity_node,
    map_output_node,
    then_node,
    traverse_ordered_node,
)
from app.successor_runtime.language.transforms import (
    TransformRef,
    TransformRegistry,
)

__all__ = [
    "COLLECT_FOLD_TRANSFORM_NAME",
    "COLLECT_FOLD_TRANSFORM_VERSION",
    "COLLECT_SEQUENCE_TO_FOLD_PAYLOAD_TRANSFORM_NAME",
    "FAMILY_PAYLOAD_CODEC_ID",
    "TRAVERSAL_COMPILED_CODE",
    "TraversalCompileStatus",
    "build_collect_c3_1_program",
    "build_collect_c3_2_program",
    "build_collect_c3_2_pure_fold_program",
    "build_collect_c3_composed_program",
    "build_collect_c3_program",
    "build_collect_c3_transform_registry",
    "build_declared_traversal_program",
    "build_family_payload_value_ref",
    "compile_collect_c3_program",
    "compile_declared_traversal_program",
    "exact_contract_ref",
    "family_payload_incarnation",
    "family_payload_sequence_type",
    "fold_transform_ref",
    "payload_value_ref",
    "sequence_to_fold_payload_transform_ref",
]

TRAVERSAL_COMPILED_CODE = "COMPILED_TRAVERSE_ORDERED"
COLLECT_FOLD_TRANSFORM_NAME = "collect.fold_ordered_results"
COLLECT_FOLD_TRANSFORM_VERSION = "1.0.0"
COLLECT_SEQUENCE_TO_FOLD_PAYLOAD_TRANSFORM_NAME = "collect.sequence_to_fold_payload"
FAMILY_PAYLOAD_CODEC_ID = "mrw.successor.collect.c3.family-payload.codec.v1"
FAMILY_PAYLOAD_IDENTITY_SCHEMA = "mrw.successor.collect.c3.family-payload-identity.v1"


def _element_atom_root() -> Any:
    bundle = c3.build_collect_c3_bundle()
    ref = bundle.operation_c3_1.ref
    dummy = ValueRef(
        value_id="placeholder:c3-element",
        project_key="demo_proj",
        object_type=c3.COLLECT_C3_1_PAYLOAD_TYPE,
        codec_id=c3.COLLECT_C3_1_PAYLOAD_CODEC_ID,
        content_digest="0" * 64,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref="project-value:placeholder:c3-element",
        byte_size=0,
        provenance_digest="0" * 64,
    )
    operation = OperationSpec(
        operation_id=c3.COLLECT_C3_1_OPERATION_ID,
        contract_ref=ref,
        input_refs=(dummy,),
        payload_ref=dummy,
        allowed_overrides=freeze_json_object({}),
    )
    return atom_node(
        operation,
        input_type=c3.COLLECT_C3_1_PAYLOAD_TYPE,
        output_type=c3.COLLECT_C3_1_RESULT_TYPE,
    )


def family_payload_sequence_type() -> Any:
    return traverse_ordered_node(
        _element_atom_root(),
        traversal_policy="MATERIALIZED_SHAPE",
    ).input_type


def family_payload_incarnation(
    *,
    program_id: str,
    project_key: str,
    value_ref: ValueRef,
) -> str:
    """Derive the exact immutable payload incarnation from Program closure."""

    return "payload-inc:" + content_digest(
        {
            "schema": FAMILY_PAYLOAD_IDENTITY_SCHEMA,
            "program_id": program_id,
            "project_key": project_key,
            "value_id": value_ref.value_id,
            "content_digest": value_ref.content_digest,
            "provenance_digest": value_ref.provenance_digest,
            "byte_size": value_ref.byte_size,
        }
    )


def build_family_payload_value_ref(
    element_payloads: tuple[c3.CollectBatchElementPayload, ...],
    *,
    program_id: str,
    project_key: str,
) -> ValueRef:
    """Exact content-addressed ValueRef for the ordered element payload sequence."""

    plain = [payload.to_plain() for payload in element_payloads]
    exact_text = canonical_json(plain)
    exact_bytes = exact_text.encode("utf-8")
    content_digest_hex = sha256_hex(exact_bytes)
    value_id = f"{program_id}:payload:family"
    provenance_digest = content_digest(
        {
            "schema": "mrw.successor.collect.c3.family-payload-provenance.v1",
            "program_id": program_id,
            "project_key": project_key,
            "element_count": len(element_payloads),
            "content_digest": content_digest_hex,
        }
    )
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=family_payload_sequence_type(),
        codec_id=FAMILY_PAYLOAD_CODEC_ID,
        content_digest=content_digest_hex,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact_bytes),
        provenance_digest=provenance_digest,
    )


def _sequence_to_fold_payload_plain(sequence_plain: dict[str, Any]) -> dict[str, Any]:
    """Pure typed intermediate: ordered outcome sequence -> fold payload."""

    parent_request_ref = sequence_plain.get("parent_request_ref")
    if not isinstance(parent_request_ref, dict):
        raise TypeError("sequence_to_fold_payload requires a parent_request_ref")
    return {
        "parent_request_ref": parent_request_ref,
        "ordered_outcomes": sequence_plain,
        "aggregation_policy_ref": c3.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
        "observation_profile_ref": c3.COLLECT_FOLD_OBSERVATION_PROFILE,
    }


def _fold_ordered_payload_plain(payload_plain: dict[str, Any]) -> dict[str, Any]:
    """Pure named fold transform over an already observed fold payload."""

    outcomes = payload_plain.get("ordered_outcomes")
    if not isinstance(outcomes, dict):
        raise TypeError("fold transform requires ordered_outcomes")
    payload = c3.collect_fold_payload_from_dicts(
        parent_request_ref=outcomes["parent_request_ref"],
        ordered_outcomes=outcomes,
        aggregation_policy_ref=payload_plain.get(
            "aggregation_policy_ref", c3.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF
        ),
        observation_profile_ref=payload_plain.get(
            "observation_profile_ref", c3.COLLECT_FOLD_OBSERVATION_PROFILE
        ),
    )
    aggregate = c3.fold_ordered_results(
        payload.ordered_outcomes,
        aggregation_policy_ref=payload.aggregation_policy_ref,
        observation_profile_ref=payload.observation_profile_ref,
    )
    return aggregate.to_plain()


def _register_fold_transform(registry: TransformRegistry) -> TransformRef:
    return registry.register_transform(
        name=COLLECT_FOLD_TRANSFORM_NAME,
        version=COLLECT_FOLD_TRANSFORM_VERSION,
        input_type=c3.COLLECT_C3_2_PAYLOAD_TYPE,
        output_type=c3.COLLECT_FOLD_RESULT_TYPE,
        func=_fold_ordered_payload_plain,
        loss_profile_id="mrw.successor.collect.c3-2.fold.loss-profile.v1",
    )


def _register_sequence_to_fold_payload(
    registry: TransformRegistry,
    *,
    sequence_type: Any,
) -> TransformRef:
    return registry.register_transform(
        name=COLLECT_SEQUENCE_TO_FOLD_PAYLOAD_TRANSFORM_NAME,
        version="1.0.0",
        input_type=sequence_type,
        output_type=c3.COLLECT_C3_2_PAYLOAD_TYPE,
        func=_sequence_to_fold_payload_plain,
    )


def build_collect_c3_transform_registry() -> TransformRegistry:
    """Family-local registered transforms; no shared registry edits."""

    registry = TransformRegistry(
        registry_id="mrw.successor.collect.c3.transforms.v1",
        registry_version="1",
    )
    _register_fold_transform(registry)
    sequence_type = traverse_ordered_node(
        _element_atom_root(),
        traversal_policy="MATERIALIZED_SHAPE",
    ).output_type
    _register_sequence_to_fold_payload(registry, sequence_type=sequence_type)
    return registry


def _family_refs(
    registry: TransformRegistry,
) -> tuple[TransformRef, TransformRef]:
    refs = registry.transform_refs()
    fold = next(ref for ref in refs if ref.name == COLLECT_FOLD_TRANSFORM_NAME)
    sequence = next(
        ref
        for ref in refs
        if ref.name == COLLECT_SEQUENCE_TO_FOLD_PAYLOAD_TRANSFORM_NAME
    )
    return fold, sequence


def fold_transform_ref() -> TransformRef:
    return _register_fold_transform(TransformRegistry())


def sequence_to_fold_payload_transform_ref() -> TransformRef:
    return _register_sequence_to_fold_payload(
        TransformRegistry(),
        sequence_type=traverse_ordered_node(
            _element_atom_root(),
            traversal_policy="MATERIALIZED_SHAPE",
        ).output_type,
    )


def exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
    *,
    kind: str,
) -> OperationContractRef:
    ref = catalog.lookup(kind)
    if ref is None:
        raise ValueError(f"contract {kind} missing from catalog {catalog.catalog_id}")
    return ref


def payload_value_ref(
    payload: Any,
    *,
    program_id: str,
    project_key: str,
    payload_type: Any,
    codec_id: str,
    value_suffix: str,
) -> ValueRef:
    """Build the exact content-addressed ValueRef for one C3 payload."""

    if payload.parent_request_ref.project_key != project_key:
        raise ValueError("payload project scope drift")
    require_hex64(payload.payload_digest, f"{type(payload).__name__}.payload_digest")
    plain = dataclasses.asdict(payload)
    exact_text = canonical_json(plain)
    exact_bytes = exact_text.encode("utf-8")
    content_digest_hex = sha256_hex(exact_bytes)
    value_id = f"{program_id}:payload:{value_suffix}"
    provenance_digest = content_digest(
        {
            "schema": f"mrw.successor.collect.c3.payload-provenance.{value_suffix}.v1",
            "program_id": program_id,
            "project_key": project_key,
            "request_id": payload.parent_request_ref.request_id,
            "request_channel": payload.parent_request_ref.channel,
            "request_digest": payload.parent_request_ref.request_digest,
            "operation_kind": payload.operation_kind,
            "content_digest": content_digest_hex,
        }
    )
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=payload_type,
        codec_id=codec_id,
        content_digest=content_digest_hex,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact_bytes),
        provenance_digest=provenance_digest,
    )


def _metadata(
    *,
    payload: Any,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    value_ref: ValueRef,
    extra: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "mrw.successor.collect.c3.program-metadata.v1",
        "operation_kind": payload.operation_kind,
        "project_registry_revision": project_registry_revision,
        "project_scope_digest": project_scope_digest,
        "request_id": payload.parent_request_ref.request_id,
        "request_channel": payload.parent_request_ref.channel,
        "request_digest": payload.parent_request_ref.request_digest,
        "payload_value_id": value_ref.value_id,
        "payload_storage_ref": value_ref.storage_ref,
        "payload_content_digest": value_ref.content_digest,
        "payload_provenance_digest": value_ref.provenance_digest,
        **extra,
    }


def build_collect_c3_program(
    *,
    payload: Any,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    operation_id: str,
    semantic_identity: str,
    observation_profile: str,
    payload_type: Any,
    result_type: Any,
    codec_id: str,
    value_suffix: str,
    extra_metadata: dict[str, Any] | None = None,
    contract_version: str = "mrw.functorial-successor.program-spec.v1",
) -> ProgramSpec:
    """Build the exact-bound single-Atom Program for one C3 payload."""

    if payload.parent_request_ref.project_key != project_key:
        raise ValueError("payload project_key does not match Program project_key")
    ref = exact_contract_ref(catalog, kind=payload.operation_kind)
    value_ref = payload_value_ref(
        payload,
        program_id=program_id,
        project_key=project_key,
        payload_type=payload_type,
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
        input_type=payload_type,
        output_type=result_type,
    )
    metadata = freeze_json_object(
        _metadata(
            payload=payload,
            program_id=program_id,
            project_key=project_key,
            project_registry_revision=project_registry_revision,
            project_scope_digest=project_scope_digest,
            value_ref=value_ref,
            extra={
                "catalog_id": catalog.catalog_id,
                "catalog_version": catalog.catalog_version,
                "catalog_digest": catalog.catalog_digest,
                "canonical_owner": (
                    c3.COLLECT_C3_1_OWNER
                    if payload.operation_kind == c3.COLLECT_C3_1_KIND
                    else c3.COLLECT_C3_2_OWNER
                ),
                **(extra_metadata or {}),
            },
        )
    )
    return ProgramSpec(
        program_id=program_id,
        contract_version=contract_version,
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


def build_collect_c3_1_program(
    *,
    payload: c3.CollectBatchElementPayload,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> ProgramSpec:
    return build_collect_c3_program(
        payload=payload,
        catalog=catalog,
        program_id=program_id,
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        operation_id=c3.COLLECT_C3_1_OPERATION_ID,
        semantic_identity=c3.COLLECT_C3_1_SEMANTIC_IDENTITY,
        observation_profile=c3.COLLECT_TRAVERSAL_OBSERVATION_PROFILE,
        payload_type=c3.COLLECT_C3_1_PAYLOAD_TYPE,
        result_type=c3.COLLECT_C3_1_RESULT_TYPE,
        codec_id=c3.COLLECT_C3_1_PAYLOAD_CODEC_ID,
        value_suffix="c3-1",
        extra_metadata={
            "traversal_realization": ("SUCCESSOR_ORDERED_TRAVERSAL_PENDING_COMPILER"),
            "compiled_traversal": False,
            "element_id": payload.element.element_id,
            "input_index": payload.element.input_index,
            "resource_policy_digest": payload.resource_policy.policy_digest,
            "authority_scope_ref": payload.authority_scope_ref,
        },
    )


def build_collect_c3_2_program(
    *,
    payload: c3.CollectFoldPayload,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> ProgramSpec:
    return build_collect_c3_program(
        payload=payload,
        catalog=catalog,
        program_id=program_id,
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        operation_id=c3.COLLECT_C3_2_OPERATION_ID,
        semantic_identity=c3.COLLECT_C3_2_SEMANTIC_IDENTITY,
        observation_profile=c3.COLLECT_FOLD_OBSERVATION_PROFILE,
        payload_type=c3.COLLECT_C3_2_PAYLOAD_TYPE,
        result_type=c3.COLLECT_FOLD_RESULT_TYPE,
        codec_id=c3.COLLECT_C3_2_PAYLOAD_CODEC_ID,
        value_suffix="c3-2",
        extra_metadata={
            "aggregation_policy_ref": payload.aggregation_policy_ref,
            "fold_observation_profile": payload.observation_profile_ref,
            "outcome_sequence_digest": payload.ordered_outcomes.sequence_digest,
        },
    )


def build_collect_c3_2_pure_fold_program(
    *,
    payload: c3.CollectFoldPayload,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> ProgramSpec:
    """Named pure fold Program realized as a registered TRANSFORM (no EFFECT)."""

    if payload.parent_request_ref.project_key != project_key:
        raise ValueError("payload project_key does not match Program project_key")
    registry = build_collect_c3_transform_registry()
    fold_ref, _sequence_ref = _family_refs(registry)
    root = map_output_node(
        identity_node(c3.COLLECT_C3_2_PAYLOAD_TYPE),
        fold_ref,
        target_type=c3.COLLECT_FOLD_RESULT_TYPE,
    )
    metadata = freeze_json_object(
        {
            "schema": "mrw.successor.collect.c3-2.pure-fold-program.v1",
            "operation_kind": c3.COLLECT_C3_2_KIND,
            "fold_realization": "PURE_TRANSFORM",
            "fold_transform": fold_ref.label(),
            "aggregation_policy_ref": payload.aggregation_policy_ref,
            "observation_profile_ref": payload.observation_profile_ref,
            "request_id": payload.parent_request_ref.request_id,
            "request_digest": payload.parent_request_ref.request_digest,
            "catalog_id": catalog.catalog_id,
            "catalog_version": catalog.catalog_version,
            "catalog_digest": catalog.catalog_digest,
            "project_registry_revision": project_registry_revision,
            "project_scope_digest": project_scope_digest,
            "canonical_owner": c3.COLLECT_C3_2_OWNER,
        }
    )
    return ProgramSpec(
        program_id=program_id,
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity=c3.COLLECT_C3_2_SEMANTIC_IDENTITY,
        input_type=root.input_type,
        output_type=root.output_type,
        root=root,
        algebra_refs=(
            AlgebraRef(
                algebra_id="mrw.successor.language.algebra",
                algebra_version="1",
            ),
        ),
        transform_refs=(fold_ref,),
        observation_profile=c3.COLLECT_FOLD_OBSERVATION_PROFILE,
        metadata=metadata,
        program_digest="",
    ).with_digest()


def build_collect_c3_composed_program(
    *,
    element_payloads: tuple[c3.CollectBatchElementPayload, ...],
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> ProgramSpec:
    """Compose TraverseOrdered -> typed fold payload -> FoldAtom.

    The composed Program binds the actual TraverseOrdered materialization
    epoch and the fold atom's exact contract in one Program/ExecutionPlan.
    """

    if not element_payloads:
        raise ValueError("composed C3 program requires at least one element payload")
    for payload in element_payloads:
        if payload.parent_request_ref.project_key != project_key:
            raise ValueError("payload project_key does not match Program project_key")

    element_program = build_collect_c3_1_program(
        payload=element_payloads[0],
        catalog=catalog,
        program_id=program_id + ":element",
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
    )
    traverse = traverse_ordered_node(
        element_program.root,
        traversal_policy="MATERIALIZED_SHAPE",
    )
    registry = build_collect_c3_transform_registry()
    fold_ref, sequence_ref = _family_refs(registry)
    fold_payload_map = map_output_node(
        traverse,
        sequence_ref,
        target_type=c3.COLLECT_C3_2_PAYLOAD_TYPE,
    )

    bundle = c3.build_collect_c3_bundle()
    fold_contract = bundle.operation_c3_2.ref
    dummy_fold_value = ValueRef(
        value_id="placeholder:c3-fold",
        project_key=project_key,
        object_type=c3.COLLECT_C3_2_PAYLOAD_TYPE,
        codec_id=c3.COLLECT_C3_2_PAYLOAD_CODEC_ID,
        content_digest="0" * 64,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref="project-value:placeholder:c3-fold",
        byte_size=0,
        provenance_digest="0" * 64,
    )
    fold_operation = OperationSpec(
        operation_id=c3.COLLECT_C3_2_OPERATION_ID,
        contract_ref=fold_contract,
        input_refs=(dummy_fold_value,),
        payload_ref=dummy_fold_value,
        allowed_overrides=freeze_json_object({}),
    )
    fold_atom = atom_node(
        fold_operation,
        input_type=c3.COLLECT_C3_2_PAYLOAD_TYPE,
        output_type=c3.COLLECT_FOLD_RESULT_TYPE,
    )
    root = then_node(fold_payload_map, fold_atom)
    family_value_ref = build_family_payload_value_ref(
        element_payloads,
        program_id=program_id,
        project_key=project_key,
    )
    metadata = freeze_json_object(
        {
            "schema": "mrw.successor.collect.c3.composed-program.v1",
            "operation_kind": c3.COLLECT_C3_1_KIND,
            "fold_atom_kind": c3.COLLECT_C3_2_KIND,
            "compiled_traversal": True,
            "traversal_policy": "MATERIALIZED_SHAPE",
            "composition": (
                "Then(TraverseOrdered, MapOutput(sequence_to_fold_payload), FoldAtom)"
            ),
            "sequence_transform": sequence_ref.label(),
            "fold_transform": fold_ref.label(),
            "element_payload_count": len(element_payloads),
            "payload_value_id": family_value_ref.value_id,
            "payload_storage_ref": family_value_ref.storage_ref,
            "payload_content_digest": family_value_ref.content_digest,
            "payload_provenance_digest": family_value_ref.provenance_digest,
            "payload_object_type": family_value_ref.object_type.type_id,
            "payload_codec_id": family_value_ref.codec_id,
            "payload_byte_size": family_value_ref.byte_size,
            "payload_element_count": len(element_payloads),
            "payload_element_digests": tuple(
                payload.payload_digest for payload in element_payloads
            ),
            "payload_incarnation": family_payload_incarnation(
                program_id=program_id,
                project_key=project_key,
                value_ref=family_value_ref,
            ),
            "request_id": element_payloads[0].parent_request_ref.request_id,
            "request_digest": element_payloads[0].parent_request_ref.request_digest,
            "catalog_id": catalog.catalog_id,
            "catalog_version": catalog.catalog_version,
            "catalog_digest": catalog.catalog_digest,
            "project_registry_revision": project_registry_revision,
            "project_scope_digest": project_scope_digest,
            "canonical_owner": c3.COLLECT_C3_1_OWNER,
        }
    )
    return ProgramSpec(
        program_id=program_id,
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity=c3.COLLECT_C3_1_SEMANTIC_IDENTITY,
        input_type=root.input_type,
        output_type=root.output_type,
        root=root,
        algebra_refs=(
            AlgebraRef(
                algebra_id="mrw.successor.language.algebra",
                algebra_version="1",
            ),
        ),
        transform_refs=(sequence_ref, fold_ref),
        observation_profile=c3.COLLECT_TRAVERSAL_OBSERVATION_PROFILE,
        metadata=metadata,
        program_digest="",
    ).with_digest()


def compile_collect_c3_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_contracts: OperationContractResolver,
    transform_registry: TransformRegistry | None = None,
) -> Any:
    """Compile a C3 single-Atom Program through the shared compiler."""

    return compile_program(
        program,
        catalog,
        operation_contracts=operation_contracts,
        transform_registry=transform_registry,
    )


@dataclasses.dataclass(frozen=True, slots=True)
class TraversalCompileStatus:
    compiled: bool
    code: str
    message: str
    program_digest: str
    plan_digest: str | None = None

    def to_plain(self) -> dict[str, Any]:
        return {
            "compiled": self.compiled,
            "code": self.code,
            "message": self.message,
            "program_digest": self.program_digest,
            "plan_digest": self.plan_digest,
        }


def build_declared_traversal_program(
    *,
    element_payload: c3.CollectBatchElementPayload,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    traversal_policy: str = "MATERIALIZED_SHAPE",
    static_shape_digest: str | None = None,
    static_element_count: int | None = None,
) -> ProgramSpec:
    """Declared TraverseOrdered program with exact occurrence binding metadata."""

    if traversal_policy not in {"STATIC_SHAPE", "MATERIALIZED_SHAPE"}:
        raise ValueError(f"unsupported traversal policy {traversal_policy!r}")
    if traversal_policy == "STATIC_SHAPE":
        if not isinstance(static_shape_digest, str) or len(static_shape_digest) != 64:
            raise ValueError("STATIC_SHAPE requires an exact traversal_shape_digest")
        if (
            not isinstance(static_element_count, int)
            or isinstance(static_element_count, bool)
            or static_element_count < 0
        ):
            raise ValueError(
                "STATIC_SHAPE requires a non-negative traversal_element_count"
            )
    else:
        if static_shape_digest is not None or static_element_count is not None:
            raise ValueError("MATERIALIZED_SHAPE must not carry static shape metadata")

    element_program = build_collect_c3_1_program(
        payload=element_payload,
        catalog=catalog,
        program_id=program_id + ":element",
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
    )
    root = traverse_ordered_node(
        element_program.root,
        traversal_policy=traversal_policy,
    )
    metadata_payload: dict[str, Any] = {
        "schema": "mrw.successor.collect.c3.declared-traversal.v1",
        "operation_kind": c3.COLLECT_C3_1_KIND,
        "traversal_policy": traversal_policy,
        "compiled_traversal": True,
        "program_id": program_id,
        "catalog_id": catalog.catalog_id,
        "catalog_version": catalog.catalog_version,
        "catalog_digest": catalog.catalog_digest,
        "element_program_digest": element_program.program_digest,
    }
    if traversal_policy == "STATIC_SHAPE":
        metadata_payload["traversal_shape_digest"] = static_shape_digest
        metadata_payload["traversal_element_count"] = static_element_count
    metadata = freeze_json_object(metadata_payload)
    return ProgramSpec(
        program_id=program_id,
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity=c3.COLLECT_C3_1_SEMANTIC_IDENTITY,
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
        observation_profile=c3.COLLECT_TRAVERSAL_OBSERVATION_PROFILE,
        metadata=metadata,
        program_digest="",
    ).with_digest()


def compile_declared_traversal_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_contracts: OperationContractResolver,
) -> TraversalCompileStatus:
    """Compile through the shared compiler; report the exact blocker otherwise."""

    try:
        plan = compile_program(
            program,
            catalog,
            operation_contracts=operation_contracts,
        )
    except CompileFailure as exc:
        return TraversalCompileStatus(
            compiled=False,
            code=exc.code,
            message=str(exc),
            program_digest=program.program_digest,
        )
    return TraversalCompileStatus(
        compiled=True,
        code=TRAVERSAL_COMPILED_CODE,
        message=(
            f"TraverseOrdered compiled with occurrence binding "
            f"{TRAVERSAL_MATERIALIZER_TRANSFORM}@{TRAVERSAL_MATERIALIZER_VERSION}"
        ),
        program_digest=program.program_digest,
        plan_digest=plan.plan_digest,
    )
