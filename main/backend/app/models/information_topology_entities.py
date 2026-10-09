"""Durable revision rows for the heterogeneous information-topology layer."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, BigIDMixin


class InformationTopologyState(BigIDMixin, Base):
    __tablename__ = "information_topology_states"
    __table_args__ = (
        UniqueConstraint(
            "project_key", "module_id", "namespace", "state_id", "revision",
            name="uq_information_topology_state_revision",
        ),
        Index(
            "uq_information_topology_state_current",
            "project_key", "module_id", "namespace", "state_id",
            unique=True, postgresql_where=text("is_current IS TRUE"),
        ),
        Index("ix_information_topology_state_project_module", "project_key", "module_id"),
    )

    project_key: Mapped[str] = mapped_column(String(128), nullable=False)
    module_id: Mapped[str] = mapped_column(String(128), nullable=False)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    state_id: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_version: Mapped[str] = mapped_column(String(128), nullable=False)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InformationTopologyLink(BigIDMixin, Base):
    __tablename__ = "information_topology_links"
    __table_args__ = (
        UniqueConstraint(
            "project_key", "link_id", "revision", name="uq_information_topology_link_revision"
        ),
        Index(
            "uq_information_topology_link_current", "project_key", "link_id", unique=True,
            postgresql_where=text("is_current IS TRUE"),
        ),
        Index("ix_information_topology_link_project_kind", "project_key", "record_kind"),
    )

    project_key: Mapped[str] = mapped_column(String(128), nullable=False)
    link_id: Mapped[str] = mapped_column(String(255), nullable=False)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    record_kind: Mapped[str] = mapped_column(String(32), nullable=False)  # relation | mapping
    type_or_rule_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    endpoints: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
