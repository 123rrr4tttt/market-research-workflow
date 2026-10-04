from __future__ import annotations

from datetime import datetime, UTC
from unittest.mock import patch

import pytest

from app.services.agent_core.contracts import CoreToolResult
from app.services.information_topology.contracts import topology_failures
from app.services.information_topology.modules.retrieval import profile_from_state_payload
from app.services.information_topology.profiles import decode_state
from functorial_kit import Failure
from app.services.project_retrieval.execution import _ingest_failure_receipt, execute_retrieval_run
from app.services.project_retrieval.mode import compile_preview, load_mode


def test_build_topology_service_only_assembles_existing_dependencies(monkeypatch):
    from app.services.information_topology.service import InformationTopologyService
    from app.services.project_retrieval import topology

    def forbidden_session():
        raise AssertionError("construction must not open a DB session")

    monkeypatch.setattr(topology, "SessionLocal", forbidden_session)
    service = topology.build_topology_service()
    assert isinstance(service, InformationTopologyService)
    assert service.dependencies.session_factory is forbidden_session


def test_skill_adapter_rejects_cross_project_key(monkeypatch):
    from app.services.project_retrieval import skill
    from app.services.project_retrieval.service import RetrievalError

    monkeypatch.setattr(skill, "current_project_key", lambda: "project-a")
    with pytest.raises(RetrievalError) as error:
        skill.current({"project_key": "project-b"})
    assert (error.value.code, error.value.status) == ("PROJECT_MISMATCH", 404)


def test_project_retrieval_service_lifts_typed_failures():
    from app.services.project_retrieval.service import ProjectRetrievalService, RetrievalError

    service = ProjectRetrievalService(session_factory=lambda: pytest.fail("invalid request must not open a session"))
    with pytest.raises(RetrievalError) as error:
        service.start("project-a", plan_id="plan-a", idempotency_key="")
    assert (error.value.code, error.value.status) == ("INVALID_IDEMPOTENCY_KEY", 422)


def test_project_retrieval_current_preserves_unresolved_integrity_error(monkeypatch):
    from sqlalchemy.exc import IntegrityError
    from app.services.project_retrieval import mode
    from app.services.project_retrieval.service import ProjectRetrievalService

    conflict = IntegrityError("INSERT", {}, RuntimeError("concurrent insert"))

    class Session:
        def scalar(self, _statement):
            return None

        def add(self, _row):
            pass

        def commit(self):
            raise conflict

        def rollback(self):
            pass

    monkeypatch.setattr(mode, "load_mode", lambda _project_key: {
        "mode_id": "mode-a", "version": "1", "source_revision": "digest-a",
    })
    with pytest.raises(IntegrityError) as error:
        ProjectRetrievalService()._current(Session(), "project-a")
    assert error.value is conflict


class _Store:
    def __init__(self, *, fail_report=False):
        self.artifacts = []
        self.fail_report = fail_report

    def upsert_artifact(self, item):
        if self.fail_report and item["name"] == "project_retrieval.run_report.json":
            raise RuntimeError
        self.artifacts.append(item)
        return item


class _SessionService:
    def __init__(self, *, fail_report=False):
        self.store = _Store(fail_report=fail_report)
        self.created = []

    def create_session(self, **kwargs):
        self.created.append(kwargs)
        return {"session": {"session_id": "session-1", "project_key": kwargs["project_key"], "root_task_id": "task-1"}}

    def claim_task(self, session_id, task_id, *, owner):
        return {"status": "running"}

    def release_task(self, session_id, task_id, **kwargs):
        self.released = kwargs
        return {"status": kwargs["status"]}


