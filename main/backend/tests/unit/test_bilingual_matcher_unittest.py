from __future__ import annotations

import unittest

import pytest

from app.services.graph.bilingual_matcher import suggest_merge_candidates

pytestmark = pytest.mark.unit


class BilingualMatcherUnitTestCase(unittest.TestCase):
    def test_suggest_merge_candidates_same_type_and_threshold(self):
        candidates = suggest_merge_candidates(
            [
                {
                    "node_id": 10,
                    "node_type": "CompanyEntity",
                    "alias_dict": {"zh": ["开放人工智能"], "en": ["OpenAI", "Open AI"]},
                },
                {
                    "node_id": 11,
                    "node_type": "CompanyEntity",
                    "alias_dict": {"en": ["openai"], "abbr": ["OAI"]},
                },
                {
                    "node_id": 12,
                    "node_type": "ProductEntity",
                    "alias_dict": {"en": ["OpenAI"]},
                },
            ],
            threshold=0.3,
            metric="max",
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["source_node_ids"], [10, 11])
        self.assertGreaterEqual(float(candidates[0]["score"]), 0.3)
        self.assertIn("jaccard=", candidates[0]["reason"])
        self.assertEqual(candidates[0]["node_type"], "companyentity")

    def test_metric_jaccard_applies_threshold(self):
        candidates = suggest_merge_candidates(
            [
                {"node_id": 1, "node_type": "Entity", "alias_dict": {"en": ["OpenAI", "OAI"]}},
                {"node_id": 2, "node_type": "Entity", "alias_dict": {"en": ["OpenAI"]}},
            ],
            threshold=0.6,
            metric="jaccard",
        )
        self.assertEqual(candidates, [])

        candidates = suggest_merge_candidates(
            [
                {"node_id": 1, "node_type": "Entity", "alias_dict": {"en": ["OpenAI", "OAI"]}},
                {"node_id": 2, "node_type": "Entity", "alias_dict": {"en": ["OpenAI"]}},
            ],
            threshold=0.4,
            metric="jaccard",
        )
        self.assertEqual(len(candidates), 1)
        self.assertAlmostEqual(candidates[0]["score"], 0.5, places=6)

    def test_aliases_fallback_field_supported(self):
        candidates = suggest_merge_candidates(
            [
                {"node_id": 1, "node_type": "Entity", "aliases": [" OpenAI ", "OAI"]},
                {"node_id": 2, "node_type": "Entity", "aliases": {"en": ["openai"]}},
            ],
            threshold=0.5,
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["source_node_ids"], [1, 2])


if __name__ == "__main__":
    unittest.main()

