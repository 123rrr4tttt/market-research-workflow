#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Build the create-only current-byte binding successor evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BINDINGS_REL = Path("stage1-successor-evidence/current-byte-remediation-v1/bindings")
BINDINGS_ROOT = REPOSITORY_ROOT / BINDINGS_REL

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

CURRENT_SOURCES = {
    "main/backend/app/celery_app.py": {
        "sha256": "013ddec4e03a28e9f15211a346db9481b624cb395b05cf8b05d741e54281b645",
        "bytes": 1490,
        "lines": 43,
        "git_blob_sha1": "a2282bf03b979c0db069b691c21471020c7f6fe7",
    },
    "main/backend/app/api/process.py": {
        "sha256": "5687389bdad57881a0f96543ba32ac4eaaaeef0f7939f8f7e36e16316ed7ee61",
        "bytes": 56853,
        "lines": 1509,
        "git_blob_sha1": "d2074ef04369db5125c8aab9147eaf4f8a5c7dec",
    },
    "main/backend/app/models/base.py": {
        "sha256": "173d95722cef7411f4b1e4606f8dbdbf850d74fbae9847b942b13be1e56c8308",
        "bytes": 13390,
        "lines": 334,
        "git_blob_sha1": "374fdc5f6e1505fe68ec575c533fbd3df0f86354",
    },
    "main/backend/app/services/workflow_graph/runtime.py": {
        "sha256": "15c22d898b1c90205c43585aae4e3d83a425782e57676926507b92e6b8fb68ca",
        "bytes": 16319,
        "lines": 429,
        "git_blob_sha1": "e6cec400462f3ffbc6763fe8c89123edb3ff7382",
    },
}

P = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
R = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release"
)


def ref(
    artifact: str,
    artifact_sha256: str,
    pointer: str,
    hash_field: str,
    bound_sha256: str,
) -> dict[str, str]:
    return {
        "artifact": artifact,
        "artifact_sha256": artifact_sha256,
        "json_pointer": pointer,
        "hash_field": hash_field,
        "bound_sha256": bound_sha256,
    }


PROCESS_OLD = "790b6cb90086d6ba1171309e572b7e7be4c906db3705170dbd4a12ca7ea16c63"
CELERY_SPEC_OLD = "5f28badfb562179370c4042e2a9a7ef5a8f84933c961755aa86d6c6b8be1b380"
CELERY_B23 = "6766bc85cb01afd79b8f91793ec2b6020ee45ea0d4797ef0a589076072f2d49d"
BASE_C7_OLD = "5b81ef9a41bf8e21c87f2d7a0e0239a4afa14c46de0eb7b37601d217422654f4"
BASE_ALL_LINES_OLD = "80e9683f8de422956eef020d4a657b7cc41b8843aaa4e8825ab87c4e3f8c32cd"
RUNTIME_OLD = "cb4ae041aef79ce9b8d68a14615c4a85f1b9182319380a5462133534eeca67fc"

