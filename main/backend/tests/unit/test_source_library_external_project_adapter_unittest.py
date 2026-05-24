from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.source_library.adapters.external_project import handle_external_project_manifest


def _build_manifest(*, execution_mode: str = "rss_feed") -> dict[str, object]:
    runner_ref = "https://example.com/feed.xml"
    source_kind = "feed_aggregator"
    capabilities = {
        "candidate_urls": True,
        "article_metadata": True,
        "article_body": False,
        "pdf_artifact": False,
    }
    accepted_inputs = {
        "query_terms": True,
        "urls": False,
        "domains": False,
        "date_range": False,
        "max_items": True,
    }
    normalization = {
        "record_kind": "article_metadata",
        "frontdoor_strategy": "records_only_defer",
    }
    if execution_mode == "http_api":
        runner_ref = "https://api.example.com/search"
    elif execution_mode == "python_library":
        runner_ref = "python-library://source_library.fixture_records.v1"
        source_kind = "python_library_wrapper"
    elif execution_mode == "cli_or_container":
        runner_ref = "cli://source_library.fixture_json.v1"
        source_kind = "cli_or_container_wrapper"
    elif execution_mode == "article_extractor":
        runner_ref = "article-extractor://trafilatura-or-heuristic"
        source_kind = "article_extraction_stack"
        capabilities["article_body"] = True
        accepted_inputs["urls"] = True
        normalization = {
            "record_kind": "document_candidate",
            "frontdoor_strategy": "records_allow_extract",
        }

    manifest: dict[str, object] = {
        "contract_version": "external_item.manifest.v1",
        "item_key": "external.demo.item",
        "display_name": "External Demo Item",
        "project_link": "https://github.com/example/external-demo",
        "source_kind": source_kind,
        "source_scope": "finance_news",
        "capabilities": capabilities,
        "accepted_inputs": accepted_inputs,
        "execution_mode": execution_mode,
        "runner_ref": runner_ref,
        "normalization": normalization,
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
            "source_refs": ["https://github.com/example/external-demo"],
        },
    }
    if execution_mode == "http_api":
        manifest["runtime_config"] = {
            "method": "GET",
            "query_param_map": {"query_terms": "q", "max_items": "limit"},
            "records_path": "items",
            "record_mapping": {
                "url": "url",
                "title": "title",
                "summary": "summary",
                "artifact_url": "pdf_url",
            },
        }
    elif execution_mode == "python_library":
        manifest["runtime_config"] = {
            "runner_id": "source_library.fixture_records.v1",
            "fixture_records": [
                {
                    "url": "https://example.com/python/one",
                    "title": "Python Runner Record",
                    "summary": "Materialized by a registered Python runner.",
                }
            ],
        }
    elif execution_mode == "cli_or_container":
        manifest["runtime_config"] = {
            "runner_id": "source_library.fixture_json.v1",
            "records_path": "items",
            "fixture_output_json": {
                "items": [
                    {
                        "url": "https://example.com/cli/one",
                        "title": "CLI Runner Record",
                        "summary": "Materialized by a registered CLI/container wrapper.",
                    }
                ]
            },
        }
    elif execution_mode == "article_extractor":
        manifest["runtime_config"] = {
            "parser": "heuristic.main_content.v1",
        }
    return manifest


