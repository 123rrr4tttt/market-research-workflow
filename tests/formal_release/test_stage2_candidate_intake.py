from __future__ import annotations

import importlib.util
import copy
import json
import os
import shutil
import stat
import subprocess
import sys
import shlex
import unicodedata
from pathlib import Path
from typing import Annotated, Any, get_args, get_origin, get_type_hints

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/formal_release/stage2_candidate_intake.py"
SPEC = importlib.util.spec_from_file_location("stage2_candidate_intake", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)
REAL_CHECK_CANDIDATE = tool.stage_family_fragment_rebind.check_candidate


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ("git", "-C", str(root), *args),
        text=True,
    ).strip()


def write(root: Path, relative: str, payload: bytes, *, executable: bool = False) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    if executable:
        path.chmod(0o755)
    return path


@pytest.fixture(autouse=True)
def stub_upstream_validators(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool]] = []

    def check_candidate(path: Path, *, repo_root: Path, history_only: bool) -> dict[str, str]:
        family = path.parent.name
        calls.append((family, history_only))
        return {
            "family": family,
            "status": tool.stage_family_fragment_rebind.LIVE_STATUS,
            "candidate_id": "0" * 64,
        }

    monkeypatch.setattr(tool.stage_family_fragment_rebind, "check_candidate", check_candidate)
    monkeypatch.setattr(
        tool.generate_stage1_production_contract_record,
        "validate_stage1_record",
        lambda root, record: None,
    )


def fixture(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    source.mkdir(parents=True)
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "source@example.test")
    git(source, "config", "user.name", "Source")
    git(source, "remote", "add", "origin", "https://example.test/source.git")
    write(source, ".gitignore", b"base\n")
    write(source, "closure/existing.py", b"base\n")
    write(source, "obsolete.txt", b"obsolete\n")
    write(source, tool.DEFAULT_STAGE0_ROOT / "snapshots" / ("a" * 64), b"base stage0 closure\n")
    for family in tool.STAGE0_FAMILIES:
        write(
            source,
            tool.DEFAULT_STAGE0_ROOT / "candidates" / family / "candidate.v2.json",
            b"{}\n",
        )
    git(source, "add", ".")
    git(source, "commit", "-m", "base")
    base = git(source, "rev-parse", "HEAD")
    git(source, "update-ref", tool.DEFAULT_BASE_REF, base)

    for family in tool.STAGE0_FAMILIES:
        write(
            source,
            tool.DEFAULT_STAGE0_ROOT / "candidates" / family / "candidate.v2.json",
            b"{}\n",
        )
    write(
        source,
        "stage1-evidence/record.json",
        b'{"status":"PRODUCTION_CONTRACT_IMPLEMENTED_NOT_AUTHORITY",'
        b'"authoritative":false,"commands":{"r3":{"receipt":'
        b'{"path":"stage1-receipts/r3.log"}}}}\n',
    )
    write(source, "stage1-receipts/r3.log", b"PASS\n")
    write(source, "closure/existing.py", b"closure\n")
    safe_link = source / "closure/link"
    safe_link.symlink_to("existing.py")
    (source / "obsolete.txt").unlink()
    git(source, "add", ".")
    git(source, "commit", "-m", "closure")
    assert git(source, "status", "--porcelain=v1", "--untracked-files=all") == ""
    return source, base


def build(tmp_path: Path, **overrides: object) -> dict[str, object]:
    source, _ = fixture(tmp_path)
    kwargs: dict[str, object] = {
        "source_root": source,
        "stage0_paths": tool.STAGE0_CANDIDATE_PATHS,
        "stage1_record": Path("stage1-evidence/record.json"),
        "stage1_receipts": (Path("stage1-receipts/r3.log"),),
        "additional_upserts": (Path("closure/existing.py"),),
        "delete_paths": (Path("obsolete.txt"),),
    }
    kwargs.update(overrides)
    return tool.build_manifest(**kwargs)  # type: ignore[arg-type]


def break_direct_binding_path(manifest: dict[str, object]) -> None:
    references = manifest["stage0_b23"]["refs"]  # type: ignore[index]
    references[0] = {**references[0], "path": []}


def test_manifest_return_has_exact_non_authority_metadata() -> None:
    return_hint = get_type_hints(tool.build_manifest, include_extras=True)["return"]
    assert get_origin(return_hint) is Annotated
    value, metadata = get_args(return_hint)
    assert value == dict[str, Any]
    tokens = shlex.split(metadata)
    assert tokens[0] == "kit:non-authoritative"
    fields = dict(token.split("=", 1) for token in tokens[1:])
    assert fields == {
        "derived_as": "exact_candidate_intake",
        "fact_source": "git_source_checkout+stage0_refs+stage1_bindings+selected_files",
        "witness": "test:test_builds_canonical_manifest_with_exact_base_preconditions",
    }


def test_builds_canonical_manifest_with_exact_base_preconditions(tmp_path: Path) -> None:
    manifest = build(tmp_path)

    assert manifest["schema_version"] == tool.SCHEMA_VERSION
    assert manifest["authoritative"] is False
    entries = {row["path"]: row for row in manifest["entries"]}  # type: ignore[index]
    assert set(entries) == {
        "closure/existing.py",
        "obsolete.txt",
        "stage1-evidence/record.json",
        "stage1-receipts/r3.log",
        *(str(path) for path in tool.STAGE0_CANDIDATE_PATHS),
    }
    assert entries["obsolete.txt"]["operation"] == "DELETE"  # type: ignore[index]
    assert manifest["stage0_b23"]["closure"] == []  # type: ignore[index]
    assert entries["closure/existing.py"]["base_blob"] != entries["closure/existing.py"]["blob"]  # type: ignore[index]
    assert entries["stage1-evidence/record.json"]["base_mode"] == "000000"  # type: ignore[index]
    assert tool.canonical_json(manifest) == tool.canonical_json(json.loads(tool.canonical_json(manifest)))


def test_read_cache_hit_requires_full_fingerprint_and_does_not_skip_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tool.BoundedReadOnlyCache(max_entries=2)
    manifest = build(tmp_path, read_cache=cache)
    fingerprint = {**manifest["source"], "object_format": "sha1"}  # type: ignore[arg-type]
    assert tool.cached_base_index(manifest, fingerprint, cache) is not None
    for field in ("checkout", "dev", "ino", "head", "porcelain_sha256", "base_oid", "object_format"):
        drifted = dict(fingerprint)
        drifted[field] = "drift" if field not in {"dev", "ino"} else fingerprint[field] + 1
        assert tool.cached_base_index(manifest, drifted, cache) is None

    key = tool._manifest_cache_key(manifest, object_format="sha1")
    cache.put(key, object())
    assert tool.cached_base_index(manifest, fingerprint, cache) is None

    reads = 0
    original_read = tool._read_regular_bytes

    def counting_read(*args, **kwargs):
        nonlocal reads
        reads += 1
        return original_read(*args, **kwargs)

    monkeypatch.setattr(tool, "_read_regular_bytes", counting_read)
    build(tmp_path / "second", read_cache=cache)
    assert reads > 0


def test_read_cache_fails_closed_without_explicit_sha1_object_format(tmp_path: Path) -> None:
    cache = tool.BoundedReadOnlyCache(max_entries=2)
    manifest = build(tmp_path, read_cache=cache)
    fingerprint = {**manifest["source"], "object_format": "sha1"}  # type: ignore[arg-type]
    key = tool._manifest_cache_key(manifest, object_format="sha1")
    value = cache.get(key)
    assert value is not None

    missing = dict(fingerprint)
    del missing["object_format"]
    assert tool.cached_base_index(manifest, missing, cache) is None

    for object_format in (None, "sha256", 123):
        drifted = dict(fingerprint)
        drifted["object_format"] = object_format
        assert tool.cached_base_index(manifest, drifted, cache) is None


