"""Inquiry-family domain objects: intent, inquiry, and plan."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .codec import finalize_digest

__all__ = ["Inquiry", "PlanWorkItem", "ResearchIntent", "ResearchPlan"]


@dataclass(frozen=True, slots=True)
class ResearchIntent:
    intent_id: str
    project_key: str
    purpose: str
    audience_or_use: str
    scope: dict[str, Any]
    as_of: datetime
    constraints: dict[str, Any]
    expected_delivery: dict[str, Any]
    content_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.audience_or_use, str):
            raise ValueError("ResearchIntent audience_or_use is required")
        if not isinstance(self.constraints, dict):
            raise ValueError("ResearchIntent constraints are required")
        finalize_digest(self, "content_digest")


@dataclass(frozen=True, slots=True)
class Inquiry:
    inquiry_id: str
    intent_ref: str
    question_or_hypothesis: str
    acceptance_conditions: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    uncertainty_ceiling: str
    content_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.uncertainty_ceiling, str):
            raise ValueError("Inquiry uncertainty_ceiling is required")
        finalize_digest(self, "content_digest")


@dataclass(frozen=True, slots=True)
class PlanWorkItem:
    work_id: str
    operator: str
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    plan_id: str
    inquiry_ref: str
    work_items: tuple[PlanWorkItem, ...]
    budget: dict[str, Any]
    deadline: datetime | None
    replan_policy: dict[str, Any]
    content_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.replan_policy, dict):
            raise ValueError("ResearchPlan replan_policy is required")
        finalize_digest(self, "content_digest")
