from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stage_family_fragment_rebind as tool  # noqa: E402


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stage_family_fragment_rebind.py"


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def content_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        canonical({key: item for key, item in value.items() if key != "content_digest"})
    ).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))
    return path


def json_manifest_ref(root: Path, relative: str) -> dict[str, str]:
    path = root / relative
    parsed = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": relative,
        "file_sha256": file_digest(path),
        "content_digest": content_digest(parsed),
    }


def raw_manifest_ref(root: Path, relative: str) -> dict[str, str]:
    path = root / relative
    return {
        "path": relative,
        "file_sha256": file_digest(path),
    }


def make_manifest(root: Path) -> tuple[Path, Path, Path, Path]:
    fragment = write_json(
        root / "fragments/C7.json",
        {"family": "c7", "schema": "fixture.fragment.v1"},
    )
    source = root / "sources/source.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"SOURCE = 'old'\n")
    test = root / "tests/test.py"
    test.parent.mkdir(parents=True, exist_ok=True)
    test.write_bytes(b"def test_old():\n    assert True\n")
    manifest = write_json(
        root / "manifest.json",
        {
            "amendment": "bind exact C7 evidence",
            "family": "c7",
            "fragments": [json_manifest_ref(root, "fragments/C7.json")],
            "schema": tool.MANIFEST_SCHEMA,
            "sources": [raw_manifest_ref(root, "sources/source.py")],
            "tests": [raw_manifest_ref(root, "tests/test.py")],
        },
    )
    return manifest, fragment, source, test


def snapshot_paths(output: Path) -> set[Path]:
    return set((output / tool.SNAPSHOT_DIRECTORY).iterdir())


def test_stage_is_deterministic_and_freezes_manifest_and_all_inputs(tmp_path: Path) -> None:
    manifest, fragment, source, test = make_manifest(tmp_path)
    first_output = tmp_path / "staged-a"
    second_output = tmp_path / "staged-b"

    first = tool.stage(manifest, first_output, repo_root=tmp_path)
    second = tool.stage(manifest, second_output, repo_root=tmp_path)

    assert first["candidate_id"] == second["candidate_id"]
    assert first["status"] == second["status"]
    assert first["status"] == tool.LIVE_STATUS
    candidate = first_output / tool.CANDIDATE_FILENAME
    assert (second_output / tool.CANDIDATE_FILENAME).read_bytes() == candidate.read_bytes()
    assert sorted(path.name for path in first_output.iterdir()) == [
        tool.CANDIDATE_FILENAME,
        tool.SNAPSHOT_DIRECTORY,
    ]
    assert {
        file_digest(path)
        for path in (manifest, fragment, source, test)
    } == {path.name for path in snapshot_paths(first_output)}
    assert {path.name for path in snapshot_paths(first_output)} == {
        path.name for path in snapshot_paths(second_output)
    }
    assert candidate.stat().st_mode & 0o222 == 0
    assert all(
        path.stat().st_mode & 0o222 == 0 for path in snapshot_paths(first_output)
    )

    result = tool.check_candidate(candidate, repo_root=tmp_path)
    assert result["candidate_id"] == first["candidate_id"]
    assert result["status"] == tool.LIVE_STATUS


def test_history_only_ignores_deleted_and_changed_logical_paths(tmp_path: Path) -> None:
    manifest, _, source, _ = make_manifest(tmp_path)
    output = tmp_path / "staged"
    staged = tool.stage(manifest, output, repo_root=tmp_path)
    candidate = output / tool.CANDIDATE_FILENAME

    source.unlink()
    history = tool.check_candidate(
        candidate,
        repo_root=tmp_path,
        history_only=True,
    )
    assert history["status"] == tool.HISTORY_STATUS
    assert history["candidate_id"] == staged["candidate_id"]

    source.write_bytes(b"SOURCE = 'changed'\n")
    with pytest.raises(tool.ValidationError, match="live logical path mismatch"):
        tool.check_candidate(candidate, repo_root=tmp_path)
    assert tool.check_candidate(
        candidate,
        repo_root=tmp_path,
        history_only=True,
    )["status"] == tool.HISTORY_STATUS


