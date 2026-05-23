#!/usr/bin/env python3
"""Audit docs-root shared navigation and MERGED_OVERVIEW drift.

This checker is intentionally read-only. Worker branches can use the default
audit mode to record whether the remaining docs-root navigation blocker is
machine-checkable without editing shared navigation files. The final
integration lane can use --require-clean to fail until the shared indexes and
MERGED_OVERVIEW cite the latest docs-root topic-local evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote


TOPIC_DIR = Path("development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring")
CONTENT_PLAN = Path("docs/development/latest-dev-docs-content-plan.json")
REQUIRED_BLOCKERS = {"shared_navigation_sync", "MERGED_OVERVIEW_drift"}
POST_WAVE25_MIN_PREFIX = 14


@dataclass(frozen=True)
class Surface:
    role: str
    path: Path


@dataclass(frozen=True)
class MissingReference:
    anchor: Path
    surface: Surface


@dataclass(frozen=True)
class Problem:
    path: Path
    message: str


SHARED_SURFACES = (
    Surface("latest-dev-docs README", Path("development/latest-dev-docs/README.md")),
    Surface("latest-dev-docs MERGED_OVERVIEW", Path("development/latest-dev-docs/MERGED_OVERVIEW.md")),
    Surface("development-plans INDEX", Path("development/latest-dev-docs/development-plans/INDEX.md")),
    Surface("CURRENT_DEV INDEX", Path("development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md")),
)

LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit docs-root shared navigation drift.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="Exit non-zero when shared navigation drift or docs-root unsafe moves remain.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print missing references.")
    return parser.parse_args()


def load_json(path: Path, problems: list[Problem]) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        problems.append(Problem(path, "file is missing"))
        return None
    except json.JSONDecodeError as exc:
        problems.append(Problem(path, f"invalid JSON: {exc}"))
        return None
    if not isinstance(data, dict):
        problems.append(Problem(path, "JSON root must be an object"))
        return None
    return data


def normalize_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.find(">")].strip()
    for marker in (' "', " '", " ("):
        if marker in target:
            return target.split(marker, 1)[0].strip()
    return target


def target_path(raw: str) -> str | None:
    target = normalize_target(raw)
    if not target or target.startswith("#") or target.startswith("//") or SCHEME_RE.match(target):
        return None
    return unquote(target.split("#", 1)[0].split("?", 1)[0])


def resolve_link(repo_root: Path, surface_path: Path, raw_target: str) -> Path | None:
    path_text = target_path(raw_target)
    if not path_text:
        return None
    candidate = repo_root / path_text.lstrip("/") if path_text.startswith("/") else surface_path.parent / path_text
    try:
        return candidate.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return None


def markdown_links(repo_root: Path, surface: Surface, problems: list[Problem]) -> set[Path]:
    surface_path = repo_root / surface.path
    if not surface_path.is_file():
        problems.append(Problem(surface.path, "shared navigation surface is missing"))
        return set()

    links: set[Path] = set()
    for _, _, raw_target in LINK_RE.findall(surface_path.read_text(encoding="utf-8")):
        resolved = resolve_link(repo_root, surface_path, raw_target)
        if resolved is not None:
            links.add(resolved)
    return links


def topic_evidence_anchors(repo_root: Path, problems: list[Problem]) -> list[Path]:
    topic_dir = repo_root / TOPIC_DIR
    if not topic_dir.is_dir():
        problems.append(Problem(TOPIC_DIR, "docs-root topic directory is missing"))
        return []

    anchors: list[Path] = []
    for path in sorted(topic_dir.glob("*.md")):
        prefix = path.name.split("_", 1)[0]
        if prefix.isdigit() and int(prefix) >= POST_WAVE25_MIN_PREFIX:
            anchors.append(path.relative_to(repo_root))
    if not anchors:
        problems.append(Problem(TOPIC_DIR, "no post-Wave25 docs-root evidence anchors found"))
    return anchors


def validate_blocker_fields(
    repo_root: Path,
    move: dict[str, Any],
    move_path: Path,
    gate_field: str,
    ledger_field: str,
    problems: list[Problem],
) -> None:
    gates = set(item for item in move.get(gate_field, []) if isinstance(item, str))
    missing = sorted(REQUIRED_BLOCKERS - gates)
    if missing:
        problems.append(Problem(move_path, f"{gate_field} missing docs-root navigation blockers: {missing}"))

    ledger_raw = move.get(ledger_field)
    if not isinstance(ledger_raw, str):
        return
    ledger = load_json(repo_root / ledger_raw, problems)
    if ledger is None:
        return
    summary = ledger.get("summary")
    if not isinstance(summary, dict):
        problems.append(Problem(Path(ledger_raw), "classification ledger summary must be an object"))
        return
    ledger_blockers = set(
        item for item in summary.get("remaining_blockers_after_classification", []) if isinstance(item, str)
    )
    missing_ledger_blockers = sorted(REQUIRED_BLOCKERS - ledger_blockers)
    if missing_ledger_blockers:
        problems.append(
            Problem(
                Path(ledger_raw),
                f"ledger remaining blockers missing docs-root navigation blockers: {missing_ledger_blockers}",
            )
        )


def validate_content_plan(repo_root: Path, problems: list[Problem]) -> tuple[int, int]:
    data = load_json(repo_root / CONTENT_PLAN, problems)
    if data is None:
        return 0, 0

    remaining_moves = data.get("remaining_unsafe_moves")
    if not isinstance(remaining_moves, list):
        problems.append(Problem(CONTENT_PLAN, "remaining_unsafe_moves must be a list"))
        return 0, 0

    for index, move in enumerate(remaining_moves):
        move_path = Path(f"{CONTENT_PLAN}#remaining_unsafe_moves[{index}]")
        if not isinstance(move, dict):
            problems.append(Problem(move_path, "unsafe move entry must be an object"))
            continue
        validate_blocker_fields(
            repo_root=repo_root,
            move=move,
            move_path=move_path,
            gate_field="required_gates",
            ledger_field="classification_ledger",
            problems=problems,
        )

    decomposed_moves = data.get("decomposed_broad_moves", [])
    if not isinstance(decomposed_moves, list):
        problems.append(Problem(CONTENT_PLAN, "decomposed_broad_moves must be a list when present"))
        return len(remaining_moves), 0

    for index, move in enumerate(decomposed_moves):
        move_path = Path(f"{CONTENT_PLAN}#decomposed_broad_moves[{index}]")
        if not isinstance(move, dict):
            problems.append(Problem(move_path, "decomposed broad move entry must be an object"))
            continue
        validate_blocker_fields(
            repo_root=repo_root,
            move=move,
            move_path=move_path,
            gate_field="remaining_gates",
            ledger_field="classification_ledger",
            problems=problems,
        )

    return len(remaining_moves), len(decomposed_moves)


def missing_references(repo_root: Path, anchors: list[Path], problems: list[Problem]) -> list[MissingReference]:
    missing: list[MissingReference] = []
    for surface in SHARED_SURFACES:
        links = markdown_links(repo_root, surface, problems)
        for anchor in anchors:
            if anchor not in links:
                missing.append(MissingReference(anchor=anchor, surface=surface))
    return missing


def display(path: Path) -> str:
    return path.as_posix()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.root).resolve()
    problems: list[Problem] = []

    anchors = topic_evidence_anchors(repo_root, problems)
    unsafe_moves, decomposed_moves = validate_content_plan(repo_root, problems)
    missing = missing_references(repo_root, anchors, problems)

    if problems:
        for problem in problems:
            print(f"FAIL {display(problem.path)}: {problem.message}", file=sys.stderr)
        return 1

    if args.verbose or args.require_clean:
        for item in missing:
            print(
                "MISSING docs_root_navigation_ref "
                f"surface={display(item.surface.path)} anchor={display(item.anchor)}"
            )

    status = "clean" if not missing and unsafe_moves == 0 and decomposed_moves == 0 else "blocked"
    summary = (
        "OK docs_root_navigation_drift=audit "
        f"status={status} surfaces={len(SHARED_SURFACES)} anchors={len(anchors)} "
        f"missing_refs={len(missing)} unsafe_moves={unsafe_moves} decomposed_moves={decomposed_moves}"
    )

    if args.require_clean and status != "clean":
        print(summary.replace("OK ", "FAIL ", 1), file=sys.stderr)
        return 1

    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
