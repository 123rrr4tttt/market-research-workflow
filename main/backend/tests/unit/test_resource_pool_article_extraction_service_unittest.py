from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.resource_pool.article_extraction_service import extract_article_content_from_html


class ArticleExtractionServiceUnitTestCase(unittest.TestCase):
    def test_extract_article_content_from_html_falls_back_to_heuristic_extractor(self) -> None:
        html = """
        <html><body>
          <article>
            <h1>OpenAI pricing update</h1>
            <p>OpenAI updated pricing for enterprise customers.</p>
            <p>The change affects API and priority processing.</p>
          </article>
        </body></html>
        """
        with patch("app.services.resource_pool.article_extraction_service.trafilatura", None):
            result = extract_article_content_from_html(
                html=html,
                url="https://example.com/openai-pricing",
                title="OpenAI pricing update",
            )
        self.assertEqual(result.extractor, "heuristic.main_content.v1")
        self.assertIn("OpenAI updated pricing", result.content)


if __name__ == "__main__":
    unittest.main()
