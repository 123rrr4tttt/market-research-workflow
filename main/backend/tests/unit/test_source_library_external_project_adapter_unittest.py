from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.source_library.adapters.external_project import handle_external_project_manifest


def _build_manifest(*, execution_mode: str = "rss_feed") -> dict[str, object]:
    manifest: dict[str, object] = {
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
        "execution_mode": execution_mode,
        "runner_ref": "https://example.com/feed.xml" if execution_mode != "http_api" else "https://api.example.com/search",
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
    if execution_mode == "http_api":
        manifest["runtime_config"] = {
            "method": "GET",
            "query_param_map": {"query_terms": "q", "max_items": "limit"},
            "records_path": "items",
            "record_mapping": {
                "url": "url",
                "title": "title",
                "summary": "summary",
                "artifact_url": "pdf_url",
            },
        }
    return manifest


class ExternalProjectAdapterUnitTestCase(unittest.TestCase):
    def test_rss_feed_manifest_returns_materialized_records(self) -> None:
        params = {
            "_source_library_item": {
                "item_key": "external.demo.item",
                "name": "External Demo Item",
                "extra": {"external_project_manifest": _build_manifest()},
            },
            "query_terms": ["fintech"],
            "max_items": 2,
        }

        with patch("app.services.source_library.adapters.external_project.execute_feed_probe") as execute:
            execute.return_value = SimpleNamespace(
                selected_candidates=[
                    SimpleNamespace(url="https://example.com/posts/1", title="Fintech One", text="Summary one"),
                    SimpleNamespace(url="https://example.com/posts/2", title="Fintech Two", text="Summary two"),
                ],
                used_term_fallback=False,
                pages_scanned=1,
                diagnostics={"raw_candidates": 2},
                errors=[],
            )
            result = handle_external_project_manifest(params, project_key="demo_proj")

        execute.assert_called_once()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["provider"], "external_project")
        self.assertEqual(result["execution_mode"], "rss_feed")
        self.assertEqual(result["provider_binding"]["provider_key"], "external_project.rss_feed")
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["records"][0]["title"], "Fintech One")
        self.assertEqual(result["records"][0]["record_meta"]["external_project"]["project_link"], "https://github.com/example/external-demo")

    def test_http_api_manifest_maps_artifacts_into_record_meta(self) -> None:
        params = {
            "_source_library_item": {
                "item_key": "external.demo.item",
                "name": "External Demo Item",
                "extra": {"external_project_manifest": _build_manifest(execution_mode="http_api")},
            },
            "query_terms": ["robotics"],
            "max_items": 1,
        }

        with patch("app.services.source_library.adapters.external_project.default_http_client.get_json") as get_json:
            get_json.return_value = {
                "items": [
                    {
                        "url": "https://example.com/posts/api-1",
                        "title": "API Record",
                        "summary": "API summary",
                        "pdf_url": "https://example.com/posts/api-1.pdf",
                    }
                ]
            }
            result = handle_external_project_manifest(params, project_key=None)

        get_json.assert_called_once()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["execution_mode"], "http_api")
        self.assertEqual(result["provider_binding"]["provider_key"], "external_project.http_api")
        self.assertEqual(result["records"][0]["url"], "https://example.com/posts/api-1")
        self.assertEqual(
            result["records"][0]["record_meta"]["artifact_ref"]["source_locator"],
            "https://example.com/posts/api-1.pdf",
        )


if __name__ == "__main__":
    unittest.main()
