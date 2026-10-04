from __future__ import annotations

import unittest
from contextlib import nullcontext
from unittest.mock import patch

import pytest

from app.services.agent_core import CoreToolRegistry, CoreToolSpec
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore


pytestmark = pytest.mark.unit


class SharedCoreToolProjectionUnitTest(unittest.TestCase):
    def test_tool_registry_schema_inventory_is_deterministic_and_schema_complete(self):
        registry = CoreToolRegistry()
        registry.register(
            CoreToolSpec(
                name="write.note",
                description_for_model="Write a shared note.",
                input_schema={
                    "type": "object",
                    "properties": {"body": {"type": "string"}},
                    "required": ["body"],
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "properties": {"note_id": {"type": "string"}}},
                source="project",
                risk="write_shared",
                permission="ask",
                concurrency="serial",
            ),
            lambda tool_call, tool_spec, request, emit: registry.simple_result(
                call=tool_call, model_summary="ok"
            ),
        )
        registry.register(
            CoreToolSpec(
                name="read.project",
                description_for_model="Read project data.",
                input_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                source="project",
                risk="read_only",
                permission="allow",
            ),
            lambda tool_call, tool_spec, request, emit: registry.simple_result(
                call=tool_call, model_summary="ok"
            ),
        )

        inventory = registry.schema_inventory()

        assert inventory["contract_version"] == "agent_core.tool_schema_inventory.v1"
        assert inventory["tool_count"] == 2
        assert [tool["name"] for tool in inventory["tools"]] == [
            "read.project",
            "write.note",
        ]
        assert inventory["summary"]["by_permission"] == {"allow": 1, "ask": 1}
        assert inventory["summary"]["by_risk"] == {"read_only": 1, "write_shared": 1}
        assert inventory["tools"][0]["input_schema"]["type"] == "object"
        assert "output_schema" in inventory["tools"][0]

    def test_authoring_tool_sources_preserve_original_registry_families(self):
        from app.services.agent_core.authoring_tools import (
            AuthoringToolContext,
            authoring_ingest_writing_batch_sources,
            authoring_task_session_sources,
        )
        from app.services.agent_core.tool_contribution import (
            register_project_tool_contributions,
        )

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        context = AuthoringToolContext(
            service=service,
            structured_data_searcher=lambda **_kwargs: {},
        )

        early = authoring_task_session_sources(context)
        later = authoring_ingest_writing_batch_sources(context)

        assert [source.tool_spec.name for source in early] == [
            "agent_task.plan.append",
            "agent_long_task.stage.update",
            "agent_long_task.stage.read",
            "agent_session.resume_bundle",
        ]
        assert [source.tool_spec.name for source in later] == [
            "ingest.url_pool.submit",
            "ingest.url_pool.status",
            "source.history.read",
            "agent_investigation.leads.append",
            "agent_investigation.trace.read",
            "writing.document.list",
            "writing.document.read",
            "writing.document.section.read",
            "writing.document.create",
            "writing.document.insert_paragraph",
            "writing.document.citations.upsert",
            "agent_batch.submit",
        ]
        assert [source.binding_id for source in early + later] == [
            f"facility.{source.tool_spec.name}" for source in early + later
        ]

        registry = CoreToolRegistry()
        assert register_project_tool_contributions(registry, early + later) is None
        assert len(registry.list_specs()) == 16
        assert registry.get("agent_batch.submit") is not None
        assert registry.get("writing.document.insert_paragraph") is not None

    def test_authoring_writing_conflict_readback_is_preserved(self):
        from app.services.agent_core.authoring_tools import (
            AuthoringToolContext,
            authoring_ingest_writing_batch_sources,
        )
        from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
        from app.services.agent_core.tool_contribution import (
            register_project_tool_contributions,
        )
        from app.services.writing import WritingVersionConflictError

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        context = AuthoringToolContext(
            service=service,
            structured_data_searcher=lambda **_kwargs: {},
        )
        registry = CoreToolRegistry()
        assert register_project_tool_contributions(
            registry,
            authoring_ingest_writing_batch_sources(context),
        ) is None
        spec = registry.get("writing.document.insert_paragraph")
        assert spec is not None

        current_document = {
            "id": 7,
            "title": "Market brief",
            "body_md": "Existing analysis",
            "version": 4,
            "etag": "etag-4",
        }
        conflict = WritingVersionConflictError(
            expected_version=3,
            current_version=4,
            server_snapshot={"conflict_code": "VERSION_CONFLICT", "version": 4},
        )
        import app.services.agent_core.authoring_tools as authoring_tools

        with (
            patch.object(authoring_tools, "bind_project", return_value=nullcontext()),
            patch.object(authoring_tools, "get_document", return_value=current_document),
            patch.object(
                authoring_tools,
                "save_document_with_conflict",
                side_effect=conflict,
            ) as mocked_save,
        ):
            result = registry.execute_tool(
                tool_call=CoreToolCall(
                    tool_name="writing.document.insert_paragraph",
                    call_id="call-writing-conflict",
                    arguments={
                        "doc_id": 7,
                        "content_md": "New paragraph",
                        "operation": "append",
                        "base_version": 3,
                    },
                ),
                tool_spec=spec,
                request=AgentCoreRequest(
                    message="update writing",
                    session_id="session-writing",
                    project_key="demo_proj",
                ),
                emit=lambda _event: None,
            )

        mocked_save.assert_called_once()
        assert result.status == "failed"
        assert result.error["code"] == "writing_version_conflict"
        assert result.error["current_version"] == 4
        assert result.structured_content["conflict"]["version"] == 4

    def test_authoring_url_pool_submit_respects_cooperative_abort(self):
        from app.services.agent_core.authoring_tools import (
            AuthoringToolContext,
            authoring_ingest_writing_batch_sources,
        )
        from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="URL pool cooperative cancel",
            project_key="demo_proj",
            task_blueprints=[],
        )
        session_id = bundle["session"]["session_id"]
        service.cancel_session(session_id)
        context = AuthoringToolContext(
            service=service,
            structured_data_searcher=lambda **_kwargs: {},
        )
        source = next(
            item
            for item in authoring_ingest_writing_batch_sources(context)
            if item.tool_spec.name == "ingest.url_pool.submit"
        )

        events = []
        result = source.handler(
            CoreToolCall(
                tool_name="ingest.url_pool.submit",
                call_id="call-url-cancel",
                arguments={"url": "https://example.gov/report", "async_mode": True},
            ),
            source.tool_spec,
            AgentCoreRequest(
                message="collect",
                session_id=session_id,
                project_key="demo_proj",
            ),
            events.append,
        )

        assert result.status == "canceled"
        assert result.error["code"] == "session_canceled"
        assert events[0].payload["skipped_items"] == ["https://example.gov/report"]

    def test_url_pool_background_task_stops_when_agent_session_is_canceled(self):
        from app.services.tasks import task_ingest_url_via_source_library

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="URL-pool background cancel",
            project_key="demo_proj",
            task_blueprints=[],
        )
        session_id = bundle["session"]["session_id"]
        service.cancel_session(session_id)
        marker = {
            "session_id": session_id,
            "artifact_name": "ingest.url_pool_submissions.json",
            "idempotency_key": "cancel-bg:url_pool",
            "project_key": "demo_proj",
            "url": "https://example.gov/reports/robotics-market",
            "task_id": "task-cancel-bg",
            "source_call_id": "call-url-pool-background-cancel",
        }

        with (
            patch(
                "app.services.agent_sessions.service.get_agent_session_service",
                return_value=service,
            ),
            patch(
                "app.services.ingest.url_pool.ingest_url_via_source_library_frontdoor"
            ) as mocked_frontdoor,
        ):
            result = task_ingest_url_via_source_library(
                "https://example.gov/reports/robotics-market",
                query_terms=["robotics"],
                strict_mode=False,
                project_key="demo_proj",
                search_options={"_agent_core_url_pool_submission": marker},
            )

        mocked_frontdoor.assert_not_called()
        assert result["status"] == "canceled"
        assert result["abort_requested"] is True
        event_artifact = next(
            item
            for item in service.list_artifacts(session_id)
            if item["name"] == "ingest.url_pool_task_events.json"
        )
        assert event_artifact["content_json"]["events"][0]["status"] == "canceled"

    def test_url_pool_task_completion_helper_writes_session_artifacts(self):
        from app.services.tasks import _record_agent_url_pool_task_event

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="Background URL-pool completion",
            project_key="demo_proj",
            task_blueprints=[],
        )
        session_id = bundle["session"]["session_id"]
        service.store.upsert_artifact(
            {
                "session_id": session_id,
                "name": "ingest.url_pool_submissions.json",
                "artifact_type": "url_pool_ingest_submission_state",
                "mime_type": "application/json",
                "content_json": {
                    "contract_version": "ingest.url_pool.submit.v1",
                    "project_key": "demo_proj",
                    "submissions": [
                        {
                            "idempotency_key": "candidate-example-gov:url_pool",
                            "url": "https://example.gov/reports/robotics-market",
                            "dispatch_result": {
                                "task_id": "agent-url-pool-123",
                                "status": "queued",
                            },
                        }
                    ],
                },
            }
        )

        with patch(
            "app.services.agent_sessions.service.get_agent_session_service",
            return_value=service,
        ):
            _record_agent_url_pool_task_event(
                {
                    "session_id": session_id,
                    "artifact_name": "ingest.url_pool_submissions.json",
                    "idempotency_key": "candidate-example-gov:url_pool",
                    "project_key": "demo_proj",
                    "url": "https://example.gov/reports/robotics-market",
                    "task_id": "agent-url-pool-123",
                },
                status="completed",
                result={"inserted": 1, "documents": [{"id": 7}]},
            )

        event_artifact = next(
            item
            for item in service.list_artifacts(session_id)
            if item["name"] == "ingest.url_pool_task_events.json"
        )
        assert event_artifact["content_json"]["events"][0]["status"] == "completed"
        submission_artifact = next(
            item
            for item in service.list_artifacts(session_id)
            if item["name"] == "ingest.url_pool_submissions.json"
        )
        submission = submission_artifact["content_json"]["submissions"][0]
        assert submission["latest_task_status"] == "completed"
        assert submission["task_events"][0]["task_id"] == "agent-url-pool-123"
        assert any(
            event["event_type"] == "ingest.url_pool.task.completed"
            for event in service.list_events(session_id)
        )
