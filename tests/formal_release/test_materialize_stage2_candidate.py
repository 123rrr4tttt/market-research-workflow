from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.formal_release import stage2_candidate_intake as canonical_intake
from scripts.formal_release.source_closure import (
    CORE_ROOT,
    REQUIRED_CONSUMERS,
    REQUIRED_CORE_MODULES,
)


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/formal_release/materialize_stage2_candidate.py"
INTAKE_SCRIPT = ROOT / "scripts/formal_release/stage2_candidate_intake.py"
SPEC = importlib.util.spec_from_file_location("materialize_stage2_candidate", SCRIPT)
INTAKE_SPEC = importlib.util.spec_from_file_location("stage2_candidate_intake_for_materialize", INTAKE_SCRIPT)
assert SPEC is not None and SPEC.loader is not None
assert INTAKE_SPEC is not None and INTAKE_SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
intake = importlib.util.module_from_spec(INTAKE_SPEC)
sys.modules[SPEC.name] = tool
sys.modules[INTAKE_SPEC.name] = intake
SPEC.loader.exec_module(tool)
INTAKE_SPEC.loader.exec_module(intake)


@pytest.fixture(autouse=True)
def stub_upstream_validators(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the fixture small while exercising intake's strict boundary."""
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


def write(root: Path, relative: str, payload: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def setup_pair(
    tmp_path: Path,
    clone_args: tuple[str, ...] = ("--no-local",),
    *,
    include_mrw_source_closure: bool = False,
) -> tuple[Path, Path, dict[str, object]]:
    source = tmp_path / "source"
    source.mkdir(parents=True)
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "source@example.test")
    git(source, "config", "user.name", "Source")
    git(source, "remote", "add", "origin", "https://example.test/source.git")
    stage0_paths = tuple(intake.STAGE0_CANDIDATE_PATHS)
    stage0 = stage0_paths[0]
    write(source, "keep.txt", b"keep\n")
    write(source, "closure/existing.py", b"base\n")
    write(source, "obsolete.txt", b"delete me\n")
    for candidate in stage0_paths:
        write(source, candidate, b"base stage0\n")
    if include_mrw_source_closure:
        required = set(REQUIRED_CORE_MODULES)
        mrw_paths = [
            path.relative_to(ROOT)
            for path in (ROOT / CORE_ROOT).glob("*.py")
            if path.relative_to(ROOT).as_posix() not in required
        ]
        for relative in mrw_paths:
            destination = source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        for consumer, imports in REQUIRED_CONSUMERS.items():
            destination = source / consumer
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                "".join(f"from {module} import {name}\n" for module, name in imports),
                encoding="utf-8",
            )
    git(source, "add", ".")
    git(source, "commit", "-m", "base")
    base = git(source, "rev-parse", "HEAD")
    git(source, "update-ref", intake.DEFAULT_BASE_REF, base)

    for stage0 in stage0_paths:
        write(source, stage0, b"{}\n")
    stage0_source = Path("closure/stage0.py")
    stage0_snapshot = stage0_paths[0].parent / "snapshots/stage0"
    write(source, stage0_source.as_posix(), b"changed stage0 closure\n")
    write(source, stage0_snapshot.as_posix(), b"stage0 snapshot\n")
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
    write(source, "closure/existing.py", b"closure\n")
    (source / "closure/existing.py").chmod(0o755)
    (source / "obsolete.txt").unlink()
    if include_mrw_source_closure:
        for relative in REQUIRED_CORE_MODULES:
            destination = source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
    git(source, "add", ".")
    git(source, "commit", "-m", "closure")

    target = tmp_path / "target"
    subprocess.check_call(("git", "clone", *clone_args, str(source), str(target)))
    git(target, "update-ref", intake.DEFAULT_BASE_REF, base)
    git(target, "checkout", "--detach", base)
    git(target, "remote", "set-url", "origin", "https://example.test/source.git")
    additional_upserts = [Path("closure/existing.py")]
    if include_mrw_source_closure:
        additional_upserts.extend(Path(path) for path in REQUIRED_CORE_MODULES)
    manifest = intake.build_manifest(
        source_root=source,
        stage0_paths=stage0_paths,
        stage1_record=Path("stage1-evidence/record.json"),
        stage1_receipts=(Path("stage1-receipts/r3.log"),),
        stage0_closure_upserts=(stage0_source, stage0_snapshot),
        additional_upserts=tuple(additional_upserts),
        delete_paths=(Path("obsolete.txt"),),
    )
    return source, target, manifest


def object_store_receipt(root: Path) -> dict[str, tuple[str, str]]:
    objects = root / ".git" / "objects"
    receipt: dict[str, tuple[str, str]] = {}
    for path in sorted(objects.rglob("*")):
        relative = path.relative_to(objects).as_posix()
        if path.is_symlink():
            receipt[relative] = ("symlink", os.readlink(path))
        elif path.is_file():
            receipt[relative] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
        elif path.is_dir():
            receipt[relative] = ("directory", "")
    return receipt