class _Registry:
    def __init__(self, *, search_status="completed", review_payload=True, followup_query=None):
        self.calls = []
        self.search_status = search_status
        self.review_payload = review_payload
        self.followup_query = followup_query

    def get(self, name):
        return {"name": name}

    def execute_tool(self, *, tool_call, tool_spec, request, emit):
        self.calls.append((tool_call.tool_name, dict(tool_call.arguments)))
        name = tool_call.tool_name
        body = {}
        status = "completed"
        if name == "source.web.search":
            status = self.search_status
            body = (
                {
                    "candidates": [
                        {"url": "https://example.org/source", "title": "Source", "trust": {"status": "accepted"}}
                    ]
                }
                if status == "completed"
                else {}
            )
        elif name == "source.candidate.review":
            body = (
                {"ingest_payload": {"type": "url_pool", "url": "https://example.org/source"}}
                if self.review_payload
                else {}
            )
        elif name == "source.discovery.plan":
            body = {"search_queries": [{"query": self.followup_query}]} if self.followup_query else {}
        elif name == "ingest.url_pool.submit":
            body = {"dispatch_result": {"document_id": 42, "status": "success"}}
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=name,
            status=status,
            model_summary=f"{name}: {status}",
            structured_content=body,
            error={"code": "PROVIDER_DOWN"} if status == "failed" else None,
        )


class _Topology:
    def __init__(self, *, conflict=False):
        self.writes = []
        self.conflict = conflict
        self.current = None

        class _DocumentSession:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def get(self, model, document_id):
                return type(
                    "Document",
                    (),
                    {
                        "content": "A primary source body.",
                        "title": "Source",
                        "uri": "https://example.org/source",
                        "updated_at": datetime(2026, 9, 26, tzinfo=UTC),
                    },
                )()

        self.dependencies = type("Dependencies", (), {"session_factory": _DocumentSession})()

    def read_topology(self, project_key, target, filters):
        return self.current if self.current is not None else topology_failures.fail("NOT_FOUND", "new run state")

    def apply_batch(self, project_key, **kwargs):
        self.writes.append((project_key, kwargs))
        if self.conflict:
            return topology_failures.fail("VERSION_CONFLICT", "concurrent write")
        wire = {"kind": "information_topology.state.v1", **kwargs["state_patches"][0]["initial_state"]}
        profile = profile_from_state_payload(project_key, wire["profile_id"], wire["profile_version"], wire)
        assert not isinstance(profile, Failure)
        assert not isinstance(decode_state(profile, wire), Failure)
        self.current = {"revision": 1, "digest": "committed-digest", "topology": wire}
        return {"state_revisions": [{"revision": 1}]}


def _plan():
    return {
        "plan_id": "p1",
        "mode_id": "m1",
        "mode_version": "1",
        "route_id": "r1",
        "query_ids": ["q1", "q2"],
        "queries": [
            {"query_id": "q1", "route_id": "r1", "expression": "water policy", "language": "en"},
            {"query_id": "q2", "route_id": "r1", "expression": "water report", "language": "en"},
        ],
        "limits": {"max_queries": 1, "max_materials": 1, "max_followups": 0},
        "topology_ref": {"module_id": "retrieval", "namespace": "rapid", "state_id": "retrieval-run:run-1"},
        "binding_snapshot": {
            "routes": [
                {
                    "route_id": "r1",
                    "pool": "A",
                    "outline_sections": ["1"],
                    "node_types": ["现场"],
                    "target_edges": ["关联"],
                }
            ]
        },
        "topology_seed": {
            "domain_vocabulary": {
                "域名": "Example",
                "节点类型": ["现场"],
                "边类型": ["关联"],
                "问题意识视角": ["供水"],
                "大纲节": ["1"],
                "池": ["A"],
                "档": ["甲"],
            },
            "domain_source_ref": {
                "ref": {
                    "project_key": "example",
                    "module_id": "retrieval",
                    "namespace": "brief",
                    "type_id": "source",
                    "local_id": "brief",
                },
                "observed_revision": "source-1",
                "content_digest": None,
            },
            "source_routes": [{"route_id": "r1", "pool": "A", "status": "planned"}],
            "keyword_plans": [
                {
                    "plan_id": "q1",
                    "kind": "query",
                    "expression": "water policy",
                    "execution_status": "not_executed",
                    "source_route_id": "r1",
                }
            ],
        },
    }


