from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validate_successor_migration_batch import (
    BATCH_SCHEMA,
    FIXED_ISSUE_CODES,
    P3_AGGREGATE_SCHEMA,
    P3_CELL_ORDER,
    P3_FAMILY_ORDER,
    canonical_content_digest,
    fragment_cell_ids,
    run_cli,
    validate_batch,
    validate_p3_aggregate_document,
)

pytestmark = pytest.mark.unit


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(root: Path, relpath: str, text: str) -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _binding(root: Path, relpath: str, text: str) -> dict[str, Any]:
    path = _write(root, relpath, text)
    data = path.read_bytes()
    return {
        "path": relpath,
        "sha256": _sha256(data),
        "bytes": len(data),
        "lines": data.count(b"\n"),
    }


def _authority() -> dict[str, bool]:
    return {
        "production_canonical_write": False,
        "live_provider": False,
        "external_delivery": False,
        "cutover": False,
        "authority_transfer": False,
        "legacy_retired": False,
    }


def make_fragment(
    root: Path,
    *,
    phase: str,
    family: str,
    cell_ids: tuple[str, ...],
    bindings: tuple[tuple[str, str], ...] = (
        ("main/backend/src/example.py", "class Example:\n    pass\n"),
    ),
    evidence: tuple[Mapping[str, Any], ...] = (),
    observed_symbols: tuple[str, ...] = (),
    schema: str | None = None,
    status: str = "FAMILY_LOCAL_NOT_PROMOTED",
    line_semantics: str | None = None,
) -> dict[str, Any]:
    relpath = f"evidence/{phase.lower()}-fragments/{family}.json"
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    binding_entries = [_binding(root, rel, text) for rel, text in bindings]
    fragment: dict[str, Any] = {
        "schema": schema
        or f"mrw.functorial_successor.{phase.lower()}_{family.lower()}_evidence_fragment.v1",
        "family": family,
        "phase": phase,
        "status": status,
        "cells": {cell_id: {"cell": cell_id} for cell_id in cell_ids},
        "files": binding_entries,
        "source_evidence": [
            {
                "path": item.get("path", bindings[0][0]),
                "symbol_or_lines": item.get("symbol_or_lines", "lines 1-1"),
                "claim": item.get("claim", "deterministic fixture"),
            }
            for item in evidence
        ],
        "observed_symbols": list(observed_symbols),
        "authority_ceiling": _authority(),
        "generated_at_utc": "2030-09-01T00:00:00Z",
    }
    if line_semantics is not None:
        fragment["line_semantics"] = line_semantics
    fragment["content_digest"] = canonical_content_digest(fragment)
    path.write_text(json.dumps(fragment, sort_keys=True) + "\n", encoding="utf-8")
    return fragment


def make_aggregate(
    root: Path,
    *,
    phase: str,
    families: list[str],
    cell_ids: list[str],
    status: str = "NOT_PROMOTED",
) -> dict[str, Any]:
    relpath = f"evidence/{phase.lower()}-aggregate.json"
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    aggregate: dict[str, Any] = {
        "schema": f"mrw.functorial_successor.{phase.lower()}_aggregate_evidence.v1",
        "phase": phase,
        "status": status,
        "families": families,
        "cell_ids": cell_ids,
        "authority_ceiling": _authority(),
        "generated_at_utc": "2030-09-01T00:00:00Z",
    }
    aggregate["content_digest"] = canonical_content_digest(aggregate)
    path.write_text(json.dumps(aggregate, sort_keys=True) + "\n", encoding="utf-8")
    return aggregate


def _chain_artifact(root: Path, name: str) -> tuple[str, dict[str, Any]]:
    path = root / f"evidence/{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": f"mrw.functorial_successor.{name}.v1",
        "status": "FROZEN_LOCAL_ONLY_NOT_LIVE",
        "content": name,
    }
    artifact["content_digest"] = canonical_content_digest(artifact)
    path.write_text(json.dumps(artifact, sort_keys=True) + "\n", encoding="utf-8")
    data = path.read_bytes()
    return str(path), {
        "path": str(path),
        "file_sha256": _sha256(data),
        "content_digest": artifact["content_digest"],
    }


