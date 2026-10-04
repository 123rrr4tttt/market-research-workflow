"""Global RuntimeNode registry and immutable deployment catalog."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection

from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    StaleRevisionError,
    _one_mapping,
    _table,
    _utcnow,
)


@dataclass(frozen=True, slots=True)
class DeploymentCatalog:
    catalog_digest: str
    catalog_version: str
    catalog_ref: str
    node_profile_digest: str
    security_profile_digest: str
    resource_profile_digest: str


class DeploymentCatalogRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def put_exact(self, catalog: DeploymentCatalog) -> Mapping[str, Any]:
        table = _table("runtime_deployment_catalogs")
        values = {name: getattr(catalog, name) for name in catalog.__dataclass_fields__}
        values["created_at"] = _utcnow()
        self.connection.execute(pg_insert(table).values(**values).on_conflict_do_nothing(index_elements=(table.c.catalog_digest,)))
        row = self.load(catalog.catalog_digest)
        if any(row[name] != getattr(catalog, name) for name in catalog.__dataclass_fields__):
            raise ExactBindingConflict("deployment catalog digest is bound to different metadata")
        return row

    def load(self, catalog_digest: str) -> Mapping[str, Any]:
        table = _table("runtime_deployment_catalogs")
        row = _one_mapping(self.connection.execute(select(table).where(table.c.catalog_digest == catalog_digest)))
        if row is None:
            raise RecordNotFound(f"deployment catalog not found: {catalog_digest}")
        return row


class RuntimeNodeRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def register(self, *, node_id: str, node_profile_digest: str, deployment_catalog_digest: str, runtime_protocol_version: str, started_at: datetime) -> Mapping[str, Any]:
        table = _table("runtime_nodes")
        values = dict(node_id=node_id, node_profile_digest=node_profile_digest, deployment_catalog_digest=deployment_catalog_digest,
                      runtime_protocol_version=runtime_protocol_version, state="ACTIVE", heartbeat_at=started_at, started_at=started_at,
                      drain_requested_at=None, current_claim_count=0, revision=0, created_at=_utcnow(), updated_at=_utcnow())
        self.connection.execute(pg_insert(table).values(**values).on_conflict_do_nothing(index_elements=(table.c.node_id,)))
        row = self.load(node_id)
        immutable = ("node_profile_digest", "deployment_catalog_digest", "runtime_protocol_version", "started_at")
        if any(row[field] != values[field] for field in immutable):
            raise ExactBindingConflict("node identity cannot be rebound to another deployment")
        return row

    def load(self, node_id: str) -> Mapping[str, Any]:
        table = _table("runtime_nodes")
        row = _one_mapping(self.connection.execute(select(table).where(table.c.node_id == node_id)))
        if row is None:
            raise RecordNotFound(f"runtime node not found: {node_id}")
        return row

    def heartbeat(self, node_id: str, *, expected_revision: int, heartbeat_at: datetime, current_claim_count: int) -> Mapping[str, Any]:
        table = _table("runtime_nodes")
        result = self.connection.execute(update(table).where(table.c.node_id == node_id, table.c.revision == expected_revision).values(
            heartbeat_at=heartbeat_at, current_claim_count=current_claim_count, revision=expected_revision + 1, updated_at=_utcnow()))
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError("runtime node heartbeat CAS failed")
        return self.load(node_id)

    def request_drain(self, node_id: str, *, expected_revision: int, requested_at: datetime) -> Mapping[str, Any]:
        table = _table("runtime_nodes")
        result = self.connection.execute(update(table).where(table.c.node_id == node_id, table.c.revision == expected_revision).values(
            state="DRAINING", drain_requested_at=requested_at, revision=expected_revision + 1, updated_at=_utcnow()))
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError("runtime node drain CAS failed")
        return self.load(node_id)


__all__ = ["DeploymentCatalog", "DeploymentCatalogRepository", "RuntimeNodeRepository"]
