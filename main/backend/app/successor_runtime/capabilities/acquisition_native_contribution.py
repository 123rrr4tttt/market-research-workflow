"""Authored native-contribution rule over the acquisition batch authority.

The rule lowers one acquisition source into the existing operation contracts, payload
codecs, failure profiles, ordered Program atoms, interpreter identities and
assembly context.  It owns no domain kernel: :mod:`collect_c3` remains the
authority for traversal/fold semantics, and the legacy/successor binding
adapters remain the authority for compatibility bindings.
"""

from __future__ import annotations
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, Literal

if TYPE_CHECKING:
    from app.successor_runtime.assembly.base import AcquisitionAssemblyOptions, FamilyAssembly
from functorial_kit.contribution_compiler import NativeContributionRule, compile_native_contribution
from functorial_kit.contribution_verification import ContributionVerification, VerificationCheck
from functorial_kit.contributions import ContributionObject, contribution_failures
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import define_law_witness
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    ProjectedContributionSpec,
)
from app.successor_runtime.capabilities import acquisition_batch as acquisition
from app.successor_runtime.capabilities import acquisition_batch_program as acquisition_program
from app.successor_runtime.substrate.postgres.acquisition_batch_canary import (
    AcquisitionBatchComposedRuntimeHandler as AcquisitionBatchComposedRuntimeHandler,
)
from mrw_functorial_kit.core.provider_port_failures import collect_runtime_failures
from app.successor_runtime.capabilities import (
    authority_requirement_digest,
    successor_fold_ordered_results_interpreter_profile_digest,
)

__all__ = [
    "ASSEMBLY_CELL_IDS",
    "ACQUISITION_NATIVE_CONTRIBUTION_RULE",
    "ACQUISITION_NATIVE_RULE_ID",
    "ACQUISITION_NATIVE_VERIFICATION_INPUTS",
    "ACQUISITION_BATCH_FAILURES",
    "AcquisitionAssemblyContext",
    "AcquisitionNativeBinding",
    "AcquisitionNativeDefinition",
    "AcquisitionOperationSource",
    "AcquisitionProgramStep",
    "DEFAULT_ACQUISITION_NATIVE_SOURCE",
    "compile_acquisition_native_contribution",
]
ACQUISITION_NATIVE_RULE_ID = "mrw.acquisition.batch.native-rule.v2"
ACQUISITION_NATIVE_PROGRAM_REGISTRY_REVISION = 0
ACQUISITION_NATIVE_VERIFICATION_INPUTS = (
    "mrw.acquisition.batch.definition",
    "mrw.acquisition.batch.order",
    "mrw.acquisition.batch.codec",
    "mrw.acquisition.batch.profile",
    "mrw.acquisition.batch.interpreter",
    "mrw.acquisition.batch.binding",
)
ACQUISITION_BATCH_FAILURES = acquisition.ACQUISITION_BATCH_FAILURES
_CURRENT_CODEC_IDS = ("mrw.acquisition.batch-element.codec.v2", "mrw.acquisition.ordered-result-fold.codec.v2")


@dataclass(frozen=True, slots=True)
class AcquisitionProgramStep:
    """One authored Program atom position in the composed acquisition Program."""

    atom: Literal["TraverseOrdered", "FoldAtom"]
    operation_id: str


@dataclass(frozen=True, slots=True)
class AcquisitionOperationSource:
    operation_id: str
    cell_id: str
    kind: str
    owner: str
    payload_codec_id: str
    failure_profile_id: str
    observation_profile_id: str
    interpreter_id: str
    legacy_interpreter_id: str


@dataclass(frozen=True, slots=True)
class AcquisitionNativeSource:
    """One authored acquisition fact: ordered traversal and fold in one source."""

    contribution_id: str
    bundle_id: str
    owner: str
    operations: tuple[AcquisitionOperationSource, AcquisitionOperationSource]
    program: tuple[AcquisitionProgramStep, AcquisitionProgramStep]
    failure_codes_1: tuple[str, ...]
    failure_codes_2: tuple[str, ...]
    rollback_refs: tuple[str, ...]
    legacy_binding_refs: tuple[str, ...]
    successor_binding_refs: tuple[str, ...]

    @property
    def operation_by_id(self) -> MappingProxyType[str, AcquisitionOperationSource]:
        return MappingProxyType({item.operation_id: item for item in self.operations})