def test_routes_stage0_closure_separately_from_stage1_closure(tmp_path: Path) -> None:
    source, _ = fixture(tmp_path)
    write(source, "closure/referenced_source.py", b"source\n")
    write(source, "closure/referenced_test.py", b"test\n")
    direct_snapshot = tool.STAGE0_CANDIDATE_PATHS[0].parent / "snapshots/source"
    test_snapshot = tool.STAGE0_CANDIDATE_PATHS[0].parent / "snapshots/test"
    write(source, direct_snapshot, b"source snapshot\n")
    write(source, test_snapshot, b"test snapshot\n")
    (source / tool.STAGE0_CANDIDATE_PATHS[0]).write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "path": "closure/referenced_source.py",
                        "snapshot_path": "snapshots/source",
                    }
                ],
                "tests": [
                    {
                        "path": "closure/referenced_test.py",
                        "snapshot_path": "snapshots/test",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = tool.build_manifest(
        source_root=source,
        stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
        stage0_closure_upserts=(
            direct_snapshot,
            test_snapshot,
            Path("closure/referenced_test.py"),
            Path("closure/referenced_source.py"),
        ),
        stage1_record=Path("stage1-evidence/record.json"),
        stage1_receipts=(Path("stage1-receipts/r3.log"),),
        additional_upserts=(Path("closure/existing.py"),),
    )
    entries = {row["path"]: row for row in manifest["entries"]}  # type: ignore[index]
    stage0_closure = [row["path"] for row in manifest["stage0_b23"]["closure"]]  # type: ignore[index]
    stage1_closure = [row["path"] for row in manifest["stage1"]["closure"]]  # type: ignore[index]
    assert stage0_closure == [
        "closure/referenced_source.py",
        "closure/referenced_test.py",
        direct_snapshot.as_posix(),
        test_snapshot.as_posix(),
    ]
    assert stage1_closure == ["closure/existing.py"]
    assert all(
        entries[path] is row
        for path, row in zip(stage0_closure, manifest["stage0_b23"]["closure"], strict=True)
    )  # type: ignore[index]
    assert all(
        entries[path] is row
        for path, row in zip(stage1_closure, manifest["stage1"]["closure"], strict=True)
    )  # type: ignore[index]
    tool.validate_manifest(manifest)


def test_allows_recursive_predecessor_candidate_snapshot_closure(tmp_path: Path) -> None:
    source, _ = fixture(tmp_path)
    predecessor = Path(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
        "stage-b22-2026-09-05/candidates/C2/candidate.v2.json"
    )
    predecessor_snapshot = predecessor.parent / "snapshots" / "historical-source"
    direct_snapshot = tool.STAGE0_CANDIDATE_PATHS[0].parent / "snapshots/predecessor-candidate"
    write(source, "closure/historical.py", b"historical\n")
    write(source, direct_snapshot, b"direct candidate snapshot\n")
    write(source, predecessor_snapshot, b"historical snapshot\n")
    write(
        source,
        predecessor,
        json.dumps(
            {
                "sources": [
                    {
                        "path": "closure/historical.py",
                        "snapshot_path": "snapshots/historical-source",
                    }
                ]
            }
        ).encode(),
    )
    (source / tool.STAGE0_CANDIDATE_PATHS[0]).write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "path": predecessor.as_posix(),
                        "snapshot_path": "snapshots/predecessor-candidate",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    manifest = tool.build_manifest(
        source_root=source,
        stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
        stage0_closure_upserts=(
            direct_snapshot,
            predecessor,
            predecessor_snapshot,
            Path("closure/historical.py"),
        ),
        stage1_record=Path("stage1-evidence/record.json"),
        stage1_receipts=(Path("stage1-receipts/r3.log"),),
    )

    assert [row["path"] for row in manifest["stage0_b23"]["closure"]] == [
        Path("closure/historical.py").as_posix(),
        predecessor.as_posix(),
        predecessor_snapshot.as_posix(),
        direct_snapshot.as_posix(),
    ]


def test_recursive_predecessor_candidate_fifo_fails_before_read(tmp_path: Path) -> None:
    source, _ = fixture(tmp_path)
    predecessor = Path(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
        "stage-b22-2026-09-05/candidates/C2/candidate.v2.json"
    )
    direct_snapshot = tool.STAGE0_CANDIDATE_PATHS[0].parent / "snapshots/predecessor-candidate"
    write(source, direct_snapshot, b"direct candidate snapshot\n")
    write(source, predecessor, b"{}\n")
    (source / tool.STAGE0_CANDIDATE_PATHS[0]).write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "path": predecessor.as_posix(),
                        "snapshot_path": "snapshots/predecessor-candidate",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (source / predecessor).unlink()
    os.mkfifo(source / predecessor)

    with pytest.raises(tool.Stage2IntakeError, match="recursive candidate must be a regular file"):
        tool._read_stage0_reference_paths(source, tool.STAGE0_CANDIDATE_PATHS)


def test_v4_recursive_closure_allows_bound_historical_predecessor(tmp_path: Path) -> None:
    source, _ = fixture(tmp_path)
    direct = tool.FRESH_STAGE0_CANDIDATE_PATHS[0]
    predecessor = tool.DEFAULT_STAGE0_ROOT / "candidates/C2/candidate.v2.json"
    snapshot = direct.parent / "snapshots/predecessor-candidate"
    write(source, snapshot.as_posix(), b"historical predecessor snapshot\n")
    write(source, predecessor.as_posix(), b"{}\n")
    write(
        source,
        direct.as_posix(),
        json.dumps(
            {
                "sources": [
                    {
                        "path": predecessor.as_posix(),
                        "snapshot_path": "snapshots/predecessor-candidate",
                    }
                ]
            }
        ).encode(),
    )

    references = tool._read_stage0_reference_paths(
        source,
        (direct,),
        stage0_root=tool.FRESH_STAGE0_ROOT,
    )

    assert predecessor in references
    assert snapshot in references


def test_v4_full_reference_set_includes_historical_regression_candidates(
    tmp_path: Path,
) -> None:
    source, _ = fixture(tmp_path)
    _write_v4_inputs(source)
    expected_snapshots = set()
    for candidate in tool.SUCCESSOR_RUNTIME_CANDIDATE_PATHS:
        snapshot = candidate.parent / "snapshots/regression-input"
        expected_snapshots.add(snapshot)
        write(source, snapshot.as_posix(), b"historical input\n")
        write(
            source,
            candidate.as_posix(),
            json.dumps({"sources": [{
                "path": "closure/existing.py",
                "snapshot_path": "snapshots/regression-input",
            }]}).encode(),
        )

    references = tool._read_stage0_reference_paths(
        source,
        tool.FRESH_STAGE0_CANDIDATE_PATHS,
        stage0_root=tool.FRESH_STAGE0_ROOT,
    )

    assert set(tool.FRESH_V4_HISTORICAL_STAGE0_CANDIDATE_PATHS) <= references
    assert {path.parent.name for path in tool.SUCCESSOR_RUNTIME_CANDIDATE_PATHS} == {
        "C4", "C6", "C7", "C9"
    }
    assert expected_snapshots <= references


@pytest.mark.parametrize("remove_snapshot", [False, True])
def test_missing_or_nonregular_recursive_stage0_reference_fails_closed(
    tmp_path: Path, remove_snapshot: bool
) -> None:
    source, _ = fixture(tmp_path)
    source_path = Path("closure/referenced.py")
    snapshot = tool.STAGE0_CANDIDATE_PATHS[0].parent / "snapshots/referenced"
    write(source, source_path, b"referenced\n")
    write(source, snapshot, b"snapshot\n")
    (source / tool.STAGE0_CANDIDATE_PATHS[0]).write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "path": source_path.as_posix(),
                        "snapshot_path": "snapshots/referenced",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest = tool.build_manifest(
        source_root=source,
        stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
        stage0_closure_upserts=(source_path, snapshot),
        stage1_record=Path("stage1-evidence/record.json"),
        stage1_receipts=(Path("stage1-receipts/r3.log"),),
    )

    victim = snapshot if remove_snapshot else source_path
    (source / victim).unlink()
    if not remove_snapshot:
        os.mkfifo(source / victim)
    with pytest.raises(
        tool.Stage2IntakeError,
        match=r"Stage0 reference path or snapshot (is (missing|invalid)|must be a regular file)",
    ):
        tool.assert_stage0_closure_projection(manifest, source)


def test_stage0_closure_is_exact_not_a_subset_or_superset(tmp_path: Path) -> None:
    source, _ = fixture(tmp_path)
    source_path = Path("closure/referenced.py")
    snapshot = tool.STAGE0_CANDIDATE_PATHS[0].parent / "snapshots/referenced"
    write(source, source_path, b"changed\n")
    write(source, snapshot, b"snapshot\n")
    (source / tool.STAGE0_CANDIDATE_PATHS[0]).write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "path": source_path.as_posix(),
                        "snapshot_path": "snapshots/referenced",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    common = {
        "source_root": source,
        "stage0_paths": tool.STAGE0_CANDIDATE_PATHS,
        "stage1_record": Path("stage1-evidence/record.json"),
        "stage1_receipts": (Path("stage1-receipts/r3.log"),),
    }
    with pytest.raises(tool.Stage2IntakeError, match="missing=.*referenced.py"):
        tool.build_manifest(**common, stage0_closure_upserts=(snapshot,))  # type: ignore[arg-type]
    with pytest.raises(tool.Stage2IntakeError, match="extra=.*unreferenced"):
        write(source, "closure/unreferenced.py", b"extra\n")
        tool.build_manifest(**common, stage0_closure_upserts=(source_path, snapshot, Path("closure/unreferenced.py")))  # type: ignore[arg-type]
    (source / "closure/unreferenced.py").unlink()
    with pytest.raises(tool.Stage2IntakeError, match="missing=.*referenced.py"):
        tool.build_manifest(**common, additional_upserts=(source_path,), stage0_closure_upserts=(snapshot,))  # type: ignore[arg-type]

    manifest = tool.build_manifest(**common, stage0_closure_upserts=(source_path, snapshot))  # type: ignore[arg-type]
    assert [row["path"] for row in manifest["stage0_b23"]["closure"]] == [
        source_path.as_posix(),
        snapshot.as_posix(),
    ]
    assert manifest["stage1"]["closure"] == []


def test_write_is_create_only_and_cli_outputs_manifest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source, _ = fixture(tmp_path)
    output = tmp_path / "intake.json"
    argv = ["--source-root", str(source)]
    for path in tool.STAGE0_CANDIDATE_PATHS:
        argv.extend(("--stage0-ref", path.as_posix()))
    argv.extend(
        (
            "--stage1-record",
            "stage1-evidence/record.json",
            "--stage1-receipt",
            "stage1-receipts/r3.log",
            "--upsert",
            "closure/existing.py",
            "--output",
            str(output),
        )
    )

    assert tool.main(argv) == 0
    payload = json.loads(output.read_bytes())
    assert payload == json.loads(capsys.readouterr().out)
    assert payload["stage0_b23"]["closure"] == []
    assert payload["stage1"]["closure"][0]["path"] == "closure/existing.py"  # type: ignore[index]
    assert output.read_bytes() == tool.canonical_json(payload) + b"\n"
    with pytest.raises(tool.Stage2IntakeError, match="create-only target already exists"):
        tool.write_create_only(output, payload)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        ("/absolute.txt", "escapes repository root"),
        ("../outside.txt", "escapes repository root"),
        ("keep.txt//", "not a canonical POSIX path"),
        ("a/./b", "not a canonical POSIX path"),
        ("trailing/", "not a canonical POSIX path"),
        (r"platform\alias.txt", "not a canonical POSIX path"),
        ("C:/platform-alias.txt", "not a canonical POSIX path"),
        (".git/config", "git metadata"),
        ("__pycache__/tool.pyc", "forbidden history/cache/runtime"),
        ("runtime/tool.json", "forbidden history/cache/runtime"),
        ("secrets/token.json", "secret directory"),
        (unicodedata.normalize("NFD", "café.txt"), "not NFC-normalized"),
    ],
)
def test_rejects_unsafe_paths(relative: str, message: str) -> None:
    with pytest.raises(tool.Stage2IntakeError, match=message):
        tool.safe_relative(relative)


def test_accepts_exact_project_source_paths() -> None:
    assert tool.safe_relative("main/backend/app/successor_runtime/runtime/token_provider.py")
    assert tool.safe_relative("main/backend/app/credentials.py")
    assert tool.safe_relative("main/backend/tests/test_secret_loader.py")
    assert tool.safe_relative("main/backend/tests/test_password_policy.py")
    assert tool.safe_relative("main/backend/.env.example")
    assert tool.safe_relative("main/backend/.env.production.example")


def test_accepts_only_contract14_derived_history_prefix() -> None:
    allowed = (
        "stage1-successor-evidence/contract14-local-execution-v1/history/"
        "history-verification-receipt.v1.json"
    )
    assert tool.safe_relative(allowed) == Path(allowed)
    for relative in (
        "stage1-successor-evidence/other/history/receipt.json",
        "stage1-successor-evidence/contract14-local-execution-v1/history",
        "stage1-successor-evidence/contract14-local-execution-v1/history/cache/data.json",
    ):
        with pytest.raises(tool.Stage2IntakeError, match="forbidden history/cache/runtime"):
            tool.safe_relative(relative)


def test_candidate_specific_current_byte_successor_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    current = b"current celery bytes\n"
    predecessor = "1" * 64
    live_path = Path("main/backend/app/celery_app.py")
    write(source, live_path.as_posix(), current)
    candidate_sha = ""
    for family, candidate_path in zip(
        tool.STAGE0_FAMILIES, tool.STAGE0_CANDIDATE_PATHS, strict=True
    ):
        candidate = {"fragments": [], "sources": [], "tests": []}
        if family == "C2":
            candidate["sources"] = [
                {"path": live_path.as_posix(), "file_sha256": predecessor}
            ]
        payload = tool.canonical_json(candidate) + b"\n"
        write(source, candidate_path.as_posix(), payload)
        if family == "C2":
            candidate_sha = tool.sha256_bytes(payload)

    def history_candidate(path: Path, *, repo_root: Path, history_only: bool) -> dict[str, str]:
        assert history_only is True
        return {
            "family": path.parent.name,
            "status": tool.stage_family_fragment_rebind.HISTORY_STATUS,
            "candidate_id": "0" * 64,
        }

    monkeypatch.setattr(tool.stage_family_fragment_rebind, "check_candidate", history_candidate)
    registry = {
        "successors": [
            {
                "successor_id": "i1-c5-4-celery-app-current-bytes-v1",
                "family": "I1",
                "source_path": live_path.as_posix(),
                "predecessor_sha256": predecessor,
                "successor_sha256": tool.sha256_bytes(current),
                "predecessor_declarations": [],
            }
        ]
    }
    rows = tool._registry_resolution_rows(
        source,
        tool.STAGE0_CANDIDATE_PATHS,
        registry,
        expected_identity=tool.directory_identity(source),
    )
    assert rows == [
        {
            "candidate_path": tool.STAGE0_CANDIDATE_PATHS[0].as_posix(),
            "candidate_sha256": candidate_sha,
            "family": "C2",
            "group": "sources",
            "source_path": live_path.as_posix(),
            "predecessor_sha256": predecessor,
            "successor_sha256": tool.sha256_bytes(current),
            "registry_successor_id": "i1-c5-4-celery-app-current-bytes-v1",
            "registry_family": "I1",
        }
    ]
    registry["successors"][0]["successor_id"] = "unrelated-successor"
    with pytest.raises(tool.Stage2IntakeError, match="candidate-specific successor"):
        tool._registry_resolution_rows(
            source,
            tool.STAGE0_CANDIDATE_PATHS,
            registry,
            expected_identity=tool.directory_identity(source),
        )


def test_v3_inherits_shared_i1_successor_and_resolves_real_current_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tool.stage_family_fragment_rebind,
        "check_candidate",
        REAL_CHECK_CANDIDATE,
    )
    builder_path = ROOT / tool.CONVERGENCE_CURRENT_BYTE_SUCCESSOR_REGISTRY.parent / (
        "build_current_byte_binding_successors_v3.py"
    )
    spec = importlib.util.spec_from_file_location("intake_v3_binding_builder", builder_path)
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    # Validate current bytes without creating any formal binding output.
    registry = json.loads(builder.build_documents(ROOT)[builder.REGISTRY_REL])
    rows = tool._registry_resolution_rows(
        ROOT,
        tool.STAGE0_CANDIDATE_PATHS,
        registry,
        expected_identity=tool.directory_identity(ROOT),
    )
    shared_rows = [
        row for row in rows
        if row["source_path"] == "main/backend/app/services/agent_runtime/run_loop.py"
    ]
    assert {row["family"] for row in shared_rows} == {"C5", "C6", "I1"}
    assert len(shared_rows) == 3
    assert {row["registry_successor_id"] for row in shared_rows} == {
        "c5-c6-i1-run-loop-current-bytes-v3"
    }
    assert [
        row
        for row in rows
        if row["family"] == "C6"
        and row["source_path"]
        == "main/backend/app/services/agent_core/native_provider.py"
    ] == [
        {
            "candidate_path": (
                tool.DEFAULT_STAGE0_ROOT / "candidates/C6/candidate.v2.json"
            ).as_posix(),
            "candidate_sha256": (
                "ffdb0020e8a3617a8693f10657a97787f11c6c759bc9afe96e7d06dcb876f87a"
            ),
            "family": "C6",
            "group": "sources",
            "source_path": "main/backend/app/services/agent_core/native_provider.py",
            "predecessor_sha256": (
                "e3735f8e74c81f5e1a979bb993926097500f97a2c64065c60f3d5bba2d8e1428"
            ),
            "successor_sha256": (
                "1daddedc2fe8a435c062fa66019e00db2b47aeb2e88d8fce97e7dfe3e8bd4cf5"
            ),
            "registry_successor_id": "i1-c6-native-provider-current-bytes-v2",
            "registry_family": "I1",
        }
    ]


