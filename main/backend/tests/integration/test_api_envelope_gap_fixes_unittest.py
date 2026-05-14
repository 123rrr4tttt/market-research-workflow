from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from app.api.codex_auth import codex_auth_login
    from app.api.skills import SkillInvokeRequest, invoke_skill_api
    from app.contracts.errors import ErrorCode

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ApiEnvelopeGapFixesIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"api envelope integration tests require backend dependencies: {_IMPORT_ERROR}")

    def test_codex_auth_login_returns_error_envelope_when_cli_login_missing(self):
        with (
            patch("app.api.codex_auth.codex_oauth_enabled", return_value=False),
            patch("app.api.codex_auth.has_valid_token_sink", return_value=False),
        ):
            response = codex_auth_login(next_url=None)

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.body)
        self.assertEqual(payload["status"], "error")
        self.assertIsNone(payload["data"])
        self.assertEqual(payload["error"]["code"], "INVALID_INPUT")
        self.assertEqual(payload["error"]["details"]["reason_code"], "codex_cli_login_required")
        self.assertEqual(payload["detail"]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(response.headers.get("x-error-code"), "INVALID_INPUT")
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_codex_auth_login_prefers_existing_token_sink(self):
        with (
            patch("app.api.codex_auth.codex_oauth_enabled", return_value=True),
            patch("app.api.codex_auth.has_valid_token_sink", return_value=True),
        ):
            response = codex_auth_login(next_url="http://localhost:5173")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "http://localhost:5173")

    def test_codex_auth_login_can_force_browser_oauth(self):
        with (
            patch("app.api.codex_auth.codex_oauth_enabled", return_value=True),
            patch("app.api.codex_auth.has_valid_token_sink", return_value=True),
            patch("app.api.codex_auth.build_authorize_url", return_value="https://auth.openai.com/oauth/authorize"),
        ):
            response = codex_auth_login(next_url="http://localhost:5173", force_oauth=True)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "https://auth.openai.com/oauth/authorize")

    def test_skills_invoke_success_returns_ok_envelope(self):
        with patch(
            "app.api.skills.invoke_skill",
            return_value={
                "skill_id": "demo.skill",
                "result": {"accepted": True},
                "trace_id": "trace-1",
                "consumer": "skills.api",
                "actor_role": "orchestration_runtime",
                "requested_permissions": ["read"],
                "owner": "qa",
                "execution_profile": "default",
                "concurrency_class": "read_only",
                "approval_policy": {"default": "optional"},
                "artifact_contract": {"primary": "memory.md"},
                "approval_request": None,
            },
        ):
            response = invoke_skill_api(
                SkillInvokeRequest(skill_id="demo.skill", payload={"query": "ping"})
            )

        self.assertEqual(response["status"], "ok")
        self.assertIsNone(response["error"])
        self.assertEqual(response["data"]["skill_id"], "demo.skill")
        self.assertEqual(response["data"]["skill_meta"]["permissions"], ["read"])
        self.assertEqual(response["data"]["skill_meta"]["execution_profile"], "default")
        self.assertEqual(response["data"]["skill_meta"]["concurrency_class"], "read_only")
        self.assertEqual(response["data"]["skill_meta"]["approval_policy"]["default"], "optional")
        self.assertEqual(response["data"]["skill_meta"]["artifact_contract"]["primary"], "memory.md")
        self.assertIsNone(response["data"]["skill_meta"]["approval_request"])

    def test_skills_invoke_approval_required_returns_error_envelope(self):
        with patch(
            "app.api.skills.invoke_skill",
            side_effect=PermissionError("skill invoke denied: demo.skill (approval_required:approval-1)"),
        ):
            response = invoke_skill_api(
                SkillInvokeRequest(
                    skill_id="demo.skill",
                    payload={},
                    session_id="as-1",
                    task_id="task-1",
                )
            )

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.body)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_INPUT")
        self.assertEqual(payload["error"]["details"]["category"], "skill_permission_denied")
        self.assertIn("approval_required:approval-1", payload["error"]["message"])

    def test_skills_invoke_write_conflict_returns_error_envelope(self):
        with patch(
            "app.api.skills.invoke_skill",
            side_effect=RuntimeError("skill invoke denied: demo.skill (write_set_conflict)"),
        ):
            response = invoke_skill_api(
                SkillInvokeRequest(
                    skill_id="demo.skill",
                    payload={},
                    session_id="as-1",
                    task_id="task-1",
                )
            )

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.body)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_INPUT")
        self.assertEqual(payload["error"]["details"]["category"], "skill_write_conflict")
        self.assertIn("write_set_conflict", payload["error"]["message"])

    def test_skills_invoke_permission_error_returns_error_envelope(self):
        with patch("app.api.skills.invoke_skill", side_effect=PermissionError("approval_granted is required")):
            response = invoke_skill_api(SkillInvokeRequest(skill_id="demo.skill", payload={}))

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.body)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_INPUT")
        self.assertEqual(payload["error"]["details"]["category"], "skill_permission_denied")
        self.assertEqual(payload["detail"]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(response.headers.get("x-error-code"), "INVALID_INPUT")
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_skills_invoke_maps_generic_exception_to_error_status(self):
        with patch("app.api.skills.invoke_skill", side_effect=RuntimeError("skill not found")):
            response = invoke_skill_api(SkillInvokeRequest(skill_id="missing.skill", payload={}))

        self.assertEqual(response.status_code, 404)
        payload = json.loads(response.body)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "NOT_FOUND")
        self.assertEqual(payload["error"]["message"], "skill not found")
        self.assertEqual(payload["detail"]["error"]["code"], "NOT_FOUND")
        self.assertEqual(response.headers.get("x-error-code"), "NOT_FOUND")
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)

    def test_skills_invoke_maps_config_error_to_400(self):
        with patch("app.api.skills.invoke_skill", side_effect=RuntimeError("missing API key")):
            response = invoke_skill_api(SkillInvokeRequest(skill_id="missing.skill", payload={}))

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.body)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "CONFIG_ERROR")
        self.assertEqual(payload["error"]["message"], "missing API key")
        self.assertEqual(payload["detail"]["error"]["code"], "CONFIG_ERROR")
        self.assertEqual(response.headers.get("x-error-code"), "CONFIG_ERROR")
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.CONFIG_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.CONFIG_ERROR.value)


if __name__ == "__main__":
    unittest.main()
