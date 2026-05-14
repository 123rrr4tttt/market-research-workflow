from __future__ import annotations

import asyncio
from collections import deque
import json
import threading
import time
from typing import Any, AsyncIterator, Deque

_ACTIVE_STREAMS_BY_SESSION: dict[str, int] = {}
_STREAM_OPEN_TIMES_BY_SESSION: dict[str, Deque[float]] = {}
_ACTIVE_STREAMS_LOCK = threading.Lock()
_MAX_ACTIVE_STREAMS_PER_SESSION = 2
_STREAM_BURST_WINDOW_SECONDS = 10.0
_MAX_STREAM_OPENS_PER_WINDOW = 8
_STREAM_RETRY_MS = 30_000


def _try_claim_stream(session_id: str) -> bool:
    with _ACTIVE_STREAMS_LOCK:
        active = _ACTIVE_STREAMS_BY_SESSION.get(session_id, 0)
        if active >= _MAX_ACTIVE_STREAMS_PER_SESSION:
            return False
        _ACTIVE_STREAMS_BY_SESSION[session_id] = active + 1
        return True


def _release_stream(session_id: str) -> None:
    with _ACTIVE_STREAMS_LOCK:
        active = _ACTIVE_STREAMS_BY_SESSION.get(session_id, 0)
        if active <= 1:
            _ACTIVE_STREAMS_BY_SESSION.pop(session_id, None)
        else:
            _ACTIVE_STREAMS_BY_SESSION[session_id] = active - 1


def _is_stream_bursting(session_id: str) -> bool:
    now = time.time()
    with _ACTIVE_STREAMS_LOCK:
        timestamps = _STREAM_OPEN_TIMES_BY_SESSION.setdefault(session_id, deque())
        while timestamps and now - timestamps[0] > _STREAM_BURST_WINDOW_SECONDS:
            timestamps.popleft()
        timestamps.append(now)
        return len(timestamps) > _MAX_STREAM_OPENS_PER_WINDOW


async def _yield_throttled_stream(session_id: str, reason: str) -> AsyncIterator[str]:
    yield f"retry: {_STREAM_RETRY_MS}\n"
    yield "event: stream_throttled\n"
    yield (
        "data: "
        + json.dumps(
            {
                "event_type": "stream_throttled",
                "session_id": session_id,
                "reason": reason,
                "retry_ms": _STREAM_RETRY_MS,
            },
            ensure_ascii=False,
        )
        + "\n\n"
    )
    await asyncio.sleep(_STREAM_RETRY_MS / 1000)


async def iter_session_events(
    *,
    service: Any,
    session_id: str,
    since_seq: int = 0,
    poll_seconds: float = 1.0,
    max_seconds: int = 30,
) -> AsyncIterator[str]:
    if _is_stream_bursting(session_id):
        async for chunk in _yield_throttled_stream(session_id, "too_many_stream_opens_for_session"):
            yield chunk
        return

    if not _try_claim_stream(session_id):
        async for chunk in _yield_throttled_stream(session_id, "too_many_active_streams_for_session"):
            yield chunk
        return

    started = time.time()
    last_seq = max(0, int(since_seq or 0))
    interval = max(0.2, min(float(poll_seconds or 1.0), 5.0))
    ttl = max(5, min(int(max_seconds or 30), 300))
    try:
        while time.time() - started <= ttl:
            events = service.list_events(session_id)
            emitted = False
            for event in events:
                seq = int(event.get("seq") or 0)
                if seq <= last_seq:
                    continue
                emitted = True
                last_seq = seq
                yield f"id: {seq}\n"
                yield f"event: {event.get('event_type')}\n"
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if not emitted:
                yield ": keep-alive\n\n"
            await asyncio.sleep(interval)
    finally:
        _release_stream(session_id)
