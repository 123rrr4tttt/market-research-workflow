from __future__ import annotations
# ruff: noqa: TRY003, TRY300, TRY301

import json
import os
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal


PreflightStatus = Literal["PASS", "FAIL", "BLOCKED", "UNEXECUTED"]

SCHEMA_VERSION: Final = "mrw.formal-release-preflight.v1"
DERIVED_AS: Final = "preflight"
_STATUS_PRECEDENCE: Final[dict[PreflightStatus, int]] = {
    "PASS": 0,
    "UNEXECUTED": 1,
    "BLOCKED": 2,
    "FAIL": 3,
}


class CreateOnlyWriteError(RuntimeError):
    """Raised when a create-only output path cannot be written without redirection."""


class StableFileReadError(RuntimeError):
    """Raised when a regular-file read cannot be proven path-stable."""


DirectoryIdentity = tuple[int, int]


def directory_identity(path: Path) -> DirectoryIdentity:
    """Return the stable filesystem identity of a directory."""
    identity = os.stat(path, follow_symlinks=False)
    return identity.st_dev, identity.st_ino


def _open_directory_no_symlinks(path: Path) -> int:
    absolute = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _assert_ancestors_outside(
    parent_descriptor: int,
    forbidden_identities: Iterable[DirectoryIdentity],
) -> None:
    forbidden = frozenset(forbidden_identities)
    if not forbidden:
        return

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.dup(parent_descriptor)
    try:
        while True:
            identity = os.fstat(descriptor)
            if (identity.st_dev, identity.st_ino) in forbidden:
                raise CreateOnlyWriteError(
                    "create-only output ancestor entered a forbidden checkout"
                )
            parent = os.open("..", flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = parent
            parent_identity = os.fstat(descriptor)
            if (parent_identity.st_dev, parent_identity.st_ino) == (
                identity.st_dev,
                identity.st_ino,
            ):
                return
    finally:
        os.close(descriptor)


def write_create_only_bytes(
    path: Path,
    payload: bytes,
    forbidden_identities: Iterable[DirectoryIdentity] = (),
) -> Path:
    """Create one file through stable directory descriptors and verify its path identity."""
    destination = path.absolute()
    parent_descriptor: int | None = None
    created = False
    try:
        parent_descriptor = _open_directory_no_symlinks(destination.parent)
        parent_identity = os.fstat(parent_descriptor)
        _assert_ancestors_outside(parent_descriptor, forbidden_identities)
        descriptor = os.open(
            destination.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o644,
            dir_fd=parent_descriptor,
        )
        created = True
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise CreateOnlyWriteError("create-only output write made no progress")
                view = view[written:]
            os.fsync(descriptor)
            created_identity = os.fstat(descriptor)
            _assert_ancestors_outside(parent_descriptor, forbidden_identities)
        finally:
            os.close(descriptor)

        verification_parent = _open_directory_no_symlinks(destination.parent)
        try:
            current_parent = os.fstat(verification_parent)
            verification = os.open(
                destination.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=verification_parent,
            )
            try:
                current_file = os.fstat(verification)
            finally:
                os.close(verification)
        finally:
            os.close(verification_parent)
        if (parent_identity.st_dev, parent_identity.st_ino) != (
            current_parent.st_dev,
            current_parent.st_ino,
        ) or (created_identity.st_dev, created_identity.st_ino, created_identity.st_size) != (
            current_file.st_dev,
            current_file.st_ino,
            current_file.st_size,
        ):
            raise CreateOnlyWriteError("create-only output path changed during write")
        return destination
    except FileExistsError as exc:
        raise CreateOnlyWriteError(f"create-only target already exists: {destination}") from exc
    except (CreateOnlyWriteError, OSError) as exc:
        if created and parent_descriptor is not None:
            try:
                os.unlink(destination.name, dir_fd=parent_descriptor)
            except OSError:
                pass
        if isinstance(exc, CreateOnlyWriteError):
            raise
        raise CreateOnlyWriteError(f"create-only output path is unsafe: {destination}: {exc}") from exc
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def read_stable_regular_bytes(path: Path, *, label: str = "file") -> bytes:
    """Read one regular file without blocking on a swapped FIFO or symlink."""
    destination = path.absolute()
    parent_descriptor: int | None = None
    try:
        parent_descriptor = _open_directory_no_symlinks(destination.parent)
        parent_identity = os.fstat(parent_descriptor)
        descriptor = os.open(
            destination.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_descriptor,
        )
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                kind = "FIFO" if stat.S_ISFIFO(before.st_mode) else "non-regular file"
                raise StableFileReadError(f"{label} must be a regular file ({kind})")
            chunks: list[bytes] = []
            while chunk := os.read(descriptor, 1024 * 1024):
                if not chunk:
                    raise StableFileReadError(f"{label} read made no progress")
                chunks.append(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)

        verification_parent = _open_directory_no_symlinks(destination.parent)
        try:
            current_parent = os.fstat(verification_parent)
            verification = os.open(
                destination.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
                dir_fd=verification_parent,
            )
            try:
                current = os.fstat(verification)
            finally:
                os.close(verification)
        finally:
            os.close(verification_parent)
    except BlockingIOError as exc:
        raise StableFileReadError(f"{label} read would block") from exc
    except StableFileReadError:
        raise
    except OSError as exc:
        raise StableFileReadError(f"{label} cannot be read safely: {exc}") from exc
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)

    stable = (
        stat.S_ISREG(current.st_mode)
        and (parent_identity.st_dev, parent_identity.st_ino)
        == (current_parent.st_dev, current_parent.st_ino)
        and (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
        and (after.st_dev, after.st_ino) == (current.st_dev, current.st_ino)
        and before.st_size == after.st_size == sum(len(chunk) for chunk in chunks)
        and before.st_mtime_ns == after.st_mtime_ns
        and before.st_ctime_ns == after.st_ctime_ns
    )
    if not stable:
        raise StableFileReadError(f"{label} changed during read")
    return b"".join(chunks)


def _required_text(value: str, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized


def _validate_status(value: str) -> PreflightStatus:
    if value not in _STATUS_PRECEDENCE:
        raise ValueError(f"unknown preflight status: {value!r}")
    return value  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class Finding:
    check_id: str
    status: PreflightStatus
    summary: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_id", _required_text(self.check_id, "check_id"))
        object.__setattr__(self, "status", _validate_status(self.status))
        object.__setattr__(self, "summary", _required_text(self.summary, "summary"))
        object.__setattr__(
            self,
            "evidence",
            tuple(_required_text(item, "evidence item") for item in self.evidence),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "summary": self.summary,
            "evidence": list(self.evidence),
        }


def aggregate_status(findings: Iterable[Finding]) -> PreflightStatus:
    items = tuple(findings)
    if not items:
        return "UNEXECUTED"
    return max(items, key=lambda item: _STATUS_PRECEDENCE[item.status]).status


@dataclass(frozen=True, slots=True)
class PreflightReport:
    checker: str
    findings: tuple[Finding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "checker", _required_text(self.checker, "checker"))
        object.__setattr__(self, "findings", tuple(self.findings))
        check_ids = [item.check_id for item in self.findings]
        if len(set(check_ids)) != len(check_ids):
            raise ValueError("finding check_id values must be unique")

    @property
    def status(self) -> PreflightStatus:
        return aggregate_status(self.findings)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "checker": self.checker,
            "authoritative": False,
            "derived_as": DERIVED_AS,
            "status": self.status,
            "findings": [item.to_dict() for item in self.findings],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