def object_inodes(root: Path) -> dict[tuple[int, int], Path]:
    objects = root / ".git" / "objects"
    return {
        (path.lstat().st_dev, path.lstat().st_ino): path
        for path in objects.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


@pytest.mark.parametrize(
    "ignored_path",
    [
        ".netrc",
        "config/.npmrc",
        "python/.pypirc",
        ".ssh/id_ed25519",
        ".ssh/id_rsa",
        ".docker/config.json",
        ".kube/config",
    ],
)
def test_dangerous_ignored_covers_common_credential_files(ignored_path: str) -> None:
    assert tool._dangerous_ignored(ignored_path)


@pytest.mark.parametrize(
    "ignored_path",
    [
        "config/.npmrc.example",
        "config/.netrc.template",
        ".ssh/id_ed25519.sample",
        "templates/.ssh/id_rsa",
    ],
)
def test_dangerous_ignored_allows_explicit_example_files(ignored_path: str) -> None:
    assert not tool._dangerous_ignored(ignored_path)


def test_materializes_single_parent_exact_delta_and_clean_candidate(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path)

    result = tool.materialize_candidate(
        target_root=target,
        source_root=source,
        manifest=manifest,  # type: ignore[arg-type]
    )

    assert git(target, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert result["parent"] == result["base"]
    assert git(target, "rev-list", "--parents", "-n", "1", "HEAD").split()[1:] == [result["base"]]
    assert git(target, "rev-list", "--count", f"{result['base']}..HEAD") == "1"
    assert (target / "closure/existing.py").read_text() == "closure\n"
    assert not (target / "obsolete.txt").exists()
    snapshot = target / tool.safe_relative(
        next(
            row["path"]
            for row in manifest["entries"]
            if Path(row["path"]).parent.name == "snapshots"
        )
    )
    assert snapshot.stat().st_mode & 0o222 == 0
    assert (target / "closure/existing.py").stat().st_mode & 0o200
    commit_message = subprocess.check_output(
        ("git", "-C", str(target), "show", "-s", "--format=%B", "HEAD"),
        text=True,
    )
    assert "X-Stage2-Candidate=REMEDIATION_INCLUSIVE_RELEASE" in commit_message
    assert git(target, "show", "-s", "--format=%an <%ae>", "HEAD") == (
        f"{tool.COMMIT_IDENTITY_NAME} <{tool.COMMIT_IDENTITY_EMAIL}>"
    )
    assert not list(target.parent.glob(".stage2-index-*"))


def test_materializer_cross_clone_reads_base_objects_from_target_and_upserts_from_source(
    tmp_path: Path,
) -> None:
    source, target, manifest = setup_pair(
        tmp_path,
        include_mrw_source_closure=True,
    )
    for relative in REQUIRED_CORE_MODULES:
        assert not (target / relative).exists()

    result = tool.materialize_candidate(
        target_root=target,
        source_root=source,
        manifest=manifest,  # type: ignore[arg-type]
    )

    assert result["commit"] == git(target, "rev-parse", "HEAD")
    for relative in REQUIRED_CORE_MODULES:
        assert (target / relative).read_bytes() == (source / relative).read_bytes()


def test_snapshot_mode_restore_is_limited_to_manifest_closure(tmp_path: Path) -> None:
    target = tmp_path / "target"
    closure_snapshot = write(target, "candidate/snapshots/closure", b"closure\n")
    unrelated_snapshot = write(target, "ordinary/snapshots/unrelated", b"ordinary\n")
    manifest = {
        "entries": [
            {"operation": "UPSERT", "path": "candidate/snapshots/closure"},
            {"operation": "UPSERT", "path": "ordinary/snapshots/unrelated"},
        ],
        "stage0_b23": {
            "closure": [{"operation": "UPSERT", "path": "candidate/snapshots/closure"}]
        },
        "stage1": {"closure": []},
    }

    tool._restore_manifest_snapshot_modes(
        target,
        manifest,
        expected_identity=tool.directory_identity(target),
    )

    assert closure_snapshot.stat().st_mode & 0o222 == 0
    assert unrelated_snapshot.stat().st_mode & 0o200


def test_snapshot_mode_restore_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    target = tmp_path / "target"
    snapshot = target / "candidate/snapshots/fifo"
    snapshot.parent.mkdir(parents=True)
    os.mkfifo(snapshot)
    manifest = {
        "entries": [{"operation": "UPSERT", "path": "candidate/snapshots/fifo"}],
        "stage0_b23": {
            "closure": [{"operation": "UPSERT", "path": "candidate/snapshots/fifo"}]
        },
        "stage1": {"closure": []},
    }

    with pytest.raises(tool.Stage2MaterializeError, match="not a regular file"):
        tool._restore_manifest_snapshot_modes(
            target,
            manifest,
            expected_identity=tool.directory_identity(target),
        )


def test_materializer_batches_git_operations_and_preserves_modes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    calls: list[tuple[str, ...]] = []
    index_info_input = b""
    hash_object_input = b""
    original_run = tool.subprocess.run

    def spy_run(command: object, *args: object, **kwargs: object) -> object:
        nonlocal hash_object_input, index_info_input
        argv = tuple(str(item) for item in command) if isinstance(command, (tuple, list)) else ()
        if argv and argv[0] == "git":
            if "ls-tree" in argv or "cat-file" in argv or "hash-object" in argv or (
                "update-index" in argv and "--index-info" in argv
            ):
                calls.append(argv)
            if "update-index" in argv and "--index-info" in argv:
                index_info_input = kwargs.get("input", b"")  # type: ignore[assignment]
            if "hash-object" in argv:
                hash_object_input = kwargs.get("input", b"")  # type: ignore[assignment]
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(tool.subprocess, "run", spy_run)
    executable = next(row for row in manifest["entries"] if row["mode"] == "100755")
    result = tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)
    assert result["commit"] == git(target, "rev-parse", "HEAD")
    assert sum("ls-tree" in call for call in calls) == 1
    assert sum("cat-file" in call and "--batch" in call for call in calls) == 1
    assert sum("update-index" in call and "--index-info" in call for call in calls) == 1
    assert sum("hash-object" in call for call in calls) == 1
    hash_call = next(call for call in calls if "hash-object" in call)
    assert "--stdin-paths" in hash_call and "--no-filters" in hash_call
    assert len(hash_object_input.splitlines()) == sum(
        row["operation"] == "UPSERT" for row in manifest["entries"]
    )
    assert index_info_input.count(b"\0") == len(manifest["entries"])
    assert b"0 " + (b"0" * 40) + b"\tobsolete.txt\0" in index_info_input
    assert any(record.startswith(b"100755 ") for record in index_info_input.split(b"\0"))
    assert git(target, "ls-tree", "-r", "HEAD", executable["path"]).split()[0] == executable["mode"]
    assert not (target / "obsolete.txt").exists()


def test_corrupt_existing_loose_object_fails_closed(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path)
    row = next(row for row in manifest["entries"] if row["operation"] == "UPSERT")
    object_path = target / ".git" / "objects" / row["blob"][:2] / row["blob"][2:]
    object_path.parent.mkdir(parents=True, exist_ok=True)
    object_path.write_bytes(b"corrupt-object")
    before = git(target, "rev-parse", "HEAD")
    with pytest.raises(tool.Stage2MaterializeError, match="existing git object is corrupt"):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)
    assert git(target, "rev-parse", "HEAD") == before


