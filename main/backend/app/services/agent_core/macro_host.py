from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import threading
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence, TypeGuard, TypedDict
from uuid import uuid4

from functorial_kit import Failure
from app.services.agent_sessions.service import AgentSessionService
from app.services.llm.codex_macro_binding import NativeAgentBinding

from .contracts import AgentCoreRequest, CoreEvent, CoreToolCall, json_object
from app.services.request_identity import RequestActorContext
from .host_authorization import TrustedHostContext, canonical_arguments_sha256
from .macro_environment import (
    ResolvedMacroEnvironment,
    assemble_native_macro_binding,
    native_tool_specs,
    resolve_macro_environment,
    resolve_tool_package_digest,
    select_active_macro_identity,
    SYSTEM_NAVIGATION_INSTRUCTIONS,
)
from .project_tools import build_project_core_tool_registry
from .registry import CoreToolRegistry


ProjectChecker = Callable[[str], bool]


class _DispatchCacheEntry(TypedDict):
    tool: str
    args_digest: str
    response: dict[str, object]


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_string_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return _is_object_mapping(value) and all(isinstance(key, str) for key in value)


def _is_object_sequence(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_string_sequence(value: object) -> TypeGuard[list[str]]:
    if not _is_object_sequence(value):
        return False
    return all(isinstance(item, str) and bool(item.strip()) for item in value)


def _ignore_core_event(_event: CoreEvent) -> None:
    return None


class MacroEnvironmentOwner(Protocol):
    def resolve(
        self,
        *,
        project_key: str,
        binding_id: str,
        phase: str,
        package_id: str | None = None,
        package_version: str | None = None,
    ) -> object: ...

    def assemble(self, environment: MacroEnvironment, context: TrustedHostContext) -> object: ...


class MacroHostError(Exception):
    """A typed failure at the WebUI native-host transport boundary."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class MacroSkillDescriptor:
    name: str
    path: str
    content_digest: str
    source_root: str | None = None
    relative_path: str | None = None


@dataclass(frozen=True, slots=True)
class MacroEnvironment:
    environment_digest: str
    dynamic_tools: tuple[Mapping[str, object], ...]
    skills: tuple[MacroSkillDescriptor, ...]
    skill_roots: tuple[str, ...]
    descriptor: Mapping[str, object]
    status: str
    package_digest: str | None = None
    resolved: ResolvedMacroEnvironment | None = None


@dataclass(frozen=True, slots=True)
class MacroNativeBinding:
    native_binding: NativeAgentBinding
    registry: CoreToolRegistry
    package_digest: str | None

    def logical_tool_name(self, *, namespace: str | None, name: str) -> str | None:
        for spec in self.registry.list_specs():
            parts = str(spec.name).split(".")
            if len(parts) >= 3:
                expected_namespace, expected_name = "_".join(parts[:-1]), parts[-1]
            elif len(parts) == 2:
                expected_namespace, expected_name = parts
            else:
                expected_namespace, expected_name = None, str(spec.name)
            if expected_namespace == namespace and expected_name == name:
                return str(spec.name)
        return None


class DefaultMacroEnvironmentOwner:
    """Wire B's exact activated package and the existing base registry."""

    def __init__(self, *, service: AgentSessionService, source_roots: Sequence[str | Path]) -> None:
        self.service = service
        self.source_roots = tuple(source_roots)

    def resolve(
        self,
        *,
        project_key: str,
        binding_id: str,
        phase: str,
        package_id: str | None = None,
        package_version: str | None = None,
    ) -> MacroEnvironment:
        del binding_id, phase
        registry = build_project_core_tool_registry(service=self.service)
        identity = select_active_macro_identity(
            self.service,
            project_key,
            package_id=package_id,
            package_version=package_version,
        )
        if isinstance(identity, Failure):
            code = dict(identity.context or {}).get("macro_environment_code")
            status_code = 409 if code == "macro_environment_ambiguous" else 503
            raise MacroHostError("macro_environment_invalid", identity.message, status_code=status_code)
        ids, versions = identity
        resolved = resolve_macro_environment(
            self.service,
            project_key,
            ids,
            versions,
            self.source_roots,
            registry,
        )
        if isinstance(resolved, Failure):
            raise MacroHostError("macro_environment_invalid", resolved.message, status_code=503)
        return self._from_resolved(resolved)

    def assemble(self, environment: MacroEnvironment, context: TrustedHostContext) -> MacroNativeBinding:
        if environment.resolved is None:
            raise MacroHostError("macro_environment_unavailable", "macro environment is not resolved", status_code=503)
        native = assemble_native_macro_binding(environment.resolved, context, self.service)
        if isinstance(native, Failure):
            raise MacroHostError("macro_environment_invalid", native.message, status_code=503)
        return MacroNativeBinding(
            native_binding=native,
            registry=environment.resolved.registry,
            package_digest=environment.package_digest,
        )

    def _from_resolved(self, resolved: ResolvedMacroEnvironment) -> MacroEnvironment:
        skills = tuple(
            MacroSkillDescriptor(
                item.native.name,
                item.native.path,
                item.native.content_digest,
                item.source_root,
                item.relative_path,
            )
            for item in resolved.skills
        )
        descriptor = dict(resolved.descriptor())
        descriptor["dynamic_tools"] = native_tool_specs(resolved.registry.list_specs())
        descriptor["skills"] = [
            {
                "name": item.name,
                "path": item.path,
                "content_digest": item.content_digest,
                "source_root": item.source_root,
                "relative_path": item.relative_path,
            }
            for item in skills
        ]
        descriptor["skill_roots"] = sorted({str(Path(item.path).parent.parent) for item in skills})
        descriptor["status"] = "configured"
        return MacroEnvironment(
            environment_digest=resolved.environment_digest,
            dynamic_tools=tuple(descriptor["dynamic_tools"]),
            skills=skills,
            skill_roots=tuple(descriptor["skill_roots"]),
            descriptor=descriptor,
            status="configured",
            package_digest=resolved.package.content_digest if resolved.package is not None else None,
            resolved=resolved,
        )

@dataclass(slots=True)
class MacroTurnAdmission:
    admission_id: str
    thread_id: str
    session_id: str
    actor_identity: tuple[str, str, str, bool] | None
    environment: MacroEnvironment
    expires_at: datetime
    consumed_turn_id: str | None = None


class MacroTurnAttachment(TypedDict):
    kind: Literal["local_image"]
    attachmentId: str
    filename: str
    size: int
    sha256: str


@dataclass(slots=True)
class MacroHostBinding:
    binding_id: str
    project_key: str
    environment: MacroEnvironment
    package_id: str | None
    package_version: str | None
    prepared_at: datetime
    expires_at: datetime
    status: str = "prepared"
    thread_id: str | None = None
    session_id: str | None = None
    turn_contexts: dict[str, TrustedHostContext] = field(
        default_factory=lambda: dict[str, TrustedHostContext]()
    )
    turn_bindings: dict[str, MacroNativeBinding] = field(
        default_factory=lambda: dict[str, MacroNativeBinding]()
    )
    turn_environments: dict[str, MacroEnvironment] = field(
        default_factory=lambda: dict[str, MacroEnvironment]()
    )
    turn_admissions: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    admissions: dict[str, MacroTurnAdmission] = field(
        default_factory=lambda: dict[str, MacroTurnAdmission]()
    )
    dispatch_cache: dict[str, _DispatchCacheEntry] = field(
        default_factory=lambda: dict[str, _DispatchCacheEntry]()
    )
    ended_turns: set[str] = field(default_factory=lambda: set[str]())


@dataclass(slots=True)
class _BindingStoreState:
    bindings: dict[str, MacroHostBinding] = field(
        default_factory=lambda: dict[str, MacroHostBinding]()
    )
    threads: dict[str, str] = field(default_factory=lambda: dict[str, str]())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _actor_identity(actor: RequestActorContext | None) -> tuple[str, str, str, bool] | None:
    if actor is None:
        return None
    return actor.actor_id, actor.actor_source, actor.actor_auth_mode, actor.actor_trusted


_ATTACHMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ATTACHMENT_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ATTACHMENT_KEYS = frozenset({"kind", "attachmentId", "filename", "size", "sha256"})


def _turn_attachments(
    values: Sequence[Mapping[str, object]] | None,
) -> tuple[MacroTurnAttachment, ...]:
    if not values:
        return ()
    if len(values) > 8:
        raise MacroHostError("invalid_attachment", "at most 8 attachments are allowed")
    normalized: list[MacroTurnAttachment] = []
    seen: set[str] = set()
    for item in values:
        if set(item) != _ATTACHMENT_KEYS or item.get("kind") != "local_image":
            raise MacroHostError("invalid_attachment", "attachment metadata is invalid")
        attachment_id = str(item.get("attachmentId") or "").strip()
        filename = str(item.get("filename") or "").strip()
        size = item.get("size")
        digest = str(item.get("sha256") or "").strip().lower()
        if (
            not _ATTACHMENT_ID_RE.fullmatch(attachment_id)
            or attachment_id in seen
            or not filename
            or len(filename) > 255
            or "/" in filename
            or "\\" in filename
            or "\x00" in filename
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or not _ATTACHMENT_HASH_RE.fullmatch(digest)
        ):
            raise MacroHostError("invalid_attachment", "attachment metadata is invalid")
        seen.add(attachment_id)
        normalized.append(
            {
                "kind": "local_image",
                "attachmentId": attachment_id,
                "filename": filename,
                "size": size,
                "sha256": digest,
            }
        )
    return tuple(normalized)


def _required_str(value: object, *, label: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise MacroHostError("invalid_input", f"{label} is required")
    return result


def _system_instructions(environment: MacroEnvironment) -> str:
    # Fixture descriptors predate the snapshot field; production resolver always sets it.
    value = environment.descriptor.get("system_instructions")
    return str(value).strip() if isinstance(value, str) and value.strip() else SYSTEM_NAVIGATION_INSTRUCTIONS


class AgentMacroHostService:
    """Prepare real native threads and dispatch their tools through owned registries."""

    def __init__(
        self,
        *,
        project_checker: ProjectChecker,
        agent_session_service: AgentSessionService,
        environment_owner: MacroEnvironmentOwner | None = None,
        prepared_binding_ttl_seconds: int = 900,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.project_checker = project_checker
        self.agent_session_service = agent_session_service
        self.environment_owner = environment_owner or DefaultMacroEnvironmentOwner(
            service=agent_session_service,
            source_roots=(Path(__file__).resolve().parents[3] / "skills",),
        )
        self.prepared_binding_ttl_seconds = prepared_binding_ttl_seconds
        self.clock = clock
        self._state = _BindingStoreState()
        self._lock = threading.RLock()
        self._input_lock = threading.RLock()
        self._call_locks: dict[str, threading.Lock] = {}

    def prepare(
        self,
        *,
        project_key: str,
        package_id: str | None = None,
        package_version: str | None = None,
    ) -> dict[str, Any]:
        project = _required_str(project_key, label="projectKey")
        if bool(package_id) != bool(package_version):
            raise MacroHostError("invalid_input", "packageId and packageVersion must be supplied together")
        if not self.project_checker(project):
            raise MacroHostError("project_not_found", "selected project is not available", status_code=404)
        binding_id = f"mrw-host-{uuid4().hex}"
        environment = self._resolve_environment(
            project_key=project,
            binding_id=binding_id,
            phase="prepare",
            package_id=package_id,
            package_version=package_version,
        )
        self._validate_environment(environment)
        now = self.clock()
        binding = MacroHostBinding(
            binding_id=binding_id,
            project_key=project,
            environment=environment,
            package_id=package_id,
            package_version=package_version,
            prepared_at=now,
            expires_at=now + timedelta(seconds=self.prepared_binding_ttl_seconds),
        )
        with self._lock:
            self._state.bindings[binding_id] = binding
        return self._binding_projection(binding)

    def bind(self, *, binding_id: str, thread_id: str) -> dict[str, Any]:
        binding = self._prepared_binding(_required_str(binding_id, label="bindingId"))
        native_thread_id = _required_str(thread_id, label="threadId")
        with self._lock:
            existing = self._state.threads.get(native_thread_id)
        if existing and existing != binding.binding_id:
            raise MacroHostError("thread_already_bound", "native thread is already bound", status_code=409)
        current = self._resolve_environment(
            project_key=binding.project_key,
            binding_id=binding.binding_id,
            phase="bind",
            package_id=binding.package_id,
            package_version=binding.package_version,
        )
        self._validate_environment(current)
        if current.environment_digest != binding.environment.environment_digest:
            binding.status = "environment_stale"
            raise MacroHostError("environment_stale", "macro environment changed before native thread binding", status_code=409)
        session = self.agent_session_service.create_session(
            source="codex_webui_host",
            project_key=binding.project_key,
            entrypoint_type="codex_native_thread",
            goal=f"Codex WebUI native macro host thread {native_thread_id}",
            metadata={
                "binding_id": binding.binding_id,
                "native_thread_id": native_thread_id,
                "environment_digest": current.environment_digest,
                "environment_status": current.status,
            },
        )
        if isinstance(session, Failure):
            raise MacroHostError("agent_session_unavailable", session.message, status_code=503)
        embedded_session = session.get("session")
        session_record = embedded_session if _is_string_mapping(embedded_session) else session
        session_value = session_record.get("session_id")
        session_id = _required_str(session_value, label="agent sessionId")
        now = self.clock()
        with self._lock:
            if binding.status != "prepared" or binding.expires_at < now:
                raise MacroHostError("binding_expired", "prepared macro binding expired", status_code=409)
            binding.environment = current
            binding.thread_id = native_thread_id
            binding.session_id = session_id
            binding.status = "bound"
            binding.expires_at = now + timedelta(days=1)
            self._state.threads[native_thread_id] = binding.binding_id
        return self._binding_projection(binding)

    def environment(self, *, binding_id: str | None = None, thread_id: str | None = None) -> dict[str, Any]:
        binding = self._binding(binding_id=binding_id, thread_id=thread_id)
        current_digest: str | None = None
        if binding.status == "bound":
            current = self._resolve_environment(
                project_key=binding.project_key,
                binding_id=binding.binding_id,
                phase="read",
                package_id=binding.package_id,
                package_version=binding.package_version,
            )
            current_digest = current.environment_digest
        return {
            **self._binding_projection(binding),
            "environmentChanged": current_digest is not None and current_digest != binding.environment.environment_digest,
            "currentEnvironmentDigest": current_digest,
            "environmentStale": binding.status == "environment_stale",
        }

    def prepare_turn(
        self, *, thread_id: str, actor_context: RequestActorContext | None = None,
    ) -> dict[str, Any]:
        if actor_context is not None and (not actor_context.actor_trusted or not actor_context.actor_id):
            raise MacroHostError("host_actor_untrusted", "host actor is not authenticated", status_code=403)
        binding = self._bound_binding(thread_id)
        environment = self._resolve_environment(
            project_key=binding.project_key,
            binding_id=binding.binding_id,
            phase="prepare_turn",
            package_id=binding.package_id,
            package_version=binding.package_version,
        )
        self._validate_environment(environment)
        now = self.clock()
        admission = MacroTurnAdmission(
            admission_id=f"mrw-turn-{uuid4().hex}",
            thread_id=binding.thread_id or thread_id,
            session_id=binding.session_id or "",
            actor_identity=_actor_identity(actor_context),
            environment=environment,
            expires_at=now + timedelta(seconds=self.prepared_binding_ttl_seconds),
        )
        with self._lock:
            if binding.status != "bound":
                raise MacroHostError("thread_not_bound", "native thread is not bound", status_code=404)
            for old_id, old in tuple(binding.admissions.items()):
                if old.consumed_turn_id is None and old.expires_at < now:
                    del binding.admissions[old_id]
            binding.admissions[admission.admission_id] = admission
        return {
            "admissionId": admission.admission_id,
            "threadId": admission.thread_id,
            "environmentDigest": environment.environment_digest,
            "environmentStatus": environment.status,
            "dynamicTools": [dict(item) for item in environment.dynamic_tools],
            "skills": self._skill_projection(environment.skills),
            "skillRoots": list(environment.skill_roots),
            "systemInstructions": _system_instructions(environment),
            "expiresAt": admission.expires_at.isoformat(),
        }

    def record_input(
        self, *, thread_id: str, content: str, turn_id: str,
        admission_id: str,
        attachments: Sequence[Mapping[str, object]] | None = None,
        actor_context: RequestActorContext | None = None,
    ) -> dict[str, Any]:
        with self._input_lock:
            return self._record_input(
                thread_id=thread_id, content=content, turn_id=turn_id,
                admission_id=admission_id, attachments=attachments,
                actor_context=actor_context,
            )

    def _record_input(
        self, *, thread_id: str, content: str, turn_id: str,
        admission_id: str,
        attachments: Sequence[Mapping[str, object]] | None = None,
        actor_context: RequestActorContext | None = None,
    ) -> dict[str, Any]:
        if actor_context is not None and (not actor_context.actor_trusted or not actor_context.actor_id):
            raise MacroHostError("host_actor_untrusted", "host actor is not authenticated", status_code=403)
        binding = self._bound_binding(thread_id)
        normalized_turn = _required_str(turn_id, label="turnId")
        normalized_admission = _required_str(admission_id, label="admissionId")
        normalized_content = str(content or "").strip()
        normalized_attachments = _turn_attachments(attachments)
        if not normalized_content and not normalized_attachments:
            raise MacroHostError("invalid_input", "user text or an attachment is required")
        message_content = normalized_content or f"附件 ×{len(normalized_attachments)}"
        with self._lock:
            if normalized_turn in binding.ended_turns:
                raise MacroHostError("turn_ended", "host input turn has ended", status_code=409)
            prior = binding.turn_contexts.get(normalized_turn)
            if prior is not None and _actor_identity(prior.actor_context) != _actor_identity(actor_context):
                raise MacroHostError("host_actor_mismatch", "recorded turn belongs to another authenticated actor", status_code=403)
            admission = binding.admissions.get(normalized_admission)
            if admission is None:
                raise MacroHostError("admission_not_found", "turn admission was not found", status_code=404)
            if (admission.thread_id != binding.thread_id or admission.session_id != binding.session_id
                    or admission.actor_identity != _actor_identity(actor_context)):
                raise MacroHostError("admission_mismatch", "turn admission does not match this host context", status_code=409)
            if prior is None:
                if admission.consumed_turn_id is not None:
                    raise MacroHostError("admission_consumed", "turn admission was already used", status_code=409)
                if admission.expires_at < self.clock():
                    raise MacroHostError("admission_expired", "turn admission expired", status_code=409)
                admission.consumed_turn_id = normalized_turn
                environment = admission.environment
            else:
                if binding.turn_admissions.get(normalized_turn) != normalized_admission:
                    raise MacroHostError("admission_mismatch", "turn admission differs from recorded turn", status_code=409)
                environment = binding.turn_environments[normalized_turn]
        context = TrustedHostContext(
            project_key=binding.project_key,
            session_id=binding.session_id or "",
            host_thread_id=binding.thread_id or thread_id,
            turn_id=normalized_turn,
            user_message_id=f"host-message-{uuid4().hex}",
            actor_context=actor_context,
        )
        try:
            turn_binding = self._assemble_turn(environment, context) if prior is None else None
            message = self.agent_session_service.create_host_user_message(
                context,
                content=message_content,
                attachments=list(normalized_attachments) or None,
            )
            if isinstance(message, Failure):
                raise MacroHostError("host_input_rejected", message.message, status_code=403)
        except Exception:
            if prior is None:
                with self._lock:
                    if normalized_turn not in binding.turn_contexts:
                        admission.consumed_turn_id = None
            raise
        with self._lock:
            if prior is None:
                binding.turn_environments[normalized_turn] = environment
                binding.turn_admissions[normalized_turn] = normalized_admission
                assert turn_binding is not None
                binding.turn_bindings[normalized_turn] = turn_binding
            binding.turn_contexts[normalized_turn] = context
        message_id = message.get("message_id")
        return {
            "recorded": True,
            "role": "user",
            "messageId": message_id,
            "turnId": normalized_turn,
            "attachments": list(normalized_attachments),
            "sessionId": binding.session_id,
            "environmentStatus": environment.status,
            "environmentDigest": environment.environment_digest,
        }

    def confirm(
        self,
        *,
        thread_id: str,
        turn_id: str,
        action_id: str,
        approved: bool,
        user_text: str | None = None,
    ) -> dict[str, Any]:
        binding = self._bound_binding(thread_id)
        normalized_turn = _required_str(turn_id, label="turnId")
        normalized_action = _required_str(action_id, label="actionId")
        with self._lock:
            if normalized_turn in binding.ended_turns:
                raise MacroHostError("turn_ended", "host confirmation turn has ended", status_code=409)
            context = binding.turn_contexts.get(normalized_turn)
        if context is None:
            raise MacroHostError("host_turn_context_required", "host confirmation turn context is required", status_code=409)
        decision = "approve" if approved else "reject"
        supplied = str(user_text or "").strip()
        content = f"approval:{normalized_action} {decision} {supplied}".strip()
        outcome = self.agent_session_service.record_host_tool_confirmation(
            context,
            approval_id=normalized_action,
            content=content,
            approved=approved,
        )
        if isinstance(outcome, Failure):
            raise MacroHostError("host_confirmation_rejected", outcome.message, status_code=403)
        message_id = outcome.get("message_id")
        return {
            "confirmed": True,
            "actionId": normalized_action,
            "approved": approved,
            "turnId": normalized_turn,
            "messageId": message_id,
        }

    def end_turn(self, *, thread_id: str, turn_id: str) -> dict[str, Any]:
        with self._input_lock:
            binding = self._bound_binding(thread_id)
            normalized_turn = _required_str(turn_id, label="turnId")
            with self._lock:
                binding.ended_turns.add(normalized_turn)
                binding.turn_contexts.pop(normalized_turn, None)
                binding.turn_bindings.pop(normalized_turn, None)
                binding.turn_environments.pop(normalized_turn, None)
                admission_id = binding.turn_admissions.pop(normalized_turn, None)
                if admission_id is not None:
                    binding.admissions.pop(admission_id, None)
        return {
            "ended": True,
            "threadId": binding.thread_id,
            "turnId": normalized_turn,
        }

    def dispatch(
        self,
        *,
        thread_id: str,
        turn_id: str,
        call_id: str,
        namespace: str | None,
        tool: str,
        arguments: Mapping[str, object],
        actor_context: RequestActorContext | None = None,
    ) -> dict[str, Any]:
        normalized_thread = _required_str(thread_id, label="threadId")
        normalized_turn = _required_str(turn_id, label="turnId")
        normalized_call = _required_str(call_id, label="callId")
        tool_name = _required_str(tool, label="tool")
        binding = self._binding(thread_id=normalized_thread)
        if binding.status != "bound":
            return self._tool_failure("dynamic tool call rejected: native thread is not bound")
        with self._lock:
            if normalized_turn in binding.ended_turns:
                return self._tool_failure("dynamic tool call rejected: turn ended")
            context = binding.turn_contexts.get(normalized_turn)
            native = binding.turn_bindings.get(normalized_turn)
            turn_environment = binding.turn_environments.get(normalized_turn)
        if context is None or native is None or turn_environment is None:
            return self._tool_failure("dynamic tool call rejected: trusted host input is not recorded for this turn")
        if _actor_identity(context.actor_context) != _actor_identity(actor_context):
            return self._tool_failure("dynamic tool call rejected: authenticated host actor differs from recorded input")
        logical_name = native.logical_tool_name(namespace=namespace, name=tool_name)
        if logical_name is None or native.registry.get(logical_name) is None:
            return self._tool_failure(f"unknown mounted macro tool: {namespace + '.' if namespace else ''}{tool_name}")
        digest = canonical_arguments_sha256(arguments)
        if isinstance(digest, Failure):
            return self._tool_failure(f"dynamic tool arguments rejected: {digest.message}")
        cache_key = f"{normalized_thread}:{normalized_turn}:{normalized_call}"
        with self._lock:
            if normalized_turn in binding.ended_turns:
                return self._tool_failure("dynamic tool call rejected: turn ended")
            cached = binding.dispatch_cache.get(cache_key)
            if cached is not None:
                if cached["tool"] != logical_name or cached["args_digest"] != digest:
                    return self._tool_failure(
                        "dynamic tool call arguments changed for the same call"
                    )
                return cached["response"]
            call_lock = self._call_locks.setdefault(cache_key, threading.Lock())

        with call_lock:
            with self._lock:
                if normalized_turn in binding.ended_turns:
                    return self._tool_failure("dynamic tool call rejected: turn ended")
                cached = binding.dispatch_cache.get(cache_key)
                if cached is not None:
                    if cached["tool"] != logical_name or cached["args_digest"] != digest:
                        return self._tool_failure(
                            "dynamic tool call arguments changed for the same call"
                        )
                    return cached["response"]

            tool_call = CoreToolCall(
                tool_name=logical_name,
                arguments=json_object(arguments),
                call_id=normalized_call,
                reason="codex_webui_macro_host",
            )
            resolved_env = turn_environment.resolved
            if resolved_env is not None:
                package_digest = resolve_tool_package_digest(
                    resolved_env,
                    context,
                    self.agent_session_service,
                    tool_call,
                )
                if isinstance(package_digest, Failure):
                    return self._tool_failure(
                        f"dynamic tool package digest rejected: {package_digest.message}"
                    )
            else:
                package_digest = turn_environment.package_digest
            with self._lock:
                if normalized_turn in binding.ended_turns:
                    return self._tool_failure("dynamic tool call rejected: turn ended")
            result = native.registry.execute_tool(
                tool_call=tool_call,
                request=AgentCoreRequest(
                    message="Codex WebUI native macro host tool call",
                    session_id=binding.session_id or "",
                    project_key=binding.project_key,
                    turn_id=normalized_turn,
                    context={
                        "runtime_variant": "agent_macro_webui_host",
                        "binding_id": binding.binding_id,
                        "environment_status": turn_environment.status,
                    },
                ),
                emit=_ignore_core_event,
                trusted_context=context,
                authorization_service=self.agent_session_service,
                package_digest=package_digest,
            )
            projection = result.to_dict()
            structured_value = projection.get("structured_content")
            structured = json_object(structured_value)
            status = str(projection.get("status") or "")
            self._record_dispatch_event(
                binding=binding,
                turn_id=normalized_turn,
                call_id=normalized_call,
                logical_name=logical_name,
                arguments_digest=digest,
                status=status,
                structured=structured,
                environment=turn_environment,
                package_digest=package_digest,
            )
            pending_action = None
            if status == "needs_approval":
                pending_action = {
                    "actionId": str(structured.get("approval_id") or ""),
                    "actionDigest": digest,
                    "toolName": logical_name,
                    "arguments": dict(arguments),
                    "projectKey": binding.project_key,
                    "threadId": normalized_thread,
                    "turnId": normalized_turn,
                }
            response: dict[str, object] = {
                "success": status == "completed",
                "resultProjection": projection,
                "pendingAction": pending_action,
                "contentItems": [
                    {"type": "inputText", "text": _stable_json(projection)}
                ],
            }
            if status != "needs_approval":
                with self._lock:
                    binding.dispatch_cache[cache_key] = {
                        "tool": logical_name,
                        "args_digest": digest,
                        "response": response,
                    }
            return response

    def _record_dispatch_event(
        self,
        *,
        binding: MacroHostBinding,
        turn_id: str,
        call_id: str,
        logical_name: str,
        arguments_digest: str,
        status: str,
        structured: Mapping[str, object],
        environment: MacroEnvironment,
        package_digest: str | None,
    ) -> None:
        if not binding.session_id:
            return
        try:
            self.agent_session_service.store.append_event(
                binding.session_id,
                event_type="macro_host.tool.dispatched",
                payload=json_object({
                    "project_key": binding.project_key,
                    "session_id": binding.session_id,
                    "thread_id": binding.thread_id,
                    "turn_id": turn_id,
                    "call_id": call_id,
                    "tool": logical_name,
                    "arguments_digest": arguments_digest,
                    "package_digest": package_digest,
                    "environment_digest": environment.environment_digest,
                    "status": status,
                    "structured_content": dict(structured or {}),
                }),
            )
        except Exception:
            # Event persistence is best-effort; the dispatch result remains authoritative.
            return

    def _resolve_environment(
        self,
        *,
        project_key: str,
        binding_id: str,
        phase: str,
        package_id: str | None,
        package_version: str | None,
    ) -> MacroEnvironment:
        try:
            raw = self.environment_owner.resolve(
                project_key=project_key,
                binding_id=binding_id,
                phase=phase,
                package_id=package_id,
                package_version=package_version,
            )
        except MacroHostError:
            raise
        except Exception as exc:
            raise MacroHostError("macro_environment_unavailable", str(exc), status_code=503) from exc
        return raw if isinstance(raw, MacroEnvironment) else self._read_environment(raw)

    def _assemble_turn(self, environment: MacroEnvironment, context: TrustedHostContext) -> MacroNativeBinding:
        try:
            native = self.environment_owner.assemble(environment, context)
        except MacroHostError:
            raise
        except Exception as exc:
            raise MacroHostError("macro_environment_unavailable", str(exc), status_code=503) from exc
        if not isinstance(native, MacroNativeBinding):
            raise MacroHostError("macro_environment_invalid", "native macro binding has no trusted registry dispatch", status_code=503)
        return native

    @staticmethod
    def _read_environment(raw: object) -> MacroEnvironment:
        if not _is_string_mapping(raw):
            raise MacroHostError("macro_environment_unavailable", "macro environment owner is unavailable", status_code=503)
        tools_value = raw.get("dynamic_tools") or raw.get("dynamicTools")
        raw_skills_value = raw.get("skills")
        if raw_skills_value is None:
            raw_skills_value = list[object]()
        roots_value = raw.get("skill_roots") or raw.get("skillRoots")
        if not _is_object_sequence(tools_value) or not _is_object_sequence(raw_skills_value):
            raise MacroHostError("macro_environment_invalid", "macro environment descriptor is invalid")
        tools = tuple(
            item
            for item in tools_value
            if _is_string_mapping(item)
        )
        if len(tools) != len(tools_value):
            raise MacroHostError("macro_environment_invalid", "macro dynamic tool descriptor is invalid")
        skills_raw = tuple(item for item in raw_skills_value if _is_string_mapping(item))
        if len(skills_raw) != len(raw_skills_value):
            raise MacroHostError("macro_environment_invalid", "macro skill descriptor is invalid")
        skills = tuple(
            MacroSkillDescriptor(
                _required_str(skill.get("name"), label="skill name"),
                _required_str(skill.get("path"), label="skill path"),
                _required_str(skill.get("content_digest") or skill.get("contentDigest"), label="skill digest"),
                str(skill.get("source_root") or skill.get("sourceRoot") or "").strip() or None,
                str(skill.get("relative_path") or skill.get("relativePath") or "").strip() or None,
            )
            for skill in skills_raw
        )
        if roots_value is None:
            roots = sorted({str(Path(item.path).parent.parent) for item in skills})
        elif _is_string_sequence(roots_value):
            roots = roots_value
        else:
            raise MacroHostError("macro_environment_invalid", "macro skill roots descriptor is invalid")
        return MacroEnvironment(
            environment_digest=_required_str(raw.get("environment_digest") or raw.get("environmentDigest"), label="environment digest"),
            dynamic_tools=tools,
            skills=skills,
            skill_roots=tuple(sorted(set(roots))),
            descriptor=raw,
            status=str(raw.get("status") or "configured"),
            package_digest=str(raw.get("package_digest") or raw.get("packageDigest") or "").strip() or None,
        )

    @staticmethod
    def _validate_environment(environment: MacroEnvironment) -> None:
        for skill in environment.skills:
            if not Path(skill.path).expanduser().is_file():
                raise MacroHostError("skill_mount_unavailable", f"mounted skill is missing: {skill.name}", status_code=409)

    def _prepared_binding(self, binding_id: str) -> MacroHostBinding:
        binding = self._binding(binding_id=binding_id)
        now = self.clock()
        if binding.status != "prepared" or binding.expires_at < now:
            binding.status = "binding_expired" if binding.status == "prepared" else binding.status
            raise MacroHostError("binding_expired", "prepared macro binding expired", status_code=409)
        return binding

    def _bound_binding(self, thread_id: str) -> MacroHostBinding:
        binding = self._binding(thread_id=_required_str(thread_id, label="threadId"))
        if binding.status != "bound":
            raise MacroHostError("thread_not_bound", "native thread is not bound", status_code=404)
        return binding

    def _binding(self, *, binding_id: str | None = None, thread_id: str | None = None) -> MacroHostBinding:
        normalized_thread = _required_str(thread_id, label="threadId") if thread_id else None
        with self._lock:
            if binding_id:
                binding = self._state.bindings.get(_required_str(binding_id, label="bindingId"))
            elif normalized_thread:
                owner = self._state.threads.get(normalized_thread)
                binding = self._state.bindings.get(owner or "")
            else:
                raise MacroHostError("invalid_input", "bindingId or threadId is required")
        if binding is None:
            if normalized_thread:
                found = self.agent_session_service.store.find_session_by_native_thread_id(normalized_thread)
                if isinstance(found, Failure) or found is not None:
                    raise MacroHostError(
                        "rebind_required",
                        "macro host binding was lost; rebind required",
                        status_code=409,
                    )
            raise MacroHostError("binding_not_found", "macro host binding not found", status_code=404)
        return binding

    def _binding_projection(self, binding: MacroHostBinding) -> dict[str, Any]:
        return {
            "bindingId": binding.binding_id,
            "projectKey": binding.project_key,
            "packageId": binding.package_id,
            "packageVersion": binding.package_version,
            "sessionId": binding.session_id,
            "threadId": binding.thread_id,
            "status": binding.status,
            "environmentStatus": binding.environment.status,
            "environmentDigest": binding.environment.environment_digest,
            "dynamicTools": [dict(item) for item in binding.environment.dynamic_tools],
            "skills": self._skill_projection(binding.environment.skills),
            "skillRoots": list(binding.environment.skill_roots),
            "systemInstructions": _system_instructions(binding.environment),
            "preparedAt": binding.prepared_at.isoformat(),
            "expiresAt": binding.expires_at.isoformat(),
        }

    @staticmethod
    def _skill_projection(skills: Sequence[MacroSkillDescriptor]) -> list[dict[str, object]]:
        return [
            {
                "name": item.name,
                "path": item.path,
                "contentDigest": item.content_digest,
                "sourceRoot": item.source_root,
                "relativePath": item.relative_path,
            }
            for item in skills
        ]

    @staticmethod
    def _tool_failure(message: str) -> dict[str, Any]:
        return {"success": False, "contentItems": [{"type": "inputText", "text": message}]}


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
