"""S1 horizontal request-identity port for ALL-SM-010.

This is a self-contained pure successor port.  It re-expresses the donor
actor/identity normalization contract as typed authenticated, legacy-header and
anonymous resolution without importing donor code, a web framework, a runtime
port registry or any facade contract module.

The port performs no effect: it never reads a live request, never writes
``request.state`` or canonical state, never touches credentials, and grants no
runtime authority.  Secret-like input may only be converted to a digest ref;
the raw value is never stored in a context or emitted by this module.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final, Literal, TypeAlias

REQUEST_IDENTITY_PORT_REF: Final[str] = (
    "mrw.successor.request-identity.horizontal-port.v1"
)
REQUEST_IDENTITY_SCHEMA: Final[str] = "mrw.successor.request-identity.actor-context.v1"
REQUEST_IDENTITY_OBSERVATION_SCHEMA: Final[str] = (
    "mrw.successor.request-identity.observation.v1"
)
REQUEST_IDENTITY_AUTHORITY_SCHEMA: Final[str] = (
    "mrw.successor.request-identity.authority.v1"
)

ACTOR_IDENTITY_AUTHENTICATED: Final[str] = "authenticated"
ACTOR_IDENTITY_LEGACY_HEADER: Final[str] = "legacy_header"
ACTOR_IDENTITY_ANONYMOUS: Final[str] = "anonymous"
IDENTITY_KINDS: Final[frozenset[str]] = frozenset(
    {
        ACTOR_IDENTITY_AUTHENTICATED,
        ACTOR_IDENTITY_LEGACY_HEADER,
        ACTOR_IDENTITY_ANONYMOUS,
    }
)
ActorIdentityKind: TypeAlias = Literal["authenticated", "legacy_header", "anonymous"]

ANONYMOUS_ACTOR_ID: Final[str] = "anonymous"
LEGACY_ACTOR_SOURCE: Final[str] = "legacy_header"
ANONYMOUS_ACTOR_SOURCE: Final[str] = "anonymous"
DEFAULT_AUTHENTICATED_SOURCE: Final[str] = "authenticated"
DEFAULT_AUTHENTICATED_MODE: Final[str] = "authenticated"
REQUEST_STATE_SOURCE: Final[str] = "request_state"
AUTHENTICATED_REQUEST_STATE_SOURCE: Final[str] = "authenticated_request_state"

# Observation of the donor working-tree header order, expressed as fixture
# evidence only.  Nothing in this module reads headers from a live request.
LEGACY_ACTOR_HEADERS: Final[tuple[str, ...]] = (
    "X-Actor-Id",
    "X-User-Id",
    "X-User-Email",
    "X-Request-Actor",
)

_ACTOR_ID_KEYS: Final[tuple[str, ...]] = ("actor_id", "id", "subject", "sub")
_ACTOR_SOURCE_KEYS: Final[tuple[str, ...]] = (
    "identity_source",
    "actor_source",
    "source",
)
_ACTOR_AUTH_MODE_KEYS: Final[tuple[str, ...]] = (
    "actor_auth_mode",
    "auth_mode",
    "auth_type",
)
_AUTH_STATE_ATTRS: Final[tuple[tuple[str, str], ...]] = (
    ("authenticated_actor", "authenticated_actor"),
    ("codex_authenticated_actor", "codex_authenticated_actor"),
)

_ACTOR_ID_MAX_LENGTH = 128
_ACTOR_SOURCE_MAX_LENGTH = 64
_ACTOR_MODE_MAX_LENGTH = 64
_ACTOR_DIGEST_PREFIX_MAX_LENGTH = 48
_ACTOR_METADATA_KEY_MAX_LENGTH = 64
_ACTOR_METADATA_VALUE_MAX_LENGTH = 128
_ACTOR_DIGEST_HEX_LENGTH = 16

_EMPTY_METADATA: Mapping[str, Any] = MappingProxyType({})


def _clean_text(value: Any, *, max_length: int = _ACTOR_ID_MAX_LENGTH) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:max_length]


def _as_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return _EMPTY_METADATA


def _header_value(headers: Mapping[str, str] | None, name: str) -> Any | None:
    if not isinstance(headers, Mapping):
        return None
    target = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == target:
            return value
    return None


def _first_mapping_text(
    mapping: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    max_length: int,
) -> str | None:
    for key in keys:
        cleaned = _clean_text(mapping.get(key), max_length=max_length)
        if cleaned is not None:
            return cleaned
    return None


def _first_legacy_actor(headers: Mapping[str, str] | None) -> str | None:
    for header_name in LEGACY_ACTOR_HEADERS:
        cleaned = _clean_text(_header_value(headers, header_name))
        if cleaned is not None:
            return cleaned
    return None


def _freeze_actor_metadata(
    metadata: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if not isinstance(metadata, Mapping):
        return _EMPTY_METADATA
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        clean_key = _clean_text(key, max_length=_ACTOR_METADATA_KEY_MAX_LENGTH)
        if clean_key is None:
            continue
        if value is None or isinstance(value, (bool, int, float)):
            safe[clean_key] = value
        elif isinstance(value, str):
            clean_value = _clean_text(
                value, max_length=_ACTOR_METADATA_VALUE_MAX_LENGTH
            )
            if clean_value is not None:
                safe[clean_key] = clean_value
    return MappingProxyType(safe)


def actor_id_from_secret(prefix: str, value: Any) -> str:
    """Return a deterministic digest-only actor ref for a secret-like value.

    Only the SHA-256 prefix is returned.  The caller and this module must
    never log, store or emit ``value`` itself.
    """

    digest = hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[
        :_ACTOR_DIGEST_HEX_LENGTH
    ]
    clean_prefix = _clean_text(prefix, max_length=_ACTOR_DIGEST_PREFIX_MAX_LENGTH)
    return f"{clean_prefix or DEFAULT_AUTHENTICATED_SOURCE}:{digest}"


@dataclass(frozen=True, slots=True)
class RequestIdentityAuthority:
    """Authority ceiling carried by every resolved identity.

    ALL-SM-010 grants no live provider, canonical write, cutover, external
    delivery or authority transfer.  Constructing any ``True`` flag is a
    contract violation so the port fails closed even under future misuse.
    """

    schema_ref: str = REQUEST_IDENTITY_AUTHORITY_SCHEMA
    live_provider: bool = False
    canonical_write: bool = False
    cutover: bool = False
    external_delivery: bool = False
    authority_transfer: bool = False

    def __post_init__(self) -> None:
        for name in (
            "live_provider",
            "canonical_write",
            "cutover",
            "external_delivery",
            "authority_transfer",
        ):
            value = getattr(self, name)
            if not isinstance(value, bool):
                raise TypeError(f"RequestIdentityAuthority.{name} must be bool")
            if value:
                raise ValueError(
                    "request-identity port grants no runtime authority; "
                    f"{name} must be False"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_ref": self.schema_ref,
            "live_provider": self.live_provider,
            "canonical_write": self.canonical_write,
            "cutover": self.cutover,
            "external_delivery": self.external_delivery,
            "authority_transfer": self.authority_transfer,
        }


@dataclass(frozen=True, slots=True)
class RequestActorContext:
    """Typed normalized actor/identity result.

    ``actor_trusted`` is the normalized authn observation, not runtime
    authority.  Authenticated state may assert trust while ``authority`` stays
    all-False; legacy and anonymous inputs are always untrusted.
    """

    identity_kind: ActorIdentityKind
    actor_id: str
    actor_source: str
    actor_auth_mode: str
    actor_trusted: bool
    legacy_actor_id: str | None = None
    actor_metadata: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_METADATA)
    authority: RequestIdentityAuthority = field(
        default_factory=RequestIdentityAuthority
    )

    def __post_init__(self) -> None:
        if self.identity_kind not in IDENTITY_KINDS:
            raise ValueError(f"identity_kind must be one of {sorted(IDENTITY_KINDS)}")
        actor_id = _clean_text(self.actor_id)
        if actor_id is None:
            raise ValueError("RequestActorContext requires a non-empty actor_id")
        source = _clean_text(self.actor_source, max_length=_ACTOR_SOURCE_MAX_LENGTH)
        if source is None:
            raise ValueError("RequestActorContext requires actor_source")
        mode = _clean_text(self.actor_auth_mode, max_length=_ACTOR_MODE_MAX_LENGTH)
        if mode is None:
            raise ValueError("RequestActorContext requires actor_auth_mode")
        if not isinstance(self.actor_trusted, bool):
            raise TypeError("RequestActorContext.actor_trusted must be bool")
        legacy_actor_id = _clean_text(self.legacy_actor_id)
        if not isinstance(self.authority, RequestIdentityAuthority):
            raise TypeError("RequestActorContext.authority is required")
        object.__setattr__(self, "actor_id", actor_id)
        object.__setattr__(self, "actor_source", source)
        object.__setattr__(self, "actor_auth_mode", mode)
        object.__setattr__(self, "legacy_actor_id", legacy_actor_id)
        object.__setattr__(
            self,
            "actor_metadata",
            _freeze_actor_metadata(self.actor_metadata),
        )

    @property
    def identity_source(self) -> str:
        return self.actor_source

    @property
    def auth_mode(self) -> str:
        return self.actor_auth_mode

    def to_observability(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "actor_id": self.actor_id,
            "actor_source": self.actor_source,
            "identity_source": self.identity_source,
            "actor_trusted": self.actor_trusted,
            "actor_auth_mode": self.actor_auth_mode,
            "auth_mode": self.auth_mode,
            "legacy_actor_id": self.legacy_actor_id,
            "identity_kind": self.identity_kind,
            "authority": self.authority.to_plain(),
        }
        if self.actor_metadata:
            payload["actor_metadata"] = dict(self.actor_metadata)
        return payload

    def to_plain(self) -> dict[str, Any]:
        return self.to_observability()


@dataclass(frozen=True, slots=True)
class RequestIdentityObservation:
    """Framework-neutral signals equivalent to one donor request.

    Header names are matched case-insensitively.  State fields mirror the
    donor ``request.state`` attributes that participate in resolution.
    """

    schema_ref: str = REQUEST_IDENTITY_OBSERVATION_SCHEMA
    headers: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    authenticated_actor: Mapping[str, Any] | None = None
    codex_authenticated_actor: Mapping[str, Any] | None = None
    authenticated_actor_id: str | None = None
    actor_id: str | None = None
    actor_context: Mapping[str, Any] | None = None
    actor_source: str | None = None
    identity_source: str | None = None
    actor_trusted: bool | None = None
    actor_auth_mode: str | None = None
    auth_mode: str | None = None
    legacy_actor_id: str | None = None


RequestIdentityResolver: TypeAlias = Callable[
    [RequestIdentityObservation], RequestActorContext
]


def request_identity_observation_from_state(
    state: Mapping[str, Any] | None = None,
    *,
    headers: Mapping[str, str] | None = None,
) -> RequestIdentityObservation:
    """Build a pure observation from a donor-shaped ``request.state`` mapping."""

    state_map = _as_mapping(state)
    return RequestIdentityObservation(
        headers=MappingProxyType(dict(headers or {})),
        authenticated_actor=state_map.get("authenticated_actor"),
        codex_authenticated_actor=state_map.get("codex_authenticated_actor"),
        authenticated_actor_id=state_map.get("authenticated_actor_id"),
        actor_id=state_map.get("actor_id"),
        actor_context=state_map.get("actor_context"),
        actor_source=state_map.get("actor_source"),
        identity_source=state_map.get("identity_source"),
        actor_trusted=state_map.get("actor_trusted"),
        actor_auth_mode=state_map.get("actor_auth_mode"),
        auth_mode=state_map.get("auth_mode"),
        legacy_actor_id=state_map.get("legacy_actor_id"),
    )


def authenticated_actor_context(
    *,
    actor_id: Any,
    source: Any = None,
    auth_mode: Any = None,
    legacy_actor_id: Any = None,
    actor_metadata: Mapping[str, Any] | None = None,
) -> RequestActorContext:
    """Normalize one authenticated actor signal into a trusted typed context."""

    clean_actor_id = _clean_text(actor_id) or ANONYMOUS_ACTOR_ID
    return RequestActorContext(
        identity_kind=ACTOR_IDENTITY_AUTHENTICATED,
        actor_id=clean_actor_id,
        actor_source=(
            _clean_text(source, max_length=_ACTOR_SOURCE_MAX_LENGTH)
            or DEFAULT_AUTHENTICATED_SOURCE
        ),
        actor_auth_mode=(
            _clean_text(auth_mode, max_length=_ACTOR_MODE_MAX_LENGTH)
            or DEFAULT_AUTHENTICATED_MODE
        ),
        actor_trusted=True,
        legacy_actor_id=legacy_actor_id,
        actor_metadata=actor_metadata,
    )


def legacy_or_anonymous_actor_context(
    headers: Mapping[str, str] | None = None,
) -> RequestActorContext:
    """Resolve legacy-header or anonymous identity from headers only."""

    legacy_actor_id = _first_legacy_actor(headers)
    if legacy_actor_id is not None:
        return RequestActorContext(
            identity_kind=ACTOR_IDENTITY_LEGACY_HEADER,
            actor_id=legacy_actor_id,
            actor_source=LEGACY_ACTOR_SOURCE,
            actor_auth_mode=LEGACY_ACTOR_SOURCE,
            actor_trusted=False,
            legacy_actor_id=legacy_actor_id,
        )
    return RequestActorContext(
        identity_kind=ACTOR_IDENTITY_ANONYMOUS,
        actor_id=ANONYMOUS_ACTOR_ID,
        actor_source=ANONYMOUS_ACTOR_SOURCE,
        actor_auth_mode=ANONYMOUS_ACTOR_SOURCE,
        actor_trusted=False,
        legacy_actor_id=None,
    )


def _authenticated_context_from_observation(
    observation: RequestIdentityObservation,
) -> RequestActorContext | None:
    legacy_actor_id = _first_legacy_actor(observation.headers)
    for state_attr, attr_name in _AUTH_STATE_ATTRS:
        raw_actor = getattr(observation, state_attr)
        if not isinstance(raw_actor, Mapping):
            continue
        actor_id = _first_mapping_text(
            raw_actor, _ACTOR_ID_KEYS, max_length=_ACTOR_ID_MAX_LENGTH
        )
        if actor_id is None:
            continue
        return authenticated_actor_context(
            actor_id=actor_id,
            source=(
                _first_mapping_text(
                    raw_actor,
                    _ACTOR_SOURCE_KEYS,
                    max_length=_ACTOR_SOURCE_MAX_LENGTH,
                )
                or attr_name
            ),
            auth_mode=(
                _first_mapping_text(
                    raw_actor,
                    _ACTOR_AUTH_MODE_KEYS,
                    max_length=_ACTOR_MODE_MAX_LENGTH,
                )
                or attr_name
            ),
            legacy_actor_id=legacy_actor_id,
        )
    actor_id = _clean_text(observation.authenticated_actor_id)
    if actor_id is not None:
        return authenticated_actor_context(
            actor_id=actor_id,
            source=AUTHENTICATED_REQUEST_STATE_SOURCE,
            auth_mode=AUTHENTICATED_REQUEST_STATE_SOURCE,
            legacy_actor_id=legacy_actor_id,
        )
    return None


def _identity_kind_for_normalized_state(
    *,
    actor_id: str,
    actor_source: str,
    actor_auth_mode: str,
    actor_trusted: bool,
) -> ActorIdentityKind:
    if actor_source == LEGACY_ACTOR_SOURCE or actor_auth_mode == LEGACY_ACTOR_SOURCE:
        return ACTOR_IDENTITY_LEGACY_HEADER
    if actor_id == ANONYMOUS_ACTOR_ID or actor_source == ANONYMOUS_ACTOR_SOURCE:
        return ACTOR_IDENTITY_ANONYMOUS
    if actor_trusted:
        return ACTOR_IDENTITY_AUTHENTICATED
    # An untrusted non-legacy state marker is not authenticated by this port.
    return ACTOR_IDENTITY_ANONYMOUS


def _state_actor_context_from_observation(
    observation: RequestIdentityObservation,
) -> RequestActorContext | None:
    actor_id = _clean_text(observation.actor_id)
    if actor_id is None:
        return None
    context_map = _as_mapping(observation.actor_context)
    identity_source = _clean_text(
        observation.identity_source, max_length=_ACTOR_SOURCE_MAX_LENGTH
    )
    actor_source = _clean_text(
        observation.actor_source, max_length=_ACTOR_SOURCE_MAX_LENGTH
    )
    normalized_source = identity_source or actor_source or REQUEST_STATE_SOURCE
    auth_mode = _clean_text(observation.auth_mode, max_length=_ACTOR_MODE_MAX_LENGTH)
    actor_auth_mode = _clean_text(
        observation.actor_auth_mode, max_length=_ACTOR_MODE_MAX_LENGTH
    )
    normalized_mode = auth_mode or actor_auth_mode or REQUEST_STATE_SOURCE
    trusted = bool(observation.actor_trusted)
    legacy_actor_id = (
        _clean_text(context_map.get("legacy_actor_id"))
        or _clean_text(observation.legacy_actor_id)
        or _first_legacy_actor(observation.headers)
    )
    return RequestActorContext(
        identity_kind=_identity_kind_for_normalized_state(
            actor_id=actor_id,
            actor_source=normalized_source,
            actor_auth_mode=normalized_mode,
            actor_trusted=trusted,
        ),
        actor_id=actor_id,
        actor_source=normalized_source,
        actor_auth_mode=normalized_mode,
        actor_trusted=trusted,
        legacy_actor_id=legacy_actor_id,
        actor_metadata=_freeze_actor_metadata(context_map.get("actor_metadata")),
    )


def resolve_request_actor_context(
    observation: RequestIdentityObservation,
) -> RequestActorContext:
    """Resolve one typed observation with donor-compatible ordering.

    Order: authenticated state overrides legacy spoof headers; a previously
    normalized state actor follows; otherwise legacy headers or anonymous.
    """

    if not isinstance(observation, RequestIdentityObservation):
        raise TypeError(
            "resolve_request_actor_context requires RequestIdentityObservation"
        )
    authenticated = _authenticated_context_from_observation(observation)
    if authenticated is not None:
        return authenticated
    state_context = _state_actor_context_from_observation(observation)
    if state_context is not None:
        return state_context
    return legacy_or_anonymous_actor_context(observation.headers)


def resolve_request_actor_from_state(
    state: Mapping[str, Any] | None = None,
    *,
    headers: Mapping[str, str] | None = None,
) -> RequestActorContext:
    """Pure convenience wrapper over a donor-shaped state mapping."""

    observation = request_identity_observation_from_state(state, headers=headers)
    return resolve_request_actor_context(observation)


class TrustedActorRequired(RuntimeError):
    """Fail-closed denial for untrusted actor resolution.

    The successor port expresses the donor HTTP 403 as a typed exception
    carrying the same status code, reason, recovery hint and context payload.
    """

    status_code: int = 403
    category: str = "request_identity"
    reason_code: str = "trusted_actor_required"
    next_action: str = "authenticate_request"

    def __init__(self, context: RequestActorContext) -> None:
        self.context = context
        super().__init__("trusted actor required")

    def to_detail(self) -> dict[str, Any]:
        return {
            "message": str(self),
            "category": self.category,
            "reason_code": self.reason_code,
            "next_action": self.next_action,
            "actor_context": self.context.to_observability(),
        }


def require_trusted_actor_context(
    context: RequestActorContext,
) -> RequestActorContext:
    """Return a trusted context or raise a typed 403-equivalent denial."""

    if not isinstance(context, RequestActorContext):
        raise TypeError("require_trusted_actor_context requires RequestActorContext")
    if context.actor_trusted:
        return context
    raise TrustedActorRequired(context)


__all__ = [
    "ACTOR_IDENTITY_ANONYMOUS",
    "ACTOR_IDENTITY_AUTHENTICATED",
    "ACTOR_IDENTITY_LEGACY_HEADER",
    "ANONYMOUS_ACTOR_ID",
    "ANONYMOUS_ACTOR_SOURCE",
    "DEFAULT_AUTHENTICATED_MODE",
    "DEFAULT_AUTHENTICATED_SOURCE",
    "IDENTITY_KINDS",
    "LEGACY_ACTOR_HEADERS",
    "LEGACY_ACTOR_SOURCE",
    "REQUEST_IDENTITY_AUTHORITY_SCHEMA",
    "REQUEST_IDENTITY_OBSERVATION_SCHEMA",
    "REQUEST_IDENTITY_PORT_REF",
    "REQUEST_IDENTITY_SCHEMA",
    "ActorIdentityKind",
    "RequestActorContext",
    "RequestIdentityAuthority",
    "RequestIdentityObservation",
    "RequestIdentityResolver",
    "TrustedActorRequired",
    "actor_id_from_secret",
    "authenticated_actor_context",
    "legacy_or_anonymous_actor_context",
    "request_identity_observation_from_state",
    "require_trusted_actor_context",
    "resolve_request_actor_context",
    "resolve_request_actor_from_state",
]