def test_blob_tamper_fails_in_live_and_history_modes(tmp_path: Path) -> None:
    manifest, _, source, _ = make_manifest(tmp_path)
    output = tmp_path / "staged"
    tool.stage(manifest, output, repo_root=tmp_path)
    candidate = output / tool.CANDIDATE_FILENAME
    candidate_value = json.loads(candidate.read_text(encoding="utf-8"))
    snapshot = output / candidate_value["sources"][0]["snapshot_path"]
    snapshot.chmod(0o600)
    snapshot.write_bytes(b"tampered\n")

    with pytest.raises(tool.ValidationError, match="snapshot"):
        tool.check_candidate(candidate, repo_root=tmp_path)
    with pytest.raises(tool.ValidationError, match="snapshot"):
        tool.check_candidate(
            candidate,
            repo_root=tmp_path,
            history_only=True,
        )


def test_candidate_and_manifest_divergence_fails_after_digest_rewrite(tmp_path: Path) -> None:
    manifest, *_ = make_manifest(tmp_path)
    output = tmp_path / "staged"
    tool.stage(manifest, output, repo_root=tmp_path)
    candidate_path = output / tool.CANDIDATE_FILENAME
    candidate_path.chmod(0o600)
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["family"] = "changed"
    candidate["amendment"] = "changed"
    candidate["candidate_id"] = tool._candidate_id(
        candidate["family"],
        candidate["amendment"],
        candidate["manifest"],
        {group: candidate[group] for group in tool.RAW_GROUPS},
    )
    candidate["content_digest"] = content_digest(candidate)
    write_json(candidate_path, candidate)

    with pytest.raises(
        tool.ValidationError,
        match="family mismatch|amendment mismatch",
    ):
        tool.check_candidate(candidate_path, repo_root=tmp_path)


def test_stage_rejects_input_digest_and_path_failures(tmp_path: Path) -> None:
    manifest, _, source, _ = make_manifest(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_bytes(canonical({"outside": True}))

    escaped = json.loads(manifest.read_text(encoding="utf-8"))
    escaped["sources"][0]["path"] = "../outside.json"
    with pytest.raises(tool.ValidationError, match="normalized"):
        tool.stage(
            write_json(tmp_path / "escaped.json", escaped),
            tmp_path / "escaped-output",
            repo_root=tmp_path,
        )

    missing = json.loads(manifest.read_text(encoding="utf-8"))
    missing["tests"][0]["path"] = "tests/missing.py"
    with pytest.raises(tool.ValidationError, match="cannot open confined file"):
        tool.stage(
            write_json(tmp_path / "missing.json", missing),
            tmp_path / "missing-output",
            repo_root=tmp_path,
        )

    tampered = json.loads(manifest.read_text(encoding="utf-8"))
    source.write_bytes(b"SOURCE = 'changed'\n")
    with pytest.raises(tool.ValidationError, match="file_sha256 mismatch"):
        tool.stage(
            write_json(tmp_path / "tampered.json", tampered),
            tmp_path / "tampered-output",
            repo_root=tmp_path,
        )
    assert not (tmp_path / "escaped-output").exists()


def test_stage_rejects_symlinked_input_and_output_paths(tmp_path: Path) -> None:
    manifest, _, source, _ = make_manifest(tmp_path)
    source_alias = tmp_path / "sources/source-alias.py"
    source_alias.symlink_to(source)
    aliased = json.loads(manifest.read_text(encoding="utf-8"))
    aliased["sources"][0] = raw_manifest_ref(tmp_path, "sources/source-alias.py")
    aliased["sources"][0]["file_sha256"] = file_digest(source)

    with pytest.raises(tool.ValidationError, match="symlink"):
        tool.stage(
            write_json(tmp_path / "manifest-symlink.json", aliased),
            tmp_path / "output",
            repo_root=tmp_path,
        )

    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    output_alias = tmp_path / "output-alias"
    output_alias.symlink_to(outside, target_is_directory=True)
    with pytest.raises(tool.ValidationError, match="symlink"):
        tool.stage(manifest, output_alias, repo_root=tmp_path)


def test_stage_rejects_root_and_relative_escape_outputs(tmp_path: Path) -> None:
    manifest, *_ = make_manifest(tmp_path)
    with pytest.raises(tool.ValidationError, match="below the repository root"):
        tool.stage(manifest, tmp_path, repo_root=tmp_path)
    with pytest.raises(tool.ValidationError, match="below the repository root"):
        tool.stage(manifest, Path("."), repo_root=tmp_path)
    with pytest.raises(tool.ValidationError, match="normalized"):
        tool.stage(manifest, Path("nested/../outside"), repo_root=tmp_path)


def test_cli_ignores_outside_cwd_for_repo_relative_paths(tmp_path: Path) -> None:
    manifest, *_ = make_manifest(tmp_path)
    outside_cwd = tmp_path.parent / f"{tmp_path.name}-cwd"
    outside_cwd.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "stage",
            "--repo-root",
            str(tmp_path),
            "--manifest",
            "manifest.json",
            "--output-dir",
            "nested/staged",
        ],
        cwd=outside_cwd,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "nested/staged" / tool.CANDIDATE_FILENAME).is_file()
    assert not (outside_cwd / "nested").exists()

    checked = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "check-candidate",
            "--repo-root",
            str(tmp_path),
            "--candidate",
            "nested/staged/candidate.v2.json",
            "--history-only",
        ],
        cwd=outside_cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)["status"] == tool.HISTORY_STATUS


