#!/usr/bin/env python3
# ruff: noqa: TRY003
"""Check whether a checkout is an exact formal-release candidate."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.formal_release.model import (  # noqa: E402
    CreateOnlyWriteError,
    DirectoryIdentity,
    Finding,
    PreflightReport,
    directory_identity,
    write_create_only_bytes,
)


CHECKER = "candidate-identity"
VALID_CANDIDATE_STRATEGIES = (
    "REMEDIATION_INCLUSIVE_RELEASE",
    "PRODUCTION_MAIN_STABILIZATION",
)
HIDDEN_INDEX_FLAG_FLAGS = {
    "h": ("assume-unchanged",),
    "S": ("skip-worktree",),
    "s": ("assume-unchanged", "skip-worktree"),
}
class CandidateIdentityOutputError(RuntimeError):
    """Raised when a report destination is unsafe or cannot be created."""


def _git_env() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    return env


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", type=Path, help="Repository root to inspect.")
    parser.add_argument("--expected-commit", required=True, help="Expected candidate commit hash.")
    parser.add_argument("--expected-tree", required=True, help="Expected candidate tree hash.")
    parser.add_argument(
        "--candidate-strategy",
        required=True,
        help="Candidate strategy to validate.",
    )
    parser.add_argument("--output", type=Path, help="Optional path to write the preflight JSON report.")
    return parser.parse_args(argv)


def _git_output(repo_root: Path, *args: str) -> tuple[str | None, str | None]:
    completed = subprocess.run(
        ("git", "-c", "core.fsmonitor=false", "-C", str(repo_root), *args),
        check=False,
        capture_output=True,
        text=True,
        env=_git_env(),
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip()
        if not stderr:
            stderr = f"git {' '.join(args)} failed with exit code {completed.returncode}"
        return None, stderr
    return completed.stdout, None


def _read_git_snapshot(repo_root: Path) -> tuple[str | None, str | None, tuple[str, ...], str | None]:
    commit_output, error = _git_output(repo_root, "rev-parse", "HEAD")
    if error is not None:
        return None, None, (), f"git rev-parse HEAD: {error}"

    tree_output, error = _git_output(repo_root, "rev-parse", "HEAD^{tree}")
    if error is not None:
        return commit_output.strip(), None, (), f"git rev-parse HEAD^{{tree}}: {error}"

    status_output, error = _git_output(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
    if error is not None:
        return commit_output.strip(), tree_output.strip(), (), f"git status --porcelain=v1: {error}"

    status_lines = tuple(line for line in status_output.splitlines() if line.strip())
    return commit_output.strip(), tree_output.strip(), status_lines, None


def _read_hidden_index_flags(repo_root: Path) -> tuple[tuple[str, str, str], ...] | None:
    """Read assume-unchanged and skip-worktree entries from the git index."""
    output, error = _git_output(repo_root, "ls-files", "-t", "-v", "-z")
    if error is not None:
        return None

    entries = []
    for record in output.split("\0"):
        if not record:
            continue
        if len(record) < 3 or record[1] != " ":
            return None
        tag = record[0]
        if tag in HIDDEN_INDEX_FLAG_FLAGS:
            flags = HIDDEN_INDEX_FLAG_FLAGS[tag]
            entries.append((tag, "+".join(flags), record[2:]))
    return tuple(entries)


def _candidate_strategy_finding(candidate_strategy: str) -> Finding:
    strategy = candidate_strategy.strip()
    if strategy in VALID_CANDIDATE_STRATEGIES:
        return Finding(
            "candidate.strategy",
            "PASS",
            "candidate strategy is supported",
            (f"strategy={strategy}",),
        )
    return Finding(
        "candidate.strategy",
        "FAIL",
        "unsupported candidate strategy",
        (
            f"strategy={strategy}",
            "allowed=REMEDIATION_INCLUSIVE_RELEASE,PRODUCTION_MAIN_STABILIZATION",
        ),
    )


def _equality_finding(
    *,
    check_id: str,
    label: str,
    expected: str,
    observed: str | None,
) -> Finding:
    if observed == expected:
        return Finding(
            check_id,
            "PASS",
            f"{label} matches expected value",
            (f"expected={expected}", f"observed={observed}"),
        )
    return Finding(
        check_id,
        "FAIL",
        f"{label} does not match expected value",
        (f"expected={expected}", f"observed={observed or '<unavailable>'}"),
    )


def _porcelain_finding(
    *,
    check_id: str,
    label: str,
    lines: tuple[str, ...],
) -> Finding:
    if not lines:
        return Finding(check_id, "PASS", f"{label} are clean", ("count=0",))
    return Finding(
        check_id,
        "FAIL",
        f"{label} are dirty",
        (f"count={len(lines)}", *(f"porcelain={line}" for line in lines)),
    )


def _tracked_dirty_finding(
    *,
    porcelain_lines: tuple[str, ...],
    hidden_flags: tuple[tuple[str, str, str], ...],
) -> Finding:
    if not porcelain_lines and not hidden_flags:
        return Finding("candidate.dirty_tracked", "PASS", "tracked files are clean", ("count=0",))

    evidence = [f"count={len(porcelain_lines)}", f"hidden_flag_count={len(hidden_flags)}"]
    evidence.extend(f"porcelain={line}" for line in porcelain_lines)
    evidence.extend(f"hidden_flag={tag} {kind} {path}" for tag, kind, path in hidden_flags)
    return Finding(
        "candidate.dirty_tracked",
        "FAIL",
        "tracked files are dirty",
        tuple(evidence),
    )


def evaluate_candidate_identity(
    *,
    repo_root: Path,
    expected_commit: str,
    expected_tree: str,
    candidate_strategy: str,
) -> PreflightReport:
    findings = [_candidate_strategy_finding(candidate_strategy)]

    actual_commit, actual_tree, status_lines, git_error = _read_git_snapshot(repo_root)
    if git_error is not None:
        findings.append(
            Finding(
                "candidate.repo",
                "BLOCKED",
                "git metadata could not be inspected",
                (f"error={git_error}",),
            )
        )
        return PreflightReport(checker=CHECKER, findings=tuple(findings))

    hidden_flags = _read_hidden_index_flags(repo_root)
    if hidden_flags is None:
        findings.append(
            Finding(
                "candidate.repo",
                "BLOCKED",
                "git metadata could not be inspected",
                ("error=git ls-files -t -v -z: invalid or unavailable output",),
            )
        )
        return PreflightReport(checker=CHECKER, findings=tuple(findings))

    findings.append(
        _equality_finding(
            check_id="candidate.commit",
            label="HEAD commit",
            expected=expected_commit.strip(),
            observed=actual_commit,
        )
    )
    findings.append(
        _equality_finding(
            check_id="candidate.tree",
            label="HEAD tree",
            expected=expected_tree.strip(),
            observed=actual_tree,
        )
    )

    tracked_dirty = tuple(line for line in status_lines if not line.startswith("??"))
    untracked = tuple(line for line in status_lines if line.startswith("??"))
    findings.append(
        _tracked_dirty_finding(
            porcelain_lines=tracked_dirty,
            hidden_flags=hidden_flags,
        )
    )
    findings.append(
        _porcelain_finding(
            check_id="candidate.untracked",
            label="untracked files",
            lines=untracked,
        )
    )
    return PreflightReport(checker=CHECKER, findings=tuple(findings))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_report_output(path: Path, repo_root: Path) -> tuple[Path, DirectoryIdentity]:
    """Validate a create-only destination before any report is evaluated or written."""
    destination = Path(os.path.abspath(os.fspath(path)))
    requested_root = repo_root.resolve(strict=True)
    top_level, error = _git_output(requested_root, "rev-parse", "--show-toplevel")
    if error is not None or top_level is None:
        raise CandidateIdentityOutputError(
            f"candidate repository top-level is unavailable: {error or '<empty>'}"
        )
    candidate_root = Path(top_level.strip()).resolve(strict=True)
    candidate_identity = directory_identity(candidate_root)
    resolved_destination = destination.resolve(strict=False)

    if _is_within(resolved_destination, candidate_root):
        raise CandidateIdentityOutputError(
            f"output must be outside candidate repository: {candidate_root}"
        )

    for ancestor in destination.parents:
        if os.path.islink(ancestor):
            raise CandidateIdentityOutputError(
                f"output ancestor must not be a symbolic link: {ancestor}"
            )
        if not ancestor.is_dir():
            raise CandidateIdentityOutputError(
                f"output ancestor is not a directory: {ancestor}"
            )

    try:
        os.lstat(destination)
    except FileNotFoundError:
        return destination, candidate_identity
    raise CandidateIdentityOutputError(f"create-only target already exists: {destination}")


def validate_report_output(path: Path, repo_root: Path) -> Path:
    destination, _ = _validate_report_output(path, repo_root)
    return destination


def write_report(path: Path, report: PreflightReport, repo_root: Path) -> None:
    destination, candidate_identity = _validate_report_output(path, repo_root)
    try:
        write_create_only_bytes(
            destination,
            report.to_json().encode("utf-8"),
            (candidate_identity,),
        )
    except CreateOnlyWriteError as exc:
        raise CandidateIdentityOutputError(
            str(exc)
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.output is not None:
        try:
            validate_report_output(args.output, args.repo_root)
        except (CandidateIdentityOutputError, OSError) as exc:
            print(f"candidate-identity output error: {exc}", file=sys.stderr)
            return 2

    report = evaluate_candidate_identity(
        repo_root=args.repo_root,
        expected_commit=args.expected_commit,
        expected_tree=args.expected_tree,
        candidate_strategy=args.candidate_strategy,
    )
    if args.output is not None:
        try:
            write_report(args.output, report, args.repo_root)
        except (CandidateIdentityOutputError, OSError) as exc:
            print(f"candidate-identity output error: {exc}", file=sys.stderr)
            return 2
    sys.stdout.write(report.to_json())
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