def test_run_uses_registered_tools_writes_only_actual_attempt_and_preserves_formal_gap():
    service, registry, topology = _SessionService(), _Registry(), _Topology()
    with (
        patch("app.services.project_retrieval.execution.build_project_core_tool_registry", return_value=registry),
        patch(
            "app.services.project_retrieval.execution.invoke_skill",
            return_value={"result": {"status": "no_claim", "gaps": ["insufficient relation"]}},
        ),
    ):
        out = execute_retrieval_run(
            project_key="example", plan=_plan(), topology_service=topology, session_factory=lambda: service
        )

    assert len(service.created) == 1
    assert [name for name, _ in registry.calls] == [
        "source.discovery.plan",
        "source.web.search",
        "source.candidate.review",
        "ingest.url_pool.submit",
    ]
    assert registry.calls[-1][1]["async_mode"] is False
    assert len(out["attempts"]) == 1 and out["attempts"][0]["result"] == "hit"
    assert out["materials"][0]["document_id"] == 42
    assert out["materials"][0]["status"] == "body_read"
    assert out["graph"] is None and out["report"]["formal_graph_refs"] == []
    assert out["status"] == "partial"
    assert out["gaps"][0]["code"] == "NO_CLAIM"
    target = topology.writes[0][1]["state_patches"][0]
    assert target["base_revision"] is None
    assert target["target"]["state_id"] == "retrieval-run:run-1"
    assert [element["ref"]["ref"]["type_id"] for element in target["initial_state"]["elements"]] == [
        "domain_vocabulary",
        "source_route",
        "keyword_plan",
        "attempt",
    ]
    assert any(item["artifact_type"] == "project_retrieval_search_receipt" for item in service.store.artifacts)


def test_bound_source_does_not_enter_a_run_without_a_search_hit():
    class EmptySearch(_Registry):
        def execute_tool(self, *, tool_call, tool_spec, request, emit):
            result = super().execute_tool(tool_call=tool_call, tool_spec=tool_spec, request=request, emit=emit)
            if tool_call.tool_name == "source.web.search":
                return CoreToolResult(
                    call_id=result.call_id,
                    tool_name=result.tool_name,
                    status="completed",
                    model_summary="no live hits",
                    structured_content={"candidates": []},
                )
            return result

    plan = _plan()
    plan["binding_snapshot"]["source_registry"] = [{
        "source_id": "source-1", "route_ids": ["r1"],
        "name": "Historical source", "url": "https://example.org/source",
    }]
    service, registry, topology = _SessionService(), EmptySearch(), _Topology()
    with patch("app.services.project_retrieval.execution.build_project_core_tool_registry", return_value=registry):
        out = execute_retrieval_run(
            project_key="example", plan=plan, topology_service=topology, session_factory=lambda: service,
        )

    assert [name for name, _ in registry.calls] == ["source.discovery.plan", "source.web.search"]
    assert out["attempts"][0]["result"] == "miss"
    assert out["candidates"] == []
    assert out["materials"] == []
    assert out["report"]["formal_graph_refs"] == []


def test_rejected_candidates_do_not_consume_material_budget():
    class RejectedSearch(_Registry):
        def execute_tool(self, *, tool_call, tool_spec, request, emit):
            result = super().execute_tool(tool_call=tool_call, tool_spec=tool_spec, request=request, emit=emit)
            if tool_call.tool_name == "source.web.search":
                return CoreToolResult(
                    call_id=result.call_id,
                    tool_name=result.tool_name,
                    status="completed",
                    model_summary="two blocked results",
                    structured_content={"candidates": [
                        {"url": f"https://example.org/{index}", "trust": {"status": "rejected"}}
                        for index in range(2)
                    ]},
                )
            return result

    service, registry, topology = _SessionService(), RejectedSearch(), _Topology()
    with patch("app.services.project_retrieval.execution.build_project_core_tool_registry", return_value=registry):
        out = execute_retrieval_run(
            project_key="example", plan=_plan(), topology_service=topology, session_factory=lambda: service,
        )

    assert len(out["candidates"]) == 2
    assert out["materials"] == []
    assert not any(gap["code"] == "MATERIAL_BUDGET_EXHAUSTED" for gap in out["gaps"])


def test_source_failure_and_version_conflict_keep_distinct_receipts():
    service, registry, topology = _SessionService(), _Registry(search_status="failed"), _Topology(conflict=True)
    with patch("app.services.project_retrieval.execution.build_project_core_tool_registry", return_value=registry):
        out = execute_retrieval_run(
            project_key="example", plan=_plan(), topology_service=topology, session_factory=lambda: service
        )

    assert out["attempts"][0]["result"] == "access_failed"
    assert out["materials"] == []
    assert {item["kind"] for item in out["failures"]} == {"source_failure", "structure_conflict"}
    assert out["topology_write"]["error"]["code"] == "VERSION_CONFLICT"
    assert out["graph"] is None


