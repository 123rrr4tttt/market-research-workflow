from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "20251029_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(1024), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("state", sa.String(8), nullable=True),
        sa.Column("doc_type", sa.String(16), nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("publish_date", sa.Date, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("text_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("uri", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "market_stats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("state", sa.String(8), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("sales_volume", sa.Numeric(18, 2), nullable=True),
        sa.Column("revenue", sa.Numeric(18, 2), nullable=True),
        sa.Column("jackpot", sa.Numeric(18, 2), nullable=True),
        sa.Column("ticket_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("yoy", sa.Numeric(10, 4), nullable=True),
        sa.Column("mom", sa.Numeric(10, 4), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("state", "date", name="uq_market_state_date"),
    )

    op.create_table(
        "config_states",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("state_name", sa.String(32), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "embeddings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("object_id", sa.Integer, nullable=False),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("modality", sa.String(16), nullable=False),
        sa.Column("vector", Vector(3072), nullable=False),
        sa.Column("dim", sa.Integer, nullable=False, server_default=sa.text("3072")),
        sa.Column("provider", sa.String(32), nullable=False, server_default="openai"),
        sa.Column("model", sa.String(128), nullable=False, server_default="text-embedding-3-large"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Index("ix_embeddings_object", "object_id", "object_type"),
    )

    op.create_table(
        "etl_job_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_type", sa.String(16), nullable=False),
        sa.Column("params", pg.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Index("ix_etl_job_runs_type_status", "job_type", "status"),
    )


def downgrade() -> None:
    op.drop_table("etl_job_runs")
    op.drop_table("embeddings")
    op.drop_table("config_states")
    op.drop_table("market_stats")
    op.drop_table("documents")
    op.drop_table("sources")


