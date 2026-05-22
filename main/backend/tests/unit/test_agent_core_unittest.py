from __future__ import annotations

from contextlib import contextmanager
import json
import os
import unittest
from unittest.mock import patch

import pytest

from app.services.agent_core import (
    AgentCore,
    AgentCoreRequest,
    CoreApprovalResume,
    CoreModelStep,
    CoreToolCall,
    CoreToolRegistry,
    CoreToolResult,
    CoreToolSpec,
    FakeCoreProvider,
    JsonCoreProvider,
    NativeToolCallingCoreProvider,
    build_project_core_tool_registry,
    select_core_tool_window,
)
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore

pytestmark = pytest.mark.unit


@contextmanager
def _noop_project_context(project_key):
    yield


class AgentCoreUnitTest(unittest.TestCase):
    def _registry(self) -> CoreToolRegistry:
        return CoreToolRegistry()

    def test_free_conversation_returns_final_answer_without_tools(self):
        registry = self._registry()
        provider = FakeCoreProvider([CoreModelStep.final("你好，我可以直接回答。", model_path="fake")])
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(AgentCoreRequest(message="你好", session_id="as-test", project_key="demo_proj"))

        self.assertEqual(out.final_answer, "你好，我可以直接回答。")
        self.assertEqual(out.stop_reason, "final_answer")
        self.assertEqual(out.tool_results, ())
        self.assertEqual([event.event_type for event in out.events], ["session_started", "user_message", "assistant_message", "final_answer"])
        self.assertEqual(provider.calls[0]["tool_names"], [])

    def test_streaming_context_emits_non_empty_answer_deltas_before_final_answer(self):
        registry = self._registry()
        provider = FakeCoreProvider([CoreModelStep.final("这是一个较长回答，用于验证前端可以逐段显示。", model_path="fake")])
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(
            AgentCoreRequest(
                message="解释一下",
                session_id="as-test",
                project_key="demo_proj",
                context={"stream": True},
            )
        )

        event_types = [event.event_type for event in out.events]
        deltas = [
            event.payload.get("delta")
            for event in out.events
            if event.event_type == "assistant_delta" and event.payload.get("stream_kind") == "answer_text"
        ]
        self.assertGreaterEqual(len(deltas), 2)
        self.assertEqual("".join(str(item) for item in deltas), out.final_answer)
        self.assertLess(event_types.index("assistant_delta"), event_types.index("final_answer"))

    def test_model_selected_project_tool_result_is_fed_back_before_final_answer(self):
        registry = self._registry()
        calls: list[dict] = []

        spec = CoreToolSpec(
            name="project.summary.read",
            title="Project summary reader",
            description_for_model="Read project database summary without mutation.",
            risk="read_only",
            permission="allow",
            source="project",
        )

        def handler(tool_call, tool_spec, request, emit):
            calls.append(tool_call.to_dict())
            return registry.simple_result(
                call=tool_call,
                model_summary="Project demo_proj has 3 source-library items.",
                structured_content={"source_library": {"total": 3}},
            )

        registry.register(spec, handler)
        tool_call = CoreToolCall(tool_name="project.summary.read", arguments={"limit": 5}, call_id="call-project")
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(tool_call, model_path="fake"),
                CoreModelStep.final("当前项目有 3 个来源库 item。", model_path="fake"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(AgentCoreRequest(message="项目里有什么数据", session_id="as-test", project_key="demo_proj"))

        self.assertEqual(out.final_answer, "当前项目有 3 个来源库 item。")
        self.assertEqual(len(out.tool_results), 1)
        self.assertEqual(out.tool_results[0].tool_name, "project.summary.read")
        self.assertEqual(out.tool_results[0].structured_content["source_library"]["total"], 3)
        self.assertEqual(calls[0]["call_id"], "call-project")
        event_types = [event.event_type for event in out.events]
        self.assertEqual(
            event_types,
            [
                "session_started",
                "user_message",
                "tool_call_requested",
                "tool_call_started",
                "tool_result",
                "assistant_message",
                "final_answer",
            ],
        )
        second_transcript = provider.calls[1]["transcript"]
        self.assertEqual(second_transcript[-1]["tool_result"]["tool_name"], "project.summary.read")

    def test_tool_registry_schema_inventory_is_deterministic_and_schema_complete(self):
        registry = self._registry()
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
            lambda tool_call, tool_spec, request, emit: registry.simple_result(call=tool_call, model_summary="ok"),
        )
        registry.register(
            CoreToolSpec(
                name="read.project",
                description_for_model="Read project data.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                source="project",
                risk="read_only",
                permission="allow",
            ),
            lambda tool_call, tool_spec, request, emit: registry.simple_result(call=tool_call, model_summary="ok"),
        )

        inventory = registry.schema_inventory()

        self.assertEqual(inventory["contract_version"], "agent_core.tool_schema_inventory.v1")
        self.assertEqual(inventory["tool_count"], 2)
        self.assertEqual([tool["name"] for tool in inventory["tools"]], ["read.project", "write.note"])
        self.assertEqual(inventory["summary"]["by_permission"], {"allow": 1, "ask": 1})
        self.assertEqual(inventory["summary"]["by_risk"], {"read_only": 1, "write_shared": 1})
        self.assertEqual(inventory["tools"][0]["input_schema"]["type"], "object")
        self.assertIn("output_schema", inventory["tools"][0])

    def test_insubstantial_final_answer_after_tools_is_replaced_with_tool_summary(self):
        registry = self._registry()
        spec = CoreToolSpec(
            name="project.structured_data.search",
            title="Structured data search",
            description_for_model="Search project data.",
            risk="read_only",
            permission="allow",
            source="project",
        )

        def handler(tool_call, tool_spec, request, emit):
            return registry.simple_result(
                call=tool_call,
                model_summary="Found 2 robotics records.",
                structured_content={
                    "query": "机器人",
                    "total_matches": 2,
                    "dataset_counts": {"documents": 1, "graph_nodes": 1},
                    "items": [
                        {"dataset": "documents", "title": "机器人产业笔记", "summary": "供应链、政策和企业线索"},
                    ],
                },
            )

        registry.register(spec, handler)
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(CoreToolCall(tool_name="project.structured_data.search", arguments={"query": "机器人"}, call_id="call-data")),
                CoreModelStep.final("项目摘要已读取。", model_path="fake"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(AgentCoreRequest(message="项目里有哪些机器人数据", session_id="as-test", project_key="demo_proj"))

        self.assertIn("结构化数据检索", out.final_answer)
        self.assertIn("机器人产业笔记", out.final_answer)
        final_event = [event for event in out.events if event.event_type == "final_answer"][-1]
        self.assertEqual(final_event.payload["fallback_reason"], "insubstantial_model_final_answer_after_tools")

    def test_tool_result_transcript_is_compacted_for_model_followup(self):
        registry = self._registry()
        spec = CoreToolSpec(
            name="test.large.payload",
            title="Large payload test tool",
            description_for_model="Return a large payload.",
            risk="read_only",
            permission="allow",
            source="project",
        )

        def handler(tool_call, tool_spec, request, emit):
            return registry.simple_result(
                call=tool_call,
                model_summary="matched 20 records",
                structured_content={
                    "records": [
                        {"title": f"record {idx}", "body": "x" * 5000}
                        for idx in range(20)
                    ],
                    "extra": "y" * 8000,
                },
            )

        registry.register(spec, handler)
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(CoreToolCall(tool_name="test.large.payload", call_id="call-data")),
                CoreModelStep.final("已总结项目数据。"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(AgentCoreRequest(message="项目里有什么数据", session_id="as-test", project_key="demo_proj"))

        self.assertEqual(out.final_answer, "已总结项目数据。")
        transcript_result = provider.calls[1]["transcript"][-1]["tool_result"]
        self.assertEqual(transcript_result["structured_content"]["records"][-1]["_truncated"], True)
        self.assertTrue(transcript_result["structured_content"]["records"][0]["body"].endswith("[truncated]"))
        self.assertTrue(transcript_result["structured_content"]["extra"].endswith("[truncated]"))

    def test_structured_data_search_transcript_preserves_items_and_manifest(self):
        registry = self._registry()
        spec = CoreToolSpec(
            name="project.structured_data.search",
            title="Search structured project data",
            description_for_model="Search structured project data.",
            risk="read_only",
            permission="allow",
            source="project",
        )

        def handler(tool_call, tool_spec, request, emit):
            return registry.simple_result(
                call=tool_call,
                model_summary="searched structured project data",
                structured_content={
                    "result": {
                        "contract_version": "project.structured_data.search.v1",
                        "project_key": "demo_proj",
                        "query": "机器人",
                        "query_mode": "search",
                        "inventory": [{"dataset": "documents", "label": "Documents", "sample_count": 1, "total_rows": 100}],
                        "dataset_counts": {"documents": 1},
                        "dataset_total_rows": {"documents": 100},
                        "total_stored_rows": 100,
                        "total_matches": 1,
                        "items": [
                            {
                                "dataset": "documents",
                                "record_id": "doc-1",
                                "title": "Robot note",
                                "summary": "Robot adoption accelerates in warehouse pilots.",
                            }
                        ],
                        "model_evidence_manifest": [
                            {
                                "item_id": "structured:documents:doc-1",
                                "resource_uri": "project://structured/demo_proj/documents/doc-1",
                                "dataset": "documents",
                                "record_id": "doc-1",
                                "title": "Robot note",
                                "read_tool": "project.structured_data.item.read",
                                "read_arguments": {"project_key": "demo_proj", "dataset": "documents", "record_id": "doc-1"},
                            }
                        ],
                    }
                },
            )

        registry.register(spec, handler)
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(CoreToolCall(tool_name="project.structured_data.search", arguments={"query": "机器人"}, call_id="call-data")),
                CoreModelStep.final("已基于具体记录总结。"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        core.run(AgentCoreRequest(message="帮我总结机器人资料", session_id="as-test", project_key="demo_proj"))

        result = provider.calls[1]["transcript"][-1]["tool_result"]["structured_content"]["result"]
        self.assertEqual(result["items"][0]["title"], "Robot note")
        self.assertEqual(result["model_evidence_manifest"][0]["read_tool"], "project.structured_data.item.read")
        self.assertEqual(result["model_evidence_manifest"][0]["read_arguments"]["record_id"], "doc-1")

    def test_project_context_bundle_transcript_preserves_evidence_manifest(self):
        registry = self._registry()
        spec = CoreToolSpec(
            name="project.context.bundle",
            title="Read project context",
            description_for_model="Read project context bundle.",
            risk="read_only",
            permission="allow",
            source="project",
        )

        def handler(tool_call, tool_spec, request, emit):
            return registry.simple_result(
                call=tool_call,
                model_summary="built project context bundle",
                structured_content={
                    "result": {
                        "project_key": "demo_proj",
                        "query": "机器人",
                        "material_categories": {"internal_existing": {"stored_rows": 5}},
                        "model_evidence_manifest": [
                            {
                                "item_id": "structured:documents:doc-1",
                                "resource_uri": "project://structured/demo_proj/documents/doc-1",
                                "read_tool": "project.structured_data.item.read",
                                "title": "Robot note",
                            }
                        ],
                        "evidence": [{"kind": "structured_record", "title": "Robot note", "summary": "actual local evidence"}],
                    }
                },
            )

        registry.register(spec, handler)
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(CoreToolCall(tool_name="project.context.bundle", arguments={"query": "机器人"}, call_id="call-context")),
                CoreModelStep.final("已结合上下文回答。"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        core.run(AgentCoreRequest(message="项目里有哪些机器人资料", session_id="as-test", project_key="demo_proj"))

        result = provider.calls[1]["transcript"][-1]["tool_result"]["structured_content"]["result"]
        self.assertEqual(result["evidence"][0]["title"], "Robot note")
        self.assertEqual(result["model_evidence_manifest"][0]["item_id"], "structured:documents:doc-1")

    def test_project_context_can_auto_answer_after_project_tool_results(self):
        registry = self._registry()
        spec = CoreToolSpec(
            name="project.structured_data.search",
            title="Search structured project data",
            description_for_model="Search structured project data.",
            risk="read_only",
            permission="allow",
            source="project",
        )

        def handler(tool_call, tool_spec, request, emit):
            return registry.simple_result(
                call=tool_call,
                model_summary="searched structured project data: matches=2, datasets=1, stored_rows=10",
                structured_content={
                    "result": {
                        "query": "机器人",
                        "total_matches": 2,
                        "dataset_counts": {"documents": 2},
                        "items": [
                            {"dataset": "documents", "title": "Robotics Market", "summary": "robotics adoption and supply chain notes"},
                        ],
                    }
                },
            )

        registry.register(spec, handler)
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(CoreToolCall(tool_name="project.structured_data.search", arguments={"query": "机器人"}, call_id="call-data")),
                CoreModelStep.final("this second model step should not be needed"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(
            AgentCoreRequest(
                message="帮我检索机器人",
                session_id="as-test",
                project_key="demo_proj",
                context={"agent_core_auto_answer_after_project_tools": True},
            )
        )

        self.assertIn("匹配 2 条记录", out.final_answer)
        self.assertIn("Robotics Market", out.final_answer)
        self.assertEqual(len(provider.calls), 1)

    def test_project_context_default_returns_to_model_for_synthesis_after_project_tool(self):
        registry = self._registry()
        spec = CoreToolSpec(
            name="project.structured_data.search",
            title="Search structured project data",
            description_for_model="Search structured project data.",
            risk="read_only",
            permission="allow",
            source="project",
        )

        def handler(tool_call, tool_spec, request, emit):
            return registry.simple_result(
                call=tool_call,
                model_summary="searched structured project data: matches=1",
                structured_content={
                    "result": {
                        "query": "机器人",
                        "total_matches": 1,
                        "items": [{"dataset": "documents", "record_id": "doc-1", "title": "Robot Market", "summary": "robotics adoption"}],
                    }
                },
            )

        registry.register(spec, handler)
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(CoreToolCall(tool_name="project.structured_data.search", arguments={"query": "机器人"}, call_id="call-data")),
                CoreModelStep.final("模型综合后的机器人资料总结。"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(
            AgentCoreRequest(
                message="帮我总结机器人资料",
                session_id="as-test",
                project_key="demo_proj",
                context={"agent_core_auto_answer_after_project_tools": False},
            )
        )

        self.assertEqual(out.final_answer, "模型综合后的机器人资料总结。")
        self.assertEqual(len(provider.calls), 2)

    def test_project_context_auto_answer_includes_quality_audit_results(self):
        answer = AgentCore._fallback_answer_from_tool_results(
            request=AgentCoreRequest(message="做数据质量清理审计", session_id="as-test", project_key="demo_proj"),
            tool_results=[
                CoreToolResult(
                    call_id="call-quality",
                    tool_name="project.structured_data.quality_audit",
                    status="completed",
                    model_summary="Audited structured data quality.",
                    structured_content={
                        "project_key": "demo_proj",
                        "scanned": {"documents": 20, "graph_nodes": 10},
                        "noisy_record_count": 2,
                        "by_dataset": {"documents": 2},
                        "by_reason": {"script_branch": 1, "css_block": 1},
                        "samples": [
                            {
                                "dataset": "documents",
                                "title": "NBC4 shell page",
                                "noise_reasons": ["script_branch", "javascript_global"],
                                "recommended_action": "mark_quality_flag_and_reextract_article_content",
                            }
                        ],
                        "recommended_actions": ["Keep raw content as evidence", "Mark noisy records with quality flags"],
                    },
                )
            ],
        )

        self.assertIn("数据质量审计", answer)
        self.assertIn("发现 2 条", answer)
        self.assertIn("NBC4 shell page", answer)
        self.assertIn("script_branch", answer)
        self.assertIn("Mark noisy records", answer)

    def test_invalid_tool_arguments_return_recoverable_result_before_retry(self):
        registry = self._registry()
        calls: list[dict] = []
        spec = CoreToolSpec(
            name="project.graph.search",
            title="Search Project Graph",
            description_for_model="Search graph nodes.",
            risk="read_only",
            permission="allow",
            source="project",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 3},
                },
                "additionalProperties": False,
            },
        )

        def handler(tool_call, tool_spec, request, emit):
            calls.append(dict(tool_call.arguments))
            return registry.simple_result(
                call=tool_call,
                model_summary="Found 1 graph node.",
                structured_content={"graph_nodes": [{"title": "Robot"}]},
            )

        registry.register(spec, handler)
        invalid_call = CoreToolCall(tool_name="project.graph.search", arguments={"limit": 0, "extra": True}, call_id="call-invalid")
        valid_call = CoreToolCall(tool_name="project.graph.search", arguments={"query": "机器人", "limit": 2}, call_id="call-valid")
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(invalid_call, model_path="fake"),
                CoreModelStep.tools(valid_call, model_path="fake"),
                CoreModelStep.final("已基于图谱结果回答。", model_path="fake"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(AgentCoreRequest(message="追查机器人线索", session_id="as-test", project_key="demo_proj"))

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertEqual([result.status for result in out.tool_results], ["failed", "completed"])
        self.assertEqual(calls, [{"query": "机器人", "limit": 2}])
        validation = out.tool_results[0]
        self.assertEqual(validation.error["code"], "tool_schema_validation_failed")
        self.assertTrue(validation.error["recoverable"])
        error_codes = {item["code"] for item in validation.structured_content["validation_errors"]}
        self.assertEqual(error_codes, {"required", "additional_property", "minimum"})
        self.assertEqual(
            provider.calls[1]["transcript"][-1]["tool_result"]["error"]["code"],
            "tool_schema_validation_failed",
        )
        invalid_events = [event.event_type for event in out.events if event.call_id == "call-invalid"]
        self.assertEqual(invalid_events, ["tool_call_requested", "tool_result"])

    def test_invalid_high_risk_tool_arguments_do_not_request_approval(self):
        registry = self._registry()
        calls: list[dict] = []
        spec = CoreToolSpec(
            name="writing.document.insert_paragraph",
            title="Insert Paragraph",
            description_for_model="Mutate a writing document.",
            risk="write_shared",
            permission="ask",
            source="project",
            input_schema={
                "type": "object",
                "required": ["content_md"],
                "properties": {
                    "doc_id": {"type": "integer", "minimum": 1},
                    "content_md": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            },
        )

        def handler(tool_call, tool_spec, request, emit):
            calls.append(dict(tool_call.arguments))
            return registry.simple_result(call=tool_call, model_summary="should not execute")

        registry.register(spec, handler)
        tool_call = CoreToolCall(tool_name="writing.document.insert_paragraph", arguments={"doc_id": 7}, call_id="call-write")
        provider = FakeCoreProvider([CoreModelStep.tools(tool_call, model_path="fake"), CoreModelStep.final("参数需要补齐。", model_path="fake")])
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(AgentCoreRequest(message="插入一段", session_id="as-test", project_key="demo_proj"))

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertIsNone(out.permission_request)
        self.assertEqual(calls, [])
        self.assertEqual(out.tool_results[0].error["code"], "tool_schema_validation_failed")
        event_types = [event.event_type for event in out.events]
        self.assertNotIn("permission_requested", event_types)
        self.assertNotIn("tool_call_started", [event.event_type for event in out.events if event.call_id == "call-write"])

    def test_project_tool_arguments_are_normalized_from_request_context(self):
        registry = self._registry()
        calls: list[dict] = []
        spec = CoreToolSpec(
            name="project.structured_data.search",
            title="Search structured project data",
            description_for_model="Search structured project data.",
            risk="read_only",
            permission="allow",
            source="project",
            input_schema={
                "type": "object",
                "required": ["project_key", "query"],
                "properties": {
                    "project_key": {"type": "string"},
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "additionalProperties": False,
            },
        )

        def handler(tool_call, tool_spec, request, emit):
            calls.append(dict(tool_call.arguments))
            return registry.simple_result(call=tool_call, model_summary="Found structured project rows.")

        registry.register(spec, handler)
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="project.structured_data.search",
                        arguments={"query": "机器人", "limit": 5, "session_id": "as-extra", "turn_id": "turn-extra"},
                        call_id="call-structured",
                    )
                ),
                CoreModelStep.final("已读取结构化项目数据。"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(AgentCoreRequest(message="项目里有哪些机器人数据", session_id="as-test", project_key="demo_proj"))

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertEqual(
            calls,
            [{"query": "机器人", "limit": 5, "project_key": "demo_proj"}],
        )
        self.assertEqual(out.tool_results[0].status, "completed")

    def test_source_library_item_key_is_normalized_before_execution(self):
        registry = self._registry()
        calls: list[dict] = []
        spec = CoreToolSpec(
            name="ingest.source_library.run",
            title="Source-library collection",
            description_for_model="Run source-library collection.",
            risk="write_external",
            permission="ask",
            source="project",
            input_schema={
                "type": "object",
                "required": ["items", "project_key"],
                "properties": {
                    "items": {"type": "array", "items": {"type": "string"}},
                    "project_key": {"type": "string"},
                },
                "additionalProperties": False,
            },
        )
        registry.register(
            spec,
            lambda tool_call, tool_spec, request, emit: (
                calls.append(dict(tool_call.arguments))
                or registry.simple_result(call=tool_call, model_summary="normalized source-library run")
            ),
        )
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="ingest.source_library.run",
                        arguments={"item_key": "market.general.baseline", "session_id": "as-extra"},
                        call_id="call-ingest",
                    )
                )
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(AgentCoreRequest(message="用来源库 market.general.baseline 补证据", session_id="as-test", project_key="demo_proj"))

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertIsNone(out.permission_request)
        self.assertEqual(calls, [{"items": ["market.general.baseline"], "project_key": "demo_proj"}])
        self.assertEqual(out.tool_results[0].status, "completed")
        self.assertNotIn("permission_requested", [event.event_type for event in out.events])

    def test_legacy_capability_registry_uses_real_handlers_and_hides_unwired_capabilities(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="能力执行",
            project_key="demo_proj",
            task_blueprints=[],
        )
        capabilities = [
            {
                "capability_id": "ingest.source_library.run",
                "name": "Source-library collection",
                "description": "Execute selected source-library items.",
                "approval_level": "high",
                "concurrency_class": "write_external",
                "required_input": ["items", "project_key"],
                "risks": ["external_network"],
            },
            {
                "capability_id": "report.generate",
                "name": "Report generation",
                "description": "Generate a report draft.",
                "approval_level": "high",
                "concurrency_class": "write_shared",
                "required_input": ["topic"],
                "risks": ["filesystem_write"],
            },
            {
                "capability_id": "unwired.demo.capability",
                "name": "Unwired demo",
                "description": "This should not be projected as an AgentCore tool.",
                "approval_level": "high",
                "concurrency_class": "write_shared",
                "required_input": ["value"],
                "risks": ["demo"],
            },
        ]
        with (
            patch("app.services.agent_core.project_tools.list_interactive_agent_capabilities", return_value=capabilities),
            patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[]),
            patch(
                "app.services.agent_core.project_tools.invoke_skill",
                return_value={"result": {"task_id": "task-market-general"}},
            ) as mocked_invoke,
        ):
            registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])

            handled = AgentCore(
                provider=FakeCoreProvider(
                    [
                        CoreModelStep.tools(
                            CoreToolCall(
                                tool_name="ingest.source_library.run",
                                call_id="call-ingest",
                                arguments={"item_key": "market.general.baseline", "project_key": "demo_proj"},
                            )
                        ),
                        CoreModelStep.final("来源库已派发。"),
                    ]
                ),
                tool_registry=registry,
                tool_specs=registry.list_specs(),
            ).run(
                AgentCoreRequest(
                    message="用来源库 market.general.baseline 补证据",
                    session_id=bundle["session"]["session_id"],
                    project_key="demo_proj",
                )
            )

            report = AgentCore(
                provider=FakeCoreProvider(
                    [
                        CoreModelStep.tools(
                            CoreToolCall(
                                tool_name="report.generate",
                                call_id="call-report",
                                arguments={
                                    "topic": "机器人",
                                    "output_path": "reports/robot.md",
                                    "sources": [
                                        {
                                            "id": "S1",
                                            "title": "Robot source",
                                            "url": "https://example.com/robot",
                                            "publisher": "example",
                                            "evidence": "robot evidence",
                                        }
                                    ],
                                },
                            )
                        ),
                        CoreModelStep.final("报告已生成。"),
                    ]
                ),
                tool_registry=registry,
                tool_specs=registry.list_specs(),
            ).run(
                AgentCoreRequest(
                    message="生成报告",
                    session_id=bundle["session"]["session_id"],
                    project_key="demo_proj",
                )
            )

        specs = {item.name: item for item in registry.list_specs()}
        self.assertEqual(specs["ingest.source_library.run"].metadata["legacy_capability"]["capability_id"], "ingest.source_library.run")
        self.assertEqual(specs["report.generate"].metadata["legacy_capability"]["capability_id"], "report.generate")
        self.assertNotIn("unwired.demo.capability", specs)
        self.assertEqual(handled.tool_results[0].status, "completed")
        self.assertEqual(handled.tool_results[0].structured_content["task_ids"], ["task-market-general"])
        self.assertTrue(handled.tool_results[0].structured_content["dispatch_artifact_id"])
        dispatch_artifact = next(item for item in service.list_artifacts(bundle["session"]["session_id"]) if item["name"] == "ingest.source_library_dispatches.json")
        self.assertEqual(dispatch_artifact["content_json"]["latest"]["task_ids"], ["task-market-general"])
        self.assertEqual(dispatch_artifact["content_json"]["latest"]["status"], "queued")
        self.assertIn("ingest.source_library.dispatch_recorded", {item["event_type"] for item in service.list_events(bundle["session"]["session_id"])})
        mocked_invoke.assert_called_once()
        self.assertEqual(report.tool_results[0].status, "completed")
        self.assertEqual(report.tool_results[0].structured_content["output_path"], "reports/robot.md")
        self.assertEqual(report.tool_results[0].structured_content["quality_gate"]["decision"], "pass")
        artifacts = service.list_artifacts(bundle["session"]["session_id"])
        self.assertEqual([item["name"] for item in artifacts if item.get("artifact_type") == "report.generate.markdown"], ["reports/robot.md"])

    def test_source_library_run_stops_dispatching_after_session_cancel(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="补充来源库",
            project_key="demo_proj",
            task_blueprints=[],
        )
        session_id = bundle["session"]["session_id"]
        root_task_id = bundle["session"]["root_task_id"]
        dispatched: list[str] = []

        def fake_invoke_skill(skill_id, payload, context):
            dispatched.append(str(payload["item_key"]))
            service.cancel_session(session_id)
            return {"result": {"task_id": f"task-{payload['item_key']}"}}

        with (
            patch(
                "app.services.agent_core.project_tools.list_interactive_agent_capabilities",
                return_value=[
                    {
                        "capability_id": "ingest.source_library.run",
                        "name": "Source-library collection",
                        "description": "Execute selected source-library items.",
                        "approval_level": "high",
                        "concurrency_class": "write_external",
                        "required_input": ["items", "project_key"],
                        "risks": ["external_network"],
                    }
                ],
            ),
            patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[]),
            patch("app.services.agent_core.project_tools.invoke_skill", side_effect=fake_invoke_skill),
        ):
            registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
            out = AgentCore(
                provider=FakeCoreProvider(
                    [
                        CoreModelStep.tools(
                            CoreToolCall(
                                tool_name="ingest.source_library.run",
                                call_id="call-ingest",
                                arguments={
                                    "project_key": "demo_proj",
                                    "items": ["source.one", "source.two"],
                                },
                            )
                        ),
                        CoreModelStep.final("来源库任务已停止。"),
                    ]
                ),
                tool_registry=registry,
                tool_specs=registry.list_specs(),
            ).run(
                AgentCoreRequest(
                    message="用来源库补两个线索",
                    session_id=session_id,
                    project_key="demo_proj",
                    context={"root_task_id": root_task_id},
                    approval_policy="frozen",
                )
            )

        self.assertEqual(dispatched, ["source.one"])
        self.assertEqual(out.tool_results[0].status, "canceled")
        self.assertEqual(out.tool_results[0].structured_content["task_ids"], ["task-source.one"])
        self.assertEqual(out.tool_results[0].structured_content["skipped_items"], ["source.two"])
        self.assertEqual(out.tool_results[0].structured_content["abort_requested"], True)
        abort_events = [
            event
            for event in out.events
            if event.event_type == "tool_progress"
            and event.payload.get("contract_version") == "agent_core.cooperative_abort.v1"
        ]
        self.assertEqual(len(abort_events), 1)
        self.assertEqual(abort_events[0].payload["status"], "abort_requested")
        self.assertEqual(abort_events[0].payload["dispatched_count"], 1)
        self.assertEqual(abort_events[0].payload["skipped_items"], ["source.two"])

    def test_workflow_graph_run_does_not_invoke_skill_after_session_cancel(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="workflow cancel",
            project_key="demo_proj",
            task_blueprints=[],
        )
        session_id = bundle["session"]["session_id"]
        service.cancel_session(session_id)
        workflow_capability = {
            "capability_id": "workflow_graph.run",
            "name": "Workflow graph run",
            "description": "Run a workflow graph.",
            "approval_level": "high",
            "concurrency_class": "write_external",
            "required_input": ["graph_id", "inputs"],
            "risks": ["project_write"],
        }

        with (
            patch("app.services.agent_core.project_tools.list_interactive_agent_capabilities", return_value=[workflow_capability]),
            patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[]),
            patch("app.services.agent_core.project_tools.invoke_skill") as mocked_invoke,
        ):
            registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
            out = AgentCore(
                provider=FakeCoreProvider(
                    [
                        CoreModelStep.tools(
                            CoreToolCall(
                                tool_name="workflow_graph.run",
                                call_id="call-workflow-cancel",
                                arguments={"project_key": "demo_proj", "graph_id": "graph.demo", "inputs": {"topic": "robots"}},
                            )
                        ),
                        CoreModelStep.final("workflow stopped"),
                    ]
                ),
                tool_registry=registry,
                tool_specs=registry.list_specs(),
            ).run(AgentCoreRequest(message="跑 workflow", session_id=session_id, project_key="demo_proj"))

        mocked_invoke.assert_not_called()
        self.assertEqual(out.tool_results[0].status, "canceled")
        self.assertEqual(out.tool_results[0].structured_content["abort_requested"], True)
        self.assertEqual(out.tool_results[0].structured_content["skipped_items"], ["graph.demo"])

    def test_direct_skill_invocation_does_not_run_after_session_cancel(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="skill cancel",
            project_key="demo_proj",
            task_blueprints=[],
        )
        session_id = bundle["session"]["session_id"]
        service.cancel_session(session_id)
        skill_meta = {
            "skill_id": "workflow_graph.get_run",
            "required_permissions": ["workflow_graph.read"],
            "owner": "workflow_graph.runtime",
            "execution_profile": "default",
            "concurrency_class": "read_only",
            "approval_policy": {},
        }

        with (
            patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[skill_meta]),
            patch("app.services.agent_core.project_tools.invoke_skill") as mocked_invoke,
        ):
            registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
            out = AgentCore(
                provider=FakeCoreProvider(
                    [
                        CoreModelStep.tools(
                            CoreToolCall(
                                tool_name="skill.workflow_graph.get_run",
                                arguments={"run_id": "run-1"},
                                call_id="call-skill-cancel",
                            )
                        ),
                        CoreModelStep.final("skill stopped"),
                    ]
                ),
                tool_registry=registry,
                tool_specs=registry.list_specs(),
            ).run(AgentCoreRequest(message="inspect run", session_id=session_id, project_key="demo_proj"))

        mocked_invoke.assert_not_called()
        self.assertEqual(out.tool_results[0].status, "canceled")
        self.assertEqual(out.tool_results[0].structured_content["abort_requested"], True)
        self.assertEqual(out.tool_results[0].structured_content["skipped_items"], ["workflow_graph.get_run"])

    def test_ingest_url_pool_submit_does_not_queue_after_session_cancel(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="URL-pool cancel",
            project_key="demo_proj",
            task_blueprints=[],
        )
        session_id = bundle["session"]["session_id"]
        service.cancel_session(session_id)
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])

        with patch("app.services.tasks.task_ingest_url_via_source_library.apply_async") as mocked_apply_async:
            out = AgentCore(
                provider=FakeCoreProvider(
                    [
                        CoreModelStep.tools(
                            CoreToolCall(
                                tool_name="ingest.url_pool.submit",
                                call_id="call-url-pool-cancel",
                                arguments={
                                    "project_key": "demo_proj",
                                    "url": "https://example.gov/reports/robotics-market",
                                    "async_mode": True,
                                },
                            )
                        ),
                        CoreModelStep.final("url pool stopped"),
                    ]
                ),
                tool_registry=registry,
                tool_specs=registry.list_specs(),
            ).run(AgentCoreRequest(message="采集 URL", session_id=session_id, project_key="demo_proj"))

        mocked_apply_async.assert_not_called()
        self.assertEqual(out.tool_results[0].status, "canceled")
        self.assertEqual(out.tool_results[0].structured_content["abort_requested"], True)
        self.assertEqual(out.tool_results[0].structured_content["skipped_items"], ["https://example.gov/reports/robotics-market"])
        self.assertFalse(any(item.get("name") == "ingest.url_pool_submissions.json" for item in service.list_artifacts(session_id)))

    def test_ingest_url_pool_submit_does_not_write_submission_after_mid_dispatch_cancel(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="URL-pool mid dispatch cancel",
            project_key="demo_proj",
            task_blueprints=[],
        )
        session_id = bundle["session"]["session_id"]
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])

        class _Task:
            id = "agent-url-pool-canceled-mid-dispatch"

        def fake_apply_async(*, args, task_id):
            service.cancel_session(session_id)
            return _Task()

        with patch("app.services.tasks.task_ingest_url_via_source_library.apply_async", fake_apply_async):
            out = AgentCore(
                provider=FakeCoreProvider(
                    [
                        CoreModelStep.tools(
                            CoreToolCall(
                                tool_name="ingest.url_pool.submit",
                                call_id="call-url-pool-mid-cancel",
                                arguments={
                                    "project_key": "demo_proj",
                                    "url": "https://example.gov/reports/robotics-market",
                                    "async_mode": True,
                                },
                            )
                        ),
                        CoreModelStep.final("url pool stopped"),
                    ]
                ),
                tool_registry=registry,
                tool_specs=registry.list_specs(),
            ).run(AgentCoreRequest(message="采集 URL", session_id=session_id, project_key="demo_proj"))

        self.assertEqual(out.tool_results[0].status, "canceled")
        self.assertEqual(out.tool_results[0].structured_content["abort_requested"], True)
        self.assertEqual(out.tool_results[0].structured_content["dispatched_count"], 1)
        self.assertEqual(out.tool_results[0].structured_content["dispatch_result"]["task_id"], "agent-url-pool-canceled-mid-dispatch")
        self.assertFalse(any(item.get("name") == "ingest.url_pool_submissions.json" for item in service.list_artifacts(session_id)))

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
            patch("app.services.agent_sessions.service.get_agent_session_service", return_value=service),
            patch("app.services.ingest.url_pool.ingest_url_via_source_library_frontdoor") as mocked_frontdoor,
        ):
            result = task_ingest_url_via_source_library(
                "https://example.gov/reports/robotics-market",
                query_terms=["robotics"],
                strict_mode=False,
                project_key="demo_proj",
                search_options={"_agent_core_url_pool_submission": marker},
            )

        mocked_frontdoor.assert_not_called()
        self.assertEqual(result["status"], "canceled")
        self.assertEqual(result["abort_requested"], True)
        event_artifact = next(item for item in service.list_artifacts(session_id) if item["name"] == "ingest.url_pool_task_events.json")
        self.assertEqual(event_artifact["content_json"]["events"][0]["status"], "canceled")

    def test_report_generate_does_not_write_artifact_after_session_cancel(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="report cancel",
            project_key="demo_proj",
            task_blueprints=[],
        )
        session_id = bundle["session"]["session_id"]
        service.cancel_session(session_id)
        report_capability = {
            "capability_id": "report.generate",
            "name": "Report generate",
            "description": "Generate a report draft.",
            "approval_level": "explicit_user_request",
            "concurrency_class": "write_shared",
            "required_input": ["topic", "output_path"],
            "risks": ["artifact_write"],
        }

        with (
            patch("app.services.agent_core.project_tools.list_interactive_agent_capabilities", return_value=[report_capability]),
            patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[]),
        ):
            registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
            out = AgentCore(
                provider=FakeCoreProvider(
                    [
                        CoreModelStep.tools(
                            CoreToolCall(
                                tool_name="report.generate",
                                call_id="call-report-cancel",
                                arguments={"project_key": "demo_proj", "topic": "robots", "output_path": "reports/robot.md"},
                            )
                        ),
                        CoreModelStep.final("report stopped"),
                    ]
                ),
                tool_registry=registry,
                tool_specs=registry.list_specs(),
            ).run(AgentCoreRequest(message="生成报告", session_id=session_id, project_key="demo_proj"))

        self.assertEqual(out.tool_results[0].status, "canceled")
        self.assertEqual(out.tool_results[0].structured_content["abort_requested"], True)
        self.assertEqual(out.tool_results[0].structured_content["skipped_items"], ["reports/robot.md"])
        self.assertFalse(any(item.get("artifact_type") == "report.generate.markdown" for item in service.list_artifacts(session_id)))

    def test_reactive_compact_emits_event_and_keeps_recent_context(self):
        registry = self._registry()
        spec = CoreToolSpec(
            name="project.large.read",
            title="Large read",
            description_for_model="Return a large read-only result.",
            risk="read_only",
            permission="allow",
            source="project",
        )

        def handler(tool_call, tool_spec, request, emit):
            return registry.simple_result(call=tool_call, model_summary="x" * 600, structured_content={"payload": "y" * 600})

        registry.register(spec, handler)
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(CoreToolCall(tool_name="project.large.read", call_id="call-large")),
                CoreModelStep.final("已完成。", model_path="fake"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(
            AgentCoreRequest(
                message="读取大量上下文",
                session_id="as-test",
                project_key="demo_proj",
                context={
                    "agent_core_compact_threshold_chars": 200,
                    "prior_transcript": [{"role": "assistant", "content": f"old {index}"} for index in range(10)],
                },
            )
        )

        self.assertEqual(out.stop_reason, "final_answer")
        compact_events = [event for event in out.events if event.event_type == "run_compacted"]
        self.assertEqual(len(compact_events), 1)
        self.assertEqual(compact_events[0].payload["contract_version"], "agent_core.compact_context.v1")
        self.assertIn("Reactive compacted", provider.calls[1]["transcript"][0]["content"])

    def test_loop_state_events_are_available_when_enabled(self):
        registry = self._registry()
        provider = FakeCoreProvider([CoreModelStep.final("直接回答。", model_path="fake")])
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(
            AgentCoreRequest(
                message="你好",
                session_id="as-test",
                project_key="demo_proj",
                context={"agent_core_emit_turn_state_events": True},
            )
        )

        state_events = [event for event in out.events if event.event_type == "turn_state"]
        self.assertGreaterEqual(len(state_events), 2)
        self.assertEqual(state_events[0].payload["contract_version"], "agent_core.loop_state.v1")
        self.assertEqual(state_events[0].payload["phase"], "model_step")
        self.assertEqual(state_events[-1].payload["stop_reason"], "final_answer")

    def test_high_risk_tool_executes_when_approval_gate_is_frozen(self):
        registry = self._registry()
        spec = CoreToolSpec(
            name="source_library.run",
            title="Source-library collection",
            description_for_model="Run source-library collection.",
            risk="write_external",
            permission="ask",
            source="project",
        )
        registry.register(
            spec,
            lambda tool_call, tool_spec, request, emit: registry.simple_result(
                call=tool_call,
                model_summary="Collection completed for demo.news.",
                structured_content={"accepted": ["demo.news"]},
            ),
        )
        tool_call = CoreToolCall(tool_name="source_library.run", arguments={"items": ["demo.news"]}, call_id="call-run")
        provider = FakeCoreProvider([CoreModelStep.tools(tool_call, model_path="fake"), CoreModelStep.final("已完成来源库补证据。")])
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(AgentCoreRequest(message="用来源库补一轮证据", session_id="as-test", project_key="demo_proj"))

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertIsNone(out.permission_request)
        self.assertEqual(out.tool_results[0].structured_content["accepted"], ["demo.news"])
        event_types = [event.event_type for event in out.events]
        self.assertNotIn("permission_requested", event_types)
        requested = [event for event in out.events if event.event_type == "tool_call_requested" and event.call_id == "call-run"]
        self.assertEqual(requested[0].payload["permission"], "allow")

    def test_high_risk_tool_can_still_pause_when_approval_policy_enabled(self):
        registry = self._registry()
        spec = CoreToolSpec(
            name="source_library.run",
            title="Source-library collection",
            description_for_model="Run source-library collection.",
            risk="write_external",
            permission="ask",
            source="project",
        )
        registry.register(
            spec,
            lambda tool_call, tool_spec, request, emit: registry.simple_result(call=tool_call, model_summary="should not execute"),
        )
        tool_call = CoreToolCall(tool_name="source_library.run", arguments={"items": ["demo.news"]}, call_id="call-run")
        provider = FakeCoreProvider([CoreModelStep.tools(tool_call, model_path="fake")])
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(
            AgentCoreRequest(
                message="用来源库补一轮证据",
                session_id="as-test",
                project_key="demo_proj",
                approval_policy="enabled",
            )
        )

        self.assertEqual(out.stop_reason, "permission_requested")
        self.assertIsNotNone(out.permission_request)
        self.assertEqual(out.permission_request.tool_call.call_id, "call-run")
        self.assertEqual(out.tool_results, ())
        self.assertEqual([event.event_type for event in out.events[-2:]], ["tool_call_requested", "permission_requested"])

    def test_denied_tool_is_blocked_without_approval_prompt(self):
        registry = self._registry()
        spec = CoreToolSpec(
            name="project.secret.delete",
            title="Denied tool",
            description_for_model="Denied mutation.",
            risk="privileged",
            permission="deny",
            source="project",
        )
        registry.register(spec, lambda tool_call, tool_spec, request, emit: registry.simple_result(call=tool_call, model_summary="should not execute"))
        tool_call = CoreToolCall(tool_name="project.secret.delete", call_id="call-denied")
        provider = FakeCoreProvider([CoreModelStep.tools(tool_call), CoreModelStep.final("无法执行被拒绝工具。")])
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(AgentCoreRequest(message="删除受保护数据", session_id="as-test", project_key="demo_proj"))

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertEqual(out.tool_results[0].status, "failed")
        self.assertEqual(out.tool_results[0].error["code"], "tool_permission_denied")
        event_types = [event.event_type for event in out.events]
        self.assertNotIn("permission_requested", event_types)
        self.assertNotIn("tool_call_started", event_types)

    def test_approved_resume_executes_same_tool_call_and_continues_model(self):
        registry = self._registry()
        spec = CoreToolSpec(
            name="source_library.run",
            title="Source-library collection",
            description_for_model="Run source-library collection.",
            risk="write_external",
            permission="ask",
            source="project",
        )

        def handler(tool_call, tool_spec, request, emit):
            return registry.simple_result(
                call=tool_call,
                model_summary="Collection completed for demo.news.",
                structured_content={"accepted": ["demo.news"]},
            )

        registry.register(spec, handler)
        tool_call = CoreToolCall(tool_name="source_library.run", arguments={"items": ["demo.news"]}, call_id="call-run")
        provider = FakeCoreProvider([CoreModelStep.final("已完成来源库补证据。", model_path="fake")])
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(
            AgentCoreRequest(
                message="继续",
                session_id="as-test",
                project_key="demo_proj",
                resume=CoreApprovalResume(approval_id="approval-1", tool_call=tool_call, approved=True),
            )
        )

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertIn("Collection completed for demo.news.", out.final_answer)
        self.assertIn("source_library.run", out.final_answer)
        self.assertEqual(len(out.tool_results), 1)
        self.assertEqual(out.tool_results[0].structured_content["accepted"], ["demo.news"])
        event_types = [event.event_type for event in out.events]
        self.assertIn("run_resumed", event_types)
        self.assertIn("tool_call_started", event_types)
        self.assertIn("tool_result", event_types)

    def test_project_tool_registry_projects_existing_capabilities_as_core_tools(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core_test",
            goal="项目里有什么数据",
            project_key="demo_proj",
            task_blueprints=[],
        )

        def lister(project_key):
            return [
                {
                    "item_key": "demo.news",
                    "name": "Demo News",
                    "channel_key": "generic_web",
                    "enabled": True,
                    "item_type": "user_defined",
                }
            ]

        registry = build_project_core_tool_registry(service=service, source_library_lister=lister)
        specs = {spec.name: spec for spec in registry.list_specs()}

        self.assertEqual(specs["project.summary.read"].permission, "allow")
        self.assertEqual(specs["project.summary.read"].risk, "read_only")
        self.assertEqual(specs["project.structured_data.search"].permission, "allow")
        self.assertEqual(specs["project.structured_data.search"].risk, "read_only")
        self.assertEqual(specs["project.structured_data.item.read"].permission, "allow")
        self.assertEqual(specs["project.structured_data.item.read"].risk, "read_only")
        self.assertEqual(specs["project.context.resource.read"].permission, "allow")
        self.assertEqual(specs["project.context.resource.read"].risk, "read_only")
        self.assertEqual(specs["agent_task.plan.append"].permission, "allow")
        self.assertEqual(specs["agent_task.plan.append"].risk, "write_shared")
        self.assertEqual(specs["agent_task.plan.append"].metadata["auto_allow_session_write"], True)
        self.assertEqual(specs["agent_investigation.leads.append"].permission, "allow")
        self.assertEqual(specs["agent_investigation.leads.append"].risk, "write_shared")
        self.assertEqual(specs["agent_investigation.leads.append"].metadata["auto_allow_session_write"], True)
        self.assertEqual(specs["source.discovery.plan"].permission, "allow")
        self.assertEqual(specs["source.discovery.plan"].risk, "read_only")
        self.assertEqual(specs["project.graph.search"].permission, "allow")
        self.assertEqual(specs["project.structured_graph.query"].permission, "allow")
        self.assertEqual(specs["writing.document.insert_paragraph"].permission, "ask")
        self.assertEqual(specs["source_library.item.list"].permission, "allow")
        self.assertEqual(specs["ingest.url_pool.submit"].permission, "allow")
        self.assertEqual(specs["ingest.url_pool.submit"].risk, "write_external")
        self.assertEqual(specs["ingest.url_pool.status"].permission, "allow")
        self.assertEqual(specs["ingest.url_pool.status"].risk, "read_only")
        self.assertEqual(specs["source.history.read"].permission, "allow")
        self.assertEqual(specs["source.history.read"].risk, "read_only")
        self.assertEqual(specs["ingest.source_library.run"].permission, "ask")
        self.assertEqual(specs["ingest.source_library.run"].risk, "write_external")
        self.assertEqual(specs["agent_batch.nl_command.submit"].permission, "ask")

        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(CoreToolCall(tool_name="project.summary.read", call_id="call-summary")),
                CoreModelStep.final("项目里有 1 个来源库 item。"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())
        out = core.run(
            AgentCoreRequest(
                message="项目里有什么数据",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertEqual(out.final_answer, "项目里有 1 个来源库 item。")
        self.assertEqual(out.tool_results[0].tool_name, "project.summary.read")
        legacy_result = out.tool_results[0].structured_content["result"]
        self.assertEqual(legacy_result["source_library"]["total"], 1)
        self.assertNotIn("legacy_call", out.tool_results[0].structured_content)

    def test_project_tool_registry_projects_skills_and_mcp_catalog(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="skill",
            task_blueprints=[{"task_id": "core-1", "subject": "Core", "task_type": "agent_core_turn", "phase": "conversation"}],
        )
        skill_meta = {
            "skill_id": "workflow_graph.get_run",
            "required_permissions": ["workflow_graph.read"],
            "owner": "workflow_graph.runtime",
            "execution_profile": "default",
            "concurrency_class": "read_only",
            "approval_policy": {},
        }

        with patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[skill_meta]):
            with patch(
                "app.services.agent_core.project_tools.invoke_skill",
                return_value={
                    "skill_id": "workflow_graph.get_run",
                "result": {"run_id": "run-1", "status": "succeeded"},
                "owner": "workflow_graph.runtime",
                "execution_profile": "default",
                    "concurrency_class": "read_only",
                    "approval_policy": {},
                },
            ) as mocked_invoke:
                registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
                specs = {spec.name: spec for spec in registry.list_specs()}
                self.assertEqual(specs["skill.workflow_graph.get_run"].source, "skill")
                self.assertEqual(specs["skill.workflow_graph.get_run"].permission, "allow")
                self.assertEqual(specs["mcp.service.catalog"].source, "mcp")

                provider = FakeCoreProvider(
                    [
                        CoreModelStep.tools(CoreToolCall(tool_name="skill.workflow_graph.get_run", arguments={"run_id": "run-1"}, call_id="call-skill")),
                        CoreModelStep.tools(CoreToolCall(tool_name="mcp.service.catalog", call_id="call-mcp")),
                        CoreModelStep.final("skills and mcp catalog are visible"),
                    ]
                )
                core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())
                out = core.run(
                    AgentCoreRequest(
                        message="inspect run",
                        session_id=bundle["session"]["session_id"],
                        project_key="demo_proj",
                        context={"root_task_id": "core-1"},
                    )
                )

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertEqual(out.tool_results[0].structured_content["skill_id"], "workflow_graph.get_run")
        self.assertEqual(out.tool_results[1].structured_content["services"][0]["service_id"], "project-database")
        mocked_invoke.assert_called_once()
        self.assertEqual(mocked_invoke.call_args.kwargs["payload"], {"run_id": "run-1"})

    def test_skill_search_load_and_direct_skill_invocation_chain(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="加载 workflow skill",
            project_key="demo_proj",
            task_blueprints=[],
        )
        skill_meta = {
            "skill_id": "workflow_graph.get_run",
            "owner": "workflow_graph.runtime",
            "execution_profile": "default",
            "required_permissions": [],
            "concurrency_class": "read_only",
            "approval_policy": {},
            "agent_batch_task_manifest": {"description": "Read workflow graph run state."},
        }

        with patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[skill_meta]):
            with patch(
                "app.services.agent_core.project_tools.invoke_skill",
                return_value={
                    "skill_id": "workflow_graph.get_run",
                    "result": {"run_id": "run-42", "status": "succeeded"},
                    "owner": "workflow_graph.runtime",
                    "execution_profile": "default",
                    "concurrency_class": "read_only",
                    "approval_policy": {},
                },
            ) as mocked_invoke:
                registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
                provider = FakeCoreProvider(
                    [
                        CoreModelStep.tools(
                            CoreToolCall(
                                tool_name="skill.search",
                                arguments={"query": "workflow_graph", "limit": 5},
                                call_id="call-skill-search",
                            )
                        ),
                        CoreModelStep.tools(
                            CoreToolCall(
                                tool_name="skill.load",
                                arguments={"skill_id": "workflow_graph.get_run"},
                                call_id="call-skill-load",
                            )
                        ),
                        CoreModelStep.tools(
                            CoreToolCall(
                                tool_name="skill.workflow_graph.get_run",
                                arguments={"run_id": "run-42"},
                                call_id="call-skill-invoke",
                            )
                        ),
                        CoreModelStep.final("workflow skill loaded and invoked"),
                    ]
                )
                out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
                    AgentCoreRequest(
                        message="找一下 workflow run skill 并读取 run-42",
                        session_id=bundle["session"]["session_id"],
                        project_key="demo_proj",
                    )
                )

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertEqual([result.tool_name for result in out.tool_results], ["skill.search", "skill.load", "skill.workflow_graph.get_run"])
        search_result = out.tool_results[0].structured_content
        self.assertEqual(search_result["items"][0]["skill_id"], "workflow_graph.get_run")
        load_result = out.tool_results[1].structured_content
        self.assertEqual(load_result["skill"]["skill_id"], "workflow_graph.get_run")
        self.assertEqual(load_result["tool_name"], "skill.workflow_graph.get_run")
        self.assertEqual(out.tool_results[2].structured_content["result"]["status"], "succeeded")
        mocked_invoke.assert_called_once()
        self.assertEqual(mocked_invoke.call_args.kwargs["payload"], {"run_id": "run-42"})
        self.assertEqual(provider.calls[1]["transcript"][-1]["tool_result"]["tool_name"], "skill.search")
        self.assertEqual(provider.calls[2]["transcript"][-1]["tool_result"]["tool_name"], "skill.load")

    def test_mcp_tools_list_and_call_mounted_tool_with_structured_failures(self):
        from app.services.agent_core.project_tools import clear_agent_core_mcp_tools, register_agent_core_mcp_tool

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="MCP 闭环",
            project_key="demo_proj",
            task_blueprints=[],
        )

        def echo_handler(arguments, request):
            return {
                "echo": arguments,
                "project_key": request.project_key,
                "session_id": request.session_id,
            }

        def boom_handler(arguments, request):
            raise RuntimeError("boom")

        clear_agent_core_mcp_tools()
        try:
            register_agent_core_mcp_tool(
                service_id="test-mcp",
                tool_name="test.echo",
                description="Echo arguments for AgentCore MCP contract tests.",
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "additionalProperties": False,
                },
                handler=echo_handler,
            )
            register_agent_core_mcp_tool(
                service_id="test-mcp",
                tool_name="test.boom",
                description="Raise a deterministic MCP handler failure.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=boom_handler,
            )
            registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
            provider = FakeCoreProvider(
                [
                    CoreModelStep.tools(
                        CoreToolCall(tool_name="mcp.tools.list", arguments={"service_id": "test-mcp"}, call_id="call-mcp-list")
                    ),
                    CoreModelStep.tools(
                        CoreToolCall(
                            tool_name="mcp.tool.call",
                            arguments={"service_id": "test-mcp", "tool_name": "test.echo", "arguments": {"text": "hello"}},
                            call_id="call-mcp-echo",
                        )
                    ),
                    CoreModelStep.tools(
                        CoreToolCall(
                            tool_name="mcp.tool.call",
                            arguments={"service_id": "test-mcp", "tool_name": "missing.tool", "arguments": {}},
                            call_id="call-mcp-missing",
                        )
                    ),
                    CoreModelStep.tools(
                        CoreToolCall(
                            tool_name="mcp.tool.call",
                            arguments={"service_id": "wrong-mcp", "tool_name": "test.echo", "arguments": {}},
                            call_id="call-mcp-service-mismatch",
                        )
                    ),
                    CoreModelStep.tools(
                        CoreToolCall(
                            tool_name="mcp.tool.call",
                            arguments={"service_id": "test-mcp", "tool_name": "test.boom", "arguments": {}},
                            call_id="call-mcp-handler-failure",
                        )
                    ),
                    CoreModelStep.final("mcp closed loop verified"),
                ]
            )
            out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
                AgentCoreRequest(
                    message="列出并调用 MCP echo 工具",
                    session_id=bundle["session"]["session_id"],
                    project_key="demo_proj",
                )
            )
        finally:
            clear_agent_core_mcp_tools()

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertEqual([item["tool_name"] for item in out.tool_results[0].structured_content["tools"]], ["test.boom", "test.echo"])
        self.assertEqual(out.tool_results[1].status, "completed")
        self.assertTrue(out.tool_results[1].structured_content["success"])
        self.assertEqual(out.tool_results[1].structured_content["result"]["echo"], {"text": "hello"})
        self.assertEqual(out.tool_results[1].structured_content["result"]["project_key"], "demo_proj")
        self.assertEqual(out.tool_results[2].status, "failed")
        self.assertEqual(out.tool_results[2].error["code"], "mcp_tool_not_configured")
        self.assertIn("test.echo", [item["tool_name"] for item in out.tool_results[2].structured_content["available_tools"]])
        self.assertEqual(out.tool_results[3].status, "failed")
        self.assertEqual(out.tool_results[3].error["code"], "mcp_tool_service_mismatch")
        self.assertEqual(out.tool_results[3].structured_content["service_status"]["service_id"], "wrong-mcp")
        self.assertEqual(out.tool_results[3].structured_content["service_status"]["implementation_state"], "not_configured")
        self.assertEqual(out.tool_results[4].status, "failed")
        self.assertEqual(out.tool_results[4].error["code"], "mcp_tool_failed")
        self.assertEqual(out.tool_results[4].structured_content["service_status"]["status"], "available")

    def test_external_mcp_runtime_status_matrix_feeds_catalog_and_tool_pool(self):
        from app.services.agent_runtime.external_tool_status import clear_external_service_states, register_external_service_state
        from app.services.agent_runtime.tool_pool import AgentToolPoolAssembler, ToolPoolRequest

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="MCP 状态矩阵",
            project_key="demo_proj",
            task_blueprints=[],
        )
        clear_external_service_states()
        try:
            register_external_service_state(
                service_id="browser-playwright",
                configured=True,
                reachable=False,
                auth_ok=True,
                server_error="connection refused",
                reason="local browser MCP configured but unreachable",
            )
            registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
            provider = FakeCoreProvider(
                [
                    CoreModelStep.tools(CoreToolCall(tool_name="mcp.service.catalog", call_id="call-catalog")),
                    CoreModelStep.final("external status visible"),
                ]
            )
            out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
                AgentCoreRequest(
                    message="查看外部 MCP 状态",
                    session_id=bundle["session"]["session_id"],
                    project_key="demo_proj",
                )
            )
            pool = AgentToolPoolAssembler().assemble(ToolPoolRequest(project_key="demo_proj"))
        finally:
            clear_external_service_states()

        browser_status = next(item for item in out.tool_results[0].structured_content["services"] if item["service_id"] == "browser-playwright")
        self.assertEqual(browser_status["status"], "server_error")
        self.assertEqual(browser_status["implementation_state"], "server_error")
        self.assertTrue(browser_status["configured"])
        self.assertFalse(browser_status["reachable"])
        tools = {item["capability_id"]: item for item in pool["tools"]}
        browser_tool = tools["mcp.service.browser-playwright"]
        self.assertEqual(browser_tool["service_status"], "server_error")
        self.assertEqual(browser_tool["implementation_state"], "server_error")
        self.assertFalse(browser_tool["enabled"])
        self.assertIn(browser_tool, pool["groups"]["disabled"])
        self.assertEqual(tools["writing.document.list"]["tool_group"], "core")
        self.assertEqual(tools["writing.document.read"]["tool_group"], "core")
        self.assertEqual(tools["writing.document.create"]["implementation_state"], "implemented")
        self.assertIn(tools["writing.document.create"], pool["groups"]["deferred"])
        self.assertEqual(tools["writing.document.insert_paragraph"]["implementation_state"], "implemented")
        self.assertEqual(tools["writing.document.citations.upsert"]["implementation_state"], "implemented")
        self.assertIn(tools["writing.document.citations.upsert"], pool["groups"]["deferred"])

    def test_tool_window_keeps_general_chat_empty_and_project_questions_small(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        specs = registry.list_specs()

        general = select_core_tool_window(message="你好", tool_specs=specs)
        self.assertEqual(general.profile, "conversation")
        self.assertEqual(general.visible_tool_count, 0)
        self.assertGreater(general.full_tool_count, general.visible_tool_count)

        project = select_core_tool_window(message="项目里有什么数据", tool_specs=specs)
        self.assertEqual(project.profile, "project-context")
        self.assertEqual(
            [spec.name for spec in project.specs],
            [
                "project.context.bundle",
                "project.summary.read",
                "project.structured_graph.query",
                "project.structured_data.search",
                "project.structured_data.item.read",
                "project.structured_data.items.read",
                "project.context.resource.read",
                "project.structured_data.quality_audit",
                "agent_artifact.search",
                "writing.document.list",
            ],
        )
        self.assertNotIn("mcp.service.catalog", [spec.name for spec in project.specs])

        materials = select_core_tool_window(message="项目库里已有资料有哪些", tool_specs=specs)
        self.assertEqual(materials.profile, "project-context")
        material_tool_names = [spec.name for spec in materials.specs]
        self.assertIn("project.context.bundle", material_tool_names)
        self.assertIn("project.structured_data.search", material_tool_names)
        self.assertIn("agent_artifact.search", material_tool_names)
        self.assertIn("writing.document.list", material_tool_names)
        self.assertNotIn("source_library.item.list", material_tool_names)

        material_collect = select_core_tool_window(message="帮我补充资料", tool_specs=specs)
        self.assertEqual(material_collect.profile, "material-collection")
        material_collect_tools = [spec.name for spec in material_collect.specs]
        self.assertIn("project.context.bundle", material_collect_tools)
        self.assertIn("project.structured_data.search", material_collect_tools)
        self.assertIn("source.discovery.plan", material_collect_tools)
        self.assertIn("source.web.search", material_collect_tools)
        self.assertIn("source.candidate.review", material_collect_tools)
        self.assertIn("ingest.url_pool.submit", material_collect_tools)
        self.assertIn("ingest.url_pool.status", material_collect_tools)
        self.assertIn("source.history.read", material_collect_tools)
        self.assertIn("source_library.item.search", material_collect_tools)
        self.assertIn("ingest.source_library.run", material_collect_tools)

        material_search = select_core_tool_window(message="帮我搜集一些机器人资料", tool_specs=specs)
        self.assertEqual(material_search.profile, "material-collection")
        material_search_tools = [spec.name for spec in material_search.specs]
        self.assertIn("project.context.bundle", material_search_tools)
        self.assertIn("source.discovery.plan", material_search_tools)
        self.assertIn("source.web.search", material_search_tools)
        self.assertIn("source.candidate.review", material_search_tools)
        self.assertIn("ingest.url_pool.submit", material_search_tools)
        self.assertIn("ingest.url_pool.status", material_search_tools)
        self.assertIn("source.history.read", material_search_tools)
        self.assertIn("ingest.source_library.run", material_search_tools)

        reference_collect = select_core_tool_window(message="帮我补充参考来源", tool_specs=specs)
        self.assertEqual(reference_collect.profile, "source-discovery-plan")
        reference_collect_tools = [spec.name for spec in reference_collect.specs]
        self.assertIn("source.discovery.plan", reference_collect_tools)
        self.assertIn("source.web.search", reference_collect_tools)
        self.assertIn("source.candidate.review", reference_collect_tools)

        external_material = select_core_tool_window(message="帮我补充外部资料", tool_specs=specs)
        self.assertEqual(external_material.profile, "source-discovery-plan")
        external_material_tools = [spec.name for spec in external_material.specs]
        self.assertIn("source.discovery.plan", external_material_tools)
        self.assertIn("source.web.search", external_material_tools)

        source_read = select_core_tool_window(message="当前项目有哪些来源库 item？", tool_specs=specs)
        self.assertEqual(source_read.profile, "source-library-read")
        self.assertIn("source_library.item.list", [spec.name for spec in source_read.specs])

        project_graph_data = select_core_tool_window(message="项目里已有 documents 和 graph_nodes 数据", tool_specs=specs)
        self.assertEqual(project_graph_data.profile, "project-context")
        self.assertIn("project.structured_data.search", [spec.name for spec in project_graph_data.specs])
        self.assertIn("project.structured_graph.query", [spec.name for spec in project_graph_data.specs])

        data_quality = select_core_tool_window(message="项目里的数据有没有脚本噪声，帮我做质量清理审计", tool_specs=specs)
        self.assertEqual(data_quality.profile, "data-quality-audit")
        self.assertEqual(
            [spec.name for spec in data_quality.specs],
            ["project.structured_data.quality_audit", "project.summary.read"],
        )

        source_run = select_core_tool_window(message="用来源库 market.general.baseline 补一轮证据", tool_specs=specs)
        self.assertEqual(source_run.profile, "source-library-execute-explicit")
        self.assertEqual([spec.name for spec in source_run.specs], ["ingest.source_library.run"])

        workflow = select_core_tool_window(message="项目里的工作流有哪些", tool_specs=specs)
        self.assertEqual(workflow.profile, "workflow")
        self.assertIn("workflow_graph.list", [spec.name for spec in workflow.specs])

        writing = select_core_tool_window(message="帮我在写作工作台插入一段研究背景", tool_specs=specs)
        self.assertEqual(writing.profile, "writing-workbench")
        self.assertIn("writing.document.list", [spec.name for spec in writing.specs])
        self.assertIn("writing.document.read", [spec.name for spec in writing.specs])
        self.assertIn("writing.document.create", [spec.name for spec in writing.specs])
        self.assertIn("writing.document.citations.upsert", [spec.name for spec in writing.specs])

        writing_create = select_core_tool_window(message="新建稿件并把内容贴进去", tool_specs=specs)
        self.assertEqual(writing_create.profile, "writing-workbench")
        self.assertIn("writing.document.create", [spec.name for spec in writing_create.specs])

        writing_citation = select_core_tool_window(message="把这张资料卡加入写作工作台引用框", tool_specs=specs)
        self.assertEqual(writing_citation.profile, "writing-workbench")
        self.assertIn("writing.document.citations.upsert", [spec.name for spec in writing_citation.specs])

        writing_material = select_core_tool_window(message="写作时帮我补充资料", tool_specs=specs)
        self.assertEqual(writing_material.profile, "writing-workbench")
        writing_material_tools = [spec.name for spec in writing_material.specs]
        self.assertIn("project.context.bundle", writing_material_tools)
        self.assertIn("project.structured_data.search", writing_material_tools)
        self.assertIn("agent_artifact.search", writing_material_tools)

        writing_search_material = select_core_tool_window(message="写作的时候帮我搜索一些资料", tool_specs=specs)
        self.assertEqual(writing_search_material.profile, "writing-workbench")
        writing_search_tools = [spec.name for spec in writing_search_material.specs]
        self.assertIn("project.context.bundle", writing_search_tools)
        self.assertIn("writing.document.list", writing_search_tools)
        self.assertIn("source.discovery.plan", writing_search_tools)

        text_existing_data = select_core_tool_window(message="这段正文需要补一些已有数据", tool_specs=specs)
        self.assertEqual(text_existing_data.profile, "writing-workbench")
        text_existing_data_tools = [spec.name for spec in text_existing_data.specs]
        self.assertIn("project.structured_data.search", text_existing_data_tools)
        self.assertIn("agent_artifact.search", text_existing_data_tools)
        self.assertNotIn("source_library.item.list", text_existing_data_tools)

        collected_text_data = select_core_tool_window(message="选区里用已入库资料补一些事实", tool_specs=specs)
        self.assertEqual(collected_text_data.profile, "writing-workbench")
        collected_text_tools = [spec.name for spec in collected_text_data.specs]
        self.assertIn("project.context.bundle", collected_text_tools)
        self.assertIn("project.structured_data.search", collected_text_tools)
        self.assertIn("writing.document.list", collected_text_tools)

        existing_reference_text = select_core_tool_window(message="这段正文先用项目库中既有参考来源补证据", tool_specs=specs)
        self.assertEqual(existing_reference_text.profile, "writing-workbench")
        existing_reference_tools = [spec.name for spec in existing_reference_text.specs]
        self.assertIn("project.context.bundle", existing_reference_tools)
        self.assertIn("project.structured_data.search", existing_reference_tools)
        self.assertIn("writing.document.list", existing_reference_tools)

        writing_gap_sources = select_core_tool_window(message="这段正文已有资料不足，帮我再找参考来源", tool_specs=specs)
        self.assertEqual(writing_gap_sources.profile, "writing-workbench")
        writing_gap_tools = [spec.name for spec in writing_gap_sources.specs]
        self.assertIn("project.context.bundle", writing_gap_tools)
        self.assertIn("source.discovery.plan", writing_gap_tools)
        self.assertIn("source.web.search", writing_gap_tools)
        self.assertIn("source.candidate.review", writing_gap_tools)

        writing_external_material = select_core_tool_window(message="写作时帮我补充外部资料", tool_specs=specs)
        self.assertEqual(writing_external_material.profile, "writing-workbench")
        writing_external_tools = [spec.name for spec in writing_external_material.specs]
        self.assertIn("source.discovery.plan", writing_external_tools)
        self.assertIn("source.web.search", writing_external_tools)
        self.assertIn("source.candidate.review", writing_external_tools)
        self.assertIn("ingest.url_pool.submit", writing_external_tools)
        self.assertIn("ingest.url_pool.status", writing_external_tools)
        self.assertIn("source.history.read", writing_external_tools)
        self.assertIn("ingest.source_library.run", writing_external_tools)

        outside_text_source = select_core_tool_window(message="这段文字需要补一点站外公开来源", tool_specs=specs)
        self.assertEqual(outside_text_source.profile, "writing-workbench")
        outside_text_tools = [spec.name for spec in outside_text_source.specs]
        self.assertIn("project.context.bundle", outside_text_tools)
        self.assertIn("source.discovery.plan", outside_text_tools)
        self.assertIn("source.web.search", outside_text_tools)
        self.assertIn("source.candidate.review", outside_text_tools)
        self.assertIn("ingest.url_pool.submit", outside_text_tools)
        self.assertIn("ingest.url_pool.status", outside_text_tools)
        self.assertIn("source.history.read", outside_text_tools)
        self.assertIn("writing.document.insert_paragraph", [spec.name for spec in writing.specs])
        self.assertIn("agent_investigation.trace.read", [spec.name for spec in writing.specs])

        long_task = select_core_tool_window(message="启动一个长程写作调查任务，持续追查线索", tool_specs=specs)
        self.assertEqual(long_task.profile, "long-task-investigation")
        self.assertIn("agent_task.plan.append", [spec.name for spec in long_task.specs])
        self.assertIn("project.context.bundle", [spec.name for spec in long_task.specs])
        self.assertIn("project.structured_graph.query", [spec.name for spec in long_task.specs])
        self.assertIn("agent_investigation.trace.read", [spec.name for spec in long_task.specs])
        self.assertIn("source.web.search", [spec.name for spec in long_task.specs])
        self.assertIn("source.history.read", [spec.name for spec in long_task.specs])
        self.assertIn("writing.document.create", [spec.name for spec in long_task.specs])
        self.assertIn("writing.document.insert_paragraph", [spec.name for spec in long_task.specs])
        self.assertIn("writing.document.citations.upsert", [spec.name for spec in long_task.specs])
        self.assertIn("ingest.source_library.run", [spec.name for spec in long_task.specs])

    def test_native_tool_calling_provider_maps_safe_names_to_canonical_tools(self):
        class FakeBoundNativeChat:
            def __init__(self):
                self.bound_tools = []

            def bind_tools(self, tools):
                self.bound_tools = list(tools)
                return self

            def invoke(self, messages):
                self.messages = messages
                return type(
                    "Response",
                    (),
                    {
                        "content": "",
                        "tool_calls": [
                            {
                                "name": "ingest_source_library_run",
                                "args": {"items": ["market.general.baseline"], "project_key": "demo_proj"},
                                "id": "native-call-1",
                            }
                        ],
                    },
                )()

        chat = FakeBoundNativeChat()
        provider = NativeToolCallingCoreProvider(chat_model=chat)
        request = AgentCoreRequest(
            message="用来源库 market.general.baseline 补一轮证据",
            session_id="as-native",
            project_key="demo_proj",
            turn_id="turn-native",
        )
        tools = [
            CoreToolSpec(
                name="ingest.source_library.run",
                description_for_model="Run source-library collection.",
                risk="write_external",
                permission="ask",
            )
        ]

        step = provider.next_step(request=request, tools=tools, transcript=[{"role": "user", "content": request.message}], remaining_budget={})

        self.assertEqual(step.step_type, "tool_calls")
        self.assertEqual(step.tool_calls[0].tool_name, "ingest.source_library.run")
        self.assertEqual(step.tool_calls[0].arguments["items"], ["market.general.baseline"])
        self.assertEqual(chat.bound_tools[0]["function"]["name"], "ingest_source_library_run")
        system_prompt = chat.messages[0]["content"]
        self.assertIn("origin/state/context", system_prompt)
        self.assertIn("source-library items are collection entrypoints", system_prompt)

    def test_native_tool_calling_provider_falls_back_when_bind_tools_is_unavailable(self):
        class InvokeOnlyChat:
            def invoke(self, prompt):
                return {"content": "should not be used directly"}

        fallback = FakeCoreProvider([CoreModelStep.final("fallback answer")])
        provider = NativeToolCallingCoreProvider(chat_model=InvokeOnlyChat(), fallback_provider=fallback)
        request = AgentCoreRequest(message="你好", session_id="as-native", project_key="demo_proj")

        step = provider.next_step(request=request, tools=[], transcript=[{"role": "user", "content": request.message}], remaining_budget={})

        self.assertEqual(step.step_type, "final_answer")
        self.assertEqual(step.content, "fallback answer")
        self.assertEqual(step.metadata["native_fallback_reason"], "native_bind_tools_unavailable")

    def test_json_provider_guardrail_calls_read_only_tools_after_invalid_project_answer(self):
        class InvalidJsonChat:
            def __init__(self):
                self.calls = 0

            def invoke(self, prompt):
                self.calls += 1
                return {"content": "项目里有一些数据，我可以稍后读取 project.summary.read。"}

        provider = JsonCoreProvider(chat_model=InvalidJsonChat())
        request = AgentCoreRequest(message="项目里有什么数据", session_id="as-json", project_key="demo_proj", turn_id="turn-json")
        tools = [
            CoreToolSpec(name="project.summary.read", description_for_model="Read project summary."),
            CoreToolSpec(name="project.structured_data.search", description_for_model="Search stored project structured data."),
            CoreToolSpec(name="source_library.item.list", description_for_model="List source-library items."),
            CoreToolSpec(name="ingest.status.read", description_for_model="Read ingest status."),
        ]

        step = provider.next_step(request=request, tools=tools, transcript=[{"role": "user", "content": request.message}], remaining_budget={})

        self.assertEqual(step.step_type, "tool_calls")
        self.assertEqual(
            [call.tool_name for call in step.tool_calls],
            ["project.summary.read", "project.structured_data.search", "source_library.item.list", "ingest.status.read"],
        )
        self.assertEqual(step.metadata["protocol_guardrail"], "tool_required_after_invalid_json")

    def test_json_provider_guardrail_uses_prior_context_for_keyword_followup_search(self):
        class ToolAvoidingChat:
            def invoke(self, prompt):
                return {"content": '{"type":"final_answer","content":"可以用机器人、具身智能这些关键词检索。"}'}

        provider = JsonCoreProvider(chat_model=ToolAvoidingChat())
        request = AgentCoreRequest(message="不可能没有，你用关键词检索试试看", session_id="as-json", project_key="demo_proj", turn_id="turn-json")
        tools = [
            CoreToolSpec(name="project.context.bundle", description_for_model="Read project context bundle."),
            CoreToolSpec(name="project.structured_data.search", description_for_model="Search stored project structured data."),
        ]

        step = provider.next_step(
            request=request,
            tools=tools,
            transcript=[
                {"role": "user", "content": "当前项目数据库中机器人信息中值得重视的部分有哪些"},
                {"role": "assistant", "content": "ID 14《机器人产业的地缘政治经济分析文档》需要补引用。"},
                {"role": "user", "content": request.message},
            ],
            remaining_budget={},
        )

        self.assertEqual(step.step_type, "tool_calls")
        self.assertEqual([call.tool_name for call in step.tool_calls], ["project.context.bundle", "project.structured_data.search"])
        self.assertIn("机器人产业", step.tool_calls[0].arguments["query"])
        self.assertIn("机器人产业", step.tool_calls[1].arguments["query"])

    def test_json_provider_guardrail_demands_read_from_manifest_before_final_answer(self):
        class ToolAvoidingChat:
            def invoke(self, prompt):
                return {"content": '{"type":"final_answer","content":"命中 1 条机器人资料。"}'}

        provider = JsonCoreProvider(chat_model=ToolAvoidingChat())
        request = AgentCoreRequest(message="总结机器人资料", session_id="as-json", project_key="demo_proj", turn_id="turn-json")
        step = provider.next_step(
            request=request,
            tools=[
                CoreToolSpec(name="project.structured_data.item.read", description_for_model="Read a concrete structured data item."),
            ],
            transcript=[
                {"role": "user", "content": request.message},
                {
                    "role": "tool",
                    "tool_result": {
                        "tool_name": "project.structured_data.search",
                        "structured_content": {
                            "result": {
                                "model_evidence_manifest": [
                                    {
                                        "read_tool": "project.structured_data.item.read",
                                        "read_arguments": {"dataset": "documents", "record_id": "doc-robot"},
                                    }
                                ]
                            }
                        },
                    },
                },
            ],
            remaining_budget={},
        )

        self.assertEqual(step.step_type, "tool_calls")
        self.assertEqual(step.metadata["protocol_guardrail"], "demand_read_before_final_answer")
        self.assertEqual(step.tool_calls[0].tool_name, "project.structured_data.item.read")
        self.assertEqual(step.tool_calls[0].arguments["record_id"], "doc-robot")

    def test_json_provider_guardrail_creates_workbench_document_from_prior_draft(self):
        class ToolAvoidingChat:
            def invoke(self, prompt):
                return {"content": '{"type":"final_answer","content":"我现在不能直接新建或写入工作台内容。"}'}

        provider = JsonCoreProvider(chat_model=ToolAvoidingChat())
        request = AgentCoreRequest(
            message="新建稿件并把内容贴进去",
            session_id="as-json",
            project_key="demo_proj_compare_0303_121137",
            turn_id="turn-json",
        )
        step = provider.next_step(
            request=request,
            tools=[CoreToolSpec(name="writing.document.create", description_for_model="Create a writing document.")],
            transcript=[
                {"role": "user", "content": "你直接输出新的写作工作台稿件"},
                {
                    "role": "assistant",
                    "content": "# 机器人：从自动执行工具到具身智能载体的演进\n\n记录 94 提到人形机器人市场加速。\n\n## 引用框\n- 记录 94：证券时报 IDC 报告",
                },
                {"role": "user", "content": request.message},
            ],
            remaining_budget={},
        )

        self.assertEqual(step.step_type, "tool_calls")
        self.assertEqual(step.metadata["protocol_guardrail"], "writing_create_intent")
        self.assertEqual(step.tool_calls[0].tool_name, "writing.document.create")
        self.assertEqual(step.tool_calls[0].arguments["project_key"], "demo_proj_compare_0303_121137")
        self.assertEqual(step.tool_calls[0].arguments["title"], "机器人：从自动执行工具到具身智能载体的演进")
        self.assertIn("记录 94", step.tool_calls[0].arguments["body_md"])
        self.assertIn("record:94", step.tool_calls[0].arguments["source_refs"])

    def test_json_provider_guardrail_prioritizes_writing_create_over_project_search_calls(self):
        class ProjectSearchFirstChat:
            def invoke(self, prompt):
                return {
                    "content": json.dumps(
                        {
                            "type": "tool_calls",
                            "tool_calls": [
                                {
                                    "tool_name": "project.structured_data.search",
                                    "arguments": {"query": "你直接输出新的写作工作台稿件"},
                                    "reason": "mistaken project search first",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
                }

        provider = JsonCoreProvider(chat_model=ProjectSearchFirstChat())
        request = AgentCoreRequest(
            message="你直接输出新的写作工作台稿件",
            session_id="as-json",
            project_key="demo_proj_compare_0303_121137",
            turn_id="turn-json",
        )
        step = provider.next_step(
            request=request,
            tools=[
                CoreToolSpec(name="project.structured_data.search", description_for_model="Search stored project structured data."),
                CoreToolSpec(name="writing.document.create", description_for_model="Create a writing document."),
            ],
            transcript=[
                {"role": "user", "content": "输出完整稿件"},
                {
                    "role": "assistant",
                    "content": "# 机器人：从自动执行工具到具身智能载体的演进\n\n记录 94 提到人形机器人市场加速。\n\n## 引用框\n- 记录 94：证券时报 IDC 报告",
                },
                {"role": "user", "content": request.message},
            ],
            remaining_budget={},
        )

        self.assertEqual(step.step_type, "tool_calls")
        self.assertEqual(step.metadata["protocol_guardrail"], "writing_create_intent")
        self.assertEqual([call.tool_name for call in step.tool_calls], ["writing.document.create"])
        self.assertNotEqual(step.tool_calls[0].arguments["body_md"], "")

    def test_project_structured_data_tool_returns_search_results_to_core(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="项目里有什么数据",
            project_key="demo_proj",
            task_blueprints=[],
        )

        def structured_searcher(**kwargs):
            self.assertEqual(kwargs["project_key"], "demo_proj")
            return {
                "contract_version": "project.structured_data.search.v1",
                "project_key": kwargs["project_key"],
                "query": "",
                "query_mode": "inventory",
                "inventory": [{"dataset": "documents", "label": "Documents", "sample_count": 1, "total_rows": 3}],
                "dataset_counts": {"documents": 1},
                "total_matches": 1,
                "items": [{"dataset": "documents", "record_id": 1, "title": "Market note", "summary": "stored note"}],
                "dataset_results": [],
                "errors": [],
            }

        registry = build_project_core_tool_registry(
            service=service,
            source_library_lister=lambda _: [],
            structured_data_searcher=structured_searcher,
        )
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="project.structured_data.search",
                        arguments={"query": "", "limit": 8},
                        call_id="call-structured",
                    )
                ),
                CoreModelStep.final("项目里已有 documents 数据。"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(
            AgentCoreRequest(
                message="项目里有什么数据",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertEqual(out.tool_results[0].tool_name, "project.structured_data.search")
        result = out.tool_results[0].structured_content["result"]
        self.assertEqual(result["query_mode"], "inventory")
        self.assertEqual(result["inventory"][0]["dataset"], "documents")
        self.assertEqual(result["items"][0]["title"], "Market note")

    def test_project_structured_data_item_read_can_follow_search_manifest(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="总结机器人资料",
            project_key="demo_proj",
            task_blueprints=[],
        )

        def structured_searcher(**kwargs):
            return {
                "contract_version": "project.structured_data.search.v1",
                "project_key": kwargs["project_key"],
                "query": kwargs.get("query") or "",
                "query_mode": "search",
                "dataset_counts": {"documents": 1},
                "total_matches": 1,
                "items": [
                    {
                        "dataset": "documents",
                        "record_id": "doc-robot",
                        "title": "Robot local note",
                        "summary": "内部资料显示仓储机器人试点加速，成本压力集中在传感器和集成环节。",
                    }
                ],
                "dataset_results": [],
                "errors": [],
            }

        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [], structured_data_searcher=structured_searcher)
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="project.structured_data.search",
                        arguments={"query": "机器人", "limit": 5},
                        call_id="call-search",
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="project.structured_data.item.read",
                        arguments={"dataset": "documents", "record_id": "doc-robot"},
                        call_id="call-read",
                    )
                ),
                CoreModelStep.final("机器人资料显示仓储试点加速，主要约束在传感器和集成成本。"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(
            AgentCoreRequest(
                message="帮我总结机器人资料",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        self.assertEqual(out.tool_results[1].tool_name, "project.structured_data.item.read")
        result = out.tool_results[1].structured_content["result"]
        self.assertEqual(result["item"]["title"], "Robot local note")
        self.assertEqual(result["model_evidence_manifest"][0]["record_id"], "doc-robot")
        self.assertIn("仓储试点加速", out.final_answer)

    def test_agent_task_plan_append_is_auto_allowed_and_idempotent(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="长程写作调查",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        tool_call = CoreToolCall(
            tool_name="agent_task.plan.append",
            call_id="call-plan",
            arguments={
                "idempotency_key": "plan-key-1",
                "sequential": True,
                "tasks": [
                    {
                        "subject": "检索本地结构化数据",
                        "phase": "research",
                        "read_set": ["project.structured_graph.query"],
                        "completion_criteria": ["形成证据摘要"],
                    },
                    {
                        "subject": "写入研究背景草稿",
                        "phase": "implementation",
                        "write_set": ["writing.document"],
                        "verification_steps": ["检查文档版本锁"],
                    },
                ],
            },
        )
        core = AgentCore(
            provider=FakeCoreProvider([CoreModelStep.tools(tool_call), CoreModelStep.final("计划已创建。")]),
            tool_registry=registry,
            tool_specs=registry.list_specs(),
        )

        first = core.run(
            AgentCoreRequest(
                message="启动长程写作调查",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        self.assertEqual(first.stop_reason, "final_answer")
        self.assertEqual(first.tool_results[0].status, "completed")
        self.assertEqual(first.tool_results[0].structured_content["created_count"], 2)
        self.assertNotIn("permission_requested", [event.event_type for event in first.events])

        second = AgentCore(
            provider=FakeCoreProvider([CoreModelStep.tools(tool_call), CoreModelStep.final("计划已存在。")]),
            tool_registry=registry,
            tool_specs=registry.list_specs(),
        ).run(
            AgentCoreRequest(
                message="继续同一个计划",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        self.assertEqual(second.tool_results[0].structured_content["created_count"], 0)
        self.assertTrue(second.tool_results[0].structured_content["duplicate_replay"])

    def test_long_task_resume_bundle_recovers_appended_plan_after_partial_completion(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="长程调查",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        plan_call = CoreToolCall(
            tool_name="agent_task.plan.append",
            call_id="call-plan-resume",
            arguments={
                "idempotency_key": "resume-plan-key",
                "sequential": True,
                "tasks": [
                    {"subject": "读取本地资料", "phase": "research", "task_id": "task-read-local"},
                    {"subject": "整理写作段落", "phase": "implementation", "task_id": "task-write-section"},
                ],
            },
        )
        first = AgentCore(
            provider=FakeCoreProvider([CoreModelStep.tools(plan_call), CoreModelStep.final("计划已追加，等待继续。")]),
            tool_registry=registry,
            tool_specs=registry.list_specs(),
        ).run(
            AgentCoreRequest(
                message="做一个长程调查并持续推进",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )
        created_tasks = first.tool_results[0].structured_content["tasks"]
        self.assertEqual([task["task_id"] for task in created_tasks], ["task-read-local", "task-write-section"])

        service.release_task(
            bundle["session"]["session_id"],
            "task-read-local",
            status="completed",
            result_summary="已读取本地资料。",
            result_payload={"evidence_count": 3},
            activity="partial completion before resume",
        )

        resume_provider = FakeCoreProvider(
            [
                CoreModelStep.tools(CoreToolCall(tool_name="agent_session.resume_bundle", arguments={"limit": 20}, call_id="call-resume")),
                CoreModelStep.final("已恢复任务状态，将继续整理写作段落。"),
            ]
        )
        resumed = AgentCore(provider=resume_provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
            AgentCoreRequest(
                message="继续刚才的长任务",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        resume_content = resumed.tool_results[0].structured_content
        tasks_by_id = {task["task_id"]: task for task in resume_content["recent_tasks"]}
        self.assertEqual(tasks_by_id["task-read-local"]["status"], "completed")
        self.assertEqual(tasks_by_id["task-read-local"]["result_summary"], "已读取本地资料。")
        self.assertIn(tasks_by_id["task-write-section"]["status"], {"pending", "blocked"})
        self.assertIn("task-write-section", {task["task_id"] for task in resume_content["active_tasks"]})
        self.assertEqual(resume_content["counts"]["tasks"], len(service.list_tasks(bundle["session"]["session_id"])))
        self.assertEqual(resume_provider.calls[1]["transcript"][-1]["tool_result"]["tool_name"], "agent_session.resume_bundle")

    def test_long_task_stage_state_survives_resume_bundle_and_replay(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="长程调查写作",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        plan_call = CoreToolCall(
            tool_name="agent_task.plan.append",
            call_id="call-plan-stage",
            arguments={
                "idempotency_key": "stage-plan-key",
                "tasks": [
                    {"subject": "内部证据检索", "phase": "research", "task_id": "task-internal-pass"},
                    {"subject": "外部资料补充", "phase": "research", "task_id": "task-external-pass", "blocked_by_refs": ["prev"]},
                    {"subject": "写作输出", "phase": "implementation", "task_id": "task-draft-output", "blocked_by_refs": ["prev"]},
                ],
            },
        )
        stage_call = CoreToolCall(
            tool_name="agent_long_task.stage.update",
            call_id="call-stage-internal",
            arguments={
                "task_id": "task-internal-pass",
                "task_kind": "mixed",
                "stage": "internal_evidence",
                "stage_status": "completed",
                "summary": "已完成内部资料检索，发现仍缺官方来源。",
                "idempotency_key": "stage-internal-key",
                "evidence_refs": ["project.context.bundle", {"artifact": "local-evidence.json"}],
                "gap_list": ["缺官方披露", "缺监管口径"],
                "next_actions": ["规划外部发现", "追踪候选来源"],
            },
        )
        read_call = CoreToolCall(
            tool_name="agent_long_task.stage.read",
            call_id="call-stage-read",
            arguments={},
        )
        resume_call = CoreToolCall(
            tool_name="agent_session.resume_bundle",
            call_id="call-stage-resume",
            arguments={"limit": 20},
        )
        first = AgentCore(
            provider=FakeCoreProvider(
                [
                    CoreModelStep.tools(plan_call),
                    CoreModelStep.tools(stage_call),
                    CoreModelStep.tools(read_call),
                    CoreModelStep.tools(resume_call),
                    CoreModelStep.final("已保存长任务阶段状态。"),
                ]
            ),
            tool_registry=registry,
            tool_specs=registry.list_specs(),
        ).run(
            AgentCoreRequest(
                message="执行长程调查写作，持续保存阶段",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        self.assertEqual(first.stop_reason, "final_answer")
        self.assertEqual(first.tool_results[1].tool_name, "agent_long_task.stage.update")
        stage_state = first.tool_results[1].structured_content["state"]
        self.assertEqual(stage_state["current_stage"], "gap_analysis")
        internal_stage = next(item for item in stage_state["stage_summaries"] if item["stage"] == "internal_evidence")
        self.assertEqual(internal_stage["status"], "completed")
        self.assertEqual(internal_stage["counts"]["evidence_refs"], 2)
        self.assertEqual(internal_stage["counts"]["gap_list"], 2)
        read_state = first.tool_results[2].structured_content["state"]
        self.assertEqual(read_state["completed_stages"], ["plan", "internal_evidence"])
        resume_content = first.tool_results[3].structured_content
        self.assertEqual(resume_content["counts"]["long_task_states"], 1)
        self.assertEqual(resume_content["long_task_states"][0]["completed_stages"], ["plan", "internal_evidence"])
        task = next(item for item in resume_content["recent_tasks"] if item["task_id"] == "task-internal-pass")
        self.assertEqual(task["metadata"]["long_task_state_artifact"], "agent_long_task.state.json")
        self.assertEqual(task["result_payload"]["long_task_stage_state"]["completed_stages"], ["plan", "internal_evidence"])

        replay = AgentCore(
            provider=FakeCoreProvider([CoreModelStep.tools(stage_call), CoreModelStep.final("阶段状态已存在。")]),
            tool_registry=registry,
            tool_specs=registry.list_specs(),
        ).run(
            AgentCoreRequest(
                message="硬刷新后重放阶段状态",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )
        self.assertTrue(replay.tool_results[0].structured_content["replayed"])
        replay_state = replay.tool_results[0].structured_content["state"]
        replay_internal = next(item for item in replay_state["stage_summaries"] if item["stage"] == "internal_evidence")
        self.assertEqual(replay_internal["counts"]["evidence_refs"], 2)
        self.assertEqual(replay_internal["counts"]["gap_list"], 2)

    def test_long_task_final_answer_cannot_claim_completion_without_done_ledger(self):
        provider = FakeCoreProvider([CoreModelStep.final("已完成这个长任务。", model_path="fake")])
        registry = CoreToolRegistry()
        result = AgentCore(provider=provider, tool_registry=registry, tool_specs=[]).run(
            AgentCoreRequest(
                message="执行一个长任务：持续调查机器人商业化线索",
                session_id="as-long-gap",
                project_key="demo_proj",
                context={"tool_window_profile": "long-task-investigation"},
            )
        )

        self.assertIn("长任务阶段 ledger 尚未写入", result.final_answer)

    def test_investigation_leads_append_persists_session_artifact_without_approval(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="多轮调查",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="agent_investigation.leads.append",
                        call_id="call-leads",
                        arguments={
                            "project_key": "demo_proj",
                            "goal": "追查机器人商业化线索",
                            "idempotency_key": "robot-leads-1",
                            "clue_nodes": [{"id": "robot", "label": "机器人"}],
                            "pending_questions": ["有哪些本地来源可以补证据"],
                            "followed_leads": [{"url": "https://example.com/robot"}],
                            "rejected_leads": ["低质量转载"],
                            "citations": [{"source_id": "doc-1", "quote": "robot"}],
                        },
                    )
                ),
                CoreModelStep.final("已记录调查线索。"),
            ]
        )
        out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
            AgentCoreRequest(
                message="记录这轮调查线索",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertNotIn("permission_requested", [event.event_type for event in out.events])
        artifact = next(item for item in service.list_artifacts(bundle["session"]["session_id"]) if item["name"] == "investigation.leads.json")
        content = artifact["content_json"]
        self.assertEqual(content["contract_version"], "agent_investigation.leads.v1")
        self.assertEqual(content["clue_nodes"][0]["id"], "robot")
        self.assertEqual(content["pending_questions"][0]["text"], "有哪些本地来源可以补证据")
        self.assertEqual(out.tool_results[0].structured_content["counts"]["citations"], 1)

    def test_investigation_trace_read_builds_multi_hop_trace_from_session_artifact(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="多跳线索追查",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="agent_investigation.leads.append",
                        call_id="call-leads",
                        arguments={
                            "project_key": "demo_proj",
                            "artifact_name": "robot-investigation.leads.json",
                            "goal": "追查机器人商业化链条",
                            "idempotency_key": "robot-hop-1",
                            "clue_nodes": [
                                {"id": "robot_company", "label": "机器人公司"},
                                {"id": "product_line", "label": "配送机器人产品线"},
                                {"id": "funding_round", "label": "B 轮融资"},
                                {"id": "regulator", "label": "监管备案"},
                            ],
                            "clue_edges": [
                                {"source": "robot_company", "target": "product_line", "relation": "develops"},
                                {"source": "product_line", "target": "funding_round", "relation": "funded_by"},
                                {"source": "funding_round", "target": "regulator", "relation": "requires_disclosure"},
                            ],
                            "pending_questions": ["监管备案是否有官方来源"],
                            "followed_leads": [{"url": "https://example.com/robot-funding", "source": "seed"}],
                            "citations": [{"source_id": "doc-robot-1", "quote": "robot funding"}],
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="agent_investigation.trace.read",
                        call_id="call-trace",
                        arguments={
                            "project_key": "demo_proj",
                            "artifact_name": "robot-investigation.leads.json",
                            "focus_node_id": "robot_company",
                            "max_hops": 2,
                            "max_items": 10,
                        },
                    )
                ),
                CoreModelStep.final("已读取多跳线索。"),
            ]
        )

        out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
            AgentCoreRequest(
                message="读取机器人调查的多跳线索",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        self.assertEqual(out.stop_reason, "final_answer")
        trace = out.tool_results[1].structured_content
        self.assertEqual(trace["contract_version"], "agent_investigation.trace.v1")
        self.assertEqual(trace["focus_node_id"], "robot_company")
        self.assertTrue(trace["focus_found"])
        self.assertEqual({item["id"] for item in trace["nodes"]}, {"robot_company", "product_line", "funding_round"})
        self.assertNotIn("regulator", {item["id"] for item in trace["nodes"]})
        self.assertEqual({item["relation"] for item in trace["edges"]}, {"develops", "funded_by"})
        self.assertEqual(trace["counts"]["all_nodes"], 4)
        self.assertEqual(trace["counts"]["all_edges"], 3)
        self.assertIn("监管备案是否有官方来源", trace["pending_questions"][0]["text"])
        self.assertIn("pending_questions", trace["next_steps"][0])
        self.assertEqual(provider.calls[2]["transcript"][-1]["tool_result"]["tool_name"], "agent_investigation.trace.read")

    def test_structured_graph_tools_use_project_searcher(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="图谱检索",
            project_key="demo_proj",
            task_blueprints=[],
        )
        calls = []

        def structured_searcher(**kwargs):
            calls.append(kwargs)
            return {
                "contract_version": "project.structured_data.search.v1",
                "project_key": kwargs["project_key"],
                "query": kwargs.get("query"),
                "query_mode": "search",
                "inventory": [{"dataset": item, "label": item, "sample_count": 1, "total_rows": 10} for item in kwargs["datasets"]],
                "dataset_counts": {item: 1 for item in kwargs["datasets"]},
                "dataset_total_rows": {item: 10 for item in kwargs["datasets"]},
                "total_stored_rows": 10 * len(kwargs["datasets"]),
                "total_matches": 1,
                "items": [{"dataset": kwargs["datasets"][0], "record_id": 1, "title": "Robot", "summary": "robot node"}],
                "dataset_results": [],
                "errors": [],
            }

        registry = build_project_core_tool_registry(
            service=service,
            source_library_lister=lambda _: [],
            structured_data_searcher=structured_searcher,
        )
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(tool_name="project.graph.search", arguments={"query": "机器人"}, call_id="call-graph"),
                    CoreToolCall(tool_name="project.structured_graph.query", arguments={"query": "机器人"}, call_id="call-sg"),
                ),
                CoreModelStep.final("已读取图谱与结构化数据。"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        out = core.run(
            AgentCoreRequest(
                message="追查机器人线索",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertEqual(calls[0]["datasets"], ["graph_nodes"])
        self.assertIn("documents", calls[1]["datasets"])
        self.assertIn("graph_nodes", calls[1]["datasets"])
        self.assertEqual(out.tool_results[0].structured_content["graph_nodes"][0]["title"], "Robot")
        self.assertIn("items_by_dataset", out.tool_results[1].structured_content)

    def test_source_web_search_returns_trusted_candidates_without_ingest(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="外部候选资料搜索",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="source.web.search",
                        call_id="call-web-search",
                        arguments={
                            "query": "robotics commercialization official data",
                            "provider": "ddg",
                            "language": "en",
                            "max_results": 3,
                            "min_trust_score": 40,
                        },
                    )
                ),
                CoreModelStep.final("已找到外部候选来源。"),
            ]
        )
        with patch(
            "app.services.agent_core.project_tools.search_sources",
            return_value=[
                {
                    "title": "Robotics market official report",
                    "link": "https://example.gov/reports/robotics-market?utm_source=ddg",
                    "snippet": "Official robotics market data.",
                    "source": "ddg",
                    "keyword": "robotics commercialization official data",
                }
            ],
        ) as mocked_search:
            out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
                AgentCoreRequest(
                    message="帮我搜索外部机器人商业化资料",
                    session_id=bundle["session"]["session_id"],
                    project_key="demo_proj",
                )
            )

        mocked_search.assert_called_once()
        self.assertEqual(out.tool_results[0].tool_name, "source.web.search")
        content = out.tool_results[0].structured_content
        self.assertTrue(content["external_network_io"])
        self.assertFalse(content["project_write_performed"])
        self.assertFalse(content["ingest_performed"])
        self.assertEqual(content["candidate_count"], 1)
        candidate = content["candidates"][0]
        self.assertEqual(candidate["title"], "Robotics market official report")
        self.assertEqual(candidate["trust"]["domain"], "example.gov")
        self.assertEqual(candidate["trust"]["status"], "accepted")

    def test_source_discovery_plan_returns_capability_matrix(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="资料搜集矩阵规划",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(
            service=service,
            source_library_lister=lambda project_key: [{"item_key": "robot.baseline", "name": "Robot Baseline"}],
        )
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="source.discovery.plan",
                        call_id="call-matrix-plan",
                        arguments={
                            "topic": "机器人商业化政策与市场资料",
                            "query_terms": ["robotics commercialization", "policy", "market"],
                            "source_kinds": ["official", "regulatory", "market"],
                            "matrix_mode": True,
                            "max_candidates": 6,
                        },
                    )
                ),
                CoreModelStep.final("已生成资料搜集矩阵。"),
            ]
        )

        out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
            AgentCoreRequest(
                message="帮我搜集一些机器人商业化资料，要覆盖内部和外部来源",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        content = out.tool_results[0].structured_content
        self.assertIn("capability_matrix", content)
        matrix = content["capability_matrix"]
        self.assertEqual(matrix["contract_version"], "agent_core.source_capability_matrix.v1")
        self.assertGreaterEqual(matrix["summary"]["keyword_variant_count"], 3)
        self.assertTrue(matrix["summary"]["merge_rank_required"])
        self.assertIn("internal_routes", matrix["tool_provider_matrix"])
        self.assertIn("provider_routes", matrix["tool_provider_matrix"])
        self.assertIn("source_catalog", {item["scope"] for item in matrix["scope_matrix"]})
        self.assertIn("provider readiness check", matrix["verification_matrix"])
        self.assertEqual(content["matrix_summary"]["source_item_count"], 1)

    def test_source_web_search_matrix_merges_ranks_and_keeps_branch_diagnostics(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="外部资料矩阵检索",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="source.web.search",
                        call_id="call-web-search-matrix",
                        arguments={
                            "query": "robotics commercialization",
                            "query_variants": [
                                "robotics commercialization official report",
                                "robotics commercialization market statistics",
                            ],
                            "providers": ["serper", "ddg"],
                            "provider": "serper",
                            "language": "en",
                            "matrix_mode": True,
                            "max_results": 5,
                            "min_trust_score": 40,
                        },
                    )
                ),
                CoreModelStep.final("已完成矩阵检索。"),
            ]
        )

        def fake_search(query, *, language, max_results, provider, days_back, exclude_existing):
            self.assertEqual(language, "en")
            self.assertTrue(exclude_existing)
            if "official" in query:
                return [
                    {
                        "title": f"Official robotics report via {provider}",
                        "link": "https://example.gov/robotics/report",
                        "snippet": "Official robotics commercialization report.",
                        "source": provider,
                        "keyword": query,
                    }
                ]
            return [
                {
                    "title": f"Robotics market dataset via {provider}",
                    "link": f"https://example.org/robotics/market-{provider}",
                    "snippet": "Market statistics for robotics commercialization.",
                    "source": provider,
                    "keyword": query,
                }
            ]

        with patch("app.services.agent_core.project_tools.search_sources", side_effect=fake_search) as mocked_search:
            out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
                AgentCoreRequest(
                    message="帮我搜集机器人商业化资料，要多路线检索后合并排序",
                    session_id=bundle["session"]["session_id"],
                    project_key="demo_proj",
                )
            )

        self.assertEqual(mocked_search.call_count, 4)
        content = out.tool_results[0].structured_content
        self.assertTrue(content["matrix_mode"])
        self.assertEqual(content["matrix_summary"]["branch_count"], 4)
        self.assertEqual(content["matrix_summary"]["query_variant_count"], 2)
        self.assertEqual(content["matrix_summary"]["provider_count"], 2)
        self.assertTrue(content["matrix_summary"]["merge_rank_applied"])
        self.assertLess(content["candidate_count"], 4)
        self.assertEqual(content["candidate_count"], content["matrix_summary"]["merged_candidate_count"])
        self.assertEqual(len(content["search_branches"]), 4)
        self.assertTrue(all("provider_diagnostics" in branch for branch in content["search_branches"]))
        self.assertEqual(content["candidates"][0]["matrix_rank"], 1)
        self.assertGreaterEqual(content["candidates"][0]["branch_count"], 1)
        self.assertIn("branches=4", provider.calls[1]["transcript"][-1]["tool_result"]["model_summary"])

    def test_source_web_search_empty_result_reports_provider_uncertainty(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="外部候选资料搜索空结果",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="source.web.search",
                        call_id="call-web-search-empty",
                        arguments={
                            "query": "robotics commercialization official data",
                            "provider": "auto",
                            "language": "en",
                            "max_results": 3,
                        },
                    )
                ),
                CoreModelStep.final("搜索服务当前没有返回候选。"),
            ]
        )
        with patch("app.services.agent_core.project_tools.search_sources", return_value=[]):
            out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
                AgentCoreRequest(
                    message="帮我搜索外部机器人商业化资料",
                    session_id=bundle["session"]["session_id"],
                    project_key="demo_proj",
                )
            )

        content = out.tool_results[0].structured_content
        self.assertEqual(content["candidate_count"], 0)
        self.assertEqual(content["next_gate"], "retry_configured_provider_or_manual_candidate_urls")
        self.assertIn("provider_diagnostics", content)
        self.assertIn("provider_rate_limited", content["provider_diagnostics"]["empty_result_likely_causes"])
        self.assertIn("Do not conclude absence of evidence", content["empty_result_guidance"])

    def test_source_web_search_diagnostics_use_google_search_env_names(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="Google 外部搜索 readiness",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="source.web.search",
                        call_id="call-google-readiness",
                        arguments={
                            "query": "robotics official report",
                            "provider": "google",
                            "language": "en",
                            "max_results": 3,
                        },
                    )
                ),
                CoreModelStep.final("Google 搜索 readiness 已检查。"),
            ]
        )
        with patch.dict(
            os.environ,
            {
                "GOOGLE_SEARCH_API_KEY": "test-google-key",
                "GOOGLE_SEARCH_CSE_ID": "test-cse",
                "GOOGLE_CSE_ID": "",
                "GOOGLE_API_KEY": "",
            },
            clear=False,
        ), patch("app.services.agent_core.project_tools.search_sources", return_value=[]):
            out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
                AgentCoreRequest(
                    message="帮我用 Google 搜索外部机器人资料",
                    session_id=bundle["session"]["session_id"],
                    project_key="demo_proj",
                )
            )

        diagnostics = out.tool_results[0].structured_content["provider_diagnostics"]
        self.assertTrue(diagnostics["google_configured"])
        self.assertTrue(diagnostics["google_api_key_configured"])
        self.assertTrue(diagnostics["google_cse_configured"])
        self.assertTrue(diagnostics["selected_provider_configured"])
        self.assertIn("google", diagnostics["configured_paid_providers"])
        self.assertNotIn("google_not_configured", diagnostics["empty_result_likely_causes"])

    def test_source_web_search_diagnostics_keep_local_open_search_explicit_only(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="本地开源搜索 provider 显式护栏",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="source.web.search",
                        call_id="call-searxng-readiness",
                        arguments={
                            "query": "robotics official report",
                            "provider": "searxng",
                            "language": "en",
                            "max_results": 3,
                        },
                    )
                ),
                CoreModelStep.final("SearXNG readiness 已检查。"),
            ]
        )
        with patch.dict(
            os.environ,
            {
                "SEARXNG_BASE_URL": "http://127.0.0.1:8088",
                "YACY_BASE_URL": "http://127.0.0.1:8090",
            },
            clear=False,
        ), patch("app.services.agent_core.project_tools.search_sources", return_value=[]):
            out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
                AgentCoreRequest(
                    message="帮我用 SearXNG 搜索外部机器人资料",
                    session_id=bundle["session"]["session_id"],
                    project_key="demo_proj",
                )
            )

        diagnostics = out.tool_results[0].structured_content["provider_diagnostics"]
        self.assertEqual(diagnostics["provider"], "searxng")
        self.assertEqual(diagnostics["explicit_experimental_providers"], ["searxng", "yacy"])
        self.assertEqual(diagnostics["recommended_provider_order"], ["serper", "google", "serpstack", "serpapi", "ddg"])
        self.assertNotIn("searxng", diagnostics["recommended_provider_order"])
        self.assertNotIn("yacy", diagnostics["recommended_provider_order"])
        self.assertTrue(diagnostics["provider_readiness"]["searxng"]["configured"])
        self.assertTrue(diagnostics["provider_readiness"]["yacy"]["configured"])
        self.assertTrue(diagnostics["selected_provider_configured"])
        self.assertEqual(diagnostics["searxng_base_url"], "http://127.0.0.1:8088")
        self.assertEqual(diagnostics["yacy_base_url"], "http://127.0.0.1:8090")

    def test_source_history_read_recovers_recent_project_candidate_state(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        previous = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="上一轮外部来源调查",
            project_key="demo_proj",
            task_blueprints=[],
        )
        current = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="继续写作来源调查",
            project_key="demo_proj",
            task_blueprints=[],
        )
        previous_session_id = previous["session"]["session_id"]
        current_session_id = current["session"]["session_id"]
        service.store.upsert_artifact(
            {
                "session_id": previous_session_id,
                "name": "source.candidate_reviews.json",
                "artifact_type": "source_candidate_review_state",
                "mime_type": "application/json",
                "content_json": {
                    "contract_version": "source.candidate.review.v1",
                    "project_key": "demo_proj",
                    "reviews": [
                        {
                            "review_key": "review-robotics",
                            "decision": "approved",
                            "reviewed_at": "2026-05-14T01:00:00Z",
                            "candidate": {
                                "title": "Robotics policy report",
                                "url": "https://example.gov/robotics-policy",
                            },
                            "next_gate": "run_ingest.url_pool.submit_with_payload",
                        }
                    ],
                },
            }
        )
        service.store.upsert_artifact(
            {
                "session_id": previous_session_id,
                "name": "ingest.url_pool_submissions.json",
                "artifact_type": "url_pool_submission_state",
                "mime_type": "application/json",
                "content_json": {
                    "contract_version": "ingest.url_pool.submit.v1",
                    "project_key": "demo_proj",
                    "submissions": [
                        {
                            "url": "https://example.gov/robotics-policy",
                            "submitted_at": "2026-05-14T01:01:00Z",
                            "dispatch_result": {"task_id": "urlpool-robotics", "status": "queued"},
                        }
                    ],
                },
            }
        )
        service.store.upsert_artifact(
            {
                "session_id": previous_session_id,
                "name": "ingest.url_pool_task_events.json",
                "artifact_type": "url_pool_ingest_task_event_state",
                "mime_type": "application/json",
                "content_json": {
                    "contract_version": "ingest.url_pool.task_event.v1",
                    "events": [
                        {
                            "event_id": "event-urlpool-robotics-completed",
                            "url": "https://example.gov/robotics-policy",
                            "task_id": "urlpool-robotics",
                            "status": "completed",
                            "recorded_at": "2026-05-14T01:02:00Z",
                        }
                    ],
                },
            }
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="source.history.read",
                        call_id="call-source-history",
                        arguments={"project_key": "demo_proj", "include_recent_sessions": True, "session_limit": 5},
                    )
                ),
                CoreModelStep.final("已恢复上一轮来源历史。"),
            ]
        )

        out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
            AgentCoreRequest(
                message="继续之前的候选来源调查",
                session_id=current_session_id,
                project_key="demo_proj",
            )
        )

        content = out.tool_results[0].structured_content
        self.assertEqual(content["contract_version"], "source.history.read.v1")
        self.assertEqual(content["totals"]["approved"], 1)
        self.assertEqual(content["totals"]["submissions"], 1)
        self.assertEqual(content["totals"]["task_events"], 1)
        self.assertEqual(content["next_gate"], "resume_reviewed_sources_or_check_url_pool_status")
        session_ids = {item["session_id"] for item in content["sessions"]}
        self.assertIn(previous_session_id, session_ids)
        self.assertIn(current_session_id, session_ids)

    def test_source_candidate_review_records_decision_and_url_pool_payload(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="候选来源审阅",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="source.candidate.review",
                        call_id="call-candidate-review",
                        arguments={
                            "decision": "approved",
                            "preferred_ingest": "url_pool",
                            "reason": "用户选择采集",
                            "idempotency_key": "candidate-example-gov",
                            "candidate": {
                                "title": "Robotics market official report",
                                "url": "https://example.gov/reports/robotics-market",
                                "snippet": "Official robotics market data.",
                                "provider": "ddg",
                                "trust": {"status": "accepted", "trust_score": 80, "domain": "example.gov"},
                            },
                        },
                    )
                ),
                CoreModelStep.final("候选来源已审阅。"),
            ]
        )

        out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
            AgentCoreRequest(
                message="采集这个候选来源",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        result = out.tool_results[0].structured_content
        self.assertEqual(out.tool_results[0].tool_name, "source.candidate.review")
        self.assertEqual(result["decision"], "approved")
        self.assertEqual(result["ingest_payload"]["type"], "url_pool")
        self.assertEqual(result["ingest_payload"]["url"], "https://example.gov/reports/robotics-market")
        self.assertEqual(result["next_gate"], "run_ingest.url_pool.submit_with_payload")
        artifact = next(item for item in service.list_artifacts(bundle["session"]["session_id"]) if item["name"] == "source.candidate_reviews.json")
        self.assertEqual(artifact["name"], "source.candidate_reviews.json")
        self.assertEqual(artifact["content_json"]["counts"]["approved"], 1)

    def test_ingest_url_pool_submit_queues_approved_candidate_payload(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="候选来源提交采集",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        task_calls: list[tuple] = []

        class _Task:
            id = "agent-url-pool-test"

        def fake_apply_async(*, args, task_id):
            task_calls.append((tuple(args), task_id))
            return _Task()

        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="ingest.url_pool.submit",
                        call_id="call-url-pool-submit",
                        arguments={
                            "ingest_payload": {
                                "type": "url_pool",
                                "project_key": "demo_proj",
                                "url": "https://example.gov/reports/robotics-market",
                                "source_name": "Robotics market official report",
                                "metadata": {"source": "agent_candidate_review", "title": "Robotics market official report"},
                            },
                            "query_terms": ["robotics", "market"],
                            "async_mode": True,
                            "idempotency_key": "candidate-example-gov:url_pool",
                        },
                    )
                ),
                CoreModelStep.final("已提交 URL-pool 采集。"),
            ]
        )

        with patch("app.services.tasks.task_ingest_url_via_source_library.apply_async", fake_apply_async):
            out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
                AgentCoreRequest(
                    message="采集这个候选 URL",
                    session_id=bundle["session"]["session_id"],
                    project_key="demo_proj",
                )
            )

        self.assertEqual(len(task_calls), 1)
        task_args, task_id = task_calls[0]
        self.assertEqual(task_args[:4], ("https://example.gov/reports/robotics-market", ["robotics", "market"], False, "demo_proj"))
        self.assertTrue(str(task_id).startswith("agent-url-pool-"))
        self.assertEqual(task_args[4]["_agent_core_url_pool_submission"]["session_id"], bundle["session"]["session_id"])
        self.assertEqual(task_args[4]["_agent_core_url_pool_submission"]["idempotency_key"], "candidate-example-gov:url_pool")
        self.assertEqual(out.tool_results[0].tool_name, "ingest.url_pool.submit")
        result = out.tool_results[0].structured_content
        self.assertEqual(result["task_id"], "agent-url-pool-test")
        self.assertEqual(result["dispatch_result"]["status"], "queued")
        self.assertEqual(result["next_gate"], "inspect_ingest_status_or_source_artifacts")
        artifact = next(item for item in service.list_artifacts(bundle["session"]["session_id"]) if item["name"] == "ingest.url_pool_submissions.json")
        self.assertEqual(artifact["content_json"]["counts"]["submitted"], 1)
        self.assertEqual(artifact["content_json"]["submissions"][0]["url"], "https://example.gov/reports/robotics-market")

    def test_ingest_url_pool_status_returns_verified_evidence_from_project_records(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="候选来源状态复核",
            project_key="demo_proj",
            task_blueprints=[],
        )
        service.store.upsert_artifact(
            {
                "session_id": bundle["session"]["session_id"],
                "name": "ingest.url_pool_submissions.json",
                "artifact_type": "url_pool_ingest_submission_state",
                "mime_type": "application/json",
                "content_json": {
                    "contract_version": "ingest.url_pool.submit.v1",
                    "project_key": "demo_proj",
                    "submissions": [
                        {
                            "url": "https://example.gov/reports/robotics-market",
                            "dispatch_result": {"task_id": "url-pool-task-1", "status": "queued"},
                        }
                    ],
                },
                "content_text": "{}",
            }
        )

        def fake_searcher(**kwargs):
            self.assertEqual(kwargs["datasets"], ["documents", "sources"])
            self.assertEqual(kwargs["query"], "https://example.gov/reports/robotics-market")
            return {
                "contract_version": "project.structured_data.search.v1",
                "project_key": "demo_proj",
                "query": kwargs["query"],
                "total_matches": 1,
                "items": [
                    {
                        "dataset": "documents",
                        "id": 42,
                        "title": "Robotics market official report",
                        "source_uri": "https://example.gov/reports/robotics-market",
                        "summary": "Verified robotics market evidence.",
                    }
                ],
            }

        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [], structured_data_searcher=fake_searcher)
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="ingest.url_pool.status",
                        call_id="call-url-pool-status",
                        arguments={"url": "https://example.gov/reports/robotics-market"},
                    )
                ),
                CoreModelStep.final("已确认资料可用于写作。"),
            ]
        )

        out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
            AgentCoreRequest(
                message="检查刚才 URL-pool 采集是否完成",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        result = out.tool_results[0].structured_content
        self.assertEqual(out.tool_results[0].tool_name, "ingest.url_pool.status")
        self.assertTrue(result["verified"])
        self.assertFalse(result["pending"])
        self.assertEqual(result["task_id"], "url-pool-task-1")
        self.assertEqual(result["next_gate"], "verified_evidence_ready_for_writing")
        self.assertEqual(result["evidence_items"][0]["id"], 42)

    def test_ingest_url_pool_status_reads_completed_task_event_without_verified_record(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="候选来源任务完成但未验证",
            project_key="demo_proj",
            task_blueprints=[],
        )
        service.store.upsert_artifact(
            {
                "session_id": bundle["session"]["session_id"],
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
                            "dispatch_result": {"task_id": "url-pool-task-1", "status": "queued"},
                        }
                    ],
                },
                "content_text": "{}",
            }
        )
        service.store.upsert_artifact(
            {
                "session_id": bundle["session"]["session_id"],
                "name": "ingest.url_pool_task_events.json",
                "artifact_type": "url_pool_ingest_task_event_state",
                "mime_type": "application/json",
                "content_json": {
                    "contract_version": "ingest.url_pool.task_event.v1",
                    "events": [
                        {
                            "event_id": "url-pool-task-1-completed",
                            "url": "https://example.gov/reports/robotics-market",
                            "task_id": "url-pool-task-1",
                            "idempotency_key": "candidate-example-gov:url_pool",
                            "status": "completed",
                            "recorded_at": "2026-05-14T02:00:00Z",
                        }
                    ],
                },
                "content_text": "{}",
            }
        )

        registry = build_project_core_tool_registry(
            service=service,
            source_library_lister=lambda _: [],
            structured_data_searcher=lambda **_: {
                "contract_version": "project.structured_data.search.v1",
                "project_key": "demo_proj",
                "items": [],
                "total_matches": 0,
            },
        )
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="ingest.url_pool.status",
                        call_id="call-url-pool-status-completed-no-record",
                        arguments={"task_id": "url-pool-task-1"},
                    )
                ),
                CoreModelStep.final("任务完成但没有可验证资料。"),
            ]
        )

        out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
            AgentCoreRequest(
                message="检查 URL-pool 任务结果",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        result = out.tool_results[0].structured_content
        self.assertFalse(result["verified"])
        self.assertFalse(result["pending"])
        self.assertEqual(result["latest_task_event"]["status"], "completed")
        self.assertEqual(result["next_gate"], "ingest_completed_without_verified_project_record")

    def test_ingest_url_pool_status_reads_canceled_task_event_as_not_pending(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="候选来源任务取消",
            project_key="demo_proj",
            task_blueprints=[],
        )
        service.store.upsert_artifact(
            {
                "session_id": bundle["session"]["session_id"],
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
                            "dispatch_result": {"task_id": "url-pool-task-canceled", "status": "queued"},
                        }
                    ],
                },
                "content_text": "{}",
            }
        )
        service.store.upsert_artifact(
            {
                "session_id": bundle["session"]["session_id"],
                "name": "ingest.url_pool_task_events.json",
                "artifact_type": "url_pool_ingest_task_event_state",
                "mime_type": "application/json",
                "content_json": {
                    "contract_version": "ingest.url_pool.task_event.v1",
                    "events": [
                        {
                            "event_id": "url-pool-task-canceled",
                            "url": "https://example.gov/reports/robotics-market",
                            "task_id": "url-pool-task-canceled",
                            "idempotency_key": "candidate-example-gov:url_pool",
                            "status": "canceled",
                            "recorded_at": "2026-05-14T02:00:00Z",
                        }
                    ],
                },
                "content_text": "{}",
            }
        )

        registry = build_project_core_tool_registry(
            service=service,
            source_library_lister=lambda _: [],
            structured_data_searcher=lambda **_: {
                "contract_version": "project.structured_data.search.v1",
                "project_key": "demo_proj",
                "items": [],
                "total_matches": 0,
            },
        )
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="ingest.url_pool.status",
                        call_id="call-url-pool-status-canceled",
                        arguments={"task_id": "url-pool-task-canceled"},
                    )
                ),
                CoreModelStep.final("任务已取消。"),
            ]
        )

        out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
            AgentCoreRequest(
                message="检查 URL-pool 任务结果",
                session_id=bundle["session"]["session_id"],
                project_key="demo_proj",
            )
        )

        result = out.tool_results[0].structured_content
        self.assertFalse(result["verified"])
        self.assertFalse(result["pending"])
        self.assertEqual(result["latest_task_event"]["status"], "canceled")
        self.assertEqual(result["next_gate"], "url_pool_ingest_canceled_resume_or_retry")

    def test_url_pool_task_completion_helper_writes_session_artifacts(self):
        from app.services.tasks import _record_agent_url_pool_task_event

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="后台 URL-pool 完成事件",
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
                            "dispatch_result": {"task_id": "agent-url-pool-123", "status": "queued"},
                        }
                    ],
                },
            }
        )

        with patch("app.services.agent_sessions.service.get_agent_session_service", return_value=service):
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

        event_artifact = next(item for item in service.list_artifacts(session_id) if item["name"] == "ingest.url_pool_task_events.json")
        self.assertEqual(event_artifact["content_json"]["events"][0]["status"], "completed")
        submission_artifact = next(item for item in service.list_artifacts(session_id) if item["name"] == "ingest.url_pool_submissions.json")
        submission = submission_artifact["content_json"]["submissions"][0]
        self.assertEqual(submission["latest_task_status"], "completed")
        self.assertEqual(submission["task_events"][0]["task_id"], "agent-url-pool-123")
        self.assertTrue(any(event["event_type"] == "ingest.url_pool.task.completed" for event in service.list_events(session_id)))

    def test_source_discovery_to_investigation_to_writing_resume_chain(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="机器人调查写作",
            project_key="demo_proj",
            task_blueprints=[],
        )

        def source_lister(project_key):
            self.assertEqual(project_key, "demo_proj")
            return [{"item_key": "robot.baseline", "name": "Robot Baseline", "query_terms": ["机器人", "商业化"]}]

        registry = build_project_core_tool_registry(service=service, source_library_lister=source_lister)
        saved_document = {
            "id": 77,
            "project_key": "demo_proj",
            "title": "Robot Brief",
            "body_md": "# Robot Brief\n\n候选来源显示机器人商业化正在加速。",
            "status": "draft",
            "version": 1,
            "etag": "etag-77",
            "metadata_json": {},
        }
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="source.discovery.plan",
                        call_id="call-discovery",
                        arguments={
                            "topic": "机器人商业化",
                            "query_terms": ["机器人", "商业化"],
                            "candidate_urls": ["https://example.com/robot-market"],
                            "domains": ["example.com"],
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="agent_investigation.leads.append",
                        call_id="call-leads-from-discovery",
                        arguments={
                            "artifact_name": "robot-investigation.leads.json",
                            "goal": "机器人商业化调查",
                            "idempotency_key": "robot-discovery-round-1",
                            "clue_nodes": [
                                {"id": "robot_market", "label": "机器人商业化"},
                                {"id": "candidate_source", "label": "候选来源"},
                                {"id": "writing_claim", "label": "工作台待写论点"},
                            ],
                            "clue_edges": [
                                {"source": "robot_market", "target": "candidate_source", "relation": "evidenced_by"},
                                {"source": "candidate_source", "target": "writing_claim", "relation": "supports"},
                            ],
                            "followed_leads": [{"url": "https://example.com/robot-market", "source": "source.discovery.plan"}],
                            "pending_questions": ["需要补充官方或监管来源"],
                            "citations": [{"source_id": "candidate:example.com", "quote": "robot-market"}],
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="agent_investigation.trace.read",
                        call_id="call-trace-from-leads",
                        arguments={
                            "artifact_name": "robot-investigation.leads.json",
                            "focus_node_id": "robot_market",
                            "max_hops": 2,
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="writing.document.insert_paragraph",
                        call_id="call-writing-from-leads",
                        arguments={
                            "project_key": "demo_proj",
                            "title": "Robot Brief",
                            "operation": "append",
                            "content_md": "候选来源显示机器人商业化正在加速。",
                            "source_refs": ["https://example.com/robot-market"],
                            "provenance": {"from_tool_call": "call-leads-from-discovery"},
                        },
                    )
                ),
                CoreModelStep.tools(CoreToolCall(tool_name="agent_session.resume_bundle", arguments={"limit": 20}, call_id="call-resume-after-writing")),
                CoreModelStep.final("已完成候选来源规划、线索入库和写作工作台草稿更新。"),
            ]
        )

        with patch("app.services.agent_core.project_tools.bind_project", side_effect=_noop_project_context):
            with patch("app.services.agent_core.project_tools.create_document", return_value=saved_document) as mocked_create:
                out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
                    AgentCoreRequest(
                        message="围绕机器人商业化做一轮候选来源调查并写入工作台",
                        session_id=bundle["session"]["session_id"],
                        project_key="demo_proj",
                        approved_call_ids=("call-writing-from-leads",),
                    )
                )

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertEqual(
            [result.tool_name for result in out.tool_results],
            [
                "source.discovery.plan",
                "agent_investigation.leads.append",
                "agent_investigation.trace.read",
                "writing.document.insert_paragraph",
                "agent_session.resume_bundle",
            ],
        )
        discovery = out.tool_results[0].structured_content
        self.assertFalse(discovery["quality_gates"]["network_fetch_performed"])
        self.assertTrue(discovery["quality_gates"]["requires_review_before_ingest"])
        self.assertEqual(discovery["candidate_source_items"][0]["item_key"], "robot.baseline")

        leads_artifact = next(item for item in service.list_artifacts(bundle["session"]["session_id"]) if item["name"] == "robot-investigation.leads.json")
        self.assertEqual(leads_artifact["content_json"]["followed_leads"][0]["url"], "https://example.com/robot-market")
        self.assertEqual(out.tool_results[1].structured_content["counts"]["followed_leads"], 1)
        trace = out.tool_results[2].structured_content
        self.assertEqual(trace["focus_node_id"], "robot_market")
        self.assertEqual({item["id"] for item in trace["nodes"]}, {"robot_market", "candidate_source", "writing_claim"})
        self.assertEqual({item["relation"] for item in trace["edges"]}, {"evidenced_by", "supports"})

        mocked_create.assert_called_once()
        create_kwargs = mocked_create.call_args.kwargs
        self.assertEqual(create_kwargs["project_key"], "demo_proj")
        self.assertEqual(create_kwargs["title"], "Robot Brief")
        self.assertIn("机器人商业化", create_kwargs["body_md"])
        self.assertEqual(create_kwargs["metadata_json"]["last_agent_update"]["source_refs"], ["https://example.com/robot-market"])
        self.assertEqual(create_kwargs["metadata_json"]["last_agent_update"]["provenance"]["from_tool_call"], "call-leads-from-discovery")

        resume_artifacts = out.tool_results[4].structured_content["recent_artifacts"]
        self.assertIn("robot-investigation.leads.json", {item["name"] for item in resume_artifacts})
        self.assertEqual(provider.calls[4]["transcript"][-1]["tool_result"]["tool_name"], "writing.document.insert_paragraph")

    def test_model_owned_loop_internal_first_external_discovery_stage_and_resume(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="机器人长程调查写作",
            project_key="demo_proj",
            task_blueprints=[],
        )

        def source_lister(project_key):
            self.assertEqual(project_key, "demo_proj")
            return [{"item_key": "robot.baseline", "name": "Robot Baseline", "query_terms": ["机器人", "商业化"]}]

        def structured_searcher(**kwargs):
            return {
                "contract_version": "project.structured_data.search.v1",
                "project_key": kwargs["project_key"],
                "query": kwargs.get("query"),
                "inventory": [{"dataset": "documents", "label": "documents", "sample_count": 1, "total_rows": 12}],
                "dataset_counts": {"documents": 1},
                "dataset_total_rows": {"documents": 12},
                "total_stored_rows": 12,
                "total_matches": 1,
                "items": [{"dataset": "documents", "record_id": "doc-robot", "title": "Robot local note", "summary": "内部资料显示机器人商业化加速，但缺官方来源。"}],
                "dataset_results": [],
                "errors": [],
            }

        saved_document = {
            "id": 88,
            "project_key": "demo_proj",
            "title": "Robot Long Brief",
            "body_md": "# Robot Long Brief\n\n内部资料与候选来源共同显示机器人商业化加速。",
            "status": "draft",
            "version": 1,
            "etag": "etag-88",
            "metadata_json": {},
        }
        registry = build_project_core_tool_registry(
            service=service,
            source_library_lister=source_lister,
            structured_data_searcher=structured_searcher,
        )
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="agent_task.plan.append",
                        call_id="call-plan-loop",
                        arguments={
                            "idempotency_key": "robot-loop-plan",
                            "tasks": [
                                {"task_id": "task-internal", "subject": "内部证据检索", "phase": "research"},
                                {"task_id": "task-external", "subject": "外部缺口补证", "phase": "research", "blocked_by_refs": ["prev"]},
                                {"task_id": "task-draft", "subject": "写作工作台输出", "phase": "implementation", "blocked_by_refs": ["prev"]},
                            ],
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="project.context.bundle",
                        call_id="call-internal-context",
                        arguments={"query": "机器人商业化", "limit": 8},
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="agent_long_task.stage.update",
                        call_id="call-stage-internal-loop",
                        arguments={
                            "task_id": "task-internal",
                            "stage": "internal_evidence",
                            "stage_status": "completed",
                            "summary": "已完成内部资料检索，仍缺官方或监管来源。",
                            "idempotency_key": "robot-stage-internal",
                            "evidence_refs": ["project.context.bundle", "documents:doc-robot"],
                            "gap_list": ["缺官方披露", "缺监管口径"],
                            "next_actions": ["规划外部发现"],
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="source.discovery.plan",
                        call_id="call-external-discovery-loop",
                        arguments={
                            "topic": "机器人商业化官方来源",
                            "query_terms": ["机器人 商业化 官方 披露"],
                            "candidate_urls": ["https://example.com/robot-official"],
                            "domains": ["example.com"],
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="agent_long_task.stage.update",
                        call_id="call-stage-external-loop",
                        arguments={
                            "task_id": "task-external",
                            "stage": "external_discovery",
                            "stage_status": "completed",
                            "summary": "已规划候选外部来源，尚未执行 ingest。",
                            "idempotency_key": "robot-stage-external",
                            "external_discovery_plan": ["https://example.com/robot-official"],
                            "next_actions": ["保存线索并更新草稿"],
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="ingest.source_library.run",
                        call_id="call-source-intake-loop",
                        arguments={
                            "project_key": "demo_proj",
                            "items": ["robot.baseline"],
                            "max_items": 1,
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="agent_long_task.stage.update",
                        call_id="call-stage-intake-loop",
                        arguments={
                            "task_id": "task-external",
                            "stage": "source_intake",
                            "stage_status": "completed",
                            "summary": "已提交受治理的来源库采集任务。",
                            "idempotency_key": "robot-stage-intake",
                            "source_intake": [{"item_key": "robot.baseline", "task_id": "task-robot-baseline"}],
                            "next_actions": ["保存线索并更新草稿"],
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="agent_investigation.leads.append",
                        call_id="call-leads-loop",
                        arguments={
                            "artifact_name": "robot-loop.leads.json",
                            "goal": "机器人商业化长程调查",
                            "idempotency_key": "robot-loop-leads",
                            "clue_nodes": [
                                {"id": "internal_note", "label": "内部机器人资料"},
                                {"id": "official_gap", "label": "官方来源缺口"},
                                {"id": "draft_claim", "label": "写作论点"},
                            ],
                            "clue_edges": [
                                {"source": "internal_note", "target": "official_gap", "relation": "missing_evidence"},
                                {"source": "official_gap", "target": "draft_claim", "relation": "qualifies"},
                            ],
                            "followed_leads": [{"url": "https://example.com/robot-official", "source": "source.discovery.plan"}],
                            "pending_questions": ["候选官方来源是否可执行采集"],
                            "citations": [{"source_id": "documents:doc-robot", "quote": "机器人商业化加速"}],
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="writing.document.insert_paragraph",
                        call_id="call-draft-loop",
                        arguments={
                            "project_key": "demo_proj",
                            "title": "Robot Long Brief",
                            "operation": "append",
                            "content_md": "内部资料显示机器人商业化加速，但仍需以官方来源补强结论。",
                            "source_refs": ["documents:doc-robot", "https://example.com/robot-official"],
                            "provenance": {"stage": "draft_output"},
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="agent_long_task.stage.update",
                        call_id="call-stage-draft-loop",
                        arguments={
                            "task_id": "task-draft",
                            "stage": "draft_output",
                            "stage_status": "completed",
                            "summary": "已把内部证据和外部候选来源写入草稿。",
                            "idempotency_key": "robot-stage-draft",
                            "draft_refs": [{"doc_id": 88, "title": "Robot Long Brief"}],
                            "next_actions": ["校验来源库采集产物"],
                        },
                    )
                ),
                CoreModelStep.tools(CoreToolCall(tool_name="agent_session.resume_bundle", call_id="call-resume-loop", arguments={"limit": 20})),
                CoreModelStep.final("已完成内部优先检索、外部发现规划、线索保存、草稿输出，并保存可恢复阶段状态。"),
            ]
        )

        with patch("app.services.agent_core.project_tools.bind_project", side_effect=_noop_project_context):
            with patch("app.services.agent_core.project_tools.create_document", return_value=saved_document):
                with patch(
                    "app.services.agent_core.project_tools.invoke_skill",
                    return_value={"result": {"task_id": "task-robot-baseline"}},
                ):
                    out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
                        AgentCoreRequest(
                            message="执行机器人长程调查写作，先看内部资料，缺口再找外部来源并写入工作台",
                            session_id=bundle["session"]["session_id"],
                            project_key="demo_proj",
                            approved_call_ids=("call-draft-loop",),
                            max_iterations=14,
                        )
                    )

        self.assertEqual(out.stop_reason, "final_answer")
        self.assertEqual(
            [result.tool_name for result in out.tool_results],
            [
                "agent_task.plan.append",
                "project.context.bundle",
                "agent_long_task.stage.update",
                "source.discovery.plan",
                "agent_long_task.stage.update",
                "ingest.source_library.run",
                "agent_long_task.stage.update",
                "agent_investigation.leads.append",
                "writing.document.insert_paragraph",
                "agent_long_task.stage.update",
                "agent_session.resume_bundle",
            ],
        )
        context = out.tool_results[1].structured_content["result"]
        self.assertEqual(context["material_categories"]["internal_existing"]["stored_rows"], 12)
        self.assertEqual(context["source_catalog_note"], "source-library items are collection/data-source entrypoints, not already ingested project materials.")
        discovery = out.tool_results[3].structured_content
        self.assertFalse(discovery["quality_gates"]["network_fetch_performed"])
        self.assertTrue(discovery["quality_gates"]["requires_review_before_ingest"])
        ingest = out.tool_results[5].structured_content
        self.assertEqual(ingest["items"][0]["item_key"], "robot.baseline")
        self.assertEqual(ingest["task_ids"], ["task-robot-baseline"])
        intake_stage = out.tool_results[6].structured_content["state"]
        self.assertEqual(intake_stage["current_stage"], "clue_trace")
        source_intake = next(item for item in intake_stage["stage_summaries"] if item["stage"] == "source_intake")
        self.assertEqual(source_intake["counts"]["source_intake"], 1)
        final_stage = out.tool_results[9].structured_content["state"]
        self.assertEqual(final_stage["current_stage"], "verification")
        self.assertIn("draft_output", final_stage["completed_stages"])
        draft_stage = next(item for item in final_stage["stage_summaries"] if item["stage"] == "draft_output")
        self.assertEqual(draft_stage["counts"]["draft_refs"], 1)
        resume = out.tool_results[10].structured_content
        self.assertEqual(resume["counts"]["long_task_states"], 1)
        self.assertEqual(resume["long_task_states"][0]["current_stage"], "verification")
        self.assertIn("robot-loop.leads.json", {item["name"] for item in resume["recent_artifacts"]})
        self.assertEqual(provider.calls[3]["transcript"][-1]["tool_result"]["tool_name"], "agent_long_task.stage.update")
        self.assertEqual(provider.calls[3]["transcript"][-2]["tool_result"]["tool_name"], "project.context.bundle")

    def test_writing_insert_requires_version_lock_then_can_write_latest_after_approval(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="写作",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        base_document = {
            "id": 7,
            "project_key": "demo_proj",
            "title": "Research Draft",
            "body_md": "# 背景\n\n已有段落。",
            "status": "draft",
            "version": 2,
            "etag": "etag-2",
            "updated_at": "2026-05-11T00:00:00Z",
            "metadata_json": {},
        }

        without_lock = CoreToolCall(
            tool_name="writing.document.insert_paragraph",
            call_id="call-write-missing-lock",
            arguments={"doc_id": 7, "content_md": "新增段落。", "operation": "append"},
        )
        with patch("app.services.agent_core.project_tools.bind_project", side_effect=_noop_project_context):
            with patch("app.services.agent_core.project_tools.get_document", return_value=base_document):
                with patch("app.services.agent_core.project_tools.save_document_with_conflict") as mocked_save:
                    out = AgentCore(
                        provider=FakeCoreProvider([CoreModelStep.tools(without_lock), CoreModelStep.final("done")]),
                        tool_registry=registry,
                        tool_specs=registry.list_specs(),
                    ).run(
                        AgentCoreRequest(
                            message="插入一段",
                            session_id=bundle["session"]["session_id"],
                            project_key="demo_proj",
                            approved_call_ids=("call-write-missing-lock",),
                        )
                    )

        self.assertEqual(out.tool_results[0].status, "failed")
        self.assertEqual(out.tool_results[0].error["code"], "version_lock_required")
        mocked_save.assert_not_called()

        saved_document = {**base_document, "version": 3, "etag": "etag-3", "body_md": "# 背景\n\n已有段落。\n\n新增段落。\n"}
        with_lock = CoreToolCall(
            tool_name="writing.document.insert_paragraph",
            call_id="call-write-latest",
            arguments={"doc_id": 7, "content_md": "新增段落。", "operation": "append", "allow_latest": True},
        )
        with patch("app.services.agent_core.project_tools.bind_project", side_effect=_noop_project_context):
            with patch("app.services.agent_core.project_tools.get_document", return_value=base_document):
                with patch("app.services.agent_core.project_tools.save_document_with_conflict", return_value=saved_document) as mocked_save:
                    out = AgentCore(
                        provider=FakeCoreProvider([CoreModelStep.tools(with_lock), CoreModelStep.final("已插入。")]),
                        tool_registry=registry,
                        tool_specs=registry.list_specs(),
                    ).run(
                        AgentCoreRequest(
                            message="插入一段",
                            session_id=bundle["session"]["session_id"],
                            project_key="demo_proj",
                            approved_call_ids=("call-write-latest",),
                        )
                    )

        self.assertEqual(out.tool_results[0].status, "completed")
        self.assertEqual(out.tool_results[0].structured_content["doc_id"], 7)
        mocked_save.assert_called_once()
        self.assertEqual(mocked_save.call_args.kwargs["base_version"], 2)
        self.assertEqual(mocked_save.call_args.kwargs["if_match"], "etag-2")
        metadata_json = mocked_save.call_args.kwargs["metadata_json"]
        self.assertEqual(metadata_json["agent_update_count"], 1)
        self.assertEqual(metadata_json["last_agent_update"]["call_id"], "call-write-latest")
        self.assertEqual(metadata_json["last_agent_update"]["operation"], "append")
        self.assertEqual(metadata_json["last_agent_update"]["actor"], "agent_core")
        self.assertEqual(metadata_json["last_agent_update"]["locator"]["anchor_text"], "新增段落。")
        self.assertEqual(out.tool_results[0].structured_content["agent_update"]["call_id"], "call-write-latest")

    def test_writing_insert_can_replace_selected_range_with_locator_metadata(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="选区改写",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        body = "# 标题\n\n第一段要改。\n\n第二段。"
        range_start = body.index("第一段要改。")
        range_end = range_start + len("第一段要改。")
        base_document = {
            "id": 7,
            "project_key": "demo_proj",
            "title": "Research Draft",
            "body_md": body,
            "status": "draft",
            "version": 2,
            "etag": "etag-2",
            "metadata_json": {},
        }
        saved_document = {
            **base_document,
            "version": 3,
            "etag": "etag-3",
            "body_md": "# 标题\n\n替换后的第一段。\n\n第二段。\n",
        }
        tool_call = CoreToolCall(
            tool_name="writing.document.insert_paragraph",
            call_id="call-write-range",
            arguments={
                "doc_id": 7,
                "operation": "replace_range",
                "range_start": range_start,
                "range_end": range_end,
                "selection_snapshot": {"selected_text": "第一段要改。", "start": range_start, "end": range_end, "line": 3},
                "content_md": "替换后的第一段。",
                "allow_latest": True,
            },
        )

        with patch("app.services.agent_core.project_tools.bind_project", side_effect=_noop_project_context):
            with patch("app.services.agent_core.project_tools.get_document", return_value=base_document):
                with patch("app.services.agent_core.project_tools.save_document_with_conflict", return_value=saved_document) as mocked_save:
                    out = AgentCore(
                        provider=FakeCoreProvider([CoreModelStep.tools(tool_call), CoreModelStep.final("已替换选区。")]),
                        tool_registry=registry,
                        tool_specs=registry.list_specs(),
                    ).run(
                        AgentCoreRequest(
                            message="把选中的这一段改写",
                            session_id=bundle["session"]["session_id"],
                            project_key="demo_proj",
                            approved_call_ids=("call-write-range",),
                        )
                    )

        self.assertEqual(out.tool_results[0].status, "completed")
        self.assertEqual(mocked_save.call_args.kwargs["body_md"], saved_document["body_md"])
        metadata_json = mocked_save.call_args.kwargs["metadata_json"]
        locator = metadata_json["last_agent_update"]["locator"]
        self.assertEqual(locator["range_start"], range_start)
        self.assertEqual(locator["range_end"], range_end)
        self.assertEqual(locator["anchor_text"], "第一段要改。")
        self.assertEqual(locator["selection_snapshot"]["selected_text"], "第一段要改。")
        self.assertEqual(metadata_json["last_agent_update"]["replaced_text"], "第一段要改。")
        self.assertFalse(metadata_json["last_agent_update"]["replaced_text_truncated"])
        self.assertEqual(metadata_json["last_agent_update"]["provenance"]["selection_snapshot"]["line"], 3)

    def test_writing_insert_can_insert_at_cursor_offset(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="光标续写",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        body = "# 标题\n\n第一段。\n\n第二段。"
        cursor_offset = body.index("第二段。")
        base_document = {
            "id": 8,
            "project_key": "demo_proj",
            "title": "Research Draft",
            "body_md": body,
            "status": "draft",
            "version": 4,
            "etag": "etag-4",
            "metadata_json": {},
        }
        saved_document = {
            **base_document,
            "version": 5,
            "etag": "etag-5",
            "body_md": "# 标题\n\n第一段。\n\n插入段。\n\n第二段。\n",
        }
        tool_call = CoreToolCall(
            tool_name="writing.document.insert_paragraph",
            call_id="call-write-cursor",
            arguments={
                "doc_id": 8,
                "operation": "insert_at_offset",
                "cursor_offset": cursor_offset,
                "content_md": "插入段。",
                "allow_latest": True,
            },
        )

        with patch("app.services.agent_core.project_tools.bind_project", side_effect=_noop_project_context):
            with patch("app.services.agent_core.project_tools.get_document", return_value=base_document):
                with patch("app.services.agent_core.project_tools.save_document_with_conflict", return_value=saved_document) as mocked_save:
                    out = AgentCore(
                        provider=FakeCoreProvider([CoreModelStep.tools(tool_call), CoreModelStep.final("已插入。")]),
                        tool_registry=registry,
                        tool_specs=registry.list_specs(),
                    ).run(
                        AgentCoreRequest(
                            message="在光标处补一段",
                            session_id=bundle["session"]["session_id"],
                            project_key="demo_proj",
                            approved_call_ids=("call-write-cursor",),
                        )
                    )

        self.assertEqual(out.tool_results[0].status, "completed")
        self.assertEqual(mocked_save.call_args.kwargs["body_md"], saved_document["body_md"])
        locator = mocked_save.call_args.kwargs["metadata_json"]["last_agent_update"]["locator"]
        self.assertEqual(locator["cursor_offset"], cursor_offset)

    def test_writing_insert_rejects_invalid_range(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="选区改写",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        base_document = {
            "id": 7,
            "project_key": "demo_proj",
            "title": "Research Draft",
            "body_md": "# 标题\n\n第一段。",
            "status": "draft",
            "version": 2,
            "etag": "etag-2",
            "metadata_json": {},
        }
        tool_call = CoreToolCall(
            tool_name="writing.document.insert_paragraph",
            call_id="call-write-bad-range",
            arguments={
                "doc_id": 7,
                "operation": "replace_range",
                "range_start": 3,
                "range_end": 999,
                "content_md": "替换。",
                "allow_latest": True,
            },
        )

        with patch("app.services.agent_core.project_tools.bind_project", side_effect=_noop_project_context):
            with patch("app.services.agent_core.project_tools.get_document", return_value=base_document):
                with patch("app.services.agent_core.project_tools.save_document_with_conflict") as mocked_save:
                    out = AgentCore(
                        provider=FakeCoreProvider([CoreModelStep.tools(tool_call), CoreModelStep.final("done")]),
                        tool_registry=registry,
                        tool_specs=registry.list_specs(),
                    ).run(
                        AgentCoreRequest(
                            message="替换这个选区",
                            session_id=bundle["session"]["session_id"],
                            project_key="demo_proj",
                            approved_call_ids=("call-write-bad-range",),
                        )
                    )

        self.assertEqual(out.tool_results[0].status, "failed")
        self.assertEqual(out.tool_results[0].error["code"], "invalid_writing_operation")
        self.assertIn("range_end", out.tool_results[0].error["message"])
        mocked_save.assert_not_called()

    def test_writing_document_create_registers_formal_workbench_document(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="建立写作文档",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        saved_document = {
            "id": 31,
            "project_key": "demo_proj",
            "title": "机器人公司分析",
            "body_md": "# 机器人公司分析\n\n初稿正文。",
            "status": "draft",
            "version": 1,
            "etag": "etag-31",
            "metadata_json": {
                "created_by": "agent_core",
                "agent_core_call_id": "call-create-doc",
            },
        }
        create_call = CoreToolCall(
            tool_name="writing.document.create",
            call_id="call-create-doc",
            arguments={
                "title": "机器人公司分析",
                "body_md": "# 机器人公司分析\n\n初稿正文。",
                "source_refs": ["artifact-dfe1ca3c7dce43ab"],
                "provenance": {"artifact_id": "artifact-dfe1ca3c7dce43ab"},
            },
        )
        with patch("app.services.agent_core.project_tools.bind_project", side_effect=_noop_project_context):
            with patch("app.services.agent_core.project_tools.create_document", return_value=saved_document) as mocked_create:
                out = AgentCore(
                    provider=FakeCoreProvider([CoreModelStep.tools(create_call), CoreModelStep.final("已建立写作文档。")]),
                    tool_registry=registry,
                    tool_specs=registry.list_specs(),
                ).run(
                    AgentCoreRequest(
                        message="把这个报告建立成写作文档",
                        session_id=bundle["session"]["session_id"],
                        project_key="demo_proj",
                        approved_call_ids=("call-create-doc",),
                    )
                )

        self.assertEqual(out.tool_results[0].status, "completed")
        self.assertEqual(out.tool_results[0].tool_name, "writing.document.create")
        self.assertEqual(out.tool_results[0].structured_content["doc_id"], 31)
        self.assertEqual(out.tool_results[0].structured_content["document"]["title"], "机器人公司分析")
        mocked_create.assert_called_once()
        self.assertEqual(mocked_create.call_args.kwargs["project_key"], "demo_proj")
        self.assertEqual(mocked_create.call_args.kwargs["title"], "机器人公司分析")
        self.assertEqual(mocked_create.call_args.kwargs["body_md"], "# 机器人公司分析\n\n初稿正文。")
        self.assertEqual(mocked_create.call_args.kwargs["updated_by_user_id"], "agent_core")
        metadata_json = mocked_create.call_args.kwargs["metadata_json"]
        self.assertEqual(metadata_json["created_by"], "agent_core")
        self.assertEqual(metadata_json["agent_core_call_id"], "call-create-doc")
        self.assertEqual(metadata_json["source_refs"], ["artifact-dfe1ca3c7dce43ab"])
        self.assertEqual(metadata_json["agent_document_contract"], "writing.document.create.v1")

    def test_writing_document_citations_upsert_attaches_material_cards(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="加入资料卡引用",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        existing = [
            {
                "id": 1,
                "doc_id": 31,
                "project_key": "demo_proj",
                "card_id": "record:94",
                "source_title": "记录 94",
                "quote_text": "旧引用",
            }
        ]
        saved = [
            existing[0],
            {
                "id": 2,
                "doc_id": 31,
                "project_key": "demo_proj",
                "card_id": "card-robot-market",
                "source_uri": "https://example.com/robot-market",
                "source_title": "机器人市场资料卡",
                "quote_text": "机器人市场加速。",
                "position_anchor": "selection:abc",
            },
        ]
        citation_call = CoreToolCall(
            tool_name="writing.document.citations.upsert",
            call_id="call-citations",
            arguments={
                "project_key": "demo_proj",
                "doc_id": 31,
                "mode": "append",
                "position_anchor": "selection:abc",
                "material_cards": [
                    {
                        "id": "card-robot-market",
                        "title": "机器人市场资料卡",
                        "url": "https://example.com/robot-market",
                        "snippet": "机器人市场加速。",
                    },
                    {"id": "record:94", "title": "记录 94", "snippet": "重复引用应被去重。"},
                ],
                "source_refs": ["record:94"],
                "provenance": {"from_tool_call": "call-read"},
            },
        )
        with patch("app.services.agent_core.project_tools.bind_project", side_effect=_noop_project_context):
            with patch("app.services.agent_core.project_tools.list_citations", return_value=existing) as mocked_list:
                with patch("app.services.agent_core.project_tools.upsert_citations", return_value=saved) as mocked_upsert:
                    out = AgentCore(
                        provider=FakeCoreProvider([CoreModelStep.tools(citation_call), CoreModelStep.final("已加入引用。")]),
                        tool_registry=registry,
                        tool_specs=registry.list_specs(),
                    ).run(
                        AgentCoreRequest(
                            message="把这张资料卡加入写作工作台引用框",
                            session_id=bundle["session"]["session_id"],
                            project_key="demo_proj",
                            approved_call_ids=("call-citations",),
                        )
                    )

        self.assertEqual(out.tool_results[0].status, "completed")
        self.assertEqual(out.tool_results[0].tool_name, "writing.document.citations.upsert")
        self.assertEqual(out.tool_results[0].structured_content["doc_id"], 31)
        self.assertEqual(out.tool_results[0].structured_content["added_count"], 1)
        self.assertEqual(out.tool_results[0].structured_content["total_count"], 2)
        mocked_list.assert_called_once_with(doc_id=31, project_key="demo_proj")
        mocked_upsert.assert_called_once()
        saved_payload = mocked_upsert.call_args.kwargs["citations"]
        self.assertEqual(len(saved_payload), 2)
        self.assertEqual(saved_payload[1]["card_id"], "card-robot-market")
        self.assertEqual(saved_payload[1]["source_uri"], "https://example.com/robot-market")
        self.assertEqual(saved_payload[1]["position_anchor"], "selection:abc")
        self.assertEqual(saved_payload[1]["metadata_json"]["provenance"]["from_tool_call"], "call-read")

    def test_compare_session_replay_creates_workbench_document_from_existing_draft(self):
        class ProjectSearchFirstChat:
            def invoke(self, prompt):
                return {
                    "content": json.dumps(
                        {
                            "type": "tool_calls",
                            "tool_calls": [
                                {
                                    "tool_name": "project.structured_data.search",
                                    "arguments": {"query": "新建稿件并把内容贴进去"},
                                    "reason": "incorrectly tries project search first",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
                }

        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="你帮我找一点关于机器人有意义的信息",
            project_key="demo_proj_compare_0303_121137",
            task_blueprints=[],
        )
        session_id = bundle["session"]["session_id"]
        service.create_message(
            session_id,
            role="assistant",
            actor="agent_core",
            content="# 机器人：从自动执行工具到具身智能载体的演进\n\n记录 94 提到人形机器人市场加速。\n\n## 引用框\n- 记录 94：证券时报 IDC 报告",
            metadata={"turn_id": "turn-existing-draft"},
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        saved_document = {
            "id": 47,
            "project_key": "demo_proj_compare_0303_121137",
            "title": "机器人：从自动执行工具到具身智能载体的演进",
            "body_md": "# 机器人：从自动执行工具到具身智能载体的演进\n\n记录 94 提到人形机器人市场加速。",
            "status": "draft",
            "version": 1,
            "etag": "etag-47",
            "metadata_json": {},
        }

        with patch("app.services.agent_core.project_tools.bind_project", side_effect=_noop_project_context):
            with patch("app.services.agent_core.project_tools.create_document", return_value=saved_document) as mocked_create:
                out = AgentCore(
                    provider=JsonCoreProvider(chat_model=ProjectSearchFirstChat()),
                    tool_registry=registry,
                    tool_specs=registry.list_specs(),
                ).run(
                    AgentCoreRequest(
                        message="新建稿件并把内容贴进去",
                        session_id=session_id,
                        project_key="demo_proj_compare_0303_121137",
                        turn_id="turn-compare-replay",
                        context={
                            "prior_transcript": [
                                {
                                    "role": "assistant",
                                    "content": "# 机器人：从自动执行工具到具身智能载体的演进\n\n记录 94 提到人形机器人市场加速。\n\n## 引用框\n- 记录 94：证券时报 IDC 报告",
                                }
                            ]
                        },
                    )
                )

        self.assertEqual([result.tool_name for result in out.tool_results], ["writing.document.create"])
        self.assertEqual(out.tool_results[0].structured_content["doc_id"], 47)
        mocked_create.assert_called_once()
        self.assertEqual(mocked_create.call_args.kwargs["project_key"], "demo_proj_compare_0303_121137")
        self.assertIn("记录 94", mocked_create.call_args.kwargs["body_md"])
        self.assertIn("record:94", mocked_create.call_args.kwargs["metadata_json"]["source_refs"])
        self.assertIn("已在写作工作台新建文档", out.final_answer)
        self.assertIn("ID: 47", out.final_answer)

    def test_writing_read_returns_block_anchors_for_agent_targeting(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="写作定位",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        document = {
            "id": 7,
            "project_key": "demo_proj",
            "title": "Draft",
            "body_md": "# 背景\n\n第一段。\n\n## 证据\n\n第二段。",
            "status": "draft",
            "version": 2,
            "etag": "etag-2",
            "metadata_json": {},
        }
        with patch("app.services.agent_core.project_tools.bind_project", side_effect=_noop_project_context):
            with patch("app.services.agent_core.project_tools.get_document", return_value=document):
                out = AgentCore(
                    provider=FakeCoreProvider(
                        [
                            CoreModelStep.tools(CoreToolCall(tool_name="writing.document.read", call_id="call-read", arguments={"doc_id": 7})),
                            CoreModelStep.final("已读取。"),
                        ]
                    ),
                    tool_registry=registry,
                    tool_specs=registry.list_specs(),
                ).run(
                    AgentCoreRequest(
                        message="读取文稿",
                        session_id=bundle["session"]["session_id"],
                        project_key="demo_proj",
                    )
                )

        anchors = out.tool_results[0].structured_content["document"]["block_anchors"]
        self.assertEqual(anchors[0]["kind"], "heading")
        self.assertEqual(anchors[0]["line_start"], 1)
        self.assertEqual(anchors[1]["preview"], "第一段。")

    def test_writing_insert_is_idempotent_for_same_selection_and_content(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="写作幂等",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        document = {
            "id": 7,
            "project_key": "demo_proj",
            "title": "Draft",
            "body_md": "# 背景\n\n第一段。",
            "status": "draft",
            "version": 2,
            "etag": "etag-2",
            "metadata_json": {},
        }
        save_calls: list[dict] = []

        def get_document(*, doc_id: int, project_key: str):
            self.assertEqual(doc_id, 7)
            self.assertEqual(project_key, "demo_proj")
            return dict(document)

        def save_document_with_conflict(**kwargs):
            save_calls.append(dict(kwargs))
            document["body_md"] = kwargs["body_md"]
            document["version"] = int(document["version"]) + 1
            document["etag"] = f"etag-{document['version']}"
            document["metadata_json"] = dict(kwargs["metadata_json"] or {})
            return dict(document)

        tool_call = CoreToolCall(
            tool_name="writing.document.insert_paragraph",
            call_id="call-write-once",
            arguments={
                "doc_id": 7,
                "operation": "append",
                "content_md": "Agent 写入段落。",
                "allow_latest": True,
                "idempotency_key": "write-key-1",
            },
        )
        with (
            patch("app.services.agent_core.project_tools.bind_project", side_effect=_noop_project_context),
            patch("app.services.agent_core.project_tools.get_document", side_effect=get_document),
            patch("app.services.agent_core.project_tools.save_document_with_conflict", side_effect=save_document_with_conflict),
        ):
            first = AgentCore(
                provider=FakeCoreProvider([CoreModelStep.tools(tool_call), CoreModelStep.final("已写入。")]),
                tool_registry=registry,
                tool_specs=registry.list_specs(),
            ).run(AgentCoreRequest(message="写入一次", session_id=bundle["session"]["session_id"], project_key="demo_proj"))
            second = AgentCore(
                provider=FakeCoreProvider([CoreModelStep.tools(tool_call), CoreModelStep.final("已写入。")]),
                tool_registry=registry,
                tool_specs=registry.list_specs(),
            ).run(AgentCoreRequest(message="重试同一次写入", session_id=bundle["session"]["session_id"], project_key="demo_proj"))

        self.assertEqual(len(save_calls), 1)
        self.assertEqual(document["body_md"].count("Agent 写入段落。"), 1)
        self.assertFalse(first.tool_results[0].structured_content.get("replayed", False))
        self.assertTrue(second.tool_results[0].structured_content["replayed"])
        self.assertEqual(second.tool_results[0].structured_content["diff"]["added_lines"], 0)

    def test_json_provider_guardrail_calls_governed_source_library_tool(self):
        class InvalidJsonChat:
            def invoke(self, prompt):
                return {"content": "我无法直接运行来源库。"}

        provider = JsonCoreProvider(chat_model=InvalidJsonChat())
        request = AgentCoreRequest(
            message="用来源库 market.general.baseline 补一轮证据",
            session_id="as-json",
            project_key="demo_proj",
            turn_id="turn-json",
        )
        tools = [
            CoreToolSpec(
                name="ingest.source_library.run",
                description_for_model="Run source-library collection.",
                risk="write_external",
                permission="ask",
            )
        ]

        step = provider.next_step(request=request, tools=tools, transcript=[{"role": "user", "content": request.message}], remaining_budget={})

        self.assertEqual(step.step_type, "tool_calls")
        self.assertEqual(step.tool_calls[0].tool_name, "ingest.source_library.run")
        self.assertEqual(step.tool_calls[0].arguments["items"], ["market.general.baseline"])
        self.assertEqual(step.tool_calls[0].arguments["project_key"], "demo_proj")
        self.assertEqual(step.metadata["protocol_guardrail"], "tool_required_after_invalid_json")


if __name__ == "__main__":
    unittest.main()
