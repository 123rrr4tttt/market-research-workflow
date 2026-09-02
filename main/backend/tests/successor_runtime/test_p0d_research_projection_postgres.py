"""Real-PostgreSQL evidence for the P0-D Research Ledger projection."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from app.successor_runtime.research.codec import canonical_json, sha256_hex
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork
from app.successor_runtime.substrate.projections import (
    PostgresResearchLedgerProjector,
)

from .p0c_postgres_fixture import PROJECT_KEY, LiveP0CDatabase

pytest_plugins = ("tests.successor_runtime.p0c_postgres_fixture",)
pytestmark = pytest.mark.integration

NOW = datetime(2031, 1, 2, 3, 4, tzinfo=UTC)


def _digest(label: str) -> str:
    return sha256_hex({"fixture": label})


def _ref(object_id: str, object_type: str) -> dict[str, object]:
    return {
        "object_id": object_id,
        "object_type": object_type,
        "project_key": PROJECT_KEY,
        "revision": 1,
        "incarnation": f"inc:{object_id}",
        "owner_binding_ref": "ResearchLedger",
        "content_ref": f"successor-value:{object_id}",
        "content_digest": _digest(f"content:{object_id}"),
    }


def _seed_ledger(database: LiveP0CDatabase) -> None:
    objects = database.project_tables.research_objects
    relations = database.project_tables.research_relations
    inquiry = _ref("inquiry:p0d-projection", "Inquiry.v1")
    claim = _ref("claim:p0d-projection", "Claim.v1")
    with database.engine.begin() as connection:
        connection.execute(
            sa.insert(objects),
            [
                {
                    "project_key": PROJECT_KEY,
                    "object_id": ref["object_id"],
                    "object_type": ref["object_type"],
                    "revision": ref["revision"],
                    "incarnation": ref["incarnation"],
                    "lifecycle_state": "ADMITTED",
                    "owner_binding_ref": ref["owner_binding_ref"],
                    "content_ref": ref["content_ref"],
                    "content_digest": ref["content_digest"],
                    "provenance_closure_digest": _digest(
                        f"provenance:{ref['object_id']}"
                    ),
                    "valid_from": NOW,
                    "valid_to": None,
                }
                for ref in (inquiry, claim)
            ],
        )
        connection.execute(
            sa.insert(relations).values(
                project_key=PROJECT_KEY,
                relation_id="relation:answers:p0d-projection",
                relation_type="answers",
                source_object_ref=json.dumps(
                    claim, sort_keys=True, separators=(",", ":")
                ),
                target_object_ref=json.dumps(
                    inquiry, sort_keys=True, separators=(",", ":")
                ),
                direction="NONE",
                scope_ref="scope:p0d-projection",
                uncertainty_profile_ref="uncertainty:explicit",
                validity_json={"valid_from": "2031-01-02T03:04:00Z"},
                provenance_closure_digest=_digest("provenance:answers"),
                revision=1,
                incarnation="inc:relation:answers:p0d-projection",
                state="ACTIVE",
            )
        )


@contextmanager
def _capture_statements(
    database: LiveP0CDatabase,
) -> Iterator[list[str]]:
    statements: list[str] = []

    def before_execute(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement)

    sa.event.listen(database.engine, "before_cursor_execute", before_execute)
    try:
        yield statements
    finally:
        sa.event.remove(database.engine, "before_cursor_execute", before_execute)


def test_delete_disposable_artifact_and_rebuild_is_digest_equivalent(
    p0c_database: LiveP0CDatabase,
) -> None:
    _seed_ledger(p0c_database)
    with _capture_statements(p0c_database) as statements:
        with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
            first = PostgresResearchLedgerProjector(
                uow.connection,
                p0c_database.project_tables,
                p0c_database.scope,
            ).rebuild()
            uow.commit()
        cache = {"research-ledger": first}
        first_digest = cache["research-ledger"].projection_digest
        del cache["research-ledger"]
        assert cache == {}
        with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
            rebuilt = PostgresResearchLedgerProjector(
                uow.connection,
                p0c_database.project_tables,
                p0c_database.scope,
            ).rebuild()
            uow.commit()

    assert first_digest == rebuilt.projection_digest
    assert first.source_closure_digest == rebuilt.source_closure_digest
    assert first.scope_incarnation == p0c_database.scope.project_scope.incarnation
    assert first.scope_digest == p0c_database.scope.project_scope.scope_digest
    assert [
        (row.object_id, row.revision, row.incarnation) for row in first.objects
    ] == [
        ("claim:p0d-projection", 1, "inc:claim:p0d-projection"),
        ("inquiry:p0d-projection", 1, "inc:inquiry:p0d-projection"),
    ]
    assert len(first.relations) == 1
    relation = first.relations[0]
    assert relation.revision == 1
    assert relation.source_object_ref["content_digest"] == _digest(
        "content:claim:p0d-projection"
    )
    assert relation.target_object_ref["revision"] == 1
    artifact_text = canonical_json(first.to_json())
    assert "content_bytes" not in artifact_text
    assert "runtime_run_projections" not in artifact_text

    selects = [
        statement for statement in statements if statement.lstrip().startswith("SELECT")
    ]
    assert len(selects) == 2
    assert all("research_objects" in statement for statement in selects)
    assert all("research_relations" in statement for statement in selects)
    assert all("runtime_" not in statement for statement in selects)
    assert all(
        p0c_database.scope.project_scope.resolved_schema in statement
        for statement in selects
    )


def test_runtime_projection_drift_cannot_drive_or_change_ledger_projection(
    p0c_database: LiveP0CDatabase,
) -> None:
    _seed_ledger(p0c_database)
    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        first = PostgresResearchLedgerProjector(
            uow.connection, p0c_database.project_tables, p0c_database.scope
        ).rebuild()
        uow.commit()

    runtime_projection = PUBLIC_TABLES["runtime_run_projections"]
    with p0c_database.engine.begin() as connection:
        connection.execute(
            sa.insert(runtime_projection).values(
                project_key=PROJECT_KEY,
                projector_id="hostile-runtime-projection",
                projector_version="1",
                source_ref="runtime-run:hostile",
                source_incarnation="runtime-inc:hostile",
                run_id="run:hostile",
                projection_generation=999,
                source_revision=999,
                source_digest=_digest("hostile-source"),
                state_json={"claim": "must-not-control-research-ledger"},
                projection_digest=_digest("hostile-projection"),
                revision=999,
            )
        )

    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        rebuilt = PostgresResearchLedgerProjector(
            uow.connection, p0c_database.project_tables, p0c_database.scope
        ).rebuild()
        uow.commit()

    assert rebuilt == first
    with p0c_database.engine.connect() as connection:
        assert connection.scalar(
            sa.select(sa.func.count()).select_from(
                p0c_database.project_tables.research_objects
            )
        ) == len(first.objects)
        assert connection.scalar(
            sa.select(sa.func.count()).select_from(
                p0c_database.project_tables.research_relations
            )
        ) == len(first.relations)
        hostile = connection.execute(sa.select(runtime_projection)).mappings().one()
    assert hostile["revision"] == 999
    assert hostile["state_json"]["claim"] == "must-not-control-research-ledger"
