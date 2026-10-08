"""Production application composition and fail-closed request admission.

This module only composes declarative bindings and normalizes observations for
the pure policy kernel.  It never executes a provider or canonical writer and
never creates an alternative project identity.
"""

# Composition errors are intentionally descriptive at this boundary.
# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, Protocol, runtime_checkable

from fastapi import HTTPException, Request
from starlette.routing import BaseRoute
from functorial_kit import Failure

from app.production_contract import (
    ApprovalGrant,
    EffectAdmission,
    EffectClass,
    EndpointEffectContract,
    HTTPPolicy,
    OperationPolicy,
    PolicyDecision,
    PolicyOutcome,
    ProviderClass,
    ProductionPolicyConfig,
    ProductionRequest,
    ProjectBinding,
    ProviderPolicy,
    RatePolicy,
    evaluate_production_policy,
    RouteEffectContractError,
)
from app.release_identity import RELEASE_VERSION, read_build_identity
from app.services.request_identity import RequestActorContext, resolve_request_actor_context
from app.successor_runtime.substrate.postgres.session import ProjectScopeResolver
from app.successor_runtime.runtime.ports import ProjectScopeRef
from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine
from app.successor_runtime.language.object_contracts import OperationContract, OperationContractRef
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot, OperationContractRegistry
from app.successor_runtime.substrate.postgres.idempotency import IdempotencyBinding
from app.successor_runtime.language.program import ProgramSpec, program_atoms
from app.successor_runtime.language.transforms import TransformRegistry
from app.successor_runtime.research.object_types import ObjectType
from app.successor_runtime.runtime.activation import ValueEncoder
from app.successor_runtime.language.profiles import EffectProfile, ResourceProfile
from app.successor_runtime.capabilities import (
    acquisition_url, batch_business, batch_task, retrieval_candidate_native,
    retrieval_material_native, workflow_native_contribution,
)
from app.successor_runtime.assembly.installed_operation import InstalledOperationView
from app.services.agent_batch.business_readback import BrokerBusinessReadback, CeleryBrokerBusinessReadback
from app.successor_runtime.runtime.node import RunOnceReport, RuntimeHandler
from app.successor_runtime.runtime.assignments import RuntimeAssignment
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.first_specimen_activation import ActiveChildMaterializer, ActiveChildTerminalObservation, ActivationCatalogEntry, FirstSpecimenActivationCatalog
from app.successor_runtime.substrate.postgres.nodes import DeploymentCatalog
from app.successor_runtime.substrate.postgres.runtime_failures import RuntimeFailureRecord

PRODUCTION_ENVIRONMENTS = frozenset({"production", "prod"})
_ROUTE_BINDING_SCHEMAS = ("mrw.production.route-bindings.v3", "mrw.production.route-bindings.v4")
_ROUTE_BINDING_FILE = Path(__file__).with_name("production_route_bindings.json")
_WILDCARD_VALUES = frozenset({"*", "all", "any"})
_TOKEN_HEADER = "Authorization"
_APPROVAL_HEADER = "X-Approval-Id"


def is_production_environment(settings_obj: Any | None = None) -> bool:
    if settings_obj is None:
        from app.settings.config import settings

        settings_obj = settings
    return str(getattr(settings_obj, "env", "") or "").strip().lower() in PRODUCTION_ENVIRONMENTS


def _csv(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple, set, frozenset)):
        items = value
    else:
        items = str(value or "").split(",")
    return tuple(dict.fromkeys(item.strip() for item in items if str(item).strip()))


def _setting(settings_obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        value = getattr(settings_obj, name, None)
        if value is not None and (not isinstance(value, str) or value.strip()):
            return value
    return default


def _positive(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"production setting {name} must be positive")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"production setting {name} must be positive") from exc
    if parsed <= 0:
        raise RuntimeError(f"production setting {name} must be positive")
    return parsed


def _required_values(settings_obj: Any, *names: str) -> tuple[str, ...]:
    values = _csv(_setting(settings_obj, *names, default=""))
    if not values or any(value.lower() in _WILDCARD_VALUES for value in values):
        raise RuntimeError(f"production setting {names[0]} must be explicit and non-wildcard")
    return values


def _explicit_values(value: Any, name: str) -> tuple[str, ...]:
    values = _csv(value)
    if any(item.lower() in _WILDCARD_VALUES for item in values):
        raise RuntimeError(f"production runtime binding {name} must be explicit and non-wildcard")
    return values


@dataclass(frozen=True, slots=True)
class ProductionEndpointBinding:
    """One checked-in route-to-operation binding.

    Operation identity is data in the registry.  It is never inferred at
    request time from a method, path, or FastAPI route name.
    """

    route_template: str
    domain: str
    operation: str
    metrics_label: str
    methods: tuple[str, ...]
    required_scope: str = "api:invoke"
    required_approval_ids: tuple[str, ...] = ()
    requires_provider: bool = False
    provider_class: ProviderClass = ProviderClass.NULL
    requires_canonical_writer: bool = False
    approval_required: bool = False
    capability_id: str | None = None
    canonical_owner_ref: str | None = None
    writer_port_kind: str | None = None
    effect_contract: EndpointEffectContract | None = None

    def __post_init__(self) -> None:
        # When callers provide the semantic contract directly, derive the
        # compatibility policy flags before validating the legacy projection.
        # Registry loading follows the same path and never stores a second
        # effect truth.
        if isinstance(self.effect_contract, EndpointEffectContract):
            contract = self.effect_contract
            object.__setattr__(self, "requires_provider", contract.requires_provider)
            object.__setattr__(self, "requires_canonical_writer", contract.requires_canonical_writer)
            object.__setattr__(self, "approval_required", contract.approval_required)
            object.__setattr__(self, "provider_class", contract.provider_class)
            if contract.requires_canonical_writer:
                object.__setattr__(self, "canonical_owner_ref", self.canonical_owner_ref or "successor-runtime")
                object.__setattr__(self, "writer_port_kind", contract.canonical_writer_port)
        field_names = ("route_template", "domain", "operation", "metrics_label", "required_scope")
        for field_name in field_names:
            value = str(getattr(self, field_name) or "").strip()
            if not value:
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)
        methods = tuple(dict.fromkeys(str(item).upper() for item in self.methods if str(item).strip()))
        if not methods:
            raise ValueError("methods is required")
        object.__setattr__(self, "methods", methods)
        object.__setattr__(self, "required_approval_ids", _csv(self.required_approval_ids))
        for field_name in (
            "requires_provider",
            "requires_canonical_writer",
            "approval_required",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be bool")
        if not isinstance(self.provider_class, ProviderClass):
            raw_provider_class = str(self.provider_class or "").strip()
            if raw_provider_class not in {item.value for item in ProviderClass}:
                raise ValueError("provider_class must use the closed provider vocabulary")
            object.__setattr__(self, "provider_class", ProviderClass(raw_provider_class))
        if self.requires_provider and self.provider_class is ProviderClass.NULL:
            raise ValueError("requires_provider must declare a non-null provider_class")
        if not self.requires_provider and self.provider_class is not ProviderClass.NULL:
            raise ValueError("provider_class must be null when requires_provider is false")
        high_risk = self.requires_provider or self.requires_canonical_writer
        if self.approval_required != high_risk:
            raise ValueError("approval_required must match provider/writer effect risk")
        if self.approval_required:
            capability_id = str(self.capability_id or "").strip()
            if not capability_id:
                raise ValueError("capability_id is required for approval-required routes")
            object.__setattr__(self, "capability_id", capability_id)
        elif self.capability_id is not None:
            raise ValueError("capability_id must be null when approval is not required")
        if self.requires_canonical_writer:
            required_writer_fields = ("canonical_owner_ref",)
            if not isinstance(self.effect_contract, EndpointEffectContract) or self.effect_contract.admitted:
                required_writer_fields = ("canonical_owner_ref", "writer_port_kind")
            for field_name in required_writer_fields:
                value = str(getattr(self, field_name) or "").strip()
                if not value:
                    raise ValueError(f"{field_name} is required for canonical writer routes")
                object.__setattr__(self, field_name, value)
        elif self.canonical_owner_ref is not None or self.writer_port_kind is not None:
            raise ValueError("canonical writer fields must be null for non-writer routes")

        contract = self.effect_contract
        if contract is None:
            if self.requires_provider:
                effect_class = EffectClass.PROVIDER_CALL
            elif self.requires_canonical_writer:
                effect_class = EffectClass.CANONICAL_WRITE
            else:
                effect_class = EffectClass.READ
            contract = EndpointEffectContract(
                effect_class=effect_class,
                admission=(
                    EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING
                    if self.requires_provider and not self.writer_port_kind
                    else EffectAdmission.ADMITTED
                ),
                provider_class=self.provider_class,
                canonical_writer_port=self.writer_port_kind,
            )
        elif not isinstance(contract, EndpointEffectContract):
            raise RouteEffectContractError(
                "route_effect_unclassified",
                "effect_contract must be an EndpointEffectContract",
            )
        # The effect contract is authoritative for these derived policy flags.
        if self.requires_provider != contract.requires_provider:
            raise RouteEffectContractError(
                "route_effect_mismatch",
                "requires_provider disagrees with effect class",
                details={"operation": self.operation},
            )
        if self.requires_canonical_writer != contract.requires_canonical_writer:
            raise RouteEffectContractError(
                "route_effect_mismatch",
                "requires_canonical_writer disagrees with effect class",
                details={"operation": self.operation},
            )
        if self.provider_class is not contract.provider_class:
            raise RouteEffectContractError(
                "provider_class_mismatch",
                "provider class disagrees with effect contract",
                details={"operation": self.operation},
            )
        if self.approval_required != contract.approval_required:
            raise RouteEffectContractError(
                "route_effect_mismatch",
                "approval_required disagrees with effect contract",
                details={"operation": self.operation},
            )
        if self.requires_canonical_writer and self.writer_port_kind != contract.canonical_writer_port:
            raise RouteEffectContractError(
                "canonical_writer_port_unbound",
                "writer port disagrees with effect contract",
                details={"operation": self.operation},
            )
        object.__setattr__(self, "effect_contract", contract)

    def metric_labels(self, release_version: str = RELEASE_VERSION) -> dict[str, str]:
        return {
            "domain": self.domain,
            "route": self.route_template,
            "release_version": release_version,
        }


@dataclass(frozen=True, slots=True)
class ProductionRouteExemption:
    route_template: str
    methods: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        route_template = str(self.route_template or "").strip()
        reason = str(self.reason or "").strip()
        methods = tuple(dict.fromkeys(str(item).upper() for item in self.methods if str(item).strip()))
        if not route_template or not methods or not reason:
            raise ValueError("route exemption requires route_template, methods, and reason")
        object.__setattr__(self, "route_template", route_template)
        object.__setattr__(self, "methods", methods)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True, slots=True)
class RateObservation:
    request_count: int
    window_seconds: int


@dataclass(frozen=True, slots=True)
class ProviderSelection:
    provider_id: str
    provider_class: ProviderClass = ProviderClass.NULL
    request_payload_bytes: int = 0

    def __post_init__(self) -> None:
        if not str(self.provider_id or "").strip():
            raise ValueError("provider_id is required")
        object.__setattr__(self, "provider_id", str(self.provider_id).strip())
        if not isinstance(self.provider_class, ProviderClass):
            raise TypeError("provider_class must be closed")
        if (
            not isinstance(self.request_payload_bytes, int)
            or isinstance(self.request_payload_bytes, bool)
            or self.request_payload_bytes < 0
        ):
            raise ValueError("provider request_payload_bytes must be a non-negative integer")


