from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping, NoReturn

from fastapi import HTTPException, Request
from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import request_identity_failures


LEGACY_ACTOR_HEADERS = ("X-Actor-Id", "X-User-Id", "X-User-Email", "X-Request-Actor")

_REQUEST_IDENTITY_FAILURE_WITNESS = "test:test_w01_project_identity_failures"
_REQUEST_IDENTITY_FAILURE_CONTEXT_KEYS = frozenset(
    {
        "boundary_class",
        "failure_family",
        "operation",
        "owner",
        "public_detail",
        "public_exception",
        "public_message",
        "site",
        "status_code",
        "witness",
    }
)


def _identity_failure(
    code: str,
    message: str,
    *,
    operation: str,
    site: str,
    public_detail: Mapping[str, Any],
) -> Failure:
    context: dict[str, Any] = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": request_identity_failures.name,
        "operation": operation,
        "owner": site,
        "public_detail": dict(public_detail),
        "public_exception": "HTTPException",
        "public_message": message,
        "site": site,
        "status_code": 403,
        "witness": _REQUEST_IDENTITY_FAILURE_WITNESS,
    }
    return request_identity_failures.fail(code, message, context)


def _raise_identity_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    if (
        not request_identity_failures.matches(failure)
        or _REQUEST_IDENTITY_FAILURE_CONTEXT_KEYS - set(context)
        or context.get("public_exception") != "HTTPException"
        or context.get("status_code") != 403
        or not isinstance(context.get("public_detail"), dict)
    ):
        # kit:boundary owner=request_identity.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w01_request_identity_preserves_http_403_detail_envelope
        raise TypeError("request identity failure lift context is incomplete")
    # kit:boundary owner=request_identity.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=request_identity.failure witness=test:test_w01_request_identity_preserves_http_403_detail_envelope
    raise HTTPException(status_code=403, detail=dict(context["public_detail"]))


@dataclass(frozen=True)
class RequestActorContext:
    actor_id: str
    actor_source: str
    actor_trusted: bool
    actor_auth_mode: str
    legacy_actor_id: str | None = None
    actor_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def identity_source(self) -> str:
        return self.actor_source

    @property
    def auth_mode(self) -> str:
        return self.actor_auth_mode

    def to_observability(self) -> dict[str, Any]:
        payload = {
            "actor_id": self.actor_id,
            "actor_source": self.actor_source,
            "identity_source": self.identity_source,
            "actor_trusted": self.actor_trusted,
            "actor_auth_mode": self.actor_auth_mode,
            "auth_mode": self.auth_mode,
            "legacy_actor_id": self.legacy_actor_id,
        }
        if self.actor_metadata:
            payload["actor_metadata"] = dict(self.actor_metadata)
        return payload


def _clean_text(value: Any, *, max_length: int = 128) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:max_length]


def actor_id_from_secret(prefix: str, value: str) -> str:
    digest = hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]
    clean_prefix = _clean_text(prefix, max_length=48) or "authenticated"
    return f"{clean_prefix}:{digest}"


def legacy_actor_id_from_request(request: Request | None) -> str | None:
    if request is None:
        return None
    for header_name in LEGACY_ACTOR_HEADERS:
        value = _clean_text(request.headers.get(header_name))
        if value:
            return value
    return None


def authenticated_actor_context(
    *,
    actor_id: str,
    source: str,
    auth_mode: str,
    legacy_actor_id: str | None = None,
    actor_metadata: dict[str, Any] | None = None,
) -> RequestActorContext:
    return RequestActorContext(
        actor_id=_clean_text(actor_id) or "anonymous",
        actor_source=_clean_text(source, max_length=64) or "authenticated",
        actor_trusted=True,
        actor_auth_mode=_clean_text(auth_mode, max_length=64) or "authenticated",
        legacy_actor_id=_clean_text(legacy_actor_id),
        actor_metadata=_safe_actor_metadata(actor_metadata),
    )


def _safe_actor_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        clean_key = _clean_text(key, max_length=64)
        if not clean_key:
            continue
        if isinstance(value, bool) or value is None:
            safe[clean_key] = value
        elif isinstance(value, int):
            safe[clean_key] = value
        elif isinstance(value, float):
            safe[clean_key] = value
        elif isinstance(value, str):
            safe[clean_key] = _clean_text(value, max_length=128)
    return safe


