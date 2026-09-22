"""C8 native catalog integration tests."""

from __future__ import annotations

from pathlib import Path

from mrw_functorial_kit.contributions.c8_graph_projection import (
    c8_graph_projection_native_contributions,
)
from app.successor_runtime.capabilities.c8_program import (
    c8_native_contributions,
    build_c8_bundle,
)
from mrw_functorial_kit.contributions.c8 import (
    c8_law_witnesses,
    c8_native_catalog,
    contribution_catalog,
)


def test_catalog_contains_all_native_c8_cells_in_stable_order() -> None:
    assert tuple(native.projection.id for native in c8_native_catalog) == (
        "mrw.successor.c8.typed-knowledge.v1",
        "mrw.successor.c8.c8-2.writing.v1",
        "mrw.successor.c8.report.v1",
        "mrw.successor.c8.graph-projection.v1",
    )
    assert c8_native_catalog == (
        *c8_native_contributions,
        *c8_graph_projection_native_contributions,
    )
    assert tuple(contribution.id for contribution in contribution_catalog.contributions) == tuple(
        native.projection.id for native in c8_native_catalog
    )


def test_c8_native_catalog_law_witness_is_callable() -> None:
    (witness,) = c8_law_witnesses
    assert witness.id == "test_c8_native_catalog_law"
    witness.run()


def test_generated_catalog_module_points_to_combined_c8_catalog() -> None:
    root = Path(__file__).resolve().parents[4]
    text = (root / "contributions" / "c8_catalog.py").read_text(encoding="utf-8")
    assert "mrw_functorial_kit.contributions.c8" in text
    assert "c8_graph_projection_catalog" not in text


def test_default_bundle_uses_combined_native_catalog_without_duplicates() -> None:
    bundle = build_c8_bundle()
    kinds = [operation.ref.kind for operation in bundle.operations]
    assert len(kinds) == len(set(kinds))
    assert set(bundle.profiles) == {"C8.1", "C8.2", "C8.3", "C8.4"}
