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
from app.services.ingest.canary_strict_promotion import (
    OPS_STRICT_GATE_PROMOTION_ARTIFACT_KIND,
    OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION,
    PRODUCTION_24H_METRICS_ARTIFACT_KIND,
    PRODUCTION_24H_METRICS_CONTRACT_VERSION,
)
from scripts.check_ingest_canary_24h_metrics_artifact import build_24h_metrics_artifact
from scripts.check_llm_crawler_high_js_replay_readiness import PUBLIC_REPLAY_CONTRACT_VERSION
from scripts.check_single_url_official_api_provider_maturity import (
    PROVIDER_CREDENTIALS_EVIDENCE_CONTRACT_VERSION,
)
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


def _closed_public_replay_artifact() -> dict:
    return {
        "contract_version": PUBLIC_REPLAY_CONTRACT_VERSION,
        "validation": {
            "passed": True,
            "public_network_attempted": True,
            "real_public_high_js_replay_proven": True,
        },
        "inputs": {"target_count": 3},
        "outputs": {
            "public_targets_attempted": 3,
            "high_js_success_count": 3,
            "target_results": [
                {
                    "target_id": "x_search_robotics",
                    "status": "success",
                    "browser_rendered": True,
                    "public_network_attempted": True,
                },
                {
                    "target_id": "instagram_tag_robotics",
                    "status": "success",
                    "browser_rendered": True,
                    "public_network_attempted": True,
                },
                {
                    "target_id": "youtube_search_robotics",
                    "status": "success",
                    "browser_rendered": True,
                    "public_network_attempted": True,
                },
            ],
        },
        "evidence": {
            "contract_version": "llm_crawler.high_js_public_replay_evidence.v1",
            "credential_material_logged": False,
            "session": {
                "contract_version": "llm_crawler.high_js_session_replay_evidence.v1",
                "requested": True,
                "configured": True,
                "applied": True,
                "source": "unit_session_user_data_dir",
                "user_data_dir_mode": "copied_operator_profile",
                "copy_session_user_data_dir": True,
                "credential_material_logged": False,
                "path_disclosed": False,
            },
        },
    }


def _production_metrics_artifact() -> dict:
    artifact = build_24h_metrics_artifact(project_key="single_url_unit_canary")
    artifact.update(
        {
            "contract_version": PRODUCTION_24H_METRICS_CONTRACT_VERSION,
            "artifact_kind": PRODUCTION_24H_METRICS_ARTIFACT_KIND,
            "deterministic_fixture": False,
            "evidence_scope": "production",
            "source_record": {
                "record_id": "single-url-prod-24h-20260524",
                "system": "production_metrics_export",
                "generated_at": "2026-05-24T01:10:00Z",
            },
        }
    )
    artifact["window"]["live_window_observed"] = True
    artifact["live_boundaries"].update(
        {
            "production_data_claim": True,
            "metric_24h_live_readback_claim": True,
            "closure_claim": False,
            "remaining_live_gaps": [],
        }
    )
    return artifact


def _ops_promotion_artifact() -> dict:
    return {
        "contract_version": OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION,
        "artifact_kind": OPS_STRICT_GATE_PROMOTION_ARTIFACT_KIND,
        "evidence_scope": "operations",
        "operations_approval_recorded": True,
        "production_24h_metrics_reviewed": True,
        "rollback_plan_recorded": True,
        "promotion_decision": "promote",
        "strict_gate_global_default_enabled": True,
        "approved_by": "ops-oncall",
        "approved_at": "2026-05-24T01:20:00Z",
        "approval_ticket": "OPS-SINGLE-URL-20260524",
        "rollback_plan_ref": "runbook://single-url-strict-gate-rollback",
    }


