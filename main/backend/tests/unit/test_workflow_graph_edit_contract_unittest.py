from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from app.services.workflow_graph.edit_contract import (
    WorkflowGraphEditContractError,
    parse_graph_edit_draft_contract,
)
from app.services.workflow_graph.templates import WorkflowGraphTemplateService

pytestmark = pytest.mark.unit


class WorkflowGraphEditContractUnitTest(unittest.TestCase):
    def _valid_dsl(self) -> dict:
        return {
            "nodes": [
                {"id": "draft-1", "type": "Entity", "name": "A"},
                {"id": "draft-2", "type": "Entity", "name": "B"},
            ],
            "edges": [
                {"from": {"id": "draft-1"}, "to": {"id": "draft-2"}, "predicate": "REL"},
            ],
        }

    def test_parse_accepts_template_graph_with_temporary_ids(self):
        dsl = self._valid_dsl()
        contract = parse_graph_edit_draft_contract(dsl, object_kind="template_graph")

        self.assertEqual(contract.object_kind, "template_graph")
        self.assertEqual(len(contract.nodes), 2)
        self.assertEqual(len(contract.edges), 1)
        self.assertEqual(contract.edges[0].edge_type, "REL")

    def test_parse_rejects_temporary_ids_for_curated_business_graph(self):
        dsl = self._valid_dsl()
        with self.assertRaisesRegex(WorkflowGraphEditContractError, "temporary node_id"):
            parse_graph_edit_draft_contract(dsl, object_kind="curated_business_graph")

    def test_parse_rejects_duplicate_edges(self):
        dsl = self._valid_dsl()
        dsl["edges"].append({"from": "draft-1", "to": "draft-2", "type": "REL"})
        with self.assertRaisesRegex(WorkflowGraphEditContractError, "duplicate edge"):
            parse_graph_edit_draft_contract(dsl, object_kind="template_graph")

    def test_parse_rejects_missing_node_reference(self):
        dsl = self._valid_dsl()
        dsl["edges"] = [{"from": "draft-1", "to": "missing", "type": "REL"}]
        with self.assertRaisesRegex(WorkflowGraphEditContractError, "missing target node"):
            parse_graph_edit_draft_contract(dsl, object_kind="template_graph")

    def test_parse_rejects_cycle_with_explicit_integrity_signal(self):
        dsl = self._valid_dsl()
        dsl["edges"].append({"from": "draft-2", "to": "draft-1", "type": "REL"})
        with self.assertRaisesRegex(WorkflowGraphEditContractError, "workflow graph contains a cycle"):
            parse_graph_edit_draft_contract(dsl, object_kind="template_graph")

    def test_parse_rejects_system_managed_node_fields(self):
        dsl = self._valid_dsl()
        dsl["nodes"][0]["revision"] = 3
        with self.assertRaisesRegex(WorkflowGraphEditContractError, "system-managed fields"):
            parse_graph_edit_draft_contract(dsl, object_kind="template_graph")

    def test_template_create_version_enforces_edit_contract_guardrails(self):
        service = WorkflowGraphTemplateService()
        state = {
            "base_version": 2,
            "templates": {
                "tpl-1": {
                    "template_id": "tpl-1",
                    "name": "template",
                    "description": "",
                    "metadata": {},
                    "active_version_id": None,
                    "created_at": "2026-03-07T00:00:00+00:00",
                    "updated_at": "2026-03-07T00:00:00+00:00",
                    "versions": {},
                }
            },
        }

        with patch("app.services.workflow_graph.templates.current_project_key", return_value="demo_proj"), patch(
            "app.services.workflow_graph.templates.get_ingest_config",
            return_value={"payload": state},
        ), patch(
            "app.services.workflow_graph.templates.upsert_ingest_config",
            side_effect=lambda *_args, **kwargs: {"payload": kwargs.get("payload")},
        ):
            with self.assertRaisesRegex(ValueError, "missing target node"):
                service.create_version(
                    "tpl-1",
                    {
                        "base_version": 2,
                        "graph_object_kind": "template_graph",
                        "version_id": "v-bad",
                        "dsl": {
                            "nodes": [{"id": "draft-1", "type": "Entity"}],
                            "edges": [{"from": "draft-1", "to": "missing", "type": "REL"}],
                        },
                    },
                )


if __name__ == "__main__":
    unittest.main()
