"""Read-only adapters over values returned by each module's canonical reader.

These functions deliberately accept already-read objects. They do not query
ORM tables, mutate owner records, or claim historical lookup support.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Protocol, Sequence, TypeGuard

from app.services.document_queries.identity import DocumentRevisionSource, material_identity, material_revision
from functorial_kit import Failure

from ..bindings import resolve_project_semantics
from ..contracts import BoundRef, Element, ElementRef, Endpoint, TopologyState, topology_failures
from ..mapping import Correspondence
from ..modules.retrieval import DomainVocabulary, make_retrieval_profile
from ..profiles import ProfileSpec


@dataclass(frozen=True, slots=True)
class NativeObservation:
    state: TopologyState
    observed_revision: str
    revision_capability: str  # "versioned", "timestamp", or "schema_only"
    history_available: bool
    stale: bool = False


class DomainVocabularyReader(Protocol):
    """Injected canonical source reader with exact-revision semantics."""

    def read_domain_vocabulary(
        self, *, source_ref: ElementRef, observed_revision: str, content_digest: str | None,
    ) -> DomainVocabulary | Failure: ...


@dataclass(frozen=True, slots=True)
class ResolvedRetrievalDomain:
    vocabulary: DomainVocabulary
    profile: ProfileSpec


def resolve_retrieval_domain(
    reader: DomainVocabularyReader,
    source_ref: BoundRef,
    *,
    project_key: str,
    expected_profile_id: str,
    expected_profile_version: str,
) -> ResolvedRetrievalDomain | Failure:
    """Resolve one exact, project-bound vocabulary revision through its owner.

    The injected reader must honor the requested historical revision. Returning
    a current value for an older request is rejected by comparing the full
    returned BoundRef before profile derivation.
    """
    def read_semantics(*, source_ref: ElementRef, observed_revision: str,
                       content_digest: str | None) -> DomainVocabulary | Failure:
        return reader.read_domain_vocabulary(
            source_ref=source_ref,
            observed_revision=observed_revision,
            content_digest=content_digest,
        )

    binding = resolve_project_semantics(
        read_semantics,
        source_ref,
        project_key=project_key,
        expected_profile_id=expected_profile_id,
        expected_profile_version=expected_profile_version,
        profile_factory=make_retrieval_profile,
    )
    if isinstance(binding, Failure):
        return binding
    return ResolvedRetrievalDomain(binding.semantics, binding.profile)


def _read(value: object, key: str, default: object = None) -> object:
    if _is_object_mapping(value):
        return value.get(key, default)
    return _runtime_value(getattr(value, key, default))


def _time_revision(value: object) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return ""


def _reference(project_key: str, module: str, namespace: str, type_id: str, local_id: object) -> ElementRef:
    if not project_key or local_id is None or str(local_id) == "":
        # kit:boundary owner=information_topology.adapters.native._reference.identity class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_adapters_bind_identity_and_report_source_version_capability
        raise ValueError("project_key and native identity are required")
    return ElementRef(project_key, module, namespace, type_id, str(local_id))


def _state(profile: str, version: str, elements: list[Element]) -> TopologyState:
    return TopologyState(profile, version, tuple(elements))


def adapt_material(
    document: Mapping[str, object] | DocumentRevisionSource,
    *,
    project_key: str,
    namespace: str = "materials",
) -> NativeObservation:
    """Adapt a material value returned by the sole body owner."""
    local_id = _read(document, "id")
    material_id = _positive_material_id(local_id)
    if not project_key or material_id is None:
        # kit:boundary owner=information_topology.adapters.native.document_identity class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_adapter_rejects_non_positive_material_identity
        raise ValueError("project_key and native identity are required")
    updated = _time_revision(_read(document, "updated_at"))
    revision = material_revision(document)
    capability = "timestamp" if updated else "schema_only"
    ref = BoundRef(ElementRef(**material_identity(project_key, material_id, namespace=namespace)), revision or "current")
    element = Element(ref, {
        "title": str(_read(document, "title") or ""),
        "doc_type": str(_read(document, "doc_type") or ""),
        "status": str(_read(document, "status") or ""),
        "source_ref": {"source_id": _read(document, "source_id"), "uri": _read(document, "uri")},
    })
    return NativeObservation(_state("native.material", "2", [element]), ref.observed_revision, capability, False)


adapt_document = adapt_material


def adapt_typed_knowledge(record: object, *, project_key: str) -> NativeObservation | Failure:
    """Adapt a PersistenceBoundaryRecord returned by its canonical repository."""
    record_project = str(_read(record, "project_key") or "")
    if record_project != project_key:
        return topology_failures.fail("UNRESOLVABLE_REFERENCE", "typed knowledge belongs to another project")
    identity = str(_read(record, "identity_ref") or "")
    revision = str(_read(record, "updated_at") or "")
    capability = "timestamp" if revision else "schema_only"
    ref = BoundRef(_reference(project_key, "typed_knowledge", "objects", str(_read(record, "object_type") or "object"), identity), revision or "current")
    element = Element(ref, {
        "object_key": str(_read(record, "object_key") or ""),
        "lifecycle_state": str(_read(record, "lifecycle_state") or ""),
        "review_state": str(_read(record, "review_state") or ""),
        "payload_ref": identity,
    })
    return NativeObservation(_state("native.typed_knowledge", "1", [element]), ref.observed_revision, capability, False)


def adapt_writing_document(document: Mapping[str, Any], *, project_key: str) -> NativeObservation | Failure:
    """Adapt the serialized result of writing.document_service.get_document."""
    if str(document.get("project_key") or project_key) != project_key:
        return topology_failures.fail("UNRESOLVABLE_REFERENCE", "writing document belongs to another project")
    version = document.get("head_version", document.get("version"))
    if version is None:
        # A service response without a version cannot safely bind an editable reference.
        return topology_failures.fail("STALE_REFERENCE", "writing reader did not return a version")
    revision = str(version)
    ref = BoundRef(_reference(project_key, "writing", "documents", "writing_document", document.get("id")), revision, document.get("etag"))
    element = Element(ref, {"title": str(document.get("title") or ""), "status": str(document.get("status") or "")})
    return NativeObservation(_state("native.writing", "1", [element]), revision, "versioned", True)


def adapt_clue_chain_state(state: Mapping[str, Any], *, project_key: str) -> NativeObservation | Failure:
    """Adapt a value returned by ClueChainStore.load_state; no activity is inferred."""
    version = str(state.get("contract_version") or "")
    if version != "clue_chain.state.v1":
        return topology_failures.fail("STALE_REFERENCE", "unsupported clue-chain state contract")
    revision = str(state.get("base_version") or 0)
    elements: list[Element] = []
    chains = _object_mapping_or_empty(state.get("chains"))
    for chain_id, record in chains.items():
        if not _is_object_mapping(record):
            continue
        chain = _object_mapping_or_empty(record.get("chain"))
        ref = BoundRef(_reference(project_key, "clue_chains", "chains", "chain", chain.get("chain_id", chain_id)), revision)
        elements.append(Element(ref, {"title": str(chain.get("title") or ""), "status": str(chain.get("status") or ""), "objective": str(chain.get("objective") or "")}))
    return NativeObservation(_state("native.clue_chain", "1", elements), revision, "versioned", False)


def clue_retrieval_correspondence(clue_ref: BoundRef, retrieval_ref: BoundRef) -> Correspondence:
    """Explicit one-to-one link; caller supplies both observed, project-bound refs."""
    if clue_ref.ref.project_key != retrieval_ref.ref.project_key:
        # kit:boundary owner=information_topology.adapters.native.clue_retrieval_correspondence.project class=PROGRAMMER_DEFECT failure_family=none witness=test:test_clue_state_is_a_read_only_observation_and_mapping_requires_same_project
        raise ValueError("cross-project clue/retrieval correspondence is forbidden")
    return Correspondence(clue_ref, (retrieval_ref,))


def adapt_graph(graph: object, *, project_key: str, view_state: Mapping[str, Any] | None = None) -> NativeObservation | Failure:
    """Adapt GraphNodeReader.load_graph output; layout and selection are ignored."""
    schema_version = str(_read(graph, "schema_version") or "")
    nodes = _read(graph, "nodes", {})
    edges = _read(graph, "edges", ())
    if not _is_object_mapping(nodes) or not _is_object_sequence(edges):
        return topology_failures.fail("INVALID_STRUCTURE", "canonical graph projection has invalid shape")
    refs: dict[tuple[str, str], BoundRef] = {}
    for node in nodes.values():
        node_type = str(_read(node, "type") or "")
        node_id = str(_read(node, "id") or "")
        if not node_type or not node_id:
            continue
        # GraphNodeRecord is identified by (node_type, canonical_id). JSON keeps
        # that compound identity unambiguous when either native field contains a separator.
        local_id = json.dumps((node_type, node_id), ensure_ascii=False, separators=(",", ":"))
        refs[(node_type, node_id)] = BoundRef(
            _reference(project_key, "graph", "nodes", "graph_node", local_id),
            schema_version or "unknown",
        )
    elements: list[Element] = [Element(ref, {**_string_mapping_or_empty(_read(node, "properties", {})), "native_type": str(_read(node, "type") or "")}) for node in nodes.values()
        if (str(_read(node, "type") or ""), str(_read(node, "id") or "")) in refs
        for ref in (refs[(str(_read(node, "type") or ""), str(_read(node, "id") or ""))],)]
    for edge in edges:
        source, target = _read(edge, "from_node"), _read(edge, "to_node")
        source_key = (str(_read(source, "type") or ""), str(_read(source, "id") or ""))
        target_key = (str(_read(target, "type") or ""), str(_read(target, "id") or ""))
        source_ref = refs.get(source_key)
        target_ref = refs.get(target_key)
        if source_ref is None or target_ref is None:
            continue
        edge_type = str(_read(edge, "type") or "relation")
        # The canonical graph store's uniqueness key is edge type plus endpoints;
        # encode the two directed native endpoint identities without delimiter ambiguity.
        local_id = json.dumps((edge_type, source_key, target_key), ensure_ascii=False, separators=(",", ":"))
        edge_ref = BoundRef(
            _reference(project_key, "graph", "relations", "graph_relation", local_id),
            schema_version or "unknown",
        )
        elements.append(Element(edge_ref, {"edge_type": edge_type,
            "origin_ref": {"module_id": "graph", "type_id": edge_type, "local_id": local_id},
            "properties": _string_mapping_or_empty(_read(edge, "properties", {}))}, (
            Endpoint("source", source_ref), Endpoint("target", target_ref),
        )))
    # view_state is intentionally not read: selection, coordinates and expansion are UI state.
    return NativeObservation(_state("graph.view", "1", elements), schema_version or "unknown", "schema_only", False)


def _runtime_value(value: object) -> object:
    return value


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, (list, tuple))


def _object_mapping_or_empty(value: object) -> Mapping[object, object]:
    return value if _is_object_mapping(value) else {}


def _string_mapping_or_empty(value: object) -> dict[str, object]:
    if not _is_object_mapping(value):
        return {}
    result: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(key, str):
            result[key] = item
    return result


def _positive_material_id(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None