def _entry_binding(root: Path, relpath: str) -> dict[str, Any]:
    data = (root / relpath).read_bytes()
    return {
        "file_sha256": _sha256(data),
        "bytes": len(data),
        "lines": data.count(b"\n"),
    }


def make_batch(
    root: Path,
    *,
    phases: tuple[str, ...] = ("P3",),
    fragments: list[dict[str, Any]],
    aggregates: list[dict[str, Any]],
    **overrides: Any,
) -> dict[str, Any]:
    _, p1_artifact = _chain_artifact(root, "P1FunctorizationEligibility.v1")
    _, p2_artifact = _chain_artifact(root, "P2C21Selection.v1")
    fragment_entries = []
    for index, fragment in enumerate(fragments):
        relpath = Path(fragment["_path"])
        entry: dict[str, Any] = {
            "phase": fragment["phase"],
            "family": fragment["family"],
            "path": str(relpath),
            **_entry_binding(root, str(relpath)),
        }
        if "line_semantics" in fragment:
            entry["line_semantics"] = fragment["line_semantics"]
        if "aggregate_ref" in fragment:
            entry["aggregate_ref"] = fragment["aggregate_ref"]
        if "p1_p2_chain" in fragment:
            entry["p1_p2_chain"] = fragment["p1_p2_chain"]
        fragment_entries.append(entry)
    aggregate_entries = []
    for aggregate in aggregates:
        relpath = Path(aggregate["_path"])
        aggregate_entries.append(
            {
                "phase": aggregate["phase"],
                "path": str(relpath),
                "schema": aggregate["schema"],
                "status": aggregate["status"],
                "families": aggregate["families"],
                "cell_ids": aggregate["cell_ids"],
                **_entry_binding(root, str(relpath)),
                "content_digest": aggregate["content_digest"],
                "authority_ceiling": aggregate["authority_ceiling"],
            }
        )
    batch: dict[str, Any] = {
        "schema": BATCH_SCHEMA,
        "batch_id": "batch:p3-p4:fixture",
        "root": ".",
        "phase_union": list(phases),
        "fragments": fragment_entries,
        "aggregates": aggregate_entries,
        "p1_artifact": p1_artifact,
        "p2_artifact": p2_artifact,
    }
    batch.update(overrides)
    return batch


def _default_batch(
    root: Path, *, fragments: list[dict[str, Any]] | None = None, **overrides: Any
):
    if fragments is None:
        fragments = []
        for index, family in enumerate(("C2", "C3")):
            fragment = make_fragment(
                root,
                phase="P3",
                family=family,
                cell_ids=(f"{family}.1",),
            )
            fragment["_path"] = f"evidence/p3-fragments/{family}.json"
            fragments.append(fragment)
    return make_batch(root, fragments=fragments, aggregates=[], **overrides)


