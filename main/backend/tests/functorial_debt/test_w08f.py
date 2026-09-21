from __future__ import annotations

from pathlib import Path
import re
from typing import Annotated, get_args, get_origin, get_type_hints

from app.successor_migration.graph_projector_c7 import build_graph_projection
from app.successor_migration.legacy_agent_batch import (
    build_legacy_agent_batch_c4_plan_binding,
    build_legacy_agent_batch_c4_retry_binding,
    build_successor_agent_batch_c4_plan_binding,
    build_successor_agent_batch_c4_retry_binding,
    build_successor_agent_batch_c4_submission_binding,
)
from app.successor_migration.legacy_agent_core import (
    build_legacy_agent_core_c6_1_binding,
    build_legacy_agent_core_c6_2_binding,
    build_legacy_agent_core_c6_3_binding,
    build_successor_agent_core_c6_1_binding,
    build_successor_agent_core_c6_2_binding,
    build_successor_agent_core_c6_3_binding,
)
from app.successor_migration.legacy_collect_runtime import (
    build_legacy_collect_c3_1_binding,
    build_legacy_collect_c3_2_binding,
    build_successor_collect_c3_1_binding,
    build_successor_collect_c3_2_binding,
)
from app.successor_migration.legacy_source_library import (
    build_legacy_source_library_c2_1_binding,
    build_successor_source_library_c2_1_binding,
)
from app.successor_migration.search_projector_c7 import build_search_projection


W08F_EXACT_KEYS = (
    "derived-marked|main/backend/app/successor_migration/graph_projector_c7.py|"
    "build_graph_projection returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_agent_batch.py|"
    "build_legacy_agent_batch_c4_plan_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_agent_batch.py|"
    "build_legacy_agent_batch_c4_retry_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_agent_batch.py|"
    "build_successor_agent_batch_c4_plan_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_agent_batch.py|"
    "build_successor_agent_batch_c4_retry_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_agent_batch.py|"
    "build_successor_agent_batch_c4_submission_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_agent_core.py|"
    "build_legacy_agent_core_c6_1_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_agent_core.py|"
    "build_legacy_agent_core_c6_2_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_agent_core.py|"
    "build_legacy_agent_core_c6_3_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_agent_core.py|"
    "build_successor_agent_core_c6_1_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_agent_core.py|"
    "build_successor_agent_core_c6_2_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_agent_core.py|"
    "build_successor_agent_core_c6_3_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_collect_runtime.py|"
    "build_legacy_collect_c3_1_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_collect_runtime.py|"
    "build_legacy_collect_c3_2_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_collect_runtime.py|"
    "build_successor_collect_c3_1_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_collect_runtime.py|"
    "build_successor_collect_c3_2_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_source_library.py|"
    "build_legacy_source_library_c2_1_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/legacy_source_library.py|"
    "build_successor_source_library_c2_1_binding returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_migration/search_projector_c7.py|"
    "build_search_projection returns an unmarked derived value",
)


