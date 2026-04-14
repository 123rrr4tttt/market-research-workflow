from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .progress import build_summary_label
from .task_bus import find_unresolved_dependencies


class CoordinatorRuntime:
    """Claude-style coordinator pass over the session/task ledger."""

    def run_pass(self, service: Any, session_id: str) -> dict[str, Any]:
        service.reclaim_expired_tasks(session_id)
        session = service.store.get_session(session_id)
        tasks = service.store.list_tasks(session_id)
        messages = service.store.list_messages(session_id)
        approvals = service.store.list_approvals(session_id=session_id)
        decisions: list[dict[str, Any]] = []

        pending_synthesis = next(
            (
                task
                for task in tasks
                if str(task.get("phase") or "") == "synthesis"
                and str(task.get("status") or "") in {"pending", "blocked"}
                and not find_unresolved_dependencies(task, tasks)
            ),
            None,
        )
        if pending_synthesis and self._all_research_complete(tasks):
            decision = self._complete_synthesis(service, session, tasks, pending_synthesis)
            decisions.append(decision)
            tasks = service.store.list_tasks(session_id)
            messages = service.store.list_messages(session_id)

        waiting_approval = [approval for approval in approvals if str(approval.get("status") or "") == "pending"]
        if waiting_approval:
            for approval in waiting_approval:
                decisions.append(
                    {
                        "action": "wait_for_approval",
                        "approval_id": approval.get("approval_id"),
                        "requester_task_id": approval.get("requester_task_id"),
                    }
                )
        gated_task_ids = {
            str(approval.get("requester_task_id") or "").strip()
            for approval in waiting_approval
            if str(approval.get("requester_task_id") or "").strip()
        }

        for task in tasks:
            phase = str(task.get("phase") or "")
            status = str(task.get("status") or "")
            if phase not in {"implementation", "verification"}:
                continue
            if str(task.get("task_id") or "") in gated_task_ids:
                continue
            if status not in {"pending", "blocked"}:
                continue
            if find_unresolved_dependencies(task, tasks):
                continue
            decision = self._plan_worker_dispatch(session=session, task=task, tasks=tasks, messages=messages)
            service.store.update_task(
                session_id,
                task["task_id"],
                {
                    "status": "pending",
                    "metadata": {**dict(task.get("metadata") or {}), "coordinator_dispatch": decision},
                    "summary_label": build_summary_label({**task, "status": "pending"}),
                },
            )
            service.create_message(
                session_id,
                task_id=task["task_id"],
                role="assistant",
                actor="coordinator",
                content=decision["prompt"],
                metadata={"coordinator_dispatch": decision},
            )
            service.store.append_event(
                session_id,
                event_type="coordinator.dispatch_planned",
                task_id=task["task_id"],
                payload=decision,
            )
            decisions.append(decision)

        if not decisions:
            noop = {
                "action": "noop",
                "reason": "no_ready_transition",
                "session_id": session_id,
            }
            service.create_message(
                session_id,
                role="assistant",
                actor="coordinator",
                content="No coordinator transition was ready; waiting for new worker progress or approval resolution.",
                metadata={"coordinator_decision": noop},
            )
            service.store.append_event(session_id, event_type="coordinator.noop", payload=noop)
            decisions.append(noop)

        service._refresh_memory_artifacts(session_id, force=True)
        service._sync_session_state(session_id)
        return {
            "session": service.get_session(session_id),
            "decisions": decisions,
            "messages": service.list_messages(session_id),
        }

    @staticmethod
    def _all_research_complete(tasks: list[dict[str, Any]]) -> bool:
        research = [task for task in tasks if str(task.get("phase") or "") == "research"]
        return bool(research) and all(str(task.get("status") or "") == "completed" for task in research)

    def _complete_synthesis(
        self,
        service: Any,
        session: dict[str, Any],
        tasks: list[dict[str, Any]],
        synthesis_task: dict[str, Any],
    ) -> dict[str, Any]:
        research_tasks = [task for task in tasks if str(task.get("phase") or "") == "research"]
        completed_summaries = [
            str(task.get("result_summary") or task.get("summary_label") or "").strip()
            for task in research_tasks
            if str(task.get("status") or "") == "completed"
        ]
        worker_spec = {
            "task_type": "implementation",
            "goal": session.get("goal"),
            "context": {
                "research_findings": completed_summaries,
                "session_id": session.get("session_id"),
            },
            "target_scope": "session",
            "write_set": ["session:default"],
            "completion_criteria": ["Apply the synthesized plan with minimal, explicit changes."],
            "verification_steps": ["Run the minimal targeted checks and report residual risk."],
            "artifact_targets": ["coordinator_spec.json", "scratchpad.md", "memory.md"],
        }
        artifact = service.store.upsert_artifact(
            {
                "session_id": session["session_id"],
                "task_id": synthesis_task["task_id"],
                "artifact_type": "coordinator_spec_json",
                "name": "coordinator.spec.json",
                "mime_type": "application/json",
                "content_json": worker_spec,
                "metadata": {"phase": "synthesis"},
            }
        )
        summary = f"Synthesized {len(completed_summaries)} research findings into implementation spec"
        service.store.update_task(
            session["session_id"],
            synthesis_task["task_id"],
            {
                "status": "completed",
                "result_summary": summary,
                "result_payload": worker_spec,
                "completed_at": datetime.now(timezone.utc),
                "summary_label": summary[:120],
            },
        )
        service.create_message(
            session["session_id"],
            task_id=synthesis_task["task_id"],
            role="assistant",
            actor="coordinator",
            content=summary,
            metadata={"coordinator_spec_artifact_id": artifact["artifact_id"]},
        )
        service.store.append_event(
            session["session_id"],
            event_type="coordinator.synthesis_completed",
            task_id=synthesis_task["task_id"],
            payload={"artifact_id": artifact["artifact_id"], "summary": summary},
        )
        service._unblock_dependents(session["session_id"], synthesis_task["task_id"])
        return {
            "action": "synthesis_completed",
            "task_id": synthesis_task["task_id"],
            "artifact_id": artifact["artifact_id"],
            "summary": summary,
        }

    def _plan_worker_dispatch(
        self,
        *,
        session: dict[str, Any],
        task: dict[str, Any],
        tasks: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        strategy = self._choose_continue_vs_spawn(task=task, tasks=tasks)
        spec = dict(task.get("task_spec") or {})
        prompt_lines = [
            f"Task: {task.get('subject')}",
            f"Goal: {spec.get('goal') or session.get('goal')}",
            f"Target scope: {spec.get('target_scope') or 'session'}",
        ]
        write_set = list(spec.get("write_set") or task.get("write_set") or [])
        if write_set:
            prompt_lines.append(f"Write set: {', '.join(str(item) for item in write_set)}")
        completion = list(spec.get("completion_criteria") or [])
        verification = list(spec.get("verification_steps") or [])
        if completion:
            prompt_lines.append("Completion criteria:")
            prompt_lines.extend(f"- {item}" for item in completion)
        if verification:
            prompt_lines.append("Verification steps:")
            prompt_lines.extend(f"- {item}" for item in verification)
        if messages:
            recent = [
                " ".join(str(item.get("content") or "").split())
                for item in messages[-2:]
                if str(item.get("content") or "").strip()
            ]
            if recent:
                prompt_lines.append("Recent coordinator context:")
                prompt_lines.extend(f"- {item[:180]}" for item in recent)
        return {
            "action": "dispatch_worker",
            "task_id": task["task_id"],
            "phase": task.get("phase"),
            "strategy": strategy,
            "prompt": "\n".join(prompt_lines),
            "worker_spec": spec,
        }

    @staticmethod
    def _choose_continue_vs_spawn(*, task: dict[str, Any], tasks: list[dict[str, Any]]) -> str:
        phase = str(task.get("phase") or "")
        completed = [item for item in tasks if str(item.get("status") or "") == "completed"]
        if phase == "verification":
            return "spawn"
        target_scope = str(dict(task.get("task_spec") or {}).get("target_scope") or "").strip()
        write_set = set(str(item) for item in list(task.get("write_set") or []))
        overlaps = 0
        for item in completed:
            if phase == "implementation" and str(item.get("phase") or "") == "research":
                item_scope = str(dict(item.get("task_spec") or {}).get("target_scope") or "").strip()
                item_sets = set(str(entry) for entry in list(item.get("write_set") or []) + list(item.get("read_set") or []))
                if (target_scope and item_scope and target_scope == item_scope) or write_set.intersection(item_sets):
                    overlaps += 1
        return "continue" if overlaps == 1 else "spawn"
