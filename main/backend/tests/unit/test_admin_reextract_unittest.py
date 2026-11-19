from __future__ import annotations

import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.api import admin as admin_module
    from app import main as main_module
    from app.services.projects import current_project_key
    from app.settings.config import settings

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalarResult(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.commit_count = 0
        self.dirty = rows

    def execute(self, _stmt):
        return _FakeExecuteResult(self._rows)

    def commit(self):
        self.commit_count += 1


class _FakeSessionLocal:
    def __init__(self, rows):
        self._session = _FakeSession(rows)

    def __call__(self):
        return self

    def __enter__(self):
        return self._session

    def __exit__(self, _exc_type, _exc, _tb):
        return False


class AdminReextractUnitTest(unittest.TestCase):
    def test_material_routes_reuse_existing_handlers_and_accept_material_ids(self):
        routes = {route.path: route.endpoint for route in admin_module.router.routes}
        route_order = [route.path for route in admin_module.router.routes]
        self.assertFalse(any("/documents/" in path for path in routes))
        dynamic_path = "/admin/materials/{material_id}/extracted-data"
        bulk_path = "/admin/materials/bulk/extracted-data"
        self.assertIn(dynamic_path, routes)
        self.assertLess(route_order.index(bulk_path), route_order.index(dynamic_path))
        self.assertEqual(admin_module.ReExtractRequest(material_ids=[101]).material_ids, [101])
        self.assertEqual(admin_module.BulkUpdateExtractedDataRequest(material_ids=[101]).material_ids, [101])
        self.assertEqual(admin_module.DeleteMaterialsRequest(material_ids=[101]).material_ids, [101])

    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"admin re-extract tests require backend dependencies: {_IMPORT_ERROR}")

    def test_reextract_uses_frontdoor_and_merges_existing_fields(self):
        doc = SimpleNamespace(
            id=101,
            title="Policy Update",
            summary="summary",
            content="policy content",
            uri="https://example.com/policy",
            material_type="policy",
            extracted_data={"legacy": {"keep": True}},
        )
        session_factory = _FakeSessionLocal([doc])

        with (
            patch.object(admin_module.document_admin, "SessionLocal", session_factory),
            patch.object(admin_module.document_admin, "require_writable_project"),
            patch.object(
                admin_module,
                "run_frontdoor_extraction",
                return_value={
                    "status": "ok",
                    "reason": None,
                    "error": None,
                    "domains": {"policy": {"title": "new policy"}, "entities_relations": {"entities": [{"text": "CA", "type": "state"}], "relations": []}},
                    "summary": {"extraction_enabled": True, "chunks_used": 1, "extraction_mode": "admin_reextract"},
                },
            ) as mocked_extract,
        ):
            result = admin_module.re_extract_materials(
                admin_module.ReExtractRequest(material_ids=[101], force=True, batch_size=10)
            )

        self.assertEqual(result.get("status"), "ok")
        data = result.get("data") or {}
        self.assertEqual(int(data.get("success") or 0), 1)
        self.assertEqual(int(data.get("skipped") or 0), 0)
        self.assertEqual(doc.extracted_data.get("legacy"), {"keep": True})
        self.assertEqual((doc.extracted_data.get("policy") or {}).get("title"), "new policy")
        self.assertEqual(doc.extracted_data.get("structured_extraction_status"), "ok")
        self.assertEqual((doc.extracted_data.get("_structured_summary") or {}).get("extraction_mode"), "admin_reextract")
        mocked_extract.assert_called_once()
        plan = mocked_extract.call_args.kwargs.get("extraction_plan") or {}
        self.assertTrue(bool(plan.get("include_policy")))
        self.assertFalse(bool(plan.get("include_market")))
        self.assertFalse(bool(plan.get("include_sentiment")))

    def test_archived_project_refuses_material_mutations_before_work_starts(self):
        def query_archived_project(statement, parameters):
            self.assertIn("FOR SHARE", str(statement))
            self.assertEqual(parameters, {"project_key": "archived_project"})
            return SimpleNamespace(scalar_one_or_none=lambda: False)

        session = SimpleNamespace(execute=query_archived_project)
        with (
            patch.object(admin_module.document_admin, "SessionLocal", return_value=nullcontext(session)),
            patch.object(admin_module, "_get_topic_dictionaries", return_value={}),
            patch.object(admin_module, "run_frontdoor_extraction") as reextract,
            patch.object(admin_module, "run_topic_extraction_workflow") as topic_extract,
            patch.object(admin_module, "fetch_html") as fetch,
        ):
            client = TestClient(main_module.app)
            for suffix, payload in (
                ("7/extracted-data", {"extracted_data": {"new": True}}),
                ("bulk/extracted-data", {"material_ids": [7], "extracted_data": {"new": True}}),
                ("delete", {"material_ids": [7]}),
                ("re-extract", {"material_ids": [7], "fetch_missing_content": True}),
                ("topic-extract", {"material_ids": [7], "topics": ["company"], "fetch_missing_content": True}),
            ):
                with self.subTest(route=suffix):
                    response = client.post(
                        f"/api/v1/admin/materials/{suffix}",
                        headers={"X-Project-Key": "archived_project"},
                        json=payload,
                    )
                    self.assertEqual(response.status_code, 409, response.text)
                    self.assertEqual(response.json()["error"]["details"], {
                        "project_key": "archived_project",
                        "reason_code": "project_not_writable",
                    })
        reextract.assert_not_called()
        topic_extract.assert_not_called()
        fetch.assert_not_called()

    def test_bulk_mutation_uses_header_project_for_service_audit_and_trace(self):
        pre_mutation_snapshot = {
            "id": 7,
            "material_id": 7,
            "title": "Scoped document",
            "material_type": "policy",
            "state": "CA",
            "status": "ready",
            "publish_date": None,
            "content": "before",
            "summary": None,
            "uri": "https://example.com/scoped",
            "extracted_data": {"version": "before"},
            "source_id": 2,
            "created_at": None,
            "updated_at": None,
        }
        observed_project_keys: list[str] = []
        current_state = {"extracted_data": {"version": "before"}}

        def mutate(_doc_ids, command):
            observed_project_keys.append(current_project_key())
            current_state["extracted_data"] = command.extracted_data
            return {
                "requested": 1,
                "updated": 1,
                "skipped": 0,
                "missing": [],
                "errors": [],
                "readback": [pre_mutation_snapshot],
            }

        responses = []
        with (
            patch.object(settings, "active_project_key", "project_a"),
            patch.object(admin_module.document_admin, "bulk_update_admin_material_extracted_data", side_effect=mutate),
        ):
            client = TestClient(main_module.app)
            for prefix in ("materials",):
                responses.append(
                    client.post(
                        f"/api/v1/admin/{prefix}/bulk/extracted-data",
                        headers={"X-Project-Key": "Project-B", "X-Request-Id": f"admin-project-b-{prefix}"},
                        json={"material_ids": [7], "mode": "replace", "extracted_data": {"version": "after"}},
                    )
                )

        for response in responses:
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(observed_project_keys, ["project_b"])
        self.assertEqual(current_state["extracted_data"], {"version": "after"})
        expected_trace = admin_module._admin_response_trace_id(
            action_kind="materials.bulk_extracted_data",
            project_key="project_b",
            requested_ids=[7],
            affected_count=1,
            missing_ids=[],
            skipped_count=0,
            status="completed",
        )
        fallback_trace = admin_module._admin_response_trace_id(
            action_kind="materials.bulk_extracted_data",
            project_key="project_a",
            requested_ids=[7],
            affected_count=1,
            missing_ids=[],
            skipped_count=0,
            status="completed",
        )
        for response in responses:
            data = response.json()["data"]
            audit_event = data["audit_event"]
            selection = data["source_query"]["selection"]
            self.assertEqual(audit_event["project_key"], "project_b")
            self.assertEqual(audit_event["trace_id"], expected_trace)
            self.assertNotEqual(audit_event["trace_id"], fallback_trace)
            self.assertEqual(data["source_query"]["scope"], "admin.after_action.response_readback")
            self.assertEqual(selection["source_snapshot_timing"], "pre_mutation")
            self.assertFalse(selection["post_commit_readback_performed"])
            self.assertEqual(data["trace_chain"][-1]["stage"], "admin.after_action.response_readback")
            self.assertEqual(data["source_refs"][0]["material_id"], 7)

    def test_reserved_public_scope_is_rejected_before_admin_mutation(self):
        with (
            patch.object(main_module, "get_effective_project_key_enforcement_mode", return_value="require"),
            patch(
                "app.services.projects.context.get_effective_project_key_enforcement_mode",
                return_value="require",
            ),
            patch.object(admin_module.document_admin, "delete_admin_materials") as mutation,
        ):
            with self.assertRaisesRegex(ValueError, "reserved key public"):
                TestClient(main_module.app).post(
                    "/api/v1/admin/materials/delete",
                    headers={"X-Project-Key": "public"},
                    json={"ids": [7]},
                )
        mutation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
