from __future__ import annotations

from typing import Any

from app.settings.config import settings


class SessionMemoryRuntime:
    def should_refresh(self, *, tasks: list[dict[str, Any]], events: list[dict[str, Any]]) -> tuple[bool, dict[str, int]]:
        token_total = sum(int(task.get("token_usage") or 0) for task in tasks)
        tool_total = sum(int(task.get("tool_use_count") or 0) for task in tasks)
        event_total = len(events)
        thresholds = {
            "token_total": token_total,
            "tool_total": tool_total,
            "event_total": event_total,
        }
        thresholds_met = (
            token_total >= int(getattr(settings, "agent_session_memory_token_threshold", 4000) or 4000)
            or tool_total >= int(getattr(settings, "agent_session_memory_tool_threshold", 12) or 12)
            or event_total >= int(getattr(settings, "agent_session_memory_event_threshold", 16) or 16)
        )
        return thresholds_met, thresholds

    def render_memory(self, session: dict[str, Any], tasks: list[dict[str, Any]], messages: list[dict[str, Any]]) -> str:
        completed = [task for task in tasks if task.get("status") == "completed"]
        lines = [
            "# Session Memory",
            "",
            f"- Goal: {session.get('goal')}",
            f"- Source: {session.get('source')}",
            f"- Project: {session.get('project_key') or 'n/a'}",
            f"- Current phase: {session.get('current_phase')}",
            f"- Compatibility mode: {'yes' if session.get('compat_mode') else 'no'}",
        ]
        if session.get("compat_job_id"):
            lines.append(f"- Compat job id: {session.get('compat_job_id')}")
        if messages:
            latest = messages[-1]
            content = str(latest.get("content") or "").strip()
            if content:
                compact = " ".join(content.split())
                lines.append(f"- Latest coordinator note: {compact[:160]}")
        for task in completed[:6]:
            summary = str(task.get("result_summary") or task.get("summary_label") or "").strip()
            if summary:
                lines.append(f"- Completed: {summary}")
        return "\n".join(lines).strip() + "\n"

    def render_scratchpad(self, session: dict[str, Any], tasks: list[dict[str, Any]], messages: list[dict[str, Any]]) -> str:
        current = next((task for task in tasks if task.get("status") in {"claimed", "in_progress"}), None)
        pending = [task for task in tasks if task.get("status") in {"pending", "blocked"}]
        lines = [
            "# Scratchpad",
            "",
            f"- Session id: {session.get('session_id')}",
            f"- Current phase: {session.get('current_phase')}",
        ]
        if current is not None:
            lines.append(f"- Active task: {current.get('subject')} ({current.get('status')})")
        if messages:
            lines.append("- Recent coordinator messages:")
            for message in messages[-3:]:
                actor = str(message.get("actor") or message.get("role") or "agent")
                content = " ".join(str(message.get("content") or "").split())
                if content:
                    lines.append(f"  - {actor}: {content[:160]}")
        if pending:
            lines.append("- Next tasks:")
            for task in pending[:4]:
                lines.append(f"  - {task.get('subject')} [{task.get('status')}]")
        else:
            lines.append("- Next tasks: none")
        return "\n".join(lines).strip() + "\n"
