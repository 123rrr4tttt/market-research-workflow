"""Task/session observation assembly and projector registration.

Session, runtime-run and process observations are read-only projection facades.
When the run owner supplies
an exact per-run source key (source_ref and source_incarnation), the cell is
installed through a pure ``ProjectorRegistry`` registration digest only; the
registration adopts no PostgreSQL write.  Without a per-run key the cell stays
``PROJECTOR_WIRING_DECLARED``.

Effect reconciliation is installed only when the caller supplies an exact
:class:`TaskEffectReconcileRouteBinding` in :class:`TaskObservationAssemblyOptions`.  The route
handler genuinely invokes ``EffectReconciler.reconcile`` against a
deterministic read-only fixture; it never writes to a database, adopts an
outcome or changes authority.  The durable PostgreSQL RuntimeNode attempt path
is still unproven and stays recorded in every reconciliation note.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated

from app.successor_runtime.assembly.base import (
    PROJECTOR_REGISTRY_INCARNATION,
    TaskObservationAssemblyOptions,
    CellBinding,
    FamilyAssembly,
    ProjectorSourceKey,
    ProjectorWiring,
    RollbackBindingDeclaration,
    local_assembly_scope_digest,
    require_assembly_digest,
    sha256_hex,
    successor_binding,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.line_event_readback_port import (
    LineEventReadbackRecord,
)
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
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)
from app.successor_runtime.runtime.process_observation import (
    try_join_process_observations,
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
    AGENT_SESSION_PROJECTOR_ID,
    AGENT_SESSION_PROJECTOR_VERSION,
    AgentSessionSnapshot,
    PostgresAgentSessionReadAdapter,
)
from app.successor_runtime.substrate.projections.legacy_process import (
    LINE_EVENT_READBACK_PROJECTOR_REF,
    PROCESS_OBSERVATION_PROJECTOR_ID,
    PROCESS_OBSERVATION_PROJECTOR_VERSION,
    ProcessObservationProjection,
    project_line_event_readbacks,
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
                    "PROCESS_OBSERVATION_CELL_ID",
    "RUN_OBSERVATION_CELL_ID",
    "SESSION_OBSERVATION_CELL_ID",
    "TASK_EFFECT_RECONCILE_CELL_ID",
    "TASK_EFFECT_RECONCILE_DURABLE_ATTEMPT_NODE_NOT_PROVEN",
    "TASK_OBSERVATION_FAMILY_ID",
    "_registered_projector_cells",
        "build_task_observation_assembly",
        "validate_task_observation_assembly_native_definition",
    "build_deterministic_reconciliation_binding",
]

TASK_OBSERVATION_FAMILY_ID = "task.observation.v1"
SESSION_OBSERVATION_CELL_ID = "task.session-observation.project.v1"
TASK_EFFECT_RECONCILE_CELL_ID = "runtime.effect.reconcile.v1"
RUN_OBSERVATION_CELL_ID = "runtime.event.project.v1"
PROCESS_OBSERVATION_CELL_ID = "process.observation.project.v1"
TASK_EFFECT_RECONCILE_DURABLE_ATTEMPT_NODE_NOT_PROVEN = (
    "TASK_EFFECT_RECONCILE_DURABLE_ATTEMPT_NODE_NOT_PROVEN"
)
# Historical C5 identifier retained for explicit old-byte readers only.
_HISTORICAL_TASK_FRAGMENT = (
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

_PROCESS_OBSERVATION_SOURCE_KIND = "process_observations"

_SESSION_PROJECTION_ID = "mrw.task.session-observation.projection.v1"
_RUN_PROJECTION_ID = "mrw.runtime.run-observation.projection.v1"
_PROCESS_PROJECTION_ID = "mrw.process-observation.projection.v1"
_RUNTIME_RUN_PROJECTION_SCHEMA = "mrw.runtime.run-projection.v1"
_AGENT_SESSION_SNAPSHOT_SCHEMA = AgentSessionSnapshot.model_fields[
    "schema_version"
].default
_PROCESS_OBSERVATION_PROJECTION_SCHEMA = ProcessObservationProjection.model_fields[
    "schema_version"
].default

_RUN_SUPPLIED_SOURCE_NOTE = (
    "exact per-run source key supplied by the run; registry registration pending"
)

_REGISTRY_ONLY_NOTE_MARKER = "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED"
_PROJECTOR_CELL_OPERATION_CONTRACT_REFS: dict[str, tuple[str, ...]] = {
    SESSION_OBSERVATION_CELL_ID: ("task.session-observation.project.v1",),
    RUN_OBSERVATION_CELL_ID: ("runtime.event.project.v1",),
    PROCESS_OBSERVATION_CELL_ID: ("process.observation.project.v1",),
}
_PROJECTOR_CELL_RECOVERY_REFS: dict[str, str] = {
    SESSION_OBSERVATION_CELL_ID: "mrw.task.session-observation.recovery.v1",
    RUN_OBSERVATION_CELL_ID: "mrw.task.run-observation.recovery.v1",
    PROCESS_OBSERVATION_CELL_ID: "mrw.process-observation.recovery.v1",
}
_PROJECTOR_CELL_REQUIRED_WIRING: dict[str, tuple[str, ...]] = {
    SESSION_OBSERVATION_CELL_ID: ("ProjectorRegistry registration", "session/task journal replay binding"),
    RUN_OBSERVATION_CELL_ID: ("ProjectorRegistry registration", "projection offset owner binding"),
    PROCESS_OBSERVATION_CELL_ID: ("ProjectorRegistry registration", "process observation source binding"),
}

_TASK_EFFECT_RECONCILE_READBACK_INTERPRETER_ID = (
    "mrw.task.effect-reconcile.readback.v1"
)
_TASK_EFFECT_RECONCILE_READBACK_PROVIDER_ID = (
    "fixture.task-effect-reconcile-readback.v1"
)
_PROCESS_LINE_EVENT_OPERATION_DIGEST = sha256_hex("line_event.readback.project.v1")
_PROCESS_LINE_EVENT_INTERPRETER_DIGEST = sha256_hex(
    "mrw.process.line-event-readback.interpreter.v1"
)
_PROCESS_LINE_EVENT_AUTHORITY_DIGEST = sha256_hex(
    "mrw.process.line-event-readback.authority.v1"
)


def _projector_wirings() -> tuple[ProjectorWiring, ...]:
    return (
        ProjectorWiring(
            cell_id=SESSION_OBSERVATION_CELL_ID,
            projector_id=AGENT_SESSION_PROJECTOR_ID,
            projector_version=AGENT_SESSION_PROJECTOR_VERSION,
            source_kind=PostgresAgentSessionReadAdapter.source_kind,
            projection_id=_SESSION_PROJECTION_ID,
            projection_schema_ref=_AGENT_SESSION_SNAPSHOT_SCHEMA,
            note=(
                "PostgresAgentSessionReadAdapter declared; " + _RUN_SUPPLIED_SOURCE_NOTE
            ),
        ),
        ProjectorWiring(
            cell_id=RUN_OBSERVATION_CELL_ID,
            projector_id=PostgresRuntimeRunProjector.projector_id,
            projector_version=PostgresRuntimeRunProjector.projector_version,
            source_kind=PostgresRuntimeRunProjector.source_kind,
            projection_id=_RUN_PROJECTION_ID,
            projection_schema_ref=_RUNTIME_RUN_PROJECTION_SCHEMA,
            note=("PostgresRuntimeRunProjector declared; " + _RUN_SUPPLIED_SOURCE_NOTE),
        ),
        ProjectorWiring(
            cell_id=PROCESS_OBSERVATION_CELL_ID,
            projector_id=PROCESS_OBSERVATION_PROJECTOR_ID,
            projector_version=PROCESS_OBSERVATION_PROJECTOR_VERSION,
            source_kind=_PROCESS_OBSERVATION_SOURCE_KIND,
            projection_id=_PROCESS_PROJECTION_ID,
            projection_schema_ref=_PROCESS_OBSERVATION_PROJECTION_SCHEMA,
            note=("try_join_process_observations declared; " + _RUN_SUPPLIED_SOURCE_NOTE),
        ),
    )


def _declared_projector_cell(wiring: ProjectorWiring) -> CellBinding:
    return CellBinding(
        cell_id=wiring.cell_id,
        family_id=TASK_OBSERVATION_FAMILY_ID,
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
    """Build observation projector cells and a pure per-run registry."""

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
            family_id=TASK_OBSERVATION_FAMILY_ID,
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
            cell_id=SESSION_OBSERVATION_CELL_ID,
            status="PRESENT",
            binding_refs=(_HISTORICAL_TASK_FRAGMENT, _LEGACY_AGENT_SESSIONS),
        ),
        RollbackBindingDeclaration(
            cell_id=TASK_EFFECT_RECONCILE_CELL_ID,
            status="PRESENT",
            binding_refs=(_HISTORICAL_TASK_FRAGMENT, _LEGACY_EFFECT_ATTEMPTS),
        ),
        RollbackBindingDeclaration(
            cell_id=RUN_OBSERVATION_CELL_ID,
            status="PRESENT",
            binding_refs=(_HISTORICAL_TASK_FRAGMENT, _LEGACY_AGENT_SESSIONS),
        ),
        RollbackBindingDeclaration(
            cell_id=PROCESS_OBSERVATION_CELL_ID,
            status="PRESENT",
            binding_refs=(_HISTORICAL_TASK_FRAGMENT, _LEGACY_PROCESS_OBSERVATIONS),
        ),
    )


@dataclass(frozen=True, slots=True)
class TaskEffectReconcileRouteBinding:
    """Exact readback-only reconciliation route identity."""

    operation_contract_digest: str
    interpreter_profile_digest: str
    deployment_catalog_digest: str
    authority_requirement_digest: str
    readback_profile_ref: str

    def __post_init__(self) -> None:
        require_assembly_digest(
            self.operation_contract_digest,
            "task effect-reconcile operation contract digest",
        )
        require_assembly_digest(
            self.interpreter_profile_digest,
            "task effect-reconcile interpreter profile digest",
        )
        require_assembly_digest(
            self.deployment_catalog_digest,
            "task effect-reconcile deployment catalog digest",
        )
        require_assembly_digest(
            self.authority_requirement_digest,
            "task effect-reconcile authority requirement digest",
        )
        if not str(self.readback_profile_ref or "").strip():
            raise ValueError("task effect-reconcile readback_profile_ref is required")


def _task_effect_reconcile_recovery_binding(
    binding: TaskEffectReconcileRouteBinding,
) -> RecoveryBinding:
    return RecoveryBinding.from_content(
        recovery_handler_id="mrw.runtime.effect-reconcile.readback-route.v1",
        recovery_handler_version="1.0.0",
        interpreter_profile_digest=binding.interpreter_profile_digest,
        authoritative_readback_profile_ref=binding.readback_profile_ref,
    )


@dataclass(frozen=True, slots=True)
class _TaskEffectReconcileReadbackFixture:
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
            raise ReconciliationError(
                "task effect-reconcile readback fixture attempt drift"
            )
        return self.evidence

    def prove_not_started(self, attempt: EffectAttemptObservation) -> object:
        return None


@dataclass(frozen=True, slots=True)
class TaskEffectReconcileRouteHandler(RuntimeHandler):
    """Readback-only reconciliation handler over the exact EffectReconciler."""

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
            raise DefiniteInterpreterFailure(
                "TASK_EFFECT_RECONCILE_CLAIM_ASSIGNMENT_BINDING_DRIFT"
            )
        if claim.handler_binding_digest != assignment.handler_binding_digest:
            raise DefiniteInterpreterFailure(
                "TASK_EFFECT_RECONCILE_CLAIM_HANDLER_BINDING_DRIFT"
            )
        if (
            assignment.handler_binding_digest != self.handler_binding_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
            or assignment.deployment_catalog_digest != self.deployment_catalog_digest
            or getattr(assignment.handler_binding, "interpreter_profile_digest", None)
            != self.interpreter_profile_digest
        ):
            raise DefiniteInterpreterFailure(
                "EXACT_TASK_EFFECT_RECONCILE_ROUTE_HANDLER_BINDING_DRIFT"
            )

        attempt, fixture_assignment = self._reconciliation_fixture()
        fixture = _TaskEffectReconcileReadbackFixture(
            interpreter_id=_TASK_EFFECT_RECONCILE_READBACK_INTERPRETER_ID,
            interpreter_version="1.0.0",
            provider_id=_TASK_EFFECT_RECONCILE_READBACK_PROVIDER_ID,
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
                receipt_ref="receipt:readback:task-effect-reconcile-fixture-v1",
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
            interpreter_id=_TASK_EFFECT_RECONCILE_READBACK_INTERPRETER_ID,
            interpreter_version="1.0.0",
            provider_id=_TASK_EFFECT_RECONCILE_READBACK_PROVIDER_ID,
            provider_version="1.0.0",
            external_idempotency_key="idem:i1-c5-2:001",
            authoritative_readback_locator=self.readback_profile_ref,
        )
        return attempt, assignment


@dataclass(frozen=True, slots=True)
class ProcessLineEventReadbackRouteHandler(RuntimeHandler):
    """Read-only line-event/readback projection route handler."""

    handler_binding_digest: str
    interpreter_profile_digest: str
    operation_contract_digest: str
    deployment_catalog_digest: str
    records: tuple[LineEventReadbackRecord, ...]

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        if claim.assignment_digest != assignment.assignment_digest:
            raise DefiniteInterpreterFailure(
                "PROCESS_LINE_EVENT_CLAIM_ASSIGNMENT_BINDING_DRIFT"
            )
        if (
            assignment.handler_binding_digest != self.handler_binding_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
            or assignment.deployment_catalog_digest != self.deployment_catalog_digest
        ):
            raise DefiniteInterpreterFailure(
                "EXACT_PROCESS_LINE_EVENT_BINDING_DRIFT"
            )
        rows = project_line_event_readbacks(self.records)
        return InterpreterOutcome.succeeded(
            content_digest(rows),
            receipt_ref="receipt:process-line-event-readback.v1",
        )


def build_deterministic_reconciliation_binding(
    project_scope_digest: str,
) -> Annotated[
    TaskEffectReconcileRouteBinding,
    "kit:prepared-command effect_boundary=successor_runtime.c5_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """Build the deterministic task effect-reconcile route binding."""

    require_assembly_digest(
        project_scope_digest,
        "task effect-reconcile binding project scope digest",
    )
    return TaskEffectReconcileRouteBinding(
        operation_contract_digest=sha256_hex("runtime.effect.reconcile.v1"),
        interpreter_profile_digest=sha256_hex(
            "mrw.task.effect-reconcile.interpreter.v1"
        ),
        deployment_catalog_digest=sha256_hex(
            "mrw.task.observation.deployment-catalog.v1"
        ),
        authority_requirement_digest=sha256_hex(
            "mrw.task.effect-reconcile.authority.v1"
        ),
        readback_profile_ref="readback-profile:task-observation.v1",
    )


def _resolve_task_observation_native_definition(
    native_definition: object | None,
) -> object:
    """Resolve one typed author definition; the default source is authoritative."""

    from app.successor_runtime.runtime.task_observation_native_contribution import (
        TaskObservationNativeDefinition,
        DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE,
        compile_task_observation_native_contribution,
    )

    if native_definition is None:
        native_result = compile_task_observation_native_contribution(DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE)
        if not isinstance(native_result, TaskObservationNativeDefinition):
            native_definition = getattr(native_result, "definition", native_result)
        else:
            return native_result
    candidate = getattr(native_definition, "definition", native_definition)
    if not isinstance(candidate, TaskObservationNativeDefinition):
        raise TypeError(
            "task observation assembly native_definition must be a TaskObservationNativeDefinition"
        )
    return candidate


def validate_task_observation_assembly_native_definition(
    definition: object,
    assembly: object,
) -> None:
    """Validate lowered authorities against the author-declared assembly."""

    from app.successor_runtime.runtime.task_observation_native_contribution import (
        ASSEMBLY_CELL_IDS,
        TaskObservationNativeDefinition,
    )

    if not isinstance(definition, TaskObservationNativeDefinition):
        raise TypeError("validate_task_observation_assembly_native_definition requires TaskObservationNativeDefinition")
    if not isinstance(assembly, FamilyAssembly) or assembly.family_id != TASK_OBSERVATION_FAMILY_ID:
        raise ValueError(
            "task observation native validator requires the business FamilyAssembly"
        )
    if tuple(cell.cell_id for cell in assembly.cells) != ASSEMBLY_CELL_IDS:
        raise ValueError("task observation author cell order drift")
    if (
        definition.reconciler is not EffectReconciler
        or definition.session_projector is not PostgresAgentSessionReadAdapter
        or definition.runtime_projector is not PostgresRuntimeRunProjector
        or definition.process_observation_projector
        is not try_join_process_observations
        or definition.line_event_projector_ref
        != LINE_EVENT_READBACK_PROJECTOR_REF
    ):
        raise ValueError("task observation native authority identity drift")
    if any(
        getattr(definition.source, field, None)
        for field in (
            "production_canonical_write",
            "durable_evidence_authorized",
            "registry_metadata_is_execution_evidence",
        )
    ):
        raise ValueError("task observation native source adopted a forbidden authority")
    if definition.source.requires_reconciliation_route and not any(
        isinstance(handler, TaskEffectReconcileRouteHandler)
        for handler in assembly.handlers
    ):
        raise ValueError(
            "task effect-reconcile route is not installed in the real assembly"
        )


def build_task_observation_assembly(
    *,
    options: TaskObservationAssemblyOptions | None = None,
    projector_source_keys: Mapping[str, ProjectorSourceKey] | None = None,
    native_definition: object | None = None,
) -> Annotated[
    FamilyAssembly,
    "kit:prepared-command effect_boundary=successor_runtime.c5_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """Build task observations with registry registration and reconciliation."""

    opts = options or TaskObservationAssemblyOptions()
    from app.successor_runtime.runtime.task_observation_native_contribution import (
        ASSEMBLY_CELL_IDS,
    )

    definition = _resolve_task_observation_native_definition(native_definition)
    native_keys = definition.source.projector_key_map  # type: ignore[union-attr]
    supported_keys = set(ASSEMBLY_CELL_IDS) - {TASK_EFFECT_RECONCILE_CELL_ID}
    unsupported_native_keys = set(native_keys or {}) - supported_keys
    if unsupported_native_keys:
        raise ValueError(
            "task observation native projector source cell drift: "
            + ", ".join(sorted(unsupported_native_keys))
        )
    shared_source_keys = projector_source_keys or {}
    historical_c5_keys = set(shared_source_keys) & {"C5.1", "C5.2", "C5.3", "C5.4"}
    if historical_c5_keys:
        raise ValueError(
            "historical C5 projector source keys are not current task observation cells: "
            + ", ".join(sorted(historical_c5_keys))
        )
    family_source_keys = {
        cell_id: key
        for cell_id, key in shared_source_keys.items()
        if cell_id in supported_keys
    }
    conflicting_keys = set(native_keys or {}) & set(family_source_keys)
    if conflicting_keys:
        raise ValueError(
            "task observation native projector source drift: "
            + ", ".join(sorted(conflicting_keys))
        )
    resolved_source_keys = {
        **(native_keys or {}),
        **family_source_keys,
    }
    projector_cells, projector_registry = _registered_projector_cells(
        resolved_source_keys
    )
    if opts.line_event_readback_records is None and (
        definition.source.line_event_readback_records is not None
    ):
        opts = TaskObservationAssemblyOptions(
            reconciliation_binding=opts.reconciliation_binding,
            line_event_readback_records=(
                definition.source.line_event_readback_records
            ),
            note=opts.note + "; native definition supplied",
        )
    binding = opts.reconciliation_binding
    if binding is not None and not isinstance(
        binding, TaskEffectReconcileRouteBinding
    ):
        raise TypeError(
            "reconciliation_binding must be a TaskEffectReconcileRouteBinding"
        )

    if binding is not None:
        recovery = _task_effect_reconcile_recovery_binding(binding)
        handler = TaskEffectReconcileRouteHandler(
            handler_binding_digest=recovery.binding_digest,
            interpreter_profile_digest=binding.interpreter_profile_digest,
            operation_contract_digest=binding.operation_contract_digest,
            deployment_catalog_digest=binding.deployment_catalog_digest,
            authority_requirement_digest=binding.authority_requirement_digest,
            readback_profile_ref=binding.readback_profile_ref,
        )
        reconcile_status = "INSTALLED"
        reconcile_digest = handler.handler_binding_digest
        reconcile_note = (
            "INSTALLED: task effect-reconcile explicit route binding; "
            "LOCAL_OFFLINE deterministic readback-only fixture; "
            "EffectReconciler.reconcile called; no DB write/adopt/"
            "authority change; "
            + TASK_EFFECT_RECONCILE_DURABLE_ATTEMPT_NODE_NOT_PROVEN
        )
        handlers = (handler,)
    else:
        reconcile_status = "FIXTURE_CLOSURE_REQUIRED"
        reconcile_digest = None
        reconcile_note = (
            "FIXTURE_CLOSURE_REQUIRED: explicit task effect-reconcile "
            "reconciliation binding not supplied; missing "
            "options.reconciliation_binding fields: "
            "operation_contract_digest, interpreter_profile_digest, "
            "deployment_catalog_digest, authority_requirement_digest, "
            "readback_profile_ref; "
            + TASK_EFFECT_RECONCILE_DURABLE_ATTEMPT_NODE_NOT_PROVEN
        )
        handlers = ()

    route_handlers = list(handlers)
    line_event_handler = None
    if opts.line_event_readback_records is not None:
        records = tuple(opts.line_event_readback_records)
        line_binding = successor_binding(
            operation_contract_digest=_PROCESS_LINE_EVENT_OPERATION_DIGEST,
            interpreter_profile_digest=_PROCESS_LINE_EVENT_INTERPRETER_DIGEST,
            deployment_catalog_digest=sha256_hex(
                "mrw.task.observation.deployment-catalog.v1"
            ),
            project_scope_digest=local_assembly_scope_digest(),
            authority_requirement_digest=_PROCESS_LINE_EVENT_AUTHORITY_DIGEST,
        )
        line_event_handler = ProcessLineEventReadbackRouteHandler(
            handler_binding_digest=line_binding.binding_digest,
            interpreter_profile_digest=line_binding.interpreter_profile_digest,
            operation_contract_digest=line_binding.operation_contract_digest,
            deployment_catalog_digest=line_binding.deployment_catalog_digest,
            records=records,
        )
        route_handlers.append(line_event_handler)

    process_cell = projector_cells[PROCESS_OBSERVATION_CELL_ID]
    if line_event_handler is not None:
        process_cell = CellBinding(
            cell_id=PROCESS_OBSERVATION_CELL_ID,
            family_id=TASK_OBSERVATION_FAMILY_ID,
            status="PROJECTOR_WIRING_DECLARED",
            operation_contract_refs=_PROJECTOR_CELL_OPERATION_CONTRACT_REFS[
                PROCESS_OBSERVATION_CELL_ID
            ],
            recovery_binding_ref=_PROJECTOR_CELL_RECOVERY_REFS[
                PROCESS_OBSERVATION_CELL_ID
            ],
            required_wiring=_PROJECTOR_CELL_REQUIRED_WIRING[
                PROCESS_OBSERVATION_CELL_ID
            ],
            note=(
                process_cell.note
                + "; line-event readback route handler carried by family; "
                "ProjectorRegistry registration stays per-run"
            ),
        )

    cells = (
        projector_cells[SESSION_OBSERVATION_CELL_ID],
        CellBinding(
            cell_id=TASK_EFFECT_RECONCILE_CELL_ID,
            family_id=TASK_OBSERVATION_FAMILY_ID,
            status=reconcile_status,
            operation_contract_refs=("runtime.effect.reconcile.v1",),
            handler_binding_digest=reconcile_digest,
            recovery_binding_ref="mrw.runtime.effect-reconcile.recovery.v1",
            required_wiring=(
                "effect reconcile handler binding",
                "readback policy binding",
            ),
            note=reconcile_note,
        ),
        projector_cells[RUN_OBSERVATION_CELL_ID],
        process_cell,
    )
    return FamilyAssembly(
        family_id=TASK_OBSERVATION_FAMILY_ID,
        cells=cells,
        handlers=tuple(route_handlers),
        projector_wiring=_projector_wirings(),
        projector_registry=projector_registry,
        rollback_bindings=_rollback_bindings(),
    )