def test_v3_manifest_binds_successor_and_remediation_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _base = fixture(tmp_path)
    registry = Path("stage1-successor-evidence/current-byte-registry.json")
    remediation = Path("stage1-successor-evidence/remediation-record.json")
    write(source, registry.as_posix(), b"{}\n")
    write(source, remediation.as_posix(), b"{}\n")
    resolutions = [
        {
            "candidate_path": tool.STAGE0_CANDIDATE_PATHS[0].as_posix(),
            "candidate_sha256": "1" * 64,
            "family": "C2",
            "group": "sources",
            "source_path": "main/backend/app/celery_app.py",
            "predecessor_sha256": "2" * 64,
            "successor_sha256": "3" * 64,
            "registry_successor_id": "successor-1",
            "registry_family": "I1",
        }
    ]
    resolutions = [
        {
            "candidate_path": tool.STAGE0_CANDIDATE_PATHS[0].as_posix(),
            "candidate_sha256": "1" * 64,
            "family": "C2",
            "group": "sources",
            "source_path": "main/backend/app/celery_app.py",
            "predecessor_sha256": "2" * 64,
            "successor_sha256": "3" * 64,
            "registry_successor_id": "successor-1",
            "registry_family": "I1",
        }
    ]

    def validate_v3(*args, **kwargs):
        return (
            tool.STAGE0_CANDIDATE_PATHS,
            {},
            {Path("stage1-receipts/r3.log")},
            resolutions,
        )

    monkeypatch.setattr(tool, "_validate_stage0_and_stage1_v3", validate_v3)
    monkeypatch.setattr(tool, "DEFAULT_CURRENT_BYTE_SUCCESSOR_REGISTRY", registry)
    monkeypatch.setattr(tool, "DEFAULT_STAGE1_REMEDIATION_RECORD", remediation)
    manifest = tool.build_manifest(
        source_root=source,
        stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
        stage1_record=Path("stage1-evidence/record.json"),
        stage1_receipts=(Path("stage1-receipts/r3.log"),),
        current_byte_successor_registry=registry,
        stage1_remediation_record=remediation,
        additional_upserts=(Path("closure/existing.py"),),
        delete_paths=(Path("obsolete.txt"),),
    )
    assert manifest["schema_version"] == tool.SCHEMA_VERSION_V3
    assert manifest["stage0_b23"]["current_byte_successor_registry"]["path"] == registry.as_posix()
    assert manifest["stage0_b23"]["successor_resolutions"] == resolutions
    assert manifest["stage1"]["remediation_record"]["path"] == remediation.as_posix()


def _write_v4_inputs(source: Path) -> None:
    for path in tool.SUCCESSOR_RUNTIME_CANDIDATE_PATHS:
        write(source, path.as_posix(), b"{}\n")
    for family, path in zip(
        tool.STAGE0_FAMILIES, tool.FRESH_STAGE0_CANDIDATE_PATHS, strict=True
    ):
        write(
            source,
            path.as_posix(),
            json.dumps(
                {
                    "family": family,
                    "fragments": [],
                    "sources": [],
                    "tests": [],
                }
            ).encode(),
        )
    write(source, tool.FRESH_CURRENT_BYTE_SUCCESSOR_REGISTRY.as_posix(), b"{}\n")
    write(source, tool.FRESH_C9_SIDECAR_INPUT.as_posix(), b"{}\n")
    write(
        source,
        tool.STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD.as_posix(),
        b"{}\n",
    )
    write(source, tool.ALL_LINES_AGGREGATE.as_posix(), b"{}\n")


def _build_v4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    source, _base = fixture(tmp_path)
    _write_v4_inputs(source)

    def validate_v4(*args: object, **kwargs: object):
        return (
            tool.FRESH_STAGE0_CANDIDATE_PATHS,
            {},
            {Path("stage1-receipts/r3.log")},
            [],
        )

    monkeypatch.setattr(tool, "_validate_stage0_and_stage1_v4", validate_v4)
    monkeypatch.setattr(tool, "_validate_all_lines_aggregate", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        tool,
        "source_closure_module",
        type(
            "V4ClosureStub",
            (),
            {
                "compute_workflow_selector_delta": staticmethod(lambda *args, **kwargs: ()),
                "compute_frontend_selector_delta": staticmethod(lambda *args, **kwargs: ()),
                "check_workflow_selector_manifest_closure": staticmethod(
                    lambda *args, **kwargs: None
                ),
                "check_frontend_selector_manifest_closure": staticmethod(
                    lambda *args, **kwargs: None
                ),
            },
        ),
    )
    references = tool._read_stage0_reference_paths(
        source,
        tool.FRESH_STAGE0_CANDIDATE_PATHS,
        stage0_root=tool.FRESH_STAGE0_ROOT,
    )
    required_closure = tool._required_stage0_closure(
        source,
        git(source, "rev-parse", tool.DEFAULT_BASE_REF),
        references,
        direct_stage0=tool.FRESH_STAGE0_CANDIDATE_PATHS,
    )
    return tool.build_manifest(
        source_root=source,
        stage0_paths=tool.FRESH_STAGE0_CANDIDATE_PATHS,
        stage0_closure_upserts=tuple(
            sorted(required_closure, key=lambda path: path.as_posix())
        ),
        stage1_record=Path("stage1-evidence/record.json"),
        stage1_receipts=(Path("stage1-receipts/r3.log"),),
        current_byte_successor_registry=tool.FRESH_CURRENT_BYTE_SUCCESSOR_REGISTRY,
        stage1_remediation_record=(
            tool.STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD
        ),
        all_lines_aggregate=tool.ALL_LINES_AGGREGATE,
    )


def test_v4_manifest_binds_fresh_root_and_required_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _build_v4(tmp_path, monkeypatch)

    assert manifest["schema_version"] == tool.SCHEMA_VERSION_V4
    assert manifest["stage0_b23"]["root"] == tool.FRESH_STAGE0_ROOT.as_posix()  # type: ignore[index]
    assert manifest["stage0_b23"]["successor_resolutions"] == []  # type: ignore[index]
    assert [row["path"] for row in manifest["stage0_b23"]["refs"]] == [  # type: ignore[index]
        path.as_posix() for path in tool.FRESH_STAGE0_CANDIDATE_PATHS
    ]
    assert [row["path"] for row in manifest["stage0_b23"]["closure"]] == sorted(  # type: ignore[index]
        path.as_posix()
        for path in (*tool.SUCCESSOR_RUNTIME_CANDIDATE_PATHS, tool.FRESH_C9_SIDECAR_INPUT)
    )
    aggregate = manifest["stage1"]["all_lines_aggregate"]  # type: ignore[index]
    assert aggregate["path"] == tool.ALL_LINES_AGGREGATE.as_posix()
    assert aggregate in manifest["stage1"]["closure"]  # type: ignore[index]
    tool.validate_manifest_structure(manifest)


def _build_v5(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    source, _base = fixture(tmp_path)
    _write_v4_inputs(source)
    write(source, tool.STAGE1_PRODUCTION_BINDING_SUCCESSOR.as_posix(), b"{}\n")

    def validate_v4(*args: object, **kwargs: object):
        return (
            tool.FRESH_STAGE0_CANDIDATE_PATHS,
            {},
            {Path("stage1-receipts/r3.log")},
            [],
        )

    successor = {
        "current_bindings": [
            {
                "path": "stage1-evidence/record.json",
                "successor_sha256": tool.sha256_bytes(
                    (source / "stage1-evidence/record.json").read_bytes()
                ),
                "predecessor_sha256": None,
                "historical_pointer": None,
                "role": "TEST_CURRENT_BINDING",
                "relation": "ADDITIVE_CURRENT_REQUIREMENT",
            }
        ],
        "current_required_files_summary": {
            "current_binding_count": 1,
            "mismatch_count_at_generation": 0,
        },
    }
    monkeypatch.setattr(tool, "_validate_stage0_and_stage1_v4", validate_v4)
    monkeypatch.setattr(tool, "_validate_all_lines_aggregate", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        tool,
        "_validate_stage1_production_binding_successor",
        lambda *args, **kwargs: successor,
    )
    monkeypatch.setattr(
        tool,
        "source_closure_module",
        type(
            "V5ClosureStub",
            (),
            {
                "compute_workflow_selector_delta": staticmethod(lambda *args, **kwargs: ()),
                "compute_frontend_selector_delta": staticmethod(lambda *args, **kwargs: ()),
                "check_workflow_selector_manifest_closure": staticmethod(
                    lambda *args, **kwargs: None
                ),
                "check_frontend_selector_manifest_closure": staticmethod(
                    lambda *args, **kwargs: None
                ),
            },
        ),
    )
    references = tool._read_stage0_reference_paths(
        source,
        tool.FRESH_STAGE0_CANDIDATE_PATHS,
        stage0_root=tool.FRESH_STAGE0_ROOT,
    )
    required_closure = tool._required_stage0_closure(
        source,
        git(source, "rev-parse", tool.DEFAULT_BASE_REF),
        references,
        direct_stage0=tool.FRESH_STAGE0_CANDIDATE_PATHS,
    )
    return tool.build_manifest(
        source_root=source,
        stage0_paths=tool.FRESH_STAGE0_CANDIDATE_PATHS,
        stage0_closure_upserts=tuple(
            sorted(required_closure, key=lambda path: path.as_posix())
        ),
        stage1_record=Path("stage1-evidence/record.json"),
        stage1_receipts=(Path("stage1-receipts/r3.log"),),
        current_byte_successor_registry=tool.FRESH_CURRENT_BYTE_SUCCESSOR_REGISTRY,
        stage1_remediation_record=(
            tool.STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD
        ),
        all_lines_aggregate=tool.ALL_LINES_AGGREGATE,
        stage1_production_binding_successor=(
            tool.STAGE1_PRODUCTION_BINDING_SUCCESSOR
        ),
    )


def test_v5_adds_explicit_current_byte_binding_without_changing_v4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    v5 = _build_v5(tmp_path, monkeypatch)
    assert v5["schema_version"] == tool.SCHEMA_VERSION_V5
    assert v5["stage1"]["current_byte_binding_successor"]["path"] == (  # type: ignore[index]
        tool.STAGE1_PRODUCTION_BINDING_SUCCESSOR.as_posix()
    )
    tool.validate_manifest_structure(v5)

    v4 = copy.deepcopy(v5)
    v4["schema_version"] = tool.SCHEMA_VERSION_V4
    v4["stage1"].pop("current_byte_binding_successor")  # type: ignore[union-attr]
    tool.validate_manifest_structure(v4)


def test_v5_structure_requires_exact_successor_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _build_v5(tmp_path, monkeypatch)
    bad_binding = copy.deepcopy(  # type: ignore[index]
        manifest["stage1"]["current_byte_binding_successor"]
    )
    bad_binding["path"] = "wrong.json"
    manifest["stage1"]["current_byte_binding_successor"] = bad_binding  # type: ignore[index]
    with pytest.raises(tool.Stage2IntakeError, match="successor drift"):
        tool.validate_manifest_structure(manifest)


def _projected_binding_fixture(tmp_path: Path) -> tuple[Path, dict[str, object], object]:
    source = tmp_path / "projection-source"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "source@example.test")
    git(source, "config", "user.name", "Source")
    write(source, "base.txt", b"base\n")
    write(source, "changed.txt", b"old\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "base")
    base = git(source, "rev-parse", "HEAD")
    write(source, "changed.txt", b"current\n")
    index = tool.BaseTreeIndex.from_repo(source, base, runner=tool.git_output)
    manifest: dict[str, object] = {
        "source": {"base_oid": base},
        "entries": [tool._entry(source, Path("changed.txt"), base, base_index=index)],
    }
    return source, manifest, index


def _projection_successor(source: Path, *paths: str) -> dict[str, object]:
    return {
        "current_bindings": [
            {
                "path": path,
                "successor_sha256": tool.sha256_bytes((source / path).read_bytes()),
                "predecessor_sha256": None,
                "historical_pointer": None,
                "role": "TEST",
                "relation": "ADDITIVE_CURRENT_REQUIREMENT",
            }
            for path in paths
        ],
        "current_required_files_summary": {
            "current_binding_count": len(paths),
            "mismatch_count_at_generation": 0,
        },
    }


def test_v5_projected_binding_accepts_upsert_and_base_fallback(tmp_path: Path) -> None:
    source, manifest, index = _projected_binding_fixture(tmp_path)
    successor = _projection_successor(source, "base.txt", "changed.txt")
    result = tool._validate_stage1_successor_candidate_projection(
        manifest,
        source,
        successor,
        expected_identity=tool.directory_identity(source),
        base_index=index,
    )
    assert result == {
        "current_mismatch_count": 0,
        "projected_candidate_mismatch_count": 0,
    }


@pytest.mark.parametrize("mutation", ("omit-upsert", "tamper-upsert", "delete"))
def test_v5_projected_binding_rejects_omission_tamper_and_delete(
    tmp_path: Path,
    mutation: str,
) -> None:
    source, manifest, index = _projected_binding_fixture(tmp_path)
    successor = _projection_successor(source, "changed.txt")
    if mutation == "omit-upsert":
        manifest["entries"] = []
    elif mutation == "tamper-upsert":
        manifest["entries"][0]["sha256"] = "0" * 64  # type: ignore[index]
    else:
        manifest["entries"][0].update(  # type: ignore[index]
            operation="DELETE",
            mode="000000",
            sha256="",
            blob="",
        )
    with pytest.raises(tool.Stage2IntakeError, match="mismatch_count=1"):
        tool._validate_stage1_successor_candidate_projection(
            manifest,
            source,
            successor,
            expected_identity=tool.directory_identity(source),
            base_index=index,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "root",
        "missing-family",
        "duplicate-family",
        "pointer",
        "path-escape",
        "nonempty-resolutions",
        "old-registry",
        "noncorrection1",
        "aggregate-path",
    ),
)
def test_v4_structure_rejects_root_and_binding_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    manifest = copy.deepcopy(_build_v4(tmp_path, monkeypatch))
    if mutation == "root":
        manifest["stage0_b23"]["root"] = tool.DEFAULT_STAGE0_ROOT.as_posix()  # type: ignore[index]
    elif mutation == "missing-family":
        manifest["stage0_b23"]["refs"].pop()  # type: ignore[index]
    elif mutation == "duplicate-family":
        manifest["stage0_b23"]["refs"][-1] = manifest["stage0_b23"]["refs"][0]  # type: ignore[index]
    elif mutation in {"pointer", "path-escape"}:
        manifest["stage0_b23"]["refs"][0]["path"] = (  # type: ignore[index]
            "../escape/candidate.v2.json"
            if mutation == "path-escape"
            else tool.FRESH_STAGE0_CANDIDATE_PATHS[1].as_posix()
        )
    elif mutation == "nonempty-resolutions":
        manifest["stage0_b23"]["successor_resolutions"] = [{}]  # type: ignore[index]
    elif mutation == "old-registry":
        manifest["stage0_b23"]["current_byte_successor_registry"]["path"] = (  # type: ignore[index]
            tool.CONVERGENCE_CURRENT_BYTE_SUCCESSOR_REGISTRY.as_posix()
        )
    elif mutation == "noncorrection1":
        manifest["stage1"]["remediation_record"]["path"] = (  # type: ignore[index]
            tool.STAGE3_V6_ARTIFACT_REMEDIATION_RECORD.as_posix()
        )
    else:
        manifest["stage1"]["all_lines_aggregate"]["path"] = "wrong/aggregate.json"  # type: ignore[index]

    with pytest.raises(tool.Stage2IntakeError):
        tool.validate_manifest_structure(manifest)


