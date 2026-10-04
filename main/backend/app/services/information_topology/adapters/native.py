"""Read-only adapters over values returned by each module's canonical reader.

These functions deliberately accept already-read objects. They do not query
ORM tables, mutate owner records, or claim historical lookup support.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Protocol

from functorial_kit import Failure

from ..contracts import BoundRef, Element, ElementRef, Endpoint, TopologyState, topology_failures
from ..bindings import resolve_project_semantics
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


def _read(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, Mapping) else getattr(value, key, default)


def _time_revision(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return ""


def _reference(project_key: str, module: str, namespace: str, type_id: str, local_id: Any) -> ElementRef:
    if not project_key or local_id is None or str(local_id) == "":
        # kit:boundary owner=information_topology.adapters.native._reference.identity class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_adapters_bind_identity_and_report_source_version_capability
        raise ValueError("project_key and native identity are required")
    return ElementRef(project_key, module, namespace, type_id, str(local_id))


def _state(profile: str, version: str, elements: list[Element]) -> TopologyState:
    return TopologyState(profile, version, tuple(elements))


def adapt_document(document: Any, *, project_key: str, namespace: str = "documents") -> NativeObservation:
    """Adapt a Document value returned by the owning document query/read path."""
    local_id = _read(document, "id")
    updated = _time_revision(_read(document, "updated_at"))
    revision = updated or str(_read(document, "text_hash") or "")
    capability = "timestamp" if updated else "schema_only"
    ref = BoundRef(_reference(project_key, "documents", namespace, "document", local_id), revision or "current")
    element = Element(ref, {
        "title": str(_read(document, "title") or ""),
        "doc_type": str(_read(document, "doc_type") or ""),
        "status": str(_read(document, "status") or ""),
        "source_ref": {"source_id": _read(document, "source_id"), "uri": _read(document, "uri")},
    })
    return NativeObservation(_state("native.document", "1", [element]), ref.observed_revision, capability, False)


def adapt_typed_knowledge(record: Any, *, project_key: str) -> NativeObservation:
    """Adapt a PersistenceBoundaryRecord returned by its canonical repository."""
    record_project = str(_read(record, "project_key") or "")
    if record_project != project_key:
        return topology_failures.fail("UNRESOLVABLE_REFERENCE", "typed knowledge belongs to another project")  # type: ignore[return-value]
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


def adapt_writing_document(document: Mapping[str, Any], *, project_key: str) -> NativeObservation:
    """Adapt the serialized result of writing.document_service.get_document."""
    if str(document.get("project_key") or project_key) != project_key:
        return topology_failures.fail("UNRESOLVABLE_REFERENCE", "writing document belongs to another project")  # type: ignore[return-value]
    version = document.get("head_version", document.get("version"))
    if version is None:
        # A service response without a version cannot safely bind an editable reference.
        return topology_failures.fail("STALE_REFERENCE", "writing reader did not return a version")  # type: ignore[return-value]
    revision = str(version)
    ref = BoundRef(_reference(project_key, "writing", "documents", "writing_document", document.get("id")), revision, document.get("etag"))
    element = Element(ref, {"title": str(document.get("title") or ""), "status": str(document.get("status") or "")})
    return NativeObservation(_state("native.writing", "1", [element]), revision, "versioned", True)


def adapt_clue_chain_state(state: Mapping[str, Any], *, project_key: str) -> NativeObservation:
    """Adapt a value returned by ClueChainStore.load_state; no activity is inferred."""
    version = str(state.get("contract_version") or "")
    if version != "clue_chain.state.v1":
        return topology_failures.fail("STALE_REFERENCE", "unsupported clue-chain state contract")  # type: ignore[return-value]
    revision = str(state.get("base_version") or 0)
    elements: list[Element] = []
    chains = state.get("chains") if isinstance(state.get("chains"), Mapping) else {}
    for chain_id, record in chains.items():
        if not isinstance(record, Mapping):
            continue
        chain = record.get("chain") if isinstance(record.get("chain"), Mapping) else {}
        ref = BoundRef(_reference(project_key, "clue_chains", "chains", "chain", chain.get("chain_id", chain_id)), revision)
        elements.append(Element(ref, {"title": str(chain.get("title") or ""), "status": str(chain.get("status") or ""), "objective": str(chain.get("objective") or "")}))
    return NativeObservation(_state("native.clue_chain", "1", elements), revision, "versioned", False)


def clue_retrieval_correspondence(clue_ref: BoundRef, retrieval_ref: BoundRef) -> Correspondence:
    """Explicit one-to-one link; caller supplies both observed, project-bound refs."""
    if clue_ref.ref.project_key != retrieval_ref.ref.project_key:
        # kit:boundary owner=information_topology.adapters.native.clue_retrieval_correspondence.project class=PROGRAMMER_DEFECT failure_family=none witness=test:test_clue_state_is_a_read_only_observation_and_mapping_requires_same_project
        raise ValueError("cross-project clue/retrieval correspondence is forbidden")
    return Correspondence(clue_ref, (retrieval_ref,))


def adapt_graph(graph: Any, *, project_key: str, view_state: Mapping[str, Any] | None = None) -> NativeObservation:
    """Adapt GraphNodeReader.load_graph output; layout and selection are ignored."""
    schema_version = str(_read(graph, "schema_version") or "")
    nodes = _read(graph, "nodes", {})
    edges = _read(graph, "edges", ())
    if not isinstance(nodes, Mapping) or not isinstance(edges, (list, tuple)):
        return topology_failures.fail("INVALID_STRUCTURE", "canonical graph projection has invalid shape")  # type: ignore[return-value]
    refs: dict[tuple[str, str], BoundRef] = {}
    for node in nodes.values():
        node_type = str(_read(node, "type") or "")
        node_id = str(_read(node, "id") or "")
        if not node_type or not node_id:
            continue
        refs[(node_type, node_id)] = BoundRef(_reference(project_key, "graph", "nodes", "graph_node", node_id), schema_version or "unknown")
    elements: list[Element] = [Element(ref, {**dict(_read(node, "properties", {}) or {}), "native_type": str(_read(node, "type") or "")}) for node in nodes.values()
        if (str(_read(node, "type") or ""), str(_read(node, "id") or "")) in refs
        for ref in (refs[(str(_read(node, "type") or ""), str(_read(node, "id") or ""))],)]
    for edge in edges:
        source, target = _read(edge, "from_node"), _read(edge, "to_node")
        source_ref = refs.get((str(_read(source, "type") or ""), str(_read(source, "id") or "")))
        target_ref = refs.get((str(_read(target, "type") or ""), str(_read(target, "id") or "")))
        if source_ref is None or target_ref is None:
            continue
        edge_type = str(_read(edge, "type") or "relation")
        # The canonical graph store's uniqueness key is edge type plus endpoints;
        # derive the view reference from that same key, independent of row order.
        local_id = f"{edge_type}:{source_ref.ref.module_id}:{source_ref.ref.local_id}->{target_ref.ref.module_id}:{target_ref.ref.local_id}"
        edge_ref = BoundRef(_reference(project_key, "graph", "relations", "graph_relation", local_id), schema_version or "unknown")
        elements.append(Element(edge_ref, {"edge_type": edge_type,
            "origin_ref": {"module_id": "graph", "type_id": edge_type, "local_id": local_id},
            "properties": dict(_read(edge, "properties", {}) or {})}, (
            Endpoint("source", source_ref), Endpoint("target", target_ref),
        )))
    # view_state is intentionally not read: selection, coordinates and expansion are UI state.
    return NativeObservation(_state("graph.view", "1", elements), schema_version or "unknown", "schema_only", False)
