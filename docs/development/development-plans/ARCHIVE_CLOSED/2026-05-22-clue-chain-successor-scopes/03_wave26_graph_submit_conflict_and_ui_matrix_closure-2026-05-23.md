# Wave26 Graph Submit Conflict And UI Matrix Closure

Date: 2026-05-23
Status: `external_blocked` / `wave26_checked`

## Decision

Move `2026-05-22-clue-chain-successor-scopes` from `CURRENT_DEV` to `ARCHIVE_EXTERNAL_BLOCKED`.

Wave26 closed the two repo-local successor gates that caused the Wave22 retain-current decision:

- `Production graph-submit conflict handling`
- `Broader UI / visual regression`

The only remaining successor scope is `Live provider reliability`, which depends on external provider availability and opt-in live probes. That condition is not a repo-local blocker and should not keep this directory counted in the `CURRENT_DEV` `partial` total.

## Repo-Local Evidence

### Graph Submit Conflict

Changed files:

- `main/backend/app/services/clue_chains/graph_integration.py`
- `main/backend/app/services/clue_chains/__init__.py`
- `main/backend/tests/unit/test_clue_chain_graph_integration_unittest.py`
- `main/backend/tests/unit/test_workflow_graph_curated_service_unittest.py`
- `main/frontend-modern/src/pages/GraphPage.tsx`
- `main/frontend-modern/tests/e2e/graphpage.spec.ts`

Closed behavior:

- Clue Chain graph handoff output now has a staged submit bridge envelope.
- Stale `base_revision` is expressed as a `version_conflict` envelope without mutating graph state.
- Curated submit conflict readback confirms no extra audit record is appended on stale Clue Chain bridge submit.
- GraphPage exposes `submit_conflict: version_conflict expected=... actual=...`.
- The conflict path does not auto retry or clear the draft.

### UI / Visual Matrix

Changed files:

- `main/frontend-modern/src/pages/GraphPage.tsx`
- `main/frontend-modern/src/pages/graph/ClueChainInspector.tsx`
- `main/frontend-modern/tests/e2e/graph-clue-chain.spec.ts`

Closed behavior:

- selected-node seed path
- dense graph route path
- blocked provider attribution
- reviewed candidate non-pending state
- disabled actions after reviewed state
- evidence drawer content binding

## Verification

Passed:

```bash
cd /Users/wangyiliang/market-research-workflow/main/backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest tests/unit/test_clue_chain_graph_integration_unittest.py tests/unit/test_workflow_graph_curated_service_unittest.py -q
```

Result: `12 passed, 2 warnings`.

Passed:

```bash
cd /Users/wangyiliang/market-research-workflow/main/frontend-modern
./node_modules/.bin/playwright test tests/e2e/graph-clue-chain.spec.ts --project=chromium
```

Result: `4 passed`.

Passed:

```bash
cd /Users/wangyiliang/market-research-workflow/main/frontend-modern
./node_modules/.bin/playwright test tests/e2e/graphpage.spec.ts --project=chromium --grep "curated submit conflict"
```

Result: `1 passed`.

## Remaining External Condition

`Live provider reliability` remains open until an opt-in live provider run records:

- provider identity: SearXNG, YaCy, or project search adapter;
- query and retry outcome;
- raw and normalized result counts;
- duplicate count;
- blocked reason when credentials, service startup, or network availability is missing.

Until those provider conditions are supplied, keep this directory in `ARCHIVE_EXTERNAL_BLOCKED`, not `ARCHIVE_CLOSED`.