DEFAULT_ACQUISITION_NATIVE_SOURCE = AcquisitionNativeSource(
    contribution_id="mrw.acquisition.batch.native.v2",
    bundle_id="mrw.acquisition.batch.bundle.v2",
    owner="acquisition.batch.v2",
    operations=(
        AcquisitionOperationSource(
            operation_id="acquisition.batch.execute_element.v2",
            cell_id="acquisition.batch.execute_element.v2",
            kind=acquisition.COLLECT_EXECUTE_BATCH_ELEMENT_KIND,
            owner=acquisition.ACQUISITION_BATCH_EXECUTE_ELEMENT_OWNER,
            payload_codec_id=acquisition.ACQUISITION_BATCH_ELEMENT_PAYLOAD_CODEC_ID,
            failure_profile_id="collect.execute_batch_element.v1.failure",
            observation_profile_id=acquisition.COLLECT_TRAVERSAL_OBSERVATION_PROFILE,
            interpreter_id="mrw.acquisition.batch.execute_element.interpreter.v2",
            legacy_interpreter_id="legacy.collect_runtime.batch_traverse.v1",
        ),
        AcquisitionOperationSource(
            operation_id="acquisition.batch.fold_ordered_results.v2",
            cell_id="acquisition.batch.fold_ordered_results.v2",
            kind=acquisition.COLLECT_FOLD_ORDERED_RESULTS_KIND,
            owner=acquisition.ACQUISITION_BATCH_FOLD_ORDERED_RESULTS_OWNER,
            payload_codec_id=acquisition.ACQUISITION_ORDERED_RESULT_FOLD_PAYLOAD_CODEC_ID,
            failure_profile_id="collect.fold_ordered_results.v1.failure",
            observation_profile_id=acquisition.COLLECT_FOLD_OBSERVATION_PROFILE,
            interpreter_id="mrw.acquisition.batch.fold_ordered_results.interpreter.v2",
            legacy_interpreter_id="legacy.collect_runtime.result_fold.v1",
        ),
    ),
    program=(
        AcquisitionProgramStep(atom="TraverseOrdered", operation_id="acquisition.batch.execute_element.v2"),
        AcquisitionProgramStep(atom="FoldAtom", operation_id="acquisition.batch.fold_ordered_results.v2"),
    ),
    failure_codes_1=(
        "INVALID_INPUT",
        "ASSIGNMENT_BINDING_MISMATCH",
        "INTERPRETER_UNAVAILABLE",
        "TRAVERSAL_COMPILE_PENDING",
        "FOLD_CONTRACT_FAILURE",
        "ELEMENT_EXECUTION_FAILED",
        "ORDERED_TRAVERSAL_ABORTED",
        "RESOURCE_POLICY_EXCEEDED",
    ),
    failure_codes_2=(
        "INVALID_INPUT",
        "ASSIGNMENT_BINDING_MISMATCH",
        "INTERPRETER_UNAVAILABLE",
        "TRAVERSAL_COMPILE_PENDING",
        "FOLD_CONTRACT_FAILURE",
        "AGGREGATE_ALL_FAILED",
        "QUEUED_ACK_NOT_COMPLETION",
    ),
    rollback_refs=(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/p3-fragments/C3.json",
        "main/backend/app/successor_migration/legacy_collect_runtime.py",
    ),
    legacy_binding_refs=(
        "legacy_collect_runtime.build_legacy_collect_c3_1_binding",
        "legacy_collect_runtime.build_legacy_collect_c3_2_binding",
    ),
    successor_binding_refs=(
        "legacy_collect_runtime.build_successor_collect_c3_1_binding",
        "legacy_collect_runtime.build_successor_collect_c3_2_binding",
    ),
)
ASSEMBLY_CELL_IDS = tuple((operation.cell_id for operation in DEFAULT_ACQUISITION_NATIVE_SOURCE.operations))


