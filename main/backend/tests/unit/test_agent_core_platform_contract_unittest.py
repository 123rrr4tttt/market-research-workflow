from __future__ import annotations

import unittest

import pytest

from scripts.check_agent_core_platform_contract import build_contract_snapshot, validate_contract_snapshot

pytestmark = pytest.mark.unit


class AgentCorePlatformContractUnitTest(unittest.TestCase):
    def test_agent_core_platform_contract_links_inventory_dispatch_and_evidence(self) -> None:
        snapshot = build_contract_snapshot()

        self.assertEqual(validate_contract_snapshot(snapshot), [])
        self.assertEqual(snapshot["consumer"], "agent_core.tool_dispatch")
        self.assertEqual(snapshot["consumer_boundary"]["capability"], "agent_tool_dispatch")
        self.assertEqual(snapshot["agent_permission_boundary"]["allowed"], True)
        self.assertEqual(snapshot["tool_schema_inventory"]["contract_version"], "agent_core.tool_schema_inventory.v1")
        self.assertEqual(snapshot["runtime_dispatch"]["contract_version"], "agent_core.runtime_dispatch.v1")
        self.assertEqual(snapshot["provider_capability_matrix"]["contract_version"], "agent_core.provider_capability_matrix.v1")
        self.assertEqual(snapshot["evidence_envelope"]["contract_version"], "agent_core.platform_evidence.v1")
        self.assertEqual(snapshot["evidence_envelope"]["trace_audit"]["status"], "ok")

    def test_agent_core_provider_matrix_separates_static_boundary_states(self) -> None:
        snapshot = build_contract_snapshot()
        matrix = snapshot["provider_capability_matrix"]
        entries = {entry["provider_key"]: entry for entry in matrix["entries"]}

        self.assertEqual(matrix["evaluation_mode"], "static_contract_not_live_probe")
        self.assertFalse(matrix["live_provider_claims"])
        self.assertGreaterEqual(matrix["summary"]["by_status"]["repo_native_supported"], 1)
        self.assertGreaterEqual(matrix["summary"]["by_status"]["missing_config"], 1)
        self.assertGreaterEqual(matrix["summary"]["by_status"]["blocked_permissions"], 1)
        self.assertGreaterEqual(matrix["summary"]["by_status"]["deferred_external_framework"], 1)
        self.assertEqual(entries["fake_core_provider"]["status"], "repo_native_supported")
        self.assertFalse(entries["fake_core_provider"]["live_provider_claim"])
        self.assertEqual(entries["json_core_provider"]["status"], "missing_config")
        self.assertEqual(entries["native_tool_calling_provider"]["status"], "missing_config")
        self.assertEqual(entries["agent_core.permission_boundary"]["status"], "blocked_permissions")
        self.assertIn("cross_consumer.invoke", entries["agent_core.permission_boundary"]["denied_permissions"])
        self.assertEqual(matrix["external_framework_boundary"]["adoption_status"], "deferred")

    def test_agent_core_platform_contract_snapshot_is_deterministic(self) -> None:
        first = build_contract_snapshot()
        second = build_contract_snapshot()

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
