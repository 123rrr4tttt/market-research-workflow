"""C9 typed source/projection payload pure contract tests."""

from __future__ import annotations

import dataclasses
import json
import re

import pytest

from app.successor_runtime.substrate.projections import c9_sources as c9

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _event(
    sequence: int,
    event_kind: str,
    event_ref: str,
    *,
    note: str = "",
) -> c9.RuntimeSessionEventV1:
    return c9.RuntimeSessionEventV1(
        schema_version=c9.RUNTIME_SESSION_EVENT_SCHEMA,
        sequence=sequence,
        event_kind=event_kind,
        event_ref=event_ref,
        event_note=note,
    )


def _session_source(
    *,
    session_ref: str = "sess-1",
    revision: str = "r1",
    incarnation: str = "inc-1",
    events: tuple[c9.RuntimeSessionEventV1, ...] | None = None,
) -> c9.RuntimeSessionSourceV1:
    if events is None:
        events = (
            _event(0, c9.SESSION_CREATED, "e0", note="created"),
            _event(1, c9.SESSION_TASK_ASSIGNED, "e1", note="assigned"),
        )
    return c9.RuntimeSessionSourceV1(
        schema_version=c9.RUNTIME_SESSION_SOURCE_SCHEMA,
        project_scope_ref="proj-a",
        session_ref=session_ref,
        revision=revision,
        incarnation=incarnation,
        events=events,
    )


def _object(object_id: str, label: str) -> c9.ResearchGraphObjectV1:
    return c9.ResearchGraphObjectV1(
        schema_version=c9.RESEARCH_GRAPH_OBJECT_SCHEMA,
        object_id=object_id,
        object_type="concept",
        label=label,
    )


def _relation(
    relation_id: str,
    source_object_id: str,
    target_object_id: str,
) -> c9.ResearchGraphRelationV1:
    return c9.ResearchGraphRelationV1(
        schema_version=c9.RESEARCH_GRAPH_RELATION_SCHEMA,
        relation_id=relation_id,
        relation_type="relates",
        source_object_id=source_object_id,
        target_object_id=target_object_id,
        occurrence_ref=f"occ:{relation_id}",
    )


def _graph_source(
    *,
    graph_ref: str = "graph-1",
    revision: str = "r1",
    incarnation: str = "inc-1",
) -> c9.ResearchGraphSourceV1:
    return c9.ResearchGraphSourceV1(
        schema_version=c9.RESEARCH_GRAPH_SOURCE_SCHEMA,
        project_scope_ref="proj-a",
        graph_ref=graph_ref,
        revision=revision,
        incarnation=incarnation,
        objects=(_object("o1", "alpha"), _object("o2", "beta")),
        relations=(_relation("r1", "o1", "o2"),),
    )


def _segment(
    segment_id: str,
    *,
    field_path: str = "payload.structured_material.body",
) -> c9.C7SearchSegmentV1:
    return c9.C7SearchSegmentV1(
        schema_version=c9.C7_SEARCH_SEGMENT_SCHEMA,
        segment_id=segment_id,
        field_path=field_path,
        segment_text="market evidence",
        segment_kind=c9.C7_SEGMENT_KIND_TEXT,
    )


def _search_source(
    *,
    search_ref: str = "search-1",
    revision: str = "r1",
    incarnation: str = "inc-1",
) -> c9.C7SearchSourceV1:
    return c9.C7SearchSourceV1(
        schema_version=c9.C7_SEARCH_SOURCE_SCHEMA,
        project_scope_ref="proj-a",
        search_ref=search_ref,
        revision=revision,
        incarnation=incarnation,
        segments=(_segment("s1"),),
    )


def _loss(
    field_path: str,
    *,
    loss_kind: str = c9.LOSS_KIND_DECLARED,
    reason: str = "bounded local projection",
) -> c9.ProjectionFieldLossV1:
    return c9.ProjectionFieldLossV1(
        schema_version=c9.PROJECTION_FIELD_LOSS_SCHEMA,
        field_path=field_path,
        loss_kind=loss_kind,
        reason=reason,
    )


