from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import TYPE_CHECKING, Any, Literal, Mapping

from functorial_kit import Failure
from mrw_functorial_kit.core.agent_service_semantics import agent_runtime_failures

from .contracts import (
    AgentCoreRequest,
    CoreToolCall,
    CoreToolSpec,
    ToolPermission,
    json_object,
)
from app.services.request_identity import RequestActorContext

if TYPE_CHECKING:
    from app.services.agent_sessions.service import AgentSessionService


HOST_AUTHORIZATION_CONTRACT_VERSION = "agent_core.host_authorization.v1"
HOST_APPROVAL_TTL = timedelta(minutes=15)


@dataclass(frozen=True)
class TrustedHostContext:
    project_key: str
    session_id: str
    host_thread_id: str
    turn_id: str
    user_message_id: str
    actor_context: RequestActorContext | None = None


@dataclass(frozen=True)
class VerifiedHostAuthorization:
    context: TrustedHostContext
    tool_name: str
    arguments_sha256: str
    package_digest: str | None
    permission: ToolPermission
    approval_id: str | None
    origin_call_id: str
    origin_turn_id: str
    origin_user_message_id: str
    execution_call_id: str = ""

    @property
    def actor_context(self) -> RequestActorContext | None:
        return self.context.actor_context


@dataclass(frozen=True)
class HostAuthorizationDecision:
    status: Literal["authorized", "needs_approval"]
    authorization: VerifiedHostAuthorization | None = None
    approval: dict[str, Any] | None = None


_verified_host_authorization: ContextVar[VerifiedHostAuthorization | None] = ContextVar(
    "agent_core_verified_host_authorization",
    default=None,
)


