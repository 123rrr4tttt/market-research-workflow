"""add c7 canonical documents table

Revision ID: 20260903_000003
Revises: 20260831_000002
Create Date: 2026-09-03 03:30:00.000000

The C7 verified-candidate admission slice previously declared its canonical
document table only as an inline ``sa.Table`` that disposable tests created
with ``.create()``.  This Alembic revision is the production schema authority
for that exact successor-owned table; runtime code and tests must not create it
manually on a migrated database.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260903_000003"
down_revision = "20260831_000002"
branch_labels = None
depends_on = None

TABLE_NAME = "c7_movement_canonical_documents"


def _column_spec() -> list[sa.Column]:
    # Keep in lock-step with C7_MOVEMENT_CANONICAL_DOCUMENTS in
    # substrate/postgres/ingest_c7_movement_admission.py.  A parity guard in
    # test_c7_canonical_migration_parity_postgres.py fails when either side
    # drifts.
    return [
        sa.Column("project_key", sa.String(128), primary_key=True),
        sa.Column("object_id", sa.String(128), primary_key=True),
        sa.Column("commit_intent_id", sa.String(128), nullable=False),
        sa.Column("canonical_owner", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("step_id", sa.String(128), nullable=False),
        sa.Column("attempt_id", sa.String(128), nullable=False),
        sa.Column("capability_id", sa.String(128), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("program_digest", sa.String(64), nullable=False),
        sa.Column("plan_digest", sa.String(64), nullable=False),
        sa.Column("step_revision", sa.BigInteger, nullable=False),
        sa.Column("attempt_revision", sa.BigInteger, nullable=False),
        sa.Column("execution_epoch", sa.BigInteger, nullable=False),
        sa.Column("attempt_incarnation", sa.String(128), nullable=False),
        sa.Column("assignment_digest", sa.String(64), nullable=False),
        sa.Column("handler_binding_digest", sa.String(64), nullable=False),
        sa.Column("handler_realization_digest", sa.String(64), nullable=False),
        sa.Column("input_closure_digest", sa.String(64), nullable=False),
        sa.Column("revision", sa.BigInteger, nullable=False),
        sa.Column("incarnation", sa.String(128), nullable=False),
        sa.Column("expected_base_revision", sa.BigInteger, nullable=False),
        sa.Column("expected_base_incarnation", sa.String(128), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("snapshot_identity_digest", sa.String(64), nullable=False),
        sa.Column("raw_content_digest", sa.String(64), nullable=False),
        sa.Column("envelope_digest", sa.String(64), nullable=False),
        sa.Column("payload_content_digest", sa.String(64), nullable=False),
        sa.Column("ordered_source_closure_digest", sa.String(64), nullable=False),
        sa.Column("provenance_closure_digest", sa.String(64), nullable=False),
        sa.Column("decision_digest", sa.String(64), nullable=False),
        sa.Column("candidate_digest", sa.String(64), nullable=False),
        sa.Column("candidate_verification_digest", sa.String(64), nullable=False),
        sa.Column("ordered_event_closure_digest", sa.String(64), nullable=False),
        sa.Column("verification_digest", sa.String(64), nullable=False),
        sa.Column("authority_digest", sa.String(64), nullable=False),
        sa.Column("authority_epoch", sa.BigInteger, nullable=False),
        sa.Column("candidate_id", sa.String(128), nullable=False),
        sa.Column("snapshot_ref", sa.String(256), nullable=False),
        sa.Column("alternative", sa.String(32), nullable=False),
        sa.Column("verification_profile_ref", sa.String(128), nullable=False),
        sa.Column("verification_receipt", sa.String(256), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("provenance_digest", sa.String(64), nullable=False),
        sa.Column("candidate_receipt_digest", sa.String(64), nullable=False),
        sa.Column("value_ref", sa.String(256), nullable=False),
        sa.Column("value_revision", sa.BigInteger, nullable=False),
        sa.Column("value_incarnation", sa.String(128), nullable=False),
        sa.Column("value_digest", sa.String(64), nullable=False),
        sa.Column("value_provenance_digest", sa.String(64), nullable=False),
        sa.Column("canonical_commit_ref", sa.String(256), nullable=False),
        sa.Column("receipt_digest", sa.String(64), nullable=False),
        sa.Column("head_closure_digest", sa.String(64), nullable=False),
    ]


def _table_exists(connection: sa.Connection) -> bool:
    return connection.dialect.has_table(connection, TABLE_NAME, schema="public")


def upgrade() -> None:
    connection = op.get_bind()
    if _table_exists(connection):
        return
    op.create_table(TABLE_NAME, *_column_spec(), schema="public")


def downgrade() -> None:
    connection = op.get_bind()
    if _table_exists(connection):
        op.drop_table(TABLE_NAME, schema="public")
