from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
import os
from collections.abc import Mapping
from typing import Annotated, Any

from sqlalchemy import select
from sqlalchemy.engine import Engine

from .errors import ObservabilityTypeError, ObservabilityValueError
from .observations import parse_observed_at


AUTHORITY_READ_SOURCE = (
    "postgres.project_scope_registry+runtime_step_authorizations"
    "+runtime_capability_authority"
)
PROJECTION_SOURCE = "postgres.projection:project-source+active-offset"
DATABASE_SOURCE = "sqlalchemy.engine:select_1+pool_status"
PROVIDER_SOURCE = "production.provider-runtime:explicit-local-simulation-or-unknown"


class QueueReadStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class ProviderRuntimeStatus(StrEnum):
    SIMULATED_HEALTHY = "simulated_healthy"
    SIMULATED_FAILURE = "simulated_failure"
    NOT_OBSERVED = "not_observed"
    UNSUPPORTED = "unsupported"


class RuntimeBindingStatus(StrEnum):
    BOUND = "bound"
    UNBOUND = "unbound"
    UNKNOWN = "unknown"
    MISMATCH = "mismatch"


class ProjectionReleaseStatus(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"


class RuntimeAuthorityReadStatus(StrEnum):
    OBSERVED = "observed"
    NOT_OBSERVED = "not_observed"
    MISMATCH = "mismatch"


class ProjectionReadStatus(StrEnum):
    OK = "ok"
    NOT_OBSERVED = "not_observed"
    ERROR = "error"


class ProjectionDriftStatus(StrEnum):
    UNKNOWN = "unknown"
    MATCH = "match"
    MISMATCH = "mismatch"


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ObservabilityValueError(f"runtime health {field_name} is required")
    return value.strip()


@dataclass(frozen=True, slots=True)
class QueueRuntimeSignal:
    source: str
    read_status: QueueReadStatus
    depth: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _required_text(self.source, "queue source"))
        if not isinstance(self.read_status, QueueReadStatus):
            raise ObservabilityTypeError("queue read_status is closed")
        if not isinstance(self.depth, int) or isinstance(self.depth, bool) or self.depth < 0:
            raise ObservabilityValueError("queue depth must be a non-negative integer")

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DatabaseRuntimeSignal:
    source: str
    connection_status: str
    pool_status: str
    pool_size: int
    checked_out: int
    pool_limit: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _required_text(self.source, "database source"))
        object.__setattr__(self, "connection_status", _required_text(self.connection_status, "database connection status"))
        object.__setattr__(self, "pool_status", _required_text(self.pool_status, "database pool status"))
        values = (self.pool_size, self.checked_out, self.pool_limit)
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values):
            raise ObservabilityValueError("database pool counts must be non-negative integers")
        if self.checked_out > self.pool_limit:
            raise ObservabilityValueError("database checked-out count cannot exceed pool limit")

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProviderRuntimeSignal:
    source: str
    status: ProviderRuntimeStatus
    simulated: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _required_text(self.source, "provider source"))
        if not isinstance(self.status, ProviderRuntimeStatus):
            raise ObservabilityTypeError("provider status is closed")
        simulated_statuses = {
            ProviderRuntimeStatus.SIMULATED_HEALTHY,
            ProviderRuntimeStatus.SIMULATED_FAILURE,
        }
        if self.status in simulated_statuses and self.simulated is not True:
            raise ObservabilityValueError(
                "simulated provider status requires simulated=true"
            )
        if self.status not in simulated_statuses and self.simulated is not False:
            raise ObservabilityValueError(
                "non-simulated provider status requires simulated=false"
            )

    def to_dict(self) -> dict[str, str | bool]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RuntimeBindingSignal:
    source: str
    authority_status: RuntimeBindingStatus
    projection_release_status: ProjectionReleaseStatus
    authority_read: "RuntimeAuthorityReadSignal | None" = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _required_text(self.source, "runtime binding source"))
        if not isinstance(self.authority_status, RuntimeBindingStatus):
            raise ObservabilityTypeError("runtime authority status is closed")
        if not isinstance(self.projection_release_status, ProjectionReleaseStatus):
            raise ObservabilityTypeError("projection release status is closed")

    def to_dict(self) -> dict[str, str]:
        payload = asdict(self)
        payload["authority_read"] = (
            self.authority_read.to_dict() if self.authority_read is not None else None
        )
        return payload


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityReadSignal:
    source: str
    read_status: RuntimeAuthorityReadStatus
    task_id: str | None = None
    tenant_id: str | None = None
    project_scope_digest: str | None = None
    project_registry_revision: int | None = None
    capability_id: str | None = None
    step_id: str | None = None
    claim_authority_epoch: int | None = None
    expected_project_scope_digest: str | None = None
    expected_project_registry_revision: int | None = None
    expected_claim_authority_epoch: int | None = None
    mismatch_fields: tuple[str, ...] = ()
    not_observed_fields: tuple[str, ...] = ()
    read_error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _required_text(self.source, "authority read source"))
        if not isinstance(self.read_status, RuntimeAuthorityReadStatus):
            raise ObservabilityTypeError("authority read status is closed")
        object.__setattr__(self, "mismatch_fields", tuple(dict.fromkeys(self.mismatch_fields)))
        object.__setattr__(
            self, "not_observed_fields", tuple(dict.fromkeys(self.not_observed_fields))
        )
        if self.read_status is RuntimeAuthorityReadStatus.MISMATCH and not self.mismatch_fields:
            raise ObservabilityValueError("authority mismatch requires at least one field")
        if self.read_status is RuntimeAuthorityReadStatus.NOT_OBSERVED and not (
            self.not_observed_fields or self.read_error
        ):
            raise ObservabilityValueError("authority not-observed requires a field or read error")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProjectionRuntimeSignal:
    source: str
    read_status: ProjectionReadStatus
    drift_status: ProjectionDriftStatus
    active_source_digest: str
    expected_source_digest: str
    projection_generation: int
    offset_revision: int
    source_revision: int
    offset_ref: str
    status_detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _required_text(self.source, "projection source"))
        if not isinstance(self.read_status, ProjectionReadStatus):
            raise ObservabilityTypeError("projection read_status is closed")
        if not isinstance(self.drift_status, ProjectionDriftStatus):
            raise ObservabilityTypeError("projection drift_status is closed")
        counts = (self.projection_generation, self.offset_revision, self.source_revision)
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in counts
        ):
            raise ObservabilityValueError(
                "projection generation, offset revision, and source revision must be non-negative integers"
            )
        digests = (self.active_source_digest, self.expected_source_digest)
        if self.read_status is ProjectionReadStatus.OK:
            if not self.offset_ref.strip():
                raise ObservabilityValueError("readable projection offset_ref is required")
            if any(len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest) for digest in digests):
                raise ObservabilityValueError(
                    "readable projection digests must be canonical SHA-256 hex"
                )
            expected_drift = (
                ProjectionDriftStatus.MATCH
                if self.active_source_digest == self.expected_source_digest
                else ProjectionDriftStatus.MISMATCH
            )
            if self.drift_status is not expected_drift:
                raise ObservabilityValueError("projection drift_status must match its digests")
        elif any(digests):
            raise ObservabilityValueError("failed projection reads cannot invent source digests")
        if self.read_status is ProjectionReadStatus.OK:
            if self.drift_status is ProjectionDriftStatus.UNKNOWN:
                raise ObservabilityValueError(
                    "observed projection signal cannot leave drift unknown"
                )
        elif self.drift_status is not ProjectionDriftStatus.UNKNOWN:
            raise ObservabilityValueError(
                "unavailable projection read cannot claim a drift verdict"
            )
        if self.read_status is ProjectionReadStatus.OK and self.status_detail:
            raise ObservabilityValueError("readable projection signal cannot carry status_detail")
        if (
            self.read_status is not ProjectionReadStatus.OK
            and not self.status_detail.strip()
        ):
            raise ObservabilityValueError("unavailable projection read requires status_detail")

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RuntimeHealthSnapshot:
    observed_at: datetime | str
    queue: QueueRuntimeSignal
    database: DatabaseRuntimeSignal
    provider: ProviderRuntimeSignal
    runtime_binding: RuntimeBindingSignal
    projection: ProjectionRuntimeSignal
    labels: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", parse_observed_at(self.observed_at))
        labels = {str(key).strip(): str(value).strip() for key, value in dict(self.labels or {}).items()}
        object.__setattr__(self, "labels", MappingProxyType(labels))

    def to_dict(self) -> dict[str, object]:
        return {
            "observed_at": self.observed_at.isoformat(),
            "queue": self.queue.to_dict(),
            "database": self.database.to_dict(),
            "provider": self.provider.to_dict(),
            "runtime_binding": self.runtime_binding.to_dict(),
            "projection": self.projection.to_dict(),
            "labels": dict(self.labels),
        }


