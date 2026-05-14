from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any


SESSION_CONTEXT_CONTRACT_VERSION = "agent_runtime.session_context_summary.v1"
DEFAULT_TOKEN_THRESHOLD = 4000
DEFAULT_EVENT_THRESHOLD = 24
DEFAULT_TOOL_THRESHOLD = 12
PRIORITY_ORDER = (
    "latest_user_instruction",
    "approval_state",
    "current_task",
    "tool_result_summary",
    "project_summary",
    "history_summary",
)
TOOL_RESULT_EVENT_TYPES = {
    "interactive_agent.tool_call_result",
    "interactive_agent.capability_executed",
    "interactive_agent.approval_continued",
}
SUMMARY_REQUEST_PATTERN = re.compile(r"(总结|摘要|压缩|记忆|summari[sz]e|summary|memory)", re.IGNORECASE)
MEMORY_CORRECTION_PATTERN = re.compile(
    r"(记忆.*(错|不对|错误|修正|纠正|失效)|"
    r"(刚才|之前|上次).*(说错|不对|错了|错误)|"
    r"(不是|并不是).*(你说|你记|记忆)|"
    r"correct .*memory|memory .*wrong|invalidate .*summary)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SessionContextBudget:
    max_chars: int = 8000
    min_section_chars: int = 180
    per_section_max_chars: dict[str, int] = field(
        default_factory=lambda: {
            "latest_user_instruction": 1600,
            "approval_state": 1200,
            "current_task": 1200,
            "tool_result_summary": 1800,
            "project_summary": 1500,
            "history_summary": 1400,
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_chars": int(self.max_chars),
            "min_section_chars": int(self.min_section_chars),
            "per_section_max_chars": dict(self.per_section_max_chars),
        }


@dataclass(frozen=True)
class SessionMemoryUpdateThresholds:
    token_threshold: int = DEFAULT_TOKEN_THRESHOLD
    event_threshold: int = DEFAULT_EVENT_THRESHOLD
    tool_threshold: int = DEFAULT_TOOL_THRESHOLD

    def to_dict(self) -> dict[str, int]:
        return {
            "token_threshold": int(self.token_threshold),
            "event_threshold": int(self.event_threshold),
            "tool_threshold": int(self.tool_threshold),
        }


def build_session_context_summary(
    bundle: dict[str, Any],
    *,
    latest_user_instruction: str | None = None,
    project_key: str | None = None,
    budget: SessionContextBudget | None = None,
    thresholds: SessionMemoryUpdateThresholds | None = None,
) -> dict[str, Any]:
    """Build the model-facing compressed context for an AgentSessionService bundle."""

    safe_bundle = _safe_bundle(bundle)
    resolved_project_key = str(project_key or safe_bundle["session"].get("project_key") or "").strip() or None
    resolved_instruction = _compact_text(latest_user_instruction) or _latest_user_instruction(safe_bundle["messages"])
    stable_summary = build_stable_summary(safe_bundle, latest_user_instruction=resolved_instruction)
    tool_use_summary = build_tool_use_summary(safe_bundle)
    project_context = build_project_context(
        safe_bundle,
        project_key=resolved_project_key,
        tool_calls=tool_use_summary.get("_tool_calls_for_context") or [],
    )
    tool_use_summary.pop("_tool_calls_for_context", None)
    budgeted_context = build_budgeted_context(
        stable_summary=stable_summary,
        project_context=project_context,
        tool_use_summary=tool_use_summary,
        latest_user_instruction=resolved_instruction,
        budget=budget,
    )
    memory_update = should_update_memory(safe_bundle, thresholds=thresholds)
    return {
        "contract_version": SESSION_CONTEXT_CONTRACT_VERSION,
        "stable_summary": stable_summary,
        "project_context": project_context,
        "tool_use_summary": tool_use_summary,
        "budgeted_context": budgeted_context,
        "memory_update": memory_update,
    }


def build_stable_summary(bundle: dict[str, Any], *, latest_user_instruction: str | None = None) -> dict[str, Any]:
    safe_bundle = _safe_bundle(bundle)
    session = safe_bundle["session"]
    tasks = safe_bundle["tasks"]
    messages = safe_bundle["messages"]
    events = safe_bundle["events"]
    artifacts = safe_bundle["artifacts"]
    approvals = safe_bundle["approvals"]
    current_task = _select_current_task(tasks)
    completed_tasks = [task for task in tasks if str(task.get("status") or "") == "completed"]
    failed_tasks = [task for task in tasks if str(task.get("status") or "") in {"failed", "canceled", "expired"}]
    pending_tasks = [task for task in tasks if str(task.get("status") or "") in {"pending", "blocked", "claimed", "in_progress"}]
    return {
        "contract_version": SESSION_CONTEXT_CONTRACT_VERSION,
        "session": {
            "session_id": session.get("session_id"),
            "source": session.get("source"),
            "entrypoint_type": session.get("entrypoint_type"),
            "project_key": session.get("project_key"),
            "goal": _compact_text(session.get("goal"), max_chars=360),
            "status": session.get("status"),
            "current_phase": session.get("current_phase"),
            "compat_mode": bool(session.get("compat_mode")),
            "compat_job_id": session.get("compat_job_id"),
        },
        "counts": {
            "messages": len(messages),
            "tasks": len(tasks),
            "events": len(events),
            "artifacts": len(artifacts),
            "approvals": len(approvals),
            "pending_approvals": sum(1 for item in approvals if str(item.get("status") or "") == "pending"),
        },
        "latest_user_instruction": _compact_text(latest_user_instruction) or _latest_user_instruction(messages),
        "memory_correction": build_memory_correction_marker(messages),
        "current_task": _compact_task(current_task) if current_task else None,
        "history_summary": {
            "recent_messages": [_compact_message(item) for item in messages[-6:]],
            "completed_tasks": [_compact_task(item) for item in completed_tasks[-5:]],
            "open_tasks": [_compact_task(item) for item in pending_tasks[-6:]],
            "failed_tasks": [_compact_task(item) for item in failed_tasks[-4:]],
        },
    }


def build_project_context(
    bundle: dict[str, Any],
    *,
    project_key: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    safe_bundle = _safe_bundle(bundle)
    session = safe_bundle["session"]
    artifacts = safe_bundle["artifacts"]
    tasks = safe_bundle["tasks"]
    calls = list(tool_calls or _extract_tool_calls(safe_bundle))
    source_library = _source_library_context_from_calls(calls)
    ingest_status = _latest_result_for_tool(calls, "ingest.status.read")
    workflow_graph = _workflow_context_from_calls(calls)
    artifact_types: dict[str, int] = {}
    for artifact in artifacts:
        artifact_type = str(artifact.get("artifact_type") or "unknown")
        artifact_types[artifact_type] = artifact_types.get(artifact_type, 0) + 1
    recent_runs = [
        _compact_task(task)
        for task in tasks
        if any(token in str(task.get("task_type") or task.get("subject") or "").lower() for token in ("run", "ingest", "workflow", "capability"))
    ][-6:]
    return {
        "project_key": project_key or session.get("project_key"),
        "goal": _compact_text(session.get("goal"), max_chars=360),
        "session_status": session.get("status"),
        "artifact_index": {
            "total": len(artifacts),
            "types": artifact_types,
            "recent": [_compact_artifact(item) for item in artifacts[-8:]],
        },
        "source_library": source_library,
        "ingest_status": ingest_status,
        "workflow_graph": workflow_graph,
        "recent_runs": recent_runs,
    }


def build_tool_use_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    safe_bundle = _safe_bundle(bundle)
    calls = _extract_tool_calls(safe_bundle)
    tool_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    protocol_counts: dict[str, int] = {}
    failures: list[dict[str, Any]] = []
    for call in calls:
        tool_name = str(call.get("tool_name") or call.get("capability_id") or "unknown")
        status = str(call.get("status") or "unknown")
        protocol = str(call.get("protocol") or "unknown")
        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1
        protocol_counts[protocol] = protocol_counts.get(protocol, 0) + 1
        if status in {"failed", "error"} or call.get("error"):
            failures.append(_public_tool_call(call))
    return {
        "total_calls": len(calls),
        "unique_tool_count": len(tool_counts),
        "tool_counts": tool_counts,
        "status_counts": status_counts,
        "protocol_counts": protocol_counts,
        "recent_results": [_public_tool_call(item) for item in calls[-10:]],
        "latest_failures": failures[-5:],
        "_tool_calls_for_context": calls,
    }


def build_budgeted_context(
    *,
    stable_summary: dict[str, Any],
    project_context: dict[str, Any],
    tool_use_summary: dict[str, Any],
    latest_user_instruction: str | None = None,
    budget: SessionContextBudget | None = None,
) -> dict[str, Any]:
    active_budget = budget or SessionContextBudget()
    max_chars = max(1, int(active_budget.max_chars))
    raw_sections = {
        "latest_user_instruction": _compact_text(latest_user_instruction)
        or _compact_text(stable_summary.get("latest_user_instruction")),
        "approval_state": _approval_state_from_summary(stable_summary),
        "current_task": stable_summary.get("current_task"),
        "tool_result_summary": {
            "total_calls": tool_use_summary.get("total_calls"),
            "status_counts": tool_use_summary.get("status_counts"),
            "recent_results": tool_use_summary.get("recent_results"),
            "latest_failures": tool_use_summary.get("latest_failures"),
        },
        "project_summary": {
            "project_key": project_context.get("project_key"),
            "artifact_index": project_context.get("artifact_index"),
            "source_library": project_context.get("source_library"),
            "workflow_graph": project_context.get("workflow_graph"),
            "ingest_status": project_context.get("ingest_status"),
        },
        "history_summary": stable_summary.get("history_summary"),
    }
    sections: list[dict[str, Any]] = []
    omitted: list[str] = []
    remaining = max_chars
    for index, key in enumerate(PRIORITY_ORDER, start=1):
        rendered = _render_section(raw_sections.get(key))
        if not rendered:
            continue
        section_cap = min(
            max(1, int(active_budget.per_section_max_chars.get(key, max_chars))),
            max_chars,
        )
        rendered = _clip_text(rendered, section_cap)
        header = f"[{key}]"
        text = f"{header}\n{rendered}"
        separator_chars = 2 if sections else 0
        if len(text) + separator_chars > remaining:
            if remaining >= max(32, int(active_budget.min_section_chars)) or not sections:
                text = _clip_text(text, remaining - separator_chars)
                truncated = True
            else:
                omitted.append(key)
                continue
        else:
            truncated = len(rendered) >= section_cap and len(_render_section(raw_sections.get(key))) > section_cap
        sections.append(
            {
                "key": key,
                "priority": index,
                "chars": len(text),
                "truncated": bool(truncated),
                "content": text,
            }
        )
        remaining -= len(text) + separator_chars
        if remaining <= 0:
            omitted.extend(item for item in PRIORITY_ORDER[index:] if item not in omitted)
            break
    text = "\n\n".join(section["content"] for section in sections)
    return {
        "priority_order": list(PRIORITY_ORDER),
        "budget": active_budget.to_dict(),
        "used_chars": len(text),
        "sections": sections,
        "omitted_sections": omitted,
        "text": text,
    }


def should_update_memory(
    bundle: dict[str, Any],
    *,
    thresholds: SessionMemoryUpdateThresholds | None = None,
) -> dict[str, Any]:
    safe_bundle = _safe_bundle(bundle)
    active_thresholds = thresholds or SessionMemoryUpdateThresholds()
    events = safe_bundle["events"]
    tasks = safe_bundle["tasks"]
    messages = safe_bundle["messages"]
    event_window = _events_since_latest_memory_update(events)
    calls = _extract_tool_calls({"events": event_window, "tasks": tasks, "messages": messages, "session": {}, "artifacts": [], "approvals": []})
    recorded_tokens = sum(_safe_int(task.get("token_usage")) for task in tasks)
    estimated_tokens = _estimate_context_tokens(safe_bundle)
    token_count = max(recorded_tokens, estimated_tokens)
    recorded_tool_count = sum(_safe_int(task.get("tool_use_count")) for task in tasks)
    tool_count = max(recorded_tool_count, len(calls))
    latest_event = _latest_non_memory_event(events)
    latest_user = _latest_user_instruction(messages)
    correction_marker = build_memory_correction_marker(messages)
    reasons: list[str] = []
    if token_count >= int(active_thresholds.token_threshold):
        reasons.append("token_threshold")
    if len(event_window) >= int(active_thresholds.event_threshold):
        reasons.append("event_threshold")
    if tool_count >= int(active_thresholds.tool_threshold):
        reasons.append("tool_threshold")
    if latest_event and str(latest_event.get("event_type") or "").startswith("task.completed"):
        reasons.append("task_completed")
    if latest_user and SUMMARY_REQUEST_PATTERN.search(latest_user):
        reasons.append("user_requested_summary")
    if correction_marker["invalidates_previous_summary"]:
        reasons.append("user_corrected_memory")
    return {
        "should_update": bool(reasons),
        "reasons": reasons,
        "correction": correction_marker,
        "metrics": {
            "token_count": token_count,
            "recorded_token_count": recorded_tokens,
            "estimated_token_count": estimated_tokens,
            "event_count_since_memory_update": len(event_window),
            "event_count_total": len(events),
            "tool_count": tool_count,
            "recorded_tool_count": recorded_tool_count,
            "tool_result_count_since_memory_update": len(calls),
        },
        "thresholds": active_thresholds.to_dict(),
    }


def build_memory_correction_marker(messages: list[dict[str, Any]]) -> dict[str, Any]:
    latest_user = _latest_user_instruction(messages)
    matched = bool(latest_user and MEMORY_CORRECTION_PATTERN.search(latest_user))
    return {
        "invalidates_previous_summary": matched,
        "latest_correction": _compact_text(latest_user, max_chars=800) if matched else "",
        "handling": "mark_previous_summary_stale_and_rebuild" if matched else "none",
    }


def _safe_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    data = dict(bundle or {})
    return {
        "session": dict(data.get("session") or {}),
        "tasks": [dict(item or {}) for item in list(data.get("tasks") or [])],
        "messages": [dict(item or {}) for item in list(data.get("messages") or [])],
        "events": [dict(item or {}) for item in list(data.get("events") or [])],
        "artifacts": [dict(item or {}) for item in list(data.get("artifacts") or [])],
        "approvals": [dict(item or {}) for item in list(data.get("approvals") or [])],
    }


def _select_current_task(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    for status in ("claimed", "in_progress", "blocked", "pending"):
        for task in reversed(tasks):
            if str(task.get("status") or "") == status:
                return task
    return tasks[-1] if tasks else None


def _latest_user_instruction(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if str(message.get("role") or "").lower() == "user":
            text = _compact_text(message.get("content"), max_chars=2000)
            if text:
                return text
    return ""


def _compact_task(task: dict[str, Any] | None) -> dict[str, Any] | None:
    if not task:
        return None
    return {
        "task_id": task.get("task_id"),
        "subject": _compact_text(task.get("subject"), max_chars=180),
        "task_type": task.get("task_type"),
        "phase": task.get("phase"),
        "status": task.get("status"),
        "owner": task.get("owner"),
        "last_activity": _compact_text(task.get("last_activity"), max_chars=180),
        "result_summary": _compact_text(task.get("result_summary"), max_chars=300),
        "tool_use_count": _safe_int(task.get("tool_use_count")),
        "token_usage": _safe_int(task.get("token_usage")),
        "blocked_by": list(task.get("blocked_by") or [])[:8],
    }


def _compact_message(message: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(message.get("metadata") or {})
    return {
        "message_id": message.get("message_id"),
        "role": message.get("role"),
        "actor": message.get("actor"),
        "task_id": message.get("task_id"),
        "created_at": message.get("created_at"),
        "content": _compact_text(message.get("content"), max_chars=360),
        "turn_id": metadata.get("turn_id") or metadata.get("interactive_turn_id"),
    }


def _compact_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(artifact.get("metadata") or {})
    return {
        "artifact_id": artifact.get("artifact_id"),
        "task_id": artifact.get("task_id"),
        "artifact_type": artifact.get("artifact_type"),
        "name": artifact.get("name"),
        "mime_type": artifact.get("mime_type"),
        "path": artifact.get("path"),
        "summary": _compact_text(artifact.get("summary"), max_chars=260),
        "turn_id": metadata.get("turn_id"),
        "capability_id": metadata.get("capability_id"),
        "status": metadata.get("status"),
    }


def _extract_tool_calls(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    safe_bundle = _safe_bundle(bundle)
    calls: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in safe_bundle["events"]:
        event_type = str(event.get("event_type") or "")
        if event_type not in TOOL_RESULT_EVENT_TYPES:
            continue
        payload = dict(event.get("payload") or {})
        capability_id = str(payload.get("capability_id") or payload.get("tool_name") or "").strip()
        if not capability_id:
            continue
        key = str(payload.get("call_id") or "").strip()
        if not key:
            key = "|".join(
                [
                    event_type,
                    str(event.get("task_id") or ""),
                    str(event.get("seq") or ""),
                    capability_id,
                    str(payload.get("status") or payload.get("stream_state") or ""),
                    str(payload.get("summary") or ""),
                ]
            )
        if key in seen:
            continue
        seen.add(key)
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        calls.append(
            {
                "event_type": event_type,
                "seq": event.get("seq"),
                "event_id": event.get("event_id"),
                "created_at": event.get("created_at"),
                "task_id": event.get("task_id"),
                "turn_id": payload.get("turn_id"),
                "call_id": payload.get("call_id"),
                "capability_id": capability_id,
                "tool_name": payload.get("tool_name") or capability_id,
                "protocol": payload.get("protocol"),
                "status": payload.get("status") or payload.get("stream_state"),
                "summary": _compact_text(payload.get("summary"), max_chars=360),
                "error": _compact_error(payload.get("error")),
                "result": result,
                "result_summary": _summarize_tool_result(result),
            }
        )
    return calls


def _public_tool_call(call: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": call.get("event_type"),
        "seq": call.get("seq"),
        "created_at": call.get("created_at"),
        "task_id": call.get("task_id"),
        "turn_id": call.get("turn_id"),
        "call_id": call.get("call_id"),
        "capability_id": call.get("capability_id"),
        "tool_name": call.get("tool_name"),
        "protocol": call.get("protocol"),
        "status": call.get("status"),
        "summary": call.get("summary"),
        "error": call.get("error"),
        "result_summary": call.get("result_summary"),
    }


def _compact_error(error: Any) -> dict[str, Any] | None:
    if not isinstance(error, dict):
        return None
    return {
        "type": error.get("type"),
        "message": _compact_text(error.get("message"), max_chars=300),
        "recoverable": error.get("recoverable"),
    }


def _summarize_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    if not result:
        return {}
    summary: dict[str, Any] = {}
    for key in ("total", "source_total", "project_key", "query", "run_id", "status"):
        if key in result:
            summary[key] = result.get(key)
    if isinstance(result.get("source_library"), dict):
        source = dict(result.get("source_library") or {})
        summary["source_library"] = {
            "total": source.get("total"),
            "enabled": source.get("enabled"),
            "channels": dict(source.get("channels") or {}),
        }
    items = result.get("items")
    if isinstance(items, list):
        summary["items_preview"] = [_compact_item_preview(item) for item in items[:5] if isinstance(item, dict)]
        summary["items_count"] = len(items)
    artifact = result.get("artifact")
    if isinstance(artifact, dict):
        summary["artifact"] = _compact_artifact(artifact)
    graph = result.get("graph")
    if isinstance(graph, dict):
        summary["graph"] = {
            "graph_id": graph.get("graph_id"),
            "version": graph.get("version"),
            "node_count": graph.get("node_count"),
            "checksum": graph.get("checksum"),
        }
    if not summary:
        summary["preview"] = _clip_text(_to_json(result), 700)
    return summary


def _compact_item_preview(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_key": item.get("item_key"),
        "name": _compact_text(item.get("name"), max_chars=120),
        "channel_key": item.get("channel_key"),
        "enabled": item.get("enabled"),
        "scope": item.get("scope"),
        "capability_id": item.get("capability_id"),
        "tool_name": item.get("tool_name"),
    }


def _source_library_context_from_calls(calls: list[dict[str, Any]]) -> dict[str, Any]:
    for call in reversed(calls):
        result = dict(call.get("result") or {})
        capability_id = str(call.get("capability_id") or "")
        if capability_id == "project.summary.read" and isinstance(result.get("source_library"), dict):
            source = dict(result.get("source_library") or {})
            return {
                "available": True,
                "source": "project.summary.read",
                "total": source.get("total"),
                "enabled": source.get("enabled"),
                "channels": dict(source.get("channels") or {}),
                "sample": [_compact_item_preview(item) for item in list(source.get("sample") or []) if isinstance(item, dict)][:8],
            }
    for call in reversed(calls):
        result = dict(call.get("result") or {})
        capability_id = str(call.get("capability_id") or "")
        if capability_id in {"source_library.item.list", "source_library.item.search"}:
            return {
                "available": True,
                "source": capability_id,
                "total": result.get("total"),
                "source_total": result.get("source_total"),
                "project_key": result.get("project_key"),
                "sample": [_compact_item_preview(item) for item in list(result.get("items") or []) if isinstance(item, dict)][:8],
            }
    return {"available": False, "source": None, "total": 0, "sample": []}


def _workflow_context_from_calls(calls: list[dict[str, Any]]) -> dict[str, Any]:
    latest_list = _latest_result_for_tool(calls, "workflow_graph.list")
    latest_inspect = _latest_result_for_tool(calls, "workflow_graph.inspect")
    return {
        "latest_list": latest_list,
        "latest_inspect": latest_inspect,
    }


def _latest_result_for_tool(calls: list[dict[str, Any]], capability_id: str) -> dict[str, Any] | None:
    for call in reversed(calls):
        if str(call.get("capability_id") or "") == capability_id:
            return {
                "status": call.get("status"),
                "summary": call.get("summary"),
                "result_summary": call.get("result_summary"),
                "created_at": call.get("created_at"),
            }
    return None


def _approval_state_from_summary(stable_summary: dict[str, Any]) -> dict[str, Any]:
    counts = dict(stable_summary.get("counts") or {})
    history = dict(stable_summary.get("history_summary") or {})
    open_tasks = [item for item in list(history.get("open_tasks") or []) if isinstance(item, dict)]
    approval_tasks = [
        item
        for item in open_tasks
        if str(item.get("task_type") or "") == "approval_wait" or str(item.get("status") or "") == "blocked"
    ]
    return {
        "approval_count": counts.get("approvals") or 0,
        "pending_approvals": counts.get("pending_approvals") or 0,
        "approval_related_tasks": approval_tasks[-5:],
    }


def _events_since_latest_memory_update(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_memory_index = -1
    for index, event in enumerate(events):
        if str(event.get("event_type") or "") == "memory.updated":
            latest_memory_index = index
    return events[latest_memory_index + 1 :] if latest_memory_index >= 0 else events


def _latest_non_memory_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if str(event.get("event_type") or "") != "memory.updated":
            return event
    return None


def _estimate_context_tokens(bundle: dict[str, Any]) -> int:
    text_parts: list[str] = []
    for message in bundle.get("messages") or []:
        text_parts.append(str(dict(message or {}).get("content") or ""))
    for task in bundle.get("tasks") or []:
        item = dict(task or {})
        text_parts.append(str(item.get("result_summary") or ""))
        text_parts.append(str(item.get("last_activity") or ""))
    for event in bundle.get("events") or []:
        payload = dict(dict(event or {}).get("payload") or {})
        text_parts.append(str(payload.get("summary") or ""))
    char_count = len(" ".join(text_parts))
    return max(0, char_count // 4)


def _render_section(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _compact_text(value, max_chars=100000)
    if isinstance(value, (dict, list, tuple)):
        return _to_json(value)
    return _compact_text(value, max_chars=100000)


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _compact_text(value: Any, *, max_chars: int = 1000) -> str:
    text = " ".join(str(value or "").split())
    return _clip_text(text, max_chars)


def _clip_text(text: str, max_chars: int) -> str:
    limit = max(0, int(max_chars))
    if limit <= 0:
        return ""
    value = str(text or "")
    if len(value) <= limit:
        return value
    if limit <= 1:
        return value[:limit]
    return value[: limit - 3].rstrip() + "..." if limit > 3 else value[:limit]


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:  # noqa: BLE001
        return 0
