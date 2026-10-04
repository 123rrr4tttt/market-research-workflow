from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Annotated, Any


_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_NAMESPACE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

NativeToolHandler = Callable[[Mapping[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class NativeSkillBinding:
    """One exact skill body mounted into a native Codex thread environment."""

    name: str
    path: str
    content_digest: str

    @classmethod
    def from_path(cls, *, name: str, path: str | Path) -> "NativeSkillBinding":
        resolved = Path(path).expanduser().resolve()
        if resolved.name != "SKILL.md" or not resolved.is_file():
            # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_binding_rejects_invalid_authoring
            raise ValueError("native skill path must identify an existing SKILL.md")
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        return cls(name=str(name).strip(), path=str(resolved), content_digest=digest)

    def __post_init__(self) -> None:
        if not self.name or not _TOOL_NAME_RE.fullmatch(self.name):
            # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_binding_rejects_invalid_authoring
            raise ValueError("native skill name is invalid")
        if len(self.content_digest) != 64:
            # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_binding_rejects_invalid_authoring
            raise ValueError("native skill content digest must be sha256")

    @property
    def root(self) -> str:
        return str(Path(self.path).parent.parent)

    def turn_input(self) -> dict[str, str]:
        return {"type": "skill", "name": self.name, "path": self.path}


@dataclass(frozen=True, slots=True)
class NativeToolBinding:
    """Typed client-side callback for one Codex dynamic tool."""

    name: str
    description: str
    input_schema: Mapping[str, Any]
    handler: NativeToolHandler
    namespace: str | None = None

    def __post_init__(self) -> None:
        if not _TOOL_NAME_RE.fullmatch(self.name):
            # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_binding_rejects_invalid_authoring
            raise ValueError("native tool name is invalid")
        if self.namespace is not None and not _NAMESPACE_RE.fullmatch(self.namespace):
            # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_binding_rejects_invalid_authoring
            raise ValueError("native tool namespace is invalid")
        if not self.description.strip():
            # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_binding_rejects_invalid_authoring
            raise ValueError("native tool description is required")
        if not callable(self.handler):
            # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_binding_rejects_invalid_authoring
            raise TypeError("native tool handler must be callable")
        if self.input_schema.get("type") != "object":
            # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_binding_rejects_invalid_authoring
            raise ValueError("native tool input schema must describe an object")

    @property
    def logical_name(self) -> str:
        return f"{self.namespace}.{self.name}" if self.namespace else self.name

    def function_spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "inputSchema": dict(self.input_schema),
            "deferLoading": False,
        }


@dataclass(frozen=True, slots=True)
class NativeAgentBinding:
    """Explicit project and capability environment for one native Codex thread."""

    binding_id: str
    project_key: str
    scope_id: str
    skills: tuple[NativeSkillBinding, ...]
    tools: tuple[NativeToolBinding, ...]
    base_instructions: str
    developer_instructions: str
    sandbox: str = "workspace-write"
    approval_policy: str = "never"
    ephemeral: bool = True
    core_mode: str = "native-agent"

    def __post_init__(self) -> None:
        for value, label in (
            (self.binding_id, "binding_id"),
            (self.project_key, "project_key"),
            (self.scope_id, "scope_id"),
            (self.base_instructions, "base_instructions"),
            (self.developer_instructions, "developer_instructions"),
        ):
            if not str(value).strip():
                # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_binding_rejects_invalid_authoring
                raise ValueError(f"native agent {label} is required")
        if self.core_mode != "native-agent":
            # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_binding_rejects_invalid_authoring
            raise ValueError("NativeAgentBinding only represents native-agent mode")
        if self.sandbox not in {"read-only", "workspace-write"}:
            # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_binding_rejects_invalid_authoring
            raise ValueError("native agent sandbox must be read-only or workspace-write")
        if self.approval_policy != "never":
            # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_binding_rejects_invalid_authoring
            raise ValueError("native agent approval requests are not supported")
        skill_names = [item.name for item in self.skills]
        tool_names = [item.logical_name for item in self.tools]
        if len(skill_names) != len(set(skill_names)) or len(tool_names) != len(set(tool_names)):
            # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_binding_rejects_invalid_authoring
            raise ValueError("native skill and tool identities must be unique")

    @property
    def skill_roots(self) -> tuple[str, ...]:
        return tuple(sorted({item.root for item in self.skills}))

    @property
    def environment_digest(self) -> str:
        payload = {
            "binding_id": self.binding_id,
            "project_key": self.project_key,
            "scope_id": self.scope_id,
            "core_mode": self.core_mode,
            "sandbox": self.sandbox,
            "approval_policy": self.approval_policy,
            "ephemeral": self.ephemeral,
            "base_instructions": self.base_instructions,
            "developer_instructions": self.developer_instructions,
            "skills": [
                {"name": item.name, "path": item.path, "digest": item.content_digest}
                for item in self.skills
            ],
            "tools": [
                {
                    "name": item.name,
                    "namespace": item.namespace,
                    "description": item.description,
                    "input_schema": item.input_schema,
                }
                for item in self.tools
            ],
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def dynamic_tool_specs(self) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        namespaces: dict[str, list[NativeToolBinding]] = {}
        for tool in self.tools:
            if tool.namespace is None:
                specs.append(tool.function_spec())
            else:
                namespaces.setdefault(tool.namespace, []).append(tool)
        for namespace in sorted(namespaces):
            specs.append(
                {
                    "type": "namespace",
                    "name": namespace,
                    "description": f"MRW {namespace} operations.",
                    "tools": [item.function_spec() for item in namespaces[namespace]],
                }
            )
        return specs

    def find_tool(self, *, namespace: str | None, name: str) -> NativeToolBinding | None:
        for tool in self.tools:
            if tool.name == name and tool.namespace == namespace:
                return tool
        return None

    def capability_status(self) -> dict[str, str]:
        return {
            "dynamic_tools": "supported",
            "skills_extra_roots": "supported",
            "same_process_continuation": "supported",
            "thread_resume_after_process_exit": "not_supported",
            "turn_interrupt": "supported",
            "approval_requests": "not_supported",
        }


def build_agent_macro_pilot_binding(
    *, project_key: str, scope_id: str
) -> Annotated[
    NativeAgentBinding,
    "kit:prepared-command effect_boundary=codex_native_agent_read_only_binding "
    "witness=test:test_native_turn_mounts_skill_and_dispatches_existing_read_only_handler",
]:
    """Bind the M2a skill to the existing project-retrieval read-only handler."""

    from app.services.project_retrieval.skill import read_run
    from app.services.projects.context import bind_project

    skill_path = (
        Path(__file__).resolve().parents[3]
        / "skills"
        / "agent-macro-pilot"
        / "SKILL.md"
    )

    def project_read_run(arguments: Mapping[str, Any]) -> Any:
        with bind_project(project_key):
            return read_run(arguments)

    return NativeAgentBinding(
        binding_id="agent-macro-pilot.v1",
        project_key=project_key,
        scope_id=scope_id,
        skills=(
            NativeSkillBinding.from_path(name="agent-macro-pilot", path=skill_path),
        ),
        tools=(
            NativeToolBinding(
                namespace="project_retrieval",
                name="read_run",
                description="Read one persisted retrieval run in the trusted active project.",
                input_schema={
                    "type": "object",
                    "properties": {"run_id": {"type": "string", "minLength": 1}},
                    "required": ["run_id"],
                    "additionalProperties": False,
                },
                handler=project_read_run,
            ),
        ),
        base_instructions=(
            "You are an MRW native Agent bound to one trusted project and capability scope. "
            "Use only the mounted read-only skill and tools. Never infer another project identity."
        ),
        developer_instructions=(
            "Apply agent-macro-pilot only to retrieval-run readback. Preserve missing, queued, "
            "failed, and completed states exactly as returned by the mounted handler."
        ),
        sandbox="read-only",
    )


def build_agent_macro_rapid_binding(
    *, project_key: str, scope_id: str, service: Any, session_id: str
) -> Annotated[
    NativeAgentBinding,
    "kit:prepared-command effect_boundary=codex_native_agent_rapid_binding "
    "witness=test:test_rapid_binding_projects_registered_effects_as_dynamic_tools",
]:
    """Mount the Rapid collection edges into the native Core.

    The binding projects the ordinary Core registry into the native agent.  The
    model calls these as standard native tools; their handlers retain the
    existing authority, persistence and readback semantics.
    """

    from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
    from app.services.agent_core.project_tools import build_project_core_tool_registry
    from app.services.projects.context import bind_project

    skill_path = (
        Path(__file__).resolve().parents[3]
        / "skills"
        / "agent-macro-rapid"
        / "SKILL.md"
    )
    registry = build_project_core_tool_registry(service=service)
    # Rapid is a skill/context over the general Core surface.  Do not create a
    # second Rapid-only registry: project tools, writing tools, ingest tools,
    # topology tools and session tools all remain the ordinary Core surface.
    requested = tuple(spec.name for spec in registry.list_specs())
    tools: list[NativeToolBinding] = []
    for logical_name in requested:
        spec = registry.get(logical_name)
        if spec is None:
            continue
        segments = logical_name.split(".")
        if len(segments) >= 3:
            # The app-server namespace grammar is one level deep. Preserve the
            # full project identity in the namespace while keeping the callable
            # name schema-safe (e.g. source_web.search).
            namespace, name = ("_".join(segments[:-1]), segments[-1])
        elif len(segments) == 2:
            namespace, name = segments
        else:
            namespace, name = None, logical_name
        if not _TOOL_NAME_RE.fullmatch(name):
            continue

        def handler(
            arguments: Mapping[str, Any],
            *,
            logical_name: str = logical_name,
            spec: Any = spec,
        ) -> Any:
            request = AgentCoreRequest(
                message="native Rapid tool call",
                session_id=session_id,
                project_key=project_key,
                context={"runtime_variant": "agent_macro_rapid_native"},
            )
            call = CoreToolCall(
                tool_name=logical_name,
                arguments=dict(arguments),
                call_id=f"native-{hashlib.sha256(json.dumps(dict(arguments), sort_keys=True, default=str).encode()).hexdigest()[:20]}",
                reason="codex_native_rapid",
            )
            with bind_project(project_key):
                result = registry.execute_tool(
                    tool_call=call,
                    tool_spec=spec,
                    request=request,
                    emit=lambda _event: None,
                )
            return result.to_dict()

        tools.append(
            NativeToolBinding(
                namespace=namespace,
                name=name,
                description=spec.description_for_model,
                input_schema=spec.input_schema,
                handler=handler,
            )
        )

    return NativeAgentBinding(
        binding_id="agent-macro-rapid.v1",
        project_key=project_key,
        scope_id=scope_id,
        skills=(NativeSkillBinding.from_path(name="agent-macro-rapid", path=skill_path),),
        tools=tuple(tools),
        base_instructions=(
            "You are the native Rapid collection agent for one trusted MRW project. "
            "Use the mounted discovery/search/review/ingest/readback tools. Preserve "
            "candidate, snapshot, material, failure and readback identities. "
            "The mounted dynamic Core tools are the ordinary tool surface; the "
            "runtime host mechanism is not a reason to refuse them. Never invoke "
            "shell, Python, browser, MCP discovery, or undeclared capabilities."
        ),
        developer_instructions=(
            "Use the ordinary Core tool surface. For Rapid collection, preserve "
            "candidate, snapshot, material, failure and readback identities, and "
            "continue through the registered ingest/readback tools when needed. "
            "Treat every mounted dynamic tool as directly callable."
        ),
        sandbox="workspace-write",
        approval_policy="never",
    )
