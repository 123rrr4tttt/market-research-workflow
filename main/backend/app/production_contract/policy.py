"""Pure evaluation rules for production request and execution admission."""

# ruff: noqa: TRY003
from __future__ import annotations

from collections.abc import Mapping

from app.production_contract.types import (
    APPROVED_DECISION,
    OperationPolicy,
    PolicyDecision,
    PolicyOutcome,
    ProductionPolicyConfig,
    ProductionRequest,
    ProjectBinding,
    _decision_for_failure,
    policy_failure,
)


def resolve_project(
    config: ProductionPolicyConfig, request: ProductionRequest
) -> tuple[ProjectBinding | None, PolicyDecision | None]:
    """Resolve one exact project binding or return a fail-closed decision."""

    route_key = request.route_project_key
    payload_key = request.payload_project_key
    if route_key is None or payload_key is None:
        return None, _rejection(
            "project_missing",
            "route and payload project keys are required",
            stage="project",
            details={"route_project_key": route_key, "payload_project_key": payload_key},
        )
    if route_key != payload_key:
        return None, _rejection(
            "project_mismatch",
            "route and payload project keys differ",
            stage="project",
            details={"route_project_key": route_key, "payload_project_key": payload_key},
        )
    binding = config.projects.get(route_key)
    if binding is None:
        return None, _rejection(
            "project_not_found",
            "project is not registered in the policy binding",
            stage="project",
            details={"project_key": route_key},
    )
    return binding, None


def evaluate_production_policy(
    config: ProductionPolicyConfig, request: ProductionRequest
) -> PolicyDecision:
    """Evaluate all predicates in a stable order without performing effects."""

    operation = config.operations.get(request.operation)
    if operation is None:
        return _contract_invalid(f"unknown operation: {request.operation}")
    _actor, decision = _evaluate_actor(config, request)
    if decision is not None:
        return decision
    _binding, decision = resolve_project(config, request)
    if decision is not None:
        return decision
    decision = _evaluate_scope(request, operation)
    if decision is not None:
        return decision
    decision = _evaluate_approvals(request, operation)
    if decision is not None:
        return decision
    decision = _evaluate_http(config, request)
    if decision is not None:
        return decision
    decision = _evaluate_http_rate(config, request)
    if decision is not None:
        return decision
    decision = _evaluate_provider(config, request, operation)
    if decision is not None:
        return decision
    return _evaluate_writer(config, request, operation)


def classify_runtime_exception(exception: BaseException) -> PolicyDecision:
    """Map a bounded local exception set; every other exception stays a defect."""

    if isinstance(exception, TimeoutError):
        return _runtime("provider_timeout", "provider operation timed out", exception)
    if isinstance(exception, ConnectionError):
        return _runtime("provider_unavailable", "provider connection failed", exception)
    if exception.__class__.__name__ in {"OperationalError", "DBAPIError"}:
        return _runtime("database_unavailable", "database operation failed", exception)
    return _unclassified(exception)


def _evaluate_actor(
    config: ProductionPolicyConfig, request: ProductionRequest
) -> tuple[object, PolicyDecision | None]:
    actor = request.actor
    if not isinstance(getattr(actor, "actor_trusted", None), bool) or not actor.actor_trusted:
        return actor, _rejection(
            "actor_unauthenticated",
            "trusted actor context is required",
            stage="actor",
            details={"actor_id": str(getattr(actor, "actor_id", ""))},
        )
    if actor.actor_source not in config.trusted_actor_sources:
        return actor, _rejection(
            "actor_not_allowed",
            "actor identity source is not allowed",
            stage="actor",
            details={"actor_source": actor.actor_source},
        )
    if actor.actor_auth_mode not in config.trusted_auth_modes:
        return actor, _rejection(
            "actor_not_allowed",
            "actor authentication mode is not allowed",
            stage="actor",
            details={"actor_auth_mode": actor.actor_auth_mode},
        )
    return actor, None


def _evaluate_scope(
    request: ProductionRequest, operation: OperationPolicy
) -> PolicyDecision | None:
    if operation.required_scope not in request.actor_scopes:
        return _rejection(
            "scope_denied",
            "actor lacks the required operation scope",
            stage="scope",
            details={"required_scope": operation.required_scope},
        )
    return None


