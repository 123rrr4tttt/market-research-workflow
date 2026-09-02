"""Shared ProgramSpec/compiler builders for the C8 knowledge consumer atoms.

P4 ahead-of-time family-local scaffold: C8.1 demand-read, C8.2 ordered writing
composition, C8.3 report staging and C8.4 graph projection compile through the
shared successor Program AST and compiler as exact ProgramSpecs.  Every cell
owns typed return/failure/effect/authority profiles; handler binding closures
are produced per compiled step as pure payloads for the C8-owned substrate
binding module.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from app.successor_runtime.capabilities import c8_common as c8
from app.successor_runtime.capabilities.c8_common import C8ProjectionError
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    require_hex64,
    sha256_hex,
)
from app.successor_runtime.capabilities.codecs import PayloadCodec, dataclass_codec
from app.successor_runtime.language.algebra import (
    AlgebraRef,
    OperationSpec,
    ValueRef,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.object_contracts import (
    DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF,
    READ_CANONICAL_REF_RETURN_CONTRACT_REF,
    RESEARCH_ARTIFACT_RETURN_CONTRACT_REF,
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF,
    OperationContract,
    OperationContractRef,
    ReturnContract,
    make_operation_contract,
)
from app.successor_runtime.language.profiles import (
    AuthorityProfile,
    ContractProfileRef,
    EffectProfile,
    FailureProfile,
    InterpreterProfile,
    ObservationProfile,
    ResourceProfile,
    SemanticProfile,
)
from app.successor_runtime.language.program import ProgramSpec, atom_node, then_node
from app.successor_runtime.research.object_types import CANONICAL_CODEC_ID, ObjectType

__all__ = [
    "C8_1_INPUT_TYPE",
    "C8_1_KIND",
    "C8_1_OPERATION_ID",
    "C8_1_OWNER",
    "C8_1_PAYLOAD_CODEC_ID",
    "C8_1_RESULT_TYPE",
    "C8_2_COMPOSE_INPUT_TYPE",
    "C8_2_COMPOSE_KIND",
    "C8_2_COMPOSE_OPERATION_ID",
    "C8_2_COMPOSE_RESULT_TYPE",
    "C8_2_OWNER",
    "C8_2_STAGE_INPUT_TYPE",
    "C8_2_STAGE_KIND",
    "C8_2_STAGE_OPERATION_ID",
    "C8_2_STAGE_RESULT_TYPE",
    "C8_3_INPUT_TYPE",
    "C8_3_KIND",
    "C8_3_OPERATION_ID",
    "C8_3_OWNER",
    "C8_3_RESULT_TYPE",
    "C8_4_INPUT_TYPE",
    "C8_4_KIND",
    "C8_4_OPERATION_ID",
    "C8_4_OWNER",
    "C8_4_RESULT_TYPE",
    "C8_ADMISSION_INPUT_TYPE",
    "C8_ADMISSION_KIND",
    "C8_ADMISSION_OPERATION_ID",
    "C8_DELIVERY_BRIDGE_BLOCKER",
    "C8_DELIVERY_INTENT_PREPARE_KIND",
    "C8_DELIVERY_INTENT_PREPARE_OPERATION_ID",
    "C8_DELIVERY_INTENT_TYPE",
    "C8_DELIVERY_RECEIPT_TYPE",
    "C8_OPERATION_CATALOG_ID",
    "C8_OPERATION_CATALOG_VERSION",
    "C8_OPERATION_SEMANTIC_IDENTITY",
    "C8_RESEARCH_ARTIFACT_TYPE",
    "C8_VERIFY_KIND",
    "C8_VERIFY_OPERATION_ID",
    "C8_VERIFY_RESULT_TYPE",
    "C8CapabilityBundle",
    "C8DemandReadInput",
    "C8GraphProjectInput",
    "C8ReportStageInput",
    "C8WritingComposeInput",
    "build_c8_bridge_bundle",
    "build_c8_bundle",
    "build_c8_catalog",
    "build_c8_delivery_bridge_bundle",
    "build_c8_delivery_bridge_program",
    "build_c8_program",
    "build_c8_registry",
    "build_c8_report_bridge_program",
    "c8_return_contract",
    "compile_c8_delivery_bridge_program",
    "compile_c8_program",
    "compile_c8_report_bridge_program",
    "exact_contract_ref",
    "handler_binding_closure_payloads",
    "handler_binding_payload",
    "payload_body_digest",
    "payload_value_ref",
    "validate_delivery_operation_contract",
    "validate_delivery_payload_codec",
]

C8_OPERATION_CATALOG_ID = "mrw.functorial-successor.c8.operations"
C8_OPERATION_CATALOG_VERSION = "1.0.0"
C8_OPERATION_SEMANTIC_IDENTITY = "c8.knowledge-writing-report-graph"
C8_OBSERVATION_PROFILE = "mrw.successor.c8.observation.v1"

C8_1_OWNER = "typed_knowledge.c8.1.v1"
C8_2_OWNER = "writing.c8.2.v1"
C8_3_OWNER = "report.c8.3.v1"
C8_4_OWNER = "graph.c8.4.v1"

C8_1_OPERATION_ID = "c8.typed_knowledge.demand_read"
C8_1_KIND = "c8.typed_knowledge.demand_read.v1"
C8_1_PAYLOAD_CODEC_ID = "mrw.successor.c8.c8-1.payload.codec.v1"
C8_1_INPUT_TYPE = ObjectType("C8DemandReadInput.v1")
C8_1_RESULT_TYPE = ObjectType("C8DemandReadResult.v1")

C8_2_COMPOSE_OPERATION_ID = "c8.writing.compose"
C8_2_COMPOSE_KIND = "c8.writing.compose.v1"
C8_2_COMPOSE_PAYLOAD_CODEC_ID = "mrw.successor.c8.c8-2.compose.payload.codec.v1"
C8_2_COMPOSE_INPUT_TYPE = ObjectType("C8WritingComposeInput.v1")
C8_2_COMPOSE_RESULT_TYPE = ObjectType("C8WritingHandoff.v1")
C8_2_STAGE_OPERATION_ID = "c8.writing.stage"
C8_2_STAGE_KIND = "c8.writing.stage.v1"
C8_2_STAGE_INPUT_TYPE = C8_2_COMPOSE_RESULT_TYPE
C8_2_STAGE_RESULT_TYPE = ObjectType("C8StagedWritingArtifact.v1")

C8_3_OPERATION_ID = "c8.report.stage"
C8_3_KIND = "c8.report.stage.v1"
C8_3_PAYLOAD_CODEC_ID = "mrw.successor.c8.c8-3.payload.codec.v1"
C8_3_INPUT_TYPE = ObjectType("C8ReportSourceReads.v1")
C8_3_RESULT_TYPE = ObjectType("C8StagedReport.v1")

C8_4_OPERATION_ID = "c8.graph.project"
C8_4_KIND = "c8.graph.project.v1"
C8_4_PAYLOAD_CODEC_ID = "mrw.successor.c8.c8-4.payload.codec.v1"
C8_4_INPUT_TYPE = ObjectType("C8GraphProjectInput.v1")
C8_4_RESULT_TYPE = ObjectType("C8GraphContext.v1")

C8_VERIFY_OPERATION_ID = "c8.report.verify"
C8_VERIFY_KIND = "c8.report.verify.v1"
C8_VERIFY_RESULT_TYPE = ObjectType("C8ReportVerification.v1")
C8_ADMISSION_OPERATION_ID = "c8.report.admission"
C8_ADMISSION_KIND = "c8.report.admission.v1"
C8_ADMISSION_INPUT_TYPE = C8_VERIFY_RESULT_TYPE
C8_RESEARCH_ARTIFACT_TYPE = ObjectType("ResearchArtifact.v1")
C8_DELIVERY_INTENT_TYPE = ObjectType("DeliveryIntent.v1")
C8_DELIVERY_RECEIPT_TYPE = ObjectType("DeliveryReceiptRef.v1")
DELIVERY_INTERNAL_EXPORT_KIND = "delivery.internal_export.v1"
C8_DELIVERY_BRIDGE_BLOCKER = (
    "pure C8 cannot bind the exact shared delivery.internal_export.v1 "
    "OperationContract: capabilities may not import sibling first_specimen "
    "and the shared catalog/frozen JSON does not expose the full contract "
    "payload/digest to pure modules; the delivery step requires the PostgreSQL "
    "composition root to inject the exact shared contract"
)
C8_DELIVERY_INTENT_PREPARE_OPERATION_ID = "c8.delivery_intent_prepare"
C8_DELIVERY_INTENT_PREPARE_KIND = "c8.delivery_intent_prepare.v1"

_C8_1_RETURN_CONTRACT_REF = READ_CANONICAL_REF_RETURN_CONTRACT_REF
_C8_2_RETURN_CONTRACT_REF = SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF
_C8_3_RETURN_CONTRACT_REF = RUNTIME_VALUE_RETURN_CONTRACT_REF
_C8_4_RETURN_CONTRACT_REF = READ_CANONICAL_REF_RETURN_CONTRACT_REF

_CELL_IDS = ("C8.1", "C8.2", "C8.3", "C8.4")


@dataclass(frozen=True, slots=True)
class C8DemandReadInput:
    project_key: str
    item_key: str
    fields: tuple[str, ...]
    payload_digest: str = ""

    def __post_init__(self) -> None:
        _bind_payload_digest(self, "C8DemandReadInput")


@dataclass(frozen=True, slots=True)
class C8WritingComposeInput:
    project_key: str
    knowledge_item_key: str
    selection_hash: str
    selection_text: str
    demand_fields: tuple[str, ...]
    payload_digest: str = ""

    def __post_init__(self) -> None:
        _bind_payload_digest(self, "C8WritingComposeInput")


@dataclass(frozen=True, slots=True)
class C8ReportStageInput:
    project_key: str
    report_id: str
    topic: str
    source_keys: tuple[str, ...]
    payload_digest: str = ""

    def __post_init__(self) -> None:
        _bind_payload_digest(self, "C8ReportStageInput")


@dataclass(frozen=True, slots=True)
class C8GraphProjectInput:
    project_key: str
    graph_id: str
    node_keys: tuple[str, ...]
    node_types: tuple[str, ...]
    payload_digest: str = ""

    def __post_init__(self) -> None:
        _bind_payload_digest(self, "C8GraphProjectInput")


def payload_body_digest(payload: Any) -> str:
    body = {
        name: value
        for name, value in dataclasses.asdict(payload).items()
        if name != "payload_digest"
    }
    return content_digest(body)


def _bind_payload_digest(payload: Any, type_name: str) -> None:
    expected = payload_body_digest(payload)
    if payload.payload_digest == "":
        object.__setattr__(payload, "payload_digest", expected)
        return
    require_hex64(payload.payload_digest, f"{type_name}.payload_digest")
    if payload.payload_digest != expected:
        raise ValueError(
            f"{type_name}.payload_digest does not match recomputed body digest"
        )


@dataclass(frozen=True, slots=True)
class C8CapabilityBundle:
    bundle_id: str
    operations: tuple[OperationContract, ...]
    codecs: tuple[PayloadCodec, ...]
    profiles: dict[str, dict[str, object]]

    def codec_by_kind(self, kind: str) -> PayloadCodec:
        for codec in self.codecs:
            if codec.contract_ref.kind == kind:
                return codec
        raise KeyError(f"no C8 payload codec for kind {kind}")


def _profile_ref(profile: Any) -> ContractProfileRef:
    return ContractProfileRef(
        profile.profile_id,
        profile.profile_version,
        profile.profile_digest,
    )


def _cell_suffix(cell_id: str) -> str:
    return cell_id.lower().replace(".", "-")


def _semantic_profile(cell_id: str) -> SemanticProfile:
    suffix = _cell_suffix(cell_id)
    reads_creates = {
        "C8.1": (("C8DemandReadInput.v1",), ("C8DemandReadResult.v1",), ()),
        "C8.2": (
            ("C8WritingComposeInput.v1",),
            ("C8WritingHandoff.v1", "C8StagedWritingArtifact.v1"),
            (),
        ),
        "C8.3": (("C8ReportSourceReads.v1",), ("C8StagedReport.v1",), ()),
        "C8.4": (("C8GraphProjectInput.v1",), ("C8GraphContext.v1",), ()),
    }[cell_id]
    values = {
        "semantic_profile_id": f"c8.{suffix}.semantic",
        "semantic_profile_version": "1.0.0",
        "reads": reads_creates[0],
        "creates": reads_creates[1],
        "creates_relations": reads_creates[2],
        "declared_loss": (
            ("graph_node_filter", "report_export_body")
            if cell_id in ("C8.3", "C8.4")
            else ()
        ),
        "observation_profile_ref": f"mrw.successor.c8.{suffix}.observation.v1",
    }
    return SemanticProfile(**values, profile_digest=content_digest(values))


def _effect_profile(cell_id: str) -> EffectProfile:
    suffix = _cell_suffix(cell_id)
    execution_class = {
        "C8.1": "EFFECTFUL",
        "C8.2": "PURE_TRANSFORM",
        "C8.3": "ADMISSION",
        "C8.4": "PROJECTION",
    }[cell_id]
    values = {
        "effect_profile_id": f"c8.{suffix}.effect",
        "effect_profile_version": "1.0.0",
        "execution_class": execution_class,
        "external_visibility": "NONE",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": (),
        "internal_export_only": False,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": f"mrw.successor.c8.{suffix}.idempotency.v1",
    }
    return EffectProfile(**values, profile_digest=content_digest(values))


def _resource_profile(cell_id: str) -> ResourceProfile:
    suffix = _cell_suffix(cell_id)
    values = {
        "resource_profile_id": f"c8.{suffix}.resource",
        "resource_profile_version": "1.0.0",
        "resource_classes": ("CPU_LIGHT",),
        "concurrency_key": f"c8.{suffix}",
        "budget_units": "units",
        "default_soft_limit_seconds": 5,
        "default_hard_limit_seconds": 30,
        "node_profile_selector": "any",
        "budget_ref": f"mrw.functorial-successor.budget.c8-{suffix}.v1",
        "deadline_policy_ref": f"mrw.functorial-successor.deadline.c8-{suffix}.v1",
        "node_profile_requirements": ("any",),
        "units": 1,
    }
    return ResourceProfile(**values, profile_digest=content_digest(values))


def _failure_profile(cell_id: str) -> FailureProfile:
    suffix = _cell_suffix(cell_id)
    failures = {
        "C8.1": (
            "DEMAND_READ_UNAVAILABLE",
            "DEMAND_READ_AMBIGUOUS",
            "CANONICAL_REF_VALIDATION_FAILED",
        ),
        "C8.2": ("WRITING_SYNTHESIS_INCOMPLETE", "WRITING_STAGE_INVALID"),
        "C8.3": (
            "REPORT_LOCATOR_READ_ONLY_UNAVAILABLE",
            "REPORT_ADMISSION_INTERFACE_ONLY",
            "REPORT_EXPORT_NOT_EXECUTED",
        ),
        "C8.4": ("GRAPH_PROJECTION_DECLARED_LOSS", "GRAPH_ITEM_CANONICAL_REF_INVALID"),
    }[cell_id]
    values = {
        "failure_profile_id": f"c8.{suffix}.failure",
        "failure_profile_version": "1.0.0",
        "typed_failures": failures,
        "retryable": False,
        "degraded_acceptable": False,
        "unknown_outcome_supported": True,
        "readback_or_compensation": "readback",
        "failure_union_ref": f"mrw.functorial-successor.failures.c8-{suffix}.v1",
        "retryable_failure_kinds": (),
        "readback_profile_ref": {
            "C8.1": "c8.typed_knowledge.readback.v1",
            "C8.2": "c8.writing.readback.v1",
            "C8.3": "c8.report.admission.readback.v1",
            "C8.4": "c8.graph.readback.v1",
        }[cell_id],
        "compensation_profile_ref": None,
    }
    return FailureProfile(**values, profile_digest=content_digest(values))


def _authority_profile(cell_id: str) -> AuthorityProfile:
    suffix = _cell_suffix(cell_id)
    owner = {
        "C8.1": C8_1_OWNER,
        "C8.2": C8_2_OWNER,
        "C8.3": C8_3_OWNER,
        "C8.4": C8_4_OWNER,
    }[cell_id]
    values = {
        "authority_profile_id": f"c8.{suffix}.authority",
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": owner,
        "revalidation_points": ("claim_time",),
        "authority_epoch": 1,
    }
    return AuthorityProfile(**values, profile_digest=content_digest(values))


def _interpreter_profile(cell_id: str) -> InterpreterProfile:
    suffix = _cell_suffix(cell_id)
    supported_kinds = {
        "C8.1": (C8_1_KIND,),
        "C8.2": (C8_2_COMPOSE_KIND, C8_2_STAGE_KIND),
        "C8.3": (C8_3_KIND,),
        "C8.4": (C8_4_KIND,),
    }[cell_id]
    values = {
        "interpreter_profile_id": f"successor.c8.{suffix}.v1",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": supported_kinds,
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "interpreter": f"successor-native.c8.{suffix}",
                "version": "1.0.0",
                "boundary": "pure typed knowledge consumer; no legacy writer import",
            }
        ),
        "security_profile_ref": "mrw.functorial-successor.security.pure.v1",
        "resource_profile_ref": f"c8.{suffix}.resource@1.0.0",
        "credential_requirements_ref": None,
        "cancellation_profile_ref": "step_boundary",
        "idempotency_profile_ref": "logical_request_id",
        "authoritative_readback_profile_ref": None,
        "receipt_codec_ref": f"mrw.successor.c8.{suffix}.observation.v1",
    }
    return InterpreterProfile(**values, profile_digest=content_digest(values))


def _observation_profile(cell_id: str) -> ObservationProfile:
    suffix = _cell_suffix(cell_id)
    values = {
        "observation_profile_id": f"mrw.successor.c8.{suffix}.observation.v1",
        "observation_profile_version": "1.0.0",
        "dimensions": {
            "C8.1": ("read_handle", "canonical_identity", "provider_calls_zero"),
            "C8.2": ("ordered_composition", "declared_loss", "provenance_chain"),
            "C8.3": (
                "read_only_unavailable",
                "admission_interface_only",
                "declared_loss",
            ),
            "C8.4": ("declared_loss", "provenance_closure", "canonical_identity"),
        }[cell_id],
        "compatible_with_legacy": True,
        "observation_schema_ref": f"mrw.successor.c8.{suffix}.observation.v1",
    }
    return ObservationProfile(**values, profile_digest=content_digest(values))


def _make_contract(
    *,
    kind: str,
    input_type: ObjectType,
    output_type: ObjectType,
    return_contract_ref: str,
    semantic: SemanticProfile,
    effect: EffectProfile,
    resource: ResourceProfile,
    failure: FailureProfile,
    authority: AuthorityProfile,
    interpreter: InterpreterProfile,
    observation: ObservationProfile,
    owner: str,
) -> OperationContract:
    return make_operation_contract(
        kind=kind,
        contract_version="1.0.0",
        input_type=input_type,
        output_type=output_type,
        return_contract_ref=return_contract_ref,
        semantic_profile_ref=_profile_ref(semantic).to_ref_string(),
        effect_profile_ref=_profile_ref(effect).to_ref_string(),
        resource_profile_ref=_profile_ref(resource).to_ref_string(),
        failure_profile_ref=_profile_ref(failure).to_ref_string(),
        authority_profile_ref=_profile_ref(authority).to_ref_string(),
        interpreter_compatibility_ref=_profile_ref(interpreter).to_ref_string(),
        observation_profile_ref=_profile_ref(observation).to_ref_string(),
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=owner,
    )


def build_c8_bundle() -> C8CapabilityBundle:
    profiles_by_cell: dict[str, dict[str, object]] = {}
    contracts: list[OperationContract] = []
    for cell_id in _CELL_IDS:
        semantic = _semantic_profile(cell_id)
        effect = _effect_profile(cell_id)
        resource = _resource_profile(cell_id)
        failure = _failure_profile(cell_id)
        authority = _authority_profile(cell_id)
        interpreter = _interpreter_profile(cell_id)
        observation = _observation_profile(cell_id)
        profiles_by_cell[cell_id] = {
            "semantic": semantic,
            "effect": effect,
            "resource": resource,
            "failure": failure,
            "authority": authority,
            "interpreter": interpreter,
            "observation": observation,
        }
        owner = {
            "C8.1": C8_1_OWNER,
            "C8.2": C8_2_OWNER,
            "C8.3": C8_3_OWNER,
            "C8.4": C8_4_OWNER,
        }[cell_id]
        kind, input_type, output_type, return_ref = {
            "C8.1": (
                C8_1_KIND,
                C8_1_INPUT_TYPE,
                C8_1_RESULT_TYPE,
                _C8_1_RETURN_CONTRACT_REF,
            ),
            "C8.2": (
                C8_2_COMPOSE_KIND,
                C8_2_COMPOSE_INPUT_TYPE,
                C8_2_COMPOSE_RESULT_TYPE,
                _C8_2_RETURN_CONTRACT_REF,
            ),
            "C8.3": (
                C8_3_KIND,
                C8_3_INPUT_TYPE,
                C8_3_RESULT_TYPE,
                _C8_3_RETURN_CONTRACT_REF,
            ),
            "C8.4": (
                C8_4_KIND,
                C8_4_INPUT_TYPE,
                C8_4_RESULT_TYPE,
                _C8_4_RETURN_CONTRACT_REF,
            ),
        }[cell_id]
        contracts.append(
            _make_contract(
                kind=kind,
                input_type=input_type,
                output_type=output_type,
                return_contract_ref=return_ref,
                semantic=semantic,
                effect=effect,
                resource=resource,
                failure=failure,
                authority=authority,
                interpreter=interpreter,
                observation=observation,
                owner=owner,
            )
        )
        if cell_id == "C8.2":
            contracts.append(
                _make_contract(
                    kind=C8_2_STAGE_KIND,
                    input_type=C8_2_STAGE_INPUT_TYPE,
                    output_type=C8_2_STAGE_RESULT_TYPE,
                    return_contract_ref=_C8_2_RETURN_CONTRACT_REF,
                    semantic=semantic,
                    effect=effect,
                    resource=resource,
                    failure=failure,
                    authority=authority,
                    interpreter=interpreter,
                    observation=observation,
                    owner=owner,
                )
            )
    codecs = (
        _payload_codec(
            _contract_by_kind(contracts, C8_1_KIND).ref,
            C8_1_PAYLOAD_CODEC_ID,
            C8_1_INPUT_TYPE,
            C8DemandReadInput,
        ),
        _payload_codec(
            _contract_by_kind(contracts, C8_2_COMPOSE_KIND).ref,
            C8_2_COMPOSE_PAYLOAD_CODEC_ID,
            C8_2_COMPOSE_INPUT_TYPE,
            C8WritingComposeInput,
        ),
        _payload_codec(
            _contract_by_kind(contracts, C8_3_KIND).ref,
            C8_3_PAYLOAD_CODEC_ID,
            C8_3_INPUT_TYPE,
            C8ReportStageInput,
        ),
        _payload_codec(
            _contract_by_kind(contracts, C8_4_KIND).ref,
            C8_4_PAYLOAD_CODEC_ID,
            C8_4_INPUT_TYPE,
            C8GraphProjectInput,
        ),
    )
    return C8CapabilityBundle(
        bundle_id="mrw.functorial-successor.c8",
        operations=tuple(contracts),
        codecs=codecs,
        profiles=profiles_by_cell,
    )


def _contract_by_kind(
    contracts: list[OperationContract], kind: str
) -> OperationContract:
    return next(contract for contract in contracts if contract.ref.kind == kind)


def _payload_codec(
    contract_ref: OperationContractRef,
    codec_id: str,
    payload_type: ObjectType,
    dto_cls: type,
) -> PayloadCodec:
    return dataclass_codec(
        codec_id=codec_id,
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=payload_type.type_id,
        dto_cls=dto_cls,
    )


def build_c8_catalog(bundle: C8CapabilityBundle) -> OperationContractCatalogSnapshot:
    return OperationContractCatalogSnapshot(
        catalog_id=C8_OPERATION_CATALOG_ID,
        catalog_version=C8_OPERATION_CATALOG_VERSION,
        entries=tuple(
            (
                operation.ref.kind,
                operation.ref.contract_version,
                operation.ref.contract_digest,
                operation.owner_capability_id,
            )
            for operation in bundle.operations
        ),
    )


def build_c8_registry(bundle: C8CapabilityBundle) -> OperationContractRegistry:
    return OperationContractRegistry(build_c8_catalog(bundle), bundle.operations)


def exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
    *,
    kind: str,
) -> OperationContractRef:
    ref = catalog.lookup(kind)
    if ref is None:
        raise ValueError(f"contract {kind} missing from catalog {catalog.catalog_id}")
    return ref


def c8_return_contract(
    return_contract_ref: str,
    *,
    admission_required: bool = False,
) -> ReturnContract:
    return ReturnContract(
        success_modes=("SUCCEEDED",),
        failure_modes=("FAILED",),
        admission_required=admission_required,
        wait_modes=("WAIT",),
        cancel_modes=("CANCELED",),
    )


def payload_value_ref(
    payload: Any,
    *,
    program_id: str,
    project_key: str,
    codec_id: str,
    object_type: ObjectType,
    value_suffix: str,
) -> ValueRef:
    if payload.project_key != project_key:
        raise ValueError("payload project scope drift")
    plain = dataclasses.asdict(payload)
    exact_text = canonical_json(plain)
    exact_bytes = exact_text.encode("utf-8")
    require_hex64(payload.payload_digest, "payload payload_digest")
    full_bytes_digest = sha256_hex(exact_bytes)
    value_id = f"{program_id}:payload:{value_suffix}"
    provenance_digest = content_digest(
        {
            "schema": f"mrw.successor.c8.{value_suffix}.payload-provenance.v1",
            "program_id": program_id,
            "project_key": project_key,
            "semantic_payload_digest": payload.payload_digest,
            "artifact_content_digest": full_bytes_digest,
        }
    )
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=object_type,
        codec_id=codec_id,
        content_digest=full_bytes_digest,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact_bytes),
        provenance_digest=provenance_digest,
    )


def _atom(
    *,
    operation_id: str,
    contract_ref: OperationContractRef,
    input_type: ObjectType,
    output_type: ObjectType,
    return_contract_ref: str,
    value_ref: ValueRef | None = None,
    input_refs: tuple[ValueRef, ...] | None = None,
    payload_ref: ValueRef | None = None,
    admission_required: bool = False,
) -> Any:
    inputs = (
        tuple(input_refs)
        if input_refs is not None
        else ((value_ref,) if value_ref is not None else ())
    )
    payload = payload_ref if payload_ref is not None else value_ref
    if payload is None:
        raise ValueError("atom requires a payload value ref")
    operation = OperationSpec(
        operation_id=operation_id,
        contract_ref=contract_ref,
        input_refs=inputs,
        payload_ref=payload,
        allowed_overrides=freeze_json_object({}),
    )
    return atom_node(
        operation,
        input_type=input_type,
        output_type=output_type,
        return_contract=c8_return_contract(
            return_contract_ref,
            admission_required=admission_required,
        ),
    )


def build_c8_program(
    *,
    cell_id: str,
    payload: Any,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> ProgramSpec:
    if payload.project_key != project_key:
        raise ValueError("payload project_key does not match Program project_key")
    extra_metadata: dict[str, object] = {}
    if cell_id == "C8.2":
        compose_ref = exact_contract_ref(catalog, kind=C8_2_COMPOSE_KIND)
        stage_ref = exact_contract_ref(catalog, kind=C8_2_STAGE_KIND)
        handoff_value = payload_value_ref(
            payload,
            program_id=program_id,
            project_key=project_key,
            codec_id=C8_2_COMPOSE_PAYLOAD_CODEC_ID,
            object_type=C8_2_COMPOSE_INPUT_TYPE,
            value_suffix="c8-2-compose",
        )
        stage_input = ValueRef(
            value_id=f"{program_id}:payload:c8-2-stage",
            project_key=project_key,
            object_type=C8_2_STAGE_INPUT_TYPE,
            codec_id=C8_2_COMPOSE_PAYLOAD_CODEC_ID,
            content_digest=handoff_value.content_digest,
            storage_kind="project_value_ref",
            store_id="successor_values",
            store_version="1",
            storage_ref=handoff_value.storage_ref,
            byte_size=handoff_value.byte_size,
            provenance_digest=handoff_value.provenance_digest,
        )
        compose_atom = _atom(
            operation_id=C8_2_COMPOSE_OPERATION_ID,
            contract_ref=compose_ref,
            input_type=C8_2_COMPOSE_INPUT_TYPE,
            output_type=C8_2_COMPOSE_RESULT_TYPE,
            return_contract_ref=_C8_2_RETURN_CONTRACT_REF,
            value_ref=handoff_value,
        )
        stage_atom = _atom(
            operation_id=C8_2_STAGE_OPERATION_ID,
            contract_ref=stage_ref,
            input_type=C8_2_STAGE_INPUT_TYPE,
            output_type=C8_2_STAGE_RESULT_TYPE,
            return_contract_ref=_C8_2_RETURN_CONTRACT_REF,
            value_ref=stage_input,
        )
        root = then_node(compose_atom, stage_atom)
        input_type = C8_2_COMPOSE_INPUT_TYPE
        output_type = C8_2_STAGE_RESULT_TYPE
        return_contract_ref = _C8_2_RETURN_CONTRACT_REF
        operation_kinds = (C8_2_COMPOSE_KIND, C8_2_STAGE_KIND)
        payload_value = handoff_value
    else:
        kind, operation_id, codec_id, suffix, object_type, result_type = {
            "C8.1": (
                C8_1_KIND,
                C8_1_OPERATION_ID,
                C8_1_PAYLOAD_CODEC_ID,
                "c8-1",
                C8_1_INPUT_TYPE,
                C8_1_RESULT_TYPE,
            ),
            "C8.3": (
                C8_3_KIND,
                C8_3_OPERATION_ID,
                C8_3_PAYLOAD_CODEC_ID,
                "c8-3",
                C8_3_INPUT_TYPE,
                C8_3_RESULT_TYPE,
            ),
            "C8.4": (
                C8_4_KIND,
                C8_4_OPERATION_ID,
                C8_4_PAYLOAD_CODEC_ID,
                "c8-4",
                C8_4_INPUT_TYPE,
                C8_4_RESULT_TYPE,
            ),
        }[cell_id]
        ref = exact_contract_ref(catalog, kind=kind)
        value = payload_value_ref(
            payload,
            program_id=program_id,
            project_key=project_key,
            codec_id=codec_id,
            object_type=object_type,
            value_suffix=suffix,
        )
        return_contract_ref = {
            "C8.1": _C8_1_RETURN_CONTRACT_REF,
            "C8.3": _C8_3_RETURN_CONTRACT_REF,
            "C8.4": _C8_4_RETURN_CONTRACT_REF,
        }[cell_id]
        root = _atom(
            operation_id=operation_id,
            contract_ref=ref,
            input_type=object_type,
            output_type=result_type,
            return_contract_ref=return_contract_ref,
            value_ref=value,
        )
        input_type = root.input_type
        output_type = root.output_type
        operation_kinds = (kind,)
        payload_value = value
        if cell_id == "C8.3":
            extra_metadata = {
                "admission_interface_digest": c8.C8_3_ADMISSION_INTERFACE_DIGEST,
                "delivery_interface_digest": c8.C8_3_DELIVERY_INTERFACE_DIGEST,
            }
    metadata = freeze_json_object(
        {
            "schema": f"mrw.successor.c8.{cell_id.replace('.', '-')}.program-metadata.v1",
            "operation_kinds": list(operation_kinds),
            "project_registry_revision": project_registry_revision,
            "project_scope_digest": project_scope_digest,
            "payload_value_id": payload_value.value_id,
            "payload_storage_ref": payload_value.storage_ref,
            "payload_content_digest": payload_value.content_digest,
            "payload_provenance_digest": payload_value.provenance_digest,
            "canonical_owner": {
                "C8.1": C8_1_OWNER,
                "C8.2": C8_2_OWNER,
                "C8.3": C8_3_OWNER,
                "C8.4": C8_4_OWNER,
            }[cell_id],
            "return_contract_ref": return_contract_ref,
            "admission_required": False,
            "lifecycle_state": "P4_NOT_STARTED",
            "status": c8.AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED,
            **extra_metadata,
        }
    )
    return ProgramSpec(
        program_id=program_id,
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity=C8_OPERATION_SEMANTIC_IDENTITY,
        input_type=input_type,
        output_type=output_type,
        root=root,
        algebra_refs=(
            AlgebraRef(
                algebra_id="mrw.successor.language.algebra",
                algebra_version="1",
            ),
        ),
        transform_refs=(),
        observation_profile=C8_OBSERVATION_PROFILE,
        metadata=metadata,
        program_digest="",
    ).with_digest()


def compile_c8_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_contracts: OperationContractRegistry,
) -> Any:
    return compile_program(
        program,
        catalog,
        operation_contracts=operation_contracts,
    )


def handler_binding_payload(
    *,
    operation_contract_digest: str,
    interpreter_profile_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    authority_requirement_digest: str,
    resource_policy_epoch: int = 0,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> dict[str, Any]:
    for name, value in {
        "operation_contract_digest": operation_contract_digest,
        "interpreter_profile_digest": interpreter_profile_digest,
        "deployment_catalog_digest": deployment_catalog_digest,
        "project_scope_digest": project_scope_digest,
        "authority_requirement_digest": authority_requirement_digest,
    }.items():
        require_hex64(value, name)
    return {
        "operation_contract_digest": operation_contract_digest,
        "interpreter_profile_digest": interpreter_profile_digest,
        "deployment_catalog_digest": deployment_catalog_digest,
        "runtime_protocol_version": runtime_protocol_version,
        "project_scope_digest": project_scope_digest,
        "resource_policy_epoch": resource_policy_epoch,
        "authority_requirement_digest": authority_requirement_digest,
    }


def handler_binding_closure_payloads(
    plan: Any,
    *,
    interpreter_profile_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    authority_requirement_digest: str,
) -> tuple[dict[str, Any], ...]:
    closure: list[dict[str, Any]] = []
    for step in plan.ordered_steps:
        ref = step.operation_contract_ref
        if ref is None:
            raise ValueError("ExecutionPlan step is missing an operation contract ref")
        closure.append(
            {
                "step_id": step.step_id,
                "operation_id": step.operation_id,
                "operation_kind": ref.kind,
                "payload": handler_binding_payload(
                    operation_contract_digest=ref.contract_digest,
                    interpreter_profile_digest=interpreter_profile_digest,
                    deployment_catalog_digest=deployment_catalog_digest,
                    project_scope_digest=project_scope_digest,
                    authority_requirement_digest=authority_requirement_digest,
                ),
            }
        )
    return tuple(closure)


def build_c8_bridge_bundle() -> C8CapabilityBundle:
    base = build_c8_bundle()
    profiles = base.profiles["C8.3"]
    verify_contract = _make_contract(
        kind=C8_VERIFY_KIND,
        input_type=C8_3_RESULT_TYPE,
        output_type=C8_VERIFY_RESULT_TYPE,
        return_contract_ref=_C8_2_RETURN_CONTRACT_REF,
        semantic=profiles["semantic"],
        effect=profiles["effect"],
        resource=profiles["resource"],
        failure=profiles["failure"],
        authority=profiles["authority"],
        interpreter=profiles["interpreter"],
        observation=profiles["observation"],
        owner=C8_3_OWNER,
    )
    admission_contract = _make_contract(
        kind=C8_ADMISSION_KIND,
        input_type=C8_ADMISSION_INPUT_TYPE,
        output_type=C8_RESEARCH_ARTIFACT_TYPE,
        return_contract_ref=RESEARCH_ARTIFACT_RETURN_CONTRACT_REF,
        semantic=profiles["semantic"],
        effect=profiles["effect"],
        resource=profiles["resource"],
        failure=profiles["failure"],
        authority=profiles["authority"],
        interpreter=profiles["interpreter"],
        observation=profiles["observation"],
        owner=C8_3_OWNER,
    )
    return C8CapabilityBundle(
        bundle_id="mrw.functorial-successor.c8.bridge",
        operations=base.operations + (verify_contract, admission_contract),
        codecs=base.codecs,
        profiles=base.profiles,
    )


def build_c8_report_bridge_program(
    *,
    stage_payload: C8ReportStageInput,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> ProgramSpec:
    if stage_payload.project_key != project_key:
        raise ValueError("stage payload project_key does not match Program")
    stage_ref = exact_contract_ref(catalog, kind=C8_3_KIND)
    verify_ref = exact_contract_ref(catalog, kind=C8_VERIFY_KIND)
    admission_ref = exact_contract_ref(catalog, kind=C8_ADMISSION_KIND)
    stage_value = payload_value_ref(
        stage_payload,
        program_id=program_id,
        project_key=project_key,
        codec_id=C8_3_PAYLOAD_CODEC_ID,
        object_type=C8_3_INPUT_TYPE,
        value_suffix="c8-3",
    )
    verify_value = ValueRef(
        value_id=f"{program_id}:payload:c8-verify",
        project_key=project_key,
        object_type=C8_3_RESULT_TYPE,
        codec_id=C8_3_PAYLOAD_CODEC_ID,
        content_digest=stage_value.content_digest,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=stage_value.storage_ref,
        byte_size=stage_value.byte_size,
        provenance_digest=stage_value.provenance_digest,
    )
    stage_atom = _atom(
        operation_id=C8_3_OPERATION_ID,
        contract_ref=stage_ref,
        input_type=C8_3_INPUT_TYPE,
        output_type=C8_3_RESULT_TYPE,
        return_contract_ref=_C8_3_RETURN_CONTRACT_REF,
        value_ref=stage_value,
    )
    verify_atom = _atom(
        operation_id=C8_VERIFY_OPERATION_ID,
        contract_ref=verify_ref,
        input_type=C8_3_RESULT_TYPE,
        output_type=C8_VERIFY_RESULT_TYPE,
        return_contract_ref=_C8_2_RETURN_CONTRACT_REF,
        value_ref=verify_value,
    )
    admission_atom = _atom(
        operation_id=C8_ADMISSION_OPERATION_ID,
        contract_ref=admission_ref,
        input_type=C8_ADMISSION_INPUT_TYPE,
        output_type=C8_RESEARCH_ARTIFACT_TYPE,
        return_contract_ref=RESEARCH_ARTIFACT_RETURN_CONTRACT_REF,
        value_ref=verify_value,
    )
    root = then_node(then_node(stage_atom, verify_atom), admission_atom)
    metadata = freeze_json_object(
        {
            "schema": "mrw.successor.c8.bridge.program-metadata.v1",
            "operation_kinds": [
                C8_3_KIND,
                C8_VERIFY_KIND,
                C8_ADMISSION_KIND,
            ],
            "project_registry_revision": project_registry_revision,
            "project_scope_digest": project_scope_digest,
            "ordered_semantic_path": [
                "report_stage",
                "report_verification",
                "report_admission",
            ],
            "canonical_owner": C8_3_OWNER,
            "admission_required": True,
            "lifecycle_state": "P4_NOT_STARTED",
            "status": c8.AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED,
        }
    )
    return ProgramSpec(
        program_id=program_id,
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity="c8.report.stage-verify-admission",
        input_type=C8_3_INPUT_TYPE,
        output_type=C8_RESEARCH_ARTIFACT_TYPE,
        root=root,
        algebra_refs=(
            AlgebraRef(
                algebra_id="mrw.successor.language.algebra",
                algebra_version="1",
            ),
        ),
        transform_refs=(),
        observation_profile=C8_OBSERVATION_PROFILE,
        metadata=metadata,
        program_digest="",
    ).with_digest()


def compile_c8_report_bridge_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_contracts: OperationContractRegistry,
) -> Any:
    return compile_program(
        program,
        catalog,
        operation_contracts=operation_contracts,
    )


def validate_delivery_operation_contract(
    delivery_operation: OperationContract,
) -> OperationContract:
    if delivery_operation.ref.kind != DELIVERY_INTERNAL_EXPORT_KIND:
        raise C8ProjectionError(
            "delivery operation kind must be delivery.internal_export.v1"
        )
    if delivery_operation.input_type.type_id != C8_DELIVERY_INTENT_TYPE.type_id:
        raise C8ProjectionError("delivery operation input must be DeliveryIntent.v1")
    if delivery_operation.output_type.type_id != C8_DELIVERY_RECEIPT_TYPE.type_id:
        raise C8ProjectionError(
            "delivery operation output must be DeliveryReceiptRef.v1"
        )
    if (
        delivery_operation.return_contract_ref
        != DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF
    ):
        raise C8ProjectionError(
            "delivery operation must use the delivery receipt return contract"
        )
    for name in (
        "semantic_profile_ref",
        "effect_profile_ref",
        "resource_profile_ref",
        "failure_profile_ref",
        "authority_profile_ref",
        "interpreter_compatibility_ref",
        "observation_profile_ref",
    ):
        if not getattr(delivery_operation, name):
            raise C8ProjectionError(f"delivery operation missing exact {name}")
    if (
        not delivery_operation.ref.contract_digest
        or len(delivery_operation.ref.contract_digest) != 64
    ):
        raise C8ProjectionError("delivery operation contract digest is not exact")
    return delivery_operation


def validate_delivery_payload_codec(
    delivery_codec: PayloadCodec,
    delivery_operation: OperationContract,
) -> PayloadCodec:
    if delivery_codec.codec_id != "delivery.internal_export.v1.payload":
        raise C8ProjectionError(
            "delivery codec id must be delivery.internal_export.v1.payload"
        )
    if delivery_codec.payload_type_id != "InternalExportInput.v1":
        raise C8ProjectionError(
            "delivery codec payload type must be InternalExportInput.v1"
        )
    if delivery_codec.contract_ref != delivery_operation.ref:
        raise C8ProjectionError(
            "delivery codec contract ref must equal the exact delivery operation"
        )
    return delivery_codec


def build_c8_delivery_bridge_bundle(
    delivery_operation: OperationContract,
    delivery_codec: PayloadCodec,
) -> C8CapabilityBundle:
    validate_delivery_operation_contract(delivery_operation)
    validate_delivery_payload_codec(delivery_codec, delivery_operation)
    base = build_c8_bridge_bundle()
    profiles = base.profiles["C8.3"]
    prepare_contract = _make_contract(
        kind=C8_DELIVERY_INTENT_PREPARE_KIND,
        input_type=C8_RESEARCH_ARTIFACT_TYPE,
        output_type=C8_DELIVERY_INTENT_TYPE,
        return_contract_ref=_C8_3_RETURN_CONTRACT_REF,
        semantic=profiles["semantic"],
        effect=profiles["effect"],
        resource=profiles["resource"],
        failure=profiles["failure"],
        authority=profiles["authority"],
        interpreter=profiles["interpreter"],
        observation=profiles["observation"],
        owner=C8_3_OWNER,
    )
    return C8CapabilityBundle(
        bundle_id="mrw.functorial-successor.c8.delivery-bridge",
        operations=base.operations + (prepare_contract, delivery_operation),
        codecs=base.codecs + (delivery_codec,),
        profiles=base.profiles,
    )


def build_c8_delivery_bridge_program(
    *,
    delivery_operation: OperationContract,
    delivery_codec: PayloadCodec,
    delivery_payload_ref: ValueRef,
    artifact_input_ref: ValueRef,
    intent_input_ref: ValueRef,
    stage_payload: C8ReportStageInput,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> ProgramSpec:
    validate_delivery_operation_contract(delivery_operation)
    validate_delivery_payload_codec(delivery_codec, delivery_operation)
    if delivery_payload_ref.object_type.type_id != "InternalExportInput.v1":
        raise C8ProjectionError(
            "delivery payload ref object type must be InternalExportInput.v1"
        )
    if delivery_payload_ref.codec_id != delivery_codec.codec_id:
        raise C8ProjectionError(
            "delivery payload ref codec must equal the delivery codec"
        )
    if artifact_input_ref.object_type != C8_RESEARCH_ARTIFACT_TYPE:
        raise C8ProjectionError(
            "artifact input ref object type must be ResearchArtifact.v1"
        )
    if artifact_input_ref.codec_id != CANONICAL_CODEC_ID:
        raise C8ProjectionError("artifact input ref must use the canonical JSON codec")
    if intent_input_ref.object_type != C8_DELIVERY_INTENT_TYPE:
        raise C8ProjectionError(
            "intent input ref object type must be DeliveryIntent.v1"
        )
    if intent_input_ref.codec_id != CANONICAL_CODEC_ID:
        raise C8ProjectionError("intent input ref must use the canonical JSON codec")
    refs = (
        delivery_payload_ref,
        artifact_input_ref,
        intent_input_ref,
    )
    storage_refs = [ref.storage_ref for ref in refs]
    if len(set(storage_refs)) != len(storage_refs):
        raise C8ProjectionError("delivery bridge refs must not share storage_ref")
    value_ids = [ref.value_id for ref in refs]
    if len(set(value_ids)) != len(value_ids):
        raise C8ProjectionError(
            "delivery bridge refs must have distinct value identities"
        )
    if stage_payload.project_key != project_key:
        raise ValueError("stage payload project_key does not match Program")
    stage_ref = exact_contract_ref(catalog, kind=C8_3_KIND)
    verify_ref = exact_contract_ref(catalog, kind=C8_VERIFY_KIND)
    admission_ref = exact_contract_ref(catalog, kind=C8_ADMISSION_KIND)
    prepare_ref = exact_contract_ref(catalog, kind=C8_DELIVERY_INTENT_PREPARE_KIND)
    delivery_ref = exact_contract_ref(catalog, kind=DELIVERY_INTERNAL_EXPORT_KIND)
    stage_value = payload_value_ref(
        stage_payload,
        program_id=program_id,
        project_key=project_key,
        codec_id=C8_3_PAYLOAD_CODEC_ID,
        object_type=C8_3_INPUT_TYPE,
        value_suffix="c8-3",
    )
    verify_value = ValueRef(
        value_id=f"{program_id}:payload:c8-verify",
        project_key=project_key,
        object_type=C8_3_RESULT_TYPE,
        codec_id=C8_3_PAYLOAD_CODEC_ID,
        content_digest=stage_value.content_digest,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{program_id}:payload:c8-verify",
        byte_size=stage_value.byte_size,
        provenance_digest=content_digest(
            {"template": f"{program_id}:payload:c8-verify"}
        ),
    )
    stage_atom = _atom(
        operation_id=C8_3_OPERATION_ID,
        contract_ref=stage_ref,
        input_type=C8_3_INPUT_TYPE,
        output_type=C8_3_RESULT_TYPE,
        return_contract_ref=_C8_3_RETURN_CONTRACT_REF,
        value_ref=stage_value,
    )
    verify_atom = _atom(
        operation_id=C8_VERIFY_OPERATION_ID,
        contract_ref=verify_ref,
        input_type=C8_3_RESULT_TYPE,
        output_type=C8_VERIFY_RESULT_TYPE,
        return_contract_ref=_C8_2_RETURN_CONTRACT_REF,
        value_ref=verify_value,
    )
    admission_atom = _atom(
        operation_id=C8_ADMISSION_OPERATION_ID,
        contract_ref=admission_ref,
        input_type=C8_VERIFY_RESULT_TYPE,
        output_type=C8_RESEARCH_ARTIFACT_TYPE,
        return_contract_ref=RESEARCH_ARTIFACT_RETURN_CONTRACT_REF,
        value_ref=verify_value,
    )
    prepare_atom = _atom(
        operation_id=C8_DELIVERY_INTENT_PREPARE_OPERATION_ID,
        contract_ref=prepare_ref,
        input_type=C8_RESEARCH_ARTIFACT_TYPE,
        output_type=C8_DELIVERY_INTENT_TYPE,
        return_contract_ref=_C8_3_RETURN_CONTRACT_REF,
        value_ref=artifact_input_ref,
    )
    delivery_atom = _atom(
        operation_id="delivery.internal_export",
        contract_ref=delivery_ref,
        input_type=C8_DELIVERY_INTENT_TYPE,
        output_type=C8_DELIVERY_RECEIPT_TYPE,
        return_contract_ref=DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF,
        input_refs=(artifact_input_ref, intent_input_ref),
        payload_ref=delivery_payload_ref,
        admission_required=True,
    )
    root = then_node(
        then_node(
            then_node(stage_atom, verify_atom),
            admission_atom,
        ),
        then_node(prepare_atom, delivery_atom),
    )
    metadata = freeze_json_object(
        {
            "schema": "mrw.successor.c8.delivery-bridge.program-metadata.v1",
            "operation_kinds": [
                C8_3_KIND,
                C8_VERIFY_KIND,
                C8_ADMISSION_KIND,
                C8_DELIVERY_INTENT_PREPARE_KIND,
                DELIVERY_INTERNAL_EXPORT_KIND,
            ],
            "project_registry_revision": project_registry_revision,
            "project_scope_digest": project_scope_digest,
            "ordered_semantic_path": [
                "report_stage",
                "report_verification",
                "report_admission",
                "delivery_intent_prepare",
                "delivery.internal_export",
            ],
            "canonical_owner": C8_3_OWNER,
            "admission_required": True,
            "lifecycle_state": "P4_NOT_STARTED",
            "status": c8.AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED,
        }
    )
    return ProgramSpec(
        program_id=program_id,
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity="c8.report.stage-verify-admission-delivery",
        input_type=C8_3_INPUT_TYPE,
        output_type=C8_DELIVERY_RECEIPT_TYPE,
        root=root,
        algebra_refs=(
            AlgebraRef(
                algebra_id="mrw.successor.language.algebra",
                algebra_version="1",
            ),
        ),
        transform_refs=(),
        observation_profile=C8_OBSERVATION_PROFILE,
        metadata=metadata,
        program_digest="",
    ).with_digest()


def compile_c8_delivery_bridge_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_contracts: OperationContractRegistry,
) -> Any:
    return compile_program(
        program,
        catalog,
        operation_contracts=operation_contracts,
    )
