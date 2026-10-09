from __future__ import annotations

import unittest
import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.agent_core import CoreToolRegistry, CoreToolSpec
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore


pytestmark = pytest.mark.unit


@pytest.fixture
def url_pool_core_consumer():
    from app.services.agent_core.authoring_tools import AuthoringToolContext, authoring_ingest_writing_batch_sources
    from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
    from app.services.agent_core.host_authorization import TrustedHostContext
    from app.services.agent_core.tool_contribution import register_project_tool_contributions
    from app.services.request_identity import authenticated_actor_context

    service = AgentSessionService(store=InMemoryAgentSessionStore())
    session_id = service.create_session(
        source="trusted_host", entrypoint_type="agent_core", goal="Submit URL", project_key="demo_proj",
    )["session"]["session_id"]
    host = TrustedHostContext(
        "demo_proj", session_id, "url-thread", "url-turn", "url-input",
        actor_context=authenticated_actor_context(actor_id="url-actor", source="test-host", auth_mode="test-auth"),
    )
    service.create_host_user_message(host, content="collect the approved URL")
    registry = CoreToolRegistry()
    assert register_project_tool_contributions(
        registry, authoring_ingest_writing_batch_sources(
            AuthoringToolContext(service=service, structured_data_searcher=lambda **_kwargs: {})
        ),
    ) is None
    events = []

    def execute(arguments, call_id="url-call"):
        return registry.execute_tool(
            tool_call=CoreToolCall(tool_name="ingest.url_pool.submit", call_id=call_id, arguments=arguments),
            request=AgentCoreRequest(message="collect", session_id=session_id, project_key="demo_proj", turn_id=host.turn_id),
            trusted_context=host, authorization_service=service, emit=events.append,
        )

    return service, session_id, execute, events


@pytest.fixture
def url_pool_effects():
    with (
        patch("app.models.base.engine"),
        patch("app.successor_runtime.substrate.postgres.session.ServerProjectScopeResolver") as resolver,
        patch("app.composition.production.submit_installed_program", return_value=(
            {"run_id": "canonical-url-run", "state": "RUNNING"}, ("work:canonical-url-run:1",),
        )) as runtime,
        patch("app.services.agent_core.authoring_tools.bind_project", return_value=nullcontext()),
        patch("app.services.ingest.url_pool.ingest_url_via_source_library_frontdoor", return_value={
            "task_id": "sync-task", "status": "accepted",
        }) as frontdoor,
    ):
        resolver.return_value.resolve.return_value = SimpleNamespace(project_registry_revision=1, scope_digest="a" * 64)
        yield runtime, frontdoor


@pytest.mark.parametrize("async_mode", [False, True])
def test_authoring_url_pool_submit_normalization_and_replay_through_core(url_pool_core_consumer, url_pool_effects, async_mode):
    service, session_id, execute, _events = url_pool_core_consumer
    runtime, frontdoor = url_pool_effects
    arguments = {
        "project_key": "demo_proj", "url": " https://example.gov/report ", "query_terms": [],
        "strict_mode": False, "async_mode": async_mode, "search_options": {"top": 2}, "source_name": " ",
        "artifact_name": " custom.json ", "metadata": {"title": "Top title", "review_key": "top-review"},
        "ingest_payload": {
            "project_key": "demo_proj", "url": "https://example.gov/other",
            "query_terms": ["policy", " policy ", "中文"], "strict_mode": True, "async_mode": True,
            "search_options": {"payload": 1}, "source_name": "Payload source",
            "metadata": {"title": "Payload title", "review_key": "payload-review", "origin": "kept"},
        },
    }
    result = execute(arguments)
    assert result.status == "completed", result.to_dict()
    artifact = next(item for item in service.list_artifacts(session_id) if item["name"] == "custom.json")
    submission = artifact["content_json"]["submissions"][0]
    assert submission["query_terms"] == ["policy", "中文"]
    assert submission["strict_mode"] is True
    assert submission["source_name"] == ""
    assert submission["metadata"] == {"title": "Top title", "review_key": "top-review", "origin": "kept"}
    assert submission["candidate_review_key"] == "top-review"
    assert submission["idempotency_key"] == "9977663609056f6436945a8b"
    dispatch = result.structured_content["dispatch_result"]
    assert dispatch["effective_payload"] == {
        "url": "https://example.gov/report", "project_key": "demo_proj", "query_terms": ["policy", "中文"],
        "strict_mode": True, "async_mode": async_mode, "agent_session_id": session_id,
    }
    if async_mode:
        runtime.assert_called_once()
        frontdoor.assert_not_called()
        submitted = runtime.call_args.kwargs
        assert submitted["actor_id"] == "url-actor"
        assert submitted["run_id"] == "url-single-agent-3d8c1f20375cc288b4918f7b"
        assert submitted["logical_request_id"] == submission["idempotency_key"]
        assert json.loads(submitted["values"][0][1]) == {
            "url": "https://example.gov/report", "project_key": "demo_proj", "query_terms": ["policy", "中文"],
            "extra_params": {"strict_mode": True, "enable_extraction": True, "top": 2},
            "enable_extraction": True, "target": None, "context": None,
        }
        assert dispatch["runtime_state"] == "RUNNING"
        assert dispatch["status"] == "submitted"
        assert result.structured_content["runtime_run_ref"] == "runtime-run:canonical-url-run"
    else:
        runtime.assert_not_called()
        frontdoor.assert_called_once_with(
            url="https://example.gov/report", project_key="demo_proj", query_terms=["policy", "中文"],
            strict_mode=True, search_options={"top": 2}, frontdoor_options={"enabled": True},
            entrypoint="agent_core.ingest.url_pool.submit", source_name="agent_core_url_pool_submit", enable_extraction=True,
        )
        assert result.structured_content["task_id"] == "sync-task"
    replayed = execute(arguments, call_id="url-replay")
    assert replayed.status == "completed"
    assert replayed.structured_content["replayed"] is True
    assert "async_mode" not in replayed.structured_content
    assert service.list_artifacts(session_id) == [artifact]
    assert runtime.call_count + frontdoor.call_count == 1


