from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, BigIDMixin


class WritingDocument(BigIDMixin, Base):
    __tablename__ = "writing_documents"
    __table_args__ = (
        UniqueConstraint("project_key", "id", name="uq_writing_documents_project_id"),
    )

    project_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, server_default="")
    body_md: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="draft"
    )
    head_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    etag: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    updated_by_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    drafts = relationship("WritingDocumentDraft", back_populates="document", cascade="all, delete-orphan")
    citations = relationship("WritingDocumentCitation", back_populates="document", cascade="all, delete-orphan")


class WritingDocumentDraft(BigIDMixin, Base):
    __tablename__ = "writing_document_drafts"
    __table_args__ = (
        UniqueConstraint("doc_id", "autosave_token", name="uq_writing_document_drafts_doc_autosave_token"),
    )

    doc_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("writing_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    draft_body_md: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    selection_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True
    )
    base_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    autosave_token: Mapped[str] = mapped_column(
        String(128), nullable=False, server_default=""
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    document = relationship("WritingDocument", back_populates="drafts")


class WritingDocumentCitation(BigIDMixin, Base):
    __tablename__ = "writing_document_citations"

    doc_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("writing_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_doc_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quote_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    position_anchor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    card_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    document = relationship("WritingDocument", back_populates="citations")
