import copy
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.typed_knowledge import contracts  # noqa: E402
from app.services.typed_knowledge import persistence_boundary as boundary  # noqa: E402


class TypedKnowledgePersistenceBoundaryTests(unittest.TestCase):
    def test_sample_boundary_envelope_preserves_identity_visibility_lifecycle_and_handoff_refs(self):
        envelope = boundary.build_sample_boundary_envelope()
        repeated = boundary.build_sample_boundary_envelope()

        self.assertEqual(envelope["status"], "ok")
        self.assertEqual(
            envelope["data"]["contract_version"],
            boundary.PERSISTENCE_API_BOUNDARY_CONTRACT_VERSION,
        )
        self.assertEqual(len(envelope["data"]["records"]), 4)
        self.assertEqual(
            boundary.boundary_fingerprint(envelope),
            boundary.boundary_fingerprint(repeated),
        )
        self.assertEqual(envelope["data"]["repository"]["persistence_mode"], "in_memory_contract")
        self.assertFalse(envelope["data"]["repository"]["live_db_write"])
        self.assertTrue(all(write["live_db_write"] is False for write in envelope["data"]["writes"]))

        records_by_type = {record["object_type"]: record for record in envelope["data"]["records"]}
        item_record = records_by_type["knowledge_item"]
        self.assertEqual(item_record["identity_ref"], "demo_proj:knowledge_item:ki:robotics-policy")
        self.assertEqual(item_record["visibility_scope"], contracts.VISIBILITY_SCOPE_DOWNSTREAM_READY)
        self.assertEqual(item_record["lifecycle_state"], boundary.LIFECYCLE_STATE_ACTIVE)
        self.assertEqual(item_record["governance"]["review_state"], contracts.REVIEW_STATE_HUMAN_CONFIRMED)
        self.assertEqual(
            item_record["writing_handoff_refs"],
            [
                {
                    "contract_version": contracts.WRITING_KNOWLEDGE_HANDOFF_CONTRACT_VERSION,
                    "knowledge_item_key": "ki:robotics-policy",
                    "consumer": "writing.keyword_card",
                    "card_source_type": "resource",
                    "selection_hash": "selection:robotics",
                    "selection_text": "robotics investment",
                }
            ],
        )

        readiness = envelope["meta"]["readiness"]
        self.assertTrue(readiness["repository_contract"])
        self.assertTrue(readiness["api_envelope"])
        self.assertTrue(readiness["writing_handoff_refs"])
        self.assertFalse(readiness["live_db_persistence"])
        self.assertFalse(readiness["public_api_route"])
        self.assertFalse(readiness["governance_ui"])
        self.assertIn(
            "live_db_persistence_not_implemented",
            envelope["meta"]["remaining_live_gaps"],
        )

    def test_in_memory_repository_readback_records_status_before_without_claiming_live_db(self):
        item = contracts.KnowledgeItem(
            key="ki:boundary",
            project_key="demo_proj",
            canonical_statement="A governed knowledge item starts as a draft candidate.",
            primary_type_node_key="type:signal",
            evidence_refs=("doc:1",),
            review_state=contracts.REVIEW_STATE_DRAFT_CANDIDATE,
        )
        revised = contracts.KnowledgeItem(
            key=item.key,
            project_key=item.project_key,
            canonical_statement="A governed knowledge item can become active after review.",
            primary_type_node_key=item.primary_type_node_key,
            evidence_refs=item.evidence_refs,
            review_state=contracts.REVIEW_STATE_HUMAN_CONFIRMED,
        )
        repository = boundary.InMemoryTypedKnowledgeRepository(repository_ref="memory://unit-test")
        draft_record = boundary.build_persistence_boundary_record(item)
        active_record = boundary.build_persistence_boundary_record(revised)

        first = repository.upsert_record(draft_record, write_time="2026-05-22T00:00:00Z")
        second = repository.upsert_record(active_record, write_time="2026-05-22T00:01:00Z")
        stored = repository.get_record(active_record.identity_ref)

        self.assertIsNotNone(stored)
        self.assertEqual(first.status_before, None)
        self.assertEqual(first.status_after, boundary.LIFECYCLE_STATE_PROPOSED)
        self.assertEqual(second.status_before, boundary.LIFECYCLE_STATE_PROPOSED)
        self.assertEqual(second.status_after, boundary.LIFECYCLE_STATE_ACTIVE)
        self.assertEqual(stored.visibility_scope, contracts.VISIBILITY_SCOPE_DOWNSTREAM_READY)
        self.assertFalse(second.live_db_write)

    def test_api_envelope_rejects_live_db_or_ui_completion_overclaim(self):
        envelope = boundary.build_sample_boundary_envelope()
        envelope["meta"]["readiness"]["live_db_persistence"] = True

        with self.assertRaisesRegex(
            boundary.TypedKnowledgePersistenceBoundaryError,
            "persistence_api_envelope_overclaims_live_completion",
        ):
            boundary.validate_persistence_api_envelope(envelope)

        envelope = boundary.build_sample_boundary_envelope()
        envelope["data"]["writes"][0]["live_db_write"] = True

        with self.assertRaisesRegex(
            boundary.TypedKnowledgePersistenceBoundaryError,
            "persistence_api_envelope_live_write_claim_forbidden",
        ):
            boundary.validate_persistence_api_envelope(envelope)

    def test_handoff_refs_are_limited_to_writing_keyword_card_resource_boundary(self):
        record = boundary.PersistenceBoundaryRecord(
            contract_version=boundary.PERSISTENCE_API_BOUNDARY_CONTRACT_VERSION,
            object_type=boundary.OBJECT_TYPE_KNOWLEDGE_ITEM,
            object_key="ki:bad-ref",
            project_key="demo_proj",
            identity_ref="demo_proj:knowledge_item:ki:bad-ref",
            visibility_scope=contracts.VISIBILITY_SCOPE_DOWNSTREAM_READY,
            lifecycle_state=boundary.LIFECYCLE_STATE_ACTIVE,
            governance={
                "review_state": contracts.REVIEW_STATE_HUMAN_CONFIRMED,
                "visibility_scope": contracts.VISIBILITY_SCOPE_DOWNSTREAM_READY,
                "lifecycle_state": boundary.LIFECYCLE_STATE_ACTIVE,
            },
            writing_handoff_refs=(
                boundary.WritingHandoffRef(
                    contract_version=contracts.WRITING_KNOWLEDGE_HANDOFF_CONTRACT_VERSION,
                    knowledge_item_key="ki:bad-ref",
                    consumer="writing.unknown",
                    card_source_type="resource",
                ),
            ),
        )

        with self.assertRaisesRegex(
            boundary.TypedKnowledgePersistenceBoundaryError,
            "writing_handoff_ref_consumer_mismatch",
        ):
            boundary.validate_persistence_boundary_record(record)

    def test_public_api_route_contract_closes_route_gap_without_claiming_live_db(self):
        envelope = boundary.build_public_api_route_contract_envelope(project_key="route_proj")
        boundary.validate_public_api_route_contract_envelope(envelope)

        self.assertEqual(envelope["data"]["contract_version"], boundary.PUBLIC_API_ROUTE_CONTRACT_VERSION)
        self.assertEqual(envelope["data"]["route"]["path"], boundary.PUBLIC_API_ROUTE_PATH)
        self.assertTrue(envelope["meta"]["readiness"]["public_api_route"])
        self.assertFalse(envelope["meta"]["readiness"]["live_db_persistence"])
        self.assertNotIn(
            "public_typed_knowledge_api_route_not_implemented",
            envelope["meta"]["remaining_live_gaps"],
        )

        records = envelope["data"]["persistence_boundary"]["records"]
        item_record = next(record for record in records if record["object_type"] == "knowledge_item")
        self.assertEqual(item_record["project_key"], "route_proj")
        self.assertEqual(item_record["identity_ref"], "route_proj:knowledge_item:ki:robotics-policy")

        overclaim = copy.deepcopy(envelope)
        overclaim["meta"]["readiness"]["live_db_persistence"] = True
        with self.assertRaisesRegex(
            boundary.TypedKnowledgePersistenceBoundaryError,
            "public_api_route_live_completion_overclaim",
        ):
            boundary.validate_public_api_route_contract_envelope(overclaim)


if __name__ == "__main__":
    unittest.main()