def test_validate_batch_accepts_complete_phase_and_reads_bindings(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    fragments = []
    cell_ids: list[str] = []
    for index, family in enumerate(("C2", "C3", "C4", "C5", "C6")):
        cell = f"{family}.1"
        cell_ids.append(cell)
        fragment = make_fragment(
            root,
            phase="P3",
            family=family,
            cell_ids=(cell,),
            bindings=(
                (f"main/backend/src/{family}.py", f"class {family}:\n    pass\n"),
            ),
            evidence=(
                {
                    "path": f"main/backend/src/{family}.py",
                    "symbol_or_lines": f"{family}, lines 1-1",
                    "claim": "fixture evidence",
                },
            ),
            observed_symbols=(family,),
        )
        fragment["_path"] = f"evidence/p3-fragments/{family}.json"
        fragments.append(fragment)
    aggregate = make_aggregate(
        root,
        phase="P3",
        families=["C2", "C3", "C4", "C5", "C6"],
        cell_ids=cell_ids,
    )
    aggregate["_path"] = "evidence/p3-aggregate.json"
    batch = make_batch(root, fragments=fragments, aggregates=[aggregate])
    report = validate_batch(batch, root)
    assert report.is_valid(), [issue.as_dict() for issue in report.issues]
    assert report.status == "VALID"
    assert report.exit_code == 0
    assert report.counts["fragments"] == 5
    assert report.counts["cells"] == 5
    assert report.counts["source_bindings"] == 5
    assert report.counts["source_evidence"] == 5
    assert report.families_by_phase["P3"] == ("C2", "C3", "C4", "C5", "C6")


def test_batch_not_object_is_reported(tmp_path: Path) -> None:
    report = validate_batch([], tmp_path)
    assert not report.is_valid()
    assert [issue.code for issue in report.issues] == ["BATCH_NOT_OBJECT"]


def test_fragment_cell_ids_accepts_normalized_list_and_legacy_mapping() -> None:
    assert fragment_cell_ids({"cells": {"C2.2": {}, "C2.3": {}}}) == (
        "C2.2",
        "C2.3",
    )
    assert fragment_cell_ids({"cells": [{"cell_id": "C3.1"}, {"cell_id": "C3.2"}]}) == (
        "C3.1",
        "C3.2",
    )
    assert fragment_cell_ids({"cells": [{"cell": "C3.1"}]}) is None


def test_required_and_unexpected_batch_fields(tmp_path: Path) -> None:
    batch = _default_batch(tmp_path)
    del batch["p1_artifact"]
    batch["surprise"] = True
    report = validate_batch(batch, tmp_path)
    codes = [issue.code for issue in report.issues]
    assert "REQUIRED_FIELD_MISSING" in codes
    assert "UNEXPECTED_FIELD" in codes


def test_duplicate_cell_ids_across_fragments(tmp_path: Path) -> None:
    first = make_fragment(tmp_path, phase="P3", family="C2", cell_ids=("C2.1",))
    first["_path"] = "evidence/p3-fragments/C2.json"
    second = make_fragment(tmp_path, phase="P3", family="C3", cell_ids=("C2.1",))
    second["_path"] = "evidence/p3-fragments/C3.json"
    report = validate_batch(
        make_batch(tmp_path, fragments=[first, second], aggregates=[]), tmp_path
    )
    assert any(issue.code == "DUPLICATE_CELL_ID" for issue in report.issues)


def test_phase_union_and_family_coverage_checks(tmp_path: Path) -> None:
    fragment = make_fragment(tmp_path, phase="P3", family="C2", cell_ids=("C2.1",))
    fragment["_path"] = "evidence/p3-fragments/C2.json"
    batch = make_batch(
        tmp_path,
        phases=("P3",),
        fragments=[fragment],
        aggregates=[],
    )
    report = validate_batch(batch, tmp_path)
    codes = [issue.code for issue in report.issues]
    assert "PHASE_FAMILY_MISSING" in codes

    declared_mismatch = make_batch(
        tmp_path,
        phases=("P4",),
        fragments=[fragment],
        aggregates=[],
    )
    report = validate_batch(declared_mismatch, tmp_path)
    assert any(issue.code == "PHASE_UNION_MISMATCH" for issue in report.issues)


def test_fragment_content_digest_mismatch(tmp_path: Path) -> None:
    fragment = make_fragment(tmp_path, phase="P3", family="C2", cell_ids=("C2.1",))
    fragment["_path"] = "evidence/p3-fragments/C2.json"
    path = tmp_path / fragment["_path"]
    parsed = json.loads(path.read_text(encoding="utf-8"))
    parsed["status"] = "TAMPERED"
    path.write_text(json.dumps(parsed, sort_keys=True), encoding="utf-8")
    report = validate_batch(
        make_batch(tmp_path, fragments=[fragment], aggregates=[]), tmp_path
    )
    assert any(
        issue.code == "FRAGMENT_CONTENT_DIGEST_MISMATCH" for issue in report.issues
    )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("sha256", "0" * 64, "SOURCE_BINDING_SHA256_MISMATCH"),
        ("bytes", 1, "SOURCE_BINDING_BYTES_MISMATCH"),
        ("lines", 1, "SOURCE_BINDING_LINES_MISMATCH"),
    ],
)
def test_source_binding_hash_bytes_lines_checks(
    tmp_path: Path,
    field: str,
    value: int | str,
    expected: str,
) -> None:
    fragment = make_fragment(
        tmp_path,
        phase="P3",
        family="C2",
        cell_ids=("C2.1",),
        bindings=(("main/backend/src/example.py", "class Example:\n    pass\n"),),
    )
    fragment["_path"] = "evidence/p3-fragments/C2.json"
    batch = make_batch(tmp_path, fragments=[fragment], aggregates=[])
    source_binding = fragment["files"][0]
    source_binding[field] = value
    fragment_path = tmp_path / fragment["_path"]
    fragment_path.write_text(json.dumps(fragment, sort_keys=True), encoding="utf-8")
    binding = batch["fragments"][0]
    binding["file_sha256"] = _sha256(fragment_path.read_bytes())
    binding["bytes"] = len(fragment_path.read_bytes())
    binding["lines"] = fragment_path.read_bytes().count(b"\n")
    report = validate_batch(batch, tmp_path)
    assert any(issue.code == expected for issue in report.issues)