def _issue_tuple(checks: tuple[tuple[bool, str, str], ...]) -> tuple[NativeBindingIssue, ...]:
    return tuple((NativeBindingIssue(path, message) for valid, path, message in checks if not valid))


def _binding_reference_issues(source: AcquisitionNativeSource) -> tuple[NativeBindingIssue, ...]:
    """Keep compatibility identity/order inert; code liveness belongs to migration."""
    return _issue_tuple(
        (
            (
                source.legacy_binding_refs == DEFAULT_ACQUISITION_NATIVE_SOURCE.legacy_binding_refs,
                "$.source.legacy_binding_refs",
                "legacy compatibility binding identity/order drift",
            ),
            (
                source.successor_binding_refs == DEFAULT_ACQUISITION_NATIVE_SOURCE.successor_binding_refs,
                "$.source.successor_binding_refs",
                "successor compatibility binding identity/order drift",
            ),
        )
    )


def _definition_issues(
    source: AcquisitionNativeSource, bundle: acquisition.AcquisitionBatchCapabilityBundle
) -> tuple[NativeBindingIssue, ...]:
    issues = _issue_tuple(
        (
            (bundle.bundle_id == source.bundle_id, "$.source.bundle_id", "bundle identity drift"),
            (len(source.operations) == 2, "$.source.operations", "C3 has exactly two ordered operations"),
            (
                len(source.program) == 2,
                "$.source.program",
                "C3 composed Program has exactly TraverseOrdered then FoldAtom",
            ),
            (
                tuple((step.atom for step in source.program)) == ("TraverseOrdered", "FoldAtom"),
                "$.source.program.atoms",
                "program atom order drift",
            ),
            (
                tuple((step.operation_id for step in source.program))
                == tuple((item.operation_id for item in source.operations)),
                "$.source.program.operation_ids",
                "program operation order drift",
            ),
            (len(source.rollback_refs) >= 1, "$.source.rollback_refs", "rollback binding is empty"),
            (
                tuple(bundle.profiles["failure.c3_1"].typed_failures) == source.failure_codes_1,
                "$.source.failure_codes_1",
                "execute-element failure facts drift",
            ),
            (
                tuple(bundle.profiles["failure.c3_2"].typed_failures) == source.failure_codes_2,
                "$.source.failure_codes_2",
                "ordered-result-fold failure facts drift",
            ),
            (
                tuple(dict.fromkeys(source.failure_codes_1 + source.failure_codes_2))
                == ACQUISITION_BATCH_FAILURES.codes,
                "$.source.failure_codes",
                "native operation failures drift from acquisition family authority",
            ),
        )
    )
    for index, operation in enumerate(source.operations):
        suffix = "c3_1" if index == 0 else "c3_2"
        contract = bundle.execute_element_operation if index == 0 else bundle.fold_ordered_results_operation
        codec = bundle.codecs[index]
        issues += _issue_tuple(
            (
                (contract.ref.kind == operation.kind, f"$.source.operations[{index}].kind", "operation kind drift"),
                (
                    contract.owner_capability_id == operation.owner,
                    f"$.source.operations[{index}].owner",
                    "operation owner drift",
                ),
                (
                    codec.codec_id == operation.payload_codec_id,
                    f"$.source.operations[{index}].payload_codec_id",
                    "payload codec drift",
                ),
                (
                    bundle.profiles[f"failure.{suffix}"].failure_profile_id == operation.failure_profile_id,
                    f"$.source.operations[{index}].failure_profile_id",
                    "failure profile drift",
                ),
                (
                    bundle.profiles[f"observation.{suffix}"].observation_profile_id == operation.observation_profile_id,
                    f"$.source.operations[{index}].observation_profile_id",
                    "observation profile drift",
                ),
                (
                    bundle.profiles[f"interpreter.{suffix}"].interpreter_profile_id == operation.interpreter_id,
                    f"$.source.operations[{index}].interpreter_id",
                    "successor interpreter drift",
                ),
            )
        )
    issues += _binding_reference_issues(source)
    return issues


