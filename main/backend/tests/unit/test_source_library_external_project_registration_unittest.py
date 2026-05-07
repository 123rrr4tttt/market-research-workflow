from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.source_library.external_project_registration import (
    collect_external_project_context,
    synthesize_external_project_item,
    synthesize_external_project_manifest,
)


class ExternalProjectRegistrationUnitTestCase(unittest.TestCase):
    def test_collect_external_project_context_uses_github_api_when_repo_link(self) -> None:
        def _fake_get_json(url: str, **kwargs):  # noqa: ANN001
            if url.endswith("/repos/example/demo"):
                return {
                    "full_name": "example/demo",
                    "description": "Demo repo",
                    "default_branch": "main",
                    "homepage": "https://demo.example.com",
                }
            if url.endswith("/repos/example/demo/readme"):
                return {
                    "content": "IyBEZW1vIFJFQURNRQoKaHR0cHM6Ly9kZW1vLmV4YW1wbGUuY29tL2ZlZWQueG1sCmh0dHBzOi8vYXBpLmRlbW8uZXhhbXBsZS5jb20vc2VhcmNo",
                    "encoding": "base64",
                }
            return None

        with patch("app.services.source_library.external_project_registration.default_http_client.get_json", side_effect=_fake_get_json):
            context = collect_external_project_context(project_link="https://github.com/example/demo", hints={"query_terms": ["ai"]})

        self.assertEqual(context["source"], "github")
        self.assertEqual(context["repo"]["owner"], "example")
        self.assertEqual(context["repo"]["name"], "demo")
        self.assertEqual(context["hints"]["query_terms"], ["ai"])
        self.assertEqual(context["evidence"][0]["kind"], "github_repo")
        self.assertEqual(context["evidence"][1]["kind"], "readme")
        self.assertEqual(context["endpoint_candidates"][0]["execution_mode"], "rss_feed")
        self.assertEqual(context["endpoint_candidates"][0]["runner_ref"], "https://demo.example.com/feed.xml")
        self.assertIn("http_api", context["preferred_execution_modes"])

    def test_collect_external_project_context_extracts_generic_endpoint_candidates_from_html(self) -> None:
        html = """
        <html><body>
          <a href="/feed.xml">Feed</a>
          <a href="https://demo.example.com/sitemap.xml">Sitemap</a>
          <a href="https://api.demo.example.com/search">API</a>
        </body></html>
        """

        with patch("app.services.source_library.external_project_registration.default_http_client.get_text", return_value=html):
            context = collect_external_project_context(project_link="https://demo.example.com/docs", hints=None)

        self.assertEqual(context["source"], "generic")
        self.assertEqual(context["endpoint_candidates"][0]["execution_mode"], "rss_feed")
        self.assertEqual(context["endpoint_candidates"][0]["runner_ref"], "https://demo.example.com/feed.xml")
        self.assertIn("sitemap", context["preferred_execution_modes"])
        self.assertIn("http_api", context["preferred_execution_modes"])

    def test_synthesize_external_project_manifest_uses_workflow_llm_skill(self) -> None:
        llm_json = {
            "contract_version": "external_item.manifest.v1",
            "item_key": "external.github.demo",
            "display_name": "demo",
            "project_link": "https://github.com/example/demo",
            "source_kind": "feed_aggregator",
            "source_scope": "developer_news",
            "capabilities": {
                "candidate_urls": True,
                "article_metadata": True,
                "article_body": False,
                "pdf_artifact": False,
            },
            "accepted_inputs": {
                "query_terms": True,
                "urls": False,
                "domains": False,
                "date_range": False,
                "max_items": True,
            },
            "execution_mode": "rss_feed",
            "runner_ref": "https://example.com/feed.xml",
            "normalization": {
                "record_kind": "article_metadata",
                "frontdoor_strategy": "records_only_defer",
            },
            "limits": {
                "default_max_items": 20,
                "max_items_cap": 100,
                "request_timeout_ms": 30000,
            },
            "refresh_policy": {
                "manifest_ttl_minutes": 60,
                "probe_ttl_minutes": 1440,
            },
            "provenance": {
                "discovered_by": "llm_probe",
                "source_refs": ["https://github.com/example/demo"],
            },
        }
        with patch(
            "app.services.source_library.external_project_registration.invoke_skill",
            return_value={"result": {"text": json.dumps(llm_json)}},
        ) as invoke_skill:
            manifest = synthesize_external_project_manifest(
                project_link="https://github.com/example/demo",
                item_key="external.github.demo",
                display_name="demo",
                project_context={"source": "github", "evidence": []},
                hints={"query_terms": ["ai"]},
            )

        invoke_skill.assert_called_once()
        self.assertEqual(manifest["item_key"], "external.github.demo")
        self.assertEqual(manifest["execution_mode"], "rss_feed")

    def test_synthesize_external_project_manifest_uses_deterministic_context_probe_when_high_confidence_exists(self) -> None:
        project_context = {
            "source": "github",
            "evidence": [{"kind": "readme", "content": "demo"}],
            "endpoint_candidates": [
                {
                    "execution_mode": "rss_feed",
                    "runner_ref": "https://demo.example.com/feed.xml",
                    "reason": "explicit_readme_feed_marker",
                    "confidence": "high",
                }
            ],
        }
        with patch("app.services.source_library.external_project_registration.invoke_skill") as invoke_skill:
            manifest = synthesize_external_project_manifest(
                project_link="https://github.com/example/demo",
                item_key="external.github.demo",
                display_name="demo",
                project_context=project_context,
                hints=None,
            )

        invoke_skill.assert_not_called()
        self.assertEqual(manifest["execution_mode"], "rss_feed")
        self.assertEqual(manifest["runner_ref"], "https://demo.example.com/feed.xml")
        self.assertEqual(manifest["provenance"]["discovered_by"], "context_probe")
        self.assertEqual(manifest["provider_binding"]["provider_key"], "external_project.rss_feed")

    def test_synthesize_external_project_item_rejects_localhost_project_link(self) -> None:
        with self.assertRaisesRegex(ValueError, "project_link must use http or https|cannot target localhost|cannot target private"):
            synthesize_external_project_item(project_link="http://127.0.0.1:8000/demo")

    def test_synthesize_external_project_item_requires_minimum_evidence(self) -> None:
        with patch(
            "app.services.source_library.external_project_registration.collect_external_project_context",
            return_value={"source": "generic", "project_link": "https://example.com/demo", "evidence": []},
        ):
            with self.assertRaisesRegex(ValueError, "enough external project evidence"):
                synthesize_external_project_item(project_link="https://example.com/demo")

    def test_synthesize_external_project_item_attaches_provider_binding_to_registration_context(self) -> None:
        manifest = {
            "contract_version": "external_item.manifest.v1",
            "item_key": "external.example.demo",
            "display_name": "demo",
            "project_link": "https://example.com/demo",
            "source_kind": "feed_aggregator",
            "source_scope": "developer_news",
            "capabilities": {
                "candidate_urls": True,
                "article_metadata": True,
                "article_body": False,
                "pdf_artifact": False,
            },
            "accepted_inputs": {
                "query_terms": True,
                "urls": False,
                "domains": False,
                "date_range": False,
                "max_items": True,
            },
            "execution_mode": "rss_feed",
            "runner_ref": "https://example.com/feed.xml",
            "normalization": {
                "record_kind": "article_metadata",
                "frontdoor_strategy": "records_only_defer",
            },
            "limits": {
                "default_max_items": 20,
                "max_items_cap": 100,
                "request_timeout_ms": 30000,
            },
            "refresh_policy": {
                "manifest_ttl_minutes": 60,
                "probe_ttl_minutes": 1440,
            },
            "provenance": {
                "discovered_by": "manual_registration",
                "source_refs": ["https://example.com/demo"],
            },
        }
        with (
            patch(
                "app.services.source_library.external_project_registration.collect_external_project_context",
                return_value={"source": "generic", "project_link": "https://example.com/demo", "evidence": [{"kind": "page_summary", "content": "demo"}]},
            ),
            patch(
                "app.services.source_library.external_project_registration.synthesize_external_project_manifest",
                return_value={
                    **manifest,
                    "provider_binding": {
                        "registry_version": "external_project.provider_registry.v1",
                        "execution_mode": "rss_feed",
                        "provider_key": "external_project.rss_feed",
                    },
                },
            ),
        ):
            item = synthesize_external_project_item(project_link="https://example.com/demo")

        self.assertEqual(
            item["registration_context"]["provider_binding"]["provider_key"],
            "external_project.rss_feed",
        )

    def test_synthesize_external_project_manifest_rejects_blocked_headers(self) -> None:
        llm_json = {
            "contract_version": "external_item.manifest.v1",
            "item_key": "external.github.demo",
            "display_name": "demo",
            "project_link": "https://github.com/example/demo",
            "source_kind": "http_api",
            "source_scope": "developer_news",
            "capabilities": {
                "candidate_urls": True,
                "article_metadata": True,
                "article_body": False,
                "pdf_artifact": False,
            },
            "accepted_inputs": {
                "query_terms": True,
                "urls": False,
                "domains": False,
                "date_range": False,
                "max_items": True,
            },
            "execution_mode": "http_api",
            "runner_ref": "https://api.example.com/search",
            "normalization": {
                "record_kind": "article_metadata",
                "frontdoor_strategy": "records_only_defer",
            },
            "limits": {
                "default_max_items": 20,
                "max_items_cap": 100,
                "request_timeout_ms": 30000,
            },
            "refresh_policy": {
                "manifest_ttl_minutes": 60,
                "probe_ttl_minutes": 1440,
            },
            "provenance": {
                "discovered_by": "llm_probe",
                "source_refs": ["https://github.com/example/demo"],
            },
            "runtime_config": {
                "method": "GET",
                "headers": {"Authorization": "Bearer secret"},
            },
        }
        with patch(
            "app.services.source_library.external_project_registration.invoke_skill",
            return_value={"result": {"text": json.dumps(llm_json)}},
        ):
            with self.assertRaisesRegex(ValueError, "does not allow header"):
                synthesize_external_project_manifest(
                    project_link="https://github.com/example/demo",
                    item_key="external.github.demo",
                    display_name="demo",
                    project_context={"source": "github", "evidence": []},
                    hints=None,
                )


if __name__ == "__main__":
    unittest.main()