def test_source_evidence_line_and_symbol_checks(tmp_path: Path) -> None:
    fragment = make_fragment(
        tmp_path,
        phase="P3",
        family="C2",
        cell_ids=("C2.1",),
        bindings=(("main/backend/src/example.py", "class Example:\n    pass\n"),),
        evidence=(
            {
                "path": "main/backend/src/example.py",
                "symbol_or_lines": "MISSING_SYMBOL, lines 999-1000",
                "claim": "out of range",
            },
        ),
    )
    fragment["_path"] = "evidence/p3-fragments/C2.json"
    report = validate_batch(
        make_batch(tmp_path, fragments=[fragment], aggregates=[]), tmp_path
    )
    codes = [issue.code for issue in report.issues]
    assert "SOURCE_EVIDENCE_LINE_OUT_OF_RANGE" in codes
    assert "SOURCE_EVIDENCE_SYMBOL_MISSING" in codes


def test_observed_symbol_presence_requires_bound_sources(tmp_path: Path) -> None:
    fragment = make_fragment(
        tmp_path,
        phase="P3",
        family="C2",
        cell_ids=("C2.1",),
        bindings=(("main/backend/src/example.py", "class Example:\n    pass\n"),),
        observed_symbols=("ABSENT_SYMBOL",),
    )
    fragment["_path"] = "evidence/p3-fragments/C2.json"
    report = validate_batch(
        make_batch(tmp_path, fragments=[fragment], aggregates=[]), tmp_path
    )
    assert any(
        issue.code == "SOURCE_EVIDENCE_SYMBOL_MISSING" for issue in report.issues
    )


