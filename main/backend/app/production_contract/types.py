"""Immutable value types for the pure production policy kernel.

The decision is a preflight observation.  It never grants authority, even
when every policy predicate passes; an outer effect owner must separately
possess and enforce live authority.
"""

# ruff: noqa: TRY003
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, Literal, Protocol

from app.successor_runtime.runtime.ports import ProjectScopeRef
from functorial_kit import Failure, define_failure_family, derived

PRODUCTION_POLICY_SCHEMA: Final[str] = "mrw.production-policy.request.v1"
HTTP_POLICY_SCHEMA: Final[str] = "mrw.production-policy.http.v1"
PRODUCTION_POLICY_AUTHORITY_SCHEMA: Final[str] = "mrw.production-policy.authority.v1"
PRODUCTION_POLICY_FAILURE_FAMILY: Final[str] = "mrw.production-policy.failure.v1"
APPROVED_DECISION: Final[str] = "APPROVED"


class PolicyOutcome(StrEnum):
    """Outcome classes are disjoint; PASS never implies authority."""

    PASS = "PASS"
    DOMAIN_REJECTION = "DOMAIN_REJECTION"
    CLASSIFIED_RUNTIME_FAILURE = "CLASSIFIED_RUNTIME_FAILURE"
    UNCLASSIFIED_DEFECT = "UNCLASSIFIED_DEFECT"


class ProviderClass(StrEnum):
    """Closed provider capability classes used by route bindings."""

    LLM = "llm"
    CRAWLER = "crawler"
    NULL = "null"


class EffectClass(StrEnum):
    """Closed route effect vocabulary.

    This is deliberately independent of HTTP methods: the method is transport
    metadata while the effect describes the handler's semantic boundary.
    """

    READ = "read"
    PURE_COMPUTE = "pure_compute"
    PROVIDER_CALL = "provider_call"
    LEGACY_WRITE = "legacy_write"
    CANONICAL_WRITE = "canonical_write"
    EXTERNAL_AUTH = "external_auth"
    FILESYSTEM_SUBPROCESS = "filesystem_subprocess"
    CONDITIONAL = "conditional"


class EffectAdmission(StrEnum):
    """Whether a route effect is admitted by the production contract."""

    ADMITTED = "admitted"
    BLOCKED_UNTIL_EFFECT_BINDING = "blocked_until_effect_binding"


_CONDITIONAL_DISCRIMINATOR_BRANCHES: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {"handler_effect_path.v1": ("no_effect_or_read", "external_or_legacy_effect")}
)
_EFFECT_PORTS_BY_CLASS: Final[Mapping[EffectClass, frozenset[str]]] = MappingProxyType(
    {
        EffectClass.READ: frozenset(),
        EffectClass.PURE_COMPUTE: frozenset(),
        EffectClass.PROVIDER_CALL: frozenset({"provider_port"}),
        EffectClass.LEGACY_WRITE: frozenset(),
        EffectClass.CANONICAL_WRITE: frozenset({"canonical_writer_port"}),
        EffectClass.EXTERNAL_AUTH: frozenset({"external_auth_port"}),
        EffectClass.FILESYSTEM_SUBPROCESS: frozenset({"filesystem_port"}),
        EffectClass.CONDITIONAL: frozenset(),
    }
)
_EFFECT_PORT_FIELDS: Final[tuple[str, ...]] = (
    "provider_port",
    "canonical_writer_port",
    "external_auth_port",
    "filesystem_port",
)

ROUTE_EFFECT_FAILURE_FAMILY: Final[str] = "mrw.production.route-effect.failure.v1"


route_effect_failures = define_failure_family(
    "mrw.production.route-effect.failure.v1",
    (
        "route_effect_unclassified",
        "route_effect_mismatch",
        "provider_port_unbound",
        "provider_class_mismatch",
        "canonical_writer_port_unbound",
        "legacy_writer_claimed_as_successor",
        "conditional_effect_undiscriminated",
        "public_effect_route_unadmitted",
    ),
)


