from __future__ import annotations

import unittest

import pytest

from app.services.graph import node_merge_llm as m
from app.settings.config import settings
from app.services.graph.merge_policy import MergePolicyResult

pytestmark = pytest.mark.unit


class _FakeResp:
    def __init__(self, content: str):
        self.content = content


class _FakeModel:
    def __init__(self, payload: str):
        self._payload = payload

    def invoke(self, _prompt: str):
        return _FakeResp(self._payload)


class _CapturePolicy:
    name = "capture"

    def __init__(self) -> None:
        self.last_query_text = ""
        self.last_candidates: list[dict] = []

    def evaluate(self, *, query_text: str, candidates: list[dict]) -> MergePolicyResult:
        self.last_query_text = query_text
        self.last_candidates = candidates
        return MergePolicyResult(
            decision="skip",
            confidence=1.0,
            reason="capture inputs",
            evidence={"merges": [{}]},
        )


class GraphNodeMergeLlmUnitTestCase(unittest.TestCase):
    def test_is_data_point_node(self):
        self.assertTrue(m.is_data_point_node({"node_type": "NumericMetric"}))
        self.assertTrue(m.is_data_point_node({"node_type": "Any", "properties": {"data_kind": "metric"}}))
        self.assertFalse(m.is_data_point_node({"node_type": "ProductEntity", "properties": {"data_kind": "entity"}}))

    def test_suggest_node_merges_filters_data_points_and_normalizes(self):
        fake_json = """
        {
          "merges": [
            {
              "merged_node": {"display_name":"Anthropic Program","node_type":"ProductEntity","canonical_id":"product:anthropic program"},
              "source_node_ids":[10,11],
              "confidence":0.88,
              "reason":"same entity"
            },
            {
              "merged_node": {"display_name":"bad","node_type":"ProductEntity","canonical_id":"bad"},
              "source_node_ids":[999],
              "confidence":0.2,
              "reason":"invalid"
            }
          ],
          "unmerged_node_ids":[12]
        }
        """

        original = m.get_chat_model
        try:
            m.get_chat_model = lambda **_: _FakeModel(fake_json)
            result = m.suggest_node_merges_with_llm(
                query_text="anthropic research",
                candidates=[
                    {"node_id": 10, "node_type": "ProductEntity", "display_name": "Anthropic Program", "properties": {}},
                    {"node_id": 11, "node_type": "ProductEntity", "display_name": "Anthropic Program", "properties": {}},
                    {"node_id": 12, "node_type": "TopicTag", "properties": {}},
                    {"node_id": 13, "node_type": "NumericMetric", "properties": {}},
                ],
            )
        finally:
            m.get_chat_model = original

        self.assertEqual(len(result["merges"]), 1)
        self.assertEqual(result["merges"][0]["source_node_ids"], [10, 11])
        self.assertEqual(result["unmerged_node_ids"], [12])

    def test_is_content_like_node(self):
        self.assertTrue(
            m.is_content_like_node(
                {"node_type": "ProductEntity", "display_name": "A long collaborative relationship with multiple organizations through 2026 initiative"}
            )
        )
        self.assertTrue(m.is_content_like_node({"node_type": "Post", "display_name": "Any post title"}))
        self.assertFalse(m.is_content_like_node({"node_type": "CompanyEntity", "display_name": "OpenAI"}))

    def test_suggest_node_merges_rejects_mixed_type_cluster(self):
        fake_json = """
        {
          "merges": [
            {
              "merged_node": {"display_name":"Anthropic","node_type":"ProductEntity","canonical_id":"product:anthropic"},
              "source_node_ids":[10,11],
              "confidence":0.9,
              "reason":"related"
            }
          ],
          "unmerged_node_ids":[]
        }
        """
        original = m.get_chat_model
        try:
            m.get_chat_model = lambda **_: _FakeModel(fake_json)
            result = m.suggest_node_merges_with_llm(
                query_text="anthropic",
                candidates=[
                    {"node_id": 10, "node_type": "ProductEntity", "display_name": "Anthropic Program", "properties": {}},
                    {"node_id": 11, "node_type": "ProductBrand", "display_name": "Anthropic", "properties": {}},
                ],
            )
        finally:
            m.get_chat_model = original
        self.assertEqual(result["merges"], [])

    def test_normalize_merge_inputs_context_node_type_priority_and_fallback(self):
        class _RecordingExecutor:
            calls = []

            def normalize(self, value, *, rule_ids=None, context=None):  # noqa: ANN001
                del rule_ids
                _RecordingExecutor.calls.append((value, dict(context or {})))
                return str(value or "")

        original_executor = m.SymbolRuleExecutor
        try:
            m.SymbolRuleExecutor = _RecordingExecutor

            m._normalize_merge_inputs(
                query_text="Anthropic",
                candidates=[
                    {
                        "node_id": 10,
                        "node_type": "ProductEntity",
                        "display_name": "Anthropic Program",
                        "canonical_id": "product:anthropic-program",
                        "node_text": "Anthropic Program",
                        "aliases": ["Anthropic"],
                    }
                ],
                context={"project_key": "demo_proj", "node_type": "Policy"},
            )
            contexts = [ctx for _value, ctx in _RecordingExecutor.calls]
            self.assertIn({"project_key": "demo_proj", "node_type": "Policy"}, contexts)

            _RecordingExecutor.calls.clear()
            m._normalize_merge_inputs(
                query_text="Anthropic",
                candidates=[
                    {
                        "node_id": 10,
                        "node_type": "ProductEntity",
                        "display_name": "Anthropic Program",
                        "canonical_id": "product:anthropic-program",
                        "node_text": "Anthropic Program",
                        "aliases": ["Anthropic"],
                    }
                ],
                context={"project_key": "demo_proj"},
            )
            contexts = [ctx for _value, ctx in _RecordingExecutor.calls]
            self.assertIn({"project_key": "demo_proj", "node_type": "ProductEntity"}, contexts)
        finally:
            m.SymbolRuleExecutor = original_executor

    def test_policy_selection_by_project_and_node_type_applies_in_node_merge_llm(self):
        old_default = settings.graph_node_merge_policy_default
        old_selector = settings.graph_node_merge_policy_selector_json
        original = m.get_chat_model
        try:
            settings.graph_node_merge_policy_default = "default"
            settings.graph_node_merge_policy_selector_json = '{"demo_proj":{"productentity":"default"}}'
            m.get_chat_model = lambda **_: _FakeModel('{"merges":[]}')
            result = m.suggest_node_merges_with_llm(
                query_text="anthropic",
                candidates=[
                    {"node_id": 10, "node_type": "ProductEntity", "display_name": "Anthropic Program", "properties": {}},
                    {"node_id": 11, "node_type": "ProductEntity", "display_name": "Anthropic", "properties": {}},
                ],
                project_key="demo_proj",
                node_type="ProductEntity",
            )
        finally:
            settings.graph_node_merge_policy_default = old_default
            settings.graph_node_merge_policy_selector_json = old_selector
            m.get_chat_model = original

        self.assertEqual(result["policy"], "default")
        self.assertIsNone(result["policy_fallback_reason"])

    def test_policy_unknown_falls_back_to_default_with_reason(self):
        old_default = settings.graph_node_merge_policy_default
        old_selector = settings.graph_node_merge_policy_selector_json
        original = m.get_chat_model
        try:
            settings.graph_node_merge_policy_default = "default"
            settings.graph_node_merge_policy_selector_json = '{"demo_proj":{"productentity":"missing_policy"}}'
            m.get_chat_model = lambda **_: _FakeModel('{"merges":[]}')
            result = m.suggest_node_merges_with_llm(
                query_text="anthropic",
                candidates=[
                    {"node_id": 10, "node_type": "ProductEntity", "display_name": "Anthropic Program", "properties": {}},
                    {"node_id": 11, "node_type": "ProductEntity", "display_name": "Anthropic", "properties": {}},
                ],
                project_key="demo_proj",
                node_type="ProductEntity",
            )
        finally:
            settings.graph_node_merge_policy_default = old_default
            settings.graph_node_merge_policy_selector_json = old_selector
            m.get_chat_model = original

        self.assertEqual(result["policy"], "default")
        self.assertIsInstance(result["policy_fallback_reason"], str)
        self.assertIn("unknown merge policy", result["policy_fallback_reason"])

    def test_suggest_node_merges_normalizes_text_before_policy(self):
        policy = _CapturePolicy()
        original_get_policy = m.get_merge_policy
        try:
            m.get_merge_policy = lambda: policy
            m.suggest_node_merges_with_llm(
                query_text="  OpenAI， INC  ",
                candidates=[
                    {
                        "node_id": 10,
                        "node_type": "CompanyEntity",
                        "display_name": " OpenAI， Inc ",
                        "canonical_id": " COMPANY：OPENAI ",
                        "node_text": " OpenAI， Inc ",
                        "aliases": [" OPENAI ", " OpenAI（US） "],
                        "properties": {},
                    },
                    {
                        "node_id": 11,
                        "node_type": "CompanyEntity",
                        "display_name": "OpenAI",
                        "properties": {},
                    },
                ],
                project_key="proj_alpha",
                node_type="CompanyEntity",
            )
        finally:
            m.get_merge_policy = original_get_policy

        self.assertEqual(policy.last_query_text, "openai, inc")
        self.assertEqual(policy.last_candidates[0]["display_name"], "openai, inc")
        self.assertEqual(policy.last_candidates[0]["canonical_id"], "company:openai")
        self.assertEqual(policy.last_candidates[0]["node_text"], "openai, inc")
        self.assertEqual(policy.last_candidates[0]["aliases"], ["openai", "openai(us)"])


if __name__ == "__main__":
    unittest.main()
