from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, BigIDMixin


class LlmReportExportTokenState(BigIDMixin, Base):
    __tablename__ = "llm_report_export_token_states"
    __table_args__ = (
        UniqueConstraint("artifact_id", name="uq_llm_report_export_token_states_artifact_id"),
    )

    artifact_id = Column(String(128), nullable=False, index=True)
    actor_id = Column(String(128), nullable=True, index=True)
    project_key = Column(String(64), nullable=True, index=True)
    trace_id = Column(String(128), nullable=True, index=True)
    request_id = Column(String(128), nullable=True, index=True)
    job_id = Column(BigInteger, nullable=True, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    revoke_reason = Column(Text, nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
