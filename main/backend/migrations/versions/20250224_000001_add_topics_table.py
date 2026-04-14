"""add topics table

Revision ID: 20250224_000001
Revises: 20251107_000001
Create Date: 2025-02-24 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


# revision identifiers, used by Alembic.
revision = "20250224_000001"
down_revision = "20251107_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_name", sa.String(128), nullable=False, unique=True),
        sa.Column("domains", pg.JSONB, nullable=False),
        sa.Column("languages", pg.JSONB, nullable=False),
        sa.Column("keywords_seed", pg.JSONB, nullable=True),
        sa.Column("subreddits", pg.JSONB, nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_topic_topic_name", "topics", ["topic_name"])


def downgrade() -> None:
    op.drop_constraint("uq_topic_topic_name", "topics", type_="unique")
    op.drop_table("topics")