def _namespace(mapping: Mapping[str, Any], *fields: str) -> Any:
    return type("RuntimeSourceRow", (), {field: mapping[field] for field in fields})()


def runtime_authority_read_signal_from_rows(
    *,
    scope: Any,
    step: Any,
    capability: Any,
    task_id: str | None,
) -> RuntimeAuthorityReadSignal:
    tenant_id = str(getattr(scope, "project_key", "") or "")
    expected_scope_digest = str(getattr(scope, "scope_digest", "") or "")
    expected_registry_revision = getattr(scope, "project_registry_revision", None)
    capability_id = str(getattr(capability, "capability_id", "") or "")
    step_id = str(getattr(step, "step_id", "") or "")
    claim_epoch = getattr(step, "claim_authority_epoch", None)
    expected_epoch = getattr(capability, "authority_epoch", None)

    mismatched: list[str] = []
    if not task_id:
        mismatched.append("task")
    if not tenant_id:
        mismatched.append("tenant")
    if str(getattr(step, "project_key", "") or "") != tenant_id:
        mismatched.append("tenant")
    if (
        str(getattr(step, "project_scope_digest", "") or "")
        != expected_scope_digest
        or getattr(step, "project_registry_revision", None)
        != expected_registry_revision
    ):
        mismatched.append("project_scope")
    if str(getattr(step, "capability_id", "") or "") != capability_id:
        mismatched.append("capability")
    if not step_id:
        mismatched.append("step")
    if claim_epoch != expected_epoch:
        mismatched.append("epoch")

    return RuntimeAuthorityReadSignal(
        source=AUTHORITY_READ_SOURCE,
        read_status=RuntimeAuthorityReadStatus.MISMATCH
        if mismatched
        else RuntimeAuthorityReadStatus.OBSERVED,
        task_id=task_id,
        tenant_id=tenant_id or None,
        project_scope_digest=expected_scope_digest or None,
        project_registry_revision=expected_registry_revision,
        capability_id=capability_id or None,
        step_id=step_id or None,
        claim_authority_epoch=claim_epoch,
        expected_project_scope_digest=expected_scope_digest or None,
        expected_project_registry_revision=expected_registry_revision,
        expected_claim_authority_epoch=expected_epoch,
        mismatch_fields=tuple(dict.fromkeys(mismatched)),
    )


