#!/usr/bin/env python3
"""Check local Markdown link targets."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote


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
    parser = argparse.ArgumentParser(description="Check relative links in Markdown files or directories.")
    parser.add_argument("paths", nargs="+", help="Markdown files or directories, relative to the repository root.")
    return parser.parse_args()


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
    problems, link_stats = check_markdown_links(repo_root, [repo_root / path for path in args.paths])

    if problems:
        for problem in problems:
            try:
                display_path = problem.path.relative_to(repo_root)
            except ValueError:
                display_path = problem.path
            print(f"FAIL {display_path}: {problem.message}", file=sys.stderr)
        return 1

    print(
        "OK "
        f"markdown_link_files={link_stats.files} markdown_links={link_stats.links}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
