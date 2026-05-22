from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ClueChainStatus = Literal["open", "closed"]
ClueChainHopStatus = Literal["queued", "running", "completed", "failed"]
ClueChainCandidateStatus = Literal["pending", "accepted", "rejected", "merged"]
ClueChainExpansionMode = Literal["source_library_search", "external_search", "agent_tool"]
ClueChainDecisionAction = Literal["promote", "reject", "merge"]


class ClueChainCreateRequest(BaseModel):
    project_key: str | None = None
    graph_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    question: str | None = None
    root_node_ids: list[str] = Field(default_factory=list, min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ClueChainExpandRequest(BaseModel):
    mode: ClueChainExpansionMode
    query: str | None = None
    frontier_node_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=50)
    provider_options: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ClueChainDecisionRequest(BaseModel):
    action: ClueChainDecisionAction
    reason: str | None = None
    target_node_id: str | None = None
    merge_candidate_id: str | None = None
    decided_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ClueChainCloseRequest(BaseModel):
    reason: str | None = None
    closed_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ClueChainData(BaseModel):
    chain_id: str
    project_key: str
    graph_id: str
    title: str
    question: str | None = None
    status: ClueChainStatus
    root_node_ids: list[str] = Field(default_factory=list)
    frontier_node_ids: list[str] = Field(default_factory=list)
    hop_ids: list[str] = Field(default_factory=list)
    candidate_count: int = 0
    evidence_count: int = 0
    decision_count: int = 0
    created_at: str
    updated_at: str
    closed_at: str | None = None
    close_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ClueChainHopData(BaseModel):
    hop_id: str
    chain_id: str
    mode: ClueChainExpansionMode
    query: str | None = None
    status: ClueChainHopStatus
    frontier_node_ids: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: str
    completed_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ClueChainEvidenceData(BaseModel):
    evidence_id: str
    chain_id: str
    hop_id: str
    candidate_id: str | None = None
    source_type: str
    source_ref: str | None = None
    title: str | None = None
    url: str | None = None
    snippet: str | None = None
    node_refs: list[str] = Field(default_factory=list)
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ClueChainCandidateData(BaseModel):
    candidate_id: str
    chain_id: str
    hop_id: str
    label: str
    candidate_type: str = "node"
    aliases: list[str] = Field(default_factory=list)
    confidence: float | None = None
    status: ClueChainCandidateStatus
    evidence_ids: list[str] = Field(default_factory=list)
    target_node_id: str | None = None
    edge: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ClueChainDecisionData(BaseModel):
    decision_id: str
    chain_id: str
    candidate_id: str
    action: ClueChainDecisionAction
    status: ClueChainCandidateStatus
    evidence_ids: list[str] = Field(default_factory=list)
    target_node_id: str | None = None
    merge_candidate_id: str | None = None
    reason: str | None = None
    decided_by: str | None = None
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ClueChainDetailData(BaseModel):
    chain: ClueChainData
    hops: list[ClueChainHopData] = Field(default_factory=list)
    candidates: list[ClueChainCandidateData] = Field(default_factory=list)
    evidence: list[ClueChainEvidenceData] = Field(default_factory=list)
    decisions: list[ClueChainDecisionData] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ClueChainListData(BaseModel):
    items: list[ClueChainData] = Field(default_factory=list)
    total: int = 0

    model_config = ConfigDict(extra="allow")


class ClueChainExpansionData(BaseModel):
    chain: ClueChainData
    hop: ClueChainHopData
    candidates: list[ClueChainCandidateData] = Field(default_factory=list)
    evidence: list[ClueChainEvidenceData] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ClueChainDecisionResponseData(BaseModel):
    chain: ClueChainData
    candidate: ClueChainCandidateData
    decision: ClueChainDecisionData

    model_config = ConfigDict(extra="allow")


class ClueChainCloseData(BaseModel):
    chain: ClueChainData

    model_config = ConfigDict(extra="allow")
