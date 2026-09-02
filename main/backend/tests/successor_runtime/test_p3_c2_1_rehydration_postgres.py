"""Real-PostgreSQL store-rehydration tests for the C2.1 successor handler.

The handler under test captures no Program/Plan/payload fixture.  Stores are
seeded with exact bytes; handler A is constructed and discarded; a fresh
handler B/RuntimeNode rehydrates everything from stores and completes the
claimed READY work item.  Negative cases mutate stores before a direct handler
execute and assert fail-closed ``DefiniteInterpreterFailure`` with zero
terminal writes; one claim-time negative proves the full node path writes
nothing before the effect.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from app.successor_runtime.capabilities import source_library_c2_1 as c2_1_cap
from app.successor_runtime.capabilities.checksum import canonical_json
from app.successor_runtime.runtime.assignments import AssignmentKind
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    DeploymentBinding,
    NodeIdentity,
    RuntimeExecutionContext,
    RuntimeNode,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
)
from app.successor_runtime.substrate.postgres.composition_root import (
    ExactInstalledHandlerResolver,
    PostgresCancellationAuthorityGuard,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
    project_tables,
)
from app.successor_runtime.substrate.postgres.node_adapter import (
    PostgresRuntimeNodeAdapter,
    runtime_uow_factory,
)
from app.successor_runtime.substrate.postgres.runtime_values import (
    RuntimeValueBinding,
    RuntimeValueRepository,
)
from app.successor_runtime.substrate.postgres.session import compute_scope_digest
from app.successor_runtime.substrate.postgres.source_library_c2_1_handler import (
    C2_1_DEPLOYMENT_CATALOG_DRIFT,
    C2_1_PAYLOAD_CODEC_DRIFT,
    C2_1_PAYLOAD_STORE_DRIFT,
    C2_1_PLAN_STORE_DRIFT,
    C2_1_SCOPE_REHYDRATION_DRIFT,
    SourceLibraryC2_1StoreRehydratedHandler,
    c2_1_expected_payload_value_identity,
)
from app.successor_runtime.substrate.postgres.values import (
    ValueRepository,
    derive_value_write_intent_digest,
)
from app.successor_runtime.substrate.postgres.work_items import ClaimBindingMismatch

from . import test_p2_c2_1_canary_postgres as canary

pytestmark = pytest.mark.integration

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_PACKET = (
    _REPOSITORY_ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/"
    "P2C21CapabilityPacket.v5.json"
)


@dataclass(frozen=True, slots=True)
class _Prepared:
    engine: Engine
    c2_1: Any
    authorization: Any


def _make_handler(
    engine: Engine | None,
) -> SourceLibraryC2_1StoreRehydratedHandler:
    c2_1 = canary._c2_1()
    return SourceLibraryC2_1StoreRehydratedHandler(
        uow_factory=(
            runtime_uow_factory(engine)
            if engine is not None
            else lambda: (_ for _ in ()).throw(AssertionError("handler not executed"))
        ),
        handler_binding_digest=c2_1.successor_binding.binding_digest,
        interpreter_profile_digest=(c2_1.successor_binding.interpreter_profile_digest),
        operation_contract_digest=c2_1.contract_ref.contract_digest,
        deployment_catalog_digest=canary.DEPLOYMENT_CATALOG_DIGEST,
    )


def _persist_payload_stores(engine: Engine, c2_1: Any) -> None:
    identity = c2_1_expected_payload_value_identity(c2_1.program)
    ref = c2_1.payload_value_ref
    assert identity.value_id == ref.value_id
    assert identity.storage_ref == ref.storage_ref
    assert identity.content_digest == ref.content_digest
    assert identity.provenance_digest == ref.provenance_digest
    exact_bytes = canonical_json(dataclasses.asdict(c2_1.payload)).encode("utf-8")
    assert hashlib.sha256(exact_bytes).hexdigest() == identity.content_digest
    with engine.begin() as connection:
        tables = project_tables(sa.MetaData(), canary.PROJECT_SCHEMA)
        ValueRepository(connection, tables).put_exact(
            canary.SCOPE,
            value_id=identity.value_id,
            object_type=identity.object_type,
            codec_id=identity.codec_id,
            content=exact_bytes,
            expected_digest=identity.content_digest,
            provenance_digest=identity.provenance_digest,
            expected_revision=0,
            expected_incarnation=identity.incarnation,
            source_ref=identity.storage_ref,
            provenance=dict(identity.provenance),
            write_intent_digest=identity.write_intent_digest,
        )
        RuntimeValueRepository(connection, canary.SCOPE).put_exact(
            RuntimeValueBinding(
                value_id=identity.value_id,
                object_type=identity.object_type,
                codec_id=identity.codec_id,
                content_digest=identity.content_digest,
                byte_size=len(exact_bytes),
                project_value_ref=identity.storage_ref,
                storage_digest=hashlib.sha256(
                    identity.storage_ref.encode()
                ).hexdigest(),
                write_intent_digest=identity.write_intent_digest,
            ),
            state="AVAILABLE",
        )


def _build_node(
    engine: Engine,
    handler: SourceLibraryC2_1StoreRehydratedHandler,
) -> tuple[RuntimeNode, PostgresRuntimeNodeAdapter]:
    c2_1 = canary._c2_1()
    uow_factory = runtime_uow_factory(engine)
    lifecycle = PostgresRuntimeNodeAdapter(uow_factory)
    resolver = ExactInstalledHandlerResolver((handler,))
    node = RuntimeNode(
        identity=NodeIdentity(
            node_id=canary.NODE_ID,
            incarnation=canary.NODE_INCARNATION,
            started_at=canary.NOW - timedelta(minutes=1),
        ),
        profile=RuntimeNodeProfile(
            profile_digest=canary.NODE_PROFILE_DIGEST,
            supported_assignment_kinds=frozenset({AssignmentKind.INTERPRET}),
            interpreter_profile_digests=frozenset(
                {c2_1.successor_binding.interpreter_profile_digest}
            ),
        ),
        deployment=DeploymentBinding(
            catalog_digest=canary.DEPLOYMENT_CATALOG_DIGEST,
            node_profile_digest=canary.NODE_PROFILE_DIGEST,
            runtime_protocol_version="1",
        ),
        protocol=RuntimeNodeProtocol(
            version="1",
            claim_batch_size=8,
            heartbeat_extension=timedelta(seconds=45),
        ),
        control_scope=ControlPlaneScope(
            system_actor_id=canary.NODE_ID,
            permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
            authority_epoch=canary.CANARY_EPOCH,
        ),
        claims=lifecycle,
        interpreters=resolver,
        outcomes=lifecycle,
        cancellation=PostgresCancellationAuthorityGuard(uow_factory),
        clock=canary._TestClock(),
    )
    return node, lifecycle


def _direct_claim(assignment: Any, authorization: Any) -> ClaimBinding:
    return ClaimBinding.bind(
        assignment,
        authorization_digest=authorization.binding_digest,
        lease_token="lease:c2-1-store-direct",
        lease_expires_at=canary.NOW + timedelta(minutes=5),
        node_id=canary.NODE_ID,
        node_profile_digest=canary.NODE_PROFILE_DIGEST,
        authority_digest=authorization.binding_digest,
        interpreter_profile_digest=(
            assignment.handler_binding.interpreter_profile_digest
        ),
    )


def _execution_context() -> RuntimeExecutionContext:
    return RuntimeExecutionContext(
        node=NodeIdentity(
            node_id=canary.NODE_ID,
            incarnation=canary.NODE_INCARNATION,
            started_at=canary.NOW - timedelta(minutes=1),
        ),
        observed_at=canary.NOW,
    )


def _execute_direct(
    prepared: _Prepared,
    *,
    handler: SourceLibraryC2_1StoreRehydratedHandler | None = None,
) -> Any:
    if handler is None:
        handler = _make_handler(prepared.engine)
    claim = _direct_claim(prepared.c2_1.assignment, prepared.authorization)
    return handler.execute(
        prepared.c2_1.assignment,
        claim,
        _execution_context(),
    )


def _assert_zero_terminal(engine: Engine) -> None:
    with engine.connect() as connection:
        attempts = (
            connection.execute(sa.select(PUBLIC_TABLES["runtime_effect_attempts"]))
            .mappings()
            .all()
        )
        events = (
            connection.execute(sa.select(PUBLIC_TABLES["runtime_events"]))
            .mappings()
            .all()
        )
        work = canary._load_work_item(connection)
    assert not attempts
    assert all(event["event_type"] != "RuntimeValueProduced" for event in events)
    assert work["state"] == "READY"
    assert work["lease_token"] is None


def _require_dedicated_database_url() -> str:
    return canary._require_dedicated_database_url()


@pytest.fixture(scope="module")
def live_rehydrated_database() -> Iterator[Engine]:
    database_url = _require_dedicated_database_url()
    engine = canary.create_runtime_engine(database_url, poolclass=NullPool)
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
    project_metadata = sa.MetaData()
    project_tables(project_metadata, canary.PROJECT_SCHEMA)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(f'CREATE SCHEMA IF NOT EXISTS "{canary.PROJECT_SCHEMA}"')
            )
            PUBLIC_METADATA.create_all(connection, checkfirst=False)
            project_metadata.create_all(connection, checkfirst=False)
        yield engine
    finally:
        with engine.begin() as connection:
            PUBLIC_METADATA.drop_all(connection, checkfirst=True)
            connection.execute(
                sa.text(f'DROP SCHEMA IF EXISTS "{canary.PROJECT_SCHEMA}" CASCADE')
            )
        engine.dispose()


@pytest.fixture
def rehydrated_database(
    live_rehydrated_database: Engine,
) -> _Prepared:
    engine = live_rehydrated_database
    c2_1 = canary._c2_1()
    qualified = [f'"public"."{name}"' for name in PUBLIC_TABLES]
    with engine.begin() as connection:
        connection.execute(
            sa.text(f'DROP SCHEMA IF EXISTS "{canary.PROJECT_SCHEMA}" CASCADE')
        )
        connection.execute(sa.text(f'CREATE SCHEMA "{canary.PROJECT_SCHEMA}"'))
        project_metadata = sa.MetaData()
        project_tables(project_metadata, canary.PROJECT_SCHEMA)
        project_metadata.create_all(connection, checkfirst=False)
        connection.execute(
            sa.text(
                "TRUNCATE TABLE " + ", ".join(qualified) + " RESTART IDENTITY CASCADE"
            )
        )
        canary._seed(connection, c2_1)
    with canary.RuntimeUnitOfWork(engine=engine) as uow:
        canary.SourceLibraryC2_1CanaryService(
            uow.connection,
            canary.SCOPE,
        ).promote_canary(canary._canary_packet(c2_1), now=canary.NOW)
        uow.commit()
    _context, authorization, _exact = canary._persist_qualification(engine, c2_1)
    _persist_payload_stores(engine, c2_1)
    return _Prepared(engine=engine, c2_1=c2_1, authorization=authorization)


def test_p2_packet_digests_bound_to_store_rehydration_handler() -> None:
    packet = json.loads(_PACKET.read_bytes())
    c2_1 = canary._c2_1()
    contract = packet["operation_contract"]
    assert contract["contract_digest"] == c2_1.contract_ref.contract_digest
    assert contract["operation_catalog_digest"] == c2_1.catalog.catalog_digest
    assert contract["deployment_catalog_digest"] == canary.DEPLOYMENT_CATALOG_DIGEST
    assert contract["deployment_catalog_digest"] != contract["operation_catalog_digest"]
    assert contract["payload_codec_id"] == c2_1_cap.SOURCE_LIBRARY_C2_1_PAYLOAD_CODEC_ID
    assert packet["interpreters"]["same_program_digest"] == c2_1.program.program_digest
    assert packet["interpreters"]["same_plan_digest"] == c2_1.plan.plan_digest
    handler = _make_handler(None)
    assert handler.handler_binding_digest == c2_1.successor_binding.binding_digest
    assert handler.operation_contract_digest == contract["contract_digest"]
    assert handler.deployment_catalog_digest == contract["deployment_catalog_digest"]


def test_fresh_handler_rehydrates_stores_and_completes_exact_terminal(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    authorization = rehydrated_database.authorization

    handler_a = _make_handler(engine)
    node_a, _ = _build_node(engine, handler_a)
    del handler_a, node_a

    handler_b = _make_handler(engine)
    node_b, _lifecycle_b = _build_node(engine, handler_b)
    report = node_b.run_once()
    assert report.claimed == 1
    assert len(report.results) == 1
    result = report.results[0]
    assert result.state.value == "COMMITTED"
    assert result.executed is True
    assert result.committed is True
    assert result.disposition.value == "SUCCEEDED"
    assert handler_b.provider_calls == 0

    expected = c2_1.interpreter.interpret(
        program=c2_1.program,
        plan=c2_1.plan,
        contract_ref=c2_1.contract_ref,
        payload_ref=c2_1.payload_value_ref,
        payload=c2_1.payload,
        project_scope=c2_1.payload.project_scope,
        catalog=c2_1.catalog,
        deployment_catalog_digest=canary.DEPLOYMENT_CATALOG_DIGEST,
        binding=c2_1.successor_binding,
    )
    assert isinstance(expected, c2_1.interpreter_success)
    observation_digest = expected.value.observation_digest

    with engine.connect() as connection:
        attempt = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.project_key
                    == canary.PROJECT_KEY,
                    PUBLIC_TABLES["runtime_effect_attempts"].c.run_id == canary.RUN_ID,
                )
            )
            .mappings()
            .one()
        )
        step = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                    PUBLIC_TABLES["runtime_steps"].c.project_key == canary.PROJECT_KEY,
                    PUBLIC_TABLES["runtime_steps"].c.run_id == canary.RUN_ID,
                    PUBLIC_TABLES["runtime_steps"].c.step_id == c2_1.step_id,
                )
            )
            .mappings()
            .one()
        )
        work = canary._load_work_item(connection)
        reservations = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_resource_reservations"]).where(
                    PUBLIC_TABLES["runtime_resource_reservations"].c.project_key
                    == canary.PROJECT_KEY,
                    PUBLIC_TABLES["runtime_resource_reservations"].c.run_id
                    == canary.RUN_ID,
                )
            )
            .mappings()
            .all()
        )
        events = canary.RuntimeJournalRepository(
            connection,
            canary.SCOPE,
        ).load_events(canary.RUN_ID)
    assert attempt["attempt_id"] == result.attempt_id
    assert attempt["disposition"] == "SUCCEEDED"
    assert attempt["handler_binding_digest"] == c2_1.successor_binding.binding_digest
    assert (
        attempt["handler_realization_digest"] == c2_1.successor_binding.binding_digest
    )
    assert step["state"] == "SUCCEEDED"
    assert step["output_digest"] == observation_digest
    assert work["state"] == "COMPLETED"
    assert work["lease_token"] is None
    assert work["lease_owner"] is None
    assert all(reservation["state"] == "RELEASED" for reservation in reservations)
    terminal = next(
        event for event in events if event["event_type"] == "RuntimeValueProduced"
    )
    assert terminal["schema_version"] == "mrw.runtime.event.effect_succeeded.v1"
    assert terminal["step_id"] == c2_1.step_id
    assert terminal["attempt_id"] == attempt["attempt_id"]
    assert terminal["authority_digest"] == authorization.binding_digest
    assert events[0]["event_type"] == "CapabilityAuthorityChanged"
    event_count = len(events)

    handler_c = _make_handler(engine)
    node_c, _ = _build_node(engine, handler_c)
    second = node_c.run_once()
    assert second.claimed == 0
    assert second.results == ()
    with engine.connect() as connection:
        after = canary.RuntimeJournalRepository(
            connection,
            canary.SCOPE,
        ).load_events(canary.RUN_ID)
        attempts_after = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.project_key
                    == canary.PROJECT_KEY,
                    PUBLIC_TABLES["runtime_effect_attempts"].c.run_id == canary.RUN_ID,
                )
            )
            .mappings()
            .all()
        )
    assert len(after) == event_count
    assert len(attempts_after) == 1


def test_payload_byte_mutation_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    tables = project_tables(sa.MetaData(), canary.PROJECT_SCHEMA)
    with engine.begin() as connection:
        connection.execute(
            sa.update(tables.successor_values)
            .where(
                tables.successor_values.c.project_key == canary.PROJECT_KEY,
                tables.successor_values.c.value_id == c2_1.payload_value_ref.value_id,
            )
            .values(content_bytes=b'{"tampered": true}')
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_content_digest_drift_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    with engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_values"])
            .where(
                PUBLIC_TABLES["runtime_values"].c.project_key == canary.PROJECT_KEY,
                PUBLIC_TABLES["runtime_values"].c.value_id
                == c2_1.payload_value_ref.value_id,
            )
            .values(content_digest="1" * 64)
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_provenance_json_drift_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    identity = c2_1_expected_payload_value_identity(c2_1.program)
    tables = project_tables(sa.MetaData(), canary.PROJECT_SCHEMA)
    tampered = {**dict(identity.provenance), "tampered": True}
    with engine.begin() as connection:
        connection.execute(
            sa.update(tables.successor_values)
            .where(
                tables.successor_values.c.project_key == canary.PROJECT_KEY,
                tables.successor_values.c.value_id == identity.value_id,
            )
            .values(provenance_json=tampered)
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)

    consistent = {**tampered, "content_digest": identity.content_digest}
    with engine.begin() as connection:
        connection.execute(
            sa.update(tables.successor_values)
            .where(
                tables.successor_values.c.project_key == canary.PROJECT_KEY,
                tables.successor_values.c.value_id == identity.value_id,
            )
            .values(
                provenance_json=consistent,
                provenance_digest=hashlib.sha256(
                    canonical_json(consistent).encode("utf-8")
                ).hexdigest(),
            )
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_successor_values_incarnation_aba_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    identity = c2_1_expected_payload_value_identity(c2_1.program)
    tables = project_tables(sa.MetaData(), canary.PROJECT_SCHEMA)
    foreign_incarnation = "payload-inc:" + "b" * 64
    foreign_intent = derive_value_write_intent_digest(
        project_key=canary.PROJECT_KEY,
        value_id=identity.value_id,
        object_type=identity.object_type,
        codec_id=identity.codec_id,
        content_digest=identity.content_digest,
        provenance_digest=identity.provenance_digest,
        source_ref=identity.storage_ref,
        expected_revision=0,
        expected_incarnation=foreign_incarnation,
        state="AVAILABLE",
    )
    with engine.begin() as connection:
        connection.execute(
            sa.update(tables.successor_values)
            .where(
                tables.successor_values.c.project_key == canary.PROJECT_KEY,
                tables.successor_values.c.value_id == identity.value_id,
            )
            .values(
                incarnation=foreign_incarnation,
                write_intent_digest=foreign_intent,
            )
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_revision_drift_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    identity = c2_1_expected_payload_value_identity(c2_1.program)
    tables = project_tables(sa.MetaData(), canary.PROJECT_SCHEMA)
    with engine.begin() as connection:
        connection.execute(
            sa.update(tables.successor_values)
            .where(
                tables.successor_values.c.project_key == canary.PROJECT_KEY,
                tables.successor_values.c.value_id == identity.value_id,
            )
            .values(revision=99)
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_write_intent_digest_drift_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    identity = c2_1_expected_payload_value_identity(c2_1.program)
    tables = project_tables(sa.MetaData(), canary.PROJECT_SCHEMA)
    with engine.begin() as connection:
        for table in (
            tables.successor_values,
            PUBLIC_TABLES["runtime_values"],
        ):
            connection.execute(
                sa.update(table)
                .where(
                    table.c.project_key == canary.PROJECT_KEY,
                    table.c.value_id == identity.value_id,
                )
                .values(write_intent_digest="1" * 64)
            )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_program_plan_mismatch_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    tables = project_tables(sa.MetaData(), canary.PROJECT_SCHEMA)
    with engine.begin() as connection:
        connection.execute(
            sa.update(tables.research_execution_plans)
            .where(
                tables.research_execution_plans.c.project_key == canary.PROJECT_KEY,
                tables.research_execution_plans.c.plan_digest == c2_1.plan.plan_digest,
            )
            .values(program_digest="1" * 64)
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PLAN_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_project_scope_aba_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    registry = PUBLIC_TABLES["project_scope_registry"]

    def content(revision: int, suffix: str) -> tuple[str, str]:
        incarnation = f"scope-inc:c2-1-rehydrate-{suffix}"
        return (
            incarnation,
            compute_scope_digest(
                canary.PROJECT_KEY,
                canary.PROJECT_SCHEMA,
                revision,
                incarnation,
            ),
        )

    b_incarnation, b_digest = content(2, "B")
    returned_incarnation, returned_digest = content(1, "A-returned")
    with engine.begin() as connection:
        connection.execute(
            sa.update(registry)
            .where(
                registry.c.project_key == canary.PROJECT_KEY,
                registry.c.registry_revision == 1,
            )
            .values(state="RETIRED")
        )
        connection.execute(
            sa.insert(registry).values(
                project_key=canary.PROJECT_KEY,
                registry_revision=2,
                resolved_schema=canary.PROJECT_SCHEMA,
                scope_digest=b_digest,
                incarnation=b_incarnation,
                state="ACTIVE",
                updated_by=canary.ACTOR,
                approval_ref="approval:c2-1-scope-aba",
            )
        )
        connection.execute(
            sa.delete(registry).where(
                registry.c.project_key == canary.PROJECT_KEY,
                registry.c.registry_revision == 2,
            )
        )
        connection.execute(
            sa.update(registry)
            .where(
                registry.c.project_key == canary.PROJECT_KEY,
                registry.c.registry_revision == 1,
            )
            .values(
                state="ACTIVE",
                incarnation=returned_incarnation,
                scope_digest=returned_digest,
                updated_by=canary.ACTOR,
                approval_ref="approval:c2-1-scope-aba-return",
            )
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_SCOPE_REHYDRATION_DRIFT
    _assert_zero_terminal(engine)


def test_wrong_payload_codec_and_ref_fail_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    tables = project_tables(sa.MetaData(), canary.PROJECT_SCHEMA)

    with engine.begin() as connection:
        for table in (
            tables.successor_values,
            PUBLIC_TABLES["runtime_values"],
        ):
            connection.execute(
                sa.update(table)
                .where(
                    table.c.project_key == canary.PROJECT_KEY,
                    table.c.value_id == c2_1.payload_value_ref.value_id,
                )
                .values(codec_id="mrw.wrong.payload.codec.v1")
            )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_CODEC_DRIFT
    _assert_zero_terminal(engine)

    with engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_values"])
            .where(
                PUBLIC_TABLES["runtime_values"].c.project_key == canary.PROJECT_KEY,
                PUBLIC_TABLES["runtime_values"].c.value_id
                == c2_1.payload_value_ref.value_id,
            )
            .values(project_value_ref="project-value:wrong-ref")
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_deployment_catalog_drift_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    with engine.begin() as connection:
        connection.execute(
            sa.delete(PUBLIC_TABLES["runtime_nodes"]).where(
                PUBLIC_TABLES["runtime_nodes"].c.node_id == canary.NODE_ID
            )
        )
        connection.execute(
            sa.delete(PUBLIC_TABLES["runtime_deployment_catalogs"]).where(
                PUBLIC_TABLES["runtime_deployment_catalogs"].c.catalog_digest
                == canary.DEPLOYMENT_CATALOG_DIGEST
            )
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_DEPLOYMENT_CATALOG_DRIFT
    _assert_zero_terminal(engine)


def test_program_plan_ref_drift_fails_before_claim_with_zero_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    with engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_plan_refs"])
            .where(
                PUBLIC_TABLES["runtime_plan_refs"].c.project_key == canary.PROJECT_KEY,
                PUBLIC_TABLES["runtime_plan_refs"].c.plan_digest
                == c2_1.plan.plan_digest,
            )
            .values(program_digest="1" * 64)
        )
    handler = _make_handler(engine)
    node, _ = _build_node(engine, handler)
    with pytest.raises(ClaimBindingMismatch):
        node.run_once()
    _assert_zero_terminal(engine)
