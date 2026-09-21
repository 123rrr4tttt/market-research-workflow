"""Assertions for additive exact-byte successor candidates.

The frozen capability artifacts intentionally retain predecessor bindings.  A
new stage candidate is the only accepted witness for current-checkout bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


CURRENT_STAGE = "stage-b19-2026-09-05"
HISTORY_STAGE = "stage-b18-2026-09-05"
TEMPORARY_B19_STAGE = "stage-b19-2099-01-01"
# Compatibility constant for callers that still exercise the B18 temporary stage.
TEMPORARY_B18_STAGE = "stage-b18-2099-01-01"
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
STAGE_CHECKER_PATH = REPOSITORY_ROOT / "scripts/stage_family_fragment_rebind.py"


def load_stage_candidate(
    root: Path,
    family: str,
    stage: str = CURRENT_STAGE,
) -> tuple[Path, dict[str, Any]]:
    path = (
        root
        / "development/latest-dev-docs/development-plans/CURRENT_DEV"
        / "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind"
        / stage
        / "candidates"
        / family
        / "candidate.v2.json"
    )
    assert path.is_file(), f"missing additive {stage} {family} candidate"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == "mrw.family_fragment_rebind.candidate.v2"
    assert payload["family"] == family
    assert payload["status"] == "CANDIDATE_VALID_NOT_AUTHORITY"
    binding_kind = "EXACT_BINDING" if family == "I1" else "EXACT_BYTE"
    stage_label = stage.removeprefix("stage-").split("-", 1)[0].upper()
    expected_amendment = (
        f"STAGE_{stage_label}_C7_CURRENT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
        if family == "C7" and stage_label in {"B18", "B19"}
        else f"STAGE_{stage_label}_{family}_{binding_kind}_REBIND_CANDIDATE_NOT_AUTHORITY"
    )
    assert payload["amendment"] == expected_amendment
    without_digest = {
        key: value for key, value in payload.items() if key != "content_digest"
    }
    canonical = json.dumps(
        without_digest,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == payload["content_digest"]
    if payload.get("file_sha256"):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == payload["file_sha256"]
    return path, payload


def candidate_binding(
    candidate: dict[str, Any], relative_path: str
) -> dict[str, Any] | None:
    for group in (
        "sources",
        "implementation_bindings",
        "test_bindings",
        "rollback_bindings",
    ):
        for binding in candidate.get(group, []):
            if binding.get("path") == relative_path:
                return binding
    return None


def assert_current_binding(
    root: Path,
    candidate_path: Path,
    candidate: dict[str, Any],
    relative_path: str,
    predecessor_sha256: str,
) -> str:
    source = root / relative_path
    assert source.is_file(), relative_path
    actual_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    assert actual_sha256 != predecessor_sha256, relative_path
    binding = candidate_binding(candidate, relative_path)
    assert binding is not None, f"{relative_path} has no additive candidate binding"
    assert binding["file_sha256"] == actual_sha256
    assert binding["bytes"] == len(source.read_bytes())
    snapshot = candidate_path.parent / binding["snapshot_path"]
    assert snapshot.read_bytes() == source.read_bytes()
    return actual_sha256


def stage_candidate_in_temporary_repository(
    documents: dict[Path, bytes],
    family: str,
) -> dict[str, str]:
    """Publish and live-check one candidate in an isolated repository copy."""

    def repository_relative(path: Path) -> Path:
        try:
            return path.relative_to(REPOSITORY_ROOT)
        except ValueError:
            return path

    manifest_path = next(
        path for path in documents if path.parent.name == "manifests"
    )
    manifest = json.loads(documents[manifest_path].decode("utf-8"))
    document_relatives = {
        repository_relative(relative) for relative in documents
    }
    with tempfile.TemporaryDirectory(prefix=f"b19-{family.lower()}-") as name:
        temporary_root = Path(name)
        for relative, payload in documents.items():
            target = temporary_root / repository_relative(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)

        referenced_paths = {
            Path(reference["path"])
            for group in ("fragments", "sources", "tests")
            for reference in manifest[group]
            if Path(reference["path"]) not in document_relatives
        }
        for relative in referenced_paths:
            source = REPOSITORY_ROOT / relative
            target = temporary_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, target)
            except OSError:
                shutil.copyfile(source, target)

        manifest_relative = repository_relative(manifest_path)
        stage_relative = manifest_relative.parent.parent
        candidate_relative = stage_relative / "candidates" / family
        temporary_root.joinpath(candidate_relative).mkdir(parents=True)
        staged = subprocess.run(
            [
                sys.executable,
                STAGE_CHECKER_PATH,
                "stage",
                "--repo-root",
                temporary_root,
                "--manifest",
                manifest_relative,
                "--output-dir",
                candidate_relative,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert staged.returncode == 0, staged.stdout + staged.stderr

        checked = subprocess.run(
            [
                sys.executable,
                STAGE_CHECKER_PATH,
                "check-candidate",
                "--repo-root",
                temporary_root,
                "--candidate",
                candidate_relative / "candidate.v2.json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr
        result = json.loads(checked.stdout)
        assert result["family"] == family
        assert result["status"] == "CANDIDATE_VALID_NOT_AUTHORITY"
        return result


def assert_predecessor(
    root: Path,
    candidate: dict[str, Any],
    family: str,
    predecessor_stage: str | None = None,
) -> None:
    """Ensure the current candidate records its immutable predecessor."""

    if predecessor_stage is None:
        pattern = re.compile(
            rf"^development/latest-dev-docs/development-plans/CURRENT_DEV/"
            rf"2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
            rf"(stage-b\d+-\d{{4}}-\d{{2}}-\d{{2}})/candidates/{family}/"
            rf"candidate\.v2\.json$"
        )
        stages = [
            match.group(1)
            for reference in candidate.get("sources", [])
            if (match := pattern.fullmatch(reference.get("path", "")))
        ]
        assert stages, f"candidate records no {family} predecessor candidate"
        predecessor_stage = max(stages)

    relative = (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
        f"{predecessor_stage}/candidates/{family}/candidate.v2.json"
    )
    predecessor = root / relative
    assert predecessor.is_file(), relative
    binding = candidate_binding(candidate, relative)
    assert binding is not None, f"missing immutable predecessor: {relative}"
    assert binding["file_sha256"] == hashlib.sha256(predecessor.read_bytes()).hexdigest()


def assert_b16_predecessor(
    root: Path,
    candidate: dict[str, Any],
    family: str,
) -> None:
    """Legacy name retained while callers migrate to predecessor discovery."""

    assert_predecessor(root, candidate, family)
