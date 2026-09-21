from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from collections.abc import Mapping

from .errors import ObservabilityTypeError, ObservabilityValueError
from .observations import parse_observed_at


class QueueReadStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class ProviderRuntimeStatus(StrEnum):
    SIMULATED_HEALTHY = "simulated_healthy"
    SIMULATED_FAILURE = "simulated_failure"


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
        if self.simulated is not True:
            raise ObservabilityValueError("runtime provider failure signal must be explicitly simulated")

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
    "RuntimeBindingSignal",
    "RuntimeBindingStatus",
    "RuntimeAuthorityReadSignal",
    "RuntimeAuthorityReadStatus",
    "RuntimeHealthSnapshot",
]
