from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base, BigIDMixin


class WritingDocument(BigIDMixin, Base):
    __tablename__ = "writing_documents"
    __table_args__ = (
        UniqueConstraint("project_key", "id", name="uq_writing_documents_project_id"),
    )

    project_key = Column(String(64), nullable=False, index=True)
    title = Column(String(500), nullable=False, server_default="")
    body_md = Column(Text, nullable=False, server_default="")
    status = Column(String(32), nullable=False, server_default="draft")
    head_version = Column(Integer, nullable=False, server_default="1")
    etag = Column(String(64), nullable=False, server_default="")
    updated_by_user_id = Column(String(128), nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    drafts = relationship("WritingDocumentDraft", back_populates="document", cascade="all, delete-orphan")
    citations = relationship("WritingDocumentCitation", back_populates="document", cascade="all, delete-orphan")


class WritingDocumentDraft(BigIDMixin, Base):
    __tablename__ = "writing_document_drafts"
    __table_args__ = (
        UniqueConstraint("doc_id", "autosave_token", name="uq_writing_document_drafts_doc_autosave_token"),
    )

    doc_id = Column(BigInteger, ForeignKey("writing_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    project_key = Column(String(64), nullable=False, index=True)
    draft_body_md = Column(Text, nullable=False, server_default="")
    selection_snapshot = Column(JSONB, nullable=True)
    base_version = Column(Integer, nullable=False, server_default="1")
    autosave_token = Column(String(128), nullable=False, server_default="")
    request_id = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    document = relationship("WritingDocument", back_populates="drafts")


class WritingDocumentCitation(BigIDMixin, Base):
    __tablename__ = "writing_document_citations"

    doc_id = Column(BigInteger, ForeignKey("writing_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    project_key = Column(String(64), nullable=False, index=True)
    source_doc_id = Column(BigInteger, nullable=True)
    source_uri = Column(Text, nullable=True)
    source_title = Column(String(500), nullable=True)
    quote_text = Column(Text, nullable=True)
    position_anchor = Column(String(255), nullable=True)
    card_id = Column(String(128), nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    document = relationship("WritingDocument", back_populates="citations")