DECLARATIONS = {
    "c5_process": [
        ref(f"{P}/exact-byte-rebind/stage-b19-2026-09-05/fragments/C5.json", "0b3d83914cf7de356e28a51dbfb5e7836d09266f315b4c26f8eab8bcbf26e30f", "/source_bindings/10", "sha256", PROCESS_OLD),
        ref(f"{P}/exact-byte-rebind/stage-b19-2026-09-05/manifests/C5.json", "f1ae6a1678b83d75337244d200ab5b584f684180ef4c7e97076cd3573124b11f", "/sources/6", "file_sha256", PROCESS_OLD),
        ref(f"{P}/exact-byte-rebind/stage-b19-2026-09-05/candidates/C5/candidate.v2.json", "a2ddbb2ae28b330a04e52aff2030d1f8edaa1b77b4c6d7a37a48f64a0048aad2", "/sources/6", "file_sha256", PROCESS_OLD),
        ref(f"{P}/exact-byte-rebind/stage-b23-2026-09-05/fragments/C5.json", "0b3d83914cf7de356e28a51dbfb5e7836d09266f315b4c26f8eab8bcbf26e30f", "/source_bindings/10", "sha256", PROCESS_OLD),
        ref(f"{P}/exact-byte-rebind/stage-b23-2026-09-05/manifests/C5.json", "f68c123409aeb0935cd93e3072a05f50c8f2637868d5b92847cd95fb018f4c76", "/sources/6", "file_sha256", PROCESS_OLD),
        ref(f"{P}/exact-byte-rebind/stage-b23-2026-09-05/candidates/C5/candidate.v2.json", "919bbbbf66f7b5959b2407bbf7a488efecbd781844599d5b5ad945180f7dbc47", "/sources/6", "file_sha256", PROCESS_OLD),
    ],
    "i1_process": [
        ref(f"{P}/exact-byte-rebind/stage-b23-2026-09-05/fragments/I1.json", "8c99a91c0891589073318c9b872d977ec95e37e8e206e66255c88f72578d9110", "/bindings/63", "successor_sha256", PROCESS_OLD),
        ref(f"{P}/exact-byte-rebind/stage-b23-2026-09-05/manifests/I1.json", "00b0f89e5278f6aee3f5298e5b466d55326292a3fb3421c84daab5740e990521", "/sources/96", "file_sha256", PROCESS_OLD),
        ref(f"{P}/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/candidate.v2.json", "bb4fc787fbc0d1959f04797e45a99b3da1d00a544501ab30abcc5ff017af0e7e", "/sources/96", "file_sha256", PROCESS_OLD),
    ],
    "i1_celery_app": [
        ref(f"{P}/exact-byte-rebind/stage-b23-2026-09-05/fragments/I1.json", "8c99a91c0891589073318c9b872d977ec95e37e8e206e66255c88f72578d9110", "/bindings/64", "successor_sha256", CELERY_B23),
        ref(f"{P}/exact-byte-rebind/stage-b23-2026-09-05/manifests/I1.json", "00b0f89e5278f6aee3f5298e5b466d55326292a3fb3421c84daab5740e990521", "/sources/98", "file_sha256", CELERY_B23),
        ref(f"{P}/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/candidate.v2.json", "bb4fc787fbc0d1959f04797e45a99b3da1d00a544501ab30abcc5ff017af0e7e", "/sources/98", "file_sha256", CELERY_B23),
    ],
    "c7_base": [
        ref(f"{P}/exact-byte-rebind/stage-b19-2026-09-05/fragments/C7.json", "b1bdc5524461cf84638f3ec86dbb68d5e2d5a4cc164bbc4f277f26d7457a7aa1", "/source_bindings/5", "sha256", BASE_C7_OLD),
        ref(f"{P}/exact-byte-rebind/stage-b19-2026-09-05/manifests/C7.json", "8c697b0736bbb0b1083707a559d4a1d22bcf5a4d185dc7909b8bb3c21ec4662c", "/sources/4", "file_sha256", BASE_C7_OLD),
        ref(f"{P}/exact-byte-rebind/stage-b19-2026-09-05/candidates/C7/candidate.v2.json", "630e2bb6d77b5f6de24357e331c5dd8fcb31cf9135d400187ce71f01058e1c6b", "/sources/4", "file_sha256", BASE_C7_OLD),
        ref(f"{P}/exact-byte-rebind/stage-b23-2026-09-05/fragments/C7.json", "6efc59fb473a2b2465249289343cfe956bbc9559f72bda25090e922f704e3222", "/source_bindings/5", "sha256", BASE_C7_OLD),
        ref(f"{P}/exact-byte-rebind/stage-b23-2026-09-05/manifests/C7.json", "cef04d5a729154d8bf11bab1ed7323ce868802ea94524602fe180be8e60ba75f", "/sources/4", "file_sha256", BASE_C7_OLD),
        ref(f"{P}/exact-byte-rebind/stage-b23-2026-09-05/candidates/C7/candidate.v2.json", "376627c0abc0c60f78b57ee013c3b21b06d4260bbd0c1fd3c7b184e0f313d129", "/sources/4", "file_sha256", BASE_C7_OLD),
    ],
    "all_lines_process": [
        ref(f"{P}/all-lines-investigation/AllLinesDonorByteClosure.v1.json", "fc1009c172d3880795dbdaebb90d8de41a6359161d5b86a89315ed4abc4077ed", "/entries/20", "byte_hash_sha256", PROCESS_OLD),
        ref(f"{P}/all-lines-investigation/AllLinesSuccessorMovementInventory.v1.json", "08fad9f59a5c588ca86085410efc792d33114903d4723038f50f46c0f858510d", "/movements/4/donor_byte_closure_refs/4", "sha256", PROCESS_OLD),
        ref(f"{P}/all-lines-investigation/AllLinesSuccessorMovementInventory.v1.json", "08fad9f59a5c588ca86085410efc792d33114903d4723038f50f46c0f858510d", "/movements/7/donor_byte_closure_refs/1", "sha256", PROCESS_OLD),
    ],
    "all_lines_base": [
        ref(f"{P}/all-lines-investigation/AllLinesDonorByteClosure.v1.json", "fc1009c172d3880795dbdaebb90d8de41a6359161d5b86a89315ed4abc4077ed", "/entries/37", "byte_hash_sha256", BASE_ALL_LINES_OLD),
    ],
    "all_lines_runtime": [
        ref(f"{P}/all-lines-investigation/AllLinesDonorByteClosure.v1.json", "fc1009c172d3880795dbdaebb90d8de41a6359161d5b86a89315ed4abc4077ed", "/entries/172", "byte_hash_sha256", RUNTIME_OLD),
        ref(f"{P}/all-lines-investigation/AllLinesSuccessorMovementInventory.v1.json", "08fad9f59a5c588ca86085410efc792d33114903d4723038f50f46c0f858510d", "/movements/6/donor_byte_closure_refs/12", "sha256", RUNTIME_OLD),
    ],
    "stage0_c5": [
        ref(f"{R}/stage0-evidence/functorial-refactor-completion.v3.json", "0eac6b6d61c339e55a73b394d97abc9e70ae8409df893ab99371e85703625491", "/bindings/current_candidates/3", "file_sha256", "a2ddbb2ae28b330a04e52aff2030d1f8edaa1b77b4c6d7a37a48f64a0048aad2"),
        ref(f"{R}/stage0-evidence/functorial-refactor-completion.v4.json", "4911df1c6450d9802ac7bd6b0669ef3a7343e3ce308d33f0a46dde2c4cb62dda", "/bindings/current_candidates/3", "file_sha256", "a2ddbb2ae28b330a04e52aff2030d1f8edaa1b77b4c6d7a37a48f64a0048aad2"),
    ],
    "stage0_c7": [
        ref(f"{R}/stage0-evidence/functorial-refactor-completion.v3.json", "0eac6b6d61c339e55a73b394d97abc9e70ae8409df893ab99371e85703625491", "/bindings/current_candidates/5", "file_sha256", "630e2bb6d77b5f6de24357e331c5dd8fcb31cf9135d400187ce71f01058e1c6b"),
        ref(f"{R}/stage0-evidence/functorial-refactor-completion.v4.json", "4911df1c6450d9802ac7bd6b0669ef3a7343e3ce308d33f0a46dde2c4cb62dda", "/bindings/current_candidates/5", "file_sha256", "630e2bb6d77b5f6de24357e331c5dd8fcb31cf9135d400187ce71f01058e1c6b"),
    ],
    "production_process": [
        ref(f"{R}/stage1-evidence/production-contract-implementation.v1.json", "3f5c745ce8253522fa7e3728ba112ed41c80f3b6aa7409ddf028621c6ae07f31", "/bindings/required_files/source/80", "sha256", PROCESS_OLD),
    ],
}


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