def legacy_or_anonymous_actor_context(request: Request | None) -> RequestActorContext:
    legacy_actor_id = legacy_actor_id_from_request(request)
    if legacy_actor_id:
        return RequestActorContext(
            actor_id=legacy_actor_id,
            actor_source="legacy_header",
            actor_trusted=False,
            actor_auth_mode="legacy_header",
            legacy_actor_id=legacy_actor_id,
        )
    return RequestActorContext(
        actor_id="anonymous",
        actor_source="anonymous",
        actor_trusted=False,
        actor_auth_mode="anonymous",
        legacy_actor_id=None,
    )


def set_request_actor_context(request: Request, context: RequestActorContext) -> RequestActorContext:
    request.state.actor_id = context.actor_id
    request.state.actor_source = context.actor_source
    request.state.identity_source = context.identity_source
    request.state.actor_trusted = context.actor_trusted
    request.state.actor_auth_mode = context.actor_auth_mode
    request.state.auth_mode = context.auth_mode
    request.state.legacy_actor_id = context.legacy_actor_id
    request.state.actor_context = context.to_observability()
    return context


def _authenticated_context_from_state(request: Request | None) -> RequestActorContext | None:
    state = getattr(request, "state", None)
    if state is None:
        return None
    legacy_actor_id = legacy_actor_id_from_request(request)
    for attr_name in ("authenticated_actor", "codex_authenticated_actor"):
        raw_actor = getattr(state, attr_name, None)
        if not isinstance(raw_actor, dict):
            continue
        actor_id = _clean_text(
            raw_actor.get("actor_id")
            or raw_actor.get("id")
            or raw_actor.get("subject")
            or raw_actor.get("sub")
        )
        if not actor_id:
            continue
        return authenticated_actor_context(
            actor_id=actor_id,
            source=(
                _clean_text(raw_actor.get("identity_source"), max_length=64)
                or _clean_text(raw_actor.get("actor_source"), max_length=64)
                or _clean_text(raw_actor.get("source"), max_length=64)
                or attr_name
            ),
            auth_mode=(
                _clean_text(raw_actor.get("actor_auth_mode"), max_length=64)
                or _clean_text(raw_actor.get("auth_mode"), max_length=64)
                or _clean_text(raw_actor.get("auth_type"), max_length=64)
                or attr_name
            ),
            legacy_actor_id=legacy_actor_id,
        )
    actor_id = _clean_text(getattr(state, "authenticated_actor_id", None))
    if actor_id:
        return authenticated_actor_context(
            actor_id=actor_id,
            source="authenticated_request_state",
            auth_mode="authenticated_request_state",
            legacy_actor_id=legacy_actor_id,
        )
    return None


def resolve_request_actor_context(request: Request | None) -> RequestActorContext:
    state = getattr(request, "state", None)
    authenticated_context = _authenticated_context_from_state(request)
    if authenticated_context is not None:
        return authenticated_context
    actor_id = _clean_text(getattr(state, "actor_id", None))
    if actor_id:
        state_actor_context = getattr(state, "actor_context", None)
        state_actor_context = state_actor_context if isinstance(state_actor_context, dict) else {}
        legacy_actor_id = (
            _clean_text(state_actor_context.get("legacy_actor_id"))
            or _clean_text(getattr(state, "legacy_actor_id", None))
            or legacy_actor_id_from_request(request)
        )
        return RequestActorContext(
            actor_id=actor_id,
            actor_source=(
                _clean_text(getattr(state, "identity_source", None), max_length=64)
                or _clean_text(getattr(state, "actor_source", None), max_length=64)
                or "request_state"
            ),
            actor_trusted=bool(getattr(state, "actor_trusted", False)),
            actor_auth_mode=(
                _clean_text(getattr(state, "auth_mode", None), max_length=64)
                or _clean_text(getattr(state, "actor_auth_mode", None), max_length=64)
                or "request_state"
            ),
            legacy_actor_id=legacy_actor_id,
            actor_metadata=_safe_actor_metadata(state_actor_context.get("actor_metadata")),
        )
    return legacy_or_anonymous_actor_context(request)


def require_trusted_actor_context(request: Request | None) -> RequestActorContext:
    context = resolve_request_actor_context(request)
    if context.actor_trusted:
        return context
    detail = {
        "message": "trusted actor required",
        "category": "request_identity",
        "reason_code": "trusted_actor_required",
        "next_action": "authenticate_request",
        "actor_context": context.to_observability(),
    }
    _raise_identity_failure(
        _identity_failure(
            "trusted_actor_required",
            "trusted actor required",
            operation="require_trusted_actor_context",
            site="app.services.request_identity.require_trusted_actor_context",
            public_detail=detail,
        )
    )
