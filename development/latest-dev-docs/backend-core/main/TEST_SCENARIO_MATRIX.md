# Test Scenario Matrix

Last updated: 2026-03-01

<!-- markdownlint-disable MD013 -->

## Scope

- Capability-oriented scenario matrix for backend core.
- Scenario types are fixed to: `happy`, `edge`, `error`, `timeout-retry`.
- Layer mapping uses: `unit` / `integration` / `contract` / `e2e`.
- Coverage status uses: `covered` / `partial` / `gap`.

## Matrix

| Capability Domain | Scenario Type | Representative Scenario | Layer Mapping | Owner | Current Coverage |
| --- | --- | --- | --- | --- | --- |
| Health Check | happy | `GET /health` returns stable `status=ok` envelope | integration, contract, e2e | backend-core | covered |
| Health Check | edge | `GET /health/deep` with one non-critical dependency degraded still returns actionable status payload | integration, e2e | backend-core | partial |
| Health Check | error | deep health with critical dependency down returns deterministic error classification | unit, integration, contract | backend-core | partial |
| Health Check | timeout-retry | health probe timeout and retry/backoff behavior remains bounded | unit, integration | platform-sre | gap |
| Search API | happy | `GET /search` standard query returns items + pagination envelope | integration, contract, e2e | search-api | partial |
| Search API | edge | empty query or high page/limit boundary handled with stable defaults and metadata | unit, contract | search-api | partial |
| Search API | error | invalid params return `INVALID_INPUT` and proper HTTP mapping | unit, contract, integration | search-api | covered |
| Search API | timeout-retry | upstream search provider timeout triggers fallback/retry policy | unit, integration, e2e | search-api | gap |
| Ingestion Pipeline | happy | `POST /ingest/*` synchronous path persists expected payload | integration, contract | ingest-pipeline | partial |
| Ingestion Pipeline | edge | duplicate payload/idempotency path avoids duplicated side effects | unit, integration | ingest-pipeline | gap |
| Ingestion Pipeline | error | malformed or unsupported source payload returns normalized error envelope | unit, contract, integration | ingest-pipeline | partial |
| Ingestion Pipeline | timeout-retry | async ingest task transient failure retries and records terminal status | unit, integration, e2e | ingest-pipeline | gap |
| Discovery Workflows | happy | `POST /discovery/search` returns ranked candidates | integration, contract, e2e | discovery-engine | partial |
| Discovery Workflows | edge | keyword generation with sparse input still returns bounded, valid keyword set | unit, integration | discovery-engine | gap |
| Discovery Workflows | error | provider or parsing failure maps to `UPSTREAM_ERROR` / `PARSE_ERROR` | unit, contract, integration | discovery-engine | partial |
| Discovery Workflows | timeout-retry | long-running discovery timeout, cancel, and retry path is deterministic | unit, integration, e2e | discovery-engine | gap |
| API Envelope & Contract | happy | success response always conforms to `status/data/error/meta` envelope | contract, integration | api-contract | covered |
| API Envelope & Contract | edge | optional fields and pagination metadata remain backward compatible | contract, integration | api-contract | partial |
| API Envelope & Contract | error | all business/system errors map to documented code + HTTP status | unit, contract, integration | api-contract | partial |
| API Envelope & Contract | timeout-retry | timeout/retry error response schema remains contract-stable | contract, integration | api-contract | gap |
| Async Task Orchestration | happy | `async_mode=true` returns valid `task_id`, task progresses to completion | integration, e2e | async-runtime | partial |
| Async Task Orchestration | edge | duplicate submit or poll-after-expire behavior is deterministic | unit, integration | async-runtime | gap |
| Async Task Orchestration | error | task execution exception surfaces normalized terminal failure state | unit, integration, contract | async-runtime | partial |
| Async Task Orchestration | timeout-retry | worker timeout, retry limit, and dead-letter/failure record behavior is verifiable | unit, integration, e2e | async-runtime | gap |

## Ownership Notes

- `backend-core`: health and shared runtime behavior.
- `search-api`: search endpoint behaviors and upstream integration strategy.
- `ingest-pipeline`: ingest flow, idempotency, and persistence side effects.
- `discovery-engine`: discovery/deep/smart workflows.
- `api-contract`: envelope compatibility and OpenAPI/contract stability.
- `async-runtime`: async task lifecycle, retry, and observability.

## Coverage Summary

- `covered`: baseline exists in current automation and is part of active CI gates.
- `partial`: some assertions exist, but scenario depth or layer completeness is insufficient.
- `gap`: no reliable automated coverage yet; should be prioritized in next test planning cycle.

<!-- markdownlint-enable MD013 -->
