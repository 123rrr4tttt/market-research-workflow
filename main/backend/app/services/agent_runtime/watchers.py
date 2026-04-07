from __future__ import annotations

import json
import time
from typing import Any, Iterable


def iter_session_events(
    *,
    service: Any,
    session_id: str,
    since_seq: int = 0,
    poll_seconds: float = 1.0,
    max_seconds: int = 30,
) -> Iterable[str]:
    started = time.time()
    last_seq = max(0, int(since_seq or 0))
    interval = max(0.2, min(float(poll_seconds or 1.0), 5.0))
    ttl = max(5, min(int(max_seconds or 30), 300))
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
        time.sleep(interval)