def test_existing_topology_identity_is_never_patched():
    class Existing(_Topology):
        def read_topology(self, project_key, target, filters):
            return {"revision": 3, "topology": {"profile_id": "retrieval.domain.example"}}

    service, registry, topology = _SessionService(), _Registry(), Existing()
    with patch("app.services.project_retrieval.execution.build_project_core_tool_registry", return_value=registry):
        out = execute_retrieval_run(
            project_key="example", plan=_plan(), topology_service=topology, session_factory=lambda: service
        )
    assert topology.writes == []
    assert out["topology_write"]["error"]["code"] == "IDENTITY_CONFLICT"


def _formal_proposal(excerpt="A primary source body."):
    return {
        "status": "proposed",
        "proposal": {
            "nodes": [
                {"local_key": "scene", "name": "Water supply site", "type_id": "node:现场"},
                {"local_key": "actor", "name": "Water agency", "type_id": "node:现场"},
            ],
            "judgment": {
                "from_key": "scene",
                "to_key": "actor",
                "edge_type": "关联",
                "judgment": "The source records their relation",
                "scope": "This document",
                "outline_section": "1",
                "pools": ["A"],
                "relation_classes": ["证据网"],
            },
            "evidence": {
                "original_location": "document paragraph 1",
                "original_excerpt": excerpt,
                "grade": "甲",
                "conflict": False,
                "effect": "支持",
                "applicable_scope": "This document",
                "inference_note": "Directly stated in the body",
                "proves": "事实关系",
                "source_role": "直接记录",
                "independence_group": "source-1",
            },
            "clue": {"name": "Water relation", "scene_key": "scene"},
        },
        "gaps": [],
    }


def test_formal_proposal_writes_and_reads_back_validated_group_once():
    service, registry, topology = _SessionService(), _Registry(), _Topology()
    with (
        patch("app.services.project_retrieval.execution.build_project_core_tool_registry", return_value=registry),
        patch(
            "app.services.project_retrieval.execution.invoke_skill", return_value={"result": _formal_proposal()}
        ) as formalizer,
    ):
        out = execute_retrieval_run(
            project_key="example", plan=_plan(), topology_service=topology, session_factory=lambda: service
        )
    assert formalizer.call_args.kwargs["payload"]["body"] == "A primary source body."
    assert out["status"] == "completed"
    assert out["report"]["formal_graph_refs"][0]["material"]
    assert out["topology_write"]["state_digest"] == "committed-digest"
    assert len(topology.writes) == 1
    types = [
        element["ref"]["ref"]["type_id"]
        for element in topology.writes[0][1]["state_patches"][0]["initial_state"]["elements"]
    ]
    assert types.count("material") == types.count("judgment") == types.count("evidence") == types.count("clue") == 1
    assert "A primary source body." not in str(out)


def test_unlocated_quote_is_rejected_without_formal_graph_refs():
    service, registry, topology = _SessionService(), _Registry(), _Topology()
    with (
        patch("app.services.project_retrieval.execution.build_project_core_tool_registry", return_value=registry),
        patch(
            "app.services.project_retrieval.execution.invoke_skill",
            return_value={"result": _formal_proposal("Not in document")},
        ),
    ):
        out = execute_retrieval_run(
            project_key="example", plan=_plan(), topology_service=topology, session_factory=lambda: service
        )
    assert out["status"] == "partial"
    assert out["report"]["formal_graph_refs"] == []
    assert out["gaps"][0]["code"] == "FORMAL_PROPOSAL_REJECTED"
    assert out["gaps"][0]["error"]["code"] == "EVIDENCE_QUOTE_NOT_LOCATED"


