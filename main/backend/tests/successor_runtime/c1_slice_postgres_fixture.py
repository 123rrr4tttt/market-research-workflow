"""Disposable-PostgreSQL fixture for C1 Slice A/B/C runtime acceptance.

The module owns only test bootstrap facts (slice program/plan builders,
deployment/node/profile digests, capability authority rows, and a deterministic
test-only interpreter).  Every runtime transition uses the production
``RuntimeNode`` + ``PostgresRuntimeNodeAdapter`` path and the production
repository/journal lifecycle.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import text

from app.successor_runtime.capabilities import (
    build_first_specimen_bundle,
)
from app.successor_runtime.capabilities import c8_program as c8p
from app.successor_runtime.capabilities import ingest_c7_common as c7
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.ingest_c7_program import (
    build_ingest_c7_1_program,
    compile_ingest_c7_program,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.normalize import normalize_program
from app.successor_runtime.research.object_types import (
    CANONICAL_CODEC_ID,
    ObjectType,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledAdmissionBinding,
    CompiledStepRole,
    CompilerBinding,
    HandlerBindingKind,
    InterpreterBinding,
    QualificationBinding,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.authority_grants import (
    AuthorityOperationScope,
    AuthorityResourceCeiling,
    AuthorityResourceLimit,
)
from app.successor_runtime.runtime.node import (
    DeploymentBinding,
    InterpreterOutcome,
    NodeIdentity,
    RuntimeExecutionContext,
    RuntimeHandler,
    RuntimeNode,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
    ProjectScopeRef,
    RuntimeScope,
)
from app.successor_runtime.runtime.qualification import (
    AuthorityDrift,
    QualifiedPlan,
    StepAuthorizationBinding,
    require_current_authority,
)
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    ReconciliationHandlerOutcome,
    ReconciliationResult,
    ReconciliationState,
)
from app.successor_runtime.runtime.replay import (
    ReplayEvent,
    projection_digest,
    replay_runtime_events,
)
from app.successor_runtime.runtime.resources import (
    QueueEligibility,
    ResourceClass,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres.authority import (
    AuthorityGrant,
    AuthorityGrantRepository,
)
from app.successor_runtime.substrate.postgres.authority_provider import (
    PostgresAuthorityProvider,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
    ProjectTables,
    project_tables,
)
from app.successor_runtime.substrate.postgres.node_adapter import (
    PostgresRuntimeNodeAdapter,
    runtime_uow_factory,
)
from app.successor_runtime.substrate.postgres.nodes import (
    DeploymentCatalog,
    DeploymentCatalogRepository,
    RuntimeNodeRepository,
)
from app.successor_runtime.substrate.postgres.plans import PlanRepository
from app.successor_runtime.substrate.postgres.programs import ProgramRepository
from app.successor_runtime.substrate.postgres.qualification_store import (
    QualificationStoreRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactQualificationBinding,
    RuntimeJournalRepository,
)
from app.successor_runtime.substrate.postgres.runtime_lifecycle import (
    ActivateQualification,
    AssignmentEnvelope,
    AttachPlan,
    RuntimeLifecycleRepository,
    SubmitRun,
    _assignment_values,
)
from app.successor_runtime.substrate.postgres.session import (
    compute_scope_digest,
    create_runtime_engine,
)

DATABASE_ENV = "SUCCESSOR_TEST_DATABASE_URL"

AUTHORITY_EPOCH = 7
RESOURCE_POLICY_EPOCH = 8
NOW = datetime(2031, 6, 1, 8, 0, tzinfo=UTC)

DEPLOYMENT_CATALOG_DIGEST = content_digest(
    {"catalog": "mrw.c1-slice.deployment-catalog"}
)
NODE_PROFILE_DIGEST = content_digest({"profile": "mrw.c1-slice.node-profile"})
SECURITY_PROFILE_DIGEST = content_digest({"security": "mrw.c1-slice"})
RESOURCE_PROFILE_DIGEST = content_digest({"resource": "mrw.c1-slice"})
CLAIM_POLICY_DIGEST = content_digest({"policy": "mrw.c1-slice.claim-policy"})
RESOURCE_POLICY_DIGEST = content_digest({"policy": "mrw.c1-slice.resource-policy"})
SUBMISSION_AUTHORITY_DIGEST = content_digest({"authority": "mrw.c1-slice.submission"})


def _digest(label: str) -> str:
    return content_digest({"label": label})


def _server_url() -> str:
    env_url = os.environ.get(DATABASE_ENV)
    if env_url:
        url = make_url(env_url)
        return url.set(database="postgres").render_as_string(hide_password=False)
    return "postgresql+psycopg2://localhost/postgres"


@dataclass(frozen=True, slots=True)
class C1Database:
    engine: Engine
    database_name: str
    server_url: str

    def fresh_engine(self) -> Engine:
        return create_runtime_engine(
            make_url(self.server_url)
            .set(database=self.database_name)
            .render_as_string(hide_password=False),
            poolclass=NullPool,
        )


@pytest.fixture(scope="module")
def c1_database() -> Iterator[C1Database]:
    server_url = _server_url()
    database_name = f"mrw_c1_slice_acceptance_test_{secrets.token_hex(4)}"
    server = sa.create_engine(
        server_url, isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        with server.connect() as connection:
            connection.execute(
                text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            )
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    except Exception as exc:  # noqa: BLE001 - environment-dependent skip
        server.dispose()
        pytest.skip(f"cannot create disposable database {database_name}: {exc}")
    engine = create_runtime_engine(
        make_url(server_url)
        .set(database=database_name)
        .render_as_string(hide_password=False),
        poolclass=NullPool,
    )
    database = C1Database(
        engine=engine,
        database_name=database_name,
        server_url=server_url,
    )
    try:
        yield database
    finally:
        engine.dispose()
        with server.connect() as connection:
            connection.execute(
                text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            )
            remaining = connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname=:name"),
                {"name": database_name},
            )
            assert remaining is None, "C1 acceptance database residue remains"
        server.dispose()


def _slice_program_plan(
    slice_id: str,
    *,
    project_key: str,
    registry_revision: int,
    scope_digest: str,
) -> tuple[Any, Any, Any]:
    """Return (program, plan, catalog) for one exact C1 slice."""

    if slice_id == "A":
        bundle = c7.build_ingest_c7_bundle()
        catalog = c7.build_ingest_c7_catalog(bundle)
        submission = c7.C7IngestSubmission(
            idempotency_key=f"idem:{project_key}:a",
            project_key=project_key,
            source_locator=f"https://example.invalid/{project_key}/a",
            request_key=f"req:{project_key}:a",
            raw_payload={
                "title": "C1 Slice A",
                "text": "C1 stage-candidate runtime acceptance",
            },
        )
        program = build_ingest_c7_1_program(
            payload=submission,
            catalog=catalog,
            program_id=f"program:{project_key}:slice-a",
            project_key=project_key,
            project_registry_revision=registry_revision,
            project_scope_digest=scope_digest,
        )
        plan = compile_ingest_c7_program(
            program,
            catalog,
            operation_contracts=c7.build_ingest_c7_registry(bundle),
        )
        return program, plan, catalog

    if slice_id == "B":
        bundle = c8p.build_c8_bundle()
        catalog = c8p.build_c8_catalog(bundle)
        program = c8p.build_c8_program(
            cell_id="C8.2",
            payload=c8p.C8WritingComposeInput(
                project_key=project_key,
                knowledge_item_key="knowledge:c1",
                selection_hash="selection:c1",
                selection_text="C1 bounded writing",
                demand_fields=("canonical_statement", "evidence_refs"),
            ),
            catalog=catalog,
            program_id=f"program:{project_key}:slice-b",
            project_key=project_key,
            project_registry_revision=registry_revision,
            project_scope_digest=scope_digest,
        )
        plan = c8p.compile_c8_program(
            program,
            catalog,
            operation_contracts=c8p.build_c8_registry(bundle),
        )
        return program, plan, catalog

    if slice_id == "C":
        first_specimen = build_first_specimen_bundle()
        delivery_operation = first_specimen.operation_by_kind(
            c8p.DELIVERY_INTERNAL_EXPORT_KIND
        )
        delivery_codec = first_specimen.codec_by_kind(c8p.DELIVERY_INTERNAL_EXPORT_KIND)
        bundle = c8p.build_c8_delivery_bridge_bundle(
            delivery_operation,
            delivery_codec,
        )
        catalog = c8p.build_c8_catalog(bundle)
        program_id = f"program:{project_key}:slice-c"

        def value_ref(
            suffix: str,
            object_type: ObjectType,
            codec_id: str,
        ) -> ValueRef:
            value_id = f"{program_id}:payload:{suffix}"
            storage_ref = f"project-value:{value_id}"
            return ValueRef(
                value_id=value_id,
                project_key=project_key,
                object_type=object_type,
                codec_id=codec_id,
                content_digest=content_digest({"storage_ref": storage_ref}),
                storage_kind="project_value_ref",
                store_id="successor_values",
                store_version="1",
                storage_ref=storage_ref,
                byte_size=1,
                provenance_digest=content_digest({"provenance": storage_ref}),
            )

        program = normalize_program(
            c8p.build_c8_delivery_bridge_program(
                delivery_operation=delivery_operation,
                delivery_codec=delivery_codec,
                delivery_payload_ref=value_ref(
                    "internal-export-input",
                    ObjectType("InternalExportInput.v1"),
                    delivery_codec.codec_id,
                ),
                artifact_input_ref=value_ref(
                    "research-artifact",
                    c8p.C8_RESEARCH_ARTIFACT_TYPE,
                    CANONICAL_CODEC_ID,
                ),
                intent_input_ref=value_ref(
                    "delivery-intent",
                    c8p.C8_DELIVERY_INTENT_TYPE,
                    CANONICAL_CODEC_ID,
                ),
                stage_payload=c8p.C8ReportStageInput(
                    project_key=project_key,
                    report_id="report:c1",
                    topic="C1 report delivery acceptance",
                    source_keys=("knowledge:c1",),
                ),
                catalog=catalog,
                program_id=program_id,
                project_key=project_key,
                project_registry_revision=registry_revision,
                project_scope_digest=scope_digest,
            )
        )
        plan = c8p.compile_c8_delivery_bridge_program(
            program,
            catalog,
            operation_contracts=c8p.build_c8_registry(bundle),
        )
        return program, plan, catalog

    raise AssertionError(f"unsupported C1 slice {slice_id!r}")


class _C1InterpreterHandler:
    """Deterministic test-only interpreter bound to exact handler digests."""

    def __init__(
        self,
        *,
        handler_binding_digest: str,
        interpreter_profile_digest: str,
        ledger: _C1ExecutionLedger,
    ) -> None:
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.ledger = ledger

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: Any,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        assert claim.assignment_digest == assignment.assignment_digest
        step_id = assignment.step_id
        assert step_id is not None
        attempt_id = claim.attempt_id
        result_digest = content_digest(
            {
                "step": step_id,
                "attempt": attempt_id,
                "assignment": assignment.assignment_digest,
            }
        )
        receipt_ref = f"receipt:sha256:{content_digest({'receipt': step_id, 'attempt': attempt_id})}"
        self.ledger.record(
            context.node.node_id,
            step_id,
            attempt_id,
            result_digest,
            receipt_ref,
        )
        return InterpreterOutcome.succeeded(result_digest, receipt_ref=receipt_ref)


class _C1TypedFailureHandler:
    """Deterministic test-only interpreter that records then fails one effect."""

    def __init__(
        self,
        *,
        handler_binding_digest: str,
        interpreter_profile_digest: str,
        ledger: _C1ExecutionLedger,
        failure_code: str = "C1_TYPED_EFFECT_FAILURE",
    ) -> None:
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.ledger = ledger
        self.failure_code = failure_code
        self.calls: list[tuple[str, str]] = []

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: Any,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        assert claim.assignment_digest == assignment.assignment_digest
        step_id = assignment.step_id
        assert step_id is not None
        attempt_id = claim.attempt_id
        self.calls.append((step_id, attempt_id))
        self.ledger.record_attempt(
            context.node.node_id,
            step_id,
            attempt_id,
        )
        return InterpreterOutcome.failed(self.failure_code)


class _C1ExecutionLedger:
    """Shared record of every exact interpreter execution across node instances."""

    def __init__(self) -> None:
        self.executions: list[tuple[str, str, str]] = []
        self.outcomes: dict[str, tuple[str, str]] = {}

    def record(
        self,
        node_id: str,
        step_id: str,
        attempt_id: str,
        result_digest: str,
        receipt_ref: str,
    ) -> None:
        self.executions.append((node_id, step_id, attempt_id))
        self.outcomes[step_id] = (result_digest, receipt_ref)

    def record_attempt(
        self,
        node_id: str,
        step_id: str,
        attempt_id: str,
    ) -> None:
        self.executions.append((node_id, step_id, attempt_id))


class _C1WaitingReconcileHandler:
    """Authoritative readback that keeps OUTCOME_UNKNOWN in WAITING."""

    def __init__(
        self,
        *,
        handler_binding_digest: str,
        interpreter_profile_digest: str,
    ) -> None:
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.calls: list[str] = []

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: Any,
        context: RuntimeExecutionContext,
    ) -> ReconciliationHandlerOutcome:
        attempt_id = assignment.reconciliation_attempt_id
        assert attempt_id is not None
        self.calls.append(attempt_id)
        readback = AuthoritativeEffectReadback(
            attempt_id=attempt_id,
            disposition=EffectDisposition.OUTCOME_UNKNOWN,
            observation_digest=content_digest({"readback": attempt_id}),
            reason="AUTHORITATIVE_OUTCOME_UNRESOLVED",
        )
        result = ReconciliationResult(
            state=ReconciliationState.WAITING,
            attempt_id=attempt_id,
            disposition=EffectDisposition.OUTCOME_UNKNOWN,
            readback=readback,
            wait_reason=readback.reason,
        )
        return ReconciliationHandlerOutcome(result=result)


class _C1ExactResolver:
    def __init__(self, handlers: dict[str, RuntimeHandler]) -> None:
        self.handlers = handlers

    def resolve_exact(
        self,
        *,
        assignment: RuntimeAssignment,
        handler_binding_digest: str,
    ) -> RuntimeHandler:
        assert handler_binding_digest == assignment.handler_binding_digest
        try:
            return self.handlers[handler_binding_digest]
        except KeyError as exc:
            raise AssertionError("missing exact handler binding digest") from exc


class _C1AuthorityGuard:
    def __init__(self, engine: Engine, project_key: str) -> None:
        self.engine = engine
        self.project_key = project_key

    def require_not_cancelled(self, *, claim: Any, observed_at: object) -> None:
        del observed_at
        assignment = claim.assignment
        with self.engine.connect() as connection:
            cancelled = connection.scalar(
                sa.select(sa.text("cancellation_requested"))
                .select_from(sa.text("public.runtime_runs"))
                .where(sa.text("project_key=:project_key AND run_id=:run_id"))
                .params(
                    project_key=self.project_key,
                    run_id=assignment.run_id,
                )
            )
        if cancelled:
            raise RuntimeError("run cancellation is current")

    def require_current_authority(
        self,
        *,
        claim: Any,
        expected_authority_digest: str,
        expected_authority_epoch: int,
        observed_at: datetime,
    ) -> None:
        assignment = claim.assignment
        with self.engine.connect() as connection:
            capability = (
                connection.execute(
                    sa.select(PUBLIC_TABLES["runtime_capability_authority"]).where(
                        PUBLIC_TABLES["runtime_capability_authority"].c.project_key
                        == self.project_key,
                        PUBLIC_TABLES["runtime_capability_authority"].c.capability_id
                        == assignment.capability_id,
                    )
                )
                .mappings()
                .one()
            )
            authorization = (
                connection.execute(
                    sa.select(PUBLIC_TABLES["runtime_step_authorizations"]).where(
                        PUBLIC_TABLES["runtime_step_authorizations"].c.project_key
                        == self.project_key,
                        PUBLIC_TABLES["runtime_step_authorizations"].c.run_id
                        == assignment.run_id,
                        PUBLIC_TABLES["runtime_step_authorizations"].c.step_id
                        == assignment.step_id,
                        PUBLIC_TABLES[
                            "runtime_step_authorizations"
                        ].c.claim_authority_epoch
                        == expected_authority_epoch,
                    )
                )
                .mappings()
                .one_or_none()
            )
        if (
            int(capability["authority_epoch"]) != expected_authority_epoch
            or not capability["successor_claim_enabled"]
            or capability["legacy_claim_enabled"]
        ):
            raise RuntimeError("future owner authority epoch drift")
        if (
            authorization is None
            or authorization["authorization_digest"] != expected_authority_digest
            or authorization["expires_at"] <= observed_at
        ):
            raise RuntimeError("current step authority drift")


class _C1AdmissionCommitHook:
    """Test-owned CommitPrepared stage for VERIFY_ADMIT terminal commits."""

    def prepare_terminal(
        self,
        *,
        connection: sa.Connection,
        scope: RuntimeScope,
        claim: Any,
        lifecycle: Any,
        outcome: InterpreterOutcome,
        terminal: Any,
    ) -> Any:
        if (
            outcome.disposition is EffectDisposition.SUCCEEDED
            and claim.assignment.assignment_kind is AssignmentKind.VERIFY_ADMIT
        ):
            updated = RuntimeLifecycleRepository(
                connection,
                scope,
            ).begin_commit(
                lifecycle,
                observed_at=terminal.observed_at,
            )
            return replace(terminal, claimed=updated)
        return terminal

    def after_terminal(self, **kwargs: Any) -> None:
        del kwargs


class _FixedClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


@dataclass(frozen=True, slots=True)
class PreparedC1Slice:
    database: C1Database
    slice_id: str
    project_key: str
    resolved_schema: str
    scope: RuntimeScope
    tables: ProjectTables
    program: Any
    plan: Any
    catalog: Any
    run_id: str
    run_incarnation: str
    authority_epoch: int
    steps: tuple[Any, ...]
    assignments: tuple[RuntimeAssignment, ...]
    authorizations: tuple[StepAuthorizationBinding, ...]
    handler: _C1ExecutionLedger
    reconcile_handler: _C1WaitingReconcileHandler
    resolver: _C1ExactResolver
    interpreter_profile_digests: frozenset[str]
    recovery_binding_digest: str
    profile_digest: str = NODE_PROFILE_DIGEST

    @property
    def capability_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    str(authorization.capability_id)
                    for authorization in self.authorizations
                }
            )
        )


def _operation_by_kind(bundle: Any, kind: str) -> Any:
    matches = tuple(
        operation for operation in bundle.operations if operation.ref.kind == kind
    )
    if len(matches) != 1:
        raise AssertionError(f"expected one operation for {kind}, found {len(matches)}")
    return matches[0]


def _compile_assignment(
    *,
    run_id: str,
    run_incarnation: str,
    project_key: str,
    program_digest: str,
    catalog_digest: str,
    authority_epoch: int,
) -> RuntimeAssignment:
    compiler = CompilerBinding.from_content(
        compiler_id="mrw.functorial-successor.compiler",
        compiler_version="1.0.0",
        compiler_digest=_digest("c1-compiler"),
        operation_catalog_digest=catalog_digest,
        domain_contract_snapshot_digest=_digest("c1-domain-contract-snapshot"),
    )
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id=f"{run_id}:compile",
        assignment_kind=AssignmentKind.COMPILE,
        project_key=project_key,
        run_id=run_id,
        capability_id="mrw.c1.compile",
        handler_binding_kind=HandlerBindingKind.COMPILER,
        handler_binding_ref=f"handler-binding:sha256:{compiler.binding_digest}",
        handler_binding_digest=compiler.binding_digest,
        handler_binding=compiler,
        program_digest=program_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        execution_epoch=0,
        incarnation=run_incarnation,
        queue_eligibility_digest=_digest("c1-compile-eligibility"),
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        claim_authority_epoch=authority_epoch,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        trace_id=f"trace:{run_id}:compile",
    )


def _qualify_assignment(
    *,
    run_id: str,
    run_incarnation: str,
    project_key: str,
    program_digest: str,
    plan_digest: str,
    authority_epoch: int,
) -> RuntimeAssignment:
    qualification = QualificationBinding.from_content(
        authority_reader_id="c1-authority-reader",
        authority_reader_version="1.0.0",
        authority_reader_digest=_digest("c1-authority-reader"),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
    )
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id=f"{run_id}:qualify",
        assignment_kind=AssignmentKind.QUALIFY,
        project_key=project_key,
        run_id=run_id,
        capability_id="mrw.c1.qualify",
        handler_binding_kind=HandlerBindingKind.QUALIFICATION,
        handler_binding_ref=(f"handler-binding:sha256:{qualification.binding_digest}"),
        handler_binding_digest=qualification.binding_digest,
        handler_binding=qualification,
        program_digest=program_digest,
        plan_digest=plan_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        execution_epoch=0,
        incarnation=run_incarnation,
        queue_eligibility_digest=_digest("c1-qualify-eligibility"),
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        claim_authority_epoch=authority_epoch,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        trace_id=f"trace:{run_id}:qualify",
    )


def _ensure_capability_authority(
    connection: sa.Connection,
    *,
    scope: RuntimeScope,
    capability_id: str,
    authority_epoch: int,
) -> None:
    table = PUBLIC_TABLES["runtime_capability_authority"]
    existing = (
        connection.execute(
            sa.select(table).where(
                table.c.project_key == scope.project_scope.project_key,
                table.c.capability_id == capability_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    values = {
        "project_key": scope.project_scope.project_key,
        "capability_id": capability_id,
        "mode": "canary",
        "authority_epoch": authority_epoch,
        "successor_claim_enabled": True,
        "legacy_claim_enabled": False,
        "allowlist_digest": _digest(f"allowlist:{capability_id}"),
        "config_digest": _digest(f"config:{capability_id}"),
        "effective_at": NOW,
        "updated_by": scope.actor_id,
        "approval_ref": f"approval:c1:{capability_id}",
        "rollback_target_ref": "canonical:c1-legacy-read-only",
        "revision": 0,
    }
    if existing is None:
        connection.execute(sa.insert(table).values(**values))
        return
    if (
        int(existing["authority_epoch"]) != authority_epoch
        or not existing["successor_claim_enabled"]
        or existing["legacy_claim_enabled"]
    ):
        raise AssertionError("capability authority epoch drift in shared project")
    drift = [
        name
        for name in (
            "mode",
            "allowlist_digest",
            "config_digest",
            "approval_ref",
            "rollback_target_ref",
        )
        if existing[name] != values[name]
    ]
    if drift:
        raise AssertionError(f"capability authority identity rebound: {drift}")


def _ensure_resource_policy(
    connection: sa.Connection,
    *,
    scope: RuntimeScope,
    capability_id: str,
) -> None:
    table = PUBLIC_TABLES["runtime_resource_policies"]
    policy_id = f"policy:c1:{scope.project_scope.project_key}:{capability_id}"
    existing = (
        connection.execute(
            sa.select(table).where(
                table.c.project_key == scope.project_scope.project_key,
                table.c.resource_policy_id == policy_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    values = {
        "resource_policy_id": policy_id,
        "project_key": scope.project_scope.project_key,
        "capability_id": capability_id,
        "resource_class": ResourceClass.CPU_LIGHT.value,
        "concurrency_limit": 4,
        "max_project_active": 8,
        "max_capability_active": 8,
        "max_resource_active": 8,
        "units_ceiling": 8,
        "provider_limit": None,
        "policy_epoch": RESOURCE_POLICY_EPOCH,
        "policy_digest": RESOURCE_POLICY_DIGEST,
        "revision": 0,
    }
    if existing is None:
        connection.execute(sa.insert(table).values(**values))
        return
    if any(existing[name] != values[name] for name in values):
        raise AssertionError("resource policy identity rebound")


def _ensure_grant(
    connection: sa.Connection,
    *,
    scope: RuntimeScope,
    capability_id: str,
) -> None:
    repository = AuthorityGrantRepository(connection, scope)
    grant_id = f"grant:c1:{scope.project_scope.project_key}:{capability_id}"
    table = PUBLIC_TABLES["runtime_authority_grants"]
    existing = (
        connection.execute(
            sa.select(table).where(
                table.c.project_key == scope.project_scope.project_key,
                table.c.grant_id == grant_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if existing is not None:
        return
    repository.create(
        AuthorityGrant(
            grant_id=grant_id,
            actor_id=scope.actor_id,
            capability_id=capability_id,
            operation_scope_json=AuthorityOperationScope.from_content(
                operation_kinds=(capability_id,),
                project_scope_digest=scope.project_scope.scope_digest,
            ),
            resource_ceiling_json=AuthorityResourceCeiling.from_content(
                limits=(
                    AuthorityResourceLimit(
                        resource_class=ResourceClass.CPU_LIGHT.value,
                        units=8,
                    ),
                ),
                max_active=8,
            ),
            credential_ref=None,
            grant_epoch=1,
            expires_at=NOW + timedelta(days=1),
        )
    )


def _ensure_project_scope(
    connection: sa.Connection,
    scope: RuntimeScope,
) -> None:
    table = PUBLIC_TABLES["project_scope_registry"]
    existing = (
        connection.execute(
            sa.select(table).where(
                table.c.project_key == scope.project_scope.project_key,
                table.c.registry_revision
                == scope.project_scope.project_registry_revision,
            )
        )
        .mappings()
        .one_or_none()
    )
    if existing is not None:
        if (
            existing["resolved_schema"] != scope.project_scope.resolved_schema
            or existing["scope_digest"] != scope.project_scope.scope_digest
            or existing["incarnation"] != scope.project_scope.incarnation
        ):
            raise AssertionError("project scope identity rebound")
        return
    connection.execute(
        sa.insert(table).values(
            project_key=scope.project_scope.project_key,
            registry_revision=scope.project_scope.project_registry_revision,
            resolved_schema=scope.project_scope.resolved_schema,
            scope_digest=scope.project_scope.scope_digest,
            incarnation=scope.project_scope.incarnation,
            state="ACTIVE",
            updated_by="c1-slice-postgres-fixture",
            approval_ref=f"approval:{scope.project_scope.project_key}:scope",
        )
    )


def prepare_runtime(
    database: C1Database,
    *,
    slice_id: str,
    project_key: str,
    tag: str,
    run_suffix: str,
    authority_epoch: int = AUTHORITY_EPOCH,
    handler_builder: Callable[
        [str, str, _C1ExecutionLedger],
        RuntimeHandler,
    ]
    | None = None,
) -> PreparedC1Slice:
    """Install one exact C1 slice run over production PG lifecycle paths.

    ``handler_builder`` is test-only interpreter injection; when omitted the
    deterministic ``_C1InterpreterHandler`` remains the default for every kind.
    """

    resolved_schema = f"mrw_c1_{slice_id.lower()}_{tag}"
    registry_revision = 1
    scope_incarnation = f"c1-scope:{project_key}"
    run_id = f"run:{project_key}:{run_suffix}"
    run_incarnation = f"run-inc:{run_id}"
    scope_digest = compute_scope_digest(
        project_key,
        resolved_schema,
        registry_revision,
        scope_incarnation,
    )
    scope = RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=project_key,
            resolved_schema=resolved_schema,
            project_registry_revision=registry_revision,
            incarnation=scope_incarnation,
            scope_digest=scope_digest,
        ),
        actor_id=f"human:{project_key}",
    )
    metadata = sa.MetaData()
    tables = project_tables(metadata, resolved_schema)
    with database.engine.begin() as connection:
        if resolved_schema not in set(sa.inspect(connection).get_schema_names()):
            connection.execute(sa.text(f'CREATE SCHEMA "{resolved_schema}"'))
        PUBLIC_METADATA.create_all(connection, checkfirst=True)
        metadata.create_all(connection, checkfirst=True)
        _ensure_project_scope(connection, scope)

    program, plan, catalog = _slice_program_plan(
        slice_id,
        project_key=project_key,
        registry_revision=registry_revision,
        scope_digest=scope_digest,
    )
    compile_assignment = _compile_assignment(
        run_id=run_id,
        run_incarnation=run_incarnation,
        project_key=project_key,
        program_digest=program.program_digest,
        catalog_digest=catalog.catalog_digest,
        authority_epoch=authority_epoch,
    )
    qualify_assignment = _qualify_assignment(
        run_id=run_id,
        run_incarnation=run_incarnation,
        project_key=project_key,
        program_digest=program.program_digest,
        plan_digest=plan.plan_digest,
        authority_epoch=authority_epoch,
    )

    bundle_for_ops = None
    if slice_id == "A":
        bundle_for_ops = c7.build_ingest_c7_bundle()
    else:
        first_specimen = build_first_specimen_bundle()
        delivery_operation = first_specimen.operation_by_kind(
            c8p.DELIVERY_INTERNAL_EXPORT_KIND
        )
        delivery_codec = first_specimen.codec_by_kind(c8p.DELIVERY_INTERNAL_EXPORT_KIND)
        bundle_for_ops = (
            c8p.build_c8_bundle()
            if slice_id == "B"
            else c8p.build_c8_delivery_bridge_bundle(
                delivery_operation,
                delivery_codec,
            )
        )

    contracts_by_kind: dict[str, Any] = {}
    for step in plan.ordered_steps:
        ref = step.operation_contract_ref
        if ref is None or step.step_kind not in {"EFFECT", "ADMISSION"}:
            continue
        contracts_by_kind.setdefault(
            ref.kind,
            _operation_by_kind(bundle_for_ops, ref.kind),
        )

    interpreter_bindings: dict[str, InterpreterBinding] = {}
    recovery_bindings: dict[str, RecoveryBinding] = {}
    for kind, operation in contracts_by_kind.items():
        interpreter_profile_digest = _digest(f"interpreter:{kind}")
        interpreter_bindings[kind] = InterpreterBinding.from_content(
            operation_contract_digest=operation.ref.contract_digest,
            interpreter_profile_digest=interpreter_profile_digest,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            runtime_protocol_version="1",
            project_scope_digest=scope_digest,
            resource_policy_epoch=RESOURCE_POLICY_EPOCH,
            authority_requirement_digest=_digest(f"authority:{kind}"),
        )
        recovery_bindings[kind] = RecoveryBinding.from_content(
            recovery_handler_id=f"readback:{kind}",
            recovery_handler_version="1.0.0",
            interpreter_profile_digest=interpreter_profile_digest,
            authoritative_readback_profile_ref=f"project-readback:{kind}",
        )

    authorizable = tuple(
        step
        for step in plan.ordered_steps
        if step.step_kind in {"EFFECT", "ADMISSION"}
        and step.operation_contract_ref is not None
    )
    eligibility_by_step: dict[str, QueueEligibility] = {}
    capability_by_step: dict[str, str] = {}
    for step in authorizable:
        assert step.operation_contract_ref is not None
        kind = step.operation_contract_ref.kind
        operation = contracts_by_kind[kind]
        capability_id = operation.owner_capability_id
        capability_by_step[step.step_id] = capability_id
        eligibility_by_step[step.step_id] = QueueEligibility(
            project_key=project_key,
            capability_id=capability_id,
            resource_class=ResourceClass.CPU_LIGHT,
            units=1,
            policy_epoch=RESOURCE_POLICY_EPOCH,
            policy_digest=RESOURCE_POLICY_DIGEST,
            concurrency_key=f"{project_key}:{kind}",
        )

    capability_ids = tuple(
        sorted(
            {
                str(operation.owner_capability_id)
                for operation in contracts_by_kind.values()
            }
        )
    )
    first_capability_id = capability_ids[0]

    with database.engine.begin() as connection:
        for capability_id in capability_ids:
            _ensure_capability_authority(
                connection,
                scope=scope,
                capability_id=capability_id,
                authority_epoch=authority_epoch,
            )
            _ensure_resource_policy(
                connection, scope=scope, capability_id=capability_id
            )
            _ensure_grant(connection, scope=scope, capability_id=capability_id)

        contexts = {
            capability_id: PostgresAuthorityProvider(
                connection,
                scope,
            ).current_context(
                scope.actor_id,
                capability_id=capability_id,
                canonical_base_revision=0,
                canonical_incarnation=scope_incarnation,
                now=NOW,
            )
            for capability_id in capability_ids
        }

        lifecycle = RuntimeLifecycleRepository(connection, scope)
        lifecycle.submit(
            SubmitRun(
                run_id=run_id,
                incarnation=run_incarnation,
                program_id=program.program_id,
                program_digest=program.program_digest,
                program_storage_ref=f"project-value:program:{program.program_id}",
                contract_version=program.contract_version,
                submission_authority_digest=SUBMISSION_AUTHORITY_DIGEST,
                compile_work=AssignmentEnvelope(
                    assignment=compile_assignment,
                    required_node_profile_selector=NODE_PROFILE_DIGEST,
                    authority_digest=SUBMISSION_AUTHORITY_DIGEST,
                    resource_policy_digest=RESOURCE_POLICY_DIGEST,
                    fairness_key=project_key,
                ),
                due_at=NOW,
            )
        )
        RuntimeJournalRepository(connection, scope).append_transition(
            run_id=run_id,
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(
                {
                    "event_type": "CompileSucceeded",
                    "schema_version": "mrw.runtime.event.compile-succeeded.v1",
                    "event_metadata_json": {"plan_digest": plan.plan_digest},
                    "authority_digest": SUBMISSION_AUTHORITY_DIGEST,
                },
            ),
        )
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_work_items"])
            .where(
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                == compile_assignment.work_item_id
            )
            .values(state="COMPLETED", revision=1)
        )
        ProgramRepository(connection, tables).put_exact(
            scope,
            program,
            program.program_digest,
        )
        PlanRepository(connection, tables).put_exact(
            scope,
            plan,
            plan.plan_digest,
            operation_catalog_id=catalog.catalog_id,
            catalog_version=catalog.catalog_version,
            catalog_digest=catalog.catalog_digest,
        )
        lifecycle.attach_plan(
            AttachPlan(
                run_id=run_id,
                expected_run_revision=1,
                plan_id=plan.plan_id,
                plan_digest=plan.plan_digest,
                program_id=plan.program_id,
                program_digest=plan.program_digest,
                project_storage_ref=f"project-value:plan:{plan.plan_id}",
                compiler_id=plan.compiler_id,
                compiler_version=plan.compiler_version,
                operation_catalog_id=catalog.catalog_id,
                catalog_version=catalog.catalog_version,
                catalog_digest=catalog.catalog_digest,
                effect_closure_digest=plan.effect_closure_digest,
                authority_closure_digest=plan.authority_closure_digest,
                resource_closure_digest=plan.resource_closure_digest,
                qualify_work=AssignmentEnvelope(
                    assignment=qualify_assignment,
                    required_node_profile_selector=NODE_PROFILE_DIGEST,
                    authority_digest=contexts[first_capability_id].context_digest,
                    resource_policy_digest=RESOURCE_POLICY_DIGEST,
                    fairness_key=project_key,
                ),
                due_at=NOW,
            )
        )
        input_digest_by_step = {
            step.step_id: canonical_digest(
                (f"project-value:step-input:{run_id}:{step.step_id}",)
            )
            for step in authorizable
        }
        for step in authorizable:
            assert step.operation_contract_ref is not None
            operation = contracts_by_kind[step.operation_contract_ref.kind]
            eligibility = eligibility_by_step[step.step_id]
            connection.execute(
                sa.insert(PUBLIC_TABLES["runtime_steps"]).values(
                    project_key=project_key,
                    run_id=run_id,
                    step_id=step.step_id,
                    operation_id=step.operation_id,
                    operation_kind=step.operation_contract_ref.kind,
                    operation_version=step.operation_contract_ref.contract_version,
                    state="READY",
                    revision=0,
                    execution_epoch=0,
                    input_digest=input_digest_by_step[step.step_id],
                    effect_class="LOCAL_SUCCESSOR_NATIVE",
                    resource_class=eligibility.resource_class.value,
                    concurrency_key=eligibility.concurrency_key,
                    capability_id=operation.owner_capability_id,
                    claim_owner="successor",
                    claim_authority_epoch=authority_epoch,
                    claim_policy_digest=CLAIM_POLICY_DIGEST,
                    attempt_count=0,
                    max_attempts=2,
                )
            )

        authorizations: list[StepAuthorizationBinding] = []
        for step in authorizable:
            assert step.operation_contract_ref is not None
            kind = step.operation_contract_ref.kind
            operation = contracts_by_kind[kind]
            capability_id = capability_by_step[step.step_id]
            context = contexts[capability_id]
            eligibility = eligibility_by_step[step.step_id]
            authorizations.append(
                StepAuthorizationBinding.from_content(
                    run_id=run_id,
                    step_id=step.step_id,
                    operation_kind=kind,
                    operation_contract_digest=step.operation_contract_ref.contract_digest,
                    capability_id=capability_id,
                    claim_owner="successor",
                    claim_authority_epoch=authority_epoch,
                    claim_policy_digest=CLAIM_POLICY_DIGEST,
                    payload_digest=_digest(f"payload:{step.step_id}"),
                    actor_id=scope.actor_id,
                    project_key=project_key,
                    project_registry_revision=registry_revision,
                    project_scope_digest=scope_digest,
                    interpreter_binding_digest=interpreter_bindings[
                        kind
                    ].binding_digest,
                    deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                    authority_source_bindings=context.authority_source_bindings,
                    grants_digest=context.grants_digest,
                    approval_refs=(),
                    resource_ceiling_digest=context.resource_ceiling_digest,
                    resource_policy_epoch=RESOURCE_POLICY_EPOCH,
                    queue_eligibility_digest=eligibility.eligibility_digest,
                    grant_epoch=context.grant_epoch,
                    expires_at=context.expires_at,
                    canonical_base_revision=0,
                    canonical_incarnation=scope_incarnation,
                )
            )

        qualified = QualifiedPlan.from_content(
            plan_digest=plan.plan_digest,
            authority_context_digest=contexts[first_capability_id].context_digest,
            step_bindings=tuple(authorizations),
        )
        exact_qualification = ExactQualificationBinding.from_content(
            qualification_id=f"qualification:{run_id}",
            project_key=project_key,
            run_id=run_id,
            plan_id=plan.plan_id,
            plan_digest=plan.plan_digest,
            authority_context=contexts[first_capability_id],
            authority_context_digest=contexts[first_capability_id].context_digest,
            qualified_plan=qualified,
            decision="QUALIFIED",
        )
        QualificationStoreRepository(connection, scope).persist(exact_qualification)
        lifecycle.activate_qualification(
            ActivateQualification(
                run_id=run_id,
                expected_run_revision=2,
                binding=exact_qualification,
            )
        )
        connection.execute(
            sa.text(
                "UPDATE public.runtime_work_items SET state='COMPLETED', "
                "revision=1 WHERE work_item_id=:work_item_id"
            ),
            {"work_item_id": qualify_assignment.work_item_id},
        )

        assignments: list[RuntimeAssignment] = []
        for step in authorizable:
            assert step.operation_contract_ref is not None
            assert step.return_contract_ref is not None
            kind = step.operation_contract_ref.kind
            operation = contracts_by_kind[kind]
            capability_id = capability_by_step[step.step_id]
            eligibility = eligibility_by_step[step.step_id]
            interpreter = interpreter_bindings[kind]
            recovery = recovery_bindings[kind]
            return_binding = ReturnContractBinding.from_contract(
                step.return_contract_ref,
                step.return_contract,
            )
            input_refs = (f"project-value:step-input:{run_id}:{step.step_id}",)
            assignment_kind = (
                AssignmentKind.INTERPRET
                if step.step_kind == "EFFECT"
                else AssignmentKind.VERIFY_ADMIT
            )
            step_role = (
                CompiledStepRole.EFFECT
                if step.step_kind == "EFFECT"
                else CompiledStepRole.ADMISSION
            )
            compiled_admission = (
                CompiledAdmissionBinding.from_content(
                    plan_digest=plan.plan_digest,
                    effect_step_id=(
                        step.dependencies[0] if step.dependencies else step.step_id
                    ),
                    admission_step_id=step.step_id,
                    operation_contract_digest=step.operation_contract_ref.contract_digest,
                    return_contract_ref=return_binding.return_contract_ref,
                    return_contract_digest=return_binding.binding_digest,
                    source_map_digest=content_digest(plan.source_map),
                    control_digest=plan.control_root.control_digest,
                )
                if assignment_kind is AssignmentKind.VERIFY_ADMIT
                else None
            )
            assignment = RuntimeAssignment(
                runtime_protocol_version="1",
                work_item_id=f"work:{run_id}:{step.step_id}",
                assignment_kind=assignment_kind,
                project_key=project_key,
                run_id=run_id,
                step_id=step.step_id,
                step_role=step_role,
                capability_id=capability_id,
                operation_contract_ref=step.operation_contract_ref,
                operation_contract_digest=step.operation_contract_ref.contract_digest,
                return_contract_binding=return_binding,
                compiled_admission_binding=compiled_admission,
                handler_binding_kind=HandlerBindingKind.INTERPRETER,
                handler_binding_ref=(
                    f"handler-binding:sha256:{interpreter.binding_digest}"
                ),
                handler_binding_digest=interpreter.binding_digest,
                handler_binding=interpreter,
                program_digest=plan.program_digest,
                plan_digest=plan.plan_digest,
                deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                execution_epoch=0,
                incarnation=run_incarnation,
                input_refs=input_refs,
                input_closure_digest=input_digest_by_step[step.step_id],
                queue_eligibility_digest=eligibility.eligibility_digest,
                resource_policy_epoch=RESOURCE_POLICY_EPOCH,
                claim_authority_epoch=authority_epoch,
                claim_policy_digest=CLAIM_POLICY_DIGEST,
                expected_step_revision=0,
                trace_id=f"trace:{run_id}:{step.step_id}",
            )
            assignments.append(assignment)
            authorization = authorizations[len(assignments) - 1]
            envelope = AssignmentEnvelope(
                assignment=assignment,
                required_node_profile_selector=NODE_PROFILE_DIGEST,
                authority_digest=authorization.binding_digest,
                resource_policy_digest=RESOURCE_POLICY_DIGEST,
                fairness_key=project_key,
                qualification_digest=qualified.qualification_digest,
                resource_class=eligibility.resource_class.value,
                resource_units=eligibility.units,
                concurrency_key=eligibility.concurrency_key,
                recovery_binding=recovery,
                authoritative_readback_profile_ref=(
                    recovery.authoritative_readback_profile_ref
                ),
            )
            connection.execute(
                sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(
                    **_assignment_values(envelope, due_at=NOW)
                )
            )

        step_activated_events = tuple(
            {
                "event_type": "StepActivated",
                "schema_version": "mrw.runtime.event.step_activated.v1",
                "step_id": step.step_id,
                "event_metadata_json": {
                    "work_item_id": assignment.work_item_id,
                    "assignment_digest": assignment.assignment_digest,
                    "activation_digest": authorizations[index].binding_digest,
                    "input_closure_digest": assignment.input_closure_digest,
                },
                "authority_digest": authorizations[index].binding_digest,
            }
            for index, (step, assignment) in enumerate(
                zip(authorizable, assignments, strict=True)
            )
        )
        RuntimeJournalRepository(connection, scope).append_transition(
            run_id=run_id,
            expected_revision=3,
            snapshot_values={"state": "READY"},
            events=step_activated_events,
        )

        DeploymentCatalogRepository(connection).put_exact(
            DeploymentCatalog(
                catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                catalog_version="1.0.0",
                catalog_ref="artifact:c1-slice-deployment",
                node_profile_digest=NODE_PROFILE_DIGEST,
                security_profile_digest=SECURITY_PROFILE_DIGEST,
                resource_profile_digest=RESOURCE_PROFILE_DIGEST,
            )
        )
        nodes = RuntimeNodeRepository(connection)
        for node_id in (
            "c1-slice-node-a",
            "c1-slice-node-b",
            "c1-unknown-node",
            "c1-reconcile-node",
        ):
            nodes.register(
                node_id=node_id,
                node_profile_digest=NODE_PROFILE_DIGEST,
                deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                runtime_protocol_version="1",
                started_at=NOW - timedelta(minutes=1),
            )

    ledger = _C1ExecutionLedger()

    def _default_handler(
        binding_digest: str,
        interpreter_profile_digest: str,
        execution_ledger: _C1ExecutionLedger,
    ) -> RuntimeHandler:
        return _C1InterpreterHandler(
            handler_binding_digest=binding_digest,
            interpreter_profile_digest=interpreter_profile_digest,
            ledger=execution_ledger,
        )

    builder = handler_builder or _default_handler
    handlers: dict[str, RuntimeHandler] = {
        interpreter_bindings[kind].binding_digest: builder(
            interpreter_bindings[kind].binding_digest,
            interpreter_bindings[kind].interpreter_profile_digest,
            ledger,
        )
        for kind in interpreter_bindings
    }
    first_kind = next(iter(contracts_by_kind))
    reconcile_binding_digest = recovery_bindings[first_kind].binding_digest
    reconcile_profile_digest = recovery_bindings[first_kind].interpreter_profile_digest
    assert reconcile_profile_digest is not None
    reconcile_handler = _C1WaitingReconcileHandler(
        handler_binding_digest=reconcile_binding_digest,
        interpreter_profile_digest=reconcile_profile_digest,
    )
    for recovery in recovery_bindings.values():
        handlers[recovery.binding_digest] = reconcile_handler

    profile_digests = frozenset(
        binding.interpreter_profile_digest
        for binding in interpreter_bindings.values()
        if binding.interpreter_profile_digest is not None
    )
    return PreparedC1Slice(
        database=database,
        slice_id=slice_id,
        project_key=project_key,
        resolved_schema=resolved_schema,
        scope=scope,
        tables=tables,
        program=program,
        plan=plan,
        catalog=catalog,
        run_id=run_id,
        run_incarnation=run_incarnation,
        authority_epoch=authority_epoch,
        steps=authorizable,
        assignments=tuple(assignments),
        authorizations=tuple(authorizations),
        handler=ledger,
        reconcile_handler=reconcile_handler,
        resolver=_C1ExactResolver(handlers),
        interpreter_profile_digests=profile_digests,
        recovery_binding_digest=reconcile_binding_digest,
    )


def make_node(
    prepared: PreparedC1Slice,
    node_id: str,
    *,
    authority_epoch: int | None = None,
    clock_start: datetime | None = None,
) -> RuntimeNode:
    epoch = prepared.authority_epoch if authority_epoch is None else authority_epoch
    adapter = PostgresRuntimeNodeAdapter(
        runtime_uow_factory(prepared.database.engine),
        terminal_hook=_C1AdmissionCommitHook(),
    )
    return RuntimeNode(
        identity=NodeIdentity(
            node_id=node_id,
            incarnation=f"{node_id}:incarnation:1",
            started_at=NOW - timedelta(minutes=1),
        ),
        profile=RuntimeNodeProfile(
            profile_digest=prepared.profile_digest,
            supported_assignment_kinds=frozenset(
                {
                    AssignmentKind.INTERPRET,
                    AssignmentKind.VERIFY_ADMIT,
                    AssignmentKind.RECONCILE,
                }
            ),
            interpreter_profile_digests=prepared.interpreter_profile_digests,
        ),
        deployment=DeploymentBinding(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            node_profile_digest=prepared.profile_digest,
            runtime_protocol_version="1",
        ),
        protocol=RuntimeNodeProtocol(version="1", claim_batch_size=1),
        control_scope=ControlPlaneScope(
            system_actor_id=node_id,
            permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
            authority_epoch=epoch,
        ),
        claims=adapter,
        interpreters=prepared.resolver,
        outcomes=adapter,
        cancellation=_C1AuthorityGuard(prepared.database.engine, prepared.project_key),
        clock=_FixedClock(NOW if clock_start is None else clock_start),
    )


def run_to_idle(
    prepared: PreparedC1Slice,
    *,
    node_ids: tuple[str, ...] = ("c1-slice-node-a", "c1-slice-node-b"),
    authority_epoch: int | None = None,
) -> list[Any]:
    """Alternate two isomorphic RuntimeNodes until no work remains."""

    nodes = [
        make_node(prepared, node_id, authority_epoch=authority_epoch)
        for node_id in node_ids
    ]
    reports: list[Any] = []
    for _turn in range(200):
        turn_reports = [node.run_once() for node in nodes]
        reports.extend(turn_reports)
        if all(report.claimed == 0 for report in turn_reports):
            return reports
        assert all(
            result.committed for report in turn_reports for result in report.results
        ), f"uncommitted claim results: {turn_reports!r}"
    raise AssertionError("C1 slice runtime did not converge to idle")


def derive_run_completion(
    database: C1Database,
    prepared: PreparedC1Slice,
) -> bool:
    """Derive the production RunCompletionDerived event after all steps."""

    required_step_ids = frozenset(step.step_id for step in prepared.steps)
    with database.engine.begin() as connection:
        return RuntimeLifecycleRepository(
            connection,
            prepared.scope,
        ).complete_if_satisfied(
            prepared.run_id,
            required_step_ids=required_step_ids,
            authority_digest=prepared.authorizations[0].binding_digest,
            observed_at=NOW,
        )


def load_replay_events(
    database: C1Database,
    prepared: PreparedC1Slice,
) -> tuple[ReplayEvent, ...]:
    with database.engine.connect() as connection:
        run = RuntimeJournalRepository(connection, prepared.scope).load_run(
            prepared.run_id
        )
        rows = RuntimeJournalRepository(connection, prepared.scope).load_events(
            prepared.run_id
        )
        incarnation = str(run["incarnation"])
    return tuple(
        ReplayEvent.from_content(
            project_key=prepared.project_key,
            run_id=prepared.run_id,
            run_incarnation=incarnation,
            seq=int(row["seq"]),
            event_type=str(row["event_type"]),
            schema_version=str(row["schema_version"]),
            step_id=row["step_id"],
            attempt_id=row["attempt_id"],
            metadata=dict(row["event_metadata_json"] or {}),
            payload_ref=row["payload_ref"],
            payload_digest=row["payload_digest"],
            authority_digest=str(row["authority_digest"]),
        )
        for row in rows
    )


def replay_digest(
    database: C1Database,
    prepared: PreparedC1Slice,
) -> str:
    return projection_digest(
        replay_runtime_events(load_replay_events(database, prepared))
    )


def rollback_future_owner(
    database: C1Database,
    prepared: PreparedC1Slice,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Advance only the future-owner capability authority epoch by one."""

    table = PUBLIC_TABLES["runtime_capability_authority"]
    before: dict[str, dict[str, Any]] = {}
    with database.engine.begin() as connection:
        for capability_id in prepared.capability_ids:
            row = (
                connection.execute(
                    sa.select(table).where(
                        table.c.project_key == prepared.project_key,
                        table.c.capability_id == capability_id,
                    )
                )
                .mappings()
                .one()
            )
            before[capability_id] = dict(row)
            assert int(row["authority_epoch"]) == prepared.authority_epoch
            connection.execute(
                sa.update(table)
                .where(
                    table.c.project_key == prepared.project_key,
                    table.c.capability_id == capability_id,
                    table.c.revision == row["revision"],
                    table.c.authority_epoch == prepared.authority_epoch,
                )
                .values(
                    authority_epoch=prepared.authority_epoch + 1,
                    revision=int(row["revision"]) + 1,
                )
            )
    after: dict[str, dict[str, Any]] = {}
    with database.engine.connect() as connection:
        for capability_id in prepared.capability_ids:
            row = (
                connection.execute(
                    sa.select(table).where(
                        table.c.project_key == prepared.project_key,
                        table.c.capability_id == capability_id,
                    )
                )
                .mappings()
                .one()
            )
            after[capability_id] = dict(row)
            changed = {
                name: value
                for name, value in row.items()
                if before[capability_id][name] != value
            }
            assert set(changed) <= {
                "authority_epoch",
                "revision",
                "updated_at",
            }, f"rollback mutated non-authority columns: {sorted(changed)}"
            assert int(row["authority_epoch"]) == prepared.authority_epoch + 1
    return before, after


