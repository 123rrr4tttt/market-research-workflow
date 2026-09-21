from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import subprocess
import sys
import shlex
from pathlib import Path
from typing import Annotated, Any, get_args, get_origin, get_type_hints

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/formal_release/generate_stage2_candidate_record.py"
INTAKE_SCRIPT = ROOT / "scripts/formal_release/stage2_candidate_intake.py"
MATERIALIZER_SCRIPT = ROOT / "scripts/formal_release/materialize_stage2_candidate.py"
R1_SCRIPT = ROOT / "scripts/formal_release/check_candidate_identity.py"

SPEC = importlib.util.spec_from_file_location("stage2_candidate_record", SCRIPT)
INTAKE_SPEC = importlib.util.spec_from_file_location("stage2_candidate_intake_for_record", INTAKE_SCRIPT)
MATERIALIZER_SPEC = importlib.util.spec_from_file_location("stage2_materializer_for_record", MATERIALIZER_SCRIPT)
R1_SPEC = importlib.util.spec_from_file_location("candidate_identity_for_record", R1_SCRIPT)
assert all((SPEC, INTAKE_SPEC, MATERIALIZER_SPEC, R1_SPEC))
assert all((SPEC.loader, INTAKE_SPEC.loader, MATERIALIZER_SPEC.loader, R1_SPEC.loader))
tool = importlib.util.module_from_spec(SPEC)
intake = importlib.util.module_from_spec(INTAKE_SPEC)
materializer = importlib.util.module_from_spec(MATERIALIZER_SPEC)
r1 = importlib.util.module_from_spec(R1_SPEC)
for module, spec in ((tool, SPEC), (intake, INTAKE_SPEC), (materializer, MATERIALIZER_SPEC), (r1, R1_SPEC)):
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)


