from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.llm.adapters.langchain_provider import LangChainProviderAdapter
from app.services.llm.codex_cli import CodexCliChatModel, _extract_codex_answer
from app.services.llm.ports import ChatModelOptions


class CodexCliLlmFallbackUnitTest(unittest.TestCase):
    def test_extract_codex_answer_removes_cli_envelope_and_duplicate_final(self):
        raw = """
OpenAI Codex v0.107.0-alpha.5
--------
user
Return JSON
codex
{"ok": true}
{"ok": true}
tokens used
340
"""
        self.assertEqual(_extract_codex_answer(raw), '{"ok": true}')

    def test_openai_adapter_uses_codex_cli_when_api_key_missing_and_auth_available(self):
        adapter = LangChainProviderAdapter()
        with (
            patch("app.services.llm.adapters.langchain_provider.settings.llm_provider", "openai"),
            patch("app.services.llm.adapters.langchain_provider.settings.openai_api_key", None),
            patch("app.services.llm.adapters.langchain_provider.codex_cli_llm_available", return_value=True),
        ):
            chat = adapter.get_chat_model(ChatModelOptions(model="gpt-test"))

        self.assertIsInstance(chat, CodexCliChatModel)

    def test_codex_cli_chat_model_exposes_langchain_like_invoke(self):
        chat = CodexCliChatModel(model="gpt-test")
        with patch("app.services.llm.codex_cli.invoke_codex_cli", return_value="ok") as mocked:
            out = chat.invoke("hello")

        self.assertIsInstance(out, SimpleNamespace)
        self.assertEqual(out.content, "ok")
        mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
