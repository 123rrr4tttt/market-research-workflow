"""Production application composition and fail-closed request admission.

This module only composes declarative bindings and normalizes observations for
the pure policy kernel.  It never executes a provider or canonical writer and
never creates an alternative project identity.
"""

# Composition errors are intentionally descriptive at this boundary.
# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, Protocol, runtime_checkable

from fastapi import HTTPException, Request
from starlette.routing import BaseRoute

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


PRODUCTION_ENVIRONMENTS = frozenset({"production", "prod"})
_ROUTE_BINDING_SCHEMA = "mrw.production.route-bindings.v3"
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
    if not isinstance(content, dict) or content.get("schema") != _ROUTE_BINDING_SCHEMA:
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
        if effect_missing or effect_extra:
            raise RouteEffectContractError(
                "route_effect_unclassified",
                "effect contract fields are not explicit",
                details={"missing": sorted(effect_missing), "extra": sorted(effect_extra)},
            )
        try:
            effect_contract = EndpointEffectContract(
                effect_class=effect_raw.get("effect_class"),
                admission=effect_raw.get("admission"),
                provider_port=effect_raw.get("provider_port"),
                provider_class=effect_raw.get("provider_class"),
                canonical_writer_port=effect_raw.get("canonical_writer_port"),
                external_auth_port=effect_raw.get("external_auth_port"),
                filesystem_port=effect_raw.get("filesystem_port"),
                conditional_discriminator=effect_raw.get("conditional_discriminator"),
                conditional_branches=effect_raw.get("conditional_branches"),
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
            metrics_label=raw.get("metrics_label"),
            methods=raw.get("methods", ()),
            required_scope=raw.get("required_scope", "api:invoke"),
            required_approval_ids=raw.get("required_approval_ids", ()),
            requires_provider=effect_contract.requires_provider,
            provider_class=effect_contract.provider_class,
            requires_canonical_writer=effect_contract.requires_canonical_writer,
            approval_required=effect_contract.approval_required,
            capability_id=raw.get("capability_id"),
            canonical_owner_ref=("successor-runtime" if effect_contract.requires_canonical_writer else None),
            writer_port_kind=effect_contract.canonical_writer_port,
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
    """Use the canonical projection request identity for approval observation."""

    if binding.route_template != "/api/v1/material-projections/v2/commands":
        return hashlib.sha256(body).hexdigest()
    try:
        from app.contracts.successor_runtime import SuccessorRuntimeCommandV2DTO
        from app.successor_runtime.runtime.facade_contracts import (
            derive_projection_request_identity,
        )

        dto = SuccessorRuntimeCommandV2DTO.model_validate(json.loads(body))
        return derive_projection_request_identity(
            scope_digest=scope.scope_digest,
            actor_ref=actor_id,
            command_id=dto.command_id,
            command_kind=dto.command_kind,
            payload=dto.payload.model_dump(mode="json"),
            expected_base_token=dto.expected_base_token,
            approval_locator=dto.approval_locator,
        )
    except Exception:
        # DTO validation remains the route handler's responsibility; malformed
        # input keeps the raw digest and fails closed at the approval/effect
        # boundary rather than being treated as an exact authorized request.
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
