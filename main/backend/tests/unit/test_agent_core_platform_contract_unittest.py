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
        self.assertEqual(snapshot["evidence_envelope"]["contract_version"], "agent_core.platform_evidence.v1")
        self.assertEqual(snapshot["evidence_envelope"]["trace_audit"]["status"], "ok")

    def test_agent_core_platform_contract_snapshot_is_deterministic(self) -> None:
        first = build_contract_snapshot()
        second = build_contract_snapshot()

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