def test_v4_build_rejects_mixed_or_incomplete_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _base = fixture(tmp_path)
    _write_v4_inputs(source)
    common = {
        "source_root": source,
        "stage1_record": Path("stage1-evidence/record.json"),
        "stage1_receipts": (Path("stage1-receipts/r3.log"),),
        "stage1_remediation_record": (
            tool.STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD
        ),
    }
    with pytest.raises(tool.Stage2IntakeError, match="all-lines aggregate"):
        tool.build_manifest(
            **common,
            stage0_paths=tool.FRESH_STAGE0_CANDIDATE_PATHS,
            current_byte_successor_registry=tool.FRESH_CURRENT_BYTE_SUCCESSOR_REGISTRY,
        )
    with pytest.raises(tool.Stage2IntakeError, match="fresh root"):
        tool.build_manifest(
            **common,
            stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
            current_byte_successor_registry=tool.FRESH_CURRENT_BYTE_SUCCESSOR_REGISTRY,
            all_lines_aggregate=tool.ALL_LINES_AGGREGATE,
        )
    with pytest.raises(tool.Stage2IntakeError, match="B23 candidates"):
        tool.build_manifest(
            **common,
            stage0_paths=tool.FRESH_STAGE0_CANDIDATE_PATHS,
            current_byte_successor_registry=tool.CONVERGENCE_CURRENT_BYTE_SUCCESSOR_REGISTRY,
        )
    with pytest.raises(tool.Stage2IntakeError, match="correction1"):
        tool._validate_stage0_and_stage1_v4(
            source,
            tool.FRESH_STAGE0_CANDIDATE_PATHS,
            Path("stage1-evidence/record.json"),
            (Path("stage1-receipts/r3.log"),),
            tool.FRESH_CURRENT_BYTE_SUCCESSOR_REGISTRY,
            tool.STAGE3_V6_ARTIFACT_REMEDIATION_RECORD,
            expected_identity=tool.directory_identity(source),
        )


def test_v4_rejects_candidate_pointer_that_does_not_bind_current_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _base = fixture(tmp_path)
    _write_v4_inputs(source)
    referenced = Path("closure/v4-current.py")
    write(source, referenced.as_posix(), b"current bytes\n")
    candidate = source / tool.FRESH_STAGE0_CANDIDATE_PATHS[0]
    candidate.write_text(
        json.dumps(
            {
                "family": "C2",
                "fragments": [],
                "sources": [
                    {
                        "path": referenced.as_posix(),
                        "file_sha256": "0" * 64,
                        "snapshot_path": "snapshots/current.py",
                    }
                ],
                "tests": [],
            }
        ),
        encoding="utf-8",
    )
    write(
        source,
        tool.FRESH_CURRENT_BYTE_SUCCESSOR_REGISTRY.as_posix(),
        json.dumps(
            {
                "schema": "mrw.current_byte_binding_successors.v4",
                "status": "CURRENT_BYTES_BOUND_BY_ZERO_DELTA_SUCCESSOR_NOT_AUTHORITY",
                "authoritative": False,
            }
        ).encode(),
    )
    monkeypatch.setattr(tool, "_run_repo_local_checker", lambda *args, **kwargs: None)

    with pytest.raises(tool.Stage2IntakeError, match="does not bind current bytes"):
        tool._validate_stage0_and_stage1_v4(
            source,
            tool.FRESH_STAGE0_CANDIDATE_PATHS,
            Path("stage1-evidence/record.json"),
            (Path("stage1-receipts/r3.log"),),
            tool.FRESH_CURRENT_BYTE_SUCCESSOR_REGISTRY,
            tool.STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD,
            expected_identity=tool.directory_identity(source),
        )


def test_all_lines_aggregate_checker_rejects_bad_schema_digest_and_path(
    tmp_path: Path,
) -> None:
    source, _base = fixture(tmp_path)
    producer = (
        b"import json\n"
        b"def check_document(root, document_or_path, *, stage_root=None):\n"
        b"    value = json.loads((root / document_or_path).read_text())\n"
        b"    if value.get('content_digest') == 'f' * 64:\n"
        b"        raise ValueError('CONTENT_DIGEST')\n"
        b"    return {key: value[key] for key in "
        b"('schema', 'status', 'content_digest')}\n"
    )
    write(source, tool.ALL_LINES_AGGREGATE_PRODUCER.as_posix(), producer)

    def write_aggregate(*, schema: str, digest: str) -> None:
        write(
            source,
            tool.ALL_LINES_AGGREGATE.as_posix(),
            json.dumps(
                {
                    "schema": schema,
                    "status": tool.ALL_LINES_AGGREGATE_STATUS,
                    "authoritative": False,
                    "content_digest": digest,
                }
            ).encode(),
        )

    write_aggregate(schema="wrong", digest="1" * 64)
    with pytest.raises(tool.Stage2IntakeError, match="identity drift"):
        tool._validate_all_lines_aggregate(
            source,
            tool.ALL_LINES_AGGREGATE,
            expected_identity=tool.directory_identity(source),
        )
    write_aggregate(schema=tool.ALL_LINES_AGGREGATE_SCHEMA, digest="f" * 64)
    with pytest.raises(tool.Stage2IntakeError, match="CONTENT_DIGEST"):
        tool._validate_all_lines_aggregate(
            source,
            tool.ALL_LINES_AGGREGATE,
            expected_identity=tool.directory_identity(source),
        )
    with pytest.raises(tool.Stage2IntakeError, match="path drift"):
        tool._validate_all_lines_aggregate(
            source,
            Path("wrong/aggregate.json"),
            expected_identity=tool.directory_identity(source),
        )


def test_legacy_v3_remediation_path_preserves_narrow_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _base = fixture(tmp_path)
    registry = Path("stage1-successor-evidence/current-byte-registry.json")
    remediation = tool.DEFAULT_STAGE1_REMEDIATION_RECORD
    write(source, registry.as_posix(), b"{}\n")
    write(source, tool.DEFAULT_CURRENT_BYTE_SUCCESSOR_REGISTRY.as_posix(), b"{}\n")
    write(source, remediation.as_posix(), b"{}\n")
    resolutions = [
        {
            "candidate_path": tool.STAGE0_CANDIDATE_PATHS[0].as_posix(),
            "candidate_sha256": "1" * 64,
            "family": "C2",
            "group": "sources",
            "source_path": "main/backend/app/celery_app.py",
            "predecessor_sha256": "2" * 64,
            "successor_sha256": "3" * 64,
            "registry_successor_id": "successor-1",
            "registry_family": "I1",
        }
    ]

    def validate_v3(*args: object, **kwargs: object):
        return (
            tool.STAGE0_CANDIDATE_PATHS,
            {},
            {Path("stage1-receipts/r3.log")},
            resolutions,
        )

    def forbidden_delta(*args: object, **kwargs: object):
        raise AssertionError

    def forbidden_closure(*args: object, **kwargs: object):
        raise AssertionError

    monkeypatch.setattr(tool, "_validate_stage0_and_stage1_v3", validate_v3)
    monkeypatch.setattr(tool, "DEFAULT_CURRENT_BYTE_SUCCESSOR_REGISTRY", registry)
    monkeypatch.setattr(tool, "DEFAULT_STAGE1_REMEDIATION_RECORD", remediation)
    monkeypatch.setattr(
        tool,
        "source_closure_module",
        type("Stub", (), {"compute_workflow_selector_delta": staticmethod(forbidden_delta)}),
    )
    manifest = tool.build_manifest(
        source_root=source,
        stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
        stage1_record=Path("stage1-evidence/record.json"),
        stage1_receipts=(Path("stage1-receipts/r3.log"),),
        current_byte_successor_registry=registry,
        stage1_remediation_record=remediation,
        additional_upserts=(Path("closure/existing.py"),),
        delete_paths=(Path("obsolete.txt"),),
    )

    assert manifest["schema_version"] == tool.SCHEMA_VERSION_V3
    assert manifest["stage1"]["remediation_record"]["path"] == remediation.as_posix()
    assert manifest["stage1"]["closure"][0]["path"] == "closure/existing.py"


