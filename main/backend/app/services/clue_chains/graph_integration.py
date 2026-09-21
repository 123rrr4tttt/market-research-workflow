from __future__ import annotations

import hashlib
import re
import unicodedata
from copy import deepcopy
from typing import Annotated, Any, Iterable, Mapping, Sequence, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.w04_service_semantics import clue_chain_failures

CLUE_CHAIN_GRAPH_MUTATION_CONTRACT_VERSION = "clue_chain.graph_mutation.v1"
CLUE_CHAIN_GRAPH_HANDOFF_CONTRACT_VERSION = "graph_handoff.v1"
CLUE_CHAIN_GRAPH_EVIDENCE_PACK_CONTRACT_VERSION = "graph_evidence_pack.v1"
CLUE_CHAIN_GRAPH_SUBMIT_BRIDGE_CONTRACT_VERSION = "clue_chain.graph_submit_bridge.v1"
CLUE_CHAIN_GRAPH_PRODUCER = "clue_chain.graph_integration"
CLUE_CHAIN_GRAPH_CONSUMER = "workflow_graph.curated"

_APPROVED_DECISIONS = frozenset({"approve", "approved", "accept", "accepted", "promote", "promoted"})
_FIELD_PROVENANCE_KEYS = ("chain_id", "hop_id", "evidence_id", "candidate_id", "decision_id")


class ClueChainGraphIntegrationError(ValueError):
    """Raised when a Clue Chain candidate cannot be converted into graph mutations."""


def clue_chain_failure(code: str, message: str, *, owner: str, public_exception: type[Exception] | str = ClueChainGraphIntegrationError, **details: Any) -> Failure:
    return clue_chain_failures.fail(code, message, {
        "owner": owner,
        "public_exception": public_exception.__name__ if isinstance(public_exception, type) else str(public_exception),
        "public_message": message,
        **details,
    })


def raise_clue_chain_legacy(failure: Failure, exception_type: type[Exception] = ClueChainGraphIntegrationError, *, cause: BaseException | None = None) -> NoReturn:
    context = failure.context or {}
    if not clue_chain_failures.matches(failure) or context.get("public_exception") != exception_type.__name__ or "public_message" not in context:
        # kit:boundary owner=clue_chain.graph_integration.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_graph_failure_lift_covers_programmer_defect_and_cause
        raise TypeError("clue chain failure lift context is incomplete or inconsistent")
    message = str(context["public_message"])
    if cause is None:
        # kit:boundary owner=clue_chain.graph_integration.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=clue_chain.failure witness=test:test_graph_failure_lift_covers_programmer_defect_and_cause
        raise exception_type(message)
    # kit:boundary owner=clue_chain.graph_integration.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=clue_chain.failure witness=test:test_graph_failure_lift_covers_programmer_defect_and_cause
    raise exception_type(message) from cause


