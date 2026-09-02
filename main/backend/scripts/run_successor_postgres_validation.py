#!/usr/bin/env python3
"""Run a bounded PostgreSQL validation command on a disposable local database.

The runner connects to a local PostgreSQL admin cluster over a Unix socket
only, creates one uniquely named disposable database and one non-superuser
role per invocation, runs the supplied child command with a constrained child
environment, and in ``finally`` drops only the database and role it created.

Safety invariants:

- ``--database-url`` is required (or ``SUCCESSOR_POSTGRES_VALIDATION_DATABASE_URL``);
  there is no production/default target fallback.
- The URL must use a PostgreSQL driver and a Unix socket host (empty host or
  an absolute socket directory).  TCP hosts and passwords are rejected.
- Database/role names are always ``mrw_successor_validation_<token>`` where
  the token matches ``^[a-z0-9]{16}$``; every DROP is guarded by the same
  exact regex and never uses a wildcard.
- A unique token is generated per invocation; an already-existing database or
  role with the same name fails closed before any mutation.
- The child runs as the disposable non-superuser role, receives only the
  explicit child environment, and is invoked with an argument list
  (``shell=False``).
- Public-schema successor table and ``mrw_*`` schema residuals are observed
  before and after the run; teardown failure or residual growth fails the run.

CLI exit codes: 0 = validation passed and teardown clean, 1 = child validation
failed or residuals changed, 2 = usage/guard/execution/teardown error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPORT_SCHEMA = "mrw.functorial_successor.postgres_validation_report.v1"
NAME_PREFIX = "mrw_successor_validation_"
TOKEN_RE = re.compile(r"^[a-z0-9]{16}$")
OWNED_NAME_RE = re.compile(rf"^{NAME_PREFIX}[a-z0-9]{{16}}$")
FORBIDDEN_ADMIN_DATABASES = frozenset({"postgres", "template0", "template1"})
SUCCESSOR_TABLE_PREFIXES = ("runtime_", "successor_")
SCHEMA_PREFIX = "mrw_"
ADMIN_URL_ENV = "SUCCESSOR_POSTGRES_VALIDATION_DATABASE_URL"
CHILD_DATABASE_URL_ENV = "SUCCESSOR_TEST_DATABASE_URL"


class ValidationRunnerError(RuntimeError):
    """Fail-closed guard or execution error with a stable message."""


@dataclass(frozen=True, slots=True)
class RunnerIssue:
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True, slots=True)
class PostgresValidationReport:
    status: str
    exit_code: int
    database_name: str | None
    role_name: str | None
    socket_only: bool
    admin_superuser: bool
    residual_before: Mapping[str, int]
    residual_after: Mapping[str, int]
    residual_clean: bool
    child_command: tuple[str, ...]
    child_returncode: int | None
    child_stdout_digest: str | None
    child_stderr_digest: str | None
    created_database: bool
    created_role: bool
    dropped_database: bool
    dropped_role: bool
    database_absent_after: bool
    role_absent_after: bool
    issues: tuple[RunnerIssue, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": REPORT_SCHEMA,
            "status": self.status,
            "exit_code": self.exit_code,
            "database_name": self.database_name,
            "role_name": self.role_name,
            "socket_only": self.socket_only,
            "admin_superuser": self.admin_superuser,
            "residual_before": dict(self.residual_before),
            "residual_after": dict(self.residual_after),
            "residual_clean": self.residual_clean,
            "child_command": list(self.child_command),
            "child_returncode": self.child_returncode,
            "child_stdout_digest": self.child_stdout_digest,
            "child_stderr_digest": self.child_stderr_digest,
            "created_database": self.created_database,
            "created_role": self.created_role,
            "dropped_database": self.dropped_database,
            "dropped_role": self.dropped_role,
            "database_absent_after": self.database_absent_after,
            "role_absent_after": self.role_absent_after,
            "issues": [issue.as_dict() for issue in self.issues],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True)


class PostgresAdminClient:
    """Minimal psycopg2 client used only for local disposable-DB management."""

    def __init__(self, admin_url: str) -> None:
        self._admin_url = admin_url
        self._connection: Any = None

    def connect(self) -> None:
        import psycopg2

        parsed = _parse_admin_url(self._admin_url)
        socket_host = parsed.host or parsed.query.get("host") or "/var/run/postgresql"
        self._connection = psycopg2.connect(
            dbname=parsed.database,
            user=parsed.username,
            host=socket_host,
            port=parsed.port,
            connect_timeout=5,
        )
        self._connection.autocommit = True

    def is_connected(self) -> bool:
        return self._connection is not None

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        if self._connection is None:
            raise ValidationRunnerError("admin client is not connected")
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)

    def query(
        self, sql: str, params: Sequence[Any] | None = None
    ) -> list[tuple[Any, ...]]:
        if self._connection is None:
            raise ValidationRunnerError("admin client is not connected")
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


def _parse_admin_url(admin_url: str) -> Any:
    try:
        from sqlalchemy.engine import make_url
    except ImportError as exc:
        raise ValidationRunnerError(
            "sqlalchemy is required to parse --database-url"
        ) from exc
    parsed = make_url(admin_url)
    if not parsed.drivername.startswith("postgresql"):
        raise ValidationRunnerError("admin URL must use a PostgreSQL driver")
    host = parsed.host
    if host not in (None, "") and not host.startswith("/"):
        raise ValidationRunnerError("admin URL must use a Unix socket host")
    if parsed.password:
        raise ValidationRunnerError("admin URL must not carry a password")
    database = parsed.database or ""
    if not database or database in FORBIDDEN_ADMIN_DATABASES:
        raise ValidationRunnerError("refusing unsafe or empty admin database")
    if OWNED_NAME_RE.fullmatch(database):
        raise ValidationRunnerError(
            "admin URL must not target a validation-owned database"
        )
    return parsed


def _validate_owned_name(name: str) -> None:
    if not isinstance(name, str) or OWNED_NAME_RE.fullmatch(name) is None:
        raise ValidationRunnerError(f"refusing unowned validation name {name!r}")


def _generate_token(token: str | None) -> str:
    if token is not None:
        if TOKEN_RE.fullmatch(token) is None:
            raise ValidationRunnerError("token must match ^[a-z0-9]{16}$")
        return token
    return secrets.token_hex(8)


def _quote_ident(name: str) -> str:
    _validate_owned_name(name)
    return f'"{name}"'


def _build_child_env(
    admin_url: str, database_name: str, role_name: str
) -> dict[str, str]:
    parsed = _parse_admin_url(admin_url)
    _validate_owned_name(database_name)
    _validate_owned_name(role_name)
    socket_host = parsed.host or parsed.query.get("host") or "/var/run/postgresql"
    child_env: dict[str, str] = {}
    if "PATH" in os.environ:
        child_env["PATH"] = os.environ["PATH"]
    child_env[CHILD_DATABASE_URL_ENV] = (
        f"postgresql+psycopg2://{role_name}@/{database_name}?host={socket_host}"
    )
    child_env["PGHOST"] = socket_host
    child_env["PGDATABASE"] = database_name
    child_env["PGUSER"] = role_name
    child_env["PYTHONUNBUFFERED"] = "1"
    if parsed.port:
        child_env["PGPORT"] = str(parsed.port)
    return child_env


def _observe_residual(client: PostgresAdminClient) -> dict[str, int]:
    table_rows = client.query(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
        "AND (starts_with(tablename, 'runtime_') OR starts_with(tablename, 'successor_'))"
    )
    schema_rows = client.query(
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE starts_with(schema_name, 'mrw_')"
    )
    return {
        "public_successor_tables": len(table_rows),
        "mrw_schemas": len(schema_rows),
    }


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_report(
    *,
    status: str,
    exit_code: int,
    database_name: str | None,
    role_name: str | None,
    socket_only: bool,
    admin_superuser: bool,
    residual_before: Mapping[str, int],
    residual_after: Mapping[str, int],
    residual_clean: bool,
    child_command: Sequence[str],
    child_returncode: int | None,
    child_stdout_digest: str | None,
    child_stderr_digest: str | None,
    created_database: bool,
    created_role: bool,
    dropped_database: bool,
    dropped_role: bool,
    database_absent_after: bool,
    role_absent_after: bool,
    issues: Sequence[RunnerIssue],
) -> PostgresValidationReport:
    return PostgresValidationReport(
        status=status,
        exit_code=exit_code,
        database_name=database_name,
        role_name=role_name,
        socket_only=socket_only,
        admin_superuser=admin_superuser,
        residual_before=dict(residual_before),
        residual_after=dict(residual_after),
        residual_clean=residual_clean,
        child_command=tuple(child_command),
        child_returncode=child_returncode,
        child_stdout_digest=child_stdout_digest,
        child_stderr_digest=child_stderr_digest,
        created_database=created_database,
        created_role=created_role,
        dropped_database=dropped_database,
        dropped_role=dropped_role,
        database_absent_after=database_absent_after,
        role_absent_after=role_absent_after,
        issues=tuple(
            sorted(issues, key=lambda item: (item.code, item.path, item.message))
        ),
    )


def run_validation(
    *,
    admin_url: str,
    command: Sequence[str],
    token: str | None = None,
    db_client_factory: Callable[[str], PostgresAdminClient] = PostgresAdminClient,
    subprocess_run: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> PostgresValidationReport:
    """Run the bounded PostgreSQL validation and always attempt teardown."""
    issues: list[RunnerIssue] = []
    database_name: str | None = None
    role_name: str | None = None
    socket_only = False
    admin_superuser = False
    residual_before: dict[str, int] = {}
    residual_after: dict[str, int] = {}
    child_returncode: int | None = None
    child_stdout_digest: str | None = None
    child_stderr_digest: str | None = None
    created_database = False
    created_role = False
    dropped_database = False
    dropped_role = False
    database_absent_after = False
    role_absent_after = False
    status = "PASS"
    exit_code = 0
    client: PostgresAdminClient | None = None
    command_tuple = tuple(command)

    try:
        _parse_admin_url(admin_url)
        token_value = _generate_token(token)
        database_name = f"{NAME_PREFIX}{token_value}"
        role_name = f"{NAME_PREFIX}{token_value}"
        _validate_owned_name(database_name)
        _validate_owned_name(role_name)
        client = db_client_factory(admin_url)
        client.connect()
        socket_only = bool(client.query("SELECT inet_server_addr() IS NULL")[0][0])
        admin_superuser = bool(
            client.query("SELECT current_setting('is_superuser') = 'on'")[0][0]
        )
        if not socket_only:
            raise ValidationRunnerError("refusing non-Unix-socket admin connection")
        if not admin_superuser:
            raise ValidationRunnerError("admin connection is not superuser")
        existing_db = client.query(
            "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = %s)",
            (database_name,),
        )[0][0]
        existing_role = client.query(
            "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)",
            (role_name,),
        )[0][0]
        if existing_db:
            raise ValidationRunnerError(
                f"validation database already exists: {database_name}"
            )
        if existing_role:
            raise ValidationRunnerError(f"validation role already exists: {role_name}")
        residual_before = _observe_residual(client)
        client.execute(
            "CREATE ROLE "
            + _quote_ident(role_name)
            + " NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT LOGIN"
        )
        created_role = True
        client.execute(
            "CREATE DATABASE "
            + _quote_ident(database_name)
            + " OWNER "
            + _quote_ident(role_name)
        )
        created_database = True
        child_env = _build_child_env(admin_url, database_name, role_name)
        completed = subprocess_run(
            list(command_tuple),
            env=child_env,
            capture_output=True,
            shell=False,
        )
        child_returncode = completed.returncode
        child_stdout_digest = _digest_bytes(completed.stdout)
        child_stderr_digest = _digest_bytes(completed.stderr)
        if completed.returncode != 0:
            status = "FAIL"
            exit_code = 1
            issues.append(
                RunnerIssue(
                    code="CHILD_VALIDATION_FAILED",
                    path=" ".join(command_tuple),
                    message=f"child command returned {completed.returncode}",
                )
            )
    except ValidationRunnerError as exc:
        status = "ERROR"
        exit_code = 2
        issues.append(
            RunnerIssue(
                code="PRECONDITION_FAILED",
                path=admin_url,
                message=str(exc),
            )
        )
    except Exception as exc:  # noqa: BLE001 - fail-closed runner boundary
        status = "ERROR"
        exit_code = 2
        issues.append(
            RunnerIssue(
                code="RUNNER_EXECUTION_ERROR",
                path=admin_url,
                message=f"{type(exc).__name__}: {exc}",
            )
        )
    finally:
        if database_name is not None and role_name is not None:
            try:
                _validate_owned_name(database_name)
                _validate_owned_name(role_name)
                if created_database or created_role:
                    if client is None:
                        client = db_client_factory(admin_url)
                    if not client.is_connected():
                        client.connect()
                    client.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()",
                        (database_name,),
                    )
                    if created_database:
                        client.execute(
                            "DROP DATABASE IF EXISTS " + _quote_ident(database_name)
                        )
                        dropped_database = True
                    if created_role:
                        client.execute("DROP ROLE IF EXISTS " + _quote_ident(role_name))
                        dropped_role = True
                    if dropped_database:
                        database_absent_after = bool(
                            client.query(
                                "SELECT NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = %s)",
                                (database_name,),
                            )[0][0]
                        )
                    if dropped_role:
                        role_absent_after = bool(
                            client.query(
                                "SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)",
                                (role_name,),
                            )[0][0]
                        )
                    residual_after = _observe_residual(client)
            except Exception as exc:  # noqa: BLE001 - teardown must not escape
                status = "ERROR"
                exit_code = 2
                issues.append(
                    RunnerIssue(
                        code="TEARDOWN_FAILED",
                        path="teardown",
                        message=f"{type(exc).__name__}: {exc}",
                    )
                )
            finally:
                if client is not None:
                    client.close()
        if residual_before and residual_after and residual_before != residual_after:
            status = "FAIL"
            if exit_code == 0:
                exit_code = 1
            issues.append(
                RunnerIssue(
                    code="RESIDUAL_MISMATCH",
                    path="residuals",
                    message=(
                        f"public successor tables/mrw schemas changed "
                        f"({residual_before} -> {residual_after})"
                    ),
                )
            )
        if dropped_database and not database_absent_after:
            status = "FAIL"
            if exit_code == 0:
                exit_code = 1
            issues.append(
                RunnerIssue(
                    code="TEARDOWN_INCOMPLETE",
                    path=database_name,
                    message="own validation database still exists after teardown",
                )
            )
        if dropped_role and not role_absent_after:
            status = "FAIL"
            if exit_code == 0:
                exit_code = 1
            issues.append(
                RunnerIssue(
                    code="TEARDOWN_INCOMPLETE",
                    path=role_name,
                    message="own validation role still exists after teardown",
                )
            )

    residual_clean = bool(residual_before) and residual_before == residual_after
    return _build_report(
        status=status,
        exit_code=exit_code,
        database_name=database_name,
        role_name=role_name,
        socket_only=socket_only,
        admin_superuser=admin_superuser,
        residual_before=residual_before,
        residual_after=residual_after,
        residual_clean=residual_clean,
        child_command=command_tuple,
        child_returncode=child_returncode,
        child_stdout_digest=child_stdout_digest,
        child_stderr_digest=child_stderr_digest,
        created_database=created_database,
        created_role=created_role,
        dropped_database=dropped_database,
        dropped_role=dropped_role,
        database_absent_after=database_absent_after,
        role_absent_after=role_absent_after,
        issues=issues,
    )


def _fatal_report(command: Sequence[str], message: str) -> PostgresValidationReport:
    issue = RunnerIssue(code="USAGE_ERROR", path="", message=message)
    return _build_report(
        status="ERROR",
        exit_code=2,
        database_name=None,
        role_name=None,
        socket_only=False,
        admin_superuser=False,
        residual_before={},
        residual_after={},
        residual_clean=False,
        child_command=command,
        child_returncode=None,
        child_stdout_digest=None,
        child_stderr_digest=None,
        created_database=False,
        created_role=False,
        dropped_database=False,
        dropped_role=False,
        database_absent_after=False,
        role_absent_after=False,
        issues=(issue,),
    )


def _write_text_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def run_cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run successor PostgreSQL validation on a disposable local database."
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get(ADMIN_URL_ENV),
        help="local Unix-socket PostgreSQL admin URL",
    )
    parser.add_argument(
        "--token", default=None, help="optional deterministic 16-char token"
    )
    parser.add_argument(
        "--report", default=None, help="optional canonical report output"
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="child command after -- (arg list, never a shell string)",
    )
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        report = _fatal_report((), "missing child command after --")
        if args.report:
            try:
                _write_text_atomic(Path(args.report), report.to_json() + "\n")
            except OSError:
                return 2
        print(report.to_json())
        return 2
    if not args.database_url:
        report = _fatal_report(command, "missing --database-url or admin env")
        if args.report:
            try:
                _write_text_atomic(Path(args.report), report.to_json() + "\n")
            except OSError:
                return 2
        print(report.to_json())
        return 2
    report = run_validation(
        admin_url=args.database_url,
        command=command,
        token=args.token,
    )
    if args.report:
        try:
            _write_text_atomic(Path(args.report), report.to_json() + "\n")
        except OSError as exc:
            print(f"unable to write report: {exc}", file=sys.stderr)
            return 2
    print(report.to_json())
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(run_cli())