@pytest.mark.parametrize("options", [None, {}])
def test_authoring_url_pool_submit_explicit_options_override_payload_and_defaults(url_pool_core_consumer, url_pool_effects, options):
    service, session_id, execute, _events = url_pool_core_consumer
    runtime, frontdoor = url_pool_effects
    result = execute({"search_options": options, "idempotency_key": " explicit-key ", "artifact_name": " ",
                      "ingest_payload": {"url": "https://example.gov/default", "search_options": {"nested": True}}})
    assert result.status == "completed", result.to_dict()
    frontdoor.assert_not_called()
    submitted = runtime.call_args.kwargs
    assert submitted["logical_request_id"] == "explicit-key"
    body = json.loads(submitted["values"][0][1])
    assert body["query_terms"] == []
    assert body["extra_params"] == {"strict_mode": False, "enable_extraction": True}
    dispatch = result.structured_content["dispatch_result"]
    assert dispatch["params"] == {"url": "https://example.gov/default", "query_terms": None, "strict_mode": False,
                                  **({"search_options": {}} if options == {} else {})}
    artifact = service.list_artifacts(session_id)[0]
    assert artifact["name"] == "ingest.url_pool_submissions.json"
    submission = artifact["content_json"]["submissions"][0]
    assert submission["source_name"] == "https://example.gov/default"
    assert submission["async_mode"] is True


def test_authoring_url_pool_submit_keeps_core_nested_project_scope_guard(url_pool_core_consumer, url_pool_effects):
    service, session_id, execute, _events = url_pool_core_consumer
    runtime, frontdoor = url_pool_effects
    result = execute({"project_key": "demo_proj", "url": "https://example.gov/report", "async_mode": True,
                      "ingest_payload": {"project_key": "other-project"}})
    assert result.status == "failed"
    assert result.error["code"] == "session_project_mismatch"
    runtime.assert_not_called()
    frontdoor.assert_not_called()
    assert service.list_artifacts(session_id) == []


@pytest.mark.parametrize("async_mode", [False, True])
@pytest.mark.parametrize("phase", ["before", "after"])
def test_authoring_url_pool_submit_preserves_abort_dispatch_boundary(url_pool_core_consumer, url_pool_effects, async_mode, phase):
    service, session_id, execute, events = url_pool_core_consumer
    runtime, frontdoor = url_pool_effects
    if phase == "before":
        service.store.update_session(session_id, {"status": "canceled"})
    else:
        effect = runtime if async_mode else frontdoor
        original = effect.return_value
        def cancel_after_dispatch(**_kwargs):
            service.store.update_session(session_id, {"status": "canceled"})
            return original
        effect.side_effect = cancel_after_dispatch
    result = execute({"url": "https://example.gov/abort", "async_mode": async_mode})
    expected = int(phase == "after")
    assert result.status == "canceled", result.to_dict()
    assert result.structured_content["dispatched_count"] == expected
    assert result.structured_content["skipped_items"] == ["https://example.gov/abort"]
    assert events[-1].payload["dispatched_count"] == expected
    assert runtime.call_count + frontdoor.call_count == expected
    assert service.list_artifacts(session_id) == []
    if phase == "after":
        assert "dispatch_result" in result.structured_content


