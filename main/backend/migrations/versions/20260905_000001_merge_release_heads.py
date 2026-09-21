"""merge release migration heads

Revision ID: 20260905_000001
Revises: 20260525_000001, 20260831_000002
Create Date: 2026-09-05 00:00:00.000000
"""

from __future__ import annotations


revision = "20260905_000001"
down_revision = ("20260525_000001", "20260831_000002")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Keep both parent migrations at their final states."""
    pass


def downgrade() -> None:
    """Restore the merge graph without changing database objects."""
    pass
