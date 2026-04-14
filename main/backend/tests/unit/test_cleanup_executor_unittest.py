from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.ingest.cleanup_executor import execute_frontdoor_cleanup


class CleanupExecutorUnitTestCase(unittest.TestCase):
    def test_execute_frontdoor_cleanup_refetches_and_reextracts(self) -> None:
        html = """
        <html><body>
        <main>
          <article>
            <h1>Market review</h1>
            <p>Published January 2, 2026.</p>
            <p>The company expanded manufacturing capacity and improved retention.</p>
          </article>
        </main>
        </body></html>
        """
        with patch(
            "app.services.ingest.cleanup_executor.fetch_html",
            return_value=(html, type("Resp", (), {"status_code": 200})()),
        ):
            result = execute_frontdoor_cleanup(
                document_candidate={
                    "uri": "https://example.com/article-shell",
                    "title": "Support shell",
                    "content": "Support menu Login Subscribe Cookie Settings",
                },
                terminal_context={},
                cleanup_actions=["strip_boilerplate", "refetch_suggested"],
            )
        self.assertTrue(result["executed"])
        self.assertTrue(result["recovered"])
        self.assertIn("Published January 2, 2026.", result["document_candidate"]["content"])
        self.assertEqual(result["content_extraction"]["page_family"], "article")


if __name__ == "__main__":
    unittest.main()
