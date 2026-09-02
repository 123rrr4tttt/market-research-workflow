"""add successor P0-D replayable projection substrate

Revision ID: 20260831_000002
Revises: 20260830_000001
Create Date: 2026-08-31 19:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260831_000002"
down_revision = "20260830_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runtime_projection_offsets",
        sa.Column("source_kind", sa.String(32), nullable=True),
        schema="public",
    )
    op.add_column(
        "runtime_projection_offsets",
        sa.Column("source_ref", sa.Text(), nullable=True),
        schema="public",
    )
    op.add_column(
        "runtime_projection_offsets",
        sa.Column("source_incarnation", sa.String(128), nullable=True),
        schema="public",
    )
    op.add_column(
        "runtime_projection_offsets",
        sa.Column(
            "projection_generation",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        schema="public",
    )
    op.execute(
        """
        UPDATE public.runtime_projection_offsets
        SET source_kind = 'LEGACY_OFFSET',
            source_ref = 'projection-offset:' || projection_offset_id,
            source_incarnation = 'legacy:' || source_digest
        WHERE source_kind IS NULL
           OR source_ref IS NULL
           OR source_incarnation IS NULL
        """
    )
    op.alter_column(
        "runtime_projection_offsets", "source_kind", nullable=False, schema="public"
    )
    op.alter_column(
        "runtime_projection_offsets", "source_ref", nullable=False, schema="public"
    )
    op.alter_column(
        "runtime_projection_offsets",
        "source_incarnation",
        nullable=False,
        schema="public",
    )
    op.drop_constraint(
        "uq_projection_owner_version",
        "runtime_projection_offsets",
        type_="unique",
        schema="public",
    )
    op.drop_constraint(
        "ck_projection_revisions",
        "runtime_projection_offsets",
        type_="check",
        schema="public",
    )
    op.create_check_constraint(
        "ck_projection_revisions",
        "runtime_projection_offsets",
        "source_revision >= 0 AND projection_generation >= 0 AND revision >= 0",
        schema="public",
    )
    op.drop_index(
        "ix_projection_projector",
        table_name="runtime_projection_offsets",
        schema="public",
    )
    op.create_unique_constraint(
        "uq_projection_owner_source",
        "runtime_projection_offsets",
        [
            "project_key",
            "projector_id",
            "projector_version",
            "source_ref",
            "source_incarnation",
        ],
        schema="public",
    )
    op.create_index(
        "ix_projection_projector_source",
        "runtime_projection_offsets",
        ["project_key", "projector_id", "source_ref"],
        schema="public",
    )

    op.create_table(
        "runtime_run_projections",
        sa.Column("project_key", sa.String(128), primary_key=True),
        sa.Column("projector_id", sa.String(128), primary_key=True),
        sa.Column("projector_version", sa.String(64), primary_key=True),
        sa.Column("source_ref", sa.Text(), primary_key=True),
        sa.Column("source_incarnation", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(128), primary_key=True),
        sa.Column("projection_generation", sa.BigInteger(), nullable=False),
        sa.Column("source_revision", sa.BigInteger(), nullable=False),
        sa.Column("source_digest", sa.CHAR(64), nullable=False),
        sa.Column(
            "state_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("projection_digest", sa.CHAR(64), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "projection_generation >= 0 AND source_revision >= 0 AND revision >= 0",
            name="ck_runtime_run_projection_revisions",
        ),
        schema="public",
    )
    op.create_index(
        "ix_runtime_run_projection_source",
        "runtime_run_projections",
        ["project_key", "projector_id", "source_ref"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_runtime_run_projection_source",
        table_name="runtime_run_projections",
        schema="public",
    )
    op.drop_table("runtime_run_projections", schema="public")

    op.drop_index(
        "ix_projection_projector_source",
        table_name="runtime_projection_offsets",
        schema="public",
    )
    op.drop_constraint(
        "uq_projection_owner_source",
        "runtime_projection_offsets",
        type_="unique",
        schema="public",
    )
    op.create_unique_constraint(
        "uq_projection_owner_version",
        "runtime_projection_offsets",
        ["project_key", "projector_id", "projector_version"],
        schema="public",
    )
    op.create_index(
        "ix_projection_projector",
        "runtime_projection_offsets",
        ["project_key", "projector_id"],
        schema="public",
    )
    op.drop_constraint(
        "ck_projection_revisions",
        "runtime_projection_offsets",
        type_="check",
        schema="public",
    )
    op.create_check_constraint(
        "ck_projection_revisions",
        "runtime_projection_offsets",
        "source_revision >= 0 AND revision >= 0",
        schema="public",
    )
    op.drop_column(
        "runtime_projection_offsets", "projection_generation", schema="public"
    )
    op.drop_column("runtime_projection_offsets", "source_incarnation", schema="public")
    op.drop_column("runtime_projection_offsets", "source_ref", schema="public")
    op.drop_column("runtime_projection_offsets", "source_kind", schema="public")
