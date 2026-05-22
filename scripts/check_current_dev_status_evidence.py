#!/usr/bin/env python3
"""Check CURRENT_DEV status rows have repeatable evidence or blockers.

The gate is intentionally narrow: it does not close topics. It verifies that
the CURRENT_DEV index is consistent enough for a final completion audit.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote


DEFAULT_INDEX = "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md"
STATUS_SECTIONS = {
    "Partial": "partial",
    "Not Closed": "not_closed",
    "No Closure Claim / Retained Current Evidence": "no_closure_claim",
}
PRIMARY_STATUSES = set(STATUS_SECTIONS.values())
WAVE_TAGS = {
    "wave5_verified": "wave5",
    "wave6_verified": "wave6",
    "wave6_checked": "wave6",
    "wave7_verified": "wave7",
    "wave7_checked": "wave7",
    "wave8_verified": "wave8",
    "wave8_checked": "wave8",
    "wave9_verified": "wave9",
    "wave9_checked": "wave9",
    "wave10_verified": "wave10",
    "wave10_checked": "wave10",
    "wave11_verified": "wave11",
    "wave11_checked": "wave11",
    "wave12_verified": "wave12",
    "wave12_checked": "wave12",
    "wave13_verified": "wave13",
    "wave13_checked": "wave13",
    "wave14_verified": "wave14",
    "wave14_checked": "wave14",
    "wave15_verified": "wave15",
    "wave15_checked": "wave15",
    "wave16_verified": "wave16",
    "wave16_checked": "wave16",
}
ABSENT_TERMS = ("not present", "missing", "absent")
BLOCKER_TERMS = ("blocker", "blocked", "gap", "absent", "missing", "not present", "still", "remain")

COUNT_RE = re.compile(r"^- `(?P<status>[^`]+)`: (?P<count>\d+)\s*$", re.MULTILINE)
LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")
TAG_RE = re.compile(r"^-\s+`?((?:\[[^\]]+\])+)\`?")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


@dataclass(frozen=True)
class Problem:
    path: Path
    line_no: int | None
    message: str


@dataclass(frozen=True)
class Link:
    label: str
    target: str
    candidate: Path | None
    line_no: int

    @property
    def exists(self) -> bool:
        return self.candidate is None or self.candidate.exists()


@dataclass(frozen=True)
class Entry:
    status: str
    line_no: int
    raw: str
    tags: tuple[str, ...]
    links: tuple[Link, ...]

    @property
    def is_placeholder(self) -> bool:
        lowered = self.raw.lower()
        return "placeholder" in self.tags or "placeholder" in lowered

    @property
    def has_blocker_text(self) -> bool:
        lowered = self.raw.lower()
        return any(term in lowered for term in BLOCKER_TERMS)

    @property
    def covered(self) -> bool:
        return self.status in self.tags or len(self.links) > 1 or self.has_blocker_text


@dataclass(frozen=True)
class Result:
    root: Path
    index: Path
    expected: dict[str, int]
    actual: Counter[str]
    entries: tuple[Entry, ...]
    links: tuple[Link, ...]
    placeholders: tuple[Entry, ...]
    empty_dirs: tuple[Path, ...]
    wave_rows: tuple[tuple[Entry, str, tuple[Link, ...]], ...]
    problems: tuple[Problem, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate CURRENT_DEV status counts, links, placeholders, and Wave evidence."
    )
    parser.add_argument("--root", default=".", help="Repository root; defaults to cwd.")
    parser.add_argument("--index", default=DEFAULT_INDEX, help="CURRENT_DEV index path relative to --root.")
    parser.add_argument("--write-report", help="Optional Markdown report path relative to --root.")
    return parser.parse_args()


def normalize_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.find(">")].strip()
    for marker in (' "', " '", " ("):
        if marker in target:
            return target.split(marker, 1)[0].strip()
    return target


def is_external_or_anchor(target: str) -> bool:
    return target.startswith("#") or target.startswith("//") or bool(SCHEME_RE.match(target))


def target_path(target: str) -> str:
    return unquote(target.split("#", 1)[0].split("?", 1)[0])


def parse_link(root: Path, index: Path, label: str, raw_target: str, line_no: int) -> Link:
    target = normalize_target(raw_target)
    if not target or is_external_or_anchor(target):
        return Link(label=label, target=target, candidate=None, line_no=line_no)
    path_text = target_path(target)
    if not path_text:
        return Link(label=label, target=target, candidate=None, line_no=line_no)
    candidate = root / path_text.lstrip("/") if path_text.startswith("/") else index.parent / path_text
    return Link(label=label, target=target, candidate=candidate.resolve(), line_no=line_no)


def line_links(root: Path, index: Path, line: str, line_no: int) -> tuple[Link, ...]:
    return tuple(parse_link(root, index, label, target, line_no) for _, label, target in LINK_RE.findall(line))


def expected_counts(text: str) -> dict[str, int]:
    return {
        match.group("status"): int(match.group("count"))
        for match in COUNT_RE.finditer(text)
        if match.group("status") in PRIMARY_STATUSES
    }


def parse_entries(root: Path, index: Path, text: str) -> tuple[Entry, ...]:
    entries: list[Entry] = []
    current_status: str | None = None
    for line_no, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            current_status = STATUS_SECTIONS.get(line.removeprefix("## ").strip())
            continue
        if current_status is None or not line.startswith("- "):
            continue
        tag_match = TAG_RE.match(line)
        tag_blob = tag_match.group(1) if tag_match else ""
        tags = tuple(tag.lower() for tag in re.findall(r"\[([^\]]+)\]", tag_blob))
        entries.append(
            Entry(
                status=current_status,
                line_no=line_no,
                raw=line,
                tags=tags,
                links=line_links(root, index, line, line_no),
            )
        )
    return tuple(entries)


def find_empty_dirs(current_dev: Path) -> tuple[Path, ...]:
    if not current_dev.is_dir():
        return ()
    return tuple(sorted(path for path in current_dev.rglob("*") if path.is_dir() and not any(path.iterdir())))


def check(root: Path, index_rel: str) -> Result:
    index = (root / index_rel).resolve()
    problems: list[Problem] = []
    if not index.is_file():
        return Result(root, index, {}, Counter(), (), (), (), (), (), (Problem(index, None, "index is missing"),))

    text = index.read_text(encoding="utf-8")
    expected = expected_counts(text)
    entries = parse_entries(root, index, text)
    actual = Counter(entry.status for entry in entries)
    links = tuple(link for n, line in enumerate(text.splitlines(), 1) for link in line_links(root, index, line, n))

    for status in sorted(PRIMARY_STATUSES):
        if status not in expected:
            problems.append(Problem(index, None, f"missing expected count for {status}"))
        elif actual[status] != expected[status]:
            problems.append(Problem(index, None, f"{status} count mismatch: expected {expected[status]}, got {actual[status]}"))

    for link in links:
        if not link.exists:
            problems.append(Problem(index, link.line_no, f"missing Markdown link target: {link.target}"))

    for entry in entries:
        if entry.status not in entry.tags:
            problems.append(Problem(index, entry.line_no, f"entry lacks [{entry.status}] tag"))
        conflicting = sorted(tag for tag in entry.tags if tag in PRIMARY_STATUSES and tag != entry.status)
        if conflicting:
            problems.append(Problem(index, entry.line_no, f"conflicting primary status tags: {conflicting}"))
        if not entry.covered:
            problems.append(Problem(index, entry.line_no, "entry lacks status tag, evidence link, or blocker text"))
        if not entry.links and not entry.is_placeholder:
            problems.append(Problem(index, entry.line_no, "non-placeholder entry lacks a topic link"))
        if entry.is_placeholder and not any(term in entry.raw.lower() for term in ABSENT_TERMS):
            problems.append(Problem(index, entry.line_no, "placeholder entry should explicitly mark the path absent"))

    wave_rows: list[tuple[Entry, str, tuple[Link, ...]]] = []
    for entry in entries:
        for tag in entry.tags:
            wave_key = WAVE_TAGS.get(tag)
            if wave_key is None:
                continue
            explicit_matches = tuple(
                link for link in entry.links if wave_key in f"{link.label} {link.target}".lower()
            )
            matches = explicit_matches or entry.links[1:]
            wave_rows.append((entry, tag, matches))
            if not matches:
                problems.append(Problem(index, entry.line_no, f"{tag} entry lacks a {wave_key} evidence link"))
            elif not any(link.exists for link in matches):
                problems.append(Problem(index, entry.line_no, f"{tag} evidence links do not resolve"))

    empty_dirs = find_empty_dirs(index.parent)
    for empty_dir in empty_dirs:
        mentioned = any(empty_dir.name in entry.raw and (entry.is_placeholder or entry.has_blocker_text) for entry in entries)
        if not mentioned:
            problems.append(Problem(empty_dir, None, "empty CURRENT_DEV directory is not identified as placeholder/blocker"))

    placeholders = tuple(entry for entry in entries if entry.is_placeholder)
    return Result(root, index, expected, actual, entries, links, placeholders, empty_dirs, tuple(wave_rows), tuple(problems))


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def write_report(result: Result, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    status = "PASS" if result.ok else "FAIL"
    rel_index = os.path.relpath(result.index, report_path.parent)
    rel_script = os.path.relpath(result.root / "scripts/check_current_dev_status_evidence.py", report_path.parent)
    rows_with_evidence = sum(1 for entry in result.entries if len(entry.links) > 1)
    rows_with_blockers = sum(1 for entry in result.entries if entry.has_blocker_text)
    lines = [
        "# CURRENT_DEV Status Evidence Gate",
        "",
        f"- status: `{status}`",
        f"- index: [{rel(result.index, result.root)}]({rel_index})",
        f"- gate script: [{rel_script}]({rel_script})",
        "- scope: repeatable status/evidence checks only; this run does not close or archive individual topics.",
        "",
        "## Summary",
        "",
        "| Check | Value |",
        "|---|---:|",
        f"| active entries | {len(result.entries)} |",
        f"| Markdown links checked | {len(result.links)} |",
        f"| placeholder entries recognized | {len(result.placeholders)} |",
        f"| empty directories recognized | {len(result.empty_dirs)} |",
        f"| Wave5/Wave6/Wave7/Wave8/Wave9/Wave10/Wave11/Wave12/Wave13/Wave14/Wave15 evidence rows checked | {len(result.wave_rows)} |",
        f"| problems | {len(result.problems)} |",
        "",
        "## Count Gate",
        "",
        "| Status | Expected | Parsed |",
        "|---|---:|---:|",
    ]
    for name in ("partial", "not_closed", "no_closure_claim"):
        lines.append(f"| `{name}` | {result.expected.get(name, 0)} | {result.actual.get(name, 0)} |")
    lines.extend(
        [
            "",
            "## Coverage Gate",
            "",
            "| Coverage source | Rows |",
            "|---|---:|",
            f"| matching primary status tag | {sum(1 for entry in result.entries if entry.status in entry.tags)} |",
            f"| additional evidence link | {rows_with_evidence} |",
            f"| explicit blocker/gap text | {rows_with_blockers} |",
            f"| placeholder row | {len(result.placeholders)} |",
            "",
            "A row passes when it has a matching primary status tag, an evidence link, or explicit blocker/gap text.",
            "",
            "## Wave Evidence Gate",
            "",
            "| Line | Tag | Wave evidence links |",
            "|---:|---|---:|",
        ]
    )
    for entry, tag, links in result.wave_rows:
        lines.append(f"| {entry.line_no} | `{tag}` | {len(links)} |")
    if result.problems:
        lines.extend(["", "## Problems", ""])
        for problem in result.problems:
            suffix = f":{problem.line_no}" if problem.line_no else ""
            lines.append(f"- `{rel(problem.path, result.root)}{suffix}`: {problem.message}")
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def print_result(result: Result) -> None:
    counts = ",".join(f"{name}:{result.actual.get(name, 0)}" for name in ("partial", "not_closed", "no_closure_claim"))
    if result.ok:
        print(
            "OK current_dev_status_evidence=passed "
            f"entries={len(result.entries)} counts={counts} links={len(result.links)} "
            f"placeholders={len(result.placeholders)} empty_dirs={len(result.empty_dirs)} wave_rows={len(result.wave_rows)}"
        )
        return
    print(
        f"FAIL current_dev_status_evidence=failed entries={len(result.entries)} counts={counts} problems={len(result.problems)}",
        file=sys.stderr,
    )
    for problem in result.problems:
        suffix = f":{problem.line_no}" if problem.line_no else ""
        print(f"FAIL {rel(problem.path, result.root)}{suffix}: {problem.message}", file=sys.stderr)


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    result = check(root, args.index)
    if args.write_report:
        write_report(result, (root / args.write_report).resolve())
    print_result(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
