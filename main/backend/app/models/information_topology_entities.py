"""Durable revision rows for the heterogeneous information-topology layer."""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB

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

    project_key = Column(String(128), nullable=False)
    module_id = Column(String(128), nullable=False)
    namespace = Column(String(255), nullable=False)
    state_id = Column(String(255), nullable=False)
    profile_id = Column(String(255), nullable=False)
    profile_version = Column(String(128), nullable=False)
    revision = Column(BigInteger, nullable=False)
    payload = Column(JSONB, nullable=False)
    provenance = Column(JSONB, nullable=True)
    digest = Column(String(64), nullable=False)
    is_current = Column(Boolean, nullable=False, server_default="true")
    deleted = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


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

    project_key = Column(String(128), nullable=False)
    link_id = Column(String(255), nullable=False)
    revision = Column(BigInteger, nullable=False)
    record_kind = Column(String(32), nullable=False)  # relation | mapping
    type_or_rule_ref = Column(String(512), nullable=False)
    endpoints = Column(JSONB, nullable=False)
    payload = Column(JSONB, nullable=False)
    provenance = Column(JSONB, nullable=True)
    digest = Column(String(64), nullable=False)
    is_current = Column(Boolean, nullable=False, server_default="true")
    deleted = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