@runtime_checkable
class ProductionActorScopesPort(Protocol):
    def scopes(
        self,
        actor: RequestActorContext,
        operation: str,
        capability_id: str,
        scope: ProjectScopeRef,
    ) -> tuple[str, ...]: ...


@runtime_checkable
class ProductionApprovalsPort(Protocol):
    def approvals(
        self,
        actor: RequestActorContext,
        operation: str,
        capability_id: str,
        scope: ProjectScopeRef,
        observed_at: datetime,
        approval_ref: str,
        payload_digest: str,
    ) -> tuple[ApprovalGrant, ...]: ...


@runtime_checkable
class ProductionRateObservationsPort(Protocol):
    def observe_http(self, actor: RequestActorContext, operation: str) -> RateObservation: ...

    def observe_provider(
        self,
        actor: RequestActorContext,
        operation: str,
        provider_id: str,
    ) -> RateObservation: ...


@runtime_checkable
class ProductionProviderCatalogPort(Protocol):
    def allowed_provider_ids(self) -> tuple[str, ...]: ...


@runtime_checkable
class ProductionProviderSelectionPort(Protocol):
    def select(
        self,
        actor: RequestActorContext,
        provider_class: ProviderClass,
        request_payload_bytes: int,
    ) -> ProviderSelection | None: ...


@runtime_checkable
class ProductionCanonicalWriterPort(Protocol):
    def owner(
        self,
        operation: str,
        project_key: str,
        canonical_owner_ref: str,
        writer_port_kind: str,
        approvals: tuple[ApprovalGrant, ...],
    ) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ProductionRuntimeBindings:
    """Explicit read-only authority sources required by production admission."""

    project_scope_resolver: ProjectScopeResolver
    actor_scopes: ProductionActorScopesPort
    approvals: ProductionApprovalsPort
    rate_observations: ProductionRateObservationsPort
    provider_catalog: ProductionProviderCatalogPort
    provider_selection: ProductionProviderSelectionPort
    canonical_writer: ProductionCanonicalWriterPort

    def __post_init__(self) -> None:
        field_names = (
            "project_scope_resolver",
            "actor_scopes",
            "approvals",
            "rate_observations",
            "provider_catalog",
            "provider_selection",
            "canonical_writer",
        )
        for field_name in field_names:
            value = getattr(self, field_name)
            if value is None:
                raise RuntimeError(f"production runtime binding {field_name} is required")


@dataclass(frozen=True, slots=True)
class ProductionComposition:
    policy: ProductionPolicyConfig
    endpoint_bindings: tuple[ProductionEndpointBinding, ...]
    metrics_token: str
    allowed_hosts: tuple[str, ...]
    runtime: ProductionRuntimeBindings

    def binding_for(self, route_template: str, method: str) -> ProductionEndpointBinding | None:
        method = method.upper()
        for binding in self.endpoint_bindings:
            if binding.route_template == route_template and method in binding.methods:
                return binding
        return None


def _route_methods(route: BaseRoute) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(method).upper()
            for method in (getattr(route, "methods", None) or ())
            if str(method).strip()
        )
    )


def _read_registry(path: Path | str) -> dict[str, Any]:
    try:
        content = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RouteEffectContractError(
            "route_effect_unclassified",
            "production route binding registry is unavailable or malformed",
        ) from exc
    if not isinstance(content, dict) or content.get("schema") not in _ROUTE_BINDING_SCHEMAS:
        raise RouteEffectContractError(
            "route_effect_unclassified",
            "production route binding registry schema mismatch",
            details={"schema": content.get("schema") if isinstance(content, dict) else None},
        )
    return content


def load_production_route_exemptions(
    path: Path | str = _ROUTE_BINDING_FILE,
) -> tuple[ProductionRouteExemption, ...]:
    content = _read_registry(path)
    raw_exemptions = content.get("exemptions")
    if not isinstance(raw_exemptions, list):
        raise TypeError("production route exemptions must be a list")
    exemptions: list[ProductionRouteExemption] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_exemptions:
        if not isinstance(raw, dict):
            raise TypeError("production route exemption entries must be objects")
        exemption = ProductionRouteExemption(
            route_template=raw.get("route_template"),
            methods=raw.get("methods", ()),
            reason=raw.get("reason"),
        )
        for method in exemption.methods:
            pair = (exemption.route_template, method)
            if pair in seen:
                raise RuntimeError(f"production route exemption duplicate: {pair[0]} {pair[1]}")
            seen.add(pair)
        exemptions.append(exemption)
    return tuple(exemptions)


def load_production_route_bindings(
    path: Path | str = _ROUTE_BINDING_FILE,
) -> tuple[ProductionEndpointBinding, ...]:
    """Load the checked-in registry without consulting the live route graph."""

    content = _read_registry(path)
    raw_bindings = content.get("bindings")
    if not isinstance(raw_bindings, list) or not raw_bindings:
        raise RuntimeError("production route binding registry has no bindings")
    bindings: list[ProductionEndpointBinding] = []
    seen: set[tuple[str, str]] = set()
    required_fields = {
        "route_template",
        "domain",
        "operation",
        "metrics_label",
        "methods",
        "required_scope",
        "required_approval_ids",
        "capability_id",
        "effect_contract",
    }
    compact = content["schema"] == "mrw.production.route-bindings.v4"
    if compact:
        required_fields.remove("metrics_label")
    effect_required_fields = {
        "effect_class",
        "admission",
        "provider_port",
        "provider_class",
        "canonical_writer_port",
        "external_auth_port",
        "filesystem_port",
        "conditional_discriminator",
        "conditional_branches",
    }
    for raw in raw_bindings:
        if not isinstance(raw, dict):
            raise TypeError("production route binding entries must be objects")
        missing = required_fields - raw.keys()
        extra = raw.keys() - required_fields
        if missing or extra:
            raise RouteEffectContractError(
                "route_effect_unclassified",
                "production route binding fields are not explicit",
                details={"missing": sorted(missing), "extra": sorted(extra)},
            )
        effect_raw = raw.get("effect_contract")
        if not isinstance(effect_raw, dict):
            raise RouteEffectContractError(
                "route_effect_unclassified",
                "effect_contract must be an object",
            )
        effect_missing = effect_required_fields - effect_raw.keys()
        effect_extra = effect_raw.keys() - effect_required_fields
        if not compact and (effect_missing or effect_extra):
            raise RouteEffectContractError(
                "route_effect_unclassified",
                "effect contract fields are not explicit",
                details={"missing": sorted(effect_missing), "extra": sorted(effect_extra)},
            )
        try:
            effect_contract = (
                EndpointEffectContract.from_declaration(effect_raw)
                if compact else EndpointEffectContract(**effect_raw)
            )
        except RouteEffectContractError:
            raise
        except (TypeError, ValueError) as exc:
            raise RouteEffectContractError(
                "route_effect_unclassified",
                "effect contract is malformed",
            ) from exc
        binding = ProductionEndpointBinding(
            route_template=raw.get("route_template"),
            domain=raw.get("domain"),
            operation=raw.get("operation"),
            metrics_label=(
                f"{str(raw['domain'] or '').strip()}:{str(raw['route_template'] or '').strip()}"
                if compact else raw.get("metrics_label")
            ),
            methods=raw.get("methods", ()),
            required_scope=raw["required_scope"],
            required_approval_ids=raw.get("required_approval_ids", ()),
            capability_id=raw.get("capability_id"),
            effect_contract=effect_contract,
        )
        for method in binding.methods:
            pair = (binding.route_template, method)
            if pair in seen:
                raise RuntimeError(f"production route binding duplicate: {pair[0]} {pair[1]}")
            seen.add(pair)
        bindings.append(binding)
    return tuple(bindings)


def production_endpoint_binding_table() -> tuple[ProductionEndpointBinding, ...]:
    return load_production_route_bindings()


def validate_production_route_coverage(
    bindings: tuple[ProductionEndpointBinding, ...],
    routes: Iterable[BaseRoute],
    *,
    exemptions: tuple[ProductionRouteExemption, ...] | None = None,
) -> None:
    """Require an exact checked-in mapping for every installed route/method."""

    checked_exemptions = load_production_route_exemptions() if exemptions is None else exemptions
    registry_pairs = {
        (binding.route_template, method) for binding in bindings for method in binding.methods
    }
    exempt_pairs = {
        (exemption.route_template, method)
        for exemption in checked_exemptions
        for method in exemption.methods
    }
    installed_pairs = {
        (str(getattr(route, "path", "") or ""), method)
        for route in routes
        for method in _route_methods(route)
    }
    overlap = registry_pairs & exempt_pairs
    unregistered = installed_pairs - registry_pairs - exempt_pairs
    stale = (registry_pairs | exempt_pairs) - installed_pairs
    if overlap or unregistered or stale:
        raise RuntimeError(
            "production route graph differs from checked-in route bindings: "
            f"overlap={sorted(overlap)} unregistered={sorted(unregistered)} stale={sorted(stale)}"
        )


def build_production_endpoint_bindings() -> Annotated[
    tuple[ProductionEndpointBinding, ...],
    "kit:non-authoritative derived_as=view "
    "fact_source=app.composition.production_route_bindings.json "
    "witness=test:checked_in_route_registry_exactly_covers_installed_routes",
]:
    """Compatibility alias for loading the explicit registry."""

    return load_production_route_bindings()


