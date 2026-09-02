"""PostgreSQL claim-time execution reservation repository.

The repository uses a caller-owned :class:`Connection`; it never commits.  A
claim transaction first locks the exact resource-policy row, observes active
reservations under that lock, and only then inserts one reservation.  Lease
heartbeat/release/reap are token-and-revision compare-and-swap operations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app.successor_runtime.runtime.resources import (
    ExecutionReservation,
    QueueEligibility,
    ReservationDecision,
    ResourcePolicySnapshot,
    ResourceUsage,
    evaluate_reservation,
)

from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    StaleRevisionError,
    _mapping_rows,
    _one_mapping,
    _table,
    _utcnow,
)


class StaleResourcePolicy(ExactBindingConflict):
    pass


class StaleLeaseToken(StaleRevisionError):
    pass


@dataclass(frozen=True, slots=True)
class ReservationAttempt:
    decision: ReservationDecision
    reservation: Mapping[str, Any] | None


def _lock_policy_statement(eligibility: QueueEligibility):
    policies = _table("runtime_resource_policies")
    return (
        select(policies)
        .where(
            policies.c.project_key == eligibility.project_key,
            policies.c.capability_id == eligibility.capability_id,
            policies.c.resource_class == eligibility.resource_class.value,
            policies.c.policy_epoch == eligibility.policy_epoch,
            policies.c.policy_digest == eligibility.policy_digest,
        )
        .with_for_update()
    )


def _active_reservations_statement(
    eligibility: QueueEligibility, now: datetime, *, resource_policy_id: str
):
    reservations = _table("runtime_resource_reservations")
    return select(reservations).where(
        reservations.c.project_key == eligibility.project_key,
        reservations.c.state == "ACTIVE",
        reservations.c.lease_expires_at > now,
    )


def _policy_snapshot(row: Mapping[str, Any]) -> ResourcePolicySnapshot:
    return ResourcePolicySnapshot(
        project_key=str(row["project_key"]),
        capability_id=str(row["capability_id"]),
        resource_class=str(row["resource_class"]),  # type: ignore[arg-type]
        policy_epoch=int(row["policy_epoch"]),
        policy_digest=str(row["policy_digest"]),
        max_project_active=int(row.get("max_project_active", row["concurrency_limit"])),
        max_capability_active=int(
            row.get("max_capability_active", row["concurrency_limit"])
        ),
        max_resource_active=int(
            row.get("max_resource_active", row["concurrency_limit"])
        ),
        max_units=int(row.get("max_units", row["units_ceiling"])),
        max_provider_active=(
            None
            if row.get("max_provider_active", row.get("provider_limit")) is None
            else int(row.get("max_provider_active", row["provider_limit"]))
        ),
    )


def _usage(
    rows: tuple[Mapping[str, Any], ...],
    eligibility: QueueEligibility,
    *,
    resource_policy_id: str,
) -> ResourceUsage:
    return ResourceUsage(
        project_active=len(rows),
        capability_active=sum(
            row["resource_policy_id"] == resource_policy_id for row in rows
        ),
        resource_active=sum(
            row["resource_class"] == eligibility.resource_class.value for row in rows
        ),
        active_units=sum(
            int(row["units"])
            for row in rows
            if row["resource_policy_id"] == resource_policy_id
        ),
        provider_active=sum(
            eligibility.provider_key is not None and row.get("provider_key") == eligibility.provider_key
            for row in rows
        ),
        concurrency_keys=frozenset(
            str(row["concurrency_key"])
            for row in rows
            if row.get("concurrency_key") is not None
        ),
    )


class ResourceReservationRepository:
    """Live resource owner enlisted in the outer claim transaction."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def try_reserve(
        self,
        reservation: ExecutionReservation,
        eligibility: QueueEligibility,
        *,
        capability_id: str,
        node_id: str,
        resource_policy_id: str,
        now: datetime | None = None,
    ) -> ReservationAttempt:
        if capability_id != eligibility.capability_id:
            raise ExactBindingConflict("reservation capability binding drift")
        if (
            reservation.project_key != eligibility.project_key
            or reservation.policy_epoch != eligibility.policy_epoch
            or reservation.policy_digest != eligibility.policy_digest
            or reservation.resource_class != eligibility.resource_class
            or reservation.units != eligibility.units
            or reservation.concurrency_key != eligibility.concurrency_key
            or reservation.provider_key != eligibility.provider_key
        ):
            raise ExactBindingConflict("reservation differs from queue eligibility")
        observed_at = now or _utcnow()
        locked = _one_mapping(
            self.connection.execute(_lock_policy_statement(eligibility))
        )
        if locked is None:
            raise StaleResourcePolicy("exact active resource policy not found")
        active = _mapping_rows(
            self.connection.execute(
                _active_reservations_statement(
                    eligibility,
                    observed_at,
                    resource_policy_id=resource_policy_id,
                )
            )
        )
        decision = evaluate_reservation(
            eligibility,
            _policy_snapshot(locked),
            _usage(active, eligibility, resource_policy_id=resource_policy_id),
        )
        if not decision.granted:
            return ReservationAttempt(decision, None)

        table = _table("runtime_resource_reservations")
        values = {
            "reservation_id": reservation.reservation_id,
            "project_key": reservation.project_key,
            "work_item_id": reservation.work_item_id,
            "run_id": reservation.run_id,
            "step_id": reservation.step_id,
            "attempt_id": reservation.attempt_id,
            "execution_epoch": reservation.execution_epoch,
            "resource_policy_id": resource_policy_id,
            "capability_id": capability_id,
            "policy_epoch": reservation.policy_epoch,
            "policy_digest": reservation.policy_digest,
            "resource_class": reservation.resource_class.value,
            "concurrency_key": reservation.concurrency_key or reservation.work_item_id,
            "provider_key": reservation.provider_key,
            "units": reservation.units,
            "node_id": node_id,
            "lease_token": reservation.lease_token,
            "lease_expires_at": reservation.lease_expires_at,
            "state": "ACTIVE",
            "reservation_digest": reservation.reservation_digest,
            "revision": 0,
            "created_at": observed_at,
            "updated_at": observed_at,
        }
        try:
            self.connection.execute(insert(table).values(**values))
        except IntegrityError as exc:
            raise ExactBindingConflict(
                "duplicate work-item/attempt execution reservation"
            ) from exc
        return ReservationAttempt(decision, values)

    def heartbeat(
        self,
        reservation_id: str,
        lease_token: str,
        *,
        expected_revision: int,
        new_expiry: datetime,
    ) -> Mapping[str, Any]:
        table = _table("runtime_resource_reservations")
        predicates = [
                table.c.reservation_id == reservation_id,
                table.c.lease_token == lease_token,
                table.c.state == "ACTIVE",
        ]
        values: dict[str, Any] = {
            "lease_expires_at": new_expiry,
            "updated_at": _utcnow(),
            "revision": expected_revision + 1,
        }
        predicates.append(table.c.revision == expected_revision)
        result = self.connection.execute(
            update(table).where(*predicates).values(**values)
        )
        if getattr(result, "rowcount", None) != 1:
            raise StaleLeaseToken("reservation heartbeat token/revision CAS failed")
        return self.load(reservation_id)

    def release(
        self,
        reservation_id: str,
        lease_token: str,
        *,
        expected_revision: int,
        reason: str,
        now: datetime | None = None,
    ) -> Mapping[str, Any]:
        table = _table("runtime_resource_reservations")
        observed_at = now or _utcnow()
        predicates = [
                table.c.reservation_id == reservation_id,
                table.c.lease_token == lease_token,
                table.c.state == "ACTIVE",
        ]
        values: dict[str, Any] = {
            "state": "RELEASED",
            "released_at": observed_at,
            "release_reason": reason,
            "updated_at": observed_at,
            "revision": expected_revision + 1,
        }
        predicates.append(table.c.revision == expected_revision)
        result = self.connection.execute(
            update(table).where(*predicates).values(**values)
        )
        if getattr(result, "rowcount", None) != 1:
            raise StaleLeaseToken("reservation release token/revision CAS failed")
        return self.load(reservation_id)

    def reap_expired(self, now: datetime, *, limit: int = 128) -> tuple[str, ...]:
        if limit <= 0:
            return ()
        table = _table("runtime_resource_reservations")
        locked = _mapping_rows(
            self.connection.execute(
                select(
                    table.c.reservation_id,
                    table.c.revision,
                )
                .where(table.c.state == "ACTIVE", table.c.lease_expires_at <= now)
                .order_by(table.c.lease_expires_at, table.c.reservation_id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        reaped: list[str] = []
        for row in locked:
            predicates = [
                    table.c.reservation_id == row["reservation_id"],
                    table.c.state == "ACTIVE",
                    table.c.lease_expires_at <= now,
            ]
            values: dict[str, Any] = {
                "state": "EXPIRED",
                "released_at": now,
                "release_reason": "LEASE_EXPIRED",
                "updated_at": now,
                "revision": int(row["revision"]) + 1,
            }
            predicates.append(table.c.revision == row["revision"])
            result = self.connection.execute(
                update(table).where(*predicates).values(**values)
            )
            if getattr(result, "rowcount", None) == 1:
                reaped.append(str(row["reservation_id"]))
        return tuple(reaped)

    def load(self, reservation_id: str) -> Mapping[str, Any]:
        table = _table("runtime_resource_reservations")
        row = _one_mapping(
            self.connection.execute(
                select(table).where(table.c.reservation_id == reservation_id)
            )
        )
        if row is None:
            raise RecordNotFound(f"resource reservation not found: {reservation_id}")
        return row


__all__ = [
    "ReservationAttempt",
    "ResourceReservationRepository",
    "StaleLeaseToken",
    "StaleResourcePolicy",
    "_active_reservations_statement",
    "_lock_policy_statement",
]
