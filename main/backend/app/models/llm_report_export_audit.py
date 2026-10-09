from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, BigIDMixin


class LlmReportExportAuditEvent(BigIDMixin, Base):
    __tablename__ = "llm_report_export_audit_events"
    __table_args__ = (UniqueConstraint("trace_id", name="uq_llm_report_export_audit_events_trace_id"),)

    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source_trace_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    project_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    job_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    export_format: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    outcome: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="unknown", index=True
    )
    integrity_mode: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    integrity_trusted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", index=True
    )
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    artifact_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    artifact_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
