"""Authored C2 native-contribution rule over the existing source-library authority.

The rule lowers one authored C2 fact into the ordered
resolve -> plan -> provider effect -> terminal projection pipeline.  It owns no
domain kernel: the resolution, planning and provider-acquisition bundles and
the terminal projector remain the authority for contract constants, and
``c2_assembly`` remains the authority for inert family installation.  The
external provider effect and derived terminal projection are separately declared so no stage can borrow the
other's authorization.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from functorial_kit import define_failure_family
from functorial_kit.contribution_compiler import (
    NativeContributionRule,
    compile_native_contribution,
)
from functorial_kit.contribution_verification import (
    ContributionVerification,
    VerificationCheck,
)
from functorial_kit.contributions import (
    ContributionObject,
    contribution_failures,
)
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import define_law_witness
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    ProjectedContributionSpec,
)

from app.successor_runtime.capabilities import (
    source_resolution as resolution,
)
from app.successor_runtime.capabilities import (
    source_planning as planning,
)
from app.successor_runtime.capabilities import (
    source_provider_acquisition as provider_acquisition,
)
from app.successor_runtime.capabilities import (
    source_terminal_projection as terminal_projection,
)
from mrw_functorial_kit.core.source_semantics import source_contract_failures
from mrw_functorial_kit.core.w06_semantics import (
    source_provider_acquisition_failures,
    source_runtime_binding_failures,
    source_single_source_guard_failures,
)

if TYPE_CHECKING:
    from app.successor_runtime.assembly.base import ProjectorSourceKey

__all__ = [
    "SOURCE_NATIVE_RULE_ID",
    "SOURCE_NATIVE_VERIFICATION_INPUTS",
    "SOURCE_ACQUISITION_FAILURES",
    "SourceAssemblyContext",
    "SourceNativeBinding",
    "SourceNativeDefinition",
    "SourceNativeSource",
    "SourceStageSource",
    "ASSEMBLY_CELL_IDS",
    "SOURCE_FAMILY_ID",
    "DEFAULT_SOURCE_NATIVE_SOURCE",
    "compile_source_native_contribution",
]

SOURCE_NATIVE_RULE_ID = "mrw.source.acquire.native-rule.v2"
SOURCE_NATIVE_VERIFICATION_INPUTS = (
    "mrw.source.definition",
    "mrw.source.operation-order",
    "mrw.source.provider-effect-boundary",
    "mrw.source.terminal-projection-boundary",
    "mrw.source.binding",
)

SOURCE_ACQUISITION_FAILURES = define_failure_family(
    "source.acquire.failure",
    (
        "SOURCE_SCHEMA_INVALID",
        "SOURCE_DIGEST_INVALID",
        "SOURCE_SCOPE_INVALID",
        "SOURCE_CATALOG_INVALID",
        "SOURCE_PROGRAM_BINDING_INVALID",
        "SOURCE_CODEC_INVALID",
    ),
)

_CURRENT_OPERATION_IDS = (
    "source.resolve_execution_request.v2",
    "source.plan_protocol_search.v2",
    "source.plan_provider_harvest.v2",
    "source.plan_site_search.v2",
    "source.plan_url_execution.v2",
    "source.execute_provider_acquisition.v2",
)
_CURRENT_TERMINAL_PROJECTION_ID = "source.project_terminal_result.v2"
SOURCE_FAMILY_ID = "mrw.source"

SourceStageName = Literal["resolve", "plan", "provider_effect", "terminal_projection"]
_STAGE_ORDER: tuple[SourceStageName, ...] = (
    "resolve",
    "plan",
    "provider_effect",
    "terminal_projection",
)


@dataclass(frozen=True, slots=True)
class SourceStageSource:
    """One authored C2 stage bound to an existing authoritative cell."""

    name: SourceStageName
    cell_id: str
    kinds: tuple[str, ...]
    owners: tuple[str, ...]
    external_effect: bool
    read_only_projection: bool


@dataclass(frozen=True, slots=True)
class SourceNativeSource:
    """One authored C2 fact: ordered pipeline with separate effect boundaries."""

    contribution_id: str
    owner: str
    stages: tuple[SourceStageSource, ...]


DEFAULT_SOURCE_NATIVE_SOURCE = SourceNativeSource(
    contribution_id="mrw.source.resolve-and-acquire.native.v2",
    owner="source.acquire.v2",
    stages=(
        SourceStageSource(
            name="resolve",
            cell_id="source.resolve-execution-request.v2",
            kinds=(resolution.SOURCE_RESOLUTION_KIND,),
            owners=(resolution.SOURCE_RESOLUTION_OWNER,),
            external_effect=False,
            read_only_projection=False,
        ),
        SourceStageSource(
            name="plan",
            cell_id="source.plan-source-mode.v2",
            kinds=tuple(operation.ref.kind for operation in planning.build_source_planning_bundle().operations),
            owners=tuple(
                operation.owner_capability_id for operation in planning.build_source_planning_bundle().operations
            ),
            external_effect=False,
            read_only_projection=False,
        ),
        SourceStageSource(
            name="provider_effect",
            cell_id="source.execute-provider-acquisition.v2",
            kinds=(provider_acquisition.SOURCE_PROVIDER_ACQUISITION_KIND,),
            owners=(provider_acquisition.SOURCE_PROVIDER_ACQUISITION_OWNER,),
            external_effect=True,
            read_only_projection=False,
        ),
        SourceStageSource(
            name="terminal_projection",
            cell_id="source.project-terminal-result.v2",
            kinds=(terminal_projection.SOURCE_TERMINAL_PROJECTION_KIND,),
            owners=(terminal_projection.SOURCE_TERMINAL_PROJECTION_OWNER,),
            external_effect=False,
            read_only_projection=True,
        ),
    ),
)

ASSEMBLY_CELL_IDS = tuple(stage.cell_id for stage in DEFAULT_SOURCE_NATIVE_SOURCE.stages)


def _issue_tuple(checks: tuple[tuple[bool, str, str], ...]) -> tuple[NativeBindingIssue, ...]:
    return tuple(NativeBindingIssue(path, message) for valid, path, message in checks if not valid)


def _definition_issues(source: SourceNativeSource) -> tuple[NativeBindingIssue, ...]:
    stage_names = tuple(stage.name for stage in source.stages)
    stage_shape_valid = stage_names == _STAGE_ORDER
    issues = _issue_tuple(
        (
            (
                stage_shape_valid,
                "$.source.stages",
                "C2 stage order must be resolve, plan, provider_effect, terminal_projection",
            ),
            (
                tuple(stage.cell_id for stage in source.stages) == ASSEMBLY_CELL_IDS,
                "$.source.stages.cell_id",
                "source native cell identity drift",
            ),
            (
                all(stage.external_effect == (stage.name == "provider_effect") for stage in source.stages),
                "$.source.stages.external_effect",
                "only the provider_effect stage may declare an external effect",
            ),
            (
                all(stage.read_only_projection == (stage.name == "terminal_projection") for stage in source.stages),
                "$.source.stages.read_only_projection",
                "only the terminal_projection stage may declare read-only derivation",
            ),
            (len(source.owner) > 0, "$.source.owner", "owner is empty"),
        )
    )
    if not stage_shape_valid:
        return issues
    # Identity is checked against the existing bundle authorities, never
    # re-derived here: resolve/plan/provider effect bundles and the projector
    # stay the owners of their contract constants.
    b21 = resolution.build_source_resolution_bundle()
    b22 = planning.build_source_planning_bundle()
    b23 = provider_acquisition.build_source_provider_acquisition_bundle()
    issues += _issue_tuple(
        (
            (
                source.stages[0].kinds == (b21.operation.ref.kind,),
                "$.source.stages[0].kinds",
                "resolve kind drift",
            ),
            (
                source.stages[0].owners == (b21.operation.owner_capability_id,),
                "$.source.stages[0].owner",
                "resolve owner drift",
            ),
            (
                source.stages[1].kinds == tuple(operation.ref.kind for operation in b22.operations),
                "$.source.stages[1].kinds",
                "source planning ordered operation kinds drift",
            ),
            (
                source.stages[1].owners == tuple(operation.owner_capability_id for operation in b22.operations),
                "$.source.stages[1].owners",
                "source planning owners drift",
            ),
            (
                source.stages[2].kinds == (b23.operation.ref.kind,),
                "$.source.stages[2].kinds",
                "provider acquisition kind drift",
            ),
            (
                source.stages[2].owners == (b23.operation.owner_capability_id,),
                "$.source.stages[2].owner",
                "provider acquisition owner drift",
            ),
            (
                source.stages[3].kinds == (terminal_projection.SOURCE_TERMINAL_PROJECTION_KIND,),
                "$.source.stages[3].kinds",
                "terminal projection identity drift",
            ),
        )
    )
    return issues


@dataclass(frozen=True, slots=True)
class SourceNativeDefinition:
    source: SourceNativeSource

    @property
    def contribution_id(self) -> str:
        return self.source.contribution_id

    def contribution_objects(self) -> tuple[ContributionObject, ...]:
        b21 = resolution.build_source_resolution_bundle()
        b22 = planning.build_source_planning_bundle()
        b23 = provider_acquisition.build_source_provider_acquisition_bundle()
        objects: list[ContributionObject] = []
        contracts = (b21.operation, *b22.operations, b23.operation)
        seen: set[tuple[str, str]] = set()
        for current_operation_id, contract in zip(_CURRENT_OPERATION_IDS, contracts):
            input_type = contract.input_type.type_id
            output_type = contract.output_type.type_id
            for object_id, kind, references in (
                (input_type, "ObjectType", ()),
                (output_type, "ObjectType", (input_type,)),
                (
                    current_operation_id,
                    "Capability",
                    (input_type, output_type),
                ),
            ):
                object_owner = self.source.owner if kind == "ObjectType" else contract.owner_capability_id
                key = (object_id, kind)
                if key not in seen:
                    seen.add(key)
                    objects.append(ContributionObject(object_id, kind, object_owner, references))
        for stage in self.source.stages:
            if stage.read_only_projection:
                terminal_owner = stage.owners[0]
                objects.append(
                    ContributionObject(
                        _CURRENT_TERMINAL_PROJECTION_ID,
                        "ReadOnlyProjection",
                        terminal_owner,
                        (),
                    )
                )
        return tuple(objects)


def lower_source_native_source(source: SourceNativeSource) -> SourceNativeDefinition | Failure:
    issues = _definition_issues(source)
    if issues:
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "native C2 definition is invalid",
            {
                "issues": tuple(
                    {"code": "invalid_spec", "path": issue.path, "message": issue.message} for issue in issues
                )
            },
        )
    return SourceNativeDefinition(source=source)


def project_source_native_definition(
    definition: SourceNativeDefinition,
) -> ProjectedContributionSpec | Failure:
    return ProjectedContributionSpec(
        id=definition.contribution_id,
        owner=definition.source.owner,
        objects=definition.contribution_objects(),
        failures=(
            SOURCE_ACQUISITION_FAILURES,
            source_contract_failures,
            source_runtime_binding_failures,
            source_provider_acquisition_failures,
            source_single_source_guard_failures,
        ),
    )


@dataclass(frozen=True, slots=True)
class SourceAssemblyContext:
    """Explicit inert assembly boundary; handlers only run inside the family."""

    uow_factory: Callable[[], object]
    project_scope_digest: str
    provider_gateway: object | None = None
    projector_source_keys: Mapping[str, ProjectorSourceKey] | None = None


@dataclass(frozen=True, slots=True)
class SourceNativeBinding:
    definition: SourceNativeDefinition
    family_assembly: object


def assemble_source_native_definition(
    definition: SourceNativeDefinition,
    context: SourceAssemblyContext,
) -> SourceNativeBinding | Failure:
    from app.successor_runtime.assembly.source_assembly import build_source_assembly

    family_assembly = build_source_assembly(
        uow_factory=context.uow_factory,
        project_scope_digest=context.project_scope_digest,
        provider_gateway=context.provider_gateway,
        projector_source_keys=context.projector_source_keys,
        native=definition,
    )
    return SourceNativeBinding(
        definition=definition,
        family_assembly=family_assembly,
    )


def validate_source_native_binding(
    definition: SourceNativeDefinition,
    candidate: object,
) -> BindingAccepted[SourceNativeBinding] | BindingRejected:
    if not isinstance(candidate, SourceNativeBinding):
        return BindingRejected((NativeBindingIssue("$.binding", "expected C2NativeBinding"),))
    expected_cells = tuple(stage.cell_id for stage in definition.source.stages)
    actual_cells = tuple(cell.cell_id for cell in candidate.family_assembly.cells)  # type: ignore[attr-defined]
    actual_refs = tuple(tuple(cell.operation_contract_refs) for cell in candidate.family_assembly.cells)
    actual_handler_digests = tuple(handler.handler_binding_digest for handler in candidate.family_assembly.handlers)
    cell_handler_digests = tuple(cell.handler_binding_digest for cell in candidate.family_assembly.cells[:3])
    actual_handler_contract_digests = tuple(
        handler.operation_contract_digest for handler in candidate.family_assembly.handlers
    )
    b21 = resolution.build_source_resolution_bundle()
    b22 = planning.build_source_planning_bundle()
    b23 = provider_acquisition.build_source_provider_acquisition_bundle()
    expected_handler_contract_digests = (
        b21.operation.ref.contract_digest,
        *(operation.ref.contract_digest for operation in b22.operations),
        b23.operation.ref.contract_digest,
    )
    projector_wiring = candidate.family_assembly.projector_wiring
    projector_registry = candidate.family_assembly.projector_registry
    projector_cell = candidate.family_assembly.cells[-1]
    refs_match = actual_refs == tuple(stage.kinds for stage in definition.source.stages)
    handlers_match = (
        actual_handler_contract_digests == expected_handler_contract_digests
        and len(actual_handler_digests) == len(expected_handler_contract_digests)
        and cell_handler_digests
        == (
            actual_handler_digests[0],
            actual_handler_digests[1],
            actual_handler_digests[-1],
        )
    )
    projector_matches = (
        len(projector_wiring) == 1
        and projector_wiring[0].cell_id == ASSEMBLY_CELL_IDS[-1]
        and projector_wiring[0].projector_id == terminal_projection.SOURCE_TERMINAL_PROJECTION_PROJECTOR_ID
    )
    if projector_cell.status == "INSTALLED":
        registry_matches = projector_registry is not None and projector_cell.handler_binding_digest in {
            projector_wiring[0].registration_digest(contract) for contract in projector_registry.projectors
        }
    else:
        registry_matches = projector_cell.status == "PROJECTOR_WIRING_DECLARED" and projector_registry is None
    issues = _issue_tuple(
        (
            (candidate.definition == definition, "$.binding.definition", "definition drift"),
            (
                candidate.family_assembly.family_id == SOURCE_FAMILY_ID,  # type: ignore[attr-defined]
                "$.binding.family_assembly.family_id",
                "family id drift",
            ),
            (actual_cells == expected_cells, "$.binding.family_assembly.cells", "cell order drift"),
            (
                actual_cells[-1:] == ASSEMBLY_CELL_IDS[-1:],
                "$.binding.family_assembly.cells",
                "terminal projection must be the final cell",
            ),
            (
                refs_match,
                "$.binding.family_assembly.cells.operation_contract_refs",
                "installed operation contract refs drift from native source",
            ),
            (
                handlers_match,
                "$.binding.family_assembly.handlers",
                "installed handler binding digest drift",
            ),
            (
                projector_matches,
                "$.binding.family_assembly.projector_wiring",
                "installed projector identity drift",
            ),
            (
                registry_matches,
                "$.binding.family_assembly.projector_registry",
                "installed projector registration drift",
            ),
        )
    )
    return BindingRejected(issues) if issues else BindingAccepted(candidate)


def verify_source_native_definition(
    definition: SourceNativeDefinition,
    native: object,
) -> ContributionVerification | Failure:
    del native

    def _run() -> Failure | None:
        issues = _definition_issues(definition.source)
        if not issues:
            return None
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "; ".join(f"{issue.path}: {issue.message}" for issue in issues),
        )

    witness = define_law_witness(
        f"test_source_native_definition_law:{definition.contribution_id}",
        _run,
    )
    if isinstance(witness, Failure):
        return witness
    return ContributionVerification(
        rule_id=SOURCE_NATIVE_RULE_ID,
        inputs=SOURCE_NATIVE_VERIFICATION_INPUTS,
        checks=(VerificationCheck(witness=witness, inputs=SOURCE_NATIVE_VERIFICATION_INPUTS),),
        complete=True,
    )


SOURCE_NATIVE_CONTRIBUTION_RULE = NativeContributionRule[
    SourceNativeSource,
    SourceNativeDefinition,
    SourceAssemblyContext,
    SourceNativeBinding,
](
    lower=lower_source_native_source,
    project=project_source_native_definition,
    assemble=assemble_source_native_definition,
    validate_binding=validate_source_native_binding,
    verification=verify_source_native_definition,
)


def compile_source_native_contribution(
    source: SourceNativeSource,
) -> object:
    return compile_native_contribution(source, SOURCE_NATIVE_CONTRIBUTION_RULE)
