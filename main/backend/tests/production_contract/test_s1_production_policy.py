"""Focused contract tests for the pure S1 production policy kernel."""

# ruff: noqa: E402
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent.parent
for path in (str(BACKEND_ROOT), str(REPOSITORY_ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

import pytest
from dataclasses import FrozenInstanceError

from app.production_contract import (
    APPROVED_DECISION,
    ApprovalGrant,
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
    classify_runtime_exception,
    evaluate_production_policy,
    production_policy_failures,
    resolve_project,
)
from app.successor_runtime.capabilities.request_identity_port import (
    authenticated_actor_context,
    legacy_or_anonymous_actor_context,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef

pytestmark = pytest.mark.unit

OBSERVED_AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
PROJECT_KEY = "alpha"
SCOPE = ProjectScopeRef(
    project_key=PROJECT_KEY,
    resolved_schema="project_alpha",
    project_registry_revision=7,
    incarnation="project-alpha-incarnation",
    scope_digest="0" * 64,
)
ACTOR = authenticated_actor_context(
    actor_id="actor-1",
    source="oauth_session",
    auth_mode="oidc_claims",
)


def _config(
    *,
    require_tls: bool = True,
    allowed_origins: tuple[str, ...] = ("https://app.example",),
    max_body: int = 128,
    max_requests: int = 2,
    providers: tuple[str, ...] = ("serper",),
    owner: str = "successor-canonical-writer",
) -> ProductionPolicyConfig:
    return ProductionPolicyConfig(
        trusted_actor_sources=("oauth_session",),
        trusted_auth_modes=("oidc_claims",),
        transport=HTTPPolicy(
            require_tls=require_tls,
            allowed_origins=allowed_origins,
            allowed_methods=("GET", "POST"),
            allowed_content_types=("application/json",),
            max_body_bytes=max_body,
        ),
        http_rate=RatePolicy(max_requests=max_requests, window_seconds=60),
        provider=ProviderPolicy(
            allowed_provider_ids=providers,
            max_requests=1,
            window_seconds=60,
            max_payload_bytes=64,
        ),
        canonical_writer_owner=owner,
        operations={
            "document.read": OperationPolicy(required_scope="document:read"),
            "document.write": OperationPolicy(
                required_scope="document:write",
                required_approval_ids=("approval-1",),
                requires_provider=True,
                requires_canonical_writer=True,
                provider_class=ProviderClass.CRAWLER,
                approval_required=True,
                capability_id="document.write",
                canonical_owner_ref="successor-runtime",
                writer_port_kind="runtime_step_authorization.v1",
            ),
        },
        projects={PROJECT_KEY: ProjectBinding(project_key=PROJECT_KEY, scope=SCOPE)},
    )


def _request(**overrides: object) -> ProductionRequest:
    values: dict[str, object] = {
        "operation": "document.write",
        "actor": ACTOR,
        "actor_scopes": ("document:read", "document:write"),
        "approvals": (
            ApprovalGrant(
                approval_id="approval-1",
                actor_id="actor-1",
                decision=APPROVED_DECISION,
                expires_at=OBSERVED_AT + timedelta(minutes=5),
                project_key=PROJECT_KEY,
                operation="document.write",
                capability_id="document.write",
                payload_digest="a" * 64,
                claim_authority_epoch=7,
            ),
        ),
        "observed_at": OBSERVED_AT,
        "route_project_key": PROJECT_KEY,
        "payload_project_key": PROJECT_KEY,
        "scheme": "https",
        "origin": "https://app.example",
        "method": "POST",
        "body_size": 16,
        "content_type": "application/json",
        "http_request_count": 2,
        "http_window_seconds": 60,
        "provider_id": "serper",
        "provider_class": ProviderClass.CRAWLER,
        "provider_request_payload_bytes": 32,
        "provider_request_count": 1,
        "provider_window_seconds": 60,
        "canonical_writer_owner": "successor-runtime",
        "canonical_owner_ref": "successor-runtime",
        "writer_port_kind": "runtime_step_authorization.v1",
        "payload_digest": "a" * 64,
    }
    values.update(overrides)
    return ProductionRequest(**values)  # type: ignore[arg-type]


def test_valid_fixture_passes_but_does_not_grant_authority() -> None:
    decision = evaluate_production_policy(_config(), _request())

    assert decision.passed
    assert decision.outcome is PolicyOutcome.PASS
    assert decision.authority is False
    derived = decision.as_derived()
    assert derived.authoritative is False
    assert derived.derived_as == "preflight"


def test_untrusted_legacy_actor_fails_closed() -> None:
    decision = evaluate_production_policy(
        _config(), _request(actor=legacy_or_anonymous_actor_context(None))
    )

    assert decision.outcome is PolicyOutcome.DOMAIN_REJECTION
    assert decision.failure is not None
    assert production_policy_failures.matches(decision.failure)
    assert decision.failure.code == "actor_unauthenticated"


@pytest.mark.parametrize(
    ("route", "payload", "expected"),
    [
        (None, PROJECT_KEY, "project_missing"),
        (PROJECT_KEY, None, "project_missing"),
        ("alpha", "beta", "project_mismatch"),
        ("missing", "missing", "project_not_found"),
    ],
)
def test_project_resolution_fails_closed(
    route: str | None, payload: str | None, expected: str
) -> None:
    decision = evaluate_production_policy(
        _config(), _request(route_project_key=route, payload_project_key=payload)
    )

    assert decision.failure is not None
    assert decision.failure.code == expected
    resolved, direct_decision = resolve_project(
        _config(),
        _request(route_project_key=route, payload_project_key=payload),
    )
    assert resolved is None
    assert direct_decision is not None
    assert direct_decision.failure is not None
    assert direct_decision.failure.code == expected


@pytest.mark.parametrize(
    ("scopes", "approvals", "expected"),
    [
        (("document:read",), ("approval-1",), "scope_denied"),
        (("document:write",), (), "approval_missing"),
    ],
)
def test_scope_and_approval_failures_are_closed(
    scopes: tuple[str, ...], approvals: tuple[str, ...], expected: str
) -> None:
    grants = tuple(
        ApprovalGrant(
            approval_id=approval_id,
            actor_id="actor-1",
            decision=APPROVED_DECISION,
            expires_at=OBSERVED_AT + timedelta(minutes=1),
        )
        for approval_id in approvals
    )
    decision = evaluate_production_policy(
        _config(), _request(actor_scopes=scopes, approvals=grants)
    )

    assert decision.failure is not None
    assert decision.failure.code == expected


def test_wrong_or_expired_approval_is_rejected() -> None:
    wrong_actor = ApprovalGrant(
        approval_id="approval-1", actor_id="actor-2", decision=APPROVED_DECISION
    )
    denied = ApprovalGrant(
        approval_id="approval-1", actor_id="actor-1", decision="DENIED"
    )
    expired = ApprovalGrant(
        approval_id="approval-1",
        actor_id="actor-1",
        decision=APPROVED_DECISION,
        expires_at=OBSERVED_AT - timedelta(seconds=1),
    )

    for grant in (wrong_actor, denied, expired):
        decision = evaluate_production_policy(_config(), _request(approvals=(grant,)))
        assert decision.failure is not None
        assert decision.failure.code in {"approval_denied", "approval_expired"}


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"scheme": "http"}, "tls_denied"),
        ({"origin": "https://not.example"}, "cors_origin_denied"),
        ({"body_size": 129}, "body_too_large"),
        ({"content_type": "text/html"}, "content_type_denied"),
        ({"http_request_count": 3}, "rate_limited"),
    ],
)
def test_http_policy_failures_are_closed(
    overrides: dict[str, object], expected: str
) -> None:
    decision = evaluate_production_policy(_config(), _request(**overrides))

    assert decision.outcome is PolicyOutcome.DOMAIN_REJECTION
    assert decision.failure is not None
    assert decision.failure.code == expected


