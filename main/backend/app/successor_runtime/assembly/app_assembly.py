"""WP-I1-06 successor runtime app-mount dependencies (LOCAL_ONLY default).

This module owns the default app-entry wiring for the bounded v2 successor
runtime router.  The default uses the closed LOCAL_ONLY fixture options from
the I1 successor assembly and never opens a production resolver, live
provider, canonical writer, external delivery, cutover or authority transfer.
The router factory call itself stays in ``app/api/__init__.py`` so this
assembly layer never imports the API package.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from fastapi import Request

from app.successor_runtime.assembly.base import (
    FamilyAssemblyOptions,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.c9_assembly import (
    build_deterministic_facade_closure,
)
from app.successor_runtime.assembly.successor_assembly import (
    build_local_offline_fixture_options,
)
from app.successor_runtime.runtime.facade import SuccessorRuntimeFacade
from app.successor_runtime.runtime.ports import ProjectScopeRef
from app.successor_runtime.substrate.postgres.session import (
    ProjectScopeResolver,
    ProjectScopeValidationError,
    default_project_schema_name,
    validate_project_key,
)

LOCAL_ONLY_MOUNT_ACTOR = "actor:local-only-app-mount"
LOCAL_ONLY_MOUNT_INCARNATION = "incarnation:local-only-app-mount:v1"
LOCAL_ONLY_MOUNT_CONFIGURATION = "local_only_closed_fixture_options"

AUTHORITY_CEILING_CLOSED: Mapping[str, bool] = MappingProxyType(
    {
        "canonical_write": False,
        "live_provider": False,
        "external_delivery": False,
        "cutover": False,
        "authority_transfer": False,
        "candidate_created": False,
    }
)


class LocalOnlyProjectScopeResolver:
    """Deterministic LOCAL_ONLY scope resolver; never reads the registry.

    Every valid project locator maps to one deterministic local-only scope
    identity bound to the assembly's ``local_assembly_scope_digest``.  The
    production ``resolve_expected`` registry path stays closed.
    """

    def __init__(self, *, scope_digest: str | None = None) -> None:
        self._scope_digest = scope_digest or local_assembly_scope_digest()

    def resolve(self, authenticated_project_key: str) -> ProjectScopeRef:
        project_key = validate_project_key(authenticated_project_key)
        return ProjectScopeRef(
            project_key=project_key,
            resolved_schema=default_project_schema_name(project_key),
            project_registry_revision=0,
            incarnation=LOCAL_ONLY_MOUNT_INCARNATION,
            scope_digest=self._scope_digest,
        )

    def resolve_expected(
        self,
        project_key: str,
        registry_revision: int,
        scope_digest: str,
    ) -> ProjectScopeRef:
        raise ProjectScopeValidationError(
            "resolve_expected is the production registry path; "
            "the LOCAL_ONLY app mount keeps it closed"
        )


def _local_only_actor_provider(request: Request) -> str:
    return LOCAL_ONLY_MOUNT_ACTOR


@dataclass(frozen=True, slots=True)
class SuccessorRuntimeAppDependencies:
    """Inspectable default dependencies for the mounted v2 router."""

    resolver: ProjectScopeResolver
    facade: SuccessorRuntimeFacade
    actor_provider: Callable[[Request], str]
    assembly_options: FamilyAssemblyOptions
    configuration: str = LOCAL_ONLY_MOUNT_CONFIGURATION
    authority_ceiling: Mapping[str, bool] = field(
        default_factory=lambda: dict(AUTHORITY_CEILING_CLOSED)
    )
    candidate: None = None


def build_successor_runtime_app_dependencies(
    *,
    options: FamilyAssemblyOptions | None = None,
    scope_digest: str | None = None,
) -> SuccessorRuntimeAppDependencies:
    """Build the default LOCAL_ONLY router dependencies.

    ``options`` defaults to the closed local-only fixture options; the C9
    facade closure from those options is the mounted command/query facade.
    """

    assembly_options = options or build_local_offline_fixture_options()
    facade = assembly_options.c9.facade
    if facade is None:
        facade = build_deterministic_facade_closure()
    if not isinstance(facade, SuccessorRuntimeFacade):
        raise TypeError("assembly options c9.facade must be a SuccessorRuntimeFacade")
    resolver = LocalOnlyProjectScopeResolver(scope_digest=scope_digest)
    return SuccessorRuntimeAppDependencies(
        resolver=resolver,
        facade=facade,
        actor_provider=_local_only_actor_provider,
        assembly_options=assembly_options,
        configuration=LOCAL_ONLY_MOUNT_CONFIGURATION,
        authority_ceiling=dict(AUTHORITY_CEILING_CLOSED),
        candidate=None,
    )


__all__ = [
    "AUTHORITY_CEILING_CLOSED",
    "LOCAL_ONLY_MOUNT_ACTOR",
    "LOCAL_ONLY_MOUNT_CONFIGURATION",
    "LOCAL_ONLY_MOUNT_INCARNATION",
    "LocalOnlyProjectScopeResolver",
    "SuccessorRuntimeAppDependencies",
    "build_successor_runtime_app_dependencies",
]