def inject_run_aba_cycle(
    database: C1Database,
    prepared: PreparedC1Slice,
    *,
    suffix: str,
) -> dict[str, object]:
    """Rewrite one runtime run control record through A -> B -> A' (ABA).

    The final A' restores program/plan content digests byte-identical to the
    original A but advances ``revision`` twice and binds a distinct
    non-reusable incarnation, so content equality alone cannot reauthorize the
    old record as the current exact state.
    """

    runs = PUBLIC_TABLES["runtime_runs"]
    with database.engine.connect() as connection:
        original = RuntimeJournalRepository(
            connection,
            prepared.scope,
        ).load_run(prepared.run_id)
    original_revision = int(original["revision"])
    original_incarnation = str(original["incarnation"])
    incarnation_b = f"{original_incarnation}:{suffix}-b"
    incarnation_aba = f"{original_incarnation}:{suffix}-a2"
    with database.engine.begin() as connection:
        updated = connection.execute(
            sa.update(runs)
            .where(
                runs.c.project_key == prepared.project_key,
                runs.c.run_id == prepared.run_id,
            )
            .values(
                program_digest="1" * 64,
                plan_digest="2" * 64,
                incarnation=incarnation_b,
                revision=original_revision + 1,
                updated_at=NOW,
            )
        )
        assert getattr(updated, "rowcount", None) == 1
        restored = connection.execute(
            sa.update(runs)
            .where(
                runs.c.project_key == prepared.project_key,
                runs.c.run_id == prepared.run_id,
            )
            .values(
                program_digest=original["program_digest"],
                plan_digest=original["plan_digest"],
                incarnation=incarnation_aba,
                revision=original_revision + 2,
                updated_at=NOW,
            )
        )
        assert getattr(restored, "rowcount", None) == 1
    return {
        "original_program_digest": str(original["program_digest"]),
        "original_plan_digest": str(original["plan_digest"]),
        "original_incarnation": original_incarnation,
        "original_revision": original_revision,
        "aba_incarnation": incarnation_aba,
        "aba_revision": original_revision + 2,
    }


