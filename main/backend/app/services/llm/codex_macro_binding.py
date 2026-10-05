from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Annotated, Any
from uuid import uuid4

from functorial_kit import Failure


_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_NAMESPACE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

NativeToolHandler = Callable[[Mapping[str, Any]], Any]

_SKILL_ROOTS = (Path(__file__).resolve().parents[3] / "skills",)


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


@dataclass(frozen=True, slots=True)
class NativeMacroAssembly:
    """A resolved and assembled macro environment plus its declaration observation."""

    binding: NativeAgentBinding
    package_id: str | None
    package_version: str | None
    declared_tool_names: tuple[str, ...]
    skill_names: tuple[str, ...]
    environment_digest: str


def _trusted_host_context(
    *,
    project_key: str,
    session_id: str,
    host_thread_id: str,
    turn_id: str | None = None,
    user_message_id: str | None = None,
) -> Any:
    from app.services.agent_core.host_authorization import TrustedHostContext

    return TrustedHostContext(
        project_key=str(project_key).strip(),
        session_id=str(session_id).strip(),
        host_thread_id=str(host_thread_id).strip(),
        turn_id=str(turn_id or "").strip() or f"turn-{uuid4().hex}",
        user_message_id=str(user_message_id or "").strip()
        or f"host-message-{uuid4().hex}",
    )


def resolve_agent_macro_environment(
    *,
    project_key: str,
    service: Any,
    package_id: str | None = None,
    package_version: str | None = None,
) -> Any | Failure:
    """Resolve the unique active package (or base), or one explicit identity."""

    from app.services.agent_core.macro_environment import (
        resolve_macro_environment,
        select_active_macro_identity,
    )
    from app.services.agent_core.project_tools import build_project_core_tool_registry

    registry = build_project_core_tool_registry(service=service)
    identity = select_active_macro_identity(
        service, project_key, package_id, package_version
    )
    if isinstance(identity, Failure):
        return identity
    ids, versions = identity
    return resolve_macro_environment(
        service, project_key, ids, versions, _SKILL_ROOTS, registry
    )


def assemble_agent_macro_binding(
    *,
    project_key: str,
    service: Any,
    trusted_host_context: Any,
    package_id: str | None = None,
    package_version: str | None = None,
) -> NativeMacroAssembly | Failure:
    """Resolve and assemble one macro environment without starting a native turn."""

    from app.services.agent_core.macro_environment import assemble_native_macro_binding

    resolved = resolve_agent_macro_environment(
        project_key=project_key,
        service=service,
        package_id=package_id,
        package_version=package_version,
    )
    if isinstance(resolved, Failure):
        return resolved
    binding = assemble_native_macro_binding(resolved, trusted_host_context, service)
    if isinstance(binding, Failure):
        return binding
    package = resolved.package
    return NativeMacroAssembly(
        binding=binding,
        package_id=package.package_id if package is not None else None,
        package_version=package.package_version if package is not None else None,
        declared_tool_names=tuple(spec.name for spec in resolved.declared_tools),
        skill_names=tuple(skill.native.name for skill in resolved.skills),
        environment_digest=resolved.environment_digest,
    )


def build_agent_macro_pilot_binding(
    *,
    project_key: str,
    scope_id: str,
    service: Any,
    session_id: str,
    turn_id: str | None = None,
    user_message_id: str | None = None,
) -> Annotated[
    NativeAgentBinding | Failure,
    "kit:prepared-command effect_boundary=codex_native_agent_macro_binding "
    "witness=test:test_pilot_builder_surfaces_failure_without_fallback",
]:
    """Bind the project's unique active macro package, or the native base."""

    context = _trusted_host_context(
        project_key=project_key,
        session_id=session_id,
        host_thread_id=scope_id,
        turn_id=turn_id,
        user_message_id=user_message_id,
    )
    assembly = assemble_agent_macro_binding(
        project_key=project_key,
        service=service,
        trusted_host_context=context,
    )
    return assembly if isinstance(assembly, Failure) else assembly.binding


def build_agent_macro_rapid_binding(
    *,
    project_key: str,
    scope_id: str,
    service: Any,
    session_id: str,
    turn_id: str | None = None,
    user_message_id: str | None = None,
) -> Annotated[
    NativeAgentBinding | Failure,
    "kit:prepared-command effect_boundary=codex_native_agent_macro_binding "
    "witness=test:test_rapid_builder_keeps_ordinary_core_without_global_capability_ban",
]:
    """Bind the project's unique active macro package, or the native base."""

    context = _trusted_host_context(
        project_key=project_key,
        session_id=session_id,
        host_thread_id=scope_id,
        turn_id=turn_id,
        user_message_id=user_message_id,
    )
    assembly = assemble_agent_macro_binding(
        project_key=project_key,
        service=service,
        trusted_host_context=context,
    )
    return assembly if isinstance(assembly, Failure) else assembly.binding