class RouteEffectContractError(RuntimeError):
    """Typed, fail-closed loader/contract error.

    ``code`` is intentionally mirrored on the exception and its kit Failure
    so callers can preserve the observable failure family without parsing
    human-readable messages.
    """

    def __init__(self, code: str, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        self.code = code
        self.failure = route_effect_failures.fail(
            code,
            message,
            {"stage": "route_effect", "details": dict(details or {})},
        )
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class EndpointEffectContract:
    """Semantic effect binding for one endpoint.

    Ports are names of installed runtime capabilities, not implementation
    claims inferred from route names.  Conditional effects remain blocked
    unless a discriminator and a closed branch vocabulary are supplied.
    """

    effect_class: EffectClass
    admission: EffectAdmission | None = None
    provider_port: str | None = None
    provider_class: ProviderClass = ProviderClass.NULL
    canonical_writer_port: str | None = None
    external_auth_port: str | None = None
    filesystem_port: str | None = None
    conditional_discriminator: str | None = None
    conditional_branches: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            effect_class = (
                self.effect_class
                if isinstance(self.effect_class, EffectClass)
                else EffectClass(self.effect_class)
            )
        except (TypeError, ValueError) as exc:
            raise RouteEffectContractError(
                "route_effect_unclassified",
                "effect class is outside the closed route vocabulary",
                details={"effect_class": self.effect_class},
            ) from exc
        if self.admission is None:
            admission = (
                EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING
                if effect_class is EffectClass.FILESYSTEM_SUBPROCESS
                else EffectAdmission.ADMITTED
            )
        else:
            try:
                admission = (
                    self.admission
                    if isinstance(self.admission, EffectAdmission)
                    else EffectAdmission(self.admission)
                )
            except (TypeError, ValueError) as exc:
                raise RouteEffectContractError(
                    "route_effect_unclassified",
                    "effect admission is outside the closed route vocabulary",
                    details={"admission": self.admission},
                ) from exc
        object.__setattr__(self, "effect_class", effect_class)
        object.__setattr__(self, "admission", admission)
        allowed_ports = _EFFECT_PORTS_BY_CLASS[effect_class]
        for field_name in _EFFECT_PORT_FIELDS:
            value = _clean_text(getattr(self, field_name))
            object.__setattr__(self, field_name, value)
            if value is not None and field_name not in allowed_ports:
                raise RouteEffectContractError(
                    "route_effect_mismatch",
                    "effect class cannot declare this port",
                    details={"effect_class": effect_class.value, "port": field_name},
                )
        try:
            provider_class = (
                self.provider_class
                if isinstance(self.provider_class, ProviderClass)
                else ProviderClass(self.provider_class)
            )
        except (TypeError, ValueError) as exc:
            raise RouteEffectContractError(
                "provider_class_mismatch",
                "provider class is outside the closed provider vocabulary",
                details={"provider_class": self.provider_class},
            ) from exc
        object.__setattr__(self, "provider_class", provider_class)
        try:
            branches = _freeze_strings(
                self.conditional_branches,
                field_name="conditional_branches",
                deduplicate=False,
            )
        except (TypeError, ValueError) as exc:
            raise RouteEffectContractError(
                "route_effect_unclassified",
                "conditional_branches must be a sequence of non-empty strings",
            ) from exc
        object.__setattr__(self, "conditional_branches", branches)


        if effect_class is EffectClass.LEGACY_WRITE and admission is EffectAdmission.ADMITTED:
            raise RouteEffectContractError(
                "legacy_writer_claimed_as_successor",
                "legacy writes can never be admitted as successor effects",
            )
        if effect_class is EffectClass.PROVIDER_CALL:
            if admission is EffectAdmission.ADMITTED and self.provider_port is None:
                raise RouteEffectContractError(
                    "provider_port_unbound",
                    "admitted provider effect requires a provider port",
                )
            if provider_class is ProviderClass.NULL:
                raise RouteEffectContractError(
                    "provider_class_mismatch",
                    "provider effect requires a non-null provider class",
                )
        elif provider_class is not ProviderClass.NULL:
            raise RouteEffectContractError(
                "provider_class_mismatch",
                "non-provider effect cannot declare a provider class",
            )
        if (
            effect_class is EffectClass.CANONICAL_WRITE
            and admission is EffectAdmission.ADMITTED
            and self.canonical_writer_port is None
        ):
            raise RouteEffectContractError(
                "canonical_writer_port_unbound",
                "admitted canonical write requires a canonical writer port",
            )
        if (
            effect_class is EffectClass.EXTERNAL_AUTH
            and admission is EffectAdmission.ADMITTED
            and self.external_auth_port is None
        ):
            raise RouteEffectContractError(
                "route_effect_mismatch",
                "admitted external auth requires an external auth port",
            )
        if effect_class is EffectClass.FILESYSTEM_SUBPROCESS:
            if admission is EffectAdmission.ADMITTED and self.filesystem_port is None:
                raise RouteEffectContractError(
                    "route_effect_mismatch",
                    "admitted filesystem effect requires a filesystem port",
                )
        if effect_class is EffectClass.CONDITIONAL:
            discriminator = _clean_text(self.conditional_discriminator)
            if discriminator is None:
                raise RouteEffectContractError(
                    "conditional_effect_undiscriminated",
                    "conditional effect requires a discriminator",
                )
            object.__setattr__(self, "conditional_discriminator", discriminator)
            expected_branches = _CONDITIONAL_DISCRIMINATOR_BRANCHES.get(discriminator)
            if expected_branches is None or branches != expected_branches:
                raise RouteEffectContractError(
                    "route_effect_mismatch",
                    "conditional effect does not match its closed discriminator branch shape",
                    details={
                        "conditional_discriminator": discriminator,
                        "conditional_branches": branches,
                    },
                )
            # Conditional routing remains conservative until a later contract
            # proves branch closure; a discriminator alone is not execution
            # authority.
            if admission is EffectAdmission.ADMITTED:
                object.__setattr__(self, "admission", EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING)
        elif self.conditional_discriminator is not None or branches:
            raise RouteEffectContractError(
                "route_effect_mismatch",
                "conditional fields are only valid for conditional effects",
            )

    @property
    def requires_provider(self) -> bool:
        return self.effect_class is EffectClass.PROVIDER_CALL

    @property
    def requires_canonical_writer(self) -> bool:
        return self.effect_class is EffectClass.CANONICAL_WRITE

    @property
    def approval_required(self) -> bool:
        return self.requires_provider or self.requires_canonical_writer

    @property
    def admitted(self) -> bool:
        return self.admission is EffectAdmission.ADMITTED

    def require_admitted(self) -> None:
        """Fail closed for a public route before any downstream effect runs."""

        if not self.admitted:
            raise RouteEffectContractError(
                "public_effect_route_unadmitted",
                "public route effect is blocked until its effect binding is admitted",
                details={
                    "effect_class": self.effect_class.value,
                    "admission": self.admission.value,
                },
            )


production_policy_failures = define_failure_family(
    "mrw.production-policy.failure.v1",
    (
        "actor_unauthenticated",
        "actor_not_allowed",
        "project_missing",
        "project_mismatch",
        "project_not_found",
        "scope_denied",
        "approval_missing",
        "approval_denied",
        "approval_expired",
        "tls_denied",
        "cors_origin_denied",
        "body_too_large",
        "content_type_denied",
        "rate_limited",
        "provider_denied",
        "provider_limits_exceeded",
        "canonical_writer_owner_missing",
        "canonical_writer_owner_mismatch",
        "policy_contract_invalid",
        "provider_timeout",
        "provider_unavailable",
        "database_unavailable",
        "unclassified_defect",
    ),
)

_RUNTIME_CODES: Final[frozenset[str]] = frozenset(
    {"provider_timeout", "provider_unavailable", "database_unavailable"}
)
_DEFECT_CODES: Final[frozenset[str]] = frozenset(
    {"policy_contract_invalid", "unclassified_defect"}
)


class PolicyActor(Protocol):
    """Structural view of the existing successor RequestActorContext."""

    actor_id: str
    actor_source: str
    actor_auth_mode: str
    actor_trusted: bool


@dataclass(frozen=True, slots=True)
class HTTPPolicy:
    require_tls: bool
    allowed_origins: tuple[str, ...]
    allowed_methods: tuple[str, ...]
    allowed_content_types: tuple[str, ...]
    max_body_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.require_tls, bool):
            raise TypeError("HTTPPolicy.require_tls must be bool")
        methods = _freeze_strings(self.allowed_methods, field_name="allowed_methods")
        origins = _freeze_strings(self.allowed_origins, field_name="allowed_origins")
        content_types = _freeze_strings(
            self.allowed_content_types, field_name="allowed_content_types"
        )
        if not isinstance(self.max_body_bytes, int) or isinstance(
            self.max_body_bytes, bool
        ) or self.max_body_bytes < 0:
            raise ValueError("HTTPPolicy.max_body_bytes must be a non-negative integer")
        object.__setattr__(self, "allowed_methods", methods)
        object.__setattr__(self, "allowed_origins", origins)
        object.__setattr__(self, "allowed_content_types", content_types)


