"""Bind retrieval material placements to the existing canonical Document owner."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from collections.abc import Mapping
from typing import Any

from functorial_kit import Failure
from sqlalchemy import func, select

from app.models.entities import Document
from app.services.ingest.terminal_writer import persist_terminal_document_in_session
from app.services.document_queries.identity import document_identity, document_revision

from .contracts import BoundRef, Element, ElementRef, TopologyState, topology_failures, topology_state_codec
from .modules.retrieval import PROFILE_ID_PREFIX, profile_from_state_payload
from .profiles import validate_state


def read_document(session: Any, project_key: str, ref: Mapping[str, Any]) -> Document | None:
    local_id = ref.get("local_id")
    if not isinstance(local_id, str) or not local_id.isdigit() or int(local_id) <= 0:
        return None
    if ref != document_identity(project_key, int(local_id)):
        return None
    return session.execute(select(Document).where(Document.id == int(ref["local_id"]))).scalar_one_or_none()


def resolve_document(session: Any, project_key: str, ref: ElementRef):
    if (ref.module_id, ref.namespace, ref.type_id) != ("documents", "documents", "document"):
        return None
    if not ref.local_id.isdigit() or int(ref.local_id) <= 0:
        return None
    document = read_document(session, project_key, document_identity(ref.project_key, int(ref.local_id)))
    return (
        BoundRef(ElementRef(**document_identity(project_key, document.id)), document_revision(document))
        if document
        else None
    )


def bind_material_documents(session: Any, state: TopologyState) -> TopologyState | Failure:
    """Move V1 source metadata once, preserving material IDs and all endpoints.

    A locator-only source becomes a Document with null content and explicit
    reference_only status. Missing material records remain unresolved and do not
    become documents. Existing Documents are never overwritten by a snapshot.
    """
    if not state.profile_id.startswith(PROFILE_ID_PREFIX):
        return state
    if state.profile_version.startswith("2+"):
        for element in state.elements:
            ref = element.attributes.get("document_ref")
            if element.ref.ref.type_id == "material" and isinstance(ref, Mapping):
                if read_document(session, element.ref.ref.project_key, ref) is None:
                    return topology_failures.fail(
                        "UNRESOLVABLE_REFERENCE", "material Document does not exist in this project"
                    )
        return state
    elements: list[Element] = []
    for element in state.elements:
        if element.ref.ref.type_id != "material":
            elements.append(element)
            continue
        attrs = dict(element.attributes)
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
            explicit = attrs.get("document_ref")
            if explicit is None and attrs.get("reference_status") == "body_read":
                ids = {
                    path.removeprefix("document:")
                    for path in attrs.get("snapshot_path", [])
                    if isinstance(path, str) and path.startswith("document:")
                }
                if len(ids) > 1 or any(not value.isdigit() or int(value) <= 0 for value in ids):
                    return topology_failures.fail(
                        "IDENTITY_CONFLICT", "material has conflicting native Document locators"
                    )
                if ids:
                    explicit = document_identity(project_key, int(next(iter(ids))))
            if isinstance(explicit, Mapping):
                existing = read_document(session, project_key, explicit)
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
                result = persist_terminal_document_in_session(
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
                document_id = result["doc_id"]
            else:
                document_id = existing.id
            attrs["document_ref"] = document_identity(project_key, document_id)
        for key in ("title", "url", "content_name", "content_summary", "source_uri", "source_status"):
            attrs.pop(key, None)
        elements.append(replace(element, attributes=attrs))
    candidate = replace(
        state, profile_version="2+" + state.profile_version.removeprefix("1+"), elements=tuple(elements)
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


def project_document_materials(session: Any, project_key: str, wire: dict[str, Any]) -> dict[str, Any]:
    """Hydrate a read model only; source data is never written to topology state."""
    for element in wire["elements"]:
        attrs = element["attributes"]
        ref = attrs.get("document_ref")
        if element["ref"]["ref"]["type_id"] != "material" or not isinstance(ref, Mapping):
            continue
        document = read_document(session, project_key, ref)
        if document is None:
            attrs["reference_status"] = "unresolved_reference"
            continue
        attrs.update(
            {
                "title": document.title or "",
                "url": document.uri or "",
                "content_name": document.title or "",
                "source_uri": document.uri or "",
                "content_summary": document.summary or "",
                "source_status": document.status or "",
                "document_id": document.id,
                "document_revision": document_revision(document),
            }
        )
    return wire