def _evaluate_approvals(
    request: ProductionRequest, operation: OperationPolicy
) -> PolicyDecision | None:
    for grant in request.approvals:
        if not isinstance(getattr(grant, "approval_id", None), str) or not grant.approval_id:
            return _contract_invalid("approval observation has no stable locator")
        approval_id = grant.approval_id
        if grant.actor_id != request.actor.actor_id:
            return _rejection(
                "approval_denied",
                "approval actor differs from request actor",
                stage="approval",
                details={"approval_id": approval_id},
            )
        if grant.decision != APPROVED_DECISION:
            return _rejection(
                "approval_denied",
                "approval is not APPROVED",
                stage="approval",
                details={"approval_id": approval_id},
            )
        if grant.expires_at is not None and grant.expires_at <= request.observed_at:
                return _rejection(
                    "approval_expired",
                "approval is expired",
                stage="approval",
                details={"approval_id": approval_id},
            )
    if not operation.approval_required:
        return None
    if not request.approvals:
        return _rejection(
            "approval_missing",
            "verified operation approval is absent",
            stage="approval",
        )
    if len(request.approvals) != 1:
        return _contract_invalid("high-risk operation approval observation is ambiguous")
    grant = request.approvals[0]
    exact_fields = (
        (grant.project_key, request.route_project_key, "project_key"),
        (grant.operation, request.operation, "operation"),
        (grant.capability_id, operation.capability_id, "capability_id"),
        (grant.payload_digest, request.payload_digest, "payload_digest"),
    )
    if any(observed != expected for observed, expected, _field in exact_fields):
        return _rejection(
            "approval_denied",
            "verified approval binding differs from the request operation",
            stage="approval",
            details={"approval_id": grant.approval_id},
        )
    for approval_id in operation.required_approval_ids:
        if grant.approval_id != approval_id:
            return _rejection(
                "approval_missing",
                "required approval is absent",
                stage="approval",
                details={"approval_id": approval_id},
            )
    return None


def _evaluate_http(
    config: ProductionPolicyConfig, request: ProductionRequest
) -> PolicyDecision | None:
    policy = config.transport
    if policy.require_tls and request.scheme.lower() != "https":
        return _rejection(
            "tls_denied",
            "TLS is required",
            stage="http.tls",
            details={"scheme": request.scheme},
        )
    if request.method.upper() not in policy.allowed_methods:
        return _rejection(
            "actor_not_allowed",
            "HTTP method is not allowed",
            stage="http.method",
            details={"method": request.method},
        )
    if request.origin is not None and request.origin not in policy.allowed_origins:
        return _rejection(
            "cors_origin_denied",
            "origin is not allowed",
            stage="http.cors",
            details={"origin": request.origin},
        )
    if request.body_size < 0 or request.body_size > policy.max_body_bytes:
        return _rejection(
            "body_too_large",
            "request body exceeds the declared ceiling",
            stage="http.body",
            details={"body_size": request.body_size, "max_body_bytes": policy.max_body_bytes},
        )
    if request.body_size == 0:
        return None
    content_type = request.content_type
    if content_type is None or content_type.lower() not in policy.allowed_content_types:
        return _rejection(
            "content_type_denied",
            "content type is not allowed",
            stage="http.body",
            details={"content_type": content_type},
        )
    return None


def _evaluate_http_rate(
    config: ProductionPolicyConfig, request: ProductionRequest
) -> PolicyDecision | None:
    return _evaluate_rate(
        request.http_request_count,
        request.http_window_seconds,
        config.http_rate.max_requests,
        config.http_rate.window_seconds,
        stage="rate.http",
    )


