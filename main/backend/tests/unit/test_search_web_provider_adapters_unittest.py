from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import pytest

from app.services.search import web

pytestmark = pytest.mark.unit


def _load_trace_contract_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "search_provider_trace_contract.py"
    )
    spec = importlib.util.spec_from_file_location("search_provider_trace_contract", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load trace contract module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SearchWebProviderAdaptersTest(unittest.TestCase):
    def test_searxng_adapter_normalizes_results_and_keeps_provider_source(self) -> None:
        payload = {
            "results": [
                {
                    "title": "Robotics policy",
                    "url": "https://example.com/page?utm_source=test&keep=1",
                    "content": "Policy snippet",
                    "engine": "bing",
                    "category": "general",
                }
            ]
        }
        with patch("app.services.search.web.generate_keywords", return_value=["robotics policy"]):
            with patch("app.services.search.web.default_http_client.get_json", return_value=payload) as get_json:
                results = web.search_sources(
                    "robotics policy",
                    language="en",
                    max_results=5,
                    provider="searxng",
                    exclude_existing=False,
                )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "searxng")
        self.assertEqual(results[0]["title"], "Robotics policy")
        self.assertEqual(results[0]["snippet"], "Policy snippet")
        self.assertEqual(results[0]["link"], "https://example.com/page?keep=1")
        self.assertEqual(results[0]["provider_route"], "explicit:searxng")
        self.assertEqual(results[0]["provider_family"], "local_open_search")
        self.assertFalse(results[0]["provider_auto_included"])
        self.assertEqual(
            results[0]["backend_trace"],
            {
                "provider": "searxng",
                "provider_route": "explicit:searxng",
                "provider_family": "local_open_search",
                "auto_included": False,
                "pageno": 1,
            },
        )
        self.assertEqual(results[0]["raw"]["engine"], "bing")
        get_json.assert_called_once()
        self.assertTrue(get_json.call_args.args[0].endswith("/search"))
        self.assertEqual(get_json.call_args.kwargs["params"]["format"], "json")

    def test_yacy_adapter_normalizes_channel_items_and_resource_mode(self) -> None:
        payload = {
            "channels": [
                {
                    "items": [
                        {
                            "title": "Local robotics note",
                            "link": "https://example.org/local?utm_medium=x",
                            "description": "Local corpus snippet",
                            "host": "example.org",
                        }
                    ]
                }
            ]
        }
        with patch.dict(os.environ, {"YACY_RESOURCE_MODE": "local"}, clear=False):
            with patch("app.services.search.web.generate_keywords", return_value=["robotics"]):
                with patch("app.services.search.web.default_http_client.get_json", return_value=payload) as get_json:
                    results = web.search_sources(
                        "robotics",
                        language="en",
                        max_results=5,
                        provider="yacy",
                        exclude_existing=False,
                    )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "yacy")
        self.assertEqual(results[0]["title"], "Local robotics note")
        self.assertEqual(results[0]["snippet"], "Local corpus snippet")
        self.assertEqual(results[0]["link"], "https://example.org/local")
        self.assertEqual(results[0]["provider_route"], "explicit:yacy")
        self.assertEqual(results[0]["provider_family"], "local_open_search")
        self.assertFalse(results[0]["provider_auto_included"])
        self.assertEqual(
            results[0]["backend_trace"],
            {
                "provider": "yacy",
                "provider_route": "explicit:yacy",
                "provider_family": "local_open_search",
                "auto_included": False,
                "resource": "local",
            },
        )
        self.assertEqual(results[0]["raw"]["resource"], "local")
        get_json.assert_called_once()
        self.assertTrue(get_json.call_args.args[0].endswith("/yacysearch.json"))
        self.assertEqual(get_json.call_args.kwargs["params"]["resource"], "local")

    def test_auto_provider_does_not_call_experimental_local_providers(self) -> None:
        with patch.dict(os.environ, {"SERPER_API_KEY": "test-serper"}, clear=False):
            with patch("app.services.search.web.generate_keywords", return_value=["robotics"]):
                with patch("app.services.search.web._serper_search", return_value=[{"title": "Serper", "link": "https://serper.example", "snippet": "ok", "source": "serper"}]):
                    with patch("app.services.search.web._searxng_search") as searxng:
                        with patch("app.services.search.web._yacy_search") as yacy:
                            results = web.search_sources(
                                "robotics",
                                language="en",
                                max_results=5,
                                provider="auto",
                                exclude_existing=False,
                            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "serper")
        searxng.assert_not_called()
        yacy.assert_not_called()

    def test_searxng_adapter_paginates_for_larger_limits(self) -> None:
        first_page = {
            "results": [
                {"title": f"Result {idx}", "url": f"https://example.com/{idx}", "content": "First page"}
                for idx in range(1, 11)
            ]
        }
        second_page = {
            "results": [
                {"title": "Result 11", "url": "https://example.com/11", "content": "Second page"}
            ]
        }
        with patch.dict(os.environ, {"SEARXNG_MAX_PAGES": "2"}, clear=False):
            with patch("app.services.search.web.generate_keywords", return_value=["robotics"]):
                with patch("app.services.search.web.default_http_client.get_json", side_effect=[first_page, second_page]) as get_json:
                    results = web.search_sources(
                        "robotics",
                        language="en",
                        max_results=11,
                        provider="searxng",
                        exclude_existing=False,
                    )

        self.assertEqual(len(results), 11)
        self.assertEqual(get_json.call_count, 2)
        self.assertEqual(get_json.call_args_list[0].kwargs["params"]["pageno"], 1)
        self.assertEqual(get_json.call_args_list[1].kwargs["params"]["pageno"], 2)
        self.assertEqual(results[-1]["raw"]["pageno"], 2)
        self.assertEqual(results[-1]["backend_trace"]["pageno"], 2)
        self.assertEqual(results[-1]["provider_route"], "explicit:searxng")

    def test_offline_provider_trace_artifact_contract_matches_adapters(self) -> None:
        module = _load_trace_contract_module()
        artifact = module.build_contract()

        self.assertEqual(artifact["contract_version"], "search-provider-trace-artifacts.v1")
        self.assertEqual(artifact["scope"], "offline_unit_contract_no_containers")
        self.assertEqual(
            artifact["provider_auto_policy"]["excluded_local_open_search_providers"],
            ["searxng", "yacy"],
        )
        self.assertFalse(artifact["auto_route"]["searxng_called"])
        self.assertFalse(artifact["auto_route"]["yacy_called"])
        self.assertFalse(artifact["auto_route"]["local_open_search_called"])
        self.assertNotIn("searxng", artifact["auto_route"]["result_sources"])
        self.assertNotIn("yacy", artifact["auto_route"]["result_sources"])

        for provider in ("searxng", "yacy"):
            result = artifact["explicit_results"][provider]
            expected_route = f"explicit:{provider}"
            self.assertEqual(result["source"], provider)
            self.assertEqual(result["provider_route"], expected_route)
            self.assertEqual(result["provider_family"], "local_open_search")
            self.assertFalse(result["provider_auto_included"])
            self.assertEqual(result["backend_trace"]["provider"], provider)
            self.assertEqual(result["backend_trace"]["provider_route"], expected_route)
            self.assertEqual(result["backend_trace"]["provider_family"], "local_open_search")
            self.assertFalse(result["backend_trace"]["auto_included"])

        artifact_path = (
            Path(__file__).resolve().parents[4]
            / "development"
            / "latest-dev-docs"
            / "automation-runs"
            / "search-provider-trace-artifacts"
            / "2026-05-22"
            / "search_provider_trace_contract.json"
        )
        if artifact_path.exists():
            self.assertEqual(json.loads(artifact_path.read_text(encoding="utf-8")), artifact)


if __name__ == "__main__":
    unittest.main()
