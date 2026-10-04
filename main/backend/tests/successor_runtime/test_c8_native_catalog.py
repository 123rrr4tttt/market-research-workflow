"""C8 native catalog integration tests."""

from __future__ import annotations

from pathlib import Path

from app.successor_runtime.assembly.knowledge_assembly import ASSEMBLY_CELL_IDS

from mrw_functorial_kit.contributions.knowledge_graph_projection import (
    knowledge_graph_projection_native_contributions,
)
from app.successor_runtime.capabilities.knowledge_program import (
    knowledge_native_contributions,
    build_knowledge_bundle,
)
from functorial_kit.contribution_verification import VerificationChanges

from mrw_functorial_kit.contributions.knowledge import (
    knowledge_law_witnesses,
    knowledge_native_catalog,
    knowledge_verification_law_witnesses,
    knowledge_verification_plan,
    knowledge_verification_plan_for,
    knowledge_verification_registration,
    contribution_catalog,
)


def test_catalog_contains_all_native_c8_cells_in_stable_order() -> None:
    assert tuple(native.projection.id for native in knowledge_native_catalog) == (
        "mrw.knowledge.read.native.v2",
        "mrw.knowledge.writing.native.v2",
        "mrw.knowledge.report.native.v2",
        "mrw.knowledge.graph-projection.native.v2",
    )
    assert knowledge_native_catalog == (
        *knowledge_native_contributions,
        *knowledge_graph_projection_native_contributions,
    )
    assert tuple(contribution.id for contribution in contribution_catalog.contributions) == tuple(
        native.projection.id for native in knowledge_native_catalog
    )


def test_c8_native_catalog_law_witness_is_callable() -> None:
    (witness,) = (
        candidate
        for candidate in knowledge_law_witnesses
        if candidate.id == "test_knowledge_native_catalog_law"
    )
    witness.run()


def test_verification_plan_is_derived_from_the_same_native_catalog() -> None:
    expected_ids = tuple(native.projection.id for native in knowledge_native_catalog)
    selection = knowledge_verification_plan.selection
    assert selection.mode == "full"
    assert selection.reasons == ("changes_not_provided",)
    assert selection.contribution_ids == expected_ids
    check_ids = tuple(check.witness.id for check in knowledge_verification_plan.checks if check.contribution_id in expected_ids)
    assert check_ids == tuple(
        f"test_knowledge_native_definition_law:{contribution_id}"
        for contribution_id in expected_ids
        if contribution_id != "mrw.knowledge.graph-projection.native.v2"
    ) + (
        "test_knowledge_graph_projection_definition_law:"
        "mrw.knowledge.graph-projection.native.v2",
    )


def test_unknown_changes_expand_verification_selection_to_full() -> None:
    plan = knowledge_verification_plan_for(VerificationChanges(unknown=True))
    assert plan.selection.mode == "full"
    assert "unknown_changes" in plan.selection.reasons
    assert plan.selection.contribution_ids == tuple(
        native.projection.id for native in knowledge_native_catalog
    )


def test_derived_verification_witnesses_run_inert_definition_laws() -> None:
    assert knowledge_verification_registration is not None
    for witness in knowledge_verification_law_witnesses:
        witness.run()
    report = knowledge_verification_registration.report()
    assert report.complete is True
    assert report.passed is True


def test_project_catalog_contains_the_knowledge_business_catalog() -> None:
    from contributions.project_catalog import project_contribution_catalog

    assert tuple(contribution_catalog.contributions) == tuple(
        item
        for item in project_contribution_catalog
        if item.id.startswith("mrw.knowledge.")
    )


def test_default_bundle_uses_combined_native_catalog_without_duplicates() -> None:
    bundle = build_knowledge_bundle()
    kinds = [operation.ref.kind for operation in bundle.operations]
    assert len(kinds) == len(set(kinds))
    assert tuple(bundle.profiles) == ASSEMBLY_CELL_IDS
