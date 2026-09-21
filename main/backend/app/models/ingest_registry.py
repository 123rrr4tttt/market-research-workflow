from __future__ import annotations

from sqlalchemy import Column, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

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

    project_key = Column(String(64), nullable=False, index=True)
    trigger_type = Column(String(96), nullable=False, index=True)
    registry_key = Column(String(512), nullable=False, index=True)
    idempotency_key = Column(String(256), nullable=False, index=True)
    submission_id = Column(String(64), nullable=False, index=True)
    task_id = Column(String(128), nullable=True, index=True)
    status = Column(String(32), nullable=False, server_default="submitted", index=True)
    request_hash = Column(String(64), nullable=False, index=True)
    request_payload = Column(JSONB, nullable=True)
    subject_payload = Column(JSONB, nullable=True)
    response_payload = Column(JSONB, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
