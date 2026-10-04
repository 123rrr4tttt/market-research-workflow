"""Current workflow-definition native contribution catalog."""

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
from app.successor_runtime.capabilities.workflow_native_contribution import (
    WorkflowAssemblyContext,
    DEFAULT_WORKFLOW_NATIVE_SOURCE,
    compile_workflow_native_contribution,
)



def workflow_verification_plan_for(
    changes: object | None = None,
) -> VerificationPlan:
    """Derive an inert verification plan from the workflow-definition catalog."""

    plan = plan_contribution_verification(
        tuple(
            VerificationSource(native.projection, native.verification)
            for native in workflow_native_catalog
        ),
        changes,
    )
    if isinstance(plan, Failure):
        raise RuntimeError(  # noqa: TRY004, TRY003
            f"invalid workflow-definition verification plan: {plan.message}"
        )
    return plan


def _run_workflow_native_catalog_law() -> None:
    """Compile the authored DSL source and bind the workflow assembly."""

    native = compile_workflow_native_contribution(DEFAULT_WORKFLOW_NATIVE_SOURCE)
    if isinstance(native, Failure):
        raise AssertionError(native.message)  # noqa: TRY004, TRY301, B904
    expected_projection_ids = tuple(
        compile_workflow_native_contribution(source).projection.id  # type: ignore[union-attr]
        for source in (DEFAULT_WORKFLOW_NATIVE_SOURCE,)
    )
    if (native.projection.id,) != expected_projection_ids:
        raise AssertionError(  # noqa: TRY003
            "workflow native catalog order drifted from definition order"
        )
    from app.successor_runtime.assembly.base import local_assembly_scope_digest

    binding = native.assemble(
        WorkflowAssemblyContext(
            project_scope_digest=local_assembly_scope_digest(),
        )
    )
    if isinstance(binding, Failure):
        raise AssertionError(binding.message)  # noqa: TRY004, TRY301, B904


_catalog_law = define_law_witness(
    "test_workflow_native_catalog_law",
    _run_workflow_native_catalog_law,
)
if isinstance(_catalog_law, Failure):
    raise RuntimeError(  # noqa: TRY004, TRY003
            f"invalid workflow native catalog law: {_catalog_law.message}"
        )

# This tuple is the sole current workflow-definition native catalog. Historical
# compiler and acceptance authorities remain versioned read/assembly facts.
workflow_native_contribution = compile_workflow_native_contribution(DEFAULT_WORKFLOW_NATIVE_SOURCE)
if isinstance(workflow_native_contribution, Failure):
    raise RuntimeError(  # noqa: TRY004, TRY003
            f"invalid default workflow native contribution: {workflow_native_contribution.message}"
        )
workflow_native_catalog = (workflow_native_contribution,)

_registered_verification_callbacks: dict[str, Callable[[], object]] = {}


def _register_verification_runner(name: str, run: Callable[[], object]) -> None:
    """Existing verification runner target: collect callbacks without running them."""

    _registered_verification_callbacks[name] = run


workflow_verification_plan = workflow_verification_plan_for()
_registration = register_verification_plan(workflow_verification_plan, _register_verification_runner)
if isinstance(_registration, Failure):
    raise RuntimeError(  # noqa: TRY004, TRY003
            f"invalid workflow verification registration: {_registration.message}"
        )
workflow_verification_registration: VerificationRegistration | None = _registration

_verification_plan_witness_ids = (
    *(item.id for item in workflow_verification_plan.prerequisites),
    *(item.witness.id for item in workflow_verification_plan.checks),
)
workflow_verification_law_witnesses: tuple[LawWitness, ...] = tuple(
    LawWitness(
        witness_id,
        _registered_verification_callbacks[f"test:{witness_id}"],
    )
    for witness_id in _verification_plan_witness_ids
)
workflow_law_witnesses: tuple[LawWitness, ...] = (_catalog_law, *workflow_verification_law_witnesses)
workflow_law_witness_references = tuple(
    law_witness_reference(witness) for witness in workflow_law_witnesses
)

workflow_contribution_catalog = tuple(native.projection for native in workflow_native_catalog)
workflow_native_catalog = workflow_native_catalog
workflow_contribution_catalog = workflow_contribution_catalog
workflow_law_witnesses = workflow_law_witnesses
workflow_law_witness_references = workflow_law_witness_references
workflow_verification_law_witnesses = workflow_verification_law_witnesses
workflow_verification_plan = workflow_verification_plan
workflow_verification_plan_for = workflow_verification_plan_for
workflow_verification_registration = workflow_verification_registration

contribution_catalog = ContributionCatalog(
    contributions=workflow_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = [
    "workflow_contribution_catalog",
    "workflow_law_witness_references",
    "workflow_law_witnesses",
    "workflow_native_catalog",
    "workflow_native_contribution",
    "workflow_verification_law_witnesses",
    "workflow_verification_plan",
    "workflow_verification_plan_for",
    "workflow_verification_registration",
    "contribution_catalog",
    "workflow_contribution_catalog",
    "workflow_law_witness_references",
    "workflow_law_witnesses",
    "workflow_native_catalog",
    "workflow_verification_law_witnesses",
    "workflow_verification_plan",
    "workflow_verification_plan_for",
    "workflow_verification_registration",
]