@pytest.mark.parametrize(
    ("remediation", "record_schema"),
    [
        (
            tool.WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_RECORD,
            "mrw.stage1.stage2_v6_intake_remediation_record.v5",
        ),
        (
            tool.STAGE3_V6_ARTIFACT_REMEDIATION_RECORD,
            "mrw.stage1.stage3_v6_artifact_remediation_record.v1",
        ),
        (
            tool.STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD,
            "mrw.stage1.stage3_v6_artifact_remediation_record.v1",
        ),
    ],
)
def test_workflow_equivalent_v3_record_merges_selector_delta(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    remediation: Path,
    record_schema: str,
) -> None:
    source, _base = fixture(tmp_path)
    registry = (
        tool.STAGE3_CURRENT_BYTE_SUCCESSOR_REGISTRY
        if remediation in tool.STAGE3_V6_ARTIFACT_REMEDIATION_RECORDS
        else tool.DEFAULT_CURRENT_BYTE_SUCCESSOR_REGISTRY
    )
    write(source, registry.as_posix(), b"{}\n")
    selected = "closure/workflow-selected.py"
    deleted = "workflow-obsolete.txt"
    write(source, selected, b"workflow selector source\n")
    write(source, deleted, b"workflow obsolete\n")
    write(source, "obsolete.txt", b"obsolete\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "workflow selector inputs")
    (source / deleted).unlink()
    (source / "obsolete.txt").unlink()
    git(source, "update-ref", tool.DEFAULT_BASE_REF, git(source, "rev-parse", "HEAD"))

    write(
        source,
        remediation.as_posix(),
        (
            b'{"schema_version":"' + record_schema.encode("ascii") + b'",'
            b'"authoritative":false}\n'
        ),
    )
    resolutions = [
        {
            "candidate_path": tool.STAGE0_CANDIDATE_PATHS[0].as_posix(),
            "candidate_sha256": "1" * 64,
            "family": "C2",
            "group": "sources",
            "source_path": "main/backend/app/celery_app.py",
            "predecessor_sha256": "2" * 64,
            "successor_sha256": "3" * 64,
            "registry_successor_id": "successor-1",
            "registry_family": "I1",
        }
    ]

    def validate_v3(*args: object, **kwargs: object):
        return (
            tool.STAGE0_CANDIDATE_PATHS,
            {},
            {Path("stage1-receipts/r3.log")},
            resolutions,
        )

    delta_calls: list[tuple[Path, object]] = []
    closure_calls: list[tuple[Path, dict[str, object], object]] = []
    frontend_delta_calls: list[tuple[Path, object]] = []
    frontend_closure_calls: list[tuple[Path, dict[str, object], object]] = []

    def compute_delta(source_root: Path, *, base_index: object):
        delta_calls.append((source_root, base_index))
        return (
            ("UPSERT", registry.as_posix()),
            ("UPSERT", selected),
            ("DELETE", deleted),
        )

    def check_closure(
        source_root: Path,
        manifest: dict[str, object],
        *,
        base_index: object,
    ) -> None:
        closure_calls.append((source_root, manifest, base_index))
        compute_delta(source_root, base_index=base_index)

    def compute_frontend_delta(source_root: Path, *, base_index: object):
        frontend_delta_calls.append((source_root, base_index))
        return ()

    def check_frontend_closure(
        source_root: Path,
        manifest: dict[str, object],
        *,
        base_index: object,
    ) -> None:
        frontend_closure_calls.append((source_root, manifest, base_index))

    monkeypatch.setattr(tool, "_validate_stage0_and_stage1_v3", validate_v3)
    monkeypatch.setattr(
        tool,
        "source_closure_module",
        type(
            "Stub",
            (),
            {
                "compute_workflow_selector_delta": staticmethod(compute_delta),
                "check_workflow_selector_manifest_closure": staticmethod(check_closure),
                "compute_frontend_selector_delta": staticmethod(compute_frontend_delta),
                "check_frontend_selector_manifest_closure": staticmethod(
                    check_frontend_closure
                ),
            },
        ),
    )

    manifest = tool.build_manifest(
        source_root=source,
        stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
        stage1_record=Path("stage1-evidence/record.json"),
        stage1_receipts=(Path("stage1-receipts/r3.log"),),
        current_byte_successor_registry=registry,
        stage1_remediation_record=remediation,
        additional_upserts=(Path("closure/existing.py"),),
        delete_paths=(Path("obsolete.txt"),),
    )
    tool.validate_manifest(manifest)

    entries = {row["path"]: row for row in manifest["entries"]}  # type: ignore[index]
    assert manifest["schema_version"] == tool.SCHEMA_VERSION_V3
    assert manifest["stage1"]["remediation_record"]["path"] == remediation.as_posix()
    assert set(entries) == {
        "closure/existing.py",
        selected,
        "obsolete.txt",
        deleted,
        "stage1-evidence/record.json",
        "stage1-receipts/r3.log",
        registry.as_posix(),
        remediation.as_posix(),
        *(str(path) for path in tool.STAGE0_CANDIDATE_PATHS),
    }
    assert entries[selected]["operation"] == "UPSERT"  # type: ignore[index]
    assert entries[deleted]["operation"] == "DELETE"  # type: ignore[index]
    assert [row["path"] for row in manifest["stage1"]["closure"]] == [  # type: ignore[index]
        "closure/existing.py",
        selected,
    ]
    assert len(delta_calls) == 3
    assert len(closure_calls) == 2
    expected_frontend_calls = (
        1 if remediation in tool.STAGE3_V6_ARTIFACT_REMEDIATION_RECORDS else 0
    )
    assert len(frontend_delta_calls) == expected_frontend_calls
    assert len(frontend_closure_calls) == (
        2 if remediation in tool.STAGE3_V6_ARTIFACT_REMEDIATION_RECORDS else 0
    )
    wrong_registry = copy.deepcopy(manifest)
    wrong_registry["stage0_b23"]["current_byte_successor_registry"]["path"] = (
        tool.DEFAULT_CURRENT_BYTE_SUCCESSOR_REGISTRY.as_posix()
        if remediation in tool.STAGE3_V6_ARTIFACT_REMEDIATION_RECORDS
        else tool.STAGE3_CURRENT_BYTE_SUCCESSOR_REGISTRY.as_posix()
    )
    with pytest.raises(
        tool.Stage2IntakeError,
        match="v3 current-byte successor registry binding drift",
    ):
        tool.validate_manifest_structure(wrong_registry)


@pytest.mark.parametrize("registry", [
    tool.STAGE3_CURRENT_BYTE_SUCCESSOR_REGISTRY,
    tool.CONVERGENCE_CURRENT_BYTE_SUCCESSOR_REGISTRY,
])
def test_stage3_frontend_delta_is_automatically_selected_and_omission_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry: Path,
) -> None:
    source, _base = fixture(tmp_path)
    remediation = tool.STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD
    selected = "frontend/src/stage3-selected.ts"
    write(source, registry.as_posix(), b"{}\n")
    write(
        source,
        remediation.as_posix(),
        b'{"schema_version":"mrw.stage1.stage3_v6_artifact_remediation_record.v1",'
        b'"authoritative":false}\n',
    )
    write(source, selected, b"export const selected = true;\n")
    omission_message = "frontend selector manifest omits required delta"

    def validate_v3(*args: object, **kwargs: object):
        return (
            tool.STAGE0_CANDIDATE_PATHS,
            {},
            {Path("stage1-receipts/r3.log")},
            [
                {
                    "candidate_path": tool.STAGE0_CANDIDATE_PATHS[0].as_posix(),
                    "candidate_sha256": "1" * 64,
                    "family": "C2",
                    "group": "sources",
                    "source_path": "main/backend/app/celery_app.py",
                    "predecessor_sha256": "2" * 64,
                    "successor_sha256": "3" * 64,
                    "registry_successor_id": "successor-1",
                    "registry_family": "I1",
                }
            ],
        )

    def check_frontend(
        source_root: Path,
        manifest: dict[str, object],
        *,
        base_index: object,
    ) -> None:
        del source_root, base_index
        selected_paths = {row["path"] for row in manifest["entries"]}  # type: ignore[index]
        if selected not in selected_paths:
            raise ValueError(omission_message)

    monkeypatch.setattr(tool, "_validate_stage0_and_stage1_v3", validate_v3)
    monkeypatch.setattr(
        tool,
        "source_closure_module",
        type(
            "Stub",
            (),
            {
                "compute_workflow_selector_delta": staticmethod(lambda *args, **kwargs: ()),
                "check_workflow_selector_manifest_closure": staticmethod(
                    lambda *args, **kwargs: None
                ),
                "compute_frontend_selector_delta": staticmethod(
                    lambda *args, **kwargs: (("UPSERT", selected),)
                ),
                "check_frontend_selector_manifest_closure": staticmethod(check_frontend),
            },
        ),
    )

    manifest = tool.build_manifest(
        source_root=source,
        stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
        stage1_record=Path("stage1-evidence/record.json"),
        stage1_receipts=(Path("stage1-receipts/r3.log"),),
        current_byte_successor_registry=registry,
        stage1_remediation_record=remediation,
    )
    entries = {row["path"]: row for row in manifest["entries"]}
    assert entries[selected]["operation"] == "UPSERT"
    assert selected in {row["path"] for row in manifest["stage1"]["closure"]}

    if registry == tool.CONVERGENCE_CURRENT_BYTE_SUCCESSOR_REGISTRY:
        wrong_pair = copy.deepcopy(manifest)
        wrong_pair["stage1"]["remediation_record"]["path"] = (
            tool.STAGE3_V6_ARTIFACT_REMEDIATION_RECORD.as_posix()
        )
        with pytest.raises(
            tool.Stage2IntakeError,
            match="v3 current-byte successor registry binding drift",
        ):
            tool.validate_manifest_structure(wrong_pair)

    wrong_path = copy.deepcopy(manifest)
    wrong_path["stage0_b23"]["current_byte_successor_registry"]["path"] = (
        "arbitrary/current-byte-binding-successors.v3.json"
    )
    # Direct bindings share their row with entries; retain sorting so the
    # negative reaches the registry routing check rather than an earlier gate.
    wrong_path["entries"].sort(key=lambda row: row["path"])
    with pytest.raises(
        tool.Stage2IntakeError,
        match="v3 current-byte successor registry binding drift",
    ):
        tool.validate_manifest_structure(wrong_path)

    omitted = copy.deepcopy(manifest)
    omitted["entries"] = [row for row in omitted["entries"] if row["path"] != selected]
    omitted["stage1"]["closure"] = [
        row for row in omitted["stage1"]["closure"] if row["path"] != selected
    ]
    with pytest.raises(
        tool.Stage2IntakeError,
        match="frontend manifest closure failed: frontend selector manifest omits required delta",
    ):
        tool.validate_manifest(omitted)


@pytest.mark.parametrize(
    ("remediation", "record_schema"),
    [
        (
            tool.WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_RECORD,
            "mrw.stage1.stage2_v6_intake_remediation_record.v5",
        ),
        (
            tool.STAGE3_V6_ARTIFACT_REMEDIATION_RECORD,
            "mrw.stage1.stage3_v6_artifact_remediation_record.v1",
        ),
        (
            tool.STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD,
            "mrw.stage1.stage3_v6_artifact_remediation_record.v1",
        ),
    ],
)
def test_workflow_equivalent_delta_rejects_explicit_operation_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    remediation: Path,
    record_schema: str,
) -> None:
    source, _base = fixture(tmp_path)
    write(
        source,
        remediation.as_posix(),
        (
            b'{"schema_version":"' + record_schema.encode("ascii") + b'",'
            b'"authoritative":false}\n'
        ),
    )

    def validate_v3(*args: object, **kwargs: object):
        return (
            tool.STAGE0_CANDIDATE_PATHS,
            {},
            {Path("stage1-receipts/r3.log")},
            [],
        )

    def compute_delta(*args: object, **kwargs: object):
        return (("DELETE", "closure/existing.py"),)

    monkeypatch.setattr(tool, "_validate_stage0_and_stage1_v3", validate_v3)
    monkeypatch.setattr(
        tool,
        "source_closure_module",
        type(
            "Stub",
            (),
            {"compute_workflow_selector_delta": staticmethod(compute_delta)},
        ),
    )
    with pytest.raises(
        tool.Stage2IntakeError,
        match="delta conflicts with explicit intake selection",
    ):
        tool.build_manifest(
            source_root=source,
            stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
            stage1_record=Path("stage1-evidence/record.json"),
            stage1_receipts=(Path("stage1-receipts/r3.log"),),
            current_byte_successor_registry=Path(
                "stage1-successor-evidence/current-byte-registry.json"
            ),
            stage1_remediation_record=remediation,
            additional_upserts=(Path("closure/existing.py"),),
        )


