"""Prepare material from an explicit starting point before any ingest writer runs.

The input kind describes availability, not the ontology of a source. In
particular, a URL is a locator and never document text. Existing C7 snapshots
keep their original identity; this module does not mint a C7 write closure.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Callable, Literal
from urllib.parse import urlsplit

from ...successor_runtime.capabilities.material_ingest_movements import RawSnapshot


class MaterialPreparationError(ValueError):
    """Input cannot be turned into supported text material."""


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
    raw_bytes: bytes,
    *,
    mime_type: str,
    input_kind: Literal["given", "resource", "snapshot"],
    source_locator: str | None,
    snapshot_ref: str | None = None,
    snapshot_identity_digest: str | None = None,
) -> PreparedMaterial | _MaterialRejection:
    if not isinstance(raw_bytes, bytes):
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
    fetch_resource: Callable[[str], FetchedResource] | None = None,
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
    if isinstance(material, ResourceRef):
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
    material: GivenContent | ResourceRef | RawSnapshot,
    *,
    fetch_resource: Callable[[str], FetchedResource] | None = None,
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
    "ResourceRef",
    "prepare_material",
    "prepare_resource_via_http_port",
]
