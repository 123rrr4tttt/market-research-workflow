from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa

from migrations.versions._snapshots.adoption_schema_20260924_20260926 import (
    INFORMATION_TOPOLOGY_TABLES,
    PROJECT_RETRIEVAL_TABLES,
    MigrationAdoptionError,
    adopt_or_create_tables,
    preflight_adoption,
)


BACKEND_DIR = Path(__file__).resolve().parents[2]
REVISION_FILES = (
    BACKEND_DIR / "migrations/versions/20260924_000001_add_information_topology.py",
    BACKEND_DIR / "migrations/versions/20260926_000001_add_project_retrieval.py",
)
ALL_TABLES = (*INFORMATION_TOPOLOGY_TABLES, *PROJECT_RETRIEVAL_TABLES)
DATABASE_URL_ENV = "MRW_MIGRATION_ADOPTION_TEST_DATABASE_URL"


def test_revisions_use_only_the_immutable_snapshot_for_adoption_schema() -> None:
    for revision_file in REVISION_FILES:
        source = revision_file.read_text(encoding="utf-8")
        assert "adoption_schema_20260924_20260926" in source
        assert "app.models" not in source
        assert "restore the verified database snapshot" in source


@pytest.fixture(scope="session")
def adoption_engine() -> sa.Engine:
    database_url = os.getenv(DATABASE_URL_ENV)
    if not database_url:
        pytest.skip(f"{DATABASE_URL_ENV} is required for PostgreSQL adoption tests")
    engine = sa.create_engine(database_url)
    with engine.connect() as connection:
        database_name = str(connection.execute(sa.text("SELECT current_database() ")).scalar_one())
    if database_name != "mrw_release_migration_owner_test":
        engine.dispose()
        pytest.fail(
            f"refusing migration adoption tests against database {database_name!r}"
        )
    yield engine
    engine.dispose()


@pytest.fixture()
def adoption_schema(adoption_engine: sa.Engine) -> str:
    schema = f"migration_adoption_{uuid4().hex[:12]}"
    with adoption_engine.begin() as connection:
        connection.execute(sa.schema.CreateSchema(schema))
    try:
        yield schema
    finally:
        with adoption_engine.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))


def _operations(connection: sa.Connection) -> Operations:
    return Operations(MigrationContext.configure(connection))


def _create(
    connection: sa.Connection,
    schema: str,
    tables: tuple[object, ...] = ALL_TABLES,
) -> None:
    adopt_or_create_tables(connection, _operations(connection), (schema,), tables)


def _insert_state(connection: sa.Connection, schema: str, state_id: str) -> int:
    qualified = f'"{schema}".information_topology_states'
    return int(
        connection.execute(
            sa.text(
                f"INSERT INTO {qualified} "
                "(project_key, module_id, namespace, state_id, profile_id, "
                "profile_version, revision, payload, digest, is_current, deleted) "
                "VALUES ('migration-test', 'module', 'namespace', :state_id, "
                "'profile', 'v1', 1, '{}'::jsonb, :digest, true, false) RETURNING id"
            ),
            {"state_id": state_id, "digest": "d" * 64},
        ).scalar_one()
    )


def test_empty_schema_creates_all_five_tables_and_repeat_preserves_sentinel(
    adoption_engine: sa.Engine, adoption_schema: str
) -> None:
    with adoption_engine.begin() as connection:
        _create(connection, adoption_schema)
        sentinel_id = _insert_state(connection, adoption_schema, "empty-schema-sentinel")
        repeated = adopt_or_create_tables(
            connection, _operations(connection), (adoption_schema,), ALL_TABLES
        )
        assert all(not plan.create_table for plan in repeated)
        assert all(not plan.missing_uniques for plan in repeated)
        assert all(not plan.missing_indexes for plan in repeated)

        inspector = sa.inspect(connection)
        assert {
            table.name for table in ALL_TABLES
        } <= set(inspector.get_table_names(schema=adoption_schema))
        stored = connection.execute(
            sa.text(
                f'SELECT id, state_id FROM "{adoption_schema}".'
                "information_topology_states WHERE id=:sentinel_id"
            ),
            {"sentinel_id": sentinel_id},
        ).one()
        assert stored == (sentinel_id, "empty-schema-sentinel")


def test_partial_existing_tables_are_adopted_and_missing_tables_are_created(
    adoption_engine: sa.Engine, adoption_schema: str
) -> None:
    with adoption_engine.begin() as connection:
        _create(
            connection,
            adoption_schema,
            (INFORMATION_TOPOLOGY_TABLES[0], PROJECT_RETRIEVAL_TABLES[0]),
        )
        sentinel_id = _insert_state(connection, adoption_schema, "partial-sentinel")
        plans = adopt_or_create_tables(
            connection, _operations(connection), (adoption_schema,), ALL_TABLES
        )
        assert sum(plan.create_table for plan in plans) == 3
        assert connection.execute(
            sa.text(
                f'SELECT state_id FROM "{adoption_schema}".'
                "information_topology_states WHERE id=:sentinel_id"
            ),
            {"sentinel_id": sentinel_id},
        ).scalar_one() == "partial-sentinel"
        assert all(
            not plan.create_table
            for plan in preflight_adoption(connection, (adoption_schema,), ALL_TABLES)
        )