def authority_not_observed(
    reason: str,
    *,
    task_id: str | None,
    tenant_id: str | None,
) -> RuntimeAuthorityReadSignal:
    return RuntimeAuthorityReadSignal(
        source=AUTHORITY_READ_SOURCE,
        read_status=RuntimeAuthorityReadStatus.NOT_OBSERVED,
        task_id=task_id,
        tenant_id=tenant_id,
        read_error=reason,
        not_observed_fields=(
            "task",
            "tenant",
            "project_scope",
            "capability",
            "step",
            "epoch",
        ),
    )


def read_runtime_authority_signal(engine: Engine) -> RuntimeAuthorityReadSignal:
    from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES

    scopes = PUBLIC_TABLES["project_scope_registry"]
    steps = PUBLIC_TABLES["runtime_step_authorizations"]
    capabilities = PUBLIC_TABLES["runtime_capability_authority"]
    selected = (
        scopes.c.project_key,
        scopes.c.registry_revision,
        scopes.c.scope_digest,
        steps.c.run_id,
        steps.c.step_id,
        steps.c.capability_id,
        steps.c.claim_authority_epoch,
        steps.c.project_registry_revision,
        steps.c.project_scope_digest,
        capabilities.c.authority_epoch,
    )
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                select(*selected)
                .select_from(steps)
                .join(
                    scopes,
                    (scopes.c.project_key == steps.c.project_key)
                    & (scopes.c.registry_revision == steps.c.project_registry_revision)
                    & (scopes.c.state == "ACTIVE"),
                )
                .join(
                    capabilities,
                    (capabilities.c.project_key == steps.c.project_key)
                    & (capabilities.c.capability_id == steps.c.capability_id),
                )
                .order_by(steps.c.updated_at.desc(), steps.c.authorization_id.desc())
                .limit(1)
            ).mappings().all()
    except Exception as exc:  # noqa: BLE001 - source reads become typed failures
        return authority_not_observed(
            f"runtime authority read failed: {type(exc).__name__}",
            task_id=None,
            tenant_id=None,
        )
    if not rows:
        return authority_not_observed(
            "task authority row is absent or ambiguous",
            task_id=None,
            tenant_id=None,
        )

    row = rows[0]
    scope = _namespace(
        row,
        "project_key",
        "scope_digest",
        "project_registry_revision",
    )
    step = _namespace(
        row,
        "project_key",
        "step_id",
        "capability_id",
        "claim_authority_epoch",
        "project_registry_revision",
        "project_scope_digest",
    )
    capability = _namespace(row, "capability_id", "authority_epoch")
    return runtime_authority_read_signal_from_rows(
        scope=scope,
        step=step,
        capability=capability,
        task_id=str(row["run_id"]),
    )


