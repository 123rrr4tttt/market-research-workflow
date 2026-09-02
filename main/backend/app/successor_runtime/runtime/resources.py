"""Pure claim-time resource and fair-share contracts.

Qualification produces :class:`QueueEligibility`; it never consumes capacity.
An :class:`ExecutionReservation` is created only by the PostgreSQL claim
transaction for an effect-bearing assignment.  The helpers in this module are
deterministic and effect free so the live adapter and simulations can share the
same observable policy without pretending their database effects commute.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from .assignments import AssignmentKind, require_digest


class ResourceClass(StrEnum):
    CPU_LIGHT = "CPU_LIGHT"
    CPU_HEAVY = "CPU_HEAVY"
    NETWORK_IO = "NETWORK_IO"
    DB_WRITE = "DB_WRITE"
    LLM_CALL = "LLM_CALL"
    CRAWLER_JOB = "CRAWLER_JOB"
    EXTERNAL_PROCESS = "EXTERNAL_PROCESS"


EFFECT_ASSIGNMENT_KINDS = frozenset(
    {AssignmentKind.INTERPRET, AssignmentKind.VERIFY_ADMIT}
)


def assignment_requires_reservation(kind: AssignmentKind | str) -> bool:
    """Return whether claim must atomically reserve execution capacity.

    In particular, ``QUALIFY`` only establishes queue eligibility and must not
    reserve capacity early.
    """

    try:
        normalized = AssignmentKind(kind)
    except ValueError:
        return False
    return normalized in EFFECT_ASSIGNMENT_KINDS


@dataclass(frozen=True, slots=True)
class QueueEligibility:
    """Non-exclusive resource requirement attached during qualification."""

    project_key: str
    capability_id: str
    resource_class: ResourceClass
    units: int
    policy_epoch: int
    policy_digest: str
    concurrency_key: str | None = None
    provider_key: str | None = None

    def __post_init__(self) -> None:
        if not self.project_key or not self.capability_id:
            raise ValueError("queue eligibility requires project and capability")
        if self.units <= 0:
            raise ValueError("queue eligibility units must be positive")
        if self.policy_epoch < 0:
            raise ValueError("queue eligibility policy_epoch must be >= 0")
        require_digest(self.policy_digest, "policy_digest")

    @property
    def eligibility_digest(self) -> str:
        """Content identity frozen by qualification and rechecked at claim."""

        return _canonical_digest(
            {
                "project_key": self.project_key,
                "capability_id": self.capability_id,
                "resource_class": self.resource_class.value,
                "units": self.units,
                "policy_epoch": self.policy_epoch,
                "policy_digest": self.policy_digest,
                "concurrency_key": self.concurrency_key,
                "provider_key": self.provider_key,
            }
        )


@dataclass(frozen=True, slots=True)
class ResourcePolicySnapshot:
    """Exact claim-time resource ceiling read under the policy row lock."""

    project_key: str
    capability_id: str
    resource_class: ResourceClass
    policy_epoch: int
    policy_digest: str
    max_project_active: int
    max_capability_active: int
    max_resource_active: int
    max_units: int
    max_provider_active: int | None = None

    def __post_init__(self) -> None:
        require_digest(self.policy_digest, "policy_digest")
        ceilings = (
            self.max_project_active,
            self.max_capability_active,
            self.max_resource_active,
            self.max_units,
        )
        if any(value <= 0 for value in ceilings):
            raise ValueError("resource policy ceilings must be positive")
        if self.max_provider_active is not None and self.max_provider_active <= 0:
            raise ValueError("provider ceiling must be positive")


@dataclass(frozen=True, slots=True)
class ResourceUsage:
    project_active: int = 0
    capability_active: int = 0
    resource_active: int = 0
    active_units: int = 0
    provider_active: int = 0
    concurrency_keys: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if min(
            self.project_active,
            self.capability_active,
            self.resource_active,
            self.active_units,
            self.provider_active,
        ) < 0:
            raise ValueError("resource usage cannot be negative")


@dataclass(frozen=True, slots=True)
class ReservationDecision:
    granted: bool
    reason: str | None = None

    @classmethod
    def resource_limit(cls, reason: str) -> ReservationDecision:
        return cls(False, f"RESOURCE_LIMIT:{reason}")


def evaluate_reservation(
    eligibility: QueueEligibility,
    policy: ResourcePolicySnapshot,
    usage: ResourceUsage,
) -> ReservationDecision:
    """Evaluate the locked snapshot without mutating or consuming capacity."""

    expected = (
        eligibility.project_key,
        eligibility.capability_id,
        eligibility.resource_class,
        eligibility.policy_epoch,
        eligibility.policy_digest,
    )
    observed = (
        policy.project_key,
        policy.capability_id,
        policy.resource_class,
        policy.policy_epoch,
        policy.policy_digest,
    )
    if expected != observed:
        return ReservationDecision(False, "RESOURCE_POLICY_STALE")
    if usage.project_active >= policy.max_project_active:
        return ReservationDecision.resource_limit("PROJECT_ACTIVE")
    if usage.capability_active >= policy.max_capability_active:
        return ReservationDecision.resource_limit("CAPABILITY_ACTIVE")
    if usage.resource_active >= policy.max_resource_active:
        return ReservationDecision.resource_limit("RESOURCE_CLASS_ACTIVE")
    if usage.active_units + eligibility.units > policy.max_units:
        return ReservationDecision.resource_limit("UNITS")
    if (
        eligibility.provider_key is not None
        and policy.max_provider_active is not None
        and usage.provider_active >= policy.max_provider_active
    ):
        return ReservationDecision.resource_limit("PROVIDER_ACTIVE")
    if (
        eligibility.concurrency_key is not None
        and eligibility.concurrency_key in usage.concurrency_keys
    ):
        return ReservationDecision.resource_limit("CONCURRENCY_KEY")
    return ReservationDecision(True)


def _canonical_digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ExecutionReservation:
    reservation_id: str
    work_item_id: str
    project_key: str
    run_id: str
    step_id: str
    attempt_id: str
    execution_epoch: int
    resource_class: ResourceClass
    units: int
    concurrency_key: str | None
    provider_key: str | None
    policy_epoch: int
    policy_digest: str
    lease_token: str
    lease_expires_at: datetime
    reservation_digest: str

    @classmethod
    def create(
        cls,
        *,
        work_item_id: str,
        project_key: str,
        run_id: str,
        step_id: str,
        attempt_id: str,
        execution_epoch: int,
        eligibility: QueueEligibility,
        lease_token: str,
        lease_expires_at: datetime,
    ) -> ExecutionReservation:
        require_digest(attempt_id, "attempt_id")
        if execution_epoch < 0 or not lease_token:
            raise ValueError("reservation requires execution epoch and lease token")
        content: dict[str, object] = {
            "work_item_id": work_item_id,
            "project_key": project_key,
            "run_id": run_id,
            "step_id": step_id,
            "attempt_id": attempt_id,
            "execution_epoch": execution_epoch,
            "resource_class": eligibility.resource_class.value,
            "units": eligibility.units,
            "concurrency_key": eligibility.concurrency_key,
            "provider_key": eligibility.provider_key,
            "policy_epoch": eligibility.policy_epoch,
            "policy_digest": eligibility.policy_digest,
            "lease_token": lease_token,
            "lease_expires_at": lease_expires_at,
        }
        digest = _canonical_digest(content)
        return cls(
            reservation_id=f"reservation:sha256:{digest}",
            work_item_id=work_item_id,
            project_key=project_key,
            run_id=run_id,
            step_id=step_id,
            attempt_id=attempt_id,
            execution_epoch=execution_epoch,
            resource_class=eligibility.resource_class,
            units=eligibility.units,
            concurrency_key=eligibility.concurrency_key,
            provider_key=eligibility.provider_key,
            policy_epoch=eligibility.policy_epoch,
            policy_digest=eligibility.policy_digest,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            reservation_digest=digest,
        )


@dataclass(frozen=True, slots=True)
class FairSharePolicy:
    """Bounded-aging plus project/capability fair-share parameters.

    The analytical bound is a simulation contract for a finite eligible set;
    production capacity still requires a measured ``CapacityEnvelope.v1``.
    """

    aging_quantum_seconds: int = 30
    aging_increment: int = 1
    max_aging_boost: int = 100
    max_declared_priority: int = 100
    project_quantum: int = 1
    capability_quantum: int = 1
    max_project_active: int = 32
    max_capability_active: int = 8
    claim_cycle_seconds: int = 5

    def __post_init__(self) -> None:
        if min(
            self.aging_quantum_seconds,
            self.aging_increment,
            self.project_quantum,
            self.capability_quantum,
            self.max_project_active,
            self.max_capability_active,
            self.claim_cycle_seconds,
        ) <= 0:
            raise ValueError("fair-share quanta must be positive")
        if self.max_declared_priority < 0 or self.max_aging_boost < 0:
            raise ValueError("priority bounds must be non-negative")
        if self.max_aging_boost < self.max_declared_priority:
            raise ValueError("aging boost must span the declared priority range")


@dataclass(frozen=True, slots=True)
class FairClaimCandidate:
    work_item_id: str
    project_key: str
    capability_id: str
    fairness_key: str
    declared_priority: int
    enqueue_seq: int
    enqueued_at: datetime
    due_at: datetime

    def __post_init__(self) -> None:
        if not all(
            (self.work_item_id, self.project_key, self.capability_id, self.fairness_key)
        ):
            raise ValueError("fair candidate identities cannot be empty")
        if self.declared_priority < 0 or self.enqueue_seq < 0:
            raise ValueError("priority and enqueue sequence must be non-negative")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("fairness timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def effective_priority(
    declared_priority: int,
    enqueued_at: datetime,
    now: datetime,
    policy: FairSharePolicy,
) -> int:
    """Return declared priority plus a bounded, monotone age boost."""

    if declared_priority < 0 or declared_priority > policy.max_declared_priority:
        raise ValueError("declared priority is outside the frozen policy range")
    age_seconds = max(0.0, (_utc(now) - _utc(enqueued_at)).total_seconds())
    boost = min(
        policy.max_aging_boost,
        int(age_seconds // policy.aging_quantum_seconds) * policy.aging_increment,
    )
    return declared_priority + boost


def starvation_bound_seconds(
    policy: FairSharePolicy,
    *,
    eligible_item_count: int,
    project_count: int,
    capability_count: int,
    claim_batch: int,
) -> int:
    """Conservative finite-backlog bound under the deterministic selector.

    This function intentionally requires the bounded eligible cardinalities;
    without them (and without resource availability) no starvation guarantee is
    mathematically available.  It is not a production capacity claim.
    """

    if min(eligible_item_count, project_count, capability_count, claim_batch) <= 0:
        raise ValueError("starvation bound requires positive bounded cardinalities")
    priority_steps = math.ceil(
        policy.max_declared_priority / policy.aging_increment
    )
    aging_seconds = priority_steps * policy.aging_quantum_seconds
    project_rounds = math.ceil(project_count / policy.project_quantum)
    capability_rounds = math.ceil(capability_count / policy.capability_quantum)
    backlog_rounds = math.ceil(eligible_item_count / claim_batch)
    return aging_seconds + (
        project_rounds + capability_rounds + backlog_rounds
    ) * policy.claim_cycle_seconds


def select_fair_claims(
    candidates: Iterable[FairClaimCandidate],
    *,
    now: datetime,
    limit: int,
    policy: FairSharePolicy,
    active_by_project: Mapping[str, int] | None = None,
    active_by_capability: Mapping[tuple[str, str], int] | None = None,
    cursor: int = 0,
) -> tuple[FairClaimCandidate, ...]:
    """Select a deterministic project/capability fair-share batch.

    ``SKIP LOCKED`` is deliberately absent: row locking is the live adapter's
    job.  This selector establishes the order before those rows are locked.
    """

    if limit <= 0:
        return ()
    project_active = active_by_project or {}
    capability_active = active_by_capability or {}
    buckets: dict[str, dict[str, deque[FairClaimCandidate]]] = defaultdict(
        lambda: defaultdict(deque)
    )
    due = [
        candidate
        for candidate in candidates
        if _utc(candidate.due_at) <= _utc(now)
        and project_active.get(candidate.project_key, 0)
        < policy.max_project_active
        and capability_active.get(
            (candidate.project_key, candidate.capability_id), 0
        )
        < policy.max_capability_active
    ]
    due.sort(
        key=lambda item: (
            -effective_priority(
                item.declared_priority, item.enqueued_at, now, policy
            ),
            _utc(item.due_at),
            item.enqueue_seq,
            item.work_item_id,
        )
    )
    for item in due:
        buckets[item.fairness_key][item.capability_id].append(item)
    if not buckets:
        return ()

    bucket_project_keys: dict[str, str] = {}
    for fairness_key, capability_buckets in buckets.items():
        project_keys = {
            item.project_key
            for queue in capability_buckets.values()
            for item in queue
        }
        if len(project_keys) != 1:
            raise ValueError("fairness_key must remain scoped to one project")
        bucket_project_keys[fairness_key] = next(iter(project_keys))

    projects = sorted(
        buckets,
        key=lambda key: (
            project_active.get(bucket_project_keys[key], 0),
            bucket_project_keys[key],
            key,
        ),
    )
    offset = cursor % len(projects)
    projects = projects[offset:] + projects[:offset]
    project_queues: dict[str, deque[FairClaimCandidate]] = {}
    for fairness_key in projects:
        capability_buckets = buckets[fairness_key]
        capabilities = sorted(
            (key for key, values in capability_buckets.items() if values),
            key=lambda capability: (
                capability_active.get(
                    (bucket_project_keys[fairness_key], capability), 0
                ),
                capability,
            ),
        )
        capability_offset = cursor % len(capabilities)
        capabilities = (
            capabilities[capability_offset:] + capabilities[:capability_offset]
        )
        interleaved: deque[FairClaimCandidate] = deque()
        while any(capability_buckets[key] for key in capabilities):
            for capability in capabilities:
                queue = capability_buckets[capability]
                for _ in range(policy.capability_quantum):
                    if not queue:
                        break
                    interleaved.append(queue.popleft())
        project_queues[fairness_key] = interleaved

    chosen: list[FairClaimCandidate] = []
    while len(chosen) < limit and projects:
        remaining_projects: list[str] = []
        for fairness_key in projects:
            queue = project_queues[fairness_key]
            for _ in range(policy.project_quantum):
                if not queue or len(chosen) >= limit:
                    break
                chosen.append(queue.popleft())
            if queue:
                remaining_projects.append(fairness_key)
            if len(chosen) >= limit:
                break
        projects = remaining_projects
    return tuple(chosen)


__all__ = [
    "EFFECT_ASSIGNMENT_KINDS",
    "ExecutionReservation",
    "FairClaimCandidate",
    "FairSharePolicy",
    "QueueEligibility",
    "ReservationDecision",
    "ResourceClass",
    "ResourcePolicySnapshot",
    "ResourceUsage",
    "assignment_requires_reservation",
    "effective_priority",
    "evaluate_reservation",
    "select_fair_claims",
    "starvation_bound_seconds",
]
