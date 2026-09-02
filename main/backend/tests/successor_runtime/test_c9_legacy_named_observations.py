"""C9 named legacy observational traces.

Three fixed-profile, side-effect-free observations of legacy MRW surfaces
(agent sessions, graph project/backfill, and vector contracts) are captured
and compared against the pure C9 successor source/payload vocabulary. Legacy
state is only observed: the traces never write canonical source/control state
and never invoke provider/vector/index execution.
"""

from __future__ import annotations

import contextlib
import re
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.services.graph.adapters import normalize_document
from app.services.graph.backfill_graph_nodes import run_graph_node_backfill
from app.services.graph.builder import build_graph, build_topic_subgraph
from app.services.indexer.policy import _build_vector_contract_payload
from app.successor_runtime.substrate.projections import c9_sources as c9

pytestmark = pytest.mark.unit

PROJECT_SCOPE_REF = "project:legacy-c9-observation"
SESSION_PROFILE_ID = "legacy-as-session-c9-observation"
GRAPH_PROFILE_ID = "legacy-graph-project-c9-observation"
SEARCH_PROFILE_ID = "legacy-vector-contract-c9-observation"
REVISION = "legacy-c9-r1"
INCARNATION = "legacy-c9-inc1"

HEX64 = re.compile(r"^[0-9a-f]{64}$")

_LEGACY_EVENT_KINDS = {
    "session.created": c9.SESSION_CREATED,
    "task.created": c9.SESSION_TASK_ASSIGNED,
    "task.completed": c9.SESSION_PROJECTION_REFRESHED,
    "session.completed": c9.SESSION_TERMINAL_SUCCEEDED,
}

_WRITE_TARGETS = (
    "app.successor_runtime.substrate.postgres.c9_projection_sources.put_semantic_source_rows",
    "app.services.indexer.policy.index_policy_documents",
    "app.services.indexer.policy.get_embeddings",
    "app.services.indexer.policy.get_es_client",
    "app.services.indexer.policy.start_job",
    "app.services.indexer.policy.complete_job",
    "app.services.indexer.policy.fail_job",
    "app.services.indexer.policy.bulk",
    "app.services.indexer.policy.RecursiveCharacterTextSplitter",
    "app.services.graph.backfill_graph_nodes.GraphNodeWriter",
)


def _loss(
    field_path: str,
    *,
    loss_kind: str = c9.LOSS_KIND_OMITTED_FIELD,
    reason: str,
) -> c9.ProjectionFieldLossV1:
    return c9.ProjectionFieldLossV1(
        schema_version=c9.PROJECTION_FIELD_LOSS_SCHEMA,
        field_path=field_path,
        loss_kind=loss_kind,
        reason=reason,
    )


