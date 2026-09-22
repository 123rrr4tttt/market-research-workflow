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
from typing import Annotated, Any, Literal

from app.successor_runtime.capabilities import c8_common as c8
from app.successor_runtime.capabilities.c8_common import (
    reject_c8_key,
    reject_c8_projection,
    reject_c8_value,
)
from app.successor_runtime.capabilities.c8_graph_projection_contribution import (
    C8_4_INPUT_TYPE,
    C8_4_KIND,
    C8_4_OPERATION_ID,
    C8_4_OWNER,
    C8_4_PAYLOAD_CODEC_ID,  # noqa: F401 - retained public compatibility export
    C8_4_RESULT_TYPE,
    C8_4_RETURN_CONTRACT_REF,
    C8CellDefinition,
    C8GraphProjectInput,
    C8GraphProjectionAssemblyContext,
    C8GraphProjectionRuntimeBinding,
    c8_graph_projection_definition_issues,
)
from app.successor_runtime.capabilities.c8_native_contribution import (
    C8NativeAssemblyContext,
    C8NativeDefinition,
    C8NativeRuntimeBinding,
)
from app.successor_runtime.capabilities.c8_report_contribution import (
    C8_3_INPUT_TYPE,
    C8_3_KIND,
    C8_3_OPERATION_ID,
    C8_3_OWNER,
    C8_3_PAYLOAD_CODEC_ID,
    C8_3_RESULT_TYPE,
    C8ReportStageInput,  # noqa: F401 - retained public compatibility export
    c8_report_native_contribution,
)
from app.successor_runtime.capabilities.c8_typed_knowledge_contribution import (
    C8_1_INPUT_TYPE,
    C8_1_KIND,
    C8_1_OPERATION_ID,
    C8_1_OWNER,
    C8_1_PAYLOAD_CODEC_ID,
    C8_1_RESULT_TYPE,
    C8DemandReadInput,  # noqa: F401 - retained public compatibility export
    C8_TYPED_KNOWLEDGE_NATIVE,
)
from app.successor_runtime.capabilities.c8_writing_contribution import (
    C8_2_COMPOSE_INPUT_TYPE,
    C8_2_COMPOSE_KIND,
    C8_2_COMPOSE_OPERATION_ID,
    C8_2_COMPOSE_PAYLOAD_CODEC_ID,
    C8_2_COMPOSE_RESULT_TYPE,
    C8_2_OWNER,
    C8_2_STAGE_INPUT_TYPE,
    C8_2_STAGE_KIND,
    C8_2_STAGE_OPERATION_ID,
    C8_2_STAGE_RESULT_TYPE,
    C8WritingComposeInput,  # noqa: F401 - retained public compatibility export
    c8_writing_native_contribution,
)
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
from functorial_kit.contributions import compose_contributions
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import NativeContribution
from mrw_functorial_kit.contributions.c8_graph_projection import (
    c8_graph_projection_native_contributions,
)