def snapshot_program(
    database: C1Database,
    prepared: PreparedC1Slice,
) -> bytes:
    with database.engine.connect() as connection:
        reloaded = ProgramRepository(
            connection,
            prepared.tables,
        ).get(
            prepared.scope,
            prepared.program.program_id,
            expected_digest=prepared.program.program_digest,
        )
        return reloaded.canonical_json()


def snapshot_plan(
    database: C1Database,
    prepared: PreparedC1Slice,
) -> bytes:
    from app.successor_runtime.research.codec import canonical_bytes

    with database.engine.connect() as connection:
        reloaded = PlanRepository(connection, prepared.tables).get(
            prepared.scope,
            prepared.plan.plan_digest,
        )
        return canonical_bytes(reloaded)


def snapshot_journal(
    database: C1Database,
    prepared: PreparedC1Slice,
) -> tuple[dict[str, Any], ...]:
    with database.engine.connect() as connection:
        rows = RuntimeJournalRepository(connection, prepared.scope).load_events(
            prepared.run_id
        )
    return tuple(
        {
            "seq": int(row["seq"]),
            "event_type": str(row["event_type"]),
            "schema_version": str(row["schema_version"]),
            "step_id": row["step_id"],
            "attempt_id": row["attempt_id"],
            "event_metadata_json": dict(row["event_metadata_json"] or {}),
            "payload_ref": row["payload_ref"],
            "payload_digest": row["payload_digest"],
            "authority_digest": str(row["authority_digest"]),
        }
        for row in rows
    )


