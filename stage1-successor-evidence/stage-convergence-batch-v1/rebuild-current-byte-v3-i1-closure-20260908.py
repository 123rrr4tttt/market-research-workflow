#!/usr/bin/env python3
"""Rebuild v3 current-byte evidence after the complete I1 candidate projection repair."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HERE = Path("stage1-successor-evidence/stage-convergence-batch-v1")
BUNDLE = Path("stage1-successor-evidence/current-byte-remediation-v3/bindings")
BUILDER_PATH = BUNDLE / "build_current_byte_binding_successors_v3.py"
REGISTRY = BUNDLE / "current-byte-binding-successors.v3.json"
MANIFEST = BUNDLE / "artifact-manifest.v3.json"
STALE_DIR = HERE / "raw/current-byte-v3-pre-i1-closure-20260908"
RECEIPT = HERE / "raw/current-byte-v3-i1-closure-rebuild-20260908.json"
REPLACEABLE = {REGISTRY, MANIFEST}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def load_builder():
    spec = importlib.util.spec_from_file_location("current_byte_builder_v3_i1_rebuild", ROOT / BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load builder: {BUILDER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    builder = load_builder()
    if STALE_DIR.exists() or RECEIPT.exists():
        raise FileExistsError("current-byte v3 I1 closure rebuild evidence already exists")
    old_documents = {
        "registry": {"path": REGISTRY.as_posix(), "sha256": sha256(ROOT / REGISTRY)},
        "manifest": {"path": MANIFEST.as_posix(), "sha256": sha256(ROOT / MANIFEST)},
    }
    STALE_DIR.mkdir(parents=True)
    shutil.copy2(ROOT / REGISTRY, STALE_DIR / REGISTRY.name)
    shutil.copy2(ROOT / MANIFEST, STALE_DIR / MANIFEST.name)
    (STALE_DIR / "pre-rebuild.json").write_bytes(
        canonical({"authoritative": False, "documents": old_documents})
    )

    documents = builder.expected_documents(ROOT)
    for relative, payload in documents.items():
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if relative not in REPLACEABLE or target.read_bytes() == payload:
                continue
            target.chmod(0o644)
            target.write_bytes(payload)
        else:
            with target.open("xb") as handle:
                handle.write(payload)
        if target.parent.name == "snapshots":
            target.chmod(0o444)

    result = builder.check(ROOT)
    receipt = {
        "schema": "mrw.current_byte_v3_rebuild_receipt.v1",
        "status": result["status"],
        "authoritative": False,
        "reason": "ADD_COMPLETE_I1_CURRENT_CANDIDATE_PROJECTION",
        "old_documents": old_documents,
        "new_documents": {
            "registry": {"path": REGISTRY.as_posix(), "sha256": sha256(ROOT / REGISTRY)},
            "manifest": {"path": MANIFEST.as_posix(), "sha256": sha256(ROOT / MANIFEST)},
        },
        "checker": result,
        "stale_copy": STALE_DIR.as_posix(),
        "authority_ceiling": result["authority_ceiling"],
    }
    with RECEIPT.open("xb") as handle:
        handle.write(canonical(receipt))
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
