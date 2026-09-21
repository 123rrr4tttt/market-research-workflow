#!/usr/bin/env python3
"""Focused tests for building business-line async readiness artifacts."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_business_line_async_readiness_artifact.py"
SPEC = importlib.util.spec_from_file_location("build_business_line_async_readiness_artifact", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


class BusinessLineAsyncReadinessBuilderTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def write_json(self, root: Path, rel_path: str, payload: object) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def evidence_line(self, line_key: str, *, requires_worker: bool) -> dict[str, object]:
        return {
            "line_key": line_key,
            "async_execution_readiness": {
                "requires_worker": requires_worker,
                "async_surfaces": [f"{line_key} async surface"],
                "verification_artifact": f"business_line_async_worker_readiness.{line_key}.v1",
            },
        }

    def evidence_matrix(self) -> dict[str, object]:
        worker_lines = {
            "ingest",
            "search_discovery_index",
            "resource_source_library",
            "writing_knowledge_graph_agent",
        }
        return {
            "contract_version": "business_line.evidence_matrix.v1",
            "lines": [
                self.evidence_line(line_key, requires_worker=line_key in worker_lines)
                for line_key in builder.REQUIRED_LINE_KEYS
            ],
        }

    def runtime_matrix(self, *, worker_status: str = builder.STATUS_PASSED, reason: str | None = None) -> dict[str, object]:
        mode_status = "worker_blocked" if worker_status == builder.STATUS_BLOCKED else worker_status
        check: dict[str, object] = {
            "check_id": "celery_worker_process_stats",
            "status": worker_status,
            "blocked": worker_status == builder.STATUS_BLOCKED,
            "worker_online": worker_status == builder.STATUS_PASSED,
            "worker_count": 1 if worker_status == builder.STATUS_PASSED else 0,
        }
        if reason is not None:
            check["reason"] = reason
        return {
            "schema_version": "mrw.runtime_health_matrix.v1",
            "status": mode_status,
            "runtime_modes": [
                {
                    "mode": "local",
                    "status": mode_status,
                    "checked_async_readiness": [check],
                }
            ],
        }

    def test_builds_passed_artifact_when_local_worker_passed(self) -> None:
        artifact = builder.build_artifact(
            self.evidence_matrix(),
            self.runtime_matrix(),
            evidence_matrix_path=Path("evidence.json"),
            runtime_matrix_path=Path("runtime.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual(builder.ARTIFACT_SCHEMA_VERSION, artifact["schema_version"])
        self.assertEqual("passed", artifact["status"])
        self.assertEqual([], artifact["summary"]["blocked_line_keys"])
        self.assertEqual([], artifact["summary"]["failed_line_keys"])
        self.assertEqual(
            [
                "ingest",
                "search_discovery_index",
                "resource_source_library",
                "writing_knowledge_graph_agent",
            ],
            artifact["summary"]["requires_worker_line_keys"],
        )
        self.assertEqual(7, len(artifact["lines"]))
        non_worker_lines = [line for line in artifact["lines"] if line["requires_worker"] is False]
        self.assertTrue(non_worker_lines)
        self.assertTrue(
            all(line["reason"] == "sync_or_read_only_async_not_required" for line in non_worker_lines)
        )

    def test_worker_blocked_blocks_only_requires_worker_lines(self) -> None:
        artifact = builder.build_artifact(
            self.evidence_matrix(),
            self.runtime_matrix(worker_status=builder.STATUS_BLOCKED, reason="celery_worker_unavailable"),
            evidence_matrix_path=Path("evidence.json"),
            runtime_matrix_path=Path("runtime.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("blocked_by_environment", artifact["status"])
        self.assertEqual(
            [
                "ingest",
                "search_discovery_index",
                "resource_source_library",
                "writing_knowledge_graph_agent",
            ],
            artifact["summary"]["blocked_line_keys"],
        )
        self.assertNotIn("projects_config_workflow", artifact["summary"]["blocked_line_keys"])
        self.assertIn("projects_config_workflow", artifact["summary"]["passed_line_keys"])

    def test_missing_duplicate_and_unexpected_evidence_lines_fail_artifact(self) -> None:
        evidence = self.evidence_matrix()
        lines = evidence["lines"]
        assert isinstance(lines, list)
        evidence["lines"] = [
            line for line in lines if line["line_key"] != "runtime_ops"  # type: ignore[index]
        ]
        evidence["lines"].append(self.evidence_line("ingest", requires_worker=True))  # type: ignore[attr-defined]
        evidence["lines"].append(self.evidence_line("unexpected_line", requires_worker=False))  # type: ignore[attr-defined]

        artifact = builder.build_artifact(
            evidence,
            self.runtime_matrix(),
            evidence_matrix_path=Path("evidence.json"),
            runtime_matrix_path=Path("runtime.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("failed", artifact["status"])
        self.assertEqual(["runtime_ops"], artifact["summary"]["missing_line_keys"])
        self.assertEqual(["ingest"], artifact["summary"]["duplicate_line_keys"])
        self.assertEqual(["unexpected_line"], artifact["summary"]["unexpected_line_keys"])
        self.assertIn("runtime_ops", artifact["summary"]["failed_line_keys"])

    def test_worker_failure_fails_requires_worker_lines(self) -> None:
        artifact = builder.build_artifact(
            self.evidence_matrix(),
            self.runtime_matrix(worker_status=builder.STATUS_FAILED, reason="worker_readiness_failed"),
            evidence_matrix_path=Path("evidence.json"),
            runtime_matrix_path=Path("runtime.json"),
            observed_at="2026-05-25T00:00:00Z",
        )

        self.assertEqual("failed", artifact["status"])
        self.assertIn("ingest", artifact["summary"]["failed_line_keys"])
        self.assertNotIn("runtime_ops", artifact["summary"]["failed_line_keys"])

    def test_main_writes_output_file(self) -> None:
        root = self.make_repo()
        evidence_path = self.write_json(root, "evidence.json", self.evidence_matrix())
        runtime_path = self.write_json(root, "runtime.json", self.runtime_matrix())
        output_path = root / "artifact.json"

        exit_code = builder.main(
            [
                "--evidence-matrix",
                str(evidence_path),
                "--runtime-matrix",
                str(runtime_path),
                "--output",
                str(output_path),
            ]
        )

        self.assertEqual(0, exit_code)
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(builder.ARTIFACT_SCHEMA_VERSION, payload["schema_version"])
        self.assertEqual("passed", payload["status"])


if __name__ == "__main__":
    unittest.main()
