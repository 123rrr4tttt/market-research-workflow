"""Exact historical inputs for tests; never publish or rewrite repository evidence."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[4]


@lru_cache(maxsize=None)
def historical_bytes(relative: str, sha256: str) -> bytes:
    """Resolve the claimed bytes, not HEAD as a substitute for their identity."""
    path = REPO / relative
    if path.is_file():
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() == sha256:
            return data
    commits = subprocess.check_output(
        ["git", "log", "--all", "--format=%H", "--", relative], cwd=REPO,
        text=True,
    ).splitlines()
    for commit in commits:
        result = subprocess.run(
            ["git", "show", f"{commit}:{relative}"], cwd=REPO, capture_output=True,
        )
        if result.returncode == 0 and hashlib.sha256(result.stdout).hexdigest() == sha256:
            return result.stdout
    # Exact successor snapshots use a content-addressed filename. Candidate
    # snapshots retain provenance in their candidate reference records below.
    for snapshot in (REPO / "stage1-successor-evidence").glob(
        f"current-byte-remediation-*/bindings/snapshots/{sha256}"
    ):
        data = snapshot.read_bytes()
        if hashlib.sha256(data).hexdigest() == sha256:
            return data
    evidence = REPO / "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind"
    for candidate_path in sorted(evidence.glob("*/candidates/*/candidate.v2.json")):
        candidate = json.loads(candidate_path.read_bytes())
        for group in ("sources", "implementation_bindings", "test_bindings", "rollback_bindings", "tests", "fragments", "manifest"):
            entries = candidate.get(group, [])
            if isinstance(entries, dict): entries = [entries]
            for entry in entries:
                if entry.get("path") != relative or entry.get("file_sha256", entry.get("sha256")) != sha256:
                    continue
                snapshot = candidate_path.parent / entry["snapshot_path"]
                data = snapshot.read_bytes()
                if hashlib.sha256(data).hexdigest() == sha256:
                    return data
    raise AssertionError(f"historical byte gap: {relative} sha256={sha256}")


def materialize_candidate(candidate_path: Path, target: Path) -> Path:
    """Replay one candidate's actual reference closure into a disposable root."""
    stage = candidate_path.parents[2]
    shutil.copytree(stage, target / stage.relative_to(REPO), dirs_exist_ok=True)
    candidate = json.loads(candidate_path.read_bytes())
    for group in ("manifest", "fragments", "sources", "tests"):
        entries = candidate.get(group, [])
        if isinstance(entries, dict): entries = [entries]
        for entry in entries:
            snapshot = candidate_path.parent / entry["snapshot_path"]
            data = snapshot.read_bytes()
            expected = entry.get("file_sha256", entry.get("sha256"))
            assert hashlib.sha256(data).hexdigest() == expected, snapshot
            destination = target / entry["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
    return target / candidate_path.relative_to(REPO)


def write_documents(root: Path, documents: dict[Path, bytes]) -> None:
    for relative, data in documents.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def materialize_revision(target: Path, revision: str) -> Path:
    """Read a named Git revision into a test root; no checkout or live imports."""
    import io
    import tarfile

    target.mkdir(parents=True, exist_ok=True)
    requested = (
        "main", "scripts", "src", "docs/governance",
        "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration",
    )
    paths = [path for path in requested if subprocess.run(
        ["git", "cat-file", "-e", f"{revision}:{path}"], cwd=REPO,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0]
    payload = subprocess.check_output(
        ["git", "archive", "--format=tar", revision, *paths], cwd=REPO,
    )
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        archive.extractall(target, filter="data")
    return target
