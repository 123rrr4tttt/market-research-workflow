from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pytest


pytestmark = pytest.mark.unit


def _load_contract_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_source_library_ingest_external_project_contract.py"
    )
    spec = importlib.util.spec_from_file_location(
        "check_source_library_ingest_external_project_contract",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load AT-EXT contract module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SourceLibraryIngestExternalProjectContractCheckTest(unittest.TestCase):
    def test_contract_gate_reports_current_narrow_closure_and_known_gaps(self) -> None:
        module = _load_contract_module()
        contract = module.build_contract()

        self.assertEqual(
            contract["contract_version"],
            "source-library-ingest-at-ext-current-contract.v1",
        )
        self.assertEqual(contract["scope"], "deterministic_current_state_no_live_external_probe")
        self.assertEqual(contract["status"], "passed_with_known_gaps")
        self.assertEqual(contract["failures"], [])

        at_ext_status = contract["at_ext_status"]
        self.assertEqual(at_ext_status["AT-EXT-01"]["status"], "closed_narrow_v1")
        self.assertEqual(at_ext_status["AT-EXT-04"]["status"], "closed_narrow_v1")
        self.assertEqual(at_ext_status["AT-EXT-05"]["status"], "partial_narrow_v1")
        self.assertEqual(at_ext_status["AT-EXT-08"]["status"], "partial_narrow_v1")
        self.assertEqual(at_ext_status["AT-EXT-09"]["status"], "partial_pending_external_replay")

        manifest_registry = contract["evidence"]["manifest_registry"]
        self.assertEqual(manifest_registry["supported_modes"], ["article_extractor", "http_api", "rss_feed", "sitemap"])
        self.assertEqual(manifest_registry["provider_registry_modes"], ["article_extractor", "http_api", "rss_feed", "sitemap"])
        self.assertTrue(manifest_registry["http_api_supports_pdf_artifact"])

        runner_frontdoor = contract["evidence"]["runner_frontdoor"]
        self.assertTrue(runner_frontdoor["http_api_called"])
        self.assertEqual(runner_frontdoor["runner_status"], "ok")
        self.assertTrue(runner_frontdoor["artifact_ref_present"])
        self.assertEqual(runner_frontdoor["frontdoor_execution_mode"], "http_api")
        self.assertEqual(runner_frontdoor["authority_normalized_records"], 1)

        article_runner = contract["evidence"]["article_extraction_runner"]
        self.assertEqual(article_runner["provider_key"], "external_project.article_extractor")
        self.assertEqual(article_runner["runner_status"], "partial")
        self.assertEqual(article_runner["fallback_states"], ["article_body_extracted", "metadata_only_fallback"])
        self.assertTrue(article_runner["frontdoor_has_document_candidate"])
        self.assertFalse(article_runner["frontdoor_run_extraction"])

        self.assertEqual(
            sorted(gap["code"] for gap in contract["remaining_gaps"]),
            [
                "live_article_extraction_stack_replay_not_run",
                "live_external_project_replay_not_run",
                "python_library_cli_container_runners_not_enabled",
            ],
        )


if __name__ == "__main__":
    unittest.main()
