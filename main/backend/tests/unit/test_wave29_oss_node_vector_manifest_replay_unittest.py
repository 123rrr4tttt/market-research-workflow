from __future__ import annotations

import importlib.util
import importlib
from pathlib import Path
import unittest
from unittest.mock import patch

import pytest

from tests.unit._evidence_source_assertions import assert_typed_evidence_unavailable


pytestmark = pytest.mark.unit


def _load_wave29_module():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "ops"
        / "search-lab"
        / "scripts"
        / "wave29_oss_node_vector_manifest_replay.py"
    )
    spec = importlib.util.spec_from_file_location("wave29_oss_node_vector_manifest_replay", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load Wave29 replay module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave29OssNodeVectorManifestReplayTest(unittest.TestCase):
    def test_node_manifest_replay_restores_dispatcher_after_leaf_error(self) -> None:
        module = _load_wave29_module()
        provider_manifest = {
            "contract_version": "wave19-vectorization-provider-manifest.v1",
            "external_provider_boundary": {"gap_codes": sorted(module.REQUIRED_PROVIDER_GAP_CODES)},
            "provider_manifest": {
                "modes": [
                    {
                        "mode": mode,
                        "provider_id": f"local_index.{mode}",
                        "closure_claim_allowed": False,
                        "capabilities": {
                            "live_provider_verified": False,
                            "semantic_quality_claim_allowed": False,
                        },
                        "trace_quality": {"status": "passed"},
                    }
                    for mode in module.REQUIRED_MODES
                ],
            },
        }
        runtime_module = importlib.import_module("app.services.workflow_graph.runtime")
        original_execute_node = runtime_module.execute_node

        with patch.object(
            module,
            "invoke_workflow_runtime_node",
            side_effect=RuntimeError("leaf failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "leaf failed"):
                module._run_node_manifest_replay(provider_manifest)

        self.assertIs(runtime_module.execute_node, original_execute_node)

    def test_node_manifest_replay_uses_fixed_offline_leaf_witness(self) -> None:
        module = _load_wave29_module()
        provider_manifest = {
            "contract_version": "wave19-vectorization-provider-manifest.v1",
            "external_provider_boundary": {
                "gap_codes": sorted(module.REQUIRED_PROVIDER_GAP_CODES),
            },
            "provider_manifest": {
                "modes": [
                    {
                        "mode": mode,
                        "provider_id": f"local_index.{mode}",
                        "closure_claim_allowed": False,
                        "capabilities": {
                            "live_provider_verified": False,
                            "semantic_quality_claim_allowed": False,
                        },
                        "trace_quality": {"status": "passed"},
                    }
                    for mode in module.REQUIRED_MODES
                ],
            },
        }

        replay, failures = module._run_node_manifest_replay(provider_manifest)

        self.assertEqual(failures, [])
        self.assertEqual(replay["status"], "passed")
        self.assertEqual(replay["run"]["status"], "succeeded")
        self.assertEqual(replay["run"]["results_count"], len(module.REQUIRED_MODES))
        self.assertEqual(replay["run"]["execution_scope"], "fixed_offline_witness")
        self.assertFalse(replay["run"]["durable"])
        self.assertNotIn("event_replay_consistency", replay)

    def test_node_manifest_replay_closes_repo_local_oss_node_blockers(self) -> None:
        module = _load_wave29_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave29-oss-node-vector-manifest-replay.v1")
        assert_typed_evidence_unavailable(self, contract)
        self.assertFalse(contract["repo_local_closure"]["archive_external_blocked_candidate"])
        self.assertIn("live_scheduler_tenant_db_ui_sla_not_proven", contract["external_conditions_retained"])

    def test_gate_missing_manifest_fails_typed_without_reading_deleted_artifact(self) -> None:
        module = _load_wave29_module()
        contract = module.build_contract()

        assert_typed_evidence_unavailable(self, contract)
        self.assertFalse(contract["repo_local_closure"]["archive_external_blocked_candidate"])

    def test_live_platform_probe_can_close_scheduler_tenant_ui_condition(self) -> None:
        module = _load_wave29_module()
        original_probe = module._run_live_platform_probe

        def fake_live_probe(*, live_api_base: str | None, live_ui_base: str | None, timeout: float) -> dict:
            return {
                "contract_version": "wave55-oss-node-platform-io-live-probe.v1",
                "status": "passed",
                "platform_io_live_sla_closed": True,
                "api_base": live_api_base,
                "ui_base": live_ui_base,
                "api_rows": [{"step": "run", "status": "ok", "run_status": "succeeded"}],
                "ui_probe": {"validated": True},
                "failures": [],
            }

        module._run_live_platform_probe = fake_live_probe
        try:
            contract = module.build_contract(
                live_api_base="http://127.0.0.1:8000/api/v1",
                live_ui_base="http://127.0.0.1:5173/",
            )
        finally:
            module._run_live_platform_probe = original_probe

        assert_typed_evidence_unavailable(self, contract)
        self.assertFalse(contract["repo_local_closure"]["platform_io_live_sla_closed"])
        self.assertIn("live_scheduler_tenant_db_ui_sla_not_proven", contract["external_conditions_retained"])
        self.assertIn("external_embedding_provider_live_not_verified", contract["external_conditions_retained"])


if __name__ == "__main__":
    unittest.main()
