#!/usr/bin/env python3
"""Focused tests for backend live migration smoke artifact behavior."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_backend_migration_live_smoke.py"
SPEC = importlib.util.spec_from_file_location("run_backend_migration_live_smoke", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


class BackendMigrationLiveSmokeTestCase(unittest.TestCase):
    def test_blocked_environment_writes_redacted_artifact_and_allow_blocked_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "blocked.json"
            blocker = smoke.EnvironmentBlocker(
                reason="postgres_admin_connection_unavailable",
                step="create_database",
                detail="could not connect with password super-secret",
            )

            with patch.object(smoke, "_create_database", side_effect=blocker), contextlib.redirect_stdout(io.StringIO()):
                exit_code = smoke.main(
                    [
                        "--admin-url",
                        "postgresql+psycopg2://postgres:super-secret@localhost:5432/postgres",
                        "--database-name",
                        "mrw_test_smoke",
                        "--output",
                        str(output),
                        "--allow-blocked",
                        "--json",
                    ]
                )

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(0, exit_code)
            self.assertEqual("blocked_by_environment", payload["status"])
            self.assertEqual("postgres_admin_connection_unavailable", payload["blocker"]["reason"])
            self.assertEqual("create_database", payload["steps"][0]["name"])
            self.assertEqual("blocked_by_environment", payload["steps"][0]["status"])
            self.assertIn("***", payload["admin_url_redacted"])
            serialized = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("super-secret", serialized)
            self.assertTrue(payload["blocker"]["diagnostics_redacted"])
            self.assertTrue(payload["steps"][0]["diagnostics_redacted"])
            self.assertIn("docker compose -f main/ops/docker-compose.yml up -d db", payload["recommended_command"])

    def test_blocked_environment_without_allow_blocked_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "blocked.json"
            blocker = smoke.EnvironmentBlocker(
                reason="postgres_admin_connection_unavailable",
                step="create_database",
                detail="could not connect",
            )

            with patch.object(smoke, "_create_database", side_effect=blocker), contextlib.redirect_stdout(io.StringIO()):
                exit_code = smoke.main(
                    [
                        "--database-name",
                        "mrw_test_smoke",
                        "--output",
                        str(output),
                        "--json",
                    ]
                )

            self.assertEqual(1, exit_code)
            self.assertEqual("blocked_by_environment", json.loads(output.read_text(encoding="utf-8"))["status"])

    def test_success_artifact_contains_live_migration_evidence(self) -> None:
        required_tables = ["ingest_submission_registry", "llm_report_quality_trends"]

        def fake_run(command: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
            command_name = command[-1]
            stdout_by_command = {
                "heads": "20260524_000004 (head)\n",
                "head": "upgrade complete\n",
                "current": "20260524_000004 (head)\n",
            }
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=stdout_by_command[command_name],
                stderr="",
            )

        inspection = {
            "alembic_current": "20260524_000004",
            "required_tables": {
                table: {"locations": [{"schema": "public", "table": table}], "columns": ["id"]}
                for table in required_tables
            },
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "passed.json"
            with (
                patch.object(smoke, "_create_database"),
                patch.object(smoke, "_drop_database", return_value=True),
                patch.object(smoke, "_run", side_effect=fake_run),
                patch.object(smoke, "_inspect_database", return_value=inspection),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                exit_code = smoke.main(
                    [
                        "--database-name",
                        "mrw_test_smoke",
                        "--required-table",
                        required_tables[0],
                        "--required-table",
                        required_tables[1],
                        "--output",
                        str(output),
                        "--json",
                    ]
                )

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(0, exit_code)
            self.assertEqual("passed", payload["status"])
            self.assertEqual("20260524_000004", payload["expect_head"])
            self.assertEqual(["20260524_000004"], payload["evidence"]["alembic_heads"]["heads"])
            self.assertEqual("passed", payload["evidence"]["alembic_upgrade"]["status"])
            self.assertEqual("passed", payload["evidence"]["alembic_current"]["status"])
            self.assertEqual(set(required_tables), set(payload["evidence"]["required_tables"]))
            self.assertEqual("passed", payload["evidence"]["drop_database"]["status"])
            self.assertTrue(payload["evidence"]["drop_database"]["database_absent_after"])

    def test_alembic_diagnostics_are_not_written_to_report(self) -> None:
        secret_marker = "synthetic-secret-marker"

        def fake_run(command: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=command,
                returncode=1,
                stdout=f"stdout {secret_marker}",
                stderr=f"No module named alembic; password={secret_marker}",
            )

        with (
            patch.object(smoke, "_create_database"),
            patch.object(smoke, "_drop_database", return_value=True),
            patch.object(smoke, "_run", side_effect=fake_run),
        ):
            report = smoke.run_smoke(
                admin_url="postgresql+psycopg2://admin@/admin_test?host=/socket",
                database_name="mrw_test_smoke",
                expect_head="",
                required_tables=[],
                keep_database=False,
            )

        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(secret_marker, serialized)
        self.assertEqual("blocked_by_environment", report["status"])
        self.assertTrue(report["steps"][1]["diagnostics_redacted"])

    def test_drop_database_reads_back_absence(self) -> None:
        executed: list[tuple[object, object | None]] = []

        class Result:
            def __init__(self, value: object) -> None:
                self.value = value

            def scalar(self) -> object:
                return self.value

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def execute(self, statement: object, parameters: object | None = None) -> Result:
                executed.append((statement, parameters))
                return Result(True)

        class Engine:
            def connect(self) -> Connection:
                return Connection()

            def dispose(self) -> None:
                return None

        with patch.object(smoke, "create_engine", return_value=Engine()):
            absent = smoke._drop_database(
                "postgresql+psycopg2://admin@/admin_test?host=/socket",
                "mrw_test_smoke",
            )

        self.assertTrue(absent)
        self.assertEqual(3, len(executed))
        self.assertIn("SELECT NOT EXISTS", str(executed[-1][0]))
        self.assertEqual({"name": "mrw_test_smoke"}, executed[-1][1])

    def test_drop_database_fails_when_absence_readback_is_false(self) -> None:
        class Result:
            def __init__(self, value: object) -> None:
                self.value = value

            def scalar(self) -> object:
                return self.value

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def execute(self, statement: object, _parameters: object | None = None) -> Result:
                return Result("SELECT NOT EXISTS" not in str(statement))

        class Engine:
            def connect(self) -> Connection:
                return Connection()

            def dispose(self) -> None:
                return None

        with (
            patch.object(smoke, "create_engine", return_value=Engine()),
            self.assertRaisesRegex(RuntimeError, "remains after DROP"),
        ):
            smoke._drop_database(
                "postgresql+psycopg2://admin@/admin_test?host=/socket",
                "mrw_test_smoke",
            )


if __name__ == "__main__":
    unittest.main()
