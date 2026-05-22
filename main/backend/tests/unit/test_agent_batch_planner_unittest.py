from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from app.services.agent_batch.planner import (
    AGENT_BATCH_TASK_MANIFEST_VERSION,
    REASON_SKILL_PLAN_EMPTY_TASKS,
    REASON_SKILL_PLAN_SCHEMA_INVALID,
    build_agent_batch_task_manifest,
    plan_batch_search_command,
    validate_skill_planner_contract,
)
from app.services.agent_batch.task_contract import build_agent_batch_manifest_entry
from app.services.agent_batch.task_contract import build_agent_batch_approval_argv
from app.services.agent_batch.task_contract import build_agent_batch_dispatch_invocation
from app.services.agent_batch.task_contract import build_agent_batch_execution_registry
from app.services.agent_batch.task_contract import build_agent_batch_submit_item_data
from app.services.agent_batch.task_contract import build_live_quality_threshold_schema
from app.services.agent_batch.task_contract import build_retry_action_schema
from app.services.agent_batch.task_contract import build_search_brief_schema
from app.services.agent_batch.task_contract import build_search_critic_schema
from app.services.agent_batch.task_contract import build_search_quality_replay_schema
from app.services.agent_batch.task_contract import build_search_policy_contract
from app.services.agent_batch.task_contract import build_source_library_override_params
from app.services.agent_batch.task_contract import get_retry_action_allowed_fields
from app.services.agent_batch.task_contract import get_retry_action_required_fields
from app.services.agent_batch.task_contract import get_rewrite_eligible_fields_by_channel
from app.services.agent_batch.task_contract import get_search_policy_defaults
from app.services.agent_batch.task_contract import infer_agent_batch_channel
from app.services.agent_batch.task_contract import list_agent_batch_execution_bindings
from app.services.agent_batch.task_contract import list_agent_batch_dispatch_skill_bindings
from app.services.agent_batch.task_contract import list_search_policy_event_names
from app.services.agent_batch.task_contract import normalize_agent_batch_task
from app.services.agent_batch.task_contract import resolve_agent_batch_lane
from app.services.agent_batch.task_contract import validate_retry_action_payload

pytestmark = pytest.mark.unit


