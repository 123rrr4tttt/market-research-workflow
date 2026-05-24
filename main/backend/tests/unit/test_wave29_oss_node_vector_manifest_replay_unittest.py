from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import pytest


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
    def test_node_manifest_replay_closes_repo_local_oss_node_blockers(self) -> None:
        module = _load_wave29_module()
        contract = module.build_contract()

        self.assertEqual(contract["contract_version"], "wave29-oss-node-vector-manifest-replay.v1")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["failures"], [])
        self.assertTrue(contract["repo_local_closure"]["archive_external_blocked_candidate"])
        self.assertEqual(contract["repo_local_closure"]["remaining_repo_local_blockers"], [])
        self.assertEqual(
            contract["repo_local_closure"]["repo_local_blockers_closed"],
            [
                "node_schema_runtime_persistence_platformization_scope_not_closed",
                "vector_search_node_manifest_consumption_not_live_replayed",
            ],
        )

        provider_check = contract["provider_manifest_check"]
        self.assertEqual(provider_check["status"], "passed")
        self.assertEqual(provider_check["modes"], ["hybrid", "keyword", "vector"])
        self.assertFalse(provider_check["closure_claim_allowed"])
        self.assertFalse(provider_check["provider_live_closure_claim_allowed"])
        self.assertFalse(provider_check["semantic_quality_claim_allowed"])

        replay = contract["node_manifest_replay"]
        self.assertEqual(replay["status"], "passed")
        self.assertEqual(replay["run"]["status"], "succeeded")
        self.assertTrue(replay["event_replay_consistency"]["consistent"])
        self.assertEqual(replay["workflow_graph"]["node_count"], 3)
        self.assertEqual(
            replay["workflow_graph"]["topo_order"],
            ["vector_keyword", "vector_vector", "vector_hybrid"],
        )

        rows = {row["mode"]: row for row in replay["mode_results"]}
        self.assertEqual(sorted(rows), ["hybrid", "keyword", "vector"])
        for mode, row in rows.items():
            self.assertEqual(row["status"], "passed")
            self.assertEqual(row["provider_id"], f"local_index.{mode}")
            self.assertTrue(row["manifest_consumed"])
            self.assertFalse(row["closure_claim_allowed"])
            self.assertFalse(row["live_provider_verified"])
            self.assertFalse(row["semantic_quality_claim_allowed"])
            self.assertIn("query", row["io_trace_keys"])
            self.assertIn("provider_manifest_version", row["io_trace_keys"])
            self.assertIn("semantic_embedding_quality_not_proven", row["unsupported_claim_codes"])
            self.assertIn("live_scheduler_tenant_db_ui_sla_not_proven", row["unsupported_claim_codes"])

        platform = contract["platform_io_sla_readback"]
        self.assertEqual(platform["contract_version"], "wave55-oss-node-platform-io-sla-readback.v1")
        self.assertEqual(platform["status"], "passed")
        self.assertEqual(platform["repo_local_contract"]["status"], "passed")
        self.assertEqual(platform["live_probe"]["status"], "not_requested")
        self.assertFalse(platform["platform_io_live_sla_closed"])
        self.assertIn("live_scheduler_tenant_db_ui_sla_not_proven", contract["external_conditions_retained"])
        self.assertTrue(contract["repo_local_closure"]["platform_io_sla_readback_attached"])

    def test_gate_fails_if_manifest_mode_claims_live_provider(self) -> None:
        module = _load_wave29_module()
        manifest = json.loads(module.DEFAULT_PROVIDER_MANIFEST.read_text(encoding="utf-8"))
        manifest["provider_manifest"]["modes"][0]["capabilities"]["live_provider_verified"] = True

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "provider_manifest_readback.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            contract = module.build_contract(provider_manifest_path=manifest_path)

        self.assertEqual(contract["status"], "failed")
        self.assertFalse(contract["repo_local_closure"]["archive_external_blocked_candidate"])
        self.assertTrue(
            any("live_provider_verified must remain false" in failure for failure in contract["failures"])
        )

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

        self.assertEqual(contract["status"], "passed")
        self.assertTrue(contract["platform_io_sla_readback"]["platform_io_live_sla_closed"])
        self.assertTrue(contract["repo_local_closure"]["platform_io_live_sla_closed"])
        self.assertNotIn("live_scheduler_tenant_db_ui_sla_not_proven", contract["external_conditions_retained"])
        self.assertIn("external_embedding_provider_live_not_verified", contract["external_conditions_retained"])


if __name__ == "__main__":
    unittest.main()
