"""add functorial successor P0-B durable substrate

Revision ID: 20260830_000001
Revises: 20260402_000004
Create Date: 2026-08-30 17:30:00.000000

Production schema authority for these tables belongs to this Alembic
revision.  Application startup must not invoke ``create_all``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic import op

_SNAPSHOT_MODULE_NAME = "_20260830_000001_successor_schema"
_SNAPSHOT_PATH = (
    Path(__file__).with_name("_snapshots")
    / "20260830_000001_successor_schema.py"
)
_SNAPSHOT_SPEC = importlib.util.spec_from_file_location(
    _SNAPSHOT_MODULE_NAME,
    _SNAPSHOT_PATH,
)
if _SNAPSHOT_SPEC is None or _SNAPSHOT_SPEC.loader is None:  # pragma: no cover
    raise ImportError(f"cannot load immutable migration snapshot: {_SNAPSHOT_PATH}")
_SNAPSHOT = importlib.util.module_from_spec(_SNAPSHOT_SPEC)
# ``dataclasses`` resolves postponed annotations through ``sys.modules`` while
# executing the snapshot, so register this exact module before invoking its
# loader.  Replacing a prior test import also prevents stale snapshot reuse.
sys.modules[_SNAPSHOT_MODULE_NAME] = _SNAPSHOT
_SNAPSHOT_SPEC.loader.exec_module(_SNAPSHOT)

PUBLIC_METADATA = _SNAPSHOT.PUBLIC_METADATA
project_tables = _SNAPSHOT.project_tables

revision = "20260830_000001"
down_revision = "20260525_000001"
branch_labels = None
depends_on = None


def _target_project_schemas(conn: sa.Connection) -> tuple[str, ...]:
    """Discover every already-registered or materialized project schema."""

    rows = conn.execute(
        sa.text(
            """
            SELECT DISTINCT schema_name
            FROM (
                SELECT p.schema_name
                FROM public.projects AS p
                WHERE p.schema_name IS NOT NULL
                UNION
                SELECT t.table_schema AS schema_name
                FROM information_schema.tables AS t
                WHERE t.table_name IN (
                    'documents',
                    'writing_documents',
                    'typed_knowledge_objects'
                )
            ) AS candidate
            WHERE schema_name NOT IN ('public', 'pg_catalog', 'information_schema')
            ORDER BY schema_name
            """
        )
    ).fetchall()
    return tuple(str(row[0]) for row in rows if row and row[0])


def _create_tables(conn: sa.Connection, metadata: sa.MetaData) -> None:
    # ``Table.create`` is used only inside this Alembic revision.  There is no
    # runtime create_all path, and sorted order preserves declared FKs.
    for table in metadata.sorted_tables:
        table.create(bind=conn, checkfirst=True)


def _drop_tables(conn: sa.Connection, metadata: sa.MetaData) -> None:
    for table in reversed(metadata.sorted_tables):
        table.drop(bind=conn, checkfirst=True)


def upgrade() -> None:
    conn = op.get_bind()
    _create_tables(conn, PUBLIC_METADATA)

    for schema in _target_project_schemas(conn):
        metadata = sa.MetaData()
        project_tables(metadata, schema)
        _create_tables(conn, metadata)


def downgrade() -> None:
    conn = op.get_bind()

    # Resolve project schemas before dropping the public scope/registry tables.
    for schema in reversed(_target_project_schemas(conn)):
        metadata = sa.MetaData()
        project_tables(metadata, schema)
        _drop_tables(conn, metadata)

    _drop_tables(conn, PUBLIC_METADATA)
