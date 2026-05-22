from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from app.services.workflow_graph.curated_service import (
    WorkflowGraphCuratedService,
    WorkflowGraphObjectMissingError,
    WorkflowGraphSyncConflictError,
)

pytestmark = pytest.mark.unit


class WorkflowGraphCuratedServiceUnitTest(unittest.TestCase):
    def _state(self) -> dict:
        return {"base_version": 0, "graphs": {}}

    def test_submit_requires_draft_and_conflict_is_explicit(self):
        state = self._state()
        store = {"payload": state}
        service = WorkflowGraphCuratedService()
        with patch("app.services.workflow_graph.curated_service.current_project_key", return_value="demo_proj"), patch(
            "app.services.workflow_graph.curated_service.get_ingest_config",
            side_effect=lambda *_args, **_kwargs: {"payload": store["payload"]},
        ), patch(
            "app.services.workflow_graph.curated_service.upsert_ingest_config",
            side_effect=lambda *_args, **kwargs: (
                store.update({"payload": kwargs.get("payload")}),
                {"payload": store["payload"]},
            )[1],
        ):
            service.save_draft(
                "cg-1",
                {
                    "dsl": {
                        "nodes": [{"id": "n1", "type": "Entity"}, {"id": "n2", "type": "Entity"}],
                        "edges": [{"from": "n1", "to": "n2", "type": "REL"}],
                    },
                },
            )
            with self.assertRaises(WorkflowGraphSyncConflictError):
                service.submit_draft("cg-1", {"base_revision": 1})

    def test_submit_builds_revision_version_and_audit(self):
        state = self._state()
        store = {"payload": state}
        service = WorkflowGraphCuratedService()
        with patch("app.services.workflow_graph.curated_service.current_project_key", return_value="demo_proj"), patch(
            "app.services.workflow_graph.curated_service.get_ingest_config",
            side_effect=lambda *_args, **_kwargs: {"payload": store["payload"]},
        ), patch(
            "app.services.workflow_graph.curated_service.upsert_ingest_config",
            side_effect=lambda *_args, **kwargs: (
                store.update({"payload": kwargs.get("payload")}),
                {"payload": store["payload"]},
            )[1],
        ):
            service.save_draft(
                "cg-1",
                {
                    "dsl": {
                        "nodes": [{"id": "node-a", "type": "Entity"}, {"id": "node-b", "type": "Entity"}],
                        "edges": [{"from": "node-a", "to": "node-b", "predicate": "relates_to"}],
                    },
                },
            )
            submit = service.submit_draft("cg-1", {"base_revision": 0, "actor_id": "tester"})
            self.assertEqual(submit["submit_status"], "submitted")
            self.assertEqual(submit["revision"], 1)
            audits = service.list_audits("cg-1")
            self.assertEqual(audits["items"][0]["action"], "submit")
            self.assertEqual(audits["items"][0]["contract_version"], "workflow_graph.governance_audit.v1")
            self.assertEqual(
                audits["items"][0]["version_semantics"],
                "curated_graph_revision_separate_from_template_versions",
            )

    def test_rollback_uses_bounded_contract_and_audit_record(self):
        state = self._state()
        store = {"payload": state}
        service = WorkflowGraphCuratedService()
        with patch("app.services.workflow_graph.curated_service.current_project_key", return_value="demo_proj"), patch(
            "app.services.workflow_graph.curated_service.get_ingest_config",
            side_effect=lambda *_args, **_kwargs: {"payload": store["payload"]},
        ), patch(
            "app.services.workflow_graph.curated_service.upsert_ingest_config",
            side_effect=lambda *_args, **kwargs: (
                store.update({"payload": kwargs.get("payload")}),
                {"payload": store["payload"]},
            )[1],
        ):
            service.save_draft(
                "cg-1",
                {
                    "dsl": {
                        "nodes": [{"id": "node-a", "type": "Entity"}, {"id": "node-b", "type": "Entity"}],
                        "edges": [{"from": "node-a", "to": "node-b", "predicate": "relates_to"}],
                    },
                },
            )
            service.submit_draft("cg-1", {"base_revision": 0, "actor_id": "tester", "version_id": "cver-1"})
            service.save_draft(
                "cg-1",
                {
                    "base_revision": 1,
                    "dsl": {
                        "nodes": [{"id": "node-a", "type": "Entity"}, {"id": "node-c", "type": "Entity"}],
                        "edges": [{"from": "node-a", "to": "node-c", "predicate": "relates_to"}],
                    },
                },
            )
            service.submit_draft("cg-1", {"base_revision": 1, "actor_id": "tester", "version_id": "cver-2"})

            rollback = service.rollback(
                "cg-1",
                {"base_revision": 2, "actor_id": "tester", "target_version_id": "cver-1", "reason": "bad merge"},
            )

            self.assertEqual(rollback["rollback_status"], "succeeded")
            self.assertEqual(rollback["revision"], 3)
            self.assertEqual(rollback["rollback_from_version_id"], "cver-1")
            self.assertEqual(rollback["rollback_contract"]["contract_version"], "workflow_graph.rollback.v1")
            self.assertEqual(rollback["rollback_contract"]["rollback_scope"], "snapshot_restore")
            self.assertEqual(rollback["rollback_contract"]["target_version_id"], "cver-1")

            audits = service.list_audits("cg-1")
            self.assertEqual(audits["items"][0]["action"], "rollback")
            self.assertEqual(audits["items"][0]["contract_version"], "workflow_graph.governance_audit.v1")
            self.assertEqual(audits["items"][0]["rollback_from_version_id"], "cver-1")
            self.assertEqual(
                audits["items"][0]["context"]["rollback_contract"]["version_semantics"],
                "curated_graph_revision_separate_from_template_versions",
            )

    def test_save_draft_rejects_cycle_before_submit(self):
        state = self._state()
        store = {"payload": state}
        service = WorkflowGraphCuratedService()
        with patch("app.services.workflow_graph.curated_service.current_project_key", return_value="demo_proj"), patch(
            "app.services.workflow_graph.curated_service.get_ingest_config",
            side_effect=lambda *_args, **_kwargs: {"payload": store["payload"]},
        ), patch(
            "app.services.workflow_graph.curated_service.upsert_ingest_config",
            side_effect=lambda *_args, **kwargs: (
                store.update({"payload": kwargs.get("payload")}),
                {"payload": store["payload"]},
            )[1],
        ):
            with self.assertRaisesRegex(ValueError, "workflow graph contains a cycle"):
                service.save_draft(
                    "cg-1",
                    {
                        "dsl": {
                            "nodes": [{"id": "n1", "type": "Entity"}, {"id": "n2", "type": "Entity"}],
                            "edges": [
                                {"from": "n1", "to": "n2", "type": "REL"},
                                {"from": "n2", "to": "n1", "type": "REL"},
                            ],
                        },
                    },
                )

    def test_build_evidence_pack_and_reporting_handoff(self):
        state = self._state()
        store = {"payload": state}
        service = WorkflowGraphCuratedService()
        with patch("app.services.workflow_graph.curated_service.current_project_key", return_value="demo_proj"), patch(
            "app.services.workflow_graph.curated_service.get_ingest_config",
            side_effect=lambda *_args, **_kwargs: {"payload": store["payload"]},
        ), patch(
            "app.services.workflow_graph.curated_service.upsert_ingest_config",
            side_effect=lambda *_args, **kwargs: (
                store.update({"payload": kwargs.get("payload")}),
                {"payload": store["payload"]},
            )[1],
        ):
            service.save_draft(
                "cg-1",
                {
                    "dsl": {
                        "nodes": [
                            {
                                "id": "node-a",
                                "type": "Company",
                                "name": "Acme",
                                "summary": "Acme trend",
                                "source_uri": "https://example.com/acme",
                            },
                            {"id": "node-b", "type": "Market", "name": "Robotics"},
                        ],
                        "edges": [{"from": "node-a", "to": "node-b", "predicate": "in_market", "evidence": "proof"}],
                    },
                },
            )
            service.submit_draft("cg-1", {"base_revision": 0})
            pack = service.build_evidence_pack("cg-1", {"selected_node_ids": ["node-a", "node-b"]})
            self.assertEqual(pack["contract_version"], "graph_evidence_pack.v1")
            self.assertEqual(len(pack["selected_nodes"]), 2)
            reporting = service.build_reporting_handoff("cg-1", {"topic": "robotics"})
            self.assertEqual(reporting["consumer"], "llm_report.generate")
            self.assertEqual(reporting["owner"], "workflow_graph.backend_bridge")
            self.assertEqual(reporting["producer"], "workflow_graph.backend_bridge")
            self.assertEqual(reporting["report_generate_request"]["topic"], "robotics")
            self.assertEqual(len(reporting["report_generate_request"]["sources"]), 1)
            writing = service.build_writing_handoff("cg-1", {"query": "robotics"})
            self.assertEqual(writing["consumer"], "writing.keyword_cards")
            self.assertEqual(writing["owner"], "workflow_graph.backend_bridge")
            self.assertEqual(writing["producer"], "workflow_graph.backend_bridge")
            self.assertEqual(writing["keyword_card_request"]["project_key"], "demo_proj")
            self.assertEqual(writing["keyword_card_request"]["sources"], ["graph"])
            self.assertEqual(
                writing["keyword_card_request"]["context"]["graph_context"]["contract_version"],
                "graph_evidence_pack.v1",
            )

    def test_get_graph_raises_missing_for_unknown_id(self):
        service = WorkflowGraphCuratedService()
        with patch("app.services.workflow_graph.curated_service.current_project_key", return_value="demo_proj"), patch(
            "app.services.workflow_graph.curated_service.get_ingest_config",
            return_value={"payload": self._state()},
        ):
            with self.assertRaises(WorkflowGraphObjectMissingError):
                service.get_graph("missing")


if __name__ == "__main__":
    unittest.main()
