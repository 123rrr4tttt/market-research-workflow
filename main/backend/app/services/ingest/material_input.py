"""Prepare material from an explicit starting point before any ingest writer runs.

The input kind describes availability, not the ontology of a source. In
particular, a URL is a locator and never document text. Existing raw snapshots
keep their original identity; this module does not mint a write closure.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Callable, Literal, TypeGuard
from urllib.parse import urlsplit


def _is_bytes(value: object) -> TypeGuard[bytes]:
    return isinstance(value, bytes)


def _is_resource_ref(value: object) -> TypeGuard[ResourceRef]:
    return isinstance(value, ResourceRef)

from ...successor_runtime.capabilities.checksum import (
    content_digest,
    require_hex64,
    sha256_hex,
)


class MaterialPreparationError(ValueError):
    """Input cannot be turned into supported text material."""


def _required_text(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        # kit:boundary owner=ingest.material_input.raw_snapshot_invariant class=PROGRAMMER_DEFECT failure_family=none witness=test:test_raw_snapshot_constructor_rejects_invalid_fields_with_public_exception_types
        raise ValueError(f"{field_name} is required")
    return normalized


def _optional_refs(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    return tuple(
        normalized
        for item in values or ()
        if (normalized := str(item or "").strip())
    )


@dataclass(frozen=True, slots=True)
class RawSnapshot:
    """Exact immutable input bytes bound to a full material identity."""

    project_key: str
    source_locator: str
    raw_bytes: bytes
    raw_content_digest: str = ""
    revision: int = 1
    incarnation: str = "c7-raw-v1"
    mime_type: str = "application/octet-stream"
    provenance_refs: tuple[str, ...] = ()
    snapshot_identity_digest: str = ""
    snapshot_ref: str = ""

    def __post_init__(self) -> None:
        project_key = _required_text(self.project_key, "RawSnapshot.project_key")
        source_locator = _required_text(
            self.source_locator, "RawSnapshot.source_locator"
        )
        if not _is_bytes(self.raw_bytes):
            # kit:boundary owner=ingest.material_input.raw_snapshot_invariant class=PROGRAMMER_DEFECT failure_family=none witness=test:test_raw_snapshot_constructor_rejects_invalid_fields_with_public_exception_types
            raise TypeError("RawSnapshot.raw_bytes must be bytes")
        try:
            revision = int(self.revision)
        except (OverflowError, TypeError, ValueError) as exc:
            # kit:boundary owner=ingest.material_input.raw_snapshot_invariant class=PROGRAMMER_DEFECT failure_family=none witness=test:test_raw_snapshot_constructor_rejects_invalid_fields_with_public_exception_types
            raise type(exc)(str(exc)) from exc
        if revision < 1:
            # kit:boundary owner=ingest.material_input.raw_snapshot_invariant class=PROGRAMMER_DEFECT failure_family=none witness=test:test_raw_snapshot_constructor_rejects_invalid_fields_with_public_exception_types
            raise ValueError("RawSnapshot.revision must be >= 1")
        incarnation = _required_text(self.incarnation, "RawSnapshot.incarnation")
        mime_type = _required_text(
            self.mime_type or "application/octet-stream", "RawSnapshot.mime_type"
        )
        provenance_refs = _optional_refs(self.provenance_refs)
        computed = sha256_hex(self.raw_bytes)
        raw_content_digest = _required_text(
            self.raw_content_digest or computed, "RawSnapshot.raw_content_digest"
        )
        require_hex64(raw_content_digest, "RawSnapshot.raw_content_digest")
        if raw_content_digest != computed:
            # kit:boundary owner=ingest.material_input.raw_snapshot_invariant class=PROGRAMMER_DEFECT failure_family=none witness=test:test_existing_snapshot_identity_rejects_byte_and_identity_substitution
            raise ValueError(
                "RawSnapshot.raw_content_digest does not match raw bytes"
            )
        identity = content_digest(
            {
                "project_key": project_key,
                "source_locator": source_locator,
                "raw_content_digest": raw_content_digest,
                "revision": revision,
                "incarnation": incarnation,
                "mime_type": mime_type,
                "provenance_refs": provenance_refs,
            }
        )
        if self.snapshot_identity_digest and self.snapshot_identity_digest != identity:
            # kit:boundary owner=ingest.material_input.raw_snapshot_invariant class=PROGRAMMER_DEFECT failure_family=none witness=test:test_existing_snapshot_identity_rejects_byte_and_identity_substitution
            raise ValueError(
                "RawSnapshot.snapshot_identity_digest does not match identity fields"
            )
        snapshot_ref = f"material:raw:sha256:{identity}"
        if self.snapshot_ref and self.snapshot_ref != snapshot_ref:
            # kit:boundary owner=ingest.material_input.raw_snapshot_invariant class=PROGRAMMER_DEFECT failure_family=none witness=test:test_existing_snapshot_identity_rejects_byte_and_identity_substitution
            raise ValueError("RawSnapshot.snapshot_ref does not match full identity")
        object.__setattr__(self, "project_key", project_key)
        object.__setattr__(self, "source_locator", source_locator)
        object.__setattr__(self, "revision", revision)
        object.__setattr__(self, "incarnation", incarnation)
        object.__setattr__(self, "mime_type", mime_type)
        object.__setattr__(self, "provenance_refs", provenance_refs)
        object.__setattr__(self, "raw_content_digest", raw_content_digest)
        object.__setattr__(self, "snapshot_identity_digest", identity)
        object.__setattr__(self, "snapshot_ref", snapshot_ref)

    @property
    def content_digest(self) -> str:
        return self.raw_content_digest


@dataclass(frozen=True, slots=True)
class GivenContent:
    raw_bytes: bytes
    mime_type: str = "text/plain"
    source_locator: str | None = None

    @classmethod
    def from_text(cls, text: str, *, source_locator: str | None = None) -> "GivenContent":
        return cls(text.encode("utf-8"), source_locator=source_locator)


@dataclass(frozen=True, slots=True)
class ResourceRef:
    url: str


@dataclass(frozen=True, slots=True)
class FetchedResource:
    raw_bytes: bytes
    mime_type: str
    final_url: str


@dataclass(frozen=True, slots=True)
class PreparedMaterial:
    input_kind: Literal["given", "resource", "snapshot"]
    raw_bytes: bytes
    raw_content_digest: str
    mime_type: str
    text: str
    source_locator: str | None
    snapshot_ref: str | None = None
    snapshot_identity_digest: str | None = None


@dataclass(frozen=True, slots=True)
class _MaterialRejection:
    message: str
    cause: BaseException | None = None


_TEXT_MIME_TYPES = frozenset({"text/plain", "text/markdown"})


def _prepare_bytes(
    raw_bytes: object,
    *,
    mime_type: str,
    input_kind: Literal["given", "resource", "snapshot"],
    source_locator: str | None,
    snapshot_ref: str | None = None,
    snapshot_identity_digest: str | None = None,
) -> PreparedMaterial | _MaterialRejection:
    if not _is_bytes(raw_bytes):
        return _MaterialRejection("material bytes are required")
    normalized_mime = str(mime_type or "").split(";", 1)[0].strip().lower()
    if normalized_mime not in _TEXT_MIME_TYPES:
        return _MaterialRejection(f"unsupported material MIME type: {mime_type}")
    try:
        text = raw_bytes.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        return _MaterialRejection("material must be valid UTF-8", cause=exc)
    if not text:
        return _MaterialRejection("material text is empty")
    return PreparedMaterial(
        input_kind=input_kind,
        raw_bytes=raw_bytes,
        raw_content_digest=sha256(raw_bytes).hexdigest(),
        mime_type=normalized_mime,
        text=text,
        source_locator=source_locator,
        snapshot_ref=snapshot_ref,
        snapshot_identity_digest=snapshot_identity_digest,
    )


def _try_prepare_material(
    material: GivenContent | ResourceRef | RawSnapshot,
    *,
    fetch_resource: Callable[[str], object] | None = None,
) -> PreparedMaterial | _MaterialRejection:

    if isinstance(material, GivenContent):
        return _prepare_bytes(
            material.raw_bytes,
            mime_type=material.mime_type,
            input_kind="given",
            source_locator=material.source_locator,
        )
    if isinstance(material, RawSnapshot):
        prepared = _prepare_bytes(
            material.raw_bytes,
            mime_type=material.mime_type,
            input_kind="snapshot",
            source_locator=material.source_locator,
            snapshot_ref=material.snapshot_ref,
            snapshot_identity_digest=material.snapshot_identity_digest,
        )
        if isinstance(prepared, _MaterialRejection):
            return prepared
        if prepared.raw_content_digest != material.raw_content_digest:
            return _MaterialRejection("snapshot digest does not match its bytes")
        return prepared
    if _is_resource_ref(material):
        url = str(material.url).strip()
        try:
            parts = urlsplit(url)
        except ValueError as exc:
            return _MaterialRejection("resource must have an HTTP(S) URL", cause=exc)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            return _MaterialRejection("resource must have an HTTP(S) URL")
        if fetch_resource is None:
            return _MaterialRejection("resource fetch port is required")
        fetched = fetch_resource(url)
        if not isinstance(fetched, FetchedResource):
            return _MaterialRejection("resource fetch port returned an invalid result")
        return _prepare_bytes(
            fetched.raw_bytes,
            mime_type=fetched.mime_type,
            input_kind="resource",
            source_locator=fetched.final_url or url,
        )
    return _MaterialRejection("unsupported material input")


def prepare_material(
    material: object,
    *,
    fetch_resource: Callable[[str], object] | None = None,
) -> PreparedMaterial:
    """Prepare supported text; preserve the public exception contract."""

    if not isinstance(material, (GivenContent, ResourceRef, RawSnapshot)):
        # kit:boundary owner=ingest.material_input.public_api class=PROGRAMMER_DEFECT failure_family=none witness=test:test_unsupported_material_input_is_programmer_error
        raise TypeError("unsupported material input")
    result = _try_prepare_material(material, fetch_resource=fetch_resource)
    if isinstance(result, _MaterialRejection):
        # kit:boundary owner=ingest.material_input.public_api class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_preparation_rejects_unsupported_or_invalid_bytes
        raise MaterialPreparationError(result.message) from result.cause
    return result


def prepare_resource_via_http_port(
    resource: ResourceRef,
    *,
    timeout: float = 8.0,
) -> PreparedMaterial:
    """Use the registered resource-pool fetch port for a text resource.

    The existing port owns redirects, transport errors, and HTTP policy. This
    adapter only transfers its actual response bytes and MIME into preparation.
    """

    from ..resource_pool.http_port import fetch_html

    def fetch(url: str) -> FetchedResource:
        _html, response = fetch_html(url, timeout=timeout, retries=1)
        mime_type = next(
            (value for name, value in response.headers.items() if name.lower() == "content-type"),
            "application/octet-stream",
        )
        return FetchedResource(
            raw_bytes=response.content,
            mime_type=mime_type,
            final_url=response.final_url,
        )

    return prepare_material(resource, fetch_resource=fetch)


__all__ = [
    "FetchedResource",
    "GivenContent",
    "MaterialPreparationError",
    "PreparedMaterial",
    "RawSnapshot",
    "ResourceRef",
    "prepare_material",
    "prepare_resource_via_http_port",
]
