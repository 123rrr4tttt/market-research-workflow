# SA2 R15 C/D Closing

- scout_batch_id: `2026-03-04-scout-r15`
- execution_mode: `atomic + warning-first then blocking-by-line isolation`

## C line
- status: DONE (`C-R15-M1`, `C-R15-M2`)
- artifacts:
  - `/Users/wangyiliang/market-research-workflow/artifacts/gates/r15_c/problem-details-rfc9457-gate.json`
  - `/Users/wangyiliang/market-research-workflow/artifacts/gates/r15_c/otel-metric-schema-check.json`
- verification:
  - `/Users/wangyiliang/market-research-workflow/scripts/gates/run_r15_c_m1_problem_details_gate.sh /Users/wangyiliang/market-research-workflow` => passed
  - `/Users/wangyiliang/market-research-workflow/scripts/gates/run_r15_c_m2_otel_schema_gate.sh /Users/wangyiliang/market-research-workflow` => passed
- gate mapping:
  - M1: RFC9457 422 envelope + `migration_window_days` hard field
  - M2: OTel schema drift with `stable/experimental` semantic level check
- rollback_ref: `773c81b^`
- failure isolation: only C-line contract/observability gate path is impacted.

## D line
- status: DONE (`D-R15-M1`, `D-R15-M2`)
- artifacts:
  - `/Users/wangyiliang/market-research-workflow/artifacts/gates/r15_d/provenance-blocking-gate.json`
  - `/Users/wangyiliang/market-research-workflow/artifacts/gates/r15_d/llm-safety-gate-report.json`
- verification:
  - `/Users/wangyiliang/market-research-workflow/scripts/gates/run_r15_d_m1_provenance_gate.sh /Users/wangyiliang/market-research-workflow` => passed
  - `/Users/wangyiliang/market-research-workflow/scripts/gates/run_r15_d_m2_safety_gate.sh /Users/wangyiliang/market-research-workflow` => passed
- gate mapping:
  - M1: provenance missing-field fail-fast (exit 37) with D-line-only blocking isolation
  - M2: input/retrieval/output three-stage report output `llm-safety-gate-report.json`
- rollback_ref: `TBD_AFTER_D_COMMIT^`
- failure isolation: only D-line publish chain is impacted.

## unified verification
- command: `/Users/wangyiliang/market-research-workflow/scripts/gates/run_r15_cd_verification_slice.sh /Users/wangyiliang/market-research-workflow`
- result: `[r15-cd] passed`
