"""I1 rollback rehearsal evidence: per-cell bindings and C7 pure routes.

This non-PostgreSQL harness records each cell's rollback binding status from
the frozen capability specs plus the closed local-only serial assembly.
C7.1-C7.4 are installed as pure rollback-route handlers when their route
closures are supplied; the same cells stay ``DECLARED_GAP`` in the default
fail-closed assembly.  Durable journal/authority epoch rehearsal remains a
PostgreSQL opt-in surface.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine

from app.successor_runtime.assembly.successor_assembly import (
    assemble_successor_runtime,
    build_local_offline_fixture_options,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]
TOPIC = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration"
)
SPECS_DIR = REPOSITORY_ROOT / TOPIC / "evidence/capability-specs"

pytestmark = pytest.mark.unit


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _rollback_rows() -> list[dict[str, Any]]:
    assembly = assemble_successor_runtime(
        engine=create_engine("sqlite+pysqlite:///:memory:"),
        options=build_local_offline_fixture_options(),
    )
    declarations = {item.cell_id: item for item in assembly.rollback_bindings}
    rows: list[dict[str, Any]] = []
    for cell in assembly.cells:
        spec = _load(SPECS_DIR / f"{cell.cell_id}.v1.json")
        spec_bindings = tuple(
            str(item["path"]) for item in spec.get("rollback_bindings", [])
        )
        declaration = declarations.get(cell.cell_id)
        if cell.cell_id.startswith("C7.") and declaration.status == "PRESENT":
            assert declaration is not None
            for binding_path in declaration.binding_refs:
                path = Path(binding_path)
                if not path.is_absolute():
                    path = REPOSITORY_ROOT / path
                assert path.is_file(), f"rollback route missing: {binding_path}"
            rows.append(
                {
                    "cell_id": cell.cell_id,
                    "rehearsal_status": "ROUTE_ASSEMBLED",
                    "declaration_status": "PRESENT",
                    "binding_refs": list(declaration.binding_refs),
                    "note": declaration.note,
                }
            )
            continue
        if cell.cell_id.startswith("C7."):
            assert declaration is not None
            assert declaration.status == "DECLARED_GAP"
            rows.append(
                {
                    "cell_id": cell.cell_id,
                    "rehearsal_status": "BLOCKED",
                    "declaration_status": "DECLARED_GAP",
                    "binding_refs": list(declaration.binding_refs),
                    "note": declaration.note,
                }
            )
            continue
        if declaration is not None and declaration.status == "PRESENT":
            assert declaration is not None
            for binding_path in spec_bindings:
                path = Path(binding_path)
                if not path.is_absolute():
                    path = REPOSITORY_ROOT / path
                assert path.is_file(), f"rollback binding missing: {binding_path}"
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                expected = next(
                    item["file_sha256"]
                    for item in spec["rollback_bindings"]
                    if item["path"] == binding_path
                )
                assert actual == expected, (
                    f"rollback binding drift: {binding_path}: {actual} != {expected}"
                )
            rows.append(
                {
                    "cell_id": cell.cell_id,
                    "rehearsal_status": "STRUCTURAL_PASS",
                    "declaration_status": "PRESENT",
                    "binding_refs": list(spec_bindings),
                    "note": "path + sha256 verified; durable epoch rehearsal is PG opt-in",
                }
            )
        elif declaration is not None and declaration.status == "DECLARED_OPEN":
            rows.append(
                {
                    "cell_id": cell.cell_id,
                    "rehearsal_status": "DECLARED_OPEN",
                    "declaration_status": "DECLARED_OPEN",
                    "binding_refs": list(declaration.binding_refs),
                    "note": declaration.note
                    or "no rollback implementation binding is installed",
                }
            )
        else:
            rows.append(
                {
                    "cell_id": cell.cell_id,
                    "rehearsal_status": "DECLARED_OPEN",
                    "declaration_status": "DECLARED_OPEN",
                    "binding_refs": [],
                    "note": (
                        "spec has no rollback_bindings; no rollback route was invented"
                    ),
                }
            )
    assert len(rows) == 30
    return rows


def test_i1_rollback_rehearsal_matrix_covers_thirty_cells() -> None:
    rows = _rollback_rows()
    assert len(rows) == 30
    by_id = {row["cell_id"]: row for row in rows}
    for cell_id in ("C7.1", "C7.2", "C7.3", "C7.4"):
        assert by_id[cell_id]["rehearsal_status"] == "ROUTE_ASSEMBLED"
        assert by_id[cell_id]["declaration_status"] == "PRESENT"
        assert by_id[cell_id]["binding_refs"]


def test_i1_default_c7_rollback_gap_blocks_without_inventing_bindings() -> None:
    assembly = assemble_successor_runtime(
        engine=create_engine("sqlite+pysqlite:///:memory:")
    )
    declarations = {
        item.cell_id: item
        for item in assembly.rollback_bindings
        if item.cell_id.startswith("C7.")
    }
    for cell_id in ("C7.1", "C7.2", "C7.3", "C7.4"):
        declaration = declarations[cell_id]
        assert declaration.status == "DECLARED_GAP"
        assert declaration.binding_refs == ()
        assert "rollback" in declaration.note.lower()


def test_i1_present_rollback_bindings_are_exact_on_disk() -> None:
    rows = _rollback_rows()
    present = [row for row in rows if row["declaration_status"] == "PRESENT"]
    assert present
    for row in present:
        assert row["binding_refs"]


def test_i1_assembly_recovery_and_effect_digests_never_duplicate() -> None:
    assembly = assemble_successor_runtime(
        engine=create_engine("sqlite+pysqlite:///:memory:")
    )
    effect_digests = {handler.handler_binding_digest for handler in assembly.handlers}
    recovery_digests = {
        handler.handler_binding_digest for handler in assembly.recovery_handlers
    }
    assert effect_digests.isdisjoint(recovery_digests)
