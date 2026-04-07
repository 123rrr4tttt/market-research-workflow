from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.api import admin as admin_module

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
            doc_type="policy",
            extracted_data={"legacy": {"keep": True}},
        )
        session_factory = _FakeSessionLocal([doc])

        with (
            patch.object(admin_module, "SessionLocal", session_factory),
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
            result = admin_module.re_extract_documents(
                admin_module.ReExtractRequest(doc_ids=[101], force=True, batch_size=10)
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


if __name__ == "__main__":
    unittest.main()
