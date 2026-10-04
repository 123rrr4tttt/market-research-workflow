#!/usr/bin/env python3
"""Stage and validate exact-byte family-fragment rebind candidates.

Publication is atomic against truncation and same-process replacement, and
reopens the published path to detect a same-UID directory rename.  It does not
defend against a privileged process, or a concurrent same-UID process with
write access, maliciously replacing files or directory entries while the tool
runs or after its check returns.  Without such an adversary, path confinement
holds and normal concurrent stagers do not observe a truncated final path.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import secrets
import stat
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

MANIFEST_SCHEMA = "mrw.family_fragment_rebind.stage_manifest.v2"
CANDIDATE_SCHEMA = "mrw.family_fragment_rebind.candidate.v2"
CANDIDATE_FILENAME = "candidate.v2.json"
SNAPSHOT_DIRECTORY = "snapshots"

LIVE_STATUS = "CANDIDATE_VALID_NOT_AUTHORITY"
HISTORY_STATUS = "HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY"

RAW_GROUPS = ("fragments", "sources", "tests")
JSON_GROUPS = frozenset({"fragments"})
MANIFEST_KEYS = ("schema", "family", "amendment", *RAW_GROUPS)
MANIFEST_JSON_REFERENCE_KEYS = ("path", "file_sha256", "content_digest")
MANIFEST_RAW_REFERENCE_KEYS = ("path", "file_sha256")
JSON_REFERENCE_KEYS = (*MANIFEST_JSON_REFERENCE_KEYS, "snapshot_path", "bytes")
RAW_REFERENCE_KEYS = ("path", "file_sha256", "snapshot_path", "bytes")


class ValidationError(ValueError):
    """A fail-closed validation error."""


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _parse_json_bytes(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValidationError(f"cannot parse JSON {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{label} JSON root must be an object")
    return value


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"cannot encode canonical JSON: {exc}") from exc


def content_digest(value: dict[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key != "content_digest"}
    return hashlib.sha256(canonical_json(body)).hexdigest()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _normalized_relative(root: Path, raw_path: Path | str, *, label: str) -> Path:
    text = str(raw_path)
    if "\x00" in text:
        raise ValidationError(f"{label} contains a NUL byte")
    if isinstance(raw_path, Path) and raw_path.is_absolute():
        try:
            text = raw_path.relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise ValidationError(f"{label} escapes repository root: {raw_path}") from exc
    if not text or text.startswith("/") or text.startswith("~") or "\\" in text:
        raise ValidationError(f"{label} must be a non-empty repository-relative POSIX path")
    parts = tuple(text.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ValidationError(f"{label} must be normalized within the repository: {raw_path}")
    return Path(*parts)


def _close(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _open_root(root: Path) -> int:
    try:
        return os.open(
            root.resolve(strict=True),
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise ValidationError(f"cannot open repository root {root}: {exc}") from exc


def _open_component(
    descriptor: int,
    component: str,
    *,
    directory: bool,
    label: str,
) -> int:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    if directory:
        flags |= os.O_DIRECTORY
    else:
        flags |= os.O_NONBLOCK
    try:
        return os.open(component, flags, dir_fd=descriptor)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValidationError(
                f"{label} must not traverse or target a symlink: {component}"
            ) from exc
        kind = "directory" if directory else "file"
        raise ValidationError(
            f"cannot open confined {kind} {label}/{component}: {exc}"
        ) from exc


def _open_beneath(root: Path, relative: Path, *, label: str) -> tuple[int, int]:
    root_descriptor = _open_root(root)
    current = root_descriptor
    try:
        if not relative.parts:
            raise ValidationError(f"{label} must name a file below the repository root")
        for component in relative.parts[:-1]:
            child = _open_component(current, component, directory=True, label=label)
            if current != root_descriptor:
                _close(current)
            current = child
        descriptor = _open_component(
            current, relative.parts[-1], directory=False, label=label
        )
        return descriptor, root_descriptor
    finally:
        if current != root_descriptor:
            _close(current)


def _require_regular(
    descriptor: int,
    *,
    label: str,
    immutable: bool = False,
    single_link: bool = False,
) -> None:
    try:
        metadata = os.fstat(descriptor)
    except OSError as exc:
        raise ValidationError(f"cannot stat {label}: {exc}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ValidationError(f"{label} must be a regular file")
    if immutable and metadata.st_mode & 0o222:
        raise ValidationError(f"{label} immutable snapshot must not be writable")
    if single_link and metadata.st_nlink != 1:
        raise ValidationError(f"{label} immutable snapshot must have exactly one link")


def _read_descriptor(descriptor: int, *, label: str) -> bytes:
    chunks: list[bytes] = []
    while True:
        try:
            chunk = os.read(descriptor, 1024 * 1024)
        except OSError as exc:
            raise ValidationError(f"cannot read {label}: {exc}") from exc
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def _read_file(root: Path, raw_path: Path | str, *, label: str) -> tuple[bytes, Path]:
    relative = _normalized_relative(root, raw_path, label=label)
    descriptor, root_descriptor = _open_beneath(root, relative, label=label)
    try:
        _require_regular(descriptor, label=label)
        return _read_descriptor(descriptor, label=label), relative
    finally:
        _close(descriptor)
        _close(root_descriptor)


def _create_directory_beneath(root: Path, relative: Path, *, label: str) -> None:
    if not relative.parts:
        raise ValidationError(f"{label} must be below the repository root")
    root_descriptor = _open_root(root)
    current = root_descriptor
    try:
        for component in relative.parts:
            try:
                os.mkdir(component, 0o700, dir_fd=current)
            except FileExistsError:
                pass
            child = _open_component(current, component, directory=True, label=label)
            if current != root_descriptor:
                _close(current)
            current = child
    finally:
        if current != root_descriptor:
            _close(current)
        _close(root_descriptor)


def _open_parent(root: Path, relative: Path, *, label: str) -> tuple[int, int]:
    root_descriptor = _open_root(root)
    current = root_descriptor
    try:
        if not relative.parts:
            raise ValidationError(f"{label} must name a file below the repository root")
        for component in relative.parts[:-1]:
            child = _open_component(current, component, directory=True, label=label)
            if current != root_descriptor:
                _close(current)
            current = child
        return current, root_descriptor
    except Exception:
        if current != root_descriptor:
            _close(current)
        _close(root_descriptor)
        raise


def _write_all(descriptor: int, payload: bytes, *, label: str) -> None:
    view = memoryview(payload)
    try:
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fchmod(descriptor, 0o444)
        os.fsync(descriptor)
    except OSError as exc:
        raise ValidationError(f"cannot publish complete {label} payload: {exc}") from exc


def _publication_ready(
    parent: int,
    temporary_name: str,
    payload: bytes,
) -> bool:
    flags = (
        os.O_RDONLY
        | os.O_NOFOLLOW
        | os.O_NONBLOCK
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(temporary_name, flags, dir_fd=parent)
    except OSError as exc:
        raise ValidationError(f"cannot reopen temporary output {temporary_name}: {exc}") from exc
    try:
        _require_regular(descriptor, label=temporary_name, immutable=True)
        return _read_descriptor(descriptor, label=temporary_name) == payload
    finally:
        _close(descriptor)


def _verify_snapshot_at_parent(
    parent: int,
    name: str,
    payload: bytes,
    *,
    digest: str,
) -> None:
    deadline = time.monotonic() + 1.0
    descriptor = -1
    flags = (
        os.O_RDONLY
        | os.O_NOFOLLOW
        | os.O_NONBLOCK
        | getattr(os, "O_CLOEXEC", 0)
    )
    while True:
        try:
            descriptor = os.open(name, flags, dir_fd=parent)
        except OSError as exc:
            raise ValidationError(f"cannot open existing snapshot {name}: {exc}") from exc
        try:
            metadata = os.fstat(descriptor)
            if metadata.st_nlink == 1 or time.monotonic() >= deadline:
                break
        except OSError as exc:
            _close(descriptor)
            descriptor = -1
            raise ValidationError(f"cannot stat snapshot {name}: {exc}") from exc
        _close(descriptor)
        descriptor = -1
        time.sleep(0.01)
    try:
        _require_regular(
            descriptor,
            label=name,
            immutable=True,
            single_link=True,
        )
        existing = _read_descriptor(descriptor, label=name)
        if existing != payload or _sha256(existing) != digest:
            raise ValidationError(f"existing snapshot has unexpected bytes: {digest}")
    finally:
        _close(descriptor)


def _fsync_directory(descriptor: int) -> None:
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise ValidationError(f"cannot sync publication directory: {exc}") from exc


def _write_new_immutable(
    root: Path,
    relative: Path,
    payload: bytes,
    *,
    label: str,
    allow_existing_snapshot: bool = False,
) -> None:
    parent, root_descriptor = _open_parent(root, relative, label=label)
    name = relative.parts[-1]
    temporary_name = f".{name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    descriptor = -1
    published = False
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | os.O_NONBLOCK
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            descriptor = os.open(temporary_name, flags, 0o600, dir_fd=parent)
        except OSError as exc:
            raise ValidationError(
                f"cannot create temporary {label} output: {exc}"
            ) from exc
        _write_all(descriptor, payload, label=label)
        published_identity = os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino
        _close(descriptor)
        descriptor = -1
        if not _publication_ready(parent, temporary_name, payload):
            raise ValidationError(f"temporary {label} payload verification failed")

        try:
            os.link(
                temporary_name,
                name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise ValidationError(
                    f"cannot atomically publish {label} output: {exc}"
                ) from exc
            if allow_existing_snapshot:
                _verify_snapshot_at_parent(
                    parent,
                    name,
                    payload,
                    digest=_sha256(payload),
                )
            else:
                raise ValidationError(f"{label} output already exists: {relative}") from exc
        else:
            published = True
        _fsync_directory(parent)
        os.unlink(temporary_name, dir_fd=parent)
        _fsync_directory(parent)

        reopened, reopened_root = _open_beneath(root, relative, label=label)
        try:
            _require_regular(
                reopened,
                label=str(relative),
                immutable=True,
                single_link=True,
            )
            reopened_parent, reopened_parent_root = _open_parent(
                root,
                relative,
                label=label,
            )
            try:
                held_identity = os.fstat(parent).st_dev, os.fstat(parent).st_ino
                actual_parent_identity = (
                    os.fstat(reopened_parent).st_dev,
                    os.fstat(reopened_parent).st_ino,
                )
            finally:
                _close(reopened_parent)
                _close(reopened_parent_root)
            if (
                actual_parent_identity != held_identity
                or (
                    published
                    and (os.fstat(reopened).st_dev, os.fstat(reopened).st_ino)
                    != published_identity
                )
            ):
                raise ValidationError(f"published {label} path parent changed")
        finally:
            _close(reopened)
            _close(reopened_root)
    except Exception:
        if descriptor != -1:
            _close(descriptor)
        if published:
            try:
                os.unlink(name, dir_fd=parent)
            except OSError:
                pass
        try:
            os.unlink(temporary_name, dir_fd=parent)
        except OSError:
            pass
        raise
    finally:
        if descriptor != -1:
            _close(descriptor)
        _close(parent)
        _close(root_descriptor)


def _snapshot_relative(digest: str) -> Path:
    return Path(SNAPSHOT_DIRECTORY) / digest


def _store_snapshot(root: Path, output_dir: Path, payload: bytes) -> str:
    digest = _sha256(payload)
    _create_directory_beneath(
        root,
        output_dir / SNAPSHOT_DIRECTORY,
        label="snapshot directory",
    )
    relative = output_dir / SNAPSHOT_DIRECTORY / digest
    _write_new_immutable(
        root,
        relative,
        payload,
        label="snapshot",
        allow_existing_snapshot=True,
    )
    return digest


def _require_exact_keys(value: dict[str, Any], keys: tuple[str, ...], *, label: str) -> None:
    actual = set(value)
    expected = set(keys)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ValidationError(f"{label} keys invalid: missing={missing}, unknown={unknown}")


def _manifest_ref(value: Any, *, label: str, json_ref: bool) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object")
    expected_keys = (
        MANIFEST_JSON_REFERENCE_KEYS if json_ref else MANIFEST_RAW_REFERENCE_KEYS
    )
    _require_exact_keys(value, expected_keys, label=label)
    if not isinstance(value["path"], str):
        raise ValidationError(f"{label}.path must be a string")
    if not _is_digest(value["file_sha256"]):
        raise ValidationError(f"{label}.file_sha256 must be a lowercase SHA-256")
    if json_ref and not _is_digest(value["content_digest"]):
        raise ValidationError(f"{label}.content_digest must be a lowercase SHA-256")
    return dict(value)


def _validate_candidate_ref(value: Any, *, json_ref: bool, label: str) -> dict[str, Any]:
    expected_keys = JSON_REFERENCE_KEYS if json_ref else RAW_REFERENCE_KEYS
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object")
    _require_exact_keys(value, expected_keys, label=label)
    if not isinstance(value["path"], str):
        raise ValidationError(f"{label}.path must be a string")
    if not _is_digest(value["file_sha256"]):
        raise ValidationError(f"{label}.file_sha256 must be a lowercase SHA-256")
    if json_ref and not _is_digest(value["content_digest"]):
        raise ValidationError(f"{label}.content_digest must be a lowercase SHA-256")
    if not isinstance(value["snapshot_path"], str) or "\x00" in value["snapshot_path"]:
        raise ValidationError(f"{label}.snapshot_path must name a SHA-256 snapshot")
    snapshot_digest = value["snapshot_path"].replace(f"{SNAPSHOT_DIRECTORY}/", "", 1)
    if (
        not isinstance(value["snapshot_path"], str)
        or value["snapshot_path"] != f"{SNAPSHOT_DIRECTORY}/{snapshot_digest}"
        or not _is_digest(snapshot_digest)
    ):
        raise ValidationError(f"{label}.snapshot_path must name a SHA-256 snapshot")
    if not _is_nonnegative_int(value["bytes"]):
        raise ValidationError(f"{label}.bytes must be a nonnegative integer")
    return dict(value)


def _validate_manifest(
    manifest: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, list[dict[str, str]]]:
    _require_exact_keys(manifest, MANIFEST_KEYS, label="manifest")
    if manifest["schema"] != MANIFEST_SCHEMA:
        raise ValidationError(f"unknown manifest schema: {manifest['schema']!r}")
    if not isinstance(manifest["family"], str) or not manifest["family"]:
        raise ValidationError("manifest.family must be a non-empty string")
    if not isinstance(manifest["amendment"], str) or not manifest["amendment"]:
        raise ValidationError("manifest.amendment must be a non-empty string")
    refs: dict[str, list[dict[str, str]]] = {}
    seen_paths: set[str] = set()
    for group in RAW_GROUPS:
        values = manifest[group]
        if not isinstance(values, list) or not values:
            raise ValidationError(f"manifest.{group} must be a non-empty list")
        normalized: list[dict[str, str]] = []
        for index, value in enumerate(values):
            reference = _manifest_ref(
                value,
                label=f"manifest.{group}[{index}]",
                json_ref=group in JSON_GROUPS,
            )
            _normalized_relative(
                repo_root,
                reference["path"],
                label=f"manifest.{group}[{index}]",
            )
            if reference["path"] in seen_paths:
                raise ValidationError(f"duplicate manifest input path: {reference['path']}")
            seen_paths.add(reference["path"])
            normalized.append(reference)
        refs[group] = normalized
    return refs


def _candidate_id(
    family: str,
    amendment: str,
    manifest_ref: dict[str, Any],
    refs: dict[str, list[dict[str, Any]]],
) -> str:
    identity = {
        "amendment": amendment,
        "family": family,
        "manifest": manifest_ref,
        **refs,
    }
    return _sha256(canonical_json(identity))


def _is_at_or_below(path: Path, directory: Path) -> bool:
    if path == directory:
        return True
    return path.parts[: len(directory.parts)] == directory.parts


def stage(
    manifest_path: Path,
    output_dir: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, str]:
    resolved_output = output_dir.resolve(strict=False)
    if resolved_output == repo_root.resolve() or output_dir == Path("."):
        raise ValidationError("output directory must be below the repository root")
    output_relative = _normalized_relative(
        repo_root,
        output_dir,
        label="stage.output_dir",
    )
    if not output_relative.parts:
        raise ValidationError("output directory must be below the repository root")

    manifest_payload, manifest_relative = _read_file(
        repo_root,
        manifest_path,
        label="stage.manifest",
    )
    manifest = _parse_json_bytes(manifest_payload, label=str(manifest_relative))
    manifest_refs = _validate_manifest(manifest, repo_root=repo_root)
    if _is_at_or_below(manifest_relative, output_relative):
        raise ValidationError("manifest must not be inside the output directory")

    def normalize_repo_path(path: str) -> Path:
        return _normalized_relative(repo_root, path, label="manifest input")

    def read_input(reference: dict[str, str], label: str) -> bytes:
        relative = normalize_repo_path(reference["path"])
        payload, actual_relative = _read_file(repo_root, relative, label=label)
        actual_digest = _sha256(payload)
        if actual_relative != relative:
            raise ValidationError(f"{label} resolved outside repository: {reference['path']}")
        if actual_digest != reference["file_sha256"]:
            raise ValidationError(f"{label}.file_sha256 mismatch: {reference['path']}")
        return payload

    candidate_refs: dict[str, list[dict[str, Any]]] = {}
    frozen_payloads: list[bytes] = []
    for group in RAW_GROUPS:
        candidate_values: list[dict[str, Any]] = []
        for index, reference in enumerate(manifest_refs[group]):
            label = f"manifest.{group}[{index}]"
            if _is_at_or_below(normalize_repo_path(reference["path"]), output_relative):
                raise ValidationError(
                    f"manifest input must not be inside the output directory: {reference['path']}"
                )
            payload = read_input(reference, label)
            digest = _sha256(payload)
            candidate_value: dict[str, Any] = {
                **reference,
                "bytes": len(payload),
                "snapshot_path": f"{SNAPSHOT_DIRECTORY}/{digest}",
            }
            if group in JSON_GROUPS:
                parsed = _parse_json_bytes(payload, label=reference["path"])
                if content_digest(parsed) != reference["content_digest"]:
                    raise ValidationError(f"{label}.content_digest mismatch")
            candidate_values.append(candidate_value)
            frozen_payloads.append(payload)
        candidate_refs[group] = candidate_values

    manifest_digest = _sha256(manifest_payload)
    manifest_candidate_ref: dict[str, Any] = {
        "path": manifest_relative.as_posix(),
        "file_sha256": _sha256(manifest_payload),
        "content_digest": content_digest(manifest),
        "bytes": len(manifest_payload),
        "snapshot_path": f"{SNAPSHOT_DIRECTORY}/{manifest_digest}",
    }
    candidate = {
        "amendment": manifest["amendment"],
        "family": manifest["family"],
        "fragments": candidate_refs["fragments"],
        "manifest": manifest_candidate_ref,
        "schema": CANDIDATE_SCHEMA,
        "sources": candidate_refs["sources"],
        "status": LIVE_STATUS,
        "tests": candidate_refs["tests"],
    }
    candidate["candidate_id"] = _candidate_id(
        candidate["family"],
        candidate["amendment"],
        candidate["manifest"],
        candidate_refs,
    )
    candidate["content_digest"] = content_digest(candidate)
    frozen_payloads.append(manifest_payload)
    for payload in frozen_payloads:
        _store_snapshot(repo_root, output_relative, payload)
    candidate_relative = output_relative / CANDIDATE_FILENAME
    _write_new_immutable(
        repo_root,
        candidate_relative,
        canonical_json(candidate),
        label="candidate",
    )
    return {
        "candidate_id": candidate["candidate_id"],
        "candidate_path": candidate_relative.as_posix(),
        "status": LIVE_STATUS,
    }


def _read_snapshot(root: Path, candidate_path: Path, snapshot_path: str) -> bytes:
    if not isinstance(snapshot_path, str) or "\x00" in snapshot_path:
        raise ValidationError("candidate snapshot path is malformed")
    snapshot = _normalized_relative(
        root,
        candidate_path.parent / snapshot_path,
        label="candidate snapshot",
    )
    if (
        snapshot.parent.name != SNAPSHOT_DIRECTORY
        or snapshot.parent.parent != candidate_path.parent
    ):
        raise ValidationError(f"candidate snapshot must be a fixed sibling: {snapshot_path}")
    descriptor, root_descriptor = _open_beneath(root, snapshot, label=snapshot_path)
    try:
        _require_regular(
            descriptor,
            label=snapshot_path,
            immutable=True,
            single_link=True,
        )
        return _read_descriptor(descriptor, label=snapshot_path)
    finally:
        _close(descriptor)
        _close(root_descriptor)


def _verify_reference(
    root: Path,
    candidate_path: Path,
    value: dict[str, Any],
    *,
    json_ref: bool,
    label: str,
) -> bytes:
    _normalized_relative(root, value["path"], label=label)
    expected_snapshot = _snapshot_relative(value["file_sha256"]).as_posix()
    if value["snapshot_path"] != expected_snapshot:
        raise ValidationError(f"{label}.snapshot_path does not match file_sha256")
    payload = _read_snapshot(root, candidate_path, value["snapshot_path"])
    if len(payload) != value["bytes"]:
        raise ValidationError(f"{label}.snapshot bytes mismatch")
    if _sha256(payload) != value["file_sha256"]:
        raise ValidationError(f"{label}.snapshot file_sha256 mismatch")
    if json_ref:
        parsed = _parse_json_bytes(payload, label=value["path"])
        if content_digest(parsed) != value["content_digest"]:
            raise ValidationError(f"{label}.content_digest mismatch")
    return payload


def check_candidate(
    candidate_path: Path,
    *,
    repo_root: Path = REPO_ROOT,
    history_only: bool = False,
) -> dict[str, str]:
    candidate_payload, candidate_relative = _read_file(
        repo_root,
        candidate_path,
        label="check_candidate.candidate",
    )
    candidate = _parse_json_bytes(candidate_payload, label=str(candidate_relative))
    _require_exact_keys(
        candidate,
        (
            "amendment",
            "candidate_id",
            "content_digest",
            "family",
            "fragments",
            "manifest",
            "schema",
            "sources",
            "status",
            "tests",
        ),
        label="candidate",
    )
    if candidate["schema"] != CANDIDATE_SCHEMA:
        raise ValidationError(f"unknown candidate schema: {candidate['schema']!r}")
    if candidate["status"] != LIVE_STATUS:
        raise ValidationError(f"invalid candidate status: {candidate['status']!r}")
    if content_digest(candidate) != candidate.get("content_digest"):
        raise ValidationError("candidate.content_digest mismatch")
    if not isinstance(candidate["family"], str) or not candidate["family"]:
        raise ValidationError("candidate.family must be a non-empty string")
    if not isinstance(candidate["amendment"], str) or not candidate["amendment"]:
        raise ValidationError("candidate.amendment must be a non-empty string")
    if not _is_digest(candidate["candidate_id"]):
        raise ValidationError("candidate.candidate_id must be a lowercase SHA-256")

    manifest_ref = _validate_candidate_ref(
        candidate["manifest"], json_ref=True, label="candidate.manifest"
    )
    refs: dict[str, list[dict[str, Any]]] = {}
    seen_paths: set[str] = {manifest_ref["path"]}
    for group in RAW_GROUPS:
        values = candidate[group]
        if not isinstance(values, list) or not values:
            raise ValidationError(f"candidate.{group} must be a non-empty list")
        normalized: list[dict[str, Any]] = []
        for index, value in enumerate(values):
            reference = _validate_candidate_ref(
                value,
                json_ref=group in JSON_GROUPS,
                label=f"candidate.{group}[{index}]",
            )
            if reference["path"] in seen_paths:
                raise ValidationError(f"duplicate candidate input path: {reference['path']}")
            seen_paths.add(reference["path"])
            normalized.append(reference)
        refs[group] = normalized

    manifest_payload = _verify_reference(
        repo_root,
        candidate_relative,
        manifest_ref,
        json_ref=True,
        label="candidate.manifest",
    )
    manifest = _parse_json_bytes(manifest_payload, label=manifest_ref["path"])
    manifest_refs = _validate_manifest(manifest, repo_root=repo_root)
    if manifest["family"] != candidate["family"]:
        raise ValidationError("manifest and candidate family mismatch")
    if manifest["amendment"] != candidate["amendment"]:
        raise ValidationError("manifest and candidate amendment mismatch")
    for group in RAW_GROUPS:
        expected_keys = (
            MANIFEST_JSON_REFERENCE_KEYS
            if group in JSON_GROUPS
            else MANIFEST_RAW_REFERENCE_KEYS
        )
        if manifest_refs[group] != [
            {key: value[key] for key in expected_keys} for value in refs[group]
        ]:
            raise ValidationError(f"manifest and candidate {group} mismatch")

    for group in RAW_GROUPS:
        for index, reference in enumerate(refs[group]):
            payload = _verify_reference(
                repo_root,
                candidate_relative,
                reference,
                json_ref=group in JSON_GROUPS,
                label=f"candidate.{group}[{index}]",
            )
            if history_only:
                continue
            live_payload, live_relative = _read_file(
                repo_root,
                reference["path"],
                label=f"live.{group}[{index}]",
            )
            if live_relative.as_posix() != reference["path"] or live_payload != payload:
                raise ValidationError(f"live logical path mismatch: {reference['path']}")

    if not history_only:
        live_manifest, live_relative = _read_file(
            repo_root,
            manifest_ref["path"],
            label="live.manifest",
        )
        if live_relative.as_posix() != manifest_ref["path"] or live_manifest != manifest_payload:
            raise ValidationError(f"live logical path mismatch: {manifest_ref['path']}")

    expected_id = _candidate_id(
        candidate["family"],
        candidate["amendment"],
        manifest_ref,
        refs,
    )
    if candidate["candidate_id"] != expected_id:
        raise ValidationError("candidate.candidate_id mismatch")
    return {
        "candidate_id": candidate["candidate_id"],
        "family": candidate["family"],
        "status": HISTORY_STATUS if history_only else LIVE_STATUS,
    }


def _parse_repo_root_path(value: str) -> Path:
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"repo root is not a directory: {value}")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    stage_parser = subparsers.add_parser("stage")
    stage_parser.add_argument("--repo-root", type=_parse_repo_root_path, default=REPO_ROOT)
    stage_parser.add_argument("--manifest", type=Path, required=True)
    stage_parser.add_argument("--output-dir", type=Path, required=True)

    candidate_parser = subparsers.add_parser("check-candidate")
    candidate_parser.add_argument("--repo-root", type=_parse_repo_root_path, default=REPO_ROOT)
    candidate_parser.add_argument("--candidate", type=Path, required=True)
    candidate_parser.add_argument("--history-only", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "stage":
            result: dict[str, str] = stage(
                args.manifest,
                args.output_dir,
                repo_root=args.repo_root,
            )
        else:
            result = check_candidate(
                args.candidate,
                repo_root=args.repo_root,
                history_only=args.history_only,
            )
    except ValidationError as exc:
        print(f"FAIL family_fragment_rebind: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
