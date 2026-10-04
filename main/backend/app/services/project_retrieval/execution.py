"""Bounded execution of a project retrieval plan through registered MRW tools.

Candidates, collected documents, model proposals and validated graph elements
have separate identities. Only the last of these is committed as formal graph.
"""

from __future__ import annotations

from datetime import datetime, UTC
from hashlib import sha256
import json
from typing import Any
from collections.abc import Callable, Mapping

from functorial_kit import Failure

from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.information_topology.contracts import (
    topology_state_codec,
    TopologyState,
    Element,
    ElementRef,
    BoundRef,
    Endpoint,
)
from app.services.information_topology.io.retrieval import resolve_domain_vocabulary
from app.services.information_topology.modules.retrieval import (
    domain_vocabulary_element,
    make_retrieval_profile,
    profile_from_state_payload,
    validate_evidence_v2,
)
from app.services.information_topology.profiles import decode_state, validate_state
from app.services.skill_runtime import invoke_skill


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _failure(value: Any) -> dict[str, Any]:
    if isinstance(value, Failure):
        return {"code": value.code, "message": value.message, "context": dict(value.context or {})}
    return {"code": type(value).__name__, "message": str(value)}


def _ingest_failure_receipt(dispatch: Mapping[str, Any], ingest: Mapping[str, Any]) -> dict[str, Any]:
    """Keep a precise rejection code without copying fetched body bytes into run errors."""
    postprocess = dispatch.get("postprocess_frontdoor")
    postprocess_meta = postprocess.get("meta") if isinstance(postprocess, Mapping) else None
    strict_gate = dispatch.get("canary_handoff")
    strict_state = strict_gate.get("strict_gate_state") if isinstance(strict_gate, Mapping) else None
    reason = (
        (postprocess_meta or {}).get("reason_code")
        or (strict_state or {}).get("reason_code")
        or dispatch.get("reason_code")
    )
    return {
        "code": "INGEST_REJECTED" if dispatch.get("status") == "failed" else "INGEST_NO_DOCUMENT",
        "status": str(dispatch.get("status") or ingest.get("status") or "unknown"),
        "reason_code": str(reason or "unknown"),
    }


def _bounded_limit(raw: Any, maximum: int, default: int) -> int:
    try:
        number = int(raw)
    except (TypeError, ValueError):
        number = default
    return max(0, min(maximum, number))


def _compile_topology_seed(
    project_key: str, target: Mapping[str, str], raw: Mapping[str, Any], session_id: str, attempts: list[dict[str, Any]]
) -> dict[str, Any] | dict[str, str]:
    """Derive a run state from the fixed project vocabulary and selected route/query rows."""
    vocabulary = resolve_domain_vocabulary(project_key, raw)
    if isinstance(vocabulary, Failure):
        return {"error": vocabulary.code, "message": vocabulary.message}
    try:
        profile = make_retrieval_profile(vocabulary)
        elements = [domain_vocabulary_element(vocabulary)]
        by_query = {attempt["query_id"]: attempt["result"] for attempt in attempts}
        for kind, rows, identity in (
            ("source_route", raw.get("source_routes"), "route_id"),
            ("keyword_plan", raw.get("keyword_plans"), "plan_id"),
            ("source_registry", raw.get("source_registry", []), "source_id"),
        ):
            if not isinstance(rows, list):
                return {"error": "TOPOLOGY_SEED_INVALID", "message": f"{kind} rows are absent"}
            for row in rows:
                if not isinstance(row, Mapping) or not str(row.get(identity) or ""):
                    return {"error": "TOPOLOGY_SEED_INVALID", "message": f"{kind} identity is absent"}
                attrs = {key: value for key, value in row.items() if key in profile.types[kind].attributes}
                if kind == "keyword_plan" and str(row[identity]) in by_query:
                    attrs["execution_status"] = "executed"
                    attrs["result"] = by_query[str(row[identity])]
                elif kind == "source_route" and attempts:
                    attrs["status"] = "attempted"
                ref = BoundRef(
                    ElementRef(project_key, target["module_id"], target["namespace"], kind, str(row[identity])),
                    session_id,
                    _digest(attrs),
                )
                elements.append(Element(ref, attrs))
        declared_queries = {str(row.get("plan_id") or "") for row in raw.get("keyword_plans") or []}
        route_ids = [str(row.get("route_id") or "") for row in raw.get("source_routes") or []]
        for attempt in attempts:
            query_id = str(attempt["query_id"])
            if query_id in declared_queries:
                continue
            attrs = {
                "plan_id": query_id,
                "kind": "followup",
                "expression": attempt["actual_query"],
                "execution_status": "executed",
                "result": attempt["result"],
                "source_route_id": route_ids[0] if route_ids else "",
            }
            ref = BoundRef(
                ElementRef(project_key, target["module_id"], target["namespace"], "keyword_plan", query_id),
                session_id,
                _digest(attrs),
            )
            elements.append(Element(ref, attrs))
            declared_queries.add(query_id)
        wire = topology_state_codec.to_wire(TopologyState(profile.profile_id, profile.version, tuple(elements)))
        return {"profile_id": profile.profile_id, "profile_version": profile.version, "elements": wire["elements"]}
    except (TypeError, ValueError, KeyError) as exc:
        return {"error": "TOPOLOGY_SEED_INVALID", "message": str(exc)}


