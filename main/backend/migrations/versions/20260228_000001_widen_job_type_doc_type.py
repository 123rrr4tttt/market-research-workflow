"""widen job_type and doc_type for seed compatibility

Revision ID: 20260228_000001
Revises: 20260226_000004
Create Date: 2026-02-28 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "20260228_000001"
down_revision = "20260226_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Alter etl_job_runs.job_type and documents.doc_type in all schemas (public + project_*)
    for table, col in [("etl_job_runs", "job_type"), ("documents", "doc_type")]:
        rows = conn.execute(
            sa.text(
                "SELECT table_schema FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": col},
        ).fetchall()
        for (schema,) in rows:
            op.execute(
                sa.text(
                    f'ALTER TABLE "{schema}"."{table}" '
                    f'ALTER COLUMN "{col}" TYPE VARCHAR(64)'
                )
            )


def downgrade() -> None:
    conn = op.get_bind()
    for table, col in [("etl_job_runs", "job_type"), ("documents", "doc_type")]:
        rows = conn.execute(
            sa.text(
                "SELECT table_schema FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": col},
        ).fetchall()
        for (schema,) in rows:
            op.execute(
                sa.text(
                    f'ALTER TABLE "{schema}"."{table}" '
                    f'ALTER COLUMN "{col}" TYPE VARCHAR(16)'
                )
            )
