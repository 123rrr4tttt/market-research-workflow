from __future__ import annotations

import asyncio
import json
import os
import queue
from pathlib import Path
import shutil
import tempfile
import threading
import time
import tomllib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.llm.adapters.langchain_provider import LangChainProviderAdapter
from app.services.llm.codex_app_server import (
    CodexAppServerCore,
    _ISOLATED_CODEX_HOME_OWNER_FILE,
    _ISOLATED_CODEX_HOME_PREFIX,
    _cleanup_stale_isolated_codex_homes,
    _isolated_codex_config,
)
from app.services.llm.codex_cli import (
    CodexCliChatModel,
    _extract_codex_answer,
    invoke_codex_cli,
)
from app.services.llm.ports import ChatModelOptions


class CodexCliLlmFallbackUnitTest(unittest.TestCase):
    def _auth_events_from_status(self, status):
        for key in (
            "isolated_codex_home_auth_events",
            "codex_home_auth_events",
            "isolated_auth_events",
        ):
            events = status.get(key)
            if isinstance(events, list):
                return key, events

        isolated_home = status.get("isolated_codex_home")
        if isinstance(isolated_home, dict):
            for key in ("auth_events", "auth_copy_events", "events"):
                events = isolated_home.get(key)
                if isinstance(events, list):
                    return f"isolated_codex_home.{key}", events

        self.fail("status did not expose structured isolated CODEX_HOME auth events")

    def _assert_status_auth_events(
        self,
        status,
        *,
        required_fragments,
        forbidden_fragments,
    ):
        event_key, events = self._auth_events_from_status(status)
        self.assertGreater(len(events), 0, event_key)
        for event in events:
            self.assertIsInstance(event, dict, event_key)

        event_text = json.dumps(events, ensure_ascii=False, sort_keys=True, default=str)
        lowered_event_text = event_text.lower()
        for fragment_options in required_fragments:
            options = (
                fragment_options
                if isinstance(fragment_options, tuple)
                else (fragment_options,)
            )
            self.assertTrue(
                any(str(option).lower() in lowered_event_text for option in options),
                f"{event_key} did not include any of {options!r}: {event_text}",
            )
        for fragment in forbidden_fragments:
            self.assertNotIn(fragment, event_text, event_key)
        return events

    def _cleanup_events_from_status(self, status):
        events = status.get("isolated_codex_home_cleanup_events")
        if isinstance(events, list):
            return "isolated_codex_home_cleanup_events", events
        self.fail("status did not expose structured isolated CODEX_HOME cleanup events")

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

    def test_openai_adapter_uses_codex_cli_when_api_key_missing_and_auth_available(
        self,
    ):
        adapter = LangChainProviderAdapter()
        with (
            patch(
                "app.services.llm.adapters.langchain_provider.settings.llm_provider",
                "openai",
            ),
            patch(
                "app.services.llm.adapters.langchain_provider.settings.openai_api_key",
                None,
            ),
            patch(
                "app.services.llm.adapters.langchain_provider.codex_cli_llm_available",
                return_value=True,
            ),
        ):
            chat = adapter.get_chat_model(ChatModelOptions(model="gpt-test"))

        self.assertIsInstance(chat, CodexCliChatModel)

    def test_openai_adapter_prefers_codex_cli_when_configured_and_auth_available(self):
        adapter = LangChainProviderAdapter()
        with (
            patch(
                "app.services.llm.adapters.langchain_provider.settings.llm_provider",
                "openai",
            ),
            patch(
                "app.services.llm.adapters.langchain_provider.settings.openai_api_key",
                "sk-openai-present",
            ),
            patch(
                "app.services.llm.adapters.langchain_provider.settings.codex_cli_llm_preferred",
                True,
            ),
            patch(
                "app.services.llm.adapters.langchain_provider.codex_cli_llm_available",
                return_value=True,
            ),
        ):
            chat = adapter.get_chat_model(ChatModelOptions(model="glm-test"))

        self.assertIsInstance(chat, CodexCliChatModel)

    def test_openai_adapter_can_opt_out_of_preferred_codex_cli(self):
        adapter = LangChainProviderAdapter()
        with (
            patch(
                "app.services.llm.adapters.langchain_provider.settings.llm_provider",
                "openai",
            ),
            patch(
                "app.services.llm.adapters.langchain_provider.settings.openai_api_key",
                "sk-openai-present",
            ),
            patch(
                "app.services.llm.adapters.langchain_provider.settings.codex_cli_llm_preferred",
                False,
            ),
            patch(
                "app.services.llm.adapters.langchain_provider.codex_cli_llm_available",
                return_value=True,
            ),
        ):
            chat = adapter.get_chat_model(ChatModelOptions(model="gpt-test"))

        self.assertNotIsInstance(chat, CodexCliChatModel)

    def test_codex_cli_invocation_defaults_to_user_model_config(self):
        completed = SimpleNamespace(returncode=0, stdout="codex\nok\n", stderr="")
        with tempfile.TemporaryDirectory() as tmpdir:
            user_config = Path(tmpdir) / "config.toml"
            user_config.write_text(
                "\n".join(
                    [
                        'model = "glm-5.3-zhipu-glm-en"',
                        'model_provider = "codex_model_router_v2"',
                        'model_reasoning_effort = "medium"',
                        "",
                        "[mcp_servers.user]",
                        'command = "user-mcp-secret"',
                        "",
                        "[model_providers.codex_model_router_v2]",
                        'name = "Router"',
                        'base_url = "http://127.0.0.1:15721/v1"',
                        'wire_api = "responses"',
                        "requires_openai_auth = true",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch(
                    "app.services.llm.codex_cli.settings.codex_cli_user_config_path",
                    str(user_config),
                ),
                patch(
                    "app.services.llm.codex_cli.settings.codex_cli_llm_persistent_enabled",
                    False,
                ),
                patch(
                    "app.services.llm.codex_cli.settings.codex_cli_llm_ignore_user_config",
                    False,
                ),
                patch("app.services.llm.codex_cli.settings.codex_cli_llm_model", ""),
                patch(
                    "app.services.llm.codex_cli.settings.codex_cli_llm_reasoning_effort",
                    "",
                ),
                patch(
                    "app.services.llm.codex_cli._resolve_codex_bin",
                    return_value="/tmp/codex",
                ),
                patch(
                    "app.services.llm.codex_cli.has_valid_token_sink", return_value=True
                ),
                patch(
                    "app.services.llm.codex_cli.subprocess.run", return_value=completed
                ) as mocked_run,
            ):
                self.assertEqual(invoke_codex_cli("hello"), "ok")

        args = mocked_run.call_args.args[0]
        model_index = args.index("--model")
        self.assertEqual(args[model_index + 1], "glm-5.3-zhipu-glm-en")
        self.assertNotIn("--ignore-user-config", args)
        self.assertIn('model_reasoning_effort="medium"', args)

    def test_codex_cli_chat_model_exposes_langchain_like_invoke(self):
        chat = CodexCliChatModel(model="gpt-test")
        with patch(
            "app.services.llm.codex_cli.invoke_codex_cli", return_value="ok"
        ) as mocked:
            out = chat.invoke("hello")

        self.assertIsInstance(out, SimpleNamespace)
        self.assertEqual(out.content, "ok")
        mocked.assert_called_once()

    def test_codex_cli_chat_model_resolves_user_upstream_model_alias(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            user_config = Path(tmpdir) / "config.toml"
            user_config.write_text(
                "\n".join(
                    [
                        'model = "glm-5.3-zhipu-glm-en"',
                        'model_provider = "codex_model_router_v2"',
                        "",
                        "[model_providers.codex_model_router_v2]",
                        "models = [",
                        '  { model = "glm-5.3-zhipu-glm-en", upstream_model = "glm-5.3" },',
                        '  { model = "glm-5.3-flash-zhipu-glm-en", upstream_model = "glm-5.3-flash" },',
                        "]",
                    ]
                ),
                encoding="utf-8",
            )
            with patch(
                "app.services.llm.codex_user_config.settings.codex_cli_user_config_path",
                str(user_config),
            ):
                chat = CodexCliChatModel(model="glm-5.3")

        self.assertEqual(chat.model, "glm-5.3-zhipu-glm-en")

    def test_codex_model_falls_back_to_provider_default_without_top_level_model(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            user_config = Path(tmpdir) / "config.toml"
            user_config.write_text(
                "\n".join(
                    [
                        'model_provider = "codex_model_router_v2"',
                        "",
                        "[model_providers.codex_model_router_v2]",
                        "models = [",
                        '  { model = "gpt-5.4", is_default = false },',
                        '  { model = "glm-5.3-zhipu-glm-en", isDefault = true },',
                        "]",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch(
                    "app.services.llm.codex_user_config.settings.codex_cli_user_config_path",
                    str(user_config),
                ),
                patch(
                    "app.services.llm.codex_user_config.settings.codex_cli_llm_model",
                    "",
                ),
            ):
                chat = CodexCliChatModel()

        self.assertEqual(chat.model, "glm-5.3-zhipu-glm-en")

    def test_codex_cli_invocation_uses_embedded_agent_speed_config(self):
        completed = SimpleNamespace(returncode=0, stdout="codex\nok\n", stderr="")
        with (
            patch(
                "app.services.llm.codex_cli._resolve_codex_bin",
                return_value="/tmp/codex",
            ),
            patch("app.services.llm.codex_cli.has_valid_token_sink", return_value=True),
            patch(
                "app.services.llm.codex_cli.subprocess.run", return_value=completed
            ) as mocked_run,
            patch(
                "app.services.llm.codex_cli.settings.codex_cli_llm_persistent_enabled",
                False,
            ),
            patch(
                "app.services.llm.codex_cli.settings.codex_cli_llm_ignore_user_config",
                True,
            ),
            patch(
                "app.services.llm.codex_cli.settings.codex_cli_llm_reasoning_effort",
                "none",
            ),
            patch(
                "app.services.llm.codex_cli.settings.codex_cli_llm_disabled_features",
                "plugins,browser_use",
            ),
            patch("app.services.llm.codex_cli.settings.codex_cli_llm_workdir", "/tmp"),
        ):
            self.assertEqual(
                invoke_codex_cli("hello", model="gpt-test", timeout_seconds=9), "ok"
            )

        args = mocked_run.call_args.args[0]
        self.assertIn("--ignore-user-config", args)
        self.assertIn("--disable", args)
        self.assertIn("plugins", args)
        self.assertIn("-c", args)
        self.assertIn('model_reasoning_effort="none"', args)

    def test_codex_cli_invocation_uses_persistent_core_when_enabled(self):
        fake_core = SimpleNamespace(
            invoke=lambda prompt, **kwargs: SimpleNamespace(content=f"mounted:{prompt}")
        )
        with (
            patch(
                "app.services.llm.codex_cli.settings.codex_cli_llm_persistent_enabled",
                True,
            ),
            patch(
                "app.services.llm.codex_cli.get_persistent_codex_core",
                return_value=fake_core,
            ) as mocked_core,
        ):
            self.assertEqual(
                invoke_codex_cli("hello", model="gpt-test", timeout_seconds=9),
                "mounted:hello",
            )

        mocked_core.assert_called_once()

    def test_codex_cli_invocation_falls_back_if_persistent_core_fails(self):
        completed = SimpleNamespace(
            returncode=0, stdout="codex\nfallback-ok\n", stderr=""
        )
        fake_core = SimpleNamespace(
            invoke=lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("mounted failed")
            )
        )
        with (
            patch(
                "app.services.llm.codex_cli.settings.codex_cli_llm_persistent_enabled",
                True,
            ),
            patch(
                "app.services.llm.codex_cli.get_persistent_codex_core",
                return_value=fake_core,
            ),
            patch(
                "app.services.llm.codex_cli._resolve_codex_bin",
                return_value="/tmp/codex",
            ),
            patch("app.services.llm.codex_cli.has_valid_token_sink", return_value=True),
            patch("app.services.llm.codex_cli.subprocess.run", return_value=completed),
            patch("app.services.llm.codex_cli.settings.codex_cli_llm_workdir", "/tmp"),
        ):
            self.assertEqual(
                invoke_codex_cli("hello", model="gpt-test", timeout_seconds=9),
                "fallback-ok",
            )

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
        captured: dict[str, object] = {}

        def fake_process_factory(*args, **kwargs):
            captured["env"] = kwargs.get("env")
            return fake_process

        core = CodexAppServerCore(
            codex_bin_resolver=lambda: "/tmp/codex",
            workdir_resolver=lambda: "/tmp",
            disabled_features_resolver=lambda: [],
            idle_ttl_seconds=300,
            start_timeout_seconds=1,
            process_factory=fake_process_factory,
            monotonic=lambda: now["value"],
        )

        try:
            self.assertEqual(core._ensure_process(), "ws://127.0.0.1:62222")
            env = captured["env"]
            self.assertIsInstance(env, dict)
            codex_home = Path(env["CODEX_HOME"])  # type: ignore[index]
            now["value"] = 201.0
            self.assertEqual(core._ensure_process(), "ws://127.0.0.1:62222")

            status = core.status()
            self.assertTrue(status["mounted"])
            self.assertEqual(status["process_id"], 321)
            self.assertEqual(status["start_count"], 1)
            self.assertEqual(status["reuse_count"], 1)
            self.assertIsNotNone(status["last_start_duration_seconds"])
            isolated_home = status.get("isolated_codex_home")
            self.assertIsInstance(isolated_home, dict)
            self.assertEqual(isolated_home.get("namespace"), "isolated_codex_home")
            self.assertIsInstance(isolated_home.get("path_hash"), str)
            self.assertTrue(
                str(isolated_home.get("path_hash")).startswith("codex_home:")
            )
            self.assertTrue(isolated_home.get("owner_marker_present"))
            self.assertTrue(isolated_home.get("owner_matches_process"))
            status_text = json.dumps(
                status, ensure_ascii=False, sort_keys=True, default=str
            )
            self.assertNotIn(str(codex_home), status_text)
            self.assertNotIn("auth.json", str(isolated_home))
        finally:
            core.shutdown()

    def test_persistent_core_redacts_endpoint_for_status_and_invocation_display(self):
        raw_endpoint = (
            "ws://127.0.0.1:62223?token=sk-endpoint-display-secret-1234567890"
        )

        class FakeProcess:
            def __init__(self):
                self.pid = 322
                self.stdout = iter([f"listening on: {raw_endpoint}\n"])

            def poll(self):
                return None

            def terminate(self):
                pass

            def wait(self, timeout=None):
                return 0

        core = CodexAppServerCore(
            codex_bin_resolver=lambda: "/tmp/codex",
            workdir_resolver=lambda: "/tmp",
            disabled_features_resolver=lambda: [],
            idle_ttl_seconds=300,
            start_timeout_seconds=1,
            process_factory=lambda *args, **kwargs: FakeProcess(),
        )

        async def fake_invoke_async(**kwargs):
            self.assertEqual(kwargs.get("endpoint"), raw_endpoint)
            return "mounted-ok"

        try:
            self.assertEqual(core._ensure_process(), raw_endpoint)
            status = core.status()
            status_endpoint = status["endpoint"]
            self.assertIsInstance(status_endpoint, str)
            self.assertIn("token=<redacted>", status_endpoint)
            self.assertNotIn("sk-endpoint-display-secret", status_endpoint)
            self.assertNotEqual(status_endpoint, raw_endpoint)

            with patch.object(core, "_invoke_async", side_effect=fake_invoke_async):
                invocation = core.invoke("hello")
            self.assertEqual(invocation.content, "mounted-ok")
            self.assertEqual(invocation.endpoint, status_endpoint)
            self.assertNotIn("sk-endpoint-display-secret", invocation.endpoint)
        finally:
            core.shutdown()

    def test_isolated_codex_home_is_unique_per_core_start(self):
        class FakeProcess:
            def __init__(self, *, pid: int, endpoint: str):
                self.pid = pid
                self.stdout = iter([f"listening on: {endpoint}\n"])
                self.terminated = False

            def poll(self):
                return None if not self.terminated else -15

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                return -15

            def kill(self):
                self.terminated = True

        captured_envs: list[dict[str, object]] = []

        def fake_process_factory(pid: int, endpoint: str):
            def factory(*args, **kwargs):
                captured_envs.append(kwargs.get("env"))
                return FakeProcess(pid=pid, endpoint=endpoint)

            return factory

        cores: list[CodexAppServerCore] = []
        homes: list[Path] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_path = Path(tmpdir) / "auth.json"
            auth_path.write_text('{"tokens":"cli-auth"}', encoding="utf-8")
            with (
                patch(
                    "app.services.llm.codex_app_server.settings.codex_cli_auth_path",
                    str(auth_path),
                ),
                patch(
                    "app.services.llm.codex_app_server.settings.codex_oauth_token_sink_path",
                    str(Path(tmpdir) / "missing-auth-openai.json"),
                ),
            ):
                cores = [
                    CodexAppServerCore(
                        codex_bin_resolver=lambda: "/tmp/codex",
                        workdir_resolver=lambda: "/tmp",
                        disabled_features_resolver=lambda: [],
                        idle_ttl_seconds=300,
                        start_timeout_seconds=1,
                        process_factory=fake_process_factory(
                            701, "ws://127.0.0.1:63335"
                        ),
                    ),
                    CodexAppServerCore(
                        codex_bin_resolver=lambda: "/tmp/codex",
                        workdir_resolver=lambda: "/tmp",
                        disabled_features_resolver=lambda: [],
                        idle_ttl_seconds=300,
                        start_timeout_seconds=1,
                        process_factory=fake_process_factory(
                            702, "ws://127.0.0.1:63336"
                        ),
                    ),
                ]
                try:
                    self.assertEqual(cores[0]._ensure_process(), "ws://127.0.0.1:63335")
                    self.assertEqual(cores[1]._ensure_process(), "ws://127.0.0.1:63336")

                    for env in captured_envs:
                        self.assertIsInstance(env, dict)
                        homes.append(Path(env["CODEX_HOME"]))  # type: ignore[index]

                    self.assertEqual(len(homes), 2)
                    self.assertNotEqual(homes[0], homes[1])
                    for home in homes:
                        self.assertTrue(home.exists())
                        self.assertEqual(
                            (home / "auth.json").read_text(encoding="utf-8"),
                            '{"tokens":"cli-auth"}',
                        )
                        self.assertIn(
                            "[mcp_servers]",
                            (home / "config.toml").read_text(encoding="utf-8"),
                        )
                finally:
                    for core in cores:
                        core.shutdown()
                    for home in homes:
                        shutil.rmtree(home, ignore_errors=True)

    def test_cleanup_shutdown_removes_only_current_core_isolated_codex_home(self):
        class FakeProcess:
            def __init__(self, *, pid: int, endpoint: str):
                self.pid = pid
                self.stdout = iter([f"listening on: {endpoint}\n"])
                self.terminated = False

            def poll(self):
                return None if not self.terminated else -15

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                return -15

            def kill(self):
                self.terminated = True

        captured_envs: list[dict[str, object]] = []

        def fake_process_factory(pid: int, endpoint: str):
            def factory(*args, **kwargs):
                captured_envs.append(kwargs.get("env"))
                return FakeProcess(pid=pid, endpoint=endpoint)

            return factory

        cores: list[CodexAppServerCore] = []
        homes: list[Path] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_path = Path(tmpdir) / "auth.json"
            auth_path.write_text('{"tokens":"cli-auth"}', encoding="utf-8")
            with (
                patch(
                    "app.services.llm.codex_app_server.settings.codex_cli_auth_path",
                    str(auth_path),
                ),
                patch(
                    "app.services.llm.codex_app_server.settings.codex_oauth_token_sink_path",
                    str(Path(tmpdir) / "missing-auth-openai.json"),
                ),
            ):
                cores = [
                    CodexAppServerCore(
                        codex_bin_resolver=lambda: "/tmp/codex",
                        workdir_resolver=lambda: "/tmp",
                        disabled_features_resolver=lambda: [],
                        idle_ttl_seconds=300,
                        start_timeout_seconds=1,
                        process_factory=fake_process_factory(
                            711, "ws://127.0.0.1:63337"
                        ),
                    ),
                    CodexAppServerCore(
                        codex_bin_resolver=lambda: "/tmp/codex",
                        workdir_resolver=lambda: "/tmp",
                        disabled_features_resolver=lambda: [],
                        idle_ttl_seconds=300,
                        start_timeout_seconds=1,
                        process_factory=fake_process_factory(
                            712, "ws://127.0.0.1:63338"
                        ),
                    ),
                ]
                try:
                    self.assertEqual(cores[0]._ensure_process(), "ws://127.0.0.1:63337")
                    self.assertEqual(cores[1]._ensure_process(), "ws://127.0.0.1:63338")

                    for env in captured_envs:
                        self.assertIsInstance(env, dict)
                        homes.append(Path(env["CODEX_HOME"]))  # type: ignore[index]

                    self.assertEqual(len(homes), 2)
                    (homes[0] / "current-core-marker").write_text(
                        "current", encoding="utf-8"
                    )
                    (homes[1] / "other-core-marker").write_text(
                        "other", encoding="utf-8"
                    )

                    cores[0].shutdown()

                    self.assertFalse(homes[0].exists())
                    self.assertTrue(homes[1].exists())
                    self.assertEqual(
                        (homes[1] / "other-core-marker").read_text(encoding="utf-8"),
                        "other",
                    )
                finally:
                    for core in cores:
                        core.shutdown()
                    for home in homes:
                        shutil.rmtree(home, ignore_errors=True)

    def test_cleanup_failure_reports_sanitized_status_without_blocking_process_start_error(
        self,
    ):
        captured: dict[str, object] = {}
        raw_process_marker = "raw-process-start-secret"
        raw_cleanup_marker = "contains secret/path sk-cleanup-secret-token-1234567890"

        def failing_process_factory(*args, **kwargs):
            captured["env"] = kwargs.get("env")
            raise OSError(f"{raw_process_marker} auth=/private/full/auth.json")

        def failing_rmtree(target, *args, **kwargs):
            raise OSError(f"{raw_cleanup_marker} path={target}/auth.json")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            auth_path = tmp_path / "auth.json"
            auth_path.write_text('{"tokens":"cleanup-secret-token"}', encoding="utf-8")
            missing_token_sink = tmp_path / "missing-auth-openai.json"

            core = CodexAppServerCore(
                codex_bin_resolver=lambda: "/tmp/codex",
                workdir_resolver=lambda: "/tmp",
                disabled_features_resolver=lambda: ["plugins"],
                idle_ttl_seconds=300,
                start_timeout_seconds=1,
                process_factory=failing_process_factory,
            )
            with (
                patch(
                    "app.services.llm.codex_app_server.settings.codex_cli_auth_path",
                    str(auth_path),
                ),
                patch(
                    "app.services.llm.codex_app_server.settings.codex_oauth_token_sink_path",
                    str(missing_token_sink),
                ),
                patch(
                    "app.services.llm.codex_app_server.shutil.rmtree",
                    side_effect=failing_rmtree,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "codex app-server process start failed"
                ) as raised:
                    core._ensure_process()

            env = captured["env"]
            self.assertIsInstance(env, dict)
            codex_home = Path(env["CODEX_HOME"])  # type: ignore[index]
            try:
                status = core.status()
                self.assertFalse(status["mounted"])
                self.assertIsNone(status["isolated_codex_home"])
                event_key, events = self._cleanup_events_from_status(status)
                self.assertTrue(
                    any(
                        isinstance(event, dict)
                        and event.get("target") == "isolated_codex_home"
                        and event.get("status") == "cleanup_failed"
                        and event.get("reason") == "OSError"
                        for event in events
                    ),
                    f"{event_key} did not include structured cleanup failure event: {events!r}",
                )
                self.assertTrue(
                    any(
                        "cleanup failed" in str(log).lower() and "OSError" in str(log)
                        for log in status.get("recent_logs", [])
                    ),
                    status.get("recent_logs"),
                )
                leak_surface = "\n".join(
                    [
                        str(raised.exception),
                        repr(raised.exception),
                        str(raised.exception.__cause__ or ""),
                        repr(raised.exception.__cause__),
                        json.dumps(
                            status, ensure_ascii=False, sort_keys=True, default=str
                        ),
                    ]
                )
                for fragment in (
                    raw_process_marker,
                    raw_cleanup_marker,
                    "cleanup-secret-token",
                    str(auth_path),
                    str(codex_home),
                    f"{codex_home}/auth.json",
                    "/private/full/auth.json",
                ):
                    self.assertNotIn(fragment, leak_surface)
            finally:
                shutil.rmtree(codex_home, ignore_errors=True)

    def test_cleanup_ignores_non_project_prefix_and_non_tempdir_parent_without_failure_event(
        self,
    ):
        core = CodexAppServerCore(
            codex_bin_resolver=lambda: "/tmp/codex",
            workdir_resolver=lambda: "/tmp",
            disabled_features_resolver=lambda: [],
            idle_ttl_seconds=300,
            start_timeout_seconds=1,
            process_factory=lambda *args, **kwargs: self.fail(
                "process_factory should not be called"
            ),
        )
        rmtree_calls: list[object] = []

        def fail_if_rmtree_called(target, *args, **kwargs):
            rmtree_calls.append(target)
            raise OSError("should not cleanup ignored path")

        with tempfile.TemporaryDirectory() as tmpdir:
            wrong_prefix = (
                Path(tempfile.gettempdir())
                / "not-market-research-workflow-codex-core-home-secret"
            )
            wrong_parent = (
                Path(tmpdir) / "market-research-workflow-codex-core-home-secret"
            )
            wrong_prefix.mkdir(exist_ok=True)
            wrong_parent.mkdir(exist_ok=True)
            try:
                with patch(
                    "app.services.llm.codex_app_server.shutil.rmtree",
                    side_effect=fail_if_rmtree_called,
                ):
                    core._codex_home = str(wrong_prefix)
                    core.shutdown()
                    core._codex_home = str(wrong_parent)
                    core.shutdown()

                status = core.status()
                event_key, events = self._cleanup_events_from_status(status)
                self.assertEqual(events, [], event_key)
                self.assertEqual(rmtree_calls, [])
            finally:
                shutil.rmtree(wrong_prefix, ignore_errors=True)

    def test_stale_isolated_codex_home_janitor_removes_dead_owner_home_without_leaking_path(
        self,
    ):
        stale_home = Path(
            tempfile.mkdtemp(prefix=f"{_ISOLATED_CODEX_HOME_PREFIX}dead-owner-")
        )
        active_home = Path(
            tempfile.mkdtemp(prefix=f"{_ISOLATED_CODEX_HOME_PREFIX}active-owner-")
        )
        try:
            (stale_home / _ISOLATED_CODEX_HOME_OWNER_FILE).write_text(
                json.dumps({"pid": 991111, "created_at": 1}),
                encoding="utf-8",
            )
            (active_home / _ISOLATED_CODEX_HOME_OWNER_FILE).write_text(
                json.dumps({"pid": 992222, "created_at": 1}),
                encoding="utf-8",
            )
            (stale_home / "auth.json").write_text(
                '{"tokens":"janitor-dead-secret"}', encoding="utf-8"
            )
            (active_home / "auth.json").write_text(
                '{"tokens":"janitor-active-secret"}', encoding="utf-8"
            )

            def fake_process_alive(pid: int) -> bool:
                return pid == 992222

            with patch(
                "app.services.llm.codex_app_server._process_is_alive",
                side_effect=fake_process_alive,
            ):
                events = _cleanup_stale_isolated_codex_homes(
                    tempdir=Path(tempfile.gettempdir()), now=1000
                )

            self.assertFalse(stale_home.exists())
            self.assertTrue(active_home.exists())
            self.assertTrue(
                any(
                    event.get("target") == "isolated_codex_home_janitor"
                    and event.get("status") == "stale_cleanup_succeeded"
                    and event.get("reason") == "owner_process_dead"
                    for event in events
                ),
                events,
            )
            leak_surface = json.dumps(
                events, ensure_ascii=False, sort_keys=True, default=str
            )
            for fragment in (
                str(stale_home),
                str(active_home),
                "janitor-dead-secret",
                "janitor-active-secret",
                "991111",
                "992222",
            ):
                self.assertNotIn(fragment, leak_surface)
        finally:
            shutil.rmtree(stale_home, ignore_errors=True)
            shutil.rmtree(active_home, ignore_errors=True)

    def test_stale_isolated_codex_home_janitor_removes_expired_unmarked_home_only(self):
        expired_home = Path(
            tempfile.mkdtemp(prefix=f"{_ISOLATED_CODEX_HOME_PREFIX}expired-unmarked-")
        )
        fresh_home = Path(
            tempfile.mkdtemp(prefix=f"{_ISOLATED_CODEX_HOME_PREFIX}fresh-unmarked-")
        )
        try:
            old_time = 100
            os_utime = getattr(os, "utime")
            os_utime(expired_home, (old_time, old_time))
            os_utime(fresh_home, (990, 990))

            events = _cleanup_stale_isolated_codex_homes(
                tempdir=Path(tempfile.gettempdir()),
                now=1000,
                max_unmarked_age_seconds=100,
            )

            self.assertFalse(expired_home.exists())
            self.assertTrue(fresh_home.exists())
            self.assertTrue(
                any(
                    event.get("status") == "stale_cleanup_succeeded"
                    and event.get("reason") == "unmarked_expired"
                    for event in events
                ),
                events,
            )
        finally:
            shutil.rmtree(expired_home, ignore_errors=True)
            shutil.rmtree(fresh_home, ignore_errors=True)

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
                patch(
                    "app.services.llm.codex_app_server.settings.codex_cli_auth_path",
                    str(auth_path),
                ),
                patch(
                    "app.services.llm.codex_app_server.settings.codex_oauth_token_sink_path",
                    str(Path(tmpdir) / "missing-auth-openai.json"),
                ),
            ):
                core = CodexAppServerCore(
                    codex_bin_resolver=lambda: "/tmp/codex",
                    workdir_resolver=lambda: "/tmp",
                    disabled_features_resolver=lambda: ["plugins"],
                    idle_ttl_seconds=300,
                    start_timeout_seconds=1,
                    process_factory=fake_process_factory,
                )
                try:
                    self.assertEqual(core._ensure_process(), "ws://127.0.0.1:63333")
                    env = captured["env"]
                    self.assertIsInstance(env, dict)
                    codex_home = Path(env["CODEX_HOME"])  # type: ignore[index]
                    self.assertTrue((codex_home / "auth.json").exists())
                    config_text = (codex_home / "config.toml").read_text(
                        encoding="utf-8"
                    )
                    self.assertIn("[mcp_servers]", config_text)
                    self.assertNotIn("storybook", config_text)
                    self.assertNotIn("6006", config_text)
                finally:
                    core.shutdown()

    def test_isolated_codex_home_skips_unsafe_token_sink_symlink_and_copies_auth_json(
        self,
    ):
        class FakeProcess:
            def __init__(self):
                self.pid = 655
                self.stdout = iter(["listening on: ws://127.0.0.1:63334\n"])

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
            tmp_path = Path(tmpdir)
            auth_path = tmp_path / "auth.json"
            auth_path.write_text('{"tokens":"cli-auth"}', encoding="utf-8")
            token_sink_target = tmp_path / "target-auth-openai.json"
            token_sink_target.write_text(
                '{"tokens":"unsafe-token-sink-target"}', encoding="utf-8"
            )
            token_sink_symlink = tmp_path / "auth_openai.json"
            token_sink_symlink.symlink_to(token_sink_target)

            with (
                patch(
                    "app.services.llm.codex_app_server.settings.codex_cli_auth_path",
                    str(auth_path),
                ),
                patch(
                    "app.services.llm.codex_app_server.settings.codex_oauth_token_sink_path",
                    str(token_sink_symlink),
                ),
            ):
                core = CodexAppServerCore(
                    codex_bin_resolver=lambda: "/tmp/codex",
                    workdir_resolver=lambda: "/tmp",
                    disabled_features_resolver=lambda: ["plugins"],
                    idle_ttl_seconds=300,
                    start_timeout_seconds=1,
                    process_factory=fake_process_factory,
                )
                try:
                    self.assertEqual(core._ensure_process(), "ws://127.0.0.1:63334")
                    env = captured["env"]
                    self.assertIsInstance(env, dict)
                    codex_home = Path(env["CODEX_HOME"])  # type: ignore[index]
                    copied_auth = codex_home / "auth.json"
                    copied_token_sink = codex_home / "auth_openai.json"
                    copied_token_sink_target = codex_home / "target-auth-openai.json"
                    self.assertEqual(
                        copied_auth.read_text(encoding="utf-8"), '{"tokens":"cli-auth"}'
                    )
                    self.assertFalse(copied_token_sink.exists())
                    self.assertFalse(copied_token_sink.is_symlink())
                    self.assertFalse(copied_token_sink_target.exists())
                    self.assertNotIn(
                        "unsafe-token-sink-target",
                        copied_auth.read_text(encoding="utf-8"),
                    )
                    self.assertNotIn(
                        "unsafe-token-sink-target",
                        (codex_home / "config.toml").read_text(encoding="utf-8"),
                    )
                finally:
                    core.shutdown()

    def test_isolated_codex_home_auth_events_report_copy_failure_and_missing_without_tokens(
        self,
    ):
        class FakeProcess:
            def __init__(self):
                self.pid = 656
                self.stdout = iter(["listening on: ws://127.0.0.1:63339\n"])

            def poll(self):
                return None

            def terminate(self):
                pass

            def wait(self, timeout=None):
                return 0

        captured: dict[str, object] = {}

        def fake_process_factory(*args, **kwargs):
            captured["env"] = kwargs.get("env")
            return FakeProcess()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            auth_path = tmp_path / "auth.json"
            auth_path.write_text('{"tokens":"copy-failure-secret"}', encoding="utf-8")
            missing_token_sink = tmp_path / "missing-auth-openai.json"

            def fail_auth_copy(source, destination, *args, **kwargs):
                if Path(source).name == "auth.json":
                    raise OSError("copy denied")
                return shutil.copy2(source, destination, *args, **kwargs)

            with (
                patch(
                    "app.services.llm.codex_app_server.settings.codex_cli_auth_path",
                    str(auth_path),
                ),
                patch(
                    "app.services.llm.codex_app_server.settings.codex_oauth_token_sink_path",
                    str(missing_token_sink),
                ),
                patch(
                    "app.services.llm.codex_app_server.shutil.copy2",
                    side_effect=fail_auth_copy,
                ),
            ):
                core = CodexAppServerCore(
                    codex_bin_resolver=lambda: "/tmp/codex",
                    workdir_resolver=lambda: "/tmp",
                    disabled_features_resolver=lambda: ["plugins"],
                    idle_ttl_seconds=300,
                    start_timeout_seconds=1,
                    process_factory=fake_process_factory,
                )
                try:
                    self.assertEqual(core._ensure_process(), "ws://127.0.0.1:63339")
                    env = captured["env"]
                    self.assertIsInstance(env, dict)
                    codex_home = Path(env["CODEX_HOME"])  # type: ignore[index]
                    self.assertFalse((codex_home / "auth.json").exists())

                    self._assert_status_auth_events(
                        core.status(),
                        required_fragments=(
                            ("failed", "failure", "error"),
                            "auth.json",
                            ("missing", "not_found", "absent"),
                            "missing-auth-openai.json",
                        ),
                        forbidden_fragments=("copy-failure-secret",),
                    )
                finally:
                    core.shutdown()

    def test_isolated_codex_home_auth_events_report_unsafe_symlink_without_tokens(self):
        class FakeProcess:
            def __init__(self):
                self.pid = 657
                self.stdout = iter(["listening on: ws://127.0.0.1:63340\n"])

            def poll(self):
                return None

            def terminate(self):
                pass

            def wait(self, timeout=None):
                return 0

        captured: dict[str, object] = {}

        def fake_process_factory(*args, **kwargs):
            captured["env"] = kwargs.get("env")
            return FakeProcess()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            auth_path = tmp_path / "auth.json"
            auth_path.write_text('{"tokens":"cli-auth-secret"}', encoding="utf-8")
            token_sink_target = tmp_path / "target-auth-openai.json"
            token_sink_target.write_text(
                '{"tokens":"unsafe-token-sink-target"}', encoding="utf-8"
            )
            token_sink_symlink = tmp_path / "auth_openai.json"
            token_sink_symlink.symlink_to(token_sink_target)

            with (
                patch(
                    "app.services.llm.codex_app_server.settings.codex_cli_auth_path",
                    str(auth_path),
                ),
                patch(
                    "app.services.llm.codex_app_server.settings.codex_oauth_token_sink_path",
                    str(token_sink_symlink),
                ),
            ):
                core = CodexAppServerCore(
                    codex_bin_resolver=lambda: "/tmp/codex",
                    workdir_resolver=lambda: "/tmp",
                    disabled_features_resolver=lambda: ["plugins"],
                    idle_ttl_seconds=300,
                    start_timeout_seconds=1,
                    process_factory=fake_process_factory,
                )
                try:
                    self.assertEqual(core._ensure_process(), "ws://127.0.0.1:63340")
                    env = captured["env"]
                    self.assertIsInstance(env, dict)
                    codex_home = Path(env["CODEX_HOME"])  # type: ignore[index]
                    self.assertEqual(
                        (codex_home / "auth.json").read_text(encoding="utf-8"),
                        '{"tokens":"cli-auth-secret"}',
                    )
                    self.assertFalse((codex_home / "auth_openai.json").exists())

                    self._assert_status_auth_events(
                        core.status(),
                        required_fragments=(
                            ("unsafe", "not_safe", "symlink", "skipped", "skip"),
                            "auth_openai.json",
                        ),
                        forbidden_fragments=(
                            "cli-auth-secret",
                            "unsafe-token-sink-target",
                        ),
                    )
                finally:
                    core.shutdown()

    def test_isolated_codex_home_config_write_failure_fail_fast_cleans_home_without_leaks(
        self,
    ):
        process_factory_calls: list[object] = []
        created_homes: list[Path] = []
        original_mkdtemp = tempfile.mkdtemp
        original_write_text = Path.write_text

        def tracked_mkdtemp(*args, **kwargs):
            raw_path = original_mkdtemp(*args, **kwargs)
            created_homes.append(Path(raw_path))
            return raw_path

        def fail_config_write(path_self, *args, **kwargs):
            if Path(path_self).name == "config.toml":
                raise OSError(
                    "write denied for super-secret-token at /full/private/config.toml"
                )
            return original_write_text(path_self, *args, **kwargs)

        def fail_if_process_starts(*args, **kwargs):
            process_factory_calls.append((args, kwargs))
            self.fail(
                "process_factory should not be called when isolated CODEX_HOME config cannot be written"
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            auth_path = tmp_path / "auth.json"
            auth_path.write_text('{"tokens":"super-secret-token"}', encoding="utf-8")
            missing_token_sink = tmp_path / "missing-auth-openai.json"

            core = CodexAppServerCore(
                codex_bin_resolver=lambda: "/tmp/codex",
                workdir_resolver=lambda: "/tmp",
                disabled_features_resolver=lambda: ["plugins"],
                idle_ttl_seconds=300,
                start_timeout_seconds=1,
                process_factory=fail_if_process_starts,
            )
            with (
                patch(
                    "app.services.llm.codex_app_server.settings.codex_cli_auth_path",
                    str(auth_path),
                ),
                patch(
                    "app.services.llm.codex_app_server.settings.codex_oauth_token_sink_path",
                    str(missing_token_sink),
                ),
                patch(
                    "app.services.llm.codex_app_server.tempfile.mkdtemp",
                    side_effect=tracked_mkdtemp,
                ),
                patch(
                    "app.services.llm.codex_app_server.Path.write_text",
                    autospec=True,
                    side_effect=fail_config_write,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "codex isolated home preparation failed"
                ) as raised:
                    core._ensure_process()

            self.assertEqual(process_factory_calls, [])
            status = core.status()
            self.assertFalse(status["mounted"])
            self.assertIsNone(status["isolated_codex_home"])
            self.assertGreater(len(created_homes), 0)
            for codex_home in created_homes:
                self.assertFalse(
                    codex_home.exists(),
                    f"isolated CODEX_HOME was not cleaned: {codex_home}",
                )

            event_key, events = self._auth_events_from_status(status)
            self.assertTrue(
                any(
                    isinstance(event, dict)
                    and event.get("file") == "config.toml"
                    and event.get("status") in {"config_failed", "config_write_failed"}
                    for event in events
                ),
                f"{event_key} did not include structured config failure event: {events!r}",
            )
            leak_surface = "\n".join(
                [
                    str(raised.exception),
                    json.dumps(status, ensure_ascii=False, sort_keys=True, default=str),
                ]
            )
            self.assertNotIn("super-secret-token", leak_surface)
            self.assertNotIn(str(auth_path), leak_surface)
            for codex_home in created_homes:
                self.assertNotIn(str(codex_home), leak_surface)

    def test_endpoint_timeout_fail_fast_cleans_isolated_codex_home_and_preserves_events(
        self,
    ):
        class FakeProcess:
            def __init__(self):
                self.pid = 658
                self.stdout = iter(
                    ["codex app-server started without websocket endpoint\n"]
                )
                self.terminate_calls = 0
                self.kill_calls = 0

            def poll(self):
                return None

            def terminate(self):
                self.terminate_calls += 1

            def wait(self, timeout=None):
                raise TimeoutError("process ignored terminate")

            def kill(self):
                self.kill_calls += 1

        captured: dict[str, object] = {}
        fake_process = FakeProcess()

        def fake_process_factory(*args, **kwargs):
            captured["env"] = kwargs.get("env")
            return fake_process

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            auth_path = tmp_path / "auth.json"
            auth_path.write_text(
                '{"tokens":"endpoint-timeout-secret"}', encoding="utf-8"
            )
            missing_token_sink = tmp_path / "missing-auth-openai.json"

            core = CodexAppServerCore(
                codex_bin_resolver=lambda: "/tmp/codex",
                workdir_resolver=lambda: "/tmp",
                disabled_features_resolver=lambda: ["plugins"],
                idle_ttl_seconds=300,
                start_timeout_seconds=1,
                process_factory=fake_process_factory,
            )
            with (
                patch(
                    "app.services.llm.codex_app_server.settings.codex_cli_auth_path",
                    str(auth_path),
                ),
                patch(
                    "app.services.llm.codex_app_server.settings.codex_oauth_token_sink_path",
                    str(missing_token_sink),
                ),
                patch.object(core._endpoint_queue, "get", side_effect=queue.Empty),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "did not publish a websocket endpoint"
                ) as raised:
                    core._ensure_process()

            env = captured["env"]
            self.assertIsInstance(env, dict)
            codex_home = Path(env["CODEX_HOME"])  # type: ignore[index]
            self.assertFalse(
                codex_home.exists(),
                f"isolated CODEX_HOME was not cleaned: {codex_home}",
            )
            self.assertEqual(fake_process.terminate_calls, 1)
            self.assertEqual(fake_process.kill_calls, 1)

            status = core.status()
            self.assertFalse(status["mounted"])
            self.assertIsNone(status["isolated_codex_home"])
            events = self._assert_status_auth_events(
                status,
                required_fragments=(
                    "auth.json",
                    "copied",
                    "config.toml",
                    "config_written",
                    "endpoint_timeout",
                    "websocket_endpoint_missing",
                ),
                forbidden_fragments=(
                    "endpoint-timeout-secret",
                    str(auth_path),
                    str(codex_home),
                ),
            )
            self.assertTrue(
                any(
                    isinstance(event, dict)
                    and event.get("file") == "app-server"
                    and event.get("status") == "endpoint_timeout"
                    for event in events
                ),
                f"structured endpoint timeout event missing: {events!r}",
            )
            leak_surface = "\n".join(
                [
                    str(raised.exception),
                    json.dumps(status, ensure_ascii=False, sort_keys=True, default=str),
                ]
            )
            self.assertNotIn("endpoint-timeout-secret", leak_surface)
            self.assertNotIn(str(auth_path), leak_surface)
            self.assertNotIn(str(codex_home), leak_surface)

    def test_endpoint_timeout_redacts_sensitive_stdout_from_exception_and_status_recent_logs(
        self,
    ):
        stdout_seen = threading.Event()

        class FakeStdout:
            def __init__(self):
                self._lines: list[str] = []

            def set_lines(self, lines: list[str]):
                self._lines = list(lines)

            def __iter__(self):
                return self

            def __next__(self):
                if not self._lines:
                    raise StopIteration
                line = self._lines.pop(0)
                if "auth debug" in line:
                    stdout_seen.set()
                return line

        class FakeProcess:
            def __init__(self):
                self.pid = 659
                self.stdout = FakeStdout()
                self.terminate_calls = 0
                self.kill_calls = 0

            def poll(self):
                return None

            def terminate(self):
                self.terminate_calls += 1

            def wait(self, timeout=None):
                raise TimeoutError("process ignored terminate")

            def kill(self):
                self.kill_calls += 1

        captured: dict[str, object] = {}
        fake_process = FakeProcess()
        token_like_value = "sk-proj-endpoint-timeout-stdout-secret-1234567890"
        raw_auth_path = "/private/full/auth.json"

        def fake_process_factory(*args, **kwargs):
            env = kwargs.get("env")
            captured["env"] = env
            codex_home = str(env.get("CODEX_HOME")) if isinstance(env, dict) else ""
            fake_process.stdout.set_lines(
                [
                    (
                        "codex app-server auth debug "
                        f"token={token_like_value} "
                        f"Bearer:{token_like_value} "
                        f"auth={raw_auth_path} "
                        f"CODEX_HOME={codex_home} "
                        f"auth_json={codex_home}/auth.json\n"
                    ),
                    "codex app-server waiting for websocket endpoint\n",
                ]
            )
            return fake_process

        def timeout_after_stdout(*args, **kwargs):
            self.assertTrue(
                stdout_seen.wait(timeout=1),
                "fake stdout was not consumed before endpoint timeout",
            )
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                if any("auth debug" in str(log) for log in core._recent_logs):
                    break
                time.sleep(0.01)
            else:
                self.fail(
                    "fake stdout was not appended to recent logs before endpoint timeout"
                )
            raise queue.Empty

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            auth_path = tmp_path / "auth.json"
            auth_path.write_text(f'{{"tokens":"{token_like_value}"}}', encoding="utf-8")
            missing_token_sink = tmp_path / "missing-auth-openai.json"

            core = CodexAppServerCore(
                codex_bin_resolver=lambda: "/tmp/codex",
                workdir_resolver=lambda: "/tmp",
                disabled_features_resolver=lambda: ["plugins"],
                idle_ttl_seconds=300,
                start_timeout_seconds=1,
                process_factory=fake_process_factory,
            )
            with (
                patch(
                    "app.services.llm.codex_app_server.settings.codex_cli_auth_path",
                    str(auth_path),
                ),
                patch(
                    "app.services.llm.codex_app_server.settings.codex_oauth_token_sink_path",
                    str(missing_token_sink),
                ),
                patch.object(
                    core._endpoint_queue, "get", side_effect=timeout_after_stdout
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "did not publish a websocket endpoint"
                ) as raised:
                    core._ensure_process()

            env = captured["env"]
            self.assertIsInstance(env, dict)
            codex_home = Path(env["CODEX_HOME"])  # type: ignore[index]
            self.assertFalse(
                codex_home.exists(),
                f"isolated CODEX_HOME was not cleaned: {codex_home}",
            )
            self.assertEqual(fake_process.terminate_calls, 1)
            self.assertEqual(fake_process.kill_calls, 1)

            status = core.status()
            self.assertFalse(status["mounted"])
            self.assertIsNone(status["isolated_codex_home"])
            self.assertTrue(
                any(
                    "endpoint timeout" in str(log).lower()
                    for log in status.get("recent_logs", [])
                ),
                status.get("recent_logs"),
            )
            status_text = json.dumps(
                status, ensure_ascii=False, sort_keys=True, default=str
            )
            leak_surface = "\n".join([str(raised.exception), status_text])
            forbidden_fragments = (
                token_like_value,
                raw_auth_path,
                str(auth_path),
                str(codex_home),
                f"{codex_home}/auth.json",
            )
            for fragment in forbidden_fragments:
                self.assertNotIn(fragment, leak_surface)
            self.assertTrue(
                any(
                    marker in leak_surface.lower()
                    for marker in (
                        "redacted",
                        "endpoint timeout",
                        "websocket_endpoint_missing",
                    )
                ),
                leak_surface,
            )

    def test_process_factory_failure_fail_fast_cleans_isolated_codex_home_and_preserves_sanitized_events(
        self,
    ):
        captured: dict[str, object] = {}
        process_factory_calls: list[tuple[object, object]] = []
        raw_exception_marker = "raw-process-factory-message"

        def failing_process_factory(*args, **kwargs):
            process_factory_calls.append((args, kwargs))
            captured["env"] = kwargs.get("env")
            env = kwargs.get("env") if isinstance(kwargs.get("env"), dict) else {}
            raise OSError(
                f"{raw_exception_marker} process-factory-secret "
                f"auth=/private/full/auth.json home={env.get('CODEX_HOME')}"
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            auth_path = tmp_path / "auth.json"
            auth_path.write_text(
                '{"tokens":"process-factory-secret"}', encoding="utf-8"
            )
            missing_token_sink = tmp_path / "missing-auth-openai.json"

            core = CodexAppServerCore(
                codex_bin_resolver=lambda: "/tmp/codex",
                workdir_resolver=lambda: "/tmp",
                disabled_features_resolver=lambda: ["plugins"],
                idle_ttl_seconds=300,
                start_timeout_seconds=1,
                process_factory=failing_process_factory,
            )
            with (
                patch(
                    "app.services.llm.codex_app_server.settings.codex_cli_auth_path",
                    str(auth_path),
                ),
                patch(
                    "app.services.llm.codex_app_server.settings.codex_oauth_token_sink_path",
                    str(missing_token_sink),
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "codex app-server process start failed"
                ) as raised:
                    core._ensure_process()

            self.assertEqual(len(process_factory_calls), 1)
            env = captured["env"]
            self.assertIsInstance(env, dict)
            codex_home = Path(env["CODEX_HOME"])  # type: ignore[index]
            self.assertFalse(
                codex_home.exists(),
                f"isolated CODEX_HOME was not cleaned: {codex_home}",
            )

            status = core.status()
            self.assertFalse(status["mounted"])
            self.assertIsNone(status["isolated_codex_home"])
            events = self._assert_status_auth_events(
                status,
                required_fragments=(
                    "auth.json",
                    "copied",
                    "missing-auth-openai.json",
                    "missing",
                    "config.toml",
                    "config_written",
                    "process_start_failed",
                    "OSError",
                ),
                forbidden_fragments=(
                    "process-factory-secret",
                    str(auth_path),
                    str(codex_home),
                    raw_exception_marker,
                    "/private/full/auth.json",
                ),
            )
            self.assertTrue(
                any(
                    isinstance(event, dict)
                    and event.get("file") == "app-server"
                    and event.get("status") == "process_start_failed"
                    and event.get("reason") == "OSError"
                    for event in events
                ),
                f"structured process start failure event missing: {events!r}",
            )
            leak_surface = "\n".join(
                [
                    str(raised.exception),
                    repr(raised.exception),
                    str(raised.exception.__cause__ or ""),
                    repr(raised.exception.__cause__),
                    json.dumps(status, ensure_ascii=False, sort_keys=True, default=str),
                ]
            )
            self.assertNotIn("process-factory-secret", leak_surface)
            self.assertNotIn(str(auth_path), leak_surface)
            self.assertNotIn(str(codex_home), leak_surface)
            self.assertNotIn(raw_exception_marker, leak_surface)
            self.assertNotIn("/private/full/auth.json", leak_surface)

    def test_isolated_codex_config_disables_tool_mounting_features(self):
        config_text = _isolated_codex_config()
        self.assertIn("plugins = false", config_text)
        self.assertIn("apps = false", config_text)
        self.assertIn("tool_search = false", config_text)
        self.assertIn("[mcp_servers]", config_text)
        self.assertNotIn("127.0.0.1:6006", config_text)

    def test_isolated_codex_config_inherits_selected_user_model_provider_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            user_config = Path(tmpdir) / "config.toml"
            user_config.write_text(
                "\n".join(
                    [
                        'model = "glm-5.3-zhipu-glm-en"',
                        'model_provider = "codex_model_router_v2"',
                        'model_reasoning_effort = "medium"',
                        "",
                        "[mcp_servers.user]",
                        'command = "user-mcp-secret"',
                        "",
                        "[model_providers.codex_model_router_v2]",
                        'name = "Router"',
                        'base_url = "http://127.0.0.1:15721/v1"',
                        'wire_api = "responses"',
                        "requires_openai_auth = true",
                        'api_key = "provider-secret"',
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch(
                    "app.services.llm.codex_app_server.settings.codex_cli_user_config_path",
                    str(user_config),
                ),
                patch(
                    "app.services.llm.codex_app_server.settings.codex_cli_llm_model", ""
                ),
                patch(
                    "app.services.llm.codex_app_server.settings.codex_cli_llm_reasoning_effort",
                    "",
                ),
            ):
                config_text = _isolated_codex_config()

        parsed = tomllib.loads(config_text)
        self.assertEqual(parsed["model"], "glm-5.3-zhipu-glm-en")
        self.assertEqual(parsed["model_provider"], "codex_model_router_v2")
        self.assertEqual(parsed["model_reasoning_effort"], "medium")
        provider = parsed["model_providers"]["codex_model_router_v2"]
        self.assertEqual(provider["base_url"], "http://127.0.0.1:15721/v1")
        self.assertEqual(provider["wire_api"], "responses")
        self.assertTrue(provider["requires_openai_auth"])
        self.assertEqual(parsed["features"]["plugins"], False)
        self.assertNotIn("user-mcp-secret", config_text)

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
            patch(
                "app.services.llm.codex_app_server.settings.codex_cli_llm_reuse_thread",
                True,
            ),
        ):
            first = asyncio.run(
                core._ensure_thread_id(object(), model="gpt-test", timeout_seconds=5)
            )
            second = asyncio.run(
                core._ensure_thread_id(object(), model="gpt-test", timeout_seconds=5)
            )
            status = core.status()

        self.assertEqual(first, "thread-1")
        self.assertEqual(second, "thread-1")
        self.assertEqual([method for method, _params in calls], ["thread/start"])
        self.assertTrue(status["thread_reuse_enabled"])
        self.assertEqual(status["thread_reuse_scope"], "workdir_model")
        self.assertIsNone(status["thread_key_hash"])
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
            patch(
                "app.services.llm.codex_app_server.settings.codex_cli_llm_reuse_thread",
                False,
            ),
        ):
            first = asyncio.run(
                core._ensure_thread_id(object(), model="gpt-test", timeout_seconds=5)
            )
            second = asyncio.run(
                core._ensure_thread_id(object(), model="gpt-test", timeout_seconds=5)
            )

        self.assertEqual(first, "thread-1")
        self.assertEqual(second, "thread-2")
        self.assertEqual(
            [method for method, _params in calls], ["thread/start", "thread/start"]
        )
        status = core.status()
        self.assertFalse(status["thread_reuse_enabled"])
        self.assertEqual(status["thread_reuse_scope"], "disabled")
        self.assertIsNone(status["thread_key_hash"])
        self.assertEqual(status["thread_start_count"], 2)
        self.assertEqual(status["thread_reuse_count"], 0)


if __name__ == "__main__":
    unittest.main()