def _flatten_fields(value: Any, prefix: str = "") -> set[str]:
    fields: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(item, (dict, list)):
                fields.update(_flatten_fields(item, path))
            else:
                fields.add(path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{prefix}[{index}]"
            if isinstance(item, (dict, list)):
                fields.update(_flatten_fields(item, path))
            else:
                fields.add(path)
    else:
        fields.add(prefix)
    return fields


def _unmapped_losses(
    legacy_paths: set[str],
    mapped_paths: set[str],
    *,
    reason: str,
) -> tuple[c9.ProjectionFieldLossV1, ...]:
    unmapped = sorted(legacy_paths - mapped_paths)
    return tuple(_loss(path, reason=reason) for path in unmapped)


def _session_donor() -> dict[str, Any]:
    session_id = SESSION_PROFILE_ID
    session = {
        "session_id": session_id,
        "source": "agent_batch",
        "project_key": PROJECT_SCOPE_REF,
        "entrypoint_type": "agent_batch.jobs",
        "goal": "Execute legacy agent batch job legacy-job-01",
        "status": "completed",
        "current_phase": "verification",
        "compat_mode": True,
        "compat_job_id": "legacy-job-01",
        "logical_task_list_key": "legacy-job-01",
        "root_task_id": "task-legacy-01",
        "metadata": {
            "compat_projection_version": "agent_batch.jobs.v1",
            "agent_batch": {"job_id": "legacy-job-01"},
        },
        "final_result": {"status": "ok"},
        "created_at": "2026-08-31T08:00:00+00:00",
        "updated_at": "2026-08-31T09:00:00+00:00",
    }
    tasks = [
        {
            "session_id": session_id,
            "task_id": "task-legacy-01",
            "parent_task_id": None,
            "subject": "Research phase",
            "description": "Legacy research task",
            "task_type": "research",
            "phase": "research",
            "status": "completed",
            "execution_mode": "worker",
            "blocked_by": [],
            "blocks": ["task-legacy-02"],
            "priority": 5,
            "write_set": ["memory.md"],
            "read_set": [],
            "task_spec": {"task_type": "research"},
            "metadata": {"compat_projection": "agent_batch.job_item"},
            "result_summary": "Research finished",
            "result_payload": {"run_id": "legacy-run-01"},
            "summary_label": "Research phase [completed]",
            "last_activity": "task completed",
            "recent_activities": ["claimed", "completed"],
            "tool_use_count": 4,
            "token_usage": 1200,
            "lease_until": None,
            "claimed_at": "2026-08-31T08:05:00+00:00",
            "started_at": "2026-08-31T08:05:00+00:00",
            "completed_at": "2026-08-31T08:50:00+00:00",
            "created_at": "2026-08-31T08:00:00+00:00",
            "updated_at": "2026-08-31T08:50:00+00:00",
        },
        {
            "session_id": session_id,
            "task_id": "task-legacy-02",
            "parent_task_id": "task-legacy-01",
            "subject": "Synthesis phase",
            "description": "Legacy synthesis task",
            "task_type": "synthesis",
            "phase": "synthesis",
            "status": "completed",
            "execution_mode": "worker",
            "blocked_by": ["task-legacy-01"],
            "blocks": [],
            "priority": 5,
            "write_set": ["scratchpad.md"],
            "read_set": ["memory.md"],
            "task_spec": {"task_type": "synthesis"},
            "metadata": {"compat_projection": "agent_batch.job_item"},
            "result_summary": "Synthesis finished",
            "result_payload": {"run_id": "legacy-run-01"},
            "summary_label": "Synthesis phase [completed]",
            "last_activity": "task completed",
            "recent_activities": ["claimed", "completed"],
            "tool_use_count": 3,
            "token_usage": 900,
            "lease_until": None,
            "claimed_at": "2026-08-31T08:52:00+00:00",
            "started_at": "2026-08-31T08:52:00+00:00",
            "completed_at": "2026-08-31T09:00:00+00:00",
            "created_at": "2026-08-31T08:00:00+00:00",
            "updated_at": "2026-08-31T09:00:00+00:00",
        },
    ]
    events = [
        {
            "session_id": session_id,
            "seq": 1,
            "event_type": "session.created",
            "task_id": None,
            "payload": {"source": "agent_batch"},
            "ts": "2026-08-31T08:00:00+00:00",
        },
        {
            "session_id": session_id,
            "seq": 2,
            "event_type": "task.created",
            "task_id": "task-legacy-01",
            "payload": {"phase": "research"},
            "ts": "2026-08-31T08:00:01+00:00",
        },
        {
            "session_id": session_id,
            "seq": 3,
            "event_type": "task.created",
            "task_id": "task-legacy-02",
            "payload": {"phase": "synthesis"},
            "ts": "2026-08-31T08:00:02+00:00",
        },
        {
            "session_id": session_id,
            "seq": 4,
            "event_type": "task.completed",
            "task_id": "task-legacy-01",
            "payload": {"result_summary": "Research finished"},
            "ts": "2026-08-31T08:50:00+00:00",
        },
        {
            "session_id": session_id,
            "seq": 5,
            "event_type": "task.completed",
            "task_id": "task-legacy-02",
            "payload": {"result_summary": "Synthesis finished"},
            "ts": "2026-08-31T09:00:00+00:00",
        },
        {
            "session_id": session_id,
            "seq": 6,
            "event_type": "session.completed",
            "task_id": None,
            "payload": {},
            "ts": "2026-08-31T09:00:01+00:00",
        },
    ]
    return {
        "session": session,
        "tasks": tasks,
        "messages": [],
        "artifacts": [],
        "events": events,
        "approvals": [],
    }


def _seed_legacy_session(donor: dict[str, Any]) -> InMemoryAgentSessionStore:
    store = InMemoryAgentSessionStore()
    store.create_session(dict(donor["session"]))
    for task in donor["tasks"]:
        store.create_task(dict(task))
    for event in donor["events"]:
        store.append_event(
            donor["session"]["session_id"],
            event_type=str(event["event_type"]),
            task_id=event.get("task_id"),
            payload=dict(event.get("payload") or {}),
        )
    return store


def _observe_legacy_session() -> dict[str, Any]:
    donor = _session_donor()
    store = _seed_legacy_session(donor)
    service = AgentSessionService(store=store)
    first = service.get_session_bundle(SESSION_PROFILE_ID)
    second = service.get_session_bundle(SESSION_PROFILE_ID)
    assert c9.content_digest(first) == c9.content_digest(second)
    return first


def _runtime_events(bundle: dict[str, Any]) -> tuple[c9.RuntimeSessionEventV1, ...]:
    events = []
    for index, legacy_event in enumerate(bundle["events"]):
        legacy_type = str(legacy_event.get("event_type") or "")
        kind = _LEGACY_EVENT_KINDS.get(legacy_type)
        if kind is None:
            raise AssertionError(f"legacy event type has no C9 mapping: {legacy_type}")
        task_id = legacy_event.get("task_id")
        event_ref = f"{SESSION_PROFILE_ID}:e{index}:{legacy_type}"
        if task_id:
            event_ref = f"{event_ref}:{task_id}"
        events.append(
            c9.RuntimeSessionEventV1(
                schema_version=c9.RUNTIME_SESSION_EVENT_SCHEMA,
                sequence=index,
                event_kind=kind,
                event_ref=event_ref,
                event_note="",
            )
        )
    return tuple(events)


def _mapped_session_paths(bundle: dict[str, Any]) -> set[str]:
    mapped = {"session.session_id", "session.project_key", "session.status"}
    for index, event in enumerate(bundle["events"]):
        mapped.add(f"events[{index}].seq")
        mapped.add(f"events[{index}].event_type")
        if event.get("task_id") is not None:
            mapped.add(f"events[{index}].task_id")
    return mapped


def _session_source(bundle: dict[str, Any]) -> c9.RuntimeSessionSourceV1:
    return c9.RuntimeSessionSourceV1(
        schema_version=c9.RUNTIME_SESSION_SOURCE_SCHEMA,
        project_scope_ref=str(bundle["session"]["project_key"]),
        session_ref=str(bundle["session"]["session_id"]),
        revision=REVISION,
        incarnation=INCARNATION,
        events=_runtime_events(bundle),
    )


def _session_observation(
    bundle: dict[str, Any],
) -> tuple[
    c9.RuntimeSessionSourceV1,
    c9.AgentSessionProjectionPayloadV1,
    set[str],
    set[str],
]:
    source = _session_source(bundle)
    mapped = _mapped_session_paths(bundle)
    legacy_paths = _flatten_fields(bundle)
    losses = _unmapped_losses(
        legacy_paths,
        mapped,
        reason="legacy session field not carried by C9 runtime session source",
    )
    losses += (
        _loss(
            "session.status.blocked",
            reason=(
                "legacy blocked status has no C9 successor status; it is "
                "observed as RUNNING with a declared loss"
            ),
        ),
        _loss(
            "session.terminal.vocabulary",
            reason=(
                "legacy terminal statuses canceled/expired have no successor "
                "terminal event kind"
            ),
        ),
        _loss(
            "tasks.blocked_by",
            reason="task dependency/blocking is not carried by the C9 runtime session source",
        ),
    )
    payload = c9.build_agent_session_payload(source, declared_losses=losses)
    return source, payload, mapped, legacy_paths


def _graph_docs() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            id=101,
            uri="https://reddit.com/r/marketai/comments/101",
            state="published",
            doc_type="social_sentiment",
            title="AI market momentum",
            content="AI market momentum is accelerating.",
            publish_date=date(2026, 3, 3),
            created_at=datetime(2026, 3, 3, 8, 0, tzinfo=timezone.utc),
            extracted_data={
                "platform": "reddit",
                "text": "AI market momentum is accelerating.",
                "username": "analyst_alpha",
                "subreddit": "marketai",
                "keywords": ["AI", "market", "momentum"],
                "entities": [
                    {
                        "text": "OpenAI",
                        "type": "ORG",
                        "kb_id": "kb-openai",
                        "span": [0, 6],
                        "confidence": 0.9,
                    }
                ],
                "sentiment": {
                    "sentiment_orientation": "positive",
                    "sentiment_tags": ["bullish"],
                    "key_phrases": ["market growth"],
                    "emotion_words": [],
                    "topic": "AI",
                },
            },
        ),
        SimpleNamespace(
            id=102,
            uri="https://reddit.com/r/marketai/comments/102",
            state="published",
            doc_type="social_sentiment",
            title="Policy tailwind",
            content="Policy tailwind helps market momentum.",
            publish_date=date(2026, 3, 4),
            created_at=datetime(2026, 3, 4, 8, 0, tzinfo=timezone.utc),
            extracted_data={
                "platform": "reddit",
                "text": "Policy tailwind helps market momentum.",
                "username": "policy_watch",
                "subreddit": "marketai",
                "keywords": ["policy", "market", "momentum"],
                "entities": [{"text": "Fed", "type": "ORG", "span": [0, 3]}],
                "sentiment": {
                    "sentiment_orientation": "positive",
                    "sentiment_tags": ["constructive"],
                    "key_phrases": ["policy tailwind"],
                    "emotion_words": [],
                    "topic": "AI",
                },
            },
        ),
    ]


