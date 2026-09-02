"""Pure successor line-event/readback port (S1 horizontal slice).

The port re-expresses the legacy worker readback metadata surface as typed,
immutable line-event chains.  It never imports or executes donor code and
performs no runtime, provider, scheduler or canonical-write effect.

Semantic invariants
-------------------
* A line key is canonicalized and restricted to the known worker-required
  lanes; an unknown key fails closed.
* Events are inserted only in canonical order.  Status-derived lifecycle
  markers (accepted/queued/started) may be scaffolded, but the terminal
  persistence observation event is never fabricated from a status.
* Persistence is undecidable until the line's terminal readback event is
  present in the chain.
* Every transition returns a new immutable record; state is never mutated in
  place.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

SCHEMA_REF = "mrw.successor.runtime.c5-4.line-event-readback.v1"
AUTHORITY_SNAPSHOT = {
    "canonical_write": False,
    "live_provider": False,
    "external_delivery": False,
    "scheduler": False,
    "executor": False,
    "cutover": False,
}

SUCCESS_TERMINAL_STATUSES = frozenset(
    {"completed", "succeeded", "applied", "available", "healthy"}
)
FAILURE_STATUSES = frozenset({"failed", "canceled", "blocked", "rejected"})
RUNNING_STATUSES = frozenset({"running", "started", "active"})
QUEUED_STATUSES = frozenset({"queued", "scheduled", "pending"})


def _status_is_success(status: str | None) -> bool:
    return status in SUCCESS_TERMINAL_STATUSES


def _status_is_failure(status: str | None) -> bool:
    return status in FAILURE_STATUSES


def _status_is_running(status: str | None) -> bool:
    return status in RUNNING_STATUSES


def _status_is_queued(status: str | None) -> bool:
    return status in QUEUED_STATUSES


def _event_prefix_limit(
    line_key: str,
    *,
    event: str | None,
    status: str | None,
) -> int:
    """Return the canonical prefix length covered by one typed observation.

    An explicit event always admits its canonical prefix.  Status-only
    observations admit only the queued/running lifecycle prefixes; success
    status never fabricates the terminal readback event by itself.
    """

    canonical = LINE_EVENT_CHAINS[line_key]
    limit = 0
    if _status_is_queued(status):
        limit = max(limit, 2)
    if _status_is_running(status):
        limit = max(limit, 3)
    if event is not None and event in canonical:
        limit = max(limit, canonical.index(event) + 1)
    return min(limit, len(canonical))


LINE_EVENT_CHAINS: dict[str, tuple[str, ...]] = {
    "ingest": (
        "submission_accepted",
        "task_queued",
        "worker_started",
        "source_fetch_completed",
        "index_handoff_recorded",
        "readback_persisted",
    ),
    "search_discovery_index": (
        "search_or_discovery_run_accepted",
        "task_queued",
        "worker_started",
        "index_refresh_started",
        "index_refresh_completed",
        "results_readback_persisted",
    ),
    "resource_source_library": (
        "resource_action_accepted",
        "task_queued",
        "worker_started",
        "adapter_capture_completed",
        "source_lifecycle_updated",
        "readback_persisted",
    ),
    "writing_knowledge_graph_agent": (
        "agent_batch_submitted",
        "task_queued",
        "worker_started",
        "agent_event_persisted",
        "approval_state_recorded",
        "artifact_readback_persisted",
    ),
}

KNOWN_LINE_KEYS = frozenset(LINE_EVENT_CHAINS)
TERMINAL_READBACK_EVENTS = frozenset(
    {
        "readback_persisted",
        "results_readback_persisted",
        "artifact_readback_persisted",
    }
)

DEFAULT_TIMESTAMP = "1970-01-01T00:00:00+00:00"


def normalize_line_key(value: Any) -> str | None:
    """Normalize one raw line key to the typed snake_case key form."""

    if value is None:
        return None
    text = str(value).strip().lower()
    return text.replace("-", "_").replace(" ", "_") or None


def non_empty_text(value: Any) -> str | None:
    """Return trimmed text, or None for empty/missing values."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _canonical_json(value: Any) -> str:
    if isinstance(value, dict):
        payload = {key: _canonical_json(item) for key, item in sorted(value.items())}
    elif isinstance(value, (list, tuple)):
        payload = [_canonical_json(item) for item in value]
    else:
        return value
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def record_digest(record: LineEventReadbackRecord) -> str:
    """Return the content digest of one immutable readback record."""

    body = {
        "schema": SCHEMA_REF,
        "line_key": record.line_key,
        "status": record.status,
        "context": [
            (key, value)
            for key, value in (
                ("task_id", record.task_id),
                ("run_id", record.run_id),
                ("trace_id", record.trace_id),
                ("worker_name", record.worker_name),
                ("queue", record.queue),
            )
            if value is not None
        ],
        "events": [
            {
                "event": event.event,
                "source": event.source,
                "observed_at": event.observed_at,
            }
            for event in record.events
        ],
    }
    return hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


