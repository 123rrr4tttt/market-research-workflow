#!/usr/bin/env python3
# ruff: noqa: E402, TRY003, TRY301
"""Build a canonical exact-file manifest for a Stage 2 candidate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import threading
import unicodedata
from collections.abc import Iterable, Sequence
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath
from typing import Annotated, Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.formal_release.model import (
    CreateOnlyWriteError,
    DirectoryIdentity,
    Finding,
    PreflightReport,
    directory_identity,
    write_create_only_bytes,
)
from scripts.formal_release.stage2_git_batch import (
    BaseTreeIndex,
    BoundedReadOnlyCache,
    GitBatchError,
    IntakeCacheKey,
    IntakeCacheValue,
    git_blob_oid,
    make_intake_cache_key,
)
from scripts.formal_release.source_closure import (
    SourceClosureError,
    check_source_closure,
    is_mrw_projected_candidate,
)
from scripts.formal_release import source_closure as source_closure_module
from scripts import stage_family_fragment_rebind
from scripts.formal_release import generate_stage1_production_contract_record
from scripts.formal_release import generate_stage1_current_binding_successor


SCHEMA_VERSION_V2 = "mrw.stage2.exact-candidate-manifest.v2"
SCHEMA_VERSION_V3 = "mrw.stage2.exact-candidate-manifest.v3"
SCHEMA_VERSION_V4 = "mrw.stage2.exact-candidate-manifest.v4"
SCHEMA_VERSION_V5 = "mrw.stage2.exact-candidate-manifest.v5"
# Preserve the public constant for legacy callers and fixtures.  A v3 manifest
# is selected only when both successor bindings are supplied explicitly.
SCHEMA_VERSION = SCHEMA_VERSION_V2
MANIFEST_STATUS = "EXACT_CANDIDATE_INTAKE_NOT_AUTHORITY"
CHECKER = "stage2-candidate-intake"
DEFAULT_BASE_REF = "refs/remotes/origin/main"
DEFAULT_REMOTE_NAME = "origin"
DEFAULT_STAGE0_ROOT = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
    "stage-b23-2026-09-05"
)
STAGE0_FAMILIES = ("C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "I1")
STAGE0_CANDIDATE_PATHS = tuple(
    DEFAULT_STAGE0_ROOT / "candidates" / family / "candidate.v2.json"
    for family in STAGE0_FAMILIES
)
FRESH_STAGE0_ROOT = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
    "stage-b23-2026-09-08"
)
FRESH_STAGE0_CANDIDATE_PATHS = tuple(
    FRESH_STAGE0_ROOT / "candidates" / family / "candidate.v2.json"
    for family in STAGE0_FAMILIES
)
# The regression suites exercise the frozen v3 builder and the current family
# rebind candidates. These are recursive test inputs, not direct v4 Stage0 refs.
SUCCESSOR_RUNTIME_CANDIDATE_PATHS = tuple(
    FRESH_STAGE0_ROOT.parent / "stage-b23-2026-09-07" / "candidates" / family / "candidate.v2.json"
    for family in ("C4", "C6", "C7", "C9")
)
FRESH_V4_HISTORICAL_STAGE0_CANDIDATE_PATHS = (
    *STAGE0_CANDIDATE_PATHS,
    *SUCCESSOR_RUNTIME_CANDIDATE_PATHS,
)
FRESH_C9_SIDECAR_INPUT = FRESH_STAGE0_ROOT / "sidecar-inputs/C9.v8.json"
DEFAULT_CURRENT_BYTE_SUCCESSOR_REGISTRY = Path(
    "stage1-successor-evidence/current-byte-remediation-v1/bindings/"
    "current-byte-binding-successors.v1.json"
)
DEFAULT_CURRENT_BYTE_SUCCESSOR_CHECKER = Path(
    "stage1-successor-evidence/current-byte-remediation-v1/bindings/"
    "check_current_byte_binding_successors.py"
)
STAGE3_CURRENT_BYTE_SUCCESSOR_REGISTRY = Path(
    "stage1-successor-evidence/current-byte-remediation-v2/bindings/"
    "current-byte-binding-successors.v2.json"
)
STAGE3_CURRENT_BYTE_SUCCESSOR_CHECKER = Path(
    "stage1-successor-evidence/current-byte-remediation-v2/bindings/"
    "check_current_byte_binding_successors_v2.py"
)
CONVERGENCE_CURRENT_BYTE_SUCCESSOR_REGISTRY = Path(
    "stage1-successor-evidence/current-byte-remediation-v3/bindings/"
    "current-byte-binding-successors.v3.json"
)
CONVERGENCE_CURRENT_BYTE_SUCCESSOR_CHECKER = Path(
    "stage1-successor-evidence/current-byte-remediation-v3/bindings/"
    "check_current_byte_binding_successors_v3.py"
)
FRESH_CURRENT_BYTE_SUCCESSOR_REGISTRY = Path(
    "stage1-successor-evidence/current-byte-remediation-v4/bindings/"
    "current-byte-binding-successors.v4.json"
)
FRESH_CURRENT_BYTE_SUCCESSOR_CHECKER = Path(
    "stage1-successor-evidence/current-byte-remediation-v4/bindings/"
    "check_current_byte_binding_successors_v4.py"
)
ALL_LINES_AGGREGATE = Path(
    "stage1-successor-evidence/stage-convergence-batch-v1/all-lines/"
    "all-lines-exact-byte-aggregate.v1.json"
)
ALL_LINES_AGGREGATE_PRODUCER = Path(
    "scripts/formal_release/generate_stage1_all_lines_exact_byte_rebind.py"
)
ALL_LINES_AGGREGATE_SCHEMA = "mrw.all_lines_exact_byte_aggregate.v1"
ALL_LINES_AGGREGATE_STATUS = "LOCAL_DEVELOPMENT_ONLY_NOT_AUTHORITY"
STAGE1_PRODUCTION_BINDING_SUCCESSOR = (
    generate_stage1_current_binding_successor.OUTPUT_REL
)
DEFAULT_STAGE1_REMEDIATION_RECORD = Path(
    "stage1-successor-evidence/stage2-v5-intake-remediation-v2/"
    "stage2-v5-intake-remediation-record.v2.json"
)
DEFAULT_STAGE1_REMEDIATION_CHECKER = Path(
    "stage1-successor-evidence/stage2-v5-intake-remediation-v2/"
    "check_stage2_v5_intake_remediation_v2.py"
)
WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_RECORD = Path(
    "stage1-successor-evidence/stage2-v6-intake-remediation-v5/"
    "stage2-v6-intake-remediation-record.v5.json"
)
WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_CHECKER = Path(
    "stage1-successor-evidence/stage2-v6-intake-remediation-v5/"
    "check_stage2_v6_intake_remediation_v5.py"
)
STAGE3_V6_ARTIFACT_REMEDIATION_RECORD = Path(
    "stage1-successor-evidence/stage3-v6-artifact-remediation-v1/"
    "stage3-v6-artifact-remediation-record.v1.json"
)
STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD = Path(
    "stage1-successor-evidence/stage3-v6-artifact-remediation-v1/"
    "stage3-v6-artifact-remediation-record.v1.correction1.json"
)
STAGE3_V6_ARTIFACT_REMEDIATION_RECORDS = frozenset(
    {
        STAGE3_V6_ARTIFACT_REMEDIATION_RECORD,
        STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD,
    }
)
STAGE3_V6_ARTIFACT_REMEDIATION_RECORD_PATHS = frozenset(
    path.as_posix() for path in STAGE3_V6_ARTIFACT_REMEDIATION_RECORDS
)
STAGE3_V6_ARTIFACT_REMEDIATION_CHECKER = Path(
    "stage1-successor-evidence/stage3-v6-artifact-remediation-v1/"
    "check_stage3_v6_artifact_remediation_v1.py"
)
STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_DIR = Path(
    "stage1-successor-evidence/stage3-v6-artifact-remediation-correction2/package"
)
STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_RECORD = (
    STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_DIR
    / "stage3-v6-artifact-remediation-record.v1.correction2.json"
)
STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_MANIFEST = (
    STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_DIR
    / "artifact-manifest.v1.correction2.json"
)
STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_VALIDATION = (
    STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_DIR
    / "validation-receipt.v1.correction2.json"
)
STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_HASHES = {
    STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_RECORD: (
        "86073cd6495963d9dd6161b12e412cb45ff68bff527686c9387f25fbf5f2c96b"
    ),
    STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_MANIFEST: (
        "0bc405fb77d58f8621191062f9650811cd0ed0f8d1deff15d0ad36f223d01199"
    ),
    STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_VALIDATION: (
        "a9d3982734f9da8ed6755993f1cc5c066e07b6ce5c7798b60efd533a5713eccc"
    ),
}
CONTRACT14_HISTORY_PREFIX_PARTS = tuple(
    Path("stage1-successor-evidence/contract14-local-execution-v1/history").parts
)
# Some frozen B23 family candidates share exact source bindings with I1 cells.
# The current-byte registry owns one normative I1 successor per byte chain.
# These aliases are closed by family, source path and successor ID; matching
# still requires exact predecessor and live successor hashes.
SHARED_STAGE0_SUCCESSOR_ALIASES = {
    ("C2", "main/backend/app/celery_app.py"): "i1-c5-4-celery-app-current-bytes-v1",
    ("C5", "main/backend/app/celery_app.py"): "i1-c5-4-celery-app-current-bytes-v1",
    (
        "C6",
        "main/backend/app/services/agent_core/native_provider.py",
    ): "i1-c6-native-provider-current-bytes-v2",
}
B23_FROZEN_DIRECTORIES = frozenset({"fragments", "manifests", "snapshots"})
GIT_OID = re.compile(r"^[0-9a-f]{40,64}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UPSTREAM_VALIDATOR_LOCK = threading.RLock()

FORBIDDEN_COMPONENTS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".runtime",
        ".tmp",
        "__pypackages__",
        "__pycache__",
        "cache",
        "caches",
        "node_modules",
        "runtime",
        "runtime-cache",
        "tmp",
    }
)
SOURCE_RUNTIME_PREFIX_PARTS = tuple(
    Path("main/backend/app/successor_runtime/runtime").parts
)
HISTORY_COMPONENTS = frozenset({".history", "file-history", "history", "local-history"})
SECRET_DIRECTORY_NAMES = frozenset({".credentials", ".secrets", "credentials", "secrets"})
SECRET_FILE_NAMES = frozenset(
    {
        ".netrc",
        ".npmrc",
        ".pypirc",
        ".token",
        "credential",
        "credentials.json",
        "credentials.yaml",
        "credentials.yml",
        "id_ed25519",
        "id_rsa",
        "password",
        "password.txt",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
        "token.json",
        "token.yaml",
        "token.yml",
        "tokens.json",
    }
)
SECRET_FILE_SUFFIXES = (".key", ".p12", ".pem", ".pfx", ".token")
RUNTIME_FILE_SUFFIXES = (".db", ".lock", ".pid", ".pyc", ".pyo", ".sqlite", ".sqlite3")
SAFE_ENV_FILE_NAMES = frozenset({".env.example", ".env.production.example"})

__all__ = [
    "BaseTreeIndex",
    "BoundedReadOnlyCache",
    "GitBatchError",
    "IntakeCacheKey",
    "IntakeCacheValue",
    "git_blob_oid",
    "make_intake_cache_key",
    "cached_base_index",
    "build_manifest",
    "validate_manifest_structure",
    "validate_manifest",
]


class Stage2IntakeError(RuntimeError):
    """Raised when exact-candidate intake cannot be established."""


WorkflowSelectorDelta = tuple[tuple[str, Path], ...]


GenerationError = Stage2IntakeError
ValidationError = Stage2IntakeError


def _manifest_cache_key(
    manifest: dict[str, Any],
    *,
    object_format: str,
) -> IntakeCacheKey:
    source = manifest["source"]
    return make_intake_cache_key(
        schema=manifest["schema_version"],
        resolved_source=source["checkout"],
        dev=source["dev"],
        ino=source["ino"],
        head=source["head"],
        porcelain_sha256=source["porcelain_sha256"],
        canonical_manifest_sha256=sha256_bytes(canonical_json(manifest)),
        base_oid=source["base_oid"],
        object_format=object_format,
    )


def cached_base_index(
    manifest: dict[str, Any],
    current_source_fingerprint: dict[str, Any],
    read_cache: BoundedReadOnlyCache[IntakeCacheKey, IntakeCacheValue],
) -> BaseTreeIndex | None:
    """Return a hit only when all source, manifest, base, and format fields match."""
    try:
        source = manifest["source"]
        if not isinstance(source, dict) or not isinstance(current_source_fingerprint, dict):
            return None
        object_format = current_source_fingerprint.get("object_format")
        if object_format != "sha1":
            return None
        key = make_intake_cache_key(
            schema=manifest["schema_version"],
            resolved_source=current_source_fingerprint["checkout"],
            dev=current_source_fingerprint["dev"],
            ino=current_source_fingerprint["ino"],
            head=current_source_fingerprint["head"],
            porcelain_sha256=current_source_fingerprint["porcelain_sha256"],
            canonical_manifest_sha256=sha256_bytes(canonical_json(manifest)),
            base_oid=current_source_fingerprint["base_oid"],
            object_format=object_format,
        )
        if key != _manifest_cache_key(manifest, object_format=object_format):
            return None
        value = read_cache.get(key)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if not isinstance(value, IntakeCacheValue):
        return None
    index = value.base_index
    if not isinstance(index, BaseTreeIndex):
        return None
    try:
        source_checkout = Path(source["checkout"]).resolve()
        index_root = Path(index.repo_root).resolve()
    except (KeyError, TypeError, OSError):
        return None
    if (
        index.base_oid != source.get("base_oid")
        or index.object_format != object_format
        or index_root != source_checkout
    ):
        return None
    return index


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_relative(relative: Path | str, *, label: str = "path") -> Path:
    original = relative if isinstance(relative, str) else None
    try:
        candidate = Path(relative)
    except TypeError as exc:
        raise Stage2IntakeError(f"{label} must be a path: {relative!r}") from exc
    raw = candidate.as_posix()
    if original is not None and (
        original != raw or "\\" in original or PureWindowsPath(original).drive
    ):
        raise Stage2IntakeError(f"{label} is not a canonical POSIX path: {relative}")
    if (
        not candidate.parts
        or raw == "."
        or candidate.is_absolute()
        or raw.startswith("/")
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or "\x00" in raw
    ):
        raise Stage2IntakeError(f"{label} escapes repository root or is empty: {relative}")
    if raw != unicodedata.normalize("NFC", raw):
        raise Stage2IntakeError(f"{label} is not NFC-normalized: {relative}")
    lowered_parts = tuple(part.casefold() for part in candidate.parts)
    if ".git" in lowered_parts:
        raise Stage2IntakeError(f"{label} intersects git metadata: {relative}")
    source_runtime = lowered_parts[: len(SOURCE_RUNTIME_PREFIX_PARTS)] == SOURCE_RUNTIME_PREFIX_PARTS
    allowed_contract14_history = (
        lowered_parts[: len(CONTRACT14_HISTORY_PREFIX_PARTS)]
        == CONTRACT14_HISTORY_PREFIX_PARTS
        and len(lowered_parts) > len(CONTRACT14_HISTORY_PREFIX_PARTS)
    )
    if any(
        part in FORBIDDEN_COMPONENTS and not (part == "runtime" and source_runtime)
        for part in lowered_parts
    ) or (
        any(part in HISTORY_COMPONENTS for part in lowered_parts)
        and not allowed_contract14_history
    ):
        raise Stage2IntakeError(f"{label} is in a forbidden history/cache/runtime path: {relative}")
    if any(part in SECRET_DIRECTORY_NAMES for part in lowered_parts[:-1]):
        raise Stage2IntakeError(f"{label} intersects a secret directory: {relative}")

    filename = candidate.name.casefold()
    if filename in SECRET_FILE_NAMES or any(filename.endswith(suffix) for suffix in SECRET_FILE_SUFFIXES):
        raise Stage2IntakeError(f"{label} looks like a secret file: {relative}")
    if filename.startswith(".env.") and filename not in SAFE_ENV_FILE_NAMES:
        raise Stage2IntakeError(f"{label} looks like a live environment file: {relative}")
    if filename == ".env":
        raise Stage2IntakeError(f"{label} looks like a live environment file: {relative}")
    if any(filename.endswith(suffix) for suffix in RUNTIME_FILE_SUFFIXES) or filename == ".ds_store":
        raise Stage2IntakeError(f"{label} looks like a runtime or cache file: {relative}")
    if lowered_parts[:2] == (".git",) or ".git" in lowered_parts:
        raise Stage2IntakeError(f"{label} intersects git metadata: {relative}")
    return candidate


def assert_no_path_collisions(paths: Iterable[Path]) -> None:
    normalized: dict[str, Path] = {}
    for path in paths:
        key = unicodedata.normalize("NFC", path.as_posix()).casefold()
        if key in normalized and normalized[key] != path:
            raise Stage2IntakeError(
                f"case or NFC path collision: {normalized[key].as_posix()} and {path.as_posix()}"
            )
        normalized[key] = path


def _git_env() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    return env


def git_output(repo_root: Path, *args: str, stdin: bytes | None = None) -> bytes:
    completed = subprocess.run(
        ("git", "-c", "core.fsmonitor=false", "-C", str(repo_root), *args),
        check=False,
        input=stdin,
        capture_output=True,
        env=_git_env(),
    )
    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace").strip() or (
            f"git {' '.join(args)} exited {completed.returncode}"
        )
        raise Stage2IntakeError(error)
    return completed.stdout


def git_text(repo_root: Path, *args: str) -> str:
    return git_output(repo_root, *args).decode("utf-8").strip()


@contextmanager
def _stable_upstream_validators(
    source_root: Path,
    expected_identity: DirectoryIdentity,
):
    """Run unmodified upstream validators against a stable source-root fd."""
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    root_fd = os.open(source_root, directory_flags)
    try:
        root_identity = os.fstat(root_fd)
        if (root_identity.st_dev, root_identity.st_ino) != expected_identity:
            raise Stage2IntakeError("source checkout identity changed")
        with _UPSTREAM_VALIDATOR_LOCK:
            usage = {
                "root_opener": False,
                "stage1_reader": False,
                "migration_lister": False,
                "api_lister": False,
            }
            original_root_opener = stage_family_fragment_rebind._open_root
            original_stage1_read = generate_stage1_production_contract_record._read
            original_migration_rels = generate_stage1_production_contract_record._migration_rels
            original_api_rels = generate_stage1_production_contract_record._api_rels

            def stable_root_opener(root: Path) -> int:
                if Path(root).absolute() != source_root.absolute():
                    raise stage_family_fragment_rebind.ValidationError(
                        "validator opened a root outside the stable source binding"
                    )
                usage["root_opener"] = True
                return os.dup(root_fd)

            def stable_stage1_read(root: Path, relative: Path | str) -> bytes:
                if Path(root).absolute() != source_root.absolute():
                    raise generate_stage1_production_contract_record.Stage1RecordError(
                        "validator read outside the stable source binding"
                    )
                usage["stage1_reader"] = True
                payload, _metadata = _read_regular_bytes(
                    source_root,
                    safe_relative(relative, label="Stage1 validator input"),
                    label="Stage1 validator input",
                    expected_identity=expected_identity,
                    stable_root_fd=root_fd,
                )
                return payload

            def open_directory_beneath_root(relative: Path) -> int:
                flags = directory_flags
                descriptor = os.dup(root_fd)
                try:
                    for part in relative.parts:
                        child = os.open(part, flags, dir_fd=descriptor)
                        os.close(descriptor)
                        descriptor = child
                        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
                except Exception:
                    os.close(descriptor)
                    raise
                else:
                    return descriptor

            def stable_migration_rels(root: Path) -> tuple[Path, ...]:
                if Path(root).absolute() != source_root.absolute():
                    raise generate_stage1_production_contract_record.Stage1RecordError(
                        "validator enumerated migrations outside the stable source binding"
                    )
                usage["migration_lister"] = True
                relative = generate_stage1_production_contract_record.MIGRATION_VERSIONS_DIR
                descriptor = open_directory_beneath_root(relative)
                try:
                    names = sorted(os.listdir(descriptor))
                finally:
                    os.close(descriptor)
                discovered = tuple(
                    relative / name
                    for name in names
                    if name.endswith(".py") and name != "__init__.py"
                )
                merge = generate_stage1_production_contract_record.MIGRATION_MERGE_REL
                if merge not in discovered:
                    raise generate_stage1_production_contract_record.Stage1RecordError(
                        f"required input missing: {relative.as_posix()}"
                    )
                return generate_stage1_production_contract_record.MIGRATION_RELS + discovered

            def stable_api_rels(root: Path) -> tuple[Path, ...]:
                if Path(root).absolute() != source_root.absolute():
                    raise generate_stage1_production_contract_record.Stage1RecordError(
                        "validator enumerated API handlers outside the stable source binding"
                    )
                usage["api_lister"] = True
                relative = Path("main/backend/app/api")
                descriptor = open_directory_beneath_root(relative)
                try:
                    names = sorted(os.listdir(descriptor))
                finally:
                    os.close(descriptor)
                return tuple(
                    relative / name
                    for name in names
                    if name.endswith(".py")
                )

            stage_family_fragment_rebind._open_root = stable_root_opener
            generate_stage1_production_contract_record._read = stable_stage1_read
            generate_stage1_production_contract_record._migration_rels = stable_migration_rels
            generate_stage1_production_contract_record._api_rels = stable_api_rels
            try:
                yield usage
            finally:
                stage_family_fragment_rebind._open_root = original_root_opener
                generate_stage1_production_contract_record._read = original_stage1_read
                generate_stage1_production_contract_record._migration_rels = original_migration_rels
                generate_stage1_production_contract_record._api_rels = original_api_rels
    finally:
        os.close(root_fd)


def _porcelain(repo_root: Path) -> bytes:
    return git_output(repo_root, "status", "--porcelain=v1", "--untracked-files=all", "-z")


def _resolved_without_parent_symlinks(source_root: Path, relative: Path) -> Path:
    root = source_root.resolve(strict=True)
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError as exc:
            raise Stage2IntakeError(f"source parent missing: {relative.as_posix()}") from exc
        if stat.S_ISLNK(mode):
            raise Stage2IntakeError(f"source parent is a symlink: {relative.as_posix()}")
        if not current.is_dir():
            raise Stage2IntakeError(f"source parent is not a directory: {relative.as_posix()}")
    absolute = root / relative
    resolved = absolute.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        if absolute.is_symlink():
            raise Stage2IntakeError(f"symlink escapes checkout: {relative.as_posix()}") from exc
        raise Stage2IntakeError(f"source path escapes checkout: {relative.as_posix()}") from exc
    return absolute


def _open_parent_dirfd(
    source_root: Path,
    relative: Path,
    *,
    expected_identity: DirectoryIdentity | None = None,
    stable_root_fd: int | None = None,
) -> int:
    """Open a path's parent beneath source_root without following directory symlinks."""
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if stable_root_fd is not None:
        descriptor = os.dup(stable_root_fd)
    else:
        try:
            descriptor = os.open(source_root, directory_flags)
        except OSError as exc:
            if expected_identity is not None:
                raise Stage2IntakeError(
                    "source checkout cannot be opened with expected identity"
                ) from exc
            raise
    try:
        identity = os.fstat(descriptor)
        if (
            expected_identity is not None
            and (identity.st_dev, identity.st_ino) != expected_identity
        ):
            raise Stage2IntakeError("source checkout identity changed")
        for part in relative.parts[:-1]:
            child = os.open(part, directory_flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _open_parent_dirfd_with_identity(
    source_root: Path,
    relative: Path,
    *,
    expected_identity: DirectoryIdentity | None = None,
    stable_root_fd: int | None = None,
) -> tuple[int, os.stat_result]:
    descriptor = _open_parent_dirfd(
        source_root,
        relative,
        expected_identity=expected_identity,
        stable_root_fd=stable_root_fd,
    )
    try:
        return descriptor, os.fstat(descriptor)
    except Exception:
        os.close(descriptor)
        raise


def _close_optional_fd(descriptor: int | None) -> None:
    if descriptor is not None:
        os.close(descriptor)


def _open_beneath(
    source_root: Path,
    relative: Path,
    flags: int,
    *,
    expected_identity: DirectoryIdentity | None = None,
    stable_root_fd: int | None = None,
) -> int:
    parent = _open_parent_dirfd(
        source_root,
        relative,
        expected_identity=expected_identity,
        stable_root_fd=stable_root_fd,
    )
    try:
        return os.open(
            relative.name,
            flags | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent,
        )
    finally:
        os.close(parent)


def _lstat_beneath(
    source_root: Path,
    relative: Path,
    *,
    expected_identity: DirectoryIdentity | None = None,
) -> os.stat_result:
    parent = _open_parent_dirfd(source_root, relative, expected_identity=expected_identity)
    try:
        return os.stat(relative.name, dir_fd=parent, follow_symlinks=False)
    finally:
        os.close(parent)


def _read_regular_bytes(
    source_root: Path,
    relative: Path,
    *,
    label: str,
    expected_identity: DirectoryIdentity | None = None,
    stable_root_fd: int | None = None,
) -> tuple[bytes, os.stat_result]:
    """Read one stable regular file without following a swapped final symlink/FIFO."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    descriptor: int | None = None
    parent: int | None = None
    verification_parent: int | None = None
    verification: int | None = None
    try:
        try:
            parent, parent_identity = _open_parent_dirfd_with_identity(
                source_root,
                relative,
                expected_identity=expected_identity,
                stable_root_fd=stable_root_fd,
            )
            descriptor = os.open(
                relative.name,
                flags | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent,
            )
        except OSError as exc:
            raise Stage2IntakeError(
                f"{label} cannot be opened safely: {relative.as_posix()}"
            ) from exc

        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise Stage2IntakeError(
                    f"{label} must be a regular file: {relative.as_posix()}"
                )
            chunks: list[bytes] = []
            while chunk := os.read(descriptor, 1024 * 1024):
                chunks.append(chunk)
            after = os.fstat(descriptor)
        except OSError as exc:
            raise Stage2IntakeError(f"{label} cannot be read safely: {relative.as_posix()}") from exc
        try:
            verification_parent, current_parent = _open_parent_dirfd_with_identity(
                source_root,
                relative,
                expected_identity=expected_identity,
                stable_root_fd=stable_root_fd,
            )
            if (parent_identity.st_dev, parent_identity.st_ino) != (
                current_parent.st_dev,
                current_parent.st_ino,
            ):
                raise Stage2IntakeError(
                    f"{label} parent changed during read: {relative.as_posix()}"
                )
            verification = os.open(
                relative.name,
                flags | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=verification_parent,
            )
            try:
                current = os.fstat(verification)
            finally:
                _close_optional_fd(verification)
                verification = None
        except (OSError, Stage2IntakeError) as exc:
            raise Stage2IntakeError(f"{label} changed during read: {relative.as_posix()}") from exc

        stable = (
            stat.S_ISREG(after.st_mode)
            and stat.S_ISREG(current.st_mode)
            and (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
            and (after.st_dev, after.st_ino) == (current.st_dev, current.st_ino)
            and before.st_size == after.st_size == sum(map(len, chunks))
            and before.st_mtime_ns == after.st_mtime_ns
            and before.st_ctime_ns == after.st_ctime_ns
        )
        if not stable:
            raise Stage2IntakeError(f"{label} changed during read: {relative.as_posix()}")
        return b"".join(chunks), after
    finally:
        _close_optional_fd(descriptor)
        _close_optional_fd(parent)
        _close_optional_fd(verification_parent)


def _read_symlink_bytes(
    source_root: Path,
    relative: Path,
    *,
    label: str,
    expected_identity: DirectoryIdentity | None = None,
) -> tuple[bytes, os.stat_result]:
    try:
        parent = _open_parent_dirfd(source_root, relative, expected_identity=expected_identity)
        try:
            before = os.stat(relative.name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISLNK(before.st_mode):
                raise Stage2IntakeError(f"{label} must be a symbolic link: {relative.as_posix()}")
            payload = os.readlink(relative.name, dir_fd=parent).encode("utf-8")
            after = os.stat(relative.name, dir_fd=parent, follow_symlinks=False)
        finally:
            os.close(parent)
        current = _lstat_beneath(source_root, relative, expected_identity=expected_identity)
    except (OSError, Stage2IntakeError) as exc:
        if isinstance(exc, Stage2IntakeError):
            raise
        raise Stage2IntakeError(f"{label} changed during read: {relative.as_posix()}") from exc
    if (
        not stat.S_ISLNK(after.st_mode)
        or _stable_file_identity(before) != _stable_file_identity(after)
        or _stable_file_identity(after) != _stable_file_identity(current)
    ):
        raise Stage2IntakeError(f"{label} changed during read: {relative.as_posix()}")
    return payload, after


def _stable_file_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _source_bytes(
    source_root: Path,
    relative: Path,
    mode: int,
    *,
    expected_identity: DirectoryIdentity | None = None,
) -> tuple[bytes, str]:
    try:
        metadata = _lstat_beneath(source_root, relative, expected_identity=expected_identity)
    except OSError as exc:
        raise Stage2IntakeError(f"source path missing: {relative.as_posix()}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        if not stat.S_ISLNK(mode):
            raise Stage2IntakeError(f"source symlink does not match lstat mode: {relative.as_posix()}")
        payload, stable_metadata = _read_symlink_bytes(
            source_root,
            relative,
            label="source path",
            expected_identity=expected_identity,
        )
        if _stable_file_identity(stable_metadata) != _stable_file_identity(metadata):
            raise Stage2IntakeError(f"source symlink changed during read: {relative.as_posix()}")
    elif stat.S_ISREG(metadata.st_mode):
        if not stat.S_ISREG(mode):
            raise Stage2IntakeError(f"source file does not match lstat mode: {relative.as_posix()}")
        payload, stable_metadata = _read_regular_bytes(
            source_root,
            relative,
            label="source path",
            expected_identity=expected_identity,
        )
        if _stable_file_identity(stable_metadata) != _stable_file_identity(metadata):
            raise Stage2IntakeError(f"source path changed during read: {relative.as_posix()}")
        if bool(stable_metadata.st_mode & 0o111) != bool(mode & 0o111):
            raise Stage2IntakeError(f"source mode changed during read: {relative.as_posix()}")
    else:
        kind = "FIFO" if stat.S_ISFIFO(metadata.st_mode) else "device/socket/directory"
        raise Stage2IntakeError(f"unsupported source file type ({kind}): {relative.as_posix()}")
    return payload, f"{mode:o}"


def _base_tree_entry(
    repo_root: Path,
    base_oid: str,
    relative: Path,
    *,
    base_index: BaseTreeIndex | None = None,
) -> tuple[str, str]:
    try:
        index = base_index or BaseTreeIndex.from_repo(repo_root, base_oid, runner=git_output)
        if index.base_oid != base_oid:
            raise GitBatchError("base tree index oid does not match requested base")
        entry = index.lookup(relative)
    except GitBatchError as exc:
        raise Stage2IntakeError(str(exc)) from exc
    if entry is None:
        return "000000", ""
    return entry.mode, entry.oid


def _entry(
    source_root: Path,
    relative: Path,
    base_oid: str,
    *,
    operation: str = "UPSERT",
    expected_identity: DirectoryIdentity | None = None,
    base_index: BaseTreeIndex | None = None,
) -> dict[str, str]:
    safe = safe_relative(relative)
    metadata = _lstat_beneath(source_root, safe, expected_identity=expected_identity)
    if stat.S_ISLNK(metadata.st_mode):
        source_mode = stat.S_IFLNK
    elif stat.S_ISREG(metadata.st_mode):
        source_mode = stat.S_IFREG | (0o755 if metadata.st_mode & 0o111 else 0o644)
    else:
        raise Stage2IntakeError(f"unsupported source file type: {safe.as_posix()}")
    payload, mode = _source_bytes(
        source_root,
        safe,
        source_mode,
        expected_identity=expected_identity,
    )
    if mode == "120000":
        target = Path(payload.decode("utf-8", errors="strict"))
        if target.is_absolute():
            raise Stage2IntakeError(f"absolute symlink is forbidden: {safe.as_posix()}")
        resolved = (source_root / safe).resolve(strict=False)
        try:
            resolved.relative_to(source_root.resolve(strict=True))
        except ValueError as exc:
            raise Stage2IntakeError(f"symlink escapes checkout: {safe.as_posix()}") from exc
    try:
        blob = git_blob_oid(payload, object_format=(base_index.object_format if base_index else "sha1"))
    except GitBatchError as exc:
        raise Stage2IntakeError(str(exc)) from exc
    base_mode, base_blob = _base_tree_entry(
        source_root, base_oid, safe, base_index=base_index
    )
    if GIT_OID.fullmatch(blob) is None:
        raise Stage2IntakeError(f"invalid git blob oid: {blob}")
    return {
        "path": safe.as_posix(),
        "operation": operation,
        "mode": mode,
        "sha256": sha256_bytes(payload),
        "blob": blob,
        "base_mode": base_mode,
        "base_blob": base_blob,
    }


def _delete_entry(
    source_root: Path,
    relative: Path,
    base_oid: str,
    *,
    expected_identity: DirectoryIdentity | None = None,
    base_index: BaseTreeIndex | None = None,
) -> dict[str, str]:
    safe = safe_relative(relative)
    try:
        _lstat_beneath(source_root, safe, expected_identity=expected_identity)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise Stage2IntakeError(
            f"delete source cannot be checked safely: {safe.as_posix()}"
        ) from exc
    else:
        raise Stage2IntakeError(f"delete source still exists: {safe.as_posix()}")
    base_mode, base_blob = _base_tree_entry(
        source_root, base_oid, safe, base_index=base_index
    )
    if base_mode == "000000":
        raise Stage2IntakeError(f"delete path is absent from base: {safe.as_posix()}")
    return {
        "path": safe.as_posix(),
        "operation": "DELETE",
        "mode": "000000",
        "sha256": "",
        "blob": "",
        "base_mode": base_mode,
        "base_blob": base_blob,
    }


def _source_identity(source_root: Path, remote_name: str, base_ref: str) -> dict[str, Any]:
    if remote_name != DEFAULT_REMOTE_NAME:
        raise Stage2IntakeError(
            f"remote_name must be exactly {DEFAULT_REMOTE_NAME}: {remote_name}"
        )
    if base_ref != DEFAULT_BASE_REF:
        raise Stage2IntakeError(f"base_ref must be exactly {DEFAULT_BASE_REF}: {base_ref}")
    root = source_root.resolve(strict=True)
    top_level = Path(git_text(root, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if top_level != root:
        raise Stage2IntakeError(f"source_root must be the git checkout top-level: {root}")
    source_root = root
    common_dir = Path(git_text(source_root, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = source_root / common_dir
    try:
        common_dir = common_dir.resolve(strict=True)
        os.lstat(common_dir / "info/grafts")
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise Stage2IntakeError("source git common-dir or info/grafts is unreadable") from exc
    else:
        raise Stage2IntakeError("source git common-dir info/grafts is forbidden")
    root_identity = directory_identity(source_root)
    head = git_text(source_root, "rev-parse", "HEAD")
    if GIT_OID.fullmatch(head) is None:
        raise Stage2IntakeError("source HEAD is not a valid git oid")
    object_format = git_text(source_root, "rev-parse", "--show-object-format")
    if object_format != "sha1":
        raise Stage2IntakeError(f"unsupported Git object format: {object_format}")
    remote = git_text(source_root, "remote", "get-url", remote_name)
    base_oid = git_text(source_root, "rev-parse", "--verify", base_ref)
    if GIT_OID.fullmatch(base_oid) is None:
        raise Stage2IntakeError(f"base ref does not resolve locally: {base_ref}")
    porcelain = _porcelain(source_root)
    return {
        "checkout": str(source_root.resolve()),
        "dev": root_identity[0],
        "ino": root_identity[1],
        "head": head,
        "remote_name": remote_name,
        "remote": remote,
        "base_ref": base_ref,
        "base_oid": base_oid,
        "source_clean": porcelain == b"",
        "porcelain_sha256": sha256_bytes(porcelain),
        "selection_boundary": "manifest_entries_only",
    }


def _validate_stage0_and_stage1(
    source_root: Path,
    stage0_paths: Sequence[Path],
    stage1_record: Path,
    stage1_receipts: Sequence[Path],
    *,
    expected_identity: DirectoryIdentity | None = None,
) -> tuple[tuple[Path, ...], dict[str, Any], set[Path]]:
    """Close the Stage 0/1 input boundary before hashing selected bytes."""
    normalized_stage0 = tuple(safe_relative(path) for path in stage0_paths)
    expected = set(STAGE0_CANDIDATE_PATHS)
    if len(normalized_stage0) != len(expected) or set(normalized_stage0) != expected:
        raise Stage2IntakeError(
            "Stage0 refs must be exactly C2-C9/I1 candidates/<family>/candidate.v2.json"
        )

    if expected_identity is None:
        raise Stage2IntakeError("stable source identity is required for Stage0/Stage1 validation")
    with _stable_upstream_validators(source_root, expected_identity):
        for family, relative in zip(STAGE0_FAMILIES, STAGE0_CANDIDATE_PATHS, strict=True):
            if relative not in normalized_stage0:
                raise Stage2IntakeError(f"missing Stage0 family candidate: {family}")
            try:
                result = stage_family_fragment_rebind.check_candidate(
                    relative,
                    repo_root=source_root,
                    history_only=False,
                )
            except Exception as exc:
                raise Stage2IntakeError(
                    f"Stage0 {family} candidate validation failed: {exc}"
                ) from exc
            if not isinstance(result, dict) or result.get("family") != family:
                raise Stage2IntakeError(f"Stage0 candidate family mismatch: expected {family}")
            if result.get("status") != stage_family_fragment_rebind.LIVE_STATUS:
                raise Stage2IntakeError(f"Stage0 candidate status mismatch: {family}")

        stage1_relative = safe_relative(stage1_record)
        try:
            payload, _metadata = _read_regular_bytes(
                source_root,
                stage1_relative,
                label="Stage1 record",
                expected_identity=expected_identity,
            )
            record = json.loads(payload.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise Stage2IntakeError(f"cannot read Stage1 record: {exc}") from exc
        if not isinstance(record, dict):
            raise Stage2IntakeError("Stage1 record JSON root must be an object")
        try:
            generate_stage1_production_contract_record.validate_stage1_record(source_root, record)
        except Exception as exc:
            raise Stage2IntakeError(f"Stage1 record validation failed: {exc}") from exc
        if (
            record.get("status") != "PRODUCTION_CONTRACT_IMPLEMENTED_NOT_AUTHORITY"
            or record.get("authoritative") is not False
        ):
            raise Stage2IntakeError("Stage1 record status or authority ceiling drift")

        commands = record.get("commands")
        if not isinstance(commands, dict):
            raise Stage2IntakeError("Stage1 record commands must be an object")
        record_receipts: set[Path] = set()
        for command_id, command in commands.items():
            if not isinstance(command, dict) or not isinstance(command.get("receipt"), dict):
                raise Stage2IntakeError(f"Stage1 command receipt missing: {command_id}")
            receipt_path = command["receipt"].get("path")
            if not isinstance(receipt_path, str):
                raise Stage2IntakeError(f"Stage1 command receipt path missing: {command_id}")
            record_receipts.add(safe_relative(receipt_path, label=f"Stage1 receipt {command_id}"))
    if directory_identity(source_root) != expected_identity:
        raise Stage2IntakeError("source checkout identity changed")

    normalized_receipts = tuple(safe_relative(path) for path in stage1_receipts)
    if len(normalized_receipts) != len(set(normalized_receipts)):
        raise Stage2IntakeError("Stage1 receipt paths contain duplicates")
    if set(normalized_receipts) != record_receipts:
        raise Stage2IntakeError("Stage1 receipts do not match record.commands receipt paths")
    return STAGE0_CANDIDATE_PATHS, record, record_receipts


def _run_repo_local_checker(
    source_root: Path,
    checker: Path,
    arguments: Sequence[str],
    *,
    label: str,
    expected_identity: DirectoryIdentity,
) -> None:
    if directory_identity(source_root) != expected_identity:
        raise Stage2IntakeError("source checkout identity changed")
    completed = subprocess.run(
        (sys.executable, str(source_root / checker), *arguments),
        cwd=source_root,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "GIT_OPTIONAL_LOCKS": "0",
        },
    )
    if directory_identity(source_root) != expected_identity:
        raise Stage2IntakeError("source checkout identity changed")
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise Stage2IntakeError(f"{label} failed: {detail}")


def _load_json_object(
    source_root: Path,
    relative: Path,
    *,
    label: str,
    expected_identity: DirectoryIdentity,
) -> tuple[dict[str, Any], bytes]:
    try:
        payload, _metadata = _read_regular_bytes(
            source_root,
            relative,
            label=label,
            expected_identity=expected_identity,
        )
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Stage2IntakeError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise Stage2IntakeError(f"{label} JSON root must be an object")
    return value, payload


def _validate_all_lines_aggregate(
    source_root: Path,
    aggregate_path: Path,
    *,
    expected_identity: DirectoryIdentity,
) -> dict[str, Any]:
    aggregate_path = safe_relative(aggregate_path, label="all-lines aggregate")
    if aggregate_path != ALL_LINES_AGGREGATE:
        raise Stage2IntakeError("v4 all-lines aggregate path drift")
    document, _raw = _load_json_object(
        source_root,
        aggregate_path,
        label="all-lines aggregate",
        expected_identity=expected_identity,
    )
    if (
        document.get("schema") != ALL_LINES_AGGREGATE_SCHEMA
        or document.get("status") != ALL_LINES_AGGREGATE_STATUS
        or document.get("authoritative") is not False
        or not isinstance(document.get("content_digest"), str)
        or SHA256.fullmatch(document["content_digest"]) is None
    ):
        raise Stage2IntakeError("v4 all-lines aggregate identity drift")
    producer_path = source_root / ALL_LINES_AGGREGATE_PRODUCER
    if not producer_path.is_file():
        raise Stage2IntakeError("all-lines aggregate producer is unavailable")
    spec = importlib.util.spec_from_file_location(
        "_mrw_stage2_all_lines_aggregate_producer",
        producer_path,
    )
    if spec is None or spec.loader is None:
        raise Stage2IntakeError("all-lines aggregate producer cannot be loaded")
    producer = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(producer)
        check_document = producer.check_document
        summary = check_document(
            source_root,
            aggregate_path,
            stage_root=FRESH_STAGE0_ROOT,
        )
    except Exception as exc:
        raise Stage2IntakeError(f"all-lines aggregate validation failed: {exc}") from exc
    if (
        not isinstance(summary, dict)
        or summary.get("schema") != ALL_LINES_AGGREGATE_SCHEMA
        or summary.get("status") != ALL_LINES_AGGREGATE_STATUS
        or summary.get("content_digest") != document["content_digest"]
    ):
        raise Stage2IntakeError("all-lines aggregate validation summary drift")
    if directory_identity(source_root) != expected_identity:
        raise Stage2IntakeError("source checkout identity changed")
    return document


def _validate_historical_stage1_record(
    source_root: Path,
    record: dict[str, Any],
) -> set[Path]:
    """Validate frozen Stage 1 structure/receipts without projecting old source bytes live."""
    validator = generate_stage1_production_contract_record
    expected_fields = {
        "schema",
        "schema_version",
        "record_id",
        "stage",
        "status",
        "authoritative",
        "derived_as",
        "candidate_commit",
        "candidate_tree",
        "candidate",
        "authority",
        "observed_at",
        "bindings",
        "commands",
        "known_gaps",
    }
    if set(record) != expected_fields:
        raise Stage2IntakeError("historical Stage1 record field set drift")
    if (
        record.get("schema") != validator.SCHEMA
        or record.get("schema_version") != validator.SCHEMA_VERSION
        or record.get("record_id") != validator.RECORD_ID
        or record.get("stage") != "STAGE_1"
        or record.get("status") != validator.STATUS
        or record.get("authoritative") is not False
        or record.get("derived_as") != "evidence"
        or record.get("candidate_commit") is not None
        or record.get("candidate_tree") is not None
        or record.get("candidate") != {"commit": None, "tree": None}
    ):
        raise Stage2IntakeError("historical Stage1 identity or authority ceiling drift")
    authority = record.get("authority")
    if not isinstance(authority, dict) or set(authority) != set(validator.AUTHORITY_KEYS):
        raise Stage2IntakeError("historical Stage1 authority key set drift")
    if any(authority.get(key) is not False for key in validator.AUTHORITY_KEYS):
        raise Stage2IntakeError("historical Stage1 authority expanded")
    bindings = record.get("bindings")
    if not isinstance(bindings, dict) or set(bindings) != {
        "stage_plan",
        "stage_plan_freeze",
        "stage0_completion",
        "required_files",
    }:
        raise Stage2IntakeError("historical Stage1 binding field set drift")
    plan, freeze = validator._validate_frozen_plan(source_root)
    stage0 = validator._validate_stage0_completion(source_root)
    if bindings["stage_plan"] != plan or bindings["stage_plan_freeze"] != freeze:
        raise Stage2IntakeError("historical Stage1 frozen plan binding drift")
    if bindings["stage0_completion"] != stage0:
        raise Stage2IntakeError("historical Stage1 Stage0 binding drift")
    evidence = {
        "observed_at": record.get("observed_at"),
        "commands": record.get("commands"),
        "known_gaps": record.get("known_gaps"),
    }
    try:
        commands = validator._require_commands(source_root, evidence)
        gaps = validator._require_known_gaps(evidence)
    except Exception as exc:
        raise Stage2IntakeError(f"historical Stage1 receipt validation failed: {exc}") from exc
    if commands != record["commands"] or gaps != record["known_gaps"]:
        raise Stage2IntakeError("historical Stage1 command or gap projection drift")
    return {
        safe_relative(row["receipt"]["path"], label=f"Stage1 receipt {command_id}")
        for command_id, row in commands.items()
    }


def _validate_stage1_production_binding_successor(
    source_root: Path,
    successor_path: Path,
    *,
    expected_identity: DirectoryIdentity,
) -> dict[str, Any]:
    """Validate the additive current-byte Stage1 witness against one source root."""
    relative = safe_relative(
        successor_path,
        label="Stage1 production binding successor",
    )
    if relative != STAGE1_PRODUCTION_BINDING_SUCCESSOR:
        raise Stage2IntakeError("v5 Stage1 production binding successor path drift")
    record, _raw = _load_json_object(
        source_root,
        relative,
        label="Stage1 production binding successor",
        expected_identity=expected_identity,
    )
    try:
        with _stable_upstream_validators(source_root, expected_identity):
            generate_stage1_current_binding_successor.validate_bundle(
                source_root,
                record,
            )
    except Exception as exc:
        raise Stage2IntakeError(
            f"Stage1 production binding successor validation failed: {exc}"
        ) from exc
    if directory_identity(source_root) != expected_identity:
        raise Stage2IntakeError("source checkout identity changed")
    return record


def _validate_stage1_successor_candidate_projection(
    manifest: dict[str, Any],
    source_root: Path,
    successor: dict[str, Any],
    *,
    expected_identity: DirectoryIdentity,
    base_index: BaseTreeIndex,
) -> dict[str, int]:
    """Require every successor binding to equal the manifest's base+delta candidate."""
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise Stage2IntakeError("manifest entries are unavailable for Stage1 projection")
    by_path = {
        row.get("path"): row
        for row in entries
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    current_bindings = successor.get("current_bindings")
    if not isinstance(current_bindings, list):
        raise Stage2IntakeError("Stage1 successor current binding projection is invalid")
    mismatches: list[str] = []
    seen: set[Path] = set()
    for binding in current_bindings:
        if not isinstance(binding, dict) or set(binding) != {
            "path",
            "successor_sha256",
            "predecessor_sha256",
            "historical_pointer",
            "role",
            "relation",
        }:
            raise Stage2IntakeError("Stage1 successor current binding shape drift")
        relative = safe_relative(
            binding.get("path"),
            label="Stage1 successor current binding",
        )
        digest = binding.get("successor_sha256")
        if (
            relative in seen
            or not isinstance(digest, str)
            or SHA256.fullmatch(digest) is None
            or not isinstance(binding.get("role"), str)
            or not binding["role"]
            or binding.get("relation")
            not in {"IDENTITY", "CURRENT_BYTE_SUCCESSOR", "ADDITIVE_CURRENT_REQUIREMENT"}
        ):
            raise Stage2IntakeError("Stage1 successor current binding identity drift")
        seen.add(relative)
        live = _entry(
            source_root,
            relative,
            manifest["source"]["base_oid"],
            expected_identity=expected_identity,
            base_index=base_index,
        )
        delta = by_path.get(relative.as_posix())
        if delta is not None:
            matches_candidate = (
                delta.get("operation") == "UPSERT"
                and delta.get("sha256") == digest
                and delta.get("mode") == live["mode"]
                and delta.get("blob") == live["blob"]
            )
        else:
            matches_candidate = (
                live["sha256"] == digest
                and live["mode"] == live["base_mode"]
                and live["blob"] == live["base_blob"]
            )
        if not matches_candidate:
            mismatches.append(relative.as_posix())
    summary = successor.get("current_required_files_summary")
    if (
        not isinstance(summary, dict)
        or summary.get("current_binding_count") != len(seen)
        or summary.get("mismatch_count_at_generation") != 0
    ):
        raise Stage2IntakeError("Stage1 successor required-file summary drift")
    if mismatches:
        raise Stage2IntakeError(
            "Stage1 successor does not match projected candidate base+delta: "
            f"mismatch_count={len(mismatches)}, paths={sorted(mismatches)}"
        )
    return {
        "current_mismatch_count": 0,
        "projected_candidate_mismatch_count": 0,
    }


def _workflow_selector_delta(
    source_root: Path,
    base_index: BaseTreeIndex,
    *,
    helper_name: str = "compute_workflow_selector_delta",
) -> WorkflowSelectorDelta:
    """Read and normalize the closure-owned workflow-equivalent selection."""
    label = "workflow-equivalent" if helper_name == "compute_workflow_selector_delta" else "frontend"
    compute_delta = getattr(
        source_closure_module,
        helper_name,
        None,
    )
    if not callable(compute_delta):
        raise Stage2IntakeError(
            f"{label} source closure implementation is unavailable"
        )
    try:
        delta = compute_delta(source_root, base_index=base_index)
    except (OSError, TypeError, ValueError) as exc:
        raise Stage2IntakeError(
            f"{label} selector delta failed: {exc}"
        ) from exc
    if not isinstance(delta, (list, tuple)):
        raise Stage2IntakeError(
            f"{label} selector delta must be ordered"
        )

    normalized: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for row in delta:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise Stage2IntakeError(
                f"{label} selector delta row drift"
            )
        operation, raw_path = row
        if operation not in {"UPSERT", "DELETE"} or not isinstance(raw_path, str):
            raise Stage2IntakeError(
                f"{label} selector delta identity drift"
            )
        path = safe_relative(raw_path, label=f"{label} selector path")
        if path in seen:
            raise Stage2IntakeError(
                f"{label} selector delta path is duplicated: "
                f"{path.as_posix()}"
            )
        normalized.append((operation, path))
        seen.add(path)
    return tuple(normalized)


def _merge_workflow_selector_selection(
    additional_upserts: Sequence[Path],
    delete_paths: Sequence[Path],
    delta: WorkflowSelectorDelta,
    *,
    satisfied_upserts: Sequence[Path] = (),
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """Merge delta without duplicating an explicitly selected path or operation."""
    explicit_upserts = tuple(dict.fromkeys(additional_upserts))
    explicit_deletes = tuple(dict.fromkeys(delete_paths))
    selected_upserts = set(explicit_upserts)
    selected_deletes = set(explicit_deletes)
    already_satisfied = set(satisfied_upserts)
    conflicting_satisfied = already_satisfied & selected_deletes
    if conflicting_satisfied:
        path = min(conflicting_satisfied, key=lambda item: item.as_posix())
        raise Stage2IntakeError(
            "workflow-equivalent satisfied upsert conflicts with explicit delete: "
            f"{path.as_posix()}"
        )
    merged_upserts = list(explicit_upserts)
    merged_deletes = list(explicit_deletes)
    for operation, path in delta:
        if path in already_satisfied:
            if operation != "UPSERT":
                raise Stage2IntakeError(
                    "workflow-equivalent delta conflicts with satisfied upsert: "
                    f"{path.as_posix()}"
                )
            continue
        selected_operation: str | None = None
        if path in selected_upserts:
            selected_operation = "UPSERT"
        if path in selected_deletes:
            if selected_operation is not None:
                raise Stage2IntakeError(
                    "explicit intake selections conflict: "
                    f"{path.as_posix()}"
                )
            selected_operation = "DELETE"
        if selected_operation is None:
            if operation == "UPSERT":
                selected_upserts.add(path)
                merged_upserts.append(path)
            else:
                selected_deletes.add(path)
                merged_deletes.append(path)
        elif selected_operation != operation:
            raise Stage2IntakeError(
                "workflow-equivalent delta conflicts with explicit intake "
                f"selection: {path.as_posix()}"
            )
    return tuple(merged_upserts), tuple(merged_deletes)


def _registry_resolution_rows(
    source_root: Path,
    stage0_paths: Sequence[Path],
    registry: dict[str, Any],
    *,
    expected_identity: DirectoryIdentity,
) -> list[dict[str, str]]:
    successors = registry.get("successors")
    if not isinstance(successors, list):
        raise Stage2IntakeError("current-byte successor registry rows are missing")
    by_id = {
        row.get("successor_id"): row
        for row in successors
        if isinstance(row, dict) and isinstance(row.get("successor_id"), str)
    }
    if len(by_id) != len(successors):
        raise Stage2IntakeError("current-byte successor ids are invalid or duplicated")
    resolutions: list[dict[str, str]] = []
    for family, candidate_path in zip(STAGE0_FAMILIES, stage0_paths, strict=True):
        try:
            result = stage_family_fragment_rebind.check_candidate(
                candidate_path,
                repo_root=source_root,
                history_only=True,
            )
        except Exception as exc:
            raise Stage2IntakeError(
                f"Stage0 {family} frozen candidate validation failed: {exc}"
            ) from exc
        if result.get("family") != family or result.get("status") != stage_family_fragment_rebind.HISTORY_STATUS:
            raise Stage2IntakeError(f"Stage0 frozen candidate identity mismatch: {family}")
        candidate, candidate_raw = _load_json_object(
            source_root,
            candidate_path,
            label=f"Stage0 {family} candidate",
            expected_identity=expected_identity,
        )
        for group in ("fragments", "sources", "tests"):
            references = candidate.get(group)
            if not isinstance(references, list):
                raise Stage2IntakeError(f"Stage0 {family} candidate {group} binding drift")
            for reference in references:
                if not isinstance(reference, dict):
                    raise Stage2IntakeError(f"Stage0 {family} candidate reference drift")
                path = safe_relative(reference.get("path"), label="Stage0 candidate reference")
                predecessor = reference.get("file_sha256")
                if not isinstance(predecessor, str) or SHA256.fullmatch(predecessor) is None:
                    raise Stage2IntakeError(f"Stage0 {family} candidate source digest drift")
                live, _metadata = _read_regular_bytes(
                    source_root,
                    path,
                    label=f"Stage0 {family} live reference",
                    expected_identity=expected_identity,
                )
                successor = sha256_bytes(live)
                if successor == predecessor:
                    continue
                matches = [
                    row
                    for row in successors
                    if isinstance(row, dict)
                    and row.get("source_path") == path.as_posix()
                    and row.get("predecessor_sha256") == predecessor
                    and row.get("successor_sha256") == successor
                ]
                exact = []
                candidate_sha = sha256_bytes(candidate_raw)
                for row in matches:
                    declarations = row.get("predecessor_declarations")
                    if not isinstance(declarations, list):
                        continue
                    direct = any(
                        isinstance(item, dict)
                        and item.get("artifact") == candidate_path.as_posix()
                        and item.get("artifact_sha256") == candidate_sha
                        and item.get("bound_sha256") == predecessor
                        for item in declarations
                    )
                    alias_id = SHARED_STAGE0_SUCCESSOR_ALIASES.get((family, path.as_posix()))
                    if direct or row.get("successor_id") == alias_id:
                        exact.append(row)
                if len(exact) != 1:
                    raise Stage2IntakeError(
                        "current-byte registry does not contain exactly one candidate-specific "
                        f"successor for {family}:{path.as_posix()}"
                    )
                row = exact[0]
                resolutions.append(
                    {
                        "candidate_path": candidate_path.as_posix(),
                        "candidate_sha256": candidate_sha,
                        "family": family,
                        "group": group,
                        "source_path": path.as_posix(),
                        "predecessor_sha256": predecessor,
                        "successor_sha256": successor,
                        "registry_successor_id": row["successor_id"],
                        "registry_family": row.get("family") or "NONE",
                    }
                )
    resolutions.sort(key=lambda row: (row["family"], row["group"], row["source_path"]))
    return resolutions


def _validate_stage0_and_stage1_v3(
    source_root: Path,
    stage0_paths: Sequence[Path],
    stage1_record: Path,
    stage1_receipts: Sequence[Path],
    current_byte_successor_registry: Path,
    stage1_remediation_record: Path,
    *,
    expected_identity: DirectoryIdentity,
) -> tuple[tuple[Path, ...], dict[str, Any], set[Path], list[dict[str, str]]]:
    normalized_stage0 = tuple(safe_relative(path) for path in stage0_paths)
    if len(normalized_stage0) != len(STAGE0_CANDIDATE_PATHS) or set(normalized_stage0) != set(STAGE0_CANDIDATE_PATHS):
        raise Stage2IntakeError("Stage0 refs must be exactly C2-C9/I1 B23 candidates")
    registry_path = safe_relative(current_byte_successor_registry)
    remediation_path = safe_relative(stage1_remediation_record)
    if remediation_path == WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_RECORD:
        remediation_checker = WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_CHECKER
        remediation_schema = "mrw.stage1.stage2_v6_intake_remediation_record.v5"
        registry_expected = DEFAULT_CURRENT_BYTE_SUCCESSOR_REGISTRY
        registry_checker = DEFAULT_CURRENT_BYTE_SUCCESSOR_CHECKER
        registry_schema = "mrw.current_byte_binding_successors.v1"
    elif remediation_path in STAGE3_V6_ARTIFACT_REMEDIATION_RECORDS:
        remediation_checker = STAGE3_V6_ARTIFACT_REMEDIATION_CHECKER
        remediation_checker_args = (
            "--check-receipt",
            "--record",
            remediation_path.as_posix(),
        )
        remediation_schema = "mrw.stage1.stage3_v6_artifact_remediation_record.v1"
        registry_expected = STAGE3_CURRENT_BYTE_SUCCESSOR_REGISTRY
        registry_checker = STAGE3_CURRENT_BYTE_SUCCESSOR_CHECKER
        registry_schema = "mrw.current_byte_binding_successors.v2"
        if (
            remediation_path == STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD
            and registry_path == CONVERGENCE_CURRENT_BYTE_SUCCESSOR_REGISTRY
        ):
            registry_expected = CONVERGENCE_CURRENT_BYTE_SUCCESSOR_REGISTRY
            registry_checker = CONVERGENCE_CURRENT_BYTE_SUCCESSOR_CHECKER
            registry_schema = "mrw.current_byte_binding_successors.v3"
    elif remediation_path == DEFAULT_STAGE1_REMEDIATION_RECORD:
        remediation_checker = DEFAULT_STAGE1_REMEDIATION_CHECKER
        remediation_schema = "mrw.stage1.stage2_v5_intake_remediation_record.v2"
        registry_expected = DEFAULT_CURRENT_BYTE_SUCCESSOR_REGISTRY
        registry_checker = DEFAULT_CURRENT_BYTE_SUCCESSOR_CHECKER
        registry_schema = "mrw.current_byte_binding_successors.v1"
    else:
        raise Stage2IntakeError("v3 Stage1 remediation record path drift")
    if remediation_path not in STAGE3_V6_ARTIFACT_REMEDIATION_RECORDS:
        remediation_checker_args = ("--check-receipt",)
    if registry_path != registry_expected:
        raise Stage2IntakeError("v3 current-byte successor registry path drift")
    _run_repo_local_checker(
        source_root,
        registry_checker,
        ("--repo-root", str(source_root)),
        label="current-byte successor checker",
        expected_identity=expected_identity,
    )
    registry, _registry_raw = _load_json_object(
        source_root,
        registry_path,
        label="current-byte successor registry",
        expected_identity=expected_identity,
    )
    if (
        registry.get("schema") != registry_schema
        or registry.get("status") != "CURRENT_BYTES_BOUND_BY_ADDITIVE_SUCCESSORS_NOT_AUTHORITY"
        or registry.get("authoritative") is not False
    ):
        raise Stage2IntakeError("current-byte successor registry identity drift")
    resolutions = _registry_resolution_rows(
        source_root,
        normalized_stage0,
        registry,
        expected_identity=expected_identity,
    )
    stage1_relative = safe_relative(stage1_record)
    record, _record_raw = _load_json_object(
        source_root,
        stage1_relative,
        label="historical Stage1 record",
        expected_identity=expected_identity,
    )
    record_receipts = _validate_historical_stage1_record(source_root, record)
    normalized_receipts = tuple(safe_relative(path) for path in stage1_receipts)
    if len(normalized_receipts) != len(set(normalized_receipts)) or set(normalized_receipts) != record_receipts:
        raise Stage2IntakeError("Stage1 receipts do not match historical record.commands")
    _run_repo_local_checker(
        source_root,
        remediation_checker,
        remediation_checker_args,
        label="Stage1 source/static remediation checker",
        expected_identity=expected_identity,
    )
    remediation, _remediation_raw = _load_json_object(
        source_root,
        remediation_path,
        label="Stage1 remediation record",
        expected_identity=expected_identity,
    )
    if (
        remediation.get("schema_version") != remediation_schema
        or remediation.get("authoritative") is not False
    ):
        raise Stage2IntakeError("Stage1 remediation record identity drift")
    if directory_identity(source_root) != expected_identity:
        raise Stage2IntakeError("source checkout identity changed")
    return STAGE0_CANDIDATE_PATHS, record, record_receipts, resolutions


def _validate_stage0_and_stage1_v4(
    source_root: Path,
    stage0_paths: Sequence[Path],
    stage1_record: Path,
    stage1_receipts: Sequence[Path],
    current_byte_successor_registry: Path,
    stage1_remediation_record: Path,
    *,
    expected_identity: DirectoryIdentity,
) -> tuple[tuple[Path, ...], dict[str, Any], set[Path], list[dict[str, str]]]:
    """Validate fresh B23 bytes and the immutable correction1/correction2 history."""
    normalized_stage0 = tuple(safe_relative(path) for path in stage0_paths)
    expected_stage0 = FRESH_STAGE0_CANDIDATE_PATHS
    if len(normalized_stage0) != len(expected_stage0) or set(normalized_stage0) != set(
        expected_stage0
    ):
        raise Stage2IntakeError(
            "v4 Stage0 refs must be exactly C2-C9/I1 candidates below the fresh root"
        )
    registry_path = safe_relative(current_byte_successor_registry)
    remediation_path = safe_relative(stage1_remediation_record)
    if registry_path != FRESH_CURRENT_BYTE_SUCCESSOR_REGISTRY:
        raise Stage2IntakeError("v4 current-byte successor registry path drift")
    if remediation_path != STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD:
        raise Stage2IntakeError("v4 Stage1 remediation must be correction1")

    _run_repo_local_checker(
        source_root,
        FRESH_CURRENT_BYTE_SUCCESSOR_CHECKER,
        ("--repo-root", str(source_root)),
        label="fresh current-byte successor checker",
        expected_identity=expected_identity,
    )
    registry, _registry_raw = _load_json_object(
        source_root,
        registry_path,
        label="fresh current-byte successor registry",
        expected_identity=expected_identity,
    )
    if (
        registry.get("schema") != "mrw.current_byte_binding_successors.v4"
        or registry.get("status")
        != "CURRENT_BYTES_BOUND_BY_ZERO_DELTA_SUCCESSOR_NOT_AUTHORITY"
        or registry.get("authoritative") is not False
    ):
        raise Stage2IntakeError("fresh current-byte successor registry identity drift")

    with _stable_upstream_validators(source_root, expected_identity):
        for family, candidate_path in zip(
            STAGE0_FAMILIES, expected_stage0, strict=True
        ):
            try:
                result = stage_family_fragment_rebind.check_candidate(
                    candidate_path,
                    repo_root=source_root,
                    history_only=False,
                )
            except Exception as exc:
                raise Stage2IntakeError(
                    f"fresh Stage0 {family} candidate validation failed: {exc}"
                ) from exc
            if (
                not isinstance(result, dict)
                or result.get("family") != family
                or result.get("status") != stage_family_fragment_rebind.LIVE_STATUS
            ):
                raise Stage2IntakeError(
                    f"fresh Stage0 candidate identity mismatch: {family}"
                )
            candidate, _candidate_raw = _load_json_object(
                source_root,
                candidate_path,
                label=f"fresh Stage0 {family} candidate",
                expected_identity=expected_identity,
            )
            for group in ("fragments", "sources", "tests"):
                references = candidate.get(group)
                if not isinstance(references, list):
                    raise Stage2IntakeError(
                        f"fresh Stage0 {family} candidate {group} binding drift"
                    )
                for reference in references:
                    if not isinstance(reference, dict):
                        raise Stage2IntakeError(
                            f"fresh Stage0 {family} candidate reference drift"
                        )
                    referenced = safe_relative(
                        reference.get("path"),
                        label=f"fresh Stage0 {family} {group} reference",
                    )
                    bound_sha256 = reference.get("file_sha256")
                    if (
                        not isinstance(bound_sha256, str)
                        or SHA256.fullmatch(bound_sha256) is None
                    ):
                        raise Stage2IntakeError(
                            f"fresh Stage0 {family} candidate source digest drift"
                        )
                    live, _metadata = _read_regular_bytes(
                        source_root,
                        referenced,
                        label=f"fresh Stage0 {family} current-byte reference",
                        expected_identity=expected_identity,
                    )
                    if sha256_bytes(live) != bound_sha256:
                        raise Stage2IntakeError(
                            "fresh Stage0 candidate does not bind current bytes: "
                            f"{family}:{referenced.as_posix()}"
                        )

    stage1_relative = safe_relative(stage1_record)
    record, _record_raw = _load_json_object(
        source_root,
        stage1_relative,
        label="historical Stage1 record",
        expected_identity=expected_identity,
    )
    record_receipts = _validate_historical_stage1_record(source_root, record)
    normalized_receipts = tuple(safe_relative(path) for path in stage1_receipts)
    if (
        len(normalized_receipts) != len(set(normalized_receipts))
        or set(normalized_receipts) != record_receipts
    ):
        raise Stage2IntakeError("Stage1 receipts do not match historical record.commands")
    remediation, _remediation_raw = _load_json_object(
        source_root,
        remediation_path,
        label="Stage1 correction1 remediation record",
        expected_identity=expected_identity,
    )
    if (
        remediation.get("schema_version")
        != "mrw.stage1.stage3_v6_artifact_remediation_record.v1"
        or remediation.get("authoritative") is not False
    ):
        raise Stage2IntakeError("Stage1 correction1 remediation identity drift")
    correction2_documents: dict[Path, tuple[dict[str, Any], bytes]] = {}
    for relative, expected_sha256 in (
        STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_HASHES.items()
    ):
        document, raw = _load_json_object(
            source_root,
            relative,
            label="Stage1 correction2 historical package",
            expected_identity=expected_identity,
        )
        if sha256_bytes(raw) != expected_sha256:
            raise Stage2IntakeError("Stage1 correction2 historical package drift")
        correction2_documents[relative] = (document, raw)
    correction2_record = correction2_documents[
        STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_RECORD
    ][0]
    correction2_manifest = correction2_documents[
        STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_MANIFEST
    ][0]
    correction2_validation = correction2_documents[
        STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_VALIDATION
    ][0]
    if (
        correction2_record.get("schema_version")
        != "mrw.stage1.stage3_v6_artifact_remediation_correction2_record.v1"
        or correction2_record.get("status")
        != "PASS_COMPLETE_MEMBER_CLOSURE_NOT_AUTHORITY"
        or correction2_record.get("authoritative") is not False
        or correction2_record.get("production_release_authorized") is not False
        or correction2_manifest.get("schema_version")
        != "mrw.stage1.stage3_v6_artifact_remediation_correction2_manifest.v1"
        or correction2_manifest.get("status") != "COMPLETE_NOT_AUTHORITY"
        or correction2_manifest.get("authoritative") is not False
        or correction2_manifest.get("production_release_authorized") is not False
        or correction2_validation.get("schema_version")
        != "mrw.stage1.stage3_v6_artifact_remediation_correction2_validation.v1"
        or correction2_validation.get("status") != "PASS_NOT_AUTHORITY"
        or correction2_validation.get("authoritative") is not False
        or correction2_validation.get("production_release_authorized") is not False
    ):
        raise Stage2IntakeError("Stage1 correction2 historical identity drift")
    if correction2_validation.get("record") != {
        "path": STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_RECORD.as_posix(),
        "sha256": STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_HASHES[
            STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_RECORD
        ],
    } or correction2_validation.get("manifest") != {
        "path": STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_MANIFEST.as_posix(),
        "sha256": STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_HASHES[
            STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION2_MANIFEST
        ],
    }:
        raise Stage2IntakeError("Stage1 correction2 validation binding drift")
    correction1_binding = {
        row.get("path"): row.get("sha256")
        for row in correction2_record.get("predecessor_correction1", [])
        if isinstance(row, dict)
    }
    if correction1_binding.get(remediation_path.as_posix()) != sha256_bytes(
        _remediation_raw
    ):
        raise Stage2IntakeError("Stage1 correction2 predecessor binding drift")
    isolated = correction2_record.get("isolated_pytest_receipt")
    if not isinstance(isolated, dict):
        raise Stage2IntakeError("Stage1 correction2 isolated receipt binding drift")
    isolated_path = safe_relative(
        isolated.get("path"), label="Stage1 correction2 isolated receipt"
    )
    isolated_document, isolated_raw = _load_json_object(
        source_root,
        isolated_path,
        label="Stage1 correction2 isolated receipt",
        expected_identity=expected_identity,
    )
    if (
        isolated.get("expected_count") != 200
        or isolated.get("status") != "PASS_COMPLETE_EXACT_200"
        or isolated.get("sha256") != sha256_bytes(isolated_raw)
        or isolated_document.get("schema") != "mrw.current-pytest-receipt.v2"
        or isolated_document.get("status") != "PASS_COMPLETE_EXACT_200"
        or isolated_document.get("authoritative") is not False
    ):
        raise Stage2IntakeError("Stage1 correction2 isolated receipt binding drift")
    if directory_identity(source_root) != expected_identity:
        raise Stage2IntakeError("source checkout identity changed")
    # Fresh candidates already name the selected current bytes, so there are no
    # predecessor-to-successor substitutions to project into the manifest.
    return expected_stage0, record, record_receipts, []


def validate_stage0_and_stage1_bindings(
    manifest: dict[str, Any],
    source_root: Path,
    *,
    expected_identity: DirectoryIdentity | None = None,
    base_index: BaseTreeIndex | None = None,
) -> None:
    """Re-run upstream authority checks and exact live-byte binding checks."""
    stage0 = manifest.get("stage0_b23")
    stage1 = manifest.get("stage1")
    if not isinstance(stage0, dict) or not isinstance(stage0.get("refs"), list):
        raise Stage2IntakeError("manifest Stage0 reference binding is invalid")
    if not isinstance(stage1, dict) or not isinstance(stage1.get("record"), dict):
        raise Stage2IntakeError("manifest Stage1 record binding is invalid")
    if not isinstance(stage1.get("receipts"), list):
        raise Stage2IntakeError("manifest Stage1 receipt bindings are invalid")

    source = manifest.get("source")
    if not isinstance(source, dict):
        raise Stage2IntakeError("manifest source binding is invalid")
    base_oid = source.get("base_oid")
    if not isinstance(base_oid, str) or GIT_OID.fullmatch(base_oid) is None:
        raise Stage2IntakeError("manifest source base oid is invalid")
    if expected_identity is None:
        expected_identity = (
            int(source.get("dev", -1)),
            int(source.get("ino", -1)),
        )
    if directory_identity(source_root) != expected_identity:
        raise Stage2IntakeError("source checkout identity changed")
    if base_index is None:
        try:
            base_index = BaseTreeIndex.from_repo(source_root, base_oid, runner=git_output)
        except GitBatchError as exc:
            raise Stage2IntakeError(str(exc)) from exc

    refs = tuple(stage0["refs"])
    stage0_paths = tuple(
        safe_relative(row.get("path"), label="Stage0 reference binding")
        for row in refs
    )
    record_binding = stage1["record"]
    receipt_bindings = stage1["receipts"]
    stage1_record = safe_relative(record_binding.get("path"), label="Stage1 record binding")
    stage1_receipts = tuple(
        safe_relative(row.get("path"), label="Stage1 receipt binding")
        for row in receipt_bindings
    )

    schema_version = manifest.get("schema_version")
    direct_bindings: list[dict[str, Any]] = [*refs, record_binding, *receipt_bindings]
    if schema_version in {SCHEMA_VERSION_V3, SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}:
        registry_binding = stage0.get("current_byte_successor_registry")
        remediation_binding = stage1.get("remediation_record")
        if not isinstance(registry_binding, dict) or not isinstance(remediation_binding, dict):
            raise Stage2IntakeError("successor or remediation binding is invalid")
        registry_path = safe_relative(
            registry_binding.get("path"), label="current-byte successor registry binding"
        )
        remediation_path = safe_relative(
            remediation_binding.get("path"), label="Stage1 remediation record binding"
        )
        (
            actual_stage0_paths,
            _record,
            actual_receipts,
            actual_resolutions,
        ) = (
            _validate_stage0_and_stage1_v4(
                source_root,
                stage0_paths,
                stage1_record,
                stage1_receipts,
                registry_path,
                remediation_path,
                expected_identity=expected_identity,
            )
            if schema_version in {SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}
            else _validate_stage0_and_stage1_v3(
                source_root,
                stage0_paths,
                stage1_record,
                stage1_receipts,
                registry_path,
                remediation_path,
                expected_identity=expected_identity,
            )
        )
        if actual_resolutions != stage0.get("successor_resolutions"):
            raise Stage2IntakeError(
                f"{schema_version.rsplit('.', 1)[-1]} Stage0 successor resolution projection drift"
            )
        direct_bindings.extend((registry_binding, remediation_binding))
        if schema_version in {SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}:
            aggregate_binding = stage1.get("all_lines_aggregate")
            if not isinstance(aggregate_binding, dict):
                raise Stage2IntakeError("v4 all-lines aggregate binding is invalid")
            aggregate_path = safe_relative(
                aggregate_binding.get("path"), label="all-lines aggregate binding"
            )
            _validate_all_lines_aggregate(
                source_root,
                aggregate_path,
                expected_identity=expected_identity,
            )
            direct_bindings.append(aggregate_binding)
            if schema_version == SCHEMA_VERSION_V5:
                successor_binding = stage1.get("current_byte_binding_successor")
                if not isinstance(successor_binding, dict):
                    raise Stage2IntakeError(
                        "v5 Stage1 production binding successor is invalid"
                    )
                successor_path = safe_relative(
                    successor_binding.get("path"),
                    label="Stage1 production binding successor",
                )
                successor = _validate_stage1_production_binding_successor(
                    source_root,
                    successor_path,
                    expected_identity=expected_identity,
                )
                _validate_stage1_successor_candidate_projection(
                    manifest,
                    source_root,
                    successor,
                    expected_identity=expected_identity,
                    base_index=base_index,
                )
                direct_bindings.append(successor_binding)
    elif schema_version == SCHEMA_VERSION_V2:
        actual_stage0_paths, _record, actual_receipts = _validate_stage0_and_stage1(
            source_root,
            stage0_paths,
            stage1_record,
            stage1_receipts,
            expected_identity=expected_identity,
        )
    else:
        raise Stage2IntakeError("manifest schema does not select a Stage0/Stage1 validator")
    if directory_identity(source_root) != expected_identity:
        raise Stage2IntakeError("source checkout identity changed")
    expected_stage0_paths = (
        FRESH_STAGE0_CANDIDATE_PATHS
        if schema_version in {SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}
        else STAGE0_CANDIDATE_PATHS
    )
    if actual_stage0_paths != expected_stage0_paths or set(actual_receipts) != set(stage1_receipts):
        raise Stage2IntakeError("upstream Stage0 or Stage1 path binding drift")

    by_path = {row.get("path"): row for row in direct_bindings}
    direct_paths = [*stage0_paths, stage1_record, *stage1_receipts]
    if schema_version in {SCHEMA_VERSION_V3, SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}:
        direct_paths.extend((registry_path, remediation_path))
    if schema_version in {SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}:
        direct_paths.append(aggregate_path)
    if schema_version == SCHEMA_VERSION_V5:
        direct_paths.append(successor_path)
    for relative in direct_paths:
        binding = by_path.get(relative.as_posix())
        if not isinstance(binding, dict):
            raise Stage2IntakeError(f"upstream binding path drift: {relative.as_posix()}")
        live = _entry(
            source_root,
            relative,
            base_oid,
            expected_identity=expected_identity,
            base_index=base_index,
        )
        if live != binding:
            raise Stage2IntakeError(
                f"upstream binding bytes, mode, blob, or base entry drift: {relative.as_posix()}"
            )


def _read_stage0_reference_paths(
    source_root: Path,
    candidates: Sequence[Path],
    *,
    stage0_root: Path | None = None,
    expected_identity: DirectoryIdentity | None = None,
) -> frozenset[Path]:
    """Read the recursive evidence/source/test closure of the Stage0 candidates."""
    references: set[Path] = set()
    normalized_candidates = tuple(safe_relative(candidate) for candidate in candidates)
    pending = list(normalized_candidates)
    if stage0_root is not None:
        for candidate in pending:
            try:
                candidate.relative_to(stage0_root)
            except ValueError as exc:
                raise Stage2IntakeError(
                    "Stage0 direct candidate escapes declared root: "
                    f"{candidate.as_posix()}"
                ) from exc
    if (
        stage0_root == FRESH_STAGE0_ROOT
        and len(normalized_candidates) == len(FRESH_STAGE0_CANDIDATE_PATHS)
        and set(normalized_candidates) == set(FRESH_STAGE0_CANDIDATE_PATHS)
    ):
        references.update(FRESH_V4_HISTORICAL_STAGE0_CANDIDATE_PATHS)
        pending.extend(FRESH_V4_HISTORICAL_STAGE0_CANDIDATE_PATHS)
    visited: set[Path] = set()
    while pending:
        candidate = pending.pop()
        if candidate in visited:
            continue
        visited.add(candidate)
        try:
            payload, _metadata = _read_regular_bytes(
                source_root,
                candidate,
                label="Stage0 recursive candidate",
                expected_identity=expected_identity,
            )
            record = json.loads(payload.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise Stage2IntakeError(f"cannot read Stage0 candidate references: {candidate}") from exc
        if not isinstance(record, dict):
            raise Stage2IntakeError(f"Stage0 candidate references root drift: {candidate}")
        for group in ("fragments", "manifest", "sources", "tests"):
            values = record.get(group)
            if values is None:
                continue
            if isinstance(values, dict):
                values = [values]
            if not isinstance(values, list):
                raise Stage2IntakeError(f"Stage0 candidate {group} binding drift: {candidate}")
            for value in values:
                if (
                    not isinstance(value, dict)
                    or not isinstance(value.get("path"), str)
                    or not isinstance(value.get("snapshot_path"), str)
                ):
                    raise Stage2IntakeError(f"Stage0 candidate {group} reference drift: {candidate}")
                referenced = safe_relative(
                    value["path"],
                    label=f"Stage0 candidate {group} reference",
                )
                snapshot = safe_relative(
                    candidate.parent / value["snapshot_path"],
                    label=f"Stage0 candidate {group} snapshot",
                )
                references.update((referenced, snapshot))
                if referenced.name == "candidate.v2.json":
                    pending.append(referenced)
    if stage0_root == FRESH_STAGE0_ROOT:
        references.add(FRESH_C9_SIDECAR_INPUT)
    return frozenset(references)


def _is_stage0_closure_path(
    relative: Path,
    *,
    references: frozenset[Path],
    stage0_root: Path = DEFAULT_STAGE0_ROOT,
) -> bool:
    # Candidate-local snapshots live below candidates/<family>/snapshots.  They
    # are valid only through the recursive reference that names them.
    if relative in references:
        return True
    try:
        below_b23 = relative.relative_to(stage0_root)
    except ValueError:
        return False
    return len(below_b23.parts) > 1 and below_b23.parts[0] in B23_FROZEN_DIRECTORIES


def _required_stage0_closure(
    source_root: Path,
    base_oid: str,
    references: frozenset[Path],
    *,
    direct_stage0: Sequence[Path] = STAGE0_CANDIDATE_PATHS,
    expected_identity: DirectoryIdentity | None = None,
    base_index: BaseTreeIndex | None = None,
) -> frozenset[Path]:
    """Select only referenced live regular files that differ from the base tree.

    Historical candidate file_sha256 values are deliberately not consulted:
    predecessor evidence may have drifted since it was frozen.  Stage2 closure
    is defined by the current source bytes and their local origin/main base.
    """
    required: set[Path] = set()
    direct = set(direct_stage0)
    for relative in sorted(references, key=lambda path: path.as_posix()):
        if relative in direct:
            continue
        try:
            payload, metadata = _read_regular_bytes(
                source_root,
                relative,
                label="Stage0 reference path or snapshot",
                expected_identity=expected_identity,
            )
        except Stage2IntakeError as exc:
            raise Stage2IntakeError(
                f"Stage0 reference path or snapshot is invalid: {relative.as_posix()}: {exc}"
            ) from exc
        mode = "100755" if metadata.st_mode & 0o111 else "100644"
        try:
            base_mode, base_blob = _base_tree_entry(
                source_root, base_oid, relative, base_index=base_index
            )
            blob = git_blob_oid(payload, object_format=(base_index.object_format if base_index else "sha1"))
        except (OSError, UnicodeError, Stage2IntakeError, GitBatchError) as exc:
            raise Stage2IntakeError(
                f"cannot compare Stage0 closure path with base: {relative.as_posix()}: {exc}"
            ) from exc
        if (mode, blob) != (base_mode, base_blob):
            required.add(relative)
    return frozenset(required)


def assert_stage0_closure_projection(
    manifest: dict[str, Any],
    source_root: Path,
    *,
    expected_identity: DirectoryIdentity | None = None,
    base_index: BaseTreeIndex | None = None,
) -> frozenset[Path]:
    """Recompute and enforce the complete Stage0 closure from the live source."""
    source = manifest.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("checkout"), str):
        raise Stage2IntakeError("manifest source checkout is required for Stage0 closure")
    checkout = Path(source["checkout"])
    if not checkout.is_absolute():
        raise Stage2IntakeError("manifest source checkout must be absolute")
    if expected_identity is None:
        expected_identity = (
            int(source.get("dev", -1)),
            int(source.get("ino", -1)),
        )
    live_root = source_root
    if source_root.as_posix() != source["checkout"]:
        raise Stage2IntakeError("Stage0 closure source checkout drift")
    try:
        observed_identity = directory_identity(live_root)
    except OSError as exc:
        raise Stage2IntakeError("manifest source checkout is missing") from exc
    if observed_identity != expected_identity:
        raise Stage2IntakeError("source checkout identity changed")
    base_oid = source.get("base_oid")
    if not isinstance(base_oid, str) or GIT_OID.fullmatch(base_oid) is None:
        raise Stage2IntakeError("Stage0 closure base oid is invalid")
    if base_index is None:
        try:
            base_index = BaseTreeIndex.from_repo(live_root, base_oid, runner=git_output)
        except GitBatchError as exc:
            raise Stage2IntakeError(str(exc)) from exc

    stage0 = manifest.get("stage0_b23")
    if not isinstance(stage0, dict):
        raise Stage2IntakeError("Stage0 closure projection is invalid")
    refs = stage0.get("refs")
    closure = stage0.get("closure")
    if not isinstance(refs, list) or not isinstance(closure, list):
        raise Stage2IntakeError("Stage0 closure projection is invalid")
    try:
        schema_version = manifest.get("schema_version")
        if schema_version in {SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}:
            stage0_root = safe_relative(stage0.get("root"), label="Stage0 root")
            if stage0_root != FRESH_STAGE0_ROOT:
                raise Stage2IntakeError("v4 Stage0 root binding drift")
        else:
            stage0_root = DEFAULT_STAGE0_ROOT
        expected_stage0 = tuple(
            stage0_root / "candidates" / family / "candidate.v2.json"
            for family in STAGE0_FAMILIES
        )
        ref_paths = [safe_relative(row.get("path")) for row in refs]
        closure_paths = [safe_relative(row.get("path")) for row in closure]
    except (AttributeError, TypeError, Stage2IntakeError) as exc:
        raise Stage2IntakeError("Stage0 closure projection path drift") from exc
    if len(ref_paths) != len(set(ref_paths)) or set(ref_paths) != set(expected_stage0):
        raise Stage2IntakeError("Stage0 closure direct candidate set drift")
    if len(closure_paths) != len(set(closure_paths)):
        raise Stage2IntakeError("Stage0 closure paths contain duplicates")

    references = _read_stage0_reference_paths(
        live_root,
        expected_stage0,
        stage0_root=(
            stage0_root
            if schema_version in {SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}
            else None
        ),
        expected_identity=expected_identity,
    )
    required = _required_stage0_closure(
        live_root,
        base_oid,
        references,
        direct_stage0=expected_stage0,
        expected_identity=expected_identity,
        base_index=base_index,
    )
    declared = set(closure_paths)
    if declared != required:
        missing = sorted(path.as_posix() for path in required - declared)
        extra = sorted(path.as_posix() for path in declared - required)
        raise Stage2IntakeError(
            "Stage0 closure must exactly equal required upserts: "
            f"missing={missing}, extra={extra}"
        )
    return required


def _upsert_entries(
    source_root: Path,
    base_oid: str,
    stage0_paths: Sequence[Path],
    stage0_closure_upserts: Sequence[Path],
    stage1_record: Path,
    stage1_receipts: Sequence[Path],
    additional_upserts: Sequence[Path],
    *,
    stage0_root: Path = DEFAULT_STAGE0_ROOT,
    all_lines_aggregate: Path | None = None,
    stage1_production_binding_successor: Path | None = None,
    current_byte_successor_registry: Path | None = None,
    stage1_remediation_record: Path | None = None,
    expected_identity: DirectoryIdentity | None = None,
    base_index: BaseTreeIndex | None = None,
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    grouped: list[tuple[str, Path]] = []
    grouped.extend(("stage0_b23", path) for path in stage0_paths)
    grouped.extend(("stage0_closure", path) for path in stage0_closure_upserts)
    grouped.append(("stage1_record", stage1_record))
    grouped.extend(("stage1_receipt", path) for path in stage1_receipts)
    if current_byte_successor_registry is not None:
        grouped.append(("current_byte_successor_registry", current_byte_successor_registry))
    if stage1_remediation_record is not None:
        grouped.append(("stage1_remediation_record", stage1_remediation_record))
    if all_lines_aggregate is not None:
        grouped.append(("all_lines_aggregate", all_lines_aggregate))
    if stage1_production_binding_successor is not None:
        grouped.append(
            ("stage1_production_binding_successor", stage1_production_binding_successor)
        )
    grouped.extend(("stage1_closure", path) for path in additional_upserts)
    direct_stage0 = tuple(safe_relative(path) for path in stage0_paths)
    stage0_closure = tuple(safe_relative(path) for path in stage0_closure_upserts)
    additional = tuple(safe_relative(path) for path in additional_upserts)
    protected = {*direct_stage0, safe_relative(stage1_record)}
    protected.update(safe_relative(path) for path in stage1_receipts)
    if current_byte_successor_registry is not None:
        protected.add(safe_relative(current_byte_successor_registry))
    if stage1_remediation_record is not None:
        protected.add(safe_relative(stage1_remediation_record))
    if all_lines_aggregate is not None:
        protected.add(safe_relative(all_lines_aggregate))
    if stage1_production_binding_successor is not None:
        protected.add(safe_relative(stage1_production_binding_successor))
    references = _read_stage0_reference_paths(
        source_root,
        direct_stage0,
        stage0_root=(stage0_root if stage0_root == FRESH_STAGE0_ROOT else None),
        expected_identity=expected_identity,
    )
    required_closure = _required_stage0_closure(
        source_root,
        base_oid,
        references,
        direct_stage0=direct_stage0,
        expected_identity=expected_identity,
        base_index=base_index,
    )
    for path in stage0_closure:
        if path in direct_stage0:
            raise Stage2IntakeError(
                f"stage0_closure_upsert cannot overlap a direct Stage0 ref: {path.as_posix()}"
            )
    if len(stage0_closure) != len(set(stage0_closure)) or set(stage0_closure) != required_closure:
        missing = sorted(path.as_posix() for path in required_closure - set(stage0_closure))
        extra = sorted(path.as_posix() for path in set(stage0_closure) - required_closure)
        raise Stage2IntakeError(
            f"stage0_closure_upserts must exactly equal required upserts: "
            f"missing={missing}, extra={extra}"
        )
    for path in stage0_closure:
        if path in protected:
            raise Stage2IntakeError(
                f"stage0_closure_upsert overlaps Stage0/Stage1 binding: {path.as_posix()}"
            )
        if path in additional:
            raise Stage2IntakeError(
                f"stage0_closure_upsert overlaps Stage1 closure: {path.as_posix()}"
            )
        if not _is_stage0_closure_path(
            path, references=references, stage0_root=stage0_root
        ):
            raise Stage2IntakeError(
                f"stage0_closure_upsert is not B23 frozen evidence or a referenced source/test: "
                f"{path.as_posix()}"
            )
        metadata = _lstat_beneath(source_root, path, expected_identity=expected_identity)
        if not stat.S_ISREG(metadata.st_mode):
            raise Stage2IntakeError(
                f"stage0_closure_upsert must be a regular file: {path.as_posix()}"
            )
    for path in additional_upserts:
        safe = safe_relative(path)
        try:
            safe.relative_to(stage0_root)
        except ValueError:
            pass
        else:
            raise Stage2IntakeError(f"additional_upsert cannot masquerade as Stage0: {safe.as_posix()}")
        if safe in protected:
            raise Stage2IntakeError(f"additional_upsert overlaps Stage0/Stage1 binding: {safe.as_posix()}")
        if safe in stage0_closure:
            raise Stage2IntakeError(f"additional_upsert overlaps Stage0 closure: {safe.as_posix()}")
        metadata = _lstat_beneath(source_root, safe, expected_identity=expected_identity)
        if not stat.S_ISREG(metadata.st_mode):
            raise Stage2IntakeError(f"additional_upsert must be a regular file: {safe.as_posix()}")
    assert_no_path_collisions(path for _, path in grouped)
    all_paths = [path for _, path in grouped]
    if len(set(all_paths)) != len(all_paths):
        raise Stage2IntakeError("intake path sets overlap")
    entries = [
        _entry(
            source_root,
            path,
            base_oid,
            expected_identity=expected_identity,
            base_index=base_index,
        )
        for _, path in grouped
    ]
    by_path = dict(zip(all_paths, entries, strict=True))
    for relative in stage0_paths:
        try:
            safe_relative(relative).relative_to(stage0_root)
        except ValueError as exc:
            raise Stage2IntakeError(
                f"Stage0 reference is outside B23 root: {relative.as_posix()}"
            ) from exc
    return entries, by_path


def build_manifest(
    *,
    source_root: Path,
    stage0_paths: Sequence[Path],
    stage0_closure_upserts: Sequence[Path] = (),
    stage1_record: Path,
    stage1_receipts: Sequence[Path],
    current_byte_successor_registry: Path | None = None,
    stage1_remediation_record: Path | None = None,
    all_lines_aggregate: Path | None = None,
    stage1_production_binding_successor: Path | None = None,
    additional_upserts: Sequence[Path] = (),
    delete_paths: Sequence[Path] = (),
    remote_name: str = "origin",
    base_ref: str = DEFAULT_BASE_REF,
    read_cache: BoundedReadOnlyCache[IntakeCacheKey, IntakeCacheValue] | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=exact_candidate_intake "
    "fact_source=git_source_checkout+stage0_refs+stage1_bindings+selected_files "
    "witness=test:test_builds_canonical_manifest_with_exact_base_preconditions",
]:
    if not stage0_paths:
        raise Stage2IntakeError("at least one Stage0 B23 reference is required")
    if not stage1_receipts:
        raise Stage2IntakeError("at least one Stage1 receipt is required")
    if (current_byte_successor_registry is None) != (stage1_remediation_record is None):
        raise Stage2IntakeError(
            "v3 intake requires both current-byte successor registry and Stage1 remediation record"
        )
    if (
        stage1_production_binding_successor is not None
        and current_byte_successor_registry is None
    ):
        raise Stage2IntakeError(
            "v5 intake requires the complete v4 route plus the Stage1 production binding successor"
        )
    source = _source_identity(source_root, remote_name, base_ref)
    source_identity = (source["dev"], source["ino"])
    successor_resolutions: list[dict[str, str]] = []
    stage0_root = DEFAULT_STAGE0_ROOT
    if current_byte_successor_registry is None:
        if all_lines_aggregate is not None:
            raise Stage2IntakeError("all-lines aggregate is only valid for v4 intake")
        stage0_paths, _stage1_record_payload, record_receipts = _validate_stage0_and_stage1(
            source_root,
            stage0_paths,
            stage1_record,
            stage1_receipts,
            expected_identity=source_identity,
        )
        schema_version = SCHEMA_VERSION_V2
    else:
        registry_path = safe_relative(current_byte_successor_registry)
        if registry_path == FRESH_CURRENT_BYTE_SUCCESSOR_REGISTRY:
            if all_lines_aggregate is None:
                raise Stage2IntakeError("v4 intake requires the all-lines aggregate")
            (
                stage0_paths,
                _stage1_record_payload,
                record_receipts,
                successor_resolutions,
            ) = _validate_stage0_and_stage1_v4(
                source_root,
                stage0_paths,
                stage1_record,
                stage1_receipts,
                registry_path,
                stage1_remediation_record,
                expected_identity=source_identity,
            )
            if stage1_production_binding_successor is None:
                schema_version = SCHEMA_VERSION_V4
            else:
                _validate_stage1_production_binding_successor(
                    source_root,
                    stage1_production_binding_successor,
                    expected_identity=source_identity,
                )
                schema_version = SCHEMA_VERSION_V5
            stage0_root = FRESH_STAGE0_ROOT
            all_lines_aggregate = safe_relative(all_lines_aggregate)
            _validate_all_lines_aggregate(
                source_root,
                all_lines_aggregate,
                expected_identity=source_identity,
            )
        else:
            if stage1_production_binding_successor is not None:
                raise Stage2IntakeError(
                    "v5 intake requires the fresh v4 current-byte successor registry"
                )
            if all_lines_aggregate is not None:
                raise Stage2IntakeError("all-lines aggregate is only valid for v4 intake")
            (
                stage0_paths,
                _stage1_record_payload,
                record_receipts,
                successor_resolutions,
            ) = _validate_stage0_and_stage1_v3(
                source_root,
                stage0_paths,
                stage1_record,
                stage1_receipts,
                registry_path,
                stage1_remediation_record,
                expected_identity=source_identity,
            )
            schema_version = SCHEMA_VERSION_V3
    try:
        base_index = BaseTreeIndex.from_repo(source_root, source["base_oid"], runner=git_output)
    except GitBatchError as exc:
        raise Stage2IntakeError(str(exc)) from exc
    stage1_record = safe_relative(stage1_record)
    stage1_receipts = tuple(sorted(record_receipts, key=lambda path: path.as_posix()))
    if current_byte_successor_registry is not None:
        current_byte_successor_registry = safe_relative(current_byte_successor_registry)
    if stage1_remediation_record is not None:
        stage1_remediation_record = safe_relative(stage1_remediation_record)
    if stage1_production_binding_successor is not None:
        stage1_production_binding_successor = safe_relative(
            stage1_production_binding_successor
        )
    additional_upserts = tuple(safe_relative(path) for path in additional_upserts)
    if all_lines_aggregate is not None:
        all_lines_aggregate = safe_relative(all_lines_aggregate)
        additional_upserts = tuple(
            path for path in additional_upserts if path != all_lines_aggregate
        )
    stage0_closure_upserts = tuple(safe_relative(path) for path in stage0_closure_upserts)
    workflow_equivalent = (
        current_byte_successor_registry is not None
        and stage1_remediation_record is not None
        and (
            stage1_remediation_record == WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_RECORD
            or stage1_remediation_record in STAGE3_V6_ARTIFACT_REMEDIATION_RECORDS
        )
    )
    if workflow_equivalent:
        workflow_satisfied_upserts = [*stage0_closure_upserts]
        if current_byte_successor_registry is not None:
            # The current registry is already a direct Stage0 binding.  Exact
            # bundle selectors may name it, but it must not be duplicated in
            # the derived Stage1 closure.
            workflow_satisfied_upserts.append(current_byte_successor_registry)
        if stage1_production_binding_successor is not None:
            workflow_satisfied_upserts.append(stage1_production_binding_successor)
        additional_upserts, delete_paths = _merge_workflow_selector_selection(
            additional_upserts,
            tuple(safe_relative(path) for path in delete_paths),
            _workflow_selector_delta(source_root, base_index),
            satisfied_upserts=workflow_satisfied_upserts,
        )
        if stage1_remediation_record in STAGE3_V6_ARTIFACT_REMEDIATION_RECORDS:
            additional_upserts, delete_paths = _merge_workflow_selector_selection(
                additional_upserts,
                delete_paths,
                _workflow_selector_delta(
                    source_root,
                    base_index,
                    helper_name="compute_frontend_selector_delta",
                ),
                satisfied_upserts=workflow_satisfied_upserts,
            )
    else:
        delete_paths = tuple(safe_relative(path) for path in delete_paths)
    entries, by_path = _upsert_entries(
        source_root,
        source["base_oid"],
        stage0_paths,
        stage0_closure_upserts,
        stage1_record,
        stage1_receipts,
        additional_upserts,
        stage0_root=stage0_root,
        all_lines_aggregate=all_lines_aggregate,
        stage1_production_binding_successor=stage1_production_binding_successor,
        current_byte_successor_registry=current_byte_successor_registry,
        stage1_remediation_record=stage1_remediation_record,
        expected_identity=(
            source["dev"],
            source["ino"],
        ),
        base_index=base_index,
    )
    assert_no_path_collisions([*(Path(row["path"]) for row in entries), *delete_paths])
    entries.extend(
        _delete_entry(
            source_root,
            path,
            source["base_oid"],
            expected_identity=(source["dev"], source["ino"]),
            base_index=base_index,
        )
        for path in delete_paths
    )
    entries.sort(key=lambda row: row["path"])

    def ref(relative: Path) -> dict[str, str]:
        return by_path[relative]

    manifest: dict[str, Any] = {
        "schema_version": schema_version,
        "status": MANIFEST_STATUS,
        "authoritative": False,
        "source": source,
        "stage0_b23": {
            "stage": "B23",
            **(
                {"root": stage0_root.as_posix()}
                if schema_version in {SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}
                else {}
            ),
            "refs": [ref(safe_relative(path)) for path in stage0_paths],
            "closure": [
                ref(path)
                for path in sorted(stage0_closure_upserts, key=lambda path: path.as_posix())
            ],
            **(
                {
                    "current_byte_successor_registry": ref(current_byte_successor_registry),
                    "successor_resolutions": successor_resolutions,
                }
                if current_byte_successor_registry is not None
                else {}
            ),
        },
        "stage1": {
            "record": ref(safe_relative(stage1_record)),
            "receipts": [ref(safe_relative(path)) for path in stage1_receipts],
            "closure": [
                *(
                    [ref(all_lines_aggregate)]
                    if all_lines_aggregate is not None
                    else []
                ),
                *(ref(path) for path in additional_upserts),
            ],
            **(
                {"all_lines_aggregate": ref(all_lines_aggregate)}
                if all_lines_aggregate is not None
                else {}
            ),
            **(
                {"remediation_record": ref(stage1_remediation_record)}
                if stage1_remediation_record is not None
                else {}
            ),
            **(
                {
                    "current_byte_binding_successor": ref(
                        stage1_production_binding_successor
                    )
                }
                if stage1_production_binding_successor is not None
                else {}
            ),
        },
        "entries": entries,
    }
    validate_manifest(manifest, base_index=base_index)
    if read_cache is not None:
        key = _manifest_cache_key(manifest, object_format=base_index.object_format)
        read_cache.put(key, IntakeCacheValue(base_index=base_index))
    return manifest


def validate_manifest_structure(manifest: Any) -> None:
    if not isinstance(manifest, dict):
        raise Stage2IntakeError("manifest JSON root must be an object")
    required = {
        "schema_version",
        "status",
        "authoritative",
        "source",
        "stage0_b23",
        "stage1",
        "entries",
    }
    if set(manifest) != required:
        raise Stage2IntakeError("manifest field set drift")
    schema_version = manifest["schema_version"]
    if (
        schema_version not in {
            SCHEMA_VERSION_V2,
            SCHEMA_VERSION_V3,
            SCHEMA_VERSION_V4,
            SCHEMA_VERSION_V5,
        }
        or manifest["status"] != MANIFEST_STATUS
        or manifest["authoritative"] is not False
    ):
        raise Stage2IntakeError("manifest identity or authority ceiling drift")
    source = manifest["source"]
    if not isinstance(source, dict) or set(source) != {
        "checkout",
        "dev",
        "ino",
        "head",
        "remote_name",
        "remote",
        "base_ref",
        "base_oid",
        "source_clean",
        "porcelain_sha256",
        "selection_boundary",
    }:
        raise Stage2IntakeError("source identity field set drift")
    for key in ("checkout", "head", "remote_name", "remote", "base_ref", "base_oid"):
        if not isinstance(source[key], str) or not source[key].strip():
            raise Stage2IntakeError("source identity fields must be non-empty")
    if (
        isinstance(source["dev"], bool)
        or isinstance(source["ino"], bool)
        or not isinstance(source["dev"], int)
        or not isinstance(source["ino"], int)
        or source["ino"] <= 0
    ):
        raise Stage2IntakeError("source checkout filesystem identity is invalid")
    if source["base_ref"] != DEFAULT_BASE_REF:
        raise Stage2IntakeError(f"source base_ref must be exactly {DEFAULT_BASE_REF}")
    if source["remote_name"] != DEFAULT_REMOTE_NAME:
        raise Stage2IntakeError(f"source remote_name must be exactly {DEFAULT_REMOTE_NAME}")
    if not isinstance(source["source_clean"], bool):
        raise Stage2IntakeError("source_clean must be boolean")
    if not isinstance(source["porcelain_sha256"], str) or SHA256.fullmatch(source["porcelain_sha256"]) is None:
        raise Stage2IntakeError("porcelain status digest drift")
    if source["selection_boundary"] != "manifest_entries_only":
        raise Stage2IntakeError("selection boundary drift")
    if GIT_OID.fullmatch(source["head"]) is None or GIT_OID.fullmatch(source["base_oid"]) is None:
        raise Stage2IntakeError("source git oid drift")
    entries = manifest["entries"]
    if not isinstance(entries, list) or not entries:
        raise Stage2IntakeError("manifest entries must be a non-empty list")
    entry_fields = {
        "path",
        "operation",
        "mode",
        "sha256",
        "blob",
        "base_mode",
        "base_blob",
    }
    paths: list[Path] = []
    for row in entries:
        if not isinstance(row, dict) or set(row) != entry_fields:
            raise Stage2IntakeError("entry field set drift")
        if not all(isinstance(row[field], str) for field in entry_fields):
            raise Stage2IntakeError("entry contract drift")
        relative = safe_relative(row["path"])
        paths.append(relative)
        if row["operation"] == "UPSERT":
            valid = row["mode"] in {"100644", "100755", "120000"} and SHA256.fullmatch(
                row["sha256"]
            ) is not None and GIT_OID.fullmatch(row["blob"]) is not None
            if row["base_mode"] == "000000":
                valid = valid and row["base_blob"] == ""
            else:
                valid = (
                    valid
                    and row["base_mode"] in {"100644", "100755", "120000"}
                    and GIT_OID.fullmatch(row["base_blob"]) is not None
                )
        elif row["operation"] == "DELETE":
            valid = (
                row["mode"] == "000000"
                and row["sha256"] == ""
                and row["blob"] == ""
                and row["base_mode"] in {"100644", "100755", "120000"}
                and GIT_OID.fullmatch(row["base_blob"]) is not None
            )
        else:
            valid = False
        if not valid:
            raise Stage2IntakeError(f"entry contract drift: {relative.as_posix()}")
    if len(set(paths)) != len(paths):
        raise Stage2IntakeError("manifest path duplicates")
    assert_no_path_collisions(paths)
    if [path.as_posix() for path in paths] != sorted(path.as_posix() for path in paths):
        raise Stage2IntakeError("manifest entries must be path-sorted")
    stage0 = manifest["stage0_b23"]
    stage1 = manifest["stage1"]
    expected_stage0_fields = {"stage", "refs", "closure"}
    expected_stage1_fields = {"record", "receipts", "closure"}
    if schema_version in {SCHEMA_VERSION_V3, SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}:
        expected_stage0_fields.update(
            {"current_byte_successor_registry", "successor_resolutions"}
        )
        expected_stage1_fields.add("remediation_record")
    if schema_version in {SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}:
        expected_stage0_fields.add("root")
        expected_stage1_fields.add("all_lines_aggregate")
    if schema_version == SCHEMA_VERSION_V5:
        expected_stage1_fields.add("current_byte_binding_successor")
    if not isinstance(stage0, dict) or set(stage0) != expected_stage0_fields:
        raise Stage2IntakeError("Stage0 B23 binding drift")
    if stage0.get("stage") != "B23":
        raise Stage2IntakeError("Stage0 stage binding must be B23")
    if schema_version in {SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}:
        if stage0.get("root") != FRESH_STAGE0_ROOT.as_posix():
            raise Stage2IntakeError("v4 Stage0 root binding drift")
        expected_stage0_paths = FRESH_STAGE0_CANDIDATE_PATHS
    else:
        expected_stage0_paths = STAGE0_CANDIDATE_PATHS
    if not isinstance(stage0.get("refs"), list) or not isinstance(stage0.get("closure"), list):
        raise Stage2IntakeError("Stage0 closure binding drift")
    if len(stage0["refs"]) != len(expected_stage0_paths):
        raise Stage2IntakeError("Stage0 B23 binding must contain exactly nine candidates")
    if not isinstance(stage1, dict) or not isinstance(stage1.get("record"), dict):
        raise Stage2IntakeError("Stage1 record binding drift")
    if not isinstance(stage1, dict) or set(stage1) != expected_stage1_fields:
        raise Stage2IntakeError("Stage1 binding drift")
    if not isinstance(stage1.get("receipts"), list) or not stage1["receipts"]:
        raise Stage2IntakeError("Stage1 receipt binding drift")
    if not isinstance(stage1["closure"], list):
        raise Stage2IntakeError("Stage1 closure binding drift")
    entry_map = {row["path"]: row for row in entries}
    direct_bindings = [
        *stage0["refs"],
        *stage0["closure"],
        stage1["record"],
        *stage1["receipts"],
        *stage1.get("closure", []),
    ]
    if schema_version in {SCHEMA_VERSION_V3, SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}:
        registry_binding = stage0.get("current_byte_successor_registry")
        remediation_binding = stage1.get("remediation_record")
        direct_bindings.extend((registry_binding, remediation_binding))
        resolutions = stage0.get("successor_resolutions")
        resolution_fields = {
            "candidate_path",
            "candidate_sha256",
            "family",
            "group",
            "source_path",
            "predecessor_sha256",
            "successor_sha256",
            "registry_successor_id",
            "registry_family",
        }
        if not isinstance(resolutions, list) or (
            schema_version == SCHEMA_VERSION_V3 and not resolutions
        ):
            raise Stage2IntakeError("Stage0 successor resolutions are invalid")
        if schema_version in {SCHEMA_VERSION_V4, SCHEMA_VERSION_V5} and resolutions:
            raise Stage2IntakeError("fresh Stage0 successor resolutions must be empty")
        keys: list[tuple[str, str, str]] = []
        for row in resolutions:
            if not isinstance(row, dict) or set(row) != resolution_fields:
                raise Stage2IntakeError("v3 Stage0 successor resolution field drift")
            if not all(isinstance(value, str) and value for value in row.values()):
                raise Stage2IntakeError("v3 Stage0 successor resolution value drift")
            for digest_key in ("candidate_sha256", "predecessor_sha256", "successor_sha256"):
                if SHA256.fullmatch(row[digest_key]) is None:
                    raise Stage2IntakeError("v3 Stage0 successor resolution digest drift")
            if row["family"] not in STAGE0_FAMILIES or row["group"] not in {"fragments", "sources", "tests"}:
                raise Stage2IntakeError("v3 Stage0 successor resolution identity drift")
            keys.append((row["family"], row["group"], row["source_path"]))
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise Stage2IntakeError("v3 Stage0 successor resolutions are unsorted or duplicated")
        if schema_version in {SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}:
            if (
                not isinstance(remediation_binding, dict)
                or remediation_binding.get("path")
                != STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD.as_posix()
            ):
                raise Stage2IntakeError("v4 Stage1 remediation must be correction1")
            if (
                not isinstance(registry_binding, dict)
                or registry_binding.get("path")
                != FRESH_CURRENT_BYTE_SUCCESSOR_REGISTRY.as_posix()
            ):
                raise Stage2IntakeError("v4 current-byte successor registry binding drift")
            aggregate_binding = stage1.get("all_lines_aggregate")
            if (
                not isinstance(aggregate_binding, dict)
                or aggregate_binding.get("path") != ALL_LINES_AGGREGATE.as_posix()
                or aggregate_binding not in stage1["closure"]
            ):
                raise Stage2IntakeError("v4 all-lines aggregate binding drift")
            direct_bindings.append(aggregate_binding)
            if schema_version == SCHEMA_VERSION_V5:
                successor_binding = stage1.get("current_byte_binding_successor")
                if (
                    not isinstance(successor_binding, dict)
                    or successor_binding.get("path")
                    != STAGE1_PRODUCTION_BINDING_SUCCESSOR.as_posix()
                ):
                    raise Stage2IntakeError(
                        "v5 Stage1 production binding successor drift"
                    )
                direct_bindings.append(successor_binding)
        elif (
            not isinstance(remediation_binding, dict)
            or remediation_binding.get("path") not in {
                DEFAULT_STAGE1_REMEDIATION_RECORD.as_posix(),
                WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_RECORD.as_posix(),
                *STAGE3_V6_ARTIFACT_REMEDIATION_RECORD_PATHS,
            }
        ):
            raise Stage2IntakeError("v3 Stage1 remediation record binding drift")
        if schema_version == SCHEMA_VERSION_V3:
            expected_registry_path = (
                STAGE3_CURRENT_BYTE_SUCCESSOR_REGISTRY
                if remediation_binding["path"]
                in STAGE3_V6_ARTIFACT_REMEDIATION_RECORD_PATHS
                else DEFAULT_CURRENT_BYTE_SUCCESSOR_REGISTRY
            )
            allowed_registry_paths = {expected_registry_path.as_posix()}
            if (
                remediation_binding["path"]
                == STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD.as_posix()
            ):
                allowed_registry_paths.add(
                    CONVERGENCE_CURRENT_BYTE_SUCCESSOR_REGISTRY.as_posix()
                )
            if (
                not isinstance(registry_binding, dict)
                or registry_binding.get("path") not in allowed_registry_paths
            ):
                raise Stage2IntakeError("v3 current-byte successor registry binding drift")
    for binding in direct_bindings:
        if not isinstance(binding, dict) or set(binding) != entry_fields:
            raise Stage2IntakeError("Stage0 or Stage1 binding must be an upsert")
        if not isinstance(binding["operation"], str) or binding["operation"] != "UPSERT":
            raise Stage2IntakeError("Stage0 or Stage1 binding must be an upsert")
        if not isinstance(binding["path"], str):
            raise Stage2IntakeError("Stage0 or Stage1 binding does not match entries")
        if entry_map.get(binding["path"]) != binding:
            raise Stage2IntakeError("Stage0 or Stage1 binding does not match entries")
    stage0_paths = [Path(binding.get("path", "")) for binding in stage0["refs"]]
    if len(stage0_paths) != len(set(stage0_paths)) or set(stage0_paths) != set(
        expected_stage0_paths
    ):
        raise Stage2IntakeError("Stage0 refs must be exactly C2-C9/I1 candidates")
    stage0_closure_paths = [Path(binding.get("path", "")) for binding in stage0["closure"]]
    stage1_closure_paths = [Path(binding.get("path", "")) for binding in stage1["closure"]]
    if [path.as_posix() for path in stage0_closure_paths] != sorted(path.as_posix() for path in stage0_closure_paths):
        raise Stage2IntakeError("Stage0 closure paths must be sorted")
    if len(stage0_closure_paths) != len(set(stage0_closure_paths)):
        raise Stage2IntakeError("Stage0 closure paths contain duplicates")
    if len(stage1_closure_paths) != len(set(stage1_closure_paths)):
        raise Stage2IntakeError("Stage1 closure paths contain duplicates")
    protected_paths = {Path(binding.get("path", "")) for binding in stage0["refs"]}
    protected_paths.add(Path(stage1["record"].get("path", "")))
    protected_paths.update(Path(binding.get("path", "")) for binding in stage1["receipts"])
    if schema_version in {SCHEMA_VERSION_V3, SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}:
        protected_paths.add(Path(stage0["current_byte_successor_registry"].get("path", "")))
        protected_paths.add(Path(stage1["remediation_record"].get("path", "")))
    if schema_version == SCHEMA_VERSION_V5:
        protected_paths.add(
            Path(stage1["current_byte_binding_successor"].get("path", ""))
        )
    if set(stage0_closure_paths) & protected_paths or set(stage1_closure_paths) & protected_paths:
        raise Stage2IntakeError("closure overlaps a direct Stage0 or Stage1 binding")
    if set(stage0_closure_paths) & set(stage1_closure_paths):
        raise Stage2IntakeError("Stage0 and Stage1 closures overlap")
    stage0_root = (
        FRESH_STAGE0_ROOT
        if schema_version in {SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}
        else DEFAULT_STAGE0_ROOT
    )
    for binding in stage0["refs"]:
        try:
            Path(binding["path"]).relative_to(stage0_root)
        except ValueError as exc:
            raise Stage2IntakeError("Stage0 reference is outside B23 root") from exc
    return None


def validate_manifest(
    manifest: Any,
    *,
    base_index: BaseTreeIndex | None = None,
) -> None:
    """Validate structure, then re-check the projected candidate closure."""
    validate_manifest_structure(manifest)
    source = manifest["source"]
    source_root = Path(source["checkout"])
    base_oid = source["base_oid"]
    if base_index is None:
        try:
            base_index = BaseTreeIndex.from_repo(source_root, base_oid, runner=git_output)
        except GitBatchError as exc:
            raise Stage2IntakeError(str(exc)) from exc
    if manifest["schema_version"] in {SCHEMA_VERSION_V4, SCHEMA_VERSION_V5}:
        _validate_all_lines_aggregate(
            source_root,
            safe_relative(
                manifest["stage1"]["all_lines_aggregate"].get("path"),
                label="all-lines aggregate binding",
            ),
            expected_identity=(int(source["dev"]), int(source["ino"])),
        )
    if manifest["schema_version"] == SCHEMA_VERSION_V5:
        source_identity = (int(source["dev"]), int(source["ino"]))
        successor = _validate_stage1_production_binding_successor(
            source_root,
            safe_relative(
                manifest["stage1"]["current_byte_binding_successor"].get("path"),
                label="Stage1 production binding successor",
            ),
            expected_identity=source_identity,
        )
        _validate_stage1_successor_candidate_projection(
            manifest,
            source_root,
            successor,
            expected_identity=source_identity,
            base_index=base_index,
        )
    if is_mrw_projected_candidate(source_root, manifest, base_index=base_index):
        try:
            check_source_closure(
                source_root,
                manifest=manifest,
                base_index=base_index,
            )
        except SourceClosureError as exc:
            raise Stage2IntakeError(str(exc)) from exc
    assert_stage0_closure_projection(
        manifest,
        source_root,
        base_index=base_index,
    )
    source_identity = (int(source["dev"]), int(source["ino"]))
    for row in manifest["entries"]:
        relative = safe_relative(row["path"])
        try:
            if row["operation"] == "UPSERT":
                expected = _entry(
                    source_root,
                    relative,
                    base_oid,
                    expected_identity=source_identity,
                    base_index=base_index,
                )
            elif row["operation"] == "DELETE":
                expected = _delete_entry(
                    source_root,
                    relative,
                    base_oid,
                    expected_identity=source_identity,
                    base_index=base_index,
                )
            else:  # validate_manifest_structure rejects this before live reads.
                raise Stage2IntakeError(
                    f"manifest entry operation drift: {relative.as_posix()}"
                )
        except (OSError, UnicodeError) as exc:
            raise Stage2IntakeError(
                f"manifest entry cannot be validated exactly: {relative.as_posix()}"
            ) from exc
        if row != expected:
            raise Stage2IntakeError(
                f"manifest entry exact projection drift: {relative.as_posix()}"
            )
    stage1 = manifest["stage1"]
    remediation = stage1.get("remediation_record")
    if (
        isinstance(remediation, dict)
        and (
            remediation.get("path")
            == WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_RECORD.as_posix()
            or remediation.get("path") in STAGE3_V6_ARTIFACT_REMEDIATION_RECORD_PATHS
        )
    ):
        check_closure = getattr(
            source_closure_module,
            "check_workflow_selector_manifest_closure",
            None,
        )
        if not callable(check_closure):
            raise Stage2IntakeError(
                "workflow-equivalent source closure implementation is unavailable"
            )
        try:
            check_closure(source_root, manifest, base_index=base_index)
        except (OSError, TypeError, ValueError) as exc:
            raise Stage2IntakeError(
                f"workflow-equivalent manifest closure failed: {exc}"
            ) from exc
        if remediation.get("path") in STAGE3_V6_ARTIFACT_REMEDIATION_RECORD_PATHS:
            check_frontend_closure = getattr(
                source_closure_module,
                "check_frontend_selector_manifest_closure",
                None,
            )
            if not callable(check_frontend_closure):
                raise Stage2IntakeError(
                    "frontend source closure implementation is unavailable"
                )
            try:
                check_frontend_closure(source_root, manifest, base_index=base_index)
            except (OSError, TypeError, ValueError) as exc:
                raise Stage2IntakeError(
                    f"frontend manifest closure failed: {exc}"
                ) from exc


def parse_paths(values: Iterable[str] | None) -> tuple[Path, ...]:
    return tuple(Path(value) for value in (values or ()))


def _assert_output_outside_source(
    path: Path,
    manifest: dict[str, Any],
) -> tuple[Path, DirectoryIdentity]:
    source = manifest.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("checkout"), str):
        raise Stage2IntakeError("manifest source checkout is required for output confinement")
    source_root = Path(source["checkout"])
    source_identity = (int(source["dev"]), int(source["ino"]))
    if directory_identity(source_root) != source_identity:
        raise Stage2IntakeError("source checkout identity changed")
    destination = path.absolute()
    resolved = destination.resolve(strict=False)
    try:
        resolved.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise Stage2IntakeError("output must be outside source checkout")
    # Existing parent components must not be symlinks; otherwise a later mkdir/open
    # could redirect the create-only write into the source checkout.
    current = destination.parent
    missing: list[Path] = []
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for parent in [current, *reversed(missing)]:
        try:
            if stat.S_ISLNK(parent.lstat().st_mode):
                raise Stage2IntakeError("output parent must not traverse a symlink")
        except FileNotFoundError:
            continue
    return destination, source_identity


def write_create_only(path: Path, manifest: dict[str, Any]) -> Path:
    validate_manifest(manifest)
    destination, source_identity = _assert_output_outside_source(path, manifest)
    if destination.exists() or destination.is_symlink():
        raise Stage2IntakeError(f"create-only target already exists: {destination}")
    try:
        return write_create_only_bytes(
            destination,
            canonical_json(manifest) + b"\n",
            (source_identity,),
        )
    except CreateOnlyWriteError as exc:
        raise Stage2IntakeError(str(exc)) from exc


def _failure_report(message: str) -> PreflightReport:
    return PreflightReport(CHECKER, (Finding("stage2_candidate_intake", "FAIL", message),))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--stage0-ref", action="append", type=Path, required=True)
    parser.add_argument("--stage0-closure-upsert", action="append", type=Path, default=[])
    parser.add_argument("--stage1-record", type=Path, required=True)
    parser.add_argument("--stage1-receipt", action="append", type=Path, required=True)
    parser.add_argument("--current-byte-successor-registry", type=Path)
    parser.add_argument("--stage1-remediation-record", type=Path)
    parser.add_argument("--all-lines-aggregate", type=Path)
    parser.add_argument("--stage1-production-binding-successor", type=Path)
    parser.add_argument("--upsert", action="append", type=Path, default=[])
    parser.add_argument("--delete", action="append", type=Path, default=[])
    parser.add_argument("--remote-name", default="origin")
    parser.add_argument("--base-ref", default=DEFAULT_BASE_REF)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = build_manifest(
            source_root=args.source_root.resolve(),
            stage0_paths=tuple(args.stage0_ref),
            stage0_closure_upserts=tuple(args.stage0_closure_upsert),
            stage1_record=args.stage1_record,
            stage1_receipts=tuple(args.stage1_receipt),
            current_byte_successor_registry=args.current_byte_successor_registry,
            stage1_remediation_record=args.stage1_remediation_record,
            all_lines_aggregate=args.all_lines_aggregate,
            stage1_production_binding_successor=(
                args.stage1_production_binding_successor
            ),
            additional_upserts=tuple(args.upsert),
            delete_paths=tuple(args.delete),
            remote_name=args.remote_name,
            base_ref=args.base_ref,
        )
        write_create_only(args.output, manifest)
    except (Stage2IntakeError, OSError, UnicodeError) as exc:
        print(_failure_report(str(exc)).to_json(), end="")
        return 1
    print(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
