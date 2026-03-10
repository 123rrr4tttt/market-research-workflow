from __future__ import annotations

import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest.source_search_contract import (
        build_query_url_from_contract,
        normalize_source_search_contract,
    )
    from app.services.ingest import url_pool as url_pool_module

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class IngestSourceSearchContractUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"ingest source search contract unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_normalize_source_search_contract_defaults_from_template(self):
        contract = normalize_source_search_contract("https://example.com/search?q={{q}}&page={{page}}", None)
        self.assertIsNotNone(contract)
        self.assertEqual(contract.get("param_key"), "q")
        self.assertEqual(int(contract.get("page") or 0), 1)
        self.assertEqual(int(contract.get("min_results_required") or 0), 6)
        self.assertEqual(int(contract.get("max_candidates") or 0), 6)

    def test_build_query_url_from_contract_supports_template_fields(self):
        url = build_query_url_from_contract(
            "https://example.com/search?q={{q}}&page={{page}}",
            ["robotics market"],
            {
                "param_key": "query",
                "encoding": "plus",
                "lang": "en",
                "region": "us",
                "page": 2,
                "page_size": 50,
                "sort": "recent",
            },
        )
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        self.assertEqual(qs.get("q"), ["robotics market"])
        self.assertEqual(qs.get("page"), ["2"])
        self.assertEqual(qs.get("lang"), ["en"])
        self.assertEqual(qs.get("region"), ["us"])
        self.assertEqual(qs.get("page_size"), ["50"])
        self.assertEqual(qs.get("sort"), ["recent"])

    def test_url_pool_search_options_keeps_legacy_defaults_without_contract(self):
        options = url_pool_module._search_options_for_target("https://example.com/search?q=robotics", ["robotics"])
        self.assertIsNotNone(options)
        self.assertEqual(int(options.get("target_candidates") or 0), 6)
        self.assertEqual(int(options.get("min_results_required") or 0), 6)

    def test_url_pool_contract_applies_to_target_url_and_search_options(self):
        extra_params = {
            "param_key": "query",
            "encoding": "plus",
            "lang": "en",
            "region": "us",
            "page": 3,
            "page_size": 30,
            "sort": "recent",
            "min_results_required": 4,
            "max_candidates": 12,
        }
        target = {"url": "https://example.com/search"}

        resolved = url_pool_module._resolve_target_url(target, ["AI trend"], extra_params=extra_params)
        parsed = urlparse(resolved)
        qs = parse_qs(parsed.query)
        self.assertEqual(qs.get("query"), ["AI trend"])
        self.assertEqual(qs.get("lang"), ["en"])
        self.assertEqual(qs.get("region"), ["us"])
        self.assertEqual(qs.get("page"), ["3"])
        self.assertEqual(qs.get("page_size"), ["30"])
        self.assertEqual(qs.get("sort"), ["recent"])

        options = url_pool_module._search_options_for_target(
            resolved,
            ["AI trend"],
            target=target,
            extra_params=extra_params,
        )
        self.assertEqual(int(options.get("min_results_required") or 0), 4)
        self.assertEqual(int(options.get("target_candidates") or 0), 12)
        self.assertEqual(int(options.get("max_candidates") or 0), 12)


if __name__ == "__main__":
    unittest.main()
