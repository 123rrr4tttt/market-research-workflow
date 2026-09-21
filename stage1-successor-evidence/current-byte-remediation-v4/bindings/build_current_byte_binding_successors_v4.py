#!/usr/bin/env python3
# ruff: noqa: TRY003
"""Build the create-only zero-delta v4 current-byte binding bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BINDINGS_REL = Path("stage1-successor-evidence/current-byte-remediation-v4/bindings")
V3_REL = Path("stage1-successor-evidence/current-byte-remediation-v3/bindings")
REGISTRY_REL = BINDINGS_REL / "current-byte-binding-successors.v4.json"
MANIFEST_REL = BINDINGS_REL / "artifact-manifest.v4.json"
V3_REGISTRY_REL = V3_REL / "current-byte-binding-successors.v3.json"
V3_REGISTRY_SHA256 = "bcc60ffd01ef35eceb06ed87568b724a4107e26de8ea2b47ff9f1e5415bfad71"
V3_CONTENT_DIGEST = "1eb8dc20137afc09916df9a45b90a74c64a05935959a365daa48f0aa02caf6e2"
V3_SCHEMA = "mrw.current_byte_binding_successors.v3"
V3_RECORD_ID = "current-byte-binding-successors-v3"
REGISTRY_SCHEMA = "mrw.current_byte_binding_successors.v4"
REGISTRY_RECORD_ID = "current-byte-binding-successors-v4"
MANIFEST_SCHEMA = "mrw.current_byte_binding_successor_manifest.v4"
EXPECTED_SUCCESSOR_COUNT = 22

BUILDER_REL = BINDINGS_REL / Path(__file__).name
CHECKER_REL = BINDINGS_REL / "check_current_byte_binding_successors_v4.py"
TEST_REL = BINDINGS_REL / "test_current_byte_binding_successors_v4.py"
STATIC_RELS = (BUILDER_REL, CHECKER_REL, TEST_REL)

AUTHORITY = {
    "candidate_promotion": False,
    "cutover": False,
    "deployment": False,
    "external_delivery": False,
    "legacy_retirement": False,
    "live_provider": False,
    "production_canonical_write": False,
    "production_release": False,
}
AUTHORITY_CEILING = (
    "EXACT_BYTE_CORRESPONDENCE_ONLY_NO_CANDIDATE_PROMOTION_NO_STAGE0_REWRITE_"
    "NO_PRODUCTION_AUTHORITY"
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def pretty_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def with_content_digest(document: dict[str, Any]) -> dict[str, Any]:
    result = dict(document)
    result["content_digest"] = sha256(canonical_json(document))
    return result


def load_object_bytes(payload: bytes, *, label: str) -> dict[str, Any]:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise TypeError(f"JSON root must be an object: {label}")
    return value


def load_object(path: Path) -> dict[str, Any]:
    return load_object_bytes(path.read_bytes(), label=str(path))


def _validate_content_digest(document: dict[str, Any], *, label: str) -> None:
    body = {key: value for key, value in document.items() if key != "content_digest"}
    if document.get("content_digest") != sha256(canonical_json(body)):
        raise ValueError(f"{label} content digest drift")


def _require_regular_file(path: Path, *, label: str) -> bytes:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {path}")
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def validate_v3_predecessor(root: Path) -> dict[str, Any]:
    path = root / V3_REGISTRY_REL
    payload = _require_regular_file(path, label="v3 predecessor registry")
    if sha256(payload) != V3_REGISTRY_SHA256:
        raise ValueError("v3 predecessor registry byte drift")
    registry = load_object_bytes(payload, label=V3_REGISTRY_REL.as_posix())
    _validate_content_digest(registry, label="v3 predecessor registry")
    if (
        registry.get("schema") != V3_SCHEMA
        or registry.get("record_id") != V3_RECORD_ID
        or registry.get("content_digest") != V3_CONTENT_DIGEST
        or registry.get("authoritative") is not False
        or registry.get("authority") != AUTHORITY
        or registry.get("authority_ceiling") != AUTHORITY_CEILING
        or not isinstance(registry.get("successors"), list)
        or len(registry["successors"]) != EXPECTED_SUCCESSOR_COUNT
    ):
        raise ValueError("v3 predecessor registry identity drift")
    return registry


def build_registry(root: Path) -> dict[str, Any]:
    v3 = validate_v3_predecessor(root)
    return with_content_digest(
        {
            "schema": REGISTRY_SCHEMA,
            "record_id": REGISTRY_RECORD_ID,
            "status": "CURRENT_BYTES_BOUND_BY_ZERO_DELTA_SUCCESSOR_NOT_AUTHORITY",
            "authoritative": False,
            "authority": AUTHORITY,
            "authority_ceiling": AUTHORITY_CEILING,
            "extends": {
                "path": V3_REGISTRY_REL.as_posix(),
                "sha256": V3_REGISTRY_SHA256,
                "content_digest": V3_CONTENT_DIGEST,
                "schema": V3_SCHEMA,
                "record_id": V3_RECORD_ID,
                "mutation": False,
            },
            "inherited_successor_count": EXPECTED_SUCCESSOR_COUNT,
            "added_successor_count": 0,
            "new_snapshot_count": 0,
            "successors": v3["successors"],
            "limits": [
                "The v3 registry and all twenty-two successor rows remain byte-semantically "
                "unchanged and in the same order.",
                "This zero-delta successor adds no binding rows and creates no snapshot files.",
                "Fresh Stage 0 family candidates are outside this registry and are not generated or claimed here.",
                "Exact-byte correspondence grants no candidate promotion or production authority.",
                "PRODUCTION_RELEASE_NOT_AUTHORIZED",
            ],
        }
    )


def build_manifest(root: Path, registry_payload: bytes) -> dict[str, Any]:
    member_payloads = {REGISTRY_REL: registry_payload}
    for relative in STATIC_RELS:
        member_payloads[relative] = _require_regular_file(
            root / relative,
            label="v4 static bundle member",
        )
    members = [
        {
            "path": relative.as_posix(),
            "bytes": len(payload),
            "sha256": sha256(payload),
        }
        for relative, payload in sorted(member_payloads.items(), key=lambda item: item[0].as_posix())
    ]
    return with_content_digest(
        {
            "schema": MANIFEST_SCHEMA,
            "status": "COMPLETE_ZERO_DELTA_NOT_AUTHORITY",
            "authoritative": False,
            "authority": AUTHORITY,
            "authority_ceiling": AUTHORITY_CEILING,
            "extends": {
                "path": V3_REGISTRY_REL.as_posix(),
                "sha256": V3_REGISTRY_SHA256,
                "mutation": False,
            },
            "added_successor_count": 0,
            "new_snapshot_count": 0,
            "member_count": len(members),
            "members": members,
        }
    )


def expected_documents(root: Path) -> dict[Path, bytes]:
    registry_payload = pretty_json(build_registry(root))
    manifest_payload = pretty_json(build_manifest(root, registry_payload))
    return {
        REGISTRY_REL: registry_payload,
        MANIFEST_REL: manifest_payload,
    }


def _assert_non_symlink_directory(path: Path, *, label: str) -> None:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {path}")
    if not path.is_dir():
        raise ValueError(f"{label} must be an existing directory: {path}")


def preflight_publication(root: Path, documents: dict[Path, bytes]) -> None:
    _assert_non_symlink_directory(root, label="repository root")
    cursor = root
    for part in BINDINGS_REL.parts:
        cursor = cursor / part
        _assert_non_symlink_directory(cursor, label="v4 publication ancestor")
    for relative in documents:
        target = root / relative
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"create-only target exists: {relative}")


def _write_new_file(path: Path, payload: bytes) -> os.stat_result:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o644)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return os.fstat(descriptor)
    except BaseException:
        identity = os.fstat(descriptor)
        os.close(descriptor)
        descriptor = -1
        _unlink_if_identity(path, identity)
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _unlink_if_identity(path: Path, identity: os.stat_result) -> None:
    try:
        current = path.lstat()
    except FileNotFoundError:
        return
    if (
        stat.S_ISREG(current.st_mode)
        and current.st_dev == identity.st_dev
        and current.st_ino == identity.st_ino
    ):
        path.unlink()


def _rollback_created(created: list[tuple[Path, os.stat_result]]) -> None:
    for path, identity in reversed(created):
        _unlink_if_identity(path, identity)


def write_create_only(root: Path) -> None:
    documents = expected_documents(root)
    preflight_publication(root, documents)
    created: list[tuple[Path, os.stat_result]] = []
    try:
        # The manifest is last: its presence is the completion marker for the bundle.
        for relative in (REGISTRY_REL, MANIFEST_REL):
            path = root / relative
            identity = _write_new_file(path, documents[relative])
            created.append((path, identity))
    except BaseException:
        _rollback_created(created)
        raise


def check(root: Path) -> dict[str, Any]:
    expected = expected_documents(root)
    bundle_entries = list((root / BINDINGS_REL).rglob("*"))
    if any(path.is_symlink() for path in bundle_entries):
        raise ValueError("v4 binding bundle must not contain symlinks")
    actual = {
        path.relative_to(root)
        for path in bundle_entries
        if path.is_file() and "__pycache__" not in path.parts
    }
    allowed = set(STATIC_RELS) | set(expected)
    if actual != allowed:
        raise ValueError("v4 binding bundle contains missing or unexpected files")
    for relative, payload in expected.items():
        if (root / relative).read_bytes() != payload:
            raise ValueError(f"generated v4 artifact drift: {relative}")
    return {
        "status": "PASS",
        "inherited_successor_count": EXPECTED_SUCCESSOR_COUNT,
        "added_successor_count": 0,
        "new_snapshot_count": 0,
        "authority_ceiling": AUTHORITY_CEILING,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    if args.write:
        write_create_only(root)
    print(json.dumps(check(root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