__all__ = [
    "C8_1_INPUT_TYPE",
    "C8_1_KIND",
    "C8_1_OPERATION_ID",
    "C8_1_OWNER",
    "C8_1_PAYLOAD_CODEC_ID",
    "C8_1_RESULT_TYPE",
    "C8_2_COMPOSE_INPUT_TYPE",
    "C8_2_COMPOSE_KIND",
    "C8_2_COMPOSE_PAYLOAD_CODEC_ID",
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
    "C8NativeContribution",
    "C8GraphProjectInput",
    "C8ReportStageInput",
    "C8WritingComposeInput",
    "build_c8_bridge_bundle",
    "build_c8_bundle",
    "build_c8_catalog",
    "compose_default_c8_graph_projection_contributions",
    "graph_projection_binding",
    "graph_projection_definition",
    "validate_c8_graph_projection_contributions",
    "validate_c8_native_contributions",
    "build_c8_delivery_bridge_bundle",
    "build_c8_delivery_bridge_program",
    "build_c8_program",
    "build_c8_registry",
    "c8_native_binding",
    "c8_native_definition",
    "compose_default_c8_native_contributions",
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
_C8_4_RETURN_CONTRACT_REF = C8_4_RETURN_CONTRACT_REF
_CELL_IDS = ("C8.1", "C8.2", "C8.3")


def payload_body_digest(payload: Any) -> str:
    body = {
        name: value
        for name, value in dataclasses.asdict(payload).items()
        if name != "payload_digest"
    }
    return content_digest(body)


def _profile_ref(profile: Any) -> ContractProfileRef:
    return ContractProfileRef(
        profile.profile_id,
        profile.profile_version,
        profile.profile_digest,
    )


def _cell_suffix(cell_id: str) -> str:
    return cell_id.lower().replace(".", "-")


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
        reject_c8_key(f"no C8 payload codec for kind {kind}")


C8NativeContribution = NativeContribution[
    C8NativeDefinition,
    C8NativeAssemblyContext,
    C8NativeRuntimeBinding,
]

c8_native_contributions: tuple[C8NativeContribution, ...] = (
    C8_TYPED_KNOWLEDGE_NATIVE,
    c8_writing_native_contribution,
    c8_report_native_contribution,
)


def compose_default_c8_native_contributions() -> tuple[
    C8NativeContribution, ...
]:
    """Return the non-graph native list after validating its projections."""

    return validate_c8_native_contributions(c8_native_contributions)


def validate_c8_native_contributions(
    natives: tuple[C8NativeContribution, ...],
) -> tuple[C8NativeContribution, ...]:
    composition = compose_contributions(tuple(native.projection for native in natives))
    if isinstance(composition, Failure):
        reject_c8_value(
            "C8 native contribution catalog invalid: " f"{composition.message}"
        )
    cell_ids: set[str] = set()
    for native in natives:
        definition = native.definition
        expected_cells = {"C8.1", "C8.2", "C8.3"}
        if definition.cell_id not in expected_cells:
            reject_c8_value(
                f"unexpected non-graph C8 native cell {definition.cell_id}"
            )
        if definition.cell_id in cell_ids:
            reject_c8_value(f"duplicate native C8 cell id {definition.cell_id}")
        cell_ids.add(definition.cell_id)
    return natives


def _c8_native_bindings(
    native_composition: tuple[C8NativeContribution, ...] | None,
) -> tuple[C8NativeRuntimeBinding, ...]:
    natives = (
        compose_default_c8_native_contributions()
        if native_composition is None
        else validate_c8_native_contributions(native_composition)
    )
    bindings: list[C8NativeRuntimeBinding] = []
    for native in natives:
        binding = native.assemble(C8NativeAssemblyContext())
        if isinstance(binding, Failure):
            reject_c8_value(
                f"native C8 contribution {native.projection.id} invalid: "
                f"{binding.message}"
            )
        bindings.append(binding)
    return tuple(bindings)


def c8_native_binding(
    cell_id: str,
    *,
    native_composition: tuple[C8NativeContribution, ...] | None = None,
) -> C8NativeRuntimeBinding:
    for binding in _c8_native_bindings(native_composition):
        if binding.cell_id == cell_id:
            return binding
    reject_c8_value(f"native C8 operation binding {cell_id} is not declared")


def c8_native_definition(
    cell_id: str,
    *,
    native_composition: tuple[C8NativeContribution, ...] | None = None,
) -> C8NativeDefinition:
    natives = (
        compose_default_c8_native_contributions()
        if native_composition is None
        else validate_c8_native_contributions(native_composition)
    )
    for native in natives:
        if native.definition.cell_id == cell_id:
            return native.definition
    reject_c8_value(f"native C8 operation definition {cell_id} is not declared")


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


GraphProjectionNativeContribution = NativeContribution[
    C8CellDefinition,
    C8GraphProjectionAssemblyContext,
    C8GraphProjectionRuntimeBinding,
]


def compose_default_c8_graph_projection_contributions() -> tuple[
    GraphProjectionNativeContribution, ...
]:
    """Return the native list after validating its factory-free projections."""

    return validate_c8_graph_projection_contributions(
        c8_graph_projection_native_contributions
    )


def validate_c8_graph_projection_contributions(
    natives: tuple[GraphProjectionNativeContribution, ...],
) -> tuple[GraphProjectionNativeContribution, ...]:
    composition = compose_contributions(tuple(native.projection for native in natives))
    if isinstance(composition, Failure):
        reject_c8_value(
            "C8 graph projection contribution catalog invalid: "
            f"{composition.message}"
        )
    cell_ids: set[str] = set()
    for native in natives:
        definition = native.definition
        issues = c8_graph_projection_definition_issues(definition)
        if issues:
            reject_c8_value(
                f"native graph definition {definition.cell_id} invalid: "
                + "; ".join(f"{issue.path}: {issue.message}" for issue in issues)
            )
        if definition.cell_id in cell_ids:
            reject_c8_value(
                f"duplicate native graph cell id {definition.cell_id}"
            )
        cell_ids.add(definition.cell_id)
    return natives


def _graph_projection_bindings(
    graph_projection_contributions: tuple[GraphProjectionNativeContribution, ...]
    | None,
) -> tuple[C8GraphProjectionRuntimeBinding, ...]:
    natives = (
        compose_default_c8_graph_projection_contributions()
        if graph_projection_contributions is None
        else validate_c8_graph_projection_contributions(graph_projection_contributions)
    )
    bindings: list[C8GraphProjectionRuntimeBinding] = []
    for native in natives:
        binding = native.assemble(C8GraphProjectionAssemblyContext())
        if isinstance(binding, Failure):
            reject_c8_value(
                f"native graph contribution {native.projection.id} invalid: "
                f"{binding.message}"
            )
        bindings.append(binding)
    return tuple(bindings)


def graph_projection_binding(
    cell_id: str,
    *,
    graph_projection_composition: tuple[GraphProjectionNativeContribution, ...]
    | None = None,
) -> C8GraphProjectionRuntimeBinding:
    """Resolve one assembled graph operation binding by its native cell id."""

    for binding in _graph_projection_bindings(graph_projection_composition):
        if binding.cell_id == cell_id:
            return binding
    reject_c8_value(f"native graph operation binding {cell_id} is not declared")


def graph_projection_definition(
    cell_id: str,
    *,
    graph_projection_composition: tuple[GraphProjectionNativeContribution, ...]
    | None = None,
) -> C8CellDefinition:
    """Read a native definition without assembling a runtime binding."""

    natives = (
        compose_default_c8_graph_projection_contributions()
        if graph_projection_composition is None
        else validate_c8_graph_projection_contributions(graph_projection_composition)
    )
    for native in natives:
        if native.definition.cell_id == cell_id:
            return native.definition
    reject_c8_value(f"native graph operation definition {cell_id} is not declared")


def build_c8_bundle(
    *,
    native_composition: tuple[C8NativeContribution, ...] | None = None,
    graph_projection_composition: tuple[GraphProjectionNativeContribution, ...]
    | None = None,
) -> Annotated[  # NonAuthoritative
    C8CapabilityBundle,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=native_C8_definitions "
        "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands"
    ],
]:
    profiles_by_cell: dict[str, dict[str, object]] = {}
    contracts: list[OperationContract] = []
    codecs: list[PayloadCodec] = []
    for binding in _c8_native_bindings(native_composition):
        profiles_by_cell[binding.cell_id] = dict(binding.profiles)
        for operation in binding.operations:
            contracts.append(operation.operation_contract)
            if operation.payload_codec is not None:
                codecs.append(operation.payload_codec)
    for binding in _graph_projection_bindings(graph_projection_composition):
        profiles_by_cell[binding.cell_id] = dict(binding.profiles)
        contracts.append(binding.operation_contract)
        codecs.append(binding.payload_codec)
    return C8CapabilityBundle(
        bundle_id="mrw.functorial-successor.c8",
        operations=tuple(contracts),
        codecs=tuple(codecs),
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


def build_c8_catalog(bundle: C8CapabilityBundle) -> Annotated[  # NonAuthoritative
    OperationContractCatalogSnapshot,
    Literal["kit:non-authoritative derived_as=view fact_source=C8_contract_and_profile_constants witness=test:test_w06_successor_authority_metadata"],
]:
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


def build_c8_registry(bundle: C8CapabilityBundle) -> Annotated[  # NonAuthoritative
    OperationContractRegistry,
    Literal["kit:non-authoritative derived_as=view fact_source=C8_contract_and_profile_constants witness=test:test_w06_successor_authority_metadata"],
]:
    return OperationContractRegistry(build_c8_catalog(bundle), bundle.operations)


def exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
    *,
    kind: str,
) -> OperationContractRef:
    ref = catalog.lookup(kind)
    if ref is None:
        reject_c8_value(f"contract {kind} missing from catalog {catalog.catalog_id}")
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
        reject_c8_value("payload project scope drift")
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
        reject_c8_value("atom requires a payload value ref")
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
    native_composition: tuple[C8NativeContribution, ...] | None = None,
    graph_projection_composition: tuple[GraphProjectionNativeContribution, ...]
    | None = None,
) -> Annotated[  # NonAuthoritative
    ProgramSpec,
    Literal[
        "kit:non-authoritative derived_as=view "
        "fact_source=payload+native_C8_definition+program_inputs "
        "witness=test:test_w06_successor_authority_metadata"
    ],
]:
    if payload.project_key != project_key:
        reject_c8_value("payload project_key does not match Program project_key")
    extra_metadata: dict[str, object] = {}
    if cell_id in {"C8.1", "C8.2", "C8.3"}:
        native = c8_native_definition(
            cell_id, native_composition=native_composition
        )
        operations = tuple(
            native.operation_by_id[operation_id]
            for operation_id in native.ordered_operation_ids
        )
        if len(operations) == 2:
            compose_operation, stage_operation = operations
            compose_atom_values = compose_operation.program_atom
            stage_atom_values = stage_operation.program_atom
            if compose_atom_values.payload_codec_id is None:
                reject_c8_value("ordered C8 native operation lacks a payload codec")
            handoff_value = payload_value_ref(
                payload,
                program_id=program_id,
                project_key=project_key,
                codec_id=compose_atom_values.payload_codec_id,
                object_type=compose_atom_values.input_type,
                value_suffix=compose_atom_values.value_suffix,
            )
            stage_input = ValueRef(
                value_id=f"{program_id}:payload:{stage_atom_values.value_suffix}",
                project_key=project_key,
                object_type=stage_atom_values.input_type,
                codec_id=compose_atom_values.payload_codec_id,
                content_digest=handoff_value.content_digest,
                storage_kind="project_value_ref",
                store_id="successor_values",
                store_version="1",
                storage_ref=handoff_value.storage_ref,
                byte_size=handoff_value.byte_size,
                provenance_digest=handoff_value.provenance_digest,
            )
            compose_atom = _atom(
                operation_id=compose_atom_values.operation_id,
                contract_ref=exact_contract_ref(
                    catalog, kind=compose_atom_values.operation_kind
                ),
                input_type=compose_atom_values.input_type,
                output_type=compose_atom_values.output_type,
                return_contract_ref=compose_atom_values.return_contract_ref,
                value_ref=handoff_value,
            )
            stage_atom = _atom(
                operation_id=stage_atom_values.operation_id,
                contract_ref=exact_contract_ref(
                    catalog, kind=stage_atom_values.operation_kind
                ),
                input_type=stage_atom_values.input_type,
                output_type=stage_atom_values.output_type,
                return_contract_ref=stage_atom_values.return_contract_ref,
                value_ref=stage_input,
            )
            root = then_node(compose_atom, stage_atom)
            input_type = compose_atom_values.input_type
            output_type = stage_atom_values.output_type
            return_contract_ref = compose_atom_values.return_contract_ref
            operation_kinds = (
                compose_atom_values.operation_kind,
                stage_atom_values.operation_kind,
            )
            payload_value = handoff_value
        else:
            atom_values = operations[0].program_atom
            if atom_values.payload_codec_id is None:
                reject_c8_value("C8 native operation lacks a payload codec")
            value = payload_value_ref(
                payload,
                program_id=program_id,
                project_key=project_key,
                codec_id=atom_values.payload_codec_id,
                object_type=atom_values.input_type,
                value_suffix=atom_values.value_suffix,
            )
            root = _atom(
                operation_id=atom_values.operation_id,
                contract_ref=exact_contract_ref(
                    catalog, kind=atom_values.operation_kind
                ),
                input_type=atom_values.input_type,
                output_type=atom_values.output_type,
                return_contract_ref=atom_values.return_contract_ref,
                value_ref=value,
            )
            input_type = root.input_type
            output_type = root.output_type
            return_contract_ref = atom_values.return_contract_ref
            operation_kinds = (atom_values.operation_kind,)
            payload_value = value
        program_owner = native.owner
        extra_metadata = dict(native.extra_program_metadata)
    else:
        graph_definition = graph_projection_definition(
            cell_id,
            graph_projection_composition=graph_projection_composition,
        )
        atom_wiring = graph_definition.program_atom
        kind = atom_wiring.operation_kind
        ref = exact_contract_ref(catalog, kind=kind)
        value = payload_value_ref(
            payload,
            program_id=program_id,
            project_key=project_key,
            codec_id=atom_wiring.payload_codec_id,
            object_type=atom_wiring.input_type,
            value_suffix=atom_wiring.value_suffix,
        )
        return_contract_ref = atom_wiring.return_contract_ref
        root = _atom(
            operation_id=atom_wiring.operation_id,
            contract_ref=ref,
            input_type=atom_wiring.input_type,
            output_type=atom_wiring.output_type,
            return_contract_ref=return_contract_ref,
            value_ref=value,
        )
        input_type = root.input_type
        output_type = root.output_type
        operation_kinds = (kind,)
        payload_value = value
        program_owner = graph_definition.owner
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
            "canonical_owner": program_owner,
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
            reject_c8_value("ExecutionPlan step is missing an operation contract ref")
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


