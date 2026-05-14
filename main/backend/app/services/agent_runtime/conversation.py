from __future__ import annotations

from typing import Any, Protocol

from ...settings.config import settings


class AgentConversationAnswerer(Protocol):
    def answer(
        self,
        *,
        message: str,
        project_key: str | None,
        context_summary: dict[str, Any],
        turn_decision: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class ModelConversationAnswerer:
    """Generate a natural assistant reply for plain conversation turns."""

    def __init__(self, *, chat_model: Any | None = None, chat_model_factory: Any | None = None) -> None:
        self.chat_model = chat_model
        self.chat_model_factory = chat_model_factory

    def answer(
        self,
        *,
        message: str,
        project_key: str | None,
        context_summary: dict[str, Any],
        turn_decision: dict[str, Any],
    ) -> dict[str, Any]:
        model = self._get_model()
        prompt = self._build_prompt(
            message=message,
            project_key=project_key,
            context_summary=context_summary,
            turn_decision=turn_decision,
        )
        response = model.invoke(prompt)
        content = getattr(response, "content", None)
        if content is None and isinstance(response, dict):
            content = response.get("content")
        answer = str(content or "").strip()
        if not answer:
            raise RuntimeError("conversation model returned empty answer")
        return {
            "answer": answer,
            "source": "model",
            "model_path": self.__class__.__name__,
        }

    def _get_model(self) -> Any:
        if self.chat_model is not None:
            return self.chat_model
        if self.chat_model_factory is not None:
            self.chat_model = self.chat_model_factory()
            return self.chat_model
        from app.services.llm.provider import get_local_fallback_chat

        timeout = int(getattr(settings, "agent_chat_model_answer_timeout_seconds", 45) or 45)
        self.chat_model = get_local_fallback_chat(
            temperature=0.3,
            max_tokens=900,
            timeout_seconds=timeout,
            codex_cli_timeout_seconds=timeout,
            codex_cli_reasoning_effort="none",
        )
        return self.chat_model

    @staticmethod
    def _build_prompt(
        *,
        message: str,
        project_key: str | None,
        context_summary: dict[str, Any],
        turn_decision: dict[str, Any],
    ) -> str:
        context_counts = dict(context_summary.get("counts") or {})
        recent_memory = str(context_summary.get("latest_summary") or context_summary.get("summary") or "").strip()
        return "\n".join(
            [
                "You are the interactive agent inside the market-research-workflow app.",
                "Answer the user's message naturally in the same language as the user.",
                "For ordinary facts, concepts, translation, writing help, and casual dialogue, answer directly.",
                "Do not expose internal routing, task ids, JSON, parsed fields, or tool metadata unless the user asks.",
                "If the user asks for current/live information, project-private data, file changes, collection, workflow runs, or writing to disk, say what extra read-only lookup or approval-gated action is needed instead of fabricating.",
                "Keep the answer concise and useful.",
                "",
                f"project_key: {project_key or '-'}",
                f"session_counts: {context_counts}",
                f"recent_context: {recent_memory[:1000] if recent_memory else '-'}",
                f"turn_decision: action={turn_decision.get('action')}; mode={turn_decision.get('agent_mode')}; reason={turn_decision.get('reason')}",
                "",
                f"User: {message}",
                "Assistant:",
            ]
        )
