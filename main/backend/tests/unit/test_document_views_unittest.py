from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.document_views import (
    build_policy_detail,
    build_policy_summary,
    get_market_data,
    get_social_entities,
    get_social_keywords,
)


class DocumentViewsUnitTestCase(unittest.TestCase):
    def test_policy_summary_and_detail_use_compat_fallbacks(self):
        doc = SimpleNamespace(
            id=7,
            title="Policy A",
            state=None,
            status="active",
            publish_date=date(2026, 3, 1),
            created_at=datetime(2026, 3, 2, 10, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 3, 11, 0, tzinfo=timezone.utc),
            summary="",
            uri="https://example.org/policy-a",
            content="body",
            source_id=3,
            extracted_data={
                "summary": "fallback summary",
                "policy": {
                    "state": "CA",
                    "effective_date": "2026-03-15",
                    "policy_type": "notice",
                    "key_points": [" one ", "", 3],
                },
                "entities_relations": {
                    "entities": [{"name": "Lottery", "type": "org"}],
                    "relations": [{"predicate": "applies_to"}],
                },
            },
        )

        summary = build_policy_summary(doc)
        detail = build_policy_detail(doc)

        self.assertEqual(summary["state"], "CA")
        self.assertEqual(summary["summary"], "fallback summary")
        self.assertEqual(summary["key_points"], ["one"])
        self.assertEqual(detail["entities"], [{"name": "Lottery", "type": "org"}])
        self.assertEqual(detail["relations"], [{"predicate": "applies_to"}])

    def test_market_view_builds_fallback_payload(self):
        doc = SimpleNamespace(
            state="TX",
            publish_date=date(2026, 3, 4),
            extracted_data={"keyword": "powerball"},
        )

        market = get_market_data(doc)

        self.assertEqual(market["state"], "TX")
        self.assertEqual(market["game"], "powerball")
        self.assertEqual(market["report_date"], "2026-03-04")

    def test_social_view_falls_back_to_entities_relations_and_key_phrases(self):
        doc = SimpleNamespace(
            extracted_data={
                "sentiment": {"key_phrases": ["jackpot", "", 2]},
                "entities_relations": {"entities": [{"name": "Mega Millions"}]},
            }
        )

        self.assertEqual(get_social_keywords(doc), ["jackpot"])
        self.assertEqual(get_social_entities(doc), [{"name": "Mega Millions"}])


if __name__ == "__main__":
    unittest.main()
