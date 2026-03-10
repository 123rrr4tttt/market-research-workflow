from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.contracts.schemas.writing import LlmActionRequest
    from app.services.writing.llm_action_service import dispatch_action

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class WritingLlmActionServiceUnitTestCase(unittest.TestCase):
    def setUp(self):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"writing llm action service tests require backend dependencies: {_IMPORT_ERROR}")

    def test_dispatch_action_rejects_when_agent_boundary_denied(self):
        payload = LlmActionRequest(
            project_key="demo_proj",
            action_id="selection_rewrite",
            input_markdown="draft",
            selection_text="rewrite this",
            agent_role="orchestration_runtime",
        )
        with (
            patch("app.services.writing.llm_action_service.start_job", return_value=101),
            patch("app.services.writing.llm_action_service.complete_job") as mocked_complete,
        ):
            response = dispatch_action(payload)

        self.assertEqual(response.status, "rejected")
        self.assertEqual(response.mode, "selection_rewrite")
        self.assertFalse(response.dependency_gate["passed"])
        self.assertTrue(any("agent_role_not_allowed_for_consumer" in item for item in response.warnings))
        self.assertEqual(mocked_complete.call_args.kwargs["status"], "rejected")

    def test_dispatch_action_keeps_platform_observability_when_allowed(self):
        payload = LlmActionRequest(
            project_key="demo_proj",
            action_id="section_expand",
            input_markdown="# Draft",
            agent_role="business_capability_wrapper",
        )
        with (
            patch("app.services.writing.llm_action_service.start_job", return_value=102),
            patch("app.services.writing.llm_action_service.complete_job"),
        ):
            response = dispatch_action(payload)

        self.assertEqual(response.status, "completed")
        self.assertTrue(response.dependency_gate["passed"])
        self.assertIn("agent_boundary", response.action_boundary)
        self.assertIn("audit", response.observability)


if __name__ == "__main__":
    unittest.main()