class _FakeBackfillScalars:
    def __init__(self, docs: list[Any]) -> None:
        self._docs = list(docs)

    def all(self) -> list[Any]:
        return list(self._docs)


class _FakeBackfillResult:
    def __init__(self, docs: list[Any]) -> None:
        self._result = _FakeBackfillScalars(docs)

    def scalars(self) -> _FakeBackfillScalars:
        return self._result


class _FakeBackfillSession:
    def __init__(self, docs: list[Any]) -> None:
        self._docs = list(docs)

    def execute(self, _query: Any) -> _FakeBackfillResult:
        return _FakeBackfillResult(self._docs)


def _observe_legacy_graph() -> Any:
    docs = _graph_docs()
    posts = [normalize_document(doc) for doc in docs]
    assert all(post is not None for post in posts), "captured graph docs must normalize"
    graph = build_graph(posts)
    result = run_graph_node_backfill(_FakeBackfillSession(docs), dry_run=True)
    assert result.scanned_docs == len(docs)
    assert result.skipped_docs == 0
    assert result.written_nodes == len(graph.nodes)
    return graph


def _node_label(node: Any) -> str:
    props = node.properties
    if node.type == "Post":
        return str(props.get("uri") or props.get("text") or f"post-{node.id}")
    if node.type == "Keyword":
        return str(props.get("text") or node.id)
    if node.type == "Entity":
        return str(props.get("canonical_name") or props.get("text") or node.id)
    if node.type in {"Topic", "SentimentTag", "Subreddit"}:
        return str(
            props.get("label") or props.get("name") or props.get("text") or node.id
        )
    if node.type == "User":
        return str(props.get("username") or node.id)
    return str(node.id)


