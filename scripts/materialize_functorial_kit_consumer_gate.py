#!/usr/bin/env python3
"""Materialize an offline, patched functorial-kit consumer-gate test tool."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tools/functorial-kit/consumer-gate.manifest.json"
EXPECTED_ARTIFACT = "functorial-kit-consumer-gate-replay"
EXPECTED_ROLE = "test_tool_only"
EXPECTED_TARGETS = frozenset(
    {
        "python/functorial_kit/arch/gates.py",
        "python/functorial_kit/arch/scan.py",
        "python/tests/test_arch.py",
    }
)
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OBJECT = re.compile(r"[0-9a-f]{40}\Z")


class MaterializationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_text(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repo), *args),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit={result.returncode}"
        raise MaterializationError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def _git_archive(repo: Path, commit: str) -> bytes:
    result = subprocess.run(
        ("git", "-C", str(repo), "archive", "--format=tar", commit),
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise MaterializationError(f"git archive {commit} failed: {detail}")
    return result.stdout


def _safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if value.startswith("/") or path.is_absolute() or not path.parts:
        raise MaterializationError(f"absolute or empty path is forbidden: {value!r}")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise MaterializationError(f"path escape is forbidden: {value!r}")
    if "\\" in value:
        raise MaterializationError(f"backslash in repository path is forbidden: {value!r}")
    return path


def _safe_output_path(output: Path) -> Path:
    if output.exists() or output.is_symlink():
        raise MaterializationError(f"output must not already exist: {output}")
    parent = output.parent
    if not parent.is_dir():
        raise MaterializationError(f"output parent must be an existing directory: {parent}")
    if output.name in {"", ".", ".."}:
        raise MaterializationError(f"invalid output path: {output}")
    resolved_parent = parent.resolve(strict=True)
    return resolved_parent / output.name


def _patch_targets(patch_text: str) -> tuple[str, ...]:
    targets: list[str] = []
    for line in patch_text.splitlines():
        if not line.startswith("+++ b/"):
            continue
        target = line[len("+++ b/") :]
        _safe_relative_path(target)
        targets.append(target)
    return tuple(targets)


def _validate_digest_map(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != EXPECTED_TARGETS:
        raise MaterializationError(f"{field} must contain exactly {sorted(EXPECTED_TARGETS)}")
    for target, digest in value.items():
        if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
            raise MaterializationError(f"{field}[{target}] must be a lowercase sha256 digest")
    return value


def _all_authority_false(value: Any) -> bool:
    if isinstance(value, bool):
        return value is False
    if isinstance(value, dict):
        return bool(value) and all(_all_authority_false(item) for item in value.values())
    if isinstance(value, list):
        return bool(value) and all(_all_authority_false(item) for item in value)
    return False


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MaterializationError(f"cannot read manifest {path}: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise MaterializationError("manifest schema_version must be 1")
    if payload.get("artifact") != EXPECTED_ARTIFACT:
        raise MaterializationError(f"manifest artifact must be {EXPECTED_ARTIFACT!r}")
    if payload.get("role") != EXPECTED_ROLE:
        raise MaterializationError(f"manifest role must be {EXPECTED_ROLE!r}")
    if not _all_authority_false(payload.get("authority")):
        raise MaterializationError("every manifest authority value must be false")

    base = payload.get("base")
    if not isinstance(base, dict):
        raise MaterializationError("manifest.base must be an object")
    commit = base.get("git_commit")
    tree = base.get("git_tree")
    if not isinstance(commit, str) or _GIT_OBJECT.fullmatch(commit) is None:
        raise MaterializationError("manifest.base.git_commit must be a 40-hex git commit")
    if not isinstance(tree, str) or _GIT_OBJECT.fullmatch(tree) is None:
        raise MaterializationError("manifest.base.git_tree must be a 40-hex git tree")
    _validate_digest_map(base.get("targets"), "manifest.base.targets")
    _validate_digest_map(payload.get("patched_targets"), "manifest.patched_targets")

    patch = payload.get("patch")
    if not isinstance(patch, dict):
        raise MaterializationError("manifest.patch must be an object")
    patch_path = patch.get("path")
    if not isinstance(patch_path, str):
        raise MaterializationError("manifest.patch.path must be a string")
    _safe_relative_path(patch_path)
    if patch_path != "tools/functorial-kit/consumer-gate.patch":
        raise MaterializationError("manifest.patch.path is not the consumer-gate patch")
    if not isinstance(patch.get("sha256"), str) or _HEX64.fullmatch(patch["sha256"]) is None:
        raise MaterializationError("manifest.patch.sha256 must be a lowercase sha256 digest")

    runtime = payload.get("runtime_identity")
    if not isinstance(runtime, dict):
        raise MaterializationError("manifest.runtime_identity must be separate and present")
    if runtime.get("consumer_gate_materialization") != "base_git_commit_plus_sha256_verified_patch":
        raise MaterializationError("consumer-gate runtime identity is invalid")
    declared_dependency = runtime.get("pyproject_runtime_dependency")
    if not isinstance(declared_dependency, str) or declared_dependency != (
        f"functorial-kit @ git+https://github.com/123rrr4tttt/functorial-kit.git@{commit}#subdirectory=python"
    ):
        raise MaterializationError("manifest runtime dependency does not match the base commit")
    if runtime.get("pyproject_runtime_pin_modified") is not False:
        raise MaterializationError("manifest claims the pyproject runtime pin was modified")
    try:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    except OSError as error:
        raise MaterializationError(f"cannot verify pyproject runtime pin: {error}") from error
    if declared_dependency not in pyproject:
        raise MaterializationError("pyproject runtime pin does not match manifest.runtime_identity")
    return payload


def _extract_archive(archive: bytes, destination: Path) -> None:
    destination_root = destination.resolve(strict=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as archive_file:
            members = archive_file.getmembers()
            for member in members:
                relative = _safe_relative_path(member.name)
                target = destination.joinpath(*relative.parts)
                resolved_parent = target.parent.resolve(strict=False)
                if resolved_parent != destination_root and destination_root not in resolved_parent.parents:
                    raise MaterializationError(f"archive path escapes output: {member.name!r}")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise MaterializationError(f"archive member is not a regular file: {member.name!r}")
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = archive_file.extractfile(member)
                if stream is None:
                    raise MaterializationError(f"cannot extract archive member: {member.name!r}")
                with target.open("xb") as output_stream:
                    while True:
                        chunk = stream.read(1024 * 1024)
                        if not chunk:
                            break
                        output_stream.write(chunk)
                mode = 0o755 if member.mode & 0o111 else 0o644
                os.chmod(target, mode)
    except (tarfile.TarError, OSError) as error:
        raise MaterializationError(f"unsafe or invalid git archive: {error}") from error


def _verify_files(root: Path, digests: dict[str, str], phase: str) -> None:
    for target, expected in sorted(digests.items()):
        path = root.joinpath(*PurePosixPath(target).parts)
        if not path.is_file():
            raise MaterializationError(f"{phase} target is absent: {target}")
        observed = _sha256(path)
        if observed != expected:
            raise MaterializationError(f"{phase} digest mismatch for {target}: expected={expected} observed={observed}")


def materialize(kit_repo: Path, output: Path, manifest_path: Path = MANIFEST_PATH) -> dict[str, Any]:
    destination = _safe_output_path(output)
    manifest = load_manifest(manifest_path)
    patch_path = ROOT / manifest["patch"]["path"]
    if not patch_path.is_file():
        raise MaterializationError(f"patch is absent: {patch_path}")
    patch_digest = _sha256(patch_path)
    if patch_digest != manifest["patch"]["sha256"]:
        raise MaterializationError(f"patch digest mismatch: expected={manifest['patch']['sha256']} observed={patch_digest}")
    patch_text = patch_path.read_text(encoding="utf-8")
    if set(_patch_targets(patch_text)) != EXPECTED_TARGETS:
        raise MaterializationError("patch targets must exactly match the consumer-gate target set")

    repo = kit_repo.resolve(strict=True)
    if not repo.is_dir():
        raise MaterializationError(f"kit repository is not a directory: {repo}")
    base_commit = manifest["base"]["git_commit"]
    observed_commit = _git_text(repo, "rev-parse", "--verify", f"{base_commit}^{{commit}}")
    if observed_commit != base_commit:
        raise MaterializationError(f"wrong base commit: expected={base_commit} observed={observed_commit}")
    observed_tree = _git_text(repo, "rev-parse", f"{base_commit}^{{tree}}")
    if observed_tree != manifest["base"]["git_tree"]:
        raise MaterializationError(f"wrong base tree: expected={manifest['base']['git_tree']} observed={observed_tree}")

    with tempfile.TemporaryDirectory(prefix=f".{destination.name}.materialize-", dir=destination.parent) as temporary:
        staging = Path(temporary).resolve(strict=True)
        _extract_archive(_git_archive(repo, base_commit), staging)
        _verify_files(staging, manifest["base"]["targets"], "base")
        check = subprocess.run(
            ("git", "-C", str(staging), "apply", "--check", "--whitespace=nowarn", str(patch_path)),
            check=False,
            capture_output=True,
            text=True,
        )
        if check.returncode != 0:
            detail = check.stderr.strip() or check.stdout.strip()
            raise MaterializationError(f"patch does not apply cleanly: {detail}")
        applied = subprocess.run(
            ("git", "-C", str(staging), "apply", "--whitespace=nowarn", str(patch_path)),
            check=False,
            capture_output=True,
            text=True,
        )
        if applied.returncode != 0:
            detail = applied.stderr.strip() or applied.stdout.strip()
            raise MaterializationError(f"patch application failed: {detail}")
        _verify_files(staging, manifest["patched_targets"], "patched")
        os.rename(staging, destination)
    return {
        "output": str(destination),
        "base_commit": base_commit,
        "base_tree": observed_tree,
        "patch_sha256": patch_digest,
        "role": manifest["role"],
        "authority": manifest["authority"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit-repo", required=True, type=Path, help="offline git repository containing the base commit")
    parser.add_argument("--output", required=True, type=Path, help="create-only output directory")
    args = parser.parse_args(argv)
    try:
        result = materialize(args.kit_repo, args.output)
    except MaterializationError as error:
        print(f"materialization failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
