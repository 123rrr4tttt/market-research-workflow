from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

pytestmark = pytest.mark.unit

from app.services.ingest.canary_handoff import CANARY_HANDOFF_CONTRACT_VERSION
from app.services.ingest.canary_handoff_live import build_production_like_handoff_evidence
from scripts.check_llm_crawler_high_js_replay_readiness import PUBLIC_REPLAY_CONTRACT_VERSION
from scripts.check_single_url_external_blocker_closure import (
    PROVIDER_CREDENTIALS_BEYOND_CROSSREF_BLOCKER,
    _configured_provider_live_evidence_from_canary,
    build_check,
)


def _public_replay_artifact() -> dict:
    target_results = [
        {
            "target_id": "x_search_robotics",
            "status": "auth_or_anti_bot_blocked",
            "browser_rendered": True,
            "public_network_attempted": True,
            "markers": {"contains_login": True, "contains_captcha": False},
            "reason": "login gate",
        },
        {
            "target_id": "instagram_tag_robotics",
            "status": "success",
            "browser_rendered": True,
            "public_network_attempted": True,
            "markers": {"contains_login": False, "contains_captcha": False},
        },
        {
            "target_id": "youtube_search_robotics",
            "status": "success",
            "browser_rendered": True,
            "public_network_attempted": True,
            "markers": {"contains_login": False, "contains_captcha": False, "contains_video_title": True},
        },
    ]
    return {
        "contract_version": PUBLIC_REPLAY_CONTRACT_VERSION,
        "validation": {
            "passed": True,
            "public_network_attempted": True,
            "real_public_high_js_replay_proven": False,
        },
        "inputs": {"target_count": 3},
        "outputs": {
            "public_targets_attempted": 3,
            "high_js_success_count": 2,
            "target_results": target_results,
        },
    }


def _fake_live_canary_result(**_kwargs) -> dict:
    handoff = {
        "contract_version": CANARY_HANDOFF_CONTRACT_VERSION,
        "handoff_state": "live_canary_validated",
        "frontdoor_run": {
            "entrypoint": "ingest.url.single",
            "source_mode": "url_execution",
            "project_key": "single_url_unit_canary",
            "source_url": "https://example.com/wave57-single-url",
        },
        "closure_claim": False,
    }
    evidence = build_production_like_handoff_evidence(
        project_key="single_url_unit_canary",
        accepted_url="https://example.com/wave57-single-url",
        rejected_url="https://example.com/search?q=wave57",
        accepted_status_code=200,
        rejected_status_code=200,
        accepted_result={
            "status": "success",
            "canary_handoff": {
                "strict_gate_state": {"state": "strict_passed", "strict_gate_enabled": True},
                "rollout": {"channel": "canary"},
                "handoff_state": "live_canary_validated",
            },
        },
        rejected_result={
            "status": "failed",
            "canary_handoff": {
                "strict_gate_state": {
                    "state": "strict_blocked",
                    "strict_gate_enabled": True,
                    "reason_code": "domain_blocked",
                },
                "rollout": {"channel": "canary"},
                "handoff_state": "live_canary_validated",
            },
        },
        db_readback={"accepted_doc_count": 1, "accepted_doc_ids": [10], "rejected_doc_count": 0},
    )
    return {
        "contract_version": "ingest.single_url_canary_handoff.production_like_check.v1",
        "status": "passed",
        "project_key": "single_url_unit_canary",
        "accepted_response_status_code": 200,
        "rejected_response_status_code": 200,
        "evidence": evidence,
        "validation": {"status": "passed", "passed": True},
        "validated_handoff": handoff,
        "cleanup": {"performed": True, "error": None},
    }


def _fake_official_api_report(**_kwargs) -> dict:
    return {
        "contract_version": "single_url.official_api_provider_maturity.v1",
        "status": "passed",
        "live_crossref": {"status": "passed"},
        "non_arxiv_provider_maturity": {
            "remaining_provider_catalog_boundary": [
                "provider-specific credentials and quota behavior beyond public Crossref remain external"
            ]
        },
    }


class SingleUrlExternalBlockerClosureUnitTestCase(unittest.TestCase):
    def test_configured_provider_evidence_uses_single_url_entrypoint(self) -> None:
        evidence = _configured_provider_live_evidence_from_canary(_fake_live_canary_result())

        self.assertTrue(evidence["demo_proj_live_canary_validated"])
        self.assertEqual(evidence["frontdoor_run"]["entrypoint"], "ingest.url.single")
        self.assertEqual(evidence["configured_provider"]["runtime"], "repo_local_api_db_runtime")

    def test_build_check_reduces_repo_public_boundaries_without_closure_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            public_artifact = Path(tmp) / "high_js_public_replay.json"
            public_artifact.write_text(json.dumps(_public_replay_artifact(), ensure_ascii=False) + "\n", encoding="utf-8")
            result = build_check(
                public_replay_artifact=public_artifact,
                live_canary_runner=_fake_live_canary_result,
                official_api_report_builder=_fake_official_api_report,
            )

        self.assertEqual(result["status"], "passed", result["runtime_results"])
        self.assertFalse(result["closure_decision"]["can_be_closed"])
        self.assertFalse(result["closure_decision"]["closure_claim"])
        self.assertTrue(result["closure_decision"]["repo_public_boundaries_reduced"]["public_browser_runtime_replay"])
        self.assertTrue(result["closure_decision"]["repo_public_boundaries_reduced"]["repo_local_configured_canary"])
        self.assertFalse(result["strict_promotion_readiness"]["production_24h_metrics_satisfied"])
        remaining_ids = {item["id"] for item in result["closure_decision"]["remaining_external_blockers"]}
        self.assertIn(PROVIDER_CREDENTIALS_BEYOND_CROSSREF_BLOCKER, remaining_ids)


if __name__ == "__main__":
    unittest.main()
