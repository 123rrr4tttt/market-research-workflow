from __future__ import annotations

from sqlalchemy import Column, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, BigIDMixin


class TypedKnowledgeObject(BigIDMixin, Base):
    __tablename__ = "typed_knowledge_objects"
    __table_args__ = (
        UniqueConstraint("project_key", "object_type", "object_key", name="uq_typed_knowledge_project_type_key"),
        UniqueConstraint("identity_ref", name="uq_typed_knowledge_identity_ref"),
    )

    project_key = Column(String(64), nullable=False, index=True)
    object_type = Column(String(32), nullable=False, index=True)
    object_key = Column(String(255), nullable=False)
    identity_ref = Column(String(512), nullable=False, index=True)
    visibility_scope = Column(String(64), nullable=False)
    lifecycle_state = Column(String(32), nullable=False)
    review_state = Column(String(64), nullable=False, index=True)
    governance = Column(JSONB, nullable=True)
    writing_handoff_refs = Column(JSONB, nullable=True)
    payload = Column(JSONB, nullable=True)
    updated_at_text = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
