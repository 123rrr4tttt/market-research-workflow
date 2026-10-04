"""Explicit kit contribution catalog for the native MRW C4 family."""

from __future__ import annotations

from collections.abc import Callable

from app.successor_runtime.assembly.base import BatchTaskAssemblyOptions
from app.successor_runtime.capabilities.batch_task_native_contribution import (
    ASSEMBLY_CELL_IDS,
    DEFAULT_BATCH_TASK_NATIVE_SOURCE,
    BatchTaskAssemblyContext,
    compile_batch_task_native_contribution,
)
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


def batch_verification_plan_for(
    changes: object | None = None,
) -> VerificationPlan:
    """Derive an inert verification plan from the same native C4 catalog."""

    plan = plan_contribution_verification(
        tuple(
            VerificationSource(native.projection, native.verification)
            for native in batch_native_catalog
        ),
        changes,
    )
    if isinstance(plan, Failure):
        raise RuntimeError(f"invalid C4 verification plan: {plan.message}")
    return plan


def _run_batch_native_catalog_law() -> None:
    """Exercise the default native definition and its inert assembly law."""

    native = compile_batch_task_native_contribution(DEFAULT_BATCH_TASK_NATIVE_SOURCE)
    if isinstance(native, Failure):
        raise AssertionError(native.message)
    binding = native.assemble(
        BatchTaskAssemblyContext(
            uow_factory=lambda: None,
            project_scope_digest="0" * 64,
            definition=native.definition,
            options=BatchTaskAssemblyOptions(),
        )
    )
    if isinstance(binding, Failure):
        raise AssertionError(binding.message)
    assert tuple(cell.cell_id for cell in binding.family_assembly.cells) == ASSEMBLY_CELL_IDS


_catalog_law = define_law_witness(
    "test_batch_native_catalog_law",
    _run_batch_native_catalog_law,
)
if isinstance(_catalog_law, Failure):
    raise RuntimeError(f"invalid C4 native catalog law: {_catalog_law.message}")

# This tuple is the sole native C4 contribution catalog.  Runtime consumers and
# the factory-free generated projections both derive from it.
batch_native_contribution = compile_batch_task_native_contribution(DEFAULT_BATCH_TASK_NATIVE_SOURCE)
if isinstance(batch_native_contribution, Failure):
    raise RuntimeError(f"invalid default C4 native contribution: {batch_native_contribution.message}")
batch_native_catalog = (batch_native_contribution,)


batch_verification_plan = batch_verification_plan_for()
_registered_verification_callbacks: dict[str, Callable[[], object]] = {}


def _register_verification_runner(name: str, run: Callable[[], object]) -> None:
    """Existing C4 runner target: collect plan callbacks without running them."""

    _registered_verification_callbacks[name] = run


_registration = register_verification_plan(batch_verification_plan, _register_verification_runner)
if isinstance(_registration, Failure):
    raise RuntimeError(f"invalid C4 verification registration: {_registration.message}")
batch_verification_registration: VerificationRegistration | None = _registration

_verification_plan_witness_ids = (
    *(item.id for item in batch_verification_plan.prerequisites),
    *(item.witness.id for item in batch_verification_plan.checks),
)
batch_verification_law_witnesses: tuple[LawWitness, ...] = tuple(
    LawWitness(
        witness_id,
        _registered_verification_callbacks[f"test:{witness_id}"],
    )
    for witness_id in _verification_plan_witness_ids
)
batch_law_witnesses: tuple[LawWitness, ...] = (_catalog_law, *batch_verification_law_witnesses)
batch_law_witness_references = tuple(
    law_witness_reference(witness) for witness in batch_law_witnesses
)

batch_contribution_catalog = tuple(native.projection for native in batch_native_catalog)
batch_native_catalog = batch_native_catalog
batch_contribution_catalog = batch_contribution_catalog
batch_law_witnesses = batch_law_witnesses
batch_law_witness_references = batch_law_witness_references
batch_verification_law_witnesses = batch_verification_law_witnesses
batch_verification_plan = batch_verification_plan
batch_verification_plan_for = batch_verification_plan_for
batch_verification_registration = batch_verification_registration

contribution_catalog = ContributionCatalog(
    contributions=batch_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = [
    "batch_contribution_catalog",
    "batch_law_witness_references",
    "batch_law_witnesses",
    "batch_native_catalog",
    "batch_native_contribution",
    "batch_verification_law_witnesses",
    "batch_verification_plan",
    "batch_verification_plan_for",
    "batch_verification_registration",
    "contribution_catalog",
    "batch_contribution_catalog",
    "batch_law_witness_references",
    "batch_law_witnesses",
    "batch_native_catalog",
    "batch_verification_law_witnesses",
    "batch_verification_plan",
    "batch_verification_plan_for",
    "batch_verification_registration",
]
