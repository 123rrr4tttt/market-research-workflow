from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient
    from app.api import project_customization as customization_api
    from app.main import app as backend_app
    from app.project_customization.interfaces import WorkflowDefinition, WorkflowStep

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


def _compact_json(value: object, max_len: int = 220) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= max_len:
        return text
    return text[:max_len] + "...(truncated)"


class ProjectSchemaGuardTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"project schema guard tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.base_headers = {"X-Request-Id": "project-schema-guard"}

    def test_dashboard_stats_is_available_for_each_project(self):
        projects_resp = self.client.get("/api/v1/projects", headers={"X-Project-Key": "default", **self.base_headers})
        if projects_resp.status_code != 200 and os.getenv("DOCKER_ENV") != "true":
            self.skipTest(f"project schema guard requires a reachable database, got {projects_resp.status_code}")
        self.assertEqual(
            projects_resp.status_code,
            200,
            f"/api/v1/projects should be available, got {projects_resp.status_code}: {projects_resp.text}",
        )
        projects_body = projects_resp.json()
        items = ((projects_body.get("data") or {}).get("items") or []) if isinstance(projects_body, dict) else []
        self.assertIsInstance(items, list, f"projects payload shape changed: {_compact_json(projects_body)}")

        broken: list[str] = []
        for item in items:
            project_key = str((item or {}).get("project_key") or "").strip()
            if not project_key:
                continue

            resp = self.client.get(
                "/api/v1/dashboard/stats",
                headers={
                    "X-Project-Key": project_key,
                    "X-Request-Id": f"project-schema-guard:{project_key}",
                },
            )

            body: object
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                body = {"raw": resp.text}

            if resp.status_code != 200:
                broken.append(f"{project_key}: http={resp.status_code}, body={_compact_json(body)}")
                continue

            if not isinstance(body, dict) or body.get("status") != "ok":
                broken.append(f"{project_key}: unexpected envelope={_compact_json(body)}")
                continue

            data = body.get("data") or {}
            documents = data.get("documents") if isinstance(data, dict) else None
            if not isinstance(documents, dict) or "total" not in documents:
                broken.append(f"{project_key}: missing documents.total in payload={_compact_json(body)}")

        if broken:
            self.fail(
                "Project schema guard failed. Dashboard stats unavailable for project(s):\n"
                + "\n".join(f"- {line}" for line in broken)
            )

    def test_project_customization_workflow_dry_run_schema_has_preview_fields(self):
        workflow = WorkflowDefinition(steps=[WorkflowStep(handler="ingest.market", params={"limit": 1})])

        with (
            patch.object(
                customization_api,
                "get_project_customization",
                return_value=SimpleNamespace(
                    project_key="schema_proj",
                    get_workflow_mapping=lambda: {"demo": workflow},
                ),
            ),
            patch.object(customization_api, "load_custom_workflow_definition", return_value=None),
            patch.object(customization_api, "load_custom_workflow_board_layout", return_value={}),
            patch.object(
                customization_api,
                "get_config",
                return_value={"payload": {"version": 3, "workflows": {}, "boards": {}}},
            ),
            patch.object(customization_api, "execute_project_workflow") as execute_project_workflow,
        ):
            resp = self.client.post(
                "/api/v1/project-customization/workflows/demo/run",
                json={"project_key": "schema_proj", "dry_run": True, "params": {}},
                headers=self.base_headers,
            )

        self.assertEqual(resp.status_code, 200, resp.text)
        execute_project_workflow.assert_not_called()
        body = resp.json()
        self.assertEqual(body.get("status"), "ok", _compact_json(body))
        data = body.get("data") or {}
        self.assertTrue(data.get("dry_run"), _compact_json(body))
        self.assertEqual(data.get("missing_dependencies"), [], _compact_json(body))
        self.assertEqual(data.get("config_version"), 3, _compact_json(body))
        self.assertEqual(data.get("current_version"), 3, _compact_json(body))
        impact = data.get("impact_summary") or {}
        self.assertFalse(impact.get("will_execute"), _compact_json(body))
        self.assertTrue(impact.get("writes_blocked"), _compact_json(body))

    def test_project_customization_workflow_template_diff_schema_has_version_fields(self):
        workflow = WorkflowDefinition(steps=[WorkflowStep(handler="ingest.market", params={"limit": 1})])

        with (
            patch.object(
                customization_api,
                "get_project_customization",
                return_value=SimpleNamespace(
                    project_key="schema_proj",
                    get_workflow_mapping=lambda: {"demo": workflow},
                ),
            ),
            patch.object(customization_api, "load_custom_workflow_definition", return_value=None),
            patch.object(customization_api, "load_custom_workflow_board_layout", return_value={}),
            patch.object(
                customization_api,
                "get_config",
                return_value={"payload": {"version": 4, "workflows": {}, "boards": {}}},
            ),
            patch.object(customization_api, "upsert_config") as upsert_config,
        ):
            resp = self.client.post(
                "/api/v1/project-customization/workflows/demo/template/diff",
                json={
                    "project_key": "schema_proj",
                    "steps": [{"handler": "ingest.market", "params": {"limit": 2}}],
                    "board_layout": {},
                },
                headers=self.base_headers,
            )

        self.assertEqual(resp.status_code, 200, resp.text)
        upsert_config.assert_not_called()
        body = resp.json()
        self.assertEqual(body.get("status"), "ok", _compact_json(body))
        data = body.get("data") or {}
        self.assertEqual(data.get("current_version"), 4, _compact_json(body))
        self.assertEqual(data.get("next_version"), 5, _compact_json(body))
        version_summary = data.get("version_summary") or {}
        self.assertEqual(version_summary.get("stage"), "draft_preview", _compact_json(body))
        self.assertFalse(version_summary.get("will_mutate"), _compact_json(body))
        diff = data.get("diff") or {}
        self.assertEqual(diff.get("step_count_before"), 1, _compact_json(body))
        self.assertEqual(diff.get("step_count_after"), 1, _compact_json(body))
        self.assertTrue(diff.get("steps"), _compact_json(body))


if __name__ == "__main__":
    unittest.main()
