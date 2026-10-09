"""Add revisioned information-topology storage to public and tenant schemas.

Revision ID: 20260924_000001
Revises: 20260905_000001
Create Date: 2026-09-24 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from migrations.versions._snapshots.adoption_schema_20260924_20260926 import (
    INFORMATION_TOPOLOGY_TABLES,
    adopt_or_create_tables,
)

revision = "20260924_000001"
down_revision = "20260905_000001"
branch_labels = None
depends_on = None

_DOWNGRADE_MESSAGE = (
    "20260924_000001 may have adopted pre-existing business tables; "
    "restore the verified database snapshot for code+data rollback"
)


def _project_schemas(conn: sa.Connection) -> tuple[str, ...]:
    if not sa.inspect(conn).has_table("projects", schema="public"):
        return ()
    rows = conn.execute(sa.text(
        "SELECT DISTINCT schema_name FROM public.projects "
        "WHERE schema_name IS NOT NULL AND schema_name NOT IN "
        "('public', 'pg_catalog', 'information_schema') ORDER BY schema_name"
    )).scalars()
    return tuple(str(name) for name in rows if name)


def upgrade() -> None:
    conn = op.get_bind()
    adopt_or_create_tables(
        conn,
        op,
        ("public", *_project_schemas(conn)),
        INFORMATION_TOPOLOGY_TABLES,
    )


def downgrade() -> None:
    raise RuntimeError(_DOWNGRADE_MESSAGE)
