# Wave8 Target Overlap Priority Evidence (2026-05-22)

Scope: local closure slice for prompt time-density priority semantics.

## Landed Slice

Wave8 made `target_overlap_gap` observable in the prompt density priority contract:

- `main/backend/app/services/stats/prompt_time_density.py` now includes target-overlap pressure in `shift_signal` and priority scoring.
- `main/backend/tests/unit/test_prompt_time_density_priority_unittest.py` locks the expected priority ordering when target-overlap evidence is missing.

## Status Boundary

This closes the narrow gap where the merged time-density plan described target overlap as a priority signal but the service did not make that signal affect the computed shift priority.

The topic remains `partial` because the broader OPE gate, source-time-window lifecycle, and production data validation are still outside this slice.

## Repeatable Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_prompt_time_density_priority_unittest.py \
  main/backend/tests/core_business/test_process_consistency_core_contract.py \
  -k prompt_time_density

python3 -m py_compile main/backend/app/services/stats/prompt_time_density.py
git diff --check
```

Observed in Wave8 integration:

- `3 passed, 1 deselected`
- `py_compile`: passed
- `git diff --check`: passed
