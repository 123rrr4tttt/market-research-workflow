#!/usr/bin/env python3
# ruff: noqa: E402, TRY003, TRY301
"""Materialize a Stage 2 exact-file manifest into one isolated candidate commit."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import secrets
import zlib
from collections.abc import Sequence
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.formal_release.model import DirectoryIdentity, Finding, PreflightReport, directory_identity
from scripts.formal_release.model import StableFileReadError, read_stable_regular_bytes
from scripts.formal_release.stage2_candidate_intake import (
    GIT_OID,
    Stage2IntakeError,
    _lstat_beneath,
    _open_parent_dirfd,
    _source_bytes,
    canonical_json,
    cached_base_index,
    safe_relative,
    sha256_bytes,
    validate_stage0_and_stage1_bindings,
    validate_manifest_structure,
    validate_manifest,
)
from scripts.formal_release.stage2_git_batch import (
    BaseTreeIndex,
    BoundedReadOnlyCache,
    GitBatchError,
    IntakeCacheKey,
    IntakeCacheValue,
    git_blob_oid,
    parse_raw_diff_tree_z,
)


def build_base_tree_index(repo_root: Path, base_oid: str) -> Annotated[
    BaseTreeIndex,
    "kit:non-authoritative derived_as=view "
    "fact_source=git.base_tree "
    "witness=test:test_materializer_batches_git_operations_and_preserves_modes",
]:
    """Construct the shared immutable index with one recursive ls-tree call."""
    return BaseTreeIndex.from_repo(repo_root, base_oid)


CHECKER = "stage2-candidate-materializer"
CANDIDATE_STRATEGY = "REMEDIATION_INCLUSIVE_RELEASE"
CANDIDATE_REF = "refs/heads/stage2/exact-candidate"
COMMIT_IDENTITY_NAME = "MRW Stage 2 Candidate Bot"
COMMIT_IDENTITY_EMAIL = "stage2-candidate-bot@localhost"
COMMIT_TIMESTAMP = "2026-01-01T00:00:00+00:00"
COMMIT_MESSAGE = """Stage 2: materialize exact remediation candidate

