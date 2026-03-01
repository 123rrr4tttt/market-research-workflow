# Backend Test Strategy

This directory follows a layered test strategy:

- `unit/`: isolated logic tests, no external dependency required.
- `integration/`: application wiring and module interaction tests.
- `contract/`: API/envelope/OpenAPI contract stability tests.
- `e2e/`: smoke tests for request path behavior.

## Markers

Configured in `main/backend/pytest.ini`:

- `unit`
- `integration`
- `contract`
- `e2e`
- `slow`
- `external`

## Local Commands

Run from `main/backend`:

```bash
.venv311/bin/python -m pytest -m unit -q
.venv311/bin/python -m pytest -m integration -q
.venv311/bin/python -m pytest -m contract -q
.venv311/bin/python -m pytest -m e2e -q
.venv311/bin/python -m pytest -q
```

## CI Gate Policy

- `pull_request`:
  - `unit-check`
  - `integration-check`
  - `docker-check`
- `push` to `main`, `schedule`, `workflow_dispatch`:
  - `unit-check`
  - `integration-check`
  - `contract-check`
  - `e2e-check`
  - `docker-check`

This keeps PR feedback fast while preserving full layered validation on mainline.
