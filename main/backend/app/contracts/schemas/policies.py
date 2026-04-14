from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PolicySummary(BaseModel):
    id: int
    title: str | None = None
    state: str | None = None
    status: str | None = None
    publish_date: str | None = None
    effective_date: str | None = None
    policy_type: str | None = None
    key_points: list[str] = Field(default_factory=list)
    summary: str | None = None
    uri: str | None = None
    created_at: str | None = None


class PoliciesListData(BaseModel):
    items: list[PolicySummary] = Field(default_factory=list)


class CountByState(BaseModel):
    state: str
    count: int


class CountByPolicyType(BaseModel):
    policy_type: str
    count: int


class CountByStatus(BaseModel):
    status: str
    count: int


class CountByDate(BaseModel):
    date: str | None = None
    count: int


class PolicyStats(BaseModel):
    total: int
    active_count: int
    states_count: int
    state_distribution: list[CountByState] = Field(default_factory=list)
    type_distribution: list[CountByPolicyType] = Field(default_factory=list)
    status_distribution: list[CountByStatus] = Field(default_factory=list)
    trend_series: list[CountByDate] = Field(default_factory=list)


class CountByType(BaseModel):
    type: str
    count: int


class CountByPredicate(BaseModel):
    predicate: str
    count: int


class PolicyStateStatistics(BaseModel):
    total: int
    active_count: int
    most_common_type: str | None = None
    type_distribution: list[CountByType] = Field(default_factory=list)
    entity_distribution: list[CountByType] = Field(default_factory=list)
    relation_distribution: list[CountByPredicate] = Field(default_factory=list)
    key_points_count: int


class PolicyStateDetail(BaseModel):
    state: str
    policies: list[PolicySummary] = Field(default_factory=list)
    statistics: PolicyStateStatistics


class PolicyDetail(PolicySummary):
    content: str | None = None
    source_id: int | None = None
    updated_at: str | None = None
    entities: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)

