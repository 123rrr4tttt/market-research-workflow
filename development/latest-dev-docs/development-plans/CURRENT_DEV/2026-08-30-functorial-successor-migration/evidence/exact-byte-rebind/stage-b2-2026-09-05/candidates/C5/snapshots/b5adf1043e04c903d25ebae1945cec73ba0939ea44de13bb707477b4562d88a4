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

from pydantic import Field, model_validator

from .assignments import Digest, FrozenContract, canonical_digest


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
            raise ValueError("legacy observation observed_at must be timezone-aware")
        expected = canonical_digest(self, exclude_fields={"source_digest"})
        if self.source_digest != expected:
            raise ValueError("legacy observation source_digest mismatch")
        if (
            self.observation_class is ObservationClass.OBSERVED
            and not self.observed_state
        ):
            raise ValueError("OBSERVED observation requires an observed_state")
        if (
            self.observation_class is ObservationClass.CONTRADICTORY
            and self.reason is None
        ):
            raise ValueError("CONTRADICTORY observation requires a reason")
        if self.terminal_authority_claim is not None:
            raise ValueError("legacy observations never claim terminal authority")
        return self

    @classmethod
    def from_content(cls, **content: object) -> LegacySourceObservation:
        if "source_digest" in content:
            raise ValueError("source_digest is derived, not caller supplied")
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
            raise ValueError("observation set captured_at must be timezone-aware")
        identities = tuple(
            (item.source_kind.value, item.source_identity) for item in self.observations
        )
        if tuple(sorted(identities)) != identities:
            raise ValueError("observation set is not canonically ordered")
        if len(set(identities)) != len(identities):
            raise ValueError("observation set contains duplicate source identity")
        expected = canonical_digest(self, exclude_fields={"set_digest"})
        if self.set_digest != expected:
            raise ValueError("observation set_digest mismatch")
        return self

    @classmethod
    def from_content(cls, **content: object) -> LegacyObservationSet:
        if "set_digest" in content:
            raise ValueError("set_digest is derived, not caller supplied")
        provisional = cls.model_construct(**content, set_digest="0" * 64)
        return cls(
            **content,
            set_digest=canonical_digest(
                provisional,
                exclude_fields={"set_digest"},
            ),
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
    "LegacySourceObservation",
    "ObservationClass",
    "ObservationFreshness",
    "ObservationSourceKind",
    "ProcessTaskObservationJoin",
]
