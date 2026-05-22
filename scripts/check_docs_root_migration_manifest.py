#!/usr/bin/env python3
"""Validate the first docs-root migration manifests."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MANIFESTS = (
    Path("docs/development/latest-dev-docs-entry-manifest.json"),
    Path("docs/architecture/latest-dev-docs-entry-manifest.json"),
)
EXPECTED_SCHEMA = "docs-root-entry-manifest/v1"
ALLOWED_STATUSES = {"mapped_not_moved"}
EXPECTED_CLASSIFICATION_BY_ROOT = {
    "docs/development": "development",
    "docs/architecture": "architecture",
}
REQUIRED_SOURCE_ROLES_BY_ROOT = {
    "docs/development": {"latest-dev-docs-main-entry", "active-development-plan-root"},
    "docs/architecture": {"explicit-architecture-tree"},
}


@dataclass(frozen=True)
class Problem:
    path: Path
    message: str


def load_json(path: Path) -> tuple[dict[str, Any] | None, list[Problem]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except FileNotFoundError:
        return None, [Problem(path, "manifest is missing")]
    except json.JSONDecodeError as exc:
        return None, [Problem(path, f"manifest is not valid JSON: {exc}")]


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def validate_manifest(repo_root: Path, manifest_path: Path) -> tuple[list[Problem], int]:
    problems: list[Problem] = []
    data, load_problems = load_json(manifest_path)
    problems.extend(load_problems)
    if data is None:
        return problems, 0

    root_raw = data.get("root")
    if data.get("schema") != EXPECTED_SCHEMA:
        problems.append(Problem(manifest_path, "unexpected schema"))
    if root_raw not in EXPECTED_CLASSIFICATION_BY_ROOT:
        problems.append(Problem(manifest_path, f"unexpected root: {root_raw!r}"))
        return problems, 0

    root = repo_root / root_raw
    expected_classification = EXPECTED_CLASSIFICATION_BY_ROOT[root_raw]
    required_source_roles = set(REQUIRED_SOURCE_ROLES_BY_ROOT[root_raw])

    if not root.is_dir():
        problems.append(Problem(root, "target root is missing"))
    root_readme = root / "README.md"
    if not root_readme.is_file():
        problems.append(Problem(root_readme, "target root README is missing"))
    elif manifest_path.name not in root_readme.read_text(encoding="utf-8"):
        problems.append(Problem(root_readme, "target root README does not link the manifest"))

    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        problems.append(Problem(manifest_path, "entries must be a non-empty list"))
        return problems, 0

    seen_ids: set[str] = set()
    seen_source_roles: set[str] = set()

    for index, entry in enumerate(entries):
        entry_path = Path(f"{manifest_path}#entries[{index}]")
        if not isinstance(entry, dict):
            problems.append(Problem(entry_path, "entry must be an object"))
            continue

        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            problems.append(Problem(entry_path, "entry id is missing"))
        elif entry_id in seen_ids:
            problems.append(Problem(entry_path, f"duplicate entry id: {entry_id}"))
        else:
            seen_ids.add(entry_id)

        if entry.get("classification") != expected_classification:
            problems.append(Problem(entry_path, "entry classification does not match root"))
        if entry.get("status") not in ALLOWED_STATUSES:
            problems.append(Problem(entry_path, "entry status must be mapped_not_moved"))

        source_raw = entry.get("source")
        target_raw = entry.get("target")
        source_role = entry.get("source_role")
        if isinstance(source_role, str):
            seen_source_roles.add(source_role)

        if not isinstance(source_raw, str) or not source_raw.startswith("development/latest-dev-docs/"):
            problems.append(Problem(entry_path, "source must be under development/latest-dev-docs"))
            continue
        if not isinstance(target_raw, str):
            problems.append(Problem(entry_path, "target is missing"))
            continue

        source = repo_root / source_raw
        target = repo_root / target_raw
        if not source.exists():
            problems.append(Problem(source, "mapped source does not exist"))
        if not target.is_file():
            problems.append(Problem(target, "target entry README does not exist"))
            continue
        if not is_relative_to(target, root):
            problems.append(Problem(target, "target entry is outside its manifest root"))

        target_text = target.read_text(encoding="utf-8")
        if source_raw not in target_text:
            problems.append(Problem(target, f"target README does not mention mapped source: {source_raw}"))

    missing_roles = required_source_roles - seen_source_roles
    if missing_roles:
        problems.append(Problem(manifest_path, f"required source roles missing: {sorted(missing_roles)}"))

    return problems, len(entries)


def main() -> int:
    repo_root = Path.cwd()
    all_problems: list[Problem] = []
    total_entries = 0

    for manifest in MANIFESTS:
        problems, entries = validate_manifest(repo_root, manifest)
        all_problems.extend(problems)
        total_entries += entries

    if all_problems:
        for problem in all_problems:
            print(f"FAIL {problem.path}: {problem.message}", file=sys.stderr)
        return 1

    print(f"OK docs_root_migration_manifest=passed manifests={len(MANIFESTS)} entries={total_entries}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
