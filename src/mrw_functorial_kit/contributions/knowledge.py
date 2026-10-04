"""Explicit kit contribution catalog for the native MRW C8 cells."""

from __future__ import annotations

from collections.abc import Callable

from functorial_kit.contribution_verification import (
    VerificationPlan,
    VerificationRegistration,
    VerificationSource,
    plan_contribution_verification,
    register_verification_plan,
)
from functorial_kit.contributions import ContributionCatalog
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import (
    LawWitness,
    define_law_witness,
    law_witness_reference,
)
from app.successor_runtime.capabilities.knowledge_graph_projection_contribution import (
    KnowledgeGraphProjectionAssemblyContext,
)
from mrw_functorial_kit.contributions.knowledge_graph_projection import knowledge_graph_projection_native_contributions
from app.successor_runtime.capabilities.knowledge_native_contribution import KnowledgeNativeAssemblyContext
from app.successor_runtime.capabilities.knowledge_program import (
    build_knowledge_bundle,
    knowledge_native_contributions,
    validate_knowledge_graph_projection_contributions,
    validate_knowledge_native_contributions,
)


def knowledge_verification_plan_for(
    changes: object | None = None,
) -> VerificationPlan:
    """Derive an inert verification plan from the same native catalog.

    Without known changes, the plan selects the full C8 catalog.
    """

    plan = plan_contribution_verification(
        tuple(
            VerificationSource(native.projection, native.verification)
            for native in knowledge_native_catalog
        ),
        changes,
    )
    if isinstance(plan, Failure):
        raise RuntimeError(f"invalid C8 verification plan: {plan.message}")
    return plan


def _run_knowledge_native_catalog_law() -> None:
    """Exercise all native definitions, assembly order, and codec identity."""

    native_contributions = validate_knowledge_native_contributions(knowledge_native_contributions)
    graph_contributions = validate_knowledge_graph_projection_contributions(
        knowledge_graph_projection_native_contributions
    )
    natives = (*native_contributions, *graph_contributions)
    projected_ids = tuple(native.projection.id for native in natives)
    expected_ids = tuple(native.definition.contribution_id for native in natives)
    if projected_ids != expected_ids:
        raise AssertionError("native contribution order drifted from definition order")

    for native in native_contributions:
        binding = native.assemble(KnowledgeNativeAssemblyContext())
        if isinstance(binding, Failure):
            raise AssertionError(binding.message)
    for native in graph_contributions:
        binding = native.assemble(KnowledgeGraphProjectionAssemblyContext())
        if isinstance(binding, Failure):
            raise AssertionError(binding.message)

    bundle = build_knowledge_bundle(
        native_composition=native_contributions,
        graph_projection_composition=graph_contributions,
    )
    expected_kinds: tuple[str, ...] = ()
    for native in native_contributions:
        expected_kinds += tuple(
            operation.source.kind for operation in native.definition.operations
        )
    expected_kinds += tuple(
        native.definition.kind for native in graph_contributions
    )
    actual_kinds = tuple(operation.ref.kind for operation in bundle.operations)
    if actual_kinds != expected_kinds:
        raise AssertionError("C8 operation order drifted from native catalog order")
    for native in native_contributions:
        for operation in native.definition.operations:
            bundle_operation = next(
                candidate
                for candidate in bundle.operations
                if candidate.ref.kind == operation.source.kind
            )
            if bundle_operation != operation.operation_contract:
                raise AssertionError(
                    f"{native.definition.cell_id} operation contract drift"
                )
            if operation.payload_codec is not None:
                if bundle.codec_by_kind(operation.source.kind) is not operation.payload_codec:
                    raise AssertionError(
                        f"{native.definition.cell_id} payload codec identity drift"
                    )
            if bundle.profiles[native.definition.cell_id] != dict(native.definition.profiles):
                raise AssertionError(f"{native.definition.cell_id} profile binding drift")
    for native in graph_contributions:
        definition = native.definition
        bundle_operation = next(
            candidate
            for candidate in bundle.operations
            if candidate.ref.kind == definition.kind
        )
        if bundle_operation != definition.operation_contract:
            raise AssertionError(f"{definition.cell_id} operation contract drift")
        if bundle.codec_by_kind(definition.kind) is not definition.payload_codec:
            raise AssertionError(f"{definition.cell_id} payload codec identity drift")
        if bundle.profiles[definition.cell_id] != dict(definition.profiles):
            raise AssertionError(f"{definition.cell_id} profile binding drift")


_catalog_law = define_law_witness(
    "test_knowledge_native_catalog_law",
    _run_knowledge_native_catalog_law,
)
if isinstance(_catalog_law, Failure):
    raise RuntimeError(f"invalid C8 native catalog law: {_catalog_law.message}")

# This tuple is the sole native C8 contribution catalog. Runtime consumers and
# the factory-free generated projections both derive from it.
knowledge_native_catalog = (*knowledge_native_contributions, *knowledge_graph_projection_native_contributions)

_registered_verification_callbacks: dict[str, Callable[[], object]] = {}


def _register_verification_runner(name: str, run: Callable[[], object]) -> None:
    """Existing C8 runner target: collect plan callbacks without running them."""

    _registered_verification_callbacks[name] = run


knowledge_verification_plan = knowledge_verification_plan_for()
knowledge_verification_registration: VerificationRegistration | None
_registration = register_verification_plan(knowledge_verification_plan, _register_verification_runner)
if isinstance(_registration, Failure):
    raise RuntimeError(f"invalid C8 verification registration: {_registration.message}")
knowledge_verification_registration = _registration

_verification_plan_witness_ids = (
    *(item.id for item in knowledge_verification_plan.prerequisites),
    *(item.witness.id for item in knowledge_verification_plan.checks),
)
knowledge_verification_law_witnesses: tuple[LawWitness, ...] = tuple(
    LawWitness(
        witness_id,
        _registered_verification_callbacks[f"test:{witness_id}"],
    )
    for witness_id in _verification_plan_witness_ids
)
knowledge_law_witnesses: tuple[LawWitness, ...] = (_catalog_law, *knowledge_verification_law_witnesses)
knowledge_law_witness_references = tuple(
    law_witness_reference(witness) for witness in knowledge_law_witnesses
)

knowledge_contribution_catalog = tuple(native.projection for native in knowledge_native_catalog)
knowledge_native_catalog = knowledge_native_catalog
knowledge_contribution_catalog = knowledge_contribution_catalog
knowledge_law_witnesses = knowledge_law_witnesses
knowledge_law_witness_references = knowledge_law_witness_references
knowledge_verification_law_witnesses = knowledge_verification_law_witnesses
knowledge_verification_plan = knowledge_verification_plan
knowledge_verification_plan_for = knowledge_verification_plan_for
knowledge_verification_registration = knowledge_verification_registration

contribution_catalog = ContributionCatalog(
    contributions=knowledge_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = [
    "knowledge_contribution_catalog",
    "knowledge_verification_law_witnesses",
    "knowledge_verification_plan",
    "knowledge_verification_plan_for",
    "knowledge_verification_registration",
    "knowledge_law_witness_references",
    "knowledge_law_witnesses",
    "knowledge_native_catalog",
    "contribution_catalog",
    "knowledge_contribution_catalog",
    "knowledge_law_witness_references",
    "knowledge_law_witnesses",
    "knowledge_native_catalog",
    "knowledge_verification_law_witnesses",
    "knowledge_verification_plan",
    "knowledge_verification_plan_for",
    "knowledge_verification_registration",
]
