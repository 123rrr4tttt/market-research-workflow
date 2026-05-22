from __future__ import annotations

import unittest

import pytest

from app.services.workflow_graph.governance_contract import (
    AUDIT_CONTRACT_VERSION,
    ROLLBACK_CONTRACT_VERSION,
    build_graph_edit_audit_record,
    build_graph_rollback_contract,
)

pytestmark = pytest.mark.unit


class WorkflowGraphGovernanceContractUnitTest(unittest.TestCase):
    def test_submit_audit_record_is_bounded_to_curated_graph_edits(self):
        record = build_graph_edit_audit_record(
            action="submit",
            actor_id="analyst-1",
            project_key="demo_proj",
            graph_id="cg-1",
            object_scope="curated_business_graph",
            from_revision=1,
            to_revision=2,
            version_id="cver-2",
            timestamp="2026-05-22T00:00:00+00:00",
        )

        self.assertEqual(record["contract_version"], AUDIT_CONTRACT_VERSION)
        self.assertEqual(record["action"], "submit")
        self.assertEqual(record["object_scope"], "curated_business_graph")
        self.assertEqual(record["project_key"], "demo_proj")
        self.assertEqual(record["from_revision"], 1)
        self.assertEqual(record["to_revision"], 2)
        self.assertEqual(record["status"], "succeeded")

        with self.assertRaisesRegex(ValueError, "unsupported graph edit audit action"):
            build_graph_edit_audit_record(
                action="delete_everything",
                actor_id="analyst-1",
                project_key="demo_proj",
                graph_id="cg-1",
                object_scope="curated_business_graph",
                from_revision=1,
                to_revision=2,
                version_id="cver-2",
            )

    def test_rollback_audit_requires_target_version_and_monotonic_revision(self):
        with self.assertRaisesRegex(ValueError, "rollback_from_version_id is required"):
            build_graph_edit_audit_record(
                action="rollback",
                actor_id="analyst-1",
                project_key="demo_proj",
                graph_id="cg-1",
                object_scope="curated_business_graph",
                from_revision=2,
                to_revision=3,
                version_id="cver-3",
            )

        with self.assertRaisesRegex(ValueError, "to_revision must be greater"):
            build_graph_edit_audit_record(
                action="rollback",
                actor_id="analyst-1",
                project_key="demo_proj",
                graph_id="cg-1",
                object_scope="curated_business_graph",
                from_revision=2,
                to_revision=2,
                version_id="cver-3",
                rollback_from_version_id="cver-1",
            )

    def test_rollback_contract_freezes_snapshot_restore_boundary(self):
        contract = build_graph_rollback_contract(
            actor_id="analyst-1",
            project_key="demo_proj",
            graph_id="cg-1",
            target_version_id="cver-1",
            current_revision=3,
            base_revision=3,
            requested_at="2026-05-22T00:00:00+00:00",
            reason="bad merge",
        )

        self.assertEqual(contract["contract_version"], ROLLBACK_CONTRACT_VERSION)
        self.assertEqual(contract["rollback_scope"], "snapshot_restore")
        self.assertEqual(contract["target_version_id"], "cver-1")
        self.assertEqual(contract["current_revision"], 3)
        self.assertTrue(contract["requires_base_revision_match"])
        self.assertEqual(
            contract["version_semantics"],
            "curated_graph_revision_separate_from_template_versions",
        )


if __name__ == "__main__":
    unittest.main()
