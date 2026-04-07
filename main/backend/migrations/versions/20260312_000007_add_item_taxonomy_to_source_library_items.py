"""add item taxonomy fields to source library items

Revision ID: 20260312_000007
Revises: 20260303_000006
Create Date: 2026-03-12 15:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

from migrations.util import table_exists


# revision identifiers, used by Alembic.
revision = "20260312_000007"
down_revision = "20260303_000006"
branch_labels = None
depends_on = None


ITEM_TYPE_VALUES = ("user_defined", "service_aggregated")
MANAGED_BY_VALUES = ("user", "system")


def _quote_ident(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _schemas_with_table(table_name: str) -> list[str]:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT table_schema FROM information_schema.tables "
            "WHERE table_name = :table_name"
        ),
        {"table_name": table_name},
    ).fetchall()
    return [str(schema) for (schema,) in rows if schema]


def _project_schemas() -> list[str]:
    conn = op.get_bind()
    if not table_exists(conn, "projects", schema="public"):
        return []
    rows = conn.execute(sa.text("SELECT schema_name FROM public.projects")).fetchall()
    return [str(schema_name) for (schema_name,) in rows if schema_name]


def _target_source_item_schemas() -> list[str]:
    conn = op.get_bind()
    seen: set[str] = set()
    ordered: list[str] = []
    for schema in _project_schemas() + _schemas_with_table("source_library_items"):
        if schema == "public":
            continue
        if not table_exists(conn, "source_library_items", schema=schema):
            continue
        if schema not in seen:
            seen.add(schema)
            ordered.append(schema)
    return ordered


def _column_exists(schema: str, table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table_name AND column_name = :column_name LIMIT 1"
        ),
        {"schema": schema, "table_name": table_name, "column_name": column_name},
    ).fetchone()
    return row is not None


def _constraint_exists(schema: str, table_name: str, constraint_name: str) -> bool:
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_schema = :schema AND table_name = :table_name AND constraint_name = :constraint_name LIMIT 1"
        ),
        {"schema": schema, "table_name": table_name, "constraint_name": constraint_name},
    ).fetchone()
    return row is not None


def _ensure_columns(schema: str, table_name: str) -> None:
    if not _column_exists(schema, table_name, "item_type"):
        op.add_column(
            table_name,
            sa.Column("item_type", sa.String(length=32), nullable=True),
            schema=schema,
        )
    if not _column_exists(schema, table_name, "managed_by"):
        op.add_column(
            table_name,
            sa.Column("managed_by", sa.String(length=32), nullable=True),
            schema=schema,
        )


def _backfill(schema: str, table_name: str) -> None:
    qualified_table = f"{_quote_ident(schema)}.{_quote_ident(table_name)}"

    op.execute(
        sa.text(
            f"""
            UPDATE {qualified_table}
               SET item_type = 'service_aggregated',
                   managed_by = 'system'
             WHERE item_key LIKE 'handler.cluster.%'
                OR channel_key LIKE 'crawler.%'
                OR item_key = 'url_pool.default'
                OR coalesce(extra->>'stable_handler_cluster', '') = 'true'
                OR coalesce(extra->>'creation_handler', '') LIKE 'handler.%'
                OR coalesce(extra->>'crawler_provider', '') <> ''
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE {qualified_table}
               SET item_type = 'user_defined',
                   managed_by = 'user'
             WHERE coalesce(item_type, '') = ''
                OR coalesce(managed_by, '') = ''
            """
        )
    )


def _enforce_contract(schema: str, table_name: str) -> None:
    item_constraint = f"ck_{table_name}_item_type"
    managed_by_constraint = f"ck_{table_name}_managed_by"

    if not _constraint_exists(schema, table_name, item_constraint):
        op.create_check_constraint(
            item_constraint,
            table_name,
            f"item_type IN {ITEM_TYPE_VALUES}",
            schema=schema,
        )
    if not _constraint_exists(schema, table_name, managed_by_constraint):
        op.create_check_constraint(
            managed_by_constraint,
            table_name,
            f"managed_by IN {MANAGED_BY_VALUES}",
            schema=schema,
        )

    op.alter_column(
        table_name,
        "item_type",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default=sa.text("'user_defined'"),
        schema=schema,
    )
    op.alter_column(
        table_name,
        "managed_by",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default=sa.text("'user'"),
        schema=schema,
    )


def _downgrade_table(schema: str, table_name: str) -> None:
    item_constraint = f"ck_{table_name}_item_type"
    managed_by_constraint = f"ck_{table_name}_managed_by"

    if _constraint_exists(schema, table_name, item_constraint):
        op.drop_constraint(item_constraint, table_name, type_="check", schema=schema)
    if _constraint_exists(schema, table_name, managed_by_constraint):
        op.drop_constraint(managed_by_constraint, table_name, type_="check", schema=schema)

    if _column_exists(schema, table_name, "item_type"):
        op.drop_column(table_name, "item_type", schema=schema)
    if _column_exists(schema, table_name, "managed_by"):
        op.drop_column(table_name, "managed_by", schema=schema)


def upgrade() -> None:
    conn = op.get_bind()

    if table_exists(conn, "shared_source_library_items", schema="public"):
        _ensure_columns("public", "shared_source_library_items")
        _backfill("public", "shared_source_library_items")
        _enforce_contract("public", "shared_source_library_items")

    for schema in _target_source_item_schemas():
        _ensure_columns(schema, "source_library_items")
        _backfill(schema, "source_library_items")
        _enforce_contract(schema, "source_library_items")


def downgrade() -> None:
    for schema in _target_source_item_schemas():
        _downgrade_table(schema, "source_library_items")

    conn = op.get_bind()
    if table_exists(conn, "shared_source_library_items", schema="public"):
        _downgrade_table("public", "shared_source_library_items")
