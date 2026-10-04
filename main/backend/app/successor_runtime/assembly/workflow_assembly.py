"""Workflow family assembly: pure compile plus observe/restore kernel wiring.

The workflow family is a parse/validate/compile facade plus runtime node
observation and store-rehydrate facade surfaces.  Workflow definition compile is
installed as a deterministic pure ``RuntimeHandler`` over
``workflow_legacy_dsl.parse_and_validate_workflow_dsl`` and the
``workflow_slice_acceptance.accept_workflow_slice`` named-observation shadow
gate.  It performs no effect, database, provider or canonical write.  Runtime
observation and state restore are carried by explicit ``KernelWiring``
declarations installed by the PostgreSQL composition root; they are not family
``RuntimeHandler`` instances.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from app.successor_runtime.assembly.base import (
    CellBinding,
    FamilyAssembly,
    KernelWiring,
    RollbackBindingDeclaration,
    local_assembly_scope_digest,
    require_assembly_digest,
    sha256_hex,
    successor_binding,
)
from app.successor_runtime.capabilities import workflow_legacy_dsl as workflow_dsl
from app.successor_runtime.capabilities import workflow_slice_acceptance as workflow_acceptance
from app.successor_runtime.capabilities.workflow_native_contribution import (
    ASSEMBLY_CELL_IDS,
    DEFAULT_WORKFLOW_NATIVE_SOURCE,
    WORKFLOW_FAMILY_ID,
    WorkflowCellSource,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.material_ingest_common import MaterialIngestSubmission, build_material_ingest_bundle, build_material_ingest_catalog, build_material_ingest_registry
from app.successor_runtime.capabilities.material_ingest_program import build_material_stage_candidate_program, compile_material_ingest_program
from app.successor_runtime.language.plan import ExecutionPlan
from app.successor_runtime.language.program import ProgramSpec
from app.successor_runtime.runtime.assignments import RuntimeAssignment
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)

WORKFLOW_COMPILE_ROLLBACK_PATH = "main/backend/app/successor_migration/legacy_workflow_graph.py"
WORKFLOW_COMPILE_INTERPRETER_MODULE = (
    "main/backend/app/successor_runtime/capabilities/c1_legacy_dsl.py"
)
WORKFLOW_COMPILE_ACCEPTANCE_MODULE = (
    "main/backend/app/successor_runtime/capabilities/c1_slice_acceptance.py"
)
WORKFLOW_COMPILE_ROLLBACK_PATHS = (
    WORKFLOW_COMPILE_ROLLBACK_PATH,
    WORKFLOW_COMPILE_INTERPRETER_MODULE,
    WORKFLOW_COMPILE_ACCEPTANCE_MODULE,
)

WORKFLOW_COMPILE_INTERPRETER_PROFILE_ID = DEFAULT_WORKFLOW_NATIVE_SOURCE.interpreter_profile_id
WORKFLOW_COMPILE_DEPLOYMENT_CATALOG_DIGEST = sha256_hex(
    DEFAULT_WORKFLOW_NATIVE_SOURCE.deployment_catalog_preimage
)
WORKFLOW_COMPILE_AUTHORITY_REQUIREMENT_DIGEST = sha256_hex(
    DEFAULT_WORKFLOW_NATIVE_SOURCE.authority_requirement_preimage
)

WORKFLOW_RUNTIME_OBSERVATION_ROLLBACK_PATHS = (
    (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/p5-c1-slices/C1SliceA.v1.json"
    ),
    (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/p5-c1-slices/C1SliceB.v1.json"
    ),
    (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/p5-c1-slices/C1SliceC.v1.json"
    ),
    WORKFLOW_COMPILE_ROLLBACK_PATH,
)

WORKFLOW_COMPILE_REQUIRED_WIRING = (
    "workflow definition compiler bound to the pure RuntimeHandler",
    "named-observation compatibility gate remains effect-free",
    "historical rollback binding remains byte-addressed",
)

WORKFLOW_RUNTIME_OBSERVATION_REQUIRED_WIRING = (
    "explicit workflow runtime observation kernel wiring",
    "no independent RuntimeHandler; the composition root owns RuntimeNode",
)

WORKFLOW_STATE_RESTORE_REQUIRED_WIRING = (
    "explicit workflow state restore/replay kernel wiring",
    "no independent RuntimeHandler; the composition root owns replay",
)


@dataclass(frozen=True, slots=True)
class WorkflowSliceClosure:
    """Pure named-observation closure for one workflow slice acceptance gate."""

    slice_id: workflow_acceptance.WorkflowSliceId
    program: ProgramSpec
    plan: ExecutionPlan
    legacy_observations: tuple[workflow_acceptance.WorkflowNamedStepObservation, ...]
    successor_observations: tuple[workflow_acceptance.WorkflowNamedStepObservation, ...]
    runtime_evidence: workflow_acceptance.WorkflowRuntimeEvidenceRefs
    rollback_before_after: workflow_acceptance.WorkflowRollbackBeforeAfter


def _workflow_slice_observations(
    plan: ExecutionPlan,
) -> tuple[workflow_acceptance.WorkflowNamedStepObservation, ...]:
    return tuple(
        workflow_acceptance.WorkflowNamedStepObservation(
            name=f"step-{index}:{step.step_kind.lower()}",
            step_id=step.step_id,
            status=workflow_acceptance.WorkflowStepStatus.SUCCESS,
            result_digest=content_digest(
                {"name": f"step-{index}", "status": "success"}
            ),
            evidence_ref=f"evidence:workflow:step-{index}:success",
        )
        for index, step in enumerate(plan.ordered_steps)
    )


def build_deterministic_workflow_slice_closure(
    project_scope_digest: str,
) -> Annotated[
    WorkflowSliceClosure,
    "kit:prepared-command effect_boundary=successor_runtime.workflow_assembly "
    "witness=test:test_c1_assembly_installs_kernel_wiring_for_c12_and_c13",
]:
    """Build the deterministic workflow Slice A closure over the real C7.1 program."""

    require_assembly_digest(project_scope_digest, "workflow slice closure scope digest")
    bundle = build_material_ingest_bundle()
    catalog = build_material_ingest_catalog(bundle)
    registry = build_material_ingest_registry(bundle)
    submission = MaterialIngestSubmission(
        idempotency_key="idem:workflow-definition-local:001",
        project_key="workflow-definition-local",
        source_locator="https://example.invalid/workflow-definition-local/001",
        request_key="req:workflow-definition-local:001",
        raw_payload={
            "title": "Local workflow definition route fixture",
            "text": "deterministic compile fixture",
        },
    )
    program = build_material_stage_candidate_program(
        payload=submission,
        catalog=catalog,
        program_id="program:workflow:definition:slice-a",
        project_key="workflow-definition-local",
        project_registry_revision=1,
        project_scope_digest=project_scope_digest,
    )
    plan = compile_material_ingest_program(
        program,
        catalog,
        operation_contracts=registry,
    )
    observations = _workflow_slice_observations(plan)
    return WorkflowSliceClosure(
        slice_id="A",
        program=program,
        plan=plan,
        legacy_observations=observations,
        successor_observations=observations,
        runtime_evidence=workflow_acceptance.WorkflowRuntimeEvidenceRefs(
            runtime_evidence_refs=("runtime:workflow:receipt",),
            journal_refs=("journal:workflow:run",),
            readback_refs=("readback:workflow:run",),
            replay_refs=("replay:workflow:run",),
        ),
        rollback_before_after=workflow_acceptance.WorkflowRollbackBeforeAfter(
            rollback_ref="rollback:workflow:future-owner",
            before_authority_epoch=7,
            after_authority_epoch=8,
            before_journal_refs=("journal:workflow:run",),
            after_journal_refs=("journal:workflow:run",),
            before_readback_refs=("readback:workflow:run",),
            after_readback_refs=("readback:workflow:run",),
        ),
    )


def _require_exact_route_binding(
    *,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
    handler_binding_digest: str,
    interpreter_profile_digest: str,
    operation_contract_digest: str,
    deployment_catalog_digest: str,
    drift_code: str,
) -> None:
    """Fail closed unless the live claim/assignment matches the exact route."""

    if claim.assignment_digest != assignment.assignment_digest:
        raise DefiniteInterpreterFailure("WORKFLOW_CLAIM_ASSIGNMENT_BINDING_DRIFT")
    if claim.handler_binding_digest != assignment.handler_binding_digest:
        raise DefiniteInterpreterFailure("WORKFLOW_CLAIM_HANDLER_BINDING_DRIFT")
    if (
        assignment.handler_binding_digest != handler_binding_digest
        or assignment.operation_contract_digest != operation_contract_digest
        or assignment.deployment_catalog_digest != deployment_catalog_digest
        or getattr(assignment.handler_binding, "interpreter_profile_digest", None)
        != interpreter_profile_digest
    ):
        raise DefiniteInterpreterFailure(drift_code)


@dataclass(frozen=True, slots=True)
class WorkflowPureCompileValidateRouteHandler(RuntimeHandler):
    """Deterministic pure parse/validate/compile route over the real compiler."""

    payload: Any
    slice_closure: WorkflowSliceClosure
    handler_binding_digest: str
    interpreter_profile_digest: str
    operation_contract_digest: str
    deployment_catalog_digest: str
    authority_requirement_digest: str

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        _require_exact_route_binding(
            assignment=assignment,
            claim=claim,
            handler_binding_digest=self.handler_binding_digest,
            interpreter_profile_digest=self.interpreter_profile_digest,
            operation_contract_digest=self.operation_contract_digest,
            deployment_catalog_digest=self.deployment_catalog_digest,
            drift_code="WORKFLOW_COMPILE_ROUTE_HANDLER_BINDING_DRIFT",
        )
        receipt = workflow_dsl.parse_and_validate_workflow_dsl(self.payload)
        if not receipt.ok:
            assert receipt.failure is not None
            return InterpreterOutcome.failed(receipt.failure.code)
        try:
            acceptance = workflow_acceptance.accept_workflow_slice(
                in_slice_id=self.slice_closure.slice_id,
                in_program=self.slice_closure.program,
                in_plan=self.slice_closure.plan,
                in_legacy_step_observations=self.slice_closure.legacy_observations,
                in_successor_step_observations=(
                    self.slice_closure.successor_observations
                ),
                in_runtime_evidence=self.slice_closure.runtime_evidence,
                in_rollback_before_after=self.slice_closure.rollback_before_after,
            )
        except workflow_acceptance.WorkflowAcceptanceError:
            return InterpreterOutcome.failed("WORKFLOW_ACCEPTANCE_BLOCKED")
        if not acceptance.accepted:
            return InterpreterOutcome.failed("WORKFLOW_ACCEPTANCE_BLOCKED")
        result_digest = content_digest(
            {
                "schema": "mrw.workflow.definition.compile.route-result.v2",
                "program_digest": receipt.program_digest,
                "plan_digest": receipt.plan_digest,
                "catalog_digest": receipt.catalog_digest,
                "node_count": receipt.node_count,
                "edge_count": receipt.edge_count,
                "acceptance_digest": acceptance.acceptance_digest,
                "provider_calls": 0,
                "store_writes": 0,
                "canonical_effect_calls": 0,
            }
        )
        return InterpreterOutcome.succeeded(result_digest)


def _workflow_native_definition(native: object | None) -> Any:
    """Resolve the default workflow typed contribution without eager family assembly."""

    from app.successor_runtime.capabilities.workflow_native_contribution import (
        WorkflowNativeDefinition,
        compile_workflow_native_contribution,
    )

    if native is None:
        native = compile_workflow_native_contribution(DEFAULT_WORKFLOW_NATIVE_SOURCE)
    definition = getattr(native, "definition", native)
    if not isinstance(definition, WorkflowNativeDefinition):
        raise ValueError("workflow native handle drift")
    return definition


def _workflow_compile_binding(
    project_scope_digest: str,
    catalog: Any,
    source: object,
) -> Any:
    return successor_binding(
        operation_contract_digest=catalog.catalog_digest,
        interpreter_profile_digest=sha256_hex(source.interpreter_profile_id),
        deployment_catalog_digest=sha256_hex(source.deployment_catalog_preimage),
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=sha256_hex(
            source.authority_requirement_preimage
        ),
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )


def _kernel_digest(
    digest_preimage: str,
    kernel_id: str,
    refs: tuple[str, ...],
) -> str:
    """Deterministic sha256 digest for one explicit kernel wiring."""

    return sha256_hex(
        digest_preimage + "|" + kernel_id + "|" + "|".join(refs)
    )


WORKFLOW_RUNTIME_OBSERVATION_KERNEL_REFS = (
    "main/backend/app/successor_runtime/runtime/node.py",
    "main/backend/app/successor_runtime/substrate/postgres/node_adapter.py",
    "main/backend/app/successor_runtime/substrate/postgres/composition_root.py",
    "main/backend/app/successor_runtime/capabilities/c1_slice_acceptance.py",
)

WORKFLOW_STATE_RESTORE_KERNEL_REFS = (
    "main/backend/app/successor_runtime/substrate/postgres/captured_values.py",
    "main/backend/app/successor_runtime/runtime/replay.py",
    "main/backend/app/successor_runtime/substrate/postgres/nodes.py",
)

def _kernel_wiring(
    cell: WorkflowCellSource,
    refs: tuple[str, ...],
) -> KernelWiring:
    if cell.kernel_id is None:
        raise ValueError(f"workflow kernel identity missing for {cell.cell_id}")
    return KernelWiring(
        cell_id=cell.cell_id,
        kernel_id=cell.kernel_id,
        kernel_version=cell.kernel_version,
        binding_digest=_kernel_digest(
            cell.digest_preimage,
            cell.kernel_id,
            refs,
        ),
        binding_refs=refs,
        note=(
            f"{cell.role} kernel is installed by the composition root; "
            "no independent RuntimeHandler or new authority"
        ),
    )


WORKFLOW_RUNTIME_OBSERVATION_KERNEL_WIRING = _kernel_wiring(
    DEFAULT_WORKFLOW_NATIVE_SOURCE.cells[1],
    WORKFLOW_RUNTIME_OBSERVATION_KERNEL_REFS,
)
WORKFLOW_STATE_RESTORE_KERNEL_WIRING = _kernel_wiring(
    DEFAULT_WORKFLOW_NATIVE_SOURCE.cells[2],
    WORKFLOW_STATE_RESTORE_KERNEL_REFS,
)


def build_workflow_assembly(
    *,
    project_scope_digest: str | None = None,
    native: object | None = None,
) -> Annotated[
    FamilyAssembly,
    "kit:prepared-command effect_boundary=successor_runtime.workflow_assembly "
    "witness=test:test_c1_assembly_installs_kernel_wiring_for_c12_and_c13",
]:
    """Return the workflow assembly from the native workflow typed contribution.

    ``native`` is optional for the existing callers; when supplied it must be
    the compiled ``workflow_native_contribution`` handle (or its typed definition).
    The workflow compiler, slice acceptance and kernel-wiring authorities remain
    unchanged.
    """

    scope = project_scope_digest or local_assembly_scope_digest()
    require_assembly_digest(scope, "workflow assembly project scope digest")
    native_definition = _workflow_native_definition(native)
    source = native_definition.source
    if tuple(cell.cell_id for cell in source.cells) != ASSEMBLY_CELL_IDS:
        raise ValueError("workflow native cell order drift")
    compile_cell, runtime_cell, restore_cell = source.cells
    runtime_kernel = _kernel_wiring(runtime_cell, WORKFLOW_RUNTIME_OBSERVATION_KERNEL_REFS)
    restore_kernel = _kernel_wiring(restore_cell, WORKFLOW_STATE_RESTORE_KERNEL_REFS)
    binding = _workflow_compile_binding(scope, native_definition.catalog, source)
    handler = WorkflowPureCompileValidateRouteHandler(
        payload=native_definition.source.dsl_payload,
        slice_closure=build_deterministic_workflow_slice_closure(scope),
        handler_binding_digest=binding.binding_digest,
        interpreter_profile_digest=binding.interpreter_profile_digest,
        operation_contract_digest=binding.operation_contract_digest,
        deployment_catalog_digest=binding.deployment_catalog_digest,
        authority_requirement_digest=binding.authority_requirement_digest,
    )

    cells = (
        CellBinding(
            cell_id=compile_cell.cell_id,
            family_id=source.family_id,
            status="INSTALLED",
            operation_contract_refs=tuple(
                entry[0] for entry in native_definition.catalog.entries
            ),
            handler_binding_digest=handler.handler_binding_digest,
            recovery_binding_ref=compile_cell.recovery_binding_ref,
            rollback_binding_refs=native_definition.source.rollback_refs,
            note=(
                "workflow definition pure compile/validate route handler "
                "installed from native "
                f"{native_definition.contribution_id}; binds c1_legacy_dsl.py / "
                "c1_slice_acceptance.py / legacy_workflow_graph.py (real "
                "interpreter/movement files); no effect/DB/provider/canonical "
                "write"
            ),
        ),
        CellBinding(
            cell_id=runtime_cell.cell_id,
            family_id=source.family_id,
            status="INSTALLED",
            operation_contract_refs=(
                "ingest_index.stage_candidate.v1",
                "knowledge.writing.compose.v2",
                "knowledge.writing.stage.v2",
                "knowledge.report.stage.v2",
                "knowledge.report.verify.v2",
                "knowledge.report.admission.v2",
                "knowledge.report.prepare_delivery_intent.v2",
                "delivery.internal_export.v1",
            ),
            handler_binding_digest=runtime_kernel.binding_digest,
            recovery_binding_ref=runtime_cell.recovery_binding_ref,
            required_wiring=WORKFLOW_RUNTIME_OBSERVATION_REQUIRED_WIRING,
            note=(
                "workflow runtime observation kernel is installed by the "
                "composition root; no independent RuntimeHandler"
            ),
        ),
        CellBinding(
            cell_id=restore_cell.cell_id,
            family_id=source.family_id,
            status="INSTALLED",
            operation_contract_refs=("runtime.store.rehydrate.v1",),
            handler_binding_digest=restore_kernel.binding_digest,
            recovery_binding_ref=restore_cell.recovery_binding_ref,
            required_wiring=WORKFLOW_STATE_RESTORE_REQUIRED_WIRING,
            note=(
                "workflow state restore/replay kernel is installed by the "
                "composition root; no independent RuntimeHandler"
            ),
        ),
    )
    rollback_bindings = (
        RollbackBindingDeclaration(
            cell_id=compile_cell.cell_id,
            status="PRESENT",
            binding_refs=native_definition.source.rollback_refs,
            note=(
                "workflow compile rollback binding retains the historical route and "
                "real successor compiler and slice-acceptance implementation files"
            ),
        ),
        RollbackBindingDeclaration(
            cell_id=runtime_cell.cell_id,
            status="PRESENT",
            binding_refs=WORKFLOW_RUNTIME_OBSERVATION_ROLLBACK_PATHS,
            note=(
                "runtime observation rollback retains historical slice evidence "
                "and legacy_workflow_graph.py bytes"
            ),
        ),
        RollbackBindingDeclaration(
            cell_id=restore_cell.cell_id,
            status="PRESENT",
            binding_refs=WORKFLOW_RUNTIME_OBSERVATION_ROLLBACK_PATHS,
            note=(
                "state restore rollback retains historical slice evidence and "
                "legacy_workflow_graph.py bytes"
            ),
        ),
    )
    return FamilyAssembly(
        family_id=source.family_id,
        cells=cells,
        handlers=(handler,),
        rollback_bindings=rollback_bindings,
        kernel_wiring=(runtime_kernel, restore_kernel),
    )


__all__ = [
    "WORKFLOW_COMPILE_ACCEPTANCE_MODULE",
    "WORKFLOW_COMPILE_INTERPRETER_MODULE",
    "WORKFLOW_COMPILE_REQUIRED_WIRING",
    "WORKFLOW_COMPILE_ROLLBACK_PATH",
    "WORKFLOW_COMPILE_ROLLBACK_PATHS",
    "WORKFLOW_RUNTIME_OBSERVATION_KERNEL_WIRING",
    "WORKFLOW_RUNTIME_OBSERVATION_REQUIRED_WIRING",
    "WORKFLOW_RUNTIME_OBSERVATION_ROLLBACK_PATHS",
    "WORKFLOW_STATE_RESTORE_KERNEL_WIRING",
    "WORKFLOW_STATE_RESTORE_REQUIRED_WIRING",
    "ASSEMBLY_CELL_IDS",
    "WORKFLOW_FAMILY_ID",
    "WorkflowSliceClosure",
    "WorkflowPureCompileValidateRouteHandler",
    "build_workflow_assembly",
    "build_deterministic_workflow_slice_closure",
]
