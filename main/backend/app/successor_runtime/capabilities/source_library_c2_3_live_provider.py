"""Live Serper adapter for the C2.3 provider-effect ports.

Credential resolution and receipts stay redacted.  The adapter supports only
synchronous Serper search execution and exposes no async job readback.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from app.successor_runtime.capabilities import source_library_c2_shared as shared
from app.successor_runtime.capabilities.checksum import content_digest

SERPER_ENDPOINT = "https://google.serper.dev/search"
ENV_VAR_NAME = "SERPER_API_KEY"
LIVE_PROVIDER = "serper"

_GRANT_SCOPE = "project"
_REDACTION_PROFILE = "credential-ref-only"
_LEASE_SECONDS = 300
_MAX_RECORD_REFS = 5
_DEFAULT_LIMIT = 5

__all__ = [
    "ENV_VAR_NAME",
    "LIVE_PROVIDER",
    "SERPER_ENDPOINT",
    "SerperLiveCredentialResolverPort",
    "SerperLiveEffectPort",
    "SerperLiveProviderEffectGateway",
    "SerperLiveReadbackPort",
    "SerperOutcomeUnknownError",
    "build_serper_live_gateway",
    "serper_authority_digest",
]


def _env_api_key_provider() -> str | None:
    return os.getenv(ENV_VAR_NAME)


def _utc_now_iso_millis(offset_seconds: int = 0) -> str:
    now = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def serper_authority_digest() -> str:
    """Digest binding the live Serper grant to the frozen C2.3 authority."""

    return content_digest(
        {
            "schema": "mrw.successor.source-library.c2-3.live-authority.v1",
            "canonical_owner": "source_library.c2_3.v1",
            "provider": LIVE_PROVIDER,
            "grant_scope": _GRANT_SCOPE,
            "redaction": _REDACTION_PROFILE,
        }
    )


def _rejection(
    ref: shared.CredentialRef,
    *,
    code: str,
    decision: str,
    message: str,
) -> shared.RedactedCredentialRejection:
    return shared.RedactedCredentialRejection(
        code=code,
        credential_ref=ref.ref,
        message=message,
        credential_decision_receipt=shared.CredentialDecisionReceipt(
            decision=decision,
            credential_refs=(ref.ref,),
            redacted_profile={
                "provider": ref.provider,
                "grant_scope": ref.grant_scope,
                "redaction": _REDACTION_PROFILE,
            },
        ),
    )


class SerperLiveCredentialResolverPort:
    """Resolve an opaque Serper credential ref without exposing the key."""

    def __init__(
        self,
        api_key_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self._api_key_provider = api_key_provider or _env_api_key_provider
        self.resolves: list[str] = []

    def resolve(
        self,
        ref: shared.CredentialRef,
        authorization: Any,
    ) -> shared.EphemeralCredentialLease | shared.RedactedCredentialRejection:
        self.resolves.append(ref.ref)
        if ref.provider != LIVE_PROVIDER:
            return _rejection(
                ref,
                code="UNAUTHORIZED",
                decision="UNAUTHORIZED",
                message="credential ref is not bound to the serper provider",
            )
        if not isinstance(ref.grant_scope, str) or not ref.grant_scope.strip():
            return _rejection(
                ref,
                code="UNAUTHORIZED",
                decision="UNAUTHORIZED",
                message="serper credential grant scope is required",
            )
        if isinstance(authorization, Mapping):
            if "authority_digest" in authorization and (
                authorization["authority_digest"] != serper_authority_digest()
            ):
                return _rejection(
                    ref,
                    code="UNAUTHORIZED",
                    decision="UNAUTHORIZED",
                    message="authority digest does not bind the serper grant",
                )
            if "grant_scope" in authorization and (
                authorization["grant_scope"] != ref.grant_scope
            ):
                return _rejection(
                    ref,
                    code="UNAUTHORIZED",
                    decision="UNAUTHORIZED",
                    message="authorization grant scope does not match credential ref",
                )
            if "provider" in authorization and (
                authorization["provider"] != ref.provider
            ):
                return _rejection(
                    ref,
                    code="UNAUTHORIZED",
                    decision="UNAUTHORIZED",
                    message="authorization provider does not match credential ref",
                )
        key = self._api_key_provider()
        if key is None or not str(key).strip():
            return _rejection(
                ref,
                code="MISSING_CREDENTIAL" if ref.required else "UNAUTHORIZED",
                decision="MISSING" if ref.required else "UNAUTHORIZED",
                message="serper API key is not configured for this project",
            )
        lease_id = (
            "lease:serper:"
            + content_digest({"credential_ref": ref.ref, "provider": ref.provider})[:24]
        )
        return shared.EphemeralCredentialLease(
            lease_id=lease_id,
            credential_ref=ref.ref,
            provider=ref.provider,
            expires_at=_utc_now_iso_millis(offset_seconds=_LEASE_SECONDS),
            credential_decision_receipt=shared.CredentialDecisionReceipt(
                decision="RESOLVED",
                credential_refs=(ref.ref,),
                redacted_profile={
                    "provider": ref.provider,
                    "grant_scope": ref.grant_scope,
                    "redaction": _REDACTION_PROFILE,
                },
            ),
        )


class SerperOutcomeUnknownError(Exception):
    """Transport-level marker for a provider outcome that cannot be typed."""


def _default_serper_transport(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: int,
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            if not isinstance(parsed, dict):
                raise TypeError("serper response must be a JSON object")
            return int(response.status), parsed
    except urllib.error.HTTPError as exc:
        try:
            parsed = json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - HTTP error bodies are best-effort
            parsed = {}
        return int(exc.code), parsed


def _frozen_payload_values(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)
    return dict(payload)


def _serper_query(payload: Any) -> str:
    values = _frozen_payload_values(payload)
    query_term = values.get("query_term")
    if isinstance(query_term, str) and query_term.strip():
        return query_term.strip()
    query_terms = values.get("query_terms")
    if isinstance(query_terms, (list, tuple)):
        for term in query_terms:
            if isinstance(term, str) and term.strip():
                return term.strip()
    return ""


def _serper_limit(payload: Any) -> int:
    values = _frozen_payload_values(payload)
    raw = values.get("limit", values.get("ingest_limit", _DEFAULT_LIMIT))
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return _DEFAULT_LIMIT


def _attempt_ref(
    request: shared.ProviderEffectRequest,
) -> shared.ProviderAttemptRef:
    return shared.ProviderAttemptRef(
        attempt_id=f"attempt:serper:{request.request_id}",
        request_digest=request.request_digest,
        provider=LIVE_PROVIDER,
    )


def _record_digest(title: str, link: str, snippet: str) -> str:
    return content_digest({"title": title, "link": link, "snippet": snippet})


def _record_refs(
    request: shared.ProviderEffectRequest,
    organic: list[Any],
) -> tuple[shared.CapturedSourceRecordRef, ...]:
    limit = min(
        max(_serper_limit(_frozen_payload_values(request.effect_payload)), 0),
        _MAX_RECORD_REFS,
    )
    records: list[shared.CapturedSourceRecordRef] = []
    for index, item in enumerate(organic):
        if len(records) >= limit:
            break
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or "").strip()
        snippet = str(item.get("snippet") or item.get("description") or "").strip()
        records.append(
            shared.CapturedSourceRecordRef(
                record_id=f"record:serper:{request.request_id}:{index}",
                content_ref=f"content:serper:{request.request_id}:{index}",
                content_digest=_record_digest(title, link, snippet),
                source_ref=link or f"source:serper:{request.request_id}:{index}",
            )
        )
    return tuple(records)


class SerperLiveEffectPort:
    """Execute one synchronous Serper search through an injected transport."""

    def __init__(
        self,
        api_key_provider: Callable[[], str | None] | None = None,
        transport: Callable[..., tuple[int, dict[str, Any]]] | None = None,
        timeout_seconds: int = 30,
        observed_at_provider: str | None = None,
    ) -> None:
        self._api_key_provider = api_key_provider or _env_api_key_provider
        self.transport = transport or _default_serper_transport
        self.timeout_seconds = timeout_seconds
        self.observed_at_provider = observed_at_provider or _utc_now_iso_millis()
        self.provider_calls: list[str] = []
        self.cancel_calls: list[str] = []
        self.real_provider_calls = 0

    def execute(
        self,
        request: shared.ProviderEffectRequest,
        ephemeral_credentials: tuple[shared.EphemeralCredentialLease, ...],
    ) -> shared.ProviderEffectOutcome:
        key = self._api_key_provider()
        if key is None or not str(key).strip():
            return shared.RejectedProviderEffect(
                code="MISSING_CREDENTIAL",
                message="serper API key is not configured for this request",
            )
        if request.provider != LIVE_PROVIDER:
            return shared.RejectedProviderEffect(
                code="UNSUPPORTED_PROVIDER",
                message="serper live adapter only executes serper provider requests",
            )
        query = _serper_query(request.effect_payload)
        if not query:
            return shared.RejectedProviderEffect(
                code="INVALID_PARAMS",
                message="serper search request requires one query term",
            )
        attempt = _attempt_ref(request)
        self.provider_calls.append(request.request_id)
        limit = _serper_limit(request.effect_payload)
        payload: dict[str, Any] = {"q": query, "num": max(1, limit)}
        headers = {
            "X-API-KEY": str(key),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            status, body = self.transport(
                SERPER_ENDPOINT,
                payload,
                headers,
                self.timeout_seconds,
            )
        except SerperOutcomeUnknownError:
            self.real_provider_calls += 1
            return shared.OutcomeUnknownProviderEffect(
                attempt_ref=attempt.as_ref_string(),
                reason="serper transport left the attempt outcome unknown",
            )
        except TimeoutError:
            self.real_provider_calls += 1
            return shared.FailedProviderEffect(
                code="TIMEOUT",
                message="serper transport timed out",
            )
        except urllib.error.URLError as exc:
            self.real_provider_calls += 1
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                return shared.FailedProviderEffect(
                    code="TIMEOUT",
                    message="serper transport timed out",
                )
            return shared.FailedProviderEffect(
                code="TRANSPORT",
                message="serper transport request failed",
            )
        except Exception:  # noqa: BLE001 - any transport failure stays typed
            self.real_provider_calls += 1
            return shared.FailedProviderEffect(
                code="TRANSPORT",
                message="serper transport request failed",
            )
        else:
            self.real_provider_calls += 1
        if status == 200 and isinstance(body, dict):
            organic = body.get("organic")
            if organic is None or not isinstance(organic, list):
                organic = []
            return shared.CompletedProviderEffect(
                receipt=shared.ProviderReceipt(
                    receipt_id=f"receipt:serper:{request.request_id}",
                    provider=LIVE_PROVIDER,
                    provider_job_id=None,
                    provider_status="COMPLETED",
                    attempt_ref=attempt.as_ref_string(),
                    observed_at=self.observed_at_provider,
                ),
                record_refs=_record_refs(request, organic),
                staged_artifact_refs=(),
            )
        if status == 429:
            return shared.FailedProviderEffect(
                code="RATE_LIMIT",
                message="serper API rate limit exceeded",
                retryable=True,
            )
        if status in (401, 403):
            return shared.FailedProviderEffect(
                code="PROVIDER_REJECTED",
                message="serper API rejected the request credentials",
            )
        if 400 <= status < 500:
            return shared.FailedProviderEffect(
                code="PROVIDER_REJECTED",
                message="serper API rejected the request",
            )
        return shared.FailedProviderEffect(
            code="TRANSPORT",
            message="serper transport returned an error status",
        )

    def cancel(
        self,
        attempt_ref: shared.ProviderAttemptRef,
        request: shared.ProviderEffectRequest,
    ) -> shared.CancelReceipt:
        self.cancel_calls.append(request.request_id)
        return shared.CancelReceipt(
            cancel_receipt_id=f"cancel:serper:{request.request_id}",
            attempt_ref=attempt_ref.as_ref_string(),
            request_digest=request.request_digest,
            cancel_status="ALREADY_TERMINAL",
        )


class SerperLiveReadbackPort:
    """Honest readback oracle for a provider with no job readback API."""

    def readback(
        self,
        attempt_ref: shared.ProviderAttemptRef,
        request: shared.ProviderEffectRequest,
    ) -> shared.ProviderReadbackResult:
        return shared.ReadbackUnavailable(
            attempt_ref=attempt_ref.as_ref_string(),
            reason="Serper search API has no authoritative job readback; "
            "synchronous terminal only",
        )

    def prove_not_started(
        self,
        attempt_ref: shared.ProviderAttemptRef,
        request: shared.ProviderEffectRequest,
    ) -> shared.NonStartProof | shared.NonStartUnprovable:
        return shared.NonStartUnprovable(
            attempt_ref=attempt_ref.as_ref_string(),
            reason="Serper API exposes no non-start oracle",
        )


class SerperLiveProviderEffectGateway:
    """Combined live Serper gateway mirroring the fixture gateway shape."""

    def __init__(
        self,
        *,
        credentials: SerperLiveCredentialResolverPort,
        effect: SerperLiveEffectPort,
        readback: SerperLiveReadbackPort,
    ) -> None:
        self.credentials = credentials
        self.effect = effect
        self.readback = readback

    @property
    def provider_calls(self) -> list[str]:
        return self.effect.provider_calls

    def execute(
        self,
        request: shared.ProviderEffectRequest,
        authorization: Any = None,
    ) -> shared.ProviderEffectOutcome:
        leases: list[shared.EphemeralCredentialLease] = []
        for ref in request.credential_refs:
            resolved = self.credentials.resolve(ref, authorization)
            if isinstance(resolved, shared.RedactedCredentialRejection):
                return shared.RejectedProviderEffect(
                    code=resolved.code,
                    message=resolved.message,
                )
            leases.append(resolved)
        return self.effect.execute(request, tuple(leases))

    def readback_attempt(
        self,
        attempt_ref: shared.ProviderAttemptRef,
        request: shared.ProviderEffectRequest,
    ) -> shared.ProviderReadbackResult:
        return self.readback.readback(attempt_ref, request)

    def cancel(
        self,
        attempt_ref: shared.ProviderAttemptRef,
        request: shared.ProviderEffectRequest,
    ) -> shared.CancelReceipt:
        return self.effect.cancel(attempt_ref, request)

    def prove_not_started(
        self,
        attempt_ref: shared.ProviderAttemptRef,
        request: shared.ProviderEffectRequest,
    ) -> shared.NonStartProof | shared.NonStartUnprovable:
        return self.readback.prove_not_started(attempt_ref, request)


def build_serper_live_gateway(
    *,
    api_key_provider: Callable[[], str | None] | None = None,
    transport: Callable[..., tuple[int, dict[str, Any]]] | None = None,
) -> SerperLiveProviderEffectGateway | None:
    key_provider = api_key_provider or _env_api_key_provider
    configured_key = key_provider()
    if configured_key is None or not str(configured_key).strip():
        return None
    return SerperLiveProviderEffectGateway(
        credentials=SerperLiveCredentialResolverPort(api_key_provider=key_provider),
        effect=SerperLiveEffectPort(
            api_key_provider=key_provider,
            transport=transport,
        ),
        readback=SerperLiveReadbackPort(),
    )
