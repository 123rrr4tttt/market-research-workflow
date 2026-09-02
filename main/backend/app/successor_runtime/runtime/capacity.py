"""Pure contract for bounded successor-runtime capacity observations.

``CapacityEnvelope.v1`` is evidence about one measured workload and one exact
runtime/database identity.  It is deliberately not a promise about production
throughput.  Every required but unmeasured field carries the literal
``UNSUPPORTED_CAPACITY`` marker and is named in ``unsupported_capacity``.

This module performs no I/O.  PostgreSQL observation and artifact publication
live at interpreter boundaries in ``substrate.postgres.capacity`` and the
capacity generator respectively.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Final

from app.successor_runtime.research.codec import canonical_bytes, sha256_hex
from app.successor_runtime.runtime.resources import FairSharePolicy

CAPACITY_ENVELOPE_SCHEMA_VERSION: Final = "CapacityEnvelope.v1"
BOUNDED_TWO_NODE_SCOPE: Final = "BOUNDED_LOCAL_TWO_NODE_BASELINE"
UNSUPPORTED_CAPACITY: Final = "UNSUPPORTED_CAPACITY"
CAPACITY_FAIR_SHARE_POLICY: Final = FairSharePolicy()


def fair_share_policy_payload(policy: FairSharePolicy) -> dict[str, int]:
    """Return the exact JSON policy parameters bound by capacity evidence."""

    return {str(name): int(value) for name, value in asdict(policy).items()}


def fair_share_policy_digest(policy: FairSharePolicy) -> str:
    """Digest the policy type and all selection-relevant parameters."""

    return sha256_hex(
        {
            "policy_type": type(policy).__name__,
            "parameters": fair_share_policy_payload(policy),
        }
    )


class CapacityContractError(ValueError):
    """Raised when capacity evidence is incomplete or internally inconsistent."""


def nearest_rank(samples: Iterable[float], percentile: float) -> float:
    """Return the nearest-rank percentile for finite, non-negative samples.

    The rank is ``ceil(percentile / 100 * n)`` with percentile zero selecting
    the minimum.  This definition is intentionally explicit so measurement
    artifacts do not silently change with a statistics-library upgrade.
    """

    if isinstance(percentile, bool) or not isinstance(percentile, (int, float)):
        raise CapacityContractError("percentile must be a number between 0 and 100")
    if not math.isfinite(float(percentile)) or not 0 <= float(percentile) <= 100:
        raise CapacityContractError("percentile must be between 0 and 100")
    ordered = sorted(float(sample) for sample in samples)
    if not ordered:
        raise CapacityContractError("nearest-rank requires at least one sample")
    if any(not math.isfinite(sample) or sample < 0 for sample in ordered):
        raise CapacityContractError(
            "capacity latency samples must be finite and non-negative"
        )
    if float(percentile) == 0:
        return ordered[0]
    rank = math.ceil(float(percentile) / 100 * len(ordered))
    return ordered[rank - 1]


@dataclass(frozen=True, slots=True)
class LatencyPercentiles:
    """Nearest-rank latency summary in milliseconds."""

    sample_count: int
    minimum_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    maximum_ms: float

    def __post_init__(self) -> None:
        values = (
            self.minimum_ms,
            self.p50_ms,
            self.p95_ms,
            self.p99_ms,
            self.maximum_ms,
        )
        if self.sample_count <= 0:
            raise CapacityContractError("latency summary requires samples")
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise CapacityContractError("latencies must be finite and non-negative")
        if tuple(sorted(values)) != values:
            raise CapacityContractError("latency percentiles must be monotone")

    @classmethod
    def from_samples(cls, samples: Iterable[float]) -> LatencyPercentiles:
        values = tuple(float(sample) for sample in samples)
        if not values:
            raise CapacityContractError("latency summary requires samples")
        return cls(
            sample_count=len(values),
            minimum_ms=min(values),
            p50_ms=nearest_rank(values, 50),
            p95_ms=nearest_rank(values, 95),
            p99_ms=nearest_rank(values, 99),
            maximum_ms=max(values),
        )

    def as_payload(self) -> dict[str, int | float]:
        return {
            "sample_count": self.sample_count,
            "minimum_ms": self.minimum_ms,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "maximum_ms": self.maximum_ms,
        }


@dataclass(frozen=True, slots=True)
class LockObservation:
    """Point-in-time PostgreSQL lock census for the measured database."""

    total_locks: int
    ungranted_locks: int
    lock_waiting_connections: int

    def __post_init__(self) -> None:
        if (
            min(
                self.total_locks,
                self.ungranted_locks,
                self.lock_waiting_connections,
            )
            < 0
        ):
            raise CapacityContractError("lock observations cannot be negative")
        if self.ungranted_locks > self.total_locks:
            raise CapacityContractError("ungranted locks cannot exceed total locks")

    def as_payload(self) -> dict[str, int]:
        return {
            "total_locks": self.total_locks,
            "ungranted_locks": self.ungranted_locks,
            "lock_waiting_connections": self.lock_waiting_connections,
        }


@dataclass(frozen=True, slots=True)
class ConnectionObservation:
    """Point-in-time PostgreSQL connection census for the measured database."""

    database_connections: int
    active_connections: int
    idle_in_transaction_connections: int
    max_connections_setting: int

    def __post_init__(self) -> None:
        values = (
            self.database_connections,
            self.active_connections,
            self.idle_in_transaction_connections,
            self.max_connections_setting,
        )
        if min(values) < 0 or self.max_connections_setting == 0:
            raise CapacityContractError("connection observations are invalid")
        if self.active_connections > self.database_connections:
            raise CapacityContractError(
                "active connections cannot exceed database connections"
            )
        if self.idle_in_transaction_connections > self.database_connections:
            raise CapacityContractError(
                "idle-in-transaction connections cannot exceed database connections"
            )

    def as_payload(self) -> dict[str, int]:
        return {
            "database_connections": self.database_connections,
            "active_connections": self.active_connections,
            "idle_in_transaction_connections": (self.idle_in_transaction_connections),
            "max_connections_setting": self.max_connections_setting,
        }


CapacityMetric = int | float | str


def _require_metric(value: CapacityMetric, name: str) -> None:
    if value == UNSUPPORTED_CAPACITY:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CapacityContractError(
            f"{name} must be non-negative or {UNSUPPORTED_CAPACITY}"
        )
    if not math.isfinite(float(value)) or value < 0:
        raise CapacityContractError(
            f"{name} must be non-negative or {UNSUPPORTED_CAPACITY}"
        )


@dataclass(frozen=True, slots=True)
class CapacityEnvelope:
    """Digest-bound evidence for one exact bounded capacity measurement."""

    schema_version: str
    measurement_scope: str
    observed_at: datetime
    database_name: str
    database_role: str
    database_transport: str
    postgres_version: str
    postgres_settings: Mapping[str, str]
    node_ids: tuple[str, ...]
    node_profile_digests: tuple[str, ...]
    fair_share_policy_digest: str
    fair_share_policy_parameters: Mapping[str, int]
    project_count: int
    capability_count: int
    eligible_row_count: int
    initial_eligible_ids_digest: str
    observed_claimed_ids_digest: str
    observed_claimed_count: int
    observed_project_claim_counts: Mapping[str, int]
    observed_capability_claim_counts: Mapping[str, int]
    analytical_max_selection_rounds: int
    analytical_starvation_bound_seconds: float
    measured_max_selection_round: int
    measured_max_selection_seconds: float
    violations: int
    work_item_table_before_digest: str
    work_item_table_after_digest: str
    work_item_table_unchanged: bool
    terminal_row_count: int
    claim_batch_size: int
    work_item_rate_per_second: CapacityMetric
    concurrency: int
    claim_latency_ms: LatencyPercentiles
    commit_latency_ms: LatencyPercentiles
    lock_wait_ms: CapacityMetric
    lock_observation: LockObservation
    connection_observation: ConnectionObservation
    backlog_age_seconds: CapacityMetric
    max_starvation_seconds: CapacityMetric
    vacuum_policy: str
    partition_policy: str
    archive_policy: str
    unsupported_capacity: tuple[str, ...]
    measurement_notes: tuple[str, ...]
    envelope_digest: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != CAPACITY_ENVELOPE_SCHEMA_VERSION:
            raise CapacityContractError(
                f"schema_version must be {CAPACITY_ENVELOPE_SCHEMA_VERSION}"
            )
        if self.measurement_scope != BOUNDED_TWO_NODE_SCOPE:
            raise CapacityContractError(
                f"measurement_scope must be {BOUNDED_TWO_NODE_SCOPE}"
            )
        if self.observed_at.tzinfo is None:
            raise CapacityContractError("observed_at must be timezone-aware")
        object.__setattr__(
            self,
            "observed_at",
            self.observed_at.astimezone(timezone.utc),
        )
        for name in (
            "database_name",
            "database_role",
            "database_transport",
            "postgres_version",
            "vacuum_policy",
            "partition_policy",
            "archive_policy",
        ):
            if not getattr(self, name):
                raise CapacityContractError(f"{name} must be non-empty")
        if self.database_transport != "unix_socket":
            raise CapacityContractError(
                "bounded capacity evidence requires unix_socket"
            )
        frozen_settings = MappingProxyType(
            {
                str(key): str(value)
                for key, value in sorted(self.postgres_settings.items())
            }
        )
        if not frozen_settings:
            raise CapacityContractError("postgres_settings must be measured")
        object.__setattr__(self, "postgres_settings", frozen_settings)
        object.__setattr__(self, "node_ids", tuple(self.node_ids))
        object.__setattr__(
            self,
            "node_profile_digests",
            tuple(self.node_profile_digests),
        )
        policy_parameters = MappingProxyType(
            {
                str(key): int(value)
                for key, value in sorted(self.fair_share_policy_parameters.items())
            }
        )
        project_claim_counts = MappingProxyType(
            {
                str(key): int(value)
                for key, value in sorted(self.observed_project_claim_counts.items())
            }
        )
        capability_claim_counts = MappingProxyType(
            {
                str(key): int(value)
                for key, value in sorted(self.observed_capability_claim_counts.items())
            }
        )
        object.__setattr__(self, "fair_share_policy_parameters", policy_parameters)
        object.__setattr__(self, "observed_project_claim_counts", project_claim_counts)
        object.__setattr__(
            self, "observed_capability_claim_counts", capability_claim_counts
        )
        object.__setattr__(
            self,
            "unsupported_capacity",
            tuple(sorted(set(self.unsupported_capacity))),
        )
        object.__setattr__(self, "measurement_notes", tuple(self.measurement_notes))
        if len(self.node_ids) != 2 or len(set(self.node_ids)) != 2:
            raise CapacityContractError(
                "bounded baseline requires exactly two distinct RuntimeNode identities"
            )
        if len(self.node_profile_digests) != 1:
            raise CapacityContractError(
                "two-node baseline requires one exact homologous node profile"
            )
        if (
            min(
                self.project_count,
                self.capability_count,
                self.eligible_row_count,
                self.observed_claimed_count,
                self.terminal_row_count,
                self.analytical_max_selection_rounds,
                self.measured_max_selection_round,
                self.violations,
            )
            < 0
        ):
            raise CapacityContractError("row and project census cannot be negative")
        if min(self.project_count, self.capability_count, self.eligible_row_count) == 0:
            raise CapacityContractError(
                "two-node baseline requires a non-empty project/capability workload"
            )
        if self.claim_batch_size <= 0 or self.concurrency != 2:
            raise CapacityContractError(
                "two-node baseline requires positive claim batch and concurrency=2"
            )
        for name in (
            "work_item_rate_per_second",
            "lock_wait_ms",
            "backlog_age_seconds",
            "max_starvation_seconds",
        ):
            _require_metric(getattr(self, name), name)
        for name in (
            "fair_share_policy_digest",
            "initial_eligible_ids_digest",
            "observed_claimed_ids_digest",
            "work_item_table_before_digest",
            "work_item_table_after_digest",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
            ):
                raise CapacityContractError(f"{name} must be a SHA-256 digest")
        if not policy_parameters or any(
            value < 0 for value in policy_parameters.values()
        ):
            raise CapacityContractError("fair-share policy parameters are invalid")
        expected_policy_digest = sha256_hex(
            {"policy_type": "FairSharePolicy", "parameters": dict(policy_parameters)}
        )
        if dict(policy_parameters) != fair_share_policy_payload(
            CAPACITY_FAIR_SHARE_POLICY
        ):
            raise CapacityContractError(
                "capacity evidence must bind the frozen FairSharePolicy"
            )
        if self.fair_share_policy_digest != expected_policy_digest:
            raise CapacityContractError("fair-share policy digest mismatch")
        if self.observed_claimed_count != self.eligible_row_count:
            raise CapacityContractError(
                "observed claimed count must cover the initial eligible set"
            )
        if self.initial_eligible_ids_digest != self.observed_claimed_ids_digest:
            raise CapacityContractError(
                "observed claimed IDs must exactly equal the initial eligible IDs"
            )
        if (
            len(project_claim_counts) != self.project_count
            or sum(project_claim_counts.values()) != self.observed_claimed_count
            or min(project_claim_counts.values(), default=0) <= 0
        ):
            raise CapacityContractError(
                "project claim counts do not cover the workload"
            )
        if (
            len(capability_claim_counts) != self.capability_count
            or sum(capability_claim_counts.values()) != self.observed_claimed_count
            or min(capability_claim_counts.values(), default=0) <= 0
        ):
            raise CapacityContractError(
                "capability claim counts do not cover the workload"
            )
        for name in (
            "analytical_starvation_bound_seconds",
            "measured_max_selection_seconds",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise CapacityContractError(f"{name} must be finite and non-negative")
        if self.analytical_max_selection_rounds <= 0:
            raise CapacityContractError("analytical selection rounds must be positive")
        if (
            not 1
            <= self.measured_max_selection_round
            <= self.analytical_max_selection_rounds
        ):
            raise CapacityContractError(
                "measured selection round exceeds analytical bound"
            )
        if self.max_starvation_seconds != self.analytical_starvation_bound_seconds:
            raise CapacityContractError(
                "max_starvation_seconds must be derived from the analytical bound"
            )
        if (
            self.measured_max_selection_seconds
            > self.analytical_starvation_bound_seconds
        ):
            raise CapacityContractError(
                "measured selection time exceeds starvation bound"
            )
        if self.violations != 0:
            raise CapacityContractError("capacity evidence requires violations=0")
        if (
            not self.work_item_table_unchanged
            or self.work_item_table_before_digest != self.work_item_table_after_digest
        ):
            raise CapacityContractError(
                "rollback-only observation must leave runtime_work_items unchanged"
            )
        unsupported_fields = {
            name
            for name in (
                "work_item_rate_per_second",
                "lock_wait_ms",
                "backlog_age_seconds",
                "max_starvation_seconds",
                "vacuum_policy",
                "partition_policy",
                "archive_policy",
            )
            if getattr(self, name) == UNSUPPORTED_CAPACITY
        }
        declared = set(self.unsupported_capacity)
        if unsupported_fields != declared:
            raise CapacityContractError(
                "unsupported_capacity must exactly name every required field marked "
                f"{UNSUPPORTED_CAPACITY}; observed {sorted(declared)}, "
                f"expected {sorted(unsupported_fields)}"
            )
        expected = self.compute_digest()
        if self.envelope_digest is None:
            object.__setattr__(self, "envelope_digest", expected)
        elif self.envelope_digest != expected:
            raise CapacityContractError("CapacityEnvelope envelope_digest mismatch")

    @property
    def envelope_ref(self) -> str:
        return f"capacity-envelope:sha256:{self.envelope_digest}"

    @property
    def node_count(self) -> int:
        return len(self.node_ids)

    @property
    def node_profile_count(self) -> int:
        return len(self.node_profile_digests)

    def as_payload(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "measurement_scope": self.measurement_scope,
            "observed_at": self.observed_at,
            "database_name": self.database_name,
            "database_role": self.database_role,
            "database_transport": self.database_transport,
            "postgres_version": self.postgres_version,
            "postgres_settings": dict(self.postgres_settings),
            "node_count": self.node_count,
            "node_ids": list(self.node_ids),
            "node_profile_count": self.node_profile_count,
            "node_profile_digests": list(self.node_profile_digests),
            "fair_share_policy_digest": self.fair_share_policy_digest,
            "fair_share_policy_parameters": dict(self.fair_share_policy_parameters),
            "project_count": self.project_count,
            "capability_count": self.capability_count,
            "eligible_row_count": self.eligible_row_count,
            "initial_eligible_ids_digest": self.initial_eligible_ids_digest,
            "observed_claimed_ids_digest": self.observed_claimed_ids_digest,
            "observed_claimed_count": self.observed_claimed_count,
            "observed_project_claim_counts": dict(self.observed_project_claim_counts),
            "observed_capability_claim_counts": dict(
                self.observed_capability_claim_counts
            ),
            "analytical_max_selection_rounds": self.analytical_max_selection_rounds,
            "analytical_starvation_bound_seconds": (
                self.analytical_starvation_bound_seconds
            ),
            "measured_max_selection_round": self.measured_max_selection_round,
            "measured_max_selection_seconds": self.measured_max_selection_seconds,
            "violations": self.violations,
            "work_item_table_before_digest": self.work_item_table_before_digest,
            "work_item_table_after_digest": self.work_item_table_after_digest,
            "work_item_table_unchanged": self.work_item_table_unchanged,
            "terminal_row_count": self.terminal_row_count,
            "claim_batch_size": self.claim_batch_size,
            "work_item_rate_per_second": self.work_item_rate_per_second,
            "concurrency": self.concurrency,
            "claim_latency_ms": self.claim_latency_ms.as_payload(),
            "commit_latency_ms": self.commit_latency_ms.as_payload(),
            "lock_wait_ms": self.lock_wait_ms,
            "lock_observation": self.lock_observation.as_payload(),
            "connection_observation": self.connection_observation.as_payload(),
            "backlog_age_seconds": self.backlog_age_seconds,
            "max_starvation_seconds": self.max_starvation_seconds,
            "vacuum_policy": self.vacuum_policy,
            "partition_policy": self.partition_policy,
            "archive_policy": self.archive_policy,
            "unsupported_capacity": list(self.unsupported_capacity),
            "measurement_notes": list(self.measurement_notes),
        }
        if include_digest:
            payload["envelope_digest"] = self.envelope_digest
        return payload

    def compute_digest(self) -> str:
        return sha256_hex(self.as_payload(include_digest=False))

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.as_payload())


def capacity_envelope_json_schema() -> dict[str, Any]:
    """Return the closed JSON Schema for serialized ``CapacityEnvelope.v1``."""

    metric = {
        "oneOf": [
            {"type": "number", "minimum": 0},
            {"const": UNSUPPORTED_CAPACITY},
        ]
    }
    latency = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "sample_count",
            "minimum_ms",
            "p50_ms",
            "p95_ms",
            "p99_ms",
            "maximum_ms",
        ],
        "properties": {
            "sample_count": {"type": "integer", "minimum": 1},
            "minimum_ms": {"type": "number", "minimum": 0},
            "p50_ms": {"type": "number", "minimum": 0},
            "p95_ms": {"type": "number", "minimum": 0},
            "p99_ms": {"type": "number", "minimum": 0},
            "maximum_ms": {"type": "number", "minimum": 0},
        },
    }
    properties: dict[str, Any] = {
        "schema_version": {"const": CAPACITY_ENVELOPE_SCHEMA_VERSION},
        "measurement_scope": {"const": BOUNDED_TWO_NODE_SCOPE},
        "observed_at": {"type": "string", "format": "date-time"},
        "database_name": {"type": "string", "minLength": 1},
        "database_role": {"type": "string", "minLength": 1},
        "database_transport": {"const": "unix_socket"},
        "postgres_version": {"type": "string", "minLength": 1},
        "postgres_settings": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {"type": "string"},
        },
        "node_count": {"const": 2},
        "node_ids": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "node_profile_count": {"const": 1},
        "node_profile_digests": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1,
            "items": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        },
        "fair_share_policy_digest": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "fair_share_policy_parameters": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {"type": "integer", "minimum": 0},
        },
        "project_count": {"type": "integer", "minimum": 1},
        "capability_count": {"type": "integer", "minimum": 1},
        "eligible_row_count": {"type": "integer", "minimum": 1},
        "initial_eligible_ids_digest": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "observed_claimed_ids_digest": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "observed_claimed_count": {"type": "integer", "minimum": 1},
        "observed_project_claim_counts": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {"type": "integer", "minimum": 1},
        },
        "observed_capability_claim_counts": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {"type": "integer", "minimum": 1},
        },
        "analytical_max_selection_rounds": {"type": "integer", "minimum": 1},
        "analytical_starvation_bound_seconds": {"type": "number", "minimum": 0},
        "measured_max_selection_round": {"type": "integer", "minimum": 1},
        "measured_max_selection_seconds": {"type": "number", "minimum": 0},
        "violations": {"const": 0},
        "work_item_table_before_digest": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "work_item_table_after_digest": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "work_item_table_unchanged": {"const": True},
        "terminal_row_count": {"type": "integer", "minimum": 0},
        "claim_batch_size": {"type": "integer", "minimum": 1},
        "work_item_rate_per_second": metric,
        "concurrency": {"const": 2},
        "claim_latency_ms": latency,
        "commit_latency_ms": latency,
        "lock_wait_ms": metric,
        "lock_observation": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "total_locks",
                "ungranted_locks",
                "lock_waiting_connections",
            ],
            "properties": {
                "total_locks": {"type": "integer", "minimum": 0},
                "ungranted_locks": {"type": "integer", "minimum": 0},
                "lock_waiting_connections": {"type": "integer", "minimum": 0},
            },
        },
        "connection_observation": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "database_connections",
                "active_connections",
                "idle_in_transaction_connections",
                "max_connections_setting",
            ],
            "properties": {
                "database_connections": {"type": "integer", "minimum": 0},
                "active_connections": {"type": "integer", "minimum": 0},
                "idle_in_transaction_connections": {
                    "type": "integer",
                    "minimum": 0,
                },
                "max_connections_setting": {"type": "integer", "minimum": 1},
            },
        },
        "backlog_age_seconds": metric,
        "max_starvation_seconds": metric,
        "vacuum_policy": {"type": "string", "minLength": 1},
        "partition_policy": {"type": "string", "minLength": 1},
        "archive_policy": {"type": "string", "minLength": 1},
        "unsupported_capacity": {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "measurement_notes": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "envelope_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:mrw:successor:CapacityEnvelope.v1",
        "title": CAPACITY_ENVELOPE_SCHEMA_VERSION,
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


def build_capacity_envelope(
    *,
    observed_at: datetime,
    database_name: str,
    database_role: str,
    postgres_version: str,
    postgres_settings: Mapping[str, str],
    node_ids: Sequence[str],
    node_profile_digests: Sequence[str],
    fair_share_policy_digest: str,
    fair_share_policy_parameters: Mapping[str, int],
    project_count: int,
    capability_count: int,
    eligible_row_count: int,
    initial_eligible_ids_digest: str,
    observed_claimed_ids_digest: str,
    observed_claimed_count: int,
    observed_project_claim_counts: Mapping[str, int],
    observed_capability_claim_counts: Mapping[str, int],
    analytical_max_selection_rounds: int,
    analytical_starvation_bound_seconds: float,
    measured_max_selection_round: int,
    measured_max_selection_seconds: float,
    violations: int,
    work_item_table_before_digest: str,
    work_item_table_after_digest: str,
    work_item_table_unchanged: bool,
    terminal_row_count: int,
    claim_batch_size: int,
    work_item_rate_per_second: CapacityMetric,
    claim_latency_samples_ms: Iterable[float],
    commit_latency_samples_ms: Iterable[float],
    lock_wait_ms: CapacityMetric,
    lock_observation: LockObservation,
    connection_observation: ConnectionObservation,
    backlog_age_seconds: CapacityMetric,
    max_starvation_seconds: CapacityMetric,
    vacuum_policy: str,
    partition_policy: str,
    archive_policy: str,
    measurement_notes: Sequence[str] = (),
) -> CapacityEnvelope:
    """Build one exact two-node envelope and derive unsupported-field names."""

    required_values = {
        "work_item_rate_per_second": work_item_rate_per_second,
        "lock_wait_ms": lock_wait_ms,
        "backlog_age_seconds": backlog_age_seconds,
        "max_starvation_seconds": max_starvation_seconds,
        "vacuum_policy": vacuum_policy,
        "partition_policy": partition_policy,
        "archive_policy": archive_policy,
    }
    unsupported = tuple(
        name for name, value in required_values.items() if value == UNSUPPORTED_CAPACITY
    )
    return CapacityEnvelope(
        schema_version=CAPACITY_ENVELOPE_SCHEMA_VERSION,
        measurement_scope=BOUNDED_TWO_NODE_SCOPE,
        observed_at=observed_at,
        database_name=database_name,
        database_role=database_role,
        database_transport="unix_socket",
        postgres_version=postgres_version,
        postgres_settings=postgres_settings,
        node_ids=tuple(node_ids),
        node_profile_digests=tuple(node_profile_digests),
        fair_share_policy_digest=fair_share_policy_digest,
        fair_share_policy_parameters=fair_share_policy_parameters,
        project_count=project_count,
        capability_count=capability_count,
        eligible_row_count=eligible_row_count,
        initial_eligible_ids_digest=initial_eligible_ids_digest,
        observed_claimed_ids_digest=observed_claimed_ids_digest,
        observed_claimed_count=observed_claimed_count,
        observed_project_claim_counts=observed_project_claim_counts,
        observed_capability_claim_counts=observed_capability_claim_counts,
        analytical_max_selection_rounds=analytical_max_selection_rounds,
        analytical_starvation_bound_seconds=analytical_starvation_bound_seconds,
        measured_max_selection_round=measured_max_selection_round,
        measured_max_selection_seconds=measured_max_selection_seconds,
        violations=violations,
        work_item_table_before_digest=work_item_table_before_digest,
        work_item_table_after_digest=work_item_table_after_digest,
        work_item_table_unchanged=work_item_table_unchanged,
        terminal_row_count=terminal_row_count,
        claim_batch_size=claim_batch_size,
        work_item_rate_per_second=work_item_rate_per_second,
        concurrency=2,
        claim_latency_ms=LatencyPercentiles.from_samples(claim_latency_samples_ms),
        commit_latency_ms=LatencyPercentiles.from_samples(commit_latency_samples_ms),
        lock_wait_ms=lock_wait_ms,
        lock_observation=lock_observation,
        connection_observation=connection_observation,
        backlog_age_seconds=backlog_age_seconds,
        max_starvation_seconds=max_starvation_seconds,
        vacuum_policy=vacuum_policy,
        partition_policy=partition_policy,
        archive_policy=archive_policy,
        unsupported_capacity=unsupported,
        measurement_notes=tuple(measurement_notes),
    )


__all__ = [
    "BOUNDED_TWO_NODE_SCOPE",
    "CAPACITY_ENVELOPE_SCHEMA_VERSION",
    "CAPACITY_FAIR_SHARE_POLICY",
    "UNSUPPORTED_CAPACITY",
    "CapacityContractError",
    "CapacityEnvelope",
    "ConnectionObservation",
    "LatencyPercentiles",
    "LockObservation",
    "build_capacity_envelope",
    "capacity_envelope_json_schema",
    "fair_share_policy_digest",
    "fair_share_policy_payload",
    "nearest_rank",
]
