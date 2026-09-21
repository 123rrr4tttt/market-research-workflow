#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Read-only checker for the additive v3 current-byte successor registry."""

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
    "build_current_byte_binding_successors_v3",
    HERE / "build_current_byte_binding_successors_v3.py",
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def validate_document_semantics(
    root: Path,
    *,
    v2: dict[str, Any],
    registry: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    for document in (registry, manifest):
        if document.get("authoritative") is not False:
            raise ValueError("v3 binding evidence must remain non-authoritative")
        if document.get("authority") != BUILDER.AUTHORITY or any(document["authority"].values()):
            raise ValueError("v3 binding evidence expands authority")
        if document.get("authority_ceiling") != BUILDER.AUTHORITY_CEILING:
            raise ValueError("v3 binding evidence authority ceiling drift")
        body = {key: value for key, value in document.items() if key != "content_digest"}
        if document.get("content_digest") != BUILDER.sha256(BUILDER.canonical_json(body)):
            raise ValueError("v3 binding evidence content digest mismatch")
    if (
        registry.get("schema") != "mrw.current_byte_binding_successors.v3"
        or registry.get("record_id") != "current-byte-binding-successors-v3"
        or registry.get("status") != "CURRENT_BYTES_BOUND_BY_ADDITIVE_SUCCESSORS_NOT_AUTHORITY"
    ):
        raise ValueError("unexpected v3 registry identity")
    if registry.get("extends") != {
        "path": BUILDER.V2_REGISTRY_REL.as_posix(),
        "sha256": BUILDER.V2_REGISTRY_SHA256,
        "content_digest": BUILDER.V2_CONTENT_DIGEST,
        "schema": "mrw.current_byte_binding_successors.v2",
        "record_id": "current-byte-binding-successors-v2",
        "mutation": False,
    }:
        raise ValueError("v3 predecessor extension drift")

    successors = registry.get("successors")
    if not isinstance(successors, list):
        raise TypeError("v3 successors must be a list")
    ids = [row.get("successor_id") for row in successors if isinstance(row, dict)]
    if len(ids) != len(set(ids)):
        raise ValueError("v3 successor row duplicated")
    expected_successor_count = 11 + 2 + len(BUILDER.CONTRACT_REPAIRS)
    if len(successors) != expected_successor_count or registry.get("inherited_successor_count") != 11:
        raise ValueError("v3 successor count drift")
    if successors[:11] != v2.get("successors"):
        raise ValueError("v3 inherited eleven-row projection drift")
    expected_added = [
        BUILDER.shared_run_loop_successor(),
        BUILDER.shared_provider_test_successor(),
        *BUILDER.contract_repair_rows(root),
    ]
    if successors[11:] != expected_added:
        raise ValueError("v3 exact shared successor identities drift")

    run_loop = successors[11]
    declarations = run_loop.get("direct_candidate_declarations")
    if declarations != [dict(item) for item in BUILDER.CANDIDATE_DECLARATIONS]:
        raise ValueError("v3 direct candidate declarations drift")
    predecessor_declarations = run_loop.get("predecessor_declarations")
    expected_predecessor_declarations = [
        {
            "artifact": item["candidate_path"],
            "artifact_sha256": item["candidate_sha256"],
            "json_pointer": item["json_pointer"],
            "hash_field": "file_sha256",
            "bound_sha256": item["predecessor_sha256"],
        }
        for item in BUILDER.CANDIDATE_DECLARATIONS
    ]
    if predecessor_declarations != expected_predecessor_declarations:
        raise ValueError("v3 canonical predecessor declarations drift")
    declaration_keys = [
        (
            item.get("candidate_path"),
            item.get("candidate_sha256"),
            item.get("json_pointer"),
            item.get("predecessor_sha256"),
        )
        for item in declarations
    ]
    if len(declaration_keys) != 3 or len(set(declaration_keys)) != 3:
        raise ValueError("v3 direct candidate declaration duplicated")
    if [item.get("family") for item in declarations] != ["C5", "C6", "I1"]:
        raise ValueError("v3 direct candidate family order drift")
    if run_loop.get("frozen_cell_sources") != [dict(item) for item in BUILDER.FROZEN_CELL_SOURCES]:
        raise ValueError("v3 frozen cell sources drift")
    if run_loop.get("change_class") != "TYPE_CHECKING_ONLY_IMPORT_RELOCATION":
        raise ValueError("v3 change class drift")

    provider_test = successors[12]
    provider_declarations = provider_test.get("direct_candidate_declarations")
    if provider_declarations != [
        dict(item) for item in BUILDER.PROVIDER_TEST_CANDIDATE_DECLARATIONS
    ]:
        raise ValueError("v3 provider test direct candidate declarations drift")
    if provider_test.get("predecessor_declarations") != BUILDER.provider_test_predecessor_declarations():
        raise ValueError("v3 provider test canonical predecessor declarations drift")
    provider_declaration_keys = [
        (
            item.get("candidate_path"),
            item.get("candidate_sha256"),
            item.get("json_pointer"),
            item.get("predecessor_sha256"),
        )
        for item in provider_declarations
    ]
    if len(provider_declaration_keys) != 7 or len(set(provider_declaration_keys)) != 7:
        raise ValueError("v3 provider test direct candidate declaration duplicated")
    if [item.get("stage") for item in provider_declarations] != [
        "stage-b13-2026-09-05",
        "stage-b15-2026-09-05",
        "stage-b16-2026-09-05",
        "stage-b17-2026-09-05",
        "stage-b18-2026-09-05",
        "stage-b19-2026-09-05",
        "stage-b23-2026-09-05",
    ]:
        raise ValueError("v3 provider test direct candidate stage order drift")
    if provider_test.get("frozen_source_snapshots") != BUILDER.provider_test_frozen_source_snapshots():
        raise ValueError("v3 provider test frozen source snapshots drift")
    if provider_test.get("change_class") != "TEST_FIXTURE_IMPORT_EFFECT_ISOLATION":
        raise ValueError("v3 provider test change class drift")
    preservation = provider_test.get("preservation_scope")
    if not isinstance(preservation, dict) or preservation.get("test_functions_changed") is not False:
        raise ValueError("v3 provider test preservation scope drift")
    if any(
        preservation.get(field) is not False
        for field in (
            "test_assertions_changed",
            "production_sources_changed",
            "alias_or_provider_binding_changed",
        )
    ):
        raise ValueError("v3 provider test preservation scope expands change")


def validate_snapshot(root: Path, shared: dict[str, Any]) -> None:
    expected_path = f"snapshots/{BUILDER.SUCCESSOR_SHA256}"
    if shared.get("snapshot_path") != expected_path:
        raise ValueError("v3 snapshot path drift")
    snapshot = root / BUILDER.BINDINGS_REL / expected_path
    payload = snapshot.read_bytes()
    if BUILDER.sha256(payload) != BUILDER.SUCCESSOR_SHA256:
        raise ValueError("v3 run_loop snapshot drift")
    if payload != (root / BUILDER.RUN_LOOP_PATH).read_bytes():
        raise ValueError("v3 run_loop snapshot/source mismatch")


def validate_provider_test_snapshot(root: Path, shared: dict[str, Any]) -> None:
    expected_path = f"snapshots/{BUILDER.PROVIDER_TEST_SUCCESSOR_SHA256}"
    if shared.get("snapshot_path") != expected_path:
        raise ValueError("v3 provider test snapshot path drift")
    snapshot = root / BUILDER.BINDINGS_REL / expected_path
    payload = snapshot.read_bytes()
    if BUILDER.sha256(payload) != BUILDER.PROVIDER_TEST_SUCCESSOR_SHA256:
        raise ValueError("v3 provider test snapshot drift")
    if payload != (root / BUILDER.PROVIDER_TEST_PATH).read_bytes():
        raise ValueError("v3 provider test snapshot/source mismatch")


def validate(root: Path) -> dict[str, Any]:
    result = BUILDER.check(root)
    v2 = load_json(root / BUILDER.V2_REGISTRY_REL)
    registry = load_json(root / BUILDER.REGISTRY_REL)
    manifest = load_json(root / BUILDER.MANIFEST_REL)
    validate_document_semantics(root, v2=v2, registry=registry, manifest=manifest)
    validate_snapshot(root, registry["successors"][11])
    validate_provider_test_snapshot(root, registry["successors"][12])
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=BUILDER.REPOSITORY_ROOT)
    args = parser.parse_args()
    print(json.dumps(validate(args.repo_root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