def test_git_hash_batch_failure_precedes_object_ref_and_index_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    head_before = git(target, "rev-parse", "HEAD")
    objects_before = object_store_receipt(target)
    original_git = tool._git
    hash_calls = 0

    def reject_git_hash(repo_root: Path, *args: str, **kwargs: object) -> bytes:
        nonlocal hash_calls
        if args[:1] == ("hash-object",):
            hash_calls += 1
            raise tool.Stage2MaterializeError(  # noqa: TRY003
                "injected Git collision detection failure"
            )
        return original_git(repo_root, *args, **kwargs)  # type: ignore[misc]

    monkeypatch.setattr(tool, "_git", reject_git_hash)
    with pytest.raises(
        tool.Stage2MaterializeError,
        match="injected Git collision detection failure",
    ):
        tool.materialize_candidate(
            target_root=target,
            source_root=source,
            manifest=manifest,
        )

    assert hash_calls == 1
    assert git(target, "rev-parse", "HEAD") == head_before
    assert tool._git_optional_ref(target, tool.CANDIDATE_REF) == ""
    assert object_store_receipt(target) == objects_before
    assert not list(target.parent.glob(".stage2-index-*"))


def test_materializer_reuses_matching_base_index_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    index = tool.BaseTreeIndex.from_repo(source, manifest["source"]["base_oid"])
    cache = canonical_intake.BoundedReadOnlyCache(max_entries=1)
    key = canonical_intake._manifest_cache_key(manifest, object_format="sha1")
    cache.put(key, canonical_intake.IntakeCacheValue(base_index=index))
    rebuilds = 0
    reads = 0
    original_read = tool._read_upsert

    def fail_rebuild(*args: object, **kwargs: object) -> object:
        nonlocal rebuilds
        rebuilds += 1
        raise AssertionError

    def count_read(*args: object, **kwargs: object) -> object:
        nonlocal reads
        reads += 1
        return original_read(*args, **kwargs)

    monkeypatch.setattr(tool, "build_base_tree_index", fail_rebuild)
    monkeypatch.setattr(tool, "_read_upsert", count_read)
    result = tool.materialize_candidate(
        target_root=target,
        source_root=source,
        manifest=manifest,
        read_cache=cache,
    )
    assert result["commit"] == git(target, "rev-parse", "HEAD")
    assert rebuilds == 0
    assert reads == sum(row["operation"] == "UPSERT" for row in manifest["entries"])




def test_materializer_rejects_tampered_stage0_closure_before_write(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path)
    original_head = git(target, "rev-parse", "HEAD")
    tampered = json.loads(json.dumps(manifest))
    tampered["stage1"]["closure"].append(tampered["stage0_b23"]["closure"].pop())
    with pytest.raises(
        tool.Stage2MaterializeError,
        match="Stage0 closure must exactly equal required upserts",
    ):
        tool.materialize_candidate(
            target_root=target,
            source_root=source,
            manifest=tampered,  # type: ignore[arg-type]
        )
    assert git(target, "rev-parse", "HEAD") == original_head
    assert tool._git_optional_ref(target, tool.CANDIDATE_REF) == ""


def test_materializer_revalidates_semantic_upstream_bindings_before_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    original_head = git(target, "rev-parse", "HEAD")
    target_receipt = object_store_receipt(target)
    candidate_path = source / intake.STAGE0_CANDIDATE_PATHS[1]
    payload = b'{"status":"SEMANTIC_TAMPER"}\n'
    candidate_path.write_bytes(payload)
    expected_blob = subprocess.check_output(
        ("git", "-C", str(source), "hash-object", "--stdin"),
        input=payload,
    ).decode().strip()
    for row in manifest["entries"]:  # type: ignore[union-attr]
        if row["path"] == intake.STAGE0_CANDIDATE_PATHS[1].as_posix():
            row["sha256"] = hashlib.sha256(payload).hexdigest()
            row["blob"] = expected_blob
    for row in manifest["stage0_b23"]["refs"]:  # type: ignore[index]
        if row["path"] == intake.STAGE0_CANDIDATE_PATHS[1].as_posix():
            row["sha256"] = hashlib.sha256(payload).hexdigest()
            row["blob"] = expected_blob
    intake.validate_manifest(manifest)

    original_check = intake.stage_family_fragment_rebind.check_candidate

    def reject_semantic_tamper(
        path: Path, *, repo_root: Path, history_only: bool
    ) -> object:
        if path in {candidate_path, intake.STAGE0_CANDIDATE_PATHS[1]}:
            raise RuntimeError("semantic status tamper")  # noqa: TRY003
        return original_check(path, repo_root=repo_root, history_only=history_only)  # type: ignore[misc]

    monkeypatch.setattr(
        intake.stage_family_fragment_rebind, "check_candidate", reject_semantic_tamper
    )
    # Source porcelain drift is rejected by cheap preflight before semantic
    # validators are allowed to reread the tampered candidate.
    with pytest.raises(
        tool.Stage2MaterializeError,
        match="source (?:checkout has tracked or untracked changes|porcelain status digest drift)",
    ):
        tool.materialize_candidate(
            target_root=target,
            source_root=source,
            manifest=manifest,  # type: ignore[arg-type]
        )
    assert git(target, "rev-parse", "HEAD") == original_head
    assert tool._git_optional_ref(target, tool.CANDIDATE_REF) == ""
    assert object_store_receipt(target) == target_receipt


