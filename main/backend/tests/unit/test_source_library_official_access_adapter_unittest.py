from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.source_library.adapters.official_access import handle_official_access_api


class OfficialAccessAdapterUnitTestCase(unittest.TestCase):
    def setUp(self) -> None:
        arxiv_patcher = patch("app.services.source_library.adapters.official_access._ARXIV_RESULT_CACHE", {})
        crossref_patcher = patch("app.services.source_library.adapters.official_access._CROSSREF_RESULT_CACHE", {})
        self.addCleanup(arxiv_patcher.stop)
        self.addCleanup(crossref_patcher.stop)
        arxiv_patcher.start()
        crossref_patcher.start()

    def test_arxiv_official_api_returns_candidate_urls(self) -> None:
        with patch("app.services.source_library.adapters.official_access.execute_feed_probe") as execute:
            execute.return_value = SimpleNamespace(
                selected_candidates=[
                    SimpleNamespace(url="https://arxiv.org/abs/2501.00001"),
                    SimpleNamespace(url="https://arxiv.org/abs/2501.00002"),
                ],
                used_term_fallback=False,
                pages_scanned=1,
                diagnostics={"selected_candidates": 2},
                errors=[],
            )
            result = handle_official_access_api(
                {
                    "provider_key": "arxiv",
                    "query_terms": ["graph neural networks", "reasoning"],
                    "max_results": 5,
                },
                project_key=None,
            )

        execute.assert_called_once()
        self.assertEqual(
            result["candidates"],
            [
                "https://arxiv.org/abs/2501.00001",
                "https://arxiv.org/abs/2501.00002",
            ],
        )
        self.assertEqual(result["diagnostics"]["provider_key"], "arxiv")
        self.assertIn("search_query=all:graph+neural+networks+AND+all:reasoning", result["diagnostics"]["feed_url"])

    def test_arxiv_official_api_falls_back_to_raw_feed_candidates(self) -> None:
        with patch("app.services.source_library.adapters.official_access.execute_feed_probe") as execute:
            execute.return_value = SimpleNamespace(
                raw_candidates=[
                    SimpleNamespace(url="https://arxiv.org/abs/2501.00003"),
                    SimpleNamespace(url="https://arxiv.org/abs/2501.00004"),
                ],
                selected_candidates=[],
                used_term_fallback=True,
                pages_scanned=1,
                diagnostics={"selected_candidates": 0, "raw_candidates": 2},
                errors=[],
            )
            result = handle_official_access_api(
                {
                    "provider_key": "arxiv",
                    "query_terms": ["openai api pricing"],
                    "max_results": 5,
                },
                project_key=None,
            )

        self.assertEqual(
            result["candidates"],
            [
                "https://arxiv.org/abs/2501.00003",
                "https://arxiv.org/abs/2501.00004",
            ],
        )
        self.assertEqual(result["diagnostics"]["selection_mode"], "raw_feed_candidates")

    def test_arxiv_official_api_falls_back_to_html_search_when_feed_fails(self) -> None:
        html = """
        <html>
          <body>
            <ol>
              <li class="arxiv-result">
                <p class="title is-5 mathjax">
                  <a href="https://arxiv.org/abs/2501.00009">Paper One</a>
                </p>
              </li>
              <li class="arxiv-result">
                <p class="title is-5 mathjax">
                  <a href="https://arxiv.org/abs/2501.00010">Paper Two</a>
                </p>
              </li>
            </ol>
          </body>
        </html>
        """
        with (
            patch("app.services.source_library.adapters.official_access.execute_feed_probe") as execute,
            patch(
                "app.services.source_library.adapters.official_access.fetch_html",
                return_value=(html, SimpleNamespace(status_code=200)),
            ),
        ):
            execute.return_value = SimpleNamespace(
                raw_candidates=[],
                selected_candidates=[],
                used_term_fallback=False,
                pages_scanned=1,
                diagnostics={"selected_candidates": 0, "raw_candidates": 0},
                errors=[{"error": "Failed to fetch https://export.arxiv.org/api/query?...", "error_class": "transport_failure"}],
            )
            result = handle_official_access_api(
                {
                    "provider_key": "arxiv",
                    "query_terms": ["openai api pricing"],
                    "max_results": 5,
                },
                project_key=None,
            )

        self.assertEqual(
            result["candidates"],
            [
                "https://arxiv.org/abs/2501.00009",
                "https://arxiv.org/abs/2501.00010",
            ],
        )
        self.assertEqual(result["diagnostics"]["fallback_mode"], "html_search")
        self.assertTrue(result["diagnostics"]["api_probe_failed"])

    def test_arxiv_official_api_reuses_cached_candidates_after_rate_limit(self) -> None:
        with patch("app.services.source_library.adapters.official_access.execute_feed_probe") as execute:
            execute.return_value = SimpleNamespace(
                raw_candidates=[SimpleNamespace(url="https://arxiv.org/abs/2501.00011")],
                selected_candidates=[],
                used_term_fallback=False,
                pages_scanned=1,
                diagnostics={"selected_candidates": 0, "raw_candidates": 1},
                errors=[],
            )
            first = handle_official_access_api(
                {
                    "provider_key": "arxiv",
                    "query_terms": ["openai api pricing"],
                    "max_results": 5,
                },
                project_key=None,
            )

        self.assertEqual(first["candidates"], ["https://arxiv.org/abs/2501.00011"])

        with patch("app.services.source_library.adapters.official_access.execute_feed_probe") as execute:
            execute.return_value = SimpleNamespace(
                raw_candidates=[],
                selected_candidates=[],
                used_term_fallback=False,
                pages_scanned=1,
                diagnostics={"selected_candidates": 0, "raw_candidates": 0},
                errors=[{"error": "429 Client Error", "error_class": "transport_failure"}],
            )
            second = handle_official_access_api(
                {
                    "provider_key": "arxiv",
                    "query_terms": ["openai api pricing"],
                    "max_results": 5,
                },
                project_key=None,
            )

        execute.assert_not_called()
        self.assertEqual(second["candidates"], ["https://arxiv.org/abs/2501.00011"])
        self.assertTrue(second["diagnostics"]["cache_hit"])

    def test_unknown_provider_stays_placeholder(self) -> None:
        result = handle_official_access_api({"provider_key": "unknown"}, project_key=None)
        self.assertEqual(result["candidates"], [])
        self.assertIn("placeholder", result["message"])

    def test_crossref_official_api_returns_doi_candidate_urls(self) -> None:
        payload = {
            "message": {
                "total-results": 2,
                "items": [
                    {
                        "DOI": "10.5555/example-1",
                        "URL": "https://doi.org/10.5555/example-1",
                        "title": ["Robotics Market Evidence"],
                        "publisher": "Example Publisher",
                        "type": "journal-article",
                    },
                    {
                        "DOI": "10.5555/example-2",
                        "title": ["Automation Adoption Evidence"],
                    },
                ],
            }
        }
        with patch("app.services.source_library.adapters.official_access.default_http_client.get_json") as get_json:
            get_json.return_value = payload
            result = handle_official_access_api(
                {
                    "provider_key": "crossref",
                    "query_terms": ["robotics market"],
                    "max_results": 5,
                },
                project_key=None,
            )

        get_json.assert_called_once()
        self.assertEqual(
            result["candidates"],
            [
                "https://doi.org/10.5555/example-1",
                "https://doi.org/10.5555/example-2",
            ],
        )
        self.assertEqual(result["diagnostics"]["provider_key"], "crossref")
        self.assertEqual(result["diagnostics"]["endpoint"], "https://api.crossref.org/works")
        self.assertFalse(result["diagnostics"]["credential_required"])
        self.assertTrue(result["diagnostics"]["public_api"])
        self.assertEqual(result["candidate_records"][0]["title"], "Robotics Market Evidence")

    def test_crossref_official_api_reuses_cached_candidates(self) -> None:
        payload = {
            "message": {
                "total-results": 1,
                "items": [{"DOI": "10.5555/cached", "title": ["Cached Record"]}],
            }
        }
        with patch("app.services.source_library.adapters.official_access.default_http_client.get_json") as get_json:
            get_json.return_value = payload
            first = handle_official_access_api(
                {"provider_key": "crossref", "query_terms": ["robotics market"], "max_results": 2},
                project_key=None,
            )
        self.assertEqual(first["candidates"], ["https://doi.org/10.5555/cached"])

        with patch("app.services.source_library.adapters.official_access.default_http_client.get_json") as get_json:
            second = handle_official_access_api(
                {"provider_key": "crossref", "query_terms": ["robotics market"], "max_results": 2},
                project_key=None,
            )

        get_json.assert_not_called()
        self.assertEqual(second["candidates"], ["https://doi.org/10.5555/cached"])
        self.assertTrue(second["diagnostics"]["cache_hit"])

    def test_crossref_official_api_reports_transport_failure(self) -> None:
        with patch("app.services.source_library.adapters.official_access.default_http_client.get_json") as get_json:
            get_json.side_effect = RuntimeError("crossref unavailable")
            result = handle_official_access_api(
                {"provider_key": "crossref", "query_terms": ["robotics market"], "max_results": 2},
                project_key=None,
            )

        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["diagnostics"]["provider_key"], "crossref")
        self.assertFalse(result["diagnostics"]["credential_required"])
        self.assertEqual(result["errors"][0]["error_class"], "transport_failure")


if __name__ == "__main__":
    unittest.main()
