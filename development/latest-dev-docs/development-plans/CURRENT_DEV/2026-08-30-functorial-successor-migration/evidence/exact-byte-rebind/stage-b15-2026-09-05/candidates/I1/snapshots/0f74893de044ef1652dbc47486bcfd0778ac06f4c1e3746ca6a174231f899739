"""C1 Slice A/B/C evidence generator determinism and fail-closed tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR = _BACKEND_ROOT / "scripts/generate_c1_slice_acceptance.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_c1_slice_acceptance", _GENERATOR
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_pg_fixture(tmp_path: Path, module, *, missing_nodes=()) -> Path:
    path = tmp_path / "test_p5_c1_slice_acceptance_postgres.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for node in module.PG_TEST_NODES:
        if node in missing_nodes:
            continue
        lines.append(f"def {node}():\n    assert True\n")
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _write_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "c1_slice_postgres_fixture.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '"""Disposable-PostgreSQL fixture for isolated generator tests."""\n',
        encoding="utf-8",
    )
    return path


def _configure(
    module,
    tmp_path: Path,
    monkeypatch,
    *,
    pg_missing: bool = False,
    missing_nodes=(),
) -> dict[str, Path]:
    pg_path = tmp_path / "pg" / "test_p5_c1_slice_acceptance_postgres.py"
    if not pg_missing:
        pg_path.parent.mkdir(parents=True, exist_ok=True)
        pg_path = _write_pg_fixture(pg_path.parent, module, missing_nodes=missing_nodes)
        monkeypatch.setattr(
            module, "PG_TEST_FILE_SHA256", _sha256(pg_path.read_bytes())
        )
    monkeypatch.setattr(module, "PG_TEST_PATH", pg_path)
    fixture_path = _write_fixture(tmp_path / "pg-fixture")
    monkeypatch.setattr(
        module,
        "PG_TEST_FIXTURE_SHA256",
        _sha256(fixture_path.read_bytes()),
    )
    monkeypatch.setattr(module, "PG_TEST_FIXTURE_PATH", fixture_path)
    slice_paths = {
        slice_id: tmp_path / f"C1Slice{slice_id}.v1.json"
        for slice_id in module.SLICE_ORDER
    }
    aggregate_path = tmp_path / "P5C1SliceAcceptance.v1.json"
    monkeypatch.setattr(module, "SLICE_PATHS", slice_paths)
    monkeypatch.setattr(module, "AGGREGATE_PATH", aggregate_path)
    return {"aggregate": aggregate_path, **slice_paths}


def _run_cli(*args: str):
    return subprocess.run(
        [sys.executable, str(_GENERATOR), *args],
        capture_output=True,
        text=True,
        cwd=str(_BACKEND_ROOT),
        check=False,
    )


def test_slices_are_normalized_with_c1_coverage_and_authority_false(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_generator()
    _configure(module, tmp_path, monkeypatch)
    slices = module.build_evidence()

    assert set(slices) == {"A", "B", "C"}
    digest_keys = (
        "program_digest",
        "plan_digest",
        "catalog_digest",
        "control_root_digest",
        "source_map_digest",
        "dependency_index_digest",
    )
    for slice_id, artifact in slices.items():
        assert artifact["schema"] == module.SLICE_SCHEMA
        assert artifact["slice_id"] == slice_id
        assert artifact["accepted"] is True
        assert artifact["blocking_findings"] == []
        assert set(artifact["cell_coverage"]) == {"C1.1", "C1.2", "C1.3"}
        for key in digest_keys:
            assert len(artifact["exact_digests"][key]) == 64
        assert artifact["program_plan_sameness"]["same_exact_program"] is True
        assert artifact["program_plan_sameness"]["same_exact_plan"] is True
        assert artifact["observations"]["observational_compatibility"] is True
        assert artifact["observations"]["compatibility_claim"] == (
            "NAMED_OBSERVATIONAL_COMPATIBILITY_ONLY"
        )
        assert artifact["pg_binding"]["nodes"] == list(module.PG_TEST_NODES)
        assert artifact["pg_binding"]["nodes_present"] is True
        assert len(artifact["pg_binding"]["fixture"]["sha256"]) == 64
        assert artifact["acceptance"]["provider_calls"] == 0
        assert artifact["acceptance"]["store_writes"] == 0
        assert artifact["acceptance"]["canonical_effect_calls"] == 0
        assert artifact["acceptance"]["duplicated_effect_calls"] == 0
        assert artifact["acceptance"]["graph_json_reads"] == 0
        assert all(not value for value in artifact["authority"].values())
        assert artifact["acceptance"]["accepted"] is True
        assert len(artifact["acceptance"]["acceptance_digest"]) == 64
        assert len(artifact["acceptance"]["receipt_digest"]) == 64


def test_bindings_are_exact_and_cover_pure_and_pg_refs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_generator()
    _configure(module, tmp_path, monkeypatch)
    artifact = module.build_evidence()["A"]

    for binding in (
        *artifact["source_bindings"],
        *artifact["implementation_bindings"],
        *artifact["test_bindings"],
    ):
        assert set(binding) == {"path", "sha256", "bytes", "lines", "role"}
        assert len(binding["sha256"]) == 64
        assert binding["bytes"] > 0
        assert binding["lines"] > 0
    test_roles = {entry["role"] for entry in artifact["test_bindings"]}
    assert {
        "pure_slice_programs_test",
        "pure_legacy_oracle_test",
        "c1_evidence_generator_test",
        "c1_postgres_gate",
        "c1_postgres_fixture",
    } <= test_roles
    source_roles = {entry["role"] for entry in artifact["source_bindings"]}
    assert "vertical_slices_route_decision" in source_roles
    assert "p1_fragment_C1" in source_roles
    assert "legacy_workflow_graph_oracle" in source_roles


def test_write_is_deterministic_atomic_and_digest_self_tested(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_generator()
    paths = _configure(module, tmp_path, monkeypatch)
    module.write_evidence()

    for slice_id, path in module.SLICE_PATHS.items():
        value = json.loads(path.read_text(encoding="utf-8"))
        assert value["slice_id"] == slice_id
        assert value["schema"] == module.SLICE_SCHEMA
        expected = module.content_digest(
            {key: item for key, item in value.items() if key != "content_digest"}
        )
        assert value["content_digest"] == expected
    aggregate = json.loads(module.AGGREGATE_PATH.read_text(encoding="utf-8"))
    assert aggregate["schema"] == module.AGGREGATE_SCHEMA
    assert aggregate["status"] == module.STATUS_READY
    assert aggregate["promotion_claim"] is False
    assert aggregate["candidate_state"] == "NO_CANDIDATE"
    expected_aggregate_digest = module.content_digest(
        {key: item for key, item in aggregate.items() if key != "content_digest"}
    )
    assert aggregate["content_digest"] == expected_aggregate_digest
    assert all(not value for value in aggregate["authority_ceiling"].values())

    first_bytes = {path: path.read_bytes() for path in paths.values()}
    module.write_evidence()
    assert {path: path.read_bytes() for path in paths.values()} == first_bytes


def test_aggregate_blocks_on_missing_or_blocked_slice(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_generator()
    _configure(module, tmp_path, monkeypatch)
    module.write_evidence()

    module.SLICE_PATHS["B"].unlink()
    with pytest.raises(module.EvidenceBuildError) as exc:
        module.build_aggregate_from_disk()
    assert "missing" in str(exc.value)
    assert exc.value.exit_code == module.EXIT_MISSING

    module.write_evidence()
    blocked = json.loads(module.SLICE_PATHS["A"].read_text(encoding="utf-8"))
    blocked["accepted"] = False
    blocked["blocking_findings"] = ["OBSERVED_BLOCKED:step-0:effect"]
    blocked["content_digest"] = module.content_digest(
        {key: item for key, item in blocked.items() if key != "content_digest"}
    )
    module.SLICE_PATHS["A"].write_text(
        module._canonical_json(blocked) + "\n",
        encoding="utf-8",
    )
    aggregate = module.build_aggregate_from_disk()
    assert aggregate["status"] == module.STATUS_BLOCK
    assert any(
        finding.startswith("SLICE_BLOCKED:A")
        for finding in aggregate["blocking_findings"]
    )


def test_aggregate_partial_when_pg_binding_is_inconsistent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_generator()
    _configure(module, tmp_path, monkeypatch)
    module.write_evidence()

    drifted = json.loads(module.SLICE_PATHS["C"].read_text(encoding="utf-8"))
    drifted["pg_binding"]["sha256"] = "b" * 64
    drifted["content_digest"] = module.content_digest(
        {key: item for key, item in drifted.items() if key != "content_digest"}
    )
    module.SLICE_PATHS["C"].write_text(
        module._canonical_json(drifted) + "\n",
        encoding="utf-8",
    )
    aggregate = module.build_aggregate_from_disk()
    assert aggregate["status"] == module.STATUS_PARTIAL
    assert "PG_BINDING_INCONSISTENT_ACROSS_SLICES" in aggregate["blocking_findings"]


def test_pg_fail_closed_missing_unbound_node_and_sha_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_generator()
    _configure(module, tmp_path, monkeypatch, pg_missing=True)
    with pytest.raises(module.EvidenceBuildError) as exc:
        module.build_evidence()
    assert "PG test file missing" in str(exc.value)
    assert exc.value.exit_code == module.EXIT_MISSING

    _configure(module, tmp_path, monkeypatch)
    monkeypatch.setattr(module, "PG_TEST_FILE_SHA256", "")
    with pytest.raises(module.EvidenceBuildError) as exc:
        module.build_evidence()
    assert "unbound" in str(exc.value)
    assert exc.value.exit_code == module.EXIT_PG_UNBOUND

    _configure(
        module,
        tmp_path,
        monkeypatch,
        missing_nodes=(module.PG_TEST_NODES[0],),
    )
    with pytest.raises(module.EvidenceBuildError) as exc:
        module.build_evidence()
    assert "PG test nodes missing" in str(exc.value)
    assert exc.value.exit_code == module.EXIT_PG_BINDING

    _configure(module, tmp_path, monkeypatch)
    monkeypatch.setattr(module, "PG_TEST_FILE_SHA256", _sha256(b"drift"))
    with pytest.raises(module.EvidenceBuildError) as exc:
        module.build_evidence()
    assert "bound SHA drift" in str(exc.value)
    assert exc.value.exit_code == module.EXIT_PG_BINDING

    _configure(module, tmp_path, monkeypatch)
    monkeypatch.setattr(
        module,
        "PG_TEST_FIXTURE_PATH",
        tmp_path / "missing" / "c1_slice_postgres_fixture.py",
    )
    with pytest.raises(module.EvidenceBuildError) as exc:
        module.build_evidence()
    assert "PG fixture file missing" in str(exc.value)
    assert exc.value.exit_code == module.EXIT_MISSING

    _configure(module, tmp_path, monkeypatch)
    monkeypatch.setattr(
        module,
        "PG_TEST_FIXTURE_SHA256",
        _sha256(b"fixture-drift"),
    )
    with pytest.raises(module.EvidenceBuildError) as exc:
        module.build_evidence()
    assert "PG fixture file bound SHA drift" in str(exc.value)
    assert exc.value.exit_code == module.EXIT_PG_BINDING


def test_cli_write_then_check_is_read_only_and_exact(tmp_path: Path) -> None:
    module = _load_generator()
    pg_path = _write_pg_fixture(tmp_path / "cli-pg", module)
    pg_sha = _sha256(pg_path.read_bytes())
    fixture_path = _write_fixture(tmp_path / "cli-fixture")
    fixture_sha = _sha256(fixture_path.read_bytes())
    slice_a = tmp_path / "C1SliceA.v1.json"
    slice_b = tmp_path / "C1SliceB.v1.json"
    slice_c = tmp_path / "C1SliceC.v1.json"
    aggregate = tmp_path / "P5C1SliceAcceptance.v1.json"

    common = [
        "--slice-a-path",
        str(slice_a),
        "--slice-b-path",
        str(slice_b),
        "--slice-c-path",
        str(slice_c),
        "--aggregate-path",
        str(aggregate),
        "--pg-test-path",
        str(pg_path),
        "--pg-sha256",
        pg_sha,
        "--pg-fixture-path",
        str(fixture_path),
        "--pg-fixture-sha256",
        fixture_sha,
    ]
    proc = _run_cli(*common)
    assert proc.returncode == 0, proc.stderr
    assert all(path.is_file() for path in (slice_a, slice_b, slice_c, aggregate))

    before = {path: path.stat() for path in (slice_a, slice_b, slice_c, aggregate)}
    proc = _run_cli("--check", *common)
    assert proc.returncode == 0, proc.stderr
    assert "unchanged" in proc.stdout
    for path, stat in before.items():
        after = path.stat()
        assert after.st_mtime_ns == stat.st_mtime_ns
        assert after.st_size == stat.st_size

    first_bytes = {
        path: path.read_bytes() for path in (slice_a, slice_b, slice_c, aggregate)
    }
    proc = _run_cli(*common)
    assert proc.returncode == 0, proc.stderr
    assert {
        path: path.read_bytes() for path in (slice_a, slice_b, slice_c, aggregate)
    } == first_bytes


def test_cli_check_missing_and_drift_fail_without_writing(tmp_path: Path) -> None:
    module = _load_generator()
    pg_path = _write_pg_fixture(tmp_path / "cli-missing", module)
    pg_sha = _sha256(pg_path.read_bytes())
    fixture_path = _write_fixture(tmp_path / "cli-fixture-missing")
    fixture_sha = _sha256(fixture_path.read_bytes())
    missing = tmp_path / "missing" / "C1SliceA.v1.json"
    common = [
        "--slice-a-path",
        str(missing),
        "--slice-b-path",
        str(tmp_path / "C1SliceB.v1.json"),
        "--slice-c-path",
        str(tmp_path / "C1SliceC.v1.json"),
        "--aggregate-path",
        str(tmp_path / "P5C1SliceAcceptance.v1.json"),
        "--pg-test-path",
        str(pg_path),
        "--pg-sha256",
        pg_sha,
        "--pg-fixture-path",
        str(fixture_path),
        "--pg-fixture-sha256",
        fixture_sha,
    ]
    proc = _run_cli("--check", *common)
    assert proc.returncode == module.EXIT_MISSING
    assert "missing" in proc.stderr
    assert "no write performed" in proc.stderr

    write = _run_cli(*common)
    assert write.returncode == 0, write.stderr
    aggregate = tmp_path / "P5C1SliceAcceptance.v1.json"
    corrupted = b'{"drift": true}'
    aggregate.write_bytes(corrupted)
    proc = _run_cli("--check", *common)
    assert proc.returncode == module.EXIT_DRIFT
    assert "no write performed" in proc.stderr
    assert aggregate.read_bytes() == corrupted


def test_cli_fails_closed_on_pg_node_missing_and_sha_drift(tmp_path: Path) -> None:
    module = _load_generator()
    pg_path = _write_pg_fixture(
        tmp_path / "cli-node",
        module,
        missing_nodes=(module.PG_TEST_NODES[1],),
    )
    pg_sha = _sha256(pg_path.read_bytes())
    fixture_path = _write_fixture(tmp_path / "cli-node-fixture")
    fixture_sha = _sha256(fixture_path.read_bytes())
    common = [
        "--slice-a-path",
        str(tmp_path / "C1SliceA.v1.json"),
        "--slice-b-path",
        str(tmp_path / "C1SliceB.v1.json"),
        "--slice-c-path",
        str(tmp_path / "C1SliceC.v1.json"),
        "--aggregate-path",
        str(tmp_path / "P5C1SliceAcceptance.v1.json"),
        "--pg-test-path",
        str(pg_path),
        "--pg-sha256",
        pg_sha,
        "--pg-fixture-path",
        str(fixture_path),
        "--pg-fixture-sha256",
        fixture_sha,
    ]
    proc = _run_cli(*common)
    assert proc.returncode == module.EXIT_PG_BINDING
    assert "PG test nodes missing" in proc.stderr
    assert not (tmp_path / "C1SliceA.v1.json").exists()

    drifted_sha = _sha256(b"drift")
    drift_args = list(common)
    drift_args[drift_args.index("--pg-sha256") + 1] = drifted_sha
    proc = _run_cli(*drift_args)
    assert proc.returncode == module.EXIT_PG_BINDING
    assert "bound SHA drift" in proc.stderr


def test_live_canonical_check_when_pg_bound() -> None:
    module = _load_generator()
    if not module.PG_TEST_FILE_SHA256 or not module.PG_TEST_PATH.is_file():
        pytest.skip("PG gate file is not bound yet")
    proc = _run_cli("--check")
    assert proc.returncode == 0, proc.stderr
    assert "unchanged" in proc.stdout
    assert module.SLICE_PATHS["A"].is_file()
    assert module.SLICE_PATHS["B"].is_file()
    assert module.SLICE_PATHS["C"].is_file()
    assert module.AGGREGATE_PATH.is_file()