def _tool(
    registry: Any,
    request: AgentCoreRequest,
    name: str,
    arguments: Mapping[str, Any],
    *,
    emit: Callable[[str, Mapping[str, Any]], None] | None,
) -> dict[str, Any]:
    spec = registry.get(name)
    if spec is None:
        return {"status": "failed", "error": {"code": "TOOL_UNAVAILABLE", "message": name}, "structured_content": {}}
    call = CoreToolCall(
        tool_name=name,
        arguments=dict(arguments),
        call_id=f"retrieval-{_digest((request.session_id, name, arguments))[:24]}",
    )
    try:
        result = registry.execute_tool(tool_call=call, tool_spec=spec, request=request, emit=lambda _: None)
        receipt = result.to_dict()
    except Exception as exc:  # failed tool calls are evidence, not an implicit retry
        receipt = {"status": "failed", "error": _failure(exc), "structured_content": {}}
    if emit is not None:
        emit(
            "tool.result",
            {"tool": name, "call_id": call.call_id, "status": receipt["status"], "error": receipt.get("error")},
        )
    return receipt


def _read_document_body(topology_service: Any, project_key: str, document_id: Any) -> tuple[dict[str, Any], str | None]:
    """Read the persisted ingest output; a queued task or document ID alone is not a body."""
    try:
        from app.models.entities import Document
        from app.services.projects import bind_project

        with bind_project(project_key):
            with topology_service.dependencies.session_factory() as session:
                document = session.get(Document, int(document_id))
                if document is None:
                    return {"status": "missing", "error": {"code": "DOCUMENT_NOT_FOUND"}}, None
                body = str(document.content or "").strip()
                if not body:
                    return {"status": "missing", "error": {"code": "DOCUMENT_BODY_EMPTY"}}, None
                return {
                    "status": "read",
                    "document_id": int(document_id),
                    "title": str(document.title or ""),
                    "uri": str(document.uri or ""),
                    "body_digest": sha256(body.encode("utf-8")).hexdigest(),
                    "body_length": len(body),
                    "document_updated_at": document.updated_at.isoformat()
                    if getattr(document, "updated_at", None)
                    else None,
                }, body
    except Exception as exc:
        return {"status": "failed", "error": _failure(exc)}, None