def build_graph_submit_bridge_envelope(
    *,
    graph_id: str | None = None,
    chain_id: str | None = None,
    base_revision: int | str | None = None,
    current_revision: int | str | None = None,
    handoff: Mapping[str, Any] | None = None,
    mutation: Mapping[str, Any] | None = None,
    actor_id: str | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:prepared-command effect_boundary=clue_chain_graph_submit "
    "witness=test:test_w04_authority_metadata",
]:
    """Build a staged graph-submit bridge envelope without mutating the graph."""

    handoff_map = handoff if isinstance(handoff, Mapping) else {}
    mutation_map = mutation if isinstance(mutation, Mapping) else {}
    if not mutation_map and isinstance(handoff_map.get("graph_mutation"), Mapping):
        mutation_map = handoff_map["graph_mutation"]

    resolved_graph_id = (
        _text(graph_id)
        or _first_text(mutation_map, ("graph_id",))
        or _first_text(handoff_map, ("graph_id",))
        or "default"
    )
    resolved_chain_id = (
        _text(chain_id)
        or _first_text(mutation_map, ("chain_id",))
        or _first_text(handoff_map, ("chain_id",))
        or "unknown-chain"
    )
    resolved_base_revision = _optional_non_negative_int(base_revision, "base_revision")
    if isinstance(resolved_base_revision, Failure):
        raise_clue_chain_legacy(resolved_base_revision)
    resolved_current_revision = _optional_non_negative_int(current_revision, "current_revision")
    if isinstance(resolved_current_revision, Failure):
        raise_clue_chain_legacy(resolved_current_revision)

    common_meta = {
        "contract_version": CLUE_CHAIN_GRAPH_SUBMIT_BRIDGE_CONTRACT_VERSION,
        "producer": CLUE_CHAIN_GRAPH_PRODUCER,
        "consumer": CLUE_CHAIN_GRAPH_CONSUMER,
        "bridge_mode": "staged_handoff",
        "handoff_mode": _first_text(handoff_map, ("handoff_mode",)) or "push_payload",
        "requires_base_revision_match": True,
        "graph_mutation_performed": False,
    }
    revision_contract = {
        "category": "version_conflict",
        "graph_id": resolved_graph_id,
        "chain_id": resolved_chain_id,
        "base_revision": resolved_base_revision,
        "current_revision": resolved_current_revision,
        "expected_revision": resolved_base_revision,
        "actual_revision": resolved_current_revision,
        "requires_base_revision_match": True,
        "version_semantics": "curated_graph_revision_separate_from_template_versions",
    }

    if (
        resolved_base_revision is not None
        and resolved_current_revision is not None
        and resolved_base_revision != resolved_current_revision
    ):
        return {
            "status": "conflict",
            "data": None,
            "error": {
                "code": "clue_chain_graph_revision_conflict",
                "message": "stale base_revision for graph submit",
                "details": revision_contract,
            },
            "meta": {**common_meta, "submit_status": "rejected_conflict"},
        }

    return {
        "status": "ok",
        "data": {
            "submit_status": "staged",
            "graph_id": resolved_graph_id,
            "chain_id": resolved_chain_id,
            "base_revision": resolved_base_revision,
            "current_revision": resolved_current_revision,
            "actor_id": _text(actor_id),
            "handoff": deepcopy(dict(handoff_map)) if handoff_map else None,
            "graph_mutation": deepcopy(dict(mutation_map)) if mutation_map else None,
        },
        "error": None,
        "meta": {**common_meta, "submit_status": "staged"},
    }


def try_build_graph_submit_bridge_envelope(**kwargs: Any) -> dict[str, Any] | Failure:
    try:
        return build_graph_submit_bridge_envelope(**kwargs)
    except ClueChainGraphIntegrationError as exc:
        return clue_chain_failure("input_invalid", str(exc), owner="clue_chain.graph_integration.submit_bridge")


def build_graph_handoff_payload(
    *,
    chain: Mapping[str, Any] | None = None,
    graph_id: str | None = None,
    candidates: Sequence[Mapping[str, Any]] | None = None,
    decisions: Sequence[Mapping[str, Any]] | None = None,
    evidence_items: Sequence[Mapping[str, Any]] | None = None,
    existing_alias_index: Mapping[str, str] | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view "
    "fact_source=graph_mutation+evidence_pack "
    "witness=test:test_w04_authority_metadata",
]:
    mutation = try_build_graph_mutation_payload(
        chain=chain,
        graph_id=graph_id,
        candidates=candidates,
        decisions=decisions,
        evidence_items=evidence_items,
        existing_alias_index=existing_alias_index,
    )
    if isinstance(mutation, Failure):
        raise_clue_chain_legacy(mutation)
    evidence_pack = build_graph_evidence_pack(mutation)
    handoff_id = _stable_id(
        "handoff_clue_chain",
        mutation["graph_id"],
        mutation["chain_id"],
        mutation["mutation_id"],
    )
    return {
        "contract_version": CLUE_CHAIN_GRAPH_HANDOFF_CONTRACT_VERSION,
        "handoff_id": handoff_id,
        "owner": CLUE_CHAIN_GRAPH_PRODUCER,
        "producer": CLUE_CHAIN_GRAPH_PRODUCER,
        "consumer": CLUE_CHAIN_GRAPH_CONSUMER,
        "handoff_mode": "push_payload",
        "evidence_pack": evidence_pack,
        "graph_mutation": mutation,
    }


def try_build_graph_handoff_payload(**kwargs: Any) -> dict[str, Any] | Failure:
    try:
        return build_graph_handoff_payload(**kwargs)
    except ClueChainGraphIntegrationError as exc:
        return clue_chain_failure("graph_projection_invalid", str(exc), owner="clue_chain.graph_integration.handoff")


