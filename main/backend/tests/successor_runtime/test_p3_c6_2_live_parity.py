"""P3 C6.2 real OpenAI provider-port parity (fake transport only)."""

from __future__ import annotations

import json

import pytest

from app.successor_runtime.capabilities import agent_core_c6_2 as c6_2
from app.successor_runtime.capabilities import (
    agent_core_c6_2_live_model_port as live,
)
from app.successor_runtime.capabilities.agent_core_c6_2_interpreters import (
    authority_requirement_digest,
)
from app.successor_runtime.capabilities.agent_core_c6_common import (
    AgentModelStep,
    ProjectScope,
)

pytestmark = pytest.mark.unit

ATTEMPT_ID = "attempt:c6-2:live:001"
SECRET = "fixture-c6-2-super-secret-key-not-real"


def _scope() -> ProjectScope:
    return ProjectScope(
        "demo_proj",
        5,
        "mrw_p_demo_proj",
        "scope-inc-5",
        "",
    )


def _request(**overrides) -> c6_2.AgentModelStepRequest:
    values = {
        "schema_version": c6_2.AGENT_CORE_C6_2_PAYLOAD_SCHEMA,
        "operation_kind": c6_2.AGENT_CORE_C6_2_KIND,
        "project_scope": _scope(),
        "session_id": "session-c6-2-live",
        "turn_id": "turn-c6-2-live",
        "message_ref": "project-value:message:c6-2-live",
        "transcript_ref": "project-value:transcript:c6-2-live",
        "tool_contract_refs": ("source_library.resolve_execution_request.v1",),
        "max_iterations": 3,
        "iteration": 1,
        "max_tool_calls": 2,
        "remaining_tool_calls": 2,
        "provider_profile_ref": "live.agent_core.c6_2.openai_provider_port.v1",
        "credential_ref": "credential:opaque:c6-2-live",
    }
    values.update(overrides)
    return c6_2.AgentModelStepRequest(**values)


class _FakeTransport:
    """Deterministic chat-completions transport that never touches network."""

    def __init__(
        self,
        status: int = 200,
        payload: dict | list | str | None = None,
        error: Exception | None = None,
    ) -> None:
        self.status = status
        self.payload = payload if payload is not None else {}
        self.error = error
        self.calls: list[tuple[str, dict, dict[str, str], float]] = []

    def __call__(
        self,
        url: str,
        body: dict,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> tuple[int, dict]:
        self.calls.append((url, body, headers, float(timeout_seconds)))
        if self.error is not None:
            raise self.error
        return self.status, self.payload


def _success_payload(
    *,
    content: str = "PARITY_OK",
    finish_reason: str = "stop",
) -> dict:
    return {
        "id": "chatcmpl-fake",
        "model": "gpt-4o-mini",
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
    }


def _port(
    transport: _FakeTransport,
    *,
    api_key: str | None = SECRET,
) -> live.OpenAILiveProviderPort:
    return live.OpenAILiveProviderPort(
        api_key_provider=lambda: api_key,
        transport=transport,
    )


def test_authority_digest_matches_interpreter_binding_digest() -> None:
    assert live.openai_authority_digest() == authority_requirement_digest()


def test_success_receipt_metadata_and_probe_body_are_parity_exact() -> None:
    request = _request()
    transport = _FakeTransport(payload=_success_payload())
    port = _port(transport)
    result = c6_2.interpret_model_step(
        request,
        port,
        attempt_id=ATTEMPT_ID,
    )

    assert isinstance(result.step, AgentModelStep)
    assert result.step.step_type == "final_answer"
    assert result.step.content == "PARITY_OK"
    assert result.step.schema_version == "mrw.successor.agent-core.c6.model-step.v1"
    assert result.receipt.outcome_code == "ProviderStepSucceeded"
    assert result.receipt.provider_calls == 1
    assert result.receipt.readback_status == "NOT_APPLICABLE"
    assert result.receipt.receipt_digest
    assert result.result_digest
    assert port.provider_calls == 1
    assert len(transport.calls) == 1

    step_plain = result.step.to_plain()
    metadata = step_plain["metadata"]
    assert metadata["live"] is True
    assert metadata["provider"] == "openai"
    assert metadata["model"] == port.model
    assert metadata["finish_reason"] == "stop"
    assert metadata["iteration"] == request.iteration
    assert metadata["provider_calls"] == 1

    url, body, headers, _timeout = transport.calls[0]
    assert url == f"{port.base_url.rstrip('/')}{live.CHAT_COMPLETIONS_PATH}"
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["Content-Type"] == "application/json"
    assert body["model"] == port.model
    assert body["max_tokens"] == 16
    assert body["temperature"] == 0
    user_content = str(body["messages"][1]["content"])
    assert request.session_id in user_content
    assert request.turn_id in user_content
    assert str(request.iteration) in user_content
    assert request.message_ref not in user_content
    assert request.transcript_ref not in user_content
    assert SECRET not in json.dumps(step_plain)
    assert SECRET not in json.dumps(result.receipt.to_plain())


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "ProviderCredentialRejected"),
        (403, "ProviderCredentialRejected"),
        (429, "ProviderRateLimited"),
        (408, "ProviderUnavailable"),
        (503, "ProviderUnavailable"),
    ],
)
def test_http_status_failures_are_typed_and_do_not_retry(
    status: int,
    expected: str,
) -> None:
    transport = _FakeTransport(status=status, payload={})
    port = _port(transport)
    result = c6_2.interpret_model_step(
        _request(),
        port,
        attempt_id=ATTEMPT_ID,
    )
    assert result.receipt.outcome_code == expected
    assert result.step is None
    assert result.receipt.provider_calls == 1
    assert port.provider_calls == 1
    assert len(transport.calls) == 1
    assert SECRET not in json.dumps(result.receipt.to_plain())