class AgentBatchPlannerUnitTest(unittest.TestCase):
    def test_plan_zh_command_parses_constraints_and_strips_boilerplate(self):
        command = "请帮我搜索最近14天美国在线彩票市场新闻和监管政策，前30条，优先google和serper"

        plan = plan_batch_search_command(command)

        self.assertEqual(plan["intent"], "regulatory_monitoring")
        self.assertEqual(plan["strategy"], "parallel_by_query_term")
        self.assertEqual(plan["constraints"]["max_items"], 30)
        self.assertEqual(plan["constraints"]["days_back"], 14)
        self.assertEqual(plan["constraints"]["provider_hints"], ["google", "serper"])
        self.assertGreaterEqual(len(plan["tasks"]), 2)

        for task in plan["tasks"]:
            self.assertEqual(task["channel"], "search.market")
            self.assertEqual(task["max_items"], 30)
            self.assertEqual(task["days_back"], 14)
            self.assertEqual(task["language"], "zh")
            term = task["query_terms"][0]
            self.assertNotIn("请帮我", term)
            self.assertNotEqual(term, command)

    def test_plan_en_command_parses_provider_and_limits(self):
        command = "Please help me find last 7 days AI chip supply chain updates and pricing trends, top 12 results via ddg"

        plan = plan_batch_search_command(command)

        self.assertEqual(plan["intent"], "pricing_research")
        self.assertEqual(plan["constraints"]["max_items"], 12)
        self.assertEqual(plan["constraints"]["days_back"], 7)
        self.assertEqual(plan["constraints"]["provider_hints"], ["ddg"])
        self.assertGreaterEqual(len(plan["tasks"]), 2)
        self.assertTrue(any("chip supply chain" in task["query_terms"][0].lower() for task in plan["tasks"]))
        self.assertFalse(any(task["query_terms"][0].lower() == "ddg" for task in plan["tasks"]))

    def test_plan_is_deterministic(self):
        command = "帮我找过去30天电动车价格变化和竞品动态，最多15条"

        first = plan_batch_search_command(command)
        second = plan_batch_search_command(command)

        self.assertEqual(first, second)

    def test_plan_fallback_when_command_has_only_boilerplate(self):
        plan = plan_batch_search_command("请帮我搜索一下")

        self.assertEqual(plan["intent"], "market_research_general")
        self.assertEqual(plan["constraints"]["max_items"], None)
        self.assertEqual(plan["constraints"]["days_back"], None)
        self.assertEqual(plan["tasks"][0]["query_terms"], ["市场研究"])
        self.assertEqual(plan["strategy"], "single_query")

    def test_plan_clamps_limits_to_supported_ranges(self):
        plan = plan_batch_search_command("search last 999 days battery recycling news, top 999 results")

        self.assertEqual(plan["constraints"]["days_back"], 365)
        self.assertEqual(plan["constraints"]["max_items"], 100)
        self.assertEqual(plan["tasks"][0]["max_items"], 100)

    def test_validate_skill_planner_contract_rejects_invalid_schema(self):
        _, reason_code = validate_skill_planner_contract({"intent": "x", "tasks": "not-list"})
        self.assertEqual(reason_code, REASON_SKILL_PLAN_SCHEMA_INVALID)

    def test_validate_skill_planner_contract_rejects_empty_tasks(self):
        _, reason_code = validate_skill_planner_contract({"intent": "x", "strategy": "s", "tasks": []})
        self.assertEqual(reason_code, REASON_SKILL_PLAN_EMPTY_TASKS)

    def test_validate_skill_planner_contract_accepts_valid_search_tasks(self):
        normalized, reason_code = validate_skill_planner_contract(
            {
                "intent": "market_news",
                "strategy": "single_query",
                "tasks": [{"channel": "search.market", "query_terms": ["ai market"], "max_items": 5}],
            }
        )
        self.assertIsNone(reason_code)
        self.assertEqual(normalized["tasks"][0]["channel"], "search.market")
        self.assertEqual(normalized["tasks"][0]["query_terms"], ["ai market"])

    def test_validate_skill_planner_contract_accepts_valid_source_library_tasks(self):
        normalized, reason_code = validate_skill_planner_contract(
            {
                "intent": "market_news",
                "strategy": "single_query",
                "tasks": [{"channel": "source_library", "item_key": "ai_terminal.weekly"}],
            }
        )
        self.assertIsNone(reason_code)
        self.assertEqual(normalized["tasks"][0]["channel"], "source_library")
        self.assertEqual(normalized["tasks"][0]["item_key"], "ai_terminal.weekly")
        self.assertEqual(normalized["tasks"][0]["max_items"], 20)
        self.assertIsNone(normalized["tasks"][0]["source_mode"])

    def test_task_manifest_exposes_callable_channels(self):
        manifest = build_agent_batch_task_manifest()
        self.assertEqual(manifest["manifest_version"], AGENT_BATCH_TASK_MANIFEST_VERSION)
        channels = [item["channel"] for item in manifest["callable_tasks"]]
        self.assertIn("search.market", channels)
        self.assertIn("source_library", channels)
        by_channel = {item["channel"]: item for item in manifest["callable_tasks"]}
        self.assertIn("override_params_schema", by_channel["search.market"])
        self.assertIn("source_mode", by_channel["source_library"]["optional_keys"])
        self.assertIn("urls", by_channel["source_library"]["optional_keys"])
        self.assertIn("query_terms", by_channel["source_library"]["optional_keys"])

    def test_task_manifest_uses_registered_skill_overrides(self):
        with patch(
            "app.services.agent_batch.planner._collect_registered_agent_batch_task_manifest_entries",
            return_value=[
                {
                    "channel": "search.market",
                    "description": "runtime-registered description",
                    "defaults": {"max_items": 12, "provider": "auto"},
                }
            ],
        ):
            manifest = build_agent_batch_task_manifest()
        by_channel = {item["channel"]: item for item in manifest["callable_tasks"]}
        self.assertEqual(by_channel["search.market"]["description"], "runtime-registered description")
        self.assertEqual(by_channel["search.market"]["defaults"]["max_items"], 12)

    def test_search_policy_contract_is_frozen_in_shared_contract(self):
        brief_schema = build_search_brief_schema()
        self.assertEqual(brief_schema["artifact"], "search_brief")
        self.assertIn("search_strategies", brief_schema["required_keys"])
        self.assertEqual(brief_schema["stop_conditions_required_keys"], ["min_entity_count", "min_source_domains", "max_search_rounds"])

        critic_schema = build_search_critic_schema()
        self.assertEqual(critic_schema["artifact"], "search_critic")
        self.assertIn("score", critic_schema["required_keys"])
        self.assertIn("retry_with_source_library", critic_schema["next_action_allowed_values"])
        self.assertIn("novelty_gain", critic_schema["coverage_keys"])

        quality_replay_schema = build_search_quality_replay_schema()
        self.assertEqual(quality_replay_schema["artifact"], "search_quality_replay")
        self.assertIn("source_quality_signals", quality_replay_schema["required_keys"])
        self.assertIn("source_quality", quality_replay_schema["coverage_keys"])
        self.assertIn("quality_claim_allowed", quality_replay_schema["live_provider_gap_required_keys"])

        live_threshold_schema = build_live_quality_threshold_schema()
        self.assertEqual(live_threshold_schema["artifact"], "live_quality_threshold")
        self.assertIn("quality_thresholds", live_threshold_schema["required_keys"])
        self.assertIn("live_provider_replay_closed", live_threshold_schema["required_keys"])
        self.assertIn("min_relevance_score", live_threshold_schema["quality_threshold_required_keys"])
        self.assertIn("min_review_sample_count", live_threshold_schema["quality_threshold_required_keys"])

        retry_schema = build_retry_action_schema()
        self.assertEqual(retry_schema["artifact"], "retry_action")
        self.assertTrue(retry_schema["fail_closed"])
        self.assertIn("replace_source_library", retry_schema["allowed_actions"])
        self.assertEqual(retry_schema["required_rewrite_fields_by_action"]["shift_time_window"], ["days_back"])
        self.assertIn("item_key", retry_schema["allowed_rewrite_fields_by_action"]["attach_source_library"])

        rewrite_fields = get_rewrite_eligible_fields_by_channel()
        self.assertEqual(rewrite_fields["search.market"], ["query_terms", "max_items", "provider", "language", "days_back", "override_params"])
        self.assertIn("source_mode", rewrite_fields["source_library"])
        self.assertIn("item_key", rewrite_fields["source_library"])
        self.assertEqual(get_retry_action_allowed_fields("expand_query_terms", "search.market"), ["query_terms", "max_items", "override_params"])
        self.assertEqual(get_retry_action_required_fields("attach_source_library", "source_library"), ["item_key"])
        self.assertEqual(get_retry_action_allowed_fields("change_provider", "source_library"), ["provider", "language", "override_params"])

        defaults = get_search_policy_defaults()
        self.assertEqual(defaults["retry_budget"], 1)
        self.assertEqual(defaults["max_retry_rounds"], 1)
        self.assertEqual(defaults["retry_score_threshold"], 0.72)
        self.assertFalse(defaults["branching_default_enabled"])
        self.assertEqual(defaults["critic_mode"], "observe_only")

        event_names = list_search_policy_event_names()
        self.assertEqual(
            event_names,
            [
                "search_brief.created",
                "search_round.completed",
                "search_critic.scored",
                "search_retry.scheduled",
                "search_retry.skipped",
                "search_stop.completed",
            ],
        )

        policy_contract = build_search_policy_contract()
        self.assertEqual(policy_contract["search_brief"], brief_schema)
        self.assertEqual(policy_contract["search_critic"], critic_schema)
        self.assertEqual(policy_contract["quality_replay"], quality_replay_schema)
        self.assertEqual(policy_contract["live_quality_threshold"], live_threshold_schema)
        self.assertEqual(policy_contract["retry_action"], retry_schema)
        self.assertEqual(policy_contract["rewrite_eligible_fields_by_channel"], rewrite_fields)
        self.assertEqual(policy_contract["defaults"], defaults)
        self.assertEqual(policy_contract["event_names"], event_names)

    def test_validate_retry_action_payload_normalizes_and_fail_closes(self):
        normalized, reason_code, details = validate_retry_action_payload(
            {
                "action": "expand_query_terms",
                "reason": "need broader recall",
                "channel": "search.market",
                "rewrite": {"query_terms": ["ai chips", "supply chain"], "max_items": "12"},
                "target_items": ["search_1", "search_1", "search_2"],
            }
        )
        self.assertIsNone(reason_code)
        self.assertEqual(details, {})
        self.assertEqual(normalized["rewrite"]["query_terms"], ["ai chips", "supply chain"])
        self.assertEqual(normalized["rewrite"]["max_items"], 12)
        self.assertEqual(normalized["target_items"], ["search_1", "search_2"])

        normalized, reason_code, details = validate_retry_action_payload(
            {
                "action": "expand_query_terms",
                "reason": "need broader recall",
                "channel": "search.market",
                "rewrite": {"item_key": "ai_terminal.weekly"},
            }
        )
        self.assertIsNone(normalized)
        self.assertEqual(reason_code, "retry_action_rewrite_fields_unsupported")
        self.assertEqual(details["unsupported_fields"], ["item_key"])

        normalized, reason_code, details = validate_retry_action_payload(
            {
                "action": "shift_time_window",
                "reason": "need newer content",
                "channel": "search.market",
                "rewrite": {},
            }
        )
        self.assertIsNone(normalized)
        self.assertEqual(reason_code, "retry_action_rewrite_fields_missing")
        self.assertEqual(details["missing_required_fields"], ["days_back"])

    def test_base_task_contract_entry_matches_planner_callable_task(self):
        manifest = build_agent_batch_task_manifest()
        by_channel = {item["channel"]: item for item in manifest["callable_tasks"]}
        self.assertEqual(by_channel["search.market"], build_agent_batch_manifest_entry("search.market"))
        self.assertEqual(by_channel["source_library"], build_agent_batch_manifest_entry("source_library"))

    def test_normalize_agent_batch_task_uses_contract_defaults(self):
        normalized = normalize_agent_batch_task({"channel": "source_library", "item_key": "demo.item"}, idx=1, default_language="zh")
        self.assertEqual(normalized["max_items"], 20)
        self.assertEqual(normalized["provider"], "auto")
        self.assertIsNone(normalized["source_mode"])
        self.assertEqual(normalized["language"], "zh")

    def test_build_source_library_override_params_promotes_top_level_fields(self):
        override_params = build_source_library_override_params(
            {
                "override_params": {},
                "query_terms": ["ai terminal"],
                "urls": ["https://example.com/a"],
                "max_items": 3,
                "provider": "google",
                "language": "zh",
                "scope": "project",
                "platforms": ["web", "rss"],
                "source_mode": "site_search",
            },
            workflow_run_id="run-1",
        )
        self.assertEqual(override_params["query_terms"], ["ai terminal"])
        self.assertEqual(override_params["urls"], ["https://example.com/a"])
        self.assertEqual(override_params["max_items"], 3)
        self.assertEqual(override_params["limit"], 3)
        self.assertEqual(override_params["provider"], "google")
        self.assertEqual(override_params["language"], "zh")
        self.assertEqual(override_params["scope"], "project")
        self.assertEqual(override_params["platforms"], ["web", "rss"])
        self.assertEqual(override_params["source_mode"], "site_search")
        self.assertEqual(override_params["workflow_run_id"], "run-1")

    def test_dispatch_bindings_and_helpers_come_from_shared_contract(self):
        bindings = {item["channel"]: item for item in list_agent_batch_dispatch_skill_bindings()}
        self.assertEqual(bindings["search.market"]["skill_id"], "agent_batch.dispatch.market_collect")
        self.assertEqual(bindings["source_library"]["handler_export"], "_skill_dispatch_source_library_item")

        execution_bindings = {item["channel"]: item for item in list_agent_batch_execution_bindings()}
        self.assertEqual(execution_bindings["search.market"]["submitter_export"], "_submit_search_market_job")
        self.assertEqual(execution_bindings["search.market"]["rule_guard_export"], "_enforce_search_market_rule_set")
        self.assertEqual(execution_bindings["source_library"]["submitter_export"], "_submit_source_library_job")

        search_invocation = build_agent_batch_dispatch_invocation(
            "search.market",
            {
                "query_terms": ["ai chips"],
                "max_items": 5,
                "project_key": "proj-1",
                "provider": "google",
            },
            trace_id=None,
        )
        self.assertEqual(search_invocation["skill_id"], "agent_batch.dispatch.market_collect")
        self.assertEqual(search_invocation["payload"]["channel"], "search.market")
        self.assertEqual(search_invocation["context"]["permissions"], ["agent_batch.dispatch.market_collect"])

        source_argv = build_agent_batch_approval_argv("source_library", {"item_key": "ai_terminal.weekly"})
        self.assertEqual(source_argv, ["task_run_source_library_item", "ai_terminal.weekly"])
        self.assertEqual(resolve_agent_batch_lane("source_library", 9), "subagent")
        self.assertEqual(resolve_agent_batch_lane("search.market", 9), "system")

    def test_build_agent_batch_submit_item_data_uses_shared_defaults(self):
        item = build_agent_batch_submit_item_data({"channel": "source_library", "item_key": "demo.item"}, idx=1, default_language="zh")
        self.assertEqual(item["channel"], "source_library")
        self.assertEqual(item["item_key"], "demo.item")
        self.assertEqual(item["max_items"], 20)
        self.assertEqual(item["provider"], "auto")
        self.assertIsNone(item["source_mode"])

    def test_build_agent_batch_execution_registry_resolves_exports_and_fails_fast(self):
        registry = build_agent_batch_execution_registry(
            execution_bindings=[
                {
                    "channel": "search.market",
                    "submitter_export": "submit_search",
                    "rule_guard_export": "guard_search",
                }
            ],
            globals_map={
                "submit_search": lambda *_args, **_kwargs: None,
                "guard_search": lambda *_args, **_kwargs: None,
            },
        )
        self.assertTrue(callable(registry["search.market"]["submitter"]))
        self.assertTrue(callable(registry["search.market"]["rule_guard"]))

        with self.assertRaises(RuntimeError):
            build_agent_batch_execution_registry(
                execution_bindings=[{"channel": "search.market", "submitter_export": "missing_submitter"}],
                globals_map={},
            )

    def test_infer_agent_batch_channel_requires_identifying_fields(self):
        self.assertEqual(infer_agent_batch_channel({"item_key": "ai_terminal.weekly"}), "source_library")
        self.assertEqual(infer_agent_batch_channel({"query_terms": ["ai chips"]}), "search.market")
        self.assertEqual(infer_agent_batch_channel({"input": {"query_terms": ["ai chips"]}}), "search.market")
        self.assertIsNone(infer_agent_batch_channel({}))


if __name__ == "__main__":
    unittest.main()
