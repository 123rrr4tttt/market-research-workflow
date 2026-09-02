"""C7 family assembly: explicit pure rollback-route and successor write wiring.

C7.1-C7.4 are installed only when the caller supplies the exact deterministic
route closure in :class:`C7AssemblyOptions`.  Every installed route is a pure
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
from typing import Any

from sqlalchemy.engine import Connection

from app.successor_runtime.assembly.base import (
    PROJECTOR_REGISTRY_INCARNATION,
    C7AssemblyOptions,
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
from app.successor_runtime.capabilities.ingest_c7_common import (
    COMMIT_INTENT_CONTRACT_ID,
    PROJECTION_DIFF_CONTRACT_ID,
    READBACK_RECONCILIATION_CONTRACT_ID,
    STAGE_CANDIDATE_KIND,
    C7IngestSubmission,
    C7ReconciliationDecision,
    ProjectionDiff,
    build_ingest_c7_bundle,
    build_ingest_c7_catalog,
)
from app.successor_runtime.capabilities.ingest_c7_interpreters import (
    C7_INTERPRETER_PROFILE_IDS,
    IngestInterpreterSuccess,
    interpret_commit_readback,
    interpret_projection_diff,
    interpret_reconciliation,
    interpret_staged_candidate,
)
from app.successor_runtime.capabilities.ingest_c7_movements import (
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
    C7_CANONICAL_SOURCE_KIND,
    C7_GRAPH_PROJECTION_SCHEMA,
    C7_GRAPH_PROJECTOR_ID,
    C7_GRAPH_PROJECTOR_VERSION,
    C7_SEARCH_PROJECTION_SCHEMA,
    C7_SEARCH_PROJECTOR_ID,
    C7_SEARCH_PROJECTOR_VERSION,
    C7ProjectorDriver,
    C7ProjectorDriverError,
    c7_graph_declared_loss,
    c7_search_declared_loss,
)
from app.successor_runtime.substrate.postgres.ingest_c7_movement_admission import (
    C7AdmissionConfig,
)
from app.successor_runtime.substrate.projections.registry import RebuildMode

C7_FAMILY_ID = "C7"

C7_DEPLOYMENT_CATALOG_DIGEST = sha256_hex("mrw.successor.deployment-catalog.c7.v1")
C7_AUTHORITY_REQUIREMENT_DIGEST = sha256_hex("mrw.successor.c7.authority.v1")

_C7_INTERPRETERS_MODULE = (
    "main/backend/app/successor_runtime/capabilities/ingest_c7_interpreters.py"
)
_C7_COMMON_MODULE = (
    "main/backend/app/successor_runtime/capabilities/ingest_c7_common.py"
)
_C7_MOVEMENTS_MODULE = (
    "main/backend/app/successor_runtime/capabilities/ingest_c7_movements.py"
)
_C7_RECONCILIATION_MODULE = (
    "main/backend/app/successor_runtime/runtime/reconciliation.py"
)
_C7_CANONICAL_WRITE_MODULE = (
    "main/backend/app/successor_runtime/substrate/postgres/c7_canonical_write.py"
)
_C7_ADMISSION_MODULE = (
    "main/backend/app/successor_runtime/substrate/postgres/"
    "ingest_c7_movement_admission.py"
)
_C7_PROJECTOR_DRIVER_MODULE = (
    "main/backend/app/successor_runtime/substrate/postgres/c7_projector_driver.py"
)
_C7_PROJECTION_OFFSETS_MODULE = (
    "main/backend/app/successor_runtime/substrate/postgres/projection_offsets.py"
)
_C7_DOCUMENT_READBACK_MODULE = (
    "main/backend/app/successor_runtime/substrate/postgres/c7_document_readback.py"
)

_C7_ROUTE_OPTION_FIELDS = {
    "C7.1": "submission",
    "C7.2": "commit_readback",
    "C7.3": "projection_diff",
    "C7.4": "reconciliation_decision",
}
_C7_ROUTE_PROFILE_KEYS = {
    "C7.1": "staged_candidate",
    "C7.2": "commit_readback",
    "C7.3": "projection_diff",
    "C7.4": "reconciliation",
}
_C7_ROUTE_KINDS = {
    "C7.1": STAGE_CANDIDATE_KIND,
    "C7.2": COMMIT_INTENT_CONTRACT_ID,
    "C7.3": PROJECTION_DIFF_CONTRACT_ID,
    "C7.4": READBACK_RECONCILIATION_CONTRACT_ID,
}
_C7_ROLLBACK_REFS = {
    "C7.1": (_C7_INTERPRETERS_MODULE, _C7_MOVEMENTS_MODULE),
    "C7.2": (_C7_INTERPRETERS_MODULE, _C7_COMMON_MODULE),
    "C7.3": (_C7_INTERPRETERS_MODULE, _C7_COMMON_MODULE),
    "C7.4": (
        _C7_INTERPRETERS_MODULE,
        _C7_COMMON_MODULE,
        _C7_RECONCILIATION_MODULE,
    ),
}

C7_CELL_SPECS: dict[
    str,
    tuple[tuple[str, ...], str, tuple[str, ...], str],
] = {
    "C7.1": (
        ("ingest_index.stage_candidate.v1",),
        (
            "ingest_index.c7.stage.recovery.v1#retain-staged-candidate-and-"
            "runtime-receipt;no-repeat-effect"
        ),
        (
            "C7 assembly 与 AdmissionCoordinator 注册",
            "legacy writer 保持 zero 的适配边界",
            "document admission/canonical write 需单独 authority review",
        ),
        (
            "staged-candidate components exist; no RuntimeHandler or "
            "AdmissionCoordinator registration; canonical write authority closed"
        ),
    ),
    "C7.2": (
        (
            "ingest_index.commit_intent.readback.v1",
            "ingest_index.admission.readback.v1",
        ),
        (
            "ingest_index.commit_intent.readback.v1#prepare-then-readback;"
            "no-repeat-commit;outcome-unknown-waits-for-readback"
        ),
        ("C7 admission 注册", "readback resource policy"),
        (
            "commit-intent/readback components exist; C7 admission is not "
            "registered with an AdmissionCoordinator"
        ),
    ),
    "C7.3": (
        ("ingest_index.projection_declared_loss.v1",),
        (
            "ingest_index.projection_declared_loss.v1#rebuild-from-bound-document;"
            "resume-offset-or-full-rebuild;no-canonical-mutation"
        ),
        ("C7 projector 注册", "projection offset 驱动"),
        (
            "projection-diff components exist; no C7 projector registration "
            "or projection offset driver"
        ),
    ),
    "C7.4": (
        ("ingest_index.reconcile.readback.v1", "ingest_index.reconcile.nonstart.v1"),
        (
            "ingest_index.reconcile.nonstart.v1#exact-nonstart-proof-plus-current-"
            "authority;new-attempt-epoch-only;rollback-changes-future-routing-not-events"
        ),
        ("C7 reconcile handler installation", "recovery binding"),
        (
            "reconcile components exist; no C7 reconcile RuntimeHandler "
            "installation or recovery binding"
        ),
    ),
}

C7_ROLLBACK_GAP_NOTE = (
    "FC-04/I1-2026-09-02: current C7 specs list p4-fragments/C7.json only as "
    "c7_N_rollback_family_observation bindings, not as legacy rollback routes; "
    "no rollback route binding exists, so rehearsal/assembly rollback "
    "acceptance stays blocked (DECLARED_GAP)"
)

_C7_PURE_ROUTE_NOTE = (
    "纯 route 装配：真实 successor_runtime 实现模块绑定；非 p4-fragments 观察绑定"
)
_C7_PG_ROUTE_NOTE = (
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
        raise DefiniteInterpreterFailure("C7_CLAIM_ASSIGNMENT_BINDING_DRIFT")
    if claim.handler_binding_digest != assignment.handler_binding_digest:
        raise DefiniteInterpreterFailure("C7_CLAIM_HANDLER_BINDING_DRIFT")
    if (
        assignment.handler_binding_digest != handler_binding_digest
        or assignment.operation_contract_digest != operation_contract_digest
        or assignment.deployment_catalog_digest != deployment_catalog_digest
        or getattr(assignment.handler_binding, "interpreter_profile_digest", None)
        != interpreter_profile_digest
    ):
        raise DefiniteInterpreterFailure(drift_code)


def _succeeded_interpreter_outcome(outcome: Any) -> InterpreterOutcome:
    if not isinstance(outcome, IngestInterpreterSuccess):
        raise DefiniteInterpreterFailure("C7_ROLLBACK_INTERPRETER_REJECTED")
    return InterpreterOutcome.succeeded(content_digest(outcome.value))


@dataclass(frozen=True, slots=True)
class C7_1StageCandidateRollbackRouteHandler(RuntimeHandler):
    """Pure staged-candidate rollback route over ``interpret_staged_candidate``."""

    submission: C7IngestSubmission
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
            drift_code="EXACT_C7_1_ROLLBACK_HANDLER_BINDING_DRIFT",
        )
        outcome = interpret_staged_candidate(self.submission)
        if isinstance(outcome, IngestInterpreterSuccess):
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
            reason="C7.1 staged candidate interpreter failed",
            failure=outcome.message,
        )
        return InterpreterOutcome(
            disposition=EffectDisposition.OUTCOME_UNKNOWN,
            failure_code="STAGE_FAILED",
            reconciliation_hint=(f"reverse_return:{reverse.reverse_return_digest}"),
        )


@dataclass(frozen=True, slots=True)
class C7_2CommitReadbackRollbackRouteHandler(RuntimeHandler):
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
            drift_code="EXACT_C7_2_ROLLBACK_HANDLER_BINDING_DRIFT",
        )
        return _succeeded_interpreter_outcome(
            interpret_commit_readback(**self.readback_args)
        )


@dataclass(frozen=True, slots=True)
class C7_3ProjectionDiffRollbackRouteHandler(RuntimeHandler):
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
            drift_code="EXACT_C7_3_ROLLBACK_HANDLER_BINDING_DRIFT",
        )
        return _succeeded_interpreter_outcome(interpret_projection_diff(self.diff))


@dataclass(frozen=True, slots=True)
class C7_4ReconcileRollbackRouteHandler(RuntimeHandler):
    """Pure reconciliation-decision rollback route; no adopt/authority change."""

    decision: C7ReconciliationDecision
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
            drift_code="EXACT_C7_4_ROLLBACK_HANDLER_BINDING_DRIFT",
        )
        return _succeeded_interpreter_outcome(interpret_reconciliation(self.decision))


@dataclass(frozen=True, slots=True)
class C7CanonicalWriteClosure:
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
class C7ProjectorDriverClosure:
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
class C7_2CanonicalCommitWriteHandler(RuntimeHandler):
    """Real C7.2 canonical commit write over the successor-only port."""

    closure: C7CanonicalWriteClosure
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
            drift_code="EXACT_C7_2_CANONICAL_WRITE_HANDLER_BINDING_DRIFT",
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
            raise DefiniteInterpreterFailure("C7_2_CANONICAL_WRITE_REJECTED") from exc
        finally:
            connection.close()
        return InterpreterOutcome.succeeded(
            result.readback.readback_digest,
            receipt_ref=result.readback.canonical_commit_ref,
        )


@dataclass(frozen=True, slots=True)
class C7_3ProjectorDriverHandler(RuntimeHandler):
    """Real C7.3 projector driver over successor-only offset/value writes."""

    closure: C7ProjectorDriverClosure
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
            drift_code="EXACT_C7_3_PROJECTOR_DRIVER_HANDLER_BINDING_DRIFT",
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
            raise DefiniteInterpreterFailure("C7_3_PROJECTOR_DRIVE_REJECTED") from exc
        finally:
            connection.close()
        payload = {
            "schema": "mrw.successor.c7.projector-drive.v1",
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


_C7_ROUTE_HANDLERS = {
    "C7.1": C7_1StageCandidateRollbackRouteHandler,
    "C7.2": C7_2CommitReadbackRollbackRouteHandler,
    "C7.3": C7_3ProjectionDiffRollbackRouteHandler,
    "C7.4": C7_4ReconcileRollbackRouteHandler,
}

_C7_INSTALLED_NOTES = {
    "C7.1": (
        "C7.1 staged-candidate rollback route installed; pure "
        "interpret_staged_candidate plus return_for_cleanup reverse return; "
        "no DB/admission/canonical write"
    ),
    "C7.2": (
        "C7.2 commit-readback rollback route installed; pure "
        "interpret_commit_readback; canonical commit write NOT executed "
        "(authority closed); owner: WP-I1-06 canonical write authority"
    ),
    "C7.3": (
        "C7.3 projection-diff rollback route installed; pure "
        "interpret_projection_diff; projector driver NOT executed "
        "(authority closed); owner: projector driver milestone / "
        "canonical write authority"
    ),
    "C7.4": (
        "C7.4 reconciliation-decision rollback route installed; pure "
        "interpret_reconciliation over READBACK_RECONCILIATION_CONTRACT_ID; "
        "no adopt/authority change"
    ),
}

_C7_CANONICAL_WRITE_INSTALLED_NOTE = (
    "C7.2 canonical commit write handler installed over "
    "admit_verified_candidate; successor-only tables "
    "(c7_movement_canonical_documents, runtime_commit_intents, "
    "successor_values); idempotent exact-duplicate readback; "
    "ABA/authority-epoch fail-closed; rollback PRESENT"
)
_C7_PROJECTOR_DRIVER_INSTALLED_NOTE = (
    "C7.3 projector driver installed; search+graph projector contracts "
    "registered in ProjectorRegistry; runtime_projection_offsets exact CAS "
    "plus successor_values persistence; rebuild driver; successor tables only"
)

_C7_GAP_DETAILS = {
    "C7.1": "missing options.submission route closure; canonical write authority closed",
    "C7.2": (
        "missing options.commit_readback route closure; "
        "canonical commit write authority closed"
    ),
    "C7.3": (
        "missing options.projection_diff route closure; "
        "projector driver authority closed"
    ),
    "C7.4": (
        "missing options.reconciliation_decision route closure; "
        "adopt/authority change closed"
    ),
}


def _c7_catalog() -> Any:
    bundle = build_ingest_c7_bundle()
    return build_ingest_c7_catalog(bundle)


def _c7_operation_contract_digest(kind: str) -> str:
    ref = _c7_catalog().lookup(kind)
    if ref is not None:
        return ref.contract_digest
    # The ingest-c7 bundle registers only the C7.1 stage contract today; the
    # remaining route kinds get a deterministic assembly-scope identity.
    return content_digest(
        {
            "operation_contract_kind": kind,
            "catalog": "mrw.functorial-successor.ingest-c7.operations",
            "catalog_lookup_absent": True,
        }
    )


def _c7_binding(*, cell_id: str, project_scope_digest: str) -> Any:
    kind = _C7_ROUTE_KINDS[cell_id]
    profile_id = C7_INTERPRETER_PROFILE_IDS[_C7_ROUTE_PROFILE_KEYS[cell_id]]
    return successor_binding(
        operation_contract_digest=_c7_operation_contract_digest(kind),
        interpreter_profile_digest=sha256_hex(profile_id),
        deployment_catalog_digest=C7_DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=C7_AUTHORITY_REQUIREMENT_DIGEST,
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )


def _c7_route_handler(
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
    handler_cls = _C7_ROUTE_HANDLERS[cell_id]
    if cell_id == "C7.1":
        return handler_cls(submission=closure, **common)
    if cell_id == "C7.2":
        return handler_cls(readback_args=closure, **common)
    if cell_id == "C7.3":
        return handler_cls(diff=closure, **common)
    return handler_cls(decision=closure, **common)


def _c7_3_projector_contracts(
    closure: C7ProjectorDriverClosure,
) -> tuple[ProjectorContract, ProjectorContract]:
    """Build the exact search/graph projector contracts for one document."""

    source_ref = f"document:{closure.object_id}"
    search_key = ProjectorKey(
        projector_id=C7_SEARCH_PROJECTOR_ID,
        projector_version=C7_SEARCH_PROJECTOR_VERSION,
        source_kind=C7_CANONICAL_SOURCE_KIND,
        source_ref=source_ref,
        source_incarnation=closure.expected_source_incarnation,
    )
    graph_key = ProjectorKey(
        projector_id=C7_GRAPH_PROJECTOR_ID,
        projector_version=C7_GRAPH_PROJECTOR_VERSION,
        source_kind=C7_CANONICAL_SOURCE_KIND,
        source_ref=source_ref,
        source_incarnation=closure.expected_source_incarnation,
    )
    return (
        ProjectorContract(
            key=search_key,
            projection_id="projection.c7-search.v1",
            projection_schema_ref=C7_SEARCH_PROJECTION_SCHEMA,
            declared_loss=c7_search_declared_loss(),
        ),
        ProjectorContract(
            key=graph_key,
            projection_id="projection.c7-graph.v1",
            projection_schema_ref=C7_GRAPH_PROJECTION_SCHEMA,
            declared_loss=c7_graph_declared_loss(),
        ),
    )


def build_c7_assembly(
    *,
    options: C7AssemblyOptions | None = None,
    project_scope_digest: str | None = None,
    canonical_write: C7CanonicalWriteClosure | None = None,
    projector_driver: C7ProjectorDriverClosure | None = None,
) -> FamilyAssembly:
    """Build the C7 family assembly with per-cell rollback-route closures.

    ``project_scope_digest`` defaults to the deterministic local-only identity
    because :class:`C7AssemblyOptions` does not yet carry a scope field; a run
    must pass the exact persisted scope when it is available.

    ``canonical_write`` installs the real C7.2 successor-only canonical
    commit-write handler; ``projector_driver`` installs the real C7.3
    successor-only projector driver and registers its search/graph projector
    contracts in the family ``ProjectorRegistry``.
    """

    scope = project_scope_digest or local_assembly_scope_digest()
    require_assembly_digest(scope, "C7 assembly project scope digest")
    opts = options or C7AssemblyOptions()
    cells: list[CellBinding] = []
    handlers: list[RuntimeHandler] = []
    rollback_bindings: list[RollbackBindingDeclaration] = []
    projector_registry: ProjectorRegistry | None = None

    for cell_id, (
        operation_contract_refs,
        recovery_binding_ref,
        required_wiring,
        declared_note,
    ) in C7_CELL_SPECS.items():
        if cell_id == "C7.2" and canonical_write is not None:
            binding = _c7_binding(cell_id=cell_id, project_scope_digest=scope)
            handler = C7_2CanonicalCommitWriteHandler(
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
                    family_id=C7_FAMILY_ID,
                    status="INSTALLED",
                    operation_contract_refs=operation_contract_refs,
                    handler_binding_digest=handler.handler_binding_digest,
                    recovery_binding_ref=recovery_binding_ref,
                    required_wiring=required_wiring,
                    note=_C7_CANONICAL_WRITE_INSTALLED_NOTE,
                )
            )
            rollback_bindings.append(
                RollbackBindingDeclaration(
                    cell_id=cell_id,
                    status="PRESENT",
                    binding_refs=(
                        _C7_CANONICAL_WRITE_MODULE,
                        _C7_ADMISSION_MODULE,
                    ),
                    note=_C7_PG_ROUTE_NOTE,
                )
            )
            continue
        if cell_id == "C7.3" and projector_driver is not None:
            binding = _c7_binding(cell_id=cell_id, project_scope_digest=scope)
            handler = C7_3ProjectorDriverHandler(
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
                    family_id=C7_FAMILY_ID,
                    status="INSTALLED",
                    operation_contract_refs=operation_contract_refs,
                    handler_binding_digest=handler.handler_binding_digest,
                    recovery_binding_ref=recovery_binding_ref,
                    required_wiring=required_wiring,
                    note=_C7_PROJECTOR_DRIVER_INSTALLED_NOTE,
                )
            )
            rollback_bindings.append(
                RollbackBindingDeclaration(
                    cell_id=cell_id,
                    status="PRESENT",
                    binding_refs=(
                        _C7_PROJECTOR_DRIVER_MODULE,
                        _C7_PROJECTION_OFFSETS_MODULE,
                        _C7_DOCUMENT_READBACK_MODULE,
                    ),
                    note=_C7_PG_ROUTE_NOTE,
                )
            )
            contracts = _c7_3_projector_contracts(projector_driver)
            projector_registry = ProjectorRegistry(
                revision=0,
                incarnation=PROJECTOR_REGISTRY_INCARNATION,
                projectors=contracts,
            )
            continue
        option_field = _C7_ROUTE_OPTION_FIELDS[cell_id]
        closure = getattr(opts, option_field)
        if closure is None:
            cells.append(
                CellBinding(
                    cell_id=cell_id,
                    family_id=C7_FAMILY_ID,
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
                    note=(C7_ROLLBACK_GAP_NOTE + "; " + _C7_GAP_DETAILS[cell_id]),
                )
            )
            continue

        binding = _c7_binding(cell_id=cell_id, project_scope_digest=scope)
        handler = _c7_route_handler(
            cell_id=cell_id,
            closure=closure,
            binding=binding,
        )
        assert handler.handler_binding_digest == binding.binding_digest
        handlers.append(handler)
        cells.append(
            CellBinding(
                cell_id=cell_id,
                family_id=C7_FAMILY_ID,
                status="INSTALLED",
                operation_contract_refs=operation_contract_refs,
                handler_binding_digest=handler.handler_binding_digest,
                recovery_binding_ref=recovery_binding_ref,
                required_wiring=required_wiring,
                note=_C7_INSTALLED_NOTES[cell_id],
            )
        )
        rollback_bindings.append(
            RollbackBindingDeclaration(
                cell_id=cell_id,
                status="PRESENT",
                binding_refs=_C7_ROLLBACK_REFS[cell_id],
                note=_C7_PURE_ROUTE_NOTE,
            )
        )

    return FamilyAssembly(
        family_id=C7_FAMILY_ID,
        cells=tuple(cells),
        handlers=tuple(handlers),
        rollback_bindings=tuple(rollback_bindings),
        projector_registry=projector_registry,
    )


def build_deterministic_c7_rollback_options(
    project_scope_digest: str,
) -> C7AssemblyOptions:
    """Build the deterministic local C7 rollback-route fixture closures."""

    require_assembly_digest(
        project_scope_digest,
        "C7 rollback options project scope digest",
    )
    submission = C7IngestSubmission(
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
    reconciliation_decision = C7ReconciliationDecision(
        new_attempt_allowed=False,
        requirement=(
            "exact non-start proof plus current authority required before "
            "any new attempt"
        ),
        reason=(
            "deterministic local rollback reconciliation fixture; new attempt forbidden"
        ),
    )
    return C7AssemblyOptions(
        submission=submission,
        commit_readback=commit_readback,
        projection_diff=projection_diff,
        reconciliation_decision=reconciliation_decision,
    )


__all__ = [
    "C7_AUTHORITY_REQUIREMENT_DIGEST",
    "C7_CELL_SPECS",
    "C7_DEPLOYMENT_CATALOG_DIGEST",
    "C7_FAMILY_ID",
    "C7_ROLLBACK_GAP_NOTE",
    "C7CanonicalWriteClosure",
    "C7ProjectorDriverClosure",
    "C7_1StageCandidateRollbackRouteHandler",
    "C7_2CanonicalCommitWriteHandler",
    "C7_2CommitReadbackRollbackRouteHandler",
    "C7_3ProjectionDiffRollbackRouteHandler",
    "C7_3ProjectorDriverHandler",
    "C7_4ReconcileRollbackRouteHandler",
    "build_c7_assembly",
    "build_deterministic_c7_rollback_options",
]