Materialized from a per-file canonical intake manifest.
X-Stage2-Candidate=REMEDIATION_INCLUSIVE_RELEASE
"""
GIT_RUNTIME_OPTIONS = (
    "-c",
    f"core.hooksPath={os.devnull}",
    "-c",
    "core.fsmonitor=false",
)


class Stage2MaterializeError(RuntimeError):
    """Raised when the isolated candidate cannot be materialized exactly."""


GenerationError = Stage2MaterializeError


@dataclass(frozen=True)
class ObjectStoreBaseline:
    """Non-authoritative target object-store receipt used for rollback only."""

    store: Path
    files: Mapping[str, tuple[int, int]]
    directories: Mapping[str, tuple[int, int]]

    @property
    def identities(self) -> set[tuple[int, int]]:
        return {
            identity
            for values in (self.files.values(), self.directories.values())
            for identity in values
        }


def _wrap(exc: Exception) -> Stage2MaterializeError:
    if isinstance(exc, Stage2MaterializeError):
        return exc
    return Stage2MaterializeError(str(exc))


def _git_env(*, index_file: Path | None = None) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    if index_file is not None:
        environment["GIT_INDEX_FILE"] = str(index_file)
    return environment


def _git(repo_root: Path, *args: str, stdin: bytes | None = None, index_file: Path | None = None) -> bytes:
    try:
        completed = subprocess.run(
            (
                "git",
                f"--git-dir={_repo_git_dir(repo_root)}",
                f"--work-tree={repo_root}",
                *GIT_RUNTIME_OPTIONS,
                *args,
            ),
            cwd=repo_root,
            input=stdin,
            capture_output=True,
            env=_git_env(index_file=index_file),
            check=False,
        )
        if completed.returncode:
            error = completed.stderr.decode("utf-8", errors="replace").strip() or (
                f"git {' '.join(args)} exited {completed.returncode}"
            )
            raise Stage2MaterializeError(error)
        else:
            return completed.stdout
    except OSError as exc:
        raise Stage2MaterializeError(str(exc)) from exc


def _git_str(repo_root: Path, *args: str, index_file: Path | None = None) -> str:
    return _git(repo_root, *args, index_file=index_file).decode("utf-8", errors="strict").strip()


def _git_recovery(repo_root: Path, *args: str) -> bytes:
    """Run a recovery command without the normal command hook.

    Recovery must remain available when a test or wrapper injects a failure into
    the regular `_git` path (for example, a checkout failure after CAS update).
    """
    try:
        completed = subprocess.run(
            (
                "git",
                f"--git-dir={_repo_git_dir(repo_root)}",
                f"--work-tree={repo_root}",
                *GIT_RUNTIME_OPTIONS,
                *args,
            ),
            cwd=repo_root,
            input=None,
            capture_output=True,
            env=_git_env(),
            check=False,
        )
    except OSError as exc:
        raise Stage2MaterializeError(str(exc)) from exc
    if completed.returncode:
        error = completed.stderr.decode("utf-8", errors="replace").strip() or (
            f"git {' '.join(args)} exited {completed.returncode}"
        )
        raise Stage2MaterializeError(error)
    return completed.stdout


def _git_optional_ref(repo_root: Path, ref: str) -> str:
    completed = subprocess.run(
        (
            "git",
            f"--git-dir={_repo_git_dir(repo_root)}",
            f"--work-tree={repo_root}",
            *GIT_RUNTIME_OPTIONS,
            "rev-parse",
            "--verify",
            "--quiet",
            ref,
        ),
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        env=_git_env(),
    )
    if completed.returncode == 0:
        return completed.stdout.strip()
    if completed.stderr.strip():
        raise Stage2MaterializeError(completed.stderr.strip())
    return ""


def _assert_no_executable_repo_filters(repo_root: Path, label: str) -> None:
    """Reject effective repository/worktree filter commands before status."""
    completed = subprocess.run(
        (
            "git",
            f"--git-dir={_repo_git_dir(repo_root)}",
            f"--work-tree={repo_root}",
            *GIT_RUNTIME_OPTIONS,
            "config",
            "--includes",
            "--null",
            "--name-only",
            "--get-regexp",
            r"^filter\.",
        ),
        cwd=repo_root,
        check=False,
        capture_output=True,
        env=_git_env(),
    )
    if completed.returncode not in {0, 1}:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise Stage2MaterializeError(
            message or f"{label} effective repository filter configuration cannot be inspected"
        )
    executable_suffixes = (".clean", ".smudge", ".process")
    configured = tuple(
        name.decode("utf-8", errors="surrogateescape")
        for name in completed.stdout.split(b"\0")
        if name and name.decode("utf-8", errors="surrogateescape").casefold().endswith(
            executable_suffixes
        )
    )
    if configured:
        raise Stage2MaterializeError(
            f"{label} effective repository executable filter configuration is forbidden: "
            f"{configured[0]}"
        )


def _repo_git_dir(repo_root: Path) -> Path:
    """Resolve git-dir without honoring caller-provided repository variables."""
    completed = subprocess.run(
        ("git", *GIT_RUNTIME_OPTIONS, "rev-parse", "--git-dir"),
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        env=_git_env(),
    )
    if completed.returncode:
        raise Stage2MaterializeError(completed.stderr.strip() or "not a git checkout")
    return (repo_root / completed.stdout.strip()).resolve()


def _assert_source_root_identity(
    source_root: Path,
    expected_identity: DirectoryIdentity | None,
) -> None:
    if expected_identity is None:
        return
    observed = directory_identity(source_root)
    if observed != expected_identity:
        raise Stage2MaterializeError("source checkout identity changed")


def _repo_metadata(
    repo_root: Path,
    *,
    expected_identity: DirectoryIdentity | None = None,
) -> tuple[Path, Path, Path, Path]:
    _assert_source_root_identity(repo_root, expected_identity)
    root = repo_root.resolve(strict=True)
    _assert_source_root_identity(root, expected_identity)
    top = Path(_git_str(root, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if top != root:
        raise Stage2MaterializeError(f"{root} is not the git checkout top-level")
    git_dir = _repo_git_dir(root)
    common = Path(_git_str(root, "rev-parse", "--git-common-dir"))
    common = (root / common).resolve()
    index = Path(_git_str(root, "rev-parse", "--git-path", "index"))
    index = (root / index).resolve() if not index.is_absolute() else index.resolve()
    if index in {git_dir, common}:
        raise Stage2MaterializeError("git index path collides with git metadata")
    return root, git_dir, common, index


def _assert_standalone_clone(repo_root: Path, common_dir: Path) -> None:
    """Reject clones whose object or history model is borrowed."""
    def marker_is_present(path: Path, label: str) -> bool:
        try:
            os.lstat(path)
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise Stage2MaterializeError(f"{label} marker is unreadable") from exc
        else:
            return True

    alternates = common_dir / "objects" / "info" / "alternates"
    if marker_is_present(alternates, "object alternates"):
        raise Stage2MaterializeError(
            f"{repo_root} is not a standalone clone: object alternates are present"
        )
    shallow = common_dir / "shallow"
    if marker_is_present(shallow, "shallow-history"):
        raise Stage2MaterializeError(
            f"{repo_root} is not a standalone clone: shallow history is present"
        )
    grafts = common_dir / "info" / "grafts"
    if marker_is_present(grafts, "history grafts"):
        raise Stage2MaterializeError(
            f"{repo_root} is not a standalone clone: history grafts are present"
        )


def _safe_realpath(path: Path, label: str) -> Path:
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise Stage2MaterializeError(f"{label} realpath is unreadable") from exc


def _safe_lstat(path: Path, label: str) -> os.stat_result:
    try:
        return os.lstat(path)
    except OSError as exc:
        raise Stage2MaterializeError(f"{label} receipt is unreadable") from exc


def _object_walk(root: Path, label: str) -> list[tuple[str, list[str], list[str]]]:
    def fail_closed(error: OSError) -> None:
        raise Stage2MaterializeError(f"{label} object-store traversal is unreadable") from error

    try:
        return list(os.walk(root, topdown=True, onerror=fail_closed, followlinks=False))
    except Stage2MaterializeError:
        raise
    except OSError as exc:
        raise Stage2MaterializeError(f"{label} object-store traversal is unreadable") from exc


def _assert_object_store_isolated(
    repo_root: Path, common_dir: Path, source_object_dir: Path
) -> Path:
    """Resolve and require a real, target-owned object store without walking it."""
    if common_dir != repo_root / ".git":
        raise Stage2MaterializeError("target common-dir is outside the standalone target")

    visible = Path(_git_str(repo_root, "rev-parse", "--git-path", "objects"))
    if not visible.is_absolute():
        visible = repo_root / visible
    try:
        os.readlink(visible)
    except FileNotFoundError as exc:
        raise Stage2MaterializeError("target object store is missing") from exc
    except OSError as exc:
        if exc.errno != errno.EINVAL:
            raise Stage2MaterializeError("target object-store link state is unreadable") from exc
    else:
        raise Stage2MaterializeError("target object store is a symlink")
    _safe_lstat(visible, "target object store")

    resolved = _safe_realpath(visible, "target object store")
    canonical = common_dir / "objects"
    if resolved != canonical:
        raise Stage2MaterializeError("target object-store realpath is not owned by the target common-dir")
    source_object_dir = _safe_realpath(source_object_dir, "source object store")
    if resolved == source_object_dir or resolved.is_relative_to(source_object_dir) or (
        source_object_dir.is_relative_to(resolved)
    ):
        raise Stage2MaterializeError("target and source object stores share ownership or are nested")
    return resolved


def _snapshot_object_store(
    root: Path,
    label: str,
    *,
    reject_hardlinks: bool,
) -> tuple[Mapping[str, tuple[int, int]], Mapping[str, tuple[int, int]]]:
    files: dict[str, tuple[int, int]] = {}
    directories: dict[str, tuple[int, int]] = {}
    root_metadata = _safe_lstat(root, f"{label} object-store")
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise Stage2MaterializeError(f"{label} object store is not a directory")
    directories["."] = (root_metadata.st_dev, root_metadata.st_ino)
    for directory, names, filenames in _object_walk(root, label):
        base = Path(directory)
        for name in (*names, *filenames):
            candidate = base / name
            metadata = _safe_lstat(candidate, f"{label} object-store")
            if stat.S_ISLNK(metadata.st_mode):
                raise Stage2MaterializeError(f"{label} object store contains a symlink")
            resolved = _safe_realpath(candidate, f"{label} object-store")
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise Stage2MaterializeError(
                    f"{label} object-store entry escapes confinement: {candidate}"
                ) from exc
            relative = candidate.relative_to(root)
            if name in names:
                if not stat.S_ISDIR(metadata.st_mode):
                    raise Stage2MaterializeError(
                        f"{label} object-store entry is not a directory: {candidate}"
                    )
                directories[relative.as_posix()] = (metadata.st_dev, metadata.st_ino)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise Stage2MaterializeError(
                    f"{label} object-store entry is not a regular file: {candidate}"
                )
            if reject_hardlinks and metadata.st_nlink > 1:
                raise Stage2MaterializeError(
                    f"{label} object-store file is hardlinked (st_nlink={metadata.st_nlink}): {candidate}"
                )
            files[relative.as_posix()] = (metadata.st_dev, metadata.st_ino)
    return (
        MappingProxyType(dict(sorted(files.items()))),
        MappingProxyType(dict(sorted(directories.items()))),
    )


def _assert_and_snapshot_object_stores(
    source_object_dir: Path, target_object_dir: Path
) -> Annotated[
    ObjectStoreBaseline,
    "kit:non-authoritative derived_as=filesystem_snapshot "
    "fact_source=target.object_store "
    "witness=test:object_store_rollback_preserves_only_baseline_objects",
]:
    """Run both object-store full walks and capture the target rollback receipt."""
    source_inodes: dict[tuple[int, int], Path] = {}
    source_files, _source_directories = _snapshot_object_store(
        source_object_dir,
        "source",
        reject_hardlinks=False,
    )
    for relative, identity in source_files.items():
        source_inodes.setdefault(identity, source_object_dir / relative)

    target_files, target_directories = _snapshot_object_store(
        target_object_dir,
        "target",
        reject_hardlinks=True,
    )
    shared = set(target_files.values()) & set(source_files.values())
    if shared:
        identity = next(iter(shared))
        raise Stage2MaterializeError(
            f"target object-store file shares an inode with source object: "
            f"{target_object_dir} -> {source_inodes[identity]}"
        )
    return ObjectStoreBaseline(
        store=target_object_dir,
        files=target_files,
        directories=target_directories,
    )


def _rollback_object_store_to_baseline(baseline: ObjectStoreBaseline) -> None:
    """Delete only new, safe target-store entries; never replace baseline state."""
    store = baseline.store
    current_files, current_directories = _snapshot_object_store(
        store,
        "target",
        reject_hardlinks=True,
    )
    for label, expected, current in (
        ("file", baseline.files, current_files),
        ("directory", baseline.directories, current_directories),
    ):
        for relative, identity in expected.items():
            if current.get(relative) != identity:
                raise Stage2MaterializeError(
                    f"rollback object-store baseline {label} identity changed: {relative}"
                )

    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )

    def remove_snapshot_entry(
        store_fd: int,
        relative: str,
        identity: tuple[int, int],
        *,
        is_directory: bool,
    ) -> None:
        parts = Path(relative).parts
        parent_fd = os.dup(store_fd)
        descriptor: int | None = None
        try:
            prefix: list[str] = []
            for component in parts[:-1]:
                prefix.append(component)
                expected_parent = current_directories.get("/".join(prefix))
                if expected_parent is None:
                    raise Stage2MaterializeError(
                        f"rollback object-store parent is unreceipted: {relative}"
                    )
                child_fd = os.open(component, directory_flags, dir_fd=parent_fd)
                os.close(parent_fd)
                parent_fd = child_fd
                opened_parent = os.fstat(parent_fd)
                if (
                    not stat.S_ISDIR(opened_parent.st_mode)
                    or (opened_parent.st_dev, opened_parent.st_ino) != expected_parent
                ):
                    raise Stage2MaterializeError(
                        f"rollback object-store parent identity changed: {relative}"
                    )

            name = parts[-1]
            metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            expected_mode = stat.S_ISDIR if is_directory else stat.S_ISREG
            if (
                not expected_mode(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or (metadata.st_dev, metadata.st_ino) != identity
                or (not is_directory and metadata.st_nlink > 1)
            ):
                raise Stage2MaterializeError(
                    f"rollback object-store identity changed: {relative}"
                )

            flags = directory_flags if is_directory else (
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            )
            descriptor = os.open(name, flags, dir_fd=parent_fd)
            opened = os.fstat(descriptor)
            if (
                not expected_mode(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != identity
            ):
                raise Stage2MaterializeError(
                    f"rollback object-store identity changed: {relative}"
                )

            if is_directory:
                os.rmdir(name, dir_fd=parent_fd)
            else:
                os.unlink(name, dir_fd=parent_fd)
        except Stage2MaterializeError:
            raise
        except OSError as exc:
            raise Stage2MaterializeError(
                f"object-store rollback failed: {relative}"
            ) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(parent_fd)

    try:
        store_fd = os.open(store, directory_flags)
    except OSError as exc:
        raise Stage2MaterializeError("target object store cannot be opened safely") from exc
    try:
        opened_store = os.fstat(store_fd)
        if (opened_store.st_dev, opened_store.st_ino) != baseline.directories["."]:
            raise Stage2MaterializeError(
                "rollback object-store baseline directory identity changed: ."
            )
        for relative, identity in current_files.items():
            if relative in baseline.files:
                continue
            remove_snapshot_entry(store_fd, relative, identity, is_directory=False)

        for relative in sorted(
            current_directories,
            key=lambda item: (item.count("/"), item),
            reverse=True,
        ):
            if relative in baseline.directories or relative == ".":
                continue
            remove_snapshot_entry(
                store_fd,
                relative,
                current_directories[relative],
                is_directory=True,
            )
    finally:
        os.close(store_fd)

    restored_files, restored_directories = _snapshot_object_store(
        store,
        "target",
        reject_hardlinks=True,
    )
    if restored_files != baseline.files or restored_directories != baseline.directories:
        raise Stage2MaterializeError("object-store rollback receipt does not match baseline")


def _is_explicit_example_path(lowered_path: str, parts: set[str]) -> bool:
    example_components = {
        "example", "examples", "fixture", "fixtures", "sample", "samples",
        "template", "templates",
    }
    if any(part in example_components for part in parts):
        return True
    return lowered_path.endswith((".example", ".sample", ".template", ".tpl", ".tmpl"))


def _dangerous_ignored(path: str) -> bool:
    lowered = path.casefold()
    parts = set(Path(lowered).parts)
    dangerous_components = {
        ".cache", "cache", "caches", "__pycache__", ".pytest_cache", ".mypy_cache",
        ".ruff_cache", "tmp", "temp", "runtime", "node_modules", "dist", "build", "target",
    }
    if any(part in dangerous_components for part in parts):
        return True
    if any(
        part.startswith(".env")
        or any(secret in part for secret in ("secret", "token", "credential", "password"))
        for part in parts
    ):
        return True
    if _is_explicit_example_path(lowered, parts):
        return False
    credential_files = {
        ".authinfo", ".git-credentials", ".htpasswd", ".netrc", ".npmrc",
        ".pgpass", ".pypirc", "_netrc",
    }
    private_key_files = {
        "id_dsa", "id_ecdsa", "id_ed25519", "id_ed25519_sk", "id_ed25519_sk_rk",
        "id_rsa",
    }
    name = Path(lowered).name
    if name in credential_files:
        return True
    if ".ssh" in parts and name in private_key_files:
        return True
    if ".docker" in parts and name == "config.json":
        return True
    if ".kube" in parts and name == "config":
        return True
    return lowered.endswith((".db", ".sqlite", ".sqlite3", ".sqlitedb", ".pem", ".key", ".p12", ".pfx"))


def _assert_clean(repo_root: Path, label: str) -> None:
    porcelain = _git(repo_root, "status", "--porcelain=v1", "-z", "--ignored", "--untracked-files=all")
    for record in porcelain.split(b"\0"):
        if not record:
            continue
        text = record.decode("utf-8", errors="surrogateescape")
        if text.startswith("!! "):
            ignored = text[3:]
            if _dangerous_ignored(ignored):
                raise Stage2MaterializeError(f"{label} contains dangerous ignored path: {ignored}")
            continue
        raise Stage2MaterializeError(f"{label} has tracked or untracked changes")
    flags = _git(repo_root, "ls-files", "-v", "-z")
    for record in flags.split(b"\0"):
        if not record:
            continue
        marker = chr(record[0])
        if marker == "S" or marker.islower():
            path = record[2:].decode("utf-8", errors="surrogateescape")
            raise Stage2MaterializeError(f"{label} has assume-unchanged or skip-worktree flag: {path}")


def _restore_manifest_snapshot_modes(
    target_root: Path,
    manifest: Mapping[str, Any],
    *,
    expected_identity: DirectoryIdentity,
) -> None:
    """Restore the runtime immutability that Git tree modes cannot encode."""
    closure_rows = (
        *manifest["stage0_b23"]["closure"],
        *manifest["stage1"]["closure"],
    )
    snapshot_paths = tuple(
        sorted(
            {
                relative
                for row in closure_rows
                if row["operation"] == "UPSERT"
                and (relative := safe_relative(row["path"])).parent.name == "snapshots"
            },
            key=Path.as_posix,
        )
    )
    for relative in snapshot_paths:
        parent_fd = _open_parent_dirfd(
            target_root,
            relative,
            expected_identity=expected_identity,
        )
        descriptor: int | None = None
        try:
            descriptor = os.open(
                relative.name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent_fd,
            )
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise Stage2MaterializeError(
                    f"candidate snapshot is not a regular file: {relative.as_posix()}"
                )
            if metadata.st_nlink != 1:
                raise Stage2MaterializeError(
                    f"candidate snapshot must have exactly one link: {relative.as_posix()}"
                )
            os.fchmod(descriptor, 0o444)
            if os.fstat(descriptor).st_mode & 0o222:
                raise Stage2MaterializeError(
                    f"candidate snapshot remains writable: {relative.as_posix()}"
                )
        except OSError as exc:
            raise Stage2MaterializeError(
                f"candidate snapshot mode cannot be restored: {relative.as_posix()}: {exc}"
            ) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(parent_fd)


def _source_fingerprint(
    source_root: Path,
    source: dict[str, Any],
) -> dict[str, Any]:
    """Recheck the manifest's source identity and porcelain receipt cheaply."""
    _assert_source_root_identity(source_root, (int(source["dev"]), int(source["ino"])))
    head = _git_str(source_root, "rev-parse", "HEAD")
    base = _git_str(source_root, "rev-parse", "--verify", source["base_ref"])
    remote = _git_str(source_root, "remote", "get-url", source["remote_name"])
    # Match intake's canonical receipt exactly (ignored files are excluded).
    porcelain = _git(source_root, "status", "--porcelain=v1", "--untracked-files=all", "-z")
    if head != source["head"] or base != source["base_oid"] or remote != source["remote"]:
        raise Stage2MaterializeError("manifest source or base identity drift")
    if hashlib.sha256(porcelain).hexdigest() != source["porcelain_sha256"]:
        raise Stage2MaterializeError("source porcelain status digest drift")
    if (porcelain == b"") is not bool(source["source_clean"]):
        raise Stage2MaterializeError("source_clean precondition drift")
    return {
        "checkout": source_root.as_posix(),
        "dev": int(source["dev"]),
        "ino": int(source["ino"]),
        "head": head,
        "porcelain_sha256": source["porcelain_sha256"],
        "base_oid": base,
        "object_format": _git_str(source_root, "rev-parse", "--show-object-format"),
    }