def test_registered_formalizer_receives_real_body_and_commits_profile_valid_state():
    service, registry, topology = _SessionService(), _Registry(), _Topology()
    proposal = _formal_proposal()

    class _Model:
        def invoke(self, prompt):
            assert "A primary source body." in prompt
            return proposal

    with (
        patch("app.services.project_retrieval.execution.build_project_core_tool_registry", return_value=registry),
        patch("app.services.llm.provider.get_chat_model", return_value=_Model()),
    ):
        out = execute_retrieval_run(
            project_key="example", plan=_plan(), topology_service=topology, session_factory=lambda: service
        )
    assert out["status"] == "completed"
    assert len(out["report"]["formal_graph_refs"]) == 1
    assert out["report"]["formal_graph_refs"][0]["document_updated_at"] == "2026-09-26T00:00:00+00:00"


def test_missing_review_ingest_payload_is_a_gap():
    service, registry, topology = _SessionService(), _Registry(review_payload=False), _Topology()
    with patch("app.services.project_retrieval.execution.build_project_core_tool_registry", return_value=registry):
        out = execute_retrieval_run(
            project_key="example", plan=_plan(), topology_service=topology, session_factory=lambda: service
        )
    assert out["materials"] == []
    assert out["gaps"][0]["code"] == "CANDIDATE_INGEST_PAYLOAD_MISSING"
    assert out["status"] == "partial"


def test_followup_uses_remaining_query_budget_and_no_gap_skips_followup():
    plan = _plan()
    plan["query_ids"] = ["q1"]
    plan["limits"] = {"max_queries": 3, "max_materials": 1, "max_followups": 2}
    service, registry, topology = _SessionService(), _Registry(followup_query="water policy additional"), _Topology()
    with (
        patch("app.services.project_retrieval.execution.build_project_core_tool_registry", return_value=registry),
        patch(
            "app.services.project_retrieval.execution.invoke_skill",
            return_value={"result": {"status": "no_claim", "gaps": ["missing relation"]}},
        ),
    ):
        out = execute_retrieval_run(
            project_key="example", plan=plan, topology_service=topology, session_factory=lambda: service
        )
    assert len(out["attempts"]) == 2
    assert out["followup_rounds"] == 1
    assert len(out["materials"]) == 1
    assert any(item["code"] == "FOLLOWUP_QUERY_UNAVAILABLE" for item in out["gaps"])
    assert any(
        element["attributes"].get("kind") == "followup"
        for element in topology.writes[0][1]["state_patches"][0]["initial_state"]["elements"]
    )

    service, registry, topology = _SessionService(), _Registry(followup_query="water policy additional"), _Topology()
    with (
        patch("app.services.project_retrieval.execution.build_project_core_tool_registry", return_value=registry),
        patch("app.services.project_retrieval.execution.invoke_skill", return_value={"result": _formal_proposal()}),
    ):
        out = execute_retrieval_run(
            project_key="example", plan=plan, topology_service=topology, session_factory=lambda: service
        )
    assert out["status"] == "completed"
    assert out["followup_rounds"] == 0
    assert [name for name, _ in registry.calls].count("source.discovery.plan") == 1


def test_report_artifact_failure_prevents_completed_status():
    service, registry, topology = _SessionService(fail_report=True), _Registry(), _Topology()
    with (
        patch("app.services.project_retrieval.execution.build_project_core_tool_registry", return_value=registry),
        patch("app.services.project_retrieval.execution.invoke_skill", return_value={"result": _formal_proposal()}),
    ):
        out = execute_retrieval_run(
            project_key="example", plan=_plan(), topology_service=topology, session_factory=lambda: service
        )
    assert out["status"] == "partial"
    assert out["report"]["formal_graph_refs"]
    assert any(item["code"] == "REPORT_PERSISTENCE_FAILED" for item in out["gaps"])


