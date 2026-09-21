#!/usr/bin/env python3
# ruff: noqa: TRY003
"""Fail-closed audit adapter for MRW's single pinned functorial-kit dependency."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement


EXPECTED_NAME = "functorial-kit"
EXPECTED_VERSION = "0.1.0"
EXPECTED_COMMIT = "785ff25e201c9eae84c862e68e786bc975e7a800"
EXPECTED_REPOSITORY_TREE = "40a8019815040ff00c0ce61c0cdca30ac004ec7e"
EXPECTED_PYTHON_SUBTREE = "a3d291c03826e8be781aac866797cc98cb744385"
EXPECTED_GIT_URL = "https://github.com/123rrr4tttt/functorial-kit.git"
EXPECTED_SUBDIRECTORY = "python"
EXPECTED_REQUIREMENT = (
    f"{EXPECTED_NAME} @ git+{EXPECTED_GIT_URL}@{EXPECTED_COMMIT}"
    f"#subdirectory={EXPECTED_SUBDIRECTORY}"
)
RAW_URL_PATTERN = re.compile(r"^(?:git|hg|svn|bzr)\+|^(?:https?|file)://", re.IGNORECASE)


class AuditContractError(RuntimeError):
    """Raised when the narrow dependency-audit contract cannot be satisfied."""

    def __init__(self, message: str, *, evidence: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.evidence = evidence


@dataclass(frozen=True)
class InstalledDependency:
    package_root: Path
    direct_url: dict[str, Any]
    declared_requirements: tuple[str, ...]
    active_runtime_requirements: tuple[str, ...]


@dataclass(frozen=True)
class ManifestIdentity:
    path: Path
    commit: str
    repository_tree: str
    runtime_requirement: str
    runtime_pin_modified: bool


@dataclass(frozen=True)
class SourceIdentity:
    checkout: Path
    origin: str
    commit: str
    repository_tree: str
    python_subtree: str
    package_files: tuple[dict[str, Any], ...]
    package_content_digest: str


def _direct_url_dependencies(values: Sequence[str], *, source: str) -> list[str]:
    direct_urls: list[str] = []
    for value in values:
        stripped = value.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("-"):
            raise AuditContractError(f"{source} contains an unsupported source directive: {stripped!r}")
        if RAW_URL_PATTERN.search(stripped):
            raise AuditContractError(f"{source} contains an unnamed direct URL: {stripped!r}")
        try:
            requirement = Requirement(stripped)
        except InvalidRequirement as exc:
            raise AuditContractError(f"{source} contains an invalid requirement: {stripped!r}") from exc
        if requirement.url is not None:
            direct_urls.append(stripped)
    return direct_urls


def classify_declarations(requirements_text: str, pyproject_bytes: bytes) -> str:
    """Validate the two declarations and return the public-PyPI requirements projection."""

    requirement_lines = requirements_text.splitlines(keepends=True)
    backend_direct_urls = _direct_url_dependencies(requirement_lines, source="main/backend/requirements.txt")
    if backend_direct_urls != [EXPECTED_REQUIREMENT]:
        raise AuditContractError(
            "main/backend/requirements.txt must contain exactly one direct URL, the authorized "
            "functorial-kit Git requirement; "
            f"observed={backend_direct_urls!r}"
        )

    try:
        pyproject = tomllib.loads(pyproject_bytes.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise AuditContractError(f"pyproject.toml is not valid UTF-8 TOML: {exc}") from exc
    dependencies = pyproject.get("project", {}).get("dependencies")
    if not isinstance(dependencies, list) or not all(isinstance(value, str) for value in dependencies):
        raise AuditContractError("pyproject.toml project.dependencies must be a string array")
    pyproject_direct_urls = _direct_url_dependencies(
        dependencies, source="pyproject.toml project.dependencies"
    )
    if pyproject_direct_urls != [EXPECTED_REQUIREMENT]:
        raise AuditContractError(
            "pyproject.toml project.dependencies must contain exactly one direct URL, the authorized "
            "functorial-kit Git requirement; "
            f"observed={pyproject_direct_urls!r}"
        )

    public_lines = [line for line in requirement_lines if line.strip() != EXPECTED_REQUIREMENT]
    if len(public_lines) == len(requirement_lines):
        raise AuditContractError("authorized functorial-kit requirement was not removed from the public projection")
    projection = "".join(public_lines)
    remaining_direct_urls = _direct_url_dependencies(
        projection.splitlines(), source="public PyPI requirements projection"
    )
    if remaining_direct_urls:
        raise AuditContractError(
            f"public PyPI projection still contains direct URLs: {remaining_direct_urls!r}"
        )
    backend_public_requirements = {
        str(Requirement(line.strip()))
        for line in public_lines
        if line.strip() and not line.lstrip().startswith("#")
    }
    pyproject_public_requirements = [
        str(Requirement(value)) for value in dependencies if value != EXPECTED_REQUIREMENT
    ]
    additions = [
        requirement
        for requirement in pyproject_public_requirements
        if requirement not in backend_public_requirements
    ]
    if additions:
        if projection and not projection.endswith("\n"):
            projection += "\n"
        projection += "".join(f"{requirement}\n" for requirement in additions)
    return projection


def inspect_consumer_gate_manifest(path: Path) -> ManifestIdentity:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditContractError(f"consumer-gate manifest is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise AuditContractError("consumer-gate manifest root must be an object")
    base = payload.get("base")
    runtime_identity = payload.get("runtime_identity")
    if not isinstance(base, dict) or not isinstance(runtime_identity, dict):
        raise AuditContractError("consumer-gate manifest identity sections must be objects")
    commit = base.get("git_commit")
    repository_tree = base.get("git_tree")
    runtime_requirement = runtime_identity.get("pyproject_runtime_dependency")
    runtime_pin_modified = runtime_identity.get("pyproject_runtime_pin_modified")
    if commit != EXPECTED_COMMIT:
        raise AuditContractError(f"consumer-gate manifest commit mismatch: {commit!r}")
    if repository_tree != EXPECTED_REPOSITORY_TREE:
        raise AuditContractError(f"consumer-gate manifest repository tree mismatch: {repository_tree!r}")
    if runtime_requirement != EXPECTED_REQUIREMENT:
        raise AuditContractError(
            f"consumer-gate manifest runtime requirement mismatch: {runtime_requirement!r}"
        )
    if runtime_pin_modified is not False:
        raise AuditContractError(
            "consumer-gate manifest must record pyproject_runtime_pin_modified=false"
        )
    return ManifestIdentity(
        path=path.resolve(),
        commit=commit,
        repository_tree=repository_tree,
        runtime_requirement=runtime_requirement,
        runtime_pin_modified=runtime_pin_modified,
    )


def _package_file_manifest(files: dict[str, bytes]) -> tuple[tuple[dict[str, Any], ...], str]:
    entries = tuple(
        {"path": path, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
        for path, payload in sorted(files.items())
    )
    aggregate_payload = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return entries, hashlib.sha256(aggregate_payload).hexdigest()


def _run_git(checkout: Path, *arguments: str) -> bytes:
    command = ["git", "-C", str(checkout), *arguments]
    try:
        completed = subprocess.run(command, capture_output=True, check=False)
    except OSError as exc:
        raise AuditContractError(f"could not execute Git for source checkout: {exc}") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise AuditContractError(
            f"Git source checkout inspection failed: command={command!r} "
            f"exit={completed.returncode} stderr={stderr!r}"
        )
    return completed.stdout


def _git_text(checkout: Path, *arguments: str) -> str:
    try:
        return _run_git(checkout, *arguments).decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise AuditContractError(f"Git identity output is not UTF-8: {arguments!r}") from exc


def _canonical_https_git_url(value: str) -> str:
    return value.rstrip("/").removesuffix(".git")


def inspect_source_checkout(checkout: Path) -> SourceIdentity:
    checkout = checkout.resolve()
    if not checkout.is_dir():
        raise AuditContractError(f"functorial-kit source checkout is missing: {checkout}")
    origin = _git_text(checkout, "remote", "get-url", "origin")
    commit = _git_text(checkout, "rev-parse", "HEAD")
    repository_tree = _git_text(checkout, "rev-parse", "HEAD^{tree}")
    python_subtree = _git_text(checkout, "rev-parse", "HEAD:python")
    if _canonical_https_git_url(origin) != _canonical_https_git_url(EXPECTED_GIT_URL):
        raise AuditContractError(f"functorial-kit source origin mismatch: {origin!r}")
    if commit != EXPECTED_COMMIT:
        raise AuditContractError(f"functorial-kit source commit mismatch: {commit!r}")
    if repository_tree != EXPECTED_REPOSITORY_TREE:
        raise AuditContractError(f"functorial-kit source repository tree mismatch: {repository_tree!r}")
    if python_subtree != EXPECTED_PYTHON_SUBTREE:
        raise AuditContractError(f"functorial-kit source python subtree mismatch: {python_subtree!r}")

    raw_entries = _run_git(
        checkout, "ls-tree", "-r", "-z", "HEAD", "--", "python/functorial_kit"
    )
    source_files: dict[str, bytes] = {}
    for raw_entry in raw_entries.split(b"\0"):
        if not raw_entry:
            continue
        try:
            metadata, raw_path = raw_entry.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split()
            source_path = raw_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise AuditContractError("functorial-kit Git tree contains an unparseable entry") from exc
        if object_type != "blob" or mode not in {"100644", "100755"}:
            raise AuditContractError(
                f"functorial-kit package contains a non-ordinary Git entry: {source_path!r}"
            )
        relative_path = source_path.removeprefix("python/")
        if not relative_path.startswith("functorial_kit/"):
            raise AuditContractError(f"functorial-kit source path escaped package root: {source_path!r}")
        source_files[relative_path] = _run_git(checkout, "cat-file", "blob", object_id)
    if not source_files:
        raise AuditContractError("functorial-kit Git object contains no package files")
    package_files, package_content_digest = _package_file_manifest(source_files)
    return SourceIdentity(
        checkout=checkout,
        origin=origin,
        commit=commit,
        repository_tree=repository_tree,
        python_subtree=python_subtree,
        package_files=package_files,
        package_content_digest=package_content_digest,
    )


def inspect_installed_package_files(package_root: Path) -> tuple[tuple[dict[str, Any], ...], str]:
    installed_files: dict[str, bytes] = {}
    for path in sorted(package_root.rglob("*")):
        relative = path.relative_to(package_root)
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise AuditContractError(f"installed functorial-kit contains a symlink: {relative.as_posix()!r}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise AuditContractError(
                f"installed functorial-kit contains a non-ordinary file: {relative.as_posix()!r}"
            )
        installed_files[f"functorial_kit/{relative.as_posix()}"] = path.read_bytes()
    if not installed_files:
        raise AuditContractError("installed functorial-kit contains no package files")
    return _package_file_manifest(installed_files)


def compare_installed_to_source(
    installed_files: tuple[dict[str, Any], ...],
    source_files: tuple[dict[str, Any], ...],
) -> None:
    if installed_files == source_files:
        return
    installed_by_path = {entry["path"]: entry for entry in installed_files}
    source_by_path = {entry["path"]: entry for entry in source_files}
    installed_paths = set(installed_by_path)
    source_paths = set(source_by_path)
    changed = sorted(
        path
        for path in installed_paths & source_paths
        if installed_by_path[path] != source_by_path[path]
    )
    evidence = {
        "missing_installed_paths": sorted(source_paths - installed_paths),
        "extra_installed_paths": sorted(installed_paths - source_paths),
        "changed_paths": changed,
    }
    raise AuditContractError(
        "installed functorial-kit files do not byte-match the fixed Git object",
        evidence={"artifact_comparison": evidence},
    )


def inspect_installed_dependency(distribution: importlib.metadata.Distribution) -> InstalledDependency:
    metadata_name = distribution.metadata.get("Name")
    if metadata_name != EXPECTED_NAME:
        raise AuditContractError(f"installed distribution name mismatch: {metadata_name!r}")
    if distribution.version != EXPECTED_VERSION:
        raise AuditContractError(f"installed distribution version mismatch: {distribution.version!r}")

    direct_url_text = distribution.read_text("direct_url.json")
    if direct_url_text is None:
        raise AuditContractError("installed functorial-kit is missing direct_url.json")
    try:
        direct_url = json.loads(direct_url_text)
    except json.JSONDecodeError as exc:
        raise AuditContractError(f"installed direct_url.json is invalid JSON: {exc}") from exc
    if not isinstance(direct_url, dict):
        raise AuditContractError(
            "installed direct_url.json root must be an object",
            evidence={"installed_direct_url": direct_url},
        )
    vcs_info = direct_url.get("vcs_info")
    expected_vcs = {
        "vcs": "git",
        "commit_id": EXPECTED_COMMIT,
        "requested_revision": EXPECTED_COMMIT,
    }
    if direct_url.get("url") != EXPECTED_GIT_URL:
        raise AuditContractError(
            f"installed direct URL mismatch: {direct_url.get('url')!r}",
            evidence={"installed_direct_url": direct_url},
        )
    if direct_url.get("subdirectory") != EXPECTED_SUBDIRECTORY:
        raise AuditContractError(
            f"installed direct URL subdirectory mismatch: {direct_url.get('subdirectory')!r}",
            evidence={"installed_direct_url": direct_url},
        )
    if not isinstance(vcs_info, dict) or vcs_info != expected_vcs:
        raise AuditContractError(
            f"installed VCS identity mismatch: {vcs_info!r}",
            evidence={"installed_direct_url": direct_url},
        )

    declared_requirements = tuple(distribution.requires or ())
    active_runtime_requirements: list[str] = []
    for raw_requirement in declared_requirements:
        try:
            requirement = Requirement(raw_requirement)
        except InvalidRequirement as exc:
            raise AuditContractError(f"installed distribution has an invalid requirement: {raw_requirement!r}") from exc
        if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
            if requirement.url is not None:
                raise AuditContractError(
                    "functorial-kit has an active runtime direct URL that cannot enter the public "
                    f"PyPI audit projection: {raw_requirement!r}"
                )
            active_runtime_requirements.append(str(requirement))

    package_root = Path(distribution.locate_file("functorial_kit")).resolve()
    if not package_root.is_dir():
        raise AuditContractError(f"installed functorial-kit package root is missing: {package_root}")
    return InstalledDependency(
        package_root=package_root,
        direct_url=direct_url,
        declared_requirements=declared_requirements,
        active_runtime_requirements=tuple(active_runtime_requirements),
    )


def extend_public_projection(
    projection: str, runtime_requirements: Sequence[str]
) -> tuple[str, tuple[str, ...]]:
    existing = {
        str(Requirement(line.strip()))
        for line in projection.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    additions: list[str] = []
    for raw_requirement in runtime_requirements:
        try:
            requirement = Requirement(raw_requirement)
        except InvalidRequirement as exc:
            raise AuditContractError(
                f"functorial-kit runtime requirement cannot be classified: {raw_requirement!r}"
            ) from exc
        if requirement.url is not None:
            raise AuditContractError(
                "functorial-kit runtime direct URL cannot enter the public PyPI audit projection: "
                f"{raw_requirement!r}"
            )
        normalized = str(requirement)
        if normalized not in existing:
            additions.append(normalized)
            existing.add(normalized)
    if not additions:
        return projection, ()
    if projection and not projection.endswith("\n"):
        projection += "\n"
    projection += "".join(f"{requirement}\n" for requirement in additions)
    _direct_url_dependencies(
        projection.splitlines(), source="extended public PyPI requirements projection"
    )
    return projection, tuple(additions)


def run_installed_source_bandit(
    package_root: Path,
    bandit_executable: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    command = [
        bandit_executable,
        "-q",
        "-r",
        str(package_root),
        "--severity-level",
        "high",
        "--confidence-level",
        "high",
        "--format",
        "json",
    ]
    try:
        completed = runner(command, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise AuditContractError(f"could not execute Bandit for installed functorial-kit: {exc}") from exc
    try:
        native_report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AuditContractError(
            "functorial-kit Bandit scan did not emit valid JSON; "
            f"exit={completed.returncode} stderr={completed.stderr.strip()!r}"
        ) from exc
    if not isinstance(native_report, dict):
        raise AuditContractError(
            "functorial-kit Bandit report root must be an object",
            evidence={
                "bandit": {
                    "command": command,
                    "exit_code": completed.returncode,
                    "stderr": completed.stderr,
                    "native_report": native_report,
                }
            },
        )
    result = {
        "command": command,
        "exit_code": completed.returncode,
        "stderr": completed.stderr,
        "native_report": native_report,
    }
    if not isinstance(native_report.get("errors"), list) or not isinstance(
        native_report.get("results"), list
    ):
        raise AuditContractError(
            "functorial-kit Bandit report must contain errors and results arrays",
            evidence={"bandit": result},
        )
    if completed.returncode != 0:
        raise AuditContractError(
            "functorial-kit Bandit high/high scan failed; "
            f"exit={completed.returncode} findings={len(native_report['results'])}",
            evidence={"bandit": result},
        )
    if native_report.get("errors"):
        raise AuditContractError(
            f"functorial-kit Bandit scan reported errors: {native_report['errors']!r}",
            evidence={"bandit": result},
        )
    if native_report.get("results"):
        raise AuditContractError(
            "functorial-kit Bandit scan returned findings despite a zero exit code",
            evidence={"bandit": result},
        )
    return result


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--pyproject", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--public-requirements", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--bandit", default="bandit")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report: dict[str, Any] = {
        "schema": "mrw.functorial-kit-dependency-audit.v1",
        "status": "FAIL",
        "expected_identity": {
            "name": EXPECTED_NAME,
            "version": EXPECTED_VERSION,
            "git_url": EXPECTED_GIT_URL,
            "commit": EXPECTED_COMMIT,
            "repository_tree": EXPECTED_REPOSITORY_TREE,
            "python_subtree": EXPECTED_PYTHON_SUBTREE,
            "subdirectory": EXPECTED_SUBDIRECTORY,
            "requirement": EXPECTED_REQUIREMENT,
        },
        "public_vulnerability_database_coverage": {
            "status": "NOT_COVERED_FOR_GIT_SOURCE",
            "reason": "pip-audit public services identify PyPI name/version, not this Git commit",
            "source_bandit_equivalent_to_public_vulnerability_scan": False,
        },
        "qualification": {
            "scope": "DECLARATION_SOURCE_INSTALLED_ARTIFACT_AND_SAST",
            "public_vulnerability_database_gap": True,
            "equivalent_to_public_vulnerability_database_scan": False,
        },
        "authority": "SCOPED_DEPENDENCY_AUDIT_RECEIPT_NOT_RELEASE_AUTHORITY",
    }
    try:
        requirements_text = args.requirements.read_text(encoding="utf-8")
        pyproject_bytes = args.pyproject.read_bytes()
        public_requirements = classify_declarations(requirements_text, pyproject_bytes)
        manifest = inspect_consumer_gate_manifest(args.manifest)
        source = inspect_source_checkout(args.source_checkout)
        try:
            distribution = importlib.metadata.distribution(EXPECTED_NAME)
        except importlib.metadata.PackageNotFoundError as exc:
            raise AuditContractError("installed functorial-kit distribution was not found") from exc
        installed = inspect_installed_dependency(distribution)
        public_requirements, runtime_projection = extend_public_projection(
            public_requirements, installed.active_runtime_requirements
        )
        installed_files, installed_content_digest = inspect_installed_package_files(
            installed.package_root
        )
        compare_installed_to_source(installed_files, source.package_files)
        bandit_result = run_installed_source_bandit(installed.package_root, args.bandit)

        args.public_requirements.parent.mkdir(parents=True, exist_ok=True)
        args.public_requirements.write_text(public_requirements, encoding="utf-8")
        report.update(
            {
                "status": "SCOPED_PASS_WITH_PUBLIC_VULNERABILITY_DB_GAP",
                "declarations": {
                    "requirements": str(args.requirements),
                    "pyproject": str(args.pyproject),
                    "public_requirements": str(args.public_requirements),
                    "public_requirements_sha256": hashlib.sha256(public_requirements.encode("utf-8")).hexdigest(),
                    "runtime_requirements_added_to_public_projection": list(runtime_projection),
                },
                "consumer_gate_manifest": {
                    "path": str(manifest.path),
                    "base_git_commit": manifest.commit,
                    "base_git_tree": manifest.repository_tree,
                    "runtime_requirement": manifest.runtime_requirement,
                    "runtime_pin_modified": manifest.runtime_pin_modified,
                },
                "source": {
                    "checkout": str(source.checkout),
                    "origin": source.origin,
                    "commit": source.commit,
                    "repository_tree": source.repository_tree,
                    "python_subtree": source.python_subtree,
                    "package_files": list(source.package_files),
                    "package_content_digest": source.package_content_digest,
                },
                "installed": {
                    "package_root": str(installed.package_root),
                    "direct_url": installed.direct_url,
                    "declared_requirements": list(installed.declared_requirements),
                    "active_runtime_requirements": list(installed.active_runtime_requirements),
                    "package_files": list(installed_files),
                    "package_content_digest": installed_content_digest,
                    "byte_matches_fixed_git_object": True,
                },
                "bandit": bandit_result,
            }
        )
    except (AuditContractError, OSError) as exc:
        report["error"] = str(exc)
        if isinstance(exc, AuditContractError) and exc.evidence is not None:
            report["failure_evidence"] = exc.evidence
        _write_json(args.report, report)
        print(json.dumps(report, sort_keys=True))
        return 1

    _write_json(args.report, report)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
