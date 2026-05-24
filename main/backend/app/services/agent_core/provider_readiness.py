from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Mapping

from .contracts import AgentCoreRequest, CoreModelStep, CoreToolCall, CoreToolResult, CoreToolSpec
from .core import AgentCore
from .fake_provider import FakeCoreProvider
from .json_provider import JsonCoreProvider
from .live_provider_shim import (
    build_repo_local_live_provider_shim_evidence,
    validate_repo_local_live_provider_shim_evidence,
)
from .native_provider import NativeToolCallingCoreProvider, _native_tool_name
from .registry import CoreToolRegistry


AGENT_CORE_PROVIDER_LIVE_READINESS_CONTRACT_VERSION = "agent_core.provider_live_readiness.v1"

_SUPPORTED_LLM_PROVIDERS = ("openai", "azure", "ollama", "litellm", "local")
_AGENT_CORE_PROVIDER_KEYS = (
    "fake_core_provider",
    "json_core_provider",
    "native_tool_calling_provider",
)


@dataclass(frozen=True)
class ProviderConfigRow:
    provider: str
    selected: bool
    implementation_path: str
    config_state: str
    required_config_keys: tuple[str, ...] = ()
    missing_config_keys: tuple[str, ...] = ()
    live_probe_status: str = "not_run"
    live_gap_reason: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "selected": self.selected,
            "implementation_path": self.implementation_path,
            "config_state": self.config_state,
            "required_config_keys": list(self.required_config_keys),
            "missing_config_keys": list(self.missing_config_keys),
            "live_probe_status": self.live_probe_status,
            "live_gap_reason": self.live_gap_reason,
            "notes": self.notes,
        }


def build_agent_core_provider_live_readiness_contract(
    *,
    settings_source: Any | None = None,
    codex_cli_status: Mapping[str, Any] | None = None,
    enable_live_probes: bool = False,
) -> dict[str, Any]:
    """Build a bounded AgentCore live-provider readiness contract.

    The contract intentionally keeps local fixture readiness separate from live
    provider availability. Local fixtures prove repo-owned AgentCore provider
    adapters still dispatch through schemas and tools; live provider rows record
    current configuration and gaps without spending external model calls.
    """

    if settings_source is None:
        from app.settings.config import settings as settings_source

    resolved_codex_status = _codex_cli_status(codex_cli_status)
    provider_rows = _configured_provider_rows(settings_source, resolved_codex_status)
    local_fixtures = _local_fixture_readiness()
    live_provider_closure = (
        build_repo_local_live_provider_shim_evidence()
        if enable_live_probes
        else _disabled_live_provider_closure()
    )
    live_availability = _live_availability_rows(
        provider_rows=provider_rows,
        enable_live_probes=enable_live_probes,
        live_provider_closure=live_provider_closure,
    )
    unsupported_claims = _unsupported_closure_claims(
        provider_rows=provider_rows,
        live_availability=live_availability,
        live_provider_closure=live_provider_closure,
    )
    failures = _contract_failures(
        local_fixtures=local_fixtures,
        provider_rows=provider_rows,
        live_provider_closure=live_provider_closure,
        enable_live_probes=enable_live_probes,
    )
    readiness_state = _readiness_state(
        provider_rows=provider_rows,
        local_fixtures=local_fixtures,
        live_availability=live_availability,
        live_provider_closure=live_provider_closure,
        unsupported_claims=unsupported_claims,
    )
    selected_row = next((row for row in provider_rows if row.selected), None)
    selected_provider = selected_row.provider if selected_row is not None else _selected_llm_provider(settings_source)

    return {
        "contract_version": AGENT_CORE_PROVIDER_LIVE_READINESS_CONTRACT_VERSION,
        "status": "passed" if not failures else "failed",
        "readiness_state": readiness_state,
        "scope": (
            "agent_core_provider_live_readiness_with_repo_local_live_provider_shim"
            if enable_live_probes
            else "agent_core_provider_live_readiness_boundary_no_external_model_spend"
        ),
        "configured_provider": {
            "llm_provider": selected_provider,
            "agent_core_runtime_provider": "native_tool_calling_provider_with_json_fallback",
            "e2e_scripted_provider_enabled": bool(_setting(settings_source, "agent_core_e2e_scripted_provider_enabled", False)),
        },
        "configured_providers": [row.to_dict() for row in provider_rows],
        "codex_cli_fallback": dict(resolved_codex_status),
        "agent_core_provider_boundary": {
            "provider_keys": list(_AGENT_CORE_PROVIDER_KEYS),
            "runtime_builder": "app.api.agent_chat._build_agent_core_provider",
            "default_provider": "NativeToolCallingCoreProvider(fallback_provider=JsonCoreProvider())",
            "local_fixture_contract": "schema_inventory_plus_tool_dispatch_no_network",
        },
        "local_fixture_readiness": local_fixtures,
        "live_availability": live_availability,
        "live_provider_closure": live_provider_closure,
        "unsupported_closure_claims": unsupported_claims,
        "gate_semantics": {
            "status_passed_means": "AgentCore provider readiness contract shape and local fixture dispatch are valid",
            "status_passed_does_not_mean": "OpenAI, Azure, LiteLLM, Ollama, external frameworks, or production model quality are externally verified",
            "live_probe_policy": (
                "repo-local live provider shim runs when enable_live_probes=true; it records zero external model calls "
                "and must not be cited as external provider evidence"
            ),
        },
        "failures": failures,
    }


