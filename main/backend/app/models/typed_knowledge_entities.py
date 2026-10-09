from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, BigIDMixin


class TypedKnowledgeObject(BigIDMixin, Base):
    __tablename__ = "typed_knowledge_objects"
    __table_args__ = (
        UniqueConstraint("project_key", "object_type", "object_key", name="uq_typed_knowledge_project_type_key"),
        UniqueConstraint("identity_ref", name="uq_typed_knowledge_identity_ref"),
    )

    project_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    object_key: Mapped[str] = mapped_column(String(255), nullable=False)
    identity_ref: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    visibility_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False)
    review_state: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    governance: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    writing_handoff_refs: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB, nullable=True
    )
    payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    updated_at_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
