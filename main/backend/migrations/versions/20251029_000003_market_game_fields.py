from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


# revision identifiers, used by Alembic.
revision = "20251029_000003"
down_revision = "20251029_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_stats", sa.Column("game", sa.String(length=32), nullable=True))
    op.add_column("market_stats", sa.Column("revenue_estimated", sa.Numeric(18, 2), nullable=True))
    op.add_column("market_stats", sa.Column("draw_number", sa.String(length=32), nullable=True))
    op.add_column("market_stats", sa.Column("extra", pg.JSONB(astext_type=sa.Text()), nullable=True))
    # Replace unique constraint on (state, date) -> (state, game, date)
    try:
        op.drop_constraint("uq_market_state_date", "market_stats", type_="unique")
    except Exception:
        pass
    op.create_unique_constraint("uq_market_state_game_date", "market_stats", ["state", "game", "date"]) 


def downgrade() -> None:
    try:
        op.drop_constraint("uq_market_state_game_date", "market_stats", type_="unique")
    except Exception:
        pass
    op.create_unique_constraint("uq_market_state_date", "market_stats", ["state", "date"]) 
    op.drop_column("market_stats", "extra")
    op.drop_column("market_stats", "draw_number")
    op.drop_column("market_stats", "revenue_estimated")
    op.drop_column("market_stats", "game")