def test_hk_snapshot_sources_are_annotations_and_new_attempt_is_profile_valid():
    snapshot = load_mode("hk_water_investigation")
    route_id = next(route["route_id"] for route in snapshot["routes"] if route["status"] == "active")
    plan = compile_preview(
        snapshot, route_id=route_id, limits={"max_queries": 1, "max_materials": 1, "max_followups": 0}
    )
    plan["topology_ref"] = {"module_id": "retrieval", "namespace": "rapid", "state_id": "retrieval-run:hk-fixture"}
    service, registry, topology = _SessionService(), _Registry(search_status="failed"), _Topology()
    with patch("app.services.project_retrieval.execution.build_project_core_tool_registry", return_value=registry):
        out = execute_retrieval_run(
            project_key="hk_water_investigation", plan=plan, topology_service=topology, session_factory=lambda: service
        )

    assert len(out["attempts"]) == 1
    assert out["topology_write"]["status"] == "completed"
    elements = topology.writes[0][1]["state_patches"][0]["initial_state"]["elements"]
    kinds = [element["ref"]["ref"]["type_id"] for element in elements]
    assert kinds.count("source_registry") == len(plan["topology_seed"]["source_registry"])
    assert kinds.count("attempt") == 1
    assert all(
        element["attributes"]["status"] == "historically_verified"
        for element in elements
        if element["ref"]["ref"]["type_id"] == "source_registry"
    )


def test_ingest_failure_receipt_does_not_copy_pdf_bytes_into_run_errors():
    dispatch = {"status": "failed", "records": [{"content_text": "%PDF-1.5 binary body"}],
                "postprocess_frontdoor": {"meta": {"reason_code": "light_filter_rejected"}}}
    receipt = _ingest_failure_receipt(dispatch, {"status": "completed"})
    assert receipt == {"code": "INGEST_REJECTED", "status": "failed",
                       "reason_code": "light_filter_rejected"}
    assert "%PDF" not in str(receipt)


def test_query_catalog_web_search_preserves_provider_effect_and_readback(monkeypatch):
    import socket

    from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
    from app.services.agent_core import query_tools
    from app.services.agent_core.registry import CoreToolRegistry
    from app.services.agent_sessions.service import AgentSessionService
    from app.services.agent_sessions.store import InMemoryAgentSessionStore
    from app.successor_runtime.capabilities.retrieval_common import (
        Candidate,
        CandidateBundle,
        ProviderObservation,
    )

    service = AgentSessionService(store=InMemoryAgentSessionStore())
    bundle = service.create_session(
        source="user",
        entrypoint_type="agent_core",
        goal="external source search",
        project_key="example",
        task_blueprints=[],
    )
    registry = CoreToolRegistry()
    assert query_tools.register_query_project_tools(registry=registry, service=service) is None

    def discover(request):
        assert request.topic == "water policy evidence"
        assert request.provider == "searxng"
        assert request.project_ref == "example"
        return CandidateBundle(
            request=request,
            candidates=(
                Candidate(
                    resource_uri="https://example.org/source",
                    title="Source",
                    snippet="Primary source",
                    source="searxng",
                    keyword="water policy",
                    original_rank=1,
                    result_rank=1,
                    relevance_score=1.0,
                    raw={"link": "https://example.org/source", "title": "Source"},
                ),
            ),
            occurrences=(),
            observations=(
                ProviderObservation(
                    provider="searxng",
                    route="explicit:searxng",
                    keyword="water policy",
                    status="completed",
                    returned_count=1,
                ),
            ),
            stop_reason="limit_reached",
        )

    monkeypatch.setattr(query_tools, "discover_candidates", discover)
    monkeypatch.setattr(
        "app.services.source_library.external_project.socket.getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    result = registry.execute_tool(
        tool_call=CoreToolCall(
            tool_name="source.web.search",
            call_id="call-query-web-search",
            arguments={
                "project_key": "example",
                "query": "water policy evidence",
                "provider": "searxng",
                "max_results": 1,
            },
        ),
        tool_spec=registry.get("source.web.search"),
        request=AgentCoreRequest(
            message="search source",
            session_id=bundle["session"]["session_id"],
            project_key="example",
        ),
        emit=lambda _event: None,
    )
    content = result.structured_content
    assert result.status == "completed"
    assert content["external_network_io"] is True
    assert content["project_write_performed"] is False
    assert content["ingest_performed"] is False
    assert content["candidates"][0]["url"] == "https://example.org/source"
    assert content["search_branches"][0]["provider"] == "searxng"
    assert content["search_branches"][0]["observations"][0]["route"] == "explicit:searxng"
    assert content["provider_diagnostics"]["provider_readiness"]["searxng"]["configured"] is True
    assert content["retrieval_run"]["project_key"] == "example"
