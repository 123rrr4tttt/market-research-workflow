"""Explicit kit contribution catalog for the native MRW C9 authority."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from app.successor_runtime.runtime.projection_native_contribution import (
    DEFAULT_PROJECTION_NATIVE_SOURCE,
    NON_DEFAULT_PROJECTION_NATIVE_SOURCE,
    PROJECTION_SOURCE_ANCHOR_OBJECT_SUFFIX,
    PROJECTION_SOURCE_VIEWS_OBJECT_SUFFIX,
    ProjectionNativeDefinition,
    compile_projection_native_contribution,
)
from app.successor_runtime.substrate.postgres import (
    projection_sources as projection_source_store,
)
from app.successor_runtime.substrate.projections import (
    projection_sources as projection_sources,
)
from functorial_kit.contribution_verification import (
    VerificationPlan,
    VerificationRegistration,
    VerificationSource,
    plan_contribution_verification,
    register_verification_plan,
)
from functorial_kit.contributions import ContributionCatalog, ContributionSketch
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import (
    LawWitness,
    define_law_witness,
    law_witness_reference,
)

from mrw_functorial_kit.core.projection_semantics import projection_processing_failures

_PROJECTION_SOURCE_OWNER = (
    "main/backend/app/successor_runtime/substrate/projections/projection_sources.py"
)
_PROJECTION_SOURCE_STORE_OWNER = (
    "main/backend/app/successor_runtime/substrate/postgres/projection_sources.py"
)
_PROJECTION_OFFSET_OWNER = (
    "main/backend/app/successor_runtime/substrate/postgres/projection_offsets.py"
)


def _projection_source_views_sketch(
    definition: ProjectionNativeDefinition,
) -> ContributionSketch:
    return ContributionSketch(
        (
            f"{definition.contribution_id}"
            f"{PROJECTION_SOURCE_VIEWS_OBJECT_SUFFIX}"
        ),
        {
            "shape": "views-fold",
            "objects": [
                {
                    "name": projection_sources.PROJECT_SOURCE_CLOSURE_SCHEMA,
                    "kind": "schema",
                    "owner": _PROJECTION_SOURCE_OWNER,
                },
                {
                    "name": projection_sources.TASK_VIEW_SCHEMA,
                    "kind": "schema",
                    "owner": _PROJECTION_SOURCE_OWNER,
                },
                {
                    "name": (
                        projection_sources.KNOWLEDGE_VIEW_SCHEMA
                    ),
                    "kind": "schema",
                    "owner": _PROJECTION_SOURCE_OWNER,
                },
                {
                    "name": projection_sources.MATERIAL_VIEW_SCHEMA,
                    "kind": "schema",
                    "owner": _PROJECTION_SOURCE_OWNER,
                },
            ],
            "operations": [
                {"name": "build_agent_session_payload", "order_depends_on": []},
                {"name": "build_research_graph_payload", "order_depends_on": []},
                {"name": "build_search_payload", "order_depends_on": []},
            ],
            "equations": [
                {
                    "claim": (
                        "terminal task status derives only from the ordered event chain"
                    ),
                    "class": "testable",
                    "witness": (
                        "test:test_runtime_terminal_status_derives_only_from_event_chain"
                    ),
                },
                {
                    "claim": (
                        "knowledge projection keeps objects and relations one-to-one"
                    ),
                    "class": "testable",
                    "witness": (
                        "test:test_graph_payload_keeps_objects_and_relations_one_to_one"
                    ),
                },
                {
                    "claim": (
                        "material segments retain field paths and NOT_EXECUTED provider status"
                    ),
                    "class": "testable",
                    "witness": (
                        "test:test_search_segments_carry_field_path_and_not_executed_statuses"
                    ),
                },
                {
                    "claim": (
                        "field-level loss records are bound to projection view payloads"
                    ),
                    "class": "testable",
                    "witness": (
                        "test:test_field_level_loss_records_are_bound_to_payloads"
                    ),
                },
            ],
            "failures": [projection_processing_failures.name],
            "axes": {
                "open": "projection interpreters",
                "closed": (
                    "task events and statuses, material segment kinds, loss kinds, "
                    "and project source schemas"
                ),
            },
            "derived": {"authoritative": False, "derived_as": "view"},
            "change": {
                "kind": "extension",
                "declared_loss": ["external provider realization"],
            },
        },
    )


def _projection_source_anchor_sketch(
    definition: ProjectionNativeDefinition,
) -> ContributionSketch:
    return ContributionSketch(
        (
            f"{definition.contribution_id}"
            f"{PROJECTION_SOURCE_ANCHOR_OBJECT_SUFFIX}"
        ),
        {
            "shape": "anchor",
            "objects": [
                {
                    "name": projection_sources.PROJECT_SOURCE_CLOSURE_SCHEMA,
                    "kind": "schema",
                    "owner": _PROJECTION_SOURCE_OWNER,
                },
                {
                    "name": projection_source_store.PROJECT_SOURCE_MANIFEST_SCHEMA,
                    "kind": "schema",
                    "owner": _PROJECTION_SOURCE_STORE_OWNER,
                },
                {
                    "name": projection_source_store.PROJECT_SOURCE_IDENTITY_PROJECTOR_ID,
                    "kind": "projector",
                    "owner": _PROJECTION_SOURCE_STORE_OWNER,
                },
                {
                    "name": "ProjectionOffsetKey",
                    "kind": "record",
                    "owner": _PROJECTION_OFFSET_OWNER,
                },
            ],
            "operations": [
                {"name": "build_semantic_source_closure", "order_depends_on": []},
                {
                    "name": "put_semantic_source_rows",
                    "order_depends_on": ["build_semantic_source_closure"],
                },
                {
                    "name": "load_exact_semantic_source_closure",
                    "order_depends_on": ["put_semantic_source_rows"],
                },
            ],
            "equations": [
                {
                    "claim": "same project source put is idempotent and loads exactly",
                    "class": "testable",
                    "witness": (
                        "test:test_same_closure_put_is_idempotent_and_loads_exact"
                    ),
                },
                {
                    "claim": (
                        "legitimate project source advance writes new versions and "
                        "retains old versions"
                    ),
                    "class": "testable",
                    "witness": (
                        "test:test_legitimate_advance_writes_new_versions_retains_old_and_loads_current"
                    ),
                },
                {
                    "claim": "reversion to an old project source closure fails closed",
                    "class": "testable",
                    "witness": "test:test_reversion_to_old_closure_fails_closed",
                },
                {
                    "claim": "project source payload tampering fails closed",
                    "class": "testable",
                    "witness": "test:test_payload_tamper_fails_closed",
                },
            ],
            "failures": [projection_processing_failures.name],
            "axes": {
                "open": "storage interpreters",
                "closed": (
                    "project source schemas, source identity projector, offset key, "
                    "and projection processing failures"
                ),
            },
            "derived": {"authoritative": False, "derived_as": "anchor"},
            "change": {
                "kind": "extension",
                "declared_loss": [
                    "live delivery, cutover, and runtime failure closure"
                ],
            },
        },
    )


def _attach_projection_source_sketches(native: object) -> object:
    definition = native.definition
    projection = replace(
        native.projection,
        sketches=(
            _projection_source_views_sketch(definition),
            _projection_source_anchor_sketch(definition),
        ),
    )
    return replace(native, projection=projection)


def projection_verification_plan_for(changes: object | None = None) -> VerificationPlan:
    plan = plan_contribution_verification(
        tuple(
            VerificationSource(native.projection, native.verification)
            for native in projection_native_catalog
        ),
        changes,
    )
    if isinstance(plan, Failure):
        raise RuntimeError(f"invalid C9 verification plan: {plan.message}")
    return plan


def _run_projection_native_catalog_law() -> None:
    default = compile_projection_native_contribution(DEFAULT_PROJECTION_NATIVE_SOURCE)
    non_default = compile_projection_native_contribution(NON_DEFAULT_PROJECTION_NATIVE_SOURCE)
    if isinstance(default, Failure) or isinstance(non_default, Failure):
        raise AssertionError("invalid default or non-default C9 native contribution")
    if tuple(native.projection.id for native in projection_native_catalog) != (default.projection.id,):
        raise AssertionError("C9 native catalog order drifted from source order")
    if default.projection.id == non_default.projection.id:
        raise AssertionError("C9 non-default source must have distinct identity")


_catalog_law = define_law_witness(
    "test_projection_native_catalog_law",
    _run_projection_native_catalog_law,
)
if isinstance(_catalog_law, Failure):
    raise RuntimeError(f"invalid C9 native catalog law: {_catalog_law.message}")


_default_compiled = (compile_projection_native_contribution(DEFAULT_PROJECTION_NATIVE_SOURCE),)
if any(isinstance(native, Failure) for native in _default_compiled):
    raise RuntimeError("invalid default C9 native contribution")
projection_native_contributions = tuple(
    _attach_projection_source_sketches(native) for native in _default_compiled
)
projection_native_catalog = projection_native_contributions
projection_verification_plan = projection_verification_plan_for()

_registered_verification_callbacks: dict[str, Callable[[], object]] = {}


def _register_verification_runner(name: str, run: Callable[[], object]) -> None:
    _registered_verification_callbacks[name] = run


_registration = register_verification_plan(
    projection_verification_plan,
    _register_verification_runner,
)
if isinstance(_registration, Failure):
    raise RuntimeError(f"invalid C9 verification registration: {_registration.message}")
projection_verification_registration: VerificationRegistration | None = _registration

_verification_witness_ids = (
    *(item.id for item in projection_verification_plan.prerequisites),
    *(item.witness.id for item in projection_verification_plan.checks),
)
projection_verification_law_witnesses: tuple[LawWitness, ...] = tuple(
    LawWitness(
        witness_id,
        _registered_verification_callbacks[f"test:{witness_id}"],
    )
    for witness_id in _verification_witness_ids
)
projection_law_witnesses: tuple[LawWitness, ...] = (
    _catalog_law,
    *projection_verification_law_witnesses,
)
projection_law_witness_references = tuple(law_witness_reference(w) for w in projection_law_witnesses)
projection_contribution_catalog = tuple(native.projection for native in projection_native_catalog)
projection_native_catalog = projection_native_catalog
projection_contribution_catalog = projection_contribution_catalog
projection_law_witnesses = projection_law_witnesses
projection_law_witness_references = projection_law_witness_references
projection_verification_law_witnesses = projection_verification_law_witnesses
projection_verification_plan = projection_verification_plan
projection_verification_plan_for = projection_verification_plan_for
projection_verification_registration = projection_verification_registration
contribution_catalog = ContributionCatalog(
    contributions=projection_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = [
    "projection_contribution_catalog",
    "projection_law_witness_references",
    "projection_law_witnesses",
    "projection_native_catalog",
    "projection_native_contributions",
    "projection_verification_law_witnesses",
    "projection_verification_plan",
    "projection_verification_plan_for",
    "projection_verification_registration",
    "contribution_catalog",
    "projection_contribution_catalog",
    "projection_law_witness_references",
    "projection_law_witnesses",
    "projection_native_catalog",
    "projection_verification_law_witnesses",
    "projection_verification_plan",
    "projection_verification_plan_for",
    "projection_verification_registration",
]
