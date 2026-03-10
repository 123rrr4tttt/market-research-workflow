from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services import tasks as tasks_module
    from app.services.ingest.meaningful_gate import GateDecision
    from app.services.ingest import single_url as single_url_module
    from app.services.ingest import url_pool as url_pool_module

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class SingleUrlIngestUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"single url ingest unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_task_ingest_single_url_low_value_strict_mode_switches_status(self):
        captured_calls: list[dict] = []

        def _fake_ingest_single_url(
            *,
            url: str,
            query_terms: list[str] | None = None,
            strict_mode: bool = False,
            search_options: dict | None = None,
        ):
            captured_calls.append(
                {
                    "url": url,
                    "query_terms": list(query_terms or []),
                    "strict_mode": strict_mode,
                    "search_options": dict(search_options or {}),
                }
            )
            if strict_mode:
                return {"status": "failed", "task_result_status": "failed", "low_value": True}
            return {"status": "degraded", "task_result_status": "degraded", "low_value": True}

        fake_module = types.ModuleType("app.services.ingest.single_url")
        fake_module.ingest_single_url = _fake_ingest_single_url

        with patch.dict(sys.modules, {"app.services.ingest.single_url": fake_module}):
            degraded = tasks_module.task_ingest_single_url(
                "https://example.com/legal",
                ["market"],
                False,
                "demo_proj",
            )
            failed = tasks_module.task_ingest_single_url(
                "https://example.com/legal",
                ["market"],
                True,
                "demo_proj",
            )

        self.assertEqual(degraded.get("status"), "degraded")
        self.assertEqual(degraded.get("task_result_status"), "degraded")
        self.assertTrue(degraded.get("low_value"))
        self.assertEqual(failed.get("status"), "failed")
        self.assertEqual(failed.get("task_result_status"), "failed")
        self.assertTrue(failed.get("low_value"))
        self.assertEqual(
            captured_calls,
            [
                {"search_options": {}, "url": "https://example.com/legal", "query_terms": ["market"], "strict_mode": False},
                {"search_options": {}, "url": "https://example.com/legal", "query_terms": ["market"], "strict_mode": True},
            ],
        )

    def test_apply_structured_extraction_exception_sets_failed_without_structured_fields(self):
        extracted_data = {"platform": "url_pool"}

        class _ExplodingExtractor:
            @staticmethod
            def extract_structured_enriched(*_args, **_kwargs):
                raise RuntimeError("extractor offline")

        with patch.object(url_pool_module, "_EXTRACTION_APP", _ExplodingExtractor()):
            url_pool_module._apply_structured_extraction(
                extracted_data,
                domain_str="example.com",
                content="important content",
                url="https://example.com/post/1",
            )

        self.assertEqual(extracted_data.get("platform"), "url_pool")
        self.assertEqual(extracted_data.get("extraction_status"), "failed")
        self.assertEqual(extracted_data.get("extraction_reason"), "extractor_exception")
        self.assertIn("RuntimeError", str(extracted_data.get("extraction_error")))
        self.assertNotIn("market_data", extracted_data)
        self.assertNotIn("policy_data", extracted_data)
        self.assertNotIn("company_data", extracted_data)

    def test_ingest_single_url_search_template_without_results_is_gated(self):
        fake_job_id = 123
        fake_fetch = unittest.mock.Mock(return_value=("<html></html>", unittest.mock.Mock(status_code=200)))
        fake_extract = unittest.mock.Mock(return_value={"items": [], "result_count": 0, "summary_text": "", "snippet_chars": 0})

        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ) as complete_job, patch.object(single_url_module, "fetch_html", fake_fetch), patch.object(
            single_url_module, "_extract_search_results", fake_extract
        ), patch.object(
            single_url_module, "_pick_crawler_channel", return_value=None
        ):
            degraded = single_url_module.ingest_single_url(
                url="https://www.google.com/search?q=test",
                query_terms=["test"],
                strict_mode=False,
                search_options={"fallback_on_insufficient": False},
            )
            failed = single_url_module.ingest_single_url(
                url="https://www.google.com/search?q=test",
                query_terms=["test"],
                strict_mode=True,
                search_options={"fallback_on_insufficient": False},
            )

        self.assertEqual(degraded.get("status"), "degraded_success")
        self.assertEqual(degraded.get("inserted"), 0)
        self.assertEqual(degraded.get("skipped"), 1)
        self.assertEqual(degraded.get("page_gate", {}).get("reason"), "search_template_results_insufficient")
        self.assertEqual(degraded.get("reason_code"), "search_template_results_insufficient")
        self.assertIn("search_template_no_results", degraded.get("degradation_flags", []))
        self.assertEqual(degraded.get("search_results", {}).get("result_count"), 0)
        diagnostics = (degraded.get("page_gate") or {}).get("diagnostics") or {}
        self.assertEqual(int(diagnostics.get("result_count") or 0), 0)
        self.assertEqual(int(diagnostics.get("min_results_required") or 0), 6)
        self.assertEqual(int(diagnostics.get("candidate_shortfall") or 0), 6)
        self.assertEqual(failed.get("status"), "failed")
        failed_reason = failed.get("page_gate", {}).get("reason")
        prefetch_reason = failed.get("pre_fetch_url_gate", {}).get("reason")
        self.assertIn(
            failed_reason or prefetch_reason,
            {"search_template_results_insufficient", "url_policy_low_value_endpoint"},
        )
        self.assertEqual(fake_fetch.call_count, 1)
        self.assertEqual(fake_extract.call_count, 1)
        self.assertEqual(complete_job.call_count, 2)

    def test_ingest_single_url_search_template_does_not_write_template_document_by_default(self):
        fake_job_id = 124
        fake_fetch = unittest.mock.Mock(return_value=("<html></html>", unittest.mock.Mock(status_code=200)))
        fake_extract = unittest.mock.Mock(
            return_value={
                "items": [
                    {"title": "A", "url": "https://example.com/a", "snippet": "s1"},
                    {"title": "B", "url": "https://example.org/b", "snippet": "s2"},
                ],
                "result_count": 2,
                "summary_text": "1. A | https://example.com/a\n2. B | https://example.org/b",
                "snippet_chars": 64,
            }
        )
        allowed_gate = GateDecision(
            accepted=True,
            blocked=False,
            reason="ok",
            quality_score=100.0,
            diagnostics={},
        )
        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ) as complete_job, patch.object(
            single_url_module, "url_policy_check", return_value=allowed_gate
        ), patch.object(single_url_module, "fetch_html", fake_fetch), patch.object(
            single_url_module, "_extract_search_results", fake_extract
        ), patch.object(
            single_url_module, "_persist_single_url_document"
        ) as persist_doc:
            result = single_url_module.ingest_single_url(
                url="https://www.google.com/search?q=test",
                query_terms=["test"],
                strict_mode=False,
                search_options={
                    "search_expand": False,
                    "allow_search_summary_write": True,
                    "min_results_required": 1,
                },
            )

        self.assertEqual(result.get("status"), "degraded_success")
        self.assertEqual(int(result.get("inserted") or 0), 0)
        self.assertEqual(result.get("page_gate", {}).get("reason"), "search_template_document_write_disabled")
        self.assertEqual(result.get("reason_code"), "search_template_document_write_disabled")
        diagnostics = (result.get("page_gate") or {}).get("diagnostics") or {}
        self.assertEqual(int(diagnostics.get("result_count") or 0), 2)
        self.assertEqual(int(diagnostics.get("min_results_required") or 0), 1)
        self.assertEqual(int(diagnostics.get("candidate_shortfall") or 0), 0)
        self.assertEqual(persist_doc.call_count, 0)
        self.assertEqual(complete_job.call_count, 1)

    def test_ingest_single_url_search_template_can_write_template_document_when_explicitly_enabled(self):
        fake_job_id = 125
        fake_fetch = unittest.mock.Mock(return_value=("<html></html>", unittest.mock.Mock(status_code=200)))
        fake_extract = unittest.mock.Mock(
            return_value={
                "items": [
                    {"title": "A", "url": "https://example.com/a", "snippet": "s1"},
                    {"title": "B", "url": "https://example.org/b", "snippet": "s2"},
                ],
                "result_count": 2,
                "summary_text": "1. A | https://example.com/a\n2. B | https://example.org/b",
                "snippet_chars": 64,
            }
        )
        allowed_gate = GateDecision(
            accepted=True,
            blocked=False,
            reason="ok",
            quality_score=100.0,
            diagnostics={},
        )
        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ) as complete_job, patch.object(
            single_url_module, "url_policy_check", return_value=allowed_gate
        ), patch.object(single_url_module, "fetch_html", fake_fetch), patch.object(
            single_url_module, "_extract_search_results", fake_extract
        ), patch.object(
            single_url_module, "content_quality_check", return_value=allowed_gate
        ), patch.object(
            single_url_module._EXTRACTION_APP, "extract_structured_enriched", return_value={}
        ), patch.object(
            single_url_module, "_persist_single_url_document", return_value=(501, 1, 0, "url_fetch")
        ) as persist_doc:
            result = single_url_module.ingest_single_url(
                url="https://www.google.com/search?q=test",
                query_terms=["test"],
                strict_mode=False,
                search_options={
                    "search_expand": False,
                    "allow_search_summary_write": True,
                    "allow_template_as_document": True,
                    "min_results_required": 1,
                },
            )

        self.assertGreaterEqual(int(result.get("inserted") or 0), 1)
        self.assertEqual(result.get("document_id"), 501)
        self.assertNotEqual(result.get("page_gate", {}).get("reason"), "search_template_document_write_disabled")
        self.assertEqual(persist_doc.call_count, 1)
        self.assertEqual(complete_job.call_count, 1)

    def test_ingest_single_url_search_template_with_candidates_expands_and_persists_children(self):
        fake_job_id = 126
        parent_url = "https://www.google.com/search?q=test"
        child_urls = ["https://example.com/a", "https://example.org/b"]
        fake_extract = unittest.mock.Mock(
            return_value={
                "items": [
                    {"title": "A", "url": child_urls[0], "snippet": "s1"},
                    {"title": "B", "url": child_urls[1], "snippet": "s2"},
                ],
                "result_count": 2,
                "summary_text": "1. A | https://example.com/a\n2. B | https://example.org/b",
                "snippet_chars": 64,
            }
        )
        allowed_gate = GateDecision(
            accepted=True,
            blocked=False,
            reason="ok",
            quality_score=100.0,
            diagnostics={},
        )

        def _fake_fetch(url: str, *_args, **_kwargs):
            if url == parent_url:
                return "<html><body>search</body></html>", unittest.mock.Mock(status_code=200)
            return "<html><head><title>Detail</title></head><body>detail</body></html>", unittest.mock.Mock(status_code=200)

        persisted = {"count": 0}

        def _fake_persist(**_kwargs):
            persisted["count"] += 1
            return 600 + persisted["count"], 1, 0, "url_fetch"

        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ) as complete_job, patch.object(
            single_url_module, "url_policy_check", return_value=allowed_gate
        ), patch.object(single_url_module, "fetch_html", side_effect=_fake_fetch), patch.object(
            single_url_module, "_extract_search_results", fake_extract
        ), patch.object(
            single_url_module, "_extract_text_from_html", return_value=("meaningful robotics insight " * 80)
        ), patch.object(
            single_url_module, "_classify_page_type", return_value=("detail", False, None)
        ), patch.object(
            single_url_module, "content_quality_check", return_value=allowed_gate
        ), patch.object(
            single_url_module._EXTRACTION_APP, "extract_structured_enriched", return_value={"market_data": {"summary": "ok"}}
        ), patch.object(
            single_url_module, "_persist_single_url_document", side_effect=_fake_persist
        ):
            result = single_url_module.ingest_single_url(
                url=parent_url,
                query_terms=["test"],
                strict_mode=False,
                search_options={
                    "search_expand": True,
                    "search_expand_limit": 2,
                    "min_results_required": 1,
                },
            )

        self.assertGreaterEqual(int(result.get("inserted") or 0), 2)
        self.assertGreaterEqual(int(result.get("inserted_valid") or 0), 2)
        self.assertEqual(result.get("page_gate", {}).get("reason"), "search_expand_ingested")
        self.assertEqual((result.get("search_expand") or {}).get("expanded_count"), 2)
        self.assertEqual(persisted["count"], 2)
        self.assertEqual(complete_job.call_count, 3)

    def test_ingest_single_url_pre_fetch_url_gate_rejects_before_fetch(self):
        fake_job_id = 451
        fake_decision = GateDecision(
            accepted=False,
            blocked=True,
            reason="url_policy_low_value_endpoint",
            quality_score=0.0,
            diagnostics={"matched_path_keyword": "/search"},
        )
        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ) as complete_job, patch.object(
            single_url_module, "url_policy_check", return_value=fake_decision
        ), patch.object(
            single_url_module, "fetch_html"
        ) as fetch_html:
            result = single_url_module.ingest_single_url(
                url="https://example.com/search?q=test",
                query_terms=["test"],
                strict_mode=False,
            )
        self.assertEqual(result.get("status"), "degraded_success")
        self.assertEqual(result.get("inserted"), 0)
        self.assertEqual(result.get("rejected_count"), 1)
        gate_reason = str((result.get("pre_fetch_url_gate") or {}).get("reason") or "").strip()
        self.assertTrue(bool(gate_reason))
        breakdown = dict(result.get("rejection_breakdown") or {})
        self.assertGreaterEqual(sum(int(v or 0) for v in breakdown.values()), 1)
        self.assertEqual(fetch_html.call_count, 0)
        self.assertEqual(complete_job.call_count, 1)

    def test_ingest_single_url_search_template_fallbacks_to_crawler_pool_after_simple_flow(self):
        fake_job_id = 321
        fake_fetch = unittest.mock.Mock(return_value=("<html></html>", unittest.mock.Mock(status_code=200)))
        fake_extract = unittest.mock.Mock(return_value={"items": [], "result_count": 0, "summary_text": "", "snippet_chars": 0})
        fake_channel = {"channel_key": "crawler.demo_proj", "provider_type": "scrapy", "enabled": True, "default_params": {}}
        fake_dispatch = {
            "inserted": 1,
            "updated": 0,
            "skipped": 0,
            "provider_job_id": "job-1",
            "provider_status": "ok",
            "provider_type": "scrapy",
            "attempt_count": 1,
            "output_ingest": {"import_result": {"items": [{"doc_id": 999, "status": "ok"}]}},
        }

        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ) as complete_job, patch.object(single_url_module, "fetch_html", fake_fetch), patch.object(
            single_url_module, "_extract_search_results", fake_extract
        ), patch.object(
            single_url_module, "_pick_crawler_channel", return_value=("crawler.demo_proj", fake_channel)
        ), patch.object(
            single_url_module, "_dispatch_via_crawler_pool", return_value=fake_dispatch
        ), patch.object(
            single_url_module, "_validate_crawler_output_docs", return_value={"passed_ids": [999], "failed_ids": [], "reasons": {}}
        ):
            result = single_url_module.ingest_single_url(
                url="https://www.google.com/search?q=test",
                query_terms=["test"],
                strict_mode=False,
                search_options={"fallback_on_insufficient": False},
            )

        self.assertEqual(result.get("status"), "success")
        self.assertGreaterEqual(int(result.get("inserted") or 0), 1)
        self.assertEqual(result.get("handler_allocation", {}).get("handler_used"), "crawler_pool")
        self.assertEqual(result.get("handler_allocation", {}).get("matched_channel_key"), "crawler.demo_proj")
        self.assertEqual(result.get("page_gate", {}).get("reason"), "search_template_results_insufficient")
        self.assertEqual(fake_fetch.call_count, 1)
        self.assertEqual(fake_extract.call_count, 1)
        self.assertEqual(complete_job.call_count, 1)

    def test_ingest_single_url_crawler_pool_low_quality_keeps_degraded(self):
        fake_job_id = 654
        fake_fetch = unittest.mock.Mock(return_value=("<html></html>", unittest.mock.Mock(status_code=200)))
        fake_extract = unittest.mock.Mock(return_value={"items": [], "result_count": 0, "summary_text": "", "snippet_chars": 0})
        fake_channel = {"channel_key": "crawler.demo_proj", "provider_type": "scrapy", "enabled": True, "default_params": {}}
        fake_dispatch = {
            "inserted": 1,
            "updated": 0,
            "skipped": 0,
            "provider_job_id": "job-low",
            "provider_status": "ok",
            "provider_type": "scrapy",
            "attempt_count": 1,
            "output_ingest": {"import_result": {"items": [{"doc_id": 1001, "status": "ok"}]}},
        }

        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ) as complete_job, patch.object(single_url_module, "fetch_html", fake_fetch), patch.object(
            single_url_module, "_extract_search_results", fake_extract
        ), patch.object(
            single_url_module, "_pick_crawler_channel", return_value=("crawler.demo_proj", fake_channel)
        ), patch.object(
            single_url_module, "_dispatch_via_crawler_pool", return_value=fake_dispatch
        ), patch.object(
            single_url_module, "_validate_crawler_output_docs", return_value={"passed_ids": [], "failed_ids": [1001], "reasons": {"script_shell_like": 1}}
        ):
            result = single_url_module.ingest_single_url(
                url="https://www.google.com/search?q=test",
                query_terms=["test"],
                strict_mode=False,
            )

        self.assertEqual(result.get("status"), "degraded_success")
        self.assertEqual(result.get("inserted"), 0)
        self.assertIn("crawler_pool_low_quality_output", result.get("degradation_flags", []))
        self.assertEqual(result.get("handler_allocation", {}).get("crawler_quality_reasons", {}).get("script_shell_like"), 1)
        self.assertEqual(complete_job.call_count, 1)

    def test_extract_github_structured_content_from_shell_page(self):
        html = """
        <html>
          <head>
            <meta property="og:title" content="owner/repo" />
            <meta name="description" content="Repository for embodied robotics agents." />
          </head>
          <body>Navigation Menu Search or jump to Pull requests Issues Stargazers</body>
        </html>
        """
        raw_content = "Navigation Menu Search or jump to Stargazers 123 stars 45 forks"
        out = single_url_module._extract_github_structured_content(
            "https://github.com/owner/repo/stargazers",
            html,
            raw_content,
        )
        self.assertIsInstance(out, dict)
        self.assertEqual(out.get("metadata", {}).get("repo_owner"), "owner")
        self.assertEqual(out.get("metadata", {}).get("repo_name"), "repo")
        self.assertEqual(out.get("metadata", {}).get("repo_page_type"), "stargazers")
        self.assertIn("Repository: owner/repo", str(out.get("content")))
        self.assertIn("Stars: 123", str(out.get("content")))

    def test_force_crawler_domain_for_reddit(self):
        self.assertTrue(single_url_module._is_force_crawler_domain("https://www.reddit.com/search?q=robotics"))
        self.assertFalse(single_url_module._is_force_crawler_domain("https://example.com/search?q=robotics"))

    def test_extract_search_results_auto_config_decodes_redirect_links(self):
        html = """
        <html><body>
          <div class="g">
            <h3><a href="/url?q=https%3A%2F%2Fexample.com%2Fposts%2F1">Example One Result</a></h3>
            <div class="VwiC3b">snippet one</div>
          </div>
          <div class="g">
            <h3><a href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fnews%2F2">Example Two Result</a></h3>
            <div class="VwiC3b">snippet two</div>
          </div>
        </body></html>
        """
        cfg = single_url_module._build_search_auto_config("https://www.google.com/search?q=robotics", ["robotics"])
        payload = single_url_module._extract_search_results(
            "https://www.google.com/search?q=robotics",
            html,
            auto_config=cfg,
        )
        urls = [str(x.get("url")) for x in (payload.get("items") or [])]
        self.assertEqual(int(payload.get("result_count") or 0), 2)
        self.assertIn("https://example.com/posts/1", urls)
        self.assertIn("https://example.org/news/2", urls)
        self.assertEqual(int((payload.get("auto_config") or {}).get("target_candidates") or 0), 6)

    def test_extract_search_results_auto_config_filters_low_value_domains(self):
        html = """
        <html><body>
          <div class="g">
            <h3><a href="https://news.google.com/articles/abc">News Google Wrapper</a></h3>
          </div>
          <div class="g">
            <h3><a href="https://example.com/research/embodied-ai-report">Embodied AI Research Report</a></h3>
          </div>
        </body></html>
        """
        cfg = single_url_module._build_search_auto_config("https://www.google.com/search?q=embodied+ai", ["embodied ai"])
        payload = single_url_module._extract_search_results(
            "https://www.google.com/search?q=embodied+ai",
            html,
            auto_config=cfg,
        )
        items = payload.get("items") or []
        self.assertEqual(int(payload.get("result_count") or 0), 1)
        self.assertEqual(str(items[0].get("url")), "https://example.com/research/embodied-ai-report")

    def test_select_search_expand_urls_prefers_domain_diversity(self):
        items = [
            {"url": "https://a.example.com/p1"},
            {"url": "https://a.example.com/p2"},
            {"url": "https://b.example.com/p3"},
            {"url": "https://c.example.com/p4"},
        ]
        selected = single_url_module._select_search_expand_urls(items, limit=3, prefer_domain_diversity=True)
        self.assertEqual(len(selected), 3)
        domains = [single_url_module._domain_of_candidate(x) for x in selected]
        self.assertEqual(len(set(domains)), 3)

    def test_classify_search_expand_child_outcome_breakdown(self):
        self.assertEqual(
            single_url_module._classify_search_expand_child_outcome(
                {"inserted_valid": 0, "degradation_flags": ["document_already_exists"]}
            ),
            "duplicate",
        )
        self.assertEqual(
            single_url_module._classify_search_expand_child_outcome(
                {"inserted_valid": 0, "degradation_flags": ["fetch_failed"]}
            ),
            "fetch_failed",
        )
        self.assertEqual(
            single_url_module._classify_search_expand_child_outcome(
                {"inserted_valid": 0, "degradation_flags": ["low_value_page:nav"]}
            ),
            "quality_rejected",
        )
        self.assertEqual(
            single_url_module._classify_search_expand_child_outcome(
                {"inserted_valid": 0, "degradation_flags": []}
            ),
            "other",
        )
        self.assertEqual(
            single_url_module._classify_search_expand_child_outcome(
                {"inserted_valid": 0, "degradation_flags": ["light_filter_rejected:static_asset_url"]}
            ),
            "quality_rejected",
        )

    def test_preprocess_content_for_quality_filters_noise_and_keeps_meaningful_text(self):
        html = """
        <html>
          <head>
            <title>Embodied Robotics Weekly</title>
            <meta name="description" content="Weekly report about embodied robotics products and deployments." />
          </head>
          <body>
            <main><h1>Embodied Robotics Weekly Update</h1></main>
          </body>
        </html>
        """
        noisy = "\n".join(
            [
                "Skip to content",
                "Privacy Terms cookie settings",
                "window.test=1; document.cookie='a=b'; function(){return 1};",
                "This week we observed new embodied robotics deployments in healthcare and logistics.",
            ]
        )
        cleaned = single_url_module._preprocess_content_for_quality(
            url="https://example.com/report",
            title="Embodied Robotics Weekly",
            html=html,
            content=noisy,
        )
        self.assertIn("embodied robotics", cleaned.lower())
        self.assertNotIn("privacy terms cookie", cleaned.lower())

    def test_provenance_dirty_decision_blocks_github_api_intermediate(self):
        blocked, reason, diagnostics = single_url_module._provenance_dirty_decision(
            url="https://api.github.com/repos/openai/openai-python",
            title="repos/openai (openai-python) - GitHub",
            content="{}",
            domain_specific_metadata={},
        )
        self.assertTrue(blocked)
        self.assertEqual(reason, "github_api_intermediate")
        self.assertEqual(str(diagnostics.get("domain")), "api.github.com")

    def test_ingest_single_url_blocks_mojibake_script_shell(self):
        fake_job_id = 777
        fake_html = "<html><head><title>èªå¨é©¾é©¶ææ¯</title></head><body></body></html>"
        fake_content = (
            "window.test=1; document.cookie='a=b'; var x=1; function(){return 1}; "
            "sourcemappingurl=abc; " * 20
        )
        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ) as complete_job, patch.object(
            single_url_module, "fetch_html", return_value=(fake_html, unittest.mock.Mock(status_code=200))
        ), patch.object(
            single_url_module, "_extract_text_from_html", return_value=fake_content
        ):
            result = single_url_module.ingest_single_url(
                url="https://finance.sina.com.cn/jjxw/2025-08-21/doc-infmtwfc4390325.shtml",
                query_terms=["无人驾驶"],
                strict_mode=False,
            )
        self.assertEqual(result.get("status"), "degraded_success")
        self.assertEqual(result.get("inserted"), 0)
        self.assertEqual(result.get("rejection_breakdown", {}).get("mojibake_script_shell"), 1)
        self.assertEqual(result.get("page_gate", {}).get("page_type"), "provenance_intermediate")
        self.assertEqual(complete_job.call_count, 1)

    def test_provenance_dirty_decision_blocks_ddg_intermediate(self):
        blocked, reason, diagnostics = single_url_module._provenance_dirty_decision(
            url="https://html.duckduckgo.com/html/?q=Tesla",
            title="Tesla at DuckDuckGo",
            content="search shell",
            domain_specific_metadata={},
        )
        self.assertTrue(blocked)
        self.assertEqual(reason, "ddg_intermediate_page")
        self.assertEqual(str(diagnostics.get("domain")), "html.duckduckgo.com")

    def test_pre_write_block_includes_reason_flag(self):
        fake_job_id = 778
        fake_html = "<html><head><title>Template Page</title></head><body>placeholder</body></html>"
        fake_gate = GateDecision(
            accepted=False,
            blocked=True,
            reason="content_js_template_shell",
            quality_score=0.0,
            diagnostics={"js_template_hits": 8},
        )
        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ), patch.object(
            single_url_module, "fetch_html", return_value=(fake_html, unittest.mock.Mock(status_code=200))
        ), patch.object(
            single_url_module, "_classify_page_type", return_value=("detail", False, None)
        ), patch.object(
            single_url_module, "content_quality_check", return_value=fake_gate
        ):
            result = single_url_module.ingest_single_url(
                url="https://example.com/template",
                query_terms=["test"],
                strict_mode=False,
            )
        flags = list(result.get("degradation_flags") or [])
        self.assertIn("content_js_template_shell", flags)
        self.assertIn("content_gate_rejected:content_js_template_shell", flags)

    def test_evaluate_light_filter_rejects_static_asset_url(self):
        options = single_url_module._normalize_search_options({})
        payload = single_url_module._evaluate_light_filter(
            url="https://example.com/static/app.js",
            title="app.js",
            snippet="",
            source_domain="example.com",
            http_status=200,
            entry_type="detail",
            options=options,
        )
        self.assertEqual(payload.get("filter_decision"), "reject")
        self.assertEqual(payload.get("filter_reason_code"), "static_asset_url")
        self.assertFalse(bool(payload.get("keep_for_vectorization")))

    def test_normalize_search_options_light_filter_defaults_and_clamp(self):
        defaults = single_url_module._normalize_search_options(None)
        self.assertTrue(bool(defaults.get("light_filter_enabled")))
        self.assertEqual(int(defaults.get("light_filter_min_score") or 0), 30)
        self.assertTrue(bool(defaults.get("light_filter_reject_static_assets")))
        self.assertTrue(bool(defaults.get("light_filter_reject_search_noise_domain")))
        self.assertFalse(bool(defaults.get("allow_template_as_document")))

        custom = single_url_module._normalize_search_options(
            {
                "light_filter_enabled": False,
                "light_filter_min_score": 999,
                "light_filter_reject_static_assets": False,
                "light_filter_reject_search_noise_domain": False,
                "allow_template_as_document": True,
            }
        )
        self.assertFalse(bool(custom.get("light_filter_enabled")))
        self.assertEqual(int(custom.get("light_filter_min_score") or 0), 100)
        self.assertFalse(bool(custom.get("light_filter_reject_static_assets")))
        self.assertFalse(bool(custom.get("light_filter_reject_search_noise_domain")))
        self.assertTrue(bool(custom.get("allow_template_as_document")))

    def test_apply_light_filter_fields_when_not_run(self):
        result = {"status": "degraded_success"}
        out = single_url_module._apply_light_filter_fields(result, None)
        self.assertEqual(out.get("filter_decision"), "not_run")
        self.assertEqual(out.get("filter_reason_code"), "not_evaluated")
        self.assertEqual(int(out.get("filter_score") or 0), 100)
        self.assertTrue(bool(out.get("keep_for_vectorization")))
        self.assertEqual((out.get("light_filter") or {}).get("filter_decision"), "not_run")

    def test_ingest_single_url_light_filter_rejects_and_emits_fields(self):
        fake_job_id = 901
        fake_html = "<html><head><title>app.js</title></head><body>var app=1;</body></html>"
        allowed_gate = GateDecision(
            accepted=True,
            blocked=False,
            reason="ok",
            quality_score=100.0,
            diagnostics={},
        )
        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ) as complete_job, patch.object(
            single_url_module, "fetch_html", return_value=(fake_html, unittest.mock.Mock(status_code=200))
        ), patch.object(
            single_url_module, "_extract_text_from_html", return_value="var app=1;"
        ), patch.object(
            single_url_module, "url_policy_check", return_value=allowed_gate
        ):
            result = single_url_module.ingest_single_url(
                url="https://example.com/static/app.js",
                query_terms=["robotics"],
                strict_mode=False,
            )
        self.assertEqual(result.get("status"), "degraded_success")
        self.assertEqual(result.get("page_gate", {}).get("page_type"), "light_filter")
        self.assertEqual(result.get("filter_decision"), "reject")
        self.assertEqual(result.get("filter_reason_code"), "static_asset_url")
        self.assertFalse(bool(result.get("keep_for_vectorization")))
        self.assertIn("light_filter_rejected:static_asset_url", list(result.get("degradation_flags") or []))
        self.assertEqual(result.get("reason_code"), "static_asset_url")
        self.assertEqual(result.get("reason_category"), "technical")
        self.assertEqual((result.get("stage_context") or {}).get("run_id"), fake_job_id)
        self.assertEqual((result.get("stage_context") or {}).get("reason_code"), "static_asset_url")
        self.assertEqual(complete_job.call_count, 1)

    def test_ingest_single_url_pre_fetch_gate_exposes_stage_contract_fields(self):
        fake_job_id = 990
        fake_decision = GateDecision(
            accepted=False,
            blocked=True,
            reason="url_policy_low_value_endpoint",
            quality_score=0.0,
            diagnostics={"matched_path_keyword": "/search"},
        )
        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ), patch.object(single_url_module, "url_policy_check", return_value=fake_decision), patch.object(
            single_url_module, "fetch_html"
        ) as fetch_html:
            result = single_url_module.ingest_single_url(
                url="https://example.com/search?q=robotics",
                query_terms=["robotics"],
                strict_mode=False,
                search_options={"frontdoor_enabled": True},
            )

        self.assertEqual(result.get("status"), "degraded_success")
        self.assertTrue(str(result.get("reason_code") or "").strip())
        self.assertEqual(result.get("reason_category"), "policy")
        stage_context = result.get("stage_context") or {}
        self.assertEqual(stage_context.get("run_id"), fake_job_id)
        self.assertEqual(stage_context.get("reason_code"), result.get("reason_code"))
        self.assertTrue(any(str(flag).startswith("url_gate_rejected:") for flag in list(stage_context.get("degradation_flags") or [])))
        frontdoor_meta = ((result.get("frontdoor_envelope") or {}).get("meta") or {})
        self.assertIn("retry_count_by_reason", frontdoor_meta)
        self.assertIn("retry_count_by_class", frontdoor_meta)
        self.assertIn("retryable", frontdoor_meta)
        self.assertEqual((frontdoor_meta.get("retry_count_by_class") or {}).get("transient"), 0)
        self.assertEqual((frontdoor_meta.get("retry_count_by_class") or {}).get("permanent"), 0)
        self.assertFalse(bool(frontdoor_meta.get("retryable")))
        self.assertEqual(fetch_html.call_count, 0)

    def test_ingest_single_url_light_filter_disabled_allows_pipeline_to_continue(self):
        fake_job_id = 902
        fake_html = "<html><head><title>app.js</title></head><body>placeholder</body></html>"
        allowed_gate = GateDecision(
            accepted=True,
            blocked=False,
            reason="ok",
            quality_score=100.0,
            diagnostics={},
        )
        strict_fail_gate = GateDecision(
            accepted=True,
            blocked=False,
            reason="ok",
            quality_score=100.0,
            diagnostics={},
        )
        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ) as complete_job, patch.object(
            single_url_module, "fetch_html", return_value=(fake_html, unittest.mock.Mock(status_code=200))
        ), patch.object(
            single_url_module, "_extract_text_from_html", return_value=("meaningful robotics insight " * 80)
        ), patch.object(
            single_url_module, "_classify_page_type", return_value=("detail", False, None)
        ), patch.object(
            single_url_module, "url_policy_check", return_value=allowed_gate
        ), patch.object(
            single_url_module, "content_quality_check", return_value=strict_fail_gate
        ), patch.object(
            single_url_module._EXTRACTION_APP, "extract_structured_enriched", return_value={}
        ):
            result = single_url_module.ingest_single_url(
                url="https://example.com/static/app.js",
                query_terms=["robotics"],
                strict_mode=True,
                search_options={"light_filter_enabled": False},
            )
        self.assertEqual(result.get("status"), "failed")
        self.assertIn("strict_mode_quality_gate", list(result.get("degradation_flags") or []))
        self.assertEqual(result.get("filter_decision"), "allow")
        self.assertEqual(result.get("filter_reason_code"), "light_filter_disabled")
        self.assertTrue(bool(result.get("keep_for_vectorization")))
        self.assertNotEqual(result.get("page_gate", {}).get("page_type"), "light_filter")
        self.assertEqual(complete_job.call_count, 1)

    def test_collect_urls_from_list_uses_single_url_pipeline(self):
        fake_module = types.ModuleType("app.services.ingest.single_url")
        fake_module.ingest_single_url = Mock(return_value={"status": "success", "inserted": 1, "skipped": 0, "document_id": 101, "degradation_flags": []})

        with patch.dict(sys.modules, {"app.services.ingest.single_url": fake_module}), patch.object(
            url_pool_module, "_annotate_url_pool_context"
        ) as annotate_ctx:
            result = url_pool_module.collect_urls_from_list(
                ["https://a.example.com/path/1", "https://a.example.com/search?q=robotics"],
                project_key=None,
                query_terms=["robotics"],
            )

        call_urls = [c.kwargs.get("url") for c in fake_module.ingest_single_url.call_args_list]
        self.assertGreaterEqual(len(call_urls), 3)
        self.assertEqual(call_urls[0], "https://a.example.com/")
        self.assertIn("https://a.example.com/path/1", call_urls)
        self.assertIn("https://a.example.com/search?q=robotics", call_urls)
        self.assertGreaterEqual(int(result.get("debug", {}).get("site_seed_count") or 0), 1)
        self.assertGreaterEqual(annotate_ctx.call_count, 3)

    def test_collect_urls_from_pool_annotates_pool_context_from_single_url_result(self):
        fake_module = types.ModuleType("app.services.ingest.single_url")
        fake_module.ingest_single_url = Mock(
            return_value={
                "status": "success",
                "inserted": 1,
                "skipped": 0,
                "document_id": None,
                "degradation_flags": [],
                "handler_allocation": {"handler_used": "crawler_pool", "matched_channel_key": "crawler.demo"},
                "crawler_dispatch": {"valid_output_doc_ids": [301, 302]},
            }
        )
        fake_items = [
            {
                "id": 1,
                "url": "https://news.example.com/post/1",
                "scope": "effective",
                "source": "search",
                "domain": "news.example.com",
                "source_ref": "q=robotics",
            }
        ]

        with patch.dict(sys.modules, {"app.services.ingest.single_url": fake_module}), patch.object(
            url_pool_module, "list_urls", return_value=(fake_items, 1)
        ), patch.object(url_pool_module, "_annotate_url_pool_context") as annotate_ctx:
            result = url_pool_module.collect_urls_from_pool(
                scope="effective",
                project_key=None,
                limit=20,
                query_terms=["robotics"],
            )

        self.assertGreaterEqual(int(result.get("inserted") or 0), 1)
        self.assertGreaterEqual(fake_module.ingest_single_url.call_count, 2)
        call_urls = [c.kwargs.get("url") for c in fake_module.ingest_single_url.call_args_list]
        self.assertEqual(call_urls[0], "https://news.example.com/")
        self.assertIn("https://news.example.com/post/1", call_urls)
        self.assertGreaterEqual(annotate_ctx.call_count, 1)
        kwargs = annotate_ctx.call_args.kwargs
        self.assertEqual(kwargs.get("doc_ids"), [301, 302])
        self.assertEqual(kwargs.get("context", {}).get("mode"), "pool")
        self.assertEqual(kwargs.get("context", {}).get("scope"), "effective")
        self.assertEqual(kwargs.get("context", {}).get("source"), "search")

    def test_collect_urls_from_list_parallel_workers_emits_debug_and_aggregates(self):
        fake_module = types.ModuleType("app.services.ingest.single_url")
        fake_module.ingest_single_url = Mock(
            return_value={"status": "success", "inserted": 1, "inserted_valid": 1, "skipped": 0, "document_id": 101, "degradation_flags": []}
        )

        with patch.dict(sys.modules, {"app.services.ingest.single_url": fake_module}), patch.object(
            url_pool_module, "_annotate_url_pool_context"
        ):
            result = url_pool_module.collect_urls_from_list(
                [
                    "https://a.example.com/path/1",
                    "https://a.example.com/path/2",
                    "https://a.example.com/search?q=robotics",
                ],
                project_key=None,
                query_terms=["robotics"],
                extra_params={"single_url_parallel_workers": 4, "single_url_parallel_batch_size": 2, "single_url_dispatch_mode": "thread"},
            )

        self.assertEqual(result.get("debug", {}).get("dispatch_mode"), "thread")
        self.assertGreaterEqual(int(result.get("debug", {}).get("parallel_workers") or 0), 2)
        self.assertEqual(int(result.get("inserted") or 0), int(fake_module.ingest_single_url.call_count))
        self.assertEqual(int(result.get("queued") or 0), 0)
        self.assertEqual(result.get("single_write_workflow"), "single_url")

    def test_resolve_parallel_workers_uses_auto_default_when_not_provided(self):
        with patch.object(url_pool_module, "_DEFAULT_PARALLEL_WORKERS", 6):
            self.assertEqual(url_pool_module._resolve_parallel_workers(extra_params=None, target_count=10), 6)
            self.assertEqual(url_pool_module._resolve_parallel_workers(extra_params=None, target_count=3), 3)

    def test_collect_urls_from_list_can_disable_site_seed_expansion(self):
        fake_module = types.ModuleType("app.services.ingest.single_url")
        fake_module.ingest_single_url = Mock(
            return_value={"status": "success", "inserted": 1, "inserted_valid": 1, "skipped": 0, "document_id": 101, "degradation_flags": []}
        )

        with patch.dict(sys.modules, {"app.services.ingest.single_url": fake_module}), patch.object(
            url_pool_module, "_annotate_url_pool_context"
        ):
            result = url_pool_module.collect_urls_from_list(
                [
                    "https://a.example.com/path/1",
                    "https://a.example.com/search?q=robotics",
                ],
                project_key=None,
                query_terms=["robotics"],
                extra_params={"disable_site_seed_expansion": True},
            )

        call_urls = [c.kwargs.get("url") for c in fake_module.ingest_single_url.call_args_list]
        self.assertEqual(len(call_urls), 2)
        self.assertIn("https://a.example.com/path/1", call_urls)
        self.assertIn("https://a.example.com/search?q=robotics", call_urls)
        self.assertEqual(int(result.get("debug", {}).get("site_seed_count") or 0), 0)
        self.assertTrue(bool(result.get("debug", {}).get("disable_site_seed_expansion")))

    def test_collect_urls_from_list_site_only_mode_uses_only_site_seeds(self):
        fake_module = types.ModuleType("app.services.ingest.single_url")
        fake_module.ingest_single_url = Mock(
            return_value={"status": "success", "inserted": 1, "inserted_valid": 1, "skipped": 0, "document_id": 101, "degradation_flags": []}
        )

        with patch.dict(sys.modules, {"app.services.ingest.single_url": fake_module}), patch.object(
            url_pool_module, "_annotate_url_pool_context"
        ):
            result = url_pool_module.collect_urls_from_list(
                [
                    "https://a.example.com/path/1",
                    "https://a.example.com/search?q=robotics",
                ],
                project_key=None,
                query_terms=["robotics"],
                extra_params={"single_url_target_mode": "site_only"},
            )

        call_urls = [str(c.kwargs.get("url") or "") for c in fake_module.ingest_single_url.call_args_list]
        self.assertIn("https://a.example.com/", call_urls)
        self.assertNotIn("https://a.example.com/path/1", call_urls)
        self.assertEqual(result.get("debug", {}).get("target_mode"), "site_only")

    def test_collect_urls_from_list_defaults_to_site_then_detail_target_mode(self):
        fake_module = types.ModuleType("app.services.ingest.single_url")
        fake_module.ingest_single_url = Mock(
            return_value={"status": "success", "inserted": 1, "inserted_valid": 1, "skipped": 0, "document_id": 101, "degradation_flags": []}
        )
        with patch.dict(sys.modules, {"app.services.ingest.single_url": fake_module}), patch.object(
            url_pool_module, "_annotate_url_pool_context"
        ):
            result = url_pool_module.collect_urls_from_list(
                [
                    "https://a.example.com/path/1",
                    "https://a.example.com/search?q=robotics",
                ],
                project_key=None,
                query_terms=["robotics"],
            )

        call_urls = [str(c.kwargs.get("url") or "") for c in fake_module.ingest_single_url.call_args_list]
        self.assertIn("https://a.example.com/", call_urls)
        self.assertIn("https://a.example.com/path/1", call_urls)
        self.assertEqual(result.get("debug", {}).get("target_mode"), "site_then_detail")

    def test_collect_urls_from_list_async_dispatch_queues_celery_tasks(self):
        class _AsyncResult:
            def __init__(self, task_id: str):
                self.id = task_id

        class _TaskStub:
            def __init__(self):
                self.calls = 0

            def delay(self, *_args, **_kwargs):
                self.calls += 1
                return _AsyncResult(f"task-{self.calls}")

        fake_task = _TaskStub()
        fake_tasks_module = types.ModuleType("app.services.tasks")
        fake_tasks_module.task_ingest_single_url = fake_task

        fake_module = types.ModuleType("app.services.ingest.single_url")
        fake_module.ingest_single_url = Mock(return_value={"status": "success", "inserted": 1, "skipped": 0})

        with patch.dict(
            sys.modules,
            {
                "app.services.tasks": fake_tasks_module,
                "app.services.ingest.single_url": fake_module,
            },
        ), patch.object(url_pool_module, "_annotate_url_pool_context"):
            result = url_pool_module.collect_urls_from_list(
                ["https://a.example.com/path/1", "https://a.example.com/search?q=robotics"],
                project_key=None,
                query_terms=["robotics"],
                extra_params={"single_url_dispatch_mode": "celery_async"},
            )

        self.assertEqual(result.get("debug", {}).get("dispatch_mode"), "celery_async")
        self.assertGreaterEqual(int(result.get("queued") or 0), 1)
        self.assertEqual(result.get("single_write_workflow"), "single_url_async")
        self.assertEqual(fake_module.ingest_single_url.call_count, 0)
        details = list(result.get("debug", {}).get("url_details") or [])
        self.assertTrue(details)
        self.assertTrue(any(str(x.get("task_id") or "").startswith("task-") for x in details))

    def test_ingest_single_url_frontdoor_high_js_prefers_crawler_before_native_fetch(self):
        fake_job_id = 1201
        fake_channel = {"channel_key": "crawler.demo", "provider_type": "scrapy", "enabled": True, "default_params": {}}
        allowed_gate = GateDecision(
            accepted=True,
            blocked=False,
            reason="ok",
            quality_score=100.0,
            diagnostics={},
        )
        fake_dispatch = {
            "inserted": 1,
            "updated": 0,
            "skipped": 0,
            "provider_job_id": "job-frontdoor",
            "provider_status": "ok",
            "provider_type": "scrapy",
            "attempt_count": 1,
            "output_ingest": {"import_result": {"items": [{"doc_id": 901, "status": "ok"}]}},
        }
        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ) as complete_job, patch.object(
            single_url_module, "url_policy_check", return_value=allowed_gate
        ), patch.object(
            single_url_module, "_pick_crawler_channel", return_value=("crawler.demo", fake_channel)
        ), patch.object(
            single_url_module, "_dispatch_via_crawler_pool", return_value=fake_dispatch
        ), patch.object(
            single_url_module, "_validate_crawler_output_docs", return_value={"passed_ids": [901], "failed_ids": [], "reasons": {}}
        ), patch.object(
            single_url_module, "fetch_html"
        ) as fetch_html:
            result = single_url_module.ingest_single_url(
                url="https://x.com/openai/status/123",
                query_terms=["openai"],
                strict_mode=False,
                frontdoor_options={"enabled": True},
            )

        self.assertEqual(result.get("status"), "success")
        self.assertEqual(result.get("handler_allocation", {}).get("handler_used"), "crawler_pool")
        self.assertEqual(result.get("handler_allocation", {}).get("frontdoor_route"), "crawler_browse")
        self.assertEqual(fetch_html.call_count, 0)
        self.assertEqual(complete_job.call_count, 1)

    def test_ingest_single_url_frontdoor_search_shell_route_skips_crawler_fallback(self):
        fake_job_id = 1202
        allowed_gate = GateDecision(
            accepted=True,
            blocked=False,
            reason="ok",
            quality_score=100.0,
            diagnostics={},
        )
        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ) as complete_job, patch.object(
            single_url_module, "url_policy_check", return_value=allowed_gate
        ), patch.object(
            single_url_module, "fetch_html", return_value=("<html></html>", unittest.mock.Mock(status_code=200))
        ), patch.object(
            single_url_module, "_extract_search_results", return_value={"items": [], "result_count": 0, "summary_text": "", "snippet_chars": 0}
        ), patch.object(
            single_url_module, "_pick_crawler_channel"
        ) as pick_crawler:
            result = single_url_module.ingest_single_url(
                url="https://www.google.com/search?q=robotics",
                query_terms=["robotics"],
                strict_mode=False,
                search_options={"fallback_on_insufficient": False},
                frontdoor_options={"enabled": True},
            )

        self.assertEqual(result.get("status"), "degraded_success")
        self.assertEqual(result.get("page_gate", {}).get("page_type"), "search_shell")
        self.assertEqual(result.get("handler_allocation", {}).get("frontdoor_route"), "search_shell")
        self.assertEqual(pick_crawler.call_count, 0)
        self.assertEqual(complete_job.call_count, 1)

    def test_collect_urls_from_list_frontdoor_injects_per_url_route_hints(self):
        fake_module = types.ModuleType("app.services.ingest.single_url")
        fake_module.ingest_single_url = Mock(
            return_value={"status": "success", "inserted": 1, "inserted_valid": 1, "skipped": 0, "document_id": 101, "degradation_flags": []}
        )
        with patch.dict(sys.modules, {"app.services.ingest.single_url": fake_module}), patch.object(
            url_pool_module, "_annotate_url_pool_context"
        ):
            url_pool_module.collect_urls_from_list(
                [
                    "https://x.com/openai/status/1",
                    "https://www.google.com/search?q=robotics",
                ],
                project_key=None,
                query_terms=["robotics"],
                extra_params={"single_url_frontdoor_enabled": True},
            )

        calls = list(fake_module.ingest_single_url.call_args_list)
        crawler_hint_seen = False
        search_shell_hint_seen = False
        for call in calls:
            kwargs = call.kwargs
            call_url = str(kwargs.get("url") or "")
            search_options = dict(kwargs.get("search_options") or {})
            if "x.com" in call_url:
                crawler_hint_seen = crawler_hint_seen or (
                    str(search_options.get("frontdoor_route_hint")) == "crawler_browse"
                    and bool(search_options.get("frontdoor_prefers_crawler"))
                )
            if "/search" in call_url:
                search_shell_hint_seen = search_shell_hint_seen or (
                    str(search_options.get("frontdoor_route_hint")) == "search_shell"
                    and bool(search_options.get("frontdoor_prefers_search_shell"))
                )
        self.assertTrue(crawler_hint_seen)
        self.assertTrue(search_shell_hint_seen)


if __name__ == "__main__":
    unittest.main()
