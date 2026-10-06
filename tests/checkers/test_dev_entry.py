from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
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


def test_test_and_gate_commands_keep_the_known_focused_tests_separate_from_full_gates() -> None:
    python = Path("/test/python")
    pilot = DEV._command_for("test", python)
    gates = DEV._command_for("gates", python)

    assert pilot[-len(DEV.PILOT_TESTS):] == list(DEV.PILOT_TESTS)
    assert "main/backend/tests/successor_runtime/test_retrieval_native_catalog.py" in DEV.PILOT_TESTS
    assert DEV.ARCHITECTURE_TEST not in pilot
    assert gates[-1] == DEV.ARCHITECTURE_TEST
    assert all(test not in gates for test in DEV.PILOT_TESTS)
    assert "--maxfail" not in gates


def test_default_help_describes_current_contribution_validation() -> None:
    assert "C8 pilot" not in DEV.__doc__
    assert "pilot" not in DEV.__doc__


def test_fixed_git_source_is_declared_consistently_and_has_no_personal_path_default() -> None:
    source = DEV._kit_source()
    pyproject = DEV.PYPROJECT.read_text(encoding="utf-8")
    requirements = (DEV.ROOT / "main" / "backend" / "requirements.txt").read_text(encoding="utf-8")

    assert source.repository == "https://github.com/123rrr4tttt/functorial-kit.git"
    assert source.revision == "6dbae536a72ab235998b21c9647b8b00d15a71e6"
    assert source.declaration in pyproject
    assert source.declaration in requirements.splitlines()
    assert "[tool.uv.sources]" not in pyproject
    assert "../Desktop/functorial-kit" not in pyproject


