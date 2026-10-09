from __future__ import annotations

# ruff: noqa: TRY003

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, UTC
from types import MappingProxyType
from typing import Protocol, TypeGuard, runtime_checkable
from collections.abc import Iterable, Iterator, Mapping, Sequence

from .errors import ObservabilityTypeError, ObservabilityValueError
from .contracts import SOURCE_CONTRACT_VERSIONS
from .contracts import LabelBinding, MetricFamily


def _empty_labels() -> dict[str, str]:
    return {}


def _is_metric_family(value: object) -> TypeGuard[MetricFamily]:
    return isinstance(value, MetricFamily)


def _is_positive_int(value: object) -> TypeGuard[int]:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


@runtime_checkable
class _ObjectIterable(Protocol):
    def __iter__(self) -> Iterator[object]: ...


def _is_object_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence)


def _label_items(value: object) -> Iterable[tuple[object, object]]:
    if value is None:
        return ()
    if _is_object_mapping(value):
        return value.items()
    if not isinstance(value, _ObjectIterable):
        raise ObservabilityTypeError("labels must be a mapping, item pairs, or null")
    items: list[tuple[object, object]] = []
    for item in value:
        if (
            isinstance(item, (str, bytes))
            or not _is_object_sequence(item)
            or len(item) != 2
        ):
            raise ObservabilityTypeError("labels must contain key-value pairs")
        items.append((item[0], item[1]))
    return tuple(items)


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_observed_at(value: object) -> datetime:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise ObservabilityValueError("observed_at must be a datetime or ISO timestamp")
    if parsed.tzinfo is None:
        raise ObservabilityValueError("observed_at must be timezone-aware")
    return parsed.astimezone(UTC)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def observation_digest(observation: Observation) -> str:
    payload = {
        "contract_version": observation.contract_version,
        "observation_id": observation.observation_id,
        "observed_at": observation.observed_at.isoformat(),
        "source_contract_version": observation.source_contract_version,
        "metric_family": observation.metric_family.value,
        "domain": observation.domain,
        "route": observation.route,
        "release_version": observation.release_version,
        "value": observation.value,
        "sample_count": observation.sample_count,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Observation:
    observation_id: str
    observed_at: datetime
    source_contract_version: str
    metric_family: MetricFamily
    domain: str
    route: str
    release_version: str
    value: float
    sample_count: int
    contract_version: str = "production.observability.core.v1"
    labels: Mapping[str, str] = field(default_factory=_empty_labels)

    def __post_init__(self) -> None:
        raw_labels: object = self.labels
        labels = {
            str(key).strip(): str(value).strip()
            for key, value in _label_items(raw_labels)
        }
        binding = LabelBinding(self.domain, self.route, self.release_version).normalized()
        object.__setattr__(self, "labels", MappingProxyType(labels))
        object.__setattr__(self, "domain", binding.domain)
        object.__setattr__(self, "route", binding.route)
        object.__setattr__(self, "release_version", binding.release_version)
        object.__setattr__(self, "observed_at", parse_observed_at(self.observed_at))
        if not self.observation_id.strip():
            raise ObservabilityValueError("observation_id is required")
        if not self.source_contract_version.strip():
            raise ObservabilityValueError("source_contract_version is required")
        if self.source_contract_version not in SOURCE_CONTRACT_VERSIONS:
            raise ObservabilityValueError("source_contract_version must bind an existing canary contract")
        if not _is_metric_family(self.metric_family):
            raise ObservabilityTypeError("metric_family is closed")
        if not self.domain or not self.route or not self.release_version:
            raise ObservabilityValueError("domain, route, and release_version labels are required")
        if not math.isfinite(self.value) or self.value < 0 or self.value > 1:
            raise ObservabilityValueError("metric value must be a finite ratio in [0, 1]")
        if not _is_positive_int(self.sample_count):
            raise ObservabilityValueError("sample_count must be a positive integer")

    @property
    def digest(self) -> str:
        return observation_digest(self)

    @property
    def binding(self) -> LabelBinding:
        return LabelBinding(self.domain, self.route, self.release_version)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "observation_id": self.observation_id,
            "observed_at": self.observed_at.isoformat(),
            "source_contract_version": self.source_contract_version,
            "metric_family": self.metric_family.value,
            "domain": self.domain,
            "route": self.route,
            "release_version": self.release_version,
            "value": self.value,
            "sample_count": self.sample_count,
            "labels": dict(self.labels),
        }


def make_observation(
    *,
    observation_id: str,
    observed_at: datetime | str,
    source_contract_version: str,
    metric_family: MetricFamily | str,
    domain: str,
    route: str,
    release_version: str,
    value: float,
    sample_count: int,
    labels: Mapping[str, str] | None = None,
) -> Observation:
    family = metric_family if isinstance(metric_family, MetricFamily) else MetricFamily(metric_family)
    return Observation(
        observation_id=observation_id,
        observed_at=parse_observed_at(observed_at),
        source_contract_version=source_contract_version,
        metric_family=family,
        domain=domain,
        route=route,
        release_version=release_version,
        value=value,
        sample_count=sample_count,
        labels=dict(labels or {}),
    )


__all__ = ["Observation", "make_observation", "observation_digest", "parse_observed_at", "utc_now"]