def _provider_credentials_artifact() -> dict:
    return {
        "contract_version": PROVIDER_CREDENTIALS_EVIDENCE_CONTRACT_VERSION,
        "evidence_scope": "provider_credentials_quota",
        "generated_by": "ops-provider-health-export",
        "generated_at": "2026-05-24T01:30:00Z",
        "live_probe_authorized": True,
        "credential_material_logged": False,
        "providers": [
            {
                "provider_key": "semanticscholar",
                "credential_state": "configured",
                "quota_status": "within_quota",
                "live_probe_status": "passed",
                "live_probe_authorized": True,
                "provider_specific_quota_validated": True,
                "credential_material_logged": False,
            }
        ],
    }


def _provider_credentials_configured_only_artifact() -> dict:
    artifact = _provider_credentials_artifact()
    artifact["live_probe_authorized"] = False
    artifact["providers"][0].update(
        {
            "quota_status": "configured_only",
            "live_probe_status": "configured_only",
            "live_probe_authorized": False,
            "provider_specific_quota_validated": False,
        }
    )
    return artifact


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

    def test_build_check_can_close_when_all_external_evidence_is_supplied_and_claimed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            public_artifact = tmp_path / "high_js_public_replay.json"
            production_artifact = tmp_path / "production_metrics.json"
            ops_artifact = tmp_path / "ops_promotion.json"
            provider_artifact = tmp_path / "provider_credentials.json"
            public_artifact.write_text(
                json.dumps(_closed_public_replay_artifact(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            production_artifact.write_text(
                json.dumps(_production_metrics_artifact(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            ops_artifact.write_text(
                json.dumps(_ops_promotion_artifact(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            provider_artifact.write_text(
                json.dumps(_provider_credentials_artifact(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            result = build_check(
                public_replay_artifact=public_artifact,
                live_canary_runner=_fake_live_canary_result,
                production_metrics_artifact_path=production_artifact,
                ops_promotion_artifact_path=ops_artifact,
                provider_credentials_artifact_path=provider_artifact,
                claim_closure=True,
            )

        self.assertEqual(result["status"], "passed", result["runtime_results"])
        self.assertEqual(result["closure_decision"]["status"], "closed")
        self.assertTrue(result["closure_decision"]["can_be_closed"])
        self.assertTrue(result["closure_decision"]["closure_claim"])
        self.assertEqual(result["closure_decision"]["remaining_external_blockers"], [])

    def test_configured_only_provider_credentials_keep_closure_external_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            public_artifact = tmp_path / "high_js_public_replay.json"
            production_artifact = tmp_path / "production_metrics.json"
            ops_artifact = tmp_path / "ops_promotion.json"
            provider_artifact = tmp_path / "provider_credentials.json"
            public_artifact.write_text(
                json.dumps(_closed_public_replay_artifact(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            production_artifact.write_text(
                json.dumps(_production_metrics_artifact(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            ops_artifact.write_text(
                json.dumps(_ops_promotion_artifact(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            provider_artifact.write_text(
                json.dumps(_provider_credentials_configured_only_artifact(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            result = build_check(
                public_replay_artifact=public_artifact,
                live_canary_runner=_fake_live_canary_result,
                production_metrics_artifact_path=production_artifact,
                ops_promotion_artifact_path=ops_artifact,
                provider_credentials_artifact_path=provider_artifact,
                claim_closure=True,
            )

        self.assertEqual(result["status"], "passed", result["runtime_results"])
        self.assertEqual(result["closure_decision"]["status"], "external_blocked")
        self.assertFalse(result["closure_decision"]["can_be_closed"])
        self.assertFalse(result["closure_decision"]["closure_claim"])
        self.assertFalse(
            result["closure_decision"]["repo_public_boundaries_reduced"]["provider_credentials_beyond_crossref"]
        )
        maturity = result["official_api_provider_maturity"]["non_arxiv_provider_maturity"]
        self.assertEqual(maturity["provider_credentials_boundary"]["status"], "configured_only")
        remaining_ids = {item["id"] for item in result["closure_decision"]["remaining_external_blockers"]}
        self.assertEqual(remaining_ids, {PROVIDER_CREDENTIALS_BEYOND_CROSSREF_BLOCKER})


if __name__ == "__main__":
    unittest.main()