def _assert_source_fingerprint(source_root: Path, source: dict[str, Any]) -> None:
    _source_fingerprint(source_root, source)


def _write_loose_objects(object_store: Path, blobs: dict[str, bytes]) -> None:
    """Install target-owned loose blob objects without replacing existing files."""
    store_fd: int | None = None
    try:
        store_fd = os.open(object_store, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        if not stat.S_ISDIR(os.fstat(store_fd).st_mode):
            os.close(store_fd)
            store_fd = None
            raise Stage2MaterializeError("target object store is not a directory")
    except OSError as exc:
        if store_fd is not None:
            os.close(store_fd)
        raise Stage2MaterializeError("target object store cannot be opened safely") from exc
    try:
        for oid, payload in blobs.items():
            if GIT_OID.fullmatch(oid) is None or git_blob_oid(payload) != oid:
                raise Stage2MaterializeError(f"source git blob drift: {oid}")
            prefix_name, object_name = oid[:2], oid[2:]
            try:
                os.mkdir(prefix_name, mode=0o755, dir_fd=store_fd)
            except FileExistsError:
                pass
            prefix_fd = os.open(
                prefix_name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=store_fd,
            )
            try:
                prefix_is_dir = stat.S_ISDIR(os.fstat(prefix_fd).st_mode)
            except OSError:
                os.close(prefix_fd)
                raise
            if not prefix_is_dir:
                os.close(prefix_fd)
                raise Stage2MaterializeError(f"git object prefix is not a directory: {oid}")
            temp_name: str | None = None
            temp_fd: int | None = None
            try:
                try:
                    existing_fd = os.open(object_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=prefix_fd)
                except FileNotFoundError:
                    existing_fd = None
                if existing_fd is not None:
                    try:
                        before = os.fstat(existing_fd)
                        if not stat.S_ISREG(before.st_mode):
                            raise Stage2MaterializeError(f"existing git object is not regular: {oid}")
                        chunks: list[bytes] = []
                        while chunk := os.read(existing_fd, 1024 * 1024):
                            chunks.append(chunk)
                        after = os.fstat(existing_fd)
                        if (before.st_dev, before.st_ino, before.st_size) != (
                            after.st_dev,
                            after.st_ino,
                            sum(map(len, chunks)),
                        ):
                            raise Stage2MaterializeError(f"existing git object changed during read: {oid}")
                        try:
                            encoded = zlib.decompress(b"".join(chunks))
                        except zlib.error as exc:
                            raise Stage2MaterializeError(f"existing git object is corrupt: {oid}") from exc
                        if encoded != b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload:
                            raise Stage2MaterializeError(f"existing git object is corrupt: {oid}")
                        continue
                    finally:
                        os.close(existing_fd)
                compressed = zlib.compress(b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload)
                for _attempt in range(8):
                    candidate = f".{object_name}.{secrets.token_hex(8)}"
                    try:
                        temp_fd = os.open(
                            candidate,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                            0o600,
                            dir_fd=prefix_fd,
                        )
                    except FileExistsError:
                        continue
                    temp_name = candidate
                    break
                else:
                    raise Stage2MaterializeError(f"cannot allocate temporary git object: {oid}")
                with os.fdopen(temp_fd, "wb", closefd=True) as handle:
                    temp_fd = None
                    handle.write(compressed)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.link(temp_name, object_name, src_dir_fd=prefix_fd, dst_dir_fd=prefix_fd)
                except FileExistsError:
                    check_fd = os.open(object_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=prefix_fd)
                    try:
                        encoded = zlib.decompress(os.read(check_fd, 64 * 1024 * 1024))
                    finally:
                        os.close(check_fd)
                    if encoded != b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload:
                        raise Stage2MaterializeError(f"existing git object is corrupt: {oid}") from None
                else:
                    directory_fd = os.dup(prefix_fd)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
            except OSError as exc:
                raise Stage2MaterializeError(f"cannot install git object {oid}: {exc}") from exc
            finally:
                if temp_fd is not None:
                    os.close(temp_fd)
                if temp_name is not None:
                    try:
                        os.unlink(temp_name, dir_fd=prefix_fd)
                    except FileNotFoundError:
                        pass
                os.close(prefix_fd)
    finally:
        os.close(store_fd)


def _cat_file_batch(repo_root: Path, oids: Sequence[str], expected: dict[str, bytes] | None = None) -> None:
    if not oids:
        return
    request = b"".join(f"{oid}\n".encode("ascii") for oid in oids)
    output = _git(repo_root, "cat-file", "--batch", stdin=request)
    offset = 0
    for oid in oids:
        header_end = output.find(b"\n", offset)
        if header_end < 0:
            raise Stage2MaterializeError("git cat-file batch receipt truncated")
        header = output[offset:header_end].decode("ascii", errors="strict").split()
        offset = header_end + 1
        if len(header) != 3 or header[0] != oid or header[1] != "blob":
            raise Stage2MaterializeError(f"git blob receipt mismatch: {oid}")
        try:
            size = int(header[2])
        except ValueError as exc:
            raise Stage2MaterializeError(f"git blob receipt size invalid: {oid}") from exc
        payload = output[offset:offset + size]
        if len(payload) != size or output[offset + size:offset + size + 1] != b"\n":
            raise Stage2MaterializeError(f"git cat-file batch receipt truncated: {oid}")
        if expected is not None:
            wanted = expected.get(oid)
            if wanted is None or payload != wanted or git_blob_oid(payload) != oid:
                raise Stage2MaterializeError(f"git blob receipt content mismatch: {oid}")
        offset += size + 1
    if output[offset:]:
        raise Stage2MaterializeError("git cat-file batch receipt has trailing bytes")


def _verify_prepared_blobs_with_git(
    repo_root: Path,
    source_root: Path,
    prepared: Sequence[tuple[dict[str, str], bytes | None, str | None]],
) -> None:
    """Run one SHA1_DC-backed Git hash pass over every prepared UPSERT."""
    upserts = tuple(item for item in prepared if item[0]["operation"] == "UPSERT")
    if not upserts:
        return
    request_paths: list[bytes] = []
    with tempfile.TemporaryDirectory(prefix="mrw-stage2-hash-") as temp_name:
        fallback_root = Path(temp_name)
        for index, (row, payload, mode) in enumerate(upserts):
            assert payload is not None and mode is not None
            relative = safe_relative(row["path"])
            source_path = source_root / relative
            encoded_source_path = os.fsencode(source_path)
            if mode != "120000" and b"\n" not in encoded_source_path:
                hash_path = encoded_source_path
            else:
                fallback = fallback_root / str(index)
                fallback.write_bytes(payload)
                hash_path = os.fsencode(fallback)
            if b"\n" in hash_path:
                raise Stage2MaterializeError("git hash-object batch path is not line-safe")
            request_paths.append(hash_path)

        output = _git(
            repo_root,
            "hash-object",
            "--stdin-paths",
            "--no-filters",
            stdin=b"\n".join(request_paths) + b"\n",
        )
    raw_oids = output.splitlines()
    if len(raw_oids) != len(upserts):
        raise Stage2MaterializeError("git hash-object batch receipt count mismatch")
    for (row, _payload, _mode), raw_oid in zip(upserts, raw_oids, strict=True):
        try:
            oid = raw_oid.decode("ascii")
        except UnicodeDecodeError as exc:
            raise Stage2MaterializeError("git hash-object batch receipt is malformed") from exc
        if GIT_OID.fullmatch(oid) is None or oid != row["blob"]:
            raise Stage2MaterializeError(f"git hash-object blob mismatch: {row['path']}")


def _read_upsert(
    source_root: Path,
    row: dict[str, str],
    *,
    expected_identity: DirectoryIdentity | None = None,
) -> tuple[bytes, str]:
    relative = safe_relative(row["path"])
    source_mode = stat.S_IFLNK if row["mode"] == "120000" else stat.S_IFREG
    if row["mode"] == "100755":
        source_mode |= 0o755
    elif row["mode"] == "100644":
        source_mode |= 0o644
    try:
        payload, mode = _source_bytes(
            source_root,
            relative,
            source_mode,
            expected_identity=expected_identity,
        )
    except Stage2IntakeError as exc:
        raise Stage2MaterializeError(str(exc)) from exc
    if mode == "120000":
        _assert_source_root_identity(source_root, expected_identity)
        target = Path(payload.decode("utf-8"))
        lexical_target = Path(os.path.normpath((relative.parent / target).as_posix()))
        if (
            target.is_absolute()
            or lexical_target.is_absolute()
            or any(part == ".." for part in lexical_target.parts)
            or not (source_root / relative).resolve().is_relative_to(source_root.resolve())
        ):
            raise Stage2MaterializeError(f"symlink escapes checkout: {relative.as_posix()}")
    if mode != row["mode"] or sha256_bytes(payload) != row["sha256"]:
        raise Stage2MaterializeError(f"source mode or sha256 drift: {relative.as_posix()}")
    return payload, mode


def _assert_delete_source_absent(
    source_root: Path,
    relative: Path,
    *,
    expected_identity: DirectoryIdentity,
) -> None:
    """Require DELETE input absence beneath the stable source-root binding."""
    try:
        _lstat_beneath(
            source_root,
            relative,
            expected_identity=expected_identity,
        )
    except FileNotFoundError:
        return
    except (OSError, Stage2IntakeError) as exc:
        raise Stage2MaterializeError(
            f"delete source cannot be checked safely: {relative.as_posix()}"
        ) from exc
    raise Stage2MaterializeError(f"delete source still exists: {relative.as_posix()}")


def _delta(repo_root: Path, base_oid: str, tree_oid: str) -> dict[str, dict[str, str]]:
    try:
        parsed = parse_raw_diff_tree_z(
            _git(
                repo_root,
                "diff-tree",
                "-r",
                "--no-renames",
                "--raw",
                "--no-commit-id",
                "-z",
                base_oid,
                tree_oid,
            )
        )
    except GitBatchError as exc:
        raise Stage2MaterializeError(f"candidate raw delta is invalid: {exc}") from exc
    return {
        path: {
            "base_mode": row.base_mode,
            "base_blob": row.base_blob,
            "mode": row.mode,
            "blob": row.blob,
        }
        for path, row in parsed.items()
    }


def _commit_tree(repo_root: Path, tree_oid: str, parent_oid: str) -> str:
    environment = _git_env()
    environment.update(
        {
            "GIT_AUTHOR_NAME": COMMIT_IDENTITY_NAME,
            "GIT_AUTHOR_EMAIL": COMMIT_IDENTITY_EMAIL,
            "GIT_AUTHOR_DATE": COMMIT_TIMESTAMP,
            "GIT_COMMITTER_NAME": COMMIT_IDENTITY_NAME,
            "GIT_COMMITTER_EMAIL": COMMIT_IDENTITY_EMAIL,
            "GIT_COMMITTER_DATE": COMMIT_TIMESTAMP,
        }
    )
    completed = subprocess.run(
        (
            "git",
            f"--git-dir={_repo_git_dir(repo_root)}",
            f"--work-tree={repo_root}",
            *GIT_RUNTIME_OPTIONS,
            "commit-tree",
            tree_oid,
            "-p",
            parent_oid,
            "-m",
            COMMIT_MESSAGE,
        ),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if completed.returncode != 0:
        raise Stage2MaterializeError(completed.stderr.strip() or "git commit-tree failed")
    return completed.stdout.strip()


def _raw_commit_parents(repo_root: Path, commit_oid: str) -> tuple[str, ...]:
    """Read parent OIDs from the stored commit header without revision rewriting."""
    payload = _git(repo_root, "cat-file", "commit", commit_oid)
    header, separator, _message = payload.partition(b"\n\n")
    if not separator or b"\0" in header:
        raise Stage2MaterializeError("candidate commit header is malformed")
    trees: list[str] = []
    parents: list[str] = []
    for line in header.split(b"\n"):
        if line.startswith(b" "):
            continue
        key, delimiter, raw_value = line.partition(b" ")
        if not delimiter or not key or not raw_value:
            raise Stage2MaterializeError("candidate commit header is malformed")
        if key not in {b"tree", b"parent"}:
            continue
        try:
            value = raw_value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise Stage2MaterializeError("candidate commit header is malformed") from exc
        if GIT_OID.fullmatch(value) is None:
            raise Stage2MaterializeError("candidate commit header is malformed")
        if key == b"tree":
            trees.append(value)
        else:
            parents.append(value)
    if len(trees) != 1:
        raise Stage2MaterializeError("candidate commit header is malformed")
    return tuple(parents)


def _restore_candidate_ref(repo_root: Path, old_ref: str, commit_oid: str) -> None:
    """Restore the exact pre-CAS candidate-ref state."""
    if old_ref == "0" * 40:
        _git_recovery(repo_root, "update-ref", "-d", CANDIDATE_REF, commit_oid)
    else:
        _git_recovery(repo_root, "update-ref", CANDIDATE_REF, old_ref, commit_oid)


def materialize_candidate(
    *,
    target_root: Path,
    source_root: Path,
    manifest: dict[str, Any],
    read_cache: BoundedReadOnlyCache[IntakeCacheKey, IntakeCacheValue] | None = None,
) -> dict[str, str]:
    try:
        # Structure-only validation must precede any live source reads.
        validate_manifest_structure(manifest)
        source = manifest["source"]
        source_identity = (int(source["dev"]), int(source["ino"]))
    except (Stage2IntakeError, KeyError, TypeError, ValueError) as exc:
        raise Stage2MaterializeError(str(exc)) from exc
    try:
        manifest_source_root = Path(source["checkout"]).resolve(strict=True)
    except (KeyError, OSError, TypeError) as exc:
        raise Stage2MaterializeError("manifest source checkout is not resolvable") from exc
    if manifest_source_root != source_root.resolve(strict=True):
        raise Stage2MaterializeError("source checkout top-level identity drift")
    _assert_source_root_identity(source_root, source_identity)
    source_root, source_git, source_common, source_index = _repo_metadata(
        source_root,
        expected_identity=source_identity,
    )
    target_root, target_git, target_common, target_index = _repo_metadata(target_root)
    target_identity = directory_identity(target_root)
    source_object = Path(_git_str(source_root, "rev-parse", "--git-path", "objects"))
    if not source_object.is_absolute():
        source_object = source_root / source_object
    source_object = source_object.resolve(strict=True)
    _assert_standalone_clone(target_root, target_common)
    if source_root == target_root:
        raise Stage2MaterializeError("target must be an isolated checkout, not the source checkout")
    if source_root.is_relative_to(target_root) or target_root.is_relative_to(source_root):
        raise Stage2MaterializeError("source and target realpaths must not be nested")
    target_object = _assert_object_store_isolated(target_root, target_common, source_object)
    if target_git == source_git or target_common == source_common or target_index == source_index:
        raise Stage2MaterializeError("target shares git-dir, common-dir, or index with source")
    if target_common == source_git or target_git == source_common:
        raise Stage2MaterializeError("linked worktree is not an isolated standalone clone")
    _assert_no_executable_repo_filters(source_root, "source")
    _assert_no_executable_repo_filters(target_root, "target")
    current_source_fingerprint = _source_fingerprint(source_root, source)
    _assert_clean(target_root, "target checkout")
    detached = subprocess.run(
        (
            "git",
            f"--git-dir={target_git}",
            f"--work-tree={target_root}",
            *GIT_RUNTIME_OPTIONS,
            "symbolic-ref",
            "-q",
            "HEAD",
        ),
        cwd=target_root,
        check=False,
        capture_output=True,
        env=_git_env(),
    )
    if detached.returncode == 0:
        raise Stage2MaterializeError("target HEAD must be detached")
    target_head = _git_str(target_root, "rev-parse", "HEAD")
    if target_head != source["base_oid"]:
        raise Stage2MaterializeError("target HEAD is not the manifest base commit")
    target_remote = _git_str(target_root, "remote", "get-url", source["remote_name"])
    target_base = _git_str(target_root, "rev-parse", "--verify", source["base_ref"])
    if target_remote != source["remote"] or target_base != source["base_oid"]:
        raise Stage2MaterializeError("target remote or base ref identity drift")

    existing_ref = _git_optional_ref(target_root, CANDIDATE_REF)
    if existing_ref and existing_ref != source["base_oid"]:
        raise Stage2MaterializeError("candidate ref precondition is not the manifest base")

    # All cheap environment preconditions are now checked. The object proof is
    # still write-blocking, but must follow cheap preflight and precede every
    # semantic validator and every object/index/ref mutation.
    object_baseline = _assert_and_snapshot_object_stores(source_object, target_object)

    # Snapshot the base tree once; both intake closure checks and entry checks
    # consume this immutable mapping without issuing per-path ls-tree calls.
    base_index = (
        cached_base_index(manifest, current_source_fingerprint, read_cache)
        if read_cache is not None
        else None
    )
    if base_index is None:
        base_index = build_base_tree_index(target_root, source["base_oid"])

    # Expensive semantic validators run only after all cheap environment checks.
    try:
        validate_manifest(manifest, base_index=base_index)
        validate_stage0_and_stage1_bindings(
            manifest,
            source_root,
            expected_identity=source_identity,
            base_index=base_index,
        )
    except Stage2IntakeError as exc:
        raise Stage2MaterializeError(str(exc)) from exc

    prepared: list[tuple[dict[str, str], bytes | None, str | None]] = []
    delete_relatives: list[Path] = []
    expected_delta: dict[str, dict[str, str]] = {}
    blobs: dict[str, bytes] = {}
    for row in manifest["entries"]:
        relative = safe_relative(row["path"])
        base_entry = base_index.get(relative.as_posix())
        if base_entry is None:
            base_mode, base_blob = "000000", ""
        else:
            base_mode, base_blob = base_entry.mode, base_entry.oid
        if base_mode != row["base_mode"] or base_blob != row["base_blob"]:
            raise Stage2MaterializeError(f"base precondition drift: {relative.as_posix()}")
        if row["operation"] == "DELETE":
            _assert_delete_source_absent(
                source_root,
                relative,
                expected_identity=source_identity,
            )
            delete_relatives.append(relative)
            prepared.append((row, None, None))
            expected_delta[row["path"]] = {
                "base_mode": row["base_mode"], "base_blob": row["base_blob"], "mode": "000000", "blob": ""
            }
            continue
        payload, mode = _read_upsert(source_root, row, expected_identity=source_identity)
        blob = git_blob_oid(payload)
        if blob != row["blob"]:
            raise Stage2MaterializeError(f"source git blob drift: {relative.as_posix()}")
        blobs.setdefault(blob, payload)
        prepared.append((row, payload, mode))
        if (row["base_mode"], row["base_blob"]) != (row["mode"], row["blob"]):
            expected_delta[row["path"]] = {
                "base_mode": row["base_mode"], "base_blob": row["base_blob"], "mode": row["mode"], "blob": row["blob"]
            }

    # Reconfirm DELETE absence after all payload reads. Ignored paths are not in
    # porcelain, so the final source fingerprint cannot replace this witness.
    for relative in delete_relatives:
        _assert_delete_source_absent(
            source_root,
            relative,
            expected_identity=source_identity,
        )

    # Verify the source did not move while semantic inputs and payloads were read.
    _assert_source_fingerprint(source_root, source)
    _verify_prepared_blobs_with_git(target_root, source_root, prepared)
    fd, temp_index_name = tempfile.mkstemp(prefix=".stage2-index-", dir=target_root.parent)
    os.close(fd)
    temp_index = Path(temp_index_name)
    cas_updated = False
    old_ref = existing_ref or "0" * 40
    tree_oid = ""
    commit_oid = ""
    try:
        _write_loose_objects(target_object, blobs)
        _cat_file_batch(target_root, tuple(blobs), blobs)
        _git(target_root, "read-tree", source["base_oid"], index_file=temp_index)
        index_records: list[bytes] = []
        for row, payload, mode in prepared:
            relative = safe_relative(row["path"])
            if row["operation"] == "DELETE":
                index_records.append(f"0 {('0' * 40)}\t{relative.as_posix()}\0".encode())
            else:
                assert payload is not None and mode is not None
                index_records.append(f"{mode} {row['blob']}\t{relative.as_posix()}\0".encode())
        if index_records:
            _git(
                target_root,
                "update-index",
                "-z",
                "--index-info",
                stdin=b"".join(index_records),
                index_file=temp_index,
            )
        tree_oid = _git_str(target_root, "write-tree", index_file=temp_index)
        delta = _delta(target_root, source["base_oid"], tree_oid)
        if delta != expected_delta:
            raise Stage2MaterializeError("candidate delta is not exactly equal to the manifest")
        commit_oid = _commit_tree(target_root, tree_oid, source["base_oid"])
        _git(target_root, "update-ref", CANDIDATE_REF, commit_oid, old_ref)
        cas_updated = True
        if GIT_OID.fullmatch(commit_oid) is None:
            raise Stage2MaterializeError("candidate commit oid is invalid")
        parent = _raw_commit_parents(target_root, commit_oid)
        if parent != (source["base_oid"],):
            raise Stage2MaterializeError("candidate commit parent set is not exactly the base")
        if _git_str(target_root, "rev-list", "--count", f"{source['base_oid']}..{commit_oid}") != "1":
            raise Stage2MaterializeError("candidate is not exactly one commit after base")
        _git(target_root, "checkout", "--detach", commit_oid)
        _git(target_root, "reset", "--hard", commit_oid)
        _restore_manifest_snapshot_modes(
            target_root,
            manifest,
            expected_identity=target_identity,
        )
        _assert_clean(target_root, "candidate checkout")
        actual_tree = _git_str(target_root, "rev-parse", f"{commit_oid}^{{tree}}")
        if actual_tree != tree_oid:
            raise Stage2MaterializeError("candidate commit tree drift")
        try:
            temp_index.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise Stage2MaterializeError(
                f"temporary index cleanup failed: {exc}"
            ) from exc
    except Exception as exc:
        cleanup_error: Exception | None = None
        try:
            temp_index.unlink()
        except FileNotFoundError:
            pass
        except OSError as cleanup_exc:
            cleanup_error = cleanup_exc
        if not cas_updated:
            object_rollback_error: Exception | None = None
            try:
                _rollback_object_store_to_baseline(object_baseline)
            except Exception as rollback_exc:
                object_rollback_error = rollback_exc
            if cleanup_error is not None or object_rollback_error is not None:
                rollback_details = [
                    detail
                    for detail in (
                        None if cleanup_error is None else f"temporary index cleanup failed: {cleanup_error}",
                        None if object_rollback_error is None else f"object rollback failed: {object_rollback_error}",
                    )
                    if detail is not None
                ]
                raise Stage2MaterializeError(
                    "candidate pre-CAS materialization failed: "
                    f"{exc}; rollback incomplete: {'; '.join(rollback_details)}"
                ) from exc
            raise
        # The candidate ref has already been CAS-updated. Restore both that ref
        # and the original detached base before surfacing the failure.
        rollback_errors: list[str] = []
        ref_rollback_succeeded = True
        checkout_rollback_succeeded = True
        try:
            _restore_candidate_ref(target_root, old_ref, commit_oid)
        except Exception as rollback_exc:  # pragma: no cover - defensive path
            rollback_errors.append(f"ref rollback failed: {rollback_exc}")
            ref_rollback_succeeded = False
        try:
            _git_recovery(target_root, "checkout", "--detach", target_head)
            _git_recovery(target_root, "reset", "--hard", target_head)
        except Exception as rollback_exc:  # pragma: no cover - defensive path
            rollback_errors.append(f"checkout rollback failed: {rollback_exc}")
            checkout_rollback_succeeded = False
        if ref_rollback_succeeded and checkout_rollback_succeeded:
            try:
                _rollback_object_store_to_baseline(object_baseline)
            except Exception as rollback_exc:
                rollback_errors.append(f"object rollback failed: {rollback_exc}")
        else:
            rollback_errors.append("object rollback deferred to preserve referenced objects")
        if cleanup_error is not None:
            rollback_errors.append(f"temporary index cleanup failed: {cleanup_error}")
        suffix = (
            f"; rollback incomplete: {'; '.join(rollback_errors)}"
            if rollback_errors
            else "; rollback complete"
        )
        raise Stage2MaterializeError(f"candidate post-CAS materialization failed: {exc}{suffix}") from exc
    return {
        "base": source["base_oid"],
        "parent": source["base_oid"],
        "commit": commit_oid,
        "tree": tree_oid,
        "ref": CANDIDATE_REF,
        "strategy": CANDIDATE_STRATEGY,
    }


def _failure_report(message: str) -> PreflightReport:
    return PreflightReport(CHECKER, (Finding("stage2_candidate_materializer", "FAIL", message),))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        raw = read_stable_regular_bytes(args.manifest, label="candidate intake manifest")
        if raw != canonical_json(json.loads(raw)) + b"\n":
            raise Stage2MaterializeError("manifest is not canonical JSON")
        result = materialize_candidate(
            target_root=args.target_root,
            source_root=args.source_root,
            manifest=json.loads(raw),
        )
    except (
        Stage2MaterializeError,
        Stage2IntakeError,
        StableFileReadError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        print(_failure_report(str(exc)).to_json(), end="")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
