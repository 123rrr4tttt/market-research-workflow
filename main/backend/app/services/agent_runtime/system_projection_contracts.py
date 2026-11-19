from __future__ import annotations

from dataclasses import dataclass

from app.contracts.json import JSONObject


SYSTEM_ID = "mrw.system"
SYSTEM_INSPECT_TOOL_NAME = "agent_runtime.system.inspect"
SYSTEM_PROJECTION_CONTRACT_VERSION = "mrw.system_projection.v1"
UNMAPPED_TOOLS_COVERAGE_REF = "mrw.coverage.unmapped_tools"
SYSTEM_INSPECT_DESCRIPTION = (
    "Inspect the MRW system structure by semantic query or exact object/tool reference. "
    "This tool is read-only and never executes referenced tools."
)
EXPECTED_RESPONSIBILITY_REFS = (
    "mrw.sources",
    "mrw.ingestion",
    "mrw.retrieval",
    "mrw.workflow",
    "mrw.writing",
    "mrw.consumers",
    "mrw.agent",
    "mrw.persistence",
)
EXPECTED_SOURCE_OWNER = {
    "mrw.sources": "main/backend/app/services/agent_runtime/system_sources_materials.py:SYSTEM_OBJECTS",
    "mrw.ingestion": "main/backend/app/services/agent_runtime/system_sources_materials.py:SYSTEM_OBJECTS",
    "mrw.retrieval": "main/backend/app/services/agent_runtime/system_sources_materials.py:SYSTEM_OBJECTS",
    "mrw.workflow": "main/backend/app/services/agent_runtime/system_sources_work.py:SYSTEM_OBJECTS",
    "mrw.writing": "main/backend/app/services/agent_runtime/system_sources_work.py:SYSTEM_OBJECTS",
    "mrw.consumers": "main/backend/app/services/agent_runtime/system_sources_work.py:SYSTEM_OBJECTS",
    "mrw.agent": "main/backend/app/services/agent_runtime/system_sources_host.py:SYSTEM_OBJECTS",
    "mrw.persistence": "main/backend/app/services/agent_runtime/system_sources_host.py:SYSTEM_OBJECTS",
}
SYSTEM_RELATION_KINDS = frozenset(
    {"contains", "uses", "produces", "consumed_by", "observes"}
)
SYSTEM_PROJECTION_ARGUMENTS = frozenset(
    {"query", "ref", "limit", "offset", "revision"}
)


@dataclass(frozen=True, slots=True)
class SystemRelation:
    kind: str
    target_ref: str


@dataclass(frozen=True, slots=True)
class SystemObjectSource:
    ref: str
    title: str
    summary: str
    owner_ref: str
    source_refs: tuple[str, ...]
    purpose_terms: tuple[str, ...]
    tool_refs: tuple[str, ...]
    relations: tuple[SystemRelation, ...]


def system_inspect_input_schema() -> JSONObject:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "query": {
                "type": "string",
                "maxLength": 256,
                "description": "Chinese or English semantic search text. Omit to read the root object.",
            },
            "ref": {
                "type": "string",
                "description": (
                    "Exact system object ID, tool:<tool name>, or "
                    "mrw.coverage.unmapped_tools."
                ),
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "default": 8,
                "description": "Maximum combined number of returned items and relations.",
            },
            "offset": {
                "type": "integer",
                "minimum": 0,
                "default": 0,
                "description": "Offset in the deterministic object, relations, target-object sequence.",
            },
            "revision": {
                "type": "string",
                "description": "Revision from a prior page. A different value returns stale_projection.",
            },
        },
    }


def system_inspect_capability() -> JSONObject:
    return {
        "capability_id": SYSTEM_INSPECT_TOOL_NAME,
        "name": "MRW system inspector",
        "description": SYSTEM_INSPECT_DESCRIPTION,
        "domain": "agent_runtime",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [
            {
                "type": "internal_service",
                "id": "app.services.agent_runtime.system_projection.inspect_system_projection",
            }
        ],
        "required_input": [],
        "risks": [],
        "implemented": True,
    }


__all__ = [
    "EXPECTED_RESPONSIBILITY_REFS",
    "EXPECTED_SOURCE_OWNER",
    "SYSTEM_ID",
    "SYSTEM_INSPECT_DESCRIPTION",
    "SYSTEM_INSPECT_TOOL_NAME",
    "SYSTEM_PROJECTION_ARGUMENTS",
    "SYSTEM_PROJECTION_CONTRACT_VERSION",
    "SYSTEM_RELATION_KINDS",
    "SystemObjectSource",
    "SystemRelation",
    "UNMAPPED_TOOLS_COVERAGE_REF",
    "system_inspect_capability",
    "system_inspect_input_schema",
]
