"""Production composition root for the PostgreSQL first-specimen RuntimeNode.

The root is intentionally explicit: it wires the infrastructure-free node to
the PostgreSQL claim/lifecycle adapter, a current-authority guard, and an exact
installed-handler resolver.  No test helper, legacy service, or Document port
is part of this graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, Self

from sqlalchemy import select
from sqlalchemy.engine import Engine

from app.successor_runtime.capabilities.first_specimen_interpreters import (
    FirstSpecimenInterpreters,
    InterpreterFailure,
    InterpreterSuccess,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    RuntimeAssignment,
    require_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    Clock,
    DefiniteInterpreterFailure,
    DeploymentBinding,
    ExactHandlerMismatch,
    InterpreterOutcome,
    NodeIdentity,
    RuntimeExecutionContext,
    RuntimeHandler,
    RuntimeNode,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import ControlPlaneScope, RuntimeScope

from .captured_values import (
    MATERIAL_READ_OPERATION_KIND,
    CapturedValueReplayError,
    PostgresCapturedValueReplayAdapter,
)
from .deployment_backlog import (
    DeploymentInstallationSet,
    DeploymentInstallationSnapshot,
    PostgresBacklogAwareClaimPort,
)
from .models import PUBLIC_TABLES
from .node_adapter import (
    PostgresRuntimeNodeAdapter,
    TerminalCommitHook,
    runtime_uow_factory,
)
from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    validate_authorization_row,
)
from .session import ProjectScopeStale, ServerProjectScopeResolver


class RuntimeCompositionError(RuntimeError):
    """A production node dependency cannot realize the exact frozen binding."""


class _ReadUow(Protocol):
    connection: Any

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


class _ReadUowFactory(Protocol):
    def __call__(self) -> _ReadUow: ...


@dataclass(frozen=True, slots=True)
class InstalledMaterialReadHandler:
    """One exact deployed realization, never a post-claim selection hint."""

    handler_binding_digest: str
    interpreter_profile_digest: str
    operation_contract_digest: str

    def __post_init__(self) -> None:
        require_digest(self.handler_binding_digest, "installed handler binding digest")
        require_digest(
            self.interpreter_profile_digest,
            "installed interpreter profile digest",
        )
        require_digest(
            self.operation_contract_digest,
            "installed operation contract digest",
        )


class PostgresMaterialReadHandler(RuntimeHandler):
    """Execute one exact material read from submission-captured project bytes."""

    def __init__(
        self,
        installation: InstalledMaterialReadHandler,
        replay: PostgresCapturedValueReplayAdapter,
    ) -> None:
        self.handler_binding_digest = installation.handler_binding_digest
        self.interpreter_profile_digest = installation.interpreter_profile_digest
        self.operation_contract_digest = installation.operation_contract_digest
        self._replay = replay

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        if claim.assignment_digest != assignment.assignment_digest:
            raise DefiniteInterpreterFailure("CLAIM_ASSIGNMENT_BINDING_DRIFT")
        if (
            assignment.handler_binding_digest != self.handler_binding_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
            or assignment.operation_contract_ref is None
            or assignment.operation_contract_ref.kind != MATERIAL_READ_OPERATION_KIND
        ):
            raise DefiniteInterpreterFailure("EXACT_MATERIAL_HANDLER_BINDING_DRIFT")
        try:
            replay = self._replay.load_material_read(
                assignment,
                actor_id=context.node.node_id,
            )
        except CapturedValueReplayError as exc:
            raise DefiniteInterpreterFailure("CAPTURED_VALUE_REPLAY_REJECTED") from exc

        interpreted = FirstSpecimenInterpreters().read_canonical_ref(
            replay.payload,
            replay.captured,
        )
        if isinstance(interpreted, InterpreterFailure):
            raise DefiniteInterpreterFailure(interpreted.code)
        if not isinstance(interpreted, InterpreterSuccess):
            raise DefiniteInterpreterFailure("MATERIAL_INTERPRETER_RESULT_INVALID")
        material = interpreted.value
        if material != replay.expected_material or material.content_digest is None:
            raise DefiniteInterpreterFailure("MATERIAL_RESULT_EXACT_BINDING_DRIFT")
        self._replay.publish_material_result(
            assignment,
            actor_id=context.node.node_id,
            replay=replay,
        )
        return InterpreterOutcome.succeeded(
            replay.expected_material_value_ref.content_digest
        )


class ExactInstalledHandlerResolver:
    """Resolve only handler digests present in the immutable node installation."""

    def __init__(self, handlers: tuple[RuntimeHandler, ...]) -> None:
        by_digest: dict[str, RuntimeHandler] = {}
        for handler in handlers:
            if handler.handler_binding_digest in by_digest:
                raise ValueError("duplicate installed handler binding digest")
            by_digest[handler.handler_binding_digest] = handler
        if not by_digest:
            raise ValueError("runtime installation requires at least one handler")
        self._by_digest = by_digest

    def resolve_exact(
        self,
        *,
        assignment: RuntimeAssignment,
        handler_binding_digest: str,
    ) -> RuntimeHandler:
        if handler_binding_digest != assignment.handler_binding_digest:
            raise ExactHandlerMismatch("resolver request/assignment digest drift")
        handler = self._by_digest.get(handler_binding_digest)
        if handler is None:
            raise ExactHandlerMismatch("exact handler binding is not installed")
        profile = getattr(
            assignment.handler_binding,
            "interpreter_profile_digest",
            None,
        )
        if handler.interpreter_profile_digest != profile:
            raise ExactHandlerMismatch("installed handler profile drift")
        if (
            getattr(handler, "operation_contract_digest", None)
            != assignment.operation_contract_digest
        ):
            raise ExactHandlerMismatch("installed operation contract drift")
        return handler


class PostgresCancellationAuthorityGuard:
    """Fresh PostgreSQL cancellation and single-owner authority checks."""

    def __init__(self, uow_factory: _ReadUowFactory) -> None:
        self._uow_factory = uow_factory

    def require_not_cancelled(
        self,
        *,
        claim: Any,
        observed_at: datetime,
    ) -> None:
        assignment = claim.assignment
        with self._uow_factory() as uow:
            run = self._run(uow.connection, assignment)
            if run["cancellation_requested"]:
                raise ExactBindingConflict("run cancellation is current")
            if (
                assignment.deadline_at is not None
                and assignment.deadline_at <= observed_at
            ):
                raise ExactBindingConflict("assignment deadline has elapsed")

    def require_current_authority(
        self,
        *,
        claim: Any,
        expected_authority_digest: str,
        expected_authority_epoch: int,
        observed_at: datetime,
    ) -> None:
        assignment = claim.assignment
        with self._uow_factory() as uow:
            connection = uow.connection
            run = self._run(connection, assignment)
            if run["cancellation_requested"]:
                raise ExactBindingConflict("run cancellation is current")
            scope = self._scope(
                connection, run, assignment, claim.claim_binding.node_id
            )
            del scope  # The validated current scope is the authority boundary.

            if assignment.assignment_kind is AssignmentKind.MATERIALIZE_SUCCESSOR:
                if (
                    assignment.step_id is not None
                    or claim.claim_binding.authorization_digest
                    != expected_authority_digest
                ):
                    raise ExactBindingConflict(
                        "run-scoped materializer authority binding drift"
                    )
                self._require_materializer_capability_authority(
                    connection,
                    assignment,
                    expected_authority_epoch=expected_authority_epoch,
                    observed_at=observed_at,
                )
                return

            authorizations = PUBLIC_TABLES["runtime_step_authorizations"]
            row = (
                connection.execute(
                    select(authorizations).where(
                        authorizations.c.project_key == assignment.project_key,
                        authorizations.c.run_id == assignment.run_id,
                        authorizations.c.step_id == assignment.step_id,
                        authorizations.c.authorization_digest
                        == expected_authority_digest,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise RecordNotFound("exact step authorization is absent")
            authorization = validate_authorization_row(row)
            expected_interpreter_binding_digest = assignment.handler_binding_digest
            if assignment.assignment_kind is AssignmentKind.RECONCILE:
                if assignment.reconciliation_attempt_id is None:
                    raise ExactBindingConflict(
                        "RECONCILE authority guard lacks target attempt"
                    )
                attempts = PUBLIC_TABLES["runtime_effect_attempts"]
                original_attempt = (
                    connection.execute(
                        select(attempts).where(
                            attempts.c.project_key == assignment.project_key,
                            attempts.c.attempt_id
                            == assignment.reconciliation_attempt_id,
                            attempts.c.run_id == assignment.run_id,
                            attempts.c.step_id == assignment.step_id,
                            attempts.c.disposition == "OUTCOME_UNKNOWN",
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if original_attempt is None:
                    raise ExactBindingConflict(
                        "RECONCILE authority guard target attempt is not unknown"
                    )
                expected_interpreter_binding_digest = str(
                    original_attempt["handler_binding_digest"]
                )
            if (
                authorization.binding_digest != expected_authority_digest
                or authorization.claim_authority_epoch != expected_authority_epoch
                or authorization.claim_authority_epoch
                != assignment.claim_authority_epoch
                or authorization.capability_id != assignment.capability_id
                or authorization.operation_contract_digest
                != assignment.operation_contract_digest
                or authorization.interpreter_binding_digest
                != expected_interpreter_binding_digest
                or authorization.expires_at <= observed_at
            ):
                raise ExactBindingConflict("step authorization exact binding drift")

            capabilities = PUBLIC_TABLES["runtime_capability_authority"]
            capability = (
                connection.execute(
                    select(capabilities).where(
                        capabilities.c.project_key == assignment.project_key,
                        capabilities.c.capability_id == assignment.capability_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if capability is None:
                raise RecordNotFound("capability authority is absent")
            if (
                int(capability["authority_epoch"]) != expected_authority_epoch
                or not capability["successor_claim_enabled"]
                or capability["legacy_claim_enabled"]
                or capability["effective_at"] > observed_at
            ):
                raise ExactBindingConflict(
                    "successor is not the current single claim owner"
                )

    @staticmethod
    def _require_materializer_capability_authority(
        connection: Any,
        assignment: RuntimeAssignment,
        *,
        expected_authority_epoch: int,
        observed_at: datetime,
    ) -> None:
        capabilities = PUBLIC_TABLES["runtime_capability_authority"]
        capability = (
            connection.execute(
                select(capabilities).where(
                    capabilities.c.project_key == assignment.project_key,
                    capabilities.c.capability_id == assignment.capability_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if capability is None:
            raise RecordNotFound("materializer capability authority is absent")
        if (
            int(capability["authority_epoch"]) != expected_authority_epoch
            or expected_authority_epoch != assignment.claim_authority_epoch
            or not capability["successor_claim_enabled"]
            or capability["legacy_claim_enabled"]
            or capability["effective_at"] > observed_at
        ):
            raise ExactBindingConflict(
                "materializer is not the current single claim owner"
            )

    @staticmethod
    def _run(connection: Any, assignment: RuntimeAssignment) -> Any:
        runs = PUBLIC_TABLES["runtime_runs"]
        run = (
            connection.execute(
                select(runs).where(
                    runs.c.project_key == assignment.project_key,
                    runs.c.run_id == assignment.run_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if run is None:
            raise RecordNotFound("runtime run is absent")
        if (
            run["incarnation"] != assignment.incarnation
            or run["program_digest"] != assignment.program_digest
            or run["plan_digest"] != assignment.plan_digest
            or int(run["execution_epoch"]) != assignment.execution_epoch
        ):
            raise ExactBindingConflict("runtime run exact identity drift")
        return run

    @staticmethod
    def _scope(
        connection: Any,
        run: Any,
        assignment: RuntimeAssignment,
        actor_id: str,
    ) -> RuntimeScope:
        resolver = ServerProjectScopeResolver(connection=connection)
        expected = resolver.resolve_expected(
            assignment.project_key,
            int(run["project_registry_revision"]),
            str(run["project_scope_digest"]),
        )
        if isinstance(expected, ProjectScopeStale):
            raise ExactBindingConflict("runtime run project scope is stale")
        if resolver.resolve(assignment.project_key) != expected:
            raise ExactBindingConflict("runtime run project scope is no longer current")
        return RuntimeScope(project_scope=expected, actor_id=actor_id)


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class PostgresFirstSpecimenRuntime:
    """Inspectable production composition; ``node`` is the executable root."""

    node: RuntimeNode
    lifecycle: PostgresRuntimeNodeAdapter
    replay: PostgresCapturedValueReplayAdapter
    resolver: ExactInstalledHandlerResolver
    authority: PostgresCancellationAuthorityGuard
    installation: DeploymentInstallationSnapshot
    backlog_claims: PostgresBacklogAwareClaimPort


def compose_postgres_first_specimen_runtime(
    *,
    engine: Engine,
    identity: NodeIdentity,
    profile: RuntimeNodeProfile,
    deployment: DeploymentBinding,
    protocol: RuntimeNodeProtocol,
    control_scope: ControlPlaneScope,
    installations: tuple[InstalledMaterialReadHandler, ...],
    additional_handlers: tuple[RuntimeHandler, ...] = (),
    available_installations: tuple[DeploymentInstallationSnapshot, ...] | None = None,
    terminal_hook: TerminalCommitHook | None = None,
    clock: Clock | None = None,
) -> PostgresFirstSpecimenRuntime:
    """Wire one same-form RuntimeNode over fresh PostgreSQL UoWs."""

    uow_factory = runtime_uow_factory(engine)
    lifecycle = PostgresRuntimeNodeAdapter(
        uow_factory,
        terminal_hook=terminal_hook,
    )
    replay = PostgresCapturedValueReplayAdapter(uow_factory)
    handlers = tuple(
        PostgresMaterialReadHandler(item, replay) for item in installations
    )
    installed_handlers = handlers + additional_handlers
    resolver = ExactInstalledHandlerResolver(installed_handlers)
    installation = DeploymentInstallationSnapshot.from_runtime(
        deployment=deployment,
        profile=profile,
        protocol=protocol,
        handlers=installed_handlers,
    )
    availability = DeploymentInstallationSet(available_installations or (installation,))
    availability.require_contains(installation)
    backlog_claims = PostgresBacklogAwareClaimPort(
        lifecycle,
        uow_factory,
        availability,
    )
    authority = PostgresCancellationAuthorityGuard(uow_factory)
    node = RuntimeNode(
        identity=identity,
        profile=profile,
        deployment=deployment,
        protocol=protocol,
        control_scope=control_scope,
        claims=backlog_claims,
        interpreters=resolver,
        outcomes=lifecycle,
        cancellation=authority,
        clock=clock or SystemClock(),
    )
    return PostgresFirstSpecimenRuntime(
        node=node,
        lifecycle=lifecycle,
        replay=replay,
        resolver=resolver,
        authority=authority,
        installation=installation,
        backlog_claims=backlog_claims,
    )


def build_postgres_first_specimen_runtime_node(**kwargs: Any) -> RuntimeNode:
    """Convenience entry point for process startup."""

    return compose_postgres_first_specimen_runtime(**kwargs).node


__all__ = [
    "DeploymentInstallationSnapshot",
    "ExactInstalledHandlerResolver",
    "InstalledMaterialReadHandler",
    "PostgresCancellationAuthorityGuard",
    "PostgresFirstSpecimenRuntime",
    "PostgresMaterialReadHandler",
    "RuntimeCompositionError",
    "SystemClock",
    "build_postgres_first_specimen_runtime_node",
    "compose_postgres_first_specimen_runtime",
]
