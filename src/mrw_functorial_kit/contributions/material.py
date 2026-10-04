"""Explicit kit contribution catalog for the native MRW C7 ingest family."""

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
from app.successor_runtime.capabilities.material_native_contribution import (
    DEFAULT_MATERIAL_NATIVE_SOURCE,
    compile_material_native_contribution,
)


def material_verification_plan_for(changes: object | None = None) -> VerificationPlan:
    """Derive an inert verification plan from the same native C7 catalog."""

    plan = plan_contribution_verification(
        tuple(
            VerificationSource(native.projection, native.verification)
            for native in material_native_catalog
        ),
        changes,
    )
    if isinstance(plan, Failure):
        raise RuntimeError(f"invalid C7 verification plan: {plan.message}")
    return plan


def _run_material_native_catalog_law() -> None:
    """Compile the default C7 definition and assert stable source identity."""

    compiled = compile_material_native_contribution(DEFAULT_MATERIAL_NATIVE_SOURCE)
    if isinstance(compiled, Failure):
        raise AssertionError("invalid default C7 native contribution")
    if compiled.projection.id != DEFAULT_MATERIAL_NATIVE_SOURCE.contribution_id:  # type: ignore[union-attr]
        raise AssertionError("C7 native catalog order drifted from source order")


_catalog_law = define_law_witness(
    "test_material_native_catalog_law",
    _run_material_native_catalog_law,
)
if isinstance(_catalog_law, Failure):
    raise RuntimeError(f"invalid C7 native catalog law: {_catalog_law.message}")


_default_compiled = compile_material_native_contribution(DEFAULT_MATERIAL_NATIVE_SOURCE)
if isinstance(_default_compiled, Failure):
    raise RuntimeError("invalid default C7 native contribution")
material_native_contributions = (_default_compiled,)
material_native_catalog = material_native_contributions

material_verification_plan = material_verification_plan_for()
_registered_verification_callbacks: dict[str, Callable[[], object]] = {}


def _register_verification_runner(name: str, run: Callable[[], object]) -> None:
    """Collect existing runner callbacks without executing them at import."""

    _registered_verification_callbacks[name] = run


_registration = register_verification_plan(
    material_verification_plan,
    _register_verification_runner,
)
if isinstance(_registration, Failure):
    raise RuntimeError(f"invalid C7 verification registration: {_registration.message}")
material_verification_registration: VerificationRegistration | None = _registration

_verification_witness_ids = (
    *(item.id for item in material_verification_plan.prerequisites),
    *(item.witness.id for item in material_verification_plan.checks),
)
material_verification_law_witnesses: tuple[LawWitness, ...] = tuple(
    LawWitness(
        witness_id,
        _registered_verification_callbacks[f"test:{witness_id}"],
    )
    for witness_id in _verification_witness_ids
)
material_law_witnesses: tuple[LawWitness, ...] = (
    _catalog_law,
    *material_verification_law_witnesses,
)
material_law_witness_references = tuple(
    law_witness_reference(witness) for witness in material_law_witnesses
)

material_contribution_catalog = tuple(
    native.projection for native in material_native_catalog
)
material_native_catalog = material_native_catalog
material_contribution_catalog = material_contribution_catalog
material_law_witnesses = material_law_witnesses
material_law_witness_references = material_law_witness_references
material_verification_law_witnesses = material_verification_law_witnesses
material_verification_plan = material_verification_plan
material_verification_plan_for = material_verification_plan_for
material_verification_registration = material_verification_registration

contribution_catalog = ContributionCatalog(
    contributions=material_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = [
    "material_contribution_catalog",
    "material_law_witness_references",
    "material_law_witnesses",
    "material_native_catalog",
    "material_native_contributions",
    "material_verification_law_witnesses",
    "material_verification_plan",
    "material_verification_plan_for",
    "material_verification_registration",
    "contribution_catalog",
    "material_contribution_catalog",
    "material_law_witness_references",
    "material_law_witnesses",
    "material_native_catalog",
    "material_verification_law_witnesses",
    "material_verification_plan",
    "material_verification_plan_for",
    "material_verification_registration",
]
