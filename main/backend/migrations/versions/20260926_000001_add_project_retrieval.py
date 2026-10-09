"""Persist versioned project retrieval methods, previews and runs.

Revision ID: 20260926_000001
Revises: 20260924_000001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.versions._snapshots.adoption_schema_20260924_20260926 import (
    PROJECT_RETRIEVAL_TABLES,
    adopt_or_create_tables,
)

revision = "20260926_000001"
down_revision = "20260924_000001"
branch_labels = None
depends_on = None

_DOWNGRADE_MESSAGE = (
    "20260926_000001 may have adopted pre-existing business tables; "
    "restore the verified database snapshot for code+data rollback"
)


def _schemas(conn: sa.Connection) -> tuple[str, ...]:
    rows = conn.execute(sa.text(
        "SELECT DISTINCT schema_name FROM public.projects WHERE schema_name IS NOT NULL "
        "AND schema_name NOT IN ('public', 'pg_catalog', 'information_schema')"
    )).scalars()
    return tuple(str(row) for row in rows if row)


def upgrade() -> None:
    conn = op.get_bind()
    adopt_or_create_tables(
        conn,
        op,
        _schemas(conn),
        PROJECT_RETRIEVAL_TABLES,
    )


def downgrade() -> None:
    raise RuntimeError(_DOWNGRADE_MESSAGE)