@dataclass(frozen=True, slots=True)
class AcquisitionNativeDefinition:
    source: AcquisitionNativeSource
    bundle: acquisition.AcquisitionBatchCapabilityBundle
    catalog: object
    registry: object
    program_wiring: tuple[AcquisitionProgramStep, AcquisitionProgramStep]

    @property
    def contribution_id(self) -> str:
        return self.source.contribution_id

    def contribution_objects(self) -> tuple[ContributionObject, ...]:
        contracts = (self.bundle.execute_element_operation, self.bundle.fold_ordered_results_operation)
        merged: dict[tuple[str, str, str], tuple[str, ...]] = {}
        for operation_source, contract, codec_id in zip(self.source.operations, contracts, _CURRENT_CODEC_IDS):
            input_type = contract.input_type.type_id
            output_type = contract.output_type.type_id
            declared = (
                (input_type, "ObjectType", ()),
                (output_type, "ObjectType", (input_type,)),
                (operation_source.operation_id, "Capability", (input_type, output_type)),
                (codec_id, "PayloadCodec", (operation_source.operation_id, input_type)),
            )
            for object_id, kind, references in declared:
                key = (object_id, kind, self.source.owner)
                prior_references = merged.setdefault(key, ())
                merged[key] = prior_references + tuple(
                    (reference for reference in references if reference not in prior_references)
                )
        return tuple(
            (
                ContributionObject(object_id, kind, owner, references)
                for (object_id, kind, owner), references in merged.items()
            )
        )


def lower_acquisition_native_source(source: AcquisitionNativeSource) -> AcquisitionNativeDefinition | Failure:
    bundle = acquisition.build_acquisition_batch_bundle()
    issues = _definition_issues(source, bundle)
    if issues:
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "native C3 definition is invalid",
            {
                "issues": tuple(
                    ({"code": "invalid_spec", "path": issue.path, "message": issue.message} for issue in issues)
                )
            },
        )
    return AcquisitionNativeDefinition(
        source=source,
        bundle=bundle,
        catalog=acquisition.build_acquisition_batch_catalog(bundle),
        registry=acquisition.build_acquisition_batch_registry(bundle),
        program_wiring=source.program,
    )


def project_acquisition_native_definition(
    definition: AcquisitionNativeDefinition,
) -> ProjectedContributionSpec | Failure:
    return ProjectedContributionSpec(
        id=definition.contribution_id,
        owner=definition.source.owner,
        objects=definition.contribution_objects(),
        failures=(ACQUISITION_BATCH_FAILURES, collect_runtime_failures),
    )


@dataclass(frozen=True, slots=True)
class AcquisitionAssemblyContext:
    """Explicit inert assembly boundary; handlers only run in FamilyAssembly."""

    uow_factory: Callable[[], object]
    project_scope_digest: str
    options: "AcquisitionAssemblyOptions"


@dataclass(frozen=True, slots=True)
class AcquisitionNativeBinding:
    definition: AcquisitionNativeDefinition
    family_assembly: "FamilyAssembly"
    catalog: object
    registry: object

    @property
    def rollback_binding_refs_by_cell(self) -> tuple[tuple[str, ...], ...]:
        """Derived authored rollback projection; no second fact source."""
        return tuple((self.definition.source.rollback_refs for _ in self.definition.source.operations))

    def composed_program_id(self, project_key: str) -> str:
        return f"program:acquisition-batch:{project_key}"

    def transform_registry(self) -> object:
        return acquisition_program.build_acquisition_batch_transform_registry()