def test_dirty_target_preflight_does_not_walk_object_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    (target / "dirty.txt").write_bytes(b"dirty\n")
    object_scans = 0

    def fail_object_scan(*args: object, **kwargs: object) -> object:
        nonlocal object_scans
        object_scans += 1
        raise AssertionError("dirty target must fail before object-store full proof")  # noqa: TRY003

    monkeypatch.setattr(tool, "_assert_and_snapshot_object_stores", fail_object_scan)
    with pytest.raises(tool.Stage2MaterializeError, match="target checkout has tracked or untracked changes"):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)
    assert object_scans == 0


def test_post_cas_failure_restores_exact_state_and_rolls_back_objects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    base = manifest["source"]["base_oid"]  # type: ignore[index]
    head_before = git(target, "rev-parse", "HEAD")
    ref_before = tool._git_optional_ref(target, tool.CANDIDATE_REF)
    objects_before = object_store_receipt(target)
    original_git = tool._git
    candidate_armed = False

    def fail_candidate_checkout(repo_root: Path, *args: str, **kwargs: object) -> bytes:
        nonlocal candidate_armed
        if "update-ref" in args and tool.CANDIDATE_REF in args:
            candidate_armed = True
        if "checkout" in args and candidate_armed:
            raise tool.Stage2MaterializeError("injected candidate checkout failure")  # noqa: TRY003
        return original_git(repo_root, *args, **kwargs)  # type: ignore[misc]

    monkeypatch.setattr(tool, "_git", fail_candidate_checkout)
    with pytest.raises(
        tool.Stage2MaterializeError,
        match="candidate post-CAS materialization failed.*rollback complete",
    ):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)

    assert git(target, "rev-parse", "HEAD") == base == head_before
    assert tool._git_optional_ref(target, tool.CANDIDATE_REF) == ref_before
    assert object_store_receipt(target) == objects_before
    assert git(target, "status", "--porcelain=v1", "--untracked-files=all") == ""


def test_object_store_rollback_removes_all_new_prefix_directories_and_matches_receipt(
    tmp_path: Path,
) -> None:
    source, target, _manifest = setup_pair(tmp_path)
    source_objects = source / ".git" / "objects"
    target_objects = target / ".git" / "objects"
    baseline = tool._assert_and_snapshot_object_stores(source_objects, target_objects)
    receipt_before = object_store_receipt(target)

    (target_objects / "aa").mkdir()
    (target_objects / "bb").mkdir()
    (target_objects / "cc" / "nested").mkdir(parents=True)
    assert object_store_receipt(target) != receipt_before

    tool._rollback_object_store_to_baseline(baseline)

    assert object_store_receipt(target) == receipt_before
    assert not (target_objects / "aa").exists()
    assert not (target_objects / "bb").exists()
    assert not (target_objects / "cc").exists()


def test_object_store_rollback_rejects_changed_baseline_directory_identity(
    tmp_path: Path,
) -> None:
    source, target, _manifest = setup_pair(tmp_path)
    source_objects = source / ".git" / "objects"
    target_objects = target / ".git" / "objects"
    baseline = tool._assert_and_snapshot_object_stores(source_objects, target_objects)
    baseline_directory = next(
        relative for relative in baseline.directories if relative != "."
    )
    victim = target_objects / baseline_directory
    moved = target_objects / f"{baseline_directory}.moved"
    victim.rename(moved)
    victim.mkdir()

    with pytest.raises(
        tool.Stage2MaterializeError,
        match="baseline directory identity changed",
    ):
        tool._rollback_object_store_to_baseline(baseline)

    assert moved.exists()


def test_resolves_source_object_store_relative_to_source_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    caller_cwd = tmp_path / "caller"
    caller_cwd.mkdir()
    monkeypatch.chdir(caller_cwd)

    result = tool.materialize_candidate(
        target_root=target,
        source_root=source,
        manifest=manifest,  # type: ignore[arg-type]
    )

    assert git(target, "rev-parse", "HEAD") == result["commit"]
    assert git(target, "status", "--porcelain=v1", "--untracked-files=all") == ""


def test_requires_isolated_clean_target_at_exact_base(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path)
    with pytest.raises(tool.Stage2MaterializeError, match="target must be an isolated"):
        tool.materialize_candidate(
            target_root=source,
            source_root=source,
            manifest=manifest,  # type: ignore[arg-type]
        )

    (target / "keep.txt").write_text("dirty\n")
    with pytest.raises(tool.Stage2MaterializeError, match="target checkout has tracked"):
        tool.materialize_candidate(
            target_root=target,
            source_root=source,
            manifest=manifest,  # type: ignore[arg-type]
        )


def test_base_precondition_and_source_drift_fail_before_commit(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path)
    tampered = json.loads(json.dumps(manifest))
    entry = next(row for row in tampered["entries"] if row["operation"] == "DELETE")
    entry["base_blob"] = "0" * 40
    with pytest.raises(tool.Stage2MaterializeError, match="manifest entry exact projection drift"):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=tampered)

    source, target, manifest = setup_pair(tmp_path / "second")
    (source / "closure/existing.py").write_text("post-intake\n")
    git(source, "update-index", "--assume-unchanged", "closure/existing.py")
    with pytest.raises(tool.Stage2MaterializeError, match="manifest entry exact projection drift"):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)  # type: ignore[arg-type]


