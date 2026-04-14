from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from app.services.collect_runtime.runtime import run_source_library_item_compat

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


def _external_manifest() -> dict[str, object]:
    return {
        "contract_version": "external_item.manifest.v1",
        "item_key": "external.demo.item",
        "display_name": "External Demo Item",
        "project_link": "https://github.com/example/external-demo",
        "source_kind": "feed_aggregator",
        "source_scope": "finance_news",
        "capabilities": {
            "candidate_urls": True,
            "article_metadata": True,
            "article_body": False,
            "pdf_artifact": False,
        },
        "accepted_inputs": {
            "query_terms": True,
            "urls": False,
            "domains": False,
            "date_range": False,
            "max_items": True,
        },
        "execution_mode": "rss_feed",
        "runner_ref": "https://example.com/feed.xml",
        "normalization": {
            "record_kind": "article_metadata",
            "frontdoor_strategy": "records_only_defer",
        },
        "limits": {
            "default_max_items": 20,
            "max_items_cap": 100,
            "request_timeout_ms": 30000,
        },
        "refresh_policy": {
            "manifest_ttl_minutes": 60,
            "probe_ttl_minutes": 1440,
        },
        "provenance": {
            "discovered_by": "manual_registration",
            "source_refs": ["https://github.com/example/external-demo"],
        },
    }


class ExternalProjectCollectRuntimeIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"external project runtime integration requires backend dependencies: {_IMPORT_ERROR}")

    def test_run_source_library_item_compat_preserves_external_manifest_across_frontdoor_bridge(self):
        fake_item = {
            "item_key": "external.demo.item",
            "name": "External Demo Item",
            "channel_key": "external_project.manifest",
            "enabled": True,
            "item_type": "user_defined",
            "managed_by": "user",
            "params": {},
            "extra": {
                "external_project_manifest": _external_manifest(),
            },
        }
        fake_raw = {
            "item_key": "external.demo.item",
            "name": "External Demo Item",
            "channel_key": "external_project.manifest",
            "item_type": "user_defined",
            "managed_by": "user",
            "params": {"query_terms": ["ai"]},
            "extra": {
                "external_project_manifest": _external_manifest(),
            },
            "result": {
                "records": [
                    {
                        "record_id": "r1",
                        "url": "https://example.com/a",
                        "title": "Alpha",
                        "summary": "alpha summary",
                    }
                ],
                "errors": [],
            },
        }

        with (
            patch("app.services.collect_runtime.adapters.source_library.start_job", return_value="job-ext-1"),
            patch("app.services.collect_runtime.adapters.source_library.complete_job"),
            patch("app.services.collect_runtime.adapters.source_library.fail_job"),
            patch("app.services.source_library.resolver.list_effective_items", return_value=[fake_item]),
            patch("app.services.source_library.resolver.list_effective_channels", return_value=[]),
            patch("app.services.source_library.resolver.run_item_payload", return_value=fake_raw),
        ):
            response = run_source_library_item_compat(
                item_key="external.demo.item",
                project_key="demo_proj",
                override_params={"query_terms": ["ai"], "max_items": 1},
            )

        self.assertEqual(response["terminal_output"]["item"]["item_key"], "external.demo.item")
        self.assertEqual(
            response["terminal_output"]["item"]["external_manifest"]["project_link"],
            "https://github.com/example/external-demo",
        )
        self.assertEqual(
            response["terminal_output"]["item"]["external_manifest"]["execution_mode"],
            "rss_feed",
        )
        self.assertEqual(response["frontdoor_ingress"]["source_ref"]["source_kind"], "feed_aggregator")
        self.assertEqual(response["frontdoor_ingress"]["source_ref"]["execution_mode"], "rss_feed")
        self.assertEqual(response["authority_output"]["summary"]["record_stats"]["normalized"], 1)
        self.assertEqual(response["compat_projection"]["status"], "retained_compat")
        self.assertIn(response["postprocess_frontdoor"]["data"]["admission"], {"accept", "defer", "reject"})
        self.assertEqual(len(response["terminal_output"]["results"]["records"]), 1)


if __name__ == "__main__":
    unittest.main()
