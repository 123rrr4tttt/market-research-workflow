#!/usr/bin/env python3
"""Preflight gate for LLM report export token production safety."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_LLM_REPORT_EXPORT_TOKEN_SECRET = "mrw-local-llm-report-export-token-v1"
PRODUCTION_LIKE_ENVS = {"prod", "production", "stage", "staging", "preprod", "pre-production"}
SECURITY_PREFLIGHT_REMEDIATION_COMMAND = (
    "python3 scripts/configure-external-services.py wizard && "
    "python3 main/backend/scripts/check_llm_report_export_secret_preflight.py"
)
REQUIRED_APP_SERVER_DISABLED_FEATURES = {
    "apps",
    "browser_use",
    "chronicle",
    "memories",
    "multi_agent",
    "plugins",
    "realtime_conversation",
    "tool_search",
    "tool_suggest",
}


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _normalize_env(value: str | None) -> str:
    return str(value or "dev").strip().lower() or "dev"


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _split_csv(value: Any) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for item in str(value or "").split(","):
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        items.append(normalized)
        seen.add(normalized)
    return items


def _redacted_configured(value: str | None) -> bool:
    return bool(str(value or "").strip())


def _check(
    *,
    category: str,
    name: str,
    failed: bool,
    required: bool,
    failure_detail: str,
    passed_detail: str,
    recommended_command: str = SECURITY_PREFLIGHT_REMEDIATION_COMMAND,
    failures: list[str] | None = None,
) -> dict[str, Any]:
    should_fail = bool(required and failed)
    return {
        "category": category,
        "name": name,
        "status": "failed" if failed else "passed",
        "required": bool(required),
        "should_fail": should_fail,
        "recommended_command": recommended_command if should_fail else None,
        "detail": failure_detail if failed else passed_detail,
        "failures": list(failures or []),
    }


def evaluate_llm_report_export_secret_preflight(
    *,
    env: str | None,
    token_secret: str | None,
    require_artifact_token: Any,
) -> dict[str, Any]:
    normalized_env = _normalize_env(env)
    secret = str(token_secret or "").strip()
    production_like = normalized_env in PRODUCTION_LIKE_ENVS
    require_token = _normalize_bool(require_artifact_token)
    failures: list[str] = []

    if production_like:
        if not secret:
            failures.append("llm_report_export_token_secret_missing")
        if secret == DEFAULT_LLM_REPORT_EXPORT_TOKEN_SECRET:
            failures.append("llm_report_export_token_secret_uses_local_default")
        if secret and len(secret) < 32:
            failures.append("llm_report_export_token_secret_too_short")
        if not require_token:
            failures.append("llm_report_export_require_artifact_token_disabled")

    return {
        "status": "fail" if failures else "ok",
        "gate_type": "llm_report_export_secret_preflight",
        "env": normalized_env,
        "production_like": production_like,
        "require_artifact_token": require_token,
        "secret_configured": bool(secret),
        "secret_is_default": secret == DEFAULT_LLM_REPORT_EXPORT_TOKEN_SECRET,
        "secret_length": len(secret),
        "failures": failures,
        "should_fail": bool(failures),
        "recommended_command": SECURITY_PREFLIGHT_REMEDIATION_COMMAND if failures else None,
    }


def evaluate_ops_security_preflight(
    *,
    env: str | None,
    llm_report_export_token_secret: str | None,
    llm_report_export_require_artifact_token: Any,
    codex_auth_enabled: Any,
    codex_auth_tokens: str | None,
    codex_oauth_enabled: Any,
    codex_oauth_authorize_url: str | None,
    codex_oauth_token_url: str | None,
    codex_oauth_client_id: str | None,
    codex_oauth_client_secret: str | None,
    codex_oauth_redirect_uri: str | None,
    codex_oauth_cookie_secure: Any,
    codex_oauth_provider: str | None,
    codex_oauth_provider_revoke_url: str | None,
    codex_oauth_token_sink_enabled: Any,
    codex_cli_llm_fallback_enabled: Any,
    codex_cli_llm_persistent_enabled: Any,
    codex_cli_llm_ignore_user_config: Any,
    codex_cli_llm_disabled_features: str | None,
    codex_cli_llm_command: str | None,
    codex_cli_llm_persistent_start_timeout_seconds: Any,
    codex_cli_llm_persistent_idle_ttl_seconds: Any,
) -> dict[str, Any]:
    normalized_env = _normalize_env(env)
    production_like = normalized_env in PRODUCTION_LIKE_ENVS
    oauth_enabled = _normalize_bool(codex_oauth_enabled)
    auth_enabled = _normalize_bool(codex_auth_enabled)
    token_auth_configured = _redacted_configured(codex_auth_tokens)
    token_sink_enabled = _normalize_bool(codex_oauth_token_sink_enabled)
    provider = str(codex_oauth_provider or "openai").strip().lower() or "openai"
    authorize_url = str(codex_oauth_authorize_url or "").strip()
    token_url = str(codex_oauth_token_url or "").strip()
    client_id = str(codex_oauth_client_id or "").strip()
    client_secret = str(codex_oauth_client_secret or "").strip()
    redirect_uri = str(codex_oauth_redirect_uri or "").strip()
    provider_revoke_url = str(codex_oauth_provider_revoke_url or "").strip()
    fallback_enabled = _normalize_bool(codex_cli_llm_fallback_enabled)
    persistent_enabled = _normalize_bool(codex_cli_llm_persistent_enabled)
    ignore_user_config = _normalize_bool(codex_cli_llm_ignore_user_config)
    disabled_features = set(_split_csv(codex_cli_llm_disabled_features))
    missing_disabled_features = sorted(REQUIRED_APP_SERVER_DISABLED_FEATURES - disabled_features)
    app_server_command = str(codex_cli_llm_command or "").strip()
    start_timeout = _normalize_int(codex_cli_llm_persistent_start_timeout_seconds)
    idle_ttl = _normalize_int(codex_cli_llm_persistent_idle_ttl_seconds)

    llm_report = evaluate_llm_report_export_secret_preflight(
        env=normalized_env,
        token_secret=llm_report_export_token_secret,
        require_artifact_token=llm_report_export_require_artifact_token,
    )
    checks: list[dict[str, Any]] = [
        _check(
            category="security_secret",
            name="llm_report_export_token",
            failed=bool(llm_report["failures"]),
            required=production_like,
            failures=list(llm_report["failures"]),
            failure_detail=";".join(llm_report["failures"]) or "llm report export token is unsafe",
            passed_detail=(
                "llm report export token is production-safe"
                if production_like
                else "non-production environment allows local export token defaults"
            ),
        )
    ]

    auth_failures: list[str] = []
    if production_like:
        if not auth_enabled:
            auth_failures.append("codex_auth_disabled")
        if not token_auth_configured and not (oauth_enabled and token_sink_enabled):
            auth_failures.append("codex_auth_missing_token_or_oauth_sink")
        if oauth_enabled:
            if provider != "openai" and not authorize_url:
                auth_failures.append("codex_oauth_authorize_url_missing")
            if provider != "openai" and not token_url:
                auth_failures.append("codex_oauth_token_url_missing")
            if not client_id:
                auth_failures.append("codex_oauth_client_id_missing")
            if provider != "openai" and not client_secret:
                auth_failures.append("codex_oauth_client_secret_missing")
            if not redirect_uri:
                auth_failures.append("codex_oauth_redirect_uri_missing")
            if not _normalize_bool(codex_oauth_cookie_secure):
                auth_failures.append("codex_oauth_cookie_secure_disabled")
    checks.append(
        _check(
            category="auth",
            name="codex_auth_runtime",
            failed=bool(auth_failures),
            required=production_like,
            failures=auth_failures,
            failure_detail=";".join(auth_failures) or "codex auth runtime is not production-safe",
            passed_detail=(
                "codex auth runtime is production-safe"
                if production_like
                else "non-production environment allows relaxed codex auth defaults"
            ),
        )
    )

    revoke_failures: list[str] = []
    if production_like and oauth_enabled and not provider_revoke_url:
        revoke_failures.append("codex_oauth_provider_revoke_url_missing")
    checks.append(
        _check(
            category="provider_revoke",
            name="codex_oauth_provider_revoke",
            failed=bool(revoke_failures),
            required=production_like and oauth_enabled,
            failures=revoke_failures,
            failure_detail=";".join(revoke_failures) or "provider revoke endpoint is missing",
            passed_detail=(
                "provider revoke endpoint configured"
                if oauth_enabled
                else "oauth disabled; provider revoke not required"
            ),
        )
    )

    app_server_failures: list[str] = []
    if production_like and fallback_enabled:
        if not persistent_enabled:
            app_server_failures.append("codex_app_server_persistent_runtime_disabled")
        if not app_server_command:
            app_server_failures.append("codex_app_server_command_missing")
        if not ignore_user_config:
            app_server_failures.append("codex_app_server_ignore_user_config_disabled")
        if missing_disabled_features:
            app_server_failures.append(
                "codex_app_server_disabled_features_missing:" + ",".join(missing_disabled_features)
            )
        if start_timeout <= 0:
            app_server_failures.append("codex_app_server_start_timeout_invalid")
        if idle_ttl <= 0:
            app_server_failures.append("codex_app_server_idle_ttl_invalid")
    checks.append(
        _check(
            category="app_server_runtime",
            name="codex_app_server_runtime",
            failed=bool(app_server_failures),
            required=production_like and fallback_enabled,
            failures=app_server_failures,
            failure_detail=";".join(app_server_failures) or "codex app-server runtime is not production-safe",
            passed_detail=(
                "codex app-server runtime is production-safe"
                if fallback_enabled
                else "codex cli fallback disabled; app-server runtime not required"
            ),
        )
    )

    failed_required = [check for check in checks if check["should_fail"]]
    status = "fail" if failed_required else "ok"
    return {
        "status": status,
        "gate_type": "ops_security_preflight",
        "env": normalized_env,
        "production_like": production_like,
        "checks": checks,
        "failures": [failure for check in checks for failure in check["failures"]],
        "safe_config": {
            "codex_auth_enabled": auth_enabled,
            "codex_auth_tokens_configured": token_auth_configured,
            "codex_oauth_enabled": oauth_enabled,
            "codex_oauth_token_sink_enabled": token_sink_enabled,
            "codex_oauth_provider": provider,
            "codex_oauth_provider_revoke_url_configured": bool(provider_revoke_url),
            "codex_cli_llm_fallback_enabled": fallback_enabled,
            "codex_cli_llm_persistent_enabled": persistent_enabled,
            "codex_cli_llm_ignore_user_config": ignore_user_config,
            "codex_cli_llm_disabled_features": sorted(disabled_features),
        },
        "fail_fast_decision": {
            "should_fail": bool(failed_required),
            "status": "fail_fast" if failed_required else "continue",
            "reasons": [f"{check['category']}:{check['name']}" for check in failed_required],
            "recommended_command": SECURITY_PREFLIGHT_REMEDIATION_COMMAND if failed_required else None,
        },
        "recommended_command": SECURITY_PREFLIGHT_REMEDIATION_COMMAND if failed_required else None,
    }


def render_preflight_records_tsv(report: dict[str, Any]) -> str:
    rows: list[str] = []
    for check in report.get("checks", []):
        if not isinstance(check, dict):
            continue
        fields = [
            str(check.get("category") or "security"),
            str(check.get("name") or "unknown"),
            str(check.get("status") or "unknown"),
            "true" if check.get("required") else "false",
            str(check.get("recommended_command") or ""),
            str(check.get("detail") or ""),
        ]
        rows.append("\t".join(field.replace("\t", " ").replace("\n", " ") for field in fields))
    return "\n".join(rows)


def _settings_values() -> dict[str, Any]:
    sys.path.insert(0, str(_backend_root()))
    from app.settings.config import settings  # noqa: PLC0415

    keys = [
        "env",
        "llm_report_export_token_secret",
        "llm_report_export_require_artifact_token",
        "codex_auth_enabled",
        "codex_auth_tokens",
        "codex_oauth_enabled",
        "codex_oauth_authorize_url",
        "codex_oauth_token_url",
        "codex_oauth_client_id",
        "codex_oauth_client_secret",
        "codex_oauth_redirect_uri",
        "codex_oauth_cookie_secure",
        "codex_oauth_provider",
        "codex_oauth_provider_revoke_url",
        "codex_oauth_token_sink_enabled",
        "codex_cli_llm_fallback_enabled",
        "codex_cli_llm_persistent_enabled",
        "codex_cli_llm_ignore_user_config",
        "codex_cli_llm_disabled_features",
        "codex_cli_llm_command",
        "codex_cli_llm_persistent_start_timeout_seconds",
        "codex_cli_llm_persistent_idle_ttl_seconds",
    ]
    return {key: getattr(settings, key) for key in keys}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default=None, help="override environment name for deterministic tests")
    parser.add_argument("--secret", default=None, help="override token secret for deterministic tests; value is not printed")
    parser.add_argument(
        "--require-artifact-token",
        default=None,
        choices=["true", "false"],
        help="override artifact-token requirement for deterministic tests",
    )
    parser.add_argument("--records-tsv", action="store_true", help="emit deploy-script preflight records as TSV")
    args = parser.parse_args(argv)

    values = _settings_values()
    if args.env is not None:
        values["env"] = args.env
    if args.secret is not None:
        values["llm_report_export_token_secret"] = args.secret
    if args.require_artifact_token is not None:
        values["llm_report_export_require_artifact_token"] = args.require_artifact_token

    report = evaluate_ops_security_preflight(
        env=values["env"],
        llm_report_export_token_secret=values["llm_report_export_token_secret"],
        llm_report_export_require_artifact_token=values["llm_report_export_require_artifact_token"],
        codex_auth_enabled=values["codex_auth_enabled"],
        codex_auth_tokens=values["codex_auth_tokens"],
        codex_oauth_enabled=values["codex_oauth_enabled"],
        codex_oauth_authorize_url=values["codex_oauth_authorize_url"],
        codex_oauth_token_url=values["codex_oauth_token_url"],
        codex_oauth_client_id=values["codex_oauth_client_id"],
        codex_oauth_client_secret=values["codex_oauth_client_secret"],
        codex_oauth_redirect_uri=values["codex_oauth_redirect_uri"],
        codex_oauth_cookie_secure=values["codex_oauth_cookie_secure"],
        codex_oauth_provider=values["codex_oauth_provider"],
        codex_oauth_provider_revoke_url=values["codex_oauth_provider_revoke_url"],
        codex_oauth_token_sink_enabled=values["codex_oauth_token_sink_enabled"],
        codex_cli_llm_fallback_enabled=values["codex_cli_llm_fallback_enabled"],
        codex_cli_llm_persistent_enabled=values["codex_cli_llm_persistent_enabled"],
        codex_cli_llm_ignore_user_config=values["codex_cli_llm_ignore_user_config"],
        codex_cli_llm_disabled_features=values["codex_cli_llm_disabled_features"],
        codex_cli_llm_command=values["codex_cli_llm_command"],
        codex_cli_llm_persistent_start_timeout_seconds=values[
            "codex_cli_llm_persistent_start_timeout_seconds"
        ],
        codex_cli_llm_persistent_idle_ttl_seconds=values[
            "codex_cli_llm_persistent_idle_ttl_seconds"
        ],
    )
    if args.records_tsv:
        print(render_preflight_records_tsv(report))
    else:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