def _formal_group(
    *, project_key: str, target: Mapping[str, str], session_id: str, package: Mapping[str, Any], profile: Any
) -> tuple[list[Element], dict[str, Any]] | dict[str, Any]:
    """Interpret one formalizer proposal against the bound profile and read body."""
    proposal = package.get("proposal")
    receipt = package.get("body_read")
    body = package.get("body")
    if not isinstance(proposal, Mapping) or not isinstance(receipt, Mapping) or not isinstance(body, str):
        return {"code": "FORMAL_PROPOSAL_INVALID", "message": "proposal or document observation is missing"}
    nodes = proposal.get("nodes")
    judgment = proposal.get("judgment")
    evidence = proposal.get("evidence")
    clue = proposal.get("clue")
    if not isinstance(nodes, list) or len(nodes) < 2 or not all(isinstance(n, Mapping) for n in nodes):
        return {"code": "FORMAL_PROPOSAL_INVALID", "message": "at least two nodes are required"}
    if not all(isinstance(part, Mapping) for part in (judgment, evidence, clue)):
        return {"code": "FORMAL_PROPOSAL_INVALID", "message": "judgment, evidence and clue are required"}
    observed = str(receipt.get("body_digest") or "")
    if not observed or sha256(body.encode("utf-8")).hexdigest() != observed:
        return {"code": "SOURCE_CHANGED", "message": "body observation differs from the supplied document"}
    excerpt = str(evidence.get("original_excerpt") or "")
    if not excerpt or excerpt not in body:
        return {"code": "EVIDENCE_QUOTE_NOT_LOCATED", "message": "original_excerpt is absent from the read body"}
    document_id = str(receipt.get("document_id") or "")
    candidate_id = str(package.get("candidate_id") or "")
    if not document_id or not candidate_id:
        return {"code": "FORMAL_PROPOSAL_INVALID", "message": "document/candidate identity is missing"}
    observation = str(receipt.get("document_updated_at") or observed)
    prefix = _digest((session_id, document_id, candidate_id))[:24]

    def bound(kind: str, local_id: str, attrs: Mapping[str, Any]) -> BoundRef:
        return BoundRef(
            ElementRef(project_key, target["module_id"], target["namespace"], kind, local_id),
            observation,
            _digest(attrs),
        )

    node_refs: dict[str, BoundRef] = {}
    node_labels: dict[str, str] = {}
    group: list[Element] = []
    for node in nodes:
        key = str(node.get("local_key") or "").strip()
        raw_type = str(node.get("type_id") or "").strip()
        source_type = raw_type.removeprefix("node:")
        name = str(node.get("name") or "").strip()
        kind = f"node:{source_type}"
        if not key or key in node_refs or not name or kind not in profile.types:
            return {"code": "FORMAL_NODE_INVALID", "message": "node key, type or name is invalid"}
        attrs = {"source_type": source_type, "name": name}
        ref = bound(kind, f"node-{prefix}-{_digest(key)[:12]}", attrs)
        node_refs[key], node_labels[key] = ref, name
        group.append(Element(ref, attrs))

    from_key, to_key = str(judgment.get("from_key") or ""), str(judgment.get("to_key") or "")
    scene_key = str(clue.get("scene_key") or "")
    if from_key not in node_refs or to_key not in node_refs or scene_key not in node_refs:
        return {"code": "FORMAL_ENDPOINT_MISSING", "message": "proposal endpoint does not name a proposed node"}
    if node_refs[scene_key].ref.type_id != "node:现场":
        return {"code": "FORMAL_SCENE_INVALID", "message": "clue scene_key must point to a 现场 node"}
    for field in ("pools", "relation_classes"):
        if not isinstance(judgment.get(field), list):
            return {"code": "FORMAL_JUDGMENT_INVALID", "message": f"{field} must be an array"}
    outline_section = str(judgment.get("outline_section") or "")
    edge_type = str(judgment.get("edge_type") or "")
    query = package.get("query") if isinstance(package.get("query"), Mapping) else {}
    route = package.get("source_route") if isinstance(package.get("source_route"), Mapping) else {}
    if query.get("outline_sections") and outline_section not in query["outline_sections"]:
        return {"code": "QUERY_SCOPE_MISMATCH", "message": "judgment outline section is outside the selected query"}
    if query.get("target_edge") and edge_type != query["target_edge"]:
        return {"code": "QUERY_SCOPE_MISMATCH", "message": "judgment edge type differs from the selected query"}
    if route.get("pool") and any(pool != route["pool"] for pool in judgment["pools"]):
        return {"code": "ROUTE_SCOPE_MISMATCH", "message": "judgment pool differs from the selected route"}

    material_attrs = {
        "title": str(receipt.get("title") or receipt.get("uri") or "document"),
        "url": str(receipt.get("uri") or package.get("url") or ""),
        "grade": str(evidence.get("grade") or ""),
        "outline_section": outline_section,
        "reference_status": "body_read",
        "node_ids": [ref.ref.local_id for ref in node_refs.values()],
        "edge_ids": [f"judgment-{prefix}"],
        "relation_classes": list(judgment["relation_classes"]),
        "candidate_id": candidate_id,
        "candidate_key": candidate_id,
        "snapshot_path": [f"document:{document_id}"],
    }
    material_ref = bound("material", f"material-{prefix}", material_attrs)
    group.append(Element(material_ref, material_attrs))
    judgment_id, evidence_id, clue_id = f"judgment-{prefix}", f"evidence-{prefix}", f"clue-{prefix}"
    judgment_attrs = {
        "edge_type": edge_type,
        "judgment": str(judgment.get("judgment") or ""),
        "scope": str(judgment.get("scope") or ""),
        "judgment_version": session_id,
        "outline_section": outline_section,
        "pools": list(judgment["pools"]),
        "relation_classes": list(judgment["relation_classes"]),
        "evidence_ids": [evidence_id],
        "from_id": node_refs[from_key].ref.local_id,
        "to_id": node_refs[to_key].ref.local_id,
    }
    judgment_ref = bound("judgment", judgment_id, judgment_attrs)
    group.append(
        Element(
            judgment_ref, judgment_attrs, (Endpoint("from", node_refs[from_key]), Endpoint("to", node_refs[to_key]))
        )
    )
    evidence_attrs = {
        key: evidence[key]
        for key in (
            "grade",
            "conflict",
            "effect",
            "original_location",
            "original_excerpt",
            "applicable_scope",
            "inference_note",
            "proves",
            "source_role",
            "independence_group",
        )
        if key in evidence
    }
    evidence_attrs["upstream_material_ids"] = [material_ref.ref.local_id]
    evidence_attrs["conflicting_evidence_ids"] = list(evidence.get("conflicting_evidence_ids") or [])
    evidence_failure = validate_evidence_v2(evidence_attrs)
    if evidence_failure is not None:
        return {"code": evidence_failure.code, "message": evidence_failure.message}
    evidence_ref = bound("evidence", evidence_id, evidence_attrs)
    group.append(
        Element(evidence_ref, evidence_attrs, (Endpoint("material", material_ref), Endpoint("judgment", judgment_ref)))
    )
    clue_attrs = {
        "clue_id": clue_id,
        "round_id": session_id,
        "name": str(clue.get("name") or "").strip(),
        "scene_id": node_refs[scene_key].ref.local_id,
        "scene_label": node_labels[scene_key],
        "pools": list(judgment["pools"]),
        "generation_date": _now()[:10],
    }
    if not clue_attrs["name"]:
        return {"code": "FORMAL_CLUE_INVALID", "message": "clue name is missing"}
    clue_ref = bound("clue", clue_id, clue_attrs)
    group.append(Element(clue_ref, clue_attrs, (Endpoint("item", judgment_ref, 0), Endpoint("item", evidence_ref, 1))))
    refs = {
        "document_id": document_id,
        "candidate_id": candidate_id,
        "material": material_ref.ref.local_id,
        "nodes": [ref.ref.local_id for ref in node_refs.values()],
        "judgment": judgment_id,
        "evidence": evidence_id,
        "clue": clue_id,
        "body_digest": observed,
        "document_updated_at": receipt.get("document_updated_at"),
    }
    return group, refs