def test_p1_p2_chain_mismatch(tmp_path: Path) -> None:
    fragment = make_fragment(tmp_path, phase="P3", family="C2", cell_ids=("C2.1",))
    fragment["_path"] = "evidence/p3-fragments/C2.json"
    batch = make_batch(tmp_path, fragments=[fragment], aggregates=[])
    p1_artifact_path = tmp_path / "evidence/P1FunctorizationEligibility.v1.json"
    p1_artifact_path.write_text("{not json", encoding="utf-8")
    report = validate_batch(batch, tmp_path)
    codes = [issue.code for issue in report.issues]
    assert "P1_ARTIFACT_CONTENT_DIGEST_MISMATCH" in codes

    fragment["p1_p2_chain"] = {
        "p1_artifact": {
            "path": "other.json",
            "file_sha256": "0" * 64,
            "content_digest": "1" * 64,
        },
        "p2_artifact": {
            "path": str(tmp_path / "evidence/P2C21Selection.v1.json"),
            "file_sha256": _sha256(
                (tmp_path / "evidence/P2C21Selection.v1.json").read_bytes()
            ),
            "content_digest": json.loads(
                (tmp_path / "evidence/P2C21Selection.v1.json").read_text(
                    encoding="utf-8"
                )
            )["content_digest"],
        },
    }
    path = tmp_path / fragment["_path"]
    path.write_text(json.dumps(fragment, sort_keys=True), encoding="utf-8")
    batch["fragments"][0]["p1_p2_chain"] = fragment["p1_p2_chain"]
    report = validate_batch(batch, tmp_path)
    assert any(issue.code == "P1_P2_CHAIN_MISMATCH" for issue in report.issues)


def test_authority_ceiling_violation(tmp_path: Path) -> None:
    fragment = make_fragment(tmp_path, phase="P3", family="C2", cell_ids=("C2.1",))
    fragment["_path"] = "evidence/p3-fragments/C2.json"
    fragment["authority_ceiling"]["cutover"] = True
    path = tmp_path / fragment["_path"]
    path.write_text(json.dumps(fragment, sort_keys=True), encoding="utf-8")
    report = validate_batch(
        make_batch(tmp_path, fragments=[fragment], aggregates=[]), tmp_path
    )
    assert any(issue.code == "AUTHORITY_CEILING_VIOLATION" for issue in report.issues)


def test_fragment_vs_aggregate_consistency(tmp_path: Path) -> None:
    fragment = make_fragment(tmp_path, phase="P3", family="C2", cell_ids=("C2.1",))
    fragment["_path"] = "evidence/p3-fragments/C2.json"
    aggregate = make_aggregate(
        tmp_path,
        phase="P3",
        families=["C3"],
        cell_ids=["C3.1"],
        status="PROMOTED",
    )
    aggregate["_path"] = "evidence/p3-aggregate.json"
    report = validate_batch(
        make_batch(tmp_path, fragments=[fragment], aggregates=[aggregate]), tmp_path
    )
    codes = [issue.code for issue in report.issues]
    assert "AGGREGATE_FAMILIES_MISMATCH" in codes
    assert "AGGREGATE_CELLS_MISMATCH" in codes
    assert "AGGREGATE_CLAIM_EXCEEDS_FRAGMENTS" in codes


def test_fragment_aggregate_ref_must_resolve(tmp_path: Path) -> None:
    fragment = make_fragment(tmp_path, phase="P3", family="C2", cell_ids=("C2.1",))
    fragment["_path"] = "evidence/p3-fragments/C2.json"
    fragment["aggregate_ref"] = "evidence/missing-aggregate.json"
    path = tmp_path / fragment["_path"]
    path.write_text(json.dumps(fragment, sort_keys=True), encoding="utf-8")
    batch = make_batch(tmp_path, fragments=[fragment], aggregates=[])
    report = validate_batch(batch, tmp_path)
    assert any(
        issue.code == "FRAGMENT_AGGREGATE_REF_MISSING" for issue in report.issues
    )


