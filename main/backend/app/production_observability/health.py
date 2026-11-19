from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Annotated, Protocol, TypeGuard, TypeVar, runtime_checkable

from sqlalchemy import select
from sqlalchemy.engine import Engine

from .errors import ObservabilityTypeError, ObservabilityValueError
from .observations import parse_observed_at


AUTHORITY_READ_SOURCE = (
    "postgres.project_scope_registry+runtime_step_authorizations"
    "+runtime_capability_authority"
)
DATABASE_SOURCE = "sqlalchemy.engine:select_1+pool_status"
PROVIDER_SOURCE = "production.provider-runtime:unobserved"
_Type = TypeVar("_Type")


def _instance_of(value: object, expected_type: type[_Type]) -> TypeGuard[_Type]:
    return isinstance(value, expected_type)


def _nonnegative_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _runtime_int(value: object) -> int:
    if not _nonnegative_int(value):
        raise TypeError("runtime health count must be a non-negative integer")
    return value


def _config_int(value: object) -> int:
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        return max(0, int(value))
    return 0


@runtime_checkable
class SourceRow(Protocol):
    def __getitem__(self, key: str) -> object: ...


@runtime_checkable
class _ObjectIterable(Protocol):
    def __iter__(self) -> Iterator[object]: ...


class _RedisQueueClient:
    def __init__(self, client: object) -> None:
        self._client = client

    def llen(self, queue_name: str) -> object:
        method = getattr(self._client, "llen", None)
        if not callable(method):
            raise TypeError("Redis queue client does not expose llen")
        return method(queue_name)


def _empty_labels() -> dict[str, str]:
    return {}


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence)


def _label_items(value: object) -> Iterable[tuple[object, object]]:
    if value is None:
        return ()
    if _is_object_mapping(value):
        return value.items()
    if not isinstance(value, _ObjectIterable):
        raise ObservabilityTypeError(
            "runtime health labels must be a mapping, item pairs, or null"
        )
    items: list[tuple[object, object]] = []
    for item in value:
        if (
            isinstance(item, (str, bytes))
            or not _is_object_sequence(item)
            or len(item) != 2
        ):
            raise ObservabilityTypeError(
                "runtime health labels must contain key-value pairs"
            )
        items.append((item[0], item[1]))
    return tuple(items)


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
        if not _instance_of(self.read_status, QueueReadStatus):
            raise ObservabilityTypeError("queue read_status is closed")
        if not _nonnegative_int(self.depth):
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
        if any(not _nonnegative_int(value) for value in values):
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
        if not _instance_of(self.status, ProviderRuntimeStatus):
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
        if not _instance_of(self.authority_status, RuntimeBindingStatus):
            raise ObservabilityTypeError("runtime authority status is closed")
        if not _instance_of(self.projection_release_status, ProjectionReleaseStatus):
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
        if not _instance_of(self.read_status, RuntimeAuthorityReadStatus):
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
class RuntimeHealthSnapshot:
    observed_at: datetime | str
    queue: QueueRuntimeSignal
    database: DatabaseRuntimeSignal
    provider: ProviderRuntimeSignal
    runtime_binding: RuntimeBindingSignal
    labels: Mapping[str, str] = field(default_factory=_empty_labels)

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", parse_observed_at(self.observed_at))
        raw_labels: object = self.labels
        labels = {
            str(key).strip(): str(value).strip()
            for key, value in _label_items(raw_labels)
        }
        object.__setattr__(self, "labels", MappingProxyType(labels))

    def to_dict(self) -> dict[str, object]:
        return {
            "observed_at": parse_observed_at(self.observed_at).isoformat(),
            "queue": self.queue.to_dict(),
            "database": self.database.to_dict(),
            "provider": self.provider.to_dict(),
            "runtime_binding": self.runtime_binding.to_dict(),
            "labels": dict(self.labels),
        }


def _namespace(mapping: SourceRow, *fields: str) -> dict[str, object]:
    return {field: mapping[field] for field in fields}


def _row_value(row: object, field: str) -> object | None:
    if _is_object_mapping(row):
        return row.get(field)
    return getattr(row, field, None)


def runtime_authority_read_signal_from_rows(
    *,
    scope: object,
    step: object,
    capability: object,
    task_id: str | None,
) -> RuntimeAuthorityReadSignal:
    tenant_id = str(_row_value(scope, "project_key") or "")
    expected_scope_digest = str(_row_value(scope, "scope_digest") or "")
    raw_registry_revision = _row_value(scope, "project_registry_revision")
    expected_registry_revision = (
        _runtime_int(raw_registry_revision)
        if raw_registry_revision is not None
        else None
    )
    capability_id = str(_row_value(capability, "capability_id") or "")
    step_id = str(_row_value(step, "step_id") or "")
    raw_claim_epoch = _row_value(step, "claim_authority_epoch")
    claim_epoch = _runtime_int(raw_claim_epoch) if raw_claim_epoch is not None else None
    raw_expected_epoch = _row_value(capability, "authority_epoch")
    expected_epoch = (
        _runtime_int(raw_expected_epoch) if raw_expected_epoch is not None else None
    )

    mismatched: list[str] = []
    if not task_id:
        mismatched.append("task")
    if not tenant_id:
        mismatched.append("tenant")
    if str(_row_value(step, "project_key") or "") != tenant_id:
        mismatched.append("tenant")
    if (
        str(_row_value(step, "project_scope_digest") or "")
        != expected_scope_digest
        or _row_value(step, "project_registry_revision")
        != expected_registry_revision
    ):
        mismatched.append("project_scope")
    if str(_row_value(step, "capability_id") or "") != capability_id:
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


def read_runtime_queue_signal(
    settings_obj: object,
    *,
    queue_name: str = "celery",
) -> QueueRuntimeSignal:
    try:
        import redis

        factory: object = redis.Redis
        from_url = getattr(factory, "from_url", None)
        if not callable(from_url):
            raise TypeError("Redis client factory does not expose from_url")
        queue_client = _RedisQueueClient(
            from_url(str(getattr(settings_obj, "redis_url", "") or ""))
        )
        depth = _runtime_int(queue_client.llen(queue_name))
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
    pool_status: Mapping[str, object] | None,
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
    raw_pool_status: object = pool_status
    if raw_pool_status is None:
        pool_values: dict[object, object] = {}
    elif _is_object_mapping(raw_pool_status):
        pool_values = dict(raw_pool_status)
    else:
        raise ObservabilityTypeError("database pool status must be a mapping or null")
    pool_size = _config_int(pool_values.get("size", 0))
    checked_out = _config_int(pool_values.get("checkedout", 0))
    max_overflow = _config_int(getattr(settings_obj, "db_pool_max_overflow", 0))
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
    )


__all__ = [
    "DatabaseRuntimeSignal",
    "ProjectionReleaseStatus",
    "ProviderRuntimeSignal",
    "ProviderRuntimeStatus",
    "QueueReadStatus",
    "QueueRuntimeSignal",
    "AUTHORITY_READ_SOURCE",
    "DATABASE_SOURCE",
    "PROVIDER_SOURCE",
    "authority_not_observed",
    "build_runtime_health_snapshot",
    "read_runtime_authority_signal",
    "read_runtime_provider_signal",
    "read_runtime_queue_signal",
    "RuntimeBindingSignal",
    "RuntimeBindingStatus",
    "RuntimeAuthorityReadSignal",
    "RuntimeAuthorityReadStatus",
    "RuntimeHealthSnapshot",
]
