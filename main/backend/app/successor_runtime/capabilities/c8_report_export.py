"""C8.3 successor report-export signing and typed verification.

Movement binding: ALL-SM-009 (llm-report export/token-state successor) |
C8.3 report delivery cluster.  This module is a self-contained, pure
successor port.  It re-expresses the donor ``llm_report_export`` token
contract as typed signing/verify/receipt operations without importing donor
services, database models, request frameworks or live providers.

The module performs no effect: it never reads a live request, never writes
token state, never touches credentials and grants no runtime authority.  The
actor is carried as a deterministic digest ref, never as a raw actor value.
``artifact_token`` is only present on the returned :class:`SignedReportExportToken`
value; no persistence or readback API in this family stores or emits the
full token.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final

__all__ = [
    "DEFAULT_LOCAL_TOKEN_SECRET",
    "REPORT_EXPORT_AUTHORITY_SCHEMA",
    "REPORT_EXPORT_SCHEMA",
    "REPORT_EXPORT_TOKEN_CONTRACT",
    "ReportExportReceipt",
    "ReportExportSigningInput",
    "ReportExportTokenAuthority",
    "ReportExportTokenError",
    "SignedReportExportToken",
    "actor_id_from_secret",
    "build_report_export_receipt",
    "canonical_payload",
    "markdown_sha256",
    "sign_report_export_token",
    "verify_report_export_token",
]

REPORT_EXPORT_SCHEMA: Final[str] = "mrw.successor.c8.report-export.v1"
REPORT_EXPORT_AUTHORITY_SCHEMA: Final[str] = (
    "mrw.successor.c8.report-export.authority.v1"
)
REPORT_EXPORT_TOKEN_CONTRACT: Final[str] = "mrw.successor.c8.report-export-token.v1"
# Local/test-only fallback.  Production callers must supply a private secret
# through an explicit credential boundary; this default must never be used as
# a durable production token secret.
DEFAULT_LOCAL_TOKEN_SECRET: Final[str] = "mrw-successor-c8-report-export-local-v1"

_TOKEN_HEADER = "llmrpt-v1"
_RECEIPT_SCHEMA = "mrw.successor.c8.report-export.receipt.v1"
_SHA256_HEX = frozenset("0123456789abcdef")
_ACTOR_DIGEST_HEX_LENGTH = 16
_ACTOR_DIGEST_PREFIX_MAX_LENGTH = 48


def _clean_text(value: Any, *, max_length: int = 128) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:max_length]


def _require_text(value: Any, *, name: str, max_length: int = 128) -> str:
    text = _clean_text(value, max_length=max_length)
    if text is None:
        raise ValueError(f"{name} is required")
    return text


def _require_sha256_hex(value: Any, *, name: str) -> str:
    digest = _require_text(value, name=name, max_length=64)
    if len(digest) != 64 or any(char not in _SHA256_HEX for char in digest):
        raise ValueError(f"{name} must be a 64-char lowercase sha256 hex digest")
    return digest


def _as_bool(value: Any, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be bool")
    return value


def _as_int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise TypeError("job_id must be int or None")
    return int(value)


def _as_utc(value: datetime | None, *, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _isoformat_utc(value: datetime) -> str:
    return _as_utc(value, name="datetime").replace(microsecond=0).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value, name="datetime")
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(parsed, name="datetime")


def actor_id_from_secret(prefix: str, value: Any) -> str:
    """Return a deterministic digest-only actor ref for a secret-like value.

    Only the first 16 hex characters of the SHA-256 digest are returned.  The
    raw value itself is never stored, logged or emitted by this module.
    """

    digest = hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[
        :_ACTOR_DIGEST_HEX_LENGTH
    ]
    clean_prefix = _clean_text(prefix, max_length=_ACTOR_DIGEST_PREFIX_MAX_LENGTH)
    return f"{clean_prefix or 'authenticated'}:{digest}"


def markdown_sha256(markdown: str) -> str:
    """Return the deterministic SHA-256 hex digest of markdown bytes."""

    return hashlib.sha256(str(markdown or "").encode("utf-8")).hexdigest()


def _canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padded = value + ("=" * ((4 - len(value) % 4) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _stable_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _token_secret_bytes(token_secret: str | None) -> bytes:
    secret = str(token_secret or "").strip() or DEFAULT_LOCAL_TOKEN_SECRET
    return secret.encode("utf-8")


def _normalize_gate_snapshot(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("gate_snapshot must be a mapping")
    return {str(key): item for key, item in value.items()}


def canonical_payload(payload_or_mapping: Mapping[str, Any] | Any) -> bytes:
    """Return canonical UTF-8 JSON bytes for signing or digest purposes.

    A :class:`ReportExportSigningInput` is accepted and converted through
    ``payload_plain`` so no secret or token ever reaches the serialized bytes.
    """

    if isinstance(payload_or_mapping, ReportExportSigningInput):
        payload: Mapping[str, Any] = payload_or_mapping.payload_plain()
    elif isinstance(payload_or_mapping, Mapping):
        payload = payload_or_mapping
    else:
        raise TypeError(
            "canonical_payload requires a mapping or ReportExportSigningInput"
        )
    return _canonical_json_bytes({str(key): item for key, item in payload.items()})


@dataclass(frozen=True, slots=True)
class ReportExportTokenAuthority:
    """Authority ceiling carried by signed export values.

    ALL-SM-009 grants no live provider, canonical write, cutover, external
    delivery, authority transfer, scheduler, executor or credential read.
    Constructing any ``True`` flag is a contract violation so the port fails
    closed even under future misuse.
    """

    schema_ref: str = REPORT_EXPORT_AUTHORITY_SCHEMA
    live_provider: bool = False
    canonical_write: bool = False
    cutover: bool = False
    external_delivery: bool = False
    authority_transfer: bool = False
    scheduler: bool = False
    executor: bool = False
    credential_read: bool = False

    def __post_init__(self) -> None:
        if not self.schema_ref or not isinstance(self.schema_ref, str):
            raise ValueError("ReportExportTokenAuthority requires schema_ref")
        for name in (
            "live_provider",
            "canonical_write",
            "cutover",
            "external_delivery",
            "authority_transfer",
            "scheduler",
            "executor",
            "credential_read",
        ):
            value = getattr(self, name)
            if not isinstance(value, bool):
                raise TypeError(f"ReportExportTokenAuthority.{name} must be bool")
            if value:
                raise ValueError(
                    "report-export port grants no runtime authority; "
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
            "scheduler": self.scheduler,
            "executor": self.executor,
            "credential_read": self.credential_read,
        }


@dataclass(frozen=True, slots=True)
class ReportExportSigningInput:
    """Deterministic signing input for one report-export artifact token."""

    artifact_id: str
    markdown_sha256: str
    export_format: str
    trace_id: str | None
    request_id: str | None
    project_key: str | None
    job_id: int | None
    actor_digest: str
    gate_snapshot: Mapping[str, Any]
    issued_at: datetime
    expires_at: datetime
    one_time_use: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _require_text(self.artifact_id, name="artifact_id", max_length=128),
        )
        object.__setattr__(
            self,
            "markdown_sha256",
            _require_sha256_hex(self.markdown_sha256, name="markdown_sha256"),
        )
        export_format = str(self.export_format or "").strip().lower()
        if not export_format:
            raise ValueError("export_format is required")
        object.__setattr__(self, "export_format", export_format[:32])
        object.__setattr__(
            self,
            "trace_id",
            _clean_text(self.trace_id, max_length=128),
        )
        object.__setattr__(
            self,
            "request_id",
            _clean_text(self.request_id, max_length=128),
        )
        object.__setattr__(
            self,
            "project_key",
            _clean_text(self.project_key, max_length=64),
        )
        object.__setattr__(self, "job_id", _as_int_or_none(self.job_id))
        object.__setattr__(
            self,
            "actor_digest",
            _require_text(self.actor_digest, name="actor_digest", max_length=128),
        )
        object.__setattr__(
            self,
            "gate_snapshot",
            _normalize_gate_snapshot(self.gate_snapshot),
        )
        issued_at = _as_utc(self.issued_at, name="issued_at")
        expires_at = _as_utc(self.expires_at, name="expires_at")
        if issued_at is None or expires_at is None:
            raise ValueError("issued_at and expires_at are required")
        object.__setattr__(self, "issued_at", issued_at)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(
            self,
            "one_time_use",
            _as_bool(self.one_time_use, name="one_time_use"),
        )

    def payload_plain(self) -> dict[str, Any]:
        """Return the safe token payload without secrets or signed tokens."""

        return {
            "contract_version": REPORT_EXPORT_TOKEN_CONTRACT,
            "artifact_id": self.artifact_id,
            "markdown_sha256": self.markdown_sha256,
            "export_format": self.export_format,
            "gate": dict(self.gate_snapshot),
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "project_key": self.project_key,
            "job_id": self.job_id,
            "actor_digest": self.actor_digest,
            "issued_at": _isoformat_utc(self.issued_at),
            "expires_at": _isoformat_utc(self.expires_at),
            "one_time_use": self.one_time_use,
        }


@dataclass(frozen=True, slots=True)
class SignedReportExportToken:
    """Typed return value of one deterministic token signing operation."""

    token_ref: str
    payload_digest: str
    artifact_token: str
    authority: ReportExportTokenAuthority = field(
        default_factory=ReportExportTokenAuthority
    )

    def __post_init__(self) -> None:
        token_ref = _require_text(self.token_ref, name="token_ref", max_length=256)
        object.__setattr__(self, "token_ref", token_ref)
        object.__setattr__(
            self,
            "payload_digest",
            _require_sha256_hex(self.payload_digest, name="payload_digest"),
        )
        token = str(self.artifact_token or "").strip()
        if not token.startswith(_TOKEN_HEADER + "."):
            raise ValueError("artifact_token must be an llmrpt-v1 signed token")
        object.__setattr__(self, "artifact_token", token)
        if not isinstance(self.authority, ReportExportTokenAuthority):
            raise TypeError("SignedReportExportToken.authority must be typed")


class ReportExportTokenError(RuntimeError):
    """Typed fail-closed report export token error.

    The error mirrors the trusted-actor detail style used by successor ports:
    ``to_detail()`` emits only typed category/reason/detail values and never
    carries a secret or the full signed token.
    """

    status_code = 403
    category = "report_export"

    def __init__(
        self,
        reason_code: str,
        *,
        detail: Any = None,
        status_code: int | None = None,
    ) -> None:
        if not reason_code:
            raise ValueError("ReportExportTokenError requires reason_code")
        self.reason_code = reason_code
        self.detail = detail
        if status_code is not None:
            self.status_code = int(status_code)
        message = reason_code
        if detail is not None:
            message = f"{reason_code}: {detail}"
        super().__init__(message)

    def to_detail(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "reason_code": self.reason_code,
            "status_code": self.status_code,
            "detail": self.detail,
        }


def _sign_payload(
    payload: dict[str, Any],
    token_secret: str,
) -> tuple[str, str, str]:
    payload_bytes = _canonical_json_bytes(payload)
    payload_part = _base64url_encode(payload_bytes)
    expected_signature = hmac.new(
        _token_secret_bytes(token_secret),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    signature = _base64url_encode(expected_signature)
    token = f"{_TOKEN_HEADER}.{payload_part}.{signature}"
    digest = hashlib.sha256(payload_bytes).hexdigest()
    return token, digest, payload_part


def sign_report_export_token(
    signing_input: ReportExportSigningInput,
    token_secret: str = DEFAULT_LOCAL_TOKEN_SECRET,
) -> SignedReportExportToken:
    """Sign one deterministic report-export payload.

    The secret is used only inside this call and is never stored on the typed
    result.  ``DEFAULT_LOCAL_TOKEN_SECRET`` is a local/test fallback and must
    not be used as a production secret.
    """

    if not isinstance(signing_input, ReportExportSigningInput):
        raise TypeError("sign_report_export_token requires typed signing input")
    payload = signing_input.payload_plain()
    token, payload_digest, _payload_part = _sign_payload(
        payload,
        token_secret,
    )
    return SignedReportExportToken(
        token_ref=f"export-token:{payload_digest}",
        payload_digest=payload_digest,
        artifact_token=token,
        authority=ReportExportTokenAuthority(),
    )


def verify_report_export_token(
    token: str,
    markdown_sha256: str,
    actor_digest: str,
    token_secret: str = DEFAULT_LOCAL_TOKEN_SECRET,
    now: datetime | None = None,
    revoked_check: Callable[[str], bool] | None = None,
    used_check: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Verify an export token in the fixed donor-derived order.

    Order: format -> signature -> payload -> contract -> markdown hash ->
    expiry -> actor mismatch -> revoked -> used (one-time only).  Every
    rejection uses a typed ``ReportExportTokenError.reason_code``.
    """

    parts = str(token or "").strip().split(".")
    if len(parts) != 3 or parts[0] != _TOKEN_HEADER or not parts[1] or not parts[2]:
        raise ReportExportTokenError("invalid_export_token_format")
    payload_part = parts[1]
    expected_signature = hmac.new(
        _token_secret_bytes(token_secret),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        supplied_signature = _base64url_decode(parts[2])
    except Exception as exc:
        raise ReportExportTokenError("invalid_export_token_signature") from exc
    if not hmac.compare_digest(expected_signature, supplied_signature):
        raise ReportExportTokenError("invalid_export_token_signature")
    try:
        payload = json.loads(_base64url_decode(payload_part).decode("utf-8"))
    except Exception as exc:
        raise ReportExportTokenError("invalid_export_token_payload") from exc
    if not isinstance(payload, dict):
        raise ReportExportTokenError("invalid_export_token_payload")
    if payload.get("contract_version") != REPORT_EXPORT_TOKEN_CONTRACT:
        raise ReportExportTokenError("unsupported_export_token_contract")

    expected_hash = str(payload.get("markdown_sha256") or "").strip()
    supplied_hash = str(markdown_sha256 or "").strip()
    if not expected_hash or expected_hash != supplied_hash:
        raise ReportExportTokenError("export_token_markdown_hash_mismatch")

    expires_at = _parse_datetime(payload.get("expires_at"))
    if expires_at is None:
        raise ReportExportTokenError("export_token_missing_expiry")
    observed_at = _as_utc(now, name="now") if isinstance(now, datetime) else _utc_now()
    if observed_at > expires_at:
        raise ReportExportTokenError("export_token_expired")

    expected_actor = str(payload.get("actor_digest") or "").strip()
    supplied_actor = str(actor_digest or "").strip()
    if not expected_actor or expected_actor != supplied_actor:
        raise ReportExportTokenError("export_token_actor_mismatch")

    artifact_id = str(payload.get("artifact_id") or "").strip()
    if revoked_check is not None and bool(revoked_check(artifact_id)):
        raise ReportExportTokenError("export_token_revoked")
    if (
        bool(payload.get("one_time_use", True))
        and used_check is not None
        and bool(used_check(artifact_id))
    ):
        raise ReportExportTokenError("export_token_already_used")
    return payload


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ReportExportReceipt:
    """Digest-only delivery receipt for a report-export artifact.

    The receipt stores metadata and a deterministic digest.  A full
    ``artifact_token`` or token secret never appears on this value.
    """

    artifact_id: str
    markdown_sha256: str
    export_format: str
    trace_id: str | None
    request_id: str | None
    project_key: str | None
    job_id: int | None
    actor_digest: str
    issued_at: datetime
    expires_at: datetime
    delivery_state: str = "NOT_DELIVERED"
    receipt_digest: str = field(init=False, default="", repr=False)
    authority: ReportExportTokenAuthority = field(
        default_factory=ReportExportTokenAuthority
    )
    token_ref: str | None = field(default=None, repr=False, compare=False)
    token_payload_digest: str | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _require_text(self.artifact_id, name="artifact_id", max_length=128),
        )
        object.__setattr__(
            self,
            "markdown_sha256",
            _require_sha256_hex(self.markdown_sha256, name="markdown_sha256"),
        )
        export_format = str(self.export_format or "").strip().lower()
        if not export_format:
            raise ValueError("export_format is required")
        object.__setattr__(self, "export_format", export_format[:32])
        object.__setattr__(
            self,
            "trace_id",
            _clean_text(self.trace_id, max_length=128),
        )
        object.__setattr__(
            self,
            "request_id",
            _clean_text(self.request_id, max_length=128),
        )
        object.__setattr__(
            self,
            "project_key",
            _clean_text(self.project_key, max_length=64),
        )
        object.__setattr__(self, "job_id", _as_int_or_none(self.job_id))
        object.__setattr__(
            self,
            "actor_digest",
            _require_text(self.actor_digest, name="actor_digest", max_length=128),
        )
        issued_at = _as_utc(self.issued_at, name="issued_at")
        expires_at = _as_utc(self.expires_at, name="expires_at")
        if issued_at is None or expires_at is None:
            raise ValueError("issued_at and expires_at are required")
        object.__setattr__(self, "issued_at", issued_at)
        object.__setattr__(self, "expires_at", expires_at)
        delivery_state = str(self.delivery_state or "").strip().upper()
        if not delivery_state:
            raise ValueError("delivery_state is required")
        object.__setattr__(self, "delivery_state", delivery_state)
        if (self.token_ref is None) != (self.token_payload_digest is None):
            raise ValueError("token_ref and token_payload_digest are an exact pair")
        if self.token_payload_digest is not None:
            object.__setattr__(
                self,
                "token_payload_digest",
                _require_sha256_hex(
                    self.token_payload_digest,
                    name="token_payload_digest",
                ),
            )
        if not isinstance(self.authority, ReportExportTokenAuthority):
            raise TypeError("ReportExportReceipt.authority must be typed")
        digest_input: dict[str, Any] = {
            "schema": _RECEIPT_SCHEMA,
            "artifact_id": self.artifact_id,
            "markdown_sha256": self.markdown_sha256,
            "export_format": self.export_format,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "project_key": self.project_key,
            "job_id": self.job_id,
            "actor_digest": self.actor_digest,
            "issued_at": _isoformat_utc(self.issued_at),
            "expires_at": _isoformat_utc(self.expires_at),
            "delivery_state": self.delivery_state,
            "authority": self.authority.to_plain(),
        }
        if self.token_ref is not None:
            digest_input["token_ref"] = self.token_ref
            digest_input["token_payload_digest"] = self.token_payload_digest
        object.__setattr__(self, "receipt_digest", _stable_digest(digest_input))


def build_report_export_receipt(
    signing_input: ReportExportSigningInput,
    token: SignedReportExportToken | None = None,
) -> ReportExportReceipt:
    """Build a digest-only receipt from typed signing metadata.

    When ``token`` is provided, only its digest-bearing refs are folded into
    the receipt digest; the full signed token is never retained.
    """

    if not isinstance(signing_input, ReportExportSigningInput):
        raise TypeError("build_report_export_receipt requires typed signing input")
    if token is not None and not isinstance(token, SignedReportExportToken):
        raise TypeError("token must be a SignedReportExportToken")
    return ReportExportReceipt(
        artifact_id=signing_input.artifact_id,
        markdown_sha256=signing_input.markdown_sha256,
        export_format=signing_input.export_format,
        trace_id=signing_input.trace_id,
        request_id=signing_input.request_id,
        project_key=signing_input.project_key,
        job_id=signing_input.job_id,
        actor_digest=signing_input.actor_digest,
        issued_at=signing_input.issued_at,
        expires_at=signing_input.expires_at,
        delivery_state="NOT_DELIVERED",
        authority=ReportExportTokenAuthority(),
        token_ref=token.token_ref if token is not None else None,
        token_payload_digest=(token.payload_digest if token is not None else None),
    )