def validate_agent_core_provider_live_readiness_contract(contract: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    _expect(
        contract.get("contract_version") == AGENT_CORE_PROVIDER_LIVE_READINESS_CONTRACT_VERSION,
        errors,
        "unexpected provider live readiness contract version",
    )
    _expect(contract.get("status") in {"passed", "failed"}, errors, "invalid status")
    _expect(contract.get("readiness_state") in {"ready", "partial", "blocked"}, errors, "invalid readiness_state")
    provider_rows = [row for row in contract.get("configured_providers") or [] if isinstance(row, dict)]
    _expect(any(row.get("selected") for row in provider_rows), errors, "selected configured provider row missing")
    fixture_rows = [row for row in contract.get("local_fixture_readiness") or [] if isinstance(row, dict)]
    fixture_keys = {str(row.get("provider_key") or "") for row in fixture_rows}
    for provider_key in _AGENT_CORE_PROVIDER_KEYS:
        _expect(provider_key in fixture_keys, errors, f"local fixture row missing: {provider_key}")
    for row in fixture_rows:
        _expect(row.get("fixture_status") == "ready", errors, f"local fixture not ready: {row.get('provider_key')}")
        _expect(
            row.get("schema_inventory_contract_version") == "agent_core.tool_schema_inventory.v1",
            errors,
            f"fixture schema inventory drift: {row.get('provider_key')}",
        )
        _expect(row.get("tool_count") == 1, errors, f"fixture tool count drift: {row.get('provider_key')}")
        _expect(row.get("stop_reason") == "final_answer", errors, f"fixture did not reach final_answer: {row.get('provider_key')}")
        _expect(row.get("tool_result_status_counts", {}).get("completed", 0) >= 1, errors, f"fixture did not complete a tool: {row.get('provider_key')}")
    live_rows = [row for row in (contract.get("live_availability") or {}).get("providers") or [] if isinstance(row, dict)]
    _expect(bool(live_rows), errors, "live availability rows missing")
    selected_live_rows = [row for row in live_rows if row.get("selected")]
    _expect(bool(selected_live_rows), errors, "selected live availability row missing")
    closure = contract.get("live_provider_closure") if isinstance(contract.get("live_provider_closure"), Mapping) else {}
    if contract.get("readiness_state") == "ready":
        _expect(bool(closure), errors, "ready contract missing live provider closure")
        _expect(closure.get("closed") is True, errors, "ready contract closure not closed")
        for error in validate_repo_local_live_provider_shim_evidence(closure):
            errors.append(f"repo-local live provider shim invalid: {error}")
        _expect(any(row.get("live_probe_status") == "ready" for row in selected_live_rows), errors, "selected live row not ready")
        _expect(
            closure.get("external_provider_live_verified") is False,
            errors,
            "repo-local closure must not claim external provider verification",
        )
    claim_codes = {str(row.get("code") or "") for row in contract.get("unsupported_closure_claims") or [] if isinstance(row, dict)}
    if contract.get("readiness_state") == "ready":
        _expect(
            "repo_local_shim_is_not_external_provider_evidence" in claim_codes,
            errors,
            "missing repo-local shim external-evidence limitation",
        )
        _expect(
            "selected_provider_live_availability_not_closed" not in claim_codes,
            errors,
            "ready repo-local closure still reports selected-provider live gap",
        )
    else:
        _expect("all_agentcore_providers_live_not_closed" in claim_codes, errors, "missing all-provider unsupported claim")
        _expect("selected_provider_live_availability_not_closed" in claim_codes, errors, "missing selected-provider unsupported claim")
    return errors


def _configured_provider_rows(settings_source: Any, codex_status: Mapping[str, Any]) -> list[ProviderConfigRow]:
    selected = _selected_llm_provider(settings_source)
    rows: list[ProviderConfigRow] = []
    for provider in _SUPPORTED_LLM_PROVIDERS:
        rows.append(_provider_config_row(provider=provider, selected=provider == selected, settings_source=settings_source, codex_status=codex_status))
    if selected not in _SUPPORTED_LLM_PROVIDERS:
        rows.append(
            ProviderConfigRow(
                provider=selected,
                selected=True,
                implementation_path="app.services.llm.provider.get_chat_model",
                config_state="unsupported_provider",
                live_probe_status="blocked",
                live_gap_reason="unsupported_llm_provider",
                notes="The configured llm_provider is not in the AgentCore provider readiness allowlist.",
            )
        )
    return rows


def _provider_config_row(
    *,
    provider: str,
    selected: bool,
    settings_source: Any,
    codex_status: Mapping[str, Any],
) -> ProviderConfigRow:
    if provider == "openai":
        if _has_setting(settings_source, "openai_api_key"):
            return ProviderConfigRow(
                provider=provider,
                selected=selected,
                implementation_path="langchain_openai.ChatOpenAI",
                config_state="configured",
                required_config_keys=("OPENAI_API_KEY",),
                notes="Direct OpenAI chat model configuration is present.",
            )
        if bool(codex_status.get("available")):
            return ProviderConfigRow(
                provider=provider,
                selected=selected,
                implementation_path="app.services.llm.codex_cli.CodexCliChatModel",
                config_state="configured_via_codex_cli_fallback",
                required_config_keys=("CODEX_CLI_BINARY", "CODEX_AUTH_TOKEN_SINK"),
                notes="OpenAI API key is absent, but the repo fallback can use local Codex CLI auth.",
            )
        return ProviderConfigRow(
            provider=provider,
            selected=selected,
            implementation_path="langchain_openai.ChatOpenAI",
            config_state="missing_config",
            required_config_keys=("OPENAI_API_KEY", "or CODEX_CLI_BINARY+CODEX_AUTH_TOKEN_SINK"),
            missing_config_keys=("OPENAI_API_KEY", "CODEX_CLI_BINARY+CODEX_AUTH_TOKEN_SINK"),
            live_probe_status="blocked",
            live_gap_reason="missing_openai_or_codex_cli_credentials",
            notes="OpenAI live availability cannot be claimed without API key or Codex CLI fallback readiness.",
        )
    if provider == "azure":
        required = ("AZURE_API_BASE", "AZURE_API_KEY", "AZURE_API_VERSION", "AZURE_CHAT_DEPLOYMENT")
        missing = tuple(key for key in required if not _has_setting(settings_source, _env_to_setting(key)))
        return ProviderConfigRow(
            provider=provider,
            selected=selected,
            implementation_path="langchain_openai.AzureChatOpenAI",
            config_state="configured" if not missing else "missing_config",
            required_config_keys=required,
            missing_config_keys=missing,
            live_probe_status="blocked" if missing else "not_run",
            live_gap_reason="missing_azure_chat_config" if missing else None,
            notes="Azure readiness is config-recorded only; no live model call is made by this checker.",
        )
    if provider == "ollama":
        missing = () if _has_setting(settings_source, "ollama_base_url") else ("OLLAMA_BASE_URL",)
        return ProviderConfigRow(
            provider=provider,
            selected=selected,
            implementation_path="langchain_community.chat_models.ChatOllama",
            config_state="configured" if not missing else "missing_config",
            required_config_keys=("OLLAMA_BASE_URL",),
            missing_config_keys=missing,
            live_probe_status="not_run" if not missing else "blocked",
            live_gap_reason=None if not missing else "missing_ollama_base_url",
            notes="Ollama endpoint configuration is recorded; endpoint health is not probed here.",
        )
    if provider == "litellm":
        required = ("LITELLM_API_BASE", "LITELLM_API_KEY")
        missing = tuple(key for key in required if not _has_setting(settings_source, _env_to_setting(key)))
        return ProviderConfigRow(
            provider=provider,
            selected=selected,
            implementation_path="langchain_openai.ChatOpenAI(openai-compatible LiteLLM endpoint)",
            config_state="configured" if not missing else "missing_config",
            required_config_keys=required,
            missing_config_keys=missing,
            live_probe_status="blocked" if missing else "not_run",
            live_gap_reason="missing_litellm_config" if missing else None,
            notes="LiteLLM readiness is config-recorded only; no proxy call is made by this checker.",
        )
    if provider == "local":
        return ProviderConfigRow(
            provider=provider,
            selected=selected,
            implementation_path="not_implemented_in_app.services.llm.provider.get_chat_model",
            config_state="unsupported_provider",
            required_config_keys=("LOCAL_LLM_ENABLED",),
            live_probe_status="blocked",
            live_gap_reason="local_llm_provider_not_implemented",
            notes="Settings mention local as an allowed value, but the current chat-model adapter has no local provider branch.",
        )
    return ProviderConfigRow(
        provider=provider,
        selected=selected,
        implementation_path="unknown",
        config_state="unsupported_provider",
        live_probe_status="blocked",
        live_gap_reason="unsupported_llm_provider",
    )


def _local_fixture_readiness() -> list[dict[str, Any]]:
    return [
        _run_fixture(
            provider_key="fake_core_provider",
            provider=FakeCoreProvider(
                [
                    CoreModelStep.tools(_fixture_tool_call("fake"), model_path="fake_core_provider"),
                    CoreModelStep.final("fake fixture ready", model_path="fake_core_provider"),
                ]
            ),
        ),
        _run_fixture(
            provider_key="json_core_provider",
            provider=JsonCoreProvider(chat_model=_JsonFixtureChat()),
        ),
        _run_fixture(
            provider_key="native_tool_calling_provider",
            provider=NativeToolCallingCoreProvider(chat_model=_NativeFixtureChat()),
        ),
    ]


def _run_fixture(*, provider_key: str, provider: Any) -> dict[str, Any]:
    try:
        registry = CoreToolRegistry()
        registry.register(_fixture_tool_spec(), _fixture_tool_handler)
        schema_inventory = registry.schema_inventory()
        request = AgentCoreRequest(
            message=f"Run AgentCore provider readiness fixture for {provider_key}.",
            session_id=f"agent-core-provider-readiness-{provider_key}",
            turn_id=f"turn-agent-core-provider-readiness-{provider_key}",
            project_key="demo_proj",
            max_iterations=4,
            max_tool_calls=2,
            context={
                "trace_id": f"trace-agent-core-provider-readiness-{provider_key}",
                "request_id": f"req-agent-core-provider-readiness-{provider_key}",
                "default_provider": provider_key,
                "default_model": "fixture",
            },
        )
        result = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(request)
        event_counts = Counter(event.event_type for event in result.events)
        tool_result_counts = Counter(item.status for item in result.tool_results)
        ready = (
            result.stop_reason == "final_answer"
            and bool(result.tool_results)
            and all(item.status == "completed" for item in result.tool_results)
        )
        return {
            "provider_key": provider_key,
            "fixture_status": "ready" if ready else "failed",
            "fixture_type": "local_no_network_tool_dispatch",
            "schema_inventory_contract_version": schema_inventory.get("contract_version"),
            "tool_count": schema_inventory.get("tool_count"),
            "session_id": result.session_id,
            "turn_id": result.turn_id,
            "stop_reason": result.stop_reason,
            "event_type_counts": {name: event_counts[name] for name in sorted(event_counts)},
            "tool_result_status_counts": {name: tool_result_counts[name] for name in sorted(tool_result_counts)},
            "tool_names": [item.tool_name for item in result.tool_results],
            "final_answer_present": bool(result.final_answer),
        }
    except Exception as exc:  # noqa: BLE001 - readiness contract records the real fixture failure.
        return {
            "provider_key": provider_key,
            "fixture_status": "failed",
            "fixture_type": "local_no_network_tool_dispatch",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }


def _live_availability_rows(
    *,
    provider_rows: list[ProviderConfigRow],
    enable_live_probes: bool,
    live_provider_closure: Mapping[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    closure_ready = bool(live_provider_closure.get("closed") is True)
    for row in provider_rows:
        if row.selected and closure_ready:
            live_status = "ready"
            gap_reason = None
            availability_state = "ready"
            unsupported_claim = None
        elif row.config_state in {"missing_config", "unsupported_provider"}:
            live_status = "blocked"
            gap_reason = row.live_gap_reason or row.config_state
            availability_state = "gap_recorded"
            unsupported_claim = "current live model availability is not proven by this run"
        elif enable_live_probes:
            live_status = "not_run"
            gap_reason = "repo_local_live_shim_only_selected_provider"
            availability_state = "gap_recorded"
            unsupported_claim = "only the selected repo-local shim path is closed by this run"
        else:
            live_status = "not_run"
            gap_reason = "live_probe_disabled"
            availability_state = "gap_recorded"
            unsupported_claim = "current live model availability is not proven by this run"
        rows.append(
            {
                "provider": row.provider,
                "selected": row.selected,
                "config_state": row.config_state,
                "live_probe_status": live_status,
                "availability_state": availability_state,
                "gap_reason": gap_reason,
                "unsupported_claim": unsupported_claim,
                "closure_basis": live_provider_closure.get("closure_basis") if row.selected and closure_ready else None,
                "external_provider_live_verified": False,
                "external_model_calls": live_provider_closure.get("external_model_calls", 0) if row.selected and closure_ready else 0,
            }
        )
    return {
        "probe_type": (
            "repo_local_live_provider_shim"
            if closure_ready
            else "configuration_and_local_fixture_readiness_no_external_model_call"
        ),
        "live_probes_enabled": enable_live_probes,
        "closure_basis": live_provider_closure.get("closure_basis") if closure_ready else None,
        "external_provider_live_verified": False,
        "external_model_calls": live_provider_closure.get("external_model_calls", 0) if closure_ready else 0,
        "providers": rows,
        "summary": {
            "by_live_probe_status": _count_by_key(rows, "live_probe_status"),
            "by_availability_state": _count_by_key(rows, "availability_state"),
        },
    }


def _unsupported_closure_claims(
    *,
    provider_rows: list[ProviderConfigRow],
    live_availability: Mapping[str, Any],
    live_provider_closure: Mapping[str, Any],
) -> list[dict[str, str]]:
    selected = next((row for row in provider_rows if row.selected), None)
    selected_provider = selected.provider if selected is not None else "unknown"
    live_statuses = {
        str(row.get("provider") or ""): str(row.get("live_probe_status") or "")
        for row in live_availability.get("providers") or []
        if isinstance(row, Mapping)
    }
    if live_provider_closure.get("closed") is True:
        claims = [
            {
                "code": "repo_local_shim_is_not_external_provider_evidence",
                "claim": "The repo-local live provider shim proves OpenAI, Azure, LiteLLM, Ollama, or another external provider account is live.",
                "reason": "The closure evidence records network_scope=repo_local_in_process_no_external_network and external_provider_live_verified=false.",
                "required_next_evidence": "A separate bounded external provider/API/account/network invocation with real credentials and the same redacted trace envelope.",
            },
            {
                "code": "all_external_agentcore_providers_live_not_closed",
                "claim": "All external AgentCore providers are live-ready.",
                "reason": f"Only the selected repo-local shim path is closed; current live statuses are {live_statuses}.",
                "required_next_evidence": "Provider-specific bounded live probes for each external provider that should be promoted.",
            },
            {
                "code": "external_framework_live_adoption_not_closed",
                "claim": "LangGraph, Semantic Kernel, CrewAI, or another external agent framework can replace AgentCore.",
                "reason": "The closure is repo-native and does not add or evaluate external framework runtime dependencies.",
                "required_next_evidence": "A written additive-capability delta that preserves schema inventory, dispatch events, permission checks, and trace audit evidence.",
            },
        ]
        return claims
    claims = [
        {
            "code": "all_agentcore_providers_live_not_closed",
            "claim": "All AgentCore providers are live-ready.",
            "reason": f"Current live statuses are recorded as {live_statuses}; local fixtures do not prove external model availability.",
            "required_next_evidence": "Bounded live invocation evidence for the selected provider plus native/json fallback behavior under current credentials.",
        },
        {
            "code": "selected_provider_live_availability_not_closed",
            "claim": f"The selected AgentCore LLM provider {selected_provider!r} is live-available.",
            "reason": "This checker records configuration and local fixture readiness; it does not perform an external model call.",
            "required_next_evidence": "A live provider probe with timeout, model id, response shape, and failure classification.",
        },
        {
            "code": "native_tool_calling_quality_not_closed",
            "claim": "Native tool calling quality is proven for the selected live model.",
            "reason": "The native provider fixture proves bind_tools dispatch shape only; production model tool-call reliability remains unmeasured.",
            "required_next_evidence": "Live native tool-call replay against the configured model with schema adherence assertions.",
        },
        {
            "code": "external_framework_live_adoption_not_closed",
            "claim": "LangGraph, Semantic Kernel, CrewAI, or another external agent framework can replace AgentCore.",
            "reason": "The current readiness boundary is repo-native and does not add or evaluate external framework runtime dependencies.",
            "required_next_evidence": "A written additive-capability delta that preserves schema inventory, dispatch events, permission checks, and trace audit evidence.",
        },
    ]
    if selected is not None and selected.config_state == "unsupported_provider":
        claims.append(
            {
                "code": f"{selected.provider}_provider_adapter_not_implemented",
                "claim": f"The configured provider {selected.provider!r} is supported by AgentCore live runtime.",
                "reason": selected.notes or selected.live_gap_reason or "The selected provider has no supported AgentCore live adapter.",
                "required_next_evidence": "Implement and test the provider branch or change llm_provider to a supported configured provider.",
            }
        )
    return claims


def _disabled_live_provider_closure() -> dict[str, Any]:
    return {
        "contract_version": "agent_core.repo_local_live_provider_shim.v1",
        "status": "not_run",
        "closed": False,
        "closure_basis": None,
        "reason": "live probes disabled",
        "external_provider_live_verified": False,
        "external_model_calls": 0,
    }


def _contract_failures(
    *,
    local_fixtures: list[dict[str, Any]],
    provider_rows: list[ProviderConfigRow],
    live_provider_closure: Mapping[str, Any],
    enable_live_probes: bool,
) -> list[str]:
    failures: list[str] = []
    for row in local_fixtures:
        if row.get("fixture_status") != "ready":
            failures.append(f"local fixture failed: {row.get('provider_key')}: {row.get('error_type') or row.get('stop_reason')}")
    if not any(row.selected for row in provider_rows):
        failures.append("selected provider row missing")
    if enable_live_probes:
        for error in validate_repo_local_live_provider_shim_evidence(live_provider_closure):
            failures.append(f"repo-local live provider shim invalid: {error}")
    return failures


def _readiness_state(
    *,
    provider_rows: list[ProviderConfigRow],
    local_fixtures: list[dict[str, Any]],
    live_availability: Mapping[str, Any],
    live_provider_closure: Mapping[str, Any],
    unsupported_claims: list[dict[str, str]],
) -> str:
    if any(row.get("fixture_status") != "ready" for row in local_fixtures):
        return "blocked"
    if live_provider_closure.get("status") == "failed":
        return "blocked"
    if live_provider_closure.get("closed") is True:
        return "ready"
    selected = next((row for row in provider_rows if row.selected), None)
    if selected is None or selected.config_state in {"missing_config", "unsupported_provider"}:
        return "partial"
    selected_live = next(
        (
            row
            for row in live_availability.get("providers") or []
            if isinstance(row, Mapping) and row.get("selected")
        ),
        {},
    )
    if selected_live.get("live_probe_status") == "ready" and not unsupported_claims:
        return "ready"
    return "partial"


def _fixture_tool_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent.provider_readiness.echo",
        title="Agent provider readiness echo",
        description_for_model="Deterministic provider readiness echo tool.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "contract_version": {"type": "string"},
                "echo": {"type": "string"},
            },
            "required": ["contract_version", "echo"],
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="serial",
        project_service_id="agent.provider_readiness.echo",
        metadata={"contract_version": "agent.provider_readiness.echo.v1"},
    )


def _fixture_tool_handler(tool_call: CoreToolCall, tool_spec: CoreToolSpec, request: AgentCoreRequest, emit: Any) -> CoreToolResult:
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="completed",
        model_summary="AgentCore provider readiness fixture completed.",
        structured_content={
            "contract_version": "agent.provider_readiness.echo.result.v1",
            "echo": str(tool_call.arguments.get("query") or ""),
        },
    )