def test_setup_uses_fixed_git_source_or_explicit_local_checkout(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(DEV.shutil, "which", lambda _name: "/test/uv")
    local_kit = tmp_path / "anywhere" / "functorial-kit"

    assert DEV._setup_command(Path("/test/python")) == [
        "/test/uv",
        "pip",
        "install",
        "--python",
        "/test/python",
        "--no-deps",
        "--reinstall",
        DEV._kit_source().requirement,
    ]
    assert DEV._setup_command(Path("/test/python"), local_kit) == [
        "/test/uv",
        "pip",
        "install",
        "--python",
        "/test/python",
        "--no-deps",
        "--reinstall",
        "--editable",
        str(local_kit),
    ]


def test_setup_prefers_uv_and_falls_back_to_the_selected_python(monkeypatch) -> None:
    monkeypatch.setattr(DEV.shutil, "which", lambda _name: None)

    assert DEV._setup_command(Path("/test/python"))[-1] == DEV._kit_source().requirement
    assert DEV._setup_command(Path("/test/python"))[:-1] == [
        "/test/python",
        "-m",
        "pip",
        "install",
        "--no-deps",
        "--force-reinstall",
    ]


def test_python_override_preserves_virtualenv_symlink(monkeypatch, tmp_path) -> None:
    venv_python = tmp_path / "venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(sys.executable)
    monkeypatch.setenv("MRW_DEV_PYTHON", str(venv_python))

    assert DEV._python_executable() == venv_python.absolute()
    assert DEV._python_executable() != venv_python.resolve()


def test_validate_runs_sync_check_types_focused_tests_and_gates_fail_fast(monkeypatch) -> None:
    python = Path("/test/python")
    commands = []
    completions = [
        type("Completed", (), {"returncode": 0})(),
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
    monkeypatch.setattr(DEV, "_require_kit_source", lambda _python, kit_path: kit_path is None)
    monkeypatch.setattr(DEV, "_require_test_environment", lambda _python, backend_dependencies: backend_dependencies)

    assert DEV.main(["validate"]) == 0
    assert commands == [DEV._command_for(command, python) for command in DEV.VALIDATE_COMMANDS]
    assert [command[command.index("contributions") + 1] for command in commands[:2]] == ["sync", "check"]
    assert commands[2][1:3] == ["-m", "pyright"]
    assert commands[3][-len(DEV.PILOT_TESTS):] == list(DEV.PILOT_TESTS)
    assert commands[4][-1] == DEV.ARCHITECTURE_TEST


def test_typecheck_preserves_failure_and_backend_environment(monkeypatch) -> None:
    backend_python = Path("/backend/python")
    monkeypatch.setenv("MRW_TYPECHECK_PYTHON", "/checker/python")
    monkeypatch.setattr(DEV, "_python_executable", lambda: backend_python)
    monkeypatch.setattr(DEV, "_require_kit_source", lambda *_args: True)
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        return type("Completed", (), {"returncode": 1})()

    monkeypatch.setattr(DEV.subprocess, "run", run)
    assert DEV.main(["typecheck"]) == 1
    command = commands[0]
    assert command[0] == "/checker/python"
    assert command[command.index("--pythonpath") + 1] == str(backend_python)
    assert command[command.index("--project") + 1] == str(DEV.PYPROJECT)


def test_backend_typecheck_uses_declared_boundaries_and_preserves_failure(monkeypatch, tmp_path) -> None:
    project = tmp_path / "pyproject.toml"
    project.write_text(
        '[tool.pyright]\ninclude = ["src", "tests", "main/backend/app/example.py"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(DEV, "PYPROJECT", project)
    monkeypatch.setattr(DEV, "_kit_source", lambda: None)
    monkeypatch.setattr(DEV, "_require_kit_source", lambda *_args: True)
    monkeypatch.setattr(DEV, "_python_executable", lambda: Path("/backend/python"))
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        return type("Completed", (), {"returncode": 7})()

    monkeypatch.setattr(DEV.subprocess, "run", run)
    assert DEV.main(["typecheck", "--backend-boundaries"]) == 7
    assert commands[0][-1:] == ["main/backend/app/example.py"]
    assert "src" not in commands[0] and "tests" not in commands[0]


def test_contribution_composition_preserves_factory_types_and_catalog_cannot_assemble() -> None:
    valid = """from typing import assert_type
from functorial_kit import Failure
from functorial_kit.contributions import ContributionCatalog, ContributionSpec, compose_contributions, define_contribution

def transform(value: str) -> int:
    return len(value)

contribution = define_contribution(ContributionSpec("example", "example", factory=transform))
composed = compose_contributions((contribution,))
if not isinstance(composed, Failure):
    assert_type(composed.assemble("hello"), tuple[int, ...])
catalog = ContributionCatalog((contribution,))
"""
    invalid = """if not isinstance(composed, Failure):
    composed.assemble(123)
factory = catalog.contributions[0].factory
if factory is not None:
    factory("hello")
"""
    with tempfile.TemporaryDirectory(prefix="mrw-type-probe-") as probe_root:
        probe = Path(probe_root) / "contribution_boundary.py"
        checker = os.environ.get("MRW_TYPECHECK_PYTHON", sys.executable)
        command = [
            checker, "-m", "pyright", "--outputjson", "--pythonpath", str(DEV._python_executable()),
            "--project", str(DEV.PYPROJECT), str(probe),
        ]
        probe.write_text(valid, encoding="utf-8")
        accepted = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert accepted.returncode == 0, accepted.stdout + accepted.stderr
        assert json.loads(accepted.stdout)["summary"]["filesAnalyzed"] > 0
        probe.write_text(valid + invalid, encoding="utf-8")
        rejected = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert rejected.returncode == 1, rejected.stdout + rejected.stderr
        diagnostics = json.loads(rejected.stdout)["generalDiagnostics"]
        errors = [item for item in diagnostics if item["severity"] == "error"]
        assert len(errors) == 2, diagnostics
        assert all(item["rule"] == "reportArgumentType" for item in errors), diagnostics


def test_validate_stops_before_later_stages_when_a_stage_fails(monkeypatch) -> None:
    python = Path("/test/python")
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        return type("Completed", (), {"returncode": 3})()

    monkeypatch.setattr(DEV.subprocess, "run", run)
    monkeypatch.setattr(DEV, "_python_executable", lambda: python)
    monkeypatch.setattr(DEV, "_require_kit_source", lambda _python, kit_path: kit_path is None)
    monkeypatch.setattr(DEV, "_require_test_environment", lambda _python, backend_dependencies: backend_dependencies)

    assert DEV.main(["validate"]) == 3
    assert commands == [DEV._command_for("sync", python)]


def test_standard_architecture_file_wires_read_only_contribution_check() -> None:
    source = (DEV.ROOT / DEV.ARCHITECTURE_TEST).read_text(encoding="utf-8")

    assert "def test_contribution_projection_is_current" in source
    assert 'contributions_main(["check"' in source
    assert 'str(CATALOG)' in source
    assert 'str(ROOT)' in source
    assert '"sync"' not in source


def _completed(stdout: str = "", returncode: int = 0) -> object:
    return type("Completed", (), {"stdout": stdout, "stderr": "", "returncode": returncode})()


def test_default_check_accepts_only_real_fixed_git_import_and_metadata(monkeypatch, tmp_path) -> None:
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")
    site_packages = tmp_path / "site-packages"
    module = site_packages / "functorial_kit" / "__init__.py"
    source = DEV._kit_source()
    payload = {
        "module_path": str(module),
        "distribution_root": str(site_packages),
        "direct_url": {
            "url": f"git+{source.repository}@{source.revision}#subdirectory={source.subdirectory}",
            "vcs_info": {"vcs": "git", "commit_id": source.revision},
        },
    }

    assert DEV._require_kit_source(python, runner=lambda *_args, **_kwargs: _completed(json.dumps(payload)))


def test_default_check_accepts_uv_normalized_git_direct_url(monkeypatch, tmp_path) -> None:
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")
    site_packages = tmp_path / "site-packages"
    source = DEV._kit_source()
    payload = {
        "module_path": str(site_packages / "functorial_kit" / "__init__.py"),
        "distribution_root": str(site_packages),
        "direct_url": {
            "url": source.repository,
            "subdirectory": source.subdirectory,
            "vcs_info": {
                "vcs": "git",
                "commit_id": source.revision,
                "requested_revision": source.revision,
            },
        },
    }

    assert DEV._require_kit_source(python, runner=lambda *_args, **_kwargs: _completed(json.dumps(payload)))


def test_explicit_local_check_accepts_any_checkout_path_and_marks_local_source(monkeypatch, tmp_path, capsys) -> None:
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")
    kit_path = tmp_path / "not-desktop" / "functorial-kit" / "python"
    module = kit_path / "src" / "functorial_kit" / "__init__.py"
    payload = {
        "module_path": str(module),
        "distribution_root": str(tmp_path / "site-packages"),
        "direct_url": {"url": kit_path.as_uri(), "dir_info": {"editable": True}},
    }
    monkeypatch.setattr(DEV, "_local_kit_revision", lambda _path: "arbitrary-local-revision")

    assert DEV._require_kit_source(
        python,
        kit_path,
        runner=lambda *_args, **_kwargs: _completed(json.dumps(payload)),
    )
    assert "local checkout" in capsys.readouterr().err


def test_explicit_local_check_rejects_a_different_installed_checkout(monkeypatch, tmp_path) -> None:
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")
    selected_kit = tmp_path / "selected-kit"
    installed_kit = tmp_path / "installed-kit"
    payload = {
        "module_path": str(selected_kit / "functorial_kit" / "__init__.py"),
        "distribution_root": str(tmp_path / "site-packages"),
        "direct_url": {"url": installed_kit.as_uri(), "dir_info": {"editable": True}},
    }
    monkeypatch.setattr(DEV, "_local_kit_revision", lambda _path: "selected-local-revision")

    assert not DEV._require_kit_source(
        python,
        selected_kit,
        runner=lambda *_args, **_kwargs: _completed(json.dumps(payload)),
    )


def test_source_mismatch_is_rejected_before_running_the_requested_command(monkeypatch, tmp_path) -> None:
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")
    site_packages = tmp_path / "site-packages"
    payload = {
        "module_path": str(site_packages / "functorial_kit" / "__init__.py"),
        "distribution_root": str(site_packages),
        "direct_url": {
            "url": "git+https://github.com/example/other.git@0000000000000000000000000000000000000000",
            "vcs_info": {
                "vcs": "git",
                "commit_id": "0000000000000000000000000000000000000000",
            },
        },
    }
    launched = []
    monkeypatch.setattr(DEV, "_python_executable", lambda: python)
    monkeypatch.setattr(
        DEV.subprocess,
        "run",
        lambda *args, **kwargs: launched.append((args, kwargs)) or _completed(json.dumps(payload)),
    )

    assert DEV.main(["check"]) == 1
    assert len(launched) == 1
    assert launched[0][0][0][0:2] == [str(python), "-c"]


def test_explicit_local_mode_and_child_exit_code_are_preserved(monkeypatch, tmp_path) -> None:
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")
    local_kit = tmp_path / "selected-kit"
    monkeypatch.setattr(DEV, "_python_executable", lambda: python)
    monkeypatch.setattr(DEV, "_require_local_kit_path", lambda _path: True)
    monkeypatch.setattr(DEV, "_require_kit_source", lambda _python, kit_path: kit_path == local_kit)
    monkeypatch.setattr(DEV.subprocess, "run", lambda *_args, **_kwargs: _completed(returncode=7))

    assert DEV.main(["check", "--local-kit", str(local_kit)]) == 7


def test_setup_preserves_installer_failure_and_verifies_a_successful_install(monkeypatch, tmp_path) -> None:
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")
    local_kit = tmp_path / "selected-kit"
    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return _completed(returncode=4)

    monkeypatch.setattr(DEV, "_python_executable", lambda: python)
    monkeypatch.setattr(DEV, "_require_local_kit_path", lambda _path: True)
    monkeypatch.setattr(DEV, "_require_setup_environment", lambda _python: True)
    monkeypatch.setattr(DEV, "_require_kit_source", lambda *_args: calls.append("verified") is None)
    monkeypatch.setattr(DEV.subprocess, "run", run)

    assert DEV.main(["setup", "--local-kit", str(local_kit)]) == 4
    assert calls[-1] != "verified"


def test_celery_stubs_preserve_task_inputs_and_outputs(tmp_path) -> None:
    with tempfile.TemporaryDirectory(prefix="mrw-type-probe-") as probe_root:
        fixtures = ROOT / "tests/typecheck/celery"
        cases = (
            ("positive.py", []),
            ("negative_wrong_task_input.py.txt", ["reportArgumentType", "reportArgumentType"]),
            ("negative_bound_task_input.py.txt", ["reportArgumentType"]),
            ("negative_task_output.py.txt", ["reportAssignmentType"]),
        )
        checker = os.environ.get("MRW_TYPECHECK_PYTHON", sys.executable)
        for fixture, expected_rules in cases:
            probe = Path(probe_root) / "celery_boundary.py"
            probe.write_text((fixtures / fixture).read_text(encoding="utf-8"), encoding="utf-8")
            result = subprocess.run(
                [checker, "-m", "pyright", "--outputjson", "--pythonpath", str(DEV._python_executable()),
                 "--project", str(DEV.PYPROJECT), str(probe)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            assert result.returncode == (1 if expected_rules else 0), result.stdout + result.stderr
            report = json.loads(result.stdout)
            assert report["summary"]["filesAnalyzed"] > 0, report
            diagnostics = report["generalDiagnostics"]
            errors = [item for item in diagnostics if item["severity"] == "error"]
            assert [item["rule"] for item in errors] == expected_rules, diagnostics


def test_public_typecheck_includes_src_and_backend_from_one_declaration(monkeypatch, tmp_path) -> None:
    project = tmp_path / "pyproject.toml"
    project.write_text(
        '[tool.pyright]\ninclude = ["src", "tests", "main/backend/app/example.py"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(DEV, "PYPROJECT", project)
    monkeypatch.setattr(DEV, "_kit_source", lambda: None)
    monkeypatch.setattr(DEV, "_require_kit_source", lambda *_args: True)
    monkeypatch.setattr(DEV, "_python_executable", lambda: Path("/backend/python"))
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        return type("Completed", (), {"returncode": 7})()

    monkeypatch.setattr(DEV.subprocess, "run", run)
    assert DEV.main(["typecheck", "--public-boundaries"]) == 7
    assert commands[0][-2:] == ["src", "main/backend/app/example.py"]