class ExternalProjectAdapterUnitTestCase(unittest.TestCase):
    def test_rss_feed_manifest_returns_materialized_records(self) -> None:
        params = {
            "_source_library_item": {
                "item_key": "external.demo.item",
                "name": "External Demo Item",
                "extra": {"external_project_manifest": _build_manifest()},
            },
            "query_terms": ["fintech"],
            "max_items": 2,
        }

        with patch("app.services.source_library.adapters.external_project.execute_feed_probe") as execute:
            execute.return_value = SimpleNamespace(
                selected_candidates=[
                    SimpleNamespace(url="https://example.com/posts/1", title="Fintech One", text="Summary one"),
                    SimpleNamespace(url="https://example.com/posts/2", title="Fintech Two", text="Summary two"),
                ],
                used_term_fallback=False,
                pages_scanned=1,
                diagnostics={"raw_candidates": 2},
                errors=[],
            )
            result = handle_external_project_manifest(params, project_key="demo_proj")

        execute.assert_called_once()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["provider"], "external_project")
        self.assertEqual(result["execution_mode"], "rss_feed")
        self.assertEqual(result["provider_binding"]["provider_key"], "external_project.rss_feed")
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["records"][0]["title"], "Fintech One")
        self.assertEqual(result["records"][0]["record_meta"]["external_project"]["project_link"], "https://github.com/example/external-demo")

    def test_http_api_manifest_maps_artifacts_into_record_meta(self) -> None:
        params = {
            "_source_library_item": {
                "item_key": "external.demo.item",
                "name": "External Demo Item",
                "extra": {"external_project_manifest": _build_manifest(execution_mode="http_api")},
            },
            "query_terms": ["robotics"],
            "max_items": 1,
        }

        with patch("app.services.source_library.adapters.external_project.default_http_client.get_json") as get_json:
            get_json.return_value = {
                "items": [
                    {
                        "url": "https://example.com/posts/api-1",
                        "title": "API Record",
                        "summary": "API summary",
                        "pdf_url": "https://example.com/posts/api-1.pdf",
                    }
                ]
            }
            result = handle_external_project_manifest(params, project_key=None)

        get_json.assert_called_once()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["execution_mode"], "http_api")
        self.assertEqual(result["provider_binding"]["provider_key"], "external_project.http_api")
        self.assertEqual(result["records"][0]["url"], "https://example.com/posts/api-1")
        self.assertEqual(
            result["records"][0]["record_meta"]["artifact_ref"]["source_locator"],
            "https://example.com/posts/api-1.pdf",
        )

    def test_python_library_manifest_runs_registered_fixture_runner(self) -> None:
        params = {
            "_source_library_item": {
                "item_key": "external.demo.item",
                "name": "External Demo Item",
                "extra": {"external_project_manifest": _build_manifest(execution_mode="python_library")},
            },
            "query_terms": ["robotics"],
            "max_items": 1,
        }

        result = handle_external_project_manifest(params, project_key="demo_proj")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["execution_mode"], "python_library")
        self.assertEqual(result["provider_binding"]["provider_key"], "external_project.python_library")
        self.assertEqual(result["records"][0]["url"], "https://example.com/python/one")
        self.assertEqual(
            result["runtime_diagnostics"]["diagnostics"]["runner_contract"],
            "external_project.python_library_runner.v1",
        )

    def test_cli_or_container_manifest_runs_predeclared_fixture_wrapper(self) -> None:
        params = {
            "_source_library_item": {
                "item_key": "external.demo.item",
                "name": "External Demo Item",
                "extra": {"external_project_manifest": _build_manifest(execution_mode="cli_or_container")},
            },
            "query_terms": ["robotics"],
            "max_items": 1,
        }

        result = handle_external_project_manifest(params, project_key="demo_proj")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["execution_mode"], "cli_or_container")
        self.assertEqual(result["provider_binding"]["provider_key"], "external_project.cli_or_container")
        self.assertEqual(result["records"][0]["url"], "https://example.com/cli/one")
        self.assertEqual(
            result["runtime_diagnostics"]["diagnostics"]["execution_policy"],
            "predeclared_wrapper_no_arbitrary_shell",
        )

    def test_python_library_manifest_rejects_unknown_runner_id(self) -> None:
        manifest = _build_manifest(execution_mode="python_library")
        manifest["runtime_config"]["runner_id"] = "unknown.runner"
        params = {
            "_source_library_item": {
                "item_key": "external.demo.item",
                "name": "External Demo Item",
                "extra": {"external_project_manifest": manifest},
            }
        }

        with self.assertRaisesRegex(ValueError, "unsupported python_library runner_id"):
            handle_external_project_manifest(params, project_key="demo_proj")

    def test_article_extractor_manifest_materializes_body_and_diagnostics(self) -> None:
        params = {
            "_source_library_item": {
                "item_key": "external.demo.item",
                "name": "External Demo Item",
                "extra": {"external_project_manifest": _build_manifest(execution_mode="article_extractor")},
            },
            "urls": ["https://example.com/articles/body"],
            "max_items": 1,
        }

        extraction = SimpleNamespace(
            title="Article Body",
            content="Body paragraph with deterministic article text.",
            extractor="heuristic.main_content.v1",
            confidence="medium",
            meta={"fixture": True},
        )
        with (
            patch("app.services.source_library.adapters.external_project.default_http_client.get_text", return_value="<article>body</article>") as get_text,
            patch("app.services.source_library.adapters.external_project.extract_article_content_from_html", return_value=extraction) as extractor,
        ):
            result = handle_external_project_manifest(params, project_key="demo_proj")

        get_text.assert_called_once()
        self.assertTrue(get_text.call_args.kwargs["follow_redirects"])
        extractor.assert_called_once()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["execution_mode"], "article_extractor")
        self.assertEqual(result["provider_binding"]["provider_key"], "external_project.article_extractor")
        self.assertEqual(result["records"][0]["content_text"], "Body paragraph with deterministic article text.")
        article_meta = result["records"][0]["record_meta"]["article_extraction"]
        self.assertEqual(article_meta["contract_version"], "external_project.article_body_extraction.v1")
        self.assertEqual(article_meta["state"], "article_body_extracted")
        self.assertEqual(article_meta["parser_capability"]["parser"], "heuristic.main_content.v1")
        self.assertEqual(
            result["runtime_diagnostics"]["diagnostics"]["fallback_states"][0]["state"],
            "article_body_extracted",
        )

    def test_article_extractor_manifest_reports_metadata_and_fetch_fallback_states(self) -> None:
        params = {
            "_source_library_item": {
                "item_key": "external.demo.item",
                "name": "External Demo Item",
                "extra": {"external_project_manifest": _build_manifest(execution_mode="article_extractor")},
            },
            "urls": ["https://example.com/articles/empty", "https://example.com/articles/error"],
            "max_items": 2,
        }

        def _fake_get_text(url: str, **kwargs):  # noqa: ANN001
            if url.endswith("/error"):
                raise RuntimeError("fixture fetch failed")
            return "<html><body>metadata only</body></html>"

        extraction = SimpleNamespace(
            title=None,
            content="",
            extractor="heuristic.main_content.v1",
            confidence="low",
            meta={"fixture": True},
        )
        with (
            patch("app.services.source_library.adapters.external_project.default_http_client.get_text", side_effect=_fake_get_text),
            patch("app.services.source_library.adapters.external_project.extract_article_content_from_html", return_value=extraction),
        ):
            result = handle_external_project_manifest(params, project_key="demo_proj")

        self.assertEqual(result["status"], "partial")
        states = [row["state"] for row in result["runtime_diagnostics"]["diagnostics"]["fallback_states"]]
        self.assertEqual(states, ["metadata_only_fallback", "fetch_error_fallback"])
        self.assertEqual(result["records"][0]["record_meta"]["article_extraction"]["state"], "metadata_only_fallback")
        self.assertEqual(result["records"][1]["record_meta"]["article_extraction"]["state"], "fetch_error_fallback")
        self.assertEqual(result["error_details"][0]["fallback_state"], "fetch_error_fallback")


if __name__ == "__main__":
    unittest.main()
