#!/usr/bin/env python3
"""Read-only checker for the I1 semantic-movement extension."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER = load_module(
    "build_semantic_binding_successors_v3",
    HERE / "build_semantic_binding_successors_v3.py",
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def validate_document_semantics(root: Path, *, registry: dict[str, Any], manifest: dict[str, Any]) -> None:
    for document in (registry, manifest):
        if document.get("authoritative") is not False:
            raise ValueError("semantic binding evidence must remain non-authoritative")
        if document.get("authority") != BUILDER.AUTHORITY or any(document["authority"].values()):
            raise ValueError("semantic binding evidence expands authority")
        if document.get("authority_ceiling") != BUILDER.AUTHORITY_CEILING:
            raise ValueError("semantic binding authority ceiling drift")
        body = {key: value for key, value in document.items() if key != "content_digest"}
        if document.get("content_digest") != BUILDER.sha256(BUILDER.canonical_json(body)):
            raise ValueError("semantic binding content digest mismatch")
    if registry.get("schema") != "mrw.current_byte_semantic_binding_successors.v3" or registry.get("record_id") != "current-byte-semantic-binding-successors-v3":
        raise ValueError("semantic binding registry identity drift")
    successors = registry.get("successors")
    if not isinstance(successors, list) or len(successors) != len(BUILDER._semantic_rows(root)):
        raise ValueError("semantic binding successor count drift")
    if successors != BUILDER._semantic_rows(root):
        raise ValueError("semantic binding successor drift")


def validate(root: Path) -> dict[str, Any]:
    result = BUILDER.check(root)
    registry = load_json(root / BUILDER.REGISTRY_REL)
    manifest = load_json(root / BUILDER.MANIFEST_REL)
    validate_document_semantics(root, registry=registry, manifest=manifest)
    for row in registry["successors"]:
        snapshot = root / BUILDER.ROOT / row["snapshot_path"]
        source = root / row["source_path"]
        if snapshot.read_bytes() != source.read_bytes():
            raise ValueError(f"semantic binding snapshot/source mismatch: {row['source_path']}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=BUILDER.REPOSITORY_ROOT)
    args = parser.parse_args()
    print(json.dumps(validate(args.repo_root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
