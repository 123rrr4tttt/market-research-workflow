from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.writing.document_service import (
        WritingVersionConflictError,
        _build_conflict_details,
        _compute_etag,
        _serialize_document,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _FakeDocument:
    def __init__(self):
        self.id = 11
        self.project_key = "demo_proj"
        self.title = "Draft"
        self.body_md = "body"
        self.status = "draft"
        self.head_version = 2
        self.etag = "etag-2"
        self.updated_by_user_id = "tester"
        self.updated_at = None
        self.created_at = None
        self.metadata_json = {}


class WritingDocumentServiceUnitTestCase(unittest.TestCase):
    def setUp(self):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"writing document service tests require backend dependencies: {_IMPORT_ERROR}")

    def test_compute_etag_changes_with_version(self):
        first = _compute_etag(body_md="body", version=1)
        second = _compute_etag(body_md="body", version=2)
        self.assertNotEqual(first, second)

    def test_build_conflict_details(self):
        details = _build_conflict_details(_FakeDocument(), expected_version=1)
        self.assertEqual(details["conflict_code"], "VERSION_CONFLICT")
        self.assertEqual(details["expected_version"], 1)
        self.assertEqual(details["current_version"], 2)

    def test_version_conflict_error_carries_snapshot(self):
        exc = WritingVersionConflictError(expected_version=1, current_version=2, server_snapshot={"conflict_code": "VERSION_CONFLICT"})
        self.assertEqual(exc.expected_version, 1)
        self.assertEqual(exc.current_version, 2)
        self.assertEqual(exc.server_snapshot["conflict_code"], "VERSION_CONFLICT")

    def test_serialize_document_uses_view_shape(self):
        serialized = _serialize_document(_FakeDocument())
        self.assertEqual(serialized["id"], 11)
        self.assertEqual(serialized["version"], 2)
        self.assertEqual(serialized["etag"], "etag-2")


if __name__ == "__main__":
    unittest.main()
