#!/usr/bin/env python3
"""Tests for building canonical real-backend browser artifacts from Playwright JSON."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "build_business_line_real_backend_browser_artifact.py"
)
SPEC = importlib.util.spec_from_file_location("build_business_line_real_backend_browser_artifact", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


class BuildBusinessLineRealBackendBrowserArtifactTestCase(unittest.TestCase):
    def make_temp_path(self, name: str) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / name

    def write_json_report(self, payload: object, *, prefix: str = "") -> Path:
        path = self.make_temp_path("playwright.json")
        import json

        path.write_text(prefix + json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def spec(self, line_key: str, status: str = "passed") -> dict[str, object]:
        return {
            "title": f"real-backend business line smoke [line_key={line_key}] classifies endpoint",
            "tests": [
                {
                    "projectName": "chromium",
                    "results": [
                        {
                            "status": status,
                            "duration": 12,
                        }
                    ],
                }
            ],
        }

    def report(self, statuses: dict[str, str] | None = None) -> dict[str, object]:
        statuses = statuses or {}
        return {
            "suites": [
                {
                    "title": "real-backend-business-lines.spec.ts",
                    "specs": [
                        self.spec(line_key, statuses.get(line_key, "passed"))
                        for line_key in builder.REQUIRED_LINE_KEYS
                    ],
                    "suites": [],
                }
            ]
        }

    def test_builds_passed_artifact_from_all_passed_specs(self) -> None:
        artifact = builder.build_artifact(
            self.report(),
            source_path=Path("/tmp/playwright.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual(builder.ARTIFACT_SCHEMA_VERSION, artifact["schema_version"])
        self.assertEqual("passed", artifact["status"])
        self.assertEqual(7, len(artifact["lines"]))
        self.assertEqual([], artifact["summary"]["blocked_line_keys"])
        self.assertEqual([], artifact["summary"]["failed_line_keys"])
        self.assertTrue(all(line["proof_level"] == "real_backend_browser_smoke" for line in artifact["lines"]))
        self.assertTrue(all(line["mocked"] is False for line in artifact["lines"]))
        self.assertTrue(all(line["skipped"] is False for line in artifact["lines"]))

    def test_skipped_specs_build_blocked_artifact_not_passed(self) -> None:
        artifact = builder.build_artifact(
            self.report({line_key: "skipped" for line_key in builder.REQUIRED_LINE_KEYS}),
            source_path=Path("/tmp/playwright.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("blocked_by_environment", artifact["status"])
        self.assertEqual(sorted(builder.REQUIRED_LINE_KEYS), sorted(artifact["summary"]["blocked_line_keys"]))
        self.assertTrue(all(line["skipped"] is True for line in artifact["lines"]))

    def test_failed_spec_builds_failed_artifact(self) -> None:
        artifact = builder.build_artifact(
            self.report({"ingest": "failed"}),
            source_path=Path("/tmp/playwright.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("failed", artifact["status"])
        self.assertEqual(["ingest"], artifact["summary"]["failed_line_keys"])
        ingest = [line for line in artifact["lines"] if line["line_key"] == "ingest"][0]
        self.assertEqual("playwright_test_failed", ingest["reason"])

    def test_missing_line_builds_failed_line(self) -> None:
        report = self.report()
        report["suites"][0]["specs"] = [  # type: ignore[index]
            spec
            for spec in report["suites"][0]["specs"]  # type: ignore[index]
            if "[line_key=runtime_ops]" not in spec["title"]
        ]

        artifact = builder.build_artifact(
            report,
            source_path=Path("/tmp/playwright.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("failed", artifact["status"])
        self.assertIn("runtime_ops", artifact["summary"]["failed_line_keys"])
        runtime_ops = [line for line in artifact["lines"] if line["line_key"] == "runtime_ops"][0]
        self.assertEqual("missing_playwright_spec_for_line_key", runtime_ops["reason"])

    def test_load_json_accepts_npm_script_banner_before_playwright_json(self) -> None:
        report_path = self.write_json_report(
            self.report(),
            prefix="\n> frontend-modern@0.1.8-rc1 test:e2e:real-backend-business-lines\n> playwright test\n\n",
        )

        payload = builder.load_json(report_path)

        self.assertIn("suites", payload)


if __name__ == "__main__":
    unittest.main()
