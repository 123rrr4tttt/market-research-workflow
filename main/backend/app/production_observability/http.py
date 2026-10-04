from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from prometheus_client import REGISTRY, Counter, Histogram
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse


PRODUCTION_REQUEST_METRIC_NAME = "market_api_production_requests_total"
PRODUCTION_REQUEST_LATENCY_METRIC_NAME = "market_api_production_request_latency_seconds"
_ERROR_LOGGER = logging.getLogger("app.production_observability.http")


def _existing_collector(name: str) -> Any:
    return REGISTRY._names_to_collectors.get(name)


PRODUCTION_REQUEST_COUNT = _existing_collector(PRODUCTION_REQUEST_METRIC_NAME) or Counter(
    PRODUCTION_REQUEST_METRIC_NAME,
    "Production API request count by stable route binding",
    ("domain", "route", "release_version", "method", "status"),
)
PRODUCTION_REQUEST_LATENCY = _existing_collector(
    PRODUCTION_REQUEST_LATENCY_METRIC_NAME
) or Histogram(
    PRODUCTION_REQUEST_LATENCY_METRIC_NAME,
    "Production API request latency by stable route binding",
    ("domain", "route", "release_version"),
)
REQUEST_COUNT = _existing_collector("market_api_requests_total") or Counter(
    "market_api_requests_total",
    "API request count",
    ("method", "endpoint", "status"),
)
REQUEST_LATENCY = _existing_collector("market_api_request_latency_seconds") or Histogram(
    "market_api_request_latency_seconds",
    "API request latency",
    ("endpoint",),
)


def _terminal_outcome(
    request: Request,
    response: Response,
    terminal_outcome: str | None,
) -> str | None:
    if terminal_outcome is not None:
        return terminal_outcome
    stream_state = getattr(request.state, "production_stream_state", None)
    if isinstance(stream_state, dict):
        stream_outcome = stream_state.get("terminal_outcome")
        if stream_outcome is not None:
            return str(stream_outcome)
    if (response.headers.get("X-Error-Code") or "").strip():
        return "application_error"
    return None


def _latch_observation_failure(
    controller: Any,
    *,
    request_id: str,
    reason: str,
    exc: Exception,
) -> None:
    _ERROR_LOGGER.warning(
        "production observation failed request_id=%s reason=%s error_type=%s",
        request_id,
        reason,
        type(exc).__name__,
        exc_info=exc,
    )
    if controller is None:
        return
    try:
        controller.latch_runtime_failure(
            request_id=request_id,
            reason=reason,
        )
    except Exception as latch_exc:  # noqa: BLE001 - latching cannot replace a response
        _ERROR_LOGGER.error(
            "production observation latch failed request_id=%s error_type=%s",
            request_id,
            type(latch_exc).__name__,
            exc_info=latch_exc,
        )


def observe_production_http_request(
    *,
    controller: Any,
    request_id: str,
    status_code: int,
    terminal_outcome: str | None = None,
    latency_seconds: float | None = None,
) -> None:
    """Forward one terminal HTTP observation to the installed R7 controller."""

    controller.observe_http_request(
        observation_id=request_id,
        status_code=status_code,
        terminal_outcome=terminal_outcome,
        latency_seconds=latency_seconds,
    )


def finalize_request_metrics(
    *,
    request: Request,
    response: Response,
    request_id: str,
    endpoint: str,
    metric_labels: dict[str, str],
    elapsed: float,
    production_runtime: bool,
    controller: Any,
    terminal_outcome: str | None = None,
) -> None:
    outcome = _terminal_outcome(request, response, terminal_outcome)
    if production_runtime and controller is not None:
        try:
            observe_production_http_request(
                controller=controller,
                request_id=request_id,
                status_code=response.status_code,
                terminal_outcome=outcome,
                latency_seconds=elapsed,
            )
        except Exception as exc:  # noqa: BLE001 - observation cannot replace a response
            _latch_observation_failure(
                controller,
                request_id=f"{request_id}:production-http-observation",
                reason=f"production HTTP observation failed: {type(exc).__name__}",
                exc=exc,
            )

    count_labels = {
        **metric_labels,
        "method": request.method,
        "status": str(response.status_code),
    }
    try:
        REQUEST_COUNT.labels(request.method, endpoint, response.status_code).inc()
        REQUEST_LATENCY.labels(endpoint).observe(elapsed)
        PRODUCTION_REQUEST_COUNT.labels(**count_labels).inc()
        PRODUCTION_REQUEST_LATENCY.labels(**metric_labels).observe(elapsed)
    except Exception as exc:  # noqa: BLE001 - metric projection cannot replace a response
        _latch_observation_failure(
            controller,
            request_id=f"{request_id}:legacy-request-metrics",
            reason=f"legacy request metrics failed: {type(exc).__name__}",
            exc=exc,
        )


def is_sse_response(response: Response) -> bool:
    if isinstance(response, StreamingResponse):
        media_type = (response.media_type or "").lower()
        if media_type == "text/event-stream":
            return True
    content_type = (response.headers.get("content-type") or "").lower()
    return content_type.startswith("text/event-stream")


def wrap_stream_response(
    request: Request,
    response: StreamingResponse,
    *,
    finalize: Callable[[str], None],
) -> StreamingResponse:
    """Observe a stream only after its original iterator reaches a terminal state."""

    source_iterator = response.body_iterator
    finalized = False

    def _finalize_once(outcome: str) -> None:
        nonlocal finalized
        if finalized:
            return
        finalized = True
        try:
            finalize(outcome)
        except Exception as exc:  # noqa: BLE001 - finalization cannot replace the stream result
            _ERROR_LOGGER.error(
                "production stream finalization failed error_type=%s",
                type(exc).__name__,
                exc_info=exc,
            )

    async def _observed_iterator():
        try:
            async for chunk in source_iterator:
                yield chunk
        except BaseException as exc:
            _finalize_once("terminal_failure" if isinstance(exc, GeneratorExit) else "iterator_failure")
            raise
        stream_state = getattr(request.state, "production_stream_state", None)
        outcome = "success"
        if isinstance(stream_state, dict):
            outcome = str(stream_state.get("terminal_outcome") or outcome)
        _finalize_once(outcome)

    response.body_iterator = _observed_iterator()
    return response


__all__ = [
    "PRODUCTION_REQUEST_COUNT",
    "PRODUCTION_REQUEST_LATENCY_METRIC_NAME",
    "PRODUCTION_REQUEST_LATENCY",
    "PRODUCTION_REQUEST_METRIC_NAME",
    "finalize_request_metrics",
    "is_sse_response",
    "observe_production_http_request",
    "wrap_stream_response",
]
