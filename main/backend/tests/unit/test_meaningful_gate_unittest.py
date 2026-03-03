from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest.meaningful_gate import (
        content_quality_check,
        normalize_content_for_ingest,
        normalize_reason_code,
        url_policy_check,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class MeaningfulGateUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"meaningful gate unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_url_policy_blocks_low_value_path(self):
        decision = url_policy_check(
            "https://www.google.com/search?q=robotics",
            config={"enable_strict_gate": True},
        )
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.reason, "url_policy_low_value_endpoint")

    def test_url_policy_accepts_detail_page(self):
        decision = url_policy_check(
            "https://example.com/news/robotics-breakthrough",
            config={"enable_strict_gate": True},
        )
        self.assertFalse(decision.blocked)
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.reason, "ok")

    def test_content_quality_rejects_shell_signature(self):
        decision = content_quality_check(
            "https://example.com/post",
            "window.wiz_progre = true; this is hydration shell",
            "url_fetch",
            config={"enable_strict_gate": True, "min_semantic_len": 60},
        )
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.reason, "content_shell_signature")

    def test_content_quality_rejects_pdf_binary_payload(self):
        decision = content_quality_check(
            "https://example.com/file.pdf",
            "%PDF-1.7\n%%EOF",
            "url_fetch",
            extraction_status=None,
            config={"enable_strict_gate": True, "min_semantic_len": 50},
        )
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.reason, "content_pdf_binary_without_text")

    def test_content_quality_rejects_too_short_semantic_text(self):
        decision = content_quality_check(
            "https://example.com/post",
            "short text",
            "url_fetch",
            config={"enable_strict_gate": True, "min_semantic_len": 120},
        )
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.reason, "content_semantic_too_short")

    def test_content_quality_accepts_meaningful_text(self):
        content = " ".join(["robotics market supply chain update"] * 80)
        decision = content_quality_check(
            "https://example.com/report",
            content,
            "url_fetch",
            config={"enable_strict_gate": True, "min_semantic_len": 200},
        )
        self.assertTrue(decision.accepted)
        self.assertFalse(decision.blocked)
        self.assertEqual(decision.reason, "ok")

    def test_normalize_content_for_ingest_removes_noise_lines(self):
        raw = (
            "Skip to content\n"
            "Accessibility Help\n"
            "Watch live\n"
            "Robotics startup raised funding and expanded production in 2026.\n"
        )
        normalized = normalize_content_for_ingest(raw, max_chars=1000)
        self.assertIn("Robotics startup raised funding", normalized)
        self.assertNotIn("Skip to content", normalized)
        self.assertNotIn("Accessibility Help", normalized)

    def test_normalize_content_for_ingest_removes_nav_shell_lines_and_keeps_body(self):
        raw = (
            "Home | News | Sport | Business | Technology | Sign in | Register\n"
            "Privacy Policy | Terms of Use | Cookie Settings\n"
            "Embodied AI device shipments increased 37 percent year over year in 2025.\n"
            "The company focused on one high-frequency workflow and improved retention.\n"
        )
        normalized = normalize_content_for_ingest(raw, max_chars=2000)
        self.assertIn("Embodied AI device shipments increased", normalized)
        self.assertIn("high-frequency workflow", normalized)
        self.assertNotIn("Home | News | Sport", normalized)
        self.assertNotIn("Privacy Policy", normalized)

    def test_content_quality_rejects_link_farm_like(self):
        links = " ".join([f"https://example.com/{idx}" for idx in range(30)])
        decision = content_quality_check(
            "https://example.com/topic-page",
            links,
            "url_fetch",
            config={"enable_strict_gate": True, "min_semantic_len": 120},
        )
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.reason, "content_link_farm_like")

    def test_content_quality_rejects_api_status_wrapper(self):
        decision = content_quality_check(
            "https://example.com/rss",
            '{"url":"https://example.com/rss","status":202,"title":null,"text":""}',
            "url_fetch",
            config={"enable_strict_gate": True, "min_semantic_len": 80},
        )
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.reason, "content_api_status_wrapper")

    def test_content_quality_rejects_rss_feed_shell(self):
        decision = content_quality_check(
            "https://export.arxiv.org/rss",
            "No archive specified. Archives are: astro-ph, cs, math.",
            "url_fetch",
            config={"enable_strict_gate": True, "min_semantic_len": 120},
        )
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.reason, "content_rss_feed_shell")

    def test_content_quality_rejects_js_template_shell(self):
        content = " ".join(
            [
                "__doPostBack('x','y')",
                "window.test=1;",
                "document.cookie='a=b';",
                "function(){return 1;}",
                "var x=1;",
                "@font-face",
                ":root{--x:1}",
                "sourcemappingurl=abc",
            ]
        )
        decision = content_quality_check(
            "https://example.com/template",
            content,
            "url_fetch",
            config={"enable_strict_gate": True, "min_semantic_len": 100},
        )
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.reason, "content_js_template_shell")

    def test_content_quality_rejects_mojibake_garbled(self):
        decision = content_quality_check(
            "https://example.com/garbled",
            "èªå¨é©¾é©¶ æ°é» å·æ¸ ç»å½ æ³¨å æ¨è",
            "url_fetch",
            config={"enable_strict_gate": True, "min_semantic_len": 80},
        )
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.reason, "content_mojibake_garbled")

    def test_gate_can_be_disabled(self):
        decision = url_policy_check(
            "https://www.google.com/search?q=robotics",
            config={"enable_strict_gate": False},
        )
        self.assertTrue(decision.accepted)
        self.assertFalse(decision.blocked)
        self.assertEqual(decision.reason, "disabled")

    def test_normalize_reason_code_generates_stable_snake_case(self):
        self.assertEqual(normalize_reason_code("Low Value/Page"), "low_value_page")
        self.assertEqual(normalize_reason_code(""), "unknown_rejection_reason")


if __name__ == "__main__":
    unittest.main()
