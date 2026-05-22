from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.source_library_real_probes import run_probe


class SourceLibraryRealProbeFixtureUnitTestCase(unittest.TestCase):
    def test_local_http_fixture_covers_site_entries_and_transport_fallback(self) -> None:
        result = run_probe(probe_timeout=0.5)

        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertIn("sitemap", result["outputs"]["site_entry_discovery"]["entry_types"])
        self.assertIn("rss", result["outputs"]["site_entry_discovery"]["entry_types"])
        self.assertIn("search_template", result["outputs"]["site_entry_discovery"]["entry_types"])

        search = result["outputs"]["adapter_results"]["search_template"]
        self.assertEqual(search["diagnostics"]["search_service"], "resilient")
        self.assertEqual(search["diagnostics"]["search_service_fallbacks"], 1)
        self.assertEqual(result["outputs"]["transport_resilience"]["blocked_search_attempts"], 2)
        self.assertEqual(search["diagnostics"]["transport_errors"], 0)
        self.assertEqual(search["diagnostics"]["candidate_filter_state"], "selected")
        self.assertEqual(len(search["candidates"]), 1)

        request_counts = result["outputs"]["transport_resilience"]["request_counts"]
        self.assertGreaterEqual(request_counts.get("/sitemap.xml", 0), 1)
        self.assertGreaterEqual(request_counts.get("/feed.xml", 0), 1)
        self.assertGreaterEqual(request_counts.get("/search", 0), 1)
        self.assertEqual(request_counts.get("/blocked-search", 0), 2)


if __name__ == "__main__":
    unittest.main()
