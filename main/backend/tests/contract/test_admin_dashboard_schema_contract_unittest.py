from __future__ import annotations

import unittest
from contextlib import nullcontext
from unittest.mock import patch

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from app.api.dashboard import (
    DashboardJsonInput,
    DashboardReportFromFilterRequest,
    get_dashboard_llm_report_detail,
)
from app.api.admin import (
    DeleteMaterialsRequest,
    MaterialListRequest,
    RawImportRequest,
    ReExtractRequest,
)
from app.contracts import ApiEnvelope
from app.main import app as backend_app
from scripts.generate_api_schema_inventory import build_inventory

pytestmark = pytest.mark.contract


class _DashboardDetailStorage(BaseModel):
    degraded: bool
    export_audit: dict[str, JsonValue]
    quality: dict[str, JsonValue]


class _DashboardDetailActionability(BaseModel):
    next_action: str


class _DashboardDetailData(BaseModel):
    found: bool
    storage: _DashboardDetailStorage
    actionability: _DashboardDetailActionability


class AdminDashboardSchemaContractTestCase(unittest.TestCase):
    def test_admin_and_dashboard_legacy_dict_endpoints_have_openapi_200_schema(self):
        inventory = build_inventory(backend_app)
        by_source = {row["source_module"]: row for row in inventory["source_summary"]}

        for source_module in ("admin.py", "dashboard.py"):
            row = by_source[source_module]
            self.assertEqual(row["untyped_200"], 0, msg=row)
            self.assertEqual(row["response_models"], row["operations"], msg=row)

    def test_admin_and_dashboard_success_responses_keep_envelope_schema(self):
        operations = {
            (operation["method"], operation["path"]): operation
            for operation in build_inventory(backend_app)["operations"]
        }

        for key in (
            ("GET", "/api/v1/admin/stats"),
            ("GET", "/api/v1/admin/content-graph"),
            ("GET", "/api/v1/dashboard/stats"),
            ("GET", "/api/v1/dashboard/ecom-price-trends"),
        ):
            operation = operations[key]
            self.assertIn("ApiEnvelope", operation["response_model"], msg=operation)
            self.assertNotEqual(operation["response_200_schema"], "untyped", msg=operation)

    def test_admin_exposes_only_material_routes_for_canonical_records(self):
        operations = build_inventory(backend_app)["operations"]
        admin_paths = {
            operation["path"]
            for operation in operations
            if operation["source_module"] == "admin.py"
        }

        self.assertIn("/api/v1/admin/materials/list", admin_paths)
        self.assertIn("/api/v1/admin/materials/{material_id}", admin_paths)
        self.assertFalse(any(path.startswith("/api/v1/admin/documents") for path in admin_paths))

    def test_admin_material_payloads_reject_retired_document_fields(self):
        for model, payload in (
            (MaterialListRequest, {"doc_type": "policy"}),
            (DeleteMaterialsRequest, {"ids": [1]}),
            (DeleteMaterialsRequest, {"doc_ids": [1]}),
            (ReExtractRequest, {"doc_ids": [1]}),
            (
                RawImportRequest,
                {"items": [{"text": "sample"}], "default_doc_type": "raw_note"},
            ),
            (
                RawImportRequest,
                {"items": [{"text": "sample", "doc_type": "raw_note"}]},
            ),
        ):
            with self.subTest(model=model.__name__, payload=payload), self.assertRaises(ValidationError):
                model.model_validate(payload)

    def test_admin_stats_projects_one_canonical_material_count(self):
        from app.services import document_admin

        class _ScalarResult:
            def __init__(self, value: int) -> None:
                self.value = value

            def scalar(self) -> int:
                return self.value

        session = unittest.mock.MagicMock()
        session.__enter__.return_value = session
        session.__exit__.return_value = False
        session.execute.side_effect = [
            _ScalarResult(11),
            _ScalarResult(2),
            _ScalarResult(3),
            _ScalarResult(1),
            _ScalarResult(4),
            _ScalarResult(5),
        ]
        with (
            patch.object(document_admin, "bind_project", return_value=nullcontext()),
            patch.object(document_admin, "SessionLocal", return_value=session),
        ):
            result = document_admin.get_admin_stats("demo_proj")

        self.assertEqual(
            result,
            {
                "materials": {"total": 11, "recent_today": 2},
                "social_data": {"total": 3, "recent_today": 1},
                "sources": {"total": 4},
                "search_history": {"total": 5},
            },
        )
        self.assertNotIn("table_total", result["materials"])

    def test_dashboard_report_request_accepts_recursive_json_and_rejects_runtime_objects(self):
        request = DashboardReportFromFilterRequest.model_validate(
            {
                "dashboard": {
                    "filters": {"published": True, "range": [1, 2.5, None]},
                    "source_refs": [{"id": "dashboard.stats.materials"}],
                },
                "report_options": {"format": "markdown"},
            }
        )

        self.assertEqual(
            request.dashboard,
            {
                "filters": {"published": True, "range": [1, 2.5, None]},
                "source_refs": [{"id": "dashboard.stats.materials"}],
            },
        )
        with self.assertRaises(ValidationError):
            DashboardReportFromFilterRequest.model_validate({"dashboard": {"opaque": object()}})

    def test_dashboard_report_detail_exposes_service_failure_as_degraded(self):
        with (
            patch(
                "app.api.dashboard.list_llm_report_export_audit_events_for_trace",
                side_effect=RuntimeError("export store unavailable"),
            ),
            patch(
                "app.api.dashboard.list_quality_trend_records_for_trace_ids",
                side_effect=RuntimeError("quality store unavailable"),
            ),
        ):
            response = get_dashboard_llm_report_detail(
                trace_id="trace-degraded",
                project_key=None,
                limit=10,
            )

        envelope = ApiEnvelope[DashboardJsonInput].model_validate(response)
        self.assertEqual(envelope.status, "ok")
        self.assertIsNotNone(envelope.data)
        detail = _DashboardDetailData.model_validate(envelope.data)
        self.assertFalse(detail.found)
        self.assertTrue(detail.storage.degraded)
        self.assertEqual(
            detail.storage.export_audit["degraded_reason"],
            "llm_report_export_audit_service_unavailable",
        )
        self.assertEqual(
            detail.storage.quality["degraded_reason"],
            "llm_report_quality_detail_service_unavailable",
        )
        self.assertEqual(
            detail.actionability.next_action,
            "retry_detail_query_or_inspect_process_history_by_trace_id",
        )


if __name__ == "__main__":
    unittest.main()