def build_graph_evidence_pack(
    mutation: Mapping[str, Any],
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view "
    "fact_source=graph_mutation_payload "
    "witness=test:test_w04_authority_metadata",
]:
    result = try_build_graph_evidence_pack(mutation)
    if isinstance(result, Failure):
        raise_clue_chain_legacy(result)
    return result


def try_build_graph_evidence_pack(mutation: Mapping[str, Any]) -> dict[str, Any] | Failure:
    nodes = _list_of_mappings(mutation.get("nodes"))
    edges = _list_of_mappings(mutation.get("edges"))
    graph_id = _required_text(mutation, "graph_id")
    if isinstance(graph_id, Failure):
        return graph_id
    chain_id = _required_text(mutation, "chain_id")
    if isinstance(chain_id, Failure):
        return chain_id
    mutation_id = _required_text(mutation, "mutation_id")
    if isinstance(mutation_id, Failure):
        return mutation_id
    evidence_ids = sorted(
        {
            _text((item.get("provenance") or {}).get("evidence_id"))
            for item in [*nodes, *edges]
            if isinstance(item.get("provenance"), Mapping)
            and _text((item.get("provenance") or {}).get("evidence_id"))
        }
    )
    return {
        "contract_version": CLUE_CHAIN_GRAPH_EVIDENCE_PACK_CONTRACT_VERSION,
        "pack_id": _stable_id("gep_clue_chain", graph_id, chain_id, mutation_id),
        "graph_id": graph_id,
        "graph_scope": "curated_business_graph",
        "selected_nodes": [deepcopy(node) for node in nodes],
        "relations": [deepcopy(edge) for edge in edges],
        "provenance": {
            "source": CLUE_CHAIN_GRAPH_PRODUCER,
            "chain_id": chain_id,
            "mutation_id": mutation_id,
            "evidence_ids": evidence_ids,
        },
    }


def build_graph_mutation_payload(
    *,
    chain: Mapping[str, Any] | None = None,
    graph_id: str | None = None,
    candidates: Sequence[Mapping[str, Any]] | None = None,
    decisions: Sequence[Mapping[str, Any]] | None = None,
    evidence_items: Sequence[Mapping[str, Any]] | None = None,
    existing_alias_index: Mapping[str, str] | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view "
    "fact_source=decisions+candidates+evidence "
    "witness=test:test_w04_authority_metadata",
]:
    result = try_build_graph_mutation_payload(
        chain=chain,
        graph_id=graph_id,
        candidates=candidates,
        decisions=decisions,
        evidence_items=evidence_items,
        existing_alias_index=existing_alias_index,
    )
    if isinstance(result, Failure):
        raise_clue_chain_legacy(result)
    return result