def _fixture_tool_call(suffix: str) -> CoreToolCall:
    return CoreToolCall(
        tool_name="agent.provider_readiness.echo",
        arguments={"query": f"{suffix}-provider-readiness"},
        call_id=f"call-agent-provider-readiness-{suffix}",
        reason="deterministic provider readiness fixture",
    )


class _JsonFixtureChat:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, prompt: Any) -> SimpleNamespace:
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "type": "tool_calls",
                        "tool_calls": [
                            {
                                "tool_name": "agent.provider_readiness.echo",
                                "arguments": {"query": "json-provider-readiness"},
                                "call_id": "call-agent-provider-readiness-json",
                                "reason": "JSON provider fixture tool dispatch",
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        return SimpleNamespace(
            content=json.dumps(
                {
                    "type": "final_answer",
                    "content": "json provider fixture ready",
                },
                ensure_ascii=False,
            )
        )


class _NativeFixtureChat:
    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, tools: Any) -> "_NativeFixtureChat":
        return self

    def invoke(self, messages: Any) -> SimpleNamespace:
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                content="",
                tool_calls=[
                    {
                        "id": "call-agent-provider-readiness-native",
                        "name": _native_tool_name("agent.provider_readiness.echo"),
                        "args": {"query": "native-provider-readiness"},
                    }
                ],
            )
        return SimpleNamespace(content="native provider fixture ready", tool_calls=[])


