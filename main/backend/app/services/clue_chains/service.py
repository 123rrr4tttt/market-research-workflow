from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Callable, Mapping
import unicodedata

from app.services.projects import current_project_key

from .contracts import (
    CANDIDATE_STATUSES,
    CHAIN_STATUSES,
    DECISIONS,
    EDGE_STATUSES,
    EVIDENCE_STATUSES,
    HOP_STATUSES,
    STATE_CONTRACT_VERSION,
    Chain,
    ChainCandidate,
    ChainDecision,
    ChainEdge,
    ChainEvidence,
    ChainHop,
    model_to_record,
)
from .store import ClueChainStore, build_clue_chain_store

ManualExpansionProvider = Callable[[dict[str, Any], Mapping[str, Any]], Mapping[str, Any]]


class ClueChainNotFoundError(KeyError):
    pass


class ClueChainObjectMissingError(KeyError):
    pass


class ClueChainClosedError(ValueError):
    pass


class ClueChainService:
    def __init__(
        self,
        *,
        store: ClueChainStore | None = None,
        project_key: str | None = None,
        clock: Callable[[], datetime | str] | None = None,
    ) -> None:
        self.store = store or build_clue_chain_store(project_key=project_key)
        self._project_key = str(project_key or "").strip() or None
        self._clock = clock

    def create_chain(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be a mapping")
        project_key = _non_empty(payload.get("project_key")) or self._resolve_project_key()
        seed_node_ids = _normalize_string_list(payload.get("seed_node_ids"))
        seed_nodes = _normalize_seed_nodes(payload.get("seed_nodes"))
        for seed_node in seed_nodes:
            seed_node_id = _non_empty(seed_node.get("node_id") or seed_node.get("id"))
            if seed_node_id and seed_node_id not in seed_node_ids:
                seed_node_ids.append(seed_node_id)
        if not seed_node_ids:
            raise ValueError("seed_node_ids or seed_nodes is required")

        title = _non_empty(payload.get("title")) or f"Chain for {', '.join(seed_node_ids[:3])}"
        objective = _non_empty(payload.get("objective")) or f"Trace clues from {', '.join(seed_node_ids[:3])}"
        graph_id = _non_empty(payload.get("graph_id"))
        now = self._now()
        chain_id = _non_empty(payload.get("chain_id")) or stable_id(
            "chain",
            {
                "project_key": project_key,
                "graph_id": graph_id,
                "seed_node_ids": seed_node_ids,
                "title": title,
                "objective": objective,
            },
        )
        status = _normalize_choice(payload.get("status"), CHAIN_STATUSES, default="draft", field="status")
        frontier_node_ids = _normalize_string_list(payload.get("frontier_node_ids")) or list(seed_node_ids)
        policy_json = _dict(payload.get("policy_json"))
        max_depth = _bounded_int(payload.get("max_depth"), default=3, minimum=1, maximum=25)
        max_hops = _bounded_int(payload.get("max_hops"), default=25, minimum=1, maximum=500)
        confidence_threshold = _bounded_float(payload.get("confidence_threshold"), default=0.62, minimum=0.0, maximum=1.0)

        chain = Chain(
            chain_id=chain_id,
            project_key=project_key,
            title=title,
            objective=objective,
            status=status,
            seed_node_ids=tuple(seed_node_ids),
            frontier_node_ids=tuple(frontier_node_ids),
            max_depth=max_depth,
            max_hops=max_hops,
            confidence_threshold=confidence_threshold,
            created_by=_non_empty(payload.get("created_by")) or "unknown",
            provenance_policy=_non_empty(payload.get("provenance_policy"))
            or _non_empty(policy_json.get("provenance_policy"))
            or "archive_before_pivot",
            privacy_policy=_non_empty(payload.get("privacy_policy"))
            or _non_empty(policy_json.get("privacy_policy"))
            or "public_sources_only",
            created_at=now,
            updated_at=now,
            graph_id=graph_id,
            policy_json=policy_json,
            metadata={**_dict(payload.get("metadata")), "seed_nodes": seed_nodes},
        )

        def _mutator(state: dict[str, Any]) -> dict[str, Any]:
            chains = state.setdefault("chains", {})
            if chain_id in chains:
                return state
            chains[chain_id] = {
                "chain": model_to_record(chain),
                "hops": {},
                "evidence": {},
                "candidates": {},
                "decisions": {},
                "edges": {},
                "alias_index": {},
                "events": [
                    {
                        "event_type": "chain_created",
                        "chain_id": chain_id,
                        "created_at": now,
                        "actor": chain.created_by,
                    }
                ],
            }
            return state

        state = self._mutate(_mutator)
        return self._aggregate_from_state(state, chain_id)

    def list_chains(self, *, status: str | None = None, limit: int = 50) -> dict[str, Any]:
        state = self.store.load_state()
        status_filter = _non_empty(status)
        items = []
        for record in state.get("chains", {}).values():
            chain = deepcopy(record.get("chain") or {})
            if status_filter and chain.get("status") != status_filter:
                continue
            chain["hop_count"] = len(record.get("hops") or {})
            chain["evidence_count"] = len(record.get("evidence") or {})
            chain["candidate_count"] = len(record.get("candidates") or {})
            items.append(chain)
        items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        safe_limit = max(1, min(int(limit or 50), 500))
        return {"items": items[:safe_limit], "total": len(items), "base_version": state.get("base_version", 0)}

    def get_chain(self, chain_id: str) -> dict[str, Any]:
        state = self.store.load_state()
        return self._aggregate_from_state(state, _normalize_id(chain_id, "chain_id"))

    def close_chain(self, chain_id: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        cid = _normalize_id(chain_id, "chain_id")
        body = payload if isinstance(payload, Mapping) else {}
        now = self._now()

        def _mutator(state: dict[str, Any]) -> dict[str, Any]:
            record = self._chain_record_ref(state, cid)
            chain = record["chain"]
            chain["status"] = "closed"
            chain["closed_at"] = now
            chain["updated_at"] = now
            chain["close_reason"] = _non_empty(body.get("reason") or body.get("close_reason")) or "closed"
            chain["blockers"] = _normalize_string_list(body.get("blockers"))
            _append_event(record, "chain_closed", now=now, actor=_non_empty(body.get("actor")) or "unknown")
            return state

        state = self._mutate(_mutator)
        return self._aggregate_from_state(state, cid)

    def expand_chain(
        self,
        chain_id: str,
        payload: Mapping[str, Any],
        *,
        provider: ManualExpansionProvider | None = None,
    ) -> dict[str, Any]:
        body = dict(payload or {})
        if provider is not None:
            provider_output = provider(self.get_chain(chain_id), body)
            if not isinstance(provider_output, Mapping):
                raise ValueError("manual expansion provider must return a mapping")
            merged = dict(body)
            merged.update(dict(provider_output))
            if not _non_empty(merged.get("provider")):
                merged["provider"] = getattr(provider, "__name__", provider.__class__.__name__)
            body = merged
        return self.record_hop(chain_id, body)

    def record_hop(self, chain_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        cid = _normalize_id(chain_id, "chain_id")
        body = dict(payload or {})
        now = self._now()
        resolved_hop_id = {"value": ""}

        def _mutator(state: dict[str, Any]) -> dict[str, Any]:
            record = self._chain_record_ref(state, cid)
            self._ensure_chain_open(record)
            chain = record["chain"]
            mode = _non_empty(body.get("mode") or body.get("expansion_mode")) or "manual"
            query_json = _dict(body.get("query_json") or body.get("query"))
            input_node_id = _non_empty(body.get("input_node_id")) or _first(chain.get("frontier_node_ids")) or ""
            status_default = "completed" if body.get("evidence") or body.get("candidates") or body.get("edges") else "planned"
            status = _normalize_choice(body.get("status"), HOP_STATUSES, default=status_default, field="hop.status")
            hop_id = _non_empty(body.get("hop_id")) or stable_id(
                "hop",
                {
                    "chain_id": cid,
                    "mode": mode,
                    "input_node_id": input_node_id,
                    "query_json": query_json,
                    "params": _dict(body.get("params")),
                    "depth": _bounded_int(body.get("depth"), default=0, minimum=0, maximum=100),
                },
            )
            resolved_hop_id["value"] = hop_id
            existing = record["hops"].get(hop_id)
            hop = dict(existing or {})
            hop.update(
                model_to_record(
                    ChainHop(
                        hop_id=hop_id,
                        chain_id=cid,
                        depth=_bounded_int(body.get("depth") if "depth" in body else hop.get("depth"), default=0),
                        input_node_id=input_node_id,
                        mode=mode,
                        tool_name=_non_empty(body.get("tool_name")) or "chain.expand",
                        query_json=query_json,
                        status=status,
                        started_at=_non_empty(body.get("started_at")) or hop.get("started_at") or now,
                        provider=_non_empty(body.get("provider")) or hop.get("provider"),
                        actor=_non_empty(body.get("actor")) or hop.get("actor"),
                        finished_at=_non_empty(body.get("finished_at")) or (now if status in {"completed", "failed"} else None),
                        params=_dict(body.get("params")) or _dict(hop.get("params")),
                        evidence_ids=tuple(_normalize_string_list(hop.get("evidence_ids"))),
                        candidate_ids=tuple(_normalize_string_list(hop.get("candidate_ids"))),
                        edge_ids=tuple(_normalize_string_list(hop.get("edge_ids"))),
                        error=_non_empty(body.get("error")),
                        trace=_dict(body.get("trace")) or _dict(hop.get("trace")),
                    )
                )
            )
            record["hops"][hop_id] = hop

            evidence_records = []
            for evidence_payload in _mapping_list(body.get("evidence")):
                evidence = self._add_evidence_record(record, hop_id, evidence_payload, now)
                evidence_records.append(evidence)
                _append_unique(hop, "evidence_ids", evidence["evidence_id"])

            candidate_records = []
            for candidate_payload in _mapping_list(body.get("candidates")):
                candidate = self._add_candidate_record(record, hop_id, candidate_payload, now)
                candidate_records.append(candidate)
                _append_unique(hop, "candidate_ids", candidate["candidate_id"])

            edge_records = []
            for edge_payload in _mapping_list(body.get("edges")):
                edge = self._add_edge_record(record, hop_id, edge_payload, now)
                edge_records.append(edge)
                _append_unique(hop, "edge_ids", edge["edge_id"])

            chain["updated_at"] = now
            if chain.get("status") == "draft":
                chain["status"] = "running"
            _append_event(record, "hop_recorded", now=now, actor=hop.get("actor") or "unknown", hop_id=hop_id)
            return state

        state = self._mutate(_mutator)
        aggregate = self._aggregate_from_state(state, cid)
        hop = aggregate["hops_by_id"][resolved_hop_id["value"]]
        return {
            "chain_id": cid,
            "hop": hop,
            "evidence": [aggregate["evidence_by_id"][eid] for eid in hop.get("evidence_ids", [])],
            "candidates": [aggregate["candidates_by_id"][candidate_id] for candidate_id in hop.get("candidate_ids", [])],
            "edges": [aggregate["edges_by_id"][edge_id] for edge_id in hop.get("edge_ids", [])],
            "base_version": aggregate["base_version"],
        }

    def add_evidence(self, chain_id: str, hop_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        cid = _normalize_id(chain_id, "chain_id")
        hid = _normalize_id(hop_id, "hop_id")
        now = self._now()

        def _mutator(state: dict[str, Any]) -> dict[str, Any]:
            record = self._chain_record_ref(state, cid)
            self._ensure_chain_open(record)
            if hid not in record["hops"]:
                raise ClueChainObjectMissingError(f"hop not found: {hid}")
            evidence = self._add_evidence_record(record, hid, payload, now)
            _append_unique(record["hops"][hid], "evidence_ids", evidence["evidence_id"])
            record["chain"]["updated_at"] = now
            return state

        state = self._mutate(_mutator)
        return self._aggregate_from_state(state, cid)["evidence_by_id"][self._last_evidence_id(payload, cid, hid)]

    def add_candidate(self, chain_id: str, hop_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        cid = _normalize_id(chain_id, "chain_id")
        hid = _normalize_id(hop_id, "hop_id")
        now = self._now()
        resolved_candidate_id = {"value": ""}

        def _mutator(state: dict[str, Any]) -> dict[str, Any]:
            record = self._chain_record_ref(state, cid)
            self._ensure_chain_open(record)
            if hid not in record["hops"]:
                raise ClueChainObjectMissingError(f"hop not found: {hid}")
            candidate = self._add_candidate_record(record, hid, payload, now)
            resolved_candidate_id["value"] = candidate["candidate_id"]
            _append_unique(record["hops"][hid], "candidate_ids", candidate["candidate_id"])
            record["chain"]["updated_at"] = now
            return state

        state = self._mutate(_mutator)
        return self._aggregate_from_state(state, cid)["candidates_by_id"][resolved_candidate_id["value"]]

    def record_decision(self, chain_id: str, candidate_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        cid = _normalize_id(chain_id, "chain_id")
        cand_id = _normalize_id(candidate_id, "candidate_id")
        body = dict(payload or {})
        now = self._now()

        def _mutator(state: dict[str, Any]) -> dict[str, Any]:
            record = self._chain_record_ref(state, cid)
            self._ensure_chain_open(record)
            candidate = record["candidates"].get(cand_id)
            if not isinstance(candidate, Mapping):
                raise ClueChainObjectMissingError(f"candidate not found: {cand_id}")
            decision = _normalize_choice(body.get("decision") or body.get("action"), DECISIONS, default="defer", field="decision")
            target_candidate_id = _non_empty(body.get("target_candidate_id"))
            if decision == "merge":
                if not target_candidate_id:
                    raise ValueError("target_candidate_id is required for merge decisions")
                if target_candidate_id not in record["candidates"]:
                    raise ClueChainObjectMissingError(f"target candidate not found: {target_candidate_id}")
            actor = _non_empty(body.get("actor")) or "unknown"
            reason = _non_empty(body.get("reason")) or ""
            graph_node_id = _non_empty(body.get("graph_node_id"))
            edge_ids = _normalize_string_list(body.get("edge_ids"))
            evidence_ids = _merge_unique(candidate.get("evidence_ids"), body.get("evidence_ids"))
            decision_id = _non_empty(body.get("decision_id")) or stable_id(
                "decision",
                {
                    "chain_id": cid,
                    "candidate_id": cand_id,
                    "decision": decision,
                    "actor": actor,
                    "reason": reason,
                    "target_candidate_id": target_candidate_id,
                    "graph_node_id": graph_node_id,
                    "evidence_ids": evidence_ids,
                },
            )
            record["decisions"][decision_id] = model_to_record(
                ChainDecision(
                    decision_id=decision_id,
                    chain_id=cid,
                    candidate_id=cand_id,
                    actor=actor,
                    decision=decision,
                    reason=reason,
                    created_at=now,
                    target_candidate_id=target_candidate_id,
                    graph_node_id=graph_node_id,
                    evidence_ids=tuple(evidence_ids),
                    edge_ids=tuple(edge_ids),
                    metadata=_dict(body.get("metadata")),
                )
            )
            candidate = dict(candidate)
            candidate["updated_at"] = now
            _append_unique(candidate, "decision_ids", decision_id)
            if decision == "promote":
                candidate["decision_status"] = "promoted"
                candidate["graph_node_id"] = graph_node_id
            elif decision == "reject":
                candidate["decision_status"] = "rejected"
            elif decision == "merge":
                candidate["decision_status"] = "merged"
                candidate["merged_into_candidate_id"] = target_candidate_id
                self._merge_candidate_into(record, source_id=cand_id, target_id=target_candidate_id, now=now)
            elif decision == "pause":
                candidate["decision_status"] = "paused"
            else:
                candidate["decision_status"] = "deferred"
            record["candidates"][cand_id] = candidate
            record["chain"]["updated_at"] = now
            _append_event(record, "candidate_decision_recorded", now=now, actor=actor, candidate_id=cand_id, decision=decision)
            return state

        state = self._mutate(_mutator)
        aggregate = self._aggregate_from_state(state, cid)
        decision_id = _non_empty(body.get("decision_id")) or stable_id(
            "decision",
            {
                "chain_id": cid,
                "candidate_id": cand_id,
                "decision": _normalize_choice(body.get("decision") or body.get("action"), DECISIONS, default="defer", field="decision"),
                "actor": _non_empty(body.get("actor")) or "unknown",
                "reason": _non_empty(body.get("reason")) or "",
                "target_candidate_id": _non_empty(body.get("target_candidate_id")),
                "graph_node_id": _non_empty(body.get("graph_node_id")),
                "evidence_ids": _merge_unique(aggregate["candidates_by_id"][cand_id].get("evidence_ids"), body.get("evidence_ids")),
            },
        )
        return {
            "chain_id": cid,
            "candidate": aggregate["candidates_by_id"][cand_id],
            "decision": aggregate["decisions_by_id"][decision_id],
            "base_version": aggregate["base_version"],
        }

    def merge_aliases(self, chain_id: str, candidate_id: str, aliases: list[str]) -> dict[str, Any]:
        cid = _normalize_id(chain_id, "chain_id")
        cand_id = _normalize_id(candidate_id, "candidate_id")
        now = self._now()

        def _mutator(state: dict[str, Any]) -> dict[str, Any]:
            record = self._chain_record_ref(state, cid)
            candidate = record["candidates"].get(cand_id)
            if not isinstance(candidate, Mapping):
                raise ClueChainObjectMissingError(f"candidate not found: {cand_id}")
            merged = merge_alias_values(candidate.get("aliases"), aliases)
            candidate = dict(candidate)
            candidate["aliases"] = merged
            candidate["updated_at"] = now
            record["candidates"][cand_id] = candidate
            for alias in merged:
                norm = normalize_alias(alias)
                if norm:
                    record["alias_index"][norm] = cand_id
            record["chain"]["updated_at"] = now
            return state

        state = self._mutate(_mutator)
        return self._aggregate_from_state(state, cid)["candidates_by_id"][cand_id]

    def _add_evidence_record(
        self,
        record: dict[str, Any],
        hop_id: str,
        payload: Mapping[str, Any],
        now: str,
    ) -> dict[str, Any]:
        source_ref = _dict(payload.get("source_ref"))
        for key in ("source_item_key", "channel", "document_id", "chunk_id", "rank", "local_index_mode"):
            value = payload.get(key)
            if value not in (None, ""):
                source_ref.setdefault(key, value)
        source_kind = _non_empty(payload.get("source_kind")) or _non_empty(payload.get("kind")) or "manual"
        status = _normalize_choice(payload.get("status"), EVIDENCE_STATUSES, default="lead", field="evidence.status")
        evidence_id = _non_empty(payload.get("evidence_id")) or stable_id(
            "evidence",
            {
                "chain_id": record["chain"]["chain_id"],
                "hop_id": hop_id,
                "source_kind": source_kind,
                "source_ref": source_ref,
                "url": _non_empty(payload.get("url")),
                "title": _non_empty(payload.get("title")),
                "snippet": _non_empty(payload.get("snippet") or payload.get("text")),
            },
        )
        existing = record["evidence"].get(evidence_id)
        existing_record = dict(existing) if isinstance(existing, Mapping) else {}
        evidence = model_to_record(
            ChainEvidence(
                evidence_id=evidence_id,
                chain_id=record["chain"]["chain_id"],
                hop_id=hop_id,
                source_kind=source_kind,
                source_ref={**_dict(existing_record.get("source_ref")), **source_ref},
                captured_at=_non_empty(payload.get("captured_at")) or existing_record.get("captured_at") or now,
                status=status,
                url=_non_empty(payload.get("url")) or existing_record.get("url"),
                archive_url=_non_empty(payload.get("archive_url")) or existing_record.get("archive_url"),
                content_hash=_non_empty(payload.get("hash") or payload.get("content_hash"))
                or existing_record.get("content_hash"),
                title=_non_empty(payload.get("title")) or existing_record.get("title"),
                snippet=_non_empty(payload.get("snippet") or payload.get("text")) or existing_record.get("snippet"),
                provider=_non_empty(payload.get("provider")) or existing_record.get("provider"),
                query=_non_empty(payload.get("query")) or existing_record.get("query"),
                metadata={
                    **_dict(existing_record.get("metadata")),
                    **_dict(payload.get("metadata")),
                },
            )
        )
        record["evidence"][evidence_id] = evidence
        return evidence

    def _add_candidate_record(
        self,
        record: dict[str, Any],
        hop_id: str,
        payload: Mapping[str, Any],
        now: str,
    ) -> dict[str, Any]:
        entity_type = _non_empty(payload.get("entity_type") or payload.get("node_type") or payload.get("type")) or "Entity"
        value = _non_empty(payload.get("value") or payload.get("label") or payload.get("title") or payload.get("name"))
        if not value:
            raise ValueError("candidate value is required")
        aliases = merge_alias_values([value], payload.get("aliases"))
        alias_norms = [normalize_alias(alias) for alias in aliases if normalize_alias(alias)]
        if not alias_norms:
            raise ValueError("candidate aliases must normalize to a non-empty key")

        alias_index = record.setdefault("alias_index", {})
        existing_id = next((alias_index[norm] for norm in alias_norms if norm in alias_index), None)
        candidate_id = existing_id or _non_empty(payload.get("candidate_id")) or stable_id(
            "candidate",
            {
                "chain_id": record["chain"]["chain_id"],
                "entity_type": entity_type.casefold(),
                "alias": alias_norms[0],
            },
        )
        evidence_ids = _normalize_string_list(payload.get("evidence_ids"))
        if payload.get("evidence_id"):
            _append_value(evidence_ids, str(payload.get("evidence_id")))
        edge_ids = _normalize_string_list(payload.get("edge_ids"))
        existing = record["candidates"].get(candidate_id)
        if isinstance(existing, Mapping):
            evidence_ids = _merge_unique(existing.get("evidence_ids"), evidence_ids)
            edge_ids = _merge_unique(existing.get("edge_ids"), edge_ids)
            aliases = merge_alias_values(existing.get("aliases"), aliases)
            score = _max_optional_float(existing.get("score"), payload.get("score"))
            properties = {**_dict(existing.get("properties")), **_dict(payload.get("properties"))}
            metadata = {
                **_dict(existing.get("metadata")),
                **_dict(payload.get("metadata")),
                "merged_hop_ids": _merge_unique((existing.get("metadata") or {}).get("merged_hop_ids"), [hop_id]),
            }
            decision_status = _normalize_choice(
                payload.get("decision_status"),
                CANDIDATE_STATUSES,
                default=str(existing.get("decision_status") or "pending"),
                field="candidate.decision_status",
            )
            candidate = dict(existing)
            candidate.update(
                {
                    "aliases": aliases,
                    "score": score,
                    "decision_status": decision_status,
                    "evidence_ids": evidence_ids,
                    "edge_ids": edge_ids,
                    "updated_at": now,
                    "properties": properties,
                    "metadata": metadata,
                }
            )
        else:
            score = _optional_float(payload.get("score"))
            candidate = model_to_record(
                ChainCandidate(
                    candidate_id=candidate_id,
                    chain_id=record["chain"]["chain_id"],
                    hop_id=hop_id,
                    entity_type=entity_type,
                    value=value,
                    aliases=tuple(aliases),
                    score=score,
                    decision_status=_normalize_choice(
                        payload.get("decision_status"), CANDIDATE_STATUSES, default="pending", field="candidate.decision_status"
                    ),
                    evidence_ids=tuple(evidence_ids),
                    created_at=now,
                    updated_at=now,
                    canonical_key=f"{_slug(entity_type)}:{alias_norms[0]}",
                    edge_ids=tuple(edge_ids),
                    properties=_dict(payload.get("properties")),
                    metadata=_dict(payload.get("metadata")),
                )
            )
        record["candidates"][candidate_id] = candidate
        for alias in aliases:
            norm = normalize_alias(alias)
            if norm:
                alias_index[norm] = candidate_id
        return candidate

    def _add_edge_record(
        self,
        record: dict[str, Any],
        hop_id: str,
        payload: Mapping[str, Any],
        now: str,
    ) -> dict[str, Any]:
        from_ref = _non_empty(
            payload.get("from_ref") or payload.get("from_node_id") or payload.get("from_candidate_id") or payload.get("source")
        )
        to_ref = _non_empty(payload.get("to_ref") or payload.get("to_node_id") or payload.get("to_candidate_id") or payload.get("target"))
        relation = _non_empty(payload.get("relation") or payload.get("edge_type") or payload.get("predicate")) or "related_to"
        if not from_ref or not to_ref:
            raise ValueError("edge from_ref and to_ref are required")
        evidence_ids = _normalize_string_list(payload.get("evidence_ids"))
        if payload.get("evidence_id"):
            _append_value(evidence_ids, str(payload.get("evidence_id")))
        status = _normalize_choice(payload.get("status"), EDGE_STATUSES, default="candidate", field="edge.status")
        edge_id = _non_empty(payload.get("edge_id")) or stable_id(
            "edge",
            {
                "chain_id": record["chain"]["chain_id"],
                "hop_id": hop_id,
                "from_ref": from_ref,
                "to_ref": to_ref,
                "relation": relation,
                "evidence_ids": evidence_ids,
            },
        )
        existing = record["edges"].get(edge_id)
        edge = model_to_record(
            ChainEdge(
                edge_id=edge_id,
                chain_id=record["chain"]["chain_id"],
                hop_id=hop_id,
                from_ref=from_ref,
                to_ref=to_ref,
                relation=relation,
                evidence_ids=tuple(_merge_unique((existing or {}).get("evidence_ids") if isinstance(existing, Mapping) else None, evidence_ids)),
                status=status,
                created_at=(existing or {}).get("created_at") if isinstance(existing, Mapping) else now,
                updated_at=now,
                confidence=_optional_float(payload.get("confidence")),
                metadata={
                    **_dict((existing or {}).get("metadata") if isinstance(existing, Mapping) else None),
                    **_dict(payload.get("metadata")),
                },
            )
        )
        record["edges"][edge_id] = edge
        return edge

    def _merge_candidate_into(self, record: dict[str, Any], *, source_id: str, target_id: str, now: str) -> None:
        source = dict(record["candidates"].get(source_id) or {})
        target = dict(record["candidates"].get(target_id) or {})
        if not source or not target:
            return
        target["aliases"] = merge_alias_values(target.get("aliases"), source.get("aliases"))
        target["evidence_ids"] = _merge_unique(target.get("evidence_ids"), source.get("evidence_ids"))
        target["edge_ids"] = _merge_unique(target.get("edge_ids"), source.get("edge_ids"))
        target["updated_at"] = now
        record["candidates"][target_id] = target
        for alias in target.get("aliases") or []:
            norm = normalize_alias(alias)
            if norm:
                record["alias_index"][norm] = target_id

    def _aggregate_from_state(self, state: Mapping[str, Any], chain_id: str) -> dict[str, Any]:
        cid = _normalize_id(chain_id, "chain_id")
        chains = state.get("chains") if isinstance(state.get("chains"), Mapping) else {}
        record = chains.get(cid)
        if not isinstance(record, Mapping):
            raise ClueChainNotFoundError(f"clue chain not found: {cid}")
        hops = _sorted_records(record.get("hops"), "started_at")
        evidence = _sorted_records(record.get("evidence"), "captured_at")
        candidates = _sorted_records(record.get("candidates"), "updated_at")
        decisions = _sorted_records(record.get("decisions"), "created_at")
        edges = _sorted_records(record.get("edges"), "updated_at")
        return {
            "contract_version": STATE_CONTRACT_VERSION,
            "base_version": state.get("base_version", 0),
            "chain": deepcopy(record.get("chain") or {}),
            "hops": hops,
            "evidence": evidence,
            "candidates": candidates,
            "decisions": decisions,
            "edges": edges,
            "alias_index": deepcopy(record.get("alias_index") or {}),
            "events": deepcopy(record.get("events") or []),
            "hops_by_id": {item["hop_id"]: item for item in hops},
            "evidence_by_id": {item["evidence_id"]: item for item in evidence},
            "candidates_by_id": {item["candidate_id"]: item for item in candidates},
            "decisions_by_id": {item["decision_id"]: item for item in decisions},
            "edges_by_id": {item["edge_id"]: item for item in edges},
        }

    def _chain_record_ref(self, state: dict[str, Any], chain_id: str) -> dict[str, Any]:
        chains = state.setdefault("chains", {})
        record = chains.get(chain_id)
        if not isinstance(record, dict):
            raise ClueChainNotFoundError(f"clue chain not found: {chain_id}")
        for key in ("hops", "evidence", "candidates", "decisions", "edges", "alias_index"):
            record.setdefault(key, {})
        record.setdefault("events", [])
        return record

    def _ensure_chain_open(self, record: Mapping[str, Any]) -> None:
        chain = record.get("chain") if isinstance(record.get("chain"), Mapping) else {}
        if chain.get("status") == "closed":
            raise ClueChainClosedError(f"clue chain is closed: {chain.get('chain_id')}")

    def _mutate(self, mutator: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        state = self.store.load_state()
        current = int(state.get("base_version") or 0)
        updated = mutator(deepcopy(state))
        updated["contract_version"] = STATE_CONTRACT_VERSION
        updated["base_version"] = current + 1
        return self.store.save_state(updated)

    def _resolve_project_key(self) -> str:
        if self._project_key:
            return self._project_key
        store_project_key = getattr(self.store, "project_key", None)
        if store_project_key:
            return str(store_project_key)
        return current_project_key()

    def _now(self) -> str:
        if self._clock is None:
            value: datetime | str = datetime.now(timezone.utc)
        else:
            value = self._clock()
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat()
        return str(value)

    def _last_hop_id(self, *, payload: Mapping[str, Any], chain_id: str) -> str:
        if payload.get("hop_id"):
            return str(payload["hop_id"])
        mode = _non_empty(payload.get("mode") or payload.get("expansion_mode")) or "manual"
        query_json = _dict(payload.get("query_json") or payload.get("query"))
        input_node_id = _non_empty(payload.get("input_node_id")) or ""
        return stable_id(
            "hop",
            {
                "chain_id": chain_id,
                "mode": mode,
                "input_node_id": input_node_id,
                "query_json": query_json,
                "params": _dict(payload.get("params")),
                "depth": _bounded_int(payload.get("depth"), default=0, minimum=0, maximum=100),
            },
        )

    def _last_evidence_id(self, payload: Mapping[str, Any], chain_id: str, hop_id: str) -> str:
        if payload.get("evidence_id"):
            return str(payload["evidence_id"])
        source_ref = _dict(payload.get("source_ref"))
        for key in ("source_item_key", "channel", "document_id", "chunk_id", "rank", "local_index_mode"):
            value = payload.get(key)
            if value not in (None, ""):
                source_ref.setdefault(key, value)
        return stable_id(
            "evidence",
            {
                "chain_id": chain_id,
                "hop_id": hop_id,
                "source_kind": _non_empty(payload.get("source_kind")) or _non_empty(payload.get("kind")) or "manual",
                "source_ref": source_ref,
                "url": _non_empty(payload.get("url")),
                "title": _non_empty(payload.get("title")),
                "snippet": _non_empty(payload.get("snippet") or payload.get("text")),
            },
        )

    def _last_candidate_id(self, payload: Mapping[str, Any], chain_id: str) -> str:
        if payload.get("candidate_id"):
            return str(payload["candidate_id"])
        entity_type = _non_empty(payload.get("entity_type") or payload.get("node_type") or payload.get("type")) or "Entity"
        value = _non_empty(payload.get("value") or payload.get("label") or payload.get("title") or payload.get("name")) or ""
        alias_norms = [normalize_alias(alias) for alias in merge_alias_values([value], payload.get("aliases")) if normalize_alias(alias)]
        return stable_id("candidate", {"chain_id": chain_id, "entity_type": entity_type.casefold(), "alias": alias_norms[0]})


def stable_id(prefix: str, payload: Mapping[str, Any] | list[Any] | str) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:20]}"


def normalize_alias(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    if not text:
        return ""
    text = re.sub(r"[\s_\-]+", " ", text)
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def merge_alias_values(*groups: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        values = group if isinstance(group, (list, tuple, set)) else [group]
        for value in values:
            item = str(value or "").strip()
            if not item:
                continue
            norm = normalize_alias(item)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            out.append(item)
    return out


def _normalize_seed_nodes(raw: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []


def _mapping_list(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, Mapping):
        return [dict(raw)]
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, Mapping)]
    return []


def _dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        return {"query": raw.strip()}
    return {}


def _normalize_string_list(raw: Any) -> list[str]:
    out: list[str] = []
    values = raw if isinstance(raw, (list, tuple, set)) else []
    for value in values:
        _append_value(out, str(value or "").strip())
    return out


def _append_value(out: list[str], value: str) -> None:
    item = str(value or "").strip()
    if item and item not in out:
        out.append(item)


def _append_unique(record: dict[str, Any], field: str, value: str) -> None:
    items = _normalize_string_list(record.get(field))
    _append_value(items, value)
    record[field] = items


def _merge_unique(left: Any, right: Any) -> list[str]:
    out = _normalize_string_list(left)
    for value in _normalize_string_list(right):
        _append_value(out, value)
    return out


def _append_event(record: dict[str, Any], event_type: str, *, now: str, actor: str, **payload: Any) -> None:
    events = record.setdefault("events", [])
    events.append({"event_type": event_type, "created_at": now, "actor": actor, **payload})


def _sorted_records(raw: Any, timestamp_field: str) -> list[dict[str, Any]]:
    records = [dict(item) for item in (raw or {}).values()] if isinstance(raw, Mapping) else []
    records.sort(key=lambda item: str(item.get(timestamp_field) or ""))
    return records


def _normalize_id(value: Any, field: str) -> str:
    item = str(value or "").strip()
    if not item:
        raise ValueError(f"{field} is required")
    return item


def _non_empty(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _first(values: Any) -> str | None:
    if isinstance(values, (list, tuple)) and values:
        return _non_empty(values[0])
    return None


def _normalize_choice(value: Any, allowed: frozenset[str], *, default: str, field: str) -> str:
    candidate = str(value or "").strip().lower() or default
    if candidate not in allowed:
        raise ValueError(f"unsupported {field}: {candidate}")
    return candidate


def _bounded_int(value: Any, *, default: int, minimum: int = 0, maximum: int = 1_000_000) -> int:
    if value in (None, ""):
        result = default
    else:
        try:
            result = int(value)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("integer field is invalid") from exc
    return max(minimum, min(maximum, result))


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("float field is invalid") from exc


def _bounded_float(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    result = default if value in (None, "") else _optional_float(value)
    if result is None:
        result = default
    return max(minimum, min(maximum, float(result)))


def _max_optional_float(left: Any, right: Any) -> float | None:
    values = [value for value in (_optional_float(left), _optional_float(right)) if value is not None]
    return max(values) if values else None


def _slug(value: str) -> str:
    return normalize_alias(value).replace(" ", "_") or "entity"
