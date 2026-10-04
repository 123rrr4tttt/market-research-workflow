#!/usr/bin/env python3
"""Thin local development entry for MRW's contribution validation."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
import os
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CATALOG = ROOT / "contributions" / "project_catalog.py"
PILOT_TESTS = (
    "main/backend/tests/unit/test_project_tool_contribution.py",
    "main/backend/tests/successor_runtime/test_i1_c7_c9_assembly.py",
    "main/backend/tests/successor_runtime/test_p4_c8_5_program.py",
    "main/backend/tests/successor_runtime/test_p4_c8_4_graph.py",
    "main/backend/tests/successor_runtime/test_c8_graph_projection_contribution.py",
    "main/backend/tests/successor_runtime/test_c8_typed_knowledge_contribution.py",
    "main/backend/tests/successor_runtime/test_c8_writing_contribution.py",
    "main/backend/tests/successor_runtime/test_c8_report_contribution.py",
    "main/backend/tests/successor_runtime/test_c8_native_catalog.py",
    "main/backend/tests/successor_runtime/test_c1_native_catalog.py",
    "main/backend/tests/successor_runtime/test_c2_native_catalog.py",
    "main/backend/tests/successor_runtime/test_c3_native_catalog.py",
    "main/backend/tests/successor_runtime/test_c4_native_contribution.py",
    "main/backend/tests/successor_runtime/test_c5_native_catalog.py",
    "main/backend/tests/successor_runtime/test_c7_native_catalog.py",
    "main/backend/tests/successor_runtime/test_c9_native_catalog.py",
    "main/backend/tests/successor_runtime/test_retrieval_native_catalog.py",
    "tests/test_c8_semantic_registration.py",
)
ARCHITECTURE_TEST = "tests/test_architecture.py"
VALIDATE_COMMANDS = ("sync", "check", "test", "gates")
_KIT_PACKAGE = "functorial-kit"
_MISSING_KIT_SOURCE = (
    "pyproject.toml must declare valid [tool.mrw.dev-kit] repository, revision, and subdirectory fields"
)
_SOURCE_DECLARATION_MISMATCH = (
    "functorial-kit source declarations do not match [tool.mrw.dev-kit]; "
    "expected {declaration!r} in pyproject.toml and main/backend/requirements.txt"
)
_KIT_PROBE_CODE = """
import importlib.metadata
import json
import pathlib
import sys
import functorial_kit

distribution = importlib.metadata.distribution("functorial-kit")
try:
    direct_url = json.loads(distribution.read_text("direct_url.json"))
except FileNotFoundError:
    direct_url = None
