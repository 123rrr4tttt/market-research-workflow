from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.contracts.schemas.writing import LlmActionRequest, WritingPrimaryLoopCheckpoint
    from app.services.writing.primary_loop_service import build_wave_a_baseline_matrix, evaluate_primary_loop_state

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class WritingPrimaryLoopServiceUnitTestCase(unittest.TestCase):
    def setUp(self):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"writing primary loop service tests require backend dependencies: {_IMPORT_ERROR}")

    def test_wave_a_baseline_matrix_marks_wave_b_deferred_items_open(self):
        matrix = build_wave_a_baseline_matrix()
        by_id = {item.capability_id: item for item in matrix.capabilities}

        self.assertIn("graph_context_adapter_boundary", by_id)
        self.assertFalse(by_id["graph_context_adapter_boundary"].still_open)
        self.assertIn("cross_theme_dependency_merge_gate", by_id)
        self.assertFalse(by_id["cross_theme_dependency_merge_gate"].still_open)
        self.assertIn("non_markdown_export_adapters", by_id)
        self.assertTrue(by_id["non_markdown_export_adapters"].still_open)
        self.assertIn("Writing page and writing API already exist", matrix.repo_reality)

    def test_no_graph_happy_path_can_reach_write_back_ready(self):
        state = evaluate_primary_loop_state(
            WritingPrimaryLoopCheckpoint(
                project_key="demo_proj",
                document_id=101,
                has_markdown_body=True,
                saved_version=3,
                has_context_cards=True,
                has_accepted_citation=True,
                llm_action_invoked=True,
                has_write_back_candidate=True,
                graph_context_attached=False,
            )
        )

        self.assertIsNone(state.next_required_stage)
        self.assertTrue(state.no_graph_happy_path_complete)
        self.assertIn("graph_context_adapter", state.optional_layers)

    def test_missing_citation_is_detected_even_if_action_already_invoked(self):
        state = evaluate_primary_loop_state(
            WritingPrimaryLoopCheckpoint(
                document_id=101,
                has_markdown_body=True,
                saved_version=2,
                has_context_cards=True,
                has_accepted_citation=False,
                llm_action_invoked=True,
                has_write_back_candidate=False,
            )
        )

        self.assertEqual(state.next_required_stage, "citation_applied")
        self.assertIn("action_executed_before_citation_applied", state.ordering_violations)
        self.assertTrue(state.cross_theme_dependency_gate["passed"])

    def test_llm_action_request_infers_target_scope(self):
        selection_scope = LlmActionRequest(action_id="selection_rewrite", input_markdown="", selection_text="rewrite this")
        document_scope = LlmActionRequest(action_id="section_expand", input_markdown="# Draft", selection_text=None)

        self.assertEqual(selection_scope.target_scope, "selection")
        self.assertEqual(document_scope.target_scope, "document")

    def test_cross_theme_gate_blocks_invalid_graph_handoff_contract(self):
        state = evaluate_primary_loop_state(
            WritingPrimaryLoopCheckpoint(
                document_id=101,
                has_markdown_body=True,
                saved_version=2,
                has_context_cards=True,
                has_accepted_citation=True,
                llm_action_invoked=True,
                has_write_back_candidate=True,
                graph_context_attached=True,
                graph_handoff_contract_version="graph_handoff.beta",
            )
        )

        self.assertFalse(state.cross_theme_dependency_gate["passed"])
        self.assertEqual(state.cross_theme_dependency_gate["graph"]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
