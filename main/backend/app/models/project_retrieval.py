"""Project-scoped retrieval method snapshots, plans and run receipts."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.schema import Table

from app.services.project_retrieval.contracts import (
    RetrievalJsonArray,
    RetrievalJsonAtom,
    RetrievalJsonObject,
    RetrievalJsonValue,
)

from .base import Base, BigIDMixin


# SQLAlchemy resolves recursive ``Mapped`` aliases in this module's namespace.
# Keeping the complete authority-owned JSON alias graph here lets the native
# mapper evaluate the fields without introducing a shadow persistence type.
_SQLALCHEMY_ANNOTATION_NAMESPACE = (
    RetrievalJsonAtom,
    RetrievalJsonArray,
    RetrievalJsonValue,
)


class ProjectRetrievalMode(BigIDMixin, Base):
    __tablename__ = "project_retrieval_modes"
    __table_args__ = (
        UniqueConstraint("project_key", "mode_id", "version", name="uq_project_retrieval_mode_version"),
        Index("uq_project_retrieval_mode_current", "project_key", unique=True,
              postgresql_where=text("is_current IS TRUE")),
    )

    project_key: Mapped[str] = mapped_column(String(128), nullable=False)
    mode_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[RetrievalJsonObject] = mapped_column(JSONB, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __init__(
        self,
        *,
        project_key: str,
        mode_id: str,
        version: str,
        source_revision: str,
        snapshot: RetrievalJsonObject,
        is_current: bool = True,
    ) -> None:
        self.project_key = project_key
        self.mode_id = mode_id
        self.version = version
        self.source_revision = source_revision
        self.snapshot = snapshot
        self.is_current = is_current


class ProjectRetrievalPlan(BigIDMixin, Base):
    __tablename__ = "project_retrieval_plans"
    __table_args__ = (UniqueConstraint("project_key", "plan_id", name="uq_project_retrieval_plan"),)

    project_key: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_id: Mapped[str] = mapped_column(String(64), nullable=False)
    mode_id: Mapped[str] = mapped_column(String(128), nullable=False)
    mode_version: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[RetrievalJsonObject] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __init__(
        self,
        *,
        project_key: str,
        plan_id: str,
        mode_id: str,
        mode_version: str,
        payload: RetrievalJsonObject,
    ) -> None:
        self.project_key = project_key
        self.plan_id = plan_id
        self.mode_id = mode_id
        self.mode_version = mode_version
        self.payload = payload


def project_retrieval_tables() -> tuple[Table, Table]:
    """Return the native tenant tables owned by project retrieval."""

    return (
        ProjectRetrievalMode.__table__,
        ProjectRetrievalPlan.__table__,
    )


__all__ = [
    "ProjectRetrievalMode",
    "ProjectRetrievalPlan",
    "project_retrieval_tables",
]
