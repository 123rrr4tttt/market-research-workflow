from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


STATE_CONTRACT_VERSION = "clue_chain.state.v1"
CONFIG_KEY = "clue_chains_state_v1"
CONFIG_TYPE = "clue_chains_state"

CHAIN_STATUSES = frozenset({"draft", "running", "paused", "blocked", "closed"})
HOP_STATUSES = frozenset({"planned", "running", "completed", "failed", "blocked"})
EVIDENCE_STATUSES = frozenset({"lead", "finding", "corroborated", "rejected"})
CANDIDATE_STATUSES = frozenset({"pending", "promoted", "rejected", "merged", "deferred", "paused"})
DECISIONS = frozenset({"promote", "reject", "merge", "defer", "pause", "close"})
EDGE_STATUSES = frozenset({"candidate", "promoted", "rejected"})


@dataclass(frozen=True, slots=True)
class Chain:
    chain_id: str
    project_key: str
    title: str
    objective: str
    status: str
    seed_node_ids: tuple[str, ...]
    frontier_node_ids: tuple[str, ...]
    max_depth: int
    max_hops: int
    confidence_threshold: float
    created_by: str
    provenance_policy: str
    privacy_policy: str
    created_at: str
    updated_at: str
    graph_id: str | None = None
    closed_at: str | None = None
    close_reason: str | None = None
    blockers: tuple[str, ...] = ()
    policy_json: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChainHop:
    hop_id: str
    chain_id: str
    depth: int
    input_node_id: str
    mode: str
    tool_name: str
    query_json: Mapping[str, Any]
    status: str
    started_at: str
    provider: str | None = None
    actor: str | None = None
    finished_at: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    edge_ids: tuple[str, ...] = ()
    error: str | None = None
    trace: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChainEvidence:
    evidence_id: str
    chain_id: str
    hop_id: str
    source_kind: str
    source_ref: Mapping[str, Any]
    captured_at: str
    status: str
    url: str | None = None
    archive_url: str | None = None
    content_hash: str | None = None
    title: str | None = None
    snippet: str | None = None
    provider: str | None = None
    query: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChainCandidate:
    candidate_id: str
    chain_id: str
    hop_id: str
    entity_type: str
    value: str
    aliases: tuple[str, ...]
    score: float | None
    decision_status: str
    evidence_ids: tuple[str, ...]
    created_at: str
    updated_at: str
    canonical_key: str
    edge_ids: tuple[str, ...] = ()
    decision_ids: tuple[str, ...] = ()
    merged_into_candidate_id: str | None = None
    graph_node_id: str | None = None
    properties: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChainDecision:
    decision_id: str
    chain_id: str
    candidate_id: str
    actor: str
    decision: str
    reason: str
    created_at: str
    target_candidate_id: str | None = None
    graph_node_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    edge_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChainEdge:
    edge_id: str
    chain_id: str
    hop_id: str
    from_ref: str
    to_ref: str
    relation: str
    evidence_ids: tuple[str, ...]
    status: str
    created_at: str
    updated_at: str
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


def model_to_record(model: Any) -> dict[str, Any]:
    data = asdict(model)
    for key, value in list(data.items()):
        if isinstance(value, tuple):
            data[key] = list(value)
        elif isinstance(value, Mapping):
            data[key] = dict(value)
    return data
