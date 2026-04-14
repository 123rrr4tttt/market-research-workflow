from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


# revision identifiers, used by Alembic.
revision = "20251101_000001"
down_revision = "20251029_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建搜索历史表（如果不存在）
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    
    if "search_history" not in tables:
        op.create_table(
            "search_history",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("topic", sa.String(255), nullable=False),
            sa.Column("last_search_time", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_unique_constraint("uq_search_history_topic", "search_history", ["topic"])
    else:
        # 表已存在，只检查约束
        try:
            op.create_unique_constraint("uq_search_history_topic", "search_history", ["topic"])
        except Exception:
            pass  # 约束可能已存在
    
    # 添加extracted_data字段到documents表（如果不存在）
    columns = [col["name"] for col in inspector.get_columns("documents")]
    if "extracted_data" not in columns:
        op.add_column("documents", sa.Column("extracted_data", pg.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "extracted_data")
    op.drop_constraint("uq_search_history_topic", "search_history", type_="unique")
    op.drop_table("search_history")

