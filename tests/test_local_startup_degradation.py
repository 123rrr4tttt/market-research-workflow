from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


LAUNCHER = Path(__file__).resolve().parents[1] / "main/backend/start-local.sh"


@pytest.mark.parametrize("fault", ("postgres", "redis", "worker", "none"))
def test_local_startup_separates_required_database_from_worker(
    tmp_path: Path, fault: str,
) -> None:
    backend = tmp_path / "main/backend"
    commands = backend / ".venv311/bin"
    commands.mkdir(parents=True)
    (tmp_path / "main/ops").mkdir()
    (tmp_path / "main/frontend-modern").mkdir()

    source = LAUNCHER.read_text(encoding="utf-8")
    # Redirect only the worker's PID and log files; execute the entire launcher.
    for name in ("celery-local-worker.pid", "celery-local-worker.log"):
        source = source.replace(f"/tmp/{name}", str(tmp_path / name))
    launcher = backend / LAUNCHER.name
    launcher.write_text(source, encoding="utf-8")
    (backend / ".env").write_text(
        "DATABASE_URL='postgresql+psycopg2://test:test@127.0.0.1:15432/test'\n",
        encoding="utf-8",
    )
    (commands / "activate").write_text(
        'export PATH="$PWD/.venv311/bin:$PATH"\n', encoding="utf-8",
    )

    def stub(name: str, body: str) -> None:
        path = commands / name
        path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        path.chmod(0o755)

    stub("pg_isready", '[ "$FAULT" != postgres ] && [ "$4" = 15432 ]')
    stub("nc", "exit 1")
    stub("curl", "exit 1")
    stub("ipconfig", "exit 1")
    stub("ifconfig", "exit 1")
    stub("lsof", '''
case " $* " in
    *" -iTCP:5173 "*) echo 123; exit 0 ;;
    *" -a -p 123 -d cwd "*) printf 'n%s/main/frontend-modern\\n' "$HOME"; exit 0 ;;
esac
exit 1
''')
    stub("ps", "printf '%s\\n' 'node vite'")
    stub("python", 'cat >/dev/null; echo redis-probe >> "$TRACE"; [ "$FAULT" != redis ]')
    stub("celery", 'echo worker >> "$TRACE"; [ "$FAULT" != worker ] || exit 7; exec sleep 3')
    stub("uvicorn", 'echo api >> "$TRACE"')
    trace = tmp_path / "trace"
    result = subprocess.run(
        ["bash", str(launcher), "--low-memory", "--non-interactive"],
        cwd=backend, capture_output=True, text=True, timeout=10, check=False,
        env={
            "HOME": str(tmp_path), "PATH": os.defpath, "TRACE": str(trace), "FAULT": fault,
        },
    )
    output = result.stdout + result.stderr
    if fault == "postgres":
        assert result.returncode == 1, output
        assert "PostgreSQL 未监听（127.0.0.1:15432）" in output
        assert not trace.exists()
        return

    assert result.returncode == 0, output
    expected = ["redis-probe", "api"] if fault == "redis" else ["redis-probe", "worker", "api"]
    assert trace.read_text(encoding="utf-8").splitlines() == expected
    assert "Elasticsearch 未就绪" in output
    if fault == "redis":
        assert "Redis 连接未通过；跳过本机 Celery worker" in output
    elif fault == "worker":
        assert "本机 Celery worker 启动失败" in output
        assert not (tmp_path / "celery-local-worker.pid").exists()
    else:
        assert "未验证任务消费" in output
