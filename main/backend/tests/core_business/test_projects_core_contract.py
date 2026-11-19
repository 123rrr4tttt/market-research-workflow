from __future__ import annotations

import gzip
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

try:
    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app
    from app.api.projects import (
        InjectInitialProjectPayload,
        _bootstrap_demo_seed_if_needed,
        _build_initial_project_copy_insert_sql,
        _DEMO_SEED_TABLES,
        INITIAL_PROJECT_TABLES,
        _execute_seed_sql,
        _resolve_inject_target_key,
        inject_initial_project,
    )
    from app.services.projects.schema_initialization import DatabaseRevisionIncompatibleError

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ProjectsCoreContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            reason = f"projects core contract tests require backend dependencies: {_IMPORT_ERROR}"
            raise unittest.SkipTest(reason)
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

    def test_inject_initial_old_revision_has_no_seed_delete_or_drop_side_effect(self):
        connection = Mock()
        transaction = Mock()
        transaction.__enter__ = Mock(return_value=connection)
        transaction.__exit__ = Mock(return_value=None)
        database_engine = Mock()
        database_engine.begin.return_value = transaction
        bootstrap_demo = Mock()
        session_local = Mock()

        with (
            patch("app.api.projects.engine", database_engine),
            patch(
                "app.api.projects.ensure_database_revision_compatible",
                side_effect=DatabaseRevisionIncompatibleError(
                    actual=frozenset({"old_head"}),
                    expected=frozenset({"current_head"}),
                ),
            ) as revision_guard,
            patch("app.api.projects._bootstrap_demo_seed_if_needed", bootstrap_demo),
            patch("app.api.projects.SessionLocal", session_local),
        ):
            with self.assertRaises(DatabaseRevisionIncompatibleError):
                inject_initial_project(
                    InjectInitialProjectPayload(
                        project_key="target_proj",
                        source_project_key="demo_proj",
                        overwrite=True,
                    )
                )

        revision_guard.assert_called_once_with(connection)
        bootstrap_demo.assert_not_called()
        session_local.assert_not_called()
        connection.execute.assert_not_called()

    def test_inject_initial_rejects_archived_target_until_restored(self):
        source = SimpleNamespace(project_key="source_proj", enabled=False)
        target = SimpleNamespace(project_key="target_proj", enabled=False)
        source_result, target_result = Mock(), Mock()
        source_result.scalar_one_or_none.return_value = source
        target_result.scalar_one_or_none.return_value = target
        session_local = self._session_local_with_result(target_result)
        session = session_local.return_value.__enter__.return_value
        session.execute.side_effect = [source_result, target_result, target_result, source_result, target_result]
        connection = Mock()
        connection.execute.return_value.scalar.return_value = True
        database_engine = Mock()
        database_engine.begin.side_effect = lambda: nullcontext(connection)
        path = "/api/v1/projects/inject-initial"
        payload = {
            "project_key": target.project_key,
            "source_project_key": source.project_key,
            "overwrite": True,
            "activate": False,
        }

        with (
            patch("app.api.projects.engine", database_engine),
            patch("app.api.projects.ensure_database_revision_compatible"),
            patch("app.api.projects.bind_schema", return_value=nullcontext()),
            patch("app.api.projects.SessionLocal", session_local),
            patch("app.api.projects.ensure_project_schema_ready") as ensure_schema,
            patch("app.api.projects._copy_initial_project_table", return_value=1) as copy_table,
        ):
            response = self.client.post(path, headers=self.headers, json=payload)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["error"]["code"], ErrorCode.INVALID_INPUT.value)
            self.assertIn("restore it before overwrite", response.json()["error"]["message"])
            session.delete.assert_not_called()
            session.commit.assert_not_called()
            ensure_schema.assert_not_called()
            copy_table.assert_not_called()
            self.assertFalse(any("DROP SCHEMA" in str(call.args[0]) for call in connection.execute.call_args_list))

            restored = self.client.post("/api/v1/projects/target_proj/restore", headers=self.headers)
            self.assertEqual(restored.status_code, 200)
            self.assertFalse(restored.json()["data"]["archived"])
            self.assertTrue(target.enabled)

            response = self.client.post(path, headers=self.headers, json=payload)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["data"]["source_project_key"], source.project_key)
            self.assertEqual(response.json()["data"]["project_key"], target.project_key)
            session.delete.assert_called_once_with(target)
            ensure_schema.assert_called_once()
            copy_table.assert_called()
            self.assertFalse(source.enabled)

    def test_populated_registered_demo_does_not_require_newer_seed_tables(self):
        conn, database_engine = Mock(), Mock()
        database_engine.begin.return_value = nullcontext(conn)
        conn.execute.return_value.scalar_one.return_value = True
        with (
            patch("app.api.projects.engine", database_engine),
            patch("app.api.projects.project_schema_name", return_value="tenant_demo_proj"),
            patch("app.api.projects.ensure_database_revision_compatible") as revision,
            patch("app.api.projects.tenant_table_exists", return_value=True) as exists,
            patch("app.api.projects.ensure_project_schema_ready") as bootstrap,
        ):
            _bootstrap_demo_seed_if_needed("demo_proj")
        revision.assert_called_once_with(conn)
        exists.assert_called_once_with(conn, schema_name="tenant_demo_proj", table_name="materials")
        query, params = conn.execute.call_args.args
        self.assertIn("project_key=:key AND schema_name=:schema", str(query))
        self.assertIn('EXISTS (SELECT 1 FROM "tenant_demo_proj".materials)', str(query))
        self.assertEqual(params, {"key": "demo_proj", "schema": "tenant_demo_proj"})
        bootstrap.assert_not_called()

    def test_lazy_demo_seed_admission_and_idempotence_under_lock(self):
        conn, database_engine = Mock(), Mock()
        database_engine.begin.side_effect = lambda: nullcontext(conn)
        schema = "tenant_demo_proj"
        body = "INSERT INTO materials (content) VALUES ('project_demo_proj.documents 97%\n pg_catalog.setval');"
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        seed = Path(directory.name) / "seed.sql.gz"
        seed.write_bytes(b"not a gzip file")
        with (
            patch("app.api.projects.engine", database_engine),
            patch("app.api.projects.project_schema_name", return_value=schema),
            patch("app.api.projects.ensure_database_revision_compatible"),
            patch("app.api.projects.ensure_project_schema_ready"),
            patch("app.api.projects.tenant_table_exists", return_value=False),
            patch("app.api.projects._DEMO_SEED_FILE", seed),
            patch("app.api.projects._execute_seed_sql") as execute_seed,
            patch("app.api.projects._align_copied_id_sequence") as align,
        ):
            for registration in (None, ("public", True), (schema, False)):
                with self.subTest(registration=registration):
                    conn.reset_mock()
                    conn.execute.return_value.one_or_none.return_value = registration
                    if registration == (schema, False):
                        _bootstrap_demo_seed_if_needed("demo_proj")
                    else:
                        with self.assertRaises(HTTPException) as error:
                            _bootstrap_demo_seed_if_needed("demo_proj")
                        self.assertEqual(error.exception.status_code, 409)
                    query, args = conn.execute.call_args.args
                    self.assertIn("FOR UPDATE", str(query))
                    self.assertEqual(args, {"project_key": "demo_proj"})
                    conn.execute.assert_called_once()
                    execute_seed.assert_not_called()

            conn.execute.return_value.one_or_none.return_value = (schema, True)
            for present in ({"materials"}, {"sources"}):
                conn.execute.return_value.one.return_value = tuple(name in present for name in _DEMO_SEED_TABLES)
                if "materials" in present:
                    _bootstrap_demo_seed_if_needed("demo_proj")
                else:
                    with self.assertRaises(HTTPException) as error:
                        _bootstrap_demo_seed_if_needed("demo_proj")
                    self.assertEqual(error.exception.status_code, 409)
                execute_seed.assert_not_called()
                align.assert_not_called()

            conn.reset_mock()
            conn.execute.return_value.one.return_value = (False,) * len(_DEMO_SEED_TABLES)
            with self.assertRaises(gzip.BadGzipFile):
                _bootstrap_demo_seed_if_needed("demo_proj")
            execute_seed.assert_not_called()
            align.assert_not_called()

            seed.write_bytes(gzip.compress(body.encode("utf-8")))
            conn.reset_mock()
            _bootstrap_demo_seed_if_needed("demo_proj")
            queries = [str(call.args[0]) for call in conn.execute.call_args_list]
            self.assertIn("FOR UPDATE", queries[0])
            self.assertIn("LOCK TABLE", queries[1])
            for name in _DEMO_SEED_TABLES:
                self.assertIn(f'"{schema}"."{name}"', queries[1])
                self.assertIn(f'EXISTS (SELECT 1 FROM "{schema}"."{name}")', queries[2])
            self.assertEqual(queries[3], f'SET LOCAL search_path TO "{schema}", pg_catalog')
            self.assertEqual(queries[4], "SET LOCAL standard_conforming_strings = on")
            execute_seed.assert_called_once_with(conn, body)
            self.assertEqual(
                [call.args for call in align.call_args_list], [(conn, schema, n) for n in _DEMO_SEED_TABLES]
            )

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
        seed_sql = "INSERT INTO project_demo_proj.materials (content) VALUES ('87% success');"

        _execute_seed_sql(conn, seed_sql)

        cursor.execute.assert_called_once_with(seed_sql)
        cursor.close.assert_called_once()

    def test_clone_rebinds_resource_pool_ownership_but_retains_provenance(self):
        columns = [
            {"column_name": "project_key", "udt_name": "varchar"}, {"column_name": "source_ref", "udt_name": "jsonb"}
        ]
        for name in ("resource_pool_urls", "resource_pool_site_entries"):
            sql = _build_initial_project_copy_insert_sql(
                source_schema="project_demo_proj", target_schema="project_copy", table_name=name,
                source_columns=columns, target_columns=columns,
            )
            self.assertIn('SELECT :target_project_key, "source_ref" FROM', sql)
            self.assertNotIn(":source_project_key", sql)

    def test_template_graph_ownership_and_child_references(self):
        for table, columns, parent, fks in (
            ("graph_nodes", ("id", "canonical_id"), "", ()),
            ("graph_node_aliases", ("id", "node_id"), "graph_nodes", ("node_id",)),
            ("graph_edges", ("id", "from_node_id", "to_node_id"), "graph_nodes", ("from_node_id", "to_node_id")),
            ("writing_document_drafts", ("id", "doc_id", "project_key"), "writing_documents", ("doc_id",)),
        ):
            target = [{"column_name": c} for c in columns]
            source = target if "project_key" in columns else [*target, {"column_name": "project_key"}]
            sql = _build_initial_project_copy_insert_sql(
                source_schema="src", target_schema="dst", table_name=table,
                source_columns=source, target_columns=target,
            )
            if table == "writing_document_drafts":
                self.assertIn('WHERE "project_key" = :source_project_key', sql)
            else:
                self.assertNotIn(":source_project_key", sql)
            for fk in fks:
                self.assertIn(f'"{fk}" IN (SELECT id FROM "dst"."{parent}")', sql)

    def test_template_rebinds_writing_metadata_not_prose_or_export_tokens(self):
        columns = [{"column_name": c} for c in ("project_key", "metadata_json", "body_md")]
        sql = _build_initial_project_copy_insert_sql(
            source_schema="src", target_schema="dst", table_name="writing_documents",
            source_columns=columns, target_columns=columns,
        )
        self.assertIn(":target_project_key", sql)
        self.assertIn("- 'export_artifact'", sql)
        self.assertIn("jsonb_set(", sql)
        self.assertIn('"body_md" FROM', sql)

    def test_seed_tables_can_be_cloned_in_dependency_order(self):
        order = [table.name for table in INITIAL_PROJECT_TABLES]
        self.assertTrue(set(_DEMO_SEED_TABLES) <= set(order))
        self.assertNotIn("typed_knowledge_objects", order)
        for child, parent in (
            ("materials", "sources"), ("graph_nodes", "materials"), ("graph_edges", "graph_nodes"),
            ("graph_node_aliases", "graph_nodes"), ("writing_document_drafts", "writing_documents"),
            ("writing_document_citations", "writing_documents"), ("source_library_items", "ingest_channels"),
        ):
            self.assertLess(order.index(parent), order.index(child))
        with self.assertRaises(HTTPException) as error:
            _resolve_inject_target_key("demo_proj", source_key="demo_proj", overwrite=True)
        self.assertEqual(error.exception.status_code, 409)

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
        from app.services.projects.bootstrap import TENANT_TABLES

        table_names = {table.name for table in TENANT_TABLES}
        self.assertIn("graph_nodes", table_names)
        self.assertIn("graph_node_aliases", table_names)
        self.assertIn("graph_edges", table_names)
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
