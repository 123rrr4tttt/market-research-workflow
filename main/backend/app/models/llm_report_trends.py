from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, BigIDMixin


class LlmReportQualityTrend(BigIDMixin, Base):
    __tablename__ = "llm_report_quality_trends"
    __table_args__ = (UniqueConstraint("trace_id", name="uq_llm_report_quality_trends_trace_id"),)

    trace_id = Column(String(128), nullable=True, index=True)
    request_id = Column(String(128), nullable=True, index=True)
    project_key = Column(String(64), nullable=True, index=True)
    job_id = Column(BigInteger, nullable=True, index=True)
    job_status = Column(String(32), nullable=True, index=True)
    topic = Column(Text, nullable=True)
    decision = Column(String(16), nullable=False, server_default="fail", index=True)
    passed = Column(Boolean, nullable=False, server_default="false")
    gate_mode = Column(String(16), nullable=True, index=True)
    gate_mode_raw = Column(String(32), nullable=True)
    gate_mode_fallback = Column(Boolean, nullable=False, server_default="false")
    citation_coverage = Column(Numeric(6, 4), nullable=False, server_default="0")
    evidence_coverage = Column(Numeric(6, 4), nullable=False, server_default="0")
    source_count = Column(Integer, nullable=False, server_default="0")
    source_count_requested = Column(Integer, nullable=False, server_default="0")
    source_count_resolved = Column(Integer, nullable=False, server_default="0")
    missing_items_count = Column(Integer, nullable=False, server_default="0")
    hard_failure_count = Column(Integer, nullable=False, server_default="0")
    soft_failure_count = Column(Integer, nullable=False, server_default="0")
    readiness = Column(String(32), nullable=True, index=True)
    next_action = Column(String(128), nullable=True)
    record_source = Column(String(32), nullable=False, server_default="generate", index=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
