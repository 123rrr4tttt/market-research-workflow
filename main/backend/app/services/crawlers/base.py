from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Protocol, TypeAlias, runtime_checkable

from functorial_kit import Failure
from app.successor_runtime.capabilities.source_contracts import (
    CancelReceipt,
    ProviderAttemptRef,
    ProviderReadbackResult,
    ReadbackTerminal,
    ReadbackUnavailable,
    ReadbackWaiting,
    AuthoritativeProviderReadback,
)


CrawlerJsonAtom: TypeAlias = None | bool | int | float | str
CrawlerJsonValue: TypeAlias = (
    CrawlerJsonAtom | list["CrawlerJsonValue"] | dict[str, "CrawlerJsonValue"]
)
CrawlerJsonObject: TypeAlias = dict[str, CrawlerJsonValue]
CrawlerPollOutcome: TypeAlias = CrawlerJsonObject | Failure
CrawlerCancelOutcome: TypeAlias = CancelReceipt | CrawlerJsonObject | Failure
CrawlerTerminalStatus: TypeAlias = Literal["COMPLETED", "FAILED", "CANCELLED"]


def _empty_crawler_json_object() -> CrawlerJsonObject:
    return {}


@dataclass(slots=True)
class CrawlerDispatchRequest:
    provider: str
    project: str
    spider: str
    arguments: CrawlerJsonObject = field(default_factory=_empty_crawler_json_object)
    settings: CrawlerJsonObject = field(default_factory=_empty_crawler_json_object)
    version: str | None = None
    priority: int | None = None
    job_id: str | None = None
    idempotency_key: str | None = None
    attempt_id: str | None = None
    request_digest: str | None = None

    def __post_init__(self) -> None:
        """Bind one dispatch to a stable request/attempt identity."""
        digest = crawler_request_digest(self)
        if not self.request_digest:
            self.request_digest = digest
        if not self.idempotency_key:
            self.idempotency_key = f"crawler:{self.provider}:{digest}"
        if not self.attempt_id:
            self.attempt_id = f"attempt:crawler:{digest}"


def crawler_request_digest(request: CrawlerDispatchRequest) -> str:
    """Compute the canonical digest used for durable crawler binding."""

    canonical = {
        "provider": request.provider,
        "project": request.project,
        "spider": request.spider,
        "arguments": dict(request.arguments or {}),
        "settings": dict(request.settings or {}),
        "version": request.version,
        "priority": request.priority,
        "job_id": request.job_id,
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


@dataclass(slots=True)
class CrawlerDispatchResult:
    """Provider acknowledgement; completion is valid only with terminal_readback."""

    provider_type: str
    provider_status: str
    provider_job_id: str | None = None
    attempt_count: int | None = None
    raw: CrawlerJsonObject = field(default_factory=_empty_crawler_json_object)
    idempotency_key: str | None = None
    attempt_id: str | None = None
    terminal_readback: ProviderReadbackResult | None = None
    dispatch_acknowledged: bool | None = None

    def __post_init__(self) -> None:
        if self.dispatch_acknowledged is None:
            self.dispatch_acknowledged = str(self.provider_status or "").strip().lower() in {
                "ok",
                "queued",
                "scheduled",
                "running",
                "accepted",
                "completed",
            }


CrawlerDispatchOutcome = CrawlerDispatchResult | Failure

# Scrapyd and compatible crawler schedulers use these values for a dispatch
# that was accepted by the provider.  Keep the interpretation in this module
# so source-library and collect projections cannot drift apart.
CRAWLER_DISPATCH_ACK_STATUSES = frozenset(
    {"ok", "queued", "scheduled", "running", "accepted", "completed"}
)
CRAWLER_ACCEPTED_STATUSES = frozenset(
    {"ok", "queued", "scheduled", "running", "accepted"}
)
CRAWLER_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


def is_crawler_dispatch_accepted(status: str | None) -> bool:
    return str(status or "").strip().lower() in CRAWLER_ACCEPTED_STATUSES


def is_crawler_dispatch_acknowledged(status: str | None) -> bool:
    """Whether a provider response acknowledges dispatch, not completion."""

    return str(status or "").strip().lower() in CRAWLER_DISPATCH_ACK_STATUSES


def is_crawler_terminal_status(status: str | None) -> bool:
    return str(status or "").strip().lower() in CRAWLER_TERMINAL_STATUSES


def typed_crawler_readback(
    *,
    attempt_id: str,
    provider_job_id: str | None,
    payload: CrawlerPollOutcome,
) -> ProviderReadbackResult:
    """Map provider poll output into the shared C2.3 readback vocabulary."""

    attempt_ref = f"provider-attempt:{attempt_id}"
    observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(payload, Failure):
        return ReadbackUnavailable(attempt_ref=attempt_ref, reason="crawler poll returned a non-object payload")
    status = str(payload.get("provider_status") or payload.get("status") or "").strip().lower()
    if status in CRAWLER_TERMINAL_STATUSES:
        terminal_status: CrawlerTerminalStatus
        if status == "completed":
            terminal_status = "COMPLETED"
        elif status == "failed":
            terminal_status = "FAILED"
        else:
            terminal_status = "CANCELLED"
        raw_provider_job_id = payload.get("external_job_id")
        readback = AuthoritativeProviderReadback(
            attempt_ref=attempt_ref,
            provider_job_id=provider_job_id or (str(raw_provider_job_id) if raw_provider_job_id else None),
            terminal_status=terminal_status,
            readback_receipt_id=str(payload.get("readback_receipt_id") or f"readback:crawler:{attempt_id}"),
            observed_at=str(payload.get("observed_at") or observed_at),
        )
        return ReadbackTerminal(readback=readback)
    if status in CRAWLER_DISPATCH_ACK_STATUSES:
        return ReadbackWaiting(attempt_ref=attempt_ref, observed_at=str(payload.get("observed_at") or observed_at))
    return ReadbackUnavailable(
        attempt_ref=attempt_ref,
        reason=str(payload.get("reason") or "crawler provider did not expose authoritative readback"),
    )


class CrawlerProvider(Protocol):
    provider_type: str

    def dispatch(self, request: CrawlerDispatchRequest) -> CrawlerDispatchOutcome:
        ...

    def poll(
        self,
        *,
        external_job_id: str,
        project: str | None = None,
        spider: str | None = None,
        options: CrawlerJsonObject | None = None,
    ) -> CrawlerPollOutcome:
        """Return provider observation; terminal completion requires typed readback."""
        ...


@runtime_checkable
class CrawlerCancelPort(Protocol):
    """Optional provider cancellation boundary used by the durable bridge."""

    def cancel(
        self,
        *,
        attempt_ref: ProviderAttemptRef,
        request: CrawlerDispatchRequest,
        external_job_id: str | None,
        project: str,
        spider: str,
    ) -> CrawlerCancelOutcome:
        ...


__all__ = [
    "CrawlerDispatchRequest",
    "CrawlerDispatchResult",
    "CrawlerDispatchOutcome",
    "CrawlerJsonAtom",
    "CrawlerJsonValue",
    "CrawlerJsonObject",
    "CrawlerPollOutcome",
    "CrawlerCancelOutcome",
    "CrawlerCancelPort",
    "crawler_request_digest",
    "CRAWLER_ACCEPTED_STATUSES",
    "CRAWLER_DISPATCH_ACK_STATUSES",
    "CRAWLER_TERMINAL_STATUSES",
    "is_crawler_dispatch_accepted",
    "is_crawler_dispatch_acknowledged",
    "is_crawler_terminal_status",
    "typed_crawler_readback",
    "CrawlerProvider",
]
