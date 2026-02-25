"""add llm_service_configs table

Revision ID: 20251107_000001
Revises: 20251102_000002
Create Date: 2025-11-07 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


# revision identifiers, used by Alembic.
revision = "20251107_000001"
down_revision = "20251102_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_service_configs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("service_name", sa.String(64), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("user_prompt_template", sa.Text(), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("temperature", sa.Numeric(3, 2), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("top_p", sa.Numeric(5, 4), nullable=True),
        sa.Column("presence_penalty", sa.Numeric(5, 4), nullable=True),
        sa.Column("frequency_penalty", sa.Numeric(5, 4), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_llm_service_config_service_name", "llm_service_configs", ["service_name"])


def downgrade() -> None:
    op.drop_constraint("uq_llm_service_config_service_name", "llm_service_configs", type_="unique")
    op.drop_table("llm_service_configs")

