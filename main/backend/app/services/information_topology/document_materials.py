"""Bind retrieval placements to the canonical material owner, transporting V1/V2."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from hashlib import sha256
from typing import TypeGuard

from app.models.entities import Material as Document
from app.services.document_queries import (
    DocumentQueryJsonObject,
    DocumentQueryJsonValue,
    coerce_document_query_result_row,
)
from app.services.document_queries.identity import (
    canonical_material_identity,
    document_identity,
    material_identity,
)
from app.services.document_queries.identity import (
    material_revision as document_revision,
)
from app.services.ingest.terminal_writer import persist_terminal_material_in_session
from functorial_kit import Failure
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .contracts import BoundRef, Element, ElementRef, TopologyState, topology_failures, topology_state_codec
from .modules.retrieval import PROFILE_ID_PREFIX, profile_from_state_payload
from .profiles import validate_state


def _is_object_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _identity_mapping(value: object) -> DocumentQueryJsonObject | None:
    if not _is_object_mapping(value):
        return None
    project_key = value.get("project_key")
    module_id = value.get("module_id")
    namespace = value.get("namespace")
    type_id = value.get("type_id")
    local_id = value.get("local_id")
    if not all(isinstance(item, str) for item in (project_key, module_id, namespace, type_id, local_id)):
        return None
    return coerce_document_query_result_row(value)


def _positive_int(value: DocumentQueryJsonValue) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def read_document(session: Session, project_key: str, ref: Mapping[str, object]) -> Document | None:
    local_id = ref.get("local_id")
    if not isinstance(local_id, str) or not local_id.isdigit() or int(local_id) <= 0:
        return None
    if canonical_material_identity(project_key, ref) is None:
        return None
    return session.execute(select(Document).where(Document.id == int(local_id))).scalar_one_or_none()


def resolve_document(session: Session, project_key: str, ref: ElementRef) -> BoundRef | None:
    if (ref.module_id, ref.namespace, ref.type_id) not in (
        ("materials", "materials", "material"), ("documents", "documents", "document"),
    ) or ref.project_key != project_key:
        return None
    if not ref.local_id.isdigit() or int(ref.local_id) <= 0:
        return None
    document = read_document(session, project_key, document_identity(ref.project_key, int(ref.local_id)))
    return (
        BoundRef(ref, _document_revision(document))
        if document
        else None
    )


def bind_material_documents(session: Session, state: TopologyState) -> TopologyState | Failure:
    """Move V1 source metadata once, preserving material IDs and all endpoints.

    A locator-only source becomes a Document with null content and explicit
    reference_only status. Missing material records remain unresolved and do not
    become documents. Existing Documents are never overwritten by a snapshot.
    """
    if not state.profile_id.startswith(PROFILE_ID_PREFIX):
        return state
    if state.profile_version.startswith("3+"):
        for element in state.elements:
            current_attrs = coerce_document_query_result_row(element.attributes)
            ref = _identity_mapping(current_attrs.get("material_ref"))
            if element.ref.ref.type_id == "material" and ref is not None:
                if read_document(session, element.ref.ref.project_key, ref) is None:
                    return topology_failures.fail(
                        "UNRESOLVABLE_REFERENCE", "material does not exist in this project"
                    )
        return state
    elements: list[Element] = []
    for element in state.elements:
        if element.ref.ref.type_id != "material":
            elements.append(element)
            continue
        attrs = coerce_document_query_result_row(element.attributes)
        project_key = element.ref.ref.project_key
        if attrs.get("reference_status") != "unresolved_reference":
            uri = str(attrs.get("url") or attrs.get("source_uri") or "").strip() or None
            origin = sha256(
                json.dumps(
                    {
                        "project": project_key,
                        "module": element.ref.ref.module_id,
                        "namespace": element.ref.ref.namespace,
                        "material": element.ref.ref.local_id,
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            explicit = attrs.get("material_ref", attrs.get("document_ref"))
            if attrs.get("material_ref") is not None and attrs.get("document_ref") is not None:
                legacy_ref = attrs["document_ref"]
                explicit_ref = _identity_mapping(explicit)
                legacy_ref_mapping = _identity_mapping(legacy_ref)
                current_identity = canonical_material_identity(project_key, explicit_ref) if explicit_ref is not None else None
                legacy_identity = canonical_material_identity(project_key, legacy_ref_mapping) if legacy_ref_mapping is not None else None
                if current_identity is None or current_identity != legacy_identity:
                    return topology_failures.fail("IDENTITY_CONFLICT", "material reference aliases disagree")
            if explicit is None and attrs.get("reference_status") == "body_read":
                snapshot_path = attrs.get("snapshot_path")
                snapshot_items = snapshot_path if isinstance(snapshot_path, list) else []
                ids = {
                    path.split(":", 1)[1]
                    for path in snapshot_items
                    if isinstance(path, str) and path.startswith(("document:", "material:"))
                }
                if len(ids) > 1 or any(not value.isdigit() or int(value) <= 0 for value in ids):
                    return topology_failures.fail(
                        "IDENTITY_CONFLICT", "material has conflicting native Document locators"
                    )
                if ids:
                    explicit = material_identity(project_key, int(next(iter(ids))))
            explicit_ref = _identity_mapping(explicit)
            if explicit_ref is not None:
                existing = read_document(session, project_key, explicit_ref)
                if existing is None:
                    return topology_failures.fail("UNRESOLVABLE_REFERENCE", "explicit material Document does not exist")
            else:
                session.execute(
                    select(
                        func.pg_advisory_xact_lock(
                            int(sha256((project_key + ":" + (uri or origin)).encode()).hexdigest()[:15], 16)
                        )
                    )
                )
                existing = session.execute(
                    select(Document).where(Document.extracted_data["topology_origin_key"].astext == origin)
                ).scalar_one_or_none()
            if existing is None and uri:
                matches = session.execute(select(Document).where(Document.uri == uri)).scalars().all()
                if len(matches) > 1:
                    return topology_failures.fail(
                        "IDENTITY_CONFLICT", "source URI resolves to several Documents", {"uri": uri}
                    )
                existing = matches[0] if matches else None
            if existing is None:
                result = persist_terminal_material_in_session(
                    session,
                    {
                        "source_name": "retrieval_materials",
                        "source_kind": "import",
                        "doc_type": "raw_note",
                        "title": attrs.get("title") or attrs.get("content_name"),
                        "summary": attrs.get("content_summary"),
                        "uri": uri,
                        "status": "reference_only",
                        "content": None,
                        "extracted_data": {"project_key": project_key, "topology_origin_key": origin},
                    },
                )
                normalized_result = coerce_document_query_result_row(result)
                document_id = _positive_int(normalized_result.get("material_id"))
                if document_id is None:
                    return topology_failures.fail(
                        "UNRESOLVABLE_REFERENCE", "material writer did not return a positive material_id"
                    )
            else:
                document_id = int(str(existing.id))
            attrs["material_ref"] = coerce_document_query_result_row(
                material_identity(project_key, document_id)
            )
        attrs.pop("document_ref", None)
        snapshot_value = attrs.get("snapshot_path")
        if isinstance(snapshot_value, list):
            attrs["snapshot_path"] = [
                "material:" + path.removeprefix("document:")
                if isinstance(path, str) and path.startswith("document:") else path
                for path in snapshot_value
            ]
        for key in ("title", "url", "content_name", "content_summary", "source_uri", "source_status"):
            attrs.pop(key, None)
        elements.append(replace(element, attributes=attrs))
    candidate = replace(
        state, profile_version="3+" + state.profile_version.split("+", 1)[-1], elements=tuple(elements)
    )
    profile = profile_from_state_payload(
        elements[0].ref.ref.project_key,
        candidate.profile_id,
        candidate.profile_version,
        topology_state_codec.to_wire(candidate),
    )
    if isinstance(profile, Failure):
        return profile
    failure = validate_state(profile, candidate)
    return failure if failure is not None else candidate


def project_document_materials(
    session: Session,
    project_key: str,
    wire: Mapping[str, object],
) -> DocumentQueryJsonObject:
    """Hydrate a read model only; source data is never written to topology state."""
    projected = coerce_document_query_result_row(wire)
    elements_value = projected.get("elements")
    if not isinstance(elements_value, list):
        return projected
    elements = elements_value
    for index, element_value in enumerate(elements):
        if not isinstance(element_value, dict):
            continue
        element = coerce_document_query_result_row(element_value)
        attrs_value = element.get("attributes")
        ref_container = element.get("ref")
        if not isinstance(attrs_value, dict) or not isinstance(ref_container, dict):
            continue
        attrs = coerce_document_query_result_row(attrs_value)
        bound_ref = coerce_document_query_result_row(ref_container)
        native_ref_value = bound_ref.get("ref")
        if not isinstance(native_ref_value, dict):
            continue
        native_ref = coerce_document_query_result_row(native_ref_value)
        ref = attrs.get("material_ref", attrs.get("document_ref"))
        ref_mapping = _identity_mapping(ref)
        if native_ref.get("type_id") != "material" or ref_mapping is None:
            continue
        document = read_document(session, project_key, ref_mapping)
        if document is None:
            attrs["reference_status"] = "unresolved_reference"
            element["attributes"] = attrs
            elements[index] = element
            continue
        document_id = int(str(document.id))
        attrs.update(
            coerce_document_query_result_row(
            {
                "material_ref": material_identity(project_key, document_id),
                "title": str(document.title or ""),
                "url": str(document.uri or ""),
                "content_name": str(document.title or ""),
                "source_uri": str(document.uri or ""),
                "content_summary": str(document.summary or ""),
                "source_status": str(document.status or ""),
                "material_revision": _document_revision(document),
            }
            )
        )
        element["attributes"] = attrs
        elements[index] = element
    projected["elements"] = elements
    return projected


bind_materials = bind_material_documents
project_materials = project_document_materials
resolve_material = resolve_document


def _runtime_value(value: object) -> object:
    return value


def _document_revision(document: Document) -> str:
    return document_revision({
        "updated_at": _runtime_value(document.updated_at),
        "text_hash": _runtime_value(document.text_hash),
    })
