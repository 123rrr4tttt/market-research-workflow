from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

try:
    from fastapi.testclient import TestClient
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class IngestResponseContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"ingest response contract tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)

    def test_single_url_sync_contract_includes_stable_business_fields(self):
        fake_result = {
            "status": "degraded_success",
            "inserted": 0,
            "inserted_valid": 0,
            "skipped": 1,
            "rejected_count": 1,
            "rejection_breakdown": {"content_gate_rejected": 1},
            "degradation_flags": ["content_gate_rejected:content_gate_rejected"],
            "document_id": None,
            "quality_score": 0.0,
            "source_domain": "example.com",
            "source_time": None,
            "ingested_at": "2026-03-03T10:00:00+00:00",
            "effective_time": "2026-03-03T10:00:00+00:00",
            "time_confidence": 0.0,
            "time_provenance": "fallback_ingested_at",
            "time_parse_version": "st_v1",
        }

        with patch("app.services.ingest.single_url.ingest_single_url", return_value=fake_result):
            resp = self.client.post(
                "/api/v1/ingest/url/single",
                json={
                    "url": "https://example.com/post/1",
                    "project_key": "demo_proj",
                    "async_mode": False,
                    "strict_mode": False,
                },
                headers={"X-Project-Key": "demo_proj"},
            )

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")
        data = body.get("data") or {}

        # frozen business result fields for platformized ingest outputs
        self.assertIn("status", data)
        self.assertIn("extraction_status", data)
        self.assertIn("structured_extraction_status", data)
        self.assertIn("inserted_valid", data)
        self.assertIn("rejected_count", data)
        self.assertIn("rejection_breakdown", data)
        self.assertIn("degradation_flags", data)
        self.assertIn("source_domain", data)
        self.assertIn("source_time", data)
        self.assertIn("ingested_at", data)
        self.assertIn("effective_time", data)
        self.assertIn("time_confidence", data)
        self.assertIn("time_provenance", data)
        self.assertIn("time_parse_version", data)

        self.assertIn(data.get("extraction_status"), {"success", "degraded", "failed"})
        self.assertIsInstance(data.get("rejection_breakdown"), dict)
        self.assertIsInstance(data.get("degradation_flags"), list)


if __name__ == "__main__":
    unittest.main()