def _iso_timestamp_or_default(value: Any) -> str:
    if value is None:
        return DEFAULT_TIMESTAMP
    text = str(value).strip()
    return text or DEFAULT_TIMESTAMP


def _normalize_status(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


class LineEventReadbackError(ValueError):
    """Base typed failure for line-event readback operations."""


class UnknownLineKeyError(LineEventReadbackError):
    """Raised when a line key is absent or not in the known lane registry."""


class UnknownLineEventError(LineEventReadbackError):
    """Raised when an observed event is not part of the line's canonical chain."""


class IllegalEventMigrationError(LineEventReadbackError):
    """Raised when an event violates canonical order or immutable state."""


@dataclass(frozen=True, slots=True)
class LineEvent:
    """One typed event observation within a canonical line-event chain."""

    event: str
    source: str
    observed_at: str = DEFAULT_TIMESTAMP


@dataclass(frozen=True, slots=True)
class LineEventReadbackRecord:
    """Immutable successor state for one line-event/readback chain.

    The record is deliberately frozen: transitions create new records and
    never mutate existing state.  ``digest`` is a content address; callers
    that decode untrusted bytes should call :meth:`verify_digest`.
    """

    line_key: str
    events: tuple[LineEvent, ...] = ()
    status: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    worker_name: str | None = None
    queue: str | None = None
    digest: str = field(default="", compare=False, repr=False)

    def __post_init__(self) -> None:
        normalized = normalize_line_key(self.line_key)
        if normalized not in KNOWN_LINE_KEYS:
            raise UnknownLineKeyError(f"unknown line_key {self.line_key!r}")
        canonical = LINE_EVENT_CHAINS[normalized]
        event_names = tuple(item.event for item in self.events)
        if len(set(event_names)) != len(event_names):
            raise IllegalEventMigrationError(
                f"line {normalized} contains duplicate events"
            )
        if any(name not in canonical for name in event_names):
            raise UnknownLineEventError(
                f"line {normalized} contains an event outside its canonical chain"
            )
        if event_names != canonical[: len(event_names)]:
            raise IllegalEventMigrationError(
                f"line {normalized} event chain has a gap or is not canonical"
            )
        object.__setattr__(self, "line_key", normalized)
        if self.digest == "":
            object.__setattr__(self, "digest", record_digest(self))

    def verify_digest(self) -> None:
        """Fail closed when the content address no longer matches content."""

        if self.digest != record_digest(self):
            raise IllegalEventMigrationError(
                f"line {self.line_key} readback record digest mismatch"
            )

    @property
    def event_names(self) -> tuple[str, ...]:
        return tuple(item.event for item in self.events)

    @property
    def persistence_observed(self) -> bool:
        return (
            self.event_names[-1] in TERMINAL_READBACK_EVENTS if self.events else False
        )


@dataclass(frozen=True, slots=True)
class LineEventReadbackResult:
    """Typed, non-authoritative readback outcome for one line chain."""

    line_key: str
    events: tuple[LineEvent, ...]
    status: str | None
    persistence_decidable: bool
    persistence_observed: bool
    canonical_write_authority: bool = False
    reason: str | None = None


class LineEventReadbackPort:
    """Pure typed transition/readback port for successor worker line events.

    The port holds no mutable state and performs no I/O.  Its authority
    ceiling is all-false; any live binding must remain an explicit, separate
    interpreter with its own authority review.
    """

    interpreter_id = "pure.successor_runtime.c5_4.line_event_readback.v1"
    schema_ref = SCHEMA_REF
    canonical_write_authority = False
    live_provider_authority = False
    external_delivery_authority = False
    scheduler_authority = False
    executor_authority = False
    cutover_authority = False

    @classmethod
    def empty(cls, line_key: str) -> LineEventReadbackRecord:
        normalized = normalize_line_key(line_key)
        if normalized not in KNOWN_LINE_KEYS:
            raise UnknownLineKeyError(f"unknown line_key {line_key!r}")
        return LineEventReadbackRecord(line_key=normalized)

    @classmethod
    def observe(
        cls,
        record: LineEventReadbackRecord,
        *,
        event: str | None = None,
        status: str | None = None,
        source: str = "runtime",
        observed_at: Any = None,
        task_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        worker_name: str | None = None,
        queue: str | None = None,
    ) -> LineEventReadbackRecord:
        """Record one typed observation and return a new immutable record.

        ``event`` is an explicitly observed canonical lifecycle step; it may
        be omitted when the caller observes only a status transition.  A
        success status is admitted only after the full pre-terminal chain is
        recorded and never fabricates the terminal readback observation; the
        terminal event remains pending until explicitly observed.
        """

        record.verify_digest()
        canonical = LINE_EVENT_CHAINS[record.line_key]
        resolved_status = _normalize_status(status)
        observed_name = non_empty_text(event)
        if observed_name is not None:
            normalized_event = observed_name.lower()
            if normalized_event not in canonical:
                raise UnknownLineEventError(
                    f"line {record.line_key} has no canonical event {observed_name!r}"
                )
            if _status_is_failure(resolved_status):
                raise IllegalEventMigrationError(
                    f"line {record.line_key} cannot record {normalized_event!r} "
                    f"under failure status {resolved_status!r}"
                )
        elif resolved_status is None:
            raise UnknownLineEventError(
                "an observation requires a canonical event or a known status"
            )
        else:
            normalized_event = ""

        prefix_limit = _event_prefix_limit(
            record.line_key,
            event=normalized_event or None,
            status=resolved_status,
        )
        if _status_is_success(resolved_status):
            if normalized_event and normalized_event not in TERMINAL_READBACK_EVENTS:
                raise IllegalEventMigrationError(
                    f"line {record.line_key} cannot record {normalized_event!r} "
                    f"under success status {resolved_status!r}"
                )
            if len(record.events) < len(canonical) - 1:
                raise IllegalEventMigrationError(
                    f"line {record.line_key} has only {len(record.events)} "
                    f"recorded events; success status {resolved_status!r} "
                    "requires every required pre-terminal event to be recorded"
                )
            prefix_limit = len(canonical) - 1
            if normalized_event == canonical[-1]:
                prefix_limit = len(canonical)
        if normalized_event in TERMINAL_READBACK_EVENTS and _status_is_failure(
            resolved_status
        ):
            raise IllegalEventMigrationError(
                f"line {record.line_key} cannot observe {normalized_event!r} "
                f"under failure status {resolved_status!r}"
            )

        recorded_name = normalized_event or (
            canonical[prefix_limit - 1] if prefix_limit > 0 else ""
        )
        effective_status = resolved_status
        if recorded_name in TERMINAL_READBACK_EVENTS:
            if _status_is_failure(effective_status):
                raise IllegalEventMigrationError(
                    f"line {record.line_key} cannot observe {recorded_name!r} "
                    "under a failure status"
                )
            if not _status_is_success(effective_status):
                effective_status = "completed"

        event_names = set(record.event_names)
        for name in canonical[:prefix_limit]:
            event_names.add(name)

        existing_by_name = {item.event: item for item in record.events}
        ordered: list[LineEvent] = []
        for name in canonical:
            if name not in event_names:
                continue
            existing = existing_by_name.get(name)
            if name == recorded_name and existing is None:
                ordered.append(
                    LineEvent(
                        event=name,
                        source=non_empty_text(source) or "runtime",
                        observed_at=_iso_timestamp_or_default(observed_at),
                    )
                )
            elif existing is not None:
                ordered.append(existing)
            else:
                ordered.append(
                    LineEvent(
                        event=name,
                        source="successor_scaffold",
                        observed_at=DEFAULT_TIMESTAMP,
                    )
                )

        if recorded_name == canonical[-1]:
            effective_status = effective_status or "completed"
        elif effective_status is None and ordered and ordered[-1].event == canonical[0]:
            effective_status = "accepted"
        elif effective_status is None and ordered and ordered[-1].event == canonical[1]:
            effective_status = "queued"
        elif effective_status is None and ordered and ordered[-1].event == canonical[2]:
            effective_status = "running"

        try:
            candidate = LineEventReadbackRecord(
                line_key=record.line_key,
                events=tuple(ordered),
                status=effective_status,
                task_id=non_empty_text(task_id) or record.task_id,
                run_id=non_empty_text(run_id) or record.run_id,
                trace_id=non_empty_text(trace_id) or record.trace_id,
                worker_name=non_empty_text(worker_name) or record.worker_name,
                queue=non_empty_text(queue) or record.queue,
            )
        except ValueError as exc:
            raise IllegalEventMigrationError(str(exc)) from exc
        candidate.verify_digest()
        return candidate

    @classmethod
    def merge_context(
        cls,
        record: LineEventReadbackRecord,
        context: dict[str, Any] | None = None,
    ) -> LineEventReadbackRecord:
        """Merge optional identity/routing metadata and return a new record."""

        record.verify_digest()
        merged = dict(context or {})
        return LineEventReadbackRecord(
            line_key=record.line_key,
            events=record.events,
            status=record.status,
            task_id=non_empty_text(merged.get("task_id")) or record.task_id,
            run_id=non_empty_text(merged.get("run_id")) or record.run_id,
            trace_id=non_empty_text(merged.get("trace_id")) or record.trace_id,
            worker_name=non_empty_text(merged.get("worker_name")) or record.worker_name,
            queue=non_empty_text(merged.get("queue")) or record.queue,
        )

    @classmethod
    def readback(
        cls,
        record: LineEventReadbackRecord,
    ) -> LineEventReadbackResult:
        """Return a fail-closed readback view without any persistence claim."""

        record.verify_digest()
        terminal = LINE_EVENT_CHAINS[record.line_key][-1]
        observed = record.persistence_observed
        reason = None
        decidable = False
        if record.status in FAILURE_STATUSES:
            reason = "line status is a typed failure; persistence is not claimed"
        elif observed:
            if record.event_names[:-1] == LINE_EVENT_CHAINS[record.line_key][:-1]:
                decidable = True
            else:
                reason = (
                    f"terminal event {terminal!r} observed before its canonical "
                    "predecessors"
                )
        else:
            reason = (
                f"terminal readback event {terminal!r} not observed; "
                "persistence is undecidable"
            )
        if not decidable and reason is None:
            reason = "persistence is not claimed by a non-terminal observation"
        return LineEventReadbackResult(
            line_key=record.line_key,
            events=record.events,
            status=record.status,
            persistence_decidable=decidable,
            persistence_observed=observed,
            canonical_write_authority=False,
            reason=reason,
        )

    @classmethod
    def build_payload(
        cls,
        record: LineEventReadbackRecord,
    ) -> dict[str, Any]:
        """Build the structured legacy-compatible readback payload view."""

        result = cls.readback(record)
        return {
            "schema": SCHEMA_REF,
            "line_key": record.line_key,
            "status": record.status,
            "task_id": record.task_id,
            "run_id": record.run_id,
            "trace_id": record.trace_id,
            "worker_name": record.worker_name,
            "queue": record.queue,
            "events": [
                {
                    "event": item.event,
                    "event_source": item.source,
                    "timestamp": item.observed_at,
                }
                for item in record.events
            ],
            "readback": {
                "terminal_event": LINE_EVENT_CHAINS[record.line_key][-1],
                "persistence_decidable": result.persistence_decidable,
                "persistence_observed": result.persistence_observed,
                "reason": result.reason,
            },
            "authority": dict(AUTHORITY_SNAPSHOT),
        }

    @classmethod
    def build_acceptance_trace(
        cls,
        record: LineEventReadbackRecord,
    ) -> LineEventReadbackRecord:
        """Run the canonical event observation sequence for one line."""

        record.verify_digest()
        for event_name in LINE_EVENT_CHAINS[record.line_key]:
            record = cls.observe(
                record,
                event=event_name,
                status="running"
                if event_name == "worker_started"
                else "completed"
                if event_name in TERMINAL_READBACK_EVENTS
                else record.status,
                source="runtime",
            )
        return record


__all__ = [
    "AUTHORITY_SNAPSHOT",
    "DEFAULT_TIMESTAMP",
    "FAILURE_STATUSES",
    "KNOWN_LINE_KEYS",
    "LINE_EVENT_CHAINS",
    "QUEUED_STATUSES",
    "RUNNING_STATUSES",
    "SCHEMA_REF",
    "SUCCESS_TERMINAL_STATUSES",
    "TERMINAL_READBACK_EVENTS",
    "IllegalEventMigrationError",
    "LineEvent",
    "LineEventReadbackError",
    "LineEventReadbackPort",
    "LineEventReadbackRecord",
    "LineEventReadbackResult",
    "UnknownLineEventError",
    "UnknownLineKeyError",
    "non_empty_text",
    "normalize_line_key",
    "record_digest",
]
