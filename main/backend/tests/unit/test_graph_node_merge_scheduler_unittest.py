from __future__ import annotations

import unittest

import numpy as np
import pytest

from app.services.graph.node_merge_scheduler import (
    build_disjoint_related_groups,
    rank_candidates,
)

pytestmark = pytest.mark.unit


class GraphNodeMergeSchedulerUnitTestCase(unittest.TestCase):
    def test_rank_candidates_prefers_richer_nodes(self):
        ranked = rank_candidates(
            [
                {"node_id": 1, "node_text": "a", "aliases": []},
                {"node_id": 2, "node_text": "long text value", "aliases": ["x", "y"], "properties": {"k": 1}},
            ]
        )
        self.assertEqual(ranked[0].node_id, 2)

    def test_build_disjoint_related_groups_removes_assigned_nodes(self):
        candidates = [
            {"node_id": 1, "node_text": "a", "aliases": ["a"]},
            {"node_id": 2, "node_text": "a2", "aliases": []},
            {"node_id": 3, "node_text": "b", "aliases": ["b"]},
            {"node_id": 4, "node_text": "b2", "aliases": []},
        ]
        vectors = np.array(
            [
                [1.0, 0.0],   # 1 close to 2
                [0.96, 0.04], # 2
                [0.0, 1.0],   # 3 close to 4
                [0.02, 0.98], # 4
            ],
            dtype=float,
        )
        groups = build_disjoint_related_groups(
            candidates=candidates,
            vectors=vectors,
            similarity_threshold=0.9,
            max_group_size=3,
            max_groups=10,
        )
        flat = [x for g in groups for x in g]
        self.assertEqual(len(flat), len(set(flat)))
        self.assertEqual(set(flat), {1, 2, 3, 4})
        self.assertTrue(any(set(g) == {1, 2} for g in groups))
        self.assertTrue(any(set(g) == {3, 4} for g in groups))

    def test_supplemental_merge_promotes_singletons_with_lower_threshold(self):
        candidates = [
            {"node_id": 1, "node_text": "seed-a", "aliases": ["a"]},
            {"node_id": 2, "node_text": "seed-b", "aliases": ["b"]},
            {"node_id": 3, "node_text": "singleton-c", "aliases": []},
        ]
        vectors = np.array(
            [
                [1.0, 0.0],     # node 1
                [0.0, 1.0],     # node 2
                [0.72, 0.69],   # node 3 similar to both but below 0.78
            ],
            dtype=float,
        )
        groups = build_disjoint_related_groups(
            candidates=candidates,
            vectors=vectors,
            similarity_threshold=0.78,
            fallback_similarity_threshold=0.70,
            min_group_size=2,
            max_group_size=10,
            max_groups=10,
        )
        # At least one group should be promoted to size 2 via fallback threshold.
        self.assertTrue(any(len(g) >= 2 for g in groups))

    def test_supplemental_merge_promotes_small_group_to_mature_group(self):
        candidates = [
            {"node_id": 1, "node_text": "alpha-main", "aliases": ["alpha"]},
            {"node_id": 2, "node_text": "alpha-peer", "aliases": ["alpha"]},
            {"node_id": 3, "node_text": "alpha-bridge", "aliases": []},
            {"node_id": 4, "node_text": "alpha-tail", "aliases": []},
            {"node_id": 5, "node_text": "beta-lone", "aliases": []},
        ]
        vectors = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.98, 0.05, 0.0],
                [0.95, 0.12, 0.0],
                [0.84, 0.52, 0.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=float,
        )
        groups = build_disjoint_related_groups(
            candidates=candidates,
            vectors=vectors,
            similarity_threshold=0.9,
            fallback_similarity_threshold=0.72,
            min_group_size=3,
            max_group_size=10,
            max_groups=10,
        )
        self.assertTrue(any(set([1, 2, 3, 4]).issubset(set(g)) for g in groups))


if __name__ == "__main__":
    unittest.main()