@dataclass(frozen=True, slots=True)
class RatePolicy:
    max_requests: int
    window_seconds: int

    def __post_init__(self) -> None:
        _require_non_negative_int(self.max_requests, "RatePolicy.max_requests")
        _require_positive_int(self.window_seconds, "RatePolicy.window_seconds")


@dataclass(frozen=True, slots=True)
class ProviderPolicy:
    allowed_provider_ids: tuple[str, ...]
    max_requests: int
    window_seconds: int
    max_payload_bytes: int

    def __post_init__(self) -> None:
        providers = _freeze_strings(
            self.allowed_provider_ids, field_name="allowed_provider_ids"
        )
        _require_non_negative_int(self.max_requests, "ProviderPolicy.max_requests")
        _require_positive_int(self.window_seconds, "ProviderPolicy.window_seconds")
        _require_non_negative_int(
            self.max_payload_bytes, "ProviderPolicy.max_payload_bytes"
        )
        object.__setattr__(self, "allowed_provider_ids", providers)


@dataclass(frozen=True, slots=True)
class OperationPolicy:
    required_scope: str
    required_approval_ids: tuple[str, ...] = ()
    requires_provider: bool = False
    requires_canonical_writer: bool = False
    provider_class: ProviderClass = ProviderClass.NULL
    approval_required: bool = False
    capability_id: str = ""
    canonical_owner_ref: str | None = None
    writer_port_kind: str | None = None
    effect_admission: EffectAdmission = EffectAdmission.ADMITTED

    def __post_init__(self) -> None:
        if _clean_text(self.required_scope) is None:
            raise ValueError("OperationPolicy.required_scope must be non-empty")
        approvals = _freeze_strings(
            self.required_approval_ids, field_name="required_approval_ids"
        )
        for field_name in ("requires_provider", "requires_canonical_writer"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"OperationPolicy.{field_name} must be bool")
        for field_name in ("approval_required",):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"OperationPolicy.{field_name} must be bool")
        if not isinstance(self.effect_admission, EffectAdmission):
            try:
                object.__setattr__(self, "effect_admission", EffectAdmission(self.effect_admission))
            except (TypeError, ValueError) as exc:
                raise ValueError("OperationPolicy.effect_admission is not closed") from exc
        if not isinstance(self.provider_class, ProviderClass):
            try:
                provider_class = ProviderClass(self.provider_class)
            except ValueError as exc:
                raise ValueError("OperationPolicy.provider_class is not closed") from exc
            object.__setattr__(self, "provider_class", provider_class)
        if self.requires_provider and self.provider_class is ProviderClass.NULL:
            raise ValueError("OperationPolicy requiring a provider must declare a non-null class")
        if not self.requires_provider and self.provider_class is not ProviderClass.NULL:
            raise ValueError("OperationPolicy not requiring a provider must declare the null class")
        high_risk = self.requires_provider or self.requires_canonical_writer
        if self.approval_required != high_risk:
            raise ValueError("OperationPolicy.approval_required must match its high-risk effects")
        if self.approval_required and _clean_text(self.capability_id) is None:
            raise ValueError("high-risk OperationPolicy.capability_id is required")
        if self.requires_canonical_writer:
            if self.effect_admission is EffectAdmission.ADMITTED and (
                _clean_text(self.canonical_owner_ref) is None
                or _clean_text(self.writer_port_kind) is None
            ):
                raise ValueError("canonical writer OperationPolicy requires owner and port bindings")
        elif self.canonical_owner_ref is not None or self.writer_port_kind is not None:
            raise ValueError("non-writer OperationPolicy cannot declare canonical writer bindings")
        capability = _clean_text(self.capability_id)
        owner = _clean_text(self.canonical_owner_ref)
        port = _clean_text(self.writer_port_kind)
        object.__setattr__(self, "required_scope", _clean_text(self.required_scope))
        object.__setattr__(self, "required_approval_ids", approvals)
        object.__setattr__(self, "capability_id", capability or "")
        object.__setattr__(self, "canonical_owner_ref", owner)
        object.__setattr__(self, "writer_port_kind", port)


