"""Project-scoped retrieval method snapshots, plans and run receipts."""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, BigIDMixin


class ProjectRetrievalMode(BigIDMixin, Base):
    __tablename__ = "project_retrieval_modes"
    __table_args__ = (
        UniqueConstraint("project_key", "mode_id", "version", name="uq_project_retrieval_mode_version"),
        Index("uq_project_retrieval_mode_current", "project_key", unique=True,
              postgresql_where=text("is_current IS TRUE")),
    )

    project_key = Column(String(128), nullable=False)
    mode_id = Column(String(128), nullable=False)
    version = Column(String(128), nullable=False)
    source_revision = Column(String(64), nullable=False)
    snapshot = Column(JSONB, nullable=False)
    is_current = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProjectRetrievalPlan(BigIDMixin, Base):
    __tablename__ = "project_retrieval_plans"
    __table_args__ = (UniqueConstraint("project_key", "plan_id", name="uq_project_retrieval_plan"),)

    project_key = Column(String(128), nullable=False)
    plan_id = Column(String(64), nullable=False)
    mode_id = Column(String(128), nullable=False)
    mode_version = Column(String(128), nullable=False)
    payload = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProjectRetrievalRun(BigIDMixin, Base):
    __tablename__ = "project_retrieval_runs"
    __table_args__ = (
        UniqueConstraint("project_key", "run_id", name="uq_project_retrieval_run"),
        UniqueConstraint("project_key", "idempotency_key", name="uq_project_retrieval_idempotency"),
    )

    project_key = Column(String(128), nullable=False)
    run_id = Column(String(64), nullable=False)
    plan_id = Column(String(64), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False)
    phase = Column(String(64), nullable=False)
    counts = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    errors = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    receipt = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