def test_authoring_url_pool_submit_bounds_history_and_preserves_frontdoor_readback(url_pool_core_consumer, url_pool_effects):
    service, session_id, execute, _events = url_pool_core_consumer
    runtime, frontdoor = url_pool_effects
    prior = [{"idempotency_key": f"previous-{index}", "async_mode": bool(index % 2)} for index in range(100)]
    service.store.upsert_artifact({
        "session_id": session_id, "name": "ingest.url_pool_submissions.json", "artifact_type": "url_pool_ingest_submission_state",
        "content_json": {"submissions": prior, "retained": "original"},
    })
    frontdoor.return_value = {"task_id": "sync-task", "effective_payload": {"frontdoor": "original"}}
    result = execute({"url": "https://example.gov/new", "async_mode": False})
    assert result.status == "completed", result.to_dict()
    runtime.assert_not_called()
    frontdoor.assert_called_once()
    content = service.list_artifacts(session_id)[0]["content_json"]
    assert content["retained"] == "original"
    assert content["submissions"][:-1] == prior[1:]
    assert len(content["submissions"]) == 100
    assert content["counts"] == {"submitted": 101, "async": 50, "sync": 51}
    assert result.structured_content["dispatch_result"]["effective_payload"] == {"frontdoor": "original"}


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

    def test_authoring_writing_insert_projection_covers_completed_paths(self):
        from app.services.agent_core.authoring_tools import (
            AuthoringToolContext,
            authoring_ingest_writing_batch_sources,
        )
        from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
        from app.services.agent_core.host_authorization import TrustedHostContext
        from app.services.agent_core.tool_contribution import (
            register_project_tool_contributions,
        )

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        session = service.create_session(
            source="trusted_host", entrypoint_type="agent_macro", project_key="demo_proj",
            goal="writing projection",
        )["session"]
        session_id = session["session_id"]
        initial_context = TrustedHostContext("demo_proj", session_id, "thread-insert", "turn-0", "input-insert")
        service.create_host_user_message(initial_context, content="update writing")
        registry = CoreToolRegistry()
        assert register_project_tool_contributions(
            registry,
            authoring_ingest_writing_batch_sources(
                AuthoringToolContext(service=service, structured_data_searcher=lambda **_kwargs: {})
            ),
        ) is None
        spec = registry.get("writing.document.insert_paragraph")
        assert spec is not None
        current = {
            "id": 7,
            "title": "Market brief",
            "body_md": "Existing analysis",
            "version": 4,
            "etag": "etag-4",
        }
        arguments = {
            "doc_id": 7,
            "content_md": "New paragraph",
            "operation": "append",
            "idempotency_key": "stable-writing-key",
            "source_refs": ["record:94"],
            "provenance": {"message_id": "message-94"},
        }
        saved = {
            "id": 7,
            "title": "Market brief",
            "body_md": "Existing analysis\n\nNew paragraph\n",
            "version": 5,
            "etag": "etag-5",
        }
        turn = -1

        def execute(updated_arguments: dict[str, object]):
            nonlocal turn
            turn += 1
            if turn == 0:
                pending_context = initial_context
            else:
                pending_context = TrustedHostContext(
                    "demo_proj", session_id, "thread-insert", f"turn-{turn}", f"input-{turn}"
                )
                service.create_host_user_message(pending_context, content="update writing")
            call = CoreToolCall(
                tool_name="writing.document.insert_paragraph",
                call_id=f"call-writing-{turn}",
                arguments=updated_arguments,
            )
            request = AgentCoreRequest(
                message="update writing", session_id=session_id, project_key="demo_proj",
                turn_id=pending_context.turn_id,
            )
            pending = registry.execute_tool(
                tool_call=call, tool_spec=spec, request=request,
                trusted_context=pending_context, authorization_service=service,
                emit=lambda _event: None,
            )
            assert pending.status == "needs_approval"
            confirmation = TrustedHostContext(
                "demo_proj", session_id, "thread-insert", f"turn-{turn}-confirm", f"confirm-{turn}"
            )
            approval_id = pending.structured_content["approval_id"]
            service.record_host_tool_confirmation(
                confirmation, approval_id=approval_id, content=f"Allow once approval:{approval_id}"
            )
            return registry.execute_tool(
                tool_call=call, tool_spec=spec,
                request=AgentCoreRequest(
                    message="update writing", session_id=session_id, project_key="demo_proj",
                    turn_id=confirmation.turn_id,
                ),
                trusted_context=confirmation, authorization_service=service,
                emit=lambda _event: None,
            )

        import app.services.agent_core.authoring_tools as authoring_tools
        with (
            patch.object(authoring_tools, "bind_project", return_value=nullcontext()),
            patch.object(authoring_tools, "get_document", return_value=current),
            patch.object(authoring_tools, "create_document", return_value=saved) as mocked_create,
            patch.object(
                authoring_tools, "save_document_with_conflict", return_value=saved
            ) as mocked_save,
        ):
            dry = execute({**arguments, "dry_run": True})
            assert dry.status == "completed", dry.to_dict()
            assert dry.call_id == "call-writing-0"
            assert dry.tool_name == "writing.document.insert_paragraph"
            assert dry.structured_content["contract_version"] == spec.metadata["contract_version"]
            assert dry.structured_content["doc_id"] == 7
            assert dry.structured_content["dry_run"] is True
            assert dry.structured_content["source_refs"] == ["record:94"]
            assert dry.structured_content["provenance"] == {"message_id": "message-94"}
            mocked_save.assert_not_called()
            mocked_create.assert_not_called()

            locked = execute(dict(arguments))
            assert locked.status == "failed"
            assert locked.structured_content["current_version"] == 4
            assert locked.structured_content["current_etag"] == "etag-4"
            assert locked.structured_content["retry_arguments"]["base_version"] == 4
            assert locked.error["code"] == "version_lock_required"
            mocked_save.assert_not_called()
            mocked_create.assert_not_called()

            success = execute({**arguments, "base_version": 4, "if_match": "etag-4"})
            assert success.status == "completed"
            assert success.structured_content["document"]["version"] == 5
            assert success.structured_content["diff"]["added_lines"] == 2
            assert success.structured_content["agent_update"]["idempotency_key"] == "stable-writing-key"
            mocked_save.assert_called_once()
            mocked_create.assert_not_called()

            replayed_document = {
                **current,
                "metadata_json": {
                    "agent_updates": [success.structured_content["agent_update"]],
                },
            }
            with patch.object(authoring_tools, "get_document", return_value=replayed_document):
                replayed = execute({**arguments, "base_version": 4, "if_match": "etag-4"})
                assert replayed.status == "completed"
                assert replayed.structured_content["replayed"] is True
                assert replayed.structured_content["diff"]["added_lines"] == 0
                assert replayed.structured_content["agent_update"] == success.structured_content["agent_update"]
            mocked_save.assert_called_once()
            mocked_create.assert_not_called()

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

    def _url_pool_status_source(self, service: AgentSessionService, session_id: str):
        from app.services.agent_core.authoring_tools import (
            AuthoringToolContext,
            authoring_ingest_writing_batch_sources,
        )

        context = AuthoringToolContext(
            service=service,
            structured_data_searcher=lambda **_kwargs: {"items": [{"document_id": 999}]},
        )
        return next(
            item
            for item in authoring_ingest_writing_batch_sources(context)
            if item.tool_spec.name == "ingest.url_pool.status"
        )

    def _write_url_pool_submission(self, service: AgentSessionService, session_id: str) -> None:
        service.store.upsert_artifact({
            "session_id": session_id,
            "artifact_type": "url_pool_ingest_submission_state",
            "name": "ingest.url_pool_submissions.json",
            "content_json": {
                "submissions": [{
                    "idempotency_key": "url-key",
                    "project_key": "demo_proj",
                    "url": "https://example.gov/report",
                    "task_id": "",
                    "runtime_run_ref": "runtime-run:url-runtime-1",
                    "async_mode": True,
                    "dispatch_result": {"runtime_run_ref": "runtime-run:url-runtime-1"},
                }]
            },
        })
        service.store.upsert_artifact({
            "session_id": session_id,
            "artifact_type": "json",
            "name": "ingest.url_pool_task_events.json",
            "content_json": {"events": [{"task_id": "", "status": "completed", "url": "https://example.gov/report"}]},
        })

    def test_url_pool_status_canonical_failed_is_not_pending_from_weak_evidence(self):
        from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
        from app.services.agent_core.host_authorization import (
            TrustedHostContext,
            VerifiedHostAuthorization,
            verified_host_authorization_channel,
        )
        from app.services.request_identity import authenticated_actor_context

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        session_id = service.create_session(
            source="user", entrypoint_type="agent_core", goal="Read failed URL runtime",
            project_key="demo_proj",
        )["session"]["session_id"]
        self._write_url_pool_submission(service, session_id)
        source = self._url_pool_status_source(service, session_id)
        actor = authenticated_actor_context(actor_id="status-actor", source="test-host", auth_mode="test-auth")
        authorization = VerifiedHostAuthorization(
            context=TrustedHostContext("demo_proj", session_id, "host", "turn", "message", actor_context=actor),
            tool_name="ingest.url_pool.status",
            arguments_sha256="0" * 64,
            package_digest=None,
            permission="allow",
            approval_id=None,
            origin_call_id="status-call",
            origin_turn_id="turn",
            origin_user_message_id="message",
        )

        with (
            patch("app.services.job_logger.list_jobs", return_value=[]),
            patch(
                "app.services.agent_core.authoring_tools._url_pool_capability_grant_is_current",
                return_value=True,
            ),
            patch(
                "app.composition.production.read_installed_program",
                return_value=({"run_id": "url-runtime-1", "project_key": "demo_proj", "state": "FAILED"}, (), ()),
            ) as read_runtime,
            patch(
                "app.services.agent_core.authoring_tools._read_url_pool_runtime_url",
                return_value="https://example.gov/report",
            ),
            patch(
                "app.composition.production.read_installed_program_failures",
                return_value=((1, SimpleNamespace(
                    domain_failure=None,
                    failure_code="URL_POOL_EXECUTION_FAILED",
                    failure_digest="a" * 64,
                    attempt_id="attempt-1",
                )),),
            ) as read_failures,
            patch("app.composition.production.read_installed_program_outputs") as read_outputs,
        ):
            with verified_host_authorization_channel(authorization):
                result = source.handler(
                    CoreToolCall(tool_name="ingest.url_pool.status", call_id="status-call", arguments={}),
                    source.tool_spec,
                    AgentCoreRequest(message="status", session_id=session_id, project_key="demo_proj"),
                    lambda _event: None,
                )

        assert result.status == "completed"
        assert result.structured_content["verified"] is False
        assert result.structured_content["pending"] is False
        assert result.structured_content["next_gate"] == "url_pool_canonical_runtime_failed"
        assert result.structured_content["runtime_readback"]["state"] == "FAILED"
        assert result.structured_content["runtime_failures"][0]["failure_code"] == "URL_POOL_EXECUTION_FAILED"
        assert result.structured_content["runtime_failures"][0]["reason"] == "URL_POOL_EXECUTION_FAILED"
        read_runtime.assert_called_once()
        read_failures.assert_called_once()
        read_outputs.assert_not_called()

    def test_url_pool_status_completed_requires_runtime_output_and_document_readback(self):
        import json as json_module

        from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
        from app.services.agent_core.host_authorization import (
            TrustedHostContext,
            VerifiedHostAuthorization,
            verified_host_authorization_channel,
        )
        from app.services.request_identity import authenticated_actor_context
        from app.successor_runtime.capabilities.acquisition_url import (
            UrlSingleUrlOutcome,
            build_url_single_url_contract,
            build_url_single_url_outcome_codec,
        )

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        session_id = service.create_session(
            source="user", entrypoint_type="agent_core", goal="Read completed URL runtime",
            project_key="demo_proj",
        )["session"]["session_id"]
        self._write_url_pool_submission(service, session_id)
        source = self._url_pool_status_source(service, session_id)
        actor = authenticated_actor_context(actor_id="status-actor", source="test-host", auth_mode="test-auth")
        authorization = VerifiedHostAuthorization(
            context=TrustedHostContext("demo_proj", session_id, "host", "turn", "message", actor_context=actor),
            tool_name="ingest.url_pool.status",
            arguments_sha256="0" * 64,
            package_digest=None,
            permission="allow",
            approval_id=None,
            origin_call_id="status-call",
            origin_turn_id="turn",
            origin_user_message_id="message",
        )
        contract = build_url_single_url_contract()
        outcome_payload = build_url_single_url_outcome_codec(contract.ref).encode_payload(
            UrlSingleUrlOutcome(status="completed", inserted=1, updated=0, skipped=0, document_id=42)
        )
        exact = json_module.dumps(outcome_payload).encode("utf-8")

        with (
            patch("app.services.job_logger.list_jobs", return_value=[]),
            patch(
                "app.services.agent_core.authoring_tools._url_pool_capability_grant_is_current",
                return_value=True,
            ),
            patch(
                "app.composition.production.read_installed_program",
                return_value=(
                    {"run_id": "url-runtime-1", "project_key": "demo_proj", "state": "COMPLETED"},
                    ({"step_id": "url-step", "operation_kind": "acquisition.url.single_url.v1"},),
                    (),
                ),
            ),
            patch(
                "app.services.agent_core.authoring_tools._read_url_pool_runtime_url",
                return_value="https://example.gov/report",
            ),
            patch(
                "app.composition.production.read_installed_program_outputs",
                return_value=(("url-step", object(), exact),),
            ),
            patch(
                "app.services.agent_core.authoring_tools._read_url_pool_document",
                return_value={
                    "project_key": "demo_proj",
                    "document_id": 42,
                    "matched_url": "https://example.gov/report",
                },
            ) as read_document,
        ):
            with verified_host_authorization_channel(authorization):
                result = source.handler(
                    CoreToolCall(tool_name="ingest.url_pool.status", call_id="status-call", arguments={}),
                    source.tool_spec,
                    AgentCoreRequest(message="status", session_id=session_id, project_key="demo_proj"),
                    lambda _event: None,
                )

        assert result.status == "completed"
        assert result.structured_content["runtime_error"] is None, result.structured_content["runtime_error"]
        assert result.structured_content["verified"] is True
        assert result.structured_content["pending"] is False
        assert result.structured_content["runtime_output"]["document_id"] == 42
        assert result.structured_content["document_readback"]["document_id"] == 42
        assert result.structured_content["document_readback"]["project_key"] == "demo_proj"
        assert result.structured_content["causal_evidence"]["document"]["matched_url"] == "https://example.gov/report"
        read_document.assert_called_once_with("demo_proj", 42, "https://example.gov/report")

    def test_url_pool_document_rejects_same_domain_root_and_accepts_persisted_redirect(self):
        from app.services.agent_core.authoring_tools import _read_url_pool_document

        session = MagicMock()
        session.execute.return_value.first.side_effect = (
            SimpleNamespace(
                id=42,
                uri="https://example.gov/article/42",
                extracted_data={"source_ref": {"url": "https://example.gov/requested"}},
                base_url="https://example.gov",
            ),
            SimpleNamespace(
                id=42,
                uri="https://example.gov/article/42",
                extracted_data={"source_ref": {"url": "https://example.gov/requested"}},
                base_url="https://example.gov",
            ),
        )
        session_context = MagicMock()
        session_context.__enter__.return_value = session
        with (
            patch(
                "app.services.agent_core.authoring_tools.bind_project",
                return_value=nullcontext(),
            ),
            patch(
                "app.services.agent_core.authoring_tools.SessionLocal",
                return_value=session_context,
            ),
        ):
            root_match = _read_url_pool_document(
                "demo_proj", 42, "https://example.gov"
            )
            redirect_match = _read_url_pool_document(
                "demo_proj", 42, "https://example.gov/requested"
            )

        assert root_match is None
        assert redirect_match is not None
        assert redirect_match["uri"] == "https://example.gov/article/42"
        assert redirect_match["matched_url"] == "https://example.gov/requested"
        assert redirect_match["match_kind"] == "persisted_source_ref"

    def test_url_pool_status_explicit_url_without_submission_does_not_reuse_other_run(self):
        from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        session_id = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="Read exact URL runtime",
            project_key="demo_proj",
        )["session"]["session_id"]
        self._write_url_pool_submission(service, session_id)
        source = self._url_pool_status_source(service, session_id)

        with (
            patch("app.services.job_logger.list_jobs", return_value=[]),
            patch("app.composition.production.read_installed_program") as read_runtime,
        ):
            result = source.handler(
                CoreToolCall(
                    tool_name="ingest.url_pool.status",
                    call_id="status-call",
                    arguments={"url": "https://example.gov/missing"},
                ),
                source.tool_spec,
                AgentCoreRequest(
                    message="status",
                    session_id=session_id,
                    project_key="demo_proj",
                ),
                lambda _event: None,
            )

        assert result.structured_content["verified"] is False
        assert result.structured_content["pending"] is False
        assert result.structured_content["submission"] == {}
        assert (
            result.structured_content["runtime_error"]["code"]
            == "url_pool_submission_not_found"
        )
        read_runtime.assert_not_called()

    def test_url_pool_status_async_readback_fails_closed_without_verified_actor(self):
        from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        session_id = service.create_session(
            source="user", entrypoint_type="agent_core", goal="Read URL runtime without actor",
            project_key="demo_proj",
        )["session"]["session_id"]
        self._write_url_pool_submission(service, session_id)
        source = self._url_pool_status_source(service, session_id)

        with patch("app.services.job_logger.list_jobs", return_value=[]):
            result = source.handler(
                CoreToolCall(tool_name="ingest.url_pool.status", call_id="status-call", arguments={}),
                source.tool_spec,
                AgentCoreRequest(message="status", session_id=session_id, project_key="demo_proj"),
                lambda _event: None,
            )

        assert result.status == "completed"
        assert result.structured_content["verified"] is False
        assert result.structured_content["pending"] is False
        assert result.structured_content["runtime_error"]["code"] == "url_pool_runtime_actor_required"

    def test_url_pool_status_trusted_actor_does_not_replace_capability_grant(self):
        from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
        from app.services.agent_core.host_authorization import (
            TrustedHostContext,
            VerifiedHostAuthorization,
            verified_host_authorization_channel,
        )
        from app.services.request_identity import authenticated_actor_context

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        session_id = service.create_session(
            source="user", entrypoint_type="agent_core", goal="Read URL runtime without grant",
            project_key="demo_proj",
        )["session"]["session_id"]
        self._write_url_pool_submission(service, session_id)
        source = self._url_pool_status_source(service, session_id)
        actor = authenticated_actor_context(
            actor_id="status-actor", source="test-host", auth_mode="test-auth"
        )
        authorization = VerifiedHostAuthorization(
            context=TrustedHostContext(
                "demo_proj", session_id, "host", "turn", "message", actor_context=actor
            ),
            tool_name="ingest.url_pool.status",
            arguments_sha256="0" * 64,
            package_digest=None,
            permission="allow",
            approval_id=None,
            origin_call_id="status-call",
            origin_turn_id="turn",
            origin_user_message_id="message",
        )

        with (
            patch("app.services.job_logger.list_jobs", return_value=[]),
            patch(
                "app.services.agent_core.authoring_tools._url_pool_capability_grant_is_current",
                return_value=False,
            ) as grant_check,
            patch("app.composition.production.read_installed_program") as read_runtime,
        ):
            with verified_host_authorization_channel(authorization):
                result = source.handler(
                    CoreToolCall(
                        tool_name="ingest.url_pool.status",
                        call_id="status-call",
                        arguments={},
                    ),
                    source.tool_spec,
                    AgentCoreRequest(
                        message="status", session_id=session_id, project_key="demo_proj"
                    ),
                    lambda _event: None,
                )

        assert result.status == "completed"
        assert result.structured_content["verified"] is False
        assert result.structured_content["pending"] is False
        assert (
            result.structured_content["runtime_error"]["code"]
            == "url_pool_runtime_capability_grant_required"
        )
        grant_check.assert_called_once()
        read_runtime.assert_not_called()

    def test_url_pool_status_preserves_cancelled_and_superseded_runtime_states(self):
        from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
        from app.services.agent_core.host_authorization import (
            TrustedHostContext,
            VerifiedHostAuthorization,
            verified_host_authorization_channel,
        )
        from app.services.request_identity import authenticated_actor_context

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        session_id = service.create_session(
            source="user", entrypoint_type="agent_core", goal="Read terminal URL runtime",
            project_key="demo_proj",
        )["session"]["session_id"]
        self._write_url_pool_submission(service, session_id)
        source = self._url_pool_status_source(service, session_id)
        actor = authenticated_actor_context(
            actor_id="status-actor", source="test-host", auth_mode="test-auth"
        )
        authorization = VerifiedHostAuthorization(
            context=TrustedHostContext(
                "demo_proj", session_id, "host", "turn", "message", actor_context=actor
            ),
            tool_name="ingest.url_pool.status",
            arguments_sha256="0" * 64,
            package_digest=None,
            permission="allow",
            approval_id=None,
            origin_call_id="status-call",
            origin_turn_id="turn",
            origin_user_message_id="message",
        )

        for state, expected_code, expected_gate in (
            (
                "CANCELLED",
                "url_pool_runtime_cancelled",
                "url_pool_canonical_runtime_cancelled",
            ),
            (
                "SUPERSEDED",
                "url_pool_runtime_superseded",
                "url_pool_canonical_runtime_superseded",
            ),
        ):
            with self.subTest(state=state):
                with (
                    patch("app.services.job_logger.list_jobs", return_value=[]),
                    patch(
                        "app.services.agent_core.authoring_tools._url_pool_capability_grant_is_current",
                        return_value=True,
                    ),
                    patch(
                        "app.composition.production.read_installed_program",
                        return_value=(
                            {
                                "run_id": "url-runtime-1",
                                "project_key": "demo_proj",
                                "state": state,
                            },
                            (),
                            (),
                        ),
                    ),
                    patch(
                        "app.services.agent_core.authoring_tools._read_url_pool_runtime_url",
                        return_value="https://example.gov/report",
                    ),
                    patch(
                        "app.composition.production.read_installed_program_failures",
                        return_value=(),
                    ),
                    patch("app.composition.production.read_installed_program_outputs") as outputs,
                ):
                    with verified_host_authorization_channel(authorization):
                        result = source.handler(
                            CoreToolCall(
                                tool_name="ingest.url_pool.status",
                                call_id="status-call",
                                arguments={},
                            ),
                            source.tool_spec,
                            AgentCoreRequest(
                                message="status",
                                session_id=session_id,
                                project_key="demo_proj",
                            ),
                            lambda _event: None,
                        )

                assert result.structured_content["verified"] is False
                assert result.structured_content["pending"] is False
                assert result.structured_content["runtime_error"]["code"] == expected_code
                assert result.structured_content["next_gate"] == expected_gate
                outputs.assert_not_called()

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


