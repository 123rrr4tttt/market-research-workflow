#!/usr/bin/env python3
"""Focused tests for real-backend browser business-line artifact checks."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "check_business_line_real_backend_browser_artifact.py"
)
SPEC = importlib.util.spec_from_file_location("check_business_line_real_backend_browser_artifact", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class BusinessLineRealBackendBrowserArtifactTestCase(unittest.TestCase):
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
        status: str = checker.STATUS_PASSED,
        proof_level: str = checker.PROOF_LEVEL_REAL_BACKEND_BROWSER,
        mocked: bool = False,
        skipped: bool = False,
    ) -> dict[str, object]:
        return {
            "line_key": line_key,
            "status": status,
            "proof_level": proof_level,
            "mocked": mocked,
            "skipped": skipped,
            "browser": "chromium",
            "base_url": "http://127.0.0.1:4173",
            "api_base_url": "http://127.0.0.1:8000",
        }

    def payload(self, status: str = checker.STATUS_PASSED) -> dict[str, object]:
        return {
            "schema_version": checker.ARTIFACT_SCHEMA_VERSION,
            "status": status,
            "lines": [self.line(line_key) for line_key in checker.REQUIRED_LINE_KEYS],
        }

    def test_passed_artifact_with_all_seven_real_backend_lines_passes(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/real-browser.json", self.payload())

        report = checker.build_report(artifact, root=root)

        self.assertEqual("business_line_real_backend_browser_smoke_check.v1", report["schema_version"])
        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["artifact"]["summary"]["missing_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["unexpected_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["duplicate_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["blocked_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["failed_line_keys"])
        self.assertEqual([], report["artifact"]["summary"]["mocked_or_skipped_line_keys"])
        self.assertEqual(7, report["artifact"]["summary"]["observed_line_count"])
        self.assertEqual(sorted(checker.REQUIRED_LINE_KEYS), report["artifact"]["observed_line_keys"])
        self.assertEqual(0, checker.main([str(artifact)]))

    def test_blocked_artifact_exits_zero_only_when_allowed(self) -> None:
        root = self.make_repo()
        payload = self.payload(status=checker.STATUS_BLOCKED)
        payload["lines"] = [
            self.line(line_key, status=checker.STATUS_BLOCKED, skipped=True)
            for line_key in checker.REQUIRED_LINE_KEYS
        ]
        artifact = self.write_json(root, "artifacts/real-browser-blocked.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("blocked_by_environment", report["status"])
        self.assertEqual(sorted(checker.REQUIRED_LINE_KEYS), report["artifact"]["summary"]["blocked_line_keys"])
        self.assertEqual(1, checker.main([str(artifact)]))
        self.assertEqual(0, checker.main([str(artifact), "--allow-blocked"]))

    def test_missing_line_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"] = [
            line for line in payload["lines"] if line["line_key"] != "runtime_ops"  # type: ignore[index]
        ]
        artifact = self.write_json(root, "artifacts/real-browser.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("runtime_ops", report["artifact"]["summary"]["missing_line_keys"])
        self.assertIn("missing_line_keys", report["artifact"]["structural_failures"])

    def test_unexpected_line_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"].append(self.line("unexpected_line"))  # type: ignore[attr-defined]
        artifact = self.write_json(root, "artifacts/real-browser.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("unexpected_line", report["artifact"]["summary"]["unexpected_line_keys"])
        self.assertIn("unexpected_line_keys", report["artifact"]["structural_failures"])

    def test_duplicate_line_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"].append(self.line("ingest"))  # type: ignore[attr-defined]
        artifact = self.write_json(root, "artifacts/real-browser.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["duplicate_line_keys"])
        self.assertIn("duplicate_line_keys", report["artifact"]["structural_failures"])

    def test_mocked_or_skipped_passed_artifact_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"][0]["mocked"] = True  # type: ignore[index]
        payload["lines"][1]["skipped"] = True  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/real-browser.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertEqual(
            ["ingest", "search_discovery_index"],
            report["artifact"]["summary"]["mocked_or_skipped_line_keys"],
        )
        self.assertIn("line_real_backend_browser_fields", report["artifact"]["structural_failures"])
        self.assertIn("not_mocked", report["artifact"]["lines"][0]["violations"])
        self.assertIn("not_skipped", report["artifact"]["lines"][1]["violations"])

    def test_wrong_proof_level_passed_artifact_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["lines"][0]["proof_level"] = "mocked_browser_smoke"  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/real-browser.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["incomplete_line_keys"])
        self.assertIn("real_backend_browser_proof_level", report["artifact"]["lines"][0]["violations"])

    def test_failed_artifact_fails_even_when_blocked_is_allowed(self) -> None:
        root = self.make_repo()
        payload = self.payload(status=checker.STATUS_FAILED)
        artifact = self.write_json(root, "artifacts/real-browser-failed.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("failed_artifact_status", report["artifact"]["structural_failures"])
        self.assertEqual(1, checker.main([str(artifact), "--allow-blocked"]))

    def test_failed_line_fails_even_when_blocked_is_allowed(self) -> None:
        root = self.make_repo()
        payload = self.payload(status=checker.STATUS_BLOCKED)
        payload["lines"][0]["status"] = checker.STATUS_FAILED  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/real-browser-failed-line.json", payload)

        report = checker.build_report(artifact, root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("ingest", report["artifact"]["summary"]["failed_line_keys"])
        self.assertEqual(1, checker.main([str(artifact), "--allow-blocked"]))


if __name__ == "__main__":
    unittest.main()
