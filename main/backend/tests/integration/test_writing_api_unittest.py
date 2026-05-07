from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app
    from app.services.writing.document_service import WritingVersionConflictError

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class WritingApiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"writing integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "writing-integration"}

    def test_create_document_success(self):
        with patch(
            "app.api.writing.create_document",
            return_value={"id": 101, "project_key": "demo_proj", "title": "Draft", "body_md": "", "version": 1, "etag": "abc"},
        ):
            response = self.client.post("/api/v1/writing/documents", json={"title": "Draft"}, headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["id"], 101)

    def test_patch_document_conflict(self):
        conflict = WritingVersionConflictError(
            expected_version=1,
            current_version=2,
            server_snapshot={"conflict_code": "VERSION_CONFLICT", "current_version": 2},
        )
        with patch("app.api.writing.save_document_with_conflict", side_effect=conflict):
            response = self.client.patch(
                "/api/v1/writing/documents/101",
                json={"body_md": "new body", "base_version": 1},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.headers.get("x-error-code"), "INVALID_INPUT")

    def test_export_markdown_success(self):
        with (
            patch(
                "app.api.writing.export_document_markdown",
                return_value={"doc_id": 101, "project_key": "demo_proj", "filename": "writing-document-101.md", "markdown": "# Draft"},
            ),
            patch("app.api.writing.list_citations", return_value=[]),
        ):
            response = self.client.post("/api/v1/writing/export/markdown", json={"doc_id": 101}, headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment; filename=writing-document-101.md", response.headers.get("content-disposition", ""))
        self.assertEqual(response.text, "# Draft")

    def test_get_document_not_found_returns_structured_error(self):
        with patch("app.api.writing.get_document", side_effect=KeyError("document not found")):
            response = self.client.get("/api/v1/writing/documents/101", headers=self.headers)

        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)

    def test_autosave_not_found_returns_structured_error(self):
        with patch("app.api.writing.save_draft_autosave", side_effect=KeyError("document not found")):
            response = self.client.post(
                "/api/v1/writing/documents/101/draft",
                json={"draft_body_md": "draft", "autosave_token": "token-1"},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)

    def test_export_markdown_not_found_returns_structured_error(self):
        with patch("app.api.writing.export_document_markdown", side_effect=KeyError("document not found")):
            response = self.client.post("/api/v1/writing/export/markdown", json={"doc_id": 101}, headers=self.headers)

        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)

    def test_create_document_project_context_value_error_returns_invalid_input(self):
        @contextmanager
        def _broken_bind(_project_key):
            raise ValueError("reserved project key")
            yield

        with patch("app.api.writing.bind_project", _broken_bind):
            response = self.client.post("/api/v1/writing/documents", json={"title": "Draft"}, headers=self.headers)

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)


if __name__ == "__main__":
    unittest.main()
