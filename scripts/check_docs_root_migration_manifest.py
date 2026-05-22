#!/usr/bin/env python3
"""Validate docs-root migration manifests and content shims."""

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
ALLOWED_STATUSES = {"mapped_not_moved", "content_shim", "content_moved_batch"}
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


def same_path(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve()


def validate_content_shim(
    repo_root: Path,
    entry_path: Path,
    root: Path,
    root_raw: str,
    source: Path,
    source_raw: str,
    target: Path,
    target_raw: str,
    target_text: str,
    entry: dict[str, Any],
) -> list[Problem]:
    problems: list[Problem] = []

    target_root_raw = entry.get("target_root")
    shim_raw = entry.get("shim")
    compatibility_entry_raw = entry.get("compatibility_entry")

    if not isinstance(target_root_raw, str):
        problems.append(Problem(entry_path, "content_shim entry target_root is missing"))
    elif not target_root_raw.startswith(f"{root_raw}/"):
        problems.append(Problem(entry_path, "content_shim target_root is outside manifest root"))
    else:
        target_root = repo_root / target_root_raw
        if not target_root.is_dir():
            problems.append(Problem(target_root, "content_shim target_root directory is missing"))
        if not is_relative_to(target_root, root):
            problems.append(Problem(target_root, "content_shim target_root is outside manifest root"))
        if not same_path(target, target_root / "README.md"):
            problems.append(Problem(target, "content_shim target must be target_root/README.md"))
        if target_root_raw not in target_text:
            problems.append(Problem(target, f"content_shim README does not mention target_root: {target_root_raw}"))

    if shim_raw != target_raw:
        problems.append(Problem(entry_path, "content_shim shim must match target README path"))
    elif shim_raw not in target_text:
        problems.append(Problem(target, f"content_shim README does not mention shim path: {shim_raw}"))

    if not isinstance(compatibility_entry_raw, str):
        problems.append(Problem(entry_path, "content_shim compatibility_entry is missing"))
    else:
        compatibility_entry = repo_root / compatibility_entry_raw
        if not compatibility_entry.exists():
            problems.append(Problem(compatibility_entry, "content_shim compatibility_entry does not exist"))
        elif source.exists() and not is_relative_to(compatibility_entry, source):
            problems.append(
                Problem(
                    compatibility_entry,
                    f"content_shim compatibility_entry is not within source path: {source_raw}",
                )
            )
        if source.is_file() and not same_path(compatibility_entry, source):
            problems.append(Problem(entry_path, "content_shim file source must use the source as compatibility_entry"))
        if compatibility_entry_raw not in target_text:
            problems.append(
                Problem(
                    target,
                    f"content_shim README does not mention compatibility_entry: {compatibility_entry_raw}",
                )
            )

    if "content shim" not in target_text.lower():
        problems.append(Problem(target, "content_shim README must identify itself as a content shim"))

    return problems


def validate_content_moved_batch(
    repo_root: Path,
    entry_path: Path,
    root: Path,
    root_raw: str,
    source: Path,
    source_raw: str,
    target: Path,
    target_raw: str,
    target_text: str,
    entry: dict[str, Any],
) -> list[Problem]:
    problems: list[Problem] = []

    target_root_raw = entry.get("target_root")
    shim_raw = entry.get("shim")
    compatibility_entry_raw = entry.get("compatibility_entry")
    moved_files_raw = entry.get("moved_files")

    if not isinstance(target_root_raw, str):
        problems.append(Problem(entry_path, "content_moved_batch entry target_root is missing"))
        target_root = None
    elif not target_root_raw.startswith(f"{root_raw}/"):
        problems.append(Problem(entry_path, "content_moved_batch target_root is outside manifest root"))
        target_root = None
    else:
        target_root = repo_root / target_root_raw
        if not target_root.is_dir():
            problems.append(Problem(target_root, "content_moved_batch target_root directory is missing"))
        elif not is_relative_to(target_root, root):
            problems.append(Problem(target_root, "content_moved_batch target_root is outside manifest root"))
        if not same_path(target, target_root / "README.md"):
            problems.append(Problem(target, "content_moved_batch target must remain target_root/README.md"))
        if target_root_raw not in target_text:
            problems.append(Problem(target, f"content_moved_batch README does not mention target_root: {target_root_raw}"))

    if shim_raw != target_raw:
        problems.append(Problem(entry_path, "content_moved_batch shim must match target README path"))
    elif shim_raw not in target_text:
        problems.append(Problem(target, f"content_moved_batch README does not mention shim path: {shim_raw}"))

    if not isinstance(compatibility_entry_raw, str):
        problems.append(Problem(entry_path, "content_moved_batch compatibility_entry is missing"))
    else:
        compatibility_entry = repo_root / compatibility_entry_raw
        if not compatibility_entry.exists():
            problems.append(Problem(compatibility_entry, "content_moved_batch compatibility_entry does not exist"))
        elif source.exists() and not is_relative_to(compatibility_entry, source):
            problems.append(
                Problem(
                    compatibility_entry,
                    f"content_moved_batch compatibility_entry is not within source path: {source_raw}",
                )
            )
        if compatibility_entry_raw not in target_text:
            problems.append(
                Problem(
                    target,
                    f"content_moved_batch README does not mention compatibility_entry: {compatibility_entry_raw}",
                )
            )

    if not isinstance(moved_files_raw, list) or not moved_files_raw:
        return problems + [Problem(entry_path, "content_moved_batch moved_files must be a non-empty list")]

    if "content moved" not in target_text.lower():
        problems.append(Problem(target, "content_moved_batch README must identify moved content"))

    for file_index, moved_file in enumerate(moved_files_raw):
        file_path = Path(f"{entry_path}#moved_files[{file_index}]")
        if not isinstance(moved_file, dict):
            problems.append(Problem(file_path, "moved file entry must be an object"))
            continue

        moved_source_raw = moved_file.get("source")
        moved_target_raw = moved_file.get("target")
        moved_compatibility_raw = moved_file.get("compatibility_entry")

        if not isinstance(moved_source_raw, str) or not moved_source_raw.startswith(f"{source_raw}/"):
            problems.append(Problem(file_path, "moved file source must be inside the manifest source"))
            moved_source = None
        else:
            moved_source = repo_root / moved_source_raw
            if not moved_source.is_file():
                problems.append(Problem(moved_source, "moved file source compatibility shim is missing"))

        if not isinstance(moved_target_raw, str) or not isinstance(target_root_raw, str) or not moved_target_raw.startswith(f"{target_root_raw}/"):
            problems.append(Problem(file_path, "moved file target must be inside target_root"))
            moved_target = None
        else:
            moved_target = repo_root / moved_target_raw
            if not moved_target.is_file():
                problems.append(Problem(moved_target, "moved file target is missing"))
            elif not is_relative_to(moved_target, root):
                problems.append(Problem(moved_target, "moved file target is outside manifest root"))

        if moved_compatibility_raw != moved_source_raw:
            problems.append(Problem(file_path, "moved file compatibility_entry must equal moved source"))
        if moved_file.get("authority") != "target_authoritative":
            problems.append(Problem(file_path, "moved file authority must be target_authoritative"))
        if moved_file.get("source_status") != "compatibility_shim":
            problems.append(Problem(file_path, "moved file source_status must be compatibility_shim"))

        for required in (moved_source_raw, moved_target_raw):
            if isinstance(required, str) and required and required not in target_text:
                problems.append(Problem(target, f"content_moved_batch README does not mention moved path: {required}"))

        if moved_source is not None and moved_source.is_file() and isinstance(moved_target_raw, str):
            source_text = moved_source.read_text(encoding="utf-8")
            if "compatibility shim" not in source_text.lower():
                problems.append(Problem(moved_source, "moved source must identify itself as a compatibility shim"))
            if moved_target_raw not in source_text:
                problems.append(Problem(moved_source, f"moved source does not point at target: {moved_target_raw}"))

        if moved_target is not None and moved_target.is_file() and isinstance(moved_source_raw, str):
            moved_target_text = moved_target.read_text(encoding="utf-8")
            if moved_source_raw not in moved_target_text:
                problems.append(Problem(moved_target, f"moved target does not mention compatibility source: {moved_source_raw}"))
            if "content moved" not in moved_target_text.lower():
                problems.append(Problem(moved_target, "moved target must identify content moved status"))

    return problems


def validate_navigation_promotions(
    repo_root: Path,
    manifest_path: Path,
    root: Path,
    root_raw: str,
    data: dict[str, Any],
    entries_by_id: dict[str, dict[str, Any]],
) -> list[Problem]:
    problems: list[Problem] = []
    promotions_raw = data.get("navigation_promotions", [])
    if promotions_raw is None:
        return problems
    if not isinstance(promotions_raw, list):
        return [Problem(manifest_path, "navigation_promotions must be a list when present")]

    seen_promotion_ids: set[str] = set()
    expected_root_readme_raw = f"{root_raw}/README.md"
    expected_root_readme = repo_root / expected_root_readme_raw
    root_text = expected_root_readme.read_text(encoding="utf-8") if expected_root_readme.is_file() else ""

    for promotion_index, promotion in enumerate(promotions_raw):
        promotion_path = Path(f"{manifest_path}#navigation_promotions[{promotion_index}]")
        if not isinstance(promotion, dict):
            problems.append(Problem(promotion_path, "navigation promotion must be an object"))
            continue

        promotion_id = promotion.get("id")
        if not isinstance(promotion_id, str) or not promotion_id:
            problems.append(Problem(promotion_path, "navigation promotion id is missing"))
        elif promotion_id in seen_promotion_ids:
            problems.append(Problem(promotion_path, f"duplicate navigation promotion id: {promotion_id}"))
        else:
            seen_promotion_ids.add(promotion_id)

        if promotion.get("status") != "navigation_promoted":
            problems.append(Problem(promotion_path, "navigation promotion status must be navigation_promoted"))

        root_readme_raw = promotion.get("root_readme")
        if root_readme_raw != expected_root_readme_raw:
            problems.append(
                Problem(
                    promotion_path,
                    f"navigation promotion root_readme must be {expected_root_readme_raw}",
                )
            )
        if not expected_root_readme.is_file():
            problems.append(Problem(expected_root_readme, "navigation promotion root README is missing"))

        navigation_section = promotion.get("navigation_section")
        if not isinstance(navigation_section, str) or not navigation_section:
            problems.append(Problem(promotion_path, "navigation promotion navigation_section is missing"))
        elif navigation_section not in root_text:
            problems.append(
                Problem(expected_root_readme, f"navigation section is missing: {navigation_section}")
            )

        if isinstance(promotion_id, str) and promotion_id and promotion_id not in root_text:
            problems.append(Problem(expected_root_readme, f"navigation promotion id is not mentioned: {promotion_id}"))

        navigation_entries = promotion.get("entries")
        if not isinstance(navigation_entries, list) or not navigation_entries:
            problems.append(Problem(promotion_path, "navigation promotion entries must be a non-empty list"))
            continue

        for entry_index, navigation_entry in enumerate(navigation_entries):
            navigation_entry_path = Path(f"{promotion_path}#entries[{entry_index}]")
            if not isinstance(navigation_entry, dict):
                problems.append(Problem(navigation_entry_path, "navigation entry must be an object"))
                continue

            target_root_raw = navigation_entry.get("target_root")
            target_raw = navigation_entry.get("target")
            compatibility_entry_raw = navigation_entry.get("compatibility_entry")
            manifest_entry_ids_raw = navigation_entry.get("manifest_entry_ids")

            if not isinstance(target_root_raw, str) or not target_root_raw.startswith(f"{root_raw}/"):
                problems.append(Problem(navigation_entry_path, "navigation target_root is outside manifest root"))
                target_root = None
            else:
                target_root = repo_root / target_root_raw
                if not target_root.is_dir():
                    problems.append(Problem(target_root, "navigation target_root directory is missing"))
                elif not is_relative_to(target_root, root):
                    problems.append(Problem(target_root, "navigation target_root is outside manifest root"))

            if not isinstance(target_raw, str):
                problems.append(Problem(navigation_entry_path, "navigation target is missing"))
                target = None
            else:
                target = repo_root / target_raw
                if not target.is_file():
                    problems.append(Problem(target, "navigation target README is missing"))
                if target_root is not None and not same_path(target, target_root / "README.md"):
                    problems.append(Problem(target, "navigation target must be target_root/README.md"))

            if isinstance(compatibility_entry_raw, str):
                compatibility_entry = repo_root / compatibility_entry_raw
                if not compatibility_entry_raw.startswith("development/latest-dev-docs/"):
                    problems.append(
                        Problem(navigation_entry_path, "navigation compatibility_entry must be under development/latest-dev-docs")
                    )
                elif not compatibility_entry.exists():
                    problems.append(Problem(compatibility_entry, "navigation compatibility_entry does not exist"))
            else:
                problems.append(Problem(navigation_entry_path, "navigation compatibility_entry is missing"))

            if not isinstance(manifest_entry_ids_raw, list) or not manifest_entry_ids_raw:
                problems.append(Problem(navigation_entry_path, "navigation manifest_entry_ids must be a non-empty list"))
                manifest_entry_ids: list[str] = []
            else:
                manifest_entry_ids = []
                for raw_entry_id in manifest_entry_ids_raw:
                    if not isinstance(raw_entry_id, str) or not raw_entry_id:
                        problems.append(Problem(navigation_entry_path, "navigation manifest_entry_ids must be strings"))
                        continue
                    manifest_entry_ids.append(raw_entry_id)
                    source_entry = entries_by_id.get(raw_entry_id)
                    if source_entry is None:
                        problems.append(Problem(navigation_entry_path, f"navigation references unknown entry id: {raw_entry_id}"))
                        continue
                    if target_root_raw and source_entry.get("target_root") != target_root_raw:
                        problems.append(
                            Problem(navigation_entry_path, f"navigation entry id target_root mismatch: {raw_entry_id}")
                        )
                    if target_raw and source_entry.get("target") != target_raw:
                        problems.append(
                            Problem(navigation_entry_path, f"navigation entry id target mismatch: {raw_entry_id}")
                        )

            required_root_text = [
                value
                for value in (
                    target_root_raw,
                    target_raw,
                    compatibility_entry_raw,
                    *manifest_entry_ids,
                )
                if isinstance(value, str) and value
            ]
            for required in required_root_text:
                if required not in root_text:
                    problems.append(Problem(expected_root_readme, f"navigation README does not mention: {required}"))

            partial_boundary = navigation_entry.get("partial_boundary")
            if not isinstance(partial_boundary, str) or not partial_boundary:
                problems.append(Problem(navigation_entry_path, "navigation partial_boundary is missing"))

    return problems


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
    entries_by_id: dict[str, dict[str, Any]] = {}
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
            entries_by_id[entry_id] = entry

        if entry.get("classification") != expected_classification:
            problems.append(Problem(entry_path, "entry classification does not match root"))
        status = entry.get("status")
        if status not in ALLOWED_STATUSES:
            problems.append(Problem(entry_path, f"entry status must be one of {sorted(ALLOWED_STATUSES)}"))

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
        if status == "content_shim":
            problems.extend(
                validate_content_shim(
                    repo_root=repo_root,
                    entry_path=entry_path,
                    root=root,
                    root_raw=root_raw,
                    source=source,
                    source_raw=source_raw,
                    target=target,
                    target_raw=target_raw,
                    target_text=target_text,
                    entry=entry,
                )
            )
        elif status == "content_moved_batch":
            problems.extend(
                validate_content_moved_batch(
                    repo_root=repo_root,
                    entry_path=entry_path,
                    root=root,
                    root_raw=root_raw,
                    source=source,
                    source_raw=source_raw,
                    target=target,
                    target_raw=target_raw,
                    target_text=target_text,
                    entry=entry,
                )
            )

    missing_roles = required_source_roles - seen_source_roles
    if missing_roles:
        problems.append(Problem(manifest_path, f"required source roles missing: {sorted(missing_roles)}"))

    problems.extend(
        validate_navigation_promotions(
            repo_root=repo_root,
            manifest_path=manifest_path,
            root=root,
            root_raw=root_raw,
            data=data,
            entries_by_id=entries_by_id,
        )
    )

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
