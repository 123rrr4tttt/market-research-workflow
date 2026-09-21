"""Native C8 graph-projection definitions and mechanical realizations.

One ``C8CellDefinition`` owns the operation, codec, profiles, projector
identity, cell declaration, rollback declaration and Program atom wiring.
Catalog projection is factory-free; explicit native assembly creates and
validates the runtime binding.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated, Any, Literal

from app.successor_runtime.capabilities.c8_common import reject_c8_projection, reject_c8_value
from app.successor_runtime.capabilities.c8_graph import GRAPH_CONTEXT_PROJECTION, GRAPH_PROJECTION_SCHEMA
from app.successor_runtime.capabilities.checksum import content_digest, require_hex64
from app.successor_runtime.capabilities.codecs import PayloadCodec, dataclass_codec
from app.successor_runtime.language.object_contracts import (
    READ_CANONICAL_REF_RETURN_CONTRACT_REF,
    OperationContract,
    make_operation_contract,
)
from app.successor_runtime.language.profiles import (
    AuthorityProfile,
    EffectProfile,
    FailureProfile,
    InterpreterProfile,
    ObservationProfile,
    ResourceProfile,
    SemanticProfile,
)
from app.successor_runtime.research.object_types import ObjectType
from functorial_kit.contributions import ContributionObject, contribution_failures
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    ProjectedContributionSpec,
)
from mrw_functorial_kit.core.c8_semantics import c8_graph_failures, c8_operation_kinds

__all__ = [
    "C8_4_CELL_ID",
    "C8_4_DECLARED_LOSS",
    "C8_4_FAILURE_CODES",
    "C8_4_INPUT_TYPE",
    "C8_4_KIND",
    "C8_4_OPERATION_ID",
    "C8_4_OWNER",
    "C8_4_PAYLOAD_CODEC_ID",
    "C8_4_RESULT_TYPE",
    "C8_4_RETURN_CONTRACT_REF",
    "C8_4_ROLLBACK_REF",
    "C8_FAMILY_ID",
    "C8CellDefinition",
    "C8GraphProjectInput",
    "C8GraphProjectionAssemblyContext",
    "C8GraphProjectionDefinition",
    "C8GraphProjectionOperationDefinition",
    "C8GraphProjectionRollback",
    "C8GraphProjectionRuntimeBinding",
    "C8GraphProjectionWiring",
    "C8ProgramAtomWiring",
    "C8_GRAPH_PROJECTION_DEFINITION",
    "C8_GRAPH_PROJECTOR_ID",
    "C8_GRAPH_PROJECTOR_VERSION",
    "C8_GRAPH_SOURCE_KIND",
    "C8_GRAPH_VALUE_SCHEMA",
    "assemble_c8_graph_projection_definition",
    "build_c8_graph_projection_binding",
    "c8_graph_projection_definition_issues",
    "define_c8_graph_projection_cell",
    "project_c8_graph_projection_definition",
    "validate_c8_graph_projection_binding",
]

C8_FAMILY_ID = "C8"
C8_4_CELL_ID = "C8.4"
C8_4_OWNER = "graph.c8.4.v1"
C8_4_OPERATION_ID = "c8.graph.project"
C8_4_KIND = "c8.graph.project.v1"
C8_4_PAYLOAD_CODEC_ID = "mrw.successor.c8.c8-4.payload.codec.v1"
C8_4_INPUT_TYPE = ObjectType("C8GraphProjectInput.v1")
C8_4_RESULT_TYPE = ObjectType("C8GraphContext.v1")
C8_4_RETURN_CONTRACT_REF = READ_CANONICAL_REF_RETURN_CONTRACT_REF
C8_4_FAILURE_CODES = c8_graph_failures.codes
C8_4_ROLLBACK_REF = "main/backend/app/successor_migration/legacy_c8_graph.py"

# The PostgreSQL projector, FamilyAssembly and catalog projection all import
# these four projector identities from this one native declaration module.
C8_GRAPH_PROJECTOR_ID = "c8.graph.projector"
C8_GRAPH_PROJECTOR_VERSION = "1"
C8_GRAPH_SOURCE_KIND = "successor_value"
C8_GRAPH_VALUE_SCHEMA = "mrw.successor.c8.graph-projection.v1"
C8_4_DECLARED_LOSS = (
    "c8.graph.node-edge-filtering.v1",
    "c8.graph.text-truncation.v1",
    "c8.graph.redaction.v1",
    "c8.graph.casefold-and-duplicate-collapse.v1",
    "c8.graph.omitted-fields.v1",
)


def _payload_body_digest(payload: Any) -> str:
    return content_digest(
        {name: value for name, value in dataclasses.asdict(payload).items() if name != "payload_digest"}
    )


@dataclass(frozen=True, slots=True)
class C8GraphProjectInput:
    project_key: str
    graph_id: str
    node_keys: tuple[str, ...]
    node_types: tuple[str, ...]
    payload_digest: str = ""

    def __post_init__(self) -> None:
        expected = _payload_body_digest(self)
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
            return
        require_hex64(self.payload_digest, "C8GraphProjectInput.payload_digest")
        if self.payload_digest != expected:
            reject_c8_value("C8GraphProjectInput.payload_digest does not match recomputed body digest")


@dataclass(frozen=True, slots=True)
class C8GraphProjectionWiring:
    projector_id: str
    projector_version: str
    source_kind: str
    projection_id: str
    projection_schema_ref: str
    declared_loss: tuple[str, ...]
    note: str


@dataclass(frozen=True, slots=True)
class C8GraphProjectionRollback:
    binding_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class C8ProgramAtomWiring:
    operation_id: str
    operation_kind: str
    payload_codec_id: str
    input_type: ObjectType
    output_type: ObjectType
    return_contract_ref: str
    value_suffix: str


@dataclass(frozen=True, slots=True)
class C8CellDefinition:
    """Complete native meaning of one graph-projection cell."""

    family_id: str
    contribution_id: str
    cell_id: str
    owner: str
    operation_id: str
    kind: str
    input_type: ObjectType
    output_type: ObjectType
    return_contract_ref: str
    payload_type: type
    payload_codec: PayloadCodec
    profiles: Mapping[str, object]
    operation_contract: OperationContract
    program_atom: C8ProgramAtomWiring
    failure_codes: tuple[str, ...]
    projector_wiring: C8GraphProjectionWiring | None
    rollback_binding: C8GraphProjectionRollback

    @property
    def payload_codec_id(self) -> str:
        return self.payload_codec.codec_id

    @property
    def payload_codec_version(self) -> str:
        return self.payload_codec.codec_version

    @property
    def rollback_ref(self) -> str:
        return self.rollback_binding.binding_refs[0]

    def contribution_objects(self) -> tuple[ContributionObject, ...]:
        return (
            ContributionObject(self.input_type.type_id, "ObjectType", self.owner),
            ContributionObject(
                self.output_type.type_id,
                "ObjectType",
                self.owner,
                references=(self.input_type.type_id,),
            ),
            ContributionObject(
                self.operation_id,
                "Capability",
                self.owner,
                references=(self.input_type.type_id, self.output_type.type_id),
            ),
            ContributionObject(
                self.payload_codec.codec_id,
                "PayloadCodec",
                self.owner,
                references=(self.operation_id, self.input_type.type_id),
            ),
        )


C8GraphProjectionDefinition = C8CellDefinition
C8GraphProjectionOperationDefinition = C8CellDefinition


def _profile_ref(profile: Any) -> str:
    return f"{profile.profile_id}@{profile.profile_version}"


def _profiles(
    *,
    cell_id: str,
    owner: str,
    kind: str,
    input_type: ObjectType,
    output_type: ObjectType,
    failure_codes: tuple[str, ...],
) -> Mapping[str, object]:
    suffix = cell_id.lower().replace(".", "-")
    semantic_values = {
        "semantic_profile_id": f"c8.{suffix}.semantic",
        "semantic_profile_version": "1.0.0",
        "reads": (input_type.type_id,),
        "creates": (output_type.type_id,),
        "creates_relations": (),
        "declared_loss": ("graph_node_filter", "report_export_body"),
        "observation_profile_ref": f"mrw.successor.c8.{suffix}.observation.v1",
    }
    effect_values = {
        "effect_profile_id": f"c8.{suffix}.effect",
        "effect_profile_version": "1.0.0",
        "execution_class": "PROJECTION",
        "external_visibility": "NONE",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": (),
        "internal_export_only": False,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": f"mrw.successor.c8.{suffix}.idempotency.v1",
    }
    resource_values = {
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
    failure_values = {
        "failure_profile_id": f"c8.{suffix}.failure",
        "failure_profile_version": "1.0.0",
        "typed_failures": failure_codes,
        "retryable": False,
        "degraded_acceptable": False,
        "unknown_outcome_supported": True,
        "readback_or_compensation": "readback",
        "failure_union_ref": f"mrw.functorial-successor.failures.c8-{suffix}.v1",
        "retryable_failure_kinds": (),
        "readback_profile_ref": "c8.graph.readback.v1",
        "compensation_profile_ref": None,
    }
    authority_values = {
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
    interpreter_values = {
        "interpreter_profile_id": f"successor.c8.{suffix}.v1",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": (kind,),
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
    observation_values = {
        "observation_profile_id": f"mrw.successor.c8.{suffix}.observation.v1",
        "observation_profile_version": "1.0.0",
        "dimensions": ("declared_loss", "provenance_closure", "canonical_identity"),
        "compatible_with_legacy": True,
        "observation_schema_ref": f"mrw.successor.c8.{suffix}.observation.v1",
    }
    return MappingProxyType(
        {
            "semantic": SemanticProfile(**semantic_values, profile_digest=content_digest(semantic_values)),
            "effect": EffectProfile(**effect_values, profile_digest=content_digest(effect_values)),
            "resource": ResourceProfile(**resource_values, profile_digest=content_digest(resource_values)),
            "failure": FailureProfile(**failure_values, profile_digest=content_digest(failure_values)),
            "authority": AuthorityProfile(**authority_values, profile_digest=content_digest(authority_values)),
            "interpreter": InterpreterProfile(**interpreter_values, profile_digest=content_digest(interpreter_values)),
            "observation": ObservationProfile(**observation_values, profile_digest=content_digest(observation_values)),
        }
    )


def define_c8_graph_projection_cell(
    *,
    cell_id: str,
    contribution_id: str | None = None,
    owner: str,
    operation_id: str,
    kind: str,
    payload_codec_id: str,
    input_type: ObjectType,
    output_type: ObjectType,
    payload_type: type,
    projector_wiring: C8GraphProjectionWiring | None,
    rollback_refs: tuple[str, ...],
    failure_codes: tuple[str, ...] = C8_4_FAILURE_CODES,
    return_contract_ref: str = C8_4_RETURN_CONTRACT_REF,
) -> C8CellDefinition:
    profiles = _profiles(
        cell_id=cell_id,
        owner=owner,
        kind=kind,
        input_type=input_type,
        output_type=output_type,
        failure_codes=failure_codes,
    )
    operation = make_operation_contract(
        kind=kind,
        contract_version="1.0.0",
        input_type=input_type,
        output_type=output_type,
        return_contract_ref=return_contract_ref,
        semantic_profile_ref=_profile_ref(profiles["semantic"]),
        effect_profile_ref=_profile_ref(profiles["effect"]),
        resource_profile_ref=_profile_ref(profiles["resource"]),
        failure_profile_ref=_profile_ref(profiles["failure"]),
        authority_profile_ref=_profile_ref(profiles["authority"]),
        interpreter_compatibility_ref=_profile_ref(profiles["interpreter"]),
        observation_profile_ref=_profile_ref(profiles["observation"]),
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=owner,
    )
    codec = dataclass_codec(
        codec_id=payload_codec_id,
        codec_version="1",
        contract_ref=operation.ref,
        payload_type_id=input_type.type_id,
        dto_cls=payload_type,
    )
    atom = C8ProgramAtomWiring(
        operation_id=operation_id,
        operation_kind=kind,
        payload_codec_id=payload_codec_id,
        input_type=input_type,
        output_type=output_type,
        return_contract_ref=return_contract_ref,
        value_suffix=cell_id.lower().replace(".", "-"),
    )
    return C8CellDefinition(
        family_id=C8_FAMILY_ID,
        contribution_id=(
            contribution_id if contribution_id is not None else f"mrw.successor.{cell_id.lower()}.graph-projection.v1"
        ),
        cell_id=cell_id,
        owner=owner,
        operation_id=operation_id,
        kind=kind,
        input_type=input_type,
        output_type=output_type,
        return_contract_ref=return_contract_ref,
        payload_type=payload_type,
        payload_codec=codec,
        profiles=profiles,
        operation_contract=operation,
        program_atom=atom,
        failure_codes=failure_codes,
        projector_wiring=projector_wiring,
        rollback_binding=C8GraphProjectionRollback(rollback_refs),
    )


C8_GRAPH_PROJECTION_DEFINITION = define_c8_graph_projection_cell(
    cell_id=C8_4_CELL_ID,
    contribution_id="mrw.successor.c8.graph-projection.v1",
    owner=C8_4_OWNER,
    operation_id=C8_4_OPERATION_ID,
    kind=C8_4_KIND,
    payload_codec_id=C8_4_PAYLOAD_CODEC_ID,
    input_type=C8_4_INPUT_TYPE,
    output_type=C8_4_RESULT_TYPE,
    payload_type=C8GraphProjectInput,
    projector_wiring=C8GraphProjectionWiring(
        projector_id=C8_GRAPH_PROJECTOR_ID,
        projector_version=C8_GRAPH_PROJECTOR_VERSION,
        source_kind=C8_GRAPH_SOURCE_KIND,
        projection_id=GRAPH_CONTEXT_PROJECTION,
        projection_schema_ref=C8_GRAPH_VALUE_SCHEMA,
        declared_loss=C8_4_DECLARED_LOSS,
        note=(f"capability schema: {GRAPH_PROJECTION_SCHEMA}; exact per-run source key is supplied by the runner"),
    ),
    rollback_refs=(C8_4_ROLLBACK_REF,),
)


def project_c8_graph_projection_definition(
    definition: C8CellDefinition,
) -> ProjectedContributionSpec | Failure:
    issues = c8_graph_projection_definition_issues(definition)
    if issues:
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "native C8 graph projection definition is invalid",
            {
                "issues": tuple(
                    {
                        "code": "invalid_spec",
                        "path": issue.path,
                        "message": issue.message,
                    }
                    for issue in issues
                )
            },
        )
    return ProjectedContributionSpec(
        id=definition.contribution_id,
        owner=definition.owner,
        objects=definition.contribution_objects(),
        vocabularies=(c8_operation_kinds,),
        failures=(c8_graph_failures,),
    )


@dataclass(frozen=True, slots=True)
class C8GraphProjectionAssemblyContext:
    """Pure assembly boundary; run-specific source keys bind later."""


@dataclass(frozen=True, slots=True)
class C8GraphProjectionRuntimeBinding:
    definition: C8CellDefinition
    cell_id: str
    operation_contract: OperationContract
    payload_codec: PayloadCodec
    profiles: Mapping[str, object]
    projector_wiring: C8GraphProjectionWiring | None
    rollback_binding: C8GraphProjectionRollback

    def assembly_projector_wiring(self) -> Any:
        from app.successor_runtime.assembly.base import ProjectorWiring

        assert self.projector_wiring is not None
        return ProjectorWiring(
            cell_id=self.cell_id,
            projector_id=self.projector_wiring.projector_id,
            projector_version=self.projector_wiring.projector_version,
            source_kind=self.projector_wiring.source_kind,
            projection_id=self.projector_wiring.projection_id,
            projection_schema_ref=self.projector_wiring.projection_schema_ref,
            declared_loss=self.projector_wiring.declared_loss,
            note=self.projector_wiring.note,
        )

    def assembly_rollback_binding(self) -> Any:
        from app.successor_runtime.assembly.base import RollbackBindingDeclaration

        return RollbackBindingDeclaration(
            cell_id=self.cell_id,
            status="PRESENT",
            binding_refs=self.rollback_binding.binding_refs,
        )

    def unbound_cell(self) -> Any:
        from app.successor_runtime.assembly.base import CellBinding

        return CellBinding(
            cell_id=self.cell_id,
            family_id=self.definition.family_id,
            status="PROJECTOR_WIRING_DECLARED",
            operation_contract_refs=(self.operation_contract.ref.kind,),
            recovery_binding_ref=(
                "c8.graph.recovery.v1#offset-cas-keeps-old-active-generation;rebuild-from-source-closure"
            ),
            required_wiring=(f"{self.cell_id} RuntimeHandler/注册", "declared-loss projection 记账"),
            note=(
                "缺 per-run source_ref/source_incarnation 与 ProjectorRegistry "
                "注册；no PostgreSQL write adopted（authority 关闭）"
            ),
        )

    def install(self, source_key: Any) -> tuple[Any, Any] | None:
        from app.successor_runtime.assembly.base import (
            PROJECTOR_REGISTRY_INCARNATION,
            CellBinding,
            ProjectorRegistry,
            validate_projector_contract,
        )

        if self.projector_wiring is None:
            return None
        wiring = self.assembly_projector_wiring()
        contract = wiring.to_contract(source_key)
        validation = validate_projector_contract(contract)
        if not validation.valid:
            reject_c8_projection(
                f"{self.cell_id} projector contract invalid: "
                + "; ".join(item.message for item in validation.violations)
            )
        return (
            CellBinding(
                cell_id=self.cell_id,
                family_id=self.definition.family_id,
                status="INSTALLED",
                operation_contract_refs=(self.operation_contract.ref.kind,),
                handler_binding_digest=wiring.registration_digest(contract),
                recovery_binding_ref=(
                    "c8.graph.recovery.v1#offset-cas-keeps-old-active-generation;rebuild-from-source-closure"
                ),
                note=(
                    "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED: "
                    "per-run source_ref/source_incarnation bound；no PostgreSQL "
                    "write adopted"
                ),
            ),
            ProjectorRegistry(
                revision=0,
                incarnation=PROJECTOR_REGISTRY_INCARNATION,
                projectors=(contract,),
            ),
        )


def assemble_c8_graph_projection_definition(
    definition: C8CellDefinition,
    context: C8GraphProjectionAssemblyContext,
) -> C8GraphProjectionRuntimeBinding:
    del context
    return C8GraphProjectionRuntimeBinding(
        definition=definition,
        cell_id=definition.cell_id,
        operation_contract=definition.operation_contract,
        payload_codec=definition.payload_codec,
        profiles=definition.profiles,
        projector_wiring=definition.projector_wiring,
        rollback_binding=definition.rollback_binding,
    )


def validate_c8_graph_projection_binding(
    definition: C8CellDefinition,
    candidate: object,
) -> BindingAccepted[C8GraphProjectionRuntimeBinding] | BindingRejected:
    if not isinstance(candidate, C8GraphProjectionRuntimeBinding):
        return BindingRejected((NativeBindingIssue("$.binding", "expected C8GraphProjectionRuntimeBinding"),))
    definition_issues = c8_graph_projection_definition_issues(definition)
    checks = (
        (candidate.definition == definition, "$.binding.definition", "definition drift"),
        (candidate.cell_id == definition.cell_id, "$.binding.cell_id", "cell id drift"),
        (
            candidate.operation_contract == definition.operation_contract,
            "$.binding.operation_contract",
            "operation contract drift",
        ),
        (
            candidate.operation_contract.ref.kind == definition.program_atom.operation_kind,
            "$.binding.operation_contract.ref.kind",
            "program atom kind drift",
        ),
        (
            candidate.operation_contract.input_type == definition.input_type,
            "$.binding.operation_contract.input_type",
            "input type drift",
        ),
        (
            candidate.operation_contract.output_type == definition.output_type,
            "$.binding.operation_contract.output_type",
            "output type drift",
        ),
        (
            candidate.operation_contract.owner_capability_id == definition.owner,
            "$.binding.operation_contract.owner_capability_id",
            "owner drift",
        ),
        (candidate.payload_codec == definition.payload_codec, "$.binding.payload_codec", "payload codec drift"),
        (dict(candidate.profiles) == dict(definition.profiles), "$.binding.profiles", "profile drift"),
        (
            candidate.projector_wiring == definition.projector_wiring,
            "$.binding.projector_wiring",
            "projector identity drift",
        ),
        (candidate.rollback_binding == definition.rollback_binding, "$.binding.rollback_binding", "rollback drift"),
    )
    issues = definition_issues + tuple(
        NativeBindingIssue(path, message) for valid, path, message in checks if not valid
    )
    return BindingRejected(issues) if issues else BindingAccepted(candidate)


def c8_graph_projection_definition_issues(
    definition: C8CellDefinition,
) -> tuple[NativeBindingIssue, ...]:
    """Check equations internal to one authoritative native definition."""

    atom = definition.program_atom
    operation = definition.operation_contract
    codec = definition.payload_codec
    semantic = definition.profiles.get("semantic")
    authority = definition.profiles.get("authority")
    interpreter = definition.profiles.get("interpreter")
    failure = definition.profiles.get("failure")
    checks = (
        (bool(definition.contribution_id), "$.definition.contribution_id", "contribution id is empty"),
        (operation.ref.kind == definition.kind, "$.definition.operation_contract.ref.kind", "operation kind drift"),
        (
            operation.input_type == definition.input_type,
            "$.definition.operation_contract.input_type",
            "operation input type drift",
        ),
        (
            operation.output_type == definition.output_type,
            "$.definition.operation_contract.output_type",
            "operation output type drift",
        ),
        (
            operation.return_contract_ref == definition.return_contract_ref,
            "$.definition.operation_contract.return_contract_ref",
            "return contract drift",
        ),
        (
            operation.owner_capability_id == definition.owner,
            "$.definition.operation_contract.owner_capability_id",
            "operation owner drift",
        ),
        (codec.contract_ref == operation.ref, "$.definition.payload_codec.contract_ref", "codec contract drift"),
        (
            codec.payload_type_id == definition.input_type.type_id,
            "$.definition.payload_codec.payload_type_id",
            "codec payload type drift",
        ),
        (
            isinstance(definition.payload_type, type),
            "$.definition.payload_type",
            "codec payload type must be a type",
        ),
        (
            atom.operation_id == definition.operation_id,
            "$.definition.program_atom.operation_id",
            "atom operation id drift",
        ),
        (atom.operation_kind == definition.kind, "$.definition.program_atom.operation_kind", "atom kind drift"),
        (atom.payload_codec_id == codec.codec_id, "$.definition.program_atom.payload_codec_id", "atom codec drift"),
        (atom.input_type == definition.input_type, "$.definition.program_atom.input_type", "atom input type drift"),
        (atom.output_type == definition.output_type, "$.definition.program_atom.output_type", "atom output type drift"),
        (
            atom.return_contract_ref == definition.return_contract_ref,
            "$.definition.program_atom.return_contract_ref",
            "atom return contract drift",
        ),
        (
            semantic is not None
            and tuple(semantic.reads) == (definition.input_type.type_id,)
            and tuple(semantic.creates) == (definition.output_type.type_id,),
            "$.definition.profiles.semantic",
            "semantic types drift",
        ),
        (
            authority is not None and authority.canonical_owner == definition.owner,
            "$.definition.profiles.authority",
            "authority owner drift",
        ),
        (
            interpreter is not None and tuple(interpreter.supported_contract_kinds) == (definition.kind,),
            "$.definition.profiles.interpreter",
            "interpreter kind drift",
        ),
        (
            failure is not None and tuple(failure.typed_failures) == definition.failure_codes,
            "$.definition.profiles.failure",
            "failure codes drift",
        ),
        (bool(definition.rollback_binding.binding_refs), "$.definition.rollback_binding", "rollback binding is empty"),
    )
    return tuple(NativeBindingIssue(path, message) for valid, path, message in checks if not valid)


def build_c8_graph_projection_binding(
    context: C8GraphProjectionAssemblyContext | None = None,
) -> Annotated[
    C8GraphProjectionRuntimeBinding,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=C8CellDefinition "
        "witness=test:test_default_and_installed_c8_4_assembly_preserve_exact_declarations"
    ],
]:
    binding = assemble_c8_graph_projection_definition(
        C8_GRAPH_PROJECTION_DEFINITION,
        context or C8GraphProjectionAssemblyContext(),
    )
    decision = validate_c8_graph_projection_binding(C8_GRAPH_PROJECTION_DEFINITION, binding)
    if isinstance(decision, BindingRejected):
        reject_c8_projection("; ".join(f"{issue.path}: {issue.message}" for issue in decision.issues))
    return binding