def _build_composed_handler(
    *,
    definition: AcquisitionNativeDefinition,
    uow_factory: Callable[[], object],
    project_scope_digest: str,
    element_payloads: tuple[object, ...],
) -> AcquisitionBatchComposedRuntimeHandler | None:
    from app.successor_runtime.assembly.base import successor_binding

    bundle = definition.bundle
    catalog = definition.catalog
    registry = definition.registry
    fold_contract_ref = bundle.fold_ordered_results_operation.ref
    project_key = element_payloads[0].parent_request_ref.project_key
    if any((payload.parent_request_ref.project_key != project_key for payload in element_payloads)):
        return None
    program = acquisition_program.build_acquisition_batch_composed_program(
        element_payloads=element_payloads,
        catalog=catalog,
        program_id=f"program:acquisition-batch:{project_key}",
        project_key=project_key,
        project_scope_digest=project_scope_digest,
        project_registry_revision=ACQUISITION_NATIVE_PROGRAM_REGISTRY_REVISION,
    )
    plan = acquisition_program.compile_collect_program(
        program,
        catalog,
        operation_contracts=registry,
        transform_registry=acquisition_program.build_acquisition_batch_transform_registry(),
    )
    deployment_catalog_digest = acquisition.deployment_catalog_digest()
    binding = successor_binding(
        operation_contract_digest=fold_contract_ref.contract_digest,
        interpreter_profile_digest=successor_fold_ordered_results_interpreter_profile_digest(),
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=authority_requirement_digest(
            definition.bundle.fold_ordered_results_operation.ref.kind
        ),
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )
    return AcquisitionBatchComposedRuntimeHandler(
        composed_program=program,
        composed_plan=plan,
        catalog=catalog,
        binding=binding,
        deployment_catalog_digest=deployment_catalog_digest,
        uow_factory=uow_factory,
    )


def assemble_acquisition_native_definition(
    definition: AcquisitionNativeDefinition, context: AcquisitionAssemblyContext
) -> AcquisitionNativeBinding | Failure:
    from app.successor_runtime.assembly.base import CellBinding, FamilyAssembly, RollbackBindingDeclaration

    opts = context.options or AcquisitionAssemblyOptions()
    payloads = tuple(opts.element_payloads)
    if payloads:
        handler = _build_composed_handler(
            definition=definition,
            uow_factory=context.uow_factory,
            project_scope_digest=context.project_scope_digest,
            element_payloads=payloads,
        )
        handler_digest = None if handler is None else handler.handler_binding_digest
        status = "INSTALLED"
        installed_note = "LOCAL_OFFLINE deterministic no-provider fixture closure; both acquisition operations share the composed TraverseOrdered->FoldAtom handler; exact persisted registry revision/scope must be supplied by the run"
    else:
        handler = None
        handler_digest = None
        status = "FIXTURE_CLOSURE_REQUIRED"
        installed_note = (
            "FIXTURE_CLOSURE_REQUIRED: no deterministic element payloads supplied; missing element_payloads"
        )
    cells = tuple(
        (
            CellBinding(
                cell_id=operation.cell_id,
                family_id="acquisition.batch",
                status=status,
                operation_contract_refs=(
                    definition.bundle.execute_element_operation.ref.kind,
                    "mrw.traverse_ordered.materialize",
                )
                if index == 0
                else (definition.bundle.fold_ordered_results_operation.ref.kind,),
                handler_binding_digest=handler_digest,
                recovery_binding_ref="mrw.acquisition.batch.execute_element.recovery.v2"
                if index == 0
                else "mrw.acquisition.batch.fold_ordered_results.recovery.v2",
                rollback_binding_refs=definition.source.rollback_refs,
                note=installed_note,
            )
            for index, operation in enumerate(definition.source.operations)
        )
    )
    rollback_bindings = tuple(
        (
            RollbackBindingDeclaration(
                cell_id=operation.cell_id,
                status="PRESENT",
                binding_refs=definition.source.rollback_refs,
                note="native source rollback binding",
            )
            for operation in definition.source.operations
        )
    )
    family_assembly = FamilyAssembly(
        family_id="acquisition.batch",
        cells=cells,
        handlers=() if handler is None else (handler,),
        rollback_bindings=rollback_bindings,
    )
    return AcquisitionNativeBinding(
        definition=definition, family_assembly=family_assembly, catalog=definition.catalog, registry=definition.registry
    )


