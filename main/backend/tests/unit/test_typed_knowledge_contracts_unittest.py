import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_module(name: str, rel_path: str):
    path = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


baseline = _load_module("typed_knowledge_baseline", "app/services/typed_knowledge/baseline.py")
contracts = _load_module("typed_knowledge_contracts", "app/services/typed_knowledge/contracts.py")


class TypedKnowledgeK1K2ContractsTests(unittest.TestCase):
    def test_k1_baseline_contains_required_surfaces_and_terms(self):
        self.assertIn("main/backend/app/services/discovery/store.py", baseline.K1_BASELINE_SURFACES)
        self.assertIn("main/backend/app/services/resource_pool/auto_classify.py", baseline.K1_BASELINE_SURFACES)
        self.assertIn("type_node", baseline.K1_GLOSSARY)
        self.assertIn("knowledge_item", baseline.K1_GLOSSARY)
        self.assertIn("topic_cluster", baseline.K1_GLOSSARY)
        self.assertIn("booklet", baseline.K1_GLOSSARY)

    def test_relationship_validation_passes_for_minimal_valid_contract(self):
        type_node = contracts.TypeNode(key="type:policy", project_key="demo_proj", label="Policy")
        topic_cluster = contracts.TopicCluster(key="topic:energy", project_key="demo_proj", label="Energy Policy")
        booklet = contracts.Booklet(key="booklet:q1", project_key="demo_proj", title="Q1 Notes")
        item = contracts.KnowledgeItem(
            key="ki:1",
            project_key="demo_proj",
            canonical_statement="Policy support remains strong.",
            primary_type_node_key=type_node.key,
            evidence_refs=("doc:42",),
            topic_cluster_keys=(topic_cluster.key,),
            booklet_keys=(booklet.key,),
        )
        topic_cluster_with_item = contracts.TopicCluster(
            key=topic_cluster.key,
            project_key=topic_cluster.project_key,
            label=topic_cluster.label,
            knowledge_item_keys=(item.key,),
        )
        booklet_with_refs = contracts.Booklet(
            key=booklet.key,
            project_key=booklet.project_key,
            title=booklet.title,
            included_type_node_keys=(type_node.key,),
            included_topic_cluster_keys=(topic_cluster.key,),
            included_knowledge_item_keys=(item.key,),
        )

        contracts.validate_relationships(
            type_nodes=(type_node,),
            knowledge_items=(item,),
            topic_clusters=(topic_cluster_with_item,),
            booklets=(booklet_with_refs,),
        )

    def test_knowledge_item_requires_provenance(self):
        item = contracts.KnowledgeItem(
            key="ki:bad",
            project_key="demo_proj",
            canonical_statement="missing refs",
            primary_type_node_key="type:policy",
            evidence_refs=(),
        )

        with self.assertRaisesRegex(contracts.TypedKnowledgeContractError, "knowledge_item_missing_provenance"):
            contracts.validate_knowledge_item(item)

    def test_relationship_validation_rejects_unknown_type(self):
        item = contracts.KnowledgeItem(
            key="ki:1",
            project_key="demo_proj",
            canonical_statement="x",
            primary_type_node_key="type:missing",
            evidence_refs=("doc:1",),
        )

        with self.assertRaisesRegex(contracts.TypedKnowledgeContractError, "knowledge_item_unknown_primary_type"):
            contracts.validate_relationships(
                type_nodes=(),
                knowledge_items=(item,),
                topic_clusters=(),
                booklets=(),
            )

    def test_governance_matrix_covers_k3_dimensions(self):
        self.assertIn("review_state", contracts.GOVERNANCE_DIMENSION_MATRIX)
        self.assertIn("quality_grade", contracts.GOVERNANCE_DIMENSION_MATRIX)
        self.assertIn("locale", contracts.GOVERNANCE_DIMENSION_MATRIX)
        self.assertIn("provenance", contracts.GOVERNANCE_DIMENSION_MATRIX)
        self.assertEqual(contracts.BOOKLET_MEMBERSHIP_MODE, "curated_explicit_membership")
        self.assertEqual(contracts.TOPIC_CLUSTER_MEMBERSHIP_MODE, "thematic_explicit_membership")

    def test_knowledge_item_rejects_invalid_quality_grade_and_locale_shape(self):
        invalid_grade = contracts.KnowledgeItem(
            key="ki:invalid-grade",
            project_key="demo_proj",
            canonical_statement="statement",
            primary_type_node_key="type:policy",
            evidence_refs=("doc:1",),
            quality_grade="unknown",
        )
        with self.assertRaisesRegex(contracts.TypedKnowledgeContractError, "knowledge_item_invalid_quality_grade"):
            contracts.validate_knowledge_item(invalid_grade)

        invalid_locale = contracts.KnowledgeItem(
            key="ki:invalid-locale",
            project_key="demo_proj",
            canonical_statement="statement",
            primary_type_node_key="type:policy",
            evidence_refs=("doc:1",),
            locale=None,
            locale_variants={"zh-CN": "中文"},
        )
        with self.assertRaisesRegex(
            contracts.TypedKnowledgeContractError, "knowledge_item_locale_variants_require_locale"
        ):
            contracts.validate_knowledge_item(invalid_locale)

    def test_relationship_validation_rejects_cross_project_bindings(self):
        type_node = contracts.TypeNode(key="type:policy", project_key="proj_a", label="Policy")
        item = contracts.KnowledgeItem(
            key="ki:1",
            project_key="proj_a",
            canonical_statement="x",
            primary_type_node_key=type_node.key,
            evidence_refs=("doc:1",),
        )
        cross_project_topic = contracts.TopicCluster(
            key="topic:1",
            project_key="proj_b",
            label="Energy",
            knowledge_item_keys=(item.key,),
        )

        with self.assertRaisesRegex(contracts.TypedKnowledgeContractError, "knowledge_item_cross_project_topic_clusters"):
            contracts.validate_relationships(
                type_nodes=(type_node,),
                knowledge_items=(
                    contracts.KnowledgeItem(
                        key=item.key,
                        project_key=item.project_key,
                        canonical_statement=item.canonical_statement,
                        primary_type_node_key=item.primary_type_node_key,
                        evidence_refs=item.evidence_refs,
                        topic_cluster_keys=(cross_project_topic.key,),
                    ),
                ),
                topic_clusters=(cross_project_topic,),
                booklets=(),
            )

    def test_build_and_validate_downstream_contract_draft(self):
        item = contracts.KnowledgeItem(
            key="ki:1",
            project_key="demo_proj",
            canonical_statement=" Policy support remains strong. ",
            primary_type_node_key="type:policy",
            evidence_refs=("doc:42",),
            topic_cluster_keys=("topic:energy",),
            booklet_keys=("booklet:q1",),
            review_state=contracts.REVIEW_STATE_HUMAN_CONFIRMED,
            quality_grade=contracts.QUALITY_GRADE_GOLD,
            locale="en",
            locale_variants={"zh-CN": "政策支持依然强劲"},
            updated_at="2026-05-22T00:00:00Z",
        )
        draft = contracts.build_downstream_contract_draft(item)

        self.assertEqual(draft.canonical_statement, "Policy support remains strong.")
        self.assertEqual(draft.visibility_scope, contracts.VISIBILITY_SCOPE_DOWNSTREAM_READY)
        self.assertEqual(draft.updated_at, "2026-05-22T00:00:00Z")
        self.assertIn("knowledge_item_key", contracts.DOWNSTREAM_CONTRACT_FIELDS)
        self.assertIn("updated_at", contracts.DOWNSTREAM_CONTRACT_FIELDS)
        self.assertIn("graph", contracts.DOWNSTREAM_CONSUMER_FACETS)
        contracts.validate_downstream_contract_draft(draft)

    def test_updated_at_must_not_be_blank_when_present(self):
        item = contracts.KnowledgeItem(
            key="ki:invalid-updated-at",
            project_key="demo_proj",
            canonical_statement="statement",
            primary_type_node_key="type:policy",
            evidence_refs=("doc:1",),
            updated_at=" ",
        )

        with self.assertRaisesRegex(contracts.TypedKnowledgeContractError, "knowledge_item_invalid_updated_at"):
            contracts.validate_knowledge_item(item)

    def test_downstream_contract_visibility_must_match_review_state(self):
        draft = contracts.DownstreamKnowledgeContractDraft(
            knowledge_item_key="ki:1",
            project_key="demo_proj",
            canonical_statement="x",
            primary_type_node_key="type:policy",
            topic_cluster_keys=(),
            booklet_keys=(),
            review_state=contracts.REVIEW_STATE_HUMAN_CONFIRMED,
            quality_grade=None,
            locale="en",
            locale_variants={},
            evidence_refs=("doc:1",),
            visibility_scope=contracts.VISIBILITY_SCOPE_INTERNAL_ONLY,
        )

        with self.assertRaisesRegex(contracts.TypedKnowledgeContractError, "downstream_contract_visibility_scope_mismatch"):
            contracts.validate_downstream_contract_draft(draft)

    def test_apply_review_state_transition_enforces_manual_gate(self):
        updated = contracts.apply_review_state_transition(
            current_state=contracts.REVIEW_STATE_DRAFT_CANDIDATE,
            target_state=contracts.REVIEW_STATE_REVISED,
            actor=contracts.ACTOR_AUTOMATION,
        )
        self.assertEqual(updated, contracts.REVIEW_STATE_REVISED)

        with self.assertRaisesRegex(contracts.TypedKnowledgeContractError, "governance_transition_requires_human"):
            contracts.apply_review_state_transition(
                current_state=contracts.REVIEW_STATE_DRAFT_CANDIDATE,
                target_state=contracts.REVIEW_STATE_HUMAN_CONFIRMED,
                actor=contracts.ACTOR_AUTOMATION,
            )


if __name__ == "__main__":
    unittest.main()