def try_build_graph_mutation_payload(
    *,
    chain: Mapping[str, Any] | None = None,
    graph_id: str | None = None,
    candidates: Sequence[Mapping[str, Any]] | None = None,
    decisions: Sequence[Mapping[str, Any]] | None = None,
    evidence_items: Sequence[Mapping[str, Any]] | None = None,
    existing_alias_index: Mapping[str, str] | None = None,
) -> dict[str, Any] | Failure:
    chain_map = dict(chain or {})
    resolved_chain_id = _first_text(chain_map, ("chain_id", "id")) or "unknown-chain"
    resolved_graph_id = _text(graph_id) or _first_text(chain_map, ("graph_id", "project_graph_id")) or "default"
    decision_index = _index_approved_decisions(decisions or [])
    evidence_index = _index_by_id(evidence_items or [], "evidence_id")
    alias_index = {
        _alias_key(alias): _text(node_id)
        for alias, node_id in (existing_alias_index or {}).items()
        if _alias_key(alias) and _text(node_id)
    }

    nodes_by_id: dict[str, dict[str, Any]] = {}
    edges_by_id: dict[str, dict[str, Any]] = {}
    alias_merges: list[dict[str, Any]] = []
    included_candidate_ids: list[str] = []
    included_decision_ids: list[str] = []

    for candidate in candidates or []:
        if not isinstance(candidate, Mapping):
            continue
        candidate_id = _required_text(candidate, "candidate_id")
        if isinstance(candidate_id, Failure):
            return candidate_id
        decision = decision_index.get(candidate_id)
        if decision is None:
            continue
        evidence_id = _first_text(candidate, ("evidence_id", "source_evidence_id"))
        if not evidence_id:
            evidence_id = _first_text(decision, ("evidence_id", "source_evidence_id"))
        if not evidence_id:
            return clue_chain_failure("graph_projection_invalid", f"candidate {candidate_id} missing evidence_id", owner="clue_chain.graph_integration.mutation", candidate_id=candidate_id)
        evidence = evidence_index.get(evidence_id)
        if evidence is None:
            return clue_chain_failure("graph_projection_invalid", f"candidate {candidate_id} references missing evidence {evidence_id}", owner="clue_chain.graph_integration.mutation", candidate_id=candidate_id, evidence_id=evidence_id)

        decision_id = _required_text(decision, "decision_id")
        if isinstance(decision_id, Failure):
            return decision_id
        provenance = _provenance(
            chain_id=_first_text(candidate, ("chain_id",)) or _first_text(evidence, ("chain_id",)) or resolved_chain_id,
            hop_id=_first_text(candidate, ("hop_id",)) or _first_text(evidence, ("hop_id",)),
            evidence_id=evidence_id,
            candidate_id=candidate_id,
            decision_id=decision_id,
        )
        if isinstance(provenance, Failure):
            return provenance
        node = _build_node(
            graph_id=resolved_graph_id,
            candidate=candidate,
            evidence=evidence,
            provenance=provenance,
            alias_index=alias_index,
        )
        existing = nodes_by_id.get(node["node_id"])
        if existing is None:
            nodes_by_id[node["node_id"]] = node
        else:
            _merge_node(existing, node, provenance)
            alias_merges.append(
                {
                    "node_id": existing["node_id"],
                    "candidate_id": candidate_id,
                    "decision_id": provenance["decision_id"],
                    "aliases": node.get("aliases", []),
                }
            )

        for alias in node.get("aliases", []):
            key = _alias_key(alias)
            if key:
                alias_index.setdefault(key, node["node_id"])

        for edge in _build_edges(
            graph_id=resolved_graph_id,
            candidate=candidate,
            evidence=evidence,
            target_node_id=node["node_id"],
            provenance=provenance,
            alias_index=alias_index,
        ):
            existing_edge = edges_by_id.get(edge["edge_id"])
            if existing_edge is None:
                edges_by_id[edge["edge_id"]] = edge
            else:
                _merge_edge(existing_edge, edge, provenance)
        included_candidate_ids.append(candidate_id)
        included_decision_ids.append(provenance["decision_id"])

    node_items = sorted(nodes_by_id.values(), key=lambda item: item["node_id"])
    edge_items = sorted(edges_by_id.values(), key=lambda item: item["edge_id"])
    mutation_id = _stable_id(
        "ccgm",
        resolved_graph_id,
        resolved_chain_id,
        "|".join(sorted(included_candidate_ids)),
        "|".join(sorted(included_decision_ids)),
    )
    return {
        "contract_version": CLUE_CHAIN_GRAPH_MUTATION_CONTRACT_VERSION,
        "mutation_id": mutation_id,
        "graph_id": resolved_graph_id,
        "chain_id": resolved_chain_id,
        "producer": CLUE_CHAIN_GRAPH_PRODUCER,
        "operations": {
            "upsert_nodes": node_items,
            "upsert_edges": edge_items,
            "merge_aliases": alias_merges,
        },
        "nodes": node_items,
        "edges": edge_items,
        "candidate_ids": sorted(included_candidate_ids),
        "decision_ids": sorted(included_decision_ids),
    }


def _build_node(
    *,
    graph_id: str,
    candidate: Mapping[str, Any],
    evidence: Mapping[str, Any],
    provenance: Mapping[str, str],
    alias_index: dict[str, str],
) -> dict[str, Any]:
    node_raw = candidate.get("node")
    node = node_raw if isinstance(node_raw, Mapping) else candidate
    title = _first_text(node, ("title", "name", "label", "text")) or _first_text(
        evidence,
        ("title", "name", "label"),
    )
    aliases = _aliases(candidate, node, title)
    primary_alias_key = _alias_key(aliases[0] if aliases else title)
    node_id = _first_text(candidate, ("existing_node_id", "matched_node_id", "merge_with_node_id"))
    if not node_id and primary_alias_key:
        node_id = alias_index.get(primary_alias_key)
    if not node_id:
        node_id = _stable_id("ccn", graph_id, primary_alias_key or provenance["candidate_id"])
    return {
        "node_id": node_id,
        "node_type": _first_text(node, ("node_type", "type", "kind")) or "Entity",
        "title": title or node_id,
        "summary": _first_text(node, ("summary", "description", "snippet")) or _first_text(
            evidence,
            ("summary", "snippet", "text", "quote"),
        ),
        "source_uri": _first_text(node, ("source_uri", "url", "uri")) or _first_text(
            evidence,
            ("source_uri", "url", "uri"),
        ),
        "aliases": aliases,
        "provenance": dict(provenance),
        "provenance_items": [dict(provenance)],
    }


