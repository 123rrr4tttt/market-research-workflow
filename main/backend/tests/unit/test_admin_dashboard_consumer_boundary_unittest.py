from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_admin_dashboard_consumer_boundary import (  # noqa: E402
    CONTRACT_VERSION,
    build_check,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


def _scope_request(headers: dict[str, str] | None = None, query: str = "") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (name.lower().encode("ascii"), value.encode("utf-8"))
                for name, value in (headers or {}).items()
            ],
            "query_string": query.encode("utf-8"),
        }
    )


class AdminDashboardConsumerBoundaryUnitTestCase(unittest.TestCase):
    def test_checker_passes_for_wave13_admin_dashboard_python_read_slice(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["topic_id"], "2026-03-14-consumer-side-modularization")
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["validation"]["passed"])
        self.assertEqual(result["validation"]["direct_instance_extracted_data_read_count"], 0)
        self.assertEqual(result["validation"]["allowed_sql_json_expression_count"], 0)

        surfaces = {item["path"]: item for item in result["checked_surfaces"]}
        self.assertIn("main/backend/app/api/dashboard.py", surfaces)
        self.assertIn("main/backend/app/api/admin.py", surfaces)
        self.assertIn("main/backend/app/services/document_admin.py", surfaces)

        dashboard_functions = {
            item["name"]: item
            for item in surfaces["main/backend/app/api/dashboard.py"]["functions"]
        }
        self.assertEqual(
            set(dashboard_functions),
            {"get_sentiment_analysis", "get_sentiment_sources"},
        )
        for function in dashboard_functions.values():
            self.assertTrue(function["passed"], function)
            self.assertFalse(function["missing_boundary_calls"], function)

        admin_functions = {
            item["name"]: item
            for item in surfaces["main/backend/app/api/admin.py"]["functions"]
        }
        for name in (
            "_augment_market_graph_with_topic_structured",
            "list_social_data",
            "get_content_graph",
            "get_market_graph",
            "get_policy_graph",
        ):
            self.assertIn(name, admin_functions)
            self.assertTrue(admin_functions[name]["passed"], admin_functions[name])
            self.assertFalse(admin_functions[name]["missing_boundary_calls"], admin_functions[name])
        self.assertEqual(
            admin_functions["get_content_graph"]["required_boundary_calls"],
            ["get_admin_content_graph"],
        )
        self.assertEqual(
            admin_functions["get_market_graph"]["required_boundary_calls"],
            ["get_admin_market_graph"],
        )
        self.assertEqual(
            admin_functions["get_policy_graph"]["required_boundary_calls"],
            ["get_admin_policy_graph"],
        )

        document_admin_functions = {
            item["name"]: item
            for item in surfaces["main/backend/app/services/document_admin.py"]["functions"]
        }
        self.assertEqual(
            document_admin_functions["get_admin_content_graph"]["required_boundary_calls"],
            ["get_social_platform_label", "get_social_sentiment"],
        )
        self.assertEqual(
            document_admin_functions["get_admin_market_graph"]["required_boundary_calls"],
            ["get_market_data"],
        )
        self.assertEqual(
            document_admin_functions["get_admin_policy_graph"]["required_boundary_calls"],
            ["get_policy_data"],
        )
        for function in document_admin_functions.values():
            self.assertTrue(function["passed"], function)
            self.assertFalse(function["missing_boundary_calls"], function)

    def test_checker_defers_sql_json_predicates_to_wave15_facade_gate(self) -> None:
        result = build_check(REPO_ROOT)
        admin_surface = next(
            item
            for item in result["checked_surfaces"]
            if item["path"] == "main/backend/app/api/admin.py"
        )
        by_name = {item["name"]: item for item in admin_surface["functions"]}

        self.assertEqual(by_name["get_content_graph"]["sql_json_expression_count"], 0)
        self.assertEqual(by_name["get_market_graph"]["sql_json_expression_count"], 0)
        self.assertIn("Wave15", result["boundary_rule"])

    def test_dashboard_scope_keeps_payload_explicit_and_query_explicit(self) -> None:
        from app.api.dashboard import _dashboard_project_key_from_request

        payload_request = _scope_request(headers={"X-Project-Key": "header-project"})
        self.assertEqual(
            _dashboard_project_key_from_request(payload_request, "payload-project"),
            "payload_project",
        )

        header_request = _scope_request(headers={"X-Project-Key": "header-project"})
        header_request.state.project_key_resolved = "header-project"
        header_request.state.project_key_source = "header"
        self.assertEqual(_dashboard_project_key_from_request(header_request), "header_project")

        query_request = _scope_request(query="project_key=query-project")
        query_request.state.project_key_resolved = "fallback-state"
        query_request.state.project_key_source = "fallback"
        self.assertEqual(_dashboard_project_key_from_request(query_request), "query_project")

    def test_admin_scope_falls_back_to_active_database_project(self) -> None:
        from app.api.admin import _project_key_from_request

        class FakeResult:
            def fetchone(self) -> tuple[str]:
                return ("database-project",)

        class FakeConnection:
            def __enter__(self) -> "FakeConnection":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc_value: BaseException | None,
                traceback: object | None,
            ) -> bool:
                return False

            def execute(self, statement: object) -> FakeResult:
                return FakeResult()

        class FakeEngine:
            def connect(self):
                return FakeConnection()

        with patch("app.models.base.engine", FakeEngine()):
            self.assertEqual(_project_key_from_request(_scope_request()), "database-project")

    def test_admin_scope_uses_shared_resolved_fallback_state(self) -> None:
        from app.api.admin import _project_key_from_request

        request = _scope_request()
        request.state.project_key_resolved = "state-fallback"
        request.state.project_key_source = "fallback"
        self.assertEqual(_project_key_from_request(request), "state-fallback")

    def test_dashboard_rejects_fallback_state_and_uses_declared_fallback(self) -> None:
        from app.api.dashboard import _dashboard_project_key_from_request

        request = _scope_request()
        request.state.project_key_resolved = "state-fallback"
        request.state.project_key_source = "fallback"
        settings = SimpleNamespace(active_project_key="settings-project")

        with patch("app.api.dashboard.settings", settings):
            self.assertEqual(_dashboard_project_key_from_request(request), "settings_project")


if __name__ == "__main__":
    unittest.main()
