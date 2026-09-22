from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.successor_runtime.substrate.postgres import (
    PROJECT_TABLE_NAMES,
    PUBLIC_TABLES,
    project_tables,
)

EXPECTED_PROJECT_TABLES = {
    "research_objects",
    "research_relations",
    "research_owner_bindings",
    "research_program_specs",
    "research_execution_plans",
    "successor_values",
    "successor_receipts",
}

EXPECTED_PUBLIC_TABLES = {
    "runtime_program_refs",
    "runtime_plan_refs",
    "project_scope_registry",
    "runtime_runs",
    "runtime_steps",
    "runtime_events",
    "runtime_work_items",
    "runtime_effect_attempts",
    "runtime_values",
    "runtime_staged_artifacts",
    "runtime_qualifications",
    "runtime_step_authorizations",
    "runtime_approvals",
    "runtime_idempotency",
    "runtime_projection_offsets",
    "runtime_authority_grants",
    "runtime_capability_authority",
    "runtime_resource_policies",
    "runtime_resource_reservations",
    "runtime_commit_intents",
    "runtime_nodes",
    "runtime_deployment_catalogs",
}


def _ddl(table: sa.Table) -> str:
    return str(CreateTable(table).compile(dialect=postgresql.dialect()))


def _revision_paths() -> tuple[Path, Path]:
    versions = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    return (
        versions / "20260830_000001_add_successor_runtime_p0b.py",
        versions / "_snapshots" / "20260830_000001_successor_schema.py",
    )


def _load_revision() -> ModuleType:
    revision_path, _ = _revision_paths()
    spec = importlib.util.spec_from_file_location("p0b_revision", revision_path)
    assert spec and spec.loader
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _table_signature(table: sa.Table) -> tuple[str, tuple[str, ...]]:
    table_ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    index_ddl = tuple(
        sorted(
            str(CreateIndex(index).compile(dialect=postgresql.dialect()))
            for index in table.indexes
        )
    )
    return table_ddl, index_ddl


def _p0b_projection_offsets_contract() -> sa.Table:
    """Declare the frozen pre-P0-D offset shape independently of current models."""

    metadata = sa.MetaData(schema="public")
    return sa.Table(
        "runtime_projection_offsets",
        metadata,
        sa.Column("projection_offset_id", sa.String(128), primary_key=True),
        sa.Column("project_key", sa.String(128), nullable=False),
        sa.Column("projector_id", sa.String(128), nullable=False),
        sa.Column("projector_version", sa.String(64), nullable=False),
        sa.Column("source_revision", sa.BigInteger, nullable=False),
        sa.Column("source_digest", sa.CHAR(64), nullable=False),
        sa.Column("offset_ref", sa.Text, nullable=False),
        sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "project_key",
            "projection_offset_id",
            name="uq_projection_scope_id",
        ),
        sa.UniqueConstraint(
            "project_key",
            "projector_id",
            "projector_version",
            name="uq_projection_owner_version",
        ),
        sa.CheckConstraint(
            "source_revision >= 0 AND revision >= 0",
            name="ck_projection_revisions",
        ),
        sa.Index("ix_projection_projector", "project_key", "projector_id"),
    )


def test_project_factory_declares_exact_payload_owners_and_is_idempotent() -> None:
    metadata = sa.MetaData()
    first = project_tables(metadata, "project_contract")
    second = project_tables(metadata, "project_contract")

    assert set(PROJECT_TABLE_NAMES) == EXPECTED_PROJECT_TABLES
    assert set(first.as_dict()) == EXPECTED_PROJECT_TABLES
    assert first == second
    assert all(table.schema == "project_contract" for table in first.as_dict().values())
    assert isinstance(first.successor_values.c.content_bytes.type, sa.LargeBinary)
    assert isinstance(first.research_program_specs.c.spec_json.type, postgresql.JSONB)
    assert isinstance(first.research_execution_plans.c.plan_json.type, postgresql.JSONB)


def test_public_control_plane_has_scope_without_business_payload_bytes() -> None:
    # P0-B owns this baseline inventory. Later additive tables have their exact
    # structure checked by their own revision contract tests, while every
    # current table must continue to satisfy this payload/scope invariant.
    assert EXPECTED_PUBLIC_TABLES <= set(PUBLIC_TABLES)

    global_tables = {"runtime_nodes", "runtime_deployment_catalogs"}
    for name, table in PUBLIC_TABLES.items():
        assert table.schema == "public"
        assert not any(
            isinstance(column.type, sa.LargeBinary) for column in table.columns
        )
        if name in global_tables:
            assert "project_key" not in table.c
            continue
        assert table.c.project_key.nullable is False
        scoped_shape = any(
            "project_key" in tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(
                constraint,
                (sa.PrimaryKeyConstraint, sa.UniqueConstraint, sa.ForeignKeyConstraint),
            )
        )
        scoped_index = any(
            "project_key" in tuple(column.name for column in index.columns)
            for index in table.indexes
        )
        assert scoped_shape or scoped_index, name


