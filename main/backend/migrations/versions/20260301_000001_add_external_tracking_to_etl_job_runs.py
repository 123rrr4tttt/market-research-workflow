"""add external tracking fields to etl_job_runs

Revision ID: 20260301_000001
Revises: 20260228_000001
Create Date: 2026-03-01 09:55:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260301_000001"
down_revision = "20260228_000001"
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


def upgrade() -> None:
    for schema in _schemas_with_table("etl_job_runs"):
        op.add_column(
            "etl_job_runs",
            sa.Column("external_job_id", sa.String(length=255), nullable=True),
            schema=schema,
        )
        op.add_column(
            "etl_job_runs",
            sa.Column("external_provider", sa.String(length=64), nullable=True),
            schema=schema,
        )
        op.add_column(
            "etl_job_runs",
            sa.Column("retry_count", sa.Integer(), nullable=True),
            schema=schema,
        )


def downgrade() -> None:
    for schema in _schemas_with_table("etl_job_runs"):
        op.drop_column("etl_job_runs", "retry_count", schema=schema)
        op.drop_column("etl_job_runs", "external_provider", schema=schema)
        op.drop_column("etl_job_runs", "external_job_id", schema=schema)
