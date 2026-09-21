from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("mrw_dev_entry", ROOT / "scripts" / "dev.py")
assert SPEC is not None and SPEC.loader is not None
DEV = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = DEV
SPEC.loader.exec_module(DEV)


def test_contribution_commands_bind_root_catalog_and_optional_inspect_id() -> None:
    python = Path("/test/python")
    for action in ("check", "sync"):
        command = DEV._command_for(action, python)
        assert command[:5] == [str(python), "-m", "functorial_kit", "contributions", action]
        assert command[command.index("--catalog") + 1] == str(DEV.CATALOG)
        assert command[command.index("--root") + 1] == str(DEV.ROOT)

    inspect = DEV._command_for("inspect", python, contribution_id="mrw.successor.c8.graph-projection.v1")
    assert inspect[-2:] == ["--id", "mrw.successor.c8.graph-projection.v1"]
    assert DEV._command_environment()["PYTHONPATH"].split(DEV.os.pathsep)[:2] == [
        str(DEV.ROOT / "src"),
        str(DEV.ROOT / "main" / "backend"),
    ]


def test_test_and_gate_commands_keep_the_known_pilot_separate_from_full_gates() -> None:
    python = Path("/test/python")
    pilot = DEV._command_for("test", python)
    gates = DEV._command_for("gates", python)

    assert pilot[-5:] == list(DEV.PILOT_TESTS)
    assert DEV.ARCHITECTURE_TEST not in pilot
    assert gates[-1] == DEV.ARCHITECTURE_TEST
    assert all(test not in gates for test in DEV.PILOT_TESTS)
    assert "--maxfail" not in gates


def test_setup_uses_declared_local_source_without_dependency_resolution(monkeypatch) -> None:
    monkeypatch.setattr(DEV.shutil, "which", lambda _name: "/test/uv")
    kit_path = DEV._local_kit_path()
    command = DEV._setup_command(Path("/test/python"), kit_path)

    assert kit_path == (DEV.ROOT / "../Desktop/functorial-kit/python").resolve()
    assert command == [
        "/test/uv",
        "pip",
        "install",
        "--offline",
        "--python",
        "/test/python",
        "--no-deps",
        "--editable",
        str(kit_path),
    ]


def test_python_override_preserves_virtualenv_symlink(monkeypatch, tmp_path) -> None:
    venv_python = tmp_path / "venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(sys.executable)
    monkeypatch.setenv("MRW_DEV_PYTHON", str(venv_python))

    assert DEV._python_executable() == venv_python.absolute()
    assert DEV._python_executable() != venv_python.resolve()


def test_validate_runs_sync_check_focused_tests_and_gates_fail_fast(monkeypatch) -> None:
    python = Path("/test/python")
    commands = []
    completions = [
        type("Completed", (), {"returncode": 0})(),
        type("Completed", (), {"returncode": 0})(),
        type("Completed", (), {"returncode": 0})(),
        type("Completed", (), {"returncode": 0})(),
    ]

    def run(command, **_kwargs):
        commands.append(command)
        return completions[len(commands) - 1]

    monkeypatch.setattr(DEV.subprocess, "run", run)
    monkeypatch.setattr(DEV, "_python_executable", lambda: python)
    monkeypatch.setattr(DEV, "_local_kit_path", lambda: Path("/test/kit"))
    monkeypatch.setattr(DEV, "_require_local_kit", lambda _python, _kit: True)
    monkeypatch.setattr(DEV, "_require_test_environment", lambda _python, backend_dependencies: backend_dependencies)

    assert DEV.main(["validate"]) == 0
    assert commands == [DEV._command_for(command, python) for command in DEV.VALIDATE_COMMANDS]
    assert [command[command.index("contributions") + 1] for command in commands[:2]] == ["sync", "check"]
    assert commands[2][-5:] == list(DEV.PILOT_TESTS)
    assert commands[3][-1] == DEV.ARCHITECTURE_TEST


def test_validate_stops_before_later_stages_when_a_stage_fails(monkeypatch) -> None:
    python = Path("/test/python")
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        return type("Completed", (), {"returncode": 3})()

    monkeypatch.setattr(DEV.subprocess, "run", run)
    monkeypatch.setattr(DEV, "_python_executable", lambda: python)
    monkeypatch.setattr(DEV, "_local_kit_path", lambda: Path("/test/kit"))
    monkeypatch.setattr(DEV, "_require_local_kit", lambda _python, _kit: True)
    monkeypatch.setattr(DEV, "_require_test_environment", lambda _python, backend_dependencies: backend_dependencies)

    assert DEV.main(["validate"]) == 3
    assert commands == [DEV._command_for("sync", python)]


def test_standard_architecture_file_wires_read_only_contribution_check() -> None:
    source = (DEV.ROOT / DEV.ARCHITECTURE_TEST).read_text(encoding="utf-8")

    assert "def test_contribution_projection_is_current" in source
    assert 'contributions_main(["check"' in source
    assert f'str(CATALOG)' in source
    assert f'str(ROOT)' in source
    assert '"sync"' not in source