def _evaluate_provider(
    config: ProductionPolicyConfig,
    request: ProductionRequest,
    operation: OperationPolicy,
) -> PolicyDecision | None:
    if operation.requires_provider and request.provider_id is None:
        return _rejection(
            "provider_denied",
            "provider is required",
                stage="provider",
            )
    if operation.requires_provider and request.provider_class != operation.provider_class:
        return _rejection(
            "provider_denied",
            "provider class differs from the registered operation class",
            stage="provider",
            details={"provider_class": request.provider_class.value},
        )
    if request.provider_id is None:
        return None
    if not operation.requires_provider:
        return _contract_invalid("provider observation is outside the operation contract")
    if request.provider_id not in config.provider.allowed_provider_ids:
        return _rejection(
            "provider_denied",
            "provider is not allowlisted",
            stage="provider",
            details={"provider_id": request.provider_id},
        )
    if (
        request.provider_request_payload_bytes < 0
        or request.provider_request_payload_bytes > config.provider.max_payload_bytes
    ):
        return _rejection(
            "provider_limits_exceeded",
            "provider request payload bytes exceed the declared ceiling",
            stage="provider.limits",
            details={
                "provider_id": request.provider_id,
                "payload_measure": "cached_http_raw_request_body_bytes",
                "payload_size": request.provider_request_payload_bytes,
                "max_payload_bytes": config.provider.max_payload_bytes,
            },
        )
    return _evaluate_rate(
        request.provider_request_count,
        request.provider_window_seconds,
        config.provider.max_requests,
        config.provider.window_seconds,
        stage="rate.provider",
        details={"provider_id": request.provider_id},
    )


def _evaluate_writer(
    config: ProductionPolicyConfig,
    request: ProductionRequest,
    operation: OperationPolicy,
) -> PolicyDecision | None:
    if not operation.requires_canonical_writer:
        return PolicyDecision(outcome=PolicyOutcome.PASS)
    owner = request.canonical_writer_owner
    if owner is None:
        return _rejection(
            "canonical_writer_owner_missing",
            "canonical write requires the declared writer owner",
                stage="canonical_writer",
            )
    if (
        request.canonical_owner_ref != operation.canonical_owner_ref
        or request.writer_port_kind != operation.writer_port_kind
        or owner != operation.canonical_owner_ref
    ):
        return _rejection(
            "canonical_writer_owner_mismatch",
            "canonical writer claim does not match the registered project-operation port",
            stage="canonical_writer",
            details={
                "expected_owner": operation.canonical_owner_ref,
                "expected_writer_port_kind": operation.writer_port_kind,
                "observed_owner": owner,
                "observed_writer_port_kind": request.writer_port_kind,
            },
        )
    return PolicyDecision(outcome=PolicyOutcome.PASS)


def _evaluate_rate(
    observed_count: int,
    observed_window: int,
    max_requests: int,
    configured_window: int,
    *,
    stage: str,
    details: Mapping[str, object] | None = None,
) -> PolicyDecision | None:
    if observed_count < 0 or observed_window <= 0:
        return _contract_invalid("rate observation must be non-negative with a positive window")
    normalized_count = observed_count * configured_window // observed_window
    if normalized_count > max_requests:
        return _rejection(
            "rate_limited",
            "configured rate ceiling is exceeded",
            stage=stage,
            details={
                **(dict(details) if details else {}),
                "observed_count": observed_count,
                "observed_window": observed_window,
                "max_requests": max_requests,
                "configured_window": configured_window,
            },
        )
    return None


def _rejection(
    code: str,
    message: str,
    *,
    stage: str,
    details: Mapping[str, object] | None = None,
) -> PolicyDecision:
    return _decision_for_failure(policy_failure(code, message, stage=stage, details=details))


def _runtime(code: str, message: str, exception: BaseException) -> PolicyDecision:
    return _decision_for_failure(
        policy_failure(
            code,
            message,
            stage="runtime",
            details={"exception_type": exception.__class__.__name__},
        )
    )


def _unclassified(exception: BaseException) -> PolicyDecision:
    return _decision_for_failure(
        policy_failure(
            "unclassified_defect",
            "exception is outside the production policy runtime family",
            stage="runtime",
            details={"exception_type": exception.__class__.__name__},
        )
    )


def _contract_invalid(message: str) -> PolicyDecision:
    return _decision_for_failure(
        policy_failure("policy_contract_invalid", message, stage="contract")
    )