_AUTHORITY = {
    build_graph_projection: (
        "kit:non-authoritative derived_as=view",
        "test:test_graph_projection_binds_document_ref_and_declares_loss",
    ),
    build_search_projection: (
        "kit:non-authoritative derived_as=view",
        "test:test_search_projection_binds_document_ref_and_declares_loss",
    ),
    build_legacy_agent_batch_c4_plan_binding: (
        "kit:prepared-command",
        "test:test_binding_swap_and_mutation_reject_c4_1",
    ),
    build_successor_agent_batch_c4_plan_binding: (
        "kit:prepared-command",
        "test:test_binding_swap_and_mutation_reject_c4_1",
    ),
    build_legacy_agent_batch_c4_retry_binding: (
        "kit:prepared-command",
        "test:test_binding_swap_and_mutation_reject_c4_2",
    ),
    build_successor_agent_batch_c4_retry_binding: (
        "kit:prepared-command",
        "test:test_binding_swap_and_mutation_reject_c4_2",
    ),
    build_successor_agent_batch_c4_submission_binding: (
        "kit:prepared-command",
        "test:test_rollback_rehearsal_legacy_claim_no_dual_and_receipt_retained",
    ),
    build_legacy_agent_core_c6_1_binding: (
        "kit:prepared-command",
        "test:test_c6_1_same_program_legacy_and_successor_shadow_parity",
    ),
    build_successor_agent_core_c6_1_binding: (
        "kit:prepared-command",
        "test:test_c6_1_same_program_legacy_and_successor_shadow_parity",
    ),
    build_legacy_agent_core_c6_2_binding: (
        "kit:prepared-command",
        "test:test_c6_2_same_program_legacy_and_successor_provider_parity",
    ),
    build_successor_agent_core_c6_2_binding: (
        "kit:prepared-command",
        "test:test_c6_2_same_program_legacy_and_successor_provider_parity",
    ),
    build_legacy_agent_core_c6_3_binding: (
        "kit:prepared-command",
        "test:test_c6_3_swapped_bindings_and_mutation_reject",
    ),
    build_successor_agent_core_c6_3_binding: (
        "kit:prepared-command",
        "test:test_c6_3_swapped_bindings_and_mutation_reject",
    ),
    build_legacy_collect_c3_1_binding: (
        "kit:prepared-command",
        "test:test_legacy_and_successor_bindings_are_distinct_and_exact",
    ),
    build_successor_collect_c3_1_binding: (
        "kit:prepared-command",
        "test:test_legacy_and_successor_bindings_are_distinct_and_exact",
    ),
    build_legacy_collect_c3_2_binding: (
        "kit:prepared-command",
        "test:test_legacy_and_successor_bindings_are_distinct_and_exact",
    ),
    build_successor_collect_c3_2_binding: (
        "kit:prepared-command",
        "test:test_legacy_and_successor_bindings_are_distinct_and_exact",
    ),
    build_legacy_source_library_c2_1_binding: (
        "kit:prepared-command",
        "test:test_exact_bindings_are_distinct_and_cross_rejected",
    ),
    build_successor_source_library_c2_1_binding: (
        "kit:prepared-command",
        "test:test_exact_bindings_are_distinct_and_cross_rejected",
    ),
}


def test_w08f_authority_metadata_is_exact_and_evidence_bound() -> None:
    assert len(W08F_EXACT_KEYS) == len(set(W08F_EXACT_KEYS)) == 19
    assert set(_AUTHORITY) == {
        build_graph_projection,
        build_search_projection,
        build_legacy_agent_batch_c4_plan_binding,
        build_legacy_agent_batch_c4_retry_binding,
        build_successor_agent_batch_c4_plan_binding,
        build_successor_agent_batch_c4_retry_binding,
        build_successor_agent_batch_c4_submission_binding,
        build_legacy_agent_core_c6_1_binding,
        build_legacy_agent_core_c6_2_binding,
        build_legacy_agent_core_c6_3_binding,
        build_successor_agent_core_c6_1_binding,
        build_successor_agent_core_c6_2_binding,
        build_successor_agent_core_c6_3_binding,
        build_legacy_collect_c3_1_binding,
        build_legacy_collect_c3_2_binding,
        build_successor_collect_c3_1_binding,
        build_successor_collect_c3_2_binding,
        build_legacy_source_library_c2_1_binding,
        build_successor_source_library_c2_1_binding,
    }

    witnesses: set[str] = set()
    for function, (expected_prefix, witness) in _AUTHORITY.items():
        return_type = get_type_hints(function, include_extras=True)["return"]
        assert get_origin(return_type) is Annotated
        annotation = get_args(return_type)[1]
        assert isinstance(annotation, str)
        assert annotation.startswith(expected_prefix)
        assert f"witness={witness}" in annotation
        if expected_prefix == "kit:non-authoritative derived_as=view":
            assert "fact_source=successor.ingest_index." in annotation
        else:
            assert "kit:prepared-command effect_boundary=app.successor_migration." in annotation
            assert "derived_as=" not in annotation
        witnesses.add(witness)

    test_root = Path(__file__).resolve().parents[1] / "successor_runtime"
    test_names = {
        match.group(1)
        for path in test_root.glob("test_*.py")
        for match in re.finditer(r"^def (test_\w+)\(", path.read_text(encoding="utf-8"), re.M)
    }
    assert {witness.removeprefix("test:") for witness in witnesses} <= test_names
