"""Typed runtime work-item root schema (no database realization).

The work-item root is a discriminated union over the closed generic
``AssignmentKind`` values.  A capability extension adds contracts, codecs and
profiles; it never adds a work-item variant or a capability switch.  Concrete
queue/PostgreSQL storage belongs to a P0-B substrate adapter behind
``runtime.ports.WorkItemPort``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, model_validator

from .assignments import AssignmentKind, FrozenContract, RuntimeAssignment

WORK_ITEM_SCHEMA_VERSION = "mrw.runtime.work_item.v1"


class WorkItemState(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    CLAIMED = "CLAIMED"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class WorkItemWaitReason(StrEnum):
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    INTERPRETER_UNAVAILABLE = "INTERPRETER_UNAVAILABLE"
    AUTHORITY_STALE = "AUTHORITY_STALE"
    BACKOFF = "BACKOFF"
    SCHEDULE_NOT_DUE = "SCHEDULE_NOT_DUE"


class WorkItemRoot(FrozenContract):
    """One generic runtime work item plus its exact runtime assignment."""

    schema_version: Literal["mrw.runtime.work_item.v1"] = WORK_ITEM_SCHEMA_VERSION
    work_item_id: str = Field(min_length=1)
    project_key: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    step_id: str | None = None
    assignment_kind: AssignmentKind
    assignment: RuntimeAssignment
    state: WorkItemState = WorkItemState.PENDING
    wait_reason: WorkItemWaitReason | None = None
    required_node_profile_selector: str = Field(min_length=1)
    fairness_key: str = Field(min_length=1)
    declared_priority: int = Field(default=0, ge=0)
    enqueue_seq: int = Field(default=0, ge=0)
    enqueued_at: datetime
    due_at: datetime
    attempt_count: int = Field(default=0, ge=0)
    lease_token: str | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    deadline_at: datetime | None = None
    schedule_occurrence_ref: str | None = None
    last_failure_ref: str | None = None

    @model_validator(mode="after")
    def validate_assignment_identity(self) -> "WorkItemRoot":
        if self.work_item_id != self.assignment.work_item_id:
            raise ValueError("work item id does not match assignment")
        if self.project_key != self.assignment.project_key:
            raise ValueError("work item project scope does not match assignment")
        if self.run_id != self.assignment.run_id:
            raise ValueError("work item run does not match assignment")
        if self.step_id != self.assignment.step_id:
            raise ValueError("work item step does not match assignment")
        if self.assignment_kind != self.assignment.assignment_kind:
            raise ValueError("work item kind does not match assignment")
        if self.state is WorkItemState.WAITING and self.wait_reason is None:
            raise ValueError("WAITING work item requires wait_reason")
        return self

    @property
    def assignment_digest(self) -> str:
        return self.assignment.assignment_digest

    @property
    def handler_binding_digest(self) -> str:
        return self.assignment.handler_binding_digest


class CompileWorkItemRoot(WorkItemRoot):
    assignment_kind: Literal[AssignmentKind.COMPILE] = AssignmentKind.COMPILE


class QualifyWorkItemRoot(WorkItemRoot):
    assignment_kind: Literal[AssignmentKind.QUALIFY] = AssignmentKind.QUALIFY


class InterpretWorkItemRoot(WorkItemRoot):
    assignment_kind: Literal[AssignmentKind.INTERPRET] = AssignmentKind.INTERPRET


class VerifyAdmitWorkItemRoot(WorkItemRoot):
    assignment_kind: Literal[AssignmentKind.VERIFY_ADMIT] = AssignmentKind.VERIFY_ADMIT


class ProjectWorkItemRoot(WorkItemRoot):
    assignment_kind: Literal[AssignmentKind.PROJECT] = AssignmentKind.PROJECT


class ReconcileWorkItemRoot(WorkItemRoot):
    assignment_kind: Literal[AssignmentKind.RECONCILE] = AssignmentKind.RECONCILE


class MaterializeSuccessorWorkItemRoot(WorkItemRoot):
    assignment_kind: Literal[AssignmentKind.MATERIALIZE_SUCCESSOR] = (
        AssignmentKind.MATERIALIZE_SUCCESSOR
    )


WORK_ITEM_KIND_INDEX: dict[AssignmentKind, type[WorkItemRoot]] = {
    AssignmentKind.COMPILE: CompileWorkItemRoot,
    AssignmentKind.QUALIFY: QualifyWorkItemRoot,
    AssignmentKind.INTERPRET: InterpretWorkItemRoot,
    AssignmentKind.VERIFY_ADMIT: VerifyAdmitWorkItemRoot,
    AssignmentKind.PROJECT: ProjectWorkItemRoot,
    AssignmentKind.RECONCILE: ReconcileWorkItemRoot,
    AssignmentKind.MATERIALIZE_SUCCESSOR: MaterializeSuccessorWorkItemRoot,
}

WORK_ITEM_ROOT_MEMBERS: tuple[type[WorkItemRoot], ...] = tuple(
    WORK_ITEM_KIND_INDEX.values()
)

WorkItemRootUnion: TypeAlias = Annotated[
    CompileWorkItemRoot
    | QualifyWorkItemRoot
    | InterpretWorkItemRoot
    | VerifyAdmitWorkItemRoot
    | ProjectWorkItemRoot
    | ReconcileWorkItemRoot
    | MaterializeSuccessorWorkItemRoot,
    Field(discriminator="assignment_kind"),
]

# Port-facing name used by ``runtime.ports.WorkItemPort``.
WorkItemRecord: TypeAlias = WorkItemRootUnion


__all__ = [
    "CompileWorkItemRoot",
    "InterpretWorkItemRoot",
    "MaterializeSuccessorWorkItemRoot",
    "ProjectWorkItemRoot",
    "QualifyWorkItemRoot",
    "ReconcileWorkItemRoot",
    "VerifyAdmitWorkItemRoot",
    "WORK_ITEM_KIND_INDEX",
    "WORK_ITEM_ROOT_MEMBERS",
    "WORK_ITEM_SCHEMA_VERSION",
    "WorkItemRecord",
    "WorkItemRoot",
    "WorkItemRootUnion",
    "WorkItemState",
    "WorkItemWaitReason",
]
