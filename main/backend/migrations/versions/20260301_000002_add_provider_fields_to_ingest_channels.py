"""add provider fields to ingest channel tables

Revision ID: 20260301_000002
Revises: 20260301_000001
Create Date: 2026-03-01 10:20:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision = "20260301_000002"
down_revision = "20260301_000001"
branch_labels = None
depends_on = None


def _schemas_with_table(table_name: str) -> list[str]:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT table_schema FROM information_schema.tables "
            "WHERE table_name = :t AND table_type = 'BASE TABLE'"
        ),
        {"t": table_name},
    ).fetchall()
    return [str(schema) for (schema,) in rows]


def _has_column(schema: str, table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = :t AND column_name = :c"
        ),
        {"s": schema, "t": table_name, "c": column_name},
    ).fetchone()
    return row is not None


def _add_cols(table_name: str, schema: str) -> None:
    if not _has_column(schema, table_name, "provider_type"):
        op.add_column(
            table_name,
            sa.Column("provider_type", sa.String(length=32), nullable=False, server_default="native"),
            schema=schema,
        )
    if not _has_column(schema, table_name, "provider_config"):
        op.add_column(
            table_name,
            sa.Column("provider_config", pg.JSONB(astext_type=sa.Text()), nullable=True),
            schema=schema,
        )
    if not _has_column(schema, table_name, "execution_policy"):
        op.add_column(
            table_name,
            sa.Column("execution_policy", pg.JSONB(astext_type=sa.Text()), nullable=True),
            schema=schema,
        )


def _drop_cols(table_name: str, schema: str) -> None:
    if _has_column(schema, table_name, "execution_policy"):
        op.drop_column(table_name, "execution_policy", schema=schema)
    if _has_column(schema, table_name, "provider_config"):
        op.drop_column(table_name, "provider_config", schema=schema)
    if _has_column(schema, table_name, "provider_type"):
        op.drop_column(table_name, "provider_type", schema=schema)


def upgrade() -> None:
    for schema in _schemas_with_table("ingest_channels"):
        _add_cols("ingest_channels", schema)
    for schema in _schemas_with_table("shared_ingest_channels"):
        _add_cols("shared_ingest_channels", schema)


def downgrade() -> None:
    for schema in _schemas_with_table("shared_ingest_channels"):
        _drop_cols("shared_ingest_channels", schema)
    for schema in _schemas_with_table("ingest_channels"):
        _drop_cols("ingest_channels", schema)
