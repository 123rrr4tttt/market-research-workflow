#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Read-only checker for the additive v2 current-byte successor registry."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "build_current_byte_binding_successors_v2",
    HERE / "build_current_byte_binding_successors_v2.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load v2 current-byte successor builder")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def validate(root: Path) -> dict[str, Any]:
    result = BUILDER.check(root)
    v1_checker = load_module(
        "check_current_byte_binding_successors_v1",
        root / BUILDER.V1_REL / "check_current_byte_binding_successors.py",
    )
    v1_result = v1_checker.validate(root)
    if v1_result.get("status") != "PASS" or v1_result.get("successor_count") != 10:
        raise ValueError("v1 predecessor checker failed")

    v1 = load_json(root / BUILDER.V1_REGISTRY_REL)
    registry = load_json(root / BUILDER.REGISTRY_REL)
    manifest = load_json(root / BUILDER.MANIFEST_REL)
    for document in (registry, manifest):
        if document["authoritative"] is not False:
            raise ValueError("v2 binding evidence must remain non-authoritative")
        if document["authority"] != BUILDER.AUTHORITY or any(document["authority"].values()):
            raise ValueError("v2 binding evidence expands authority")
        if document["authority_ceiling"] != BUILDER.AUTHORITY_CEILING:
            raise ValueError("v2 binding evidence authority ceiling drift")
        body = {key: value for key, value in document.items() if key != "content_digest"}
        if document["content_digest"] != BUILDER.sha256(BUILDER.canonical_json(body)):
            raise ValueError("v2 binding evidence content digest mismatch")
    if (
        registry["schema"] != "mrw.current_byte_binding_successors.v2"
        or registry["record_id"] != "current-byte-binding-successors-v2"
        or registry["status"] != "CURRENT_BYTES_BOUND_BY_ADDITIVE_SUCCESSORS_NOT_AUTHORITY"
    ):
        raise ValueError("unexpected v2 registry identity")
    if registry["extends"] != {
        "path": BUILDER.V1_REGISTRY_REL.as_posix(),
        "sha256": BUILDER.V1_REGISTRY_SHA256,
        "content_digest": BUILDER.V1_CONTENT_DIGEST,
        "schema": "mrw.current_byte_binding_successors.v1",
        "record_id": "current-byte-binding-successors-v1",
        "mutation": False,
    }:
        raise ValueError("v2 predecessor extension drift")
    successors = registry["successors"]
    if len(successors) != 11 or successors[:10] != v1["successors"]:
        raise ValueError("v2 inherited successor projection drift")
    if len({row["successor_id"] for row in successors}) != 11:
        raise ValueError("v2 successor ids are incomplete or duplicated")
    native_rows = [
        row for row in successors if row["source_path"] == BUILDER.NATIVE_PATH
    ]
    if native_rows != [BUILDER.shared_native_successor()]:
        raise ValueError("shared native provider successor identity drift")
    native = native_rows[0]
    if native["cell_ids"] != ["C6.1", "C6.2"] or len(set(native["cell_ids"])) != 2:
        raise ValueError("shared native provider cell expansion drift")
    if native["ordered_sha256_chain"] != [
        {"stage": "SPEC_PREDECESSOR", "sha256": BUILDER.SPEC_PREDECESSOR},
        {"stage": "B23_SUCCESSOR", "sha256": BUILDER.B23_SUCCESSOR},
        {"stage": "CURRENT_WORKING_TREE_SUCCESSOR", "sha256": BUILDER.CURRENT_SUCCESSOR},
    ]:
        raise ValueError("shared native provider ordered hash chain drift")
    snapshot = root / BUILDER.BINDINGS_REL / native["snapshot_path"]
    if BUILDER.sha256(snapshot.read_bytes()) != BUILDER.CURRENT_SUCCESSOR:
        raise ValueError("shared native provider snapshot drift")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=BUILDER.REPOSITORY_ROOT)
    args = parser.parse_args()
    print(json.dumps(validate(args.repo_root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