def _graph_source(graph: Any) -> c9.ResearchGraphSourceV1:
    objects = []
    for key in sorted(graph.nodes):
        node = graph.nodes[key]
        objects.append(
            c9.ResearchGraphObjectV1(
                schema_version=c9.RESEARCH_GRAPH_OBJECT_SCHEMA,
                object_id=key,
                object_type=node.type,
                label=_node_label(node),
            )
        )
    relations = []
    for index, edge in enumerate(graph.edges):
        source_id = f"{edge.from_node.type}:{edge.from_node.id}"
        target_id = f"{edge.to_node.type}:{edge.to_node.id}"
        relations.append(
            c9.ResearchGraphRelationV1(
                schema_version=c9.RESEARCH_GRAPH_RELATION_SCHEMA,
                relation_id=f"legacy-edge-{index}",
                relation_type=edge.type,
                source_object_id=source_id,
                target_object_id=target_id,
                occurrence_ref=f"{edge.type}:{source_id}->{target_id}",
            )
        )
    return c9.ResearchGraphSourceV1(
        schema_version=c9.RESEARCH_GRAPH_SOURCE_SCHEMA,
        project_scope_ref=PROJECT_SCOPE_REF,
        graph_ref=GRAPH_PROFILE_ID,
        revision=REVISION,
        incarnation=INCARNATION,
        objects=tuple(objects),
        relations=tuple(relations),
    )


