"""C7 semantic movement v3 completeness tests."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scripts.check_successor_c7_semantic_movements import (
    ALLOWED_DISPOSITIONS,
    BLOCKER_IDS,
    DECLARED_LOSS_IDS,
    DESIGN_REL,
    INVENTORY_REL,
    LEGACY_TRACES,
    MATRIX_REL,
    REQUIRED_FIELDS,
    STATUS,
    TOPIC,
    TRACE_REL,
    build_documents,
    parse_design,
)

REPO = BACKEND.parents[1]
DESIGN_ROOT = Path(
    os.environ.get("C7_SEMANTIC_MOVEMENT_DESIGN_ROOT", str(REPO))
).resolve()
SCRIPT = BACKEND / "scripts/check_successor_c7_semantic_movements.py"
STAGE_B8_ROOT = (
    REPO
    / TOPIC
    / "evidence/exact-byte-rebind/stage-b8-2026-09-05/candidates/C7"
).resolve()
CANDIDATE_REL = STAGE_B8_ROOT / "candidate.v2.json"
FRAGMENT_REL = (
    REPO
    / TOPIC
    / "evidence/exact-byte-rebind/stage-b8-2026-09-05/fragments/C7.json"
).resolve()
STAGE_B12_ROOT = (
    REPO
    / TOPIC
    / "evidence/exact-byte-rebind/stage-b12-2026-09-05/candidates/C7"
).resolve()
B12_CANDIDATE_REL = STAGE_B12_ROOT / "candidate.v2.json"
B12_FRAGMENT_REL = (
    REPO
    / TOPIC
    / "evidence/exact-byte-rebind/stage-b12-2026-09-05/fragments/C7.json"
).resolve()
STAGE_B23_ROOT = (
    REPO
    / TOPIC
    / "evidence/exact-byte-rebind/stage-b23-2026-09-07/candidates/C7"
).resolve()
CURRENT_CANDIDATE_REL = STAGE_B23_ROOT / "candidate.v2.json"
CURRENT_FRAGMENT_REL = (
    REPO
    / TOPIC
    / "evidence/exact-byte-rebind/stage-b23-2026-09-07/fragments/C7.json"
).resolve()
B12_CANDIDATE_ID = (
    "763dfb78825e9664c9e4c3cbfa3245c7566669c29918957304a863b6311c5327"
)

FROZEN_PREDECESSOR_EVIDENCE = {
    INVENTORY_REL: {
        "sha256": "8ca654e374b009f5ed97fec337a093a1751367f35c579f8e1afdc0e2273ac271",
        "bytes": 5139,
        "content_digest": "4c92fef4f38ebe6b8d5ddf95771bc6b4b4da3ca132ac177cbeddea706ebe4bf8",
    },
    MATRIX_REL: {
        "sha256": "b9d877f0d24b58aedc077b2ed36e2293859eec660917c1ef9ee03f18fe112515",
        "bytes": 24999,
        "content_digest": "b4d15c086a2d9699061f934fc57880741f6959c939a7a493b0420fafc7fd05fd",
    },
    TRACE_REL: {
        "sha256": "43c72f47a239af8f3f94070259469b03dbbf18bec3a9038f9ddc49c94670d7b5",
        "bytes": 9506,
        "content_digest": "2f1c0f179449b26ad1403cf6dda0034890b9020ccde4900ce4487e8ec485f92d",
    },
}

REQUIRED_B23_CANDIDATE_BINDINGS = {
    "main/backend/app/services/ingest/cleanup_executor.py": "sources",
    "main/backend/app/successor_runtime/capabilities/ingest_c7_movements.py": (
        "sources"
    ),
    "main/backend/app/successor_runtime/capabilities/ingest_c7_common.py": "sources",
    "main/backend/app/successor_runtime/capabilities/ingest_c7_program.py": "sources",
    "main/backend/app/successor_runtime/capabilities/ingest_c7_registry.py": (
        "sources"
    ),
    "scripts/generate_c7_exact_byte_rebind.py": "sources",
    "tests/test_c7_runtime_failure_closure.py": "tests",
    "tests/test_c7_semantic_registration.py": "tests",
}
REQUIRED_B23_FRAGMENT_BINDINGS = {
    "main/backend/app/services/ingest/cleanup_executor.py": "source_bindings",
    "main/backend/app/successor_runtime/capabilities/ingest_c7_movements.py": (
        "implementation_bindings"
    ),
    "main/backend/app/successor_runtime/capabilities/ingest_c7_common.py": (
        "implementation_bindings"
    ),
    "main/backend/app/successor_runtime/capabilities/ingest_c7_program.py": (
        "implementation_bindings"
    ),
    "main/backend/app/successor_runtime/capabilities/ingest_c7_registry.py": (
        "implementation_bindings"
    ),
}


def _load(repo_root: Path, relative: Path) -> dict:
    return json.loads((repo_root / relative).read_text(encoding="utf-8"))


def test_design_has_twenty_unique_rows_and_zero_blockers() -> None:
    rows = parse_design((DESIGN_ROOT / DESIGN_REL).read_text(encoding="utf-8"))
    assert len(rows) == 20
    assert len({row["movement_id"] for row in rows}) == 20
    assert all(row["disposition"] in ALLOWED_DISPOSITIONS for row in rows)
    assert all(all(row[field] for field in REQUIRED_FIELDS) for row in rows)
    blockers = tuple(
        row["movement_id"] for row in rows if row["disposition"] == "UNASSIGNED_BLOCKER"
    )
    assert blockers == BLOCKER_IDS == ()


def test_matrix_contract_topology_and_authority_ceiling() -> None:
    documents = build_documents(DESIGN_ROOT)
    matrix = json.loads(documents[MATRIX_REL])
    rows = matrix["movements"]
    assert len(rows) == 20
    assert len({row["movement_id"] for row in rows}) == 20
    for row in rows:
        assert set(REQUIRED_FIELDS) <= set(row), row["movement_id"]
        assert row["disposition"] in ALLOWED_DISPOSITIONS, row["movement_id"]
    assert matrix["status"] == STATUS
    assert matrix["unassigned_blockers"] == 0
    assert matrix["unassigned_blocker_ids"] == []
    assert matrix["blocked_dependency_scopes"] == [
        "C7 pilot",
        "C7 family",
        "Slice A",
        "P4 promotion",
        "candidate",
    ]
    topology = matrix["decision_topology"]
    assert topology["one_of"] is True
    assert topology["alternatives_serial"] is False
    assert topology["commutativity_claim"] == "NOT_CLAIMED"
    assert topology["legacy_dual_flag_conflicts_preserved"] == [
        "CHUNK_FIRST+extract_required",
        "SUMMARIZE_FIRST+extract_required",
    ]
    assert matrix["promotion"] is False
    assert matrix["candidate"] is False
    assert not any(matrix["authority_ceiling"].values())


def test_trace_and_loss_bundle_exact_losses_and_review_candidates() -> None:
    documents = build_documents(DESIGN_ROOT)
    bundle = json.loads(documents[TRACE_REL])
    assert bundle["status"] == STATUS
    assert bundle["zero_loss_declared"] is False
    assert bundle["unaccepted_loss_blockers"] == []
    loss_ids = [loss["movement_id"] for loss in bundle["declared_losses"]]
    assert loss_ids == list(DECLARED_LOSS_IDS)
    assert all(loss["account"] for loss in bundle["declared_losses"])
    assert [trace["trace_id"] for trace in bundle["legacy_traces"]] == [
        trace_id for trace_id, _ in LEGACY_TRACES
    ]
    for trace in bundle["legacy_traces"]:
        assert trace["target_status"] == "REVIEW_CANDIDATE"
        assert trace["test_refs"], trace["trace_id"]
        for ref in trace["test_refs"]:
            assert ref["path"].startswith("main/")
            assert ref["sha256"] and ref["bytes"] > 0 and ref["lines"] > 0
            full = DESIGN_ROOT / ref["path"]
            assert full.is_file(), ref["path"]
            text = full.read_text(encoding="utf-8", errors="replace")
            assert f"def {ref['node_id']}" in text or f"class {ref['node_id']}" in text


def test_exact_design_refs_resolve() -> None:
    documents = build_documents(DESIGN_ROOT)
    matrix = json.loads(documents[MATRIX_REL])
    for row in matrix["movements"]:
        for field in ("source_evidence", "target_realization", "acceptance_trace"):
            for ref in row[field].split(";"):
                ref = ref.strip()
                if not ref.startswith(("main/", "development/")):
                    continue
                path_part, _, node_id = ref.partition("::")
                pointer = None
                if "#" in path_part:
                    path_part, pointer = path_part.split("#", 1)
                full = DESIGN_ROOT / path_part
                assert full.is_file(), (row["movement_id"], field, ref)
                if node_id:
                    text = full.read_text(encoding="utf-8", errors="replace")
                    assert f"def {node_id}" in text or f"class {node_id}" in text, (
                        row["movement_id"],
                        field,
                        ref,
                    )
                if pointer:
                    assert full.suffix == ".json", (row["movement_id"], field, ref)
                    doc = json.loads(full.read_text(encoding="utf-8"))
                    resolved = False
                    if isinstance(doc, list):
                        resolved = any(
                            isinstance(item, dict) and str(item.get("cell")) == pointer
                            for item in doc
                        )
                    elif isinstance(doc, dict):
                        resolved = pointer in doc
                    assert resolved, (row["movement_id"], field, ref)


def test_canonical_digests_and_inventory_projection() -> None:
    documents = build_documents(DESIGN_ROOT)
    matrix = json.loads(documents[MATRIX_REL])
    inventory = json.loads(documents[INVENTORY_REL])
    bundle = json.loads(documents[TRACE_REL])
    payload = {key: value for key, value in matrix.items() if key != "content_digest"}
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert (
        matrix["content_digest"]
        == hashlib.sha256((canonical + "\n").encode("utf-8")).hexdigest()
    )
    assert inventory["matrix_content_digest"] == matrix["content_digest"]
    assert inventory["movement_ids"] == [
        row["movement_id"] for row in matrix["movements"]
    ]
    assert matrix["trace_and_loss_digest"] == bundle["content_digest"]


def test_frozen_predecessor_evidence_bytes_and_known_hashes() -> None:
    for relative, expected in FROZEN_PREDECESSOR_EVIDENCE.items():
        payload = (REPO / relative).read_bytes()
        assert len(payload) == expected["bytes"], relative
        assert len(payload.splitlines()) == 1, relative
        assert hashlib.sha256(payload).hexdigest() == expected["sha256"], relative
        document = json.loads(payload)
        assert document["content_digest"] == expected["content_digest"], relative


def test_current_runtime_checker_reports_drift_without_writing() -> None:
    documents = build_documents(DESIGN_ROOT)
    before = {
        relative: ((REPO / relative).read_bytes(), (REPO / relative).stat().st_mtime_ns)
        for relative in documents
    }
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(REPO),
            "--design-root",
            str(DESIGN_ROOT),
            "--check",
        ],
        cwd=BACKEND,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "DRIFT"
    assert report["paths"] == [
        INVENTORY_REL.as_posix(),
        MATRIX_REL.as_posix(),
        TRACE_REL.as_posix(),
    ]
    assert (REPO / INVENTORY_REL).read_bytes() != documents[INVENTORY_REL]
    assert (REPO / MATRIX_REL).read_bytes() != documents[MATRIX_REL]
    assert (REPO / TRACE_REL).read_bytes() != documents[TRACE_REL]
    after = {
        relative: ((REPO / relative).read_bytes(), (REPO / relative).stat().st_mtime_ns)
        for relative in documents
    }
    assert after == before


def test_stage_b8_predecessor_is_history_only_without_current_authority() -> None:
    candidate = json.loads(CANDIDATE_REL.read_text(encoding="utf-8"))
    fragment = json.loads(FRAGMENT_REL.read_text(encoding="utf-8"))
    assert candidate["schema"] == "mrw.family_fragment_rebind.candidate.v2"
    assert candidate["status"] == "CANDIDATE_VALID_NOT_AUTHORITY"
    assert candidate["amendment"] == (
        "STAGE_B8_BOUND_WITNESS_REBIND_CANDIDATE_NOT_AUTHORITY"
    )
    assert candidate["family"] == "C7"
    assert fragment["family"] == "C7"
    assert fragment["status"] == "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"
    assert all(value is False for value in fragment["authority"].values())

    before = {
        path.relative_to(STAGE_B8_ROOT).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes(),
        )
        for path in sorted(STAGE_B8_ROOT.rglob("*"))
        if path.is_file()
    }
    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts/stage_family_fragment_rebind.py"),
            "check-candidate",
            "--repo-root",
            str(REPO),
            "--candidate",
            CANDIDATE_REL.relative_to(REPO).as_posix(),
            "--history-only",
        ],
        cwd=BACKEND,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "candidate_id": candidate["candidate_id"],
        "family": "C7",
        "status": "HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY",
    }
    after = {
        path.relative_to(STAGE_B8_ROOT).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes(),
        )
        for path in sorted(STAGE_B8_ROOT.rglob("*"))
        if path.is_file()
    }
    assert after == before


def test_stage_b12_predecessor_is_history_only_without_current_authority() -> None:
    candidate = json.loads(B12_CANDIDATE_REL.read_text(encoding="utf-8"))
    fragment = json.loads(B12_FRAGMENT_REL.read_text(encoding="utf-8"))
    assert candidate["schema"] == "mrw.family_fragment_rebind.candidate.v2"
    assert candidate["candidate_id"] == B12_CANDIDATE_ID
    assert candidate["status"] == "CANDIDATE_VALID_NOT_AUTHORITY"
    assert candidate["amendment"] == (
        "STAGE_B12_C7_FINAL_FAILURE_REBIND_CANDIDATE_NOT_AUTHORITY"
    )
    assert candidate["family"] == "C7"
    assert fragment["family"] == "C7"
    assert fragment["status"] == "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"
    assert all(value is False for value in fragment["authority"].values())

    before = {
        path.relative_to(STAGE_B12_ROOT).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes(),
        )
        for path in sorted(STAGE_B12_ROOT.rglob("*"))
        if path.is_file()
    }
    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts/stage_family_fragment_rebind.py"),
            "check-candidate",
            "--repo-root",
            str(REPO),
            "--candidate",
            B12_CANDIDATE_REL.relative_to(REPO).as_posix(),
            "--history-only",
        ],
        cwd=BACKEND,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "candidate_id": B12_CANDIDATE_ID,
        "family": "C7",
        "status": "HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY",
    }
    after = {
        path.relative_to(STAGE_B12_ROOT).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes(),
        )
        for path in sorted(STAGE_B12_ROOT.rglob("*"))
        if path.is_file()
    }
    assert after == before


def test_stage_b23_candidate_snapshot_binds_recorded_bytes_read_only(tmp_path: Path) -> None:
    from .historical_fixture import materialize_candidate
    isolated_root = tmp_path / "candidate-replay"
    materialize_candidate(CURRENT_CANDIDATE_REL, isolated_root)
    candidate = json.loads(CURRENT_CANDIDATE_REL.read_text(encoding="utf-8"))
    fragment = json.loads(CURRENT_FRAGMENT_REL.read_text(encoding="utf-8"))
    assert candidate["schema"] == "mrw.family_fragment_rebind.candidate.v2"
    assert isinstance(candidate["candidate_id"], str)
    assert len(candidate["candidate_id"]) == 64
    assert candidate["status"] == "CANDIDATE_VALID_NOT_AUTHORITY"
    assert candidate["amendment"] == (
        "STAGE_B23_C7_CURRENT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
    )
    assert candidate["family"] == "C7"
    assert fragment["family"] == "C7"
    assert fragment["status"] == "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"
    assert all(value is False for value in fragment["authority"].values())

    candidate_refs = {
        reference["path"]: reference
        for group in ("sources", "tests")
        for reference in candidate[group]
    }
    for path, group in REQUIRED_B23_CANDIDATE_BINDINGS.items():
        assert path in candidate_refs, (group, path)
        live_payload = (isolated_root / path).read_bytes()
        digest = hashlib.sha256(live_payload).hexdigest()
        assert candidate_refs[path]["file_sha256"] == digest, path
        assert candidate_refs[path]["bytes"] == len(live_payload), path

    fragment_bindings = {
        binding["path"]: binding
        for group in set(REQUIRED_B23_FRAGMENT_BINDINGS.values())
        for binding in fragment[group]
    }
    for path, fragment_group in REQUIRED_B23_FRAGMENT_BINDINGS.items():
        live_payload = (isolated_root / path).read_bytes()
        digest = hashlib.sha256(live_payload).hexdigest()
        assert fragment_bindings[path]["sha256"] == digest, path
        assert fragment_bindings[path]["bytes"] == len(live_payload), path
        assert fragment_bindings[path]["role"]
        assert REQUIRED_B23_FRAGMENT_BINDINGS[path] == fragment_group

    fragment_reference = candidate["fragments"][0]
    fragment_payload = CURRENT_FRAGMENT_REL.read_bytes()
    assert fragment_reference["path"] == (
        CURRENT_FRAGMENT_REL.relative_to(REPO).as_posix()
    )
    assert fragment_reference["bytes"] == len(fragment_payload)
    assert fragment_reference["file_sha256"] == hashlib.sha256(
        fragment_payload
    ).hexdigest()

    before = {
        path.relative_to(STAGE_B23_ROOT).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes(),
        )
        for path in sorted(STAGE_B23_ROOT.rglob("*"))
        if path.is_file()
    }
    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts/stage_family_fragment_rebind.py"),
            "check-candidate",
            "--repo-root",
            str(isolated_root),
            "--candidate",
            CURRENT_CANDIDATE_REL.relative_to(REPO).as_posix(),
        ],
        cwd=BACKEND,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "candidate_id": candidate["candidate_id"],
        "family": "C7",
        "status": "CANDIDATE_VALID_NOT_AUTHORITY",
    }
    after = {
        path.relative_to(STAGE_B23_ROOT).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes(),
        )
        for path in sorted(STAGE_B23_ROOT.rglob("*"))
        if path.is_file()
    }
    assert after == before


def test_check_drift_reports_one_without_writing(tmp_path: Path) -> None:
    documents = build_documents(DESIGN_ROOT)
    for relative, expected in documents.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(expected)
    matrix_path = tmp_path / MATRIX_REL
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    matrix["unassigned_blockers"] = 1
    matrix_path.write_text(
        json.dumps(matrix, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    before = matrix_path.read_bytes()
    before_mtime = matrix_path.stat().st_mtime_ns
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--design-root",
            str(DESIGN_ROOT),
            "--check",
        ],
        cwd=BACKEND,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert matrix_path.read_bytes() == before
    assert matrix_path.stat().st_mtime_ns == before_mtime


def test_check_invalid_input_returns_two(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--design-root",
            str(tmp_path),
            "--check",
        ],
        cwd=BACKEND,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, result.stdout + result.stderr
