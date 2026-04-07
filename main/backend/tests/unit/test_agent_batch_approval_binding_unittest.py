from __future__ import annotations

import unittest

import pytest

from app.services.agent_batch.approval_binding import (
    approve_approval,
    request_approval,
    verify_approval_token,
)

pytestmark = pytest.mark.unit


class AgentBatchApprovalBindingUnitTest(unittest.TestCase):
    def test_approval_token_must_be_approved_and_match_binding(self):
        binding = {
            "argv": ["task_ingest_market", "ai chips"],
            "cwd": "/workspace/proj-a",
            "env": {"WORKFLOW_RUN_ID": "run-1", "TRACE_ID": "trace-1"},
            "channel": "search.market",
            "project_key": "proj-a",
        }
        req = request_approval(binding=binding, ttl_seconds=300)
        token = req["approval_token"]

        ok_before, reason_before = verify_approval_token(approval_token=token, binding=binding)
        self.assertFalse(ok_before)
        self.assertEqual(reason_before, "approval_not_approved")

        approve_approval(approval_token=token)
        ok_after, reason_after = verify_approval_token(approval_token=token, binding=binding)
        self.assertTrue(ok_after)
        self.assertIsNone(reason_after)

        mismatch_binding = {**binding, "cwd": "/workspace/proj-b"}
        ok_mismatch, reason_mismatch = verify_approval_token(
            approval_token=token,
            binding=mismatch_binding,
        )
        self.assertFalse(ok_mismatch)
        self.assertEqual(reason_mismatch, "approval_binding_mismatch")


if __name__ == "__main__":
    unittest.main()
