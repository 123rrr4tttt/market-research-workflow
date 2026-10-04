from __future__ import annotations

import sys
import unittest
import hashlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.ingest.content_extraction import analyze_frontdoor_content, apply_main_content_extraction


class ContentExtractionUnitTestCase(unittest.TestCase):
    def test_ingest_html_locators_match_original_fixture_text_and_hash(self) -> None:
        fixture = (
            "<html><head><title>SIMP-03 fixture</title></head><body>"
            "<nav>Global navigation</nav>"
            "<article>" + ("The retrieval fixture has a stable main article body. " * 4) + "</article>"
            "<footer>Footer shell</footer></body></html>"
        )
        expected = (
            "The retrieval fixture has a stable main article body. " * 4
        ).rstrip()

        try:
            from app.services.ingest.raw_import import _extract_text_from_html as raw_extract
            from app.services.ingest.url_pool import _extract_text_from_html as url_pool_extract
            from app.services.ingest.content_cleaner import normalize_content_for_ingest
            from app.services.resource_pool.http_port import make_html_parser
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"ingest HTML locator tests require backend dependencies: {exc}")

        def legacy_extract(html: str, *, transform) -> str:
            parser = make_html_parser(html)
            for selector in ("article", "main article", "[role='main'] article", "main"):
                node = parser.css_first(selector)
                if node is None:
                    continue
                text = str(node.text(separator="\n", strip=True) or "").strip()
                if len(text) >= 120:
                    return transform(text)
            body = parser.body
            if body:
                return transform(str(body.text(separator="\n", strip=True) or "").strip())
            return ""

        original_raw = legacy_extract(fixture, transform=lambda text: text[:50000])
        original_url_pool = legacy_extract(
            fixture,
            transform=lambda text: normalize_content_for_ingest(text, max_chars=50000),
        )
        current_raw = raw_extract(fixture)
        current_url_pool = url_pool_extract(fixture)

        self.assertEqual(original_raw, expected)
        self.assertEqual(current_raw, original_raw)
        self.assertEqual(current_url_pool, original_url_pool)
        self.assertEqual(
            hashlib.sha256(current_raw.encode("utf-8")).hexdigest(),
            hashlib.sha256(original_raw.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            hashlib.sha256(current_url_pool.encode("utf-8")).hexdigest(),
            hashlib.sha256(original_url_pool.encode("utf-8")).hexdigest(),
        )

    def test_ingest_html_locators_keep_empty_and_fallback_behavior(self) -> None:
        try:
            from app.services.ingest.raw_import import _extract_text_from_html as raw_extract
            from app.services.ingest.url_pool import _extract_text_from_html as url_pool_extract
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"ingest HTML locator tests require backend dependencies: {exc}")

        body_only = "<html><body>Short fallback body</body></html>"
        self.assertEqual(raw_extract(""), "")
        self.assertEqual(raw_extract(body_only), "Short fallback body")
        self.assertEqual(url_pool_extract(""), "")
        self.assertEqual(url_pool_extract(body_only), "Short fallback body")

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

    def test_declared_material_text_preserves_exact_body_for_given_and_resource(self) -> None:
        body = (
            "Plain reference <https://example.test/a>.\n\n"
            "Short paragraph one.\n\nShort paragraph two."
        )
        for kind in ("given", "resource"):
            with self.subTest(kind=kind):
                candidate = {
                    "uri": "https://example.test/report",
                    "title": "Declared material",
                    "content": body,
                    "extracted_data_base": {
                        "_raw_input": {
                            "material_input": {
                                "kind": kind,
                                "raw_content_digest": "a" * 64,
                                "mime_type": "text/plain",
                            }
                        }
                    },
                }
                preserved, analysis = apply_main_content_extraction(candidate)

                self.assertEqual(preserved["content"], body)
                self.assertEqual(analysis["main_content"], body)
                self.assertEqual(analysis["main_text_ratio"], 1.0)
                self.assertEqual(analysis["extractor_name"], "ingest.material_text.v1")
                self.assertFalse(analysis["readerable"])

    def test_declared_material_text_keeps_quality_gate_signals(self) -> None:
        body = "\n".join(
            [
                "Published report analysis.",
                "The material explains the retrieval chain and preserves source semantics.",
            ]
            * 80
        )
        candidate = {
            "uri": "https://example.test/report",
            "title": "Declared long material",
            "content": body,
            "extracted_data_base": {
                "_raw_input": {
                    "material_input": {
                        "kind": "resource",
                        "raw_content_digest": "b" * 64,
                        "mime_type": "text/markdown",
                    }
                }
            },
        }
        preserved, analysis = apply_main_content_extraction(candidate)

        self.assertEqual(preserved["content"], body)
        self.assertTrue(analysis["readerable"])
        self.assertEqual(analysis["main_text_ratio"], 1.0)

    def test_declared_material_text_survives_frontdoor_cleaning_limit(self) -> None:
        from app.services.ingest.content_cleaner import clean_frontdoor_document_candidate

        body = "Preserved plain report body.\n" * 2500
        self.assertGreater(len(body), 50000)
        candidate = {
            "uri": "https://example.test/rfc",
            "title": "RFC-like plain",
            "content": body,
            "extracted_data_base": {
                "_raw_input": {
                    "material_input": {
                        "kind": "resource",
                        "raw_content_digest": "c" * 64,
                        "mime_type": "text/plain",
                    }
                }
            },
        }
        extracted, profile = apply_main_content_extraction(candidate)
        cleaned, cleaning_report = clean_frontdoor_document_candidate(extracted)

        self.assertEqual(cleaned["content"], body)
        self.assertEqual(profile["main_text_ratio"], 1.0)
        self.assertFalse(cleaning_report["content_changed"])


if __name__ == "__main__":
    unittest.main()
