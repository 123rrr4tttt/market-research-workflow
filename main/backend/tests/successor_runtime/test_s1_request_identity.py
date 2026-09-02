"""Focused S1 ALL-SM-010 request-identity port tests.

The donor module is never imported or executed.  Donor bytes are represented
only by the path/SHA fixture below and by named semantic observations replayed
through this successor port.
"""

from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

from app.successor_runtime.capabilities.request_identity_port import (
    ACTOR_IDENTITY_ANONYMOUS,
    ACTOR_IDENTITY_AUTHENTICATED,
    ACTOR_IDENTITY_LEGACY_HEADER,
    ANONYMOUS_ACTOR_ID,
    ANONYMOUS_ACTOR_SOURCE,
    LEGACY_ACTOR_SOURCE,
    RequestActorContext,
    TrustedActorRequired,
    actor_id_from_secret,
    authenticated_actor_context,
    request_identity_observation_from_state,
    require_trusted_actor_context,
    resolve_request_actor_context,
)

pytestmark = pytest.mark.unit

# AllLinesDonorByteClosure.v1 fixture: donor is read-only evidence, not code.
DONOR_REQUEST_IDENTITY_PATH = "main/backend/app/services/request_identity.py"
DONOR_REQUEST_IDENTITY_SHA256 = (
    "d9a2f5a125a335d3fcd3ac6e65d83a0a99f5daaabc24d04b1d04f757c5c8cc1d"
)
ACCEPTANCE_TRACE_ID = "ALL-SM-010-S1-request-identity-acceptance.v1"


def _observation(
    state: dict[str, object] | None = None, headers: dict[str, str] | None = None
):
    return request_identity_observation_from_state(state, headers=headers)


def _authority_flags_are_false(context: RequestActorContext) -> bool:
    plain = context.authority.to_plain()
    return (
        plain["live_provider"] is False
        and plain["canonical_write"] is False
        and plain["cutover"] is False
        and plain["external_delivery"] is False
        and plain["authority_transfer"] is False
    )


def test_authenticated_state_actor_overrides_legacy_spoof_header_and_aliases() -> None:
    observation = _observation(
        {
            "authenticated_actor": {
                "actor_id": "authenticated-actor",
                "identity_source": "oauth_session",
                "auth_mode": "oidc_claims",
            }
        },
        headers={"X-Actor-Id": "spoofed-header-actor"},
    )

    context = resolve_request_actor_context(observation)

    assert context.identity_kind == ACTOR_IDENTITY_AUTHENTICATED
    assert context.actor_id == "authenticated-actor"
    assert context.actor_trusted is True
    assert context.identity_source == "oauth_session"
    assert context.actor_source == "oauth_session"
    assert context.auth_mode == "oidc_claims"
    assert context.actor_auth_mode == "oidc_claims"
    assert context.legacy_actor_id == "spoofed-header-actor"
    assert _authority_flags_are_false(context)

    observability = context.to_observability()
    assert observability["identity_source"] == "oauth_session"
    assert observability["actor_source"] == "oauth_session"
    assert observability["auth_mode"] == "oidc_claims"
    assert observability["actor_auth_mode"] == "oidc_claims"
    assert observability["legacy_actor_id"] == "spoofed-header-actor"


def test_codex_authenticated_actor_alias_and_subject_fallback() -> None:
    observation = _observation(
        {
            "codex_authenticated_actor": {
                "id": "codex-auth-subject",
                "source": "codex_session",
                "auth_type": "session_claims",
            }
        }
    )

    context = resolve_request_actor_context(observation)

    assert context.identity_kind == ACTOR_IDENTITY_AUTHENTICATED
    assert context.actor_id == "codex-auth-subject"
    assert context.actor_source == "codex_session"
    assert context.actor_auth_mode == "session_claims"
    assert context.actor_trusted is True


def test_legacy_header_is_untrusted_and_explicitly_labelled() -> None:
    observation = _observation({}, headers={"x-actor-id": "spoofed-header-actor"})

    context = resolve_request_actor_context(observation)

    assert context.identity_kind == ACTOR_IDENTITY_LEGACY_HEADER
    assert context.actor_id == "spoofed-header-actor"
    assert context.actor_source == LEGACY_ACTOR_SOURCE
    assert context.actor_auth_mode == LEGACY_ACTOR_SOURCE
    assert context.actor_trusted is False
    assert context.legacy_actor_id == "spoofed-header-actor"
    assert _authority_flags_are_false(context)

    observability = context.to_observability()
    assert observability["actor_trusted"] is False
    assert observability["identity_source"] == LEGACY_ACTOR_SOURCE
    assert observability["auth_mode"] == LEGACY_ACTOR_SOURCE


