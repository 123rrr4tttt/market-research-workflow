"""C7 family assembly: explicit pure rollback-route and successor write wiring.

C7.1-C7.4 are installed only when the caller supplies the exact deterministic
route closure in :class:`MaterialIngestAssemblyOptions`.  Every installed route is a pure
RuntimeHandler over the existing ``ingest_c7_interpreters`` programs; it never
touches a database, index, graph, provider or canonical writer.  When a route
closure is absent the cell stays ``UNWIRED_DECLARED`` and its rollback binding
stays ``DECLARED_GAP`` with the missing options field and authority boundary
listed exactly.

C7.2 additionally installs a real successor-only canonical commit-write
handler when the caller supplies :class:`C7CanonicalWriteClosure`; C7.3
installs the successor-only projector driver when it supplies
:class:`C7ProjectorDriverClosure`.  Those real handlers register in the
family assembly with rollback ``PRESENT`` and never touch legacy tables,
providers, exports or live cutover.

The ingest-c7 capability bundle currently registers only the C7.1 stage
contract.  For C7.2-C7.4 the operation-contract digest is therefore a
deterministic assembly-scope digest over the declared contract kind, not a
production catalog digest; this is stated in each installed cell note.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from sqlalchemy.engine import Connection

from app.successor_runtime.assembly.base import (
    PROJECTOR_REGISTRY_INCARNATION,
    MaterialIngestAssemblyOptions,
    CellBinding,
    FamilyAssembly,
    ProjectorContract,
    ProjectorKey,
    ProjectorRegistry,
    RollbackBindingDeclaration,
    local_assembly_scope_digest,
    require_assembly_digest,
    sha256_hex,
    successor_binding,
)
from app.successor_runtime.capabilities.checksum import canonical_json, content_digest
from app.successor_runtime.capabilities.material_native_contribution import (
    ASSEMBLY_CELL_IDS as AUTHOR_ASSEMBLY_CELL_IDS,
    DEFAULT_MATERIAL_NATIVE_SOURCE,
    MATERIAL_COMMIT_READBACK_CELL_ID,
    MATERIAL_PROJECTION_DIFF_CELL_ID,
    MATERIAL_RECONCILIATION_CELL_ID,
    MATERIAL_STAGE_CANDIDATE_CELL_ID,
)
from app.successor_runtime.capabilities.material_ingest_common import (
    MATERIAL_COMMIT_INTENT_CONTRACT_ID,
    MATERIAL_PROJECTION_DIFF_CONTRACT_ID,
    MATERIAL_READBACK_RECONCILIATION_CONTRACT_ID,
    MATERIAL_STAGE_CANDIDATE_KIND,
    MaterialIngestSubmission,
    MaterialReconciliationDecision,
    ProjectionDiff,
    build_material_ingest_bundle,
    build_material_ingest_catalog,
)
from app.successor_runtime.capabilities.material_ingest_interpreters import (
    MATERIAL_INTERPRETER_PROFILE_IDS,
    MaterialInterpreterSuccess,
    interpret_commit_readback,
    interpret_projection_diff,
    interpret_reconciliation,
    interpret_staged_candidate,
)
from app.successor_runtime.capabilities.material_ingest_movements import (
    RawSnapshot,
    StructuredMaterialCandidate,
    VerifiedMaterialCandidate,
    return_for_cleanup,
)
from app.successor_runtime.runtime.admission import VerificationBinding
from app.successor_runtime.runtime.assignments import RuntimeAssignment
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres.c7_canonical_write import (
    C7CanonicalWritePort,
    C7MovementAdmissionError,
)
from app.successor_runtime.substrate.postgres.c7_projector_driver import (
    MATERIAL_CANONICAL_SOURCE_KIND,
    MATERIAL_GRAPH_PROJECTION_SCHEMA,
    MATERIAL_GRAPH_PROJECTOR_ID,
    MATERIAL_GRAPH_PROJECTOR_VERSION,
    MATERIAL_SEARCH_PROJECTION_SCHEMA,
    MATERIAL_SEARCH_PROJECTOR_ID,
    MATERIAL_SEARCH_PROJECTOR_VERSION,
    C7ProjectorDriver,
    C7ProjectorDriverError,
    c7_graph_declared_loss,
    c7_search_declared_loss,
    MATERIAL_GRAPH_PROJECTION_ID,
    MATERIAL_SEARCH_PROJECTION_ID,
)
from app.successor_runtime.substrate.postgres.ingest_c7_movement_admission import (
    C7AdmissionConfig,
)
from app.successor_runtime.substrate.postgres.ingest_c7_registry_handler import (
    C7IngestRegistryRuntimeHandler,
)
from app.successor_runtime.substrate.projections.registry import RebuildMode

MATERIAL_INGEST_FAMILY_ID = "mrw.material.ingest"

MATERIAL_INGEST_DEPLOYMENT_CATALOG_DIGEST = sha256_hex("mrw.material.deployment-catalog.v2")
MATERIAL_INGEST_AUTHORITY_REQUIREMENT_DIGEST = content_digest(
    (
        DEFAULT_MATERIAL_NATIVE_SOURCE.canonical_writer_ref,
        DEFAULT_MATERIAL_NATIVE_SOURCE.production_admission_ref,
        DEFAULT_MATERIAL_NATIVE_SOURCE.projector_driver_ref,
    )
)
_MATERIAL_INGEST_REGISTRY_OPERATION_REF = "material.ingest.submission-registry.lifecycle.v2"
_MATERIAL_INGEST_REGISTRY_OPERATION_DIGEST = sha256_hex(
    "mrw.material.ingest.submission-registry.operation.v2"
)
_MATERIAL_INGEST_REGISTRY_INTERPRETER_DIGEST = sha256_hex(
    "material.ingest.submission-registry.v2"
)
_MATERIAL_INGEST_REGISTRY_AUTHORITY_DIGEST = sha256_hex(
    "mrw.material.ingest.submission-registry.authority.v2"
)

_MATERIAL_INTERPRETERS_MODULE = (
    "main/backend/app/successor_runtime/capabilities/material_ingest_interpreters.py"
)
_MATERIAL_COMMON_MODULE = (
    "main/backend/app/successor_runtime/capabilities/material_ingest_common.py"
)
_MATERIAL_MOVEMENTS_MODULE = (
    "main/backend/app/successor_runtime/capabilities/material_ingest_movements.py"
)
_MATERIAL_RECONCILIATION_MODULE = (
    "main/backend/app/successor_runtime/runtime/reconciliation.py"
)
_MATERIAL_CANONICAL_WRITE_MODULE = (
    "main/backend/app/successor_runtime/substrate/postgres/c7_canonical_write.py"
)
_MATERIAL_ADMISSION_MODULE = (
    "main/backend/app/successor_runtime/substrate/postgres/"
    "ingest_c7_movement_admission.py"
)
_MATERIAL_PROJECTOR_DRIVER_MODULE = (
    "main/backend/app/successor_runtime/substrate/postgres/c7_projector_driver.py"
)
_MATERIAL_PROJECTION_OFFSETS_MODULE = (
    "main/backend/app/successor_runtime/substrate/postgres/projection_offsets.py"
)
_MATERIAL_DOCUMENT_READBACK_MODULE = (
    "main/backend/app/successor_runtime/substrate/postgres/c7_document_readback.py"
)
_MATERIAL_INGEST_REGISTRY_CAPABILITY_MODULE = (
    "main/backend/app/successor_runtime/capabilities/material_ingest_registry.py"
)
_MATERIAL_INGEST_REGISTRY_HANDLER_MODULE = (
    "main/backend/app/successor_runtime/substrate/postgres/"
    "ingest_c7_registry_handler.py"
)

MATERIAL_INGEST_AUTHORITY_WIRING_REFS: dict[str, tuple[str, ...]] = {
    MATERIAL_STAGE_CANDIDATE_CELL_ID: (_MATERIAL_INTERPRETERS_MODULE, _MATERIAL_MOVEMENTS_MODULE),
    MATERIAL_COMMIT_READBACK_CELL_ID: (
        _MATERIAL_CANONICAL_WRITE_MODULE,
        _MATERIAL_ADMISSION_MODULE,
        _MATERIAL_DOCUMENT_READBACK_MODULE,
    ),
    MATERIAL_PROJECTION_DIFF_CELL_ID: (
        _MATERIAL_PROJECTOR_DRIVER_MODULE,
        _MATERIAL_PROJECTION_OFFSETS_MODULE,
        _MATERIAL_DOCUMENT_READBACK_MODULE,
    ),
    MATERIAL_RECONCILIATION_CELL_ID: (
        _MATERIAL_INTERPRETERS_MODULE,
        _MATERIAL_COMMON_MODULE,
        _MATERIAL_RECONCILIATION_MODULE,
    ),
}

_MATERIAL_ROUTE_OPTION_FIELDS = {
    MATERIAL_STAGE_CANDIDATE_CELL_ID: "submission",
    MATERIAL_COMMIT_READBACK_CELL_ID: "commit_readback",
    MATERIAL_PROJECTION_DIFF_CELL_ID: "projection_diff",
    MATERIAL_RECONCILIATION_CELL_ID: "reconciliation_decision",
}
_MATERIAL_ROUTE_PROFILE_KEYS = {
    MATERIAL_STAGE_CANDIDATE_CELL_ID: "staged_candidate",
    MATERIAL_COMMIT_READBACK_CELL_ID: "commit_readback",
    MATERIAL_PROJECTION_DIFF_CELL_ID: "projection_diff",
    MATERIAL_RECONCILIATION_CELL_ID: "reconciliation",
}
_MATERIAL_ROUTE_KINDS = {
    MATERIAL_STAGE_CANDIDATE_CELL_ID: MATERIAL_STAGE_CANDIDATE_KIND,
    MATERIAL_COMMIT_READBACK_CELL_ID: MATERIAL_COMMIT_INTENT_CONTRACT_ID,
    MATERIAL_PROJECTION_DIFF_CELL_ID: MATERIAL_PROJECTION_DIFF_CONTRACT_ID,
    MATERIAL_RECONCILIATION_CELL_ID: MATERIAL_READBACK_RECONCILIATION_CONTRACT_ID,
}
_MATERIAL_ROLLBACK_REFS = dict(MATERIAL_INGEST_AUTHORITY_WIRING_REFS)

MATERIAL_INGEST_CELL_SPECS: dict[
    str,
    tuple[tuple[str, ...], str, tuple[str, ...], str],
] = {
    MATERIAL_STAGE_CANDIDATE_CELL_ID: (
        ("ingest_index.stage_candidate.v1",),
        (
            "material.ingest.stage-candidate.recovery.v2#retain-staged-candidate-and-"
            "runtime-receipt;no-repeat-effect"
        ),
        (
            "material ingest assembly 与 AdmissionCoordinator 注册",
            "legacy writer 保持 zero 的适配边界",
            "document admission/canonical write 需单独 authority review",
        ),
        (
            "staged-candidate components exist; no RuntimeHandler or "
            "AdmissionCoordinator registration; canonical write authority closed"
        ),
    ),
    MATERIAL_COMMIT_READBACK_CELL_ID: (
        (
            "ingest_index.commit_intent.readback.v1",
            "ingest_index.admission.readback.v1",
        ),
        (
            "ingest_index.commit_intent.readback.v1#prepare-then-readback;"
            "no-repeat-commit;outcome-unknown-waits-for-readback"
        ),
        ("material admission 注册", "readback resource policy"),
        (
            "commit-intent/readback components exist; material admission is not "
            "registered with an AdmissionCoordinator"
        ),
    ),
    MATERIAL_PROJECTION_DIFF_CELL_ID: (
        ("ingest_index.projection_declared_loss.v1",),
        (
            "ingest_index.projection_declared_loss.v1#rebuild-from-bound-document;"
            "resume-offset-or-full-rebuild;no-canonical-mutation"
        ),
        ("material projector 注册", "projection offset 驱动"),
        (
            "projection-diff components exist; no material projector registration "
            "or projection offset driver"
        ),
    ),
    MATERIAL_RECONCILIATION_CELL_ID: (
        ("ingest_index.reconcile.readback.v1", "ingest_index.reconcile.nonstart.v1"),
        (
            "ingest_index.reconcile.nonstart.v1#exact-nonstart-proof-plus-current-"
            "authority;new-attempt-epoch-only;rollback-changes-future-routing-not-events"
        ),
        ("material reconcile handler installation", "recovery binding"),
        (
            "reconcile components exist; no material reconcile RuntimeHandler "
            "installation or recovery binding"
        ),
    ),
}

ASSEMBLY_CELL_IDS = AUTHOR_ASSEMBLY_CELL_IDS
if tuple(MATERIAL_INGEST_CELL_SPECS) != ASSEMBLY_CELL_IDS:
    raise RuntimeError("material ingest assembly specs drifted from native author cells")
MATERIAL_INGEST_ASSEMBLY_CELL_IDS = ASSEMBLY_CELL_IDS

MATERIAL_INGEST_ROLLBACK_GAP_NOTE = (
    "FC-04/I1-2026-09-02: current C7 specs list p4-fragments/C7.json only as "
    "c7_N_rollback_family_observation bindings, not as legacy rollback routes; "
    "no rollback route binding exists, so rehearsal/assembly rollback "
    "acceptance stays blocked (DECLARED_GAP)"
)

_MATERIAL_PURE_ROUTE_NOTE = (
    "纯 route 装配：真实 successor_runtime 实现模块绑定；非 p4-fragments 观察绑定"
)
_MATERIAL_PG_ROUTE_NOTE = (
    "真实 PostgreSQL 装配：successor-only 表写入；legacy/provider/export/"
    "cutover 保持关闭"
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
        raise DefiniteInterpreterFailure(
            "MATERIAL_INGEST_CLAIM_ASSIGNMENT_BINDING_DRIFT"
        )
    if claim.handler_binding_digest != assignment.handler_binding_digest:
        raise DefiniteInterpreterFailure(
            "MATERIAL_INGEST_CLAIM_HANDLER_BINDING_DRIFT"
        )
    if (
        assignment.handler_binding_digest != handler_binding_digest
        or assignment.operation_contract_digest != operation_contract_digest
        or assignment.deployment_catalog_digest != deployment_catalog_digest
        or getattr(assignment.handler_binding, "interpreter_profile_digest", None)
        != interpreter_profile_digest
    ):
        raise DefiniteInterpreterFailure(drift_code)


def _succeeded_interpreter_outcome(outcome: Any) -> InterpreterOutcome:
    if not isinstance(outcome, MaterialInterpreterSuccess):
        raise DefiniteInterpreterFailure(
            "MATERIAL_INGEST_ROLLBACK_INTERPRETER_REJECTED"
        )
    return InterpreterOutcome.succeeded(content_digest(outcome.value))


@dataclass(frozen=True, slots=True)
class MaterialStageCandidateRollbackRouteHandler(RuntimeHandler):
    """Pure staged-candidate rollback route over ``interpret_staged_candidate``."""

    submission: MaterialIngestSubmission
    handler_binding_digest: str
    interpreter_profile_digest: str
    operation_contract_digest: str
    deployment_catalog_digest: str

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
            drift_code=(
                "EXACT_MATERIAL_INGEST_STAGE_CANDIDATE_ROLLBACK_"
                "HANDLER_BINDING_DRIFT"
            ),
        )
        outcome = interpret_staged_candidate(self.submission)
        if isinstance(outcome, MaterialInterpreterSuccess):
            return InterpreterOutcome.succeeded(content_digest(outcome.value))

        # The frozen InterpreterOutcome contract forbids FAILED plus
        # reconciliation_hint, so the pure reverse-return evidence is carried
        # as an OUTCOME_UNKNOWN typed route result with both fields present.
        reverse = return_for_cleanup(
            snapshot=RawSnapshot(
                project_key=self.submission.project_key,
                source_locator=self.submission.source_locator,
                raw_bytes=canonical_json(
                    dict(self.submission.raw_payload or {})
                ).encode("utf-8"),
            ),
            reason="material staged candidate interpreter failed",
            failure=outcome.message,
        )
        return InterpreterOutcome(
            disposition=EffectDisposition.OUTCOME_UNKNOWN,
            failure_code="STAGE_FAILED",
            reconciliation_hint=(f"reverse_return:{reverse.reverse_return_digest}"),
        )


@dataclass(frozen=True, slots=True)
class MaterialCommitReadbackRollbackRouteHandler(RuntimeHandler):
    """Pure commit-readback rollback route; never performs a canonical write."""

    readback_args: dict[str, str]
    handler_binding_digest: str
    interpreter_profile_digest: str
    operation_contract_digest: str
    deployment_catalog_digest: str

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
            drift_code=(
                "EXACT_MATERIAL_INGEST_COMMIT_READBACK_ROLLBACK_"
                "HANDLER_BINDING_DRIFT"
            ),
        )
        return _succeeded_interpreter_outcome(
            interpret_commit_readback(**self.readback_args)
        )


@dataclass(frozen=True, slots=True)
class MaterialProjectionDiffRollbackRouteHandler(RuntimeHandler):
    """Pure projection-diff rollback route; no projector driver is executed."""

    diff: ProjectionDiff
    handler_binding_digest: str
    interpreter_profile_digest: str
    operation_contract_digest: str
    deployment_catalog_digest: str

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
            drift_code=(
                "EXACT_MATERIAL_INGEST_PROJECTION_DIFF_ROLLBACK_"
                "HANDLER_BINDING_DRIFT"
            ),
        )
        return _succeeded_interpreter_outcome(interpret_projection_diff(self.diff))


@dataclass(frozen=True, slots=True)
class MaterialReconciliationRollbackRouteHandler(RuntimeHandler):
    """Pure reconciliation-decision rollback route; no adopt/authority change."""

    decision: MaterialReconciliationDecision
    handler_binding_digest: str
    interpreter_profile_digest: str
    operation_contract_digest: str
    deployment_catalog_digest: str

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
            drift_code=(
                "EXACT_MATERIAL_INGEST_RECONCILIATION_ROLLBACK_"
                "HANDLER_BINDING_DRIFT"
            ),
        )
        return _succeeded_interpreter_outcome(interpret_reconciliation(self.decision))


@dataclass(frozen=True, slots=True)
class MaterialCanonicalWriteClosure:
    """Exact C7.2 canonical write closure supplied by the run owner."""

    write_port: C7CanonicalWritePort
    connection_factory: Callable[[], Connection]
    structured_candidate: StructuredMaterialCandidate
    verified_candidate: VerifiedMaterialCandidate
    binding: VerificationBinding
    ordered_event_payloads: tuple[dict[str, object], ...]
    config: C7AdmissionConfig
    scope: RuntimeScope


@dataclass(frozen=True, slots=True)
class MaterialProjectorDriverClosure:
    """Exact C7.3 projector driver closure supplied by the run owner."""

    connection_factory: Callable[[], Connection]
    scope: RuntimeScope
    object_id: str
    expected_source_incarnation: str
    rebuild_mode: RebuildMode = "FULL"

    def __post_init__(self) -> None:
        if not self.object_id:
            raise ValueError("C7 projector driver requires a non-empty object id")
        if not self.expected_source_incarnation:
            raise ValueError(
                "C7 projector driver requires the exact canonical incarnation"
            )
        if self.rebuild_mode not in ("FULL", "INCREMENTAL"):
            raise ValueError(f"unsupported rebuild mode: {self.rebuild_mode}")


@dataclass(frozen=True, slots=True)
class MaterialCanonicalCommitWriteHandler(RuntimeHandler):
    """Real C7.2 canonical commit write over the successor-only port."""

    closure: MaterialCanonicalWriteClosure
    handler_binding_digest: str
    interpreter_profile_digest: str
    operation_contract_digest: str
    deployment_catalog_digest: str

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
            drift_code=(
                "EXACT_MATERIAL_INGEST_CANONICAL_WRITE_HANDLER_BINDING_DRIFT"
            ),
        )
        connection = self.closure.connection_factory()
        try:
            with connection.begin():
                result = self.closure.write_port.admit(
                    connection,
                    self.closure.structured_candidate,
                    self.closure.verified_candidate,
                    self.closure.binding,
                    self.closure.ordered_event_payloads,
                    config=self.closure.config,
                    scope=self.closure.scope,
                )
        except C7MovementAdmissionError as exc:
            raise DefiniteInterpreterFailure(
                "MATERIAL_INGEST_CANONICAL_WRITE_REJECTED"
            ) from exc
        finally:
            connection.close()
        return InterpreterOutcome.succeeded(
            result.readback.readback_digest,
            receipt_ref=result.readback.canonical_commit_ref,
        )


@dataclass(frozen=True, slots=True)
class MaterialProjectorDriverHandler(RuntimeHandler):
    """Real C7.3 projector driver over successor-only offset/value writes."""

    closure: MaterialProjectorDriverClosure
    handler_binding_digest: str
    interpreter_profile_digest: str
    operation_contract_digest: str
    deployment_catalog_digest: str

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
            drift_code=(
                "EXACT_MATERIAL_INGEST_PROJECTOR_DRIVER_HANDLER_BINDING_DRIFT"
            ),
        )
        connection = self.closure.connection_factory()
        try:
            with connection.begin():
                driver = C7ProjectorDriver(connection, self.closure.scope)
                results = driver.rebuild_document(
                    self.closure.object_id,
                    mode=self.closure.rebuild_mode,
                    expected_source_incarnation=self.closure.expected_source_incarnation,
                )
        except C7ProjectorDriverError as exc:
            raise DefiniteInterpreterFailure(
                "MATERIAL_INGEST_PROJECTOR_DRIVE_REJECTED"
            ) from exc
        finally:
            connection.close()
        payload = {
            "schema": "mrw.material.projector-drive.v2",
            "object_id": self.closure.object_id,
            "rebuild_mode": self.closure.rebuild_mode,
            "results": [
                {
                    "projection_kind": result.projection_kind,
                    "projection_digest": result.projection_digest,
                    "source_revision": result.source_revision,
                    "source_digest": result.source_digest,
                    "offset_ref": result.offset_ref,
                    "value_ref": result.value_ref,
                    "store_writes": result.store_writes,
                    "provider_calls": result.provider_calls,
                    "export_calls": result.export_calls,
                    "production_canonical_authority": (
                        result.production_canonical_authority
                    ),
                }
                for result in results
            ],
        }
        return InterpreterOutcome.succeeded(content_digest(payload))


_MATERIAL_ROUTE_HANDLERS = {
    MATERIAL_STAGE_CANDIDATE_CELL_ID: MaterialStageCandidateRollbackRouteHandler,
    MATERIAL_COMMIT_READBACK_CELL_ID: MaterialCommitReadbackRollbackRouteHandler,
    MATERIAL_PROJECTION_DIFF_CELL_ID: MaterialProjectionDiffRollbackRouteHandler,
    MATERIAL_RECONCILIATION_CELL_ID: MaterialReconciliationRollbackRouteHandler,
}

_MATERIAL_INSTALLED_NOTES = {
    MATERIAL_STAGE_CANDIDATE_CELL_ID: (
        "material staged-candidate rollback route installed; pure "
        "interpret_staged_candidate plus return_for_cleanup reverse return; "
        "no DB/admission/canonical write"
    ),
    MATERIAL_COMMIT_READBACK_CELL_ID: (
        "material commit-readback rollback route installed; pure "
        "interpret_commit_readback; canonical commit write NOT executed "
        "(authority closed); owner: WP-I1-06 canonical write authority"
    ),
    MATERIAL_PROJECTION_DIFF_CELL_ID: (
        "material projection-diff rollback route installed; pure "
        "interpret_projection_diff; projector driver NOT executed "
        "(authority closed); owner: projector driver milestone / "
        "canonical write authority"
    ),
    MATERIAL_RECONCILIATION_CELL_ID: (
        "material reconciliation-decision rollback route installed; pure "
        "interpret_reconciliation over READBACK_RECONCILIATION_CONTRACT_ID; "
        "no adopt/authority change"
    ),
}

_MATERIAL_CANONICAL_WRITE_INSTALLED_NOTE = (
    "C7.2 canonical commit write handler installed over "
    "admit_verified_candidate; successor-only tables "
    "(c7_movement_canonical_documents, runtime_commit_intents, "
    "successor_values); idempotent exact-duplicate readback; "
    "ABA/authority-epoch fail-closed; rollback PRESENT"
)
_MATERIAL_PROJECTOR_DRIVER_INSTALLED_NOTE = (
    "C7.3 projector driver installed; search+graph projector contracts "
    "registered in ProjectorRegistry; runtime_projection_offsets exact CAS "
    "plus successor_values persistence; rebuild driver; successor tables only"
)

_MATERIAL_GAP_DETAILS = {
    MATERIAL_STAGE_CANDIDATE_CELL_ID: (
        "missing options.submission route closure; canonical write authority closed"
    ),
    MATERIAL_COMMIT_READBACK_CELL_ID: (
        "missing options.commit_readback route closure; "
        "canonical commit write authority closed"
    ),
    MATERIAL_PROJECTION_DIFF_CELL_ID: (
        "missing options.projection_diff route closure; "
        "projector driver authority closed"
    ),
    MATERIAL_RECONCILIATION_CELL_ID: (
        "missing options.reconciliation_decision route closure; "
        "adopt/authority change closed"
    ),
}


def _material_catalog() -> Any:
    bundle = build_material_ingest_bundle()
    return build_material_ingest_catalog(bundle)


def _material_operation_contract_digest(kind: str) -> str:
    ref = _material_catalog().lookup(kind)
    if ref is not None:
        return ref.contract_digest
    # The ingest-c7 bundle registers only the C7.1 stage contract today; the
    # remaining route kinds get a deterministic assembly-scope identity.
    return content_digest(
        {
            "operation_contract_kind": kind,
            "catalog": "mrw.material.ingest.operations",
            "catalog_lookup_absent": True,
        }
    )


def _resolve_material_native_definition(native_definition: object | None) -> object:
    """Resolve the typed C7 native definition; the default source is authoritative."""

    from app.successor_runtime.capabilities.material_native_contribution import (
        MaterialNativeDefinition,
        DEFAULT_MATERIAL_NATIVE_SOURCE,
        compile_material_native_contribution,
    )

    if native_definition is None:
        native_result = compile_material_native_contribution(DEFAULT_MATERIAL_NATIVE_SOURCE)
        if not isinstance(native_result, MaterialNativeDefinition):
            native_definition = getattr(native_result, "definition", native_result)
        else:
            return native_result
    candidate = getattr(native_definition, "definition", native_definition)
    if not isinstance(candidate, MaterialNativeDefinition):
        raise TypeError("C7 assembly native_definition must be a C7NativeDefinition")
    return candidate


def _material_authority_digest(native_definition: object) -> str:
    source = native_definition.source
    return content_digest(
        (
            source.canonical_writer_ref,
            source.production_admission_ref,
            source.projector_driver_ref,
        )
    )


def _material_binding(
    *,
    cell_id: str,
    project_scope_digest: str,
    native_definition: object,
) -> Any:
    kind = _MATERIAL_ROUTE_KINDS[cell_id]
    profile_id = MATERIAL_INTERPRETER_PROFILE_IDS[_MATERIAL_ROUTE_PROFILE_KEYS[cell_id]]
    catalog_ref = native_definition.catalog.lookup(_MATERIAL_ROUTE_KINDS[cell_id])
    operation_digest = (
        catalog_ref.contract_digest
        if catalog_ref is not None
        else _material_operation_contract_digest(kind)
    )
    return successor_binding(
        operation_contract_digest=operation_digest,
        interpreter_profile_digest=sha256_hex(profile_id),
        deployment_catalog_digest=MATERIAL_INGEST_DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=_material_authority_digest(native_definition),
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )


def validate_material_ingest_assembly_native_definition(
    definition: object,
    assembly: object,
) -> None:
    """Validate lowered C7 boundaries against the real family assembly."""

    from app.successor_runtime.capabilities.material_native_contribution import (
        MaterialNativeDefinition,
    )

    if not isinstance(definition, MaterialNativeDefinition):
        raise TypeError("validate_c7_assembly_native_definition requires C7NativeDefinition")
    if (
        not isinstance(assembly, FamilyAssembly)
        or assembly.family_id != definition.source.bundle_id
    ):
        raise ValueError(
            "material ingest native validator requires its authored FamilyAssembly"
        )
    if (
        tuple(cell.cell_id for cell in assembly.cells)
        != definition.source.assembly_cell_ids
    ):
        raise ValueError("material ingest native cell order drift")
    if definition.source.canonical_write_authorized or definition.source.canonical_commit_executed:
        raise ValueError("C7 native source adopted durable canonical write authority")
    if definition.source.canonical_writer_ref == definition.source.projector_driver_ref:
        raise ValueError("C7 native canonical/projector authority boundary drift")


def _material_route_handler(
    *,
    cell_id: str,
    closure: Any,
    binding: Any,
) -> RuntimeHandler:
    common = {
        "handler_binding_digest": binding.binding_digest,
        "interpreter_profile_digest": binding.interpreter_profile_digest,
        "operation_contract_digest": binding.operation_contract_digest,
        "deployment_catalog_digest": binding.deployment_catalog_digest,
    }
    handler_cls = _MATERIAL_ROUTE_HANDLERS[cell_id]
    if cell_id == MATERIAL_STAGE_CANDIDATE_CELL_ID:
        return handler_cls(submission=closure, **common)
    if cell_id == MATERIAL_COMMIT_READBACK_CELL_ID:
        return handler_cls(readback_args=closure, **common)
    if cell_id == MATERIAL_PROJECTION_DIFF_CELL_ID:
        return handler_cls(diff=closure, **common)
    return handler_cls(decision=closure, **common)


def _material_projector_contracts(
    closure: MaterialProjectorDriverClosure,
) -> tuple[ProjectorContract, ProjectorContract]:
    """Build the exact search/graph projector contracts for one document."""

    source_ref = f"document:{closure.object_id}"
    search_key = ProjectorKey(
        projector_id=MATERIAL_SEARCH_PROJECTOR_ID,
        projector_version=MATERIAL_SEARCH_PROJECTOR_VERSION,
        source_kind=MATERIAL_CANONICAL_SOURCE_KIND,
        source_ref=source_ref,
        source_incarnation=closure.expected_source_incarnation,
    )
    graph_key = ProjectorKey(
        projector_id=MATERIAL_GRAPH_PROJECTOR_ID,
        projector_version=MATERIAL_GRAPH_PROJECTOR_VERSION,
        source_kind=MATERIAL_CANONICAL_SOURCE_KIND,
        source_ref=source_ref,
        source_incarnation=closure.expected_source_incarnation,
    )
    return (
        ProjectorContract(
            key=search_key,
            projection_id=MATERIAL_SEARCH_PROJECTION_ID,
            projection_schema_ref=MATERIAL_SEARCH_PROJECTION_SCHEMA,
            declared_loss=c7_search_declared_loss(),
        ),
        ProjectorContract(
            key=graph_key,
            projection_id=MATERIAL_GRAPH_PROJECTION_ID,
            projection_schema_ref=MATERIAL_GRAPH_PROJECTION_SCHEMA,
            declared_loss=c7_graph_declared_loss(),
        ),
    )


def build_material_ingest_assembly(
    *,
    options: MaterialIngestAssemblyOptions | None = None,
    project_scope_digest: str | None = None,
    canonical_write: MaterialCanonicalWriteClosure | None = None,
    projector_driver: MaterialProjectorDriverClosure | None = None,
    native_definition: object | None = None,
) -> Annotated[
    FamilyAssembly,
    "kit:prepared-command effect_boundary=successor_runtime.c7_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """Build the C7 family assembly with per-cell rollback-route closures.

    ``project_scope_digest`` defaults to the deterministic local-only identity
    because :class:`MaterialIngestAssemblyOptions` does not yet carry a scope field; a run
    must pass the exact persisted scope when it is available.

    ``canonical_write`` installs the real C7.2 successor-only canonical
    commit-write handler; ``projector_driver`` installs the real C7.3
    successor-only projector driver and registers its search/graph projector
    contracts in the family ``ProjectorRegistry``.
    """

    scope = project_scope_digest or local_assembly_scope_digest()
    require_assembly_digest(scope, "C7 assembly project scope digest")
    opts = options or MaterialIngestAssemblyOptions()
    definition = _resolve_material_native_definition(native_definition)
    cells: list[CellBinding] = []
    handlers: list[RuntimeHandler] = []
    rollback_bindings: list[RollbackBindingDeclaration] = []
    projector_registry: ProjectorRegistry | None = None

    for cell_id, (
        operation_contract_refs,
        recovery_binding_ref,
        required_wiring,
        declared_note,
    ) in MATERIAL_INGEST_CELL_SPECS.items():
        if cell_id == MATERIAL_COMMIT_READBACK_CELL_ID and canonical_write is not None:
            binding = _material_binding(cell_id=cell_id, project_scope_digest=scope, native_definition=definition)
            handler = MaterialCanonicalCommitWriteHandler(
                closure=canonical_write,
                handler_binding_digest=binding.binding_digest,
                interpreter_profile_digest=binding.interpreter_profile_digest,
                operation_contract_digest=binding.operation_contract_digest,
                deployment_catalog_digest=binding.deployment_catalog_digest,
            )
            handlers.append(handler)
            cells.append(
                CellBinding(
                    cell_id=cell_id,
                    family_id=MATERIAL_INGEST_FAMILY_ID,
                    status="INSTALLED",
                    operation_contract_refs=operation_contract_refs,
                    handler_binding_digest=handler.handler_binding_digest,
                    recovery_binding_ref=recovery_binding_ref,
                    required_wiring=required_wiring,
                    note=_MATERIAL_CANONICAL_WRITE_INSTALLED_NOTE,
                )
            )
            rollback_bindings.append(
                RollbackBindingDeclaration(
                    cell_id=cell_id,
                    status="PRESENT",
                    binding_refs=(
                        _MATERIAL_CANONICAL_WRITE_MODULE,
                        _MATERIAL_ADMISSION_MODULE,
                    ),
                    note=_MATERIAL_PG_ROUTE_NOTE,
                )
            )
            continue
        if cell_id == MATERIAL_PROJECTION_DIFF_CELL_ID and projector_driver is not None:
            binding = _material_binding(cell_id=cell_id, project_scope_digest=scope, native_definition=definition)
            handler = MaterialProjectorDriverHandler(
                closure=projector_driver,
                handler_binding_digest=binding.binding_digest,
                interpreter_profile_digest=binding.interpreter_profile_digest,
                operation_contract_digest=binding.operation_contract_digest,
                deployment_catalog_digest=binding.deployment_catalog_digest,
            )
            handlers.append(handler)
            cells.append(
                CellBinding(
                    cell_id=cell_id,
                    family_id=MATERIAL_INGEST_FAMILY_ID,
                    status="INSTALLED",
                    operation_contract_refs=operation_contract_refs,
                    handler_binding_digest=handler.handler_binding_digest,
                    recovery_binding_ref=recovery_binding_ref,
                    required_wiring=required_wiring,
                    note=_MATERIAL_PROJECTOR_DRIVER_INSTALLED_NOTE,
                )
            )
            rollback_bindings.append(
                RollbackBindingDeclaration(
                    cell_id=cell_id,
                    status="PRESENT",
                    binding_refs=(
                        _MATERIAL_PROJECTOR_DRIVER_MODULE,
                        _MATERIAL_PROJECTION_OFFSETS_MODULE,
                        _MATERIAL_DOCUMENT_READBACK_MODULE,
                    ),
                    note=_MATERIAL_PG_ROUTE_NOTE,
                )
            )
            contracts = _material_projector_contracts(projector_driver)
            projector_registry = ProjectorRegistry(
                revision=0,
                incarnation=PROJECTOR_REGISTRY_INCARNATION,
                projectors=contracts,
            )
            continue
        option_field = _MATERIAL_ROUTE_OPTION_FIELDS[cell_id]
        closure = getattr(opts, option_field)
        if closure is None:
            cells.append(
                CellBinding(
                    cell_id=cell_id,
                    family_id=MATERIAL_INGEST_FAMILY_ID,
                    status="UNWIRED_DECLARED",
                    operation_contract_refs=operation_contract_refs,
                    recovery_binding_ref=recovery_binding_ref,
                    required_wiring=required_wiring,
                    note=(
                        f"{declared_note}; missing options.{option_field} route closure"
                    ),
                )
            )
            rollback_bindings.append(
                RollbackBindingDeclaration(
                    cell_id=cell_id,
                    status="DECLARED_GAP",
                    note=(MATERIAL_INGEST_ROLLBACK_GAP_NOTE + "; " + _MATERIAL_GAP_DETAILS[cell_id]),
                )
            )
            continue

        binding = _material_binding(cell_id=cell_id, project_scope_digest=scope, native_definition=definition)
        handler = _material_route_handler(
            cell_id=cell_id,
            closure=closure,
            binding=binding,
        )
        assert handler.handler_binding_digest == binding.binding_digest
        handlers.append(handler)
        cells.append(
            CellBinding(
                cell_id=cell_id,
                family_id=MATERIAL_INGEST_FAMILY_ID,
                status="INSTALLED",
                operation_contract_refs=operation_contract_refs,
                handler_binding_digest=handler.handler_binding_digest,
                recovery_binding_ref=recovery_binding_ref,
                required_wiring=required_wiring,
                note=_MATERIAL_INSTALLED_NOTES[cell_id],
            )
        )
        rollback_bindings.append(
            RollbackBindingDeclaration(
                cell_id=cell_id,
                status="PRESENT",
                binding_refs=_MATERIAL_ROLLBACK_REFS[cell_id],
                note=_MATERIAL_PURE_ROUTE_NOTE,
            )
        )

    registry_store = opts.registry_store
    registry_command = opts.registry_command
    if (registry_store is None) != (registry_command is None):
        raise ValueError(
            "material ingest registry wiring requires both registry_store and "
            "registry_command"
        )
    if registry_store is not None:
        binding = successor_binding(
            operation_contract_digest=_MATERIAL_INGEST_REGISTRY_OPERATION_DIGEST,
            interpreter_profile_digest=_MATERIAL_INGEST_REGISTRY_INTERPRETER_DIGEST,
            deployment_catalog_digest=MATERIAL_INGEST_DEPLOYMENT_CATALOG_DIGEST,
            project_scope_digest=scope,
            authority_requirement_digest=_MATERIAL_INGEST_REGISTRY_AUTHORITY_DIGEST,
        )
        handler = C7IngestRegistryRuntimeHandler(
            store=registry_store,
            command=registry_command,
            handler_binding_digest=binding.binding_digest,
            interpreter_profile_digest=binding.interpreter_profile_digest,
            operation_contract_digest=binding.operation_contract_digest,
            deployment_catalog_digest=binding.deployment_catalog_digest,
        )
        handlers.append(handler)
        commit_readback_index = next(
            index
            for index, cell in enumerate(cells)
            if cell.cell_id == MATERIAL_COMMIT_READBACK_CELL_ID
        )
        previous = cells[commit_readback_index]
        previous_rollback = rollback_bindings[commit_readback_index]
        registry_note = (
            "; material ingest-submission registry typed route handler installed "
            "over the successor-only registry port/readback; exact/idempotent "
            "duplicate handling; legacy/provider/canonical-write authority closed"
        )
        operation_refs = previous.operation_contract_refs + (
            _MATERIAL_INGEST_REGISTRY_OPERATION_REF,
        )
        if previous.status == "UNWIRED_DECLARED":
            cells[commit_readback_index] = CellBinding(
                cell_id=MATERIAL_COMMIT_READBACK_CELL_ID,
                family_id=MATERIAL_INGEST_FAMILY_ID,
                status="INSTALLED",
                operation_contract_refs=operation_refs,
                handler_binding_digest=handler.handler_binding_digest,
                recovery_binding_ref=previous.recovery_binding_ref,
                required_wiring=previous.required_wiring,
                note=previous.note + registry_note,
            )
        else:
            cells[commit_readback_index] = CellBinding(
                cell_id=MATERIAL_COMMIT_READBACK_CELL_ID,
                family_id=MATERIAL_INGEST_FAMILY_ID,
                status=previous.status,
                operation_contract_refs=operation_refs,
                handler_binding_digest=previous.handler_binding_digest,
                recovery_binding_ref=previous.recovery_binding_ref,
                required_wiring=previous.required_wiring,
                rollback_binding_refs=previous.rollback_binding_refs,
                note=previous.note + registry_note,
            )
        rollback_bindings[commit_readback_index] = RollbackBindingDeclaration(
            cell_id=MATERIAL_COMMIT_READBACK_CELL_ID,
            status="PRESENT",
            binding_refs=previous_rollback.binding_refs
            + (
                _MATERIAL_INGEST_REGISTRY_CAPABILITY_MODULE,
                _MATERIAL_INGEST_REGISTRY_HANDLER_MODULE,
            ),
            note=previous_rollback.note + registry_note,
        )

    return FamilyAssembly(
        family_id=MATERIAL_INGEST_FAMILY_ID,
        cells=tuple(cells),
        handlers=tuple(handlers),
        rollback_bindings=tuple(rollback_bindings),
        projector_registry=projector_registry,
    )


def build_deterministic_material_ingest_rollback_options(
    project_scope_digest: str,
) -> Annotated[
    MaterialIngestAssemblyOptions,
    "kit:prepared-command effect_boundary=successor_runtime.c7_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """Build the deterministic local C7 rollback-route fixture closures."""

    require_assembly_digest(
        project_scope_digest,
        "C7 rollback options project scope digest",
    )
    submission = MaterialIngestSubmission(
        idempotency_key="idem:i1-local-c7:001",
        project_key="i1-local-c7",
        source_locator="https://example.invalid/i1-local-c7/001",
        request_key="req:i1-local-c7:001",
        raw_payload={
            "title": "I1 local C7 rollback route fixture",
            "text": "deterministic staged candidate fixture",
            "project_scope_digest": project_scope_digest,
        },
    )
    commit_readback = {
        "commit_intent_id": "commit:i1-c7:001",
        "content_digest_hex": sha256_hex("content:i1-c7:001"),
        "verification_binding_digest": sha256_hex("verification:i1-c7:001"),
        "state": "readback_available",
    }
    projection_diff = ProjectionDiff(
        source_identity="document:i1-c7:001",
        projection_kind="search",
        source_digest=sha256_hex("source:i1-c7:001"),
        projection_digest=sha256_hex("projection:i1-c7:001"),
        declared_loss=(
            ("full_text", "raw text not indexed"),
            ("raw_payload", "raw payload not indexed"),
        ),
    )
    reconciliation_decision = MaterialReconciliationDecision(
        new_attempt_allowed=False,
        requirement=(
            "exact non-start proof plus current authority required before "
            "any new attempt"
        ),
        reason=(
            "deterministic local rollback reconciliation fixture; new attempt forbidden"
        ),
    )
    return MaterialIngestAssemblyOptions(
        submission=submission,
        commit_readback=commit_readback,
        projection_diff=projection_diff,
        reconciliation_decision=reconciliation_decision,
    )


__all__ = [
    "ASSEMBLY_CELL_IDS",
    "MATERIAL_INGEST_ASSEMBLY_CELL_IDS",
    "MATERIAL_INGEST_AUTHORITY_REQUIREMENT_DIGEST",
    "MATERIAL_INGEST_CELL_SPECS",
    "MATERIAL_INGEST_DEPLOYMENT_CATALOG_DIGEST",
    "MATERIAL_INGEST_FAMILY_ID",
    "MATERIAL_INGEST_ROLLBACK_GAP_NOTE",
    "MaterialCanonicalWriteClosure",
    "MaterialProjectorDriverClosure",
    "MaterialStageCandidateRollbackRouteHandler",
    "MaterialCanonicalCommitWriteHandler",
    "MaterialCommitReadbackRollbackRouteHandler",
    "MaterialProjectionDiffRollbackRouteHandler",
    "MaterialProjectorDriverHandler",
    "MaterialReconciliationRollbackRouteHandler",
    "build_material_ingest_assembly",
    "build_deterministic_material_ingest_rollback_options",
    "validate_material_ingest_assembly_native_definition",
]
