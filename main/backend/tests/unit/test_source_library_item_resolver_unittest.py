from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.source_library.item_resolver import ItemResolver, execution_request_to_dict, normalize_item_taxonomy
from app.services.source_library.types import FrontDoorExecutionProtocol


def _build_protocol(*, item, params, project_key):
    return FrontDoorExecutionProtocol(
        item_key=str(item.get("item_key") or ""),
        item_channel_key=str(item.get("channel_key") or ""),
        project_key=project_key,
        front_door_owner="test",
        execution_mode="url_routing" if params.get("urls") else "single_channel",
        write_mode="front_door_url_routing" if params.get("urls") else "channel_direct",
        route_decision="test",
        query_terms=list(params.get("query_terms") or []),
        site_entries=list(params.get("site_entries") or []),
        candidate_urls=list(params.get("urls") or []),
        expected_entry_type=None,
        write_to_pool=True,
        auto_ingest=False,
        ingest_limit=10,
        force_url_routing_flow=False,
        prefer_crawler_first=False,
        search_parallelism=1,
        routing_parallelism=1,
        concurrency_plan={"batch_size": 1, "shared_budget": 1, "search": {}, "url": {}},
        source_tier="",
        onboarding_priority="",
    )


class SourceLibraryItemResolverUnitTestCase(unittest.TestCase):
    def test_resolve_url_execution_when_urls_present(self) -> None:
        item = {"item_key": "report.urls", "channel_key": "market.default"}
        request = ItemResolver.resolve(
            item=item,
            params={"urls": ["https://example.com/a"]},
            project_key="demo_proj",
            channel_map={"market.default": {"channel_key": "market.default", "provider_type": "native"}},
            build_frontdoor_protocol=_build_protocol,
            is_handler_cluster_item=lambda _item: False,
            has_site_entries=lambda params: bool(params.get("site_entries")),
        )
        self.assertEqual(request.source_mode, "url_execution")

    def test_resolve_provider_harvest_for_crawler_channel(self) -> None:
        item = {"item_key": "crawler.item", "channel_key": "crawler.demo_proj"}
        request = ItemResolver.resolve(
            item=item,
            params={},
            project_key="demo_proj",
            channel_map={"crawler.demo_proj": {"channel_key": "crawler.demo_proj", "provider_type": "scrapy"}},
            build_frontdoor_protocol=_build_protocol,
            is_handler_cluster_item=lambda _item: False,
            has_site_entries=lambda params: bool(params.get("site_entries")),
        )
        self.assertEqual(request.source_mode, "provider_harvest")

    def test_generic_web_internal_adapter_is_promoted_to_site_search_taxonomy(self) -> None:
        item = {"item_key": "generic.internal.search", "channel_key": "generic_web.search_template"}
        request = ItemResolver.resolve(
            item=item,
            params={"query_terms": ["robotics"], "template": "https://example.com/search?q={{q}}"},
            project_key="demo_proj",
            channel_map={
                "generic_web.search_template": {
                    "channel_key": "generic_web.search_template",
                    "provider": "generic_web",
                    "provider_type": "native",
                }
            },
            build_frontdoor_protocol=_build_protocol,
            is_handler_cluster_item=lambda _item: False,
            has_site_entries=lambda params: bool(params.get("site_entries")),
        )
        self.assertEqual(request.source_mode, "site_search")
        self.assertEqual(request.taxonomy["channel_family"], "generic_web")
        self.assertTrue(request.taxonomy["internal_adapter_only"])
        self.assertIn("generic_web_internal_adapter_detected", request.warnings)

    def test_normalize_item_taxonomy_marks_handler_cluster_as_service_aggregated(self) -> None:
        item = normalize_item_taxonomy(
            {
                "item_key": "handler.cluster.search_template",
                "channel_key": "handler.cluster",
                "extra": {"stable_handler_cluster": True},
            }
        )
        self.assertEqual(item["item_type"], "service_aggregated")
        self.assertEqual(item["managed_by"], "system")

    def test_execution_request_dict_contains_taxonomy_snapshot(self) -> None:
        item = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "handler.cluster",
            "extra": {"stable_handler_cluster": True, "expected_entry_type": "search_template"},
        }
        request = ItemResolver.resolve(
            item=item,
            params={"query_terms": ["robotics"], "site_entries": ["https://example.com/search?q={{q}}"]},
            project_key="demo_proj",
            channel_map={"handler.cluster": {"channel_key": "handler.cluster", "provider_type": "native"}},
            build_frontdoor_protocol=_build_protocol,
            is_handler_cluster_item=lambda _item: True,
            has_site_entries=lambda params: bool(params.get("site_entries")),
        )

        dto = execution_request_to_dict(request)
        self.assertEqual(dto["taxonomy"]["channel_family"], "handler_cluster")
        self.assertEqual(dto["taxonomy"]["item_type"], "service_aggregated")
        self.assertEqual(dto["taxonomy"]["managed_by"], "system")


if __name__ == "__main__":
    unittest.main()
