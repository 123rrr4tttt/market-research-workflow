# ruff: noqa: TRY003
"""Batch Git primitives used by Stage 2 candidate intake.

The index is deliberately read-only: it snapshots one base tree with a single
``git ls-tree`` invocation and never consults Git again during lookups.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections import OrderedDict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
import unicodedata
from pathlib import Path
from types import MappingProxyType
from typing import Any, Generic, TypeVar


class GitBatchError(RuntimeError):
    """Raised when a Git batch response cannot be trusted."""


SHA1_RE = re.compile(rb"^[0-9a-f]{40}$")
MODE_RE = re.compile(rb"^[0-7]{6}$")
_ZERO_SHA1 = "0" * 40
_GIT_RUNTIME_OPTIONS = (
    "-c",
    "core.fsmonitor=false",
    "-c",
    f"core.hooksPath={os.devnull}",
)


@dataclass(frozen=True)
class BaseTreeEntry:
    mode: str
    kind: str
    oid: str


def _git_env() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    return environment


def _run_git(repo_root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ("git", *_GIT_RUNTIME_OPTIONS, "-C", str(repo_root), *args),
        check=False,
        capture_output=True,
        env=_git_env(),
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise GitBatchError(detail or f"git {' '.join(args)} exited {completed.returncode}")
    return completed.stdout


def _validate_path(path_bytes: bytes) -> str:
    try:
        path = path_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GitBatchError("git ls-tree path is not UTF-8") from exc
    if not path or path.startswith("/") or "\x00" in path:
        raise GitBatchError("git ls-tree path is empty or absolute")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise GitBatchError(f"git ls-tree path is not canonical: {path}")
    if path != unicodedata.normalize("NFC", path):
        raise GitBatchError(f"git ls-tree path is not NFC-normalized: {path}")
    return path


@dataclass(frozen=True)
class RawDiffTreeEntry:
    """Canonical metadata for one raw ``diff-tree --raw -z`` pair."""

    base_mode: str
    base_blob: str
    mode: str
    blob: str


def parse_raw_diff_tree_z(output: bytes) -> dict[str, RawDiffTreeEntry]:
    """Strictly parse ``diff-tree --raw --no-commit-id -z`` output.

    Empty output is the only non-NUL-terminated response allowed: Git uses it
    for an empty delta. Every other response must be exact NUL-separated
    metadata/path pairs.
    """
    if not isinstance(output, bytes):
        raise GitBatchError("git diff-tree response is not bytes")
    if output == b"":
        return {}
    if not output.endswith(b"\0"):
        raise GitBatchError("git diff-tree response is not NUL terminated")

    entries: dict[str, RawDiffTreeEntry] = {}
    records = output[:-1].split(b"\0")
    index = 0
    while index < len(records):
        metadata = records[index]
        index += 1
        if index >= len(records):
            if metadata.startswith(b":") and metadata[1:].split(b" ")[-1].startswith((b"R", b"C")):
                raise GitBatchError("git diff-tree contains a rename or copy")
            raise GitBatchError("git diff-tree response has an unpaired path record")
        raw_path = records[index]
        index += 1
        if not metadata.startswith(b":"):
            raise GitBatchError("git diff-tree metadata is malformed")
        if not raw_path:
            raise GitBatchError("git diff-tree path is empty")
        fields = metadata[1:].split(b" ")
        if len(fields) != 5:
            raise GitBatchError("git diff-tree metadata is malformed")
        if fields[4] in {b"R100", b"R", b"C100", b"C"} or fields[4].startswith((b"R", b"C")):
            raise GitBatchError("git diff-tree contains a rename or copy")
        try:
            old_mode, new_mode, old_blob, new_blob, status = (
                field.decode("ascii") for field in fields
            )
            path = _validate_path(raw_path)
        except UnicodeDecodeError as exc:
            raise GitBatchError("git diff-tree metadata is not ASCII") from exc
        if (
            MODE_RE.fullmatch(old_mode.encode("ascii")) is None
            or MODE_RE.fullmatch(new_mode.encode("ascii")) is None
            or SHA1_RE.fullmatch(old_blob.encode("ascii")) is None
            or SHA1_RE.fullmatch(new_blob.encode("ascii")) is None
            or len(status) != 1
            or status not in frozenset("ADMT")
        ):
            raise GitBatchError("git diff-tree metadata is malformed")
        had_base = old_mode != "000000"
        has_candidate = new_mode != "000000"
        expected_presence = {
            "A": (False, True),
            "D": (True, False),
            "M": (True, True),
            "T": (True, True),
        }[status]
        if (had_base, has_candidate) != expected_presence:
            raise GitBatchError("git diff-tree status does not match modes")
        expected_zero = {
            "A": (True, False),
            "D": (False, True),
            "M": (False, False),
            "T": (False, False),
        }[status]
        if (old_blob == _ZERO_SHA1, new_blob == _ZERO_SHA1) != expected_zero:
            raise GitBatchError("git diff-tree blob zero state is inconsistent")
        if path in entries:
            raise GitBatchError(f"duplicate git diff-tree path: {path}")
        entries[path] = RawDiffTreeEntry(
            base_mode=old_mode,
            base_blob="" if had_base is False else old_blob,
            mode=new_mode,
            blob="" if has_candidate is False else new_blob,
        )
    return entries


class BaseTreeIndex:
    """Immutable path index parsed from one recursive base-tree response."""

    def __init__(
        self,
        repo_root: Path,
        base_oid: str,
        *,
        runner: Callable[..., bytes] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.base_oid = base_oid
        self.object_format = self._object_format(runner)
        if self.object_format != "sha1":
            raise GitBatchError(f"unsupported Git object format: {self.object_format}")
        if not re.fullmatch(r"[0-9a-f]{40}", base_oid):
            raise GitBatchError("base oid must be a SHA-1 object id")
        run = runner or _run_git
        output = run(
            self.repo_root,
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            base_oid,
        )
        self._entries = MappingProxyType(self._parse(output))

    def _object_format(self, runner: Callable[..., bytes] | None) -> str:
        run = runner or _run_git
        raw = run(self.repo_root, "rev-parse", "--show-object-format")
        try:
            return raw.decode("ascii").strip().lower()
        except UnicodeDecodeError as exc:
            raise GitBatchError("Git object format is not ASCII") from exc

    @classmethod
    def from_repo(
        cls,
        repo_root: Path,
        base_oid: str,
        *,
        runner: Callable[..., bytes] | None = None,
    ) -> BaseTreeIndex:
        return cls(repo_root, base_oid, runner=runner)

    @staticmethod
    def _parse(output: bytes) -> dict[str, BaseTreeEntry]:
        entries: dict[str, BaseTreeEntry] = {}
        if not isinstance(output, bytes):
            raise GitBatchError("git ls-tree response is not bytes")
        if output == b"":
            return entries
        if not output.endswith(b"\0"):
            raise GitBatchError("git ls-tree response is not NUL terminated")
        for record in output[:-1].split(b"\0"):
            if not record:
                raise GitBatchError("git ls-tree response contains an empty record")
            if b"\t" not in record:
                raise GitBatchError("malformed git ls-tree record")
            header, raw_path = record.split(b"\t", 1)
            fields = header.split(b" ")
            if len(fields) != 3 or any(not field for field in fields):
                raise GitBatchError("malformed git ls-tree header")
            mode_b, kind_b, oid_b = fields
            if MODE_RE.fullmatch(mode_b) is None or SHA1_RE.fullmatch(oid_b) is None:
                raise GitBatchError("malformed git ls-tree mode or object id")
            try:
                kind = kind_b.decode("ascii")
            except UnicodeDecodeError as exc:
                raise GitBatchError("git ls-tree kind is not ASCII") from exc
            path = _validate_path(raw_path)
            if path in entries:
                raise GitBatchError(f"duplicate git ls-tree path: {path}")
            entries[path] = BaseTreeEntry(mode_b.decode("ascii"), kind, oid_b.decode("ascii"))
        return entries

    parse = _parse

    def lookup(self, relative: Path | str) -> BaseTreeEntry | None:
        path = relative.as_posix() if isinstance(relative, Path) else str(relative)
        _validate_path(path.encode("utf-8"))
        entry = self._entries.get(path)
        if entry is None:
            return None
        if entry.kind != "blob" or entry.mode not in {"100644", "100755", "120000"}:
            raise GitBatchError(f"unsupported base tree entry: {path}")
        return entry

    get = lookup

    def __contains__(self, relative: object) -> bool:
        if isinstance(relative, Path):
            relative = relative.as_posix()
        return isinstance(relative, str) and relative in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def items(self) -> Iterator[tuple[str, BaseTreeEntry]]:
        return iter(self._entries.items())


def git_blob_oid(payload: bytes, *, object_format: str = "sha1") -> str:
    """Compute Git's blob object id without invoking ``git hash-object``."""
    if object_format != "sha1":
        raise GitBatchError(f"unsupported Git object format: {object_format}")
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