def read_runtime_projection_signal(engine: Engine) -> ProjectionRuntimeSignal:
    from app.successor_runtime.substrate.postgres.projection_sources import (
        PROJECT_SOURCE_KIND,
        PROJECT_SOURCE_IDENTITY_PROJECTOR_ID,
        PROJECT_SOURCE_IDENTITY_PROJECTOR_VERSION,
        load_exact_project_source_closure,
    )
    from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
    from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope

    offsets = PUBLIC_TABLES["runtime_projection_offsets"]
    scopes = PUBLIC_TABLES["project_scope_registry"]
    selected = (
        scopes.c.project_key.label("project_key"),
        scopes.c.registry_revision.label("registry_revision"),
        scopes.c.resolved_schema.label("resolved_schema"),
        scopes.c.incarnation.label("incarnation"),
        scopes.c.scope_digest.label("scope_digest"),
        offsets.c.projection_generation.label("projection_generation"),
        offsets.c.revision.label("revision"),
        offsets.c.source_revision.label("source_revision"),
        offsets.c.source_digest.label("source_digest"),
        offsets.c.offset_ref.label("offset_ref"),
    )
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                select(*selected)
                .select_from(offsets)
                .join(
                    scopes,
                    (scopes.c.project_key == offsets.c.project_key)
                    & (scopes.c.incarnation == offsets.c.source_incarnation)
                    & (scopes.c.state == "ACTIVE"),
                )
                .where(
                    offsets.c.projector_id == PROJECT_SOURCE_IDENTITY_PROJECTOR_ID,
                    offsets.c.projector_version == PROJECT_SOURCE_IDENTITY_PROJECTOR_VERSION,
                    offsets.c.source_kind == PROJECT_SOURCE_KIND,
                )
                .order_by(offsets.c.updated_at.desc(), offsets.c.revision.desc())
                .limit(1)
            ).mappings().all()
            if not rows:
                return ProjectionRuntimeSignal(
                    source=PROJECTION_SOURCE,
                    read_status=ProjectionReadStatus.NOT_OBSERVED,
                    drift_status=ProjectionDriftStatus.UNKNOWN,
                    active_source_digest="",
                    expected_source_digest="",
                    projection_generation=0,
                    offset_revision=0,
                    source_revision=0,
                    offset_ref="",
                    status_detail="active material projection offset missing",
                )

            row = rows[0]
            scope_ref = ProjectScopeRef(
                project_key=str(row["project_key"]),
                resolved_schema=str(row["resolved_schema"]),
                project_registry_revision=int(row["registry_revision"]),
                incarnation=str(row["incarnation"]),
                scope_digest=str(row["scope_digest"]),
            )
            runtime_scope = RuntimeScope(
                project_scope=scope_ref,
                actor_id="observability:runtime-health",
            )
            closure = load_exact_project_source_closure(connection, runtime_scope)
            active_digest = str(row["source_digest"])
            expected_digest = closure.closure_digest
            return ProjectionRuntimeSignal(
                source=PROJECTION_SOURCE,
                read_status=ProjectionReadStatus.OK,
                drift_status=ProjectionDriftStatus.MATCH
                if active_digest == expected_digest
                else ProjectionDriftStatus.MISMATCH,
                active_source_digest=active_digest,
                expected_source_digest=expected_digest,
                projection_generation=int(row["projection_generation"]),
                offset_revision=int(row["revision"]),
                source_revision=int(row["source_revision"]),
                offset_ref=str(row["offset_ref"]),
            )
    except Exception as exc:  # noqa: BLE001 - projection reads become typed failures
        return ProjectionRuntimeSignal(
            source=PROJECTION_SOURCE,
            read_status=ProjectionReadStatus.ERROR,
            drift_status=ProjectionDriftStatus.UNKNOWN,
            active_source_digest="",
            expected_source_digest="",
            projection_generation=0,
            offset_revision=0,
            source_revision=0,
            offset_ref="",
            status_detail=f"material projection source read failed: {type(exc).__name__}",
        )