def _append_attempts(
    *,
    topology_service: Any,
    project_key: str,
    topology_ref: Mapping[str, Any] | None,
    topology_seed: Mapping[str, Any] | None,
    profile_id: str,
    profile_version: str,
    session_id: str,
    attempts: list[dict[str, Any]],
    formal_packages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a run-owned state in one write; historical states are never patched."""
    if not attempts:
        return {"status": "not_needed", "attempt_refs": []}
    if not isinstance(topology_ref, Mapping):
        return {"status": "blocked", "error": {"code": "TOPOLOGY_TARGET_MISSING"}, "attempt_refs": []}
    target = {key: str(topology_ref.get(key) or "") for key in ("module_id", "namespace", "state_id")}
    if not all(target.values()):
        return {"status": "blocked", "error": {"code": "TOPOLOGY_TARGET_INCOMPLETE"}, "attempt_refs": []}
    if not target["state_id"].startswith("retrieval-run:"):
        return {"status": "blocked", "error": {"code": "RUN_TOPOLOGY_TARGET_REQUIRED"}, "attempt_refs": []}
    if not isinstance(topology_seed, Mapping):
        return {"status": "blocked", "error": {"code": "TOPOLOGY_SEED_MISSING"}, "attempt_refs": []}
    if not isinstance(topology_seed.get("elements"), list):
        topology_seed = _compile_topology_seed(project_key, target, topology_seed, session_id, attempts)
    if "error" in topology_seed:
        return {
            "status": "failed",
            "error": {"code": topology_seed["error"], "message": topology_seed.get("message")},
            "attempt_refs": [],
        }
    profile_id = profile_id or str(topology_seed.get("profile_id") or "")
    profile_version = profile_version or str(topology_seed.get("profile_version") or "")
    if (topology_seed.get("profile_id"), topology_seed.get("profile_version")) != (profile_id, profile_version):
        return {"status": "failed", "error": {"code": "PROFILE_VERSION_CONFLICT"}, "attempt_refs": []}
    elements = list(topology_seed["elements"])
    if any(
        not isinstance(element, Mapping)
        or ((element.get("ref") or {}).get("ref") or {}).get("project_key") != project_key
        for element in elements
    ):
        return {"status": "failed", "error": {"code": "TOPOLOGY_SEED_PROJECT_MISMATCH"}, "attempt_refs": []}
    if (
        sum(
            1
            for element in elements
            if ((element.get("ref") or {}).get("ref") or {}).get("type_id") == "domain_vocabulary"
        )
        != 1
    ):
        return {"status": "failed", "error": {"code": "DOMAIN_VOCABULARY_SEED_REQUIRED"}, "attempt_refs": []}
    try:
        current = topology_service.read_topology(project_key, target, {})
    except Exception as exc:
        return {"status": "failed", "error": _failure(exc), "attempt_refs": []}
    if not isinstance(current, Failure) or current.code != "NOT_FOUND":
        return {
            "status": "failed",
            "error": {
                "code": "IDENTITY_CONFLICT" if not isinstance(current, Failure) else current.code,
                "message": "run topology identity already exists or cannot be read",
            },
            "attempt_refs": [],
        }
    refs: list[dict[str, Any]] = []
    for attempt in attempts:
        local_id = str(attempt["attempt_id"])
        ref = {
            "ref": {
                "project_key": project_key,
                "module_id": target["module_id"],
                "namespace": target["namespace"],
                "type_id": "attempt",
                "local_id": local_id,
            },
            "observed_revision": session_id,
            "content_digest": _digest(attempt),
        }
        element = {"ref": ref, "attributes": attempt, "endpoints": []}
        elements.append(element)
        refs.append(ref)
    wire = {
        "kind": "information_topology.state.v1",
        "profile_id": profile_id,
        "profile_version": profile_version,
        "elements": elements,
    }
    profile = profile_from_state_payload(project_key, profile_id, profile_version, wire)
    if isinstance(profile, Failure):
        return {"status": "failed", "error": _failure(profile), "attempt_refs": []}
    base = decode_state(profile, wire)
    if isinstance(base, Failure):
        return {"status": "failed", "error": _failure(base), "attempt_refs": []}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    state_elements = list(base.elements)
    for package in formal_packages or []:
        candidate_id = str(package.get("candidate_id") or "")
        group = _formal_group(
            project_key=project_key, target=target, session_id=session_id, package=package, profile=profile
        )
        if isinstance(group, dict):
            rejected.append({"candidate_id": candidate_id, "error": group})
            continue
        proposed_elements, group_refs = group
        candidate_state = TopologyState(profile_id, profile_version, tuple(state_elements + proposed_elements))
        invalid = validate_state(profile, candidate_state)
        if invalid is not None:
            rejected.append({"candidate_id": candidate_id, "error": _failure(invalid)})
            continue
        state_elements.extend(proposed_elements)
        accepted.append(group_refs)
    elements = topology_state_codec.to_wire(TopologyState(profile_id, profile_version, tuple(state_elements)))[
        "elements"
    ]
    try:
        result = topology_service.apply_batch(
            project_key,
            state_patches=[
                {
                    "target": target,
                    "base_revision": None,
                    "initial_state": {
                        "profile_id": profile_id,
                        "profile_version": profile_version,
                        "elements": elements,
                    },
                    "patch": [],
                }
            ],
            link_writes=[],
            read_set=[],
            link_read_set=[],
        )
    except Exception as exc:
        return {"status": "failed", "error": _failure(exc), "attempt_refs": []}
    if isinstance(result, Failure):
        return {"status": "failed", "error": _failure(result), "attempt_refs": []}
    revision = (result.get("state_revisions") or [{}])[0].get("revision")
    try:
        readback = topology_service.read_topology(project_key, {**target, "revision": revision}, {})
    except Exception as exc:
        return {
            "status": "readback_failed",
            "error": _failure(exc),
            "attempt_refs": refs,
            "rejected_formal": rejected,
            "formal_graph_refs": [],
            "state_revision": revision,
        }
    if isinstance(readback, Failure):
        return {
            "status": "readback_failed",
            "error": _failure(readback),
            "attempt_refs": refs,
            "rejected_formal": rejected,
            "formal_graph_refs": [],
            "state_revision": revision,
        }
    read_ids = {
        str(((element.get("ref") or {}).get("ref") or {}).get("local_id") or "")
        for element in (readback.get("topology") or {}).get("elements") or []
    }
    verified = [
        group
        for group in accepted
        if all(
            key in read_ids
            for key in (group["material"], *group["nodes"], group["judgment"], group["evidence"], group["clue"])
        )
    ]
    if len(verified) != len(accepted) or readback.get("revision") != revision:
        return {
            "status": "readback_failed",
            "error": {"code": "TOPOLOGY_READBACK_MISMATCH"},
            "attempt_refs": refs,
            "rejected_formal": rejected,
            "formal_graph_refs": [],
            "state_revision": revision,
        }
    return {
        "status": "completed",
        "attempt_refs": refs,
        "rejected_formal": rejected,
        "formal_graph_refs": verified,
        "state_digest": readback.get("digest"),
        "topology_ref": target,
        "profile_id": profile_id,
        "profile_version": profile_version,
        "state_revision": revision,
    }


def execute_retrieval_run(
    *,
    project_key: str,
    plan: Mapping[str, Any],
    topology_service: Any,
    session_factory: Callable[[], Any],
    emit: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> Mapping[str, Any]:
    """Run a fixed plan once and return inspectable receipts and precise gaps.

    ``session_factory`` returns the configured AgentSessionService.  The caller
    owns plan validation, idempotent run creation, and background dispatch.
    This function creates one project Agent session for its actual tool calls.
    """
    plan_id = str(plan.get("plan_id") or "").strip()
    selected = [str(value) for value in plan.get("query_ids") or []]
    queries = {
        str(item.get("id") or item.get("query_id") or ""): dict(item)
        for item in plan.get("queries") or []
        if isinstance(item, Mapping) and (item.get("id") or item.get("query_id"))
    }
    limits = plan.get("limits") if isinstance(plan.get("limits"), Mapping) else {}
    max_queries = _bounded_limit(limits.get("max_queries"), 10, 10)
    max_materials = _bounded_limit(limits.get("max_materials"), 20, 20)
    max_followups = _bounded_limit(limits.get("max_followups"), 2, 2)
    if not project_key or not plan_id or not selected or max_queries == 0 or any(q not in queries for q in selected):
        return {
            "status": "failed",
            "error": {"code": "INVALID_PLAN", "message": "project, plan and selected queries are required"},
            "attempts": [],
            "candidates": [],
            "materials": [],
            "graph": None,
        }
    selected = selected[:max_queries]
    route_id = str(plan.get("route_id") or "")
    if any(
        str(queries[q].get("source_route_id") or queries[q].get("route_id") or route_id) != route_id for q in selected
    ):
        return {
            "status": "failed",
            "error": {"code": "QUERY_ROUTE_MISMATCH"},
            "attempts": [],
            "candidates": [],
            "materials": [],
            "graph": None,
        }

    try:
        service = session_factory()
        bundle = service.create_session(
            source="project_retrieval",
            entrypoint_type="project_retrieval",
            goal=f"Execute retrieval plan {plan_id} for route {route_id}",
            project_key=project_key,
            initial_context={
                "plan_id": plan_id,
                "mode_id": plan.get("mode_id"),
                "mode_version": plan.get("mode_version"),
            },
            metadata={"project_retrieval": {"plan_id": plan_id, "route_id": route_id}},
            task_blueprints=[
                {
                    "subject": "Execute project retrieval plan",
                    "description": (
                        "Run the fixed project method through registered retrieval "
                        "and topology capabilities."
                    ),
                    "task_type": "project_retrieval",
                    "phase": "research",
                    "execution_mode": "worker",
                    "priority": 1,
                    "write_set": [f"project:{project_key}:retrieval-run:{plan.get('run_id') or plan_id}"],
                    "read_set": [f"project:{project_key}:retrieval-mode:{plan.get('mode_version')}"],
                    "task_spec": {
                        "plan_id": plan_id,
                        "route_id": route_id,
                        "completion_criteria": ["Read real source bodies and validate formal graph evidence."],
                        "artifact_targets": ["project_retrieval.run_report.json"],
                    },
                }
            ],
        )
        if isinstance(bundle, Failure):
            return {
                "status": "failed",
                "error": _failure(bundle),
                "attempts": [],
                "candidates": [],
                "materials": [],
                "graph": None,
            }
        session_id = str(bundle["session"]["session_id"])
        task_id = str(bundle["session"]["root_task_id"])
        claimed = service.claim_task(session_id, task_id, owner="project_retrieval.executor")
        if isinstance(claimed, Failure):
            return {
                "status": "failed",
                "error": _failure(claimed),
                "session_id": session_id,
                "attempts": [],
                "candidates": [],
                "materials": [],
                "graph": None,
            }
        registry = build_project_core_tool_registry(service=service)
    except Exception as exc:
        return {
            "status": "failed",
            "error": {"code": "SESSION_UNAVAILABLE", "message": str(exc)},
            "attempts": [],
            "candidates": [],
            "materials": [],
            "graph": None,
        }

    request = AgentCoreRequest(
        message=f"Execute fixed project retrieval plan {plan_id}", session_id=session_id, project_key=project_key
    )
    if emit is not None:
        emit("run.started", {"session_id": session_id, "plan_id": plan_id})
    discovery = _tool(
        registry,
        request,
        "source.discovery.plan",
        {
            "topic": route_id,
            "query_terms": [queries[q]["expression"] for q in selected],
            "max_candidates": min(30, max_materials or 1),
        },
        emit=emit,
    )
    attempts: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    materials: list[dict[str, Any]] = []
    formal_packages: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if discovery["status"] != "completed":
        failures.append({"phase": "discovery", "kind": "source_failure", "error": discovery.get("error")})
    seen_urls: set[str] = set()
    executed_expressions: set[str] = set()

    def execute_query(query_id: str, query: Mapping[str, Any]) -> None:
        expression = str(query.get("expression") or "").strip()
        if not expression:
            failures.append({"phase": "search", "kind": "invalid_query", "query_id": query_id})
            return
        if len(attempts) >= max_queries or expression in executed_expressions:
            return
        executed_expressions.add(expression)
        search = _tool(
            registry,
            request,
            "source.web.search",
            {
                "query": expression,
                "language": str(query.get("language") or "bi"),
                "max_results": min(20, max_materials or 1),
            },
            emit=emit,
        )
        receipt_name = f"project_retrieval.search.{_digest(query_id)[:16]}.json"
        receipt_location = f"agent_session:{session_id}:artifact:{receipt_name}"
        try:
            service.store.upsert_artifact(
                {
                    "session_id": session_id,
                    "name": receipt_name,
                    "artifact_type": "project_retrieval_search_receipt",
                    "mime_type": "application/json",
                    "content_text": json.dumps(search, ensure_ascii=False, sort_keys=True, default=str),
                    "content_json": search,
                    "metadata": {"project_key": project_key, "plan_id": plan_id, "query_id": query_id},
                }
            )
        except Exception as exc:
            receipt_location = "unpersisted:search-receipt-failure"
            failures.append(
                {"phase": "receipt", "kind": "persistence_failure", "query_id": query_id, "error": _failure(exc)}
            )
        content = search.get("structured_content") or {}
        found = list(content.get("candidates") or []) if search["status"] == "completed" else []
        attempt = {
            "attempt_id": f"attempt-{_digest((session_id, query_id))[:24]}",
            "query_id": query_id,
            "round_id": session_id,
            "clue_key": route_id,
            "executed_at": _now(),
            "tool": "source.web.search",
            "actual_query": expression,
            "result": "access_failed" if search["status"] != "completed" else ("hit" if found else "miss"),
            "source_ids": [],
            "material_ids": [],
            "next_step": "candidate_review" if found else "inspect_provider_diagnostics",
            "result_note": str(search.get("model_summary") or search.get("error") or ""),
            "raw_return_location": receipt_location,
        }
        attempts.append(attempt)
        if search["status"] != "completed":
            failures.append(
                {"phase": "search", "kind": "source_failure", "query_id": query_id, "error": search.get("error")}
            )
            return
        for raw in found:
            if not isinstance(raw, Mapping):
                continue
            candidate = dict(raw)
            url = str(candidate.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            candidate_id = f"candidate-{_digest((session_id, query_id, url))[:24]}"
            item = {
                "candidate_id": candidate_id,
                "query_id": query_id,
                "url": url,
                "title": str(candidate.get("title") or url),
                "provider": candidate.get("provider"),
                "trust": candidate.get("trust"),
                "status": "candidate",
            }
            candidates.append(item)
            if len(materials) >= max_materials:
                item["review_status"] = "budget_exhausted"
                continue
            trusted = str((candidate.get("trust") or {}).get("status") or "") == "accepted"
            if not trusted:
                failures.append(
                    {
                        "phase": "candidate_review",
                        "kind": "source_access_blocked",
                        "candidate_id": candidate_id,
                        "reason": (candidate.get("trust") or {}).get("blocked_reason")
                        or "candidate trust gate did not accept this URL",
                    }
                )
            review = _tool(
                registry,
                request,
                "source.candidate.review",
                {
                    "project_key": project_key,
                    "candidate": candidate,
                    "decision": "approved" if trusted else "deferred",
                    "reason": "Bounded project retrieval: collect trust-accepted URL for body review"
                    if trusted
                    else "URL trust check did not accept collection",
                    "preferred_ingest": "url_pool",
                    "idempotency_key": candidate_id,
                },
                emit=emit,
            )
            item["review_status"] = review["status"]
            item["review_receipt"] = review.get("structured_content")
            if review["status"] != "completed":
                failures.append(
                    {
                        "phase": "review",
                        "kind": "candidate_review_failure",
                        "candidate_id": candidate_id,
                        "error": review.get("error"),
                    }
                )
                continue
            ingest_payload = (review.get("structured_content") or {}).get("ingest_payload")
            if not trusted:
                continue
            if not isinstance(ingest_payload, Mapping) or ingest_payload.get("type") != "url_pool":
                gaps.append(
                    {
                        "code": "CANDIDATE_INGEST_PAYLOAD_MISSING",
                        "candidate_id": candidate_id,
                        "next_gate": (review.get("structured_content") or {}).get("next_gate"),
                    }
                )
                continue
            ingest = _tool(
                registry,
                request,
                "ingest.url_pool.submit",
                {
                    "project_key": project_key,
                    "ingest_payload": dict(ingest_payload),
                    "async_mode": False,
                    "candidate_review_key": candidate_id,
                    "idempotency_key": candidate_id,
                    "search_options": {"disable_site_seed_expansion": True},
                },
                emit=emit,
            )
            dispatch = (ingest.get("structured_content") or {}).get("dispatch_result") or {}
            document_id = dispatch.get("document_id") if isinstance(dispatch, Mapping) else None
            body_read, body = (
                _read_document_body(topology_service, project_key, document_id) if document_id else (None, None)
            )
            material = {
                "candidate_id": candidate_id,
                "url": url,
                "document_id": document_id,
                "status": "body_read"
                if ingest["status"] == "completed" and body_read and body_read["status"] == "read"
                else ("submitted" if ingest["status"] == "completed" else "access_failed"),
                "body_read": body_read,
                "ingest_receipt": {
                    "call_id": ingest.get("call_id"),
                    "tool_status": ingest.get("status"),
                    "task_id": (ingest.get("structured_content") or {}).get("task_id"),
                    "document_id": document_id,
                    "status": dispatch.get("status") if isinstance(dispatch, Mapping) else None,
                    "reason_code": dispatch.get("reason_code") if isinstance(dispatch, Mapping) else None,
                    "errors": dispatch.get("errors") if isinstance(dispatch, Mapping) else None,
                },
                "formal_topology_ref": None,
            }
            materials.append(material)
            if material["status"] != "body_read":
                failures.append(
                    {
                        "phase": "body_read" if document_id else "ingest",
                        "kind": "source_failure",
                        "candidate_id": candidate_id,
                        "error": (body_read or {}).get("error") or ingest.get("error")
                        or _ingest_failure_receipt(dispatch, ingest),
                    }
                )
                continue
            route_rows = (
                (plan.get("binding_snapshot") or {}).get("routes")
                or (plan.get("topology_seed") or {}).get("source_routes")
                or []
            )
            source_route = next(
                (dict(row) for row in route_rows if isinstance(row, Mapping) and row.get("route_id") == route_id), {}
            )
            payload = {
                "project_key": project_key,
                "run_id": str(plan.get("run_id") or session_id),
                "plan_id": plan_id,
                "route_id": route_id,
                "query_id": query_id,
                "candidate_id": candidate_id,
                "document_id": document_id,
                "title": body_read.get("title"),
                "url": body_read.get("uri") or url,
                "body": body,
                "body_digest": body_read["body_digest"],
                "document_updated_at": body_read.get("document_updated_at"),
                "domain_vocabulary": plan.get("domain_vocabulary")
                or (plan.get("topology_seed") or {}).get("domain_vocabulary"),
                "query": dict(query),
                "source_route": source_route,
            }
            try:
                invoked = invoke_skill(
                    skill_id="project_retrieval.formalize_document",
                    payload=payload,
                    context={
                        "actor_role": "orchestration_runtime",
                        "permissions": ["project_retrieval.formalize"],
                        "agent_session_id": session_id,
                        "agent_task_id": task_id,
                        "project_key": project_key,
                        "consumer": "project_retrieval.executor",
                    },
                )
                formal = invoked.get("result")
            except Exception as exc:
                error = _failure(exc)
                code = "FORMALIZATION_OPERATOR_UNAVAILABLE" if isinstance(exc, KeyError) else "FORMALIZATION_FAILED"
                gaps.append({"code": code, "candidate_id": candidate_id, "error": error})
                if emit is not None:
                    emit("formalizer.result", {"candidate_id": candidate_id, "status": "failed", "error": error})
                continue
            if not isinstance(formal, Mapping):
                gaps.append({"code": "FORMALIZATION_INVALID_RESULT", "candidate_id": candidate_id})
                continue
            formal_status = str(formal.get("status") or "")
            material["formalizer_status"] = formal_status
            material["formalizer_gaps"] = list(formal.get("gaps") or [])
            if formal_status == "proposed":
                gaps.extend(
                    {"code": "FORMALIZATION_REMAINING_GAP", "candidate_id": candidate_id, "detail": detail}
                    for detail in formal.get("gaps") or []
                )
            if formal.get("error"):
                material["formalizer_error"] = formal["error"]
            if emit is not None:
                emit("formalizer.result", {"candidate_id": candidate_id, "status": formal_status})
            if formal_status != "proposed" or not isinstance(formal.get("proposal"), Mapping):
                gaps.append(
                    {
                        "code": "NO_CLAIM" if formal_status == "no_claim" else "FORMALIZATION_FAILED",
                        "candidate_id": candidate_id,
                        "details": list(formal.get("gaps") or []),
                        "error": formal.get("error"),
                    }
                )
                continue
            current_body_read, current_body = _read_document_body(topology_service, project_key, document_id)
            if (
                current_body_read.get("status") != "read"
                or current_body_read.get("body_digest") != body_read.get("body_digest")
                or current_body_read.get("document_updated_at") != body_read.get("document_updated_at")
                or current_body != body
            ):
                gaps.append({"code": "SOURCE_CHANGED", "candidate_id": candidate_id, "document_id": document_id})
                continue
            formal_packages.append(
                {
                    "proposal": dict(formal["proposal"]),
                    "body_read": body_read,
                    "body": body,
                    "candidate_id": candidate_id,
                    "query": query,
                    "source_route": source_route,
                    "url": url,
                }
            )

    for query_id in selected:
        execute_query(query_id, queries[query_id])

    followup_rounds = 0
    if max_followups and (gaps or failures):
        for round_number in range(1, max_followups + 1):
            if len(attempts) >= max_queries:
                gaps.append(
                    {"code": "FOLLOWUP_QUERY_BUDGET_EXHAUSTED", "remaining_rounds": max_followups - followup_rounds}
                )
                break
            gap = gaps[-1] if gaps else failures[-1]
            gap_subject = str(
                gap.get("message") or gap.get("code") or gap.get("reason") or gap.get("kind") or "evidence gap"
            )
            planned = _tool(
                registry,
                request,
                "source.discovery.plan",
                {
                    "topic": f"{route_id}: {gap_subject}",
                    "query_terms": [queries[selected[0]]["expression"], gap_subject],
                    "max_candidates": min(30, max_queries - len(attempts)),
                },
                emit=emit,
            )
            if planned["status"] != "completed":
                gaps.append({"code": "FOLLOWUP_PLANNER_FAILED", "round": round_number, "error": planned.get("error")})
                break
            proposed_queries = (planned.get("structured_content") or {}).get("search_queries") or []
            expression = next(
                (
                    str(item.get("query") or "").strip()
                    for item in proposed_queries
                    if isinstance(item, Mapping)
                    and str(item.get("query") or "").strip()
                    and str(item.get("query") or "").strip() not in executed_expressions
                ),
                "",
            )
            if not expression:
                gaps.append({"code": "FOLLOWUP_QUERY_UNAVAILABLE", "round": round_number})
                break
            originating = next((item for item in candidates if item["candidate_id"] == gap.get("candidate_id")), None)
            basis_id = str((originating or {}).get("query_id") or selected[0])
            basis = dict(queries.get(basis_id) or queries[selected[0]])
            followup_id = f"followup:{round_number}:{_digest(expression)[:12]}"
            basis.update({"query_id": followup_id, "route_id": route_id, "expression": expression})
            execute_query(followup_id, basis)
            followup_rounds += 1

    topology = _append_attempts(
        topology_service=topology_service,
        project_key=project_key,
        topology_ref=plan.get("topology_ref"),
        profile_id=str(plan.get("profile_id") or ""),
        topology_seed=plan.get("topology_seed"),
        profile_version=str(plan.get("profile_version") or ""),
        session_id=session_id,
        attempts=attempts,
        formal_packages=formal_packages,
    )
    if topology["status"] in {"failed", "blocked", "readback_failed"}:
        failures.append(
            {
                "phase": "topology_write",
                "kind": "structure_conflict"
                if (topology.get("error") or {}).get("code")
                in {"VERSION_CONFLICT", "PROFILE_VERSION_CONFLICT", "IDENTITY_CONFLICT"}
                else "topology_unavailable",
                "error": topology.get("error"),
            }
        )
    for rejected in topology.get("rejected_formal") or []:
        gaps.append({"code": "FORMAL_PROPOSAL_REJECTED", **rejected})
    budget_deferred = sum(item.get("review_status") == "budget_exhausted" for item in candidates)
    if budget_deferred:
        gaps.append({"code": "MATERIAL_BUDGET_EXHAUSTED", "remaining_candidates": budget_deferred})
    if (
        (gaps or failures)
        and max_followups
        and followup_rounds < max_followups
        and not any(item["code"].startswith("FOLLOWUP_") for item in gaps)
    ):
        gaps.append(
            {"code": "FOLLOWUP_INCOMPLETE", "executed_rounds": followup_rounds, "allowed_rounds": max_followups}
        )
    formal_graph_refs = list(topology.get("formal_graph_refs") or [])
    status = (
        "completed"
        if formal_graph_refs and not gaps and not failures
        else ("partial" if attempts or candidates or materials else "blocked")
    )
    report = {
        "plan_id": plan_id,
        "session_id": session_id,
        "route_id": route_id,
        "query_ids": selected,
        "attempt_ids": [item["attempt_id"] for item in attempts],
        "candidate_ids": [item["candidate_id"] for item in candidates],
        "document_ids": [item["document_id"] for item in materials if item.get("document_id")],
        "read_document_ids": [item["document_id"] for item in materials if item["status"] == "body_read"],
        "topology_attempt_refs": topology.get("attempt_refs") or [],
        "topology_ref": topology.get("topology_ref"),
        "profile_id": topology.get("profile_id"),
        "profile_version": topology.get("profile_version"),
        "formal_graph_refs": formal_graph_refs,
        "gaps": gaps,
    }
    result = {
        "status": status,
        "session_id": session_id,
        "plan_id": plan_id,
        "mode_id": plan.get("mode_id"),
        "mode_version": plan.get("mode_version"),
        "discovery": discovery,
        "attempts": attempts,
        "candidates": candidates,
        "materials": materials,
        "topology_write": topology,
        "graph": {"topology_ref": topology.get("topology_ref"), "groups": formal_graph_refs}
        if formal_graph_refs
        else None,
        "failures": failures,
        "gaps": gaps,
        "report": report,
        "followup_rounds": followup_rounds,
    }
    try:
        service.store.upsert_artifact(
            {
                "session_id": session_id,
                "name": "project_retrieval.run_report.json",
                "artifact_type": "project_retrieval_run_report",
                "mime_type": "application/json",
                "content_text": json.dumps(report, ensure_ascii=False, sort_keys=True, default=str),
                "content_json": report,
                "metadata": {"project_key": project_key, "plan_id": plan_id},
            }
        )
    except Exception as exc:
        failures.append({"phase": "report", "kind": "persistence_failure", "error": _failure(exc)})
        gaps.append({"code": "REPORT_PERSISTENCE_FAILED"})
        report["gaps"] = gaps
        if status == "completed":
            status = "partial"
            result["status"] = status
    if emit is not None:
        emit(
            "run.finished",
            {
                "session_id": session_id,
                "status": status,
                "attempt_count": len(attempts),
                "material_count": len(materials),
                "formal_graph_count": len(formal_graph_refs),
            },
        )
    service.release_task(
        session_id,
        task_id,
        status="completed" if status == "completed" else "failed",
        result_summary="Formal graph committed" if status == "completed" else "Retrieval finished with unresolved gaps",
        result_payload={
            "plan_id": plan_id,
            "run_id": plan.get("run_id"),
            "status": status,
            "report_artifact": "project_retrieval.run_report.json",
        },
        tool_use_count=1 + len(selected) + len(candidates) + len(materials),
    )
    return result


__all__ = ["execute_retrieval_run"]