def _codex_cli_status(override: Mapping[str, Any] | None) -> dict[str, Any]:
    if override is not None:
        return {
            "available": bool(override.get("available")),
            "binary_available": bool(override.get("binary_available")),
            "auth_available": bool(override.get("auth_available")),
            "fallback_enabled": bool(override.get("fallback_enabled", True)),
            "model": _text(override.get("model")) or None,
            "reason": _text(override.get("reason")) or None,
        }
    try:
        from app.services.codex_oauth import has_valid_token_sink
        from app.services.llm.codex_cli import _resolve_codex_bin, codex_cli_llm_available
        from app.settings.config import settings

        command = str(getattr(settings, "codex_cli_llm_command", "codex") or "codex").strip() or "codex"
        binary_available = bool(_resolve_codex_bin(command))
        auth_available = bool(has_valid_token_sink())
        fallback_enabled = bool(getattr(settings, "codex_cli_llm_fallback_enabled", True))
        available = bool(codex_cli_llm_available())
        return {
            "available": available,
            "binary_available": binary_available,
            "auth_available": auth_available,
            "fallback_enabled": fallback_enabled,
            "model": str(getattr(settings, "codex_cli_llm_model", "") or "").strip() or None,
            "reason": None if available else "codex_cli_binary_or_auth_unavailable",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "binary_available": False,
            "auth_available": False,
            "fallback_enabled": False,
            "model": None,
            "reason": f"{exc.__class__.__name__}: {exc}",
        }


def _selected_llm_provider(settings_source: Any) -> str:
    return str(_setting(settings_source, "llm_provider", "openai") or "openai").strip().lower() or "openai"


def _setting(settings_source: Any, key: str, default: Any = None) -> Any:
    if isinstance(settings_source, Mapping):
        return settings_source.get(key, default)
    return getattr(settings_source, key, default)


def _has_setting(settings_source: Any, key: str) -> bool:
    value = _setting(settings_source, key, None)
    if isinstance(value, bool):
        return value
    return bool(str(value or "").strip())


def _env_to_setting(key: str) -> str:
    return key.lower()


def _count_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: Counter[str] = Counter(str(row.get(key) or "unknown") for row in rows)
    return {name: counts[name] for name in sorted(counts)}


def _expect(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def _text(value: Any) -> str:
    return str(value or "").strip()
