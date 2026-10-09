from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, BigIDMixin


class LlmReportQualityTrend(BigIDMixin, Base):
    __tablename__ = "llm_report_quality_trends"
    __table_args__ = (UniqueConstraint("trace_id", name="uq_llm_report_quality_trends_trace_id"),)

    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    project_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    job_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    job_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="fail", index=True
    )
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    gate_mode: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    gate_mode_raw: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gate_mode_fallback: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    citation_coverage: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, server_default="0"
    )
    evidence_coverage: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, server_default="0"
    )
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    source_count_requested: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    source_count_resolved: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    missing_items_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    hard_failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    soft_failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    readiness: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    next_action: Mapped[str | None] = mapped_column(String(128), nullable=True)
    record_source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="generate", index=True
    )
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