def test_legacy_header_priority_uses_first_non_empty_named_header() -> None:
    observation = _observation(
        {},
        headers={
            "x-actor-id": "",
            "X-USER-ID": "legacy-user-from-second-header",
        },
    )

    context = resolve_request_actor_context(observation)

    assert context.identity_kind == ACTOR_IDENTITY_LEGACY_HEADER
    assert context.actor_id == "legacy-user-from-second-header"
    assert context.actor_trusted is False


def test_anonymous_when_no_identity_signal_is_present() -> None:
    context = resolve_request_actor_context(_observation({}))

    assert context.identity_kind == ACTOR_IDENTITY_ANONYMOUS
    assert context.actor_id == ANONYMOUS_ACTOR_ID
    assert context.actor_source == ANONYMOUS_ACTOR_SOURCE
    assert context.actor_auth_mode == ANONYMOUS_ACTOR_SOURCE
    assert context.actor_trusted is False
    assert context.legacy_actor_id is None
    assert _authority_flags_are_false(context)


def test_normalized_request_state_context_propagates_observability() -> None:
    observation = _observation(
        {
            "actor_id": "authenticated-actor",
            "actor_context": {
                "legacy_actor_id": "spoofed-header-actor",
                "actor_metadata": {"label": "existing-context", "kept": True},
            },
            "identity_source": "oauth_session",
            "actor_trusted": True,
            "auth_mode": "oidc_claims",
        },
        headers={"X-Actor-Id": "spoofed-header-actor"},
    )

    context = resolve_request_actor_context(observation)

    assert context.identity_kind == ACTOR_IDENTITY_AUTHENTICATED
    assert context.actor_source == "oauth_session"
    assert context.actor_auth_mode == "oidc_claims"
    assert context.legacy_actor_id == "spoofed-header-actor"
    assert context.actor_metadata == {
        "label": "existing-context",
        "kept": True,
    }


def test_require_trusted_actor_context_fails_closed_for_legacy_and_anonymous() -> None:
    for observation in (
        _observation({}, headers={"X-Actor-Id": "legacy-actor"}),
        _observation({}),
    ):
        context = resolve_request_actor_context(observation)
        with pytest.raises(TrustedActorRequired) as error:
            require_trusted_actor_context(context)

        detail = error.value.to_detail()
        assert error.value.status_code == 403
        assert error.value.category == "request_identity"
        assert detail["message"] == "trusted actor required"
        assert detail["reason_code"] == "trusted_actor_required"
        assert detail["next_action"] == "authenticate_request"
        assert detail["actor_context"]["actor_trusted"] is False
        assert _authority_flags_are_false(error.value.context)


def test_require_trusted_actor_context_returns_authenticated_actor() -> None:
    observation = _observation(
        {
            "authenticated_actor": {
                "actor_id": "authenticated-actor",
                "identity_source": "oauth_session",
                "auth_mode": "oidc_claims",
            }
        },
        headers={"X-Actor-Id": "spoofed-header-actor"},
    )

    context = require_trusted_actor_context(resolve_request_actor_context(observation))

    assert context.actor_id == "authenticated-actor"
    assert context.actor_trusted is True
    assert context.legacy_actor_id == "spoofed-header-actor"


def test_actor_digest_from_secret_is_deterministic_and_digest_only() -> None:
    secret = "test-secret-not-a-real-credential"
    expected_digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]

    digest_ref = actor_id_from_secret("provider", secret)

    assert digest_ref == f"provider:{expected_digest}"
    assert digest_ref == actor_id_from_secret("provider", secret)
    assert secret not in digest_ref
    assert digest_ref.startswith("authenticated:") is False
    assert actor_id_from_secret("", secret).startswith("authenticated:")


def test_actor_digest_prefix_is_truncated_to_fixed_boundary() -> None:
    long_prefix = "prefix-" * 40

    digest_ref = actor_id_from_secret(long_prefix, "value")

    prefix, digest = digest_ref.rsplit(":", 1)
    assert prefix == long_prefix[:48]
    assert len(digest) == 16
    assert all(character in "0123456789abcdef" for character in digest)


def test_actor_metadata_is_sanitized_and_context_is_immutable() -> None:
    context = authenticated_actor_context(
        actor_id="actor-1",
        source="oauth_session",
        auth_mode="oidc_claims",
        actor_metadata={
            "label": "  padded-label  ",
            "ok": True,
            "count": 3,
            "unsupported": object(),
            "nested": {"secret": "must-not-enter"},
        },
    )

    assert context.actor_metadata["label"] == "padded-label"
    assert context.actor_metadata["ok"] is True
    assert context.actor_metadata["count"] == 3
    assert "unsupported" not in context.actor_metadata
    assert "nested" not in context.actor_metadata
    assert isinstance(context.actor_metadata, MappingProxyType)
    with pytest.raises(FrozenInstanceError):
        context.actor_id = "changed"  # type: ignore[misc]


