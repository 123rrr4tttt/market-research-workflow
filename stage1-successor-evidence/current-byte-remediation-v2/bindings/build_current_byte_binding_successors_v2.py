#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Build the create-only v2 current-byte binding successor bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BINDINGS_REL = Path("stage1-successor-evidence/current-byte-remediation-v2/bindings")
V1_REL = Path("stage1-successor-evidence/current-byte-remediation-v1/bindings")
REGISTRY_REL = BINDINGS_REL / "current-byte-binding-successors.v2.json"
MANIFEST_REL = BINDINGS_REL / "artifact-manifest.v2.json"

V1_REGISTRY_REL = V1_REL / "current-byte-binding-successors.v1.json"
V1_REGISTRY_SHA256 = "7e2a6d84ef37174bf52142a9e2560470a24e60c84549962e856688f4702e401b"
V1_CONTENT_DIGEST = "8d001e30dfc0207e117fa74062796b87a4d245e11c74c36f14b5e9b29d036fdb"
V1_MEMBER_HASHES = {
    V1_REL / "artifact-manifest.v1.json": "b4662dcf3d56fd08a892931def5fcef666a675a68052f6199f98b39951340805",
    V1_REL / "build_current_byte_binding_successors.py": "7bb0b63c94a5a05b6480ee3567f5c73d0ec8310d89105f60acd30164c0dbf79b",
    V1_REL / "check_current_byte_binding_successors.py": "fd747f05fd5addc20957e8b7447250b2d8368423dcc6d99d9364a8cdd28ac91c",
    V1_REL / "current-byte-binding-successors.v1.json": V1_REGISTRY_SHA256,
    V1_REL / "test_current_byte_binding_successors.py": "022b2a812c9f250e9cdfef2a7347a64969e3e7b0636ee24ceb859fc9fce7cb54",
}

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

NATIVE_PATH = "main/backend/app/services/agent_core/native_provider.py"
SPEC_PREDECESSOR = "5cff4695fa1aa9455d3090ae7e8ca51d414a3e7e93599243ccefccd35331b566"
B23_SUCCESSOR = "e3735f8e74c81f5e1a979bb993926097500f97a2c64065c60f3d5bba2d8e1428"
CURRENT_SUCCESSOR = "1daddedc2fe8a435c062fa66019e00db2b47aeb2e88d8fce97e7dfe3e8bd4cf5"
CURRENT_BYTES = 18697
CURRENT_LINES = 366
CURRENT_GIT_BLOB_SHA1 = "a8d2c0799ef7ca8ae0d32fa5fc9d87b0aca22782"

P = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/"
    "exact-byte-rebind/stage-b23-2026-09-05"
)
I1_FRAGMENT = f"{P}/fragments/I1.json"
I1_MANIFEST = f"{P}/manifests/I1.json"
I1_CANDIDATE = f"{P}/candidates/I1/candidate.v2.json"
PREDECESSOR_DECLARATIONS = [
    {
        "artifact": I1_FRAGMENT,
        "artifact_sha256": "8c99a91c0891589073318c9b872d977ec95e37e8e206e66255c88f72578d9110",
        "json_pointer": "/bindings/69",
        "hash_field": "successor_sha256",
        "bound_sha256": B23_SUCCESSOR,
        "cell_id": "C6.1",
    },
    {
        "artifact": I1_FRAGMENT,
        "artifact_sha256": "8c99a91c0891589073318c9b872d977ec95e37e8e206e66255c88f72578d9110",
        "json_pointer": "/bindings/74",
        "hash_field": "successor_sha256",
        "bound_sha256": B23_SUCCESSOR,
        "cell_id": "C6.2",
    },
    {
        "artifact": I1_MANIFEST,
        "artifact_sha256": "00b0f89e5278f6aee3f5298e5b466d55326292a3fb3421c84daab5740e990521",
        "json_pointer": "/sources/108",
        "hash_field": "file_sha256",
        "bound_sha256": B23_SUCCESSOR,
    },
    {
        "artifact": I1_CANDIDATE,
        "artifact_sha256": "bb4fc787fbc0d1959f04797e45a99b3da1d00a544501ab30abcc5ff017af0e7e",
        "json_pointer": "/sources/108",
        "hash_field": "file_sha256",
        "bound_sha256": B23_SUCCESSOR,
    },
]
SPEC_BINDINGS = [
    {
        "cell_id": "C6.1",
        "spec_path": (
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/"
            "capability-specs/C6.1.v1.json"
        ),
        "spec_sha256": "a7da8f3ad74f1bdd0b7aa9900d45f7556811e3968698346ca2a3bf955acafbd4",
        "fragment_json_pointer": "/bindings/69",
    },
    {
        "cell_id": "C6.2",
        "spec_path": (
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/"
            "capability-specs/C6.2.v1.json"
        ),
        "spec_sha256": "73bdfadc766b005c6459135ddb8169c1f024d9fcda72e0aa89ed202d5b7437fe",
        "fragment_json_pointer": "/bindings/74",
    },
]


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def pretty_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()


