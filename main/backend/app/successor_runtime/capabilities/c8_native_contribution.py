"""Reusable native contribution rule for the non-graph C8 cells.

The rule lowers one authored cell fact into the existing C8 profile, contract,
codec, Program atom, ordered composition and assembly declarations.  It does
not own a domain kernel: each capability module supplies its payload, failures,
declared loss, rollback references and exact interface text.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, Protocol

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.codecs import PayloadCodec, dataclass_codec
from app.successor_runtime.language.object_contracts import OperationContract, make_operation_contract
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
from functorial_kit.contribution_compiler import NativeContributionRule
from functorial_kit.contributions import ContributionObject, contribution_failures
from functorial_kit.core.failure import Failure, FailureFamily
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    ProjectedContributionSpec,
)
from mrw_functorial_kit.core.c8_semantics import c8_operation_kinds

if TYPE_CHECKING:
    from app.successor_runtime.assembly.base import CellBinding, RollbackBindingDeclaration

__all__ = [
    "C8NativeAssemblyContext",
    "C8NativeAssemblyDeclaration",
    "C8NativeAuthorSource",
    "C8NativeDefinition",
    "C8NativeOperationDefinition",
    "C8NativeOperationSource",
    "C8NativeRuntimeBinding",
    "C8_NATIVE_CONTRIBUTION_RULE",
    "c8_native_definition_issues",
    "lower_c8_native_author_source",
    "project_c8_native_definition",
    "validate_c8_native_binding",
]

C8_NATIVE_FAMILY_ID = "C8"
C8ExecutionClass = Literal["PURE_TRANSFORM", "EFFECTFUL", "ADMISSION"]


@dataclass(frozen=True, slots=True)
class C8NativeOperationSource:
    operation_id: str
    kind: str
    input_type: ObjectType
    output_type: ObjectType
    return_contract_ref: str
    value_suffix: str
    payload_codec_id: str | None = None
    payload_type: type | None = None


@dataclass(frozen=True, slots=True)
class C8NativeAssemblyDeclaration:
    status: Literal["UNWIRED_DECLARED", "PROJECTOR_WIRING_DECLARED"]
    operation_contract_refs: tuple[str, ...]
    recovery_binding_ref: str
    required_wiring: tuple[str, ...]
    note: str
    rollback_refs: tuple[str, ...]
    installed_required_wiring: tuple[str, ...] = ()
    installed_note: str = ""


@dataclass(frozen=True, slots=True)
class C8NativeAuthorSource:
    contribution_id: str
    cell_id: str
    owner: str
    execution_class: C8ExecutionClass
    operations: tuple[C8NativeOperationSource, ...]
    ordered_operation_ids: tuple[str, ...]
    reads: tuple[str, ...]
    creates: tuple[str, ...]
    failure_codes: tuple[str, ...]
    readback_profile_ref: str
    observation_dimensions: tuple[str, ...]
    assembly: C8NativeAssemblyDeclaration
    failure_family: FailureFamily
    declared_loss: tuple[str, ...] = ()
    creates_relations: tuple[str, ...] = ()
    extra_program_metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class C8ProgramAtomWiring:
    operation_id: str
    operation_kind: str
    payload_codec_id: str | None
    input_type: ObjectType
    output_type: ObjectType
    return_contract_ref: str
    value_suffix: str


@dataclass(frozen=True, slots=True)
class C8NativeOperationDefinition:
    source: C8NativeOperationSource
    operation_contract: OperationContract
    payload_codec: PayloadCodec | None
    program_atom: C8ProgramAtomWiring


@dataclass(frozen=True, slots=True)
class C8NativeDefinition:
    family_id: str
    contribution_id: str
    cell_id: str
    owner: str
    execution_class: C8ExecutionClass
    operations: tuple[C8NativeOperationDefinition, ...]
    ordered_operation_ids: tuple[str, ...]
    profiles: Mapping[str, object]
    assembly: C8NativeAssemblyDeclaration
    failure_codes: tuple[str, ...]
    failure_family: FailureFamily
    extra_program_metadata: Mapping[str, object]

    @property
    def operation_by_id(self) -> Mapping[str, C8NativeOperationDefinition]:
        return MappingProxyType(
            {operation.source.operation_id: operation for operation in self.operations}
        )

    def contribution_objects(self) -> tuple[ContributionObject, ...]:
        # One ordered pipeline may consume the object emitted by its prior
        # operation.  Merge that object's references instead of declaring the
        # same domain object twice.
        merged: dict[tuple[str, str, str], tuple[str, ...]] = {}
        for operation in self.operations:
            source = operation.source
            declared = (
                (source.input_type.type_id, "ObjectType", ()),
                (
                    source.output_type.type_id,
                    "ObjectType",
                    (source.input_type.type_id,),
                ),
                (
                    source.operation_id,
                    "Capability",
                    (source.input_type.type_id, source.output_type.type_id),
                ),
            )
            if operation.payload_codec is not None:
                declared += (
                    (
                        operation.payload_codec.codec_id,
                        "PayloadCodec",
                        (source.operation_id, source.input_type.type_id),
                    ),
                )
            for object_id, kind, references in declared:
                key = (object_id, kind, self.owner)
                prior_references = merged.setdefault(key, ())
                added = tuple(
                    reference
                    for reference in references
                    if reference not in prior_references
                )
                merged[key] = prior_references + added
        return tuple(
            ContributionObject(object_id, kind, owner, references)
            for (object_id, kind, owner), references in merged.items()
        )


class _ProfileRefSource(Protocol):
    @property
    def profile_id(self) -> str: ...

    @property
    def profile_version(self) -> str: ...


def _profile_ref(profile: _ProfileRefSource) -> str:
    return f"{profile.profile_id}@{profile.profile_version}"


def _cell_suffix(cell_id: str) -> str:
    return cell_id.lower().replace(".", "-")


def _profiles(source: C8NativeAuthorSource) -> Mapping[str, object]:
    suffix = _cell_suffix(source.cell_id)
    semantic_values = {
        "semantic_profile_id": f"c8.{suffix}.semantic",
        "semantic_profile_version": "1.0.0",
        "reads": source.reads,
        "creates": source.creates,
        "creates_relations": source.creates_relations,
        "declared_loss": source.declared_loss,
        "observation_profile_ref": f"mrw.successor.c8.{suffix}.observation.v1",
    }
    effect_values = {
        "effect_profile_id": f"c8.{suffix}.effect",
        "effect_profile_version": "1.0.0",
        "execution_class": source.execution_class,
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
        "typed_failures": source.failure_codes,
        "retryable": False,
        "degraded_acceptable": False,
        "unknown_outcome_supported": True,
        "readback_or_compensation": "readback",
        "failure_union_ref": f"mrw.functorial-successor.failures.c8-{suffix}.v1",
        "retryable_failure_kinds": (),
        "readback_profile_ref": source.readback_profile_ref,
        "compensation_profile_ref": None,
    }
    authority_values = {
        "authority_profile_id": f"c8.{suffix}.authority",
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": source.owner,
        "revalidation_points": ("claim_time",),
        "authority_epoch": 1,
    }
    interpreter_values = {
        "interpreter_profile_id": f"successor.c8.{suffix}.v1",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": tuple(operation.kind for operation in source.operations),
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
        "dimensions": source.observation_dimensions,
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


def lower_c8_native_author_source(source: C8NativeAuthorSource) -> C8NativeDefinition:
    profiles = _profiles(source)
    operations: list[C8NativeOperationDefinition] = []
    for operation_source in source.operations:
        operation = make_operation_contract(
            kind=operation_source.kind,
            contract_version="1.0.0",
            input_type=operation_source.input_type,
            output_type=operation_source.output_type,
            return_contract_ref=operation_source.return_contract_ref,
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
        codec = (
            dataclass_codec(
                codec_id=operation_source.payload_codec_id,
                codec_version="1",
                contract_ref=operation.ref,
                payload_type_id=operation_source.input_type.type_id,
                dto_cls=operation_source.payload_type,
            )
            if operation_source.payload_codec_id is not None
            else None
        )
        atom = C8ProgramAtomWiring(
            operation_id=operation_source.operation_id,
            operation_kind=operation_source.kind,
            payload_codec_id=operation_source.payload_codec_id,
            input_type=operation_source.input_type,
            output_type=operation_source.output_type,
            return_contract_ref=operation_source.return_contract_ref,
            value_suffix=operation_source.value_suffix,
        )
        operations.append(
            C8NativeOperationDefinition(
                source=operation_source,
                operation_contract=operation,
                payload_codec=codec,
                program_atom=atom,
            )
        )
    return C8NativeDefinition(
        family_id=C8_NATIVE_FAMILY_ID,
        contribution_id=source.contribution_id,
        cell_id=source.cell_id,
        owner=source.owner,
        execution_class=source.execution_class,
        operations=tuple(operations),
        ordered_operation_ids=source.ordered_operation_ids,
        profiles=profiles,
        assembly=source.assembly,
        failure_codes=source.failure_codes,
        failure_family=source.failure_family,
        extra_program_metadata=MappingProxyType(dict(source.extra_program_metadata)),
    )


def c8_native_definition_issues(definition: C8NativeDefinition) -> tuple[NativeBindingIssue, ...]:
    operations = definition.operation_by_id
    checks = (
        (bool(definition.contribution_id), "$.definition.contribution_id", "contribution id is empty"),
        (bool(definition.cell_id), "$.definition.cell_id", "cell id is empty"),
        (bool(definition.owner), "$.definition.owner", "owner is empty"),
        (bool(definition.operations), "$.definition.operations", "operations are empty"),
        (
            tuple(operations.keys()) == definition.ordered_operation_ids,
            "$.definition.ordered_operation_ids",
            "ordered operation ids do not match declared operations in author order",
        ),
        (
            bool(definition.assembly.rollback_refs),
            "$.definition.assembly.rollback_refs",
            "rollback binding is empty",
        ),
        (
            bool(definition.assembly.operation_contract_refs),
            "$.definition.assembly.operation_contract_refs",
            "assembly operation refs are empty",
        ),
        (
            definition.profiles["effect"].execution_class == definition.execution_class,
            "$.definition.profiles.effect",
            "execution class drift",
        ),
        (
            definition.profiles["authority"].canonical_owner == definition.owner,
            "$.definition.profiles.authority",
            "owner drift",
        ),
        (
            tuple(definition.profiles["failure"].typed_failures) == definition.failure_codes,
            "$.definition.profiles.failure",
            "failure codes drift",
        ),
        (
            tuple(definition.profiles["interpreter"].supported_contract_kinds)
            == tuple(operation.source.kind for operation in definition.operations),
            "$.definition.profiles.interpreter",
            "interpreter kinds drift",
        ),
        *(
            (
                left.source.output_type == right.source.input_type,
                f"$.definition.operations[{right.source.operation_id}].input_type",
                "ordered operation input does not consume prior output",
            )
            for left, right in zip(definition.operations, definition.operations[1:])
        ),
    )
    issues = tuple(NativeBindingIssue(path, message) for valid, path, message in checks if not valid)
    for operation in definition.operations:
        source = operation.source
        prefix = f"$.definition.operations[{source.operation_id}]"
        if operation.payload_codec is None:
            if source.payload_codec_id is not None or source.payload_type is not None:
                issues += (
                    NativeBindingIssue(prefix + ".payload_codec", "codec facts are incomplete without a codec id"),
                )
            continue
        codec = operation.payload_codec
        codec_issues = (
            (source.payload_codec_id == codec.codec_id, prefix + ".payload_codec.codec_id", "codec id drift"),
            (
                source.payload_type is not None and codec.payload_type_id == source.input_type.type_id,
                prefix + ".payload_codec.payload_type_id",
                "codec payload type drift",
            ),
            (
                codec.contract_ref == operation.operation_contract.ref,
                prefix + ".payload_codec.contract_ref",
                "codec contract drift",
            ),
        )
        issues += tuple(NativeBindingIssue(path, message) for valid, path, message in codec_issues if not valid)
    return issues


def project_c8_native_definition(definition: C8NativeDefinition) -> ProjectedContributionSpec | Failure:
    issues = c8_native_definition_issues(definition)
    if issues:
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "native C8 definition is invalid",
            {
                "issues": tuple(
                    {"code": "invalid_spec", "path": issue.path, "message": issue.message}
                    for issue in issues
                )
            },
        )
    return ProjectedContributionSpec(
        id=definition.contribution_id,
        owner=definition.owner,
        objects=definition.contribution_objects(),
        vocabularies=(c8_operation_kinds,),
        failures=(definition.failure_family,),
    )


@dataclass(frozen=True, slots=True)
class C8NativeAssemblyContext:
    """Pure assembly boundary; run dependencies are supplied by FamilyAssembly."""


@dataclass(frozen=True, slots=True)
class C8NativeRuntimeBinding:
    definition: C8NativeDefinition
    cell_id: str
    operations: tuple[C8NativeOperationDefinition, ...]
    profiles: Mapping[str, object]
    assembly: C8NativeAssemblyDeclaration

    def assembly_rollback_binding(self) -> RollbackBindingDeclaration:
        from app.successor_runtime.assembly.base import RollbackBindingDeclaration

        return RollbackBindingDeclaration(
            cell_id=self.cell_id,
            status="PRESENT",
            binding_refs=self.assembly.rollback_refs,
        )

    def declared_cell(self) -> CellBinding:
        from app.successor_runtime.assembly.base import CellBinding

        return CellBinding(
            cell_id=self.cell_id,
            family_id=self.definition.family_id,
            status=self.assembly.status,
            operation_contract_refs=self.assembly.operation_contract_refs,
            recovery_binding_ref=self.assembly.recovery_binding_ref,
            required_wiring=self.assembly.required_wiring,
            note=self.assembly.note,
        )

    def installed_cell(self, handler_binding_digest: str) -> CellBinding:
        from app.successor_runtime.assembly.base import CellBinding

        return CellBinding(
            cell_id=self.cell_id,
            family_id=self.definition.family_id,
            status="INSTALLED",
            operation_contract_refs=self.assembly.operation_contract_refs,
            handler_binding_digest=handler_binding_digest,
            recovery_binding_ref=self.assembly.recovery_binding_ref,
            required_wiring=self.assembly.installed_required_wiring,
            note=self.assembly.installed_note,
        )


def assemble_c8_native_definition(
    definition: C8NativeDefinition,
    context: C8NativeAssemblyContext,
) -> C8NativeRuntimeBinding:
    del context
    return C8NativeRuntimeBinding(
        definition=definition,
        cell_id=definition.cell_id,
        operations=definition.operations,
        profiles=definition.profiles,
        assembly=definition.assembly,
    )


def validate_c8_native_binding(
    definition: C8NativeDefinition,
    candidate: object,
) -> BindingAccepted[C8NativeRuntimeBinding] | BindingRejected:
    if not isinstance(candidate, C8NativeRuntimeBinding):
        return BindingRejected((NativeBindingIssue("$.binding", "expected C8NativeRuntimeBinding"),))
    checks = (
        (candidate.definition == definition, "$.binding.definition", "definition drift"),
        (candidate.cell_id == definition.cell_id, "$.binding.cell_id", "cell id drift"),
        (candidate.operations == definition.operations, "$.binding.operations", "operation drift"),
        (dict(candidate.profiles) == dict(definition.profiles), "$.binding.profiles", "profile drift"),
        (candidate.assembly == definition.assembly, "$.binding.assembly", "assembly declaration drift"),
    )
    issues = c8_native_definition_issues(definition) + tuple(
        NativeBindingIssue(path, message) for valid, path, message in checks if not valid
    )
    return BindingRejected(issues) if issues else BindingAccepted(candidate)


C8_NATIVE_CONTRIBUTION_RULE = NativeContributionRule[
    C8NativeAuthorSource,
    C8NativeDefinition,
    C8NativeAssemblyContext,
    C8NativeRuntimeBinding,
](
    lower=lower_c8_native_author_source,
    project=project_c8_native_definition,
    assemble=assemble_c8_native_definition,
    validate_binding=validate_c8_native_binding,
)
