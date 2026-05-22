from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.document_views import (  # noqa: E402
    CONSUMER_FACADE_CONTRACT_VERSION,
    get_consumer_boundary_snapshot,
    get_document_source_label,
    get_social_identity,
    has_structured_data,
)
from app.services.graph.adapters.market import MarketAdapter  # noqa: E402
from app.services.graph.adapters.policy import PolicyAdapter  # noqa: E402
from app.services.graph.adapters.reddit import RedditAdapter  # noqa: E402
from app.services.writing import search_suggest_service  # noqa: E402
from scripts.check_consumer_side_facade_contract import build_check  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[4]


class ConsumerSideFacadeContractUnitTestCase(unittest.TestCase):
    def test_consumer_boundary_facade_normalizes_structured_read_fields(self) -> None:
        doc = SimpleNamespace(
            extracted_data={
                "platform": " reddit ",
                "source": "fallback-source",
                "username": " user_1 ",
                "subreddit": " robotics ",
            }
        )

        self.assertTrue(has_structured_data(doc))
        self.assertEqual(get_document_source_label(doc), "reddit")
        self.assertEqual(
            get_social_identity(doc),
            {"username": "user_1", "subreddit": "robotics"},
        )

    def test_consumer_boundary_snapshot_records_worker5_scope(self) -> None:
        snapshot = get_consumer_boundary_snapshot()

        self.assertEqual(snapshot["contract_version"], CONSUMER_FACADE_CONTRACT_VERSION)
        self.assertEqual(snapshot["worker4_boundary"], "does_not_modify_document_queries_core")
        self.assertIn("graph.adapters_python_read_boundary", snapshot["worker5_scope"])

    def test_writing_suggest_material_items_use_document_query_boundary(self) -> None:
        with patch(
            "app.services.writing.search_suggest_service.query_source_library_material_rows",
            return_value=[
                {
                    "item_key": "robotics_feed",
                    "name": "Robotics Feed",
                    "description": "robotics market source",
                    "channel_key": "market",
                }
            ],
        ) as mocked_query:
            items = search_suggest_service._material_items("demo_proj", "robotics", 10)

        mocked_query.assert_called_once_with("demo_proj", query="robotics")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "material")
        self.assertEqual(items[0].extra["channel_key"], "market")

    def test_graph_adapters_keep_structured_values_through_consumer_facade(self) -> None:
        reddit_doc = SimpleNamespace(
            id=1,
            uri="https://example.com/r",
            publish_date=None,
            created_at=None,
            state="CA",
            extracted_data={
                "platform": "reddit",
                "text": "Robotics policy discussion",
                "username": "policy_user",
                "subreddit": "robotics",
                "keywords": ["robotics"],
                "sentiment": {"sentiment_orientation": "positive", "topic": "automation"},
                "entities_relations": {"entities": [{"text": "robotics", "type": "topic"}]},
            },
        )
        reddit = RedditAdapter().to_normalized(reddit_doc)

        self.assertIsNotNone(reddit)
        self.assertEqual(reddit.username, "policy_user")
        self.assertEqual(reddit.subreddit, "robotics")
        self.assertEqual(reddit.entities[0]["text"], "robotics")

        market_doc = SimpleNamespace(
            id=2,
            uri="https://example.com/m",
            title="Market report",
            publish_date=None,
            state="NY",
            extracted_data={
                "platform": "market_feed",
                "market": {"state": "NY", "game": "lotto", "sales_volume": 10},
            },
        )
        market = MarketAdapter().to_normalized(market_doc)

        self.assertIsNotNone(market)
        self.assertEqual(market.source_name, "market_feed")
        self.assertEqual(market.state, "NY")
        self.assertEqual(market.game, "lotto")

        policy_doc = SimpleNamespace(
            id=3,
            title="Policy",
            status="active",
            doc_type="policy",
            uri="https://example.com/p",
            publish_date=None,
            state="WA",
            summary=None,
            extracted_data={
                "policy": {"state": "WA", "policy_type": "regulation", "key_points": ["point"]},
                "entities_relations": {"entities": [{"text": "agency"}], "relations": [{"type": "issued_by"}]},
            },
        )
        policy = PolicyAdapter().to_normalized(policy_doc)

        self.assertIsNotNone(policy)
        self.assertEqual(policy.state, "WA")
        self.assertEqual(policy.policy_type, "regulation")
        self.assertEqual(policy.key_points, ["point"])
        self.assertEqual(policy.entities[0]["text"], "agency")

    def test_checker_passes_for_worker5_consumer_surfaces(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONSUMER_FACADE_CONTRACT_VERSION)
        self.assertEqual(result["topic_id"], "2026-03-14-consumer-side-modularization")
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["validation"]["passed"])
        self.assertEqual(result["validation"]["direct_extracted_data_read_count"], 0)
        self.assertIn(
            "main/backend/app/services/stats/prompt_time_density.py",
            result["validation"]["extracted_query_surfaces"],
        )
        self.assertNotIn(
            "main/backend/app/services/stats/prompt_time_density.py",
            result["validation"]["deferred_query_surfaces"],
        )

        surfaces = {item["path"]: item for item in result["surfaces"]}
        self.assertFalse(
            surfaces["main/backend/app/services/writing/search_suggest_service.py"]["prohibited_query_bypass_imports"]
        )
        for item in surfaces.values():
            self.assertTrue(item["passed"], item)


if __name__ == "__main__":
    unittest.main()
