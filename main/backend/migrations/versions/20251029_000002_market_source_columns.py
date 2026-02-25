from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251029_000002"
down_revision = "20251029_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_stats",
        sa.Column("source_name", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "market_stats",
        sa.Column("source_uri", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("market_stats", "source_uri")
    op.drop_column("market_stats", "source_name")


