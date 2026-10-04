from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = [pytest.mark.contract, pytest.mark.mocked]

try:
    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _AuthenticatedActorStateApp:
    def __init__(self, app, *, actor_id: str):
        self._app = app
        self._actor_id = actor_id

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            state = scope.setdefault("state", {})
            actor = {
                "actor_id": self._actor_id,
                "source": "test_authenticated_actor_context",
                "auth_type": "codex_test",
            }
            state["authenticated_actor"] = actor
            state["authenticated_actor_id"] = self._actor_id
            state["codex_authenticated_actor"] = actor
        await self._app(scope, receive, send)


class _FakeResult:
    def __init__(self, scalar_value=None, all_value=None):
        self._scalar_value = scalar_value
        self._all_value = all_value

    def scalar(self):
        return self._scalar_value

    def all(self):
        return self._all_value


class _FakeDashboardSession:
    def __init__(self):
        self._execute_count = 0

    def execute(self, _query):
        self._execute_count += 1
        match self._execute_count:
            case 1:
                return _FakeResult(scalar_value=10)  # doc_total
            case 2:
                return _FakeResult(scalar_value=2)  # doc_recent_today
            case 3:
                return _FakeResult(scalar_value=4)  # doc_recent_7d
            case 4:
                return _FakeResult(scalar_value=3)  # source_total
            case 5:
                return _FakeResult(scalar_value=2)  # source_enabled
            case 6:
                return _FakeResult(scalar_value=7)  # history_total
            case 7:
                return _FakeResult(scalar_value=9)  # task_total
            case 8:
                return _FakeResult(scalar_value=1)  # task_running
            case 9:
                return _FakeResult(scalar_value=6)  # task_completed
            case 10:
                return _FakeResult(scalar_value=2)  # task_failed
            case 11:
                rows = [SimpleNamespace(doc_type="policy", count=6), SimpleNamespace(doc_type="news", count=4)]
                return _FakeResult(all_value=rows)  # doc_type_dist
            case 12:
                return _FakeResult(scalar_value=5)  # doc_with_extracted
            case 13:
                rows = [
                    SimpleNamespace(
                        params={
                            "frontdoor_status_summary": {
                                "dashboard_status_counts": {
                                    "success": 3,
                                    "degraded_success": 2,
                                    "failed": 1,
                                }
                            }
                        },
                        status="completed",
                    ),
                    SimpleNamespace(
                        params={
                            "meta": {
                                "frontdoor_status_summary": {
                                    "dashboard_status_counts": {
                                        "success": 1,
                                        "degraded_success": 0,
                                        "failed": 1,
                                    }
                                }
                            }
                        },
                        status="completed",
                    ),
                ]
                return _FakeResult(all_value=rows)  # frontdoor_tri_state_rows
            case _:
                return _FakeResult(scalar_value=0)


class _FakeDashboardEmptySession:
    def execute(self, _query):
        return _FakeResult(scalar_value=0, all_value=[])


class _FakeSessionLocalOk:
    def __enter__(self):
        return _FakeDashboardSession()

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeSessionLocalEmpty:
    def __enter__(self):
        return _FakeDashboardEmptySession()

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeSessionLocalOperationalError:
    def __enter__(self):
        raise Exception("database timeout")

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeResultNone:
    def scalar_one_or_none(self):
        return None


class _FakeResultDoc:
    def __init__(self, doc):
        self._doc = doc

    def scalar_one_or_none(self):
        return self._doc


class _FakeScalarRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeAdminSession:
    def __init__(self, doc=None):
        self._doc = doc

    def execute(self, _query):
        return _FakeResultDoc(self._doc) if self._doc is not None else _FakeResultNone()

    def commit(self):
        return None


class _FakeAdminSessionLocal:
    def __init__(self, doc=None):
        self._doc = doc

    def __enter__(self):
        return _FakeAdminSession(self._doc)

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakePreviewDeleteSession:
    def __init__(self, docs):
        self._docs = docs
        self.deleted = []
        self.committed = False

    def execute(self, _query):
        return _FakeScalarRowsResult(self._docs)

    def delete(self, doc):
        self.deleted.append(doc)

    def commit(self):
        self.committed = True


class _FakePreviewDeleteSessionLocal:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeDrilldownSession:
    def execute(self, _query):
        rows = [
            SimpleNamespace(
                id=101,
                title="Policy sample",
                doc_type="policy",
                status="active",
                state="CA",
                uri="https://example.test/policy",
                source_id=7,
                publish_date=None,
                created_at=None,
                extracted_data={"summary": "ok"},
            )
        ]
        return _FakeScalarRowsResult(rows)


class _FakeDrilldownSessionLocal:
    def __enter__(self):
        return _FakeDrilldownSession()

    def __exit__(self, exc_type, exc, tb):
        return False


class AdminDashboardProcessCoreContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"core contract tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "core-contract-h"}

    def _authenticated_client(self, *, actor_id: str):
        return TestClient(_AuthenticatedActorStateApp(backend_app, actor_id=actor_id))

    def _dashboard_report_from_filter_payload(self) -> dict:
        return {
            "request_type": "report_from_dashboard_filter",
            "project_key": "demo_proj",
            "dashboard": {
                "variant": "dashboard",
                "selected_label": "Documents",
                "selected_metric": "documents",
                "selected_source_ref": "dashboard.stats.documents",
                "filters": {"limit": 1, "doc_type": "policy"},
                "source_query": {
                    "scope": "dashboard.stats",
                    "card": "documents",
                    "table": "documents",
                    "metrics": ["documents"],
                    "filters": {"doc_type": "policy"},
                },
                "source_refs": [
                    {
                        "id": "dashboard.stats.documents",
                        "kind": "sql_table",
                        "table": "documents",
                        "columns": ["id", "title"],
                        "published_at": "2026-05-01",
                        "trust_score": 0.92,
                    }
                ],
                "sample_rows": [{"id": 101, "title": "Policy sample"}],
                "sample_row_count": 1,
            },
            "report_options": {"include_dashboard_sample_rows": True, "as_of_date": "2026-05-24"},
        }

    def test_admin_raw_import_success_returns_envelope(self):
        mock_delay = Mock(return_value=SimpleNamespace(id="task-123"))
        fake_tasks_module = SimpleNamespace(task_raw_import_documents=SimpleNamespace(delay=mock_delay))

        with patch("app.api.admin._tasks_module", return_value=fake_tasks_module):
            resp = self.client.post(
                "/api/v1/admin/documents/raw-import",
                headers=self.headers,
                json={
                    "items": [{"text": "hello"}],
                    "source_name": "manual",
                    "async_mode": True,
                },
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(body.keys()))
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["async"], True)
        self.assertEqual(body["data"]["task_id"], "task-123")

    def test_admin_raw_import_http_exception_maps_to_rate_limited(self):
        mock_delay = Mock(side_effect=HTTPException(status_code=429, detail="too many requests"))
        fake_tasks_module = SimpleNamespace(task_raw_import_documents=SimpleNamespace(delay=mock_delay))

        with patch("app.api.admin._tasks_module", return_value=fake_tasks_module):
            resp = self.client.post(
                "/api/v1/admin/documents/raw-import",
                headers=self.headers,
                json={
                    "items": [{"text": "hello"}],
                    "source_name": "manual",
                    "async_mode": True,
                },
            )

        self.assertEqual(resp.status_code, 429)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.RATE_LIMITED.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.RATE_LIMITED.value)

    def test_dashboard_stats_contract_includes_source_queries(self):
        llm_quality_records = [
            {
                "trace_id": "trace-pass",
                "project_key": "demo_proj",
                "decision": "pass",
                "readiness": "ready",
                "citation_coverage": 1.0,
                "evidence_coverage": 0.75,
                "job_id": 1001,
                "job_status": "completed",
                "recorded_at": "2026-05-24T00:00:00+00:00",
            },
            {
                "trace_id": "trace-fail",
                "project_key": "demo_proj",
                "decision": "fail",
                "readiness": "blocked",
                "citation_coverage": 0.2,
                "evidence_coverage": 0.1,
                "job_id": 1002,
                "job_status": "failed",
                "recorded_at": "2026-05-24T00:01:00+00:00",
            },
            {
                "contract_version": "llm_report.export_trend_metric.v1",
                "event_type": "llm_report_export",
                "trace_id": "trace-export",
                "project_key": "demo_proj",
                "decision": "pass",
                "readiness": "ready",
                "record_source": "export",
                "export_format": "pdf",
                "export_outcome": "success",
                "export_integrity_mode": "artifact_token",
                "export_integrity_trusted": True,
                "recorded_at": "2026-05-24T00:02:00+00:00",
            },
        ]
        llm_quality_storage = {
            "contract_version": "llm_report.quality_trend_storage.v1",
            "memory_count": 2,
            "persisted_count": 0,
            "persisted_degraded": False,
            "merged_count": 2,
        }
        llm_export_audit_records = [
            {
                "contract_version": "llm_report.export_audit_event.v1",
                "event_type": "llm_report_export",
                "record_source": "export_audit",
                "trace_id": "trace-export",
                "source_trace_id": "trace-pass",
                "project_key": "demo_proj",
                "actor_id": "analyst-1",
                "export_format": "pdf",
                "export_outcome": "success",
                "outcome": "success",
                "export_integrity_mode": "artifact_token",
                "integrity_mode": "artifact_token",
                "export_integrity_trusted": True,
                "integrity_trusted": True,
                "ui_read_only_context_included": True,
                "recorded_at": "2026-05-24T00:02:00+00:00",
            }
        ]
        with (
            patch.object(
                backend_app.state, "information_topology_service",
                SimpleNamespace(count_current_elements=lambda _project, _kind: 0),
                create=True,
            ),
            patch("app.api.dashboard.SessionLocal", return_value=_FakeSessionLocalOk()),
            patch(
                "app.api.dashboard.list_quality_trend_records",
                return_value=(llm_quality_records, llm_quality_storage),
            ),
            patch(
                "app.api.dashboard.list_recent_llm_report_export_audit_events",
                return_value=llm_export_audit_records,
            ),
        ):
            resp = self.client.get("/api/v1/dashboard/stats", headers=self.headers)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(body.keys()))
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["documents"]["total"], 10)
        self.assertEqual(body["data"]["documents"]["extraction_rate"], 50.0)
        self.assertEqual(body["data"]["documents"]["source_query"]["card"], "documents")
        self.assertEqual(body["data"]["documents"]["source_query"]["table"], "documents")
        self.assertEqual(body["data"]["documents"]["source_refs"][0]["id"], "dashboard.stats.documents")
        self.assertEqual(body["data"]["documents"]["source_refs"][0]["table"], "documents")
        self.assertEqual(body["data"]["sources"]["source_query"]["card"], "sources")
        self.assertNotIn("market_stats", body["data"])
        self.assertEqual(body["data"]["search_history"]["source_refs"][0]["table"], "search_history")
        self.assertEqual(body["data"]["tasks"]["source_query"]["card"], "tasks")
        llm_quality = body["data"]["llm_report_quality"]
        self.assertEqual(llm_quality["contract_version"], "dashboard.llm_report_quality.v1")
        self.assertEqual(llm_quality["trend_contract_version"], "llm_report.quality_trends.v1")
        self.assertEqual(llm_quality["summary"]["total"], 3)
        self.assertEqual(llm_quality["summary"]["by_decision"]["fail"], 1)
        self.assertEqual(llm_quality["summary"]["export_events"]["total"], 1)
        self.assertEqual(llm_quality["summary"]["export_events"]["success"], 1)
        self.assertEqual(llm_quality["summary"]["export_events"]["ui_read_only_context_included_count"], 1)
        self.assertEqual(llm_quality["summary"]["export_events"]["by_format"]["pdf"], 1)
        self.assertEqual(len(llm_quality["recent_export_events"]), 1)
        self.assertEqual(llm_quality["recent_export_events"][0]["trace_id"], "trace-export")
        self.assertEqual(llm_quality["recent_export_events"][0]["export_format"], "pdf")
        self.assertIn("export_events", llm_quality["source_query"]["metrics"])
        self.assertEqual(llm_quality["source_query"]["card"], "llm_report_quality")
        self.assertEqual(llm_quality["source_refs"][0]["table"], "llm_report_export_audit_events")
        self.assertEqual(llm_quality["storage"]["export_audit"]["table"], "llm_report_export_audit_events")
        self.assertTrue(llm_quality["actionability"]["has_blocked_exports"])
        pending_actions = body["data"]["pending_actions"]
        self.assertIsInstance(pending_actions, list)
        self.assertTrue({"id", "type", "severity", "status", "source_metric", "source_refs"}.issubset(pending_actions[0].keys()))
        self.assertEqual(pending_actions[0]["status"], "open")
        self.assertIn("provider_degradation", {item["type"] for item in pending_actions})
        self.assertIn("source_invalid", {item["type"] for item in pending_actions})
        self.assertIn("report_reference_gap", {item["type"] for item in pending_actions})
        self.assertEqual(
            body["data"]["tasks"]["frontdoor_tri_state"],
            {
                "states": ["success", "degraded_success", "failed"],
                "counts": {"success": 4, "degraded_success": 2, "failed": 2},
                "total": 8,
                "source": "etl_job_runs.params.frontdoor_status_summary.dashboard_status_counts",
                "source_query": {
                    "scope": "dashboard.stats",
                    "card": "tasks.frontdoor_tri_state",
                    "table": "etl_job_runs",
                    "metrics": ["frontdoor_tri_state"],
                    "filters": {"params.frontdoor_status_summary": "present"},
                },
                "source_refs": [
                    {
                        "id": "dashboard.stats.tasks.frontdoor_tri_state",
                        "kind": "sql_table",
                        "table": "etl_job_runs",
                        "columns": ["params", "status"],
                        "detail": "params.frontdoor_status_summary.dashboard_status_counts",
                    }
                ],
            },
        )

    def test_dashboard_stats_empty_data_returns_stable_pending_actions(self):
        with (
            patch.object(
                backend_app.state, "information_topology_service",
                SimpleNamespace(count_current_elements=lambda _project, _kind: 0),
                create=True,
            ),
            patch("app.api.dashboard.SessionLocal", return_value=_FakeSessionLocalEmpty()),
            patch("app.api.dashboard.list_quality_trend_records", return_value=([], {})),
        ):
            resp = self.client.get("/api/v1/dashboard/stats", headers=self.headers)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["documents"]["total"], 0)
        self.assertEqual(body["data"]["documents"]["type_distribution"], {})
        self.assertEqual(body["data"]["llm_report_quality"]["summary"]["total"], 0)
        self.assertEqual(len(body["data"]["pending_actions"]), 1)
        self.assertEqual(body["data"]["pending_actions"][0]["type"], "config_missing")
        self.assertEqual(body["data"]["pending_actions"][0]["source_refs"], ["dashboard.stats.sources"])

    def test_dashboard_drilldown_by_source_ref_returns_rows_and_filters(self):
        with patch("app.api.dashboard.SessionLocal", return_value=_FakeDrilldownSessionLocal()):
            resp = self.client.get(
                "/api/v1/dashboard/drilldown",
                headers=self.headers,
                params={"source_ref": "dashboard.stats.documents", "limit": 1},
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["metric"], "documents")
        self.assertEqual(body["data"]["source_ref"], "dashboard.stats.documents")
        self.assertEqual(body["data"]["filters"]["limit"], 1)
        self.assertEqual(body["data"]["row_count"], 1)
        self.assertEqual(body["data"]["sample_rows"][0]["id"], 101)
        self.assertEqual(body["data"]["sample_rows"][0]["has_extracted_data"], True)
        self.assertEqual(body["data"]["source_query"]["table"], "documents")

    def test_dashboard_report_from_filter_creates_writing_draft_with_evidence_metadata(self):
        created_doc = {
            "id": 321,
            "project_key": "demo_proj",
            "title": "Dashboard report draft - Documents",
            "body_md": "# Dashboard report draft - Documents",
            "status": "draft",
            "version": 1,
            "metadata_json": {},
        }
        payload = {
            "request_type": "report_from_dashboard_filter",
            "project_key": "demo_proj",
            "dashboard": {
                "variant": "dashboard",
                "selected_label": "Documents",
                "selected_metric": "documents",
                "selected_source_ref": "dashboard.stats.documents",
                "filters": {"limit": 1, "doc_type": "policy"},
                "source_query": {
                    "scope": "dashboard.stats",
                    "card": "documents",
                    "table": "documents",
                    "metrics": ["documents"],
                    "filters": {"doc_type": "policy"},
                },
                "source_refs": [
                    {
                        "id": "dashboard.stats.documents",
                        "kind": "sql_table",
                        "table": "documents",
                        "columns": ["id", "title"],
                        "published_at": "2026-05-01",
                        "trust_score": 0.92,
                    }
                ],
                "sample_rows": [{"id": 101, "title": "Policy sample"}],
                "sample_row_count": 1,
            },
            "report_options": {"include_dashboard_sample_rows": True, "as_of_date": "2026-05-24"},
        }

        with patch("app.api.dashboard.create_document", return_value=created_doc) as mocked_create:
            resp = self.client.post("/api/v1/dashboard/report-from-filter", headers=self.headers, json=payload)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        data = body["data"]
        self.assertEqual(data["draft_id"], 321)
        self.assertEqual(data["report_id"], "writing_document:321")
        self.assertEqual(data["filters"], {"limit": 1, "doc_type": "policy"})
        self.assertEqual(data["source_refs"][0]["id"], "dashboard.stats.documents")
        self.assertEqual(data["source_query"]["table"], "documents")
        self.assertEqual(data["quality"]["status"], "ready")
        self.assertEqual(data["quality"]["quality_gate_mode"], "compatible")
        self.assertEqual(data["quality"]["next_action"], "continue_to_draft_generation")
        self.assertEqual(data["quality"]["checklist"][1]["id"], "source_refs_preserved")
        self.assertEqual(data["report_quality_gate"]["status"], "pass")
        self.assertTrue(data["report_quality_gate"]["pass"])
        self.assertEqual(data["report_quality_gate"]["source_ref_coverage"], 1.0)
        self.assertEqual(data["report_quality_gate"]["stale_source_ratio"], 0.0)
        self.assertEqual(data["report_quality_gate"]["low_trust_source_ratio"], 0.0)
        self.assertEqual(data["report_quality_gate"]["warnings"], [])
        self.assertEqual(data["report_quality_gate"]["blocking_reasons"], [])
        self.assertEqual(data["export_artifact"]["contract_version"], "llm_report.export_artifact.v1")
        self.assertTrue(data["export_artifact"]["artifact_token"].startswith("llmrpt-v1."))
        self.assertEqual(data["export_artifact"], data["artifact"])
        create_kwargs = mocked_create.call_args.kwargs
        self.assertEqual(create_kwargs["project_key"], "demo_proj")
        self.assertIn("Dashboard report draft - Documents", create_kwargs["body_md"])
        self.assertIn("Report Quality Gate", create_kwargs["body_md"])
        metadata = create_kwargs["metadata_json"]
        self.assertEqual(metadata["contract_version"], "dashboard.report_from_filter.v1")
        self.assertEqual(metadata["dashboard"]["filters"], {"limit": 1, "doc_type": "policy"})
        self.assertEqual(metadata["dashboard"]["source_refs"][0]["id"], "dashboard.stats.documents")
        self.assertEqual(metadata["dashboard"]["source_query"]["table"], "documents")
        self.assertEqual(metadata["report_quality_gate"]["status"], "pass")
        self.assertEqual(metadata["export_artifact"], data["export_artifact"])

    def test_dashboard_report_from_filter_export_pdf_then_llm_report_detail_preserves_dashboard_evidence(self):
        from app.services import llm_report_export_audit, llm_report_trends
        from app.services.llm_report_export import reset_llm_report_export_token_state

        llm_report_export_audit.clear_llm_report_export_audit_memory()
        llm_report_trends.clear_quality_trend_memory()
        reset_llm_report_export_token_state()
        created_doc = {
            "id": 324,
            "project_key": "demo_proj",
            "title": "Dashboard report draft - Documents",
            "body_md": "# placeholder",
            "status": "draft",
            "version": 1,
            "metadata_json": {},
        }

        with (
            patch("app.api.dashboard.create_document", return_value=created_doc) as mocked_create,
            patch("app.services.llm_report_trends._persist_quality_trend", return_value=False),
            patch("app.services.llm_report_export_audit._persist_export_audit_event", return_value=False),
        ):
            draft_resp = self.client.post(
                "/api/v1/dashboard/report-from-filter",
                headers=self.headers,
                json=self._dashboard_report_from_filter_payload(),
            )

            self.assertEqual(draft_resp.status_code, 200)
            draft_data = draft_resp.json()["data"]
            artifact = draft_data["export_artifact"]
            self.assertTrue(artifact["trace_id"].startswith("dashboard-report:"))
            self.assertEqual(artifact["request_id"], self.headers["X-Request-Id"])
            markdown = mocked_create.call_args.kwargs["body_md"]
            export_resp = self.client.post(
                "/api/v1/llm-report/export/pdf",
                json={
                    "markdown": markdown,
                    "quality_gate": draft_data["report_quality_gate"],
                    "quality_gate_mode": draft_data["quality"]["quality_gate_mode"],
                    "filename": "dashboard-report.pdf",
                    "project_key": "demo_proj",
                    "artifact_token": artifact["artifact_token"],
                    "artifact_sha256": artifact["artifact_sha256"],
                },
            )

            self.assertEqual(export_resp.status_code, 200)
            self.assertEqual(export_resp.headers.get("x-llm-report-source-trace-id"), artifact["trace_id"])
            detail_resp = self.client.get(
                "/api/v1/dashboard/llm-report-detail",
                headers=self.headers,
                params={"trace_id": artifact["trace_id"], "project_key": "demo_proj"},
            )

        self.assertEqual(detail_resp.status_code, 200)
        detail = detail_resp.json()["data"]
        self.assertTrue(detail["found"])
        self.assertEqual(detail["source_refs"][0]["id"], "dashboard.stats.documents")
        self.assertEqual(detail["source_query"]["table"], "documents")
        self.assertEqual(detail["quality_gate"]["status"], "pass")
        self.assertEqual(detail["report_artifact"]["artifact_id"], artifact["artifact_id"])
        self.assertNotIn("artifact_token", detail["report_artifact"])
        self.assertEqual(detail["export_audit"]["events"][0]["source_trace_id"], artifact["trace_id"])
        self.assertEqual(detail["export_events_summary"]["success"], 1)
        self.assertTrue(detail["actionability"]["has_export_events"])
        self.assertFalse(detail["actionability"]["requires_repair"])

    def test_dashboard_report_from_filter_prefers_authenticated_actor_context_over_spoofed_header_actor(self):
        created_doc = {
            "id": 322,
            "project_key": "demo_proj",
            "title": "Dashboard report draft - Documents",
            "body_md": "# Dashboard report draft - Documents",
            "status": "draft",
            "version": 1,
            "metadata_json": {},
        }
        with (
            self._authenticated_client(actor_id="auth-dashboard-actor") as client,
            patch("app.api.dashboard.create_document", return_value=created_doc) as mocked_create,
        ):
            resp = client.post(
                "/api/v1/dashboard/report-from-filter",
                headers={**self.headers, "X-Actor-Id": "spoofed-header-actor"},
                json=self._dashboard_report_from_filter_payload(),
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["export_artifact"]["actor_id"], "auth-dashboard-actor")
        self.assertEqual(data["artifact"]["actor_id"], "auth-dashboard-actor")
        metadata = mocked_create.call_args.kwargs["metadata_json"]
        self.assertEqual(metadata["export_artifact"]["actor_id"], "auth-dashboard-actor")

    def test_dashboard_report_from_filter_uses_header_actor_as_legacy_fallback_without_authenticated_context(self):
        created_doc = {
            "id": 323,
            "project_key": "demo_proj",
            "title": "Dashboard report draft - Documents",
            "body_md": "# Dashboard report draft - Documents",
            "status": "draft",
            "version": 1,
            "metadata_json": {},
        }
        with patch("app.api.dashboard.create_document", return_value=created_doc) as mocked_create:
            resp = self.client.post(
                "/api/v1/dashboard/report-from-filter",
                headers={**self.headers, "X-Actor-Id": "legacy-dashboard-actor"},
                json=self._dashboard_report_from_filter_payload(),
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["export_artifact"]["actor_id"], "legacy-dashboard-actor")
        self.assertEqual(data["artifact"]["actor_id"], "legacy-dashboard-actor")
        metadata = mocked_create.call_args.kwargs["metadata_json"]
        self.assertEqual(metadata["export_artifact"]["actor_id"], "legacy-dashboard-actor")

    def test_dashboard_report_from_filter_warns_for_stale_and_low_trust_refs(self):
        created_doc = {
            "id": 322,
            "project_key": "demo_proj",
            "title": "Dashboard report draft - Sources",
            "body_md": "# Dashboard report draft - Sources",
            "status": "draft",
            "version": 1,
            "metadata_json": {},
        }
        payload = {
            "request_type": "report_from_dashboard_filter",
            "project_key": "demo_proj",
            "dashboard": {
                "selected_label": "Sources",
                "selected_metric": "sources",
                "selected_source_ref": "dashboard.stats.sources",
                "source_query": {"scope": "dashboard.stats", "card": "sources", "table": "sources"},
                "source_refs": [
                    {
                        "id": "dashboard.stats.sources",
                        "kind": "sql_table",
                        "table": "sources",
                        "published_at": "2024-01-01",
                        "trust_score": 0.35,
                    }
                ],
            },
            "report_options": {"as_of_date": "2026-05-24", "max_source_age_days": 365},
        }

        with patch("app.api.dashboard.create_document", return_value=created_doc) as mocked_create:
            resp = self.client.post("/api/v1/dashboard/report-from-filter", headers=self.headers, json=payload)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        gate = body["data"]["report_quality_gate"]
        self.assertEqual(gate["status"], "warn")
        self.assertFalse(gate["pass"])
        self.assertFalse(gate["fail"])
        self.assertEqual(gate["source_ref_coverage"], 1.0)
        self.assertEqual(gate["stale_source_ratio"], 1.0)
        self.assertEqual(gate["low_trust_source_ratio"], 1.0)
        self.assertIn("stale_source_ratio", gate["warnings"])
        self.assertIn("low_trust_source_ratio", gate["warnings"])
        self.assertEqual(gate["blocking_reasons"], [])
        self.assertEqual(body["data"]["quality"]["quality_gate_mode"], "compatible")
        self.assertEqual(body["data"]["quality"]["next_action"], "review_quality_gate_warnings_before_export")
        mocked_create.assert_called_once()
        self.assertEqual(mocked_create.call_args.kwargs["metadata_json"]["report_quality_gate"]["status"], "warn")

    def test_dashboard_report_from_filter_strict_mode_allows_warn_gate_with_draft(self):
        created_doc = {
            "id": 324,
            "project_key": "demo_proj",
            "title": "Dashboard report draft - Sources",
            "body_md": "# Dashboard report draft - Sources",
            "status": "draft",
            "version": 1,
            "metadata_json": {},
        }
        payload = {
            "request_type": "report_from_dashboard_filter",
            "project_key": "demo_proj",
            "dashboard": {
                "selected_label": "Sources",
                "selected_metric": "sources",
                "selected_source_ref": "dashboard.stats.sources",
                "source_query": {"scope": "dashboard.stats", "card": "sources", "table": "sources"},
                "source_refs": [
                    {
                        "id": "dashboard.stats.sources",
                        "kind": "sql_table",
                        "table": "sources",
                        "published_at": "2024-01-01",
                        "trust_score": 0.35,
                    }
                ],
            },
            "report_options": {
                "as_of_date": "2026-05-24",
                "max_source_age_days": 365,
                "quality_gate_mode": "strict",
            },
        }

        with patch("app.api.dashboard.create_document", return_value=created_doc) as mocked_create:
            resp = self.client.post("/api/v1/dashboard/report-from-filter", headers=self.headers, json=payload)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        gate = body["data"]["report_quality_gate"]
        self.assertEqual(gate["status"], "warn")
        self.assertEqual(body["data"]["quality"]["quality_gate_mode"], "strict")
        self.assertEqual(body["data"]["quality"]["next_action"], "review_quality_gate_warnings_before_export")
        mocked_create.assert_called_once()

    def test_dashboard_report_from_filter_blocks_quality_gate_for_missing_selected_ref(self):
        created_doc = {
            "id": 323,
            "project_key": "demo_proj",
            "title": "Dashboard report draft - Documents",
            "body_md": "# Dashboard report draft - Documents",
            "status": "draft",
            "version": 1,
            "metadata_json": {},
        }
        payload = {
            "request_type": "report_from_dashboard_filter",
            "project_key": "demo_proj",
            "dashboard": {
                "selected_label": "Documents",
                "selected_metric": "documents",
                "selected_source_ref": "dashboard.stats.documents",
                "source_query": {"scope": "dashboard.stats", "card": "documents", "table": "documents"},
                "source_refs": [
                    {
                        "id": "dashboard.stats.sources",
                        "kind": "sql_table",
                        "table": "sources",
                        "published_at": "2026-05-01",
                        "trust_score": 0.9,
                    }
                ],
            },
            "report_options": {"as_of_date": "2026-05-24"},
        }

        with patch("app.api.dashboard.create_document", return_value=created_doc) as mocked_create:
            resp = self.client.post("/api/v1/dashboard/report-from-filter", headers=self.headers, json=payload)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        gate = body["data"]["report_quality_gate"]
        self.assertEqual(gate["status"], "blocked")
        self.assertTrue(gate["fail"])
        self.assertEqual(gate["source_ref_coverage"], 0.0)
        self.assertIn("source_ref_coverage", gate["blocking_reasons"])
        self.assertEqual(gate["evidence"]["expected_source_refs"], ["dashboard.stats.documents"])
        self.assertEqual(gate["evidence"]["covered_source_refs"], [])
        self.assertEqual(body["data"]["quality"]["quality_gate_mode"], "compatible")
        self.assertEqual(
            body["data"]["quality"]["next_action"],
            "fix_blocking_quality_gate_reasons_before_generating_report",
        )
        mocked_create.assert_called_once()

    def test_dashboard_report_from_filter_strict_mode_rejects_blocked_gate_before_draft_write(self):
        payload = {
            "request_type": "report_from_dashboard_filter",
            "project_key": "demo_proj",
            "quality_gate_mode": "strict",
            "dashboard": {
                "selected_label": "Documents",
                "selected_metric": "documents",
                "selected_source_ref": "dashboard.stats.documents",
                "source_query": {"scope": "dashboard.stats", "card": "documents", "table": "documents"},
                "source_refs": [
                    {
                        "id": "dashboard.stats.sources",
                        "kind": "sql_table",
                        "table": "sources",
                        "published_at": "2026-05-01",
                        "trust_score": 0.9,
                    }
                ],
            },
            "report_options": {"as_of_date": "2026-05-24"},
        }

        with patch("app.api.dashboard.create_document") as mocked_create:
            resp = self.client.post("/api/v1/dashboard/report-from-filter", headers=self.headers, json=payload)

        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        details = body["error"]["details"]
        self.assertEqual(details["reason_code"], "DASHBOARD_REPORT_QUALITY_GATE_BLOCKED")
        self.assertEqual(details["quality_gate_mode"], "strict")
        self.assertEqual(details["report_quality_gate"]["status"], "blocked")
        self.assertEqual(details["blocking_reasons"], ["source_ref_coverage"])
        self.assertEqual(
            details["next_action"],
            "fix_blocking_quality_gate_reasons_before_generating_report",
        )
        self.assertEqual(details["quality"]["report_quality_gate"]["status"], "blocked")
        self.assertEqual(body["detail"]["error"], body["error"])
        mocked_create.assert_not_called()

    def test_dashboard_report_from_filter_requires_source_refs_before_draft_write(self):
        payload = {
            "request_type": "report_from_dashboard_filter",
            "project_key": "demo_proj",
            "dashboard": {
                "selected_label": "Documents",
                "filters": {"limit": 1},
                "source_query": {"scope": "dashboard.stats", "card": "documents"},
                "source_refs": [],
            },
        }

        with patch("app.api.dashboard.create_document") as mocked_create:
            resp = self.client.post("/api/v1/dashboard/report-from-filter", headers=self.headers, json=payload)

        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(
            body["error"]["details"]["reason_code"],
            "DASHBOARD_REPORT_SOURCE_REFS_REQUIRED",
        )
        self.assertEqual(body["error"]["details"]["quality"]["status"], "blocked")
        self.assertEqual(body["error"]["details"]["quality"]["report_quality_gate"]["status"], "blocked")
        self.assertEqual(body["error"]["details"]["report_quality_gate"]["status"], "blocked")
        self.assertEqual(body["error"]["details"]["blocking_reasons"], ["source_ref_coverage"])
        self.assertEqual(
            body["error"]["details"]["next_action"],
            "fix_blocking_quality_gate_reasons_before_generating_report",
        )
        self.assertIn(
            "source_ref_coverage",
            body["error"]["details"]["quality"]["report_quality_gate"]["blocking_reasons"],
        )
        self.assertEqual(body["detail"]["error"], body["error"])
        mocked_create.assert_not_called()

    def test_dashboard_report_from_filter_invalid_project_keeps_exact_error_contract(self):
        payload = {
            "request_type": "report_from_dashboard_filter",
            "project_key": "demo_proj",
            "dashboard": {
                "selected_label": "Documents",
                "source_query": {"scope": "dashboard.stats", "card": "documents"},
                "source_refs": [
                    {
                        "id": "dashboard.stats.documents",
                        "kind": "sql_table",
                        "table": "documents",
                    }
                ],
            },
        }

        with patch(
            "app.api.dashboard.create_document",
            side_effect=ValueError("invalid project fixture"),
        ):
            resp = self.client.post(
                "/api/v1/dashboard/report-from-filter",
                headers=self.headers,
                json=payload,
            )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)
        body = resp.json()
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["error"]["message"], "invalid project fixture")
        self.assertEqual(body["error"]["details"]["project_key"], "demo_proj")
        self.assertEqual(body["error"]["details"]["exception_type"], "ValueError")
        self.assertEqual(body["detail"]["error"], body["error"])

    def test_dashboard_llm_report_detail_trace_hit_returns_quality_and_export_contract(self):
        quality_record = {
            "contract_version": "llm_report.quality_trend_metric.v1",
            "trace_id": "trace-detail-hit",
            "request_id": "req-detail-hit",
            "project_key": "demo_proj",
            "decision": "fail",
            "pass": False,
            "readiness": "blocked",
            "next_action": "fix_blocking_quality_gate_reasons_before_generating_report",
            "citation_coverage": 0.25,
            "evidence_coverage": 0.5,
            "source_count": 2,
            "missing_items_count": 1,
            "hard_failure_count": 1,
            "soft_failure_count": 0,
            "job_id": 2001,
            "job_status": "failed",
            "topic": "Dashboard report draft - Documents",
            "recorded_at": "2026-05-24T00:03:00+00:00",
            "source_refs": [
                {
                    "id": "dashboard.stats.documents",
                    "kind": "sql_table",
                    "table": "documents",
                    "columns": ["id", "title", "extracted_data"],
                }
            ],
            "source_query": {
                "scope": "dashboard.stats",
                "card": "documents",
                "table": "documents",
                "metrics": ["total", "extraction_rate"],
                "filters": {"doc_type": "policy"},
            },
            "report_artifact": {
                "contract_version": "llm_report.export_artifact.v1",
                "artifact_id": "artifact-detail-hit",
                "artifact_sha256": "f" * 64,
                "artifact_token": "llmrpt-v1.detail-hit",
                "filename": "dashboard-detail-hit.pdf",
            },
            "quality_gate": {
                "gate_version": "dashboard.report_quality_gate.v1",
                "status": "blocked",
                "pass": False,
                "fail": True,
                "blocking_reasons": ["source_ref_coverage"],
                "warnings": [],
            },
        }
        export_event = {
            "contract_version": "llm_report.export_audit_event.v1",
            "event_type": "llm_report_export",
            "record_source": "export_audit",
            "trace_id": "trace-detail-export",
            "source_trace_id": "trace-detail-hit",
            "project_key": "demo_proj",
            "actor_id": "analyst-1",
            "export_format": "pdf",
            "export_outcome": "blocked",
            "outcome": "blocked",
            "export_integrity_mode": "artifact_token",
            "integrity_mode": "artifact_token",
            "export_integrity_trusted": True,
            "integrity_trusted": True,
            "ui_read_only_context_included": True,
            "ui_read_only_context_scope": "ui_read_only_evidence_context",
            "artifact_id": "artifact-detail-hit",
            "artifact_sha256": "f" * 64,
            "filename": "dashboard-detail-hit.pdf",
            "content_type": "application/pdf",
            "recorded_at": "2026-05-24T00:04:00+00:00",
        }
        export_event_string_context = {
            **export_event,
            "trace_id": "trace-detail-export-string-context",
            "export_format": "docx",
            "export_outcome": "success",
            "outcome": "success",
            "ui_read_only_context_included": "true",
            "recorded_at": "2026-05-24T00:05:00+00:00",
        }

        with (
            patch(
                "app.api.dashboard.list_quality_trend_records_for_trace_ids",
                return_value=([quality_record], {"merged_count": 1}),
            ),
            patch("app.api.dashboard.list_quality_trend_records", return_value=([quality_record], {"merged_count": 1})),
            patch(
                "app.api.dashboard.list_llm_report_export_audit_events_for_trace",
                return_value=([export_event, export_event_string_context], {"merged_count": 2}),
            ),
            patch(
                "app.api.dashboard.list_recent_llm_report_export_audit_events",
                return_value=[export_event, export_event_string_context],
            ),
        ):
            resp = self.client.get(
                "/api/v1/dashboard/llm-report-detail",
                headers=self.headers,
                params={"trace_id": "trace-detail-hit"},
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(body.keys()))
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        data = body["data"]
        self.assertEqual(data["contract_version"], "dashboard.llm_report_detail.v1")
        self.assertTrue(data["found"])
        self.assertEqual(data["trace_id"], "trace-detail-hit")
        self.assertEqual(data["quality_record"]["trace_id"], "trace-detail-hit")
        self.assertEqual(data["export_audit"]["events"][0]["source_trace_id"], "trace-detail-hit")
        self.assertEqual(data["export_audit"]["summary"]["total"], 2)
        self.assertEqual(data["export_audit"]["summary"]["blocked"], 1)
        self.assertEqual(data["export_audit"]["summary"]["success"], 1)
        self.assertEqual(data["export_audit"]["summary"]["ui_read_only_context_included_count"], 1)
        self.assertEqual(data["export_audit"]["summary"]["by_format"], {"pdf": 1, "docx": 1})
        self.assertEqual(
            data["export_audit"]["summary"]["read_only_context_semantics"],
            (
                "ui_read_only_context_included_count is detail observability only; it is not report proof, "
                "not quality gate input, not scheduled_run_evidence proof, and does not change export audit outcome."
            ),
        )
        self.assertEqual(data["export_events_summary"]["ui_read_only_context_included_count"], 1)
        self.assertEqual(data["source_refs"][0]["id"], "dashboard.stats.documents")
        self.assertEqual(data["source_query"]["table"], "documents")
        self.assertEqual(data["report_artifact"]["artifact_id"], "artifact-detail-hit")
        self.assertEqual(data["quality_gate"]["status"], "blocked")
        self.assertEqual(data["repair_context"]["trace_id"], "trace-detail-hit")
        self.assertEqual(data["repair_context"]["source_refs"][0]["id"], "dashboard.stats.documents")
        self.assertEqual(
            data["repair_context"]["next_action"],
            "fix_blocking_quality_gate_reasons_before_generating_report",
        )
        self.assertTrue(data["actionability"]["requires_repair"])
        self.assertEqual(
            data["actionability"]["next_action"],
            "fix_blocking_quality_gate_reasons_before_generating_report",
        )

    def test_dashboard_llm_report_detail_trace_miss_returns_actionable_not_found_contract(self):
        export_event = {
            "contract_version": "llm_report.export_audit_event.v1",
            "event_type": "llm_report_export",
            "record_source": "export_audit",
            "trace_id": "other-export",
            "source_trace_id": "other-trace",
            "project_key": "demo_proj",
            "export_format": "pdf",
            "export_outcome": "success",
            "outcome": "success",
            "recorded_at": "2026-05-24T00:04:00+00:00",
        }

        with (
            patch("app.api.dashboard.list_quality_trend_records", return_value=([], {"merged_count": 0})),
            patch(
                "app.api.dashboard.list_recent_llm_report_export_audit_events",
                return_value=[export_event],
            ),
        ):
            resp = self.client.get(
                "/api/v1/dashboard/llm-report-detail",
                headers=self.headers,
                params={"trace_id": "missing-trace"},
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        data = body["data"]
        self.assertEqual(data["contract_version"], "dashboard.llm_report_detail.v1")
        self.assertFalse(data["found"])
        self.assertEqual(data["trace_id"], "missing-trace")
        self.assertEqual(data["quality_record"], None)
        self.assertEqual(data["export_audit"]["events"], [])
        self.assertEqual(data["source_refs"], [])
        self.assertEqual(data["source_query"]["filters"]["trace_id"], "missing-trace")
        self.assertFalse(data["actionability"]["requires_repair"])
        self.assertEqual(data["actionability"]["next_action"], "refresh_llm_report_quality_trends")
        self.assertEqual(data["repair_context"]["trace_id"], "missing-trace")
        self.assertEqual(data["repair_context"]["next_action"], "refresh_llm_report_quality_trends")
        self.assertIn("missing-trace", data["repair_context"]["message"])

    def test_dashboard_llm_report_detail_empty_trace_id_returns_error_envelope(self):
        with (
            patch("app.api.dashboard.list_quality_trend_records") as mocked_quality,
            patch("app.api.dashboard.list_recent_llm_report_export_audit_events") as mocked_audit,
        ):
            resp = self.client.get(
                "/api/v1/dashboard/llm-report-detail",
                headers=self.headers,
                params={"trace_id": ""},
            )

        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["error"]["details"]["reason_code"], "DASHBOARD_LLM_REPORT_TRACE_ID_REQUIRED")
        self.assertEqual(body["detail"]["error"], body["error"])
        mocked_quality.assert_not_called()
        mocked_audit.assert_not_called()

    def test_dashboard_stats_db_failure_maps_to_upstream_error(self):
        with patch("app.api.dashboard.SessionLocal", return_value=_FakeSessionLocalOperationalError()):
            resp = self.client.get("/api/v1/dashboard/stats", headers=self.headers)

        self.assertEqual(resp.status_code, 503)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.UPSTREAM_ERROR.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.UPSTREAM_ERROR.value)

    def test_admin_get_document_not_found_returns_error_envelope(self):
        with patch("app.api.admin.SessionLocal", return_value=_FakeAdminSessionLocal()):
            resp = self.client.get("/api/v1/admin/documents/999", headers=self.headers)

        self.assertEqual(resp.status_code, 404)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)

    def test_admin_update_document_invalid_merge_returns_error_envelope(self):
        doc = SimpleNamespace(id=1, extracted_data="raw")
        with patch("app.api.admin.SessionLocal", return_value=_FakeAdminSessionLocal(doc)):
            resp = self.client.post(
                "/api/v1/admin/documents/1/extracted-data",
                headers=self.headers,
                json={"mode": "merge", "extracted_data": {"a": 1}},
            )

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_admin_bulk_update_requires_doc_ids_returns_error_envelope(self):
        from app.api.admin import BulkUpdateExtractedDataRequest, bulk_update_document_extracted_data

        resp = bulk_update_document_extracted_data(
            BulkUpdateExtractedDataRequest(doc_ids=[], mode="replace", extracted_data={})
        )

        self.assertEqual(resp.status_code, 400)
        body = json.loads(resp.body)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_admin_bulk_update_extracted_data_preview_returns_impact_without_writes(self):
        from app.api.admin import BulkUpdateExtractedDataRequest, bulk_update_document_extracted_data

        docs = [
            SimpleNamespace(
                id=1,
                title="Policy A",
                doc_type="policy",
                state="CA",
                uri="https://example.com/policy-a",
                source_id=11,
                content="policy content",
                extracted_data={"policy": {"agency": "A"}},
            ),
            SimpleNamespace(
                id=2,
                title="Market B",
                doc_type="market_info",
                state=None,
                uri="https://example.com/market-b",
                source_id=12,
                content="market content",
                extracted_data=None,
            ),
        ]
        fake_session = _FakePreviewDeleteSession(docs)

        with patch("app.api.admin.SessionLocal", return_value=_FakePreviewDeleteSessionLocal(fake_session)):
            resp = bulk_update_document_extracted_data(
                BulkUpdateExtractedDataRequest(
                    doc_ids=[1, 2, 99],
                    preview=True,
                    mode="merge",
                    extracted_data={"manual": {"reviewed": True}},
                )
            )

        self.assertFalse(fake_session.committed)
        self.assertEqual(docs[0].extracted_data, {"policy": {"agency": "A"}})
        self.assertIsNone(docs[1].extracted_data)
        self.assertEqual(resp["status"], "ok")
        self.assertIsNone(resp["error"])
        self.assertEqual(resp["data"]["preview"], True)
        self.assertEqual(resp["data"]["action_kind"], "documents.bulk_extracted_data")
        self.assertEqual(resp["data"]["would_affect_count"], 2)
        self.assertEqual(resp["data"]["samples"][0]["id"], 1)
        self.assertEqual(resp["data"]["missing"], [99])
        self.assertIn("bulk_write", resp["data"]["risk_tags"])
        self.assertIn("merge_write", resp["data"]["risk_tags"])
        self.assertIn("missing_ids", resp["data"]["risk_tags"])
        self.assertEqual(resp["data"]["risk_labels"], resp["data"]["risk_tags"])
        self.assertEqual(resp["data"]["requires_confirmation"], True)
        self.assertEqual(resp["data"]["source_query"]["scope"], "admin.preview")
        self.assertEqual(resp["data"]["source_query"]["action"], "documents.bulk_extracted_data")
        self.assertEqual(resp["data"]["source_query"]["filters"]["mode"], "merge")
        self.assertEqual(resp["data"]["source_query"]["selection"]["requested_ids"], [1, 2, 99])
        self.assertEqual(resp["data"]["source_query"]["selection"]["missing_ids"], [99])
        self.assertEqual(resp["data"]["source_refs"][0]["document_id"], 1)
        self.assertEqual(resp["data"]["source_refs"][0]["uri"], "https://example.com/policy-a")
        self.assertEqual(resp["data"]["trace_chain"][0]["stage"], "admin.preview.request")
        self.assertEqual(resp["data"]["trace_chain"][1]["matched_count"], 2)
        self.assertEqual(resp["data"]["trace_chain"][2]["requires_confirmation"], True)
        self.assertEqual(resp["data"]["evidence_preview"]["evidence_kind"], "document_selection")
        self.assertEqual(resp["data"]["evidence_preview"]["documents_matched"], 2)
        self.assertFalse(resp["data"]["evidence_preview"]["execution_result_available"])

    def test_admin_delete_documents_preview_returns_impact_without_writes(self):
        from app.api.admin import DeleteDocumentsRequest, delete_documents

        docs = [
            SimpleNamespace(
                id=1,
                title="Policy A",
                doc_type="policy",
                state="CA",
                uri="https://example.com/policy-a",
                source_id=11,
                extracted_data={"policy": {"agency": "A"}},
            ),
            SimpleNamespace(
                id=2,
                title="Market B",
                doc_type="market_info",
                state=None,
                uri="https://example.com/market-b",
                source_id=12,
                extracted_data=None,
            ),
        ]
        fake_session = _FakePreviewDeleteSession(docs)

        with patch("app.api.admin.SessionLocal", return_value=_FakePreviewDeleteSessionLocal(fake_session)):
            resp = delete_documents(DeleteDocumentsRequest(ids=[1, 2, 99], preview=True))

        self.assertFalse(fake_session.deleted)
        self.assertFalse(fake_session.committed)
        self.assertEqual(resp["status"], "ok")
        self.assertIsNone(resp["error"])
        self.assertEqual(resp["data"]["preview"], True)
        self.assertEqual(resp["data"]["action"], "documents.delete")
        self.assertEqual(resp["data"]["would_affect_count"], 2)
        self.assertEqual(resp["data"]["samples"][0]["id"], 1)
        self.assertEqual(resp["data"]["missing"], [99])
        self.assertIn("destructive_write", resp["data"]["risk_tags"])
        self.assertIn("bulk_delete", resp["data"]["risk_tags"])
        self.assertIn("missing_ids", resp["data"]["risk_tags"])
        self.assertEqual(resp["data"]["risk_labels"], resp["data"]["risk_tags"])
        self.assertEqual(resp["data"]["requires_confirmation"], True)
        self.assertEqual(resp["data"]["source_query"]["scope"], "admin.preview")
        self.assertEqual(resp["data"]["source_query"]["action"], "documents.delete")
        self.assertEqual(resp["data"]["source_query"]["filters"]["ids"], [1, 2, 99])
        self.assertEqual(resp["data"]["source_query"]["selection"]["missing_count"], 1)
        self.assertEqual(resp["data"]["source_refs"][0]["kind"], "document_record")
        self.assertEqual(resp["data"]["source_refs"][0]["document_id"], 1)
        self.assertEqual(resp["data"]["source_refs"][0]["source_id"], 11)
        self.assertEqual(resp["data"]["trace_chain"][2]["status"], "required")
        self.assertEqual(resp["data"]["evidence_preview"]["missing_ids"], [99])
        self.assertFalse(resp["data"]["evidence_preview"]["execution_result_available"])

    def test_admin_delete_documents_execution_returns_response_audit_readback(self):
        from app.api.admin import DeleteDocumentsRequest, delete_documents

        docs = [
            SimpleNamespace(
                id=1,
                title="Policy A",
                doc_type="policy",
                state="CA",
                uri="https://example.com/policy-a",
                source_id=11,
                extracted_data={"policy": {"agency": "A"}},
            ),
            SimpleNamespace(
                id=2,
                title="Market B",
                doc_type="market_info",
                state=None,
                uri="https://example.com/market-b",
                source_id=12,
                extracted_data=None,
            ),
        ]
        fake_session = _FakePreviewDeleteSession(docs)

        with patch("app.api.admin.SessionLocal", return_value=_FakePreviewDeleteSessionLocal(fake_session)):
            resp = delete_documents(DeleteDocumentsRequest(ids=[1, 2, 99], preview=False))

        self.assertEqual(fake_session.deleted, docs)
        self.assertTrue(fake_session.committed)
        data = resp["data"]
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(data["deleted"], 2)
        self.assertEqual(data["missing"], [99])
        self.assertEqual(data["action_kind"], "documents.delete")
        self.assertEqual(data["audit_event"]["action_kind"], "documents.delete")
        self.assertEqual(data["audit_event"]["requested_count"], 3)
        self.assertEqual(data["audit_event"]["affected_count"], 2)
        self.assertEqual(data["audit_event"]["status"], "completed_with_missing")
        self.assertEqual(data["audit_event"]["audit_scope"], "response_level_only")
        self.assertEqual(data["audit_event"]["persistence"], "not_persisted")
        self.assertTrue(data["audit_event"]["trace_id"].startswith("admin-response-readback-"))
        self.assertEqual(data["audit_trail"][0], data["audit_event"])
        self.assertTrue(data["execution_result"]["execution_result_available"])
        self.assertEqual(data["execution_result"]["affected_count"], 2)
        self.assertEqual(data["execution_result"]["deleted_count"], 2)
        self.assertEqual(data["execution_result"]["missing_ids"], [99])
        self.assertEqual(data["source_query"]["scope"], "admin.after_action.response_readback")
        self.assertEqual(data["source_query"]["selection"]["affected_count"], 2)
        self.assertEqual(data["source_refs"][0]["document_id"], 1)
        self.assertEqual(data["trace_chain"][2]["stage"], "admin.after_action.mutation")
        self.assertTrue(data["trace_chain"][3]["execution_result_available"])
        self.assertEqual(data["response_level_audit_readback"]["persistence"], "not_persisted")
        self.assertIn("not automatically reversible", data["rollback_hint"])

    def test_admin_bulk_update_extracted_data_execution_returns_response_audit_readback(self):
        from app.api.admin import BulkUpdateExtractedDataRequest, bulk_update_document_extracted_data

        docs = [
            SimpleNamespace(
                id=1,
                title="Policy A",
                doc_type="policy",
                state="CA",
                uri="https://example.com/policy-a",
                source_id=11,
                content="policy content",
                extracted_data={"policy": {"agency": "A"}},
            ),
            SimpleNamespace(
                id=2,
                title="Market B",
                doc_type="market_info",
                state=None,
                uri="https://example.com/market-b",
                source_id=12,
                content="market content",
                extracted_data=None,
            ),
        ]
        fake_session = _FakePreviewDeleteSession(docs)

        with patch("app.api.admin.SessionLocal", return_value=_FakePreviewDeleteSessionLocal(fake_session)):
            resp = bulk_update_document_extracted_data(
                BulkUpdateExtractedDataRequest(
                    doc_ids=[1, 2, 99],
                    preview=False,
                    mode="merge",
                    extracted_data={"manual": {"reviewed": True}},
                )
            )

        self.assertTrue(fake_session.committed)
        self.assertEqual(docs[0].extracted_data, {"policy": {"agency": "A"}, "manual": {"reviewed": True}})
        self.assertEqual(docs[1].extracted_data, {"manual": {"reviewed": True}})
        data = resp["data"]
        self.assertEqual(data["updated"], 2)
        self.assertEqual(data["skipped"], 0)
        self.assertEqual(data["missing"], [99])
        self.assertEqual(data["action_kind"], "documents.bulk_extracted_data")
        self.assertEqual(data["audit_event"]["action_kind"], "documents.bulk_extracted_data")
        self.assertEqual(data["audit_event"]["affected_count"], 2)
        self.assertEqual(data["audit_event"]["status"], "completed_with_skips")
        self.assertTrue(data["execution_result"]["execution_result_available"])
        self.assertEqual(data["execution_result"]["updated_count"], 2)
        self.assertEqual(data["execution_result"]["skipped_count"], 0)
        self.assertEqual(data["execution_result"]["missing_ids"], [99])
        self.assertEqual(data["execution_result"]["mode"], "merge")
        self.assertEqual(data["source_query"]["filters"]["mode"], "merge")
        self.assertEqual(data["source_query"]["selection"]["requested_ids"], [1, 2, 99])
        self.assertEqual(data["source_refs"][0]["id"], "admin.after_action.documents.bulk_extracted_data.document:1")
        self.assertEqual(data["trace_chain"][3]["stage"], "admin.after_action.response_readback")
        self.assertEqual(data["response_level_audit_readback"]["scope"], "response_level_only")
        self.assertIn("no automatic rollback", data["rollback_recommendation"])

    def test_admin_reextract_preview_returns_impact_without_mutation(self):
        from app.api.admin import ReExtractRequest, re_extract_documents

        docs = [
            SimpleNamespace(
                id=1,
                title="Policy A",
                doc_type="policy",
                state="CA",
                content="policy content",
                uri="https://example.com/a",
                source_id=11,
                extracted_data={"policy": {"agency": "A"}},
            ),
            SimpleNamespace(
                id=2,
                title="Market B",
                doc_type="market_info",
                state=None,
                content="market content",
                uri="https://example.com/b",
                source_id=12,
                extracted_data=None,
            ),
        ]
        fake_session = _FakePreviewDeleteSession(docs)

        with (
            patch("app.api.admin.SessionLocal", return_value=_FakePreviewDeleteSessionLocal(fake_session)),
            patch("app.api.admin.run_frontdoor_extraction") as mocked_extract,
            patch("app.api.admin.fetch_html") as mocked_fetch,
        ):
            resp = re_extract_documents(
                ReExtractRequest(
                    doc_ids=[1, 2],
                    preview=True,
                    force=True,
                    fetch_missing_content=True,
                    batch_size=5,
                )
            )

        mocked_extract.assert_not_called()
        mocked_fetch.assert_not_called()
        self.assertFalse(fake_session.committed)
        self.assertEqual(docs[0].extracted_data, {"policy": {"agency": "A"}})
        self.assertIsNone(docs[1].extracted_data)
        self.assertEqual(resp["status"], "ok")
        self.assertIsNone(resp["error"])
        self.assertEqual(resp["data"]["preview"], True)
        self.assertEqual(resp["data"]["action_kind"], "documents.re_extract")
        self.assertEqual(resp["data"]["would_affect_count"], 2)
        self.assertEqual(resp["data"]["samples"][0]["id"], 1)
        self.assertIn("bulk_reextract", resp["data"]["risk_tags"])
        self.assertIn("force_overwrite", resp["data"]["risk_tags"])
        self.assertIn("may_fetch_missing_content", resp["data"]["risk_tags"])
        self.assertEqual(resp["data"]["risk_labels"], resp["data"]["risk_tags"])
        self.assertEqual(resp["data"]["requires_confirmation"], True)
        self.assertEqual(resp["data"]["source_query"]["scope"], "admin.preview")
        self.assertEqual(resp["data"]["source_query"]["action"], "documents.re_extract")
        self.assertEqual(resp["data"]["source_query"]["filters"]["force"], True)
        self.assertEqual(resp["data"]["source_query"]["filters"]["fetch_missing_content"], True)
        self.assertEqual(resp["data"]["source_query"]["selection"]["requested_ids"], [1, 2])
        self.assertEqual(resp["data"]["source_refs"][0]["document_id"], 1)
        self.assertEqual(resp["data"]["source_refs"][0]["uri"], "https://example.com/a")
        self.assertEqual(resp["data"]["trace_chain"][1]["status"], "matched")
        self.assertEqual(resp["data"]["trace_chain"][2]["risk_tags"], resp["data"]["risk_tags"])
        self.assertEqual(resp["data"]["evidence_preview"]["source"], "admin_preview")
        self.assertFalse(resp["data"]["evidence_preview"]["fields_are_predicted"])

    def test_admin_reextract_execution_returns_response_audit_readback(self):
        from app.api.admin import ReExtractRequest, re_extract_documents

        docs = [
            SimpleNamespace(
                id=1,
                title="Policy A",
                summary="summary A",
                doc_type="policy",
                state="CA",
                content="policy content",
                uri="https://example.com/a",
                source_id=11,
                extracted_data={},
            ),
            SimpleNamespace(
                id=2,
                title="Market B",
                summary="summary B",
                doc_type="market_info",
                state=None,
                content="market content",
                uri="https://example.com/b",
                source_id=12,
                extracted_data=None,
            ),
        ]
        fake_session = _FakePreviewDeleteSession(docs)

        with (
            patch("app.api.admin.SessionLocal", return_value=_FakePreviewDeleteSessionLocal(fake_session)),
            patch(
                "app.api.admin.run_frontdoor_extraction",
                return_value={
                    "status": "success",
                    "domains": {"policy": {"agency": "A"}},
                    "summary": {"domain_count": 1},
                },
            ) as mocked_extract,
        ):
            resp = re_extract_documents(
                ReExtractRequest(
                    doc_ids=[1, 2],
                    preview=False,
                    force=True,
                    batch_size=5,
                )
            )

        self.assertEqual(mocked_extract.call_count, 2)
        self.assertTrue(fake_session.committed)
        self.assertEqual(docs[0].extracted_data["policy"], {"agency": "A"})
        self.assertEqual(docs[0].extracted_data["structured_extraction_status"], "success")
        data = resp["data"]
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["success"], 2)
        self.assertEqual(data["error"], 0)
        self.assertEqual(data["skipped"], 0)
        self.assertEqual(data["action_kind"], "documents.re_extract")
        self.assertEqual(data["audit_event"]["action_kind"], "documents.re_extract")
        self.assertEqual(data["audit_event"]["affected_count"], 2)
        self.assertEqual(data["audit_event"]["status"], "completed")
        self.assertTrue(data["execution_result"]["execution_result_available"])
        self.assertEqual(data["execution_result"]["success_count"], 2)
        self.assertEqual(data["execution_result"]["error_count"], 0)
        self.assertEqual(data["execution_result"]["missing_ids"], [])
        self.assertEqual(data["source_query"]["filters"]["force"], True)
        self.assertEqual(data["source_query"]["selection"]["affected_count"], 2)
        self.assertEqual(data["source_refs"][0]["document_id"], 1)
        self.assertEqual(data["trace_chain"][2]["status"], "completed")
        self.assertIn("not automatically reversible", data["rollback_hint"])

    def test_admin_export_graph_empty_doc_ids_returns_error_envelope(self):
        resp = self.client.get("/api/v1/admin/export-graph?doc_ids=", headers=self.headers)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_admin_export_graph_invalid_doc_ids_returns_error_envelope(self):
        resp = self.client.get("/api/v1/admin/export-graph?doc_ids=1,abc", headers=self.headers)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_admin_content_graph_invalid_start_date_returns_error_envelope(self):
        resp = self.client.get("/api/v1/admin/content-graph?start_date=not-a-date&limit=10", headers=self.headers)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["details"]["field"], "start_date")
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_admin_market_graph_invalid_start_date_returns_error_envelope(self):
        resp = self.client.get("/api/v1/admin/market-graph?start_date=2026-13-99&limit=10", headers=self.headers)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["details"]["field"], "start_date")
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_admin_policy_graph_invalid_end_date_returns_error_envelope(self):
        resp = self.client.get("/api/v1/admin/policy-graph?end_date=bad-date&limit=10", headers=self.headers)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["detail"]["error"]["details"]["field"], "end_date")
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_dashboard_ecom_price_trends_invalid_start_date_returns_422_invalid_input(self):
        resp = self.client.get(
            "/api/v1/dashboard/ecom-price-trends",
            headers=self.headers,
            params={"start_date": "2026-01-01"},
        )

        self.assertEqual(resp.status_code, 422)
        body = resp.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(body.keys()))
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("start_date", body["error"]["message"])
        self.assertIn("ISO8601 datetime", body["error"]["message"])
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_process_stats_success_returns_envelope(self):
        inspect = SimpleNamespace(
            active=lambda: {"w1": [{"id": "a1"}]},
            registered=lambda: {"w1": ["task.alpha", "task.beta"]},
            scheduled=lambda: {"w1": [{"request": {"id": "s1"}}]},
            reserved=lambda: {"w1": [{"id": "r1"}]},
        )

        with patch("app.api.process.celery_app.control.inspect", return_value=inspect):
            resp = self.client.get("/api/v1/process/stats", headers=self.headers)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(body.keys()))
        self.assertEqual(body["status"], "ok")
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["active_tasks"], 1)
        self.assertEqual(body["data"]["total_running"], 3)

    def test_process_stats_failure_maps_to_internal_error(self):
        inspect = SimpleNamespace(
            active=Mock(side_effect=RuntimeError("inspect failed")),
            registered=lambda: {},
            scheduled=lambda: {},
            reserved=lambda: {},
        )

        with patch("app.api.process.celery_app.control.inspect", return_value=inspect):
            resp = self.client.get("/api/v1/process/stats", headers=self.headers)

        self.assertEqual(resp.status_code, 500)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INTERNAL_ERROR.value)


if __name__ == "__main__":
    unittest.main()