@pytest.fixture(autouse=True)
def stub_upstream_validators(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise strict Stage2 checks with deterministic local validator receipts."""
    monkeypatch.setattr(
        intake.stage_family_fragment_rebind,
        "check_candidate",
        lambda path, *, repo_root, history_only: {
            "family": path.parent.name,
            "status": intake.stage_family_fragment_rebind.LIVE_STATUS,
            "candidate_id": "0" * 64,
        },
    )
    monkeypatch.setattr(
        intake.generate_stage1_production_contract_record,
        "validate_stage1_record",
        lambda root, record: None,
    )


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(("git", "-C", str(root), *args), text=True).strip()


def git_bytes(root: Path, *args: str, stdin: bytes = b"") -> str:
    return subprocess.check_output(("git", "-C", str(root), *args), input=stdin).decode()


def write(root: Path, relative: str, payload: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def write_index_tree(root: Path, rows: tuple[tuple[str, str, bytes], ...]) -> str:
    records: list[bytes] = []
    for mode, relative, payload in rows:
        blob = git_bytes(root, "hash-object", "-w", "--stdin", stdin=payload).strip()
        records.append(f"{mode} {blob}\t{relative}\0".encode())
    git_bytes(root, "read-tree", "--empty")
    git_bytes(root, "update-index", "-z", "--index-info", stdin=b"".join(records))
    return git(root, "write-tree")


def fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, dict[str, object]]:
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "source@example.test")
    git(source, "config", "user.name", "Source")
    git(source, "remote", "add", "origin", "https://example.test/source.git")
    write(source, "keep.txt", b"keep\n")
    stage0_paths = tuple(intake.STAGE0_CANDIDATE_PATHS)
    for stage0 in stage0_paths:
        write(source, stage0, b"base\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "base")
    base = git(source, "rev-parse", "HEAD")
    git(source, "update-ref", intake.DEFAULT_BASE_REF, base)
    stage0_source = Path("closure/stage0.py")
    stage0_snapshot = stage0_paths[0].parent / "snapshots/stage0"
    write(source, stage0_source.as_posix(), b"changed stage0 closure\n")
    write(source, stage0_snapshot.as_posix(), b"stage0 snapshot\n")
    for stage0 in stage0_paths:
        write(source, stage0, b"{}\n")
    write(
        source,
        stage0_paths[0].as_posix(),
        json.dumps(
            {
                "sources": [
                    {
                        "path": stage0_source.as_posix(),
                        "snapshot_path": "snapshots/stage0",
                    }
                ]
            }
        ).encode(),
    )
    write(
        source,
        "stage1-evidence/record.json",
        b'{"status":"PRODUCTION_CONTRACT_IMPLEMENTED_NOT_AUTHORITY",'
        b'"authoritative":false,"commands":{"r3":{"receipt":'
        b'{"path":"stage1-receipts/r3.log"}}}}\n',
    )
    write(source, "stage1-receipts/r3.log", b"PASS\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "closure")

    clone = tmp_path / "clone"
    subprocess.check_call(("git", "clone", "--no-local", str(source), str(clone)))
    git(clone, "update-ref", intake.DEFAULT_BASE_REF, base)
    git(clone, "checkout", "--detach", base)
    git(clone, "remote", "set-url", "origin", "https://example.test/source.git")
    manifest = intake.build_manifest(
        source_root=source,
        stage0_paths=stage0_paths,
        stage1_record=Path("stage1-evidence/record.json"),
        stage1_receipts=(Path("stage1-receipts/r3.log"),),
        stage0_closure_upserts=(stage0_source, stage0_snapshot),
        additional_upserts=(Path("keep.txt"),),
    )
    keep = next(row for row in manifest["entries"] if row["path"] == "keep.txt")  # type: ignore[index]
    assert (keep["base_mode"], keep["base_blob"]) == (keep["mode"], keep["blob"])
    materializer.materialize_candidate(
        target_root=clone,
        source_root=source,
        manifest=manifest,  # type: ignore[arg-type]
    )
    manifest_path = tmp_path / "intake.json"
    manifest_path.write_bytes(intake.canonical_json(manifest) + b"\n")
    r1_path = tmp_path / "r1.json"
    report = r1.evaluate_candidate_identity(
        repo_root=clone,
        expected_commit=git(clone, "rev-parse", "HEAD"),
        expected_tree=git(clone, "rev-parse", "HEAD^{tree}"),
        candidate_strategy=tool.CANDIDATE_STRATEGY,
    )
    r1_path.write_text(report.to_json(), encoding="utf-8")
    return source, clone, manifest_path, r1_path, manifest


def refresh_r1(candidate: Path, r1_path: Path) -> None:
    report = r1.evaluate_candidate_identity(
        repo_root=candidate,
        expected_commit=git(candidate, "rev-parse", "HEAD"),
        expected_tree=git(candidate, "rev-parse", "HEAD^{tree}"),
        candidate_strategy=tool.CANDIDATE_STRATEGY,
    )
    r1_path.write_text(report.to_json(), encoding="utf-8")


def test_candidate_record_return_has_exact_non_authority_metadata() -> None:
    return_hint = get_type_hints(tool.build_record, include_extras=True)["return"]
    assert get_origin(return_hint) is Annotated
    value, metadata = get_args(return_hint)
    assert value == dict[str, Any]
    tokens = shlex.split(metadata)
    assert tokens[0] == "kit:non-authoritative"
    fields = dict(token.split("=", 1) for token in tokens[1:])
    assert fields == {
        "derived_as": "exact_candidate_record",
        "fact_source": "candidate_intake_manifest+r1_report+git_tree",
        "witness": "test:test_builds_create_only_record_outside_candidate",
    }


def test_builds_create_only_record_outside_candidate(tmp_path: Path) -> None:
    source, candidate, manifest_path, r1_path, manifest = fixture(tmp_path)
    output = tmp_path / "candidate-record.json"

    record = tool.build_record(
        repo_root=candidate,
        source_root=source,
        manifest_path=manifest_path,
        r1_path=r1_path,
    )
    tool.validate_record(candidate, record)
    assert record["schema_version"] == tool.SCHEMA_VERSION
    assert record["authoritative"] is False
    assert record["authority"] == {key: False for key in tool.AUTHORITY_KEYS}
    assert record["authority_ceiling"] == "PRODUCTION_RELEASE_NOT_AUTHORIZED"
    assert record["bindings"]["candidate"]["commit"] == git(candidate, "rev-parse", "HEAD")
    assert record["bindings"]["r1"]["status"] == "PASS"
    assert record["bindings"]["stage0_b23"] == manifest["stage0_b23"]  # type: ignore[index]

    assert tool.write_create_only(candidate, record, output) == output.resolve()
    assert output.read_bytes() == tool.canonical_json(record) + b"\n"
    assert git(candidate, "status", "--porcelain=v1", "--untracked-files=all") == ""


def test_replace_ref_cannot_disguise_wrong_raw_parent(
    tmp_path: Path,
) -> None:
    source, candidate, manifest_path, r1_path, manifest = fixture(tmp_path)
    git(candidate, "config", "user.name", "Disposable Fixture")
    git(candidate, "config", "user.email", "fixture@example.test")
    base = manifest["source"]["base_oid"]  # type: ignore[index]
    tree = git(candidate, "rev-parse", "HEAD^{tree}")
    wrong_parent = subprocess.check_output(
        ("git", "-C", str(candidate), "commit-tree", tree),
        input=b"unrelated root\n",
    ).decode().strip()
    wrong_commit = subprocess.check_output(
        ("git", "-C", str(candidate), "commit-tree", tree, "-p", wrong_parent),
        input=b"wrong actual parent\n",
    ).decode().strip()
    replacement = subprocess.check_output(
        ("git", "-C", str(candidate), "commit-tree", tree, "-p", str(base)),
        input=b"replacement claims manifest base\n",
    ).decode().strip()
    git(candidate, "update-ref", "HEAD", wrong_commit)
    git(candidate, "replace", wrong_commit, replacement)
    refresh_r1(candidate, r1_path)

    interpreted = subprocess.check_output(
        ("git", "-C", str(candidate), "cat-file", "commit", "HEAD"),
        # This observation deliberately enables the attack in the disposable
        # fixture; the production reader below must still reject raw lineage.
        env={key: value for key, value in os.environ.items() if key != "GIT_NO_REPLACE_OBJECTS"},
    )
    assert f"parent {base}\n".encode() in interpreted.partition(b"\n\n")[0]
    with pytest.raises(
        tool.Stage2RecordError,
        match="raw commit parent is not exactly the manifest base",
    ):
        tool.build_record(
            repo_root=candidate,
            source_root=source,
            manifest_path=manifest_path,
            r1_path=r1_path,
        )


@pytest.mark.parametrize("grafts_kind", ("regular", "symlink", "nonempty-directory"))
def test_candidate_common_dir_grafts_fail_closed(
    tmp_path: Path,
    grafts_kind: str,
) -> None:
    source, candidate, manifest_path, r1_path, manifest = fixture(tmp_path)
    common_dir_raw = git(candidate, "rev-parse", "--git-common-dir")
    common_dir = Path(common_dir_raw)
    if not common_dir.is_absolute():
        common_dir = candidate / common_dir
    grafts = common_dir.resolve() / "info" / "grafts"
    grafts.parent.mkdir(parents=True, exist_ok=True)
    commit = git(candidate, "rev-parse", "HEAD")
    base = manifest["source"]["base_oid"]  # type: ignore[index]
    forged = f"{commit} {base}\n"
    if grafts_kind == "regular":
        grafts.write_text(forged, encoding="ascii")
    elif grafts_kind == "symlink":
        target = tmp_path / "forged-grafts"
        target.write_text(forged, encoding="ascii")
        grafts.symlink_to(target)
    else:
        grafts.mkdir()
        (grafts / "forged").write_text(forged, encoding="ascii")

    with pytest.raises(tool.Stage2RecordError, match=r"common-dir info/grafts .*forbidden"):
        tool.build_record(
            repo_root=candidate,
            source_root=source,
            manifest_path=manifest_path,
            r1_path=r1_path,
        )


def test_candidate_delta_preserves_raw_paths_and_delete(tmp_path: Path) -> None:
    source = tmp_path / "paths-source"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "paths@example.test")
    git(source, "config", "user.name", "Paths")
    write(source, "removed.txt", b"delete me\n")
    write(source, "typed.txt", b"not a link\n")
    git(source, "add", "removed.txt", "typed.txt")
    base_tree = git(source, "write-tree")

    raw_paths = (
        "caf\u00e9.txt",
        "trailing .txt",
        "tab\there.txt",
        "newline\nhere.txt",
    )
    candidate_tree = write_index_tree(
        source,
        tuple(("100644", relative, f"{relative}\n".encode()) for relative in raw_paths)
        + (("120000", "typed.txt", b"target\n"),),
    )
    observed = tool._candidate_delta(source, base_tree, candidate_tree)

    expected_paths = (*raw_paths, "removed.txt", "typed.txt")
    assert sorted(observed) == sorted(expected_paths)
    expected_order = sorted(expected_paths, key=lambda relative: relative.encode())
    assert list(observed) == expected_order
    for relative in raw_paths:
        row = observed[relative]
        assert (row["base_mode"], row["base_blob"]) == ("000000", "")
        assert row["mode"] == "100644"
        assert tool.GIT_OID.fullmatch(row["blob"]) is not None

    deletion = observed["removed.txt"]
    assert deletion["mode"] == "000000"
    assert deletion["blob"] == ""
    assert deletion["base_mode"] == "100644"
    assert tool.GIT_OID.fullmatch(deletion["base_blob"]) is not None
    typechange = observed["typed.txt"]
    assert typechange["base_mode"] == "100644"
    assert typechange["mode"] == "120000"
    assert tool.GIT_OID.fullmatch(typechange["base_blob"]) is not None
    assert tool.GIT_OID.fullmatch(typechange["blob"]) is not None


def test_candidate_delta_fails_closed_on_malformed_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oid = "0" * 40
    valid_metadata = f":100644 000000 {oid} {oid} D".encode()
    cases = (
            (
                b"garbage\0",
                "unpaired path record",
        ),
            (
                b":\0x.txt\0",
                "metadata is malformed",
        ),
            (
                b":10064x 100644 0*40 0*40 M\0cafe.txt\0".replace(b"0*40", oid.encode()),
                "metadata is malformed",
        ),
            (
                valid_metadata + b"\0\0",
                "duplicate git diff-tree path|empty",
        ),
        (
            b":100644 100644 "
            + oid.encode()
            + b" "
            + oid.encode()
            + b" R100\0old.txt\0new.txt\0",
            "rename or copy",
        ),
            (
                b":100644 000000 " + oid.encode() + b" " + oid.encode() + b" D\0x.txt",
                "not NUL terminated",
        ),
            (
                b":100644 000000 " + oid.encode() + b" " + oid.encode() + b" D\0caf\xe9.txt\0",
                "path is not UTF-8",
        ),
    )

    for output, message in cases:
        monkeypatch.setattr(tool, "_git_bytes", lambda *args, output=output: output)
        with pytest.raises(tool.Stage2RecordError, match=message):
            tool._candidate_delta(Path("unused"), "0" * 40, "0" * 40)


def test_drifted_r1_or_manifest_fails_closed(tmp_path: Path) -> None:
    source, candidate, manifest_path, r1_path, _ = fixture(tmp_path)
    tampered_r1 = tmp_path / "tampered-r1.json"
    payload = json.loads(r1_path.read_text(encoding="utf-8"))
    payload["findings"][0]["summary"] = "not the same"
    tampered_r1.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(tool.Stage2RecordError, match="R1 report bytes"):
        tool.build_record(
            repo_root=candidate,
            source_root=source,
            manifest_path=manifest_path,
            r1_path=tampered_r1,
        )

    tampered_manifest = tmp_path / "tampered-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["stage0_b23"]["refs"][0]["sha256"] = "0" * 64
    tampered_manifest.write_bytes(intake.canonical_json(manifest) + b"\n")
    with pytest.raises((tool.Stage2RecordError, intake.Stage2IntakeError)):
        tool.build_record(
            repo_root=candidate,
            source_root=source,
            manifest_path=tampered_manifest,
            r1_path=r1_path,
        )


def test_record_revalidates_stage0_closure_before_build_and_validate(tmp_path: Path) -> None:
    source, candidate, manifest_path, r1_path, manifest = fixture(tmp_path)
    tampered_manifest = tmp_path / "tampered-stage0-manifest.json"
    payload = json.loads(json.dumps(manifest))
    payload["stage0_b23"]["closure"] = []
    tampered_manifest.write_bytes(intake.canonical_json(payload) + b"\n")
    with pytest.raises(tool.Stage2RecordError, match="Stage0 closure must exactly equal"):
        tool.build_record(
            repo_root=candidate,
            source_root=source,
            manifest_path=tampered_manifest,
            r1_path=r1_path,
        )

    record = tool.build_record(
        repo_root=candidate,
        source_root=source,
        manifest_path=manifest_path,
        r1_path=r1_path,
    )
    tampered_record = json.loads(json.dumps(record))
    tampered_record["bindings"]["stage0_b23"]["closure"] = []
    with pytest.raises(tool.Stage2RecordError, match="Stage0 closure must exactly equal"):
        tool.validate_record(candidate, tampered_record)


def test_record_build_and_validate_construct_base_tree_index_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, candidate, manifest_path, r1_path, _manifest = fixture(tmp_path)
    original_builder = tool._build_base_tree_index
    build_calls: list[Path] = []
    validate_calls: list[Path] = []
    phase = "build"

    def count_build(source_root: Path, base_oid: str):
        target = build_calls if phase == "build" else validate_calls
        target.append(source_root)
        return original_builder(source_root, base_oid)

    monkeypatch.setattr(tool, "_build_base_tree_index", count_build)
    record = tool.build_record(
        repo_root=candidate,
        source_root=source,
        manifest_path=manifest_path,
        r1_path=r1_path,
    )
    assert build_calls == [source]
    assert validate_calls == []
    phase = "validate"
    tool.validate_record(candidate, record)
    assert validate_calls == [source]


def test_record_revalidates_upstream_semantics_even_with_synced_entry_hashes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, candidate, manifest_path, r1_path, manifest = fixture(tmp_path)
    record = tool.build_record(
        repo_root=candidate,
        source_root=source,
        manifest_path=manifest_path,
        r1_path=r1_path,
    )

    stage0_path = source / intake.STAGE0_CANDIDATE_PATHS[1]
    stage0_payload = b'{"status":"SEMANTIC_TAMPER"}\n'
    stage0_path.write_bytes(stage0_payload)
    stage0_manifest = json.loads(json.dumps(manifest))
    _sync_binding(
        stage0_manifest,
        intake.STAGE0_CANDIDATE_PATHS[1],
        stage0_payload,
        source,
    )
    stage0_manifest_path = tmp_path / "tampered-stage0-intake.json"
    stage0_manifest_path.write_bytes(intake.canonical_json(stage0_manifest) + b"\n")
    tampered_record = json.loads(json.dumps(record))
    tampered_record["bindings"]["intake"] = {
        "path": stage0_manifest_path.resolve().as_posix(),
        "sha256": hashlib.sha256(stage0_manifest_path.read_bytes()).hexdigest(),
    }
    _sync_binding(
        tampered_record["bindings"]["stage0_b23"],
        intake.STAGE0_CANDIDATE_PATHS[1],
        stage0_payload,
        source,
        refs_only=True,
    )

    def reject_stage0_semantics(
        path: Path, *, repo_root: Path, history_only: bool
    ) -> object:
        if path in {stage0_path, intake.STAGE0_CANDIDATE_PATHS[1]}:
            raise RuntimeError("semantic status tamper")  # noqa: TRY003
        return {
            "family": path.parent.name,
            "status": intake.stage_family_fragment_rebind.LIVE_STATUS,
            "candidate_id": "0" * 64,
        }

    monkeypatch.setattr(
        intake.stage_family_fragment_rebind, "check_candidate", reject_stage0_semantics
    )
    with pytest.raises(tool.Stage2RecordError, match="Stage0 C3 candidate validation failed"):
        tool.validate_record(candidate, tampered_record)

    def accept_stage0_for_stage1_phase(
        path: Path, *, repo_root: Path, history_only: bool
    ) -> object:
        return {
            "family": path.parent.name,
            "status": intake.stage_family_fragment_rebind.LIVE_STATUS,
            "candidate_id": "0" * 64,
        }

    monkeypatch.setattr(
        intake.stage_family_fragment_rebind,
        "check_candidate",
        accept_stage0_for_stage1_phase,
    )
    stage0_path.write_bytes(b"{}\n")
    stage1_relative = Path("stage1-evidence/record.json")
    stage1_path = source / stage1_relative
    stage1_payload = (
        b'{"status":"SEMANTIC_TAMPER_NOT_AUTHORITY",'
        b'"authoritative":false,"commands":{"r3":{"receipt":'
        b'{"path":"stage1-receipts/r3.log"}}}}\n'
    )
    stage1_path.write_bytes(stage1_payload)
    stage1_manifest = json.loads(json.dumps(manifest))
    _sync_binding(stage1_manifest, stage1_relative, stage1_payload, source)
    stage1_manifest_path = tmp_path / "tampered-stage1-intake.json"
    stage1_manifest_path.write_bytes(intake.canonical_json(stage1_manifest) + b"\n")

    original_stage1_validate = intake.generate_stage1_production_contract_record.validate_stage1_record

    def reject_stage1_semantics(root: Path, value: dict[str, object]) -> None:
        if value.get("status") == "SEMANTIC_TAMPER_NOT_AUTHORITY":
            raise RuntimeError("semantic status tamper")  # noqa: TRY003
        original_stage1_validate(root, value)  # type: ignore[misc]

    monkeypatch.setattr(
        intake.generate_stage1_production_contract_record,
        "validate_stage1_record",
        reject_stage1_semantics,
    )
    with pytest.raises(tool.Stage2RecordError, match="Stage1 record validation failed"):
        tool.build_record(
            repo_root=candidate,
            source_root=source,
            manifest_path=stage1_manifest_path,
            r1_path=r1_path,
        )


def _sync_binding(
    payload: dict[str, object],
    relative: Path,
    content: bytes,
    source: Path,
    *,
    refs_only: bool = False,
) -> None:
    blob = subprocess.check_output(
        ("git", "-C", str(source), "hash-object", "--stdin"),
        input=content,
    ).decode().strip()
    digest = hashlib.sha256(content).hexdigest()
    rows: list[dict[str, str]]
    if refs_only:
        rows = list(payload["refs"])  # type: ignore[index]
    else:
        rows = list(payload["entries"])  # type: ignore[index]
        stage0 = payload.get("stage0_b23")
        if isinstance(stage0, dict):
            rows.extend(stage0.get("refs", []))  # type: ignore[union-attr]
        stage1 = payload.get("stage1")
        if isinstance(stage1, dict):
            stage1_record = stage1.get("record")  # type: ignore[union-attr]
            if isinstance(stage1_record, dict):
                rows.append(stage1_record)  # type: ignore[arg-type]
            rows.extend(stage1.get("receipts", []))  # type: ignore[union-attr]
    for row in rows:
        if row.get("path") == relative.as_posix():
            row["sha256"] = digest
            row["blob"] = blob


def test_rejects_existing_or_in_candidate_output(tmp_path: Path) -> None:
    source, candidate, manifest_path, r1_path, _ = fixture(tmp_path)
    record = tool.build_record(
        repo_root=candidate,
        source_root=source,
        manifest_path=manifest_path,
        r1_path=r1_path,
    )
    existing = tmp_path / "existing.json"
    existing.write_text("x", encoding="utf-8")
    with pytest.raises(tool.Stage2RecordError, match="create-only target already exists"):
        tool.write_create_only(candidate, record, existing)
    with pytest.raises(tool.Stage2RecordError, match="outside the candidate"):
        tool.write_create_only(candidate, record, candidate / "record.json")


def test_nested_repo_root_is_rejected_without_pollution(tmp_path: Path) -> None:
    source, candidate, manifest_path, r1_path, _ = fixture(tmp_path)
    record = tool.build_record(
        repo_root=candidate,
        source_root=source,
        manifest_path=manifest_path,
        r1_path=r1_path,
    )
    nested = candidate / "nested"
    nested.mkdir()
    output = candidate / "record.json"

    with pytest.raises(
        tool.Stage2RecordError,
        match="repo root must be the git checkout top-level",
    ):
        tool.write_create_only(nested, record, output)

    assert not output.exists()
    assert not (nested / "record.json").exists()


def test_read_json_fails_fast_on_fifo(tmp_path: Path) -> None:
    destination = tmp_path / "manifest.json"
    os.mkfifo(destination)

    with pytest.raises(tool.Stage2RecordError, match="missing or invalid JSON"):
        tool._read_json(destination, "candidate intake manifest")


def test_source_root_rename_to_output_parent_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, candidate, manifest_path, r1_path, _ = fixture(tmp_path)
    record = tool.build_record(
        repo_root=candidate,
        source_root=source,
        manifest_path=manifest_path,
        r1_path=r1_path,
    )
    output_parent = tmp_path / "receipt"
    output_parent.mkdir()
    output = output_parent / "record.json"
    original_write = tool.write_create_only_bytes

    def rename_source_before_write(
        path: Path,
        payload: bytes,
        identities: object,
    ) -> Path:
        source.rename(output_parent)
        return original_write(path, payload, identities)

    monkeypatch.setattr(tool, "write_create_only_bytes", rename_source_before_write)
    with pytest.raises(
        tool.Stage2RecordError,
        match="ancestor entered a forbidden checkout",
    ):
        tool.write_create_only(candidate, record, output)

    assert not output.exists()