def build_production_composition(
    settings_obj: Any | None = None,
    *,
    routes: Iterable[BaseRoute],
    runtime_bindings: ProductionRuntimeBindings,
) -> Annotated[
    ProductionComposition,
    "kit:non-authoritative derived_as=plan "
    "fact_source=settings+routes+runtime_bindings+route_bindings+build_identity "
    "witness=test:production_build_requires_runtime_bindings_and_exact_route_coverage",
]:
    """Build a declarative production composition; never perform an effect."""

    if runtime_bindings is None:
        raise RuntimeError("production runtime bindings are required")
    if not isinstance(runtime_bindings, ProductionRuntimeBindings):
        raise TypeError("production runtime bindings have the wrong type")
    if settings_obj is None:
        from app.settings.config import settings

        settings_obj = settings
    if not is_production_environment(settings_obj):
        raise RuntimeError("production composition requested outside production")
    if bool(_setting(settings_obj, "codex_oauth_enabled", default=True)) and not bool(
        _setting(settings_obj, "codex_oauth_cookie_secure", default=False)
    ):
        raise RuntimeError("production OAuth requires secure session cookies")
    identity = read_build_identity()
    if not identity.fully_bound:
        raise RuntimeError("production startup requires a fully bound build identity")
    service_version = str(os.getenv("SERVICE_VERSION") or "").strip()
    if service_version and service_version != RELEASE_VERSION:
        raise RuntimeError("SERVICE_VERSION must equal release_identity.RELEASE_VERSION")

    allowed_hosts = _required_values(settings_obj, "production_allowed_hosts", "allowed_hosts")
    allowed_origins = _required_values(settings_obj, "production_allowed_origins", "cors_allowed_origins")
    trusted_sources = _required_values(settings_obj, "production_trusted_actor_sources")
    trusted_modes = _required_values(settings_obj, "production_trusted_auth_modes")
    max_body = _positive(
        _setting(settings_obj, "production_max_body_bytes", "production_http_max_body_bytes", default=0),
        "production_max_body_bytes",
    )
    http_max = _positive(
        _setting(settings_obj, "production_http_rate_max_requests", default=0),
        "production_http_rate_max_requests",
    )
    http_window = _positive(
        _setting(settings_obj, "production_http_rate_window_seconds", default=0),
        "production_http_rate_window_seconds",
    )
    provider_max = _positive(
        _setting(settings_obj, "production_provider_rate_max_requests", default=0),
        "production_provider_rate_max_requests",
    )
    provider_window = _positive(
        _setting(settings_obj, "production_provider_rate_window_seconds", default=0),
        "production_provider_rate_window_seconds",
    )
    provider_payload = _positive(
        _setting(settings_obj, "production_provider_max_payload_bytes", default=0),
        "production_provider_max_payload_bytes",
    )

    try:
        provider_ids = _explicit_values(
            runtime_bindings.provider_catalog.allowed_provider_ids(), "provider_catalog"
        )
    except Exception as exc:
        raise RuntimeError("production runtime authority ports are unavailable") from exc

    bindings = load_production_route_bindings()
    writer_refs = {
        binding.canonical_owner_ref for binding in bindings if binding.canonical_owner_ref is not None
    }
    writer_ports = {
        binding.writer_port_kind for binding in bindings if binding.writer_port_kind is not None
    }
    if writer_refs and writer_refs != {"successor-runtime"}:
        raise RuntimeError("production canonical writer route bindings are not exact")
    if writer_ports and writer_ports != {"postgres.projection_rebuild.v2"}:
        raise RuntimeError("production canonical writer route bindings are not exact")
    declared_writer_owner = str(
        _setting(settings_obj, "production_canonical_writer_owner", default="") or ""
    ).strip()
    declared_writer_binding = str(
        _setting(settings_obj, "production_canonical_writer_binding", default="") or ""
    ).strip()
    if declared_writer_owner and (
        not writer_refs or declared_writer_owner != next(iter(writer_refs))
    ):
        raise RuntimeError("production canonical writer owner deployment assertion differs")
    if declared_writer_binding and (
        not writer_ports or declared_writer_binding != next(iter(writer_ports))
    ):
        raise RuntimeError("production canonical writer binding deployment assertion differs")
    route_tuple = tuple(routes)
    validate_production_route_coverage(bindings, route_tuple)
    operations: dict[str, OperationPolicy] = {}
    for binding in bindings:
        operation_policy = OperationPolicy(
            required_scope=binding.required_scope,
            required_approval_ids=binding.required_approval_ids,
            requires_provider=binding.requires_provider,
            requires_canonical_writer=binding.requires_canonical_writer,
            provider_class=binding.provider_class,
            approval_required=binding.approval_required,
            capability_id=binding.capability_id or "",
            canonical_owner_ref=binding.canonical_owner_ref,
            writer_port_kind=binding.writer_port_kind,
            effect_admission=binding.effect_contract.admission,
        )
        existing = operations.get(binding.operation)
        if existing is not None and existing != operation_policy:
            raise RuntimeError(f"production operation has conflicting policies: {binding.operation}")
        operations[binding.operation] = operation_policy

    token = str(_setting(settings_obj, "production_metrics_token", "metrics_token", default="") or "").strip()
    if not token or token.lower() in _WILDCARD_VALUES:
        raise RuntimeError("production_metrics_token must be explicit and non-wildcard")
    policy = ProductionPolicyConfig(
        trusted_actor_sources=trusted_sources,
        trusted_auth_modes=trusted_modes,
        transport=HTTPPolicy(
            require_tls=bool(_setting(settings_obj, "production_require_tls", default=True)),
            allowed_origins=allowed_origins,
            allowed_methods=_required_values(settings_obj, "production_allowed_methods"),
            allowed_content_types=_required_values(settings_obj, "production_allowed_content_types"),
            max_body_bytes=max_body,
        ),
        http_rate=RatePolicy(max_requests=http_max, window_seconds=http_window),
        provider=ProviderPolicy(
            allowed_provider_ids=provider_ids,
            max_requests=provider_max,
            window_seconds=provider_window,
            max_payload_bytes=provider_payload,
        ),
        operations=operations,
        projects=MappingProxyType({}),
    )
    return ProductionComposition(policy, bindings, token, allowed_hosts, runtime_bindings)


def _composition_for_request(request: Request) -> ProductionComposition:
    runtime = getattr(request.app.state, "production_runtime_bindings", None)
    if not isinstance(runtime, ProductionRuntimeBindings):
        raise HTTPException(
            status_code=503,
            detail={
                "message": "production runtime bindings are unavailable",
                "reason_code": "composition_unavailable",
            },
        )
    return build_production_composition(routes=request.app.routes, runtime_bindings=runtime)


def _route_project_key(request: Request) -> str | None:
    params = getattr(request, "path_params", {}) or {}
    for key in ("project_key", "project", "projectId"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _payload_project_key(body: bytes, content_type: str | None) -> str | None:
    if not body or (content_type is not None and content_type != "application/json"):
        return None
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail={"message": "JSON payload is malformed", "reason_code": "json_payload_invalid"},
        ) from exc
    if isinstance(payload, dict):
        value = payload.get("project_key") or payload.get("projectKey")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _operation_payload_digest(
    binding: ProductionEndpointBinding,
    body: bytes,
    *,
    scope: ProjectScopeRef,
    actor_id: str,
) -> str:
    """Hash the exact request body observed by production admission."""

    del binding, scope, actor_id
    return hashlib.sha256(body).hexdigest()


def _host_matches(host: str, allowed: tuple[str, ...]) -> bool:
    host = host.split(":", 1)[0].strip().lower().strip("[]")
    return host in {item.lower().split(":", 1)[0].strip().strip("[]") for item in allowed}


def _project_binding(runtime: ProductionRuntimeBindings, project_key: str) -> ProjectBinding:
    try:
        scope = runtime.project_scope_resolver.resolve(project_key)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "project scope is unavailable",
                "reason_code": "project_scope_unavailable",
            },
        ) from exc
    if not isinstance(scope, ProjectScopeRef) or scope.project_key != project_key:
        raise HTTPException(
            status_code=503,
            detail={"message": "project scope binding is invalid", "reason_code": "project_scope_invalid"},
        )
    return ProjectBinding(project_key=project_key, scope=scope)


async def require_production_policy(request: Request) -> PolicyDecision | None:
    """FastAPI dependency used as the sole production API deny gate."""

    from app.production_observability import (
        CanaryRouteAction,
        ProductionObservabilityController,
    )

    controller = getattr(request.app.state, "production_observability_r7", None)
    if isinstance(controller, ProductionObservabilityController):
        try:
            rollback_latched = controller.route_advice.action is CanaryRouteAction.ROLLBACK
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "production observability route advice is unavailable",
                    "reason_code": "observability_unavailable",
                },
            ) from exc
        if rollback_latched:
            raise HTTPException(
                status_code=403,
                detail={
                    "message": "production observability rollback is latched",
                    "reason_code": "observability_rollback_latched",
                },
            )

    if not is_production_environment():
        return None
    composition = _composition_for_request(request)
    route = str(getattr(request.scope.get("route"), "path", "") or "")
    binding = composition.binding_for(route, request.method)
    if binding is None:
        raise HTTPException(status_code=404, detail={"message": "route is not registered in production binding"})
    effect_contract = binding.effect_contract
    if effect_contract is None:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "production effect route is not admitted",
                "reason_code": "public_effect_route_unadmitted",
            },
        )
    if not effect_contract.admitted:
        # This check intentionally precedes body buffering, Redis windows and
        # authority reads.  A route without an admitted effect binding cannot
        # observe or execute any downstream effect.
        raise HTTPException(
            status_code=403,
            detail={
                "message": "production effect route is not admitted",
                "reason_code": "public_effect_route_unadmitted",
                "effect_class": effect_contract.effect_class.value,
                "admission": effect_contract.admission.value,
            },
        )
    if not _host_matches(request.headers.get("host", ""), composition.allowed_hosts):
        raise HTTPException(
            status_code=403,
            detail={"message": "host is not allowed", "reason_code": "host_denied"},
        )
    if request.query_params.get("project_key"):
        raise HTTPException(
            status_code=403,
            detail={"message": "query project is not allowed", "reason_code": "project_query_denied"},
        )

    route_project = _route_project_key(request)
    header_project = (request.headers.get("X-Project-Key") or "").strip() or None
    explicit_project = route_project or header_project
    body = await request.body()
    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower() or None
    payload_project = _payload_project_key(body, content_type)
    if payload_project is None:
        payload_project = explicit_project
    if explicit_project is None or payload_project is None:
        raise HTTPException(
            status_code=403,
            detail={"message": "production project key is required", "reason_code": "project_missing"},
        )

    runtime = composition.runtime
    binding_project = _project_binding(runtime, explicit_project)
    actor = resolve_request_actor_context(request)
    observed_at = datetime.now(UTC)
    payload_digest = _operation_payload_digest(
        binding,
        body,
        scope=binding_project.scope,
        actor_id=actor.actor_id,
    )
    approval_ref = (request.headers.get(_APPROVAL_HEADER) or "").strip()
    try:
        actor_scopes = _csv(
            runtime.actor_scopes.scopes(
                actor,
                binding.operation,
                binding.capability_id or "",
                binding_project.scope,
            )
        )
        approvals = tuple(
            runtime.approvals.approvals(
                actor,
                binding.operation,
                binding.capability_id or "",
                binding_project.scope,
                observed_at,
                approval_ref,
                payload_digest,
            )
        ) if binding.approval_required else ()
        http_rate = runtime.rate_observations.observe_http(actor, binding.operation)
        selection = (
            runtime.provider_selection.select(
                actor,
                binding.provider_class,
                len(body),
            )
            if binding.requires_provider
            else None
        )
        if selection is not None and not isinstance(selection, ProviderSelection):
            raise RuntimeError("provider selection has invalid type")  # noqa: TRY301
        provider_rate = (
            runtime.rate_observations.observe_provider(actor, binding.operation, selection.provider_id)
            if selection is not None
            else RateObservation(0, 60)
        )
        writer_owner = (
            runtime.canonical_writer.owner(
                binding.operation,
                binding_project.project_key,
                binding.canonical_owner_ref or "",
                binding.writer_port_kind or "",
                approvals,
            )
            if binding.requires_canonical_writer
            else None
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "production authority observations are unavailable",
                "reason_code": "authority_observation_unavailable",
            },
        ) from exc

    request_config = replace(
        composition.policy,
        projects=MappingProxyType({binding_project.project_key: binding_project}),
    )
    request_obj = ProductionRequest(
        operation=binding.operation,
        actor=actor,
        actor_scopes=actor_scopes,
        approvals=approvals,
        observed_at=observed_at,
        route_project_key=explicit_project,
        payload_project_key=payload_project,
        scheme=request.url.scheme,
        origin=request.headers.get("origin"),
        method=request.method,
        body_size=len(body),
        content_type=content_type,
        http_request_count=http_rate.request_count,
        http_window_seconds=http_rate.window_seconds,
        provider_id=selection.provider_id if selection is not None else None,
        provider_class=selection.provider_class if selection is not None else ProviderClass.NULL,
        provider_request_payload_bytes=(
            selection.request_payload_bytes if selection is not None else 0
        ),
        provider_request_count=provider_rate.request_count,
        provider_window_seconds=provider_rate.window_seconds,
        canonical_writer_owner=writer_owner,
        canonical_owner_ref=binding.canonical_owner_ref,
        writer_port_kind=binding.writer_port_kind,
        payload_digest=payload_digest,
    )
    decision = evaluate_production_policy(request_config, request_obj)
    if decision.outcome is not PolicyOutcome.PASS:
        failure = decision.failure
        raise HTTPException(
            status_code=403,
            detail={
                "message": "production policy denied request",
                "reason_code": failure.code if failure else "policy_denied",
                "stage": decision.stage,
                "details": dict(decision.details),
            },
        )
    return decision