def with_content_digest(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["content_digest"] = sha256(canonical_json(value))
    return result


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def resolve_pointer(value: Any, pointer: str) -> Any:
    current = value
    for raw in pointer.removeprefix("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def validate_inputs(root: Path) -> tuple[dict[str, Any], bytes]:
    for relative, expected in V1_MEMBER_HASHES.items():
        payload = (root / relative).read_bytes()
        if sha256(payload) != expected:
            raise ValueError(f"v1 predecessor bundle drift: {relative}")
    v1 = load_object(root / V1_REGISTRY_REL)
    if (
        v1.get("schema") != "mrw.current_byte_binding_successors.v1"
        or v1.get("record_id") != "current-byte-binding-successors-v1"
        or v1.get("content_digest") != V1_CONTENT_DIGEST
        or v1.get("authoritative") is not False
        or len(v1.get("successors", [])) != 10
    ):
        raise ValueError("v1 predecessor registry identity drift")

    payload = (root / NATIVE_PATH).read_bytes()
    if sha256(payload) != CURRENT_SUCCESSOR:
        raise ValueError("native provider current source hash mismatch")
    if len(payload) != CURRENT_BYTES or payload.count(b"\n") != CURRENT_LINES:
        raise ValueError("native provider current source size mismatch")

    for reference in PREDECESSOR_DECLARATIONS:
        artifact = (root / reference["artifact"]).read_bytes()
        if sha256(artifact) != reference["artifact_sha256"]:
            raise ValueError(f"B23 predecessor artifact drift: {reference['artifact']}")
        bound = resolve_pointer(json.loads(artifact), reference["json_pointer"])
        if bound[reference["hash_field"]] != reference["bound_sha256"]:
            raise ValueError(
                f"B23 predecessor pointer drift: {reference['artifact']}"
                f"{reference['json_pointer']}"
            )
        if bound.get("path") != NATIVE_PATH:
            raise ValueError("B23 native provider logical path drift")

    for spec_binding in SPEC_BINDINGS:
        spec_payload = (root / spec_binding["spec_path"]).read_bytes()
        if sha256(spec_payload) != spec_binding["spec_sha256"]:
            raise ValueError(f"I1 spec drift: {spec_binding['cell_id']}")
        binding = resolve_pointer(
            json.loads((root / I1_FRAGMENT).read_bytes()),
            spec_binding["fragment_json_pointer"],
        )
        expected = {
            "cell_id": spec_binding["cell_id"],
            "binding_group": "source_bindings",
            "path": NATIVE_PATH,
            "role": "legacy_donor_c6_2",
            "predecessor_sha256": SPEC_PREDECESSOR,
            "successor_sha256": B23_SUCCESSOR,
            "spec_path": spec_binding["spec_path"],
            "spec_sha256": spec_binding["spec_sha256"],
            "bytes": 18604,
        }
        if binding != expected:
            raise ValueError(f"I1 B23 binding identity drift: {spec_binding['cell_id']}")
    return v1, payload


def shared_native_successor() -> dict[str, Any]:
    return {
        "successor_id": "i1-c6-native-provider-current-bytes-v2",
        "relation": "I1_SHARED_EXACT_BINDING_SUCCESSOR",
        "family": "I1",
        "cell_ids": ["C6.1", "C6.2"],
        "binding_group": "source_bindings",
        "role": "legacy_donor_c6_2",
        "source_path": NATIVE_PATH,
        "prior_spec_predecessor_sha256": SPEC_PREDECESSOR,
        "predecessor_sha256": B23_SUCCESSOR,
        "successor_sha256": CURRENT_SUCCESSOR,
        "bytes": CURRENT_BYTES,
        "lines": CURRENT_LINES,
        "git_blob_sha1_working_tree": CURRENT_GIT_BLOB_SHA1,
        "snapshot_path": f"snapshots/{CURRENT_SUCCESSOR}",
        "spec_bindings": SPEC_BINDINGS,
        "predecessor_declarations": PREDECESSOR_DECLARATIONS,
        "ordered_sha256_chain": [
            {"stage": "SPEC_PREDECESSOR", "sha256": SPEC_PREDECESSOR},
            {"stage": "B23_SUCCESSOR", "sha256": B23_SUCCESSOR},
            {"stage": "CURRENT_WORKING_TREE_SUCCESSOR", "sha256": CURRENT_SUCCESSOR},
        ],
        "change_class": "NONSEMANTIC_SECURITY_INTENT_ANNOTATION",
        "qualification": "EXACT_BYTES_ONLY_NOT_AUTHORITY",
    }


def build_documents(root: Path) -> dict[Path, bytes]:
    v1, native_payload = validate_inputs(root)
    registry = with_content_digest(
        {
            "schema": "mrw.current_byte_binding_successors.v2",
            "record_id": "current-byte-binding-successors-v2",
            "status": "CURRENT_BYTES_BOUND_BY_ADDITIVE_SUCCESSORS_NOT_AUTHORITY",
            "authoritative": False,
            "authority": AUTHORITY,
            "authority_ceiling": AUTHORITY_CEILING,
            "extends": {
                "path": V1_REGISTRY_REL.as_posix(),
                "sha256": V1_REGISTRY_SHA256,
                "content_digest": V1_CONTENT_DIGEST,
                "schema": "mrw.current_byte_binding_successors.v1",
                "record_id": "current-byte-binding-successors-v1",
                "mutation": False,
            },
            "inherited_successor_count": 10,
            "successors": [*v1["successors"], shared_native_successor()],
            "limits": [
                "The v1 registry, records, checkers, manifests, and snapshots remain unchanged.",
                "The shared C6 row resolves one candidate source and expands to two I1 cell bindings.",
                "Exact-byte correspondence grants no candidate promotion or production authority.",
                "PRODUCTION_RELEASE_NOT_AUTHORIZED",
            ],
        }
    )
    return {
        REGISTRY_REL: pretty_json(registry),
        BINDINGS_REL / "snapshots" / CURRENT_SUCCESSOR: native_payload,
    }


def build_manifest(root: Path, documents: dict[Path, bytes]) -> bytes:
    static_members = (
        BINDINGS_REL / "build_current_byte_binding_successors_v2.py",
        BINDINGS_REL / "check_current_byte_binding_successors_v2.py",
        BINDINGS_REL / "test_current_byte_binding_successors_v2.py",
    )
    members = [
        {"path": path.as_posix(), "bytes": len(payload), "sha256": sha256(payload)}
        for path, payload in documents.items()
    ]
    for path in static_members:
        payload = (root / path).read_bytes()
        members.append({"path": path.as_posix(), "bytes": len(payload), "sha256": sha256(payload)})
    members.sort(key=lambda item: item["path"])
    return pretty_json(
        with_content_digest(
            {
                "schema": "mrw.current_byte_binding_successor_manifest.v2",
                "status": "COMPLETE_NOT_AUTHORITY",
                "authoritative": False,
                "authority": AUTHORITY,
                "authority_ceiling": AUTHORITY_CEILING,
                "member_count": len(members),
                "members": members,
            }
        )
    )


def expected_documents(root: Path) -> dict[Path, bytes]:
    documents = build_documents(root)
    documents[MANIFEST_REL] = build_manifest(root, documents)
    return documents


def check(root: Path) -> dict[str, Any]:
    documents = expected_documents(root)
    static_paths = {
        BINDINGS_REL / "build_current_byte_binding_successors_v2.py",
        BINDINGS_REL / "check_current_byte_binding_successors_v2.py",
        BINDINGS_REL / "test_current_byte_binding_successors_v2.py",
    }
    actual_paths = {
        path.relative_to(root)
        for path in (root / BINDINGS_REL).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    if actual_paths != set(documents) | static_paths:
        raise ValueError("v2 binding bundle contains missing or unexpected files")
    for relative, expected in documents.items():
        if (root / relative).read_bytes() != expected:
            raise ValueError(f"generated v2 artifact drift: {relative}")
    registry = load_object(root / REGISTRY_REL)
    return {
        "status": "PASS",
        "source_count": len({row["source_path"] for row in registry["successors"]}),
        "successor_count": len(registry["successors"]),
        "expanded_i1_binding_count": sum(
            len(row.get("cell_ids", [row.get("cell_id")]))
            for row in registry["successors"]
            if row.get("relation")
            in {"I1_EXACT_BINDING_SUCCESSOR", "I1_SHARED_EXACT_BINDING_SUCCESSOR"}
        ),
        "authority_ceiling": AUTHORITY_CEILING,
    }


def write_create_only(root: Path) -> None:
    for relative, payload in expected_documents(root).items():
        target = root / relative
        if target.exists():
            if target.read_bytes() != payload:
                raise ValueError(f"create-only target differs: {relative}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        if target.parent.name == "snapshots":
            os.chmod(target, 0o444)


def main() -> int:
    parser = argparse.ArgumentParser()
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
