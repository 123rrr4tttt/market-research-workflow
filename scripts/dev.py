#!/usr/bin/env python3
"""Thin local development entry for MRW's functorial contribution pilot."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CATALOG = ROOT / "contributions" / "c8_graph_projection_catalog.py"
PILOT_TESTS = (
    "main/backend/tests/successor_runtime/test_i1_c7_c9_assembly.py",
    "main/backend/tests/successor_runtime/test_p4_c8_5_program.py",
    "main/backend/tests/successor_runtime/test_p4_c8_4_graph.py",
    "main/backend/tests/successor_runtime/test_c8_graph_projection_contribution.py",
    "tests/test_c8_semantic_registration.py",
)
ARCHITECTURE_TEST = "tests/test_architecture.py"
VALIDATE_COMMANDS = ("sync", "check", "test", "gates")
_MISSING_KIT_SOURCE = "pyproject.toml must declare [tool.uv.sources].functorial-kit.path"
_INVALID_KIT_SOURCE = "[tool.uv.sources].functorial-kit.path must be a non-empty string"


def _local_kit_path() -> Path:
    try:
        document = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        source = document["tool"]["uv"]["sources"]["functorial-kit"]
        path = source["path"]
    except (KeyError, OSError, tomllib.TOMLDecodeError, TypeError) as exc:
        raise RuntimeError(_MISSING_KIT_SOURCE) from exc
    if not isinstance(path, str) or not path.strip():
        raise RuntimeError(_INVALID_KIT_SOURCE)
    return (ROOT / path).resolve()


def _python_executable() -> Path:
    configured = os.environ.get("MRW_DEV_PYTHON")
    if configured:
        return Path(configured).expanduser().absolute()
    candidates = (
        ROOT / "main" / "backend" / ".venv311" / "bin" / "python",
        ROOT / "main" / "backend" / ".venv311" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
        ROOT / ".venv" / "Scripts" / "python.exe",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), Path(sys.executable).absolute())


def _command_environment() -> dict[str, str]:
    env = dict(os.environ)
    imports = [str(ROOT / "src"), str(ROOT / "main" / "backend")]
    inherited = env.get("PYTHONPATH")
    if inherited:
        imports.append(inherited)
    env["PYTHONPATH"] = os.pathsep.join(imports)
    return env


def _setup_command(python: Path, kit_path: Path) -> list[str]:
    uv = shutil.which("uv")
    if uv is not None:
        return [
            uv,
            "pip",
            "install",
            "--offline",
            "--python",
            str(python),
            "--no-deps",
            "--editable",
            str(kit_path),
        ]
    return [
        str(python),
        "-m",
        "pip",
        "install",
        "--no-deps",
        "--no-build-isolation",
        "--editable",
        str(kit_path),
    ]


def _command_for(command: str, python: Path, *, contribution_id: str | None = None) -> list[str]:
    if command == "setup":
        return _setup_command(python, _local_kit_path())
    if command in {"check", "sync", "inspect"}:
        argv = [
            str(python),
            "-m",
            "functorial_kit",
            "contributions",
            command,
            "--catalog",
            str(CATALOG),
            "--root",
            str(ROOT),
        ]
        if command == "inspect" and contribution_id is not None:
            argv.extend(("--id", contribution_id))
        return argv
    if command == "test":
        return [str(python), "-m", "pytest", "-q", "-p", "no:cacheprovider", *PILOT_TESTS]
    if command == "gates":
        return [str(python), "-m", "pytest", "-q", "-p", "no:cacheprovider", ARCHITECTURE_TEST]
    raise ValueError(command)


def _require_local_kit(python: Path, kit_path: Path) -> bool:
    if not python.is_file():
        print(f"MRW dev Python does not exist: {python}", file=sys.stderr)
        return False
    if not kit_path.is_dir():
        print(f"Local functorial-kit source does not exist: {kit_path}", file=sys.stderr)
        return False
    probe = subprocess.run(
        [str(python), "-c", "import pathlib, functorial_kit; print(pathlib.Path(functorial_kit.__file__).resolve())"],
        cwd=ROOT,
        env=_command_environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        detail = probe.stderr.strip() or probe.stdout.strip() or "functorial_kit is not importable"
        print(f"Selected Python cannot import functorial_kit: {detail}", file=sys.stderr)
        print(f"Run: {python} {Path(__file__).resolve()} setup", file=sys.stderr)
        return False
    origin = Path(probe.stdout.strip()).resolve()
    if not origin.is_relative_to(kit_path):
        print(
            f"Selected Python imports functorial_kit from {origin}; expected editable source under {kit_path}",
            file=sys.stderr,
        )
        print(f"Run: {python} {Path(__file__).resolve()} setup", file=sys.stderr)
        return False
    return True


def _require_setup_environment(python: Path, kit_path: Path) -> bool:
    if not python.is_file():
        print(f"MRW dev Python does not exist: {python}", file=sys.stderr)
        return False
    if not kit_path.is_dir():
        print(f"Local functorial-kit source does not exist: {kit_path}", file=sys.stderr)
        return False
    if shutil.which("uv") is not None:
        return True
    probe = subprocess.run(
        [str(python), "-m", "pip", "--version"],
        cwd=ROOT,
        env=_command_environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode == 0:
        return True
    detail = probe.stderr.strip() or probe.stdout.strip() or "pip is not installed"
    print(f"uv is unavailable and the selected Python cannot run pip: {detail}", file=sys.stderr)
    return False


def _require_test_environment(python: Path, *, backend_dependencies: bool) -> bool:
    imports = "import pytest, sqlalchemy" if backend_dependencies else "import pytest"
    probe = subprocess.run(
        [str(python), "-c", imports],
        cwd=ROOT,
        env=_command_environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode == 0:
        return True
    detail = probe.stderr.strip() or probe.stdout.strip()
    print(
        "Selected Python lacks the required test environment "
        f"({detail}). Use main/backend/.venv311 or set MRW_DEV_PYTHON to an equivalent environment.",
        file=sys.stderr,
    )
    return False


def _run_validate(python: Path, *, runner=None) -> int:
    """Run development validation stages sequentially without masking an earlier failure."""
    active_runner = subprocess.run if runner is None else runner
    for command_name in VALIDATE_COMMANDS:
        completed = active_runner(
            _command_for(command_name, python),
            cwd=ROOT,
            env=_command_environment(),
            check=False,
        )
        returncode = completed.returncode
        if returncode != 0:
            return returncode
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("setup", "check", "sync", "test", "gates", "validate"):
        subparsers.add_parser(command)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--id", dest="contribution_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    python = _python_executable()
    try:
        kit_path = _local_kit_path()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.command == "setup" and not _require_setup_environment(python, kit_path):
        return 1
    if args.command != "setup" and not _require_local_kit(python, kit_path):
        return 1
    if args.command in {"test", "gates"} and not _require_test_environment(
        python,
        backend_dependencies=args.command == "test",
    ):
        return 1
    if args.command == "validate":
        if not _require_test_environment(python, backend_dependencies=True):
            return 1
        return _run_validate(python)

    command = _command_for(args.command, python, contribution_id=getattr(args, "contribution_id", None))
    completed = subprocess.run(command, cwd=ROOT, env=_command_environment(), check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
