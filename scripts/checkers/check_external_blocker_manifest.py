#!/usr/bin/env python3
"""Check structured evidence contracts for external-blocked dev-plan targets."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEV_PLANS_ROOT = Path("development/latest-dev-docs/development-plans")
DEFAULT_ALLOWLIST = DEV_PLANS_ROOT / "TARGET_TOPIC_ALLOWLIST.json"
DEFAULT_MANIFEST = DEV_PLANS_ROOT / "EXTERNAL_BLOCKER_MANIFEST.v1.json"
MATRIX_SCRIPT = Path(__file__).with_name("check_development_plans_status_matrix.py")

VALID_DEPENDENCY_TYPES = {
    "service",
    "provider",
    "vendor_api",
    "infra",
    "compliance",
    "human_review",
}
VALID_EVIDENCE_REQUIRED = {"probe", "manual_check", "ticket", "log", "run_output", "contract"}
VALID_MODES = {"probe", "manual"}
VALID_EXIT_STATES = {"blocked", "satisfied"}
COMMAND_REF_SUFFIXES = (".py", ".sh", ".js", ".mjs", ".ts", ".tsx")


@dataclass(frozen=True)
class Problem:
    path: Path
    message: str


@dataclass(frozen=True)
class Result:
    manifest_path: Path
    external_targets: tuple[Path, ...]
    manifest_targets: tuple[Path, ...]
    problems: tuple[Problem, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate EXTERNAL_BLOCKER_MANIFEST.v1.json against the target-topic matrix."
    )
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--allowlist",
        default=str(DEFAULT_ALLOWLIST),
        help="Target-topic allowlist path relative to repo root.",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="External blocker manifest path relative to repo root. Defaults to allowlist external_blocker_manifest.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args()


def load_matrix_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_development_plans_status_matrix", MATRIX_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load matrix checker from {MATRIX_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_json(root: Path, relative_path: Path, problems: list[Problem], *, label: str) -> dict[str, Any]:
    path = root / relative_path
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        problems.append(Problem(relative_path, f"{label} is missing"))
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        problems.append(Problem(relative_path, f"{label} JSON parse failed: {exc}"))
        return {}
    if not isinstance(payload, dict):
        problems.append(Problem(relative_path, f"{label} root must be a JSON object"))
        return {}
    return payload


def configured_manifest_path(root: Path, allowlist_path: Path, explicit_manifest: Path | None) -> tuple[Path, list[Problem]]:
    problems: list[Problem] = []
    if explicit_manifest is not None:
        return explicit_manifest, problems

    allowlist = read_json(root, allowlist_path, problems, label="allowlist")
    raw_path = allowlist.get("external_blocker_manifest")
    if raw_path is None:
        return DEFAULT_MANIFEST, problems
    if not isinstance(raw_path, str) or not raw_path:
        problems.append(Problem(allowlist_path, "external_blocker_manifest must be a non-empty string"))
        return DEFAULT_MANIFEST, problems
    return Path(raw_path), problems


def matrix_external_targets(root: Path, allowlist_path: Path, problems: list[Problem]) -> tuple[Path, ...]:
    matrix = load_matrix_module()
    result = matrix.check(root, allowlist_path)
    for problem in result.problems:
        problems.append(Problem(problem.path, f"target matrix problem: {problem.message}"))

    external: list[Path] = []
    for target in result.targets:
        profile = result.target_profiles[target.path]
        review_status = matrix.target_review_status(target, profile)
        if target.status == "external_blocked" or review_status == "external_blocked":
            external.append(target.path)
    return tuple(sorted(external, key=lambda path: path.as_posix()))


def as_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def as_nonempty_string_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(as_nonempty_string(item) for item in value)


def validate_probe_or_manual(entry_path: Path, payload: Any, problems: list[Problem]) -> None:
    if not isinstance(payload, dict):
        problems.append(Problem(entry_path, "probe_or_manual_evidence must be an object"))
        return
    mode = payload.get("mode")
    if mode not in VALID_MODES:
        problems.append(Problem(entry_path, f"probe_or_manual_evidence.mode must be one of {sorted(VALID_MODES)}"))
        return

    if mode == "probe":
        required = ("command", "last_run_at", "result_artifact", "exit_code_expectation", "result_summary")
        for key in required:
            if not as_nonempty_string(payload.get(key)):
                problems.append(Problem(entry_path, f"probe_or_manual_evidence.{key} is required for probe mode"))
        command = payload.get("command", "")
        if as_nonempty_string(command) and not any(
            token in command for token in ("python", "pytest", "bash", "npm", "pnpm", "yarn", "node", "./")
        ):
            problems.append(Problem(entry_path, "probe command must name a runnable local command"))
        return

    required = ("reviewer", "reviewed_at", "artifact")
    for key in required:
        if not as_nonempty_string(payload.get(key)):
            problems.append(Problem(entry_path, f"probe_or_manual_evidence.{key} is required for manual mode"))
    if not as_nonempty_string_list(payload.get("checklist")):
        problems.append(Problem(entry_path, "probe_or_manual_evidence.checklist must be a non-empty string list"))


def validate_exit_criteria(entry_path: Path, payload: Any, problems: list[Problem]) -> None:
    if not isinstance(payload, list) or not payload:
        problems.append(Problem(entry_path, "exit_criteria must be a non-empty list"))
        return
    blocked_count = 0
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            problems.append(Problem(entry_path, f"exit_criteria[{index}] must be an object"))
            continue
        for key in ("id", "state", "evidence", "note"):
            if not as_nonempty_string(item.get(key)):
                problems.append(Problem(entry_path, f"exit_criteria[{index}].{key} is required"))
        state = item.get("state")
        if state not in VALID_EXIT_STATES:
            problems.append(Problem(entry_path, f"exit_criteria[{index}].state must be blocked or satisfied"))
        if state == "blocked":
            blocked_count += 1
    if blocked_count == 0:
        problems.append(Problem(entry_path, "external_blocked manifest entry must retain at least one blocked exit criterion"))


def validate_owner_surface(entry_path: Path, payload: Any, problems: list[Problem]) -> None:
    if not isinstance(payload, dict):
        problems.append(Problem(entry_path, "owner_surface must be an object"))
        return
    if not as_nonempty_string(payload.get("owner")):
        problems.append(Problem(entry_path, "owner_surface.owner is required"))
    if not (as_nonempty_string(payload.get("surface")) or as_nonempty_string(payload.get("contact"))):
        problems.append(Problem(entry_path, "owner_surface requires surface or contact"))


def command_reference_paths(command: str) -> tuple[Path, ...]:
    try:
        parts = shlex.split(command)
    except ValueError:
        return ()
    references: list[Path] = []
    for part in parts:
        if part.startswith("-") or "://" in part:
            continue
        if not part.endswith(COMMAND_REF_SUFFIXES):
            continue
        references.append(Path(part))
    return tuple(references)


def validate_manifest_entry(root: Path, entry: Any, index: int, external_targets: set[Path], problems: list[Problem]) -> Path | None:
    entry_path = Path(f"{DEFAULT_MANIFEST.as_posix()}#targets[{index}]")
    if not isinstance(entry, dict):
        problems.append(Problem(entry_path, "target entry must be an object"))
        return None

    raw_path = entry.get("path")
    if not as_nonempty_string(raw_path):
        problems.append(Problem(entry_path, "path is required"))
        return None
    path = Path(raw_path)
    entry_path = Path(f"{raw_path}#external_blocker_manifest")
    if path not in external_targets:
        problems.append(Problem(entry_path, "manifest path is not an external_blocked review target"))

    dependency_type = entry.get("dependency_type")
    if dependency_type not in VALID_DEPENDENCY_TYPES:
        problems.append(Problem(entry_path, f"dependency_type must be one of {sorted(VALID_DEPENDENCY_TYPES)}"))
    if not as_nonempty_string(entry.get("blocked_on")):
        problems.append(Problem(entry_path, "blocked_on is required"))

    evidence = entry.get("repo_local_evidence")
    if not as_nonempty_string_list(evidence):
        problems.append(Problem(entry_path, "repo_local_evidence must be a non-empty string list"))
    else:
        for raw_evidence in evidence:
            evidence_path = Path(raw_evidence)
            if not (root / evidence_path).is_file():
                problems.append(Problem(entry_path, f"repo_local_evidence file is missing: {raw_evidence}"))

    evidence_required = entry.get("evidence_required")
    if not as_nonempty_string_list(evidence_required):
        problems.append(Problem(entry_path, "evidence_required must be a non-empty string list"))
    else:
        invalid = sorted({item for item in evidence_required if item not in VALID_EVIDENCE_REQUIRED})
        if invalid:
            problems.append(Problem(entry_path, f"evidence_required has invalid values: {invalid}"))

    external_surfaces = entry.get("external_surfaces")
    if external_surfaces is not None and not as_nonempty_string_list(external_surfaces):
        problems.append(Problem(entry_path, "external_surfaces must be a non-empty string list when present"))

    probe_or_manual = entry.get("probe_or_manual_evidence")
    validate_probe_or_manual(entry_path, probe_or_manual, problems)
    if isinstance(probe_or_manual, dict) and probe_or_manual.get("mode") == "probe":
        command = probe_or_manual.get("command")
        if isinstance(command, str):
            for ref_path in command_reference_paths(command):
                candidate = ref_path if ref_path.is_absolute() else root / ref_path
                if not candidate.exists():
                    problems.append(Problem(entry_path, f"probe command references missing local file: {ref_path}"))
    validate_exit_criteria(entry_path, entry.get("exit_criteria"), problems)
    validate_owner_surface(entry_path, entry.get("owner_surface"), problems)
    return path


def validate_manifest(
    root: Path, manifest_path: Path, external_targets: tuple[Path, ...], problems: list[Problem]
) -> tuple[Path, ...]:
    payload = read_json(root, manifest_path, problems, label="external blocker manifest")
    if not payload:
        return ()

    if payload.get("schema") != "external-blocker-manifest/v1":
        problems.append(Problem(manifest_path, "schema must be external-blocker-manifest/v1"))
    if not as_nonempty_string(payload.get("updated")):
        problems.append(Problem(manifest_path, "updated is required"))

    entries = payload.get("targets")
    if not isinstance(entries, list) or not entries:
        problems.append(Problem(manifest_path, "targets must be a non-empty list"))
        return ()

    external_set = set(external_targets)
    manifest_paths: list[Path] = []
    seen: set[Path] = set()
    for index, entry in enumerate(entries):
        path = validate_manifest_entry(root, entry, index, external_set, problems)
        if path is None:
            continue
        if path in seen:
            problems.append(Problem(path, "duplicate manifest entry"))
        seen.add(path)
        manifest_paths.append(path)

    missing = sorted(external_set - seen, key=lambda path: path.as_posix())
    extra = sorted(seen - external_set, key=lambda path: path.as_posix())
    for path in missing:
        problems.append(Problem(path, "external_blocked review target missing from manifest"))
    for path in extra:
        problems.append(Problem(path, "manifest entry does not correspond to current external_blocked target"))
    return tuple(sorted(manifest_paths, key=lambda path: path.as_posix()))


def check(root: Path, allowlist_path: Path = DEFAULT_ALLOWLIST, manifest_path: Path | None = None) -> Result:
    root = root.resolve()
    manifest, problems = configured_manifest_path(root, allowlist_path, manifest_path)
    external_targets = matrix_external_targets(root, allowlist_path, problems)
    manifest_targets = validate_manifest(root, manifest, external_targets, problems)
    return Result(
        manifest_path=manifest,
        external_targets=external_targets,
        manifest_targets=manifest_targets,
        problems=tuple(problems),
    )


def result_json(result: Result) -> dict[str, Any]:
    return {
        "status": "passed" if result.ok else "failed",
        "contract_version": "external-blocker-manifest.v1",
        "manifest_path": result.manifest_path.as_posix(),
        "external_target_count": len(result.external_targets),
        "manifest_target_count": len(result.manifest_targets),
        "external_targets": [path.as_posix() for path in result.external_targets],
        "manifest_targets": [path.as_posix() for path in result.manifest_targets],
        "problems": [
            {"path": problem.path.as_posix(), "message": problem.message}
            for problem in result.problems
        ],
    }


def print_result(result: Result, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result_json(result), ensure_ascii=False, indent=2))
        return
    if result.ok:
        print(
            "OK external_blocker_manifest=passed "
            f"external_targets={len(result.external_targets)} manifest_targets={len(result.manifest_targets)} "
            f"manifest={result.manifest_path.as_posix()}"
        )
        return
    print(
        "FAIL external_blocker_manifest=failed "
        f"external_targets={len(result.external_targets)} manifest_targets={len(result.manifest_targets)} "
        f"problems={len(result.problems)}",
        file=sys.stderr,
    )
    for problem in result.problems:
        print(f"FAIL {problem.path.as_posix()}: {problem.message}", file=sys.stderr)


def main() -> int:
    args = parse_args()
    result = check(
        Path(args.root),
        Path(args.allowlist),
        Path(args.manifest) if args.manifest else None,
    )
    print_result(result, as_json=args.json)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
