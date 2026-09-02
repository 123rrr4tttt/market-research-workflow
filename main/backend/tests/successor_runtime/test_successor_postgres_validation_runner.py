from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts.run_successor_postgres_validation as runner

pytestmark = [pytest.mark.unit, pytest.mark.mocked]

OWNED_RE = re.compile(r"^mrw_successor_validation_[a-z0-9]{16}$")
TOKEN = "0123456789abcdef"
DATABASE_NAME = f"mrw_successor_validation_{TOKEN}"
ROLE_NAME = f"mrw_successor_validation_{TOKEN}"
ADMIN_URL = "postgresql+psycopg2://admin@/mrw_admin_test?host=/var/run/postgresql"
CHILD_COMMAND = ("python3.11", "-m", "pytest", "-q", "tests/successor_runtime")


class FakeAdminClient:
    def __init__(
        self,
        admin_url: str,
        *,
        existing_database: bool = False,
        existing_role: bool = False,
        residual_tables: int = 0,
        residual_schemas: int = 0,
        superuser: bool = True,
        fail_connect: bool = False,
        fail_on_execute: str | None = None,
    ) -> None:
        self.admin_url = admin_url
        self.executed: list[tuple[str, Sequence[Any] | None]] = []
        self.queried: list[tuple[str, Sequence[Any] | None]] = []
        self.connected = False
        self.existing_database = existing_database
        self.existing_role = existing_role
        self.residual_tables = residual_tables
        self.residual_schemas = residual_schemas
        self.superuser = superuser
        self.fail_connect = fail_connect
        self.fail_on_execute = fail_on_execute
        self.database_absent = True
        self.role_absent = True

    def connect(self) -> None:
        if self.fail_connect:
            raise RuntimeError("simulated connect failure")
        self.connected = True

    def is_connected(self) -> bool:
        return self.connected

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        if self.fail_on_execute and self.fail_on_execute in sql:
            raise RuntimeError(f"simulated execute failure on {self.fail_on_execute}")
        self.executed.append((sql, params))
        if sql.startswith("DROP DATABASE"):
            match = re.search(r'"([^"]+)"', sql)
            if match is None or OWNED_RE.fullmatch(match.group(1)) is None:
                raise RuntimeError(f"refusing unowned drop: {sql}")
            self.database_absent = True
        if sql.startswith("DROP ROLE"):
            match = re.search(r'"([^"]+)"', sql)
            if match is None or OWNED_RE.fullmatch(match.group(1)) is None:
                raise RuntimeError(f"refusing unowned drop: {sql}")
            self.role_absent = True
        if sql.startswith("CREATE DATABASE"):
            self.database_absent = False

    def query(
        self, sql: str, params: Sequence[Any] | None = None
    ) -> list[tuple[Any, ...]]:
        self.queried.append((sql, params))
        if "inet_server_addr()" in sql:
            return [(True,)]
        if "is_superuser" in sql:
            return [(self.superuser,)]
        if "starts_with(tablename" in sql:
            return [("runtime_legacy",)] * self.residual_tables
        if "starts_with(schema_name" in sql:
            return [("mrw_legacy",)] * self.residual_schemas
        if "SELECT EXISTS (SELECT 1 FROM pg_database" in sql:
            return [(self.existing_database,)]
        if "SELECT EXISTS (SELECT 1 FROM pg_roles" in sql:
            return [(self.existing_role,)]
        if "NOT EXISTS (SELECT 1 FROM pg_database" in sql:
            return [(self.database_absent,)]
        if "NOT EXISTS (SELECT 1 FROM pg_roles" in sql:
            return [(self.role_absent,)]
        if "SELECT 1 FROM pg_database" in sql:
            return [(1,)] if not self.database_absent else []
        if "SELECT 1 FROM pg_roles" in sql:
            return [(1,)] if not self.role_absent else []
        return []

    def close(self) -> None:
        self.connected = False


