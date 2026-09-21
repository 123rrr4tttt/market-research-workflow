#!/usr/bin/env python3
"""Focused tests for offline business trace/source readback contract checks."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_business_trace_readback_contract.py"
SPEC = importlib.util.spec_from_file_location("check_business_trace_readback_contract", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class BusinessTraceReadbackContractTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def write_json(self, root: Path, rel_path: str, payload: object) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def test_search_artifact_with_trace_source_and_provider_passes(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(
            root,
            "artifacts/search-response.json",
            {
                "status": "success",
                "data": {
                    "business_line": "search",
                    "trace_chain": [{"stage": "request", "trace_id": "trace-search-1"}],
                    "source_refs": [{"kind": "search_retrieval_run", "retrieval_run_id": "run-1"}],
                    "provider_trace": {"provider": "test", "request_id": "provider-1"},
                },
            },
        )

        report = checker.build_report([artifact], root=root)

        self.assertEqual("passed", report["status"])
        self.assertEqual(1, report["summary"]["passed_count"])
        row = report["artifacts"][0]
        self.assertEqual("search", row["business_line"])
        self.assertEqual([], row["missing_contract_fields"])
        self.assertEqual("passed", row["checks"]["search_provider_or_readback"]["status"])

    def test_dashboard_missing_source_fails(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(
            root,
            "artifacts/dashboard-response.json",
            {
                "status": "success",
                "data": {
                    "business_line": "dashboard",
                    "trace_id": "trace-dashboard-1",
                    "summary": {"ready": True},
                },
            },
        )

        report = checker.build_report([artifact], root=root)

        self.assertEqual("failed", report["status"])
        row = report["artifacts"][0]
        self.assertEqual("failed", row["status"])
        self.assertIn("source_refs_or_source_query", row["missing_contract_fields"])
        self.assertEqual("passed", row["checks"]["trace_readback"]["status"])

    def test_ingest_missing_trace_fails(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(
            root,
            "artifacts/ingest-response.json",
            {
                "status": "success",
                "data": {
                    "business_line": "ingest",
                    "submission_id": "sub-1",
                    "source_query": {"document_id": "doc-1"},
                },
            },
        )

        report = checker.build_report([artifact], root=root)

        self.assertEqual("failed", report["status"])
        row = report["artifacts"][0]
        self.assertIn("trace_chain_or_trace_id", row["missing_contract_fields"])
        self.assertEqual("passed", row["checks"]["source_readback"]["status"])
        self.assertEqual("passed", row["checks"]["ingest_trace_identity"]["status"])

    def test_ingest_empty_trace_without_identity_fails(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(
            root,
            "artifacts/ingest-response.json",
            {
                "status": "success",
                "data": {
                    "business_line": "ingest",
                    "trace_chain": [],
                    "source_query": {"document_id": "doc-1"},
                },
            },
        )

        report = checker.build_report([artifact], root=root)

        self.assertEqual("failed", report["status"])
        row = report["artifacts"][0]
        self.assertIn("trace_chain_or_trace_id", row["missing_contract_fields"])
        self.assertIn("ingest_trace_identity", row["missing_contract_fields"])
        self.assertEqual("failed", row["checks"]["ingest_trace_identity"]["status"])

    def test_ingest_trace_chain_object_identity_passes(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(
            root,
            "artifacts/ingest-response.json",
            {
                "status": "success",
                "data": {
                    "business_line": "ingest",
                    "trace_chain": {
                        "contract_version": "ingest_search.trace_chain.v1",
                        "trace_id": "trace-ingest-2",
                        "ids": {"retrieval_run_id": "run-2"},
                    },
                    "source_query": {"document_id": "doc-2"},
                },
            },
        )

        report = checker.build_report([artifact], root=root)

        self.assertEqual("passed", report["status"])
        row = report["artifacts"][0]
        self.assertEqual([], row["missing_contract_fields"])
        self.assertEqual("passed", row["checks"]["ingest_trace_identity"]["status"])
        self.assertIn("data.trace_chain.ids.retrieval_run_id", row["checks"]["ingest_trace_identity"]["matched_paths"])

    def test_admin_preview_missing_evidence_preview_or_risk_fails(self) -> None:
        root = self.make_repo()
        missing_evidence = self.write_json(
            root,
            "artifacts/admin-missing-evidence.json",
            {
                "status": "success",
                "data": {
                    "business_line": "admin",
                    "trace_chain": [{"stage": "preview"}],
                    "source_refs": [{"kind": "document", "id": "doc-1"}],
                    "risk_labels": ["destructive"],
                },
            },
        )
        missing_risk = self.write_json(
            root,
            "artifacts/admin-missing-risk.json",
            {
                "status": "success",
                "data": {
                    "business_line": "admin",
                    "trace_chain": [{"stage": "preview"}],
                    "source_refs": [{"kind": "document", "id": "doc-2"}],
                    "evidence_preview": {"execution_result_available": False},
                },
            },
        )

        report = checker.build_report([missing_evidence, missing_risk], root=root)

        self.assertEqual("failed", report["status"])
        rows = {Path(row["artifact_path"]).name: row for row in report["artifacts"]}
        self.assertIn("evidence_preview", rows["admin-missing-evidence.json"]["missing_contract_fields"])
        self.assertEqual(
            "failed",
            rows["admin-missing-evidence.json"]["checks"]["admin_preview_evidence"]["status"],
        )
        self.assertIn("risk_tags_or_risk_labels", rows["admin-missing-risk.json"]["missing_contract_fields"])
        self.assertEqual(
            "failed",
            rows["admin-missing-risk.json"]["checks"]["admin_preview_evidence"]["status"],
        )

    def test_search_missing_provider_or_readback_fails_even_with_trace_and_source(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(
            root,
            "artifacts/search-response.json",
            {
                "status": "success",
                "data": {
                    "business_line": "search",
                    "trace_id": "trace-search-2",
                    "source_query": {"query": "battery market"},
                },
            },
        )

        report = checker.build_report([artifact], root=root)

        self.assertEqual("failed", report["status"])
        row = report["artifacts"][0]
        self.assertIn(
            "provider_trace_or_retrieval_run_readback_or_index_freshness",
            row["missing_contract_fields"],
        )
        self.assertEqual("failed", row["checks"]["search_provider_or_readback"]["status"])

    def test_multiple_artifacts_mixed_failure_fails_summary(self) -> None:
        root = self.make_repo()
        passed_admin = self.write_json(
            root,
            "artifacts/admin-preview.json",
            {
                "status": "success",
                "data": {
                    "business_line": "admin",
                    "trace_chain": [{"stage": "preview"}],
                    "source_refs": [{"kind": "document", "id": "doc-1"}],
                    "evidence_preview": {"execution_result_available": False},
                    "operation_preview": {"risk_labels": ["destructive"]},
                },
            },
        )
        failed_search = self.write_json(
            root,
            "artifacts/search-response.json",
            {
                "status": "success",
                "data": {
                    "business_line": "search",
                    "source_refs": [{"kind": "search_retrieval_run", "retrieval_run_id": "run-2"}],
                    "retrieval_run_readback": {"status": "passed"},
                },
            },
        )

        report = checker.build_report([passed_admin, failed_search], root=root)

        self.assertEqual("failed", report["status"])
        self.assertEqual(2, report["summary"]["artifact_count"])
        self.assertEqual(1, report["summary"]["passed_count"])
        self.assertEqual(1, report["summary"]["failed_count"])
        failures = [row for row in report["artifacts"] if row["status"] == "failed"]
        self.assertEqual(1, len(failures))
        self.assertIn("trace_chain_or_trace_id", failures[0]["missing_contract_fields"])


if __name__ == "__main__":
    unittest.main()
