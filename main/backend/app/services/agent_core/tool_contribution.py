"""Native contribution rule for the existing project Core tool registry.

Authors supply one ``ProjectToolAuthorSource`` containing the original
``CoreToolSpec`` and special handler.  The rule validates and lowers that source
to the existing ``FacilityBinding``; projection and assembly stay inert until a
caller explicitly invokes the registered handler.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from functorial_kit import Failure
from functorial_kit.contribution_compiler import (
    NativeContributionRule,
    compile_native_contribution,
)
from functorial_kit.contributions import ContributionObject, contribution_failures
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    NativeContribution,
    ProjectedContributionSpec,
)

from .contracts import CoreToolSpec
from .macro_tools import FacilityBinding, FacilityHandler, facility_tool_projection


PROJECT_TOOL_REGISTRY_OWNER = "app.services.agent_core.registry.CoreToolRegistry"
PROJECT_TOOL_CONTRIBUTION_OWNER = "app.services.agent_core.project_tools"


class ProjectToolRegistry(Protocol):
    def get(self, tool_name: str) -> CoreToolSpec | None: ...

    def register(self, spec: CoreToolSpec, handler: FacilityHandler) -> Failure | None: ...


@dataclass(frozen=True, slots=True)
class ProjectToolAuthorSource:
    """Authored semantics and original implementation for one static Core tool."""

    binding_id: str
    version: str
    tool_spec: CoreToolSpec
    handler: FacilityHandler | None
    executor_ref: str
    scope_source: str
    permission_source: str
    failure_family: str
    readback_semantics: str
    governed_dispatch_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectToolAssemblyContext:
    """The existing registry target; it grants no business-effect authority."""

    registry_owner: str = PROJECT_TOOL_REGISTRY_OWNER


@dataclass(frozen=True, slots=True)
class ProjectToolBinding:
    """One validated registry entry derived from its native definition."""

    definition: FacilityBinding
    registry_owner: str
    spec: CoreToolSpec
    handler: FacilityHandler


def _invalid(*issues: tuple[str, str]) -> Failure:
    return contribution_failures.fail(
        "CONTRIBUTION_INVALID",
        "project tool contribution is invalid",
        {
            "issues": tuple(
                {
                    "code": "invalid_spec",
                    "path": path,
                    "message": message,
                }
                for path, message in issues
            )
        },
    )


def lower_project_tool_source(source: ProjectToolAuthorSource) -> FacilityBinding | Failure:
    if not isinstance(source, ProjectToolAuthorSource):
        return _invalid(("$.source", "source must be a ProjectToolAuthorSource"))

    issues: list[tuple[str, str]] = []
    for name in (
        "binding_id",
        "version",
        "executor_ref",
        "scope_source",
        "permission_source",
        "failure_family",
        "readback_semantics",
    ):
        value = getattr(source, name)
        if not isinstance(value, str) or not value.strip():
            issues.append((f"$.source.{name}", "nonempty semantic reference required"))
    if not isinstance(source.tool_spec, CoreToolSpec):
        issues.append(("$.source.tool_spec", "tool_spec must be a CoreToolSpec"))
    else:
        if not isinstance(source.tool_spec.name, str) or not source.tool_spec.name.strip():
            issues.append(("$.source.tool_spec.name", "tool name is required"))
        if (
            not isinstance(source.tool_spec.description_for_model, str)
            or not source.tool_spec.description_for_model.strip()
        ):
            issues.append((
                "$.source.tool_spec.description_for_model",
                "model description is required",
            ))
        if (
            not isinstance(source.tool_spec.input_schema, Mapping)
            or source.tool_spec.input_schema.get("type") != "object"
        ):
            issues.append((
                "$.source.tool_spec.input_schema",
                "tool input schema must describe an object",
            ))
    if not callable(source.handler):
        issues.append(("$.source.handler", "tool contribution needs an actual handler"))
    if issues:
        return _invalid(*issues)

    try:
        return FacilityBinding(
            binding_id=source.binding_id,
            version=source.version,
            tool_spec=source.tool_spec,
            handler=source.handler,
            executor_ref=source.executor_ref,
            scope_source=source.scope_source,
            permission_source=source.permission_source,
            failure_family=source.failure_family,
            readback_semantics=source.readback_semantics,
            input_policy="project_tool_contract",
            governed_dispatch_ref=source.governed_dispatch_ref,
        )
    except (TypeError, ValueError) as exc:
        return _invalid(("$.source", str(exc)))


def project_project_tool_definition(
    definition: FacilityBinding,
) -> ProjectedContributionSpec:
    contribution_id = f"{definition.binding_id}@{definition.version}"
    references = (
        definition.tool_spec.name,
        definition.executor_ref,
        definition.scope_source,
        definition.permission_source,
        definition.failure_family,
        definition.readback_semantics,
    )
    return ProjectedContributionSpec(
        id=contribution_id,
        owner=PROJECT_TOOL_CONTRIBUTION_OWNER,
        objects=(
            ContributionObject(
                contribution_id,
                "ProjectCoreTool",
                PROJECT_TOOL_CONTRIBUTION_OWNER,
                references,
            ),
        ),
    )


def assemble_project_tool_definition(
    definition: FacilityBinding,
    context: ProjectToolAssemblyContext,
) -> ProjectToolBinding | Failure:
    if (
        not isinstance(context, ProjectToolAssemblyContext)
        or context.registry_owner != PROJECT_TOOL_REGISTRY_OWNER
    ):
        return _invalid((
            "$.context.registry_owner",
            "project tool must target the existing CoreToolRegistry",
        ))
    spec, handler = facility_tool_projection(definition)
    return ProjectToolBinding(
        definition=definition,
        registry_owner=context.registry_owner,
        spec=spec,
        handler=handler,
    )


def validate_project_tool_binding(
    definition: FacilityBinding,
    candidate: object,
) -> BindingAccepted[ProjectToolBinding] | BindingRejected:
    if (
        isinstance(candidate, ProjectToolBinding)
        and candidate.definition is definition
        and candidate.registry_owner == PROJECT_TOOL_REGISTRY_OWNER
        and candidate.spec is definition.tool_spec
        and candidate.handler is definition.handler
    ):
        return BindingAccepted(candidate)
    return BindingRejected((
        NativeBindingIssue(
            "$.binding",
            "project tool definition, spec, handler, or registry owner mismatch",
        ),
    ))


PROJECT_TOOL_NATIVE_RULE = NativeContributionRule[
    ProjectToolAuthorSource,
    FacilityBinding,
    ProjectToolAssemblyContext,
    ProjectToolBinding,
](
    lower=lower_project_tool_source,
    project=project_project_tool_definition,
    assemble=assemble_project_tool_definition,
    validate_binding=validate_project_tool_binding,
)


def compile_project_tool_native(
    source: ProjectToolAuthorSource,
) -> NativeContribution[
    FacilityBinding,
    ProjectToolAssemblyContext,
    ProjectToolBinding,
] | Failure:
    return compile_native_contribution(source, PROJECT_TOOL_NATIVE_RULE)


def register_project_tool_contributions(
    registry: ProjectToolRegistry,
    sources: Sequence[ProjectToolAuthorSource],
) -> Failure | None:
    """Compile the whole source catalog before mutating the shared registry."""

    bindings: list[ProjectToolBinding] = []
    seen_binding_ids: set[str] = set()
    seen_tool_names: set[str] = set()
    for index, source in enumerate(sources):
        native = compile_project_tool_native(source)
        if isinstance(native, Failure):
            return native
        binding = native.assemble(ProjectToolAssemblyContext())
        if isinstance(binding, Failure):
            return binding
        if source.binding_id in seen_binding_ids:
            return _invalid((
                f"$.sources[{index}].binding_id",
                f"duplicate project tool binding id: {source.binding_id}",
            ))
        if binding.spec.name in seen_tool_names or registry.get(binding.spec.name) is not None:
            return _invalid((
                f"$.sources[{index}].tool_spec.name",
                f"duplicate project tool name: {binding.spec.name}",
            ))
        seen_binding_ids.add(source.binding_id)
        seen_tool_names.add(binding.spec.name)
        bindings.append(binding)

    for binding in bindings:
        failure = registry.register(binding.spec, binding.handler)
        if isinstance(failure, Failure):
            return failure
    return None


__all__ = [
    "PROJECT_TOOL_NATIVE_RULE",
    "ProjectToolAssemblyContext",
    "ProjectToolAuthorSource",
    "ProjectToolBinding",
    "compile_project_tool_native",
    "register_project_tool_contributions",
]
