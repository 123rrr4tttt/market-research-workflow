"""add document temporal fields

Revision ID: 20260303_000007
Revises: 20260303_000006
Create Date: 2026-03-03 18:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "20260303_000007"
down_revision = "20260303_000006"
branch_labels = None
depends_on = None


def _target_schemas(conn) -> list[str]:
    rows = conn.execute(
        sa.text(
            "SELECT DISTINCT table_schema FROM information_schema.tables "
            "WHERE table_name = 'documents'"
        )
    ).fetchall()
    schemas = [str(r[0]) for r in rows if r and r[0]]
    return schemas or ["public"]


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(sa.text(f'ALTER TABLE "{schema}"."documents" ADD COLUMN IF NOT EXISTS source_time TIMESTAMPTZ NULL'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."documents" ADD COLUMN IF NOT EXISTS effective_time TIMESTAMPTZ NULL'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."documents" ADD COLUMN IF NOT EXISTS time_confidence NUMERIC(4, 3) NULL'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."documents" ADD COLUMN IF NOT EXISTS time_provenance VARCHAR(64) NULL'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."documents" ADD COLUMN IF NOT EXISTS source_domain VARCHAR(255) NULL'))


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        op.execute(sa.text(f'ALTER TABLE "{schema}"."documents" DROP COLUMN IF EXISTS source_domain'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."documents" DROP COLUMN IF EXISTS time_provenance'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."documents" DROP COLUMN IF EXISTS time_confidence'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."documents" DROP COLUMN IF EXISTS effective_time'))
        op.execute(sa.text(f'ALTER TABLE "{schema}"."documents" DROP COLUMN IF EXISTS source_time'))