def _build_edges(
    *,
    graph_id: str,
    candidate: Mapping[str, Any],
    evidence: Mapping[str, Any],
    target_node_id: str,
    provenance: Mapping[str, str],
    alias_index: Mapping[str, str],
) -> list[dict[str, Any]]:
    explicit_edges = _list_of_mappings(candidate.get("edges"))
    if not explicit_edges:
        relation = candidate.get("relation")
        explicit_edges = [relation] if isinstance(relation, Mapping) else []
    if not explicit_edges:
        source_node_id = _first_text(
            candidate,
            ("source_node_id", "from_node_id", "origin_node_id", "seed_node_id", "parent_node_id"),
        )
        if not source_node_id:
            return []
        explicit_edges = [{"from_node_id": source_node_id, "to_node_id": target_node_id}]

    edges: list[dict[str, Any]] = []
    for item in explicit_edges:
        from_node_id = _edge_endpoint(item, "from", alias_index=alias_index)
        to_node_id = _edge_endpoint(item, "to", alias_index=alias_index)
        if not from_node_id:
            from_node_id = _first_text(
                candidate,
                ("source_node_id", "from_node_id", "origin_node_id", "seed_node_id", "parent_node_id"),
            )
        if not to_node_id:
            to_node_id = target_node_id
        if not from_node_id or not to_node_id:
            continue
        edge_type = _first_text(item, ("edge_type", "type", "predicate", "relation")) or _first_text(
            candidate,
            ("edge_type", "predicate", "relation_type"),
        )
        if not edge_type:
            edge_type = "RELATED_TO"
        edge_id = _first_text(item, ("edge_id", "id"))
        if not edge_id:
            edge_id = _stable_id("cce", graph_id, from_node_id, to_node_id, edge_type)
        edges.append(
            {
                "edge_id": edge_id,
                "from_node_id": from_node_id,
                "to_node_id": to_node_id,
                "edge_type": edge_type,
                "evidence": _first_text(item, ("evidence", "summary", "text"))
                or _first_text(candidate, ("evidence", "summary"))
                or _first_text(evidence, ("summary", "snippet", "text", "quote")),
                "confidence": _safe_float(item.get("confidence", candidate.get("confidence"))),
                "provenance": dict(provenance),
                "provenance_items": [dict(provenance)],
            }
        )
    return edges


def _merge_node(target: dict[str, Any], source: Mapping[str, Any], provenance: Mapping[str, str]) -> None:
    target["aliases"] = sorted({*_list_of_text(target.get("aliases")), *_list_of_text(source.get("aliases"))})
    for key in ("summary", "source_uri"):
        if not _text(target.get(key)) and _text(source.get(key)):
            target[key] = source.get(key)
    _append_provenance(target, provenance)


def _merge_edge(target: dict[str, Any], source: Mapping[str, Any], provenance: Mapping[str, str]) -> None:
    if _safe_float(target.get("confidence")) is None and _safe_float(source.get("confidence")) is not None:
        target["confidence"] = _safe_float(source.get("confidence"))
    if not _text(target.get("evidence")) and _text(source.get("evidence")):
        target["evidence"] = source.get("evidence")
    _append_provenance(target, provenance)


def _append_provenance(target: dict[str, Any], provenance: Mapping[str, str]) -> None:
    items = _list_of_mappings(target.get("provenance_items"))
    if dict(provenance) not in items:
        items.append(dict(provenance))
    target["provenance_items"] = items
    target["provenance"] = {**dict(provenance), "merged_count": len(items)}