def read_runtime_queue_signal(
    settings_obj: object,
    *,
    queue_name: str = "celery",
) -> QueueRuntimeSignal:
    try:
        import redis

        depth = int(
            redis.Redis.from_url(
                str(getattr(settings_obj, "redis_url", "") or "")
            ).llen(queue_name)
        )
    except Exception:  # noqa: BLE001 - queue reads become typed failures
        return QueueRuntimeSignal(
            source=f"redis.broker.llen:{queue_name}",
            read_status=QueueReadStatus.ERROR,
            depth=0,
        )
    return QueueRuntimeSignal(
        source=f"redis.broker.llen:{queue_name}",
        read_status=QueueReadStatus.OK,
        depth=depth,
    )


def read_runtime_provider_signal(
    settings_obj: object,
    *,
    production_runtime: bool,
) -> ProviderRuntimeSignal:
    simulated_failure = str(
        os.getenv("STAGE5_SIMULATE_PROVIDER_FAILURE", "")
    ).strip().lower()
    if simulated_failure in {"1", "true", "yes"}:
        return ProviderRuntimeSignal(
            source=PROVIDER_SOURCE,
            status=ProviderRuntimeStatus.SIMULATED_FAILURE,
            simulated=True,
        )
    return ProviderRuntimeSignal(
        source=PROVIDER_SOURCE,
        status=ProviderRuntimeStatus.UNSUPPORTED
        if production_runtime
        else ProviderRuntimeStatus.NOT_OBSERVED,
        simulated=False,
    )


def build_runtime_health_snapshot(
    *,
    database_connection_status: str,
    database_pool_status: str,
    pool_status: Mapping[str, object],
    runtime_status: Mapping[str, object],
    engine: Engine,
    settings_obj: object,
    release_version: str,
    production_runtime: bool,
    service_version: str | None = None,
) -> Annotated[
    RuntimeHealthSnapshot,
    "kit:non-authoritative derived_as=view fact_source=production.runtime-health.live-sources witness=test:test_deep_health_sources_build_typed_runtime_snapshot",
]:
    pool_values = dict(pool_status or {})
    pool_size = max(0, int(pool_values.get("size", 0) or 0))
    checked_out = max(0, int(pool_values.get("checkedout", 0) or 0))
    max_overflow = max(0, int(getattr(settings_obj, "db_pool_max_overflow", 0) or 0))
    authority_read = read_runtime_authority_signal(engine)
    authority_status = (
        RuntimeBindingStatus.MISMATCH
        if authority_read.read_status is RuntimeAuthorityReadStatus.MISMATCH
        else RuntimeBindingStatus.BOUND
        if authority_read.read_status is RuntimeAuthorityReadStatus.OBSERVED
        else RuntimeBindingStatus.UNKNOWN
    )
    return RuntimeHealthSnapshot(
        observed_at=datetime.now(timezone.utc),
        queue=read_runtime_queue_signal(settings_obj),
        database=DatabaseRuntimeSignal(
            source=DATABASE_SOURCE,
            connection_status=database_connection_status,
            pool_status=database_pool_status,
            pool_size=pool_size,
            checked_out=checked_out,
            pool_limit=pool_size + max_overflow,
        ),
        provider=read_runtime_provider_signal(
            settings_obj,
            production_runtime=production_runtime,
        ),
        runtime_binding=RuntimeBindingSignal(
            source="app.state.production_runtime_bindings+release_identity",
            authority_status=authority_status,
            projection_release_status=ProjectionReleaseStatus.MATCH
            if str(service_version or release_version) == release_version
            else ProjectionReleaseStatus.MISMATCH,
            authority_read=authority_read,
        ),
        projection=read_runtime_projection_signal(engine),
    )


__all__ = [
    "DatabaseRuntimeSignal",
    "ProjectionDriftStatus",
    "ProjectionReadStatus",
    "ProjectionReleaseStatus",
    "ProjectionRuntimeSignal",
    "ProviderRuntimeSignal",
    "ProviderRuntimeStatus",
    "QueueReadStatus",
    "QueueRuntimeSignal",
    "AUTHORITY_READ_SOURCE",
    "DATABASE_SOURCE",
    "PROJECTION_SOURCE",
    "PROVIDER_SOURCE",
    "authority_not_observed",
    "build_runtime_health_snapshot",
    "read_runtime_authority_signal",
    "read_runtime_provider_signal",
    "read_runtime_projection_signal",
    "read_runtime_queue_signal",
    "RuntimeBindingSignal",
    "RuntimeBindingStatus",
    "RuntimeAuthorityReadSignal",
    "RuntimeAuthorityReadStatus",
    "RuntimeHealthSnapshot",
]