@pytest.mark.parametrize(
    "remediation",
    [
        tool.WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_RECORD,
        tool.STAGE3_V6_ARTIFACT_REMEDIATION_RECORD,
        tool.STAGE3_V6_ARTIFACT_REMEDIATION_CORRECTION1_RECORD,
    ],
)
def test_cli_keeps_existing_remediation_record_option_for_new_v3_path(
    remediation: Path,
) -> None:
    args = tool.parse_args(
        (
            "--stage0-ref",
            "candidate.json",
            "--stage1-record",
            "stage1.json",
            "--stage1-receipt",
            "receipt.log",
            "--current-byte-successor-registry",
            "registry.json",
            "--stage1-remediation-record",
            remediation.as_posix(),
            "--output",
            "manifest.json",
        )
    )
    assert args.stage1_remediation_record == Path(remediation.as_posix())


def test_workflow_equivalent_delta_accepts_stage0_closure_as_satisfied_upsert() -> None:
    stage0_path = Path("main/backend/app/api/agent_batch.py")
    upserts, deletes = tool._merge_workflow_selector_selection(
        (Path("closure/existing.py"),),
        (),
        (("UPSERT", stage0_path),),
        satisfied_upserts=(stage0_path,),
    )
    assert upserts == (Path("closure/existing.py"),)
    assert deletes == ()

    with pytest.raises(
        tool.Stage2IntakeError,
        match="delta conflicts with satisfied upsert",
    ):
        tool._merge_workflow_selector_selection(
            (),
            (),
            (("DELETE", stage0_path),),
            satisfied_upserts=(stage0_path,),
        )


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        ("app/runtime/tool.json", "forbidden history/cache/runtime"),
        ("app/runtime-cache/data", "forbidden history/cache/runtime"),
        ("main/app/secrets/token.json", "secret directory"),
        ("credentials/client.json", "secret directory"),
        ("main/backend/.env", "live environment file"),
        ("main/backend/.env.local", "live environment file"),
        ("main/backend/.env.production", "live environment file"),
        ("deploy/private.key", "secret file"),
        ("deploy/certificate.pem", "secret file"),
        ("deploy/identity.p12", "secret file"),
        ("deploy/identity.pfx", "secret file"),
        ("keys/id_rsa", "secret file"),
        ("keys/id_ed25519", "secret file"),
        (".netrc", "secret file"),
        (".npmrc", "secret file"),
        (".pypirc", "secret file"),
        ("service.token", "secret file"),
        ("cache.db", "runtime or cache file"),
        ("server.pid", "runtime or cache file"),
    ],
)
def test_rejects_exact_sensitive_and_runtime_paths(relative: str, message: str) -> None:
    with pytest.raises(tool.Stage2IntakeError, match=message):
        tool.safe_relative(relative)


@pytest.mark.parametrize(
    "base_ref",
    [
        "main",
        "refs/heads/main",
        "refs/remotes/origin/master",
        "refs/remotes/origin/main ",
        "refs/remotes/upstream/main",
    ],
)
def test_rejects_non_canonical_base_refs(base_ref: str, tmp_path: Path) -> None:
    with pytest.raises(tool.Stage2IntakeError, match="base_ref must be exactly"):
        build(tmp_path, base_ref=base_ref)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        pytest.param(
            lambda manifest: manifest["source"].update(porcelain_sha256=None),
            "porcelain status digest drift",
            id="source-porcelain-not-str",
        ),
        pytest.param(
            lambda manifest: manifest["source"].update(head=[]),
            "source identity fields must be non-empty",
            id="source-head-not-str",
        ),
        pytest.param(
            lambda manifest: manifest["entries"][0].update(mode=None),
            "entry contract drift",
            id="entry-mode-not-str",
        ),
        pytest.param(
            lambda manifest: manifest["entries"][0].update(base_mode="100644", base_blob=None),
            "entry contract drift",
            id="upsert-nonzero-base-mode-invalid-base-blob",
        ),
        pytest.param(
            lambda manifest: manifest["entries"][-1].update(base_blob=40),
            "entry contract drift",
            id="delete-base-blob-not-str",
        ),
        pytest.param(
            break_direct_binding_path,
            "Stage0 or Stage1 binding",
            id="binding-path-not-str",
        ),
    ],
)
def test_rejects_malformed_manifest_types_without_runtime_errors(
    mutate: object,
    message: str,
    tmp_path: Path,
) -> None:
    manifest = build(tmp_path)
    drifted = copy.deepcopy(manifest)
    assert callable(mutate)
    mutate(drifted)
    with pytest.raises(tool.Stage2IntakeError, match=message):
        tool.validate_manifest_structure(drifted)


def test_validator_rejects_unchanged_closure_path_alias_before_materialization(
    tmp_path: Path,
) -> None:
    manifest = build(tmp_path)
    drifted = copy.deepcopy(manifest)
    closure_binding = drifted["stage1"]["closure"][0]  # type: ignore[index]
    canonical_path = closure_binding["path"]
    entry_index = next(
        index
        for index, row in enumerate(drifted["entries"])
        if row["path"] == canonical_path
    )
    alias = f"{canonical_path}//"
    closure_binding["path"] = alias
    drifted["entries"][entry_index]["path"] = alias

    with pytest.raises(tool.Stage2IntakeError, match="not a canonical POSIX path"):
        tool.validate_manifest_structure(drifted)


def test_cli_returns_structured_failure_for_malformed_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = build(tmp_path / "fixture")
    output = tmp_path / "malformed-intake.json"
    drifted = copy.deepcopy(manifest)
    drifted["source"]["porcelain_sha256"] = None  # type: ignore[index]
    monkeypatch.setattr(tool, "build_manifest", lambda **kwargs: drifted)
    argv = [
        "--stage0-ref",
        "ignored",
        "--stage1-record",
        "ignored",
        "--stage1-receipt",
        "ignored",
        "--output",
        str(output),
    ]

    assert tool.main(argv) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["findings"][0]["status"] == "FAIL"
    assert report["findings"][0]["summary"] == "porcelain status digest drift"
    assert not output.exists()


def test_rejects_remote_name_not_paired_with_origin_main(tmp_path: Path) -> None:
    source, _ = fixture(tmp_path)
    git(source, "remote", "add", "upstream", "https://example.test/upstream.git")
    with pytest.raises(tool.Stage2IntakeError, match="remote_name must be exactly origin"):
        tool.build_manifest(
            source_root=source,
            stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
            stage1_record=Path("stage1-evidence/record.json"),
            stage1_receipts=(Path("stage1-receipts/r3.log"),),
            remote_name="upstream",
        )
    manifest = build(tmp_path / "origin")
    drifted = {**manifest, "source": {**manifest["source"], "remote_name": "upstream"}}  # type: ignore[arg-type]
    with pytest.raises(tool.Stage2IntakeError, match="remote_name must be exactly origin"):
        tool.validate_manifest(drifted)


def test_validator_rejects_base_ref_projection_drift(tmp_path: Path) -> None:
    manifest = build(tmp_path)
    assert isinstance(manifest["source"], dict)  # type: ignore[index]
    drifted = {**manifest, "source": {**manifest["source"], "base_ref": "refs/heads/main"}}  # type: ignore[index]
    with pytest.raises(tool.Stage2IntakeError, match="base_ref must be exactly"):
        tool.validate_manifest(drifted)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("base_mode", "100755"),
        ("base_blob", "0" * 40),
        ("sha256", "0" * 64),
        ("blob", "0" * 40),
        ("mode", "100755"),
    ),
)
def test_validator_rejects_non_core_upsert_exact_projection_drift(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    manifest = build(tmp_path)
    drifted = copy.deepcopy(manifest)
    row = next(
        entry
        for entry in drifted["entries"]  # type: ignore[index]
        if entry["path"] == "closure/existing.py"
    )
    row[field] = value

    with pytest.raises(tool.Stage2IntakeError, match="manifest entry exact projection drift"):
        tool.validate_manifest(drifted)


def test_validator_rejects_non_core_upsert_live_bytes_drift(tmp_path: Path) -> None:
    manifest = build(tmp_path)
    source = Path(manifest["source"]["checkout"])  # type: ignore[index]
    write(source, "closure/existing.py", b"drifted after manifest\n")

    with pytest.raises(tool.Stage2IntakeError, match="manifest entry exact projection drift"):
        tool.validate_manifest(manifest)


def test_write_create_only_rejects_invalid_non_core_upsert_before_output(
    tmp_path: Path,
) -> None:
    manifest = build(tmp_path / "fixture")
    row = next(
        entry
        for entry in manifest["entries"]  # type: ignore[index]
        if entry["path"] == "closure/existing.py"
    )
    row["sha256"] = "0" * 64
    output = tmp_path / "invalid-intake.json"

    with pytest.raises(tool.Stage2IntakeError, match="manifest entry exact projection drift"):
        tool.write_create_only(output, manifest)

    assert not output.exists()


def test_validator_rejects_delete_base_precondition_drift(tmp_path: Path) -> None:
    manifest = build(tmp_path)
    drifted = copy.deepcopy(manifest)
    row = next(
        entry
        for entry in drifted["entries"]  # type: ignore[index]
        if entry["path"] == "obsolete.txt"
    )
    row["base_blob"] = "0" * 40

    with pytest.raises(tool.Stage2IntakeError, match="manifest entry exact projection drift"):
        tool.validate_manifest(drifted)


def test_validator_rejects_delete_path_reappearing_after_manifest(tmp_path: Path) -> None:
    manifest = build(tmp_path)
    source = Path(manifest["source"]["checkout"])  # type: ignore[index]
    write(source, "obsolete.txt", b"reappeared\n")

    with pytest.raises(tool.Stage2IntakeError, match="delete source still exists"):
        tool.validate_manifest(manifest)


def test_validator_fails_closed_when_projected_mrw_package_is_missing(tmp_path: Path) -> None:
    manifest = build(tmp_path)
    source = Path(manifest["source"]["checkout"])  # type: ignore[index]
    entries = list(manifest["entries"])  # type: ignore[index]
    for relative in (
        "src/mrw_functorial_kit/core/w07_semantics.py",
        "src/mrw_functorial_kit/core/agent_service_semantics.py",
    ):
        payload = b"value = 1\n"
        write(source, relative, payload)
        entries.append(
            {
                "path": relative,
                "operation": "UPSERT",
                "mode": "100644",
                "sha256": tool.sha256_bytes(payload),
                "blob": tool.git_blob_oid(payload),
                "base_mode": "000000",
                "base_blob": "",
            }
        )
    entries.sort(key=lambda row: row["path"])
    projected = {**manifest, "entries": entries}

    with pytest.raises(tool.Stage2IntakeError, match="core package is missing"):
        tool.validate_manifest(projected)


def test_cli_rejects_non_canonical_base_ref_before_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source, _ = fixture(tmp_path)
    output = tmp_path / "intake.json"
    argv = ["--source-root", str(source)]
    for path in tool.STAGE0_CANDIDATE_PATHS:
        argv.extend(("--stage0-ref", path.as_posix()))
    argv.extend(
        (
            "--stage1-record",
            "stage1-evidence/record.json",
            "--stage1-receipt",
            "stage1-receipts/r3.log",
            "--upsert",
            "closure/existing.py",
            "--delete",
            "obsolete.txt",
            "--output",
            str(output),
            "--base-ref",
            "refs/heads/main",
        )
    )

    assert tool.main(argv) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["findings"][0]["summary"].startswith("base_ref must be exactly")
    assert not output.exists()


def test_rejects_case_collision_and_bad_source_types(tmp_path: Path) -> None:
    with pytest.raises(tool.Stage2IntakeError, match="case or NFC path collision"):
        tool.assert_no_path_collisions((Path("A.txt"), Path("a.txt")))

    source, _ = fixture(tmp_path)
    fifo = source / "closure/fifo"
    fifo.parent.mkdir(parents=True, exist_ok=True)
    os.mkfifo(fifo)
    assert stat.S_ISFIFO(fifo.lstat().st_mode)
    with pytest.raises(tool.Stage2IntakeError, match="unsupported source file type"):
        tool._entry(source, Path("closure/fifo"), git(source, "rev-parse", "HEAD~1"))


def test_regular_file_swap_to_fifo_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, _ = fixture(tmp_path)
    relative = Path("closure/race.py")
    victim = write(source, relative.as_posix(), b"regular\n")
    original_open = os.open
    swapped = False

    def swap_before_open(
        path: os.PathLike[str] | str,
        flags: int,
        *args: object,
        **kwargs: object,
    ) -> int:
        nonlocal swapped
        if Path(path).name == victim.name and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            victim.unlink()
            os.mkfifo(victim)
        return original_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", swap_before_open)
    with pytest.raises(tool.Stage2IntakeError, match="must be a regular file"):
        tool._read_regular_bytes(source, relative, label="race probe")


def test_parent_directory_swap_to_external_symlink_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, _ = fixture(tmp_path)
    relative = Path("closure/race-parent.py")
    victim = write(source, relative.as_posix(), b"inside\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    write(outside, victim.name, b"outside\n")
    original_parent = victim.parent.with_name("closure-original")
    original_open = os.open
    swapped = False

    def swap_parent_before_final_open(
        path: os.PathLike[str] | str,
        flags: int,
        *args: object,
        **kwargs: object,
    ) -> int:
        nonlocal swapped
        if Path(path).name == victim.name and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            victim.parent.rename(original_parent)
            victim.parent.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", swap_parent_before_final_open)
    with pytest.raises(tool.Stage2IntakeError, match="changed during read"):
        tool._read_regular_bytes(source, relative, label="parent race probe")


def test_stage1_record_swap_to_fifo_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, _ = fixture(tmp_path)
    record = source / "stage1-evidence/record.json"
    original_open = os.open
    swapped = False

    def swap_record_before_open(
        path: os.PathLike[str] | str,
        flags: int,
        *args: object,
        **kwargs: object,
    ) -> int:
        nonlocal swapped
        if Path(path).name == record.name and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            record.unlink()
            os.mkfifo(record)
        return original_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", swap_record_before_open)
    with pytest.raises(tool.Stage2IntakeError, match="Stage1 record.*regular file"):
        tool._validate_stage0_and_stage1(
            source,
            tool.STAGE0_CANDIDATE_PATHS,
            Path("stage1-evidence/record.json"),
            (Path("stage1-receipts/r3.log"),),
            expected_identity=tool.directory_identity(source),
        )


def test_git_environment_cannot_redirect_source_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, _source_base = fixture(tmp_path / "source-fixture")
    other, _other_base = fixture(tmp_path / "other-fixture")
    source_head = git(source, "rev-parse", "HEAD")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))

    assert tool.git_text(source, "rev-parse", "HEAD") == source_head


