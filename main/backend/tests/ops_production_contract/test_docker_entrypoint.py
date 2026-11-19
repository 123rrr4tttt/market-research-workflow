from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ENTRYPOINT = Path(__file__).resolve().parents[2] / "docker-entrypoint.sh"
REDIS_URL = "rediss://worker:fixture%27password@redis:6380/3"


@pytest.mark.parametrize(
    ("failure", "attempts"),
    [(None, ["pg_isready", "pg_isready", "curl", "redis", "alembic", "app"]),
     ("redis", ["pg_isready", "pg_isready", "curl", "redis", "redis"])],
)
def test_entrypoint_checks_in_order_and_fails_before_migrations(
    tmp_path: Path, failure: str | None, attempts: list[str],
) -> None:
    events_file = tmp_path / "events"
    setup_file = tmp_path / "bash-env"
    setup_file.write_text('cd() { builtin cd "$PROBE_APP_DIR"; }\n', encoding="utf-8")
    python = tmp_path / "python"
    python.symlink_to(sys.executable)
    stub = tmp_path / "probe"
    stub.write_text(
        f"#!{sys.executable}\n" + """\
import json, os, sys
from pathlib import Path

name = Path(sys.argv[0]).name
path = Path(os.environ["PROBE_EVENTS"])
first_db_attempt = name == "pg_isready" and not path.exists()
with path.open("a") as stream:
    print(json.dumps([name, *sys.argv[1:]]), file=stream)
raise SystemExit(1 if first_db_attempt else 0)
""",
        encoding="utf-8",
    )
    stub.chmod(0o700)
    for name in ("pg_isready", "curl", "alembic", "app"):
        (tmp_path / name).symlink_to(stub)
    (tmp_path / "redis.py").write_text(
        """\
import json, os

class Redis:
    @classmethod
    def from_url(cls, url, **kwargs):
        with open(os.environ["PROBE_EVENTS"], "a") as stream:
            print(json.dumps(["redis", url, kwargs]), file=stream)
        return cls()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def ping(self):
        return os.environ["PROBE_FAILURE"] != "redis"
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(ENTRYPOINT), "app", "--flag", "two words"],
        env={
            **os.environ,
            "BASH_ENV": str(setup_file),
            "PATH": os.pathsep.join([str(tmp_path), os.defpath]),
            "PYTHONPATH": str(tmp_path),
            "PROBE_APP_DIR": str(tmp_path),
            "PROBE_EVENTS": str(events_file),
            "PROBE_FAILURE": failure or "",
            "DATABASE_URL": "postgresql+psycopg2://worker@postgres:5439/project",
            "ES_URL": "https://elastic:fixture@search:9443",
            "REDIS_URL": REDIS_URL,
            "STARTUP_MAX_RETRIES": "2",
            "STARTUP_RETRY_DELAY": "0",
            "RUN_MIGRATIONS": "true",
        },
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    events = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines()]
    assert [event[0] for event in events] == attempts
    assert events[0] == ["pg_isready", "-h", "postgres", "-p", "5439", "-U", "worker", "-d", "project"]
    assert events[2] == ["curl", "-fsS", "--user", "elastic:fixture", "https://search:9443/_cluster/health"]
    assert events[3] == ["redis", REDIS_URL, {"socket_connect_timeout": 5, "socket_timeout": 5}]
    assert REDIS_URL not in result.stdout + result.stderr
    if failure:
        assert result.returncode == 1
        assert "Redis" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert events[-2:] == [["alembic", "upgrade", "head"], ["app", "--flag", "two words"]]
