#!/usr/bin/env python3
"""Repo-local R41 OpenClaw runtime handoff gate.

This checker verifies that the repository mirror tells one consistent story:
the R41 handoff is present, the mirrored autodispatch gate remains skipped with
no ready line tasks, and the implementation notes record a no-op handoff rather
than a live external OpenClaw runtime validation.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
TOPIC_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-03-04-r41-openclaw-autodispatch"
)
BATCH = "2026-03-04-scout-r41"
AUTODISPATCH_GATE_SCRIPT = Path("scripts/checkers/check_r41_openclaw_autodispatch_gate.py")

AUTODISPATCH_REL = Path("orchestration/line-autodispatch-2026-03-04-scout-r41.md")
EVIDENCE_REL = Path("implementation/WAVE15_R41_OPENCLAW_RUNTIME_HANDOFF_EVIDENCE.md")
REFERENCE_POOL_REL = Path("reference-pool/2026-03-04-scout-r41")
CODEX_HANDOFF_REL = REFERENCE_POOL_REL / "codex_handoff.md"
DEDUP_DIFF_REL = REFERENCE_POOL_REL / "dedup_diff.md"
REFERENCE_INDEX_REL = REFERENCE_POOL_REL / "INDEX.md"
INTERFACE_ALIGNMENT_REL = REFERENCE_POOL_REL / "interface_envelope_alignment.md"

EXPECTED_LINES = ("A", "B", "C", "D", "E", "F")
EXPECTED_HANDOFF_TASKS = {line: (f"{line}-R41-M1", f"{line}-R41-M2") for line in EXPECTED_LINES}
EXPECTED_REFERENCE_FILES = (
    "AB-envelope.md",
    "CD-envelope.md",
    "EF-envelope.md",
    "reference_pack.md",
    "research_note.md",
    "codex_handoff.md",
    "dedup_diff.md",
    "source_repo_urls.txt",
    "line_sync_leveling.md",
    "interface_envelope_alignment.md",
    "structural_inconsistency_patch.md",
)

READY_ZERO_RE = re.compile(r"ready_dispatch_count\s*(?:=|:|：)?\s*`?0`?")
RUN_STATE_RE = re.compile(r"(run_state|run state|state/runs/line-autodispatch-2026-03-04-scout-r41\.json)")
NO_RUNTIME_SLICE_RE = re.compile(
    r"(未生成|未新增).{0,40}(development/interface-unify|development/interface|执行切片)|无可推进"
)
TASK_RE = re.compile(r"^\s*-\s*task_id:\s*(?P<task>[A-F]-R41-M[12])\s*$")
LINE_RE = re.compile(r"^line:\s*(?P<line>[A-F])\s*$")
FORBIDDEN_LIVE_CLAIMS = (
    re.compile(r"external_openclaw_runtime_live_verified:\s*`?true`?", re.IGNORECASE),
    re.compile(r"external_runtime_checked:\s*`?true`?", re.IGNORECASE),
    re.compile(r"runtime_handoff_status:\s*`?live_verified`?", re.IGNORECASE),
)


@dataclass(frozen=True)
class Problem:
    path: Path
    line_no: int | None
    message: str


@dataclass(frozen=True)
class ImplementationDoc:
    path: Path
    label: str
    lines: tuple[str, ...]
    r42_envelope: str


IMPLEMENTATION_DOCS = (
    ImplementationDoc(
        Path("implementation/SA1-R41-AB-line-unfinished-autodispatch.md"),
        "SA1-AB",
        ("A", "B"),
        "AB-envelope.md",
    ),
    ImplementationDoc(
        Path("implementation/SA2-R41-CD-line-unfinished-autodispatch.md"),
        "SA2-CD",
        ("C", "D"),
        "CD-envelope.md",
    ),
    ImplementationDoc(
        Path("implementation/SA3-R41-EF-line-unfinished-autodispatch.md"),
        "SA3-EF",
        ("E", "F"),
        "EF-envelope.md",
    ),
)


@dataclass(frozen=True)
class GateResult:
    topic: Path
    problems: tuple[Problem, ...]
    mirror_line_rows: int
    handoff_task_count: int
    implementation_doc_count: int
    reference_file_count: int

    @property
    def ok(self) -> bool:
        return not self.problems


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate repo-local R41 OpenClaw handoff and external runtime boundary evidence."
    )
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repository root; defaults to this checkout.")
    parser.add_argument(
        "--topic",
        default=str(TOPIC_REL),
        help="R41 topic folder relative to --root, or an absolute topic path.",
    )
    return parser.parse_args()


def load_autodispatch_gate(root: Path) -> ModuleType:
    script_path = root / AUTODISPATCH_GATE_SCRIPT
    spec = importlib.util.spec_from_file_location("check_r41_openclaw_autodispatch_gate_runtime_handoff", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load autodispatch checker: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_text(path: Path, problems: list[Problem]) -> str:
    if not path.is_file():
        problems.append(Problem(path, None, "required document is missing"))
        return ""
    return path.read_text(encoding="utf-8")


def line_no(text: str, needle: str) -> int | None:
    for index, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return index
    return None


def regex_line_no(text: str, pattern: re.Pattern[str]) -> int | None:
    for index, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            return index
    return None


def require_contains(path: Path, text: str, needle: str, problems: list[Problem], message: str | None = None) -> None:
    if needle not in text:
        problems.append(Problem(path, None, message or f"missing marker: {needle}"))


def require_regex(path: Path, text: str, pattern: re.Pattern[str], problems: list[Problem], message: str) -> None:
    if not pattern.search(text):
        problems.append(Problem(path, None, message))


def check_mirror_gate(topic: Path, root: Path, problems: list[Problem]) -> int:
    try:
        mirror_gate = load_autodispatch_gate(root)
    except RuntimeError as exc:
        problems.append(Problem(root / AUTODISPATCH_GATE_SCRIPT, None, str(exc)))
        return 0

    result = mirror_gate.check_topic(topic)
    if not result.ok:
        for problem in result.problems:
            problems.append(Problem(problem.path, problem.line_no, f"mirror gate failed: {problem.message}"))
        return int(getattr(result, "line_count", 0))

    return int(result.line_count)


def check_autodispatch_runtime_state(topic: Path, problems: list[Problem]) -> None:
    path = topic / AUTODISPATCH_REL
    text = read_text(path, problems)
    if not text:
        return
    require_contains(path, text, f"batch: `{BATCH}`", problems)
    require_contains(path, text, "status: `skipped`", problems)
    require_contains(path, text, "reason: no_unfinished_line_task", problems)
    require_regex(path, text, READY_ZERO_RE, problems, "ready_dispatch_count must remain 0")
    for line in EXPECTED_LINES:
        require_contains(path, text, f"| {line} | none |", problems, f"line {line} must remain task_id=none")


def parse_handoff_tasks(text: str) -> dict[str, list[str]]:
    current_line: str | None = None
    tasks: dict[str, list[str]] = {line: [] for line in EXPECTED_LINES}
    for raw_line in text.splitlines():
        line_match = LINE_RE.match(raw_line)
        if line_match:
            current_line = line_match.group("line")
            continue
        task_match = TASK_RE.match(raw_line)
        if task_match and current_line in tasks:
            tasks[current_line].append(task_match.group("task"))
    return tasks


def check_handoff_doc(topic: Path, problems: list[Problem]) -> int:
    path = topic / CODEX_HANDOFF_REL
    text = read_text(path, problems)
    if not text:
        return 0
    require_contains(path, text, f"Codex Handoff — {BATCH}", problems, "handoff title must preserve R41 batch")
    require_contains(path, text, "must_to_atomic:", problems)
    require_contains(path, text, "next-batch-trigger:", problems)
    require_contains(path, text, "runtime_fingerprint", problems, "line D handoff must preserve runtime_fingerprint handoff field")
    tasks = parse_handoff_tasks(text)
    for line, expected in EXPECTED_HANDOFF_TASKS.items():
        actual = tuple(tasks.get(line, ()))
        if actual != expected:
            problems.append(Problem(path, None, f"line {line} task list expected {expected}, got {actual}"))
    return sum(len(value) for value in tasks.values())


def check_implementation_docs(topic: Path, problems: list[Problem]) -> int:
    checked = 0
    for doc in IMPLEMENTATION_DOCS:
        path = topic / doc.path
        text = read_text(path, problems)
        if not text:
            continue
        checked += 1
        require_contains(path, text, "line_unfinished_autodispatch", problems)
        require_contains(path, text, "LINE_AUTODISPATCH_skipped", problems)
        require_contains(path, text, "no_unfinished_line_task", problems)
        require_regex(path, text, READY_ZERO_RE, problems, f"{doc.label} must record ready_dispatch_count=0")
        require_regex(path, text, RUN_STATE_RE, problems, f"{doc.label} must record the R41 run-state path")
        require_regex(path, text, NO_RUNTIME_SLICE_RE, problems, f"{doc.label} must record no development/interface runtime slice")
        require_contains(path, text, "R42", problems, f"{doc.label} must keep next-batch research boundary")
        require_contains(path, text, "research", problems, f"{doc.label} must keep research-only boundary")
        require_contains(path, text, doc.r42_envelope, problems, f"{doc.label} must name its R42 research envelope")
        for line in doc.lines:
            if line not in text:
                problems.append(Problem(path, None, f"{doc.label} does not mention line {line}"))
    return checked


def check_reference_mirror(topic: Path, problems: list[Problem]) -> int:
    index_path = topic / REFERENCE_INDEX_REL
    index_text = read_text(index_path, problems)
    file_count = 0
    if index_text:
        require_contains(index_path, index_text, f"batch: `{BATCH}`", problems)
        for name in EXPECTED_REFERENCE_FILES:
            file_path = topic / REFERENCE_POOL_REL / name
            if file_path.is_file():
                file_count += 1
            else:
                problems.append(Problem(file_path, None, "reference mirror file is missing"))
            require_contains(index_path, index_text, f"`{name}`", problems, f"reference index missing {name}")

    dedup_path = topic / DEDUP_DIFF_REL
    dedup_text = read_text(dedup_path, problems)
    if dedup_text:
        require_contains(dedup_path, dedup_text, f"baseline_batch: {BATCH}", problems)
        require_contains(dedup_path, dedup_text, "ready_for_r41_buildlane: yes", problems)
        require_contains(dedup_path, dedup_text, "boundaries:", problems)

    alignment_path = topic / INTERFACE_ALIGNMENT_REL
    alignment_text = read_text(alignment_path, problems)
    if alignment_text:
        require_contains(alignment_path, alignment_text, f"batch: `{BATCH}`", problems)
        require_contains(alignment_path, alignment_text, "total_line_added_keys: 0", problems)
        for line in EXPECTED_LINES:
            require_contains(
                alignment_path,
                alignment_text,
                f"| {line} | 0 | none | no_new_key |",
                problems,
                f"interface alignment must keep line {line} as no_new_key",
            )

    return file_count


def check_evidence_doc(topic: Path, problems: list[Problem]) -> None:
    path = topic / EVIDENCE_REL
    text = read_text(path, problems)
    if not text:
        return

    required_markers = (
        "wave15_openclaw_runtime_handoff",
        "repo_local_handoff_mirror_consistent",
        "external_openclaw_runtime_live_verified: `false`",
        "external_runtime_checked: `false`",
        "runtime_handoff_status: `repo_local_handoff_mirror_only`",
        "scripts/checkers/check_r41_openclaw_runtime_handoff.py",
        "scripts/checkers/check_r41_openclaw_autodispatch_gate.py",
        "LINE_AUTODISPATCH_skipped",
        "no_unfinished_line_task",
        "ready_dispatch_count=0",
    )
    for marker in required_markers:
        require_contains(path, text, marker, problems)

    for claim_re in FORBIDDEN_LIVE_CLAIMS:
        claim_line = regex_line_no(text, claim_re)
        if claim_line is not None:
            problems.append(Problem(path, claim_line, "evidence doc must not claim external OpenClaw runtime live verification"))


def check_topic(topic: Path, root: Path | None = None) -> GateResult:
    root = (root or REPO_ROOT).resolve()
    topic = topic.resolve()
    problems: list[Problem] = []

    mirror_line_rows = check_mirror_gate(topic, root, problems)
    check_autodispatch_runtime_state(topic, problems)
    handoff_task_count = check_handoff_doc(topic, problems)
    implementation_doc_count = check_implementation_docs(topic, problems)
    reference_file_count = check_reference_mirror(topic, problems)
    check_evidence_doc(topic, problems)

    return GateResult(
        topic=topic,
        problems=tuple(problems),
        mirror_line_rows=mirror_line_rows,
        handoff_task_count=handoff_task_count,
        implementation_doc_count=implementation_doc_count,
        reference_file_count=reference_file_count,
    )


def display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    topic_arg = Path(args.topic)
    topic = topic_arg if topic_arg.is_absolute() else root / topic_arg

    result = check_topic(topic, root)
    if not result.ok:
        for problem in result.problems:
            location = display_path(problem.path, root)
            if problem.line_no is not None:
                location = f"{location}:{problem.line_no}"
            print(f"FAIL r41_openclaw_runtime_handoff {location}: {problem.message}", file=sys.stderr)
        return 1

    print(
        "OK r41_openclaw_runtime_handoff=passed "
        f"topic={display_path(result.topic, root)} "
        "repo_local_handoff_mirror_consistent=true "
        f"mirror_line_rows={result.mirror_line_rows} "
        f"handoff_tasks={result.handoff_task_count} "
        f"implementation_docs={result.implementation_doc_count} "
        f"reference_files={result.reference_file_count} "
        "external_openclaw_runtime_live_verified=false "
        "external_runtime_checked=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
