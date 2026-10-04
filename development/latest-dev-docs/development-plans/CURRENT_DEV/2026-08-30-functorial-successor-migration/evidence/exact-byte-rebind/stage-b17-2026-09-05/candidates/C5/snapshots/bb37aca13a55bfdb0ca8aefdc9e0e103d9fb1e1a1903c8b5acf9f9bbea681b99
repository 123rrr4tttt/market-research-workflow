"""Typed, non-authoritative offline observations of legacy process state.

The contracts here describe *what was observed* from Celery inspect,
``AsyncResult`` snapshots, ``EtlJobRun`` rows, or worker logs.  They never
infer a canonical run/step/attempt terminal fact: terminal-looking source
states stay bound to their source kind and observation class, and the join
projection must preserve contradiction, staleness, unavailability, and
unboundness explicitly.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from functorial_kit import Failure

from pydantic import Field, ValidationError, model_validator

from .assignments import Digest, FrozenContract, canonical_digest
from .failure_policy import raise_runtime_failure, runtime_failure


class LegacyObservationError(ValueError):
    """Invalid captured legacy evidence at the compatibility boundary."""


def _raise_legacy_observation_failure(message: object, *, site: str) -> None:
    """Preserve native validation errors while recording typed evidence."""

    failure: Failure = runtime_failure(
        "LEGACY_OBSERVATION_INVALID",
        message,
        LegacyObservationError,
        site=site,
    )
    # The pydantic validator wraps this ValueError into its native ValidationError.
    raise_runtime_failure(failure, LegacyObservationError)


class ObservationSourceKind(StrEnum):
    CELERY_INSPECT = "celery_inspect"
    CELERY_ASYNC_RESULT = "celery_async_result"
    ETL_JOB_RUN = "etl_job_run"
    PROCESS_LOG = "process_log"


class ObservationClass(StrEnum):
    OBSERVED = "OBSERVED"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    CONTRADICTORY = "CONTRADICTORY"
    UNBOUND = "UNBOUND"


class ObservationFreshness(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class LegacySourceObservation(FrozenContract):
    """One captured source observation with exact identity and digest."""

    schema_version: Literal["mrw.runtime.legacy-observation.v1"] = (
        "mrw.runtime.legacy-observation.v1"
    )
    source_kind: ObservationSourceKind
    source_locator: str = Field(min_length=1)
    source_identity: str = Field(min_length=1)
    observed_state: str | None = None
    observation_class: ObservationClass
    observed_at: datetime
    source_digest: Digest
    freshness: ObservationFreshness
    linked_run_id: str | None = None
    linked_step_id: str | None = None
    linked_attempt_id: Digest | None = None
    raw_evidence_ref: str | None = None
    reason: str | None = None
    terminal_authority_claim: None = None

    @model_validator(mode="after")
    def validate_observation(self) -> LegacySourceObservation:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            _raise_legacy_observation_failure(
                "legacy observation observed_at must be timezone-aware",
                site="runtime.observations.observed_at",
            )
        expected = canonical_digest(self, exclude_fields={"source_digest"})
        if self.source_digest != expected:
            _raise_legacy_observation_failure(
                "legacy observation source_digest mismatch",
                site="runtime.observations.source_digest",
            )
        if (
            self.observation_class is ObservationClass.OBSERVED
            and not self.observed_state
        ):
            _raise_legacy_observation_failure(
                "OBSERVED observation requires an observed_state",
                site="runtime.observations.observed_state",
            )
        if (
            self.observation_class is ObservationClass.CONTRADICTORY
            and self.reason is None
        ):
            _raise_legacy_observation_failure(
                "CONTRADICTORY observation requires a reason",
                site="runtime.observations.contradiction",
            )
        if self.terminal_authority_claim is not None:
            _raise_legacy_observation_failure(
                "legacy observations never claim terminal authority",
                site="runtime.observations.terminal_authority",
            )
        return self

    @classmethod
    def from_content(cls, **content: object) -> LegacySourceObservation:
        if "source_digest" in content:
            _raise_legacy_observation_failure(
                "source_digest is derived, not caller supplied",
                site="runtime.observations.from_content.source_digest",
            )
        provisional = cls.model_construct(**content, source_digest="0" * 64)
        return cls(
            **content,
            source_digest=canonical_digest(
                provisional,
                exclude_fields={"source_digest"},
            ),
        )


class LegacyObservationSet(FrozenContract):
    """Deterministically ordered captured set of legacy observations."""

    schema_version: Literal["mrw.runtime.legacy-observation-set.v1"] = (
        "mrw.runtime.legacy-observation-set.v1"
    )
    captured_at: datetime
    observations: tuple[LegacySourceObservation, ...]
    set_digest: Digest

    @model_validator(mode="after")
    def validate_set(self) -> LegacyObservationSet:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            _raise_legacy_observation_failure(
                "observation set captured_at must be timezone-aware",
                site="runtime.observations.set.captured_at",
            )
        identities = tuple(
            (item.source_kind.value, item.source_identity) for item in self.observations
        )
        if tuple(sorted(identities)) != identities:
            _raise_legacy_observation_failure(
                "observation set is not canonically ordered",
                site="runtime.observations.set.order",
            )
        if len(set(identities)) != len(identities):
            _raise_legacy_observation_failure(
                "observation set contains duplicate source identity",
                site="runtime.observations.set.identity",
            )
        expected = canonical_digest(self, exclude_fields={"set_digest"})
        if self.set_digest != expected:
            _raise_legacy_observation_failure(
                "observation set_digest mismatch",
                site="runtime.observations.set_digest",
            )
        return self

    @classmethod
    def from_content(cls, **content: object) -> LegacyObservationSet:
        if "set_digest" in content:
            _raise_legacy_observation_failure(
                "set_digest is derived, not caller supplied",
                site="runtime.observations.set.from_content.set_digest",
            )
        provisional = cls.model_construct(**content, set_digest="0" * 64)
        return cls(
            **content,
            set_digest=canonical_digest(
                provisional,
                exclude_fields={"set_digest"},
            ),
        )

    @classmethod
    def readback(cls, payload: object) -> LegacyObservationSet:
        """Read captured legacy evidence with the native Pydantic ABI."""

        return cls.model_validate(payload)

    @classmethod
    def readback_result(cls, payload: object) -> LegacyObservationSet | Failure:
        """Return captured evidence or a typed compatibility-boundary failure."""

        try:
            return cls.readback(payload)
        except ValidationError as exc:
            return runtime_failure(
                "LEGACY_OBSERVATION_INVALID",
                str(exc),
                LegacyObservationError,
                site="runtime.observations.set.readback",
            )


class ProcessTaskObservationJoin(FrozenContract):
    """Joined view of one task identity across captured sources."""

    schema_version: Literal["mrw.runtime.process-task-join.v1"] = (
        "mrw.runtime.process-task-join.v1"
    )
    task_id: str = Field(min_length=1)
    observation_class: ObservationClass
    status: str
    source_identities: tuple[str, ...]
    linked_run_id: str | None = None
    linked_step_id: str | None = None
    linked_attempt_id: Digest | None = None
    terminal_authority_claim: None = None
    reason: str | None = None


__all__ = [
    "LegacyObservationSet",
    "LegacyObservationError",
    "LegacySourceObservation",
    "ObservationClass",
    "ObservationFreshness",
    "ObservationSourceKind",
    "ProcessTaskObservationJoin",
]
