# External Dependency Mock Baseline

This folder defines a baseline for tests that isolate code from external dependencies (HTTP, SDK clients, third-party services).

## Goals

- Keep unit/integration tests deterministic.
- Avoid real network calls in CI and local fast feedback loops.
- Provide repeatable examples for new tests.

## Strategy

- Prefer patching at the call site actually used by the target function.
- Use `pytest` `monkeypatch` or `unittest.mock` (`patch`, `Mock`) to replace external calls.
- Return minimal realistic responses (status code, payload shape, error behavior) needed by assertions.
- Verify both behavior and interaction:
  - behavior: returned values / raised errors
  - interaction: called URL/params/headers when relevant

## Marker

- Use `@pytest.mark.mocked` (or module-level `pytestmark`) for tests that mock external dependencies.
- `mocked` tests should not require real network access.

## Example

See `test_http_client_mock_unittest.py` in this folder.
