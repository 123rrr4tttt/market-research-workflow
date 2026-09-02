"""C6.2 real OpenAI chat completions provider port.

The live port keeps the frozen C6.2 receipt boundary: one explicit
``next_step`` increments ``provider_calls``, credentials are never copied into
receipts or error messages, and every pre-send unknown outcome is read back as
``NON_START_PROOF``. HTTP is performed with stdlib ``urllib.request`` only.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from app.successor_runtime.capabilities import agent_core_c6_2 as c6_2
from app.successor_runtime.capabilities.agent_core_c6_common import (
    AgentModelStep,
    freeze_c6_json_object,
)
from app.successor_runtime.capabilities.checksum import content_digest

__all__ = [
    "CHAT_COMPLETIONS_PATH",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "ENV_VAR_NAME",
    "OpenAILiveProviderPort",
    "OpenAIOutcomeUnknownBeforeSendError",
    "build_openai_live_provider_port",
    "openai_authority_digest",
]

ENV_VAR_NAME = "OPENAI_API_KEY"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
CHAT_COMPLETIONS_PATH = "/chat/completions"

_AUTHORITY_PAYLOAD = {
    "schema": "mrw.successor.agent-core.c6-2.authority.v1",
    "canonical_owner": "agent_core.c6_2.v1",
    "authority": "named provider-step interpretation only",
    "grant_scope": "project",
}
_MAX_PROBE_TOKENS = 16
_PROBE_TEMPERATURE = 0


class OpenAIOutcomeUnknownBeforeSendError(RuntimeError):
    """Marker for a provider call whose outcome is unknown before HTTP send."""


class _OpenAIProtocolResponseError(ValueError):
    """Marker for a malformed or non-JSON chat completions response."""


def openai_authority_digest() -> str:
    """Return the C6.2 authority digest required for this live binding."""

    return content_digest(_AUTHORITY_PAYLOAD)


def _default_api_key_provider() -> str | None:
    return os.getenv(ENV_VAR_NAME)


def _decode_http_body(raw: bytes, *, require_object: bool) -> dict[str, Any]:
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        if require_object:
            raise _OpenAIProtocolResponseError(
                "OpenAI chat completions response is not valid JSON"
            ) from exc
        return {}
    if not isinstance(decoded, dict):
        if require_object:
            raise _OpenAIProtocolResponseError(
                "OpenAI chat completions response is not a JSON object"
            )
        return {}
    return decoded


def _openai_chat_transport(
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[int, dict[str, Any]]:
    """POST one OpenAI chat completions request and decode its JSON body."""

    encoded = json.dumps(body, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=encoded,
        headers=dict(headers),
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=float(timeout_seconds)
        ) as response:
            status = int(getattr(response, "status", None) or response.getcode() or 200)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()
    return int(status), _decode_http_body(
        raw,
        require_object=status == 200,
    )


class OpenAILiveProviderPort:
    """C6.2 provider port that performs one real OpenAI chat completion."""

    interpreter_id = "live.agent_core.c6_2.openai_provider_port.v1"
    live_provider = True
    provider_calls = 0

    def __init__(
        self,
        api_key_provider: Callable[[], str | None] | None = None,
        transport: Callable[
            [str, dict[str, Any], dict[str, str], float],
            tuple[int, dict[str, Any]],
        ]
        | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_key_provider = api_key_provider or _default_api_key_provider
        self._transport = transport or _openai_chat_transport
        self.model = self._resolve_text_setting(
            model,
            os.getenv("C6_2_LIVE_MODEL"),
            DEFAULT_MODEL,
        )
        self.base_url = self._resolve_text_setting(
            base_url,
            os.getenv("OPENAI_API_BASE"),
            DEFAULT_BASE_URL,
        )
        self.timeout_seconds = (
            30.0 if timeout_seconds is None else float(timeout_seconds)
        )
        self.requests: list[c6_2.AgentModelStepRequest] = []
        self.started: list[dict[str, Any]] = []

    @staticmethod
    def _resolve_text_setting(
        explicit: str | None,
        env_value: str | None,
        default: str,
    ) -> str:
        for candidate in (explicit, env_value, default):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return default

    @staticmethod
    def _provider_failure(
        code: str,
        message: str,
        *,
        retryable: bool,
    ) -> c6_2.ProviderFailure:
        return c6_2.ProviderFailure(
            code=code,
            message=message,
            retryable=retryable,
        )

    def next_step(
        self,
        request: c6_2.AgentModelStepRequest,
    ) -> c6_2.ProviderStepOutcome:
        self.provider_calls += 1
        self.requests.append(request)
        self.started.append(
            {
                "session_id": request.session_id,
                "turn_id": request.turn_id,
                "iteration": request.iteration,
                "provider_calls": self.provider_calls,
            }
        )
        api_key = self._api_key_provider()
        if not api_key or not str(api_key).strip():
            return self._provider_failure(
                "ProviderCredentialRejected",
                "OpenAI credential is missing",
                retryable=False,
            )

        url = f"{self.base_url.rstrip('/')}{CHAT_COMPLETIONS_PATH}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        user_probe = (
            "PARITY_OK probe for session "
            f"{request.session_id}, turn {request.turn_id}, "
            f"iteration {request.iteration}."
        )
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a C6.2 provider parity probe. "
                        "Reply with exactly PARITY_OK and nothing else."
                    ),
                },
                {"role": "user", "content": user_probe},
            ],
            "max_tokens": _MAX_PROBE_TOKENS,
            "temperature": _PROBE_TEMPERATURE,
        }
        try:
            status, response = self._transport(
                url,
                body,
                headers,
                self.timeout_seconds,
            )
        except OpenAIOutcomeUnknownBeforeSendError:
            return self._provider_failure(
                "ProviderOutcomeUnknown",
                "OpenAI provider outcome is unknown before send",
                retryable=False,
            )
        except _OpenAIProtocolResponseError:
            return self._provider_failure(
                "ProviderProtocolInvalid",
                "OpenAI chat completions response is not valid JSON",
                retryable=False,
            )
        except (ValueError, TypeError):
            return self._provider_failure(
                "ProviderProtocolInvalid",
                "OpenAI chat completions transport returned invalid data",
                retryable=False,
            )
        except TimeoutError:
            return self._provider_failure(
                "ProviderTimeout",
                "OpenAI chat completions request timed out",
                retryable=True,
            )
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                return self._provider_failure(
                    "ProviderTimeout",
                    "OpenAI chat completions request timed out",
                    retryable=True,
                )
            return self._provider_failure(
                "ProviderUnavailable",
                "OpenAI chat completions endpoint is unavailable",
                retryable=True,
            )
        except (ConnectionError, OSError):
            return self._provider_failure(
                "ProviderUnavailable",
                "OpenAI chat completions endpoint is unavailable",
                retryable=True,
            )
        except Exception:  # noqa: BLE001 - transport failure is a typed outcome
            return self._provider_failure(
                "ProviderUnavailable",
                "OpenAI chat completions transport failed",
                retryable=True,
            )

        if status == 401 or status == 403:
            return self._provider_failure(
                "ProviderCredentialRejected",
                "OpenAI credential was rejected",
                retryable=False,
            )
        if status == 429:
            return self._provider_failure(
                "ProviderRateLimited",
                "OpenAI chat completions rate limit was reached",
                retryable=True,
            )
        if status == 408 or status >= 500:
            return self._provider_failure(
                "ProviderUnavailable",
                "OpenAI chat completions endpoint is unavailable",
                retryable=True,
            )
        if status != 200:
            return self._provider_failure(
                "ProviderProtocolInvalid",
                "OpenAI chat completions returned an unexpected status",
                retryable=False,
            )
        if not isinstance(response, dict):
            return self._provider_failure(
                "ProviderProtocolInvalid",
                "OpenAI chat completions response is not a JSON object",
                retryable=False,
            )
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            return self._provider_failure(
                "ProviderProtocolInvalid",
                "OpenAI chat completions response has no choices",
                retryable=False,
            )
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return self._provider_failure(
                "ProviderProtocolInvalid",
                "OpenAI chat completions choice is malformed",
                retryable=False,
            )
        choice_message = first_choice.get("message")
        if not isinstance(choice_message, dict):
            return self._provider_failure(
                "ProviderProtocolInvalid",
                "OpenAI chat completions message is malformed",
                retryable=False,
            )
        content = choice_message.get("content")
        if not isinstance(content, str):
            return self._provider_failure(
                "ProviderProtocolInvalid",
                "OpenAI chat completions message has no content",
                retryable=False,
            )
        content = content.strip()
        if not content:
            return self._provider_failure(
                "ProviderProtocolInvalid",
                "OpenAI chat completions message content is empty",
                retryable=False,
            )
        step = AgentModelStep(
            schema_version="mrw.successor.agent-core.c6.model-step.v1",
            step_type="final_answer",
            content=content,
            metadata=freeze_c6_json_object(
                {
                    "provider": "openai",
                    "live": True,
                    "model": self.model,
                    "finish_reason": first_choice.get("finish_reason"),
                    "iteration": request.iteration,
                    "provider_calls": self.provider_calls,
                }
            ),
        )
        return c6_2.ProviderStepSucceeded(
            schema_version="mrw.successor.agent-core.c6-2.step-success.v1",
            step=step,
            provider_observation_ref=(
                f"project-value:observation:c6-2-live:"
                f"{request.session_id}:{request.turn_id}"
            ),
            provider_calls=self.provider_calls,
        )

    def readback(self, attempt_id: str) -> c6_2.ProviderReadback:
        return c6_2.ProviderReadback(
            schema_version=c6_2.PROVIDER_READBACK_SCHEMA_REF,
            attempt_id=attempt_id,
            status="NON_START_PROOF",
        )


def build_openai_live_provider_port(
    *,
    api_key_provider: Callable[[], str | None] | None = None,
    transport: Callable[
        [str, dict[str, Any], dict[str, str], float],
        tuple[int, dict[str, Any]],
    ]
    | None = None,
    model: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float = 30.0,
) -> OpenAILiveProviderPort | None:
    """Return a live OpenAI port only when a credential is available."""

    key_provider = api_key_provider or _default_api_key_provider
    api_key = key_provider()
    if not api_key or not str(api_key).strip():
        return None
    return OpenAILiveProviderPort(
        api_key_provider=key_provider,
        transport=transport,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