def production_metrics_label(request: Request) -> dict[str, str]:
    """Return low-cardinality labels; production composition failures stay closed."""

    route = str(getattr(request.scope.get("route"), "path", "unknown"))
    if not is_production_environment():
        return {"domain": "unknown", "route": route, "release_version": RELEASE_VERSION}
    composition = _composition_for_request(request)
    if any(
        exemption.route_template == route and request.method.upper() in exemption.methods
        for exemption in load_production_route_exemptions()
    ):
        return {"domain": "exempt", "route": route, "release_version": RELEASE_VERSION}
    binding = composition.binding_for(route, request.method)
    if binding is None:
        raise HTTPException(status_code=404, detail={"message": "route is not registered in production binding"})
    return binding.metric_labels()


def require_observability_token(request: Request, token: str) -> None:
    """Protect metrics/deep health with an independent bearer token."""

    if not is_production_environment():
        return
    import secrets

    supplied = (request.headers.get(_TOKEN_HEADER) or "").strip()
    if supplied.lower().startswith("bearer "):
        supplied = supplied[7:].strip()
    query_token = request.query_params.get("token")
    if query_token or not supplied or not secrets.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail={"message": "observability bearer token required"})


def build_operation_activation(
    connection: Connection, scope: RuntimeScope, *, contract: OperationContract,
    interpreter_profile_digest: str, authority_requirement_digest: str,
    resource_profile: ResourceProfile, effect_profile: EffectProfile,
    deployment: DeploymentCatalog | None = None,
) -> Annotated[tuple[FirstSpecimenActivationCatalog, DeploymentCatalog], 'kit:authoritative-write canonical_writer=DeploymentCatalogRepository witness=test:test_post_waits_for_real_business_outputs_in_input_order']:
    """Bind installed dispatch code to the project's existing resource policy.

    This registers immutable deployment metadata; grants, claim ownership and
    capacity remain controlled by their existing PostgreSQL authorities.
    """
    from app.successor_runtime.runtime.assignments import InterpreterBinding, RecoveryBinding, canonical_digest
    from app.successor_runtime.runtime.resources import QueueEligibility, ResourceClass
    from app.successor_runtime.language.transforms import TransformRegistry
    from app.successor_runtime.substrate.postgres.first_specimen_activation import ActivationCatalogEntry
    from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
    from app.successor_runtime.substrate.postgres.nodes import DeploymentCatalogRepository

    if effect_profile.ref != contract.effect_profile_ref:
        raise ValueError("installed operation effect profile differs from its contract")
    if resource_profile.ref != contract.resource_profile_ref or len(resource_profile.resource_classes) != 1:
        raise ValueError("installed operation requires one exact declared resource class")
    resource_class = ResourceClass(resource_profile.resource_classes[0])
    policies = PUBLIC_TABLES["runtime_resource_policies"]
    policy = connection.execute(select(policies).where(
        policies.c.project_key == scope.project_scope.project_key,
        policies.c.capability_id == contract.owner_capability_id,
        policies.c.resource_class == resource_class.value,
    ).order_by(policies.c.policy_epoch.desc()).limit(1)).mappings().one()
    protocol = "mrw.runtime.protocol.v1"
    if deployment is None:
        node_profile = canonical_digest({
            "schema": "mrw.installed-operation-node.v2", "contract": contract.ref.contract_digest,
            "value_codec_realization": "mrw.installed-value-codecs.v1",
            "runtime_protocol": protocol,
        })
        deployment = DeploymentCatalog(
            catalog_digest=canonical_digest({"node_profile": node_profile, "contract": contract.ref.contract_digest,
                                             "project_scope": scope.project_scope.scope_digest}),
            catalog_version="2", catalog_ref=f"installed:{contract.ref.kind}",
            node_profile_digest=node_profile,
            security_profile_digest=contract.authority_profile_ref.profile_digest,
            resource_profile_digest=contract.resource_profile_ref.profile_digest,
        )
    DeploymentCatalogRepository(connection).put_exact(deployment)
    binding = InterpreterBinding.from_content(
        operation_contract_digest=contract.ref.contract_digest,
        interpreter_profile_digest=interpreter_profile_digest,
        deployment_catalog_digest=deployment.catalog_digest,
        runtime_protocol_version=protocol, project_scope_digest=scope.project_scope.scope_digest,
        resource_policy_epoch=int(policy["policy_epoch"]),
        authority_requirement_digest=authority_requirement_digest,
    )
    eligibility = QueueEligibility(
        project_key=scope.project_scope.project_key, capability_id=contract.owner_capability_id,
        resource_class=resource_class, units=resource_profile.units,
        policy_epoch=int(policy["policy_epoch"]), policy_digest=str(policy["policy_digest"]),
    )
    return FirstSpecimenActivationCatalog(
        entries=(ActivationCatalogEntry(
            operation_contract_digest=contract.ref.contract_digest, interpreter_binding=binding,
            recovery_binding=RecoveryBinding.from_content(
                recovery_handler_id=f"{contract.ref.kind}.readback", recovery_handler_version="1",
                interpreter_profile_digest=binding.interpreter_profile_digest,
                authoritative_readback_profile_ref=contract.observation_profile_ref.profile_id,
            ), queue_eligibility=eligibility, required_node_profile_selector=deployment.node_profile_digest,
            resource_policy_digest=eligibility.policy_digest,
            fairness_key=scope.project_scope.project_key, effect_class=effect_profile.execution_class,
            external_gate_required=effect_profile.human_approval_required,
        ),), transform_registry=TransformRegistry(), merge_registry=TransformRegistry(),
        discriminator_registry=TransformRegistry(),
        encode_value=_installed_value_encoder((contract,), TransformRegistry(), TransformRegistry()),
    ), deployment



def _installed_operation_facts(
    ref: OperationContractRef,
) -> tuple[OperationContract, ResourceProfile, EffectProfile, str, str]:
    """Resolve original declarations; caller data cannot install executable code."""
    from app.successor_runtime.assembly.installed_operation import (
        installed_operation_catalog,
        installed_operation_for_ref,
    )

    installed = installed_operation_for_ref(installed_operation_catalog, ref)
    if installed is None:
        raise ValueError(f"operation is not installed: {ref.kind}")
    definition = installed.definition
    contract = definition.contract
    return (
        contract,
        definition.profiles.resource,
        definition.profiles.effect,
        definition.interpreter_profile_digest,
        definition.authority_requirement_digest,
    )


def _installed_value_encoder(
    contracts: tuple[OperationContract, ...],
    transforms: TransformRegistry,
    merges: TransformRegistry,
) -> ValueEncoder:
    """Interpret only native endpoint declarations with their existing codecs."""
    from app.successor_runtime.capabilities.checksum import canonical_json
    from app.successor_runtime.capabilities.retrieval_candidate_native import RETRIEVAL_CANDIDATE_ATTEMPT_SEQUENCE_TYPE
    from app.successor_runtime.language.checksum import canonical_bytes
    from app.successor_runtime.language.program import _tuple_object_type, sequence_object_type

    endpoints = {endpoint for contract in contracts for endpoint in (contract.input_type, contract.output_type)}
    for ref in transforms.transform_refs():
        entry = transforms.resolve_transform(ref)
        endpoints.update((entry.input_type, entry.output_type))
    structural = {RETRIEVAL_CANDIDATE_ATTEMPT_SEQUENCE_TYPE}
    for ref in merges.merge_refs():
        merge = merges.resolve_merge(ref)
        endpoints.update((merge.left_type, merge.right_type, merge.output_type))
        structural.add(_tuple_object_type((merge.left_type, merge.right_type)))
    structural.update(sequence_object_type(endpoint, version=version)
                      for endpoint in endpoints for version in ("1", "2"))
    structural.intersection_update(endpoints)

    def encode(object_type: ObjectType, value: object) -> bytes:
        if object_type not in endpoints:
            raise ValueError("value codec has no exact installed endpoint declaration")
        return canonical_bytes(value) if object_type in structural else canonical_json(value).encode("utf-8")

    return encode


def build_program_activation(
    connection: Connection, scope: RuntimeScope, program: ProgramSpec,
) -> Annotated[tuple[FirstSpecimenActivationCatalog, DeploymentCatalog], 'kit:authoritative-write canonical_writer=DeploymentCatalogRepository witness=test:test_post_waits_for_real_business_outputs_in_input_order']:
    """Assemble every exact operation of a Program into one Node deployment."""
    from app.successor_runtime.capabilities.batch_task_program import build_ordered_dispatch_merge_registry
    from app.successor_runtime.capabilities.retrieval_candidate_native import (
        RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND,
    )
    from app.successor_runtime.capabilities.retrieval_material_native import RETRIEVAL_LEAF_KINDS
    from app.successor_runtime.language.transforms import TransformRegistry
    from app.successor_runtime.runtime.assignments import canonical_digest

    refs = tuple(sorted({atom.operation.contract_ref for atom in program_atoms(program.root)},
                        key=lambda ref: (ref.kind, ref.contract_version, ref.contract_digest)))
    if not refs:
        raise ValueError("installed Program requires operation declarations")
    facts = tuple(_installed_operation_facts(ref) for ref in refs)
    deployment = None
    if len(facts) > 1:
        contracts = tuple(fact[0] for fact in facts)
        digests = tuple(contract.ref.contract_digest for contract in contracts)
        node_profile = canonical_digest({
            "schema": "mrw.installed-program-node.v2", "contracts": digests,
            "value_codec_realization": "mrw.installed-value-codecs.v1",
            "runtime_protocol": "mrw.runtime.protocol.v1",
        })
        deployment = DeploymentCatalog(
            catalog_digest=canonical_digest({"node_profile": node_profile, "contracts": digests,
                                             "project_scope": scope.project_scope.scope_digest}),
            catalog_version="2", catalog_ref=f"installed-program:{node_profile}",
            node_profile_digest=node_profile,
            security_profile_digest=canonical_digest(tuple(asdict(c.authority_profile_ref) for c in contracts)),
            resource_profile_digest=canonical_digest(tuple(asdict(c.resource_profile_ref) for c in contracts)),
        )
    entries: list[ActivationCatalogEntry] = []
    for contract, resource, effect, interpreter, authority in facts:
        catalog, deployment = build_operation_activation(
            connection, scope, contract=contract, interpreter_profile_digest=interpreter,
            authority_requirement_digest=authority, resource_profile=resource, effect_profile=effect, deployment=deployment,
        )
        entries.extend(catalog.entries)
    assert deployment is not None
    merges = build_ordered_dispatch_merge_registry()
    transforms = TransformRegistry()
    discriminators = TransformRegistry()
    if any(ref.kind in (RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND, *RETRIEVAL_LEAF_KINDS) for ref in refs):
        from app.services.project_retrieval.execution import (
            build_retrieval_transform_registry, build_retrieval_merge_registry,
            build_retrieval_discriminator_registry,
        )
        transforms = build_retrieval_transform_registry()
        discriminators = build_retrieval_discriminator_registry()
        retrieval_merges = build_retrieval_merge_registry()
        for ref in retrieval_merges.merge_refs():
            entry = retrieval_merges.resolve_merge(ref)
            installed = merges.register_merge(
                name=entry.id, version=entry.version, left_type=entry.left_type,
                right_type=entry.right_type, output_type=entry.output_type, func=entry.callable,
            )
            if installed != ref:
                raise ValueError("installed retrieval merge differs from its native declaration")
    return FirstSpecimenActivationCatalog(
        entries=tuple(entries), transform_registry=transforms,
        merge_registry=merges, discriminator_registry=discriminators,
        encode_value=_installed_value_encoder(
            tuple(fact[0] for fact in facts), transforms, merges,
        ),
    ), deployment


