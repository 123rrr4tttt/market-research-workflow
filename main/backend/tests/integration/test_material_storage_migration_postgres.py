"""Disposable PostgreSQL witnesses for the Material storage revision."""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from importlib import import_module
import os
from pathlib import Path
from typing import Any
from unittest.mock import Mock

from alembic import command
from alembic.config import Config
from functorial_kit import Failure
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.entities import Material, Source, WorkflowGraphEvent, WorkflowGraphRun
from app.models.information_topology_entities import InformationTopologyState
from app.models.typed_knowledge_entities import TypedKnowledgeObject
from app.services.information_topology.io.retrieval import (
    _digest,
    _source_ref_wire,
    _state_digest,
    build_import_preview,
)
from app.services.information_topology.modules.retrieval import _make_legacy_retrieval_profile
from app.services.information_topology.profiles import validate_state
from app.services.information_topology.repository import InformationTopologyRepository, StateWrite
from app.settings.config import settings
from app.services.projects.bootstrap import (
    ProjectSchemaIncompatibleError,
    TENANT_TABLES,
    ensure_project_schema_ready,
    validate_project_schema,
)
from app.services.projects.schema_initialization import (
    DatabaseRevisionIncompatibleError,
    initialize_default_project_schema,
)


BACKEND_DIR = Path(__file__).resolve().parents[2]
OLD_HEAD = "20260926_000001"
NEW_HEAD = "20261009_000001"
FOLLOWUP_HEAD = "20261009_000002"
CURRENT_HEAD = "20261119_000002"
DSN = "postgresql+psycopg2://postgres@127.0.0.1:50931/material_migration_test"
DSN_ENV = "MATERIAL_MIGRATION_TEST_DATABASE_URL"

pytestmark = pytest.mark.skipif(
    os.environ.get(DSN_ENV, "").strip() != DSN,
    reason="requires the exclusive Material migration PostgreSQL test DSN",
)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _config(dsn: str, *, x: tuple[str, ...] = ()) -> Config:
    # Programmatic migrations use the test runner's logging configuration.
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", dsn)
    config.cmd_opts = Namespace(x=list(x))
    return config


def _with_test_dsn(callable_: Callable[[str], Any]) -> Any:
    assert os.environ[DSN_ENV].strip() == DSN
    original = settings.database_url
    settings.database_url = DSN
    try:
        return callable_(DSN)
    finally:
        settings.database_url = original


def _reset_database(engine) -> None:
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        schemas = (
            conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name NOT IN ('pg_catalog', 'information_schema') "
                    "AND schema_name NOT LIKE 'pg\\_%'"
                )
            )
            .scalars()
            .all()
        )
        for schema in schemas:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {_quote(str(schema))} CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture
def exclusive_engine():
    engine = create_engine(DSN)
    _with_test_dsn(lambda _: _reset_database(engine))
    try:
        yield engine
    finally:
        _with_test_dsn(lambda _: _reset_database(engine))
        engine.dispose()


def _stamp_old_head(dsn: str) -> None:
    command.stamp(_config(dsn), OLD_HEAD)


def _head(engine) -> str:
    with engine.begin() as conn:
        return str(conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one())


def _has_table(engine, schema: str, table: str) -> bool:
    with engine.begin() as conn:
        return (
            conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_schema = :schema AND table_name = :table"),
                {"schema": schema, "table": table},
            ).fetchone()
            is not None
        )


