"""Real-PostgreSQL family-local C4.3 idempotency tests.

The test owns a disposable database named ``mrw_p3_c4_worker_test``: it drops
any prior database, creates the generic public ``runtime_idempotency`` table,
exercises shared STARTED/TERMINAL idempotency reserve/replay/conflict/terminal
with family-specific acceptance status in the typed receipt, then drops the
database on teardown.  No shared migration, API, catalog or aggregate evidence
is touched; no provider/network effect runs.  The deterministic RuntimeNode
fixture canary remains in ``test_p3_c4_canary.py`` (fixture-only, no DB).
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_runtime.capabilities import agent_batch_c4 as c4
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.agent_batch_c4 import (
    C4SubmissionConflict,
    PostgresC4SubmissionRepository,
)
from app.successor_runtime.substrate.postgres.idempotency import (
    IdempotencyBinding,
    IdempotencyRepository,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_TABLES,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    StaleRevisionError,
)

from .p3_c4_fixture import (
    PROJECT_KEY,
    REGISTRY_REVISION,
    RESOLVED_SCHEMA,
    SCOPE_DIGEST,
    SCOPE_INCARNATION,
)

pytestmark = pytest.mark.integration

DATABASE_NAME = "mrw_p3_c4_worker_test"
ENV_URL = "SUCCESSOR_TEST_DATABASE_URL"


def _server_url() -> str:
    env_url = os.environ.get(ENV_URL)
    if env_url:
        url = make_url(env_url)
        return url.set(database="postgres").render_as_string(hide_password=False)
    return "postgresql+psycopg2://localhost/postgres"


def _create_database() -> Engine:
    server_url = _server_url()
    server = sa.create_engine(
        server_url, isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        with server.connect() as connection:
            connection.execute(
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
            connection.execute(text("CREATE DATABASE " + DATABASE_NAME))
    except Exception as exc:  # noqa: BLE001 - environment-dependent skip
        server.dispose()
        pytest.skip(f"cannot create disposable database {DATABASE_NAME}: {exc}")
    return server


def _drop_database(server: Engine) -> None:
    try:
        with server.connect() as connection:
            connection.execute(
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
    finally:
        server.dispose()


@pytest.fixture(scope="module")
def disposable_database() -> Iterator[Engine]:
    server = _create_database()
    engine = sa.create_engine(
        make_url(_server_url())
        .set(database=DATABASE_NAME)
        .render_as_string(hide_password=False),
        poolclass=NullPool,
    )
    with engine.begin() as connection:
        # Idempotency tests only need the generic public idempotency table.
        PUBLIC_TABLES["runtime_idempotency"].create(connection)
    try:
        yield engine
    finally:
        engine.dispose()
        _drop_database(server)


def _scope() -> RuntimeScope:
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=PROJECT_KEY,
            resolved_schema=RESOLVED_SCHEMA,
            project_registry_revision=REGISTRY_REVISION,
            incarnation=SCOPE_INCARNATION,
            scope_digest=SCOPE_DIGEST,
        ),
        actor_id="actor:p3-c4-postgres",
    )


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _binding(
    *,
    request_digest: str | None = None,
    logical_request_id: str = "request:p3:c4:pg:001",
    idempotency_id: str = "idem:p3:c4:pg:001",
    run_id: str = "run:p3:c4:pg:001",
) -> IdempotencyBinding:
    return IdempotencyBinding(
        idempotency_id=idempotency_id,
        capability_id=c4.SUBMISSION_OWNER,
        logical_request_id=logical_request_id,
        operation_kind=c4.SUBMISSION_KIND,
        request_digest=request_digest or _digest("request:p3:c4:pg:001"),
        run_id=run_id,
    )


def test_postgres_idempotency_reserve_replay_conflict_terminal(
    disposable_database: Engine,
) -> None:
    scope = _scope()
    with disposable_database.begin() as connection:
        repo = PostgresC4SubmissionRepository(connection, scope)
        binding = _binding()
        reserved, state = repo.reserve(binding)
        assert state == "STARTED"
        assert reserved.request_digest == binding.request_digest
        # The canonical DB row (including generated identity) is returned, not
        # the transient input binding.
        assert reserved.idempotency_id == binding.idempotency_id
        assert reserved.capability_id == binding.capability_id
        assert reserved.logical_request_id == binding.logical_request_id
        assert reserved.state == "STARTED"

        replay, replay_state = repo.reserve(binding)
        assert replay_state == "STARTED"
        assert replay.request_digest == binding.request_digest
        assert replay.run_id == binding.run_id

        with pytest.raises(C4SubmissionConflict):
            repo.reserve(_binding(request_digest=_digest("mutated")))

        terminal = repo.record_terminal(
            capability_id=binding.capability_id,
            logical_request_id=binding.logical_request_id,
            acceptance_state="ACCEPTED",
            receipt_ref="receipt:p3:c4:pg:001",
        )
        assert terminal.state == "TERMINAL"
        assert terminal.terminal_observation_ref == "receipt:p3:c4:pg:001"
        # Terminal replay returns the canonical DB row binding again.
        replay_terminal = repo.load(
            capability_id=binding.capability_id,
            logical_request_id=binding.logical_request_id,
        )
        assert replay_terminal.state == "TERMINAL"
        assert replay_terminal.terminal_observation_ref == "receipt:p3:c4:pg:001"
        assert replay_terminal.idempotency_id == terminal.idempotency_id
        loaded = repo.load(
            capability_id=binding.capability_id,
            logical_request_id=binding.logical_request_id,
        )
        assert loaded.state == "TERMINAL"
        with pytest.raises(StaleRevisionError):
            repo.record_terminal(
                capability_id=binding.capability_id,
                logical_request_id=binding.logical_request_id,
                acceptance_state="ACCEPTED",
                receipt_ref="receipt:p3:c4:pg:002",
            )


def test_postgres_shared_repository_rejects_digest_drift(
    disposable_database: Engine,
) -> None:
    scope = _scope()
    with disposable_database.begin() as connection:
        repo = PostgresC4SubmissionRepository(connection, scope)
        original = _binding(
            request_digest=_digest("shared-repo-original"),
            logical_request_id="request:p3:c4:pg:shared",
            idempotency_id="idem:p3:c4:pg:shared",
            run_id="run:p3:c4:pg:shared",
        )
        repo.reserve(original)
        with pytest.raises(C4SubmissionConflict):
            repo.reserve(
                _binding(
                    request_digest=_digest("mutated"),
                    logical_request_id="request:p3:c4:pg:shared",
                    idempotency_id="idem:p3:c4:pg:shared-mutated",
                    run_id="run:p3:c4:pg:shared-mutated",
                )
            )
        # The underlying shared substrate still reports ExactBindingConflict
        # when used directly with a fresh conflicting digest, proving the
        # generic root owns the conflict.
        with pytest.raises(ExactBindingConflict):
            IdempotencyRepository(connection, scope).reserve(
                _binding(
                    request_digest=_digest("shared-mutated-2"),
                    logical_request_id="request:p3:c4:pg:shared",
                    idempotency_id="idem:p3:c4:pg:shared-mutated-2",
                    run_id="run:p3:c4:pg:shared-mutated-2",
                )
            )


def test_postgres_database_enum_is_generic_started_terminal(
    disposable_database: Engine,
) -> None:
    scope = _scope()
    with disposable_database.begin() as connection:
        repo = PostgresC4SubmissionRepository(connection, scope)
        binding = _binding(
            request_digest=_digest("enum-check"),
            logical_request_id="request:p3:c4:pg:enum",
            idempotency_id="idem:p3:c4:pg:enum",
            run_id="run:p3:c4:pg:enum",
        )
        repo.reserve(binding)
        rows = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_idempotency"].c.state).where(
                    PUBLIC_TABLES["runtime_idempotency"].c.logical_request_id
                    == binding.logical_request_id
                )
            )
            .scalars()
            .all()
        )
        assert rows == ["STARTED"]
        repo.record_terminal(
            capability_id=binding.capability_id,
            logical_request_id=binding.logical_request_id,
            acceptance_state="PARTIALLY_ACCEPTED",
            receipt_ref="receipt:p3:c4:pg:enum",
        )
        rows = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_idempotency"].c.state).where(
                    PUBLIC_TABLES["runtime_idempotency"].c.logical_request_id
                    == binding.logical_request_id
                )
            )
            .scalars()
            .all()
        )
        assert rows == ["TERMINAL"]
