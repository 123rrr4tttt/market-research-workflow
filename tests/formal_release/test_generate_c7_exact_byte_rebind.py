from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/generate_c7_exact_byte_rebind.py"
SPEC = importlib.util.spec_from_file_location("c7_exact_byte_generator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_stage_aliases_and_invalid_dates_are_rejected() -> None:
    assert GENERATOR.validate_stage("B12") == GENERATOR.DEFAULT_B12_STAGE
    assert GENERATOR.validate_stage(GENERATOR.DEFAULT_B12_STAGE) == GENERATOR.DEFAULT_B12_STAGE
    assert GENERATOR.validate_stage("B18") == GENERATOR.DEFAULT_B18_STAGE
    assert GENERATOR.validate_stage("stage-b18-2099-01-01") == "stage-b18-2099-01-01"
    assert GENERATOR.validate_stage("B19") == GENERATOR.DEFAULT_B19_STAGE
    assert GENERATOR.validate_stage("stage-b19-2099-01-01") == "stage-b19-2099-01-01"
    assert GENERATOR.validate_stage("B23") == GENERATOR.DEFAULT_B23_STAGE
    assert GENERATOR.validate_stage("stage-b23-2099-01-01") == "stage-b23-2099-01-01"
    for stage in ("B13", "stage-b12-2099-01-01", "stage-b18-2099-02-30", "stage-b19-2099-02-30", "stage-b23-2099-02-30", "../B18"):
        with pytest.raises(GENERATOR.GenerationError, match="invalid stage"):
            GENERATOR.validate_stage(stage)


def test_b12_is_checked_as_immutable_predecessor_history() -> None:
    documents = GENERATOR._build_documents(ROOT, "B12")
    assert set(documents) == {GENERATOR.B12_FRAGMENT_REL, GENERATOR.B12_MANIFEST_REL}
    for relative, expected in GENERATOR.B12_PREDECESSORS.items():
        if relative == GENERATOR.B12_CANDIDATE_REL:
            continue
        assert documents[relative] == (ROOT / relative).read_bytes()
        assert hashlib.sha256(documents[relative]).hexdigest() == expected


def test_b18_is_deterministic_and_closes_current_bindings_and_b12_history() -> None:
    first = GENERATOR._build_documents(ROOT, "stage-b18-2099-01-01")
    second = GENERATOR._build_documents(ROOT, "stage-b18-2099-01-01")
    assert first == second

    fragment_rel = (
        GENERATOR.EXACT_REBIND_REL / "stage-b18-2099-01-01/fragments/C7.json"
    )
    manifest_rel = (
        GENERATOR.EXACT_REBIND_REL / "stage-b18-2099-01-01/manifests/C7.json"
    )
    assert set(first) == {fragment_rel, manifest_rel}
    fragment = json.loads(first[fragment_rel])
    manifest = json.loads(first[manifest_rel])

    assert fragment["family"] == "C7"
    assert all(value is False for value in fragment["authority"].values())
    assert fragment["content_digest"] == GENERATOR._content_digest(fragment)
    assert manifest["amendment"] == GENERATOR.B18_AMENDMENT
    assert manifest["fragments"][0]["file_sha256"] == hashlib.sha256(
        first[fragment_rel]
    ).hexdigest()

    source_refs = {item["path"]: item for item in manifest["sources"]}
    test_refs = {item["path"]: item for item in manifest["tests"]}
    for group, refs in (
        ("source_bindings", source_refs),
        ("implementation_bindings", source_refs),
        ("test_bindings", test_refs),
    ):
        declared = {item["path"] for item in fragment[group]}
        assert declared
        assert declared <= set(refs)

    for path in (
        "scripts/generate_c7_exact_byte_rebind.py",
        "main/backend/app/successor_runtime/specification/shared_family_generator.py",
        GENERATOR.STAGE_CHECKER_REL,
    ):
        assert path in source_refs
        assert source_refs[path]["file_sha256"] == _sha(ROOT / path)
    for relative, expected in GENERATOR.B12_PREDECESSORS.items():
        path = relative.as_posix()
        assert source_refs[path]["file_sha256"] == expected == _sha(ROOT / relative)

    implementation_roles = {
        item["path"]: item["role"] for item in fragment["implementation_bindings"]
    }
    assert implementation_roles[GENERATOR.STAGE_CHECKER_REL] == "stage_candidate_protocol"
    assert not (ROOT / fragment_rel).exists()
    assert not (ROOT / manifest_rel).exists()


def test_b19_is_deterministic_and_guards_b18_direct_predecessor() -> None:
    # B19 is already a checked-in create-only stage. Build its deterministic
    # payload directly; overwrite protection is covered separately below.
    first = GENERATOR._build_b18_documents(ROOT, GENERATOR.DEFAULT_B19_STAGE)
    second = GENERATOR._build_b18_documents(ROOT, GENERATOR.DEFAULT_B19_STAGE)
    assert first == second
    fragment_rel = GENERATOR.EXACT_REBIND_REL / "stage-b19-2026-09-05/fragments/C7.json"
    manifest_rel = GENERATOR.EXACT_REBIND_REL / "stage-b19-2026-09-05/manifests/C7.json"
    assert set(first) == {fragment_rel, manifest_rel}
    manifest = json.loads(first[manifest_rel])
    assert manifest["amendment"] == GENERATOR.B19_AMENDMENT
    source_refs = {item["path"]: item for item in manifest["sources"]}
    for relative, expected in GENERATOR.B19_PREDECESSORS.items():
        assert source_refs[relative.as_posix()]["file_sha256"] == expected == _sha(ROOT / relative)


def test_b23_is_deterministic_and_guards_b19_direct_predecessor() -> None:
    first = GENERATOR._build_b18_documents(ROOT, "stage-b23-2099-01-01")
    second = GENERATOR._build_b18_documents(ROOT, "stage-b23-2099-01-01")
    assert first == second
    fragment_rel = GENERATOR.EXACT_REBIND_REL / "stage-b23-2099-01-01/fragments/C7.json"
    manifest_rel = GENERATOR.EXACT_REBIND_REL / "stage-b23-2099-01-01/manifests/C7.json"
    assert set(first) == {fragment_rel, manifest_rel}
    manifest = json.loads(first[manifest_rel])
    assert manifest["amendment"] == GENERATOR.B23_AMENDMENT
    source_refs = {item["path"]: item for item in manifest["sources"]}
    assert set(GENERATOR.B23_PREDECESSORS) == {
        GENERATOR.B19_FRAGMENT_REL,
        GENERATOR.B19_MANIFEST_REL,
        GENERATOR.B19_CANDIDATE_REL,
    }
    for relative, expected in GENERATOR.B23_PREDECESSORS.items():
        assert source_refs[relative.as_posix()]["file_sha256"] == expected == _sha(ROOT / relative)


def test_create_only_targets_are_protected(tmp_path: Path) -> None:
    fragment_rel = (
        GENERATOR.EXACT_REBIND_REL / "stage-b18-2099-01-01/fragments/C7.json"
    )
    target = tmp_path / fragment_rel
    target.parent.mkdir(parents=True)
    target.write_bytes(b"existing")
    with pytest.raises(GENERATOR.GenerationError, match="refusing to overwrite"):
        GENERATOR._guard_create_only(
            tmp_path,
            {
                fragment_rel: b"new",
                fragment_rel.parent.parent / "manifests/C7.json": b"new",
            },
        )


def test_b12_write_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert GENERATOR.main(["--repo-root", str(ROOT), "--stage", "B12", "--write"]) == 2
    output = capsys.readouterr().out
    assert "B12 predecessor is immutable and cannot be written" in output