def test_line_semantics_raw_newline_and_splitlines(tmp_path: Path) -> None:
    source = tmp_path / "main/backend/src/example.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"line1\nline2")  # raw newline 1, splitlines 2
    data = source.read_bytes()
    binding = {
        "path": "main/backend/src/example.py",
        "sha256": _sha256(data),
        "bytes": len(data),
        "lines": 1,
        "line_semantics": "raw_newline",
    }

    def build_line_fragment(family: str, files: list[dict[str, Any]]) -> dict[str, Any]:
        fragment: dict[str, Any] = {
            "schema": f"mrw.functorial_successor.p3_{family.lower()}_evidence_fragment.v1",
            "family": family,
            "phase": "P3",
            "status": "FAMILY_LOCAL_NOT_PROMOTED",
            "cells": {f"{family}.1": {}},
            "files": files,
            "source_evidence": [],
            "authority_ceiling": _authority(),
        }
        fragment["content_digest"] = canonical_content_digest(fragment)
        path = tmp_path / f"evidence/p3-fragments/{family}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fragment, sort_keys=True), encoding="utf-8")
        fragment["_path"] = f"evidence/p3-fragments/{family}.json"
        return fragment

    def other_families() -> list[dict[str, Any]]:
        fragments = []
        for family in ("C3", "C4", "C5", "C6"):
            fragment = make_fragment(
                tmp_path,
                phase="P3",
                family=family,
                cell_ids=(f"{family}.1",),
                bindings=(
                    (f"main/backend/src/{family}.py", f"class {family}:\n    pass\n"),
                ),
            )
            fragment["_path"] = f"evidence/p3-fragments/{family}.json"
            fragments.append(fragment)
        return fragments

    raw_fragment = build_line_fragment("C2", [binding])
    batch = make_batch(
        tmp_path,
        fragments=[raw_fragment, *other_families()],
        aggregates=[],
    )
    report = validate_batch(batch, tmp_path)
    assert report.is_valid(), [issue.as_dict() for issue in report.issues]

    split_binding = dict(binding)
    split_binding["line_semantics"] = "splitlines"
    split_binding["lines"] = 2
    split_fragment = build_line_fragment("C2", [split_binding])
    split_batch = make_batch(
        tmp_path,
        fragments=[split_fragment, *other_families()],
        aggregates=[],
    )
    report = validate_batch(split_batch, tmp_path)
    assert report.is_valid(), [issue.as_dict() for issue in report.issues]

    bad_binding = dict(binding)
    bad_binding["lines"] = 2
    bad_fragment = build_line_fragment("C2", [bad_binding])
    bad_batch = make_batch(
        tmp_path,
        fragments=[bad_fragment, *other_families()],
        aggregates=[],
    )
    report = validate_batch(bad_batch, tmp_path)
    assert any(issue.code == "SOURCE_BINDING_LINES_MISMATCH" for issue in report.issues)


def test_issues_are_sorted_and_from_fixed_code_set(tmp_path: Path) -> None:
    first = make_fragment(tmp_path, phase="P3", family="C2", cell_ids=("C2.1",))
    first["_path"] = "evidence/p3-fragments/C2.json"
    second = make_fragment(tmp_path, phase="P3", family="C3", cell_ids=("C2.1",))
    second["_path"] = "evidence/p3-fragments/C3.json"
    batch = make_batch(tmp_path, fragments=[first, second], aggregates=[])
    batch["extra"] = True
    report = validate_batch(batch, tmp_path)
    assert report.issues
    assert all(issue.code in FIXED_ISSUE_CODES for issue in report.issues)
    keys = [(issue.code, issue.path, issue.message) for issue in report.issues]
    assert keys == sorted(keys)


