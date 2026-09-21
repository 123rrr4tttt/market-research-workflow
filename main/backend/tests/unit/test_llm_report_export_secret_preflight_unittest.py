from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "check_llm_report_export_secret_preflight.py"
)
SPEC = importlib.util.spec_from_file_location("llm_report_export_secret_preflight", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def secure_ops_kwargs(**overrides):
    values = {
        "env": "production",
        "llm_report_export_token_secret": "x" * 48,
        "llm_report_export_require_artifact_token": True,
        "codex_auth_enabled": True,
        "codex_auth_tokens": "token-1",
        "codex_oauth_enabled": True,
        "codex_oauth_authorize_url": "",
        "codex_oauth_token_url": "",
        "codex_oauth_client_id": "app_test",
        "codex_oauth_client_secret": "",
        "codex_oauth_redirect_uri": "https://example.com/api/v1/codex-auth/callback",
        "codex_oauth_cookie_secure": True,
        "codex_oauth_provider": "openai",
        "codex_oauth_provider_revoke_url": "https://auth.example.com/oauth/revoke",
        "codex_oauth_token_sink_enabled": True,
        "codex_cli_llm_fallback_enabled": True,
        "codex_cli_llm_persistent_enabled": True,
        "codex_cli_llm_ignore_user_config": True,
        "codex_cli_llm_disabled_features": ",".join(
            sorted(preflight.REQUIRED_APP_SERVER_DISABLED_FEATURES)
        ),
        "codex_cli_llm_command": "codex",
        "codex_cli_llm_persistent_start_timeout_seconds": 20,
        "codex_cli_llm_persistent_idle_ttl_seconds": 300,
    }
    values.update(overrides)
    return values


class LlmReportExportSecretPreflightTestCase(unittest.TestCase):
    def test_dev_allows_local_default_secret(self):
        report = preflight.evaluate_llm_report_export_secret_preflight(
            env="dev",
            token_secret=preflight.DEFAULT_LLM_REPORT_EXPORT_TOKEN_SECRET,
            require_artifact_token=True,
        )

        self.assertEqual(report["status"], "ok")
        self.assertFalse(report["production_like"])
        self.assertTrue(report["secret_is_default"])

    def test_production_rejects_default_secret(self):
        report = preflight.evaluate_llm_report_export_secret_preflight(
            env="production",
            token_secret=preflight.DEFAULT_LLM_REPORT_EXPORT_TOKEN_SECRET,
            require_artifact_token=True,
        )

        self.assertEqual(report["status"], "fail")
        self.assertIn("llm_report_export_token_secret_uses_local_default", report["failures"])

    def test_production_rejects_disabled_artifact_token_requirement(self):
        report = preflight.evaluate_llm_report_export_secret_preflight(
            env="staging",
            token_secret="x" * 48,
            require_artifact_token=False,
        )

        self.assertEqual(report["status"], "fail")
        self.assertIn("llm_report_export_require_artifact_token_disabled", report["failures"])

    def test_production_accepts_overridden_secret_and_required_token(self):
        report = preflight.evaluate_llm_report_export_secret_preflight(
            env="prod",
            token_secret="x" * 48,
            require_artifact_token=True,
        )

        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["production_like"])
        self.assertFalse(report["secret_is_default"])

    def test_ops_security_preflight_manifest_categories_are_present(self):
        report = preflight.evaluate_ops_security_preflight(**secure_ops_kwargs())

        self.assertEqual(report["status"], "ok")
        self.assertFalse(report["fail_fast_decision"]["should_fail"])
        categories = {check["category"] for check in report["checks"]}
        self.assertGreaterEqual(
            categories,
            {"auth", "provider_revoke", "app_server_runtime", "security_secret"},
        )

    def test_ops_security_preflight_missing_prod_security_config_fail_fast(self):
        report = preflight.evaluate_ops_security_preflight(
            **secure_ops_kwargs(
                llm_report_export_token_secret=preflight.DEFAULT_LLM_REPORT_EXPORT_TOKEN_SECRET,
                codex_auth_enabled=False,
                codex_auth_tokens="",
                codex_oauth_provider_revoke_url="",
                codex_cli_llm_persistent_enabled=False,
                codex_cli_llm_ignore_user_config=False,
            )
        )

        self.assertEqual(report["status"], "fail")
        self.assertTrue(report["fail_fast_decision"]["should_fail"])
        self.assertEqual(report["fail_fast_decision"]["status"], "fail_fast")
        self.assertIsNotNone(report["fail_fast_decision"]["recommended_command"])
        self.assertIn("llm_report_export_token_secret_uses_local_default", report["failures"])
        self.assertIn("codex_auth_disabled", report["failures"])
        self.assertIn("codex_oauth_provider_revoke_url_missing", report["failures"])
        self.assertIn("codex_app_server_persistent_runtime_disabled", report["failures"])

    def test_ops_security_preflight_records_tsv_has_remediation_for_failures(self):
        report = preflight.evaluate_ops_security_preflight(
            **secure_ops_kwargs(
                codex_oauth_provider_revoke_url="",
            )
        )

        records = preflight.render_preflight_records_tsv(report)

        self.assertIn("provider_revoke\tcodex_oauth_provider_revoke\tfailed\ttrue", records)
        self.assertIn("python3 scripts/configure-external-services.py wizard", records)

    def test_ops_security_preflight_production_like_negative_evidence_records(self):
        scenarios = [
            (
                "default_secret",
                {
                    "llm_report_export_token_secret": preflight.DEFAULT_LLM_REPORT_EXPORT_TOKEN_SECRET,
                },
                "security_secret",
                "llm_report_export_token_secret_uses_local_default",
            ),
            (
                "short_secret",
                {
                    "llm_report_export_token_secret": "short-secret",
                },
                "security_secret",
                "llm_report_export_token_secret_too_short",
            ),
            (
                "artifact_token_requirement_disabled",
                {
                    "llm_report_export_require_artifact_token": False,
                },
                "security_secret",
                "llm_report_export_require_artifact_token_disabled",
            ),
            (
                "provider_revoke_missing",
                {
                    "codex_oauth_provider_revoke_url": "",
                },
                "provider_revoke",
                "codex_oauth_provider_revoke_url_missing",
            ),
            (
                "app_server_unsafe_runtime",
                {
                    "codex_cli_llm_persistent_enabled": False,
                    "codex_cli_llm_ignore_user_config": False,
                    "codex_cli_llm_disabled_features": "",
                    "codex_cli_llm_command": "",
                    "codex_cli_llm_persistent_start_timeout_seconds": 0,
                    "codex_cli_llm_persistent_idle_ttl_seconds": 0,
                },
                "app_server_runtime",
                "codex_app_server_persistent_runtime_disabled",
            ),
        ]

        for env in ("production", "staging", "preprod"):
            for name, overrides, expected_category, expected_failure in scenarios:
                with self.subTest(env=env, scenario=name):
                    report = preflight.evaluate_ops_security_preflight(
                        **secure_ops_kwargs(env=env, **overrides)
                    )
                    checks_by_category = {
                        check["category"]: check for check in report["checks"]
                    }
                    check = checks_by_category[expected_category]
                    records = preflight.render_preflight_records_tsv(report)

                    self.assertEqual(report["status"], "fail")
                    self.assertTrue(report["production_like"])
                    self.assertTrue(report["fail_fast_decision"]["should_fail"])
                    self.assertEqual(report["fail_fast_decision"]["status"], "fail_fast")
                    self.assertEqual(check["status"], "failed")
                    self.assertTrue(check["required"])
                    self.assertTrue(check["should_fail"])
                    self.assertIn(expected_failure, report["failures"])
                    self.assertIn(expected_failure, check["failures"])
                    self.assertIn(f"{expected_category}\t{check['name']}\tfailed\ttrue", records)

    def test_ops_security_preflight_dev_local_test_allows_unsafe_defaults(self):
        for env in ("dev", "local", "test"):
            with self.subTest(env=env):
                report = preflight.evaluate_ops_security_preflight(
                    **secure_ops_kwargs(
                        env=env,
                        llm_report_export_token_secret=preflight.DEFAULT_LLM_REPORT_EXPORT_TOKEN_SECRET,
                        llm_report_export_require_artifact_token=False,
                        codex_auth_enabled=False,
                        codex_auth_tokens="",
                        codex_oauth_provider_revoke_url="",
                        codex_cli_llm_persistent_enabled=False,
                        codex_cli_llm_ignore_user_config=False,
                        codex_cli_llm_disabled_features="",
                        codex_cli_llm_command="",
                        codex_cli_llm_persistent_start_timeout_seconds=0,
                        codex_cli_llm_persistent_idle_ttl_seconds=0,
                    )
                )

                self.assertEqual(report["status"], "ok")
                self.assertFalse(report["production_like"])
                self.assertFalse(report["fail_fast_decision"]["should_fail"])
                self.assertEqual(report["fail_fast_decision"]["status"], "continue")


if __name__ == "__main__":
    unittest.main()
