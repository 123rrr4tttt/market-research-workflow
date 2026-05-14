# 2026-05-13 AgentChat Stream Hang RCA And R34 Fix

## User-Level Symptom

- User test showed AgentChat continuously thinking without returning content.
- The backend could answer a minimal direct free-chat probe, but the browser-backed UI path later caused `/api/v1/health` and fresh AgentChat turns to time out.

## Root Cause

The failure was not a model reasoning stall.

1. `AgentChatPage` mounted the backend session event stream in an effect that depended on `refetchBackendSession`.
2. That callback depended on React Query objects and could change identity after streamed events updated state.
3. Each streamed event triggered `setStreamEvents`, a re-render, effect cleanup/reopen, and another `/agent-sessions/{session_id}/stream` request.
4. An old open browser tab could keep the stale loop alive even after source code was fixed, so the backend needed its own stream backpressure.

## Changes

- Frontend:
  - Store the latest backend refresh callback in `refetchBackendSessionRef`.
  - Bind the session-stream effect only to `activeBackendSessionId`.
  - Result: one backend session owns one frontend stream.
- Backend:
  - Convert `iter_session_events` to an async iterator.
  - Add session-level active-stream throttling.
  - Add session-level burst-open throttling for stale clients that repeatedly reopen streams.
- Data quality path:
  - Keep R33 quality audit bounded by projected/truncated SQL columns rather than loading full ORM rows.

## Verification

- Direct quality-audit AgentCore SSE:
  - first byte: `0.02s`
  - complete answer: `14.704s`
  - tools: `project.summary.read`, `project.structured_data.quality_audit`
  - artifact: `development/latest-dev-docs/automation-runs/agent-core-live-user-audit-2026-05-13/r34_stream_hang_fix/quality_audit_direct_after_stream_flood_fix.json`
- Frontend UI on clean port:
  - URL: `http://127.0.0.1:5175/#agent-chat.html`
  - prompt: `你好，请直接回复一句话`
  - visible result: `你好！`
- Backend health after clean UI test:
  - `/api/v1/health` returned ok
  - backend RSS about `134MB`
  - backend CPU about `1%`
- Regression:
  - `67 passed, 11 warnings` for watcher, structured-data, agent-core, and agent-chat API tests.
  - `npm run lint` passed in `main/frontend-modern`.

## Remaining Operational Note

If a browser tab is still open on old port `5174`, it may keep stale JavaScript in memory. Use the clean fixed port `5175` or hard-refresh the old tab before evaluating interaction speed.
