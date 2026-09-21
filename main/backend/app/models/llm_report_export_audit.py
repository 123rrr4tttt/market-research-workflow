from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, BigIDMixin


class LlmReportExportAuditEvent(BigIDMixin, Base):
    __tablename__ = "llm_report_export_audit_events"
    __table_args__ = (UniqueConstraint("trace_id", name="uq_llm_report_export_audit_events_trace_id"),)

    trace_id = Column(String(128), nullable=True, index=True)
    source_trace_id = Column(String(128), nullable=True, index=True)
    request_id = Column(String(128), nullable=True, index=True)
    project_key = Column(String(64), nullable=True, index=True)
    job_id = Column(BigInteger, nullable=True, index=True)
    export_format = Column(String(32), nullable=True, index=True)
    outcome = Column(String(32), nullable=False, server_default="unknown", index=True)
    integrity_mode = Column(String(64), nullable=True, index=True)
    integrity_trusted = Column(Boolean, nullable=False, server_default="false", index=True)
    actor_id = Column(String(128), nullable=True, index=True)
    artifact_id = Column(String(128), nullable=True, index=True)
    artifact_sha256 = Column(String(64), nullable=True, index=True)
    filename = Column(Text, nullable=True)
    content_type = Column(String(128), nullable=True)
    content_size_bytes = Column(BigInteger, nullable=True)
    error_code = Column(String(128), nullable=True, index=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
