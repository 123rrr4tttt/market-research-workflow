"""db perf indexes and observability baseline

Revision ID: 20260303_000006
Revises: 20260303_000005
Create Date: 2026-03-03 23:22:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "20260303_000006"
down_revision = "20260303_000005"
branch_labels = None
depends_on = None


def _target_schemas(conn) -> list[str]:
    rows = conn.execute(
        sa.text(
            "SELECT DISTINCT table_schema FROM information_schema.tables "
            "WHERE table_name = 'etl_job_runs'"
        )
    ).fetchall()
    schemas = [str(r[0]) for r in rows if r and r[0]]
    return schemas or ["public"]


def _table_exists(conn, schema: str, table_name: str) -> bool:
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = :table LIMIT 1"
        ),
        {"schema": schema, "table": table_name},
    ).fetchone()
    return bool(row)


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        if _table_exists(conn, schema, "etl_job_runs"):
            op.execute(
                sa.text(
                    f'CREATE INDEX IF NOT EXISTS ix_etl_job_runs_status_started_at ON "{schema}"."etl_job_runs" (status, started_at DESC)'
                )
            )
            op.execute(
                sa.text(
                    f'CREATE INDEX IF NOT EXISTS ix_etl_job_runs_external_ref ON "{schema}"."etl_job_runs" (external_provider, external_job_id)'
                )
            )

        if _table_exists(conn, schema, "documents"):
            op.execute(
                sa.text(
                    f'CREATE INDEX IF NOT EXISTS ix_documents_status_publish_date ON "{schema}"."documents" (status, publish_date DESC)'
                )
            )


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{schema}".ix_etl_job_runs_status_started_at'))
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{schema}".ix_etl_job_runs_external_ref'))
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{schema}".ix_documents_status_publish_date'))