def build_c8_bridge_bundle() -> Annotated[  # NonAuthoritative
    C8CapabilityBundle,
    Literal["kit:non-authoritative derived_as=view fact_source=C8_contract_and_profile_constants witness=test:test_w06_successor_authority_metadata"],
]:
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
) -> Annotated[  # NonAuthoritative
    ProgramSpec,
    Literal["kit:non-authoritative derived_as=view fact_source=payload+catalog+program_inputs witness=test:test_w06_successor_authority_metadata"],
]:
    if stage_payload.project_key != project_key:
        reject_c8_value("stage payload project_key does not match Program")
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
        reject_c8_projection(
            "delivery operation kind must be delivery.internal_export.v1"
        )
    if delivery_operation.input_type.type_id != C8_DELIVERY_INTENT_TYPE.type_id:
        reject_c8_projection("delivery operation input must be DeliveryIntent.v1")
    if delivery_operation.output_type.type_id != C8_DELIVERY_RECEIPT_TYPE.type_id:
        reject_c8_projection(
            "delivery operation output must be DeliveryReceiptRef.v1"
        )
    if (
        delivery_operation.return_contract_ref
        != DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF
    ):
        reject_c8_projection(
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
            reject_c8_projection(f"delivery operation missing exact {name}")
    if (
        not delivery_operation.ref.contract_digest
        or len(delivery_operation.ref.contract_digest) != 64
    ):
        reject_c8_projection("delivery operation contract digest is not exact")
    return delivery_operation


def validate_delivery_payload_codec(
    delivery_codec: PayloadCodec,
    delivery_operation: OperationContract,
) -> PayloadCodec:
    if delivery_codec.codec_id != "delivery.internal_export.v1.payload":
        reject_c8_projection(
            "delivery codec id must be delivery.internal_export.v1.payload"
        )
    if delivery_codec.payload_type_id != "InternalExportInput.v1":
        reject_c8_projection(
            "delivery codec payload type must be InternalExportInput.v1"
        )
    if delivery_codec.contract_ref != delivery_operation.ref:
        reject_c8_projection(
            "delivery codec contract ref must equal the exact delivery operation"
        )
    return delivery_codec


def build_c8_delivery_bridge_bundle(
    delivery_operation: OperationContract,
    delivery_codec: PayloadCodec,
) -> Annotated[  # NonAuthoritative
    C8CapabilityBundle,
    Literal["kit:non-authoritative derived_as=view fact_source=C8_contract_and_profile_constants witness=test:test_w06_successor_authority_metadata"],
]:
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
) -> Annotated[  # NonAuthoritative
    ProgramSpec,
    Literal["kit:non-authoritative derived_as=view fact_source=payload+catalog+program_inputs witness=test:test_w06_successor_authority_metadata"],
]:
    validate_delivery_operation_contract(delivery_operation)
    validate_delivery_payload_codec(delivery_codec, delivery_operation)
    if delivery_payload_ref.object_type.type_id != "InternalExportInput.v1":
        reject_c8_projection(
            "delivery payload ref object type must be InternalExportInput.v1"
        )
    if delivery_payload_ref.codec_id != delivery_codec.codec_id:
        reject_c8_projection(
            "delivery payload ref codec must equal the delivery codec"
        )
    if artifact_input_ref.object_type != C8_RESEARCH_ARTIFACT_TYPE:
        reject_c8_projection(
            "artifact input ref object type must be ResearchArtifact.v1"
        )
    if artifact_input_ref.codec_id != CANONICAL_CODEC_ID:
        reject_c8_projection("artifact input ref must use the canonical JSON codec")
    if intent_input_ref.object_type != C8_DELIVERY_INTENT_TYPE:
        reject_c8_projection(
            "intent input ref object type must be DeliveryIntent.v1"
        )
    if intent_input_ref.codec_id != CANONICAL_CODEC_ID:
        reject_c8_projection("intent input ref must use the canonical JSON codec")
    refs = (
        delivery_payload_ref,
        artifact_input_ref,
        intent_input_ref,
    )
    storage_refs = [ref.storage_ref for ref in refs]
    if len(set(storage_refs)) != len(storage_refs):
        reject_c8_projection("delivery bridge refs must not share storage_ref")
    value_ids = [ref.value_id for ref in refs]
    if len(set(value_ids)) != len(value_ids):
        reject_c8_projection(
            "delivery bridge refs must have distinct value identities"
        )
    if stage_payload.project_key != project_key:
        reject_c8_value("stage payload project_key does not match Program")
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