def test_missing_safe_constraint_and_index_are_added_without_data_change(
    adoption_engine: sa.Engine, adoption_schema: str
) -> None:
    table = INFORMATION_TOPOLOGY_TABLES[0]
    with adoption_engine.begin() as connection:
        _create(connection, adoption_schema, (table,))
        sentinel_id = _insert_state(connection, adoption_schema, "repair-sentinel")
        connection.execute(
            sa.text(
                f'ALTER TABLE "{adoption_schema}".{table.name} '
                "DROP CONSTRAINT uq_information_topology_state_revision"
            )
        )
        connection.execute(
            sa.text(
                f'DROP INDEX "{adoption_schema}".'
                "uq_information_topology_state_current"
            )
        )

        plans = adopt_or_create_tables(
            connection, _operations(connection), (adoption_schema,), (table,)
        )
        assert plans[0].missing_uniques[0].name == "uq_information_topology_state_revision"
        assert plans[0].missing_indexes[0].name == "uq_information_topology_state_current"
        assert connection.execute(
            sa.text(
                f'SELECT count(*) FROM "{adoption_schema}".{table.name} '
                "WHERE id=:sentinel_id"
            ),
            {"sentinel_id": sentinel_id},
        ).scalar_one() == 1


@pytest.mark.parametrize(
    ("alteration", "property_fragment"),
    (
        (
            "ALTER COLUMN project_key TYPE varchar(64)",
            "column project_key type",
        ),
        (
            "ALTER COLUMN link_id DROP NOT NULL",
            "column link_id nullability",
        ),
        (
            "ADD COLUMN unexpected_required text NOT NULL",
            "columns: missing=[], unexpected=['unexpected_required']",
        ),
    ),
)
def test_incompatible_column_fails_before_any_missing_table_is_created(
    adoption_engine: sa.Engine,
    adoption_schema: str,
    alteration: str,
    property_fragment: str,
) -> None:
    incompatible = INFORMATION_TOPOLOGY_TABLES[1]
    missing = INFORMATION_TOPOLOGY_TABLES[0]
    with adoption_engine.begin() as connection:
        _create(connection, adoption_schema, (incompatible,))
        connection.execute(
            sa.text(
                f'ALTER TABLE "{adoption_schema}".{incompatible.name} {alteration}'
            )
        )

        with pytest.raises(MigrationAdoptionError) as raised:
            adopt_or_create_tables(
                connection,
                _operations(connection),
                (adoption_schema,),
                (missing, incompatible),
            )
        assert f"{adoption_schema}.{incompatible.name}" in str(raised.value)
        assert property_fragment in str(raised.value)
        assert not sa.inspect(connection).has_table(missing.name, schema=adoption_schema)


@pytest.mark.parametrize(
    "replacement",
    (
        "CREATE INDEX uq_information_topology_state_current "
        "ON {qualified} (project_key, module_id, namespace, state_id) "
        "WHERE is_current IS TRUE",
        "CREATE UNIQUE INDEX uq_information_topology_state_current "
        "ON {qualified} (project_key, module_id, namespace, state_id) "
        "WHERE is_current IS FALSE",
    ),
)
def test_wrong_current_index_uniqueness_or_predicate_is_rejected(
    adoption_engine: sa.Engine, adoption_schema: str, replacement: str
) -> None:
    table = INFORMATION_TOPOLOGY_TABLES[0]
    qualified = f'"{adoption_schema}".{table.name}'
    with adoption_engine.begin() as connection:
        _create(connection, adoption_schema, (table,))
        connection.execute(
            sa.text(
                f'DROP INDEX "{adoption_schema}".'
                "uq_information_topology_state_current"
            )
        )
        connection.execute(sa.text(replacement.format(qualified=qualified)))

        with pytest.raises(MigrationAdoptionError) as raised:
            adopt_or_create_tables(
                connection, _operations(connection), (adoption_schema,), (table,)
            )
        message = str(raised.value)
        assert f"{adoption_schema}.{table.name}" in message
        assert "index uq_information_topology_state_current" in message


def test_conflicting_history_rejects_missing_unique_without_partial_repair(
    adoption_engine: sa.Engine, adoption_schema: str
) -> None:
    table = INFORMATION_TOPOLOGY_TABLES[0]
    qualified = f'"{adoption_schema}".{table.name}'
    with adoption_engine.begin() as connection:
        _create(connection, adoption_schema, (table,))
        connection.execute(
            sa.text(
                f"ALTER TABLE {qualified} DROP CONSTRAINT "
                "uq_information_topology_state_revision"
            )
        )
        for state_id in ("conflict-a", "conflict-b"):
            connection.execute(
                sa.text(
                    f"INSERT INTO {qualified} "
                    "(project_key, module_id, namespace, state_id, profile_id, "
                    "profile_version, revision, payload, digest, is_current, deleted) "
                    "VALUES ('migration-test', 'module', 'namespace', 'duplicate', "
                    "'profile', 'v1', 1, '{}'::jsonb, :digest, false, false)"
                ),
                {"digest": (state_id + "d" * 64)[:64]},
            )

        with pytest.raises(MigrationAdoptionError) as raised:
            adopt_or_create_tables(
                connection, _operations(connection), (adoption_schema,), (table,)
            )
        message = str(raised.value)
        assert f"{adoption_schema}.{table.name}" in message
        assert "historical rows conflict" in message
        constraints = {
            item["name"]
            for item in sa.inspect(connection).get_unique_constraints(
                table.name, schema=adoption_schema
            )
        }
        assert "uq_information_topology_state_revision" not in constraints
