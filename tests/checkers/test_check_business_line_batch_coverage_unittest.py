#!/usr/bin/env python3
"""Focused tests for offline business-line batch coverage gate."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_business_line_batch_coverage.py"
SPEC = importlib.util.spec_from_file_location("check_business_line_batch_coverage", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class BusinessLineBatchCoverageTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def write_json(self, root: Path, rel_path: str, payload: object) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def valid_line(self, line_key: str) -> dict[str, object]:
        return {
            "line_key": line_key,
            "current_gaps": [f"{line_key} current gap"],
            "next_remediation": f"{line_key} remediation in this batch",
            "verification_commands": [f"pytest {line_key}"],
        }

    def valid_payload(self) -> dict[str, object]:
        return {
            "contract_version": checker.CONTRACT_VERSION,
            "lines": [self.valid_line(line_key) for line_key in checker.REQUIRED_LINE_KEYS],
        }

    def test_full_seven_line_matrix_passes(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "artifacts/evidence-matrix.json", self.valid_payload())

        report = checker.build_report([artifact], root=root)

        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["summary"]["missing_line_keys"])
        self.assertEqual(7, report["summary"]["observed_line_count"])
        self.assertEqual(sorted(checker.REQUIRED_LINE_KEYS), report["observed_line_keys"])

    def test_missing_line_fails_summary(self) -> None:
        root = self.make_repo()
        payload = self.valid_payload()
        payload["lines"] = [
            line for line in payload["lines"] if line["line_key"] != "runtime_ops"  # type: ignore[index]
        ]
        artifact = self.write_json(root, "artifacts/evidence-matrix.json", payload)

        report = checker.build_report([artifact], root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("runtime_ops", report["summary"]["missing_line_keys"])
        self.assertEqual(6, report["summary"]["observed_line_count"])

    def test_missing_required_line_field_fails(self) -> None:
        root = self.make_repo()
        payload = self.valid_payload()
        first_line = payload["lines"][0]  # type: ignore[index]
        del first_line["verification_commands"]  # type: ignore[index]
        artifact = self.write_json(root, "artifacts/evidence-matrix.json", payload)

        report = checker.build_report([artifact], root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn(str(first_line["line_key"]), report["summary"]["incomplete_line_keys"])  # type: ignore[index]
        rows = report["line_rows"][str(first_line["line_key"])]  # type: ignore[index]
        self.assertIn("verification_commands", rows[0]["missing_fields"])

    def test_wrong_contract_version_fails_even_when_lines_are_complete(self) -> None:
        root = self.make_repo()
        payload = self.valid_payload()
        payload["contract_version"] = "business_line.evidence_matrix.v0"
        artifact = self.write_json(root, "artifacts/evidence-matrix.json", payload)

        report = checker.build_report([artifact], root=root)

        self.assertEqual("failed", report["status"])
        self.assertIn("contract_version", report["artifacts"][0]["missing_contract_fields"])

    def test_multiple_artifacts_can_supply_the_full_batch_matrix(self) -> None:
        root = self.make_repo()
        first = self.write_json(
            root,
            "artifacts/evidence-matrix-a.json",
            {
                "contract_version": checker.CONTRACT_VERSION,
                "lines": [self.valid_line(line_key) for line_key in checker.REQUIRED_LINE_KEYS[:3]],
            },
        )
        second = self.write_json(
            root,
            "artifacts/evidence-matrix-b.json",
            {
                "data": {
                    "contract_version": checker.CONTRACT_VERSION,
                    "evidence_matrix": {
                        line_key: self.valid_line(line_key) for line_key in checker.REQUIRED_LINE_KEYS[3:]
                    },
                },
            },
        )

        report = checker.build_report([first, second], root=root)

        self.assertEqual("passed", report["status"])
        self.assertEqual(7, report["summary"]["observed_line_count"])


if __name__ == "__main__":
    unittest.main()
