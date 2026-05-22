from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkflowGraphCuratedStateData(BaseModel):
    graph_id: str | None = None
    revision: int | None = None
    active_version_id: str | None = None
    draft: dict[str, Any] = Field(default_factory=dict)
    has_draft: bool | None = None
    updated_at: str | None = None
    base_version: int | None = None
    version_semantics: str | None = None
    sync_status: str | None = None
    in_sync: bool | None = None
    server_snapshot: dict[str, Any] = Field(default_factory=dict)
    submit_status: str | None = None
    rollback_status: str | None = None
    rollback_from_version_id: str | None = None
    audit_id: str | None = None
    draft_updated_at: str | None = None

    model_config = ConfigDict(extra="allow")


class WorkflowGraphAuditListData(BaseModel):
    graph_id: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    total: int | None = None
    base_version: int | None = None

    model_config = ConfigDict(extra="allow")


class WorkflowGraphEvidenceNode(BaseModel):
    node_id: str | None = None
    node_type: str | None = None
    title: str | None = None
    summary: str | None = None
    source_uri: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class WorkflowGraphEvidenceRelation(BaseModel):
    from_node_id: str | None = None
    to_node_id: str | None = None
    edge_type: str | None = None
    evidence: str | None = None
    confidence: float | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class WorkflowGraphEvidencePackData(BaseModel):
    contract_version: str | None = None
    pack_id: str | None = None
    graph_id: str | None = None
    graph_scope: str | None = None
    revision: int | None = None
    version_id: str | None = None
    generated_at: str | None = None
    selected_nodes: list[WorkflowGraphEvidenceNode] = Field(default_factory=list)
    relations: list[WorkflowGraphEvidenceRelation] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class WorkflowGraphHandoffData(BaseModel):
    contract_version: str | None = None
    handoff_id: str | None = None
    owner: str | None = None
    producer: str | None = None
    handoff_mode: str | None = None
    consumer: str | None = None
    report_generate_request: dict[str, Any] = Field(default_factory=dict)
    keyword_card_request: dict[str, Any] = Field(default_factory=dict)
    evidence_pack: WorkflowGraphEvidencePackData | dict[str, Any] | None = None
    graph_context: WorkflowGraphEvidencePackData | dict[str, Any] | None = None
    persistence: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class WorkflowGraphHandoffListData(BaseModel):
    run_id: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    total: int | None = None
    contract_version: str | None = None

    model_config = ConfigDict(extra="allow")


class WorkflowGraphHandoffReplayData(BaseModel):
    run_id: str | None = None
    handoff_id: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    contract_version: str | None = None

    model_config = ConfigDict(extra="allow")