def test_missing_key_fails_before_transport_invocation() -> None:
    transport = _FakeTransport(payload=_success_payload())
    port = live.OpenAILiveProviderPort(
        api_key_provider=lambda: None,
        transport=transport,
    )
    result = c6_2.interpret_model_step(
        _request(),
        port,
        attempt_id=ATTEMPT_ID,
    )
    assert result.receipt.outcome_code == "ProviderCredentialRejected"
    assert result.receipt.provider_calls == 1
    assert transport.calls == []


def test_outcome_unknown_before_send_reads_back_non_start_proof() -> None:
    transport = _FakeTransport(
        error=live.OpenAIOutcomeUnknownBeforeSendError("pre-send")
    )
    port = _port(transport)
    result = c6_2.interpret_model_step(
        _request(),
        port,
        attempt_id=ATTEMPT_ID,
    )
    assert result.receipt.outcome_code == "ProviderOutcomeUnknown"
    assert result.receipt.readback_status == "NON_START_PROOF"
    assert result.receipt.provider_calls == 1
    assert port.provider_calls == 1


def test_malformed_success_response_is_protocol_invalid() -> None:
    for payload in (
        _success_payload(content="   "),
        _success_payload(content=None),
        {"choices": []},
        {"choices": [{"message": {}}]},
        [],
        "not-json",
    ):
        transport = _FakeTransport(payload=payload)
        port = _port(transport)
        result = c6_2.interpret_model_step(
            _request(),
            port,
            attempt_id=ATTEMPT_ID,
        )
        assert result.receipt.outcome_code == "ProviderProtocolInvalid"


def test_timeout_and_connection_failures_are_typed() -> None:
    for error, expected in (
        (TimeoutError("timeout"), "ProviderTimeout"),
        (ConnectionError("connection refused"), "ProviderUnavailable"),
    ):
        transport = _FakeTransport(error=error)
        port = _port(transport)
        result = c6_2.interpret_model_step(
            _request(),
            port,
            attempt_id=ATTEMPT_ID,
        )
        assert result.receipt.outcome_code == expected
        assert result.receipt.provider_calls == 1


def test_builder_resolves_key_presence_without_real_network() -> None:
    assert (
        live.build_openai_live_provider_port(
            api_key_provider=lambda: None,
            transport=_FakeTransport(),
        )
        is None
    )
    transport = _FakeTransport(payload=_success_payload())
    port = live.build_openai_live_provider_port(
        api_key_provider=lambda: SECRET,
        transport=transport,
    )
    assert port is not None
    assert port.live_provider is True
    result = c6_2.interpret_model_step(
        _request(),
        port,
        attempt_id=ATTEMPT_ID,
    )
    assert result.receipt.outcome_code == "ProviderStepSucceeded"


def test_environment_defaults_resolve_without_credential_read(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("C6_2_LIVE_MODEL", raising=False)
    port = live.OpenAILiveProviderPort(transport=_FakeTransport())
    assert port.model == live.DEFAULT_MODEL
    assert port.base_url == live.DEFAULT_BASE_URL
    assert port.timeout_seconds == 30.0

    monkeypatch.setenv("OPENAI_API_BASE", "https://fixture.example/v1/")
    monkeypatch.setenv("C6_2_LIVE_MODEL", "fixture-model")
    configured = live.OpenAILiveProviderPort(transport=_FakeTransport())
    assert configured.model == "fixture-model"
    assert configured.base_url == "https://fixture.example/v1/"
