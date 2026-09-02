#!/usr/bin/env python3
"""Read-only validator for the P1-P3 semantic movement backfill artifacts.

The validator recomputes every generated artifact from the mainline inputs,
compares persisted bytes, and runs the declared-scope and predecessor-to-
successor contract checks described by the mainline spec.  It never writes.

Run from ``main/backend``::

    python3.11 scripts/validate_successor_semantic_movement.py

``--repo-root`` names the canonical evidence root (default: the repository
root); ``--output-root`` names the checkout holding the generated artifacts
(default: ``--repo-root``).  Exit codes: 0 = PASS, 1 = FAIL, 2 = INVALID.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

_GENERATOR = Path(__file__).with_name("generate_successor_p1_p3_semantic_movement.py")


def _load_generator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p1_p3_semantic_movement", _GENERATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load generator module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_KNOWN_UNRESOLVED_REF_IDS = ()


def _check(
    checks: list[dict[str, Any]], check_id: str, ok: bool, detail: Any = None
) -> None:
    checks.append(
        {
            "id": check_id,
            "status": "PASS" if ok else "FAIL",
            "detail": detail,
        }
    )


def _validate(repo_root: Path, output_root: Path) -> tuple[bool, list[dict[str, Any]]]:
    generator = _load_generator()
    checks: list[dict[str, Any]] = []
    relative_paths = (
        *[
            generator.FRAGMENT_REL / f"{family}.v1.json"
            for family in generator.FAMILIES
        ],
        generator.INVENTORY_REL,
        generator.MATRIX_REL,
        generator.GATE_REL,
    )
    missing = [
        relative.as_posix()
        for relative in relative_paths
        if not (output_root / relative).is_file()
    ]
    _check(checks, "artifacts_exist", not missing, {"missing": missing})

    try:
        documents = generator.build_documents(repo_root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        checks.append(
            {"id": "canonical_rebuild", "status": "INVALID", "detail": str(exc)}
        )
        return False, checks

    drift = [
        relative.as_posix()
        for relative, expected in documents.items()
        if not (output_root / relative).is_file()
        or (output_root / relative).read_bytes() != expected
    ]
    _check(checks, "canonical_rebuild_matches", not drift, {"drift": drift})

    try:
        matrix = json.loads(
            (output_root / generator.MATRIX_REL).read_text(encoding="utf-8")
        )
        inventory = json.loads(
            (output_root / generator.INVENTORY_REL).read_text(encoding="utf-8")
        )
        gate = json.loads(
            (output_root / generator.GATE_REL).read_text(encoding="utf-8")
        )
        fragments = {
            family: json.loads(
                (output_root / generator.FRAGMENT_REL / f"{family}.v1.json").read_text(
                    encoding="utf-8"
                )
            )
            for family in generator.FAMILIES
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        checks.append(
            {"id": "artifacts_parse", "status": "INVALID", "detail": str(exc)}
        )
        return False, checks

    digest_mismatch = []
    for label, artifact in [
        ("inventory", inventory),
        ("matrix", matrix),
        ("gate", gate),
        *[(f"fragment_{family}", fragments[family]) for family in generator.FAMILIES],
    ]:
        if artifact.get("content_digest") != generator._content_digest(artifact):
            digest_mismatch.append(label)
    _check(checks, "content_digests_recompute", not digest_mismatch, digest_mismatch)

    rows = matrix["movements"]
    field_violations = []
    disposition_violations = []
    for row in rows:
        missing_fields = [
            field for field in generator.REQUIRED_FIELDS if field not in row
        ]
        if missing_fields:
            field_violations.append(
                {"movement_id": row["movement_id"], "missing": missing_fields}
            )
        if row.get("disposition") not in generator.ALLOWED_DISPOSITIONS:
            disposition_violations.append(
                {
                    "movement_id": row["movement_id"],
                    "disposition": row.get("disposition"),
                }
            )
    _check(
        checks,
        "movement_record_required_fields",
        not field_violations,
        {"violations": field_violations},
    )
    _check(
        checks,
        "allowed_dispositions",
        not disposition_violations,
        {"violations": disposition_violations},
    )

    ids = [row["movement_id"] for row in rows]
    blocker_ids = [
        row["movement_id"] for row in rows if row["disposition"] == "UNASSIGNED_BLOCKER"
    ]
    counts_ok = (
        len(ids) == 60
        and matrix["inline_movement_count"] == 40
        and matrix["external_c7_movement_count"] == 20
        and matrix["total_movement_count"] == 60
        and matrix["unique_movement_ids"] == 60
        and len(set(ids)) == 60
        and matrix["unassigned_blocker_count"] == len(blocker_ids)
        and matrix["unassigned_blocker_ids"] == blocker_ids
    )
    _check(
        checks,
        "movement_counts_and_unique_identity",
        counts_ok,
        {
            "inline": matrix["inline_movement_count"],
            "external_c7": matrix["external_c7_movement_count"],
            "total": matrix["total_movement_count"],
            "unique": matrix["unique_movement_ids"],
            "blockers": matrix["unassigned_blocker_count"],
        },
    )

    expected_partitions = {
        "C1": 4,
        "C2": 8,
        "C3": 3,
        "C4": 5,
        "C5": 6,
        "C6": 4,
        "C7": 20,
        "C8": 5,
        "C9": 5,
    }
    family_blocker_counts = {
        family: sum(
            row["family"] == family and row["disposition"] == "UNASSIGNED_BLOCKER"
            for row in rows
        )
        for family in generator.FAMILIES
    }
    partitions_ok = (
        all(
            matrix["family_partitions"][family]["movement_count"] == expected
            for family, expected in expected_partitions.items()
        )
        and sum(
            matrix["family_partitions"][family]["unassigned_blocker_count"]
            for family in generator.FAMILIES
        )
        == len(blocker_ids)
        and all(
            matrix["family_partitions"][family]["unassigned_blocker_count"] == expected
            for family, expected in family_blocker_counts.items()
        )
    )
    _check(checks, "family_partitions", partitions_ok, matrix["family_partitions"])

    c7_binding = matrix["c7_external_binding"]
    design_rows = generator.parse_c7_design(
        (repo_root / generator.C7_DESIGN_REL).read_text(encoding="utf-8")
    )
    c7_matrix = json.loads(
        (repo_root / generator.C7_MATRIX_REL).read_text(encoding="utf-8")
    )
    c7_inventory = json.loads(
        (repo_root / generator.C7_INVENTORY_REL).read_text(encoding="utf-8")
    )
    c7_trace = json.loads(
        (repo_root / generator.C7_TRACE_REL).read_text(encoding="utf-8")
    )
    fragment_c7_rows = [
        {
            key: value
            for key, value in row.items()
            if key
            not in {
                "family",
                "phase_partition",
                "p1_cell_scope",
                "locator_role",
                "evidence_bindings",
            }
        }
        for row in fragments["C7"]["movements"]
    ]
    design_sha256 = generator._sha256(
        (repo_root / generator.C7_DESIGN_REL).read_bytes()
    )
    design_source_binding = next(
        binding
        for binding in matrix["source_bindings"]
        if binding["role"] == "c7_external_semantic_design"
    )
    c7_inventory_digest = generator._content_digest(c7_inventory)
    c7_matrix_digest = generator._content_digest(c7_matrix)
    c7_trace_digest = generator._content_digest(c7_trace)
    c7_ok = (
        len(design_rows) == 20
        and len(
            [row for row in design_rows if row["disposition"] == "UNASSIGNED_BLOCKER"]
        )
        == 0
        and c7_binding["status"] == "EXACT_BOUND"
        and c7_binding["row_count"] == 20
        and c7_binding["unassigned_blocker_count"] == 0
        and c7_binding["design_unassigned_blocker_count"] == 0
        and design_sha256 == generator.C7_DESIGN_SHA256
        and c7_binding["design_sha256"] == design_sha256
        and design_source_binding["sha256"] == design_sha256
        and c7_binding["matrix_content_digest"] == c7_matrix_digest
        and c7_binding["inventory_content_digest"] == c7_inventory_digest
        and c7_binding["trace_content_digest"] == c7_trace_digest
        and c7_matrix["content_digest"] == c7_matrix_digest
        and c7_inventory["content_digest"] == c7_inventory_digest
        and c7_trace["content_digest"] == c7_trace_digest
        and c7_matrix_digest == generator.C7_MATRIX_DIGEST
        and c7_inventory_digest == generator.C7_INVENTORY_DIGEST
        and c7_trace_digest == generator.C7_TRACE_DIGEST
        and fragment_c7_rows == c7_matrix["movements"]
    )
    _check(checks, "c7_external_exact_binding", c7_ok, c7_binding)

    spec_bytes = (repo_root / generator.SPEC_REL).read_bytes()
    spec_binding = matrix["spec_binding"]
    spec_ok = (
        spec_binding["bytes_sha256"] == generator.SPEC_BYTES_SHA256
        and generator._sha256(spec_bytes) == generator.SPEC_BYTES_SHA256
        and spec_binding["canonical_content_digest"]
        == generator._sha256(generator._canonical(json.loads(spec_bytes)))
    )
    _check(checks, "spec_exact_binding", spec_ok, spec_binding)

    unresolved = [
        (row["movement_id"], field, binding)
        for row in rows
        for field in ("source_evidence", "target_realization", "acceptance_trace")
        for binding in row["evidence_bindings"].get(field, [])
        if binding.get("kind") == "unresolved"
    ]
    descriptive_absence = [
        (row["movement_id"], field, binding)
        for row in rows
        for field in ("source_evidence", "target_realization", "acceptance_trace")
        for binding in row["evidence_bindings"].get(field, [])
        if binding.get("kind") == "absence_evidence"
    ]
    known = [
        (movement_id, field)
        for movement_id, field, _binding in unresolved
        if (movement_id, field) in _KNOWN_UNRESOLVED_REF_IDS
    ]
    unexpected = [
        (movement_id, field, binding["ref"])
        for movement_id, field, binding in unresolved
        if (movement_id, field) not in _KNOWN_UNRESOLVED_REF_IDS
    ]
    refs_ok = (
        len(unresolved) == len(_KNOWN_UNRESOLVED_REF_IDS) == len(known)
        and not unexpected
        and not descriptive_absence
        and gate["evidence_refs"]["absence_evidence"] == 0
    )
    _check(
        checks,
        "evidence_refs_resolve",
        refs_ok,
        {
            "unresolved": [
                {"movement_id": mid, "field": field, "ref": binding["ref"]}
                for mid, field, binding in unresolved
            ],
            "unexpected_unresolved": unexpected,
            "descriptive_absence": [
                {
                    "movement_id": mid,
                    "field": field,
                    "ref": binding["ref"],
                }
                for mid, field, binding in descriptive_absence
            ],
            "summary": gate["evidence_refs"],
        },
    )

    promotion_ok = (
        matrix["promotion_decision"] is None
        and matrix["promotion_allowed"] is False
        and gate["promotion_decision"] is None
        and gate["promotion_allowed"] is False
        and not any(matrix["authority_ceiling"].values())
        and matrix["scope"]["does_not_revoke_or_reprove_p0_p3_local_only_state"] is True
        and gate["scoped_blocker_gate"][
            "does_not_revoke_or_reprove_p0_p3_local_only_state"
        ]
        is True
    )
    _check(checks, "promotion_and_scoped_blocker_gate", promotion_ok)

    matrix_ids = [row["movement_id"] for row in matrix["movements"]]
    matrix_by_family = {
        family: [row["movement_id"] for row in rows if row["family"] == family]
        for family in generator.FAMILIES
    }
    fragment_partition_matches = all(
        fragments[family]["movement_ids"] == matrix_by_family[family]
        for family in generator.FAMILIES
    )
    fragment_ids = [
        movement_id
        for family in generator.FAMILIES
        for movement_id in fragments[family]["movement_ids"]
    ]
    projection_ok = (
        fragment_partition_matches
        and sorted(fragment_ids) == sorted(matrix_ids)
        and len(set(fragment_ids)) == 60
        and inventory["movement_ids"] == matrix_ids
        and all(
            fragments[family]["matrix_content_digest"] == matrix["content_digest"]
            for family in generator.FAMILIES
        )
        and inventory["matrix_content_digest"] == matrix["content_digest"]
    )
    _check(checks, "projections_bijective", projection_ok)

    c2_m008 = next(row for row in rows if row["movement_id"] == "C2-M008")
    loss_ok = (
        c2_m008["disposition"] == "DECLARED_LOSS"
        and "source_library.c2_4.compat.loss.v1" in str(c2_m008["projection_loss"])
        and gate["trace_and_loss_account"]["zero_loss_declared"] is False
        and gate["trace_and_loss_account"]["declared_loss_movements"]
        == [
            "C2-M008",
            "C7-MOV-002",
            "C7-MOV-011",
            "C7-MOV-021",
            "C7-MOV-031",
            "C7-MOV-041",
            "C7-MOV-070",
            "C7-MOV-060",
            "C7-MOV-061",
        ]
        and sum(
            movement.startswith("C7-MOV-")
            for movement in gate["trace_and_loss_account"]["declared_loss_movements"]
        )
        == 8
        and len(c7_trace["declared_losses"]) == 8
    )
    _check(checks, "trace_and_loss_account", loss_ok, gate["trace_and_loss_account"])

    gate_ok = (
        gate["status"] == "BLOCK_DEPENDENT_SCOPE"
        and gate["verdict"] == "BLOCK"
        and gate["counts"]["inline_unassigned_blockers"]
        == matrix["unassigned_blocker_account"]["inline_count"]
        and gate["counts"]["external_c7_unassigned_blockers"]
        == matrix["unassigned_blocker_account"]["external_C7_count"]
        and gate["counts"]["exact_blockers_for_this_spec"]
        == matrix["unassigned_blocker_count"]
        and gate["counts"]["total_movements"] == 60
        and gate["aggregate"]["status"] == "BLOCK_DEPENDENT_SCOPE"
        and gate["aggregate"]["promotion_allowed"] is False
        and f"UNASSIGNED_BLOCKER = {matrix['unassigned_blocker_count']}"
        in gate["aggregate"]["reason"]
        and gate["declared_scope_correctness_gate"]["status"] == "PASS"
        and gate["predecessor_to_successor_completeness_gate"]["status"] == "PASS"
        and gate["content_digests"]["matrix"] == matrix["content_digest"]
        and gate["content_digests"]["inventory"] == inventory["content_digest"]
    )
    _check(checks, "gate_consistency", gate_ok, gate["counts"])

    return all(check["status"] == "PASS" for check in checks), checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[3]
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="checkout holding generated artifacts (default: --repo-root)",
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    output_root = (args.output_root or args.repo_root).resolve()
    try:
        ok, checks = _validate(repo_root, output_root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "INVALID", "error": str(exc)}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "status": "PASS" if ok else "FAIL",
                "checks": checks,
            },
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
