from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient
    from app.main import app as backend_app

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


if __name__ == "__main__":
    unittest.main()
