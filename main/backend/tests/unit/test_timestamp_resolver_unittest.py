from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest.timestamp_resolver import resolve_document_temporal_fields

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class TimestampResolverUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"timestamp resolver unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_resolver_prefers_source_time_and_normalizes_utc(self):
        ingested_at = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
        out = resolve_document_temporal_fields(
            source_domain="example.com",
            metadata={"source_time": "2026-03-01T10:00:00-08:00"},
            content_excerpt="",
            ingested_at=ingested_at,
        )
        self.assertEqual(out["source_domain"], "example.com")
        self.assertEqual(out["source_time"].isoformat(), "2026-03-01T18:00:00+00:00")
        self.assertEqual(out["effective_time"].isoformat(), "2026-03-01T18:00:00+00:00")
        self.assertGreaterEqual(float(out["time_confidence"]), 0.9)
        self.assertIn("source_time", str(out["time_provenance"]))

    def test_resolver_falls_back_when_candidate_is_far_future(self):
        ingested_at = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
        out = resolve_document_temporal_fields(
            source_domain="example.com",
            metadata={"source_time": "2036-03-01T10:00:00+00:00"},
            content_excerpt="",
            ingested_at=ingested_at,
        )
        self.assertIsNone(out["source_time"])
        self.assertEqual(out["effective_time"], ingested_at)
        self.assertEqual(out["time_provenance"], "fallback_ingested_at")
        self.assertEqual(float(out["time_confidence"]), 0.0)

    def test_resolver_extracts_date_from_content_excerpt_when_metadata_missing(self):
        ingested_at = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
        out = resolve_document_temporal_fields(
            source_domain="example.com",
            metadata={},
            content_excerpt="Published on 2026-02-20 and updated later.",
            ingested_at=ingested_at,
        )
        self.assertEqual(out["source_time"].isoformat(), "2026-02-20T00:00:00+00:00")
        self.assertEqual(out["effective_time"].isoformat(), "2026-02-20T00:00:00+00:00")
        self.assertEqual(out["time_provenance"], "body_regex_date")


if __name__ == "__main__":
    unittest.main()
