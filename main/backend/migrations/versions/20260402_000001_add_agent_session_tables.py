"""add claude-style agent session tables

Revision ID: 20260402_000001
Revises: 20260312_000008
Create Date: 2026-04-02 00:01:00.000000

"""

from alembic import op
import sqlalchemy as sa

from migrations.util import table_exists


# revision identifiers, used by Alembic.
revision = "20260402_000001"
down_revision = "20260312_000008"
branch_labels = None
depends_on = None


def _jsonb_default(value: str) -> sa.sql.elements.TextClause:
    return sa.text(value)


def _create_agent_sessions_table() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="user"),
        sa.Column("project_key", sa.String(length=128), nullable=True),
        sa.Column("entrypoint_type", sa.String(length=64), nullable=False, server_default="chat"),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("current_phase", sa.String(length=32), nullable=False, server_default="research"),
        sa.Column("compat_mode", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("compat_job_id", sa.String(length=64), nullable=True),
        sa.Column("logical_task_list_key", sa.String(length=128), nullable=True),
        sa.Column("root_task_id", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'{}'::jsonb")),
        sa.Column("final_summary", sa.Text(), nullable=True),
        sa.Column("final_result", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("session_id", name="uq_agent_sessions_session_id"),
        schema="public",
    )
    op.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_agent_sessions_project_key ON public.agent_sessions (project_key)'))
    op.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_agent_sessions_compat_job_id ON public.agent_sessions (compat_job_id)'))


def _create_agent_tasks_table() -> None:
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("parent_task_id", sa.String(length=64), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False, server_default="research"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("execution_mode", sa.String(length=32), nullable=False, server_default="worker"),
        sa.Column("owner", sa.String(length=128), nullable=True),
        sa.Column("blocked_by", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'[]'::jsonb")),
        sa.Column("blocks", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'[]'::jsonb")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("write_set", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'[]'::jsonb")),
        sa.Column("read_set", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'[]'::jsonb")),
        sa.Column("task_spec", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'{}'::jsonb")),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'{}'::jsonb")),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("result_payload", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'{}'::jsonb")),
        sa.Column("tool_use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_usage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_activity", sa.Text(), nullable=True),
        sa.Column("recent_activities", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'[]'::jsonb")),
        sa.Column("summary_label", sa.String(length=255), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("task_id", name="uq_agent_tasks_task_id"),
        schema="public",
    )
    op.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_agent_tasks_session_id ON public.agent_tasks (session_id)'))
    op.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_agent_tasks_parent_task_id ON public.agent_tasks (parent_task_id)'))


def _create_agent_messages_table() -> None:
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="public",
    )
    op.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_agent_messages_session_id ON public.agent_messages (session_id)'))
    op.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_agent_messages_task_id ON public.agent_messages (task_id)'))


def _create_agent_artifacts_table() -> None:
    op.create_table(
        "agent_artifacts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("artifact_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_json", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'{}'::jsonb")),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("artifact_id", name="uq_agent_artifacts_artifact_id"),
        schema="public",
    )
    op.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_agent_artifacts_session_id ON public.agent_artifacts (session_id)'))
    op.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_agent_artifacts_task_id ON public.agent_artifacts (task_id)'))


def _create_agent_events_table() -> None:
    op.create_table(
        "agent_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'{}'::jsonb")),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("session_id", "seq", name="uq_agent_events_session_seq"),
        schema="public",
    )
    op.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_agent_events_session_id ON public.agent_events (session_id)'))
    op.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_agent_events_task_id ON public.agent_events (task_id)'))


def _create_agent_approvals_table() -> None:
    op.create_table(
        "agent_approvals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("approval_id", sa.String(length=128), nullable=False),
        sa.Column("binding_hash", sa.String(length=128), nullable=False),
        sa.Column("binding_payload", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'{}'::jsonb")),
        sa.Column("requester_session_id", sa.String(length=64), nullable=True),
        sa.Column("requester_task_id", sa.String(length=64), nullable=True),
        sa.Column("requester_actor", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("audit_log", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'[]'::jsonb")),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_jsonb_default("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("approval_id", name="uq_agent_approvals_approval_id"),
        schema="public",
    )
    op.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_agent_approvals_binding_hash ON public.agent_approvals (binding_hash)'))
    op.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_agent_approvals_requester_session_id ON public.agent_approvals (requester_session_id)'))
    op.execute(sa.text('CREATE INDEX IF NOT EXISTS ix_agent_approvals_requester_task_id ON public.agent_approvals (requester_task_id)'))


def upgrade() -> None:
    conn = op.get_bind()
    if not table_exists(conn, "agent_sessions", schema="public"):
        _create_agent_sessions_table()
    if not table_exists(conn, "agent_tasks", schema="public"):
        _create_agent_tasks_table()
    if not table_exists(conn, "agent_messages", schema="public"):
        _create_agent_messages_table()
    if not table_exists(conn, "agent_artifacts", schema="public"):
        _create_agent_artifacts_table()
    if not table_exists(conn, "agent_events", schema="public"):
        _create_agent_events_table()
    if not table_exists(conn, "agent_approvals", schema="public"):
        _create_agent_approvals_table()


def downgrade() -> None:
    conn = op.get_bind()
    for index_name in [
        "ix_agent_approvals_requester_task_id",
        "ix_agent_approvals_requester_session_id",
        "ix_agent_approvals_binding_hash",
        "ix_agent_events_task_id",
        "ix_agent_events_session_id",
        "ix_agent_artifacts_task_id",
        "ix_agent_artifacts_session_id",
        "ix_agent_messages_task_id",
        "ix_agent_messages_session_id",
        "ix_agent_tasks_parent_task_id",
        "ix_agent_tasks_session_id",
        "ix_agent_sessions_compat_job_id",
        "ix_agent_sessions_project_key",
    ]:
        op.execute(sa.text(f'DROP INDEX IF EXISTS public."{index_name}"'))

    for table_name in [
        "agent_approvals",
        "agent_events",
        "agent_artifacts",
        "agent_messages",
        "agent_tasks",
        "agent_sessions",
    ]:
        if table_exists(conn, table_name, schema="public"):
            op.drop_table(table_name, schema="public")