@dataclass(frozen=True, slots=True)
class ProjectBinding:
    project_key: str
    scope: ProjectScopeRef

    def __post_init__(self) -> None:
        if _clean_text(self.project_key) is None:
            raise ValueError("ProjectBinding.project_key must be non-empty")
        if not isinstance(self.scope, ProjectScopeRef):
            raise TypeError("ProjectBinding.scope must be ProjectScopeRef")
        object.__setattr__(self, "project_key", _clean_text(self.project_key))


@dataclass(frozen=True, slots=True)
class ApprovalGrant:
    approval_id: str
    actor_id: str
    decision: str
    expires_at: datetime | None = None
    project_key: str = ""
    operation: str = ""
    capability_id: str = ""
    payload_digest: str = ""
    claim_authority_epoch: int = 0

    def __post_init__(self) -> None:
        for field_name in ("approval_id", "actor_id", "decision"):
            if _clean_text(getattr(self, field_name)) is None:
                raise ValueError(f"ApprovalGrant.{field_name} is required")
        if self.claim_authority_epoch < 0:
            raise ValueError("ApprovalGrant.claim_authority_epoch must be non-negative")


@dataclass(frozen=True, slots=True)
class ProductionRequest:
    """One normalized pure observation; no Request or effect object is read."""

    operation: str
    actor: PolicyActor
    actor_scopes: tuple[str, ...]
    approvals: tuple[ApprovalGrant, ...]
    observed_at: datetime
    route_project_key: str | None = None
    payload_project_key: str | None = None
    scheme: str = "https"
    origin: str | None = None
    method: str = "POST"
    body_size: int = 0
    content_type: str | None = None
    http_request_count: int = 0
    http_window_seconds: int = 60
    provider_id: str | None = None
    provider_class: ProviderClass = ProviderClass.NULL
    provider_request_payload_bytes: int = 0
    provider_request_count: int = 0
    provider_window_seconds: int = 60
    canonical_writer_owner: str | None = None
    canonical_owner_ref: str | None = None
    writer_port_kind: str | None = None
    payload_digest: str = ""