@pytest.fixture
def source_web_core_consumer():
    import socket
    from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
    from app.services.agent_core.query_tools import register_query_project_tools

    service = AgentSessionService(store=InMemoryAgentSessionStore())
    session_id = service.create_session(
        source="user", entrypoint_type="agent_core", goal="Search sources", project_key="demo_proj",
    )["session"]["session_id"]
    registry = CoreToolRegistry()
    assert register_query_project_tools(registry=registry, service=service) is None

    def execute(arguments):
        return registry.execute_tool(
            tool_call=CoreToolCall(tool_name="source.web.search", call_id="web-search", arguments=arguments),
            request=AgentCoreRequest(message="base", session_id=session_id, project_key="demo_proj"),
            emit=lambda _event: None,
        )

    public_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    with (
        patch("app.services.source_library.external_project.socket.getaddrinfo", return_value=public_dns),
        patch("app.services.ingest.url_pool.ingest_url_via_source_library_frontdoor", side_effect=AssertionError("search cannot ingest")),
        patch("app.composition.production.submit_installed_program", side_effect=AssertionError("search cannot submit a write")),
    ):
        yield execute, service, session_id


def test_source_web_search_matrix_core_preserves_order_failure_trust_and_dedupe(source_web_core_consumer):
    from app.services.search.candidate_contracts import Candidate, CandidateBundle, ProviderObservation

    execute, service, session_id = source_web_core_consumer
    calls = []

    def discover(request):
        calls.append((request.topic, request.provider, request.max_results))
        if len(calls) == 1:
            raise OSError("first branch unavailable")
        rows = [
            {"link": "http://127.0.0.1/private", "title": "Private", "snippet": "blocked", "source": request.provider, "keyword": request.topic},
            {"link": "https://www.gov.uk/policy", "title": "Official policy", "snippet": "policy evidence", "source": request.provider, "keyword": request.topic},
        ]
        candidates = tuple(Candidate(
            resource_uri=row["link"], title=row["title"], snippet=row["snippet"],
            source=row["source"], keyword=row["keyword"], original_rank=99, result_rank=90 + index,
            relevance_score=1.0, raw=row,
        ) for index, row in enumerate(rows, start=1))
        observations = (ProviderObservation(request.provider, "test", request.topic, "completed", 2),)
        if len(calls) == 2:
            observations += (ProviderObservation(request.provider, "fallback", request.topic, "failed", 0, "timeout", "TimeoutError", "partial branch"),)
        return CandidateBundle(request, candidates, (), observations, "candidates_observed")

    with patch("app.services.agent_core.query_tools.discover_candidates", side_effect=discover):
        result = execute({
            "query": "base", "query_variants": ["base", "official", "market", "other"],
            "providers": ["auto", "serpapi", "ddg"], "matrix_mode": True, "max_results": 20,
        })
    assert result.status == "completed", result.to_dict()
    assert calls == [
        ("base", "auto", 5), ("base", "serpapi", 5), ("base", "ddg", 5),
        ("official", "auto", 5), ("official", "serpapi", 5), ("official", "ddg", 5),
        ("market", "auto", 5), ("market", "serpapi", 5),
    ]
    content = result.structured_content
    assert content["contract_version"] == "source.web.search.v1"
    assert content["project_write_performed"] is False and content["ingest_performed"] is False
    branches = content["search_branches"]
    assert [branch["status"] for branch in branches] == ["failed", "partial"] + ["completed"] * 6
    assert branches[0]["error"] == {"code": "OSError", "message": "first branch unavailable"}
    assert [item["status"] for item in branches[1]["observations"]] == ["completed", "failed"]
    candidates = content["candidates"]
    assert len(candidates) == 2
    assert candidates[0]["url"] == "https://www.gov.uk/policy"
    assert candidates[0]["trust"]["status"] == "accepted"
    assert candidates[0]["rank"] == 2  # Wire rank remains original branch enumeration.
    assert candidates[0]["branch_count"] == 7
    assert candidates[1]["trust"]["status"] == "rejected"
    assert service.list_artifacts(session_id) == []


