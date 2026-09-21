from __future__ import annotations

import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

try:
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app
    from app.api.projects import (
        _build_initial_project_copy_insert_sql,
        _execute_seed_sql,
        _filter_seed_sql_text,
        _resolve_inject_target_key,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ProjectsCoreContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"projects core contract tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "projects-core-contract"}

    @staticmethod
    def _session_local_with_result(result: Mock) -> Mock:
        session = Mock()
        session.execute.return_value = result
        session_cm = Mock()
        session_cm.__enter__ = Mock(return_value=session)
        session_cm.__exit__ = Mock(return_value=None)
        return Mock(return_value=session_cm)

    def test_list_projects_returns_enveloped_items(self):
        rows = [
            SimpleNamespace(
                id=1,
                project_key="demo_proj",
                name="Demo",
                schema_name="tenant_demo_proj",
                enabled=True,
                is_active=True,
            ),
            SimpleNamespace(
                id=2,
                project_key="alpha_proj",
                name="Alpha",
                schema_name="tenant_alpha_proj",
                enabled=False,
                is_active=False,
            ),
            SimpleNamespace(
                id=3,
                project_key="missing_schema_proj",
                name="Missing Schema",
                schema_name="",
                enabled=True,
                is_active=False,
            ),
        ]
        result = Mock()
        result.scalars.return_value.all.return_value = rows

        with (
            patch("app.api.projects.bind_schema", return_value=nullcontext()),
            patch("app.api.projects.SessionLocal", self._session_local_with_result(result)),
        ):
            response = self.client.get("/api/v1/projects", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(payload["error"])
        items = payload["data"]["items"]
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["project_key"], "demo_proj")
        self.assertFalse(items[0]["archived"])
        self.assertTrue(items[0]["schema_ready"])
        self.assertTrue(items[0]["has_worker_fixture"])
        self.assertTrue(items[0]["nightly_matrix_eligible"])

        self.assertEqual(items[1]["project_key"], "alpha_proj")
        self.assertTrue(items[1]["archived"])
        self.assertTrue(items[1]["schema_ready"])
        self.assertFalse(items[1]["has_worker_fixture"])
        self.assertFalse(items[1]["nightly_matrix_eligible"])

        self.assertEqual(items[2]["project_key"], "missing_schema_proj")
        self.assertFalse(items[2]["archived"])
        self.assertFalse(items[2]["schema_ready"])
        self.assertFalse(items[2]["has_worker_fixture"])
        self.assertFalse(items[2]["nightly_matrix_eligible"])

    def test_project_detail_path_not_found_maps_to_not_found_error_code(self):
        result = Mock()
        result.scalar_one_or_none.return_value = None

        with (
            patch("app.api.projects.bind_schema", return_value=nullcontext()),
            patch("app.api.projects.SessionLocal", self._session_local_with_result(result)),
        ):
            response = self.client.post("/api/v1/projects/missing_proj/activate", headers=self.headers)

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)

    def test_invalid_parameter_maps_to_invalid_input_error_code(self):
        response = self.client.post(
            "/api/v1/projects/inject-initial",
            headers=self.headers,
            json={"project_key": "target_proj", "source_project_key": "   "},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_inject_initial_requires_explicit_target(self):
        with self.assertRaises(Exception) as ctx:
            _resolve_inject_target_key("   ", source_key="demo_proj", overwrite=True)
        self.assertEqual(getattr(ctx.exception, "status_code", None), 400)

    def test_inject_initial_missing_target_is_rejected_before_project_creation(self):
        response = self.client.post(
            "/api/v1/projects/inject-initial",
            headers=self.headers,
            json={"source_project_key": "demo_proj"},
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.INVALID_INPUT.value)

    def test_inject_target_allows_default_only_in_overwrite_mode(self):
        self.assertEqual(
            _resolve_inject_target_key("default", source_key="demo_proj", overwrite=True),
            "default",
        )
        with self.assertRaises(Exception) as ctx:
            _resolve_inject_target_key("default", source_key="demo_proj", overwrite=False)
        self.assertEqual(getattr(ctx.exception, "status_code", None), 409)

    def test_inject_initial_copy_sql_uses_common_columns_and_jsonb_conversion(self):
        sql = _build_initial_project_copy_insert_sql(
            source_schema="tenant_demo_proj",
            target_schema="tenant_batch84_matrix_proj",
            table_name="resource_pool_site_entries",
            source_columns=[
                {"column_name": "id", "udt_name": "int4"},
                {"column_name": "site_url", "udt_name": "varchar"},
                {"column_name": "capabilities", "udt_name": "varchar"},
                {"column_name": "source_only_legacy", "udt_name": "text"},
            ],
            target_columns=[
                {"column_name": "id", "udt_name": "int4"},
                {"column_name": "site_url", "udt_name": "varchar"},
                {"column_name": "capabilities", "udt_name": "jsonb"},
                {"column_name": "target_only_new", "udt_name": "text"},
            ],
        )

        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn('INSERT INTO "tenant_batch84_matrix_proj"."resource_pool_site_entries"', sql)
        self.assertIn('("id", "site_url", "capabilities")', sql)
        self.assertIn('SELECT "id", "site_url", "capabilities"::jsonb', sql)
        self.assertIn('FROM "tenant_demo_proj"."resource_pool_site_entries"', sql)
        self.assertNotIn("SELECT *", sql)
        self.assertNotIn("target_only_new", sql)
        self.assertNotIn("source_only_legacy", sql)

    def test_inject_initial_copy_sql_casts_json_source_to_jsonb_target(self):
        sql = _build_initial_project_copy_insert_sql(
            source_schema="tenant_demo_proj",
            target_schema="tenant_batch84_matrix_proj",
            table_name="resource_pool_site_entries",
            source_columns=[{"column_name": "capabilities", "udt_name": "json"}],
            target_columns=[{"column_name": "capabilities", "udt_name": "jsonb"}],
        )

        self.assertEqual(
            sql,
            'INSERT INTO "tenant_batch84_matrix_proj"."resource_pool_site_entries" ("capabilities") '
            'SELECT "capabilities"::jsonb FROM "tenant_demo_proj"."resource_pool_site_entries"',
        )

    def test_inject_initial_copy_sql_skips_when_no_common_columns(self):
        sql = _build_initial_project_copy_insert_sql(
            source_schema="tenant_demo_proj",
            target_schema="tenant_batch84_matrix_proj",
            table_name="resource_pool_site_entries",
            source_columns=[{"column_name": "legacy_name", "udt_name": "text"}],
            target_columns=[{"column_name": "site_url", "udt_name": "varchar"}],
        )

        self.assertIsNone(sql)

    def test_seed_sql_executes_via_driver_cursor_without_parameter_mapping(self):
        cursor = Mock()
        driver_connection = Mock()
        driver_connection.cursor.return_value = cursor
        conn = SimpleNamespace(connection=SimpleNamespace(driver_connection=driver_connection))
        seed_sql = "INSERT INTO project_demo_proj.documents (content) VALUES ('87% success');"

        _execute_seed_sql(conn, seed_sql)

        cursor.execute.assert_called_once_with(seed_sql)
        cursor.close.assert_called_once()

    def test_seed_sql_filter_removes_psql_meta_and_version_specific_lines(self):
        filtered = _filter_seed_sql_text(
            "\n".join(
                [
                    r"\restrict abc",
                    "SET transaction_timeout = 0;",
                    "SELECT pg_catalog.setval('project_demo_proj.documents_id_seq', 146, true);",
                    "INSERT INTO project_demo_proj.documents (id, doc_type) VALUES (1, 'market_info');",
                    r"\&gt; quoted html entity inside a seed string should stay",
                    r"\unrestrict abc",
                ]
            )
        )

        self.assertEqual(
            filtered,
            "INSERT INTO project_demo_proj.documents (id, doc_type) VALUES (1, 'market_info');\n"
            r"\&gt; quoted html entity inside a seed string should stay",
        )

    def test_create_project_duplicate_key_maps_to_invalid_input_error_code(self):
        result = Mock()
        result.scalar_one_or_none.return_value = SimpleNamespace(id=1, project_key="demo_proj")

        with (
            patch("app.api.projects.bind_schema", return_value=nullcontext()),
            patch("app.api.projects.SessionLocal", self._session_local_with_result(result)),
        ):
            response = self.client.post(
                "/api/v1/projects",
                headers=self.headers,
                json={"project_key": "demo_proj", "name": "Demo", "enabled": True},
            )

        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_create_project_table_set_includes_writing_workbench_tables(self):
        from app.api.projects import TENANT_TABLES

        table_names = {table.name for table in TENANT_TABLES}
        self.assertIn("writing_documents", table_names)
        self.assertIn("writing_document_drafts", table_names)
        self.assertIn("writing_document_citations", table_names)

    def test_projects_auto_create_missing_template_maps_to_not_found_error_code(self):
        with patch("app.api.projects._project_exists", return_value=False):
            response = self.client.post(
                "/api/v1/projects/auto-create",
                headers=self.headers,
                json={
                    "project_name": "New Project",
                    "project_key": "new_proj",
                    "template_project_key": "missing_proj",
                    "activate": False,
                    "copy_initial_data": True,
                    "llm_configs": [],
                },
            )

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)

    def test_activate_archived_project_maps_to_invalid_input_error_code(self):
        disabled_project = SimpleNamespace(project_key="archived_proj", enabled=False)
        result = Mock()
        result.scalar_one_or_none.return_value = disabled_project

        with (
            patch("app.api.projects.bind_schema", return_value=nullcontext()),
            patch("app.api.projects.SessionLocal", self._session_local_with_result(result)),
        ):
            response = self.client.post("/api/v1/projects/archived_proj/activate", headers=self.headers)

        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_delete_default_hard_delete_guard_maps_to_invalid_input_error_code(self):
        response = self.client.delete("/api/v1/projects/default", headers=self.headers, params={"hard": True})

        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)


if __name__ == "__main__":
    unittest.main()
