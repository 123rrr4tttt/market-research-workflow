#!/usr/bin/env python3
"""Audit the additive ROOT support selector policy against one exact manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from scripts.formal_release.source_closure import (
    WORKFLOW_SELECTOR_JSON_ROOTS,
    WORKFLOW_SELECTOR_JSON_SUBTREE_ROOTS,
    WORKFLOW_SELECTOR_PYTHON_ROOTS,
    WORKFLOW_SELECTOR_ROOTS,
    WORKFLOW_SELECTOR_SHELL_ROOTS,
    _is_workflow_selector_path,
    compute_workflow_selector_delta,
)
from scripts.formal_release.stage2_git_batch import BaseTreeIndex


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--classification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.resolve(strict=True)
    preview = args.preview.resolve(strict=True)
    manifest_path = args.manifest.resolve(strict=True)
    classification_path = args.classification.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.exists() or output.is_symlink():
        parser.error(f"output already exists: {output}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    classification = json.loads(classification_path.read_text(encoding="utf-8"))
    base_oid = manifest["source"]["base_oid"]
    base_index = BaseTreeIndex.from_repo(source, base_oid)
    expected = compute_workflow_selector_delta(source, base_index=base_index)
    manifest_rows = {
        row["path"]: row["operation"]
        for row in manifest["entries"]
        if isinstance(row, dict)
        and isinstance(row.get("path"), str)
        and isinstance(row.get("operation"), str)
    }
    missing_or_wrong = [
        {"operation": operation, "path": relative, "manifest_operation": manifest_rows.get(relative)}
        for operation, relative in expected
        if manifest_rows.get(relative) != operation
    ]

    projection_causes = sorted(
        {
            relative
            for item in classification["failures"]
            if item["category"] in {"MISSING_PROJECTION", "CASCADING_MISSING_PROJECTION"}
            for relative in item["root_cause_source_paths"]
        }
    )
    observed_coverage = [
        {
            "path": relative,
            "accepted_by_policy": _is_workflow_selector_path(relative),
            "expected_delta_operation": dict((path, operation) for operation, path in expected).get(relative),
            "manifest_operation": manifest_rows.get(relative),
            "source_exists": (source / relative).is_file(),
            "preview_absent": not (preview / relative).exists(),
        }
        for relative in projection_causes
    ]
    covers = all(
        item["accepted_by_policy"]
        and item["expected_delta_operation"] == "UPSERT"
        and item["manifest_operation"] is None
        and item["source_exists"]
        and item["preview_absent"]
        for item in observed_coverage
    )

    repo_root = Path(__file__).resolve().parents[2]
    bound_files = {
        relative: sha256(repo_root / relative)
        for relative in (
            "scripts/formal_release/source_closure.py",
            "tests/formal_release/test_source_closure.py",
            "stage1-successor-evidence/stage-convergence-batch-v1/run-root-gates-attempt-next.sh",
        )
    }
    payload = {
        "schema": "mrw.stage1.root-astra-selector-policy-audit.v1",
        "status": "PASS_POLICY_COVERS_OBSERVED_ROOT_CAUSES" if covers else "FAIL_POLICY_GAP_REMAINS",
        "authoritative": False,
        "inputs": {
            "source": str(source),
            "preview": str(preview),
            "manifest": str(manifest_path),
            "manifest_sha256": sha256(manifest_path),
            "classification": str(classification_path),
            "classification_sha256": sha256(classification_path),
            "base_oid": base_oid,
        },
        "policy": {
            "python_roots": list(WORKFLOW_SELECTOR_PYTHON_ROOTS),
            "shell_roots": list(WORKFLOW_SELECTOR_SHELL_ROOTS),
            "json_roots": list(WORKFLOW_SELECTOR_JSON_ROOTS),
            "json_subtree_roots": list(WORKFLOW_SELECTOR_JSON_SUBTREE_ROOTS),
            "selector_roots": list(WORKFLOW_SELECTOR_ROOTS),
            "exact_rebind_json_subtree": "sidecar-inputs",
            "bound_file_sha256": bound_files,
        },
        "current_source_delta": {
            "rows": len(expected),
            "by_operation": dict(sorted(Counter(operation for operation, _ in expected).items())),
            "attempt6_manifest_missing_or_wrong_rows": missing_or_wrong,
            "attempt6_manifest_missing_or_wrong_count": len(missing_or_wrong),
        },
        "observed_failure_root_cause_coverage": observed_coverage,
        "limits": [
            "This audit is additive diagnostic evidence; it does not replace "
            "the frozen v3 policy record or bind a successor.",
            "The integration owner must materialize a fresh preview and manifest before rerunning ROOT gates.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=True, indent=2, sort_keys=True)
        stream.write("\n")
    print(
        json.dumps(
            {
                "output": str(output),
                "status": payload["status"],
                "missing_or_wrong": len(missing_or_wrong),
            },
            sort_keys=True,
        )
    )
    return 0 if covers else 1


if __name__ == "__main__":
    raise SystemExit(main())
