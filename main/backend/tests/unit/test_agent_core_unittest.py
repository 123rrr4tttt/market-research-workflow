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

    def test_long_task_stage_update_requires_explicit_stage_completion(self):
        from app.services.agent_core.authoring_tools import (
            AuthoringToolContext,
            authoring_task_session_sources,
        )
        from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="explicit long-task stages",
            project_key="demo_proj",
            task_blueprints=[
                {
                    "task_id": "task-long",
                    "subject": "long task",
                    "task_type": "execute",
                    "phase": "research",
                }
            ],
        )
        session_id = bundle["session"]["session_id"]
        task_before = service.store.get_task(session_id, "task-long")
        source = next(
            item
            for item in authoring_task_session_sources(
                AuthoringToolContext(service=service, structured_data_searcher=lambda **_kwargs: {})
            )
            if item.tool_spec.name == "agent_long_task.stage.update"
        )

        result = source.handler(
            CoreToolCall(
                tool_name="agent_long_task.stage.update",
                call_id="call-long-stage",
                arguments={
                    "stage": "gap_analysis",
                    "stage_status": "in_progress",
                    "task_id": "task-long",
                    "summary": "Explicit gap analysis",
                },
            ),
            source.tool_spec,
            AgentCoreRequest(
                message="continue long task",
                session_id=session_id,
                project_key="demo_proj",
            ),
            lambda _event: None,
        )

        assert result.status == "completed"
        assert "current_stage" not in result.structured_content["state"]
        artifact = next(
            item
            for item in service.list_artifacts(session_id)
            if item["name"] == "agent_long_task.state.json"
        )
        stages = {
            item["stage"]: item
            for item in artifact["content_json"]["stages"]
        }
        assert stages["plan"]["status"] == "pending"
        assert stages["plan"]["summary"] == ""
        assert "completed_at" not in stages["plan"]
        assert stages["internal_evidence"]["status"] == "pending"
        assert stages["gap_analysis"]["status"] == "in_progress"
        assert stages["gap_analysis"]["task_id"] == "task-long"
        assert "current_stage" not in artifact["content_json"]
        assert service.store.get_task(session_id, "task-long") == task_before

    def test_authoring_writing_conflict_readback_is_preserved(self):
        from app.services.agent_core.authoring_tools import (
            AuthoringToolContext,
            authoring_ingest_writing_batch_sources,
        )
        from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
        from app.services.agent_core.host_authorization import TrustedHostContext
        from app.services.agent_core.tool_contribution import (
            register_project_tool_contributions,
        )
        from app.services.writing import WritingVersionConflictError

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        session = service.create_session(
            source="trusted_host", entrypoint_type="agent_macro", project_key="demo_proj",
            goal="update writing",
        )["session"]
        session_id = session["session_id"]
        host_context = TrustedHostContext("demo_proj", session_id, "thread-writing", "turn-1", "input-writing")
        service.create_host_user_message(host_context, content="update writing")
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
            call = CoreToolCall(
                    tool_name="writing.document.insert_paragraph",
                    call_id="call-writing-conflict",
                    arguments={
                        "doc_id": 7,
                        "content_md": "New paragraph",
                        "operation": "append",
                        "base_version": 3,
                    },
                )
            request = AgentCoreRequest(
                message="update writing", session_id=session_id, project_key="demo_proj",
                turn_id=host_context.turn_id,
            )
            pending = registry.execute_tool(
                tool_call=call,
                tool_spec=spec,
                request=request,
                trusted_context=host_context,
                authorization_service=service,
                emit=lambda _event: None,
            )
            assert pending.status == "needs_approval"
            mocked_save.assert_not_called()
            approval_id = pending.structured_content["approval_id"]
            confirmation = TrustedHostContext("demo_proj", session_id, "thread-writing", "turn-2", "confirm-writing")
            service.record_host_tool_confirmation(
                confirmation, approval_id=approval_id,
                content=f"Allow once approval:{approval_id}",
            )
            result = registry.execute_tool(
                tool_call=call,
                tool_spec=spec,
                request=AgentCoreRequest(
                    message="update writing", session_id=session_id, project_key="demo_proj",
                    turn_id=confirmation.turn_id,
                ),
                trusted_context=confirmation,
                authorization_service=service,
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
        service.store.update_session(session_id, {"status": "canceled"})
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
        assert "task.continue" not in result.retry_hint
        assert "task.summary" in result.retry_hint
        assert "canonical runtime run" in result.retry_hint
        assert events[0].payload["skipped_items"] == ["https://example.gov/report"]

    def test_authoring_url_pool_submit_fails_closed_without_trusted_request_actor(self):
        from app.services.agent_core.authoring_tools import (
            AuthoringToolContext,
            authoring_ingest_writing_batch_sources,
        )
        from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
        from app.services.agent_core.host_authorization import (
            TrustedHostContext,
            VerifiedHostAuthorization,
            verified_host_authorization_channel,
        )

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        session_id = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="URL pool durable submission",
            project_key="demo_proj",
            task_blueprints=[],
        )["session"]["session_id"]
        context = AuthoringToolContext(
            service=service,
            structured_data_searcher=lambda **_kwargs: {},
        )
        source = next(
            item
            for item in authoring_ingest_writing_batch_sources(context)
            if item.tool_spec.name == "ingest.url_pool.submit"
        )
        trusted_context = TrustedHostContext(
            project_key="demo_proj",
            session_id=session_id,
            host_thread_id="url-host-thread-1",
            turn_id="turn-url-runtime",
            user_message_id="input-url-runtime",
        )
        authorization = VerifiedHostAuthorization(
            context=trusted_context,
            tool_name="ingest.url_pool.submit",
            arguments_sha256="0" * 64,
            package_digest=None,
            permission="allow",
            approval_id=None,
            origin_call_id="call-url-runtime",
            origin_turn_id="turn-url-runtime",
            origin_user_message_id="input-url-runtime",
        )

        with (
            patch(
                "app.composition.production.submit_installed_program"
            ) as submit_runtime,
        ):
            with verified_host_authorization_channel(authorization):
                result = source.handler(
                    CoreToolCall(
                        tool_name="ingest.url_pool.submit",
                        call_id="call-url-runtime",
                        arguments={
                            "url": "https://example.gov/report",
                            "async_mode": True,
                            "search_options": {"light_filter_min_score": 55},
                        },
                    ),
                    source.tool_spec,
                    AgentCoreRequest(
                        message="collect",
                        session_id=session_id,
                        project_key="demo_proj",
                        turn_id="turn-url-runtime",
                    ),
                    lambda _event: None,
                )

        assert result.status == "failed"
        assert result.error["code"] == "request_actor_context_missing"
        assert "trusted request actor" in result.model_summary
        submit_runtime.assert_not_called()
        assert all(
            item["name"] != "ingest.url_pool_submissions.json"
            for item in service.list_artifacts(session_id)
        )

    def test_authoring_url_pool_submit_uses_trusted_actor_for_runtime_submission(self):
        from types import SimpleNamespace
        from unittest.mock import Mock

        from app.services.agent_core.authoring_tools import (
            AuthoringToolContext,
            authoring_ingest_writing_batch_sources,
        )
        from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
        from app.services.agent_core.host_authorization import (
            TrustedHostContext,
            VerifiedHostAuthorization,
            verified_host_authorization_channel,
        )
        from app.services.request_identity import authenticated_actor_context

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        session_id = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="URL pool durable submission",
            project_key="demo_proj",
            task_blueprints=[],
        )["session"]["session_id"]
        context = AuthoringToolContext(
            service=service,
            structured_data_searcher=lambda **_kwargs: {},
        )
        source = next(
            item
            for item in authoring_ingest_writing_batch_sources(context)
            if item.tool_spec.name == "ingest.url_pool.submit"
        )
        actor_context = authenticated_actor_context(
            actor_id="host-actor-17",
            source="test-host",
            auth_mode="test-auth",
        )
        trusted_context = TrustedHostContext(
            project_key="demo_proj",
            session_id=session_id,
            host_thread_id="url-host-thread-1",
            turn_id="turn-url-runtime",
            user_message_id="input-url-runtime",
            actor_context=actor_context,
        )
        authorization = VerifiedHostAuthorization(
            context=trusted_context,
            tool_name="ingest.url_pool.submit",
            arguments_sha256="0" * 64,
            package_digest=None,
            permission="allow",
            approval_id=None,
            origin_call_id="call-url-runtime",
            origin_turn_id="turn-url-runtime",
            origin_user_message_id="input-url-runtime",
        )

        with (
            patch("app.models.base.engine") as engine,
            patch(
                "app.successor_runtime.substrate.postgres.session.ServerProjectScopeResolver"
            ) as resolver,
            patch(
                "app.composition.production.submit_installed_program",
                return_value=(
                    {"run_id": "url-single-agent-runtime-1", "state": "READY"},
                    ("work:url-single-agent-runtime-1:1",),
                ),
            ) as submit_runtime,
        ):
            connection = engine.connect.return_value.__enter__.return_value
            resolver.return_value = SimpleNamespace(
                resolve=Mock(
                    return_value=SimpleNamespace(
                        project_key="demo_proj",
                        project_registry_revision=1,
                        scope_digest="a" * 64,
                    )
                )
            )
            with verified_host_authorization_channel(authorization):
                result = source.handler(
                    CoreToolCall(
                        tool_name="ingest.url_pool.submit",
                        call_id="call-url-runtime",
                        arguments={
                            "url": "https://example.gov/report",
                            "async_mode": True,
                        },
                    ),
                    source.tool_spec,
                    AgentCoreRequest(
                        message="collect",
                        session_id=session_id,
                        project_key="demo_proj",
                        turn_id="turn-url-runtime",
                    ),
                    lambda _event: None,
                )

        assert connection is not None
        assert result.status == "completed"
        assert result.structured_content["task_id"] == ""
        assert result.structured_content["runtime_run_ref"] == "runtime-run:url-single-agent-runtime-1"
        assert result.structured_content["work_item_ids"] == ["work:url-single-agent-runtime-1:1"]
        submit_runtime.assert_called_once()
        assert submit_runtime.call_args.kwargs["actor_id"] == "host-actor-17"

    def test_canceled_url_pool_status_recommends_runtime_observation(self):
        from app.services.agent_core.authoring_tools import (
            AuthoringToolContext,
            authoring_ingest_writing_batch_sources,
        )
        from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        session_id = service.create_session(
            source="user", entrypoint_type="agent_core", goal="Read canceled ingest",
            project_key="demo_proj",
        )["session"]["session_id"]
        service.store.upsert_artifact({
            "session_id": session_id, "artifact_type": "json",
            "name": "ingest.url_pool_task_events.json",
            "content_json": {"events": [{"task_id": "canceled-ingest", "status": "canceled"}]},
        })
        context = AuthoringToolContext(
            service=service, structured_data_searcher=lambda **_kwargs: {"items": []},
        )
        source = next(item for item in authoring_ingest_writing_batch_sources(context)
                      if item.tool_spec.name == "ingest.url_pool.status")
        with patch("app.services.job_logger.list_jobs", return_value=[]):
            result = source.handler(
                CoreToolCall(tool_name="ingest.url_pool.status", call_id="read-cancel",
                             arguments={"task_id": "canceled-ingest"}),
                source.tool_spec,
                AgentCoreRequest(message="status", session_id=session_id, project_key="demo_proj"),
                lambda _event: None,
            )
        guidance = result.structured_content["writing_guidance"]
        assert "task.continue" not in guidance
        assert "task.retry" not in guidance
        assert guidance.index("runtime summary") < guidance.index("cancellation observation")
