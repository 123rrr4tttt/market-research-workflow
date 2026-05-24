from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, BigIDMixin


class LongCycleLiveTask(BigIDMixin, Base):
    __tablename__ = "long_cycle_live_tasks"
    __table_args__ = (
        UniqueConstraint("project_key", "task_key", name="uq_long_cycle_live_tasks_project_task"),
        UniqueConstraint("project_key", "queue_item_key", name="uq_long_cycle_live_tasks_project_queue_item"),
    )

    project_key = Column(String(64), nullable=False, index=True)
    task_key = Column(String(96), nullable=False, index=True)
    queue_item_key = Column(String(96), nullable=False, index=True)
    dispatch_key = Column(String(96), nullable=False, index=True)
    dispatch_ref = Column(String(256), nullable=False)
    scheduler_ref = Column(String(256), nullable=False)
    persistent_ref = Column(String(256), nullable=False)
    queue_name = Column(String(128), nullable=False)
    worker_task_name = Column(String(128), nullable=False)
    selected_window = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, index=True)
    output_ref = Column(Text, nullable=True)
    live_dispatch = Column(Boolean, nullable=False, server_default="false")
    live_enqueue = Column(Boolean, nullable=False, server_default="false")
    live_db_write = Column(Boolean, nullable=False, server_default="false")
    worker_consumed = Column(Boolean, nullable=False, server_default="false")
    digestion_output_readback = Column(Boolean, nullable=False, server_default="false")
    downstream_handoff_observed = Column(Boolean, nullable=False, server_default="false")
    task_payload = Column(JSONB, nullable=False)
    queue_payload = Column(JSONB, nullable=False)
    persistence_writes = Column(JSONB, nullable=False)
    lifecycle_events = Column(JSONB, nullable=False)
    downstream_handoffs = Column(JSONB, nullable=False)
    closure_evidence = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
