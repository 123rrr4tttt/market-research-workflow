#!/usr/bin/env python3
"""Validate docs-root content-plan manifests.

The content-plan gate is intentionally stricter than the migration manifest
checker: it proves the current batch is still a shim plan, keeps
development/latest-dev-docs as the content authority, and records blocked broad
moves before any shared index or MERGED_OVERVIEW reconciliation happens.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PLAN_MANIFESTS = (
    Path("docs/development/latest-dev-docs-content-plan.json"),
    Path("docs/architecture/latest-dev-docs-content-plan.json"),
)
EXPECTED_PLAN_SCHEMA = "docs-root-content-plan/v1"
EXPECTED_MIGRATION_SCHEMA = "docs-root-entry-manifest/v1"
SOURCE_AUTHORITY = "development/latest-dev-docs"
ALLOWED_ROOTS = {"docs/development", "docs/architecture"}
ALLOWED_ENTRY_MODES = {"shim_only", "moved_file_batch"}
UNSAFE_MOVE_MODE = "blocked_broad_move"
REQUIRED_MOVE_BLOCKERS = {"shared_navigation_sync", "MERGED_OVERVIEW_drift"}


@dataclass(frozen=True)
class Problem:
    path: Path
    message: str


def load_json(path: Path) -> tuple[dict[str, Any] | None, list[Problem]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [Problem(path, "JSON manifest is missing")]
    except json.JSONDecodeError as exc:
        return None, [Problem(path, f"JSON manifest is invalid: {exc}")]
    if not isinstance(data, dict):
        return None, [Problem(path, "JSON manifest must be an object")]
    return data, []


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def validate_discoverability(repo_root: Path, root_raw: str, plan_path: Path, checker_raw: str) -> list[Problem]:
    problems: list[Problem] = []
    root_readme = repo_root / root_raw / "README.md"
    if not root_readme.is_file():
        return [Problem(root_readme, "root README is missing")]

    text = root_readme.read_text(encoding="utf-8")
    for required in (plan_path.name, checker_raw):
        if required not in text:
            problems.append(Problem(root_readme, f"root README does not mention content-plan gate: {required}"))
    return problems


def load_migration_entries(
    repo_root: Path,
    plan_path: Path,
    expected_root: str,
    migration_manifest_raw: Any,
) -> tuple[dict[str, dict[str, Any]], list[Problem]]:
    if not isinstance(migration_manifest_raw, str):
        return {}, [Problem(plan_path, "migration_manifest is missing")]

    migration_path = repo_root / migration_manifest_raw
    data, problems = load_json(migration_path)
    if data is None:
        return {}, problems

    if data.get("schema") != EXPECTED_MIGRATION_SCHEMA:
        problems.append(Problem(migration_path, "unexpected migration manifest schema"))
    if data.get("root") != expected_root:
        problems.append(Problem(migration_path, f"migration manifest root must be {expected_root}"))

    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        problems.append(Problem(migration_path, "migration manifest entries must be a non-empty list"))
        return {}, problems

    entries: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(raw_entries):
        entry_path = Path(f"{migration_path}#entries[{index}]")
        if not isinstance(entry, dict):
            problems.append(Problem(entry_path, "migration entry must be an object"))
            continue
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            problems.append(Problem(entry_path, "migration entry id is missing"))
            continue
        if entry_id in entries:
            problems.append(Problem(entry_path, f"duplicate migration entry id: {entry_id}"))
            continue
        entries[entry_id] = entry
    return entries, problems


def validate_content_plan_entries(
    repo_root: Path,
    plan_path: Path,
    root_raw: str,
    source_authority: str,
    migration_entries: dict[str, dict[str, Any]],
    raw_entries: Any,
) -> tuple[list[Problem], int]:
    problems: list[Problem] = []
    if not isinstance(raw_entries, list) or not raw_entries:
        return [Problem(plan_path, "entries must be a non-empty list")], 0

    root = repo_root / root_raw
    seen_ids: set[str] = set()
    seen_manifest_ids: set[str] = set()

    for index, entry in enumerate(raw_entries):
        entry_path = Path(f"{plan_path}#entries[{index}]")
        if not isinstance(entry, dict):
            problems.append(Problem(entry_path, "content-plan entry must be an object"))
            continue

        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            problems.append(Problem(entry_path, "content-plan entry id is missing"))
        elif entry_id in seen_ids:
            problems.append(Problem(entry_path, f"duplicate content-plan entry id: {entry_id}"))
        else:
            seen_ids.add(entry_id)

        manifest_entry_id = entry.get("manifest_entry_id")
        if not isinstance(manifest_entry_id, str) or not manifest_entry_id:
            problems.append(Problem(entry_path, "manifest_entry_id is missing"))
            migration_entry = None
        else:
            seen_manifest_ids.add(manifest_entry_id)
            migration_entry = migration_entries.get(manifest_entry_id)
            if migration_entry is None:
                problems.append(Problem(entry_path, f"unknown migration manifest entry: {manifest_entry_id}"))

        source_raw = entry.get("source")
        target_root_raw = entry.get("target_root")
        shim_raw = entry.get("shim")
        mode = entry.get("mode")

        if entry.get("source_authority") != source_authority:
            problems.append(Problem(entry_path, f"source_authority must be {source_authority}"))
        if not isinstance(source_raw, str) or not source_raw.startswith(f"{source_authority}/"):
            problems.append(Problem(entry_path, f"source must be under {source_authority}"))
        else:
            source = repo_root / source_raw
            if not source.exists():
                problems.append(Problem(source, "content-plan source does not exist"))

        if not isinstance(target_root_raw, str) or not target_root_raw.startswith(f"{root_raw}/"):
            problems.append(Problem(entry_path, "target_root must be under the plan root"))
        else:
            target_root = repo_root / target_root_raw
            if not target_root.is_dir():
                problems.append(Problem(target_root, "target_root directory does not exist"))
            elif not is_relative_to(target_root, root):
                problems.append(Problem(target_root, "target_root is outside the plan root"))

        if not isinstance(shim_raw, str):
            problems.append(Problem(entry_path, "shim is missing"))
        else:
            shim = repo_root / shim_raw
            if not shim.is_file():
                problems.append(Problem(shim, "shim file does not exist"))

        if mode not in ALLOWED_ENTRY_MODES:
            problems.append(Problem(entry_path, f"mode must be one of {sorted(ALLOWED_ENTRY_MODES)}"))
        elif mode == "shim_only":
            if entry.get("source_remains_authoritative") is not True:
                problems.append(Problem(entry_path, "source_remains_authoritative must be true for shim_only"))
            if entry.get("move_allowed") is not False:
                problems.append(Problem(entry_path, "move_allowed must be false for shim_only"))
        elif mode == "moved_file_batch":
            if entry.get("source_remains_authoritative") is not False:
                problems.append(Problem(entry_path, "source_remains_authoritative must be false for moved_file_batch"))
            if entry.get("move_allowed") is not True:
                problems.append(Problem(entry_path, "move_allowed must be true for moved_file_batch"))

        blockers = set(string_list(entry.get("blocked_by")))
        missing_blockers = REQUIRED_MOVE_BLOCKERS - blockers
        if missing_blockers:
            problems.append(Problem(entry_path, f"blocked_by missing required blockers: {sorted(missing_blockers)}"))
        if not isinstance(entry.get("next_gate"), str) or not entry["next_gate"]:
            problems.append(Problem(entry_path, "next_gate is missing"))

        if migration_entry is not None:
            expected_pairs = {
                "source": migration_entry.get("source"),
                "target_root": migration_entry.get("target_root"),
                "shim": migration_entry.get("shim") or migration_entry.get("target"),
            }
            actual_pairs = {
                "source": source_raw,
                "target_root": target_root_raw,
                "shim": shim_raw,
            }
            for key, expected in expected_pairs.items():
                if actual_pairs[key] != expected:
                    problems.append(
                        Problem(
                            entry_path,
                            f"{key} does not match migration manifest entry {manifest_entry_id}: {expected}",
                        )
                    )
            expected_status = "content_moved_batch" if mode == "moved_file_batch" else "content_shim"
            if migration_entry.get("status") != expected_status:
                problems.append(
                    Problem(entry_path, f"content-plan entry mode {mode} must point at {expected_status} migration entries")
                )
            if mode == "moved_file_batch":
                problems.extend(
                    validate_moved_file_batch(
                        repo_root=repo_root,
                        entry_path=entry_path,
                        root=root,
                        target_root_raw=target_root_raw,
                        entry=entry,
                        migration_entry=migration_entry,
                    )
                )

    missing_manifest_entries = sorted(set(migration_entries) - seen_manifest_ids)
    if missing_manifest_entries:
        problems.append(Problem(plan_path, f"missing content-plan entries for migration manifest ids: {missing_manifest_entries}"))

    return problems, len(raw_entries)


def validate_moved_file_batch(
    repo_root: Path,
    entry_path: Path,
    root: Path,
    target_root_raw: Any,
    entry: dict[str, Any],
    migration_entry: dict[str, Any],
) -> list[Problem]:
    problems: list[Problem] = []
    moved_files = entry.get("moved_files")
    migration_moved_files = migration_entry.get("moved_files")

    if not isinstance(moved_files, list) or not moved_files:
        return [Problem(entry_path, "moved_file_batch moved_files must be a non-empty list")]
    if not isinstance(migration_moved_files, list) or not migration_moved_files:
        problems.append(Problem(entry_path, "moved_file_batch migration entry must declare moved_files"))
        migration_moved_files = []
    if moved_files != migration_moved_files:
        problems.append(Problem(entry_path, "moved_file_batch moved_files must match migration manifest moved_files"))

    target_root_prefix = f"{target_root_raw}/" if isinstance(target_root_raw, str) else ""
    for index, moved_file in enumerate(moved_files):
        moved_path = Path(f"{entry_path}#moved_files[{index}]")
        if not isinstance(moved_file, dict):
            problems.append(Problem(moved_path, "moved file entry must be an object"))
            continue

        source_raw = moved_file.get("source")
        target_raw = moved_file.get("target")
        compatibility_raw = moved_file.get("compatibility_entry")

        if not isinstance(source_raw, str) or not source_raw.startswith("development/latest-dev-docs/"):
            problems.append(Problem(moved_path, "moved file source must be under development/latest-dev-docs"))
            source = None
        else:
            source = repo_root / source_raw
            if not source.is_file():
                problems.append(Problem(source, "moved file compatibility shim is missing"))

        if not isinstance(target_raw, str) or not target_root_prefix or not target_raw.startswith(target_root_prefix):
            problems.append(Problem(moved_path, "moved file target must be inside target_root"))
            target = None
        else:
            target = repo_root / target_raw
            if not target.is_file():
                problems.append(Problem(target, "moved file target is missing"))
            elif not is_relative_to(target, root):
                problems.append(Problem(target, "moved file target is outside plan root"))

        if compatibility_raw != source_raw:
            problems.append(Problem(moved_path, "moved file compatibility_entry must equal source"))
        if moved_file.get("authority") != "target_authoritative":
            problems.append(Problem(moved_path, "moved file authority must be target_authoritative"))
        if moved_file.get("source_status") != "compatibility_shim":
            problems.append(Problem(moved_path, "moved file source_status must be compatibility_shim"))

        if source is not None and source.is_file() and isinstance(target_raw, str):
            source_text = source.read_text(encoding="utf-8")
            if "compatibility shim" not in source_text.lower():
                problems.append(Problem(source, "moved source must identify itself as a compatibility shim"))
            if target_raw not in source_text:
                problems.append(Problem(source, f"moved source does not point at target: {target_raw}"))

        if target is not None and target.is_file() and isinstance(source_raw, str):
            target_text = target.read_text(encoding="utf-8")
            if "content moved" not in target_text.lower():
                problems.append(Problem(target, "moved target must identify content moved status"))
            if source_raw not in target_text:
                problems.append(Problem(target, f"moved target does not mention compatibility source: {source_raw}"))

    return problems


def validate_remaining_unsafe_moves(
    repo_root: Path,
    plan_path: Path,
    root_raw: str,
    source_authority: str,
    raw_moves: Any,
) -> tuple[list[Problem], int]:
    problems: list[Problem] = []
    if not isinstance(raw_moves, list) or not raw_moves:
        return [Problem(plan_path, "remaining_unsafe_moves must be a non-empty list")], 0

    root = repo_root / root_raw
    seen_ids: set[str] = set()
    for index, move in enumerate(raw_moves):
        move_path = Path(f"{plan_path}#remaining_unsafe_moves[{index}]")
        if not isinstance(move, dict):
            problems.append(Problem(move_path, "unsafe move entry must be an object"))
            continue

        move_id = move.get("id")
        if not isinstance(move_id, str) or not move_id:
            problems.append(Problem(move_path, "unsafe move id is missing"))
        elif move_id in seen_ids:
            problems.append(Problem(move_path, f"duplicate unsafe move id: {move_id}"))
        else:
            seen_ids.add(move_id)

        source_raw = move.get("source")
        target_root_raw = move.get("target_root")
        if not isinstance(source_raw, str) or not source_raw.startswith(f"{source_authority}/"):
            problems.append(Problem(move_path, f"unsafe move source must be under {source_authority}"))
        else:
            source = repo_root / source_raw
            if not source.exists():
                problems.append(Problem(source, "unsafe move source does not exist"))

        if not isinstance(target_root_raw, str) or not target_root_raw.startswith(f"{root_raw}/"):
            problems.append(Problem(move_path, "unsafe move target_root must be under the plan root"))
        else:
            target_root = repo_root / target_root_raw
            if not target_root.is_dir():
                problems.append(Problem(target_root, "unsafe move target_root directory does not exist"))
            elif not is_relative_to(target_root, root):
                problems.append(Problem(target_root, "unsafe move target_root is outside the plan root"))

        if move.get("mode") != UNSAFE_MOVE_MODE:
            problems.append(Problem(move_path, f"unsafe move mode must be {UNSAFE_MOVE_MODE}"))
        if not isinstance(move.get("reason"), str) or not move["reason"]:
            problems.append(Problem(move_path, "unsafe move reason is missing"))

        required_gates = set(string_list(move.get("required_gates")))
        missing_gates = REQUIRED_MOVE_BLOCKERS - required_gates
        if missing_gates:
            problems.append(Problem(move_path, f"required_gates missing blockers: {sorted(missing_gates)}"))

    return problems, len(raw_moves)


def validate_plan(repo_root: Path, plan_path: Path) -> tuple[list[Problem], int, int]:
    problems: list[Problem] = []
    data, load_problems = load_json(plan_path)
    problems.extend(load_problems)
    if data is None:
        return problems, 0, 0

    root_raw = data.get("root")
    if data.get("schema") != EXPECTED_PLAN_SCHEMA:
        problems.append(Problem(plan_path, "unexpected content-plan schema"))
    if root_raw not in ALLOWED_ROOTS:
        problems.append(Problem(plan_path, f"unexpected root: {root_raw!r}"))
        return problems, 0, 0

    source_authority = data.get("source_authority")
    if source_authority != SOURCE_AUTHORITY:
        problems.append(Problem(plan_path, f"source_authority must be {SOURCE_AUTHORITY}"))
        source_authority = SOURCE_AUTHORITY

    checker_raw = data.get("checker")
    if checker_raw != "scripts/checkers/check_docs_root_content_plan.py":
        problems.append(Problem(plan_path, "checker must be scripts/checkers/check_docs_root_content_plan.py"))
        checker_raw = "scripts/checkers/check_docs_root_content_plan.py"

    root = repo_root / root_raw
    if not root.is_dir():
        problems.append(Problem(root, "plan root does not exist"))
    problems.extend(validate_discoverability(repo_root, root_raw, plan_path, checker_raw))

    migration_entries, migration_problems = load_migration_entries(
        repo_root=repo_root,
        plan_path=plan_path,
        expected_root=root_raw,
        migration_manifest_raw=data.get("migration_manifest"),
    )
    problems.extend(migration_problems)

    entry_problems, entry_count = validate_content_plan_entries(
        repo_root=repo_root,
        plan_path=plan_path,
        root_raw=root_raw,
        source_authority=source_authority,
        migration_entries=migration_entries,
        raw_entries=data.get("entries"),
    )
    problems.extend(entry_problems)

    unsafe_problems, unsafe_count = validate_remaining_unsafe_moves(
        repo_root=repo_root,
        plan_path=plan_path,
        root_raw=root_raw,
        source_authority=source_authority,
        raw_moves=data.get("remaining_unsafe_moves"),
    )
    problems.extend(unsafe_problems)

    return problems, entry_count, unsafe_count


def display_path(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> int:
    repo_root = Path.cwd()
    all_problems: list[Problem] = []
    total_entries = 0
    total_unsafe_moves = 0

    for plan_path in PLAN_MANIFESTS:
        problems, entries, unsafe_moves = validate_plan(repo_root, plan_path)
        all_problems.extend(problems)
        total_entries += entries
        total_unsafe_moves += unsafe_moves

    if all_problems:
        for problem in all_problems:
            print(f"FAIL {display_path(repo_root, problem.path)}: {problem.message}", file=sys.stderr)
        return 1

    print(
        "OK docs_root_content_plan=passed "
        f"plans={len(PLAN_MANIFESTS)} entries={total_entries} unsafe_moves={total_unsafe_moves}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