def test_json_parser_rejects_duplicate_keys_and_non_finite_numbers(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
    non_finite = tmp_path / "non-finite.json"
    non_finite.write_text('{"value":NaN}', encoding="utf-8")

    with pytest.raises(tool.ValidationError, match="duplicate JSON object key"):
        tool._parse_json_bytes(duplicate.read_bytes(), label="duplicate")
    with pytest.raises(tool.ValidationError, match="non-finite JSON number"):
        tool._parse_json_bytes(non_finite.read_bytes(), label="non-finite")


def test_cli_help_contains_only_stage_and_check_candidate() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0
    assert "{stage,check-candidate}" in completed.stdout
    for forbidden in ("check-pointer", "current pointer", "review", "selection"):
        assert forbidden not in completed.stdout.lower()

    invalid = subprocess.run(
        [sys.executable, str(SCRIPT), "invalid"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert invalid.returncode != 0
    assert "invalid choice" in invalid.stderr


def test_stage_rejects_output_overlap_without_publication_side_effects(tmp_path: Path) -> None:
    manifest, *_ = make_manifest(tmp_path)
    inside_output = tmp_path / "manifest-inside"
    inside_manifest = write_json(
        inside_output / "manifest.json",
        json.loads(manifest.read_text(encoding="utf-8")),
    )
    with pytest.raises(tool.ValidationError, match="manifest must not be inside"):
        tool.stage(inside_manifest, inside_output, repo_root=tmp_path)

    manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_value["sources"][0]["path"] = "staged/source.py"
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "source.py").write_bytes(b"SOURCE = 'old'\n")
    manifest_value["sources"][0]["file_sha256"] = file_digest(staged / "source.py")
    write_json(manifest, manifest_value)

    with pytest.raises(tool.ValidationError, match="inside the output directory"):
        tool.stage(manifest, staged, repo_root=tmp_path)
    assert sorted(path.name for path in staged.iterdir()) == ["source.py"]

    bad = tmp_path / "bad.json"
    bad_value = json.loads(manifest.read_text(encoding="utf-8"))
    bad_value["sources"][0]["file_sha256"] = "0" * 64
    write_json(bad, bad_value)
    with pytest.raises(tool.ValidationError, match="file_sha256 mismatch"):
        tool.stage(bad, tmp_path / "no-output", repo_root=tmp_path)
    assert not (tmp_path / "no-output").exists()


def test_check_candidate_rejects_hardlinked_snapshot(tmp_path: Path) -> None:
    manifest, *_ = make_manifest(tmp_path)
    output = tmp_path / "staged"
    tool.stage(manifest, output, repo_root=tmp_path)
    candidate_path = output / tool.CANDIDATE_FILENAME
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    snapshot = output / candidate["sources"][0]["snapshot_path"]
    alias = output / "hardlinked-blob"
    os.link(snapshot, alias)

    with pytest.raises(tool.ValidationError, match="exactly one link"):
        tool.check_candidate(
            candidate_path,
            repo_root=tmp_path,
            history_only=True,
        )


def test_malformed_snapshot_path_is_cli_failure_not_traceback(tmp_path: Path) -> None:
    manifest, *_ = make_manifest(tmp_path)
    output = tmp_path / "staged"
    tool.stage(manifest, output, repo_root=tmp_path)
    candidate_path = output / tool.CANDIDATE_FILENAME
    candidate_path.chmod(0o600)
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["sources"][0]["snapshot_path"] = {"malformed": True}
    candidate["content_digest"] = content_digest(candidate)
    write_json(candidate_path, candidate)

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "check-candidate",
            "--repo-root",
            str(tmp_path),
            "--candidate",
            candidate_path.relative_to(tmp_path).as_posix(),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 1
    assert completed.stderr.startswith("FAIL family_fragment_rebind:")
    assert "snapshot_path must name" in completed.stderr
    assert "Traceback" not in completed.stderr


def test_final_path_is_published_only_after_complete_temporary_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, *_ = make_manifest(tmp_path)
    output = tmp_path / "staged"
    ready: list[str] = []
    real_ready = tool._publication_ready
    real_link = os.link

    def delayed_ready(parent: int, temporary_name: str, payload: bytes) -> bool:
        if not ready:
            snapshots = output / tool.SNAPSHOT_DIRECTORY
            assert not any(
                path.is_file() and not path.name.endswith(".tmp")
                for path in snapshots.iterdir()
            )
        result = real_ready(parent, temporary_name, payload)
        ready.append(temporary_name)
        return result

    def guarded_link(
        source: str | os.PathLike[str],
        destination: str | os.PathLike[str],
        **kwargs: object,
    ) -> None:
        assert ready
        real_link(source, destination, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(tool, "_publication_ready", delayed_ready)
    monkeypatch.setattr(os, "link", guarded_link)
    staged = tool.stage(manifest, output, repo_root=tmp_path)
    assert staged["status"] == tool.LIVE_STATUS
    assert len(ready) == 5


def test_concurrent_stage_never_exposes_truncated_final_paths(tmp_path: Path) -> None:
    first_manifest, *_ = make_manifest(tmp_path)
    first_value = json.loads(first_manifest.read_text(encoding="utf-8"))
    second_source = tmp_path / "sources/second.py"
    second_source.write_bytes(b"SOURCE = 'second'\n")
    second_value = dict(first_value)
    second_value["sources"] = [
        {
            "path": "sources/second.py",
            "file_sha256": file_digest(second_source),
        }
    ]
    second_manifest = write_json(tmp_path / "second-manifest.json", second_value)
    output = tmp_path / "staged"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(tool.stage, first_manifest, output, repo_root=tmp_path),
            executor.submit(tool.stage, second_manifest, output, repo_root=tmp_path),
        ]
        results = []
        errors = []
        for future in futures:
            try:
                results.append(future.result())
            except tool.ValidationError as exc:
                errors.append(str(exc))

    assert sum(result["status"] == tool.LIVE_STATUS for result in results) == 1
    assert len(errors) == 1
    assert "candidate output already exists" in errors[0]
    candidate_path = output / tool.CANDIDATE_FILENAME
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    snapshots = list((output / tool.SNAPSHOT_DIRECTORY).iterdir())
    assert all(path.stat().st_nlink == 1 for path in snapshots)
    assert all(path.stat().st_mode & 0o222 == 0 for path in snapshots)
    assert all(file_digest(path) == path.name for path in snapshots)
    assert not [path for path in snapshots if path.name.endswith(".tmp")]
    assert tool.check_candidate(
        candidate_path,
        repo_root=tmp_path,
        history_only=True,
    )["candidate_id"] == candidate["candidate_id"]


def run_cli(*args: object, timeout: float = 2.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(value) for value in args)],
        check=False,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def test_cli_rejects_fifo_candidate_manifest_input_and_snapshot_without_blocking(
    tmp_path: Path,
) -> None:
    manifest, _, source, _ = make_manifest(tmp_path)
    output = tmp_path / "staged"
    tool.stage(manifest, output, repo_root=tmp_path)
    candidate_path = output / tool.CANDIDATE_FILENAME
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))

    manifest_fifo = tmp_path / "manifest-fifo"
    os.mkfifo(manifest_fifo)
    completed = run_cli(
        "stage",
        "--repo-root",
        tmp_path,
        "--manifest",
        manifest_fifo,
        "--output-dir",
        tmp_path / "fifo-output",
    )
    assert completed.returncode == 1
    assert completed.stderr.startswith("FAIL family_fragment_rebind:")
    assert "regular file" in completed.stderr

    input_fifo = tmp_path / "sources/input-fifo"
    os.mkfifo(input_fifo)
    fifo_manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
    fifo_manifest_value["sources"][0] = {
        "path": "sources/input-fifo",
        "file_sha256": hashlib.sha256(b"").hexdigest(),
    }
    fifo_manifest = write_json(tmp_path / "fifo-input-manifest.json", fifo_manifest_value)
    completed = run_cli(
        "stage",
        "--repo-root",
        tmp_path,
        "--manifest",
        fifo_manifest.relative_to(tmp_path),
        "--output-dir",
        tmp_path / "fifo-input-output",
    )
    assert completed.returncode == 1
    assert "regular file" in completed.stderr

    snapshot_path = output / candidate["sources"][0]["snapshot_path"]
    snapshot_path.chmod(0o600)
    snapshot_path.unlink()
    os.mkfifo(snapshot_path)
    completed = run_cli(
        "check-candidate",
        "--repo-root",
        tmp_path,
        "--candidate",
        candidate_path.relative_to(tmp_path),
        "--history-only",
    )
    assert completed.returncode == 1
    assert "regular file" in completed.stderr

    candidate_path.unlink()
    os.mkfifo(candidate_path)
    completed = run_cli(
        "check-candidate",
        "--repo-root",
        tmp_path,
        "--candidate",
        candidate_path.relative_to(tmp_path),
        "--history-only",
    )
    assert completed.returncode == 1
    assert "regular file" in completed.stderr