def test_provider_deny_and_limits_fail_closed() -> None:
    denied = evaluate_production_policy(
        _config(), _request(provider_id="not-allowlisted")
    )
    limited = evaluate_production_policy(
        _config(), _request(provider_request_count=2)
    )
    oversized = evaluate_production_policy(
        _config(), _request(provider_request_payload_bytes=65)
    )

    assert denied.failure is not None and denied.failure.code == "provider_denied"
    assert limited.failure is not None and limited.failure.code == "rate_limited"
    assert oversized.failure is not None
    assert oversized.failure.code == "provider_limits_exceeded"


def test_writer_owner_is_the_single_declared_value() -> None:
    missing = evaluate_production_policy(_config(), _request(canonical_writer_owner=None))
    mismatched = evaluate_production_policy(
        _config(), _request(canonical_writer_owner="legacy-writer")
    )

    assert missing.failure is not None
    assert missing.failure.code == "canonical_writer_owner_missing"
    assert mismatched.failure is not None
    assert mismatched.failure.code == "canonical_writer_owner_mismatch"


def test_runtime_and_unclassified_defects_are_separate_outcomes() -> None:
    timeout = classify_runtime_exception(TimeoutError("provider timeout"))
    connection = classify_runtime_exception(ConnectionError("unreachable"))
    defect = classify_runtime_exception(ValueError("not classified"))

    assert timeout.outcome is PolicyOutcome.CLASSIFIED_RUNTIME_FAILURE
    assert timeout.authority is False
    assert timeout.failure is not None and timeout.failure.code == "provider_timeout"
    assert connection.outcome is PolicyOutcome.CLASSIFIED_RUNTIME_FAILURE
    assert defect.outcome is PolicyOutcome.UNCLASSIFIED_DEFECT
    assert defect.failure is not None and defect.failure.code == "unclassified_defect"


def test_failure_family_is_closed_and_decisions_are_immutable() -> None:
    decision = evaluate_production_policy(_config(), _request())
    valid_code = production_policy_failures.codes

    assert isinstance(decision, PolicyDecision)
    assert all(isinstance(code, str) for code in valid_code)
    with pytest.raises(FrozenInstanceError):
        decision.authority = True  # type: ignore[misc]
