from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.ingest.content_extraction import analyze_frontdoor_content, apply_main_content_extraction


class ContentExtractionUnitTestCase(unittest.TestCase):
    def test_article_like_content_is_classified_and_trimmed(self) -> None:
        content = "\n".join(
            [
                "Home | News | Tech | Reviews | Subscribe",
                "Share | Follow | Newsletter | Terms of Use",
                "AI hardware market review",
                "Published March 10, 2026 by Jane Doe.",
                "The market expanded as vendors focused on enterprise note-taking workflows.",
                "Revenue increased and retention improved in the second half of the year.",
            ]
        )
        analysis = analyze_frontdoor_content(
            uri="https://example.com/articles/ai-hardware-review",
            title="AI hardware market review",
            content=content,
        )
        self.assertEqual(analysis["page_family"], "article")
        self.assertTrue(analysis["prefix_trimmed"])
        self.assertGreater(analysis["main_text_ratio"], 0.35)
        self.assertIn("Published March 10, 2026", analysis["main_content"])
        self.assertNotIn("Home | News", analysis["main_content"])

    def test_video_shell_is_classified_as_video(self) -> None:
        content = "if(a)return a;c.prototype.toString=function(){return this.g}; Symbol.iterator window.document"
        analysis = analyze_frontdoor_content(
            uri="https://www.youtube.com/watch?v=abc123",
            title="Video shell",
            content=content,
        )
        self.assertEqual(analysis["page_family"], "video")
        self.assertTrue(analysis["js_heavy"])

    def test_apply_main_content_extraction_rewrites_content(self) -> None:
        candidate, analysis = apply_main_content_extraction(
            {
                "uri": "https://example.com/report",
                "title": "Market report",
                "content": "\n".join(
                    [
                        "Home | News | Sport | Business",
                        "Published January 2, 2026.",
                        "The company shipped more devices and expanded partnerships.",
                    ]
                ),
            }
        )
        self.assertIn("Published January 2, 2026.", candidate["content"])
        self.assertNotIn("Home | News", candidate["content"])
        self.assertEqual(analysis["page_family"], "article")


if __name__ == "__main__":
    unittest.main()