def snapshot_attempts(
    database: C1Database,
    prepared: PreparedC1Slice,
) -> tuple[dict[str, Any], ...]:
    table = PUBLIC_TABLES["runtime_effect_attempts"]
    with database.engine.connect() as connection:
        rows = (
            connection.execute(
                sa.select(table)
                .where(
                    table.c.project_key == prepared.project_key,
                    table.c.run_id == prepared.run_id,
                )
                .order_by(table.c.attempt_id)
            )
            .mappings()
            .all()
        )
    return tuple(
        {
            "attempt_id": str(row["attempt_id"]),
            "step_id": str(row["step_id"]),
            "assignment_digest": str(row["assignment_digest"]),
            "disposition": str(row["disposition"]),
            "receipt_ref": row["receipt_ref"],
            "receipt_digest": row["receipt_digest"],
        }
        for row in rows
    )


def snapshot_receipts(
    database: C1Database,
    prepared: PreparedC1Slice,
) -> tuple[dict[str, Any], ...]:
    table = prepared.tables.successor_receipts
    with database.engine.connect() as connection:
        rows = (
            connection.execute(
                sa.select(table).where(table.c.project_key == prepared.project_key)
            )
            .mappings()
            .all()
        )
    return tuple(
        {
            "receipt_id": str(row["receipt_id"]),
            "receipt_digest": str(row["receipt_digest"]),
            "attempt_ref": str(row["attempt_ref"]),
        }
        for row in rows
    )


