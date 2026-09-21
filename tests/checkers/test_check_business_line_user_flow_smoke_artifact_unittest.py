#!/usr/bin/env python3
"""Focused tests for business-line user-flow smoke artifact checks."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_business_line_user_flow_smoke_artifact.py"
SPEC = importlib.util.spec_from_file_location("check_business_line_user_flow_smoke_artifact", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class BusinessLineUserFlowSmokeArtifactTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def write_json(self, root: Path, rel_path: str, payload: object) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def line(
        self,
        line_key: str,
        status: str = checker.LINE_STATUS_PASSED,
        response_assertion_status: str = checker.RESPONSE_ASSERTION_PASSED,
    ) -> dict[str, object]:
        return {
            "line_key": line_key,
            "probe_path": f"/probe/{line_key}",
            "status": status,
            "proof_level": "contract_reachable",
            "response_assertion_status": response_assertion_status,
        }

    def feedback_loop(self, status: str = checker.STATUS_PASSED) -> dict[str, object]:
        if status == checker.STATUS_BLOCKED:
            return {
                "status": checker.STATUS_BLOCKED,
                "reason": "feedback_submit_unavailable",
                "submission_id": None,
                "task_id": None,
                "trace_id": None,
                "failures": ["feedback_submit_unavailable"],
                "readback": {
                    "matched": False,
                    "missing_fields": ["submission_id", "task_id", "status", "trace_id"],
                },
            }
        if status == checker.STATUS_FEEDBACK_READBACK_MISSING:
            return {
                "status": checker.STATUS_FEEDBACK_READBACK_MISSING,
                "reason": checker.STATUS_FEEDBACK_READBACK_MISSING,
                "submission_id": "sub-smoke",
                "task_id": "task-smoke",
                "trace_id": "trace-smoke",
                "failures": ["feedback_history_missing_submission"],
                "readback": {
                    "matched": False,
                    "matched_by": [],
                    "history_item_count": 0,
                    "missing_fields": ["submission_id", "task_id", "status", "trace_id"],
                    "mismatched_fields": [],
                },
            }
        return {
            "status": checker.STATUS_PASSED,
            "reason": "feedback_readback_confirmed",
            "submission_id": "sub-smoke",
            "task_id": "task-smoke",
            "trace_id": "trace-smoke",
            "failures": [],
            "readback": {
                "matched": True,
                "matched_by": ["sub-smoke"],
                "history_item_count": 1,
                "submission_id": "sub-smoke",
                "task_id": "task-smoke",
                "status": "queued",
                "trace_id": "trace-smoke",
                "missing_fields": [],
                "mismatched_fields": [],
            },
        }

    def payload(self, status: str = checker.STATUS_PASSED) -> dict[str, object]:
        return {
            "schema_version": checker.ARTIFACT_SCHEMA_VERSION,
            "status": status,
            "lines": [self.line(line_key) for line_key in checker.REQUIRED_LINE_KEYS],
            "feedback_loop": self.feedback_loop(status),
        }

    def test_passed_artifact_with_all_seven_lines_passes(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/user-flow-smoke.json", self.payload())

        report = checker.build_report(artifact, root=root)

        self.assertEqual("business_line_user_flow_smoke_check.v1", report["schema_version"])
        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["artifact"]["summary"]["missing_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["response_assertion_failed_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["response_assertion_missing_line_keys"])
        self.assertEqual(7, report["artifact"]["summary"]["observed_line_count"])
        self.assertEqual("passed", report["artifact"]["summary"]["feedback_loop_status"])
        self.assertEqual("sub-smoke", report["evidence"]["submission_id"])
        self.assertEqual("task-smoke", report["evidence"]["task_id"])
        self.assertEqual("trace-smoke", report["evidence"]["trace_id"])
        self.assertEqual([], report["failures"])
        self.assertEqual(sorted(checker.REQUIRED_LINE_KEYS), report["artifact"]["observed_line_keys"])

    def test_blocked_artifact_exits_zero_only_when_allowed(self) -> None:
        root = self.make_repo()
        payload = self.payload(status=checker.STATUS_BLOCKED)
        payload["lines"] = [
            self.line(
                line_key,
                checker.STATUS_BLOCKED,
                checker.RESPONSE_ASSERTION_SKIPPED_BLOCKED,
            )
            for line_key in checker.REQUIRED_LINE_KEYS
        ]
        payload["lines"][-1]["response_assertion_status"] = checker.RESPONSE_ASSERTION_NOT_RUN  # type: ignore[index]
        payload["feedback_loop"] = self.feedback_loop(checker.STATUS_BLOCKED)
        artifact = self.write_json(root, "artifacts/user-flow-smoke.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("blocked_by_environment", report["status"])
        self.assertEqual(1, checker.main([str(artifact)]))
        self.assertEqual(0, checker.main([str(artifact), "--allow-blocked"]))

    def test_failed_artifact_fails_even_when_blocked_is_allowed(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"][0]["status"] = "failed"  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/user-flow-smoke.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertEqual(1, checker.main([str(artifact), "--allow-blocked"]))
        first_line = report["artifact"]["lines"][0]
        self.assertIn("valid_status", first_line["missing_fields"])

    def test_response_assertion_failed_line_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"][0]["response_assertion_status"] = checker.RESPONSE_ASSERTION_FAILED  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/user-flow-smoke.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["response_assertion_failed_line_keys"])
        self.assertIn("ingest", report["artifact"]["summary"]["incomplete_line_keys"])
        self.assertIn("line_contract_fields", report["artifact"]["structural_failures"])
        first_line = report["artifact"]["lines"][0]
        self.assertIn("valid_response_assertion_status", first_line["missing_fields"])

    def test_response_assertion_not_declared_line_fails_as_missing(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"][0]["response_assertion_status"] = checker.RESPONSE_ASSERTION_NOT_DECLARED  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/user-flow-smoke.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["response_assertion_missing_line_keys"])
        self.assertIn("ingest", report["artifact"]["summary"]["incomplete_line_keys"])
        first_line = report["artifact"]["lines"][0]
        self.assertIn("valid_response_assertion_status", first_line["missing_fields"])

    def test_legacy_line_without_response_assertion_status_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        del payload["lines"][0]["response_assertion_status"]  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/user-flow-smoke.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["response_assertion_missing_line_keys"])
        first_line = report["artifact"]["lines"][0]
        self.assertIsNone(first_line["response_assertion_status"])
        self.assertIn("response_assertion_status", first_line["missing_fields"])

    def test_missing_line_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"] = [
            line for line in payload["lines"] if line["line_key"] != "runtime_ops"  # type: ignore[index]
        ]
        artifact = self.write_json(root, "artifacts/user-flow-smoke.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("runtime_ops", report["artifact"]["summary"]["missing_line_keys"])
        self.assertIn("missing_line_keys", report["artifact"]["structural_failures"])

    def test_unexpected_line_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"].append(self.line("unexpected_line"))  # type: ignore[attr-defined]
        artifact = self.write_json(root, "artifacts/user-flow-smoke.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("unexpected_line", report["artifact"]["summary"]["unexpected_line_keys"])
        self.assertIn("unexpected_line_keys", report["artifact"]["structural_failures"])

    def test_duplicate_line_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"].append(self.line("ingest"))  # type: ignore[attr-defined]
        artifact = self.write_json(root, "artifacts/user-flow-smoke.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["duplicate_line_keys"])
        self.assertIn("duplicate_line_keys", report["artifact"]["structural_failures"])

    def test_missing_feedback_loop_fails_even_when_lines_pass(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        del payload["feedback_loop"]
        artifact = self.write_json(root, "artifacts/user-flow-smoke.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("feedback_loop", report["failures"])
        self.assertIn("feedback_loop", report["artifact"]["feedback_loop"]["missing_fields"])

    def test_feedback_readback_missing_is_not_allowed_as_passed(self) -> None:
        root = self.make_repo()
        payload = self.payload(status=checker.STATUS_FEEDBACK_READBACK_MISSING)
        artifact = self.write_json(root, "artifacts/user-flow-smoke.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("feedback_readback_missing", report["status"])
        self.assertIn("feedback_loop", report["failures"])
        self.assertEqual("sub-smoke", report["evidence"]["submission_id"])
        self.assertIn(
            "feedback_history_missing_submission",
            report["artifact"]["feedback_loop"]["failures"],
        )
        self.assertEqual(1, checker.main([str(artifact), "--allow-blocked"]))


if __name__ == "__main__":
    unittest.main()
