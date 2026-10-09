from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, BigIDMixin


class IngestSubmissionRegistry(BigIDMixin, Base):
    __tablename__ = "ingest_submission_registry"
    __table_args__ = (
        UniqueConstraint("registry_key", name="uq_ingest_submission_registry_key"),
        UniqueConstraint(
            "project_key",
            "trigger_type",
            "idempotency_key",
            name="uq_ingest_submission_project_trigger_key",
        ),
    )

    project_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    registry_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    submission_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(
        String(32), nullable=False, server_default="submitted", index=True
    )
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    subject_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    response_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