def test_invalid_non_core_upsert_fails_before_candidate_mutation(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path)
    entry = next(
        row for row in manifest["entries"] if row["path"] == "closure/existing.py"
    )
    entry["sha256"] = "0" * 64
    head_before = git(target, "rev-parse", "HEAD")
    objects_before = object_store_receipt(target)

    with pytest.raises(
        tool.Stage2MaterializeError,
        match="manifest entry exact projection drift",
    ):
        tool.materialize_candidate(
            target_root=target,
            source_root=source,
            manifest=manifest,  # type: ignore[arg-type]
        )

    assert git(target, "rev-parse", "HEAD") == head_before
    assert tool._git_optional_ref(target, tool.CANDIDATE_REF) == ""
    assert object_store_receipt(target) == objects_before
    assert not list(target.parent.glob(".stage2-index-*"))


@pytest.mark.parametrize("resurrection_kind", ["file", "symlink", "fifo"])
def test_rejects_ignored_delete_source_resurrection(
    tmp_path: Path,
    resurrection_kind: str,
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    victim = source / "obsolete.txt"
    (source / ".git" / "info" / "exclude").write_text(
        "obsolete.txt\n",
        encoding="utf-8",
    )
    if resurrection_kind == "file":
        victim.write_bytes(b"ignored resurrection\n")
    elif resurrection_kind == "symlink":
        victim.symlink_to("keep.txt")
    else:
        os.mkfifo(victim)
    assert git(source, "status", "--porcelain=v1", "--untracked-files=all") == ""
    head_before = git(target, "rev-parse", "HEAD")
    objects_before = object_store_receipt(target)

    with pytest.raises(
        tool.Stage2MaterializeError,
        match="delete source still exists: obsolete.txt",
    ):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)

    assert git(target, "rev-parse", "HEAD") == head_before
    assert tool._git_optional_ref(target, tool.CANDIDATE_REF) == ""
    assert object_store_receipt(target) == objects_before
    assert not list(target.parent.glob(".stage2-index-*"))


def test_rechecks_ignored_delete_absence_after_payload_reads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    victim = source / "obsolete.txt"
    (source / ".git" / "info" / "exclude").write_text(
        "obsolete.txt\n",
        encoding="utf-8",
    )
    original_assert = tool._assert_delete_source_absent
    checks = 0

    def resurrect_before_final_check(
        source_root: Path,
        relative: Path,
        *,
        expected_identity: tuple[int, int],
    ) -> None:
        nonlocal checks
        checks += 1
        if relative == Path("obsolete.txt") and checks == 2:
            victim.write_bytes(b"late ignored resurrection\n")
        original_assert(
            source_root,
            relative,
            expected_identity=expected_identity,
        )

    monkeypatch.setattr(tool, "_assert_delete_source_absent", resurrect_before_final_check)
    head_before = git(target, "rev-parse", "HEAD")
    objects_before = object_store_receipt(target)

    with pytest.raises(
        tool.Stage2MaterializeError,
        match="delete source still exists: obsolete.txt",
    ):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)

    assert checks == 2
    assert git(target, "rev-parse", "HEAD") == head_before
    assert tool._git_optional_ref(target, tool.CANDIDATE_REF) == ""
    assert object_store_receipt(target) == objects_before
    assert not list(target.parent.glob(".stage2-index-*"))


def test_read_upsert_swap_to_fifo_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, _target, manifest = setup_pair(tmp_path)
    row = next(item for item in manifest["entries"] if item["path"] == "closure/existing.py")  # type: ignore[index]
    victim = source / row["path"]
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
    with pytest.raises(tool.Stage2MaterializeError, match="must be a regular file"):
        tool._read_upsert(source, row)


@pytest.mark.parametrize("replacement_kind", ["symlink", "same-form-checkout"])
def test_materializer_source_root_race_after_identity_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    replacement_kind: str,
) -> None:
    case_root = tmp_path / replacement_kind
    source, target, manifest = setup_pair(case_root)
    expected_identity = (
        manifest["source"]["dev"],  # type: ignore[index]
        manifest["source"]["ino"],  # type: ignore[index]
    )
    original_read = tool._read_upsert
    observed_identity = None

    def replace_root_during_first_read(
        source_root: Path,
        row: dict[str, str],
        *,
        expected_identity: tuple[int, int],
    ) -> tuple[bytes, str]:
        nonlocal observed_identity
        observed_identity = expected_identity
        moved = source_root.parent / "source-original"
        source_root.rename(moved)
        if replacement_kind == "symlink":
            source_root.symlink_to(moved, target_is_directory=True)
        else:
            replacement = source_root.parent / "source-replacement"
            shutil.copytree(moved, replacement, symlinks=True)
            replacement.rename(source_root)
        return original_read(source_root, row, expected_identity=expected_identity)

    monkeypatch.setattr(tool, "_read_upsert", replace_root_during_first_read)
    head_before = git(target, "rev-parse", "HEAD")
    objects_before = object_store_receipt(target)
    with pytest.raises(
        tool.Stage2MaterializeError,
        match=(
            "cannot be opened safely|cannot be opened with expected identity|"
            "source checkout identity changed"
        ),
    ):
        tool.materialize_candidate(
            target_root=target,
            source_root=source,
            manifest=manifest,  # type: ignore[arg-type]
        )

    assert observed_identity == expected_identity
    assert git(target, "rev-parse", "HEAD") == head_before
    assert tool._git_optional_ref(target, tool.CANDIDATE_REF) == ""
    assert object_store_receipt(target) == objects_before


def test_cli_rejects_noncanonical_manifest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source, target, manifest = setup_pair(tmp_path)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    assert tool.main(("--target-root", str(target), "--source-root", str(source), "--manifest", str(path))) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAIL"
    assert payload["checker"] == tool.CHECKER


