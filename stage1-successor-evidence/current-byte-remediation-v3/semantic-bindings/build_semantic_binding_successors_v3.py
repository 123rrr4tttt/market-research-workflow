#!/usr/bin/env python3
"""Build the create-only I1 semantic-movement current-byte extension."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ROOT = Path("stage1-successor-evidence/current-byte-remediation-v3/semantic-bindings")
I1_FRAGMENT_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
    "stage-b23-2026-09-05/fragments/I1.json"
)
I1_FRAGMENT_SHA256 = "8c99a91c0891589073318c9b872d977ec95e37e8e206e66255c88f72578d9110"
I1_CANDIDATE_SHA256 = "bb4fc787fbc0d1959f04797e45a99b3da1d00a544501ab30abcc5ff017af0e7e"
REGISTRY_REL = ROOT / "semantic-binding-successors.v3.json"
MANIFEST_REL = ROOT / "artifact-manifest.v3.json"
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
SEMANTIC_REPAIRS = (
    {
        "successor_id": "i1-semantic-movement-inventory-v3",
        "source_path": "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/P1P3LegacyDonorSemanticMovementInventory.v1.json",
        "predecessor_sha256": "b4ae38c055ee2135daca0f276d30336483b920692d5c5b9d5c03dfa499c5db25",
        "successor_sha256": "40fea5ab8d9526ec1c085ab353e9acf12564c5c348dcb826cc46557ea6b81bd0",
        "bytes": 25944,
    },
    {
        "successor_id": "i1-semantic-movement-matrix-v3",
        "source_path": "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/P1P3SuccessorMovementMatrix.v1.json",
        "predecessor_sha256": "a292ebfec63457d04a0671f15095ca4f371059c977f45146c3945919e046e523",
        "successor_sha256": "776ae30af7d5224bbff17006909e52efcd8384cd041fef01e2d169a3dc1fe440",
        "bytes": 250677,
    },
    {
        "successor_id": "i1-semantic-movement-c1-fragment-v3",
        "source_path": "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/fragments/C1.v1.json",
        "predecessor_sha256": "fc26123aea12acf8705e600170620c247309f035378cb6146962d6ddfd682c15",
        "successor_sha256": "8c6814d0c21e7957bfc3d84a1fcf47d0598e81959768adcd5be5662a32af460f",
        "bytes": 23291,
    },
    {
        "successor_id": "i1-semantic-movement-gate-v3",
        "source_path": "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/P1P3SemanticMovementGate.v1.json",
        "predecessor_sha256": "9d54a449aba89bf04197737764568984b0f9cc9aeb823445bbd17ae515f9e35e",
        "successor_sha256": "7936419d8fe94475640ec133198dec2db8c24af00e1d75d716425a8696d93514",
        "bytes": 7597,
    },
    {
        "successor_id": "i1-semantic-movement-c9-fragment-v3",
        "source_path": "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/fragments/C9.v1.json",
        "predecessor_sha256": "b918073cb449c11511392b7ee799f119a702e24d319331b8f8cd7e8d1b6cfc89",
        "successor_sha256": "0b9ba3f993c8577902052243bda4dfc6b382abdf53d5ed6e84b6cb78c95512e8",
        "bytes": 32274,
    },
    {
        "successor_id": "i1-c5-historical-stage-selector-v3",
        "source_path": "main/backend/tests/successor_runtime/test_p3_c5_0_evidence_generator.py",
        "binding_group": "test_bindings",
        "predecessor_sha256": "284fb952da78d28d03b6f8dc16b9cfb8cbe500f6d8a14a9ef92aa6ad63906319",
        "predecessor_bytes": 9987,
        "successor_sha256": "dea6b74abfdb2b70fabfbe3f598fa5bc87c3d655617085875ad5fc7c3bd6c387",
        "bytes": 9988,
    },
)
STATIC_FILES = (
    ROOT / "build_semantic_binding_successors_v3.py",
    ROOT / "check_semantic_binding_successors_v3.py",
    ROOT / "test_semantic_binding_successors_v3.py",
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def pretty_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"


def with_content_digest(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["content_digest"] = sha256(canonical_json({k: v for k, v in result.items() if k != "content_digest"}))
    return result


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _semantic_rows(root: Path) -> list[dict[str, Any]]:
    fragment_path = root / I1_FRAGMENT_REL
    if sha256(fragment_path.read_bytes()) != I1_FRAGMENT_SHA256:
        raise ValueError("I1 B23 semantic predecessor fragment drift")
    fragment = _load_json(fragment_path)
    bindings = fragment.get("bindings")
    if not isinstance(bindings, list):
        raise TypeError("I1 B23 semantic predecessor bindings missing")

    rows: list[dict[str, Any]] = []
    for repair in SEMANTIC_REPAIRS:
        owning = [item for item in bindings if item.get("path") == repair["source_path"]]
        if not owning:
            raise ValueError(f"semantic predecessor binding missing: {repair['source_path']}")
        if any(
            item.get("binding_group") != repair.get("binding_group", "source_bindings")
            or item.get("successor_sha256") != repair["predecessor_sha256"]
            or item.get("bytes") != repair.get("predecessor_bytes", repair["bytes"])
            for item in owning
        ):
            raise ValueError(f"semantic predecessor binding drift: {repair['source_path']}")

        payload = (root / repair["source_path"]).read_bytes()
        if sha256(payload) != repair["successor_sha256"] or len(payload) != repair["bytes"]:
            raise ValueError(f"semantic current source drift: {repair['source_path']}")

        roles = list(dict.fromkeys(item["role"] for item in owning))
        for role in roles:
            role_owning = [item for item in owning if item["role"] == role]
            spec_bindings = []
            for item in role_owning:
                spec_path = item["spec_path"]
                spec = _load_json(root / spec_path)
                group_field = repair.get("binding_group", "source_bindings")
                source_bindings = spec.get(group_field)
                if not isinstance(source_bindings, list):
                    raise TypeError(f"semantic owning specification bindings missing: {spec_path}")
                matches = [
                    index
                    for index, binding in enumerate(source_bindings)
                    if binding.get("path") == item["path"]
                    and binding.get("role") == item["role"]
                    and binding.get("file_sha256") == item["predecessor_sha256"]
                ]
                if len(matches) != 1:
                    raise ValueError(f"semantic owning specification binding drift: {spec_path}")
                spec_bindings.append(
                    {
                        "cell_id": item["cell_id"],
                        "spec_path": spec_path,
                        "spec_sha256": item["spec_sha256"],
                        "json_pointer": f"/{group_field}/{matches[0]}",
                        "role": item["role"],
                        "prior_spec_predecessor_sha256": item["predecessor_sha256"],
                    }
                )

            rows.append(
                {
                    "successor_id": repair["successor_id"] + (
                        f"-{role}" if len(roles) > 1 else ""
                    ),
                    "relation": "I1_SHARED_EXACT_BINDING_SUCCESSOR",
                    "cell_ids": list(dict.fromkeys(item["cell_id"] for item in role_owning)),
                    "spec_bindings": spec_bindings,
                    "source_path": repair["source_path"],
                    "binding_group": repair.get("binding_group", "source_bindings"),
                    "role": role,
                    "prior_spec_predecessor_sha256": role_owning[0]["predecessor_sha256"],
                    "predecessor_sha256": repair["predecessor_sha256"],
                    "successor_sha256": repair["successor_sha256"],
                    "bytes": repair["bytes"],
                    "lines": payload.count(b"\n"),
                    "snapshot_path": f"snapshots/{repair['successor_sha256']}",
                    "change_class": "SEMANTIC_MOVEMENT_DERIVED_ARTIFACT_REBUILD",
                    "preservation_scope": {
                        "taxonomy_semantics_changed": False,
                        "source_code_changed": False,
                        "artifact_group_validator_passed": True,
                    },
                    "qualification": "EXACT_BYTES_ONLY_NOT_AUTHORITY",
                }
            )
    return rows


def expected_documents(root: Path) -> dict[Path, bytes]:
    rows = _semantic_rows(root)
    registry = with_content_digest(
        {
            "schema": "mrw.current_byte_semantic_binding_successors.v3",
            "record_id": "current-byte-semantic-binding-successors-v3",
            "status": "CURRENT_BYTES_BOUND_BY_ADDITIVE_SUCCESSORS_NOT_AUTHORITY",
            "authoritative": False,
            "authority": AUTHORITY,
            "authority_ceiling": AUTHORITY_CEILING,
            "extends": {
                "path": I1_FRAGMENT_REL.as_posix(),
                "sha256": I1_FRAGMENT_SHA256,
                "candidate_sha256": I1_CANDIDATE_SHA256,
                "mutation": False,
            },
            "inherited_successor_count": 0,
            "successors": rows,
            "limits": [
                "Five I1-owned semantic-movement artifacts and one C5 historical-stage selector update are bound additively.",
                "The B23 I1 fragment remains immutable and is not rewritten.",
                "Exact-byte correspondence grants no candidate promotion or production authority.",
                "PRODUCTION_RELEASE_NOT_AUTHORIZED",
            ],
        }
    )
    member_inputs = [
        (ROOT / "snapshots" / row["successor_sha256"], (root / row["source_path"]).read_bytes())
        for row in rows
    ]
    member_inputs.append((REGISTRY_REL, pretty_json(registry)))
    unique_member_inputs = {
        path.as_posix(): payload for path, payload in member_inputs
    }
    members = [
        {"path": path, "bytes": len(payload), "sha256": sha256(payload)}
        for path, payload in sorted(unique_member_inputs.items())
    ]
    for path in STATIC_FILES:
        payload = (root / path).read_bytes()
        members.append({"path": path.as_posix(), "bytes": len(payload), "sha256": sha256(payload)})
    members.sort(key=lambda item: item["path"])
    manifest = with_content_digest(
        {
            "schema": "mrw.current_byte_semantic_binding_manifest.v3",
            "status": "COMPLETE_NOT_AUTHORITY",
            "authoritative": False,
            "authority": AUTHORITY,
            "authority_ceiling": AUTHORITY_CEILING,
            "member_count": len(members),
            "members": members,
        }
    )
    return {
        **{ROOT / "snapshots" / row["successor_sha256"]: (root / row["source_path"]).read_bytes() for row in rows},
        REGISTRY_REL: pretty_json(registry),
        MANIFEST_REL: pretty_json(manifest),
    }


def check(root: Path) -> dict[str, Any]:
    documents = expected_documents(root)
    actual = {
        path.relative_to(root)
        for path in (root / ROOT).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    if actual != set(documents) | set(STATIC_FILES):
        raise ValueError("semantic binding bundle contains missing or unexpected files")
    for relative, payload in documents.items():
        if (root / relative).read_bytes() != payload:
            raise ValueError(f"semantic generated artifact drift: {relative}")
    registry = _load_json(root / REGISTRY_REL)
    return {
        "status": "PASS",
        "source_count": len({row["source_path"] for row in registry["successors"]}),
        "successor_count": len(registry["successors"]),
        "authority_ceiling": AUTHORITY_CEILING,
    }


def write_create_only(root: Path) -> None:
    documents = expected_documents(root)
    for relative in documents:
        target = root / relative
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"create-only target exists: {relative}")
    for relative, payload in documents.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(payload)
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