def test_source_web_search_nonmatrix_failure_core_keeps_exact_error(source_web_core_consumer):
    execute, service, session_id = source_web_core_consumer
    with patch("app.services.agent_core.query_tools.discover_candidates", side_effect=OSError("provider unavailable")) as discover:
        result = execute({"query": "base", "provider": "serpapi"})
    assert discover.call_count == 1
    assert result.status == "failed"
    assert result.error == {"code": "OSError", "message": "provider unavailable"}
    assert result.structured_content["contract_version"] == "source.web.search.v1"
    assert result.structured_content["project_write_performed"] is False
    assert result.structured_content["ingest_performed"] is False
    assert service.list_artifacts(session_id) == []


@pytest.mark.parametrize("url_field,date_field", [("url", "published_at"), ("href", "date")])
def test_source_web_search_real_candidate_constructor_keeps_scalar_fallback(source_web_core_consumer, url_field, date_field):
    execute, service, session_id = source_web_core_consumer
    # These fields intentionally produce empty typed URI/snippet/source in the
    # real discover_candidates constructor; its raw compatibility fields remain.
    row = {
        url_field: "https://www.gov.uk/legacy", "body": "legacy body", "provider": "legacy-provider",
        "title": "Legacy title", "keyword": "legacy keyword", "rank": 77,
        date_field: {"value": "2026-10-08", "precision": "day"},
    }
    with patch("app.services.search.candidate_search.search_sources", return_value=[row]):
        result = execute({"query": "legacy", "provider": "serpapi"})
    assert result.status == "completed", result.to_dict()
    candidate, = result.structured_content["candidates"]
    assert candidate["url"] == "https://www.gov.uk/legacy"
    assert candidate["title"] == "Legacy title"
    assert candidate["snippet"] == "legacy body"
    assert candidate["source_provider"] == "legacy-provider"
    assert candidate["keyword"] == "legacy keyword"
    assert candidate["published_at"] == {"value": "2026-10-08", "precision": "day"}
    assert candidate["rank"] == 1
    assert result.structured_content["project_write_performed"] is False
    assert result.structured_content["ingest_performed"] is False
    assert service.list_artifacts(session_id) == []