@dataclass(frozen=True, slots=True)
class ProductionPolicyConfig:
    """Injected declarative configuration; no value is read from settings."""

    trusted_actor_sources: tuple[str, ...]
    trusted_auth_modes: tuple[str, ...]
    transport: HTTPPolicy
    http_rate: RatePolicy
    provider: ProviderPolicy
    operations: Mapping[str, OperationPolicy]
    projects: Mapping[str, ProjectBinding]
    canonical_writer_owner: str = ""

    def __post_init__(self) -> None:
        sources = _freeze_strings(
            self.trusted_actor_sources, field_name="trusted_actor_sources"
        )
        modes = _freeze_strings(
            self.trusted_auth_modes, field_name="trusted_auth_modes"
        )
        operations = _freeze_mapping(self.operations, field_name="operations")
        projects = _freeze_mapping(self.projects, field_name="projects")
        if not operations:
            raise ValueError("at least one operation policy is required")
        for operation, policy in operations.items():
            if _clean_text(operation) != operation or not isinstance(policy, OperationPolicy):
                raise ValueError("operations must map canonical names to OperationPolicy")
        for project_key, binding in projects.items():
            if _clean_text(project_key) != project_key or not isinstance(binding, ProjectBinding):
                raise ValueError("projects must map canonical names to ProjectBinding")
            if binding.project_key != project_key:
                raise ValueError("project binding key differs from catalog key")
        object.__setattr__(self, "trusted_actor_sources", sources)
        object.__setattr__(self, "trusted_auth_modes", modes)
        object.__setattr__(self, "canonical_writer_owner", _clean_text(self.canonical_writer_owner) or "")
        object.__setattr__(self, "operations", operations)
        object.__setattr__(self, "projects", projects)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """A derived decision with an explicit non-authoritative boundary."""

    outcome: PolicyOutcome
    failure: Failure | None = None
    stage: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    authority: Literal[False] = False

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, PolicyOutcome):
            raise TypeError("PolicyDecision.outcome must be PolicyOutcome")
        if self.outcome is PolicyOutcome.PASS and self.failure is not None:
            raise ValueError("PASS decision cannot carry a failure")
        if self.outcome is not PolicyOutcome.PASS and self.failure is None:
            raise ValueError("non-PASS decision requires a failure")
        if self.authority is not False:
            raise ValueError("policy decisions never grant authority")
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))

    @property
    def passed(self) -> bool:
        return self.outcome is PolicyOutcome.PASS

    def as_derived(self) -> Any:
        """Return the kit-owned non-authoritative marker for this decision."""

        return derived("preflight", self)


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _freeze_strings(
    values: Any,
    *,
    field_name: str,
    deduplicate: bool = True,
) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} must be a list or tuple")
    cleaned: list[str] = []
    for value in values:
        text = _clean_text(value)
        if text is None:
            raise ValueError(f"{field_name} entries must be non-empty strings")
        cleaned.append(text)
    return tuple(dict.fromkeys(cleaned) if deduplicate else cleaned)