def require_old_authority_fails_closed(
    database: C1Database,
    prepared: PreparedC1Slice,
) -> None:
    with database.engine.connect() as connection:
        stored = QualificationStoreRepository(
            connection,
            prepared.scope,
        ).load_step_binding(prepared.run_id, prepared.assignments[0].step_id or "")
        current = PostgresAuthorityProvider(
            connection,
            prepared.scope,
        ).current_step_binding(
            prepared.run_id,
            prepared.assignments[0].step_id or "",
            now=NOW,
        )
        try:
            require_current_authority(stored, current, now=NOW)
        except AuthorityDrift:
            pass
        else:
            raise AssertionError("old authority remained current after rollback")


__all__ = [
    "AUTHORITY_EPOCH",
    "CLAIM_POLICY_DIGEST",
    "DEPLOYMENT_CATALOG_DIGEST",
    "NODE_PROFILE_DIGEST",
    "NOW",
    "RESOURCE_POLICY_DIGEST",
    "C1Database",
    "PreparedC1Slice",
    "c1_database",
    "derive_run_completion",
    "inject_run_aba_cycle",
    "load_replay_events",
    "make_node",
    "prepare_runtime",
    "replay_digest",
    "require_old_authority_fails_closed",
    "rollback_future_owner",
    "run_to_idle",
    "snapshot_attempts",
    "snapshot_journal",
    "snapshot_plan",
    "snapshot_program",
    "snapshot_receipts",
]
