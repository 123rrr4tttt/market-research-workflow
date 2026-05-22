# Source Library Search Governance Checker (2026-05-22)

## Scope

This run is a no-network governance gate for Wave10 worker5. It checks:

1. source-library search-chain mount routes
2. `site_search -> handler.cluster -> unified_search` routing invariants
3. `search_template` adapter capability/profile downgrade and review states
4. public replay known gaps and term-fallback relevance-review boundaries

## Artifact

- `output.json`

## Command

```bash
python3.11 main/backend/scripts/check_source_library_search_governance.py \
  --repo-root . \
  --output development/latest-dev-docs/automation-runs/source-library-search-governance/2026-05-22/output.json
```

## Result

- `validation.passed=true`
- `validation.public_network_attempted=false`
- `governance_scope.claims_full_45_site_public_replay=false`
- `governance_scope.claims_human_relevance_review_complete=false`

## Boundary

This checker does not run the public 45-site replay and does not claim human relevance review completion. It only keeps those blockers explicit and machine-checkable.
