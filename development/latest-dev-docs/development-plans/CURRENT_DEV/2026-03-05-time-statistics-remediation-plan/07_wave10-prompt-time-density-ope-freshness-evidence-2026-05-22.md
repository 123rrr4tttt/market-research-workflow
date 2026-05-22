# Wave10 Prompt-Time Density OPE Freshness Evidence (2026-05-22)

Scope: local deterministic closure slice for prompt-time-density release freshness and OPE gate behavior.

## Landed Slice

- `main/backend/scripts/run_prompt_time_density_ope.py` now emits deterministic OPE diagnostics:
  - `effective_sample_size`
  - `effective_sample_size_ratio`
  - `weight_cv`
  - `propensity_missing_rate`
  - `reward_proxy_rate`
  - `freshness.status`
  - `freshness.latest_age_hours`
- `main/backend/scripts/generate_prompt_time_density_gonogo.py` now supports strong OPE gate inputs:
  - `--require-ope`
  - `--ope-min-contexts`
  - `--ope-max-latest-age-hours`
  - `--ope-min-ess-ratio`
  - `--ope-max-weight-cv`
- `main/backend/tests/unit/test_prompt_time_density_ope_gate_unittest.py` locks the fresh/stale OPE behavior without relying on production data.

## Status Boundary

This closes the warehouse-local OPE freshness checker and Go/No-Go strong-gate contract. It does not claim real production data has passed the OPE gate.

Known remaining gaps:

- live `prompt_time_policy_decision_logs` volume not verified here
- live `prompt_time_window_feedback` reward alignment not verified here
- release pipeline has not been wired to require this gate by default

## Repeatable Validation

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  tests/unit/test_prompt_time_density_ope_gate_unittest.py \
  tests/unit/test_time_semantics_ope_contract_check_unittest.py
```

Observed locally:

- `4 passed`

Combined Wave10 checker:

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 scripts/check_time_semantics_ope_contract.py
```

Observed locally:

- `status=passed_with_known_gaps`
- `ope_freshness_gate.diagnostics_present=true`
- `ope_freshness_gate.fresh_gate_go=true`
- `ope_freshness_gate.stale_gate_no_go=true`
