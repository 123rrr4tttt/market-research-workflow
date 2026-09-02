from __future__ import annotations

import hashlib

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.successor_runtime.substrate.postgres.idempotency import (
    IdempotencyBinding,
    IdempotencyRepository,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    StaleRevisionError,
)

from .p0c_postgres_fixture import (
    LiveP0CDatabase,
    live_p0c_database,  # noqa: F401 - registers module-scoped dependency fixture
    p0c_database,  # noqa: F401 - imported pytest fixture
)

pytestmark = pytest.mark.integration


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _binding(*, request_digest: str | None = None) -> IdempotencyBinding:
    return IdempotencyBinding(
        idempotency_id="idem:p3:c4:001",
        capability_id="agent_batch.c4_3.v1",
        logical_request_id="request:p3:c4:001",
        operation_kind="agent_batch.submit.v1",
        request_digest=request_digest or _digest("request:p3:c4:001"),
        run_id="run:p3:c4:001",
    )


def test_started_reserve_replay_conflict_and_terminal_cas(
    p0c_database: LiveP0CDatabase,  # noqa: F811 - pytest fixture injection
) -> None:
    with p0c_database.engine.begin() as connection:
        repository = IdempotencyRepository(connection, p0c_database.scope)
        started = repository.reserve(_binding())
        replay = repository.reserve(_binding())
        assert started["state"] == "STARTED"
        assert replay["request_digest"] == started["request_digest"]

        with pytest.raises(ExactBindingConflict):
            repository.reserve(_binding(request_digest=_digest("mutated")))

        terminal = repository.record_terminal(
            "agent_batch.c4_3.v1",
            "request:p3:c4:001",
            expected_revision=0,
            terminal_observation_ref="receipt:p3:c4:001",
        )
        assert terminal["state"] == "TERMINAL"
        assert terminal["revision"] == 1
        with pytest.raises(StaleRevisionError):
            repository.record_terminal(
                "agent_batch.c4_3.v1",
                "request:p3:c4:001",
                expected_revision=0,
                terminal_observation_ref="receipt:p3:c4:001",
            )


def test_database_rejects_superseded_legacy_open_state(
    p0c_database: LiveP0CDatabase,  # noqa: F811 - pytest fixture injection
) -> None:
    table = PUBLIC_TABLES["runtime_idempotency"]
    with pytest.raises(IntegrityError), p0c_database.engine.begin() as connection:
        connection.execute(
            sa.insert(table).values(
                idempotency_id="idem:p3:open-invalid",
                project_key=p0c_database.scope.project_scope.project_key,
                capability_id="agent_batch.c4_3.v1",
                logical_request_id="request:p3:open-invalid",
                operation_kind="agent_batch.submit.v1",
                request_digest=_digest("open-invalid"),
                run_id=None,
                terminal_observation_ref=None,
                state="OPEN",
                revision=0,
            )
        )
