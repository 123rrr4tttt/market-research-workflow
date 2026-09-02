"""C5 family assembly: projector wiring, registry registration and C5.2.

C5.1/C5.3/C5.4 are read-only projection facades.  When the run owner supplies
an exact per-run source key (source_ref and source_incarnation), the cell is
installed through a pure ``ProjectorRegistry`` registration digest only; the
registration adopts no PostgreSQL write.  Without a per-run key the cell stays
``PROJECTOR_WIRING_DECLARED``.

C5.2 is installed only when the caller supplies an exact
:class:`C5_2ReconcileRouteBinding` in :class:`C5AssemblyOptions`.  The route
handler genuinely invokes ``EffectReconciler.reconcile`` against a
deterministic read-only fixture; it never writes to a database, adopts an
outcome or changes authority.  The durable PostgreSQL RuntimeNode attempt path
is still unproven and stays recorded as ``C5_2_DURABLE_ATTEMPT_NODE_NOT_PROVEN``
in every C5.2 note.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.successor_runtime.assembly.base import (
    PROJECTOR_REGISTRY_INCARNATION,
    C5AssemblyOptions,
    CellBinding,
    FamilyAssembly,
    ProjectorSourceKey,
    ProjectorWiring,
    RollbackBindingDeclaration,
    require_assembly_digest,
    sha256_hex,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    HandlerBindingKind,
    RecoveryBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    RuntimeExecutionContext,
    RuntimeHandler,
)
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    EffectAttemptObservation,
    EffectReconciler,
    ReconciliationError,
    ReconciliationHandlerOutcome,
    ReconciliationState,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.projections.agent_session import (
    AgentSessionSnapshot,
    PostgresAgentSessionReadAdapter,
)
from app.successor_runtime.substrate.projections.legacy_process import (
    LegacyProcessObservationProjection,
)
from app.successor_runtime.substrate.projections.registry import (
    ProjectorContract,
    ProjectorRegistry,
    validate_projector_contract,
)
from app.successor_runtime.substrate.projections.runtime_run import (
    PostgresRuntimeRunProjector,
)

__all__ = [
    "C5_2_DURABLE_ATTEMPT_NODE_NOT_PROVEN",
    "C5_2ReconcileRouteBinding",
    "C5_2ReconcileRouteHandler",
    "_registered_projector_cells",
    "build_c5_assembly",
    "build_deterministic_reconciliation_binding",
]

C5_2_DURABLE_ATTEMPT_NODE_NOT_PROVEN = "C5_2_DURABLE_ATTEMPT_NODE_NOT_PROVEN"

_C5_FRAGMENT = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C5.json"
)
_LEGACY_AGENT_SESSIONS = "main/backend/app/successor_migration/legacy_agent_sessions.py"
_LEGACY_EFFECT_ATTEMPTS = (
    "main/backend/app/successor_migration/legacy_effect_attempts.py"
)
_LEGACY_PROCESS_OBSERVATIONS = (
    "main/backend/app/successor_migration/legacy_process_observations.py"
)

_C5_1_PROJECTOR_ID = "successor.agent_session.journal_projection.v1"
_C5_4_PROJECTOR_ID = "successor.legacy_process_observation_join.v1"
_C5_4_SOURCE_KIND = "legacy_process_observations"

_PROJECTION_ID_C5_1 = "projection.agent-session.v1"
_PROJECTION_ID_C5_3 = "projection.runtime-run.v1"
_PROJECTION_ID_C5_4 = "projection.legacy-process-observation.v1"
_RUNTIME_RUN_PROJECTION_SCHEMA = "mrw.runtime.run-projection.v1"
_AGENT_SESSION_SNAPSHOT_SCHEMA = AgentSessionSnapshot.model_fields[
    "schema_version"
].default
_LEGACY_PROCESS_PROJECTION_SCHEMA = LegacyProcessObservationProjection.model_fields[
    "schema_version"
].default

_RUN_SUPPLIED_SOURCE_NOTE = (
    "exact per-run source key supplied by the run; registry registration pending"
)

_REGISTRY_ONLY_NOTE_MARKER = "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED"
_PROJECTOR_CELL_OPERATION_CONTRACT_REFS: dict[str, tuple[str, ...]] = {
    "C5.1": ("agent_session.task_transition.v1",),
    "C5.3": ("runtime.event.project.v1",),
    "C5.4": ("legacy.runtime_observation.project.v1",),
}
_PROJECTOR_CELL_RECOVERY_REFS: dict[str, str] = {
    "C5.1": "mrw.successor.agent-session.c5-1.recovery.v1",
    "C5.3": "mrw.successor.runtime.c5-3.recovery.v1",
    "C5.4": "mrw.successor.runtime.c5-4.recovery.v1",
}
_PROJECTOR_CELL_REQUIRED_WIRING: dict[str, tuple[str, ...]] = {
    "C5.1": ("ProjectorRegistry 注册", "legacy session/task replay binding"),
    "C5.3": ("ProjectorRegistry 注册", "projection offset owner 绑定"),
    "C5.4": ("ProjectorRegistry 注册", "observation source binding"),
}

_C5_2_READBACK_INTERPRETER_ID = "successor.c5.reconciliation.readback.v1"
_C5_2_READBACK_PROVIDER_ID = "provider.c5-2.readback-fixture"


def _projector_wirings() -> tuple[ProjectorWiring, ...]:
    return (
        ProjectorWiring(
            cell_id="C5.1",
            projector_id=_C5_1_PROJECTOR_ID,
            projector_version="1.0.0",
            source_kind=PostgresAgentSessionReadAdapter.source_kind,
            projection_id=_PROJECTION_ID_C5_1,
            projection_schema_ref=_AGENT_SESSION_SNAPSHOT_SCHEMA,
            note=(
                "PostgresAgentSessionReadAdapter declared; " + _RUN_SUPPLIED_SOURCE_NOTE
            ),
        ),
        ProjectorWiring(
            cell_id="C5.3",
            projector_id=PostgresRuntimeRunProjector.projector_id,
            projector_version=PostgresRuntimeRunProjector.projector_version,
            source_kind=PostgresRuntimeRunProjector.source_kind,
            projection_id=_PROJECTION_ID_C5_3,
            projection_schema_ref=_RUNTIME_RUN_PROJECTION_SCHEMA,
            note=("PostgresRuntimeRunProjector declared; " + _RUN_SUPPLIED_SOURCE_NOTE),
        ),
        ProjectorWiring(
            cell_id="C5.4",
            projector_id=_C5_4_PROJECTOR_ID,
            projector_version="1.0.0",
            source_kind=_C5_4_SOURCE_KIND,
            projection_id=_PROJECTION_ID_C5_4,
            projection_schema_ref=_LEGACY_PROCESS_PROJECTION_SCHEMA,
            note=("join_process_observations declared; " + _RUN_SUPPLIED_SOURCE_NOTE),
        ),
    )


def _declared_projector_cell(wiring: ProjectorWiring) -> CellBinding:
    return CellBinding(
        cell_id=wiring.cell_id,
        family_id="C5",
        status="PROJECTOR_WIRING_DECLARED",
        operation_contract_refs=_PROJECTOR_CELL_OPERATION_CONTRACT_REFS[wiring.cell_id],
        recovery_binding_ref=_PROJECTOR_CELL_RECOVERY_REFS[wiring.cell_id],
        required_wiring=_PROJECTOR_CELL_REQUIRED_WIRING[wiring.cell_id],
        note=(
            "缺 per-run source_ref/source_incarnation key；"
            "PROJECTOR_WIRING_DECLARED 保持；no PostgreSQL write adopted"
        ),
    )


def _registered_projector_cells(
    projector_source_keys: Mapping[str, ProjectorSourceKey] | None,
) -> tuple[dict[str, CellBinding], ProjectorRegistry | None]:
    """Build C5.1/C5.3/C5.4 cells and a pure per-run projector registry."""

    keys = projector_source_keys or {}
    contracts: list[ProjectorContract] = []
    cells: dict[str, CellBinding] = {}
    for wiring in _projector_wirings():
        source_key = keys.get(wiring.cell_id)
        if source_key is None:
            cells[wiring.cell_id] = _declared_projector_cell(wiring)
            continue
        contract = wiring.to_contract(source_key)
        validation = validate_projector_contract(contract)
        if not validation.valid:
            raise ValueError(
                f"{wiring.cell_id} projector contract invalid: "
                + "; ".join(item.message for item in validation.violations)
            )
        digest = wiring.registration_digest(contract)
        contracts.append(contract)
        cells[wiring.cell_id] = CellBinding(
            cell_id=wiring.cell_id,
            family_id="C5",
            status="INSTALLED",
            operation_contract_refs=_PROJECTOR_CELL_OPERATION_CONTRACT_REFS[
                wiring.cell_id
            ],
            handler_binding_digest=digest,
            recovery_binding_ref=_PROJECTOR_CELL_RECOVERY_REFS[wiring.cell_id],
            required_wiring=(),
            note=(
                _REGISTRY_ONLY_NOTE_MARKER + f": {wiring.cell_id} registered; per-run "
                "source_ref/source_incarnation bound; no PostgreSQL write "
                "adopted"
            ),
        )
    registry = (
        ProjectorRegistry(
            revision=0,
            incarnation=PROJECTOR_REGISTRY_INCARNATION,
            projectors=tuple(contracts),
        )
        if contracts
        else None
    )
    return cells, registry


def _rollback_bindings() -> tuple[RollbackBindingDeclaration, ...]:
    return (
        RollbackBindingDeclaration(
            cell_id="C5.1",
            status="PRESENT",
            binding_refs=(_C5_FRAGMENT, _LEGACY_AGENT_SESSIONS),
        ),
        RollbackBindingDeclaration(
            cell_id="C5.2",
            status="PRESENT",
            binding_refs=(_C5_FRAGMENT, _LEGACY_EFFECT_ATTEMPTS),
        ),
        RollbackBindingDeclaration(
            cell_id="C5.3",
            status="PRESENT",
            binding_refs=(_C5_FRAGMENT, _LEGACY_AGENT_SESSIONS),
        ),
        RollbackBindingDeclaration(
            cell_id="C5.4",
            status="PRESENT",
            binding_refs=(_C5_FRAGMENT, _LEGACY_PROCESS_OBSERVATIONS),
        ),
    )


@dataclass(frozen=True, slots=True)
class C5_2ReconcileRouteBinding:
    """Exact readback-only reconciliation route identity for the C5.2 cell."""

    operation_contract_digest: str
    interpreter_profile_digest: str
    deployment_catalog_digest: str
    authority_requirement_digest: str
    readback_profile_ref: str

    def __post_init__(self) -> None:
        require_assembly_digest(
            self.operation_contract_digest,
            "C5.2 operation contract digest",
        )
        require_assembly_digest(
            self.interpreter_profile_digest,
            "C5.2 interpreter profile digest",
        )
        require_assembly_digest(
            self.deployment_catalog_digest,
            "C5.2 deployment catalog digest",
        )
        require_assembly_digest(
            self.authority_requirement_digest,
            "C5.2 authority requirement digest",
        )
        if not str(self.readback_profile_ref or "").strip():
            raise ValueError("C5.2 readback_profile_ref is required")


def _c5_2_recovery_binding(
    binding: C5_2ReconcileRouteBinding,
) -> RecoveryBinding:
    return RecoveryBinding.from_content(
        recovery_handler_id="mrw.successor.c5-2.readback-route.v1",
        recovery_handler_version="1.0.0",
        interpreter_profile_digest=binding.interpreter_profile_digest,
        authoritative_readback_profile_ref=binding.readback_profile_ref,
    )


@dataclass(frozen=True, slots=True)
class _C5_2ReadbackFixture:
    """Deterministic read-only readback fixture; no provider or DB access."""

    interpreter_id: str
    interpreter_version: str
    provider_id: str
    provider_version: str
    evidence: AuthoritativeEffectReadback

    def readback(
        self, attempt: EffectAttemptObservation
    ) -> AuthoritativeEffectReadback:
        if attempt.attempt_id != self.evidence.attempt_id:
            raise ReconciliationError("C5.2 readback fixture attempt drift")
        return self.evidence

    def prove_not_started(self, attempt: EffectAttemptObservation) -> object:
        return None


@dataclass(frozen=True, slots=True)
class C5_2ReconcileRouteHandler(RuntimeHandler):
    """Readback-only C5.2 route handler over the exact EffectReconciler."""

    handler_binding_digest: str
    interpreter_profile_digest: str
    operation_contract_digest: str
    deployment_catalog_digest: str
    authority_requirement_digest: str
    readback_profile_ref: str

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> ReconciliationHandlerOutcome:
        if claim.assignment_digest != assignment.assignment_digest:
            raise DefiniteInterpreterFailure("C5_2_CLAIM_ASSIGNMENT_BINDING_DRIFT")
        if claim.handler_binding_digest != assignment.handler_binding_digest:
            raise DefiniteInterpreterFailure("C5_2_CLAIM_HANDLER_BINDING_DRIFT")
        if (
            assignment.handler_binding_digest != self.handler_binding_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
            or assignment.deployment_catalog_digest != self.deployment_catalog_digest
            or getattr(assignment.handler_binding, "interpreter_profile_digest", None)
            != self.interpreter_profile_digest
        ):
            raise DefiniteInterpreterFailure("EXACT_C5_2_ROUTE_HANDLER_BINDING_DRIFT")

        attempt, fixture_assignment = self._reconciliation_fixture()
        fixture = _C5_2ReadbackFixture(
            interpreter_id=_C5_2_READBACK_INTERPRETER_ID,
            interpreter_version="1.0.0",
            provider_id=_C5_2_READBACK_PROVIDER_ID,
            provider_version="1.0.0",
            evidence=AuthoritativeEffectReadback(
                attempt_id=attempt.attempt_id,
                disposition=EffectDisposition.SUCCEEDED,
                provider_locator=self.readback_profile_ref,
                receipt_digest=sha256_hex("receipt:i1-c5-2:001"),
                observation_digest=sha256_hex("observation:i1-c5-2:001"),
            ),
        )
        result = EffectReconciler().reconcile(
            assignment=fixture_assignment,
            attempt=attempt,
            interpreter=fixture,
        )
        if (
            result.state is ReconciliationState.RESOLVED
            and result.disposition is EffectDisposition.SUCCEEDED
        ):
            return ReconciliationHandlerOutcome(
                result=result,
                output_digest=content_digest(result.model_dump(mode="json")),
                receipt_ref="receipt:readback:c5-2-fixture",
            )
        return ReconciliationHandlerOutcome(result=result)

    def _reconciliation_fixture(
        self,
    ) -> tuple[EffectAttemptObservation, RuntimeAssignment]:
        attempt_id = sha256_hex("attempt:i1-c5-2:001")
        recovery = RecoveryBinding.from_content(
            recovery_handler_id="mrw.successor.c5-2.readback-route.v1",
            recovery_handler_version="1.0.0",
            interpreter_profile_digest=self.interpreter_profile_digest,
            authoritative_readback_profile_ref=self.readback_profile_ref,
        )
        assignment = RuntimeAssignment(
            runtime_protocol_version="1",
            work_item_id="work:i1-c5-2:001",
            assignment_kind=AssignmentKind.RECONCILE,
            project_key="i1-local-c5",
            run_id="run:i1-c5-2:001",
            step_id="step:c5-2:reconcile",
            capability_id="runtime.effect.reconcile.v1",
            operation_contract_ref=OperationContractRef(
                kind="runtime.effect.reconcile.v1",
                contract_version="1.0.0",
                contract_digest=self.operation_contract_digest,
            ),
            operation_contract_digest=self.operation_contract_digest,
            handler_binding_kind=HandlerBindingKind.RECOVERY,
            handler_binding_ref=(f"handler-binding:sha256:{recovery.binding_digest}"),
            handler_binding_digest=recovery.binding_digest,
            handler_binding=recovery,
            program_digest=self.handler_binding_digest,
            deployment_catalog_digest=self.deployment_catalog_digest,
            execution_epoch=1,
            incarnation="inc:i1-c5-2:001",
            input_refs=(),
            queue_eligibility_digest=sha256_hex("queue-eligibility:i1-c5-2:001"),
            resource_policy_epoch=1,
            claim_authority_epoch=1,
            claim_policy_digest=sha256_hex("claim-policy:i1-c5-2:001"),
            expected_step_revision=1,
            reconciliation_attempt_id=attempt_id,
            trace_id="trace:i1-c5-2:001",
        )
        attempt = EffectAttemptObservation(
            attempt_id=attempt_id,
            assignment_digest=assignment.assignment_digest,
            handler_binding_digest=assignment.handler_binding_digest,
            interpreter_profile_digest=self.interpreter_profile_digest,
            interpreter_id=_C5_2_READBACK_INTERPRETER_ID,
            interpreter_version="1.0.0",
            provider_id=_C5_2_READBACK_PROVIDER_ID,
            provider_version="1.0.0",
            external_idempotency_key="idem:i1-c5-2:001",
            authoritative_readback_locator=self.readback_profile_ref,
        )
        return attempt, assignment


def build_deterministic_reconciliation_binding(
    project_scope_digest: str,
) -> C5_2ReconcileRouteBinding:
    """Build the deterministic C5.2 reconciliation route binding."""

    require_assembly_digest(
        project_scope_digest,
        "C5.2 reconciliation binding project scope digest",
    )
    return C5_2ReconcileRouteBinding(
        operation_contract_digest=sha256_hex("runtime.effect.reconcile.v1"),
        interpreter_profile_digest=sha256_hex("successor.c5.reconciliation.v1"),
        deployment_catalog_digest=sha256_hex("mrw.successor.deployment-catalog.c5.v1"),
        authority_requirement_digest=sha256_hex("mrw.successor.c5.authority.v1"),
        readback_profile_ref="readback-profile:p3-c5",
    )


def build_c5_assembly(
    *,
    options: C5AssemblyOptions | None = None,
    projector_source_keys: Mapping[str, ProjectorSourceKey] | None = None,
) -> FamilyAssembly:
    """Build C5 with optional registry registration and the C5.2 route."""

    opts = options or C5AssemblyOptions()
    projector_cells, projector_registry = _registered_projector_cells(
        projector_source_keys
    )
    binding = opts.reconciliation_binding
    if binding is not None and not isinstance(binding, C5_2ReconcileRouteBinding):
        raise TypeError(
            "C5.2 reconciliation_binding must be a C5_2ReconcileRouteBinding"
        )

    if binding is not None:
        recovery = _c5_2_recovery_binding(binding)
        handler = C5_2ReconcileRouteHandler(
            handler_binding_digest=recovery.binding_digest,
            interpreter_profile_digest=binding.interpreter_profile_digest,
            operation_contract_digest=binding.operation_contract_digest,
            deployment_catalog_digest=binding.deployment_catalog_digest,
            authority_requirement_digest=binding.authority_requirement_digest,
            readback_profile_ref=binding.readback_profile_ref,
        )
        c52_status = "INSTALLED"
        c52_digest = handler.handler_binding_digest
        c52_note = (
            "INSTALLED: C5.2 explicit reconciliation route binding; "
            "LOCAL_OFFLINE deterministic readback-only fixture; "
            "EffectReconciler.reconcile called; no DB write/adopt/"
            "authority change; " + C5_2_DURABLE_ATTEMPT_NODE_NOT_PROVEN
        )
        handlers = (handler,)
    else:
        c52_status = "FIXTURE_CLOSURE_REQUIRED"
        c52_digest = None
        c52_note = (
            "FIXTURE_CLOSURE_REQUIRED: REUSE_INFERRED: explicit C5.2 "
            "reconciliation binding not supplied; missing "
            "options.reconciliation_binding fields: "
            "operation_contract_digest, interpreter_profile_digest, "
            "deployment_catalog_digest, authority_requirement_digest, "
            "readback_profile_ref; " + C5_2_DURABLE_ATTEMPT_NODE_NOT_PROVEN
        )
        handlers = ()

    cells = (
        projector_cells["C5.1"],
        CellBinding(
            cell_id="C5.2",
            family_id="C5",
            status=c52_status,
            operation_contract_refs=("runtime.effect.reconcile.v1",),
            handler_binding_digest=c52_digest,
            recovery_binding_ref="mrw.successor.runtime.c5-2.recovery.v1",
            required_wiring=(
                "C5.2 reconcile handler 绑定 legacy attempt kinds",
                "readback policy 接线",
            ),
            note=c52_note,
        ),
        projector_cells["C5.3"],
        projector_cells["C5.4"],
    )
    return FamilyAssembly(
        family_id="C5",
        cells=cells,
        handlers=handlers,
        projector_wiring=_projector_wirings(),
        projector_registry=projector_registry,
        rollback_bindings=_rollback_bindings(),
    )
