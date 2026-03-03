from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.indexer.policy import (
        _build_vector_contract_payload,
        _validate_vector_contract_payload,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class PolicyIndexerVectorContractUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"policy indexer vector contract tests require backend dependencies: {_IMPORT_ERROR}")

    def test_build_vector_contract_payload_derives_required_fields(self):
        doc = SimpleNamespace(
            id=42,
            uri="https://example.org/policy/42",
            publish_date=None,
            created_at=datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc),
            extracted_data={"project_key": "demo_proj", "language": "en"},
        )
        payload = _build_vector_contract_payload(doc, "  clean text body  ")

        self.assertEqual(payload["project_key"], "demo_proj")
        self.assertEqual(payload["object_id"], 42)
        self.assertEqual(payload["object_type"], "policy_chunk")
        self.assertEqual(payload["language"], "en")
        self.assertEqual(payload["source_domain"], "example.org")
        self.assertEqual(payload["clean_text"], "clean text body")
        self.assertTrue(payload["keep_for_vectorization"])
        _validate_vector_contract_payload(payload)

    def test_validate_vector_contract_payload_rejects_missing_fields(self):
        payload = {
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": 1,
            "vector_version": "v1",
            "clean_text": "abc",
            "language": "en",
            "source_domain": None,
            "effective_time": None,
            "keep_for_vectorization": True,
        }

        with self.assertRaisesRegex(ValueError, "vector_contract_missing_fields"):
            _validate_vector_contract_payload(payload)

    def test_validate_vector_contract_payload_rejects_non_vectorizable_flag(self):
        payload = {
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": 1,
            "vector_version": "v1",
            "clean_text": "abc",
            "language": "en",
            "source_domain": "example.org",
            "effective_time": "2026-03-03T10:00:00+00:00",
            "keep_for_vectorization": False,
        }

        with self.assertRaisesRegex(ValueError, "vector_contract_keep_for_vectorization_false"):
            _validate_vector_contract_payload(payload)


if __name__ == "__main__":
    unittest.main()