def _install_current_tenant_schema(engine, schema: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {_quote(schema)}"))
        conn.execute(text(f"SET LOCAL search_path TO {_quote(schema)}"))
        schema_conn = conn.execution_options(schema_translate_map={None: schema})
        for table in TENANT_TABLES:
            if table.name == "embeddings":
                continue
            table.create(bind=schema_conn, checkfirst=False)


def _relation_fingerprint(conn, schema: str, table: str) -> tuple[object, ...]:
    qualified = f"{schema}.{table}"
    sequence = conn.execute(
        text("SELECT pg_get_serial_sequence(:qualified, 'id')"),
        {"qualified": qualified},
    ).scalar_one()
    sequence_identity: tuple[object, ...] | None = None
    if sequence:
        sequence_identity = (
            int(conn.execute(text("SELECT to_regclass(:sequence)::oid"), {"sequence": sequence}).scalar_one()),
            *tuple(conn.execute(text(f"SELECT last_value, is_called FROM {sequence}")).one()),
        )
    return (
        int(
            conn.execute(
                text("SELECT to_regclass(:qualified)::oid"),
                {"qualified": qualified},
            ).scalar_one()
        ),
        int(conn.execute(text(f"SELECT count(*) FROM {_quote(schema)}.{_quote(table)}")).scalar_one()),
        str(
            conn.execute(
                text(
                    f"SELECT coalesce(md5(string_agg(row_to_json(row_value)::text, '' ORDER BY row_value.id)), md5('')) "
                    f"FROM {_quote(schema)}.{_quote(table)} AS row_value"
                )
            ).scalar_one()
        ),
        sequence_identity,
    )


def _install_projects_table(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE public.projects (
                    id BIGSERIAL PRIMARY KEY,
                    project_key VARCHAR(64) NOT NULL UNIQUE,
                    name VARCHAR(255) NOT NULL,
                    schema_name VARCHAR(128) NOT NULL UNIQUE,
                    enabled BOOLEAN NOT NULL DEFAULT true,
                    is_active BOOLEAN NOT NULL DEFAULT false
                )
                """
            )
        )


def _register_project(
    engine,
    project_key: str,
    schema: str,
    *,
    enabled: bool = True,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO public.projects "
                "(project_key, name, schema_name, enabled, is_active) "
                "VALUES (:project_key, :project_key, :schema, :enabled, false)"
            ),
            {
                "project_key": project_key,
                "schema": schema,
                "enabled": enabled,
            },
        )


def _storage_digest(
    conn,
    schema: str,
    table: str,
    type_column: str,
    *,
    max_id: int | None = None,
) -> str:
    where = "" if max_id is None else " WHERE row_value.id <= :max_id"
    parameters: dict[str, object] = {
        "source_key": f'"{type_column}"',
        "target_key": '"material_type"',
    }
    if max_id is not None:
        parameters["max_id"] = max_id
    value = conn.execute(
        text(
            "SELECT coalesce(md5(string_agg("
            "replace(row_to_json(row_value)::text, :source_key, :target_key), "
            "'' ORDER BY row_value.id)), md5('')) "
            f"FROM {_quote(schema)}.{_quote(table)} AS row_value{where}"
        ),
        parameters,
    ).scalar_one()
    return str(value)


def _install_legacy_schema(
    engine,
    schema: str,
    *,
    rows: int,
    with_source_fk: bool = True,
) -> dict[str, Any]:
    source_fk = f"REFERENCES {_quote(schema)}.sources(id) ON DELETE SET NULL" if with_source_fk else ""
    with engine.begin() as conn:
        if schema != "public":
            conn.execute(text(f"CREATE SCHEMA {_quote(schema)}"))
        conn.execute(
            text(
                f"""
                CREATE TABLE {_quote(schema)}.sources (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    base_url TEXT,
                    enabled BOOLEAN NOT NULL DEFAULT true,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE {_quote(schema)}.documents (
                    id BIGSERIAL PRIMARY KEY,
                    source_id BIGINT {source_fk},
                    state VARCHAR(8),
                    doc_type VARCHAR(64) NOT NULL,
                    title TEXT,
                    status VARCHAR(32),
                    publish_date DATE,
                    content TEXT,
                    summary TEXT,
                    text_hash VARCHAR(64) UNIQUE,
                    uri TEXT,
                    extracted_data JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    extra_text TEXT NOT NULL DEFAULT '',
                    extra_nullable TEXT,
                    extra_number INTEGER NOT NULL DEFAULT 7,
                    extra_json JSONB,
                    extra_bool BOOLEAN NOT NULL DEFAULT false,
                    CONSTRAINT documents_positive_id CHECK (id > 0)
                );
                CREATE INDEX ix_documents_status_publish_date
                    ON {_quote(schema)}.documents (status, publish_date DESC);
                CREATE TABLE {_quote(schema)}.graph_nodes (
                    id BIGSERIAL PRIMARY KEY,
                    node_type VARCHAR(64) NOT NULL,
                    canonical_id VARCHAR(255) NOT NULL,
                    source_doc_id BIGINT,
                    CONSTRAINT uq_graph_nodes_type_canonical UNIQUE (node_type, canonical_id)
                );
                CREATE INDEX ix_graph_nodes_source_doc_id
                    ON {_quote(schema)}.graph_nodes (source_doc_id);
                CREATE TABLE {_quote(schema)}.writing_documents (
                    id BIGSERIAL PRIMARY KEY,
                    project_key VARCHAR(64) NOT NULL
                );
                CREATE TABLE {_quote(schema)}.writing_document_citations (
                    id BIGSERIAL PRIMARY KEY,
                    doc_id BIGINT NOT NULL
                        REFERENCES {_quote(schema)}.writing_documents(id) ON DELETE CASCADE,
                    project_key VARCHAR(64) NOT NULL,
                    source_doc_id BIGINT,
                    source_uri TEXT
                );
                CREATE INDEX ix_writing_document_citations_source_doc_id
                    ON {_quote(schema)}.writing_document_citations (source_doc_id)
                """
            )
        )
        source_id = int(
            conn.execute(
                text(f"INSERT INTO {_quote(schema)}.sources (name, kind) VALUES (:schema, 'integration') RETURNING id"),
                {"schema": schema},
            ).scalar_one()
        )
        if rows:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {_quote(schema)}.documents
                      (source_id, state, doc_type, title, status, publish_date,
                       content, summary, text_hash, uri, extracted_data,
                       extra_text, extra_nullable, extra_number, extra_json, extra_bool)
                    SELECT :source_id, 'active', 'news', :schema || '-title-' || item,
                           'ok', DATE '2026-01-01', :schema || '-body-' || item,
                           :schema || '-summary-' || item,
                           md5(:schema || '-hash-' || item),
                           'https://example.test/' || :schema || '/' || item,
                           jsonb_build_object('legacy', true, 'item', item),
                           'preserve-' || item, NULL, item, jsonb_build_object('x', item),
                           (item % 2 = 0)
                    FROM generate_series(1, :rows) AS item
                    """
                ),
                {"source_id": source_id, "schema": schema, "rows": rows},
            )
            conn.execute(
                text(
                    f"INSERT INTO {_quote(schema)}.graph_nodes "
                    "(node_type, canonical_id, source_doc_id) VALUES ('Post', '1', 1)"
                )
            )
            writing_id = int(
                conn.execute(
                    text(f"INSERT INTO {_quote(schema)}.writing_documents (project_key) VALUES (:schema) RETURNING id"),
                    {"schema": schema},
                ).scalar_one()
            )
            conn.execute(
                text(
                    f"INSERT INTO {_quote(schema)}.writing_document_citations "
                    "(doc_id, project_key, source_doc_id, source_uri) "
                    "VALUES (:writing_id, :schema, 1, 'https://example.test/citation')"
                ),
                {"writing_id": writing_id, "schema": schema},
            )
        table_oid = int(
            conn.execute(
                text("SELECT to_regclass(:qualified)::oid"),
                {"qualified": f"{schema}.documents"},
            ).scalar_one()
        )
        sequence_oid = int(
            conn.execute(
                text("SELECT to_regclass(:qualified)::oid"),
                {"qualified": f"{schema}.documents_id_seq"},
            ).scalar_one()
        )
        sequence_state = tuple(
            conn.execute(text(f"SELECT last_value, is_called FROM {_quote(schema)}.documents_id_seq")).one()
        )
        columns = tuple(
            conn.execute(
                text(
                    "SELECT column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_schema=:schema AND table_name='documents' "
                    "ORDER BY ordinal_position"
                ),
                {"schema": schema},
            ).all()
        )
        digest = _storage_digest(conn, schema, "documents", "doc_type")
    return {
        "rows": rows,
        "table_oid": table_oid,
        "sequence_oid": sequence_oid,
        "sequence_state": sequence_state,
        "columns": columns,
        "digest": digest,
    }


def _install_source_topology(
    engine,
    schema: str,
    project_key: str,
    uri: str,
    *,
    snapshot_locator: str | None = None,
) -> None:
    from fixtures.information_topology_retrieval import source_bundle, vocabulary

    with engine.begin() as conn:
        conn.execute(text(f"SET LOCAL search_path = {_quote(schema)}, public"))
        InformationTopologyState.__table__.create(conn)
    sessions = sessionmaker(bind=engine, autoflush=False)
    with sessions.begin() as session:
        session.execute(text(f"SET LOCAL search_path = {_quote(schema)}, public"))
        source = source_bundle()
        source["domain_source_ref"]["ref"]["project_key"] = project_key
        source["materials"] = [
            {
                "材料ID": "item:test:1",
                "标题": "first placement",
                "档": "A",
                "URL": uri,
                **({"快照路径": snapshot_locator} if snapshot_locator else {}),
            },
            {
                "材料ID": "item:test:2",
                "标题": "second placement",
                "档": "A",
                "URL": uri,
            },
        ]
        declared_vocabulary = vocabulary(project_key)
        current_source = deepcopy(source)
        for material_id, material in enumerate(current_source["materials"], start=1):
            material["material_id"] = material_id
        preview = build_import_preview(
            project_key=project_key,
            module_id="retrieval",
            namespace="retrieval",
            source=current_source,
            vocabulary=declared_vocabulary,
        )
        assert not isinstance(preview, Failure)
        legacy_profile = _make_legacy_retrieval_profile(declared_vocabulary)
        materials_by_id = {material["材料ID"]: material for material in source["materials"]}
        legacy_elements = []
        for element in preview.state.elements:
            if element.ref.ref.type_id == "domain_vocabulary":
                element = replace(
                    element,
                    ref=replace(element.ref, observed_revision=legacy_profile.version),
                )
            elif element.ref.ref.type_id == "material":
                material = materials_by_id[element.ref.ref.local_id]
                attributes = dict(element.attributes)
                attributes.pop("material_ref", None)
                attributes.pop("placement_title", None)
                attributes["title"] = material["标题"]
                if material.get("URL"):
                    attributes["url"] = material["URL"]
                snapshot_path = material.get("快照路径")
                if snapshot_path:
                    attributes["snapshot_path"] = [snapshot_path]
                element = replace(element, attributes=attributes)
            legacy_elements.append(element)
        legacy_state = replace(
            preview.state,
            profile_version=legacy_profile.version,
            elements=tuple(legacy_elements),
        )
        assert validate_state(legacy_profile, legacy_state) is None
        source_digest = _digest(
            {"source": source, "vocabulary": _source_ref_wire(declared_vocabulary)}
        )
        preview = replace(
            preview,
            state=legacy_state,
            profile=legacy_profile,
            source_digest=source_digest,
            provenance={
                **preview.provenance,
                "source_digest": source_digest,
                "initial_state_digest": _state_digest(legacy_state),
            },
        )
        assert preview.state.profile_version.startswith("1+")
        result = InformationTopologyRepository({}).apply_batch(
            session,
            states=(StateWrite(preview.state_key, preview.state, None, preview.provenance),),
        )
        assert not hasattr(result, "code")


def _source_root(tmp_path: Path, project_key: str) -> tuple[Path, str]:
    root = tmp_path / f"{project_key}=source"
    root.mkdir()
    return root, f"material_source_root={project_key}={root}"


def test_source_root_parser_is_project_exact_and_keeps_equals(tmp_path: Path) -> None:
    migration = import_module("migrations.versions.20261009_000001_unify_material_storage")
    root, argument = _source_root(tmp_path, "owner")
    assert migration._material_source_roots({"owner"}, [argument]) == {"owner": root}
    invalid = (
        ("material_source_root=", "MATERIAL_SOURCE_ROOT_INVALID"),
        ("material_source_root=owner=relative", "MATERIAL_SOURCE_ROOT_NOT_ABSOLUTE"),
        (f"material_source_root=unknown={root}", "MATERIAL_SOURCE_ROOT_UNKNOWN_PROJECT"),
        (f"material_source_root=owner={tmp_path / 'missing'}", "MATERIAL_SOURCE_ROOT_NOT_DIRECTORY"),
    )
    for raw, code in invalid:
        with pytest.raises(RuntimeError, match=code):
            migration._material_source_roots({"owner"}, [raw])
    with pytest.raises(RuntimeError, match="MATERIAL_SOURCE_ROOT_DUPLICATE"):
        migration._material_source_roots({"owner"}, [argument, argument])


def test_required_tenant_table_followup_rejects_model_shape_drift_before_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sqlalchemy as sa

    migration = import_module(
        "migrations.versions.20261009_000002_repair_required_tenant_tables"
    )
    original = next(
        table for table in migration._repair_tables() if table.name == "graph_nodes"
    )
    metadata = sa.MetaData()
    changed = original.to_metadata(metadata)
    changed.columns["node_type"].type = sa.Text()
    connection = Mock()
    monkeypatch.setattr(migration, "_repair_tables", lambda: (changed,))
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)

    with pytest.raises(RuntimeError, match="TENANT_REPAIR_MODEL_SHAPE_DRIFT"):
        migration.upgrade()

    connection.execute.assert_not_called()