def test_validate_batch_is_read_only(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    fragment = make_fragment(root, phase="P3", family="C2", cell_ids=("C2.1",))
    fragment["_path"] = "evidence/p3-fragments/C2.json"
    make_batch(root, fragments=[fragment], aggregates=[])
    before = {
        str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    validate_batch(make_batch(root, fragments=[fragment], aggregates=[]), root)
    after = {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert before == after


def test_cli_exit_codes_and_report_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fragment = make_fragment(tmp_path, phase="P3", family="C2", cell_ids=("C2.1",))
    fragment["_path"] = "evidence/p3-fragments/C2.json"
    batch = make_batch(tmp_path, fragments=[fragment], aggregates=[])
    batch_path = tmp_path / "batch.json"
    batch_path.write_text(json.dumps(batch, sort_keys=True), encoding="utf-8")
    report_path = tmp_path / "report.json"
    assert (
        run_cli(
            [
                "--batch",
                str(batch_path),
                "--root",
                str(tmp_path),
                "--report",
                str(report_path),
            ]
        )
        == 1
    )
    parsed = json.loads(report_path.read_text(encoding="utf-8"))
    assert parsed["status"] == "INVALID"

    valid_batch = make_batch(tmp_path, fragments=[], aggregates=[], phases=())
    valid_batch_path = tmp_path / "valid.json"
    valid_batch_path.write_text(
        json.dumps(valid_batch, sort_keys=True), encoding="utf-8"
    )
    assert (
        run_cli(["--batch", str(valid_batch_path), "--root", str(tmp_path), "--quiet"])
        == 0
    )

    broken = tmp_path / "broken.json"
    broken.write_text("{invalid", encoding="utf-8")
    assert run_cli(["--batch", str(broken), "--root", str(tmp_path), "--quiet"]) == 2
    capsys.readouterr()


def test_p3_aggregate_validator_preserves_order_and_no_candidate_claim() -> None:
    aggregate: dict[str, Any] = {
        "schema": P3_AGGREGATE_SCHEMA,
        "ordered_composition": {
            "family_order": list(P3_FAMILY_ORDER),
            "cell_order": list(P3_CELL_ORDER),
            "commutativity_claim": False,
        },
        "fragment_bindings": [{"family": family} for family in P3_FAMILY_ORDER],
        "cell_bindings": [
            {
                "cell_id": cell_id,
                "provider_calls": 0,
                "operation_bindings": [
                    {
                        "operation_kind": f"fixture.{cell_id}",
                        "contract_digest": "a" * 64,
                    }
                ],
            }
            for cell_id in P3_CELL_ORDER
        ],
        "external_family_reviews": [],
        "canonical_ownership": {
            "live_claim_owner": "legacy",
            "conflicting_contract_identities": [],
        },
        "authority_ceiling": {
            "provider_calls": 0,
            "network": False,
            "production_canonical_write": False,
            "live_provider": False,
            "external_delivery": False,
            "cutover": False,
            "authority_transfer": False,
            "legacy_retired": False,
            "candidate_created": False,
        },
        "worktree_identity": {"candidate_commit": None, "candidate_tree": None},
        "promotion_prerequisites": {"promotion_claim": False},
    }
    assert validate_p3_aggregate_document(aggregate) == ()


def test_p3_aggregate_validator_rejects_reordered_cells() -> None:
    aggregate = {
        "schema": P3_AGGREGATE_SCHEMA,
        "ordered_composition": {
            "family_order": list(P3_FAMILY_ORDER),
            "cell_order": list(reversed(P3_CELL_ORDER)),
            "commutativity_claim": False,
        },
        "fragment_bindings": [{"family": family} for family in P3_FAMILY_ORDER],
        "cell_bindings": [],
        "external_family_reviews": [],
        "canonical_ownership": {
            "live_claim_owner": "legacy",
            "conflicting_contract_identities": [],
        },
        "authority_ceiling": {
            "provider_calls": 0,
            "network": False,
            "production_canonical_write": False,
            "live_provider": False,
            "external_delivery": False,
            "cutover": False,
            "authority_transfer": False,
            "legacy_retired": False,
            "candidate_created": False,
        },
        "worktree_identity": {"candidate_commit": None, "candidate_tree": None},
        "promotion_prerequisites": {"promotion_claim": False},
    }
    codes = {issue.code for issue in validate_p3_aggregate_document(aggregate)}
    assert "P3_AGGREGATE_CELL_ORDER_MISMATCH" in codes
