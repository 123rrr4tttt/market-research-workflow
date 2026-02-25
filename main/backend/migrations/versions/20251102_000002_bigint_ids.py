"""migrate integer ids to bigint

Revision ID: 20251102_000002
Revises: 20251101_000001
Create Date: 2025-11-02 07:34:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "20251102_000002"
down_revision = "20251101_000001"
branch_labels = None
depends_on = None


PK_TABLES = [
    "sources",
    "documents",
    "market_stats",
    "config_states",
    "embeddings",
    "etl_job_runs",
    "search_history",
]


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    # Drop foreign key temporarily to allow type change
    if _table_exists(inspector, "documents"):
        fks = inspector.get_foreign_keys("documents")
        for fk in fks:
            if fk.get("constrained_columns") == ["source_id"]:
                op.drop_constraint(fk["name"], "documents", type_="foreignkey")
                break

    for table in PK_TABLES:
        if _table_exists(inspector, table):
            op.alter_column(
                table,
                "id",
                existing_type=sa.Integer(),
                type_=sa.BigInteger(),
                postgresql_using="id::bigint",
            )

    if _table_exists(inspector, "documents"):
        op.alter_column(
            "documents",
            "source_id",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            postgresql_using="source_id::bigint",
        )

    if _table_exists(inspector, "embeddings"):
        op.alter_column(
            "embeddings",
            "object_id",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            postgresql_using="object_id::bigint",
        )

    if _table_exists(inspector, "documents") and _table_exists(inspector, "sources"):
        op.create_foreign_key(
            "documents_source_id_fkey",
            "documents",
            "sources",
            ["source_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if _table_exists(inspector, "documents"):
        fks = inspector.get_foreign_keys("documents")
        for fk in fks:
            if fk.get("constrained_columns") == ["source_id"]:
                op.drop_constraint(fk["name"], "documents", type_="foreignkey")
                break

    for table in PK_TABLES:
        if _table_exists(inspector, table):
            op.alter_column(
                table,
                "id",
                existing_type=sa.BigInteger(),
                type_=sa.Integer(),
                postgresql_using="id::integer",
            )

    if _table_exists(inspector, "documents"):
        op.alter_column(
            "documents",
            "source_id",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            postgresql_using="source_id::integer",
        )

    if _table_exists(inspector, "embeddings"):
        op.alter_column(
            "embeddings",
            "object_id",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            postgresql_using="object_id::integer",
        )

    if _table_exists(inspector, "documents") and _table_exists(inspector, "sources"):
        op.create_foreign_key(
            "documents_source_id_fkey",
            "documents",
            "sources",
            ["source_id"],
            ["id"],
            ondelete="SET NULL",
        )

