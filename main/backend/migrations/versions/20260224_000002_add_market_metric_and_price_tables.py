"""add market metric and price tables

Revision ID: 20260224_000002
Revises: 20260224_000001
Create Date: 2026-02-24 00:10:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


# revision identifiers, used by Alembic.
revision = "20260224_000002"
down_revision = "20260224_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_metric_points",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("metric_key", sa.String(128), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("currency", sa.String(16), nullable=True),
        sa.Column("source_name", sa.String(128), nullable=True),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("extra", pg.JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_metric_key_date_source",
        "market_metric_points",
        ["metric_key", "date", "source_uri"],
    )

    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("source_name", sa.String(128), nullable=True),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("selector_hint", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(16), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("extra", pg.JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_product_name_source",
        "products",
        ["name", "source_uri"],
    )

    op.create_table(
        "price_observations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("price", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(16), nullable=True),
        sa.Column("availability", sa.String(32), nullable=True),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("extra", pg.JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_price_product_captured_at",
        "price_observations",
        ["product_id", "captured_at"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_price_product_captured_at", "price_observations", type_="unique")
    op.drop_table("price_observations")

    op.drop_constraint("uq_product_name_source", "products", type_="unique")
    op.drop_table("products")

    op.drop_constraint("uq_metric_key_date_source", "market_metric_points", type_="unique")
    op.drop_table("market_metric_points")