parse_ls_tree_z = BaseTreeIndex.parse


K = TypeVar("K")
V = TypeVar("V")


class BoundedReadOnlyCache(Generic[K, V]):
    """Bounded process-local cache; values are never derived by reading sources."""

    def __init__(self, max_entries: int = 128, *, max_size: int | None = None) -> None:
        if max_size is not None:
            max_entries = max_size
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._values: OrderedDict[K, V] = OrderedDict()

    def get(self, key: K, default: V | None = None) -> V | None:
        value = self._values.get(key, default)
        if key in self._values:
            self._values.move_to_end(key)
        return value

    def put(self, key: K, value: V) -> V:
        self._values[key] = value
        self._values.move_to_end(key)
        while len(self._values) > self.max_entries:
            self._values.popitem(last=False)
        return value

    def __len__(self) -> int:
        return len(self._values)

    def clear(self) -> None:
        self._values.clear()


@dataclass(frozen=True)
class IntakeCacheKey:
    schema: str
    resolved_source: str
    dev: int
    ino: int
    head: str
    porcelain_sha256: str
    canonical_manifest_sha256: str
    base_oid: str
    object_format: str

    @classmethod
    def from_values(cls, **values: Any) -> IntakeCacheKey:
        required = {field.name for field in cls.__dataclass_fields__.values()}
        if set(values) != required:
            raise ValueError(f"cache key fields must be exactly {sorted(required)}")
        return cls(**values)


def make_intake_cache_key(**values: Any) -> IntakeCacheKey:
    return IntakeCacheKey.from_values(**values)


@dataclass(frozen=True)
class IntakeCacheValue:
    """Immutable process-local value containing a base tree index."""

    base_index: BaseTreeIndex


__all__ = [
    "BaseTreeEntry",
    "BaseTreeIndex",
    "BoundedReadOnlyCache",
    "GitBatchError",
    "IntakeCacheKey",
    "IntakeCacheValue",
    "git_blob_oid",
    "make_intake_cache_key",
    "parse_ls_tree_z",
]
