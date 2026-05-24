from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.source_library_ingest_live_replay import CONTRACT_VERSION
from scripts.source_library_ingest_live_replay import run_replay


def _fake_runner(item: dict, params: dict, project_key: str) -> dict:
    _ = project_key
    manifest = item["extra"]["external_project_manifest"]
    execution_mode = manifest["execution_mode"]
    if execution_mode == "article_extractor":
        content = "Live article body. " * 90
        url = params["urls"][0]
        return {
            "status": "ok",
            "provider": "external_project",
            "execution_mode": "article_extractor",
            "provider_binding": {"provider_key": "external_project.article_extractor"},
            "records": [
                {
                    "record_id": "external:article:0",
                    "url": url,
                    "title": "Live Article",
                    "content_text": content,
                    "summary": content[:800],
                    "source_label": "Live Article Extraction PEP 8",
                    "record_meta": {
                        "article_extraction": {
                            "contract_version": "external_project.article_body_extraction.v1",
                            "state": "article_body_extracted",
                            "content_chars": len(content),
                        }
                    },
                    "raw_ref": {"source": "external_project"},
                }
            ],
            "errors": [],
            "runtime_diagnostics": {
                "diagnostics": {
                    "target_urls": [url],
                    "article_body_extracted": 1,
                    "parser_capability": {
                        "contract_version": "external_project.article_extraction_runner.v1",
                        "parser": "heuristic.main_content.v1",
                    },
                    "fallback_states": [
                        {
                            "url": url,
                            "state": "article_body_extracted",
                            "extractor": "heuristic.main_content.v1",
                            "confidence": "medium",
                            "content_chars": len(content),
                        }
                    ],
                }
            },
        }
    return {
        "status": "ok",
        "provider": "external_project",
        "execution_mode": "http_api",
        "provider_binding": {"provider_key": "external_project.http_api"},
        "records": [
            {
                "record_id": "external:http-api:0",
                "url": "https://github.com/python/cpython",
                "title": "python/cpython",
                "summary": "The Python programming language",
                "source_label": "Live GitHub CPython API",
                "record_meta": {},
                "raw_ref": {"source": "external_project"},
            }
        ],
        "errors": [],
        "runtime_diagnostics": {
            "diagnostics": {
                "endpoint": "https://api.github.com/repos/python/cpython",
                "method": "GET",
                "records_total": 1,
            }
        },
    }


class SourceLibraryIngestLiveReplayUnitTestCase(unittest.TestCase):
    def test_live_replay_is_skip_safe_by_default(self) -> None:
        result = run_replay(allow_public_network=False)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertTrue(result["validation"]["skipped"])
        self.assertFalse(result["validation"]["live_evidence_sufficient"])
        self.assertEqual(result["outputs"]["article_extraction_stack"]["status"], "skipped_public_network_disabled")
        self.assertEqual(result["outputs"]["external_project_replay"]["status"], "skipped_public_network_disabled")

    def test_live_replay_validates_article_and_external_project_boundaries(self) -> None:
        result = run_replay(
            allow_public_network=True,
            runner=_fake_runner,
            min_article_content_chars=1000,
        )

        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertFalse(result["validation"]["skipped"])
        self.assertTrue(result["validation"]["live_evidence_sufficient"])
        self.assertTrue(result["validation"]["live_article_extraction_stack_replay_closed"])
        self.assertTrue(result["validation"]["live_external_project_replay_closed"])
        self.assertEqual(
            result["outputs"]["article_extraction_stack"]["runner_result"]["article_extraction"]["article_body_extracted"],
            1,
        )
        self.assertEqual(result["outputs"]["external_project_replay"]["runner_result"]["record_count"], 1)
        self.assertEqual(result["outputs"]["external_project_replay"]["frontdoor"]["record_stats"]["normalized"], 1)


if __name__ == "__main__":
    unittest.main()