def test_authority_defaults_false_for_all_three_identity_kinds() -> None:
    contexts = (
        resolve_request_actor_context(
            _observation(
                {
                    "authenticated_actor": {
                        "actor_id": "actor-1",
                        "identity_source": "oauth_session",
                        "auth_mode": "oidc_claims",
                    }
                }
            )
        ),
        resolve_request_actor_context(
            _observation({}, headers={"X-Actor-Id": "legacy-1"})
        ),
        resolve_request_actor_context(_observation({})),
    )

    assert {context.identity_kind for context in contexts} == {
        ACTOR_IDENTITY_AUTHENTICATED,
        ACTOR_IDENTITY_LEGACY_HEADER,
        ACTOR_IDENTITY_ANONYMOUS,
    }
    for context in contexts:
        assert context.authority.live_provider is False
        assert context.authority.canonical_write is False
        assert context.authority.cutover is False
        assert context.authority.external_delivery is False
        assert context.authority.authority_transfer is False
        assert _authority_flags_are_false(context)


def test_resolution_is_pure_and_does_not_mutate_input() -> None:
    headers = {"X-Actor-Id": "legacy-actor"}
    state = {
        "authenticated_actor": {
            "actor_id": "authenticated-actor",
            "identity_source": "oauth_session",
            "auth_mode": "oidc_claims",
        },
        "actor_context": {"actor_metadata": {"label": "before"}},
    }
    headers_before = dict(headers)
    state_before = {key: dict(value) for key, value in state.items()}

    resolve_request_actor_context(_observation(state, headers=headers))

    assert headers == headers_before
    assert state == state_before


def test_s1_acceptance_trace_authenticated_legacy_anonymous() -> None:
    authenticated = resolve_request_actor_context(
        _observation(
            {
                "authenticated_actor": {
                    "actor_id": "authenticated-actor",
                    "identity_source": "oauth_session",
                    "auth_mode": "oidc_claims",
                }
            },
            headers={"X-Actor-Id": "spoofed-header-actor"},
        )
    )
    legacy = resolve_request_actor_context(
        _observation({}, headers={"X-Actor-Id": "legacy-header-actor"})
    )
    anonymous = resolve_request_actor_context(_observation({}))

    trace_rows = (
        {
            "trace_id": ACCEPTANCE_TRACE_ID,
            "observation": "authenticated-state-actor",
            "identity_kind": authenticated.identity_kind,
            "actor_id": authenticated.actor_id,
            "actor_trusted": authenticated.actor_trusted,
            "legacy_actor_id": authenticated.legacy_actor_id,
            "authority": authenticated.authority.to_plain(),
        },
        {
            "trace_id": ACCEPTANCE_TRACE_ID,
            "observation": "legacy-header-actor",
            "identity_kind": legacy.identity_kind,
            "actor_id": legacy.actor_id,
            "actor_trusted": legacy.actor_trusted,
            "legacy_actor_id": legacy.legacy_actor_id,
            "authority": legacy.authority.to_plain(),
        },
        {
            "trace_id": ACCEPTANCE_TRACE_ID,
            "observation": "anonymous-actor",
            "identity_kind": anonymous.identity_kind,
            "actor_id": anonymous.actor_id,
            "actor_trusted": anonymous.actor_trusted,
            "legacy_actor_id": anonymous.legacy_actor_id,
            "authority": anonymous.authority.to_plain(),
        },
    )

    assert [row["identity_kind"] for row in trace_rows] == [
        ACTOR_IDENTITY_AUTHENTICATED,
        ACTOR_IDENTITY_LEGACY_HEADER,
        ACTOR_IDENTITY_ANONYMOUS,
    ]
    assert trace_rows[0]["actor_trusted"] is True
    assert trace_rows[1]["actor_trusted"] is False
    assert trace_rows[2]["actor_trusted"] is False
    assert trace_rows[0]["legacy_actor_id"] == "spoofed-header-actor"
    assert trace_rows[1]["legacy_actor_id"] == "legacy-header-actor"
    assert trace_rows[2]["legacy_actor_id"] is None
    for row in trace_rows:
        assert all(
            flag is False
            for flag in row["authority"].values()
            if isinstance(flag, bool)
        )

    trace_digest = hashlib.sha256(
        repr(
            (trace_rows, DONOR_REQUEST_IDENTITY_PATH, DONOR_REQUEST_IDENTITY_SHA256)
        ).encode("utf-8")
    ).hexdigest()
    assert len(trace_digest) == 64


def test_donor_sha_fixture_is_bounded_evidence_not_an_import() -> None:
    assert len(DONOR_REQUEST_IDENTITY_SHA256) == 64
    assert DONOR_REQUEST_IDENTITY_PATH.startswith("main/backend/app/services/")