def _session_payload() -> c9.AgentSessionProjectionPayloadV1:
    return c9.build_agent_session_payload(
        _session_source(),
        declared_losses=(
            _loss("events.terminal_ref", loss_kind=c9.LOSS_KIND_NOT_EXECUTED),
        ),
    )


def _graph_payload() -> c9.ResearchGraphProjectionPayloadV1:
    return c9.build_research_graph_payload(
        _graph_source(),
        declared_losses=(
            _loss("objects.label", reason="projected labels are bounded"),
        ),
    )


def _search_payload() -> c9.SearchProjectionPayloadV1:
    return c9.build_search_payload(
        _search_source(),
        declared_losses=(_loss("segments.text", loss_kind=c9.LOSS_KIND_OMITTED_FIELD),),
    )


def _flatten_keys(value: object, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(f"{prefix}{key}")
            keys.update(_flatten_keys(item, f"{prefix}{key}."))
    elif isinstance(value, list):
        for item in value:
            keys.update(_flatten_keys(item, prefix))
    return keys


def test_canonical_json_is_deterministic_with_string_keys_and_finite_values() -> None:
    left = {"b": 1, "a": [1, 2.5, None, True], "nested": {"z": "x"}}
    right = {"a": [1, 2.5, None, True], "b": 1, "nested": {"z": "x"}}
    assert c9.canonical_json(left) == c9.canonical_json(right)
    assert c9.canonical_json(left) == json.dumps(
        left, sort_keys=True, separators=(",", ":")
    )
    with pytest.raises(ValueError, match="non-finite"):
        c9.canonical_json({"value": float("nan")})
    with pytest.raises(TypeError, match="string dictionary keys"):
        c9.canonical_json({1: "not-a-string-key"})
    with pytest.raises(TypeError, match="unsupported canonical JSON value"):
        c9.canonical_json({"value": object()})


def test_runtime_terminal_status_derives_only_from_event_chain() -> None:
    terminal_events = (
        _event(0, c9.SESSION_CREATED, "e0"),
        _event(1, c9.SESSION_TERMINAL_SUCCEEDED, "e1"),
    )
    source = _session_source(events=terminal_events)
    assert source.terminal_event is not None
    assert source.terminal_event.event_ref == "e1"
    payload = c9.build_agent_session_payload(
        source,
        declared_losses=(
            _loss("events.terminal_ref", loss_kind=c9.LOSS_KIND_NOT_EXECUTED),
        ),
    )
    assert payload.status == c9.SESSION_STATUS_TERMINAL_SUCCEEDED
    assert payload.terminal_event_ref == "e1"

    running = _session_source()
    assert running.terminal_event is None
    running_payload = c9.build_agent_session_payload(
        running,
        declared_losses=(
            _loss("events.terminal_ref", loss_kind=c9.LOSS_KIND_NOT_EXECUTED),
        ),
    )
    assert running_payload.status == c9.SESSION_STATUS_RUNNING
    assert running_payload.terminal_event_ref is None

    with pytest.raises(ValueError, match="terminal runtime event must be the last"):
        _session_source(
            events=(
                _event(0, c9.SESSION_TERMINAL_FAILED, "e0"),
                _event(1, c9.SESSION_CREATED, "e1"),
            )
        )
    with pytest.raises(ValueError, match="more than one terminal event"):
        _session_source(
            events=(
                _event(0, c9.SESSION_TERMINAL_SUCCEEDED, "e0"),
                _event(1, c9.SESSION_TERMINAL_FAILED, "e1"),
            )
        )


def test_session_payload_digest_is_deterministic_and_identity_sensitive() -> None:
    first = _session_payload()
    second = _session_payload()
    assert first.payload_digest == second.payload_digest
    assert first.closure_ref == second.closure_ref
    assert HEX64.match(first.payload_digest)
    assert HEX64.match(first.closure_ref)
    assert HEX64.match(first.source_digest)

    other = c9.build_agent_session_payload(
        _session_source(session_ref="sess-2"),
        declared_losses=(
            _loss("events.terminal_ref", loss_kind=c9.LOSS_KIND_NOT_EXECUTED),
        ),
    )
    assert other.payload_digest != first.payload_digest
    assert other.closure_ref != first.closure_ref


def test_identity_mutation_fails_closed() -> None:
    source = _session_source()
    with pytest.raises(ValueError, match="identity/revision/incarnation closure"):
        dataclasses.replace(source, session_ref="mutated-session")
    with pytest.raises(ValueError, match="identity/revision/incarnation closure"):
        dataclasses.replace(source, revision="r2")

    payload = _session_payload()
    with pytest.raises(ValueError, match="identity/revision/incarnation closure"):
        dataclasses.replace(payload, session_ref="mutated-session")


def test_graph_payload_keeps_objects_and_relations_one_to_one() -> None:
    source = _graph_source()
    payload = _graph_payload()
    assert [obj.object_id for obj in payload.objects] == [
        obj.object_id for obj in source.objects
    ]
    assert [rel.relation_id for rel in payload.relations] == [
        rel.relation_id for rel in source.relations
    ]
    assert len(payload.relations) == len(source.relations)
    assert HEX64.match(payload.payload_digest)

    with pytest.raises(ValueError, match="does not exist in the same source"):
        c9.ResearchGraphSourceV1(
            schema_version=c9.RESEARCH_GRAPH_SOURCE_SCHEMA,
            project_scope_ref="proj-a",
            graph_ref="graph-dangling",
            revision="r1",
            incarnation="inc-1",
            objects=(_object("o1", "alpha"),),
            relations=(_relation("r1", "o1", "missing"),),
        )


def test_search_segments_carry_field_path_and_not_executed_statuses() -> None:
    source = _search_source()
    assert all(
        segment.field_path == "payload.structured_material.body"
        for segment in source.segments
    )
    assert all(
        segment.provider_status == c9.NOT_EXECUTED for segment in source.segments
    )
    assert all(
        segment.vectorization_status == c9.NOT_EXECUTED for segment in source.segments
    )
    payload = _search_payload()
    assert payload.provider_status == c9.NOT_EXECUTED
    assert payload.vectorization_status == c9.NOT_EXECUTED
    keys = _flatten_keys(payload.to_plain())
    assert "provider_status" in keys
    assert "vectorization_status" in keys
    for forbidden in ("provider", "model", "embedding", "vector", "provider_id"):
        assert forbidden not in keys

    with pytest.raises(ValueError, match="provider_status must be NOT_EXECUTED"):
        c9.C7SearchSourceV1(
            schema_version=c9.C7_SEARCH_SOURCE_SCHEMA,
            project_scope_ref="proj-a",
            search_ref="search-1",
            revision="r1",
            incarnation="inc-1",
            segments=(_segment("s1"),),
            provider_status="EXECUTED",
        )


def test_field_level_loss_records_are_bound_to_payloads() -> None:
    payload = _session_payload()
    assert payload.declared_losses
    loss = payload.declared_losses[0]
    assert loss.field_path == "events.terminal_ref"
    assert loss.loss_kind == c9.LOSS_KIND_NOT_EXECUTED
    assert HEX64.match(loss.loss_digest)

    with pytest.raises(ValueError, match="unsupported projection loss kind"):
        _loss("events", loss_kind="UNKNOWN_LOSS")
    with pytest.raises(ValueError, match="requires declared field losses"):
        c9.build_agent_session_payload(_session_source(), declared_losses=())


def test_unknown_types_and_kinds_fail_closed() -> None:
    with pytest.raises(TypeError, match="requires RuntimeSessionSourceV1"):
        c9.build_agent_session_payload(
            None,  # type: ignore[arg-type]
            declared_losses=(_loss("events"),),
        )
    with pytest.raises(TypeError, match="requires ResearchGraphSourceV1"):
        c9.build_research_graph_payload(
            _session_source(),  # type: ignore[arg-type]
            declared_losses=(_loss("objects"),),
        )
    with pytest.raises(TypeError, match="requires C7SearchSourceV1"):
        c9.build_search_payload(
            _graph_source(),  # type: ignore[arg-type]
            declared_losses=(_loss("segments"),),
        )
    with pytest.raises(ValueError, match="unsupported runtime event kind"):
        _session_source(events=(_event(0, "UNKNOWN_EVENT", "e0"),))
    with pytest.raises(ValueError, match="unsupported search segment kind"):
        c9.C7SearchSegmentV1(
            schema_version=c9.C7_SEARCH_SEGMENT_SCHEMA,
            segment_id="s1",
            field_path="payload.body",
            segment_text="text",
            segment_kind="UNKNOWN_SEGMENT",
        )


def test_c8_coverage_flags_are_non_empty_and_closed() -> None:
    source = _session_source()
    assert source.coverage_incomplete_flags == (c9.C8_COVERAGE_INCOMPLETE_SESSION,)
    closure = c9.C9SemanticSourceClosureV1(
        schema_version=c9.C9_SEMANTIC_SOURCE_CLOSURE_SCHEMA,
        project_scope_ref="proj-a",
        closure_id="closure-1",
        revision="r1",
        incarnation="inc-1",
        runtime_session_source=source,
        research_graph_source=_graph_source(),
        c7_search_source=_search_source(),
    )
    assert set(closure.coverage_incomplete_flags) == set(
        c9.C8_COVERAGE_INCOMPLETE_FLAGS
    )
    assert HEX64.match(closure.closure_digest)
    assert HEX64.match(closure.closure_ref)

    with pytest.raises(ValueError, match="unsupported coverage flag"):
        c9.RuntimeSessionSourceV1(
            schema_version=c9.RUNTIME_SESSION_SOURCE_SCHEMA,
            project_scope_ref="proj-a",
            session_ref="sess-1",
            revision="r1",
            incarnation="inc-1",
            events=(_event(0, c9.SESSION_CREATED, "e0"),),
            coverage_incomplete_flags=("C8.UNKNOWN_FLAG",),
        )
    with pytest.raises(ValueError, match="must share project_scope_ref"):
        c9.C9SemanticSourceClosureV1(
            schema_version=c9.C9_SEMANTIC_SOURCE_CLOSURE_SCHEMA,
            project_scope_ref="proj-a",
            closure_id="closure-1",
            revision="r1",
            incarnation="inc-1",
            runtime_session_source=_session_source(),
            research_graph_source=c9.ResearchGraphSourceV1(
                schema_version=c9.RESEARCH_GRAPH_SOURCE_SCHEMA,
                project_scope_ref="other-project",
                graph_ref="graph-1",
                revision="r1",
                incarnation="inc-1",
                objects=(_object("o1", "alpha"), _object("o2", "beta")),
                relations=(_relation("r1", "o1", "o2"),),
            ),
            c7_search_source=_search_source(),
        )


def test_cross_family_coverage_flags_cannot_substitute_required_flag() -> None:
    session_flag = c9.C8_COVERAGE_INCOMPLETE_SESSION
    graph_flag = c9.C8_COVERAGE_INCOMPLETE_GRAPH
    search_flag = c9.C8_COVERAGE_INCOMPLETE_SEARCH

    with pytest.raises(ValueError, match="must include required C8 coverage flag"):
        c9.ResearchGraphSourceV1(
            schema_version=c9.RESEARCH_GRAPH_SOURCE_SCHEMA,
            project_scope_ref="proj-a",
            graph_ref="graph-wrong-flag",
            revision="r1",
            incarnation="inc-1",
            objects=(_object("o1", "alpha"), _object("o2", "beta")),
            relations=(_relation("r1", "o1", "o2"),),
            coverage_incomplete_flags=(session_flag,),
        )
    with pytest.raises(ValueError, match="must include required C8 coverage flag"):
        c9.C7SearchSourceV1(
            schema_version=c9.C7_SEARCH_SOURCE_SCHEMA,
            project_scope_ref="proj-a",
            search_ref="search-wrong-flag",
            revision="r1",
            incarnation="inc-1",
            segments=(_segment("s1"),),
            coverage_incomplete_flags=(graph_flag,),
        )
    with pytest.raises(ValueError, match="must include required C8 coverage flag"):
        c9.RuntimeSessionSourceV1(
            schema_version=c9.RUNTIME_SESSION_SOURCE_SCHEMA,
            project_scope_ref="proj-a",
            session_ref="sess-wrong-flag",
            revision="r1",
            incarnation="inc-1",
            events=(_event(0, c9.SESSION_CREATED, "e0"),),
            coverage_incomplete_flags=(search_flag,),
        )

    with pytest.raises(ValueError, match="must include required C8 coverage flag"):
        dataclasses.replace(_session_payload(), coverage_incomplete_flags=(graph_flag,))
    with pytest.raises(ValueError, match="must include required C8 coverage flag"):
        dataclasses.replace(_graph_payload(), coverage_incomplete_flags=(search_flag,))
    with pytest.raises(ValueError, match="must include required C8 coverage flag"):
        dataclasses.replace(
            _search_payload(), coverage_incomplete_flags=(session_flag,)
        )


def test_extra_legal_coverage_flags_are_allowed_alongside_required_flag() -> None:
    graph_source = c9.ResearchGraphSourceV1(
        schema_version=c9.RESEARCH_GRAPH_SOURCE_SCHEMA,
        project_scope_ref="proj-a",
        graph_ref="graph-extra",
        revision="r1",
        incarnation="inc-1",
        objects=(_object("o1", "alpha"), _object("o2", "beta")),
        relations=(_relation("r1", "o1", "o2"),),
        coverage_incomplete_flags=(
            c9.C8_COVERAGE_INCOMPLETE_GRAPH,
            c9.C8_COVERAGE_INCOMPLETE_SEARCH,
        ),
    )
    assert graph_source.coverage_incomplete_flags == (
        c9.C8_COVERAGE_INCOMPLETE_GRAPH,
        c9.C8_COVERAGE_INCOMPLETE_SEARCH,
    )
    graph_payload = c9.build_research_graph_payload(
        graph_source,
        declared_losses=(_loss("objects.label"),),
    )
    assert c9.C8_COVERAGE_INCOMPLETE_GRAPH in graph_payload.coverage_incomplete_flags
    assert c9.C8_COVERAGE_INCOMPLETE_SEARCH in graph_payload.coverage_incomplete_flags

    session_source = c9.RuntimeSessionSourceV1(
        schema_version=c9.RUNTIME_SESSION_SOURCE_SCHEMA,
        project_scope_ref="proj-a",
        session_ref="sess-extra",
        revision="r1",
        incarnation="inc-1",
        events=(
            _event(0, c9.SESSION_CREATED, "e0"),
            _event(1, c9.SESSION_TASK_ASSIGNED, "e1"),
        ),
        coverage_incomplete_flags=(
            c9.C8_COVERAGE_INCOMPLETE_SESSION,
            c9.C8_COVERAGE_INCOMPLETE_GRAPH,
        ),
    )
    session_payload = c9.build_agent_session_payload(
        session_source,
        declared_losses=(
            _loss("events.terminal_ref", loss_kind=c9.LOSS_KIND_NOT_EXECUTED),
        ),
    )
    assert (
        c9.C8_COVERAGE_INCOMPLETE_SESSION in session_payload.coverage_incomplete_flags
    )
    assert c9.C8_COVERAGE_INCOMPLETE_GRAPH in session_payload.coverage_incomplete_flags


def test_payloads_have_no_generic_inputs_manifest() -> None:
    for payload in (_session_payload(), _graph_payload(), _search_payload()):
        plain = payload.to_plain()
        assert "inputs" not in plain
        assert "inputs" not in _flatten_keys(plain)
        json.dumps(plain)


def test_payload_schemas_are_semantically_distinct() -> None:
    session_plain = _session_payload().to_plain()
    graph_plain = _graph_payload().to_plain()
    search_plain = _search_payload().to_plain()
    assert session_plain["schema_version"] == c9.AGENT_SESSION_PROJECTION_PAYLOAD_SCHEMA
    assert graph_plain["schema_version"] == c9.RESEARCH_GRAPH_PROJECTION_PAYLOAD_SCHEMA
    assert search_plain["schema_version"] == c9.SEARCH_PROJECTION_PAYLOAD_SCHEMA
    assert "events" in session_plain
    assert "objects" in graph_plain and "relations" in graph_plain
    assert "segments" in search_plain
