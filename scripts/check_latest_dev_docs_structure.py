#!/usr/bin/env python3
"""Focused structure and Markdown-link checks for development/latest-dev-docs."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote


EXPECTED_SECTIONS = (
    "root-plans",
    "backend-core",
    "backend-docs",
    "ops-frontend",
    "development-plans",
    "frontend-modern",
)

LINK_RE = re.compile(r"(!?\[[^\]]*\]\(([^)]+)\))")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


@dataclass(frozen=True)
class Problem:
    path: Path
    message: str


@dataclass(frozen=True)
class LinkStats:
    files: int
    links: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify latest-dev-docs has the required INDEX/main structure and "
            "check relative Markdown links in selected files or directories."
        )
    )
    parser.add_argument(
        "--root",
        default="development/latest-dev-docs",
        help="latest-dev-docs root to inspect",
    )
    parser.add_argument(
        "--link-path",
        action="append",
        default=[],
        help=(
            "Markdown file or directory to link-check. Can be repeated. "
            "If omitted, only structure is checked."
        ),
    )
    return parser.parse_args()


def check_structure(docs_root: Path) -> list[Problem]:
    problems: list[Problem] = []

    if not docs_root.is_dir():
        return [Problem(docs_root, "docs root does not exist")]

    for section in EXPECTED_SECTIONS:
        section_dir = docs_root / section
        index_file = section_dir / "INDEX.md"
        main_dir = section_dir / "main"
        main_index = main_dir / "index.md"
        merged_docs = sorted(main_dir.glob("MERGED_*.md"))

        if not section_dir.is_dir():
            problems.append(Problem(section_dir, "section directory is missing"))
            continue
        if not index_file.is_file():
            problems.append(Problem(index_file, "section INDEX.md is missing"))
        else:
            first_link = first_markdown_link(index_file)
            if first_link and not points_to_main(first_link):
                problems.append(
                    Problem(index_file, f"first Markdown link does not point to main/: {first_link}")
                )
        if not main_dir.is_dir():
            problems.append(Problem(main_dir, "main/ directory is missing"))
        if not main_index.is_file():
            problems.append(Problem(main_index, "main/index.md is missing"))
        if not merged_docs:
            problems.append(Problem(main_dir, "main/MERGED_*.md is missing"))

    return problems


def first_markdown_link(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    for match in LINK_RE.finditer(text):
        target = normalize_link_target(match.group(2))
        if target and not is_external_or_anchor(target):
            return target
    return None


def points_to_main(target: str) -> bool:
    stripped = link_path_without_fragment(target)
    while stripped.startswith("./"):
        stripped = stripped[2:]
    return stripped == "main/" or stripped.startswith("main/")


def iter_markdown_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() == ".md":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(p for p in path.rglob("*.md") if p.is_file()))
        else:
            files.append(path)
    return sorted(dict.fromkeys(files))


def normalize_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if not target:
        return ""
    if target.startswith("<") and ">" in target:
        return target[1 : target.find(">")].strip()

    for marker in (' "', " '", " ("):
        if marker in target:
            return target.split(marker, 1)[0].strip()
    return target


def is_external_or_anchor(target: str) -> bool:
    return (
        target.startswith("#")
        or target.startswith("//")
        or bool(SCHEME_RE.match(target))
    )


def link_path_without_fragment(target: str) -> str:
    no_fragment = target.split("#", 1)[0]
    no_query = no_fragment.split("?", 1)[0]
    return unquote(no_query)


def check_markdown_links(repo_root: Path, paths: list[Path]) -> tuple[list[Problem], LinkStats]:
    problems: list[Problem] = []
    markdown_files = iter_markdown_files(paths)
    checked_links = 0

    for md_file in markdown_files:
        if not md_file.exists():
            problems.append(Problem(md_file, "link-check path does not exist"))
            continue

        text = md_file.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            raw_target = normalize_link_target(match.group(2))
            if not raw_target or is_external_or_anchor(raw_target):
                continue

            link_path = link_path_without_fragment(raw_target)
            if not link_path:
                continue
            checked_links += 1

            if link_path.startswith("/"):
                candidate = repo_root / link_path.lstrip("/")
            else:
                candidate = md_file.parent / link_path
            if not candidate.exists():
                problems.append(Problem(md_file, f"missing link target: {raw_target}"))

    return problems, LinkStats(files=len(markdown_files), links=checked_links)


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    docs_root = (repo_root / args.root).resolve()
    link_paths = [(repo_root / raw).resolve() for raw in args.link_path]

    problems = check_structure(docs_root)
    link_stats = LinkStats(files=0, links=0)
    if link_paths:
        link_problems, link_stats = check_markdown_links(repo_root, link_paths)
        problems.extend(link_problems)

    if problems:
        for problem in problems:
            try:
                display_path = problem.path.relative_to(repo_root)
            except ValueError:
                display_path = problem.path
            print(f"FAIL {display_path}: {problem.message}", file=sys.stderr)
        return 1

    print(
        "OK latest_dev_docs_structure=passed "
        f"markdown_link_files={link_stats.files} markdown_links={link_stats.links}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
