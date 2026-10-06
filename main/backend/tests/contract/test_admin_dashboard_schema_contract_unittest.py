from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from app.api.dashboard import (
    DashboardJsonInput,
    DashboardReportFromFilterRequest,
    get_dashboard_llm_report_detail,
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

    def test_dashboard_report_request_accepts_recursive_json_and_rejects_runtime_objects(self):
        request = DashboardReportFromFilterRequest.model_validate(
            {
                "dashboard": {
                    "filters": {"published": True, "range": [1, 2.5, None]},
                    "source_refs": [{"id": "dashboard.stats.documents"}],
                },
                "report_options": {"format": "markdown"},
            }
        )

        self.assertEqual(
            request.dashboard,
            {
                "filters": {"published": True, "range": [1, 2.5, None]},
                "source_refs": [{"id": "dashboard.stats.documents"}],
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
