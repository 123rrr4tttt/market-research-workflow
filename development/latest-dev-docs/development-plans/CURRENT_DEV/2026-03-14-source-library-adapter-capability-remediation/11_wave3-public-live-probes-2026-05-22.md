# Wave3 Public Live Probes - 2026-05-22

## Scope

This lane advances the Wave2 blocker for public anti-bot / dirty-source replay. It does not pretend that the full historical `demo_proj` 45-site replay is closed. It adds a repeatable public live probe with an explicit public-network gate and records the first four-target evidence snapshot.

Evidence package:

- [source-library-live-probes/2026-05-22](../../../automation-runs/source-library-live-probes/2026-05-22/README.md)
- Script: `main/backend/scripts/source_library_public_live_probes.py`
- Gate test: `main/backend/tests/unit/test_source_library_public_live_probe_gate_unittest.py`

## What Changed

- Public network execution is opt-in through `--allow-public-network` or `SOURCE_LIBRARY_ALLOW_PUBLIC_PROBES=1`.
- Default execution is skip-safe and exits cleanly without contacting public websites.
- Results distinguish:
  - `candidate_ready`
  - `candidate_ready_with_term_fallback`
  - `anti_bot_or_transport_blocked`
  - `transport_blocked`
  - `parser_or_source_semantics_blocked`
  - `empty_public_result`
- `candidate_ready_with_term_fallback` is intentionally not treated as full dirty-source closure.

## Current Public Evidence

Live run, 2026-05-22:

| Target | Status | Candidates | Closure meaning |
| --- | --- | ---: | --- |
| `commercialobserver_parser_weak` | `candidate_ready_with_term_fallback` | 21 | Public fetch and parser path work, but relevance still needs review because term fallback selected the result set. |
| `pymnts_parser_weak` | `candidate_ready` | 2 | Public fetch and selected candidate path work without term fallback. |
| `investopedia_validated_query` | `candidate_ready` | 17 | Public baseline works without term fallback. |
| `hai_stanford_mixed_shell` | `candidate_ready_with_term_fallback` | 6 | Public fetch works, but dynamic/research-hub semantics still need relevance review. |

No selected target hit a 403/429/transport blocker in this environment. The remaining shortlist is relevance-oriented rather than network-blocked:

- `commercialobserver_parser_weak`
- `hai_stanford_mixed_shell`

## Status Against AT-AC Items

| Item | Status | Evidence |
| --- | --- | --- |
| `AT-AC-06` anti-bot / transport resilience | advanced, not globally closed | Public live run produced candidate-ready evidence with zero transport errors on the selected target set; skip-safe gate records blockers when public network is unavailable. |
| `AT-AC-10` real site-entry replay / dirty-source shortlist | partial | A controlled shortlist is now generated. Full closure still requires expanding beyond the selected four targets or replaying the full historical `demo_proj` site-entry set in a controlled environment. |

## Validation

```bash
cd main/backend
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python -m pytest -q \
  tests/unit/test_source_library_public_live_probe_gate_unittest.py
```

Result: `4 passed, 2 warnings`.

```bash
cd main/backend
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python scripts/source_library_public_live_probes.py \
  --target-file ../../development/latest-dev-docs/automation-runs/source-library-live-probes/2026-05-22/input.json \
  --output ../../development/latest-dev-docs/automation-runs/source-library-live-probes/2026-05-22/output.json \
  --log-output ../../development/latest-dev-docs/automation-runs/source-library-live-probes/2026-05-22/logs/live-probe.log \
  --probe-timeout 6 \
  --allow-public-network
```

Result: `passed`, `live_evidence_sufficient=true`, `status_counts={"candidate_ready": 2, "candidate_ready_with_term_fallback": 2}`.