def _graph_plain(graph: Any) -> dict[str, Any]:
    return {
        "nodes": {
            key: {
                "type": node.type,
                "id": node.id,
                "properties": dict(node.properties),
            }
            for key, node in graph.nodes.items()
        },
        "edges": [
            {
                "type": edge.type,
                "from_node": {"type": edge.from_node.type, "id": edge.from_node.id},
                "to_node": {"type": edge.to_node.type, "id": edge.to_node.id},
                "properties": dict(edge.properties),
            }
            for edge in graph.edges
        ],
    }


def _mapped_graph_paths(plain: dict[str, Any]) -> set[str]:
    mapped: set[str] = set()
    for key in plain["nodes"]:
        mapped.add(f"nodes.{key}.type")
        mapped.add(f"nodes.{key}.id")
    for index in range(len(plain["edges"])):
        mapped.add(f"edges[{index}].type")
        mapped.add(f"edges[{index}].from_node.type")
        mapped.add(f"edges[{index}].from_node.id")
        mapped.add(f"edges[{index}].to_node.type")
        mapped.add(f"edges[{index}].to_node.id")
    return mapped


def _graph_observation(
    graph: Any,
) -> tuple[
    c9.ResearchGraphSourceV1,
    c9.ResearchGraphProjectionPayloadV1,
    dict[str, Any],
    set[str],
    set[str],
]:
    plain = _graph_plain(graph)
    source = _graph_source(graph)
    mapped = _mapped_graph_paths(plain)
    legacy_paths = _flatten_fields(plain)
    losses = _unmapped_losses(
        legacy_paths,
        mapped,
        reason="legacy graph field not carried by C9 research graph source",
    )
    losses += (
        _loss(
            "graph.objects.label",
            loss_kind=c9.LOSS_KIND_DECLARED,
            reason="label is inferred from legacy node properties for presentation only",
        ),
        _loss(
            "graph.node_key_presentation",
            loss_kind=c9.LOSS_KIND_DECLARED,
            reason=(
                "legacy Type:id node keys are preserved as object_id; the "
                "type prefix is presentation only"
            ),
        ),
        _loss(
            "graph.edge_endpoint_types",
            loss_kind=c9.LOSS_KIND_DECLARED,
            reason=(
                "edge endpoint types are recoverable only by object lookup, "
                "not as edge fields"
            ),
        ),
        _loss(
            "graph.induced_subgraph",
            loss_kind=c9.LOSS_KIND_DECLARED,
            reason=(
                "the legacy topic subgraph is derived from adjacency; the C9 "
                "payload carries the full graph only"
            ),
        ),
    )
    payload = c9.build_research_graph_payload(source, declared_losses=losses)
    return source, payload, plain, mapped, legacy_paths


def _vector_doc() -> SimpleNamespace:
    return SimpleNamespace(
        id=42,
        uri="https://example.org/policy/42",
        publish_date=date(2026, 3, 3),
        created_at=datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc),
        extracted_data={
            "project_key": PROJECT_SCOPE_REF,
            "language": "en",
            "vector_version": "v1",
            "source_domain": "example.org",
            "effective_time": "2026-03-03T00:00:00Z",
            "keep_for_vectorization": True,
        },
    )


def _observe_legacy_vector() -> dict[str, Any]:
    return _build_vector_contract_payload(
        _vector_doc(), "  AI market momentum is accelerating.  "
    )


