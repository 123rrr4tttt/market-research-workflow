from __future__ import annotations

import sys
import unittest
from contextlib import nullcontext
from datetime import datetime
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
    def test_document_admin_material_query_executes_current_predicates(self) -> None:
        from app.models.entities import Material

        from app.services import document_admin

        material = Material(
            id=41,
            title="Material title",
            material_type="social_sentiment",
            content="Material body",
            uri="https://example.test/material",
            extracted_data={"sentiment": {"topic": "materials"}},
            created_at=datetime(2026, 1, 2),
        )

        class _Result:
            def __init__(self, *, scalar_value: int = 0, rows: list[Material] | None = None) -> None:
                self.scalar_value = scalar_value
                self.rows = rows or []

            def scalar(self) -> int:
                return self.scalar_value

            def scalars(self) -> "_Result":
                return self

            def all(self) -> list[Material]:
                return self.rows

        class _Session:
            def __init__(self) -> None:
                self.results = iter([_Result(scalar_value=1), _Result(rows=[material])])

            def __enter__(self) -> "_Session":
                return self

            def __exit__(self, *_args: object) -> bool:
                return False

            def execute(self, _statement: object) -> _Result:
                return next(self.results)

        with (
            patch.object(document_admin, "bind_project", return_value=nullcontext()),
            patch.object(document_admin, "SessionLocal", return_value=_Session()),
        ):
            result = document_admin.list_admin_materials(
                "demo_proj",
                document_admin.AdminMaterialListQuery(
                    page=1,
                    page_size=10,
                    has_extracted_data=True,
                ),
            )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["material_id"], 41)
        self.assertEqual(result["items"][0]["material_type"], "social_sentiment")

    def test_document_admin_graph_paths_execute_current_adapters_and_doc_types(self) -> None:
        from app.models.entities import Material

        from app.services import document_admin

        material = Material(
            id=41,
            title="Material title",
            material_type="social_sentiment",
            content="Material body",
            uri="https://example.test/material",
            extracted_data={
                "platform": "generic",
                "sentiment": {
                    "sentiment_orientation": "positive",
                    "topic": "materials",
                    "key_phrases": ["material"],
                },
            },
            created_at=datetime(2026, 1, 2),
        )

        class _RowsResult:
            def __init__(self, rows: list[Material]) -> None:
                self.rows = rows

            def scalars(self) -> "_RowsResult":
                return self

            def all(self) -> list[Material]:
                return self.rows

        class _Session:
            def __init__(self, rows: list[Material]) -> None:
                self.rows = rows
                self.committed = False

            def __enter__(self) -> "_Session":
                return self

            def __exit__(self, *_args: object) -> bool:
                return False

            def execute(self, _statement: object) -> _RowsResult:
                return _RowsResult(self.rows)

            def commit(self) -> None:
                self.committed = True

            def rollback(self) -> None:
                return None

        class _Customization:
            def get_field_mapping(self) -> dict[str, object]:
                return {}

        export_session = _Session([material])
        with patch.object(document_admin, "SessionLocal", return_value=export_session):
            exported = document_admin.export_admin_graph([41])
        self.assertEqual({node["type"] for node in exported["nodes"]}, {"Post", "Keyword", "Topic"})

        content_session = _Session([material])
        writer_summary = SimpleNamespace(
            attempted=3,
            inserted_or_updated=3,
            aliases_written=0,
            edges_written=2,
            skipped=0,
        )
        with (
            patch.object(document_admin, "bind_project", return_value=nullcontext()),
            patch.object(document_admin, "SessionLocal", return_value=content_session),
            patch(
                "app.services.graph.doc_types.get_project_customization",
                return_value=_Customization(),
            ),
            patch(
                "app.services.graph.persistence.GraphNodeWriter.persist_graph_nodes",
                return_value=writer_summary,
            ),
        ):
            content_graph = document_admin.get_admin_content_graph(
                "demo_proj",
                start_date=None,
                end_date=None,
                platform=None,
                topic=None,
                limit=10,
            )

        self.assertEqual({node["type"] for node in content_graph["nodes"]}, {"Post", "Keyword", "Topic"})
        self.assertTrue(content_session.committed)

    def test_document_admin_empty_graph_queries_execute_all_delayed_predicates(self) -> None:
        from app.services import document_admin

        class _EmptyResult:
            def scalar(self) -> int:
                return 0

            def scalars(self) -> "_EmptyResult":
                return self

            def all(self) -> list[object]:
                return []

        class _EmptySession:
            def __enter__(self) -> "_EmptySession":
                return self

            def __exit__(self, *_args: object) -> bool:
                return False

            def execute(self, _statement: object) -> _EmptyResult:
                return _EmptyResult()

        with (
            patch.object(document_admin, "bind_project", return_value=nullcontext()),
            patch.object(document_admin, "SessionLocal", side_effect=lambda: _EmptySession()),
        ):
            market = document_admin.get_admin_market_graph(
                "demo_proj",
                start_date=None,
                end_date=None,
                state="CA",
                game="lottery",
                deep_view=False,
                topic_scope=None,
                limit=10,
                market_graph_augmenter=lambda *_args: None,
            )
            policy = document_admin.get_admin_policy_graph(
                "demo_proj",
                start_date=None,
                end_date=None,
                state="CA",
                policy_type="regulation",
                limit=10,
            )
            social = document_admin.list_admin_social_data(
                document_admin.AdminSocialDataListQuery(
                    page=1,
                    page_size=10,
                    platform="generic",
                    sentiment_orientation="positive",
                ),
                projector=lambda _row: {},
            )

        self.assertEqual(market, {"graph_schema_version": "v1", "nodes": [], "edges": []})
        self.assertEqual(policy, {"graph_schema_version": "v1", "nodes": [], "edges": []})
        self.assertEqual(social, {"items": [], "total": 0, "page": 1, "page_size": 10})

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

        query_request = _scope_request(
            headers={"X-Project-Key": "header-project"},
            query="project_key=query-project",
        )
        query_request.state.project_key_resolved = "fallback-state"
        query_request.state.project_key_source = "fallback"
        self.assertEqual(_dashboard_project_key_from_request(query_request), "header_project")

        raw_query_request = _scope_request(query="project_key=query-project")
        raw_query_request.state.project_key_resolved = "fallback-state"
        raw_query_request.state.project_key_source = "fallback"
        self.assertEqual(
            _dashboard_project_key_from_request(raw_query_request),
            "query_project",
        )

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

    def test_dashboard_uses_shared_resolved_fallback_before_declared_fallback(self) -> None:
        from app.api.dashboard import _dashboard_project_key_from_request
        from app.services.projects.context import resolve_request_project_context

        request = _scope_request()
        request.state.project_key_resolved = "state-fallback"
        request.state.project_key_source = "fallback"
        settings = SimpleNamespace(active_project_key="settings-project")

        with patch("app.api.dashboard.settings", settings):
            self.assertEqual(_dashboard_project_key_from_request(request), "state_fallback")
            self.assertEqual(
                _dashboard_project_key_from_request(_scope_request()),
                "settings_project",
            )
            self.assertEqual(
                resolve_request_project_context(
                    request,
                    fallback=lambda: "declared-fallback",
                    use_resolved_fallback=False,
                ),
                ("declared-fallback", "fallback", True),
            )


if __name__ == "__main__":
    unittest.main()