def test_old_head_startup_and_cli_fail_before_publishing_material_shadow(
    exclusive_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.projects import bootstrap as bootstrap_module

    def scenario(dsn: str) -> None:
        _stamp_old_head(dsn)
        _install_projects_table(exclusive_engine)
        _register_project(exclusive_engine, "owner", "project_owner")
        before = _install_legacy_schema(exclusive_engine, "project_owner", rows=1)
        monkeypatch.setattr(bootstrap_module, "engine", exclusive_engine)

        with pytest.raises(DatabaseRevisionIncompatibleError):
            initialize_default_project_schema(
                database_engine=exclusive_engine,
                settings_obj=Namespace(env="dev", active_project_key="owner"),
            )
        with pytest.raises(DatabaseRevisionIncompatibleError):
            ensure_project_schema_ready("owner")

        assert _head(exclusive_engine) == OLD_HEAD
        assert _has_table(exclusive_engine, "project_owner", "documents")
        assert not _has_table(exclusive_engine, "project_owner", "materials")
        with exclusive_engine.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM public.projects")).scalar_one() == 1
            assert tuple(
                conn.execute(
                    text("SELECT last_value, is_called FROM project_owner.documents_id_seq")
                ).one()
            ) == before["sequence_state"]

    _with_test_dsn(scenario)


def test_current_head_existing_project_is_validation_only_and_new_project_initializes(
    exclusive_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.projects import bootstrap as bootstrap_module

    def scenario(dsn: str) -> None:
        command.upgrade(_config(dsn), "head")
        monkeypatch.setattr(bootstrap_module, "engine", exclusive_engine)

        created = ensure_project_schema_ready("new_owner", name="New Owner")
        assert created == {
            "project_key": "new_owner",
            "schema_name": "project_new_owner",
        }
        assert _has_table(exclusive_engine, "project_new_owner", "materials")
        assert _has_table(exclusive_engine, "project_new_owner", "typed_knowledge_objects")
        assert not _has_table(exclusive_engine, "project_new_owner", "documents")

        statements: list[str] = []

        def capture(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
            statements.append(str(statement))

        from sqlalchemy import event

        event.listen(exclusive_engine, "before_cursor_execute", capture)
        try:
            assert initialize_default_project_schema(
                database_engine=exclusive_engine,
                settings_obj=Namespace(env="dev", active_project_key="new_owner"),
            )
            assert ensure_project_schema_ready("new_owner") == created
        finally:
            event.remove(exclusive_engine, "before_cursor_execute", capture)

        ddl = [
            statement
            for statement in statements
            if statement.lstrip().upper().startswith(("CREATE ", "ALTER ", "DROP "))
        ]
        assert ddl == []

    _with_test_dsn(scenario)


def test_current_head_missing_material_is_reported_without_repair(
    exclusive_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.projects import bootstrap as bootstrap_module

    def scenario(dsn: str) -> None:
        command.upgrade(_config(dsn), "head")
        monkeypatch.setattr(bootstrap_module, "engine", exclusive_engine)
        ensure_project_schema_ready("broken_owner")
        with exclusive_engine.begin() as conn:
            conn.execute(text("DROP TABLE project_broken_owner.materials"))

        with pytest.raises(ProjectSchemaIncompatibleError, match="materials"):
            ensure_project_schema_ready("broken_owner")

        assert not _has_table(exclusive_engine, "project_broken_owner", "materials")
        with exclusive_engine.begin() as conn:
            assert (
                conn.execute(
                    text(
                        "SELECT schema_name FROM public.projects "
                        "WHERE project_key='broken_owner'"
                    )
                ).scalar_one()
                == "project_broken_owner"
            )

    _with_test_dsn(scenario)


def test_fresh_migration_creates_public_workflow_history(exclusive_engine) -> None:
    def scenario(dsn: str) -> None:
        command.upgrade(_config(dsn), "head")
        assert _head(exclusive_engine) == CURRENT_HEAD
        with exclusive_engine.begin() as conn:
            validate_project_schema(
                conn,
                schema_name="public",
                tables=[WorkflowGraphRun.__table__, WorkflowGraphEvent.__table__],
            )
        for model in (WorkflowGraphRun, WorkflowGraphEvent):
            assert _has_table(exclusive_engine, "public", model.__tablename__)

    _with_test_dsn(scenario)


def test_workflow_history_migration_keeps_preexisting_rows(exclusive_engine, monkeypatch) -> None:
    from app.services.workflow_graph import store

    def scenario(dsn: str) -> None:
        command.upgrade(_config(dsn), FOLLOWUP_HEAD)
        with exclusive_engine.begin() as conn:
            # Older application startup created both tables from ORM metadata.
            WorkflowGraphRun.__table__.create(conn)
            WorkflowGraphEvent.__table__.create(conn)
            conn.execute(WorkflowGraphRun.__table__.insert().values(run_id="saved-run", status="succeeded"))
            conn.execute(
                WorkflowGraphEvent.__table__.insert(),
                [
                    {"run_id": "saved-run", "seq": 2, "event_type": "run_completed"},
                    {"run_id": "saved-run", "seq": 1, "event_type": "run_started"},
                ],
            )
            before = tuple(
                _relation_fingerprint(conn, "public", table.__tablename__)
                for table in (WorkflowGraphRun, WorkflowGraphEvent)
            )

        command.upgrade(_config(dsn), "head")
        assert _head(exclusive_engine) == CURRENT_HEAD
        with exclusive_engine.begin() as conn:
            assert before == tuple(
                _relation_fingerprint(conn, "public", table.__tablename__)
                for table in (WorkflowGraphRun, WorkflowGraphEvent)
            )
        monkeypatch.setattr(store, "engine", exclusive_engine)
        snapshot = store.SqlHistoricalWorkflowRunReader().snapshot("saved-run")
        assert snapshot["run"]["status"] == "succeeded"
        assert [event["seq"] for event in snapshot["events"]] == [1, 2]

    _with_test_dsn(scenario)


def test_workflow_history_migration_rejects_relation_conflict_without_partial_creation(exclusive_engine) -> None:
    def scenario(dsn: str) -> None:
        command.upgrade(_config(dsn), FOLLOWUP_HEAD)
        with exclusive_engine.begin() as conn:
            conn.execute(text("CREATE VIEW public.workflow_graph_events AS SELECT 1"))

        with pytest.raises(RuntimeError, match="WORKFLOW_HISTORY_RELATION_CONFLICT"):
            command.upgrade(_config(dsn), "head")

        assert _head(exclusive_engine) == FOLLOWUP_HEAD
        assert not _has_table(exclusive_engine, "public", "workflow_graph_runs")

    _with_test_dsn(scenario)


def test_typed_knowledge_repair_preserves_existing_and_limits_target_schemas(exclusive_engine) -> None:
    def scenario(dsn: str) -> None:
        # Replaying the prior required-table repair must not treat a gap that
        # belongs to this new revision as a failure in the earlier revision.
        command.upgrade(_config(dsn), NEW_HEAD)
        for key, schema, enabled in (
            ("existing", "project_kept", True),
            ("missing", "project_missing", True),
            ("archived", "project_archived", False),
        ):
            _install_current_tenant_schema(exclusive_engine, schema)
            _register_project(exclusive_engine, key, schema, enabled=enabled)
        table = TypedKnowledgeObject.__tablename__
        with exclusive_engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA project_unregistered"))
            for schema in ("project_missing", "project_archived"):
                conn.execute(text(f"DROP TABLE {schema}.{table}"))
            conn.execute(
                text(
                    f"INSERT INTO project_kept.{table} "
                    "(project_key, object_type, object_key, identity_ref, visibility_scope, lifecycle_state, review_state) "
                    "VALUES ('existing', 'concept', 'sample', 'knowledge:existing:sample', 'project', 'active', 'pending')"
                )
            )
            before = _relation_fingerprint(conn, "project_kept", table)

        command.upgrade(_config(dsn), "head")
        assert _head(exclusive_engine) == CURRENT_HEAD
        for schema in ("project_missing", "project_archived"):
            assert _has_table(exclusive_engine, schema, table)
        assert not _has_table(exclusive_engine, "project_unregistered", table)
        with exclusive_engine.begin() as conn:
            assert _relation_fingerprint(conn, "project_kept", table) == before

    _with_test_dsn(scenario)


def test_typed_knowledge_repair_rejects_relation_conflict_without_partial_creation(exclusive_engine) -> None:
    def scenario(dsn: str) -> None:
        command.upgrade(_config(dsn), "20261119_000001")
        for schema in ("project_gap", "project_view"):
            _install_current_tenant_schema(exclusive_engine, schema)
            _register_project(exclusive_engine, schema, schema)
        with exclusive_engine.begin() as conn:
            conn.execute(text("DROP TABLE project_gap.typed_knowledge_objects, project_view.typed_knowledge_objects"))
            conn.execute(text("CREATE VIEW project_view.typed_knowledge_objects AS SELECT 1"))

        with pytest.raises(RuntimeError, match="TYPED_KNOWLEDGE_REPAIR_RELATION_CONFLICT"):
            command.upgrade(_config(dsn), "head")

        assert _head(exclusive_engine) == "20261119_000001"
        assert not _has_table(exclusive_engine, "project_gap", "typed_knowledge_objects")

    _with_test_dsn(scenario)


def test_required_tenant_table_followup_repairs_only_missing_tables(
    exclusive_engine,
) -> None:
    def scenario(dsn: str) -> None:
        command.upgrade(_config(dsn), NEW_HEAD)
        schemas = {
            "alpha": "project_followup_alpha",
            "beta": "project_followup_beta",
            "gamma": "project_followup_gamma",
        }
        for project_key, schema in schemas.items():
            _install_current_tenant_schema(exclusive_engine, schema)
            _register_project(exclusive_engine, project_key, schema)

        with exclusive_engine.begin() as conn:
            alpha = schemas["alpha"]
            beta = schemas["beta"]
            gamma = schemas["gamma"]
            conn.execute(
                text(
                    f"INSERT INTO {_quote(alpha)}.materials "
                    "(material_type, title, content) VALUES ('report', 'kept', 'material-body')"
                )
            )
            conn.execute(
                text(
                    f"INSERT INTO {_quote(alpha)}.graph_nodes "
                    "(node_type, canonical_id, display_name, source_material_id) "
                    "VALUES ('entity', 'kept-node', 'Kept node', 1)"
                )
            )
            conn.execute(
                text(
                    f"INSERT INTO {_quote(alpha)}.graph_node_aliases "
                    "(node_id, alias_text, alias_norm) VALUES (1, 'Kept', 'kept')"
                )
            )
            conn.execute(
                text(
                    f"INSERT INTO {_quote(alpha)}.graph_edges "
                    "(edge_type, from_node_id, to_node_id) VALUES ('self', 1, 1)"
                )
            )
            conn.execute(text(f"DROP TABLE {_quote(alpha)}.ingest_submission_registry"))
            conn.execute(
                text(
                    f"DROP TABLE {_quote(beta)}.graph_edges, "
                    f"{_quote(beta)}.graph_node_aliases, {_quote(beta)}.graph_nodes"
                )
            )
            conn.execute(
                text(
                    f"DROP TABLE {_quote(gamma)}.ingest_submission_registry, "
                    f"{_quote(gamma)}.resource_pool_site_entries"
                )
            )
            before = {
                (alpha, "materials"): _relation_fingerprint(conn, alpha, "materials"),
                (alpha, "graph_nodes"): _relation_fingerprint(conn, alpha, "graph_nodes"),
                (alpha, "graph_node_aliases"): _relation_fingerprint(conn, alpha, "graph_node_aliases"),
                (alpha, "graph_edges"): _relation_fingerprint(conn, alpha, "graph_edges"),
                (beta, "materials"): _relation_fingerprint(conn, beta, "materials"),
            }

        command.upgrade(_config(dsn), FOLLOWUP_HEAD)
        assert _head(exclusive_engine) == FOLLOWUP_HEAD

        for schema in schemas.values():
            for table_name in (
                "graph_nodes",
                "graph_node_aliases",
                "graph_edges",
                "ingest_submission_registry",
                "resource_pool_site_entries",
            ):
                assert _has_table(exclusive_engine, schema, table_name)

        with exclusive_engine.begin() as conn:
            after = {
                key: _relation_fingerprint(conn, *key)
                for key in before
            }
            assert after == before
            assert conn.execute(
                text(
                    "SELECT count(*) FROM pg_constraint AS c "
                    "JOIN pg_class AS source_table ON source_table.oid=c.conrelid "
                    "JOIN pg_namespace AS source_ns ON source_ns.oid=source_table.relnamespace "
                    "JOIN pg_class AS target_table ON target_table.oid=c.confrelid "
                    "JOIN pg_namespace AS target_ns ON target_ns.oid=target_table.relnamespace "
                    "WHERE c.contype='f' AND source_ns.nspname=:schema "
                    "AND target_ns.nspname=:schema "
                    "AND source_table.relname IN ('graph_node_aliases', 'graph_edges') "
                    "AND target_table.relname='graph_nodes'"
                ),
                {"schema": schemas["beta"]},
            ).scalar_one() == 3

    _with_test_dsn(scenario)


def test_required_tenant_table_followup_is_tenant_ddl_noop_when_complete(
    exclusive_engine,
) -> None:
    def scenario(dsn: str) -> None:
        command.upgrade(_config(dsn), NEW_HEAD)
        schema = "project_followup_complete"
        _install_current_tenant_schema(exclusive_engine, schema)
        _register_project(exclusive_engine, "complete", schema)
        statements: list[str] = []

        def capture(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
            statements.append(str(statement))

        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        event.listen(Engine, "before_cursor_execute", capture)
        try:
            command.upgrade(_config(dsn), FOLLOWUP_HEAD)
        finally:
            event.remove(Engine, "before_cursor_execute", capture)

        assert _head(exclusive_engine) == FOLLOWUP_HEAD
        assert any(
            "SELECT project_key, schema_name FROM public.projects" in statement
            for statement in statements
        )
        assert any(
            statement.lstrip().upper().startswith("UPDATE")
            and "alembic_version" in statement
            for statement in statements
        )
        tenant_ddl = [
            statement
            for statement in statements
            if schema in statement
            and statement.lstrip().upper().startswith(("CREATE ", "ALTER ", "DROP "))
        ]
        assert tenant_ddl == []

    _with_test_dsn(scenario)


def test_required_tenant_table_followup_conflict_rolls_back_all_schemas(
    exclusive_engine,
) -> None:
    def scenario(dsn: str) -> None:
        command.upgrade(_config(dsn), NEW_HEAD)
        first_schema = "project_followup_a_first"
        conflict_schema = "project_followup_b_conflict"
        for project_key, schema in (
            ("a_first", first_schema),
            ("b_conflict", conflict_schema),
        ):
            _install_current_tenant_schema(exclusive_engine, schema)
            _register_project(exclusive_engine, project_key, schema)
        with exclusive_engine.begin() as conn:
            conn.execute(text(f"DROP TABLE {_quote(first_schema)}.ingest_submission_registry"))
            conn.execute(
                text(
                    f"DROP TABLE {_quote(conflict_schema)}.graph_edges, "
                    f"{_quote(conflict_schema)}.graph_node_aliases, "
                    f"{_quote(conflict_schema)}.graph_nodes"
                )
            )
            conn.execute(
                text(
                    f"CREATE TABLE {_quote(conflict_schema)}.graph_nodes "
                    "(id BIGINT PRIMARY KEY)"
                )
            )

        with pytest.raises(RuntimeError, match="TENANT_REPAIR_COLUMN_CONFLICT"):
            command.upgrade(_config(dsn), FOLLOWUP_HEAD)

        assert _head(exclusive_engine) == NEW_HEAD
        assert not _has_table(
            exclusive_engine,
            first_schema,
            "ingest_submission_registry",
        )
        assert not _has_table(exclusive_engine, conflict_schema, "graph_node_aliases")
        assert not _has_table(exclusive_engine, conflict_schema, "graph_edges")

    _with_test_dsn(scenario)


def test_each_schema_uses_an_isolated_session_for_equal_primary_keys(exclusive_engine) -> None:
    def scenario(dsn: str) -> None:
        _stamp_old_head(dsn)
        _install_projects_table(exclusive_engine)
        expected_uris = {
            "project_a_owner": "https://example.test/a-material",
            "project_b_owner": "https://example.test/b-material",
        }
        for project_key, schema in (
            ("a_owner", "project_a_owner"),
            ("b_owner", "project_b_owner"),
        ):
            _register_project(exclusive_engine, project_key, schema)
            _install_legacy_schema(exclusive_engine, schema, rows=1)
            _install_source_topology(
                exclusive_engine,
                schema,
                project_key,
                expected_uris[schema],
            )

        command.upgrade(_config(dsn), NEW_HEAD)
        assert _head(exclusive_engine) == NEW_HEAD
        for project_key, schema in (
            ("a_owner", "project_a_owner"),
            ("b_owner", "project_b_owner"),
        ):
            with exclusive_engine.begin() as conn:
                current = conn.execute(
                    text(
                        f"SELECT project_key, revision, payload FROM "
                        f"{_quote(schema)}.information_topology_states WHERE is_current"
                    )
                ).one()
                assert current.project_key == project_key
                assert current.revision == 2
                refs = {
                    element["attributes"]["material_ref"]["local_id"]
                    for element in current.payload["elements"]
                    if element["ref"]["ref"]["type_id"] == "material"
                }
                assert refs == {"2"}
                assert (
                    conn.execute(text(f"SELECT uri FROM {_quote(schema)}.materials WHERE id=2")).scalar_one()
                    == expected_uris[schema]
                )

    _with_test_dsn(scenario)


def test_topology_schema_without_materials_does_not_fall_back_to_public(
    exclusive_engine,
) -> None:
    def scenario(dsn: str) -> None:
        _stamp_old_head(dsn)
        _install_projects_table(exclusive_engine)
        _install_legacy_schema(exclusive_engine, "public", rows=1)
        schema = "project_missing_owner"
        project_key = "missing_owner"
        with exclusive_engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA {_quote(schema)}"))
        _register_project(exclusive_engine, project_key, schema)
        _install_source_topology(
            exclusive_engine,
            schema,
            project_key,
            "https://example.test/must-not-land-in-public",
        )

        with pytest.raises(RuntimeError) as error:
            command.upgrade(_config(dsn), NEW_HEAD)
        failure_text = str(error.value)
        assert "MATERIAL_TOPOLOGY_MATERIAL_TABLE_MISSING" in failure_text
        assert schema in failure_text
        assert project_key in failure_text
        assert _head(exclusive_engine) == OLD_HEAD
        assert _has_table(exclusive_engine, "public", "documents")
        assert not _has_table(exclusive_engine, "public", "materials")
        assert not _has_table(exclusive_engine, schema, "documents")
        assert not _has_table(exclusive_engine, schema, "materials")
        with exclusive_engine.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM public.documents")).scalar_one() == 1
            assert (
                conn.execute(
                    text(f"SELECT max(revision) FROM {_quote(schema)}.information_topology_states")
                ).scalar_one()
                == 1
            )

    _with_test_dsn(scenario)


def test_upgrade_preserves_229_rows_and_all_storage_objects(
    exclusive_engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def scenario(dsn: str) -> None:
        _stamp_old_head(dsn)
        _install_projects_table(exclusive_engine)
        snapshots: dict[str, dict[str, Any]] = {}
        row_counts = (18, *(13 for _ in range(12)))
        for index, count in enumerate(row_counts):
            project_key = f"owner_{index:02d}"
            schema = f"project_owner_{index:02d}"
            _register_project(
                exclusive_engine,
                project_key,
                schema,
                enabled=index % 2 == 0,
            )
            snapshots[schema] = _install_legacy_schema(
                exclusive_engine,
                schema,
                rows=count,
                with_source_fk=True,
            )
        snapshots["project_default"] = _install_legacy_schema(
            exclusive_engine,
            "project_default",
            rows=55,
            with_source_fk=False,
        )
        assert len(snapshots) == 14
        assert sum(snapshot["rows"] for snapshot in snapshots.values()) == 229
        assert len({snapshot["sequence_oid"] for snapshot in snapshots.values()}) == 14

        topology_schema = "project_owner_00"
        root, x_argument = _source_root(tmp_path, "owner_00")
        (root / "note.md").write_bytes(b"local material\n")
        _install_source_topology(
            exclusive_engine,
            topology_schema,
            "owner_00",
            "https://example.test/shared-topology-material",
            snapshot_locator="note.md",
        )
        with exclusive_engine.begin() as conn:
            old_history = conn.execute(
                text(
                    f"SELECT revision, payload::text, provenance::text, digest "
                    f"FROM {_quote(topology_schema)}.information_topology_states"
                )
            ).one()

        from app.services.information_topology.service import InformationTopologyService

        observed: dict[str, Path | None] = {}
        original = InformationTopologyService.merge_materials_in_session

        def observing_merge(self, session, project_key, *, source_root=None):
            observed[project_key] = source_root
            return original(
                self,
                session,
                project_key,
                source_root=source_root,
            )

        monkeypatch.setattr(
            InformationTopologyService,
            "merge_materials_in_session",
            observing_merge,
        )
        command.upgrade(_config(dsn, x=(x_argument,)), NEW_HEAD)
        assert _head(exclusive_engine) == NEW_HEAD
        assert observed == {"owner_00": root}
        assert not _has_table(exclusive_engine, "public", "documents")
        assert not _has_table(exclusive_engine, "public", "materials")

        for schema, snapshot in snapshots.items():
            assert not _has_table(exclusive_engine, schema, "documents")
            assert _has_table(exclusive_engine, schema, "materials")
            with exclusive_engine.begin() as conn:
                assert (
                    int(
                        conn.execute(
                            text("SELECT to_regclass(:qualified)::oid"),
                            {"qualified": f"{schema}.materials"},
                        ).scalar_one()
                    )
                    == snapshot["table_oid"]
                )
                assert (
                    int(
                        conn.execute(
                            text("SELECT to_regclass(:qualified)::oid"),
                            {"qualified": f"{schema}.materials_id_seq"},
                        ).scalar_one()
                    )
                    == snapshot["sequence_oid"]
                )
                sequence_state = tuple(
                    conn.execute(text(f"SELECT last_value, is_called FROM {_quote(schema)}.materials_id_seq")).one()
                )
                if schema == topology_schema:
                    assert sequence_state == (
                        snapshot["sequence_state"][0] + 1,
                        snapshot["sequence_state"][1],
                    )
                else:
                    assert sequence_state == snapshot["sequence_state"]
                assert (
                    _storage_digest(
                        conn,
                        schema,
                        "materials",
                        "material_type",
                        max_id=snapshot["rows"],
                    )
                    == snapshot["digest"]
                )
                columns = tuple(
                    conn.execute(
                        text(
                            "SELECT column_name, is_nullable FROM information_schema.columns "
                            "WHERE table_schema=:schema AND table_name='materials' "
                            "ORDER BY ordinal_position"
                        ),
                        {"schema": schema},
                    ).all()
                )
                expected_columns = tuple(
                    ("material_type", nullable) if name == "doc_type" else (name, nullable)
                    for name, nullable in snapshot["columns"]
                )
                assert columns == expected_columns
                assert {
                    "extra_text",
                    "extra_nullable",
                    "extra_number",
                    "extra_json",
                    "extra_bool",
                }.issubset({name for name, _ in columns})
                assert (
                    conn.execute(
                        text(
                            "SELECT count(*) FROM pg_constraint c "
                            "JOIN pg_class t ON t.oid=c.conrelid "
                            "JOIN pg_namespace n ON n.oid=t.relnamespace "
                            "WHERE n.nspname=:schema AND t.relname='materials' "
                            "AND c.contype IN ('p','u')"
                        ),
                        {"schema": schema},
                    ).scalar_one()
                    == 2
                )
                index_names = set(
                    conn.execute(
                        text("SELECT indexname FROM pg_indexes WHERE schemaname=:schema AND tablename='materials'"),
                        {"schema": schema},
                    ).scalars()
                )
                assert {
                    "materials_pkey",
                    "materials_text_hash_key",
                    "ix_materials_status_publish_date",
                }.issubset(index_names)
                if snapshot["rows"]:
                    assert (
                        conn.execute(text(f"SELECT source_material_id FROM {_quote(schema)}.graph_nodes")).scalar_one()
                        == 1
                    )
                    assert (
                        conn.execute(
                            text(f"SELECT source_material_id FROM {_quote(schema)}.writing_document_citations")
                        ).scalar_one()
                        == 1
                    )

        with exclusive_engine.begin() as conn:
            assert (
                conn.execute(
                    text(
                        "SELECT count(*) FROM pg_constraint c "
                        "JOIN pg_class source_table ON source_table.oid=c.confrelid "
                        "JOIN pg_namespace source_ns ON source_ns.oid=source_table.relnamespace "
                        "WHERE c.contype='f' AND source_table.relname='sources' "
                        "AND source_ns.nspname LIKE 'project_owner_%'"
                    )
                ).scalar_one()
                == 13
            )
            current = conn.execute(
                text(
                    f"SELECT revision, profile_version, payload "
                    f"FROM {_quote(topology_schema)}.information_topology_states "
                    "WHERE is_current"
                )
            ).one()
            history = conn.execute(
                text(
                    f"SELECT revision, payload::text, provenance::text, digest "
                    f"FROM {_quote(topology_schema)}.information_topology_states "
                    "WHERE revision=1"
                )
            ).one()
            assert history == old_history
            assert current.revision == 2
            assert current.profile_version.startswith("3+")
            refs = [
                element["attributes"]["material_ref"]["local_id"]
                for element in current.payload["elements"]
                if element["ref"]["ref"]["type_id"] == "material"
            ]
            assert len(refs) == 2 and len(set(refs)) == 1
            assert (
                conn.execute(text(f"SELECT count(*) FROM {_quote(topology_schema)}.materials")).scalar_one()
                == snapshots[topology_schema]["rows"] + 1
            )
            assert conn.execute(
                text(
                    f"SELECT content, status FROM {_quote(topology_schema)}.materials "
                    "WHERE uri='https://example.test/shared-topology-material'"
                )
            ).one() == ("local material", "active")

        command.upgrade(_config(dsn, x=(x_argument,)), NEW_HEAD)
        assert _head(exclusive_engine) == NEW_HEAD
        with exclusive_engine.begin() as conn:
            assert (
                conn.execute(
                    text(f"SELECT max(revision) FROM {_quote(topology_schema)}.information_topology_states")
                ).scalar_one()
                == 2
            )
            conn.execute(text('CREATE SCHEMA "project_new_owner"'))
            conn.execute(text('SET LOCAL search_path = "project_new_owner", public'))
            Source.__table__.create(conn)
            Material.__table__.create(conn)
        assert _has_table(exclusive_engine, "project_new_owner", "materials")
        assert not _has_table(exclusive_engine, "project_new_owner", "documents")

    _with_test_dsn(scenario)


def test_failure_in_second_schema_rolls_back_first_schema_and_head(
    exclusive_engine,
    tmp_path: Path,
) -> None:
    def scenario(dsn: str) -> None:
        _stamp_old_head(dsn)
        _install_projects_table(exclusive_engine)
        for project_key, schema in (
            ("a_owner", "project_a_owner"),
            ("b_owner", "project_b_owner"),
        ):
            _register_project(exclusive_engine, project_key, schema)
            _install_legacy_schema(exclusive_engine, schema, rows=2)
            _install_source_topology(
                exclusive_engine,
                schema,
                project_key,
                "https://example.test/schema-shared",
                snapshot_locator=("snapshots/local-material.txt" if project_key == "b_owner" else None),
            )
        _, a_x = _source_root(tmp_path, "a_owner")
        with pytest.raises(RuntimeError) as error:
            command.upgrade(_config(dsn, x=(a_x,)), NEW_HEAD)
        failure_text = str(error.value)
        assert "MATERIAL_TOPOLOGY_MIGRATION_FAILED" in failure_text
        assert "project_b_owner" in failure_text
        assert "b_owner" in failure_text
        assert "source_root_required" in failure_text
        assert _head(exclusive_engine) == OLD_HEAD
        for schema in ("project_a_owner", "project_b_owner"):
            assert _has_table(exclusive_engine, schema, "documents")
            assert not _has_table(exclusive_engine, schema, "materials")
            with exclusive_engine.begin() as conn:
                assert (
                    conn.execute(
                        text(f"SELECT max(revision) FROM {_quote(schema)}.information_topology_states")
                    ).scalar_one()
                    == 1
                )
                assert conn.execute(text(f"SELECT count(*) FROM {_quote(schema)}.documents")).scalar_one() == 2

    _with_test_dsn(scenario)


def test_preexisting_material_table_conflict_has_no_partial_rename(exclusive_engine) -> None:
    def scenario(dsn: str) -> None:
        _stamp_old_head(dsn)
        _install_projects_table(exclusive_engine)
        for project_key, schema in (
            ("a_owner", "project_a_owner"),
            ("b_owner", "project_b_owner"),
        ):
            _register_project(exclusive_engine, project_key, schema)
            _install_legacy_schema(exclusive_engine, schema, rows=1)
        with exclusive_engine.begin() as conn:
            conn.execute(text("CREATE TABLE project_b_owner.materials (id BIGINT PRIMARY KEY)"))
        with pytest.raises(RuntimeError, match="MATERIAL_TABLE_CONFLICT"):
            command.upgrade(_config(dsn), NEW_HEAD)
        assert _head(exclusive_engine) == OLD_HEAD
        for schema in ("project_a_owner", "project_b_owner"):
            assert _has_table(exclusive_engine, schema, "documents")
        with exclusive_engine.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM project_a_owner.documents")).scalar_one() == 1

    _with_test_dsn(scenario)


def test_downgrade_reverses_storage_only_and_retains_material_history(
    exclusive_engine,
    tmp_path: Path,
) -> None:
    def scenario(dsn: str) -> None:
        _stamp_old_head(dsn)
        _install_projects_table(exclusive_engine)
        _install_legacy_schema(exclusive_engine, "public", rows=1)
        _register_project(exclusive_engine, "topology_owner", "project_topology_owner")
        tenant_snapshot = _install_legacy_schema(
            exclusive_engine,
            "project_topology_owner",
            rows=1,
        )
        _install_source_topology(
            exclusive_engine,
            "project_topology_owner",
            "topology_owner",
            "https://example.test/downgrade-material",
        )
        _, x_argument = _source_root(tmp_path, "topology_owner")
        command.upgrade(_config(dsn, x=(x_argument,)), NEW_HEAD)
        command.downgrade(_config(dsn), OLD_HEAD)
        assert _head(exclusive_engine) == OLD_HEAD
        assert _has_table(exclusive_engine, "public", "documents")
        assert not _has_table(exclusive_engine, "public", "materials")
        assert _has_table(exclusive_engine, "project_topology_owner", "documents")
        assert not _has_table(exclusive_engine, "project_topology_owner", "materials")
        with exclusive_engine.begin() as conn:
            assert (
                int(conn.execute(text("SELECT 'project_topology_owner.documents'::regclass::oid")).scalar_one())
                == tenant_snapshot["table_oid"]
            )
            current = conn.execute(
                text(
                    "SELECT revision, profile_version FROM "
                    "project_topology_owner.information_topology_states WHERE is_current"
                )
            ).one()
            assert current.revision == 2
            assert current.profile_version.startswith("3+")

    _with_test_dsn(scenario)


def test_bundled_demo_loads_a_connected_research_project(exclusive_engine, monkeypatch) -> None:
    from app.api import projects
    from app.services.projects import bootstrap

    monkeypatch.setattr(settings, "database_url", DSN)
    monkeypatch.setattr(settings, "project_schema_prefix", "project_")
    monkeypatch.setattr(bootstrap, "engine", exclusive_engine)
    monkeypatch.setattr(projects, "engine", exclusive_engine)
    command.upgrade(_config(DSN), "head")
    projects._bootstrap_demo_seed_if_needed("demo_proj")

    with exclusive_engine.begin() as conn:
        conn.execute(text("SET LOCAL search_path TO project_demo_proj, pg_catalog"))
        # Optional references may be NULL; every supplied reference must resolve.
        for child, column, parent in (
            ("materials", "source_id", "sources"),
            ("graph_nodes", "source_material_id", "materials"),
            ("graph_node_aliases", "node_id", "graph_nodes"),
            ("graph_edges", "from_node_id", "graph_nodes"),
            ("graph_edges", "to_node_id", "graph_nodes"),
            ("writing_document_citations", "doc_id", "writing_documents"),
            ("writing_document_citations", "source_material_id", "materials"),
        ):
            linked, dangling = conn.execute(
                text(
                    f"SELECT count(p.id), count(*) FILTER (WHERE p.id IS NULL) "
                    f"FROM {child} c LEFT JOIN {parent} p ON p.id = c.{column} "
                    f"WHERE c.{column} IS NOT NULL"
                )
            ).one()
            assert linked > 0 and dangling == 0, (child, column, parent, linked, dangling)
