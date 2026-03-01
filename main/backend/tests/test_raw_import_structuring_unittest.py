from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from app.services.ingest.raw_import import (
        _build_structured_summary,
        _derive_publish_date_from_extracted,
        _resolve_extraction_flags,
    )
    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class RawImportStructuringTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"raw import structuring tests require backend dependencies: {_IMPORT_ERROR}")

    def test_auto_mode_uses_comprehensive_for_raw_note(self):
        flags = _resolve_extraction_flags("auto", "raw_note")
        self.assertEqual(flags["mode"], "comprehensive")
        self.assertTrue(flags["include_policy"])
        self.assertTrue(flags["include_market"])
        self.assertTrue(flags["include_sentiment"])
        self.assertTrue(flags["include_company"])
        self.assertTrue(flags["include_product"])
        self.assertTrue(flags["include_operation"])

    def test_auto_mode_keeps_market_specific_profile(self):
        flags = _resolve_extraction_flags("auto", "market_info")
        self.assertEqual(flags["mode"], "market")
        self.assertFalse(flags["include_policy"])
        self.assertTrue(flags["include_market"])
        self.assertFalse(flags["include_sentiment"])
        self.assertTrue(flags["include_company"])
        self.assertTrue(flags["include_product"])
        self.assertTrue(flags["include_operation"])

    def test_build_structured_summary_counts_entities_relations(self):
        summary = _build_structured_summary(
            {
                "entities_relations": {
                    "entities": [{"text": "A", "type": "ORG"}, {"text": "B", "type": "LOC"}],
                    "relations": [{"subject": "A", "predicate": "affects", "object": "B"}],
                },
                "policy": {"state": "CA"},
                "company_structured": {"company_name": "ACME"},
            },
            extraction_enabled=True,
            chunks_used=3,
            extraction_mode="comprehensive",
        )
        self.assertEqual(summary["entity_count"], 2)
        self.assertEqual(summary["relation_count"], 1)
        self.assertTrue(summary["has_policy"])
        self.assertTrue(summary["has_company"])
        self.assertEqual(summary["chunks_used"], 3)
        self.assertEqual(summary["extraction_mode"], "comprehensive")

    def test_derive_publish_date_from_extracted_prefers_policy_effective_date(self):
        derived = _derive_publish_date_from_extracted(
            {
                "policy": {"effective_date": "2026-02-01"},
                "market": {"report_date": "2026-01-31"},
            }
        )
        self.assertIsNotNone(derived)
        self.assertEqual(str(derived), "2026-02-01")


if __name__ == "__main__":
    unittest.main()
