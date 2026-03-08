# Prompt-Time-Density Go/No-Go Report

- decision: `GO`
- gate_realcase: `True` (failed=0)
- gate_p95: `True` (p95=0.82, threshold=1.5)
- gate_error_rate: `True` (error_rate=0.001, threshold=0.01)

## Rollback Steps
1. Stop rollout and freeze new traffic to prompt-time-density endpoints.
2. Revert backend entries in `main/backend/app/api/stats.py` and `main/backend/app/services/stats/`.
3. Revert scheduler integration in `main/backend/app/services/tasks.py`.
4. Re-run core contracts and realcase checks before re-enable.

## Verification Commands
```bash
cd main/backend
python3.11 -m pytest -q tests/core_business/test_api_group_a_core_contract.py tests/core_business/test_process_consistency_core_contract.py -k "prompt_time_density or invalid"
python3.11 scripts/run_realcase_prompt_time_density.py --project demo_proj --case-set all --fail-fast
```