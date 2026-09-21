#!/usr/bin/env python3
"""Run backend Alembic migrations against a disposable PostgreSQL database."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "main" / "backend"
DEFAULT_ADMIN_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"
DEFAULT_EXPECT_HEAD = ""
DEFAULT_REQUIRED_TABLES = (
    "ingest_submission_registry",
    "llm_report_quality_trends",
    "llm_report_export_audit_events",
    "llm_report_export_token_states",
)


class EnvironmentBlocker(RuntimeError):
    """Raised when live migration proof cannot run without external services."""

    def __init__(self, *, reason: str, step: str, detail: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.step = step
        self.detail = detail


def _database_name_from_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    name = parsed.path.lstrip("/")
    if not name:
        raise ValueError("database URL must include a database name")
    return name


def _url_for_database(database_url: str, database_name: str) -> str:
    parsed = urlparse(database_url)
    return urlunparse(parsed._replace(path=f"/{database_name}"))


def _redact_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if parsed.password is None:
        return database_url
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    user = parsed.username or ""
    netloc = f"{user}:***@{host}" if user else host
    return urlunparse(parsed._replace(netloc=netloc))


def _quote_pg_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _run(command: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(BACKEND_DIR),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _backend_python() -> str:
    configured = os.environ.get("MRW_BACKEND_PYTHON", "").strip()
    if configured:
        return configured
    return shutil.which("python3.11") or sys.executable


def _command_step(name: str, completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    return {
        "name": name,
        "status": "passed" if completed.returncode == 0 else "failed",
        "command": completed.args,
        "returncode": completed.returncode,
        "stdout_length": len(stdout),
        "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
        "stderr_length": len(stderr),
        "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        "diagnostics_redacted": True,
    }


def _parse_alembic_heads(stdout: str) -> list[str]:
    heads: list[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        heads.append(stripped.split()[0])
    return heads


def _subprocess_environment_blocker(
    step: dict[str, object], stderr: str
) -> dict[str, object] | None:
    if "unsupported operand type(s) for |" in stderr:
        return {
            "reason": "backend_python_incompatible",
            "step": str(step.get("name", "alembic")),
            "diagnostics_redacted": True,
        }
    if "No module named alembic" in stderr:
        return {
            "reason": "backend_alembic_dependency_missing",
            "step": str(step.get("name", "alembic")),
            "diagnostics_redacted": True,
        }
    return None


def _recommended_command(database_name: str) -> str:
    return (
        "docker compose -f main/ops/docker-compose.yml up -d db && "
        "python3 scripts/run_backend_migration_live_smoke.py "
        f"--database-name {database_name} "
        "--output /tmp/mrw_migration_smoke_batch60.json --allow-blocked --json"
    )


def _create_database(admin_url: str, database_name: str) -> None:
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": database_name},
            ).scalar()
            if exists:
                raise RuntimeError(f"temporary database already exists: {database_name}")
            conn.execute(text(f"CREATE DATABASE {_quote_pg_identifier(database_name)}"))
    except SQLAlchemyError as exc:
        raise EnvironmentBlocker(
            reason="postgres_admin_connection_unavailable",
            step="create_database",
            detail=str(exc),
        ) from exc
    finally:
        engine.dispose()


def _drop_database(admin_url: str, database_name: str) -> bool:
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :name AND pid <> pg_backend_pid()
                    """
                ),
                {"name": database_name},
            )
            conn.execute(text(f"DROP DATABASE IF EXISTS {_quote_pg_identifier(database_name)}"))
            database_absent_after = bool(
                conn.execute(
                    text("SELECT NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :name)"),
                    {"name": database_name},
                ).scalar()
            )
            if not database_absent_after:
                raise RuntimeError(
                    f"temporary database remains after DROP: {database_name}"
                )
            return database_absent_after
    finally:
        engine.dispose()


