#!/usr/bin/env python3
# ruff: noqa: TRY003
"""Read-only checker for the zero-delta v4 current-byte binding bundle."""

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
    "build_current_byte_binding_successors_v4",
    HERE / "build_current_byte_binding_successors_v4.py",
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _validate_common(document: dict[str, Any], *, label: str) -> None:
    if document.get("authoritative") is not False:
        raise ValueError(f"{label} must remain non-authoritative")
    if document.get("authority") != BUILDER.AUTHORITY or any(document["authority"].values()):
        raise ValueError(f"{label} expands authority")
    if document.get("authority_ceiling") != BUILDER.AUTHORITY_CEILING:
        raise ValueError(f"{label} authority ceiling drift")
    body = {key: value for key, value in document.items() if key != "content_digest"}
    if document.get("content_digest") != BUILDER.sha256(BUILDER.canonical_json(body)):
        raise ValueError(f"{label} content digest mismatch")


def validate_document_semantics(
    root: Path,
    *,
    v3: dict[str, Any],
    registry: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    _validate_common(registry, label="v4 registry")
    _validate_common(manifest, label="v4 manifest")
    if (
        registry.get("schema") != BUILDER.REGISTRY_SCHEMA
        or registry.get("record_id") != BUILDER.REGISTRY_RECORD_ID
        or registry.get("status") != "CURRENT_BYTES_BOUND_BY_ZERO_DELTA_SUCCESSOR_NOT_AUTHORITY"
    ):
        raise ValueError("unexpected v4 registry identity")
    expected_extension = {
        "path": BUILDER.V3_REGISTRY_REL.as_posix(),
        "sha256": BUILDER.V3_REGISTRY_SHA256,
        "content_digest": BUILDER.V3_CONTENT_DIGEST,
        "schema": BUILDER.V3_SCHEMA,
        "record_id": BUILDER.V3_RECORD_ID,
        "mutation": False,
    }
    if registry.get("extends") != expected_extension:
        raise ValueError("v4 predecessor extension drift")
    successors = registry.get("successors")
    if not isinstance(successors, list):
        raise TypeError("v4 successors must be a list")
    if (
        registry.get("inherited_successor_count") != BUILDER.EXPECTED_SUCCESSOR_COUNT
        or registry.get("added_successor_count") != 0
        or registry.get("new_snapshot_count") != 0
        or len(successors) != BUILDER.EXPECTED_SUCCESSOR_COUNT
    ):
        raise ValueError("v4 zero-delta counts drift")
    if successors != v3.get("successors"):
        raise ValueError("v4 inherited successor row mutation")
    if BUILDER.canonical_json(successors) != BUILDER.canonical_json(v3["successors"]):
        raise ValueError("v4 inherited successor byte semantics drift")

    if (
        manifest.get("schema") != BUILDER.MANIFEST_SCHEMA
        or manifest.get("status") != "COMPLETE_ZERO_DELTA_NOT_AUTHORITY"
        or manifest.get("extends")
        != {
            "path": BUILDER.V3_REGISTRY_REL.as_posix(),
            "sha256": BUILDER.V3_REGISTRY_SHA256,
            "mutation": False,
        }
    ):
        raise ValueError("unexpected v4 manifest identity")
    if manifest.get("added_successor_count") != 0 or manifest.get("new_snapshot_count") != 0:
        raise ValueError("v4 manifest falsely declares an addition or snapshot")
    expected_members = BUILDER.build_manifest(
        root,
        BUILDER.pretty_json(BUILDER.build_registry(root)),
    )["members"]
    if (
        manifest.get("member_count") != len(expected_members)
        or manifest.get("members") != expected_members
    ):
        raise ValueError("v4 manifest member identity drift")
    if any("/snapshots/" in member.get("path", "") for member in manifest["members"]):
        raise ValueError("v4 manifest falsely materializes a snapshot")


def validate(root: Path) -> dict[str, Any]:
    result = BUILDER.check(root)
    v3 = BUILDER.validate_v3_predecessor(root)
    registry = load_json(root / BUILDER.REGISTRY_REL)
    manifest = load_json(root / BUILDER.MANIFEST_REL)
    validate_document_semantics(
        root,
        v3=v3,
        registry=registry,
        manifest=manifest,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=BUILDER.REPOSITORY_ROOT)
    args = parser.parse_args()
    print(json.dumps(validate(args.repo_root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
