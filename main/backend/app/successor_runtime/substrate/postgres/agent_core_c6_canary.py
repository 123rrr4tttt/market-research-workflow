"""Bounded local PostgreSQL canary + future-owner rollback for the C6 line.

The service owns no transaction: callers pass a connection enlisted in a
``RuntimeUnitOfWork``.  A canary transition locks the exact run, rehashes the
current capability authority row, requires one exact approval binding,
CAS-updates the authority, and appends one ``CapabilityAuthorityChanged``
event to the same run in the same transaction.  Rollback selects legacy as the
only future claim owner, retains the successor journal, and never enables
legacy and successor claims together.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.assignments import canonical_digest, require_digest
from app.successor_runtime.runtime.ports import RuntimeScope

from .approvals import ApprovalRepository
from .authority import CapabilityAuthority, CapabilityAuthorityRepository
from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    RuntimeJournalRepository,
    StaleRevisionError,
    _one_mapping,
    _scope_key,
    _table,
    _utcnow,
    validate_runtime_assignment_row,
)

TRANSITION_SCHEMA = "mrw.successor.agent-core.c6.canary-transition.v1"
AUTHORITY_EVENT_TYPE = "CapabilityAuthorityChanged"
AUTHORITY_EVENT_SCHEMA = "mrw.successor.agent-core.c6.authority-event.v1"

_OPAQUE_PAYLOAD_REF_PREFIXES = (
    "value:",
    "project-value:",
    "runtime-blob:",
    "canonical:",
)
_PACKET_DIGEST_PLACEHOLDER = "0" * 64


class C6CanaryPhase(StrEnum):
    """Successor claim states used by the bounded C6 canary."""

    OFF = "off"
    SHADOW = "shadow"
    CANARY = "canary"

    @property
    def mode(self) -> str:
        return self.value

    @property
    def successor_claim_enabled(self) -> bool:
        return self is C6CanaryPhase.CANARY

    @property
    def legacy_claim_enabled(self) -> bool:
        return self in {C6CanaryPhase.SHADOW, C6CanaryPhase.OFF}


def select_future_owner(
    row: Mapping[str, Any],
) -> Literal["legacy", "successor", "none"]:
    """Return the single future claim owner selected by an authority row."""

    successor = bool(row["successor_claim_enabled"])
    legacy = bool(row["legacy_claim_enabled"])
    if successor and legacy:
        raise ExactBindingConflict(
            "capability authority cannot enable legacy and successor claims together"
        )
    if successor:
        return "successor"
    if legacy:
        return "legacy"
    return "none"


@dataclass(frozen=True, slots=True)
class C6CanaryTransitionPacket:
    """Content-addressed exact transition packet for one C6 canary move."""

    transition_id: str
    capability_id: str
    run_id: str
    step_id: str
    work_item_id: str
    program_digest: str
    plan_digest: str
    payload_digest: str
    payload_ref: str
    successor_binding_digest: str
    source_phase: C6CanaryPhase
    target_phase: C6CanaryPhase
    expected_authority_epoch: int
    expected_authority_revision: int
    expected_run_revision: int
    approval_ref: str
    rollback_target_ref: str
    allowlist_digest: str
    config_digest: str
    effective_at: datetime
    before_authority_digest: str
    after_authority_digest: str
    schema_version: Literal["mrw.successor.agent-core.c6.canary-transition.v1"] = (
        TRANSITION_SCHEMA
    )
    transition_packet_digest: str = ""

    def __post_init__(self) -> None:
        for name in (
            "transition_id",
            "capability_id",
            "run_id",
            "step_id",
            "work_item_id",
            "payload_ref",
            "approval_ref",
            "rollback_target_ref",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        if not self.payload_ref.startswith(_OPAQUE_PAYLOAD_REF_PREFIXES):
            raise ValueError("payload_ref must be a bounded opaque locator")
        for name in (
            "program_digest",
            "plan_digest",
            "payload_digest",
            "successor_binding_digest",
            "allowlist_digest",
            "config_digest",
            "before_authority_digest",
            "after_authority_digest",
            "transition_packet_digest",
        ):
            value = getattr(self, name)
            if name == "transition_packet_digest" and (
                value == _PACKET_DIGEST_PLACEHOLDER or value == ""
            ):
                continue
            require_digest(value, name)
        if any(
            value < 0
            for value in (
                self.expected_authority_epoch,
                self.expected_authority_revision,
                self.expected_run_revision,
            )
        ):
            raise ValueError("canary epoch/revision expectations must be non-negative")
        if self.source_phase is self.target_phase:
            raise ValueError("canary transition must change the authority phase")
        if self.target_phase is C6CanaryPhase.CANARY and not (
            self.target_phase.successor_claim_enabled
            and not self.target_phase.legacy_claim_enabled
        ):
            raise ValueError("canary phase must be successor-only")
        expected = canonical_digest(self._content(exclude={"transition_packet_digest"}))
        if (
            self.transition_packet_digest
            not in {
                "",
                _PACKET_DIGEST_PLACEHOLDER,
            }
            and self.transition_packet_digest != expected
        ):
            raise ValueError("canary transition packet digest mismatch")

    @classmethod
    def from_content(cls, **content: object) -> C6CanaryTransitionPacket:
        if "transition_packet_digest" in content:
            raise ValueError("transition_packet_digest is derived from packet content")
        content.setdefault("schema_version", TRANSITION_SCHEMA)
        provisional = cls(
            **content, transition_packet_digest=_PACKET_DIGEST_PLACEHOLDER
        )
        return cls(
            **content,
            transition_packet_digest=canonical_digest(
                provisional._content(exclude={"transition_packet_digest"})
            ),
        )

    def _content(self, *, exclude: set[str] | None = None) -> dict[str, object]:
        payload: dict[str, object] = {}
        for field in fields(self):
            if exclude is not None and field.name in exclude:
                continue
            value: object = getattr(self, field.name)
            if isinstance(value, C6CanaryPhase):
                value = value.value
            elif isinstance(value, datetime):
                value = value.isoformat()
            payload[field.name] = value
        return payload


@dataclass(frozen=True, slots=True)
class C6CanaryTransitionReceipt:
    transition_id: str
    run_id: str
    event_seq: int
    previous_run_revision: int
    run_revision: int
    authority_epoch: int
    authority_revision: int
    before_authority_digest: str
    after_authority_digest: str


def authority_digest(
    *,
    project_key: str,
    capability_id: str,
    mode: str,
    authority_epoch: int,
    successor_claim_enabled: bool,
    legacy_claim_enabled: bool,
    allowlist_digest: str,
    config_digest: str,
    effective_at: datetime,
    updated_by: str,
    approval_ref: str,
    rollback_target_ref: str,
    revision: int,
) -> str:
    """Content-addressed digest over one C6 capability authority row."""

    if successor_claim_enabled and legacy_claim_enabled:
        raise ValueError("legacy and successor claim authority cannot both be enabled")
    return canonical_digest(
        {
            "project_key": project_key,
            "capability_id": capability_id,
            "mode": mode,
            "authority_epoch": authority_epoch,
            "successor_claim_enabled": successor_claim_enabled,
            "legacy_claim_enabled": legacy_claim_enabled,
            "allowlist_digest": allowlist_digest,
            "config_digest": config_digest,
            "effective_at": effective_at.astimezone(UTC).isoformat(),
            "updated_by": updated_by,
            "approval_ref": approval_ref,
            "rollback_target_ref": rollback_target_ref,
            "revision": revision,
        }
    )


def _capability_authority_changed_event(
    packet: C6CanaryTransitionPacket,
    *,
    authority_epoch: int,
    authority_revision: int,
    before_digest: str,
    after_digest: str,
) -> dict[str, Any]:
    return {
        "event_type": AUTHORITY_EVENT_TYPE,
        "schema_version": AUTHORITY_EVENT_SCHEMA,
        "step_id": packet.step_id,
        "event_metadata_json": {
            "transition_id": packet.transition_id,
            "state": "CAPABILITY_AUTHORITY_CHANGED",
            "previous_state": packet.source_phase.value,
            "next_state": packet.target_phase.value,
            "capability_id": packet.capability_id,
            "authority_epoch": authority_epoch,
            "previous_revision": packet.expected_authority_revision,
            "target_revision": authority_revision,
            "approval_ref": packet.approval_ref,
            "rollback_target_ref": packet.rollback_target_ref,
            "payload_digest": packet.payload_digest,
            "program_digest": packet.program_digest,
            "plan_digest": packet.plan_digest,
            "successor_binding_digest": packet.successor_binding_digest,
            "before_authority_digest": before_digest,
            "after_authority_digest": after_digest,
        },
        "payload_ref": packet.payload_ref,
        "payload_digest": packet.payload_digest,
        "authority_digest": after_digest,
    }


class AgentCoreC6CanaryService:
    """Atomic authority/event transitions on the caller-owned connection."""

    def __init__(
        self,
        connection: Connection,
        scope: RuntimeScope,
        *,
        journal: RuntimeJournalRepository | None = None,
        approvals: ApprovalRepository | None = None,
        authority_repository: CapabilityAuthorityRepository | None = None,
    ) -> None:
        self.connection = connection
        self.scope = scope
        self.journal = journal or RuntimeJournalRepository(connection, scope)
        self.approvals = approvals or ApprovalRepository(connection, scope)
        self.authority_repository = (
            authority_repository or CapabilityAuthorityRepository(connection, scope)
        )

    def promote_canary(
        self,
        packet: C6CanaryTransitionPacket,
        *,
        now: datetime | None = None,
    ) -> C6CanaryTransitionReceipt:
        return self._transition(
            packet,
            source=C6CanaryPhase.SHADOW,
            target=C6CanaryPhase.CANARY,
            now=now,
        )

    def rollback_legacy(
        self,
        packet: C6CanaryTransitionPacket,
        *,
        now: datetime | None = None,
    ) -> C6CanaryTransitionReceipt:
        return self._transition(
            packet,
            source=C6CanaryPhase.CANARY,
            target=C6CanaryPhase.OFF,
            now=now,
        )

    def _transition(
        self,
        packet: C6CanaryTransitionPacket,
        *,
        source: C6CanaryPhase,
        target: C6CanaryPhase,
        now: datetime | None,
    ) -> C6CanaryTransitionReceipt:
        if packet.source_phase is not source or packet.target_phase is not target:
            raise ExactBindingConflict("canary packet phase does not match transition")
        observed_at = now or _utcnow()
        if packet.effective_at > observed_at:
            raise ExactBindingConflict("canary effective_at is in the future")

        self.journal.load_run(packet.run_id, for_update=True)
        row = self.authority_repository.load(packet.capability_id, for_update=True)
        self._require_source_authority(row, packet, source)
        before = authority_digest(
            project_key=str(row["project_key"]),
            capability_id=str(row["capability_id"]),
            mode=str(row["mode"]),
            authority_epoch=int(row["authority_epoch"]),
            successor_claim_enabled=bool(row["successor_claim_enabled"]),
            legacy_claim_enabled=bool(row["legacy_claim_enabled"]),
            allowlist_digest=str(row["allowlist_digest"]),
            config_digest=str(row["config_digest"]),
            effective_at=row["effective_at"],
            updated_by=str(row["updated_by"]),
            approval_ref=str(row["approval_ref"]),
            rollback_target_ref=str(row["rollback_target_ref"]),
            revision=int(row["revision"]),
        )
        if before != packet.before_authority_digest:
            raise ExactBindingConflict("canary before authority digest mismatch")

        next_epoch = packet.expected_authority_epoch + 1
        next_revision = packet.expected_authority_revision + 1
        after = authority_digest(
            project_key=_scope_key(self.scope),
            capability_id=packet.capability_id,
            mode=target.mode,
            authority_epoch=next_epoch,
            successor_claim_enabled=target.successor_claim_enabled,
            legacy_claim_enabled=target.legacy_claim_enabled,
            allowlist_digest=packet.allowlist_digest,
            config_digest=packet.config_digest,
            effective_at=packet.effective_at,
            updated_by=self.scope.actor_id,
            approval_ref=packet.approval_ref,
            rollback_target_ref=packet.rollback_target_ref,
            revision=next_revision,
        )
        if after != packet.after_authority_digest:
            raise ExactBindingConflict("canary after authority digest mismatch")

        required_claim_epoch = (
            next_epoch
            if target is C6CanaryPhase.CANARY
            else packet.expected_authority_epoch
        )
        self._require_exact_work_binding(
            packet,
            required_claim_authority_epoch=required_claim_epoch,
        )
        self.approvals.require_current(
            packet.approval_ref,
            run_id=packet.run_id,
            step_id=packet.step_id,
            payload_digest=packet.payload_digest,
            authority_digest=packet.after_authority_digest,
            now=observed_at,
        )

        authority = CapabilityAuthority(
            capability_id=packet.capability_id,
            mode=target.mode,
            authority_epoch=next_epoch,
            successor_claim_enabled=target.successor_claim_enabled,
            legacy_claim_enabled=target.legacy_claim_enabled,
            allowlist_digest=packet.allowlist_digest,
            config_digest=packet.config_digest,
            effective_at=packet.effective_at,
            approval_ref=packet.approval_ref,
            rollback_target_ref=packet.rollback_target_ref,
        )
        self.authority_repository.revise(
            authority,
            expected_revision=packet.expected_authority_revision,
        )
        event = _capability_authority_changed_event(
            packet,
            authority_epoch=next_epoch,
            authority_revision=next_revision,
            before_digest=before,
            after_digest=after,
        )
        receipt = self.journal.append_transition(
            run_id=packet.run_id,
            expected_revision=packet.expected_run_revision,
            snapshot_values={},
            events=(event,),
        )
        return C6CanaryTransitionReceipt(
            transition_id=packet.transition_id,
            run_id=packet.run_id,
            event_seq=receipt.first_event_seq or 0,
            previous_run_revision=receipt.previous_revision,
            run_revision=receipt.revision,
            authority_epoch=next_epoch,
            authority_revision=next_revision,
            before_authority_digest=before,
            after_authority_digest=after,
        )

    def _require_source_authority(
        self,
        row: Mapping[str, Any],
        packet: C6CanaryTransitionPacket,
        source: C6CanaryPhase,
    ) -> None:
        if (
            str(row["mode"]) != source.mode
            or bool(row["successor_claim_enabled"]) != source.successor_claim_enabled
            or bool(row["legacy_claim_enabled"]) != source.legacy_claim_enabled
        ):
            raise ExactBindingConflict("canary source authority phase mismatch")
        if str(row["rollback_target_ref"]) != packet.rollback_target_ref:
            raise ExactBindingConflict("canary rollback target mismatch")
        if int(row["authority_epoch"]) != packet.expected_authority_epoch:
            raise ExactBindingConflict("canary authority epoch is stale")
        if int(row["revision"]) != packet.expected_authority_revision:
            raise StaleRevisionError("canary authority revision CAS failed")

    def _require_exact_work_binding(
        self,
        packet: C6CanaryTransitionPacket,
        *,
        required_claim_authority_epoch: int,
    ) -> None:
        table = _table("runtime_work_items")
        row = _one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.work_item_id == packet.work_item_id,
                )
            )
        )
        if row is None:
            raise RecordNotFound(f"canary work item not found: {packet.work_item_id}")
        validate_runtime_assignment_row(row)
        required = {
            "run_id": packet.run_id,
            "step_id": packet.step_id,
            "assignment_kind": "INTERPRET",
            "program_digest": packet.program_digest,
            "plan_digest": packet.plan_digest,
            "payload_digest": packet.payload_digest,
            "handler_binding_digest": packet.successor_binding_digest,
            "claim_authority_epoch": required_claim_authority_epoch,
        }
        mismatches = [
            name for name, expected in required.items() if row.get(name) != expected
        ]
        if mismatches:
            raise ExactBindingConflict(
                "canary work binding drift: " + ", ".join(mismatches)
            )


__all__ = [
    "AUTHORITY_EVENT_SCHEMA",
    "AUTHORITY_EVENT_TYPE",
    "TRANSITION_SCHEMA",
    "AgentCoreC6CanaryService",
    "C6CanaryPhase",
    "C6CanaryTransitionPacket",
    "C6CanaryTransitionReceipt",
    "authority_digest",
    "select_future_owner",
]
