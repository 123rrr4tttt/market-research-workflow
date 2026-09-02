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
    TRACE_REL,
    build_documents,
    parse_design,
)

REPO = BACKEND.parents[1]
DESIGN_ROOT = Path(
    os.environ.get("C7_SEMANTIC_MOVEMENT_DESIGN_ROOT", str(REPO))
).resolve()
SCRIPT = BACKEND / "scripts/check_successor_c7_semantic_movements.py"


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


def test_persisted_documents_match_and_check_is_read_only() -> None:
    documents = build_documents(DESIGN_ROOT)
    for relative, expected in documents.items():
        assert (REPO / relative).read_bytes() == expected, relative
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
    assert result.returncode == 0, result.stdout + result.stderr
    after = {
        relative: ((REPO / relative).read_bytes(), (REPO / relative).stat().st_mtime_ns)
        for relative in documents
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
