"""Project-bound semantic parameters for the shared information topology.

The topology owns structural storage and operations. A project contributes a
versioned semantic value and a profile factory; readers, validators, mappings,
and projections can then use the same resolved binding without making that
semantic a framework-wide vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Protocol, TypeVar

from functorial_kit import Failure

from .contracts import BoundRef, topology_failures
from .profiles import ProfileSpec


class ProjectBoundSemantics(Protocol):
    """A semantic declaration anchored to its authoritative observation."""

    source_ref: BoundRef


SemanticT = TypeVar("SemanticT", bound=ProjectBoundSemantics)


@dataclass(frozen=True, slots=True)
class ProjectSemanticBinding(Generic[SemanticT]):
    """Resolved semantic parameter and its topology profile for one project."""

    project_key: str
    semantics: SemanticT
    profile: ProfileSpec


SemanticReader = Callable[..., SemanticT | Failure]
ProfileFactory = Callable[[SemanticT], ProfileSpec]


def resolve_project_semantics(
    reader: SemanticReader[SemanticT],
    source_ref: BoundRef,
    *,
    project_key: str,
    expected_profile_id: str | None = None,
    expected_profile_version: str | None = None,
    profile_factory: ProfileFactory[SemanticT],
) -> ProjectSemanticBinding[SemanticT] | Failure:
    """Resolve an exact project semantic observation into a topology parameter.

    The reader is supplied by the owning module. This common boundary checks
    project identity, exact observed revision, and the derived profile identity;
    it does not know retrieval/Rapid fields or execute module behavior.
    """
    if source_ref.ref.project_key != project_key:
        return topology_failures.fail("UNRESOLVABLE_REFERENCE", "semantic binding belongs to another project")
    if not source_ref.observed_revision.strip():
        return topology_failures.fail("STALE_REFERENCE", "semantic binding revision is required")
    if (expected_profile_id is None) != (expected_profile_version is None):
        return topology_failures.fail(
            "INVALID_STRUCTURE", "expected topology profile identity must include both id and version"
        )
    semantics = reader(
        source_ref=source_ref.ref,
        observed_revision=source_ref.observed_revision,
        content_digest=source_ref.content_digest,
    )
    if isinstance(semantics, Failure):
        return semantics
    resolved_ref = getattr(semantics, "source_ref", None)
    if not isinstance(resolved_ref, BoundRef):
        return topology_failures.fail("INVALID_STRUCTURE", "semantic reader returned a value without a bound source reference")
    if resolved_ref != source_ref:
        return topology_failures.fail(
            "STALE_REFERENCE", "semantic reader could not resolve the requested observation",
            {"requested_revision": source_ref.observed_revision,
             "resolved_revision": getattr(resolved_ref, "observed_revision", None)},
        )
    try:
        profile = profile_factory(semantics)
    except (AttributeError, TypeError, ValueError) as exc:
        return topology_failures.fail("INVALID_STRUCTURE", "project semantic declaration is invalid", {"reason": str(exc)})
    if expected_profile_id is not None and (profile.profile_id, profile.version) != (
        expected_profile_id, expected_profile_version
    ):
        return topology_failures.fail(
            "STALE_REFERENCE", "project semantics do not match the requested topology profile",
            {"expected_profile_id": expected_profile_id, "expected_profile_version": expected_profile_version,
             "resolved_profile_id": profile.profile_id, "resolved_profile_version": profile.version},
        )
    return ProjectSemanticBinding(project_key, semantics, profile)


__all__ = [
    "ProjectBoundSemantics", "ProjectSemanticBinding", "ProfileFactory",
    "SemanticReader", "resolve_project_semantics",
]
