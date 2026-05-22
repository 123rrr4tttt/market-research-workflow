from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.resource_pool.search_result_parser_service import resolve_search_result_parser_modules
from app.services.resource_pool.search_result_parser_service import resolve_search_result_parser_profile
from app.services.resource_pool.search_template_service import execute_search_template
from app.services.resource_pool.search_template_service import execute_feed_probe
from app.services.resource_pool.search_template_service import execute_external_site_search
from app.services.resource_pool.search_template_service import execute_sitemap_probe
from app.services.resource_pool.search_template_service import extract_link_candidates_from_html
from app.services.resource_pool.search_template_service import extract_link_candidates_with_diagnostics_from_html
from app.services.resource_pool.search_template_service import normalize_search_template_placeholders
from app.services.resource_pool.search_template_service import resolve_search_template_pagination


class SearchTemplateServiceUnitTestCase(unittest.TestCase):
    def test_normalize_placeholders_decodes_encoded_markers(self) -> None:
        raw = "https://example.com/search?q=%7B%7Bq%7D%7D&page=%7B%7Bpage%7D%7D"
        self.assertEqual(
            normalize_search_template_placeholders(raw),
            "https://example.com/search?q={{q}}&page={{page}}",
        )

    def test_resolve_pagination_clamps_values(self) -> None:
        start_page, max_pages = resolve_search_template_pagination({"page": -4, "max_pages": 1000})
        self.assertEqual(start_page, 1)
        self.assertEqual(max_pages, 50)

    def test_execute_search_template_collects_multi_page_candidates(self) -> None:
        seen_urls: list[str] = []
        page_one = """
        <html><body>
          <a href="/posts/123?utm_source=nl">Alpha market update</a>
        </body></html>
        """
        page_two = """
        <html><body>
          <a href="/posts/456" title="Beta outlook">Read more</a>
        </body></html>
        """

        def _fake_fetch(url: str, *, timeout: float, retries: int):  # noqa: ANN001
            seen_urls.append(url)
            if "page=2" in url:
                return page_two, object()
            return page_one, object()

        with patch("app.services.resource_pool.search_template_service.fetch_html", side_effect=_fake_fetch):
            result = execute_search_template(
                template="https://example.com/search?query={{q}}",
                query_terms=["Alpha", "Beta"],
                params={"page": 1, "max_pages": 2},
                probe_timeout=5.0,
                allow_term_fallback=True,
                entry_domain="example.com",
            )

        self.assertEqual(len(seen_urls), 2)
        self.assertEqual(result.pages_scanned, 2)
        self.assertEqual(len(result.raw_candidates), 2)
        self.assertEqual(
            {decision.url for decision in result.selected_candidates},
            {"https://example.com/posts/123", "https://example.com/posts/456"},
        )
        self.assertFalse(result.used_term_fallback)
        self.assertGreaterEqual(result.diagnostics["parser_global_anchor_hit"], 2)

    def test_execute_search_template_retries_with_resilient_service_on_429(self) -> None:
        attempts: list[tuple[str, int]] = []
        html = """
        <html><body>
          <a href="/posts/123">Robotics digest</a>
        </body></html>
        """

        def _fake_fetch(url: str, *, timeout: float, retries: int):  # noqa: ANN001
            attempts.append((url, retries))
            if len(attempts) == 1:
                raise Exception("429 Client Error: rate limit")
            return html, object()

        with patch("app.services.resource_pool.search_template_service.fetch_html", side_effect=_fake_fetch):
            result = execute_search_template(
                template="https://example.com/search?q={{q}}",
                query_terms=["robotics"],
                params={"enable_search_service_fallback": True},
                probe_timeout=5.0,
                allow_term_fallback=False,
                entry_domain="example.com",
            )

        self.assertEqual(attempts[0][1], 1)
        self.assertEqual(attempts[1][1], 2)
        self.assertEqual(result.diagnostics["search_service"], "resilient")
        self.assertEqual(result.diagnostics["search_service_fallbacks"], 1)
        self.assertEqual([decision.url for decision in result.selected_candidates], ["https://example.com/posts/123"])

    def test_execute_search_template_reports_filter_empty_without_fallback(self) -> None:
        html = """
        <html><body>
          <a href="/posts/market-outlook">Market outlook</a>
        </body></html>
        """

        with patch("app.services.resource_pool.search_template_service.fetch_html", return_value=(html, object())), patch(
            "app.services.resource_pool.search_capabilities._expand_semantic_query_terms_with_llm",
            return_value=[],
        ):
            result = execute_search_template(
                template="https://example.com/search?q={{q}}",
                query_terms=["robotics"],
                params={},
                probe_timeout=5.0,
                allow_term_fallback=False,
                entry_domain="example.com",
            )

        self.assertEqual(result.selected_candidates, [])
        self.assertTrue(result.used_term_fallback)
        self.assertFalse(result.diagnostics["fallback_allowed"])
        self.assertTrue(result.diagnostics["used_term_fallback"])
        self.assertEqual(result.diagnostics["candidate_filter_state"], "term_filter_empty_no_fallback")

    def test_execute_search_template_reports_filter_fallback_used(self) -> None:
        html = """
        <html><body>
          <a href="/posts/market-outlook">Market outlook</a>
        </body></html>
        """

        with patch("app.services.resource_pool.search_template_service.fetch_html", return_value=(html, object())):
            result = execute_search_template(
                template="https://example.com/search?q={{q}}",
                query_terms=["robotics"],
                params={},
                probe_timeout=5.0,
                allow_term_fallback=True,
                entry_domain="example.com",
            )

        self.assertEqual([decision.url for decision in result.selected_candidates], ["https://example.com/posts/market-outlook"])
        self.assertTrue(result.used_term_fallback)
        self.assertTrue(result.diagnostics["fallback_allowed"])
        self.assertTrue(result.diagnostics["used_term_fallback"])
        self.assertEqual(result.diagnostics["candidate_filter_state"], "term_filter_empty_fallback_used")

    def test_extract_link_candidates_from_html_filters_navigation_noise(self) -> None:
        html = """
        <html><body>
          <main>
            <article class="search-result">
              <h2><a href="/posts/openai-earnings">OpenAI earnings analysis</a></h2>
              <p>Analysis on OpenAI and Microsoft results.</p>
            </article>
            <nav>
              <a href="/login">Sign in</a>
              <a href="https://twitter.com/example">Twitter</a>
            </nav>
          </main>
        </body></html>
        """
        candidates = extract_link_candidates_from_html(html, base_url="https://example.com/search?q=openai")
        self.assertEqual([item.url for item in candidates], ["https://example.com/posts/openai-earnings"])
        self.assertIn("Microsoft", candidates[0].text)
        self.assertIn("Analysis on OpenAI", candidates[0].summary)

    def test_extract_link_candidates_from_html_supports_structured_result_attributes(self) -> None:
        html = """
        <html><body>
          <main>
            <article class="search-result" data-url="/posts/openai-roadmap">
              <h2>OpenAI roadmap update</h2>
              <p>Roadmap details and platform changes.</p>
            </article>
          </main>
        </body></html>
        """
        candidates = extract_link_candidates_from_html(html, base_url="https://example.com/search?q=openai")
        self.assertEqual([item.url for item in candidates], ["https://example.com/posts/openai-roadmap"])
        self.assertEqual(candidates[0].title, "OpenAI roadmap update")

    def test_extract_link_candidates_from_html_supports_json_ld_result_items(self) -> None:
        html = """
        <html><body>
          <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "itemListElement": [
              {
                "@type": "ListItem",
                "position": 1,
                "item": {
                  "@type": "NewsArticle",
                  "url": "https://example.com/posts/openai-article",
                  "name": "OpenAI article",
                  "description": "OpenAI article summary"
                }
              }
            ]
          }
          </script>
        </body></html>
        """
        candidates = extract_link_candidates_from_html(html, base_url="https://example.com/search?q=openai")
        self.assertEqual([item.url for item in candidates], ["https://example.com/posts/openai-article"])
        self.assertEqual(candidates[0].title, "OpenAI article")
        self.assertIn("OpenAI article summary", candidates[0].summary)

    def test_extract_link_candidates_from_html_uses_container_title_when_anchor_is_read_more(self) -> None:
        html = """
        <html><body>
          <div class="search-results">
            <div class="result-item">
              <h2 class="entry-title">OpenAI enterprise pricing memo</h2>
              <p class="summary">Notes on enterprise pricing and rollout.</p>
              <a href="/posts/openai-pricing">Read more</a>
            </div>
          </div>
        </body></html>
        """
        candidates = extract_link_candidates_from_html(html, base_url="https://example.com/search?q=openai")
        self.assertEqual([item.url for item in candidates], ["https://example.com/posts/openai-pricing"])
        self.assertEqual(candidates[0].title, "OpenAI enterprise pricing memo")
        self.assertIn("enterprise pricing", candidates[0].text)

    def test_extract_link_candidates_from_html_uses_global_anchor_recovery(self) -> None:
        html = """
        <html><body>
          <nav><a href="/about">About</a></nav>
          <section>
            <a href="/posts/openai-roadmap-2026">OpenAI roadmap 2026 deep dive</a>
          </section>
        </body></html>
        """
        candidates = extract_link_candidates_from_html(html, base_url="https://example.com/search?q=openai")
        self.assertEqual([item.url for item in candidates], ["https://example.com/posts/openai-roadmap-2026"])

    def test_extract_link_candidates_from_html_prefers_commercialobserver_article_links(self) -> None:
        html = """
        <html><body>
          <div class="card-text">
            <a href="https://commercialobserver.com/industrial/">Industrial</a>
            <h2><a href="https://commercialobserver.com/2026/02/barry-diraimondo-steelwave-5-questions/">Barry DiRaimondo of SteelWave: 5 Questions</a></h2>
            <p>Interview and market context.</p>
          </div>
        </body></html>
        """
        candidates = extract_link_candidates_from_html(
            html,
            base_url="https://commercialobserver.com/?s=openai",
            entry_domain="commercialobserver.com",
        )
        self.assertEqual(
            [item.url for item in candidates],
            ["https://commercialobserver.com/2026/02/barry-diraimondo-steelwave-5-questions"],
        )
        self.assertEqual(candidates[0].title, "Barry DiRaimondo of SteelWave: 5 Questions")

    def test_extract_link_candidates_with_anchor_only_profile_skips_container_modules(self) -> None:
        html = """
        <html><body>
          <main>
            <article class="search-result">
              <h2><a href="/posts/openai-earnings">OpenAI earnings analysis</a></h2>
            </article>
          </main>
        </body></html>
        """
        _, diagnostics = extract_link_candidates_with_diagnostics_from_html(
            html,
            base_url="https://example.com/search?q=openai",
            entry_domain="example.com",
            parser_profile="fallback_anchor_only",
        )
        self.assertEqual(diagnostics["parser_profile_resolved"], "fallback_anchor_only")
        self.assertEqual(diagnostics["parser_modules_tried"], ["global_anchor"])

    def test_resolve_search_result_parser_modules_returns_commercialobserver_specific_chain(self) -> None:
        profile = resolve_search_result_parser_profile(
            "commercialobserver.com",
            parser_profile="site_adaptive",
        )
        modules = resolve_search_result_parser_modules(profile)
        self.assertEqual([module.module_id for module in modules], ["container", "structured", "jsonld", "global_anchor"])
        self.assertEqual(profile.profile_key, "site_adaptive.commercialobserver_card")

    def test_extract_link_candidates_from_html_filters_pymnts_topic_noise(self) -> None:
        html = """
        <html><body>
          <article class="search-result">
            <h2><a href="https://www.pymnts.com/topic/ai/">AI</a></h2>
          </article>
          <article class="search-result">
            <h2><a href="https://www.pymnts.com/news/artificial-intelligence/2026/03/15/openai-rolls-out-new-agent-tools/">OpenAI Rolls Out New Agent Tools</a></h2>
            <p>Coverage of OpenAI launches and payments infrastructure.</p>
          </article>
        </body></html>
        """
        candidates = extract_link_candidates_from_html(
            html,
            base_url="https://www.pymnts.com/?s=openai",
            entry_domain="www.pymnts.com",
        )
        self.assertEqual(
            [item.url for item in candidates],
            [
                "https://www.pymnts.com/topic/ai",
                "https://www.pymnts.com/news/artificial-intelligence/2026/03/15/openai-rolls-out-new-agent-tools",
            ],
        )
        self.assertEqual(candidates[0].extra.get("route_kind"), "section")
        self.assertEqual(candidates[1].extra.get("route_kind"), "article")

    def test_resolve_search_result_parser_profile_returns_pymnts_profile(self) -> None:
        profile = resolve_search_result_parser_profile(
            "www.pymnts.com",
            parser_profile="site_adaptive",
        )
        self.assertEqual(profile.profile_key, "site_adaptive.pymnts_card")

    def test_extract_link_candidates_from_html_prefers_investopedia_result_cards(self) -> None:
        html = """
        <html><body>
          <div class="mntl-search-results__list">
            <article class="mntl-document-card">
              <a href="https://www.investopedia.com/openai-is-shuttering-its-sora-video-app-here-is-what-the-move-says-about-its-strategy-11933900">
                OpenAI Is Shuttering Its Sora Video App. Here's What the Move Says About Its Strategy.
              </a>
              <p>Analysis of OpenAI's product strategy shift.</p>
            </article>
            <article class="mntl-document-card">
              <a href="https://www.investopedia.com/simulator/portfolio">Login / Portfolio</a>
            </article>
          </div>
        </body></html>
        """
        candidates = extract_link_candidates_from_html(
            html,
            base_url="https://www.investopedia.com/search?q=openai+api",
            entry_domain="www.investopedia.com",
        )
        self.assertEqual(
            [item.url for item in candidates],
            ["https://www.investopedia.com/openai-is-shuttering-its-sora-video-app-here-is-what-the-move-says-about-its-strategy-11933900"],
        )
        self.assertEqual(candidates[0].extra.get("route_kind"), "article")

    def test_resolve_search_result_parser_profile_returns_investopedia_profile(self) -> None:
        profile = resolve_search_result_parser_profile(
            "www.investopedia.com",
            parser_profile="site_adaptive",
        )
        self.assertEqual(profile.profile_key, "site_adaptive.investopedia_cards")
        self.assertEqual(profile.default_route_kind, "article")

    def test_extract_link_candidates_from_html_routes_hai_section_and_publication_candidates(self) -> None:
        html = """
        <html><body>
          <a href="https://hai.stanford.edu/research/fellowship-programs">Fellowship Programs</a>
          <a href="https://hai.stanford.edu/ai-index/2025-ai-index-report">AI Index Report</a>
          <a href="https://hai.stanford.edu/policy/publications">Policy Publications</a>
          <a href="https://www.stanford.edu/site/accessibility">Accessibility</a>
        </body></html>
        """
        candidates = extract_link_candidates_from_html(
            html,
            base_url="https://hai.stanford.edu/search?keyword=openai",
            entry_domain="hai.stanford.edu",
        )
        self.assertEqual(
            [item.url for item in candidates],
            [
                "https://hai.stanford.edu/research/fellowship-programs",
                "https://hai.stanford.edu/ai-index/2025-ai-index-report",
                "https://hai.stanford.edu/policy/publications",
            ],
        )
        self.assertEqual(candidates[0].extra.get("route_kind"), "section")
        self.assertEqual(candidates[1].extra.get("route_kind"), "research_tool")
        self.assertEqual(candidates[2].extra.get("route_kind"), "publication_hub")

    def test_resolve_search_result_parser_profile_returns_hai_profile(self) -> None:
        profile = resolve_search_result_parser_profile(
            "hai.stanford.edu",
            parser_profile="site_adaptive",
        )
        self.assertEqual(profile.profile_key, "site_adaptive.hai_research_shell")
        self.assertEqual(profile.default_route_kind, "page")
        self.assertTrue(profile.route_rules)

    def test_extract_link_candidates_from_html_rejects_image_assets_from_json_ld(self) -> None:
        html = """
        <html><body>
          <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@graph": [
              {"@type":"ImageObject","url":"https://example.com/uploads/openai-cover.jpg"},
              {"@type":"NewsArticle","url":"https://example.com/posts/openai-update","headline":"OpenAI update"}
            ]
          }
          </script>
        </body></html>
        """
        candidates = extract_link_candidates_from_html(
            html,
            base_url="https://example.com/search?q=openai",
            entry_domain="example.com",
        )
        self.assertEqual([item.url for item in candidates], ["https://example.com/posts/openai-update"])

    def test_execute_feed_probe_supports_atom_entries(self) -> None:
        atom_xml = """
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Robotics Weekly</title>
            <summary>Hands-on robotics coverage</summary>
            <link rel="alternate" type="text/html" href="https://example.com/posts/robotics-weekly" />
          </entry>
        </feed>
        """

        with patch("app.services.resource_pool.search_template_service.fetch_html", return_value=(atom_xml, object())):
            result = execute_feed_probe(
                feed_url="https://example.com/feed.xml",
                query_terms=["robotics"],
                probe_timeout=5.0,
                allow_term_fallback=False,
            )

        self.assertEqual(
            [decision.url for decision in result.selected_candidates],
            ["https://example.com/posts/robotics-weekly"],
        )
        self.assertFalse(result.used_term_fallback)
        self.assertEqual(result.diagnostics["candidate_filter_state"], "selected")

    def test_execute_external_site_search_uses_search_sources_results(self) -> None:
        with patch(
            "app.services.search.web.generate_keywords",
            return_value=["site:example.com robotics"],
        ), patch(
            "app.services.search.web.DDGS"
        ) as ddgs:
            ddgs.return_value.__enter__.return_value.text.return_value = iter(
                [
                    {
                        "title": "Example robotics guide",
                        "href": "https://example.com/posts/robotics-guide?utm_source=ddg",
                        "body": "Guide to robotics",
                    }
                ]
            )
            result = execute_external_site_search(
                entry_domain="example.com",
                query_terms=["robotics"],
                probe_timeout=5.0,
                allow_term_fallback=False,
                params={"external_search_provider": "ddg", "external_search_limit": 5},
            )

        self.assertEqual(
            [decision.url for decision in result.selected_candidates],
            ["https://example.com/posts/robotics-guide"],
        )
        self.assertEqual(result.diagnostics["search_service"], "external_search")

    def test_execute_external_site_search_uses_slowlane_when_provider_returns_empty(self) -> None:
        html = """
        <html><body>
          <a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fposts%2Fslow-hit">Example robotics slow hit</a>
        </body></html>
        """
        with patch(
            "app.services.search.web.search_sources",
            return_value=[],
        ), patch(
            "app.services.resource_pool.search_template_service.fetch_html",
            return_value=(html, object()),
        ), patch(
            "app.services.resource_pool.search_template_service.time.sleep"
        ):
            result = execute_external_site_search(
                entry_domain="example.com",
                query_terms=["robotics"],
                probe_timeout=5.0,
                allow_term_fallback=False,
                params={"enable_external_search_slowlane": True},
            )

        self.assertEqual(
            [decision.url for decision in result.selected_candidates],
            ["https://example.com/posts/slow-hit"],
        )
        self.assertEqual(result.diagnostics["search_service"], "external_search_slowlane")

    def test_execute_sitemap_probe_expands_nested_sitemaps(self) -> None:
        sitemap_index = """
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <sitemap><loc>https://example.com/sitemap-posts.xml</loc></sitemap>
        </sitemapindex>
        """
        sitemap_posts = """
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://example.com/posts/robotics-guide</loc></url>
        </urlset>
        """

        def _fake_fetch(url: str, *, timeout: float, retries: int):  # noqa: ANN001
            if url.endswith("sitemap-posts.xml"):
                return sitemap_posts, object()
            return sitemap_index, object()

        with patch("app.services.resource_pool.search_template_service.fetch_html", side_effect=_fake_fetch):
            result = execute_sitemap_probe(
                sitemap_url="https://example.com/sitemap.xml",
                query_terms=["robotics"],
                probe_timeout=5.0,
                max_depth=2,
                max_sitemaps=10,
                allow_term_fallback=False,
            )

        self.assertEqual(
            [decision.url for decision in result.selected_candidates],
            ["https://example.com/posts/robotics-guide"],
        )
        self.assertFalse(result.used_term_fallback)


if __name__ == "__main__":
    unittest.main()