def test_cli_manifest_fifo_fails_fast(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    destination = tmp_path / "manifest.json"
    os.mkfifo(destination)

    assert tool.main(
        (
            "--target-root", str(tmp_path / "target"),
            "--source-root", str(tmp_path / "source"),
            "--manifest", str(destination),
        )
    ) == 1
    assert "must be a regular file (FIFO)" in capsys.readouterr().out


def test_git_environment_clears_external_variables_and_rewrites_remote(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, _target, _manifest = setup_pair(tmp_path)
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
    monkeypatch.setenv("GIT_AUTHOR_NAME", "External Author")
    index_file = tmp_path / "materializer-index"

    environment = tool._git_env(index_file=index_file)

    assert {
        key for key in environment if key.startswith("GIT_")
    } == {
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_INDEX_FILE",
        "GIT_NO_REPLACE_OBJECTS",
    }
    assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert environment["GIT_INDEX_FILE"] == str(index_file)
    assert tool._git_str(source, "remote", "get-url", "origin") == "https://example.test/source.git"


@pytest.mark.parametrize("config_location", ["home", "xdg"])
def test_home_and_xdg_git_config_cannot_activate_checkout_hook(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_location: str,
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    marker = tmp_path / f"{config_location}-hook-ran"
    hooks = tmp_path / f"{config_location}-hooks"
    hooks.mkdir()
    post_checkout = hooks / "post-checkout"
    post_checkout.write_text(
        f"#!/bin/sh\ntouch '{marker}'\n",
        encoding="utf-8",
    )
    post_checkout.chmod(0o755)
    if config_location == "home":
        home = tmp_path / "malicious-home"
        home.mkdir()
        (home / ".gitconfig").write_text(
            f"[core]\n\thooksPath = {hooks}\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    else:
        home = tmp_path / "clean-home"
        home.mkdir()
        xdg = tmp_path / "malicious-xdg"
        (xdg / "git").mkdir(parents=True)
        (xdg / "git" / "config").write_text(
            f"[core]\n\thooksPath = {hooks}\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))

    result = tool.materialize_candidate(
        target_root=target,
        source_root=source,
        manifest=manifest,
    )

    assert result["commit"] == git(target, "rev-parse", "HEAD")
    assert not marker.exists()


def test_local_post_checkout_hook_is_disabled(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path)
    marker = tmp_path / "local-hook-ran"
    hook = target / ".git" / "hooks" / "post-checkout"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
    hook.chmod(0o755)

    result = tool.materialize_candidate(
        target_root=target,
        source_root=source,
        manifest=manifest,
    )

    assert result["commit"] == git(target, "rev-parse", "HEAD")
    assert not marker.exists()


def test_target_local_executable_filter_is_rejected_before_execution(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path)
    marker = tmp_path / "local-filter-ran"
    git(
        target,
        "config",
        "filter.evil.smudge",
        f"sh -c \"touch '{marker}'; cat\"",
    )
    objects_before = object_store_receipt(target)

    with pytest.raises(
        tool.Stage2MaterializeError,
        match="target effective repository executable filter configuration is forbidden",
    ):
        tool.materialize_candidate(
            target_root=target,
            source_root=source,
            manifest=manifest,
        )

    assert not marker.exists()
    assert object_store_receipt(target) == objects_before
    assert not list(target.parent.glob(".stage2-index-*"))


@pytest.mark.parametrize("via_include", [False, True])
def test_worktree_executable_filter_is_rejected_before_info_attributes_can_run_it(
    tmp_path: Path,
    via_include: bool,
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    marker = tmp_path / "worktree-filter-ran"
    filter_script = tmp_path / "worktree-filter"
    filter_script.write_text(
        f"#!/bin/sh\ntouch '{marker}'\ncat\n",
        encoding="utf-8",
    )
    filter_script.chmod(0o755)
    git(target, "config", "extensions.worktreeConfig", "true")
    if via_include:
        included = tmp_path / "included-worktree-filter.config"
        included.write_text(
            f'[filter "evil"]\n\tsmudge = {filter_script}\n',
            encoding="utf-8",
        )
        git(target, "config", "--worktree", "include.path", str(included))
    else:
        git(
            target,
            "config",
            "--worktree",
            "filter.evil.smudge",
            str(filter_script),
        )
    (target / ".git" / "info" / "attributes").write_text(
        "* filter=evil\n",
        encoding="utf-8",
    )
    objects_before = object_store_receipt(target)

    with pytest.raises(
        tool.Stage2MaterializeError,
        match="target effective repository executable filter configuration is forbidden",
    ):
        tool.materialize_candidate(
            target_root=target,
            source_root=source,
            manifest=manifest,
        )

    assert not marker.exists()
    assert object_store_receipt(target) == objects_before
    assert not list(target.parent.glob(".stage2-index-*"))


def test_local_executable_fsmonitor_is_disabled_for_source_and_target(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path)
    marker = tmp_path / "fsmonitor-ran"
    monitor = tmp_path / "malicious-fsmonitor"
    monitor.write_text(
        f"#!/bin/sh\ntouch '{marker}'\nprintf 'token\\n'\n",
        encoding="utf-8",
    )
    monitor.chmod(0o755)
    git(source, "config", "core.fsmonitor", str(monitor))
    git(target, "config", "core.fsmonitor", str(monitor))

    result = tool.materialize_candidate(
        target_root=target,
        source_root=source,
        manifest=manifest,
    )

    assert result["commit"] == git(target, "rev-parse", "HEAD")
    assert not marker.exists()


def test_source_and_target_replace_refs_cannot_rewrite_candidate_history(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path)
    base = manifest["source"]["base_oid"]  # type: ignore[index]
    replacement = git(source, "rev-parse", "HEAD")
    git(source, "replace", base, replacement)
    git(target, "replace", base, replacement)

    result = tool.materialize_candidate(
        target_root=target,
        source_root=source,
        manifest=manifest,
    )

    assert result["parent"] == base
    assert tool._raw_commit_parents(target, result["commit"]) == (base,)
    assert git(source, "show-ref", "--verify", f"refs/replace/{base}")
    assert git(target, "show-ref", "--verify", f"refs/replace/{base}")


def test_target_history_grafts_are_rejected_before_materialization(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path)
    base = manifest["source"]["base_oid"]  # type: ignore[index]
    objects_before = object_store_receipt(target)
    grafts = target / ".git" / "info" / "grafts"
    grafts.write_text(f"{base}\n", encoding="ascii")

    with pytest.raises(
        tool.Stage2MaterializeError,
        match="history grafts are present",
    ):
        tool.materialize_candidate(
            target_root=target,
            source_root=source,
            manifest=manifest,
        )

    assert git(target, "rev-parse", "HEAD") == base
    assert tool._git_optional_ref(target, tool.CANDIDATE_REF) == ""
    assert object_store_receipt(target) == objects_before
    assert not list(target.parent.glob(".stage2-index-*"))


def test_checkout_failure_rolls_back_candidate_ref_and_detached_base(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    base = manifest["source"]["base_oid"]  # type: ignore[index]
    git(target, "update-ref", tool.CANDIDATE_REF, base)
    original_git = tool._git

    def fail_checkout(repo_root: Path, *args: str, **kwargs: object) -> bytes:
        if args[:1] == ("checkout",):
            raise tool.Stage2MaterializeError
        return original_git(repo_root, *args, **kwargs)

    monkeypatch.setattr(tool, "_git", fail_checkout)
    with pytest.raises(tool.Stage2MaterializeError, match="candidate post-CAS materialization failed"):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)

    assert git(target, "rev-parse", "HEAD") == base
    head_ref = subprocess.run(
        ("git", "-C", str(target), "symbolic-ref", "-q", "HEAD"),
        check=False,
        capture_output=True,
        text=True,
    )
    assert head_ref.returncode != 0 and head_ref.stdout == ""
    assert git(target, "rev-parse", tool.CANDIDATE_REF) == base
    assert git(target, "status", "--porcelain=v1", "--untracked-files=all") == ""


def test_snapshot_mode_restore_failure_rolls_back_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    base = manifest["source"]["base_oid"]  # type: ignore[index]

    def fail_restore(*args: object, **kwargs: object) -> None:
        raise tool.Stage2MaterializeError("injected snapshot mode failure")  # noqa: TRY003

    monkeypatch.setattr(tool, "_restore_manifest_snapshot_modes", fail_restore)
    with pytest.raises(
        tool.Stage2MaterializeError,
        match="candidate post-CAS materialization failed: injected snapshot mode failure",
    ):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)

    assert git(target, "rev-parse", "HEAD") == base
    assert tool._git_optional_ref(target, tool.CANDIDATE_REF) == ""
    assert git(target, "status", "--porcelain=v1", "--untracked-files=all") == ""


def test_rev_list_failure_rolls_back_absent_candidate_ref(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    base = manifest["source"]["base_oid"]  # type: ignore[index]
    original_git = tool._git

    def fail_rev_list_count(repo_root: Path, *args: str, **kwargs: object) -> bytes:
        if args[:2] == ("rev-list", "--count"):
            raise tool.Stage2MaterializeError
        return original_git(repo_root, *args, **kwargs)

    monkeypatch.setattr(tool, "_git", fail_rev_list_count)
    with pytest.raises(
        tool.Stage2MaterializeError,
        match="candidate post-CAS materialization failed",
    ):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)

    assert git(target, "rev-parse", "HEAD") == base
    head_ref = subprocess.run(
        ("git", "-C", str(target), "symbolic-ref", "-q", "HEAD"),
        check=False,
        capture_output=True,
        text=True,
    )
    assert head_ref.returncode != 0 and head_ref.stdout == ""
    ref_check = subprocess.run(
        ("git", "-C", str(target), "rev-parse", "--verify", "--quiet", tool.CANDIDATE_REF),
        check=False,
        capture_output=True,
        text=True,
    )
    assert ref_check.returncode != 0
    assert git(target, "status", "--porcelain=v1", "--untracked-files=all") == ""


def test_read_tree_and_unlink_failures_roll_back_absent_candidate_ref(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    base = manifest["source"]["base_oid"]  # type: ignore[index]

    def fail_read_tree(repo_root: Path, *args: str, **kwargs: object) -> bytes:
        if "read-tree" in args:
            raise tool.Stage2MaterializeError("injected read-tree failure")  # noqa: TRY003
        return original_git(repo_root, *args, **kwargs)  # type: ignore[misc]

    original_git = tool._git
    monkeypatch.setattr(tool, "_git", fail_read_tree)
    with pytest.raises(
        tool.Stage2MaterializeError,
        match="injected read-tree failure",
    ):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)

    assert git(target, "rev-parse", "HEAD") == base
    head_ref = subprocess.run(
        ("git", "-C", str(target), "symbolic-ref", "-q", "HEAD"),
        check=False,
        capture_output=True,
        text=True,
    )
    assert head_ref.returncode != 0 and head_ref.stdout == ""
    ref_check = subprocess.run(
        ("git", "-C", str(target), "rev-parse", "--verify", "--quiet", tool.CANDIDATE_REF),
        check=False,
        capture_output=True,
        text=True,
    )
    assert ref_check.returncode != 0
    assert git(target, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert not list(target.parent.glob(".stage2-index-*"))


def test_temp_index_unlink_failure_is_reported_by_pre_cas_transaction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    original_unlink = Path.unlink
    original_git = tool._git

    def fail_temp_index_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.name.startswith(".stage2-index-"):
            raise PermissionError("injected temporary-index unlink failure")  # noqa: TRY003
        original_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

    def fail_read_tree(repo_root: Path, *args: str, **kwargs: object) -> bytes:
        if "read-tree" in args:
            raise tool.Stage2MaterializeError("injected read-tree failure")  # noqa: TRY003
        return original_git(repo_root, *args, **kwargs)  # type: ignore[misc]

    monkeypatch.setattr(Path, "unlink", fail_temp_index_unlink)
    monkeypatch.setattr(tool, "_git", fail_read_tree)
    with pytest.raises(
        tool.Stage2MaterializeError,
        match="rollback incomplete.*temporary index cleanup failed",
    ):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)
    assert list(target.parent.glob(".stage2-index-*"))


def test_success_path_temp_index_cleanup_failure_rolls_back_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    base = manifest["source"]["base_oid"]  # type: ignore[index]
    objects_before = object_store_receipt(target)
    original_unlink = Path.unlink

    def fail_temp_index_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.name.startswith(".stage2-index-"):
            raise PermissionError("injected successful-path index cleanup failure")  # noqa: TRY003
        original_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "unlink", fail_temp_index_unlink)
    with pytest.raises(
        tool.Stage2MaterializeError,
        match=(
            "candidate post-CAS materialization failed: temporary index cleanup failed.*"
            "rollback incomplete: temporary index cleanup failed"
        ),
    ):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)

    assert git(target, "rev-parse", "HEAD") == base
    assert tool._git_optional_ref(target, tool.CANDIDATE_REF) == ""
    assert git(target, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert object_store_receipt(target) == objects_before
    assert list(target.parent.glob(".stage2-index-*"))


def test_rejects_shared_clone_object_alternates(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path / "shared", clone_args=("--shared",))
    with pytest.raises(tool.Stage2MaterializeError, match="object alternates are present"):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)


def test_rejects_shallow_clone(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path)
    base = manifest["source"]["base_oid"]  # type: ignore[index]
    (target / ".git" / "shallow").write_text(f"{base}\n", encoding="ascii")
    with pytest.raises(tool.Stage2MaterializeError, match="shallow history is present"):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)


def test_rejects_target_objects_symlinked_to_source_store(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path)
    target_objects = target / ".git" / "objects"
    target_local_objects = target / ".git" / "objects.local"
    target_objects.rename(target_local_objects)
    os.symlink(source / ".git" / "objects", target_objects)

    before = object_store_receipt(source)
    with pytest.raises(tool.Stage2MaterializeError, match="target object store is a symlink"):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)
    assert object_store_receipt(source) == before


def test_rejects_local_clone_hardlinked_objects_without_source_drift(tmp_path: Path) -> None:
    source, target, manifest = setup_pair(tmp_path / "local", clone_args=("--local",))
    source_before = object_store_receipt(source)
    target_before = object_store_receipt(target)
    source_inodes = object_inodes(source)
    target_inodes = object_inodes(target)
    assert set(source_inodes) & set(target_inodes)

    with pytest.raises(
        tool.Stage2MaterializeError,
        match=r"target object-store file is hardlinked \(st_nlink=[2-9][0-9]*\)",
    ):
        tool.materialize_candidate(
            target_root=target,
            source_root=source,
            manifest=manifest,  # type: ignore[arg-type]
        )
    assert object_store_receipt(source) == source_before
    assert object_store_receipt(target) == target_before


@pytest.mark.parametrize("side", ["source", "target"])
def test_rejects_object_store_walk_errors_before_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    side: str,
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    original_head = git(target, "rev-parse", "HEAD")
    source_receipt = object_store_receipt(source)
    target_receipt = object_store_receipt(target)
    walk_root = (
        source / ".git" / "objects"
        if side == "source"
        else target / ".git" / "objects"
    )
    original_walk = tool.os.walk

    def fail_closed_walk(root: object, *args: object, **kwargs: object) -> object:
        if Path(str(root)) != walk_root:
            return original_walk(root, *args, **kwargs)  # type: ignore[arg-type]
        if kwargs.get("onerror") is None:
            raise AssertionError("object walk must install an onerror callback")  # noqa: TRY003
        kwargs["onerror"](PermissionError(f"injected {side} object-store walk failure"))
        raise AssertionError("object walk onerror must reject materialization")  # noqa: TRY003

    monkeypatch.setattr(tool.os, "walk", fail_closed_walk)
    with pytest.raises(
        tool.Stage2MaterializeError,
        match=f"{side} object-store traversal is unreadable",
    ):
        tool.materialize_candidate(
            target_root=target,
            source_root=source,
            manifest=manifest,  # type: ignore[arg-type]
        )

    assert git(target, "rev-parse", "HEAD") == original_head
    assert tool._git_optional_ref(target, tool.CANDIDATE_REF) == ""
    assert object_store_receipt(source) == source_receipt
    assert object_store_receipt(target) == target_receipt
    assert not list(target.parent.glob(".stage2-index-*"))


def test_rejects_object_store_realpath_outside_target_common_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source, target, manifest = setup_pair(tmp_path)
    outside = tmp_path / "outside-object-store"
    outside.mkdir()
    original_git_str = tool._git_str

    def git_str_with_external_objects(repo_root: Path, *args: str, **kwargs: object) -> str:
        if repo_root == target and args == ("rev-parse", "--git-path", "objects"):
            return str(outside)
        return original_git_str(repo_root, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(tool, "_git_str", git_str_with_external_objects)
    with pytest.raises(
        tool.Stage2MaterializeError,
        match="target object-store realpath is not owned by the target common-dir",
    ):
        tool.materialize_candidate(target_root=target, source_root=source, manifest=manifest)
