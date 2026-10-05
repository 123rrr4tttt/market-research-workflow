from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import agent_cell
from app.services.agent_core.macro_environment import _failure
from app.services.projects.context import bind_project


class AgentCellApiTests(unittest.TestCase):
    def setUp(self):
        self.service = SimpleNamespace(store=SimpleNamespace(list_project_artifacts=Mock(return_value=[])))
        self.registry = object()
        self.descriptor = {"project_key": "cell_test", "definition": {"cell_id": "base"}}
        self.resolved = SimpleNamespace(descriptor=lambda: self.descriptor, environment_digest="digest")
        self.service_patch = patch.object(agent_cell, "get_agent_session_service", return_value=self.service)
        self.registry_patch = patch.object(agent_cell, "build_project_core_tool_registry", return_value=self.registry)
        self.resolve_patch = patch.object(agent_cell, "resolve_macro_environment", return_value=self.resolved)
        self.service_patch.start()
        self.registry_patch.start()
        self.resolve = self.resolve_patch.start()
        self.addCleanup(patch.stopall)

    def test_base_uses_bound_project_and_existing_descriptor_only(self):
        with bind_project("cell_test"):
            result = agent_cell.read_agent_cell()
        self.assertEqual(result["data"], {"environment": self.descriptor, "environment_digest": "digest"})
        args = self.resolve.call_args.args
        self.assertEqual(args[:4], (self.service, "cell_test", (), ()))
        self.assertEqual(args[4][0].name, "skills")
        self.assertIs(args[5], self.registry)
        self.service.store.list_project_artifacts.assert_called_once_with(project_key="cell_test")

    def test_explicit_package_is_forwarded_without_activation(self):
        with bind_project("cell_test"):
            agent_cell.read_agent_cell("package-a", "3")
        self.assertEqual(self.resolve.call_args.args[2:4], (("package-a",), ("3",)))
        self.service.store.list_project_artifacts.assert_not_called()

    def test_partial_identity_rejected_without_resolving(self):
        with bind_project("cell_test"), self.assertRaises(HTTPException) as error:
            agent_cell.read_agent_cell("package-a", None)
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(error.exception.detail["error"]["code"], "exact_package_identity_required")
        self.resolve.assert_not_called()

    def test_multiple_packages_preserve_choices_and_do_not_pick_one(self):
        self.service.store.list_project_artifacts.return_value = [
            {"artifact_type": "agent_macro.registration_package", "name": f"macro-registration/{name}@1.json",
             "metadata": {"activation_status": "activated"}}
            for name in ("a", "b")
        ]
        with bind_project("cell_test"), self.assertRaises(HTTPException) as error:
            agent_cell.read_agent_cell()
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(error.exception.detail["error"]["details"]["activated"], [("a", "1"), ("b", "1")])
        self.resolve.assert_not_called()

    def test_invalid_environment_does_not_fall_back(self):
        self.resolve.return_value = _failure("macro_environment_invalid", "invalid skill digest")
        with bind_project("cell_test"), self.assertRaises(HTTPException) as error:
            agent_cell.read_agent_cell("package-a", "1")
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(error.exception.detail["error"]["message"], "invalid skill digest")
        self.assertEqual(self.resolve.call_count, 1)

    def test_missing_project_rejected_before_service_read(self):
        with patch.object(agent_cell, "current_project_key", return_value=""), self.assertRaises(HTTPException) as error:
            agent_cell.read_agent_cell()
        self.assertEqual(error.exception.status_code, 400)
        self.resolve.assert_not_called()

    def test_http_route_keeps_existing_agent_auth_boundary(self):
        from app import main

        with patch.object(main.settings, "codex_auth_enabled", True), \
                patch.object(main, "_parse_codex_auth_tokens", return_value={"test-cell-token"}), \
                patch.object(main, "_resolve_codex_oauth_actor_context", return_value=None):
            response = TestClient(main.app).get("/api/v1/agent-chat/cell", headers={"X-Project-Key": "cell_test"})
        self.assertEqual(response.status_code, 401)
        self.resolve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