def _fake_subprocess(
    returncode: int = 0,
    stdout: bytes = b"ok",
    stderr: bytes = b"",
    raise_error: Exception | None = None,
) -> Callable[..., subprocess.CompletedProcess[bytes]]:
    captured: dict[str, Any] = {}

    def _run(
        args: Sequence[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[bytes]:
        captured["args"] = list(args)
        captured["kwargs"] = kwargs
        if raise_error is not None:
            raise raise_error
        return subprocess.CompletedProcess(
            args=list(args),
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    _run.captured = captured  # type: ignore[attr-defined]
    return _run


def _client_factory(client: FakeAdminClient) -> Callable[[str], FakeAdminClient]:
    def _factory(admin_url: str) -> FakeAdminClient:
        assert admin_url == ADMIN_URL
        return client

    return _factory


def _run(
    client: FakeAdminClient | None = None,
    *,
    token: str = TOKEN,
    subprocess_run: Callable[..., subprocess.CompletedProcess[bytes]] | None = None,
    admin_url: str = ADMIN_URL,
) -> tuple[runner.PostgresValidationReport, FakeAdminClient | None]:
    if client is None:
        client = FakeAdminClient(admin_url)
    if subprocess_run is None:
        subprocess_run = _fake_subprocess()
    report = runner.run_validation(
        admin_url=admin_url,
        command=CHILD_COMMAND,
        token=token,
        db_client_factory=_client_factory(client),
        subprocess_run=subprocess_run,
    )
    return report, client


def test_generates_regex_bound_names_and_runs_child_once() -> None:
    report, client = _run()
    assert report.status == "PASS"
    assert report.exit_code == 0
    assert report.database_name == DATABASE_NAME
    assert report.role_name == ROLE_NAME
    assert OWNED_RE.fullmatch(report.database_name or "")
    assert OWNED_RE.fullmatch(report.role_name or "")
    executed_sql = [sql for sql, _ in client.executed]
    assert (
        f'CREATE ROLE "{ROLE_NAME}" NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT LOGIN'
        in executed_sql
    )
    assert f'CREATE DATABASE "{DATABASE_NAME}" OWNER "{ROLE_NAME}"' in executed_sql
    assert f'DROP DATABASE IF EXISTS "{DATABASE_NAME}"' in executed_sql
    assert f'DROP ROLE IF EXISTS "{ROLE_NAME}"' in executed_sql
    assert report.created_database
    assert report.created_role
    assert report.dropped_database
    assert report.dropped_role
    assert report.database_absent_after
    assert report.role_absent_after


def test_child_env_is_constrained_and_uses_generated_role_database() -> None:
    fake = _fake_subprocess()
    report, _ = _run(subprocess_run=fake)
    assert report.exit_code == 0
    env = fake.captured["kwargs"]["env"]  # type: ignore[attr-defined]
    assert set(env) == {
        "PATH",
        "SUCCESSOR_TEST_DATABASE_URL",
        "PGHOST",
        "PGDATABASE",
        "PGUSER",
        "PYTHONUNBUFFERED",
    }
    assert env["PGDATABASE"] == DATABASE_NAME
    assert env["PGUSER"] == ROLE_NAME
    assert env["PGHOST"] == "/var/run/postgresql"
    assert env["SUCCESSOR_TEST_DATABASE_URL"].startswith(
        f"postgresql+psycopg2://{ROLE_NAME}@/{DATABASE_NAME}?host=/var/run/postgresql"
    )
    assert "PATH" in env


def test_subprocess_uses_args_list_without_shell() -> None:
    fake = _fake_subprocess()
    report, _ = _run(subprocess_run=fake)
    assert report.exit_code == 0
    args = fake.captured["args"]  # type: ignore[attr-defined]
    assert args == list(CHILD_COMMAND)
    assert all(isinstance(item, str) for item in args)
    assert fake.captured["kwargs"]["shell"] is False  # type: ignore[attr-defined]


def test_child_failure_exits_1_and_teardown_still_drops_own_objects() -> None:
    fake = _fake_subprocess(returncode=1, stderr=b"boom")
    report, client = _run(subprocess_run=fake)
    assert report.exit_code == 1
    assert report.status == "FAIL"
    assert any(issue.code == "CHILD_VALIDATION_FAILED" for issue in report.issues)
    assert report.child_returncode == 1
    executed_sql = [sql for sql, _ in client.executed]
    assert f'DROP DATABASE IF EXISTS "{DATABASE_NAME}"' in executed_sql
    assert f'DROP ROLE IF EXISTS "{ROLE_NAME}"' in executed_sql


def test_teardown_only_touches_regex_bound_owned_names() -> None:
    report, client = _run()
    assert report.exit_code == 0
    for sql, _ in client.executed:
        if sql.startswith("DROP"):
            names = re.findall(r'"([^"]+)"', sql)
            assert names and all(OWNED_RE.fullmatch(name) for name in names)


def test_invalid_token_fails_before_any_database_touch() -> None:
    report, client = _run(token="NOT_A_VALID_TOKEN")
    assert report.exit_code == 2
    assert report.status == "ERROR"
    assert client.executed == []
    assert client.queried == []


def test_existing_database_or_role_fails_closed_without_mutation() -> None:
    client = FakeAdminClient(ADMIN_URL, existing_database=True)
    report, client = _run(client=client)
    assert report.exit_code == 2
    assert any(issue.code == "PRECONDITION_FAILED" for issue in report.issues)
    assert not any(sql.startswith("CREATE") for sql, _ in client.executed)

    client = FakeAdminClient(ADMIN_URL, existing_role=True)
    report, client = _run(client=client)
    assert report.exit_code == 2
    assert not any(sql.startswith("CREATE") for sql, _ in client.executed)


@pytest.mark.parametrize(
    "admin_url",
    [
        "postgresql+psycopg2://admin@127.0.0.1:5432/postgres",
        "postgresql+psycopg2://admin:secret@/postgres?host=/var/run/postgresql",
        "mysql://admin@/postgres",
        "postgresql+psycopg2://admin@/postgres",
        "postgresql+psycopg2://admin@/template1?host=/var/run/postgresql",
    ],
)
def test_unsafe_admin_urls_fail_closed(admin_url: str) -> None:
    client = FakeAdminClient(admin_url)
    report, client = _run(client=client, admin_url=admin_url)
    assert report.exit_code == 2
    assert client.executed == []
    assert client.queried == []


def test_non_superuser_admin_fails_closed() -> None:
    client = FakeAdminClient(ADMIN_URL, superuser=False)
    report, client = _run(client=client)
    assert report.exit_code == 2
    assert not any(sql.startswith("CREATE") for sql, _ in client.executed)


def test_residual_growth_fails_after_teardown() -> None:
    client = FakeAdminClient(ADMIN_URL, residual_tables=0, residual_schemas=0)

    def residual_subprocess(
        args: Sequence[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[bytes]:
        client.residual_tables = 1
        return subprocess.CompletedProcess(list(args), 0, b"ok", b"")

    report, _ = _run(client=client, subprocess_run=residual_subprocess)
    assert report.exit_code == 1
    assert any(issue.code == "RESIDUAL_MISMATCH" for issue in report.issues)


def test_child_execution_error_still_tears_down_own_database_and_role() -> None:
    client = FakeAdminClient(ADMIN_URL)
    fake = _fake_subprocess(raise_error=RuntimeError("simulated child launch failure"))
    report, client = _run(client=client, subprocess_run=fake)
    assert report.exit_code == 2
    assert any(issue.code == "RUNNER_EXECUTION_ERROR" for issue in report.issues)
    executed_sql = [sql for sql, _ in client.executed]
    assert f'DROP DATABASE IF EXISTS "{DATABASE_NAME}"' in executed_sql
    assert f'DROP ROLE IF EXISTS "{ROLE_NAME}"' in executed_sql


def test_teardown_failure_is_reported() -> None:
    client = FakeAdminClient(ADMIN_URL)
    fake = _fake_subprocess()

    original_execute = client.execute

    def failing_execute(sql: str, params: Sequence[Any] | None = None) -> None:
        if sql.startswith("DROP DATABASE"):
            raise RuntimeError("simulated drop failure")
        original_execute(sql, params)

    client.execute = failing_execute  # type: ignore[method-assign]
    report, _ = _run(client=client, subprocess_run=fake)
    assert report.exit_code == 2
    assert any(issue.code == "TEARDOWN_FAILED" for issue in report.issues)


def test_run_cli_missing_database_url_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SUCCESSOR_POSTGRES_VALIDATION_DATABASE_URL", raising=False)
    report_path = tmp_path / "report.json"
    exit_code = runner.run_cli(["--report", str(report_path), "--", *CHILD_COMMAND])
    assert exit_code == 2
    parsed = json.loads(report_path.read_text(encoding="utf-8"))
    assert parsed["status"] == "ERROR"
    assert parsed["exit_code"] == 2


def test_run_cli_report_and_exit_code_propagation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def fake_run_validation(**kwargs: Any) -> runner.PostgresValidationReport:
        calls["kwargs"] = kwargs
        return runner._fatal_report(kwargs["command"], "simulated")

    monkeypatch.setattr(runner, "run_validation", fake_run_validation)
    report_path = tmp_path / "report.json"
    exit_code = runner.run_cli(
        [
            "--database-url",
            ADMIN_URL,
            "--token",
            TOKEN,
            "--report",
            str(report_path),
            "--",
            *CHILD_COMMAND,
        ]
    )
    assert exit_code == 2
    parsed = json.loads(report_path.read_text(encoding="utf-8"))
    assert parsed["exit_code"] == 2
    assert calls["kwargs"]["admin_url"] == ADMIN_URL
    assert calls["kwargs"]["token"] == TOKEN
    assert list(calls["kwargs"]["command"]) == list(CHILD_COMMAND)


def test_unit_tests_never_use_real_postgres_client_or_drop() -> None:
    import scripts.run_successor_postgres_validation as module

    original_client = module.PostgresAdminClient
    instantiated: list[str] = []

    class GuardClient:
        def __init__(self, admin_url: str) -> None:
            instantiated.append(admin_url)
            raise AssertionError("unit tests must not instantiate the real DB client")

    module.PostgresAdminClient = GuardClient  # type: ignore[assignment]
    try:
        client = FakeAdminClient(ADMIN_URL)
        report, _ = _run(client=client)
        assert report.exit_code == 0
    finally:
        module.PostgresAdminClient = original_client
    assert instantiated == []
    for sql, _ in client.executed:
        if "DROP" in sql:
            assert DATABASE_NAME in sql or ROLE_NAME in sql
