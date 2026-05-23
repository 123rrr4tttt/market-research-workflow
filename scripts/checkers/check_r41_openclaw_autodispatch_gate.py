#!/usr/bin/env python3
"""Repo-local gate for the R41 OpenClaw autodispatch CURRENT_DEV row.

The checker intentionally reads only the mirrored topic documents in this
repository. It does not inspect the external OpenClaw workspace or claim
runtime state there.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TOPIC_NAME = "2026-03-04-r41-openclaw-autodispatch"
CURRENT_TOPIC_REL = Path("development/latest-dev-docs/development-plans/CURRENT_DEV") / TOPIC_NAME
ARCHIVE_CLOSED_TOPIC_REL = Path("docs/development/development-plans/ARCHIVE_CLOSED") / TOPIC_NAME
ARCHIVE_EXTERNAL_BLOCKED_TOPIC_REL = (
    Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED") / TOPIC_NAME
)
TOPIC_CANDIDATE_RELS = (ARCHIVE_CLOSED_TOPIC_REL, ARCHIVE_EXTERNAL_BLOCKED_TOPIC_REL, CURRENT_TOPIC_REL)
TOPIC_REL = ARCHIVE_CLOSED_TOPIC_REL
AUTODISPATCH_REL = Path("orchestration/line-autodispatch-2026-03-04-scout-r41.md")
INTERFACE_CONTRACT_REL = Path("R41_INTERFACE_CONTRACT.md")

EXPECTED_STATUS = "skipped"
EXPECTED_REASON = "no_unfinished_line_task"
EXPECTED_READY_DISPATCH_COUNT = "0"
EXPECTED_LINES = ("A", "B", "C", "D", "E", "F")
EXPECTED_REQUIRED_FIELDS = {
    "A": (
        "anchor_freeze_id",
        "anchor_epoch",
        "freeze_approver_chain",
        "shift_ticket_id",
    ),
    "B": (
        "auto_degrade_plan_ref",
        "owner_ack",
        "escalation_stage",
    ),
    "C": (
        "normalization_profile_id",
        "profile_signature",
        "score_reason_code",
        "evidence_digest",
        "lifecycle_state",
        "sunset_checkpoint_ref",
    ),
    "D": (
        "deterministic_replay_proof",
        "seed",
        "runtime_fingerprint",
        "timeout_severity",
        "remediation_ticket",
    ),
    "E": (
        "threshold_source_signature",
        "policy_epoch",
        "drill_proof_ref",
        "freshness_window_days",
    ),
    "F": (
        "anchor_lineage",
        "comparable_batch_set_hash",
        "approval_chain_ref",
        "expiry_guard",
    ),
}

KV_RE = re.compile(r"^\s*-\s*(?P<key>[A-Za-z0-9_-]+):\s*(?P<value>.*?)\s*$")


@dataclass(frozen=True)
class Problem:
    path: Path
    line_no: int | None
    message: str


@dataclass(frozen=True)
class GateResult:
    topic: Path
    problems: tuple[Problem, ...]
    line_count: int
    required_field_count: int

    @property
    def ok(self) -> bool:
        return not self.problems


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate repo-local R41 OpenClaw autodispatch evidence without "
            "reading the external OpenClaw workspace."
        )
    )
    parser.add_argument(
        "--root",
        "--repo-root",
        dest="root",
        default=str(REPO_ROOT),
        help="Repository root; defaults to this checkout.",
    )
    parser.add_argument(
        "--topic",
        default=None,
        help=(
            "R41 topic folder relative to --root/--repo-root, or an absolute topic path. "
            "Defaults to the first existing archive/current-dev topic path."
        ),
    )
    return parser.parse_args()


def clean_value(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`") and len(value) >= 2:
        value = value[1:-1]
    return value.strip()


def markdown_row_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_kv_lines(text: str) -> dict[str, tuple[str, int]]:
    values: dict[str, tuple[str, int]] = {}
    for line_no, line in enumerate(text.splitlines(), start=1):
        match = KV_RE.match(line)
        if match:
            values[match.group("key")] = (clean_value(match.group("value")), line_no)
    return values


def parse_autodispatch_table(text: str) -> dict[str, tuple[dict[str, str], int]]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        cells = [cell.lower() for cell in markdown_row_cells(line)]
        if "line" not in cells or "task_id" not in cells:
            continue
        header = cells
        rows: dict[str, tuple[dict[str, str], int]] = {}
        for row_index in range(index + 2, len(lines)):
            row_line = lines[row_index]
            if not row_line.strip().startswith("|"):
                break
            values = markdown_row_cells(row_line)
            if len(values) != len(header):
                continue
            row = dict(zip(header, values))
            line_key = clean_value(row.get("line", ""))
            if line_key:
                rows[line_key] = (row, row_index + 1)
        return rows
    return {}


def read_text(path: Path, problems: list[Problem]) -> str:
    if not path.is_file():
        problems.append(Problem(path, None, "required document is missing"))
        return ""
    return path.read_text(encoding="utf-8")


def check_autodispatch_doc(path: Path, text: str, problems: list[Problem]) -> int:
    kv = parse_kv_lines(text)

    def require_key(key: str, expected: str) -> None:
        if key not in kv:
            problems.append(Problem(path, None, f"missing autodispatch key: {key}"))
            return
        actual, line_no = kv[key]
        if actual != expected:
            problems.append(Problem(path, line_no, f"{key} expected {expected!r}, got {actual!r}"))

    require_key("status", EXPECTED_STATUS)
    require_key("reason", EXPECTED_REASON)
    require_key("ready_dispatch_count", EXPECTED_READY_DISPATCH_COUNT)

    if "contract_lock_required" not in kv:
        problems.append(Problem(path, None, "missing contract_lock_required marker"))
    else:
        value, line_no = kv["contract_lock_required"]
        lowered = value.lower()
        if "yes" not in lowered or "interface-unify" not in lowered:
            problems.append(
                Problem(
                    path,
                    line_no,
                    "contract_lock_required must note yes and interface-unify dependency",
                )
            )

    rows = parse_autodispatch_table(text)
    unexpected = sorted(line for line in rows if line not in EXPECTED_LINES)
    if unexpected:
        problems.append(Problem(path, None, f"unexpected autodispatch line rows: {unexpected}"))

    for line_key in EXPECTED_LINES:
        if line_key not in rows:
            problems.append(Problem(path, None, f"missing autodispatch table row for line {line_key}"))
            continue
        row, line_no = rows[line_key]
        task_id = clean_value(row.get("task_id", "")).lower()
        if task_id != "none":
            problems.append(Problem(path, line_no, f"line {line_key} task_id expected 'none', got {task_id!r}"))

    return len(rows)


def required_fields_section(text: str) -> str:
    in_section = False
    collected: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if in_section:
                break
            in_section = line.strip() == "## R41 Required Fields (by line)"
            continue
        if in_section:
            collected.append(line)
    return "\n".join(collected)


def check_interface_contract(path: Path, text: str, problems: list[Problem]) -> int:
    if "Version: `R41`" not in text:
        problems.append(Problem(path, None, "missing R41 version marker"))
    if "Source batch: `2026-03-04-scout-r41`" not in text:
        problems.append(Problem(path, None, "missing R41 source batch marker"))

    section = required_fields_section(text)
    if not section.strip():
        problems.append(Problem(path, None, "missing R41 Required Fields section"))
        return 0

    found_count = 0
    for line_key, expected_fields in EXPECTED_REQUIRED_FIELDS.items():
        match = re.search(rf"^- {re.escape(line_key)}:\s*(?P<fields>.+)$", section, flags=re.MULTILINE)
        if not match:
            problems.append(Problem(path, None, f"missing required-field row for line {line_key}"))
            continue
        row_text = match.group("fields")
        for field in expected_fields:
            if f"`{field}`" not in row_text:
                problems.append(Problem(path, None, f"line {line_key} missing required field {field}"))
            else:
                found_count += 1
    return found_count


def check_topic(topic: Path) -> GateResult:
    problems: list[Problem] = []
    autodispatch_path = topic / AUTODISPATCH_REL
    interface_path = topic / INTERFACE_CONTRACT_REL

    autodispatch_text = read_text(autodispatch_path, problems)
    interface_text = read_text(interface_path, problems)

    line_count = check_autodispatch_doc(autodispatch_path, autodispatch_text, problems) if autodispatch_text else 0
    required_field_count = check_interface_contract(interface_path, interface_text, problems) if interface_text else 0
    return GateResult(
        topic=topic,
        problems=tuple(problems),
        line_count=line_count,
        required_field_count=required_field_count,
    )


def resolve_topic_path(root: Path, topic: Path | None = None) -> Path:
    if topic is not None:
        return topic if topic.is_absolute() else root / topic
    for relative in TOPIC_CANDIDATE_RELS:
        candidate = root / relative
        if candidate.is_dir():
            return candidate
    return root / TOPIC_REL


def display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    topic_arg = Path(args.topic) if args.topic else None
    topic = resolve_topic_path(root, topic_arg)

    result = check_topic(topic)
    if not result.ok:
        for problem in result.problems:
            location = display_path(problem.path, root)
            if problem.line_no is not None:
                location = f"{location}:{problem.line_no}"
            print(f"FAIL r41_openclaw_autodispatch_gate {location}: {problem.message}", file=sys.stderr)
        return 1

    print(
        "OK r41_openclaw_autodispatch_gate=passed "
        f"topic={display_path(result.topic, root)} "
        f"status={EXPECTED_STATUS} reason={EXPECTED_REASON} "
        f"ready_dispatch_count={EXPECTED_READY_DISPATCH_COUNT} "
        f"line_task_ids_none={result.line_count} "
        f"required_fields={result.required_field_count} "
        "contract_lock=noted external_runtime_checked=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
