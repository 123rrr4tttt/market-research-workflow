from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit

try:
    from app.api import agent_batch as agent_batch_api
except Exception as exc:  # pragma: no cover - dependency/import guard
    agent_batch_api = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class _DelayTaskStub:
    def __init__(self):
        self.calls: list[tuple[str, str | None, dict]] = []

    def delay(self, item_key: str, project_key: str | None, override_params: dict):
        task_id = f"task-{len(self.calls) + 1}"
        self.calls.append((item_key, project_key, dict(override_params or {})))
        return SimpleNamespace(id=task_id)


class _MarketDelayTaskStub:
    def __init__(self):
        self.calls: list[tuple[list[str], int, bool, str | None, None, int | None, str | None, str | None]] = []

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
    ):
        task_id = f"mkt-{len(self.calls) + 1}"
        self.calls.append((list(query_terms), max_items, enable_extraction, project_key, start_offset, days_back, language, provider))
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
        self.assertEqual([x["task_id"] for x in first["data"]["accepted_job_items"]], ["task-1", "task-2"])
        self.assertEqual(second["status"], "ok")
        self.assertTrue(second["data"]["idempotency_reused"])
        self.assertEqual(second["data"]["accepted_count"], 2)
        self.assertEqual(len(delay_stub.calls), 2)

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
        self.assertEqual(job["data"]["progress"], {"total": 2, "succeeded": 1, "failed": 1, "running": 0, "queued": 0})
        self.assertEqual(items["status"], "ok")
        self.assertEqual(len(items["data"]["items"]), 2)
        self.assertEqual(items["data"]["items"][0]["output"], {"doc_id": 101})
        self.assertEqual(items["data"]["items"][1]["error"], "boom")
        self.assertEqual(events["status"], "ok")
        self.assertEqual([e["event_type"] for e in events["data"]["events"]], ["task.success", "task.failure"])

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

    def test_nl_command_dispatches_search_market_batch(self):
        market_delay_stub = _MarketDelayTaskStub()
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="采集最近14天美国在线彩票市场新闻和监管政策，前30条",
            project_key="proj-nl",
            idempotency_key="idem-nl-1",
        )
        with patch.object(agent_batch_api.tasks_module, "task_ingest_market", market_delay_stub):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        parsed = resp["data"]["parsed"]
        self.assertEqual(parsed["channel"], "search.market")
        self.assertEqual(parsed["days_back"], 14)
        self.assertEqual(parsed["max_items"], 30)
        self.assertEqual(parsed["language"], "zh")
        self.assertEqual(resp["data"]["submit"]["accepted_count"], 1)
        self.assertEqual(resp["data"]["submit"]["accepted_job_items"][0]["task_id"], "mkt-1")
        self.assertEqual(len(market_delay_stub.calls), 1)


if __name__ == "__main__":
    unittest.main()
