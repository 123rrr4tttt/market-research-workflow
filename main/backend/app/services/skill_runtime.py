from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from importlib import import_module
from threading import RLock
from typing import Any, Callable, Mapping

from app.services.agent_sessions import get_agent_session_service
from app.settings.config import settings
from app.services.agent_batch.task_contract import build_agent_batch_manifest_entry, list_agent_batch_dispatch_skill_bindings


SkillHandler = Callable[..., Any]
_ALLOWED_ACTOR_ROLES = frozenset({"orchestration_runtime", "business_capability_wrapper", "user_facing_assistant"})
_ALLOWED_CONCURRENCY_CLASSES = frozenset({"read_only", "write_shared", "write_external", "privileged"})


@dataclass(frozen=True)
class SkillSpec:
    skill_id: str
    handler: SkillHandler
    allowed_actor_roles: tuple[str, ...]
    required_permissions: tuple[str, ...]
    owner: str
    execution_profile: str = "default"
    concurrency_class: str = "read_only"
    approval_policy: dict[str, Any] | None = None
    artifact_contract: dict[str, Any] | None = None
    agent_batch_task_manifest: dict[str, Any] | None = None


class SkillRuntime:
    def __init__(self) -> None:
        self._lock = RLock()
        self._registry: dict[str, SkillSpec] = {}
        self._bootstrapped = False

    def list_skills(self) -> list[dict[str, Any]]:
        self._bootstrap()
        with self._lock:
            return [
                {
                    "skill_id": item.skill_id,
                    "allowed_actor_roles": list(item.allowed_actor_roles),
                    "required_permissions": list(item.required_permissions),
                    "owner": item.owner,
                    "execution_profile": item.execution_profile,
                    "concurrency_class": item.concurrency_class,
                    "approval_policy": dict(item.approval_policy or {}),
                    "artifact_contract": dict(item.artifact_contract or {}),
                    "agent_batch_task_manifest": dict(item.agent_batch_task_manifest or {}),
                }
                for item in sorted(self._registry.values(), key=lambda x: x.skill_id)
            ]

    def list_agent_batch_task_manifest_entries(self) -> list[dict[str, Any]]:
        self._bootstrap()
        with self._lock:
            out: list[dict[str, Any]] = []
            for item in self._registry.values():
                entry = item.agent_batch_task_manifest
                if isinstance(entry, dict) and entry:
                    out.append(dict(entry))
            return out

    def register(
        self,
        *,
        skill_id: str,
        handler: SkillHandler,
        allowed_actor_roles: tuple[str, ...] = ("orchestration_runtime",),
        required_permissions: tuple[str, ...] = (),
        owner: str = "unknown",
        execution_profile: str = "default",
        concurrency_class: str = "read_only",
        approval_policy: Mapping[str, Any] | None = None,
        artifact_contract: Mapping[str, Any] | None = None,
        agent_batch_task_manifest: Mapping[str, Any] | None = None,
    ) -> None:
        resolved_skill_id = str(skill_id or "").strip()
        if not resolved_skill_id:
            raise ValueError("skill_id is required")
        if not callable(handler):
            raise ValueError("handler must be callable")

        normalized_roles = tuple(_normalize_actor_roles(allowed_actor_roles))
        normalized_permissions = tuple(_normalize_permissions(required_permissions))

        spec = SkillSpec(
            skill_id=resolved_skill_id,
            handler=handler,
            allowed_actor_roles=normalized_roles,
            required_permissions=normalized_permissions,
            owner=str(owner or "unknown").strip() or "unknown",
            execution_profile=str(execution_profile or "default").strip() or "default",
            concurrency_class=_normalize_concurrency_class(concurrency_class),
            approval_policy=_normalize_contract_dict(approval_policy),
            artifact_contract=_normalize_contract_dict(artifact_contract),
            agent_batch_task_manifest=_normalize_agent_batch_task_manifest(agent_batch_task_manifest),
        )
        with self._lock:
            self._registry[resolved_skill_id] = spec

    def invoke(
        self,
        *,
        skill_id: str,
        payload: Any = None,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._bootstrap()
        resolved_skill_id = str(skill_id or "").strip()
        if not resolved_skill_id:
            raise ValueError("skill_id is required")

        with self._lock:
            spec = self._registry.get(resolved_skill_id)
        if spec is None:
            raise KeyError(f"unknown skill: {resolved_skill_id}")

        loop_guard_reason = _detect_skill_loop_guard(
            skill_id=resolved_skill_id,
            payload=payload,
            args=args,
            kwargs=kwargs,
            context=context,
        )
        if loop_guard_reason:
            raise RuntimeError(loop_guard_reason)

        actor_role = _resolve_actor_role(context)
        requested_permissions = _resolve_requested_permissions(context, spec.required_permissions)
        missing_permissions = [p for p in spec.required_permissions if p not in requested_permissions]
        denied_reasons: list[str] = []
        if actor_role not in spec.allowed_actor_roles:
            denied_reasons.append("actor_role_not_allowed")
        if missing_permissions:
            denied_reasons.append("missing_required_permissions")
        if denied_reasons:
            raise PermissionError(
                f"skill invoke denied: {resolved_skill_id} ({','.join(denied_reasons)})"
            )

        approval_request = _enforce_runtime_policies(
            spec=spec,
            skill_id=resolved_skill_id,
            payload=payload,
            args=args,
            kwargs=kwargs,
            context=context,
        )

        if args is None and kwargs is None:
            result = spec.handler(payload)
        else:
            result = spec.handler(*(args or ()), **(kwargs or {}))

        trace_id = str((context or {}).get("trace_id") or "").strip() or f"skill-{resolved_skill_id}"
        consumer = str((context or {}).get("consumer") or "skill_runtime").strip() or "skill_runtime"

        return {
            "skill_id": resolved_skill_id,
            "result": result,
            "trace_id": trace_id,
            "consumer": consumer,
            "actor_role": actor_role,
            "requested_permissions": requested_permissions,
            "owner": spec.owner,
            "execution_profile": spec.execution_profile,
            "concurrency_class": spec.concurrency_class,
            "approval_policy": dict(spec.approval_policy or {}),
            "artifact_contract": dict(spec.artifact_contract or {}),
            "approval_request": approval_request,
        }

    def _bootstrap(self) -> None:
        with self._lock:
            if self._bootstrapped:
                return
            self._bootstrapped = True

        module = import_module("app.services.workflow_graph")
        compiler = getattr(module, "compiler", None)
        runtime = getattr(module, "runtime", None)
        curated = getattr(module, "curated", None)
        if compiler is None or runtime is None or curated is None:
            raise RuntimeError("workflow_graph services unavailable for skill bootstrap")
        workflow_llm_module = import_module("app.services.workflow_graph.executors.llm_call")
        workflow_llm_handler = getattr(workflow_llm_module, "invoke_workflow_llm_call_skill", None)
        if workflow_llm_handler is None:
            raise RuntimeError("workflow llm_call executor unavailable for skill bootstrap")
        ingest_api_module = import_module("app.api.ingest")
        ingest_dispatch_market = getattr(ingest_api_module, "_skill_dispatch_ingest_market_collect", None)
        ingest_dispatch_source = getattr(ingest_api_module, "_skill_dispatch_ingest_source_library_item", None)
        if ingest_dispatch_market is None or ingest_dispatch_source is None:
            raise RuntimeError("ingest dispatch skills unavailable for skill bootstrap")
        agent_batch_api_module = import_module("app.api.agent_batch")
        dispatch_bindings = list_agent_batch_dispatch_skill_bindings()
        if not dispatch_bindings:
            raise RuntimeError("agent batch dispatch skill bindings unavailable for skill bootstrap")

        self.register(
            skill_id="workflow_graph.compile",
            handler=compiler.compile,
            required_permissions=("workflow_graph.compile",),
            owner="workflow_graph.compiler",
        )
        self.register(
            skill_id="workflow_graph.run",
            handler=runtime.run,
            required_permissions=("workflow_graph.run",),
            owner="workflow_graph.runtime",
            concurrency_class="write_shared",
        )
        self.register(
            skill_id="workflow_graph.get_run",
            handler=runtime.get_run,
            allowed_actor_roles=("orchestration_runtime", "business_capability_wrapper", "user_facing_assistant"),
            required_permissions=("workflow_graph.read",),
            owner="workflow_graph.runtime",
        )
        self.register(
            skill_id="workflow_graph.get_run_events",
            handler=runtime.get_run_events,
            allowed_actor_roles=("orchestration_runtime", "business_capability_wrapper", "user_facing_assistant"),
            required_permissions=("workflow_graph.read",),
            owner="workflow_graph.runtime",
        )
        self.register(
            skill_id="workflow_graph.get_run_agent_session",
            handler=runtime.get_run_agent_session,
            allowed_actor_roles=("orchestration_runtime", "business_capability_wrapper", "user_facing_assistant"),
            required_permissions=("workflow_graph.read",),
            owner="workflow_graph.runtime",
        )
        self.register(
            skill_id="workflow_graph.replay_run",
            handler=runtime.replay_run,
            allowed_actor_roles=("orchestration_runtime", "business_capability_wrapper", "user_facing_assistant"),
            required_permissions=("workflow_graph.read",),
            owner="workflow_graph.runtime",
        )
        self.register(
            skill_id="workflow_graph.get_compiled",
            handler=compiler.get_compiled,
            allowed_actor_roles=("orchestration_runtime", "business_capability_wrapper", "user_facing_assistant"),
            required_permissions=("workflow_graph.read",),
            owner="workflow_graph.compiler",
        )
        self.register(
            skill_id="workflow_graph.template.list",
            handler=compiler.list_templates,
            required_permissions=("workflow_graph.template",),
            owner="workflow_graph.compiler",
        )
        self.register(
            skill_id="workflow_graph.template.create",
            handler=compiler.create_template,
            required_permissions=("workflow_graph.template",),
            owner="workflow_graph.compiler",
        )
        self.register(
            skill_id="workflow_graph.template.get",
            handler=compiler.get_template,
            required_permissions=("workflow_graph.template",),
            owner="workflow_graph.compiler",
        )
        self.register(
            skill_id="workflow_graph.template.patch",
            handler=compiler.patch_template,
            required_permissions=("workflow_graph.template",),
            owner="workflow_graph.compiler",
        )
        self.register(
            skill_id="workflow_graph.template.delete",
            handler=compiler.delete_template,
            required_permissions=("workflow_graph.template",),
            owner="workflow_graph.compiler",
        )
        self.register(
            skill_id="workflow_graph.template.version.list",
            handler=compiler.list_template_versions,
            required_permissions=("workflow_graph.template",),
            owner="workflow_graph.compiler",
        )
        self.register(
            skill_id="workflow_graph.template.version.create",
            handler=compiler.create_template_version,
            required_permissions=("workflow_graph.template",),
            owner="workflow_graph.compiler",
        )
        self.register(
            skill_id="workflow_graph.template.version.get",
            handler=compiler.get_template_version,
            required_permissions=("workflow_graph.template",),
            owner="workflow_graph.compiler",
        )
        self.register(
            skill_id="workflow_graph.template.version.activate",
            handler=compiler.activate_template_version,
            required_permissions=("workflow_graph.template",),
            owner="workflow_graph.compiler",
        )
        self.register(
            skill_id="workflow_graph.curated.get",
            handler=curated.get_graph,
            required_permissions=("workflow_graph.curated",),
            owner="workflow_graph.curated",
        )
        self.register(
            skill_id="workflow_graph.curated.save_draft",
            handler=curated.save_draft,
            required_permissions=("workflow_graph.curated",),
            owner="workflow_graph.curated",
            concurrency_class="write_shared",
        )
        self.register(
            skill_id="workflow_graph.curated.submit",
            handler=curated.submit_draft,
            required_permissions=("workflow_graph.curated",),
            owner="workflow_graph.curated",
            concurrency_class="write_shared",
        )
        self.register(
            skill_id="workflow_graph.curated.sync",
            handler=curated.sync_graph,
            required_permissions=("workflow_graph.curated",),
            owner="workflow_graph.curated",
            concurrency_class="write_shared",
        )
        self.register(
            skill_id="workflow_graph.curated.rollback",
            handler=curated.rollback,
            required_permissions=("workflow_graph.curated",),
            owner="workflow_graph.curated",
            concurrency_class="write_shared",
        )
        self.register(
            skill_id="workflow_graph.curated.list_audits",
            handler=curated.list_audits,
            required_permissions=("workflow_graph.curated",),
            owner="workflow_graph.curated",
        )
        self.register(
            skill_id="workflow.llm_call",
            handler=workflow_llm_handler,
            required_permissions=("workflow.llm_call",),
            owner="workflow_graph.executor.llm_call",
        )
        self.register(
            skill_id="workflow_graph.curated.evidence_pack",
            handler=curated.build_evidence_pack,
            required_permissions=("workflow_graph.curated",),
            owner="workflow_graph.curated",
        )
        self.register(
            skill_id="workflow_graph.curated.handoff.reporting",
            handler=curated.build_reporting_handoff,
            required_permissions=("workflow_graph.handoff",),
            owner="workflow_graph.curated",
        )
        self.register(
            skill_id="workflow_graph.curated.handoff.writing",
            handler=curated.build_writing_handoff,
            required_permissions=("workflow_graph.handoff",),
            owner="workflow_graph.curated",
        )
        self.register(
            skill_id="ingest.dispatch.source_library_item",
            handler=ingest_dispatch_source,
            allowed_actor_roles=("orchestration_runtime", "business_capability_wrapper", "user_facing_assistant"),
            required_permissions=("ingest.dispatch.source_library_item",),
            owner="ingest.api.dispatch",
            concurrency_class="write_shared",
            approval_policy={"default": "optional"},
        )
        self.register(
            skill_id="ingest.dispatch.market_collect",
            handler=ingest_dispatch_market,
            allowed_actor_roles=("orchestration_runtime", "business_capability_wrapper", "user_facing_assistant"),
            required_permissions=("ingest.dispatch.market_collect",),
            owner="ingest.api.dispatch",
            concurrency_class="write_shared",
            approval_policy={"default": "optional"},
        )
        for binding in dispatch_bindings:
            channel = str(binding.get("channel") or "").strip().lower()
            skill_id = str(binding.get("skill_id") or "").strip()
            required_permission = str(binding.get("required_permission") or "").strip()
            handler_export = str(binding.get("handler_export") or "").strip()
            if not channel or not skill_id or not required_permission or not handler_export:
                raise RuntimeError("agent batch dispatch skill binding is incomplete")
            handler = getattr(agent_batch_api_module, handler_export, None)
            if handler is None:
                raise RuntimeError(f"agent batch dispatch handler unavailable for channel={channel}: {handler_export}")
            self.register(
                skill_id=skill_id,
                handler=handler,
                allowed_actor_roles=("orchestration_runtime", "business_capability_wrapper", "user_facing_assistant"),
                required_permissions=(required_permission,),
                owner="agent_batch.api.dispatch",
                execution_profile="agent_batch.dispatch",
                concurrency_class="write_shared",
                approval_policy={"default": "optional"},
                agent_batch_task_manifest=build_agent_batch_manifest_entry(channel),
            )


def _normalize_actor_roles(values: tuple[str, ...] | list[str] | set[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        candidate = str(value or "").strip()
        if not candidate:
            continue
        if candidate not in _ALLOWED_ACTOR_ROLES:
            raise ValueError(f"unsupported actor_role: {candidate}")
        if candidate not in out:
            out.append(candidate)
    if not out:
        return ["orchestration_runtime"]
    return out


def _normalize_permissions(values: tuple[str, ...] | list[str] | set[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        candidate = str(value or "").strip()
        if candidate and candidate not in out:
            out.append(candidate)
    return out


def _normalize_agent_batch_task_manifest(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    entry = dict(value)
    channel = str(entry.get("channel") or "").strip().lower()
    if not channel:
        raise ValueError("agent_batch_task_manifest.channel is required")
    entry["channel"] = channel
    return entry


def _normalize_concurrency_class(value: str | None) -> str:
    candidate = str(value or "read_only").strip().lower() or "read_only"
    if candidate not in _ALLOWED_CONCURRENCY_CLASSES:
        raise ValueError(f"unsupported concurrency_class: {candidate}")
    return candidate


def _normalize_contract_dict(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return dict(value)


def _resolve_actor_role(context: Mapping[str, Any] | None) -> str:
    actor_role = str((context or {}).get("actor_role") or "orchestration_runtime").strip()
    if actor_role not in _ALLOWED_ACTOR_ROLES:
        raise PermissionError(f"unsupported actor_role: {actor_role}")
    return actor_role


def _resolve_requested_permissions(context: Mapping[str, Any] | None, defaults: tuple[str, ...]) -> list[str]:
    raw = (context or {}).get("permissions")
    if isinstance(raw, (list, tuple, set)):
        values = _normalize_permissions(tuple(str(x or "") for x in raw))
        if values:
            return values
    return list(defaults)


def _build_approval_binding(
    *,
    skill_id: str,
    payload: Any,
    args: tuple[Any, ...] | None,
    kwargs: dict[str, Any] | None,
    context: Mapping[str, Any] | None,
    spec: SkillSpec,
) -> dict[str, Any]:
    return {
        "skill_id": skill_id,
        "payload": payload,
        "args": list(args or ()),
        "kwargs": dict(kwargs or {}),
        "consumer": str((context or {}).get("consumer") or "skill_runtime").strip() or "skill_runtime",
        "trace_id": str((context or {}).get("trace_id") or "").strip() or None,
        "owner": spec.owner,
        "execution_profile": spec.execution_profile,
        "concurrency_class": spec.concurrency_class,
    }


def _resolve_agent_session_context(context: Mapping[str, Any] | None) -> tuple[str | None, str | None]:
    session_id = str(
        (context or {}).get("agent_session_id")
        or (context or {}).get("session_id")
        or ""
    ).strip() or None
    task_id = str(
        (context or {}).get("agent_task_id")
        or (context or {}).get("task_id")
        or ""
    ).strip() or None
    return session_id, task_id


def _enforce_runtime_policies(
    *,
    spec: SkillSpec,
    skill_id: str,
    payload: Any,
    args: tuple[Any, ...] | None,
    kwargs: dict[str, Any] | None,
    context: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    concurrency_class = spec.concurrency_class
    if concurrency_class not in {"write_external", "privileged"}:
        return None

    approval_granted = bool((context or {}).get("approval_granted") or (context or {}).get("bypass_approval"))
    if approval_granted:
        return None

    session_id, task_id = _resolve_agent_session_context(context)
    if not session_id or not task_id:
        raise PermissionError(f"skill invoke denied: {skill_id} (approval_context_required)")

    service = get_agent_session_service()
    binding_payload = _build_approval_binding(
        skill_id=skill_id,
        payload=payload,
        args=args,
        kwargs=kwargs,
        context=context,
        spec=spec,
    )
    approval = service.request_approval(
        session_id=session_id,
        task_id=task_id,
        requester_actor=str((context or {}).get("actor_role") or "unknown"),
        binding_payload=binding_payload,
        metadata={
            "skill_id": skill_id,
            "owner": spec.owner,
            "concurrency_class": concurrency_class,
            "approval_policy": dict(spec.approval_policy or {}),
            "required_permissions": list(spec.required_permissions),
            "force_approval": True,
        },
    )
    raise PermissionError(
        f"skill invoke denied: {skill_id} (approval_required:{approval['approval_id']})"
    )


_LOOP_GUARD_LOCK = RLock()
_LOOP_GUARD_STATE: dict[str, dict[str, Any]] = {}


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        return str(value)


def _signature_for_loop_guard(*, skill_id: str, payload: Any, args: tuple[Any, ...] | None, kwargs: dict[str, Any] | None) -> str:
    raw = {
        "skill_id": skill_id,
        "payload": payload,
        "args": args or (),
        "kwargs": kwargs or {},
    }
    return hashlib.sha256(_safe_json(raw).encode("utf-8")).hexdigest()


def _detect_skill_loop_guard(
    *,
    skill_id: str,
    payload: Any,
    args: tuple[Any, ...] | None,
    kwargs: dict[str, Any] | None,
    context: Mapping[str, Any] | None,
) -> str | None:
    if not bool(getattr(settings, "skill_loop_guard_enabled", True)):
        return None
    threshold = max(2, int(getattr(settings, "skill_loop_guard_threshold", 10) or 10))
    ttl_seconds = max(60, int(getattr(settings, "skill_loop_guard_ttl_seconds", 600) or 600))
    consumer = str((context or {}).get("consumer") or "unknown_consumer").strip() or "unknown_consumer"
    trace_id = str((context or {}).get("trace_id") or "").strip() or "no-trace"
    key = f"{consumer}:{trace_id}:{skill_id}"
    signature = _signature_for_loop_guard(skill_id=skill_id, payload=payload, args=args, kwargs=kwargs)

    import time

    now = int(time.time())
    with _LOOP_GUARD_LOCK:
        stale_keys = [k for k, v in _LOOP_GUARD_STATE.items() if int(v.get("updated_at") or 0) < now - ttl_seconds]
        for stale in stale_keys:
            _LOOP_GUARD_STATE.pop(stale, None)

        state = _LOOP_GUARD_STATE.get(key)
        if not state:
            _LOOP_GUARD_STATE[key] = {"signature": signature, "count": 1, "updated_at": now}
            return None
        if str(state.get("signature") or "") == signature:
            state["count"] = int(state.get("count") or 0) + 1
            state["updated_at"] = now
            if int(state["count"]) >= threshold:
                return "tool_loop_detected"
            return None
        state["signature"] = signature
        state["count"] = 1
        state["updated_at"] = now
        return None


_RUNTIME = SkillRuntime()


def list_registered_skills() -> list[dict[str, Any]]:
    return _RUNTIME.list_skills()


def register_skill(
    *,
    skill_id: str,
    handler: SkillHandler,
    allowed_actor_roles: tuple[str, ...] = ("orchestration_runtime",),
    required_permissions: tuple[str, ...] = (),
    owner: str = "unknown",
    execution_profile: str = "default",
    concurrency_class: str = "read_only",
    approval_policy: Mapping[str, Any] | None = None,
    artifact_contract: Mapping[str, Any] | None = None,
    agent_batch_task_manifest: Mapping[str, Any] | None = None,
) -> None:
    _RUNTIME.register(
        skill_id=skill_id,
        handler=handler,
        allowed_actor_roles=allowed_actor_roles,
        required_permissions=required_permissions,
        owner=owner,
        execution_profile=execution_profile,
        concurrency_class=concurrency_class,
        approval_policy=approval_policy,
        artifact_contract=artifact_contract,
        agent_batch_task_manifest=agent_batch_task_manifest,
    )


def invoke_skill(
    *,
    skill_id: str,
    payload: Any = None,
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _RUNTIME.invoke(skill_id=skill_id, payload=payload, args=args, kwargs=kwargs, context=context)


def invoke_skill_safe(
    *,
    skill_id: str,
    payload: Any = None,
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Safe wrapper for skill invocation used by loop-based orchestrators.

    Returns a stable shape and never raises:
    - {"ok": True, "result": <invoke_skill response>, "error": None}
    - {"ok": False, "result": None, "error": "<message>"}
    """
    try:
        return {
            "ok": True,
            "result": invoke_skill(
                skill_id=skill_id,
                payload=payload,
                args=args,
                kwargs=kwargs,
                context=context,
            ),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "result": None, "error": str(exc)}


def list_registered_agent_batch_task_manifest_entries() -> list[dict[str, Any]]:
    return _RUNTIME.list_agent_batch_task_manifest_entries()
