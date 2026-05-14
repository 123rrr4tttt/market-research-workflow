from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.llm.adapters.langchain_provider import LangChainProviderAdapter
from app.services.llm.codex_app_server import CodexAppServerCore, _isolated_codex_config
from app.services.llm.codex_cli import CodexCliChatModel, _extract_codex_answer, invoke_codex_cli
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

    def test_codex_cli_invocation_uses_embedded_agent_speed_config(self):
        completed = SimpleNamespace(returncode=0, stdout="codex\nok\n", stderr="")
        with (
            patch("app.services.llm.codex_cli._resolve_codex_bin", return_value="/tmp/codex"),
            patch("app.services.llm.codex_cli.has_valid_token_sink", return_value=True),
            patch("app.services.llm.codex_cli.subprocess.run", return_value=completed) as mocked_run,
            patch("app.services.llm.codex_cli.settings.codex_cli_llm_persistent_enabled", False),
            patch("app.services.llm.codex_cli.settings.codex_cli_llm_ignore_user_config", True),
            patch("app.services.llm.codex_cli.settings.codex_cli_llm_reasoning_effort", "none"),
            patch("app.services.llm.codex_cli.settings.codex_cli_llm_disabled_features", "plugins,browser_use"),
            patch("app.services.llm.codex_cli.settings.codex_cli_llm_workdir", "/tmp"),
        ):
            self.assertEqual(invoke_codex_cli("hello", model="gpt-test", timeout_seconds=9), "ok")

        args = mocked_run.call_args.args[0]
        self.assertIn("--ignore-user-config", args)
        self.assertIn("--disable", args)
        self.assertIn("plugins", args)
        self.assertIn("-c", args)
        self.assertIn('model_reasoning_effort="none"', args)

    def test_codex_cli_invocation_uses_persistent_core_when_enabled(self):
        fake_core = SimpleNamespace(invoke=lambda prompt, **kwargs: SimpleNamespace(content=f"mounted:{prompt}"))
        with (
            patch("app.services.llm.codex_cli.settings.codex_cli_llm_persistent_enabled", True),
            patch("app.services.llm.codex_cli.get_persistent_codex_core", return_value=fake_core) as mocked_core,
        ):
            self.assertEqual(invoke_codex_cli("hello", model="gpt-test", timeout_seconds=9), "mounted:hello")

        mocked_core.assert_called_once()

    def test_codex_cli_invocation_falls_back_if_persistent_core_fails(self):
        completed = SimpleNamespace(returncode=0, stdout="codex\nfallback-ok\n", stderr="")
        fake_core = SimpleNamespace(invoke=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("mounted failed")))
        with (
            patch("app.services.llm.codex_cli.settings.codex_cli_llm_persistent_enabled", True),
            patch("app.services.llm.codex_cli.get_persistent_codex_core", return_value=fake_core),
            patch("app.services.llm.codex_cli._resolve_codex_bin", return_value="/tmp/codex"),
            patch("app.services.llm.codex_cli.has_valid_token_sink", return_value=True),
            patch("app.services.llm.codex_cli.subprocess.run", return_value=completed),
            patch("app.services.llm.codex_cli.settings.codex_cli_llm_workdir", "/tmp"),
        ):
            self.assertEqual(invoke_codex_cli("hello", model="gpt-test", timeout_seconds=9), "fallback-ok")

    def test_persistent_core_idle_shutdown_terminates_process(self):
        class FakeProcess:
            def __init__(self):
                self.pid = 123
                self.stdout = iter(["listening on: ws://127.0.0.1:61111\n"])
                self.terminated = False

            def poll(self):
                return None if not self.terminated else -15

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                return -15

            def kill(self):
                self.terminated = True

        fake_process = FakeProcess()
        now = {"value": 100.0}
        core = CodexAppServerCore(
            codex_bin_resolver=lambda: "/tmp/codex",
            workdir_resolver=lambda: "/tmp",
            disabled_features_resolver=lambda: [],
            idle_ttl_seconds=1,
            start_timeout_seconds=1,
            process_factory=lambda *args, **kwargs: fake_process,
            monotonic=lambda: now["value"],
        )

        endpoint = core._ensure_process()
        self.assertEqual(endpoint, "ws://127.0.0.1:61111")
        self.assertFalse(fake_process.terminated)

        now["value"] = 102.0
        self.assertTrue(core._reap_idle_once())

        self.assertTrue(fake_process.terminated)

    def test_persistent_core_status_reports_start_and_reuse_metrics(self):
        class FakeProcess:
            def __init__(self):
                self.pid = 321
                self.stdout = iter(["listening on: ws://127.0.0.1:62222\n"])

            def poll(self):
                return None

            def terminate(self):
                pass

            def wait(self, timeout=None):
                return 0

        fake_process = FakeProcess()
        now = {"value": 200.0}
        core = CodexAppServerCore(
            codex_bin_resolver=lambda: "/tmp/codex",
            workdir_resolver=lambda: "/tmp",
            disabled_features_resolver=lambda: [],
            idle_ttl_seconds=300,
            start_timeout_seconds=1,
            process_factory=lambda *args, **kwargs: fake_process,
            monotonic=lambda: now["value"],
        )

        self.assertEqual(core._ensure_process(), "ws://127.0.0.1:62222")
        now["value"] = 201.0
        self.assertEqual(core._ensure_process(), "ws://127.0.0.1:62222")

        status = core.status()
        self.assertTrue(status["mounted"])
        self.assertEqual(status["process_id"], 321)
        self.assertEqual(status["start_count"], 1)
        self.assertEqual(status["reuse_count"], 1)
        self.assertIsNotNone(status["last_start_duration_seconds"])
        self.assertIn("isolated_codex_home", status)

    def test_persistent_core_uses_isolated_codex_home_without_global_mcp(self):
        class FakeProcess:
            def __init__(self):
                self.pid = 654
                self.stdout = iter(["listening on: ws://127.0.0.1:63333\n"])

            def poll(self):
                return None

            def terminate(self):
                pass

            def wait(self, timeout=None):
                return 0

        captured: dict[str, object] = {}

        def fake_process_factory(*args, **kwargs):
            captured["args"] = args[0]
            captured["env"] = kwargs.get("env")
            return FakeProcess()

        with tempfile.TemporaryDirectory() as tmpdir:
            auth_path = Path(tmpdir) / "auth.json"
            auth_path.write_text('{"tokens":true}', encoding="utf-8")
            with (
                patch("app.services.llm.codex_app_server.settings.codex_cli_auth_path", str(auth_path)),
                patch("app.services.llm.codex_app_server.settings.codex_oauth_token_sink_path", str(Path(tmpdir) / "missing-auth-openai.json")),
            ):
                core = CodexAppServerCore(
                    codex_bin_resolver=lambda: "/tmp/codex",
                    workdir_resolver=lambda: "/tmp",
                    disabled_features_resolver=lambda: ["plugins"],
                    idle_ttl_seconds=300,
                    start_timeout_seconds=1,
                    process_factory=fake_process_factory,
                )
                self.assertEqual(core._ensure_process(), "ws://127.0.0.1:63333")

        env = captured["env"]
        self.assertIsInstance(env, dict)
        codex_home = Path(env["CODEX_HOME"])  # type: ignore[index]
        self.assertTrue((codex_home / "auth.json").exists())
        config_text = (codex_home / "config.toml").read_text(encoding="utf-8")
        self.assertIn("[mcp_servers]", config_text)
        self.assertNotIn("storybook", config_text)
        self.assertNotIn("6006", config_text)

    def test_isolated_codex_config_disables_tool_mounting_features(self):
        config_text = _isolated_codex_config()
        self.assertIn("plugins = false", config_text)
        self.assertIn("apps = false", config_text)
        self.assertIn("tool_search = false", config_text)
        self.assertIn("[mcp_servers]", config_text)
        self.assertNotIn("127.0.0.1:6006", config_text)

    def test_persistent_core_reuses_app_server_thread(self):
        core = CodexAppServerCore(
            codex_bin_resolver=lambda: "/tmp/codex",
            workdir_resolver=lambda: "/tmp",
            disabled_features_resolver=lambda: [],
            idle_ttl_seconds=300,
            start_timeout_seconds=1,
        )
        calls: list[tuple[str, dict]] = []

        async def fake_request(ws, *, request_id, method, params, timeout_seconds):
            calls.append((method, dict(params)))
            return {"thread": {"id": "thread-1"}}

        with (
            patch.object(core, "_request", side_effect=fake_request),
            patch("app.services.llm.codex_app_server.settings.codex_cli_llm_reuse_thread", True),
        ):
            first = asyncio.run(core._ensure_thread_id(object(), model="gpt-test", timeout_seconds=5))
            second = asyncio.run(core._ensure_thread_id(object(), model="gpt-test", timeout_seconds=5))

        self.assertEqual(first, "thread-1")
        self.assertEqual(second, "thread-1")
        self.assertEqual([method for method, _params in calls], ["thread/start"])
        status = core.status()
        self.assertEqual(status["thread_start_count"], 1)
        self.assertEqual(status["thread_reuse_count"], 1)

    def test_persistent_core_uses_fresh_thread_by_default(self):
        core = CodexAppServerCore(
            codex_bin_resolver=lambda: "/tmp/codex",
            workdir_resolver=lambda: "/tmp",
            disabled_features_resolver=lambda: [],
            idle_ttl_seconds=300,
            start_timeout_seconds=1,
        )
        calls: list[tuple[str, dict]] = []

        async def fake_request(ws, *, request_id, method, params, timeout_seconds):
            calls.append((method, dict(params)))
            return {"thread": {"id": f"thread-{len(calls)}"}}

        with (
            patch.object(core, "_request", side_effect=fake_request),
            patch("app.services.llm.codex_app_server.settings.codex_cli_llm_reuse_thread", False),
        ):
            first = asyncio.run(core._ensure_thread_id(object(), model="gpt-test", timeout_seconds=5))
            second = asyncio.run(core._ensure_thread_id(object(), model="gpt-test", timeout_seconds=5))

        self.assertEqual(first, "thread-1")
        self.assertEqual(second, "thread-2")
        self.assertEqual([method for method, _params in calls], ["thread/start", "thread/start"])
        status = core.status()
        self.assertEqual(status["thread_start_count"], 2)
        self.assertEqual(status["thread_reuse_count"], 0)


if __name__ == "__main__":
    unittest.main()