def _index_approved_decisions(decisions: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for decision in decisions:
        if not isinstance(decision, Mapping):
            continue
        candidate_id = _first_text(decision, ("candidate_id", "target_candidate_id"))
        if not candidate_id:
            continue
        decision_value = (_first_text(decision, ("decision", "status", "action", "verdict")) or "").strip().lower()
        if decision_value in _APPROVED_DECISIONS or decision.get("approved") is True:
            out[candidate_id] = decision
    return out


def _index_by_id(items: Sequence[Mapping[str, Any]], id_key: str) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        item_id = _first_text(item, (id_key, "id"))
        if item_id:
            out[item_id] = item
    return out


def _provenance(
    *,
    chain_id: str,
    hop_id: str | None,
    evidence_id: str,
    candidate_id: str,
    decision_id: str,
) -> dict[str, str] | Failure:
    values = {
        "chain_id": chain_id,
        "hop_id": hop_id,
        "evidence_id": evidence_id,
        "candidate_id": candidate_id,
        "decision_id": decision_id,
    }
    missing = [key for key in _FIELD_PROVENANCE_KEYS if not _text(values.get(key))]
    if missing:
        return clue_chain_failure("graph_projection_invalid", f"graph provenance missing required fields: {', '.join(missing)}", owner="clue_chain.graph_integration.provenance", missing=missing)
    return {key: _text(values[key]) for key in _FIELD_PROVENANCE_KEYS}


def _aliases(candidate: Mapping[str, Any], node: Mapping[str, Any], title: str | None) -> list[str]:
    values: list[str] = []
    values.extend(_list_of_text(candidate.get("aliases")))
    values.extend(_list_of_text(candidate.get("duplicate_aliases")))
    values.extend(_list_of_text(candidate.get("merge_aliases")))
    values.extend(_list_of_text(node.get("aliases")))
    for key in ("canonical_alias", "name", "title", "label"):
        value = _text(candidate.get(key)) or _text(node.get(key))
        if value:
            values.append(value)
    if title:
        values.append(title)
    deduped = sorted({_collapse_space(item) for item in values if _collapse_space(item)}, key=str.lower)
    return deduped


def _edge_endpoint(item: Mapping[str, Any], field: str, *, alias_index: Mapping[str, str]) -> str | None:
    direct = item.get(field)
    if isinstance(direct, Mapping):
        node_id = _first_text(direct, ("node_id", "id", "key"))
        if node_id:
            return node_id
        alias = _first_text(direct, ("alias", "name", "title", "label"))
        if alias:
            return alias_index.get(_alias_key(alias))
    if isinstance(direct, str):
        value = direct.strip()
        return alias_index.get(_alias_key(value), value)
    direct_id = _first_text(item, (f"{field}_node_id", f"{field}_id"))
    if direct_id:
        return direct_id
    alias = _first_text(item, (f"{field}_alias", f"{field}_name", f"{field}_title"))
    if alias:
        return alias_index.get(_alias_key(alias))
    return None


def _required_text(item: Mapping[str, Any], key: str) -> str | Failure:
    value = _text(item.get(key))
    if not value:
        return clue_chain_failure("input_invalid", f"{key} is required", owner="clue_chain.graph_integration.required_text", field=key)
    return value


def _first_text(item: Mapping[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = _text(item.get(key))
        if value:
            return value
    return None


def _list_of_mappings(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, (list, tuple)):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _list_of_text(raw: Any) -> list[str]:
    if not isinstance(raw, (list, tuple, set)):
        return []
    return [_collapse_space(item) for item in raw if _collapse_space(item)]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _collapse_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _alias_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def _stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256("||".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()[:12]
    label = _slug(next((part for part in reversed(parts) if _text(part)), prefix))
    if label:
        return f"{prefix}_{label}_{digest}"[:96]
    return f"{prefix}_{digest}"


def _slug(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"[^0-9a-z]+", "-", text).strip("-")
    return text[:36]


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_non_negative_int(value: Any, field: str) -> int | None | Failure:
    if value in (None, ""):
        return None
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return clue_chain_failure("input_invalid", f"{field} must be an integer", owner="clue_chain.graph_integration.revision", field=field)
    if resolved < 0:
        return clue_chain_failure("input_invalid", f"{field} must be non-negative", owner="clue_chain.graph_integration.revision", field=field)
    return resolved
