from __future__ import annotations

import unittest

import pytest

from app.services.graph import merge_policy as mp
from app.services.graph.merge_policy import (
    MergePolicy,
    MergePolicyResult,
    get_merge_policy,
    list_merge_policies,
    register_merge_policy,
    select_merge_policy,
)
from app.settings.config import settings

pytestmark = pytest.mark.unit


class _AlwaysApprovePolicy(MergePolicy):
    name = "always_approve"

    def evaluate(self, *, query_text: str, candidates: list[dict]):
        return MergePolicyResult(
            decision="merge",
            confidence=0.99,
            reason="test policy",
            evidence={"query_text": query_text, "candidate_count": len(candidates)},
        )


class MergePolicyRegistryUnitTestCase(unittest.TestCase):
    def test_default_policy_returns_expected_structure(self):
        policy = get_merge_policy()
        result = policy.evaluate(
            query_text="OpenAI",
            candidates=[
                {"node_id": 10},
                {"node_id": "11"},
                {"node_id": "bad"},
            ],
        )

        self.assertEqual(result.decision, "skip")
        self.assertIsInstance(result.confidence, float)
        self.assertIsInstance(result.reason, str)
        self.assertIsInstance(result.evidence, dict)
        self.assertEqual(result.evidence["query_text"], "OpenAI")
        self.assertEqual(result.evidence["candidate_count"], 3)
        self.assertEqual(result.evidence["candidate_ids"], [10, 11])
        self.assertEqual(result.evidence["merges"], [])

    def test_policy_registry_register_and_lookup(self):
        try:
            register_merge_policy(_AlwaysApprovePolicy())
        except ValueError:
            # Tolerate pre-registered state from parallel runs.
            pass

        self.assertIn("always_approve", list_merge_policies())
        policy = get_merge_policy("ALWAYS_APPROVE")
        result = policy.evaluate(query_text="q", candidates=[{"node_id": 1}, {"node_id": 2}])

        self.assertEqual(result.decision, "merge")
        self.assertEqual(result.evidence["candidate_count"], 2)

    def test_select_merge_policy_by_project_and_node_type_with_fallback(self):
        try:
            register_merge_policy(_AlwaysApprovePolicy())
        except ValueError:
            pass

        old_default = settings.graph_node_merge_policy_default
        old_selector = settings.graph_node_merge_policy_selector_json
        try:
            settings.graph_node_merge_policy_default = "default"
            settings.graph_node_merge_policy_selector_json = (
                '{"demo_proj":{"entity":"always_approve","*":"missing_policy"},"*":{"*":"default"}}'
            )

            selected, reason = select_merge_policy(project_key="demo_proj", node_type="Entity")
            self.assertEqual(selected.name, "always_approve")
            self.assertIsNone(reason)

            selected, reason = select_merge_policy(project_key="demo_proj", node_type="UnknownType")
            self.assertEqual(selected.name, "default")
            self.assertIsInstance(reason, str)
            self.assertIn("unknown merge policy", reason)
        finally:
            settings.graph_node_merge_policy_default = old_default
            settings.graph_node_merge_policy_selector_json = old_selector

    def test_select_merge_policy_priority_includes_global_node_type_and_global_default(self):
        try:
            register_merge_policy(_AlwaysApprovePolicy())
        except ValueError:
            pass

        old_default = settings.graph_node_merge_policy_default
        old_selector = settings.graph_node_merge_policy_selector_json
        try:
            settings.graph_node_merge_policy_default = "default"
            settings.graph_node_merge_policy_selector_json = (
                '{"demo_proj":{"productentity":"always_approve","*":"default"},'
                '"*":{"productentity":"always_approve","*":"default"}}'
            )

            selected, reason = select_merge_policy(project_key="other_proj", node_type="ProductEntity")
            self.assertEqual(selected.name, "always_approve")
            self.assertIsNone(reason)

            selected, reason = select_merge_policy(project_key="other_proj", node_type="OtherType")
            self.assertEqual(selected.name, "default")
            self.assertIsNone(reason)
        finally:
            settings.graph_node_merge_policy_default = old_default
            settings.graph_node_merge_policy_selector_json = old_selector

    def test_select_merge_policy_prefers_db_selector_over_json(self):
        old_default = settings.graph_node_merge_policy_default
        old_selector = settings.graph_node_merge_policy_selector_json
        old_db_enabled = settings.graph_node_merge_policy_selector_db_enabled
        original_get_ingest = mp.get_ingest_config
        try:
            settings.graph_node_merge_policy_default = "default"
            settings.graph_node_merge_policy_selector_json = '{"demo_proj":{"entity":"default"}}'
            settings.graph_node_merge_policy_selector_db_enabled = True

            def _fake_get_ingest(project_key: str, config_key: str):
                if config_key != mp.MERGE_POLICY_SELECTOR_CONFIG_KEY:
                    return None
                if project_key == "demo_proj":
                    return {"payload": {"entity": "always_approve"}}
                return None

            mp.get_ingest_config = _fake_get_ingest
            try:
                register_merge_policy(_AlwaysApprovePolicy())
            except ValueError:
                pass
            selected, reason = select_merge_policy(project_key="demo_proj", node_type="entity")
            self.assertEqual(selected.name, "always_approve")
            self.assertIsNone(reason)
        finally:
            mp.get_ingest_config = original_get_ingest
            settings.graph_node_merge_policy_default = old_default
            settings.graph_node_merge_policy_selector_json = old_selector
            settings.graph_node_merge_policy_selector_db_enabled = old_db_enabled

    def test_select_merge_policy_db_disabled_falls_back_to_json(self):
        old_default = settings.graph_node_merge_policy_default
        old_selector = settings.graph_node_merge_policy_selector_json
        old_db_enabled = settings.graph_node_merge_policy_selector_db_enabled
        original_get_ingest = mp.get_ingest_config
        try:
            settings.graph_node_merge_policy_default = "default"
            settings.graph_node_merge_policy_selector_json = '{"demo_proj":{"entity":"always_approve"}}'
            settings.graph_node_merge_policy_selector_db_enabled = False

            def _fake_get_ingest(_project_key: str, _config_key: str):
                return {"payload": {"entity": "default"}}

            mp.get_ingest_config = _fake_get_ingest
            try:
                register_merge_policy(_AlwaysApprovePolicy())
            except ValueError:
                pass
            selected, reason = select_merge_policy(project_key="demo_proj", node_type="entity")
            self.assertEqual(selected.name, "always_approve")
            self.assertIsNone(reason)
        finally:
            mp.get_ingest_config = original_get_ingest
            settings.graph_node_merge_policy_default = old_default
            settings.graph_node_merge_policy_selector_json = old_selector
            settings.graph_node_merge_policy_selector_db_enabled = old_db_enabled


if __name__ == "__main__":
    unittest.main()
