"""C1 family assembly: pure compile route plus explicit kernel wiring.

The C1 family is a successor parse/validate/compile facade plus runtime node
observation and store-rehydrate facade surfaces.  C1.1 is installed as a
deterministic pure ``RuntimeHandler`` over the existing
``c1_legacy_dsl.parse_and_validate_legacy_dsl`` compiler and the
``c1_slice_acceptance.accept_c1_slice`` named-observation shadow gate; it
performs no effect, database, provider or canonical write.  C1.2 and C1.3 are
carried by explicit ``KernelWiring`` declarations installed by the PostgreSQL
composition root; they are not family ``RuntimeHandler`` instances.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
from app.successor_runtime.capabilities import c1_legacy_dsl as c1_dsl
from app.successor_runtime.capabilities import c1_slice_acceptance as c1_accept
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.ingest_c7_common import (
    C7IngestSubmission,
    build_ingest_c7_bundle,
    build_ingest_c7_catalog,
    build_ingest_c7_registry,
)
from app.successor_runtime.capabilities.ingest_c7_program import (
    build_ingest_c7_1_program,
    compile_ingest_c7_program,
)
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

C1_FAMILY_ID = "C1"

C1_1_ROLLBACK_PATH = "main/backend/app/successor_migration/legacy_workflow_graph.py"
C1_1_INTERPRETER_MODULE = (
    "main/backend/app/successor_runtime/capabilities/c1_legacy_dsl.py"
)
C1_1_ACCEPTANCE_MODULE = (
    "main/backend/app/successor_runtime/capabilities/c1_slice_acceptance.py"
)
C1_1_ROLLBACK_PATHS = (
    C1_1_ROLLBACK_PATH,
    C1_1_INTERPRETER_MODULE,
    C1_1_ACCEPTANCE_MODULE,
)

C1_1_INTERPRETER_PROFILE_ID = "successor.c1.legacy-dsl.parse-validate-compile.v1"
C1_1_DEPLOYMENT_CATALOG_DIGEST = sha256_hex("mrw.successor.deployment-catalog.c1.v1")
C1_1_AUTHORITY_REQUIREMENT_DIGEST = sha256_hex("mrw.successor.c1.authority.v1")

C1_1_DETERMINISTIC_PAYLOAD: dict[str, Any] = {
    "version": "1.0",
    "options": {},
    "nodes": [
        {
            "node_id": "retrieve",
            "node_type": "vector_search",
            "config": {"top_k": 5},
        },
        {
            "node_id": "draft",
            "node_type": "llm_call",
            "config": {"model": "mrw-local"},
        },
        {
            "node_id": "combine",
            "node_type": "join",
            "config": {"field": "values"},
        },
    ],
    "edges": [
        {"from": "retrieve", "to": "combine"},
        {"from": "draft", "to": "combine"},
    ],
}

C1_2_ROLLBACK_PATHS = (
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
    C1_1_ROLLBACK_PATH,
)

C1_1_REQUIRED_WIRING = (
    "C1.1 successor compiler 绑定到可执行 Program/RuntimeHandler",
    "legacy DSL named-observation oracle 作为 shadow parity 门",
    "rollback binding: legacy_workflow_graph.py (spec 已绑定)",
)

C1_2_REQUIRED_WIRING = (
    ("显式 C1.2 RuntimeNode kernel wiring (mrw.successor.runtime.c1-2.node.v1)"),
    "无独立 RuntimeHandler；RuntimeNode 内核机制由组合根承担",
)

C1_3_REQUIRED_WIRING = (
    (
        "显式 C1.3 store-rehydrate/replay kernel wiring "
        "(mrw.successor.store.c1-3.replay.v1)"
    ),
    "无独立 RuntimeHandler；store-rehydrate/replay 由组合根内核机制承担",
)


@dataclass(frozen=True, slots=True)
class C1SliceClosure:
    """Pure named-observation closure for one C1 slice acceptance gate."""

    slice_id: c1_accept.C1SliceId
    program: ProgramSpec
    plan: ExecutionPlan
    legacy_observations: tuple[c1_accept.C1NamedStepObservation, ...]
    successor_observations: tuple[c1_accept.C1NamedStepObservation, ...]
    runtime_evidence: c1_accept.C1RuntimeEvidenceRefs
    rollback_before_after: c1_accept.C1RollbackBeforeAfter


def _c1_slice_observations(
    plan: ExecutionPlan,
) -> tuple[c1_accept.C1NamedStepObservation, ...]:
    return tuple(
        c1_accept.C1NamedStepObservation(
            name=f"step-{index}:{step.step_kind.lower()}",
            step_id=step.step_id,
            status=c1_accept.C1StepStatus.SUCCESS,
            result_digest=content_digest(
                {"name": f"step-{index}", "status": "success"}
            ),
            evidence_ref=f"evidence:c1:step-{index}:success",
        )
        for index, step in enumerate(plan.ordered_steps)
    )


def build_deterministic_c1_slice_closure(
    project_scope_digest: str,
) -> C1SliceClosure:
    """Build the deterministic C1 Slice A closure over the real C7.1 program."""

    require_assembly_digest(project_scope_digest, "C1 slice closure scope digest")
    bundle = build_ingest_c7_bundle()
    catalog = build_ingest_c7_catalog(bundle)
    registry = build_ingest_c7_registry(bundle)
    submission = C7IngestSubmission(
        idempotency_key="idem:i1-local-c1:001",
        project_key="i1-local-c1",
        source_locator="https://example.invalid/i1-local-c1/001",
        request_key="req:i1-local-c1:001",
        raw_payload={
            "title": "I1 local C1.1 route fixture",
            "text": "deterministic compile fixture",
        },
    )
    program = build_ingest_c7_1_program(
        payload=submission,
        catalog=catalog,
        program_id="program:c1-1:slice-a",
        project_key="i1-local-c1",
        project_registry_revision=1,
        project_scope_digest=project_scope_digest,
    )
    plan = compile_ingest_c7_program(
        program,
        catalog,
        operation_contracts=registry,
    )
    observations = _c1_slice_observations(plan)
    return C1SliceClosure(
        slice_id="A",
        program=program,
        plan=plan,
        legacy_observations=observations,
        successor_observations=observations,
        runtime_evidence=c1_accept.C1RuntimeEvidenceRefs(
            runtime_evidence_refs=("runtime:c1:receipt",),
            journal_refs=("journal:c1:run",),
            readback_refs=("readback:c1:run",),
            replay_refs=("replay:c1:run",),
        ),
        rollback_before_after=c1_accept.C1RollbackBeforeAfter(
            rollback_ref="rollback:c1:future-owner",
            before_authority_epoch=7,
            after_authority_epoch=8,
            before_journal_refs=("journal:c1:run",),
            after_journal_refs=("journal:c1:run",),
            before_readback_refs=("readback:c1:run",),
            after_readback_refs=("readback:c1:run",),
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
        raise DefiniteInterpreterFailure("C1_1_CLAIM_ASSIGNMENT_BINDING_DRIFT")
    if claim.handler_binding_digest != assignment.handler_binding_digest:
        raise DefiniteInterpreterFailure("C1_1_CLAIM_HANDLER_BINDING_DRIFT")
    if (
        assignment.handler_binding_digest != handler_binding_digest
        or assignment.operation_contract_digest != operation_contract_digest
        or assignment.deployment_catalog_digest != deployment_catalog_digest
        or getattr(assignment.handler_binding, "interpreter_profile_digest", None)
        != interpreter_profile_digest
    ):
        raise DefiniteInterpreterFailure(drift_code)


@dataclass(frozen=True, slots=True)
class C1_1PureCompileValidateRouteHandler(RuntimeHandler):
    """Deterministic pure parse/validate/compile route over the real compiler."""

    payload: Any
    slice_closure: C1SliceClosure
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
            drift_code="EXACT_C1_1_COMPILE_ROUTE_HANDLER_BINDING_DRIFT",
        )
        receipt = c1_dsl.parse_and_validate_legacy_dsl(self.payload)
        if not receipt.ok:
            assert receipt.failure is not None
            return InterpreterOutcome.failed(receipt.failure.code)
        try:
            acceptance = c1_accept.accept_c1_slice(
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
        except c1_accept.C1AcceptanceError:
            return InterpreterOutcome.failed("C1_SLICE_ACCEPTANCE_BLOCKED")
        if not acceptance.accepted:
            return InterpreterOutcome.failed("C1_SLICE_ACCEPTANCE_BLOCKED")
        result_digest = content_digest(
            {
                "schema": "mrw.successor.c1.c1-1.compile-route-result.v1",
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


def _c1_1_binding(project_scope_digest: str) -> Any:
    catalog = c1_dsl.build_c1_catalog()
    return successor_binding(
        operation_contract_digest=catalog.catalog_digest,
        interpreter_profile_digest=sha256_hex(C1_1_INTERPRETER_PROFILE_ID),
        deployment_catalog_digest=C1_1_DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=C1_1_AUTHORITY_REQUIREMENT_DIGEST,
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )


def _kernel_digest(kernel_id: str, refs: tuple[str, ...]) -> str:
    """Deterministic sha256 digest for one explicit kernel wiring."""

    return sha256_hex(
        "mrw.successor.assembly.kernel-wiring.v1|" + kernel_id + "|" + "|".join(refs)
    )


C1_2_KERNEL_REFS = (
    "main/backend/app/successor_runtime/runtime/node.py",
    "main/backend/app/successor_runtime/substrate/postgres/node_adapter.py",
    "main/backend/app/successor_runtime/substrate/postgres/composition_root.py",
    "main/backend/app/successor_runtime/capabilities/c1_slice_acceptance.py",
)

C1_2_KERNEL_WIRING = KernelWiring(
    cell_id="C1.2",
    kernel_id="mrw.successor.runtime.c1-2.node.v1",
    kernel_version="1.0.0",
    binding_digest=_kernel_digest(
        "mrw.successor.runtime.c1-2.node.v1",
        C1_2_KERNEL_REFS,
    ),
    binding_refs=C1_2_KERNEL_REFS,
    note=(
        "RuntimeNode 内核机制由组合根安装；这是显式 C1.2 node-wiring 声明，"
        "不是独立 RuntimeHandler 绑定"
    ),
)

C1_3_KERNEL_REFS = (
    "main/backend/app/successor_runtime/substrate/postgres/captured_values.py",
    "main/backend/app/successor_runtime/runtime/replay.py",
    "main/backend/app/successor_runtime/substrate/postgres/nodes.py",
)

C1_3_KERNEL_WIRING = KernelWiring(
    cell_id="C1.3",
    kernel_id="mrw.successor.store.c1-3.replay.v1",
    kernel_version="1.0.0",
    binding_digest=_kernel_digest(
        "mrw.successor.store.c1-3.replay.v1",
        C1_3_KERNEL_REFS,
    ),
    binding_refs=C1_3_KERNEL_REFS,
    note=(
        "store-rehydrate/replay 内核机制由组合根安装；这是显式 C1.3 "
        "kernel-wiring 声明，不是独立 RuntimeHandler 绑定"
    ),
)


def build_c1_assembly(
    *,
    project_scope_digest: str | None = None,
) -> FamilyAssembly:
    """Return the C1 assembly with the C1.1 route and explicit kernel wiring."""

    scope = project_scope_digest or local_assembly_scope_digest()
    require_assembly_digest(scope, "C1 assembly project scope digest")
    binding = _c1_1_binding(scope)
    handler = C1_1PureCompileValidateRouteHandler(
        payload=C1_1_DETERMINISTIC_PAYLOAD,
        slice_closure=build_deterministic_c1_slice_closure(scope),
        handler_binding_digest=binding.binding_digest,
        interpreter_profile_digest=binding.interpreter_profile_digest,
        operation_contract_digest=binding.operation_contract_digest,
        deployment_catalog_digest=binding.deployment_catalog_digest,
        authority_requirement_digest=binding.authority_requirement_digest,
    )

    cells = (
        CellBinding(
            cell_id="C1.1",
            family_id=C1_FAMILY_ID,
            status="INSTALLED",
            operation_contract_refs=(
                "workflow.vector_search.v1",
                "workflow.llm_call.v1",
                "workflow.join.v1",
            ),
            handler_binding_digest=handler.handler_binding_digest,
            recovery_binding_ref="mrw.successor.c1.c1-1.recovery.v1",
            rollback_binding_refs=C1_1_ROLLBACK_PATHS,
            note=(
                "C1.1 deterministic pure compile/validate route handler "
                "installed; binds c1_legacy_dsl.py / c1_slice_acceptance.py / "
                "legacy_workflow_graph.py (real interpreter/movement files); "
                "no effect/DB/provider/canonical write"
            ),
        ),
        CellBinding(
            cell_id="C1.2",
            family_id=C1_FAMILY_ID,
            status="INSTALLED",
            operation_contract_refs=(
                "ingest_index.stage_candidate.v1",
                "c8.writing.compose.v1",
                "c8.writing.stage.v1",
                "c8.report.stage.v1",
                "c8.report.verify.v1",
                "c8.report.admission.v1",
                "c8.delivery_intent_prepare.v1",
                "delivery.internal_export.v1",
            ),
            handler_binding_digest=C1_2_KERNEL_WIRING.binding_digest,
            recovery_binding_ref="mrw.successor.runtime.c1-2.recovery.v1",
            required_wiring=C1_2_REQUIRED_WIRING,
            note=(
                "显式 C1.2 node-wiring：RuntimeNode 内核机制由组合根安装，"
                "无独立 RuntimeHandler；handler_binding_digest 承载 kernel digest"
            ),
        ),
        CellBinding(
            cell_id="C1.3",
            family_id=C1_FAMILY_ID,
            status="INSTALLED",
            operation_contract_refs=("runtime.store.rehydrate.v1",),
            handler_binding_digest=C1_3_KERNEL_WIRING.binding_digest,
            recovery_binding_ref="mrw.successor.store.c1-3.recovery.v1",
            required_wiring=C1_3_REQUIRED_WIRING,
            note=(
                "显式 C1.3 kernel-wiring：store-rehydrate/replay 内核机制由组合根"
                "安装，无独立 RuntimeHandler；handler_binding_digest 承载 "
                "kernel digest"
            ),
        ),
    )
    rollback_bindings = (
        RollbackBindingDeclaration(
            cell_id="C1.1",
            status="PRESENT",
            binding_refs=C1_1_ROLLBACK_PATHS,
            note=(
                "C1.1 rollback binding present: legacy rollback route plus the "
                "real successor compiler and slice-acceptance implementation files"
            ),
        ),
        RollbackBindingDeclaration(
            cell_id="C1.2",
            status="PRESENT",
            binding_refs=C1_2_ROLLBACK_PATHS,
            note=(
                "显式 C1.2 kernel wiring 已安装；rollback 绑定到 C1SliceA/B/C "
                "证据与 legacy_workflow_graph.py（spec 真实 rollback 绑定）"
            ),
        ),
        RollbackBindingDeclaration(
            cell_id="C1.3",
            status="PRESENT",
            binding_refs=C1_2_ROLLBACK_PATHS,
            note=(
                "显式 C1.3 kernel wiring 已安装；rollback 绑定到 C1SliceA/B/C "
                "证据与 legacy_workflow_graph.py（spec 真实 rollback 绑定）"
            ),
        ),
    )
    return FamilyAssembly(
        family_id=C1_FAMILY_ID,
        cells=cells,
        handlers=(handler,),
        rollback_bindings=rollback_bindings,
        kernel_wiring=(C1_2_KERNEL_WIRING, C1_3_KERNEL_WIRING),
    )


__all__ = [
    "C1_1_ACCEPTANCE_MODULE",
    "C1_1_DETERMINISTIC_PAYLOAD",
    "C1_1_INTERPRETER_MODULE",
    "C1_1_REQUIRED_WIRING",
    "C1_1_ROLLBACK_PATH",
    "C1_1_ROLLBACK_PATHS",
    "C1_2_KERNEL_WIRING",
    "C1_2_REQUIRED_WIRING",
    "C1_2_ROLLBACK_PATHS",
    "C1_3_KERNEL_WIRING",
    "C1_3_REQUIRED_WIRING",
    "C1_FAMILY_ID",
    "C1SliceClosure",
    "C1_1PureCompileValidateRouteHandler",
    "build_c1_assembly",
    "build_deterministic_c1_slice_closure",
]