print(json.dumps({
    "module_path": pathlib.Path(functorial_kit.__file__).resolve().as_posix(),
    "distribution_root": pathlib.Path(str(distribution.locate_file(""))).resolve().as_posix(),
    "direct_url": direct_url,
}))
"""


@dataclass(frozen=True)
class KitSource:
    repository: str
    revision: str
    subdirectory: str

    @property
    def requirement(self) -> str:
        return f"git+{self.repository}@{self.revision}#subdirectory={self.subdirectory}"

    @property
    def declaration(self) -> str:
        return f"{_KIT_PACKAGE} @ {self.requirement}"


def _kit_source() -> KitSource:
    try:
        document = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        config = document["tool"]["mrw"]["dev-kit"]
        package = config["package"]
        source = KitSource(
            repository=config["repository"],
            revision=config["revision"],
            subdirectory=config["subdirectory"],
        )
    except (KeyError, OSError, tomllib.TOMLDecodeError, TypeError) as exc:
        raise RuntimeError(_MISSING_KIT_SOURCE) from exc
    fields = (source.repository, source.revision, source.subdirectory)
    if package != _KIT_PACKAGE or not all(isinstance(field, str) and field.strip() for field in fields):
        raise RuntimeError(_MISSING_KIT_SOURCE)
    dependencies = document.get("project", {}).get("dependencies", [])
    requirements = (ROOT / "main" / "backend" / "requirements.txt").read_text(encoding="utf-8").splitlines()
    if source.declaration not in dependencies or source.declaration not in requirements:
        raise RuntimeError(_SOURCE_DECLARATION_MISMATCH.format(declaration=source.declaration))
    return source


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


def _setup_command(python: Path, kit_path: Path | None = None) -> list[str]:
    uv = shutil.which("uv")
    if uv is not None:
        command = [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "--no-deps",
            "--reinstall",
        ]
        if kit_path is not None:
            command.extend(("--editable", str(kit_path)))
        else:
            command.append(_kit_source().requirement)
        return command
    command = [
        str(python),
        "-m",
        "pip",
        "install",
        "--no-deps",
        "--force-reinstall",
    ]
    if kit_path is not None:
        command.extend(("--no-build-isolation", "--editable", str(kit_path)))
    else:
        command.append(_kit_source().requirement)
    return command


def _command_for(command: str, python: Path, *, contribution_id: str | None = None) -> list[str]:
    if command == "setup":
        return _setup_command(python)
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


def _default_provenance_error(direct_url: object, source: KitSource) -> str | None:
    if not isinstance(direct_url, dict):
        return f"installed direct_url metadata is missing; expected Git revision {source.revision}"
    installed_url = direct_url.get("url")
    if not isinstance(installed_url, str):
        return f"installed direct_url metadata has no url; expected Git revision {source.revision}"
    installed = urlparse(installed_url)
    repository = urlparse(source.repository)
    expected_scheme = f"git+{repository.scheme}"
    if installed.scheme == expected_scheme:
        path_revision = installed.path.rsplit("@", 1)
        fragments = parse_qs(installed.fragment)
        repository_matches = (
            len(path_revision) == 2
            and f"{repository.scheme}://{installed.netloc}{path_revision[0]}" == source.repository
        )
        subdirectory_matches = fragments.get("subdirectory") == [source.subdirectory]
    elif installed.scheme == repository.scheme:
        path_revision = [installed.path]
        repository_matches = f"{repository.scheme}://{installed.netloc}{installed.path}" == source.repository
        subdirectory_matches = direct_url.get("subdirectory") == source.subdirectory
    else:
        path_revision = []
        repository_matches = False
        subdirectory_matches = False
    if not repository_matches or not subdirectory_matches:
        return (
            f"installed direct_url is {installed_url}; "
            f"expected {source.repository}@{source.revision}#subdirectory={source.subdirectory}"
        )
    vcs_info = direct_url.get("vcs_info")
    requested_revision = vcs_info.get("requested_revision") if isinstance(vcs_info, dict) else None
    if (
        not isinstance(vcs_info, dict)
        or vcs_info.get("vcs") != "git"
        or vcs_info.get("commit_id") != source.revision
        or (requested_revision is not None and requested_revision != source.revision)
    ):
        return f"installed Git commit does not match fixed revision {source.revision}"
    return None


def _local_provenance_error(direct_url: object, kit_path: Path) -> str | None:
    if not isinstance(direct_url, dict):
        return f"installed direct_url metadata is missing; expected editable checkout {kit_path}"
    installed_url = direct_url.get("url")
    if not isinstance(installed_url, str):
        return f"installed direct_url metadata has no url; expected editable checkout {kit_path}"
    installed = urlparse(installed_url)
    if installed.scheme != "file":
        return f"installed direct_url is {installed_url}; expected editable local checkout {kit_path}"
    installed_path = Path(unquote(installed.path)).resolve()
    dir_info = direct_url.get("dir_info")
    if installed_path != kit_path or not isinstance(dir_info, dict) or dir_info.get("editable") is not True:
        return f"installed direct_url is {installed_url}; expected editable local checkout {kit_path}"
    return None


def _local_kit_revision(kit_path: Path) -> str | None:
    probe = subprocess.run(
        ["git", "-C", str(kit_path), "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        return None
    return probe.stdout.strip() or None


def _setup_hint(python: Path, kit_path: Path | None) -> str:
    command = f"{python} {Path(__file__).resolve()} setup"
    return f"{command} --local-kit {kit_path}" if kit_path is not None else command


def _require_kit_source(python: Path, kit_path: Path | None = None, *, runner=None) -> bool:
    if not python.is_file():
        print(f"MRW dev Python does not exist: {python}", file=sys.stderr)
        return False
    active_runner = subprocess.run if runner is None else runner
    probe = active_runner(
        [str(python), "-c", _KIT_PROBE_CODE],
        cwd=ROOT,
        env=_command_environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        detail = probe.stderr.strip() or probe.stdout.strip() or "functorial_kit is not importable"
        print(f"Selected Python cannot import functorial_kit: {detail}", file=sys.stderr)
        print(f"Run: {_setup_hint(python, kit_path)}", file=sys.stderr)
        return False
    try:
        provenance = json.loads(probe.stdout)
        origin = Path(provenance["module_path"]).resolve()
        distribution_root = Path(provenance["distribution_root"]).resolve()
        direct_url = provenance["direct_url"]
    except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
        print(f"Selected Python returned invalid functorial-kit provenance: {exc}", file=sys.stderr)
        return False
    source = _kit_source()
    if kit_path is None:
        error = _default_provenance_error(direct_url, source)
        if error is None and not origin.is_relative_to(distribution_root):
            error = f"functorial_kit imports from {origin}; expected the installed distribution at {distribution_root}"
        label = f"functorial-kit source: git {source.repository}@{source.revision}"
    else:
        error = _local_provenance_error(direct_url, kit_path)
        if error is None and not origin.is_relative_to(kit_path):
            error = f"functorial_kit imports from {origin}; expected editable source under {kit_path}"
        revision = _local_kit_revision(kit_path)
        if error is None and revision is None:
            error = f"Local functorial-kit source is not a readable Git checkout: {kit_path}"
        label = f"functorial-kit source: local checkout {kit_path}"
        if revision is not None:
            label = f"{label} (Git revision {revision})"
    if error is not None:
        print(
            f"functorial-kit source mismatch: {error}",
            file=sys.stderr,
        )
        print(f"Run: {_setup_hint(python, kit_path)}", file=sys.stderr)
        return False
    print(label, file=sys.stderr)
    return True


def _require_local_kit_path(kit_path: Path) -> bool:
    if not kit_path.is_dir():
        print(f"Local functorial-kit source does not exist: {kit_path}", file=sys.stderr)
        return False
    try:
        package = tomllib.loads((kit_path / "pyproject.toml").read_text(encoding="utf-8"))["project"]["name"]
    except (KeyError, OSError, tomllib.TOMLDecodeError, TypeError):
        print(f"Local functorial-kit source has no functorial-kit package declaration: {kit_path}", file=sys.stderr)
        return False
    if package != _KIT_PACKAGE or _local_kit_revision(kit_path) is None:
        print(f"Local functorial-kit source is not a readable functorial-kit Git checkout: {kit_path}", file=sys.stderr)
        return False
    return True


def _require_setup_environment(python: Path) -> bool:
    if not python.is_file():
        print(f"MRW dev Python does not exist: {python}", file=sys.stderr)
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
    for command in ("setup", "check", "sync", "test", "gates", "validate", "inspect"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument(
            "--local-kit",
            type=Path,
            default=None,
            help="use an explicit local functorial-kit checkout instead of the fixed Git source",
        )
    inspect_parser = subparsers.choices["inspect"]
    inspect_parser.add_argument("--id", dest="contribution_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    python = _python_executable()
    try:
        _kit_source()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    kit_path = None if args.local_kit is None else args.local_kit.expanduser().resolve()
    if kit_path is not None and not _require_local_kit_path(kit_path):
        return 1
    if args.command == "setup" and not _require_setup_environment(python):
        return 1
    if args.command != "setup" and not _require_kit_source(python, kit_path):
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

    if args.command == "setup":
        completed = subprocess.run(
            _setup_command(python, kit_path),
            cwd=ROOT,
            env=_command_environment(),
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode
        return 0 if _require_kit_source(python, kit_path) else 1

    command = _command_for(args.command, python, contribution_id=getattr(args, "contribution_id", None))
    completed = subprocess.run(command, cwd=ROOT, env=_command_environment(), check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