def test_git_environment_clears_config_rewrites_for_remote(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, _ = fixture(tmp_path)
    original_remote = "https://example.test/source.git"
    malicious_config = tmp_path / "global-git-config"
    malicious_config.write_text(
        '[url "https://evil.test/"]\n'
        "\tinsteadOf = https://example.test/\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(malicious_config))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "url.https://example.test/.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://evil.test/")

    identity = tool._source_identity(source, tool.DEFAULT_REMOTE_NAME, tool.DEFAULT_BASE_REF)

    assert identity["remote"] == original_remote  # type: ignore[index]


def test_home_and_xdg_gitconfigs_cannot_affect_git_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, base = fixture(tmp_path / "fixture")
    original_remote = "https://example.test/source.git"
    (source / ".git/info/attributes").write_text(
        "closure/existing.py filter=poison\n",
        encoding="utf-8",
    )

    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    hook_directory = tmp_path / "hooks"
    home.mkdir()
    (xdg / "git").mkdir(parents=True)
    hook_directory.mkdir()
    (home / ".gitconfig").write_text(
        '[url "https://home-evil.test/"]\n'
        "\tinsteadOf = https://example.test/\n"
        "[core]\n"
        f"\thooksPath = {hook_directory}\n",
        encoding="utf-8",
    )
    (xdg / "git/config").write_text(
        '[filter "poison"]\n'
        "\tclean = false\n"
        "\trequired = true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))

    identity = tool._source_identity(source, tool.DEFAULT_REMOTE_NAME, tool.DEFAULT_BASE_REF)
    base_index = tool.BaseTreeIndex.from_repo(source, base, runner=tool.git_output)
    isolated_env = tool._git_env()

    assert identity["remote"] == original_remote
    assert identity["source_clean"] is True
    assert base_index.lookup("obsolete.txt") is not None
    assert isolated_env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert isolated_env["GIT_CONFIG_GLOBAL"] == os.devnull


def test_local_fsmonitor_is_disabled_for_git_reads(tmp_path: Path) -> None:
    source, _ = fixture(tmp_path / "fixture")
    marker = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "fsmonitor-hook"
    hook.write_text(
        f"#!/bin/sh\ntouch '{marker}'\nexit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    git(source, "config", "core.fsmonitor", str(hook))

    identity = tool._source_identity(source, tool.DEFAULT_REMOTE_NAME, tool.DEFAULT_BASE_REF)

    assert identity["source_clean"] is True
    assert not marker.exists()


def test_replace_refs_cannot_substitute_source_or_base_objects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, base = fixture(tmp_path / "fixture")
    head = git(source, "rev-parse", "HEAD")
    head_tree = git(source, "rev-parse", "HEAD^{tree}")
    write(source, "closure/existing.py", b"replacement\n")
    git(source, "add", "closure/existing.py")
    git(source, "commit", "-m", "replacement")
    replacement_commit = git(source, "rev-parse", "HEAD")
    git(source, "checkout", "--detach", head)
    git(source, "replace", head, replacement_commit)
    git(source, "replace", base, replacement_commit)
    monkeypatch.delenv("GIT_NO_REPLACE_OBJECTS", raising=False)
    assert git(source, "rev-parse", "HEAD^{tree}") != head_tree
    assert git(source, "status", "--porcelain=v1") != ""
    assert "obsolete.txt" not in git(
        source, "ls-tree", "-r", "--name-only", base
    ).splitlines()

    identity = tool._source_identity(source, tool.DEFAULT_REMOTE_NAME, tool.DEFAULT_BASE_REF)
    base_index = tool.BaseTreeIndex.from_repo(source, base, runner=tool.git_output)
    observed_tree = tool.git_text(source, "rev-parse", "HEAD^{tree}")
    isolated_env = tool._git_env()

    assert identity["head"] == head
    assert identity["source_clean"] is True
    assert observed_tree == head_tree
    assert base_index.lookup("obsolete.txt") is not None
    assert isolated_env["GIT_NO_REPLACE_OBJECTS"] == "1"


@pytest.mark.parametrize("kind", ["file", "directory", "dangling-symlink"])
def test_source_identity_rejects_any_info_grafts_entry(kind: str, tmp_path: Path) -> None:
    source, _ = fixture(tmp_path / "fixture")
    common_dir = Path(git(source, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = source / common_dir
    grafts = common_dir / "info/grafts"
    grafts.parent.mkdir(parents=True, exist_ok=True)
    if kind == "file":
        grafts.write_text("0" * 40 + " " + "1" * 40 + "\n", encoding="ascii")
    elif kind == "directory":
        grafts.mkdir()
    else:
        grafts.symlink_to("missing-grafts-target")

    with pytest.raises(tool.Stage2IntakeError, match="info/grafts is forbidden"):
        tool._source_identity(source, tool.DEFAULT_REMOTE_NAME, tool.DEFAULT_BASE_REF)


def test_source_identity_rejects_repository_subdirectory(tmp_path: Path) -> None:
    source, _ = fixture(tmp_path)
    subdirectory = source / "nested"
    subdirectory.mkdir()
    with pytest.raises(tool.Stage2IntakeError, match="git checkout top-level"):
        tool._source_identity(subdirectory, tool.DEFAULT_REMOTE_NAME, tool.DEFAULT_BASE_REF)


def test_rejects_symlink_escape_and_accepts_unrelated_dirty_source(tmp_path: Path) -> None:
    source, _ = fixture(tmp_path)
    escape = source / "closure/escape"
    escape.symlink_to("../../outside.txt")
    with pytest.raises(tool.Stage2IntakeError, match="symlink escapes checkout"):
        tool._entry(source, Path("closure/escape"), git(source, "rev-parse", "HEAD~1"))

    with pytest.raises(tool.Stage2IntakeError, match="delete path is absent from base"):
        tool._delete_entry(source, Path("not-in-base.txt"), git(source, "rev-parse", "HEAD~1"))

    write(source, "dirty.txt", b"dirty\n")
    manifest = tool.build_manifest(
        source_root=source,
        stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
        stage1_record=Path("stage1-evidence/record.json"),
        stage1_receipts=(Path("stage1-receipts/r3.log"),),
    )
    assert manifest["source"]["source_clean"] is False
    assert "dirty.txt" not in {row["path"] for row in manifest["entries"]}  # type: ignore[index]


def test_dirty_source_audit_projection_and_unselected_file(tmp_path: Path) -> None:
    source, _ = fixture(tmp_path)
    write(source, "unselected-dirty.txt", b"dirty\n")
    manifest = tool.build_manifest(
        source_root=source,
        stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
        stage1_record=Path("stage1-evidence/record.json"),
        stage1_receipts=(Path("stage1-receipts/r3.log"),),
    )
    source_meta = manifest["source"]
    assert source_meta["selection_boundary"] == "manifest_entries_only"  # type: ignore[index]
    assert source_meta["porcelain_sha256"]  # type: ignore[index]


@pytest.mark.parametrize(
    "stage0_paths",
    [
        lambda: tool.STAGE0_CANDIDATE_PATHS[:-1],
        lambda: (*tool.STAGE0_CANDIDATE_PATHS[:-1], Path("evil-stage-b23/candidates/I1/candidate.v2.json")),
    ],
)
def test_rejects_missing_or_evil_stage0_family(stage0_paths, tmp_path: Path) -> None:
    with pytest.raises(tool.Stage2IntakeError, match="exactly C2-C9/I1"):
        build(tmp_path, stage0_paths=stage0_paths())


def test_rejects_validator_family_status_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        tool.stage_family_fragment_rebind,
        "check_candidate",
        lambda path, *, repo_root, history_only: {
            "family": "C2",
            "status": "WRONG",
        },
    )
    with pytest.raises(tool.Stage2IntakeError, match="family mismatch|status mismatch"):
        build(tmp_path)


def test_rejects_stage1_receipt_mismatch_and_fake_stage1(tmp_path: Path) -> None:
    source, _ = fixture(tmp_path)
    with pytest.raises(tool.Stage2IntakeError, match="do not match record.commands"):
        tool.build_manifest(
            source_root=source,
            stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
            stage1_record=Path("stage1-evidence/record.json"),
            stage1_receipts=(Path("missing-receipt.log"),),
        )
    (source / "stage1-evidence/record.json").write_text(
        '{"status":"AUTHORITY","authoritative":true,"commands":{}}', encoding="utf-8"
    )
    with pytest.raises(tool.Stage2IntakeError, match="status or authority"):
        tool.build_manifest(
            source_root=source,
            stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
            stage1_record=Path("stage1-evidence/record.json"),
            stage1_receipts=(Path("stage1-receipts/r3.log"),),
        )


def test_rejects_stage0_closure_scope_and_direct_masquerade(tmp_path: Path) -> None:
    with pytest.raises(tool.Stage2IntakeError, match="overlap a direct Stage0 ref"):
        build(
            tmp_path / "direct",
            stage0_closure_upserts=(tool.STAGE0_CANDIDATE_PATHS[0],),
            additional_upserts=(),
        )

    source, _ = fixture(tmp_path / "scope")
    with pytest.raises(tool.Stage2IntakeError, match="extra=.*note.txt"):
        tool.build_manifest(
            source_root=source,
            stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
            stage0_closure_upserts=(tool.DEFAULT_STAGE0_ROOT / "notes" / "note.txt",),
            stage1_record=Path("stage1-evidence/record.json"),
            stage1_receipts=(Path("stage1-receipts/r3.log"),),
        )
    snapshot = tool.DEFAULT_STAGE0_ROOT / "snapshots" / ("a" * 64)
    with pytest.raises(tool.Stage2IntakeError, match="cannot masquerade as Stage0"):
        tool.build_manifest(
            source_root=source,
            stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
            stage1_record=Path("stage1-evidence/record.json"),
            stage1_receipts=(Path("stage1-receipts/r3.log"),),
            additional_upserts=(snapshot,),
        )
    symlink = tool.STAGE0_CANDIDATE_PATHS[0].parent / "snapshots/link"
    linked = Path("closure/linked.py")
    write(source, linked, b"linked\n")
    (source / tool.STAGE0_CANDIDATE_PATHS[0]).write_text(
        json.dumps({"sources": [{"path": "closure/linked.py", "snapshot_path": "snapshots/link"}]}),
        encoding="utf-8",
    )
    (source / symlink).parent.mkdir(parents=True, exist_ok=True)
    os.symlink(source / "closure/existing.py", source / symlink)
    with pytest.raises(tool.Stage2IntakeError, match="opened safely|regular file|extra=.*snapshots/link"):
        tool.build_manifest(
            source_root=source,
            stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
            stage0_closure_upserts=(linked, symlink),
            stage1_record=Path("stage1-evidence/record.json"),
            stage1_receipts=(Path("stage1-receipts/r3.log"),),
        )


def test_validator_rejects_closure_duplicates_crossing_and_missing_entries(tmp_path: Path) -> None:
    source, _ = fixture(tmp_path)
    referenced = Path("closure/referenced.py")
    snapshot = tool.STAGE0_CANDIDATE_PATHS[0].parent / "snapshots/referenced"
    write(source, referenced, b"changed\n")
    write(source, snapshot, b"snapshot\n")
    (source / tool.STAGE0_CANDIDATE_PATHS[0]).write_text(
        json.dumps({"sources": [{"path": referenced.as_posix(), "snapshot_path": "snapshots/referenced"}]}),
        encoding="utf-8",
    )
    manifest = tool.build_manifest(
            source_root=source,
            stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
            stage0_closure_upserts=(referenced, snapshot),
        stage1_record=Path("stage1-evidence/record.json"),
        stage1_receipts=(Path("stage1-receipts/r3.log"),),
    )
    frozen_binding = manifest["stage0_b23"]["closure"][0]  # type: ignore[index]
    duplicate = {
        **manifest,
        "stage0_b23": {
            **manifest["stage0_b23"],  # type: ignore[arg-type]
            "closure": [frozen_binding, frozen_binding],
        },
    }
    with pytest.raises(tool.Stage2IntakeError, match="Stage0 closure paths contain duplicates"):
        tool.validate_manifest(duplicate)

    crossing = {
        **manifest,
        "stage1": {
            **manifest["stage1"],  # type: ignore[arg-type]
            "closure": [frozen_binding],
        },
    }
    with pytest.raises(tool.Stage2IntakeError, match="closures overlap"):
        tool.validate_manifest(crossing)

    missing_direct = {
        **manifest,
        "stage0_b23": {
            **manifest["stage0_b23"],  # type: ignore[arg-type]
            "refs": list(manifest["stage0_b23"]["refs"])[:-1],  # type: ignore[index]
        },
    }
    with pytest.raises(tool.Stage2IntakeError, match="exactly nine candidates"):
        tool.validate_manifest(missing_direct)

    absent = {
        **frozen_binding,
        "path": "closure/not-referenced.py",
    }
    drifted = {
        **manifest,
        "stage0_b23": {
            **manifest["stage0_b23"],  # type: ignore[arg-type]
            "closure": [absent],
        },
    }
    with pytest.raises(tool.Stage2IntakeError, match="does not match entries|must exactly equal"):
        tool.validate_manifest(drifted)


def test_output_must_be_outside_source_and_additional_files_regular(tmp_path: Path) -> None:
    manifest = build(tmp_path)
    source = Path(manifest["source"]["checkout"])  # type: ignore[index]
    with pytest.raises(tool.Stage2IntakeError, match="outside source checkout"):
        tool.write_create_only(source / "intake.json", manifest)
    with pytest.raises(tool.Stage2IntakeError, match="regular file"):
        build(tmp_path / "symlink", additional_upserts=(Path("closure/link"),))


def test_output_parent_swap_cannot_redirect_write_into_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = build(tmp_path / "fixture")
    source = Path(manifest["source"]["checkout"])  # type: ignore[index]
    output_parent = tmp_path / "receipt"
    output_parent.mkdir()
    moved_parent = tmp_path / "receipt-original"
    output = output_parent / "intake.json"
    original_write = tool.write_create_only_bytes

    def redirect_before_write(path: Path, payload: bytes, identities: object) -> Path:
        output_parent.rename(moved_parent)
        output_parent.symlink_to(source, target_is_directory=True)
        return original_write(path, payload, identities)

    monkeypatch.setattr(tool, "write_create_only_bytes", redirect_before_write)
    with pytest.raises(tool.Stage2IntakeError, match="unsafe"):
        tool.write_create_only(output, manifest)

    assert not (source / output.name).exists()
    assert not (moved_parent / output.name).exists()


def test_source_root_rename_to_external_directory_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, _ = fixture(tmp_path / "fixture")
    original_identity = tool._source_identity

    def capture_and_swap(
        source_root: Path,
        remote_name: str,
        base_ref: str,
    ) -> dict[str, object]:
        result = original_identity(source_root, remote_name, base_ref)
        external = source_root.parent / "external"
        moved = source_root.parent / "source-original"
        source_root.rename(moved)
        shutil.copytree(moved, external, symlinks=True)
        external.rename(source_root)
        return result

    monkeypatch.setattr(tool, "_source_identity", capture_and_swap)
    with pytest.raises(
        tool.Stage2IntakeError,
        match="source checkout identity changed",
    ):
        tool.build_manifest(
            source_root=source,
            stage0_paths=tool.STAGE0_CANDIDATE_PATHS,
            stage1_record=Path("stage1-evidence/record.json"),
            stage1_receipts=(Path("stage1-receipts/r3.log"),),
        )

    assert not (Path(source).parent / "external/intake.json").exists()


def test_delete_entry_rejects_same_form_root_replacement(
    tmp_path: Path,
) -> None:
    source, _ = fixture(tmp_path / "fixture")
    relative = Path("resurrected.txt")
    expected_identity = tool.directory_identity(source)
    moved = source.parent / "source-original"
    replacement = source.parent / "source-replacement"
    source.rename(moved)
    shutil.copytree(moved, replacement, symlinks=True)
    write(replacement, relative.as_posix(), b"resurrected\n")
    replacement.rename(source)

    with pytest.raises(
        tool.Stage2IntakeError,
        match="source checkout identity changed",
    ):
        tool._delete_entry(
            source,
            relative,
            git(moved, "rev-parse", "HEAD"),
            expected_identity=expected_identity,
        )


def test_stable_upstream_context_reads_original_fd_and_restores(tmp_path: Path) -> None:
    source, _ = fixture(tmp_path / "fixture")
    payload_path = Path("validator/input.txt")
    write(source, payload_path.as_posix(), b"stable payload\n")
    migration_dir = Path("main/backend/app/migrations/versions")
    write(source, (migration_dir / "0001.py").as_posix(), b"# migration\n")
    write(
        source,
        (tool.generate_stage1_production_contract_record.MIGRATION_MERGE_REL).as_posix(),
        b"# merge\n",
    )
    write(source, "main/backend/app/api/routes.py", b"# api\n")
    expected_identity = tool.directory_identity(source)
    original_root_opener = tool.stage_family_fragment_rebind._open_root
    original_stage1_read = tool.generate_stage1_production_contract_record._read
    original_migration_rels = tool.generate_stage1_production_contract_record._migration_rels
    original_api_rels = tool.generate_stage1_production_contract_record._api_rels

    with tool._stable_upstream_validators(source, expected_identity) as usage:
        assert usage == {
            "root_opener": False,
            "stage1_reader": False,
            "migration_lister": False,
            "api_lister": False,
        }
        assert tool.stage_family_fragment_rebind._read_file(
            source,
            payload_path,
            label="validator input",
        )[0] == b"stable payload\n"
        assert tool.generate_stage1_production_contract_record._read(source, payload_path) == b"stable payload\n"
        assert tool.generate_stage1_production_contract_record._migration_rels(source)
        assert tool.generate_stage1_production_contract_record._api_rels(source)
        assert all(usage.values())

        moved = source.parent / "source-original"
        source.rename(moved)
        source.symlink_to(moved, target_is_directory=True)
        assert tool.stage_family_fragment_rebind._read_file(
            source,
            payload_path,
            label="validator input",
        )[0] == b"stable payload\n"
        assert tool.generate_stage1_production_contract_record._read(source, payload_path) == b"stable payload\n"
        assert tool.generate_stage1_production_contract_record._migration_rels(source)
        assert tool.generate_stage1_production_contract_record._api_rels(source)

    source.unlink()
    moved.rename(source)
    assert tool.directory_identity(source) == expected_identity
    assert tool.stage_family_fragment_rebind._open_root is original_root_opener
    assert tool.generate_stage1_production_contract_record._read is original_stage1_read
    assert tool.generate_stage1_production_contract_record._migration_rels is original_migration_rels
    assert tool.generate_stage1_production_contract_record._api_rels is original_api_rels


def test_source_bytes_rejects_same_mode_file_swap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, _ = fixture(tmp_path / "fixture")
    relative = Path("same-mode/input")
    target = source / relative
    write(source, relative.as_posix(), b"same bytes\n")
    original_read = tool._read_regular_bytes

    def swap_same_mode_before_read(*args: object, **kwargs: object) -> tuple[bytes, os.stat_result]:
        target.unlink()
        target.parent.chmod(0o755)
        target.write_bytes(b"same bytes\n")
        target.chmod(0o644)
        return original_read(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(tool, "_read_regular_bytes", swap_same_mode_before_read)
    with pytest.raises(tool.Stage2IntakeError, match="source path changed during read"):
        tool._source_bytes(source, relative, stat.S_IFREG | 0o644)


def test_regular_reader_rejects_same_inode_file_after_parent_swap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    relative = Path("directory/input")
    parent = root / relative.parent
    parent.mkdir(parents=True)
    target = parent / relative.name
    target.write_bytes(b"payload\n")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    os.link(target, replacement / relative.name)
    moved = tmp_path / "directory-original"
    original_read = os.read
    swapped = False

    def swap_parent_after_first_read(fd: int, size: int) -> bytes:
        nonlocal swapped
        chunk = original_read(fd, size)
        if not swapped:
            swapped = True
            parent.rename(moved)
            replacement.rename(parent)
        return chunk

    monkeypatch.setattr(os, "read", swap_parent_after_first_read)
    with pytest.raises(tool.Stage2IntakeError, match="parent changed during read"):
        tool._read_regular_bytes(root, relative, label="swapped parent")


def test_regular_reader_failed_final_open_does_not_leak_descriptors(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    symlink_target = root / "target"
    symlink_target.write_text("payload\n", encoding="utf-8")

    def descriptor_count() -> int:
        for root_path in ("/dev/fd", "/proc/self/fd"):
            path = Path(root_path)
            if path.exists():
                valid = 0
                for item in path.iterdir():
                    if not item.name.isdigit():
                        continue
                    try:
                        os.fstat(int(item.name))
                    except OSError:
                        continue
                    valid += 1
                return valid
        pytest.skip("no /dev/fd or /proc/self/fd descriptor view")

    missing = Path("missing")
    linked = Path("race-link")
    before = descriptor_count()
    for index in range(192):
        relative = missing if index % 2 == 0 else linked
        if index % 2:
            (root / linked).symlink_to(symlink_target)
        with pytest.raises(
            tool.Stage2IntakeError,
            match="cannot be opened safely|changed during read",
        ):
            tool._read_regular_bytes(root, relative, label="failed final open")
        if (root / linked).is_symlink():
            (root / linked).unlink()

    after = descriptor_count()
    assert after <= before + 4


def test_open_parent_identity_fstat_failure_does_not_leak_descriptors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    root.mkdir()

    def descriptor_count() -> int:
        for root_path in ("/dev/fd", "/proc/self/fd"):
            path = Path(root_path)
            if path.exists():
                valid = 0
                for item in path.iterdir():
                    if not item.name.isdigit():
                        continue
                    try:
                        os.fstat(int(item.name))
                    except OSError:
                        continue
                    valid += 1
                return valid
        pytest.skip("no /dev/fd or /proc/self/fd descriptor view")

    original_fstat = os.fstat
    fstat_calls = 0

    def fail_second_fstat(fd: int) -> os.stat_result:
        nonlocal fstat_calls
        fstat_calls += 1
        if fstat_calls % 2 == 0:
            raise OSError("injected fstat failure")  # noqa: TRY003
        return original_fstat(fd)

    before = descriptor_count()
    with monkeypatch.context() as patched:
        patched.setattr(tool.os, "fstat", fail_second_fstat)
        for _ in range(200):
            with pytest.raises(OSError, match="injected fstat failure"):
                tool._open_parent_dirfd_with_identity(root, Path("input"))

    assert fstat_calls == 400
    assert descriptor_count() <= before + 4
