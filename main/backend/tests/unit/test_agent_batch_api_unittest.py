from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

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


class _DelayTaskStub:
    def __init__(self):
        self.calls: list[tuple[str, str | None, dict, str | None]] = []

    def delay(self, item_key: str, project_key: str | None, override_params: dict, **kwargs):
        task_id = f"task-{len(self.calls) + 1}"
        self.calls.append((item_key, project_key, dict(override_params or {}), kwargs.get("workflow_run_id")))
        return SimpleNamespace(id=task_id)


class _MarketDelayTaskStub:
    def __init__(self):
        self.calls: list[
            tuple[list[str], int, bool, str | None, None, int | None, str | None, str | None, str | None]
        ] = []

    def delay(
        self,
        query_terms: list[str],
        max_items: int,
        enable_extraction: bool,
        project_key: str | None,
        start_offset: None,
        days_back: int | None,
        language: str | None,
        provider: str | None,
        **kwargs,
    ):
        task_id = f"mkt-{len(self.calls) + 1}"
        self.calls.append(
            (
                list(query_terms),
                max_items,
                enable_extraction,
                project_key,
                start_offset,
                days_back,
                language,
                provider,
                kwargs.get("workflow_run_id"),
            )
        )
        return SimpleNamespace(id=task_id)


class _AsyncResultStub:
    def __init__(self, *, status: str, ready: bool, successful: bool, failed: bool, result):
        self.status = status
        self._ready = ready
        self._successful = successful
        self._failed = failed
        self.result = result

    def ready(self) -> bool:
        return self._ready

    def successful(self) -> bool:
        return self._successful

    def failed(self) -> bool:
        return self._failed


class AgentBatchApiUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"agent batch api unit tests require backend dependencies: {_IMPORT_ERROR}")

    def setUp(self):
        agent_batch_api._BATCH_JOB_REGISTRY.clear()
        agent_batch_api._IDEMPOTENCY_INDEX.clear()
        store = InMemoryAgentSessionStore()
        reset_agent_session_store_for_tests(store)
        reset_agent_session_service_for_tests(AgentSessionService(store=store))

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
        delay_stub = _DelayTaskStub()
        with patch.object(agent_batch_api.tasks_module, "task_run_source_library_item", delay_stub):
            first = agent_batch_api.submit_agent_batch_job(self._build_submit_payload(idem="idem-1"))
            second = agent_batch_api.submit_agent_batch_job(self._build_submit_payload(idem="idem-1"))

        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["data"]["accepted_count"], 2)
        self.assertEqual(first["data"]["rejected_count"], 0)
        self.assertTrue(str(first["data"].get("session_id") or ""))
        self.assertEqual(first["data"]["current_phase"], "implementation")
        self.assertEqual([x["task_id"] for x in first["data"]["accepted_job_items"]], ["task-1", "task-2"])
        self.assertEqual(len(first["data"]["run_ids"]), 2)
        self.assertEqual(first["data"]["run_ids"][0], first["data"]["accepted_job_items"][0]["run_id"])
        self.assertTrue(first["data"]["accepted_job_items"][0]["workflow_run_id"].endswith("-run"))
        self.assertTrue(first["data"]["accepted_job_items"][0]["trace_id"].startswith("trace-"))
        self.assertEqual(second["status"], "ok")
        self.assertTrue(second["data"]["idempotency_reused"])
        self.assertEqual(second["data"]["accepted_count"], 2)
        self.assertEqual(second["data"]["session_id"], first["data"]["session_id"])
        self.assertEqual(len(second["data"]["run_ids"]), 2)
        self.assertTrue(delay_stub.calls[0][2]["workflow_run_id"].endswith("-run"))
        self.assertTrue((delay_stub.calls[0][3] or "").endswith("-run"))
        self.assertEqual(len(delay_stub.calls), 2)
        compat_session = agent_batch_api.get_agent_session_service().find_session_by_compat_job_id(first["data"]["job_id"])
        self.assertIsNotNone(compat_session)

    def test_get_job_and_items_and_events_reflect_celery_task_snapshots(self):
        delay_stub = _DelayTaskStub()
        status_by_task = {
            "task-1": _AsyncResultStub(status="SUCCESS", ready=True, successful=True, failed=False, result={"doc_id": 101}),
            "task-2": _AsyncResultStub(status="FAILURE", ready=True, successful=False, failed=True, result="boom"),
        }
        with patch.object(agent_batch_api.tasks_module, "task_run_source_library_item", delay_stub):
            submit = agent_batch_api.submit_agent_batch_job(self._build_submit_payload())
            job_id = submit["data"]["job_id"]
        with patch.object(
            agent_batch_api.celery_app,
            "AsyncResult",
            side_effect=lambda task_id: status_by_task[task_id],
        ):
            job = agent_batch_api.get_agent_batch_job(job_id)
            items = agent_batch_api.list_agent_batch_items(job_id)
            events = agent_batch_api.get_agent_batch_events(job_id)

        self.assertEqual(job["status"], "ok")
        self.assertEqual(job["data"]["status"], "completed")
        self.assertTrue(str(job["data"].get("session_id") or ""))
        self.assertEqual(job["data"]["progress"], {"total": 2, "succeeded": 1, "failed": 1, "running": 0, "queued": 0})
        self.assertEqual(len(job["data"]["run_ids"]), 2)
        self.assertEqual(items["status"], "ok")
        self.assertEqual(len(items["data"]["items"]), 2)
        self.assertEqual(items["data"]["items"][0]["run_id"], job["data"]["run_ids"][0])
        self.assertEqual(items["data"]["items"][0]["output"], {"doc_id": 101})
        self.assertEqual(items["data"]["items"][1]["error"], "boom")
        self.assertEqual(events["status"], "ok")
        self.assertEqual(events["data"]["events"][0]["run_id"], job["data"]["run_ids"][0])
        event_types = [e["event_type"] for e in events["data"]["events"]]
        self.assertIn("task.success", event_types)
        self.assertIn("task.failure", event_types)
        self.assertIn("agent_session.session.created", event_types)
        self.assertIn("agent_session.compat.job_state_projected", event_types)
        projected = agent_batch_api.get_agent_session_service().find_session_by_compat_job_id(job_id)
        self.assertIsNotNone(projected)
        session_bundle = agent_batch_api.get_agent_session_service().get_session_bundle(projected["session_id"])
        implementation_tasks = [
            task
            for task in session_bundle["tasks"]
            if str(dict(task.get("metadata") or {}).get("compat_projection") or "") == "agent_batch.job_item"
        ]
        verification_task = next(
            task
            for task in session_bundle["tasks"]
            if str(dict(task.get("metadata") or {}).get("compat_projection") or "") == "agent_batch.job_verification"
        )
        self.assertEqual({task["status"] for task in implementation_tasks}, {"completed", "failed"})
        self.assertEqual(verification_task["status"], "failed")

    def test_retry_replays_failed_items_only(self):
        delay_stub = _DelayTaskStub()
        with patch.object(agent_batch_api.tasks_module, "task_run_source_library_item", delay_stub):
            submit = agent_batch_api.submit_agent_batch_job(self._build_submit_payload())
            job_id = submit["data"]["job_id"]
            with patch.object(
                agent_batch_api.celery_app,
                "AsyncResult",
                side_effect=lambda task_id: {
                    "task-1": _AsyncResultStub(status="FAILURE", ready=True, successful=False, failed=True, result="bad"),
                    "task-2": _AsyncResultStub(status="SUCCESS", ready=True, successful=True, failed=False, result={"ok": True}),
                }[task_id],
            ):
                retried = agent_batch_api.retry_agent_batch_job(job_id, agent_batch_api.AgentBatchRetryRequest())

        self.assertEqual(retried["status"], "ok")
        self.assertEqual(retried["data"]["retry_count"], 1)
        self.assertEqual(retried["data"]["targets"], ["task-3"])
        stored = agent_batch_api._BATCH_JOB_REGISTRY[job_id]
        self.assertEqual([x.task_id for x in stored.items], ["task-1", "task-2", "task-3"])
        self.assertEqual(stored.items[2].item_id, "item-1-retry-1")

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
        delay_stub = _DelayTaskStub()
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
        with patch.object(agent_batch_api.tasks_module, "task_run_source_library_item", delay_stub):
            out = agent_batch_api.submit_agent_batch_job(payload)
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
        out = agent_batch_api.submit_agent_batch_job(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 0)
        self.assertEqual(out["data"]["rejected_count"], 1)
        self.assertEqual(out["data"]["rejected_job_items"][0]["reason_code"], "unsupported_channel")

    def test_submit_job_rejects_unsupported_search_market_override_params(self):
        market_delay_stub = _MarketDelayTaskStub()
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
        with patch.object(agent_batch_api.tasks_module, "task_ingest_market", market_delay_stub):
            out = agent_batch_api.submit_agent_batch_job(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 0)
        self.assertEqual(out["data"]["rejected_count"], 1)
        rejected = out["data"]["rejected_job_items"][0]
        self.assertEqual(rejected["reason_code"], "override_params_keys_unsupported")
        self.assertIn("per_keyword_limit", rejected["details"]["unsupported_keys"])
        self.assertEqual(len(market_delay_stub.calls), 0)

    def test_submit_job_rejects_unsupported_source_library_override_params(self):
        delay_stub = _DelayTaskStub()
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
        with patch.object(agent_batch_api.tasks_module, "task_run_source_library_item", delay_stub):
            out = agent_batch_api.submit_agent_batch_job(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 0)
        self.assertEqual(out["data"]["rejected_count"], 1)
        rejected = out["data"]["rejected_job_items"][0]
        self.assertEqual(rejected["reason_code"], "override_params_keys_unsupported")
        self.assertIn("days_back", rejected["details"]["unsupported_keys"])
        self.assertEqual(len(delay_stub.calls), 0)

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
        market_delay_stub = _MarketDelayTaskStub()
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
        with patch.object(agent_batch_api.tasks_module, "task_ingest_market", market_delay_stub):
            out = agent_batch_api.submit_agent_batch_job(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 1)
        self.assertEqual(out["data"]["rejected_count"], 2)
        reason_codes = [x.get("reason_code") for x in out["data"]["rejected_job_items"]]
        self.assertIn("provider_blocked_by_rule_set", reason_codes)
        self.assertIn("max_items_exceeds_rule_set_cap", reason_codes)
        self.assertEqual(len(market_delay_stub.calls), 1)

    def test_submit_job_preserves_search_market_override_params(self):
        market_delay_stub = _MarketDelayTaskStub()
        payload = agent_batch_api.AgentBatchSubmitRequest(
            project_key="proj-test",
            batch=agent_batch_api.AgentBatchSubmitBatch(
                jobs=[
                    agent_batch_api.AgentBatchItemSubmit(
                        item_id="search-override",
                        channel="search.market",
                        query_terms=["acme"],
                        max_items=8,
                        provider="google",
                        override_params={"enable_extraction": False, "start_offset": 12},
                    )
                ]
            ),
        )
        with patch.object(agent_batch_api.tasks_module, "task_ingest_market", market_delay_stub):
            out = agent_batch_api.submit_agent_batch_job(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 1)
        self.assertEqual(len(market_delay_stub.calls), 1)
        call = market_delay_stub.calls[0]
        self.assertEqual(call[0], ["acme"])
        self.assertEqual(call[1], 8)
        self.assertFalse(call[2])
        self.assertEqual(call[4], 12)

    def test_submit_job_promotes_source_library_top_level_fields_into_override_params(self):
        delay_stub = _DelayTaskStub()
        payload = agent_batch_api.AgentBatchSubmitRequest(
            project_key="proj-test",
            batch=agent_batch_api.AgentBatchSubmitBatch(
                jobs=[
                    agent_batch_api.AgentBatchItemSubmit(
                        item_id="source-rich",
                        channel="source_library",
                        item_key="ai_terminal.weekly",
                        query_terms=["ai terminal"],
                        urls=["https://example.com/a"],
                        max_items=3,
                        provider="google",
                        language="zh",
                        scope="project",
                        platforms=["web", "rss"],
                        source_mode="site_search",
                    )
                ]
            ),
        )
        with patch.object(agent_batch_api.tasks_module, "task_run_source_library_item", delay_stub):
            out = agent_batch_api.submit_agent_batch_job(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 1)
        self.assertEqual(len(delay_stub.calls), 1)
        _, _, override_params, workflow_run_id = delay_stub.calls[0]
        self.assertEqual(override_params["query_terms"], ["ai terminal"])
        self.assertEqual(override_params["urls"], ["https://example.com/a"])
        self.assertEqual(override_params["max_items"], 3)
        self.assertEqual(override_params["limit"], 3)
        self.assertEqual(override_params["provider"], "google")
        self.assertEqual(override_params["language"], "zh")
        self.assertEqual(override_params["scope"], "project")
        self.assertEqual(override_params["platforms"], ["web", "rss"])
        self.assertEqual(override_params["source_mode"], "site_search")
        self.assertEqual(override_params["workflow_run_id"], workflow_run_id)

    def test_nl_command_dispatches_search_market_batch(self):
        market_delay_stub = _MarketDelayTaskStub()
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="采集最近14天美国在线彩票市场新闻和监管政策，前30条",
            project_key="proj-nl",
            idempotency_key="idem-nl-1",
        )
        with patch.object(agent_batch_api.tasks_module, "task_ingest_market", market_delay_stub), patch.object(
            __import__("app.services.agent_batch.agent_loop", fromlist=["invoke_skill_safe"]),
            "invoke_skill_safe",
            return_value={"ok": False, "result": None, "error": "planner unavailable"},
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        parsed = resp["data"]["parsed"]
        self.assertEqual(parsed["channel"], "search.market")
        self.assertEqual(parsed["days_back"], 14)
        self.assertEqual(parsed["max_items"], 30)
        self.assertEqual(parsed["language"], "zh")
        self.assertEqual(parsed["intent"], "regulatory_monitoring")
        self.assertGreaterEqual(parsed["task_count"], 2)
        self.assertEqual(resp["data"]["submit"]["accepted_count"], parsed["task_count"])
        self.assertEqual(resp["data"]["submit"]["accepted_job_items"][0]["task_id"], "mkt-1")
        self.assertEqual(len(market_delay_stub.calls), parsed["task_count"])
        self.assertTrue(resp["data"]["executor"]["worker_online"])
        self.assertTrue(resp["data"]["compat_mode"])
        self.assertTrue(str(resp["data"]["session_id"]))
        self.assertTrue(str(resp["data"]["root_task_id"]))

    def test_nl_command_supports_dry_run_without_dispatch(self):
        market_delay_stub = _MarketDelayTaskStub()
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="帮我搜索人工智能终端成功案例，最近7天，前10条",
            project_key="proj-nl",
            dry_run=True,
        )
        with patch.object(agent_batch_api.tasks_module, "task_ingest_market", market_delay_stub), patch.object(
            __import__("app.services.agent_batch.agent_loop", fromlist=["invoke_skill_safe"]),
            "invoke_skill_safe",
            return_value={"ok": False, "result": None, "error": "planner unavailable"},
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": False, "workers": []},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        self.assertTrue(resp["data"]["dry_run"])
        self.assertIsNone(resp["data"]["submit"])
        self.assertGreaterEqual(len(resp["data"]["plan"]["tasks"]), 1)
        self.assertEqual(len(market_delay_stub.calls), 0)

    def test_nl_command_preserves_search_market_override_params_from_loop_tasks(self):
        market_delay_stub = _MarketDelayTaskStub()
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="search ai chips last 7 days top 5",
            project_key="proj-nl",
        )
        with patch.object(
            __import__("app.services.agent_batch.agent_loop", fromlist=["invoke_skill_safe"]),
            "invoke_skill_safe",
            return_value={"ok": False, "result": None, "error": "planner unavailable"},
        ), patch.object(
            agent_batch_api,
            "plan_batch_search_command",
            return_value={
                "intent": "market_news",
                "strategy": "single_query",
                "tasks": [
                    {
                        "channel": "search.market",
                        "query_terms": ["ai chips"],
                        "max_items": 5,
                        "provider": "google",
                        "language": "en",
                        "days_back": 7,
                        "override_params": {"enable_extraction": False, "start_offset": 9},
                    }
                ],
            },
        ), patch.object(agent_batch_api.tasks_module, "task_ingest_market", market_delay_stub), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["data"]["submit"]["accepted_count"], 1)
        self.assertEqual(len(market_delay_stub.calls), 1)
        call = market_delay_stub.calls[0]
        self.assertFalse(call[2])
        self.assertEqual(call[4], 9)

    def test_nl_command_rejects_unsupported_override_params_from_loop_tasks(self):
        market_delay_stub = _MarketDelayTaskStub()
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="search ai chips last 7 days top 5",
            project_key="proj-nl",
        )
        with patch.object(
            __import__("app.services.agent_batch.agent_loop", fromlist=["invoke_skill_safe"]),
            "invoke_skill_safe",
            return_value={"ok": False, "result": None, "error": "planner unavailable"},
        ), patch.object(
            agent_batch_api,
            "plan_batch_search_command",
            return_value={
                "intent": "market_news",
                "strategy": "single_query",
                "tasks": [
                    {
                        "channel": "search.market",
                        "query_terms": ["ai chips"],
                        "override_params": {"per_keyword_limit": 3},
                    }
                ],
            },
        ), patch.object(agent_batch_api.tasks_module, "task_ingest_market", market_delay_stub), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["data"]["submit"]["accepted_count"], 0)
        self.assertEqual(resp["data"]["submit"]["rejected_count"], 1)
        rejected = resp["data"]["submit"]["rejected_job_items"][0]
        self.assertEqual(rejected["reason_code"], "override_params_keys_unsupported")
        self.assertEqual(len(market_delay_stub.calls), 0)

    def test_nl_command_submit_response_preserves_optional_run_id_when_present(self):
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="search ai chips last 7 days top 5",
            project_key="proj-nl",
        )
        with patch.object(
            __import__("app.services.agent_batch.agent_loop", fromlist=["invoke_skill_safe"]),
            "invoke_skill_safe",
            return_value={"ok": False, "result": None, "error": "planner unavailable"},
        ), patch.object(
            agent_batch_api,
            "plan_batch_search_command",
            return_value={
                "intent": "market_news",
                "strategy": "single_query",
                "tasks": [
                    {
                        "channel": "search.market",
                        "query_terms": ["ai chips"],
                        "max_items": 5,
                        "provider": "auto",
                        "language": "en",
                        "days_back": 7,
                    }
                ],
            },
        ), patch.object(
            agent_batch_api,
            "submit_agent_batch_job",
            return_value={"status": "ok", "data": {"job_id": "abj-1", "accepted_count": 1, "run_id": "run-123"}},
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["data"]["submit"]["run_id"], "run-123")

    def test_nl_command_submit_response_allows_missing_optional_run_id(self):
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="search ai chips last 7 days top 5",
            project_key="proj-nl",
        )
        with patch.object(
            __import__("app.services.agent_batch.agent_loop", fromlist=["invoke_skill_safe"]),
            "invoke_skill_safe",
            return_value={"ok": False, "result": None, "error": "planner unavailable"},
        ), patch.object(
            agent_batch_api,
            "plan_batch_search_command",
            return_value={
                "intent": "market_news",
                "strategy": "single_query",
                "tasks": [
                    {
                        "channel": "search.market",
                        "query_terms": ["ai chips"],
                        "max_items": 5,
                        "provider": "auto",
                        "language": "en",
                        "days_back": 7,
                    }
                ],
            },
        ), patch.object(
            agent_batch_api,
            "submit_agent_batch_job",
            return_value={"status": "ok", "data": {"job_id": "abj-1", "accepted_count": 1}},
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        self.assertNotIn("run_id", resp["data"]["submit"])

    def test_nl_command_defaults_to_skill_planner_path_metadata(self):
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="search semiconductor regulation updates last 7 days top 5",
            project_key="proj-nl",
        )
        skill_text = (
            '{"intent":"regulatory_monitoring","strategy":"single_query","tasks":[{"channel":"search.market",'
            '"query_terms":["semiconductor regulation updates"],"max_items":5,"provider":"auto","language":"en","days_back":7}]}'
        )
        with patch.object(
            __import__("app.services.agent_batch.agent_loop", fromlist=["invoke_skill_safe"]),
            "invoke_skill_safe",
            return_value={"ok": True, "result": {"result": {"text": skill_text}}, "error": None},
        ), patch.object(
            agent_batch_api,
            "plan_batch_search_command",
            return_value={
                "intent": "regulatory_monitoring",
                "strategy": "single_query",
                "tasks": [
                    {
                        "channel": "search.market",
                        "query_terms": ["semiconductor regulation updates"],
                        "max_items": 5,
                        "provider": "auto",
                        "language": "en",
                        "days_back": 7,
                    }
                ],
                "loop": {
                    "planner": "skill",
                    "planner_path": "skill_planner",
                    "degradation_flags": [],
                    "iteration": 1,
                },
            },
        ), patch.object(
            agent_batch_api,
            "submit_agent_batch_job",
            return_value={"status": "ok", "data": {"job_id": "abj-1", "accepted_count": 1}},
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["data"]["plan"]["loop"]["planner"], "skill")
        self.assertEqual(resp["data"]["plan"]["loop"]["planner_path"], "skill_planner")
        self.assertEqual(resp["data"]["plan"]["loop"]["degradation_flags"], [])

    def test_nl_command_skill_failure_fallback_has_degradation_flags(self):
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="search payment market news last 3 days top 8",
            project_key="proj-nl",
        )
        with patch.object(
            __import__("app.services.agent_batch.agent_loop", fromlist=["invoke_skill_safe"]),
            "invoke_skill_safe",
            return_value={"ok": False, "result": None, "error": "skill_invoke_error"},
        ), patch.object(
            agent_batch_api,
            "plan_batch_search_command",
            return_value={
                "intent": "market_news",
                "strategy": "single_query",
                "tasks": [
                    {
                        "channel": "search.market",
                        "query_terms": ["payment market news"],
                        "max_items": 8,
                        "provider": "auto",
                        "language": "en",
                        "days_back": 3,
                    }
                ],
                "loop": {
                    "planner": "rule",
                    "planner_path": "rule_planner_fallback",
                    "degradation_flags": ["skill_planner_failed"],
                    "fallback_reason": "skill_invoke_error",
                },
            },
        ), patch.object(
            agent_batch_api,
            "submit_agent_batch_job",
            return_value={"status": "ok", "data": {"job_id": "abj-2", "accepted_count": 1}},
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        loop_meta = resp["data"]["plan"]["loop"]
        self.assertEqual(loop_meta["planner"], "rule")
        self.assertEqual(loop_meta["planner_path"], "rule_planner_fallback")
        self.assertIn("skill_planner_failed", loop_meta["degradation_flags"])

    def test_executor_health_endpoint_wraps_service_output(self):
        with patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@w1"], "diagnostics": {}},
        ):
            resp = agent_batch_api.get_agent_batch_executor_health()
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["data"]["workers"], ["celery@w1"])

    def test_nl_command_direct_waits_completion_and_returns_completion_block(self):
        market_delay_stub = _MarketDelayTaskStub()
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="search ai chips last 7 days top 3",
            project_key="proj-nl",
            completion_timeout_seconds=3,
            completion_poll_seconds=0.2,
        )
        with patch.object(agent_batch_api.tasks_module, "task_ingest_market", market_delay_stub), patch.object(
            __import__("app.services.agent_batch.agent_loop", fromlist=["invoke_skill_safe"]),
            "invoke_skill_safe",
            return_value={"ok": False, "result": None, "error": "planner unavailable"},
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ), patch.object(
            agent_batch_api.celery_app,
            "AsyncResult",
            return_value=_AsyncResultStub(status="SUCCESS", ready=True, successful=True, failed=False, result={"ok": True}),
        ):
            resp = agent_batch_api.run_agent_batch_nl_command_direct(payload)

        self.assertEqual(resp["status"], "ok")
        completion = resp["data"].get("completion") or {}
        self.assertTrue(completion.get("completed"))
        self.assertFalse(completion.get("timed_out"))
        self.assertEqual(str(completion.get("phase")), "completed")
        self.assertEqual((completion.get("progress") or {}).get("failed"), 0)

    def test_nl_command_persists_search_brief_into_job_meta_and_events(self):
        market_delay_stub = _MarketDelayTaskStub()
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="search ai terminal market signals last 14 days top 20",
            project_key="proj-nl",
            dry_run=False,
        )
        skill_text = (
            '{"intent":"market_news","strategy":"parallel_by_query_term","tasks":[{"channel":"search.market",'
            '"query_terms":["ai terminal market signals"],"max_items":20,"provider":"auto","language":"en","days_back":14}]}'
        )
        with patch.object(agent_batch_api.tasks_module, "task_ingest_market", market_delay_stub), patch.object(
            __import__("app.services.agent_batch.agent_loop", fromlist=["invoke_skill_safe"]),
            "invoke_skill_safe",
            return_value={"ok": True, "result": {"result": {"text": skill_text}}, "error": None},
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)
            job_id = str((resp["data"].get("submit") or {}).get("job_id") or "")

        self.assertEqual(resp["status"], "ok")
        self.assertTrue(job_id)
        self.assertIn("search_brief", resp["data"]["plan"])

        with patch.object(
            agent_batch_api.celery_app,
            "AsyncResult",
            return_value=_AsyncResultStub(status="SUCCESS", ready=True, successful=True, failed=False, result={"ok": True}),
        ):
            job = agent_batch_api.get_agent_batch_job(job_id)
            events = agent_batch_api.get_agent_batch_events(job_id)

        self.assertEqual(job["status"], "ok")
        self.assertIn("search_brief", job["data"]["meta"])
        self.assertTrue(str(job["data"].get("session_id") or ""))
        self.assertEqual(job["data"]["meta"]["search_brief"]["goal"], "search ai terminal market signals last 14 days top 20")
        self.assertEqual(job["data"]["meta"]["search_brief"]["time_strategy"]["days_back"], 14)
        self.assertIn("stage_artifacts", job["data"]["meta"])
        self.assertEqual(job["data"]["meta"]["stage_artifacts"]["search_brief"]["name"], "search_brief")

        event_types = [event["event_type"] for event in events["data"]["events"]]
        self.assertIn("search_brief.created", event_types)
        self.assertIn("search_critic.scored", event_types)
        self.assertIn("search_retry.skipped", event_types)
        self.assertIn("agent_session.session.created", event_types)
        search_brief_event = next(event for event in events["data"]["events"] if event["event_type"] == "search_brief.created")
        self.assertEqual(search_brief_event["payload"]["search_brief"]["goal"], "search ai terminal market signals last 14 days top 20")
        self.assertEqual(search_brief_event["payload"]["stage"]["name"], "search_brief")

    def test_nl_command_persists_retry_state_when_bounded_retry_is_enabled(self):
        market_delay_stub = _MarketDelayTaskStub()
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="search chip pricing regulation last 120 days top 6",
            project_key="proj-nl",
            dry_run=False,
            enable_bounded_retry=True,
        )
        skill_text = (
            '{"intent":"market_news","strategy":"single_query","tasks":[{"channel":"search.market",'
            '"query_terms":["chip pricing regulation"],"max_items":6,"provider":"auto","language":"en","days_back":120}]}'
        )
        with patch.object(agent_batch_api.tasks_module, "task_ingest_market", market_delay_stub), patch.object(
            __import__("app.services.agent_batch.agent_loop", fromlist=["invoke_skill_safe"]),
            "invoke_skill_safe",
            return_value={"ok": True, "result": {"result": {"text": skill_text}}, "error": None},
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)
            job_id = str((resp["data"].get("submit") or {}).get("job_id") or "")

        self.assertEqual(resp["status"], "ok")
        self.assertEqual(len(market_delay_stub.calls), 2)
        self.assertTrue(job_id)
        self.assertEqual(len(resp["data"]["submit_rounds"]), 2)
        self.assertTrue(resp["data"]["plan"]["search_retry"]["scheduled"])
        self.assertEqual(resp["data"]["plan"]["search_retry"]["action"]["action"], "narrow_query_terms")

        with patch.object(
            agent_batch_api.celery_app,
            "AsyncResult",
            return_value=_AsyncResultStub(status="SUCCESS", ready=True, successful=True, failed=False, result={"ok": True}),
        ):
            job = agent_batch_api.get_agent_batch_job(job_id)
            events = agent_batch_api.get_agent_batch_events(job_id)
            metrics = agent_batch_api.get_agent_batch_search_policy_metrics()

        self.assertEqual(job["status"], "ok")
        self.assertIn("search_retry", job["data"]["meta"])
        self.assertTrue(job["data"]["meta"]["search_retry"]["scheduled"])
        self.assertEqual(job["data"]["meta"]["search_retry"]["round"], 2)
        self.assertEqual(len(job["data"]["meta"]["submit_rounds"]), 2)
        self.assertEqual(job["data"]["meta"]["stage_artifacts"]["search_retry"]["name"], "search_retry")
        event_types = [event["event_type"] for event in events["data"]["events"]]
        self.assertIn("search_round.completed", event_types)
        self.assertIn("search_critic.scored", event_types)
        self.assertIn("search_retry.scheduled", event_types)
        self.assertEqual(metrics["status"], "ok")
        self.assertEqual(metrics["data"]["contract_version"], "agent_batch.search_policy_metrics.v1")
        self.assertGreaterEqual(int(metrics["data"]["retry_outcome_counts"]["scheduled"]), 1)

    def test_nl_command_retry_can_attach_source_library_and_preserve_runtime_fields(self):
        market_delay_stub = _MarketDelayTaskStub()
        source_delay_stub = _DelayTaskStub()
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="search ai terminal products companies web only last 30 days top 10",
            project_key="proj-nl",
            dry_run=False,
            enable_bounded_retry=True,
        )
        skill_text = (
            '{"intent":"market_research_general","strategy":"single_query","constraints":{"retrieval_mode":"web_only"},'
            '"tasks":[{"channel":"search.market","query_terms":["ai terminal products companies"],'
            '"max_items":10,"provider":"auto","language":"en","days_back":30}]}'
        )
        with patch.object(agent_batch_api.tasks_module, "task_ingest_market", market_delay_stub), patch.object(
            agent_batch_api.tasks_module, "task_run_source_library_item", source_delay_stub
        ), patch.object(
            __import__("app.services.agent_batch.agent_loop", fromlist=["invoke_skill_safe"]),
            "invoke_skill_safe",
            return_value={"ok": True, "result": {"result": {"text": skill_text}}, "error": None},
        ), patch(
            "app.services.agent_batch.agent_loop._list_effective_source_items",
            return_value=[
                {
                    "item_key": "ai_terminal.weekly",
                    "name": "AI Terminal Weekly",
                    "channel_key": "handler.cluster",
                    "enabled": True,
                    "params": {
                        "site_entries": ["https://example.com/search?q={{q}}"],
                        "expected_entry_type": "search_template",
                    },
                }
            ],
        ), patch(
            "app.services.agent_batch.agent_loop._build_channel_capability_index",
            return_value={"handler.cluster": {"channel_key": "handler.cluster", "provider": "handler", "credential_refs": []}},
        ), patch(
            "app.services.agent_batch.agent_loop._is_item_credentials_ready",
            return_value=True,
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        self.assertEqual(len(market_delay_stub.calls), 2)
        self.assertEqual(len(source_delay_stub.calls), 1)
        self.assertTrue(resp["data"]["plan"]["search_retry"]["scheduled"])
        self.assertEqual(resp["data"]["plan"]["search_retry"]["action"]["action"], "attach_source_library")
        self.assertEqual(len(resp["data"]["submit_rounds"]), 2)
        self.assertEqual(resp["data"]["submit_rounds"][1]["accepted_count"], 2)

        item_key, project_key, override_params, workflow_run_id = source_delay_stub.calls[0]
        self.assertEqual(item_key, "ai_terminal.weekly")
        self.assertEqual(project_key, "proj-nl")
        self.assertEqual(override_params["query_terms"], ["ai terminal products companies"])
        self.assertEqual(override_params["provider"], "auto")
        self.assertEqual(override_params["max_items"], 10)
        self.assertEqual(override_params["limit"], 10)
        self.assertNotIn("source_mode", override_params)
        self.assertEqual(override_params["workflow_run_id"], workflow_run_id)

    def test_search_policy_benchmark_pack_and_gate_endpoints_return_contract_shapes(self):
        pack = agent_batch_api.get_agent_batch_search_policy_benchmark_pack()
        gate = agent_batch_api.get_agent_batch_search_policy_gate()

        self.assertEqual(pack["status"], "ok")
        self.assertEqual(pack["data"]["contract_version"], "agent_batch.search_policy_benchmark.v1")
        self.assertEqual(len(pack["data"]["cases"]), 5)

        self.assertEqual(gate["status"], "ok")
        self.assertEqual(gate["data"]["contract_version"], "agent_batch.search_policy_benchmark.v1")
        self.assertIn(gate["data"]["decision"], {"go", "hold", "no_go"})
        self.assertGreaterEqual(len(gate["data"]["criteria"]), 3)

    def test_submit_job_adds_lane_metadata_for_items(self):
        market_delay_stub = _MarketDelayTaskStub()
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
        with patch.object(agent_batch_api.tasks_module, "task_ingest_market", market_delay_stub):
            out = agent_batch_api.submit_agent_batch_job(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_job_items"][0]["lane"], "system")

    def test_submit_job_requires_approval_when_rule_set_enabled(self):
        delay_stub = _DelayTaskStub()
        payload = agent_batch_api.AgentBatchSubmitRequest(
            project_key="proj-test",
            rule_set={"require_approval": True},
            batch=agent_batch_api.AgentBatchSubmitBatch(
                jobs=[agent_batch_api.AgentBatchItemSubmit(item_id="item-1", item_key="source-a")]
            ),
        )
        with patch.object(agent_batch_api.tasks_module, "task_run_source_library_item", delay_stub):
            out = agent_batch_api.submit_agent_batch_job(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 0)
        self.assertEqual(out["data"]["rejected_count"], 1)
        self.assertEqual(out["data"]["rejected_job_items"][0]["reason_code"], "approval_required")

    def test_submit_job_fails_closed_when_channel_submit_handler_missing(self):
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
        )
        with patch.dict(agent_batch_api._CHANNEL_EXECUTION_REGISTRY, {}, clear=True):
            out = agent_batch_api.submit_agent_batch_job(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 0)
        self.assertEqual(out["data"]["rejected_count"], 1)
        self.assertEqual(out["data"]["rejected_job_items"][0]["reason_code"], "dispatch_error")
        self.assertIn("channel has no submit handler", out["data"]["rejected_job_items"][0]["reason"])

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
            out = agent_batch_api.submit_agent_batch_job(payload)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["accepted_count"], 0)
        self.assertEqual(out["data"]["rejected_count"], 1)
        self.assertEqual(out["data"]["rejected_job_items"][0]["reason_code"], "dispatch_error")
        self.assertIn("channel has no approval binding handler", out["data"]["rejected_job_items"][0]["reason"])

    def test_channel_execution_registry_is_built_from_shared_contract(self):
        search_entry = dict(agent_batch_api._CHANNEL_EXECUTION_REGISTRY.get("search.market") or {})
        source_entry = dict(agent_batch_api._CHANNEL_EXECUTION_REGISTRY.get("source_library") or {})
        self.assertTrue(callable(search_entry.get("submitter")))
        self.assertTrue(callable(search_entry.get("rule_guard")))
        self.assertTrue(callable(source_entry.get("submitter")))
        self.assertIsNone(source_entry.get("rule_guard"))

    def test_workflow_handoffs_query_aggregates_by_job_id_and_builds_replay_map(self):
        delay_stub = _DelayTaskStub()
        with patch.object(agent_batch_api.tasks_module, "task_run_source_library_item", delay_stub):
            submit = agent_batch_api.submit_agent_batch_job(self._build_submit_payload())
            job_id = submit["data"]["job_id"]
            run_id_1 = submit["data"]["accepted_job_items"][0]["workflow_run_id"]
            run_id_2 = submit["data"]["accepted_job_items"][1]["workflow_run_id"]

        status_by_task = {
            "task-1": _AsyncResultStub(
                status="SUCCESS",
                ready=True,
                successful=True,
                failed=False,
                result={"run_id": "external-run-1"},
            ),
            "task-2": _AsyncResultStub(
                status="SUCCESS",
                ready=True,
                successful=True,
                failed=False,
                result={"data": {"run_id": "external-run-2"}},
            ),
        }

        with patch.object(
            agent_batch_api.celery_app,
            "AsyncResult",
            side_effect=lambda task_id: status_by_task[task_id],
        ), patch.object(
            agent_batch_api.handoff_store,
            "list_handoffs",
            side_effect=[
                {
                    "run_id": run_id_1,
                    "items": [{"handoff_id": "h1", "handoff_mode": "pull_prepared_evidence"}],
                    "total": 1,
                },
                {
                    "run_id": run_id_2,
                    "items": [{"handoff_id": "h2", "handoff_mode": "push_payload"}],
                    "total": 1,
                },
            ],
        ):
            resp = agent_batch_api.list_agent_batch_job_workflow_handoffs(job_id)

        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["error"], None)
        self.assertIn("meta", resp)
        self.assertEqual(resp["data"]["runs_total"], 2)
        self.assertEqual(resp["data"]["handoffs_total"], 2)
        first = resp["data"]["items"][0]
        self.assertEqual(first["run_id"], run_id_1)
        self.assertEqual(first["replay_entry_map"]["h1"]["workflow_graph"], f"/api/v1/workflow-graph/runs/{run_id_1}/handoff/h1/replay")
        self.assertEqual(resp["data"]["skipped_count"], 0)

    def test_workflow_handoffs_query_skips_legacy_item_when_run_id_missing(self):
        job_id = "abj-legacy"
        agent_batch_api._BATCH_JOB_REGISTRY[job_id] = agent_batch_api._BatchJobRecord(
            job_id=job_id,
            project_key="proj-test",
            items=[
                agent_batch_api._BatchItemRecord(
                    item_id="legacy-item-1",
                    item_key="source-a",
                    project_key="proj-test",
                    channel="source_library",
                    task_id="legacy-task-1",
                    workflow_run_id=None,
                    trace_id=None,
                )
            ],
        )

        with patch.object(
            agent_batch_api.celery_app,
            "AsyncResult",
            return_value=_AsyncResultStub(status="SUCCESS", ready=True, successful=True, failed=False, result={"ok": True}),
        ):
            resp = agent_batch_api.list_agent_batch_job_workflow_handoffs(job_id)

        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["data"]["skipped_count"], 1)
        self.assertEqual(resp["data"]["skipped_items"][0]["reason_code"], "run_id_missing")
        self.assertEqual(len(resp["data"]["items"]), 0)

    def test_approval_request_persists_agent_approval(self):
        response = agent_batch_api.create_agent_batch_approval(
            agent_batch_api.AgentBatchApprovalRequest(
                argv=["task_ingest_market", "ai terminals"],
                cwd="/workspace/proj-a",
                env={"TRACE_ID": "trace-1"},
                channel="search.market",
                project_key="proj-a",
                requester_session_id="session-1",
                requester_task_id="task-1",
            )
        )

        self.assertEqual(response["status"], "ok")
        token = response["data"]["approval_token"]
        approvals = agent_batch_api.get_agent_session_service().list_approvals(session_id="session-1")
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]["approval_id"], token)

    def test_load_job_missing_raises_structured_not_found(self):
        with self.assertRaises(HTTPException) as ctx:
            agent_batch_api._load_job("missing-job")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail["error"]["code"], ErrorCode.NOT_FOUND.value)

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

    def test_nl_command_requires_command_with_structured_error(self):
        with self.assertRaises(HTTPException) as ctx:
            agent_batch_api.run_agent_batch_nl_command(
                agent_batch_api.AgentBatchNlCommandRequest(command="   ", project_key="proj-test")
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(ctx.exception.detail["error"]["message"], "command is required")

    def test_nl_command_loop_failure_raises_structured_invalid_input(self):
        payload = agent_batch_api.AgentBatchNlCommandRequest(command="collect ai", project_key="proj-test")
        with patch.object(agent_batch_api, "run_agent_batch_nl_command_loop", side_effect=RuntimeError("loop exploded")):
            with self.assertRaises(HTTPException) as ctx:
                agent_batch_api.run_agent_batch_nl_command(payload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("loop exploded", ctx.exception.detail["error"]["message"])

    def test_resolve_item_key_missing_identifiers_raises_structured_invalid_input(self):
        job = agent_batch_api.AgentBatchItemSubmit(item_id="missing-key")
        with self.assertRaises(HTTPException) as ctx:
            agent_batch_api._resolve_item_key(job)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["error"]["code"], ErrorCode.INVALID_INPUT.value)

    def test_submit_search_market_job_missing_query_terms_raises_structured_invalid_input(self):
        job = agent_batch_api.AgentBatchItemSubmit(item_id="market-1", channel="search.market", query_terms=[])
        with self.assertRaises(HTTPException) as ctx:
            agent_batch_api._submit_search_market_job(
                job,
                project_key="proj-test",
                lane="main",
                trace_id="trace-1",
                workflow_run_id="run-1",
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("query_terms", ctx.exception.detail["error"]["message"])

    def test_submit_batch_item_without_submitter_raises_structured_invalid_input(self):
        job = agent_batch_api.AgentBatchItemSubmit(item_id="m1", channel="search.market", query_terms=["ai"])
        with patch.dict(agent_batch_api._CHANNEL_EXECUTION_REGISTRY, {}, clear=True):
            with self.assertRaises(HTTPException) as ctx:
                agent_batch_api._submit_batch_item(
                    job,
                    project_key="proj-test",
                    priority=None,
                    trace_id="trace-1",
                    workflow_run_id="run-1",
                )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("channel has no submit handler", ctx.exception.detail["error"]["message"])

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
