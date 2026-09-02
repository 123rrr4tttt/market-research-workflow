"""P4 C9 projector registry, exact offset CAS/ABA/stale and rebuild."""

from __future__ import annotations

import dataclasses
from dataclasses import replace

from app.successor_runtime.runtime.ports import ProjectScopeRef
from app.successor_runtime.substrate.postgres.projection_offsets import (
    ProjectionOffsetKey,
)
from app.successor_runtime.substrate.projections.registry import (
    REBUILD_MODES,
    OffsetExpectation,
    ProjectionOffset,
    ProjectionRebuild,
    ProjectionRebuildReceipt,
    ProjectorContract,
    ProjectorKey,
    ProjectorRegistry,
    rebuild_plan_digest,
    validate_offset_advance,
    validate_offset_snapshot,
    validate_projection_offset,
    validate_rebuild,
    validate_rebuild_receipt,
    validate_registry,
    validate_registry_revision_advance,
)

_SOURCE_DIGEST = "a" * 64
_SCOPE = ProjectScopeRef(
    project_key="p4-c9-demo",
    resolved_schema="mrw_p4_c9_demo",
    project_registry_revision=1,
    incarnation="scope-inc-c9",
    scope_digest="a" * 64,
)


def _key(**overrides: str) -> ProjectorKey:
    values = {
        "projector_id": "projector.run-summary",
        "projector_version": "1.1.0",
        "source_kind": "runtime_journal",
        "source_ref": "runtime-run:run-1",
        "source_incarnation": "run-inc-1",
    }
    values.update(overrides)
    return ProjectorKey(**values)


def _contract(**overrides: object) -> ProjectorContract:
    values: dict[str, object] = {
        "key": _key(),
        "projection_id": "projection.run-summary.v1",
        "projection_schema_ref": "mrw.successor.projector.run-summary.v1",
        "declared_loss": ("dropped_diagnostic_turns",),
    }
    values.update(overrides)
    return ProjectorContract(**values)


def _registry() -> ProjectorRegistry:
    return ProjectorRegistry(
        revision=1,
        incarnation="registry-inc-c9-scaffold",
        projectors=(_contract(),),
    )


def _offset(**overrides: object) -> ProjectionOffset:
    values: dict[str, object] = {
        "projection_offset_id": "offset-1",
        "key": _key(),
        "projection_generation": 1,
        "source_revision": 8,
        "source_digest": _SOURCE_DIGEST,
        "offset_ref": "offset-ref-8",
        "revision": 0,
    }
    values.update(overrides)
    return ProjectionOffset(**values)


def _expectation(**overrides: object) -> OffsetExpectation:
    values: dict[str, object] = {
        "expected_revision": 0,
        "expected_generation": 1,
        "expected_source_revision": 8,
        "expected_source_digest": _SOURCE_DIGEST,
    }
    values.update(overrides)
    return OffsetExpectation(**values)


def _next_offset() -> ProjectionOffset:
    return _offset(source_revision=9, offset_ref="offset-ref-9", revision=1)


def _rebuild(**overrides: object) -> ProjectionRebuild:
    values: dict[str, object] = {
        "rebuild_id": "rebuild-1",
        "key": _key(),
        "mode": "INCREMENTAL",
        "expected": _expectation(),
        "from_offset": 5,
        "declared_loss": ("dropped_diagnostic_turns",),
    }
    values.update(overrides)
    return ProjectionRebuild(**values)


def _receipt(**overrides: object) -> ProjectionRebuildReceipt:
    values: dict[str, object] = {
        "receipt_id": "receipt-1",
        "rebuild_id": "rebuild-1",
        "project_scope_ref": _SCOPE,
        "projection_id": "projection.run-summary.v1",
        "projection_digest": "b" * 64,
        "source_revision": 9,
        "source_digest": _SOURCE_DIGEST,
        "projection_generation": 2,
        "observed_at": "2026-09-01T00:00:00Z",
    }
    values.update(overrides)
    return ProjectionRebuildReceipt(**values)


