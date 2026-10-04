"""Native C8 graph-projection definitions and mechanical realizations.
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

from app.successor_runtime.capabilities.knowledge_common import (
    KNOWLEDGE_GRAPH_PROJECTION_CELL_ID,
    reject_knowledge_contract,
    reject_knowledge_projection,
    reject_knowledge_value,
    GRAPH_CONTEXT_PROJECTION,
    GRAPH_PROJECTION_SCHEMA,
)
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
from dataclasses import replace
from functorial_kit.contribution_compiler import NativeContributionRule, compile_native_contribution
from functorial_kit.contribution_verification import (
    ContributionVerification,
    VerificationCheck,
)
from functorial_kit.law_witness import define_law_witness
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    NativeContribution,
    ProjectedContributionSpec,
)
from mrw_functorial_kit.core.knowledge_semantics import knowledge_graph_failures, knowledge_operation_kinds

__all__ = [
    "KNOWLEDGE_GRAPH_PROJECTION_CELL_ID",
    "KNOWLEDGE_GRAPH_PROJECTION_DECLARED_LOSS",
    "KNOWLEDGE_GRAPH_PROJECTION_FAILURE_CODES",
    "KNOWLEDGE_GRAPH_PROJECTION_INPUT_TYPE",
    "KNOWLEDGE_GRAPH_PROJECTION_KIND",
    "KNOWLEDGE_GRAPH_PROJECTION_OPERATION_ID",
    "KNOWLEDGE_GRAPH_PROJECTION_OWNER",
    "KNOWLEDGE_GRAPH_PROJECTION_PAYLOAD_CODEC_ID",
    "KNOWLEDGE_GRAPH_PROJECTION_RESULT_TYPE",
    "KNOWLEDGE_GRAPH_PROJECTION_RETURN_CONTRACT_REF",
    "KNOWLEDGE_GRAPH_PROJECTION_ROLLBACK_REF",
    "KNOWLEDGE_FAMILY_ID",
    "KnowledgeCellDefinition",
    "KnowledgeGraphProjectInput",
    "KnowledgeGraphProjectionAssemblyContext",
    "KnowledgeGraphProjectionAuthorSource",
    "KnowledgeGraphProjectionDefinition",
    "KnowledgeGraphProjectionOperationDefinition",
    "KnowledgeGraphProjectionRollback",
    "KnowledgeGraphProjectionRuntimeBinding",
    "KnowledgeGraphProjectionWiring",
    "KnowledgeProgramAtomWiring",
    "KNOWLEDGE_GRAPH_PROJECTION_AUTHOR_SOURCE",
    "KNOWLEDGE_GRAPH_PROJECTION_DEFINITION",
    "KNOWLEDGE_GRAPH_PROJECTION_NATIVE_RULE",
    "KNOWLEDGE_GRAPH_PROJECTOR_ID",
    "KNOWLEDGE_GRAPH_PROJECTOR_VERSION",
    "KNOWLEDGE_GRAPH_SOURCE_KIND",
    "KNOWLEDGE_GRAPH_VALUE_SCHEMA",
    "assemble_knowledge_graph_projection_definition",
    "build_knowledge_graph_projection_binding",
    "knowledge_graph_projection_native_contribution",
    "knowledge_graph_projection_definition_issues",
    "KNOWLEDGE_GRAPH_PROJECTION_RULE_ID",
    "KNOWLEDGE_GRAPH_PROJECTION_VERIFICATION_INPUTS",
    "verify_knowledge_graph_projection_definition",
    "define_knowledge_graph_projection_cell",
    "lower_knowledge_graph_projection_author_source",
    "project_knowledge_graph_projection_definition",
    "validate_knowledge_graph_projection_binding",
]

KNOWLEDGE_FAMILY_ID = "mrw.knowledge"
KNOWLEDGE_GRAPH_PROJECTION_OWNER = "knowledge.graph-projection.v2"
KNOWLEDGE_GRAPH_PROJECTION_OPERATION_ID = "knowledge.graph.project"
KNOWLEDGE_GRAPH_PROJECTION_KIND = "knowledge.graph.project.v2"
KNOWLEDGE_GRAPH_PROJECTION_PAYLOAD_CODEC_ID = "mrw.knowledge.graph-project.codec.v2"
KNOWLEDGE_GRAPH_PROJECTION_INPUT_TYPE = ObjectType("KnowledgeGraphProjectInput.v2")
KNOWLEDGE_GRAPH_PROJECTION_RESULT_TYPE = ObjectType("KnowledgeGraphContext.v2")
KNOWLEDGE_GRAPH_PROJECTION_RETURN_CONTRACT_REF = READ_CANONICAL_REF_RETURN_CONTRACT_REF
KNOWLEDGE_GRAPH_PROJECTION_FAILURE_CODES = knowledge_graph_failures.codes
KNOWLEDGE_GRAPH_PROJECTION_ROLLBACK_REF = "main/backend/app/successor_migration/legacy_c8_graph.py"

# The PostgreSQL projector, FamilyAssembly and catalog projection all import
# these four projector identities from this one native declaration module.
KNOWLEDGE_GRAPH_PROJECTOR_ID = "knowledge.graph.projector"
KNOWLEDGE_GRAPH_PROJECTOR_VERSION = "1"
KNOWLEDGE_GRAPH_SOURCE_KIND = "knowledge_value"
KNOWLEDGE_GRAPH_VALUE_SCHEMA = "mrw.knowledge.graph-projection.v2"
KNOWLEDGE_GRAPH_PROJECTION_DECLARED_LOSS = (
    "knowledge.graph.node-edge-filtering.v2",
    "knowledge.graph.text-truncation.v2",
    "knowledge.graph.redaction.v2",
    "knowledge.graph.casefold-and-duplicate-collapse.v2",
    "knowledge.graph.omitted-fields.v2",
)


def _payload_body_digest(payload: Any) -> str:
    return content_digest(
        {name: value for name, value in dataclasses.asdict(payload).items() if name != "payload_digest"}
    )


@dataclass(frozen=True, slots=True)
class KnowledgeGraphProjectInput:
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
            reject_knowledge_value("C8GraphProjectInput.payload_digest does not match recomputed body digest")


@dataclass(frozen=True, slots=True)
class KnowledgeGraphProjectionWiring:
    projector_id: str
    projector_version: str
    source_kind: str
    projection_id: str
    projection_schema_ref: str
    declared_loss: tuple[str, ...]
    note: str


@dataclass(frozen=True, slots=True)
class KnowledgeGraphProjectionRollback:
    binding_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeProgramAtomWiring:
    operation_id: str
    operation_kind: str
    payload_codec_id: str
    input_type: ObjectType
    output_type: ObjectType
    return_contract_ref: str
    value_suffix: str


@dataclass(frozen=True, slots=True)
class KnowledgeGraphProjectionAuthorSource:
    """Immutable native author facts lowered into one C8 graph cell definition."""

    cell_id: str
    owner: str
    operation_id: str
    kind: str
    payload_codec_id: str
    input_type: ObjectType
    output_type: ObjectType
    payload_type: type
    projector_wiring: KnowledgeGraphProjectionWiring | None
    rollback_refs: tuple[str, ...]
    failure_codes: tuple[str, ...] = KNOWLEDGE_GRAPH_PROJECTION_FAILURE_CODES
    return_contract_ref: str = KNOWLEDGE_GRAPH_PROJECTION_RETURN_CONTRACT_REF
    contribution_id: str | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeCellDefinition:
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
    program_atom: KnowledgeProgramAtomWiring
    failure_codes: tuple[str, ...]
    projector_wiring: KnowledgeGraphProjectionWiring | None
    rollback_binding: KnowledgeGraphProjectionRollback

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


KnowledgeGraphProjectionDefinition = KnowledgeCellDefinition
KnowledgeGraphProjectionOperationDefinition = KnowledgeCellDefinition


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
    namespace = owner.removesuffix(".v2")
    semantic_values = {
        "semantic_profile_id": f"{namespace}.semantic",
        "semantic_profile_version": "1.0.0",
        "reads": (input_type.type_id,),
        "creates": (output_type.type_id,),
        "creates_relations": (),
        "declared_loss": ("graph_node_filter", "report_export_body"),
        "observation_profile_ref": f"mrw.{namespace}.observation.v2",
    }
    effect_values = {
        "effect_profile_id": f"{namespace}.effect",
        "effect_profile_version": "1.0.0",
        "execution_class": "PROJECTION",
        "external_visibility": "NONE",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": (),
        "internal_export_only": False,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": f"mrw.{namespace}.idempotency.v2",
    }
    resource_values = {
        "resource_profile_id": f"{namespace}.resource",
        "resource_profile_version": "1.0.0",
        "resource_classes": ("CPU_LIGHT",),
        "concurrency_key": namespace,
        "budget_units": "units",
        "default_soft_limit_seconds": 5,
        "default_hard_limit_seconds": 30,
        "node_profile_selector": "any",
        "budget_ref": f"mrw.{namespace}.budget.v2",
        "deadline_policy_ref": f"mrw.{namespace}.deadline.v2",
        "node_profile_requirements": ("any",),
        "units": 1,
    }
    failure_values = {
        "failure_profile_id": f"{namespace}.failure",
        "failure_profile_version": "1.0.0",
        "typed_failures": failure_codes,
        "retryable": False,
        "degraded_acceptable": False,
        "unknown_outcome_supported": True,
        "readback_or_compensation": "readback",
        "failure_union_ref": f"mrw.{namespace}.failures.v2",
        "retryable_failure_kinds": (),
        "readback_profile_ref": "knowledge.graph.readback.v2",
        "compensation_profile_ref": None,
    }
    authority_values = {
        "authority_profile_id": f"{namespace}.authority",
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
        "interpreter_profile_id": f"{namespace}.native.v2",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": (kind,),
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "interpreter": f"{namespace}.native",
                "version": "2.0.0",
                "boundary": "pure typed knowledge consumer; historical writers are excluded",
            }
        ),
        "security_profile_ref": "mrw.knowledge.security.pure.v2",
        "resource_profile_ref": f"{namespace}.resource@1.0.0",
        "credential_requirements_ref": None,
        "cancellation_profile_ref": "step_boundary",
        "idempotency_profile_ref": "logical_request_id",
        "authoritative_readback_profile_ref": None,
        "receipt_codec_ref": f"mrw.{namespace}.observation.v2",
    }
    observation_values = {
        "observation_profile_id": f"mrw.{namespace}.observation.v2",
        "observation_profile_version": "1.0.0",
        "dimensions": ("declared_loss", "provenance_closure", "canonical_identity"),
        "compatible_with_legacy": True,
        "observation_schema_ref": f"mrw.{namespace}.observation.v2",
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


def lower_knowledge_graph_projection_author_source(
    source: KnowledgeGraphProjectionAuthorSource,
) -> KnowledgeCellDefinition:
    """Lower native author facts into profiles, contract, codec, and Program atom."""

    profiles = _profiles(
        cell_id=source.cell_id,
        owner=source.owner,
        kind=source.kind,
        input_type=source.input_type,
        output_type=source.output_type,
        failure_codes=source.failure_codes,
    )
    operation = make_operation_contract(
        kind=source.kind,
        contract_version="1.0.0",
        input_type=source.input_type,
        output_type=source.output_type,
        return_contract_ref=source.return_contract_ref,
        semantic_profile_ref=_profile_ref(profiles["semantic"]),
        effect_profile_ref=_profile_ref(profiles["effect"]),
        resource_profile_ref=_profile_ref(profiles["resource"]),
        failure_profile_ref=_profile_ref(profiles["failure"]),
        authority_profile_ref=_profile_ref(profiles["authority"]),
        interpreter_compatibility_ref=_profile_ref(profiles["interpreter"]),
        observation_profile_ref=_profile_ref(profiles["observation"]),
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=source.owner,
    )
    codec = dataclass_codec(
        codec_id=source.payload_codec_id,
        codec_version="1",
        contract_ref=operation.ref,
        payload_type_id=source.input_type.type_id,
        dto_cls=source.payload_type,
    )
    atom = KnowledgeProgramAtomWiring(
        operation_id=source.operation_id,
        operation_kind=source.kind,
        payload_codec_id=source.payload_codec_id,
        input_type=source.input_type,
        output_type=source.output_type,
        return_contract_ref=source.return_contract_ref,
        value_suffix=source.cell_id.lower().replace(".", "-"),
    )
    contribution_namespace = source.cell_id.removeprefix("knowledge.").removesuffix(".v2")
    return KnowledgeCellDefinition(
        family_id=KNOWLEDGE_FAMILY_ID,
        contribution_id=(
            source.contribution_id
            if source.contribution_id is not None
            else f"mrw.knowledge.{contribution_namespace}.native.v2"
        ),
        cell_id=source.cell_id,
        owner=source.owner,
        operation_id=source.operation_id,
        kind=source.kind,
        input_type=source.input_type,
        output_type=source.output_type,
        return_contract_ref=source.return_contract_ref,
        payload_type=source.payload_type,
        payload_codec=codec,
        profiles=profiles,
        operation_contract=operation,
        program_atom=atom,
        failure_codes=source.failure_codes,
        projector_wiring=source.projector_wiring,
        rollback_binding=KnowledgeGraphProjectionRollback(source.rollback_refs),
    )


def define_knowledge_graph_projection_cell(
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
    projector_wiring: KnowledgeGraphProjectionWiring | None,
    rollback_refs: tuple[str, ...],
    failure_codes: tuple[str, ...] = KNOWLEDGE_GRAPH_PROJECTION_FAILURE_CODES,
    return_contract_ref: str = KNOWLEDGE_GRAPH_PROJECTION_RETURN_CONTRACT_REF,
) -> KnowledgeCellDefinition:
    lowered = lower_knowledge_graph_projection_author_source(
        KnowledgeGraphProjectionAuthorSource(
            cell_id=cell_id,
            contribution_id=contribution_id,
            owner=owner,
            operation_id=operation_id,
            kind=kind,
            payload_codec_id=payload_codec_id,
            input_type=input_type,
            output_type=output_type,
            payload_type=payload_type,
            projector_wiring=projector_wiring,
            rollback_refs=rollback_refs,
            failure_codes=failure_codes,
            return_contract_ref=return_contract_ref,
        )
    )
    return lowered


KNOWLEDGE_GRAPH_PROJECTION_AUTHOR_SOURCE = KnowledgeGraphProjectionAuthorSource(
    cell_id=KNOWLEDGE_GRAPH_PROJECTION_CELL_ID,
    contribution_id="mrw.knowledge.graph-projection.native.v2",
    owner=KNOWLEDGE_GRAPH_PROJECTION_OWNER,
    operation_id=KNOWLEDGE_GRAPH_PROJECTION_OPERATION_ID,
    kind=KNOWLEDGE_GRAPH_PROJECTION_KIND,
    payload_codec_id=KNOWLEDGE_GRAPH_PROJECTION_PAYLOAD_CODEC_ID,
    input_type=KNOWLEDGE_GRAPH_PROJECTION_INPUT_TYPE,
    output_type=KNOWLEDGE_GRAPH_PROJECTION_RESULT_TYPE,
    payload_type=KnowledgeGraphProjectInput,
    projector_wiring=KnowledgeGraphProjectionWiring(
        projector_id=KNOWLEDGE_GRAPH_PROJECTOR_ID,
        projector_version=KNOWLEDGE_GRAPH_PROJECTOR_VERSION,
        source_kind=KNOWLEDGE_GRAPH_SOURCE_KIND,
        projection_id=GRAPH_CONTEXT_PROJECTION,
        projection_schema_ref=KNOWLEDGE_GRAPH_VALUE_SCHEMA,
        declared_loss=KNOWLEDGE_GRAPH_PROJECTION_DECLARED_LOSS,
        note=(f"capability schema: {GRAPH_PROJECTION_SCHEMA}; exact per-run source key is supplied by the runner"),
    ),
    rollback_refs=(KNOWLEDGE_GRAPH_PROJECTION_ROLLBACK_REF,),
)


def project_knowledge_graph_projection_definition(
    definition: KnowledgeCellDefinition,
) -> ProjectedContributionSpec | Failure:
    issues = knowledge_graph_projection_definition_issues(definition)
    if issues:
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "native knowledge graph-projection definition is invalid",
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
        vocabularies=(knowledge_operation_kinds,),
        failures=(knowledge_graph_failures,),
    )


@dataclass(frozen=True, slots=True)
class KnowledgeGraphProjectionAssemblyContext:
    """Pure assembly boundary; run-specific source keys bind later."""


@dataclass(frozen=True, slots=True)
class KnowledgeGraphProjectionRuntimeBinding:
    definition: KnowledgeCellDefinition
    cell_id: str
    operation_contract: OperationContract
    payload_codec: PayloadCodec
    profiles: Mapping[str, object]
    projector_wiring: KnowledgeGraphProjectionWiring | None
    rollback_binding: KnowledgeGraphProjectionRollback

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
                "knowledge.graph.recovery.v2#offset-cas-keeps-old-active-generation;rebuild-from-source-closure"
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
            reject_knowledge_projection(
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
                    "knowledge.graph.recovery.v2#offset-cas-keeps-old-active-generation;rebuild-from-source-closure"
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


def assemble_knowledge_graph_projection_definition(
    definition: KnowledgeCellDefinition,
    context: KnowledgeGraphProjectionAssemblyContext,
) -> KnowledgeGraphProjectionRuntimeBinding:
    del context
    return KnowledgeGraphProjectionRuntimeBinding(
        definition=definition,
        cell_id=definition.cell_id,
        operation_contract=definition.operation_contract,
        payload_codec=definition.payload_codec,
        profiles=definition.profiles,
        projector_wiring=definition.projector_wiring,
        rollback_binding=definition.rollback_binding,
    )


def validate_knowledge_graph_projection_binding(
    definition: KnowledgeCellDefinition,
    candidate: object,
) -> BindingAccepted[KnowledgeGraphProjectionRuntimeBinding] | BindingRejected:
    if not isinstance(candidate, KnowledgeGraphProjectionRuntimeBinding):
        return BindingRejected((NativeBindingIssue("$.binding", "expected C8GraphProjectionRuntimeBinding"),))
    definition_issues = knowledge_graph_projection_definition_issues(definition)
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


def knowledge_graph_projection_definition_issues(
    definition: KnowledgeCellDefinition,
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


# One reusable MRW rule wires shared graph lowering and the existing definition callbacks.
# The default is compiled through this rule exactly once; no second hand-built definition exists.
KNOWLEDGE_GRAPH_PROJECTION_NATIVE_RULE = NativeContributionRule[
    KnowledgeGraphProjectionAuthorSource,
    KnowledgeCellDefinition,
    KnowledgeGraphProjectionAssemblyContext,
    KnowledgeGraphProjectionRuntimeBinding,
](
    lower=lower_knowledge_graph_projection_author_source,
    project=project_knowledge_graph_projection_definition,
    assemble=assemble_knowledge_graph_projection_definition,
    validate_binding=validate_knowledge_graph_projection_binding,
)

def build_knowledge_graph_projection_binding(
    context: KnowledgeGraphProjectionAssemblyContext | None = None,
) -> Annotated[
    KnowledgeGraphProjectionRuntimeBinding,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=C8CellDefinition "
        "witness=test:test_default_and_installed_c8_4_assembly_preserve_exact_declarations"
    ],
]:
    binding = assemble_knowledge_graph_projection_definition(
        KNOWLEDGE_GRAPH_PROJECTION_DEFINITION,
        context or KnowledgeGraphProjectionAssemblyContext(),
    )
    decision = validate_knowledge_graph_projection_binding(KNOWLEDGE_GRAPH_PROJECTION_DEFINITION, binding)
    if isinstance(decision, BindingRejected):
        reject_knowledge_projection("; ".join(f"{issue.path}: {issue.message}" for issue in decision.issues))
    return binding


KNOWLEDGE_GRAPH_PROJECTION_RULE_ID = "mrw.knowledge.graph-projection.native-rule.v2"
KNOWLEDGE_GRAPH_PROJECTION_VERIFICATION_INPUTS = (
    "mrw.knowledge.graph.definition",
    "mrw.knowledge.graph.codec",
    "mrw.knowledge.graph.profile",
    "mrw.knowledge.graph.authority",
)


def _run_knowledge_graph_projection_definition_law(definition: KnowledgeCellDefinition) -> Failure | None:
    """Run the inert definition law for the graph projection cell; no assembly runs."""

    issues = knowledge_graph_projection_definition_issues(definition)
    authority = definition.profiles.get("authority")
    if authority is None or authority.approval_required is not False:
        issues += (
            NativeBindingIssue(
                "$.definition.profiles.authority",
                "authority approval boundary drift",
            ),
        )
    if issues:
        return knowledge_graph_failures.fail(
            "GRAPH_ITEM_CANONICAL_REF_INVALID",
            f"{definition.contribution_id} graph projection definition law failed",
            {
                "issues": tuple(
                    {"code": "definition_law", "path": issue.path, "message": issue.message}
                    for issue in issues
                )
            },
        )
    return None


def verify_knowledge_graph_projection_definition(
    definition: KnowledgeCellDefinition,
    native: object,
) -> ContributionVerification | Failure:
    """Plan inert law obligations for the graph projection native definition."""

    del native
    witness = define_law_witness(
        f"test_knowledge_graph_projection_definition_law:{definition.contribution_id}",
        lambda: _run_knowledge_graph_projection_definition_law(definition),
    )
    if isinstance(witness, Failure):
        return witness
    return ContributionVerification(
        rule_id=KNOWLEDGE_GRAPH_PROJECTION_RULE_ID,
        inputs=KNOWLEDGE_GRAPH_PROJECTION_VERIFICATION_INPUTS,
        checks=(VerificationCheck(witness=witness, inputs=KNOWLEDGE_GRAPH_PROJECTION_VERIFICATION_INPUTS),),
        complete=True,
    )


KNOWLEDGE_GRAPH_PROJECTION_NATIVE_RULE = replace(
    KNOWLEDGE_GRAPH_PROJECTION_NATIVE_RULE,
    verification=verify_knowledge_graph_projection_definition,
)

_compiled_knowledge_graph_projection_native = compile_native_contribution(
    KNOWLEDGE_GRAPH_PROJECTION_AUTHOR_SOURCE,
    KNOWLEDGE_GRAPH_PROJECTION_NATIVE_RULE,
)
if isinstance(_compiled_knowledge_graph_projection_native, Failure):
    reject_knowledge_contract(
        "invalid native knowledge graph-projection contribution: "
        f"{_compiled_knowledge_graph_projection_native.message}",
        exception_type=RuntimeError,
        operation=KNOWLEDGE_GRAPH_PROJECTION_OPERATION_ID,
        site="c8_graph_projection_contribution.import",
    )
knowledge_graph_projection_native_contribution: NativeContribution[
    KnowledgeCellDefinition,
    KnowledgeGraphProjectionAssemblyContext,
    KnowledgeGraphProjectionRuntimeBinding,
] = _compiled_knowledge_graph_projection_native
KNOWLEDGE_GRAPH_PROJECTION_DEFINITION = knowledge_graph_projection_native_contribution.definition
