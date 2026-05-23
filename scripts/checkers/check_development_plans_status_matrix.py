#!/usr/bin/env python3
"""Check development-plans target topic classification and status consistency.

This gate is deliberately not a generic "every directory needs INDEX.md" check.
It separates real development target topics from navigation categories,
evidence/process records, compatibility shims, and embedded reference repos.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote


DEV_PLANS_ROOT = Path("development/latest-dev-docs/development-plans")
ALLOWLIST = DEV_PLANS_ROOT / "TARGET_TOPIC_ALLOWLIST.json"
CURRENT_DEV = DEV_PLANS_ROOT / "CURRENT_DEV"
CURRENT_DEV_INDEX = CURRENT_DEV / "INDEX.md"
ACTIVE_NAVIGATION = (
    DEV_PLANS_ROOT / "INDEX.md",
    CURRENT_DEV_INDEX,
)
PRIMARY_STATUSES = ("partial", "not_closed", "no_closure_claim")
HISTORICAL_MARKERS = ("historical", "history", "历史", "旧快照", "历史快照", "快照")

COUNT_RE = re.compile(r"`?(partial|not_closed|no_closure_claim)`?\s*[:：]\s*`?(\d+)`?", re.IGNORECASE)
LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
VALID_TARGET_STATUSES = {"active_current", "closed", "external_blocked", "retired"}
VALID_REVIEW_STATUSES = {"active_current", "closed", "external_blocked", "retired", "needs_update"}
DEFAULT_REFERENCE_EXCLUDES = ("**/references/repos/**", "references/repos/**")
PROFILE_SUFFIXES = {".md", ".json", ".yml", ".yaml", ".toml", ".txt", ".sh", ".py"}
CODE_RE = re.compile(
    r"(?:^|[\s`'\"(<\[])(?:\.?/)?(?:main|scripts|tests|src|app|frontend|backend|codex_settings|\.github)"
    r"/[^\s`'\"),>\]]+\.(?:py|ts|tsx|js|mjs|sh|yml|yaml|json|toml|md)\b|"
    r"(?:^|[\s`'\"(<\[])[\w./@+-]+/[\w./@+-]+\.(?:py|ts|tsx|js|mjs|sh)\b",
    re.MULTILINE,
)
SCRIPT_RE = re.compile(
    r"(?:^|[\s`])(?:PYTHONPATH=[^\s`]+\s+)?(?:python(?:3(?:\.\d+)?)?|bash|npm|pnpm|yarn|node)"
    r"[^\n`]*(?:scripts?/|check_|verify_|run_|pytest|test|lint|build|\.sh|\.py)\b|"
    r"(?:^|[\s`'\"(<\[])(?:\.?/)?(?:scripts|codex_settings/scripts|main/backend/scripts)/[^\s`'\"),>\]]+",
    re.IGNORECASE | re.MULTILINE,
)
TEST_RE = re.compile(
    r"\b(?:pytest|unittest|tests?/[^\s`'\"),]+|test_[\w.-]+\.py|"
    r"npm\s+(?:--prefix\s+\S+\s+)?run\s+test|[0-9]+\s+passed)\b",
    re.IGNORECASE,
)
GATE_RE = re.compile(
    r"\b(?:check_[\w-]+|verify_[\w-]+|gate|check:|lint|build|contract|smoke|readback|manifest)\b|验证|门禁",
    re.IGNORECASE,
)
EXTERNAL_RE = re.compile(
    r"\b(external_blocked|external blocker|live|production|public replay|tenant|provider|operator|human review|"
    r"not_run|not_verified|missing_real_evidence|外部|公网|生产|人工)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Problem:
    path: Path
    message: str
    line_no: int | None = None


@dataclass(frozen=True)
class StatusCount:
    status: str
    count: int
    path: Path
    line_no: int
    line: str


@dataclass(frozen=True)
class TargetTopic:
    path: Path
    status: str
    entrypoint: Path
    role: str = "development_target"
    review_status_override: str | None = None
    review_reason: str | None = None


@dataclass(frozen=True)
class EvidenceProfile:
    file_count: int
    has_code_reference: bool
    has_script_reference: bool
    has_test_reference: bool
    has_gate_reference: bool
    has_external_blocker: bool
    sample_files: tuple[Path, ...]


@dataclass(frozen=True)
class Result:
    status_counts: dict[str, int]
    targets: tuple[TargetTopic, ...]
    target_profiles: dict[Path, EvidenceProfile]
    non_target_roots: tuple[Path, ...]
    evidence_roots: tuple[Path, ...]
    active_navigation: tuple[Path, ...]
    problems: tuple[Problem, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check development-plans target topic allowlist and status matrix consistency."
    )
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--allowlist",
        default=str(ALLOWLIST),
        help="Target-topic allowlist JSON path relative to repo root.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a compact status line.",
    )
    parser.add_argument(
        "--fail-on-needs-update",
        action="store_true",
        help="Exit nonzero when any target profile is classified as needs_update.",
    )
    return parser.parse_args()


def reference_excludes(allowlist: dict[str, Any] | None = None) -> tuple[str, ...]:
    defaults = list(DEFAULT_REFERENCE_EXCLUDES)
    if not allowlist:
        return tuple(defaults)
    configured = allowlist.get("reference_excludes", [])
    if not isinstance(configured, list):
        return tuple(defaults)
    patterns = defaults
    for item in configured:
        if isinstance(item, str) and item and item not in patterns:
            patterns.append(item)
    return tuple(patterns)


def is_reference_repo_path(path: Path, patterns: tuple[str, ...] | None = None) -> bool:
    normalized = path.as_posix()
    active_patterns = patterns or DEFAULT_REFERENCE_EXCLUDES
    if any(fnmatch.fnmatch(normalized, pattern) for pattern in active_patterns):
        return True
    parts = path.parts
    return any(parts[index : index + 2] == ("references", "repos") for index in range(len(parts) - 1))


def rel(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return path


def read_text(
    root: Path,
    relative_path: Path,
    problems: list[Problem],
    reference_patterns: tuple[str, ...] | None = None,
) -> str:
    if is_reference_repo_path(relative_path, reference_patterns):
        return ""
    try:
        return (root / relative_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        problems.append(Problem(relative_path, "file is missing"))
    except UnicodeDecodeError as exc:
        problems.append(Problem(relative_path, f"file is not valid UTF-8: {exc}"))
    return ""


def read_json(root: Path, relative_path: Path, problems: list[Problem]) -> dict[str, Any]:
    text = read_text(root, relative_path, problems)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        problems.append(Problem(relative_path, f"JSON parse failed: {exc}"))
        return {}
    if not isinstance(parsed, dict):
        problems.append(Problem(relative_path, "allowlist root must be a JSON object"))
        return {}
    return parsed


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
    path_text = unquote(target.split("#", 1)[0].split("?", 1)[0])
    return path_text or None


def resolve_link(
    root: Path,
    source_rel: Path,
    raw_target: str,
    reference_patterns: tuple[str, ...] | None = None,
) -> Path | None:
    path_text = target_path(raw_target)
    if path_text is None:
        return None
    candidate = root / path_text.lstrip("/") if path_text.startswith("/") else root / source_rel.parent / path_text
    try:
        relative = candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    if is_reference_repo_path(relative, reference_patterns):
        return None
    return relative


def parse_current_status_counts(
    root: Path, problems: list[Problem], reference_patterns: tuple[str, ...] | None = None
) -> dict[str, int]:
    text = read_text(root, CURRENT_DEV_INDEX, problems, reference_patterns)
    counts: dict[str, int] = {}
    in_distribution = False
    for line in text.splitlines():
        if line.startswith("## "):
            title = line.removeprefix("## ").strip().lower()
            in_distribution = title in {"剩余状态分布", "remaining status distribution"}
            continue
        if not in_distribution:
            continue
        match = COUNT_RE.search(line)
        if match:
            counts[match.group(1).lower()] = int(match.group(2))
    return counts


def historical_count_line(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in HISTORICAL_MARKERS)


def status_counts_in_active_navigation(
    root: Path, problems: list[Problem], reference_patterns: tuple[str, ...] | None = None
) -> list[StatusCount]:
    counts: list[StatusCount] = []
    for surface in ACTIVE_NAVIGATION:
        text = read_text(root, surface, problems, reference_patterns)
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "references/repos" in line:
                continue
            for match in COUNT_RE.finditer(line):
                counts.append(
                    StatusCount(
                        status=match.group(1).lower(),
                        count=int(match.group(2)),
                        path=surface,
                        line_no=line_no,
                        line=line,
                    )
                )
    return counts


def direct_child_dirs(root: Path, parent: Path, reference_patterns: tuple[str, ...] | None = None) -> tuple[Path, ...]:
    full_parent = root / parent
    if not full_parent.is_dir():
        return ()
    children: list[Path] = []
    for child in sorted(full_parent.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            child_rel = rel(child, root)
            if not is_reference_repo_path(child_rel, reference_patterns):
                children.append(child_rel)
    return tuple(children)


def as_path(value: Any) -> Path | None:
    return Path(value) if isinstance(value, str) and value else None


def strings(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str)}


def collect_targets(
    root: Path,
    allowlist: dict[str, Any],
    problems: list[Problem],
    reference_patterns: tuple[str, ...] | None = None,
) -> tuple[TargetTopic, ...]:
    targets: list[TargetTopic] = []
    target_roots = allowlist.get("target_roots")
    if not isinstance(target_roots, list):
        problems.append(Problem(ALLOWLIST, "target_roots must be a list"))
        return ()

    for index, rule in enumerate(target_roots):
        if not isinstance(rule, dict):
            problems.append(Problem(ALLOWLIST, f"target_roots[{index}] must be an object"))
            continue
        root_path = as_path(rule.get("path"))
        entrypoint = as_path(rule.get("entrypoint"))
        status = rule.get("status")
        if root_path is None or entrypoint is None or not isinstance(status, str):
            problems.append(Problem(ALLOWLIST, f"target_roots[{index}] requires path, status, and entrypoint"))
            continue
        if status not in VALID_TARGET_STATUSES:
            problems.append(Problem(ALLOWLIST, f"target_roots[{index}] has invalid status {status!r}"))
            continue
        if not (root / root_path).is_dir():
            problems.append(Problem(root_path, "target root is missing"))
            continue
        if not (root / entrypoint).is_file():
            problems.append(Problem(entrypoint, "target root entrypoint is missing"))

        excluded = strings(rule.get("excluded_topic_dirs"))
        allowed_non_topic = strings(rule.get("allowed_non_topic_dirs"))
        for child in direct_child_dirs(root, root_path, reference_patterns):
            name = child.name
            if name in excluded or name in allowed_non_topic:
                continue
            targets.append(TargetTopic(path=child, status=status, entrypoint=entrypoint))
    return tuple(sorted(targets, key=lambda item: item.path.as_posix()))


def collect_declared_roots(allowlist: dict[str, Any], key: str, problems: list[Problem]) -> tuple[Path, ...]:
    values = allowlist.get(key, [])
    if not isinstance(values, list):
        problems.append(Problem(ALLOWLIST, f"{key} must be a list"))
        return ()
    roots: list[Path] = []
    for index, item in enumerate(values):
        if isinstance(item, str):
            roots.append(Path(item))
        elif isinstance(item, dict) and isinstance(item.get("path"), str):
            roots.append(Path(item["path"]))
        else:
            problems.append(Problem(ALLOWLIST, f"{key}[{index}] must be a path string or object with path"))
    return tuple(roots)


def collect_target_overrides(allowlist: dict[str, Any], problems: list[Problem]) -> dict[Path, dict[str, Any]]:
    raw_overrides = allowlist.get("target_topic_overrides", [])
    if not isinstance(raw_overrides, list):
        problems.append(Problem(ALLOWLIST, "target_topic_overrides must be a list when present"))
        return {}
    overrides: dict[Path, dict[str, Any]] = {}
    for index, item in enumerate(raw_overrides):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            problems.append(Problem(ALLOWLIST, f"target_topic_overrides[{index}] must be an object with path"))
            continue
        path = Path(item["path"])
        review_status = item.get("review_status")
        if review_status is not None and review_status not in VALID_REVIEW_STATUSES:
            problems.append(
                Problem(ALLOWLIST, f"target_topic_overrides[{index}] has invalid review_status {review_status!r}")
            )
            continue
        overrides[path] = item
    return overrides


def index_mentions_topic(
    root: Path,
    entrypoint: Path,
    topic: Path,
    problems: list[Problem],
    reference_patterns: tuple[str, ...] | None = None,
) -> bool:
    text = read_text(root, entrypoint, problems, reference_patterns)
    topic_name = topic.name
    if topic_name in text:
        return True
    for _, _, raw_target in LINK_RE.findall(text):
        resolved = resolve_link(root, entrypoint, raw_target, reference_patterns)
        if resolved is not None and (resolved == topic or topic in resolved.parents):
            return True
    return False


def check_target_evidence(
    root: Path,
    target: TargetTopic,
    problems: list[Problem],
    profile: EvidenceProfile,
    reference_patterns: tuple[str, ...] | None = None,
) -> None:
    full = root / target.path
    if not full.is_dir():
        problems.append(Problem(target.path, "target topic directory is missing"))
        return
    topic_files = [
        child
        for child in full.iterdir()
        if child.is_file() and child.suffix.lower() in {".md", ".json", ".yml", ".yaml", ".toml", ".txt"}
    ]
    if not topic_files:
        problems.append(Problem(target.path, "target topic has no local evidence files"))
    if not index_mentions_topic(root, target.entrypoint, target.path, problems, reference_patterns):
        problems.append(Problem(target.entrypoint, f"target root entrypoint does not mention {target.path.name}"))

    if target.status in {"active_current", "closed", "external_blocked"} and not (
        profile.has_code_reference
        or profile.has_script_reference
        or profile.has_test_reference
        or profile.has_gate_reference
    ):
        problems.append(
            Problem(
                target.path,
                "target lacks code/script/test/gate evidence signals; classify as process/evidence or add a verifiable gate",
            )
        )

    if target.status == "external_blocked":
        text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in topic_files)
        entry_text = read_text(root, target.entrypoint, problems, reference_patterns)
        if not profile.has_external_blocker:
            problems.append(Problem(target.path, "external_blocked target lacks external blocker signal"))
        if "external_blocked" not in text and "external_blocked" not in entry_text:
            problems.append(Problem(target.path, "external_blocked target lacks explicit external blocker evidence"))


def profile_files(root: Path, topic: Path, reference_patterns: tuple[str, ...] | None = None) -> tuple[Path, ...]:
    full = root / topic
    if not full.is_dir():
        return ()
    files: list[Path] = []
    for child in sorted(full.rglob("*")):
        if not child.is_file():
            continue
        child_rel = rel(child, root)
        if is_reference_repo_path(child_rel, reference_patterns) or child.suffix.lower() not in PROFILE_SUFFIXES:
            continue
        files.append(child_rel)
    return tuple(files)


def evidence_profile(root: Path, topic: Path, reference_patterns: tuple[str, ...] | None = None) -> EvidenceProfile:
    files = profile_files(root, topic, reference_patterns)
    text_parts: list[str] = []
    for file_path in files:
        try:
            text_parts.append((root / file_path).read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    text = "\n".join(text_parts)
    return EvidenceProfile(
        file_count=len(files),
        has_code_reference=bool(CODE_RE.search(text)),
        has_script_reference=bool(SCRIPT_RE.search(text)),
        has_test_reference=bool(TEST_RE.search(text)),
        has_gate_reference=bool(GATE_RE.search(text)),
        has_external_blocker=bool(EXTERNAL_RE.search(text)),
        sample_files=files[:5],
    )


def profile_gaps(target: TargetTopic, profile: EvidenceProfile) -> tuple[str, ...]:
    if target.review_status_override and target.review_status_override != "needs_update":
        return ()
    gaps: list[str] = []
    if target.review_status_override == "needs_update":
        gaps.append("review_override_needs_update")
    if profile.file_count == 0:
        gaps.append("no_evidence_files")

    if target.status in {"active_current", "closed", "external_blocked"} and not profile.has_code_reference:
        gaps.append("missing_code_reference")

    if target.status in {"active_current", "closed"}:
        if not profile.has_test_reference:
            gaps.append("missing_test_reference")
        if not profile.has_gate_reference:
            gaps.append("missing_gate_reference")

    if target.status == "external_blocked":
        if not profile.has_external_blocker:
            gaps.append("missing_external_blocker")
        if not (profile.has_test_reference or profile.has_gate_reference):
            gaps.append("missing_repo_local_test_or_gate")

    return tuple(gaps)


def target_review_status(target: TargetTopic, profile: EvidenceProfile) -> str:
    if target.review_status_override:
        return target.review_status_override
    if target.status == "retired":
        return "retired"
    gaps = profile_gaps(target, profile)
    if gaps:
        return "needs_update"
    return target.status


def check_non_targets_exist(root: Path, roots: tuple[Path, ...], problems: list[Problem]) -> None:
    for path in roots:
        if not (root / path).exists():
            problems.append(Problem(path, "declared non-target/evidence root is missing"))


def check(root: Path, allowlist_path: Path = ALLOWLIST) -> Result:
    problems: list[Problem] = []
    allowlist = read_json(root, allowlist_path, problems)
    reference_patterns = reference_excludes(allowlist)
    status_counts = parse_current_status_counts(root, problems, reference_patterns)
    target_overrides = collect_target_overrides(allowlist, problems)
    targets = collect_targets(root, allowlist, problems, reference_patterns)
    if target_overrides:
        targets = tuple(
            TargetTopic(
                path=target.path,
                status=target.status,
                entrypoint=target.entrypoint,
                role=str(target_overrides.get(target.path, {}).get("role", target.role)),
                review_status_override=target_overrides.get(target.path, {}).get("review_status"),
                review_reason=target_overrides.get(target.path, {}).get("reason"),
            )
            for target in targets
        )
        target_paths = {target.path for target in targets}
        for override_path in target_overrides:
            if override_path not in target_paths:
                problems.append(Problem(override_path, "target_topic_override path does not match any target topic"))
    target_profiles = {target.path: evidence_profile(root, target.path, reference_patterns) for target in targets}
    non_target_roots = collect_declared_roots(allowlist, "non_target_roots", problems)
    evidence_roots = collect_declared_roots(allowlist, "evidence_roots", problems)

    for status in PRIMARY_STATUSES:
        if status not in status_counts:
            problems.append(Problem(CURRENT_DEV_INDEX, f"remaining status distribution missing {status} count"))

    active_current_targets = tuple(target for target in targets if target.status == "active_current")
    if status_counts.get("partial") != len(active_current_targets):
        problems.append(
            Problem(
                CURRENT_DEV_INDEX,
                f"partial count {status_counts.get('partial')} does not match active_current target count {len(active_current_targets)}",
            )
        )

    current_partial = status_counts.get("partial")
    for count in status_counts_in_active_navigation(root, problems, reference_patterns):
        if count.status != "partial" or current_partial is None:
            continue
        if count.count != current_partial and not historical_count_line(count.line):
            problems.append(
                Problem(
                    count.path,
                    f"active navigation stale partial count {count.count}; current distribution is {current_partial}",
                    count.line_no,
                )
            )

    seen: set[Path] = set()
    for target in targets:
        if target.path in seen:
            problems.append(Problem(target.path, "duplicate target topic in allowlist expansion"))
        seen.add(target.path)
        check_target_evidence(root, target, problems, target_profiles[target.path], reference_patterns)

    check_non_targets_exist(root, non_target_roots, problems)
    check_non_targets_exist(root, evidence_roots, problems)

    return Result(
        status_counts=status_counts,
        targets=targets,
        target_profiles=target_profiles,
        non_target_roots=non_target_roots,
        evidence_roots=evidence_roots,
        active_navigation=ACTIVE_NAVIGATION,
        problems=tuple(problems),
    )


def result_json(result: Result) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    review_status_counts: dict[str, int] = {}
    for target in result.targets:
        status_counts[target.status] = status_counts.get(target.status, 0) + 1
        profile = result.target_profiles[target.path]
        review_status = target_review_status(target, profile)
        review_status_counts[review_status] = review_status_counts.get(review_status, 0) + 1
    status_summary = {
        "unsealed_count": sum(result.status_counts.get(status, 0) for status in PRIMARY_STATUSES),
        "sealed_count": review_status_counts.get("closed", 0) + review_status_counts.get("external_blocked", 0),
        "outdated_count": review_status_counts.get("retired", 0),
        "needs_update_count": review_status_counts.get("needs_update", 0),
        "external_blocked_count": review_status_counts.get("external_blocked", 0),
    }
    return {
        "status": "passed" if result.ok else "failed",
        "contract_version": "development-plans-target-topic-matrix.v1",
        "state_schema_version": 2,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "current_dev_counts": result.status_counts,
        "target_status_counts": status_counts,
        "target_review_status_counts": review_status_counts,
        "status_summary": status_summary,
        "status_mapping_rules": {
            "unsealed_count": "sum(current_dev_counts.partial, current_dev_counts.not_closed, current_dev_counts.no_closure_claim)",
            "sealed_count": "target_review_status_counts.closed + target_review_status_counts.external_blocked",
            "outdated_count": "target_review_status_counts.retired",
            "needs_update_count": "target_review_status_counts.needs_update",
            "external_blocked_count": "target_review_status_counts.external_blocked; repo-local sealed but external evidence still required",
        },
        "targets": [
            {
                "path": target.path.as_posix(),
                "status": target.status,
                "entrypoint": target.entrypoint.as_posix(),
                "role": target.role,
                "review_status_override": target.review_status_override,
                "review_reason": target.review_reason,
            }
            for target in result.targets
        ],
        "target_profiles": [
            {
                "path": target.path.as_posix(),
                "status": target.status,
                "role": target.role,
                "file_count": result.target_profiles[target.path].file_count,
                "has_code_reference": result.target_profiles[target.path].has_code_reference,
                "has_script_reference": result.target_profiles[target.path].has_script_reference,
                "has_test_reference": result.target_profiles[target.path].has_test_reference,
                "has_gate_reference": result.target_profiles[target.path].has_gate_reference,
                "has_external_blocker": result.target_profiles[target.path].has_external_blocker,
                "target_review_status": target_review_status(target, result.target_profiles[target.path]),
                "review_reason": target.review_reason,
                "profile_gaps": list(profile_gaps(target, result.target_profiles[target.path])),
                "sample_files": [path.as_posix() for path in result.target_profiles[target.path].sample_files],
            }
            for target in result.targets
        ],
        "non_target_roots": [path.as_posix() for path in result.non_target_roots],
        "evidence_roots": [path.as_posix() for path in result.evidence_roots],
        "active_navigation": [path.as_posix() for path in result.active_navigation],
        "problems": [
            {"path": problem.path.as_posix(), "line": problem.line_no, "message": problem.message}
            for problem in result.problems
        ],
    }


def print_result(result: Result, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result_json(result), ensure_ascii=False, indent=2))
        return
    current_counts = ",".join(f"{status}:{result.status_counts.get(status, 'missing')}" for status in PRIMARY_STATUSES)
    json_result = result_json(result)
    target_counts = json_result["target_status_counts"]
    review_counts = json_result["target_review_status_counts"]
    target_summary = ",".join(f"{status}:{target_counts.get(status, 0)}" for status in sorted(VALID_TARGET_STATUSES))
    review_summary = ",".join(
        f"{status}:{review_counts.get(status, 0)}" for status in sorted(VALID_REVIEW_STATUSES)
    )
    if result.ok:
        print(
            "OK development_plans_target_topic_matrix=passed "
            f"current={current_counts} targets={target_summary} "
            f"reviews={review_summary} non_target_roots={len(result.non_target_roots)} "
            f"evidence_roots={len(result.evidence_roots)}"
        )
        return
    print(
        "FAIL development_plans_target_topic_matrix=failed "
        f"current={current_counts} targets={target_summary} problems={len(result.problems)}",
        file=sys.stderr,
    )
    for problem in result.problems:
        suffix = f":{problem.line_no}" if problem.line_no else ""
        print(f"FAIL {problem.path.as_posix()}{suffix}: {problem.message}", file=sys.stderr)


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    result = check(root, Path(args.allowlist))
    print_result(result, as_json=args.json)
    if args.fail_on_needs_update and result.ok:
        review_counts = result_json(result)["target_review_status_counts"]
        if review_counts.get("needs_update", 0):
            return 1
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
