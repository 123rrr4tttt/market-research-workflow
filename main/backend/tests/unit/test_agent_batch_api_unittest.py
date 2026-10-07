from __future__ import annotations

import unittest
import json
from starlette.requests import Request
from app.services.agent_batch import dispatch as dispatch_module
from app.services.request_identity import RequestActorContext, set_request_actor_context
from app.successor_runtime.runtime.ports import ProjectScopeRef
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from app.services.agent_batch.task_contract import validate_retry_action_payload
from app.services.agent_sessions import reset_agent_session_service_for_tests, reset_agent_session_store_for_tests
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore

pytestmark = pytest.mark.unit

try:
    from app.api import agent_batch as agent_batch_api
    from app.contracts.errors import ErrorCode
except Exception as exc:  # pragma: no cover - dependency/import guard
    agent_batch_api = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class AgentBatchApiUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"agent batch api unit tests require backend dependencies: {_IMPORT_ERROR}")

    def setUp(self):
        store = InMemoryAgentSessionStore()
        reset_agent_session_store_for_tests(store)
        reset_agent_session_service_for_tests(AgentSessionService(store=store))
        self.request = Request({"type": "http", "headers": []})
        set_request_actor_context(self.request, RequestActorContext("batch-actor", "test", True, "test-auth"))
        scope = ProjectScopeRef(project_key="proj-test", resolved_schema="project_proj_test",
                                project_registry_revision=1, incarnation="scope-1", scope_digest="a" * 64)
        for target, name, value in ((agent_batch_api, "engine", MagicMock()), (dispatch_module, "engine", MagicMock())):
            self.enterContext(patch.object(target, name, value))
        self.enterContext(patch.object(agent_batch_api.ServerProjectScopeResolver, "resolve", return_value=scope))
        self.submission = self.enterContext(patch.object(dispatch_module, "submit_installed_program",
            side_effect=lambda **kwargs: ({"run_id": kwargs["run_id"]}, ("work-1",))))
        self.outputs = self.enterContext(patch.object(dispatch_module, "read_installed_program_outputs", return_value=()))

    def _submit(self, payload):
        return agent_batch_api.submit_agent_batch_job(payload, self.request)

    def _submitted_payloads(self):
        return [json.loads(exact) for _, exact in self.submission.call_args.kwargs["values"]]

    @staticmethod
    def _build_submit_payload(*, idem: str | None = None):
        return agent_batch_api.AgentBatchSubmitRequest(
            project_key="proj-test",
            idempotency_key=idem,
            batch=agent_batch_api.AgentBatchSubmitBatch(
                jobs=[
                    agent_batch_api.AgentBatchItemSubmit(item_id="item-1", item_key="source-a"),
                    agent_batch_api.AgentBatchItemSubmit(source_id="source-b", override_params={"lang": "zh"}),
                ]
            ),
        )

    def test_submit_job_accepts_items_and_reuses_idempotency_key(self):
        first = self._submit(self._build_submit_payload(idem="idem-1"))
        second = self._submit(self._build_submit_payload(idem="idem-1"))
        self.assertEqual(first["data"]["accepted_count"], 2)
        self.assertEqual(first["data"]["rejected_count"], 0)
        self.assertEqual(first["data"]["run_ids"], [first["data"]["job_id"]])
        self.assertEqual(second["data"]["job_id"], first["data"]["job_id"])
        calls = self.submission.call_args_list
        self.assertEqual(len(calls), 2)
        identity_fields = (
            "idempotency_id", "identity_capability_id", "logical_request_id",
            "identity_operation_kind", "run_id",
        )
        self.assertEqual(
            tuple(calls[0].kwargs[field] for field in identity_fields),
            tuple(calls[1].kwargs[field] for field in identity_fields),
        )
        self.assertEqual(calls[0].kwargs["values"], calls[1].kwargs["values"])
        self.assertEqual(len(calls[0].kwargs["canonical_bindings"]), 4)
        self.assertEqual(calls[0].kwargs["actor_id"], "batch-actor")
        self.assertEqual([value["item"]["item_key"] for value in self._submitted_payloads()], ["source-a", "source-b"])

    def test_get_job_items_events_share_original_runtime_readback(self):
        journal_events = ({"event_type": "RunSubmitted", "sequence": 1},)
        with patch.object(dispatch_module, "read_installed_program", return_value=(
            {"run_id": "run-read", "state": "SUBMITTED"}, ({
                "step_id": "dispatch-1", "operation_id": "dispatch:item-1",
                "operation_kind": dispatch_module.batch_task.DISPATCH_SINGLE_KIND,
                "state": "PENDING", "failure_digest": None,
            },), journal_events,
        )) as read:
            job = agent_batch_api.get_agent_batch_job("run-read", self.request, "proj-test")
            items = agent_batch_api.list_agent_batch_items("run-read", self.request, "proj-test")
            events = agent_batch_api.get_agent_batch_events("run-read", self.request, "proj-test")
        self.assertEqual(job["data"]["status"], "queued")
        self.assertEqual(job["data"]["events"], journal_events)
        self.assertFalse(job["data"]["business_terminal"])
        self.assertEqual(items["data"]["items"][0]["input"], {"run_id": "run-read"})
        self.assertIsNone(items["data"]["items"][0]["output"])
        self.assertEqual(events["data"]["events"], journal_events)
        self.assertEqual(read.call_count, 3)
        for call in read.call_args_list:
            self.assertEqual(call.kwargs["actor_id"], "batch-actor")
            self.assertEqual(call.kwargs["project_key"], "proj-test")
        self.submission.assert_not_called()


    def test_validate_rule_set_reports_errors_and_warnings(self):
        invalid = agent_batch_api.validate_agent_batch_rule_set(agent_batch_api.RuleSetValidateRequest(rule_set={}))
        self.assertEqual(invalid["status"], "ok")
        self.assertFalse(invalid["data"]["valid"])
        self.assertEqual(invalid["data"]["errors"][0]["code"], "rule_set_empty")

        valid_with_warning = agent_batch_api.validate_agent_batch_rule_set(
            agent_batch_api.RuleSetValidateRequest(
                rule_set={"mode": "allow"},
                sample_items=[{"id": i} for i in range(501)],
            )
        )
        self.assertEqual(valid_with_warning["status"], "ok")
        self.assertTrue(valid_with_warning["data"]["valid"])
        self.assertEqual(valid_with_warning["data"]["warnings"][0]["code"], "sample_items_truncated")

    def test_submit_job_fail_closed_for_unsupported_channel_and_missing_contract_version(self):
        payload = agent_batch_api.AgentBatchSubmitRequest(
            project_key="proj-test",
            batch=agent_batch_api.AgentBatchSubmitBatch(
                jobs=[
                    agent_batch_api.AgentBatchItemSubmit(
                        item_id="bad-1",
                        channel="unknown.channel",
                        query_terms=["acme"],
                    ),
                    agent_batch_api.AgentBatchItemSubmit(
                        item_id="bad-2",
                        channel="search.market",
                        query_terms=["acme"],
                        contract_version="",
                    ),
                    agent_batch_api.AgentBatchItemSubmit(
                        item_id="ok-1",
                        item_key="source-a",
                    ),
                ]
            ),
        )
        out = self._submit(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 1)
        self.assertEqual(out["data"]["rejected_count"], 2)
        reason_codes = [x.get("reason_code") for x in out["data"]["rejected_job_items"]]
        self.assertIn("unsupported_channel", reason_codes)
        self.assertIn("contract_version_missing", reason_codes)

    def test_submit_job_fail_closed_when_channel_cannot_be_inferred(self):
        payload = agent_batch_api.AgentBatchSubmitRequest(
            project_key="proj-test",
            batch=agent_batch_api.AgentBatchSubmitBatch(
                jobs=[
                    agent_batch_api.AgentBatchItemSubmit(
                        item_id="ambiguous-1",
                        channel=None,
                        query_terms=[],
                    )
                ]
            ),
        )
        out = self._submit(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 0)
        self.assertEqual(out["data"]["rejected_count"], 1)
        self.assertEqual(out["data"]["rejected_job_items"][0]["reason_code"], "unsupported_channel")

    def test_submit_job_rejects_unsupported_search_market_override_params(self):
        payload = agent_batch_api.AgentBatchSubmitRequest(
            project_key="proj-test",
            batch=agent_batch_api.AgentBatchSubmitBatch(
                jobs=[
                    agent_batch_api.AgentBatchItemSubmit(
                        item_id="bad-override",
                        channel="search.market",
                        query_terms=["acme"],
                        override_params={"per_keyword_limit": 5},
                    )
                ]
            ),
        )
        out = self._submit(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 0)
        self.assertEqual(out["data"]["rejected_count"], 1)
        rejected = out["data"]["rejected_job_items"][0]
        self.assertEqual(rejected["reason_code"], "override_params_keys_unsupported")
        self.assertIn("per_keyword_limit", rejected["details"]["unsupported_keys"])
        self.submission.assert_not_called()

    def test_submit_job_rejects_unsupported_source_library_override_params(self):
        payload = agent_batch_api.AgentBatchSubmitRequest(
            project_key="proj-test",
            batch=agent_batch_api.AgentBatchSubmitBatch(
                jobs=[
                    agent_batch_api.AgentBatchItemSubmit(
                        item_id="bad-source-override",
                        channel="source_library",
                        item_key="ai_terminal.weekly",
                        override_params={"days_back": 30},
                    )
                ]
            ),
        )
        out = self._submit(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 0)
        self.assertEqual(out["data"]["rejected_count"], 1)
        rejected = out["data"]["rejected_job_items"][0]
        self.assertEqual(rejected["reason_code"], "override_params_keys_unsupported")
        self.assertIn("days_back", rejected["details"]["unsupported_keys"])
        self.submission.assert_not_called()

    def test_retry_action_contract_rejects_unsupported_search_market_mutation(self):
        normalized, reason_code, details = validate_retry_action_payload(
            {
                "action": "change_provider",
                "reason": "google looked weak",
                "channel": "search.market",
                "rewrite": {"provider": "serper", "item_key": "ai_terminal.weekly"},
            }
        )
        self.assertIsNone(normalized)
        self.assertEqual(reason_code, "retry_action_rewrite_fields_unsupported")
        self.assertEqual(details["unsupported_fields"], ["item_key"])

    def test_retry_action_contract_accepts_source_library_replacement_payload(self):
        normalized, reason_code, details = validate_retry_action_payload(
            {
                "action": "replace_source_library",
                "reason": "switch to a better fixed source",
                "channel": "source_library",
                "rewrite": {
                    "item_key": "robotics.market_watch",
                    "source_mode": "site_search",
                    "provider": "google",
                    "query_terms": ["robotics companies"],
                },
                "target_items": ["source_1"],
            }
        )
        self.assertIsNone(reason_code)
        self.assertEqual(details, {})
        self.assertEqual(normalized["rewrite"]["item_key"], "robotics.market_watch")
        self.assertEqual(normalized["rewrite"]["source_mode"], "site_search")
        self.assertEqual(normalized["rewrite"]["provider"], "google")
        self.assertEqual(normalized["rewrite"]["query_terms"], ["robotics companies"])
        self.assertEqual(normalized["target_items"], ["source_1"])

    def test_submit_job_respects_rule_set_provider_allowlist_and_cap(self):
        payload = agent_batch_api.AgentBatchSubmitRequest(
            project_key="proj-test",
            rule_set={
                "provider_allowlist": ["google"],
                "max_items_cap": 10,
            },
            batch=agent_batch_api.AgentBatchSubmitBatch(
                jobs=[
                    agent_batch_api.AgentBatchItemSubmit(
                        item_id="blocked-provider",
                        channel="search.market",
                        query_terms=["acme"],
                        provider="auto",
                        max_items=5,
                    ),
                    agent_batch_api.AgentBatchItemSubmit(
                        item_id="blocked-cap",
                        channel="search.market",
                        query_terms=["acme"],
                        provider="google",
                        max_items=20,
                    ),
                    agent_batch_api.AgentBatchItemSubmit(
                        item_id="allowed",
                        channel="search.market",
                        query_terms=["acme"],
                        provider="google",
                        max_items=10,
                    ),
                ]
            ),
        )
        out = self._submit(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 1)
        self.assertEqual(out["data"]["rejected_count"], 2)
        reason_codes = [x.get("reason_code") for x in out["data"]["rejected_job_items"]]
        self.assertIn("provider_blocked_by_rule_set", reason_codes)
        self.assertIn("max_items_exceeds_rule_set_cap", reason_codes)
        self.assertEqual(len(self._submitted_payloads()), 1)

    def test_submit_job_preserves_search_market_override_params(self):
        out = self._submit(agent_batch_api.AgentBatchSubmitRequest(project_key="proj-test",
            batch=agent_batch_api.AgentBatchSubmitBatch(jobs=[agent_batch_api.AgentBatchItemSubmit(
                item_id="search-override", channel="search.market", query_terms=["acme"], max_items=8,
                provider="google", override_params={"enable_extraction": False, "start_offset": 12},
            )])))
        self.assertEqual(out["data"]["accepted_count"], 1)
        item = self._submitted_payloads()[0]["item"]
        self.assertEqual(item["query_terms"], ["acme"])
        self.assertEqual(item["max_items"], 8)
        self.assertEqual(item["override_params"], {"enable_extraction": False, "start_offset": 12})

    def test_submit_job_preserves_typed_source_library_fields(self):
        out = self._submit(agent_batch_api.AgentBatchSubmitRequest(project_key="proj-test",
            batch=agent_batch_api.AgentBatchSubmitBatch(jobs=[agent_batch_api.AgentBatchItemSubmit(
                item_id="source-rich", channel="source_library", item_key="ai_terminal.weekly",
                query_terms=["ai terminal"], urls=["https://example.com/a"], max_items=3,
                provider="google", language="zh", scope="project", platforms=["web", "rss"],
            )])))
        self.assertEqual(out["data"]["accepted_count"], 1)
        item = self._submitted_payloads()[0]["item"]
        for key, expected in {"query_terms": ["ai terminal"], "urls": ["https://example.com/a"],
                              "max_items": 3, "provider": "google", "language": "zh",
                              "scope": "project", "platforms": ["web", "rss"]}.items():
            self.assertEqual(item[key], expected)

    def test_executor_health_endpoint_wraps_service_output(self):
        with patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@w1"], "diagnostics": {}},
        ):
            resp = agent_batch_api.get_agent_batch_executor_health()
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["data"]["workers"], ["celery@w1"])


    def test_submit_job_adds_lane_metadata_for_items(self):
        payload = agent_batch_api.AgentBatchSubmitRequest(
            project_key="proj-test",
            batch=agent_batch_api.AgentBatchSubmitBatch(
                jobs=[
                    agent_batch_api.AgentBatchItemSubmit(
                        item_id="m1",
                        channel="search.market",
                        query_terms=["ai"],
                    )
                ]
            ),
            priority=8,
        )
        out = self._submit(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_job_items"][0]["lane"], "system")

    def test_submit_job_preserves_runtime_readback_metadata_for_search_and_source(self):
        out = self._submit(agent_batch_api.AgentBatchSubmitRequest(project_key="proj-test",
            batch=agent_batch_api.AgentBatchSubmitBatch(jobs=[
                agent_batch_api.AgentBatchItemSubmit(item_id="search", channel="search.market", query_terms=["ai"]),
                agent_batch_api.AgentBatchItemSubmit(item_id="source", channel="source_library", item_key="source:1"),
            ])))
        self.assertEqual(out["data"]["accepted_count"], 2)
        payloads = self._submitted_payloads()
        for payload, line_key in zip(payloads, ["search_discovery_index", "resource_source_library"]):
            readback = payload["runtime_readback"]
            self.assertEqual(readback["line_key"], line_key)
            self.assertEqual(readback["trace_id"], payload["trace_id"])
            self.assertEqual(readback["run_id"], payload["workflow_run_id"])
            self.assertEqual(readback["queue"], payload["queue"])
            self.assertNotIn("events", readback)

    def test_submit_job_requires_approval_when_rule_set_enabled(self):
        payload = agent_batch_api.AgentBatchSubmitRequest(
            project_key="proj-test",
            rule_set={"require_approval": True},
            batch=agent_batch_api.AgentBatchSubmitBatch(
                jobs=[agent_batch_api.AgentBatchItemSubmit(item_id="item-1", item_key="source-a")]
            ),
        )
        out = self._submit(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 0)
        self.assertEqual(out["data"]["rejected_count"], 1)
        self.assertEqual(out["data"]["rejected_job_items"][0]["reason_code"], "approval_required")

    def test_submit_job_fails_closed_when_channel_approval_handler_missing(self):
        payload = agent_batch_api.AgentBatchSubmitRequest(
            project_key="proj-test",
            rule_set={"require_approval": True},
            batch=agent_batch_api.AgentBatchSubmitBatch(
                jobs=[
                    agent_batch_api.AgentBatchItemSubmit(
                        item_id="m1",
                        channel="search.market",
                        query_terms=["ai"],
                    )
                ]
            ),
        )
        with patch.object(agent_batch_api, "build_agent_batch_approval_argv", return_value=[]):
            with self.assertRaises(HTTPException) as ctx:
                self._submit(payload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("channel has no approval binding handler", ctx.exception.detail["error"]["message"])
        self.submission.assert_not_called()

    def test_channel_execution_registry_contains_only_the_live_rule_guard(self):
        search_entry = dict(agent_batch_api._CHANNEL_EXECUTION_REGISTRY.get("search.market") or {})
        self.assertEqual(set(agent_batch_api._CHANNEL_EXECUTION_REGISTRY), {"search.market"})
        self.assertEqual(set(search_entry), {"rule_guard"})
        self.assertTrue(callable(search_entry["rule_guard"]))

    def test_workflow_handoffs_query_aggregates_by_job_id_and_builds_replay_map(self):
        job_id = "runtime-job-1"
        with patch.object(
            agent_batch_api.handoff_store,
            "list_handoffs",
            return_value={"run_id": job_id, "items": [
                {"handoff_id": "h1", "handoff_mode": "pull_prepared_evidence"},
                {"handoff_id": "h2", "handoff_mode": "push_payload"},
            ], "total": 2},
        ) as read_handoffs:
            resp = agent_batch_api.list_agent_batch_job_workflow_handoffs(job_id)
        read_handoffs.assert_called_once_with(run_id=job_id, handoff_mode=None)
        self.assertEqual(resp["status"], "ok")
        self.assertIsNone(resp["error"])
        self.assertEqual(resp["data"]["runs_total"], 1)
        self.assertEqual(resp["data"]["handoffs_total"], 2)
        first = resp["data"]["items"][0]
        self.assertEqual(first["run_id"], job_id)
        self.assertEqual(first["replay_entry_map"]["h1"]["workflow_graph"],
                         f"/api/v1/workflow-graph/runs/{job_id}/handoff/h1/replay?source=historical")
        self.assertEqual(resp["data"]["skipped_count"], 0)

    def test_workflow_handoffs_query_keeps_unavailable_history_empty(self):
        with patch.object(agent_batch_api.handoff_store, "list_handoffs", side_effect=KeyError("absent")):
            resp = agent_batch_api.list_agent_batch_job_workflow_handoffs("unknown-run")
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["data"]["handoffs_total"], 0)
        self.assertEqual(resp["data"]["items"][0]["handoffs"], [])
        self.assertEqual(resp["data"]["items"][0]["replay_entry_map"], {})

    def test_approval_request_persists_agent_approval(self):
        service = agent_batch_api.get_agent_session_service()
        bundle = service.create_session(
            source="agent_batch",
            entrypoint_type="approval_request",
            goal="Approve a batch action",
            project_key="proj-a",
            task_blueprints=[
                {
                    "task_id": "task-1",
                    "subject": "Approval-gated batch action",
                    "task_type": "implementation",
                    "phase": "implementation",
                    "write_set": ["external:search.market"],
                }
            ],
        )
        session_id = bundle["session"]["session_id"]
        events_before = service.list_events(session_id)
        messages_before = service.list_messages(session_id)
        artifacts_before = service.list_artifacts(session_id)

        response = agent_batch_api.create_agent_batch_approval(
            agent_batch_api.AgentBatchApprovalRequest(
                argv=["task_ingest_market", "ai terminals"],
                cwd="/workspace/proj-a",
                env={"TRACE_ID": "trace-1"},
                channel="search.market",
                project_key="proj-a",
                requester_session_id=session_id,
                requester_task_id="task-1",
            )
        )

        self.assertEqual(response["status"], "ok")
        token = response["data"]["approval_token"]
        approvals = service.list_approvals(session_id=session_id)
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]["approval_id"], token)
        self.assertEqual(approvals[0]["status"], "pending")
        self.assertEqual(approvals[0]["requester_session_id"], session_id)
        self.assertEqual(approvals[0]["requester_task_id"], "task-1")
        self.assertEqual(approvals[0]["requester_actor"], "user_facing_assistant")
        self.assertEqual(
            approvals[0]["binding_payload"],
            {
                "argv": ["task_ingest_market", "ai terminals"],
                "cwd": "/workspace/proj-a",
                "env": {"TRACE_ID": "trace-1"},
                "channel": "search.market",
                "project_key": "proj-a",
            },
        )
        self.assertEqual(
            approvals[0]["metadata"],
            {"channel": "search.market", "project_key": "proj-a"},
        )

        tasks = {item["task_id"]: item for item in service.list_tasks(session_id)}
        approval_wait = next(item for item in tasks.values() if item["task_type"] == "approval_wait")
        self.assertEqual(tasks["task-1"]["status"], "blocked")
        self.assertEqual(approval_wait["status"], "in_progress")
        self.assertEqual(approval_wait["metadata"]["approval_id"], token)

        events_after = service.list_events(session_id)
        self.assertEqual(len(events_after), len(events_before) + 2)
        self.assertEqual(
            [event["event_type"] for event in events_after[-2:]],
            ["approval.pending", "approval.waiting"],
        )
        self.assertEqual(events_after[-2]["payload"]["approval_id"], token)
        self.assertEqual(events_after[-1]["payload"]["approval_id"], token)
        self.assertEqual(service.list_messages(session_id), messages_before)
        self.assertEqual(service.list_artifacts(session_id), artifacts_before)

    def test_load_job_missing_preserves_original_readback_failure(self):
        missing = HTTPException(status_code=404, detail={"error": {"code": ErrorCode.NOT_FOUND.value}})
        with patch.object(dispatch_module, "read_installed_program", side_effect=missing):
            with self.assertRaises(HTTPException) as ctx:
                agent_batch_api.get_agent_batch_job("missing-job", self.request, "proj-test")
        self.assertIs(ctx.exception, missing)

    def test_resolve_approval_rejects_unapproved_flag_with_structured_error(self):
        with self.assertRaises(HTTPException) as ctx:
            agent_batch_api.resolve_agent_batch_approval(
                "approval-token",
                agent_batch_api.AgentBatchApprovalResolveRequest(approved=False),
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("only approved=true is supported", ctx.exception.detail["error"]["message"])

    def test_resolve_approval_missing_token_raises_structured_not_found(self):
        with patch.object(agent_batch_api, "approve_approval", side_effect=KeyError("missing")):
            with self.assertRaises(HTTPException) as ctx:
                agent_batch_api.resolve_agent_batch_approval(
                    "missing-token",
                    agent_batch_api.AgentBatchApprovalResolveRequest(approved=True),
                )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(ctx.exception.detail["error"]["message"], "approval token not found")

    def test_resolve_approval_value_error_raises_structured_invalid_input(self):
        with patch.object(agent_batch_api, "approve_approval", side_effect=ValueError("binding mismatch")):
            with self.assertRaises(HTTPException) as ctx:
                agent_batch_api.resolve_agent_batch_approval(
                    "bad-token",
                    agent_batch_api.AgentBatchApprovalResolveRequest(approved=True),
                )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("binding mismatch", ctx.exception.detail["error"]["message"])

    def test_retired_nl_command_routes_return_gone_without_session_effect(self):
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="collect ai", project_key="proj-test"
        )
        with patch.object(agent_batch_api, "get_agent_session_service") as get_session_service:
            for route in (
                agent_batch_api.run_agent_batch_nl_command,
                agent_batch_api.run_agent_batch_nl_command_direct,
            ):
                with self.subTest(route=route.__name__):
                    with self.assertRaises(HTTPException) as ctx:
                        route(payload)
                    self.assertEqual(ctx.exception.status_code, 410)
                    self.assertEqual(
                        ctx.exception.detail["error"]["code"], "agent_runtime_retired"
                    )
            get_session_service.assert_not_called()

    def test_resolve_item_key_missing_identifiers_raises_structured_invalid_input(self):
        job = agent_batch_api.AgentBatchItemSubmit(item_id="missing-key")
        with self.assertRaises(HTTPException) as ctx:
            agent_batch_api._resolve_item_key(job)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["error"]["code"], ErrorCode.INVALID_INPUT.value)

        self.assertEqual(ctx.exception.detail["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("requires item_key or source_id", ctx.exception.detail["error"]["message"])

    def test_build_approval_binding_without_argv_raises_structured_invalid_input(self):
        job = agent_batch_api.AgentBatchItemSubmit(item_id="m1", channel="search.market", query_terms=["ai"])
        with patch.object(agent_batch_api, "build_agent_batch_approval_argv", return_value=[]):
            with self.assertRaises(HTTPException) as ctx:
                agent_batch_api._build_approval_binding(
                    channel="search.market",
                    project_key="proj-test",
                    workflow_run_id="run-1",
                    trace_id="trace-1",
                    job=job,
                )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("approval binding handler", ctx.exception.detail["error"]["message"])


if __name__ == "__main__":
    unittest.main()


def test_batch_readback_rejects_codec_and_ack_identity_drift(monkeypatch):
    from types import SimpleNamespace
    from app.successor_runtime.capabilities import batch_business, batch_task
    from app.successor_runtime.capabilities.checksum import canonical_json
    from app.successor_runtime.substrate.postgres.runtime_journal import ExactBindingConflict
    ack = batch_task.BatchTaskSingleDispatchAck(
        schema_version=batch_task.DISPATCH_SINGLE_ACK_SCHEMA, operation_kind=batch_task.DISPATCH_SINGLE_KIND,
        dispatch_id="item-one", channel="search.market", celery_task_id="task-one", lane="main", queue="celery",
    )
    result = batch_business.build_batch_business_result_from_ack_fields(task_id="different-task", ack_digest=ack.ack_digest)
    steps = ({"step_id": "dispatch", "operation_kind": batch_task.DISPATCH_SINGLE_KIND,
              "operation_id": batch_task.DISPATCH_SINGLE_OPERATION_ID + ":item-one", "state": "SUCCEEDED"},
             {"step_id": "wait", "operation_kind": batch_business.BUSINESS_WAIT_KIND,
              "operation_id": batch_business.BUSINESS_WAIT_KIND + ":item-one", "state": "SUCCEEDED"})
    monkeypatch.setattr(dispatch_module, "read_installed_program", lambda **kwargs: ({}, steps, ()))
    ack_ref = SimpleNamespace(object_type=batch_task.DISPATCH_SINGLE_ACK_TYPE, codec_id=batch_task.DISPATCH_SINGLE_ACK_TYPE.codec_id)
    result_ref = SimpleNamespace(object_type=batch_business.BUSINESS_WAIT_RESULT_TYPE, codec_id=batch_business.BUSINESS_WAIT_RESULT_CODEC_ID)
    outputs = [("dispatch", ack_ref, canonical_json(ack).encode()), ("wait", result_ref, canonical_json(result).encode())]
    monkeypatch.setattr(dispatch_module, "read_installed_program_outputs", lambda **kwargs: outputs)
    with pytest.raises(ExactBindingConflict, match="does not bind its dispatch ACK"):
        dispatch_module.load_dispatch_run(run_id="run", project_key="demo", actor_id="actor")
    ack_ref.codec_id = "wrong-codec"
    with pytest.raises(ExactBindingConflict, match="codec differs"):
        dispatch_module.load_dispatch_run(run_id="run", project_key="demo", actor_id="actor")


@pytest.mark.parametrize("source,trusted", [("anonymous", False), ("authenticated_oauth_token_sink", True), ("authenticated_oauth_token_sink_claims", True)])
def test_batch_submit_actor_boundary_rejects_untrusted_and_token_sink_proof(source, trusted):
    payload = agent_batch_api.AgentBatchSubmitRequest(
        project_key="demo", batch=agent_batch_api.AgentBatchSubmitBatch(jobs=[agent_batch_api.AgentBatchItemSubmit(item_key="one")]),
    )
    with patch.object(agent_batch_api, "cleanup_expired") as cleanup:
        with pytest.raises(HTTPException):
            agent_batch_api.submit_agent_batch_for_actor(payload, RequestActorContext("actor", source, trusted, "test"))
    cleanup.assert_not_called()
