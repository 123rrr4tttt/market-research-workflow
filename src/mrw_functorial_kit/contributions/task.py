"""Explicit kit contribution catalog for the native MRW C5 family."""

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

from app.successor_runtime.runtime.task_observation_native_contribution import (
    DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE,
    NON_DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE,
    compile_task_observation_native_contribution,
)

_C5_SOURCES = (DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE, NON_DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE)


def task_verification_plan_for(
    changes: object | None = None,
) -> VerificationPlan:
    """Derive an inert verification plan from the same native C5 catalog."""

    plan = plan_contribution_verification(
        tuple(
            VerificationSource(native.projection, native.verification)
            for native in task_native_catalog
        ),
        changes,
    )
    if isinstance(plan, Failure):
        raise RuntimeError(f"invalid C5 verification plan: {plan.message}")
    return plan


def _run_task_native_catalog_law() -> None:
    """Compile both authored definitions and assert stable catalog order."""

    compiled = tuple(compile_task_observation_native_contribution(source) for source in _C5_SOURCES)
    if any(isinstance(native, Failure) for native in compiled):
        raise AssertionError("invalid default C5 native contribution")
    expected = tuple(native.projection.id for native in compiled)  # type: ignore[union-attr]
    if tuple(native.projection.id for native in task_native_catalog) != expected:
        raise AssertionError("C5 native catalog order drifted from definition order")


_catalog_law = define_law_witness(
    "test_task_native_catalog_law",
    _run_task_native_catalog_law,
)
if isinstance(_catalog_law, Failure):
    raise RuntimeError(f"invalid C5 native catalog law: {_catalog_law.message}")


_default_compiled = tuple(compile_task_observation_native_contribution(source) for source in _C5_SOURCES)
if any(isinstance(native, Failure) for native in _default_compiled):
    raise RuntimeError("invalid C5 native contribution")
task_native_contributions = _default_compiled
task_native_catalog = task_native_contributions

task_verification_plan = task_verification_plan_for()
_registered_verification_callbacks: dict[str, Callable[[], object]] = {}


def _register_verification_runner(name: str, run: Callable[[], object]) -> None:
    """Collect existing runner callbacks without executing them at import."""

    _registered_verification_callbacks[name] = run


_registration = register_verification_plan(
    task_verification_plan,
    _register_verification_runner,
)
if isinstance(_registration, Failure):
    raise RuntimeError(f"invalid C5 verification registration: {_registration.message}")
task_verification_registration: VerificationRegistration | None = _registration

_verification_witness_ids = (
    *(item.id for item in task_verification_plan.prerequisites),
    *(item.witness.id for item in task_verification_plan.checks),
)
task_verification_law_witnesses: tuple[LawWitness, ...] = tuple(
    LawWitness(
        witness_id,
        _registered_verification_callbacks[f"test:{witness_id}"],
    )
    for witness_id in _verification_witness_ids
)
task_law_witnesses: tuple[LawWitness, ...] = (
    _catalog_law,
    *task_verification_law_witnesses,
)
task_law_witness_references = tuple(law_witness_reference(witness) for witness in task_law_witnesses)

task_contribution_catalog = tuple(native.projection for native in task_native_catalog)
task_native_catalog = task_native_catalog
task_contribution_catalog = task_contribution_catalog
task_law_witnesses = task_law_witnesses
task_law_witness_references = task_law_witness_references
task_verification_law_witnesses = task_verification_law_witnesses
task_verification_plan = task_verification_plan
task_verification_plan_for = task_verification_plan_for
task_verification_registration = task_verification_registration

contribution_catalog = ContributionCatalog(
    contributions=task_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = [
    "task_contribution_catalog",
    "task_law_witness_references",
    "task_law_witnesses",
    "task_native_catalog",
    "task_native_contributions",
    "task_verification_law_witnesses",
    "task_verification_plan",
    "task_verification_plan_for",
    "task_verification_registration",
    "contribution_catalog",
    "task_contribution_catalog",
    "task_law_witness_references",
    "task_law_witnesses",
    "task_native_catalog",
    "task_verification_law_witnesses",
    "task_verification_plan",
    "task_verification_plan_for",
    "task_verification_registration",
]