def canonical_arguments_sha256(canonical_arguments: Mapping[str, Any]) -> str | Failure:
    try:
        body = json.dumps(
            dict(canonical_arguments or {}),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        return _failure("canonical_arguments_invalid", f"canonical arguments are not JSON-serializable: {exc}")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def host_action_binding(
    context: TrustedHostContext,
    spec: CoreToolSpec,
    *,
    arguments_sha256: str,
    package_digest: str | None,
    originating_call_id: str | None = None,
) -> dict[str, Any] | Failure:
    context_failure = validate_context(context)
    if isinstance(context_failure, Failure):
        return context_failure
    normalized_package_digest = _normalize_package_digest(package_digest)
    if isinstance(normalized_package_digest, Failure):
        return normalized_package_digest
    if not _is_sha256(arguments_sha256):
        return _failure("arguments_digest_invalid", "arguments_sha256 must be a SHA-256 hex digest")
    origin_call_id = str(originating_call_id or "").strip()
    if not origin_call_id:
        return _failure("originating_call_id_required", "originating tool call_id is required")
    return {
        "contract_version": HOST_AUTHORIZATION_CONTRACT_VERSION,
        "project_key": context.project_key,
        "session_id": context.session_id,
        "host_thread_id": context.host_thread_id,
        "origin_call_id": origin_call_id,
        "origin_turn_id": context.turn_id,
        "origin_user_message_id": context.user_message_id,
        "tool_name": spec.name,
        "tool_permission": spec.permission,
        "tool_risk": spec.risk,
        "arguments_sha256": arguments_sha256,
        "package_digest": normalized_package_digest,
    }


def authorize_tool_call(
    service: AgentSessionService,
    context: TrustedHostContext,
    spec: object,
    canonical_arguments: Mapping[str, Any],
    package_digest: str | None = None,
    *,
    originating_call_id: str | None = None,
) -> HostAuthorizationDecision | Failure:
    if not isinstance(spec, CoreToolSpec):
        return _failure("tool_spec_invalid", "tool spec must be a registered CoreToolSpec")
    arguments_sha256 = canonical_arguments_sha256(canonical_arguments)
    if isinstance(arguments_sha256, Failure):
        return arguments_sha256
    binding = host_action_binding(
        context,
        spec,
        arguments_sha256=arguments_sha256,
        package_digest=package_digest,
        originating_call_id=originating_call_id,
    )
    if isinstance(binding, Failure):
        return binding
    scope_failure = _validate_session_scope(service, context)
    if isinstance(scope_failure, Failure):
        return scope_failure

    if spec.permission == "deny":
        return _failure("tool_permission_denied", f"tool {spec.name} is denied by CoreToolSpec.permission")
    if spec.permission == "allow":
        provenance_failure = _validate_request_host_message(service, context)
        if isinstance(provenance_failure, Failure):
            return provenance_failure
        return HostAuthorizationDecision(
            status="authorized",
            authorization=VerifiedHostAuthorization(
                context=context,
                tool_name=spec.name,
                arguments_sha256=arguments_sha256,
                package_digest=_normalize_optional_text(package_digest),
                permission=spec.permission,
                approval_id=None,
                origin_call_id=str(originating_call_id or ""),
                origin_turn_id=context.turn_id,
                origin_user_message_id=context.user_message_id,
                execution_call_id=str(originating_call_id or ""),
            ),
        )
    if spec.permission not in {"ask", "explicit_user_request"}:
        return _failure("tool_permission_unsupported", f"unsupported tool permission: {spec.permission}")

    approvals = service.list_approvals(session_id=context.session_id)
    if isinstance(approvals, Failure):
        return approvals
    action_identity = _action_identity(binding)
    matching = [
        item
        for item in approvals
        if _action_identity(dict(item.get("binding_payload") or {})) == action_identity
    ]
    consumed = next((item for item in matching if item.get("status") == "consumed"), None)
    if consumed is not None:
        return _failure(
            "host_approval_grant_consumed",
            "this host approval grant has already been used",
            approval_id=consumed.get("approval_id"),
        )

    if not matching:
        approval_id = f"host-approval-{hashlib.sha256(json.dumps(binding, sort_keys=True).encode('utf-8')).hexdigest()[:24]}"
        approval = service.create_or_update_approval(
            approval_id=approval_id,
            binding_payload=binding,
            requester_session_id=context.session_id,
            requester_task_id=None,
            requester_actor=f"trusted_host:{context.host_thread_id}",
            expires_at=datetime.now(timezone.utc) + HOST_APPROVAL_TTL,
            status="pending",
            metadata={"contract_version": HOST_AUTHORIZATION_CONTRACT_VERSION},
            audit_log=[{"action": "requested", "actor": "agent_core.host_authorization"}],
        )
        if isinstance(approval, Failure):
            return approval
        return HostAuthorizationDecision(status="needs_approval", approval=approval)

    approved = [item for item in matching if item.get("status") == "approved"]
    rejected = next((item for item in matching if item.get("status") == "failed"), None)
    if rejected is not None:
        return _failure("host_approval_rejected", "host approval was rejected", approval_id=rejected.get("approval_id"))
    pending = [item for item in matching if item.get("status") == "pending"]
    if pending:
        expiry_failure = _validate_expiry(pending[0])
        if isinstance(expiry_failure, Failure):
            return expiry_failure
        return HostAuthorizationDecision(status="needs_approval", approval=pending[0])
    if not approved:
        return _failure("host_approval_status_invalid", "host approval has an invalid status")
    validated = validate_host_authorization(
        service,
        context,
        approval_id=str(approved[0].get("approval_id") or ""),
        tool_name=spec.name,
        arguments_sha256=arguments_sha256,
        package_digest=package_digest,
        originating_call_id=originating_call_id,
        consume=True,
    )
    if isinstance(validated, Failure):
        return validated
    return HostAuthorizationDecision(status="authorized", authorization=validated)


def validate_host_authorization(
    service: AgentSessionService,
    context: TrustedHostContext,
    *,
    approval_id: str,
    tool_name: str,
    arguments_sha256: str,
    package_digest: str | None = None,
    originating_call_id: str | None = None,
    execution_call_id: str | None = None,
    consume: bool = False,
) -> VerifiedHostAuthorization | Failure:
    normalized_approval_id = str(approval_id or "").strip()
    if not normalized_approval_id:
        return _failure("approval_id_required", "approval_id is required")
    approval = service.store.get_approval(normalized_approval_id)
    if isinstance(approval, Failure):
        return approval
    binding = json_object(approval.get("binding_payload") or {})
    if binding.get("contract_version") != HOST_AUTHORIZATION_CONTRACT_VERSION:
        return _failure("host_approval_contract_invalid", "approval does not use the host authorization contract")
    resolved_execution_call_id = (
        str(execution_call_id or "").strip()
        or str(originating_call_id or "").strip()
        or str(binding.get("origin_call_id") or "")
    )
    expected = {
        "project_key": context.project_key,
        "session_id": context.session_id,
        "host_thread_id": context.host_thread_id,
        "tool_name": tool_name,
        "arguments_sha256": arguments_sha256,
        "package_digest": _normalize_optional_text(package_digest),
    }
    origin_context = TrustedHostContext(
        project_key=context.project_key,
        session_id=context.session_id,
        host_thread_id=context.host_thread_id,
        turn_id=str(binding.get("origin_turn_id") or ""),
        user_message_id=str(binding.get("origin_user_message_id") or ""),
    )
    origin_message_failure = _validate_host_message(service, origin_context, approval_id=None)
    if isinstance(origin_message_failure, Failure):
        return origin_message_failure
    for key, value in expected.items():
        if binding.get(key) != value:
            return _failure(
                "host_approval_binding_mismatch",
                f"host approval binding mismatch for {key}",
                field=key,
                approval_id=normalized_approval_id,
            )
    status = str(approval.get("status") or "")
    if status == "failed":
        return _failure("host_approval_rejected", "host approval was rejected", approval_id=normalized_approval_id)
    if status == "consumed":
        return _failure("host_approval_grant_consumed", "host approval grant was already used", approval_id=normalized_approval_id)
    if status != "approved":
        return _failure("host_approval_pending", "host approval is not approved", approval_id=normalized_approval_id)
    expiry_failure = _validate_expiry(approval)
    if isinstance(expiry_failure, Failure):
        return expiry_failure
    provenance_failure = _validate_request_host_message(service, context)
    if isinstance(provenance_failure, Failure):
        return provenance_failure
    metadata = json_object(approval.get("metadata") or {})
    confirmation = json_object(metadata.get("host_confirmation") or {})
    confirmation_message_id = str(confirmation.get("user_message_id") or "")
    if not confirmation_message_id:
        return _failure("host_confirmation_missing", "approved host action has no trusted user confirmation", approval_id=normalized_approval_id)
    confirmation_context = TrustedHostContext(
        project_key=context.project_key,
        session_id=context.session_id,
        host_thread_id=str(confirmation.get("host_thread_id") or ""),
        turn_id=str(confirmation.get("turn_id") or ""),
        user_message_id=confirmation_message_id,
    )
    confirmation_failure = _validate_host_message(service, confirmation_context, approval_id=normalized_approval_id)
    if isinstance(confirmation_failure, Failure):
        return confirmation_failure
    if (
        confirmation_context.turn_id != context.turn_id
        or confirmation_context.user_message_id != context.user_message_id
    ):
        return _failure(
            "host_continuation_mismatch",
            "host approval continuation turn does not match the confirming host input",
            approval_id=normalized_approval_id,
        )

    if consume:
        consumed = service.store.consume_host_approval(
            approval_id=normalized_approval_id,
            expected_binding_payload=binding,
            consumed_metadata={
                "grant_consumed_at": datetime.now(timezone.utc).isoformat(),
                "execution_call_id": resolved_execution_call_id,
            },
            consumed_audit_log=[{"action": "grant_consumed", "actor": "agent_core.host_authorization"}],
        )
        if isinstance(consumed, Failure):
            return _consume_failure(consumed)
    permission = _tool_permission(binding)
    if isinstance(permission, Failure):
        return _failure(
            "host_approval_binding_mismatch",
            "host approval has an unsupported tool permission",
            field="tool_permission",
            approval_id=normalized_approval_id,
        )
    return VerifiedHostAuthorization(
        context=context,
        tool_name=tool_name,
        arguments_sha256=arguments_sha256,
        package_digest=_normalize_optional_text(package_digest),
        permission=permission,
        approval_id=normalized_approval_id,
        origin_call_id=str(binding.get("origin_call_id") or ""),
        origin_turn_id=origin_context.turn_id,
        origin_user_message_id=origin_context.user_message_id,
        execution_call_id=resolved_execution_call_id,
    )


def validate_verified_host_authorization(
    authorization: VerifiedHostAuthorization,
    context: TrustedHostContext,
    spec: CoreToolSpec,
    canonical_arguments: Mapping[str, Any],
    package_digest: str | None = None,
) -> VerifiedHostAuthorization | Failure:
    """Validate an already consumed in-flight grant without consuming it again."""

    arguments_sha256 = canonical_arguments_sha256(canonical_arguments)
    if isinstance(arguments_sha256, Failure):
        return arguments_sha256
    if authorization.context != context:
        return _failure("host_authorization_context_mismatch", "verified host authorization context does not match")
    if (
        authorization.tool_name != spec.name
        or authorization.arguments_sha256 != arguments_sha256
        or authorization.package_digest != _normalize_optional_text(package_digest)
        or authorization.permission != spec.permission
    ):
        return _failure("host_authorization_action_mismatch", "verified host authorization action does not match")
    return authorization


def validate_execution_scope(
    context: TrustedHostContext,
    request: AgentCoreRequest,
    tool_call: CoreToolCall,
) -> None | Failure:
    """Ensure the actual execution scope equals the trusted host context.

    Only the selectors that genuinely drive the execution target are checked:
    the request scope, the top-level ``arguments.project_key`` selector, and
    the nested ``arguments.ingest_payload.project_key`` selector for the
    ``ingest.url_pool.submit`` tool. Data labels inside metadata/provenance/
    skill payloads are intentionally ignored so ordinary same-name fields are
    not promoted to scope.
    """
    for field in ("project_key", "session_id", "turn_id"):
        request_value = str(getattr(request, field, None) or "").strip()
        context_value = str(getattr(context, field, None) or "").strip()
        if request_value != context_value:
            return _failure(
                "host_execution_scope_mismatch",
                f"request {field} does not match the trusted host context",
                field=f"request.{field}",
                request_value=request_value,
                context_value=context_value,
            )

    arguments = dict(tool_call.arguments or {})
    top_project_key = arguments.get("project_key")
    if top_project_key is not None and str(top_project_key).strip():
        if str(top_project_key).strip() != context.project_key:
            return _failure(
                "host_execution_scope_mismatch",
                "tool arguments project_key does not match the trusted host context",
                field="arguments.project_key",
                request_value=str(top_project_key).strip(),
                context_value=context.project_key,
            )

    ingest_payload = arguments.get("ingest_payload")
    if tool_call.tool_name == "ingest.url_pool.submit" and isinstance(ingest_payload, dict):
        nested_project_key = ingest_payload.get("project_key")
        if nested_project_key is not None and str(nested_project_key).strip():
            if str(nested_project_key).strip() != context.project_key:
                return _failure(
                    "host_execution_scope_mismatch",
                    "tool ingest_payload project_key does not match the trusted host context",
                    field="arguments.ingest_payload.project_key",
                    request_value=str(nested_project_key).strip(),
                    context_value=context.project_key,
                )

    return None


def current_verified_host_authorization() -> VerifiedHostAuthorization | None:
    return _verified_host_authorization.get()


@contextmanager
def verified_host_authorization_channel(authorization: VerifiedHostAuthorization):
    token = _verified_host_authorization.set(authorization)
    try:
        yield authorization
    finally:
        _verified_host_authorization.reset(token)


def _consume_failure(failure: Failure) -> Failure:
    context = dict(failure.context or {})
    host_code = str(context.get("host_code") or "")
    status = str(context.get("status") or "")
    approval_id = context.get("approval_id")
    if failure.code == "approval_not_found":
        return _failure("host_approval_missing", failure.message, approval_id=approval_id)
    if host_code == "host_approval_binding_mismatch":
        return _failure("host_approval_binding_mismatch", failure.message, approval_id=approval_id)
    if host_code == "host_approval_grant_consumed" or status == "consumed":
        return _failure("host_approval_grant_consumed", failure.message, approval_id=approval_id)
    if host_code == "host_approval_rejected" or status == "failed":
        return _failure("host_approval_rejected", failure.message, approval_id=approval_id)
    return _failure("host_approval_pending", failure.message, approval_id=approval_id)


def validate_context(context: TrustedHostContext) -> None | Failure:
    for field in ("project_key", "session_id", "host_thread_id", "turn_id", "user_message_id"):
        if not str(getattr(context, field) or "").strip():
            return _failure("host_context_invalid", f"trusted host context field is required: {field}", field=field)
    if context.actor_context is not None and (
        not context.actor_context.actor_trusted or not context.actor_context.actor_id
    ):
        return _failure("host_actor_untrusted", "host actor must come from the authenticated request context")
    return None


_ACTION_IDENTITY_KEYS = (
    "contract_version",
    "project_key",
    "session_id",
    "host_thread_id",
    "tool_name",
    "tool_permission",
    "tool_risk",
    "arguments_sha256",
    "package_digest",
    "origin_call_id",
)


def _action_identity(binding: Mapping[str, Any]) -> dict[str, Any]:
    return {key: binding.get(key) for key in _ACTION_IDENTITY_KEYS}


def _validate_session_scope(service: AgentSessionService, context: TrustedHostContext) -> None | Failure:
    session = service.store.get_session(context.session_id)
    if isinstance(session, Failure):
        return session
    project_key = str(session.get("project_key") or "")
    if project_key != context.project_key:
        return _failure(
            "host_context_project_mismatch",
            "trusted host context project does not match the session",
            context_project_key=context.project_key,
            session_project_key=project_key,
        )
    return None


def _validate_request_host_message(service: AgentSessionService, context: TrustedHostContext) -> None | Failure:
    return _validate_host_message(service, context, approval_id=None)


def _validate_host_message(
    service: AgentSessionService,
    context: TrustedHostContext,
    *,
    approval_id: str | None,
) -> None | Failure:
    messages = service.list_messages(context.session_id)
    if isinstance(messages, Failure):
        return messages
    actor = f"trusted_host:{context.host_thread_id}"
    for message in messages:
        metadata = dict(message.get("metadata") or {})
        host_message = dict(metadata.get("host_message") or {})
        host_confirmation = dict(metadata.get("host_confirmation") or {})
        matches_message = (
            str(message.get("role") or "") == "user"
            and str(message.get("actor") or "") == actor
            and str(host_message.get("user_message_id") or "") == context.user_message_id
            and str(host_message.get("host_thread_id") or "") == context.host_thread_id
            and str(host_message.get("turn_id") or "") == context.turn_id
        )
        if approval_id is None:
            if matches_message:
                return None
        elif matches_message and str(host_confirmation.get("approval_id") or "") == approval_id:
            return None
    if approval_id is None:
        return _failure("host_request_message_missing", "trusted host request message was not found")
    return _failure("host_confirmation_message_missing", "trusted host confirmation message was not found", approval_id=approval_id)


def _validate_expiry(approval: Mapping[str, object]) -> None | Failure:
    value = approval.get("expires_at")
    if value is None:
        return None
    try:
        expires_at = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except ValueError:
        return _failure("host_approval_expiry_invalid", "host approval expiry is invalid")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        return _failure("host_approval_expired", "host approval has expired", expires_at=value)
    return None


def _normalize_package_digest(package_digest: str | None) -> str | None | Failure:
    value = _normalize_optional_text(package_digest)
    if value is None:
        return None
    if not _is_sha256(value):
        return _failure("package_digest_invalid", "package_digest must be a SHA-256 hex digest")
    return value


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _tool_permission(binding: Mapping[str, object]) -> ToolPermission | Failure:
    value = str(binding.get("tool_permission") or "ask")
    if value == "allow":
        return "allow"
    if value == "ask":
        return "ask"
    if value == "deny":
        return "deny"
    if value == "explicit_user_request":
        return "explicit_user_request"
    return _failure("host_approval_binding_mismatch", "host approval has an unsupported tool permission")


def _is_sha256(value: str) -> bool:
    try:
        return len(value) == 64 and int(value, 16) >= 0
    except ValueError:
        return False


def _failure(code: str, message: str, **context: Any) -> Failure:
    # The shared family is closed; preserve the precise message/context while
    # lowering new host-authorization outcomes onto its existing vocabulary.
    if code == "approval_id_required":
        family_code = code
    elif code in {
        "host_context_project_mismatch",
        "host_execution_scope_mismatch",
        "session_project_mismatch",
    }:
        family_code = "session_project_mismatch"
    elif code in {
        "canonical_arguments_invalid",
        "arguments_digest_invalid",
        "host_context_invalid",
        "package_digest_invalid",
        "host_request_message_missing",
        "host_confirmation_message_missing",
    }:
        family_code = "capability_input_missing"
    else:
        family_code = "writing_operation_unsupported"
    detailed_context = {**context, "host_code": code}
    return agent_runtime_failures.fail(family_code, message, detailed_context)