def _search_source(legacy: dict[str, Any]) -> c9.C7SearchSourceV1:
    return c9.C7SearchSourceV1(
        schema_version=c9.C7_SEARCH_SOURCE_SCHEMA,
        project_scope_ref=str(legacy["project_key"]),
        search_ref=SEARCH_PROFILE_ID,
        revision=REVISION,
        incarnation=INCARNATION,
        segments=(
            c9.C7SearchSegmentV1(
                schema_version=c9.C7_SEARCH_SEGMENT_SCHEMA,
                segment_id=f"{legacy['object_type']}:{legacy['object_id']}:0",
                field_path="legacy.vector_contract.clean_text",
                segment_text=str(legacy["clean_text"]),
                segment_kind=c9.C7_SEGMENT_KIND_TEXT,
            ),
        ),
    )


def _vector_observation(
    legacy: dict[str, Any] | None = None,
) -> tuple[
    dict[str, Any],
    c9.C7SearchSourceV1,
    c9.SearchProjectionPayloadV1,
    set[str],
    set[str],
]:
    if legacy is None:
        legacy = _observe_legacy_vector()
    source = _search_source(legacy)
    mapped = {"project_key", "object_id", "clean_text"}
    legacy_paths = _flatten_fields(legacy)
    losses = _unmapped_losses(
        legacy_paths,
        mapped,
        reason="legacy vector contract field not carried by the C7 search payload",
    )
    losses += (
        _loss(
            "vector_contract.object_id",
            loss_kind=c9.LOSS_KIND_DECLARED,
            reason="legacy object id is re-keyed into the C7 segment_id",
        ),
        _loss(
            "provider.model",
            loss_kind=c9.LOSS_KIND_NOT_EXECUTED,
            reason="legacy embedding provider/model is never executed in the C7 projection",
        ),
        _loss(
            "vector.embedding",
            loss_kind=c9.LOSS_KIND_NOT_EXECUTED,
            reason="vector fields are never produced by the C7 projection",
        ),
        _loss(
            "index.es_document",
            loss_kind=c9.LOSS_KIND_NOT_EXECUTED,
            reason="Elasticsearch index document write is not executed",
        ),
        _loss(
            "index.qdrant_point",
            loss_kind=c9.LOSS_KIND_NOT_EXECUTED,
            reason="Qdrant point write is not executed",
        ),
    )
    payload = c9.build_search_payload(source, declared_losses=losses)
    return legacy, source, payload, mapped, legacy_paths


def test_named_legacy_session_observation_maps_identity_status_blocked_terminal() -> (
    None
):
    bundle = _observe_legacy_session()
    source, payload, mapped, legacy_paths = _session_observation(bundle)

    assert source.session_ref == SESSION_PROFILE_ID
    assert source.project_scope_ref == PROJECT_SCOPE_REF
    assert payload.session_ref == source.session_ref
    assert payload.source_ref == f"runtime-session:{source.session_ref}"

    assert bundle["session"]["status"] == "completed"
    assert payload.status == c9.SESSION_STATUS_TERMINAL_SUCCEEDED
    assert source.terminal_event is not None
    assert payload.terminal_event_ref == source.terminal_event.event_ref
    assert source.terminal_event.sequence == len(source.events) - 1

    assert "blocked" not in c9.SESSION_STATUSES
    assert "tasks" not in payload.to_plain()
    loss_paths = {loss.field_path for loss in payload.declared_losses}
    assert loss_paths >= legacy_paths - mapped
    assert {
        "session.status.blocked",
        "session.terminal.vocabulary",
        "tasks.blocked_by",
    } <= loss_paths
    for loss in payload.declared_losses:
        assert loss.loss_kind in c9.LOSS_KINDS
        assert HEX64.match(loss.loss_digest)


