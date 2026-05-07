from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit

try:
    from app.api import agent_batch as agent_batch_api
    from app.services.agent_batch.agent_loop import run_agent_batch_nl_command_loop
except Exception as exc:  # pragma: no cover - dependency/import guard
    agent_batch_api = None  # type: ignore[assignment]
    run_agent_batch_nl_command_loop = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class AgentBatchLoopUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"agent batch loop unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_nl_command_dry_run_contains_loop_metadata(self):
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="search ai infra trend last 7 days top 6",
            project_key="proj-loop",
            dry_run=True,
        )
        skill_text = (
            '{"intent":"market_news","strategy":"single_query","tasks":[{"channel":"search.market",'
            '"query_terms":["ai infra trend"],"max_items":6,"provider":"auto","language":"en","days_back":7}]}'
        )
        with patch(
            "app.services.agent_batch.agent_loop.invoke_skill_safe",
            return_value={"ok": True, "result": {"result": {"text": skill_text}}, "error": None},
        ), patch.object(
            agent_batch_api,
            "plan_batch_search_command",
            return_value={
                "intent": "market_news",
                "strategy": "single_query",
                "tasks": [
                    {
                        "channel": "search.market",
                        "query_terms": ["ai infra trend"],
                        "max_items": 6,
                        "provider": "auto",
                        "language": "en",
                        "days_back": 7,
                    }
                ],
                "loop": {
                    "iteration": 1,
                    "planner": "skill",
                    "planner_path": "skill_planner",
                    "degradation_flags": [],
                },
            },
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        self.assertTrue(resp["data"]["dry_run"])
        self.assertIn("loop", resp["data"]["plan"])
        self.assertEqual(resp["data"]["plan"]["loop"]["planner"], "skill")
        self.assertEqual(resp["data"]["plan"]["loop"]["iteration"], 1)
        self.assertEqual(resp["data"]["plan"]["contract_version"], "agent_batch_planner.contract.v1")
        self.assertEqual(resp["data"]["plan"]["prompt_id"], "agent_batch_planner.v1")

    def test_nl_command_plan_exposes_loop_strategy_adjustment_fields(self):
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="search ai terminal market signals last 14 days top 20",
            project_key="proj-loop",
            dry_run=True,
        )
        skill_text = (
            '{"intent":"market_news","strategy":"parallel_by_query_term","tasks":[{"channel":"search.market",'
            '"query_terms":["ai terminal market signals"],"max_items":20,"provider":"auto","language":"en","days_back":14}]}'
        )
        with patch(
            "app.services.agent_batch.agent_loop.invoke_skill_safe",
            return_value={"ok": True, "result": {"result": {"text": skill_text}}, "error": None},
        ), patch.object(
            agent_batch_api,
            "plan_batch_search_command",
            return_value={
                "intent": "market_news",
                "strategy": "parallel_by_query_term",
                "tasks": [
                    {
                        "channel": "search.market",
                        "query_terms": ["ai terminal market signals"],
                        "max_items": 20,
                        "provider": "auto",
                        "language": "en",
                        "days_back": 14,
                    }
                ],
                "loop": {
                    "planner": "skill",
                    "planner_path": "skill_planner",
                    "degradation_flags": [],
                },
                "strategy_adjustments": {
                    "parallelism": 4,
                    "provider_policy": "stable",
                    "retry_backoff_seconds": 2,
                },
            },
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        self.assertIn("strategy_adjustments", resp["data"]["plan"])
        self.assertIn("parallelism", resp["data"]["plan"]["strategy_adjustments"])
        self.assertIn("provider_policy", resp["data"]["plan"]["strategy_adjustments"])
        self.assertIn("search_brief", resp["data"]["plan"])
        brief = resp["data"]["plan"]["search_brief"]
        self.assertEqual(brief["intent"], "market_news")
        self.assertEqual(brief["goal"], payload.command)
        self.assertEqual(brief["time_strategy"]["mode"], "recent")
        self.assertEqual(brief["time_strategy"]["days_back"], 14)
        self.assertEqual(brief["search_strategies"][0]["label"], "broad")
        self.assertEqual(brief["search_strategies"][0]["query_terms"], ["ai terminal market signals"])
        self.assertFalse(brief["source_preferences"]["attach_source_library"])
        self.assertIn("search_critic", resp["data"]["plan"])
        critic = resp["data"]["plan"]["search_critic"]
        self.assertEqual(critic["next_action"], "retry_with_source_library")
        self.assertIn("source_backing_missing", critic["reason_codes"])
        self.assertNotIn("rewrite", critic)
        stage_names = [str(x.get("name") or "") for x in list(resp["data"].get("stages") or [])]
        self.assertIn("search_brief", stage_names)
        self.assertIn("search_critic", stage_names)

    def test_nl_command_skill_invalid_json_sets_stable_fallback_reason_code(self):
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="search ai terminal market signals last 14 days top 20",
            project_key="proj-loop",
            dry_run=True,
        )
        with patch(
            "app.services.agent_batch.agent_loop.invoke_skill_safe",
            return_value={"ok": True, "result": {"result": {"text": "not-json"}}, "error": None},
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        loop_meta = resp["data"]["plan"]["loop"]
        self.assertEqual(loop_meta["planner"], "rule")
        self.assertEqual(loop_meta["fallback_reason_code"], "skill_planner_invalid_json")

    def test_nl_command_autonomously_adds_source_library_tasks(self):
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="请帮我搜集一些关于智能终端商业产品和公司的资料",
            project_key="proj-loop",
            dry_run=True,
        )
        skill_text = (
            '{"intent":"market_research_general","strategy":"single_query","tasks":[{"channel":"search.market",'
            '"query_terms":["智能终端 商业产品 公司"],"max_items":10,"provider":"auto","language":"zh","days_back":30}]}'
        )
        with patch(
            "app.services.agent_batch.agent_loop.invoke_skill_safe",
            return_value={"ok": True, "result": {"result": {"text": skill_text}}, "error": None},
        ), patch(
            "app.services.agent_batch.agent_loop._list_effective_source_items",
            return_value=[
                {
                    "item_key": "ai_terminal.weekly",
                    "name": "智能终端周报",
                    "channel_key": "handler.cluster",
                    "description": "跟踪智能终端公司与产品动态",
                    "enabled": True,
                    "tags": ["智能终端", "公司", "产品"],
                    "params": {
                        "site_entries": ["https://example.com/search?q={{q}}"],
                        "expected_entry_type": "search_template",
                    },
                },
                {
                    "item_key": "robotics.market_watch",
                    "name": "机器人商业观察",
                    "channel_key": "handler.cluster",
                    "description": "人形机器人与终端商业化",
                    "enabled": True,
                    "tags": ["商业", "案例"],
                    "params": {
                        "site_entries": ["https://example.org/rss"],
                        "expected_entry_type": "rss",
                    },
                },
            ],
        ), patch(
            "app.services.agent_batch.agent_loop._build_channel_capability_index",
            return_value={
                "policy.general": {"channel_key": "policy.general", "provider": "policy", "credential_refs": ["LEGISCAN_API_KEY"]},
                "handler.cluster": {"channel_key": "handler.cluster", "provider": "handler", "credential_refs": []},
            },
        ), patch(
            "app.services.agent_batch.agent_loop._is_item_credentials_ready",
            side_effect=lambda **kwargs: str(kwargs.get("row", {}).get("item_key")) != "policy.general.default",
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        self.assertTrue(resp["data"]["dry_run"])
        tasks = list(resp["data"]["plan"].get("tasks") or [])
        self.assertEqual(len(tasks), 3)
        channels = [str(x.get("channel") or "") for x in tasks]
        self.assertEqual(channels.count("search.market"), 1)
        self.assertEqual(channels.count("source_library"), 2)
        brief = resp["data"]["plan"]["search_brief"]
        self.assertEqual(brief["goal"], payload.command)
        self.assertIn("products", brief["coverage_axes"])
        self.assertIn("companies", brief["coverage_axes"])
        self.assertTrue(brief["source_preferences"]["attach_source_library"])
        self.assertEqual(brief["source_preferences"]["candidate_items"], ["ai_terminal.weekly", "robotics.market_watch"])
        self.assertEqual(brief["time_strategy"]["days_back"], 30)
        self.assertEqual(brief["stop_conditions"]["max_search_rounds"], 2)
        self.assertIn("search_critic", resp["data"]["plan"])
        critic = resp["data"]["plan"]["search_critic"]
        self.assertEqual(critic["next_action"], "stop")
        self.assertIn("coverage_sufficient", critic["reason_codes"])
        self.assertGreaterEqual(float(critic["coverage"]["source_diversity"]), 0.8)
        stage_names = [str(x.get("name") or "") for x in list(resp["data"].get("stages") or [])]
        self.assertIn("search_brief", stage_names)
        self.assertIn("search_critic", stage_names)
        self.assertIn("autonomous_mix", stage_names)
        source_keys = [str(x.get("item_key") or "") for x in tasks if str(x.get("channel") or "") == "source_library"]
        self.assertEqual(source_keys, ["ai_terminal.weekly", "robotics.market_watch"])
        for source_task in [x for x in tasks if str(x.get("channel") or "") == "source_library"]:
            self.assertEqual(source_task["query_terms"], ["智能终端 商业产品 公司"])

    def test_nl_command_autonomous_source_prefers_site_constrained_items(self):
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="搜集智能终端公司动态",
            project_key="proj-loop",
            dry_run=True,
        )
        skill_text = (
            '{"intent":"market_research_general","strategy":"single_query","tasks":[{"channel":"search.market",'
            '"query_terms":["智能终端 公司 动态"],"max_items":10,"provider":"auto","language":"zh","days_back":30}]}'
        )
        with patch(
            "app.services.agent_batch.agent_loop.invoke_skill_safe",
            return_value={"ok": True, "result": {"result": {"text": skill_text}}, "error": None},
        ), patch(
            "app.services.agent_batch.agent_loop._list_effective_source_items",
            return_value=[
                {
                    "item_key": "policy.general.default",
                    "name": "政策通道默认项",
                    "channel_key": "policy.general",
                    "enabled": True,
                    "params": {"state": "NY"},
                },
                {
                    "item_key": "handler.cluster.search_template",
                    "name": "站点检索模板",
                    "channel_key": "handler.cluster",
                    "enabled": True,
                    "params": {
                        "site_entries": ["https://example.com/search?q={{q}}"],
                        "expected_entry_type": "search_template",
                    },
                },
            ],
        ), patch(
            "app.services.agent_batch.agent_loop._build_channel_capability_index",
            return_value={
                "policy.general": {"channel_key": "policy.general", "provider": "policy", "credential_refs": ["LEGISCAN_API_KEY"]},
                "handler.cluster": {"channel_key": "handler.cluster", "provider": "handler", "credential_refs": []},
            },
        ), patch(
            "app.services.agent_batch.agent_loop._is_item_credentials_ready",
            side_effect=lambda **kwargs: str(kwargs.get("row", {}).get("item_key")) != "policy.general.default",
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        tasks = list(resp["data"]["plan"].get("tasks") or [])
        source_tasks = [x for x in tasks if str(x.get("channel") or "") == "source_library"]
        self.assertEqual(len(source_tasks), 1)
        self.assertEqual(str(source_tasks[0].get("item_key") or ""), "handler.cluster.search_template")

    def test_normalize_tasks_uses_shared_source_library_defaults(self):
        from app.services.agent_batch.agent_loop import _normalize_tasks

        tasks = _normalize_tasks(
            [
                {
                    "channel": "source_library",
                    "item_key": "ai_terminal.weekly",
                }
            ],
            command="搜集智能终端资料",
        )

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["max_items"], 20)
        self.assertEqual(tasks[0]["provider"], "auto")
        self.assertIsNone(tasks[0]["source_mode"])

    def test_planner_prompt_contains_task_manifest(self):
        from app.services.agent_batch.agent_loop import _build_planner_prompt

        prompt = _build_planner_prompt("search ai infra updates last 7 days")
        self.assertIn("TASK_MANIFEST:", prompt)
        self.assertIn('"channel":"search.market"', prompt)
        self.assertIn('"channel":"source_library"', prompt)

    def test_discover_source_items_balances_capability_categories_and_skips_api_without_credentials(self):
        from app.services.agent_batch import agent_loop

        with patch.object(
            agent_loop,
            "_list_effective_source_items",
            return_value=[
                {
                    "item_key": "policy.general.default",
                    "name": "policy",
                    "channel_key": "policy.general",
                    "enabled": True,
                    "params": {"state": "NY"},
                },
                {
                    "item_key": "market.general.baseline",
                    "name": "market",
                    "channel_key": "market.general",
                    "enabled": True,
                    "params": {"keywords": ["market trend"]},
                },
                {
                    "item_key": "handler.cluster.search_template",
                    "name": "handler search",
                    "channel_key": "handler.cluster",
                    "enabled": True,
                    "params": {
                        "site_entries": ["https://example.com/search?q={{q}}"],
                        "expected_entry_type": "search_template",
                    },
                },
            ],
        ), patch.object(
            agent_loop,
            "_build_channel_capability_index",
            return_value={
                "policy.general": {"channel_key": "policy.general", "provider": "policy", "credential_refs": ["LEGISCAN_API_KEY"]},
                "market.general": {"channel_key": "market.general", "provider": "market", "credential_refs": []},
                "handler.cluster": {"channel_key": "handler.cluster", "provider": "handler", "credential_refs": []},
            },
        ), patch.object(
            agent_loop,
            "_is_item_credentials_ready",
            side_effect=lambda **kwargs: str(kwargs.get("row", {}).get("item_key")) != "policy.general.default",
        ):
            keys = agent_loop._discover_source_library_item_keys(project_key="proj-loop", limit=2)

        self.assertEqual(keys, ["handler.cluster.search_template", "market.general.baseline"])

    def test_discover_source_items_prefers_goal_relevant_collect_sources(self):
        from app.services.agent_batch import agent_loop

        with patch.object(
            agent_loop,
            "_list_effective_source_items",
            return_value=[
                {
                    "item_key": "handler.cluster.domain_root",
                    "name": "General domain roots",
                    "channel_key": "handler.cluster",
                    "enabled": True,
                    "params": {
                        "site_entries": ["https://example.com/"],
                        "expected_entry_type": "domain_root",
                    },
                },
                {
                    "item_key": "report1.high_value_urls",
                    "name": "High value static URLs",
                    "channel_key": "url_pool",
                    "enabled": True,
                    "params": {
                        "urls": ["https://example.com/unrelated-review"],
                    },
                },
                {
                    "item_key": "robotics.market_watch",
                    "name": "Embodied AI Robotics Market Watch",
                    "description": "Commercial robotics product launches and embodied AI company news",
                    "channel_key": "handler.cluster",
                    "enabled": True,
                    "tags": ["robotics", "embodied ai", "commercialization"],
                    "params": {
                        "site_entries": ["https://robotics.example.com/search?q={{q}}"],
                        "expected_entry_type": "search_template",
                    },
                },
                {
                    "item_key": "robotics.rss",
                    "name": "Robotics Commercialization RSS",
                    "description": "Robotics funding and product launch feeds",
                    "channel_key": "handler.cluster",
                    "enabled": True,
                    "tags": ["robotics", "funding"],
                    "params": {
                        "site_entries": ["https://robotics.example.com/feed.xml"],
                        "expected_entry_type": "rss",
                    },
                },
            ],
        ), patch.object(
            agent_loop,
            "_build_channel_capability_index",
            return_value={
                "handler.cluster": {"channel_key": "handler.cluster", "provider": "handler", "credential_refs": []},
                "url_pool": {"channel_key": "url_pool", "provider": "url_pool", "credential_refs": []},
            },
        ), patch.object(
            agent_loop,
            "_is_item_credentials_ready",
            return_value=True,
        ):
            keys = agent_loop._discover_source_library_item_keys(
                project_key="proj-loop",
                limit=2,
                command="search embodied ai robotics commercialization companies product latest news",
                tasks=[
                    {
                        "channel": "search.market",
                        "query_terms": ["embodied ai robotics commercialization companies product latest news"],
                    }
                ],
            )

        self.assertEqual(keys, ["robotics.market_watch", "robotics.rss"])

    def test_loop_schedules_single_retry_round_when_enabled(self):
        submit_calls: list[dict[str, object]] = []

        def _submitter(tasks, project_key, idempotency_key):
            submit_calls.append(
                {
                    "tasks": [dict(task) for task in tasks],
                    "project_key": project_key,
                    "idempotency_key": idempotency_key,
                }
            )
            return {
                "job_id": f"abj-{len(submit_calls)}",
                "accepted_count": len(tasks),
                "rejected_count": 0,
                "status": "ok",
            }

        skill_text = (
            '{"intent":"market_news","strategy":"single_query","tasks":[{"channel":"search.market",'
            '"query_terms":["chip pricing regulation"],"max_items":6,"provider":"auto","language":"en","days_back":120}]}'
        )
        with patch(
            "app.services.agent_batch.agent_loop.invoke_skill_safe",
            return_value={"ok": True, "result": {"result": {"text": skill_text}}, "error": None},
        ):
            result = run_agent_batch_nl_command_loop(
                command="search chip pricing regulation last 120 days top 6",
                project_key="proj-loop",
                idempotency_key="idem-loop",
                dry_run=False,
                enable_bounded_retry=True,
                enable_limited_branching=False,
                parser_fallback=lambda _command: {
                    "intent": "market_news",
                    "strategy": "single_query",
                    "tasks": [
                        {
                            "channel": "search.market",
                            "query_terms": ["chip pricing regulation"],
                            "max_items": 6,
                            "provider": "auto",
                            "language": "en",
                            "days_back": 120,
                        }
                    ],
                },
                submitter=_submitter,
                executor_snapshot=lambda: {"worker_online": True, "workers": ["celery@test"]},
            )

        self.assertEqual(len(submit_calls), 2)
        self.assertEqual(result["submit"]["job_id"], "abj-2")
        self.assertEqual(len(result["submit_rounds"]), 2)
        self.assertTrue(result["plan"]["search_retry"]["scheduled"])
        self.assertEqual(result["plan"]["search_retry"]["action"]["action"], "narrow_query_terms")
        self.assertEqual(result["plan"]["search_retry"]["round"], 2)
        self.assertTrue(str(submit_calls[1]["idempotency_key"]).endswith(":retry:2"))
        retried_tasks = list(submit_calls[1]["tasks"])
        self.assertEqual(retried_tasks[0]["days_back"], 120)
        self.assertNotEqual(retried_tasks[0]["query_terms"], ["chip pricing regulation"])

    def test_loop_retries_source_library_when_source_gap_score_is_above_threshold(self):
        submit_calls: list[dict[str, object]] = []

        def _submitter(tasks, project_key, idempotency_key):
            submit_calls.append(
                {
                    "tasks": [dict(task) for task in tasks],
                    "project_key": project_key,
                    "idempotency_key": idempotency_key,
                }
            )
            return {
                "job_id": f"abj-{len(submit_calls)}",
                "accepted_count": len(tasks),
                "rejected_count": 0,
                "status": "ok",
            }

        skill_text = (
            '{"intent":"market_research_general","strategy":"single_query","constraints":{"retrieval_mode":"web_only"},'
            '"tasks":[{"channel":"search.market",'
            '"query_terms":["embodied ai robotics commercialization companies product latest news"],'
            '"max_items":3,"provider":"auto","language":"en","days_back":7}]}'
        )
        with patch(
            "app.services.agent_batch.agent_loop.invoke_skill_safe",
            return_value={"ok": True, "result": {"result": {"text": skill_text}}, "error": None},
        ), patch(
            "app.services.agent_batch.agent_loop._list_effective_source_items",
            return_value=[
                {
                    "item_key": "robotics.market_watch",
                    "name": "Robotics Market Watch",
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
            return_value={
                "handler.cluster": {
                    "channel_key": "handler.cluster",
                    "provider": "handler",
                    "credential_refs": [],
                }
            },
        ), patch(
            "app.services.agent_batch.agent_loop._is_item_credentials_ready",
            return_value=True,
        ):
            result = run_agent_batch_nl_command_loop(
                command="search embodied ai robotics commercialization companies product latest news last 7 days top 3",
                project_key="proj-loop",
                idempotency_key="idem-loop",
                dry_run=False,
                enable_bounded_retry=True,
                enable_limited_branching=False,
                parser_fallback=lambda _command: {
                    "intent": "market_research_general",
                    "strategy": "single_query",
                    "tasks": [
                        {
                            "channel": "search.market",
                            "query_terms": ["embodied ai robotics commercialization companies product latest news"],
                            "max_items": 3,
                            "provider": "auto",
                            "language": "en",
                            "days_back": 7,
                        }
                    ],
                },
                submitter=_submitter,
                executor_snapshot=lambda: {"worker_online": True, "workers": ["celery@test"]},
            )

        search_retry = result["plan"]["search_retry"]
        self.assertGreaterEqual(search_retry["score"], search_retry["score_threshold"])
        self.assertTrue(search_retry["scheduled"])
        self.assertTrue(search_retry["threshold_bypassed"])
        self.assertEqual(search_retry["threshold_bypass_reason"], "source_backing_missing")
        self.assertEqual(search_retry["action"]["action"], "attach_source_library")
        self.assertEqual(len(submit_calls), 2)
        self.assertEqual(len(result["submit_rounds"]), 2)
        retried_tasks = list(submit_calls[1]["tasks"])
        source_tasks = [task for task in retried_tasks if str(task.get("channel") or "") == "source_library"]
        self.assertEqual(len(source_tasks), 1)
        self.assertEqual(source_tasks[0]["item_key"], "robotics.market_watch")
        self.assertEqual(source_tasks[0]["max_items"], 3)
        self.assertEqual(source_tasks[0]["query_terms"], ["embodied ai robotics commercialization companies product latest news"])
        self.assertIsNone(source_tasks[0]["source_mode"])
        self.assertTrue(str(submit_calls[1]["idempotency_key"]).endswith(":retry:2"))

    def test_loop_skips_retry_when_critic_recommends_stop(self):
        submit_calls: list[dict[str, object]] = []

        def _submitter(tasks, project_key, idempotency_key):
            submit_calls.append(
                {
                    "tasks": [dict(task) for task in tasks],
                    "project_key": project_key,
                    "idempotency_key": idempotency_key,
                }
            )
            return {
                "job_id": f"abj-{len(submit_calls)}",
                "accepted_count": len(tasks),
                "rejected_count": 0,
                "status": "ok",
            }

        skill_text = (
            '{"intent":"market_news","strategy":"single_query","tasks":[{"channel":"search.market",'
            '"query_terms":["ai market overview"],"max_items":6,"provider":"auto","language":"en","days_back":14}]}'
        )
        with patch(
            "app.services.agent_batch.agent_loop.invoke_skill_safe",
            return_value={"ok": True, "result": {"result": {"text": skill_text}}, "error": None},
        ):
            result = run_agent_batch_nl_command_loop(
                command="search ai market overview last 14 days top 6",
                project_key="proj-loop",
                idempotency_key="idem-loop",
                dry_run=False,
                enable_bounded_retry=True,
                enable_limited_branching=False,
                parser_fallback=lambda _command: {
                    "intent": "market_news",
                    "strategy": "single_query",
                    "tasks": [
                        {
                            "channel": "search.market",
                            "query_terms": ["ai market overview"],
                            "max_items": 6,
                            "provider": "auto",
                            "language": "en",
                            "days_back": 14,
                        }
                    ],
                },
                submitter=_submitter,
                executor_snapshot=lambda: {"worker_online": True, "workers": ["celery@test"]},
            )

        self.assertEqual(len(submit_calls), 1)
        self.assertFalse(result["plan"]["search_retry"]["scheduled"])
        self.assertEqual(result["plan"]["search_retry"]["skip_reason"], "critic_stop")
        self.assertEqual(len(result["submit_rounds"]), 1)

    def test_nl_command_can_enable_default_off_limited_branching_for_high_ambiguity_prompt(self):
        payload = agent_batch_api.AgentBatchNlCommandRequest(
            command="search ai terminal products companies web only last 30 days top 10",
            project_key="proj-loop",
            dry_run=True,
            enable_limited_branching=True,
        )
        skill_text = (
            '{"intent":"market_research_general","strategy":"single_query","constraints":{"retrieval_mode":"web_only"},'
            '"tasks":[{"channel":"search.market","query_terms":["ai terminal products companies"],'
            '"max_items":10,"provider":"auto","language":"en","days_back":30}]}'
        )
        with patch(
            "app.services.agent_batch.agent_loop.invoke_skill_safe",
            return_value={"ok": True, "result": {"result": {"text": skill_text}}, "error": None},
        ), patch.object(
            agent_batch_api,
            "inspect_executor_health",
            return_value={"worker_online": True, "workers": ["celery@test"]},
        ):
            resp = agent_batch_api.run_agent_batch_nl_command(payload)

        self.assertEqual(resp["status"], "ok")
        self.assertIn("branching", resp["data"]["plan"])
        branching = resp["data"]["plan"]["branching"]
        self.assertTrue(branching["enabled"])
        self.assertEqual(branching["branch_count"], 2)
        self.assertEqual(branching["strategy_labels"], ["broad", "precision"])
        tasks = list(resp["data"]["plan"].get("tasks") or [])
        self.assertEqual(len(tasks), 2)
        self.assertNotEqual(tasks[0]["query_terms"], tasks[1]["query_terms"])
        stage_names = [str(x.get("name") or "") for x in list(resp["data"].get("stages") or [])]
        self.assertIn("branching", stage_names)


if __name__ == "__main__":
    unittest.main()