def test_store_snapshot_preset_symlink_is_cli_failure_without_traceback(
    tmp_path: Path,
) -> None:
    manifest, _, source, _ = make_manifest(tmp_path)
    output = tmp_path / "staged"
    snapshots = output / tool.SNAPSHOT_DIRECTORY
    snapshots.mkdir(parents=True)
    (snapshots / file_digest(source)).symlink_to(tmp_path / "missing-target")

    completed = run_cli(
        "stage",
        "--repo-root",
        tmp_path,
        "--manifest",
        manifest.relative_to(tmp_path),
        "--output-dir",
        output.relative_to(tmp_path),
    )
    assert completed.returncode == 1
    assert completed.stderr.startswith("FAIL family_fragment_rebind:")
    assert "cannot open existing snapshot" in completed.stderr
    assert "Traceback" not in completed.stderr


def test_snapshot_stuck_at_two_links_fails_with_stable_validation_error(
    tmp_path: Path,
) -> None:
    payload = b"stable-nlink-failure\n"
    output = tmp_path / "staged"
    digest = tool._store_snapshot(tmp_path, output, payload)
    snapshot = output / tool.SNAPSHOT_DIRECTORY / digest
    os.link(snapshot, output / "extra-link")

    with pytest.raises(tool.ValidationError, match="exactly one link"):
        tool._store_snapshot(tmp_path, output, payload)