def _freeze_mapping(values: Mapping[str, Any], *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a Mapping")
    return MappingProxyType(dict(values))


def _require_non_negative_int(value: Any, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_positive_int(value: Any, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def policy_failure(
    code: str,
    message: str,
    *,
    stage: str,
    details: Mapping[str, Any] | None = None,
) -> Failure:
    """Build the only failure value admitted by this kernel."""

    clean_stage = _clean_text(stage)
    if clean_stage is None:
        raise ValueError("policy failure stage must be non-empty")
    clean_message = _clean_text(message)
    if clean_message is None:
        raise ValueError("policy failure message must be non-empty")
    context = {
        "stage": clean_stage,
        "details": dict(details or {}),
    }
    return production_policy_failures.fail(code, clean_message, context)


def _decision_for_failure(failure: Failure) -> PolicyDecision:
    context = failure.context or {}
    stage = str(context.get("stage", ""))
    details = context.get("details")
    if not production_policy_failures.matches(failure) or not isinstance(details, dict):
        raise ValueError("failure context is outside the production policy contract")
    if failure.code in _DEFECT_CODES:
        outcome = PolicyOutcome.UNCLASSIFIED_DEFECT
    elif failure.code in _RUNTIME_CODES:
        outcome = PolicyOutcome.CLASSIFIED_RUNTIME_FAILURE
    else:
        outcome = PolicyOutcome.DOMAIN_REJECTION
    return PolicyDecision(outcome=outcome, failure=failure, stage=stage, details=details)
