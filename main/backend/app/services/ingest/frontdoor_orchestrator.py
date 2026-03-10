from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .frontdoor_contract import FRONTDOOR_STAGES, apply_stage_update, build_frontdoor_envelope

StageHandler = Callable[[dict[str, Any]], Mapping[str, Any] | None]


@dataclass(frozen=True)
class FrontDoorOrchestratorConfig:
    stop_on_failed: bool = True


class FrontDoorOrchestrator:
    """Minimal stage orchestrator for front-door ingest workflows.

    The orchestrator runs six canonical stages in order:
    unwrap -> gate -> fetch -> extract -> quality -> persist.

    Each stage handler receives a context dict and may return a partial update.
    A partial update can include envelope fields and any additional payload keys.
    """

    def __init__(
        self,
        *,
        stage_handlers: Mapping[str, StageHandler] | None = None,
        config: FrontDoorOrchestratorConfig | None = None,
    ) -> None:
        self._stage_handlers: dict[str, StageHandler] = {
            str(name): handler
            for name, handler in dict(stage_handlers or {}).items()
            if str(name) in FRONTDOOR_STAGES and callable(handler)
        }
        self._config = config or FrontDoorOrchestratorConfig()

    def run(
        self,
        *,
        payload: Mapping[str, Any] | None = None,
        trace_id: str | None = None,
        request_key: str | None = None,
        stage_handlers: Mapping[str, StageHandler] | None = None,
    ) -> dict[str, Any]:
        envelope = build_frontdoor_envelope(
            status="success",
            reason_code="ok",
            stage=FRONTDOOR_STAGES[0],
            retryable=False,
            trace_id=trace_id,
            request_key=request_key,
            diagnostics={
                "orchestrator": "frontdoor",
                "stages_total": len(FRONTDOOR_STAGES),
            },
            extra={"payload": dict(payload or {})},
        )

        handlers = dict(self._stage_handlers)
        if stage_handlers:
            for stage, handler in stage_handlers.items():
                stage_name = str(stage)
                if stage_name in FRONTDOOR_STAGES and callable(handler):
                    handlers[stage_name] = handler

        for stage in FRONTDOOR_STAGES:
            envelope["stage"] = stage
            handler = handlers.get(stage)
            if handler is None:
                apply_stage_update(
                    envelope,
                    stage=stage,
                    update={
                        "diagnostics": {
                            f"stage.{stage}.status": "skipped",
                            f"stage.{stage}.reason": "handler_not_configured",
                        }
                    },
                )
                continue

            context = {
                "stage": stage,
                "payload": dict(envelope.get("payload") or {}),
                "envelope": dict(envelope),
            }
            try:
                result = handler(context)
            except Exception as exc:  # noqa: BLE001
                apply_stage_update(
                    envelope,
                    stage=stage,
                    update={
                        "status": "failed",
                        "reason_code": "unexpected_exception",
                        "retryable": True,
                        "degradation_flags": ["frontdoor_stage_exception", f"stage_exception:{stage}"],
                        "diagnostics": {
                            f"stage.{stage}.status": "exception",
                            f"stage.{stage}.error": str(exc) or exc.__class__.__name__,
                        },
                    },
                )
                if self._config.stop_on_failed:
                    break
                continue

            if result:
                update_payload = dict(result)
                update_diag = dict(update_payload.get("diagnostics") or {})
                stage_status_key = f"stage.{stage}.status"
                stage_reason_key = f"stage.{stage}.reason"
                if stage_status_key not in update_diag:
                    update_status = str(update_payload.get("status") or "").strip().lower()
                    stage_status = "failed" if update_status == "failed" else "ok"
                    update_diag[stage_status_key] = stage_status
                if stage_reason_key not in update_diag:
                    update_reason = str(update_payload.get("reason_code") or "").strip().lower()
                    if update_reason and update_reason != "ok":
                        update_diag[stage_reason_key] = update_reason
                if update_diag:
                    update_payload["diagnostics"] = update_diag
                apply_stage_update(envelope, stage=stage, update=update_payload)
            else:
                apply_stage_update(
                    envelope,
                    stage=stage,
                    update={"diagnostics": {f"stage.{stage}.status": "ok"}},
                )

            if self._config.stop_on_failed and str(envelope.get("status") or "").lower() == "failed":
                break

        return envelope


__all__ = [
    "FrontDoorOrchestrator",
    "FrontDoorOrchestratorConfig",
    "StageHandler",
]