def resolve_pointer(value: Any, pointer: str) -> Any:
    current = value
    for raw in pointer.removeprefix("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def validate_inputs(root: Path) -> dict[str, bytes]:
    source_bytes: dict[str, bytes] = {}
    for relative, expected in CURRENT_SOURCES.items():
        payload = (root / relative).read_bytes()
        if sha256(payload) != expected["sha256"]:
            raise ValueError(f"current source hash mismatch: {relative}")
        if len(payload) != expected["bytes"] or payload.count(b"\n") != expected["lines"]:
            raise ValueError(f"current source size mismatch: {relative}")
        source_bytes[relative] = payload
    for refs in DECLARATIONS.values():
        for item in refs:
            payload = (root / item["artifact"]).read_bytes()
            if sha256(payload) != item["artifact_sha256"]:
                raise ValueError(f"predecessor artifact drift: {item['artifact']}")
            value = json.loads(payload)
            bound = resolve_pointer(value, item["json_pointer"])
            if bound[item["hash_field"]] != item["bound_sha256"]:
                raise ValueError(
                    f"predecessor pointer drift: {item['artifact']}{item['json_pointer']}"
                )
    celery_binding = resolve_pointer(
        json.loads((root / DECLARATIONS["i1_celery_app"][0]["artifact"]).read_bytes()),
        "/bindings/64",
    )
    expected_celery_binding = {
        "binding_group": "source_bindings",
        "bytes": 756,
        "cell_id": "C5.4",
        "path": "main/backend/app/celery_app.py",
        "predecessor_sha256": CELERY_SPEC_OLD,
        "role": "legacy_donor_c5_4_normative",
        "spec_path": f"{P}/capability-specs/C5.4.v1.json",
        "spec_sha256": "2ed59f58d051d74a76cd38a7721f2c484465f841b4d6646eb95277d3a34f13dd",
        "successor_sha256": CELERY_B23,
    }
    if celery_binding != expected_celery_binding:
        raise ValueError("celery_app B23 binding identity or predecessor chain drift")
    return source_bytes


def successor(
    successor_id: str,
    relation: str,
    source_path: str,
    predecessor_sha256: str,
    declaration_group: str,
    **extra: Any,
) -> dict[str, Any]:
    current = CURRENT_SOURCES[source_path]
    return {
        "successor_id": successor_id,
        "relation": relation,
        "source_path": source_path,
        "predecessor_sha256": predecessor_sha256,
        "successor_sha256": current["sha256"],
        "bytes": current["bytes"],
        "lines": current["lines"],
        "snapshot_path": f"snapshots/{current['sha256']}",
        "predecessor_declarations": DECLARATIONS[declaration_group],
        **extra,
    }


def build_documents(root: Path) -> dict[Path, bytes]:
    source_bytes = validate_inputs(root)
    closure = with_content_digest(
        {
            "schema": "mrw.functorial_successor.all_lines_donor_byte_closure.v2",
            "record_id": "current-byte-all-lines-closure-v2",
            "status": "OBSERVED_BYTE_CLOSURE_NOT_PROMOTION",
            "authoritative": False,
            "authority": AUTHORITY,
            "authority_ceiling": AUTHORITY_CEILING,
            "extends": {
                "path": f"{P}/all-lines-investigation/AllLinesDonorByteClosure.v1.json",
                "sha256": "fc1009c172d3880795dbdaebb90d8de41a6359161d5b86a89315ed4abc4077ed",
                "mutation": False,
            },
            "entries": [
                {
                    "path": source_path,
                    "byte_hash_sha256": CURRENT_SOURCES[source_path]["sha256"],
                    "byte_hash_kind": "sha256_of_current_working_tree_bytes",
                    "git_blob_sha1_working_tree": CURRENT_SOURCES[source_path]["git_blob_sha1"],
                    "bytes": CURRENT_SOURCES[source_path]["bytes"],
                    "lines": CURRENT_SOURCES[source_path]["lines"],
                    "snapshot_path": f"snapshots/{CURRENT_SOURCES[source_path]['sha256']}",
                    "predecessor_declarations": DECLARATIONS[group],
                }
                for source_path, group in (
                    ("main/backend/app/api/process.py", "all_lines_process"),
                    ("main/backend/app/models/base.py", "all_lines_base"),
                    ("main/backend/app/services/workflow_graph/runtime.py", "all_lines_runtime"),
                )
            ],
            "limits": [
                "This v2 record is an additive current-byte projection; v1 remains immutable history.",
                "Byte correspondence does not establish semantic acceptance or production authority.",
                "PRODUCTION_RELEASE_NOT_AUTHORIZED",
            ],
        }
    )
    closure_bytes = pretty_json(closure)
    registry = with_content_digest(
        {
            "schema": "mrw.current_byte_binding_successors.v1",
            "record_id": "current-byte-binding-successors-v1",
            "status": "CURRENT_BYTES_BOUND_BY_ADDITIVE_SUCCESSORS_NOT_AUTHORITY",
            "authoritative": False,
            "authority": AUTHORITY,
            "authority_ceiling": AUTHORITY_CEILING,
            "all_lines_successor": {
                "path": f"{BINDINGS_REL}/current-byte-all-lines-closure.v2.json",
                "sha256": sha256(closure_bytes),
                "content_digest": closure["content_digest"],
            },
            "successors": [
                successor("c5-process-current-bytes-v1", "C5_SOURCE_BINDING_SUCCESSOR", "main/backend/app/api/process.py", PROCESS_OLD, "c5_process", family="C5", cell_id="C5.4", role="legacy_donor_c5_4_supplementary"),
                successor("i1-c5-4-process-current-bytes-v1", "I1_EXACT_BINDING_SUCCESSOR", "main/backend/app/api/process.py", PROCESS_OLD, "i1_process", family="I1", cell_id="C5.4", binding_group="source_bindings", role="legacy_donor_c5_4_supplementary", prior_spec_predecessor_sha256="d3eab110965741ed8c44e2eac31b607675f4102b26679c3ac68b72b8d7addbdc"),
                successor("i1-c5-4-celery-app-current-bytes-v1", "I1_EXACT_BINDING_SUCCESSOR", "main/backend/app/celery_app.py", CELERY_B23, "i1_celery_app", family="I1", cell_id="C5.4", binding_group="source_bindings", role="legacy_donor_c5_4_normative", prior_spec_predecessor_sha256=CELERY_SPEC_OLD, ordered_sha256_chain=[{"stage": "SPEC_PREDECESSOR", "sha256": CELERY_SPEC_OLD}, {"stage": "B23_SUCCESSOR", "sha256": CELERY_B23}, {"stage": "CURRENT_WORKING_TREE_SUCCESSOR", "sha256": CURRENT_SOURCES["main/backend/app/celery_app.py"]["sha256"]}]),
                successor("stage0-c5-process-current-bytes-v1", "STAGE0_V3_V4_C5_DECLARATION_SUCCESSOR", "main/backend/app/api/process.py", PROCESS_OLD, "stage0_c5", family="C5", stage0_record_mutated=False),
                successor("production-contract-process-current-bytes-v1", "PRODUCTION_CONTRACT_SOURCE_BINDING_SUCCESSOR", "main/backend/app/api/process.py", PROCESS_OLD, "production_process", production_contract_mutated=False),
                successor("c7-models-base-current-bytes-v1", "C7_SOURCE_BINDING_SUCCESSOR", "main/backend/app/models/base.py", BASE_C7_OLD, "c7_base", family="C7", role="frozen_locator_db_retry"),
                successor("stage0-c7-models-base-current-bytes-v1", "STAGE0_V3_V4_C7_DECLARATION_SUCCESSOR", "main/backend/app/models/base.py", BASE_C7_OLD, "stage0_c7", family="C7", stage0_record_mutated=False),
                successor("all-lines-process-current-bytes-v1", "ALL_LINES_V2_ENTRY_SUCCESSOR", "main/backend/app/api/process.py", PROCESS_OLD, "all_lines_process"),
                successor("all-lines-models-base-current-bytes-v1", "ALL_LINES_V2_ENTRY_SUCCESSOR", "main/backend/app/models/base.py", BASE_ALL_LINES_OLD, "all_lines_base"),
                successor("all-lines-workflow-runtime-current-bytes-v1", "ALL_LINES_V2_ENTRY_SUCCESSOR", "main/backend/app/services/workflow_graph/runtime.py", RUNTIME_OLD, "all_lines_runtime"),
            ],
            "declaration_alignment": {
                "stage0_v3": {"path": f"{R}/stage0-evidence/functorial-refactor-completion.v3.json", "sha256": "0eac6b6d61c339e55a73b394d97abc9e70ae8409df893ab99371e85703625491", "preserved": True},
                "stage0_v4": {"path": f"{R}/stage0-evidence/functorial-refactor-completion.v4.json", "sha256": "4911df1c6450d9802ac7bd6b0669ef3a7343e3ce308d33f0a46dde2c4cb62dda", "preserved": True},
                "b19_and_b23_candidates": "IMMUTABLE_PREDECESSOR_DECLARATIONS",
                "current_projection": "THIS_VERSIONED_SUCCESSOR_REGISTRY",
            },
            "limits": [
                "No frozen fragment, manifest, candidate, contract, Stage0 record, or AllLines v1 record was overwritten.",
                "The registry resolves only the enumerated current-byte drift and grants no promotion.",
                "PRODUCTION_RELEASE_NOT_AUTHORIZED",
            ],
        }
    )
    documents: dict[Path, bytes] = {
        BINDINGS_REL / "current-byte-all-lines-closure.v2.json": closure_bytes,
        BINDINGS_REL / "current-byte-binding-successors.v1.json": pretty_json(registry),
    }
    for source_path, payload in source_bytes.items():
        documents[BINDINGS_REL / "snapshots" / CURRENT_SOURCES[source_path]["sha256"]] = payload
    return documents


def build_manifest(root: Path, documents: dict[Path, bytes]) -> bytes:
    static_members = (
        BINDINGS_REL / "build_current_byte_binding_successors.py",
        BINDINGS_REL / "check_current_byte_binding_successors.py",
        BINDINGS_REL / "test_current_byte_binding_successors.py",
    )
    members = [
        {"path": path.as_posix(), "bytes": len(payload), "sha256": sha256(payload)}
        for path, payload in sorted(documents.items(), key=lambda item: item[0].as_posix())
    ]
    for path in static_members:
        payload = (root / path).read_bytes()
        members.append({"path": path.as_posix(), "bytes": len(payload), "sha256": sha256(payload)})
    members.sort(key=lambda item: item["path"])
    return pretty_json(
        with_content_digest(
            {
                "schema": "mrw.current_byte_binding_successor_manifest.v1",
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
    documents[BINDINGS_REL / "artifact-manifest.v1.json"] = build_manifest(root, documents)
    return documents


def check(root: Path) -> dict[str, Any]:
    documents = expected_documents(root)
    expected_paths = {path for path in documents}
    actual_paths = {
        path.relative_to(root)
        for path in (root / BINDINGS_REL).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    static_paths = {
        BINDINGS_REL / "build_current_byte_binding_successors.py",
        BINDINGS_REL / "check_current_byte_binding_successors.py",
        BINDINGS_REL / "test_current_byte_binding_successors.py",
    }
    if actual_paths != expected_paths | static_paths:
        raise ValueError("binding bundle contains missing or unexpected files")
    for relative, expected in documents.items():
        if (root / relative).read_bytes() != expected:
            raise ValueError(f"generated artifact drift: {relative}")
    return {
        "status": "PASS",
        "source_count": len(CURRENT_SOURCES),
        "successor_count": 10,
        "authority_ceiling": AUTHORITY_CEILING,
    }


def write_create_only(root: Path) -> None:
    documents = expected_documents(root)
    for relative, payload in documents.items():
        target = root / relative
        if target.exists():
            if target.read_bytes() != payload:
                raise ValueError(f"create-only target differs: {relative}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        if target.parent.name == "snapshots":
            os.chmod(target, 0o444)


def refresh_owned_generated(root: Path) -> None:
    """Refresh only generated members inside this additive successor bundle."""
    documents = expected_documents(root)
    for relative, payload in documents.items():
        target = root / relative
        if target.exists() and target.read_bytes() == payload:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        if target.parent.name == "snapshots":
            os.chmod(target, 0o444)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--refresh-owned-generated", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    if args.write and args.refresh_owned_generated:
        parser.error("--write and --refresh-owned-generated are mutually exclusive")
    if args.refresh_owned_generated:
        refresh_owned_generated(root)
        result = check(root)
    elif args.write:
        write_create_only(root)
        result = check(root)
    else:
        result = check(root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
