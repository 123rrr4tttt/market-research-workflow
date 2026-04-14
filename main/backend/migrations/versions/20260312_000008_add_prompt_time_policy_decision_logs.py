"""add prompt-time-density policy decision log and feedback tables

Revision ID: 20260312_000008
Revises: 20260312_000007
Create Date: 2026-03-12 17:10:00.000000
"""

from alembic import op
import sqlalchemy as sa

from migrations.util import table_exists


# revision identifiers, used by Alembic.
revision = "20260312_000008"
down_revision = "20260312_000007"
branch_labels = None
depends_on = None


def _create_policy_log_table() -> None:
    op.create_table(
        "prompt_time_policy_decision_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("project_key", sa.String(length=64), nullable=True),
        sa.Column("source_domain", sa.String(length=255), nullable=False),
        sa.Column("noun_group_id", sa.String(length=255), nullable=False),
        sa.Column("window", sa.String(length=16), nullable=False),
        sa.Column("chosen_window", sa.String(length=16), nullable=False),
        sa.Column("is_chosen", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("vector_overlap", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("shift_signal", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("p_base", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("p_new", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("kl_to_base", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("offpeak_confidence", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("policy_version", sa.String(length=64), nullable=False, server_default="density-cloud-v1"),
        sa.Column("shift_signal_breakdown", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("features_json", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="public",
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_prompt_time_policy_decision_logs_request_id "
            "ON public.prompt_time_policy_decision_logs(request_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_prompt_time_policy_decision_logs_noun_group_id "
            "ON public.prompt_time_policy_decision_logs(noun_group_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_prompt_time_policy_decision_logs_project_key "
            "ON public.prompt_time_policy_decision_logs(project_key)"
        )
    )


def _create_feedback_table() -> None:
    op.create_table(
        "prompt_time_window_feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("source_domain", sa.String(length=255), nullable=False),
        sa.Column("noun_group_id", sa.String(length=255), nullable=False),
        sa.Column("window", sa.String(length=16), nullable=False),
        sa.Column("observed_reward", sa.Numeric(10, 6), nullable=True),
        sa.Column("duplicate_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("fail_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("feedback_json", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="public",
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_prompt_time_window_feedback_request_id "
            "ON public.prompt_time_window_feedback(request_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_prompt_time_window_feedback_noun_group_id "
            "ON public.prompt_time_window_feedback(noun_group_id)"
        )
    )


def upgrade() -> None:
    conn = op.get_bind()
    if not table_exists(conn, "prompt_time_policy_decision_logs", schema="public"):
        _create_policy_log_table()
    if not table_exists(conn, "prompt_time_window_feedback", schema="public"):
        _create_feedback_table()


def downgrade() -> None:
    conn = op.get_bind()
    if table_exists(conn, "prompt_time_window_feedback", schema="public"):
        op.drop_table("prompt_time_window_feedback", schema="public")
    if table_exists(conn, "prompt_time_policy_decision_logs", schema="public"):
        op.drop_table("prompt_time_policy_decision_logs", schema="public")