def test_projector_key_aligns_with_projection_offset_key() -> None:
    assert tuple(field.name for field in dataclasses.fields(ProjectorKey)) == (
        "projector_id",
        "projector_version",
        "source_kind",
        "source_ref",
        "source_incarnation",
    )
    assert tuple(field.name for field in dataclasses.fields(ProjectorKey)) == tuple(
        field.name for field in dataclasses.fields(ProjectionOffsetKey)
    )


def test_registry_registration_is_pure_and_keys_are_exact() -> None:
    original = _registry()
    second_key = _key(
        projector_id="projector.market-index",
        source_ref="runtime-run:run-2",
    )
    second_contract = _contract(
        key=second_key,
        projection_id="projection.market-index.v1",
        projection_schema_ref="mrw.successor.projector.market-index.v1",
    )
    extended = original.register(second_contract)

    assert original.projectors == (_contract(),)
    assert extended.lookup(second_key) == second_contract
    assert len(extended.by_projection("projection.run-summary.v1")) == 1
    assert len(extended.by_projection("projection.market-index.v1")) == 1
    assert extended.digest() != original.digest()

    duplicate = _registry().register(_contract())
    assert any(
        v.code == "DUPLICATE_PROJECTOR_KEY"
        for v in validate_registry(duplicate).violations
    )


def test_offset_requires_exact_generation_revision_and_digest() -> None:
    assert validate_projection_offset(_offset()).valid
    negative = _offset(projection_generation=-1)
    assert any(
        v.code == "OFFSET_POSITION_NEGATIVE"
        for v in validate_projection_offset(negative).violations
    )
    bad_digest = _offset(source_digest="not-hex")
    assert any(
        v.code == "SOURCE_DIGEST_INVALID"
        for v in validate_projection_offset(bad_digest).violations
    )


def test_cas_advance_rejects_aba_generation_stale_and_regression() -> None:
    current = _offset()
    expectation = _expectation()
    assert validate_offset_advance(current, expectation, _next_offset()).valid

    aba = replace(current, revision=2)
    assert any(
        v.code == "OFFSET_ABA_DETECTED"
        for v in validate_offset_advance(aba, expectation, _next_offset()).violations
    )

    generation_mismatch = replace(current, projection_generation=3)
    assert any(
        v.code == "OFFSET_GENERATION_MISMATCH"
        for v in validate_offset_advance(
            generation_mismatch, expectation, _next_offset()
        ).violations
    )

    stale = replace(current, source_revision=9)
    assert any(
        v.code == "SOURCE_STALE"
        for v in validate_offset_advance(stale, expectation, _next_offset()).violations
    )

    regression = _offset(source_revision=7, offset_ref="offset-ref-7", revision=1)
    assert any(
        v.code == "SOURCE_REVISION_REGRESSION"
        for v in validate_offset_advance(current, expectation, regression).violations
    )

    wrong_advance = _offset(source_revision=9, offset_ref="offset-ref-9", revision=2)
    assert any(
        v.code == "OFFSET_REVISION_ADVANCE_MISMATCH"
        for v in validate_offset_advance(current, expectation, wrong_advance).violations
    )


def test_cas_advance_preserves_offset_id_and_rejects_digest_conflict() -> None:
    current = _offset()
    expectation = _expectation()
    wrong_id = _offset(projection_offset_id="offset-other", source_revision=9)
    assert any(
        v.code == "OFFSET_ID_MISMATCH"
        for v in validate_offset_advance(current, expectation, wrong_id).violations
    )

    digest_conflict = _offset(
        source_revision=8,
        source_digest="b" * 64,
        offset_ref="offset-ref-8b",
        revision=1,
    )
    assert any(
        v.code == "SOURCE_REVISION_DIGEST_CONFLICT"
        for v in validate_offset_advance(
            current, expectation, digest_conflict
        ).violations
    )


