# Wave10 Time Semantics OPE Contract Evidence (2026-05-22)

Scope: local deterministic contract slice for the merged time-semantics/density plan.

## Landed Slice

Wave10 added one repeatable checker that covers the narrow closure targets still open after Wave8:

- checker: `main/backend/scripts/check_time_semantics_ope_contract.py`
- source-time-window contract:
  - trusted `source_time` becomes `effective_time`
  - task windows anchor to `effective_time`
  - prompt density document day resolution prefers explicit `effective_time/source_time`
- target-overlap priority contract:
  - `target_overlap_gap` remains observable
  - changing `target_overlap` changes priority probability
  - policy decision trace carries target-overlap fields
- OPE freshness contract:
  - OPE report contains freshness and importance-weight diagnostics
  - Go/No-Go can require OPE presence, minimum contexts, freshness, ESS ratio, and weight CV
  - stale OPE evidence fails the local deterministic gate

## Status Boundary

This closes a repository-controlled contract/checker slice. It does not close the broader production validation claim.

Known remaining gaps:

- live decision-log volume and reward feedback alignment are not verified in this worker branch
- production freshness is not claimed
- release pipeline wiring remains a separate integration/ops task

## Repeatable Validation

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  tests/unit/test_ingest_digestion_scaffold_unittest.py \
  tests/unit/test_prompt_time_density_priority_unittest.py \
  tests/unit/test_document_queries_policy_filters_unittest.py

/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  tests/unit/test_prompt_time_density_ope_gate_unittest.py \
  tests/unit/test_time_semantics_ope_contract_check_unittest.py

/Users/wangyiliang/.local/bin/python3.11 scripts/check_time_semantics_ope_contract.py
```

Observed locally:

- first pytest group: `20 passed`
- second pytest group: `4 passed`
- checker: `status=passed_with_known_gaps`, `failures=[]`
