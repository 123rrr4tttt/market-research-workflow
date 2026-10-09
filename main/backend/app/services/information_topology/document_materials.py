"""Bind retrieval placements to the canonical Material owner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from hashlib import sha256
from pathlib import Path
from typing import Sequence, TypeGuard, cast

from app.models.entities import Material
from app.services.document_queries import (
    MaterialQueryJsonObject,
    MaterialQueryJsonValue,
    coerce_material_query_result_row,
)
from app.services.document_queries.identity import (
    canonical_material_identity,
    material_identity,
    material_revision,
)
from app.services.ingest.local_snapshot import LocalSnapshotResult, prepare_local_snapshot
from app.services.ingest.terminal_writer import persist_terminal_material_in_session
from functorial_kit import Failure
from sqlalchemy import select
from sqlalchemy.orm import Session

from .contracts import BoundRef, Element, ElementRef, TopologyState, topology_failures, topology_state_codec
from .modules.retrieval import PROFILE_ID_PREFIX, profile_from_state_payload
from .profiles import validate_state


@dataclass(slots=True)
class MaterialBindingLedger:
    created_material_ids: set[int] = field(default_factory=lambda: set[int]())
    reused_material_ids: set[int] = field(default_factory=lambda: set[int]())
    bound_placements: int = 0
    unresolved_placements: int = 0

    def record_created(self, material_id: int) -> None:
        self.created_material_ids.add(material_id)
        self.bound_placements += 1

    def record_reused(self, material_id: int) -> None:
        self.reused_material_ids.add(material_id)
        self.bound_placements += 1


@dataclass(frozen=True, slots=True)
class _LegacyPlacement:
    state_index: int
    element_index: int
    element: Element
    attributes: MaterialQueryJsonObject


@dataclass(frozen=True, slots=True)
class _MaterialGroupResolution:
    material_id: int | None
    unresolved: bool = False
    source_evidence: tuple[MaterialQueryJsonObject, ...] = ()


def _is_object_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _identity_mapping(value: object) -> MaterialQueryJsonObject | None:
    if not _is_object_mapping(value):
        return None
    keys = ("project_key", "module_id", "namespace", "type_id", "local_id")
    if set(value) != set(keys) or not all(isinstance(value[key], str) for key in keys):
        return None
    return coerce_material_query_result_row(value)


def _positive_int(value: MaterialQueryJsonValue) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _legacy_material_identity(project_key: str, ref: object) -> MaterialQueryJsonObject | None:
    mapping = _identity_mapping(ref)
    if mapping is None:
        return None
    if canonical_material_identity(project_key, mapping) is not None:
        return mapping
    local_id = str(mapping.get("local_id", ""))
    if (
        mapping.get("project_key") == project_key
        and mapping.get("module_id") == "documents"
        and mapping.get("namespace") == "documents"
        and mapping.get("type_id") == "document"
        and local_id.isdigit()
        and int(local_id) > 0
    ):
        return coerce_material_query_result_row(material_identity(project_key, int(local_id)))
    return None


def _project_value(material: Material) -> str | None:
    value = material.extracted_data.get("project_key") if isinstance(material.extracted_data, Mapping) else None
    return str(value) if value is not None else None


def _belongs_to_project(material: Material, project_key: str) -> bool:
    material_project = _project_value(material)
    return material_project is None or material_project == project_key


def _existing_material(
    session: Session,
    project_key: str,
    *,
    uri: str | None = None,
    text_hash: str | None = None,
) -> Material | Failure | None:
    if uri is None and text_hash is None:
        return None
    predicate = Material.uri == uri if uri is not None else Material.text_hash == text_hash
    matches = list(session.execute(select(Material).where(predicate)).scalars().all())
    if len(matches) > 1:
        return topology_failures.fail(
            "IDENTITY_CONFLICT", "several existing Materials match one legacy source identity"
        )
    if not matches:
        return None
    material = matches[0]
    if not _belongs_to_project(material, project_key):
        return topology_failures.fail(
            "IDENTITY_CONFLICT", "legacy source resolves to a Material outside the active project"
        )
    return material


def read_material(session: Session, project_key: str, ref: Mapping[str, object]) -> Material | None:
    local_id = ref.get("local_id")
    if not isinstance(local_id, str) or not local_id.isdigit() or int(local_id) <= 0:
        return None
    if canonical_material_identity(project_key, ref) is None:
        return None
    material = session.execute(select(Material).where(Material.id == int(local_id))).scalar_one_or_none()
    if material is None or not _belongs_to_project(material, project_key):
        return None
    return material


def resolve_material(session: Session, project_key: str, ref: ElementRef) -> BoundRef | None:
    if (ref.module_id, ref.namespace, ref.type_id) != ("materials", "materials", "material"):
        return None
    if ref.project_key != project_key or not ref.local_id.isdigit() or int(ref.local_id) <= 0:
        return None
    material = read_material(session, project_key, material_identity(ref.project_key, int(ref.local_id)))
    revision_source: Mapping[str, object] = {
        "updated_at": material.updated_at,
        "text_hash": material.text_hash,
    } if material else {}
    return BoundRef(ref, material_revision(revision_source)) if material else None


class MaterialBinder:
    """Validate current placements without accepting legacy transport."""

    def __init__(self) -> None:
        self.ledger = MaterialBindingLedger()

    def bind(self, session: Session, state: TopologyState) -> TopologyState | Failure:
        if not state.profile_id.startswith(PROFILE_ID_PREFIX):
            return state
        if not state.profile_version.startswith("3+"):
            return topology_failures.fail(
                "INVALID_STRUCTURE", "legacy material transport is accepted only by the migration entry"
            )
        return self._validate_bound_state(session, state)

    def _validate_bound_state(self, session: Session, state: TopologyState) -> TopologyState | Failure:
        for element in state.elements:
            if element.ref.ref.type_id != "material":
                continue
            attrs = coerce_material_query_result_row(element.attributes)
            if attrs.get("document_ref") is not None:
                return topology_failures.fail(
                    "INVALID_STRUCTURE", "current material placement cannot use a Document reference"
                )
            if any(locator.startswith("document:") for locator in _snapshot_locators(attrs)):
                return topology_failures.fail(
                    "INVALID_STRUCTURE", "current material placement cannot use a documents locator"
                )
            ref = _identity_mapping(attrs.get("material_ref"))
            if attrs.get("reference_status") == "unresolved_reference":
                if ref is not None:
                    return topology_failures.fail("INVALID_STRUCTURE", "unresolved material cannot claim a body owner")
                self.ledger.unresolved_placements += 1
                continue
            if ref is None or canonical_material_identity(element.ref.ref.project_key, ref) is None:
                return topology_failures.fail("INVALID_STRUCTURE", "material requires a canonical Material reference")
            if read_material(session, element.ref.ref.project_key, ref) is None:
                return topology_failures.fail(
                    "UNRESOLVABLE_REFERENCE", "material does not exist in this project"
                )
            local_id = ref.get("local_id")
            if not isinstance(local_id, str):
                return topology_failures.fail("INVALID_STRUCTURE", "material identity is malformed")
            self.ledger.record_reused(int(local_id))
        return state


def _legacy_group_key(project_key: str, element: Element) -> tuple[str, str, str, str, str] | Failure:
    ref = element.ref.ref
    identity = (ref.project_key, ref.module_id, ref.namespace, ref.type_id, ref.local_id)
    if ref.project_key != project_key or any(not value for value in identity):
        return topology_failures.fail(
            "IDENTITY_CONFLICT", "legacy material placement crosses project or lacks an identity"
        )
    return identity


def _snapshot_locators(attrs: Mapping[str, object]) -> tuple[str, ...]:
    value = attrs.get("snapshot_path")
    if not isinstance(value, list):
        return ()
    return tuple(dict.fromkeys(
        item.strip() for item in cast(list[object], value) if isinstance(item, str) and item.strip()
    ))


def _native_material_id(project_key: str, placement: _LegacyPlacement) -> int | Failure | None:
    attrs = placement.attributes
    ids: set[int] = set()
    for key in ("material_ref", "document_ref"):
        raw = attrs.get(key)
        ref = _legacy_material_identity(project_key, raw)
        if raw is not None and ref is None:
            return topology_failures.fail("IDENTITY_CONFLICT", f"legacy {key} is invalid")
        if ref is not None:
            local_id = ref.get("local_id")
            if not isinstance(local_id, str):
                return topology_failures.fail("IDENTITY_CONFLICT", f"legacy {key} is invalid")
            ids.add(int(local_id))
    for locator in _snapshot_locators(attrs):
        if locator.startswith(("material:", "document:")):
            local_id = locator.split(":", 1)[1]
            if not local_id.isdigit() or int(local_id) <= 0:
                return topology_failures.fail(
                    "IDENTITY_CONFLICT", "legacy native material locator is invalid"
                )
            ids.add(int(local_id))
    if len(ids) > 1:
        return topology_failures.fail(
            "IDENTITY_CONFLICT", "legacy material placements disagree on their native Material identity"
        )
    return next(iter(ids)) if ids else None


def _declared_primary_locator(placements: Sequence[_LegacyPlacement]) -> str | Failure | None:
    declared = {
        value.strip()
        for placement in placements
        for key in ("primary_snapshot_path", "primary_source_locator")
        for value in (placement.attributes.get(key),)
        if isinstance(value, str) and value.strip()
    }
    if len(declared) > 1:
        return topology_failures.fail(
            "IDENTITY_CONFLICT", "legacy material placements declare several primary snapshots"
        )
    return next(iter(declared)) if declared else None


def _legacy_identity_record(
    identity: tuple[str, str, str, str, str],
) -> MaterialQueryJsonObject:
    return coerce_material_query_result_row({
        "project_key": identity[0],
        "module_id": identity[1],
        "namespace": identity[2],
        "type_id": identity[3],
        "local_id": identity[4],
    })


def _source_evidence_records(
    identity: tuple[str, str, str, str, str],
    locators: Sequence[str],
    snapshots: Sequence[LocalSnapshotResult],
    *,
    selected_locator: str | None,
    material_text_hash: str | None,
    unread_reason: str = "not_read",
) -> tuple[MaterialQueryJsonObject, ...]:
    by_locator = {snapshot.locator: snapshot for snapshot in snapshots}
    legacy_identity = _legacy_identity_record(identity)
    records: list[MaterialQueryJsonObject] = []
    for locator in locators:
        snapshot = by_locator.get(locator)
        snapshot_text_hash = (
            sha256(snapshot.content.encode("utf-8")).hexdigest()
            if snapshot is not None and snapshot.content is not None
            else None
        )
        records.append(coerce_material_query_result_row({
            "locator": locator,
            "raw_sha256": snapshot.raw_sha256 if snapshot is not None else None,
            "mime_type": snapshot.mime_type if snapshot is not None else None,
            "extractor": snapshot.extractor if snapshot is not None else None,
            "extraction_status": snapshot.extraction_status if snapshot is not None else "reference_only",
            "reason": snapshot.reason if snapshot is not None else unread_reason,
            "snapshot_text_hash": snapshot_text_hash,
            "material_text_hash": material_text_hash,
            "selected_for_material_body": locator == selected_locator,
            "legacy_material_identity": legacy_identity,
        }))
    return tuple(records)


def _merge_created_material_evidence(
    session: Session,
    material: Material,
    evidence: Sequence[MaterialQueryJsonObject],
) -> None:
    extracted = dict(material.extracted_data) if isinstance(material.extracted_data, Mapping) else {}
    prior_value = extracted.get("migration_source_evidence")
    prior = [
        coerce_material_query_result_row(item)
        for item in cast(list[object], prior_value)
        if _is_object_mapping(item)
    ] if isinstance(prior_value, list) else []
    for record in evidence:
        if record not in prior:
            prior.append(record)
    extracted["migration_source_evidence"] = prior
    material.extracted_data = extracted
    session.flush()


def _select_title(
    placements: Sequence[_LegacyPlacement],
    snapshots: Sequence[LocalSnapshotResult],
) -> tuple[str | None, str | None]:
    source_titles = {
        str(snapshot.source_title or "").strip()
        for snapshot in snapshots
        if str(snapshot.source_title or "").strip()
    }
    placement_titles = {
        str(placement.attributes.get("title") or "").strip()
        for placement in placements
        if str(placement.attributes.get("title") or "").strip()
    }
    if len(source_titles) == 1:
        return next(iter(source_titles)), None
    if len(source_titles) > 1:
        return None, "source_title_conflict"
    if len(placement_titles) == 1:
        return next(iter(placement_titles)), None
    if len(placement_titles) > 1:
        return None, "placement_title_conflict"
    return None, "title_missing"


def _select_body(
    snapshots: Sequence[LocalSnapshotResult],
    primary_locator: str | None,
) -> tuple[str | None, str | None, str | None]:
    bodies: dict[str, tuple[str, set[str]]] = {}
    for snapshot in snapshots:
        content = snapshot.content
        locator = snapshot.locator
        if isinstance(content, str) and content:
            digest = sha256(content.encode("utf-8")).hexdigest()
            prior = bodies.setdefault(digest, (content, set()))
            prior[1].add(locator)
    if primary_locator is not None:
        selected = [(body, primary_locator) for body, locators in bodies.values() if primary_locator in locators]
        if len(selected) != 1:
            return None, None, "declared_primary_body_unavailable"
        body, locator = selected[0]
        return body, locator, None
    if len(bodies) == 1:
        body, locators = next(iter(bodies.values()))
        return body, sorted(locators)[0], None
    if len(bodies) > 1:
        return None, None, "body_selection_conflict"
    reasons = sorted({
        str(snapshot.reason or "").strip()
        for snapshot in snapshots
        if str(snapshot.reason or "").strip()
    })
    return None, None, reasons[0] if len(reasons) == 1 else "body_unavailable"


def _persist_legacy_group(
    session: Session,
    project_key: str,
    identity: tuple[str, str, str, str, str],
    placements: Sequence[_LegacyPlacement],
    *,
    source_root: Path | None,
    created_material_ids: set[int],
) -> _MaterialGroupResolution | Failure:
    locators = tuple(dict.fromkeys(
        locator
        for placement in placements
        for locator in _snapshot_locators(placement.attributes)
        if not locator.startswith(("material:", "document:"))
    ))
    urls = {
        str(placement.attributes.get(key) or "").strip()
        for placement in placements
        for key in ("url", "source_uri")
        if str(placement.attributes.get(key) or "").strip()
    }
    evidence_locators = tuple(dict.fromkeys((*locators, *sorted(urls))))
    unresolved = [
        placement for placement in placements
        if placement.attributes.get("reference_status") == "unresolved_reference"
    ]
    if unresolved:
        if len(unresolved) != len(placements):
            return topology_failures.fail(
                "IDENTITY_CONFLICT", "one legacy material identity is both resolved and unresolved"
            )
        for placement in placements:
            native_id = _native_material_id(project_key, placement)
            if isinstance(native_id, Failure):
                return native_id
            if native_id is not None:
                return topology_failures.fail(
                    "IDENTITY_CONFLICT", "unresolved legacy material cannot claim a body owner"
                )
        return _MaterialGroupResolution(
            None,
            unresolved=True,
            source_evidence=_source_evidence_records(
                identity,
                evidence_locators,
                (),
                selected_locator=None,
                material_text_hash=None,
                unread_reason="unresolved_reference",
            ),
        )

    native_ids: set[int] = set()
    for placement in placements:
        native_id = _native_material_id(project_key, placement)
        if isinstance(native_id, Failure):
            return native_id
        if native_id is not None:
            native_ids.add(native_id)
    if len(native_ids) > 1:
        return topology_failures.fail(
            "IDENTITY_CONFLICT", "one legacy material identity resolves to several Materials"
        )
    if native_ids:
        material_id = next(iter(native_ids))
        if read_material(session, project_key, material_identity(project_key, material_id)) is None:
            return topology_failures.fail(
                "UNRESOLVABLE_REFERENCE", "legacy Material identity does not exist in this project"
            )
        return _MaterialGroupResolution(
            material_id,
            source_evidence=_source_evidence_records(
                identity,
                evidence_locators,
                (),
                selected_locator=None,
                material_text_hash=None,
                unread_reason="existing_material_identity",
            ),
        )

    uri_candidates = urls or set(locators)
    uri = next(iter(uri_candidates)) if len(uri_candidates) == 1 else None
    existing = _existing_material(session, project_key, uri=uri)
    if isinstance(existing, Failure):
        return existing
    if existing is not None:
        return _MaterialGroupResolution(
            int(existing.id),
            source_evidence=_source_evidence_records(
                identity,
                evidence_locators,
                (),
                selected_locator=None,
                material_text_hash=str(existing.text_hash or "") or None,
                unread_reason="existing_material_uri",
            ),
        )

    local_locators = tuple(
        locator for locator in locators if not locator.startswith(("http://", "https://"))
    )
    if local_locators and source_root is None:
        return topology_failures.fail(
            "INVALID_STRUCTURE",
            "local snapshot migration requires an explicit source root",
            {"reason": "source_root_required", "project_key": project_key},
        )

    snapshots: list[LocalSnapshotResult] = []
    if source_root is not None:
        for locator in local_locators:
            snapshot = prepare_local_snapshot(
                project_key=project_key,
                source_root=source_root,
                locator=locator,
            )
            if isinstance(snapshot, Failure):
                return snapshot
            snapshots.append(snapshot)

    primary = _declared_primary_locator(placements)
    if isinstance(primary, Failure):
        return primary
    title, title_reason = _select_title(placements, snapshots)
    content, selected_locator, body_reason = _select_body(snapshots, primary)
    text_hash = sha256(content.encode("utf-8")).hexdigest() if content is not None else None
    source_evidence = _source_evidence_records(
        identity,
        evidence_locators,
        snapshots,
        selected_locator=selected_locator,
        material_text_hash=text_hash,
    )
    existing = _existing_material(session, project_key, text_hash=text_hash)
    if isinstance(existing, Failure):
        return existing
    if existing is not None:
        material_id = int(existing.id)
        if material_id in created_material_ids:
            _merge_created_material_evidence(session, existing, source_evidence)
        return _MaterialGroupResolution(material_id, source_evidence=source_evidence)
    payload: dict[str, object] = {
        "source_name": "retrieval_materials",
        "source_kind": "import",
        "material_type": "raw_note",
        "title": title,
        "summary": None,
        "uri": uri,
        "status": "reference_only" if content is None else (
            "partial" if any(snapshot.extraction_status == "partial" for snapshot in snapshots) else "active"
        ),
        "content": content,
        "text_hash": text_hash,
        "extracted_data": {
            "project_key": project_key,
            "legacy_material_identity": _legacy_identity_record(identity),
            "migration_source_evidence": list(source_evidence),
            "migration_decision": {
                "title_reason": title_reason,
                "body_reason": body_reason,
                "selected_source_locator": selected_locator,
            },
        },
    }
    written = persist_terminal_material_in_session(session, payload)
    if isinstance(written, Failure):
        return written
    result = coerce_material_query_result_row(written)
    material_id = _positive_int(result.get("material_id"))
    if material_id is None:
        return topology_failures.fail(
            "UNRESOLVABLE_REFERENCE", "material writer did not return a positive material_id"
        )
    if _positive_int(result.get("inserted")) == 1:
        created_material_ids.add(material_id)
    return _MaterialGroupResolution(material_id, source_evidence=source_evidence)


def migrate_legacy_material_states(
    session: Session,
    project_key: str,
    states: Sequence[TopologyState],
    *,
    source_root: Path | None = None,
) -> tuple[TopologyState, ...] | Failure:
    """Migrate all current states after grouping every legacy placement identity."""
    groups: dict[tuple[str, str, str, str, str], list[_LegacyPlacement]] = {}
    for state_index, state in enumerate(states):
        if not state.profile_id.startswith(PROFILE_ID_PREFIX) or state.profile_version.startswith("3+"):
            continue
        for element_index, element in enumerate(state.elements):
            if element.ref.ref.type_id != "material":
                continue
            key = _legacy_group_key(project_key, element)
            if isinstance(key, Failure):
                return key
            groups.setdefault(key, []).append(_LegacyPlacement(
                state_index,
                element_index,
                element,
                coerce_material_query_result_row(element.attributes),
            ))

    resolutions: dict[tuple[str, str, str, str, str], _MaterialGroupResolution] = {}
    created_material_ids: set[int] = set()
    for identity in sorted(groups):
        resolution = _persist_legacy_group(
            session,
            project_key,
            identity,
            groups[identity],
            source_root=source_root,
            created_material_ids=created_material_ids,
        )
        if isinstance(resolution, Failure):
            return resolution
        resolutions[identity] = resolution

    migrated = list(states)
    for state_index, state in enumerate(states):
        if not state.profile_id.startswith(PROFILE_ID_PREFIX) or state.profile_version.startswith("3+"):
            continue
        elements = list(state.elements)
        for element_index, element in enumerate(elements):
            if element.ref.ref.type_id != "material":
                continue
            key = _legacy_group_key(project_key, element)
            if isinstance(key, Failure):
                return key
            resolution = resolutions[key]
            attrs = coerce_material_query_result_row(element.attributes)
            placement_source_locators = {
                locator
                for locator in _snapshot_locators(attrs)
                if not locator.startswith(("document:", "material:"))
            }
            placement_source_locators.update(
                value.strip()
                for name in ("url", "source_uri")
                for value in (attrs.get(name),)
                if isinstance(value, str) and value.strip()
            )
            placement_title = str(attrs.get("title") or "").strip()
            if placement_title:
                attrs["placement_title"] = placement_title
            for name in (
                "title", "url", "content_name", "content_summary", "source_uri",
                "source_status", "document_ref", "primary_snapshot_path", "primary_source_locator",
            ):
                attrs.pop(name, None)
            snapshot_path = attrs.get("snapshot_path")
            if isinstance(snapshot_path, list):
                retained_locators = [
                    item
                    for item in cast(list[MaterialQueryJsonValue], snapshot_path)
                    if not isinstance(item, str) or not item.startswith(("document:", "material:"))
                ]
                if retained_locators:
                    attrs["snapshot_path"] = retained_locators
                else:
                    attrs.pop("snapshot_path", None)
            placement_evidence = [
                record
                for record in resolution.source_evidence
                if record.get("locator") in placement_source_locators
            ]
            if placement_evidence:
                attrs.update(coerce_material_query_result_row({
                    "migration_source_evidence": placement_evidence,
                }))
            else:
                attrs.pop("migration_source_evidence", None)
            if resolution.unresolved:
                attrs.pop("material_ref", None)
            elif resolution.material_id is not None:
                attrs["material_ref"] = coerce_material_query_result_row(
                    material_identity(project_key, resolution.material_id)
                )
            elements[element_index] = replace(element, attributes=attrs)
        candidate = replace(
            state,
            profile_version="3+" + state.profile_version.split("+", 1)[-1],
            elements=tuple(elements),
        )
        profile = profile_from_state_payload(
            project_key,
            candidate.profile_id,
            candidate.profile_version,
            topology_state_codec.to_wire(candidate),
        )
        if isinstance(profile, Failure):
            return profile
        failure = validate_state(profile, candidate)
        if failure is not None:
            return failure
        migrated[state_index] = candidate
    return tuple(migrated)


def bind_materials(session: Session, state: TopologyState) -> TopologyState | Failure:
    """Bind a newly authored retrieval state without accepting legacy transport."""
    return MaterialBinder().bind(session, state)


def project_materials(
    session: Session,
    project_key: str,
    wire: Mapping[str, object],
) -> MaterialQueryJsonObject:
    """Hydrate a read model only; source data is never written to topology state."""
    projected = coerce_material_query_result_row(wire)
    elements_value = projected.get("elements")
    if not isinstance(elements_value, list):
        return projected
    elements = elements_value
    for index, element_value in enumerate(elements):
        if not isinstance(element_value, dict):
            continue
        element = coerce_material_query_result_row(element_value)
        attrs_value = element.get("attributes")
        ref_container = element.get("ref")
        if not isinstance(attrs_value, dict) or not isinstance(ref_container, dict):
            continue
        attrs = coerce_material_query_result_row(attrs_value)
        bound_ref = coerce_material_query_result_row(ref_container)
        native_ref_value = bound_ref.get("ref")
        if not isinstance(native_ref_value, dict):
            continue
        native_ref = coerce_material_query_result_row(native_ref_value)
        ref = _identity_mapping(attrs.get("material_ref"))
        if native_ref.get("type_id") != "material" or ref is None:
            continue
        material = read_material(session, project_key, ref)
        if material is None:
            attrs["reference_status"] = "unresolved_reference"
            attrs.pop("material_ref", None)
            element["attributes"] = attrs
            elements[index] = element
            continue
        material_id = int(material.id)
        attrs.update(
            coerce_material_query_result_row(
                {
                    "material_ref": material_identity(project_key, material_id),
                    "title": str(material.title or ""),
                    "url": str(material.uri or ""),
                    "content_name": str(material.title or ""),
                    "source_uri": str(material.uri or ""),
                    "content_summary": str(material.summary or ""),
                    "source_status": str(material.status or ""),
                    "material_revision": material_revision({
                        "updated_at": material.updated_at,
                        "text_hash": material.text_hash,
                    }),
                }
            )
        )
        element["attributes"] = attrs
        elements[index] = element
    projected["elements"] = elements
    return projected


__all__ = [
    "MaterialBinder",
    "MaterialBindingLedger",
    "bind_materials",
    "migrate_legacy_material_states",
    "project_materials",
    "read_material",
    "resolve_material",
]