def test_frozen_p0b_constraints_compile_for_postgresql() -> None:
    runs = _ddl(PUBLIC_TABLES["runtime_runs"])
    work_items = _ddl(PUBLIC_TABLES["runtime_work_items"])
    events = _ddl(PUBLIC_TABLES["runtime_events"])
    authority = _ddl(PUBLIC_TABLES["runtime_capability_authority"])
    reservations = _ddl(PUBLIC_TABLES["runtime_resource_reservations"])
    policies = _ddl(PUBLIC_TABLES["runtime_resource_policies"])
    idempotency = _ddl(PUBLIC_TABLES["runtime_idempotency"])
    attempts = _ddl(PUBLIC_TABLES["runtime_effect_attempts"])

    assert "next_event_seq" in runs
    assert "ck_run_state_plan_required" in runs
    assert "state = 'COMPILING'" in runs
    assert "plan_id IS NOT NULL AND plan_digest IS NOT NULL" in runs
    assert "GENERATED BY DEFAULT AS IDENTITY" in work_items
    for value in (
        "COMPILE",
        "QUALIFY",
        "INTERPRET",
        "VERIFY_ADMIT",
        "PROJECT",
        "RECONCILE",
        "MATERIALIZE_SUCCESSOR",
    ):
        assert value in work_items
    assert "PRIMARY KEY (run_id, seq)" in events
    assert "ck_cap_auth_single_claim_owner" in authority
    assert "uq_reservation_step_epoch" in reservations
    assert "uq_idem_scope_cap_request" in idempotency
    assert "assignment_digest" in attempts
    assert "handler_binding_digest" in attempts
    assert "claim_binding_digest" in attempts
    assert "delivery_intent_ref" in attempts
    assert "ck_attempt_exact_handler_realization" in attempts
    assert "ck_work_assignment_binding" in work_items
    assert "ck_work_claim_binding" in work_items
    assert "queue_eligibility_digest" in work_items
    assert "assignment_binding_json" in work_items
    assert "execution_epoch" in work_items
    assert "assignment_incarnation" in work_items
    assert "claim_authority_epoch" in work_items
    assert "claim_policy_digest" in work_items
    assert "recovery_handler_binding_digest" in work_items
    assert "recovery_binding_json" in work_items
    assert "provider_key" in reservations
    assert "max_project_active" in policies
    assert "max_capability_active" in policies
    assert "max_resource_active" in policies
    qualifications = _ddl(PUBLIC_TABLES["runtime_qualifications"])
    authorizations = _ddl(PUBLIC_TABLES["runtime_step_authorizations"])
    assert "qualification_binding_json" in qualifications
    assert "qualification_binding_digest" in qualifications
    assert "qualified_plan_json" in qualifications
    for column in (
        "authorization_binding_json",
        "interpreter_binding_digest",
        "deployment_catalog_digest",
        "authority_source_bindings_json",
        "grants_digest",
        "approval_refs_json",
        "resource_ceiling_digest",
        "resource_policy_epoch",
        "queue_eligibility_digest",
        "canonical_base_revision",
        "canonical_incarnation",
    ):
        assert column in authorizations
    scope_indexes = {
        index.name: index for index in PUBLIC_TABLES["project_scope_registry"].indexes
    }
    active_index = scope_indexes["uq_scope_one_active_per_project"]
    assert active_index.unique
    assert "state = 'ACTIVE'" in str(
        active_index.dialect_options["postgresql"]["where"]
    )


def test_composite_foreign_keys_keep_project_scope_on_runtime_edges() -> None:
    for name in (
        "runtime_runs",
        "runtime_steps",
        "runtime_events",
        "runtime_work_items",
        "runtime_effect_attempts",
        "runtime_staged_artifacts",
        "runtime_qualifications",
        "runtime_step_authorizations",
        "runtime_approvals",
        "runtime_resource_reservations",
        "runtime_commit_intents",
    ):
        table = PUBLIC_TABLES[name]
        foreign_keys = [
            constraint
            for constraint in table.constraints
            if isinstance(constraint, sa.ForeignKeyConstraint)
        ]
        assert foreign_keys, name
        assert any(
            "project_key" in tuple(column.name for column in constraint.columns)
            for constraint in foreign_keys
        ), name


def test_alembic_revision_is_self_contained_and_has_explicit_downgrade() -> None:
    revision_path, snapshot_path = _revision_paths()
    for path in (revision_path, snapshot_path):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_modules = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_modules.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        assert not any(
            module == "app" or module.startswith("app.") for module in imported_modules
        ), path.name

    revision = _load_revision()

    assert revision.revision == "20260830_000001"
    # Migration bridge (commit b416c723) added the six donor legacy revisions
    # between 20260402_000004 and 20260525_000001, so the successor P0-B
    # revision must start from the bridged head.
    assert revision.down_revision == "20260525_000001"
    assert callable(revision.upgrade)
    assert callable(revision.downgrade)


def test_alembic_snapshot_is_schema_equivalent_to_frozen_p0b_models() -> None:
    revision = _load_revision()
    snapshot_public = {
        table.name: table for table in revision.PUBLIC_METADATA.sorted_tables
    }
    assert set(snapshot_public) == EXPECTED_PUBLIC_TABLES
    unchanged_p0b_names = EXPECTED_PUBLIC_TABLES - {"runtime_projection_offsets"}
    assert {
        name: _table_signature(snapshot_public[name]) for name in unchanged_p0b_names
    } == {name: _table_signature(PUBLIC_TABLES[name]) for name in unchanged_p0b_names}
    assert _table_signature(snapshot_public["runtime_projection_offsets"]) == (
        _table_signature(_p0b_projection_offsets_contract())
    )

    snapshot_metadata = sa.MetaData()
    snapshot_project = revision.project_tables(
        snapshot_metadata,
        "project_contract",
    ).as_dict()
    application_metadata = sa.MetaData()
    application_project = project_tables(
        application_metadata,
        "project_contract",
    ).as_dict()
    assert set(snapshot_project) == EXPECTED_PROJECT_TABLES
    assert {
        name: _table_signature(table) for name, table in snapshot_project.items()
    } == {name: _table_signature(table) for name, table in application_project.items()}
