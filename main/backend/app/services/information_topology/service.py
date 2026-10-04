"""Project-scoped orchestration for the information-topology API.

Persistence and profile policy are supplied through explicit dependencies.  This
service has no in-memory fallback and never asks a module to execute its content.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence

from functorial_kit import Failure
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.information_topology_entities import InformationTopologyLink
from app.models.base import SessionLocal

from .contracts import (
    BoundRef, Element, ElementRef, Endpoint, PatchOperation, TopologyState,
    topology_failures, topology_state_codec,
)
from .mapping import MappingSpec, preview_mapping
from .profiles import ProfileSpec, apply_patch, decode_state, encode_state
from .structural_schema import derive_read_model_attributes
from .repository import (
    InformationTopologyRepository,
    LinkRead,
    LinkWrite,
    StateRead,
    StateWrite,
)

StateKey = tuple[str, str, str, str]


class StructureIO(Protocol):
    def import_structure(self, *, project_key: str, module_id: str, source: Mapping[str, Any]) -> Any: ...
    def export_structure(self, *, project_key: str, target: Mapping[str, Any], format: str) -> Any: ...


NativeResolver = Callable[[Session, str, ElementRef], Any]
ProfileResolver = Callable[[str, str, str, Mapping[str, Any], Mapping[str, Any] | None], ProfileSpec | Failure]


@dataclass(frozen=True, slots=True)
class InformationTopologyDependencies:
    profiles: Mapping[tuple[str, str], ProfileSpec]
    mappings: Mapping[str, tuple[MappingSpec, ProfileSpec, ProfileSpec]]
    io: StructureIO
    profile_resolver: ProfileResolver | None = None
    native_resolver: NativeResolver | None = None
    repository: InformationTopologyRepository | None = None
    session_factory: Callable[[], Session] = SessionLocal
    material_binder: Callable[[Session, TopologyState], TopologyState | Failure] | None = None
    read_model_projector: Callable[[Session, str, dict[str, Any]], dict[str, Any]] | None = None


def _ref_dict(ref: ElementRef) -> dict[str, str]:
    return {"project_key": ref.project_key, "module_id": ref.module_id, "namespace": ref.namespace,
            "type_id": ref.type_id, "local_id": ref.local_id}


def _bound_dict(ref: BoundRef) -> dict[str, Any]:
    return {"ref": _ref_dict(ref.ref), "observed_revision": ref.observed_revision,
            "content_digest": ref.content_digest}


def _element_ref(raw: Mapping[str, Any]) -> ElementRef:
    return ElementRef(str(raw["project_key"]), str(raw["module_id"]), str(raw["namespace"]),
                      str(raw["type_id"]), str(raw["local_id"]))


def _bound_ref(raw: Mapping[str, Any]) -> BoundRef:
    return BoundRef(_element_ref(raw["ref"]), str(raw["observed_revision"]), raw.get("content_digest"))


def _element(raw: Mapping[str, Any]) -> Element:
    return Element(
        _bound_ref(raw["ref"]), dict(raw.get("attributes", {})),
        tuple(Endpoint(str(ep["role"]), _bound_ref(ep["target"]), ep.get("position"))
              for ep in raw.get("endpoints", ())),
    )


def _state_wire(state: TopologyState) -> dict[str, Any]:
    return {
        "profile_id": state.profile_id, "profile_version": state.profile_version,
        "elements": [{"ref": _bound_dict(e.ref), "attributes": dict(e.attributes),
                      "endpoints": [{"role": ep.role, "target": _bound_dict(ep.target), "position": ep.position}
                                    for ep in e.endpoints]} for e in state.elements],
    }


def _read_model_wire(profile: ProfileSpec, state: TopologyState) -> dict[str, Any]:
    """Serialize a state for readers with profile-declared derived fields.

    Derived attributes are projections over source-owned data: they appear only
    in this read model, and the persisted state stays the authored payload.
    """
    return {
        "profile_id": state.profile_id, "profile_version": state.profile_version,
        "elements": [{
            "ref": _bound_dict(e.ref),
            "attributes": derive_read_model_attributes(
                e.ref.ref.type_id, e.attributes, profile.types.get(e.ref.ref.type_id)),
            "endpoints": [{"role": ep.role, "target": _bound_dict(ep.target), "position": ep.position}
                          for ep in e.endpoints],
        } for e in state.elements],
    }


class InformationTopologyService:
    def __init__(self, dependencies: InformationTopologyDependencies):
        self.dependencies = dependencies
        if dependencies.repository is not None:
            self.repository = dependencies.repository
        elif dependencies.profile_resolver is not None:
            self.repository = InformationTopologyRepository(
                dependencies.profiles, profile_resolver=dependencies.profile_resolver
            )
        else:
            self.repository = InformationTopologyRepository(dependencies.profiles)

    def _read_model(self, session: Session, project_key: str, profile: ProfileSpec,
                    state: TopologyState) -> dict[str, Any]:
        wire = _read_model_wire(profile, state)
        projector = self.dependencies.read_model_projector
        return projector(session, project_key, wire) if projector is not None else wire

    def _resolve_profile(self, project_key: str, profile_id: str, profile_version: str,
                         payload: Mapping[str, Any], source_ref: Mapping[str, Any] | None) -> ProfileSpec | Failure:
        resolver = getattr(self.repository, "resolve_profile", None)
        if resolver is not None:
            return resolver(project_key, profile_id, profile_version, payload, source_ref)
        if self.dependencies.profile_resolver is not None:
            return self.dependencies.profile_resolver(project_key, profile_id, profile_version, payload, source_ref)
        profile = self.dependencies.profiles.get((profile_id, profile_version))
        if profile is not None:
            return profile
        return topology_failures.fail(
            "UNKNOWN_PROFILE", "profile/version cannot be reconstructed from persisted source",
            {"profile_id": profile_id, "profile_version": profile_version},
        )

    @staticmethod
    def _source_ref_from_payload(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        elements = payload.get("elements", ())
        if not isinstance(elements, (list, tuple)):
            return None
        matches = [element for element in elements if isinstance(element, Mapping)
                   and isinstance(element.get("ref"), Mapping)
                   and isinstance(element["ref"].get("ref"), Mapping)
                   and element["ref"]["ref"].get("type_id") == "domain_vocabulary"]
        if len(matches) != 1:
            return None
        attributes = matches[0].get("attributes")
        source_ref = attributes.get("source_ref") if isinstance(attributes, Mapping) else None
        return source_ref if isinstance(source_ref, Mapping) else None

    def describe_profiles(self, project_key: str) -> dict[str, Any]:
        available = {(profile.profile_id, profile.version): profile
                     for profile in self.dependencies.profiles.values()}
        with self.dependencies.session_factory() as session:
            rows = self.repository.list_profile_identities(session, project_key)
            for row in rows:
                profile = self._resolve_profile(project_key, row["profile_id"], row["profile_version"],
                                                row["payload"],
                                                self._source_ref_from_payload(row["payload"]))
                if isinstance(profile, Failure):
                    continue
                available[(profile.profile_id, profile.version)] = profile
        items = [{"profile_id": profile.profile_id, "version": profile.version,
                  "types": sorted(profile.types), "relation_types": sorted(profile.relation_types)}
                 for _, profile in sorted(available.items())]
        return {"items": items, "total": len(items)}

    def list_topologies(self, project_key: str) -> dict[str, Any]:
        """Read current project topologies in one DB round trip; this is a derived read model."""
        with self.dependencies.session_factory() as session:
            rows = self.repository.list_current_states(session, project_key)
            items: list[dict[str, Any]] = []
            for row in rows:
                profile = self._resolve_profile(
                    project_key, row["profile_id"], row["profile_version"], row["payload"],
                    self._source_ref_from_payload(row["payload"]),
                )
                if isinstance(profile, Failure):
                    return profile
                state = decode_state(profile, row["payload"])
                if isinstance(state, Failure):
                    return state
                items.append({
                    "topology_ref": {"module_id": row["module_id"], "namespace": row["namespace"],
                                     "state_id": row["state_id"]},
                    "profile_id": row["profile_id"], "profile_version": row["profile_version"],
                    "revision": row["revision"], "digest": row["digest"],
                    "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                    "element_count": row["element_count"], "topology": self._read_model(session, project_key, profile, state),
                })
        return {"items": list(items), "total": len(items)}

    def count_current_elements(self, project_key: str, type_id: str) -> int:
        """Count elements of one declared type across current project states.

        Reads persisted payloads only; it does not decode profiles or treat the
        count as a new authoritative fact.
        """
        if not project_key or not type_id:
            return 0
        total = 0
        with self.dependencies.session_factory() as session:
            rows = self.repository.list_current_states(session, project_key)
        for row in rows:
            payload = row.get("payload")
            elements = payload.get("elements", ()) if isinstance(payload, Mapping) else ()
            for element in elements:
                if not isinstance(element, Mapping):
                    continue
                ref = element.get("ref")
                identity = ref.get("ref") if isinstance(ref, Mapping) else None
                if isinstance(identity, Mapping) and identity.get("type_id") == type_id:
                    total += 1
        return total

    def merge_material_documents(self, project_key: str) -> dict[str, Any] | Failure:
        """Explicit atomic V1 migration; historical revisions remain unchanged."""
        binder = self.dependencies.material_binder
        if binder is None:
            return topology_failures.fail("INVALID_STRUCTURE", "Document material binding is not configured")
        with self.dependencies.session_factory() as session:
            with session.begin():
                rows = self.repository.list_current_states(session, project_key)
                writes = []
                for row in rows:
                    if not row["profile_id"].startswith("retrieval.domain.") or row["profile_version"].startswith("2+"):
                        continue
                    key = (project_key, row["module_id"], row["namespace"], row["state_id"])
                    current = self.repository.read_state(session, key)
                    if isinstance(current, Failure) or current is None:
                        session.rollback()
                        return current or topology_failures.fail("NOT_FOUND", "migration state disappeared")
                    profile = self._resolve_profile(project_key, row["profile_id"], row["profile_version"], row["payload"], None)
                    if isinstance(profile, Failure):
                        session.rollback()
                        return profile
                    state = decode_state(profile, row["payload"])
                    if isinstance(state, Failure):
                        session.rollback()
                        return state
                    bound = binder(session, state)
                    if isinstance(bound, Failure):
                        session.rollback()
                        return bound
                    writes.append(StateWrite(
                        key, bound, row["revision"], current.get("provenance"),
                    ))
                result = self.repository.apply_batch(session, states=tuple(writes)) if writes else ()
                if isinstance(result, Failure):
                    session.rollback()
                    return result
        return {"project_key": project_key, "migrated_states": len(writes)}

    def resolve(self, project_key: str, refs: Sequence[Mapping[str, Any]]) -> dict[str, Any] | Failure:
        resolved: list[dict[str, Any]] = []
        with self.dependencies.session_factory() as session:
            for raw in refs:
                ref = _element_ref(raw)
                if ref.project_key != project_key:
                    return topology_failures.fail("UNRESOLVABLE_REFERENCE", "reference is outside the active project")
                result = self.dependencies.native_resolver(session, project_key, ref) if self.dependencies.native_resolver else None
                if result is None:
                    result = self._resolve_topology_ref(session, project_key, ref)
                if isinstance(result, Failure):
                    return result
                if result is None:
                    return topology_failures.fail("UNRESOLVABLE_REFERENCE", "reference does not resolve", {"ref": _ref_dict(ref)})
                if isinstance(result, BoundRef):
                    bound = result
                elif isinstance(result, Mapping) and "ref" in result:
                    bound = _bound_ref(result)
                else:
                    return topology_failures.fail("UNRESOLVABLE_REFERENCE", "resolver returned an invalid bound reference")
                if bound.ref.project_key != project_key or bound.ref != ref:
                    return topology_failures.fail("UNRESOLVABLE_REFERENCE", "resolver crossed project or identity boundary")
                resolved.append(_bound_dict(bound))
        return {"items": resolved, "total": len(resolved)}

    def _resolve_topology_ref(self, session: Session, project_key: str, ref: ElementRef) -> BoundRef | None | Failure:
        row = self.repository.read_state(session, (project_key, ref.module_id, ref.namespace, ref.local_id))
        if isinstance(row, Failure):
            return row
        if row is None or row["deleted"]:
            return None
        state = row.get("state")
        if state is None:
            profile = self._resolve_profile(project_key, row["profile_id"], row["profile_version"], row["payload"],
                                            self._source_ref_from_payload(row["payload"]))
            if isinstance(profile, Failure):
                return profile
            state = decode_state(profile, row["payload"])
            if isinstance(state, Failure):
                return state
        element = next((item for item in state.elements if item.ref.ref == ref), None)
        return None if element is None else element.ref

    def read_topology(self, project_key: str, topology_ref: Mapping[str, Any], filters: Mapping[str, Any]) -> dict[str, Any] | Failure:
        key = (project_key, str(topology_ref["module_id"]), str(topology_ref["namespace"]), str(topology_ref["state_id"]))
        revision = topology_ref.get("revision")
        with self.dependencies.session_factory() as session:
            row = self.repository.read_state(session, key, revision=revision)
            if isinstance(row, Failure):
                return row
            if row is None or row["deleted"]:
                return topology_failures.fail("NOT_FOUND", "topology state was not found")
            state = row.get("state")
            if state is None:
                profile = self._resolve_profile(project_key, row["profile_id"], row["profile_version"], row["payload"],
                                                self._source_ref_from_payload(row["payload"]))
                if isinstance(profile, Failure):
                    return profile
                state = decode_state(profile, row["payload"])
            if not isinstance(state, Failure):
                profile = self._resolve_profile(project_key, row["profile_id"], row["profile_version"],
                                                row["payload"], self._source_ref_from_payload(row["payload"]))
                if isinstance(profile, Failure):
                    return profile
                wire = self._read_model(session, project_key, profile, state)
        if isinstance(state, Failure):
            return state
        unknown_filters = set(filters) - {"type_ids", "local_ids"}
        if unknown_filters:
            return topology_failures.fail("INVALID_STRUCTURE", "unsupported topology filters", {"filters": sorted(unknown_filters)})
        type_ids, local_ids = filters.get("type_ids"), filters.get("local_ids")
        if type_ids is not None and (not isinstance(type_ids, list) or any(not isinstance(x, str) for x in type_ids)):
            return topology_failures.fail("INVALID_STRUCTURE", "type_ids filter must be a list of strings")
        if local_ids is not None and (not isinstance(local_ids, list) or any(not isinstance(x, str) for x in local_ids)):
            return topology_failures.fail("INVALID_STRUCTURE", "local_ids filter must be a list of strings")
        if type_ids is not None or local_ids is not None:
            wire["elements"] = [element for element in wire["elements"]
                if (type_ids is None or element["ref"]["ref"]["type_id"] in type_ids)
                and (local_ids is None or element["ref"]["ref"]["local_id"] in local_ids)]
        return {"topology": wire, "revision": row["revision"], "digest": row["digest"]}

    def find_relations(self, project_key: str, ref: Mapping[str, Any], relation_types: Sequence[str], direction: str) -> dict[str, Any] | Failure:
        bound = _bound_ref(ref)
        if bound.ref.project_key != project_key:
            return topology_failures.fail("UNRESOLVABLE_REFERENCE", "reference is outside the active project")
        if direction not in {"incoming", "outgoing", "both"}:
            return topology_failures.fail("INVALID_STRUCTURE", "direction must be incoming, outgoing, or both")
        # Relation links are n-ary. Direction is interpreted only for explicitly
        # declared source/target roles; other roles are returned by `both`.
        target_wire = _ref_dict(bound.ref)
        query = select(InformationTopologyLink).where(
            InformationTopologyLink.project_key == project_key,
            InformationTopologyLink.record_kind == "relation",
            InformationTopologyLink.is_current.is_(True),
            InformationTopologyLink.deleted.is_(False),
        )
        with self.dependencies.session_factory() as session:
            rows = session.execute(query).scalars().all()
        results: list[dict[str, Any]] = []
        for row in rows:
            if relation_types and row.type_or_rule_ref not in relation_types:
                continue
            matched = []
            for endpoint in row.endpoints or []:
                target = endpoint.get("target") if isinstance(endpoint, Mapping) else None
                raw_ref = target.get("ref") if isinstance(target, Mapping) else None
                if raw_ref == target_wire:
                    matched.append(str(endpoint.get("role", "")))
            if not matched:
                continue
            if direction != "both":
                expected_role = "source" if direction == "outgoing" else "target"
                if expected_role not in matched:
                    continue
            results.append({"link_id": row.link_id, "revision": row.revision,
                            "relation_type": row.type_or_rule_ref, "endpoints": row.endpoints,
                            "payload": row.payload, "provenance": row.provenance})
        return {"items": results, "total": len(results)}

    def preview_mapping(self, project_key: str, mapping_ref: str, input_refs: Sequence[Mapping[str, Any]]) -> dict[str, Any] | Failure:
        entry = self.dependencies.mappings.get(mapping_ref)
        if entry is None:
            return topology_failures.fail("MAPPING_NOT_APPLICABLE", "mapping is not registered", {"mapping_ref": mapping_ref})
        spec, source_profile, target_profile = entry
        states: list[TopologyState] = []
        for ref in input_refs:
            result = self.read_topology(project_key, ref, {})
            if isinstance(result, Failure):
                return result
            raw_state = result["topology"]
            from .contracts import topology_state_codec
            state = topology_state_codec.parse({"kind": "information_topology.state.v1", **raw_state})
            if isinstance(state, Failure):
                return state
            states.append(state)
        if len(states) != 1:
            return topology_failures.fail("MAPPING_NOT_APPLICABLE", "mapping preview currently requires one input topology")
        if (states[0].profile_id, states[0].profile_version) != (source_profile.profile_id, source_profile.version):
            return topology_failures.fail("MAPPING_NOT_APPLICABLE", "input profile differs from mapping source")
        preview = preview_mapping(spec, source_profile, target_profile, states[0])
        if isinstance(preview, Failure):
            return preview
        return {"mapping_id": preview.mapping_id, "output": _state_wire(preview.output),
                "correspondences": [{"source": _bound_dict(c.source), "targets": [_bound_dict(t) for t in c.targets]}
                                    for c in preview.correspondences],
                "unmapped": [_bound_dict(ref) for ref in preview.unmapped],
                "coverage": preview.coverage, "fidelity": preview.fidelity}

    def apply_batch(
        self,
        project_key: str,
        *,
        state_patches: Sequence[Mapping[str, Any]],
        link_writes: Sequence[Mapping[str, Any]],
        read_set: Sequence[Mapping[str, Any]],
        link_read_set: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any] | Failure:
        """Validate and commit state/link writes as one protected DB batch."""
        keys: list[StateKey] = []
        for item in state_patches:
            target = item["target"]
            keys.append((project_key, str(target["module_id"]), str(target["namespace"]), str(target["state_id"])))
        if len(set(keys)) != len(keys):
            return topology_failures.fail("INVALID_PATCH", "batch contains duplicate state targets")

        parsed_reads: list[StateRead] = []
        for item in read_set:
            target = item["target"]
            parsed_reads.append(StateRead(
                (project_key, str(target["module_id"]), str(target["namespace"]), str(target["state_id"])),
                int(item["base_revision"]),
            ))
        parsed_link_reads = [LinkRead(project_key, str(item["link_id"]), int(item["base_revision"]))
                             for item in link_read_set]

        writes: list[LinkWrite] = []
        for item in link_writes:
            endpoints = item.get("endpoints", ())
            payload = item.get("payload", {})
            provenance = item.get("provenance", {})
            if any(not _all_project_refs(child, project_key) for child in (endpoints, payload, provenance)):
                return topology_failures.fail("UNRESOLVABLE_REFERENCE", "link write contains a cross-project reference")
            writes.append(LinkWrite(
                project_key=project_key, link_id=str(item["link_id"]),
                record_kind=str(item["record_kind"]), type_or_rule_ref=str(item["type_or_rule_ref"]),
                endpoints=endpoints, payload=payload,
                expected_revision=item.get("base_revision"), provenance=provenance,
            ))

        with self.dependencies.session_factory() as session:
            try:
                with session.begin():
                    state_writes: list[StateWrite] = []
                    changed_states: list[TopologyState] = []
                    for item, key in zip(state_patches, keys, strict=True):
                        expected_revision = item.get("base_revision")
                        expected_revision = int(expected_revision) if expected_revision is not None else None
                        row = self.repository.read_state(session, key)
                        if isinstance(row, Failure):
                            return row
                        if expected_revision is None:
                            if row is not None:
                                code = "IDENTITY_CONFLICT" if row["deleted"] else "VERSION_CONFLICT"
                                return topology_failures.fail(code, "state identity already exists")
                            raw_initial = item["initial_state"]
                            initial_wire = {"kind": "information_topology.state.v1", **raw_initial}
                            profile_id = str(raw_initial["profile_id"])
                            profile_version = str(raw_initial["profile_version"])
                            profile = self._resolve_profile(
                                project_key, profile_id, profile_version, initial_wire,
                                self._source_ref_from_payload(initial_wire),
                            )
                            if isinstance(profile, Failure):
                                return profile
                            original = decode_state(profile, initial_wire)
                            if isinstance(original, Failure):
                                return original
                        else:
                            if row is None or row["deleted"]:
                                return topology_failures.fail(
                                    "VERSION_CONFLICT", "state update target does not exist",
                                    {"key": key, "expected_revision": expected_revision, "actual_revision": None},
                                )
                            if row["revision"] != expected_revision:
                                return topology_failures.fail(
                                    "VERSION_CONFLICT", "state base revision is stale",
                                    {"key": key, "expected_revision": expected_revision,
                                     "actual_revision": row["revision"]},
                                )
                            original = row.get("state")
                            if original is None:
                                profile = self._resolve_profile(
                                    project_key, row["profile_id"], row["profile_version"], row["payload"],
                                    self._source_ref_from_payload(row["payload"]),
                                )
                                if isinstance(profile, Failure):
                                    return profile
                                original = decode_state(profile, row["payload"])
                                if isinstance(original, Failure):
                                    return original
                            profile = self._resolve_profile(
                                project_key, row["profile_id"], row["profile_version"], row["payload"],
                                self._source_ref_from_payload(row["payload"]),
                            )
                            if isinstance(profile, Failure):
                                return profile
                        operations: list[PatchOperation] = []
                        for raw in item.get("patch", ()):
                            ref = _bound_ref(raw["ref"])
                            element = _element(raw["element"]) if raw.get("element") is not None else None
                            if element is not None and ref.ref.type_id == "material":
                                prior = next((e for e in original.elements if e.ref == ref), None)
                                if prior is not None and prior.attributes.get("document_ref") != element.attributes.get("document_ref"):
                                    return topology_failures.fail("INVALID_PATCH", "material Document identity cannot be rebound by a structural patch")
                            if ref.ref.project_key != project_key or (element and any(
                                candidate.ref.project_key != project_key
                                for candidate in (element.ref, *(ep.target for ep in element.endpoints))
                            )):
                                return topology_failures.fail("UNRESOLVABLE_REFERENCE", "patch reference crosses project boundary")
                            operations.append(PatchOperation(str(raw["action"]), ref, element))
                        if operations:
                            changed = apply_patch(profile, original, tuple(operations))
                            if isinstance(changed, Failure):
                                return changed
                        else:
                            changed = original
                        if any(ref.ref.project_key != project_key for element in changed.elements for ref in
                               (element.ref, *(ep.target for ep in element.endpoints))):
                            return topology_failures.fail("UNRESOLVABLE_REFERENCE", "topology contains a cross-project reference")
                        state_writes.append(StateWrite(key, changed, expected_revision))
                        changed_states.append(changed)

                    if self.dependencies.material_binder is not None:
                        normalized_writes = []
                        for write in state_writes:
                            bound_state = self.dependencies.material_binder(session, write.state)
                            if isinstance(bound_state, Failure):
                                session.rollback()
                                return bound_state
                            normalized_writes.append(StateWrite(write.key, bound_state, write.expected_revision, write.provenance))
                        state_writes = normalized_writes
                        changed_states = [write.state for write in state_writes]
                    result = self.repository.apply_batch(
                        session, states=tuple(state_writes), links=tuple(writes),
                        read_set=tuple(parsed_reads), link_read_set=tuple(parsed_link_reads),
                    )
                    if isinstance(result, Failure):
                        session.rollback()
                        return result
                state_results = [
                    {"target": {"module_id": key[1], "namespace": key[2], "state_id": key[3]},
                     "revision": result[index]["revision"], "topology": _state_wire(changed_states[index])}
                    for index, key in enumerate(keys)
                ]
                link_results = [
                    {"link_id": item.link_id, "revision": result[len(state_writes) + index]["revision"]}
                    for index, item in enumerate(writes)
                ]
                return {"state_revisions": state_results, "link_revisions": link_results}
            except IntegrityError:
                return topology_failures.fail("VERSION_CONFLICT", "concurrent topology write conflicted")

    def import_structure(self, project_key: str, module_id: str, source: Mapping[str, Any]) -> Any:
        return self.dependencies.io.import_structure(project_key=project_key, module_id=module_id, source=source)

    def export_structure(self, project_key: str, target: Mapping[str, Any], format: str) -> Any:
        return self.dependencies.io.export_structure(project_key=project_key, target=target, format=format)


__all__ = ["InformationTopologyDependencies", "InformationTopologyService", "ProfileResolver", "StructureIO"]


def _all_project_refs(value: Any, project_key: str) -> bool:
    if isinstance(value, Mapping):
        if "project_key" in value and value["project_key"] != project_key:
            return False
        return all(_all_project_refs(child, project_key) for child in value.values())
    if isinstance(value, (list, tuple)):
        return all(_all_project_refs(child, project_key) for child in value)
    return True
