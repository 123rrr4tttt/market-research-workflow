from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.graph.relation_ontology import (  # noqa: E402
    canonical_predicate,
    predicate_class,
    relation_annotation,
)


class RelationOntologyTestCase(unittest.TestCase):
    def test_alias_is_normalized_to_canonical_predicate(self):
        self.assertEqual(canonical_predicate("partners_with"), "partners_with")
        self.assertEqual(canonical_predicate("cooperates_with"), "partners_with")
        self.assertEqual(canonical_predicate("compete-with"), "competes_with")
        self.assertEqual(canonical_predicate("  reports metric "), "reports_metric")

    def test_business_predicates_are_split_instead_of_merged(self):
        self.assertEqual(canonical_predicate("uses_component"), "uses_component")
        self.assertEqual(canonical_predicate("uses_strategy"), "uses_strategy")
        self.assertEqual(canonical_predicate("targets_channel"), "targets_channel")
        self.assertEqual(canonical_predicate("operates_on"), "operates_on")
        self.assertEqual(canonical_predicate("changes_metric"), "changes_metric")
        self.assertEqual(predicate_class("uses_component"), "composition")
        self.assertEqual(predicate_class("uses_strategy"), "strategy")
        self.assertEqual(predicate_class("targets_channel"), "channel")

    def test_unknown_predicate_falls_back_to_other_class(self):
        self.assertEqual(canonical_predicate("custom_relation_xyz"), "custom_relation_xyz")
        self.assertEqual(predicate_class("custom_relation_xyz"), "other")

    def test_relation_annotation_contains_raw_norm_and_class(self):
        ann = relation_annotation("  合作  ")
        self.assertEqual(ann["predicate_raw"], "  合作  ")
        self.assertEqual(ann["predicate_norm"], "partners_with")
        self.assertEqual(ann["relation_class"], "collaboration")


if __name__ == "__main__":
    unittest.main()
