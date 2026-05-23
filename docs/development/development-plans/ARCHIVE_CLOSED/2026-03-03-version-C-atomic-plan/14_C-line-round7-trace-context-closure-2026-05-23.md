# C-line Round7 Trace Context Closure (2026-05-23)

Status: `closed / wave38_verified`

## Scope

This closes the repo-local part of Round7 from
`13_C-line-round7-repo-mapping-and-min-implementation-2026-03-04.md`.

The closed requirement is the minimal trace context contract:

- `X-Trace-Id` is accepted and echoed in the response.
- W3C `traceparent` is parsed when `X-Trace-Id` is absent.
- API envelope `meta.trace_id` uses the resolved trace id.
- `X-Request-Id` remains the request correlation fallback.

## Code Landed

- `main/backend/app/main.py`
  - added minimal `traceparent` validation and trace-id extraction;
  - added `X-Trace-Id` response header;
  - updated success and error envelopes to use the resolved trace id.
- `main/backend/tests/e2e/test_request_context_headers_e2e.py`
  - covers `X-Trace-Id` echo;
  - covers `traceparent` trace-id extraction.
- `main/backend/tests/integration/test_api_exception_envelope_unittest.py`
  - covers request-id fallback in error envelopes;
  - covers `X-Trace-Id` in error envelope `meta.trace_id`.

## Validation

Run from the repository root:

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  tests/e2e/test_request_context_headers_e2e.py \
  tests/integration/test_api_exception_envelope_unittest.py \
  tests/e2e/test_runtime_observability_smoke_e2e.py
```

Expected result: all selected request-context and observability tests pass.

## Remaining Boundary

This closure does not add a new observability backend, OpenTelemetry SDK, or a
new required CI job. It only closes the repo-local trace-context contract that
Round7 identified as missing.
