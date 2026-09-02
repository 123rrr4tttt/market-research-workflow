"""Project-scoped, content-addressed blob store.

Path contract (frozen architecture):

``/var/lib/mrw/runtime-artifacts/projects/<project-scope-digest>/sha256/<prefix>/<digest>``

Writes go to a temporary file in the final directory, are fsynced and verified
by digest/size, then atomically renamed.  Orphan reconciliation never deletes
blobs still referenced by retention refs.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.successor_runtime.runtime.ports import ProjectScopeRef

BLOB_ROOT = Path("/var/lib/mrw/runtime-artifacts")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class BlobStoreError(RuntimeError):
    """Base class for blob store failures."""


class BlobNotFound(BlobStoreError, FileNotFoundError):
    """Raised when a final blob is missing."""


class BlobDigestMismatch(BlobStoreError):
    """Raised when stored bytes do not match the content digest."""


class BlobValidationError(ValueError):
    """Raised for invalid scope or content digests."""


def _scope_digest(scope: ProjectScopeRef | str) -> str:
    if isinstance(scope, ProjectScopeRef):
        return scope.scope_digest
    if _DIGEST_PATTERN.fullmatch(scope) is None:
        raise BlobValidationError("scope digest must be canonical sha256 hex")
    return scope


def _digest_hex(digest: str) -> str:
    if _DIGEST_PATTERN.fullmatch(digest) is None:
        raise BlobValidationError("content digest must be canonical sha256 hex")
    return digest


def project_blob_root(root: Path, scope: ProjectScopeRef | str) -> Path:
    return Path(root) / "projects" / _scope_digest(scope) / "sha256"


def blob_path(root: Path, scope: ProjectScopeRef | str, digest: str) -> Path:
    digest = _digest_hex(digest)
    return project_blob_root(root, scope) / digest[:2] / digest


def compute_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def storage_ref(scope: ProjectScopeRef | str, digest: str) -> str:
    digest = _digest_hex(digest)
    scope_digest = _scope_digest(scope)
    return f"projects/{scope_digest}/sha256/{digest[:2]}/{digest}"


@dataclass(frozen=True, slots=True)
class PreparedBlob:
    scope_digest: str
    temp_path: Path
    final_path: Path
    digest: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class BlobRef:
    scope_digest: str
    digest: str
    byte_size: int
    path: Path
    storage_ref: str


@dataclass(frozen=True, slots=True)
class BlobReadback:
    data: bytes
    digest: str
    byte_size: int


class ProjectBlobStore:
    """Content-addressed blob store rooted at ``root`` (tests use tempdirs)."""

    def __init__(self, root: Path = BLOB_ROOT, *, fsync: bool = True) -> None:
        self.root = Path(root)
        self.fsync = fsync

    def prepare(self, scope: ProjectScopeRef | str, data: bytes) -> PreparedBlob:
        """Write, fsync, then verify digest/size of a same-directory temp file."""

        scope_digest = _scope_digest(scope)
        digest = compute_digest(data)
        final_path = blob_path(self.root, scope_digest, digest)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = final_path.with_name(
            f".{final_path.name}.{uuid.uuid4().hex}.tmp"
        )
        with open(temp_path, "xb") as handle:
            handle.write(data)
            handle.flush()
            if self.fsync:
                os.fsync(handle.fileno())
        written = temp_path.read_bytes()
        written_digest = compute_digest(written)
        if written_digest != digest or len(written) != len(data):
            temp_path.unlink(missing_ok=True)
            raise BlobDigestMismatch(
                "temporary blob failed digest/size verification"
            )
        return PreparedBlob(
            scope_digest=scope_digest,
            temp_path=temp_path,
            final_path=final_path,
            digest=digest,
            byte_size=len(written),
        )

    def finalize(self, prepared: PreparedBlob) -> BlobRef:
        """Atomically rename a verified temp blob into its final path."""

        if not prepared.temp_path.exists():
            raise BlobStoreError("prepared blob temp file is missing")
        current = prepared.temp_path.read_bytes()
        if compute_digest(current) != prepared.digest or len(current) != prepared.byte_size:
            raise BlobDigestMismatch(
                "prepared blob changed before finalize"
            )
        if prepared.final_path.exists():
            existing = prepared.final_path.read_bytes()
            if (
                compute_digest(existing) != prepared.digest
                or len(existing) != prepared.byte_size
            ):
                raise BlobDigestMismatch(
                    "existing final blob does not match prepared digest"
                )
            prepared.temp_path.unlink()
        else:
            os.replace(prepared.temp_path, prepared.final_path)
            self._fsync_directory(prepared.final_path.parent)
        return BlobRef(
            scope_digest=prepared.scope_digest,
            digest=prepared.digest,
            byte_size=prepared.byte_size,
            path=prepared.final_path,
            storage_ref=storage_ref(prepared.scope_digest, prepared.digest),
        )

    def store(self, scope: ProjectScopeRef | str, data: bytes) -> BlobRef:
        return self.finalize(self.prepare(scope, data))

    def readback(
        self, scope: ProjectScopeRef | str, digest: str
    ) -> BlobReadback:
        scope_digest = _scope_digest(scope)
        digest = _digest_hex(digest)
        path = blob_path(self.root, scope_digest, digest)
        try:
            data = path.read_bytes()
        except FileNotFoundError as exc:
            raise BlobNotFound(
                f"blob not found for scope {scope_digest} digest {digest}"
            ) from exc
        if compute_digest(data) != digest:
            raise BlobDigestMismatch(f"blob digest mismatch at {path}")
        return BlobReadback(data=data, digest=digest, byte_size=len(data))

    def exists(self, scope: ProjectScopeRef | str, digest: str) -> bool:
        try:
            return blob_path(self.root, scope, digest).is_file()
        except BlobValidationError:
            return False

    def reconcile_orphans(
        self,
        scope: ProjectScopeRef | str,
        retained: Iterable[str],
    ) -> list[str]:
        """Delete unreferenced final blobs; retention refs are protected."""

        scope_digest = _scope_digest(scope)
        retained_digests = {_digest_hex(item) for item in retained}
        root = project_blob_root(self.root, scope_digest)
        removed: list[str] = []
        if not root.is_dir():
            return removed
        for path in sorted(root.glob("*/*")):
            digest = path.name
            if not _DIGEST_PATTERN.fullmatch(digest) or not path.is_file():
                continue
            if digest in retained_digests:
                continue
            path.unlink()
            removed.append(digest)
        return removed

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt":
            return
        try:
            descriptor = os.open(
                path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            )
        except OSError:
            return
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
