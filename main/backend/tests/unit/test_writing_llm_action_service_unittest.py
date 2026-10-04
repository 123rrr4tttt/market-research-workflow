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
    from app.services.writing.llm_action_service import _job_to_history_item, dispatch_action

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
        self.assertEqual(response.capability_truth["implementation_kind"], "rule_template_action")
        self.assertFalse(response.capability_truth["real_model_path"])
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
            patch("app.services.writing.llm_action_service.complete_job") as mocked_complete,
        ):
            response = dispatch_action(payload)

        self.assertEqual(response.status, "completed")
        self.assertTrue(response.dependency_gate["passed"])
        self.assertEqual(response.capability_truth["implementation_kind"], "rule_template_action")
        self.assertFalse(response.capability_truth["real_model_path"])
        self.assertIn("agent_boundary", response.action_boundary)
        self.assertIn("audit", response.observability)
        complete_result = mocked_complete.call_args.kwargs["result"]
        runtime_readback = complete_result["runtime_readback"]
        self.assertEqual(runtime_readback["line_key"], "writing_knowledge_graph_agent")
        self.assertEqual(runtime_readback["run_id"], "102")
        self.assertEqual(runtime_readback["worker_name"], "local.writing_llm_action_service")
        self.assertEqual(runtime_readback["queue"], "local.writing_knowledge_graph_agent")
        self.assertEqual(runtime_readback["trace_id"], response.trace_id)
        self.assertEqual(runtime_readback["status"], "completed")
        self.assertTrue(
            any(
                isinstance(item, dict) and item.get("event") == "completed"
                for item in runtime_readback["events"]
            )
        )

    def test_async_request_completes_inline_and_returns_the_generated_content(self):
        responses = []
        complete_calls = []
        start_calls = []
        for requested_async in (False, True):
            payload = LlmActionRequest(
                project_key="demo_proj",
                action_id="outline_generate",
                input_markdown="# Alpha\n## Beta",
                async_mode=requested_async,
                agent_role="business_capability_wrapper",
            )
            with (
                patch(
                    "app.services.writing.llm_action_service.start_job",
                    side_effect=lambda *args, **kwargs: start_calls.append((args, kwargs)) or 103,
                ),
                patch(
                    "app.services.writing.llm_action_service.complete_job",
                    side_effect=lambda *args, **kwargs: complete_calls.append((args, kwargs)),
                ),
            ):
                responses.append(dispatch_action(payload))

        sync_response, inline_response = responses
        self.assertEqual(sync_response.status, "completed")
        self.assertEqual(inline_response.status, "completed")
        self.assertEqual(sync_response.content, "- Alpha\n- Beta")
        self.assertEqual(inline_response.content, sync_response.content)
        self.assertEqual(sync_response.requested_async, False)
        self.assertEqual(inline_response.requested_async, True)
        self.assertTrue(sync_response.async_honored)
        self.assertFalse(inline_response.async_honored)
        self.assertEqual(sync_response.execution_mode, "inline")
        self.assertEqual(inline_response.execution_mode, "inline")
        self.assertIn("async_not_supported_executed_inline", inline_response.warnings)
        self.assertEqual([call[1]["status"] for call in complete_calls], ["completed", "completed"])
        for index, response in enumerate(responses):
            result = complete_calls[index][1]["result"]
            self.assertEqual(result["content"], response.content)
            self.assertEqual(result["execution_mode"], "inline")
            self.assertEqual(result["requested_async"], response.requested_async)
            self.assertEqual(result["async_honored"], response.async_honored)
            self.assertEqual(result["runtime_readback"]["execution_mode"], "inline")
            self.assertEqual(result["runtime_readback"]["async_honored"], response.async_honored)
            self.assertEqual(result["capability_truth"]["contract_version"], "writing.llm_action.capability_truth.v2")
            self.assertEqual(result["capability_truth"]["execution_mode"], "inline")
            request_meta = start_calls[index][0][1]
            self.assertEqual(request_meta["requested_async"], response.requested_async)

    def test_action_history_projects_new_execution_metadata_and_accepts_old_records(self):
        current = _job_to_history_item(
            {
                "id": 104,
                "job_type": "wr_action",
                "status": "completed",
                "params": {
                    "content": "Persisted output",
                    "requested_async": True,
                    "execution_mode": "inline",
                    "async_honored": False,
                },
            }
        )
        legacy = _job_to_history_item(
            {"id": 105, "job_type": "wr_action", "status": "completed", "params": {}}
        )

        self.assertEqual(current.request_meta["requested_async"], True)
        self.assertEqual(current.result_summary["content"], "Persisted output")
        self.assertEqual(current.content, "Persisted output")
        self.assertIsNone(legacy.content)
        self.assertEqual(current.result_summary["requested_async"], True)
        self.assertEqual(current.result_summary["execution_mode"], "inline")
        self.assertFalse(current.result_summary["async_honored"])
        self.assertIsNone(legacy.result_summary["execution_mode"])


if __name__ == "__main__":
    unittest.main()
