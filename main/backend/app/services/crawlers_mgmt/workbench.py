"""Thin subprocess adapter for the external concept-architecture-workbench SDK.

This module is deliberately a boundary: it resolves configured targets, builds
a fixed CLI argv, and returns the original exit code and stdout/stderr without
reimplementing any SDK logic.  The SDK owns the authoritative behavior; this
adapter only validates its input boundary and marshals the result.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, TypeGuard, cast

SDK_ROOT_ENV = "MRW_CONCEPT_WORKBENCH_ROOT"
TARGETS_ENV = "MRW_WORKBENCH_TARGETS"

WORKBENCH_MODULE_ID = "concept_workbench.project_wiring"
WORKBENCH_MODULE_TITLE = "概念工作台接线"
WORKBENCH_CELL_REF = "agent.macro.base"

CLI_MODULE = "concept_workbench.cli"
CLI_PACKAGE_DIR = "concept_workbench"
CLI_ENTRYPOINT = "cli.py"

STATUS_REGISTERED = "registered"
STATUS_UNAVAILABLE = "unavailable"

SUBPROCESS_TIMEOUT_SECONDS = 300
TRANSPORT_EXIT_CODE = 127
TIMEOUT_EXIT_CODE = 124
MAX_METHOD_FILE_BYTES = 512 * 1024


OPERATION_DEFINITIONS: tuple[dict[str, str], ...] = (
    {"id": "init", "title": "Initialize workbench target", "effect": "write"},
    {"id": "scan", "title": "Scan registered entries", "effect": "read_only"},
    {"id": "materials", "title": "Observe library materials", "effect": "read_only"},
    {"id": "shapes", "title": "List entry shapes", "effect": "read_only"},
    {"id": "inspect", "title": "Inspect contributions", "effect": "read_only"},
    {"id": "check", "title": "Check contribution config", "effect": "read_only"},
    {"id": "sync", "title": "Sync contribution registries", "effect": "write"},
    {"id": "verify", "title": "Verify contributions", "effect": "execute"},
)


METHOD_DEFINITIONS: tuple[dict[str, str], ...] = (
    {"id": "workbench-authoring", "title": "Workbench authoring"},
    {"id": "workbench-inspect", "title": "Workbench inspect"},
    {"id": "library-analysis", "title": "Library analysis"},
    {"id": "functorial-programming-foundations", "title": "Functorial programming foundations"},
    {"id": "functorial-construction", "title": "Functorial construction"},
    {"id": "compositional-api-design", "title": "Compositional API design"},
    {"id": "effect-interpreter-development", "title": "Effect interpreter development"},
    {"id": "algebraic-property-testing", "title": "Algebraic property testing"},
    {"id": "shared-implementation-context", "title": "Shared implementation context"},
)


_OPERATION_IDS = frozenset(entry["id"] for entry in OPERATION_DEFINITIONS)
_METHOD_IDS = frozenset(entry["id"] for entry in METHOD_DEFINITIONS)


def _is_string_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(
        isinstance(key, str) for key in cast(dict[object, object], value)
    )

_OPERATION_PARAMS: dict[str, frozenset[str]] = {
    "init": frozenset({"target_id"}),
    "scan": frozenset({"target_id", "paths", "catalog", "shape"}),
    "materials": frozenset({"target_id", "paths"}),
    "shapes": frozenset({"target_id", "catalog"}),
    "inspect": frozenset({"target_id", "catalog", "id"}),
    "check": frozenset({"target_id", "catalog"}),
    "sync": frozenset({"target_id", "catalog"}),
    "verify": frozenset({"target_id", "catalog"}),
}


def _project_key(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("project_key is required")
    return value.strip()


def _targets_config() -> dict[str, Any]:
    raw = os.environ.get(TARGETS_ENV, "").strip()
    if not raw:
        return {}
    try:
        value: object = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if _is_string_object_dict(value) else {}


def _sdk_root_env_value() -> str | None:
    raw = os.environ.get(SDK_ROOT_ENV, "").strip()
    return raw or None


def _resolved_sdk_root(value: str | None) -> Path | None:
    if value is None:
        return None
    root = Path(value)
    if not root.is_absolute():
        return None
    try:
        resolved = root.resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_dir():
        return None
    if not (resolved / CLI_PACKAGE_DIR / CLI_ENTRYPOINT).is_file():
        return None
    return resolved


def _require_sdk_root() -> Path:
    value = _sdk_root_env_value()
    if value is None:
        raise ValueError(f"{SDK_ROOT_ENV} is not configured")
    root = _resolved_sdk_root(value)
    if root is None:
        raise ValueError("concept workbench SDK source is unavailable")
    return root


def _functorial_kit_available() -> bool:
    try:
        return importlib.util.find_spec("functorial_kit") is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _method_source_dir(root: Path, method_id: str) -> Path:
    return root / "skills" / method_id


def _method_source_exists(root: Path, method_id: str) -> bool:
    return (_method_source_dir(root, method_id) / "SKILL.md").is_file()


def _flag_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if value.startswith("-"):
        raise ValueError(f"{label} must not begin with '-'")
    if any(ch in value for ch in ("\n", "\r", "\x00")):
        raise ValueError(f"{label} contains an unsafe character")
    return value


def _contained_relative(root: Path, raw: Any, label: str) -> str:
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise ValueError(f"{label} must be a non-empty relative path")
    if raw.startswith("-"):
        raise ValueError(f"{label} must not begin with '-'")
    if "\\" in raw:
        raise ValueError(f"{label} must use POSIX separators")
    if any(ch in raw for ch in ("\n", "\r", "\x00")):
        raise ValueError(f"{label} contains an unsafe character")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"{label} must be a safe relative path")
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} must not contain a symlink component")
    resolved = (root / raw).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} escapes the target root") from error
    return raw


def _resolve_target(target_id: Any, project_key: str) -> dict[str, Any]:
    if not isinstance(target_id, str) or not target_id.strip():
        raise ValueError("target_id is required")
    raw_targets = os.environ.get(TARGETS_ENV, "").strip()
    if not raw_targets:
        raise ValueError("workbench targets are not configured")
    targets = _targets_config()
    entry = targets.get(target_id)
    if entry is None:
        raise ValueError(f"unknown workbench target: {target_id}")
    if not _is_string_object_dict(entry):
        raise ValueError(f"workbench target {target_id} is malformed")
    target_project = entry.get("project_key")
    if target_project != project_key:
        raise ValueError(
            f"workbench target {target_id} belongs to project {target_project!r}, not {project_key!r}"
        )
    raw_root = entry.get("root")
    if not isinstance(raw_root, str) or not raw_root.strip():
        raise ValueError(f"workbench target {target_id} has no root")
    root = Path(raw_root)
    if not root.is_absolute():
        raise ValueError(f"workbench target {target_id} root must be absolute")
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"workbench target {target_id} root is unavailable: {error}") from error
    if not resolved.is_dir():
        raise ValueError(f"workbench target {target_id} root is not a directory")
    return {"id": target_id, "root": resolved, "label": entry.get("label")}


def _validate_arguments(operation: str, arguments: Any) -> dict[str, Any]:
    if not _is_string_object_dict(arguments):
        raise ValueError("arguments must be an object")
    allowed = _OPERATION_PARAMS[operation]
    unknown = set(arguments) - allowed
    if unknown:
        raise ValueError(f"unsupported workbench argument(s): {', '.join(sorted(unknown))}")
    target_id = arguments.get("target_id")
    if not isinstance(target_id, str) or not target_id.strip():
        raise ValueError("target_id is required")
    if "paths" in allowed:
        paths = arguments.get("paths")
        if not isinstance(paths, (list, tuple)) or not paths:
            raise ValueError("paths must be a non-empty list")
    if "catalog" in allowed and "catalog" in arguments:
        _flag_value(arguments["catalog"], "catalog")
    if "shape" in allowed and "shape" in arguments:
        _flag_value(arguments["shape"], "shape")
    if "id" in allowed and "id" in arguments:
        _flag_value(arguments["id"], "id")
    return dict(arguments)


def _build_argv(operation: str, arguments: dict[str, Any], root: Path) -> list[str]:
    argv = [sys.executable, "-B", "-m", CLI_MODULE, operation]
    root_text = str(root)
    if operation == "init":
        argv.append(root_text)
        return argv
    argv.append(f"--root={root_text}")
    if operation in ("scan", "shapes", "inspect", "check", "sync", "verify") and "catalog" in arguments:
        argv.append(f"--catalog={arguments['catalog']}")
    if operation == "scan" and "shape" in arguments:
        argv.append(f"--shape={arguments['shape']}")
    if operation == "inspect" and "id" in arguments:
        argv.append(f"--id={arguments['id']}")
    if operation in ("scan", "materials"):
        argv.append("--")
        argv.extend(arguments["paths"])
    return argv


def _run_subprocess(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _report_from_stdout(stdout: str) -> dict[str, Any] | None:
    if not stdout:
        return None
    try:
        value: object = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return value if _is_string_object_dict(value) else None


def _invoke_cli(argv: list[str], sdk_root: Path) -> dict[str, Any]:
    env = os.environ.copy()
    root_text = str(sdk_root)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = root_text if not existing else root_text + os.pathsep + existing
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = _run_subprocess(argv, env)
    except subprocess.TimeoutExpired as error:
        return {
            "exit_code": TIMEOUT_EXIT_CODE,
            "stdout": error.stdout.decode("utf-8", errors="replace") if isinstance(error.stdout, bytes) else error.stdout or "",
            "stderr": error.stderr.decode("utf-8", errors="replace") if isinstance(error.stderr, bytes) else error.stderr or "",
            "report": None,
        }
    except OSError as error:
        return {
            "exit_code": TRANSPORT_EXIT_CODE,
            "stdout": "",
            "stderr": str(error),
            "report": None,
        }
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    return {
        "exit_code": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "report": _report_from_stdout(stdout),
    }


def workbench_module(project_key: str) -> dict[str, Any]:
    """Read-only module directory for one project; never invokes the CLI."""

    try:
        key = _project_key(project_key)
    except ValueError as error:
        return _unavailable(str(error))

    root = _resolved_sdk_root(_sdk_root_env_value())
    if root is None:
        return _unavailable("concept workbench SDK source is unavailable")
    if not _functorial_kit_available():
        return _unavailable("functorial_kit dependency is unavailable")

    targets = _targets_config()
    project_targets: list[dict[str, str]] = []
    for target_id, entry in targets.items():
        if not _is_string_object_dict(entry):
            continue
        if entry.get("project_key") != key:
            continue
        try:
            _resolve_target(target_id, key)
        except ValueError:
            continue
        label = entry.get("label")
        project_targets.append({"id": target_id, "label": str(label) if label else target_id})
    if not project_targets:
        return _unavailable(f"no workbench targets configured for project {key!r}")

    missing_methods = [entry["id"] for entry in METHOD_DEFINITIONS if not _method_source_exists(root, entry["id"])]
    if missing_methods:
        return _unavailable(f"workbench method sources are missing: {', '.join(missing_methods)}")

    methods = [
        {"id": entry["id"], "title": entry["title"]}
        for entry in METHOD_DEFINITIONS
        if _method_source_exists(root, entry["id"])
    ]
    return {
        "id": WORKBENCH_MODULE_ID,
        "title": WORKBENCH_MODULE_TITLE,
        "status": STATUS_REGISTERED,
        "available": True,
        "reason": None,
        "cell_ref": WORKBENCH_CELL_REF,
        "operations": [
            {"id": entry["id"], "title": entry["title"], "effect": entry["effect"]}
            for entry in OPERATION_DEFINITIONS
        ],
        "methods": methods,
        "targets": project_targets,
    }


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "id": WORKBENCH_MODULE_ID,
        "title": WORKBENCH_MODULE_TITLE,
        "status": STATUS_UNAVAILABLE,
        "available": False,
        "reason": reason,
        "cell_ref": WORKBENCH_CELL_REF,
        "operations": [
            {"id": entry["id"], "title": entry["title"], "effect": entry["effect"]}
            for entry in OPERATION_DEFINITIONS
        ],
        "methods": [],
        "targets": [],
    }


def run_workbench(operation: object, arguments: dict[str, Any], project_key: str) -> dict[str, Any]:
    """Run one whitelisted operation against a configured target via the SDK CLI."""

    key = _project_key(project_key)
    if not isinstance(operation, str) or operation not in _OPERATION_IDS:
        raise ValueError(f"unsupported workbench operation: {operation!r}")
    validated = _validate_arguments(operation, arguments)
    root = _require_sdk_root()
    target = _resolve_target(validated["target_id"], key)
    target_root = target["root"]
    if "paths" in validated:
        for raw_path in validated["paths"]:
            _contained_relative(target_root, raw_path, "path")
    if "catalog" in validated:
        _contained_relative(target_root, validated["catalog"], "catalog")
    argv = _build_argv(operation, validated, target_root)
    return _invoke_cli(argv, root)


def read_workbench_method(method_id: object, relative_path: str = "SKILL.md") -> dict[str, Any]:
    """Read one SDK skill text file and return its source reference and digest."""

    if not isinstance(method_id, str) or method_id not in _METHOD_IDS:
        raise ValueError(f"unsupported workbench method: {method_id!r}")
    root = _require_sdk_root()
    method_dir = _method_source_dir(root, method_id)
    if not method_dir.is_dir():
        raise ValueError(f"workbench method source is missing: {method_id}")
    relative = _contained_relative(method_dir, relative_path, "relative_path")
    target = method_dir / relative
    if not target.is_file():
        raise ValueError(f"workbench method file is missing: {method_id}/{relative}")
    stat = target.stat()
    if stat.st_size > MAX_METHOD_FILE_BYTES:
        raise ValueError(f"workbench method file exceeds {MAX_METHOD_FILE_BYTES} bytes: {method_id}/{relative}")
    data = target.read_bytes()
    if len(data) > MAX_METHOD_FILE_BYTES:
        raise ValueError(f"workbench method file exceeds {MAX_METHOD_FILE_BYTES} bytes: {method_id}/{relative}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"workbench method file is not UTF-8 text: {method_id}/{relative}") from error
    return {
        "source_ref": f"skills/{method_id}/{relative}",
        "content_digest": hashlib.sha256(data).hexdigest(),
        "content_text": text,
    }