def test_named_legacy_graph_observation_maps_nodes_edges_and_induced_subgraph() -> None:
    graph = _observe_legacy_graph()
    source, payload, plain, mapped, legacy_paths = _graph_observation(graph)

    assert source.graph_ref == GRAPH_PROFILE_ID
    assert source.project_scope_ref == PROJECT_SCOPE_REF
    assert payload.graph_ref == source.graph_ref

    legacy_nodes = {(key, plain["nodes"][key]["type"]) for key in plain["nodes"]}
    payload_nodes = {(obj.object_id, obj.object_type) for obj in payload.objects}
    assert payload_nodes == legacy_nodes

    legacy_edges = {
        (
            edge["type"],
            f"{edge['from_node']['type']}:{edge['from_node']['id']}",
            f"{edge['to_node']['type']}:{edge['to_node']['id']}",
        )
        for edge in plain["edges"]
    }
    payload_edges = {
        (rel.relation_type, rel.source_object_id, rel.target_object_id)
        for rel in payload.relations
    }
    assert payload_edges == legacy_edges
    assert len(payload.relations) == len(graph.edges)

    topic_key = "Topic:ai"
    assert topic_key in graph.nodes
    legacy_subgraph = build_topic_subgraph(graph, "AI")
    induced_ids = {topic_key}
    changed = True
    while changed:
        changed = False
        for rel in payload.relations:
            if (rel.source_object_id in induced_ids) != (
                rel.target_object_id in induced_ids
            ):
                changed = True
                induced_ids.add(rel.source_object_id)
                induced_ids.add(rel.target_object_id)
    payload_induced_objects = {
        obj.object_id for obj in payload.objects if obj.object_id in induced_ids
    }
    payload_induced_edges = {
        (rel.relation_type, rel.source_object_id, rel.target_object_id)
        for rel in payload.relations
        if rel.source_object_id in induced_ids and rel.target_object_id in induced_ids
    }
    assert set(legacy_subgraph.nodes) == payload_induced_objects
    legacy_sub_edges = {
        (
            edge.type,
            f"{edge.from_node.type}:{edge.from_node.id}",
            f"{edge.to_node.type}:{edge.to_node.id}",
        )
        for edge in legacy_subgraph.edges
    }
    assert legacy_sub_edges == payload_induced_edges

    loss_paths = {loss.field_path for loss in payload.declared_losses}
    assert loss_paths >= legacy_paths - mapped
    assert {
        "graph.objects.label",
        "graph.node_key_presentation",
        "graph.edge_endpoint_types",
        "graph.induced_subgraph",
    } <= loss_paths


def test_named_legacy_vector_contract_observation_maps_identity_text_and_losses() -> (
    None
):
    legacy, _source, payload, mapped, legacy_paths = _vector_observation()

    assert payload.project_scope_ref == legacy["project_key"] == PROJECT_SCOPE_REF
    assert payload.search_ref == SEARCH_PROFILE_ID
    assert payload.source_ref == f"c7-search:{payload.search_ref}"
    segment = payload.segments[0]
    assert segment.segment_id == f"{legacy['object_type']}:{legacy['object_id']}:0"
    assert segment.field_path == "legacy.vector_contract.clean_text"
    assert segment.segment_text == legacy["clean_text"]
    assert segment.segment_text == "AI market momentum is accelerating."
    assert payload.provider_status == c9.NOT_EXECUTED
    assert payload.vectorization_status == c9.NOT_EXECUTED
    assert segment.provider_status == c9.NOT_EXECUTED
    assert segment.vectorization_status == c9.NOT_EXECUTED

    loss_paths = {loss.field_path for loss in payload.declared_losses}
    assert loss_paths >= legacy_paths - mapped
    for field in (
        "object_type",
        "vector_version",
        "language",
        "source_domain",
        "effective_time",
        "keep_for_vectorization",
    ):
        assert field in loss_paths
    assert {
        "provider.model",
        "vector.embedding",
        "index.es_document",
        "index.qdrant_point",
    } <= loss_paths

    flat_fields = _flatten_fields(payload.to_plain())
    assert (
        not {
            "provider",
            "model",
            "vector",
            "embedding",
            "index",
            "es_document",
            "qdrant",
        }
        & flat_fields
    )


def test_legacy_observation_traces_never_write_canonical_or_control() -> None:
    mocks: dict[str, Any] = {}
    with contextlib.ExitStack() as stack:
        for target in _WRITE_TARGETS:
            mocks[target] = stack.enter_context(patch(target))
        session_bundle = _observe_legacy_session()
        graph = _observe_legacy_graph()
        legacy = _observe_legacy_vector()
        _session_observation(session_bundle)
        _graph_observation(graph)
        _vector_observation(legacy)
    for target, mock in mocks.items():
        assert mock.call_count == 0, f"observation wrote through {target}"
