"""Current workflow-definition contribution over the historical DSL authority.

The rule lowers one authored legacy DSL fact into the existing operation
contracts, catalog, registry, exact ProgramSpec/ExecutionPlan receipt and the
existing workflow family assembly.  :mod:`workflow_legacy_dsl` remains the
authority for parse/validate/compile semantics;
:mod:`workflow_slice_acceptance` and the workflow assembly remain the
authorities for acceptance and kernel wiring.  This rule
owns no domain kernel and creates no runtime, scheduler, cache or second DSL
consumer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

from functorial_kit.contribution_compiler import (
    NativeContributionRule,
    compile_native_contribution,
)
from functorial_kit.contribution_verification import (
    ContributionVerification,
    VerificationCheck,
)
from functorial_kit.contributions import ContributionObject, contribution_failures
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import define_law_witness
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    ProjectedContributionSpec,
)

from app.successor_runtime.capabilities import workflow_legacy_dsl as workflow_dsl
from app.successor_runtime.capabilities.workflow_common import (
    WORKFLOW_DEFINITION_FAILURES,
)

if TYPE_CHECKING:
    from app.successor_runtime.assembly.base import FamilyAssembly

__all__ = [
    "WORKFLOW_NATIVE_CONTRIBUTION_RULE",
    "WORKFLOW_NATIVE_RULE_ID",
    "WORKFLOW_NATIVE_VERIFICATION_INPUTS",
    "ASSEMBLY_CELL_IDS",
    "WORKFLOW_ASSEMBLY_CELL_IDS",
    "WORKFLOW_DEFINITION_COMPILE_CELL_ID",
    "WORKFLOW_DEFINITION_FAILURES",
    "WORKFLOW_FAMILY_ID",
    "WORKFLOW_RUNTIME_OBSERVE_CELL_ID",
    "WORKFLOW_STATE_RESTORE_CELL_ID",
    "WorkflowAssemblyContext",
    "WorkflowNativeBinding",
    "WorkflowNativeDefinition",
    "WorkflowNativeSource",
    "WorkflowCellSource",
    "DEFAULT_WORKFLOW_NATIVE_SOURCE",
    "compile_workflow_native_contribution",
]

WORKFLOW_NATIVE_RULE_ID = "mrw.workflow.definition.native-rule.v2"
WORKFLOW_NATIVE_VERIFICATION_INPUTS = (
    "mrw.workflow.definition",
    "mrw.workflow.dsl-compile",
    "mrw.workflow.operation-catalog",
    "mrw.workflow.acceptance-boundary",
    "mrw.workflow.binding",
)

WORKFLOW_FAMILY_ID: Final = "mrw.workflow"
WORKFLOW_DEFINITION_COMPILE_CELL_ID: Final = "workflow.definition.compile.v2"
WORKFLOW_RUNTIME_OBSERVE_CELL_ID: Final = "workflow.runtime.observe.v2"
WORKFLOW_STATE_RESTORE_CELL_ID: Final = "workflow.state.restore.v2"

WorkflowCellRole = Literal[
    "definition_compile",
    "runtime_observe",
    "state_restore",
]


@dataclass(frozen=True, slots=True)
class WorkflowCellSource:
    """One ordered workflow cell and its runtime-kernel identity."""

    cell_id: str
    role: WorkflowCellRole
    owner: str
    kernel_id: str | None
    kernel_version: str
    digest_preimage: str
    recovery_binding_ref: str

@dataclass(frozen=True, slots=True)
class WorkflowNativeSource:
    """One authored workflow definition fact: exact DSL payload plus its rollback authority."""

    contribution_id: str
    owner: str
    family_id: str
    cells: tuple[WorkflowCellSource, ...]
    dsl_payload: Any
    rollback_refs: tuple[str, ...]
    interpreter_profile_id: str
    deployment_catalog_preimage: str
    authority_requirement_preimage: str


DEFAULT_WORKFLOW_NATIVE_SOURCE = WorkflowNativeSource(
    contribution_id="mrw.workflow.definition.native.v2",
    owner="workflow.definition.v2",
    family_id=WORKFLOW_FAMILY_ID,
    cells=(
        WorkflowCellSource(
            cell_id=WORKFLOW_DEFINITION_COMPILE_CELL_ID,
            role="definition_compile",
            owner="workflow.definition.v2",
            kernel_id=None,
            kernel_version="2.0.0",
            digest_preimage="mrw.workflow.definition.compile.handler.v2",
            recovery_binding_ref="mrw.workflow.definition.compile.recovery.v2",
        ),
        WorkflowCellSource(
            cell_id=WORKFLOW_RUNTIME_OBSERVE_CELL_ID,
            role="runtime_observe",
            owner="workflow.runtime.v2",
            kernel_id="mrw.workflow.runtime-observe.kernel.v2",
            kernel_version="2.0.0",
            digest_preimage="mrw.workflow.runtime-observe.kernel-wiring.v2",
            recovery_binding_ref="mrw.workflow.runtime.observe.recovery.v2",
        ),
        WorkflowCellSource(
            cell_id=WORKFLOW_STATE_RESTORE_CELL_ID,
            role="state_restore",
            owner="workflow.state.v2",
            kernel_id="mrw.workflow.state-restore.replay.v2",
            kernel_version="2.0.0",
            digest_preimage="mrw.workflow.state-restore.kernel-wiring.v2",
            recovery_binding_ref="mrw.workflow.state.restore.recovery.v2",
        ),
    ),
    dsl_payload={
        "version": "1.0",
        "options": {},
        "nodes": [
            {"node_id": "retrieve", "node_type": "vector_search", "config": {"top_k": 5}},
            {"node_id": "draft", "node_type": "llm_call", "config": {"model": "mrw-local"}},
            {"node_id": "combine", "node_type": "join", "config": {"field": "values"}},
        ],
        "edges": [
            {"from": "retrieve", "to": "combine"},
            {"from": "draft", "to": "combine"},
        ],
    },
    rollback_refs=(
        "main/backend/app/successor_migration/legacy_workflow_graph.py",
        "main/backend/app/successor_runtime/capabilities/c1_legacy_dsl.py",
        "main/backend/app/successor_runtime/capabilities/c1_slice_acceptance.py",
    ),
    interpreter_profile_id="workflow.definition.compile.interpreter.v2",
    deployment_catalog_preimage="mrw.workflow.deployment-catalog.v2",
    authority_requirement_preimage="mrw.workflow.definition.compile.authority.v2",
)

ASSEMBLY_CELL_IDS: Final = tuple(
    cell.cell_id for cell in DEFAULT_WORKFLOW_NATIVE_SOURCE.cells
)
WORKFLOW_ASSEMBLY_CELL_IDS = ASSEMBLY_CELL_IDS


@dataclass(frozen=True, slots=True)
class WorkflowNativeDefinition:
    """Lowered view of one authored workflow source over existing authorities."""

    source: WorkflowNativeSource
    receipt: workflow_dsl.WorkflowLegacyDSLReceipt
    operation_contracts: tuple[workflow_dsl.OperationContract, ...]
    catalog: workflow_dsl.OperationContractCatalogSnapshot
    registry: workflow_dsl.OperationContractRegistry

    @property
    def contribution_id(self) -> str:
        return self.source.contribution_id

    def contribution_objects(self) -> tuple[ContributionObject, ...]:
        merged: dict[tuple[str, str, str], tuple[str, ...]] = {}
        context_type = workflow_dsl.WORKFLOW_CONTEXT_TYPE.type_id
        for operation in self.operation_contracts:
            declared = (
                (context_type, "ObjectType", ()),
                (
                    operation.ref.kind,
                    "Capability",
                    (context_type, context_type),
                ),
            )
            for object_id, kind, references in declared:
                key = (object_id, kind, self.source.owner)
                prior_references = merged.setdefault(key, ())
                merged[key] = prior_references + tuple(
                    reference
                    for reference in references
                    if reference not in prior_references
                )
        return tuple(
            ContributionObject(object_id, kind, owner, references)
            for (object_id, kind, owner), references in merged.items()
        )


def _definition_issues(source: WorkflowNativeSource, definition: WorkflowNativeDefinition) -> tuple[NativeBindingIssue, ...]:
    issues: tuple[NativeBindingIssue, ...] = ()
    checks: tuple[tuple[bool, str, str], ...] = (
        (bool(source.owner), "$.source.owner", "owner is empty"),
        (
            source.family_id == WORKFLOW_FAMILY_ID,
            "$.source.family_id",
            "workflow family identity drift",
        ),
        (
            len(source.cells) == 3
            and tuple(cell.cell_id for cell in source.cells) == ASSEMBLY_CELL_IDS,
            "$.source.cells",
            "workflow cell order drift",
        ),
        (
            tuple(cell.role for cell in source.cells)
            == ("definition_compile", "runtime_observe", "state_restore"),
            "$.source.cells",
            "workflow cell roles drift",
        ),
        (
            len(source.cells) == 3
            and source.cells[0].kernel_id is None
            and all(cell.kernel_id for cell in source.cells[1:]),
            "$.source.cells.kernel_id",
            "compile cell must be a handler and observe/restore must be kernels",
        ),
        (
            all(
                value and ".c1" not in value and "successor" not in value
                for value in (
                    source.interpreter_profile_id,
                    source.deployment_catalog_preimage,
                    source.authority_requirement_preimage,
                    *(cell.digest_preimage for cell in source.cells),
                    *(cell.recovery_binding_ref for cell in source.cells),
                    *(cell.kernel_id or "workflow.definition.compile.handler.v2" for cell in source.cells),
                )
            ),
            "$.source.runtime_identity",
            "current workflow runtime identity contains historical C1/successor naming",
        ),
        (bool(source.rollback_refs), "$.source.rollback_refs", "rollback binding is empty"),
        (definition.receipt.ok, "$.source.dsl_payload", "DSL did not compile successfully"),
        (
            definition.receipt.node_count > 0,
            "$.source.dsl_payload.nodes",
            "compiled DSL has no nodes",
        ),
        (
            definition.receipt.provider_calls == 0
            and definition.receipt.store_writes == 0
            and definition.receipt.canonical_effect_calls == 0,
            "$.source.dsl_payload.effects",
            "Workflow compile must remain pure",
        ),
        (
            definition.catalog.catalog_digest == definition.receipt.catalog_digest,
            "$.catalog_digest",
            "operation catalog digest drifts from compiled receipt",
        ),
        (
            tuple(operation.ref.kind for operation in definition.operation_contracts)
            == tuple(entry[0] for entry in definition.catalog.entries),
            "$.operation_contracts",
            "contract/catalog operation order drift",
        ),
    )
    issues += tuple(
        NativeBindingIssue(path, message)
        for valid, path, message in checks
        if not valid
    )
    return issues


def lower_workflow_native_source(source: WorkflowNativeSource) -> WorkflowNativeDefinition | Failure:
    operation_contracts = workflow_dsl.build_workflow_operation_contracts()
    catalog = workflow_dsl.build_workflow_catalog(operation_contracts)
    registry = workflow_dsl.build_workflow_registry(operation_contracts)
    receipt = workflow_dsl.parse_and_validate_workflow_dsl(
        source.dsl_payload,
        catalog=catalog,
        operation_contracts=registry,
    )
    definition = WorkflowNativeDefinition(
        source=source,
        receipt=receipt,
        operation_contracts=operation_contracts,
        catalog=catalog,
        registry=registry,
    )
    issues = _definition_issues(source, definition)
    if issues:
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "native workflow definition is invalid",
            {
                "issues": tuple(
                    {"code": "invalid_spec", "path": issue.path, "message": issue.message}
                    for issue in issues
                )
            },
        )
    return definition


def project_workflow_native_definition(
    definition: WorkflowNativeDefinition,
) -> ProjectedContributionSpec | Failure:
    return ProjectedContributionSpec(
        id=definition.contribution_id,
        owner=definition.source.owner,
        objects=definition.contribution_objects(),
        failures=(WORKFLOW_DEFINITION_FAILURES, contribution_failures),
    )


@dataclass(frozen=True, slots=True)
class WorkflowAssemblyContext:
    """Explicit inert assembly boundary; the C1.1 handler remains pure."""

    project_scope_digest: str


@dataclass(frozen=True, slots=True)
class WorkflowNativeBinding:
    """Derived workflow binding over the existing family assembly and compiler."""

    definition: WorkflowNativeDefinition
    family_assembly: FamilyAssembly

    @property
    def rollback_binding_refs_by_cell(self) -> tuple[tuple[str, ...], ...]:
        """Read the actual installed rollback declarations, not the source."""
        return tuple(
            rollback.binding_refs
            for rollback in self.family_assembly.rollback_bindings
        )

    @property
    def receipt(self) -> workflow_dsl.WorkflowLegacyDSLReceipt:
        return self.definition.receipt


def assemble_workflow_native_definition(
    definition: WorkflowNativeDefinition,
    context: WorkflowAssemblyContext,
) -> WorkflowNativeBinding | Failure:
    from app.successor_runtime.assembly.workflow_assembly import build_workflow_assembly

    family_assembly = build_workflow_assembly(
        project_scope_digest=context.project_scope_digest,
        native=definition,
    )
    return WorkflowNativeBinding(
        definition=definition,
        family_assembly=family_assembly,
    )


def _issue_tuple(checks: tuple[tuple[bool, str, str], ...]) -> tuple[NativeBindingIssue, ...]:
    return tuple(
        NativeBindingIssue(path, message) for valid, path, message in checks if not valid
    )


def validate_workflow_native_binding(
    definition: WorkflowNativeDefinition,
    candidate: object,
) -> BindingAccepted[WorkflowNativeBinding] | BindingRejected:
    if not isinstance(candidate, WorkflowNativeBinding):
        return BindingRejected((NativeBindingIssue("$.binding", "expected WorkflowNativeBinding"),))
    issues = _issue_tuple(
        (
            (candidate.definition == definition, "$.binding.definition", "definition drift"),
            (
                candidate.family_assembly.family_id == definition.source.family_id,
                "$.binding.family_assembly.family_id",
                "family id drift",
            ),
            (
                tuple(cell.cell_id for cell in candidate.family_assembly.cells)
                == ASSEMBLY_CELL_IDS,
                "$.binding.family_assembly.cells",
                "workflow cell order drift",
            ),
            (
                tuple(rollback.cell_id for rollback in candidate.family_assembly.rollback_bindings)
                == ASSEMBLY_CELL_IDS,
                "$.binding.rollback_bindings",
                "rollback binding cell order drift",
            ),
            (
                tuple(rollback.status for rollback in candidate.family_assembly.rollback_bindings)
                == ("PRESENT", "PRESENT", "PRESENT"),
                "$.binding.rollback_bindings",
                "rollback binding status drift",
            ),
            (
                candidate.family_assembly.rollback_bindings[0].binding_refs
                == definition.source.rollback_refs,
                f"$.binding.rollback_bindings.{ASSEMBLY_CELL_IDS[0]}",
                "workflow compile rollback binding drift from authored source",
            ),
        )
    )
    return BindingRejected(issues) if issues else BindingAccepted(candidate)


def verify_workflow_native_definition(
    definition: WorkflowNativeDefinition,
    native: object,
) -> ContributionVerification | Failure:
    del native
    def _run() -> Failure | None:
        issues = _definition_issues(definition.source, definition)
        if not issues:
            return None
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "; ".join(f"{issue.path}: {issue.message}" for issue in issues),
        )

    witness = define_law_witness(
        f"test_workflow_native_definition_law:{definition.contribution_id}",
        _run,
    )
    if isinstance(witness, Failure):
        return witness
    return ContributionVerification(
        rule_id=WORKFLOW_NATIVE_RULE_ID,
        inputs=WORKFLOW_NATIVE_VERIFICATION_INPUTS,
        checks=(VerificationCheck(witness=witness, inputs=WORKFLOW_NATIVE_VERIFICATION_INPUTS),),
        complete=True,
    )


WORKFLOW_NATIVE_CONTRIBUTION_RULE = NativeContributionRule[
    WorkflowNativeSource,
    WorkflowNativeDefinition,
    WorkflowAssemblyContext,
    WorkflowNativeBinding,
](
    lower=lower_workflow_native_source,
    project=project_workflow_native_definition,
    assemble=assemble_workflow_native_definition,
    validate_binding=validate_workflow_native_binding,
    verification=verify_workflow_native_definition,
)


def compile_workflow_native_contribution(
    source: WorkflowNativeSource,
) -> object:
    return compile_native_contribution(source, WORKFLOW_NATIVE_CONTRIBUTION_RULE)
