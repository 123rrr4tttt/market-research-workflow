# Wave19 Ingest Canary 24h Metrics Artifact

Date: 2026-05-22

Scope: `2026-03-02-meaningful-ingest-guardrails-plan`

Status marker:
`partial_meaningful_ingest_canary_24h_metrics_artifact_landed`

## Evidence

Wave19 adds a deterministic 24h metrics artifact gate for meaningful ingest guardrail rollout review.

- contract_version: ingest.canary_24h_metrics_artifact.v1
- deterministic_fixture: true
- window_hours: 24
- single_url_first_allocation: true
- live_production_canary_claim: false
- metric_24h_live_readback_claim: false
- closure_claim: false

The checker verifies the artifact carries rejection-rate, inserted-valid-ratio, reason-code, adapter, and guardrail rollout count fields. Digest validation fails if any metric or live-boundary flag is mutated after write/read.

## Landed Surface

- `main/backend/scripts/check_ingest_canary_24h_metrics_artifact.py`
- `main/backend/tests/unit/test_ingest_canary_24h_metrics_artifact_unittest.py`

## Remaining Boundary

`partial` remains because this worker did not execute a live guardrail rollout canary.

- `settings.ingest_enable_strict_gate` remains a production operations decision.
- Production 24h rejection-rate and inserted-valid ratio inspection remains open.
- The deterministic artifact must not be treated as live 24h metric validation.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_24h_metrics_artifact.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_24h_metrics_artifact_unittest.py
```
