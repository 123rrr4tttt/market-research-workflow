#!/usr/bin/env python3
"""Focused tests for the Wave20 R41 OpenClaw manifest readback checker."""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "checkers"
    / "check_r41_openclaw_mirror_runtime_manifest_readback.py"
)
SPEC = importlib.util.spec_from_file_location("check_r41_openclaw_mirror_runtime_manifest_readback", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class R41OpenClawMirrorRuntimeManifestReadbackTestCase(unittest.TestCase):
    def copy_topic(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        source = checker.REPO_ROOT / checker.TOPIC_REL
        target = Path(temp_dir.name) / "topic"
        shutil.copytree(source, target)
        return target

    def test_contract_accepts_repo_local_manifest_readback(self) -> None:
        contract = checker.build_contract(root=checker.REPO_ROOT)

        self.assertEqual(contract["status"], "passed", contract["failures"])
        self.assertEqual(contract["topic"], checker.TOPIC_REL.as_posix())
        self.assertEqual(contract["readback_state"]["local_mirror_status"], checker.STATUS_LOCAL_MIRROR_PASSED)
        self.assertEqual(
            contract["readback_state"]["external_runtime_status"],
            checker.STATUS_EXTERNAL_RUNTIME_UNVERIFIED,
        )
        self.assertEqual(contract["readback_state"]["missing_artifact_count"], 0)
        self.assertIn(checker.STATUS_LOCAL_MIRROR_PASSED, contract["readback_state"]["status_codes_seen"])
        self.assertIn(checker.STATUS_EXTERNAL_RUNTIME_UNVERIFIED, contract["readback_state"]["status_codes_seen"])
        self.assertNotIn(checker.STATUS_MISSING_ARTIFACT, contract["readback_state"]["status_codes_seen"])
        self.assertEqual(contract["handoff_manifest"]["status"], checker.STATUS_LOCAL_MIRROR_PASSED)
        self.assertEqual(contract["handoff_manifest"]["line_count"], 6)

    def test_contract_keeps_external_runtime_unverified(self) -> None:
        contract = checker.build_contract(root=checker.REPO_ROOT, topic=checker.REPO_ROOT / checker.TOPIC_REL)
        boundary = contract["external_runtime_boundary"]

        self.assertEqual(boundary["status"], checker.STATUS_EXTERNAL_RUNTIME_UNVERIFIED)
        self.assertFalse(boundary["external_openclaw_runtime_live_verified"])
        self.assertFalse(boundary["external_runtime_checked"])
        self.assertFalse(boundary["closure_claim_allowed"])

    def test_contract_reports_missing_artifact(self) -> None:
        topic = self.copy_topic()
        runtime_checker = checker.load_runtime_handoff_checker(checker.REPO_ROOT)
        (topic / runtime_checker.CODEX_HANDOFF_REL).unlink()

        contract = checker.build_contract(root=checker.REPO_ROOT, topic=topic)

        self.assertEqual(contract["status"], "failed")
        self.assertGreaterEqual(contract["readback_state"]["missing_artifact_count"], 1)
        missing_rows = [
            row
            for row in contract["required_artifacts"]
            if row["status"] == checker.STATUS_MISSING_ARTIFACT
        ]
        self.assertTrue(
            any(row["artifact_id"] == "codex_handoff_manifest" for row in missing_rows),
            missing_rows,
        )
        self.assertIn(checker.STATUS_MISSING_ARTIFACT, contract["readback_state"]["status_codes_seen"])


if __name__ == "__main__":
    unittest.main()
