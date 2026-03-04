from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.aggregator.noun_density import (
    NOUN_DENSITY_VERSION,
    build_collection_window_priority,
    build_source_noun_density,
    extract_noun_groups,
)


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalarResult(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _stmt):
        return _FakeExecuteResult(self._rows)


def _fake_doc(
    *,
    doc_id: int,
    source_domain: str,
    effective_time: datetime,
    extracted_data: dict,
    text_hash: str | None = None,
):
    return SimpleNamespace(
        id=doc_id,
        source_domain=source_domain,
        source_time=None,
        effective_time=effective_time,
        created_at=effective_time,
        text_hash=text_hash,
        uri=f"https://{source_domain}/doc/{doc_id}",
        doc_type="news",
        title=f"doc-{doc_id}",
        extracted_data=extracted_data,
    )


class NounDensityServiceUnitTest(unittest.TestCase):
    def test_extract_noun_groups_fallback_to_topic_structured(self):
        doc = SimpleNamespace(
            extracted_data={
                "company_structured": {"entities": [{"text": "A", "type": "company"}]},
                "product_structured": {"topics": ["chip"]},
            }
        )

        groups = extract_noun_groups(doc)

        self.assertEqual(groups, ["company", "product"])

    def test_build_source_noun_density_includes_version_and_rank(self):
        now = datetime.now(timezone.utc)
        docs = [
            _fake_doc(
                doc_id=1,
                source_domain="example.com",
                effective_time=now - timedelta(days=2),
                extracted_data={"noun_vector_group_ids": ["supply_chain"]},
                text_hash="h-1",
            ),
            _fake_doc(
                doc_id=2,
                source_domain="example.com",
                effective_time=now - timedelta(days=1),
                extracted_data={"noun_vector_group_ids": ["supply_chain"]},
                text_hash="h-1",
            ),
        ]

        data = build_source_noun_density(
            _FakeSession(docs),
            time_window=None,
            start_time=(now - timedelta(days=7)).isoformat(),
            end_time=now.isoformat(),
            bucket="day",
            source_domains=["example.com"],
            noun_group_ids=["supply_chain"],
            normalize=True,
        )

        self.assertEqual(data["version"], NOUN_DENSITY_VERSION)
        self.assertTrue(data["items"])
        for item in data["items"]:
            self.assertEqual(item["source_domain"], "example.com")
            self.assertEqual(item["noun_group_id"], "supply_chain")
            self.assertIn("collection_priority_score", item)
            self.assertIn("recommended_window_rank", item)

    def test_collection_window_priority_returns_ranked_rows(self):
        now = datetime.now(timezone.utc)
        docs = [
            _fake_doc(
                doc_id=11,
                source_domain="example.com",
                effective_time=now - timedelta(days=1),
                extracted_data={"noun_vector_group_ids": ["pricing"]},
                text_hash="x-1",
            ),
            _fake_doc(
                doc_id=12,
                source_domain="example.com",
                effective_time=now - timedelta(days=5),
                extracted_data={"noun_vector_group_ids": ["pricing"]},
                text_hash="x-2",
            ),
        ]

        data = build_collection_window_priority(
            _FakeSession(docs),
            source_domains=["example.com"],
            noun_group_ids=["pricing"],
            candidate_windows=["7d", "30d"],
            prefer_low_density=True,
            exclude_high_dup=True,
        )

        self.assertEqual(data["version"], NOUN_DENSITY_VERSION)
        self.assertTrue(data["items"])
        ranks = [row["rank"] for row in data["items"]]
        self.assertEqual(sorted(ranks), ranks)


if __name__ == "__main__":
    unittest.main()
