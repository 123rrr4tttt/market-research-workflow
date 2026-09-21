#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Read-only structural checker for current-byte binding successors."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "build_current_byte_binding_successors", HERE / "build_current_byte_binding_successors.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load current-byte successor builder")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def validate(root: Path) -> dict[str, Any]:
    result = BUILDER.check(root)
    registry = load_json(root / BUILDER.BINDINGS_REL / "current-byte-binding-successors.v1.json")
    closure = load_json(root / BUILDER.BINDINGS_REL / "current-byte-all-lines-closure.v2.json")
    manifest = load_json(root / BUILDER.BINDINGS_REL / "artifact-manifest.v1.json")
    for document in (registry, closure, manifest):
        if document["authoritative"] is not False:
            raise ValueError("binding evidence must remain non-authoritative")
        if document["authority"] != BUILDER.AUTHORITY or any(document["authority"].values()):
            raise ValueError("binding evidence expands authority")
        if document["authority_ceiling"] != BUILDER.AUTHORITY_CEILING:
            raise ValueError("binding evidence authority ceiling drift")
        body = {key: value for key, value in document.items() if key != "content_digest"}
        if document["content_digest"] != BUILDER.sha256(BUILDER.canonical_json(body)):
            raise ValueError("binding evidence content digest mismatch")
    if registry["status"] != "CURRENT_BYTES_BOUND_BY_ADDITIVE_SUCCESSORS_NOT_AUTHORITY":
        raise ValueError("unexpected registry status")
    if closure["status"] != "OBSERVED_BYTE_CLOSURE_NOT_PROMOTION":
        raise ValueError("unexpected AllLines successor status")
    successors = registry["successors"]
    if len(successors) != 10 or len({item["successor_id"] for item in successors}) != 10:
        raise ValueError("successor ids are incomplete or duplicated")
    for item in successors:
        expected = BUILDER.CURRENT_SOURCES[item["source_path"]]
        if item["successor_sha256"] != expected["sha256"]:
            raise ValueError(f"successor hash mismatch: {item['successor_id']}")
        if not item["predecessor_declarations"]:
            raise ValueError(f"missing predecessor declaration: {item['successor_id']}")
        snapshot = root / BUILDER.BINDINGS_REL / item["snapshot_path"]
        if BUILDER.sha256(snapshot.read_bytes()) != item["successor_sha256"]:
            raise ValueError(f"snapshot mismatch: {item['successor_id']}")
    celery = next(
        item
        for item in successors
        if item["successor_id"] == "i1-c5-4-celery-app-current-bytes-v1"
    )
    expected_celery_identity = {
        "family": "I1",
        "cell_id": "C5.4",
        "binding_group": "source_bindings",
        "role": "legacy_donor_c5_4_normative",
        "source_path": "main/backend/app/celery_app.py",
        "prior_spec_predecessor_sha256": BUILDER.CELERY_SPEC_OLD,
        "predecessor_sha256": BUILDER.CELERY_B23,
        "successor_sha256": BUILDER.CURRENT_SOURCES["main/backend/app/celery_app.py"]["sha256"],
    }
    if any(celery[key] != value for key, value in expected_celery_identity.items()):
        raise ValueError("celery_app ordered predecessor identity drift")
    expected_celery_chain = [
        {"stage": "SPEC_PREDECESSOR", "sha256": BUILDER.CELERY_SPEC_OLD},
        {"stage": "B23_SUCCESSOR", "sha256": BUILDER.CELERY_B23},
        {
            "stage": "CURRENT_WORKING_TREE_SUCCESSOR",
            "sha256": BUILDER.CURRENT_SOURCES["main/backend/app/celery_app.py"]["sha256"],
        },
    ]
    if celery["ordered_sha256_chain"] != expected_celery_chain:
        raise ValueError("celery_app ordered SHA-256 chain drift")
    expected_celery_refs = {
        (
            f"{BUILDER.P}/exact-byte-rebind/stage-b23-2026-09-05/fragments/I1.json",
            "/bindings/64",
            "successor_sha256",
        ),
        (
            f"{BUILDER.P}/exact-byte-rebind/stage-b23-2026-09-05/manifests/I1.json",
            "/sources/98",
            "file_sha256",
        ),
        (
            f"{BUILDER.P}/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/candidate.v2.json",
            "/sources/98",
            "file_sha256",
        ),
    }
    actual_celery_refs = {
        (ref["artifact"], ref["json_pointer"], ref["hash_field"])
        for ref in celery["predecessor_declarations"]
    }
    if actual_celery_refs != expected_celery_refs:
        raise ValueError("celery_app predecessor declaration key drift")
    if any(ref["bound_sha256"] != BUILDER.CELERY_B23 for ref in celery["predecessor_declarations"]):
        raise ValueError("celery_app B23 predecessor chain drift")
    if registry["declaration_alignment"]["stage0_v4"]["preserved"] is not True:
        raise ValueError("Stage0 v4 preservation not declared")
    if closure["extends"]["mutation"] is not False:
        raise ValueError("AllLines v1 mutation must remain false")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=BUILDER.REPOSITORY_ROOT)
    args = parser.parse_args()
    print(json.dumps(validate(args.repo_root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