def test_rebuild_is_a_pure_plan_with_exact_cas() -> None:
    incremental = _rebuild()
    assert incremental.execute is False
    assert validate_rebuild(incremental, _registry()).valid

    missing_expectation = replace(incremental, expected=None)
    assert any(
        v.code == "REBUILD_EXPECTATION_REQUIRED"
        for v in validate_rebuild(missing_expectation, _registry()).violations
    )

    executed = replace(incremental, execute=True)
    assert any(
        v.code == "REBUILD_EXECUTION_FORBIDDEN"
        for v in validate_rebuild(executed, _registry()).violations
    )

    unregistered = replace(incremental, key=_key(projector_id="projector.missing"))
    assert any(
        v.code == "PROJECTOR_NOT_REGISTERED"
        for v in validate_rebuild(unregistered, _registry()).violations
    )


def test_full_rebuild_requires_exact_source_binding_or_closure_receipt() -> None:
    registry = _registry()
    with_source = replace(
        _rebuild(),
        mode="FULL",
        expected=None,
        source_revision=8,
        source_digest=_SOURCE_DIGEST,
    )
    assert validate_rebuild(with_source, registry).valid

    with_receipt = replace(
        _rebuild(),
        mode="FULL",
        expected=None,
        closure_receipt="receipt:closure-1",
    )
    assert validate_rebuild(with_receipt, registry).valid

    neither = replace(
        _rebuild(),
        mode="FULL",
        expected=None,
    )
    assert any(
        v.code == "REBUILD_SOURCE_BINDING_REQUIRED"
        for v in validate_rebuild(neither, registry).violations
    )

    incomplete = replace(
        _rebuild(),
        mode="FULL",
        expected=None,
        source_revision=8,
    )
    assert any(
        v.code == "REBUILD_SOURCE_PAIR_INCOMPLETE"
        for v in validate_rebuild(incomplete, registry).violations
    )

    conflict = replace(
        _rebuild(),
        mode="FULL",
        expected=None,
        source_revision=8,
        source_digest=_SOURCE_DIGEST,
        closure_receipt="receipt:closure-1",
    )
    assert any(
        v.code == "REBUILD_BINDING_CONFLICT"
        for v in validate_rebuild(conflict, registry).violations
    )


def test_rebuild_receipt_binds_scope_rebuild_projection_digest_and_time() -> None:
    receipt = _receipt()
    assert validate_rebuild_receipt(receipt).valid
    bad_projection_digest = replace(receipt, projection_digest="not-hex")
    assert any(
        v.code == "SOURCE_DIGEST_INVALID"
        for v in validate_rebuild_receipt(bad_projection_digest).violations
    )
    negative_generation = replace(receipt, projection_generation=-1)
    assert any(
        v.code == "RECEIPT_POSITION_NEGATIVE"
        for v in validate_rebuild_receipt(negative_generation).violations
    )


def test_registry_revision_advance_is_exact() -> None:
    current = _registry()
    advanced = current.advance_revision()
    assert validate_registry_revision_advance(current, advanced).valid

    double_advance = current.advance_revision().advance_revision()
    assert any(
        v.code == "REGISTRY_REVISION_ADVANCE_MISMATCH"
        for v in validate_registry_revision_advance(current, double_advance).violations
    )

    incarnation_change = replace(advanced, incarnation="other-inc")
    assert any(
        v.code == "REGISTRY_INCARNATION_CHANGE_FORBIDDEN"
        for v in validate_registry_revision_advance(
            current, incarnation_change
        ).violations
    )


def test_rebuild_plan_digest_is_deterministic() -> None:
    first = _rebuild()
    second = replace(
        first,
        expected=replace(first.expected or _expectation(), expected_source_revision=9),
    )
    assert rebuild_plan_digest(first) == rebuild_plan_digest(_rebuild())
    assert rebuild_plan_digest(first) != rebuild_plan_digest(second)


def test_offset_snapshot_covers_every_registered_projector() -> None:
    registry = _registry()
    offsets = (_offset(),)
    assert validate_offset_snapshot(registry, offsets).valid
    missing = validate_offset_snapshot(registry, ())
    assert any(v.code == "OFFSET_MISSING" for v in missing.violations)
    duplicate = validate_offset_snapshot(registry, offsets + offsets)
    assert any(v.code == "DUPLICATE_OFFSET_KEY" for v in duplicate.violations)


def test_rebuild_modes_are_full_and_incremental() -> None:
    assert tuple(REBUILD_MODES) == ("FULL", "INCREMENTAL")
