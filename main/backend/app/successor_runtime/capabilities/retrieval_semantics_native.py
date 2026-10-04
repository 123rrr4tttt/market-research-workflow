"""Native declaration contribution for the retrieval and topology registries.

The information-topology failure family, the project-retrieval failure family
and the canonical topology-state codec stay authored in their service modules.
This rule lowers those same objects into the project contribution catalog so the
registry entries are derived from one declaration instead of restated here.
It declares no runtime binding and performs no effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from functorial_kit.contribution_compiler import (
    NativeContributionRule,
    compile_native_contribution,
)
from functorial_kit.contributions import contribution_failures
from functorial_kit.core.codec import Codec
from functorial_kit.core.failure import Failure, FailureFamily
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    ProjectedContributionSpec,
)

from app.successor_runtime.capabilities.retrieval_common import (
    project_retrieval_failures,
    topology_failures,
    topology_state_codec,
)


@dataclass(frozen=True, slots=True)
class RetrievalSemanticsSource:
    """References to the authoritative declarations that enter the registry."""

    contribution_id: str
    owner: str
    failures: tuple[FailureFamily, ...]
    codecs: tuple[Codec[Any], ...]


DEFAULT_RETRIEVAL_SEMANTICS_SOURCE = RetrievalSemanticsSource(
    contribution_id="mrw.retrieval.semantics.native.v1",
    owner="successor_runtime.capabilities.retrieval_semantics_native",
    failures=(topology_failures, project_retrieval_failures),
    codecs=(topology_state_codec,),
)


@dataclass(frozen=True, slots=True)
class RetrievalSemanticsDefinition:
    source: RetrievalSemanticsSource

    @property
    def contribution_id(self) -> str:
        return self.source.contribution_id


def lower_retrieval_semantics_source(
    source: RetrievalSemanticsSource,
) -> RetrievalSemanticsDefinition | Failure:
    issues: list[dict[str, str]] = []
    if not source.contribution_id.strip():
        issues.append({"code": "invalid_spec", "path": "$.source.contribution_id", "message": "must be nonempty"})
    if not source.owner.strip():
        issues.append({"code": "invalid_spec", "path": "$.source.owner", "message": "must be nonempty"})
    for index, family in enumerate(source.failures):
        if not isinstance(family, FailureFamily) or not family.name or not family.codes:
            issues.append(
                {
                    "code": "invalid_spec",
                    "path": f"$.source.failures[{index}]",
                    "message": "must be a named failure family with at least one code",
                }
            )
    for index, codec in enumerate(source.codecs):
        if not isinstance(codec, Codec) or not codec.name or not codec.discriminant:
            issues.append(
                {
                    "code": "invalid_spec",
                    "path": f"$.source.codecs[{index}]",
                    "message": "must be a named kit codec",
                }
            )
    if issues:
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "retrieval semantics definition is invalid",
            {"issues": tuple(issues)},
        )
    return RetrievalSemanticsDefinition(source)


def project_retrieval_semantics_definition(
    definition: RetrievalSemanticsDefinition,
) -> ProjectedContributionSpec:
    source = definition.source
    return ProjectedContributionSpec(
        id=source.contribution_id,
        owner=source.owner,
        failures=source.failures,
        codecs=source.codecs,
    )


def assemble_retrieval_semantics_definition(
    definition: RetrievalSemanticsDefinition, _context: Any = None,
) -> RetrievalSemanticsDefinition:
    """Assembly yields the declarations themselves; this contribution has no effect."""

    return definition


def validate_retrieval_semantics_binding(
    definition: RetrievalSemanticsDefinition, candidate: object,
) -> BindingAccepted[RetrievalSemanticsDefinition] | BindingRejected:
    if isinstance(candidate, RetrievalSemanticsDefinition) and candidate == definition:
        return BindingAccepted(candidate)
    return BindingRejected(
        (NativeBindingIssue("$.binding", "retrieval semantics binding definition mismatch"),)
    )


RETRIEVAL_SEMANTICS_NATIVE_RULE = NativeContributionRule[
    RetrievalSemanticsSource, RetrievalSemanticsDefinition, object, RetrievalSemanticsDefinition
](
    lower=lower_retrieval_semantics_source,
    project=project_retrieval_semantics_definition,
    assemble=assemble_retrieval_semantics_definition,
    validate_binding=validate_retrieval_semantics_binding,
)


def compile_retrieval_semantics_native(source: RetrievalSemanticsSource):
    return compile_native_contribution(source, RETRIEVAL_SEMANTICS_NATIVE_RULE)


__all__ = [
    "DEFAULT_RETRIEVAL_SEMANTICS_SOURCE",
    "RETRIEVAL_SEMANTICS_NATIVE_RULE",
    "RetrievalSemanticsDefinition",
    "RetrievalSemanticsSource",
    "compile_retrieval_semantics_native",
]
