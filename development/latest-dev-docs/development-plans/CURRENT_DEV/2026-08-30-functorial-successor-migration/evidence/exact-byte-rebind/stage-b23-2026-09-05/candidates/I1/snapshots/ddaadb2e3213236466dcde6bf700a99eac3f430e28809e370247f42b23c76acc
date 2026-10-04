"""Real-PostgreSQL C5.2 exact-binding reconciliation negative acceptance."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta

import pytest
import sqlalchemy as sa
from app.successor_migration.legacy_effect_attempts import (
    ExactLegacyAttemptBinding,
    LegacyAttemptBindingMismatch,
    LegacyInterpreterProfile,
    replay_effect_attempt,
    require_exact_adoption,
)
from app.successor_runtime.runtime.assignments import RecoveryBinding
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import RuntimeClaim
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    ReconciliationHandlerOutcome,
    ReconciliationResult,
    ReconciliationState,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
)
from app.successor_runtime.substrate.postgres.reconciliation import (
    PostgresReconciliationOwner,
)
from app.successor_runtime.substrate.postgres.session import (
    compute_scope_digest,
    create_runtime_engine,
)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from . import test_p0c_postgres_reconciliation as owner_test

pytestmark = pytest.mark.integration

DATABASE_ENV = "SUCCESSOR_TEST_DATABASE_URL"
WORKER_DATABASE_ENV = "SUCCESSOR_P3_C5_DATABASE_URL"
WORKER_DATABASE_MARKER = "mrw_p3_c5_worker_test"
PROJECT_KEY = "project-1"
PROJECT_SCHEMA = "mrw_p3_c5_reconcile"
REGISTRY_REVISION = 1
PROGRAM_ID = "program:p3-c5-reconcile"
SCOPE_INCARNATION = "p3-c5-reconcile-incarnation-1"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    PROJECT_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)
AUTHORIZATION_DIGEST = owner_test._digest("authorization")
CALL_ID = "call:pg-reconcile"
IDEMPOTENCY_KEY = "external:idem:pg-reconcile"
READBACK_LOCATOR = "provider:pg-reconcile:receipt"


def _recovery_and_profile() -> tuple[RecoveryBinding, LegacyInterpreterProfile]:
    profile = LegacyInterpreterProfile.from_content(
        interpreter_id="legacy.pg.interpreter",
        interpreter_version="1.0.0",
        provider_id="provider.pg.fixture",
        provider_version="2.0.0",
    )
    recovery = RecoveryBinding.from_content(
        recovery_handler_id="authoritative-readback",
        recovery_handler_version="1",
        interpreter_profile_digest=profile.profile_digest,
        authoritative_readback_profile_ref="readback-profile:pg",
    )
    return recovery, profile


@dataclass(frozen=True, slots=True)
class PgStore:
    engine: Engine
    original: object
    original_claim: ClaimBinding
    runtime_claim: RuntimeClaim
    recovery: RecoveryBinding
    profile: LegacyInterpreterProfile


def _require_database_url() -> str:
    worker_url = os.environ.get(WORKER_DATABASE_ENV)
    value = worker_url or os.environ.get(DATABASE_ENV)
    if not value:
        pytest.skip(f"{DATABASE_ENV} or {WORKER_DATABASE_ENV} is not set")
    url = make_url(value)
    if not url.drivername.startswith("postgresql"):
        pytest.fail("P3 C5 reconciliation requires a PostgreSQL URL")
    database_name = url.database or ""
    if database_name in {"postgres", "template0", "template1"} or not re.search(
        r"(?:test|testing|ci)", database_name, re.IGNORECASE
    ):
        pytest.fail(f"P3 C5 reconciliation refuses non-test database {database_name!r}")
    if worker_url and WORKER_DATABASE_MARKER not in database_name:
        pytest.fail(
            f"{WORKER_DATABASE_ENV} must name the unique worker database "
            f"{WORKER_DATABASE_MARKER!r}"
        )
    return value


@pytest.fixture(scope="module")
def live_pg_database() -> Iterator[Engine]:
    database_url = _require_database_url()
    engine = create_runtime_engine(database_url, poolclass=NullPool)
    inspector = sa.inspect(engine)
    existing_public = set(inspector.get_table_names(schema="public")) & set(
        PUBLIC_TABLES
    )
    if existing_public:
        engine.dispose()
        pytest.fail(
            "dedicated database already contains successor public tables; "
            f"refusing overwrite: {sorted(existing_public)}"
        )
    if PROJECT_SCHEMA in set(inspector.get_schema_names()):
        engine.dispose()
        pytest.fail(
            f"dedicated database already contains {PROJECT_SCHEMA}; refusing overwrite"
        )
    try:
        with engine.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA "{PROJECT_SCHEMA}"'))
            PUBLIC_METADATA.create_all(connection, checkfirst=False)
        yield engine
    finally:
        with engine.begin() as connection:
            PUBLIC_METADATA.drop_all(connection, checkfirst=True)
            connection.execute(
                sa.text(f'DROP SCHEMA IF EXISTS "{PROJECT_SCHEMA}" CASCADE')
            )
        engine.dispose()


def _seed(live_pg_database: Engine) -> PgStore:
    recovery, profile = _recovery_and_profile()
    original = owner_test._effect_assignment(recovery)
    original_claim = ClaimBinding.bind(
        original,
        authorization_digest=AUTHORIZATION_DIGEST,
        lease_token="lease-original",
        lease_expires_at=owner_test.NOW + timedelta(minutes=1),
        node_id="node-previous",
        node_profile_digest=owner_test._digest("old-node-profile"),
        authority_digest=AUTHORIZATION_DIGEST,
        interpreter_profile_digest=recovery.interpreter_profile_digest,
        execution_reservation_ref="reservation:original",
        execution_reservation_digest=owner_test._digest("reservation"),
    )
    target_attempt_id = original_claim.attempt_id
    assignment = owner_test._recovery_assignment(original, recovery, target_attempt_id)
    claim = ClaimBinding.bind(
        assignment,
        authorization_digest=AUTHORIZATION_DIGEST,
        lease_token="lease-reconcile",
        lease_expires_at=owner_test.NOW + timedelta(minutes=2),
        node_id="runtime-node",
        node_profile_digest=owner_test._digest("node-profile"),
        authority_digest=AUTHORIZATION_DIGEST,
        interpreter_profile_digest=recovery.interpreter_profile_digest,
    )
    runtime_claim = RuntimeClaim(
        assignment=assignment,
        claim_binding=claim,
        work_item_revision=2,
    )
    original_work = dict(
        owner_test._work_values(
            original,
            state="COMPLETED",
            revision=4,
            claim=original_claim,
            recovery=recovery,
        )
    )
    original_work.update(
        resource_class="cpu",
        resource_units=1,
        lease_token=None,
        lease_owner=None,
        lease_expires_at=None,
        claim_attempt_id=None,
    )
    reconcile_work = dict(
        owner_test._work_values(
            assignment,
            state="CLAIMED",
            revision=2,
            claim=claim,
            recovery=recovery,
        )
    )
    reconcile_work["claim_attempt_id"] = claim.attempt_id
    with live_pg_database.begin() as connection:
        connection.execute(
            sa.insert(PUBLIC_TABLES["project_scope_registry"]).values(
                project_key=PROJECT_KEY,
                registry_revision=REGISTRY_REVISION,
                resolved_schema=PROJECT_SCHEMA,
                scope_digest=SCOPE_DIGEST,
                incarnation=SCOPE_INCARNATION,
                state="ACTIVE",
                updated_by="p3-c5-reconcile-fixture",
                approval_ref="approval:p3-c5-reconcile-scope",
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_program_refs"]).values(
                program_id=PROGRAM_ID,
                project_key=PROJECT_KEY,
                program_digest=original.program_digest,
                project_storage_ref="project-program:p3-c5-reconcile",
                contract_version="1.0.0",
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_plan_refs"]).values(
                plan_id="plan:p3-c5-reconcile",
                project_key=PROJECT_KEY,
                plan_digest=original.plan_digest,
                program_id=PROGRAM_ID,
                program_digest=original.program_digest,
                project_storage_ref="project-plan:p3-c5-reconcile",
                compiler_id="compiler:p3-c5-reconcile",
                compiler_version="1.0.0",
                operation_catalog_id="catalog:p3-c5-reconcile",
                catalog_version="1.0.0",
                catalog_digest=owner_test._digest("catalog"),
                effect_closure_digest=owner_test._digest("effect"),
                authority_closure_digest=owner_test._digest("authority"),
                resource_closure_digest=owner_test._digest("resource"),
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_runs"]).values(
                run_id=original.run_id,
                project_key=PROJECT_KEY,
                project_registry_revision=REGISTRY_REVISION,
                project_scope_digest=SCOPE_DIGEST,
                resolved_schema=PROJECT_SCHEMA,
                program_id=PROGRAM_ID,
                program_digest=original.program_digest,
                plan_id="plan:p3-c5-reconcile",
                plan_digest=original.plan_digest,
                qualification_digest=owner_test._digest("qualification"),
                state="RECONCILING",
                revision=7,
                next_event_seq=10,
                execution_epoch=1,
                incarnation=original.incarnation,
                submission_authority_digest=AUTHORIZATION_DIGEST,
                cancellation_requested=False,
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_steps"]).values(
                project_key=PROJECT_KEY,
                run_id=original.run_id,
                step_id=original.step_id,
                operation_id="operation:p3-c5-reconcile",
                operation_kind="fixture.c5.operation.v1",
                operation_version="1",
                state="RECONCILING",
                revision=5,
                execution_epoch=1,
                input_digest=original.input_closure_digest,
                effect_class="fixture",
                resource_class="cpu",
                capability_id=original.capability_id,
                claim_owner="successor",
                claim_authority_epoch=2,
                claim_policy_digest=original.claim_policy_digest,
                lease_token=claim.lease_token,
                lease_owner=claim.node_id,
                lease_expires_at=claim.lease_expires_at,
                updated_at=owner_test.NOW,
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_work_items"]),
            [original_work, reconcile_work],
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_effect_attempts"]).values(
                project_key=PROJECT_KEY,
                attempt_id=target_attempt_id,
                run_id=original.run_id,
                step_id=original.step_id,
                execution_epoch=original.execution_epoch,
                incarnation=original.incarnation,
                assignment_digest=original.assignment_digest,
                handler_binding_digest=original.handler_binding_digest,
                handler_realization_digest=original.handler_binding_digest,
                idempotency_key=IDEMPOTENCY_KEY,
                authorization_digest=AUTHORIZATION_DIGEST,
                input_digest=original.input_closure_digest,
                claim_binding_json=original_claim.model_dump(mode="json"),
                claim_binding_digest=original_claim.binding_digest,
                disposition="OUTCOME_UNKNOWN",
                revision=3,
                updated_at=owner_test.NOW,
            )
        )
    return PgStore(
        engine=live_pg_database,
        original=original,
        original_claim=original_claim,
        runtime_claim=runtime_claim,
        recovery=recovery,
        profile=profile,
    )


@pytest.fixture
def pg_store(live_pg_database: Engine) -> PgStore:
    with live_pg_database.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE TABLE "
                + ", ".join(f'"public"."{name}"' for name in PUBLIC_TABLES)
                + " RESTART IDENTITY CASCADE"
            )
        )
    return _seed(live_pg_database)


def _table_counts(connection: sa.Connection) -> dict[str, int]:
    return {
        name: int(
            connection.scalar(
                sa.select(sa.func.count()).select_from(PUBLIC_TABLES[name])
            )
        )
        for name in (
            "runtime_effect_attempts",
            "runtime_events",
            "runtime_work_items",
            "runtime_steps",
            "runtime_runs",
        )
    }


def _valid_binding(store: PgStore) -> ExactLegacyAttemptBinding:
    return ExactLegacyAttemptBinding.from_claim(
        store.original_claim,
        call_id=CALL_ID,
        external_idempotency_key=IDEMPOTENCY_KEY,
        authoritative_readback_locator=READBACK_LOCATOR,
        capability_id=store.original.capability_id,
    )


def _record(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "call_id": CALL_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
        "authoritative_readback_locator": READBACK_LOCATOR,
        "capability_id": None,
        "status": "",
    }
    values.update(overrides)
    return values


def _readback(
    store: PgStore, binding: ExactLegacyAttemptBinding
) -> AuthoritativeEffectReadback:
    return AuthoritativeEffectReadback(
        attempt_id=binding.attempt_id,
        disposition=EffectDisposition.SUCCEEDED,
        provider_locator=binding.authoritative_readback_locator,
        receipt_digest=owner_test._digest("receipt"),
        observation_digest=owner_test._digest("observation"),
    )


def test_exact_binding_adoption_is_accepted_once_over_postgres(
    pg_store: PgStore,
) -> None:
    binding = _valid_binding(pg_store)
    replay_effect_attempt(
        _record(),
        assignment=pg_store.original,
        recovery=pg_store.recovery,
        profile=pg_store.profile,
        binding=binding,
        observed_at=owner_test.NOW + timedelta(seconds=1),
    )
    readback = _readback(pg_store, binding)
    require_exact_adoption(
        binding,
        claim=pg_store.original_claim,
        assignment=pg_store.original,
        readback=readback,
    )
    outcome = ReconciliationHandlerOutcome(
        result=ReconciliationResult(
            state=ReconciliationState.RESOLVED,
            attempt_id=binding.attempt_id,
            disposition=EffectDisposition.SUCCEEDED,
            readback=readback,
        ),
        output_digest=owner_test._digest("output"),
        receipt_ref="receipt:authoritative",
    )
    with pg_store.engine.begin() as connection:
        PostgresReconciliationOwner(
            connection,
            terminal_authority=owner_test._AllowCurrentTerminalAuthority(),
            failure_policy=owner_test._StaticFailurePolicy(required=True),
        ).adopt(
            claim=pg_store.runtime_claim,
            outcome=outcome,
            actor_id="runtime-node",
            observed_at=owner_test.NOW + timedelta(seconds=1),
        )
    with pg_store.engine.connect() as connection:
        disposition = connection.scalar(
            sa.select(PUBLIC_TABLES["runtime_effect_attempts"].c.disposition).where(
                PUBLIC_TABLES["runtime_effect_attempts"].c.attempt_id
                == binding.attempt_id
            )
        )
        event_count = connection.scalar(
            sa.select(sa.func.count()).select_from(PUBLIC_TABLES["runtime_events"])
        )
    assert disposition == EffectDisposition.SUCCEEDED.value
    assert event_count == 1


@pytest.mark.parametrize(
    ("case", "mutate"),
    [
        ("unrelated_call", lambda record: record.update(call_id="call:unrelated")),
        (
            "wrong_capability",
            lambda record: record.update(capability_id="mrw.wrong.capability"),
        ),
        (
            "idempotency",
            lambda record: record.update(idempotency_key="external:idem:wrong"),
        ),
    ],
)
def test_durable_binding_mismatch_writes_nothing_over_postgres(
    pg_store: PgStore,
    case: str,
    mutate,
) -> None:
    binding = _valid_binding(pg_store)
    record = _record()
    mutate(record)
    with pg_store.engine.connect() as connection:
        before = _table_counts(connection)
    with pytest.raises(LegacyAttemptBindingMismatch):
        replay_effect_attempt(
            record,
            assignment=pg_store.original,
            recovery=pg_store.recovery,
            profile=pg_store.profile,
            binding=binding,
            observed_at=owner_test.NOW,
        )
    with pg_store.engine.connect() as connection:
        after = _table_counts(connection)
        disposition = connection.scalar(
            sa.select(PUBLIC_TABLES["runtime_effect_attempts"].c.disposition)
        )
    assert before == after, case
    assert disposition == "OUTCOME_UNKNOWN"


def test_readback_locator_mismatch_writes_nothing_over_postgres(
    pg_store: PgStore,
) -> None:
    binding = _valid_binding(pg_store)
    evidence = replay_effect_attempt(
        _record(),
        assignment=pg_store.original,
        recovery=pg_store.recovery,
        profile=pg_store.profile,
        binding=binding,
        observed_at=owner_test.NOW,
    )
    assert evidence.observation.attempt_id == binding.attempt_id
    readback = AuthoritativeEffectReadback(
        attempt_id=binding.attempt_id,
        disposition=EffectDisposition.SUCCEEDED,
        provider_locator="provider:unrelated",
        receipt_digest=owner_test._digest("receipt"),
        observation_digest=owner_test._digest("observation"),
    )
    with pg_store.engine.connect() as connection:
        before = _table_counts(connection)
    with pytest.raises(LegacyAttemptBindingMismatch):
        require_exact_adoption(
            binding,
            claim=pg_store.original_claim,
            assignment=pg_store.original,
            readback=readback,
        )
    with pg_store.engine.connect() as connection:
        after = _table_counts(connection)
        disposition = connection.scalar(
            sa.select(PUBLIC_TABLES["runtime_effect_attempts"].c.disposition)
        )
    assert before == after
    assert disposition == "OUTCOME_UNKNOWN"
