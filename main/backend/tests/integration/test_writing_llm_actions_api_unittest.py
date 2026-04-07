from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient

    from app.contracts.schemas.writing import LlmActionHistoryItem, LlmActionResponse, TemplateValidateResponse
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class WritingLlmActionsApiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"writing llm action tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "writing-llm-actions"}

    def test_template_validate_success(self):
        with patch(
            "app.api.writing.validate_template_payload",
            return_value=TemplateValidateResponse(valid=True),
        ):
            response = self.client.post(
                "/api/v1/writing/templates/validate",
                json={"project_key": "demo_proj", "template_key": "market_weekly", "strict": True},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["valid"])

    def test_llm_action_and_history_success(self):
        history_item = LlmActionHistoryItem(job_id=7, job_type="wr_action", status="completed")
        with (
            patch(
                "app.api.writing.dispatch_action",
                return_value=LlmActionResponse(
                    content="Output",
                    mode="selection_rewrite",
                    trace_id="trace-1",
                    job_id=7,
                    capability_truth={
                        "contract_version": "writing.llm_action.capability_truth.v1",
                        "declared_capability": "writing_action",
                        "implementation_kind": "rule_template_action",
                        "real_model_path": False,
                        "fallback_path": True,
                        "route_kind": "sync",
                        "status": "completed",
                    },
                ),
            ),
            patch("app.api.writing.get_action_history", return_value=[history_item]),
            patch("app.api.writing.get_action_detail", return_value=history_item),
        ):
            action_response = self.client.post(
                "/api/v1/writing/llm-actions",
                json={"project_key": "demo_proj", "action_id": "selection_rewrite", "input_markdown": "draft", "async": False},
                headers=self.headers,
            )
            history_response = self.client.get("/api/v1/writing/llm-actions/history", headers=self.headers)
            detail_response = self.client.get("/api/v1/writing/llm-actions/7", headers=self.headers)

        self.assertEqual(action_response.status_code, 200)
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(action_response.json()["data"]["job_id"], 7)
        self.assertEqual(action_response.json()["data"]["capability_truth"]["implementation_kind"], "rule_template_action")
        self.assertEqual(history_response.json()["data"]["items"][0]["job_id"], 7)


if __name__ == "__main__":
    unittest.main()
