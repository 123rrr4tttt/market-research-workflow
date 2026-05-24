# Wave56 Crossref Official API Provider Maturity

Date: 2026-05-23

Scope: `2026-03-02-single-url-first-ingest-allocation-plan`

Decision marker:
`single_url_non_arxiv_official_api_provider_reduced`

## Result

This slice reduces the non-arXiv official API provider blocker with a landed public Crossref works API provider. `official_access.api` is no longer arXiv-only for the single-URL allocation path:

- `provider_key=crossref` executes `crossref_works_api` against `https://api.crossref.org/works`.
- `crossref.org` routes through `api_preferred` / `official_access.api` instead of HTML search templates.
- The provider returns normalized DOI URLs plus candidate record metadata and keeps transport failures explicit.
- The gate can run a live public Crossref probe, but it does not claim browser replay, configured demo canary closure, production 24h metrics, or all-project strict-gate promotion.

## Landed Surface

- `main/backend/app/services/source_library/adapters/official_access.py`
- `main/backend/app/services/resource_pool/site_search_policy.py`
- `main/backend/scripts/check_single_url_official_api_provider_maturity.py`
- `main/backend/tests/unit/test_source_library_official_access_adapter_unittest.py`

## Evidence

Artifact:

- `development/latest-dev-docs/automation-runs/single-url-official-api-provider-maturity/2026-05-23/official_api_provider_maturity.json`

Expected successful gate:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_single_url_official_api_provider_maturity.py --allow-live-crossref --require-live-crossref --write-report development/latest-dev-docs/automation-runs/single-url-official-api-provider-maturity/2026-05-23/official_api_provider_maturity.json
```

## Remaining Boundary

`closure_claim=false`.

This closes only the repo-local/public Crossref portion of the non-arXiv provider maturity blocker. The target remains external-blocked on:

- public browser/runtime replay for high-JS domains
- configured-service single-URL canary for `demo_proj`
- production 24h metrics readback from URL pool output
- provider-specific credentials and quota behavior beyond public Crossref

Provider credential/quota evidence is intentionally two-tiered:

- `configured_only`: credential presence may be recorded without live authorization, but it cannot satisfy external blocker closure.
- `validated`: requires explicit `live_probe_authorized=true`, a passed live probe, provider-specific quota validation, and `credential_material_logged=false`.

Provider artifacts must not include API keys, tokens, passwords, client secrets, private keys, authorization headers, or other credential values.
The checker records only safe status fields and fails artifacts that expose secret-bearing fields.
