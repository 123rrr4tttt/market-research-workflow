"""Facility bindings for macro cells without a second tool registry.

Each binding keeps the model-visible ``CoreToolSpec`` beside the actual project
handler and records where scope, permission, failure and readback semantics come
from.  M8 may project these bindings into the shared registry; this module does
not mutate that registry itself.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from functorial_kit import Failure

from app.services.agent_core.contracts import (
    AgentCoreRequest,
    CoreEvent,
    CoreToolCall,
    CoreToolResult,
    CoreToolSpec,
)
from app.services.project_retrieval.proposals import (
    RapidProposalTopologyAdapter,
    VocabularyResolver,
    rapid_proposal_from_mapping,
)
from .macro_registration import activate_registration_package, read_registration_package, save_registration_package


FacilityHandler = Callable[
    [CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]],
    CoreToolResult,
]


@dataclass(frozen=True, slots=True)
class FacilityBinding:
    """One authoritative operation projected as a Core tool.

    ``scope_source`` and ``permission_source`` are references to existing
    authority, not permission grants. Macro facilities use trusted request
    scope. Existing project tools can explicitly retain a project selector in
    their input contract; that selector does not grant permissions or roles.
    """

    binding_id: str
    version: str
    tool_spec: CoreToolSpec
    handler: FacilityHandler
    executor_ref: str
    scope_source: str
    permission_source: str
    failure_family: str
    readback_semantics: str
    input_policy: Literal["trusted_request", "project_tool_contract"] = "trusted_request"

    governed_dispatch_ref: str | None = None

    def __post_init__(self) -> None:
        required = (
            self.binding_id,
            self.version,
            self.executor_ref,
            self.scope_source,
            self.permission_source,
            self.failure_family,
            self.readback_semantics,
        )
        if any(not isinstance(value, str) or not value.strip() for value in required):
            # kit:boundary owner=FacilityBinding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_facility_binding_rejects_invalid_authoring
            raise ValueError("facility binding identity and semantic references are required")
        if not callable(self.handler):
            # kit:boundary owner=FacilityBinding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_facility_binding_rejects_invalid_authoring
            raise TypeError("facility binding needs an actual handler")
        if self.tool_spec.project_service_id != self.executor_ref:
            # kit:boundary owner=FacilityBinding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_facility_binding_rejects_invalid_authoring
            raise ValueError("facility executor_ref must name the CoreToolSpec project service")
        properties = self.tool_spec.input_schema.get("properties", {})
        if self.input_policy not in {"trusted_request", "project_tool_contract"}:
            # kit:boundary owner=FacilityBinding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_project_tool_contract_retains_existing_authority_boundaries
            raise ValueError("unsupported facility input policy")
        forbidden = {"permissions", "permission", "actor_role"}
        if self.input_policy == "trusted_request":
            forbidden.add("project_key")
        if isinstance(properties, Mapping) and forbidden & set(properties):
            # kit:boundary owner=FacilityBinding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_facility_binding_rejects_invalid_authoring
            raise ValueError("model-authored facility arguments cannot grant scope or permission")
        session_write = (
            self.input_policy == "project_tool_contract"
            and self.tool_spec.metadata.get("auto_allow_session_write") is True
            and self.tool_spec.concurrency == "serial"
        )
        governed_dispatch = (
            self.input_policy == "project_tool_contract"
            and isinstance(self.governed_dispatch_ref, str)
            and bool(self.governed_dispatch_ref.strip())
            and self.tool_spec.metadata.get("uses_existing_frontdoor") == self.governed_dispatch_ref
            and self.tool_spec.concurrency == "serial"
        )
        if self.governed_dispatch_ref is not None and not governed_dispatch:
            # kit:boundary owner=FacilityBinding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_governed_dispatch_keeps_original_frontdoor_contract
            raise ValueError("governed dispatch must reference the declared serial frontdoor")
        if self.tool_spec.risk != "read_only" and self.tool_spec.permission == "allow" and not (session_write or governed_dispatch):
            # kit:boundary owner=FacilityBinding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_facility_binding_rejects_invalid_authoring
            raise ValueError("effectful facility tools require an explicit permission boundary")

    def to_projection(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "version": self.version,
            "tool_spec": self.tool_spec.to_dict(),
            "executor_ref": self.executor_ref,
            "scope_source": self.scope_source,
            "permission_source": self.permission_source,
            "failure_family": self.failure_family,
            "readback_semantics": self.readback_semantics,
        }


def facility_tool_projection(binding: FacilityBinding) -> tuple[CoreToolSpec, FacilityHandler]:
    """Mechanical projection consumed by the shared registry owner."""
    return binding.tool_spec, binding.handler


def _project_key(request: AgentCoreRequest) -> str | None:
    value = request.project_key
    return value.strip() if isinstance(value, str) and value.strip() else None


def _failure_wire(value: Failure | BaseException, *, fallback_code: str = "facility_failed") -> dict[str, Any]:
    if isinstance(value, Failure):
        return {
            "family": value.family,
            "code": value.code,
            "message": value.message,
            "context": dict(value.context or {}),
        }
    code = str(getattr(value, "code", "") or fallback_code)
    return {"family": type(value).__name__, "code": code, "message": str(value), "context": {}}


def _failed(call: CoreToolCall, error: Failure | BaseException, *, summary: str) -> CoreToolResult:
    return CoreToolResult(
        call_id=call.call_id,
        tool_name=call.tool_name,
        status="failed",
        model_summary=summary,
        error=_failure_wire(error),
    )


def _missing_project(call: CoreToolCall) -> CoreToolResult:
    return CoreToolResult(
        call_id=call.call_id,
        tool_name=call.tool_name,
        status="failed",
        model_summary="This facility requires a project-bound session.",
        error={
            "family": "agent_core.facility",
            "code": "project_scope_required",
            "message": "project scope must come from AgentCoreRequest.project_key",
            "context": {},
        },
    )


def project_retrieval_current_facility(service: Any) -> FacilityBinding:
    spec = CoreToolSpec(
        name="project_retrieval.current",
        title="Read Current Project Retrieval Binding",
        description_for_model="Read the current versioned retrieval binding for the active project.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={"type": "object", "additionalProperties": True},
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        project_service_id="project_retrieval.current",
        metadata={"contract_version": "project_retrieval.current.facility.v1", "implemented": True},
    )

    def handler(
        tool_call: CoreToolCall,
        _tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        _emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _project_key(request)
        if project_key is None:
            return _missing_project(tool_call)
        try:
            current = service.current(project_key)
        except Exception as exc:
            return _failed(tool_call, exc, summary="Project retrieval binding could not be read.")
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Read retrieval binding {current.get('mode_id')}@{current.get('version')}.",
            structured_content={"project_key": project_key, "current": current},
        )

    return FacilityBinding(
        binding_id="facility.project_retrieval.current",
        version="1",
        tool_spec=spec,
        handler=handler,
        executor_ref="project_retrieval.current",
        scope_source="AgentCoreRequest.project_key",
        permission_source="ProjectRetrievalService.current read boundary",
        failure_family="project_retrieval.failure",
        readback_semantics="current versioned project retrieval declaration; no execution receipt",
    )


def information_topology_read_facility(service: Any) -> FacilityBinding:
    spec = CoreToolSpec(
        name="information_topology.read",
        title="Read Project Information Topology",
        description_for_model="Read one persisted topology state in the active project, optionally filtered by type or local id.",
        input_schema={
            "type": "object",
            "required": ["topology_ref"],
            "properties": {
                "topology_ref": {
                    "type": "object",
                    "required": ["module_id", "namespace", "state_id"],
                    "properties": {
                        "module_id": {"type": "string", "minLength": 1},
                        "namespace": {"type": "string", "minLength": 1},
                        "state_id": {"type": "string", "minLength": 1},
                        "revision": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                "filters": {
                    "type": "object",
                    "properties": {
                        "type_ids": {"type": "array", "items": {"type": "string"}},
                        "local_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
        output_schema={"type": "object", "additionalProperties": True},
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        project_service_id="information_topology.read",
        metadata={"contract_version": "information_topology.read.facility.v1", "implemented": True},
    )

    def handler(
        tool_call: CoreToolCall,
        _tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        _emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _project_key(request)
        if project_key is None:
            return _missing_project(tool_call)
        topology_ref = tool_call.arguments.get("topology_ref")
        filters = tool_call.arguments.get("filters", {})
        if not isinstance(topology_ref, Mapping) or not isinstance(filters, Mapping):
            return _failed(tool_call, ValueError("topology_ref and filters must be objects"), summary="Topology read arguments are invalid.")
        try:
            result = service.read_topology(project_key, dict(topology_ref), dict(filters))
        except Exception as exc:
            return _failed(tool_call, exc, summary="Topology could not be read.")
        if isinstance(result, Failure):
            return _failed(tool_call, result, summary="Topology could not be read.")
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Read topology revision {result.get('revision')}.",
            structured_content={"project_key": project_key, "readback": result},
        )

    return FacilityBinding(
        binding_id="facility.information_topology.read",
        version="1",
        tool_spec=spec,
        handler=handler,
        executor_ref="information_topology.read",
        scope_source="AgentCoreRequest.project_key",
        permission_source="InformationTopologyService read boundary",
        failure_family="information_topology",
        readback_semantics="authoritative topology revision and digest",
    )


def _string_array() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string", "minLength": 1}}


def _proposal_schema() -> dict[str, Any]:
    def rows(required: list[str], properties: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "type": "array",
            "items": {
                "type": "object",
                "required": required,
                "properties": dict(properties),
                "additionalProperties": False,
            },
        }

    text = {"type": "string", "minLength": 1}
    return {
        "type": "object",
        "required": [
            "contract_version", "proposal_id", "proposal_version", "claim_ceiling",
            "facets", "queries", "snapshots", "attempts", "occurrences", "digests", "gaps", "frontier",
        ],
        "properties": {
            "contract_version": {"const": "rapid.proposal.v1"},
            "proposal_id": text,
            "proposal_version": text,
            "claim_ceiling": {"const": "expansion_proposal"},
            "facets": rows(["facet_ref", "source_ref"], {"facet_ref": text, "source_ref": text}),
            "queries": rows(["query_id", "facet_ref", "expression"], {"query_id": text, "facet_ref": text, "expression": text}),
            "snapshots": rows(["snapshot_ref", "content_digest", "source_ref"], {"snapshot_ref": text, "content_digest": text, "source_ref": text}),
            "attempts": rows(
                ["attempt_id", "query_id", "outcome", "snapshot_refs"],
                {
                    "attempt_id": text,
                    "query_id": text,
                    "outcome": {"enum": ["hit", "miss", "access_failed", "off_topic", "partial", "unknown"]},
                    "snapshot_refs": _string_array(),
                },
            ),
            "occurrences": rows(
                ["occurrence_id", "facet_ref", "query_id", "attempt_id", "snapshot_ref", "source_ref"],
                {"occurrence_id": text, "facet_ref": text, "query_id": text, "attempt_id": text, "snapshot_ref": text, "source_ref": text},
            ),
            "digests": rows(
                ["digest_id", "occurrence_ids", "summary", "classification_proposals", "analysis_positions", "coverage_boundary", "failure_boundary"],
                {"digest_id": text, "occurrence_ids": _string_array(), "summary": text, "classification_proposals": _string_array(), "analysis_positions": _string_array(), "coverage_boundary": text, "failure_boundary": text},
            ),
            "gaps": rows(
                ["gap_id", "facet_ref", "description", "source_attempt_ids", "source_occurrence_ids"],
                {"gap_id": text, "facet_ref": text, "description": text, "source_attempt_ids": _string_array(), "source_occurrence_ids": _string_array()},
            ),
            "frontier": rows(
                ["frontier_id", "facet_ref", "proposed_query", "reason", "source_digest_ids", "source_gap_ids", "source_occurrence_ids"],
                {"frontier_id": text, "facet_ref": text, "proposed_query": text, "reason": text, "source_digest_ids": _string_array(), "source_gap_ids": _string_array(), "source_occurrence_ids": _string_array()},
            ),
        },
        "additionalProperties": False,
    }


def rapid_proposal_save_facility(
    adapter: RapidProposalTopologyAdapter,
    vocabulary_resolver: VocabularyResolver,
) -> FacilityBinding:
    spec = CoreToolSpec(
        name="project_retrieval.rapid_proposal.save",
        title="Save Rapid Expansion Proposal",
        description_for_model=(
            "Validate and save one source-closed Rapid expansion proposal in the active project. "
            "A saved proposal remains below formal evidence qualification."
        ),
        input_schema={
            "type": "object",
            "required": ["proposal"],
            "properties": {"proposal": _proposal_schema()},
            "additionalProperties": False,
        },
        output_schema={"type": "object", "additionalProperties": True},
        source="project",
        risk="write_shared",
        permission="ask",
        concurrency="serial",
        timeout_seconds=30,
        project_service_id="project_retrieval.rapid_proposal.save",
        metadata={
            "contract_version": "project_retrieval.rapid_proposal.save.v1",
            "implemented": True,
            "claim_ceiling": "expansion_proposal",
        },
    )

    def handler(
        tool_call: CoreToolCall,
        _tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        _emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _project_key(request)
        if project_key is None:
            return _missing_project(tool_call)
        proposal = rapid_proposal_from_mapping(tool_call.arguments.get("proposal"))
        if isinstance(proposal, Failure):
            return _failed(tool_call, proposal, summary="Rapid proposal contract is invalid.")
        vocabulary = vocabulary_resolver(project_key)
        if isinstance(vocabulary, Failure):
            return _failed(tool_call, vocabulary, summary="Project retrieval vocabulary could not be resolved.")
        observation = adapter.save(project_key, proposal, vocabulary)
        status = {
            "persisted": "completed",
            "already_persisted": "completed",
            "conflict": "failed",
            "failed": "failed",
            "unknown": "deferred",
        }[observation.status]
        error = dict(observation.failure) if observation.failure is not None else None
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status=status,
            model_summary=(
                f"Rapid proposal {proposal.identity} persistence status: {observation.status}; "
                f"readback: {observation.readback_status}."
            ),
            structured_content={"save_observation": observation.to_mapping()},
            error=error,
            retry_hint="Read back the same proposal identity before any retry." if observation.status == "unknown" else None,
        )

    return FacilityBinding(
        binding_id="facility.project_retrieval.rapid_proposal.save",
        version="1",
        tool_spec=spec,
        handler=handler,
        executor_ref="project_retrieval.rapid_proposal.save",
        scope_source="AgentCoreRequest.project_key and project-bound DomainVocabulary resolver",
        permission_source="Core host approval plus InformationTopologyService writer authorization",
        failure_family="project_retrieval.rapid_proposal + information_topology",
        readback_semantics="completed only after exact proposal identity and digest read back",
    )


def rapid_proposal_readback_facility(adapter: RapidProposalTopologyAdapter) -> FacilityBinding:
    spec = CoreToolSpec(
        name="project_retrieval.rapid_proposal.readback",
        title="Read Back Rapid Expansion Proposal",
        description_for_model="Read one persisted Rapid proposal by its versioned identity in the active project.",
        input_schema={
            "type": "object",
            "required": ["proposal_id", "proposal_version"],
            "properties": {
                "proposal_id": {"type": "string", "minLength": 1},
                "proposal_version": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
        output_schema={"type": "object", "additionalProperties": True},
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        project_service_id="project_retrieval.rapid_proposal.readback",
        metadata={"contract_version": "project_retrieval.rapid_proposal.readback.v1", "implemented": True},
    )

    def handler(
        tool_call: CoreToolCall,
        _tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        _emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _project_key(request)
        if project_key is None:
            return _missing_project(tool_call)
        proposal_id = str(tool_call.arguments.get("proposal_id") or "").strip()
        proposal_version = str(tool_call.arguments.get("proposal_version") or "").strip()
        if not proposal_id or not proposal_version:
            return _failed(tool_call, ValueError("proposal_id and proposal_version are required"), summary="Proposal readback identity is invalid.")
        result = adapter.read(project_key, proposal_id, proposal_version)
        if isinstance(result, Failure):
            return _failed(tool_call, result, summary="Rapid proposal could not be read back.")
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Read Rapid proposal {result.identity} with verified contract digest.",
            structured_content={
                "proposal": result.to_mapping(),
                "content_digest": result.content_digest,
                "claim_ceiling": result.claim_ceiling,
            },
        )

    return FacilityBinding(
        binding_id="facility.project_retrieval.rapid_proposal.readback",
        version="1",
        tool_spec=spec,
        handler=handler,
        executor_ref="project_retrieval.rapid_proposal.readback",
        scope_source="AgentCoreRequest.project_key",
        permission_source="InformationTopologyService read boundary",
        failure_family="project_retrieval.rapid_proposal + information_topology",
        readback_semantics="versioned proposal payload with recomputed content digest",
    )


def _registration_package_schema() -> dict[str, Any]:
    text = {"type": "string", "minLength": 1}
    refs = {"type": "array", "items": text, "minItems": 0, "uniqueItems": True}
    return {
        "type": "object",
        "required": ["package_id", "package_version", "owner", "cell"],
        "properties": {
            "contract_version": {"const": "agent_macro.registration_package.v1"},
            "package_id": text,
            "package_version": text,
            "owner": text,
            "cell": {
                "type": "object",
                "required": ["cell_id", "core_binding_ref", "core_mode", "conceptual_rule_refs", "tool_refs", "facility_refs", "readback_refs"],
                "properties": {
                    "cell_id": text, "core_binding_ref": text,
                    "core_mode": {"enum": ["native-agent", "model-only"]},
                    "conceptual_rule_refs": refs, "tool_refs": refs, "facility_refs": refs, "readback_refs": refs,
                },
                "additionalProperties": True,
            },
            "skill_contents": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "relations": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        },
        "additionalProperties": False,
    }


def macro_registration_package_create_facility(service: Any) -> FacilityBinding:
    spec = CoreToolSpec(
        name="agent_macro.registration_package.create",
        title="Create Agent Macro Registration Package",
        description_for_model=(
            "Validate and persist a candidate Agent macro registration package in the current session. "
            "This creates a candidate artifact only; it never activates capabilities or grants authority."
        ),
        input_schema={"type": "object", "required": ["package"], "properties": {"package": _registration_package_schema()}, "additionalProperties": False},
        output_schema={"type": "object", "additionalProperties": True}, source="project", risk="write_shared",
        permission="ask", concurrency="serial", timeout_seconds=30,
        project_service_id="agent_macro.registration_package.create",
        metadata={"contract_version": "agent_macro.registration_package.create.v1", "implemented": True, "activation": "separate_agentcore_consent"},
    )

    def handler(call: CoreToolCall, _spec: CoreToolSpec, request: AgentCoreRequest, _emit: Callable[[CoreEvent], None]) -> CoreToolResult:
        project_key = _project_key(request)
        if project_key is None:
            return _missing_project(call)
        if not request.session_id:
            return _failed(call, ValueError("session_id is required"), summary="Registration package needs a session identity.")
        result = save_registration_package(service, session_id=request.session_id, project_key=project_key, payload=call.arguments.get("package") or {})
        if isinstance(result, Failure):
            return _failed(call, result, summary="Macro registration package was rejected.")
        package = result["package"]
        return CoreToolResult(
            call_id=call.call_id, tool_name=call.tool_name, status="completed",
            model_summary=f"Saved candidate macro registration package {package['package_id']}@{package['package_version']}; activation remains host-owned.",
            structured_content={"registration_package": package, "artifact": result["artifact"], "activation": result["activation"]},
        )

    return FacilityBinding(
        binding_id="facility.agent_macro.registration_package.create", version="1", tool_spec=spec, handler=handler,
        executor_ref="agent_macro.registration_package.create", scope_source="AgentCoreRequest.project_key/session_id",
        permission_source="Candidate creation only; activation requires separate AgentCore user consent", failure_family="agent_runtime",
        readback_semantics="candidate package artifact with canonical content digest",
    )


def macro_registration_package_readback_facility(service: Any) -> FacilityBinding:
    spec = CoreToolSpec(
        name="agent_macro.registration_package.readback", title="Read Back Agent Macro Registration Package",
        description_for_model="Read and verify a candidate macro registration package from the current session.",
        input_schema={"type": "object", "required": ["package_id"], "properties": {"package_id": {"type": "string", "minLength": 1}, "package_version": {"type": "string", "minLength": 1}}, "additionalProperties": False},
        output_schema={"type": "object", "additionalProperties": True}, source="project", risk="read_only", permission="allow", concurrency="parallel",
        project_service_id="agent_macro.registration_package.readback",
        metadata={"contract_version": "agent_macro.registration_package.readback.v1", "implemented": True},
    )

    def handler(call: CoreToolCall, _spec: CoreToolSpec, request: AgentCoreRequest, _emit: Callable[[CoreEvent], None]) -> CoreToolResult:
        project_key = _project_key(request)
        if project_key is None:
            return _missing_project(call)
        if not request.session_id:
            return _failed(call, ValueError("session_id is required"), summary="Registration package needs a session identity.")
        result = read_registration_package(service, session_id=request.session_id, project_key=project_key, package_id=str(call.arguments.get("package_id") or "").strip(), package_version=str(call.arguments.get("package_version") or "").strip() or None)
        if isinstance(result, Failure):
            return _failed(call, result, summary="Registration package readback failed.")
        return CoreToolResult(call_id=call.call_id, tool_name=call.tool_name, status="completed", model_summary="Verified macro registration package readback.", structured_content=result)

    return FacilityBinding(
        binding_id="facility.agent_macro.registration_package.readback", version="1", tool_spec=spec, handler=handler,
        executor_ref="agent_macro.registration_package.readback", scope_source="AgentCoreRequest.project_key/session_id",
        permission_source="Agent session artifact read boundary", failure_family="agent_runtime",
        readback_semantics="recomputed canonical package digest and candidate activation status",
    )


def macro_registration_package_activate_facility(service: Any) -> FacilityBinding:
    spec = CoreToolSpec(
        name="agent_macro.registration_package.activate",
        title="Activate Agent Macro Registration Package",
        description_for_model=(
            "Activate a candidate package after the user has explicitly agreed in this AgentCore conversation. "
            "This records consent and activates only the current session/project scope."
        ),
        input_schema={
            "type": "object",
            "required": ["package_id", "consent_statement"],
            "properties": {
                "package_id": {"type": "string", "minLength": 1},
                "package_version": {"type": "string", "minLength": 1},
                "consent_statement": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
        output_schema={"type": "object", "additionalProperties": True}, source="project", risk="write_shared", permission="ask", concurrency="serial", timeout_seconds=30,
        project_service_id="agent_macro.registration_package.activate",
        metadata={"contract_version": "agent_macro.registration_package.activate.v1", "implemented": True, "activation": "agentcore_user_consent"},
    )

    def handler(call: CoreToolCall, _spec: CoreToolSpec, request: AgentCoreRequest, _emit: Callable[[CoreEvent], None]) -> CoreToolResult:
        project_key = _project_key(request)
        if project_key is None:
            return _missing_project(call)
        if not request.session_id:
            return _failed(call, ValueError("session_id is required"), summary="Registration package activation needs a session identity.")
        result = activate_registration_package(
            service,
            session_id=request.session_id,
            project_key=project_key,
            package_id=str(call.arguments.get("package_id") or "").strip(),
            package_version=str(call.arguments.get("package_version") or "").strip() or None,
            consent_statement=str(call.arguments.get("consent_statement") or "").strip(),
        )
        if isinstance(result, Failure):
            return _failed(call, result, summary="Registration package activation failed.")
        package = result["package"]
        return CoreToolResult(
            call_id=call.call_id, tool_name=call.tool_name, status="completed",
            model_summary=f"Activated macro registration package {package['package_id']}@{package['package_version']} in the current AgentCore scope.",
            structured_content=result,
        )

    return FacilityBinding(
        binding_id="facility.agent_macro.registration_package.activate", version="1", tool_spec=spec, handler=handler,
        executor_ref="agent_macro.registration_package.activate", scope_source="AgentCoreRequest.project_key/session_id",
        permission_source="Explicit user agreement in AgentCore conversation", failure_family="agent_runtime",
        readback_semantics="activated package with recorded user consent and unchanged content digest",
    )


__all__ = [
    "FacilityBinding",
    "FacilityHandler",
    "facility_tool_projection",
    "information_topology_read_facility",
    "project_retrieval_current_facility",
    "rapid_proposal_readback_facility",
    "rapid_proposal_save_facility",
    "macro_registration_package_create_facility",
    "macro_registration_package_readback_facility",
    "macro_registration_package_activate_facility",
]