def submit_installed_program(
    *, engine: Engine, project_key: str, actor_id: str, program: ProgramSpec,
    operation_catalog: OperationContractCatalogSnapshot,
    operation_contracts: OperationContractRegistry,
    values: tuple[tuple[ValueRef, bytes], ...],
    idempotency_id: str, identity_capability_id: str, logical_request_id: str,
    identity_operation_kind: str, run_id: str, incarnation: str,
    canonical_bindings: Mapping[str, tuple[int, str]],
    approvals_by_step: Mapping[str, tuple[str, ...]], trace_id: str,
    now: datetime, queue: str,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Submit exact declarations through the existing authority and runtime owners."""
    from app.services.tasks import task_successor_runtime
    from app.successor_runtime.substrate.postgres.authority import AuthorityGrantRepository
    from app.successor_runtime.substrate.postgres.authority_provider import CurrentAuthorityGrantUnavailable
    from app.successor_runtime.substrate.postgres.first_specimen_activation import (
        ActivationTrigger, compiled_submission_request_digest, submit_compiled_program,
    )
    from app.successor_runtime.substrate.postgres.runtime_journal import ExactBindingConflict, RuntimeJournalRepository
    from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver

    with engine.begin() as connection:
        project = ServerProjectScopeResolver(connection=connection).resolve(project_key)
        if (program.project_key, program.project_registry_revision, program.project_scope_digest) != (
            project.project_key, project.project_registry_revision, project.scope_digest,
        ):
            raise ExactBindingConflict("submission Program project scope is stale")
        scope = RuntimeScope(project_scope=project, actor_id=actor_id)
        idempotency = IdempotencyBinding(
            idempotency_id=idempotency_id,
            capability_id=identity_capability_id,
            logical_request_id=logical_request_id,
            operation_kind=identity_operation_kind,
            run_id=run_id,
            request_digest=compiled_submission_request_digest(
                program, scope, canonical_bindings, approvals_by_step,
            ),
        )
        contracts = tuple(_installed_operation_facts(atom.operation.contract_ref)[0]
                          for atom in program_atoms(program.root))
        for capability in {contract.owner_capability_id for contract in contracts}:
            if not AuthorityGrantRepository(connection, scope).current_for(
                actor_id=actor_id, capability_id=capability, at=now,
            ):
                raise CurrentAuthorityGrantUnavailable("no current authority grant")
        activation, _ = build_program_activation(connection, scope, program)
        submit_compiled_program(
            connection, scope, program=program, operation_catalog=operation_catalog,
            operation_contracts=operation_contracts, activation_catalog=activation,
            values=values, idempotency=idempotency, incarnation=incarnation,
            canonical_bindings=canonical_bindings, approvals_by_step=approvals_by_step,
            trigger=ActivationTrigger(now, trace_id, now),
        )
        run = dict(RuntimeJournalRepository(connection, scope).load_run(idempotency.run_id))
        work_ids = tuple(work_id for work_id, due_at in _ready_run_work(
            connection, project_key=project_key, run_id=idempotency.run_id,
        ) if due_at <= now)
    for work_id in work_ids:
        task_successor_runtime.apply_async(args=(work_id,), queue=queue)
    return run, work_ids


def read_installed_program(
    *, engine: Engine, project_key: str, actor_id: str, run_id: str,
) -> tuple[Mapping[str, object], tuple[Mapping[str, object], ...], tuple[Mapping[str, object], ...]]:
    """Read canonical run facts for an actor authorized by the existing API boundary."""
    from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
    from app.successor_runtime.substrate.postgres.runtime_journal import RuntimeJournalRepository
    from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver
    from app.successor_runtime.substrate.postgres.plans import PlanRepository
    from app.successor_runtime.substrate.postgres.models import project_tables
    from sqlalchemy import MetaData

    with engine.connect() as connection:
        project = ServerProjectScopeResolver(connection=connection).resolve(project_key)
        scope = RuntimeScope(project_scope=project, actor_id=actor_id)
        journal = RuntimeJournalRepository(connection, scope)
        run = dict(journal.load_run(run_id))
        steps = PUBLIC_TABLES["runtime_steps"]
        rows = {str(row["step_id"]): dict(row) for row in connection.execute(select(steps).where(
            steps.c.project_key == project_key, steps.c.run_id == run_id,
        )).mappings()}
        plan = PlanRepository(connection, project_tables(MetaData(), project.resolved_schema)).get(scope, str(run["plan_digest"]))
        ordered = tuple(rows[step.step_id] for step in plan.ordered_steps if step.step_id in rows)
        return run, ordered, tuple(dict(event) for event in journal.load_events(run_id))


def read_installed_program_outputs(
    *, engine: Engine, project_key: str, actor_id: str, run_id: str,
) -> tuple[tuple[str, ValueRef, bytes], ...]:
    """Read exact successful step bytes for an API-authorized project viewer."""
    from sqlalchemy import MetaData
    from app.successor_runtime.substrate.postgres.first_specimen_activation import (
        load_runtime_observations, PostgresFirstSpecimenActivationBindingAdapter,
    )
    from app.successor_runtime.substrate.postgres.models import project_tables
    from app.successor_runtime.substrate.postgres.plans import PlanRepository
    from app.successor_runtime.substrate.postgres.runtime_journal import ExactBindingConflict, RuntimeJournalRepository
    from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver

    with engine.connect() as connection:
        project = ServerProjectScopeResolver(connection=connection).resolve(project_key)
        scope = RuntimeScope(project_scope=project, actor_id=actor_id)
        run = RuntimeJournalRepository(connection, scope).load_run(run_id)
        tables = project_tables(MetaData(), project.resolved_schema)
        if run["resolved_schema"] != project.resolved_schema:
            raise ExactBindingConflict("runtime output project schema drift")
        plan = PlanRepository(connection, tables).get(scope, str(run["plan_digest"]))
        if (plan.plan_id != run["plan_id"] or plan.program_id != run["program_id"]
                or plan.program_digest != run["program_digest"]):
            raise ExactBindingConflict("runtime output Run/Plan identity drift")
        observed, _ = load_runtime_observations(connection, scope, tables, run, plan, lock=False)
        by_step = {item.step_id: item.value_ref for item in observed}
        reader = PostgresFirstSpecimenActivationBindingAdapter()
        return tuple((step.step_id, by_step[step.step_id], reader.read_value_bytes(
            connection, scope, tables, by_step[step.step_id],
        )) for step in plan.ordered_steps if step.step_id in by_step)


def read_installed_program_failures(
    *, engine: Engine, project_key: str, actor_id: str, run_id: str,
) -> tuple[tuple[int, RuntimeFailureRecord], ...]:
    """Read only exact EffectFailed bodies for an API-authorized project viewer."""
    from sqlalchemy import MetaData
    from app.successor_runtime.runtime.assignments import InterpreterBinding
    from app.successor_runtime.runtime.claims import ClaimBinding
    from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES, project_tables
    from app.successor_runtime.substrate.postgres.plans import PlanRepository
    from app.successor_runtime.substrate.postgres.runtime_failures import RuntimeFailureRepository
    from app.successor_runtime.substrate.postgres.runtime_journal import (
        ExactBindingConflict, RuntimeJournalRepository, validate_runtime_assignment_row,
    )
    from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver

    with engine.connect() as connection:
        project = ServerProjectScopeResolver(connection=connection).resolve(project_key)
        scope = RuntimeScope(project_scope=project, actor_id=actor_id)
        journal = RuntimeJournalRepository(connection, scope)
        run = journal.load_run(run_id)
        tables = project_tables(MetaData(), project.resolved_schema)
        plan = PlanRepository(connection, tables).get(scope, str(run["plan_digest"]))
        if (run["resolved_schema"] != project.resolved_schema
                or run["project_registry_revision"] != project.project_registry_revision
                or run["project_scope_digest"] != project.scope_digest or plan.plan_id != run["plan_id"]
                or plan.plan_digest != run["plan_digest"]
                or plan.program_id != run["program_id"] or plan.program_digest != run["program_digest"]):
            raise ExactBindingConflict("runtime failure Run/Plan/project identity drift")
        records: list[tuple[int, RuntimeFailureRecord]] = []
        seen: set[tuple[str, str]] = set()
        for event in journal.load_events(run_id):
            if event["event_type"] != "EffectFailed":
                continue
            step_id, attempt_id = str(event.get("step_id") or ""), str(event.get("attempt_id") or "")
            metadata = event.get("event_metadata_json")
            work_item_id = metadata.get("work_item_id") if isinstance(metadata, dict) else None
            if (not step_id or not attempt_id or not isinstance(work_item_id, str) or not work_item_id
                    or (step_id, attempt_id) in seen or event["schema_version"] != "mrw.runtime.event.effect_failed.v1"
                    or event["project_key"] != project_key or event["run_id"] != run_id):
                raise ExactBindingConflict("EffectFailed identity/schema is absent or duplicated")
            seen.add((step_id, attempt_id))
            attempts, work_items, steps = (PUBLIC_TABLES[name] for name in (
                "runtime_effect_attempts", "runtime_work_items", "runtime_steps",
            ))
            attempt = connection.execute(select(attempts).where(
                attempts.c.project_key == project_key, attempts.c.attempt_id == attempt_id,
            )).mappings().one_or_none()
            work = connection.execute(select(work_items).where(
                work_items.c.project_key == project_key, work_items.c.work_item_id == work_item_id,
            )).mappings().one_or_none()
            step = connection.execute(select(steps).where(
                steps.c.project_key == project_key, steps.c.run_id == run_id, steps.c.step_id == step_id,
            )).mappings().one_or_none()
            plan_steps = tuple(item for item in plan.ordered_steps if item.step_id == step_id)
            if attempt is None or work is None or step is None or len(plan_steps) != 1:
                raise ExactBindingConflict("EffectFailed exact attempt/work/step is absent")
            assignment = validate_runtime_assignment_row(work)
            claim = ClaimBinding.model_validate(attempt["claim_binding_json"])
            claim.validate_against(assignment)
            contract = plan_steps[0].operation_contract_ref
            if (assignment.work_item_id != work_item_id or assignment.run_id != run_id or assignment.step_id != step_id
                    or assignment.program_digest != run["program_digest"] or assignment.plan_digest != run["plan_digest"]
                    or assignment.execution_epoch != run["execution_epoch"] or assignment.incarnation != run["incarnation"]
                    or attempt["run_id"] != run_id or attempt["step_id"] != step_id or attempt["attempt_id"] != attempt_id
                    or attempt["incarnation"] != run["incarnation"] or attempt["execution_epoch"] != run["execution_epoch"]
                    or attempt["assignment_digest"] != assignment.assignment_digest
                    or attempt["handler_binding_digest"] != assignment.handler_binding_digest
                    or attempt["handler_realization_digest"] != assignment.handler_binding_digest
                    or attempt["claim_binding_digest"] != claim.binding_digest or claim.attempt_id != attempt_id
                    or attempt["authorization_digest"] != claim.authorization_digest
                    or work["authority_digest"] != claim.authorization_digest
                    or work["claim_attempt_id"] != claim.attempt_id or work["claim_binding_digest"] != claim.binding_digest
                    or work["claim_binding_json"] != claim.model_dump(mode="json")
                    or (isinstance(assignment.handler_binding, InterpreterBinding)
                        and assignment.handler_binding.project_scope_digest != project.scope_digest)
                    or event["authority_digest"] != claim.authorization_digest or attempt["disposition"] != "FAILED"
                    or step["operation_id"] != plan_steps[0].operation_id
                    or step["execution_epoch"] != run["execution_epoch"] or attempt["input_digest"] != step["input_digest"]
                    or contract is None or assignment.operation_contract_ref != contract
                    or step["operation_kind"] != contract.kind or step["operation_version"] != contract.contract_version):
                raise ExactBindingConflict("EffectFailed run/plan/attempt/claim/handler binding drift")
            failure_ref, failure_digest = attempt["failure_ref"], attempt["failure_digest"]
            if ((event.get("payload_ref"), event.get("payload_digest")) not in ((None, None), (failure_ref, failure_digest))
                    or metadata.get("failure_ref", failure_ref) != failure_ref
                    or metadata.get("failure_digest", failure_digest) != failure_digest):
                raise ExactBindingConflict("EffectFailed failure reference/digest drift")
            record = RuntimeFailureRepository(connection, tables).verify_exact(
                scope, assignment=assignment, claim=claim, failure_ref=failure_ref, failure_digest=failure_digest,
            )
            records.append((int(event["seq"]), record))
        return tuple(records)


def read_installed_program_input_bindings(
    *, engine: Engine, project_key: str, actor_id: str, run_id: str,
    static_input_type: ObjectType,
) -> tuple[
    tuple[tuple[ValueRef, bytes], ...],
    tuple[tuple[str, str, ValueRef, bytes], ...],
]:
    """Read exact static and started semantic inputs without execution effects."""
    from sqlalchemy import MetaData
    from app.successor_runtime.substrate.postgres.first_specimen_activation import (
        PostgresFirstSpecimenActivationBindingAdapter,
    )
    from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES, project_tables
    from app.successor_runtime.substrate.postgres.plans import PlanRepository
    from app.successor_runtime.substrate.postgres.programs import ProgramRepository
    from app.successor_runtime.substrate.postgres.runtime_journal import (
        ExactBindingConflict,
        RuntimeJournalRepository,
        validate_runtime_assignment_row,
    )
    from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver

    with engine.connect() as connection:
        project = ServerProjectScopeResolver(connection=connection).resolve(project_key)
        scope = RuntimeScope(project_scope=project, actor_id=actor_id)
        journal = RuntimeJournalRepository(connection, scope)
        run = journal.load_run(run_id)
        tables = project_tables(MetaData(), project.resolved_schema)
        if run["resolved_schema"] != project.resolved_schema:
            raise ExactBindingConflict("runtime input project schema drift")
        plan = PlanRepository(connection, tables).get(scope, str(run["plan_digest"]))
        program = ProgramRepository(connection, tables).get(
            scope, str(run["program_id"]), expected_digest=str(run["program_digest"]),
        )
        if (plan.plan_id != run["plan_id"] or plan.program_id != run["program_id"]
                or plan.program_digest != run["program_digest"]
                or program.program_digest != run["program_digest"]):
            raise ExactBindingConflict("runtime input Run/Program/Plan identity drift")

        reader = PostgresFirstSpecimenActivationBindingAdapter()
        static_refs = tuple(dict.fromkeys(
            ref
            for atom in program_atoms(program.root)
            for ref in atom.operation.input_refs
            if ref.object_type == static_input_type
        ))
        static_bindings = tuple(
            (ref, reader.read_value_bytes(connection, scope, tables, ref))
            for ref in static_refs
        )

        attempts_table = PUBLIC_TABLES["runtime_effect_attempts"]
        steps_table = PUBLIC_TABLES["runtime_steps"]
        work_table = PUBLIC_TABLES["runtime_work_items"]
        started_bindings: list[tuple[str, str, ValueRef, bytes]] = []
        seen_started: set[tuple[str, str]] = set()
        for event in journal.load_events(run_id):
            if event["event_type"] != "EffectStarted":
                continue
            step_id = str(event.get("step_id") or "")
            attempt_id = str(event.get("attempt_id") or "")
            identity = (step_id, attempt_id)
            if not step_id or not attempt_id or identity in seen_started:
                raise ExactBindingConflict("EffectStarted identity is absent or duplicated")
            seen_started.add(identity)
            if event["schema_version"] != "mrw.runtime.event.effect_started.v1":
                raise ExactBindingConflict("EffectStarted schema version drift")
            metadata = event.get("event_metadata_json")
            work_item_id = metadata.get("work_item_id") if isinstance(metadata, dict) else None
            if not isinstance(work_item_id, str) or not work_item_id:
                raise ExactBindingConflict("EffectStarted lacks its exact work identity")

            attempts = connection.execute(select(attempts_table).where(
                attempts_table.c.project_key == project_key,
                attempts_table.c.attempt_id == attempt_id,
            )).mappings().all()
            if len(attempts) != 1:
                raise ExactBindingConflict("EffectStarted attempt is absent or ambiguous")
            attempt = attempts[0]
            assignment_digest = str(attempt["assignment_digest"])
            work_rows = connection.execute(select(work_table).where(
                work_table.c.project_key == project_key,
                work_table.c.assignment_digest == assignment_digest,
            )).mappings().all()
            if len(work_rows) != 1:
                raise ExactBindingConflict("EffectStarted assignment digest is absent or ambiguous")
            work = work_rows[0]
            assignment = validate_runtime_assignment_row(work)
            plan_steps = tuple(item for item in plan.ordered_steps if item.step_id == step_id)
            if len(plan_steps) != 1:
                raise ExactBindingConflict("EffectStarted step is absent from exact Plan")
            plan_step = plan_steps[0]
            runtime_steps = connection.execute(select(steps_table).where(
                steps_table.c.project_key == project_key,
                steps_table.c.run_id == run_id,
                steps_table.c.step_id == step_id,
            )).mappings().all()
            if len(runtime_steps) != 1:
                raise ExactBindingConflict("EffectStarted runtime step is absent or ambiguous")
            runtime_step = runtime_steps[0]
            if (
                assignment.work_item_id != work_item_id
                or assignment.run_id != run_id
                or assignment.step_id != step_id
                or assignment.program_digest != run["program_digest"]
                or assignment.plan_digest != run["plan_digest"]
                or int(assignment.execution_epoch) != int(run["execution_epoch"])
                or assignment.incarnation != run["incarnation"]
                or attempt["run_id"] != run_id
                or attempt["step_id"] != step_id
                or int(attempt["execution_epoch"]) != int(run["execution_epoch"])
                or attempt["incarnation"] != run["incarnation"]
                or attempt["assignment_digest"] != work["assignment_digest"]
                or attempt["handler_binding_digest"] != work["handler_binding_digest"]
                or attempt["handler_realization_digest"] != work["handler_binding_digest"]
                or attempt["authorization_digest"] != event["authority_digest"]
                or attempt["authorization_digest"] != work["authority_digest"]
                or attempt["input_digest"] != runtime_step["input_digest"]
                or runtime_step["operation_id"] != plan_step.operation_id
                or int(runtime_step["execution_epoch"]) != int(run["execution_epoch"])
                or (plan_step.operation_contract_ref is None
                    or runtime_step["operation_kind"] != plan_step.operation_contract_ref.kind
                    or runtime_step["operation_version"] != plan_step.operation_contract_ref.contract_version
                    or assignment.operation_contract_digest != plan_step.operation_contract_ref.contract_digest)
            ):
                raise ExactBindingConflict("EffectStarted run/step/attempt binding drift")

            descriptor = reader.load_exact(connection, assignment, scope, tables)
            input_ref = reader.semantic_input_ref(
                connection, assignment, scope, tables, descriptor,
            )
            started_bindings.append((
                step_id, attempt_id, input_ref,
                reader.read_value_bytes(connection, scope, tables, input_ref),
            ))
        return static_bindings, tuple(started_bindings)


def _ready_run_work(
    connection: Connection, *, project_key: str, run_id: str,
) -> tuple[tuple[str, datetime], ...]:
    from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
    work, runs = PUBLIC_TABLES["runtime_work_items"], PUBLIC_TABLES["runtime_runs"]
    return tuple((str(row.work_item_id), row.due_at) for row in connection.execute(
        select(work.c.work_item_id, work.c.due_at).join(runs,
            (runs.c.project_key == work.c.project_key) & (runs.c.run_id == work.c.run_id),
        ).where(
            work.c.project_key == project_key, work.c.run_id == run_id,
            work.c.state == "READY", runs.c.cancellation_requested.is_(False),
        ).order_by(work.c.enqueue_seq)
    ))


def successor_ready_work(engine: Engine, source_work_item_id: str) -> tuple[tuple[str, datetime], ...]:
    """Read canonical frontier and due times; transport only delivers these facts."""
    from app.successor_runtime.substrate.postgres.first_specimen_activation import read_linked_runtime_frontier
    with engine.connect() as connection:
        frontier = read_linked_runtime_frontier(connection, source_work_item_id=source_work_item_id)
        return tuple((work.work_item_id, work.due_at) for work in frontier.ready_work)


def successor_ready_work_ids(engine: Engine, source_work_item_id: str) -> tuple[str, ...]:
    now = datetime.now(UTC)
    return tuple(work_id for work_id, due_at in successor_ready_work(engine, source_work_item_id) if due_at <= now)


def dispatch_batch_item(payload: batch_task.BatchTaskSingleDispatchPayload) -> batch_task.BatchTaskSingleDispatchAck:
    """Use the existing declared skill invocation and its single-item kernel."""
    from app.services.agent_batch.routing import resolve_queue_for_lane
    from app.services.agent_batch.task_contract import build_agent_batch_dispatch_invocation
    from app.services.skill_runtime import invoke_skill
    from dataclasses import asdict

    queue = resolve_queue_for_lane(payload.lane)
    declared = build_agent_batch_dispatch_invocation(payload.item.channel, {
        **asdict(payload.item), "project_key": payload.project_key,
        "task_id": batch_task.derive_dispatch_task_id(
            project_scope_digest=payload.scope_digest, capability_id=payload.capability_id,
            dispatch_id=payload.dispatch_id,
        ),
        "lane": payload.lane, "queue": queue, "trace_id": payload.trace_id,
        "workflow_run_id": payload.workflow_run_id, "runtime_readback": dict(payload.runtime_readback),
    }, trace_id=payload.trace_id)
    invocation = invoke_skill(skill_id=str(declared["skill_id"]), payload=declared["payload"], context=declared["context"])
    match invocation["result"]:
        case {"task_id": str(task_id)} if task_id:
            pass
        case _:
            raise RuntimeError("DISPATCH_CELERY_ACK_MISSING")
    return batch_task.BatchTaskSingleDispatchAck(
        schema_version=batch_task.DISPATCH_SINGLE_ACK_SCHEMA,
        operation_kind=batch_task.DISPATCH_SINGLE_KIND,
        dispatch_id=payload.dispatch_id, channel=payload.item.channel,
        celery_task_id=task_id, lane=payload.lane, queue=queue,
        trace_id=payload.trace_id, workflow_run_id=payload.workflow_run_id,
        runtime_readback=payload.runtime_readback,
    )


def _assemble_workflow_operation(  # pyright: ignore[reportUnusedFunction]
    operation: workflow_native_contribution.WorkflowRuntimeOperationDefinition,
    engine: Engine, scope: RuntimeScope, entry: ActivationCatalogEntry,
) -> RuntimeHandler:
    from app.services.projects.context import bind_resolved_project
    from app.services.workflow_graph.runtime import WorkflowNodeSettledFailure, invoke_workflow_runtime_node
    from app.successor_runtime.assembly.workflow_assembly import assemble_workflow_runtime_handler
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory
    return assemble_workflow_runtime_handler(
        operation=operation, uow_factory=runtime_uow_factory(engine), binding=entry.interpreter_binding,
        project_key=scope.project_scope.project_key, resolved_schema=scope.project_scope.resolved_schema,
        bind_project_scope=bind_resolved_project, invoke_runtime_node=invoke_workflow_runtime_node,
        settled_failure_type=WorkflowNodeSettledFailure,
    )


def _assemble_candidate_operation(  # pyright: ignore[reportUnusedFunction]
    operation: retrieval_candidate_native.CandidateRuntimeDefinition,
    engine: Engine, scope: RuntimeScope, entry: ActivationCatalogEntry,
) -> RuntimeHandler:
    from app.services.projects.context import bind_resolved_project
    from app.services.search.candidate_search import discover_candidates
    from app.successor_runtime.capabilities.retrieval_candidate_native import complete_retrieval_candidate_attempt
    from app.successor_runtime.substrate.postgres.batch_task_submission_handler import PersistentOperationHandler
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory
    def check_scope(invocation: retrieval_candidate_native.RetrievalCandidateInvocation,
                    project: ProjectScopeRef, _capability_id: str) -> None:
        if invocation.request.project_ref is not None and invocation.request.project_ref != project.project_key:
            raise ValueError("candidate request crosses the installed project scope")
    def discover(invocation: retrieval_candidate_native.RetrievalCandidateInvocation
                 ) -> retrieval_candidate_native.RetrievalCandidateAttemptOutcome:
        with bind_resolved_project(scope.project_scope.project_key, scope.project_scope.resolved_schema):
            return complete_retrieval_candidate_attempt(invocation, discover_candidates(invocation.request))
    return PersistentOperationHandler(
        uow_factory=runtime_uow_factory(engine), binding=entry.interpreter_binding,
        contract=operation.operation_contract, input_codec=operation.invocation_codec,
        output_codec=operation.output_codec, invoke=discover, validate_input=check_scope,
        validate_bound_inputs=operation.validate_bound_inputs,
    )


def _assemble_retrieval_work_leaf_operation(  # pyright: ignore[reportUnusedFunction]
    operation: InstalledOperationView[
        retrieval_material_native.RetrievalLeafDefinition[retrieval_material_native.CandidateWork],
        retrieval_material_native.CandidateWork, retrieval_material_native.CandidateWork,
    ], engine: Engine, scope: RuntimeScope, entry: ActivationCatalogEntry,
) -> RuntimeHandler:
    from app.services.project_retrieval.execution import (
        build_retrieval_leaf_invocations, build_retrieval_runtime_journal_reader,
        validate_retrieval_work_bound_inputs, review_candidate_work,
    )
    from app.services.project_retrieval.service import ProjectRetrievalService
    from app.services.project_retrieval.topology import build_topology_service
    from app.services.projects.context import bind_resolved_project
    from app.successor_runtime.substrate.postgres.batch_task_submission_handler import PersistentOperationHandler
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory
    work_invocations, _ = build_retrieval_leaf_invocations(
        topology_service=build_topology_service(),
        plan_loader=ProjectRetrievalService().read_plan,
        journal_reader=build_retrieval_runtime_journal_reader(engine=engine, actor_id=scope.actor_id),
    )

    def check_retrieval_scope(
        payload: retrieval_material_native.CandidateWork,
        project: ProjectScopeRef, capability_id: str,
    ) -> None:
        if payload.project_key != project.project_key or capability_id != operation.contract.owner_capability_id:
            raise ValueError("retrieval payload crosses installed project or capability")

    def invoke_retrieval(
        payload: retrieval_material_native.CandidateWork,
    ) -> retrieval_material_native.CandidateWork:
        if operation.contract.ref.kind == retrieval_material_native.RETRIEVAL_CANDIDATE_REVIEW_KIND:
            raise ValueError("review requires its exact assignment prefix")
        with bind_resolved_project(scope.project_scope.project_key, scope.project_scope.resolved_schema):
            return work_invocations[operation.contract.ref.kind](payload)

    def invoke_review(
        payload: retrieval_material_native.CandidateWork, assignment: RuntimeAssignment,
    ) -> retrieval_material_native.CandidateWork:
        from app.successor_runtime.substrate.postgres.first_specimen_activation import read_ordered_prior_effect_outputs
        with runtime_uow_factory(engine)() as uow:
            current_bytes, prior = read_ordered_prior_effect_outputs(uow.connection, scope, assignment)
        codec = operation.input_codec
        current = codec.decode_payload(json.loads(current_bytes))
        if current != payload or payload.candidate_ordinal != len(prior) + 1:
            raise ValueError("review current ordered invocation drift")
        approved = 0
        for position, (before_bytes, after_bytes) in enumerate(prior, 1):
            before = codec.decode_payload(json.loads(before_bytes))
            after = codec.decode_payload(json.loads(after_bytes))
            retrieval_material_native.validate_candidate_work_transition(before, after)
            if (before.candidate_ordinal != position or before.stage != "candidate"
                    or after.stage != "reviewed" or after.review is None
                    or (before.project_key, before.root_run_id, before.retrieval_budget_id,
                        before.plan_id, before.mode_version, before.route_id,
                        before.material_budget_remaining)
                    != (payload.project_key, payload.root_run_id, payload.retrieval_budget_id,
                        payload.plan_id, payload.mode_version, payload.route_id,
                        payload.material_budget_remaining)):
                raise ValueError("review prior ordered output identity drift")
            approved += after.disposition == "approved"
        with bind_resolved_project(scope.project_scope.project_key, scope.project_scope.resolved_schema):
            return review_candidate_work(payload, approved_prefix_count=approved)

    return PersistentOperationHandler(
        uow_factory=runtime_uow_factory(engine), binding=entry.interpreter_binding,
        contract=operation.contract, input_codec=operation.input_codec, output_codec=operation.output_codec,
        invoke=invoke_retrieval, validate_input=check_retrieval_scope,
        invoke_with_assignment=(invoke_review if operation.contract.ref.kind
                                == retrieval_material_native.RETRIEVAL_CANDIDATE_REVIEW_KIND else None),
        validate_bound_inputs=validate_retrieval_work_bound_inputs, bound_payload_source="semantic",
    )


def _assemble_retrieval_control_leaf_operation(  # pyright: ignore[reportUnusedFunction]
    operation: InstalledOperationView[
        retrieval_material_native.RetrievalLeafDefinition[retrieval_material_native.RetrievalControl],
        retrieval_material_native.RetrievalControl, retrieval_material_native.RetrievalControl,
    ], engine: Engine, scope: RuntimeScope, entry: ActivationCatalogEntry,
) -> RuntimeHandler:
    from app.services.project_retrieval.execution import (
        build_retrieval_leaf_invocations, build_retrieval_runtime_journal_reader,
        validate_retrieval_work_bound_inputs,
    )
    from app.services.project_retrieval.service import ProjectRetrievalService
    from app.services.project_retrieval.topology import build_topology_service
    from app.services.projects.context import bind_resolved_project
    from app.successor_runtime.substrate.postgres.batch_task_submission_handler import PersistentOperationHandler
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory
    _, control_invocations = build_retrieval_leaf_invocations(
        topology_service=build_topology_service(), plan_loader=ProjectRetrievalService().read_plan,
        journal_reader=build_retrieval_runtime_journal_reader(engine=engine, actor_id=scope.actor_id),
    )

    def invoke(payload: retrieval_material_native.RetrievalControl) -> retrieval_material_native.RetrievalControl:
        with bind_resolved_project(scope.project_scope.project_key, scope.project_scope.resolved_schema):
            return control_invocations[operation.contract.ref.kind](payload)

    def check_scope(
        payload: retrieval_material_native.RetrievalControl,
        project: ProjectScopeRef, capability_id: str,
    ) -> None:
        if payload.project_key != project.project_key or capability_id != operation.contract.owner_capability_id:
            raise ValueError("retrieval payload crosses installed project or capability")

    return PersistentOperationHandler(
        uow_factory=runtime_uow_factory(engine), binding=entry.interpreter_binding,
        contract=operation.contract, input_codec=operation.input_codec, output_codec=operation.output_codec,
        invoke=invoke, validate_input=check_scope,
        validate_bound_inputs=validate_retrieval_work_bound_inputs, bound_payload_source="semantic",
    )


def _assemble_url_operation(  # pyright: ignore[reportUnusedFunction]
    operation: InstalledOperationView[OperationContract, acquisition_url.UrlSingleUrlRequest,
                                      acquisition_url.UrlSingleUrlOutcome],
    engine: Engine, scope: RuntimeScope, entry: ActivationCatalogEntry,
) -> RuntimeHandler:
    from app.services.ingest.url_pool import invoke_url_single_url, validate_url_single_url_input
    from app.services.projects.context import bind_resolved_project
    from app.successor_runtime.runtime.node import DefiniteInterpreterFailure, OutcomeUncertain
    from app.successor_runtime.substrate.postgres.batch_task_submission_handler import PersistentOperationHandler
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory
    def check_bindings(request: acquisition_url.UrlSingleUrlRequest,
                       bound_inputs: tuple[tuple[ValueRef, bytes], ...]) -> None:
        if len(bound_inputs) != 1:
            from app.services.project_retrieval.execution import validate_retrieval_url_bound_inputs
            validate_retrieval_url_bound_inputs(request, bound_inputs)
    def invoke(request: acquisition_url.UrlSingleUrlRequest) -> acquisition_url.UrlSingleUrlOutcome:
        with bind_resolved_project(scope.project_scope.project_key, scope.project_scope.resolved_schema):
            result = invoke_url_single_url(request)
        if result.status == "failed":
            raise DefiniteInterpreterFailure("URL_POOL_EXECUTION_FAILED")
        if result.status != "completed":
            raise OutcomeUncertain("URL_POOL_TERMINAL_READBACK_REQUIRED")
        return result
    return PersistentOperationHandler(
        uow_factory=runtime_uow_factory(engine), binding=entry.interpreter_binding,
        contract=operation.contract, input_codec=operation.input_codec, output_codec=operation.output_codec,
        invoke=invoke, validate_input=validate_url_single_url_input,
        validate_bound_inputs=check_bindings, bound_payload_source="semantic",
    )


def _assemble_wait_operation(  # pyright: ignore[reportUnusedFunction]
    operation: InstalledOperationView[OperationContract, batch_business.BusinessWaitInput,
                                      batch_business.BatchBusinessResult],
    engine: Engine, _scope: RuntimeScope, entry: ActivationCatalogEntry, broker: BrokerBusinessReadback,
) -> RuntimeHandler:
    from app.services.agent_batch.business_readback import build_batch_business_wait_invoke
    from app.successor_runtime.substrate.postgres.first_specimen_reconciliation_handler import BatchBusinessWaitHandler
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory
    return BatchBusinessWaitHandler(
        uow_factory=runtime_uow_factory(engine), binding=entry.interpreter_binding,
        contract=operation.contract, input_codec=operation.input_codec, output_codec=operation.output_codec,
        invoke=build_batch_business_wait_invoke(broker),
    )


def _assemble_dispatch_operation(  # pyright: ignore[reportUnusedFunction]
    operation: InstalledOperationView[OperationContract, batch_task.BatchTaskSingleDispatchPayload,
                                      batch_task.BatchTaskSingleDispatchAck],
    engine: Engine, _scope: RuntimeScope, entry: ActivationCatalogEntry,
    dispatch: Callable[[batch_task.BatchTaskSingleDispatchPayload], batch_task.BatchTaskSingleDispatchAck],
) -> RuntimeHandler:
    from app.successor_runtime.substrate.postgres.batch_task_submission_handler import BatchTaskSingleDispatchHandler
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory
    return BatchTaskSingleDispatchHandler(
        uow_factory=runtime_uow_factory(engine), binding=entry.interpreter_binding,
        contract=operation.contract, input_codec=operation.input_codec, output_codec=operation.output_codec,
        dispatch=dispatch,
    )


def _installed_operation_handler(
    *, engine: Engine, scope: RuntimeScope, contract: OperationContract,
    entry: ActivationCatalogEntry,
    dispatch: Callable[[batch_task.BatchTaskSingleDispatchPayload], batch_task.BatchTaskSingleDispatchAck],
    broker: BrokerBusinessReadback,
) -> RuntimeHandler:
    from app.successor_runtime.assembly.installed_operation import (
        installed_operation_catalog, installed_operation_for_ref,
    )
    installed = installed_operation_for_ref(installed_operation_catalog, contract.ref)
    if installed is None:
        raise ValueError(f"operation handler is not installed: {contract.ref.kind}")
    result = installed.assemble((engine, scope, entry, dispatch, broker))
    if isinstance(result, Failure):
        raise RuntimeError(f"installed operation binding failed: {result.message}")
    return result

def _retrieval_active_child_materializer(catalog: FirstSpecimenActivationCatalog) -> ActiveChildMaterializer:
    from app.services.project_retrieval.execution import RetrievalWorkActiveChildMaterializer
    return RetrievalWorkActiveChildMaterializer(
        catalog, active_child_materializer_factory=_retrieval_active_child_materializer,
        child_activation_catalog_factory=lambda connection, scope, program: build_program_activation(connection, scope, program)[0],
    )


def _settle_retrieval_children(observations: tuple[ActiveChildTerminalObservation, ...]) -> bytes | None:
    from app.services.project_retrieval.execution import build_retrieval_work_active_child_bytes
    return build_retrieval_work_active_child_bytes(observations)


def execute_successor_work_item(
    *, engine: Engine, work_item_id: str, node_id: str,
    dispatch: Callable[[batch_task.BatchTaskSingleDispatchPayload], batch_task.BatchTaskSingleDispatchAck] = dispatch_batch_item,
    business_readback: BrokerBusinessReadback | None = None,
) -> RunOnceReport:
    """Wake the existing RuntimeNode from a persisted assignment identity."""
    from app.successor_runtime.capabilities.retrieval_candidate_native import (
        RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND,
    )
    from app.successor_runtime.capabilities.acquisition_url import URL_SINGLE_URL_KIND
    from app.successor_runtime.capabilities.retrieval_material_native import RETRIEVAL_LEAF_KINDS
    from app.successor_runtime.runtime.assignments import AssignmentKind
    from app.successor_runtime.runtime.node import DeploymentBinding, NodeIdentity, RuntimeNodeProfile, RuntimeNodeProtocol
    from app.successor_runtime.runtime.ports import ControlPlaneScope, RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION
    from app.successor_runtime.substrate.postgres.composition_root import compose_postgres_first_specimen_runtime
    from app.successor_runtime.substrate.postgres.first_specimen_activation import PostgresFirstSpecimenActivationPort
    from app.successor_runtime.substrate.postgres.first_specimen_terminal import PostgresFirstSpecimenTerminalHook
    from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory
    from app.successor_runtime.substrate.postgres.nodes import RuntimeNodeRepository
    from app.successor_runtime.substrate.postgres.runtime_journal import ExactBindingConflict, validate_runtime_assignment_row
    from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver

    now = datetime.now(UTC)
    with engine.begin() as connection:
        work = PUBLIC_TABLES["runtime_work_items"]
        row = connection.execute(select(work).where(work.c.work_item_id == work_item_id)).mappings().one()
        assignment = validate_runtime_assignment_row({str(key): value for key, value in row.items()})
        scope = RuntimeScope(
            project_scope=ServerProjectScopeResolver(connection=connection).resolve(assignment.project_key),
            actor_id=node_id,
        )
        from sqlalchemy import MetaData
        from app.successor_runtime.substrate.postgres.models import project_tables
        from app.successor_runtime.substrate.postgres.programs import ProgramRepository
        if assignment.operation_contract_ref is None:
            raise ExactBindingConflict("worker assignment has no installed operation")
        run = connection.execute(select(PUBLIC_TABLES["runtime_runs"]).where(
            PUBLIC_TABLES["runtime_runs"].c.project_key == assignment.project_key,
            PUBLIC_TABLES["runtime_runs"].c.run_id == assignment.run_id,
        )).mappings().one()
        program = ProgramRepository(connection, project_tables(MetaData(), scope.project_scope.resolved_schema)).get(
            scope, str(run["program_id"]), expected_digest=assignment.program_digest,
        )
        from app.successor_runtime.substrate.postgres.qualification_store import QualificationStoreRepository
        if assignment.step_id is None:
            raise ExactBindingConflict("worker assignment lacks its qualified step")
        authority = QualificationStoreRepository(connection, scope).load_step_binding(assignment.run_id, assignment.step_id)
        handler_scope = RuntimeScope(project_scope=scope.project_scope, actor_id=authority.actor_id)
        catalog, deployment = build_program_activation(connection, scope, program)
        entry = catalog.entry_for(assignment.operation_contract_ref.contract_digest)
        expected_binding = (entry.recovery_binding if assignment.assignment_kind is AssignmentKind.RECONCILE
                            else entry.interpreter_binding)
        if assignment.handler_binding != expected_binding:
            raise ExactBindingConflict("worker assignment differs from installed code")
        RuntimeNodeRepository(connection).register(
            node_id=node_id, node_profile_digest=deployment.node_profile_digest,
            deployment_catalog_digest=deployment.catalog_digest,
            runtime_protocol_version=assignment.runtime_protocol_version, started_at=now,
        )
    broker = business_readback or CeleryBrokerBusinessReadback()
    handlers = tuple(_installed_operation_handler(
        engine=engine, scope=handler_scope, contract=_installed_operation_facts(atom_ref)[0],
        entry=catalog.entry_for(atom_ref.contract_digest), dispatch=dispatch, broker=broker,
    ) for atom_ref in sorted({atom.operation.contract_ref for atom in program_atoms(program.root)},
                             key=lambda ref: (ref.kind, ref.contract_version, ref.contract_digest)))
    from app.successor_runtime.capabilities import batch_business
    from app.successor_runtime.substrate.postgres.first_specimen_reconciliation_handler import (
        BatchBusinessBrokerReadbackFacade, InstalledBatchTaskBusinessReadbackHandler,
        PostgresBatchTaskBusinessReadbackHandler,
    )
    wait_contract = batch_business.build_batch_business_wait_contract()
    for installed_entry in catalog.entries:
        if installed_entry.operation_contract_digest == wait_contract.ref.contract_digest:
            handlers += (PostgresBatchTaskBusinessReadbackHandler(
                InstalledBatchTaskBusinessReadbackHandler(installed_entry.recovery_binding,
                                                         wait_contract.ref.contract_digest),
                runtime_uow_factory(engine),
                readback=BatchBusinessBrokerReadbackFacade(operation_contract_ref=wait_contract.ref, broker=broker),
            ),)
    runtime = compose_postgres_first_specimen_runtime(
        engine=engine, identity=NodeIdentity(node_id, node_id, now),
        profile=RuntimeNodeProfile(deployment.node_profile_digest, frozenset({AssignmentKind.INTERPRET, AssignmentKind.RECONCILE}),
                                   frozenset(item.interpreter_binding.interpreter_profile_digest for item in catalog.entries)),
        deployment=DeploymentBinding(deployment.catalog_digest, deployment.node_profile_digest,
                                     assignment.runtime_protocol_version),
        protocol=RuntimeNodeProtocol(assignment.runtime_protocol_version),
        control_scope=ControlPlaneScope(node_id, RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
                                       assignment.claim_authority_epoch),
        installations=(), additional_handlers=handlers,
        terminal_hook=PostgresFirstSpecimenTerminalHook(
            activation=PostgresFirstSpecimenActivationPort(
                catalog,
                active_child_materializer_factory=_retrieval_active_child_materializer,
                active_child_settlement=(_settle_retrieval_children if any(
                    atom.operation.contract_ref.kind in {RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND, URL_SINGLE_URL_KIND, *RETRIEVAL_LEAF_KINDS}
                    for atom in program_atoms(program.root)
                ) else None),
                parent_activation_catalog_factory=lambda connection, parent_scope, parent_program: build_program_activation(
                    connection, parent_scope, parent_program,
                )[0],
            ),
        ),
    )
    return runtime.node.run_once()


def validate_production_startup(
    settings_obj: Any | None = None,
    *,
    routes: Iterable[BaseRoute],
    runtime_bindings: ProductionRuntimeBindings,
) -> ProductionComposition:
    return build_production_composition(settings_obj, routes=routes, runtime_bindings=runtime_bindings)


__all__ = [
    "ProductionComposition",
    "ProductionEndpointBinding",
    "ProductionRateObservationsPort",
    "ProductionRuntimeBindings",
    "build_production_composition",
    "build_production_endpoint_bindings",
    "load_production_route_bindings",
    "production_endpoint_binding_table",
    "is_production_environment",
    "production_metrics_label",
    "require_observability_token",
    "require_production_policy",
    "validate_production_route_coverage",
    "validate_production_startup",
]