def _inspect_database(database_url: str, *, required_tables: list[str]) -> dict[str, object]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            table_reports: dict[str, dict[str, object]] = {}
            for required_table in required_tables:
                table_rows = conn.execute(
                    text(
                        """
                        SELECT table_schema, table_name
                        FROM information_schema.tables
                        WHERE table_name = :table_name
                        ORDER BY table_schema, table_name
                        """
                    ),
                    {"table_name": required_table},
                ).fetchall()
                columns = conn.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = :table_name
                        ORDER BY ordinal_position
                        """
                    ),
                    {"table_name": required_table},
                ).fetchall()
                table_reports[required_table] = {
                    "locations": [{"schema": str(row[0]), "table": str(row[1])} for row in table_rows],
                    "columns": [str(row[0]) for row in columns],
                }
    finally:
        engine.dispose()

    return {
        "alembic_current": str(current or ""),
        "required_tables": table_reports,
    }


def run_smoke(
    *,
    admin_url: str,
    database_name: str,
    expect_head: str,
    required_tables: list[str],
    keep_database: bool,
) -> dict[str, object]:
    temp_url = _url_for_database(admin_url, database_name)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report: dict[str, object] = {
        "status": "failed",
        "started_at": started_at,
        "backend_dir": str(BACKEND_DIR),
        "python_executable": _backend_python(),
        "admin_url_redacted": _redact_url(admin_url),
        "database_name": database_name,
        "expect_head": expect_head,
        "required_tables": required_tables,
        "kept_database": keep_database,
        "recommended_command": _recommended_command(database_name),
        "steps": [],
        "evidence": {},
    }

    created = False
    try:
        try:
            _create_database(admin_url, database_name)
        except EnvironmentBlocker as exc:
            report["status"] = "blocked_by_environment"
            report["blocker"] = {
                "reason": exc.reason,
                "step": exc.step,
                "admin_url_redacted": _redact_url(admin_url),
                "diagnostics_redacted": True,
            }
            report["steps"].append(
                {
                    "name": exc.step,
                    "status": "blocked_by_environment",
                    "reason": exc.reason,
                    "diagnostics_redacted": True,
                }
            )
            return report
        created = True
        report["steps"].append({"name": "create_database", "status": "passed"})

        env = dict(os.environ)
        env["DATABASE_URL"] = temp_url
        python_executable = str(report["python_executable"])
        heads_completed = _run([python_executable, "-m", "alembic", "heads"], env=env)
        heads_step = _command_step("alembic_heads", heads_completed)
        heads = _parse_alembic_heads(heads_completed.stdout)
        heads_step["heads"] = heads
        report["steps"].append(heads_step)
        report["evidence"]["alembic_heads"] = heads_step
        if heads_completed.returncode != 0:
            blocker = _subprocess_environment_blocker(
                heads_step, heads_completed.stderr
            )
            if blocker:
                report["status"] = "blocked_by_environment"
                report["blocker"] = blocker
            report["error"] = "alembic heads failed"
            return report
        if not expect_head:
            if len(heads) == 1:
                expect_head = heads[0]
                report["expect_head"] = expect_head
            else:
                report["error"] = f"expected one alembic head, found {len(heads)}: {heads}"
                return report

        completed = _run([python_executable, "-m", "alembic", "upgrade", "head"], env=env)
        upgrade_step = _command_step("alembic_upgrade_head", completed)
        report["steps"].append(upgrade_step)
        report["evidence"]["alembic_upgrade"] = upgrade_step
        if completed.returncode != 0:
            blocker = _subprocess_environment_blocker(
                upgrade_step, completed.stderr
            )
            if blocker:
                report["status"] = "blocked_by_environment"
                report["blocker"] = blocker
            report["error"] = "alembic upgrade head failed"
            return report

        current_completed = _run([python_executable, "-m", "alembic", "current"], env=env)
        current_step = _command_step("alembic_current", current_completed)
        report["steps"].append(current_step)
        report["evidence"]["alembic_current"] = current_step
        if current_completed.returncode != 0:
            blocker = _subprocess_environment_blocker(
                current_step, current_completed.stderr
            )
            if blocker:
                report["status"] = "blocked_by_environment"
                report["blocker"] = blocker
            report["error"] = "alembic current failed"
            return report

        inspection = _inspect_database(temp_url, required_tables=required_tables)
        report["inspection"] = inspection
        report["evidence"]["required_tables"] = inspection["required_tables"]
        current = inspection["alembic_current"]
        if current != expect_head:
            report["error"] = f"expected alembic current {expect_head}, got {current}"
            return report
        for required_table in required_tables:
            locations = inspection["required_tables"].get(required_table, {}).get("locations", [])
            if not locations:
                report["error"] = f"required table missing after migration: {required_table}"
                return report
        report["steps"].append({"name": "inspect_database", "status": "passed"})
        report["status"] = "passed"
        return report
    finally:
        if created and not keep_database:
            drop_step: dict[str, object] = {"name": "drop_database", "status": "passed"}
            try:
                drop_step["database_absent_after"] = _drop_database(
                    admin_url, database_name
                )
            except Exception as exc:  # noqa: BLE001
                drop_step = {
                    "name": "drop_database",
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "diagnostics_redacted": True,
                }
                if report.get("status") == "passed":
                    report["status"] = "failed"
                    report["error"] = "drop_database failed"
            report["steps"].append(drop_step)
            report["evidence"]["drop_database"] = drop_step
        elif created and keep_database:
            keep_step = {"name": "drop_database", "status": "skipped", "reason": "keep_database"}
            report["steps"].append(keep_step)
            report["evidence"]["drop_database"] = keep_step


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-url", default=os.environ.get("DATABASE_URL", DEFAULT_ADMIN_URL))
    parser.add_argument("--database-name", default=f"mrw_migration_smoke_{int(time.time())}")
    parser.add_argument("--expect-head", default=DEFAULT_EXPECT_HEAD)
    parser.add_argument("--required-table", action="append", default=[])
    parser.add_argument("--keep-database", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-blocked", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    database_name = args.database_name.strip()
    if not database_name:
        database_name = f"mrw_migration_smoke_{int(time.time())}"
    admin_database = _database_name_from_url(args.admin_url)
    if database_name == admin_database:
        print("Refusing to use the admin database as the disposable smoke database.", file=sys.stderr)
        return 2

    required_tables = list(args.required_table or []) or list(DEFAULT_REQUIRED_TABLES)
    try:
        report = run_smoke(
            admin_url=args.admin_url,
            database_name=database_name,
            expect_head=args.expect_head.strip(),
            required_tables=required_tables,
            keep_database=args.keep_database,
        )
    except Exception as exc:  # noqa: BLE001
        report = {
            "status": "failed",
            "admin_url_redacted": _redact_url(args.admin_url),
            "database_name": database_name,
            "expect_head": args.expect_head.strip(),
            "required_tables": required_tables,
            "recommended_command": _recommended_command(database_name),
            "steps": [],
            "evidence": {},
            "error_type": type(exc).__name__,
            "diagnostics_redacted": True,
        }
    if args.output:
        _write_json(args.output, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "backend_migration_live_smoke="
            f"{report['status']} database={database_name} "
            f"head={report.get('inspection', {}).get('alembic_current', '')}"
        )
    if report["status"] == "passed":
        return 0
    if report["status"] == "blocked_by_environment" and args.allow_blocked:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