def validate_acquisition_native_binding(
    definition: AcquisitionNativeDefinition, candidate: object
) -> BindingAccepted[AcquisitionNativeBinding] | BindingRejected:
    if not isinstance(candidate, AcquisitionNativeBinding):
        return BindingRejected((NativeBindingIssue("$.binding", "expected AcquisitionNativeBinding"),))
    expected_cells = ASSEMBLY_CELL_IDS
    actual_cells = tuple((cell.cell_id for cell in candidate.family_assembly.cells))
    installed = tuple((cell.status for cell in candidate.family_assembly.cells))
    issues = _issue_tuple(
        (
            (candidate.definition == definition, "$.binding.definition", "definition drift"),
            (
                candidate.family_assembly.family_id == "acquisition.batch",
                "$.binding.family_assembly.family_id",
                "family id drift",
            ),
            (actual_cells == expected_cells, "$.binding.family_assembly.cells", "cell order drift"),
            (
                all((status == installed[0] for status in installed)),
                "$.binding.family_assembly.cells.status",
                "cells must share one closure status",
            ),
            (
                (installed == ("INSTALLED", "INSTALLED")) == bool(candidate.family_assembly.handlers),
                "$.binding.family_assembly.handlers",
                "handler presence must follow closure status",
            ),
            (candidate.catalog is definition.catalog, "$.binding.catalog", "catalog drift"),
            (candidate.registry is definition.registry, "$.binding.registry", "registry drift"),
            (
                candidate.rollback_binding_refs_by_cell == (definition.source.rollback_refs,) * len(expected_cells),
                "$.binding.rollback_bindings",
                "rollback binding drift from authored source",
            ),
        )
    )
    return BindingRejected(issues) if issues else BindingAccepted(candidate)


def verify_acquisition_native_definition(
    definition: AcquisitionNativeDefinition, native: object
) -> ContributionVerification | Failure:
    del native

    def _run() -> Failure | None:
        issues = _definition_issues(definition.source, definition.bundle)
        if not issues:
            return None
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID", "; ".join((f"{issue.path}: {issue.message}" for issue in issues))
        )

    witness = define_law_witness(f"test_acquisition_native_definition_law:{definition.contribution_id}", _run)
    if isinstance(witness, Failure):
        return witness
    return ContributionVerification(
        rule_id=ACQUISITION_NATIVE_RULE_ID,
        inputs=ACQUISITION_NATIVE_VERIFICATION_INPUTS,
        checks=(VerificationCheck(witness=witness, inputs=ACQUISITION_NATIVE_VERIFICATION_INPUTS),),
        complete=True,
    )


ACQUISITION_NATIVE_CONTRIBUTION_RULE = NativeContributionRule[
    AcquisitionNativeSource, AcquisitionNativeDefinition, AcquisitionAssemblyContext, AcquisitionNativeBinding
](
    lower=lower_acquisition_native_source,
    project=project_acquisition_native_definition,
    assemble=assemble_acquisition_native_definition,
    validate_binding=validate_acquisition_native_binding,
    verification=verify_acquisition_native_definition,
)
_default_definition: AcquisitionNativeDefinition | Failure | None = None


def default_acquisition_native_definition() -> AcquisitionNativeDefinition | Failure:
    """Lower the default source once for read-only runtime/catalog consumers."""
    global _default_definition
    if _default_definition is None:
        native = compile_acquisition_native_contribution(DEFAULT_ACQUISITION_NATIVE_SOURCE)
        if isinstance(native, Failure):
            return native
        _default_definition = native.definition
    return _default_definition


def compile_acquisition_native_contribution(source: AcquisitionNativeSource) -> object:
    return compile_native_contribution(source, ACQUISITION_NATIVE_CONTRIBUTION_RULE)
