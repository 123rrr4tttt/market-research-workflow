"""Authored native-contribution rule over task/session observation authorities.

The rule lowers one explicit source into the ordered task-observation family
assembly.  Reconciliation/readback, runtime/session projection and process
observation remain distinct authority boundaries.  It owns no
domain kernel and does not turn registry metadata or an offline binding into
Program execution evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

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

from app.successor_runtime.assembly.base import ProjectorSourceKey
from app.successor_runtime.assembly.task_observation_assembly import (
    PROCESS_OBSERVATION_CELL_ID,
    RUN_OBSERVATION_CELL_ID,
    SESSION_OBSERVATION_CELL_ID,
    TASK_EFFECT_RECONCILE_CELL_ID,
    TASK_OBSERVATION_FAMILY_ID,
    ProcessLineEventReadbackRouteHandler,
    TaskEffectReconcileRouteHandler,
    build_task_observation_assembly,
    build_deterministic_reconciliation_binding,
)
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    EffectReconciler,
)
from mrw_functorial_kit.core.w07_semantics import runtime_failures

from .ports import PostgresAgentSessionReadAdapter, PostgresRuntimeRunProjector
from .process_observation import (
    LINE_EVENT_READBACK_PROJECTOR_REF,
    PROCESS_OBSERVATION_PROJECTOR_REF,
    try_join_process_observations,
)

if TYPE_CHECKING:
    from app.successor_runtime.assembly.base import TaskObservationAssemblyOptions, FamilyAssembly
else:  # assembly option import remains safe/inert for definition compilation
    from app.successor_runtime.assembly.base import TaskObservationAssemblyOptions, FamilyAssembly


__all__ = [
    "TASK_OBSERVATION_NATIVE_CONTRIBUTION_RULE",
    "TASK_OBSERVATION_NATIVE_RULE_ID",
    "TASK_OBSERVATION_NATIVE_VERIFICATION_INPUTS",
    "TaskObservationAssemblyContext",
    "TaskObservationNativeDefinition",
    "TaskObservationNativeRuntimeBinding",
    "DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE",
    "NON_DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE",
    "TaskObservationAssemblyOptions",
    "TaskObservationCellSource",
    "ASSEMBLY_CELL_IDS",
    "compile_task_observation_native_contribution",
]

TASK_OBSERVATION_NATIVE_RULE_ID: Final = "mrw.task.observation.native-rule.v2"
TASK_OBSERVATION_NATIVE_VERIFICATION_INPUTS: Final = (
    "mrw.task.observation.definition",
    "mrw.task.observation.order",
    "mrw.task.effect-reconciliation",
    "mrw.task.authoritative-readback",
    "mrw.task.projection",
    "mrw.task.observation-authority",
)

TaskObservationCellId = Literal[
    SESSION_OBSERVATION_CELL_ID,
    TASK_EFFECT_RECONCILE_CELL_ID,
    RUN_OBSERVATION_CELL_ID,
    PROCESS_OBSERVATION_CELL_ID,
]
TaskObservationCellRole = Literal[
    "session_observation_projection",
    "effect_reconciliation_readback",
    "runtime_run_projection",
    "process_observation_projection",
]
@dataclass(frozen=True, slots=True)
class TaskObservationCellSource:
    """One typed authority reference and its ordered family role."""

    cell_id: TaskObservationCellId
    role: TaskObservationCellRole
    authority_ref: str
    handler_ref: str | None = None


@dataclass(frozen=True, slots=True)
class TaskObservationNativeSource:
    """The authored offline task-observation migration fact.

    ``projector_source_keys`` are ordinary declarations for the inert assembly
    binding.  A non-empty value authorizes no PostgreSQL write and supplies no
    durable evidence; the source deliberately keeps those flags false.
    """

    contribution_id: str
    owner: str
    cells: tuple[TaskObservationCellSource, ...]
    rollback_refs: tuple[str, ...]
    requires_reconciliation_route: bool = True
    projector_source_keys: tuple[tuple[TaskObservationCellId, ProjectorSourceKey], ...] = ()
    line_event_readback_records: tuple[object, ...] | None = None
    production_canonical_write: bool = False
    durable_evidence_authorized: bool = False
    registry_metadata_is_execution_evidence: bool = False

    @property
    def projector_key_map(self) -> dict[TaskObservationCellId, ProjectorSourceKey]:
        return dict(self.projector_source_keys)


_DEFAULT_RECONCILER_REF = (
    "app.successor_runtime.runtime.reconciliation:EffectReconciler"
)
_DEFAULT_READBACK_REF = (
    "app.successor_runtime.runtime.reconciliation:AuthoritativeEffectReadback"
)
_DEFAULT_SESSION_PROJECTOR_REF = (
    "app.successor_runtime.substrate.projections.agent_session:"
    "PostgresAgentSessionReadAdapter"
)
_DEFAULT_RUNTIME_PROJECTOR_REF = (
    "app.successor_runtime.substrate.projections.runtime_run:"
    "PostgresRuntimeRunProjector"
)
_DEFAULT_PROCESS_OBSERVATION_REF = PROCESS_OBSERVATION_PROJECTOR_REF
_DEFAULT_LINE_EVENT_PROJECTOR_REF = LINE_EVENT_READBACK_PROJECTOR_REF


def _issue_tuple(
    checks: tuple[tuple[bool, str, str], ...],
) -> tuple[NativeBindingIssue, ...]:
    return tuple(
        NativeBindingIssue(path, message) for valid, path, message in checks if not valid
    )


def _definition_issues(source: TaskObservationNativeSource) -> tuple[NativeBindingIssue, ...]:
    expected_cells = (
        TaskObservationCellSource(
            SESSION_OBSERVATION_CELL_ID,
            "session_observation_projection",
            _DEFAULT_SESSION_PROJECTOR_REF,
        ),
        TaskObservationCellSource(
            TASK_EFFECT_RECONCILE_CELL_ID,
            "effect_reconciliation_readback",
            _DEFAULT_RECONCILER_REF,
            _DEFAULT_READBACK_REF,
        ),
        TaskObservationCellSource(
            RUN_OBSERVATION_CELL_ID,
            "runtime_run_projection",
            _DEFAULT_RUNTIME_PROJECTOR_REF,
        ),
        TaskObservationCellSource(
            PROCESS_OBSERVATION_CELL_ID,
            "process_observation_projection",
            _DEFAULT_PROCESS_OBSERVATION_REF,
            _DEFAULT_LINE_EVENT_PROJECTOR_REF,
        ),
    )
    issues = _issue_tuple(
        (
            (
                source.cells == expected_cells,
                "$.source.cells",
                "task observation cells, roles and authority references drifted",
            ),
            (
                len(source.rollback_refs) >= 1,
                "$.source.rollback_refs",
                "rollback binding is empty",
            ),
            (
                source.production_canonical_write is False,
                "$.source.production_canonical_write",
                "native migration does not grant production canonical write",
            ),
            (
                source.durable_evidence_authorized is False,
                "$.source.durable_evidence_authorized",
                "offline native definition does not manufacture durable evidence",
            ),
            (
                source.registry_metadata_is_execution_evidence is False,
                "$.source.registry_metadata_is_execution_evidence",
                "registry metadata is not execution evidence",
            ),
            (
                len(source.projector_source_keys) <= 3,
                "$.source.projector_source_keys",
                "effect reconciliation is not a projector cell",
            ),
            (
                all(
                    cell_id != TASK_EFFECT_RECONCILE_CELL_ID
                    for cell_id, _ in source.projector_source_keys
                ),
                "$.source.projector_source_keys.effect_reconcile",
                "effect reconciliation cannot be registered as a projector",
            ),
            (
                (not source.requires_reconciliation_route)
                or source.cells[1].handler_ref == _DEFAULT_READBACK_REF,
                "$.source.cells.effect_reconcile.handler_ref",
                "reconciliation route requires the authoritative readback contract",
            ),
        )
    )
    return issues


@dataclass(frozen=True, slots=True)
class TaskObservationNativeDefinition:
    source: TaskObservationNativeSource
    reconciler: type[EffectReconciler]
    readback_contract: object
    session_projector: type[PostgresAgentSessionReadAdapter]
    runtime_projector: type[PostgresRuntimeRunProjector]
    process_observation_projector: object
    line_event_projector_ref: str

    @property
    def contribution_id(self) -> str:
        return self.source.contribution_id

    def contribution_objects(self) -> tuple[ContributionObject, ...]:
        prefix = self.contribution_id
        session_id = f"{prefix}.session-observation-projector"
        reconciler_id = f"{prefix}.effect-reconciler"
        readback_id = f"{prefix}.authoritative-readback"
        runtime_id = f"{prefix}.run-observation-projector"
        process_id = f"{prefix}.process-observation-projector"
        line_event_id = f"{prefix}.line-event-readback-projector"
        return (
            ContributionObject(session_id, "Projector", self.source.owner, ()),
            ContributionObject(reconciler_id, "Reconciler", self.source.owner, ()),
            ContributionObject(readback_id, "ReadbackContract", self.source.owner, (reconciler_id,)),
            ContributionObject(runtime_id, "Projector", self.source.owner, ()),
            ContributionObject(process_id, "Projector", self.source.owner, ()),
            ContributionObject(line_event_id, "Projector", self.source.owner, ()),
            ContributionObject(
                f"{prefix}.observe-session",
                "Capability",
                self.source.owner,
                (session_id,),
            ),
            ContributionObject(
                f"{prefix}.reconcile-effect",
                "Capability",
                self.source.owner,
                (reconciler_id, readback_id),
            ),
            ContributionObject(
                f"{prefix}.observe-run",
                "Capability",
                self.source.owner,
                (runtime_id,),
            ),
            ContributionObject(
                f"{prefix}.observe-process",
                "Capability",
                self.source.owner,
                (process_id, line_event_id),
            ),
            ContributionObject(
                f"{prefix}.project-line-event-readback",
                "Capability",
                self.source.owner,
                (line_event_id,),
            ),
        )

def lower_task_observation_native_source(source: TaskObservationNativeSource) -> TaskObservationNativeDefinition | Failure:
    issues = _definition_issues(source)
    if issues:
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "native task observation definition is invalid",
            {
                "issues": tuple(
                    {"code": "invalid_spec", "path": issue.path, "message": issue.message}
                    for issue in issues
                )
            },
        )
    return TaskObservationNativeDefinition(
        source=source,
        reconciler=EffectReconciler,
        readback_contract=AuthoritativeEffectReadback,
        session_projector=PostgresAgentSessionReadAdapter,
        runtime_projector=PostgresRuntimeRunProjector,
        process_observation_projector=try_join_process_observations,
        line_event_projector_ref=LINE_EVENT_READBACK_PROJECTOR_REF,
    )


def project_task_observation_native_definition(
    definition: TaskObservationNativeDefinition,
) -> ProjectedContributionSpec | Failure:
    return ProjectedContributionSpec(
        id=definition.contribution_id,
        owner=definition.source.owner,
        objects=definition.contribution_objects(),
        failures=(runtime_failures,),
    )


@dataclass(frozen=True, slots=True)
class TaskObservationAssemblyContext:
    """Explicit offline assembly boundary; no DB/provider is invoked here."""

    project_scope_digest: str
    options: TaskObservationAssemblyOptions


@dataclass(frozen=True, slots=True)
class TaskObservationNativeRuntimeBinding:
    definition: TaskObservationNativeDefinition
    family_assembly: FamilyAssembly
    options: TaskObservationAssemblyOptions


def assemble_task_observation_native_definition(
    definition: TaskObservationNativeDefinition,
    context: TaskObservationAssemblyContext,
) -> TaskObservationNativeRuntimeBinding | Failure:
    """Consume the family assembly without executing handlers."""

    options = TaskObservationAssemblyOptions(
        reconciliation_binding=(
            build_deterministic_reconciliation_binding(context.project_scope_digest)
            if definition.source.requires_reconciliation_route
            else None
        ),
        line_event_readback_records=(
            definition.source.line_event_readback_records
        ),
        note="task observation native inert definition binding; handlers are not executed",
    )
    family_assembly = build_task_observation_assembly(
        options=options,
        projector_source_keys=definition.source.projector_key_map,
    )
    return TaskObservationNativeRuntimeBinding(
        definition=definition,
        family_assembly=family_assembly,
        options=options,
    )


def validate_task_observation_native_binding(
    definition: TaskObservationNativeDefinition,
    candidate: object,
) -> BindingAccepted[TaskObservationNativeRuntimeBinding] | BindingRejected:
    if not isinstance(candidate, TaskObservationNativeRuntimeBinding):
        return BindingRejected(
            (NativeBindingIssue("$.binding", "expected TaskObservationNativeRuntimeBinding"),)
        )
    assembly = candidate.family_assembly
    cells = tuple(cell.cell_id for cell in assembly.cells)
    reconcile_handlers = tuple(
        handler
        for handler in assembly.handlers
        if isinstance(handler, TaskEffectReconcileRouteHandler)
    )
    line_handler = next(
        (
            handler
            for handler in assembly.handlers
            if isinstance(handler, ProcessLineEventReadbackRouteHandler)
        ),
        None,
    )
    registered_keys = tuple(
        (contract.key.source_ref, contract.key.source_incarnation)
        for contract in (assembly.projector_registry.projectors if assembly.projector_registry else ())
    )
    declared_keys = tuple(
        (key.source_ref, key.source_incarnation)
        for _, key in definition.source.projector_source_keys
    )
    issues = _issue_tuple(
        (
            (candidate.definition == definition, "$.binding.definition", "definition drift"),
            (
                assembly.family_id == TASK_OBSERVATION_FAMILY_ID,
                "$.binding.family_assembly.family_id",
                "family id drift",
            ),
            (
                cells == ASSEMBLY_CELL_IDS,
                "$.binding.family_assembly.cells",
                "author cell order drift",
            ),
            (
                len(assembly.projector_wiring) == 3,
                "$.binding.family_assembly.projector_wiring",
                "task observation projection wirings drifted",
            ),
            (
                (
                    definition.source.requires_reconciliation_route
                    and len(reconcile_handlers) == 1
                )
                or (
                    not definition.source.requires_reconciliation_route
                    and not reconcile_handlers
                ),
                "$.binding.effect_reconcile.handler",
                "reconciliation route/handler state drifted",
            ),
            (
                (
                    definition.source.line_event_readback_records is not None
                    and isinstance(line_handler, ProcessLineEventReadbackRouteHandler)
                )
                or (definition.source.line_event_readback_records is None and line_handler is None),
                "$.binding.process_observation.line_event_handler",
                "line-event readback route state drifted",
            ),
            (
                len(
                    assembly.projector_registry.projectors
                    if assembly.projector_registry
                    else ()
                )
                == len(definition.source.projector_source_keys),
                "$.binding.projector_registry",
                "projector registration count drifted",
            ),
            (
                registered_keys == declared_keys,
                "$.binding.projector_registry.source_keys",
                "projector registration source identity drifted",
            ),
            (
                definition.source.production_canonical_write is False,
                "$.source.production_canonical_write",
                "binding grants production canonical write",
            ),
            (
                definition.source.durable_evidence_authorized is False,
                "$.source.durable_evidence_authorized",
                "binding manufactures durable evidence",
            ),
            (
                definition.source.registry_metadata_is_execution_evidence is False,
                "$.source.registry_metadata_is_execution_evidence",
                "binding treats registry metadata as execution evidence",
            ),
            (
                definition.source.cells[1].authority_ref == _DEFAULT_RECONCILER_REF
                and definition.reconciler is EffectReconciler,
                "$.binding.effect_reconcile.authority_ref",
                "reconciliation authority drifted from EffectReconciler",
            ),
        )
    )
    return BindingRejected(issues) if issues else BindingAccepted(candidate)


def verify_task_observation_native_definition(
    definition: TaskObservationNativeDefinition,
    native: object,
) -> ContributionVerification | Failure:
    """Return an inert definition law; it does not prove handler execution."""

    del native

    def _run() -> Failure | None:
        checks = (
            (not _definition_issues(definition.source), "definition issues"),
            (definition.reconciler is EffectReconciler, "effect reconciler identity"),
            (
                definition.session_projector is PostgresAgentSessionReadAdapter,
                "session observation projector identity",
            ),
            (
                definition.runtime_projector is PostgresRuntimeRunProjector,
                "runtime run projector identity",
            ),
            (
                definition.process_observation_projector
                is try_join_process_observations,
                "process observation projector identity",
            ),
            (
                definition.line_event_projector_ref
                == LINE_EVENT_READBACK_PROJECTOR_REF,
                "line-event readback projector reference identity",
            ),
        )
        messages = tuple(message for valid, message in checks if not valid)
        if not messages:
            return None
        return contribution_failures.fail("CONTRIBUTION_INVALID", "; ".join(messages))

    witness = define_law_witness(
        f"test_task_native_definition_law:{definition.contribution_id}",
        _run,
    )
    if isinstance(witness, Failure):
        return witness
    return ContributionVerification(
        rule_id=TASK_OBSERVATION_NATIVE_RULE_ID,
        inputs=TASK_OBSERVATION_NATIVE_VERIFICATION_INPUTS,
        checks=(VerificationCheck(witness=witness, inputs=TASK_OBSERVATION_NATIVE_VERIFICATION_INPUTS),),
        complete=True,
    )


TASK_OBSERVATION_NATIVE_CONTRIBUTION_RULE = NativeContributionRule[
    TaskObservationNativeSource,
    TaskObservationNativeDefinition,
    TaskObservationAssemblyContext,
    TaskObservationNativeRuntimeBinding,
](
    lower=lower_task_observation_native_source,
    project=project_task_observation_native_definition,
    assemble=assemble_task_observation_native_definition,
    validate_binding=validate_task_observation_native_binding,
    verification=verify_task_observation_native_definition,
)


def compile_task_observation_native_contribution(source: TaskObservationNativeSource) -> object:
    return compile_native_contribution(source, TASK_OBSERVATION_NATIVE_CONTRIBUTION_RULE)


_DEFAULT_ROLLBACK_REFS = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C5.json",
    "main/backend/app/successor_migration/legacy_agent_sessions.py",
    "main/backend/app/successor_migration/legacy_effect_attempts.py",
    "main/backend/app/successor_migration/legacy_process_observations.py",
)

_DEFAULT_CELLS = (
    TaskObservationCellSource(
        SESSION_OBSERVATION_CELL_ID,
        "session_observation_projection",
        _DEFAULT_SESSION_PROJECTOR_REF,
    ),
    TaskObservationCellSource(
        TASK_EFFECT_RECONCILE_CELL_ID,
        "effect_reconciliation_readback",
        _DEFAULT_RECONCILER_REF,
        _DEFAULT_READBACK_REF,
    ),
    TaskObservationCellSource(
        RUN_OBSERVATION_CELL_ID,
        "runtime_run_projection",
        _DEFAULT_RUNTIME_PROJECTOR_REF,
    ),
    TaskObservationCellSource(
        PROCESS_OBSERVATION_CELL_ID,
        "process_observation_projection",
        _DEFAULT_PROCESS_OBSERVATION_REF,
        _DEFAULT_LINE_EVENT_PROJECTOR_REF,
    ),
)

DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE = TaskObservationNativeSource(
    contribution_id="mrw.task.observation.native.v2",
    owner="task.observation.v2",
    cells=_DEFAULT_CELLS,
    rollback_refs=_DEFAULT_ROLLBACK_REFS,
    requires_reconciliation_route=True,
)

ASSEMBLY_CELL_IDS: Final = tuple(
    cell.cell_id for cell in DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.cells
)

NON_DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE = TaskObservationNativeSource(
    contribution_id="mrw.task.observation.runtime-readback.native.v2",
    owner="task.observation.v2",
    cells=_DEFAULT_CELLS,
    rollback_refs=_DEFAULT_ROLLBACK_REFS,
    requires_reconciliation_route=True,
    projector_source_keys=(
        (
            RUN_OBSERVATION_CELL_ID,
            ProjectorSourceKey(
                source_ref="runtime-run:task-observation-non-default",
                source_incarnation="task-observation-non-default-v1",
            ),
        ),
    ),
    line_event_readback_records=(),
)
